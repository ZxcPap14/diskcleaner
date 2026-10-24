"""Скриншоты всех экранов в светлой и тёмной теме."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

smoke_appdata = Path(tempfile.mkdtemp(prefix="dc-shots-"))
os.environ["APPDATA"] = str(smoke_appdata)
os.environ["LOCALAPPDATA"] = str(smoke_appdata)

from disk_cleaner_app.ui.app import MainWindow  # noqa: E402

VIEWS = [
    ("dashboard", "01-dashboard"),
    ("clean", "02-clean"),
    ("analyzer", "03-analyzer"),
    ("disks", "04-disks"),
    ("duplicates", "05-duplicates"),
    ("history", "06-history"),
    ("startup", "07-startup"),
    ("uninstaller", "08-uninstaller"),
    ("settings", "09-settings"),
]


def pump(window: MainWindow, times: int = 8) -> None:
    for _ in range(times):
        window.root.update_idletasks()
        window.root.update()
        time.sleep(0.03)


def grab(window: MainWindow, target: Path) -> None:
    pump(window, 10)
    x = window.root.winfo_rootx()
    y = window.root.winfo_rooty()
    w = window.root.winfo_width()
    h = window.root.winfo_height()
    image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    image.save(target)
    print("saved", target, image.size)


def main() -> int:
    out = ROOT / ".zcode" / "shots"
    out.mkdir(parents=True, exist_ok=True)

    size = sys.argv[1] if len(sys.argv) > 1 else "1180x760"
    suffix = sys.argv[2] if len(sys.argv) > 2 else ""
    modes = ("light", "dark") if not suffix else ("light",)

    window = MainWindow()
    window.root.geometry(f"{size}+40+40")
    window.root.attributes("-topmost", True)
    window.root.deiconify()
    window.root.lift()
    pump(window, 10)

    for mode in modes:
        window.theme.mode = mode
        window._apply_theme()
        pump(window, 6)
        for view_id, filename in VIEWS:
            window._switch_view(view_id)
            pump(window, 8)
            if view_id == "disks":
                # SMART читается в фоне через PowerShell.
                for _ in range(40):
                    window.root.update_idletasks()
                    window.root.update()
                    time.sleep(0.05)
            grab(window, out / f"{filename}-{mode}{suffix}.png")

    window.root.attributes("-topmost", False)
    window._on_close()
    print("SMOKE SHOTS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
