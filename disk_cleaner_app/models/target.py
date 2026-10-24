"""Модель цели глубокой очистки.

Здесь нет обращений к диску: только описание того, что очиститель
собирается делать и как это объяснить пользователю.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ── Слои очистки ──────────────────────────────────────

LAYER_SAFE = "A"          # безопасные кэши
LAYER_SYSTEM = "B"        # системное обслуживание
LAYER_COMPONENTS = "C"    # модели, расширения, toolchain
LAYER_LEFTOVERS = "D"     # остатки и пользовательские данные
LAYER_INVENTORY = "E"     # только показ, без удаления

LAYERS = (LAYER_SAFE, LAYER_SYSTEM, LAYER_COMPONENTS, LAYER_LEFTOVERS, LAYER_INVENTORY)

LAYER_TITLES = {
    LAYER_SAFE: "Безопасные кэши",
    LAYER_SYSTEM: "Система",
    LAYER_COMPONENTS: "Компоненты и модели",
    LAYER_LEFTOVERS: "Остатки",
    LAYER_INVENTORY: "Крупные файлы",
}

LAYER_HINTS = {
    LAYER_SAFE: "Пересоздаются автоматически. Можно чистить без риска для данных.",
    LAYER_SYSTEM: "Требуют прав администратора и поддерживаемых Windows команд.",
    LAYER_COMPONENTS: "Не кэш: после удаления потребуется скачать или установить заново.",
    LAYER_LEFTOVERS: "Удаляются только в корзину и только после подтверждения.",
    LAYER_INVENTORY: "Показываем размер и объясняем, почему не удаляем автоматически.",
}


@dataclass(frozen=True)
class TargetSpec:
    """Декларативное описание цели.

    Очистители могут по-прежнему реализовывать ``get_size``/``clean``,
    но для глубокой очистки важны метаданные: слой, риск, возраст,
    необходимость прав и текст объяснения.
    """

    id: str
    name: str
    group: str
    layer: str = LAYER_SAFE
    safety: str = "🟢"
    kind: str = "dir_contents"      # dir_contents | dir_remove | files | glob | command | api
    roots: tuple[Path, ...] = ()
    patterns: tuple[str, ...] = ()
    min_age_hours: int = 0
    admin_required: bool = False
    recycle: bool = True
    recommended: bool = True
    why: str = ""
    loss: str = ""
    restore_hint: str = ""
    verify: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.layer not in LAYERS:
            raise ValueError(f"Неизвестный слой очистки: {self.layer}")
        if self.kind not in {
            "dir_contents", "dir_remove", "files", "glob", "command", "api",
        }:
            raise ValueError(f"Неизвестный тип цели: {self.kind}")
        if self.kind != "command" and self.kind != "api" and not self.roots:
            raise ValueError(f"Для цели {self.id} не указаны roots")


def layer_title(layer: str) -> str:
    return LAYER_TITLES.get(layer, layer)


def layer_hint(layer: str) -> str:
    return LAYER_HINTS.get(layer, "")
