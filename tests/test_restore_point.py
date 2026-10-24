"""Тесты сервиса точки восстановления."""
from __future__ import annotations

import pytest

import disk_cleaner_app.services.restore_point as rp


def test_restore_point_needs_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rp, "is_admin", lambda: False)

    ok, message = rp.create_restore_point()

    assert ok is False
    assert "администратора" in message


def test_restore_point_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rp, "is_admin", lambda: True)
    monkeypatch.setattr(rp, "run_powershell", lambda script, timeout=60: ("OK", ""))

    ok, message = rp.create_restore_point()

    assert ok is True
    assert "создана" in message


def test_restore_point_reports_powershell_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rp, "is_admin", lambda: True)
    monkeypatch.setattr(
        rp, "run_powershell",
        lambda script, timeout=60: ("", "Some line\nService unavailable"),
    )

    ok, message = rp.create_restore_point()

    assert ok is False
    assert "Service unavailable" in message


def test_description_single_quotes_are_escaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    def fake_ps(script: str, timeout: int = 60) -> tuple[str, str]:
        seen["script"] = script
        return ("OK", "")

    monkeypatch.setattr(rp, "is_admin", lambda: True)
    monkeypatch.setattr(rp, "run_powershell", fake_ps)

    rp.create_restore_point("it's a test")

    assert "''it''s a test''" in seen["script"] or "it''s a test" in seen["script"]


def test_availability_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rp, "is_admin", lambda: False)
    assert rp.system_restore_available() == (False, "нет прав администратора")

    monkeypatch.setattr(rp, "is_admin", lambda: True)
    monkeypatch.setattr(
        rp, "run_powershell", lambda script, timeout=60: ("2", "")
    )
    assert rp.system_restore_available()[0] is True

    monkeypatch.setattr(
        rp, "run_powershell", lambda script, timeout=60: ("0", "")
    )
    assert rp.system_restore_available()[0] is False
