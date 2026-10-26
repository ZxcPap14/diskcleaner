"""Слой E: поиск крупных файлов — порог, лимит, отмена, возраст."""
from __future__ import annotations

import datetime
import os
import subprocess
import threading

from disk_cleaner_app.services.large_files import (
    format_age,
    format_modified,
    plural_files,
    reveal_in_explorer,
    scan_large_files,
)


def _make_file(path, size_mb: int) -> None:
    """Создать файл нужного размера, не забивая диск (разреженный на NTFS)."""
    with open(path, "wb") as f:
        f.seek(size_mb * 1024 * 1024 - 1)
        f.write(b"\0")


def _files(*sizes: int, root) -> None:
    for index, size in enumerate(sizes, 1):
        _make_file(root / f"file{index}.bin", size)


def test_scan_finds_files_above_threshold_and_sorts(tmp_path) -> None:
    _files(1, 3, 2, root=tmp_path)

    result = scan_large_files(str(tmp_path), min_size_mb=2, limit=10)

    assert [item["size"] for item in result] == [3 * 1024**2, 2 * 1024**2]
    assert [item["name"] for item in result] == ["file2.bin", "file3.bin"]
    assert all(item["modified"] > 0 for item in result)
    assert all(item["path"].endswith(item["name"]) for item in result)


def test_scan_respects_limit_and_keeps_largest(tmp_path) -> None:
    _files(1, 2, 3, 4, 5, root=tmp_path)

    result = scan_large_files(str(tmp_path), min_size_mb=1, limit=3)

    assert [item["size"] for item in result] == [5 * 1024**2, 4 * 1024**2, 3 * 1024**2]


def test_scan_skips_service_and_recycle_dirs(tmp_path) -> None:
    _files(1, root=tmp_path)
    recycle = tmp_path / "$Recycle.Bin"
    recycle.mkdir()
    _make_file(recycle / "deleted.bin", 9)

    result = scan_large_files(str(tmp_path), min_size_mb=1, limit=10)

    assert [item["name"] for item in result] == ["file1.bin"]


def test_scan_stops_when_cancelled(tmp_path) -> None:
    _files(2, root=tmp_path)
    cancel = threading.Event()
    cancel.set()

    assert scan_large_files(str(tmp_path), min_size_mb=1, cancel=cancel) == []


def test_scan_missing_root_returns_empty() -> None:
    assert scan_large_files(r"Z:\definitely-missing", min_size_mb=1) == []


def test_format_age_buckets() -> None:
    now = datetime.datetime(2026, 10, 26, 12, 0, 0)

    def age(days: int) -> str:
        return format_age((now - datetime.timedelta(days=days)).timestamp(), now)

    assert age(0) == "сегодня"
    assert format_age((now + datetime.timedelta(days=1)).timestamp(), now) == "сегодня"
    assert age(5) == "5 дн."
    assert age(29) == "29 дн."
    assert age(60) == "2 мес."
    assert age(400) == "1 г."


def test_format_modified_date() -> None:
    stamp = datetime.datetime(2024, 3, 12, 9, 30).timestamp()
    assert format_modified(stamp) == "12.03.2024"


def test_plural_files_agrees_with_number() -> None:
    cases = {
        1: "файл",
        2: "файла",
        4: "файла",
        5: "файлов",
        11: "файлов",
        21: "файл",
        22: "файла",
        25: "файлов",
        111: "файлов",
    }
    assert {count: plural_files(count) for count in cases} == cases


def test_reveal_in_explorer_selects_the_file(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **_kw: calls.append(args))

    target = r"C:\Temp\a b.txt"
    assert reveal_in_explorer(target) is True
    assert calls == [["explorer", "/select,", os.path.normpath(target)]]


def test_reveal_in_explorer_handles_missing_file_and_no_explorer(monkeypatch) -> None:
    assert reveal_in_explorer("") is False

    def boom(*_args, **_kwargs):
        raise OSError("explorer missing")

    monkeypatch.setattr(subprocess, "Popen", boom)
    assert reveal_in_explorer(r"C:\Temp\a.txt") is False
