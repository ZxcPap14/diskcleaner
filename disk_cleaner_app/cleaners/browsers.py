"""🌐 Очистители браузеров: Chromium-семейство и Firefox."""
from __future__ import annotations

import configparser
import json
from pathlib import Path

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    get_dir_size,
    safe_rm_contents,
)
from disk_cleaner_app.models.item import GROUP_BROWSERS, SafetyLevel
from disk_cleaner_app.models.target import LAYER_SAFE

LOCAL = Path.home() / "AppData" / "Local"
ROAMING = Path.home() / "AppData" / "Roaming"

# Кэши Chromium. Сами папки не удаляем — чистим содержимое.
CHROMIUM_CACHE_DIRS = (
    "Cache",
    "Code Cache",
    "GPUCache",
    "DawnCache",
    "GrShaderCache",
    "ShaderCache",
    "GraphiteDawnCache",
    "GPUPersistentCache",
    "Media Cache",
)
CHROMIUM_SERVICE_WORKER = Path("Service Worker") / "CacheStorage"


def chromium_profiles(user_data: Path) -> list[Path]:
    """Профили Chromium: Local State + типовые имена папок."""
    if not user_data.exists():
        return []

    names: set[str] = set()
    try:
        with open(user_data / "Local State", encoding="utf-8") as f:
            state = json.load(f)
        info = state.get("profile", {}).get("info_cache", {})
        if isinstance(info, dict):
            names.update(str(name) for name in info)
    except (OSError, ValueError, TypeError):
        pass

    try:
        for child in user_data.iterdir():
            if not child.is_dir():
                continue
            if child.name == "Default" or child.name == "Guest Profile" \
                    or child.name.startswith("Profile "):
                names.add(child.name)
    except OSError:
        pass

    return [
        user_data / name for name in sorted(names)
        if (user_data / name).is_dir()
    ]


class ChromiumCacheMixin:
    """Общий код для Chrome/Edge/Yandex/Brave/Vivaldi."""

    browser_name = "Chromium"
    user_data: Path

    def _cache_paths(self) -> list[Path]:
        paths: list[Path] = []
        profiles = chromium_profiles(self.user_data)
        if not profiles and self.user_data.exists():
            # Opera и некоторые сборки хранят кэш прямо в каталоге профиля.
            profiles = [self.user_data]
        for profile in profiles:
            for name in CHROMIUM_CACHE_DIRS:
                p = profile / name
                if p.exists():
                    paths.append(p)
            service = profile / CHROMIUM_SERVICE_WORKER
            if service.exists():
                paths.append(service)
        return paths

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._cache_paths())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self._cache_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self._cache_paths():
            if p.exists() and not safe_rm_contents(p):
                ok = False
        return (
            ("OK", f"{self.browser_name}: кэш очищен")
            if ok else
            ("ERR", f"{self.browser_name}: часть файлов занята — закройте браузер")
        )


class _BrowserBase(ChromiumCacheMixin, BaseCleaner):
    group = GROUP_BROWSERS
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш браузера пересоздаётся; пароли, история и закладки не затрагиваются."
    loss = "Сайты загрузятся чуть медленнее; входы и настройки сохраняются."


class ChromeCacheCleaner(_BrowserBase):
    id = "chrome_cache"
    name = "🌐 Chrome — Кэш"
    browser_name = "Chrome"
    description = "Chrome Cache / Code Cache / GPU Cache (все профили)"
    user_data = LOCAL / "Google" / "Chrome" / "User Data"


class EdgeCacheCleaner(_BrowserBase):
    id = "edge_cache"
    name = "🌐 Edge — Кэш"
    browser_name = "Edge"
    description = "Edge Cache / Code Cache (все профили)"
    user_data = LOCAL / "Microsoft" / "Edge" / "User Data"


class YandexCacheCleaner(_BrowserBase):
    id = "yandex_cache"
    name = "🌐 Yandex Browser — Кэш"
    browser_name = "Yandex"
    description = "Yandex Cache (все профили)"
    user_data = LOCAL / "Yandex" / "YandexBrowser" / "User Data"


class BraveCacheCleaner(_BrowserBase):
    id = "brave_cache"
    name = "🦁 Brave — Кэш"
    browser_name = "Brave"
    description = "Brave Cache / Code Cache (все профили)"
    user_data = LOCAL / "BraveSoftware" / "Brave-Browser" / "User Data"


class VivaldiCacheCleaner(_BrowserBase):
    id = "vivaldi_cache"
    name = "🌐 Vivaldi — Кэш"
    browser_name = "Vivaldi"
    description = "Vivaldi Cache / Code Cache (все профили)"
    user_data = LOCAL / "Vivaldi" / "User Data"


class OperaCacheCleaner(_BrowserBase):
    id = "opera_cache"
    name = "🌐 Opera — Кэш"
    browser_name = "Opera"
    description = "Opera Cache / Code Cache"
    user_data = LOCAL / "Opera Software" / "Opera Stable"


# ── Firefox ────────────────────────────────────────────

FIREFOX_CACHE_DIRS = ("cache2", "startupCache", "offlineCache", "shader-cache")


def _firefox_profile_names() -> set[str]:
    """Имена профилей из profiles.ini (без обращения к сети)."""
    names: set[str] = set()
    ini = ROAMING / "Mozilla" / "Firefox" / "profiles.ini"
    if ini.exists():
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(ini, encoding="utf-8")
            for section in parser.sections():
                if not section.startswith("Profile"):
                    continue
                raw = parser.get(section, "Path", fallback="").strip()
                if raw:
                    names.add(Path(raw).name)
        except (OSError, configparser.Error):
            pass
    local_root = LOCAL / "Mozilla" / "Firefox" / "Profiles"
    try:
        if local_root.exists():
            names.update(p.name for p in local_root.iterdir() if p.is_dir())
    except OSError:
        pass
    return names


class FirefoxCacheCleaner(BaseCleaner):
    id = "firefox_cache"
    name = "🦊 Firefox — Кэш"
    group = GROUP_BROWSERS
    description = "Firefox cache2 / startupCache (все профили)"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш Firefox пересоздаётся; закладки, пароли и история не затрагиваются."
    loss = "Страницы загрузятся чуть медленнее."

    def _cache_paths(self) -> list[Path]:
        paths: list[Path] = []
        roots = [
            LOCAL / "Mozilla" / "Firefox" / "Profiles",
            ROAMING / "Mozilla" / "Firefox" / "Profiles",
        ]
        for root in roots:
            for name in _firefox_profile_names():
                profile = root / name
                for sub in FIREFOX_CACHE_DIRS:
                    p = profile / sub
                    if p.exists():
                        paths.append(p)
        # Убираем дубли (Roaming и Local могут указывать на один профиль).
        seen: set[str] = set()
        unique: list[Path] = []
        for p in paths:
            key = str(p).lower()
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._cache_paths())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self._cache_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self._cache_paths():
            if p.exists() and not safe_rm_contents(p):
                ok = False
        return ("OK", "Firefox кэш очищен") if ok else (
            "ERR", "Часть файлов занята — закройте Firefox"
        )


BROWSER_CLEANERS = [
    ChromeCacheCleaner,
    EdgeCacheCleaner,
    YandexCacheCleaner,
    BraveCacheCleaner,
    VivaldiCacheCleaner,
    OperaCacheCleaner,
    FirefoxCacheCleaner,
]
