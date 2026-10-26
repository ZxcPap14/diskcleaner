"""Влияние записей автозагрузки по журналу Diagnostics-Performance.

Windows пишет в ``Microsoft-Windows-Diagnostics-Performance/Operational``
события о медленном старте приложений, служб и драйверов. Журнал доступен
только администратору, поэтому при отказе доступа честно возвращаем
``denied`` и показываем «—», а не выдуманную оценку.

Считаем медиану ``TotalTime`` по последним 10 событиям для каждого
исполняемого файла и переводим её в тег «низкое / среднее / высокое».
Это наша метрика по времени, а не точная копия шкалы Task Manager.
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
from pathlib import Path

LOG_NAME = "Microsoft-Windows-Diagnostics-Performance/Operational"
EVENT_IDS = (101, 102, 103)
MAX_EVENTS = 500
RECENT_PER_APP = 10
LOW_MS = 1000
MEDIUM_MS = 3000

_PS_SCRIPT = rf"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try {{
    $events = Get-WinEvent -FilterHashtable @{{
        LogName = '{LOG_NAME}'
        Id = 101,102,103
        StartTime = (Get-Date).AddDays(-30)
    }} -MaxEvents {MAX_EVENTS}
}} catch {{
    $msg = $_.Exception.Message
    $status = 'error'
    if ($msg -match 'unauthorized|elevated|Access is denied|доступ') {{
        $status = 'denied'
    }} elseif ($msg -match 'No events were found|найти события|найдены события|Нет событий') {{
        $status = 'empty'
    }}
    [pscustomobject]@{{ status = $status; reason = $msg }} |
        ConvertTo-Json -Compress
    exit
}}
$out = @()
foreach ($event in $events) {{
    try {{ $xml = [xml]$event.ToXml() }} catch {{ continue }}
    $data = @{{}}
    foreach ($node in $xml.Event.EventData.Data) {{
        $name = [string]$node.GetAttribute('Name')
        if ($name) {{ $data[$name] = [string]$node.InnerText }}
    }}
    $out += [pscustomobject]@{{
        id = [int]$event.Id
        time = $event.TimeCreated.ToString('o')
        data = $data
    }}
}}
[pscustomobject]@{{ status = 'ok'; records = @($out) }} |
    ConvertTo-Json -Compress -Depth 6
"""


def _run_ps(script: str, timeout: int) -> tuple[str, str]:
    """PowerShell с UTF-8 на выходе: имена путей могут быть кириллицей."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT"
    except OSError as exc:
        return "", str(exc)


def _int_ms(value: object) -> int | None:
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def normalize_record(raw: object) -> dict | None:
    """Событие журнала -> запись с именем, путём и временем старта."""
    if not isinstance(raw, dict):
        return None
    data = raw.get("data")
    if not isinstance(data, dict):
        return None
    name = ""
    for key in ("Name", "ApplicationName", "ServiceName", "DriverName"):
        value = str(data.get(key) or "").strip()
        if value:
            name = value
            break
    path = ""
    for key in ("FilePath", "ServicePath", "DriverPath", "Path"):
        value = str(data.get(key) or "").strip()
        if value:
            path = value
            break
    total = None
    for key in ("TotalTime", "DegradationTime"):
        total = _int_ms(data.get(key))
        if total is not None:
            break
    if not name and not path:
        return None
    return {
        "id": raw.get("id"),
        "time": str(raw.get("time") or ""),
        "name": name,
        "path": path,
        "total_ms": total or 0,
    }


def parse_impact_payload(raw: str) -> dict:
    """Разобрать JSON от PowerShell, не падая на ошибках доступа."""
    text = (raw or "").strip()
    if not text:
        return {"status": "error", "reason": "пустой ответ", "records": []}
    try:
        payload = json.loads(text)
    except ValueError:
        return {"status": "error", "reason": "некорректный JSON", "records": []}
    if not isinstance(payload, dict):
        return {"status": "error", "reason": "неожиданный ответ", "records": []}
    status = str(payload.get("status") or "ok")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raw_records = []
    records = [rec for rec in (normalize_record(r) for r in raw_records) if rec]
    return {
        "status": status,
        "reason": str(payload.get("reason") or ""),
        "records": records,
    }


def read_startup_impact(timeout: int = 20) -> dict:
    out, err = _run_ps(_PS_SCRIPT, timeout)
    if err == "TIMEOUT":
        return {"status": "error", "reason": "таймаут чтения журнала", "records": []}
    if not out:
        reason = err or "пустой ответ"
        status = "denied" if "denied" in reason.lower() else "error"
        return {"status": status, "reason": reason, "records": []}
    return parse_impact_payload(out)


def command_executable(command: str) -> str:
    """Имя exe из командной строки записи (с кавычками и аргументами)."""
    text = (command or "").strip()
    if not text:
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        token = text[1:end] if end > 1 else text[1:]
    else:
        token = text.split()[0]
    return Path(token.replace("/", "\\")).name.casefold()


_GENERIC_TOKENS = {
    "update", "updater", "setup", "install", "installer", "service",
    "system", "windows", "microsoft", "program", "application", "helper",
}


def _name_keys(value: str) -> set[str]:
    value = (value or "").strip()
    if not value:
        return set()
    name = Path(value.replace("/", "\\")).name.casefold()
    keys = {name}
    stem = Path(name).stem
    if stem:
        keys.add(stem)
    if name.endswith(".exe"):
        keys.add(name[:-4])
    for token in re.split(r"[^0-9a-zа-яё]+", stem):
        if len(token) >= 4 and token not in _GENERIC_TOKENS:
            keys.add(token)
    return keys


def _record_keys(record: dict) -> set[str]:
    keys = _name_keys(record.get("path", "")) | _name_keys(record.get("name", ""))
    return {key for key in keys if len(key) >= 4}


def record_index(records: list[dict]) -> dict[str, list[dict]]:
    """Ключ (имя exe/службы) -> события, свежие первыми."""
    index: dict[str, list[dict]] = {}
    for record in records:
        for key in _record_keys(record):
            index.setdefault(key, []).append(record)
    for events in index.values():
        events.sort(key=lambda r: str(r.get("time") or ""), reverse=True)
    return index


def item_keys(item: dict) -> set[str]:
    keys = _name_keys(str(item.get("service_name") or ""))
    keys |= _name_keys(str(item.get("name") or ""))
    exe = command_executable(str(item.get("command") or ""))
    if exe:
        keys |= _name_keys(exe)
    return {key for key in keys if len(key) >= 4}


def impact_ms(item: dict, index: dict[str, list[dict]]) -> int | None:
    """Медиана старта по последним событиям; None, если совпадений нет."""
    events: list[dict] = []
    seen: set[tuple[str, object]] = set()
    for key in item_keys(item):
        for record in index.get(key, [])[:RECENT_PER_APP]:
            marker = (str(record.get("time") or ""), record.get("id"))
            if marker in seen:
                continue
            seen.add(marker)
            if int(record.get("total_ms") or 0) > 0:
                events.append(record)
    if not events:
        return None
    events.sort(key=lambda r: str(r.get("time") or ""), reverse=True)
    durations = [int(r["total_ms"]) for r in events[:RECENT_PER_APP]]
    return int(statistics.median(durations))


def impact_label(milliseconds: int | None) -> str:
    if milliseconds is None:
        return "—"
    seconds = milliseconds / 1000
    if milliseconds < LOW_MS:
        tag = "🟢 низкое"
    elif milliseconds < MEDIUM_MS:
        tag = "🟡 среднее"
    else:
        tag = "🔴 высокое"
    return f"{tag} · {seconds:.1f} с"


def attach_impacts(items: list[dict], index: dict[str, list[dict]]) -> None:
    for item in items:
        value = impact_ms(item, index)
        item["impact_ms"] = value
        item["impact_label"] = impact_label(value)


def status_hint(status: str) -> str:
    return {
        "ok": "влияние — медиана запуска за 30 дней",
        "denied": "влияние: нужны права администратора",
        "empty": "влияние: нет событий (или нет доступа)",
        "error": "влияние: журнал недоступен",
    }.get(status, "влияние: нет данных")
