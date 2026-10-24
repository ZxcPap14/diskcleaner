"""DiskGauge — кольцевой индикатор занятости диска в стиле MD3."""
from __future__ import annotations

import tkinter as tk
from typing import Any

from disk_cleaner_app.ui.theme import ThemeManager


class DiskGauge(tk.Canvas):
    """Круговой индикатор: тонкое кольцо, крупное значение, подпись."""

    def __init__(
        self,
        parent: Any,
        size: int = 156,
        theme: ThemeManager | None = None,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        self._size = size
        self._free = 0
        self._total = 0
        super().__init__(
            parent, width=size, height=size,
            highlightthickness=0, bd=0, **kwargs,
        )
        if theme is not None:
            theme.register(self)

    # ── данные ────────────────────────────────────────

    def set_values(self, free: int, total: int) -> None:
        self._free = max(0, int(free))
        self._total = max(0, int(total))
        self._draw()

    def refresh_theme(self) -> None:
        if self._theme is not None:
            self.configure(bg=self._theme.colors.SURFACE_LOW)
        self._draw()

    # ── отрисовка ─────────────────────────────────────

    def _draw(self) -> None:
        self.delete("all")
        c = self._theme.colors if self._theme is not None else None
        on_surface = c.ON_SURFACE if c else "#f0f0ff"
        variant = c.ON_SURFACE_VARIANT if c else "#9090b0"
        track = c.SURFACE_HIGHEST if c else "#2a2a50"
        accent = c.PRIMARY if c else "#6ee7b7"

        pad = 12
        cx = cy = self._size // 2
        radius = self._size // 2 - pad
        box = (cx - radius, cy - radius, cx + radius, cy + radius)

        self.create_oval(
            *[coord for coord in box], outline=track, width=13,
        )

        if self._total <= 0:
            self.create_text(
                cx, cy - 4, text="—", fill=on_surface,
                font=("Segoe UI", 18, "bold"),
            )
            self.create_text(
                cx, cy + 18, text="нет данных", fill=variant,
                font=("Segoe UI", 9),
            )
            return

        used = self._total - self._free
        ratio = max(0.0, min(1.0, used / self._total))
        if ratio > 0:
            self.create_arc(
                *box, start=90, extent=-359.9 * ratio,
                style=tk.ARC, outline=accent, width=13,
            )

        used_gb = used / (1024 ** 3)
        total_gb = self._total / (1024 ** 3)
        self.create_text(
            cx, cy - 10, text=f"{used_gb:.1f}", fill=on_surface,
            font=("Segoe UI", 22, "bold"),
        )
        self.create_text(
            cx, cy + 13, text=f"ГБ из {total_gb:.1f}", fill=variant,
            font=("Segoe UI", 9),
        )
        self.create_text(
            cx, cy + 36, text=f"{ratio * 100:.0f}% занято", fill=accent,
            font=("Segoe UI", 8, "bold"),
        )
