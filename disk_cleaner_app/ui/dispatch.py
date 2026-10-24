"""UiDispatcher — безопасная доставка событий из рабочих потоков в Tk.

Tkinter не является потокобезопасным: вызывать `after()` (и любые методы виджетов)
из фонового потока нельзя. Диспетчер складывает колбэки в очередь, а главный поток
разбирает её по таймеру.
"""
from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class UiDispatcher:
    """Очередь колбэков «воркер → UI-поток»."""

    def __init__(self, widget: tk.Misc, interval_ms: int = 50) -> None:
        self._widget = widget
        self._interval_ms = max(10, int(interval_ms))
        self._queue: queue.Queue[tuple[Callable[..., Any], tuple, dict]] = queue.Queue()
        self._after_id: str | None = None
        self._stopped = False

    # ── публичное API (можно вызывать из любого потока) ──

    def post(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Выполнить callback в UI-потоке."""
        if self._stopped:
            return
        self._queue.put((callback, args, kwargs))

    def post_after(self, delay_ms: int, callback: Callable[..., Any],
                   *args: Any, **kwargs: Any) -> None:
        """Выполнить callback в UI-потоке через delay_ms миллисекунд."""
        def schedule() -> None:
            if self._stopped:
                return
            self._widget.after(max(0, int(delay_ms)), lambda: self.post(callback, *args, **kwargs))

        self.post(schedule)

    def start(self) -> None:
        if self._stopped or self._after_id is not None:
            return
        self._schedule()

    def stop(self) -> None:
        self._stopped = True
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    # ── внутреннее ──

    def _schedule(self) -> None:
        if self._stopped:
            return
        try:
            if not self._widget.winfo_exists():
                self._stopped = True
                return
            self._after_id = self._widget.after(self._interval_ms, self._drain)
        except tk.TclError:
            self._stopped = True

    def _drain(self) -> None:
        self._after_id = None
        while True:
            try:
                callback, args, kwargs = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args, **kwargs)
            except Exception:
                # Ошибка одного колбэка не должна останавливать очередь.
                logger.exception("Ошибка в UI-колбэке %r", callback)
        self._schedule()
