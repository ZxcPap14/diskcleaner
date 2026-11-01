"""Тесты безвозвратного стирания: перезапись, папки, ссылки."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from disk_cleaner_app.services import batch_delete, shred


def test_shred_file_overwrites_before_deleting(tmp_path: Path) -> None:
    """Жёсткая ссылка видит тот же файл: после стирания в ней нули."""
    original = tmp_path / "secret.txt"
    original.write_bytes(b"TOP-SECRET" * 100)
    copy = tmp_path / "peer.bin"
    os.link(original, copy)

    assert shred.shred_file(original) is True
    assert not original.exists()
    assert copy.read_bytes() == b"\0" * len(b"TOP-SECRET" * 100)


def test_shred_file_handles_readonly(tmp_path: Path) -> None:
    target = tmp_path / "locked.log"
    target.write_bytes(b"data")
    os.chmod(target, stat.S_IREAD)

    assert shred.shred_file(target) is True
    assert not target.exists()


def test_shred_tree_removes_files_and_folders(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    (root / "sub").mkdir(parents=True)
    (root / "a.bin").write_bytes(b"a" * 10)
    (root / "sub" / "b.bin").write_bytes(b"b" * 10)

    result = shred.shred_many([str(root)])

    assert result["deleted"] == [str(root)]
    assert not root.exists()


def test_shred_many_reports_missing_paths(tmp_path: Path) -> None:
    missing = tmp_path / "gone.txt"

    result = shred.shred_many([str(missing)])

    assert result["failed"] == [str(missing)]
    assert result["deleted"] == []


def test_shred_skips_links(tmp_path: Path) -> None:
    """Ссылка не должна уводить стирание за пределы выбранного пути."""
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep me")
    link = tmp_path / "link.txt"
    try:
        os.symlink(outside, link)
    except OSError:
        import pytest

        pytest.skip("символические ссылки недоступны без прав")

    assert shred.shred_file(link) is False
    assert outside.read_bytes() == b"keep me"


def test_delete_many_shred_mode_uses_shred(tmp_path: Path, monkeypatch) -> None:
    """batch_delete с shred=True не зовёт оболочку, а стирает файлы."""
    target = tmp_path / "tmp.bin"
    target.write_bytes(b"x" * 4)
    called: list[str] = []
    monkeypatch.setattr(batch_delete, "_ifile_delete",
                        lambda *a, **k: called.append("ifile") or True)

    result = batch_delete.delete_many([str(target)], shred=True)

    assert result["deleted"] == [str(target)]
    assert called == []
    assert not target.exists()
