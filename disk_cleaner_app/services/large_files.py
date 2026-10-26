"""Слой E: крупные файлы — только инвентаризация, без удаления.

Сканируем выбранный диск и держим в памяти только топ-N файлов
(min-heap), поэтому даже на переполненном диске обход не съедает
гигабайты RAM. Ссылки и junction'ы не разворачиваем.
"""
from __future__ import annotations

import datetime
import heapq
import os
import stat
import subprocess
import threading
from pathlib import Path

from disk_cleaner_app.cleaners.base import scan_cancelled

# Служебные каталоги: файлы в них не пользовательские, а обход дорогой.
SKIP_DIRS = {
    "$recycle.bin",
    "system volume information",
    "winsxs",
    "servicing",
    "recovery",
}

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _cancelled(cancel: threading.Event | None) -> bool:
    return scan_cancelled() or bool(cancel is not None and cancel.is_set())


def _is_link(path: str) -> bool:
    """Симлинк или junction: внутрь не заходим и файлом не считаем."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return stat.S_ISLNK(st.st_mode) or bool(attrs & _REPARSE_POINT)


def scan_large_files(
    root: str = "C:\\",
    min_size_mb: int = 500,
    limit: int = 50,
    cancel: threading.Event | None = None,
) -> list[dict]:
    """Найти крупнейшие файлы на диске.

    Возвращает до ``limit`` записей с полями ``name``, ``path``, ``size``
    и ``modified`` (posix-время), отсортированных по размеру по убыванию.
    """
    limit = max(1, int(limit))
    min_bytes = max(1, int(min_size_mb)) * 1024 * 1024
    root = (root or os.environ.get("SystemDrive", "C:")).rstrip("\\/") + os.sep
    if not os.path.isdir(root):
        return []

    # (size, path, mtime) — при равных размерах сравнение идёт по пути.
    kept: list[tuple[int, str, float]] = []

    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, onerror=lambda _e: None, followlinks=False
    ):
        if _cancelled(cancel):
            break
        dirnames[:] = [
            name for name in dirnames
            if name.lower() not in SKIP_DIRS
            and not _is_link(os.path.join(dirpath, name))
        ]
        for name in filenames:
            if _cancelled(cancel):
                break
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or st.st_size < min_bytes:
                continue
            if len(kept) < limit:
                heapq.heappush(kept, (st.st_size, full, st.st_mtime))
            elif st.st_size > kept[0][0]:
                heapq.heapreplace(kept, (st.st_size, full, st.st_mtime))
        if _cancelled(cancel):
            break

    kept.sort(key=lambda item: item[0], reverse=True)
    return [
        {"name": Path(path).name, "path": path, "size": size, "modified": modified}
        for size, path, modified in kept
    ]


def plural_files(count: int) -> str:
    """Согласовать «файл» с числом: 1 файл, 2 файла, 5 файлов."""
    tail = abs(int(count)) % 100
    if 11 <= tail <= 14:
        return "файлов"
    last = tail % 10
    if last == 1:
        return "файл"
    if 2 <= last <= 4:
        return "файла"
    return "файлов"


def format_age(modified: float, now: datetime.datetime | None = None) -> str:
    """Возраст файла коротко: «сегодня», «5 дн.», «7 мес.», «3 г.»."""
    now = now or datetime.datetime.now()
    try:
        days = int((now.timestamp() - float(modified)) // 86400)
    except (TypeError, ValueError, OSError):
        return "возраст неизвестен"
    days = max(0, days)
    if days == 0:
        return "сегодня"
    if days < 30:
        return f"{days} дн."
    if days < 365:
        return f"{days // 30} мес."
    return f"{days // 365} г."


def format_modified(modified: float) -> str:
    """Дата изменения файла: 12.03.2024."""
    try:
        return datetime.datetime.fromtimestamp(modified).strftime("%d.%m.%Y")
    except (OSError, OverflowError, ValueError):
        return "дата неизвестна"


def reveal_in_explorer(path: str) -> bool:
    """Открыть папку файла с выделением самого файла. Не удаляет ничего."""
    if not path:
        return False
    try:
        subprocess.Popen(
            ["explorer", "/select,", os.path.normpath(path)],
            close_fds=True,
        )
        return True
    except OSError:
        return False
