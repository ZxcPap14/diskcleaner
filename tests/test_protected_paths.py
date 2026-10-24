"""Защищённые пути: корни, система и личные папки."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from disk_cleaner_app.cleaners.safety import (
    is_dangerous_target,
    is_protected_path,
    is_whitelisted,
    validate_custom_path,
)

SYSTEM_ROOT = Path(os.environ.get("SystemRoot", r"C:\Windows"))
PROGRAM_DATA = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
PROGRAM_FILES = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))


@pytest.mark.parametrize(
    "path",
    [
        Path("C:\\"),
        Path.home(),
        SYSTEM_ROOT,
        PROGRAM_DATA,
        PROGRAM_FILES,
    ],
)
def test_dangerous_targets_are_rejected(path: Path) -> None:
    assert is_dangerous_target(path) is True


@pytest.mark.parametrize(
    "path",
    [
        SYSTEM_ROOT / "Temp",
        SYSTEM_ROOT / "Prefetch",
        SYSTEM_ROOT / "Logs" / "CBS",
        SYSTEM_ROOT / "SoftwareDistribution" / "Download",
        PROGRAM_DATA / "Microsoft" / "Windows" / "WER",
    ],
)
def test_known_system_cache_subdirs_are_allowed(path: Path) -> None:
    assert is_dangerous_target(path) is False


def test_user_personal_folder_is_rejected(tmp_path: Path) -> None:
    documents = Path.home() / "Documents"

    assert is_dangerous_target(documents) is True
    assert is_dangerous_target(tmp_path) is False


def test_protected_path_blocks_everything_inside_windows() -> None:
    assert is_protected_path(SYSTEM_ROOT / "Temp") is True
    assert is_protected_path(Path("C:\\")) is True


def test_custom_rule_cannot_target_personal_folder() -> None:
    documents = Path.home() / "Documents"

    assert validate_custom_path(documents)


def test_custom_rule_accepts_normal_temp_folder(tmp_path: Path) -> None:
    assert validate_custom_path(tmp_path) == ""


def test_trailing_dots_and_spaces_do_not_bypass_protection() -> None:
    """Регрессия: Win32 отбрасывает хвостовые точки/пробелы, и
    «C:\\Windows » раньше читался как отдельный разрешённый путь."""
    assert is_protected_path(str(SYSTEM_ROOT) + " ") is True
    assert is_protected_path(str(SYSTEM_ROOT) + "...") is True
    assert is_dangerous_target(str(SYSTEM_ROOT) + ".") is True
    assert is_dangerous_target(str(SYSTEM_ROOT) + " \\system32") is True


def test_root_paths_survive_tail_normalization() -> None:
    assert is_protected_path("C:\\") is True
    assert is_protected_path("D:\\") is True


def test_is_whitelisted_covers_path_and_children(tmp_path: Path) -> None:
    entry = str(tmp_path / "docs")

    assert is_whitelisted(tmp_path / "docs", [entry]) is True
    assert is_whitelisted(tmp_path / "docs" / "a.txt", [entry]) is True
    assert is_whitelisted(tmp_path / "docsx", [entry]) is False
    assert is_whitelisted(tmp_path / "docs", []) is False
