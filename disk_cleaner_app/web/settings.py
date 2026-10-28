"""Данные страницы «Настройки»: конфиг, правила, история, расписание, обновления."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from disk_cleaner_app import __version__
from disk_cleaner_app.models.config import CONFIG_DIR, ConfigManager
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.logging_setup import LOG_FILE
from disk_cleaner_app.services.updater import check_for_updates

log = logging.getLogger(__name__)

# Ключи, которые разрешено менять из интерфейса.
EDITABLE_KEYS = {
    "theme", "to_recycle", "safe_mode", "restore_point", "deep_threshold_gb",
    "tray_enabled", "start_minimized", "update_source",
}

SAFETY_LABELS = {"🟢": "Безопасно", "🟡": "Осторожно", "🔴": "Продвинутый"}
DAY_TO_SCHTASKS = {
    "ПН": "MON", "ВТ": "TUE", "СР": "WED", "ЧТ": "THU",
    "ПТ": "FRI", "СБ": "SAT", "ВС": "SUN",
}


class SettingsService:
    """Читает и пишет конфиг; тяжёлые операции — через методы Api."""

    def __init__(self, config: ConfigManager, history: HistoryManager,
                 reload_cleaners) -> None:
        self._config = config
        self._history = history
        self._reload_cleaners = reload_cleaners

    # ── состояние страницы ───────────────────────────

    def state(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "theme": str(self._config.get("theme", "dark")),
            "to_recycle": bool(self._config.get("to_recycle", False)),
            "safe_mode": bool(self._config.get("safe_mode", True)),
            "restore_point": bool(self._config.get("restore_point", False)),
            "threshold": str(self._config.get("deep_threshold_gb", 10)),
            "tray_enabled": bool(self._config.get("tray_enabled", False)),
            "start_minimized": bool(self._config.get("start_minimized", False)),
            "autostart": self._autostart_enabled(),
            "update_source": str(self._config.get("update_source", "")),
            "whitelist": self._whitelist(),
            "rules": self._rules(),
            "history": self._history_summary(),
            "schedule": self._schedule_state(),
            "data_dir": str(CONFIG_DIR),
            "log_exists": LOG_FILE.exists(),
        }

    # ── конфиг ───────────────────────────────────────

    def set(self, key: str, value: Any) -> dict[str, Any]:
        if key not in EDITABLE_KEYS:
            raise ValueError(f"Ключ {key} нельзя менять из интерфейса")
        if key == "deep_threshold_gb":
            raw = str(value).strip().replace(",", ".")
            try:
                value = max(0.0, float(raw))
            except ValueError:
                value = 10.0
        self._config.set(key, value)
        return self.state()

    # ── белый список ─────────────────────────────────

    def _whitelist(self) -> list[str]:
        raw = self._config.get("whitelist", [])
        if isinstance(raw, list):
            return [str(w) for w in raw if str(w).strip()]
        return []

    def whitelist_add(self, path: str) -> dict[str, Any]:
        path = path.strip()
        if not path:
            raise ValueError("Укажите путь.")
        entries = self._whitelist()
        if path not in entries:
            entries.append(path)
            self._config.set("whitelist", entries)
        return self.state()

    def whitelist_remove(self, path: str) -> dict[str, Any]:
        entries = [w for w in self._whitelist() if w != path]
        self._config.set("whitelist", entries)
        return self.state()

    # ── правила ──────────────────────────────────────

    def _rules(self) -> list[dict[str, Any]]:
        return [
            {
                "id": str(rule.get("id", "")),
                "name": rule.get("name", "?"),
                "path": rule.get("path", "?"),
                "safety": rule.get("safety", "🟡"),
                "safety_label": SAFETY_LABELS.get(rule.get("safety", "🟡"), "Осторожно"),
            }
            for rule in self._config.load_custom_rules()
        ]

    def save_rule(self, rule_id: str, name: str, path: str, safety: str) -> dict[str, Any]:
        """Добавить (rule_id="") или изменить правило."""
        if rule_id:
            self._config.update_custom_rule(rule_id, name, path, safety)
        else:
            self._config.add_custom_rule(name, path, safety)
        self._reload_cleaners()
        return self.state()

    def delete_rule(self, rule_id: str) -> dict[str, Any]:
        self._config.remove_custom_rule(rule_id)
        self._reload_cleaners()
        return self.state()

    # ── история и файлы ──────────────────────────────

    def _history_summary(self) -> dict[str, Any]:
        rows = self._history.get_recent(5)
        return {
            "count": self._history.count(),
            "total_text": format_bytes(self._history.total_freed()),
            "recent": [
                {
                    "when": str(row[0])[:19],
                    "targets": row[1],
                    "freed_text": format_bytes(row[2]),
                }
                for row in rows
            ],
        }

    def clear_history(self) -> dict[str, Any]:
        self._history.clear()
        return self.state()

    def open_data_dir(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        import os

        os.startfile(str(CONFIG_DIR))

    def open_log(self) -> None:
        if not LOG_FILE.exists():
            raise FileNotFoundError("Файл лога ещё не создан.")
        import os

        os.startfile(str(LOG_FILE))

    # ── расписание ───────────────────────────────────

    def _schedule_state(self) -> dict[str, Any]:
        from disk_cleaner_app.services.schedule import schedule_exists

        mode = str(self._config.get("schedule_mode", "smart"))
        try:
            exists = schedule_exists()
        except Exception:
            log.warning("Не удалось опросить schtasks", exc_info=True)
            exists = False
        return {
            "exists": exists,
            "mode": mode,
            "mode_text": "Smart Clean" if mode != "deep-safe" else "Deep: безопасный набор",
        }

    def install_schedule(self, day: str, at: str, mode: str) -> dict[str, Any]:
        from disk_cleaner_app.services.schedule import install_schedule

        if mode not in ("smart", "deep-safe"):
            mode = "smart"
        self._config.set("schedule_mode", mode)
        ok, message = install_schedule(
            day=DAY_TO_SCHTASKS.get(day, "SUN"), at=at or "09:00"
        )
        if not ok:
            raise ValueError(message)
        return self.state()

    def remove_schedule(self) -> dict[str, Any]:
        from disk_cleaner_app.services.schedule import uninstall_schedule

        ok, message = uninstall_schedule()
        if not ok:
            raise ValueError(message)
        return self.state()

    # ── обновления ───────────────────────────────────

    def check_updates(self, notify) -> str:
        url = str(self._config.get("update_source", "")).strip()

        def worker() -> None:
            if not url:
                notify({
                    "status": "disabled",
                    "message": "Задайте owner/repo или адрес манифеста — проверка выключена.",
                })
                return
            result = check_for_updates(__version__, url)
            notify(result)

        threading.Thread(target=worker, name="settings-updates", daemon=True).start()
        return "started"

    # ── трей и автозапуск ────────────────────────────

    def _autostart_enabled(self) -> bool:
        try:
            from disk_cleaner_app.services.autostart_self import get_autostart

            return get_autostart() is not None
        except Exception:
            return False

    def set_autostart(self, enabled: bool) -> dict[str, Any]:
        from disk_cleaner_app.services.autostart_self import set_autostart

        _ok, message = set_autostart(enabled)
        state = self.state()
        if not state["autostart"] and enabled:
            raise ValueError(message)
        return state

    # ── резервные копии и отчёты ─────────────────────

    def export_config(self, path: str) -> Path:
        return self._config.export_config(Path(path))

    def import_config(self, path: str) -> dict[str, Any]:
        stats = self._config.import_config(Path(path))
        self._reload_cleaners()
        return stats

    def export_report(self, kind: str, path: str) -> Path:
        from disk_cleaner_app.services.reports import export_csv, export_json

        target = Path(path)
        if kind == "csv":
            return export_csv(self._history, target)
        return export_json(self._history, target)
