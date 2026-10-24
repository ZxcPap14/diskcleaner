"""Все профили браузеров, а не только Default."""
from __future__ import annotations

import json
from pathlib import Path

from disk_cleaner_app.cleaners import browsers
from disk_cleaner_app.cleaners.browsers import (
    ChromeCacheCleaner,
    FirefoxCacheCleaner,
    OperaCacheCleaner,
    chromium_profiles,
)


def _touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _chrome_user_data(root: Path) -> Path:
    user_data = root / "User Data"
    _touch(user_data / "Default" / "Cache" / "f_0001")
    _touch(user_data / "Profile 1" / "Code Cache" / "f_0002")
    _touch(user_data / "Profile 2" / "GPUCache" / "f_0003")
    _touch(user_data / "Default" / "History")
    (user_data / "Local State").write_text(
        json.dumps(
            {"profile": {"info_cache": {"Default": {}, "Profile 1": {}}}}
        ),
        encoding="utf-8",
    )
    return user_data


def test_chromium_profiles_uses_local_state_and_folders(tmp_path: Path) -> None:
    user_data = _chrome_user_data(tmp_path)
    names = {p.name for p in chromium_profiles(user_data)}

    assert names == {"Default", "Profile 1", "Profile 2"}


def test_chrome_cache_covers_every_profile(tmp_path: Path) -> None:
    user_data = _chrome_user_data(tmp_path)
    cleaner = ChromeCacheCleaner()
    cleaner.user_data = user_data
    paths = set(cleaner.affected_paths())

    assert user_data / "Default" / "Cache" in paths
    assert user_data / "Profile 1" / "Code Cache" in paths
    assert user_data / "Profile 2" / "GPUCache" in paths
    # История и прочие данные профиля не являются кэшем.
    assert user_data / "Default" / "History" not in paths
    assert cleaner.get_size() == 3


def test_chrome_cache_without_local_state(tmp_path: Path) -> None:
    user_data = tmp_path / "User Data"
    _touch(user_data / "Default" / "Cache" / "f")
    _touch(user_data / "Profile 7" / "Cache" / "f")
    cleaner = ChromeCacheCleaner()
    cleaner.user_data = user_data

    paths = set(cleaner.affected_paths())

    assert user_data / "Default" / "Cache" in paths
    assert user_data / "Profile 7" / "Cache" in paths


def test_opera_uses_user_data_as_profile(tmp_path: Path) -> None:
    root = tmp_path / "Opera Stable"
    _touch(root / "Cache" / "f")
    cleaner = OperaCacheCleaner()
    cleaner.user_data = root

    assert cleaner.affected_paths() == (root / "Cache",)


def test_firefox_profiles_ini_is_respected(tmp_path: Path, monkeypatch) -> None:
    local = tmp_path / "local"
    roaming = tmp_path / "roaming"
    profile = local / "Mozilla" / "Firefox" / "Profiles" / "abc.default"
    _touch(profile / "cache2" / "f")
    _touch(profile / "startupCache" / "f")
    _touch(profile / "bookmarks.html")

    ini = roaming / "Mozilla" / "Firefox" / "profiles.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text(
        "[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/abc.default\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(browsers, "LOCAL", local)
    monkeypatch.setattr(browsers, "ROAMING", roaming)

    cleaner = FirefoxCacheCleaner()
    paths = set(cleaner.affected_paths())

    assert profile / "cache2" in paths
    assert profile / "startupCache" in paths
    assert profile / "bookmarks.html" not in paths


def test_firefox_without_ini_still_scans_profiles(tmp_path: Path, monkeypatch) -> None:
    local = tmp_path / "local"
    profile = local / "Mozilla" / "Firefox" / "Profiles" / "xyz.default"
    _touch(profile / "cache2" / "f")

    monkeypatch.setattr(browsers, "LOCAL", local)
    monkeypatch.setattr(browsers, "ROAMING", tmp_path / "roaming")

    cleaner = FirefoxCacheCleaner()

    assert (profile / "cache2") in cleaner.affected_paths()
