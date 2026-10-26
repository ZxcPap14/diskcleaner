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

# Критические для здоровья атрибуты: ненулевой raw — повод для внимания.
CRITICAL_ATTRS = (5, 187, 196, 197, 198)

SMART_SHORT = {
    5: "reallocated",
    9: "наработка",
    194: "темп.",
    197: "pending",
    198: "uncorrectable",
}

# Стандартные имена ATA-атрибутов для полной таблицы.
ATA_ATTRIBUTE_NAMES = {
    1: "Read error rate",
    2: "Throughput performance",
    3: "Spin-up time",
    4: "Start/stop count",
    5: "Reallocated sectors",
    6: "Read channel margin",
    7: "Seek error rate",
    8: "Seek time performance",
    9: "Power-on hours",
    10: "Spin retry count",
    11: "Calibration retry count",
    12: "Power cycle count",
    13: "Soft read error rate",
    22: "Current helical flyheight",
    170: "Reserved block count (SSD)",
    171: "Program fail count (SSD)",
    172: "Erase fail count (SSD)",
    173: "Wear leveling count (SSD)",
    174: "Unexpected power loss (SSD)",
    175: "Power loss protection failure",
    176: "Erase fail count (chip)",
    177: "Wear range delta",
    178: "Used reserved blocks",
    179: "Used reserved blocks (chip)",
    180: "Unused reserved blocks",
    181: "Program fail count (total)",
    182: "Erase fail count (total)",
    183: "Runtime bad block",
    184: "End-to-end error",
    187: "Reported uncorrectable",
    188: "Command timeout",
    189: "High fly writes",
    190: "Airflow temperature",
    191: "G-sense error rate",
    192: "Power-off retract count",
    193: "Load cycle count",
    194: "Temperature",
    195: "Hardware ECC recovered",
    196: "Reallocation event count",
    197: "Pending sectors",
    198: "Uncorrectable",
    199: "UDMA CRC error",
    200: "Write error rate",
    201: "Soft read error rate",
    202: "Data address mark errors",
    203: "Run out cancel",
    204: "Soft ECC correction",
    205: "Thermal asperity rate",
    206: "Flying height",
    207: "Spin high current",
    208: "Spin buzz",
    209: "Offline seek performance",
    210: "Vibration during write",
    211: "Vibration during read",
    212: "Shock during write",
    220: "Disk shift",
    221: "G-sense error rate",
    222: "Loaded hours",
    223: "Load retry count",
    224: "Load friction",
    225: "Load cycle count",
    226: "Load-in time",
    227: "Torque amplification count",
    228: "Power-off retract count",
    230: "GMR head amplitude",
    231: "Temperature (SSD)",
    232: "Available spare (SSD)",
    233: "Media wearout indicator (SSD)",
    234: "Thermal throttling (SSD)",
    235: "Power-in cycles (SSD)",
    240: "Head flying hours",
    241: "Total LBAs written",
    242: "Total LBAs read",
    243: "Total LBAs written (expanded)",
    244: "Total LBAs read (expanded)",
    249: "NAND writes (SSD)",
    250: "Read error retry rate",
}

HEALTH_BADGES = {
    "good": ("хорошее", "✅"),
    "caution": ("внимание", "⚠️"),
    "bad": ("плохое", "❌"),
    "unknown": ("нет данных", "❔"),
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
$smart = @()
$thresholds = @()
try {
  $smart = Get-CimInstance -Namespace root/wmi -ClassName MSStorageDriver_ATAPISmartData |
    ForEach-Object {
      [pscustomobject]@{
        instance = [string]$_.InstanceName
        bytes = @($_.VendorSpecific)
      }
    }
} catch {}
try {
  $thresholds = Get-CimInstance -Namespace root/wmi -ClassName MSStorageDriver_FailurePredictThresholds |
    ForEach-Object {
      [pscustomobject]@{
        instance = [string]$_.InstanceName
        bytes = @($_.VendorSpecific)
      }
    }
} catch {}
[pscustomobject]@{ smart = $smart; thresholds = $thresholds } |
  ConvertTo-Json -Depth 4 -Compress
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


def parse_threshold_bytes(values: Any) -> dict[int, int]:
    """Разобрать ``VendorSpecific`` порогов ATA SMART: {id: порог}.

    Структура та же 12-байтовая: id и порог в нормализованном виде (0–100).
    Драйверы кладут порог в разные байты записи, поэтому проверяем оба
    варианта и берём тот, где все пороги в допустимом диапазоне; если ни
    один не сошёлся — порогов нет (честное «—» вместо догадок).
    """
    try:
        data = [int(v) & 0xFF for v in values]
    except (TypeError, ValueError):
        return {}
    for threshold_offset in (1, 2):
        result: dict[int, int] = {}
        valid = False
        for offset in range(2, len(data) - 11, 12):
            attr_id = data[offset]
            if attr_id == 0:
                continue
            threshold = data[offset + threshold_offset]
            if threshold > 100:
                valid = False
                break
            result[attr_id] = threshold
            valid = True
        if valid and result:
            return result
    return {}


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


def _has_reliability_counters(disk: dict) -> bool:
    return any(
        disk.get(key) is not None
        for key in ("temperature", "hours", "wear", "read_errors", "write_errors")
    )


def attach_smart(
    disks: list[dict],
    records: list[dict],
    threshold_records: list[dict] | None = None,
) -> None:
    """Добавить к дискам разобранные ATA-атрибуты и пороги (если WMI их отдал).

    Без ATA-данных, но с показателями StorageReliabilityCounter, источник
    помечается ``counters``: это честные значения и для NVMe, где ATA-
    структуры не существуют.
    """
    threshold_records = threshold_records or []
    for disk in disks:
        record = match_smart_record(str(disk.get("model") or ""), records)
        attrs = parse_smart_bytes(record.get("bytes")) if record else {}
        disk["smart_attributes"] = attrs

        threshold_record = match_smart_record(
            str(disk.get("model") or ""), threshold_records
        )
        disk["smart_thresholds"] = (
            parse_threshold_bytes(threshold_record.get("bytes"))
            if threshold_record else {}
        )

        if attrs:
            disk["smart_source"] = "ata"
        elif _has_reliability_counters(disk):
            disk["smart_source"] = "counters"
        else:
            disk["smart_source"] = ""


def health_badge(disk: dict) -> tuple[str, str, str]:
    """Сводный статус: (код, подпись, иконка) — good/caution/bad/unknown.

    «Плохое» берётся только из HealthStatus системы. «Внимание» — из
    ненулевых критических атрибутов, статуса WARN или горячей температуры.
    Без данных честно «нет данных».
    """
    code, label, icon = "good", *HEALTH_BADGES["good"]
    health = disk.get("health", "?")
    attrs = disk.get("smart_attributes") or {}

    if health == "BAD":
        return "bad", *HEALTH_BADGES["bad"]

    critical_nonzero = any(
        int(attrs[attr_id].get("raw") or 0) > 0
        for attr_id in CRITICAL_ATTRS
        if attr_id in attrs
    )
    _zone, _label, temp_icon = temperature_zone(disk.get("temperature"))
    if health == "WARN" or critical_nonzero or temp_icon == "❌":
        return "caution", *HEALTH_BADGES["caution"]

    if health == "OK" and (
        attrs or _has_reliability_counters(disk)
    ):
        return code, label, icon
    return "unknown", *HEALTH_BADGES["unknown"]


def _counter_rows(disk: dict) -> list[tuple[str, str, str]]:
    """Строки из StorageReliabilityCounter — единственный источник для NVMe."""
    rows: list[tuple[str, str, str]] = []
    temp = disk.get("temperature")
    if isinstance(temp, int) and temp > 0:
        _zone, _label, icon = temperature_zone(temp)
        rows.append(("Температура", format_temperature(temp), icon))
    hours = disk.get("hours")
    if isinstance(hours, int) and hours > 0:
        rows.append(("Наработка", format_hours(hours), ""))
    wear = disk.get("wear")
    if isinstance(wear, int) and wear >= 0:
        mark = ""
        if wear >= 80:
            mark = "❌"
        elif wear >= 40:
            mark = "⚠️"
        rows.append(("Износ (Wear)", f"{wear}%", mark))
    for key, title in (("read_errors", "Ошибки чтения"),
                       ("write_errors", "Ошибки записи")):
        value = disk.get(key)
        if isinstance(value, int) and value >= 0:
            rows.append((title, str(value), "⚠️" if value > 0 else "✅"))
    return rows


def smart_rows(disk: dict) -> list[tuple[str, str, str]]:
    """Полная таблица SMART: (атрибут, значение, статус).

    Значение — «value/worst · порог · raw», температура и наработка —
    в человеческом виде. Для дисков без ATA-данных, но с показателями
    reliability-счётчиков (NVMe), таблица строится из них.
    """
    attrs = disk.get("smart_attributes") or {}
    if attrs:
        thresholds = disk.get("smart_thresholds") or {}
        rows: list[tuple[str, str, str]] = []
        for attr_id in sorted(attrs):
            info = attrs[attr_id]
            name = ATA_ATTRIBUTE_NAMES.get(attr_id, f"Атрибут {attr_id}")
            title = f"{name} [{attr_id}]"
            if attr_id == 9:
                rows.append((title, format_hours(int(info.get("raw") or 0)), ""))
                continue
            if attr_id in (190, 191, 194, 231):
                temp = int(info.get("raw") or 0) & 0xFF
                if attr_id == 194 or temp:
                    _code, _label, icon = temperature_zone(temp)
                    rows.append((title, format_temperature(temp), icon))
                    continue
            value = int(info.get("value") or 0)
            worst = int(info.get("worst") or 0)
            raw = int(info.get("raw") or 0)
            value_text = f"{value}/{worst}"
            threshold = thresholds.get(attr_id)
            if threshold is not None:
                value_text += f" · порог {threshold}"
            value_text += f" · raw {raw}"
            mark = "⚠️" if attr_id in CRITICAL_ATTRS and raw > 0 else ""
            rows.append((title, value_text, mark))
        return rows
    return _counter_rows(disk)


def smart_summary(disk: dict) -> str:
    """Компактная строка ключевых атрибутов: «reallocated: 0 · pending: 0 · …»."""
    rows = {title: (value, mark) for title, value, mark in smart_rows(disk)}
    parts: list[str] = []
    for attr_id, name in SMART_ATTRIBUTES.items():
        if attr_id == 194:
            title = f"Temperature [{attr_id}]"
        elif attr_id in ATA_ATTRIBUTE_NAMES:
            title = f"{ATA_ATTRIBUTE_NAMES[attr_id]} [{attr_id}]"
        else:
            title = name
        if title not in rows:
            continue
        value, mark = rows[title]
        prefix = SMART_SHORT.get(attr_id, name)
        parts.append(f"{prefix}: {value}" + (f" {mark}" if mark and mark != "✅" else ""))
    if parts:
        return " · ".join(parts)
    return ""


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


def parse_smart_payload(raw: str) -> tuple[list[dict], list[dict]]:
    """Разобрать вывод WMI: (записи атрибутов, записи порогов).

    Поддерживаются оба формата: новый ``{"smart": [...], "thresholds":
    [...]}`` и старый массив только с атрибутами.
    """
    text = (raw or "").strip()
    if not text:
        return [], []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Не удалось разобрать SMART-атрибуты: %s", text[:200])
        return [], []

    if isinstance(payload, dict) and "smart" in payload:
        smart = payload.get("smart") or []
        thresholds = payload.get("thresholds") or []
        if isinstance(smart, dict):
            smart = [smart]
        if isinstance(thresholds, dict):
            thresholds = [thresholds]
        return (
            [item for item in smart if isinstance(item, dict) and item.get("instance")],
            [
                item for item in thresholds
                if isinstance(item, dict) and item.get("instance")
            ],
        )

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return [], []
    return [
        item for item in payload
        if isinstance(item, dict) and item.get("instance")
    ], []


def parse_smart_records(raw: str) -> list[dict]:
    """Записи атрибутов (совместимость: без порогов)."""
    return parse_smart_payload(raw)[0]


def read_smart_raw() -> tuple[list[dict], list[dict]]:
    """Сырые ATA-атрибуты и пороги через WMI (нужны права администратора)."""
    try:
        raw = _run_powershell(_SMART_SCRIPT, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        log.info("Сырые SMART-атрибуты недоступны: %s", e)
        return [], []
    return parse_smart_payload(raw)


def read_smart_records() -> list[dict]:
    """Сырые ATA-атрибуты (совместимость со старым API)."""
    return read_smart_raw()[0]


def list_disks() -> list[dict]:
    """Список физических дисков с SMART-счётчиками (может быть пустым)."""
    try:
        raw = _run_powershell(_PS_SCRIPT)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("PowerShell недоступен: %s", e)
        return []
    disks = parse_disks_json(raw)
    if disks:
        records, threshold_records = read_smart_raw()
        attach_smart(disks, records, threshold_records)
    return disks
