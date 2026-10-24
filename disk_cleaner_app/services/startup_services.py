"""Службы Windows и задания планировщика в списке автозагрузки.

Службы: перечисление через Get-CimInstance Win32_Service, отключение через
``sc config <имя> start= disabled`` с сохранением исходного типа запуска
в ``services_backup.json`` (обратимо, как у записей реестра).

Задания планировщика: ``schtasks /query`` только для чтения; отключение
и включение — штатными ``schtasks /Change /DISABLE|/ENABLE``, состояние
хранит сама ОС, дополнительный бэкап не нужен.
"""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import Any

from disk_cleaner_app.cleaners.base import run_cmd, run_powershell
from disk_cleaner_app.models.config import CONFIG_DIR

# StartMode Win32_Service -> аргумент ``start=`` для sc config.
_START_MODE_TO_SC = {
    "Auto": "auto",
    "Manual": "demand",
    "Disabled": "disabled",
}


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class ServicesManager:
    """Чтение, обратимое отключение и восстановление служб Windows."""

    def __init__(self, backup_file: Path | None = None) -> None:
        self._backup_file = backup_file or (CONFIG_DIR / "services_backup.json")
        self.last_error = ""

    # ── чтение ───────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """Все службы: имя, отображаемое имя, тип запуска, состояние, путь."""
        out, err = run_powershell(
            "Get-CimInstance Win32_Service | "
            "Select-Object Name,DisplayName,StartMode,State,PathName | "
            "ConvertTo-Json -Compress",
            timeout=120,
        )
        if err or not out:
            self.last_error = (
                f"Не удалось получить список служб: {err or 'пустой ответ'}"
            )
            return []
        try:
            data = json.loads(out)
        except ValueError:
            self.last_error = "Не удалось разобрать ответ Get-CimInstance"
            return []
        if isinstance(data, dict):
            data = [data]

        backups = self._load_backups()
        items: list[dict] = []
        for svc in data:
            if not isinstance(svc, dict):
                continue
            name = str(svc.get("Name", "")).strip()
            if not name:
                continue
            start_mode = str(svc.get("StartMode", "")).strip()
            backup = backups.get(name.lower())
            # Служба «отключена нами», если её исходный тип сохранён
            # и сейчас она стоит как Disabled.
            disabled_by_us = bool(backup and start_mode == "Disabled")
            items.append({
                "id": f"service:{name}",
                "kind": "service",
                "name": str(svc.get("DisplayName") or name),
                "service_name": name,
                "enabled": start_mode != "Disabled",
                "disabled_by_us": disabled_by_us,
                "start_mode": start_mode,
                "state": str(svc.get("State", "")),
                "command": str(svc.get("PathName") or ""),
                "source": "Службы",
            })
        items.sort(key=lambda i: (not i["enabled"], i["name"].lower()))
        return items

    # ── отключение / восстановление ─────────────────────

    def disable_item(self, item: dict) -> bool:
        name = str(item.get("service_name", ""))
        start_mode = str(item.get("start_mode", "Auto")) or "Auto"
        if not name:
            self.last_error = "Неизвестное имя службы."
            return False

        self._save_backup(name, start_mode)
        run_cmd(f'sc config "{name}" start= disabled', timeout=30)
        # Проверяем фактический результат, а не вывод sc.
        if not self._start_mode_is(name, "Disabled"):
            self._drop_backup(name)
            self.last_error = (
                "Не удалось отключить службу (нужны права администратора?)."
            )
            return False
        return True

    def enable_item(self, item: dict) -> bool:
        name = str(item.get("service_name", ""))
        if not name:
            self.last_error = "Неизвестное имя службы."
            return False

        backups = self._load_backups()
        original = backups.get(name.lower(), "Auto")
        sc_mode = _START_MODE_TO_SC.get(original, "auto")
        run_cmd(f'sc config "{name}" start= {sc_mode}', timeout=30)
        if not self._start_mode_is(name, original):
            self.last_error = "Не удалось восстановить тип запуска службы."
            return False
        self._drop_backup(name)
        return True

    def _start_mode_is(self, name: str, expected: str) -> bool:
        out, _err = run_powershell(
            "(Get-CimInstance Win32_Service -Filter "
            f'"Name={_ps_quote(name)}").StartMode',
            timeout=30,
        )
        return out.strip().lower() == expected.strip().lower()

    # ── резервные копии ──────────────────────────────────

    def _load_backups(self) -> dict[str, str]:
        try:
            data = json.loads(self._backup_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, list):
            return {}
        return {
            str(e.get("name", "")).lower(): str(e.get("start_mode", "Auto"))
            for e in data
            if isinstance(e, dict) and e.get("name")
        }

    def _save_backup(self, name: str, start_mode: str) -> None:
        backups = self._load_backups()
        backups[name.lower()] = start_mode
        self._write_backups(backups)

    def _drop_backup(self, name: str) -> None:
        backups = self._load_backups()
        backups.pop(name.lower(), None)
        self._write_backups(backups)

    def _write_backups(self, backups: dict[str, str]) -> None:
        payload: list[dict[str, Any]] = [
            {"name": n, "start_mode": m} for n, m in sorted(backups.items())
        ]
        tmp = self._backup_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._backup_file)


class ScheduledTasksManager:
    """Задания планировщика: чтение и обратимое вкл/выкл через schtasks."""

    def __init__(self) -> None:
        self.last_error = ""

    def get_all(self) -> list[dict]:
        out, err = run_cmd(
            "schtasks /query /fo csv /nh", timeout=120
        )
        if err and not out:
            self.last_error = f"Не удалось получить список задач: {err}"
            return []

        items: list[dict] = []
        reader = csv.reader(io.StringIO(out))
        for row in reader:
            if len(row) < 3 or not row[0].strip():
                continue
            task_name = row[0].strip()
            status = row[2].strip()
            items.append({
                "id": f"task:{task_name}",
                "kind": "task",
                "name": task_name.lstrip("\\"),
                "task_name": task_name,
                "enabled": status.lower() != "disabled",
                "status_text": status,
                "command": row[1].strip() if len(row) > 1 else "",
                "source": "Планировщик",
            })
        items.sort(key=lambda i: (not i["enabled"], i["name"].lower()))
        return items

    def disable_item(self, item: dict) -> bool:
        return self._change(item, "/DISABLE", "отключить")

    def enable_item(self, item: dict) -> bool:
        return self._change(item, "/ENABLE", "включить")

    def _change(self, item: dict, flag: str, verb: str) -> bool:
        task_name = str(item.get("task_name", ""))
        if not task_name:
            self.last_error = "Неизвестное имя задачи."
            return False
        out, err = run_cmd(
            f'schtasks /Change /TN "{task_name}" {flag}', timeout=30
        )
        if err and "SUCCESS" not in out.upper() and "УСПЕШНО" not in out.upper():
            self.last_error = f"Не удалось {verb} задачу: {err or out}"
            return False
        return True
