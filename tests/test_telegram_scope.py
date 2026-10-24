"""Telegram: чистим только кэш-подпапки, не tdata целиком."""
from __future__ import annotations

from pathlib import Path

from disk_cleaner_app.cleaners import apps
from disk_cleaner_app.cleaners.apps import TelegramCacheCleaner


def _touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _tdata(root: Path) -> Path:
    tdata = root / "Telegram Desktop" / "tdata"
    _touch(tdata / "user_data" / "cache" / "a", b"1234")
    _touch(tdata / "user_data" / "media_cache" / "b", b"12")
    _touch(tdata / "user_data" / "webview" / "c", b"1")
    _touch(tdata / "user_data" / "settings" / "keep")
    _touch(tdata / "key_datas")
    _touch(tdata / "D877F783D5D3EF8C" / "keep")
    return tdata


def test_only_cache_subfolders_are_targets(tmp_path: Path, monkeypatch) -> None:
    tdata = _tdata(tmp_path)
    monkeypatch.setattr(apps, "ROAMING", tmp_path)

    cleaner = TelegramCacheCleaner()
    paths = set(cleaner.affected_paths())

    assert paths == {
        tdata / "user_data" / "cache",
        tdata / "user_data" / "media_cache",
        tdata / "user_data" / "webview",
    }
    assert cleaner.get_size() == 7


def test_no_cache_dirs_means_nothing_to_clean(tmp_path: Path, monkeypatch) -> None:
    tdata = tmp_path / "Telegram Desktop" / "tdata"
    _touch(tdata / "key_datas")
    monkeypatch.setattr(apps, "ROAMING", tmp_path)

    cleaner = TelegramCacheCleaner()

    assert cleaner.affected_paths() == ()
    assert cleaner.get_size() == 0


def test_telegram_is_not_part_of_layer_components(tmp_path: Path) -> None:
    cleaner = TelegramCacheCleaner()

    assert cleaner.layer == "A"
    assert cleaner.safety != "🟢"
