"""🩺 Здоровье дисков: модель, SMART-счётчики, температура.

Данные берутся из PowerShell (Storage cmdlets), с откатом на WMI
``Win32_DiskDrive``. Модуль только читает информацию, ничего не меняет.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Any

from disk_cleaner_app.models.item import format_bytes

log = logging.getLogger(__name__)

HEALTH_LABELS = {
    "healthy": "OK",
    "warning": "WARN",
    "unhealthy": "BAD",
    "unknown": "?",
}

HEALTH_ICONS = {"OK": "✅", "WARN": "⚠️", "BAD": "❌", "?": "❔"}

# Атрибуты ATA SMART, которые полезны пользователю и не требуют догадок.
SMART_ATTRIBUTES = {
    5: "Reallocated sectors",
    9: "Power-on hours",
    194: "Temperature",
    197: "Pending sectors",
    198: "Uncorrectable",
}

SMART_SHORT = {
    5: "reallocated",
    9: "наработка",
    194: "темп.",
    197: "pending",
    198: "uncorrectable",
}

TEMP_ZONES = {
    "ok": ("норма", "✅"),
    "warm": ("повышена", "⚠️"),
    "hot": ("высокая", "🔥"),
    "critical": ("критическая", "❌"),
    "unknown": ("нет данных", "—"),
}

_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$result = @()
try {
  $result = Get-PhysicalDisk | ForEach-Object {
    $d = $_
    $r = $null
    try { $r = $d | Get-StorageReliabilityCounter } catch {}
    [pscustomobject]@{
      index = [int]$d.DeviceId
      model = [string]$d.FriendlyName
      serial = [string]$d.SerialNumber
      media = [string]$d.MediaType
      bus = [string]$d.BusType
      size = [int64]$d.Size
      health = [string]$d.HealthStatus
      status = (@($d.OperationalStatus) -join ',')
      temperature = if ($r) { $r.Temperature } else { $null }
      hours = if ($r) { $r.PowerOnHours } else { $null }
      wear = if ($r) { $r.Wear } else { $null }
      read_errors = if ($r) { $r.ReadErrorsTotal } else { $null }
      write_errors = if ($r) { $r.WriteErrorsTotal } else { $null }
    }
  }
} catch {}
if (-not $result) {
  $result = Get-CimInstance Win32_DiskDrive | ForEach-Object {
    [pscustomobject]@{
      index = [int]$_.Index
      model = [string]$_.Model
      serial = [string]$_.SerialNumber
      media = [string]$_.MediaType
      bus = [string]$_.InterfaceType
      size = [int64]$_.Size
      health = if ($_.Status -eq 'OK') { 'Healthy' } else { 'Warning' }
      status = [string]$_.Status
      temperature = $null
      hours = $null
      wear = $null
      read_errors = $null
      write_errors = $null
    }
  }
}
$result | ConvertTo-Json -Depth 4 -Compress
"""

_SMART_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$result = @()
try {
  $result = Get-CimInstance -Namespace root/wmi -ClassName MSStorageDriver_ATAPISmartData |
    ForEach-Object {
      [pscustomobject]@{
        instance = [string]$_.InstanceName
        bytes = @($_.VendorSpecific)
      }
    }
} catch {}
$result | ConvertTo-Json -Depth 4 -Compress
"""


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def health_code(status: Any) -> str:
    """Привести HealthStatus к ``OK`` / ``WARN`` / ``BAD`` / ``?``."""
    return HEALTH_LABELS.get(str(status or "").strip().lower(), "?")


def health_icon(code: str) -> str:
    return HEALTH_ICONS.get(code, "❔")


def temperature_zone(temp: int | None) -> tuple[str, str, str]:
    """Температура → (код, подпись, иконка).

    Порог 45 °C — спокойно, 55 °C — повышенная, 65 °C — высокая.
    Для NVMe те же границы: производители обычно держат троттлинг
    в районе 70–80 °C, поэтому 65 °C уже повод проверить охлаждение.
    """
    if not isinstance(temp, int) or temp <= 0:
        return ("unknown", *TEMP_ZONES["unknown"])
    if temp < 45:
        return ("ok", *TEMP_ZONES["ok"])
    if temp < 55:
        return ("warm", *TEMP_ZONES["warm"])
    if temp < 65:
        return ("hot", *TEMP_ZONES["hot"])
    return ("critical", *TEMP_ZONES["critical"])


def format_temperature(temp: int | None) -> str:
    """Температура с зоной: «42 °C · норма» / «—»."""
    if not isinstance(temp, int) or temp <= 0:
        return "—"
    _code, label, _icon = temperature_zone(temp)
    return f"{temp} °C · {label}"


def parse_smart_bytes(values: Any) -> dict[int, dict]:
    """Разобрать ``VendorSpecific`` ATA SMART в словарь по ID атрибута.

    Формат: 2 байта версии, затем записи по 12 байт:
    id, flags (2), value, worst, raw (6, little-endian).
    """
    try:
        data = [int(v) & 0xFF for v in values]
    except (TypeError, ValueError):
        return {}
    attrs: dict[int, dict] = {}
    for offset in range(2, len(data) - 11, 12):
        attr_id = data[offset]
        if attr_id == 0:
            continue
        raw_bytes = data[offset + 5:offset + 11]
        attrs[attr_id] = {
            "id": attr_id,
            "flags": data[offset + 1] | (data[offset + 2] << 8),
            "value": data[offset + 3],
            "worst": data[offset + 4],
            "raw": int.from_bytes(bytes(raw_bytes), "little"),
        }
    return attrs


def _model_tokens(model: str) -> list[str]:
    tokens = [
        token.casefold()
        for token in re.split(r"[\s_\-]+", model or "")
        if len(token) >= 4
    ]
    return sorted(tokens, key=len, reverse=True)


def match_smart_record(model: str, records: list[dict]) -> dict | None:
    """Найти запись WMI по модели диска (InstanceName содержит VEN/PROD)."""
    tokens = _model_tokens(model)
    if not tokens or not records:
        return None
    for record in records:
        instance = str(record.get("instance") or "").casefold()
        if instance and any(token in instance for token in tokens):
            return record
    return None


def attach_smart(disks: list[dict], records: list[dict]) -> None:
    """Добавить к дискам разобранные ATA-атрибуты (если WMI их отдал)."""
    for disk in disks:
        record = match_smart_record(str(disk.get("model") or ""), records)
        attrs = parse_smart_bytes(record.get("bytes")) if record else {}
        disk["smart_attributes"] = {
            attr_id: attrs[attr_id]
            for attr_id in SMART_ATTRIBUTES
            if attr_id in attrs
        }
        disk["smart_source"] = "ata" if disk["smart_attributes"] else ""


def smart_rows(disk: dict) -> list[tuple[str, str, str]]:
    """Строки для панели деталей: (атрибут, значение, статус)."""
    attrs = disk.get("smart_attributes") or {}
    rows: list[tuple[str, str, str]] = []
    for attr_id, title in SMART_ATTRIBUTES.items():
        info = attrs.get(attr_id)
        if not info:
            continue
        raw = int(info.get("raw") or 0)
        if attr_id == 9:
            rows.append((title, format_hours(raw), ""))
        elif attr_id == 194:
            temp = raw & 0xFF if raw else None
            _code, _label, icon = temperature_zone(temp)
            rows.append((title, format_temperature(temp), icon))
        else:
            rows.append((title, str(raw), "✅" if raw == 0 else "⚠️"))
    return rows


def smart_summary(disk: dict) -> str:
    """Компактная строка атрибутов: «reallocated: 0 · pending: 0 · …»."""
    parts = []
    for title, value, mark in smart_rows(disk):
        attr_id = next(k for k, v in SMART_ATTRIBUTES.items() if v == title)
        prefix = SMART_SHORT.get(attr_id, title)
        parts.append(f"{prefix}: {value}" + (f" {mark}" if mark and mark != "✅" else ""))
    return " · ".join(parts)


def normalize_disk(raw: dict) -> dict:
    """Привести запись PowerShell к стабильному виду."""
    size = _as_int(raw.get("size")) or 0
    disk = {
        "index": _as_int(raw.get("index")) or 0,
        "model": str(raw.get("model") or "Неизвестный диск").strip(),
        "serial": str(raw.get("serial") or "").strip(),
        "media": str(raw.get("media") or "").strip(),
        "bus": str(raw.get("bus") or "").strip(),
        "size": size,
        "health": health_code(raw.get("health")),
        "status": str(raw.get("status") or "").strip(),
        "temperature": _as_int(raw.get("temperature")),
        "hours": _as_int(raw.get("hours")),
        "wear": _as_int(raw.get("wear")),
        "read_errors": _as_int(raw.get("read_errors")),
        "write_errors": _as_int(raw.get("write_errors")),
    }
    return disk


def parse_disks_json(raw: str) -> list[dict]:
    """Разобрать вывод ``ConvertTo-Json`` (объект, список, пусто)."""
    text = (raw or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Не удалось разобрать SMART-вывод: %s", text[:200])
        return []

    if payload is None:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []

    disks = [
        normalize_disk(item) for item in payload if isinstance(item, dict)
    ]
    disks.sort(key=lambda d: d["index"])
    return disks


def format_hours(hours: int | None) -> str:
    """Часы наработки → «1 д 5 ч» / «—»."""
    if not hours or hours <= 0:
        return "—"
    days, rest = divmod(int(hours), 24)
    if days:
        return f"{days} д {rest} ч"
    return f"{rest} ч"


def format_disk_row(disk: dict) -> tuple[str, ...]:
    """Строка таблицы: №, модель, шина, размер, здоровье, t°, часы, износ."""
    temp = disk.get("temperature")
    wear = disk.get("wear")
    return (
        str(disk.get("index", 0)),
        disk.get("model", "—"),
        disk.get("bus") or disk.get("media") or "—",
        format_bytes(int(disk.get("size") or 0)),
        f"{health_icon(disk.get('health', '?'))} {disk.get('health', '?')}",
        f"{temp} °C" if isinstance(temp, int) and temp > 0 else "—",
        format_hours(disk.get("hours")),
        f"{wear}%" if isinstance(wear, int) and wear >= 0 else "—",
    )


def _run_powershell(script: str, timeout: int = 30) -> str:
    """Выполнить PowerShell без окна и вернуть stdout (UTF-8)."""
    completed = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-Command", script,
        ],
        capture_output=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return completed.stdout.decode("utf-8", errors="replace")


def parse_smart_records(raw: str) -> list[dict]:
    """Разобрать вывод WMI с сырыми ATA-атрибутами."""
    text = (raw or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Не удалось разобрать SMART-атрибуты: %s", text[:200])
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    return [
        item for item in payload
        if isinstance(item, dict) and item.get("instance")
    ]


def read_smart_records() -> list[dict]:
    """Сырые ATA-атрибуты через WMI (нужны права администратора)."""
    try:
        raw = _run_powershell(_SMART_SCRIPT, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        log.info("Сырые SMART-атрибуты недоступны: %s", e)
        return []
    return parse_smart_records(raw)


def list_disks() -> list[dict]:
    """Список физических дисков с SMART-счётчиками (может быть пустым)."""
    try:
        raw = _run_powershell(_PS_SCRIPT)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("PowerShell недоступен: %s", e)
        return []
    disks = parse_disks_json(raw)
    if disks:
        attach_smart(disks, read_smart_records())
    return disks
