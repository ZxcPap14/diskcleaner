"""Entry point: python -m disk_cleaner_app

CLI-режимы:
    python -m disk_cleaner_app                    — обычный GUI
    python -m disk_cleaner_app --smart-clean      — тихая очистка 🟢-целей,
                                                    затем GUI
    python -m disk_cleaner_app --smart-clean --silent
                                                 — только тихая очистка, без GUI
    python -m disk_cleaner_app --smart-clean --deep-safe --silent
                                                 — тихая deep-очистка слоем A
    python -m disk_cleaner_app --self-test       — проверить сборку и записать
                                                 отчёт в %TEMP% без запуска GUI
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


def _run_silent_clean(mode: str) -> int:
    from disk_cleaner_app.services.auto_clean import run_silent_clean

    summary = run_silent_clean(mode=mode)
    from disk_cleaner_app.models.item import format_bytes

    label = summary.get("mode", "smart")
    skipped = summary.get("skipped", 0)
    print(
        f"Тихая очистка ({label}): целей {summary['targets']}, успешно "
        f"{summary['ok']}, ошибок {summary['failed']}, освобождено "
        f"{format_bytes(summary['freed'])}"
        + (f", пропущено действий {skipped}" if skipped else "")
    )
    return 0 if summary["failed"] == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="DiskCleaner Pro")
    parser.add_argument(
        "--smart-clean", action="store_true",
        help="выполнить тихую очистку безопасных целей",
    )
    parser.add_argument(
        "--deep-safe", action="store_true",
        help="тихая глубокая очистка безопасным набором (слой A, с --smart-clean)",
    )
    parser.add_argument(
        "--silent", action="store_true",
        help="не запускать GUI (только с --smart-clean)",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="проверить сборку, записать отчёт в %%TEMP%% и выйти",
    )
    args = parser.parse_args()

    _reconfigure_streams()

    if args.self_test:
        from disk_cleaner_app.selftest import run_self_test

        raise SystemExit(run_self_test())

    if args.smart_clean:
        from disk_cleaner_app.services.auto_clean import DEEP_SAFE_MODE, SMART_MODE

        mode = DEEP_SAFE_MODE if args.deep_safe else SMART_MODE
        code = _run_silent_clean(mode)
        if args.silent:
            raise SystemExit(code)

    from disk_cleaner_app.ui.app import main as run

    run()


if __name__ == "__main__":
    main()
