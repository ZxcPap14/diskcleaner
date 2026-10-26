"""MainWindow — главное окно приложения."""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from disk_cleaner_app import __version__
from disk_cleaner_app.cleaners.base import get_disk_free
from disk_cleaner_app.cleaners.registry import CleanerRegistry
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.services.elevation import is_admin, request_elevation
from disk_cleaner_app.services.logging_setup import install_exception_hooks, setup_logging
from disk_cleaner_app.services.reports import (
    export_csv,
    export_entries_csv,
    export_entries_json,
    export_json,
)
from disk_cleaner_app.ui.assets import CONTENT_PAD, SPACE_2
from disk_cleaner_app.ui.components.header import HeaderBar
from disk_cleaner_app.ui.components.sidebar import NavigationSidebar
from disk_cleaner_app.ui.components.statusbar import StatusBar
from disk_cleaner_app.ui.theme import ThemeManager
from disk_cleaner_app.ui.views.analyzer import AnalyzerView
from disk_cleaner_app.ui.views.dashboard import DashboardView
from disk_cleaner_app.ui.views.deep_clean import DeepCleanView
from disk_cleaner_app.ui.views.disks import DisksView
from disk_cleaner_app.ui.views.duplicates import DuplicatesView
from disk_cleaner_app.ui.views.history import HistoryView
from disk_cleaner_app.ui.views.settings import SettingsView
from disk_cleaner_app.ui.views.smart_clean import SmartCleanView
from disk_cleaner_app.ui.views.startup import StartupView
from disk_cleaner_app.ui.views.uninstaller import UninstallerView


class MainWindow:
    """Главное окно — сборка всего приложения."""

    def __init__(self) -> None:
        setup_logging()
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        install_exception_hooks(self.root)
        self.root.title(f"DiskCleaner Pro {__version__}")
        self.root.geometry("1180x760")
        self.root.minsize(1024, 660)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Инициализация модулей ──
        self.config = ConfigManager()
        self.history = HistoryManager()
        self.theme = ThemeManager(self.config.get("theme", "dark"))
        self.registry = CleanerRegistry(self.config)
        self._drive: str | None = None

        self.root.configure(fg_color=self.theme.colors.SURFACE)

        # ── Сборка UI ──
        self._build_layout()

        # ── Загрузка данных ──
        self._update_disk_info()
        self._switch_view("dashboard")

        # ── Хоткеи ──
        self.root.bind("<Control-s>", lambda e: self._on_scan())
        self.root.bind("<Control-c>", lambda e: self._on_clean())
        self.root.bind("<Control-a>", lambda e: self._select_all())

    def run(self) -> None:
        """Запустить главный цикл Tk."""
        self.root.mainloop()

    def _on_close(self) -> None:
        """Остановить фоновые задачи и закрыть окно."""
        if getattr(self, "_closing", False):
            return
        self._closing = True
        for view in getattr(self, "views", {}).values():
            try:
                view.destroy()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ─────────────────────────────────────
    # LAYOUT
    # ─────────────────────────────────────

    def _build_layout(self) -> None:
        outer = ctk.CTkFrame(self.root, fg_color="transparent")
        outer.pack(fill="both", expand=True)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1, minsize=360)

        self.header = HeaderBar(
            outer, self.theme,
            on_theme_toggle=self._toggle_theme,
            on_settings=lambda: self._switch_view("settings"),
            on_elevate=self._request_admin,
        )
        self.header.grid(
            row=0, column=0, sticky="ew", padx=CONTENT_PAD + 4, pady=(6, 0),
        )
        self.header.set_admin_status(is_admin())

        middle = ctk.CTkFrame(outer, fg_color="transparent")
        middle.grid(
            row=1, column=0, sticky="nsew", padx=CONTENT_PAD + 4,
            pady=(SPACE_2, SPACE_2),
        )
        middle.grid_rowconfigure(0, weight=1)
        middle.grid_columnconfigure(1, weight=1)

        self.sidebar = NavigationSidebar(
            middle, self.theme,
            on_navigate=self._switch_view,
        )
        self.sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 14))

        self.content_card = ctk.CTkFrame(middle, fg_color="transparent")
        self.content_card.grid(row=0, column=1, sticky="nsew")

        self.views_frame = ctk.CTkFrame(self.content_card, fg_color="transparent")
        self.views_frame.pack(fill="both", expand=True)

        self.statusbar = StatusBar(outer, self.theme)
        self.statusbar.grid(
            row=2, column=0, sticky="ew", padx=CONTENT_PAD + 4, pady=(0, 10),
        )

        self._build_views()

    def _build_views(self) -> None:
        self.views: dict[str, ctk.CTkFrame] = {}

        self.views["dashboard"] = DashboardView(
            self.views_frame, self.theme,
            on_quick_clean=self._quick_clean,
            on_clean_target=self._clean_target_from_dashboard,
            on_drive_change=self._set_dashboard_drive,
            on_deep_clean=self._go_deep_from_dashboard,
            history=self.history,
        )

        self.views["clean"] = SmartCleanView(
            self.views_frame, self.theme, self.config,
            on_log=self.statusbar.log,
            statusbar=self.statusbar,
            on_reload=lambda: self._load_cleaners(force=True),
        )

        self.views["deep"] = DeepCleanView(
            self.views_frame, self.theme, self.config,
            on_log=self.statusbar.log,
            statusbar=self.statusbar,
            on_reload=lambda: self._load_deep_cleaners(force=True),
            on_elevate=self._request_admin,
            get_drive=lambda: self._drive,
        )

        self.views["analyzer"] = AnalyzerView(
            self.views_frame, self.theme,
            on_log=self.statusbar.log,
            statusbar=self.statusbar,
            get_drive=lambda: self._drive,
        )

        self.views["disks"] = DisksView(
            self.views_frame, self.theme,
            on_log=self.statusbar.log,
            statusbar=self.statusbar,
        )

        self.views["duplicates"] = DuplicatesView(
            self.views_frame, self.theme,
            on_log=self.statusbar.log,
        )

        self.views["history"] = HistoryView(
            self.views_frame, self.theme,
            history_getter=self.history.get_all,
            on_export=self._export_report,
        )

        self.views["startup"] = StartupView(
            self.views_frame, self.theme,
            on_log=self.statusbar.log,
        )

        self.views["uninstaller"] = UninstallerView(
            self.views_frame, self.theme,
            on_log=self.statusbar.log,
            statusbar=self.statusbar,
        )

        self.views["settings"] = SettingsView(
            self.views_frame, self.theme,
            config_saver=self._save_config_option,
            config_getter=self.config.get,
            history_getter=self.history.get_recent,
            rules_getter=self.config.load_custom_rules,
            total_freed_getter=self.history.total_freed,
            on_clear_history=self._clear_history,
            on_add_rule=self._add_rule,
            on_update_rule=self._update_rule,
            on_remove_rule=self._remove_rule,
            config_exporter=self._export_config,
            config_importer=self._import_config,
            report_exporter=self._export_report,
        )

    # ─────────────────────────────────────
    # NAVIGATION
    # ─────────────────────────────────────

    def _switch_view(self, vid: str) -> None:
        self.sidebar.set_active(vid)
        for view in self.views.values():
            view.pack_forget()
        if vid in self.views:
            self.views[vid].pack(fill="both", expand=True)
            if vid == "dashboard":
                self._update_disk_info()
                self._refresh_dashboard()
            elif vid == "settings":
                self.views["settings"].refresh()
            elif vid == "history":
                self.views["history"].refresh()
            elif vid == "clean":
                self._load_cleaners()
            elif vid == "deep":
                self._load_deep_cleaners()
            elif vid == "disks":
                self.views["disks"].refresh()

    # ─────────────────────────────────────
    # THEME
    # ─────────────────────────────────────

    def _toggle_theme(self) -> None:
        self.theme.toggle()
        self.config.set("theme", self.theme.mode)
        self._apply_theme()

    def _request_admin(self) -> None:
        if is_admin():
            messagebox.showinfo(
                "Права администратора",
                "Приложение уже запущено с правами администратора.",
            )
            return
        if not messagebox.askyesno(
            "Права администратора",
            "Перезапустить DiskCleaner от имени администратора?\n\n"
            "Это откроет системный запрос UAC. Текущее окно будет закрыто.",
        ):
            return
        if request_elevation():
            self._on_close()
        else:
            messagebox.showwarning(
                "Права администратора",
                "Не удалось перезапустить приложение. Возможно, запрос UAC отклонён.",
            )

    def _save_config_option(self, key: str, value: object) -> None:
        if isinstance(value, str) and value.lower() in ("true", "false"):
            self.config.set(key, value.lower() == "true")
        else:
            self.config.set(key, value)
        if key == "theme" and isinstance(value, str):
            self.theme.mode = value
            self._apply_theme()

    def _apply_theme(self) -> None:
        c = self.theme.colors
        self.root.configure(fg_color=c.SURFACE)
        self.content_card.configure(fg_color="transparent")
        self.views_frame.configure(fg_color="transparent")
        self.theme.notify()
        for view in self.views.values():
            if hasattr(view, "refresh_theme"):
                try:
                    view.refresh_theme()
                except Exception:
                    pass

    # ─────────────────────────────────────
    # DISK INFO
    # ─────────────────────────────────────

    def _update_disk_info(self) -> None:
        free, total = get_disk_free(self._drive)
        if total > 0:
            self.header.update_disk(free, total)
            self.header.update_history(self.history.total_freed())

    def _set_dashboard_drive(self, drive: str) -> None:
        self._drive = drive
        dashboard = self.views.get("dashboard")
        if dashboard is not None and hasattr(dashboard, "set_drive"):
            dashboard.set_drive(drive)
        self._update_disk_info()
        self._refresh_dashboard()
        analyzer = self.views.get("analyzer")
        if analyzer is not None and hasattr(analyzer, "set_drive"):
            analyzer.set_drive(drive)
        self.statusbar.set_status(f"Диск {drive}")

    def _refresh_dashboard(self) -> None:
        free, total = get_disk_free(self._drive)
        if "dashboard" not in self.views:
            return
        dv = self.views["dashboard"]
        if not hasattr(dv, "update_stats"):
            return
        dv.update_stats(
            free, total,
            self.history.total_freed(),
            self.history.count(),
        )

        cleaners = getattr(self.views.get("clean"), "_all_cleaners", []) or []
        targets = sorted(
            (c for c in cleaners if c.scanned and c.size > 0),
            key=lambda c: c.size,
            reverse=True,
        )
        if hasattr(dv, "set_targets"):
            dv.set_targets(targets)
        if hasattr(dv, "set_last_clean"):
            try:
                dv.set_last_clean(self.history.get_last())
            except Exception:
                dv.set_last_clean(None)

    def _clean_target_from_dashboard(self, cleaner) -> None:
        self._switch_view("clean")
        self._load_cleaners()
        cv = self.views.get("clean")
        if (
            cv is not None
            and hasattr(cv, "focus_cleaner")
            and cv.focus_cleaner(cleaner.id)
        ):
            self.statusbar.set_status(f"Выбрана цель: {cleaner.name}")
        else:
            self.statusbar.log(f"Цель недоступна: {cleaner.name}")

    # ─────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────

    def _load_cleaners(self, force: bool = False) -> None:
        if "clean" not in self.views:
            return
        cv = self.views["clean"]
        if not hasattr(cv, "load_cleaners"):
            return
        if not force and getattr(cv, "_all_cleaners", None):
            return
        cleaners = self.registry.get_all(include_auto=False)
        cv.load_cleaners(cleaners)

    def _load_deep_cleaners(self, force: bool = False) -> None:
        view = self.views.get("deep")
        if view is None or not hasattr(view, "load_cleaners"):
            return
        if not force and getattr(view, "_cleaners", None):
            return
        # Auto-discovered кэши тоже попадают на экран глубокой очистки
        # (5C-3): те же ограничения плана и подтверждения.
        view.load_cleaners(self.registry.get_all(include_auto=True))

    def _quick_clean(self) -> None:
        self._switch_view("clean")
        self._load_cleaners()
        self.statusbar.log("Запуск быстрой очистки…")
        cv = self.views["clean"]
        if hasattr(cv, "start_scan"):
            cv.start_scan()

    def _go_deep_from_dashboard(self) -> None:
        """Баннер порога: только предложение, выбор и подтверждение — за Вами."""
        self._switch_view("deep")
        self._load_deep_cleaners()
        view = self.views.get("deep")
        self.statusbar.log(
            "Места мало: предложен безопасный набор глубокой очистки."
        )
        if view is not None and hasattr(view, "select_safe_set"):
            view.select_safe_set()

    def _on_scan(self) -> None:
        if self.views.get("clean") and hasattr(self.views["clean"], "start_scan"):
            self._load_cleaners()
            self.views["clean"].start_scan()

    def _on_clean(self) -> None:
        if self.views.get("clean") and hasattr(self.views["clean"], "start_clean"):
            self.views["clean"].start_clean()

    def _select_all(self) -> None:
        if self.views.get("clean") and hasattr(self.views["clean"], "select_all"):
            self.views["clean"].select_all()

    def _clear_history(self) -> None:
        try:
            self.history.clear()
            self.statusbar.log("История очисток удалена")
        except Exception as e:
            self.statusbar.log(f"Не удалось очистить историю: {e}")
        self._update_disk_info()
        self._refresh_dashboard()

    # ─────────────────────────────────────
    # ПРАВИЛА, ОТЧЁТЫ И КОНФИГ
    # ─────────────────────────────────────

    def _reload_after_rules_change(self) -> None:
        self.registry = CleanerRegistry(self.config)
        self._load_cleaners(force=True)
        self._load_deep_cleaners(force=True)

    def _add_rule(self, name: str, path: str, safety: str) -> str:
        rule_id = self.config.add_custom_rule(name, path, safety)
        self.statusbar.log(f"Правило добавлено: {name}")
        self._reload_after_rules_change()
        return rule_id

    def _update_rule(self, rule_id: str, name: str, path: str, safety: str) -> None:
        self.config.update_custom_rule(rule_id, name, path, safety)
        self.statusbar.log(f"Правило изменено: {name}")
        self._reload_after_rules_change()

    def _remove_rule(self, rule_id: str) -> None:
        self.config.remove_custom_rule(rule_id)
        self.statusbar.log("Правило удалено")
        self._reload_after_rules_change()

    def _export_config(self, path) -> Path:
        target = self.config.export_config(path)
        self.statusbar.log(f"Настройки экспортированы: {target}")
        return target

    def _import_config(self, path) -> dict:
        stats = self.config.import_config(path)
        self.statusbar.log(
            f"Импорт: настроек {stats.get('config', 0)}, "
            f"правил {stats.get('rules', 0)}"
        )
        self._reload_after_rules_change()
        return stats

    def _export_report(
        self,
        kind: str,
        path,
        entries: list[dict] | None = None,
    ) -> Path:
        if entries is None:
            target = export_csv(self.history, path) if kind == "csv" \
                else export_json(self.history, path)
        else:
            target = export_entries_csv(entries, path) if kind == "csv" \
                else export_entries_json(entries, path)
        self.statusbar.log(f"Отчёт сохранён: {target}")
        return target


def main() -> None:
    MainWindow().run()
