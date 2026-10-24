"""📊 Disk Analyzer — анализ диска, Treemap с drill-down."""
from __future__ import annotations

import datetime
import os
import re
import threading
from functools import partial
from tkinter import Menu, messagebox

import customtkinter as ctk

from disk_cleaner_app.cleaners.base import reset_scan_cancel, set_scan_cancel
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.analyzer import (
    empty_scan_root,
    find_empty_folders,
    normalize_root,
    remove_empty_folders,
    scan_large_files,
    scan_top_folders,
)
from disk_cleaner_app.services.batch_delete import delete_many
from disk_cleaner_app.services.startup import StartupManager
from disk_cleaner_app.services.treemap import TreemapData
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
    MDLabel,
    MDTextbox,
    PageHeader,
)
from disk_cleaner_app.ui.components.treemap_canvas import TreemapCanvas
from disk_cleaner_app.ui.dispatch import UiDispatcher
from disk_cleaner_app.ui.theme import ThemeManager

PATH_RE = re.compile(r"[A-Za-z]:\\[^\n]*")


class AnalyzerView(ctk.CTkFrame):
    """Вкладка анализа диска с Treemap."""

    def __init__(self, parent, theme: ThemeManager, on_log, statusbar=None,
                 get_drive=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._on_log = on_log
        self._statusbar = statusbar
        self._get_drive = get_drive
        self._treemap_data = TreemapData()
        self._startup = StartupManager()
        self._cancel = threading.Event()
        self._is_scanning = False
        self._last_empty: list[str] = []
        self._last_text = ""
        self._last_mode = ""
        self._last_root = ""
        self._last_empty_root = ""
        self._cache: dict[
            tuple[str, str], tuple[datetime.datetime, str, list[str]]
        ] = {}
        self._ui = UiDispatcher(self)
        self._ui.start()
        self.configure(fg_color="transparent")
        self._build()

    def _drive_root(self) -> str:
        """Корень выбранного диска (по умолчанию системный)."""
        root = None
        if self._get_drive is not None:
            try:
                root = self._get_drive()
            except Exception:
                root = None
        return normalize_root(root)

    def _scan_root(self, mode: str) -> str:
        """Корень сканирования: для пустых папок — ``Users``, если есть."""
        base = self._drive_root()
        return empty_scan_root(base) if mode == "empty" else base

    def _cache_key(self, mode: str) -> tuple[str, str]:
        return (self._scan_root(mode), mode)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Анализ диска",
            "Крупные папки, файлы, пустые каталоги и treemap",
            icon="▤",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        self.refresh_btn = MDButton(
            header.actions, self._theme, "Обновить", self._refresh_analysis,
            kind="text_muted", width=94, height=34,
        )
        self.refresh_btn.pack(side="right", padx=(4, 0))

        self.cancel_btn = MDButton(
            header.actions, self._theme, "Стоп", self._cancel_analysis,
            kind="outlined", width=78, height=34, state="disabled",
        )
        self.cancel_btn.pack(side="right", padx=(4, 0))

        self.back_btn = MDButton(
            header.actions, self._theme, "Назад", self._treemap_back,
            kind="outlined", width=86, height=34, state="disabled",
        )
        self.back_btn.pack(side="right", padx=(4, 0))

        self.treemap_btn = MDButton(
            header.actions, self._theme,
            f"Treemap · {self._drive_root()}", self._show_treemap_root,
            kind="filled", width=170, height=34,
        )
        self.treemap_btn.pack(side="right")

        # ── Инструменты анализа ───────────────────────
        tools = MDCard(self, self._theme, tone="low")
        tools.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(tools, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(11, 5))

        MDLabel(
            row, self._theme, "Быстрый отчёт", role="muted",
            font=FONT_CAPTION,
        ).pack(side="left", padx=(0, 8))

        for text, cmd, kind, width in [
            ("Топ папок", "top", "tonal", 100),
            ("Файлы > 500 МБ", "big500", "outlined", 124),
            ("Файлы > 1 ГБ", "big1024", "outlined", 118),
            ("Пустые папки", "empty", "outlined", 118),
            ("Автозагрузка", "startup", "text", 106),
        ]:
            MDButton(
                row, self._theme, text, partial(self._run_analysis, cmd),
                kind=kind, width=width, height=32,
            ).pack(side="left", padx=(0, 6))

        self.remove_empty_btn = MDButton(
            row, self._theme, "Удалить пустые", self._remove_empty,
            kind="danger_text", width=126, height=32, state="disabled",
        )
        self.remove_empty_btn.pack(side="right")

        self.breadcrumb = MDLabel(
            tools, self._theme, "", role="muted", font=FONT_LABEL, anchor="w",
        )
        self.breadcrumb.pack(fill="x", padx=14, pady=(0, 10))
        self._update_breadcrumb(f"Диск: {self._drive_root()}")

        # ── Результаты ────────────────────────────────
        results = MDCard(self, self._theme, tone="low")
        results.grid(row=2, column=0, sticky="nsew")
        self._results_card = results

        self.pane = ctk.CTkFrame(results, fg_color="transparent")
        self.pane.pack(fill="both", expand=True, padx=12, pady=12)

        self.text_result = MDTextbox(
            self.pane, self._theme, font=FONT_MONO,
            fg_color=self._theme.colors.SURFACE_LOWEST,
        )
        self.text_result.pack(fill="both", expand=True)
        self.text_result.bind("<Button-3>", self._show_context_menu)
        self.text_result.insert(
            "1.0",
            "Выберите отчёт слева или постройте treemap.\n\n"
            "«Топ папок» — самые крупные каталоги,\n"
            "«Файлы > 500 МБ» и «Файлы > 1 ГБ» — тяжёлые файлы,\n"
            "«Пустые папки» — каталоги без файлов,\n"
            "«Автозагрузка» — программы в автозапуске Windows.",
        )
        self.text_result.configure(state="disabled")

        self.treemap_canvas = TreemapCanvas(
            self.pane,
            on_open_folder=self._on_treemap_drill,
            on_breadcrumb=lambda t: self._update_breadcrumb(t),
            theme=self._theme,
            bg=self._theme.colors.SURFACE_LOWEST,
        )

    # ── Analysis modes ──────────────────────────────

    def _run_analysis(self, mode: str, force: bool = False) -> None:
        """Запустить анализ в потоке (или показать кэш)."""
        if self._is_scanning:
            return

        root = self._scan_root(mode)
        key = (root, mode)
        self._last_mode = mode
        self._last_root = root
        if not force and key in self._cache:
            moment, text, empty = self._cache[key]
            self._last_text = text
            self._last_empty = empty
            self._show_text()
            self._show_text_result(text)
            self.remove_empty_btn.configure(
                state="normal" if mode == "empty" and empty else "disabled"
            )
            self._update_breadcrumb(
                f"📊 {mode} · {root} · кэш {moment.strftime('%H:%M')}"
            )
            if self._statusbar:
                self._statusbar.set_status(
                    f"✅  Из кэша ({moment.strftime('%H:%M')}) — «🔄 Обновить» для повтора"
                )
            return

        self._is_scanning = True
        self._cancel.clear()
        self.cancel_btn.configure(state="normal")
        self.remove_empty_btn.configure(state="disabled")
        self._last_empty = []
        self._show_text()
        self.text_result.configure(state="normal")
        self.text_result.delete("1.0", "end")
        self.text_result.insert("1.0", f"🔄 Сканирование {root}...")
        self.text_result.configure(state="disabled")
        self._update_breadcrumb(f"📊 {mode} · {root}")
        if self._statusbar:
            self._statusbar.set_status(f"🔄  Анализ диска {root}...")

        threading.Thread(
            target=lambda: self._analysis_worker(mode, root), daemon=True
        ).start()

    def _refresh_analysis(self) -> None:
        """Повторить последний анализ, минуя кэш."""
        if not self._last_mode:
            return
        self._run_analysis(self._last_mode, force=True)

    def set_drive(self, drive: str | None) -> None:
        """Переключить диск: сбросить кэш и обновить подписи."""
        self._cache.clear()
        root = normalize_root(drive)
        self.treemap_btn.configure(text=f"Treemap · {root}")
        self._update_breadcrumb(f"💽  Диск: {root}")
        if self._statusbar:
            self._statusbar.set_status(f"💽  Анализ: {root}")

    def _analysis_worker(self, mode: str, root: str) -> None:
        token = set_scan_cancel(self._cancel)
        text = ""
        empty: list[str] = []
        try:
            if mode == "top":
                text = f"📊  ТОП-50 ПАПОК · {root}\n" + "═" * 50 + "\n"
                folders = scan_top_folders(root, 50, cancel=self._cancel)
                for i, f in enumerate(folders, 1):
                    bar = "▓" * min(int(f["size"] / (1024**3)) + 1, 25)
                    text += (
                        f"{i:2d}. {f['name']:30s} {format_bytes(f['size']):>10s}  {bar}\n"
                        f"     📍 {f['path']}\n"
                    )
            elif mode.startswith("big"):
                mb = int(mode[3:])
                text = f"📄  ФАЙЛЫ >{mb} МБ · {root}\n" + "═" * 50 + "\n"
                files = scan_large_files(root, mb, 50, cancel=self._cancel)
                for i, f in enumerate(files, 1):
                    text += (
                        f"{i:2d}. {format_bytes(f['size']):>10s}  {f['name']}\n"
                        f"     📍 {f['path']}\n"
                    )
            elif mode == "empty":
                empty = find_empty_folders(root, cancel=self._cancel)
                text = (
                    f"📂  ПУСТЫЕ ПАПКИ · {root}: {len(empty)}\n"
                    + "═" * 50 + "\n"
                )
                for folder in empty[:60]:
                    text += f"  📁 {folder}\n"
                if len(empty) > 60:
                    text += f"  ... +{len(empty) - 60}\n"
            elif mode == "startup":
                items = self._startup.get_all()
                text = f"🚀  АВТОЗАГРУЗКА: {len(items)}\n" + "═" * 50 + "\n"
                for s in items:
                    text += f"  • {s.get('name', '?')} → {s.get('command', '')[:60]}\n"
        finally:
            reset_scan_cancel(token)

        if self._cancel.is_set():
            text = "⏹  Сканирование остановлено.\n\n" + text
        self._ui.post(self._finish_analysis, text, empty, mode, root)

    def _finish_analysis(
        self, text: str, empty: list[str], mode: str, root: str = ""
    ) -> None:
        self._is_scanning = False
        self.cancel_btn.configure(state="disabled")
        self._last_text = text
        self._last_empty = empty
        if root:
            self._last_root = root
        if mode == "empty":
            self._last_empty_root = root
        if not self._cancel.is_set():
            self._cache[(root, mode)] = (datetime.datetime.now(), text, empty)
        self._show_text_result(text)
        if mode == "empty":
            self.remove_empty_btn.configure(
                state="normal" if empty else "disabled"
            )

    def _cancel_analysis(self) -> None:
        if not self._is_scanning:
            return
        self._cancel.set()
        self.cancel_btn.configure(state="disabled")
        if self._statusbar:
            self._statusbar.set_status("⏹  Остановка анализа...")

    def _show_text_result(self, text: str) -> None:
        self.text_result.configure(state="normal")
        self.text_result.delete("1.0", "end")
        self.text_result.insert("1.0", text)
        self.text_result.configure(state="disabled")
        if self._statusbar:
            if self._cancel.is_set():
                self._statusbar.set_status("⏹  Анализ остановлен")
            else:
                self._statusbar.set_status("✅  Анализ завершён")

    # ── Пустые папки ────────────────────────────────

    def _remove_empty(self) -> None:
        if self._is_scanning or not self._last_empty:
            return
        count = len(self._last_empty)
        root = self._last_empty_root or self._scan_root("empty")
        if not messagebox.askyesno(
            "Пустые папки",
            f"Удалить {count} пустых папок?\n\n"
            "Удаляются только папки без файлов и подпапок.\n"
            f"Корень {root} защищён от удаления.",
        ):
            return

        self.remove_empty_btn.configure(state="disabled")
        folders = list(self._last_empty)

        def worker():
            removed, errors = remove_empty_folders(folders, root=root)
            self._ui.post(self._after_remove_empty, removed, errors)

        threading.Thread(target=worker, daemon=True).start()

    def _after_remove_empty(self, removed: int, errors: list[str]) -> None:
        self._on_log(f"📂  Удалено пустых папок: {removed}")
        for error in errors[:10]:
            self._on_log(f"⚠️  {error}")
        self._cache.clear()
        self._run_analysis("empty", force=True)

    # ── Контекстное меню ─────────────────────────────

    def _path_at_event(self, event) -> str | None:
        """Извлечь путь из строки под курсором."""
        text_widget = self.text_result._textbox
        index = text_widget.index(f"@{event.x},{event.y}")
        line = text_widget.get(f"{index} linestart", f"{index} lineend")
        match = PATH_RE.search(line)
        if not match:
            return None
        path = match.group(0).strip()
        return path or None

    def _show_context_menu(self, event) -> None:
        path = self._path_at_event(event)
        if not path:
            return
        exists = os.path.exists(path)
        c = self._theme.colors
        menu = Menu(
            self, tearoff=0,
            bg=c.SURFACE_HIGH, fg=c.ON_SURFACE,
            activebackground=c.SECONDARY_CONTAINER,
            activeforeground=c.ON_SECONDARY_CONTAINER,
            borderwidth=0, relief="flat", font=FONT_LABEL,
        )
        menu.add_command(
            label="📂  Открыть в проводнике",
            command=lambda: self._open_path(path),
            state="normal" if exists else "disabled",
        )
        menu.add_command(
            label="📋  Копировать путь",
            command=lambda: self._copy_path(path),
        )
        if exists and os.path.isfile(path):
            menu.add_command(
                label="🗑️  Переместить в корзину",
                command=lambda: self._recycle_path(path),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_path(self, path: str) -> None:
        try:
            if os.path.isdir(path):
                os.startfile(path)
            else:
                os.startfile(os.path.dirname(path))
        except OSError as e:
            self._on_log(f"⚠️  Не удалось открыть: {e}")

    def _copy_path(self, path: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(path)
            if self._statusbar:
                self._statusbar.set_status(f"📋  Скопировано: {path}")
        except Exception:
            pass

    def _recycle_path(self, path: str) -> None:
        if not messagebox.askyesno(
            "Корзина", f"Переместить в корзину?\n\n{path}"
        ):
            return
        result = delete_many([path], to_recycle=True)
        if result["deleted"]:
            self._on_log(f"🗑️  В корзину: {path}")
            self._cache.clear()
            self._run_analysis("big500", force=True)
        else:
            self._on_log(f"⚠️  Не удалось переместить: {path}")

    # ── Treemap ─────────────────────────────────────

    def _show_treemap_root(self) -> None:
        """Показать treemap для выбранного диска."""
        root = self._drive_root()
        self._update_breadcrumb(f"🗺️  {root}")
        self._hide_text()
        self.treemap_canvas.delete("all")
        self.back_btn.configure(state="disabled")
        self._on_log(f"🗺️  Загрузка treemap: {root}")

        def worker():
            nodes = self._treemap_data.scan_root(root, 30)
            self._ui.post(self._draw_treemap, nodes)

        threading.Thread(target=worker, daemon=True).start()

    def _on_treemap_drill(self, path: str) -> None:
        """Drill-down в папку."""
        self._update_breadcrumb(f"🗺️  {path}")
        self._on_log(f"📂  Открываю: {path}")

        def worker():
            # Ищем узел по пути
            for node_list in [self._treemap_data._history[-1]] if self._treemap_data._history else []:
                for n in node_list:
                    if n.path == path and n.is_dir:
                        children = self._treemap_data.drill_down(n, 30)
                        self._ui.post(self._draw_treemap, children)
                        self._ui.post(lambda: self.back_btn.configure(state="normal"))
                        return
            # Если нет — открываем папку
            try:
                os.startfile(path)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _treemap_back(self) -> None:
        """Вернуться на уровень выше."""
        nodes = self._treemap_data.go_back(30)
        if nodes:
            self._draw_treemap(nodes)
        if not self._treemap_data.can_go_back():
            self.back_btn.configure(state="disabled")

    def _draw_treemap(self, nodes) -> None:
        self.treemap_canvas.draw(nodes)
        if self._statusbar:
            self._statusbar.set_status(f"🗺️  {len(nodes)} элементов")

    # ── Helpers ─────────────────────────────────────

    def _show_text(self) -> None:
        self.treemap_canvas.pack_forget()
        self.text_result.pack(fill="both", expand=True)

    def _hide_text(self) -> None:
        self.text_result.pack_forget()
        self.treemap_canvas.pack(fill="both", expand=True)

    def _update_breadcrumb(self, text: str) -> None:
        self.breadcrumb.configure(text=text)

    def refresh_theme(self) -> None:
        c = self._theme.colors
        self.text_result.configure(
            fg_color=c.SURFACE_LOWEST, text_color=c.ON_SURFACE_VARIANT,
        )
        self.treemap_canvas.configure(bg=c.SURFACE_LOWEST)

    def destroy(self) -> None:
        try:
            self._cancel.set()
            self._ui.stop()
        except Exception:
            pass
        super().destroy()
