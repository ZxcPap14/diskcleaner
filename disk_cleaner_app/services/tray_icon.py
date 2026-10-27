"""🔲 Иконка в системном трее (pystray): открыть, тихая очистка, выход.

pystray — опциональная зависимость: если её нет, функции трея честно
недоступны, приложение работает как раньше. Колбэки pystray приходят
из его потока и доставляются в Tk через UiDispatcher.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def tray_available() -> bool:
    """Установлены ли pystray и Pillow (Pillow идёт с customtkinter)."""
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _load_icon_image():
    """Иконка приложения из assets; если файла нет — заглушка 64×64."""
    from PIL import Image

    if getattr(sys, "frozen", False):
        # onefile распаковывает --add-data в _MEIPASS, а не рядом с exe.
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parents[2]
    icon_path = base / "assets" / "diskcleaner.ico"
    try:
        return Image.open(icon_path)
    except OSError:
        image = Image.new("RGB", (64, 64), "#2E7D6B")
        return image


class TrayController:
    """Управление иконкой трея. Колбэки принимают без аргументов."""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_quick_clean: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_show = on_show
        self._on_quick_clean = on_quick_clean
        self._on_quit = on_quit
        self._icon: Any = None

    def start(self) -> bool:
        """Создать и показать иконку. False — pystray недоступен."""
        if self._icon is not None:
            return True
        if not tray_available():
            log.info("pystray не установлен — трей недоступен")
            return False
        try:
            import pystray

            menu = pystray.Menu(
                pystray.MenuItem("Открыть DiskCleaner", self._show, default=True),
                pystray.MenuItem("Тихая очистка (safe)", self._quick_clean),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Выход", self._quit),
            )
            self._icon = pystray.Icon(
                "DiskCleaner", _load_icon_image(),
                "DiskCleaner Pro", menu,
            )
            self._icon.run_detached()
            return True
        except Exception:
            log.warning("Не удалось запустить иконку трея", exc_info=True)
            self._icon = None
            return False

    def stop(self) -> None:
        if self._icon is None:
            return
        try:
            self._icon.stop()
        except Exception:
            log.debug("Остановка трея не удалась", exc_info=True)
        self._icon = None

    @property
    def running(self) -> bool:
        return self._icon is not None

    # ── колбэки pystray (его поток) ──────────────────

    def _show(self, *_args) -> None:
        self._on_show()

    def _quick_clean(self, *_args) -> None:
        self._on_quick_clean()

    def _quit(self, *_args) -> None:
        self._on_quit()
