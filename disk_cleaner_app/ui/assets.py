"""Дизайн-токены Material Design 3 (Material You).

Здесь собран единый источник цветовых ролей, типографики, формы и отступов.
Старые имена (``BG_CARD``, ``TEXT_PRI`` и т.д.) сохранены как алиасы, чтобы
постепенный переход на новую систему не ломал существующие экраны.
"""
from __future__ import annotations


class _MD3Colors:
    """Базовый набор ролей. Наследники задают конкретную схему."""

    # Основные роли
    PRIMARY = "#7ADBC4"
    ON_PRIMARY = "#00382E"
    PRIMARY_CONTAINER = "#005144"
    ON_PRIMARY_CONTAINER = "#98F7DF"
    PRIMARY_HOVER = "#96EBD8"
    INVERSE_PRIMARY = "#006B5B"

    SECONDARY = "#B4CCC3"
    ON_SECONDARY = "#1F352F"
    SECONDARY_CONTAINER = "#354B45"
    ON_SECONDARY_CONTAINER = "#D0E8DF"
    SECONDARY_HOVER = "#C4DCD3"

    TERTIARY = "#A9C7F7"
    ON_TERTIARY = "#0F3158"
    TERTIARY_CONTAINER = "#264874"
    ON_TERTIARY_CONTAINER = "#D3E4FF"
    TERTIARY_HOVER = "#C1D8FF"

    ERROR = "#FFB4AB"
    ON_ERROR = "#690005"
    ERROR_CONTAINER = "#93000A"
    ON_ERROR_CONTAINER = "#FFDAD6"
    ERROR_HOVER = "#FFDAD6"

    # Поверхности и контуры
    SURFACE = "#0E1513"
    SURFACE_DIM = "#0E1513"
    SURFACE_BRIGHT = "#343B39"
    SURFACE_LOWEST = "#090F0E"
    SURFACE_LOW = "#171E1C"
    SURFACE_CONTAINER = "#1B2220"
    SURFACE_HIGH = "#252C2A"
    SURFACE_CONTAINER_HIGH = SURFACE_HIGH
    SURFACE_HIGHEST = "#303735"
    ON_SURFACE = "#DDE4E1"
    ON_SURFACE_VARIANT = "#BEC9C5"
    OUTLINE = "#89938F"
    OUTLINE_VARIANT = "#3F4946"
    INVERSE_SURFACE = "#DDE4E1"
    INVERSE_ON_SURFACE = "#2A312F"
    SCRIM = "#000000"

    # Состояния (state layers)
    STATE_HOVER = "#222A27"
    STATE_PRESSED = "#2A322F"
    STATE_SELECTED = "#005144"

    # Семантические акценты
    SUCCESS = "#7ADBC4"
    WARNING = "#F5C76A"
    DANGER = "#FFB4AB"
    INFO = "#A9C7F7"

    # ── Совместимость со старым кодом ──
    BG_BASE = SURFACE
    BG_CARD = SURFACE_LOW
    BG_SIDEBAR = SURFACE_CONTAINER
    BORDER = OUTLINE_VARIANT
    TEXT_PRI = ON_SURFACE
    TEXT_SEC = ON_SURFACE_VARIANT
    TEXT_MUTED = "#8A9490"
    TREE_BG = SURFACE_LOW
    TREE_SEL = SECONDARY_CONTAINER
    CANVAS_BG = SURFACE_LOW
    PROGRESS_BG = SURFACE_HIGHEST
    BTN_BG = SURFACE_HIGH
    BTN_HOVER = SURFACE_HIGHEST


class DarkColors(_MD3Colors):
    """Тёмная схема Material 3. Seed: глубокий изумруд #2E7D6B."""


class LightColors(_MD3Colors):
    """Светлая схема Material 3."""

    PRIMARY = "#006B5B"
    ON_PRIMARY = "#FFFFFF"
    PRIMARY_CONTAINER = "#9BF2DB"
    ON_PRIMARY_CONTAINER = "#00201A"
    PRIMARY_HOVER = "#005548"
    INVERSE_PRIMARY = "#80D7C1"

    SECONDARY = "#4A635C"
    ON_SECONDARY = "#FFFFFF"
    SECONDARY_CONTAINER = "#CCE8DF"
    ON_SECONDARY_CONTAINER = "#06201A"
    SECONDARY_HOVER = "#B7D4CB"

    TERTIARY = "#3F608C"
    ON_TERTIARY = "#FFFFFF"
    TERTIARY_CONTAINER = "#D4E3FF"
    ON_TERTIARY_CONTAINER = "#001C38"
    TERTIARY_HOVER = "#AFC9F2"

    ERROR = "#BA1A1A"
    ON_ERROR = "#FFFFFF"
    ERROR_CONTAINER = "#FFDAD6"
    ON_ERROR_CONTAINER = "#410002"
    ERROR_HOVER = "#93000A"

    SURFACE = "#F5FBF7"
    SURFACE_DIM = "#D5DBD8"
    SURFACE_BRIGHT = "#F5FBF7"
    SURFACE_LOWEST = "#FFFFFF"
    SURFACE_LOW = "#EFF5F1"
    SURFACE_CONTAINER = "#E9EFEB"
    SURFACE_HIGH = "#E3E9E5"
    SURFACE_CONTAINER_HIGH = SURFACE_HIGH
    SURFACE_HIGHEST = "#DDE4DF"
    ON_SURFACE = "#171D1B"
    ON_SURFACE_VARIANT = "#3F4946"
    OUTLINE = "#6F7976"
    OUTLINE_VARIANT = "#BEC9C5"
    INVERSE_SURFACE = "#2A312F"
    INVERSE_ON_SURFACE = "#EAF1ED"
    SCRIM = "#000000"

    STATE_HOVER = "#E3ECE7"
    STATE_PRESSED = "#D8E4DE"
    STATE_SELECTED = "#9BF2DB"

    SUCCESS = "#006B5B"
    WARNING = "#8A5A00"
    DANGER = "#BA1A1A"
    INFO = "#3F608C"

    BG_BASE = SURFACE
    BG_CARD = SURFACE_LOWEST
    BG_SIDEBAR = SURFACE_CONTAINER
    BORDER = OUTLINE_VARIANT
    TEXT_PRI = ON_SURFACE
    TEXT_SEC = ON_SURFACE_VARIANT
    TEXT_MUTED = "#69736F"
    TREE_BG = SURFACE_LOWEST
    TREE_SEL = SECONDARY_CONTAINER
    CANVAS_BG = SURFACE_LOWEST
    PROGRESS_BG = SURFACE_HIGHEST
    BTN_BG = SURFACE_CONTAINER
    BTN_HOVER = SURFACE_HIGH


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

# ── Форма ───────────────────────────────────────────────
RADIUS_XS = 6
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 24
RADIUS_FULL = 999

# ── Размеры компонентов ─────────────────────────────────
SIDEBAR_WIDTH = 96
HEADER_HEIGHT = 72
STATUSBAR_HEIGHT = 52
BTN_HEIGHT = 36
BTN_HEIGHT_SM = 32
FIELD_HEIGHT = 38
TREE_ROW_HEIGHT = 32
CONTENT_PAD = 20

# Старые имена
CORNER_RADIUS = RADIUS_MD
CORNER_SMALL = RADIUS_SM

# ── Типографика ─────────────────────────────────────────
FONT_DISPLAY = ("Segoe UI", 26, "bold")
FONT_HEADLINE = ("Segoe UI", 20, "bold")
FONT_HEADLINE_SMALL = ("Segoe UI", 18, "bold")
FONT_TITLE_LARGE = ("Segoe UI", 16, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_TITLE_MEDIUM = ("Segoe UI", 11, "bold")
FONT_BODY_LARGE = ("Segoe UI", 11)
FONT_BODY = ("Segoe UI", 10)
FONT_LABEL = ("Segoe UI", 9)
FONT_LABEL_LARGE = ("Segoe UI", 10, "bold")
FONT_CAPTION = ("Segoe UI", 8)

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_HEADER = ("Segoe UI", 18, "bold")
FONT_MONO = ("Consolas", 10)
FONT_MONO_SMALL = ("Consolas", 9)
