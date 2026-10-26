"""Тесты самопроверки сборки (`--self-test`)."""
from __future__ import annotations

import json
from pathlib import Path

from disk_cleaner_app import selftest


def _payload(ok: bool = True) -> dict:
    return {
        "app": "DiskCleaner Pro",
        "version": "4.10.3",
        "ok": ok,
        "frozen": True,
        "executable": "C:\\Tools\\DiskCleaner.exe",
        "python": "3.12.0",
        "platform": "Windows-10",
        "checks": {
            "tk": {"ok": ok, "critical": True, "detail": "Tk 8.6"},
        },
    }


def test_check_captures_exception_and_critical_flag() -> None:
    failed = selftest._check("boom", lambda: 1 / 0)
    assert failed == {
        "ok": False,
        "critical": True,
        "detail": "ZeroDivisionError: division by zero",
    }

    optional = selftest._check("opt", lambda: "ok", critical=False)
    assert optional == {"ok": True, "critical": False, "detail": "ok"}


def test_collect_checks_fails_only_on_critical_checks(monkeypatch) -> None:
    monkeypatch.setattr(selftest, "_check_tk", lambda: "Tk 8.6")
    monkeypatch.setattr(selftest, "_check_imports", lambda: "imports ok")
    monkeypatch.setattr(selftest, "_check_sqlite", lambda: "SQLite 3")
    monkeypatch.setattr(selftest, "_check_config_write", lambda: "appdata")
    monkeypatch.setattr(selftest, "_check_temp_write", lambda: "temp")
    monkeypatch.setattr(selftest, "_check_admin", lambda: "обычный пользователь")

    def broken_powershell() -> str:
        raise OSError("powershell.exe не найден в PATH")

    monkeypatch.setattr(selftest, "_check_powershell", broken_powershell)
    payload = selftest.collect_checks()

    assert payload["app"] == "DiskCleaner Pro"
    assert payload["frozen"] is False
    assert payload["ok"] is True
    assert payload["checks"]["powershell"]["critical"] is False
    assert payload["checks"]["admin"]["ok"] is True
    assert payload["checks"]["tk"]["ok"] is True

    def broken_tk() -> str:
        raise RuntimeError("нет Tk")

    monkeypatch.setattr(selftest, "_check_tk", broken_tk)
    assert selftest.collect_checks()["ok"] is False


def test_run_self_test_writes_utf8_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(selftest, "collect_checks", lambda: _payload(ok=True))
    monkeypatch.setattr(selftest.sys, "stdout", None)
    target = tmp_path / "nested" / "report.json"

    assert selftest.run_self_test(target) == 0
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["version"] == "4.10.3"
    assert saved["checks"]["tk"]["detail"] == "Tk 8.6"


def test_run_self_test_returns_failure_code(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(selftest, "collect_checks", lambda: _payload(ok=False))
    monkeypatch.setattr(selftest.sys, "stdout", None)
    target = tmp_path / "report.json"

    assert selftest.run_self_test(target) == 1
    assert json.loads(target.read_text(encoding="utf-8"))["ok"] is False
