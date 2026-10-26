"""🗑️ App Uninstaller — удаление программ с deep scan (Revo-style)."""
from __future__ import annotations

import threading
from tkinter import messagebox, ttk

import customtkinter as ctk

from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.large_files import reveal_in_explorer
from disk_cleaner_app.services.uninstaller import AppUninstaller
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
    FONT_HEADLINE,
    FONT_LABEL,
    FONT_MONO_SMALL,
    FONT_SMALL,
    SPACE_2,
    SPACE_3,
)
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDEntry,
    MDLabel,
    MDOptionMenu,
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
        self._rows: dict[str, dict] = {}
        self._measure_generation = 0
        self._measured_total = 0
        self._measure_total = 0
        self._queue_stop = threading.Event()
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
        MDOptionMenu(
            options, self._theme,
            values=["По имени", "По размеру", "По дате установки"],
            variable=self.sort_var, width=160, height=34,
            command=self._set_sort,
        ).pack(side="left")

        MDLabel(
            options, self._theme, "Диск", role="secondary", font=FONT_LABEL,
        ).pack(side="left", padx=(18, 8))
        self.disk_var = ctk.StringVar(value="Все диски")
        self.disk_menu = MDOptionMenu(
            options, self._theme,
            values=["Все диски"], variable=self.disk_var, width=118, height=34,
            command=lambda _v: self._filter_apps(),
        )
        self.disk_menu.pack(side="left")

        self.open_folder_btn = MDButton(
            options, self._theme, "Открыть папку", self._open_install_folder,
            kind="text_muted", width=118, height=34,
        )
        self.open_folder_btn.pack(side="right", padx=(6, 0))

        self.leftovers_btn = MDButton(
            options, self._theme, "Найти остатки", self._scan_leftovers,
            kind="outlined", width=128, height=34,
        )
        self.leftovers_btn.pack(side="right", padx=(6, 0))

        self.uninstall_btn = MDButton(
            options, self._theme, "Удалить выбранные", self._uninstall_selected,
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
            "Двойной клик — одна программа, Ctrl — несколько",
        ).pack(side="left")

        style_treeview("Uninstall", self._theme, row_height=32)
        self.tree = ttk.Treeview(
            list_card,
            columns=("name", "disk", "version", "size", "date"),
            show="headings", selectmode="extended", height=14,
            style="Uninstall.Treeview",
        )
        self.tree.heading("name", text="Программа", anchor="w")
        self.tree.heading("disk", text="Диск", anchor="center")
        self.tree.heading("version", text="Версия", anchor="w")
        self.tree.heading("size", text="Размер", anchor="e")
        self.tree.heading("date", text="Установлена", anchor="e")
        self.tree.column("name", width=225, minwidth=140)
        self.tree.column("disk", width=52, minwidth=44, anchor="center",
                         stretch=False)
        self.tree.column("version", width=88, minwidth=64, stretch=False)
        self.tree.column("size", width=92, minwidth=70, anchor="e", stretch=False)
        self.tree.column("date", width=106, minwidth=90, anchor="e", stretch=False)

        self._list_scroll = ctk.CTkScrollbar(
            list_card, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.tree.configure(yscrollcommand=self._list_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(14, 2), pady=(0, 12))
        self._list_scroll.pack(side="right", fill="y", padx=(0, 10), pady=(0, 12))
        self.tree.bind("<Double-1>", self._on_double_click)

        right = ctk.CTkFrame(panes, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        chart_card = MDCard(right, self._theme, tone="low")
        chart_card.grid(row=0, column=0, sticky="ew")

        SectionTitle(
            chart_card, self._theme, "Занято программами",
            "Топ по текущему фильтру; хвост суммируется в «Остальные»",
        ).pack(fill="x", padx=14, pady=(12, 4))

        self.chart = ctk.CTkCanvas(
            chart_card, height=190, bg=self._theme.colors.SURFACE_LOW,
            highlightthickness=0, bd=0,
        )
        self.chart.pack(fill="x", padx=14, pady=(0, 12))
        self.chart.bind("<Configure>", lambda e: self._draw_chart())

        log_card = MDCard(right, self._theme, tone="low")
        log_card.grid(row=1, column=0, sticky="nsew", pady=(SPACE_2, 0))

        log_top = ctk.CTkFrame(log_card, fg_color="transparent")
        log_top.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            log_top, self._theme, "Журнал удаления",
            "Результаты и остатки",
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
            try:
                uwp = self._uninstaller.get_uwp_apps()
            except Exception:
                uwp = []
            known = [
                str(a.get("install_location", ""))
                for a in (*apps, *uwp) if a.get("install_location")
            ]
            try:
                portable = self._uninstaller.get_portable(known_locations=known)
            except Exception:
                portable = []
            self._ui.post(self._display, [*apps, *uwp, *portable])

        threading.Thread(target=worker, daemon=True).start()

    def _display(self, apps: list[dict]) -> None:
        self._apps = apps
        self._measured_total = 0
        self._measure_total = 0
        for app in apps:
            app.pop("real_size", None)
        self._refresh_disk_menu()
        self._filter_apps()
        self._start_measurement()

    def _refresh_disk_menu(self) -> None:
        """Пересобрать список дисков из фактических программ."""
        drives = sorted({str(a.get("drive") or "") for a in self._apps} - {""})
        unknown = any(not a.get("drive") for a in self._apps)
        values = ["Все диски", *drives] + (["—"] if unknown else [])
        self.disk_menu.configure(values=values)
        if self.disk_var.get() not in values:
            self.disk_var.set("Все диски")

    @staticmethod
    def _size_key(app: dict) -> int:
        """Реальный размер, иначе оценка из реестра (EstimatedSize)."""
        real = app.get("real_size")
        if isinstance(real, int) and not isinstance(real, bool):
            return real
        return int(app.get("size_kb", 0) or 0) * 1024

    @staticmethod
    def _size_text(app: dict) -> str:
        if "real_size" in app:
            real = app["real_size"]
            if isinstance(real, int) and not isinstance(real, bool):
                return format_bytes(real)
            return "—"
        estimated = int(app.get("size_kb", 0) or 0)
        if estimated > 0:
            return "≈ " + format_bytes(estimated * 1024)
        if str(app.get("install_location", "") or "").strip():
            return "…"
        return "—"

    def _info_text(self, shown: int) -> str:
        text = f"Показано: {shown} из {len(self._apps)}"
        if self._measure_total:
            text += f" · размеры: {self._measured_total}/{self._measure_total}"
        return text

    def _start_measurement(self) -> None:
        """Посчитать реальные размеры установочных папок в фоне."""
        self._measure_generation += 1
        generation = self._measure_generation
        apps = [a for a in self._apps
                if str(a.get("install_location", "") or "").strip()]
        self._measure_total = len(apps)
        if not apps:
            self._filter_apps()
            return

        def worker() -> None:
            for app in apps:
                if generation != self._measure_generation:
                    return
                try:
                    size = self._uninstaller.install_size(app)
                except Exception:
                    size = None
                self._ui.post(self._apply_size, generation, app, size)
            self._ui.post(self._measurement_done, generation)

        threading.Thread(target=worker, daemon=True,
                         name="uninstaller-sizes").start()

    def _apply_size(self, generation: int, app: dict, size: int | None) -> None:
        if generation != self._measure_generation:
            return
        app["real_size"] = size
        self._measured_total += 1
        for iid, row_app in self._rows.items():
            if row_app is app:
                self.tree.set(iid, "size", self._size_text(app))
                break
        self.info_label.configure(text=self._info_text(len(self._rows)))

    def _measurement_done(self, generation: int) -> None:
        if generation != self._measure_generation:
            return
        selected = {str(app.get("name", "")) for app in self._selected_apps()}
        if self._sort_mode == "size":
            self._filter_apps()
            wanted = [iid for iid, app in self._rows.items()
                      if str(app.get("name", "")) in selected]
            if wanted:
                self.tree.selection_set(wanted)
        else:
            self.info_label.configure(text=self._info_text(len(self._rows)))
        self._draw_chart()

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
        disk = self.disk_var.get()
        if disk == "—":
            apps = [a for a in apps if not a.get("drive")]
        elif disk and disk != "Все диски":
            apps = [a for a in apps if a.get("drive") == disk]
        if self._sort_mode == "size":
            apps.sort(key=self._size_key, reverse=True)
        elif self._sort_mode == "date":
            apps.sort(key=lambda a: str(a.get("install_date", "")), reverse=True)
        else:
            apps.sort(key=lambda a: str(a.get("name", "")).lower())
        return apps

    @staticmethod
    def _row_values(app: dict) -> tuple[str, str, str, str, str]:
        name = str(app.get("name", ""))
        if app.get("portable"):
            name = f"📦 {name}"
        elif app.get("uwp"):
            name = f"🪟 {name}"
        return (
            name,
            str(app.get("drive") or "—"),
            str(app.get("version", "")),
            UninstallerView._size_text(app),
            UninstallerView._install_date_label(app),
        )

    def _filter_apps(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)

        apps = self._visible_apps()
        self._rows = {}

        shown = 0
        for idx, app in enumerate(apps):
            iid = str(idx)
            self._rows[iid] = app
            self.tree.insert("", "end", iid=iid, values=self._row_values(app))
            shown += 1

        self.info_label.configure(text=self._info_text(shown))
        self._draw_chart()

    # ── диаграмма размеров ───────────────────────────────

    @staticmethod
    def _chart_data(apps: list[dict], top: int = 10) -> list[tuple[str, int]]:
        """Топ программ по размеру; всё, что дальше, — одной строкой."""
        sized = [(str(a.get("name", "")), UninstallerView._size_key(a))
                 for a in apps]
        sized = [(name, size) for name, size in sized if size > 0]
        sized.sort(key=lambda pair: pair[1], reverse=True)
        if len(sized) <= top:
            return sized
        head = sized[:top]
        rest = sum(size for _name, size in sized[top:])
        if rest > 0:
            head.append((f"Остальные: {len(sized) - top}", rest))
        return head

    def _draw_chart(self) -> None:
        """Горизонтальные полосы: какая программа сколько занимает."""
        canvas = getattr(self, "chart", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 80 or height < 40:
            return

        c = self._theme.colors
        data = self._chart_data(self._visible_apps())
        if not data:
            canvas.create_text(
                width / 2, height / 2,
                text="Нет программ с известным размером",
                fill=c.ON_SURFACE_VARIANT, font=FONT_LABEL,
            )
            return

        label_w = min(190.0, width * 0.40)
        bar_max = max(10.0, width - label_w - 84)
        peak = data[0][1] or 1
        row_h = max(16.0, min(26.0, height / len(data)))

        for index, (name, size) in enumerate(data):
            cy = (index + 0.5) * row_h
            label = name if len(name) <= 26 else name[:25] + "…"
            fill = c.OUTLINE if name.startswith("Остальные") else c.PRIMARY
            bar_w = max(3.0, bar_max * size / peak)
            canvas.create_text(
                6, cy, anchor="w", text=label, fill=c.ON_SURFACE,
                font=FONT_SMALL,
            )
            canvas.create_rectangle(
                label_w, cy - 6, label_w + bar_w, cy + 6,
                fill=fill, outline="",
            )
            canvas.create_text(
                width - 6, cy, anchor="e", text=format_bytes(size),
                fill=c.ON_SURFACE_VARIANT, font=FONT_MONO_SMALL,
            )

    def _on_double_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self._uninstall_selected()

    @staticmethod
    def _uwp_note(apps: list[dict]) -> str:
        """Пометка о UWP-пакетах для окна подтверждения."""
        uwp = [a for a in apps if a.get("uwp")]
        if not uwp:
            return ""
        names = ", ".join(a.get("name", "?") for a in uwp[:3])
        more = f" и ещё {len(uwp) - 3}" if len(uwp) > 3 else ""
        return (
            f"\n\nUWP/Store ({names}{more}) удаляются через Remove-AppxPackage "
            "для текущего пользователя."
        )

    def _confirm_uninstall(self, apps: list[dict]) -> bool:
        name = apps[0].get("name", "?")
        if len(apps) == 1:
            return messagebox.askyesno(
                "Удаление",
                f"Удалить '{name}'?\n\n"
                "Будет запущен штатный деинсталлятор программы.\n"
                "Остатки автоматически не удаляются — их можно найти отдельно."
                + self._uwp_note(apps),
            )
        lines = "\n".join(f"• {a.get('name', '?')}" for a in apps[:8])
        tail = f"\n… и ещё {len(apps) - 8}." if len(apps) > 8 else ""
        return messagebox.askyesno(
            "Очередь удаления",
            f"Удалить {len(apps)} программ?\n\n{lines}{tail}\n\n"
            "Деинсталляторы запускаются по очереди. Каждый может показать "
            "свои диалоги; очередь продолжится после его завершения."
            + self._uwp_note(apps),
        )

    def _confirm_portable(self, apps: list[dict]) -> bool:
        lines = "\n".join(f"• {a.get('name', '?')}" for a in apps[:8])
        tail = f"\n… и ещё {len(apps) - 8}." if len(apps) > 8 else ""
        return messagebox.askyesno(
            "Перемещение в корзину",
            f"Переместить {len(apps)} портативных папок в корзину?\n\n"
            f"{lines}{tail}\n\n"
            "У портативных программ нет деинсталлятора — удаляется вся папка. "
            "Её можно восстановить из корзины.",
        )

    def _uninstall_selected(self) -> None:
        if self._is_uninstalling:
            return
        apps = self._selected_apps()
        if not apps:
            messagebox.showinfo("Удаление", "Сначала выберите программу в списке.")
            return

        portable = [a for a in apps if a.get("portable")]
        installed = [a for a in apps if not a.get("portable")]

        if installed and portable:
            if not messagebox.askyesno(
                "Удаление и корзина",
                f"Выбрано {len(installed)} программ и {len(portable)} "
                "портативных папок.\n\n"
                "Для программ запустятся штатные деинсталляторы, портативные "
                "папки будут перемещены в корзину целиком. Продолжить?",
            ):
                return
        elif portable:
            if not self._confirm_portable(portable):
                return
        elif not self._confirm_uninstall(installed):
            return

        self._queue_stop.clear()
        self._is_uninstalling = True
        self.uninstall_btn.configure(text="⏹ Остановить", command=self._stop_queue)
        self.leftovers_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        if len(apps) == 1:
            title = apps[0].get("name", "?")
        else:
            title = f"Выбрано: {len(installed)} программ, {len(portable)} папок"
        self.log_text.insert("1.0", f"{title}\n\n")
        self.log_text.configure(state="disabled")

        def worker():
            # Точка восстановления — по настройке «restore_point», только
            # для программ с деинсталлятором (портативные уходят в корзину,
            # это обратимо и без точки).
            try:
                enabled = bool(
                    ConfigManager().get("restore_point", False)
                )
            except Exception:
                enabled = False
            for line in self._uninstaller.restore_point_logs(
                installed,
                create_point=self._create_restore_point,
                enabled=enabled,
            ):
                self._ui.post(self._show_log, [line])
            if installed:
                self._uninstaller.uninstall_many(
                    installed,
                    on_log=lambda line: self._ui.post(self._show_log, [line]),
                    should_stop=self._queue_stop.is_set,
                )
            for app in portable:
                if self._queue_stop.is_set():
                    break
                self._ui.post(self._show_log, [f"▶ {app.get('name', '?')}"])
                for line in self._uninstaller.remove_portable(app):
                    self._ui.post(self._show_log, [line])
            self._ui.post(
                self._on_log,
                f"Удаление: {len(installed)} программ, {len(portable)} папок",
            )
            self._ui.post(self._finish_uninstall)
            # Обновить список после завершения очереди.
            self._ui.post_after(1500, self._load_apps)

        threading.Thread(target=worker, daemon=True,
                         name="uninstaller-queue").start()

    def _create_restore_point(self, description: str) -> tuple[bool, str]:
        """Обёртка для потока очереди: сервис требует прав администратора."""
        from disk_cleaner_app.services.restore_point import create_restore_point

        return create_restore_point(description)

    def _open_install_folder(self) -> None:
        app = self._selected_app()
        if app is None:
            messagebox.showinfo(
                "Папка программы", "Сначала выберите программу в списке."
            )
            return
        location = str(app.get("install_location", "") or "").strip().strip('"')
        if not location:
            messagebox.showinfo(
                "Папка программы",
                "Путь установки неизвестен — в реестре нет InstallLocation.",
            )
            return
        if not reveal_in_explorer(location):
            messagebox.showerror("Папка программы", f"Не удалось открыть:\n{location}")

    def _stop_queue(self) -> None:
        if not self._is_uninstalling:
            return
        self._queue_stop.set()
        self.uninstall_btn.configure(text="Останавливаю…", state="disabled")
        self._show_log(["⏹ Останавливаю после текущей программы…"])

    def _finish_uninstall(self) -> None:
        self._is_uninstalling = False
        self.uninstall_btn.configure(
            text="Удалить выбранные", command=self._uninstall_selected,
            state="normal",
        )
        self.leftovers_btn.configure(state="normal")
        self.open_folder_btn.configure(state="normal")

    def _selected_apps(self) -> list[dict]:
        return [self._rows[iid] for iid in self.tree.selection()
                if iid in self._rows]

    def _selected_app(self) -> dict | None:
        apps = self._selected_apps()
        return apps[0] if apps else None

    def _scan_leftovers(self) -> None:
        if self._is_uninstalling:
            return
        app = self._selected_app()
        if app is None:
            messagebox.showinfo("Остатки", "Сначала выберите программу в списке.")
            return
        if app.get("portable"):
            messagebox.showinfo(
                "Остатки",
                "У портативной программы остатки не ищутся — это одна папка.\n"
                "Убрать её в корзину можно кнопкой «Удалить выбранные».",
            )
            return
        if app.get("uwp"):
            messagebox.showinfo(
                "Остатки",
                "UWP-пакет управляется Windows: удаление выполняется целиком "
                "через Remove-AppxPackage, остатков после него не остаётся.",
            )
            return

        name = app.get("name", "?")
        level = self._scan_level.lower()
        self._is_uninstalling = True
        self.leftovers_btn.configure(state="disabled")
        self.uninstall_btn.configure(state="disabled")
        header = [f"Поиск остатков ({level}): {name}"]
        if len(self.tree.selection()) > 1:
            header.append("ℹ️  Остатки ищутся только для первой выбранной программы.")
        self._show_log(header)

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
        chart = getattr(self, "chart", None)
        if chart is not None:
            chart.configure(bg=c.SURFACE_LOW)
            self._draw_chart()

    def destroy(self) -> None:
        self._measure_generation += 1
        self._queue_stop.set()
        try:
            self._ui.stop()
        except Exception:
            pass
        super().destroy()
