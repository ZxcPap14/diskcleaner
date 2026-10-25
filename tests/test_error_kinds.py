"""Таблица errno/winerror → род причины и агрегация (5B-1)."""
from __future__ import annotations

import errno
from pathlib import Path

import pytest

from disk_cleaner_app.services import error_kinds as ek

MODULE = "disk_cleaner_app.services.error_kinds"


def _oserror(winerror: int | None = None, err: int | None = None) -> OSError:
    e = OSError(err, "boom")
    if winerror is not None:
        e.winerror = winerror
    return e


def test_winerror_table() -> None:
    cases = {
        2: ek.NOT_FOUND,
        3: ek.NOT_FOUND,
        5: ek.ACCESS_DENIED,
        32: ek.LOCKED,
        33: ek.LOCKED,
        206: ek.PATH_TOO_LONG,
    }
    for code, kind in cases.items():
        assert ek.classify_error(_oserror(winerror=code)) == kind


def test_errno_table() -> None:
    assert ek.classify_error(_oserror(err=errno.EACCES)) == ek.ACCESS_DENIED
    assert ek.classify_error(_oserror(err=errno.ENOENT)) == ek.NOT_FOUND
    assert ek.classify_error(_oserror(err=errno.EBUSY)) == ek.IN_USE
    assert ek.classify_error(_oserror(err=errno.ENAMETOOLONG)) == ek.PATH_TOO_LONG
    assert ek.classify_error(_oserror(err=999_999)) == ek.UNKNOWN


def test_classify_path_missing(tmp_path: Path) -> None:
    assert ek.classify_path(tmp_path / "gone.bin") == ek.NOT_FOUND


def test_classify_path_too_long() -> None:
    long_path = "C:\\" + "a" * 300 + ".bin"
    assert ek.classify_path(long_path) == ek.PATH_TOO_LONG


def test_classify_path_readonly_attribute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "f.bin").touch()
    monkeypatch.setattr(MODULE + "._get_attributes", lambda p: 0x1)  # READONLY
    monkeypatch.setattr(MODULE + "._open_exclusive_error_code", lambda p: 0)
    assert ek.classify_path(tmp_path / "f.bin") == ek.READONLY


def test_classify_path_cloud_placeholder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "f.bin").touch()
    monkeypatch.setattr(MODULE + "._get_attributes", lambda p: 0x00400000)
    monkeypatch.setattr(MODULE + "._open_exclusive_error_code", lambda p: 0)
    assert ek.classify_path(tmp_path / "f.bin") == ek.CLOUD_PLACEHOLDER


def test_classify_path_locked_and_denied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "f.bin").touch()
    monkeypatch.setattr(MODULE + "._get_attributes", lambda p: -1)
    monkeypatch.setattr(MODULE + "._open_exclusive_error_code", lambda p: 32)
    assert ek.classify_path(tmp_path / "f.bin") == ek.LOCKED

    monkeypatch.setattr(MODULE + "._open_exclusive_error_code", lambda p: 5)
    assert ek.classify_path(tmp_path / "f.bin") == ek.ACCESS_DENIED


def test_classify_paths_skips_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "f.bin").touch()
    monkeypatch.setattr(MODULE + "._get_attributes", lambda p: -1)
    monkeypatch.setattr(MODULE + "._open_exclusive_error_code", lambda p: 32)
    disappeared = tmp_path / "gone.bin"
    locked = tmp_path / "f.bin"

    kinds = ek.classify_paths([str(disappeared), str(locked), str(locked)])

    # исчезнувший путь — не ошибка, занятый посчитан дважды
    assert kinds == {ek.LOCKED: 2}


def test_summarize_and_remediation() -> None:
    kinds = {ek.LOCKED: 9, ek.ACCESS_DENIED: 3}
    text = ek.summarize_kinds(kinds)
    assert "занято другим процессом 9" in text
    assert "отказ в доступе 3" in text
    assert ek.remediation(kinds).startswith("закройте")

    kinds2 = {ek.ACCESS_DENIED: 1, ek.READONLY: 1}
    assert ek.remediation(kinds2) == ek.KIND_HINTS[ek.ACCESS_DENIED]

    assert ek.remediation({}) == ""
    assert ek.summarize_kinds({}) == ""


def test_summarize_orders_by_count() -> None:
    text = ek.summarize_kinds({ek.UNKNOWN: 1, ek.LOCKED: 5})
    assert text.index("занято") < text.index("неясна")
