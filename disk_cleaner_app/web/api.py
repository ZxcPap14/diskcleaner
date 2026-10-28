"""Мост между вёрсткой и движком: методы, которые вызывает JS.

pywebview отдаёт наружу каждый публичный метод, поэтому имена короткие,
а возвращаемые значения — обычные словари (их сериализует json).
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

import webview

from disk_cleaner_app.web import win
from disk_cleaner_app.web.dashboard import DashboardService
from disk_cleaner_app.web.duplicates import DuplicatesService
from disk_cleaner_app.web.history import HistoryService
from disk_cleaner_app.web.programs import ProgramsService
from disk_cleaner_app.web.service import DeepService
from disk_cleaner_app.web.startup import StartupService

log = logging.getLogger(__name__)


class Api:
    """``window.pywebview.api`` — единственная точка входа из JS."""

    def __init__(self) -> None:
        self._window: Any = None
        self._deep = DeepService()
        self._home = DashboardService(self._deep)
        self._hist = HistoryService(self._deep.history)
        self._prog = ProgramsService()
        self._prog_busy = False
        self._startup = StartupService()
        self._dup = DuplicatesService()

    # ── запуск ───────────────────────────────────────

    def bootstrap(self) -> dict[str, Any]:
        self._deep.load()
        return {
            "workers": [{"icon": "E80F", "label": "Главная"}],
            "theme": self._deep.theme,
            "state": self._deep.state(),
            "home": self._home.state(),
        }

    def state(self) -> dict[str, Any]:
        return self._deep.state()

    # ── главная ──────────────────────────────────────

    def home_state(self) -> dict[str, Any]:
        return self._home.state()

    def home_drive(self, drive: str) -> dict[str, Any]:
        return self._home.set_drive(drive)

    # ── выбор ────────────────────────────────────────

    def toggle(self, target_id: str, value: bool) -> dict[str, Any]:
        return self._deep.toggle(target_id, value)

    def select_layer(self, layer: str, value: bool) -> dict[str, Any]:
        return self._deep.select_layer(layer, value)

    def safe_set(self) -> dict[str, Any]:
        return self._deep.safe_set()

    def deselect_all(self) -> dict[str, Any]:
        return self._deep.deselect_all()

    def preview(self) -> dict[str, Any] | None:
        return self._deep.preview()

    def history_state(self) -> dict[str, Any]:
        return self._hist.state()

    # ── дубликаты ────────────────────────────────────

    def dup_state(self) -> dict[str, Any]:
        return self._dup.state()

    def dup_root(self, path: str) -> dict[str, Any]:
        return self._dup.set_root(path)

    def dup_pick(self) -> dict[str, Any]:
        """Системный выбор папки; на отмену возвращаем текущее состояние."""
        try:
            picked = self._window.create_file_dialog(webview.FileDialog.FOLDER)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            log.warning("Диалог выбора папки недоступен", exc_info=True)
            return self._dup.state()
        if picked:
            return self._dup.set_root(picked[0])
        return self._dup.state()

    def dup_scan(self, mode: str) -> str:
        def progress(scanned: int, text: str) -> None:
            self._call(f"dc.dupProgress({scanned}, {json.dumps(text)})")

        def done(state: dict[str, Any]) -> None:
            self._call("dc.dupDone(" + json.dumps(state) + ")")

        self._dup.scan(mode, progress, done)
        return "started"

    def dup_stop(self) -> dict[str, Any]:
        return self._dup.stop()

    def dup_delete(self, paths: list[str], to_recycle: bool = True) -> str:
        def worker() -> None:
            result = self._dup.delete(list(paths), to_recycle)
            self._call("dc.dupDeleted(" + json.dumps(result) + ")")

        threading.Thread(target=worker, name="dup-delete", daemon=True).start()
        return "started"

    # ── программы ────────────────────────────────────

    def programs_state(self) -> dict[str, Any]:
        return self._prog.load()

    def startup_state(self) -> dict[str, Any]:
        return self._startup.load()

    def startup_toggle(self, item_id: str, enabled: bool) -> dict[str, Any]:
        return self._startup.toggle(item_id, enabled)

    def programs_measure(self) -> str:
        if self._prog_busy:
            return "busy"

        def notify(batch: list[dict[str, Any]]) -> None:
            self._call("dc.programsSizes(" + json.dumps(batch) + ")")

        def worker() -> None:
            try:
                self._prog.measure(notify)
            finally:
                self._prog_busy = False
                self._call("dc.programsMeasured()")

        self._prog_busy = True
        threading.Thread(target=worker, daemon=True).start()
        return "ok"

    def programs_uninstall(self, app_id: str) -> str:
        def worker() -> None:
            payload = self._prog.uninstall(app_id)
            self._call("dc.programsUninstalled(" + json.dumps(payload) + ")")

        threading.Thread(target=worker, daemon=True).start()
        return "ok"

    # ── анализ ───────────────────────────────────────

    def scan(self) -> str:
        self._call("dc.scanStarted()")

        def progress(done: int, total: int) -> None:
            self._call(f"dc.progress({done}, {total})")

        def done(state: dict[str, Any]) -> None:
            self._call("dc.scanDone(" + json.dumps(state) + ")")

        self._deep.scan(progress, done)
        return "ok"

    def stop_scan(self) -> str:
        self._deep.stop()
        return "ok"

    # ── план и очистка ───────────────────────────────

    def build_plan(self) -> str:
        self._call("dc.planStarted()")

        def notify(plan: dict[str, Any]) -> None:
            self._call("dc.planReady(" + json.dumps(plan) + ")")

        self._deep.build_plan(notify)
        return "ok"

    def clean(self) -> str:
        def progress(done: int, total: int, result: dict[str, Any]) -> None:
            self._call(
                f"dc.cleanProgress({done}, {total}, " + json.dumps(result) + ")"
            )

        def done(payload: dict[str, Any]) -> None:
            self._call("dc.cleanDone(" + json.dumps(payload) + ")")

        self._deep.clean(progress, done)
        return "ok"

    def set_option(self, key: str, value: Any) -> dict[str, Any]:
        if key in {"to_recycle", "safe_mode", "restore_point"}:
            self._deep.config.set(key, value)
        return self._deep.state()

    # ── окно ─────────────────────────────────────────

    def win_drag(self) -> str:
        win.begin_drag(self._window)
        return "ok"

    def win_resize(self, edge: str) -> str:
        win.begin_resize(self._window, edge)
        return "ok"

    def win_min(self) -> str:
        win.minimize(self._window)
        return "ok"

    def win_max(self) -> bool:
        return win.toggle_maximize(self._window)

    def win_close(self) -> str:
        self._window.destroy()
        return "ok"

    # ── служебное ────────────────────────────────────

    def _call(self, script: str) -> None:
        """Выполнить JS из рабочего потока (pywebview это разрешает)."""
        if self._window is None:
            return
        try:
            self._window.evaluate_js(script)
        except Exception:
            log.debug("Не удалось вызвать JS: %s", script, exc_info=True)
