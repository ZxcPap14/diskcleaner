"""Автозагрузка для веб-интерфейса."""
from __future__ import annotations

import logging
from typing import Any

from disk_cleaner_app.services.startup import StartupManager

log = logging.getLogger(__name__)


class StartupService:
    """Список записей автозагрузки и включение/отключение."""

    def __init__(self) -> None:
        self._manager = StartupManager()
        self._items: list[dict[str, Any]] = []

    def load(self) -> dict[str, Any]:
        try:
            self._items = self._manager.get_all()
        except Exception:
            log.warning("Не удалось прочитать автозагрузку", exc_info=True)
            self._items = []
        return self.state()

    def state(self) -> dict[str, Any]:
        items = [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "command": item.get("command", ""),
                "source": item.get("source", ""),
                "enabled": bool(item.get("enabled", False)),
            }
            for item in self._items
        ]
        enabled = sum(1 for item in items if item["enabled"])
        return {
            "items": items,
            "count": len(items),
            "enabled": enabled,
            "disabled": len(items) - enabled,
        }

    def toggle(self, item_id: str, enabled: bool) -> dict[str, Any]:
        item = next((i for i in self._items if i.get("id") == item_id), None)
        if item is None:
            return self.state()
        try:
            if enabled:
                self._manager.enable_item(item)
            else:
                self._manager.disable_item(item)
        except Exception:
            log.warning("Не удалось переключить %s", item_id, exc_info=True)
        # Перечитываем реестр: Windows мог переложить запись в Disabled.
        return self.load()
