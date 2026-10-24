"""Пакетное удаление через оболочку Windows (IFileOperation / SHFileOperationW).

Один вызов API вместо сотни отдельных операций: меньше запросов UAC,
корректная работа с корзиной и длинными путями.
"""
from __future__ import annotations

import ctypes
import logging
import os
import uuid
from ctypes import wintypes
from pathlib import Path

from disk_cleaner_app.cleaners.base import safe_remove

log = logging.getLogger(__name__)

FO_DELETE = 0x0003

FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
FOF_NOCONFIRMMKDIR = 0x0200
FOFX_ADDUNDORECORD = 0x20000000

# COM: IFileOperation (одна операция на весь пакет).
CLSID_FileOperation = uuid.UUID("{3AD05575-8857-4850-9277-11B85BDB8E09}")
IID_IFileOperation = uuid.UUID("{947AAB5F-0A5C-4C13-B4D6-4BF7836FC9F8}")
IID_IShellItem = uuid.UUID("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")
CLSCTX_INPROC_SERVER = 1
COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = 0x80010106


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_uuid(cls, value: uuid.UUID) -> GUID:
        raw = value.bytes_le
        return cls(
            int.from_bytes(raw[0:4], "little"),
            int.from_bytes(raw[4:6], "little"),
            int.from_bytes(raw[6:8], "little"),
            (ctypes.c_ubyte * 8)(*raw[8:]),
        )


def _com_call(ptr, index: int, argtypes: tuple, *args):
    """Вызвать метод COM-объекта по индексу в vtable."""
    vtable = ctypes.cast(
        ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ).contents
    prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return prototype(vtable[index])(ptr, *args)


def _release(ptr) -> None:
    if not ptr:
        return
    try:
        _com_call(ptr, 2, ())
    except Exception:
        pass


def _ifile_delete(paths: list[str], to_recycle: bool) -> bool:
    """Удалить пакет через IFileOperation (True — операция выполнена).

    Возвращает False/бросает исключение, если COM-путь недоступен:
    вызывающий код откатится на SHFileOperationW.
    """
    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    shell32.SHCreateItemFromParsingName.argtypes = [
        wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

    coinit = int(ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
    owns_com = coinit >= 0
    if not owns_com and (coinit & 0xFFFFFFFF) != RPC_E_CHANGED_MODE:
        raise OSError(coinit, "CoInitializeEx")

    operation = ctypes.c_void_p()
    created = False
    try:
        clsid = GUID.from_uuid(CLSID_FileOperation)
        iid = GUID.from_uuid(IID_IFileOperation)
        hr = int(ole32.CoCreateInstance(
            ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER,
            ctypes.byref(iid), ctypes.byref(operation),
        ))
        if hr < 0 or not operation:
            raise OSError(hr, "CoCreateInstance IFileOperation")
        created = True

        flags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_NOERRORUI
        if to_recycle:
            flags |= FOF_ALLOWUNDO | FOFX_ADDUNDORECORD
        hr = int(_com_call(operation, 5, (wintypes.DWORD,), flags))
        if hr < 0:
            raise OSError(hr, "SetOperationFlags")

        item_iid = GUID.from_uuid(IID_IShellItem)
        for raw in paths:
            item = ctypes.c_void_p()
            hr = int(shell32.SHCreateItemFromParsingName(
                _shell_path(raw), None, ctypes.byref(item_iid),
                ctypes.byref(item),
            ))
            if hr < 0 or not item:
                raise OSError(hr, f"SHCreateItemFromParsingName: {raw}")
            try:
                hr = int(_com_call(
                    operation, 18, (ctypes.c_void_p, ctypes.c_void_p),
                    item, None,
                ))
                if hr < 0:
                    raise OSError(hr, f"DeleteItem: {raw}")
            finally:
                _release(item)

        hr = int(_com_call(operation, 21, ()))
        if hr < 0:
            raise OSError(hr, "PerformOperations")

        aborted = wintypes.BOOL(False)
        hr = int(_com_call(
            operation, 22, (ctypes.POINTER(wintypes.BOOL),),
            ctypes.byref(aborted),
        ))
        if hr < 0:
            raise OSError(hr, "GetAnyOperationsAborted")
        if aborted.value:
            log.info("IFileOperation: операция прервана пользователем")
        return True
    finally:
        if created:
            _release(operation)
        if owns_com:
            ole32.CoUninitialize()

class SHFILEOPSTRUCTW(ctypes.Structure):
    """Структура SHFileOperationW (см. shellapi.h)."""

    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def build_file_list(paths: list[str]) -> str:
    """Собрать список путей с двойным NUL в конце (формат shell API)."""
    return "\0".join(paths) + "\0\0"


def _shell_delete(struct: SHFILEOPSTRUCTW, paths: list[str]) -> int:
    """Вызов SHFileOperationW (вынесено для тестов)."""
    return int(ctypes.windll.shell32.SHFileOperationW(ctypes.byref(struct)))


def _shell_path(path: str) -> str:
    """Абсолютный путь для оболочки.

    Префикс ``\\\\?\\`` намеренно не добавляется: IFileOperation и
    SHFileOperationW сами принимают пути длиннее MAX_PATH, а с префиксом
    оба API возвращают DE_INVALIDFILES (проверено на Windows 10).
    """
    return os.path.abspath(path)


def delete_many(
    paths: list[str],
    to_recycle: bool = True,
    use_ifile: bool = True,
) -> dict:
    """Удалить список путей одной операцией оболочки.

    Сначала пробует ``IFileOperation`` (COM), при недоступности —
    ``SHFileOperationW``. Оба варианта удаляют пакет за один вызов.

    Возвращает словарь:
      ``deleted`` — пути, которых больше нет;
      ``failed``  — пути, оставшиеся на месте;
      ``aborted`` — пользователь/система прервали операцию;
      ``error``   — код возврата SHFileOperationW (0 — успех);
      ``fallback``— True, если API недоступен и удаляли по одному.
    """
    result: dict = {
        "deleted": [],
        "failed": [],
        "aborted": False,
        "error": 0,
        "fallback": False,
    }

    existing: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not raw:
            continue
        try:
            path = Path(raw)
        except (TypeError, ValueError):
            continue
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        if os.path.lexists(str(path)):
            existing.append(str(path))

    if not existing:
        return result

    if use_ifile:
        try:
            if _ifile_delete(existing, to_recycle):
                return _verify(result, existing, 0, False)
        except (OSError, AttributeError, NotImplementedError) as e:
            log.info("IFileOperation недоступен: %s", e)

    flags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_NOCONFIRMMKDIR
    if to_recycle:
        flags |= FOF_ALLOWUNDO

    struct = SHFILEOPSTRUCTW()
    struct.hwnd = None
    struct.wFunc = FO_DELETE
    file_list = build_file_list([_shell_path(p) for p in existing])
    # c_wchar_p обрезает строку по первому NUL, поэтому держим буфер
    # с полным списком и передаём указатель на него.
    buffer_from = ctypes.create_unicode_buffer(file_list, len(file_list) + 1)
    struct.pFrom = ctypes.cast(buffer_from, ctypes.c_wchar_p)
    struct.pTo = None
    struct.fFlags = flags
    struct.fAnyOperationsAborted = False
    struct.hNameMappings = None
    struct.lpszProgressTitle = None

    try:
        code = _shell_delete(struct, existing)
    except (AttributeError, OSError):
        # Не Windows или API недоступен — удаляем по одному старым способом.
        log.warning("SHFileOperationW недоступен, поштучное удаление")
        result["fallback"] = True
        for target in existing:
            if safe_remove(Path(target), to_recycle=to_recycle):
                result["deleted"].append(target)
            else:
                result["failed"].append(target)
        return result

    if code != 0:
        log.warning("SHFileOperationW вернул код %s", code)
    return _verify(result, existing, code, bool(struct.fAnyOperationsAborted))


def _verify(
    result: dict,
    existing: list[str],
    code: int,
    aborted: bool,
) -> dict:
    """Заполнить deleted/failed по факту наличия путей."""
    result["error"] = code
    result["aborted"] = aborted
    for target in existing:
        if os.path.lexists(target):
            result["failed"].append(target)
        else:
            result["deleted"].append(target)
    return result
