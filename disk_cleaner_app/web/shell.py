"""Запуск интерфейса на WebView2.

    python -m disk_cleaner_app.web.shell

Вёрстка лежит рядом, в ``disk_cleaner_app/webui``, и отдаётся встроенным
http-сервером pywebview — поэтому ES-модули и относительные пути работают
как в обычном браузере.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import webview

# Метка веб-сборки: selftest понижает Tk-проверки до некритичных.
os.environ.setdefault("DISKCLEANER_WEB", "1")

# Портативный режим применяем ДО импорта моделей: CONFIG_DIR читает
# переменную окружения один раз при импорте models.config.
if "--portable" in sys.argv:
    from disk_cleaner_app.services.portable import apply_portable

    apply_portable()

from disk_cleaner_app.models.config import ConfigManager  # noqa: E402
from disk_cleaner_app.web import win  # noqa: E402
from disk_cleaner_app.web.api import Api  # noqa: E402

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
        # pywebview иначе вешает перетаскивание окна на mousedown по всей
        # странице; таскаем только за шапку через win_drag().
        easy_drag=False,
        background_color="#202020" if dark else "#F3F3F3",
    )
    if window is None:
        raise RuntimeError("WebView2 не создал окно")
    api._window = window

    def on_shown() -> None:
        win.prepare(window)
        win.set_dark_frame(window, dark)

    def on_closed() -> None:
        # destroy() закрывает окно, но процесс могут держать фоновые потоки
        # pythonnet и WebView2: без этого приложение оставалось в диспетчере
        # задач и его приходилось завершать вручную.
        os._exit(0)

    window.events.shown += on_shown
    window.events.closed += on_closed
    return window, api


def run(debug: bool = False) -> None:
    # Окно могло быть создано раньше (тесты, встраивание): не открываем второе.
    if not webview.windows:
        create(debug)
    # private_mode=True: вёрстка грузится из локальных файлов, а кэш профиля
    # WebView2 переживает обновление приложения и показывает старый интерфейс.
    webview.start(debug=debug, private_mode=True)


def _self_test() -> int:
    from disk_cleaner_app.selftest import run_self_test

    return run_self_test()


def main() -> None:
    """Точка входа для pyproject-скрипта и сборки."""
    logging.basicConfig(level=logging.INFO)
    if "--self-test" in sys.argv:
        # Собранный DiskCleanerWeb.exe проверяют тем же ключом, что и
        # основной exe: без этого здесь открылось бы окно.
        raise SystemExit(_self_test())
    run(debug=False)


if __name__ == "__main__":
    # PyInstaller запускает shell.py именно как __main__, так что проверка
    # аргументов нужна и здесь, а не только в main().
    logging.basicConfig(level=logging.INFO)
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    # DevTools — только по явному --dev: собранный exe должен открываться
    # без панели разработчика.
    run(debug="--dev" in sys.argv)
