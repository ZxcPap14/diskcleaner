"""Слой данных для нового интерфейса: тот же движок, но без Tk.

Здесь нет ни одного виджета — только словари, которые уезжают в JS через
``window.pywebview.api``. Логика очистки переиспользуется полностью, поэтому
все существующие тесты движка продолжают проверять реальное поведение.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    reset_scan_cancel,
    set_scan_cancel,
)
from disk_cleaner_app.cleaners.registry import CleanerRegistry
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.models.target import LAYERS, layer_hint, layer_title
from disk_cleaner_app.services.cleaner import CleanEngine, CleanOptions
from disk_cleaner_app.services.elevation import is_admin
from disk_cleaner_app.services.planner import OperationPlan
from disk_cleaner_app.services.restore_point import create_restore_point
from disk_cleaner_app.services.scanner import ScanEngine

Progress = Callable[[int, int], None]


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class DeepService:
    """Цели глубокой очистки: список, анализ, план, очистка."""

    def __init__(self) -> None:
        self.config = ConfigManager()
        self.history = HistoryManager()
        self.registry = CleanerRegistry(self.config)
        self.scan_engine = ScanEngine()
        self.clean_engine = CleanEngine()
        self.cleaners: list[BaseCleaner] = []
        self.selected: set[str] = set()
        self.plan: OperationPlan | None = None
        self.plan_key: frozenset[str] = frozenset()
        self.busy = ""
        self.admin = is_admin()
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    @property
    def theme(self) -> str:
        """Тема из настроек: 'light' или 'dark' ('system' считаем тёмной)."""
        return "light" if str(self.config.get("theme", "dark")) == "light" else "dark"

    # ── состояние ────────────────────────────────────

    def load(self) -> list[dict[str, Any]]:
        with self._lock:
            self.cleaners = list(self.registry.get_all(include_auto=True))
            self.selected.clear()
            self.plan = None
            self.plan_key = frozenset()
        return self.targets()

    def targets(self) -> list[dict[str, Any]]:
        return [
            {
                "id": c.id,
                "name": c.name,
                "description": _short(c.description or c.why),
                "layer": c.layer,
                "safety": c.safety,
                "recommended": bool(c.recommended),
                "admin": bool(c.admin_required and not self.admin),
                "scanned": bool(c.scanned),
                "size": int(c.size),
                "size_text": format_bytes(c.size) if c.scanned else "",
                "error": _short(c.scan_error, 120),
                "selected": c.id in self.selected,
            }
            for c in self.cleaners
        ]

    def preview(self) -> dict[str, Any] | None:
        """Первые файлы внутри выбранной цели с предпросмотром."""
        with self._lock:
            chosen = [
                c for c in self.cleaners
                if c.id in self.selected and c.can_preview and c.preview_path
            ]
        if not chosen:
            return None
        item = chosen[0]
        root = Path(item.preview_path or "")
        files: list[dict[str, Any]] = []
        try:
            for child in list(root.iterdir())[:50]:
                try:
                    size = child.stat().st_size if child.is_file() else 0
                except OSError:
                    size = 0
                files.append({
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size_text": format_bytes(size) if size else "",
                })
        except OSError:
            files = []
        return {"name": item.name, "path": str(root), "files": files}

    def layers(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for layer in LAYERS:
            items = [c for c in self.cleaners if c.layer == layer]
            if not items and layer != LAYERS[-1]:
                continue
            out.append({
                "id": layer,
                "title": layer_title(layer),
                "hint": layer_hint(layer),
                "count": len(items),
                "scanned": sum(1 for c in items if c.scanned),
                "size": sum(c.size for c in items if c.scanned),
                "selected": sum(1 for c in items if c.id in self.selected),
                "reclaimable": layer != LAYERS[-1],
            })
        return out

    def summary(self) -> dict[str, Any]:
        scanned = [c for c in self.cleaners if c.scanned]
        chosen = [c for c in self.cleaners if c.id in self.selected]
        return {
            "selected": len(chosen),
            "selected_bytes": sum(c.size for c in chosen if c.scanned),
            "selected_text": format_bytes(sum(c.size for c in chosen if c.scanned)),
            "found": sum(c.size for c in scanned),
            "found_text": format_bytes(sum(c.size for c in scanned)),
            "scanned": len(scanned),
            "total": len(self.cleaners),
            "errors": sum(1 for c in self.cleaners if c.scan_error),
        }

    def state(self) -> dict[str, Any]:
        return {
            "admin": self.admin,
            "busy": self.busy,
            "targets": self.targets(),
            "layers": self.layers(),
            "summary": self.summary(),
            "to_recycle": bool(self.config.get("to_recycle", False)),
        }

    # ── анализ ───────────────────────────────────────

    def scan(self, progress: Progress, done: Callable[[dict[str, Any]], None]) -> None:
        if self.busy:
            return
        with self._lock:
            self.selected.clear()
            self.plan = None
            self.plan_key = frozenset()
        self._cancel.clear()
        self.busy = "scan"

        def worker() -> None:
            try:
                self.scan_engine.scan_all(
                    self.cleaners, auto_discover=False, progress_callback=progress,
                )
            finally:
                self.busy = ""
                done(self.state())

        threading.Thread(target=worker, daemon=True, name="deep-scan").start()

    def stop(self) -> None:
        self._cancel.set()
        self.scan_engine.cancel()

    # ── выбор ────────────────────────────────────────

    def toggle(self, target_id: str, value: bool) -> dict[str, Any]:
        if value:
            self.selected.add(target_id)
        else:
            self.selected.discard(target_id)
        self.plan = None
        return {"summary": self.summary(), "layers": self.layers()}

    def select_layer(self, layer: str, value: bool) -> dict[str, Any]:
        ids = [c.id for c in self.cleaners if c.layer == layer]
        if value:
            self.selected.update(ids)
        else:
            self.selected.difference_update(ids)
        self.plan = None
        return {"targets": self.targets(), "summary": self.summary(), "layers": self.layers()}

    def safe_set(self) -> dict[str, Any]:
        self.selected = {
            c.id for c in self.cleaners
            if c.layer in {"A", "B"} and c.recommended
        }
        self.plan = None
        return {"targets": self.targets(), "summary": self.summary(), "layers": self.layers()}

    def deselect_all(self) -> dict[str, Any]:
        self.selected.clear()
        self.plan = None
        return {"targets": self.targets(), "summary": self.summary(), "layers": self.layers()}

    # ── план и очистка ───────────────────────────────

    def _plan_dict(self, plan: OperationPlan) -> dict[str, Any]:
        actionable = [t for t in plan.targets if t.actions and t.cleaner.is_actionable]
        return {
            "id": plan.id,
            "actions": plan.action_count,
            "bytes": plan.total_bytes,
            "bytes_text": format_bytes(plan.total_bytes),
            "warnings": list(plan.warnings),
            "by_layer": [
                {
                    "layer": layer,
                    "title": layer_title(layer),
                    "bytes": size,
                    "text": format_bytes(size),
                }
                for layer, size in sorted(plan.total_by_layer.items())
                if size
            ],
            "targets": [
                {
                    "id": t.cleaner.id,
                    "name": t.cleaner.name,
                    "layer": t.layer,
                    "bytes": t.planned_bytes,
                    "text": format_bytes(t.planned_bytes),
                    "actions": len(t.actions),
                    "blocked": t.blocked,
                    "reclaimable": t.cleaner.is_actionable,
                }
                for t in plan.targets
                if t.actions or t.blocked
            ],
            "admin_skipped": sum(1 for t in actionable if t.blocked),
        }

    def build_plan(self, notify: Callable[[dict[str, Any]], None]) -> None:
        if self.busy:
            return
        chosen = [c for c in self.cleaners if c.id in self.selected]
        key = frozenset(self.selected)
        if self.plan is not None and self.plan_key == key:
            notify(self._plan_dict(self.plan))
            return
        self.busy = "plan"

        def worker() -> None:
            token = set_scan_cancel(self._cancel)
            try:
                self.plan = self.clean_engine.build_plan(chosen)
                self.plan_key = key
            finally:
                reset_scan_cancel(token)
                self.busy = ""
            notify(self._plan_dict(self.plan))

        threading.Thread(target=worker, daemon=True, name="deep-plan").start()

    def clean(
        self,
        progress: Callable[[int, int, dict[str, Any]], None],
        done: Callable[[dict[str, Any]], None],
    ) -> None:
        plan = self.plan
        if plan is None or self.busy:
            return
        options = CleanOptions(
            to_recycle=bool(self.config.get("to_recycle", False)),
            safe_mode=bool(self.config.get("safe_mode", True)),
        )
        self.busy = "clean"
        self._cancel.clear()

        def worker() -> None:
            results: list[dict[str, Any]] = []
            started = time.perf_counter()
            try:
                if bool(self.config.get("restore_point", False)):
                    create_restore_point()
                for index, result in enumerate(
                    self.clean_engine.clean_plan(plan, options, None), start=1
                ):
                    results.append({
                        "name": result.cleaner.name,
                        "status": result.status,
                        "detail": _short(result.detail, 200),
                        "freed": result.freed,
                        "freed_text": format_bytes(result.freed),
                    })
                    progress(index, plan.action_count, results[-1])
            finally:
                self.busy = ""
                done({
                    "results": results,
                    "seconds": round(time.perf_counter() - started, 1),
                    "state": self.state(),
                })

        threading.Thread(target=worker, daemon=True, name="deep-clean").start()
