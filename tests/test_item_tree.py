"""Тесты логики групповых чекбоксов (без Tk)."""
from __future__ import annotations

from types import SimpleNamespace

from disk_cleaner_app.ui.components.item_tree import CleanerTree


def _mark(states: dict[str, bool], ids: list[str]) -> str:
    dummy = SimpleNamespace(_checked=states)
    return CleanerTree._group_mark(dummy, ids)


def test_group_mark_all_checked() -> None:
    assert _mark({"a": True, "b": True}, ["a", "b"]) == "☑"


def test_group_mark_none_checked() -> None:
    assert _mark({"a": False, "b": False}, ["a", "b"]) == "☐"


def test_group_mark_partial() -> None:
    assert _mark({"a": True, "b": False}, ["a", "b"]) == "▣"


def test_group_mark_empty_group() -> None:
    assert _mark({}, []) == "☐"


def _title(collapsed: set[str]) -> str:
    dummy = SimpleNamespace(_collapsed=collapsed)
    return CleanerTree._group_title(dummy, "🖥️ Система", 3)


def test_group_title_expanded() -> None:
    assert _title(set()) == "▼ 🖥️ Система  (3)"


def test_group_title_collapsed() -> None:
    assert _title({"🖥️ Система"}) == "▶ 🖥️ Система  (3)"
