"""Тесты 4.13.0 «Догнать CCleaner»: новые цели кэшей."""
from __future__ import annotations

from pathlib import Path

import disk_cleaner_app.cleaners.apps as apps_mod
import disk_cleaner_app.cleaners.uwp as uwp_mod
from disk_cleaner_app.cleaners.apps import TeamsNewCacheCleaner
from disk_cleaner_app.cleaners.devtools import VSCodeCacheCleaner
from disk_cleaner_app.cleaners.registry import CleanerRegistry
from disk_cleaner_app.cleaners.uwp import UwpAppCachesCleaner
from disk_cleaner_app.models.config import ConfigManager


def _write(path: Path, size: int = 8) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


# ── UWP/Store ───────────────────────────────────────────


def test_uwp_finds_only_cache_dirs(monkeypatch, tmp_path: Path) -> None:
    packages = tmp_path / "Packages"
    app_a = packages / "App.One_abc123"
    (app_a / "AC" / "INetCache").mkdir(parents=True)
    (app_a / "AC" / "Temp").mkdir(parents=True)
    (app_a / "TempState").mkdir(parents=True)
    (app_a / "LocalState").mkdir(parents=True)      # данные — не цель
    (app_a / "LocalCache").mkdir(parents=True)      # состояние — не цель
    app_b = packages / "App.Two_def456"
    (app_b / "LocalState").mkdir(parents=True)      # вообще без кэшей

    monkeypatch.setattr(uwp_mod, "LOCAL", tmp_path)
    paths = UwpAppCachesCleaner().affected_paths()

    names = {tuple(p.parts[len(tmp_path.parts):]) for p in paths}
    assert names == {
        ("Packages", "App.One_abc123", "AC", "INetCache"),
        ("Packages", "App.One_abc123", "AC", "Temp"),
        ("Packages", "App.One_abc123", "TempState"),
    }


def test_uwp_clean_empties_contents_keeps_dirs(
    monkeypatch, tmp_path: Path
) -> None:
    packages = tmp_path / "Packages"
    cache = packages / "App.One_abc123" / "AC" / "INetCache"
    _write(cache / "entry.dat")
    state = packages / "App.One_abc123" / "LocalState"
    _write(state / "settings.json")

    monkeypatch.setattr(uwp_mod, "LOCAL", tmp_path)
    status, detail = UwpAppCachesCleaner().clean()

    assert status == "OK"
    assert not (cache / "entry.dat").exists()
    assert cache.is_dir()                      # сама папка пакета цела
    assert (state / "settings.json").exists()  # данные не тронуты


# ── Новые Teams ─────────────────────────────────────────


def test_teams_new_targets_webview_caches_only(
    monkeypatch, tmp_path: Path
) -> None:
    teams = (
        tmp_path / "Packages" / "MSTeams_8wekyb3d8bbwe"
        / "LocalCache" / "Microsoft" / "Teams"
    )
    (teams / "EBWebView" / "Default" / "Cache").mkdir(parents=True)
    (teams / "EBWebView" / "Default" / "Code Cache").mkdir(parents=True)
    (teams / "EBWebView" / "Default" / "Cookies").mkdir(parents=True)  # не цель
    (teams / "Cache").mkdir(parents=True)
    (teams / "GPUCache").mkdir(parents=True)

    monkeypatch.setattr(apps_mod, "LOCAL", tmp_path)
    paths = TeamsNewCacheCleaner().affected_paths()

    names = {p.name for p in paths}
    assert names == {"Cache", "Code Cache", "GPUCache"}
    assert not any("Cookies" in p.parts for p in paths)


# ── VS Code семейство ───────────────────────────────────


def test_editor_cleaner_covers_caches_logs_and_vsix(
    tmp_path: Path,
) -> None:
    cleaner = VSCodeCacheCleaner()
    roaming = tmp_path / "Roaming" / "Code"
    ext = tmp_path / ".vscode" / "extensions"
    (roaming / "Cache").mkdir(parents=True)
    (roaming / "logs").mkdir(parents=True)
    (roaming / "User").mkdir(parents=True)          # настройки — не цель
    ext.mkdir(parents=True)
    vsix = _write(ext / "_broken.tgz")
    _write(ext / "publisher.ext-1.0.0")             # папка расширения — не цель

    cleaner.roaming_bases = (roaming,)
    cleaner.local_bases = ()
    cleaner.extensions_dirs = (ext,)

    paths = cleaner.affected_paths()
    names = {p.name for p in paths}
    assert names == {"Cache", "logs", "_broken.tgz"}

    status, _ = cleaner.clean()
    assert status == "OK"
    assert not vsix.exists()
    assert (roaming / "Cache").is_dir()
    assert (roaming / "User").is_dir()


# ── Реестр: новые цели на месте, дубликатов нет ─────────


def test_new_cleaner_ids_in_registry() -> None:
    registry = CleanerRegistry(ConfigManager())
    ids = {cleaner.id for cleaner in registry.get_all(include_auto=False)}

    expected = {
        "uwp_caches", "spotify", "teams_new", "discord_ptb_canary",
        "qbittorrent", "adobe_camera_raw", "go_build", "go_mod", "pnpm",
        "deno", "poetry", "pipx", "cypress", "puppeteer",
        "nuget_packages", "vscodium_ext", "cursor_ext", "torch_hub",
    }
    assert expected <= ids


def test_registry_ids_are_unique() -> None:
    registry = CleanerRegistry(ConfigManager())
    ids = [cleaner.id for cleaner in registry.get_all(include_auto=False)]

    assert len(ids) == len(set(ids))
