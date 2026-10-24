"""Проверка и запрос прав администратора (UAC)."""
from __future__ import annotations

import ctypes
import os
import sys

ERROR_CANCELLED = 1223


def is_admin() -> bool:
    """Запущен ли процесс с правами администратора."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def elevation_command() -> tuple[str, str]:
    """Вернуть (exe, arguments) для перезапуска с elevated-правами."""
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    return sys.executable, "-m disk_cleaner_app"


def _shell_execute(exe: str, args: str) -> int:
    """Обёртка ShellExecuteW (отдельно для тестирования)."""
    return int(
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            exe,
            args,
            os.getcwd(),
            1,  # SW_SHOWNORMAL
        )
    )


def request_elevation() -> bool:
    """Показать UAC и запустить копию приложения от администратора.

    Возвращает True, если процесс успешно создан. Пользователь может
    отклонить запрос — тогда возвращается False.
    """
    exe, args = elevation_command()
    try:
        result = _shell_execute(exe, args)
    except (AttributeError, OSError):
        return False
    if result == ERROR_CANCELLED:
        return False
    return result > 32


def elevation_hint() -> str | None:
    """Короткая подсказка для UI."""
    if is_admin():
        return None
    return "Часть системных операций требует прав администратора."
