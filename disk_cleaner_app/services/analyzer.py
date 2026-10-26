"""DiskAnalyzer — сканирование больших папок, файлов, пустых папок."""
from __future__ import annotations

import heapq
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from disk_cleaner_app.cleaners.base import get_dir_size, scan_cancelled

# Каталоги, которые не дают полезной картины «что занимает место»:
# корзина и системные служебные области.
SKIP_DIRS = {"$recycle.bin", "system volume information"}


def _cancelled(cancel: threading.Event | None) -> bool:
    return scan_cancelled() or bool(cancel is not None and cancel.is_set())


def _prune(dirnames: list[str]) -> None:
    dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]



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


def _analysis_roots(root: str) -> list[str]:
    """Где искать файлы: диск, домашняя папка, ProgramData и TEMP без дублей."""
    return _dedupe_roots([
        root,
        str(Path.home()),
        os.environ.get("ProgramData", "C:\\ProgramData"),
        os.environ.get("TEMP", ""),
    ])


def scan_large_files(
    root: str = "C:\\",
    min_size_mb: int = 500,
    limit: int = 100,
    cancel: threading.Event | None = None,
) -> list[dict]:
    """Найти файлы >= min_size_mb в ключевых папках."""
    min_bytes = min_size_mb * 1024 * 1024
    results: list[dict] = []

    scan_dirs = _analysis_roots(root)

    for sd in scan_dirs:
        if _cancelled(cancel):
            break
        if not sd or not Path(sd).exists():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(sd):
                if _cancelled(cancel):
                    break
                _prune(dirnames)
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


@dataclass(frozen=True)
class ExtensionStat:
    """Сколько занимает одно расширение во всём скане."""

    extension: str
    size: int
    count: int


@dataclass(frozen=True)
class FileScan:
    """Результат обхода: крупнейшие файлы и итоги по расширениям.

    ``files`` ограничен ``limit`` (по умолчанию 5000 крупнейших), а
    ``extensions``/``total_*`` считаются по всем файлам >= порога.
    """

    files: list[dict]
    extensions: list[ExtensionStat]
    total_files: int
    total_bytes: int
    truncated: bool


def file_extension(name: str) -> str:
    """Расширение без точки в нижнем регистре ('' — без расширения)."""
    ext = os.path.splitext(name)[1].lower()
    return ext[1:] if ext.startswith(".") else ext


def extension_label(extension: str) -> str:
    return f".{extension}" if extension else "без расширения"


def scan_files(
    root: str = "C:\\",
    min_size_mb: int = 10,
    limit: int = 5000,
    cancel: threading.Event | None = None,
) -> FileScan:
    """Один обход: топ файлов по размеру и суммарные размеры расширений."""
    min_bytes = min_size_mb * 1024 * 1024
    heap: list[tuple[int, str, float, str]] = []
    ext_sizes: dict[str, int] = {}
    ext_counts: dict[str, int] = {}
    total_files = 0
    total_bytes = 0

    for sd in _analysis_roots(root):
        if _cancelled(cancel):
            break
        if not sd or not Path(sd).exists():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(sd):
                if _cancelled(cancel):
                    break
                _prune(dirnames)
                if dirpath.lower().endswith("\\windows"):
                    dirnames[:] = [d for d in dirnames if d.lower() == "temp"]
                for fn in filenames:
                    try:
                        fp = os.path.join(dirpath, fn)
                        st = os.stat(fp)
                    except (OSError, PermissionError):
                        continue
                    size = st.st_size
                    if size < min_bytes:
                        continue
                    total_files += 1
                    total_bytes += size
                    ext = file_extension(fn)
                    ext_sizes[ext] = ext_sizes.get(ext, 0) + size
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
                    if len(heap) < limit:
                        heapq.heappush(heap, (size, fp, st.st_mtime, ext))
                    elif size > heap[0][0]:
                        heapq.heapreplace(heap, (size, fp, st.st_mtime, ext))
        except (OSError, PermissionError):
            continue

    files = [
        {
            "name": os.path.basename(fp),
            "path": fp,
            "size": size,
            "modified": modified,
            "extension": ext,
        }
        for size, fp, modified, ext in sorted(heap, reverse=True)
    ]
    extensions = [
        ExtensionStat(ext, size, ext_counts[ext])
        for ext, size in sorted(ext_sizes.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return FileScan(
        files=files,
        extensions=extensions,
        total_files=total_files,
        total_bytes=total_bytes,
        truncated=total_files > limit,
    )


def filter_files(
    files: list[dict],
    extension: str = "",
    min_size_mb: int = 0,
    min_age_days: int = 0,
    now: float | None = None,
) -> list[dict]:
    """Отфильтровать уже собранный список без повторного обхода диска.

    ``extension="."`` — только файлы без расширения (пустая строка
    означает «любое расширение»).
    """
    now_ts = time.time() if now is None else now
    min_bytes = min_size_mb * 1024 * 1024
    result: list[dict] = []
    for f in files:
        if extension:
            name_ext = f.get("extension") or file_extension(f.get("name", ""))
            if extension == ".":
                if name_ext:
                    continue
            elif name_ext.lower() != extension.lower():
                continue
        if int(f.get("size", 0)) < min_bytes:
            continue
        if min_age_days > 0:
            modified = float(f.get("modified", 0) or 0)
            if now_ts - modified < min_age_days * 86400:
                continue
        result.append(f)
    return result


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
