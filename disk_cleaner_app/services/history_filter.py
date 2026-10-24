"""Фильтрация и форматирование журнала очисток (для UI истории)."""
from __future__ import annotations

import datetime
import json
from typing import Any

from disk_cleaner_app.models.item import format_bytes

STATUS_ICONS = {"OK": "✅", "ERR": "❌", "SKIP": "⏭️"}


def parse_date(value: str) -> datetime.date | None:
    """Разобрать дату ``ГГГГ-ММ-ДД``; None для пустой/некорректной строки."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def _entry_date(entry: dict) -> datetime.date | None:
    return parse_date(str(entry.get("date", ""))[:10])


def _details_list(entry: dict) -> list[dict]:
    details = entry.get("details")
    if isinstance(details, list):
        return [item for item in details if isinstance(item, dict)]
    return []


def summarize_details(entry: dict, limit: int = 3) -> str:
    """Короткая строка целей: «Chrome cache, Temp, …»."""
    items = _details_list(entry)
    if not items:
        details = entry.get("details")
        if isinstance(details, str) and details.strip():
            return details.strip()[:60]
        return "—"

    names = [str(item.get("name") or item.get("id") or "?") for item in items]
    if len(names) > limit:
        return ", ".join(names[:limit]) + f" … +{len(names) - limit}"
    return ", ".join(names)


def format_details(entry: dict, max_lines: int = 40) -> str:
    """Подробный текст выбранной записи для панели деталей."""
    date = str(entry.get("date", "")).replace("T", " ")[:19]
    items = _details_list(entry)

    lines = [
        f"📅 {date}   ·   целей: {entry.get('items_cleaned', 0)}   ·   "
        f"{format_bytes(int(entry.get('bytes_freed', 0) or 0))}",
    ]
    if not items:
        details = entry.get("details")
        if isinstance(details, str) and details.strip():
            lines.append("")
            lines.append(details.strip()[:500])
        else:
            lines.append("")
            lines.append("Нет деталей по целям.")
        return "\n".join(lines)

    lines.append("")
    for item in items[:max_lines]:
        icon = STATUS_ICONS.get(str(item.get("status", "")), "•")
        name = str(item.get("name") or item.get("id") or "?")
        freed = int(item.get("freed", 0) or 0)
        note = item.get("note") or ""
        suffix = f" — {note}" if note else ""
        lines.append(f"  {icon}  {name}  ·  {format_bytes(freed)}{suffix}")
    if len(items) > max_lines:
        lines.append(f"  … и ещё {len(items) - max_lines}")
    return "\n".join(lines)


def filter_entries(
    entries: list[dict],
    date_from: str = "",
    date_to: str = "",
    query: str = "",
) -> list[dict]:
    """Отфильтровать журнал по датам (включительно) и тексту.

    Некорректная дата игнорируется: фильтр считается незаданным.
    Текст ищется в именах целей, статусе, деталях и дате.
    """
    start = parse_date(date_from)
    end = parse_date(date_to)
    needle = (query or "").strip().lower()

    result: list[dict] = []
    for entry in entries:
        moment = _entry_date(entry)
        if start is not None:
            if moment is None or moment < start:
                continue
        if end is not None:
            if moment is None or moment > end:
                continue
        if needle and needle not in _haystack(entry):
            continue
        result.append(entry)
    return result


def _haystack(entry: dict) -> str:
    parts: list[str] = [str(entry.get("date", ""))]
    details = entry.get("details")
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict):
                parts.append(str(item.get("name", "")))
                parts.append(str(item.get("id", "")))
                parts.append(str(item.get("status", "")))
                parts.append(str(item.get("note", "")))
    elif details is not None:
        parts.append(str(details))
    return " ".join(parts).lower()


def total_freed(entries: list[dict]) -> int:
    return sum(int(entry.get("bytes_freed", 0) or 0) for entry in entries)


def as_json_entry(entry: dict) -> dict[str, Any]:
    """Копия записи с компактным JSON в ``details`` (для вывода)."""
    copy = dict(entry)
    details = copy.get("details")
    if details is not None and not isinstance(details, str):
        copy["details"] = json.dumps(details, ensure_ascii=False)
    return copy
