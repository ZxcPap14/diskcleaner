"""Тесты менеджеров служб и заданий планировщика."""
from __future__ import annotations

import json
from pathlib import Path

import disk_cleaner_app.services.startup_services as ss

# ── службы ─────────────────────────────────────────────

def _svc_json() -> str:
    return json.dumps([
        {"Name": "Spooler", "DisplayName": "Print Spooler",
         "StartMode": "Auto", "State": "Running", "PathName": "spoolsv.exe"},
        {"Name": "DisabledSvc", "DisplayName": "Disabled One",
         "StartMode": "Disabled", "State": "Stopped", "PathName": ""},
    ])


def test_services_list(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ss, "run_powershell", lambda s, timeout=60: (_svc_json(), "")
    )
    manager = ss.ServicesManager(backup_file=tmp_path / "b.json")

    items = manager.get_all()

    assert [i["service_name"] for i in items] == ["Spooler", "DisabledSvc"]
    assert items[0]["enabled"] is True
    assert items[1]["enabled"] is False
    assert items[0]["source"] == "Службы"


def test_services_disable_saves_backup_and_verifies(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    def fake_ps(script: str, timeout: int = 60) -> tuple[str, str]:
        calls.append(script)
        if "Win32_Service -Filter" in script:
            return ("Disabled", "")
        return ("", "")

    def fake_cmd(command: str, timeout: int = 60) -> tuple[str, str]:
        calls.append(command)
        return ("", "")

    monkeypatch.setattr(ss, "run_powershell", fake_ps)
    monkeypatch.setattr(ss, "run_cmd", fake_cmd)
    backup = tmp_path / "b.json"
    manager = ss.ServicesManager(backup_file=backup)

    ok = manager.disable_item({
        "service_name": "Spooler", "start_mode": "Auto",
    })

    assert ok is True
    assert any('sc config "Spooler" start= disabled' in c for c in calls)
    data = json.loads(backup.read_text(encoding="utf-8"))
    assert data == [{"name": "spooler", "start_mode": "Auto"}]


def test_services_disable_rolls_back_backup_on_failure(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_ps(script: str, timeout: int = 60) -> tuple[str, str]:
        if "Win32_Service -Filter" in script:
            return ("Auto", "")  # режим не изменился — отключение не прошло
        return ("", "")

    monkeypatch.setattr(ss, "run_powershell", fake_ps)
    monkeypatch.setattr(ss, "run_cmd", lambda c, timeout=60: ("", ""))
    backup = tmp_path / "b.json"
    manager = ss.ServicesManager(backup_file=backup)

    ok = manager.disable_item({"service_name": "Svc", "start_mode": "Auto"})

    assert ok is False
    assert "администратора" in manager.last_error
    assert json.loads(backup.read_text(encoding="utf-8")) == []


def test_services_enable_restores_original_mode(
    monkeypatch, tmp_path: Path
) -> None:
    commands: list[str] = []

    def fake_ps(script: str, timeout: int = 60) -> tuple[str, str]:
        if "Win32_Service -Filter" in script:
            return ("Manual", "")
        return ("", "")

    monkeypatch.setattr(ss, "run_powershell", fake_ps)
    monkeypatch.setattr(
        ss, "run_cmd",
        lambda c, timeout=60: (commands.append(c) or ("", "")),
    )
    backup = tmp_path / "b.json"
    backup.write_text(
        json.dumps([{"name": "Svc", "start_mode": "Manual"}]),
        encoding="utf-8",
    )
    manager = ss.ServicesManager(backup_file=backup)

    ok = manager.enable_item({"service_name": "Svc"})

    assert ok is True
    assert any('sc config "Svc" start= demand' in c for c in commands)
    # Бэкап удалён после успешного восстановления.
    assert json.loads(backup.read_text(encoding="utf-8")) == []


# ── задания планировщика ──────────────────────────────

def test_tasks_parse_csv(monkeypatch) -> None:
    csv_text = (
        '"\\Microsoft\\Windows\\UpdateOrchestrator\\USO_NB","01.11.2026 10:00","Ready"\n'
        '"\\MyTask","","Disabled"\n'
        '"","",""\n'
    )
    monkeypatch.setattr(ss, "run_cmd", lambda c, timeout=60: (csv_text, ""))

    items = ss.ScheduledTasksManager().get_all()

    assert len(items) == 2
    assert items[0]["enabled"] is True  # Ready идёт первым после сортировки
    assert items[1]["enabled"] is False
    assert items[1]["name"] == "MyTask"
    assert items[0]["source"] == "Планировщик"


def test_tasks_disable_and_enable(monkeypatch) -> None:
    commands: list[str] = []

    def fake_cmd(command: str, timeout: int = 60) -> tuple[str, str]:
        commands.append(command)
        return ("УСПЕШНО: ...", "")

    monkeypatch.setattr(ss, "run_cmd", fake_cmd)
    manager = ss.ScheduledTasksManager()
    item = {"task_name": "\\MyTask"}

    assert manager.disable_item(item) is True
    assert manager.enable_item(item) is True
    assert commands[0].endswith("/DISABLE")
    assert commands[1].endswith("/ENABLE")


def test_tasks_error_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(ss, "run_cmd", lambda c, timeout=60: ("", "ОШИБКА"))
    manager = ss.ScheduledTasksManager()

    assert manager.disable_item({"task_name": "\\X"}) is False
    assert manager.last_error
