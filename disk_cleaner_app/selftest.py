"""Самопроверка сборки: `DiskCleaner.exe --self-test`.

Проверяет то, что чаще всего ломается при переносе exe на другой ПК:
встроенный Python/Tk, импорт зависимостей, запись в `%APPDATA%`, SQLite
и доступность PowerShell. Результат пишется в JSON, потому что у сборки
нет консоли; код возврата — 0, если все критичные проверки прошли.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
import tkinter
from collections.abc import Callable
from pathlib import Path


def _check(name: str, func: Callable[[], str], *, critical: bool = True) -> dict:
    try:
        detail = func()
    except Exception as exc:  # noqa: BLE001 - отчёт должен пережить любую ошибку
        return {
            "ok": False,
            "critical": critical,
            "detail": f"{type(exc).__name__}: {exc}",
        }
    return {"ok": True, "critical": critical, "detail": detail}


def _check_tk() -> str:
    root = tkinter.Tk()
    try:
        root.withdraw()
        root.update_idletasks()
        return f"Tk {tkinter.TkVersion}"
    finally:
        root.destroy()


def _check_imports() -> str:
    import customtkinter
    import squarify  # noqa: F401

    from disk_cleaner_app.services import planner  # noqa: F401
    from disk_cleaner_app.ui import app  # noqa: F401

    return f"customtkinter {customtkinter.__version__}, squarify ok"


def _check_sqlite() -> str:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE probe (value INTEGER)")
        connection.execute("INSERT INTO probe VALUES (1)")
        return f"SQLite {sqlite3.sqlite_version}"
    finally:
        connection.close()


def _check_config_write() -> str:
    from disk_cleaner_app.models.config import CONFIG_DIR

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    probe = CONFIG_DIR / ".selftest-probe"
    probe.write_text("ok", encoding="utf-8")
    if probe.read_text(encoding="utf-8") != "ok":
        raise OSError("файл прочитан с другим содержимым")
    probe.unlink()
    return str(CONFIG_DIR)


def _check_temp_write() -> str:
    directory = Path(tempfile.gettempdir())
    if not directory.is_dir():
        raise OSError("временный каталог недоступен")
    probe = directory / ".diskcleaner-selftest"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return str(directory)


def _check_powershell() -> str:
    executable = shutil.which("powershell")
    if not executable:
        raise OSError("powershell.exe не найден в PATH")
    return executable


def _check_admin() -> str:
    import ctypes

    elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
    return "администратор" if elevated else "обычный пользователь"


def _check_tray() -> str:
    from disk_cleaner_app.services.tray_icon import tray_available

    return "pystray + Pillow ok" if tray_available() else "pystray недоступен"


def collect_checks() -> dict:
    from disk_cleaner_app import __version__

    checks = {
        "tk": _check("tk", _check_tk),
        "imports": _check("imports", _check_imports),
        "sqlite": _check("sqlite", _check_sqlite),
        "config_write": _check("config_write", _check_config_write),
        "temp_write": _check("temp_write", _check_temp_write),
        "powershell": _check("powershell", _check_powershell, critical=False),
        "tray": _check("tray", _check_tray, critical=False),
        "admin": _check("admin", _check_admin, critical=False),
    }
    ok = all(item["ok"] for item in checks.values() if item["critical"])
    return {
        "app": "DiskCleaner Pro",
        "version": __version__,
        "ok": ok,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "checks": checks,
    }


def run_self_test(output: Path | None = None) -> int:
    payload = collect_checks()
    target = output or Path(
        os.environ.get(
            "DISKCLEANER_SELFTEST_OUT",
            Path(tempfile.gettempdir()) / "DiskCleaner-selftest.json",
        )
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if sys.stdout is not None:
        for name, item in payload["checks"].items():
            mark = "OK" if item["ok"] else "FAIL"
            print(f"[{mark}] {name}: {item['detail']}")
        print(f"Отчёт: {target}")
        print("SELF-TEST OK" if payload["ok"] else "SELF-TEST FAILED")

    return 0 if payload["ok"] else 1
