"""Тесты выбора дисков и свободного места."""
from __future__ import annotations

import os

from disk_cleaner_app.cleaners import base


def _patch_drives(monkeypatch, roots: list[str], sizes: dict[str, tuple[int, int]]):
    monkeypatch.setattr(os, "listdrives", lambda: list(roots), raising=False)
    monkeypatch.setattr(
        base, "get_disk_free", lambda root=None: sizes.get(root or "", (0, 0))
    )


def test_get_disk_free_bad_root_returns_zero() -> None:
    # Несуществующий корень не должен выбрасывать исключение.
    assert base.get_disk_free("?:\\") == (0, 0)


def test_list_drives_skips_empty_and_keeps_system_first(monkeypatch) -> None:
    _patch_drives(
        monkeypatch,
        ["D:\\", "C:\\", "E:\\"],
        {
            "C:\\": (10, 100),
            "D:\\": (20, 200),
            "E:\\": (0, 0),
        },
    )

    drives = base.list_drives()

    assert drives == [("C:\\", 10, 100), ("D:\\", 20, 200)]


def test_list_drives_orders_others_after_system(monkeypatch) -> None:
    _patch_drives(
        monkeypatch,
        ["X:\\", "C:\\", "Y:\\"],
        {"X:\\": (1, 2), "C:\\": (3, 4), "Y:\\": (5, 6)},
    )

    roots = [root for root, _free, _total in base.list_drives()]

    assert roots[0] == os.environ.get("SystemDrive", "C:") + "\\"
    assert len(roots) == 3


def test_list_drives_returns_empty_when_no_ready_drives(monkeypatch) -> None:
    _patch_drives(monkeypatch, ["A:\\", "B:\\"], {})

    assert base.list_drives() == []
