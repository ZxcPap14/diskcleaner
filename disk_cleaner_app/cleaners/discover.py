"""🧠 Auto-discover: сканирование AppData на наличие кэш-папок.

Кэширует результаты на 5 минут для ускорения повторных вызовов.
Пути, которые уже покрыты встроенными очистителями, исключаются,
чтобы не считать и не удалять одни и те же файлы дважды.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any

from disk_cleaner_app.cleaners.base import BaseCleaner, get_dir_size, safe_rm_contents
from disk_cleaner_app.models.item import GROUP_AUTO, SafetyLevel
from disk_cleaner_app.models.target import LAYER_SAFE

log = logging.getLogger(__name__)

LOCAL = Path.home() / "AppData" / "Local"
ROAMING = Path.home() / "AppData" / "Roaming"

CACHE_NAMES = {"cache", "caches", "cache_v2", "cod cache", "gpu_cache"}
CODE_CACHE_NAMES = {"code cache", "v8 code cache"}
TEMP_NAMES = {"temp", "tmp"}

_cache: list[BaseCleaner] | None = None
_cache_time: float = 0
_CACHE_TTL: float = 300  # 5 минут

# Широкие корни браузеров: профили перечисляются динамически, и новый
# профиль должен оставаться покрытым, даже если его не было при старте.
_BROAD_BROWSER_ROOTS = (
    LOCAL / "Google" / "Chrome" / "User Data",
    LOCAL / "Microsoft" / "Edge" / "User Data",
    LOCAL / "Yandex" / "YandexBrowser" / "User Data",
    LOCAL / "BraveSoftware" / "Brave-Browser" / "User Data",
    LOCAL / "Vivaldi" / "User Data",
    LOCAL / "Opera Software" / "Opera Stable",
    LOCAL / "Mozilla" / "Firefox" / "Profiles",
    ROAMING / "Mozilla" / "Firefox" / "Profiles",
)

# Резерв, если список встроенных целей недоступен: прежнее поведение.
_FALLBACK_ROOTS = (
    LOCAL / "Temp",
    *_BROAD_BROWSER_ROOTS,
    LOCAL / "Discord",
    LOCAL / "Steam",
    LOCAL / "Yandex" / "YandexMusic",
    ROAMING / "Slack",
    ROAMING / "Microsoft" / "Teams",
    ROAMING / "Zoom",
    ROAMING / "Obsidian",
    ROAMING / "Telegram Desktop",
    LOCAL / "D3DSCache",
    LOCAL / "NVIDIA",
    LOCAL / "AMD",
    LOCAL / "Intel" / "ShaderCache",
    LOCAL / "pip",
    LOCAL / "Yarn",
    LOCAL / "uv",
    LOCAL / "bun",
    LOCAL / "gradle",
    LOCAL / "rustup",
)

_covered_cache: tuple[Path, ...] | None = None


def _norm(path: Path) -> Path:
    return Path(os.path.normcase(str(path)))


def _builtin_affected_paths() -> list[Path]:
    """Файловые пути всех встроенных очистителей (источник истины).

    Импорт ленивый и без registry: registry импортирует discover, обратное
    направление цикл бы создало. Списки содержат классы — инстанцируем.
    """
    from disk_cleaner_app.cleaners.aiml import AIML_CLEANERS
    from disk_cleaner_app.cleaners.apps import APP_CLEANERS
    from disk_cleaner_app.cleaners.browsers import BROWSER_CLEANERS
    from disk_cleaner_app.cleaners.devtools import DEVTOOLS_CLEANERS
    from disk_cleaner_app.cleaners.system import SYSTEM_CLEANERS
    from disk_cleaner_app.cleaners.uwp import UWP_CLEANERS

    # Списки разнородные, mypy видит часть элементов абстрактными;
    # корректность инстанцирования проверяют тесты реестра и sync-тест.
    classes: tuple[Any, ...] = (
        *SYSTEM_CLEANERS, *UWP_CLEANERS, *APP_CLEANERS, *DEVTOOLS_CLEANERS,
        *BROWSER_CLEANERS, *AIML_CLEANERS,
    )
    roots: list[Path] = []
    for cleaner_class in classes:
        try:
            roots.extend(cleaner_class().affected_paths())
        except Exception:
            log.debug(
                "affected_paths не удался для %s",
                getattr(cleaner_class, "id", cleaner_class),
                exc_info=True,
            )

    # Декларативные JSON-цели тоже сужают область discover — иначе
    # он найдёт их же кэши второй раз.
    try:
        from disk_cleaner_app.services.json_targets import load_json_targets

        for cleaner in load_json_targets():
            roots.extend(cleaner.affected_paths())
    except Exception:
        log.debug("JSON-цели не вошли в covered-корни", exc_info=True)
    return roots


def covered_cache_roots() -> tuple[Path, ...]:
    """Каталоги, которые уже обслуживаются встроенными очистителями.

    Собирается из ``affected_paths()`` реальных целей, поэтому новый
    очиститель автоматически сужает область auto-discover. Раньше список
    дублировался вручную и разъезжался: корни «NVIDIA»/«AMD»/«pip» были
    шире фактических целей, и discover молча пропускал NV_Cache,
    ComputeCache и им подобные.
    """
    global _covered_cache
    if _covered_cache is not None:
        return _covered_cache

    roots: list[Path] = [LOCAL / "Temp", *_BROAD_BROWSER_ROOTS]
    try:
        roots.extend(_builtin_affected_paths())
    except Exception:
        log.warning("Не удалось получить пути встроенных целей", exc_info=True)
        roots = list(_FALLBACK_ROOTS)

    _covered_cache = tuple(_norm(p) for p in roots if str(p).strip())
    return _covered_cache


def reset_covered_cache() -> None:
    """Сбросить кэш covered-корней (после установки новых целей)."""
    global _covered_cache
    _covered_cache = None


def is_covered(path: Path) -> bool:
    """Покрыт ли путь встроенным очистителем (или находится внутри него)."""
    p = _norm(path)
    for root in covered_cache_roots():
        if p == root or root in p.parents:
            return True
    return False


class AutoDiscoveredCleaner(BaseCleaner):
    """Очиститель, созданный динамически для найденной кэш-папки."""

    def __init__(self, folder_path: Path, app_name: str) -> None:
        super().__init__()
        self._folder = folder_path
        # Хэш пути в id: иначе Local/Foo/Cache и Roaming/Foo/Cache
        # получают одинаковый id, и сканер молча выбрасывает вторую цель.
        path_digest = hashlib.blake2b(
            str(folder_path).encode("utf-8", errors="replace"), digest_size=4
        ).hexdigest()
        self.id = (
            f"auto_{app_name}_{folder_path.name}_{path_digest}".replace(" ", "_").lower()
        )
        self.name = f"🧠 {app_name} — {folder_path.name}"
        self.group = GROUP_AUTO
        self.description = str(folder_path)
        self.safety = SafetyLevel.CAUTION
        self.layer = LAYER_SAFE
        self.recommended = False
        self.delete_mode = "contents"
        self.can_preview = True
        self.preview_path = str(folder_path)
        self.why = "Найдена папка с именем кэша; очищаем содержимое, папку оставляем."
        self.loss = "Приложение может загрузить данные заново; папка останется на месте."

    def affected_paths(self) -> tuple[Path, ...]:
        return (self._folder,)

    def get_size(self) -> int:
        return get_dir_size(self._folder)

    def clean(self) -> tuple[str, str]:
        ok = safe_rm_contents(self._folder)
        name = self._folder.name
        return ("OK", f"Кэш {name} очищен") if ok else ("ERR", f"Не удалось очистить {name}")


def discover_cache_folders(
    root: Path,
    max_depth: int = 3,
    min_size_mb: int = 1,
    cancel_event=None,
) -> list[dict]:
    """Найти папки кэша в root. max_depth ограничивает глубину."""
    found: list[dict] = []

    def stopped() -> bool:
        return bool(cancel_event is not None and cancel_event.is_set())

    def scan(folder: Path, path_parts: list[str], depth: int = 0) -> None:
        if depth > max_depth or stopped():
            return
        try:
            for entry in folder.iterdir():
                if stopped():
                    return
                if not entry.is_dir() or entry.is_symlink():
                    continue
                name_lower = entry.name.lower()
                # Пропускаем системные и уже покрытые встроенными очистителями.
                if entry.name.startswith("$") or is_covered(entry):
                    continue

                # Определяем имя приложения: берём имя папки на глубине 0-2
                # Local/Google/Chrome → "Chrome"
                parts = path_parts + [entry.name]

                if name_lower in CACHE_NAMES or name_lower in CODE_CACHE_NAMES or name_lower in TEMP_NAMES:
                    sz = get_dir_size(entry) // (1024 * 1024)
                    if sz >= min_size_mb:
                        # App name = предпоследняя папка (или последняя, если кэш на верхнем уровне)
                        app_name = parts[-2] if len(parts) >= 2 else parts[-1]
                        found.append({
                            "path": entry,
                            "app": app_name,
                            "size_mb": sz,
                            "type": "cache" if name_lower in CACHE_NAMES
                                    else "code_cache" if name_lower in CODE_CACHE_NAMES
                                    else "temp",
                        })
                else:
                    scan(entry, parts, depth + 1)
        except (PermissionError, OSError):
            pass

    scan(root, [root.name])
    return found


def auto_discover_items(cancel_event=None) -> list[BaseCleaner]:
    """Главная функция: найти все кэши в AppData.

    Результат кэшируется на 5 минут. При отмене кэш не обновляется.
    """
    global _cache, _cache_time
    if cancel_event is not None and cancel_event.is_set():
        return []
    now = time.time()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache

    cleaners: list[BaseCleaner] = []
    seen: set[str] = set()

    for base_path, _label, depth in [
        (LOCAL, "Local", 4),
        (ROAMING, "Roaming", 3),
    ]:
        if cancel_event is not None and cancel_event.is_set():
            return cleaners
        if not base_path.exists():
            continue
        folders = discover_cache_folders(
            base_path,
            max_depth=depth,
            min_size_mb=1,
            cancel_event=cancel_event,
        )
        for f in folders:
            path_str = os.path.normcase(str(f["path"]))
            if path_str in seen:
                continue
            seen.add(path_str)
            cleaners.append(AutoDiscoveredCleaner(f["path"], f["app"]))

    if cancel_event is not None and cancel_event.is_set():
        return cleaners

    _cache = cleaners
    _cache_time = now
    return cleaners


def clear_cache() -> None:
    """Сбросить кэш (например, после добавления custom rule)."""
    global _cache, _cache_time
    _cache = None
    _cache_time = 0
    reset_covered_cache()
