"""Тесты влияния автозагрузки по Diagnostics-Performance."""
from __future__ import annotations

from disk_cleaner_app.services.startup_impact import (
    attach_impacts,
    command_executable,
    impact_label,
    impact_ms,
    item_keys,
    normalize_record,
    parse_impact_payload,
    record_index,
    status_hint,
)


def _record(name: str, path: str, total_ms: int, time: str = "2026-10-20T10:00:00") -> dict:
    return {"id": 101, "time": time, "name": name, "path": path, "total_ms": total_ms}


def test_command_executable_handles_quotes_and_arguments() -> None:
    assert command_executable(r'"C:\Program Files\Google\Chrome\chrome.exe" --no-startup-window') == "chrome.exe"
    assert command_executable(r"C:\Tools\app.exe /min") == "app.exe"
    assert command_executable(r'"%ProgramFiles%\App\app.exe"') == "app.exe"
    assert command_executable("") == ""


def test_normalize_record_reads_application_and_service_fields() -> None:
    app = normalize_record({
        "id": 101,
        "time": "2026-10-20T10:00:00",
        "data": {"Name": "Chrome", "FilePath": r"C:\Chrome\chrome.exe", "TotalTime": "1500"},
    })
    assert app == {
        "id": 101,
        "time": "2026-10-20T10:00:00",
        "name": "Chrome",
        "path": r"C:\Chrome\chrome.exe",
        "total_ms": 1500,
    }
    service = normalize_record({
        "data": {"ServiceName": "Spooler", "ServicePath": r"C:\spoolsv.exe", "DegradationTime": 700},
    })
    assert service is not None
    assert service["name"] == "Spooler"
    assert service["total_ms"] == 700
    assert normalize_record({"data": {}}) is None
    assert normalize_record("bad") is None


def test_parse_payload_keeps_status_and_drops_bad_records() -> None:
    raw = (
        '{"status":"ok","records":['
        '{"data":{"Name":"a.exe","TotalTime":120}},'
        '{"data":{}},{"bad":1}]}'
    )
    parsed = parse_impact_payload(raw)
    assert parsed["status"] == "ok"
    assert len(parsed["records"]) == 1
    assert parse_impact_payload('{"status":"denied","reason":"nope"}')["status"] == "denied"
    assert parse_impact_payload("")["status"] == "error"
    assert parse_impact_payload("not json")["status"] == "error"


def test_impact_matches_exe_and_uses_median_of_recent_events() -> None:
    records = [
        _record("Chrome", r"C:\Chrome\chrome.exe", 1000, "2026-10-01T10:00:00"),
        _record("Chrome", r"C:\Chrome\chrome.exe", 5000, "2026-10-02T10:00:00"),
        _record("Chrome", r"C:\Chrome\chrome.exe", 3000, "2026-10-03T10:00:00"),
        _record("Other", r"C:\Other\other.exe", 9000, "2026-10-04T10:00:00"),
    ]
    index = record_index(records)
    item = {"name": "Google Chrome", "command": r'"C:\Chrome\chrome.exe" --flag'}
    assert impact_ms(item, index) == 3000


def test_impact_keeps_only_ten_latest_events_per_app() -> None:
    records = [
        _record("app", r"C:\app.exe", 100 if i < 5 else 9000, f"2026-10-{i + 1:02d}T10:00:00")
        for i in range(12)
    ]
    item = {"name": "app", "command": r"C:\app.exe"}
    # 12 событий: берём 10 самых свежих — 8 медленных и 2 быстрых.
    assert impact_ms(item, record_index(records)) == 9000


def test_impact_matches_name_tokens_for_updaters() -> None:
    records = [
        _record("Teams", r"C:\Teams\Teams.exe", 3200),
        _record("Unrelated", r"C:\Other\other.exe", 100),
    ]
    item = {
        "name": "Microsoft Teams",
        "command": r'"C:\Users\demo\AppData\Local\Microsoft\Teams\Update.exe" --processStart Teams.exe',
    }
    assert impact_ms(item, record_index(records)) == 3200


def test_impact_matches_service_and_returns_none_without_data() -> None:
    records = [
        _record("Spooler", r"C:\spoolsv.exe", 2500),
        _record("Chrome", r"C:\Chrome\chrome.exe", 500),
    ]
    index = record_index(records)
    service = {"kind": "service", "name": "Print Spooler", "service_name": "Spooler"}
    assert impact_ms(service, index) == 2500
    assert impact_ms({"name": "Unknown", "command": ""}, index) is None


def test_impact_label_thresholds() -> None:
    assert impact_label(None) == "—"
    assert "низкое" in impact_label(999)
    assert "среднее" in impact_label(1000)
    assert "среднее" in impact_label(2999)
    assert "высокое" in impact_label(3000)
    assert "1.5 с" in impact_label(1500)


def test_attach_impacts_sets_values_on_every_item() -> None:
    items = [
        {"name": "Chrome", "command": r"C:\Chrome\chrome.exe"},
        {"name": "Unknown", "command": ""},
    ]
    attach_impacts(items, record_index([_record("Chrome", r"C:\Chrome\chrome.exe", 1200)]))
    assert items[0]["impact_ms"] == 1200
    assert "среднее" in items[0]["impact_label"]
    assert items[1]["impact_ms"] is None
    assert items[1]["impact_label"] == "—"


def test_item_keys_include_command_and_service() -> None:
    keys = item_keys({"name": "Chrome", "command": r'"C:\Chrome\chrome.exe" --x'})
    assert "chrome.exe" in keys
    keys = item_keys({"name": "Print Spooler", "service_name": "Spooler"})
    assert "spooler" in keys


def test_status_hint_explains_missing_data() -> None:
    assert "права" in status_hint("denied")
    assert "нет событий" in status_hint("empty")
    assert "медиана" in status_hint("ok")
    assert "недоступен" in status_hint("error")
