"""Агрегация причин ошибок в результате движка (5B-1)."""
from __future__ import annotations

import pytest

from disk_cleaner_app.cleaners.base import BaseCleaner
from disk_cleaner_app.models.item import GROUP_SYSTEM
from disk_cleaner_app.services.cleaner import CleanEngine

MODULE = "disk_cleaner_app.services.cleaner"


class _PathsCleaner(BaseCleaner):
    id = "stroke_cache"
    name = "🧪 Тестовая цель"
    group = GROUP_SYSTEM

    def __init__(self, path) -> None:
        super().__init__()
        self.paths = (path,)  # type: ignore[assignment]

    def get_size(self) -> int:
        return 2 * 1024 * 1024  # 2 МБ, чтобы сработала эвристика ERR

    def clean(self) -> tuple[str, str]:
        return "OK", ""


def _note_for_kinds(kinds: dict[str, int]) -> str:
    _status, note = CleanEngine._analyze(
        status="ERR",
        planned=2 * 1024 * 1024,
        freed=0,
        remaining=2 * 1024 * 1024,
        recycled=False,
        removed=0,
        errors=["p1", "p2", "p3"],
        mode="paths",
        kinds=kinds,
    )
    return note


def test_analyze_mentions_reasons_and_advice() -> None:
    note = _note_for_kinds({"locked": 2, "access_denied": 1})
    assert "Причины: занято другим процессом 2, отказ в доступе 1" in note
    assert "закройте" in note.lower()


def test_analyze_without_kinds_keeps_old_text() -> None:
    note = _note_for_kinds({})
    assert "Не удалось удалить объектов: 3." in note
    assert "Причины" not in note


def test_result_carries_error_kinds(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Движок прокидывает диагностику ошибок в CleanResult."""
    target = tmp_path / "locked.bin"
    target.write_text("x")
    cleaner = _PathsCleaner(target)
    engine = CleanEngine()

    def fake_delete_many(paths, to_recycle=True):
        # Имитация: один объект остался занят.
        return {"deleted": [], "failed": [str(target)], "aborted": False}

    monkeypatch.setattr(MODULE + ".delete_many", fake_delete_many)
    monkeypatch.setattr(
        "disk_cleaner_app.services.error_kinds.classify_paths",
        lambda paths: {"locked": len(paths)},
    )

    plan = engine.build_plan([cleaner])
    (result,) = engine.clean_plan(plan)

    assert result.errors == [str(target)]
    assert result.error_kinds == {"locked": 1}
