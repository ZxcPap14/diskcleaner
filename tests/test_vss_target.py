"""Цель VSS: UsedSpace, «оставить самую новую», коды PowerShell."""
from __future__ import annotations

import pytest

from disk_cleaner_app.cleaners.system import VssCleanupCleaner

MODULE = "disk_cleaner_app.cleaners.system"


def test_get_size_sums_used_space(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        MODULE + ".run_powershell",
        lambda script, timeout=60: ("1024\n2048\n\nbad\n", ""),
    )
    assert VssCleanupCleaner().get_size() == 3072


def test_get_size_zero_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        MODULE + ".run_powershell", lambda script, timeout=60: ("", "failed")
    )
    assert VssCleanupCleaner().get_size() == 0


def test_clean_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: False)
    status, detail = VssCleanupCleaner().clean()
    assert status == "ERR"
    assert "администратора" in detail


def test_clean_keeps_newest_per_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    """Самая новая точка сохраняется: скрипт сортирует от новой к старым
    и удаляет только повторные (старые) на каждом томе."""
    captured: dict[str, str] = {}

    def fake_ps(script: str, timeout: int = 60) -> tuple[str, str]:
        captured["script"] = script
        return ("REMOVED:2", "")

    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(MODULE + ".run_powershell", fake_ps)
    status, detail = VssCleanupCleaner().clean()

    script = captured["script"]
    assert "Sort-Object InstallDate -Descending" in script
    assert "Win32_ShadowCopy" in script
    assert "Remove-CimInstance" in script
    assert "ContainsKey" in script          # первый (новейший) том —.skip
    assert "InstanceId $s.InstanceId" in script
    assert status == "OK"
    assert "2" in detail
    assert "сохранена" in detail


def test_clean_skip_without_shadow_copies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(
        MODULE + ".run_powershell", lambda script, timeout=60: ("REMOVED:0", "")
    )
    status, _detail = VssCleanupCleaner().clean()
    assert status == "SKIP"


def test_clean_powershell_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(
        MODULE + ".run_powershell",
        lambda script, timeout=60: ("", "Get-CimInstance: not found"),
    )
    status, detail = VssCleanupCleaner().clean()
    assert status == "ERR"
    assert "Get-CimInstance" in detail


def test_clean_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(
        MODULE + ".run_powershell", lambda script, timeout=60: ("", "TIMEOUT")
    )
    status, detail = VssCleanupCleaner().clean()
    assert status == "ERR"
    assert "5 минут" in detail
