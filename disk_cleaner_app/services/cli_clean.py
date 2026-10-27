"""🖥️ CLI-режим скана и тихой очистки с JSON-отчётом.

    python -m disk_cleaner_app --scan
    python -m disk_cleaner_app --clean safe --report out.json

Semantics:
- ``--scan`` — измерить цели preset'а и показать таблицу; удаления нет;
- ``--clean <preset>`` — скан + очистка через CleanEngine (тот же путь,
  что и GUI: планировщик, белый список, возрастные фильтры, слой D в
  корзину);
- ``--report <path>`` — JSON-отчёт о скане и/или очистке.

Presets: ``safe`` (🟢-цели реестра) и ``deep-safe`` (слой A + recommended
без admin-целей). Другие наборы не открываются из CLI: слои C/D требуют
осознанного выбора в интерфейсе.
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path

from disk_cleaner_app import __version__
from disk_cleaner_app.cleaners.base import BaseCleaner
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.cleaner import CleanEngine

log = logging.getLogger(__name__)

SCAN_PRESETS = ("safe", "deep-safe")


def build_preset_cleaners(preset: str) -> list[BaseCleaner]:
    """Собрать набор целей CLI по имени preset'а."""
    from disk_cleaner_app.cleaners.registry import CleanerRegistry
    from disk_cleaner_app.models.config import ConfigManager

    if preset == "safe":
        return CleanerRegistry(ConfigManager()).get_safe(include_auto=True)
    if preset == "deep-safe":
        from disk_cleaner_app.services.auto_clean import deep_safe_cleaners

        return deep_safe_cleaners(ConfigManager())
    raise ValueError(
        f"Неизвестный preset «{preset}»: разрешены {', '.join(SCAN_PRESETS)}"
    )


def _scan_rows(cleaners: list[BaseCleaner]) -> list[dict]:
    rows: list[dict] = []
    for cleaner in cleaners:
        try:
            size = max(0, int(cleaner.get_size()))
            error = ""
        except Exception as e:
            size, error = 0, str(e)[:120]
        rows.append({
            "id": cleaner.id,
            "name": cleaner.name,
            "layer": getattr(cleaner, "layer", ""),
            "size": size,
            "error": error,
        })
    return rows


def _clean_rows(results: list) -> list[dict]:
    rows: list[dict] = []
    for result in results:
        rows.append({
            "id": result.cleaner.id,
            "name": result.cleaner.name,
            "status": result.status,
            "planned": int(result.planned),
            "freed": int(result.freed),
            "removed": int(result.removed),
            "recycled": bool(result.recycled),
            "note": result.note,
            "errors": list(result.errors[:5]),
        })
    return rows


def run_cli_scan_clean(
    preset: str = "safe",
    clean: bool = False,
    report_path: str | Path | None = None,
    cleaners: list[BaseCleaner] | None = None,
) -> int:
    """Скан и (опционально) очистка preset'а. Возвращает код выхода.

    ``cleaners`` — инъекция для тестов; по умолчанию берётся из реестра.
    """
    try:
        targets = cleaners if cleaners is not None else build_preset_cleaners(preset)
    except ValueError as e:
        print(str(e))
        return 2

    started = datetime.datetime.now()
    if not clean:
        rows = _scan_rows(targets)
        total = sum(row["size"] for row in rows)
        print(f"Пресет «{preset}»: целей {len(rows)}, "
              f"найдено {format_bytes(total)}")
        for row in rows:
            mark = f"  ⚠️ {row['error']}" if row["error"] else ""
            print(f"  {row['name']}: {format_bytes(row['size'])}{mark}")
        summary = {"mode": "scan", "total_size": total}
        failed = 0
    else:
        results = CleanEngine().clean_selected(targets)
        rows = _clean_rows(results)
        freed = sum(row["freed"] for row in rows)
        failed = sum(1 for row in rows if row["status"] not in ("OK", "SKIP"))
        print(
            f"Очистка «{preset}»: целей {len(rows)}, успешно "
            f"{sum(1 for r in rows if r['status'] == 'OK')}, "
            f"ошибок {failed}, освобождено {format_bytes(freed)}"
        )
        for row in rows:
            if row["status"] == "OK":
                continue
            print(f"  ⚠️ {row['name']}: {row['status']} — {row['note']}")
        summary = {"mode": "clean", "total_freed": freed, "failed": failed}

    if report_path:
        report = {
            "app": "DiskCleaner Pro",
            "version": __version__,
            "generated_at": started.isoformat(timespec="seconds"),
            "preset": preset,
            **summary,
            "targets": rows,
        }
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Отчёт: {path}")

    return 0 if failed == 0 else 1
