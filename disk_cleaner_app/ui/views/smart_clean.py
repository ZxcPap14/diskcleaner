"""🧹 Smart Clean — Easy/Advanced режимы, сканирование, очистка."""
from __future__ import annotations

import datetime
import logging
import threading
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from disk_cleaner_app.cleaners.base import BaseCleaner, CleanOptions
from disk_cleaner_app.cleaners.safety import validate_custom_path
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.models.item import SafetyLevel, format_bytes
from disk_cleaner_app.services.cleaner import CleanEngine, CleanResult
from disk_cleaner_app.services.scanner import ScanEngine
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_HEADLINE,
    FONT_LABEL,
    FONT_MONO,
    SPACE_2,
    SPACE_3,
)
from disk_cleaner_app.ui.components.item_tree import CleanerTree
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDEntry,
    MDIconButton,
    MDLabel,
    MDSegmented,
    MDTextbox,
    PageHeader,
)
from disk_cleaner_app.ui.dispatch import UiDispatcher
from disk_cleaner_app.ui.theme import ThemeManager

log = logging.getLogger(__name__)


class SmartCleanView(ctk.CTkFrame):
    """Вкладка очистки: выбор целей, сканирование, удаление."""

    def __init__(self, parent, theme: ThemeManager, config: ConfigManager,
                 on_log, statusbar=None, on_reload=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._config = config
        self._on_log = on_log
        self._statusbar = statusbar
        self._on_reload = on_reload
        self._scan_engine = ScanEngine()
        self._clean_engine = CleanEngine()
        self._all_cleaners: list[BaseCleaner] = []
        self._is_scanning = False
        self._is_cleaning = False
        self._ui = UiDispatcher(self)
        self._ui.start()

        self.configure(fg_color="transparent")
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Очистка",
            "Безопасное сканирование и удаление временных данных",
            icon="✦",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        self.mode_var = ctk.StringVar(value="easy")
        self.mode_seg = MDSegmented(
            header.actions, self._theme,
            values=["Easy", "Advanced"],
            variable=self.mode_var,
            command=self._on_mode_change,
            width=230,
        )
        self.mode_seg.pack(side="right")
        try:
            self.mode_seg._buttons_dict["Easy"].configure(text="🟢  Easy")
            self.mode_seg._buttons_dict["Advanced"].configure(text="🔴  Advanced")
        except Exception:
            pass

        # ── Панель действий ───────────────────────────
        toolbar = MDCard(self, self._theme, tone="low")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(toolbar, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 4))

        self.scan_btn = MDButton(
            row, self._theme, "Сканировать", self.start_scan,
            kind="filled", width=136,
        )
        self.scan_btn.pack(side="left", padx=(0, 6))

        self.cancel_btn = MDButton(
            row, self._theme, "Стоп", self.cancel_scan,
            kind="outlined", width=82, state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=(0, 6))

        self.clean_btn = MDButton(
            row, self._theme, "Очистить", self.start_clean,
            kind="tonal", width=112,
        )
        self.clean_btn.pack(side="left", padx=(0, 6))

        self.preview_btn = MDButton(
            row, self._theme, "Предпросмотр", self.show_preview,
            kind="text", width=118,
        )
        self.preview_btn.pack(side="left")

        self.custom_btn = MDIconButton(
            row, self._theme, "＋", self._add_custom_rule,
            kind="tonal", size=36,
        )
        self.custom_btn.pack(side="right")

        self.sel_label = MDLabel(
            row, self._theme, "", role="secondary", font=FONT_LABEL,
        )
        self.sel_label.pack(side="right", padx=(8, 8))

        selectors = ctk.CTkFrame(toolbar, fg_color="transparent")
        selectors.pack(fill="x", padx=14, pady=(0, 10))

        MDLabel(
            selectors, self._theme, "Выбор", role="muted", font=FONT_CAPTION,
        ).pack(side="left", padx=(2, 8))

        MDButton(
            selectors, self._theme, "Всё", self.select_all,
            kind="text", width=58, height=28,
        ).pack(side="left")
        MDButton(
            selectors, self._theme, "Снять", self.deselect_all,
            kind="text_muted", width=66, height=28,
        ).pack(side="left")
        MDButton(
            selectors, self._theme, "Безопасные", self.select_safe,
            kind="text", width=104, height=28,
        ).pack(side="left")
        MDButton(
            selectors, self._theme, "Свернуть группы", self._collapse_groups,
            kind="text_muted", width=132, height=28,
        ).pack(side="right")
        MDButton(
            selectors, self._theme, "Развернуть", self._expand_groups,
            kind="text_muted", width=100, height=28,
        ).pack(side="right")
        MDButton(
            selectors, self._theme, "Сбросить сортировку", self._reset_sort,
            kind="text_muted", width=150, height=28,
        ).pack(side="right")

        # ── Таблица целей ─────────────────────────────
        tree_card = MDCard(self, self._theme, tone="low")
        tree_card.grid(row=2, column=0, sticky="nsew", pady=(0, SPACE_2))

        search_row = ctk.CTkFrame(tree_card, fg_color="transparent")
        search_row.pack(fill="x", padx=14, pady=(12, 8))

        MDLabel(
            search_row, self._theme, "⌕", role="secondary",
            font=("Segoe UI", 15),
        ).pack(side="left", padx=(0, 6))

        self.search_var = ctk.StringVar(value="")
        self.search_entry = MDEntry(
            search_row, self._theme, textvariable=self.search_var,
            placeholder_text="Поиск по названию или категории…",
            width=360,
        )
        self.search_entry.pack(side="left")

        self.filter_label = MDLabel(
            search_row, self._theme, "", role="muted", font=FONT_LABEL,
        )
        self.filter_label.pack(side="left", padx=(10, 0))

        MDButton(
            search_row, self._theme, "Группы", self._reset_sort,
            kind="text_muted", width=82, height=30,
        ).pack(side="right")

        self.tree = CleanerTree(tree_card, self._theme, self._config)
        self.tree.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self._search_trace = self.search_var.trace_add(
            "write", lambda *_: self._on_search()
        )

        MDLabel(
            self, self._theme,
            "Клик по названию категории сворачивает группу; клик по ☐ выбирает всю категорию.",
            role="muted", font=FONT_CAPTION, anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(0, 2))

    # ── Mode switching ───────────────────────────────

    def _on_mode_change(self, val: str) -> None:
        mode = "easy" if val == "Easy" else "advanced"
        self.tree.set_mode(mode)
        self.tree.populate(self._all_cleaners)
        self._update_sel_label()

    def _on_search(self) -> None:
        """Отфильтровать видимые цели по строке поиска."""
        try:
            query = self.search_var.get()
            self.tree.set_filter(query)
        except Exception:
            return
        shown = self.tree.get_shown_count()
        total = self.tree.get_visible_count()
        self.filter_label.configure(
            text=f"найдено {shown} из {total}" if query.strip() else ""
        )
        self._update_sel_label()

    def _reset_sort(self) -> None:
        """Показать цели, сгруппированные по категориям."""
        self.tree.clear_sort()
        self._update_sel_label()

    def _collapse_groups(self) -> None:
        self.tree.collapse_all()
        self._update_sel_label()

    def _expand_groups(self) -> None:
        self.tree.expand_all()
        self._update_sel_label()

    # ── Scan ─────────────────────────────────────────

    def start_scan(self) -> None:
        if self._is_scanning or self._is_cleaning:
            return
        self._is_scanning = True
        self.scan_btn.configure(state="disabled")
        self.clean_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self._on_log("📡  Начало сканирования...")

        def worker() -> None:
            try:
                result = self._scan_engine.scan_all(
                    self._all_cleaners,
                    auto_discover=True,
                    progress_callback=self._scan_progress,
                )
                self._all_cleaners = result
            except Exception as e:
                self._ui.post(self._on_log, f"❌ Ошибка сканирования: {e}")
            finally:
                self._ui.post(self._scan_done)

        threading.Thread(target=worker, daemon=True, name="scan").start()

    def _scan_progress(self, done: int, total: int) -> None:
        pct = done / total if total > 0 else 0
        self._ui.post(self._update_progress, pct, f"{done}/{total}")

    def cancel_scan(self) -> None:
        """Остановить текущее сканирование."""
        if not self._is_scanning:
            return
        self._scan_engine.cancel()
        self.cancel_btn.configure(state="disabled")
        self._on_log("⏹️  Остановка сканирования...")

    def _update_progress(self, pct: float, label: str) -> None:
        if self._statusbar:
            self._statusbar.set_progress(pct, label)

    def _scan_done(self) -> None:
        self._is_scanning = False
        self.scan_btn.configure(state="normal")
        self.clean_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        if self._statusbar:
            self._statusbar.set_progress(1.0)

        self.tree.populate(self._all_cleaners)

        cancelled = self._scan_engine.was_cancelled
        scanned = [c for c in self._all_cleaners if c.scanned]
        total = sum(max(0, c.size) for c in scanned)
        errors = sum(1 for c in self._all_cleaners if c.scan_error)
        if cancelled:
            self._on_log(
                f"⏹️  Сканирование остановлено: обработано {len(scanned)} целей, "
                f"найдено {format_bytes(total)}"
            )
        else:
            self._on_log(f"✅  Найдено мусора: {format_bytes(total)}")
        if errors:
            self._on_log(f"⚠️  Не удалось просканировать целей: {errors}")
        self._update_sel_label()

    # ── Clean ────────────────────────────────────────

    def start_clean(self) -> None:
        if self._is_cleaning or self._is_scanning:
            return

        selected = self.tree.get_selected()
        if not selected:
            self._on_log("ℹ️  Ничего не выбрано — отметьте цели для очистки.")
            return

        if not any(c.scanned for c in selected):
            messagebox.showinfo(
                "Нужно сканирование",
                "Сначала нажмите «Сканировать», чтобы узнать размеры целей.",
            )
            return

        safe_mode = bool(self._config.get("safe_mode", True))
        to_clean = selected
        skipped = 0
        if safe_mode:
            to_clean = [c for c in selected if c.safety == SafetyLevel.SAFE]
            skipped = len(selected) - len(to_clean)
            if not to_clean:
                messagebox.showinfo(
                    "Безопасный режим",
                    "Среди выбранных нет безопасных (🟢) целей.\n"
                    "Отключите безопасный режим в настройках, если уверены.",
                )
                return

        planned = sum(max(0, c.size) for c in to_clean)
        to_recycle = bool(self._config.get("to_recycle", False))
        extra = "\nПеремещение в корзину: да." if to_recycle else ""
        if skipped:
            extra += f"\nПропущено из-за безопасного режима: {skipped}."

        if not messagebox.askyesno(
            "Подтверждение",
            f"Очистить {len(to_clean)} целей?\n"
            f"Планируется освободить: {format_bytes(planned)}"
            f"{extra}",
        ):
            return

        self._is_cleaning = True
        self.scan_btn.configure(state="disabled")
        self.clean_btn.configure(state="disabled")
        self._on_log(f"🧹  Очистка {len(to_clean)} целей...")
        if skipped:
            self._on_log(f"🛡️  Пропущено {skipped} целей (безопасный режим)")

        options = CleanOptions(to_recycle=to_recycle, safe_mode=safe_mode)

        def worker() -> None:
            results: list[CleanResult] = []
            try:
                results = self._clean_engine.clean_selected(
                    to_clean,
                    options=options,
                    progress_callback=self._clean_progress,
                )
            except Exception as e:
                self._ui.post(self._on_log, f"❌ Ошибка очистки: {e}")
            finally:
                self._ui.post(self._clean_done, results)

        threading.Thread(target=worker, daemon=True, name="clean").start()

    def _clean_progress(self, done: int, total: int, result: CleanResult) -> None:
        status = {"OK": "✅", "ERR": "❌"}.get(result.status, "•")
        message = f"  {status} {result.cleaner.name}: {result.detail}"
        if result.note:
            message += f" — {result.note}"
        self._ui.post(self._on_log, message)
        pct = done / total if total > 0 else 0
        self._ui.post(
            self._update_progress, pct, f"{done}/{total} · {result.cleaner.name}"
        )

    def _clean_done(self, results: list[CleanResult]) -> None:
        self._is_cleaning = False
        self.scan_btn.configure(state="normal")
        self.clean_btn.configure(state="normal")
        if self._statusbar:
            self._statusbar.set_progress(1.0)

        freed = sum(r.freed for r in results)
        planned = sum(r.planned for r in results)
        success = sum(1 for r in results if r.status == "OK")
        failed = sum(1 for r in results if r.status == "ERR")
        recycled = sum(r.planned for r in results if r.recycled)

        self._on_log(
            f"✅  Очищено {success} целей, освобождено: {format_bytes(freed)}"
            + (f" (план: {format_bytes(planned)})" if planned > 0 else "")
        )
        if failed:
            self._on_log(f"⚠️  Не удалось очистить целей: {failed}")
        if recycled > 0:
            self._on_log(
                f"🗑️  {format_bytes(recycled)} перемещено в корзину — "
                "место освободится после её очистки"
            )

        if results:
            self._save_history(results, freed)

        self._update_sel_label()
        self.tree.populate(self._all_cleaners)

        # Предложить сохранить отчёт
        if freed > 100_000_000 or planned > 100_000_000:
            if messagebox.askyesno("Отчёт", "Сохранить отчёт на рабочий стол?"):
                self._export_report(results, freed, planned)

    def _save_history(self, results: list[CleanResult], freed: int) -> None:
        """Сохранить операцию в SQLite (детали — JSON-список целей)."""
        try:
            payload = [
                {
                    "id": r.cleaner.id,
                    "name": r.cleaner.name,
                    "status": r.status,
                    "planned": r.planned,
                    "freed": r.freed,
                    "remaining": r.remaining,
                    "recycled": r.recycled,
                    "note": r.note,
                }
                for r in results
            ]
            HistoryManager().add_operation(payload, bytes_freed=freed, op_type="smart")
            log.info(
                "Очистка: целей %s, освобождено %s байт",
                len(results), freed,
            )
        except Exception as e:
            self._on_log(f"⚠️  История не сохранена: {e}")
            log.exception("Не удалось сохранить историю")

    # ── Preview ──────────────────────────────────────

    def show_preview(self) -> None:
        selected = self.tree.get_selected()
        previewable = [c for c in selected if c.can_preview and c.preview_path]
        if not previewable:
            self._on_log("ℹ️  Для выбранных целей предпросмотр недоступен.")
            return
        item = previewable[0]
        preview_path = item.preview_path or ""
        p = Path(preview_path)
        if not preview_path or not p.exists():
            self._on_log(f"ℹ️  Путь уже удалён: {item.preview_path}")
            return

        files: list[dict] = []
        try:
            for child in list(p.iterdir())[:50]:
                files.append({
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else 0,
                })
        except Exception:
            files = []

        text = f"📂 {item.preview_path}\n{'─'*50}\n"
        for f in files:
            icon = "📁" if f["is_dir"] else "📄"
            sz = format_bytes(f["size"]) if f["size"] > 0 else ""
            text += f"  {icon}  {f['name']}  {sz}\n"

        w = ctk.CTkToplevel(self)
        w.title(f"Предпросмотр: {item.name}")
        w.geometry("660x440")
        w.attributes("-topmost", True)
        w.configure(fg_color=self._theme.colors.SURFACE)
        t = MDTextbox(w, self._theme, font=FONT_MONO)
        t.pack(fill="both", expand=True, padx=18, pady=18)
        t.insert("1.0", text)
        t.configure(state="disabled")

    # ── Selection helpers ────────────────────────────

    def select_all(self) -> None:
        self.tree.select_all()
        self._update_sel_label()

    def deselect_all(self) -> None:
        self.tree.deselect_all()
        self._update_sel_label()

    def select_safe(self) -> None:
        """Отметить все безопасные цели."""
        self.tree.select_safe()
        self._update_sel_label()

    def focus_cleaner(self, cleaner_id: str) -> bool:
        """Выбрать конкретную цель (например, из Dashboard)."""
        target = next(
            (c for c in self._all_cleaners if c.id == cleaner_id), None
        )
        if target is None:
            return False

        if cleaner_id not in self.tree.get_visible_ids():
            # Цель скрыта в Easy-режиме — переключаемся на Advanced.
            self.mode_var.set("Advanced")
            self._on_mode_change("Advanced")

        if not self.tree.set_checked(cleaner_id, True):
            return False
        try:
            self.tree.tree.see(cleaner_id)
            self.tree.tree.selection_set(cleaner_id)
        except Exception:
            pass
        self._update_sel_label()
        return True

    def _update_sel_label(self) -> None:
        n = self.tree.get_selected_count()
        sz = self.tree.get_selected_total()
        self.sel_label.configure(text=f"Выбрано: {n} целей, {format_bytes(sz)}")

    # ── Custom rules ─────────────────────────────────

    def _add_custom_rule(self) -> None:
        w = ctk.CTkToplevel(self)
        w.title("Свой путь")
        w.geometry("500x320")
        w.attributes("-topmost", True)
        w.configure(fg_color=self._theme.colors.SURFACE)
        w.transient(self.winfo_toplevel())

        nv, pv = ctk.StringVar(), ctk.StringVar()

        MDLabel(
            w, self._theme, "Новое правило очистки", role="on_surface",
            font=FONT_HEADLINE, anchor="w",
        ).pack(fill="x", padx=22, pady=(20, 2))
        MDLabel(
            w, self._theme, "Укажите папку или файл, который нужно добавить в цели.",
            role="secondary", font=FONT_BODY, anchor="w",
        ).pack(fill="x", padx=22, pady=(0, 12))

        MDLabel(
            w, self._theme, "Название", role="secondary", font=FONT_LABEL, anchor="w",
        ).pack(fill="x", padx=22)
        MDEntry(w, self._theme, textvariable=nv).pack(fill="x", padx=22, pady=(2, 8))

        MDLabel(
            w, self._theme, "Путь", role="secondary", font=FONT_LABEL, anchor="w",
        ).pack(fill="x", padx=22)
        MDEntry(w, self._theme, textvariable=pv).pack(fill="x", padx=22, pady=(2, 2))

        error_label = MDLabel(
            w, self._theme, "", role="error", font=FONT_LABEL, anchor="w",
            wraplength=440, justify="left",
        )
        error_label.pack(fill="x", padx=22, pady=(4, 0))

        def save() -> None:
            name, path = nv.get().strip(), pv.get().strip()
            if not name:
                error_label.configure(text="Укажите название правила.")
                return
            error = validate_custom_path(path)
            if error:
                error_label.configure(text=error)
                return
            try:
                self._config.add_custom_rule(name, path)
            except ValueError as e:
                error_label.configure(text=str(e))
                return
            if self._on_reload:
                self._on_reload()
            w.destroy()
            self._on_log(f"Добавлено правило: {name}")
            self.start_scan()

        footer = ctk.CTkFrame(w, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=14)
        MDButton(
            footer, self._theme, "Сохранить", save,
            kind="filled", width=132,
        ).pack(side="right")
        MDButton(
            footer, self._theme, "Отмена", w.destroy,
            kind="text_muted", width=90,
        ).pack(side="right", padx=(0, 6))

    # ── Report ───────────────────────────────────────

    def _export_report(self, results: list[CleanResult], freed: int,
                       planned: int = 0) -> None:
        fn = f"diskcleaner_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
        fp = Path.home() / "Desktop" / fn
        try:
            with open(fp, "w", encoding="utf-8") as f:
                f.write("=" * 50 + "\n")
                f.write("  🧹 DiskCleaner Pro — Отчёт об очистке\n")
                f.write(f"  {datetime.datetime.now():%Y-%m-%d %H:%M}\n")
                f.write("=" * 50 + "\n\n")
                for r in results:
                    status = "✅" if r.status == "OK" else "❌"
                    f.write(f"{status} {r.cleaner.name}: {r.detail}\n")
                    if r.note:
                        f.write(f"   ⚠️  {r.note}\n")
                    f.write(
                        f"   План: {format_bytes(r.planned)} | "
                        f"Освобождено: {format_bytes(r.freed)} | "
                        f"Осталось: {format_bytes(r.remaining)}\n"
                    )
                f.write(f"\n{'─'*50}\n")
                f.write(f"✅ План: {format_bytes(planned)}\n")
                f.write(f"✅ Фактически освобождено: {format_bytes(freed)}\n")
            self._on_log(f"📄  Отчёт: {fp}")
        except Exception as e:
            self._on_log(f"❌  Ошибка сохранения отчёта: {e}")

    # ── Load cleaners ────────────────────────────────

    def load_cleaners(self, cleaners: list[BaseCleaner]) -> None:
        self._all_cleaners = cleaners
        self.tree.populate(cleaners)
        self._update_sel_label()

    # ── Theme / lifecycle ────────────────────────────

    def refresh_theme(self) -> None:
        self.tree.refresh_theme()
        try:
            self.mode_seg._buttons_dict["Easy"].configure(text="🟢  Easy")
            self.mode_seg._buttons_dict["Advanced"].configure(text="🔴  Advanced")
        except Exception:
            pass

    def destroy(self) -> None:
        try:
            self._ui.stop()
            self._scan_engine.shutdown()
        except Exception:
            pass
        try:
            self.search_var.trace_remove("write", self._search_trace)
        except Exception:
            pass
        super().destroy()
