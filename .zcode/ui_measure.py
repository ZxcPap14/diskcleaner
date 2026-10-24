"""Диагностика высот ключевых контейнеров."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
tmp = Path(tempfile.mkdtemp(prefix="dc-measure-"))
os.environ["APPDATA"] = str(tmp)
os.environ["LOCALAPPDATA"] = str(tmp)

from disk_cleaner_app.ui.app import MainWindow  # noqa: E402


def pump(window, n=8):
    for _ in range(n):
        window.root.update_idletasks()
        window.root.update()


def report(window, names):
    for name, widget in names:
        try:
            print(f"{name:28} {widget.winfo_width():5}x{widget.winfo_height():4} "
                  f"req={widget.winfo_reqheight():4}")
        except Exception as exc:
            print(name, "ERR", exc)


def main() -> int:
    window = MainWindow()
    window.root.geometry("1180x760+40+40")
    window.root.deiconify()
    pump(window, 10)

    window._switch_view("dashboard")
    pump(window, 8)
    dv = window.views["dashboard"]
    body = dv._body
    inner = body._parent_frame if hasattr(body, "_parent_frame") else None
    print("== dashboard ==")
    report(window, [
        ("root", window.root),
        ("header", window.header),
        ("statusbar", window.statusbar),
        ("views_frame", window.views_frame),
        ("dashboard", dv),
        ("body", body),
        ("body inner", inner),
    ])
    for child in body.winfo_children():
        report(window, [(f"  body child {child.winfo_class()}", child)])
    middle = body.winfo_children()[1]
    for child in middle.winfo_children():
        report(window, [(f"    middle child {child.winfo_class()}", child)])
        for sub in child.winfo_children():
            report(window, [(f"      sub {sub.winfo_class()}", sub)])

    window._switch_view("disks")
    pump(window, 8)
    dv = window.views["disks"]
    print("== disks ==")
    report(window, [
        ("disks", dv), ("tabs", dv.tabs),
        ("smart pane", dv._smart_pane), ("scan pane", dv._scan_pane),
        ("tree", dv.tree), ("details", dv.details),
        ("scan result", dv.scan_result),
    ])

    window.root.geometry("1024x660+40+40")
    pump(window, 10)
    window._switch_view("dashboard")
    pump(window, 10)
    dv = window.views["dashboard"]
    body = dv._body
    print("== 1024x660 dashboard ==")
    report(window, [
        ("root", window.root), ("header", window.header),
        ("statusbar", window.statusbar), ("dashboard", dv),
        ("content", body), ("viewport", body._parent_canvas),
        ("scrollbar visible", body._scrollbar),
    ])
    window._switch_view("disks")
    pump(window, 10)
    dv = window.views["disks"]
    print("== 1024x660 disks ==")
    report(window, [
        ("disks", dv), ("smart pane", dv._smart_pane),
        ("scan pane", dv._scan_pane), ("details", dv.details),
    ])

    window._on_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
