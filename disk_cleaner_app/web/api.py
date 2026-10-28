"""Мост между вёрсткой и движком: методы, которые вызывает JS.

pywebview отдаёт наружу каждый публичный метод, поэтому имена короткие,
а возвращаемые значения — обычные словари (их сериализует json).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

import webview

from disk_cleaner_app.web import win
from disk_cleaner_app.web.analyzer import AnalyzerService
from disk_cleaner_app.web.dashboard import DashboardService
from disk_cleaner_app.web.disks import DisksService
from disk_cleaner_app.web.duplicates import DuplicatesService
from disk_cleaner_app.web.history import HistoryService
from disk_cleaner_app.web.programs import ProgramsService
from disk_cleaner_app.web.service import DeepService
from disk_cleaner_app.web.settings import SettingsService
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
        self._disks = DisksService(self._deep.history)
        self._analyzer = AnalyzerService()
        self._settings = SettingsService(
            self._deep.config, self._deep.history, self._deep.load,
        )

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

    # ── диски ────────────────────────────────────────

    def disks_state(self) -> dict[str, Any]:
        return self._disks.load()

    def disks_smart(self) -> str:
        def notify(payload: dict[str, Any]) -> None:
            self._call("dc.disksSmart(" + json.dumps(payload) + ")")

        self._disks.load_smart(notify)
        return "started"

    # ── анализ ───────────────────────────────────────

    def analyzer_state(self) -> dict[str, Any]:
        return self._analyzer.state()

    def analyzer_set_drive(self, drive: str) -> dict[str, Any]:
        return self._analyzer.set_drive(drive)

    def analyzer_run(self, mode: str, force: bool = False) -> str:
        def notify(payload: dict[str, Any]) -> None:
            self._call("dc.analyzerDone(" + json.dumps(payload) + ")")

        return self._analyzer.run(mode, notify, force)

    def analyzer_open(self, path: str) -> dict[str, Any]:
        self._analyzer.open_path(path)
        return {"ok": True}

    def analyzer_stop(self) -> str:
        self._analyzer.stop()
        return "ok"

    def analyzer_filter(
        self, extension: str, size_mb: int, age_days: int
    ) -> dict[str, Any]:
        return self._analyzer.filter_files_report(extension, size_mb, age_days)

    def analyzer_remove_empty(self) -> str:
        def notify(payload: dict[str, Any]) -> None:
            self._call("dc.analyzerEmptied(" + json.dumps(payload) + ")")

        return self._analyzer.remove_empty(notify)

    def analyzer_treemap(self, path: str, back: bool) -> str:
        def notify(payload: dict[str, Any]) -> None:
            self._call("dc.analyzerTreemap(" + json.dumps(payload) + ")")

        return self._analyzer.treemap(path, back, notify)

    # ── настройки ────────────────────────────────────

    def settings_state(self) -> dict[str, Any]:
        return self._settings.state()

    def settings_set(self, key: str, value: Any) -> dict[str, Any]:
        return self._settings.set(key, value)

    def whitelist_add(self, path: str) -> dict[str, Any]:
        return self._settings.whitelist_add(path)

    def whitelist_remove(self, path: str) -> dict[str, Any]:
        return self._settings.whitelist_remove(path)

    def rule_save(
        self, rule_id: str, name: str, path: str, safety: str
    ) -> dict[str, Any]:
        return self._settings.save_rule(rule_id, name, path, safety)

    def rule_delete(self, rule_id: str) -> dict[str, Any]:
        return self._settings.delete_rule(rule_id)

    def history_clear(self) -> dict[str, Any]:
        return self._settings.clear_history()

    def open_special(self, kind: str) -> dict[str, Any]:
        """Открыть папку данных или файл лога."""
        if kind == "log":
            self._settings.open_log()
        else:
            self._settings.open_data_dir()
        return {"ok": True}

    def autostart_set(self, enabled: bool) -> dict[str, Any]:
        return self._settings.set_autostart(enabled)

    def schedule_install(self, day: str, at: str, mode: str) -> dict[str, Any]:
        return self._settings.install_schedule(day, at, mode)

    def schedule_remove(self) -> dict[str, Any]:
        return self._settings.remove_schedule()

    def check_updates(self) -> str:
        def notify(payload: dict[str, Any]) -> None:
            self._call("dc.updateResult(" + json.dumps(payload) + ")")

        return self._settings.check_updates(notify)

    def export_report(self, kind: str) -> dict[str, Any]:
        suffix = ".json" if kind == "json" else ".csv"
        default = f"DiskCleaner-report{suffix}"
        path = self._save_dialog(default, [("JSON", "*.json")] if kind == "json" else [("CSV", "*.csv")])
        if not path:
            return {"ok": False, "cancelled": True}
        target = self._settings.export_report(kind, path)
        return {"ok": True, "path": str(target)}

    def config_export(self) -> dict[str, Any]:
        path = self._save_dialog(
            "DiskCleaner-config.json", [("JSON", "*.json")]
        )
        if not path:
            return {"ok": False, "cancelled": True}
        target = self._settings.export_config(path)
        return {"ok": True, "path": str(target)}

    def config_import(self) -> dict[str, Any]:
        picked = self._open_dialog([("JSON", "*.json")])
        if not picked:
            return {"ok": False, "cancelled": True}
        stats = self._settings.import_config(picked)
        return {"ok": True, "stats": stats}

    # ── диалоги файлов ───────────────────────────────

    def _save_dialog(
        self, default_name: str, file_types: list[tuple[str, str]]
    ) -> str | None:
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.SAVE,  # type: ignore[attr-defined]
                save_filename=default_name,
                file_types=tuple(f"{label} ({pattern})" for label, pattern in file_types),
            )
        except Exception:  # noqa: BLE001
            log.warning("Диалог сохранения недоступен", exc_info=True)
            return None
        if isinstance(result, (list, tuple)):
            result = result[0] if result else None
        return str(result) if result else None

    def _open_dialog(self, file_types: list[tuple[str, str]]) -> str | None:
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,  # type: ignore[attr-defined]
                allow_multiple=False,
                file_types=tuple(f"{label} ({pattern})" for label, pattern in file_types),
            )
        except Exception:  # noqa: BLE001
            log.warning("Диалог открытия недоступен", exc_info=True)
            return None
        if isinstance(result, (list, tuple)):
            result = result[0] if result else None
        return str(result) if result else None

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
        def worker() -> None:
            try:
                # Скрыть и выйти немедленно: destroy() дожидается разборки
                # WebView2, из-за чего приложение «висело» пару секунд.
                self._window.hide()
            finally:
                os._exit(0)

        threading.Thread(target=worker, daemon=True).start()
        return "ok"

    def elevate(self) -> dict[str, Any]:
        """Перезапуститься с правами администратора (UAC)."""
        from disk_cleaner_app.services.elevation import is_admin, request_elevation

        if is_admin():
            return {"ok": False, "message": "Права администратора уже есть."}

        def worker() -> None:
            if request_elevation():
                # Новая копия уже запущена UAC — текущую закрываем.
                try:
                    self._window.hide()
                finally:
                    os._exit(0)
            self._call(
                'dc.elevateFailed("Запрос UAC отклонён или не выполнен")'
            )

        threading.Thread(target=worker, daemon=True, name="elevation").start()
        return {"ok": True, "started": True}

    # ── служебное ────────────────────────────────────

    def _call(self, script: str) -> None:
        """Выполнить JS из рабочего потока (pywebview это разрешает)."""
        if self._window is None:
            return
        try:
            self._window.evaluate_js(script)
        except Exception:
            log.debug("Не удалось вызвать JS: %s", script, exc_info=True)
