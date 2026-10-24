"""Логирование приложения: файл, faulthandler и перехват ошибок Tk."""
from __future__ import annotations

import faulthandler
import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from disk_cleaner_app.models.config import CONFIG_DIR

LOG_DIR = CONFIG_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
_MAX_BYTES = 1024 * 1024
_BACKUPS = 3

_configured = False
_fault_file = None


def setup_logging(level: int = logging.INFO) -> Path:
    """Настроить запись логов в %APPDATA%\\DiskCleaner\\logs\\app.log.

    Повторные вызовы безопасны: обработчики не дублируются.
    """
    global _configured, _fault_file
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if not _configured:
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUPS,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(handler)
        _configured = True

    # faulthandler пишет падение интерпретатора (segfault и т.п.).
    if _fault_file is None:
        try:
            _fault_file = open(LOG_DIR / "faulthandler.log", "a", encoding="utf-8")
            faulthandler.enable(file=_fault_file, all_threads=True)
        except (OSError, RuntimeError):
            _fault_file = None

    logging.getLogger(__name__).info(
        "DiskCleaner запущен, лог: %s", LOG_FILE
    )
    return LOG_FILE


def install_exception_hooks(root=None) -> None:
    """Логировать необработанные исключения и ошибки колбэков Tk."""
    logger = logging.getLogger("disk_cleaner_app.unhandled")

    def _hook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.error(
            "Необработанное исключение:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        # В консольной сборке полезно видеть ошибку и без лога.
        if sys.__stderr__ is not None:
            traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook

    if root is not None:
        def _tk_hook(exc_type, exc_value, exc_tb) -> None:
            logger.error(
                "Ошибка в обработчике Tk:\n%s",
                "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            )

        try:
            root.report_callback_exception = _tk_hook
        except Exception:
            pass
