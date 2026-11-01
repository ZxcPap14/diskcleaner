"""Тесты разбора записей $MFT на синтетических данных."""
from __future__ import annotations

import struct

from disk_cleaner_app.services import mft


def make_record(
    name: str = "file.txt",
    parent: int = 5,
    size: int = 0,
    is_dir: bool = False,
    namespace: int = 1,
    in_use: bool = True,
    with_data: bool = True,
) -> bytearray:
    """Запись MFT: $FILE_NAME + (для файла) нерезидентный $DATA."""
    rec = bytearray(1024)
    rec[0:4] = b"FILE"
    struct.pack_into("<HH", rec, 4, 0x30, 1)
    flags = 0x1 if in_use else 0
    if is_dir:
        flags |= 0x2
    struct.pack_into("<H", rec, 0x14, 0x38)
    struct.pack_into("<H", rec, 0x16, flags)

    body = bytearray(0x42 + len(name) * 2)
    struct.pack_into("<Q", body, 0x00, parent)
    body[0x40] = len(name)
    body[0x41] = namespace
    body[0x42:] = name.encode("utf-16-le")

    off = 0x38
    off = _resident(rec, off, 0x30, bytes(body))
    if with_data and not is_dir:
        off = _non_resident(rec, off, 0x80, size)
    struct.pack_into("<I", rec, off, 0xFFFFFFFF)
    return rec


def _resident(rec: bytearray, off: int, atype: int, value: bytes) -> int:
    length = 0x18 + len(value)
    struct.pack_into("<II", rec, off, atype, length)
    rec[off + 8] = 0  # резидентный
    struct.pack_into("<I", rec, off + 0x10, len(value))
    struct.pack_into("<H", rec, off + 0x14, 0x18)
    rec[off + 0x18:off + 0x18 + len(value)] = value
    return off + length


def _non_resident(rec: bytearray, off: int, atype: int, size: int) -> int:
    length = 0x40
    struct.pack_into("<II", rec, off, atype, length)
    rec[off + 8] = 1  # нерезидентный
    struct.pack_into("<Q", rec, off + 0x30, size)
    return off + length


def test_parse_file_record() -> None:
    parsed = mft._parse_record(make_record("setup.exe", parent=42, size=123456))

    assert parsed == ("setup.exe", 42, 123456, False)


def test_parse_directory_record() -> None:
    parsed = mft._parse_record(make_record("Windows", parent=5, is_dir=True))

    assert parsed == ("Windows", 5, 0, True)


def test_parse_skips_unused_and_dos_names() -> None:
    assert mft._parse_record(make_record(in_use=False)) is None
    assert mft._parse_record(make_record("FILE~1.TXT", namespace=2)) is None
    assert mft._parse_record(make_record("..")) is None


def test_parse_rejects_garbage() -> None:
    assert mft._parse_record(bytearray(1024)) is None


def test_fixups_restore_sector_tails() -> None:
    rec = bytearray(1024)
    rec[0:4] = b"FILE"
    struct.pack_into("<HH", rec, 4, 0x30, 3)
    rec[0x32:0x34] = b"\x11\x22"
    rec[0x34:0x36] = b"\x33\x44"
    rec[0x30:0x32] = b"\xaa\xbb"
    rec[510:512] = b"\xaa\xbb"
    rec[1022:1024] = b"\xaa\xbb"

    assert mft._apply_fixups(rec) is True
    assert bytes(rec[510:512]) == b"\x11\x22"
    assert bytes(rec[1022:1024]) == b"\x33\x44"


def test_fixups_reject_wrong_signature() -> None:
    rec = bytearray(1024)
    struct.pack_into("<HH", rec, 4, 0x30, 3)
    rec[0x30:0x32] = b"\xaa\xbb"

    assert mft._apply_fixups(rec) is False


def test_has_attribute_list_detects_extension_records() -> None:
    plain = make_record("big.bin", size=10)
    assert mft._has_attribute_list(plain) is False

    split = make_record("big.bin", with_data=False)
    off = struct.unpack_from("<H", split, 0x14)[0]
    while struct.unpack_from("<I", split, off)[0] != 0xFFFFFFFF:
        off += struct.unpack_from("<I", split, off + 4)[0]
    _resident(split, off, 0x20, b"\x01" * 8)  # $ATTRIBUTE_LIST вместо $DATA

    assert mft._has_attribute_list(split) is True


def test_data_runs_two_extents() -> None:
    rec = bytearray(1024)
    rec[0:4] = b"FILE"
    struct.pack_into("<H", rec, 0x14, 0x38)
    off = 0x38
    length = 0x48
    struct.pack_into("<II", rec, off, 0x80, length)
    rec[off + 8] = 1
    struct.pack_into("<H", rec, off + 0x20, 0x40)  # mapping pairs offset
    # (1000, 50) и (2000, 30)
    rec[off + 0x40:off + 0x44] = bytes([0x21, 50, 0xE8, 0x03])
    rec[off + 0x44:off + 0x48] = bytes([0x21, 30, 0xE8, 0x03])
    struct.pack_into("<I", rec, off + length, 0xFFFFFFFF)

    assert mft._data_runs(bytes(rec)) == [(1000, 50), (2000, 30)]


def test_extension_helper() -> None:
    assert mft._extension("Movie.MKV") == "mkv"
    assert mft._extension("README") == ""


def test_unopenable_volume_returns_none() -> None:
    assert mft.scan_volume("Q:\\") is None


def test_available_is_bool() -> None:
    assert isinstance(mft.available(), bool)
