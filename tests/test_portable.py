"""Портативный режим: данные рядом с exe, а не в %APPDATA% (--portable)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from disk_cleaner_app.models import config as config_module
from disk_cleaner_app.services import portable


def test_portable_home_next_to_exe_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "DiskCleaner.exe"))

    assert portable.portable_home() == tmp_path / portable.DATA_DIR_NAME


def test_portable_home_uses_cwd_from_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)

    assert portable.portable_home() == tmp_path / portable.DATA_DIR_NAME


def test_apply_portable_sets_env_and_config_follows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(portable.ENV_HOME, raising=False)

    home = portable.apply_portable()

    assert home == tmp_path / portable.DATA_DIR_NAME
    # config переменную читает при импорте — проверяем сам резолвер.
    assert config_module._resolve_config_dir() == home


def test_resolve_config_dir_uses_appdata_without_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(portable.ENV_HOME, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert config_module._resolve_config_dir() == tmp_path / "DiskCleaner"
