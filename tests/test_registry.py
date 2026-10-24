"""Тесты фабрики пользовательских правил и реестра."""
from __future__ import annotations

from pathlib import Path

import pytest

from disk_cleaner_app.cleaners.discover import AutoDiscoveredCleaner
from disk_cleaner_app.cleaners.registry import CleanerRegistry, _make_custom_cleaner
from disk_cleaner_app.models.item import GROUP_CUSTOM, SafetyLevel


def test_valid_rule_keeps_its_own_id(tmp_path: Path) -> None:
    rule = {
        "id": "custom_abc123",
        "name": "Мой кэш",
        "path": str(tmp_path),
        "safety": SafetyLevel.CAUTION,
    }
    cleaner = _make_custom_cleaner(rule)

    assert cleaner is not None
    # Регрессия: раньше получалось «custom_custom_abc123».
    assert cleaner.id == "custom_abc123"
    assert cleaner.group == GROUP_CUSTOM
    assert cleaner.name.count("🧩") == 1
    assert cleaner.get_size() == 0
    assert cleaner.preview_path == str(tmp_path)


@pytest.mark.parametrize(
    "rule",
    [
        {"id": "", "name": "No id", "path": "C:\\Temp"},
        {"id": "x", "name": "No path", "path": ""},
        {"id": "y", "name": "Missing", "path": "C:\\definitely-missing-dir-12345"},
        {"id": "z", "name": "Home", "path": str(Path.home())},
    ],
)
def test_invalid_rule_is_skipped(rule: dict) -> None:
    assert _make_custom_cleaner(rule) is None


def test_registry_skips_broken_rules(tmp_path: Path) -> None:
    class FakeConfig:
        def load_custom_rules(self):
            return [
                {"id": "good", "name": "Good", "path": str(tmp_path)},
                {"id": "bad", "name": "Bad", "path": "C:\\missing-12345"},
            ]

    registry = CleanerRegistry(FakeConfig())
    custom = [c for c in registry.get_all(include_auto=False) if c.group == GROUP_CUSTOM]

    assert [c.id for c in custom] == ["good"]


def test_custom_rule_cleaner_exposes_its_path(tmp_path: Path) -> None:
    """Регрессия: без affected_paths правило не попадало в план глубокой
    очистки и выглядело как «команда»."""
    target = tmp_path / "cache"
    target.mkdir()
    (target / "a.bin").write_bytes(b"x" * 10)
    cleaner = _make_custom_cleaner({
        "id": "custom_probe",
        "name": "Probe",
        "path": str(target),
    })

    assert cleaner is not None
    assert cleaner.affected_paths() == (target,)

    status, _detail = cleaner.clean()

    assert status == "OK"
    assert target.exists()                # папка остаётся
    assert not (target / "a.bin").exists()  # удаляется содержимое


def test_auto_discovered_ids_are_unique_per_path() -> None:
    """Регрессия: одинаковые app+имя папки в разных корнях получали
    один id, и сканер молча выбрасывал вторую цель."""
    local = AutoDiscoveredCleaner(Path("C:/Users/me/AppData/Local/Foo/Cache"), "Foo")
    roaming = AutoDiscoveredCleaner(
        Path("C:/Users/me/AppData/Roaming/Foo/Cache"), "Foo"
    )

    assert local.id != roaming.id
    assert local.id.startswith("auto_foo_cache_")
