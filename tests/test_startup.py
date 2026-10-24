"""Тесты обратимой автозагрузки (папка Startup + резервные копии)."""
from __future__ import annotations

import uuid
import winreg
from pathlib import Path

import pytest

from disk_cleaner_app.services.startup import StartupManager


@pytest.fixture
def manager(tmp_path: Path) -> StartupManager:
    startup = tmp_path / "Startup"
    startup.mkdir()
    mgr = StartupManager(
        startup_folder=startup,
        backup_file=tmp_path / "startup_backup.json",
    )
    # Не трогаем реальный реестр в тестах.
    mgr._read_registry = lambda: []  # type: ignore[method-assign]
    return mgr


def test_startup_folder_file_is_read(manager: StartupManager, tmp_path: Path) -> None:
    (tmp_path / "Startup" / "App.lnk").write_text("", encoding="utf-8")

    items = manager.get_all()

    assert len(items) == 1
    assert items[0]["name"] == "App"
    assert items[0]["enabled"] is True
    assert items[0]["kind"] == "startup_folder"


def test_disable_and_enable_startup_file(manager: StartupManager, tmp_path: Path) -> None:
    folder = tmp_path / "Startup"
    target = folder / "App.lnk"
    target.write_text("", encoding="utf-8")
    item = manager.get_all()[0]

    assert manager.disable_item(item) is True
    assert not target.exists()
    assert (folder / "App.lnk.disabled").exists()

    disabled = manager.get_all()
    assert len(disabled) == 1
    assert disabled[0]["enabled"] is False
    assert disabled[0]["name"] == "App"

    assert manager.enable_item(disabled[0]) is True
    assert target.exists()
    assert not (folder / "App.lnk.disabled").exists()
    assert manager.get_all()[0]["enabled"] is True


def test_disable_is_idempotent(manager: StartupManager, tmp_path: Path) -> None:
    (tmp_path / "Startup" / "App.lnk").write_text("", encoding="utf-8")
    item = manager.get_all()[0]

    assert manager.disable_item(item) is True
    assert manager.disable_item(item) is True


def test_enable_without_backup_fails(manager: StartupManager) -> None:
    item = {
        "id": "file:missing",
        "kind": "startup_folder",
        "enabled": False,
        "path": "C:\\missing\\App.lnk",
    }

    assert manager.enable_item(item) is False
    assert "не найдена" in manager.last_error


def test_registry_backup_roundtrip(manager: StartupManager) -> None:
    entry = {
        "id": "reg:HKCU:TestApp",
        "name": "TestApp",
        "command": "C:\\App\\app.exe",
        "hive": "HKCU",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\Run",
        "reg_name": "TestApp",
        "value_type": 1,
    }
    assert manager._save_backup([entry]) is True

    loaded = manager._load_backup()
    assert loaded == [entry]

    # Повреждённый файл не должен ронять чтение.
    manager._backup_file.write_text("{broken", encoding="utf-8")
    assert manager._load_backup() == []


def test_disabled_registry_entry_is_listed(manager: StartupManager) -> None:
    manager._save_backup([{
        "id": "reg:HKCU:OldApp",
        "name": "OldApp",
        "command": "old.exe",
        "hive": "HKCU",
        "reg_key": r"Software\Microsoft\Windows\CurrentVersion\Run",
        "reg_name": "OldApp",
        "value_type": 1,
    }])

    items = manager.get_all()

    assert [i["id"] for i in items] == ["reg:HKCU:OldApp"]
    assert items[0]["enabled"] is False


def test_add_item_rejects_empty_values(manager: StartupManager) -> None:
    assert manager.add_item("", "cmd") is False
    assert manager.add_item("Name", "  ") is False
    assert "название" in manager.last_error.lower()


def test_non_startup_files_are_ignored(manager: StartupManager, tmp_path: Path) -> None:
    (tmp_path / "Startup" / "readme.txt").write_text("", encoding="utf-8")
    (tmp_path / "Startup" / "App.exe").write_text("", encoding="utf-8")

    items = manager.get_all()

    assert [i["name"] for i in items] == ["App"]


# ── типы значений реестра ─────────────────────────────
# Тесты пишут во временный раздел HKCU (не в Run) и убирают за собой.


@pytest.mark.parametrize(
    ("value", "value_type"),
    [
        (b"\x00\x01\xff", winreg.REG_BINARY),
        (["первый", "second"], winreg.REG_MULTI_SZ),
        (42, winreg.REG_DWORD),
        ("C:\\App\\app.exe", winreg.REG_SZ),
    ],
)
def test_registry_value_type_survives_disable_enable(
    tmp_path: Path, value, value_type
) -> None:
    """Регрессия: str(value) в бэкапе портил REG_BINARY/REG_MULTI_SZ."""
    manager = StartupManager(
        startup_folder=tmp_path / "Startup",
        backup_file=tmp_path / "startup_backup.json",
    )
    subkey = f"Software\\DiskCleanerTest_{uuid.uuid4().hex[:8]}"
    item = {
        "id": "reg:HKCU:probe",
        "name": "probe",
        "kind": "registry",
        "hive": "HKCU",
        "reg_key": subkey,
        "reg_name": "probe",
        "enabled": True,
    }
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            winreg.SetValueEx(key, "probe", 0, value_type, value)

        assert manager.disable_item(item) is True
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            with pytest.raises(OSError):
                winreg.QueryValueEx(key, "probe")

        disabled = next(i for i in manager.get_all() if i["id"] == "reg:HKCU:probe")
        assert manager.enable_item(disabled) is True

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            restored, restored_type = winreg.QueryValueEx(key, "probe")
        assert (restored, restored_type) == (value, value_type)
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
        except OSError:
            pass


def test_old_binary_backup_falls_back_to_reg_sz(tmp_path: Path) -> None:
    """Бэкап без value_raw: бинарный тип заменяем на REG_SZ, а не падаем."""
    manager = StartupManager(
        startup_folder=tmp_path / "Startup",
        backup_file=tmp_path / "startup_backup.json",
    )
    subkey = f"Software\\DiskCleanerTest_{uuid.uuid4().hex[:8]}"
    manager._save_backup([{
        "id": "reg:HKCU:legacy",
        "name": "legacy",
        "command": "SGVsbG8=",
        "hive": "HKCU",
        "reg_key": subkey,
        "reg_name": "legacy",
        "value_type": winreg.REG_BINARY,
    }])
    try:
        disabled = next(i for i in manager.get_all() if i["id"] == "reg:HKCU:legacy")

        assert manager.enable_item(disabled) is True

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            value, value_type = winreg.QueryValueEx(key, "legacy")
        assert value == "SGVsbG8="
        assert value_type == winreg.REG_SZ
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
        except OSError:
            pass
