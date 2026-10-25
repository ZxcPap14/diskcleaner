"""Классификация причин ошибок удаления (errno/winerror → понятный род).

Разбор кодов собран в одном модуле: движок передаёт сюда срез неудачных
путей, а UI получает агрегат «занято 9, отказ 3» и подсказку, что делать
(закрыть приложение, взять права, снять «только чтение»).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import errno as _errno
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

# Устойчивые роды причин ошибки удаления.
NOT_FOUND = "not_found"
LOCKED = "locked"
ACCESS_DENIED = "access_denied"
IN_USE = "in_use"
READONLY = "readonly"
PATH_TOO_LONG = "path_too_long"
CLOUD_PLACEHOLDER = "cloud_placeholder"
UNKNOWN = "unknown"

KINDS = (
    NOT_FOUND, LOCKED, ACCESS_DENIED, IN_USE,
    READONLY, PATH_TOO_LONG, CLOUD_PLACEHOLDER, UNKNOWN,
)

# Человекочитаемые названия и действия, которые помогут пользователю.
KIND_TITLES = {
    NOT_FOUND: "файл уже исчез",
    LOCKED: "занято другим процессом",
    ACCESS_DENIED: "отказ в доступе",
    IN_USE: "используется системой",
    READONLY: "атрибут «только чтение»",
    PATH_TOO_LONG: "слишком длинный путь",
    CLOUD_PLACEHOLDER: "файл облака (загрузка по требованию)",
    UNKNOWN: "причина неясна",
}

KIND_HINTS = {
    LOCKED: "закройте приложения и повторите очистку",
    IN_USE: "завершите работу программы (или перезапустите ПК) и повторите",
    ACCESS_DENIED: "запустите очистку с правами администратора",
    READONLY: "снимите атрибут «только чтение» и повторите",
    PATH_TOO_LONG: "переместите данные в папку ближе к корню диска",
    CLOUD_PLACEHOLDER: "файлы OneDrive чистьте средствами самой Windows/OneDrive",
}

# ── таблицы кодов ─────────────────────────────────────

ERROR_KIND_WINERROR = {
    2: NOT_FOUND,          # ERROR_FILE_NOT_FOUND
    3: NOT_FOUND,          # ERROR_PATH_NOT_FOUND
    5: ACCESS_DENIED,      # ERROR_ACCESS_DENIED
    32: LOCKED,            # ERROR_SHARING_VIOLATION
    33: LOCKED,            # ERROR_LOCK_VIOLATION
    206: PATH_TOO_LONG,    # ERROR_FILENAME_EXCED_RANGE
}

_ERROR_KIND_ERRNO_TABLE = {
    _errno.EACCES: ACCESS_DENIED,
    _errno.EPERM: ACCESS_DENIED,
    _errno.ENOENT: NOT_FOUND,
    _errno.EBUSY: IN_USE,
    _errno.EAGAIN: LOCKED,
    _errno.EWOULDBLOCK: LOCKED,
    _errno.ENAMETOOLONG: PATH_TOO_LONG,
    206: PATH_TOO_LONG,    # error 206 как исключение без winerror
}


def classify_error(error: OSError) -> str:
    """Род причины по коду исключения (для fallback-удаления)."""
    winerror = getattr(error, "winerror", None)
    if isinstance(winerror, int) and winerror in ERROR_KIND_WINERROR:
        return ERROR_KIND_WINERROR[winerror]
    if error.errno is not None and error.errno in _ERROR_KIND_ERRNO_TABLE:
        return _ERROR_KIND_ERRNO_TABLE[error.errno]
    return UNKNOWN


# ── диагностика по факту (WinAPI, работает и с папками) ──

_INVALID_FILE_ATTRS = 0xFFFFFFFF          # GetFileAttributesW вернёт это при ошибке
_FILE_ATTR_READONLY = 0x00000001
# OneDrive и другие поставщики облака: выгрузка/загрузка по требованию.
# RECALL_ON_OPEN | OFFLINE | UNPINNED | RECALL_ON_DATA_ACCESS
_FILE_ATTR_CLOUD_MASK = 0x00040000 | 0x00001000 | 0x00100000 | 0x00400000

_GENERIC_READ = 0x80000000
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # нужен и для открытия папок


def _get_attributes(path: str) -> int:
    """Атрибуты файла/папки; -1 при недоступности (не-Windows, ошибка)."""
    try:
        kernel = ctypes.windll.kernel32
    except AttributeError:               # не Windows
        return -1
    try:
        attrs = kernel.GetFileAttributesW(str(path))
    except OSError:
        return -1
    if attrs == _INVALID_FILE_ATTRS:
        return -1
    return int(attrs)


def _open_exclusive_error_code(path: str) -> int:
    """Попытка открыть объект без шаринга. Возвращает код ошибки или 0.

    Блокировка (sharing violation) → 32; отказ в доступе → 5;
    открыт успешно → 0. Папка открывается с BACKUP_SEMANTICS.
    """
    try:
        kernel = ctypes.windll.kernel32
    except AttributeError:
        return 0
    _CreateFileW = kernel.CreateFileW
    _CreateFileW.restype = wintypes.HANDLE
    _CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    handle = _CreateFileW(
        str(path), _GENERIC_READ, 0, None, _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS, None,
    )
    invalid = wintypes.HANDLE(-1).value
    if handle == invalid:
        return ctypes.GetLastError()
    if handle:
        kernel.CloseHandle(handle)
    return 0


def classify_path(path: str | Path) -> str:
    """Род причины по состоянию пути на диске."""
    raw = os.path.abspath(str(path))
    if len(raw) > 260:
        # Длинный путь может сам ломать lexists — проверяем длину раньше.
        return PATH_TOO_LONG
    if not os.path.lexists(raw):
        return NOT_FOUND

    attrs = _get_attributes(raw)
    if attrs > 0:
        if attrs & _FILE_ATTR_CLOUD_MASK:
            return CLOUD_PLACEHOLDER
        if attrs & _FILE_ATTR_READONLY:
            return READONLY

    code = _open_exclusive_error_code(raw)
    if code:
        return ERROR_KIND_WINERROR.get(code, UNKNOWN)
    return UNKNOWN


def classify_paths(paths: Iterable[str | Path]) -> dict[str, int]:
    """Диагностика списка неудачных путей: счётчик «род → количество».

    Путь, который уже исчез, ошибкой не считается (он удалился).
    """
    summary: dict[str, int] = {}
    for raw in paths:
        kind = classify_path(raw)
        if kind == NOT_FOUND:
            continue
        summary[kind] = summary.get(kind, 0) + 1
    return summary


def summarize_kinds(kinds: Mapping[str, int]) -> str:
    """«занято другим процессом 9, отказ в доступе 3» (по убыванию)."""
    parts = [
        f"{KIND_TITLES.get(kind, kind)} {count}"
        for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1])
        if count > 0
    ]
    return ", ".join(parts)


def remediation(kinds: Mapping[str, int]) -> str:
    """Первая осмысленная подсказка из присутствующих родов."""
    for kind in (LOCKED, IN_USE, ACCESS_DENIED, READONLY,
                 PATH_TOO_LONG, CLOUD_PLACEHOLDER):
        if kinds.get(kind):
            return KIND_HINTS[kind]
    return ""
