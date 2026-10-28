"""История очисток для веб-интерфейса."""
from __future__ import annotations

import datetime
from typing import Any

from disk_cleaner_app.models.history import OP_TYPE_LABELS, HistoryManager
from disk_cleaner_app.models.item import format_bytes

LIMIT = 200


class HistoryService:
    """Отдаёт журнал операций и сводку по нему."""

    def __init__(self, history: HistoryManager) -> None:
        self._history = history

    def _entries(self) -> list[dict[str, Any]]:
        rows = self._history.get_recent_full(limit=LIMIT)
        out: list[dict[str, Any]] = []
        for row in rows:
            entries = row.get("details") or []
            out.append({
                "id": row["id"],
                "date": str(row["date"])[:16].replace("T", " "),
                "type": row.get("op_type") or "clean",
                "type_label": OP_TYPE_LABELS.get(
                    row.get("op_type") or "clean", "Очистка"
                ),
                "items": int(row["items_cleaned"]),
                "bytes": int(row["bytes_freed"]),
                "size_text": format_bytes(int(row["bytes_freed"])),
                "details": [
                    {
                        "name": str(item.get("name", "")),
                        "status": str(item.get("status", "")),
                        "freed": format_bytes(int(item.get("freed") or 0)),
                    }
                    for item in entries
                    if isinstance(item, dict)
                ][:40],
            })
        return out

    def _chart(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Освобождено по дням — последние 14 дней с записями."""
        by_day: dict[str, int] = {}
        for entry in reversed(entries):
            day = entry["date"][:10]
            by_day[day] = by_day.get(day, 0) + entry["bytes"]
        days = sorted(by_day)[-14:]
        return [
            {"day": day[5:], "bytes": by_day[day], "text": format_bytes(by_day[day])}
            for day in days
        ]

    def state(self) -> dict[str, Any]:
        entries = self._entries()
        total = self._history.total_freed()
        return {
            "entries": entries,
            "count": len(entries),
            "total": total,
            "total_text": format_bytes(total),
            "chart": self._chart(entries),
            "today": datetime.date.today().isoformat(),
        }
