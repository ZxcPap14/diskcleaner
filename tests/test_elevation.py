"""Тесты проверки и запроса прав администратора (без реального UAC)."""
from __future__ import annotations

import sys
from pathlib import Path

from disk_cleaner_app.services import elevation


def test_is_admin_returns_bool() -> None:
    assert isinstance(elevation.is_admin(), bool)


def test_elevation_command_points_to_current_interpreter() -> None:
    exe, args = elevation.elevation_command()

    assert Path(exe).exists()
    if getattr(sys, "frozen", False):
        assert args == ""
    else:
        assert "-m disk_cleaner_app" in args


def test_request_elevation_success(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_execute(exe: str, args: str) -> int:
        calls.append((exe, args))
        return 33  # > 32 — успех по документации ShellExecute

    monkeypatch.setattr(elevation, "_shell_execute", fake_execute)

    assert elevation.request_elevation() is True
    assert len(calls) == 1


def test_request_elevation_cancelled(monkeypatch) -> None:
    monkeypatch.setattr(elevation, "_shell_execute", lambda exe, args: 1223)
    assert elevation.request_elevation() is False


def test_request_elevation_os_error(monkeypatch) -> None:
    def boom(exe: str, args: str) -> int:
        raise OSError("denied")

    monkeypatch.setattr(elevation, "_shell_execute", boom)
    assert elevation.request_elevation() is False


def test_hint_only_for_non_admin(monkeypatch) -> None:
    monkeypatch.setattr(elevation, "is_admin", lambda: True)
    assert elevation.elevation_hint() is None

    monkeypatch.setattr(elevation, "is_admin", lambda: False)
    assert "администратора" in elevation.elevation_hint()
