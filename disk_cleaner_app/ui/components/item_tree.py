"""CleanerTree — дерево целей очистки с чекбоксами (MD3)."""
from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

from disk_cleaner_app.cleaners.base import BaseCleaner
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.item import SafetyLevel, format_bytes
from disk_cleaner_app.ui.assets import FONT_LABEL_LARGE
from disk_cleaner_app.ui.components.md3 import style_treeview
from disk_cleaner_app.ui.theme import ThemeManager

GROUP_ORDER = {
    "🖥️ Система": 0,
    "🌐 Браузеры": 1,
    "📦 Dev Tools": 2,
    "🤖 AI/ML": 3,
    "💬 Приложения": 4,
    "🧩 Пользовательские": 5,
    "🧠 Auto-discovered": 6,
}


class CleanerTree(ctk.CTkFrame):
    """Дерево с чекбоксами, группировкой по категориям, поиском и сортировкой."""

    def __init__(self, parent, theme: ThemeManager, config: ConfigManager, **kwargs):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._config = config
        self._cleaners: list[BaseCleaner] = []
        self._visible: list[BaseCleaner] = []
        self._shown: list[BaseCleaner] = []
        self._checked: dict[str, bool] = {}
        self._group_rows: dict[str, list[str]] = {}
        self._mode: str = "easy"
        self._query: str = ""
        self._sort_key: str = ""
        self._sort_desc: bool = True
        self._collapsed: set[str] = set()
        self.configure(fg_color="transparent")
        self._build()
        theme.register(self)

    def _build(self) -> None:
        c = self._theme.colors
        style_treeview("Cleaner", self._theme)

        cols = ("check", "name", "size", "safety", "group")
        self.tree = ttk.Treeview(
            self, columns=cols, show="headings",
            selectmode="none", style="Cleaner.Treeview", height=14,
        )
        self.tree.heading("check", text="")
        self.tree.heading("name", text="Цель очистки", anchor="w",
                          command=lambda: self.set_sort("name"))
        self.tree.heading("size", text="Размер", anchor="e",
                          command=lambda: self.set_sort("size"))
        self.tree.heading("safety", text="", anchor="center")
        self.tree.heading("group", text="Категория", anchor="w",
                          command=lambda: self.set_sort("group"))

        self.tree.column("check", width=38, minwidth=34, anchor="center", stretch=False)
        self.tree.column("name", width=390, minwidth=260)
        self.tree.column("size", width=122, minwidth=90, anchor="e")
        self.tree.column("safety", width=38, minwidth=32, anchor="center", stretch=False)
        self.tree.column("group", width=135, minwidth=100)

        self.tree.tag_configure("safe", foreground=c.SUCCESS)
        self.tree.tag_configure("caution", foreground=c.WARNING)
        self.tree.tag_configure("advanced", foreground=c.ERROR)
        self.tree.tag_configure("not_scanned", foreground=c.TEXT_MUTED)
        self.tree.tag_configure(
            "group", foreground=c.ON_SURFACE, background=c.SURFACE_CONTAINER,
            font=FONT_LABEL_LARGE,
        )

        self._scroll = ctk.CTkScrollbar(
            self, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=c.OUTLINE_VARIANT,
            button_hover_color=c.OUTLINE,
        )
        self.tree.configure(yscrollcommand=self._scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self._scroll.pack(side="right", fill="y", padx=(2, 0))
        self.tree.bind("<ButtonRelease-1>", self._on_click)

    # ── Populate ─────────────────────────────────────

    def populate(self, cleaners: list[BaseCleaner]) -> None:
        self._cleaners = cleaners
        self._clear()

        safe_only = self._config.get("safe_mode", True)
        visible = [c for c in cleaners if self._mode == "advanced"
                   or c.safety == SafetyLevel.SAFE]
        self._visible = visible
        visible_ids = {c.id for c in visible}

        for c in cleaners:
            if c.id not in visible_ids:
                self._checked[c.id] = False
            elif c.id not in self._checked:
                self._checked[c.id] = not (safe_only and c.safety == SafetyLevel.ADVANCED)

        self._render()

    def _render(self) -> None:
        self._clear()
        self._group_rows = {}

        query = self._query.strip().lower()
        shown = [
            c for c in self._visible
            if not query or query in c.name.lower() or query in c.group.lower()
        ]
        shown = self._apply_sort(shown)
        self._shown = shown

        grouped = not query and not self._sort_key
        if grouped:
            groups: dict[str, list[BaseCleaner]] = {}
            for item in shown:
                groups.setdefault(item.group, []).append(item)
            for group, items in groups.items():
                group_iid = f"group::{group}"
                self._group_rows[group_iid] = [c.id for c in items]
                total = sum(max(0, c.size) for c in items)
                self.tree.insert(
                    "", "end", iid=group_iid,
                    values=(
                        self._group_mark([c.id for c in items]),
                        self._group_title(group, len(items)),
                        format_bytes(total) if any(c.scanned for c in items) else "—",
                        "",
                        "",
                    ),
                    tags=("group",),
                )
                if group not in self._collapsed:
                    for item in items:
                        self._insert_item(item)
        else:
            for item in shown:
                self._insert_item(item)

        self._update_headings()

    def _insert_item(self, item: BaseCleaner) -> None:
        iid = item.id
        checked = "☑" if self._checked.get(iid, False) else "☐"
        if item.scan_error:
            sz = "ошибка"
        elif item.scanned:
            sz = format_bytes(item.size)
        else:
            sz = "—"
        tag = self._safety_tag(item)
        self.tree.insert(
            "", "end", iid=iid,
            values=(checked, f"  {item.name}", sz, item.safety, item.group),
            tags=(tag,),
        )

    def _group_mark(self, ids: list[str]) -> str:
        if not ids:
            return "☐"
        states = [bool(self._checked.get(cid, False)) for cid in ids]
        if all(states):
            return "☑"
        if any(states):
            return "▣"
        return "☐"

    def _group_title(self, group: str, count: int) -> str:
        arrow = "▶" if group in self._collapsed else "▼"
        return f"{arrow} {group}  ({count})"

    def toggle_group(self, group: str) -> None:
        if group in self._collapsed:
            self._collapsed.discard(group)
        else:
            self._collapsed.add(group)
        self._render()

    def set_collapsed(self, group: str, collapsed: bool = True) -> None:
        if collapsed:
            self._collapsed.add(group)
        else:
            self._collapsed.discard(group)
        self._render()

    def is_collapsed(self, group: str) -> bool:
        return group in self._collapsed

    def collapse_all(self) -> None:
        self._collapsed = {group for group in self._group_names()}
        self._render()

    def expand_all(self) -> None:
        self._collapsed.clear()
        self._render()

    def _group_names(self) -> list[str]:
        return [group for group in dict.fromkeys(c.group for c in self._visible)]

    def _refresh_group_row(self, group_iid: str) -> None:
        ids = self._group_rows.get(group_iid, [])
        try:
            vals = list(self.tree.item(group_iid, "values"))
        except Exception:
            return
        if vals:
            vals[0] = self._group_mark(ids)
            self.tree.item(group_iid, values=vals)

    def _apply_sort(self, items: list[BaseCleaner]) -> list[BaseCleaner]:
        if not self._sort_key:
            groups: dict[str, list[BaseCleaner]] = {}
            for c in items:
                groups.setdefault(c.group, []).append(c)
            ordered: list[BaseCleaner] = []
            for group in sorted(groups, key=lambda g: GROUP_ORDER.get(g, 99)):
                chunk = groups[group]
                chunk.sort(key=lambda x: (SafetyLevel.ORDER.get(x.safety, 99), x.name))
                ordered.extend(chunk)
            return ordered

        reverse = self._sort_desc
        if self._sort_key == "size":
            return sorted(items, key=lambda c: (c.size, c.name.lower()), reverse=reverse)
        if self._sort_key == "group":
            return sorted(
                items,
                key=lambda c: (GROUP_ORDER.get(c.group, 99), c.name.lower()),
                reverse=reverse,
            )
        return sorted(items, key=lambda c: c.name.lower(), reverse=reverse)

    def _update_headings(self) -> None:
        arrows = {"name": "Цель очистки", "size": "Размер", "group": "Категория"}
        for key, label in arrows.items():
            if key == self._sort_key:
                label += " ↓" if self._sort_desc else " ↑"
            self.tree.heading(key, text=label)

    def set_sort(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = key == "size"
        self._render()

    def set_filter(self, query: str) -> None:
        self._query = query or ""
        self._render()

    def clear_sort(self) -> None:
        self._sort_key = ""
        self._sort_desc = True
        self._collapsed.clear()
        self._render()

    def get_shown_count(self) -> int:
        return len(self._shown)

    def _safety_tag(self, item: BaseCleaner) -> str:
        if item.safety == SafetyLevel.SAFE:
            return "safe"
        elif item.safety == SafetyLevel.CAUTION:
            return "caution"
        return "advanced"

    def _clear(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)

    # ── Click handling ───────────────────────────────

    def _on_click(self, e) -> None:
        iid = self.tree.identify_row(e.y)
        if not iid:
            return
        region = self.tree.identify_region(e.x, e.y)
        if region not in ("cell", "tree"):
            return

        if iid.startswith("group::"):
            group = iid[len("group::"):]
            column = ""
            try:
                column = self.tree.column(self.tree.identify_column(e.x), "id")
            except Exception:
                column = ""
            if column == "check":
                ids = self._group_rows.get(iid, [])
                turn_on = not all(self._checked.get(cid, False) for cid in ids)
                for cid in ids:
                    self._checked[cid] = turn_on
                self._refresh_checkmarks()
            else:
                self.toggle_group(group)
            return

        self._checked[iid] = not self._checked.get(iid, False)
        vals = list(self.tree.item(iid, "values"))
        if vals:
            vals[0] = "☑" if self._checked[iid] else "☐"
            self.tree.item(iid, values=vals)
        for group_iid in self._group_rows:
            self._refresh_group_row(group_iid)

    # ── Selection ────────────────────────────────────

    def select_all(self) -> None:
        for item in self._visible:
            self._checked[item.id] = True
        self._refresh_checkmarks()

    def deselect_all(self) -> None:
        for item in self._visible:
            self._checked[item.id] = False
        self._refresh_checkmarks()

    def select_safe(self) -> None:
        for item in self._visible:
            self._checked[item.id] = item.safety == SafetyLevel.SAFE
        self._refresh_checkmarks()

    def _refresh_checkmarks(self) -> None:
        for item in self._shown:
            try:
                vals = list(self.tree.item(item.id, "values"))
            except Exception:
                continue
            if vals:
                vals[0] = "☑" if self._checked.get(item.id, False) else "☐"
                self.tree.item(item.id, values=vals)
        for group_iid in self._group_rows:
            self._refresh_group_row(group_iid)

    # ── Getters ──────────────────────────────────────

    def get_selected(self) -> list[BaseCleaner]:
        return [c for c in self._visible if self._checked.get(c.id, False)]

    def get_all_cleaners(self) -> list[BaseCleaner]:
        return self._cleaners

    def get_visible_count(self) -> int:
        return len(self._visible)

    def get_visible_ids(self) -> set[str]:
        return {c.id for c in self._visible}

    def set_checked(self, cleaner_id: str, value: bool = True) -> bool:
        if cleaner_id not in self.get_visible_ids():
            return False
        self._checked[cleaner_id] = bool(value)
        self._refresh_checkmarks()
        return True

    def get_selected_count(self) -> int:
        return sum(1 for c in self._visible if self._checked.get(c.id, False))

    def get_selected_total(self) -> int:
        return sum(max(0, c.size) for c in self._visible if self._checked.get(c.id, False))

    # ── Mode ─────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def refresh_theme(self) -> None:
        c = self._theme.colors
        style_treeview("Cleaner", self._theme)
        self.tree.tag_configure("safe", foreground=c.SUCCESS)
        self.tree.tag_configure("caution", foreground=c.WARNING)
        self.tree.tag_configure("advanced", foreground=c.ERROR)
        self.tree.tag_configure("not_scanned", foreground=c.TEXT_MUTED)
        self.tree.tag_configure(
            "group", foreground=c.ON_SURFACE, background=c.SURFACE_CONTAINER,
            font=FONT_LABEL_LARGE,
        )
        self._scroll.configure(
            button_color=c.OUTLINE_VARIANT, button_hover_color=c.OUTLINE,
            fg_color="transparent",
        )
