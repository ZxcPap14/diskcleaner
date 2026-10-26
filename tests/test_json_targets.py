"""Тесты 4.17.0: декларативные JSON-цели очистки."""
from __future__ import annotations

import json
import time
from pathlib import Path

import disk_cleaner_app.services.json_targets as jt
from disk_cleaner_app.models.item import GROUP_SYSTEM
from disk_cleaner_app.services.json_targets import (
    load_json_targets,
    make_target_cleaner,
    parse_targets_json,
    validate_target,
)


def _spec(tmp_path: Path, **overrides) -> dict:
    base = {
        "id": "testapp_cache",
        "name": "📦 TestApp Cache",
        "group": "system",
        "layer": "A",
        "safety": "safe",
        "paths": [str(tmp_path / "TestApp" / "cache")],
        "delete_mode": "contents",
        "min_age_hours": 0,
        "admin_required": False,
        "recommended": True,
        "why": "Кэш приложения TestApp; пересоздаётся сам.",
        "loss": "Приложение загрузит данные заново.",
    }
    base.update(overrides)
    return base


# ── валидация ────────────────────────────────────────────


def test_valid_spec_has_no_errors(tmp_path: Path) -> None:
    assert validate_target(_spec(tmp_path)) == []


def test_invalid_specs_list_errors(tmp_path: Path) -> None:
    cases = [
        ({**_spec(tmp_path), "id": "X"}, "id"),
        ({**_spec(tmp_path), "name": ""}, "name"),
        ({**_spec(tmp_path), "group": "unknown"}, "group"),
        ({**_spec(tmp_path), "layer": "E"}, "layer"),
        ({**_spec(tmp_path), "safety": "ok"}, "safety"),
        ({**_spec(tmp_path), "paths": []}, "paths"),
        ({**_spec(tmp_path), "delete_mode": "wipe"}, "delete_mode"),
        ({**_spec(tmp_path), "why": ""}, "why"),
        ({**_spec(tmp_path), "loss": ""}, "loss"),
        ({**_spec(tmp_path), "min_age_hours": -1}, "min_age_hours"),
    ]
    for spec, needle in cases:
        errors = validate_target(spec)
        assert errors and any(needle in e for e in errors), (needle, errors)


def test_protected_paths_rejected() -> None:
    spec = _spec(Path("C:/nowhere"), paths=[r"C:\Windows\TempX"])
    # Windows\TempX — не в списке безопасных системных подкаталогов.
    assert any("защищён" in e for e in validate_target(spec))

    spec_root = _spec(Path("C:/nowhere"), paths=[r"D:\\"])
    assert validate_target(spec_root)


# ── очиститель из декларации ─────────────────────────────


def test_make_target_cleaner_contents_mode(tmp_path: Path) -> None:
    cache = tmp_path / "TestApp" / "cache"
    cache.mkdir(parents=True)
    (cache / "a.bin").write_bytes(b"x" * 100)
    (cache / "sub").mkdir()
    (cache / "sub" / "b.bin").write_bytes(b"y" * 50)

    cleaner = make_target_cleaner(_spec(tmp_path))
    assert cleaner is not None
    assert cleaner.id == "testapp_cache"
    assert cleaner.group == GROUP_SYSTEM
    assert cleaner.affected_paths() == (cache,)
    assert cleaner.get_size() == 150

    status, _ = cleaner.clean()
    assert status == "OK"
    assert not (cache / "a.bin").exists()
    assert cache.is_dir()                      # contents: папка остаётся
    assert not (cache / "sub" / "b.bin").exists()


def test_make_target_cleaner_remove_mode(tmp_path: Path) -> None:
    folder = tmp_path / "TestApp" / "data"
    folder.mkdir(parents=True)
    (folder / "f.bin").write_bytes(b"x")

    cleaner = make_target_cleaner(
        _spec(tmp_path, paths=[str(folder)], delete_mode="remove")
    )
    assert cleaner is not None
    cleaner.clean()
    assert not folder.exists()


def test_make_target_cleaner_respects_min_age(tmp_path: Path) -> None:
    cache = tmp_path / "TestApp" / "cache"
    cache.mkdir(parents=True)
    old = cache / "old.bin"
    fresh = cache / "fresh.bin"
    old.write_bytes(b"x")
    fresh.write_bytes(b"y")
    stamp = time.time() - 48 * 3600
    import os
    os.utime(old, (stamp, stamp))

    cleaner = make_target_cleaner(_spec(tmp_path, min_age_hours=24))
    cleaner.clean()

    assert not old.exists()
    assert fresh.exists()


def test_make_target_cleaner_skips_missing_paths(tmp_path: Path) -> None:
    spec = _spec(tmp_path)  # пути не созданы
    assert make_target_cleaner(spec) is None


def test_env_expansion(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MY_TEST_ROOT", str(tmp_path))
    resolved = jt.expand_target_path("%MY_TEST_ROOT%/SomeApp/cache")
    assert resolved == tmp_path / "SomeApp" / "cache"


# ── загрузка и слияние источников ────────────────────────


def test_parse_targets_json() -> None:
    payload = parse_targets_json('{"version": 1, "targets": [{"id": "a"}]}')
    assert payload == [{"id": "a"}]
    assert parse_targets_json("битый json") == []
    assert parse_targets_json('{"version": 1}') == []


def test_load_json_targets_merges_and_dedupes(
    monkeypatch, tmp_path: Path
) -> None:
    cache = tmp_path / "Builtin" / "cache"
    cache.mkdir(parents=True)
    (cache / "f.bin").write_bytes(b"x")
    builtin = json.dumps({"version": 1, "targets": [
        _spec(tmp_path, id="builtin_a", paths=[str(cache)]),
        _spec(tmp_path, id="bad id!"),  # невалидный — пропускается
    ]})
    user = json.dumps({"version": 1, "targets": [
        # тот же id — пользовательский имеет приоритет
        _spec(tmp_path, id="builtin_a", paths=[str(cache)]),
        _spec(tmp_path, id="user_b", paths=[str(tmp_path / "UserApp" / "cache")]),
    ]})
    (tmp_path / "UserApp" / "cache").mkdir(parents=True)
    monkeypatch.setattr(jt, "BUILTIN_TARGETS_JSON", builtin)
    user_path = tmp_path / "custom_targets.json"
    user_path.write_text(user, encoding="utf-8")

    cleaners = load_json_targets(user_path=user_path)
    ids = [c.id for c in cleaners]

    # builtin_a один раз, user_b добавлен, «bad id!» отброшен.
    assert ids.count("builtin_a") == 1
    assert "user_b" in ids
    assert all(c.id != "bad id!" for c in cleaners)


def test_registry_includes_json_targets(monkeypatch, tmp_path: Path) -> None:
    from disk_cleaner_app.cleaners.registry import CleanerRegistry
    from disk_cleaner_app.models.config import ConfigManager

    cache = tmp_path / "JsonApp" / "cache"
    cache.mkdir(parents=True)
    (cache / "f.bin").write_bytes(b"x")
    builtin = json.dumps({"version": 1, "targets": [
        _spec(tmp_path, id="registry_json_target", paths=[str(cache)])
    ]})
    monkeypatch.setattr(jt, "BUILTIN_TARGETS_JSON", builtin)

    registry = CleanerRegistry(ConfigManager())
    ids = {cleaner.id for cleaner in registry.get_all(include_auto=False)}

    assert "registry_json_target" in ids


def test_builtin_json_is_valid() -> None:
    """Встроенная декларация не может разъехаться со схемой."""
    specs = parse_targets_json(jt.BUILTIN_TARGETS_JSON)
    assert specs, "встроенный JSON пуст"
    for spec in specs:
        assert validate_target(spec) == [], spec.get("id")
