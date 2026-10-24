"""Entry point: python -m disk_cleaner_app

CLI-режимы:
    python -m disk_cleaner_app                    — обычный GUI
    python -m disk_cleaner_app --smart-clean      — тихая очистка 🟢-целей,
                                                    затем GUI
    python -m disk_cleaner_app --smart-clean --silent
                                                 — только тихая очистка, без GUI
"""
from __future__ import annotations

import argparse
import sys


def _reconfigure_streams() -> None:
    # Консоль Windows часто cp1251 и не умеет эмодзи.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _run_silent_clean() -> int:
    from disk_cleaner_app.services.auto_clean import run_silent_clean

    summary = run_silent_clean()
    from disk_cleaner_app.models.item import format_bytes

    print(
        f"Smart Clean: целей {summary['targets']}, успешно {summary['ok']}, "
        f"ошибок {summary['failed']}, освобождено "
        f"{format_bytes(summary['freed'])}"
    )
    return 0 if summary["failed"] == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="DiskCleaner Pro")
    parser.add_argument(
        "--smart-clean", action="store_true",
        help="выполнить тихую очистку безопасных целей",
    )
    parser.add_argument(
        "--silent", action="store_true",
        help="не запускать GUI (только с --smart-clean)",
    )
    args = parser.parse_args()

    _reconfigure_streams()

    if args.smart_clean:
        code = _run_silent_clean()
        if args.silent:
            raise SystemExit(code)

    from disk_cleaner_app.ui.app import main as run

    run()


if __name__ == "__main__":
    main()
