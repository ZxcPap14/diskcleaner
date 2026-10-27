"""Тесты 4.18.0: CLI --scan / --clean с JSON-отчётом."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import PathCleaner

from disk_cleaner_app.services.cli_clean import (
    build_preset_cleaners,
    run_cli_scan_clean,
)


def _report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── скан без удаления ────────────────────────────────────


def test_scan_only_measures_and_reports(tmp_path: Path) -> None:
    cache = tmp_path / "App" / "cache"
    cache.mkdir(parents=True)
    (cache / "a.bin").write_bytes(b"x" * 1000)

    report = tmp_path / "out" / "report.json"
    code = run_cli_scan_clean(
        preset="safe", clean=False, report_path=report,
        cleaners=[PathCleaner([cache], cleaner_id="scanme", name="Scan Me")],
    )

    assert code == 0
    data = _report(report)
    assert data["mode"] == "scan"
    assert data["preset"] == "safe"
    assert data["total_size"] == 1000
    assert data["targets"][0]["id"] == "scanme"
    assert data["targets"][0]["size"] == 1000
    assert report.parent.is_dir()  # вложенный каталог создан


def test_scan_prints_warnings_for_broken_size(tmp_path: Path, capsys) -> None:
    class Broken(PathCleaner):
        def get_size(self) -> int:
            raise OSError("диск недоступен")

    code = run_cli_scan_clean(
        clean=False, cleaners=[Broken([tmp_path], cleaner_id="broken")]
    )

    assert code == 0
    assert "диск недоступен" in capsys.readouterr().out


def test_scan_does_not_delete(tmp_path: Path) -> None:
    cache = tmp_path / "App" / "cache"
    cache.mkdir(parents=True)
    (cache / "f.bin").write_bytes(b"x")

    run_cli_scan_clean(clean=False, cleaners=[PathCleaner([cache])])

    assert (cache / "f.bin").exists()


# ── очистка ──────────────────────────────────────────────


def test_clean_runs_engine_and_reports(tmp_path: Path) -> None:
    cache = tmp_path / "App" / "cache"
    cache.mkdir(parents=True)
    (cache / "a.bin").write_bytes(b"x" * 500)

    report = tmp_path / "report.json"
    code = run_cli_scan_clean(
        preset="safe", clean=True, report_path=report,
        cleaners=[PathCleaner([cache], cleaner_id="cleanme")],
    )

    assert code == 0
    data = _report(report)
    assert data["mode"] == "clean"
    assert data["targets"][0]["status"] == "OK"
    assert data["targets"][0]["planned"] == 500
    assert data["total_freed"] >= 0
    # Содержимое удалено, папка осталась (contents-режим).
    assert not (cache / "a.bin").exists()
    assert cache.is_dir()


def test_clean_exit_code_reflects_failures(
    tmp_path: Path, monkeypatch
) -> None:
    """Все действия не удалились → код выхода 1."""
    import disk_cleaner_app.services.cleaner as cleaner_mod

    cache = tmp_path / "App" / "cache"
    cache.mkdir(parents=True)
    (cache / "a.bin").write_bytes(b"x")

    monkeypatch.setattr(
        cleaner_mod, "delete_many",
        lambda paths, to_recycle=True, use_ifile=True: {
            "deleted": [], "failed": list(paths), "aborted": False,
        },
    )

    code = run_cli_scan_clean(
        clean=True, cleaners=[PathCleaner([cache], cleaner_id="c")]
    )

    assert code == 1


def test_invalid_preset_returns_code_2() -> None:
    assert run_cli_scan_clean(preset="everything") == 2


def test_build_preset_cleaners_rejects_unknown() -> None:
    try:
        build_preset_cleaners("everything")
    except ValueError as e:
        assert "safe" in str(e)
    else:
        raise AssertionError("ValueError не поднят")
