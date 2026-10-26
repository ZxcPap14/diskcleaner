"""📋 История — журнал очисток с фильтрами и экспортом."""
from __future__ import annotations

import datetime
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.history_filter import (
    filter_entries,
    format_details,
    freed_by_month,
    parse_date,
    summarize_details,
    total_freed,
)
from disk_cleaner_app.ui.assets import (
    FONT_CAPTION,
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
    MDTextbox,
    PageHeader,
    SectionTitle,
    style_treeview,
)
from disk_cleaner_app.ui.theme import ThemeManager


class HistoryView(ctk.CTkFrame):
    """Журнал операций: фильтр по датам и тексту, детали, экспорт."""

    def __init__(self, parent, theme: ThemeManager, history_getter,
                 on_export: Callable[[str, Path, list[dict]], Path] | None = None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._history_getter = history_getter
        self._on_export = on_export
        self._all: list[dict] = []
        self._shown: list[dict] = []
        self.configure(fg_color="transparent")
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "История операций",
            "Журнал очисток с фильтрами и экспортом отчётов",
            icon="≡",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        MDButton(
            header.actions, self._theme, "JSON", lambda: self._export("json"),
            kind="outlined", width=78, height=34,
        ).pack(side="right")
        MDButton(
            header.actions, self._theme, "CSV", lambda: self._export("csv"),
            kind="tonal", width=78, height=34,
        ).pack(side="right", padx=(0, 6))

        # ── Фильтры ───────────────────────────────────
        filters = MDCard(self, self._theme, tone="low")
        filters.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(filters, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 6))

        MDLabel(
            row, self._theme, "С", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(0, 4))
        self.from_var = ctk.StringVar(value="")
        MDEntry(
            row, self._theme, textvariable=self.from_var, width=110,
            placeholder_text="ГГГГ-ММ-ДД",
        ).pack(side="left")

        MDLabel(
            row, self._theme, "по", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(8, 4))
        self.to_var = ctk.StringVar(value="")
        MDEntry(
            row, self._theme, textvariable=self.to_var, width=110,
            placeholder_text="ГГГГ-ММ-ДД",
        ).pack(side="left")

        MDLabel(
            row, self._theme, "Тип", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(12, 4))
        self.type_var = ctk.StringVar(value="Все типы")
        self.type_menu = ctk.CTkOptionMenu(
            row,
            values=["Все типы", "Smart Clean", "Глубокая очистка", "Очистка"],
            variable=self.type_var, width=150, height=32,
            command=lambda _v: self._apply(),
        )
        self.type_menu.pack(side="left")

        MDLabel(
            row, self._theme, "⌕", role="secondary", font=("Segoe UI", 14),
        ).pack(side="left", padx=(12, 4))
        self.query_var = ctk.StringVar(value="")
        MDEntry(
            row, self._theme, textvariable=self.query_var,
            placeholder_text="Цель, статус или заметка…",
        ).pack(side="left", fill="x", expand=True)

        MDButton(
            row, self._theme, "Применить", self._apply,
            kind="filled", width=102, height=32,
        ).pack(side="left", padx=(8, 0))
        MDButton(
            row, self._theme, "Сбросить", self._reset,
            kind="text_muted", width=88, height=32,
        ).pack(side="left", padx=(4, 0))

        self.hint_label = MDLabel(
            filters, self._theme,
            "Дата — включительно; пустое поле не ограничивает.",
            role="muted", font=FONT_CAPTION, anchor="w",
        )
        self.hint_label.pack(fill="x", padx=14, pady=(0, 10))

        self._search_trace = self.query_var.trace_add(
            "write", lambda *_: self._apply()
        )

        # ── Таблица ───────────────────────────────────
        table_card = MDCard(self, self._theme, tone="low")
        table_card.grid(row=2, column=0, sticky="nsew", pady=(0, SPACE_2))

        style_treeview("History", self._theme, row_height=30)
        cols = ("date", "items", "freed", "targets")
        self.tree = ttk.Treeview(
            table_card, columns=cols, show="headings",
            selectmode="browse", style="History.Treeview",
        )
        self.tree.heading("date", text="Дата", anchor="w")
        self.tree.heading("items", text="Целей", anchor="center")
        self.tree.heading("freed", text="Освобождено", anchor="e")
        self.tree.heading("targets", text="Цели", anchor="w")
        self.tree.column("date", width=150, minwidth=120, stretch=False)
        self.tree.column("items", width=64, minwidth=50, anchor="center", stretch=False)
        self.tree.column("freed", width=118, minwidth=90, anchor="e", stretch=False)
        self.tree.column("targets", width=430, minwidth=200)

        self._table_scroll = ctk.CTkScrollbar(
            table_card, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.tree.configure(yscrollcommand=self._table_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(14, 2), pady=(12, 2))
        self._table_scroll.pack(side="right", fill="y", padx=(0, 10), pady=(12, 2))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Детали и график (в одном ряду) ────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.grid_rowconfigure(0, weight=1)
        bottom.grid_columnconfigure(0, weight=3)
        bottom.grid_columnconfigure(1, weight=2)

        details_card = MDCard(bottom, self._theme, tone="low")
        details_card.grid(row=0, column=0, sticky="nsew")

        details_top = ctk.CTkFrame(details_card, fg_color="transparent")
        details_top.pack(fill="x", padx=14, pady=(10, 4))
        SectionTitle(
            details_top, self._theme, "Детали записи",
            "Что именно было очищено и с каким результатом",
        ).pack(side="left")

        self.details = MDTextbox(
            details_card, self._theme, height=96, font=FONT_MONO_SMALL,
        )
        self.details.pack(fill="x", padx=14, pady=(0, 8))
        self._set_details("Выберите запись, чтобы увидеть детали очистки.")

        chart_card = MDCard(bottom, self._theme, tone="low")
        chart_card.grid(row=0, column=1, sticky="nsew", padx=(SPACE_2, 0))

        SectionTitle(
            chart_card, self._theme, "Освобождено по месяцам",
            "Сумма по записям текущего фильтра, последние 12 месяцев",
        ).pack(fill="x", padx=14, pady=(12, 4))

        self.chart = ctk.CTkCanvas(
            chart_card, height=96, bg=self._theme.colors.SURFACE_LOW,
            highlightthickness=0, bd=0,
        )
        self.chart.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.chart.bind("<Configure>", lambda e: self._draw_chart())

        self.status_label = MDLabel(
            self, self._theme, "", role="muted", font=FONT_CAPTION, anchor="w",
        )
        self.status_label.grid(row=4, column=0, sticky="ew", pady=(2, 0))

    # ── данные ───────────────────────────────────────────

    def refresh(self) -> None:
        """Перечитать историю и применить текущие фильтры."""
        try:
            self._all = list(self._history_getter() or [])
        except Exception:
            self._all = []
        self._apply()

    def _apply(self) -> None:
        date_from = self.from_var.get()
        date_to = self.to_var.get()

        invalid: list[str] = []
        if date_from.strip() and parse_date(date_from) is None:
            invalid.append("«С»")
        if date_to.strip() and parse_date(date_to) is None:
            invalid.append("«По»")
        if invalid:
            self.hint_label.configure(
                text=f"Некорректная дата в поле {' и '.join(invalid)}: "
                     "нужен формат ГГГГ-ММ-ДД.",
                text_color=self._theme.colors.DANGER,
            )
        else:
            self.hint_label.configure(
                text="Дата — включительно; пустое поле не ограничивает.",
                text_color=self._theme.colors.TEXT_MUTED,
            )

        type_labels = {
            "Smart Clean": "smart",
            "Глубокая очистка": "deep",
            "Очистка": "clean",
        }
        entries = filter_entries(
            self._all,
            date_from=date_from,
            date_to=date_to,
            query=self.query_var.get(),
            op_type=type_labels.get(self.type_var.get(), ""),
        )
        self._render(entries)

    def _render(self, entries: list[dict]) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        self._shown = entries
        for entry in entries:
            date = str(entry.get("date", "")).replace("T", " ")[:16]
            self.tree.insert(
                "", "end", iid=str(entry.get("id", "")),
                values=(
                    date,
                    entry.get("items_cleaned", 0),
                    format_bytes(int(entry.get("bytes_freed", 0) or 0)),
                    summarize_details(entry),
                ),
            )

        total = total_freed(entries)
        if not self._all:
            text = "История пуста — выполните очистку."
        elif len(entries) == len(self._all):
            text = f"Записей: {len(entries)} · всего {format_bytes(total)}"
        else:
            text = (
                f"Показано: {len(entries)} из {len(self._all)} · "
                f"{format_bytes(total)}"
            )
        self.status_label.configure(text=text)
        self._set_details("Выберите запись, чтобы увидеть детали очистки.")
        self._draw_chart()

    def _draw_chart(self) -> None:
        """Столбцы освобождённого места по месяцам для показанных записей."""
        canvas = self.chart
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 40 or height < 40:
            return

        c = self._theme.colors
        data = freed_by_month(self._shown)[-12:]
        if not data:
            canvas.create_text(
                width / 2, height / 2, text="Нет данных за выбранный период",
                fill=c.ON_SURFACE_VARIANT, font=FONT_CAPTION,
            )
            return

        peak = max(value for _month, value in data) or 1
        slot = width / len(data)
        show_values = slot >= 46
        top = 20 if show_values else 6
        baseline = height - 16
        bar_width = max(5.0, min(26.0, slot * 0.55))

        for index, (month, value) in enumerate(data):
            x = slot * (index + 0.5)
            bar_height = (baseline - top) * (value / peak)
            if bar_height > 0:
                canvas.create_rectangle(
                    x - bar_width / 2, baseline - bar_height,
                    x + bar_width / 2, baseline,
                    fill=c.PRIMARY, outline="",
                )
                if show_values:
                    canvas.create_text(
                        x, baseline - bar_height - 3, anchor="s",
                        text=format_bytes(value), fill=c.ON_SURFACE_VARIANT,
                        font=FONT_CAPTION,
                    )
            canvas.create_text(
                x, baseline + 3, anchor="n",
                text=f"{month[5:7]}.{month[2:4]}",
                fill=c.ON_SURFACE_VARIANT, font=FONT_CAPTION,
            )

        canvas.create_line(
            0, baseline, width, baseline, fill=c.OUTLINE_VARIANT,
        )

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        entry_id = selection[0]
        entry = next(
            (e for e in self._shown if str(e.get("id")) == entry_id), None
        )
        if entry is None:
            return
        self._set_details(format_details(entry))

    def _set_details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _reset(self) -> None:
        self.from_var.set("")
        self.to_var.set("")
        self.query_var.set("")
        self.type_var.set("Все типы")
        self.refresh()

    # ── экспорт ──────────────────────────────────────────

    def _export(self, kind: str) -> None:
        if self._on_export is None:
            return
        entries = list(self._shown)
        if not entries:
            messagebox.showinfo(
                "Экспорт журнала", "Нет записей для экспорта: измените фильтры."
            )
            return
        suffix = ".json" if kind == "json" else ".csv"
        default = (
            f"DiskCleaner-history-{datetime.date.today().isoformat()}{suffix}"
        )
        path = filedialog.asksaveasfilename(
            parent=self, title="Экспорт журнала", defaultextension=suffix,
            initialfile=default,
            filetypes=[("JSON", "*.json")] if kind == "json"
            else [("CSV", "*.csv")],
        )
        if not path:
            return
        entries = list(self._shown)
        try:
            target = self._on_export(kind, Path(path), list(entries))
        except OSError as e:
            messagebox.showerror("Экспорт журнала", f"Не удалось сохранить: {e}")
            return
        messagebox.showinfo("Экспорт журнала", f"Сохранено:\n{target}")

    def refresh_theme(self) -> None:
        c = self._theme.colors
        style_treeview("History", self._theme, row_height=30)
        self._table_scroll.configure(
            button_color=c.OUTLINE_VARIANT, button_hover_color=c.OUTLINE,
        )
        self.chart.configure(bg=c.SURFACE_LOW)
        self._apply()

    def destroy(self) -> None:
        try:
            self.query_var.trace_remove("write", self._search_trace)
        except Exception:
            pass
        super().destroy()
