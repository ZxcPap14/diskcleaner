"""💽 Диски — SMART-показатели и проверка поверхности (только чтение)."""
from __future__ import annotations

import threading
from tkinter import messagebox, ttk
from typing import Literal

import customtkinter as ctk

from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.disk_health import (
    format_disk_row,
    format_hours,
    health_icon,
    list_disks,
)
from disk_cleaner_app.services.elevation import is_admin
from disk_cleaner_app.services.surface_scan import (
    format_duration,
    format_speed,
    read_surface,
)
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_LABEL,
    FONT_MONO_SMALL,
    SPACE_2,
    SPACE_3,
)
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDLabel,
    MDOptionMenu,
    MDProgress,
    MDSegmented,
    MDTextbox,
    PageHeader,
    SectionTitle,
    style_treeview,
)
from disk_cleaner_app.ui.dispatch import UiDispatcher
from disk_cleaner_app.ui.theme import ThemeManager

SCAN_SIZES = {
    "512 МБ": 512 * 1024 ** 2,
    "1 ГБ": 1024 ** 3,
    "4 ГБ": 4 * 1024 ** 3,
    "16 ГБ": 16 * 1024 ** 3,
    "Весь диск": None,
}


class DisksView(ctk.CTkFrame):
    """Список физических дисков, SMART и чтение поверхности."""

    def __init__(self, parent, theme: ThemeManager, on_log,
                 statusbar=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._on_log = on_log
        self._statusbar = statusbar
        self._disks: list[dict] = []
        self._by_index: dict[int, dict] = {}
        self._is_loading = False
        self._is_scanning = False
        self._scan_cancel = threading.Event()
        self._ui = UiDispatcher(self)
        self._ui.start()
        self.configure(fg_color="transparent")
        self._build()

    # ── UI ───────────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Диски и здоровье",
            "SMART-показатели и проверка поверхности без записи",
            icon="◉",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        self.refresh_btn = MDButton(
            header.actions, self._theme, "Обновить", self.refresh,
            kind="tonal", width=104, height=34,
        )
        self.refresh_btn.pack(side="right")

        self.tab_var = ctk.StringVar(value="Диски и SMART")
        self.tabs = MDSegmented(
            self, self._theme,
            values=["Диски и SMART", "Проверка поверхности"],
            variable=self.tab_var, command=self._switch_tab,
            width=360, height=38,
        )
        self.tabs.grid(row=1, column=0, sticky="w", pady=(0, SPACE_3))

        panes = ctk.CTkFrame(self, fg_color="transparent")
        panes.grid(row=2, column=0, sticky="nsew")
        panes.grid_rowconfigure(0, weight=1)
        panes.grid_columnconfigure(0, weight=1)

        smart_pane = ctk.CTkFrame(panes, fg_color="transparent")
        smart_pane.grid(row=0, column=0, sticky="nsew")
        self._smart_pane = smart_pane

        # ── Таблица дисков ────────────────────────────
        table_card = MDCard(smart_pane, self._theme, tone="low")
        table_card.pack(fill="x", pady=(0, SPACE_2))

        top = ctk.CTkFrame(table_card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            top, self._theme, "Физические диски",
            "Выберите строку, чтобы увидеть подробности",
        ).pack(side="left")

        style_treeview("Disks", self._theme, row_height=30)
        tree_wrap = ctk.CTkFrame(table_card, fg_color="transparent", height=118)
        tree_wrap.pack(fill="x", padx=(10, 6), pady=(0, 12))
        tree_wrap.pack_propagate(False)
        self.tree = ttk.Treeview(
            tree_wrap, columns=(
                "index", "model", "bus", "size", "health", "temp", "hours", "wear",
            ),
            show="headings", selectmode="browse", style="Disks.Treeview", height=3,
        )
        columns: list[tuple[str, str, int, Literal["center", "w", "e"]]] = [
            ("index", "№", 38, "center"),
            ("model", "Модель", 220, "w"),
            ("bus", "Шина", 78, "w"),
            ("size", "Объём", 92, "e"),
            ("health", "Здоровье", 100, "center"),
            ("temp", "Темп.", 62, "e"),
            ("hours", "Наработка", 94, "e"),
            ("wear", "Износ", 62, "e"),
        ]
        for column, title, width, anchor in columns:
            self.tree.heading(column, text=title, anchor=anchor)
            self.tree.column(
                column, width=width, anchor=anchor, stretch=column == "model",
            )

        self._table_scroll = ctk.CTkScrollbar(
            tree_wrap, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.tree.configure(yscrollcommand=self._table_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 2))
        self._table_scroll.pack(side="right", fill="y", padx=(0, 4))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._paint_tree_tags()

        self.empty_label = MDLabel(
            tree_wrap, self._theme, "", role="muted", font=FONT_BODY, anchor="center",
        )
        self.empty_label.place(relx=0.5, rely=0.6, anchor="center")

        # ── Подробности ───────────────────────────────
        details_card = MDCard(smart_pane, self._theme, tone="low")
        details_card.pack(fill="both", expand=True)

        details_top = ctk.CTkFrame(details_card, fg_color="transparent")
        details_top.pack(fill="x", padx=14, pady=(12, 4))
        SectionTitle(
            details_top, self._theme, "Состояние выбранного диска",
            "Данные SMART; часть полей доступна только с правами администратора",
        ).pack(side="left")

        self.details = MDTextbox(
            details_card, self._theme, height=96, font=FONT_MONO_SMALL,
        )
        self.details.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self._set_details("Нажмите «Обновить», чтобы прочитать SMART-данные.")

        # ── Проверка поверхности ──────────────────────
        scan_pane = ctk.CTkFrame(panes, fg_color="transparent")
        scan_pane.grid(row=0, column=0, sticky="nsew")
        self._scan_pane = scan_pane

        scan_card = MDCard(scan_pane, self._theme, tone="low")
        scan_card.pack(fill="both", expand=True)

        head = ctk.CTkFrame(scan_card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 4))
        SectionTitle(
            head, self._theme, "Проверка поверхности",
            "Аналог Victoria read test: последовательное чтение без записи. "
            "Диск не изменяется.",
        ).pack(side="left")

        controls = ctk.CTkFrame(scan_card, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=(2, 6))

        MDLabel(
            controls, self._theme, "Диск", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(0, 4))
        self.disk_var = ctk.StringVar(value="—")
        self.disk_menu = MDOptionMenu(
            controls, self._theme, values=["—"], variable=self.disk_var,
            command=self._on_disk_pick, width=230, height=34,
        )
        self.disk_menu.pack(side="left", padx=(0, 10))

        MDLabel(
            controls, self._theme, "Объём", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(0, 4))
        self.size_var = ctk.StringVar(value="1 ГБ")
        MDOptionMenu(
            controls, self._theme, values=list(SCAN_SIZES), variable=self.size_var,
            width=108, height=34,
        ).pack(side="left", padx=(0, 10))

        self.start_btn = MDButton(
            controls, self._theme, "Проверить", self._start_scan,
            kind="filled", width=112, height=34, state="disabled",
        )
        self.start_btn.pack(side="left", padx=(0, 6))

        self.cancel_btn = MDButton(
            controls, self._theme, "Стоп", self._cancel_scan,
            kind="outlined", width=72, height=34, state="disabled",
        )
        self.cancel_btn.pack(side="left")

        self.admin_label = MDLabel(
            scan_card, self._theme, "", role="warning", font=FONT_CAPTION, anchor="w",
        )
        self.admin_label.pack(fill="x", padx=14)

        self.progress = MDProgress(scan_card, self._theme, height=8)
        self.progress.pack(fill="x", padx=14, pady=(6, 4))
        self.progress.set(0)

        self.scan_status = MDLabel(
            scan_card, self._theme, "Готово к проверке.", role="secondary",
            font=FONT_LABEL, anchor="w",
        )
        self.scan_status.pack(fill="x", padx=14)

        self.scan_result = MDTextbox(
            scan_card, self._theme, height=120, font=FONT_MONO_SMALL,
        )
        self.scan_result.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        self._set_scan_result("")

        self._switch_tab("Диски и SMART")

    def _switch_tab(self, value: str) -> None:
        """Показать выбранную вкладку раздела «Диски»."""
        if value.startswith("Проверка"):
            self._scan_pane.tkraise()
        else:
            self._smart_pane.tkraise()

    # ── Данные ──────────────────────────────────────

    def refresh(self) -> None:
        """Перечитать список дисков и SMART-счётчики."""
        if self._is_loading:
            return
        self._is_loading = True
        self.refresh_btn.configure(state="disabled")
        self.scan_status.configure(text="🔄  Чтение SMART-данных…")
        if self._statusbar:
            self._statusbar.set_status("🔄  Чтение SMART-данных…")

        def worker() -> None:
            try:
                disks = list_disks()
            except Exception as e:  # PowerShell/WMI могут быть недоступны
                self._ui.post(self._refresh_error, str(e))
            else:
                self._ui.post(self._after_refresh, disks)

        threading.Thread(target=worker, daemon=True, name="disks").start()

    def _refresh_error(self, message: str) -> None:
        self._is_loading = False
        self.refresh_btn.configure(state="normal")
        self.scan_status.configure(text=f"❌  {message}")
        if self._statusbar:
            self._statusbar.set_status("⚠️  SMART недоступен")
        self._on_log(f"❌  SMART недоступен: {message}")

    def _after_refresh(self, disks: list[dict]) -> None:
        self._is_loading = False
        self.refresh_btn.configure(state="normal")
        self._disks = disks
        self._by_index = {int(d.get("index", 0)): d for d in disks}

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for disk in disks:
            tag = {"OK": "ok", "WARN": "warn", "BAD": "bad"}.get(
                disk.get("health", "?"), "unknown"
            )
            self.tree.insert(
                "", "end", iid=str(disk.get("index", 0)),
                values=format_disk_row(disk), tags=(tag,),
            )

        if disks:
            self.empty_label.place_forget()
        else:
            self.empty_label.configure(
                text="Диски не найдены — проверьте доступ к Storage API."
            )
            self.empty_label.place(relx=0.5, rely=0.6, anchor="center")

        values = [
            f"{d.get('index', 0)} · {d.get('model', '—')}" for d in disks
        ]
        if values:
            self.disk_menu.configure(values=values)
            if self.disk_var.get() not in values:
                self.disk_var.set(values[0])
            self.start_btn.configure(state="normal")
            self._on_disk_pick(self.disk_var.get())
            self._set_details(self._disk_details(disks[0]))
        else:
            self.disk_menu.configure(values=["—"])
            self.disk_var.set("—")
            self.start_btn.configure(state="disabled")
            self._set_details(
                "Не удалось получить список дисков.\n"
                "Проверьте, что доступны PowerShell и Storage-команды."
            )

        if is_admin():
            self.admin_label.configure(text="🛡️  Права администратора: есть.")
        else:
            self.admin_label.configure(
                text="🛡️  Для чтения физического диска нужны права "
                     "администратора — нажмите 🛡️ в заголовке."
            )
        self.scan_status.configure(
            text=f"Найдено дисков: {len(disks)}." if disks else "Диски не найдены."
        )
        if self._statusbar:
            self._statusbar.set_status(
                f"💽  Дисков: {len(disks)}" if disks else "⚠️  Диски не найдены"
            )
        self._on_log(f"💽  Дисков найдено: {len(disks)}")

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        disk = self._by_index.get(int(selection[0]))
        if disk is None:
            return
        self._set_details(self._disk_details(disk))
        self.disk_var.set(f"{disk.get('index', 0)} · {disk.get('model', '—')}")
        self.start_btn.configure(state="normal")

    def _on_disk_pick(self, value: str) -> None:
        index = self._selected_index()
        if index is None:
            self.start_btn.configure(state="disabled")
            return
        disk = self._by_index.get(index)
        if disk is not None:
            self._set_details(self._disk_details(disk))
        self.start_btn.configure(state="normal")

    def _selected_index(self) -> int | None:
        value = self.disk_var.get().strip()
        if not value or value == "—":
            return None
        head = value.split("·", 1)[0].strip()
        try:
            return int(head)
        except ValueError:
            return None

    def _disk_details(self, disk: dict) -> str:
        temp = disk.get("temperature")
        wear = disk.get("wear")
        code = disk.get("health", "?")
        lines = [
            f"{health_icon(code)}  {disk.get('model', '—')}",
            f"Физический диск: PhysicalDrive{disk.get('index', 0)}   ·   "
            f"шина: {disk.get('bus') or '—'}   ·   тип: {disk.get('media') or '—'}",
            f"Объём: {format_bytes(int(disk.get('size') or 0))}   ·   "
            f"состояние: {code} ({disk.get('status') or '—'})",
            f"Температура: {temp} °C   ·   наработка: {format_hours(disk.get('hours'))}"
            if isinstance(temp, int) and temp > 0
            else f"Температура: —   ·   наработка: {format_hours(disk.get('hours'))}",
            f"Износ: {wear}%   ·   ошибки чтения/записи: "
            f"{disk.get('read_errors') if disk.get('read_errors') is not None else '—'}"
            f" / "
            f"{disk.get('write_errors') if disk.get('write_errors') is not None else '—'}",
            f"Серийный номер: {disk.get('serial') or '—'}",
        ]
        return "\n".join(lines)

    # ── Проверка поверхности ────────────────────────

    def _start_scan(self) -> None:
        if self._is_scanning:
            return
        index = self._selected_index()
        if index is None:
            return
        if not is_admin():
            messagebox.showwarning(
                "Нужны права администратора",
                "Чтение физического диска доступно только с правами "
                "администратора.\nНажмите 🛡️ в заголовке и повторите.",
            )
            return

        disk = self._by_index.get(index, {})
        limit = SCAN_SIZES.get(self.size_var.get())
        if limit is None and not messagebox.askyesno(
            "Полная проверка",
            "Будет прочитан весь диск. На HDD это может занять часы.\n"
            "Продолжить?",
        ):
            return

        self._is_scanning = True
        self._scan_cancel.clear()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.refresh_btn.configure(state="disabled")
        self.progress.set(0)
        self.scan_status.configure(text="▶  Чтение поверхности…")
        self._set_scan_result("")
        if self._statusbar:
            self._statusbar.set_status("🧪  Проверка поверхности…")
        self._on_log(
            f"🧪  Проверка поверхности PhysicalDrive{index} "
            f"({self.size_var.get()})…"
        )

        def on_progress(done: int, total: int, speed: float) -> None:
            self._ui.post(self._scan_progress, done, total, speed)

        def worker() -> None:
            try:
                result = read_surface(
                    index,
                    int(disk.get("size") or 0),
                    limit,
                    cancel=self._scan_cancel,
                    on_progress=on_progress,
                )
            except PermissionError as e:
                self._ui.post(self._scan_failed, str(e))
            except Exception as e:  # OSError, ctypes и т.п.
                self._ui.post(self._scan_failed, str(e))
            else:
                self._ui.post(self._scan_done, result)

        threading.Thread(target=worker, daemon=True, name="surface").start()

    def _cancel_scan(self) -> None:
        if not self._is_scanning:
            return
        self._scan_cancel.set()
        self.cancel_btn.configure(state="disabled")
        self.scan_status.configure(text="⏹  Остановка…")

    def _scan_progress(self, done: int, total: int, speed: float) -> None:
        pct = done / total if total > 0 else 0
        self.progress.set(min(max(pct, 0.0), 1.0))
        self.scan_status.configure(
            text=f"{format_bytes(done)} / {format_bytes(total)}   ·   "
                 f"{format_speed(speed)}   ·   {pct * 100:.1f}%"
        )

    def _scan_done(self, result: dict) -> None:
        self._finish_scan()
        icon = "⏹" if result.get("aborted") else "✅"
        lines = [
            f"{icon}  Проверка {'прервана' if result.get('aborted') else 'завершена'}",
            f"Прочитано: {format_bytes(int(result.get('read_bytes', 0)))} "
            f"из {format_bytes(int(result.get('total_bytes', 0)))}",
            f"Время: {format_duration(result.get('elapsed', 0))}   ·   "
            f"средняя: {format_speed(result.get('avg_speed', 0))}   ·   "
            f"мин: {format_speed(result.get('min_speed', 0))}   ·   "
            f"макс: {format_speed(result.get('max_speed', 0))}",
        ]
        errors = result.get("errors") or []
        lines.append(f"Ошибок чтения: {len(errors)}")
        if errors:
            lines.append("")
            for error in errors[:20]:
                offset = int(error.get("offset", 0)) / 1024 ** 2
                lines.append(
                    f"  ⚠️  {offset:.1f} МБ — код {error.get('code', '?')}"
                )
            if len(errors) > 20:
                lines.append(f"  … и ещё {len(errors) - 20}")
        self._set_scan_result("\n".join(lines))
        self._on_log(
            f"{icon}  Поверхность: ошибок {len(errors)}, "
            f"{format_speed(result.get('avg_speed', 0))}"
        )

    def _scan_failed(self, message: str) -> None:
        self._finish_scan()
        self._set_scan_result(f"❌  Не удалось проверить диск:\n{message}")
        self.scan_status.configure(text="❌  Проверка не выполнена")
        self._on_log(f"❌  Проверка поверхности: {message}")

    def _finish_scan(self) -> None:
        self._is_scanning = False
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.refresh_btn.configure(state="normal")
        if self._statusbar:
            self._statusbar.set_status("✅  Диски")

    # ── Helpers ─────────────────────────────────────

    def _set_details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _set_scan_result(self, text: str) -> None:
        self.scan_result.configure(state="normal")
        self.scan_result.delete("1.0", "end")
        self.scan_result.insert("1.0", text)
        self.scan_result.configure(state="disabled")

    def _paint_tree_tags(self) -> None:
        c = self._theme.colors
        self.tree.tag_configure("ok", foreground=c.SUCCESS)
        self.tree.tag_configure("warn", foreground=c.WARNING)
        self.tree.tag_configure("bad", foreground=c.ERROR)
        self.tree.tag_configure("unknown", foreground=c.TEXT_MUTED)

    def refresh_theme(self) -> None:
        c = self._theme.colors
        style_treeview("Disks", self._theme, row_height=30)
        self._paint_tree_tags()
        self._table_scroll.configure(
            button_color=c.OUTLINE_VARIANT, button_hover_color=c.OUTLINE,
        )

    def destroy(self) -> None:
        try:
            self._scan_cancel.set()
            self._ui.stop()
        except Exception:
            pass
        super().destroy()
