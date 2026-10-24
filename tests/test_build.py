"""Тесты команды сборки (без запуска PyInstaller)."""
from __future__ import annotations

import build


def test_default_build_has_no_admin_manifest() -> None:
    cmd = build.build_command()

    assert "--uac-admin" not in cmd
    assert "--onefile" in cmd
    assert "--noconsole" in cmd


def test_admin_manifest_flag_is_added() -> None:
    cmd = build.build_command(uac_admin=True)

    assert "--uac-admin" in cmd


def test_legacy_modules_are_excluded() -> None:
    cmd = build.build_command()

    for module in build.EXCLUDES:
        assert "--exclude-module" in cmd
        assert module in cmd
