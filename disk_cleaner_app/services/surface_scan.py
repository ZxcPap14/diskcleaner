"""🧪 Проверка поверхности диска — только чтение (аналог Victoria read test).

Читает сырое устройство ``\\\\.\\PhysicalDriveN`` блоками, измеряет скорость
и фиксирует ошибки чтения. Никаких записей на диск не выполняется.
Требуются права администратора.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
FILE_FLAG_NO_BUFFERING = 0x20000000

MEM_COMMIT = 0x00001000
MEM_RESERVE = 0x00002000
PAGE_READWRITE = 0x04
MEM_RELEASE = 0x8000

ERROR_ACCESS_DENIED = 5
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_ERRORS = 200
ALIGNMENT = 4096
DEFAULT_CHUNK = 4 * 1024 * 1024


class LARGE_INTEGER(ctypes.Structure):
    _fields_ = [("QuadPart", ctypes.c_longlong)]


def disk_path(index: int) -> str:
    return f"\\\\.\\PhysicalDrive{int(index)}"


def plan_size(total_bytes: int, limit_bytes: int | None) -> int:
    """Сколько байт читать: весь диск или заданный лимит."""
    total = max(0, int(total_bytes or 0))
    if limit_bytes is None:
        return total
    return min(total, max(0, int(limit_bytes)))


def format_speed(bytes_per_second: float) -> str:
    value = max(0.0, float(bytes_per_second))
    if value >= 1024 ** 3:
        return f"{value / 1024 ** 3:.2f} ГБ/с"
    if value >= 1024 ** 2:
        return f"{value / 1024 ** 2:.1f} МБ/с"
    if value >= 1024:
        return f"{value / 1024:.0f} КБ/с"
    return f"{value:.0f} Б/с"


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} ч {minutes:02d} мин"
    if minutes:
        return f"{minutes} мин {secs:02d} с"
    return f"{secs} с"


def _aligned(value: int) -> int:
    return value - (value % ALIGNMENT)


def read_surface(
    disk_index: int,
    total_bytes: int = 0,
    limit_bytes: int | None = None,
    cancel: threading.Event | None = None,
    on_progress=None,
    chunk_size: int = DEFAULT_CHUNK,
) -> dict:
    """Прочитать поверхность диска и вернуть статистику.

    ``on_progress(done, total, speed)`` вызывается из рабочего потока.
    При отсутствии прав поднимает ``PermissionError``.
    """
    result: dict = {
        "read_bytes": 0,
        "total_bytes": 0,
        "elapsed": 0.0,
        "min_speed": 0.0,
        "max_speed": 0.0,
        "avg_speed": 0.0,
        "errors": [],
        "aborted": False,
    }

    kernel32 = ctypes.windll.kernel32
    create_file = kernel32.CreateFileW
    create_file.restype = wintypes.HANDLE
    create_file.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    read_file = kernel32.ReadFile
    read_file.restype = wintypes.BOOL
    read_file.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    get_size = kernel32.GetFileSizeEx
    get_size.restype = wintypes.BOOL
    get_size.argtypes = [wintypes.HANDLE, ctypes.POINTER(LARGE_INTEGER)]
    virtual_alloc = kernel32.VirtualAlloc
    virtual_alloc.restype = ctypes.c_void_p
    virtual_alloc.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD,
    ]
    virtual_free = kernel32.VirtualFree
    virtual_free.restype = wintypes.BOOL
    virtual_free.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
    close_handle = kernel32.CloseHandle
    close_handle.restype = wintypes.BOOL
    close_handle.argtypes = [wintypes.HANDLE]

    path = disk_path(disk_index)
    flags = FILE_FLAG_SEQUENTIAL_SCAN | FILE_FLAG_NO_BUFFERING
    handle = create_file(
        path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, flags, None,
    )
    if handle == INVALID_HANDLE_VALUE:
        # Некоторые контроллеры не поддерживают no-buffering.
        handle = create_file(
            path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, None,
        )
    if handle == INVALID_HANDLE_VALUE:
        code = int(kernel32.GetLastError())
        if code == ERROR_ACCESS_DENIED:
            raise PermissionError(
                "Нужны права администратора для чтения физического диска."
            )
        raise OSError(code, f"Не удалось открыть {path}")

    chunk = _aligned(max(ALIGNMENT, int(chunk_size)))
    buffer = virtual_alloc(
        None, ctypes.c_size_t(chunk), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
    )
    if not buffer:
        close_handle(handle)
        raise OSError("Не удалось выделить буфер для чтения")

    try:
        size = LARGE_INTEGER()
        if get_size(handle, ctypes.byref(size)):
            disk_size = int(size.QuadPart)
        else:
            disk_size = max(0, int(total_bytes))
        limit = _aligned(plan_size(disk_size, limit_bytes))
        result["total_bytes"] = limit

        offset = 0
        read_bytes = 0
        errors: list[dict] = []
        min_speed = 0.0
        max_speed = 0.0
        started = time.perf_counter()
        last_report = 0.0
        bytes_read = wintypes.DWORD(0)

        while offset < limit:
            if cancel is not None and cancel.is_set():
                result["aborted"] = True
                break
            step = min(chunk, limit - offset)
            step = _aligned(step)
            if step <= 0:
                break

            before = time.perf_counter()
            ok = read_file(
                handle, buffer, step, ctypes.byref(bytes_read), None
            )
            moment = time.perf_counter()
            if not ok:
                code = int(kernel32.GetLastError())
                if len(errors) < MAX_ERRORS:
                    errors.append({"offset": offset, "code": code})
                log.warning("Ошибка чтения %s по %s: %s", path, offset, code)
                offset += step
            else:
                got = int(bytes_read.value)
                read_bytes += got
                delta = moment - before
                if got > 0 and delta > 0:
                    speed = got / delta
                    min_speed = speed if min_speed == 0 else min(min_speed, speed)
                    max_speed = max(max_speed, speed)
                offset += got or step

            if on_progress is not None and (
                moment - last_report >= 0.2 or offset >= limit
            ):
                last_report = moment
                elapsed = max(moment - started, 1e-9)
                on_progress(offset, limit, read_bytes / elapsed)

        elapsed = max(time.perf_counter() - started, 1e-9)
        result["read_bytes"] = read_bytes
        result["elapsed"] = elapsed
        result["errors"] = errors
        result["avg_speed"] = read_bytes / elapsed
        result["min_speed"] = min_speed
        result["max_speed"] = max_speed
        log.info(
            "Проверка поверхности %s: %s, ошибок %s, %.1f МБ/с",
            path, "прервано" if result["aborted"] else "завершено",
            len(errors), result["avg_speed"] / 1024 ** 2,
        )
    finally:
        virtual_free(ctypes.c_void_p(buffer), 0, MEM_RELEASE)
        close_handle(handle)

    return result
