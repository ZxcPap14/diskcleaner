"""Слой D: пустые папки и битые ярлыки — поиск, возраст, корзина."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from disk_cleaner_app.cleaners.leftovers import (
    BrokenShortcutsCleaner,
    EmptyFoldersCleaner,
    broken_shortcuts,
    empty_folders,
)

MODULE = "disk_cleaner_app.cleaners.leftovers"


def _age(path: Path, days: int) -> None:
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))


def test_empty_folders_skip_root_and_non_empty(tmp_path: Path) -> None:
    root = tmp_path / "Downloads"
    root.mkdir()
    old_empty = root / "old"
    old_empty.mkdir()
    _age(old_empty, 40)
    fresh_empty = root / "fresh"
    fresh_empty.mkdir()
    busy = root / "busy"
    busy.mkdir()
    (busy / "file.txt").write_text("x")
    _age(busy, 40)

    found = empty_folders((root,), max_age_hours=24 * 30)

    assert found == [old_empty]


def test_empty_folders_respects_depth(tmp_path: Path) -> None:
    root = tmp_path / "Downloads"
    deep = root
    for index in range(8):
        deep = deep / f"level{index}"
    deep.mkdir(parents=True)
    _age(deep, 90)

    assert empty_folders((root,), max_age_hours=24 * 30) == []


def test_empty_folders_cleaner_metadata(tmp_path: Path, monkeypatch) -> None:
    personal = tmp_path / "Documents"
    personal.mkdir()
    empty = personal / "temp"
    empty.mkdir()
    _age(empty, 60)
    monkeypatch.setattr(MODULE + ".USER", tmp_path)
    monkeypatch.setattr(MODULE + ".PERSONAL_DIRS", ("Documents",))

    cleaner = EmptyFoldersCleaner()

    assert cleaner.layer == "D"
    assert cleaner.affected_paths() == (empty,)


def test_broken_shortcuts_parses_powershell_output(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "Desktop"
    folder.mkdir()
    link = folder / "Сломанный.lnk"
    link.write_text("x")
    monkeypatch.setattr(
        MODULE + ".run_powershell",
        lambda script, timeout=120: (
            f"{link}\n\nC:\\Windows\\System32\\cmd.exe\n", "",
        ),
    )

    assert broken_shortcuts((folder,)) == [link]


def test_broken_shortcuts_without_dirs_does_not_run_powershell(monkeypatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        MODULE + ".run_powershell",
        lambda script, timeout=120: called.append("x") or ("", ""),
    )

    assert broken_shortcuts((Path("C:/definitely-not-here"),)) == []
    assert called == []


def test_broken_shortcuts_cleaner_recycles(tmp_path: Path, monkeypatch) -> None:
    link = tmp_path / "broken.lnk"
    link.write_text("x")
    monkeypatch.setattr(BrokenShortcutsCleaner, "_links", lambda self: [link])
    recycled: list[bool] = []
    monkeypatch.setattr(
        "disk_cleaner_app.services.batch_delete.delete_many",
        lambda paths, to_recycle=False: (
            recycled.append(to_recycle) or {"deleted": paths, "failed": []}
        ),
    )

    status, detail = BrokenShortcutsCleaner().clean()

    assert status == "OK"
    assert recycled == [True]
    assert "1" in detail


def test_shortcuts_older_than_a_day(tmp_path: Path) -> None:
    assert BrokenShortcutsCleaner().min_age_hours == 24
    assert "Пуск" in BrokenShortcutsCleaner().description


@pytest.mark.parametrize("folders", [(), (Path("C:/nope"),)])
def test_empty_folders_no_roots(tmp_path: Path, folders: tuple) -> None:
    assert empty_folders(folders, max_age_hours=1) == []
