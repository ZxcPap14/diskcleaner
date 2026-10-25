"""Детекция запущенных приложений и предупреждения плана (5B-2)."""
from __future__ import annotations

import pytest

from disk_cleaner_app.services import running_apps

MODULE = "disk_cleaner_app.services.running_apps"

FAKE_TASKLIST = (
    '"chrome.exe","1234","Console","1","205 400 КБ"\n'
    '"Telegram.exe","800","Console","1","90 000 КБ"\n'
    '"explorer.exe","700","Console","1","60 000 КБ"\n'
)


def _fake_run(output: str):
    class R:
        stdout: str = output

    def run(*_args, **_kwargs):
        return R()

    return run


def test_running_processes_parses_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".subprocess.run", _fake_run(FAKE_TASKLIST))
    names = running_apps.running_processes()
    assert names == {"chrome.exe", "telegram.exe", "explorer.exe"}


def test_running_processes_tolerates_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".subprocess.run", _fake_run("всё сломалось"))
    assert running_apps.running_processes() == set()


def test_running_processes_empty_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args, **_kwargs):
        raise OSError("no tasklist")

    monkeypatch.setattr(MODULE + ".subprocess.run", run)
    assert running_apps.running_processes() == set()


def test_detect_running_maps_targets() -> None:
    detected = running_apps.detect_running(
        ["chrome_cache", "telegram", "steam"],
        {"chrome.exe", "telegram.exe", "steamwebhelper.exe"},
    )
    assert set(detected) == {"chrome_cache", "telegram", "steam"}
    assert "Chrome" in detected["chrome_cache"]
    assert "Steam" in detected["steam"]


def test_warnings_for_targets_message() -> None:
    warnings = running_apps.warnings_for_targets(
        ["chrome_cache"], {"chrome.exe"}
    )
    assert len(warnings) == 1
    assert "Chrome запущен" in warnings[0]
    assert "пропущена" in warnings[0]


def test_warnings_empty_without_processes() -> None:
    assert running_apps.warnings_for_targets(["chrome_cache"], set()) == []


# ── интеграция с планировщиком ────────────────────────

from disk_cleaner_app.cleaners.base import BaseCleaner  # noqa: E402
from disk_cleaner_app.models.item import GROUP_SYSTEM  # noqa: E402
from disk_cleaner_app.models.target import LAYER_SAFE  # noqa: E402
from disk_cleaner_app.services.planner import Planner  # noqa: E402


class _FakeCleaner(BaseCleaner):
    id = "chrome_cache"
    name = "🌐 Chrome — Кэш"
    group = GROUP_SYSTEM
    layer = LAYER_SAFE

    def get_size(self) -> int:
        return 500

    def clean(self) -> tuple[str, str]:
        return "OK", ""


def test_planner_adds_running_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        MODULE + ".running_processes", lambda timeout=30: {"chrome.exe"}
    )
    plan = Planner(running_check=running_apps.running_processes).build(
        [_FakeCleaner()]
    )
    assert any("Chrome запущен" in w for w in plan.warnings)


def test_planner_without_running_check_has_no_warning() -> None:
    plan = Planner(running_check=None).build([_FakeCleaner()])
    assert plan.warnings == []
