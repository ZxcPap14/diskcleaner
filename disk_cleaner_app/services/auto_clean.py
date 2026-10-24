"""Тихая Smart-очистка без UI — для планировщика и CLI-режима."""
from __future__ import annotations

from typing import Any

from disk_cleaner_app.cleaners.base import BaseCleaner, CleanOptions
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.services.cleaner import CleanEngine


def run_silent_clean(
    config: ConfigManager | None = None,
    to_recycle: bool | None = None,
) -> dict[str, Any]:
    """Очистить все безопасные (🟢) цели без интерфейса.

    Используется заданием планировщика: DiskCleaner.exe --smart-clean --silent.
    Возвращает сводку {targets, ok, failed, freed}.
    """
    from disk_cleaner_app.cleaners.registry import CleanerRegistry

    config = config or ConfigManager()
    if to_recycle is None:
        to_recycle = bool(config.get("to_recycle", False))

    cleaners: list[BaseCleaner] = CleanerRegistry(config).get_safe()
    options = CleanOptions(to_recycle=to_recycle, safe_mode=True)
    engine = CleanEngine()

    results = engine.clean_selected(cleaners, options=options)
    ok = [r for r in results if r.status == "OK"]
    failed = [r for r in results if r.status == "ERR"]
    freed = sum(r.freed for r in results)

    summary: dict[str, Any] = {
        "targets": len(cleaners),
        "ok": len(ok),
        "failed": len(failed),
        "freed": freed,
    }
    try:
        payload = [
            {"id": r.cleaner.id, "name": r.cleaner.name,
             "status": r.status, "freed": r.freed, "note": r.note}
            for r in results
        ]
        HistoryManager().add_operation(payload, bytes_freed=freed, op_type="smart")
    except Exception:
        pass  # история — не причина считать очистку неудавшейся
    return summary
