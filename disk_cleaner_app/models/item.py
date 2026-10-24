"""Модели данных: CleanupItem, SafetyLevel, группы."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class SafetyLevel:
    """Уровни безопасности операции очистки."""
    SAFE = "🟢"
    CAUTION = "🟡"
    ADVANCED = "🔴"

    ORDER = {SAFE: 0, CAUTION: 1, ADVANCED: 2}


# ── Группы (категории) ──
GROUP_SYSTEM = "🖥️ Система"
GROUP_BROWSERS = "🌐 Браузеры"
GROUP_DEVTOOLS = "📦 Dev Tools"
GROUP_AIML = "🤖 AI/ML"
GROUP_APPS = "💬 Приложения"
GROUP_CUSTOM = "🧩 Пользовательские"
GROUP_AUTO = "🧠 Auto-discovered"

ALL_GROUPS = [
    GROUP_SYSTEM, GROUP_BROWSERS, GROUP_DEVTOOLS,
    GROUP_AIML, GROUP_APPS, GROUP_CUSTOM, GROUP_AUTO,
]


@dataclass
class CleanupItem:
    """Одна цель очистки (папка, кэш, система)."""
    id: str
    name: str
    group: str
    description: str
    safety: str  # SafetyLevel.SAFE / CAUTION / ADVANCED
    get_size: Callable[[], int]
    clean: Callable[[], tuple[str, str]]
    size: int = 0
    scanned: bool = False
    can_preview: bool = False
    preview_path: str | None = None

    @property
    def size_formatted(self) -> str:
        if not self.scanned and self.size == 0:
            return "—"
        return format_bytes(self.size)

    @property
    def safety_order(self) -> int:
        return SafetyLevel.ORDER.get(self.safety, 99)


def format_bytes(b: int | float) -> str:
    """Человеко-читаемый размер: 1.5 ГБ, 234 МБ, ...

    Деление выполняется в float, иначе 1.5 ГиБ превращались бы в «1.0 ГБ».
    """
    if b is None or b < 0:
        return "0 Б"

    value = float(b)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if abs(value) < 1024:
            if unit == "Б":
                return f"{int(value)} Б"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} ПБ"
