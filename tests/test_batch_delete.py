"""Тесты пакетного удаления через SHFileOperationW."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from disk_cleaner_app.services import batch_delete
from disk_cleaner_app.services.batch_delete import build_file_list, delete_many


def test_file_list_has_double_null_terminator() -> None:
    value = build_file_list([r"C:\a", r"C:\b"])

    assert value == "C:\\a\0C:\\b\0\0"
    assert value.count("\0") == 3


def test_missing_paths_are_skipped(tmp_path: Path) -> None:
    result = delete_many(
        [str(tmp_path / "missing.bin")], to_recycle=False, use_ifile=False
    )

    assert result == {
        "deleted": [],
        "failed": [],
        "aborted": False,
        "error": 0,
        "fallback": False,
    }


def test_successful_batch_deletes_files(tmp_path: Path, monkeypatch) -> None:
    one = tmp_path / "one.bin"
    two = tmp_path / "two.bin"
    one.write_bytes(b"x")
    two.write_bytes(b"y")

    def fake_shell(struct, paths) -> int:
        for path in paths:
            Path(path).unlink()
        return 0

    monkeypatch.setattr(batch_delete, "_shell_delete", fake_shell)

    result = delete_many([str(one), str(two)], to_recycle=False, use_ifile=False)

    assert result["error"] == 0
    assert sorted(result["deleted"]) == sorted([str(one), str(two)])
    assert result["failed"] == []
    assert not one.exists() and not two.exists()


def test_duplicate_paths_are_passed_once(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "dup.bin"
    target.write_bytes(b"x")
    seen: list[str] = []

    def fake_shell(struct, paths) -> int:
        seen.extend(paths)
        Path(target).unlink()
        return 0

    monkeypatch.setattr(batch_delete, "_shell_delete", fake_shell)

    delete_many([str(target), str(target)], to_recycle=False, use_ifile=False)

    assert len(seen) == 1


def test_failed_paths_are_reported(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "locked.bin"
    target.write_bytes(b"x")

    monkeypatch.setattr(batch_delete, "_shell_delete", lambda struct, paths: 0)

    result = delete_many([str(target)], to_recycle=False, use_ifile=False)

    assert result["deleted"] == []
    assert result["failed"] == [str(target)]
    assert target.exists()


def test_api_failure_falls_back_to_single_removal(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "fallback.bin"
    target.write_bytes(b"x")

    def boom(struct, paths) -> int:
        raise AttributeError("no shell32")

    monkeypatch.setattr(batch_delete, "_shell_delete", boom)

    result = delete_many([str(target)], to_recycle=False, use_ifile=False)

    assert result["fallback"] is True
    assert result["deleted"] == [str(target)]
    assert not target.exists()


def test_recycle_flag_sets_allowundo(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "recycle.bin"
    target.write_bytes(b"x")
    flags: list[int] = []

    def fake_shell(struct, paths) -> int:
        flags.append(int(struct.fFlags))
        return 0

    monkeypatch.setattr(batch_delete, "_shell_delete", fake_shell)

    delete_many([str(target)], to_recycle=True, use_ifile=False)
    delete_many([str(target)], to_recycle=False, use_ifile=False)

    assert flags[0] & batch_delete.FOF_ALLOWUNDO
    assert not flags[1] & batch_delete.FOF_ALLOWUNDO


def test_ifile_failure_falls_back_to_shell(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "fallback.bin"
    target.write_bytes(b"x")

    def boom(paths, to_recycle):
        raise OSError("COM недоступен")

    def fake_shell(struct, paths):
        Path(target).unlink()
        return 0

    monkeypatch.setattr(batch_delete, "_ifile_delete", boom)
    monkeypatch.setattr(batch_delete, "_shell_delete", fake_shell)

    result = delete_many([str(target)], to_recycle=False)

    assert result["deleted"] == [str(target)]
    assert result["error"] == 0


def test_shell_path_never_adds_long_path_prefix(tmp_path: Path) -> None:
    """Префикс \\\\?\\ ломает shell API (DE_INVALIDFILES) — его не должно быть."""
    long_path = tmp_path / ("deep\\" * 60) / "file.bin"

    assert len(str(long_path)) >= 260
    assert batch_delete._shell_path(str(long_path)) == os.path.abspath(str(long_path))
    assert not batch_delete._shell_path(str(long_path)).startswith("\\\\?\\")


@pytest.mark.skipif(sys.platform != "win32", reason="нужен shell API Windows")
def test_long_path_is_deleted_by_real_api(tmp_path: Path) -> None:
    """Регрессия: путь длиннее MAX_PATH должен удаляться реальным API.

    Раньше _shell_path добавлял \\\\?\\-префикс, и оба API возвращали
    DE_INVALIDFILES (124) — файл оставался на месте.
    """
    deep = tmp_path
    for _ in range(60):
        deep = deep / "deep"
    long_path = deep / "file.bin"
    # Создаём через префикс: Python-файловые API без него зависят
    # от системной настройки LongPathsEnabled.
    prefixed = "\\\\?\\" + str(long_path)
    os.makedirs(os.path.dirname(prefixed), exist_ok=True)
    with open(prefixed, "w", encoding="utf-8") as f:
        f.write("x")
    assert len(str(long_path)) >= 260

    result = delete_many([str(long_path)], to_recycle=False)

    assert result["failed"] == []
    assert result["error"] == 0
    assert not os.path.lexists(str(long_path))
