"""DiskAnalyzer — сканирование больших папок, файлов, пустых папок."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from disk_cleaner_app.cleaners.base import get_dir_size, scan_cancelled


def _cancelled(cancel: threading.Event | None) -> bool:
    return scan_cancelled() or bool(cancel is not None and cancel.is_set())


def normalize_root(root: str | None = None) -> str:
    """Корень диска с завершающим обратным слэшем.

    Пустое значение означает системный диск. ``D:`` → ``D:\\``.
    """
    value = (root or "").strip()
    if not value:
        value = os.environ.get("SystemDrive", "C:")
    if not value.endswith("\\"):
        value += "\\"
    return value


def empty_scan_root(root: str | None = None) -> str:
    """Где искать пустые папки: ``<диск>\\Users``, если он есть, иначе корень."""
    base = normalize_root(root)
    users = os.path.join(base, "Users")
    return users if os.path.isdir(users) else base


def scan_top_folders(
    root: str = "C:\\",
    limit: int = 50,
    cancel: threading.Event | None = None,
) -> list[dict]:
    """Вернуть top-limit папок в root по размеру."""
    folders: list[dict] = []
    try:
        with os.scandir(root) as it:
            for e in it:
                if _cancelled(cancel):
                    break
                try:
                    if e.is_dir(follow_symlinks=False):
                        sz = get_dir_size(Path(e.path))
                        if sz > 0:
                            folders.append({"name": e.name, "path": e.path, "size": sz})
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    folders.sort(key=lambda x: x["size"], reverse=True)
    return folders[:limit]


def _dedupe_roots(roots: list[str]) -> list[str]:
    """Убрать корни, вложенные в другие корни.

    Иначе один и тот же файл попадает в результаты дважды
    (например, домашняя папка при сканировании всего ``C:\\``).
    """
    unique: list[str] = []
    seen: set[str] = set()
    for raw in roots:
        if not raw:
            continue
        key = os.path.normcase(os.path.abspath(raw))
        if key in seen:
            continue
        seen.add(key)
        unique.append(raw)

    # Сначала короткие (родительские) корни, чтобы вложенные отбрасывались.
    unique.sort(key=lambda r: len(os.path.normcase(os.path.abspath(r))))
    kept: list[str] = []
    kept_keys: list[str] = []
    for raw in unique:
        key = os.path.normcase(os.path.abspath(raw)).rstrip("\\") + "\\"
        if any(key.startswith(other) for other in kept_keys):
            continue
        kept.append(raw)
        kept_keys.append(key)
    return kept


def scan_large_files(
    root: str = "C:\\",
    min_size_mb: int = 500,
    limit: int = 100,
    cancel: threading.Event | None = None,
) -> list[dict]:
    """Найти файлы >= min_size_mb в ключевых папках."""
    min_bytes = min_size_mb * 1024 * 1024
    results: list[dict] = []

    scan_dirs = _dedupe_roots([
        root,
        str(Path.home()),
        os.environ.get("ProgramData", "C:\\ProgramData"),
        os.environ.get("TEMP", ""),
    ])

    for sd in scan_dirs:
        if _cancelled(cancel):
            break
        if not sd or not Path(sd).exists():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(sd):
                if _cancelled(cancel):
                    break
                # В C:\Windows не заходим глубже Temp (там бывают большие
                # файлы установщиков); это же экономит обход диска.
                if dirpath.lower().endswith("\\windows"):
                    dirnames[:] = [d for d in dirnames if d.lower() == "temp"]
                for fn in filenames:
                    try:
                        fp = os.path.join(dirpath, fn)
                        st = os.stat(fp)
                        if st.st_size >= min_bytes:
                            results.append({
                                "name": fn,
                                "path": fp,
                                "size": st.st_size,
                            })
                            if len(results) >= limit:
                                break
                    except (OSError, PermissionError):
                        continue
            if len(results) >= limit:
                break
        except (OSError, PermissionError):
            continue

    results.sort(key=lambda x: x["size"], reverse=True)
    return results[:limit]


def find_empty_folders(
    root: str = "C:\\Users",
    cancel: threading.Event | None = None,
) -> list[str]:
    """Найти все пустые папки (нет файлов и нет подпапок)."""
    empty: list[str] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            if _cancelled(cancel):
                break
            if not dirnames and not filenames:
                empty.append(dirpath)
    except (OSError, PermissionError):
        pass
    return empty


def remove_empty_folders(
    folders: list[str],
    root: str | None = None,
) -> tuple[int, list[str]]:
    """Удалить пустые папки (вложенные сначала). Возвращает (удалено, ошибки).

    ``root`` (если указан) защищает от удаления самого корня сканирования.
    """
    removed = 0
    errors: list[str] = []
    root_key = os.path.normcase(os.path.abspath(root)) if root else None

    for fp in sorted(folders, reverse=True):
        if root_key and os.path.normcase(os.path.abspath(fp)) == root_key:
            errors.append(f"{fp}: корень сканирования не удаляется")
            continue
        if not os.path.isdir(fp):
            continue
        try:
            Path(fp).rmdir()
            removed += 1
        except OSError as e:
            errors.append(f"{fp}: {e}")
    return removed, errors
