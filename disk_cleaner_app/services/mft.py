"""Быстрый скан NTFS: чтение $MFT напрямую вместо обхода каталогов.

Рекурсивный ``os.walk`` делает запрос на каждую папку; на диске с
миллионом файлов это минуты. Здесь $MFT читается последовательно и
разбирается как записи: имя, родитель, размер. Работает только на NTFS и
только с правами администратора (том открывается на чтение), поэтому
любая ошибка возвращает ``None`` — вызывающий код идёт обычным путём.
"""
from __future__ import annotations

import ctypes
import logging
import os
import struct
import threading
from ctypes import wintypes
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FSCTL_GET_NTFS_VOLUME_DATA = 0x00090064
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ROOT_RECORD = 5
# За один ReadFile читаем 8 МБ: меньше системных вызовов, память не растёт.
CHUNK = 8 * 1024 * 1024
# Каталоги, которые не дают полезной картины (как в analyzer.SKIP_DIRS).
SKIP_DIRS = {"$recycle.bin", "system volume information"}

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
    wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
]
kernel32.SetFilePointerEx.argtypes = [
    wintypes.HANDLE, ctypes.c_longlong, wintypes.LPVOID, wintypes.DWORD,
]
kernel32.ReadFile.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
]


@dataclass
class VolumeScan:
    """Итог одного прохода по $MFT."""

    root: str
    folders: list[tuple[str, int]] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    total_files: int = 0
    total_bytes: int = 0
    extension_sizes: dict[str, int] = field(default_factory=dict)
    extension_counts: dict[str, int] = field(default_factory=dict)


def available() -> bool:
    """Есть ли смысл пробовать: Windows, NTFS, права администратора."""
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _open_volume(volume: str) -> int | None:
    path = "\\\\.\\" + volume.rstrip("\\/")
    handle = kernel32.CreateFileW(
        path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
        OPEN_EXISTING, 0, None,
    )
    if handle is None or handle == INVALID_HANDLE_VALUE:
        return None
    return int(handle)


def _volume_data(handle: int) -> tuple[int, int, int, int] | None:
    """(кластер, размер записи MFT, длина MFT, LCN начала MFT) или None."""
    out = ctypes.create_string_buffer(128)
    returned = wintypes.DWORD(0)
    ok = kernel32.DeviceIoControl(
        wintypes.HANDLE(handle), FSCTL_GET_NTFS_VOLUME_DATA, None, 0,
        out, 128, ctypes.byref(returned), None,
    )
    if not ok or returned.value < 96:
        return None
    cluster = struct.unpack_from("<I", out.raw, 44)[0]
    record = struct.unpack_from("<I", out.raw, 48)[0]
    valid = struct.unpack_from("<Q", out.raw, 56)[0]
    mft_lcn = struct.unpack_from("<Q", out.raw, 64)[0]
    if not cluster or not record or not valid:
        return None
    return cluster, record, valid, mft_lcn


def _read_at(handle: int, offset: int, size: int) -> bytes | None:
    if not kernel32.SetFilePointerEx(
        wintypes.HANDLE(handle), offset, None, 0
    ):
        return None
    buf = ctypes.create_string_buffer(size)
    read = wintypes.DWORD(0)
    if not kernel32.ReadFile(
        wintypes.HANDLE(handle), buf, size, ctypes.byref(read), None
    ):
        return None
    return buf.raw[: read.value]


def _apply_fixups(rec: bytearray) -> bool:
    """Вернуть настоящие последние 2 байта каждого сектора записи."""
    usa_off, usa_cnt = struct.unpack_from("<HH", rec, 4)
    if usa_cnt < 2 or usa_off + usa_cnt * 2 > len(rec):
        return False
    usn = bytes(rec[usa_off:usa_off + 2])
    for i in range(1, usa_cnt):
        pos = i * 512 - 2
        if pos + 2 > len(rec):
            break
        if bytes(rec[pos:pos + 2]) != usn:
            return False
        rec[pos:pos + 2] = rec[usa_off + 2 * i: usa_off + 2 * i + 2]
    return True


def _data_runs(rec: bytes | bytearray) -> list[tuple[int, int]]:
    """Таблица размещения первого безымянного $DATA: [(lcn, кластеров)]."""
    off = struct.unpack_from("<H", rec, 0x14)[0]
    while off + 8 <= len(rec):
        atype, alen = struct.unpack_from("<II", rec, off)
        if atype == 0xFFFFFFFF or alen <= 0 or off + alen > len(rec):
            break
        if atype == 0x80 and rec[off + 8] and not rec[off + 9]:
            start = off + struct.unpack_from("<H", rec, off + 0x20)[0]
            end = off + alen
            runs: list[tuple[int, int]] = []
            lcn = 0
            pos = start
            while pos < end:
                header = rec[pos]
                if header == 0:
                    break
                size_len = header & 0x0F
                off_len = header >> 4
                pos += 1
                if size_len == 0 or pos + size_len + off_len > end:
                    break
                count = int.from_bytes(rec[pos:pos + size_len], "little")
                pos += size_len
                delta = int.from_bytes(
                    rec[pos:pos + off_len], "little", signed=True
                )
                pos += off_len
                lcn += delta
                if count > 0:
                    runs.append((lcn, count))
            return runs
        off += alen
    return []


def _parse_record(rec: bytearray) -> tuple[str, int, int, bool] | None:
    """(имя, запись-родитель, размер, это_папка) или None.

    $FILE_NAME без WIN32-имени (namespace 2, только DOS) — это ссылка,
    которая уже описана записью с обычным именем, поэтому такие пропускаем.
    """
    if rec[0:4] != b"FILE":
        return None
    flags = struct.unpack_from("<H", rec, 0x16)[0]
    if not flags & 0x1:
        return None
    off = struct.unpack_from("<H", rec, 0x14)[0]
    name = ""
    parent = 0
    size = 0
    while off + 8 <= len(rec):
        atype, alen = struct.unpack_from("<II", rec, off)
        if atype == 0xFFFFFFFF or alen <= 0 or off + alen > len(rec):
            break
        non_resident = rec[off + 8]
        name_len = rec[off + 9]
        if atype == 0x30 and not non_resident:
            value = off + struct.unpack_from("<H", rec, off + 0x14)[0]
            if value + 0x42 <= off + alen:
                nlen = rec[value + 0x40]
                namespace = rec[value + 0x41]
                if nlen and namespace != 2 and not name:
                    parent = struct.unpack_from("<Q", rec, value)[0] & 0xFFFFFFFFFFFF
                    raw = bytes(rec[value + 0x42: value + 0x42 + nlen * 2])
                    name = raw.decode("utf-16-le", "replace")
        elif atype == 0x80 and not name_len:
            if non_resident:
                size = struct.unpack_from("<Q", rec, off + 0x30)[0]
            else:
                size = struct.unpack_from("<I", rec, off + 0x10)[0]
        off += alen
    if not name or name in (".", ".."):
        return None
    return name, parent, size, bool(flags & 0x2)


def _has_attribute_list(rec: bytes | bytearray) -> bool:
    """Есть ли $ATTRIBUTE_LIST: тогда размер $DATA лежит в другой записи."""
    off = struct.unpack_from("<H", rec, 0x14)[0]
    while off + 8 <= len(rec):
        atype, alen = struct.unpack_from("<II", rec, off)
        if atype == 0xFFFFFFFF or alen <= 0 or off + alen > len(rec):
            return False
        if atype == 0x20:
            return True
        off += alen
    return False


def _extension(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return ext[1:] if ext.startswith(".") else ext


def _inside_skipped_dir(parts: list[str]) -> bool:
    return any(p.lower() in SKIP_DIRS for p in parts)


def scan_volume(
    volume: str = "C:\\",
    min_bytes: int = 0,
    limit: int = 5000,
    cancel: threading.Event | None = None,
) -> VolumeScan | None:
    """Размеры папок верхнего уровня и файлы >= min_bytes за один проход.

    ``None`` — скан невозможен (не NTFS, нет прав, ошибка чтения); тогда
    вызывающий идёт обычным рекурсивным путём.
    """
    root = volume.rstrip("\\/")
    handle = _open_volume(root)
    if handle is None:
        return None
    try:
        data = _volume_data(handle)
        if data is None:
            return None
        cluster, record_size, valid, mft_lcn = data
        if record_size < 512 or record_size > 65536:
            return None
        first = _read_at(handle, mft_lcn * cluster, record_size)
        if not first:
            return None
        head = bytearray(first)
        if not _apply_fixups(head):
            return None
        runs = _data_runs(head)
        if not runs:
            return None

        dirs: dict[int, int] = {}
        dir_names: dict[int, str] = {}
        acc: dict[int, int] = {}
        big: list[tuple[int, str, int]] = []
        # $DATA в extension-записи: размер добираем os.stat после разбора.
        lost_attr: list[tuple[int, str]] = []
        index = 0
        started = False

        buffer = ctypes.create_string_buffer(CHUNK)
        for lcn, clusters in runs:
            offset = lcn * cluster
            remaining = min(clusters * cluster, valid)
            while remaining > 0 and not (cancel and cancel.is_set()):
                size = min(remaining, CHUNK)
                size -= size % record_size
                if size <= 0:
                    break
                if not kernel32.SetFilePointerEx(
                    wintypes.HANDLE(handle), offset, None, 0
                ):
                    return None
                read = wintypes.DWORD(0)
                if not kernel32.ReadFile(
                    wintypes.HANDLE(handle), buffer, size,
                    ctypes.byref(read), None,
                ):
                    return None
                chunk = buffer.raw[: read.value]
                for pos in range(0, len(chunk) - record_size + 1, record_size):
                    rec = bytearray(chunk[pos:pos + record_size])
                    if rec[0:4] != b"FILE":
                        index += 1
                        continue
                    if not started:
                        started = True
                    if not _apply_fixups(rec):
                        index += 1
                        continue
                    parsed = _parse_record(rec)
                    if parsed is None:
                        index += 1
                        continue
                    name, parent, size_bytes, is_dir = parsed
                    if is_dir:
                        dirs[index] = parent
                        dir_names[index] = name
                        acc.setdefault(index, 0)
                    else:
                        if parent in acc:
                            acc[parent] += size_bytes
                        if min_bytes > 0 and size_bytes >= min_bytes:
                            big.append((parent, name, size_bytes))
                        if not size_bytes and _has_attribute_list(rec):
                            lost_attr.append((parent, name))
                    index += 1
                offset += read.value
                remaining -= read.value
                if cancel and cancel.is_set():
                    break
            if cancel and cancel.is_set():
                break
        if not started:
            return None

        result = VolumeScan(root=root)
        paths: dict[int, str] = {ROOT_RECORD: root}

        def path_of(rec_no: int) -> tuple[str, list[str]]:
            """Полный путь папки и его части ниже корня (с кэшем)."""
            cached = paths.get(rec_no)
            if cached is not None:
                return cached, [p for p in cached[len(root):].split("\\") if p]
            chain: list[str] = []
            current = rec_no
            while current not in paths and len(chain) < 128:
                name = dir_names.get(current)
                if name is None:
                    break
                chain.append(name)
                current = dirs.get(current, ROOT_RECORD)
            full = paths.get(current, root)
            for part in reversed(chain):
                full = full + "\\" + part
            paths[rec_no] = full
            return full, [p for p in full[len(root):].split("\\") if p]

        # Размеры папок: сумма файлов уже в acc, осталось поднять её вверх.
        for parent, name in lost_attr:
            parent_path, parts = path_of(parent)
            if _inside_skipped_dir(parts):
                continue
            try:
                real = os.stat(
                    parent_path + "\\" + name, follow_symlinks=False
                ).st_size
            except OSError:
                continue
            if not real:
                continue
            acc[parent] = acc.get(parent, 0) + real
            if min_bytes > 0 and real >= min_bytes:
                big.append((parent, name, real))

        depth: dict[int, int] = {}
        for rec_no in dirs:
            chain = 0
            current = rec_no
            while current in dirs and chain < 128:
                current = dirs[current]
                chain += 1
            depth[rec_no] = chain
        for rec_no in sorted(dirs, key=lambda r: depth[r], reverse=True):
            acc[dirs[rec_no]] = acc.get(dirs[rec_no], 0) + acc.get(rec_no, 0)
        for rec_no, parent in dirs.items():
            if parent == ROOT_RECORD:
                name = dir_names[rec_no]
                if name.lower() not in SKIP_DIRS:
                    result.folders.append((name, acc.get(rec_no, 0)))
        result.folders.sort(key=lambda item: item[1], reverse=True)

        if min_bytes > 0:
            for parent, name, size_bytes in big:
                parent_path, parts = path_of(parent)
                full = parent_path + "\\" + name
                if _inside_skipped_dir(parts):
                    continue
                if parts and parts[0].lower() == "windows" and (
                    len(parts) < 2 or parts[1].lower() != "temp"
                ):
                    continue
                result.files.append({
                    "name": name,
                    "path": full,
                    "size": size_bytes,
                    "modified": 0.0,
                    "extension": _extension(name),
                })
            result.files.sort(key=lambda f: f["size"], reverse=True)
            for item in result.files:
                ext = item["extension"]
                result.extension_sizes[ext] = (
                    result.extension_sizes.get(ext, 0) + item["size"]
                )
                result.extension_counts[ext] = (
                    result.extension_counts.get(ext, 0) + 1
                )
            result.total_files = len(result.files)
            result.total_bytes = sum(item["size"] for item in result.files)
            del result.files[limit:]
        return result
    except (OSError, ValueError, struct.error):
        log.debug("MFT-скан %s не удался", root, exc_info=True)
        return None
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(handle))
