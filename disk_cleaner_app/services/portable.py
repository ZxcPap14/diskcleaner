"""Портативный режим: данные рядом с exe вместо %APPDATA% (флаг --portable).

Модуль намеренно не импортирует `models.config`: env-переменную нужно
выставить ДО того, как config посчитает CONFIG_DIR при импорте.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Имя переменной продублировано в models/config.py (_resolve_config_dir).
ENV_HOME = "DISKCLEANER_HOME"
DATA_DIR_NAME = "DiskCleanerData"


def portable_home() -> Path:
    """Папка данных рядом с exe (frozen) или с текущим каталогом (из исходников)."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path.cwd()
    return base / DATA_DIR_NAME


def apply_portable() -> Path:
    """Включить портативный режим через env и вернуть папку данных."""
    home = portable_home()
    os.environ[ENV_HOME] = str(home)
    return home
