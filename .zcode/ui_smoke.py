"""UI smoke: построить окно, пройти все экраны и темы без mainloop."""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

smoke_appdata = Path(tempfile.mkdtemp(prefix="dc-smoke-"))
os.environ["APPDATA"] = str(smoke_appdata)
os.environ["LOCALAPPDATA"] = str(smoke_appdata)

from disk_cleaner_app.ui.app import MainWindow  # noqa: E402


def pump(window: MainWindow, times: int = 4) -> None:
    for _ in range(times):
        window.root.update_idletasks()
        window.root.update()


def main() -> int:
    errors: list[str] = []
    window = MainWindow()
    pump(window, 8)

    views = [
        "dashboard", "clean", "analyzer", "disks", "duplicates",
        "history", "startup", "uninstaller", "settings",
    ]
    for view_id in views:
        try:
            window._switch_view(view_id)
            pump(window, 6)
            print(f"OK view: {view_id}")
        except Exception:
            errors.append(f"view {view_id}")
            traceback.print_exc()

    for mode in ("light", "dark", "system"):
        try:
            window.theme.mode = mode
            window._apply_theme()
            pump(window, 6)
            print(f"OK theme: {mode}")
        except Exception:
            errors.append(f"theme {mode}")
            traceback.print_exc()

    # Открыть/закрыть журнал в статус-баре
    try:
        window.statusbar._toggle_log()
        pump(window, 2)
        window.statusbar.log("проверка журнала")
        window.statusbar._toggle_log()
        pump(window, 2)
        print("OK statusbar log")
    except Exception:
        errors.append("statusbar log")
        traceback.print_exc()

    try:
        window.root.update_idletasks()
        window.root.update()
        width = window.root.winfo_width()
        height = window.root.winfo_height()
        print(f"window: {width}x{height}")
    except Exception:
        traceback.print_exc()

    window._on_close()
    print("APPDATA:", smoke_appdata)
    if errors:
        print("FAILED:", ", ".join(errors))
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
