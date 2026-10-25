"""Цель гибернации: размер hiberfil.sys, обратимость, коды powercfg."""
from __future__ import annotations

from pathlib import Path

import pytest

from disk_cleaner_app.cleaners.system import HibernationCleaner

MODULE = "disk_cleaner_app.cleaners.system"


def test_get_size_reads_hiberfil(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "hiberfil.sys"
    fake.write_text("x" * 1234)
    cleaner = HibernationCleaner()
    monkeypatch.setattr(cleaner, "_hiberfil", lambda: fake)
    assert cleaner.get_size() == 1234


def test_get_size_zero_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cleaner = HibernationCleaner()
    monkeypatch.setattr(cleaner, "_hiberfil", lambda: tmp_path / "nope.sys")
    assert cleaner.get_size() == 0


def test_clean_skip_when_no_hiberfil(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    cleaner = HibernationCleaner()
    monkeypatch.setattr(cleaner, "_hiberfil", lambda: tmp_path / "nope.sys")
    status, detail = cleaner.clean()
    assert status == "SKIP"
    assert "отсутствует" in detail


def test_clean_requires_admin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: False)
    fake = tmp_path / "hiberfil.sys"
    fake.write_text("x")
    cleaner = HibernationCleaner()
    monkeypatch.setattr(cleaner, "_hiberfil", lambda: fake)
    status, _detail = cleaner.clean()
    assert status == "ERR"


def test_clean_ok_file_disappears_and_restore_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "hiberfil.sys"
    fake.write_text("x" * 100)

    def fake_run_tool(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
        assert args[:3] == ["powercfg", "/hibernate", "off"]
        fake.unlink()  # файл освобождается сразу
        return (0, "", "")

    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(MODULE + ".run_tool", fake_run_tool)
    cleaner = HibernationCleaner()
    monkeypatch.setattr(cleaner, "_hiberfil", lambda: fake)
    status, detail = cleaner.clean()

    assert status == "OK"
    assert "powercfg /hibernate on" in detail


def test_clean_command_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "hiberfil.sys"
    fake.write_text("x")
    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(
        MODULE + ".run_tool",
        lambda args, timeout=60: (1, "", "Access is denied."),
    )
    cleaner = HibernationCleaner()
    monkeypatch.setattr(cleaner, "_hiberfil", lambda: fake)
    status, detail = cleaner.clean()

    assert status == "ERR"
    assert "powercfg" in detail
    # файл не потерян при ошибке
    assert fake.exists()
