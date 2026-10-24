"""Экспорт истории очисток в JSON и CSV.

Отчёт не содержит путей удалённых файлов — только цели, объём и время:
так его можно пересылать, не раскрывая структуру личных папок.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
from pathlib import Path

from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.services.planner import OperationPlan

CSV_COLUMNS = ("id", "date", "items_cleaned", "bytes_freed", "details")
PLAN_CSV_COLUMNS = ("target_id", "target_name", "layer", "path", "bytes",
                    "action", "volume")


def _prepare_target(path: str | Path, suffix: str) -> Path:
    target = Path(path)
    if target.suffix.lower() != suffix:
        target = target.with_suffix(suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def build_report(history: HistoryManager) -> dict:
    """Собрать отчёт в виде словаря (без записи на диск)."""
    return build_report_from_entries(history.get_all())


def build_report_from_entries(entries: list[dict]) -> dict:
    """Отчёт по произвольному набору записей (например, отфильтрованному)."""
    return {
        "app": "DiskCleaner",
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "count": len(entries),
        "total_freed": sum(int(e.get("bytes_freed", 0) or 0) for e in entries),
        "entries": entries,
    }


def export_json(history: HistoryManager, path: str | Path) -> Path:
    """Сохранить отчёт JSON (атомарная запись)."""
    return export_entries_json(history.get_all(), path)


def export_entries_json(entries: list[dict], path: str | Path) -> Path:
    """Сохранить выбранные записи в JSON."""
    target = _prepare_target(path, ".json")
    payload = build_report_from_entries(entries)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, target)
    return target


def export_csv(history: HistoryManager, path: str | Path) -> Path:
    """Сохранить отчёт CSV (UTF-8 с BOM — Excel открывает без нареканий)."""
    return export_entries_csv(history.get_all(), path)


def export_entries_csv(entries: list[dict], path: str | Path) -> Path:
    """Сохранить выбранные записи в CSV."""
    target = _prepare_target(path, ".csv")
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for entry in entries:
            row = {name: entry.get(name, "") for name in CSV_COLUMNS}
            details = row["details"]
            if details is not None and not isinstance(details, str):
                row["details"] = json.dumps(details, ensure_ascii=False)
            writer.writerow(row)
    os.replace(tmp, target)
    return target

# ── экспорт плана очистки ──────────────────────────────


def _plan_rows(plan: OperationPlan) -> list[dict]:
    rows: list[dict] = []
    for target in plan.targets:
        for act in target.actions:
            rows.append({
                "target_id": target.target_id,
                "target_name": target.cleaner.name,
                "layer": target.cleaner.layer,
                "path": str(act.path) if act.path is not None else "",
                "bytes": act.bytes,
                "action": act.action,
                "volume": act.volume,
            })
    return rows


def build_plan_report(plan: OperationPlan) -> dict:
    """План в виде словаря: сводка + действия по целям."""
    rows = _plan_rows(plan)
    return {
        "app": "DiskCleaner",
        "plan_id": plan.id,
        "created_at": datetime.datetime.fromtimestamp(
            plan.created_at
        ).isoformat(timespec="seconds"),
        "targets": len(plan.targets),
        "actions": len(rows),
        "total_bytes": sum(r["bytes"] for r in rows),
        "warnings": list(plan.warnings),
        "rows": rows,
    }


def export_plan_json(plan: OperationPlan, path: str | Path) -> Path:
    target = _prepare_target(path, ".json")
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(build_plan_report(plan), f, indent=2, ensure_ascii=False)
    os.replace(tmp, target)
    return target


def export_plan_csv(plan: OperationPlan, path: str | Path) -> Path:
    target = _prepare_target(path, ".csv")
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PLAN_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(_plan_rows(plan))
    os.replace(tmp, target)
    return target
