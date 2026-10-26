"""UsageTrendChart — линия свободного места по дням (Canvas, как в истории)."""
from __future__ import annotations

from typing import Any

import customtkinter as ctk

from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.ui.assets import FONT_CAPTION

# Точки старше этого возраста рисуются реже (метки месяцев).
_MAX_LABELS = 6


class UsageTrendChart(ctk.CTkCanvas):
    """Линия свободного места по снапшотам; подписи дат под осью."""

    def __init__(self, parent: Any, theme: Any, height: int = 120, **kwargs: Any):
        self._theme = theme
        self._points: list[tuple[str, int]] = []
        super().__init__(
            parent, height=height, bg=theme.colors.SURFACE_LOW,
            highlightthickness=0, bd=0, **kwargs,
        )
        self.bind("<Configure>", lambda _e: self.redraw())
        theme.register(self)

    # ── данные ────────────────────────────────────────

    def set_series(self, points: list[tuple[str, int]]) -> None:
        """Точки по возрастанию: (метка даты «DD.MM», свободно_байт)."""
        self._points = [(str(label), max(0, int(free))) for label, free in points]
        self.redraw()

    def refresh_theme(self) -> None:
        self.configure(bg=self._theme.colors.SURFACE_LOW)
        self.redraw()

    # ── отрисовка ─────────────────────────────────────

    def redraw(self) -> None:
        canvas = self
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 60 or height < 40:
            return

        c = self._theme.colors
        if len(self._points) < 2:
            canvas.create_text(
                width / 2, height / 2,
                text="Недостаточно данных — история занятости собирается",
                fill=c.ON_SURFACE_VARIANT, font=FONT_CAPTION,
            )
            return

        values = [free for _label, free in self._points]
        low, high = min(values), max(values)
        if high - low < 1024:  # меньше килобайта разброса — плоско
            low = high - 1024
        pad = (high - low) * 0.08 or 1

        top = 8
        baseline = height - 16
        span = width - 12
        step = span / (len(self._points) - 1)

        def y_for(value: float) -> float:
            ratio = (value - low + pad) / (high - low + 2 * pad)
            return baseline - (baseline - top) * ratio

        coords: list[float] = []
        for index, (_label, free) in enumerate(self._points):
            coords.extend([4 + step * index, y_for(free)])
        canvas.create_line(*coords, fill=c.PRIMARY, width=2, smooth=True)

        # Заливка под линией.
        polygon = [coords[0], baseline, *coords, coords[-2], baseline]
        canvas.create_polygon(
            *polygon, fill=c.PRIMARY, outline="", stipple="gray25",
        )

        # Метки дат: равномерно, не чаще _MAX_LABELS.
        label_step = max(1, len(self._points) // _MAX_LABELS)
        for index in range(0, len(self._points), label_step):
            label, _free = self._points[index]
            x = 4 + step * index
            canvas.create_text(
                x, baseline + 3, anchor="n", text=label,
                fill=c.ON_SURFACE_VARIANT, font=FONT_CAPTION,
            )

        canvas.create_line(
            0, baseline, width, baseline, fill=c.OUTLINE_VARIANT,
        )
        # Крайние значения по вертикали.
        canvas.create_text(
            width - 4, top, anchor="e", text=format_bytes(high),
            fill=c.ON_SURFACE_VARIANT, font=FONT_CAPTION,
        )
        canvas.create_text(
            width - 4, baseline - 4, anchor="s", text=format_bytes(low),
            fill=c.ON_SURFACE_VARIANT, font=FONT_CAPTION,
        )
