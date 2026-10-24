"""Тесты PathGuard: защита критических путей."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from disk_cleaner_app.cleaners.safety import is_protected_path, validate_custom_path


def test_drive_root_is_protected() -> None:
    assert is_protected_path("C:\\")


def test_home_and_its_parents_are_protected() -> None:
    home = Path.home()
    assert is_protected_path(home)
    assert is_protected_path(home.parent)


def test_personal_folders_are_protected() -> None:
    for name in ("Desktop", "Documents", "Downloads", "Pictures"):
        assert is_protected_path(Path.home() / name)


def test_personal_subfolder_is_allowed() -> None:
    # Отдельную подпапку указывать можно — это осознанное действие пользователя.
    assert not is_protected_path(Path.home() / "Downloads" / "some-old-cache")


def test_windows_and_program_files_are_protected() -> None:
    for path in (
        Path(os.environ.get("SystemRoot", r"C:\Windows")),
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "App",
        Path(os.environ.get("ProgramData", r"C:\ProgramData")),
    ):
        assert is_protected_path(path), path


def test_temp_subfolder_is_allowed(tmp_path: Path) -> None:
    assert not is_protected_path(tmp_path)


def test_empty_path_is_protected() -> None:
    assert is_protected_path("")
    assert is_protected_path("   ")


def test_validate_custom_path_requires_existing_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert "не существует" in validate_custom_path(missing)


def test_validate_custom_path_accepts_temp_dir(tmp_path: Path) -> None:
    assert validate_custom_path(tmp_path) == ""


def test_validate_custom_path_rejects_protected_dir() -> None:
    assert validate_custom_path(Path.home()) != ""


@pytest.mark.parametrize("bad", [None, ""])
def test_validate_custom_path_rejects_empty(bad) -> None:
    assert validate_custom_path(bad) == "Путь не указан."
