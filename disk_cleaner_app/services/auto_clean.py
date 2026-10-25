"""Тихая очистка без UI — для планировщика и CLI-режима."""
from __future__ import annotations

from typing import Any

from disk_cleaner_app.cleaners.base import BaseCleaner, CleanOptions
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.models.target import LAYER_SAFE
from disk_cleaner_app.services.cleaner import CleanEngine
from disk_cleaner_app.services.elevation import is_admin

SMART_MODE = "smart"
DEEP_SAFE_MODE = "deep-safe"


def deep_safe_cleaners(config: ConfigManager | None = None) -> list[BaseCleaner]:
    """Набор для тихой глубокой очистки: слой A, recommended, без блокировки.

    Тот же ``Planner``/``clean_plan``, что и ручная deep-очистка: белый список,
    возрастные фильтры и корзина для D работают как обычно. Admin-цели
    включаются только при наличии прав (иначе движок честно их SKIP-ит,
    но лучше не тащить в план).
    """
    from disk_cleaner_app.cleaners.registry import CleanerRegistry

    config = config or ConfigManager()
    admin = bool(is_admin())
    return [
        cleaner
        for cleaner in CleanerRegistry(config).get_all(include_auto=False)
        if cleaner.layer == LAYER_SAFE
        and cleaner.recommended
        and cleaner.is_actionable
        and (admin or not cleaner.admin_required)
    ]


def supported_modes() -> tuple[str, ...]:
    return (SMART_MODE, DEEP_SAFE_MODE)


def run_silent_clean(
    config: ConfigManager | None = None,
    to_recycle: bool | None = None,
    mode: str = SMART_MODE,
) -> dict[str, Any]:
    """Тихая очистка без интерфейса: Smart Clean или Deep-safe.

    Используется заданием планировщика: DiskCleaner.exe --smart-clean --silent.
    Возвращает сводку {targets, ok, failed, freed, mode, skipped}.
    """
    from disk_cleaner_app.cleaners.registry import CleanerRegistry

    config = config or ConfigManager()
    if to_recycle is None:
        to_recycle = bool(config.get("to_recycle", False))

    registry = CleanerRegistry(config)
    skipped = 0
    if mode == DEEP_SAFE_MODE:
        cleaners = deep_safe_cleaners(config)
        op_type = "deep"
    else:
        cleaners = registry.get_safe()
        op_type = "smart"

    # Точка восстановления перед тихой глубокой очисткой (если включена).
    if mode == DEEP_SAFE_MODE and bool(config.get("restore_point", False)):
        from disk_cleaner_app.services.restore_point import create_restore_point

        ok, message = create_restore_point()
        if not ok:
            # Точку не создали (нет прав/лимит 24 ч): глубокая очистка всё
            # равно идёт по плану, но честно считаем это событием.
            skipped += 1

    engine = CleanEngine()
    results: list = []
    if cleaners:
        results = engine.clean_selected(
            cleaners, options=CleanOptions(to_recycle=to_recycle, safe_mode=True)
        )
    ok_results = [r for r in results if r.status == "OK"]
    failed = [r for r in results if r.status == "ERR"]
    freed = sum(r.freed for r in results)

    summary: dict[str, Any] = {
        "targets": len(cleaners),
        "ok": len(ok_results),
        "failed": len(failed),
        "freed": freed,
        "mode": mode,
        "skipped": skipped,
    }
    try:
        payload = [
            {"id": r.cleaner.id, "name": r.cleaner.name,
             "status": r.status, "freed": r.freed, "note": r.note}
            for r in results
        ]
        HistoryManager().add_operation(
            payload, bytes_freed=freed, op_type=op_type
        )
    except Exception:
        pass  # история — не причина считать очистку неудавшейся
    return summary
