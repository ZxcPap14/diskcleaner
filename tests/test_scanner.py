"""Тесты дедупликации и отмены в ScanEngine."""
from __future__ import annotations

import threading

from helpers import FakeCleaner

from disk_cleaner_app.cleaners.base import (
    get_dir_size,
    reset_scan_cancel,
    set_scan_cancel,
)
from disk_cleaner_app.services.scanner import ScanEngine


def test_dedupe_by_id() -> None:
    cleaners = [
        FakeCleaner("same", size=5),
        FakeCleaner("same", size=7),
        FakeCleaner("other", size=9),
    ]
    result = ScanEngine._dedupe(cleaners)

    assert [c.id for c in result] == ["same", "other"]
    assert result[0].size == 5


def test_dedupe_by_preview_path() -> None:
    cleaners = [
        FakeCleaner("a", preview_path=r"C:\Temp\Cache"),
        FakeCleaner("b", preview_path=r"c:\temp\cache"),
        FakeCleaner("c", preview_path=r"C:\Temp\Other"),
    ]
    result = ScanEngine._dedupe(cleaners)

    assert [c.id for c in result] == ["a", "c"]


def test_scan_all_dedupes_and_fills_sizes() -> None:
    engine = ScanEngine()
    try:
        cleaners = [
            FakeCleaner("a", size=5),
            FakeCleaner("a", size=7),
            FakeCleaner("b", size=9, preview_path=r"C:\Temp\B"),
        ]
        result = engine.scan_all(cleaners, auto_discover=False)
    finally:
        engine.shutdown()

    assert [c.id for c in result] == ["a", "b"]
    assert all(c.scanned for c in result)
    assert [c.size for c in result] == [5, 9]


def test_scan_error_is_recorded_not_raised() -> None:
    class Exploding(FakeCleaner):
        def get_size(self) -> int:
            raise PermissionError("access denied")

    engine = ScanEngine()
    try:
        result = engine.scan_all([Exploding("bad")], auto_discover=False)
    finally:
        engine.shutdown()

    assert result[0].scan_error == "access denied"
    assert result[0].size == 0
    assert result[0].scanned is True


def test_cancelled_dir_size_stops_immediately(tmp_path) -> None:
    (tmp_path / "file.bin").write_bytes(b"x" * 100)
    event = threading.Event()
    event.set()
    token = set_scan_cancel(event)
    try:
        assert get_dir_size(tmp_path) == 0
    finally:
        reset_scan_cancel(token)


def test_scan_can_be_cancelled_from_progress_callback() -> None:
    engine = ScanEngine()
    try:
        cleaners = [FakeCleaner(f"c{i}", size=1) for i in range(5)]

        def on_progress(done: int, total: int) -> None:
            engine.cancel()

        result = engine.scan_all(
            cleaners, auto_discover=False, progress_callback=on_progress
        )
    finally:
        engine.shutdown()

    assert engine.was_cancelled is True
    assert result


def test_cancel_flag_is_reset_between_scans() -> None:
    engine = ScanEngine()
    try:
        engine.cancel()
        result = engine.scan_all(
            [FakeCleaner("one", size=1)], auto_discover=False
        )
    finally:
        engine.shutdown()

    assert engine.was_cancelled is False
    assert result[0].scanned is True
