"""🚀 Автозапуск самого приложения (HKCU Run, только с согласия пользователя).

Запись создаётся в ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
под именем «DiskCleaner Pro» и запускает приложение свёрнутым в трей
(``--tray``). Отключение удаляет запись — она не является системной.
"""
from __future__ import annotations

import sys
import winreg

AUTOSTART_NAME = "DiskCleaner Pro"
_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command() -> str:
    """Команда автозапуска: exe в сборке, ``python -m`` из исходников."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    return f'"{sys.executable}" -m disk_cleaner_app --tray'


def get_autostart(key_path: str = _RUN_KEY_PATH) -> str | None:
    """Текущая команда автозапуска или None, если записи нет."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _type = winreg.QueryValueEx(key, AUTOSTART_NAME)
            return str(value)
    except OSError:
        return None


def set_autostart(enabled: bool, key_path: str = _RUN_KEY_PATH) -> tuple[bool, str]:
    """Включить или выключить автозапуск. Возвращает (успех, сообщение)."""
    try:
        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(
                    key, AUTOSTART_NAME, 0, winreg.REG_SZ, autostart_command()
                )
            return True, "Автозапуск включён (запуск свёрнутым в трей)"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                return True, "Автозапуск и так был выключен"
        return True, "Автозапуск выключен"
    except OSError as e:
        return False, f"Не удалось изменить автозапуск: {e}"
