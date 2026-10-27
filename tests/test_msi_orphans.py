"""Сироты MSI/MSP: сверка с реестром установщика, корзина, защита путей."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from disk_cleaner_app.cleaners.msi_orphans import (
    MsiOrphanCleaner,
    orphan_files,
    referenced_packages,
)
from disk_cleaner_app.cleaners.safety import is_dangerous_target
from disk_cleaner_app.models.target import LAYER_LEFTOVERS

MODULE = "disk_cleaner_app.cleaners.msi_orphans"


def _installer(tmp_path: Path) -> Path:
    folder = tmp_path / "Installer"
    folder.mkdir()
    (folder / "used.msi").write_bytes(b"u" * 11)
    (folder / "used.msp").write_bytes(b"p" * 5)
    (folder / "orphan.msi").write_bytes(b"o" * 21)
    (folder / "orphan.msp").write_bytes(b"o" * 3)
    (folder / "readme.txt").write_text("не установщик")
    (folder / "sub").mkdir()
    (folder / "sub" / "nested.msi").write_bytes(b"n")
    return folder


def test_orphan_files_ignore_referenced_and_other_extensions(tmp_path: Path) -> None:
    folder = _installer(tmp_path)

    found = orphan_files(folder, {"used.msi", "used.msp"})

    assert sorted(p.name for p in found) == ["orphan.msi", "orphan.msp"]


def test_orphan_files_missing_dir(tmp_path: Path) -> None:
    assert orphan_files(tmp_path / "nope", set()) == []


def test_referenced_packages_reads_registry() -> None:
    # Чтение реального реестра: проверяем, что не падаем и умеем собирать имена.
    names = referenced_packages()
    assert isinstance(names, set)
    assert all(name == name.lower() for name in names)


def test_cleaner_metadata_and_scan(tmp_path: Path, monkeypatch) -> None:
    folder = _installer(tmp_path)

    monkeypatch.setattr(MODULE + ".INSTALLER_DIR", folder)
    monkeypatch.setattr(
        MODULE + ".referenced_packages", lambda: {"used.msi", "used.msp"}
    )
    cleaner = MsiOrphanCleaner()

    assert cleaner.layer == LAYER_LEFTOVERS
    assert cleaner.admin_required is True
    assert cleaner.get_size() == 21 + 3
    assert len(cleaner.affected_paths()) == 2


def test_clean_sends_to_recycle(tmp_path: Path, monkeypatch) -> None:
    folder = _installer(tmp_path)
    monkeypatch.setattr(MODULE + ".INSTALLER_DIR", folder)
    monkeypatch.setattr(
        MODULE + ".referenced_packages", lambda: {"used.msi", "used.msp"}
    )
    recycled: list[bool] = []

    def fake_delete_many(paths: list[str], to_recycle: bool = False) -> dict:
        recycled.append(to_recycle)
        return {"deleted": paths, "failed": []}

    monkeypatch.setattr(
        "disk_cleaner_app.services.batch_delete.delete_many", fake_delete_many
    )

    status, detail = MsiOrphanCleaner().clean()

    assert status == "OK"
    assert recycled == [True]
    assert "2" in detail


def test_clean_without_orphans(monkeypatch) -> None:
    monkeypatch.setattr(MODULE + ".INSTALLER_DIR", Path("C:/nonexistent-installer"))
    monkeypatch.setattr(MODULE + ".referenced_packages", lambda: set())

    status, detail = MsiOrphanCleaner().clean()

    assert status == "OK"
    assert "не найдено" in detail


def test_msi_files_allowed_by_path_guard() -> None:
    installer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Installer"

    # Установщики разрешены, остальное в каталоге — нет.
    assert is_dangerous_target(installer / "orphan.msi") is False
    assert is_dangerous_target(installer / "readme.txt") is True
    assert is_dangerous_target(installer / "sub" / "nested.msi") is True


@pytest.mark.parametrize("name", ["orphan.MSI", "orphan.MsP"])
def test_guard_is_case_insensitive(name: str) -> None:
    installer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Installer"

    assert is_dangerous_target(installer / name) is False
