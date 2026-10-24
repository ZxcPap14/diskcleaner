"""TreemapCanvas — интерактивный treemap с drill-down (WinDirStat-style)."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any

import squarify

from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.treemap import TreemapNode
from disk_cleaner_app.ui.assets import treemap_palette
from disk_cleaner_app.ui.theme import ThemeManager


def _readable_text(hex_color: str) -> str:
    """Чёрный или белый текст в зависимости от яркости фона."""
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return "#ffffff"
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#101513" if luminance > 0.62 else "#ffffff"


class TreemapCanvas(tk.Canvas):
    """Canvas с squarified treemap, hover-подсветкой и drill-down."""

    def __init__(
        self,
        parent: Any,
        on_open_folder: Callable[[str], None] | None = None,
        on_breadcrumb: Callable[[str], None] | None = None,
        theme: ThemeManager | None = None,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        self._palette = treemap_palette(theme.is_dark if theme else True)
        self._on_open_folder = on_open_folder
        self._on_breadcrumb = on_breadcrumb
        self._nodes: list[TreemapNode] = []
        self._rect_ids: list[tuple[int, TreemapNode]] = []
        self._hover_id: int | None = None

        super().__init__(parent, highlightthickness=0, cursor="hand2", bd=0, **kwargs)
        self.bind("<Motion>", self._on_hover)
        self.bind("<Button-1>", self._on_click)
        if theme is not None:
            theme.register(self)

    # ── отрисовка ─────────────────────────────────────

    def draw(self, nodes: list[TreemapNode]) -> None:
        self.delete("all")
        self._nodes = nodes
        self._rect_ids = []
        self._hover_id = None

        if not nodes:
            c = self._theme.colors if self._theme else None
            self.create_text(
                self.winfo_width() // 2 or 300,
                self.winfo_height() // 2 or 200,
                text="Нет данных для отображения",
                fill=c.ON_SURFACE_VARIANT if c else "#9090b0",
                font=("Segoe UI", 13),
            )
            return

        sizes = [max(n.size, 1) for n in nodes]
        cw = max(self.winfo_width(), 100)
        ch = max(self.winfo_height(), 100)
        norm = squarify.normalize_sizes(sizes, cw, ch)
        rects = squarify.squarify(norm, 0, 0, cw, ch)

        background = self._theme.colors.SURFACE_LOW if self._theme else str(self["bg"])
        pad = 2
        for i, rect in enumerate(rects):
            if i >= len(nodes):
                break
            node = nodes[i]
            x0 = rect["x"] + pad
            y0 = rect["y"] + pad
            x1 = rect["x"] + rect["dx"] - pad
            y1 = rect["y"] + rect["dy"] - pad
            if x1 - x0 < 5 or y1 - y0 < 5:
                continue

            color = self._palette[i % len(self._palette)]
            cid = self.create_rectangle(
                x0, y0, x1, y1,
                fill=color, outline=background, width=2,
            )
            self._rect_ids.append((cid, node))
            node.x, node.y, node.w, node.h = x0, y0, x1 - x0, y1 - y0

            if x1 - x0 > 58 and y1 - y0 > 30:
                name = node.name if len(node.name) <= 22 else node.name[:20] + "…"
                self.create_text(
                    (x0 + x1) / 2, (y0 + y1) / 2 - 5,
                    text=f"{name}\n{format_bytes(node.size)}",
                    fill=_readable_text(color),
                    font=("Segoe UI", 8, "bold"),
                    justify="center",
                )

    def _on_hover(self, event) -> None:
        if self._hover_id is not None:
            try:
                self.itemconfigure(self._hover_id, width=2, outline=self._outline())
            except tk.TclError:
                pass
            self._hover_id = None

        for cid, _node in self._rect_ids:
            coords = self.coords(cid)
            if len(coords) >= 4 and coords[0] <= event.x <= coords[2] and \
                    coords[1] <= event.y <= coords[3]:
                self.itemconfigure(
                    cid, width=3,
                    outline=self._theme.colors.PRIMARY if self._theme else "#ffffff",
                )
                self._hover_id = cid
                break

    def _outline(self) -> str:
        if self._theme is not None:
            return self._theme.colors.SURFACE_LOW
        return str(self["bg"])

    def _on_click(self, event) -> None:
        for cid, node in self._rect_ids:
            coords = self.coords(cid)
            if len(coords) >= 4 and coords[0] <= event.x <= coords[2] and \
                    coords[1] <= event.y <= coords[3]:
                if node.is_dir and self._on_open_folder:
                    self._on_open_folder(node.path)
                elif not node.is_dir and self._on_breadcrumb:
                    self._on_breadcrumb(f"📄 {node.name}")
                break

    def refresh_theme(self) -> None:
        if self._theme is None:
            return
        c = self._theme.colors
        self._palette = treemap_palette(self._theme.is_dark)
        self.configure(bg=c.SURFACE_LOW)
        self.draw(self._nodes)
