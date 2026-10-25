"""💬 Очистители приложений: Discord, Telegram, Slack, Zoom, Steam, etc."""
from __future__ import annotations

import os
from pathlib import Path

from disk_cleaner_app.cleaners.base import BaseCleaner, get_dir_size, safe_rm_contents
from disk_cleaner_app.models.item import GROUP_APPS, SafetyLevel
from disk_cleaner_app.models.target import LAYER_COMPONENTS, LAYER_SAFE

LOCAL = Path.home() / "AppData" / "Local"
ROAMING = Path.home() / "AppData" / "Roaming"
TEMP = Path.home() / "AppData" / "Local" / "Temp"


class DiscordCacheCleaner(BaseCleaner):
    id = "discord"
    name = "💬 Discord Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Discord\\app-*\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш Discord пересоздаётся; вход и настройки не затрагиваются."
    loss = "Каналы и вложения будут загружаться чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        base = LOCAL / "Discord"
        if not base.exists():
            return ()
        paths: list[Path] = []
        for folder in base.iterdir():
            if not folder.is_dir():
                continue
            for sub in ("Cache", "Code Cache", "GPUCache"):
                p = folder / sub
                if p.exists():
                    paths.append(p)
        return tuple(paths)

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if p.exists() and not safe_rm_contents(p):
                ok = False
        return ("OK", "Discord cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Discord"
        )


class TelegramCacheCleaner(BaseCleaner):
    id = "telegram"
    name = "💬 Telegram Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Telegram Desktop\\tdata\\user_data\\cache"
    safety = SafetyLevel.CAUTION
    layer = LAYER_SAFE
    why = "Медиа-кэш Telegram можно удалить; ключи и сессии в tdata не трогаем."
    loss = "Медиа будет скачано заново; аккаунт и история не пострадают."
    restore_hint = "Откройте Telegram — кэш заполнится сам."

    def _cache_dirs(self) -> list[Path]:
        user_data = ROAMING / "Telegram Desktop" / "tdata" / "user_data"
        if not user_data.exists():
            return []
        allowed = {"cache", "media_cache", "webview"}
        return [
            p for p in user_data.iterdir()
            if p.is_dir() and p.name.lower() in allowed
        ]

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._cache_dirs())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self._cache_dirs())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self._cache_dirs():
            if not safe_rm_contents(p):
                ok = False
        return ("OK", "Telegram cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Telegram и повторите."
        )


class SlackCacheCleaner(BaseCleaner):
    id = "slack"
    name = "💬 Slack Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Slack\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш Slack пересоздаётся; сообщения хранятся на сервере."
    loss = "Каналы будут загружаться чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        base = ROAMING / "Slack"
        candidates = [
            base / "Cache",
            base / "Code Cache",
            base / "GPUCache",
            base / "Service Worker" / "CacheStorage",
        ]
        return tuple(p for p in candidates if p.exists())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if not safe_rm_contents(p):
                ok = False
        return ("OK", "Slack cache очищен") if ok else ("ERR", "Ошибка")


class TeamsCacheCleaner(BaseCleaner):
    id = "teams"
    name = "💬 Microsoft Teams Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Microsoft\\Teams\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш классического Teams; сообщения и файлы хранятся в облаке."
    loss = "Teams загрузится чуть медленнее; вход сохраняется."

    def affected_paths(self) -> tuple[Path, ...]:
        base = ROAMING / "Microsoft" / "Teams"
        candidates = [
            base / "Cache",
            base / "Code Cache",
            base / "GPUCache",
            base / "Service Worker" / "CacheStorage",
        ]
        return tuple(p for p in candidates if p.exists())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if not safe_rm_contents(p):
                ok = False
        return ("OK", "Teams cache очищен") if ok else ("ERR", "Ошибка")


class ZoomCacheCleaner(BaseCleaner):
    id = "zoom"
    name = "💬 Zoom Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Zoom\\cache и logs"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш и логи Zoom; папку data с настройками не трогаем."
    loss = "Логи и временные файлы будут созданы заново."

    def affected_paths(self) -> tuple[Path, ...]:
        base = ROAMING / "Zoom"
        candidates = [base / "cache", base / "logs"]
        return tuple(p for p in candidates if p.exists())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if not safe_rm_contents(p):
                ok = False
        return ("OK", "Zoom cache очищен") if ok else ("ERR", "Ошибка")


class YaMusicCacheCleaner(BaseCleaner):
    id = "yamusic"
    name = "🎵 Яндекс Музыка Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Yandex\\YandexMusic\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш музыки; треки скачаются заново."
    loss = "Офлайн-кэш пропадёт; плейлисты и аккаунт сохранятся."

    def affected_paths(self) -> tuple[Path, ...]:
        p = LOCAL / "Yandex" / "YandexMusic" / "Cache"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Яндекс Музыка cache очищен") if ok else ("ERR", "Ошибка")


class SteamCacheCleaner(BaseCleaner):
    id = "steam"
    name = "🎮 Steam HTML Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Steam\\htmlcache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "HTML-кэш клиента Steam; не связан с файлами игр."
    loss = "Магазин и библиотека загрузятся чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        p = LOCAL / "Steam" / "htmlcache"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Steam cache очищен") if ok else ("ERR", "Ошибка")


class SteamDepotCacheCleaner(BaseCleaner):
    id = "steam_depot"
    name = "🎮 Steam Depot Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Steam\\depotcache"
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    delete_mode = "remove"
    recommended = False
    why = "Манифесты установленных игр; Steam может проверить файлы заново."
    loss = "Проверка игр станет дольше; сами игры не удаляются."
    restore_hint = "Steam восстановит манифесты при следующем запуске."

    def affected_paths(self) -> tuple[Path, ...]:
        p = LOCAL / "Steam" / "depotcache"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Steam depot cache очищен") if ok else ("ERR", "Ошибка")


class ObsidianCacheCleaner(BaseCleaner):
    id = "obsidian"
    name = "📝 Obsidian Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Obsidian\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш Obsidian; заметки и настройки хранятся отдельно."
    loss = "Заметки откроются чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        p = ROAMING / "Obsidian" / "Cache"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Obsidian cache очищен") if ok else ("ERR", "Ошибка")


class EpicGamesCacheCleaner(BaseCleaner):
    id = "epic"
    name = "🎮 Epic Games Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\EpicGamesLauncher\\Saved\\WebCache*"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Web-кэш лаунчера Epic Games; игры и вход не затрагиваются."
    loss = "Магазин Epic загрузится чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        base = LOCAL / "EpicGamesLauncher" / "Saved"
        if not base.exists():
            return ()
        return tuple(p for p in base.iterdir() if p.is_dir() and
                     p.name.lower().startswith("webcache"))

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Epic Games cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Epic Games Launcher"
        )


class AdobeCacheCleaner(BaseCleaner):
    id = "adobe"
    name = "🎨 Adobe Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Adobe\\Common\\Media Cache Files"
    safety = SafetyLevel.CAUTION
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш медиа Premiere/Media Encoder; пересоздаётся при открытии проектов."
    loss = "Открытие проектов с видео станет дольше (рендер превью заново)."
    restore_hint = "Adobe пересоздаст кэш автоматически."

    def affected_paths(self) -> tuple[Path, ...]:
        p = LOCAL / "Adobe" / "Common" / "Media Cache Files"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Adobe media cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте приложения Adobe"
        )


class JavaCacheCleaner(BaseCleaner):
    id = "java_cache"
    name = "☕ Java Deployment Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\..\\LocalLow\\Sun\\Java\\Deployment\\cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш Java-аплетов и Web Start; пересоздаётся при необходимости."
    loss = "Первый запуск Java-приложений будет чуть дольше."

    def affected_paths(self) -> tuple[Path, ...]:
        p = (
            Path.home() / "AppData" / "LocalLow" / "Sun" / "Java" / "Deployment" / "cache"
        )
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Java cache очищен") if ok else ("ERR", "Ошибка")


class WSLVhdxInfoCleaner(BaseCleaner):
    """Обнаружение vhdx-дисков WSL: только подсказка, файлы не удаляются."""

    id = "wsl_vhdx"
    name = "🐧 WSL: виртуальные диски (vhdx)"
    group = GROUP_APPS
    description = (
        "Обнаружение ext4.vhdx дистрибутивов WSL2. "
        "Файлы не удаляются — только подсказка по сжатию."
    )
    safety = SafetyLevel.ADVANCED
    layer = LAYER_COMPONENTS
    recommended = False
    delete_mode = "remove"
    why = (
        "vhdx WSL2 растёт, но не сжимается сам. Освободить место можно командой "
        "wsl --shutdown + Optimize-VHD (или diskpart compact vdisk)."
    )
    loss = "Ничего не удаляется; цель только показывает размер vhdx."
    restore_hint = "wsl --shutdown; Optimize-VHD -Path <vhdx> -Mode Full"

    def affected_paths(self) -> tuple[Path, ...]:
        base = LOCAL / "Packages"
        if not base.exists():
            return ()
        hits: list[Path] = []
        for distro in base.glob("CanonicalGroupLimited*"):
            p = distro / "LocalState" / "ext4.vhdx"
            if p.is_file():
                hits.append(p)
        return tuple(hits)

    def get_size(self) -> int:
        return sum(p.stat().st_size for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        return (
            "SKIP",
            "WSL vhdx не удаляется: wsl --shutdown, затем Optimize-VHD "
            "(см. подсказку восстановления).",
        )


class BattleNetCacheCleaner(BaseCleaner):
    """Кэш лаунчера Battle.net (квоты, агент, куки) — не файлы игр."""

    id = "battle_net"
    name = "🎮 Battle.net Cache"
    group = GROUP_APPS
    description = "%ProgramData%\\Battle.net\\Agent\\BlizzCache и кэши лаунчера"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш лаунчера Battle.net; игры и вход не затрагиваются."
    loss = "Лаунчер Battle.net загрузится чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        candidates = (
            data / "Battle.net" / "Agent" / "BlizzCache",
            data / "Battle.net" / "Agent" / "blizzard" / "Support",
            data / "Blizzard Entertainment" / "Battle.net" / "Cache",
        )
        return tuple(p for p in candidates if p.is_dir())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Battle.net cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Battle.net"
        )


class GogGalaxyCacheCleaner(BaseCleaner):
    """Web-кэш GOG Galaxy; библиотека игр хранится отдельно."""

    id = "gog_galaxy"
    name = "🎮 GOG Galaxy Cache"
    group = GROUP_APPS
    description = "%LocalAppData% и %ProgramData%\\GOG.com\\Galaxy\\webcache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Web-кэш и HTML-хранилища GOG Galaxy; игры и вход не затрагиваются."
    loss = "Интерфейс Galaxy загрузится чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        candidates = (
            LOCAL / "GOG.com" / "Galaxy" / "webcache",
            LOCAL / "GOG.com" / "Galaxy" / "webcache.inherited",
            data / "GOG.com" / "Galaxy" / "webcache",
        )
        return tuple(p for p in candidates if p.is_dir())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "GOG Galaxy cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте GOG Galaxy"
        )


APP_CLEANERS = [
    DiscordCacheCleaner,
    TelegramCacheCleaner,
    SlackCacheCleaner,
    TeamsCacheCleaner,
    ZoomCacheCleaner,
    YaMusicCacheCleaner,
    SteamCacheCleaner,
    SteamDepotCacheCleaner,
    ObsidianCacheCleaner,
    EpicGamesCacheCleaner,
    AdobeCacheCleaner,
    JavaCacheCleaner,
    WSLVhdxInfoCleaner,
    BattleNetCacheCleaner,
    GogGalaxyCacheCleaner,
]
