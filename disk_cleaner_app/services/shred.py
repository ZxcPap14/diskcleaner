"""Безвозвратное стирание: перезапись содержимого перед удалением.

Обычное удаление оставляет данные на диске до перезаписи сектора. Здесь
файл сначала заполняется нулями (``passes`` раз), затем удаляется — тот же
подход, что у BleachBit и Wise. Работает только с файлами и настоящими
папками: символические ссылки и reparse-точки пропускаются, чтобы не
стереть содержимое за пределами выбранного пути.

Один проход и нули — сознательный выбор: на SSD и в журналируемых ФС
многократная перезапись ничего не даёт, а время растёт линейно.
"""
from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

log = logging.getLogger(__name__)

# Пишем мегабайт за раз: памяти на файл не тратим, I/O не мельчим.
BLOCK = 1024 * 1024


def _clear_readonly(path: str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _overwrite(path: str, passes: int) -> None:
    """Записать нули поверх содержимого файла."""
    size = os.path.getsize(path)
    with open(path, "r+b", buffering=0) as handle:
        for _ in range(max(1, passes)):
            handle.seek(0)
            left = size
            while left > 0:
                chunk = min(BLOCK, left)
                handle.write(b"\0" * chunk)
                left -= chunk
            handle.flush()
            os.fsync(handle.fileno())


def _is_link(path: str) -> bool:
    """Ссылка или reparse-точка — её содержимое нам не принадлежит."""
    try:
        info = os.lstat(path)
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def shred_file(path: str | Path, passes: int = 1) -> bool:
    """Перезаписать и удалить один файл. False — не получилось."""
    target = str(path)
    try:
        if _is_link(target) or os.path.isdir(target):
            return False
        _clear_readonly(target)
        _overwrite(target, passes)
        os.remove(target)
        return True
    except OSError as exc:
        log.info("Стирание %s не удалось: %s", target, exc)
        return False


def _shred_tree(root: str, passes: int) -> bool:
    """Стереть папку: сначала файлы, потом сами папки снизу вверх."""
    ok = True
    dirs: list[str] = []
    for current, subdirs, files in os.walk(root, topdown=True):
        # Внутрь ссылок не заходим: там чужие данные.
        subdirs[:] = [d for d in subdirs
                      if not _is_link(os.path.join(current, d))]
        dirs.append(current)
        for name in files:
            if not shred_file(os.path.join(current, name), passes):
                ok = False
    for current in reversed(dirs):
        try:
            os.rmdir(current)
        except OSError as exc:
            log.info("Папка %s не удалена: %s", current, exc)
            ok = False
    return ok


def shred_many(paths: list[str], passes: int = 1) -> dict:
    """Стереть список путей. Формат ответа — как у ``batch_delete.delete_many``."""
    result: dict = {"deleted": [], "failed": [], "aborted": False,
                    "error": 0, "fallback": True}
    for raw in paths:
        target = str(raw)
        if not os.path.lexists(target):
            result["failed"].append(target)
            continue
        done = (_shred_tree(target, passes) if os.path.isdir(target) and not _is_link(target)
                else shred_file(target, passes))
        result["deleted" if done else "failed"].append(target)
    return result
