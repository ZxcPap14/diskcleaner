"""🔍 Duplicates — поиск дублирующихся файлов."""
from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.duplicates import DuplicateFinder
from disk_cleaner_app.ui.assets import FONT_LABEL, FONT_MONO, SPACE_2, SPACE_3
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDEntry,
    MDIconButton,
    MDLabel,
    MDTextbox,
    PageHeader,
    SectionTitle,
)
from disk_cleaner_app.ui.dispatch import UiDispatcher
from disk_cleaner_app.ui.theme import ThemeManager


class DuplicatesView(ctk.CTkFrame):
    """Поиск дубликатов: быстрый и по MD5."""

    def __init__(self, parent, theme: ThemeManager, on_log, **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._on_log = on_log
        self._finder = DuplicateFinder()
        self._dups: list[dict] = []
        self._is_searching = False
        self._cancel = threading.Event()
        self._ui = UiDispatcher(self)
        self._ui.start()
        self.configure(fg_color="transparent")
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Дубликаты",
            "Найдите одинаковые файлы и освободите место без риска",
            icon="⧉",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        # ── Параметры поиска ──────────────────────────
        search_card = MDCard(self, self._theme, tone="low")
        search_card.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        path_row = ctk.CTkFrame(search_card, fg_color="transparent")
        path_row.pack(fill="x", padx=14, pady=(12, 6))

        MDLabel(
            path_row, self._theme, "Папка поиска", role="muted",
            font=FONT_LABEL,
        ).pack(side="left", padx=(2, 8))

        self.dup_path = ctk.StringVar(value=str(Path.home()))
        MDEntry(
            path_row, self._theme, textvariable=self.dup_path,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        MDIconButton(
            path_row, self._theme, "…", self._browse, kind="tonal", size=36,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        actions = ctk.CTkFrame(search_card, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(0, 12))

        self.fast_btn = MDButton(
            actions, self._theme, "Быстрый поиск", self._start_fast,
            kind="filled", width=136,
        )
        self.fast_btn.pack(side="left", padx=(0, 6))

        self.exact_btn = MDButton(
            actions, self._theme, "Точный · BLAKE2b", self._start_exact,
            kind="tonal", width=164,
        )
        self.exact_btn.pack(side="left", padx=(0, 6))

        self.cancel_btn = MDButton(
            actions, self._theme, "Стоп", self._cancel_search,
            kind="outlined", width=74, state="disabled",
        )
        self.cancel_btn.pack(side="left")

        self.delete_btn = MDButton(
            actions, self._theme, "В корзину", self._delete_duplicates,
            kind="danger_tonal", width=112, state="disabled",
        )
        self.delete_btn.pack(side="right")

        self.dup_status = MDLabel(
            actions, self._theme, "Готово к поиску", role="secondary",
            font=FONT_LABEL,
        )
        self.dup_status.pack(side="right", padx=(0, 12))

        # ── Результаты ────────────────────────────────
        results = MDCard(self, self._theme, tone="low")
        results.grid(row=2, column=0, sticky="nsew")

        title_row = ctk.CTkFrame(results, fg_color="transparent")
        title_row.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            title_row, self._theme, "Результаты",
            "В каждой паре удаляется только второй файл",
        ).pack(side="left")

        self.dup_text = MDTextbox(results, self._theme, font=FONT_MONO)
        self.dup_text.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.dup_text.insert(
            "1.0",
            "Выберите папку и запустите поиск.\n\n"
            "«Быстрый поиск» сравнивает размер и начало файла,\n"
            "«Точный · BLAKE2b» — полное совпадение содержимого.\n"
            "В каждой паре удаляется только второй файл.",
        )
        self.dup_text.configure(state="disabled")

    def _browse(self) -> None:
        p = filedialog.askdirectory(initialdir=self.dup_path.get())
        if p:
            self.dup_path.set(p)

    def _start_fast(self) -> None:
        self._run_search("fast")

    def _start_exact(self) -> None:
        self._run_search("exact")

    def _run_search(self, mode: str) -> None:
        if self._is_searching:
            return
        self._is_searching = True
        self._dups = []
        self._cancel.clear()
        self.fast_btn.configure(state="disabled")
        self.exact_btn.configure(state="disabled")
        self.delete_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.dup_status.configure(text="🔄 Поиск...")
        self.dup_text.configure(state="normal")
        self.dup_text.delete("1.0", "end")
        self.dup_text.insert("1.0", "🔄 Сканирование...\n")
        self.dup_text.configure(state="disabled")

        def worker():
            fn = (
                self._finder.find_fast_groups
                if mode == "fast"
                else self._finder.find_exact_groups
            )
            try:
                groups = fn(
                    self.dup_path.get(),
                    cancel=self._cancel,
                    progress=self._search_progress,
                )
            except Exception as e:
                self._ui.post(self._show_result, f"❌ Ошибка поиска: {e}\n", 0, [])
                return
            cancelled = self._cancel.is_set()
            extra = sum(g["count"] - 1 for g in groups)
            text = (
                f"{'⚡ Быстрый' if mode == 'fast' else '🎯 BLAKE2b'}: "
                f"{len(groups)} групп · {extra} лишних копий · "
                f"зря занято {format_bytes(sum(g['wasted'] for g in groups))}\n"
            )
            if cancelled:
                text = "⏹ Поиск остановлен.\n" + text
            text += "═" * 50 + "\n"
            for g in groups[:50]:
                text += (
                    f"📄 {g['name']}  ×{g['count']}  "
                    f"{format_bytes(g['size'])} каждый · зря {format_bytes(g['wasted'])}\n"
                )
                for i, path in enumerate(g["files"]):
                    mark = "оригинал" if i == 0 else f"копия {i}"
                    text += f"  {i + 1}: [{mark}] {path}\n"
                text += "\n"
            self._ui.post(self._show_result, text, len(groups), groups)

        threading.Thread(target=worker, daemon=True).start()

    def _search_progress(self, done: int, total: int, label: str) -> None:
        """Колбэк из фонового потока: обновляем только через UiDispatcher."""
        text = f"{label}: {done}/{total}" if total else label
        self._ui.post(self._set_status, text)

    def _set_status(self, text: str) -> None:
        self.dup_status.configure(text=text)

    def _cancel_search(self) -> None:
        if not self._is_searching:
            return
        self._cancel.set()
        self.cancel_btn.configure(state="disabled")
        self.dup_status.configure(text="⏹ Остановка...")

    def _show_result(self, text: str, n: int, dups: list[dict]) -> None:
        self._is_searching = False
        self._dups = dups
        self.dup_text.configure(state="normal")
        self.dup_text.delete("1.0", "end")
        self.dup_text.insert("1.0", text)
        self.dup_text.configure(state="disabled")
        self.fast_btn.configure(state="normal")
        self.exact_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.delete_btn.configure(state="normal" if dups else "disabled")
        self.dup_status.configure(text=f"✅ {n}")

    def _delete_duplicates(self) -> None:
        if self._is_searching or not self._dups:
            return

        pairs = []
        for group in self._dups:
            files = group.get("files") or []
            if len(files) < 2:
                continue
            for extra in files[1:]:
                pairs.append({"file1": files[0], "file2": extra})

        unique_targets = {p["file2"] for p in pairs}
        total_size = sum(int(g.get("wasted", 0)) for g in self._dups)

        if not messagebox.askyesno(
            "Удаление дубликатов",
            f"Переместить в корзину {len(unique_targets)} файлов "
            f"({format_bytes(total_size)})?\n\n"
            "В каждой группе удаляются все копии, кроме первой (оригинала).",
        ):
            return

        self._is_searching = True
        self.fast_btn.configure(state="disabled")
        self.exact_btn.configure(state="disabled")
        self.delete_btn.configure(state="disabled")
        self.dup_status.configure(text="🗑️ Удаление...")

        def worker():
            result = self._finder.delete_duplicates(pairs, to_recycle=True)
            self._ui.post(self._after_delete, result)

        threading.Thread(target=worker, daemon=True).start()

    def _after_delete(self, result: dict) -> None:
        self._is_searching = False
        self.fast_btn.configure(state="normal")
        self.exact_btn.configure(state="normal")
        self.delete_btn.configure(state="disabled")
        self._dups = []
        self.dup_status.configure(
            text=f"🗑️ {result['deleted']} · ошибок: {result['failed']}"
        )
        self.dup_text.configure(state="normal")
        self.dup_text.insert("end", "\n" + "═" * 50 + "\n")
        self.dup_text.insert(
            "end",
            f"🗑️ В корзину: {result['deleted']} файлов "
            f"({format_bytes(result['freed'])})\n",
        )
        for error in result["errors"][:20]:
            self.dup_text.insert("end", f"⚠️  {error}\n")
        self.dup_text.configure(state="disabled")
        self._on_log(
            f"🔍 Дубликаты: в корзину {result['deleted']} файлов, "
            f"{format_bytes(result['freed'])}"
        )

    def refresh_theme(self) -> None:
        c = self._theme.colors
        self.dup_text.configure(
            fg_color=c.SURFACE_LOWEST, text_color=c.ON_SURFACE_VARIANT,
        )

    def destroy(self) -> None:
        try:
            self._ui.stop()
        except Exception:
            pass
        super().destroy()
