"""Переиспользуемые компоненты Material Design 3 для CustomTkinter.

Компоненты сами подписываются на ThemeManager, поэтому смена светлой/тёмной
темы обновляет их без ручного обхода дерева виджетов.
"""
from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk
from typing import Any

import customtkinter as ctk

from disk_cleaner_app.ui.assets import (
    BTN_HEIGHT,
    FIELD_HEIGHT,
    FONT_BODY,
    FONT_HEADLINE,
    FONT_LABEL,
    FONT_LABEL_LARGE,
    RADIUS_FULL,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    TREE_ROW_HEIGHT,
)
from disk_cleaner_app.ui.theme import ThemeManager


def tone_color(theme: ThemeManager, tone: str) -> str:
    """Цвет поверхности по имени тона."""
    c = theme.colors
    return {
        "surface": c.SURFACE,
        "dim": c.SURFACE_DIM,
        "bright": c.SURFACE_BRIGHT,
        "lowest": c.SURFACE_LOWEST,
        "low": c.SURFACE_LOW,
        "container": c.SURFACE_CONTAINER,
        "high": c.SURFACE_HIGH,
        "highest": c.SURFACE_HIGHEST,
        "primary": c.PRIMARY,
        "primary_container": c.PRIMARY_CONTAINER,
        "secondary": c.SECONDARY,
        "secondary_container": c.SECONDARY_CONTAINER,
        "tertiary": c.TERTIARY,
        "tertiary_container": c.TERTIARY_CONTAINER,
        "error": c.ERROR,
        "error_container": c.ERROR_CONTAINER,
        "transparent": "transparent",
    }.get(tone, c.SURFACE_LOW)


class MDCard(ctk.CTkFrame):
    """Карточка/поверхность MD3. Без лишних рамок и вложенных «карточек»."""

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        *,
        tone: str = "low",
        outlined: bool = False,
        radius: int = RADIUS_LG,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        self._tone = tone
        self._outlined = outlined
        self._radius = radius
        self._fg_override = kwargs.pop("fg_color", None)
        super().__init__(
            parent,
            fg_color=self._fg_override or tone_color(theme, tone),
            corner_radius=radius,
            border_width=1 if outlined else 0,
            border_color=theme.colors.OUTLINE_VARIANT if outlined else theme.colors.SURFACE_LOW,
            **kwargs,
        )
        theme.register(self)

    def refresh_theme(self) -> None:
        c = self._theme.colors
        self.configure(
            fg_color=self._fg_override or tone_color(self._theme, self._tone),
            border_color=c.OUTLINE_VARIANT if self._outlined else c.SURFACE_LOW,
        )


class MDButton(ctk.CTkButton):
    """Кнопка MD3: filled / tonal / outlined / text / danger."""

    _STYLES = {
        "filled": ("PRIMARY", "ON_PRIMARY", "PRIMARY_HOVER", None),
        "tonal": ("SECONDARY_CONTAINER", "ON_SECONDARY_CONTAINER", "SECONDARY_HOVER", None),
        "tertiary": ("TERTIARY_CONTAINER", "ON_TERTIARY_CONTAINER", "TERTIARY_HOVER", None),
        "outlined": ("transparent", "ON_SURFACE", "STATE_HOVER", "OUTLINE"),
        "text": ("transparent", "PRIMARY", "STATE_HOVER", None),
        "text_muted": ("transparent", "ON_SURFACE_VARIANT", "STATE_HOVER", None),
        "danger": ("ERROR", "ON_ERROR", "ERROR_HOVER", None),
        "danger_tonal": ("ERROR_CONTAINER", "ON_ERROR_CONTAINER", "ERROR_HOVER", None),
        "danger_text": ("transparent", "ERROR", "STATE_HOVER", None),
        "elevated": ("SURFACE_CONTAINER_HIGH", "ON_SURFACE", "SURFACE_HIGHEST", "OUTLINE_VARIANT"),
    }

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        text: str = "",
        command: Callable[..., object] | None = None,
        *,
        kind: str = "filled",
        height: int = BTN_HEIGHT,
        width: int = 120,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        self._kind = kind
        self._text = text
        super().__init__(
            parent,
            text=text,
            command=command,
            height=height,
            width=width,
            corner_radius=height // 2,
            font=FONT_LABEL_LARGE,
            **kwargs,
        )
        self._apply()
        theme.register(self)

    def _apply(self) -> None:
        c = self._theme.colors
        bg, fg, hover, border = self._STYLES.get(self._kind, self._STYLES["filled"])
        background = "transparent" if bg == "transparent" else getattr(c, bg)
        foreground = getattr(c, fg)
        hover_color = getattr(c, hover)
        self.configure(
            fg_color=background,
            text_color=foreground,
            hover_color=hover_color,
            border_width=1 if border else 0,
            border_color=getattr(c, border) if border else c.SURFACE_HIGH,
            text_color_disabled=c.TEXT_MUTED,
        )

    def refresh_theme(self) -> None:
        self._apply()


class MDIconButton(ctk.CTkButton):
    """Круглая/квадратная icon-button MD3."""

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        glyph: str,
        command: Callable[..., object] | None = None,
        *,
        kind: str = "standard",
        size: int = 40,
        font: tuple = ("Segoe UI", 15),
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        self._kind = kind
        self._glyph = glyph
        super().__init__(
            parent,
            text=glyph,
            command=command,
            width=size,
            height=size,
            corner_radius=size // 2,
            font=font,
            **kwargs,
        )
        self._apply()
        theme.register(self)

    def _apply(self) -> None:
        c = self._theme.colors
        if self._kind == "filled":
            bg, fg, hover = c.PRIMARY, c.ON_PRIMARY, c.PRIMARY_HOVER
        elif self._kind == "tonal":
            bg, fg, hover = c.SECONDARY_CONTAINER, c.ON_SECONDARY_CONTAINER, c.SECONDARY_HOVER
        elif self._kind == "outlined":
            bg, fg, hover = "transparent", c.ON_SURFACE_VARIANT, c.STATE_HOVER
        else:
            bg, fg, hover = "transparent", c.ON_SURFACE_VARIANT, c.STATE_HOVER
        self.configure(
            fg_color=bg,
            text_color=fg,
            hover_color=hover,
            border_width=1 if self._kind == "outlined" else 0,
            border_color=c.OUTLINE_VARIANT,
        )

    def refresh_theme(self) -> None:
        self._apply()


class MDLabel(ctk.CTkLabel):
    """Подпись с цветовой ролью. Сама обновляется при смене темы."""

    _ROLES = {
        "on_surface": "ON_SURFACE",
        "secondary": "ON_SURFACE_VARIANT",
        "muted": "TEXT_MUTED",
        "primary": "PRIMARY",
        "primary_container": "ON_PRIMARY_CONTAINER",
        "secondary_container": "ON_SECONDARY_CONTAINER",
        "tertiary": "TERTIARY",
        "error": "ERROR",
        "danger": "ERROR",
        "error_container": "ON_ERROR_CONTAINER",
        "on_error": "ON_ERROR",
        "success": "SUCCESS",
        "warning": "WARNING",
        "info": "INFO",
        "on_primary": "ON_PRIMARY",
    }

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        text: str = "",
        *,
        role: str = "on_surface",
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        self._role = role
        kwargs.setdefault("font", FONT_BODY)
        kwargs.pop("text_color", None)
        super().__init__(parent, text=text, text_color=theme.colors.ON_SURFACE, **kwargs)
        self._apply()
        theme.register(self)

    def set_role(self, role: str) -> None:
        """Сменить цветовую роль без пересоздания виджета."""
        self._role = role
        self._apply()

    def _apply(self) -> None:
        self.configure(text_color=getattr(self._theme.colors, self._ROLES.get(
            self._role, "ON_SURFACE"
        )))

    def refresh_theme(self) -> None:
        self._apply()


class MDEntry(ctk.CTkEntry):
    """Поле ввода MD3 (filled или outlined).

    Плейсхолдер рисуется отдельной подписью-оверлеем. Это нужно из-за
    ограничения CustomTkinter: при переданном ``textvariable`` встроенный
    placeholder не активируется и поле выглядит пустым.
    """

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        *,
        kind: str = "filled",
        height: int = FIELD_HEIGHT,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        self._kind = kind
        kwargs.setdefault("font", FONT_BODY)
        font = kwargs.get("font", FONT_BODY)
        placeholder = kwargs.pop("placeholder_text", None)
        textvariable = kwargs.get("textvariable")
        super().__init__(
            parent,
            height=height,
            corner_radius=RADIUS_SM,
            border_width=1 if kind == "outlined" else 0,
            **kwargs,
        )
        self._placeholder = placeholder or ""
        self._placeholder_label: ctk.CTkLabel | None = None
        self._apply()

        if self._placeholder:
            self._placeholder_label = ctk.CTkLabel(
                self,
                text=self._placeholder,
                font=font,
                text_color=theme.colors.ON_SURFACE_VARIANT,
                anchor="w",
            )
            self._placeholder_label.place(x=12, rely=0.5, anchor="w")
            self._placeholder_label.bind(
                "<Button-1>", lambda _event: self.focus_set()
            )
            # Красим подпись уже после создания: иначе останется прозрачной
            # и унаследует цвет прошлой темы.
            self._apply()
            self.bind("<FocusIn>", self._hide_placeholder, add="+")
            self.bind("<FocusOut>", self._sync_placeholder, add="+")
            self.bind("<KeyRelease>", self._sync_placeholder, add="+")
            if textvariable is not None:
                textvariable.trace_add("write", self._sync_placeholder)
            self._sync_placeholder()

        theme.register(self)

    def _sync_placeholder(self, *_args: Any) -> None:
        """Показать плейсхолдер, если поле пустое и не в фокусе."""
        label = getattr(self, "_placeholder_label", None)
        if label is None:
            return
        try:
            focused = self.focus_get() is self
            empty = not self.get()
            if empty and not focused:
                label.place(x=12, rely=0.5, anchor="w")
            else:
                label.place_forget()
        except Exception:
            # Виджет уже уничтожен, а переменная ещё жива.
            pass

    def _hide_placeholder(self, _event: Any = None) -> None:
        label = getattr(self, "_placeholder_label", None)
        if label is not None:
            label.place_forget()

    def _apply(self) -> None:
        c = self._theme.colors
        field = c.SURFACE_HIGH if self._kind != "outlined" else c.SURFACE_LOW
        self.configure(
            fg_color=field,
            border_color=c.OUTLINE_VARIANT if self._kind == "outlined" else c.SURFACE_HIGH,
            text_color=c.ON_SURFACE,
            placeholder_text_color=c.ON_SURFACE_VARIANT,
        )
        label = getattr(self, "_placeholder_label", None)
        if label is not None:
            # CTkLabel с прозрачным фоном кэширует цвет родителя при создании
            # и после смены темы остаётся тёмным прямоугольником.
            label.configure(
                fg_color=field,
                bg_color="transparent",
                text_color=c.ON_SURFACE_VARIANT,
            )

    def refresh_theme(self) -> None:
        self._apply()


class MDOptionMenu(ctk.CTkOptionMenu):
    """Выпадающий список MD3."""

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        *,
        values: list[str] | None = None,
        height: int = FIELD_HEIGHT,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        kwargs.setdefault("font", FONT_BODY)
        super().__init__(
            parent,
            values=values or ["—"],
            height=height,
            corner_radius=RADIUS_SM,
            **kwargs,
        )
        self._apply()
        theme.register(self)

    def _apply(self) -> None:
        c = self._theme.colors
        self.configure(
            fg_color=c.SURFACE_HIGH,
            button_color=c.SURFACE_HIGH,
            button_hover_color=c.SURFACE_HIGHEST,
            text_color=c.ON_SURFACE,
            dropdown_fg_color=c.SURFACE_CONTAINER_HIGH,
            dropdown_text_color=c.ON_SURFACE,
            dropdown_hover_color=c.SURFACE_HIGHEST,
        )

    def refresh_theme(self) -> None:
        self._apply()


class MDSegmented(ctk.CTkSegmentedButton):
    """Сегментированный переключатель MD3."""

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        *,
        values: list[str],
        height: int = BTN_HEIGHT,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        kwargs.setdefault("font", FONT_LABEL_LARGE)
        super().__init__(
            parent,
            values=values,
            height=height,
            corner_radius=height // 2,
            **kwargs,
        )
        self._apply()
        theme.register(self)

    def _apply(self) -> None:
        c = self._theme.colors
        self.configure(
            selected_color=c.SECONDARY_CONTAINER,
            selected_hover_color=c.SECONDARY_HOVER,
            unselected_color=c.SURFACE_HIGH,
            unselected_hover_color=c.STATE_HOVER,
            text_color=c.ON_SURFACE,
            text_color_disabled=c.TEXT_MUTED,
        )

    def refresh_theme(self) -> None:
        self._apply()


class MDSwitch(ctk.CTkSwitch):
    """Switch MD3."""

    def __init__(self, parent: Any, theme: ThemeManager, **kwargs: Any) -> None:
        self._theme = theme
        kwargs.setdefault("font", FONT_BODY)
        super().__init__(parent, **kwargs)
        self._apply()
        theme.register(self)

    def _apply(self) -> None:
        c = self._theme.colors
        self.configure(
            progress_color=c.PRIMARY,
            fg_color=c.SURFACE_HIGHEST,
            button_color=c.ON_PRIMARY,
            button_hover_color=c.ON_PRIMARY,
            text_color=c.ON_SURFACE,
        )

    def refresh_theme(self) -> None:
        self._apply()


class MDCheckbox(ctk.CTkCheckBox):
    """Флажок MD3 с явным цветом фона.

    ``bg_color`` приходится задавать вручную: у CTkCheckBox нет прозрачного
    фона, и на подсвеченной строке иначе оставался бы прямоугольник.
    """

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        text: str = "",
        *,
        size: int = 20,
        bg_color: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        self._size = size
        kwargs.setdefault("font", FONT_BODY)
        super().__init__(
            parent,
            text=text,
            width=size + 2,
            height=size + 2,
            checkbox_width=size,
            checkbox_height=size,
            corner_radius=max(4, size // 3),
            border_width=2,
            bg_color=bg_color or theme.colors.SURFACE,
            **kwargs,
        )
        self._apply()
        theme.register(self)

    def set_bg(self, color: str) -> None:
        """Сменить фон под цвет строки-родителя."""
        self.configure(bg_color=color)

    def _apply(self) -> None:
        c = self._theme.colors
        self.configure(
            fg_color=c.PRIMARY,
            hover_color=c.PRIMARY_HOVER,
            border_color=c.OUTLINE,
            checkmark_color=c.ON_PRIMARY,
            text_color=c.ON_SURFACE,
            text_color_disabled=c.TEXT_MUTED,
        )

    def refresh_theme(self) -> None:
        self._apply()


class MDProgress(ctk.CTkProgressBar):
    """Тонкий прогресс MD3."""

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        *,
        height: int = 6,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        super().__init__(
            parent,
            height=height,
            corner_radius=height // 2,
            **kwargs,
        )
        self._apply()
        theme.register(self)

    def _apply(self) -> None:
        c = self._theme.colors
        self.configure(progress_color=c.PRIMARY, fg_color=c.SURFACE_HIGHEST)

    def refresh_theme(self) -> None:
        self._apply()


class MDScrollArea(ctk.CTkScrollableFrame):
    """Прокручиваемая область страницы.

    Полоса прокрутки показывается только тогда, когда содержимое не влезает:
    иначе на экранах с запасом высоты оставался бы «пустой» трек.
    """

    def __init__(self, parent: Any, theme: ThemeManager, **kwargs: Any) -> None:
        self._theme = theme
        kwargs.setdefault("fg_color", theme.colors.SURFACE)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("scrollbar_button_color", theme.colors.OUTLINE_VARIANT)
        kwargs.setdefault("scrollbar_button_hover_color", theme.colors.OUTLINE)
        super().__init__(parent, **kwargs)
        self.bind("<Configure>", self._sync_scrollbar, add="+")
        self._parent_canvas.bind("<Configure>", self._sync_scrollbar, add="+")
        theme.register(self)

    def _sync_scrollbar(self, _event: Any = None) -> None:
        try:
            needed = self.winfo_reqheight() > self._parent_canvas.winfo_height() + 1
            if needed:
                self._scrollbar.grid()
            else:
                self._scrollbar.grid_remove()
        except Exception:
            pass

    def refresh_theme(self) -> None:
        c = self._theme.colors
        self.configure(
            fg_color=c.SURFACE,
            scrollbar_button_color=c.OUTLINE_VARIANT,
            scrollbar_button_hover_color=c.OUTLINE,
        )


class MDTextbox(ctk.CTkTextbox):

    """Текстовая область MD3."""

    def __init__(self, parent: Any, theme: ThemeManager, **kwargs: Any) -> None:
        self._theme = theme
        kwargs.setdefault("font", ("Consolas", 9))
        kwargs.setdefault("wrap", "word")
        kwargs.pop("fg_color", None)
        kwargs.pop("text_color", None)
        super().__init__(
            parent,
            fg_color=theme.colors.SURFACE_LOWEST,
            text_color=theme.colors.ON_SURFACE_VARIANT,
            corner_radius=RADIUS_MD,
            border_width=0,
            **kwargs,
        )
        self._apply()
        theme.register(self)

    def _apply(self) -> None:
        c = self._theme.colors
        self.configure(fg_color=c.SURFACE_LOWEST, text_color=c.ON_SURFACE_VARIANT)

    def refresh_theme(self) -> None:
        self._apply()


class PageHeader(ctk.CTkFrame):
    """Заголовок экрана MD3: иконка-бейдж, название, описание, действия."""

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        title: str,
        subtitle: str = "",
        *,
        icon: str = "",
    ) -> None:
        self._theme = theme
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)

        self._icon_frame = ctk.CTkFrame(
            self, width=46, height=46, corner_radius=14,
            fg_color=theme.colors.PRIMARY_CONTAINER,
        )
        self._icon_frame.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 14))
        self._icon_frame.grid_propagate(False)
        self._icon_label = ctk.CTkLabel(
            self._icon_frame, text=icon or "•",
            font=("Segoe UI", 20), text_color=theme.colors.ON_PRIMARY_CONTAINER,
        )
        self._icon_label.place(relx=0.5, rely=0.5, anchor="center")

        self._title = ctk.CTkLabel(
            self, text=title, font=FONT_HEADLINE,
            text_color=theme.colors.ON_SURFACE, anchor="w",
        )
        self._title.grid(row=0, column=1, sticky="sw")

        self._subtitle = ctk.CTkLabel(
            self, text=subtitle, font=FONT_BODY,
            text_color=theme.colors.ON_SURFACE_VARIANT, anchor="w",
        )
        self._subtitle.grid(row=1, column=1, sticky="nw", pady=(2, 0))

        # Пустой CTkFrame по умолчанию просит 200 px и раздувает заголовок,
        # поэтому стартовый размер минимальный — его зададут дочерние кнопки.
        self.actions = ctk.CTkFrame(
            self, fg_color="transparent", width=1, height=1,
        )
        self.actions.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))

        theme.register(self)

    def refresh_theme(self) -> None:
        c = self._theme.colors
        self._icon_frame.configure(fg_color=c.PRIMARY_CONTAINER)
        self._icon_label.configure(text_color=c.ON_PRIMARY_CONTAINER)
        self._title.configure(text_color=c.ON_SURFACE)
        self._subtitle.configure(text_color=c.ON_SURFACE_VARIANT)


class SectionTitle(ctk.CTkFrame):
    """Заголовок секции внутри карточки."""

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        title: str,
        subtitle: str = "",
        *,
        icon: str = "",
    ) -> None:
        self._theme = theme
        super().__init__(parent, fg_color="transparent")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        self._icon = ctk.CTkLabel(
            row, text=icon, font=("Segoe UI", 14),
            text_color=theme.colors.PRIMARY,
        )
        if icon:
            self._icon.pack(side="left", padx=(0, 7))
        self._title = ctk.CTkLabel(
            row, text=title, font=FONT_LABEL_LARGE,
            text_color=theme.colors.ON_SURFACE, anchor="w",
        )
        self._title.pack(side="left")
        self._subtitle = ctk.CTkLabel(
            self, text=subtitle, font=FONT_LABEL,
            text_color=theme.colors.ON_SURFACE_VARIANT, anchor="w",
            justify="left", wraplength=760,
        )
        if subtitle:
            self._subtitle.pack(fill="x", pady=(2, 0))
        theme.register(self)

    def refresh_theme(self) -> None:
        c = self._theme.colors
        self._icon.configure(text_color=c.PRIMARY)
        self._title.configure(text_color=c.ON_SURFACE)
        self._subtitle.configure(text_color=c.ON_SURFACE_VARIANT)


class MDPill(ctk.CTkFrame):
    """Компактный status-chip."""

    def __init__(
        self,
        parent: Any,
        theme: ThemeManager,
        text: str = "",
        *,
        icon: str = "",
        tone: str = "secondary_container",
    ) -> None:
        self._theme = theme
        self._tone = tone
        super().__init__(
            parent,
            fg_color=tone_color(theme, tone),
            corner_radius=RADIUS_FULL,
            height=32,
        )
        self._label = ctk.CTkLabel(
            self, text=f"{icon}  {text}".strip(),
            font=FONT_LABEL, text_color=self._label_color(),
        )
        self._label.pack(padx=12, pady=4)
        theme.register(self)

    def _label_color(self) -> str:
        c = self._theme.colors
        role = {
            "primary_container": "ON_PRIMARY_CONTAINER",
            "error_container": "ON_ERROR_CONTAINER",
            "tertiary_container": "ON_TERTIARY_CONTAINER",
            "primary": "ON_PRIMARY",
            "error": "ON_ERROR",
        }.get(self._tone, "ON_SECONDARY_CONTAINER")
        return getattr(c, role)

    def set_text(self, text: str, icon: str = "") -> None:
        self._label.configure(text=f"{icon}  {text}".strip())

    def refresh_theme(self) -> None:
        self.configure(fg_color=tone_color(self._theme, self._tone))
        self._label.configure(text_color=self._label_color())


def style_treeview(name: str, theme: ThemeManager, row_height: int = TREE_ROW_HEIGHT) -> None:
    """Единый компактный стиль ttk.Treeview в духе MD3."""
    c = theme.colors
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(
        f"{name}.Treeview",
        background=c.SURFACE_LOWEST,
        foreground=c.ON_SURFACE,
        fieldbackground=c.SURFACE_LOWEST,
        borderwidth=0,
        relief="flat",
        rowheight=row_height,
        font=FONT_BODY,
    )
    style.configure(
        f"{name}.Treeview.Heading",
        background=c.SURFACE_LOW,
        foreground=c.ON_SURFACE_VARIANT,
        borderwidth=0,
        relief="flat",
        padding=(8, 7),
        font=FONT_LABEL_LARGE,
    )
    style.map(
        f"{name}.Treeview",
        background=[("selected", c.SECONDARY_CONTAINER)],
        foreground=[("selected", c.ON_SECONDARY_CONTAINER)],
    )
    style.map(
        f"{name}.Treeview.Heading",
        background=[("active", c.SURFACE_CONTAINER)],
        foreground=[("active", c.ON_SURFACE)],
    )
