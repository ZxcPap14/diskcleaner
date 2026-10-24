"""StatusBar — нижняя панель статуса и журнала в стиле MD3."""
from __future__ import annotations

import datetime

import customtkinter as ctk

from disk_cleaner_app.ui.assets import FONT_LABEL, FONT_MONO_SMALL, RADIUS_LG
from disk_cleaner_app.ui.components.md3 import MDButton, MDProgress, MDTextbox
from disk_cleaner_app.ui.theme import ThemeManager


class StatusBar(ctk.CTkFrame):
    """Компактная строка состояния с раскрываемым журналом."""

    def __init__(self, parent, theme: ThemeManager, **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        c = theme.colors
        self.configure(
            fg_color=c.SURFACE_LOW,
            corner_radius=RADIUS_LG,
            border_width=0,
        )

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(7, 5))

        self.status_label = ctk.CTkLabel(
            row, text="●  Готов к работе", font=FONT_LABEL,
            text_color=c.ON_SURFACE_VARIANT, anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.progress_label = ctk.CTkLabel(
            row, text="", font=("Segoe UI", 8), text_color=c.TEXT_MUTED,
        )
        self.progress_label.pack(side="right", padx=(10, 0))

        self.progress = MDProgress(row, theme, height=5)
        self.progress.configure(width=180)
        self.progress.pack(side="right", padx=(10, 0))
        self.progress.set(0)

        self.log_toggle = MDButton(
            row, theme, "Журнал", self._toggle_log,
            kind="text_muted", width=80, height=28,
        )
        self.log_toggle.pack(side="right", padx=(6, 0))

        self.log_text = MDTextbox(
            self, theme, height=92, font=FONT_MONO_SMALL,
        )

        theme.register(self)

    def _toggle_log(self) -> None:
        if self.log_text.winfo_viewable():
            self.log_text.pack_forget()
            self.log_toggle.configure(text="Журнал")
        else:
            self.log_text.pack(fill="x", padx=14, pady=(0, 10))
            self.log_toggle.configure(text="Скрыть")

    def log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_status(self, text: str, color=None) -> None:
        c = self._theme.colors
        self.status_label.configure(text=text, text_color=color or c.ON_SURFACE_VARIANT)

    def set_progress(self, value: float, label: str = "") -> None:
        self.progress.set(max(0.0, min(1.0, value)))
        self.progress_label.configure(text=label)

    def refresh_theme(self) -> None:
        c = self._theme.colors
        self.configure(fg_color=c.SURFACE_LOW)
        self.status_label.configure(text_color=c.ON_SURFACE_VARIANT)
        self.progress_label.configure(text_color=c.TEXT_MUTED)
