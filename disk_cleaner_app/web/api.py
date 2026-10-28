"""Мост между вёрсткой и движком: методы, которые вызывает JS.

pywebview отдаёт наружу каждый публичный метод, поэтому имена короткие,
а возвращаемые значения — обычные словари (их сериализует json).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from disk_cleaner_app.web import win
from disk_cleaner_app.web.dashboard import DashboardService
from disk_cleaner_app.web.service import DeepService

log = logging.getLogger(__name__)


class Api:
    """``window.pywebview.api`` — единственная точка входа из JS."""

    def __init__(self) -> None:
        self._window: Any = None
        self._deep = DeepService()
        self._home = DashboardService(self._deep)

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
