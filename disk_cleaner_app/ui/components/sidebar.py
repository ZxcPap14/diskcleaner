"""NavigationSidebar — navigation rail в стиле Material Design 3."""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from disk_cleaner_app.ui.assets import FONT_SMALL, RADIUS_SM, SIDEBAR_WIDTH
from disk_cleaner_app.ui.theme import ThemeManager


class _NavItem(ctk.CTkFrame):
    """Один пункт navigation rail: pill с иконкой и подпись под ним."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        theme: ThemeManager,
        icon: str,
        label: str,
        view_id: str,
        on_click: Callable[[str], None],
    ) -> None:
        super().__init__(
            parent,
            fg_color="transparent",
            corner_radius=14,
            height=44,
            cursor="hand2",
        )
        self._theme = theme
        self._icon_text = icon
        self._label_text = label
        self._view_id = view_id
        self._on_click = on_click
        self._active = False
        self._hover = False
        self.pack_propagate(False)

        self._pill = ctk.CTkFrame(
            self, width=40, height=28, corner_radius=RADIUS_SM,
            fg_color="transparent",
        )
        self._pill.pack(pady=(3, 0))
        self._pill.pack_propagate(False)
        # Индикатор активного раздела — акцентная полоска слева, как в WinUI.
        self._bar = ctk.CTkFrame(
            self, width=3, corner_radius=2, fg_color="transparent",
        )
        self._bar.place(x=0, rely=0.5, anchor="w", relheight=0.5)
        self._icon = ctk.CTkLabel(
            self._pill, text=icon, font=("Segoe UI", 13),
            text_color=theme.colors.ON_SURFACE_VARIANT,
        )
        self._icon.place(relx=0.5, rely=0.5, anchor="center")

        self._label = ctk.CTkLabel(
            self, text=label, font=FONT_SMALL,
            text_color=theme.colors.ON_SURFACE_VARIANT,
        )
        self._label.pack(pady=(0, 1))

        for widget in (self, self._pill, self._icon, self._label):
            widget.bind("<Button-1>", self._clicked)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

        theme.register(self)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply()

    def _clicked(self, _event=None) -> None:
        self._on_click(self._view_id)

    def _enter(self, _event=None) -> None:
        self._hover = True
        self._apply()

    def _leave(self, _event=None) -> None:
        self._hover = False
        self._apply()

    def _apply(self) -> None:
        c = self._theme.colors
        if self._active:
            pill = c.STATE_SELECTED
            icon = c.PRIMARY
            label = c.ON_SURFACE
            bar = c.PRIMARY
        elif self._hover:
            pill = c.STATE_HOVER
            icon = c.ON_SURFACE
            label = c.ON_SURFACE
            bar = "transparent"
        else:
            pill = "transparent"
            icon = c.ON_SURFACE_VARIANT
            label = c.ON_SURFACE_VARIANT
            bar = "transparent"
        self.configure(fg_color="transparent")
        self._pill.configure(fg_color=pill)
        self._bar.configure(fg_color=bar)
        self._icon.configure(text_color=icon)
        self._label.configure(text_color=label)

    def refresh_theme(self) -> None:
        self._apply()


class NavigationSidebar(ctk.CTkFrame):
    """Боковая навигация с 10 разделами."""

    ITEMS = [
        ("⌂", "dashboard", "Главная"),
        ("✦", "clean", "Очистка"),
        ("◈", "deep", "Глубокая"),
        ("▤", "analyzer", "Анализ"),
        ("◉", "disks", "Диски"),
        ("⧉", "duplicates", "Дубликаты"),
        ("≡", "history", "История"),
        ("↗", "startup", "Автозагрузка"),
        ("⊖", "uninstaller", "Удаление"),
        ("⚙", "settings", "Настройки"),
    ]

    def __init__(
        self,
        parent: ctk.CTk,
        theme: ThemeManager,
        on_navigate: Callable[[str], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._on_navigate = on_navigate
        self._active = "dashboard"
        self._items: dict[str, _NavItem] = {}

        self.configure(
            fg_color=theme.colors.SURFACE_CONTAINER,
            width=SIDEBAR_WIDTH,
            corner_radius=0,
            border_width=0,
        )
        self.pack_propagate(False)
        self._build()
        theme.register(self)

    def _build(self) -> None:
        c = self._theme.colors
        ctk.CTkLabel(
            self,
            text="МЕНЮ",
            font=("Segoe UI", 8, "bold"),
            text_color=c.TEXT_MUTED,
        ).pack(pady=(10, 4))

        for icon, view_id, label in self.ITEMS:
            item = _NavItem(self, self._theme, icon, label, view_id, self._navigate)
            item.pack(fill="x", padx=10, pady=0)
            self._items[view_id] = item

        self._update_active()

    def _navigate(self, view_id: str) -> None:
        self._on_navigate(view_id)

    def set_active(self, view_id: str) -> None:
        self._active = view_id
        self._update_active()

    def _update_active(self) -> None:
        for item_id, item in self._items.items():
            item.set_active(item_id == self._active)

    def refresh_theme(self) -> None:
        self.configure(fg_color=self._theme.colors.SURFACE_CONTAINER)
        self._update_active()
