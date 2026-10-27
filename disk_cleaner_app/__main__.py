"""Entry point: python -m disk_cleaner_app

CLI-режимы:
    python -m disk_cleaner_app                    — обычный GUI
    python -m disk_cleaner_app --smart-clean      — тихая очистка 🟢-целей,
                                                    затем GUI
    python -m disk_cleaner_app --smart-clean --silent
                                                 — только тихая очистка, без GUI
    python -m disk_cleaner_app --smart-clean --deep-safe --silent
                                                 — тихая deep-очистка слоем A
    python -m disk_cleaner_app --scan            — скан preset'а, без удаления
    python -m disk_cleaner_app --clean safe      — скан + очистка preset'а
    python -m disk_cleaner_app --clean safe --report out.json
                                                 — то же с JSON-отчётом
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


def _run_cli(scan: bool, clean_preset: str | None, report: str | None) -> int:
    from disk_cleaner_app.services.cli_clean import run_cli_scan_clean

    if clean_preset:
        return run_cli_scan_clean(preset=clean_preset, clean=True, report_path=report)
    return run_cli_scan_clean(clean=False, report_path=report)


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
        "--scan", action="store_true",
        help="сканировать preset и показать размеры, без удаления",
    )
    parser.add_argument(
        "--clean", metavar="PRESET", choices=("safe", "deep-safe"),
        help="скан + очистка preset'а (safe или deep-safe), без GUI",
    )
    parser.add_argument(
        "--report", metavar="PATH",
        help="записать JSON-отчёт (с --scan или --clean)",
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

    if args.scan or args.clean:
        raise SystemExit(_run_cli(args.scan, args.clean, args.report))

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
