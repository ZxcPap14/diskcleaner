"""🔍 Duplicates — поиск дублирующихся файлов."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.duplicates import (
    ORIGINAL_POLICIES,
    DuplicateFinder,
    arrange_groups,
)
from disk_cleaner_app.ui.assets import (
    FONT_CAPTION,
    FONT_LABEL,
    FONT_MONO,
    SPACE_2,
    SPACE_3,
)
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDCheckbox,
    MDEntry,
    MDIconButton,
    MDLabel,
    MDOptionMenu,
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
        self._raw_dups: list[dict] = []
        self._last_mode = "fast"
        self._last_cancelled = False
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

        rules = ctk.CTkFrame(search_card, fg_color="transparent")
        rules.pack(fill="x", padx=14, pady=(0, 8))

        MDLabel(
            rules, self._theme, "Оригинал:", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(2, 6))

        self.policy_menu = MDOptionMenu(
            rules, self._theme,
            values=list(ORIGINAL_POLICIES.values()),
            width=148, height=30,
            command=lambda _value: self._render_results(),
        )
        self.policy_menu.set(ORIGINAL_POLICIES["oldest"])
        self.policy_menu.pack(side="left", padx=(0, 12))

        self.junk_var = ctk.BooleanVar(value=True)
        self.junk_check = MDCheckbox(
            rules, self._theme, "Temp/Downloads — первыми",
            variable=self.junk_var, command=self._render_results,
            bg_color=self._theme.colors.SURFACE_LOW, font=FONT_CAPTION,
        )
        self.junk_check.pack(side="left")
        self.junk_check.select()

        self.whitelist_label = MDLabel(
            rules, self._theme, "", role="muted", font=FONT_CAPTION,
        )
        self.whitelist_label.pack(side="right", padx=(8, 2))

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
        self._raw_dups = []
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
                self._ui.post(self._show_error, str(e))
                return
            self._ui.post(
                self._show_result, groups, mode, self._cancel.is_set()
            )

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

    def _show_error(self, message: str) -> None:
        self._is_searching = False
        self._raw_dups = []
        self._dups = []
        self.fast_btn.configure(state="normal")
        self.exact_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.delete_btn.configure(state="disabled")
        self.dup_status.configure(text="❌ Ошибка")
        self._set_text(f"❌ Ошибка поиска: {message}\n")

    def _set_text(self, text: str) -> None:
        self.dup_text.configure(state="normal")
        self.dup_text.delete("1.0", "end")
        self.dup_text.insert("1.0", text)
        self.dup_text.configure(state="disabled")

    def _whitelist(self) -> list[str]:
        """Белый список из настроек: такие пути не попадают в корзину."""
        try:
            raw = ConfigManager().get("whitelist", [])
        except Exception:
            return []
        if isinstance(raw, list):
            return [str(w) for w in raw if str(w).strip()]
        return []

    def _policy_key(self) -> str:
        label = self.policy_menu.get()
        for key, title in ORIGINAL_POLICIES.items():
            if title == label:
                return key
        return "oldest"

    def _show_result(
        self, groups: list[dict], mode: str, cancelled: bool,
    ) -> None:
        self._is_searching = False
        self._raw_dups = groups
        self._last_mode = mode
        self._last_cancelled = cancelled
        self.fast_btn.configure(state="normal")
        self.exact_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self._render_results()

    def _render_results(self) -> None:
        """Пересчитать оригиналы и предпросмотр без повторного поиска."""
        if not self._raw_dups:
            self._dups = []
            self.delete_btn.configure(state="disabled")
            self.dup_status.configure(text="✅ 0 групп")
            self._set_text(
                "Дубликатов не найдено. Попробуйте другую папку, "
                "меньший порог или точный режим.\n"
            )
            return
        whitelist = self._whitelist()
        groups = arrange_groups(
            self._raw_dups,
            self._policy_key(),
            whitelist,
            junk_first=self.junk_var.get(),
        )
        self._dups = groups
        targets = sum(len(g.get("deletable", [])) for g in groups)
        protected = sum(len(g.get("protected", [])) for g in groups)
        wasted = sum(int(g.get("wasted", 0)) for g in groups)

        mode_label = "⚡ Быстрый" if self._last_mode == "fast" else "🎯 BLAKE2b"
        text = (
            f"{mode_label}: {len(groups)} групп · {targets} к удалению · "
            f"зря занято {format_bytes(wasted)}\n"
        )
        if protected:
            text = (
                f"{text}🔒 Защищено белым списком: {protected} "
                "(не удаляются)\n"
            )
        if self._last_cancelled:
            text = "⏹ Поиск остановлен.\n" + text
        text += "═" * 50 + "\n"

        for group in groups[:50]:
            text += (
                f"📄 {group['name']}  ×{group['count']}  "
                f"{format_bytes(group['size'])} каждый · "
                f"зря {format_bytes(group['wasted'])}\n"
            )
            protected_keys = {
                os.path.normcase(p) for p in group.get("protected", [])
            }
            copy_no = 0
            for i, path in enumerate(group["files"]):
                if i == 0:
                    mark = "оригинал"
                elif os.path.normcase(path) in protected_keys:
                    mark = "🔒 белый список"
                else:
                    copy_no += 1
                    mark = f"копия {copy_no}"
                text += f"  {i + 1}: [{mark}] {path}\n"
            text += "\n"

        if protected:
            text += "🔒 — путь из белого списка, никогда не удаляется.\n"
        if not targets:
            text += "\nУдалять нечего: все копии защищены белым списком.\n"

        self._set_text(text)
        self.delete_btn.configure(state="normal" if targets else "disabled")
        self.dup_status.configure(
            text=f"✅ {len(groups)} групп · к удалению {targets}"
        )
        self.whitelist_label.configure(
            text=f"🔒 белый список: {len(whitelist)}" if whitelist else ""
        )

    def _delete_duplicates(self) -> None:
        if self._is_searching or not self._dups:
            return

        pairs = []
        seen: set[str] = set()
        protected = 0
        for group in self._dups:
            files = group.get("files") or []
            if len(files) < 2:
                continue
            original = group.get("original") or files[0]
            protected += len(group.get("protected", []))
            for extra in group.get("deletable", []):
                key = os.path.normcase(extra)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append({"file1": original, "file2": extra})

        if not pairs:
            return
        total_size = sum(
            int(g.get("size", 0)) * len(g.get("deletable", []))
            for g in self._dups
        )

        note = (
            f"\n\n🔒 Защищено белым списком: {protected} — не удаляются."
            if protected else ""
        )
        if not messagebox.askyesno(
            "Удаление дубликатов",
            f"Переместить в корзину {len(pairs)} файлов "
            f"({format_bytes(total_size)})?\n\n"
            "Оригинал в каждой группе остаётся на месте."
            + note,
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
        self._raw_dups = []
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
        self.junk_check.configure(bg_color=c.SURFACE_LOW)

    def destroy(self) -> None:
        try:
            self._ui.stop()
        except Exception:
            pass
        super().destroy()
