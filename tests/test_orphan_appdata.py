"""Тесты 5C-4: остатки удалённых программ в AppData (слой D)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import disk_cleaner_app.cleaners.orphans as orphans
from disk_cleaner_app.models.target import LAYER_LEFTOVERS


def _make_old(path: Path, days: float = 120) -> None:
    path.mkdir(parents=True, exist_ok=True)
    stamp = time.time() - days * 86_400
    os.utime(path, (stamp, stamp))


def test_normalize_and_compact_name() -> None:
    assert orphans.normalize_name("Yandex Browser (x64)!") == "yandex browser x64"
    assert orphans.compact_name("yandex browser") == "yandexbrowser"


def test_is_orphan_respects_exclude_installed_and_neighbours() -> None:
    installed = {"yandex browser", "yandexbrowser"}

    # Запретный список: кэш/логи/пакетные менеджеры.
    assert orphans._is_orphan("Cache", set(), set()) is False
    assert orphans._is_orphan("npm-cache", set(), set()) is False
    # Совпадение с установленной программой или издателем (в обе стороны).
    assert orphans._is_orphan("YandexBrowser", installed, set()) is False
    assert orphans._is_orphan("Yandex", {"yandex"}, set()) is False
    # Соседняя папка корня: vendor-папка не считается остатком.
    assert orphans._is_orphan("Yandex", set(), {"YandexBrowser"}) is False
    # Ничего не совпало — это остаток.
    assert orphans._is_orphan("OldTool", installed, {"Other"}) is True


def test_affected_paths_filters_by_name_and_age(monkeypatch, tmp_path: Path) -> None:
    local = tmp_path / "Local"
    roaming = tmp_path / "Roaming"
    _make_old(local / "OldTool")
    _make_old(roaming / "AnotherOld", days=200)
    _make_old(local / "InstalledApp")
    _make_old(local / "FreshOrphan", days=10)
    (local / "Cache").mkdir(parents=True)

    monkeypatch.setattr(orphans, "LOCAL_APPDATA", local)
    monkeypatch.setattr(orphans, "ROAMING_APPDATA", roaming)
    monkeypatch.setattr(orphans, "_installed_names", lambda: {"installedapp"})

    paths = orphans.OrphanAppDataCleaner().affected_paths()

    assert {p.name for p in paths} == {"OldTool", "AnotherOld"}


def test_missing_roots_are_ignored(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(orphans, "LOCAL_APPDATA", tmp_path / "nope-local")
    monkeypatch.setattr(orphans, "ROAMING_APPDATA", tmp_path / "nope-roaming")
    monkeypatch.setattr(orphans, "_installed_names", lambda: set())

    cleaner = orphans.OrphanAppDataCleaner()

    assert cleaner.affected_paths() == ()
    assert cleaner.get_size() == 0


def test_clean_always_moves_to_recycle(monkeypatch, tmp_path: Path) -> None:
    local = tmp_path / "Local"
    _make_old(local / "OldTool")

    monkeypatch.setattr(orphans, "LOCAL_APPDATA", local)
    monkeypatch.setattr(orphans, "ROAMING_APPDATA", tmp_path / "Roaming")
    monkeypatch.setattr(orphans, "_installed_names", lambda: set())

    calls: list[tuple[str, bool]] = []

    def fake_remove(path: Path, to_recycle: bool = False) -> bool:
        calls.append((path.name, to_recycle))
        return True

    monkeypatch.setattr(orphans, "safe_remove", fake_remove)

    cleaner = orphans.OrphanAppDataCleaner()
    status, note = cleaner.clean()

    assert status == "OK"
    assert "корзину" in note
    assert calls == [("OldTool", True)]
    # Слой D и «не рекомендуется»: по умолчанию цель не выбрана.
    assert cleaner.layer == LAYER_LEFTOVERS
    assert cleaner.recommended is False


def test_clean_reports_failure_when_remove_fails(monkeypatch, tmp_path: Path) -> None:
    local = tmp_path / "Local"
    _make_old(local / "OldTool")

    monkeypatch.setattr(orphans, "LOCAL_APPDATA", local)
    monkeypatch.setattr(orphans, "ROAMING_APPDATA", tmp_path / "Roaming")
    monkeypatch.setattr(orphans, "_installed_names", lambda: set())
    monkeypatch.setattr(orphans, "safe_remove", lambda path, to_recycle=False: False)

    status, note = orphans.OrphanAppDataCleaner().clean()

    assert status == "ERR"
    assert "занята" in note
