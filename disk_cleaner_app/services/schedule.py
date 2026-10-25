"""Регистрация еженедельной тихой очистки в планировщике Windows."""
from __future__ import annotations

import sys

from disk_cleaner_app.cleaners.base import run_cmd

TASK_NAME = "DiskCleanerPro_SmartClean"


def _command_line() -> str:
    """Команда запуска тихой очистки для планировщика.

    Режим берётся из настройки ``schedule_mode`` на момент установки
    задания: ``smart`` (Smart Clean) или ``deep-safe`` (слой A).
    """
    from disk_cleaner_app.models.config import ConfigManager

    try:
        mode = str(ConfigManager().get("schedule_mode", "smart"))
    except Exception:
        mode = "smart"
    flags = "--smart-clean --silent"
    if mode == "deep-safe":
        flags = "--smart-clean --deep-safe --silent"
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {flags}'
    entry = sys.argv[0]
    return f'"{sys.executable}" "{entry}" {flags}'


def install_schedule(day: str = "SUN", at: str = "09:00") -> tuple[bool, str]:
    """Создать/обновить задание «каждую неделю». Требует администратора."""
    out, err = run_cmd(
        f'schtasks /Create /F /TN "{TASK_NAME}" '
        f'/TR "{_command_line()}" /SC WEEKLY /D {day} /ST {at}',
        timeout=30,
    )
    text = f"{out} {err}"
    if "SUCCESS" in text.upper() or "УСПЕШНО" in text.upper():
        return (True, f"Задание создано: каждую неделю ({day} {at})")
    return (False, f"schtasks: {err or out or 'неизвестная ошибка'}")


def uninstall_schedule() -> tuple[bool, str]:
    out, err = run_cmd(f'schtasks /Delete /F /TN "{TASK_NAME}"', timeout=30)
    text = f"{out} {err}"
    if "SUCCESS" in text.upper() or "УСПЕШНО" in text.upper():
        return (True, "Задание удалено")
    return (False, f"schtasks: {err or out or 'неизвестная ошибка'}")


def schedule_exists() -> bool:
    out, err = run_cmd(f'schtasks /Query /TN "{TASK_NAME}"', timeout=30)
    return not err.strip() and TASK_NAME in out
