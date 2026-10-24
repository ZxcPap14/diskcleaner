"""Entry point: python -m disk_cleaner_app"""
from __future__ import annotations


def main() -> None:
    from disk_cleaner_app.ui.app import main as run

    run()


if __name__ == "__main__":
    main()
