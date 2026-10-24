"""
scanners.py — Smart Scanner: авто-поиск кэша по системе

Ищет папки Cache, cache, Code Cache, temp во всех AppData-директориях.
Не опирается на жёсткий список — находит даже то, чего нет в cleaners.py.
"""

import os
from pathlib import Path
from typing import Callable
from disk_cleaner_app.legacy.core import (
    CleanupItem, SafetyLevel, LOCAL_APP_DATA, ROAMING_APP_DATA, USER,
    get_dir_size, format_bytes, safe_rm_contents, safe_rmtree
)


# ─────────────────────────────────────────────
# Авто-обнаружение кэша
# ─────────────────────────────────────────────

CACHE_NAMES = {"cache", "caches", "cache_v2", "cod cache", "gpu_cache"}
CODE_CACHE_NAMES = {"code cache", "v8 code cache"}
TEMP_NAMES = {"temp", "tmp"}
COMMON_CACHE_SUFFIXES = {""}  # empty = folder itself is named Cache


def discover_cache_folders(root: Path, max_depth: int = 3, min_size_mb: int = 1) -> list[dict]:
    """
    Сканирует root в поисках папок с именами Cache/cache/Code Cache/temp.
    Возвращает список словарей: {name, path, size, type}.
    """
    found = []
    root_str = root.as_posix().lower()

    try:
        # Сканируем верхний уровень — папки приложений
        for entry in os.scandir(root):
            if not entry.is_dir():
                continue
            app_name = entry.name
            app_path = Path(entry.path)

            # Сканируем внутри приложения на глубину max_depth
            _scan_app_folder(app_path, app_name, found, max_depth, 0)

    except (PermissionError, OSError):
        pass

    return found


def _scan_app_folder(folder: Path, app_name: str, found: list, max_depth: int, depth: int):
    """Рекурсивно ищет кэш-папки внутри папки приложения."""
    if depth > max_depth:
        return
    try:
        folder_lower = folder.name.lower()
        parent_lower = folder.parent.name.lower() if folder.parent else ""

        # Проверяем, является ли эта папка кэшем
        is_cache = folder_lower in CACHE_NAMES
        is_code_cache = folder_lower in CODE_CACHE_NAMES
        is_temp = folder_lower in TEMP_NAMES

        if is_cache or is_code_cache or is_temp:
            # Определяем имя приложения-родителя
            app = parent_lower if parent_lower and parent_lower not in CACHE_NAMES | CODE_CACHE_NAMES | TEMP_NAMES else app_name
            size = get_dir_size(folder)

            if size > 1024 * 1024:  # > 1 МБ
                cache_type = "cache" if is_cache else ("code_cache" if is_code_cache else "temp")
                found.append({
                    "app": app,
                    "name": folder.name,
                    "path": folder,
                    "size": size,
                    "type": cache_type,
                })
            return  # Не идём глубже в кэш

        # Иначе рекурсивно обходим
        if depth < max_depth:
            for entry in os.scandir(folder):
                if entry.is_dir():
                    _scan_app_folder(Path(entry.path), app_name, found, max_depth, depth + 1)

    except (PermissionError, OSError):
        pass


def auto_discover_items() -> list[CleanupItem]:
    """
    Главная функция: запускает авто-сканирование и возвращает список CleanupItem
    для найденных кэшей.
    """
    discovered = []

    # Сканируем LOCALAPPDATA
    local_caches = discover_cache_folders(LOCAL_APP_DATA, max_depth=4)
    discovered.extend(local_caches)

    # Сканируем ROAMINGAPPDATA
    roaming_caches = discover_cache_folders(ROAMING_APP_DATA, max_depth=3)
    discovered.extend(roaming_caches)

    # Создаём CleanupItem для каждого найденного
    items = []
    seen_paths = set()

    for dc in discovered:
        path_str = str(dc["path"]).lower()
        if path_str in seen_paths:
            continue
        seen_paths.add(path_str)

        app_clean = "".join(c for c in dc["app"] if c.isalnum() or c in " _-").strip()
        item_id = f"auto_{app_clean}_{dc['name']}_{len(items)}"
        item_id = "".join(c for c in item_id if c.isalnum() or c in "_-")

        path = dc["path"]
        size = dc["size"]

        def make_size_fn(p: Path) -> Callable:
            return lambda: get_dir_size(p)

        def make_clean_fn(p: Path) -> Callable:
            def clean():
                ok = safe_rm_contents(p)
                return ("OK", f"Кэш {p.name} очищен") if ok else ("ERR", f"Не удалось очистить {p.name}")
            return clean

        items.append(CleanupItem(
            id=item_id,
            name=f"📦 {app_clean} ({dc['name']})",
            group=f"🤖 Авто-найденные",
            description=f"{dc['path']} ({dc['type']})",
            safety=SafetyLevel.SAFE,
            get_size=make_size_fn(path),
            clean=make_clean_fn(path),
            size=size,
            scanned=True,
        ))

    return items


# ─────────────────────────────────────────────
# Предпросмотр файлов кэша
# ─────────────────────────────────────────────

def preview_cache_files(path: Path, max_files: int = 50) -> list[dict]:
    """Возвращает список файлов в папке кэша для предпросмотра."""
    files = []
    try:
        for i, entry in enumerate(os.scandir(path)):
            if i >= max_files:
                files.append({"name": "...", "size": 0, "is_dir": True})
                break
            try:
                files.append({
                    "name": entry.name,
                    "size": entry.stat().st_size if entry.is_file() else 0,
                    "is_dir": entry.is_dir(),
                })
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return files
