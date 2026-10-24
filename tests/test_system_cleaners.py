"""Тесты поведения отдельных системных очистителей."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from disk_cleaner_app.cleaners import system
from disk_cleaner_app.cleaners.system import (
    FontCacheCleaner,
    MemoryDumpsCleaner,
    WindowsUpdateCacheCleaner,
)


def test_font_cache_is_user_scope_and_needs_no_admin() -> None:
    """Регрессия: путь в профиле пользователя зря требовал администратора."""
    assert FontCacheCleaner.admin_required is False


def test_memory_dumps_reports_failure_on_locked_file(
    tmp_path: Path, monkeypatch
) -> None:
    """Регрессия: clean() всегда возвращал OK, даже когда unlink падал."""
    locked = tmp_path / "MEMORY.DMP"
    locked.write_bytes(b"x")
    os.chmod(locked, stat.S_IREAD)
    cleaner = MemoryDumpsCleaner()
    monkeypatch.setattr(cleaner, "paths", (locked,))

    try:
        status, detail = cleaner.clean()
    finally:
        os.chmod(locked, stat.S_IWRITE)

    assert status == "ERR"
    assert locked.exists()


def test_wu_cleaner_reports_unrestored_services(monkeypatch) -> None:
    """Регрессия: exit-код PowerShell терялся, провал рестарта служб
    выглядел как успех."""
    monkeypatch.setattr(system, "is_admin", lambda: True)
    monkeypatch.setattr(
        system, "run_powershell",
        lambda script, timeout=60: ("SVC_DOWN: wuauserv,bits", ""),
    )

    status, detail = WindowsUpdateCacheCleaner().clean()

    assert status == "ERR"
    assert "не восстановлены" in detail


def test_wu_cleaner_ok_when_services_restored(monkeypatch) -> None:
    monkeypatch.setattr(system, "is_admin", lambda: True)
    monkeypatch.setattr(
        system, "run_powershell", lambda script, timeout=60: ("OK", "")
    )

    status, detail = WindowsUpdateCacheCleaner().clean()

    assert status == "OK"


def test_wu_cleaner_rejects_unexpected_output(monkeypatch) -> None:
    monkeypatch.setattr(system, "is_admin", lambda: True)
    monkeypatch.setattr(
        system, "run_powershell", lambda script, timeout=60: ("", "")
    )

    status, _detail = WindowsUpdateCacheCleaner().clean()

    assert status == "ERR"
