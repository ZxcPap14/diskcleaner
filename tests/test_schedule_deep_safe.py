"""Тесты 5C-2: тихая deep-safe очистка, точка восстановления и расписание."""
from __future__ import annotations

import sys
from pathlib import Path

import disk_cleaner_app.services.auto_clean as ac
import disk_cleaner_app.services.schedule as sched


class _FakeCleaner:
    def __init__(
        self,
        cleaner_id: str,
        *,
        layer: str = "A",
        recommended: bool = True,
        admin_required: bool = False,
    ) -> None:
        self.id = cleaner_id
        self.name = cleaner_id
        self.layer = layer
        self.recommended = recommended
        self.admin_required = admin_required
        self.is_actionable = True


class _FakeResult:
    def __init__(self, status: str, freed: int, cleaner_id: str) -> None:
        self.status = status
        self.freed = freed
        self.note = ""
        self.cleaner = _FakeCleaner(cleaner_id)


class _FakeConfig:
    def __init__(self, data: dict | None = None) -> None:
        self._data = dict(data or {})

    def get(self, key, default=None):
        return self._data.get(key, default)


def test_deep_safe_cleaners_filters_layer_recommended_and_admin(monkeypatch) -> None:
    cleaners = [
        _FakeCleaner("a"),
        _FakeCleaner("b", recommended=False),
        _FakeCleaner("c", layer="B"),
        _FakeCleaner("d", admin_required=True),
    ]

    class _Registry:
        def __init__(self, config): pass

        def get_all(self, include_auto=False):
            assert include_auto is False
            return cleaners

    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.registry.CleanerRegistry", _Registry
    )
    monkeypatch.setattr(ac, "is_admin", lambda: False)
    assert [c.id for c in ac.deep_safe_cleaners(_FakeConfig())] == ["a"]

    monkeypatch.setattr(ac, "is_admin", lambda: True)
    assert [c.id for c in ac.deep_safe_cleaners(_FakeConfig())] == ["a", "d"]


def test_run_silent_clean_deep_safe_creates_restore_point(
    monkeypatch, tmp_path: Path
) -> None:
    import disk_cleaner_app.services.restore_point as restore_mod
    from disk_cleaner_app.models.history import HistoryManager

    calls: dict = {}

    class _Engine:
        def clean_selected(self, cleaners, options=None, progress_callback=None):
            calls["cleaners"] = list(cleaners)
            return [
                _FakeResult("OK", 42, "a"),
                _FakeResult("SKIP", 0, "b"),
            ]

    db = tmp_path / "h.db"
    monkeypatch.setattr(ac, "deep_safe_cleaners", lambda config=None: ["a", "b"])
    monkeypatch.setattr(ac, "CleanEngine", _Engine)
    monkeypatch.setattr(
        restore_mod, "create_restore_point", lambda: (True, "точка создана")
    )
    monkeypatch.setattr(ac, "HistoryManager", lambda: HistoryManager(db_path=db))

    config = _FakeConfig({"restore_point": True, "to_recycle": False})
    summary = ac.run_silent_clean(config=config, mode=ac.DEEP_SAFE_MODE)

    assert summary == {
        "targets": 2,
        "ok": 1,
        "failed": 0,
        "freed": 42,
        "mode": "deep-safe",
        "skipped": 0,
    }
    assert calls["cleaners"] == ["a", "b"]
    entry = HistoryManager(db_path=db).get_last()
    assert entry is not None and entry["op_type"] == "deep"


def test_run_silent_clean_deep_safe_counts_failed_restore_point(
    monkeypatch, tmp_path: Path
) -> None:
    import disk_cleaner_app.services.restore_point as restore_mod
    from disk_cleaner_app.models.history import HistoryManager

    class _Engine:
        def clean_selected(self, cleaners, options=None, progress_callback=None):
            return [_FakeResult("OK", 10, "a")]

    db = tmp_path / "h.db"
    monkeypatch.setattr(ac, "deep_safe_cleaners", lambda config=None: ["a"])
    monkeypatch.setattr(ac, "CleanEngine", _Engine)
    monkeypatch.setattr(
        restore_mod, "create_restore_point", lambda: (False, "лимит 24 ч")
    )
    monkeypatch.setattr(ac, "HistoryManager", lambda: HistoryManager(db_path=db))

    config = _FakeConfig({"restore_point": True})
    summary = ac.run_silent_clean(config=config, mode=ac.DEEP_SAFE_MODE)

    assert summary["skipped"] == 1
    assert summary["ok"] == 1


def test_run_silent_clean_smart_does_not_touch_restore_point(
    monkeypatch, tmp_path: Path
) -> None:
    import disk_cleaner_app.services.restore_point as restore_mod
    from disk_cleaner_app.models.history import HistoryManager

    called: list[bool] = []

    class _Registry:
        def __init__(self, config): pass

        def get_safe(self):
            return ["safe"]

    class _Engine:
        def clean_selected(self, cleaners, options=None, progress_callback=None):
            return [_FakeResult("OK", 5, "safe")]

    db = tmp_path / "h.db"
    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.registry.CleanerRegistry", _Registry
    )
    monkeypatch.setattr(ac, "CleanEngine", _Engine)
    monkeypatch.setattr(
        restore_mod,
        "create_restore_point",
        lambda: called.append(True) or (True, ""),
    )
    monkeypatch.setattr(ac, "HistoryManager", lambda: HistoryManager(db_path=db))

    config = _FakeConfig({"restore_point": True})
    summary = ac.run_silent_clean(config=config)

    assert summary["mode"] == "smart"
    assert called == []
    entry = HistoryManager(db_path=db).get_last()
    assert entry is not None and entry["op_type"] == "smart"


def test_command_line_adds_deep_safe_flag(monkeypatch) -> None:
    import disk_cleaner_app.models.config as config_mod

    class _Cfg:
        def __init__(self, mode: str) -> None:
            self._mode = mode

        def get(self, key, default=None):
            return self._mode if key == "schedule_mode" else default

    monkeypatch.setattr(config_mod, "ConfigManager", lambda: _Cfg("deep-safe"))
    command = sched._command_line()
    assert "--smart-clean" in command
    assert "--deep-safe" in command

    monkeypatch.setattr(config_mod, "ConfigManager", lambda: _Cfg("smart"))
    assert "--deep-safe" not in sched._command_line()


def test_cli_deep_safe_selects_mode(monkeypatch) -> None:
    import disk_cleaner_app.__main__ as entry

    seen: dict = {}

    def fake_run(mode: str) -> int:
        seen["mode"] = mode
        return 0

    monkeypatch.setattr(entry, "_run_silent_clean", fake_run)
    monkeypatch.setattr(
        sys, "argv", ["DiskCleaner", "--smart-clean", "--deep-safe", "--silent"]
    )

    try:
        entry.main()
    except SystemExit as exc:
        assert exc.code == 0
    assert seen["mode"] == ac.DEEP_SAFE_MODE
