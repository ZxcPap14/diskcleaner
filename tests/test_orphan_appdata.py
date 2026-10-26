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

    import disk_cleaner_app.services.batch_delete as batch_mod

    calls: list[tuple[list[str], bool]] = []

    def fake_delete_many(paths, to_recycle=True, use_ifile=True):
        calls.append((list(paths), to_recycle))
        return {"deleted": list(paths), "failed": []}

    monkeypatch.setattr(batch_mod, "delete_many", fake_delete_many)

    cleaner = orphans.OrphanAppDataCleaner()
    status, note = cleaner.clean()

    assert status == "OK"
    assert "корзину" in note
    # Одна пакетная операция на все папки, а не вызов на каждый путь.
    assert len(calls) == 1 and calls[0][1] is True
    assert calls[0][0] == [str(local / "OldTool")]
    # Слой D и «не рекомендуется»: по умолчанию цель не выбрана.
    assert cleaner.layer == LAYER_LEFTOVERS
    assert cleaner.recommended is False


def test_clean_reports_failure_when_remove_fails(monkeypatch, tmp_path: Path) -> None:
    local = tmp_path / "Local"
    _make_old(local / "OldTool")

    monkeypatch.setattr(orphans, "LOCAL_APPDATA", local)
    monkeypatch.setattr(orphans, "ROAMING_APPDATA", tmp_path / "Roaming")
    monkeypatch.setattr(orphans, "_installed_names", lambda: set())

    import disk_cleaner_app.services.batch_delete as batch_mod

    monkeypatch.setattr(
        batch_mod, "delete_many",
        lambda paths, to_recycle=True, use_ifile=True: {
            "deleted": [], "failed": list(paths)
        },
    )

    status, note = orphans.OrphanAppDataCleaner().clean()

    assert status == "ERR"
    assert "Не удалось" in note


def test_affected_paths_rejects_fresh_files_inside_old_folder(
    monkeypatch, tmp_path: Path
) -> None:
    """Папка старая по mtime, но файл внутри недавно менялся — не остаток."""
    local = tmp_path / "Local"
    active = local / "ActiveTool"
    _make_old(active)
    (active / "settings.json").write_text("{}")
    # Запись файла обновила mtime каталога — состариваем только каталог,
    # как в реальном сценарии «папка не трогалась, конфиг менялся».
    stamp = time.time() - 120 * 86_400
    os.utime(active, (stamp, stamp))

    monkeypatch.setattr(orphans, "LOCAL_APPDATA", local)
    monkeypatch.setattr(orphans, "ROAMING_APPDATA", tmp_path / "Roaming")
    monkeypatch.setattr(orphans, "_installed_names", lambda: set())

    paths = orphans.OrphanAppDataCleaner().affected_paths()

    assert paths == ()
