"""Тесты файловых операций и проброса CleanOptions."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from disk_cleaner_app.cleaners import base
from disk_cleaner_app.cleaners.base import (
    CleanOptions,
    get_dir_size,
    reset_clean_options,
    safe_remove,
    safe_rm_contents,
    safe_rmtree,
    set_clean_options,
)


def test_get_dir_size_counts_nested_files(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "sub" / "b.bin").write_bytes(b"y" * 50)

    assert get_dir_size(tmp_path) == 150


def test_safe_rmtree_removes_tree(tmp_path: Path) -> None:
    target = tmp_path / "cache"
    (target / "nested").mkdir(parents=True)
    (target / "nested" / "file.tmp").write_text("data", encoding="utf-8")

    assert safe_rmtree(target) is True
    assert not target.exists()


def test_safe_rm_contents_keeps_folder(tmp_path: Path) -> None:
    target = tmp_path / "cache"
    (target / "nested").mkdir(parents=True)
    (target / "file.tmp").write_text("data", encoding="utf-8")

    assert safe_rm_contents(target) is True
    assert target.is_dir()
    assert list(target.iterdir()) == []


def test_safe_rmtree_removes_readonly_files(tmp_path: Path) -> None:
    target = tmp_path / "cache"
    target.mkdir()
    readonly = target / "locked.bin"
    readonly.write_bytes(b"data")
    os.chmod(readonly, stat.S_IREAD)

    try:
        assert safe_rmtree(target) is True
        assert not target.exists()
    finally:
        if readonly.exists():
            os.chmod(readonly, stat.S_IWRITE)


def test_options_are_taken_from_context(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    def fake_recycle(path: Path) -> bool:
        calls.append(str(path))
        path.unlink()
        return True

    monkeypatch.setattr(base, "_send_to_recycle", fake_recycle)
    target = tmp_path / "file.tmp"
    target.write_text("data", encoding="utf-8")

    token = set_clean_options(CleanOptions(to_recycle=True))
    try:
        assert safe_remove(target) is True
    finally:
        reset_clean_options(token)

    assert calls == [str(target)]
    assert not target.exists()


def test_explicit_option_overrides_context(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        base, "_send_to_recycle", lambda p: calls.append(str(p)) or True
    )
    target = tmp_path / "file.tmp"
    target.write_text("data", encoding="utf-8")

    token = set_clean_options(CleanOptions(to_recycle=True))
    try:
        # Явный False важнее опций операции: файл удаляется навсегда.
        assert safe_remove(target, False) is True
    finally:
        reset_clean_options(token)

    assert calls == []
    assert not target.exists()
