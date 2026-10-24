"""🩺 Здоровье дисков: модель, SMART-счётчики, температура.

Данные берутся из PowerShell (Storage cmdlets), с откатом на WMI
``Win32_DiskDrive``. Модуль только читает информацию, ничего не меняет.
"""
from __future__ import annotations

import json
import logging
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


def list_disks() -> list[dict]:
    """Список физических дисков с SMART-счётчиками (может быть пустым)."""
    try:
        raw = _run_powershell(_PS_SCRIPT)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("PowerShell недоступен: %s", e)
        return []
    return parse_disks_json(raw)
