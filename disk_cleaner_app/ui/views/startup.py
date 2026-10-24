"""🚀 Startup Manager — управление автозагрузкой."""
from __future__ import annotations

import threading
from tkinter import messagebox, ttk

import customtkinter as ctk

from disk_cleaner_app.services.startup import StartupManager
from disk_cleaner_app.services.startup_services import (
    ScheduledTasksManager,
    ServicesManager,
)
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
    FONT_HEADLINE,
    FONT_LABEL,
    SPACE_2,
    SPACE_3,
)
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDEntry,
    MDLabel,
    PageHeader,
    SectionTitle,
    style_treeview,
)
from disk_cleaner_app.ui.dispatch import UiDispatcher
from disk_cleaner_app.ui.theme import ThemeManager


class StartupView(ctk.CTkFrame):
    """Управление программами в автозагрузке."""

    def __init__(self, parent, theme: ThemeManager, on_log, **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._on_log = on_log
        self._manager = StartupManager()
        self._services = ServicesManager()
        self._tasks = ScheduledTasksManager()
        self._mode = "items"
        self._items: list[dict] = []
        self._items_by_id: dict[str, dict] = {}
        self._ui = UiDispatcher(self)
        self._ui.start()
        self.configure(fg_color="transparent")
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Автозагрузка",
            "Управление программами, которые запускаются вместе с Windows",
            icon="↗",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        MDButton(
            header.actions, self._theme, "Обновить", self.refresh,
            kind="text_muted", width=94, height=34,
        ).pack(side="right")

        controls = MDCard(self, self._theme, tone="low")
        controls.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(controls, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)

        self.disable_btn = MDButton(
            row, self._theme, "Отключить", self._disable_selected,
            kind="outlined", width=108, height=34,
        )
        self.disable_btn.pack(side="left", padx=(0, 6))

        self.enable_btn = MDButton(
            row, self._theme, "Включить", self._enable_selected,
            kind="tonal", width=100, height=34,
        )
        self.enable_btn.pack(side="left", padx=(0, 6))

        MDButton(
            row, self._theme, "Добавить", self._add_dialog,
            kind="filled", width=104, height=34,
        ).pack(side="left")

        self.mode_var = ctk.StringVar(value="Записи")
        self._mode_menu = ctk.CTkOptionMenu(
            row,
            values=["Записи", "Службы", "Задачи планировщика"],
            variable=self.mode_var, width=170, height=34,
            command=self._set_mode,
        )
        self._mode_menu.pack(side="left", padx=(14, 0))

        self.info_label = MDLabel(
            row, self._theme, "Загрузка…", role="secondary", font=FONT_LABEL,
        )
        self.info_label.pack(side="right")
        self.add_label = MDLabel(
            row, self._theme, "", role="muted", font=FONT_LABEL,
        )
        self.add_label.pack(side="right", padx=(0, 10))

        # ── Таблица ───────────────────────────────────
        table_card = MDCard(self, self._theme, tone="low")
        table_card.grid(row=2, column=0, sticky="nsew")

        title_row = ctk.CTkFrame(table_card, fg_color="transparent")
        title_row.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            title_row, self._theme, "Записи автозагрузки",
            "Отключение сохраняет запись и позволяет вернуть её позже",
        ).pack(side="left")

        style_treeview("Startup", self._theme, row_height=32)
        cols = ("name", "status", "command", "source")
        self.tree = ttk.Treeview(
            table_card, columns=cols, show="headings",
            selectmode="browse", height=12, style="Startup.Treeview",
        )
        self.tree.heading("name", text="Имя", anchor="w")
        self.tree.heading("status", text="Статус", anchor="center")
        self.tree.heading("command", text="Команда", anchor="w")
        self.tree.heading("source", text="Источник", anchor="w")
        self.tree.column("name", width=200, minwidth=150)
        self.tree.column("status", width=90, minwidth=76, anchor="center", stretch=False)
        self.tree.column("command", width=420, minwidth=220)
        self.tree.column("source", width=110, minwidth=90)

        self._table_scroll = ctk.CTkScrollbar(
            table_card, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.tree.configure(yscrollcommand=self._table_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(14, 2), pady=(0, 12))
        self._table_scroll.pack(side="right", fill="y", padx=(0, 10), pady=(0, 12))
        self._paint_tags()

        self.refresh()

    def _set_mode(self, label: str) -> None:
        self._mode = {"Записи": "items", "Службы": "services",
                      "Задачи планировщика": "tasks"}[label]
        self.add_label.configure(text="")
        self.refresh()

    def refresh(self) -> None:
        self.info_label.configure(text="Загрузка…")

        def worker():
            if self._mode == "services":
                items = self._services.get_all()
                if not items and self._services.last_error:
                    self._ui.post(
                        self.info_label.configure,
                        text=f"⚠️ {self._services.last_error}",
                    )
                    items = []
            elif self._mode == "tasks":
                items = self._tasks.get_all()
                if not items and self._tasks.last_error:
                    self._ui.post(
                        self.info_label.configure,
                        text=f"⚠️ {self._tasks.last_error}",
                    )
            else:
                items = self._manager.get_all()
            self._ui.post(self._display, items)

        threading.Thread(target=worker, daemon=True).start()

    def _display(self, items: list[dict]) -> None:
        self._items = items
        self._items_by_id = {str(item.get("id")): item for item in items}
        for i in self.tree.get_children():
            self.tree.delete(i)
        for item in items:
            item_id = str(item.get("id"))
            enabled = bool(item.get("enabled", False))
            if item.get("kind") == "service":
                status = "Включено" if enabled else "Отключено"
                status += f" · {item.get('state', '')} · {item.get('start_mode', '')}"
            elif item.get("kind") == "task":
                status = str(item.get("status_text", "") or
                             ("Включено" if enabled else "Отключено"))
            else:
                status = "Включено" if enabled else "Отключено"
            self.tree.insert("", "end", iid=item_id, values=(
                item.get("name", "?"),
                status,
                str(item.get("command", ""))[:80],
                item.get("source", "?"),
            ), tags=("enabled" if enabled else "disabled",))
        enabled_count = sum(1 for i in items if i.get("enabled"))
        disabled_count = len(items) - enabled_count
        if not (items == [] and self._mode != "items"):
            self.info_label.configure(
                text=f"Всего: {len(items)} · включено: {enabled_count} · "
                     f"отключено: {disabled_count}"
            )
        self.add_label.configure(text="")

    def _selected_item(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self._items_by_id.get(sel[0])

    def _manager_for(self, item: dict):
        kind = item.get("kind")
        if kind == "service":
            return self._services
        if kind == "task":
            return self._tasks
        return self._manager

    def _disable_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        name = item.get("name", "?")
        if not item.get("enabled", True):
            self._on_log(f"ℹ️  {name} уже отключена")
            return

        warning = ""
        if item.get("kind") == "service":
            warning = (
                "\n\n⚠️ Отключение системной службы может нарушить работу "
                "Windows. Исходный тип запуска сохраняется и восстановим."
            )
        if not messagebox.askyesno(
            "Отключение",
            f"Отключить '{name}'?\n\n"
            "Запись можно будет вернуть кнопкой «Включить»." + warning,
        ):
            return

        manager = self._manager_for(item)
        ok = manager.disable_item(item)
        if ok:
            self._on_log(f"🚫  Отключено: {name}")
            self.refresh()
        else:
            messagebox.showerror(
                "Ошибка",
                manager.last_error or f"Не удалось отключить {name}",
            )

    def _enable_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        name = item.get("name", "?")
        if item.get("enabled", False):
            self._on_log(f"ℹ️  {name} уже включена")
            return

        manager = self._manager_for(item)
        ok = manager.enable_item(item)
        if ok:
            self._on_log(f"✅  Включено: {name}")
            self.refresh()
        else:
            messagebox.showerror(
                "Ошибка",
                manager.last_error or f"Не удалось включить {name}",
            )

    def _add_dialog(self) -> None:
        w = ctk.CTkToplevel(self)
        w.title("Добавить в автозагрузку")
        w.geometry("520x330")
        w.attributes("-topmost", True)
        w.configure(fg_color=self._theme.colors.SURFACE)
        w.transient(self.winfo_toplevel())

        nv, cv = ctk.StringVar(), ctk.StringVar()

        MDLabel(
            w, self._theme, "Новая запись автозагрузки", role="on_surface",
            font=FONT_HEADLINE, anchor="w",
        ).pack(fill="x", padx=22, pady=(20, 2))
        MDLabel(
            w, self._theme,
            "Запись будет добавлена в автозагрузку текущего пользователя.",
            role="secondary", font=FONT_BODY, anchor="w",
        ).pack(fill="x", padx=22, pady=(0, 12))

        MDLabel(
            w, self._theme, "Название", role="secondary", font=FONT_LABEL, anchor="w",
        ).pack(fill="x", padx=22)
        MDEntry(w, self._theme, textvariable=nv).pack(fill="x", padx=22, pady=(2, 8))

        MDLabel(
            w, self._theme, "Команда или путь к программе", role="secondary",
            font=FONT_LABEL, anchor="w",
        ).pack(fill="x", padx=22)
        MDEntry(w, self._theme, textvariable=cv).pack(fill="x", padx=22, pady=(2, 2))

        error_label = MDLabel(
            w, self._theme, "", role="error", font=FONT_LABEL, anchor="w",
            wraplength=460,
        )
        error_label.pack(fill="x", padx=22, pady=(4, 0))

        def save():
            name, command = nv.get().strip(), cv.get().strip()
            if not name or not command:
                error_label.configure(text="Заполните название и команду.")
                return
            ok = self._manager.add_item(name, command)
            if ok:
                self._on_log(f"Добавлено в автозагрузку: {name}")
                self.refresh()
                w.destroy()
            else:
                error_label.configure(
                    text=self._manager.last_error or "Не удалось добавить запись"
                )

        footer = ctk.CTkFrame(w, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=14)
        MDButton(
            footer, self._theme, "Сохранить", save, kind="filled", width=132,
        ).pack(side="right")
        MDButton(
            footer, self._theme, "Отмена", w.destroy, kind="text_muted", width=90,
        ).pack(side="right", padx=(0, 6))

    def _paint_tags(self) -> None:
        c = self._theme.colors
        self.tree.tag_configure("enabled", foreground=c.SUCCESS)
        self.tree.tag_configure("disabled", foreground=c.TEXT_MUTED)

    def refresh_theme(self) -> None:
        c = self._theme.colors
        style_treeview("Startup", self._theme, row_height=32)
        self._paint_tags()
        self._table_scroll.configure(
            button_color=c.OUTLINE_VARIANT, button_hover_color=c.OUTLINE,
        )

    def destroy(self) -> None:
        try:
            self._ui.stop()
        except Exception:
            pass
        super().destroy()
