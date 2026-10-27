"""Дизайн-токены Material Design 3 (Material You).

Здесь собран единый источник цветовых ролей, типографики, формы и отступов.
Старые имена (``BG_CARD``, ``TEXT_PRI`` и т.д.) сохранены как алиасы, чтобы
постепенный переход на новую систему не ломал существующие экраны.
"""
from __future__ import annotations


class _MD3Colors:
    """Базовый набор ролей. Наследники задают конкретную схему.

    Значения тёмной схемы взяты из Fluent 2 / WinUI 3 (тема Dark):
    ``SolidBackgroundFillColorBase`` = #202020, ``CardBackgroundFillColorDefault``
    = 5% белого над базой, ``ControlStrokeColorDefault`` = ~7%. Акцент — фирменный
    изумруд: Windows разрешает любой акцент, а бренд терять незачем.
    """

    # Основные роли
    PRIMARY = "#6FD8C6"
    ON_PRIMARY = "#00201A"
    PRIMARY_CONTAINER = "#2E4741"
    ON_PRIMARY_CONTAINER = "#A8F2E2"
    PRIMARY_HOVER = "#8AE5D4"
    INVERSE_PRIMARY = "#006B5B"

    SECONDARY = "#C8C8C8"
    ON_SECONDARY = "#1A1A1A"
    SECONDARY_CONTAINER = "#2D2D2D"
    ON_SECONDARY_CONTAINER = "#FFFFFF"
    SECONDARY_HOVER = "#363636"

    TERTIARY = "#9CC7F5"
    ON_TERTIARY = "#0B2540"
    TERTIARY_CONTAINER = "#243B52"
    ON_TERTIARY_CONTAINER = "#D6E8FF"
    TERTIARY_HOVER = "#B4D5FA"

    ERROR = "#FF99A4"
    ON_ERROR = "#3A0009"
    ERROR_CONTAINER = "#4A1620"
    ON_ERROR_CONTAINER = "#FFD9DD"
    ERROR_HOVER = "#FFB3BC"

    # Поверхности и контуры (слои WinUI: база → карточка → контрол)
    SURFACE = "#202020"
    SURFACE_DIM = "#1A1A1A"
    SURFACE_BRIGHT = "#303030"
    SURFACE_LOWEST = "#171717"
    SURFACE_LOW = "#2B2B2B"
    SURFACE_CONTAINER = "#1B1B1B"
    SURFACE_HIGH = "#2D2D2D"
    SURFACE_CONTAINER_HIGH = SURFACE_HIGH
    SURFACE_HIGHEST = "#363636"
    ON_SURFACE = "#FFFFFF"
    ON_SURFACE_VARIANT = "#C8C8C8"
    OUTLINE = "#8A8A8A"
    OUTLINE_VARIANT = "#383838"
    INVERSE_SURFACE = "#F3F3F3"
    INVERSE_ON_SURFACE = "#1A1A1A"
    SCRIM = "#000000"

    # Состояния (state layers)
    STATE_HOVER = "#2F2F2F"
    STATE_PRESSED = "#262626"
    STATE_SELECTED = "#293834"

    # Семантические акценты
    SUCCESS = "#6FD8C6"
    WARNING = "#F0C46B"
    DANGER = "#FF99A4"
    INFO = "#9CC7F5"

    # ── Совместимость со старым кодом ──
    BG_BASE = SURFACE
    BG_CARD = SURFACE_LOW
    BG_SIDEBAR = SURFACE_CONTAINER
    BORDER = "#333333"
    TEXT_PRI = ON_SURFACE
    TEXT_SEC = ON_SURFACE_VARIANT
    TEXT_MUTED = "#9A9A9A"
    TREE_BG = SURFACE_LOW
    TREE_SEL = SECONDARY_CONTAINER
    CANVAS_BG = SURFACE_LOW
    PROGRESS_BG = "#3A3A3A"
    BTN_BG = SURFACE_HIGH
    BTN_HOVER = SURFACE_HIGHEST


class DarkColors(_MD3Colors):
    """Тёмная схема в духе Windows 11. Seed: глубокий изумруд #2E7D6B."""


class LightColors(_MD3Colors):
    """Светлая схема в духе Windows 11."""

    PRIMARY = "#006B5B"
    ON_PRIMARY = "#FFFFFF"
    PRIMARY_CONTAINER = "#CDEDE6"
    ON_PRIMARY_CONTAINER = "#00201A"
    PRIMARY_HOVER = "#005548"
    INVERSE_PRIMARY = "#6FD8C6"

    SECONDARY = "#5A5A5A"
    ON_SECONDARY = "#FFFFFF"
    SECONDARY_CONTAINER = "#EAEAEA"
    ON_SECONDARY_CONTAINER = "#1A1A1A"
    SECONDARY_HOVER = "#E0E0E0"

    TERTIARY = "#3F608C"
    ON_TERTIARY = "#FFFFFF"
    TERTIARY_CONTAINER = "#DCE9FA"
    ON_TERTIARY_CONTAINER = "#0B2540"
    TERTIARY_HOVER = "#CBDFF6"

    ERROR = "#BA1A1A"
    ON_ERROR = "#FFFFFF"
    ERROR_CONTAINER = "#FFE0E2"
    ON_ERROR_CONTAINER = "#410002"
    ERROR_HOVER = "#8E1111"

    SURFACE = "#F3F3F3"
    SURFACE_DIM = "#E6E6E6"
    SURFACE_BRIGHT = "#FFFFFF"
    SURFACE_LOWEST = "#FFFFFF"
    SURFACE_LOW = "#FBFBFB"
    SURFACE_CONTAINER = "#EBEBEB"
    SURFACE_HIGH = "#FFFFFF"
    SURFACE_CONTAINER_HIGH = SURFACE_HIGH
    SURFACE_HIGHEST = "#F0F0F0"
    ON_SURFACE = "#1A1A1A"
    ON_SURFACE_VARIANT = "#5C5C5C"
    OUTLINE = "#8A8A8A"
    OUTLINE_VARIANT = "#D6D6D6"
    INVERSE_SURFACE = "#202020"
    INVERSE_ON_SURFACE = "#FFFFFF"
    SCRIM = "#000000"

    STATE_HOVER = "#F0F0F0"
    STATE_PRESSED = "#E8E8E8"
    STATE_SELECTED = "#D6EDE7"

    SUCCESS = "#006B5B"
    WARNING = "#8A5A00"
    DANGER = "#BA1A1A"
    INFO = "#3F608C"

    BG_BASE = SURFACE
    BG_CARD = SURFACE_LOWEST
    BG_SIDEBAR = SURFACE_CONTAINER
    BORDER = "#E0E0E0"
    TEXT_PRI = ON_SURFACE
    TEXT_SEC = ON_SURFACE_VARIANT
    TEXT_MUTED = "#757575"
    TREE_BG = SURFACE_LOWEST
    TREE_SEL = SECONDARY_CONTAINER
    CANVAS_BG = SURFACE_LOWEST
    PROGRESS_BG = "#DCDCDC"
    BTN_BG = SURFACE_CONTAINER
    BTN_HOVER = SURFACE_HIGHEST


# ── Палитра treemap ─────────────────────────────────────
TREEMAP_COLORS = [
    "#7ADBC4", "#8FB8FF", "#F5C76A", "#FFB4AB",
    "#9CCFC4", "#C4B5FD", "#F2A7D8", "#F5B183",
    "#7DD3E8", "#E0A9F5", "#B6D97A", "#FFC48A",
    "#8EC9F5", "#7AD8CC", "#C7A9F5", "#FFB8C8",
]

TREEMAP_COLORS_LIGHT = [
    "#2E7D6B", "#3F608C", "#8A5A00", "#BA1A1A",
    "#4A635C", "#6750A4", "#8B4A77", "#9A4A1A",
    "#00647A", "#7A3D91", "#4F6B00", "#8A5A00",
    "#2F6690", "#006B5B", "#6A4A9A", "#9A3D55",
]


def treemap_palette(is_dark: bool) -> list[str]:
    """Палитра treemap под текущую тему."""
    return TREEMAP_COLORS if is_dark else TREEMAP_COLORS_LIGHT


# ── Отступы (4-пиксельная сетка) ────────────────────────
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 24
SPACE_6 = 32
SPACE_7 = 40

# ── Форма (WinUI: ControlCornerRadius = 4, OverlayCornerRadius = 8) ──
RADIUS_XS = 3
RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 8
RADIUS_XL = 12
RADIUS_FULL = 999

# ── Размеры компонентов (WinUI: контрол 32 px, поле 32 px) ──
SIDEBAR_WIDTH = 88
HEADER_HEIGHT = 64
STATUSBAR_HEIGHT = 48
BTN_HEIGHT = 32
BTN_HEIGHT_SM = 28
FIELD_HEIGHT = 32
TREE_ROW_HEIGHT = 32
CONTENT_PAD = 20

# Старые имена
CORNER_RADIUS = RADIUS_SM
CORNER_SMALL = RADIUS_SM

# ── Типографика ─────────────────────────────────────────
# Размеры в пунктах: WinUI Body 14 px ≈ 10 pt, Subtitle 20 px ≈ 15 pt.
FONT_DISPLAY = ("Segoe UI", 22, "bold")
FONT_HEADLINE = ("Segoe UI", 17, "bold")
FONT_HEADLINE_SMALL = ("Segoe UI", 15, "bold")
FONT_TITLE_LARGE = ("Segoe UI", 13, "bold")
FONT_TITLE = ("Segoe UI", 12, "bold")
FONT_TITLE_MEDIUM = ("Segoe UI", 10, "bold")
FONT_BODY_LARGE = ("Segoe UI", 11)
FONT_BODY = ("Segoe UI", 10)
FONT_LABEL = ("Segoe UI", 9)
FONT_LABEL_LARGE = ("Segoe UI", 10, "bold")
FONT_CAPTION = ("Segoe UI", 8)

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_HEADER = ("Segoe UI", 15, "bold")
FONT_MONO = ("Consolas", 10)
FONT_MONO_SMALL = ("Consolas", 9)
