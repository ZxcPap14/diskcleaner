"""⚙️ Settings — настройки, правила, отчёты и резервные копии."""
from __future__ import annotations

import datetime
import os
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from disk_cleaner_app.models.config import CONFIG_DIR
from disk_cleaner_app.models.item import SafetyLevel, format_bytes
from disk_cleaner_app.services.logging_setup import LOG_FILE
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_HEADLINE,
    FONT_LABEL,
    FONT_MONO_SMALL,
    SPACE_2,
    SPACE_3,
)
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDEntry,
    MDIconButton,
    MDLabel,
    MDOptionMenu,
    MDScrollArea,
    MDSwitch,
    MDTextbox,
    PageHeader,
    SectionTitle,
    style_treeview,
)
from disk_cleaner_app.ui.theme import ThemeManager

SAFETY_CHOICES = (
    SafetyLevel.SAFE,
    SafetyLevel.CAUTION,
    SafetyLevel.ADVANCED,
)

SAFETY_LABELS = {
    SafetyLevel.SAFE: "Безопасно",
    SafetyLevel.CAUTION: "Осторожно",
    SafetyLevel.ADVANCED: "Продвинутый",
}


def _fallback_getter(key: str, default=None):
    return default


class SettingsView(MDScrollArea):
    """Страница настроек (прокручиваемая)."""

    def __init__(self, parent, theme: ThemeManager,
                 config_saver: Callable[[str, object], None],
                 history_getter, rules_getter, total_freed_getter,
                 config_getter: Callable[[str, object], object] | None = None,
                 on_clear_history=None,
                 on_add_rule: Callable[[str, str, str], str] | None = None,
                 on_update_rule: Callable[[str, str, str, str], None] | None = None,
                 on_remove_rule: Callable[[str], None] | None = None,
                 config_exporter: Callable[[Path], Path] | None = None,
                 config_importer: Callable[[Path], dict] | None = None,
                 report_exporter: Callable[[str, Path], Path] | None = None,
                 on_autostart_change: Callable[[bool], str] | None = None,
                 on_check_updates: Callable[[str], None] | None = None,
                 **kwargs):
        super().__init__(parent, theme, **kwargs)
        self._theme = theme
        self._config_saver = config_saver
        self._history_getter = history_getter
        self._rules_getter = rules_getter
        self._total_freed_getter = total_freed_getter
        self._config_getter = config_getter or _fallback_getter
        self._on_clear_history = on_clear_history
        self._on_add_rule = on_add_rule
        self._on_update_rule = on_update_rule
        self._on_remove_rule = on_remove_rule
        self._config_exporter = config_exporter
        self._config_importer = config_importer
        self._report_exporter = report_exporter
        self._on_autostart_change = on_autostart_change
        self._on_check_updates = on_check_updates
        self._rules: list[dict] = []
        self._build()

    # ── построение ───────────────────────────────────────

    def _build(self) -> None:
        header = PageHeader(
            self, self._theme,
            "Настройки",
            "Тема, правила очистки, отчёты и резервные копии",
            icon="⚙",
        )
        header.pack(fill="x", pady=(0, SPACE_3))

        self._build_preferences()
        self._build_tray()
        self._build_history()
        self._build_reports()
        self._build_rules()
        self._build_whitelist()
        self._build_schedule()
        self._build_backup()
        self._build_updates()

    def _section(self, title: str, subtitle: str, icon: str = "") -> MDCard:
        card = MDCard(self, self._theme, tone="low")
        card.pack(fill="x", pady=(0, SPACE_2))
        SectionTitle(
            card, self._theme, title, subtitle, icon=icon,
        ).pack(fill="x", padx=18, pady=(14, 8))
        return card

    def _build_preferences(self) -> None:
        card = self._section(
            "Внешний вид и поведение",
            "Тема применяется сразу; остальные параметры — при следующей операции",
            icon="◐",
        )

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 10))

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        MDLabel(
            left, self._theme, "Тема оформления", role="on_surface",
            font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            left, self._theme, "Светлая, тёмная или как в системе",
            role="muted", font=FONT_CAPTION, anchor="w",
        ).pack(anchor="w")

        self.theme_var = ctk.StringVar(value=str(self._config_getter("theme", "dark")))
        MDOptionMenu(
            row, self._theme, values=["dark", "light", "system"],
            variable=self.theme_var, width=150,
            command=lambda v: self._config_saver("theme", v),
        ).pack(side="right")

        self._divider(card)

        self.recycle_var = ctk.BooleanVar(
            value=bool(self._config_getter("to_recycle", False))
        )
        recycle = ctk.CTkFrame(card, fg_color="transparent")
        recycle.pack(fill="x", padx=18, pady=(6, 4))
        text = ctk.CTkFrame(recycle, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        MDLabel(
            text, self._theme, "Перемещать удалённое в корзину", role="on_surface",
            font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            text, self._theme,
            "Корзина не освобождает место до её очистки. Кэши обычно удаляют "
            "безвозвратно.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=620,
        ).pack(anchor="w")
        MDSwitch(
            recycle, self._theme, text="", variable=self.recycle_var,
            command=lambda: self._config_saver(
                "to_recycle", str(self.recycle_var.get())
            ),
        ).pack(side="right", padx=(12, 0))

        self._divider(card)

        self.safe_var = ctk.BooleanVar(
            value=bool(self._config_getter("safe_mode", True))
        )
        safe = ctk.CTkFrame(card, fg_color="transparent")
        safe.pack(fill="x", padx=18, pady=(6, 14))
        safe_text = ctk.CTkFrame(safe, fg_color="transparent")
        safe_text.pack(side="left", fill="x", expand=True)
        MDLabel(
            safe_text, self._theme, "Безопасный режим", role="on_surface",
            font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            safe_text, self._theme,
            "Показывать и выбирать только безопасные цели.",
            role="muted", font=FONT_CAPTION, anchor="w",
        ).pack(anchor="w")
        MDSwitch(
            safe, self._theme, text="", variable=self.safe_var,
            command=lambda: self._config_saver(
                "safe_mode", str(self.safe_var.get())
            ),
        ).pack(side="right", padx=(12, 0))

        self._divider(card)

        self.restore_var = ctk.BooleanVar(
            value=bool(self._config_getter("restore_point", False))
        )
        restore = ctk.CTkFrame(card, fg_color="transparent")
        restore.pack(fill="x", padx=18, pady=(6, 14))
        restore_text = ctk.CTkFrame(restore, fg_color="transparent")
        restore_text.pack(side="left", fill="x", expand=True)
        MDLabel(
            restore_text, self._theme,
            "Точка восстановления перед глубокой очисткой и удалением программ",
            role="on_surface", font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            restore_text, self._theme,
            "Требует прав администратора и включённого восстановления системы. "
            "Windows создаёт точки не чаще раза в 24 часа.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=620,
        ).pack(anchor="w")
        MDSwitch(
            restore, self._theme, text="", variable=self.restore_var,
            command=lambda: self._config_saver(
                "restore_point", str(self.restore_var.get())
            ),
        ).pack(side="right", padx=(12, 0))

        self._divider(card)

        self.threshold_var = ctk.StringVar(
            value=str(self._config_getter("deep_threshold_gb", 10))
        )
        threshold_row = ctk.CTkFrame(card, fg_color="transparent")
        threshold_row.pack(fill="x", padx=18, pady=(6, 14))
        threshold_text = ctk.CTkFrame(threshold_row, fg_color="transparent")
        threshold_text.pack(side="left", fill="x", expand=True)
        MDLabel(
            threshold_text, self._theme,
            "Порог свободного места для предложения глубокой очистки",
            role="on_surface", font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            threshold_text, self._theme,
            "Если на диске меньше — на главной появится баннер с предложением. "
            "0 — выключить. Значение в ГБ, Enter для сохранения.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=620,
        ).pack(anchor="w")
        self.threshold_entry = MDEntry(
            threshold_row, self._theme,
            textvariable=self.threshold_var, width=80,
        )
        self.threshold_entry.pack(side="right", padx=(12, 0))
        try:
            self.threshold_entry.bind("<Return>", self._save_threshold)
            self.threshold_entry.bind("<FocusOut>", self._save_threshold)
        except AttributeError:
            pass

    def _build_tray(self) -> None:
        """Карточка «Трей и автозапуск» (4.19.0)."""
        card = self._section(
            "Трей и автозапуск",
            "Иконка в системном трее и старт вместе с Windows",
            icon="🔲",
        )

        from disk_cleaner_app.services.tray_icon import tray_available

        self.tray_var = ctk.BooleanVar(
            value=bool(self._config_getter("tray_enabled", False))
        )
        tray_row = ctk.CTkFrame(card, fg_color="transparent")
        tray_row.pack(fill="x", padx=18, pady=(6, 8))
        tray_text = ctk.CTkFrame(tray_row, fg_color="transparent")
        tray_text.pack(side="left", fill="x", expand=True)
        MDLabel(
            tray_text, self._theme,
            "Иконка в системном трее", role="on_surface",
            font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        caption = (
            "Крестик сворачивает приложение в трей, из меню иконки доступны "
            "тихая очистка и выход."
            if tray_available()
            else "Недоступно: установите пакет pystray (pip install pystray)."
        )
        MDLabel(
            tray_text, self._theme, caption,
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=620,
        ).pack(anchor="w")
        self.tray_switch = MDSwitch(
            tray_row, self._theme, text="", variable=self.tray_var,
            command=lambda: self._config_saver(
                "tray_enabled", str(self.tray_var.get())
            ),
        )
        self.tray_switch.pack(side="right", padx=(12, 0))
        if not tray_available():
            self.tray_switch.configure(state="disabled")

        self.minimized_var = ctk.BooleanVar(
            value=bool(self._config_getter("start_minimized", False))
        )
        min_row = ctk.CTkFrame(card, fg_color="transparent")
        min_row.pack(fill="x", padx=18, pady=(4, 8))
        min_text = ctk.CTkFrame(min_row, fg_color="transparent")
        min_text.pack(side="left", fill="x", expand=True)
        MDLabel(
            min_text, self._theme,
            "Запускаться свёрнутым в трей", role="on_surface",
            font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            min_text, self._theme,
            "Старт с --tray (в том числе по автозапуску) не показывает окно — "
            "только иконку в трее. Требуется включённая иконка трея.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=620,
        ).pack(anchor="w")
        MDSwitch(
            min_row, self._theme, text="", variable=self.minimized_var,
            command=lambda: self._config_saver(
                "start_minimized", str(self.minimized_var.get())
            ),
        ).pack(side="right", padx=(12, 0))

        self.autostart_var = ctk.BooleanVar(
            value=self._autostart_enabled()
        )
        auto_row = ctk.CTkFrame(card, fg_color="transparent")
        auto_row.pack(fill="x", padx=18, pady=(4, 14))
        auto_text = ctk.CTkFrame(auto_row, fg_color="transparent")
        auto_text.pack(side="left", fill="x", expand=True)
        MDLabel(
            auto_text, self._theme,
            "Автозапуск вместе с Windows", role="on_surface",
            font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            auto_text, self._theme,
            "Запись в HKCU\\…\\CurrentVersion\\Run: приложение стартует вместе "
            "с Windows, права администратора не нужны.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=620,
        ).pack(anchor="w")
        MDSwitch(
            auto_row, self._theme, text="", variable=self.autostart_var,
            command=self._apply_autostart,
        ).pack(side="right", padx=(12, 0))

    def _autostart_enabled(self) -> bool:
        try:
            from disk_cleaner_app.services.autostart_self import get_autostart

            return get_autostart() is not None
        except Exception:
            return False

    def _apply_autostart(self) -> None:
        enabled = bool(self.autostart_var.get())
        if self._on_autostart_change is not None:
            message = self._on_autostart_change(enabled)
        else:
            from disk_cleaner_app.services.autostart_self import set_autostart

            _ok, message = set_autostart(enabled)
        if message and not message.startswith("Автозапуск включён"):
            # Неудачу показываем явно; успех и так виден по положению тумблера.
            messagebox.showwarning("Автозапуск", message)

    def _build_updates(self) -> None:
        """Карточка «Обновления»: адрес манифеста и проверка (4.20.0)."""
        card = self._section(
            "Обновления",
            "Сравнение установленной версии с JSON-манифестом по вашему адресу",
            icon="⬆",
        )

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(6, 8))
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        MDLabel(
            text, self._theme, "Адрес манифеста", role="on_surface",
            font=FONT_BODY, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            text, self._theme,
            "JSON вида {\"version\": \"4.21.0\", \"url\": \"https://…\"}. "
            "Пустой адрес выключает проверку; сеть не используется без нажатия.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=620,
        ).pack(anchor="w")

        self.update_url_var = ctk.StringVar(
            value=str(self._config_getter("update_url", ""))
        )
        self.update_entry = MDEntry(
            row, self._theme, textvariable=self.update_url_var, width=300,
        )
        self.update_entry.pack(side="right", padx=(12, 0))
        for event in ("<Return>", "<FocusOut>"):
            try:
                self.update_entry.bind(event, lambda _e: self._save_update_url())
            except AttributeError:
                pass

        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.pack(fill="x", padx=18, pady=(0, 14))
        self.update_result = MDLabel(
            action_row, self._theme, "", role="muted",
            font=FONT_CAPTION, anchor="w", justify="left", wraplength=520,
        )
        self.update_result.pack(side="left", fill="x", expand=True)
        MDButton(
            action_row, self._theme, "Проверить обновления",
            command=self._run_update_check, kind="tonal", width=180,
        ).pack(side="right", padx=(12, 0))

    def _save_update_url(self) -> None:
        url = self.update_url_var.get().strip()
        self._config_saver("update_url", url)

    def _run_update_check(self) -> None:
        """Спросить сервер; сеть — в фоне, результат придёт в show_update_result."""
        self._save_update_url()
        url = self.update_url_var.get().strip()
        if not url:
            self.show_update_result({
                "status": "disabled",
                "message": "Задайте адрес манифеста — проверка выключена.",
            })
            return
        self.show_update_result(
            {"status": "checking", "message": "Проверяю обновления…"}
        )
        if self._on_check_updates is not None:
            self._on_check_updates(url)
            return
        from disk_cleaner_app import __version__
        from disk_cleaner_app.services.updater import check_for_updates

        self.show_update_result(check_for_updates(__version__, url))

    def show_update_result(self, result: dict) -> None:
        """Показать итог проверки; вызывается из UI-потока."""
        status = str(result.get("status", ""))
        role = {
            "available": "success",
            "up-to-date": "success",
            "error": "error",
            "checking": "muted",
        }.get(status, "muted")
        message = str(result.get("message", ""))
        url = result.get("url")
        if status == "available" and url:
            message = f"{message} Страница: {url}"
        self.update_result.configure(text=message)
        self.update_result.set_role(role)

    def _divider(self, parent) -> None:
        ctk.CTkFrame(
            parent, height=1, fg_color=self._theme.colors.OUTLINE_VARIANT,
        ).pack(fill="x", padx=18, pady=2)

    def _build_history(self) -> None:
        card = self._section(
            "История очисток",
            "Журнал операций и служебные файлы приложения",
            icon="≡",
        )

        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=18, pady=(0, 8))

        MDButton(
            tools, self._theme, "Папка данных", self._open_data_dir,
            kind="outlined", width=124, height=32,
        ).pack(side="left", padx=(0, 6))
        MDButton(
            tools, self._theme, "Открыть лог", self._open_log,
            kind="outlined", width=118, height=32,
        ).pack(side="left", padx=(0, 6))
        MDButton(
            tools, self._theme, "Очистить историю", self._clear_history,
            kind="danger_text", width=138, height=32,
        ).pack(side="right")

        self.hist_text = MDTextbox(
            card, self._theme, height=92, font=FONT_MONO_SMALL,
        )
        self.hist_text.pack(fill="x", padx=18, pady=(0, 14))

    def _build_reports(self) -> None:
        card = self._section(
            "Отчёты",
            "Экспорт журнала очисток для архива или анализа",
            icon="↑",
        )

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 6))

        MDButton(
            row, self._theme, "Экспорт JSON", lambda: self._export_report("json"),
            kind="tonal", width=132, height=32,
        ).pack(side="left", padx=(0, 6))
        MDButton(
            row, self._theme, "Экспорт CSV", lambda: self._export_report("csv"),
            kind="outlined", width=132, height=32,
        ).pack(side="left")

        MDLabel(
            card, self._theme,
            "Отчёт содержит цели, объём и дату очисток — без путей к файлам.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
        ).pack(fill="x", padx=18, pady=(2, 14))

    def _build_rules(self) -> None:
        card = self._section(
            "Пользовательские правила",
            "Свои папки и файлы, которые нужно добавлять в цели очистки",
            icon="✦",
        )

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(0, 8))

        MDButton(
            header, self._theme, "Добавить", self._add_rule,
            kind="filled", width=104, height=32,
        ).pack(side="left")
        MDButton(
            header, self._theme, "Изменить", self._edit_rule,
            kind="text", width=100, height=32,
        ).pack(side="left", padx=(4, 0))
        MDButton(
            header, self._theme, "Удалить", self._delete_rule,
            kind="danger_text", width=96, height=32,
        ).pack(side="left", padx=(4, 0))

        style_treeview("Rules", self._theme, row_height=30)
        table = ctk.CTkFrame(card, fg_color="transparent")
        table.pack(fill="x", padx=18, pady=(0, 8))

        self.rules_tree = ttk.Treeview(
            table, columns=("name", "safety", "path"), show="headings",
            selectmode="browse", height=5, style="Rules.Treeview",
        )
        self.rules_tree.heading("name", text="Название", anchor="w")
        self.rules_tree.heading("safety", text="Уровень", anchor="center")
        self.rules_tree.heading("path", text="Путь", anchor="w")
        self.rules_tree.column("name", width=220, minwidth=120)
        self.rules_tree.column(
            "safety", width=110, minwidth=96, anchor="center", stretch=False,
        )
        self.rules_tree.column("path", width=420, minwidth=200)

        self._rules_scroll = ctk.CTkScrollbar(
            table, command=self.rules_tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.rules_tree.configure(yscrollcommand=self._rules_scroll.set)
        self.rules_tree.pack(side="left", fill="x", expand=True)
        self._rules_scroll.pack(side="right", fill="y")
        self.rules_tree.bind("<Double-1>", lambda e: self._edit_rule())

        MDLabel(
            card, self._theme,
            "Путь правила не может быть системным каталогом или личной папкой "
            "целиком; удаление выполняется по правилам безопасности.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=720,
        ).pack(fill="x", padx=18, pady=(0, 14))

    def _build_whitelist(self) -> None:
        card = self._section(
            "Белый список путей",
            "Папки и файлы, которые никогда не попадут в план очистки",
            icon="🛡",
        )

        entry_row = ctk.CTkFrame(card, fg_color="transparent")
        entry_row.pack(fill="x", padx=18, pady=(0, 8))

        self.whitelist_var = ctk.StringVar()
        MDEntry(
            entry_row, self._theme, textvariable=self.whitelist_var,
            placeholder_text="Например: D:\\Projects\\важное",
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        MDButton(
            entry_row, self._theme, "Добавить", self._add_whitelist,
            kind="filled", width=104, height=32,
        ).pack(side="left")
        MDButton(
            entry_row, self._theme, "Удалить выбранное", self._remove_whitelist,
            kind="danger_text", width=150, height=32,
        ).pack(side="left", padx=(4, 0))

        style_treeview("Whitelist", self._theme, row_height=30)
        table = ctk.CTkFrame(card, fg_color="transparent")
        table.pack(fill="x", padx=18, pady=(0, 8))

        self.whitelist_tree = ttk.Treeview(
            table, columns=("path",), show="headings",
            selectmode="browse", height=4, style="Whitelist.Treeview",
        )
        self.whitelist_tree.heading("path", text="Путь", anchor="w")
        self.whitelist_tree.column("path", width=680, minwidth=300)

        scroll = ctk.CTkScrollbar(
            table, command=self.whitelist_tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.whitelist_tree.configure(yscrollcommand=scroll.set)
        self.whitelist_tree.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")

        MDLabel(
            card, self._theme,
            "Действует на глубокую очистку: путь и всё его содержимое "
            "исключаются из плана и помечаются в списке пропусков.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=720,
        ).pack(fill="x", padx=18, pady=(0, 14))
        self._refresh_whitelist()

    def _whitelist_entries(self) -> list[str]:
        raw = self._config_getter("whitelist", [])
        if isinstance(raw, list):
            return [str(w) for w in raw if str(w).strip()]
        return []

    def _refresh_whitelist(self) -> None:
        for iid in self.whitelist_tree.get_children():
            self.whitelist_tree.delete(iid)
        for path in self._whitelist_entries():
            self.whitelist_tree.insert("", "end", values=(path,))

    def _add_whitelist(self) -> None:
        path = self.whitelist_var.get().strip()
        if not path:
            return
        entries = self._whitelist_entries()
        if path not in entries:
            entries.append(path)
            self._config_saver("whitelist", entries)
        self.whitelist_var.set("")
        self._refresh_whitelist()

    def _remove_whitelist(self) -> None:
        sel = self.whitelist_tree.selection()
        if not sel:
            return
        path = self.whitelist_tree.item(sel[0], "values")[0]
        entries = [w for w in self._whitelist_entries() if w != path]
        self._config_saver("whitelist", entries)
        self._refresh_whitelist()

    def _build_schedule(self) -> None:
        card = self._section(
            "Расписание очистки",
            "Еженедельная тихая очистка безопасных целей по заданию Windows",
            icon="⏱",
        )

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 8))

        MDLabel(
            row, self._theme, "День", role="secondary", font=FONT_LABEL,
        ).pack(side="left", padx=(0, 4))
        self.sched_day_var = ctk.StringVar(value="ВС")
        ctk.CTkOptionMenu(
            row, values=["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"],
            variable=self.sched_day_var, width=76, height=32,
        ).pack(side="left")

        MDLabel(
            row, self._theme, "Время", role="secondary", font=FONT_LABEL,
        ).pack(side="left", padx=(10, 4))
        self.sched_time_var = ctk.StringVar(value="09:00")
        MDEntry(
            row, self._theme, textvariable=self.sched_time_var, width=80,
        ).pack(side="left")

        MDLabel(
            row, self._theme, "Режим", role="secondary", font=FONT_LABEL,
        ).pack(side="left", padx=(10, 4))
        self.sched_mode_var = ctk.StringVar(
            value=str(self._config_getter("schedule_mode", "smart"))
        )
        ctk.CTkOptionMenu(
            row,
            values=["smart", "deep-safe"],
            variable=self.sched_mode_var, width=120, height=32,
        ).pack(side="left")

        self.sched_install_btn = MDButton(
            row, self._theme, "Создать задание", self._install_schedule,
            kind="filled", width=140, height=32,
        )
        self.sched_install_btn.pack(side="left", padx=(12, 0))
        MDButton(
            row, self._theme, "Удалить задание", self._remove_schedule,
            kind="danger_text", width=140, height=32,
        ).pack(side="left", padx=(4, 0))

        self.sched_status = MDLabel(
            card, self._theme, "", role="muted", font=FONT_LABEL, anchor="w",
        )
        self.sched_status.pack(fill="x", padx=18, pady=(0, 14))
        self._refresh_schedule()

    _DAY_TO_SCHTASKS = {
        "ПН": "MON", "ВТ": "TUE", "СР": "WED", "ЧТ": "THU",
        "ПТ": "FRI", "СБ": "SAT", "ВС": "SUN",
    }

    def _refresh_schedule(self) -> None:
        from disk_cleaner_app.services.schedule import schedule_exists

        mode = str(self._config_getter("schedule_mode", "smart"))
        mode_text = "Smart Clean" if mode != "deep-safe" else "Deep: безопасный набор"
        if schedule_exists():
            self.sched_status.configure(
                text=f"✅ Задание активно: {mode_text}, раз в неделю."
            )
        else:
            self.sched_status.configure(text="Задание не создано.")

    def _save_threshold(self, *_args) -> None:
        raw = self.threshold_var.get().strip().replace(",", ".")
        try:
            value = max(0.0, float(raw))
        except ValueError:
            value = 10.0
        self.threshold_var.set(f"{value:g}")
        self._config_saver("deep_threshold_gb", str(value))

    def _install_schedule(self) -> None:
        from disk_cleaner_app.services.schedule import install_schedule

        at = self.sched_time_var.get().strip()
        day = self._DAY_TO_SCHTASKS.get(self.sched_day_var.get(), "SUN")
        mode = self.sched_mode_var.get().strip() or "smart"
        if mode not in ("smart", "deep-safe"):
            mode = "smart"
        self._config_saver("schedule_mode", mode)
        ok, message = install_schedule(day=day, at=at)
        if not ok:
            messagebox.showerror("Расписание очистки", message)
        self._refresh_schedule()

    def _remove_schedule(self) -> None:
        from disk_cleaner_app.services.schedule import uninstall_schedule

        ok, message = uninstall_schedule()
        if not ok:
            messagebox.showerror("Расписание очистки", message)
        self._refresh_schedule()

    def _build_backup(self) -> None:
        card = self._section(
            "Резервная копия настроек",
            "Перенос настроек и правил между компьютерами",
            icon="⤓",
        )

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 6))

        MDButton(
            row, self._theme, "Экспорт настроек", self._export_config,
            kind="tonal", width=156, height=32,
        ).pack(side="left", padx=(0, 6))
        MDButton(
            row, self._theme, "Импорт настроек", self._import_config,
            kind="outlined", width=156, height=32,
        ).pack(side="left")

        MDLabel(
            card, self._theme,
            "В файл попадают настройки и пользовательские правила. Импорт не "
            "удаляет существующие правила — только добавляет новые.",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=720,
        ).pack(fill="x", padx=18, pady=(2, 14))

    # ── обновление ───────────────────────────────────────

    def refresh(self) -> None:
        self.theme_var.set(str(self._config_getter("theme", self._theme.mode)))
        self.recycle_var.set(bool(self._config_getter("to_recycle", False)))
        self.safe_var.set(bool(self._config_getter("safe_mode", True)))
        self._refresh_history()
        self._refresh_rules()

    def _refresh_history(self) -> None:
        self.hist_text.configure(state="normal")
        self.hist_text.delete("1.0", "end")
        data = self._history_getter()
        if data:
            for row in data:
                if isinstance(row, tuple) and len(row) >= 3:
                    self.hist_text.insert(
                        "end",
                        f"  • {str(row[0])[:19]} — {row[1]} целей, "
                        f"{format_bytes(row[2])}\n",
                    )
            total = self._total_freed_getter()
            self.hist_text.insert("end", f"\n  Всего: {format_bytes(total)}\n")
        else:
            self.hist_text.insert("end", "  (пусто)\n")
        self.hist_text.configure(state="disabled")

    def _refresh_rules(self) -> None:
        for iid in self.rules_tree.get_children():
            self.rules_tree.delete(iid)
        self._rules = list(self._rules_getter() or [])
        for rule in self._rules:
            safety = rule.get("safety", SafetyLevel.CAUTION)
            self.rules_tree.insert(
                "", "end", iid=str(rule.get("id", "")),
                values=(
                    rule.get("name", "?"),
                    SAFETY_LABELS.get(safety, str(safety)),
                    rule.get("path", "?"),
                ),
            )

    def refresh_theme(self) -> None:
        c = self._theme.colors
        super().refresh_theme()
        style_treeview("Rules", self._theme, row_height=30)
        self._rules_scroll.configure(
            button_color=c.OUTLINE_VARIANT, button_hover_color=c.OUTLINE,
        )

    # ── данные и логи ────────────────────────────────────

    def _open_data_dir(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(CONFIG_DIR))
        except OSError as e:
            messagebox.showerror("Папка данных", f"Не удалось открыть папку: {e}")

    def _open_log(self) -> None:
        if not LOG_FILE.exists():
            messagebox.showinfo("Лог", "Файл лога ещё не создан.")
            return
        try:
            os.startfile(str(LOG_FILE))
        except OSError as e:
            messagebox.showerror("Лог", f"Не удалось открыть лог: {e}")

    def _clear_history(self) -> None:
        if self._on_clear_history is None:
            return
        if not messagebox.askyesno(
            "Очистка истории",
            "Удалить всю историю очисток? Это не удаляет файлы с диска.",
        ):
            return
        self._on_clear_history()
        self.refresh()

    # ── отчёты и резервные копии ─────────────────────────

    def _export_report(self, kind: str) -> None:
        if self._report_exporter is None:
            return
        suffix = ".json" if kind == "json" else ".csv"
        default = f"DiskCleaner-report-{datetime.date.today().isoformat()}{suffix}"
        path = filedialog.asksaveasfilename(
            parent=self, title="Экспорт отчёта", defaultextension=suffix,
            initialfile=default,
            filetypes=[("JSON", "*.json")] if kind == "json" else [("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            target = self._report_exporter(kind, Path(path))
        except OSError as e:
            messagebox.showerror("Экспорт отчёта", f"Не удалось сохранить: {e}")
            return
        messagebox.showinfo("Экспорт отчёта", f"Сохранено:\n{target}")

    def _export_config(self) -> None:
        if self._config_exporter is None:
            return
        default = f"DiskCleaner-config-{datetime.date.today().isoformat()}.json"
        path = filedialog.asksaveasfilename(
            parent=self, title="Экспорт настроек", defaultextension=".json",
            initialfile=default, filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            target = self._config_exporter(Path(path))
        except OSError as e:
            messagebox.showerror("Экспорт настроек", f"Не удалось сохранить: {e}")
            return
        messagebox.showinfo("Экспорт настроек", f"Сохранено:\n{target}")

    def _import_config(self) -> None:
        if self._config_importer is None:
            return
        path = filedialog.askopenfilename(
            parent=self, title="Импорт настроек",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Импорт настроек",
            "Импортировать настройки и правила из файла?\n"
            "Текущие правила останутся, новые добавятся.",
        ):
            return
        try:
            stats = self._config_importer(Path(path))
        except ValueError as e:
            messagebox.showerror("Импорт настроек", str(e))
            return
        except OSError as e:
            messagebox.showerror("Импорт настроек", f"Не удалось прочитать: {e}")
            return

        lines = [
            f"Настроек применено: {stats.get('config', 0)}",
            f"Правил добавлено: {stats.get('rules', 0)}",
        ]
        skipped = stats.get("skipped") or []
        if skipped:
            lines.append("")
            lines.append("Пропущено:")
            lines.extend(f"  • {item}" for item in skipped[:8])
            if len(skipped) > 8:
                lines.append(f"  … и ещё {len(skipped) - 8}")
        messagebox.showinfo("Импорт настроек", "\n".join(lines))
        self.refresh()

    # ── CRUD правил ──────────────────────────────────────

    def _selected_rule(self) -> dict | None:
        selection = self.rules_tree.selection()
        if not selection:
            return None
        rule_id = selection[0]
        return next((r for r in self._rules if str(r.get("id")) == rule_id), None)

    def _add_rule(self) -> None:
        if self._on_add_rule is None:
            return
        self._rule_dialog(None)

    def _edit_rule(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            messagebox.showinfo("Правило", "Выберите правило в таблице.")
            return
        self._rule_dialog(rule)

    def _delete_rule(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            messagebox.showinfo("Правило", "Выберите правило в таблице.")
            return
        if self._on_remove_rule is None:
            return
        if not messagebox.askyesno(
            "Удаление правила",
            f"Удалить правило «{rule.get('name', '?')}»?\n\n"
            "Файлы на диске не удаляются — правило просто исчезнет из списка целей.",
        ):
            return
        self._on_remove_rule(str(rule.get("id", "")))
        self.refresh()
        self._refresh_rules()

    def _rule_dialog(self, rule: dict | None) -> None:
        editing = rule is not None
        win = ctk.CTkToplevel(self)
        win.title("Изменить правило" if editing else "Новое правило")
        win.geometry("600x360")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.configure(fg_color=self._theme.colors.SURFACE)

        current: dict = rule if rule is not None else {}
        name_var = ctk.StringVar(value=str(current.get("name", "")) if editing else "")
        path_var = ctk.StringVar(value=str(current.get("path", "")) if editing else "")
        safety_var = ctk.StringVar(
            value=str(current.get("safety", SafetyLevel.CAUTION)) if editing
            else SafetyLevel.CAUTION
        )

        MDLabel(
            win, self._theme, "Изменить правило" if editing else "Новое правило",
            role="on_surface", font=FONT_HEADLINE, anchor="w",
        ).pack(fill="x", padx=22, pady=(20, 2))
        MDLabel(
            win, self._theme,
            "Путь будет проверен правилами безопасности перед добавлением.",
            role="secondary", font=FONT_BODY, anchor="w",
        ).pack(fill="x", padx=22, pady=(0, 12))

        MDLabel(
            win, self._theme, "Название", role="secondary", font=FONT_LABEL, anchor="w",
        ).pack(fill="x", padx=22)
        MDEntry(win, self._theme, textvariable=name_var).pack(
            fill="x", padx=22, pady=(2, 8),
        )

        MDLabel(
            win, self._theme, "Путь (папка или файл)", role="secondary",
            font=FONT_LABEL, anchor="w",
        ).pack(fill="x", padx=22)

        path_row = ctk.CTkFrame(win, fg_color="transparent")
        path_row.pack(fill="x", padx=22, pady=(2, 0))
        MDEntry(
            path_row, self._theme, textvariable=path_var,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        def browse_dir() -> None:
            chosen = filedialog.askdirectory(parent=win, title="Папка для правила")
            if chosen:
                path_var.set(chosen)

        def browse_file() -> None:
            chosen = filedialog.askopenfilename(parent=win, title="Файл для правила")
            if chosen:
                path_var.set(chosen)

        MDIconButton(
            path_row, self._theme, "⌕", browse_dir, kind="tonal", size=36,
            font=("Segoe UI", 14),
        ).pack(side="left", padx=(0, 4))
        MDIconButton(
            path_row, self._theme, "▤", browse_file, kind="tonal", size=36,
            font=("Segoe UI", 14),
        ).pack(side="left")

        safety_row = ctk.CTkFrame(win, fg_color="transparent")
        safety_row.pack(fill="x", padx=22, pady=(10, 0))
        MDLabel(
            safety_row, self._theme, "Уровень риска", role="secondary",
            font=FONT_LABEL,
        ).pack(side="left", padx=(0, 8))
        MDOptionMenu(
            safety_row, self._theme, values=list(SAFETY_CHOICES),
            variable=safety_var, width=150, height=34,
        ).pack(side="left")

        def submit() -> None:
            name = name_var.get()
            path_value = path_var.get()
            safety = safety_var.get()
            try:
                if editing:
                    if self._on_update_rule is None:
                        return
                    self._on_update_rule(
                        str(current.get("id", "")), name, path_value, safety
                    )
                else:
                    if self._on_add_rule is None:
                        return
                    self._on_add_rule(name, path_value, safety)
            except ValueError as e:
                messagebox.showwarning("Правило", str(e), parent=win)
                return
            win.grab_release()
            win.destroy()
            self.refresh()

        footer = ctk.CTkFrame(win, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=14)

        MDButton(
            footer, self._theme, "Сохранить", submit, kind="filled", width=132,
        ).pack(side="right")
        MDButton(
            footer, self._theme, "Отмена",
            lambda: (win.grab_release(), win.destroy()),
            kind="text_muted", width=90,
        ).pack(side="right", padx=(0, 6))
