"""ThemeManager — темы Material 3 и уведомление виджетов об изменении."""
from __future__ import annotations

import logging
import weakref
from typing import Any

import customtkinter as ctk

from disk_cleaner_app.ui.assets import DarkColors, LightColors

log = logging.getLogger(__name__)


def _blend(fg: str, bg: str, alpha: float) -> str:
    """Смешать два HEX-цвета. Полезно для state layer без прозрачности в Tk."""
    fg = fg.lstrip("#")
    bg = bg.lstrip("#")
    if len(fg) != 6 or len(bg) != 6:
        return f"#{fg}"
    alpha = max(0.0, min(1.0, alpha))
    channels = []
    for i in (0, 2, 4):
        a = int(fg[i:i + 2], 16)
        b = int(bg[i:i + 2], 16)
        channels.append(round(a * alpha + b * (1 - alpha)))
    return "#" + "".join(f"{value:02x}" for value in channels)


class ThemeManager:
    """Управляет темой, палитрой и списком виджетов для обновления."""

    def __init__(self, initial: str = "dark") -> None:
        self._mode = initial if initial in {"dark", "light", "system"} else "dark"
        self._listeners: list[weakref.ReferenceType[Any]] = []
        ctk.set_appearance_mode(self._mode)

    # ── режим ────────────────────────────────────────

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in {"dark", "light", "system"}:
            value = "dark"
        if value == self._mode:
            ctk.set_appearance_mode(value)
            return
        self._mode = value
        ctk.set_appearance_mode(value)
        self.notify()

    def set_mode(self, value: str) -> None:
        self.mode = value

    def toggle(self) -> str:
        """Переключить dark ↔ light (system превращается в light)."""
        self.mode = "light" if self.effective_mode == "dark" else "dark"
        return self._mode

    @property
    def effective_mode(self) -> str:
        if self._mode == "system":
            try:
                return "dark" if str(ctk.get_appearance_mode()).lower() == "dark" else "light"
            except Exception:
                return "light"
        return self._mode

    @property
    def is_dark(self) -> bool:
        return self.effective_mode == "dark"

    @property
    def colors(self):
        return DarkColors if self.is_dark else LightColors

    def theme_icon(self) -> str:
        return "☾" if self.is_dark else "☀"

    def theme_label(self) -> str:
        return "Тёмная тема" if self.is_dark else "Светлая тема"

    # ── подписчики ───────────────────────────────────

    def register(self, widget: Any) -> None:
        """Зарегистрировать виджет с методом ``refresh_theme``."""
        if not hasattr(widget, "refresh_theme"):
            return
        try:
            ref: weakref.ReferenceType[Any] = weakref.ref(widget)
        except TypeError:
            return
        self._listeners = [
            item for item in self._listeners
            if item() is not None and item() is not widget
        ]
        self._listeners.append(ref)

    def notify(self) -> None:
        """Обновить все живые зарегистрированные виджеты."""
        alive: list[weakref.ReferenceType[Any]] = []
        for ref in self._listeners:
            widget = ref()
            if widget is None:
                continue
            alive.append(ref)
            try:
                widget.refresh_theme()
            except Exception:
                # Уничтоженный/недорисованный виджет не должен ломать смену темы.
                log.debug("Не удалось обновить тему для %r", widget, exc_info=True)
        self._listeners = alive

    @staticmethod
    def blend(fg: str, bg: str, alpha: float) -> str:
        return _blend(fg, bg, alpha)
