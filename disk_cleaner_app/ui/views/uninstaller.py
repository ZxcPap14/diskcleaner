"""🗑️ App Uninstaller — удаление программ с deep scan (Revo-style)."""
from __future__ import annotations

import threading
from tkinter import messagebox, ttk

import customtkinter as ctk

from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.uninstaller import AppUninstaller
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
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
    MDLabel,
    MDSegmented,
    MDTextbox,
    PageHeader,
    SectionTitle,
    style_treeview,
)
from disk_cleaner_app.ui.dispatch import UiDispatcher
from disk_cleaner_app.ui.theme import ThemeManager


class UninstallerView(ctk.CTkFrame):
    """Удаление программ с глубоким сканированием остатков."""

    SCAN_LEVELS = ["Safe", "Moderate", "Advanced"]

    def __init__(self, parent, theme: ThemeManager, on_log, statusbar=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._on_log = on_log
        self._statusbar = statusbar
        self._uninstaller = AppUninstaller()
        self._apps: list[dict] = []
        self._scan_level = "Safe"
        self._is_uninstalling = False
        self._ui = UiDispatcher(self)
        self._ui.start()
        self.configure(fg_color="transparent")
        self._build()

    # ── построение ───────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Удаление программ",
            "Штатный деинсталлятор и поиск оставшихся файлов",
            icon="⊖",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        MDButton(
            header.actions, self._theme, "Обновить", self._load_apps,
            kind="text_muted", width=94, height=34,
        ).pack(side="right")

        # ── Панель управления ─────────────────────────
        controls = MDCard(self, self._theme, tone="low")
        controls.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        search_row = ctk.CTkFrame(controls, fg_color="transparent")
        search_row.pack(fill="x", padx=14, pady=(12, 6))

        MDLabel(
            search_row, self._theme, "⌕", role="secondary", font=("Segoe UI", 15),
        ).pack(side="left", padx=(0, 6))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._filter_apps())
        MDEntry(
            search_row, self._theme, textvariable=self.search_var,
            placeholder_text="Поиск установленной программы…",
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.info_label = MDLabel(
            search_row, self._theme, "", role="muted", font=FONT_LABEL,
        )
        self.info_label.pack(side="right", padx=(6, 0))

        options = ctk.CTkFrame(controls, fg_color="transparent")
        options.pack(fill="x", padx=14, pady=(0, 12))

        MDLabel(
            options, self._theme, "Глубина поиска остатков", role="secondary",
            font=FONT_LABEL,
        ).pack(side="left", padx=(2, 8))

        self.level_var = ctk.StringVar(value="Safe")
        self.level_seg = MDSegmented(
            options, self._theme, values=self.SCAN_LEVELS,
            variable=self.level_var,
            command=lambda v: setattr(self, "_scan_level", v),
            width=280, height=34,
        )
        self.level_seg.pack(side="left")

        MDLabel(
            options, self._theme, "Сортировка", role="secondary", font=FONT_LABEL,
        ).pack(side="left", padx=(18, 8))
        self.sort_var = ctk.StringVar(value="По имени")
        self._sort_mode = "name"
        ctk.CTkOptionMenu(
            options,
            values=["По имени", "По размеру", "По дате установки"],
            variable=self.sort_var, width=160, height=34,
            command=self._set_sort,
        ).pack(side="left")

        self.leftovers_btn = MDButton(
            options, self._theme, "Найти остатки", self._scan_leftovers,
            kind="outlined", width=128, height=34,
        )
        self.leftovers_btn.pack(side="right", padx=(6, 0))

        self.uninstall_btn = MDButton(
            options, self._theme, "Удалить программу", self._uninstall_selected,
            kind="danger", width=152, height=34,
        )
        self.uninstall_btn.pack(side="right")

        # ── Список и журнал ───────────────────────────
        panes = ctk.CTkFrame(self, fg_color="transparent")
        panes.grid(row=2, column=0, sticky="nsew")
        panes.grid_columnconfigure(0, weight=3)
        panes.grid_columnconfigure(1, weight=2)
        panes.grid_rowconfigure(0, weight=1)

        list_card = MDCard(panes, self._theme, tone="low")
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_2))

        list_top = ctk.CTkFrame(list_card, fg_color="transparent")
        list_top.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            list_top, self._theme, "Установленные программы",
            "Двойной клик запускает деинсталлятор",
        ).pack(side="left")

        style_treeview("Uninstall", self._theme, row_height=32)
        self.tree = ttk.Treeview(
            list_card, columns=("name", "version", "size", "date"),
            show="headings", selectmode="browse", height=14,
            style="Uninstall.Treeview",
        )
        self.tree.heading("name", text="Программа", anchor="w")
        self.tree.heading("version", text="Версия", anchor="w")
        self.tree.heading("size", text="Размер", anchor="e")
        self.tree.heading("date", text="Установлена", anchor="e")
        self.tree.column("name", width=240, minwidth=150)
        self.tree.column("version", width=90, minwidth=70, stretch=False)
        self.tree.column("size", width=92, minwidth=70, anchor="e", stretch=False)
        self.tree.column("date", width=110, minwidth=90, anchor="e", stretch=False)

        self._list_scroll = ctk.CTkScrollbar(
            list_card, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.tree.configure(yscrollcommand=self._list_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(14, 2), pady=(0, 12))
        self._list_scroll.pack(side="right", fill="y", padx=(0, 10), pady=(0, 12))
        self.tree.bind("<Double-1>", lambda e: self._uninstall_selected())

        log_card = MDCard(panes, self._theme, tone="low")
        log_card.grid(row=0, column=1, sticky="nsew")

        log_top = ctk.CTkFrame(log_card, fg_color="transparent")
        log_top.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            log_top, self._theme, "Журнал удаления",
            "Результаты деинсталляции и поиска остатков",
        ).pack(side="left")

        self.log_text = MDTextbox(
            log_card, self._theme, font=FONT_MONO_SMALL, wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.log_text.configure(state="disabled")

        self._load_apps()

    # ── данные ───────────────────────────────────────────

    def _load_apps(self) -> None:
        self.info_label.configure(text="Загрузка…")

        def worker():
            apps = self._uninstaller.get_installed()
            self._ui.post(self._display, apps)

        threading.Thread(target=worker, daemon=True).start()

    def _display(self, apps: list[dict]) -> None:
        self._apps = apps
        self._filter_apps()

    def _set_sort(self, label: str) -> None:
        modes = {
            "По имени": "name",
            "По размеру": "size",
            "По дате установки": "date",
        }
        self._sort_mode = modes.get(label, "name")
        self._filter_apps()

    @staticmethod
    def _install_date_label(app: dict) -> str:
        # InstallDate в реестре хранится как ГГГГММДД.
        raw = str(app.get("install_date", ""))
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        return "—"

    def _visible_apps(self) -> list[dict]:
        """Отфильтрованный и отсортированный список — порядок строк таблицы."""
        query = self.search_var.get().lower()
        apps = [a for a in self._apps
                if not query or query in str(a.get("name", "")).lower()]
        if self._sort_mode == "size":
            apps.sort(key=lambda a: int(a.get("size_kb", 0) or 0), reverse=True)
        elif self._sort_mode == "date":
            apps.sort(key=lambda a: str(a.get("install_date", "")), reverse=True)
        return apps

    def _filter_apps(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)

        apps = self._visible_apps()

        shown = 0
        for app in apps:
            sz = app.get("size_kb", 0)
            sz_str = format_bytes(sz * 1024) if sz > 0 else "—"
            self.tree.insert("", "end", values=(
                app.get("name", ""),
                app.get("version", ""),
                sz_str,
                self._install_date_label(app),
            ))
            shown += 1

        self.info_label.configure(text=f"Показано: {shown} из {len(self._apps)}")

    def _uninstall_selected(self) -> None:
        if self._is_uninstalling:
            return
        app = self._selected_app()
        if app is None:
            return
        name = app.get("name", "?")

        if not messagebox.askyesno(
            "Удаление",
            f"Удалить '{name}'?\n\n"
            "Будет запущен штатный деинсталлятор программы.\n"
            "Остатки автоматически не удаляются — их можно найти отдельно.",
        ):
            return

        self._is_uninstalling = True
        self.uninstall_btn.configure(state="disabled")
        self.leftovers_btn.configure(state="disabled")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", f"Удаление: {name}\n\n")
        self.log_text.configure(state="disabled")

        def worker():
            logs = self._uninstaller.uninstall(app)
            self._ui.post(self._show_log, logs)
            self._ui.post(self._on_log, f"{name}: деинсталлятор запущен")
            self._ui.post(self._finish_uninstall)
            # Обновить список после завершения деинсталлятора
            self._ui.post_after(2000, self._load_apps)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_uninstall(self) -> None:
        self._is_uninstalling = False
        self.uninstall_btn.configure(state="normal")
        self.leftovers_btn.configure(state="normal")

    def _selected_app(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        visible = self._visible_apps()
        idx = self.tree.index(sel[0])
        if idx >= len(visible):
            return None
        return visible[idx]

    def _scan_leftovers(self) -> None:
        if self._is_uninstalling:
            return
        app = self._selected_app()
        if app is None:
            messagebox.showinfo("Остатки", "Сначала выберите программу в списке.")
            return

        name = app.get("name", "?")
        level = self._scan_level.lower()
        self._is_uninstalling = True
        self.leftovers_btn.configure(state="disabled")
        self.uninstall_btn.configure(state="disabled")
        self._show_log([f"Поиск остатков ({level}): {name}"])

        def worker():
            try:
                leftovers = self._uninstaller.find_leftovers(app, level)
            except Exception as e:
                self._ui.post(self._show_log, [f"Ошибка поиска: {e}"])
                self._ui.post(self._finish_uninstall)
                return
            self._ui.post(self._offer_leftovers, name, leftovers)

        threading.Thread(target=worker, daemon=True).start()

    def _offer_leftovers(self, name: str, leftovers: list[dict]) -> None:
        self._finish_uninstall()
        if not leftovers:
            self._show_log(["  Подозрительных остатков не найдено."])
            return

        total = sum(int(item.get("size", 0)) for item in leftovers)
        self._show_log([
            f"  Найдено: {len(leftovers)} · {format_bytes(total)}",
            "  Отметьте объекты в окне предпросмотра.",
        ])

        win = ctk.CTkToplevel(self)
        win.title(f"Остатки: {name}")
        win.geometry("900x560")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.configure(fg_color=self._theme.colors.SURFACE)

        MDLabel(
            win, self._theme, f"Найдено объектов: {len(leftovers)}",
            role="on_surface", font=FONT_HEADLINE, anchor="w",
        ).pack(fill="x", padx=20, pady=(18, 2))
        MDLabel(
            win, self._theme,
            f"Общий объём: {format_bytes(total)}. По умолчанию ничего не выбрано — "
            "отметьте только те объекты, которые действительно принадлежат "
            "удалённой программе.",
            role="secondary", font=FONT_BODY, anchor="w", justify="left",
            wraplength=850,
        ).pack(fill="x", padx=20, pady=(0, 10))

        table_card = MDCard(win, self._theme, tone="low")
        table_card.pack(fill="both", expand=True, padx=20)

        style_treeview("Leftovers", self._theme, row_height=30)
        cols = ("check", "label", "path", "size")
        tree = ttk.Treeview(
            table_card, columns=cols, show="headings",
            selectmode="none", height=14, style="Leftovers.Treeview",
        )
        tree.heading("check", text="")
        tree.heading("label", text="Тип", anchor="w")
        tree.heading("path", text="Путь", anchor="w")
        tree.heading("size", text="Размер", anchor="e")
        tree.column("check", width=38, anchor="center", stretch=False)
        tree.column("label", width=150, anchor="w", stretch=False)
        tree.column("path", width=540)
        tree.column("size", width=100, anchor="e", stretch=False)

        checked: dict[int, bool] = {i: False for i in range(len(leftovers))}
        for i, item in enumerate(leftovers):
            size = format_bytes(item["size"]) if item.get("size") else "—"
            tree.insert("", "end", iid=str(i), values=(
                "☐", item.get("label", "?"), item.get("path", "?"), size,
            ))

        scroll = ctk.CTkScrollbar(
            table_card, command=tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True, padx=(12, 2), pady=12)
        scroll.pack(side="right", fill="y", padx=(0, 10), pady=12)

        footer = ctk.CTkFrame(win, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=14)

        count_label = MDLabel(
            footer, self._theme, "Выбрано: 0", role="secondary", font=FONT_LABEL,
        )

        def refresh_marks() -> None:
            for i in range(len(leftovers)):
                try:
                    vals = list(tree.item(str(i), "values"))
                except Exception:
                    continue
                vals[0] = "☑" if checked[i] else "☐"
                tree.item(str(i), values=vals)
            selected = [leftovers[i] for i, on in checked.items() if on]
            size = sum(int(item.get("size", 0)) for item in selected)
            count_label.configure(
                text=f"Выбрано: {len(selected)} · {format_bytes(size)}"
            )
            delete_btn.configure(state="normal" if selected else "disabled")

        def toggle(event) -> None:
            iid = tree.identify_row(event.y)
            if not iid:
                return
            idx = int(iid)
            checked[idx] = not checked[idx]
            refresh_marks()

        tree.bind("<ButtonRelease-1>", toggle)

        def set_all(value: bool) -> None:
            for i in checked:
                checked[i] = value
            refresh_marks()

        def confirm_delete() -> None:
            selected = [leftovers[i] for i, on in checked.items() if on]
            if not selected:
                return
            size = sum(int(item.get("size", 0)) for item in selected)
            if not messagebox.askyesno(
                "Удаление остатков",
                f"Удалить безвозвратно {len(selected)} объектов "
                f"({format_bytes(size)}), минуя корзину?",
            ):
                return
            win.grab_release()
            win.destroy()
            self._start_leftovers_removal(name, selected)

        MDButton(
            footer, self._theme, "Выбрать все", lambda: set_all(True),
            kind="text_muted", width=112, height=32,
        ).pack(side="left")
        MDButton(
            footer, self._theme, "Снять все", lambda: set_all(False),
            kind="text_muted", width=100, height=32,
        ).pack(side="left", padx=(4, 0))
        count_label.pack(side="left", padx=(10, 0))

        delete_btn = MDButton(
            footer, self._theme, "Удалить выбранные", confirm_delete,
            kind="danger", width=172, height=32, state="disabled",
        )
        delete_btn.pack(side="right")
        MDButton(
            footer, self._theme, "Отмена",
            lambda: (win.grab_release(), win.destroy()),
            kind="text_muted", width=90, height=32,
        ).pack(side="right", padx=(0, 6))

        refresh_marks()

    def _start_leftovers_removal(self, name: str, selected: list[dict]) -> None:
        """Удалить выбранные остатки в фоновом потоке."""
        self._is_uninstalling = True
        self.leftovers_btn.configure(state="disabled")
        self.uninstall_btn.configure(state="disabled")
        self._show_log([f"  Удаление выбранных остатков: {len(selected)}"])

        def worker():
            logs = self._uninstaller.remove_leftovers(selected)
            self._ui.post(self._show_log, logs)
            self._ui.post(
                self._on_log,
                f"Остатки {name}: обработано {len(selected)}",
            )
            self._ui.post(self._load_apps)
            self._ui.post(self._finish_uninstall)

        threading.Thread(target=worker, daemon=True).start()

    def _show_log(self, logs: list[str]) -> None:
        self.log_text.configure(state="normal")
        for line in logs:
            self.log_text.insert("end", line + "\n")
        self.log_text.configure(state="disabled")

    def refresh_theme(self) -> None:
        c = self._theme.colors
        style_treeview("Uninstall", self._theme, row_height=32)
        self._list_scroll.configure(
            button_color=c.OUTLINE_VARIANT, button_hover_color=c.OUTLINE,
        )

    def destroy(self) -> None:
        try:
            self._ui.stop()
        except Exception:
            pass
        super().destroy()
