"""Остатки обновления Windows: сами ничего не удаляем, открываем cleanmgr."""
from __future__ import annotations

from pathlib import Path

import pytest

from disk_cleaner_app.cleaners.system import UpdateLeftoversCleaner
from disk_cleaner_app.models.target import LAYER_SYSTEM
from disk_cleaner_app.services.cleaner import CleanEngine

MODULE = "disk_cleaner_app.cleaners.system"


def test_command_target_in_system_layer() -> None:
    cleaner = UpdateLeftoversCleaner()
    assert cleaner.layer == LAYER_SYSTEM
    assert cleaner.is_actionable is True
    # Пути не отдаются движку: удаляет Windows, а не мы.
    assert cleaner.affected_paths() == ()
    assert "Временные файлы" in cleaner.restore_hint


def test_get_size_sums_existing(tmp_path: Path) -> None:
    old = tmp_path / "Windows.old"
    old.mkdir()
    (old / "file.bin").write_text("x" * 77)

    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (old, tmp_path / "$WinREAgent")  # type: ignore[assignment]

    assert cleaner.get_size() == 77


def test_rollback_days_left_counts_from_windows_old(tmp_path: Path, monkeypatch) -> None:
    old = tmp_path / "Windows.old"
    old.mkdir()
    monkeypatch.setattr(MODULE + ".time.time", lambda: old.stat().st_mtime + 3 * 86400)
    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (old,)  # type: ignore[assignment]

    assert cleaner.rollback_days_left() == 7


def test_rollback_days_left_none_without_windows_old(tmp_path: Path) -> None:
    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (tmp_path / "nope",)  # type: ignore[assignment]

    assert cleaner.rollback_days_left() is None


def test_clean_skips_when_nothing_left(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    launched: list[list[str]] = []
    monkeypatch.setattr(MODULE + ".subprocess.Popen", lambda *a, **k: launched.append(a[0]))
    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (tmp_path / "missing",)  # type: ignore[assignment]

    status, detail = cleaner.clean()

    assert status == "SKIP"
    assert launched == []


def test_clean_opens_windows_cleanup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    old = tmp_path / "Windows.old"
    old.mkdir()
    (old / "file.bin").write_text("x" * 10)
    launched: list[list[str]] = []

    class _Proc:
        pass

    def fake_popen(args, **kwargs):
        launched.append(args)
        return _Proc()

    monkeypatch.setattr(MODULE + ".subprocess.Popen", fake_popen)
    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (old,)  # type: ignore[assignment]

    status, detail = cleaner.clean()

    assert status == "OK"
    assert launched and launched[0][0] == "cleanmgr"
    assert "Предыдущие версии" in detail
    # Мы ничего не удалили — папка на месте.
    assert old.exists()


def test_plan_is_command_mode_not_blocked(tmp_path: Path) -> None:
    old = tmp_path / "Windows.old"
    old.mkdir()
    (old / "file.bin").write_text("x" * 100)
    cleaner = UpdateLeftoversCleaner()
    cleaner.paths = (old,)  # type: ignore[assignment]

    plan = CleanEngine().build_plan([cleaner])
    target = plan.targets[0]

    assert target.mode == "command"
    assert not target.blocked
    assert old.joinpath("file.bin").exists()
