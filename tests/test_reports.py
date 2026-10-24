"""Тесты экспорта истории очисток в JSON/CSV."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.services.reports import (
    build_report,
    build_report_from_entries,
    export_csv,
    export_entries_csv,
    export_entries_json,
    export_json,
)


def _history(tmp_path: Path) -> HistoryManager:
    history = HistoryManager(db_path=tmp_path / "history.db")
    history.add_operation(
        [{"id": "chrome", "status": "OK", "freed": 2048}], bytes_freed=2048
    )
    history.add(items_cleaned=2, bytes_freed=1024, details="старая запись")
    return history


def test_build_report_totals(tmp_path: Path) -> None:
    report = build_report(_history(tmp_path))

    assert report["app"] == "DiskCleaner"
    assert report["count"] == 2
    assert report["total_freed"] == 3072
    assert len(report["entries"]) == 2


def test_export_json_creates_file(tmp_path: Path) -> None:
    target = export_json(_history(tmp_path), tmp_path / "report")

    assert target.suffix == ".json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["total_freed"] == 3072
    assert payload["entries"][0]["details"] == "старая запись"


def test_export_csv_has_utf8_bom_and_rows(tmp_path: Path) -> None:
    target = export_csv(_history(tmp_path), tmp_path / "report.csv")

    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")

    with open(target, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["bytes_freed"] == "1024"
    assert rows[1]["items_cleaned"] == "1"
    assert "chrome" in rows[1]["details"]


def test_export_is_atomic_and_overwrites(tmp_path: Path) -> None:
    history = _history(tmp_path)
    target = export_json(history, tmp_path / "report.json")
    first = target.read_text(encoding="utf-8")

    history.clear()
    export_json(history, target)

    second = json.loads(target.read_text(encoding="utf-8"))
    assert first != target.read_text(encoding="utf-8")
    assert second["count"] == 0
    assert not target.with_suffix(".json.tmp").exists()


FILTERED = [
    {
        "id": 7,
        "date": "2026-10-24T10:00:00",
        "items_cleaned": 1,
        "bytes_freed": 1024,
        "details": [{"id": "chrome", "status": "OK", "freed": 1024}],
    },
]


def test_build_report_from_entries_totals_subset() -> None:
    report = build_report_from_entries(FILTERED)

    assert report["count"] == 1
    assert report["total_freed"] == 1024
    assert report["entries"] == FILTERED


def test_export_entries_json_writes_only_filtered(tmp_path: Path) -> None:
    target = export_entries_json(FILTERED, tmp_path / "history")

    assert target.suffix == ".json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert [e["id"] for e in payload["entries"]] == [7]


def test_export_entries_csv_serializes_details(tmp_path: Path) -> None:
    target = export_entries_csv(FILTERED, tmp_path / "history.csv")

    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    with open(target, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["id"] == "7"
    assert json.loads(rows[0]["details"])[0]["id"] == "chrome"
