"""Главная страница в новом интерфейсе: диск, история, прогноз, топ целей.

Отдельный слой данных на тех же сервисах, что и Tk-вкладка: история чисток,
снапшоты занятости и уже просканированные цели берутся из ``DeepService``,
поэтому цифры на обоих экранах совпадают.
"""
from __future__ import annotations

import logging
from typing import Any

from disk_cleaner_app.cleaners.base import get_disk_free, list_drives
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.disk_usage import (
    forecast_free,
    forecast_text,
    insufficient_data,
    record_snapshot,
    usage_series,
)
from disk_cleaner_app.web.service import DeepService

log = logging.getLogger(__name__)


class DashboardService:
    """Сводка для главного экрана."""

    TOP_LIMIT = 5

    def __init__(self, deep: DeepService) -> None:
        self._deep = deep
        self.config = deep.config
        self.history = deep.history
        drives = self.drives()
        self.drive = drives[0] if drives else ""

    def drives(self) -> list[str]:
        return [item[0] for item in list_drives()] or ["C:\\"]

    def set_drive(self, drive: str) -> dict[str, Any]:
        if drive in self.drives():
            self.drive = drive
        return self.state()

    # ── данные ───────────────────────────────────────

    def _trend(self) -> tuple[list[dict[str, Any]], str]:
        """Точки графика и текст прогноза."""
        try:
            record_snapshot(self.history)
            series = usage_series(self.history, self.drive)
        except Exception:
            log.warning("Не удалось прочитать историю занятости", exc_info=True)
            return [], "Прогноз недоступен: не удалось прочитать историю."

        points: list[dict[str, Any]] = []
        for item in series:
            date_text = str(item.get("date", ""))[:10]
            parts = date_text.split("-")
            label = f"{parts[2]}.{parts[1]}" if len(parts) == 3 else date_text
            points.append({"label": label, "free": int(item.get("free", 0))})

        forecast = forecast_free(series)
        if forecast:
            return points, forecast_text(forecast)
        if insufficient_data(series):
            return points, forecast_text(None)
        return points, (
            "По наблюдениям место не убывает — прогноз не требуется. "
            f"Точек: {len(series)}."
        )

    def _threshold(self, free: int, total: int) -> dict[str, Any]:
        try:
            limit_gb = float(self.config.get("deep_threshold_gb", 10))
        except Exception:
            limit_gb = 10.0
        free_gb = free / (1024 ** 3)
        visible = bool(
            limit_gb > 0 and total > 0 and free > 0 and free_gb < limit_gb
        )
        if not visible:
            return {"visible": False, "text": ""}
        return {
            "visible": True,
            "text": (
                f"Свободно {free_gb:.1f} ГБ — меньше порога {limit_gb:g} ГБ. "
                "Предлагаем глубокую очистку: безопасный набор выберется сам."
            ),
        }

    def _last_clean(self) -> str:
        try:
            entry = self.history.get_last()
        except Exception:
            return ""
        if not entry:
            return ""
        date = str(entry.get("date", ""))[:16].replace("T", " ")
        return (
            f"{date} · {format_bytes(int(entry.get('bytes_freed', 0)))} · "
            f"{entry.get('items_cleaned', 0)} целей"
        )

    def _top(self) -> list[dict[str, Any]]:
        scanned = [c for c in self._deep.cleaners if c.scanned and c.size > 0]
        scanned.sort(key=lambda c: c.size, reverse=True)
        return [
            {
                "id": c.id,
                "name": c.name,
                "size": int(c.size),
                "size_text": format_bytes(c.size),
                "safety": str(c.safety),
            }
            for c in scanned[: self.TOP_LIMIT]
        ]

    def state(self) -> dict[str, Any]:
        free, total = get_disk_free(self.drive)
        trend, forecast = self._trend()
        used = max(0, total - free)
        return {
            "drives": self.drives(),
            "drive": self.drive,
            "free": free,
            "total": total,
            "free_text": format_bytes(free) if free > 0 else "—",
            "used_text": format_bytes(used),
            "total_text": format_bytes(total) if total > 0 else "—",
            "percent_used": round(100 * used / total) if total > 0 else 0,
            "percent_free": round(100 * free / total) if total > 0 else 0,
            "freed_text": format_bytes(self.history.total_freed()),
            "clean_count": self.history.count(),
            "last_clean": self._last_clean(),
            "trend": trend,
            "forecast": forecast,
            "threshold": self._threshold(free, total),
            "top": self._top(),
        }
