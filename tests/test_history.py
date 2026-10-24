"""Тесты истории очисток (WAL, JSON details, миграция)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from disk_cleaner_app.models.history import HistoryManager


def _manager(tmp_path: Path) -> HistoryManager:
    return HistoryManager(db_path=tmp_path / "history.db")


def test_add_and_read(tmp_path: Path) -> None:
    history = _manager(tmp_path)
    history.add(items_cleaned=3, bytes_freed=1024, details="проверка")

    rows = history.get_recent(10)

    assert len(rows) == 1
    assert rows[0][1] == 3
    assert rows[0][2] == 1024
    assert history.total_freed() == 1024
    assert history.count() == 1


def test_wal_mode_is_enabled(tmp_path: Path) -> None:
    history = _manager(tmp_path)
    with sqlite3.connect(str(history.db_path)) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


def test_details_json_is_parsed(tmp_path: Path) -> None:
    history = _manager(tmp_path)
    payload = [{"id": "chrome", "status": "OK", "freed": 2048}]
    history.add(items_cleaned=1, bytes_freed=2048, details=json.dumps(payload))

    entry = history.get_last()

    assert entry is not None
    assert entry["details"] == payload
    assert entry["bytes_freed"] == 2048


def test_plain_details_are_returned_as_text(tmp_path: Path) -> None:
    history = _manager(tmp_path)
    history.add(1, 10, details="не json")

    entry = history.get_last()

    assert entry is not None
    assert entry["details"] == "не json"


def test_add_operation_serializes_results(tmp_path: Path) -> None:
    history = _manager(tmp_path)
    results = [
        {"id": "a", "status": "OK"},
        {"id": "b", "status": "ERR"},
        {"id": "c", "status": "OK"},
    ]

    history.add_operation(results, bytes_freed=777)

    entry = history.get_last()
    assert entry is not None
    assert entry["items_cleaned"] == 2
    assert entry["bytes_freed"] == 777
    assert [item["id"] for item in entry["details"]] == ["a", "b", "c"]


def test_empty_details_are_none(tmp_path: Path) -> None:
    history = _manager(tmp_path)
    history.add(1, 0)

    assert history.get_last()["details"] is None  # type: ignore[index]


def test_clear_removes_all_rows(tmp_path: Path) -> None:
    history = _manager(tmp_path)
    history.add(1, 1)
    history.add(2, 2)

    history.clear()

    assert history.count() == 0
    assert history.total_freed() == 0


def test_op_type_roundtrip(tmp_path: Path) -> None:
    mgr = HistoryManager(db_path=tmp_path / "h.db")
    mgr.add(1, 100, op_type="smart")
    mgr.add(2, 200, op_type="deep")

    entries = mgr.get_all()

    assert [e["op_type"] for e in entries] == ["deep", "smart"]


def test_v2_database_is_migrated(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "date TEXT, items_cleaned INTEGER, bytes_freed INTEGER, details TEXT)"
        )
        conn.execute("PRAGMA user_version=2")
        conn.execute(
            "INSERT INTO history (date, items_cleaned, bytes_freed, details) "
            "VALUES ('2026-10-01T10:00:00', 1, 50, '')"
        )

    entries = HistoryManager(db_path=db).get_all()

    assert len(entries) == 1
    assert entries[0]["op_type"] == "clean"
