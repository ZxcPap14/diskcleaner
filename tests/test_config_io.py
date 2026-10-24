"""Тесты экспорта/импорта настроек и пользовательских правил."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from disk_cleaner_app.models import config as config_module
from disk_cleaner_app.models.config import ConfigManager


@pytest.fixture()
def manager(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(
        config_module, "CUSTOM_RULES_FILE", tmp_path / "custom_rules.json"
    )
    return ConfigManager()


def test_export_import_roundtrip(manager, tmp_path: Path) -> None:
    manager.set("to_recycle", True)
    folder = tmp_path / "cache"
    folder.mkdir()
    manager.add_custom_rule("Мой кэш", str(folder), "🟡")

    exported = manager.export_config(tmp_path / "backup")
    assert exported.suffix == ".json"

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    target = other_dir / "cache"
    target.mkdir()

    payload = json.loads(exported.read_text(encoding="utf-8"))
    payload["custom_rules"][0]["path"] = str(target)
    exported.write_text(json.dumps(payload), encoding="utf-8")

    manager.set("to_recycle", False)
    manager.save_custom_rules([])

    stats = manager.import_config(exported)

    assert stats["config"] >= 1
    assert stats["rules"] == 1
    assert manager.get("to_recycle") is True
    rules = manager.load_custom_rules()
    assert len(rules) == 1
    assert rules[0]["name"] == "Мой кэш"
    assert rules[0]["path"] == str(target)


def test_import_skips_invalid_values(manager, tmp_path: Path) -> None:
    payload = {
        "app": "DiskCleaner",
        "schema": 1,
        "config": {"theme": "neon", "safe_mode": "yes"},
        "custom_rules": [
            {"name": "", "path": "C:\\temp"},
            {"name": "Windows", "path": "C:\\Windows"},
            {"name": "ok", "path": str(tmp_path / "folder")},
        ],
    }
    source = tmp_path / "bad.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    stats = manager.import_config(source)

    assert stats["config"] == 0
    assert stats["rules"] == 1
    assert len(stats["skipped"]) == 4
    assert manager.get("theme") == "dark"


def test_import_without_merge_replaces_rules(manager, tmp_path: Path) -> None:
    folder = tmp_path / "a"
    folder.mkdir()
    manager.add_custom_rule("Старое", str(folder))

    payload = {
        "schema": 1,
        "config": {},
        "custom_rules": [{"name": "Новое", "path": str(tmp_path)}],
    }
    source = tmp_path / "new.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    stats = manager.import_config(source, merge=False)

    assert stats["rules"] == 1
    assert [r["name"] for r in manager.load_custom_rules()] == ["Новое"]


def test_import_rejects_newer_schema(manager, tmp_path: Path) -> None:
    source = tmp_path / "future.json"
    source.write_text(
        json.dumps({"schema": 99, "config": {}, "custom_rules": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="более новой"):
        manager.import_config(source)


def test_import_rejects_broken_json(manager, tmp_path: Path) -> None:
    source = tmp_path / "broken.json"
    source.write_text("{не json", encoding="utf-8")

    with pytest.raises(ValueError):
        manager.import_config(source)


def test_update_rule_changes_fields(manager, tmp_path: Path) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    rule_id = manager.add_custom_rule("Старое имя", str(folder))

    manager.update_custom_rule(rule_id, "Новое имя", str(folder), "🟢")

    rule = manager.load_custom_rules()[0]
    assert rule["name"] == "Новое имя"
    assert rule["safety"] == "🟢"


def test_update_missing_rule_raises(manager, tmp_path: Path) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()

    with pytest.raises(ValueError, match="не найдено"):
        manager.update_custom_rule("nope", "Имя", str(folder))
