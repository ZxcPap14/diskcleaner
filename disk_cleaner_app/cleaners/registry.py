"""CleanerRegistry — центральный реестр всех очистителей."""
from __future__ import annotations

import logging
from pathlib import Path

from disk_cleaner_app.cleaners.aiml import AIML_CLEANERS
from disk_cleaner_app.cleaners.apps import APP_CLEANERS
from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    get_dir_size,
    safe_remove,
    safe_rm_contents,
)
from disk_cleaner_app.cleaners.browsers import BROWSER_CLEANERS
from disk_cleaner_app.cleaners.devtools import DEVTOOLS_CLEANERS
from disk_cleaner_app.cleaners.discover import auto_discover_items
from disk_cleaner_app.cleaners.safety import validate_custom_path
from disk_cleaner_app.cleaners.system import SYSTEM_CLEANERS
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.item import GROUP_CUSTOM, SafetyLevel
from disk_cleaner_app.models.target import LAYER_LEFTOVERS

logger = logging.getLogger(__name__)


# ── Фабрика для custom rules ──────────────────────────

def _make_custom_cleaner(rule: dict) -> BaseCleaner | None:
    """Создать BaseCleaner из правила пользователя.

    Возвращает None, если правило некорректно (устарело/запрещённый путь).
    """
    rule_id = str(rule.get("id", "")).strip()
    name = rule.get("name", "Custom")
    path = rule.get("path", "")
    safety = rule.get("safety", SafetyLevel.CAUTION)

    if not rule_id or not path:
        return None

    error = validate_custom_path(path)
    if error:
        logger.warning("Пропущено правило %s (%s): %s", name, path, error)
        return None

    p = Path(path)
    display_name = f"🧩 {name}"
    safety_level = safety

    class CustomRuleCleaner(BaseCleaner):
        id = rule_id
        name = display_name
        group = GROUP_CUSTOM
        description = str(path)
        safety = safety_level
        layer = LAYER_LEFTOVERS
        recommended = False
        can_preview = True
        preview_path = str(path)
        why = "Правило добавлено пользователем вручную."
        loss = "Содержимое указанной папки будет удалено без возможности отката."

        def affected_paths(self) -> tuple[Path, ...]:
            return (p,)

        def get_size(self) -> int:
            if not p.exists():
                return 0
            return get_dir_size(p) if p.is_dir() else p.stat().st_size

        def clean(self) -> tuple[str, str]:
            if not p.exists():
                return ("OK", "Уже удалён")
            # Папку очищаем по содержимому (как обещает description),
            # файл удаляем целиком.
            if p.is_dir():
                ok = safe_rm_contents(p)
            else:
                ok = safe_remove(p)
            return (
                ("OK", f"{name}: удалено")
                if ok
                else ("ERR", f"{name}: не удалось удалить (занято или нет прав)")
            )

    return CustomRuleCleaner()


class CleanerRegistry:
    """Реестр всех очистителей: встроенные + auto-discover + custom rules."""

    def __init__(self, config: ConfigManager) -> None:
        self._config = config
        self._builtin_classes: list[type[BaseCleaner]] = (
            SYSTEM_CLEANERS + BROWSER_CLEANERS +
            DEVTOOLS_CLEANERS + APP_CLEANERS + AIML_CLEANERS
        )

    def get_all(self, include_auto: bool = True) -> list[BaseCleaner]:
        """Вернуть все Cleaner'ы (инстансы)."""
        items: list[BaseCleaner] = [cls() for cls in self._builtin_classes]

        if include_auto:
            items.extend(auto_discover_items())

        for rule in self._config.load_custom_rules():
            cleaner = _make_custom_cleaner(rule)
            if cleaner is not None:
                items.append(cleaner)

        return items

    def get_safe(self, include_auto: bool = True) -> list[BaseCleaner]:
        """Только 🟢 безопасные."""
        return [c for c in self.get_all(include_auto) if c.safety == SafetyLevel.SAFE]

    def count(self) -> int:
        return len(self._builtin_classes)
