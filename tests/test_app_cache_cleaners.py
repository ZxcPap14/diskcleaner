"""Тесты новых целей очистки: Epic, Adobe, Java, WSL vhdx."""
from __future__ import annotations

from pathlib import Path

from disk_cleaner_app.cleaners.apps import (
    AdobeCacheCleaner,
    EpicGamesCacheCleaner,
    JavaCacheCleaner,
    WSLVhdxInfoCleaner,
)


def test_epic_cache_collects_webcache_dirs(tmp_path: Path, monkeypatch) -> None:
    saved = tmp_path / "Local"
    (saved / "EpicGamesLauncher" / "Saved" / "WebCache_1").mkdir(parents=True)
    (saved / "EpicGamesLauncher" / "Saved" / "WebCache").mkdir()
    (saved / "EpicGamesLauncher" / "Saved" / "Logs").mkdir()
    (saved / "EpicGamesLauncher" / "Saved" / "WebCache_1" / "a.bin").write_bytes(
        b"x" * 100
    )
    monkeypatch.setattr("disk_cleaner_app.cleaners.apps.LOCAL", saved)
    cleaner = EpicGamesCacheCleaner()

    paths = cleaner.affected_paths()
    assert len(paths) == 2
    assert cleaner.get_size() == 100


def test_epic_cache_absent_when_no_launcher(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("disk_cleaner_app.cleaners.apps.LOCAL", tmp_path)
    assert EpicGamesCacheCleaner().affected_paths() == ()
    assert EpicGamesCacheCleaner().get_size() == 0


def test_adobe_cache_path(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "Adobe" / "Common" / "Media Cache Files"
    target.mkdir(parents=True)
    (target / "m.idx").write_bytes(b"y" * 50)
    monkeypatch.setattr("disk_cleaner_app.cleaners.apps.LOCAL", tmp_path)
    cleaner = AdobeCacheCleaner()

    assert cleaner.affected_paths() == (target,)
    assert cleaner.get_size() == 50
    assert cleaner.clean() == ("OK", "Adobe media cache очищен")
    assert target.exists()
    assert not (target / "m.idx").exists()


def test_java_cache_under_locallow(tmp_path: Path, monkeypatch) -> None:
    cache = (
        tmp_path / "AppData" / "LocalLow" / "Sun" / "Java" / "Deployment" / "cache"
    )
    cache.mkdir(parents=True)
    (cache / "app.jar").write_bytes(b"z" * 10)
    monkeypatch.setattr("disk_cleaner_app.cleaners.apps.Path.home",
                        lambda: tmp_path)
    cleaner = JavaCacheCleaner()

    assert cleaner.affected_paths() == (cache,)
    assert cleaner.get_size() == 10
    assert cleaner.clean()[0] == "OK"


def test_wsl_vhdx_is_detection_only(tmp_path: Path, monkeypatch) -> None:
    distro = tmp_path / "Packages" / "CanonicalGroupLimited.Ubuntu_123"
    state = distro / "LocalState"
    state.mkdir(parents=True)
    (state / "ext4.vhdx").write_bytes(b"v" * 4096)
    (tmp_path / "Packages" / "SomeOtherApp").mkdir()
    monkeypatch.setattr("disk_cleaner_app.cleaners.apps.LOCAL", tmp_path)
    cleaner = WSLVhdxInfoCleaner()

    assert cleaner.affected_paths() == (state / "ext4.vhdx",)
    assert cleaner.get_size() == 4096

    status, details = cleaner.clean()

    assert status == "SKIP"
    assert "Optimize-VHD" in details
    assert (state / "ext4.vhdx").exists()
