"""Точка восстановления Windows перед очисткой (Checkpoint-Computer)."""
from __future__ import annotations

from disk_cleaner_app.cleaners.base import run_powershell
from disk_cleaner_app.services.elevation import is_admin

DEFAULT_DESCRIPTION = "DiskCleaner Pro — перед очисткой"


def create_restore_point(description: str = DEFAULT_DESCRIPTION) -> tuple[bool, str]:
    """Создать точку восстановления системы.

    Возвращает (успех, сообщение). Требует администратора и включённого
    восстановления системы. Windows не даёт создавать точки чаще раза
    в 24 часа — это ограничение ОС, а не ошибка.
    """
    if not is_admin():
        return (False, "Точка восстановления не создана: нужны права администратора")

    # Кавычки внутри PS-строки удваиваем.
    safe_desc = description.replace("'", "''")
    _out, err = run_powershell(
        "$ErrorActionPreference = 'Stop'; "
        f"Checkpoint-Computer -Description '{safe_desc}' "
        "-RestorePointType MODIFY_SETTINGS | Out-Null; 'OK'",
        timeout=300,
    )
    if "OK" in _out:
        return (True, "Точка восстановления создана")

    if err:
        first = err.strip().splitlines()[-1]
        return (False, f"Точка восстановления не создана: {first}")
    return (False, "Точка восстановления не создана: неизвестная ошибка")


def system_restore_available() -> tuple[bool, str]:
    """Проверить, доступно ли создание точек (права + включённость)."""
    if not is_admin():
        return (False, "нет прав администратора")
    out, _err = run_powershell(
        "(Get-CimInstance -ClassName SystemRestore -ErrorAction SilentlyContinue) "
        "| Measure-Object | Select-Object -ExpandProperty Count",
        timeout=60,
    )
    # Существующие точки ещё не гарантируют, что восстановление включено
    # на системном диске, поэтому это только подсказка.
    if out.strip().isdigit() and int(out.strip()) > 0:
        return (True, "восстановление системы активно")
    return (False, "восстановление системы, похоже, отключено")
