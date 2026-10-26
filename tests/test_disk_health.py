"""Тесты разбора SMART-данных и форматирования дисков."""
from __future__ import annotations

import json

from disk_cleaner_app.services.disk_health import (
    attach_smart,
    format_disk_row,
    format_hours,
    format_temperature,
    health_code,
    health_icon,
    match_smart_record,
    normalize_disk,
    parse_disks_json,
    parse_smart_bytes,
    parse_smart_records,
    smart_rows,
    smart_summary,
    temperature_zone,
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


def _smart_bytes(entries: list[tuple[int, int, int, int]]) -> list[int]:
    data = [0x00, 0x10]
    for attr_id, value, worst, raw in entries:
        data.extend([attr_id, 0x00, 0x00, value, worst])
        data.extend(raw.to_bytes(6, "little"))
        data.append(0x00)  # резервный байт записи
    return data


def test_temperature_zone_boundaries() -> None:
    assert temperature_zone(None)[0] == "unknown"
    assert temperature_zone(0)[0] == "unknown"
    assert temperature_zone(44)[0] == "ok"
    assert temperature_zone(45)[0] == "warm"
    assert temperature_zone(54)[0] == "warm"
    assert temperature_zone(55)[0] == "hot"
    assert temperature_zone(64)[0] == "hot"
    assert temperature_zone(65)[0] == "critical"
    assert format_temperature(42) == "42 °C · норма"
    assert format_temperature(None) == "—"


def test_parse_smart_bytes_reads_attributes() -> None:
    attrs = parse_smart_bytes(_smart_bytes([
        (5, 100, 100, 3),
        (9, 99, 99, 12_345),
        (197, 100, 100, 0),
    ]))

    assert attrs[5]["raw"] == 3
    assert attrs[9]["raw"] == 12_345
    assert attrs[197]["raw"] == 0
    assert attrs[5]["value"] == 100
    assert attrs[5]["worst"] == 100
    assert attrs[5]["flags"] == 0


def test_parse_smart_bytes_handles_bad_input() -> None:
    assert parse_smart_bytes([]) == {}
    assert parse_smart_bytes(None) == {}
    assert parse_smart_bytes(["не байты"]) == {}
    assert parse_smart_bytes([0, 16, 0]) == {}


def test_match_smart_record_by_model_token() -> None:
    records = [
        {"instance": r"SCSI\DISK&VEN_WDC&PROD_WDS240G2G0B-00EPW0\5&1", "bytes": [0]},
    ]
    assert match_smart_record("WDC WDS240G2G0B-00EPW0", records) is records[0]
    assert match_smart_record("Samsung SSD 870", records) is None
    assert match_smart_record("", records) is None


def test_attach_smart_and_rows() -> None:
    disks = [normalize_disk(_raw())]
    attach_smart(disks, [{
        "instance": r"SCSI\DISK&VEN_WDC&PROD_SAMSUNG",
        "bytes": _smart_bytes([
            (5, 100, 100, 0),
            (9, 99, 99, 30),
            (194, 60, 50, 42),
        ]),
    }])

    rows = smart_rows(disks[0])
    titles = [title for title, _value, _mark in rows]
    assert titles == ["Reallocated sectors", "Power-on hours", "Temperature"]
    assert rows[0][1] == "0" and rows[0][2] == "✅"
    assert rows[1][1] == "1 д 6 ч"
    assert rows[2][1] == "42 °C · норма"
    summary = smart_summary(disks[0])
    assert "reallocated: 0" in summary
    assert "темп.: 42 °C · норма" in summary
    assert "✅" not in summary


def test_attach_smart_handles_missing_record() -> None:
    disks = [normalize_disk(_raw())]
    attach_smart(disks, [])

    assert disks[0]["smart_attributes"] == {}
    assert disks[0]["smart_source"] == ""
    assert smart_rows(disks[0]) == []


def test_parse_smart_records() -> None:
    payload = json.dumps({"instance": "SCSI\\DISK", "bytes": [1, 2, 3]})
    assert parse_smart_records(payload) == [
        {"instance": "SCSI\\DISK", "bytes": [1, 2, 3]}
    ]
    assert parse_smart_records("") == []
    assert parse_smart_records("не json") == []
    assert parse_smart_records("null") == []
