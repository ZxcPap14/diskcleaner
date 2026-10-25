"""Тесты 5C-3: auto-discovered цели на экране глубокой очистки."""
from __future__ import annotations

from pathlib import Path

import disk_cleaner_app.cleaners.registry as registry_mod
from disk_cleaner_app.cleaners.discover import AutoDiscoveredCleaner
from disk_cleaner_app.cleaners.registry import CleanerRegistry
from disk_cleaner_app.models.target import LAYER_SAFE


class _FakeConfig:
    def load_custom_rules(self):
        return []


class _FakeView:
    def __init__(self) -> None:
        self._cleaners: list = []
        self.loaded: list = []

    def load_cleaners(self, cleaners) -> None:
        self._cleaners = list(cleaners)
        self.loaded = list(cleaners)


def test_auto_discovered_is_safe_layer_but_not_recommended(tmp_path: Path) -> None:
    cleaner = AutoDiscoveredCleaner(tmp_path / "App" / "Cache", "App")

    assert cleaner.layer == LAYER_SAFE
    # Auto-цель показывается на экране и попадает в план, но не выбирается
    # по умолчанию: пользователь решает сам.
    assert cleaner.recommended is False


def test_registry_includes_auto_discovered_only_when_asked(
    monkeypatch, tmp_path: Path
) -> None:
    auto = AutoDiscoveredCleaner(tmp_path / "App" / "Cache", "App")
    monkeypatch.setattr(registry_mod, "auto_discover_items", lambda: [auto])

    with_auto = CleanerRegistry(_FakeConfig()).get_all(include_auto=True)
    without_auto = CleanerRegistry(_FakeConfig()).get_all(include_auto=False)

    assert auto in with_auto
    assert auto not in without_auto


def test_load_deep_cleaners_passes_auto_targets(monkeypatch) -> None:
    from disk_cleaner_app.ui.app import MainWindow

    view = _FakeView()
    calls: dict = {}

    class _Registry:
        def get_all(self, include_auto=True):
            calls["include_auto"] = include_auto
            return ["auto-item"]

    app = object.__new__(MainWindow)
    app.views = {"deep": view}
    app.registry = _Registry()

    app._load_deep_cleaners(force=True)

    assert calls["include_auto"] is True
    assert view.loaded == ["auto-item"]


def test_load_deep_cleaners_reuses_existing_list_without_force() -> None:
    from disk_cleaner_app.ui.app import MainWindow

    view = _FakeView()
    view._cleaners = ["already"]

    class _Registry:
        def get_all(self, include_auto=True):
            raise AssertionError("реестр не должен вызываться без force")

    app = object.__new__(MainWindow)
    app.views = {"deep": view}
    app.registry = _Registry()

    app._load_deep_cleaners()

    assert view.loaded == []
