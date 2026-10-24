"""Тесты нормализации корня диска для анализатора."""
from __future__ import annotations

from pathlib import Path

from disk_cleaner_app.services.analyzer import (
    _dedupe_roots,
    empty_scan_root,
    normalize_root,
    scan_large_files,
)


def test_normalize_root_adds_trailing_separator() -> None:
    assert normalize_root("D:") == "D:\\"
    assert normalize_root("D:\\") == "D:\\"
    assert normalize_root("D:\\Games") == "D:\\Games\\"


def test_normalize_root_defaults_to_system_drive(monkeypatch) -> None:
    monkeypatch.setenv("SystemDrive", "E:")

    assert normalize_root(None) == "E:\\"
    assert normalize_root("   ") == "E:\\"


def test_empty_scan_root_prefers_users(tmp_path: Path) -> None:
    users = tmp_path / "Users"
    users.mkdir()

    assert empty_scan_root(str(tmp_path)) == str(users)


def test_empty_scan_root_falls_back_to_drive(tmp_path: Path) -> None:
    assert empty_scan_root(str(tmp_path)) == normalize_root(str(tmp_path))


def test_dedupe_roots_drops_nested_duplicates() -> None:
    kept = _dedupe_roots(
        [
            "C:\\",
            "C:\\Users\\me",
            "C:\\Users\\me\\AppData\\Local\\Temp",
            "C:\\Users\\me",       # точный дубликат
            "D:\\",
        ]
    )

    assert kept == ["C:\\", "D:\\"]


def test_dedupe_roots_keeps_unrelated_roots() -> None:
    kept = _dedupe_roots(["C:\\Users\\me", "D:\\Games", "E:\\"])

    assert kept == ["E:\\", "D:\\Games", "C:\\Users\\me"]


def test_scan_large_files_returns_each_file_once(
    tmp_path: Path, monkeypatch
) -> None:
    """Регрессия: домашняя папка и TEMP лежат внутри корня —
    файлы попадали в результаты дважды."""
    home = tmp_path / "home"
    temp = home / "AppData" / "Local" / "Temp"
    big = temp / "big.bin"
    big.parent.mkdir(parents=True)
    big.write_bytes(b"x" * 1024)

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("ProgramData", str(tmp_path / "missing-pd"))

    results = scan_large_files(str(tmp_path), min_size_mb=0, limit=10)

    paths = [r["path"] for r in results]
    assert paths.count(str(big)) == 1


def test_scan_large_files_skips_windows_but_keeps_its_temp(
    tmp_path: Path, monkeypatch
) -> None:
    windows = tmp_path / "Windows"
    (windows / "System32").mkdir(parents=True)
    (windows / "System32" / "sys.bin").write_bytes(b"x" * 2048)
    (windows / "Temp").mkdir(parents=True)
    (windows / "Temp" / "setup.bin").write_bytes(b"x" * 2048)

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "missing-home")
    monkeypatch.setenv("TEMP", str(tmp_path / "missing-temp"))
    monkeypatch.setenv("ProgramData", str(tmp_path / "missing-pd"))

    results = scan_large_files(str(tmp_path), min_size_mb=0, limit=50)
    paths = {r["path"] for r in results}

    assert str(windows / "Temp" / "setup.bin") in paths
    assert str(windows / "System32" / "sys.bin") not in paths
