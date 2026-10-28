"""Данные страницы «Анализ»: отчёты по диску и treemap.

Вся тяжёлая работа — в фоновом потоке; UI получает готовые словари через
``notify``. Результаты кэшируются, как в Tk-версии: повторный вход в режим
не запускает обход диска заново.
"""
from __future__ import annotations

import datetime
import logging
import threading
from typing import Any

from disk_cleaner_app.cleaners.base import (
    list_drives,
    reset_scan_cancel,
    set_scan_cancel,
)
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.analyzer import (
    FileScan,
    empty_scan_root,
    extension_label,
    filter_files,
    find_empty_folders,
    normalize_root,
    remove_empty_folders,
    scan_files,
    scan_top_folders,
)
from disk_cleaner_app.services.large_files import format_age, format_modified
from disk_cleaner_app.services.treemap import TreemapData

log = logging.getLogger(__name__)

SCAN_FLOOR_MB = 10
REPORT_LIMIT = 200
TREEMAP_LIMIT = 30

SIZE_CHOICES = [
    {"label": "≥ 10 МБ", "mb": 10},
    {"label": "≥ 100 МБ", "mb": 100},
    {"label": "≥ 500 МБ", "mb": 500},
    {"label": "≥ 1 ГБ", "mb": 1024},
]
AGE_CHOICES = [
    {"label": "Любой возраст", "days": 0},
    {"label": "Старше года", "days": 365},
    {"label": "Старше 3 лет", "days": 1095},
]


class AnalyzerService:
    """Отчёты «Топ папок», «Файлы и фильтры», «Пустые папки» и treemap."""

    def __init__(self) -> None:
        self._busy = False
        self._cancel = threading.Event()
        self._cache: dict[tuple[str, str], tuple[datetime.datetime, dict[str, Any]]] = {}
        self._file_scan: FileScan | None = None
        self._file_root = ""
        self._file_moment: datetime.datetime | None = None
        self._last_empty: list[str] = []
        self._last_empty_root = ""
        self._last_mode = ""
        self._drive = normalize_root(None)
        self._treemap = TreemapData()

    # ── состояние ────────────────────────────────────

    def drives(self) -> list[dict[str, Any]]:
        return [
            {"root": root, "name": root.rstrip("\\/") or root}
            for root, _free, _total in list_drives()
        ]

    def state(self) -> dict[str, Any]:
        return {
            "drives": self.drives(),
            "drive": self._drive,
            "busy": self._busy,
            "mode": self._last_mode,
            "size_choices": SIZE_CHOICES,
            "age_choices": AGE_CHOICES,
            "extensions": self._extension_chips(),
            "cached": bool(self._last_mode),
        }

    def _extension_chips(self) -> list[dict[str, Any]]:
        scan = self._file_scan
        if scan is None or self._file_root != self._drive:
            return []
        total = scan.total_bytes or 1
        return [
            {
                "extension": stat.extension or ".",
                "label": extension_label(stat.extension),
                "size_text": format_bytes(stat.size),
                "percent": round(stat.size * 100 / total),
                "count": stat.count,
            }
            for stat in scan.extensions[:12]
        ]

    def _scan_root(self, mode: str) -> str:
        base = self._drive
        return empty_scan_root(base) if mode == "empty" else base

    # ── запуск отчётов ───────────────────────────────

    def set_drive(self, drive: str) -> dict[str, Any]:
        self._drive = normalize_root(drive)
        self._cache.clear()
        self._file_scan = None
        self._file_root = ""
        return self.state()

    def stop(self) -> None:
        if self._busy:
            self._cancel.set()

    def run(self, mode: str, notify, force: bool = False) -> str:
        """Отчёт в фоновом потоке; из кэша — мгновенный уведомляющий поток."""
        if self._busy:
            return "busy"
        root = self._scan_root(mode)
        key = (root, mode)
        self._last_mode = mode
        cached = self._cache.get(key) if not self._cancel.is_set() and not force else None
        if cached is not None:
            moment, payload = cached

            def cached_worker() -> None:
                notify(dict(
                    payload, mode=mode, cached=True,
                    when=moment.strftime("%H:%M"),
                ))

            threading.Thread(
                target=cached_worker, name="analyzer-cached", daemon=True
            ).start()
            return "started"

        self._busy = True
        self._cancel.clear()

        def worker() -> None:
            token = set_scan_cancel(self._cancel)
            try:
                payload = self._build_report(mode, root)
            except Exception:
                log.warning("Анализ %s упал", mode, exc_info=True)
                payload = {"mode": mode, "root": root, "error": True, "rows": []}
            finally:
                reset_scan_cancel(token)
                self._busy = False
            if not self._cancel.is_set():
                self._cache[(root, mode)] = (datetime.datetime.now(), payload)
            notify(dict(payload, mode=mode, cancelled=self._cancel.is_set()))

        threading.Thread(target=worker, name="analyzer-run", daemon=True).start()
        return "started"

    def _build_report(self, mode: str, root: str) -> dict[str, Any]:
        cancel = self._cancel
        if mode == "top":
            folders = scan_top_folders(root, 50, cancel=cancel)
            rows = [
                {
                    "index": i,
                    "name": f["name"],
                    "path": f["path"],
                    "size_text": format_bytes(f["size"]),
                }
                for i, f in enumerate(folders, 1)
            ]
            return {"mode": mode, "root": root, "rows": rows}

        if mode == "empty":
            empty = find_empty_folders(root, cancel=cancel)
            self._last_empty = empty
            self._last_empty_root = root
            rows = [{"path": p} for p in empty[:200]]
            return {
                "mode": mode,
                "root": root,
                "rows": rows,
                "count": len(empty),
                "hidden": max(0, len(empty) - 200),
            }

        if mode == "files":
            scan = scan_files(root, SCAN_FLOOR_MB, 5000, cancel=cancel)
            self._file_scan = scan
            self._file_root = root
            self._file_moment = datetime.datetime.now()
            return {
                "mode": mode,
                "root": root,
                "total_files": scan.total_files,
                "total_text": format_bytes(scan.total_bytes),
                "truncated": scan.truncated,
                "extensions": self._extension_chips(),
            }

        return {"mode": mode, "root": root, "rows": []}

    # ── фильтры файлов (без повторного скана) ────────

    def filter_files_report(
        self, extension: str = "", size_mb: int = SCAN_FLOOR_MB, age_days: int = 0
    ) -> dict[str, Any]:
        scan = self._file_scan
        if scan is None:
            return {"rows": [], "matched": 0, "matched_text": "0 Б"}
        matched = filter_files(scan.files, extension, size_mb, age_days)
        matched_total = sum(int(f.get("size", 0) or 0) for f in matched)
        rows = [
            {
                "index": i,
                "path": f["path"],
                "size_text": format_bytes(f["size"]),
                "modified_text": format_modified(float(f.get("modified", 0) or 0)),
                "age_text": format_age(float(f.get("modified", 0) or 0)),
            }
            for i, f in enumerate(matched[:REPORT_LIMIT], 1)
        ]
        return {
            "rows": rows,
            "matched": len(matched),
            "matched_text": format_bytes(matched_total),
            "hidden": max(0, len(matched) - REPORT_LIMIT),
            "total_files": scan.total_files,
            "total_text": format_bytes(scan.total_bytes),
            "truncated": scan.truncated,
        }

    # ── пустые папки: удаление ───────────────────────

    def remove_empty(self, notify) -> str:
        if self._busy or not self._last_empty:
            return "busy"
        folders = list(self._last_empty)
        root = self._last_empty_root or self._scan_root("empty")

        def worker() -> None:
            removed, errors = remove_empty_folders(folders, root=root)
            self._cache.clear()
            self._file_scan = None
            payload = {"removed": removed, "errors": errors[:10]}
            try:
                fresh = self._build_report("empty", self._scan_root("empty"))
            except Exception:
                log.warning("Повторный скан пустых папок упал", exc_info=True)
                fresh = {}
            self._cache[
                (self._scan_root("empty"), "empty")
            ] = (datetime.datetime.now(), fresh)
            notify(dict(payload, report=fresh))

        self._busy = True

        def runner() -> None:
            try:
                worker()
            finally:
                self._busy = False

        threading.Thread(target=runner, name="analyzer-empty", daemon=True).start()
        return "started"

    # ── treemap ──────────────────────────────────────

    def open_path(self, path: str) -> None:
        """Открыть папку в проводнике (клик по крупному прямоугольнику)."""
        import os

        if os.path.isdir(path):
            os.startfile(path)
        else:
            os.startfile(os.path.dirname(path))

    def treemap(self, path: str, back: bool, notify) -> str:
        """Узлы treemap: корень диска, drill-down или шаг назад."""

        def worker() -> None:
            try:
                if back:
                    nodes = self._treemap.go_back(TREEMAP_LIMIT) or []
                elif path:
                    target = next(
                        (n for n in (self._treemap._history[-1] if self._treemap._history else [])
                         if n.path == path and n.is_dir),
                        None,
                    )
                    if target is not None:
                        nodes = self._treemap.drill_down(target, TREEMAP_LIMIT)
                    else:
                        nodes = self._treemap.scan_root(path, TREEMAP_LIMIT)
                else:
                    nodes = self._treemap.scan_root(self._drive, TREEMAP_LIMIT)
            except Exception:
                log.warning("Treemap %s упал", path or self._drive, exc_info=True)
                nodes = []
            total = sum(n.size for n in nodes) or 1
            payload = {
                "nodes": [
                    {
                        "name": n.name,
                        "path": n.path,
                        "size_text": format_bytes(n.size),
                        "percent": round(n.size * 100 / total),
                        "is_dir": n.is_dir,
                    }
                    for n in nodes
                ],
                "path": path or self._drive,
                "can_back": self._treemap.can_go_back(),
            }
            notify(payload)

        threading.Thread(target=worker, name="analyzer-treemap", daemon=True).start()
        return "started"
