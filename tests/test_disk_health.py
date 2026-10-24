"""Тесты разбора SMART-данных и форматирования дисков."""
from __future__ import annotations

import json

from disk_cleaner_app.services.disk_health import (
    format_disk_row,
    format_hours,
    health_code,
    health_icon,
    normalize_disk,
    parse_disks_json,
)


def _raw(index: int = 0, health: str = "Healthy") -> dict:
    return {
        "index": index,
        "model": "Samsung SSD 870",
        "serial": "S123",
        "media": "SSD",
        "bus": "SATA",
        "size": 500_107_862_016,
        "health": health,
        "status": "OK",
        "temperature": 35,
        "hours": 30,
        "wear": 4,
        "read_errors": 0,
        "write_errors": 0,
    }


def test_parse_single_object() -> None:
    disks = parse_disks_json(json.dumps(_raw()))

    assert len(disks) == 1
    assert disks[0]["model"] == "Samsung SSD 870"
    assert disks[0]["health"] == "OK"
    assert disks[0]["temperature"] == 35


def test_parse_list_is_sorted_by_index() -> None:
    disks = parse_disks_json(json.dumps([_raw(2), _raw(0), _raw(1)]))

    assert [d["index"] for d in disks] == [0, 1, 2]


def test_parse_empty_and_broken_output() -> None:
    assert parse_disks_json("") == []
    assert parse_disks_json("null") == []
    assert parse_disks_json("не json") == []


def test_normalize_missing_fields() -> None:
    disk = normalize_disk({"index": "3", "model": None, "size": None})

    assert disk["index"] == 3
    assert disk["model"] == "Неизвестный диск"
    assert disk["size"] == 0
    assert disk["health"] == "?"
    assert disk["temperature"] is None


def test_health_mapping() -> None:
    assert health_code("Healthy") == "OK"
    assert health_code("warning") == "WARN"
    assert health_code("Unhealthy") == "BAD"
    assert health_code("") == "?"
    assert health_icon("BAD") == "❌"


def test_format_hours() -> None:
    assert format_hours(None) == "—"
    assert format_hours(0) == "—"
    assert format_hours(5) == "5 ч"
    assert format_hours(29) == "1 д 5 ч"


def test_format_disk_row() -> None:
    row = format_disk_row(normalize_disk(_raw()))

    assert row[0] == "0"
    assert "Samsung" in row[1]
    assert "SATA" in row[2]
    assert "ГБ" in row[3]
    assert "✅ OK" in row[4]
    assert row[5] == "35 °C"
    assert row[6] == "1 д 6 ч"
    assert row[7] == "4%"
