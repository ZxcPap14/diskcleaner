"""Тесты конфигурации и пользовательских правил."""
from __future__ import annotations

from pathlib import Path

import pytest

from disk_cleaner_app.models import config as config_module
from disk_cleaner_app.models.config import ConfigManager


@pytest.fixture
def config(tmp_path: Path, monkeypatch) -> ConfigManager:
    """Изолированный конфиг во временной папке."""
    config_dir = tmp_path / "DiskCleaner"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(config_module, "CUSTOM_RULES_FILE", config_dir / "custom_rules.json")
    return ConfigManager()


def test_defaults_are_safe(config: ConfigManager) -> None:
    assert config.get("safe_mode") is True
    assert config.get("to_recycle") is False


def test_settings_are_persisted_atomically(config: ConfigManager, tmp_path: Path) -> None:
    config.set("theme", "light")

    assert ConfigManager().get("theme") == "light"
    assert not list((tmp_path / "DiskCleaner").glob("*.tmp"))


def test_custom_rule_gets_unique_id(config: ConfigManager, tmp_path: Path) -> None:
    first = tmp_path / "cache-one"
    second = tmp_path / "cache-two"
    first.mkdir()
    second.mkdir()

    id_one = config.add_custom_rule("One", str(first))
    id_two = config.add_custom_rule("Two", str(second))

    assert id_one != id_two
    assert id_one.startswith("custom_")
    rules = config.load_custom_rules()
    assert [r["name"] for r in rules] == ["One", "Two"]


def test_custom_rule_rejects_protected_path(config: ConfigManager) -> None:
    with pytest.raises(ValueError, match="защищён"):
        config.add_custom_rule("Home", str(Path.home()))


def test_custom_rule_rejects_missing_path(config: ConfigManager, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="не существует"):
        config.add_custom_rule("Missing", str(tmp_path / "nope"))


def test_custom_rule_rejects_empty_name(config: ConfigManager, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="название"):
        config.add_custom_rule("  ", str(tmp_path))


def test_remove_custom_rule(config: ConfigManager, tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    rule_id = config.add_custom_rule("Cache", str(cache))

    config.remove_custom_rule(rule_id)

    assert config.load_custom_rules() == []


def test_corrupted_config_falls_back_to_defaults(
    config: ConfigManager, monkeypatch, tmp_path: Path
) -> None:
    config_module.CONFIG_FILE.write_text("{not json", encoding="utf-8")
    reloaded = ConfigManager()

    assert reloaded.get("safe_mode") is True
    assert reloaded.get("to_recycle") is False


def test_non_dict_config_falls_back_to_defaults(
    config: ConfigManager, tmp_path: Path
) -> None:
    """Регрессия: валидный JSON-массив вместо объекта ронял приложение."""
    config_module.CONFIG_FILE.write_text('["not", "a", "dict"]', encoding="utf-8")

    reloaded = ConfigManager()

    assert reloaded.get("safe_mode") is True
    assert reloaded.get("to_recycle") is False
    assert reloaded.get("theme") == "dark"


def test_non_list_custom_rules_are_ignored(
    config: ConfigManager, tmp_path: Path
) -> None:
    """Регрессия: JSON-объект вместо списка правил не должен ронять загрузку."""
    config_module.CUSTOM_RULES_FILE.write_text('{"path": "x"}', encoding="utf-8")

    assert config.load_custom_rules() == []

    config_module.CUSTOM_RULES_FILE.write_text(
        '[1, "junk", {"id": "ok"}]', encoding="utf-8"
    )
    assert config.load_custom_rules() == [{"id": "ok"}]
