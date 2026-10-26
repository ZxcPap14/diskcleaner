"""Анализатор: скан файлов, статистика расширений и фильтры."""
from __future__ import annotations

import threading

import pytest

from disk_cleaner_app.services import analyzer
from disk_cleaner_app.services.analyzer import (
    extension_label,
    file_extension,
    filter_files,
    scan_files,
)


def _make_file(path, size_mb: int, extension: str = "bin") -> None:
    """Разреженный файл нужного размера (не забивает диск)."""
    with open(path / f"file-{size_mb}.{extension}", "wb") as f:
        f.seek(size_mb * 1024 * 1024 - 1)
        f.write(b"\0")


@pytest.fixture
def only_tmp(monkeypatch, tmp_path):
    """Сканировать только временную папку, а не реальные HOME/TEMP."""
    monkeypatch.setattr(analyzer, "_analysis_roots", lambda _root: [str(tmp_path)])
    return tmp_path


def test_scan_collects_files_and_extension_totals(only_tmp) -> None:
    _make_file(only_tmp, 3, "mp4")
    _make_file(only_tmp, 1, "mp4")
    (only_tmp / "file-2.zip").write_bytes(b"x" * (2 * 1024 * 1024))
    (only_tmp / ".gitignore").write_bytes(b"*.tmp\n")

    scan = scan_files(str(only_tmp), min_size_mb=0, limit=100)

    assert scan.total_files == 4
    assert scan.truncated is False
    assert [f["size"] for f in scan.files] == sorted(
        (f["size"] for f in scan.files), reverse=True
    )
    assert {f["extension"] for f in scan.files} == {"mp4", "zip", ""}
    stats = {e.extension: (e.size, e.count) for e in scan.extensions}
    assert stats["mp4"] == (4 * 1024**2, 2)
    assert stats["zip"] == (2 * 1024**2, 1)
    assert stats[""] == (6, 1)


def test_scan_limit_keeps_largest_but_counts_everything(only_tmp) -> None:
    _make_file(only_tmp, 1, "a")
    _make_file(only_tmp, 4, "b")
    _make_file(only_tmp, 2, "c")
    _make_file(only_tmp, 3, "d")

    scan = scan_files(str(only_tmp), min_size_mb=1, limit=2)

    assert [f["size"] for f in scan.files] == [4 * 1024**2, 3 * 1024**2]
    assert scan.truncated is True
    assert scan.total_files == 4
    assert sum(e.count for e in scan.extensions) == 4


def test_scan_skips_recycle_bin(only_tmp) -> None:
    trash = only_tmp / "$Recycle.Bin"
    trash.mkdir()
    _make_file(trash, 5, "bin")
    _make_file(only_tmp, 1, "txt")

    scan = scan_files(str(only_tmp), min_size_mb=1, limit=10)

    assert [f["name"] for f in scan.files] == ["file-1.txt"]


def test_scan_stops_when_cancelled(only_tmp) -> None:
    _make_file(only_tmp, 2, "bin")
    cancel = threading.Event()
    cancel.set()

    scan = scan_files(str(only_tmp), min_size_mb=1, cancel=cancel)

    assert scan.files == []
    assert scan.total_files == 0
    assert scan.extensions == []


def test_filter_files_by_extension_size_and_age() -> None:
    now = 1_800_000_000.0
    day = 86400.0
    files = [
        {"name": "old.mp4", "path": "a", "size": 500 * 1024**2,
         "modified": now - 400 * day, "extension": "mp4"},
        {"name": "new.mp4", "path": "b", "size": 100 * 1024**2,
         "modified": now - 10 * day, "extension": "mp4"},
        {"name": "old.zip", "path": "c", "size": 800 * 1024**2,
         "modified": now - 800 * day, "extension": "zip"},
    ]

    assert [f["name"] for f in filter_files(files, extension="mp4")] == [
        "old.mp4", "new.mp4",
    ]
    assert [f["name"] for f in filter_files(files, min_size_mb=500)] == [
        "old.mp4", "old.zip",
    ]
    assert [f["name"] for f in filter_files(files, min_age_days=365, now=now)] == [
        "old.mp4", "old.zip",
    ]
    assert [f["name"] for f in filter_files(
        files, extension="mp4", min_size_mb=200, min_age_days=365, now=now
    )] == ["old.mp4"]


def test_filter_derives_extension_from_name_when_missing() -> None:
    files = [{"name": "movie.MKV", "path": "x", "size": 10, "modified": 0}]

    assert filter_files(files, extension="mkv") == files


def test_filter_can_select_files_without_extension() -> None:
    files = [
        {"name": "movie.mp4", "path": "a", "size": 10, "modified": 0},
        {"name": "README", "path": "b", "size": 10, "modified": 0},
        {"name": ".gitignore", "path": "c", "size": 10, "modified": 0},
    ]

    assert [f["name"] for f in filter_files(files, extension=".")] == [
        "README", ".gitignore",
    ]


def test_extension_helpers() -> None:
    assert file_extension("movie.MP4") == "mp4"
    assert file_extension("archive.tar.gz") == "gz"
    assert file_extension(".gitignore") == ""
    assert extension_label("mp4") == ".mp4"
    assert extension_label("") == "без расширения"
