"""Схлопывание потока событий Tk в один вызов.

Ресайз окна присылает десятки ``<Configure>`` в секунду. Если на каждое
событие пересчитывать геометрию или перерисовывать холст, окно «залипает»
на всё время перетаскивания. Таймер на 120 мс даёт максимум ~8 кадров в
секунду и при этом успевает обновить картинку до того, как пользователь
отпустит край окна.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

DEFAULT_MS = 120


class DebouncedEvent:
    """Обработчик события, который срабатывает не чаще одного раза за ``ms``."""

    def __init__(
        self,
        widget: Any,
        callback: Callable[[], None],
        ms: int = DEFAULT_MS,
    ) -> None:
        self._widget = widget
        self._callback = callback
        self._ms = ms
        self._pending: str | None = None

    def __call__(self, _event: Any = None) -> None:
        self._cancel()
        try:
            self._pending = self._widget.after(self._ms, self._fire)
        except Exception:
            # Виджет уже уничтожен — вызывать нечего.
            self._pending = None

    def flush(self) -> None:
        """Выполнить отложенный вызов сразу (например, перед скрытием страницы)."""
        self._cancel()
        self._callback()

    def _fire(self) -> None:
        self._pending = None
        self._callback()

    def _cancel(self) -> None:
        if self._pending is None:
            return
        try:
            self._widget.after_cancel(self._pending)
        except Exception:
            pass
        self._pending = None
