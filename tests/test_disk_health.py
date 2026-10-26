"""Тесты разбора SMART-данных и форматирования дисков."""
from __future__ import annotations

import json

from disk_cleaner_app.services.disk_health import (
    attach_smart,
    format_disk_row,
    format_hours,
    format_temperature,
    health_badge,
    health_code,
    health_icon,
    match_smart_record,
    normalize_disk,
    parse_disks_json,
    parse_smart_bytes,
    parse_smart_payload,
    parse_smart_records,
    parse_threshold_bytes,
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
            (197, 100, 100, 0),
            (241, 90, 80, 123_456),
        ]),
    }])

    rows = smart_rows(disks[0])
    # Полная таблица: все переданные атрибуты, отсортированы по ID.
    titles = [title for title, _value, _mark in rows]
    assert titles == [
        "Reallocated sectors [5]",
        "Power-on hours [9]",
        "Temperature [194]",
        "Pending sectors [197]",
        "Total LBAs written [241]",
    ]
    assert rows[0][1] == "100/100 · raw 0" and rows[0][2] == ""
    assert rows[1][1] == "1 д 6 ч"
    assert rows[2][1] == "42 °C · норма"
    assert rows[4][1] == "90/80 · raw 123456"
    assert disks[0]["smart_source"] == "ata"

    summary = smart_summary(disks[0])
    assert "reallocated: 100/100 · raw 0" in summary
    assert "темп.: 42 °C · норма" in summary
    # Ключевые атрибуты только: Total LBAs в компактную строку не попадает.
    assert "LBAs" not in summary


def test_attach_smart_with_thresholds() -> None:
    instance = r"SCSI\DISK&VEN_WDC&PROD_SAMSUNG"
    thresholds_blob = [0x00, 0x10]
    thresholds_blob.extend([5, 36])
    thresholds_blob.extend(bytes(10))

    disks = [normalize_disk(_raw())]
    attach_smart(
        disks,
        [{"instance": instance, "bytes": _smart_bytes([(5, 40, 20, 128)])}],
        [{"instance": instance, "bytes": thresholds_blob}],
    )

    rows = smart_rows(disks[0])
    assert rows[0][1] == "40/20 · порог 36 · raw 128"
    assert rows[0][2] == "⚠️"


def test_attach_smart_counters_source_for_nvme_style() -> None:
    """Без ATA-данных, но со счётчиками — источник counters, строки из них."""
    disks = [normalize_disk(_raw())]
    attach_smart(disks, [])

    assert disks[0]["smart_source"] == "counters"
    rows = smart_rows(disks[0])
    titles = [title for title, _v, _m in rows]
    assert "Температура" in titles
    assert "Наработка" in titles
    assert "Износ (Wear)" in titles
    assert ("Ошибки чтения", "0", "✅") in rows


def test_attach_smart_handles_no_data_at_all() -> None:
    disk = normalize_disk({**_raw(), "temperature": None, "hours": None,
                           "wear": None, "read_errors": None,
                           "write_errors": None})
    attach_smart([disk], [])

    assert disk["smart_attributes"] == {}
    assert disk["smart_source"] == ""
    assert smart_rows(disk) == []


def test_health_badge_logic() -> None:
    disk = normalize_disk(_raw())
    assert health_badge(disk) == ("good", "хорошее", "✅")

    warn_disk = normalize_disk(_raw(health="Warning"))
    assert health_badge(warn_disk) == ("caution", "внимание", "⚠️")

    bad_disk = normalize_disk(_raw(health="Unhealthy"))
    assert health_badge(bad_disk) == ("bad", "плохое", "❌")

    hot_disk = normalize_disk(_raw())
    hot_disk["temperature"] = 70
    assert health_badge(hot_disk) == ("caution", "внимание", "⚠️")

    critical = normalize_disk(_raw())
    attach_smart(
        [critical],
        [{"instance": r"SCSI\DISK&VEN_WDC&PROD_SAMSUNG",
          "bytes": _smart_bytes([(197, 100, 100, 7)])}],
    )
    assert health_badge(critical) == ("caution", "внимание", "⚠️")

    empty = normalize_disk({**_raw(), "temperature": None, "hours": None,
                            "wear": None, "read_errors": None,
                            "write_errors": None})
    attach_smart([empty], [])
    assert health_badge(empty) == ("unknown", "нет данных", "❔")


def test_parse_threshold_bytes_both_layouts() -> None:
    # Основной расклад: порог во втором байте записи.
    primary = _smart_bytes([(5, 100, 100, 0), (197, 100, 100, 0)])
    assert parse_threshold_bytes(primary) == {5: 0, 197: 0}

    # Альтернативный расклад: порог в третьем байте — берём его,
    # если основной не сошёлся (все пороги ≤ 100).
    shifted = [0x00, 0x10]
    for attr_id, threshold in ((5, 10), (197, 0)):
        shifted.extend([attr_id, 0xEE, threshold])
        shifted.extend(bytes(9))
    assert parse_threshold_bytes(shifted) == {5: 10, 197: 0}

    assert parse_threshold_bytes(None) == {}
    assert parse_threshold_bytes([0, 16, 0]) == {}


def test_parse_smart_payload_new_and_old_shapes() -> None:
    new_shape = json.dumps({
        "smart": [{"instance": "A", "bytes": [1]}],
        "thresholds": [{"instance": "A", "bytes": [2]}],
    })
    smart, thresholds = parse_smart_payload(new_shape)
    assert len(smart) == 1 and len(thresholds) == 1

    old_shape = json.dumps([{"instance": "A", "bytes": [1]}])
    smart, thresholds = parse_smart_payload(old_shape)
    assert len(smart) == 1 and thresholds == []

    assert parse_smart_payload("") == ([], [])
    assert parse_smart_payload("null") == ([], [])


def test_parse_smart_records() -> None:
    payload = json.dumps({"instance": "SCSI\\DISK", "bytes": [1, 2, 3]})
    assert parse_smart_records(payload) == [
        {"instance": "SCSI\\DISK", "bytes": [1, 2, 3]}
    ]
    assert parse_smart_records("") == []
    assert parse_smart_records("не json") == []
    assert parse_smart_records("null") == []
