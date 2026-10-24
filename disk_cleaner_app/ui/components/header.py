"""HeaderBar — верхний app bar в стиле Material Design 3."""
from __future__ import annotations

import customtkinter as ctk

from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.ui.assets import (
    FONT_CAPTION,
    FONT_HEADLINE_SMALL,
    FONT_LABEL,
    RADIUS_FULL,
    SPACE_2,
)
from disk_cleaner_app.ui.components.md3 import MDIconButton, MDProgress
from disk_cleaner_app.ui.theme import ThemeManager


class HeaderBar(ctk.CTkFrame):
    """App bar: бренд, состояние диска, статистика и быстрые действия."""

    def __init__(
        self,
        parent: ctk.CTk,
        theme: ThemeManager,
        on_theme_toggle,
        on_settings,
        on_elevate=None,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._theme = theme
        self._on_theme_toggle = on_theme_toggle
        self._on_settings = on_settings
        self._on_elevate = on_elevate
        self._admin = False

        self._build()
        theme.register(self)

    def _build(self) -> None:
        c = self._theme.colors

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="y")

        self._logo = ctk.CTkFrame(
            left, width=42, height=42, corner_radius=14,
            fg_color=c.PRIMARY_CONTAINER,
        )
        self._logo.pack(side="left", pady=15)
        self._logo.pack_propagate(False)
        self._logo_label = ctk.CTkLabel(
            self._logo, text="🧹", font=("Segoe UI", 18),
            text_color=c.ON_PRIMARY_CONTAINER,
        )
        self._logo_label.place(relx=0.5, rely=0.5, anchor="center")

        brand = ctk.CTkFrame(left, fg_color="transparent")
        brand.pack(side="left", padx=(10, 0))
        self._brand = ctk.CTkLabel(
            brand, text="DiskCleaner Pro", font=FONT_HEADLINE_SMALL,
            text_color=c.ON_SURFACE, anchor="w",
        )
        self._brand.pack(anchor="w")
        self._tagline = ctk.CTkLabel(
            brand, text="Чистый диск. Спокойная система.",
            font=FONT_CAPTION, text_color=c.ON_SURFACE_VARIANT, anchor="w",
        )
        self._tagline.pack(anchor="w")

        # ── Правая часть ──────────────────────────────
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(side="right", fill="y")

        self.theme_btn = MDIconButton(
            actions, self._theme, self._theme.theme_icon(),
            command=self._on_theme_toggle, kind="standard",
            font=("Segoe UI", 16),
        )
        self.theme_btn.pack(side="right", padx=(4, 0))

        self.admin_btn = MDIconButton(
            actions, self._theme, "⛨",
            command=self._on_elevate or (lambda: None), kind="standard",
            font=("Segoe UI", 16),
        )
        self.admin_btn.pack(side="right", padx=(4, 0))

        self.settings_btn = MDIconButton(
            actions, self._theme, "⚙",
            command=self._on_settings, kind="standard",
            font=("Segoe UI", 16),
        )
        self.settings_btn.pack(side="right", padx=(4, 0))

        self._history_pill = ctk.CTkFrame(
            actions, fg_color=c.SURFACE_LOW, corner_radius=RADIUS_FULL,
            height=34,
        )
        self._history_pill.pack(side="right", padx=(0, 10), pady=19)
        self._history_icon = ctk.CTkLabel(
            self._history_pill, text="↑", font=("Segoe UI", 12, "bold"),
            text_color=c.SUCCESS,
        )
        self._history_icon.pack(side="left", padx=(12, 2), pady=5)
        self._hist_caption = ctk.CTkLabel(
            self._history_pill, text="очищено", font=FONT_CAPTION,
            text_color=c.ON_SURFACE_VARIANT,
        )
        self._hist_caption.pack(side="left")
        self.hist_label = ctk.CTkLabel(
            self._history_pill, text="0 Б", font=FONT_LABEL,
            text_color=c.ON_SURFACE,
        )
        self.hist_label.pack(side="left", padx=(5, 12))

        # ── Центральная часть: состояние диска ────────
        self._disk_panel = ctk.CTkFrame(
            self, fg_color=c.SURFACE_LOW, corner_radius=RADIUS_FULL,
            height=42,
        )
        self._disk_panel.pack(side="left", fill="x", expand=True, padx=SPACE_2 * 5, pady=15)
        self._disk_panel.pack_propagate(False)

        self._disk_icon = ctk.CTkLabel(
            self._disk_panel, text="◉", font=("Segoe UI", 13),
            text_color=c.PRIMARY,
        )
        self._disk_icon.pack(side="left", padx=(16, 6))
        self.disk_label = ctk.CTkLabel(
            self._disk_panel, text="Чтение диска…", font=FONT_LABEL,
            text_color=c.ON_SURFACE_VARIANT, anchor="w",
        )
        self.disk_label.pack(side="left", fill="x", expand=True)

        self.disk_bar = MDProgress(self._disk_panel, self._theme, height=5)
        self.disk_bar.pack(side="right", padx=(8, 16), ipadx=0)
        self.disk_bar.configure(width=120)
        self.disk_bar.set(0)

    # ── данные ────────────────────────────────────────

    def update_disk(self, free: int, total: int) -> None:
        if total <= 0:
            return
        usage = 1 - free / total
        self.disk_bar.set(max(0.0, min(1.0, usage)))
        self.disk_label.configure(
            text=f"Свободно {free / 1024**3:.1f} ГБ  ·  занято "
                 f"{(total - free) / 1024**3:.1f} из {total / 1024**3:.1f} ГБ"
        )

    def update_history(self, total_freed: int) -> None:
        self.hist_label.configure(text=format_bytes(total_freed))

    def set_admin_status(self, admin: bool) -> None:
        self._admin = bool(admin)
        self._paint_admin()

    def _paint_admin(self) -> None:
        c = self._theme.colors
        if self._admin:
            self.admin_btn.configure(
                text="⛨", text_color=c.SUCCESS, hover_color=c.STATE_HOVER,
            )
        else:
            self.admin_btn.configure(
                text="⛨", text_color=c.ON_SURFACE_VARIANT, hover_color=c.STATE_HOVER,
            )

    def refresh_theme(self) -> None:
        c = self._theme.colors
        self._logo.configure(fg_color=c.PRIMARY_CONTAINER)
        self._logo_label.configure(text_color=c.ON_PRIMARY_CONTAINER)
        self._brand.configure(text_color=c.ON_SURFACE)
        self._tagline.configure(text_color=c.ON_SURFACE_VARIANT)
        self._history_pill.configure(fg_color=c.SURFACE_LOW)
        self._history_icon.configure(text_color=c.SUCCESS)
        self._hist_caption.configure(text_color=c.ON_SURFACE_VARIANT)
        self.hist_label.configure(text_color=c.ON_SURFACE)
        self._disk_panel.configure(fg_color=c.SURFACE_LOW)
        self._disk_icon.configure(text_color=c.PRIMARY)
        self.disk_label.configure(text_color=c.ON_SURFACE_VARIANT)
        self.theme_btn.configure(text=self._theme.theme_icon())
        self._paint_admin()
