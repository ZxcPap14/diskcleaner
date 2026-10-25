"""Тесты тихой очистки и расписания."""
from __future__ import annotations

from pathlib import Path

import disk_cleaner_app.services.schedule as sched
from disk_cleaner_app.services.auto_clean import run_silent_clean


class _FakeResult:
    def __init__(self, status: str, freed: int) -> None:
        self.status = status
        self.freed = freed
        self.note = ""
        class _C:
            id = "x"
            name = "X"
        self.cleaner = _C()


def test_run_silent_clean_summary_and_history(
    monkeypatch, tmp_path: Path
) -> None:
    import disk_cleaner_app.services.auto_clean as ac
    from disk_cleaner_app.models.config import ConfigManager
    from disk_cleaner_app.models.history import HistoryManager

    calls: dict = {}

    class _Registry:
        def __init__(self, config): pass

        def get_safe(self):
            return ["safe-cleaner"]

    class _Engine:
        def clean_selected(self, cleaners, options=None, progress_callback=None):
            calls["options"] = options
            return [_FakeResult("OK", 100), _FakeResult("OK", 50),
                    _FakeResult("ERR", 0)]

    db = tmp_path / "h.db"
    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.registry.CleanerRegistry", _Registry
    )
    monkeypatch.setattr(ac, "CleanEngine", _Engine)
    monkeypatch.setattr(ac, "HistoryManager", lambda: HistoryManager(db_path=db))

    config = ConfigManager()
    summary = run_silent_clean(config=config, to_recycle=True)

    assert summary["targets"] == 1
    assert summary["ok"] == 2
    assert summary["failed"] == 1
    assert summary["freed"] == 150
    assert summary["mode"] == "smart"
    assert summary["skipped"] == 0
    assert calls["options"].to_recycle is True
    entry = HistoryManager(db_path=db).get_last()
    assert entry is not None and entry["op_type"] == "smart"


def test_schedule_install_and_query(monkeypatch) -> None:
    commands: list[str] = []

    def fake_cmd(command: str, timeout: int = 60) -> tuple[str, str]:
        commands.append(command)
        if "/Create" in command:
            return ("УСПЕШНО: создана задача.", "")
        if "/Query" in command:
            return ('DiskCleanerPro_SmartClean  09:00  Ready', "")
        return ("", "")

    monkeypatch.setattr(sched, "run_cmd", fake_cmd)

    ok, message = sched.install_schedule(day="SUN", at="09:00")

    assert ok is True
    assert any("/SC WEEKLY /D SUN /ST 09:00" in c for c in commands)
    assert "--smart-clean --silent" in commands[0]
    assert sched.schedule_exists() is True


def test_schedule_uninstall_reports_error(monkeypatch) -> None:
    monkeypatch.setattr(sched, "run_cmd", lambda c, timeout=60: ("", "ОШИБКА"))
    ok, message = sched.uninstall_schedule()
    assert ok is False and "ОШИБКА" in message
