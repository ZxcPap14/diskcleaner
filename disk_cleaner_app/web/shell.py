"""Запуск интерфейса на WebView2.

    python -m disk_cleaner_app.web.shell

Вёрстка лежит рядом, в ``disk_cleaner_app/webui``, и отдаётся встроенным
http-сервером pywebview — поэтому ES-модули и относительные пути работают
как в обычном браузере.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import webview

from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.web import win
from disk_cleaner_app.web.api import Api

log = logging.getLogger(__name__)

WEBUI = (
    Path(sys._MEIPASS) / "disk_cleaner_app" / "webui"  # type: ignore[attr-defined]
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent / "webui"
)


def create(debug: bool = False) -> tuple[webview.Window, Api]:
    """Создать окно приложения, не запуская цикл событий."""
    api = Api()
    dark = str(ConfigManager().get("theme", "dark")) != "light"
    window = webview.create_window(
        "DiskCleaner Pro",
        url=str(WEBUI / "index.html"),
        js_api=api,
        width=1280,
        height=820,
        min_size=(1080, 720),
        frameless=True,
        background_color="#202020" if dark else "#F3F3F3",
    )
    if window is None:
        raise RuntimeError("WebView2 не создал окно")
    api._window = window

    def on_shown() -> None:
        win.prepare(window)
        win.set_dark_frame(window, dark)

    window.events.shown += on_shown
    return window, api


def run(debug: bool = False) -> None:
    create(debug)
    # private_mode=True: вёрстка грузится из локальных файлов, а кэш профиля
    # WebView2 переживает обновление приложения и показывает старый интерфейс.
    webview.start(debug=debug, private_mode=True)


def main() -> None:
    """Точка входа для pyproject-скрипта и сборки."""
    logging.basicConfig(level=logging.INFO)
    run(debug=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run(debug=True)
