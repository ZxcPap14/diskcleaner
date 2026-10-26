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


def test_heavy_unused_packages_are_excluded() -> None:
    cmd = build.build_command()

    for module in ("numpy", "scipy", "pandas", "matplotlib"):
        assert module in build.EXCLUDES
        assert module in cmd


def test_spec_excludes_match_build_script() -> None:
    import ast
    from pathlib import Path

    source = Path(build.__file__).with_name("DiskCleaner.spec").read_text(
        encoding="utf-8"
    )
    spec_excludes: list[str] = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", "") == "EXCLUDES" for target in node.targets
        ):
            spec_excludes = [str(item.value) for item in node.value.elts]

    assert spec_excludes == build.EXCLUDES
