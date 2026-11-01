"""Иконка в трее для веб-интерфейса: открыть окно, тихая очистка, выход.

Используется тот же ``TrayController``, что и раньше в Tk-версии:
колбэки pystray приходят из его потока, поэтому тяжёлая работа уходит
в отдельный поток, а окно трогаем только через pywebview.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


class WebTray:
    """Жизненный цикл иконки трея поверх веб-окна."""

    def __init__(self, on_show: Callable[[], None],
                 on_quit: Callable[[], None]) -> None:
        self._on_show = on_show
        self._on_quit = on_quit
        self._icon: Any = None
        self._clean: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._icon is not None

    def start(self) -> bool:
        if self._icon is not None:
            return True
        from disk_cleaner_app.services.tray_icon import TrayController

        controller = TrayController(
            on_show=self._on_show,
            on_quick_clean=self.quick_clean,
            on_quit=self._on_quit,
        )
        if not controller.start():
            return False
        self._icon = controller
        return True

    def stop(self) -> None:
        if self._icon is None:
            return
        self._icon.stop()
        self._icon = None

    def quick_clean(self) -> None:
        """Очистка safe-набора без интерфейса: окно может быть скрыто."""
        if self._clean is not None and self._clean.is_alive():
            log.info("Тихая очистка уже идёт — повторный запуск пропущен")
            return
        self._clean = threading.Thread(
            target=self._run_clean, daemon=True, name="tray-clean",
        )
        self._clean.start()

    def _run_clean(self) -> None:
        from disk_cleaner_app.models.item import format_bytes
        from disk_cleaner_app.services.auto_clean import run_silent_clean

        try:
            summary = run_silent_clean(mode="smart")
        except Exception:
            log.warning("Тихая очистка из трея не удалась", exc_info=True)
            return
        log.info("Тихая очистка из трея: освобождено %s",
                 format_bytes(summary["freed"]))
