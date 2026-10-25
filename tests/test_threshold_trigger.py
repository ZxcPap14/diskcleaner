"""Тесты 5C-1: баннер порога свободного места на дашборде."""
from __future__ import annotations

import disk_cleaner_app.ui.views.dashboard as dash

GB = 1024 ** 3


class _FakeBanner:
    def __init__(self) -> None:
        self.packed = False
        self.pack_kwargs: dict = {}

    def pack(self, **kwargs) -> None:
        self.packed = True
        self.pack_kwargs = kwargs

    def pack_forget(self) -> None:
        self.packed = False


class _FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def configure(self, **kwargs) -> None:
        if "text" in kwargs:
            self.text = kwargs["text"]


class _FakeConfig:
    def __init__(self, threshold) -> None:
        self._threshold = threshold

    def get(self, key, default=None):
        return self._threshold if key == "deep_threshold_gb" else default


def _view(monkeypatch, threshold, free_gb: float, total_gb: float = 500):
    view = object.__new__(dash.DashboardView)
    view.threshold_banner = _FakeBanner()
    view.banner_text = _FakeLabel()
    view._targets_card = object()
    view._free = int(free_gb * GB)
    view._total = int(total_gb * GB)
    monkeypatch.setattr(dash, "ConfigManager", lambda: _FakeConfig(threshold))
    return view


def test_banner_shown_below_threshold(monkeypatch) -> None:
    view = _view(monkeypatch, 10, free_gb=5)

    view._update_threshold_banner()

    assert view.threshold_banner.packed is True
    assert "меньше порога" in view.banner_text.text
    assert view.threshold_banner.pack_kwargs.get("before") is view._targets_card


def test_banner_hidden_above_threshold(monkeypatch) -> None:
    view = _view(monkeypatch, 10, free_gb=50)

    view._update_threshold_banner()

    assert view.threshold_banner.packed is False


def test_banner_disabled_with_zero_threshold(monkeypatch) -> None:
    view = _view(monkeypatch, 0, free_gb=1)

    view._update_threshold_banner()

    assert view.threshold_banner.packed is False


def test_banner_hidden_without_disk_data(monkeypatch) -> None:
    view = _view(monkeypatch, 10, free_gb=0, total_gb=0)

    view._update_threshold_banner()

    assert view.threshold_banner.packed is False


def test_go_deep_from_dashboard_selects_safe_set() -> None:
    from disk_cleaner_app.ui.app import MainWindow

    calls: list[str] = []

    class _View:
        def select_safe_set(self) -> None:
            calls.append("select_safe_set")

    class _Statusbar:
        def log(self, message: str) -> None:
            calls.append("log")

    app = object.__new__(MainWindow)
    app.views = {"deep": _View()}
    app.statusbar = _Statusbar()
    app._switch_view = lambda name: calls.append(f"switch:{name}")
    app._load_deep_cleaners = lambda: calls.append("load")

    app._go_deep_from_dashboard()

    assert calls[0] == "switch:deep"
    assert "load" in calls
    assert "select_safe_set" in calls
    assert "log" in calls
