"""Данные страницы «Диски»: тома, их занятость, прогноз и состояние железа."""
from __future__ import annotations

import logging
import threading
from typing import Any

from disk_cleaner_app.cleaners.base import list_drives
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.disk_health import (
    format_hours,
    health_badge,
    list_disks,
    smart_summary,
)
from disk_cleaner_app.services.disk_usage import (
    forecast_free,
    forecast_text,
    insufficient_data,
    usage_series,
)

log = logging.getLogger(__name__)


class DisksService:
    """Тома и физические диски. SMART читается в фоне — PowerShell не быстрый."""

    def __init__(self, history: HistoryManager) -> None:
        self._history = history
        self._disks: list[dict[str, Any]] | None = None
        self._busy = False

    # ── тома ─────────────────────────────────────────

    def _forecast(self, volume: str) -> str:
        try:
            series = usage_series(self._history, volume)
        except Exception:
            log.warning("Не удалось прочитать историю тома %s", volume, exc_info=True)
            return ""
        forecast = forecast_free(series)
        if forecast:
            return forecast_text(forecast)
        if insufficient_data(series):
            return forecast_text(None)
        return "Место не убывает — прогноз не нужен."

    def volumes(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for root, free, total in list_drives():
            total = int(total or 0)
            free = int(free or 0)
            used = max(0, total - free)
            percent = round(used * 100 / total) if total else 0
            out.append({
                "root": root,
                "name": root.rstrip("\\/") or root,
                "free_text": format_bytes(free),
                "used_text": format_bytes(used),
                "total_text": format_bytes(total),
                "percent_used": percent,
                "percent_free": 100 - percent if total else 0,
                "forecast": self._forecast(root),
            })
        return out

    # ── железо ───────────────────────────────────────

    def _disk_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for disk in self._disks or []:
            code, label, _icon = health_badge(disk)
            rows.append({
                "index": disk.get("index", 0),
                "model": disk.get("model", ""),
                "size_text": format_bytes(int(disk.get("size") or 0)),
                "media": disk.get("media", ""),
                "bus": disk.get("bus", ""),
                "health": code,
                "health_label": label,
                "temperature": (
                    f"{disk['temperature']} °C"
                    if disk.get("temperature") is not None else ""
                ),
                "hours": format_hours(disk.get("hours")) if disk.get("hours") else "",
                "wear": f"износ {disk['wear']}%" if disk.get("wear") is not None else "",
                "summary": smart_summary(disk),
            })
        return rows

    def load(self) -> dict[str, Any]:
        """Всё, что есть сейчас: тома сразу, диски — после фонового чтения."""
        return {
            "volumes": self.volumes(),
            "disks": self._disk_rows(),
            "busy": self._busy,
            "smart_ready": self._disks is not None,
        }

    def load_smart(self, notify) -> None:
        """Прочитать SMART в фоне и отдать готовые строки через ``notify``."""
        if self._busy:
            return
        self._busy = True

        def worker() -> None:
            try:
                self._disks = list_disks()
            except Exception:
                log.warning("Не удалось прочитать SMART", exc_info=True)
                self._disks = []
            finally:
                self._busy = False
            notify(self.load())

        threading.Thread(target=worker, name="smart-read", daemon=True).start()
