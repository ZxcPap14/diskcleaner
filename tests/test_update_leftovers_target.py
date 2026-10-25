"""Слой E «остатки обновления Windows»: только показ, движок — SKIP."""
from __future__ import annotations

from pathlib import Path

import pytest

from disk_cleaner_app.cleaners.system import UpdateLeftoversCleaner
from disk_cleaner_app.models.target import LAYER_INVENTORY
from disk_cleaner_app.services.cleaner import CleanEngine

MODULE = "disk_cleaner_app.cleaners.system"


def test_layer_e_and_not_actionable() -> None:
    cleaner = UpdateLeftoversCleaner()
    assert cleaner.layer == LAYER_INVENTORY
    assert cleaner.is_actionable is False
    assert "Параметры" in cleaner.restore_hint


def test_affected_paths_filter_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exists = tmp_path / "Windows.old"
    exists.mkdir()
    missing = tmp_path / "$WINDOWS.~BT"

    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (exists, missing)  # type: ignore[assignment]

    assert cleaner.affected_paths() == (exists,)


def test_get_size_sums_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exists = tmp_path / "Windows.old"
    exists.mkdir()
    (exists / "file.bin").write_text("x" * 77)

    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (exists, tmp_path / "$WinREAgent")  # type: ignore[assignment]

    assert cleaner.get_size() == 77


def test_clean_refuses_to_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    status, detail = UpdateLeftoversCleaner().clean()
    assert status == "SKIP"
    assert "Слой E" in detail


def test_engine_skips_planned_e_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Планировщик блокирует слой E, движок никогда не удаляет его пути."""
    exists = tmp_path / "Windows.old"
    exists.mkdir()
    (exists / "file.bin").write_text("x" * 100)

    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (exists,)  # type: ignore[assignment]

    plan = CleanEngine().build_plan([cleaner])
    target = plan.targets[0]
    assert target.blocked
    assert "Слой E" in target.blocked

    results = CleanEngine().clean_plan(plan)
    assert results[0].status == "SKIP"
    # Файл на месте: слой E ничего не удаляет.
    assert exists.joinpath("file.bin").exists()
