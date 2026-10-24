"""Тесты фильтрации журнала очисток."""
from __future__ import annotations

from disk_cleaner_app.services.history_filter import (
    filter_entries,
    format_details,
    parse_date,
    summarize_details,
    total_freed,
)

ENTRIES = [
    {
        "id": 3,
        "date": "2026-10-24T12:00:00",
        "items_cleaned": 2,
        "bytes_freed": 2048,
        "details": [
            {"name": "Chrome cache", "status": "OK", "freed": 1024},
            {"name": "Temp", "status": "ERR", "freed": 0, "note": "занято"},
        ],
    },
    {
        "id": 2,
        "date": "2026-09-01T08:30:00",
        "items_cleaned": 0,
        "bytes_freed": 0,
        "details": None,
    },
    {
        "id": 1,
        "date": "2025-12-31T23:59:00",
        "items_cleaned": 1,
        "bytes_freed": 512,
        "details": "старый формат",
    },
]


def test_parse_date() -> None:
    assert parse_date("2026-10-24").isoformat() == "2026-10-24"
    assert parse_date("") is None
    assert parse_date("24.10.2026") is None


def test_filter_by_date_range_is_inclusive() -> None:
    result = filter_entries(ENTRIES, "2026-09-01", "2026-10-24")

    assert [e["id"] for e in result] == [3, 2]


def test_empty_dates_do_not_filter() -> None:
    assert [e["id"] for e in filter_entries(ENTRIES)] == [3, 2, 1]


def test_invalid_date_is_ignored() -> None:
    result = filter_entries(ENTRIES, date_from="не дата")

    assert len(result) == 3


def test_query_matches_target_and_status() -> None:
    assert [e["id"] for e in filter_entries(ENTRIES, query="chrome")] == [3]
    assert [e["id"] for e in filter_entries(ENTRIES, query="err")] == [3]
    assert [e["id"] for e in filter_entries(ENTRIES, query="формат")] == [1]
    assert filter_entries(ENTRIES, query="нет такого") == []


def test_query_and_dates_combine() -> None:
    assert [e["id"] for e in filter_entries(
        ENTRIES, date_from="2026-01-01", query="temp"
    )] == [3]
    assert filter_entries(
        ENTRIES, date_from="2026-10-25", query="temp"
    ) == []


def test_summarize_details() -> None:
    assert summarize_details(ENTRIES[0]) == "Chrome cache, Temp"
    assert summarize_details(ENTRIES[1]) == "—"
    assert summarize_details(ENTRIES[2]) == "старый формат"


def test_format_details_lists_each_target() -> None:
    text = format_details(ENTRIES[0])

    assert "Chrome cache" in text
    assert "Temp" in text
    assert "✅" in text and "❌" in text
    assert "2.0 КБ" in text


def test_total_freed() -> None:
    assert total_freed(ENTRIES) == 2560
