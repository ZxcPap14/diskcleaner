"""Диалог слоя E: крупные файлы — показать, объяснить, открыть папку."""
from __future__ import annotations

import os
import threading
from collections.abc import Callable

import customtkinter as ctk

from disk_cleaner_app.cleaners.base import list_drives
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.large_files import (
    format_age,
    format_modified,
    plural_files,
    reveal_in_explorer,
    scan_large_files,
)
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_LABEL,
    FONT_LABEL_LARGE,
    FONT_MONO_SMALL,
)
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDLabel,
    MDOptionMenu,
    MDPill,
    MDProgress,
    MDScrollArea,
)
from disk_cleaner_app.ui.dispatch import UiDispatcher
from disk_cleaner_app.ui.theme import ThemeManager

_RECYCLE = 50


def _short_path(path: str, limit: int = 60) -> str:
    return path if len(path) <= limit else "…" + path[-(limit - 1):]


class LargeFilesDialog(ctk.CTkToplevel):
    """Топ крупных файлов на диске. Ничего не удаляет и не предлагает удалить."""

    MIN_SIZES: tuple[tuple[str, int], ...] = (
        ("100 МБ", 100),
        ("500 МБ", 500),
        ("1 ГБ", 1024),
        ("5 ГБ", 5120),
    )

    def __init__(
        self,
        parent,
        theme: ThemeManager,
        *,
        drive: str | None = None,
        on_log: Callable[[str], None] | None = None,
        scanner: Callable[..., list[dict]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._on_log = on_log
        self._scanner = scanner or scan_large_files
        self._cancel = threading.Event()
        self._scanning = False
        self._ui = UiDispatcher(self)
        self._ui.start()

        self._drives: dict[str, str] = {}
        self._drive_default = self._drive_label(drive)

        self.title("Крупные файлы — только показ")
        self.geometry("800x600")
        self.minsize(620, 440)
        self.configure(fg_color=theme.colors.SURFACE)
        self.transient(parent.winfo_toplevel())
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()
        theme.register(self)
        self.after(200, self.start_scan)

    # ── сборка ────────────────────────────────────────

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 8))

        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        MDLabel(
            titles, self._theme, "Крупные файлы", role="on_surface",
            font=FONT_LABEL_LARGE, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            titles, self._theme,
            "Крупнейшие файлы выбранного диска. Это могут быть ваши данные — "
            "приложение их не удаляет.",
            role="secondary", font=FONT_BODY, anchor="w", justify="left",
            wraplength=420,
        ).pack(anchor="w", pady=(2, 0))

        MDPill(
            head, self._theme, "слой E · только показ", icon="👁",
            tone="secondary_container",
        ).pack(side="right", padx=(8, 0))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=18, pady=(0, 4))

        self.drive_menu = MDOptionMenu(
            toolbar, self._theme, values=list(self._drives) or ["C:\\"],
            width=250, command=lambda _v: None,
        )
        self.drive_menu.pack(side="left")
        if self._drive_default in self._drives:
            self.drive_menu.set(self._drive_default)

        self.min_menu = MDOptionMenu(
            toolbar, self._theme, values=[label for label, _ in self.MIN_SIZES],
            width=110,
        )
        self.min_menu.pack(side="left", padx=(8, 0))
        self.min_menu.set("500 МБ")

        self.stop_btn = MDButton(
            toolbar, self._theme, "Стоп", self.stop_scan,
            kind="outlined", width=76, height=32, state="disabled",
        )
        self.stop_btn.pack(side="right")

        self.scan_btn = MDButton(
            toolbar, self._theme, "Найти", self.start_scan,
            kind="filled", width=100, height=32,
        )
        self.scan_btn.pack(side="right", padx=(0, 6))

        self.summary = MDLabel(
            self, self._theme, "Готов к поиску.", role="secondary",
            font=FONT_CAPTION, anchor="w",
        )
        self.summary.pack(fill="x", padx=18, pady=(0, 4))

        self.progress_holder = ctk.CTkFrame(self, fg_color="transparent")
        self.progress = MDProgress(self.progress_holder, self._theme, height=4)
        self.progress.pack(fill="x")
        self.progress.set(0)

        self.results = MDScrollArea(self, self._theme)
        self.results.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        self._placeholder(
            "Нажмите «Найти», чтобы увидеть крупнейшие файлы на выбранном диске."
        )

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(4, 14))

        MDLabel(
            footer, self._theme,
            "Слой E ничего не удаляет: откройте папку и решите сами.",
            role="muted", font=FONT_CAPTION, anchor="w",
        ).pack(side="left")

        MDButton(
            footer, self._theme, "Закрыть", self._close,
            kind="text_muted", width=90, height=32,
        ).pack(side="right")

    def _drive_label(self, drive: str | None) -> str:
        """Собрать подписи дисков и вернуть подпись выбранного."""
        target = (drive or os.environ.get("SystemDrive", "C:")).rstrip("\\/") + "\\"
        for root, free, _total in list_drives():
            self._drives[f"{root}  ·  {format_bytes(free)} свободно"] = root

        for label, root in self._drives.items():
            if os.path.normcase(root) == os.path.normcase(target):
                return label

        self._drives[target] = target
        return target

    # ── сканирование ──────────────────────────────────

    def start_scan(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._cancel.clear()
        self.scan_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.summary.configure(text="Сканирую диск… Обычно это занимает до двух минут.")
        self.progress_holder.pack(
            fill="x", padx=18, pady=(0, 6), after=self.summary,
        )
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._clear_results()

        root = self._drives.get(self.drive_menu.get(), self._drives.get(self._drive_default, "C:\\"))
        min_mb = dict(self.MIN_SIZES).get(self.min_menu.get(), 500)
        threading.Thread(
            target=self._worker, args=(root, min_mb), daemon=True,
            name="large-files-scan",
        ).start()

    def _worker(self, root: str, min_mb: int) -> None:
        try:
            files = self._scanner(
                root, min_mb, _RECYCLE, cancel=self._cancel,
            )
        except Exception as exc:  # сканер не должен ронять окно
            self._ui.post(self._finish, [], str(exc), min_mb)
            return
        self._ui.post(self._finish, files, "", min_mb)

    def stop_scan(self) -> None:
        if self._scanning:
            self._cancel.set()
            self.summary.configure(text="Останавливаю…")
            self.stop_btn.configure(state="disabled")

    def _finish(self, files: list[dict], error: str, min_mb: int) -> None:
        self._scanning = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self.progress_holder.pack_forget()
        self.scan_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

        if error:
            self.summary.configure(text=f"Ошибка сканирования: {error}")
            self._placeholder("Не удалось получить список файлов.")
            return
        if not files:
            self.summary.configure(text=f"Файлов ≥ {min_mb} МБ не найдено.")
            self._placeholder(
                "Попробуйте меньший порог — например, 100 МБ."
            )
            return

        total = sum(int(item.get("size", 0)) for item in files)
        self.summary.configure(
            text=(
                f"Найдено {len(files)} {plural_files(len(files))} ≥ {min_mb} МБ"
                f" · всего {format_bytes(total)}"
            )
        )
        self._render(files)
        if self._on_log is not None:
            self._on_log(f"🔎  Крупные файлы: {len(files)} шт., {format_bytes(total)}.")

    # ── список ────────────────────────────────────────

    def _clear_results(self) -> None:
        for child in self.results.winfo_children():
            child.destroy()

    def _placeholder(self, text: str) -> None:
        self._clear_results()
        MDLabel(
            self.results, self._theme, text, role="muted",
            font=FONT_BODY, anchor="center", justify="center",
        ).pack(fill="x", padx=16, pady=24)

    def _render(self, files: list[dict]) -> None:
        self._clear_results()
        for item in files:
            self._add_row(item)

    def _add_row(self, item: dict) -> None:
        row = ctk.CTkFrame(self.results, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=3)
        row.grid_columnconfigure(0, weight=1)

        text = ctk.CTkFrame(row, fg_color="transparent")
        text.grid(row=0, column=0, sticky="ew")
        MDLabel(
            text, self._theme, str(item.get("name", "?")),
            role="on_surface", font=FONT_LABEL, anchor="w",
        ).pack(fill="x")
        MDLabel(
            text, self._theme, _short_path(str(item.get("path", ""))),
            role="muted", font=FONT_MONO_SMALL, anchor="w",
        ).pack(fill="x")

        modified = float(item.get("modified", 0) or 0)
        meta = ctk.CTkFrame(row, fg_color="transparent")
        meta.grid(row=0, column=1, sticky="e", padx=(10, 8))
        MDLabel(
            meta, self._theme, format_bytes(int(item.get("size", 0))),
            role="secondary", font=FONT_LABEL, anchor="e", width=82,
        ).pack(anchor="e")
        MDLabel(
            meta, self._theme, f"{format_modified(modified)} · {format_age(modified)}",
            role="muted", font=FONT_CAPTION, anchor="e",
        ).pack(anchor="e")

        path = str(item.get("path", ""))
        MDButton(
            row, self._theme, "Открыть",
            lambda _p=path: self._reveal(_p),
            kind="text", width=96, height=30,
        ).grid(row=0, column=2, sticky="e")

    def _reveal(self, path: str) -> None:
        if not reveal_in_explorer(path):
            self.summary.configure(text="Не удалось открыть проводник.")
            return
        if self._on_log is not None:
            self._on_log(f"📂  Открыта папка файла: {path}")

    # ── закрытие и тема ───────────────────────────────

    def _close(self) -> None:
        self._cancel.set()
        self._ui.stop()
        self.destroy()

    def refresh_theme(self) -> None:
        self.configure(fg_color=self._theme.colors.SURFACE)
