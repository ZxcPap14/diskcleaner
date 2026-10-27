"""🔍 Глубокая очистка — слои, план до удаления и честный результат."""
from __future__ import annotations

import datetime
import logging
import os
import threading
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    CleanOptions,
    reset_scan_cancel,
    set_scan_cancel,
)
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.history import HistoryManager
from disk_cleaner_app.models.item import SafetyLevel, format_bytes
from disk_cleaner_app.models.target import (
    LAYER_COMPONENTS,
    LAYER_INVENTORY,
    LAYER_LEFTOVERS,
    LAYER_SAFE,
    LAYERS,
    layer_hint,
    layer_title,
)
from disk_cleaner_app.services.cleaner import CleanEngine, CleanResult
from disk_cleaner_app.services.elevation import is_admin
from disk_cleaner_app.services.error_kinds import (
    KIND_TITLES,
    classify_path,
    remediation,
    summarize_kinds,
)
from disk_cleaner_app.services.planner import OperationPlan
from disk_cleaner_app.services.reports import export_plan_csv, export_plan_json
from disk_cleaner_app.services.restore_point import create_restore_point
from disk_cleaner_app.services.scanner import ScanEngine
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_LABEL,
    FONT_LABEL_LARGE,
    FONT_MONO_SMALL,
    FONT_TITLE_MEDIUM,
    RADIUS_MD,
    SPACE_2,
    SPACE_3,
)
from disk_cleaner_app.ui.components.large_files_dialog import LargeFilesDialog
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDCheckbox,
    MDIconButton,
    MDLabel,
    MDPill,
    MDProgress,
    MDScrollArea,
    MDTextbox,
    PageHeader,
)
from disk_cleaner_app.ui.dispatch import UiDispatcher
from disk_cleaner_app.ui.theme import ThemeManager

log = logging.getLogger(__name__)

SAFETY_ROLES = {
    SafetyLevel.SAFE: "success",
    SafetyLevel.CAUTION: "warning",
    SafetyLevel.ADVANCED: "error",
}


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _short_path(path: Path | None, limit: int = 72) -> str:
    if path is None:
        return "команда"
    text = str(path)
    return text if len(text) <= limit else "…" + text[-(limit - 1):]


def _reason_of(path: str | Path) -> str:
    """Причина неудачи удаления для конкретного пути («занято», «отказ»…)."""
    try:
        return KIND_TITLES.get(classify_path(path), "причина неясна")
    except Exception:
        return "причина неясна"


def _bind_click(widget, callback: Callable[[], None]) -> None:
    """Повесить клик на контейнер и все его дочерние виджеты."""
    widget.bind("<Button-1>", lambda _event: callback())
    for child in widget.winfo_children():
        _bind_click(child, callback)


def _volumes_text(values: dict[str, int]) -> str:
    return " · ".join(
        f"{volume} {format_bytes(size)}"
        for volume, size in sorted(values.items())
        if size > 0
    )


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Русская форма слова для числа: 1 цель, 2 цели, 5 целей."""
    n = abs(count) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


class _LayerCard(ctk.CTkFrame):
    """Компактная карточка слоя: размер, число целей и выбор слоя."""

    def __init__(
        self,
        parent,
        theme: ThemeManager,
        layer: str,
        on_click: Callable[[str], None],
    ) -> None:
        super().__init__(
            parent,
            fg_color=theme.colors.SURFACE_LOW,
            corner_radius=RADIUS_MD,
            border_width=1,
            border_color=theme.colors.OUTLINE_VARIANT,
            cursor="hand2",
        )
        self._theme = theme
        self.layer = layer
        self._on_click = on_click
        self._selected = 0
        self._has_targets = False
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        top.grid_columnconfigure(1, weight=1)

        self._badge = ctk.CTkLabel(
            top, text=layer, width=20, height=20, corner_radius=6,
            fg_color=theme.colors.PRIMARY_CONTAINER,
            text_color=theme.colors.ON_PRIMARY_CONTAINER,
            font=FONT_TITLE_MEDIUM,
        )
        self._badge.grid(row=0, column=0, sticky="w")

        self._size = ctk.CTkLabel(
            top, text="—", font=FONT_LABEL_LARGE,
            text_color=theme.colors.ON_SURFACE, anchor="e",
        )
        self._size.grid(row=0, column=1, sticky="e")

        self._title = ctk.CTkLabel(
            self, text=layer_title(layer), font=FONT_CAPTION,
            text_color=theme.colors.ON_SURFACE_VARIANT, anchor="w",
            justify="left", wraplength=132,
        )
        self._title.grid(row=1, column=0, sticky="ew", padx=10)

        self._count = ctk.CTkLabel(
            self, text="", font=FONT_CAPTION,
            text_color=theme.colors.TEXT_MUTED, anchor="w",
        )
        self._count.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))

        _bind_click(self, lambda: self._on_click(self.layer))
        theme.register(self)

    def set_stats(
        self,
        size: int,
        count: int,
        selected: int,
        scanned: bool,
    ) -> None:
        self._selected = selected
        self._has_targets = count > 0
        self.configure(cursor="hand2" if self._has_targets else "arrow")
        self._size.configure(
            text=format_bytes(size) if scanned and self._has_targets else "—"
        )
        parts = [f"{count} {_plural(count, 'цель', 'цели', 'целей')}"]
        if selected:
            parts.append(f"выбрано {selected}")
        self._count.configure(
            text=" · ".join(parts) if self._has_targets else "нет целей"
        )
        self._apply()

    def _apply(self) -> None:
        c = self._theme.colors
        self.configure(
            fg_color=c.SURFACE_LOW,
            border_color=c.PRIMARY if self._selected else c.OUTLINE_VARIANT,
        )
        self._badge.configure(
            fg_color=c.PRIMARY_CONTAINER if self._has_targets else c.SURFACE_HIGH,
            text_color=(
                c.ON_PRIMARY_CONTAINER if self._has_targets else c.TEXT_MUTED
            ),
        )
        self._size.configure(
            text_color=c.ON_SURFACE if self._has_targets else c.TEXT_MUTED
        )
        self._title.configure(
            text_color=c.ON_SURFACE_VARIANT if self._has_targets else c.TEXT_MUTED
        )
        self._count.configure(
            text_color=c.PRIMARY if self._selected else c.TEXT_MUTED
        )

    def refresh_theme(self) -> None:
        self._apply()


class _TargetRow(ctk.CTkFrame):
    """Строка цели: чекбокс, объяснение, риск и размер."""

    def __init__(
        self,
        parent,
        theme: ThemeManager,
        cleaner: BaseCleaner,
        admin: bool,
        on_toggle: Callable[[BaseCleaner, bool], None],
        on_info: Callable[[BaseCleaner], None],
    ) -> None:
        super().__init__(
            parent, fg_color=theme.colors.SURFACE, corner_radius=10,
            cursor="hand2",
        )
        self._theme = theme
        self.cleaner = cleaner
        self._on_toggle = on_toggle
        self._selected = False
        self.grid_columnconfigure(1, weight=1)

        self.check = MDCheckbox(
            self, theme, size=20, bg_color=theme.colors.SURFACE,
            command=self._checked,
        )
        self.check.grid(row=0, column=0, rowspan=2, padx=(8, 8), pady=9)

        self.name = MDLabel(
            self, theme, cleaner.name, role="on_surface",
            font=FONT_LABEL_LARGE, anchor="w", justify="left", wraplength=480,
        )
        self.name.grid(row=0, column=1, sticky="ew", pady=(7, 0))

        self.meta = MDLabel(
            self, theme, "", role="muted", font=FONT_CAPTION,
            anchor="w", justify="left", wraplength=480,
        )
        self.meta.grid(row=1, column=1, sticky="ew", pady=(0, 7))

        self.size_label = MDLabel(
            self, theme, "—", role="secondary",
            font=FONT_LABEL_LARGE, anchor="e", width=76,
        )
        self.size_label.grid(row=0, column=2, rowspan=2, padx=(8, 4))

        if cleaner.admin_required and not admin:
            badge, role = "🔒", "warning"
        elif cleaner.layer == LAYER_LEFTOVERS:
            badge, role = "♻", "tertiary"
        else:
            badge = cleaner.safety
            role = SAFETY_ROLES.get(cleaner.safety, "secondary")

        self.badge = MDLabel(
            self, theme, badge, role=role, font=FONT_LABEL, width=22,
        )
        self.badge.grid(row=0, column=3, rowspan=2, padx=(0, 2))

        self.info = MDIconButton(
            self, theme, "ⓘ", lambda: on_info(cleaner),
            kind="standard", size=26, font=("Segoe UI", 11),
        )
        self.info.grid(row=0, column=4, rowspan=2, padx=(0, 6))

        for widget in (self, self.name, self.meta, self.size_label, self.badge):
            widget.bind("<Button-1>", self._row_clicked)

        self.update_state()

    # ── состояние ─────────────────────────────────────

    def _checked(self) -> None:
        self._on_toggle(self.cleaner, bool(self.check.get()))

    def _row_clicked(self, _event=None) -> None:
        self._on_toggle(self.cleaner, not self._selected)

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, value: bool) -> None:
        self._selected = bool(value)
        if self._selected:
            self.check.select()
        else:
            self.check.deselect()
        self._paint_background()

    def _paint_background(self) -> None:
        c = self._theme.colors
        background = c.SURFACE_LOW if self._selected else c.SURFACE
        self.configure(fg_color=background)
        self.check.set_bg(background)

    def update_state(self) -> None:
        cleaner = self.cleaner
        size = cleaner.size if cleaner.scanned else None
        self.size_label.configure(
            text="—" if size is None else format_bytes(size)
        )

        parts = [cleaner.why or cleaner.description or ""]
        if cleaner.layer == LAYER_LEFTOVERS:
            parts.append("всегда в корзину")
        if cleaner.admin_required and not is_admin():
            parts.append("нужны права администратора")
        if cleaner.min_age_hours:
            parts.append(f"старше {cleaner.min_age_hours} ч")
        if cleaner.scan_error:
            parts.append(f"ошибка сканирования: {cleaner.scan_error}")
        self.meta.configure(text=_short(" · ".join(p for p in parts if p), 170))

    def refresh_theme(self) -> None:
        self._paint_background()


class _LayerGroup(ctk.CTkFrame):
    """Заголовок слоя со списком целей и сворачиванием."""

    def __init__(
        self,
        parent,
        theme: ThemeManager,
        layer: str,
        on_toggle_layer: Callable[[str, bool], None],
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self._theme = theme
        self.layer = layer
        self._on_toggle_layer = on_toggle_layer
        self._syncing = False
        self._collapsed = False
        self._builder: Callable[[_LayerGroup], None] | None = None
        self._built = False

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(6, 2))

        self.check = MDCheckbox(
            header, theme, size=18, bg_color=theme.colors.SURFACE,
            command=self._header_toggled,
        )
        self.check.pack(side="left", padx=(6, 8))

        self.title = MDLabel(
            header, theme, f"{layer} · {layer_title(layer)}",
            role="on_surface", font=FONT_LABEL_LARGE, anchor="w",
        )
        self.title.pack(side="left")

        self.total = MDLabel(
            header, theme, "", role="muted", font=FONT_CAPTION, anchor="e",
        )
        self.total.pack(side="right", padx=(8, 4))

        self.chevron = MDIconButton(
            header, theme, "▾", self.toggle_collapsed,
            kind="standard", size=24, font=("Segoe UI", 10),
        )
        self.chevron.pack(side="right")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x")
        for widget in (self.title, self.total):
            widget.bind("<Button-1>", lambda _event: self.toggle_collapsed())

        self.hint = MDLabel(
            self, theme, layer_hint(layer), role="muted",
            font=FONT_CAPTION, anchor="w", justify="left", wraplength=760,
        )
        self.hint.pack(fill="x", padx=34, pady=(0, 2), before=self.body)

        theme.register(self)
        # Слои свёрнуты: развёрнутые 102 строки = ~1100 виджетов, и каждый
        # шаг ресайза перерисовывал их все.
        self.toggle_collapsed()

    def set_builder(self, builder: Callable[[_LayerGroup], None]) -> None:
        """Строки слоя создаются при первом раскрытии, а не при сборке страницы."""
        self._builder = builder

    def add_row(self, row: _TargetRow) -> None:
        row.pack(fill="x", padx=(4, 0), pady=1)

    def add_action(
        self,
        label: str,
        command: Callable[[], None],
        hint: str = "",
    ) -> None:
        """Действие слоя, которое ничего не выбирает и не удаляет."""
        holder = ctk.CTkFrame(self.body, fg_color="transparent")
        holder.pack(fill="x", padx=(34, 8), pady=(4, 8))
        MDButton(
            holder, self._theme, label, command,
            kind="tonal", width=214, height=32,
        ).pack(side="left")
        if hint:
            MDLabel(
                holder, self._theme, hint, role="muted",
                font=FONT_CAPTION, anchor="w",
            ).pack(side="left", padx=(10, 0))

    def _header_toggled(self) -> None:
        if self._syncing:
            return
        self._on_toggle_layer(self.layer, bool(self.check.get()))

    def set_state(self, selected: int, total: int, size: int, scanned: bool) -> None:
        self._syncing = True
        if selected and selected == total:
            self.check.select()
        else:
            self.check.deselect()
        self._syncing = False

        parts = [f"{total} {_plural(total, 'цель', 'цели', 'целей')}"]
        if selected:
            parts.append(f"выбрано {selected}")
        if scanned:
            parts.append(format_bytes(size))
        self.total.configure(text=" · ".join(parts))

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.body.pack_forget()
            self.hint.pack_forget()
            self.chevron.configure(text="▸")
            return
        if not self._built and self._builder is not None:
            self._built = True
            self._builder(self)
        self.body.pack(fill="x")
        self.hint.pack(fill="x", padx=34, pady=(0, 2), before=self.body)
        self.chevron.configure(text="▾")

    def refresh_theme(self) -> None:
        pass


class DeepCleanView(ctk.CTkFrame):
    """Экран глубокой очистки: анализ, слои, план и результат."""

    def __init__(
        self,
        parent,
        theme: ThemeManager,
        config: ConfigManager,
        on_log: Callable[[str], None],
        statusbar=None,
        on_reload: Callable[[], None] | None = None,
        on_elevate: Callable[[], None] | None = None,
        get_drive: Callable[[], str | None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._config = config
        self._on_log = on_log
        self._statusbar = statusbar
        self._on_reload = on_reload
        self._on_elevate = on_elevate
        self._get_drive = get_drive

        self._scan_engine = ScanEngine()
        self._clean_engine = CleanEngine()
        self._cleaners: list[BaseCleaner] = []
        self._selected: set[str] = set()
        self._rows: dict[str, _TargetRow] = {}
        self._groups: dict[str, _LayerGroup] = {}
        self._cards: dict[str, _LayerCard] = {}
        self._plan: OperationPlan | None = None
        self._plan_key: frozenset[str] | None = None
        self._plan_seconds: float = 0.0
        self._results: list[CleanResult] = []
        self._busy = ""
        self._cancel = threading.Event()
        self._admin = is_admin()

        self._ui = UiDispatcher(self)
        self._ui.start()

        self.configure(fg_color="transparent")
        self._build()
        self._update_cards()
        self._update_summary()

    # ── сборка ────────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = PageHeader(
            self, self._theme,
            "Глубокая очистка",
            "Кэши, системный мусор и крупные файлы — с планом до удаления",
            icon="🔍",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        self.admin_pill = MDPill(
            header.actions, self._theme,
            "admin" if self._admin else "без прав",
            icon="✓" if self._admin else "🔒",
            tone="secondary_container" if self._admin else "error_container",
        )
        self.admin_pill.pack(side="right")
        if self._on_elevate is not None and not self._admin:
            self.admin_pill.configure(cursor="hand2")
            _bind_click(self.admin_pill, self._on_elevate)

        # ── Панель действий ───────────────────────────
        toolbar = MDCard(self, self._theme, tone="low")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(toolbar, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(11, 6))

        self.analyze_btn = MDButton(
            row, self._theme, "Анализировать", self.start_scan,
            kind="filled", width=142,
        )
        self.analyze_btn.pack(side="left", padx=(0, 6))

        self.stop_btn = MDButton(
            row, self._theme, "Стоп", self.stop,
            kind="outlined", width=76, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(0, 6))

        self.safe_btn = MDButton(
            row, self._theme, "Безопасный набор", self.select_safe_set,
            kind="tonal", width=164,
        )
        self.safe_btn.pack(side="left", padx=(0, 6))

        self.clear_btn = MDButton(
            row, self._theme, "Снять", self.deselect_all,
            kind="text_muted", width=72,
        )
        self.clear_btn.pack(side="left")

        self.sel_label = MDLabel(
            row, self._theme, "", role="secondary", font=FONT_LABEL, anchor="e",
        )
        self.sel_label.pack(side="right", padx=(8, 2))

        if self._on_reload is not None:
            MDIconButton(
                row, self._theme, "↻", self._reload_targets,
                kind="standard", size=30, font=("Segoe UI", 14),
            ).pack(side="right", padx=(0, 2))

        self.progress = MDProgress(toolbar, self._theme, height=4)

        # ── Полоса слоёв ──────────────────────────────
        # Фиксированная высота + propagate(False): иначе пять карточек
        # заявляют свою минимальную ширину и вылезают за край узкого окна.
        strip = ctk.CTkFrame(self, fg_color="transparent", height=88)
        strip.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_2))
        strip.grid_propagate(False)
        strip.grid_rowconfigure(0, weight=1)
        for index, layer in enumerate(LAYERS):
            strip.grid_columnconfigure(index, weight=1, uniform="deep-layer")
            card = _LayerCard(strip, self._theme, layer, self._card_clicked)
            card.grid(
                row=0, column=index, sticky="nsew",
                padx=(0 if index == 0 else 6, 0),
            )
            self._cards[layer] = card

        # ── Список целей ──────────────────────────────
        self.list = MDScrollArea(self, self._theme)
        self.list.grid(row=3, column=0, sticky="nsew")

        self.hint = MDLabel(
            self.list, self._theme, "", role="muted", font=FONT_BODY,
            anchor="w", justify="left", wraplength=820,
        )
        self.hint.pack(fill="x", padx=10, pady=(8, 4))

        # ── Итоги и действия ──────────────────────────
        footer = MDCard(self, self._theme, tone="low")
        footer.grid(row=4, column=0, sticky="ew", pady=(SPACE_2, 0))

        left = ctk.CTkFrame(footer, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=(14, 6), pady=9)

        self.result_label = MDLabel(
            left, self._theme, "", role="success", font=FONT_LABEL,
            anchor="w", justify="left", wraplength=430,
        )

        self.summary_label = MDLabel(
            left, self._theme, "Ничего не выбрано", role="secondary",
            font=FONT_LABEL, anchor="w", justify="left", wraplength=430,
        )
        self.summary_label.pack(anchor="w")

        right = ctk.CTkFrame(footer, fg_color="transparent")
        right.pack(side="right", padx=(0, 12), pady=9)

        self.clean_btn = MDButton(
            right, self._theme, "Очистить", self.start_clean,
            kind="filled", width=112, state="disabled",
        )
        self.clean_btn.pack(side="right", padx=(6, 0))

        self.plan_btn = MDButton(
            right, self._theme, "Показать план", self.show_plan,
            kind="outlined", width=140, state="disabled",
        )
        self.plan_btn.pack(side="right", padx=(6, 0))

        self.report_btn = MDButton(
            right, self._theme, "Отчёт", self._save_report,
            kind="text_muted", width=82, state="disabled",
        )
        self.report_btn.pack(side="right")

        self.recycle_btn = MDButton(
            right, self._theme, "Корзина", self._open_recycle_bin,
            kind="text_muted", width=100, state="disabled",
        )
        self.recycle_btn.pack(side="right", padx=(6, 0))

        self.repeat_btn = MDButton(
            right, self._theme, "Повторить", self._repeat_clean,
            kind="outlined", width=110, state="disabled",
        )
        self.repeat_btn.pack(side="right", padx=(6, 0))

    # ── загрузка целей ───────────────────────────────

    def _reload_targets(self) -> None:
        if self._busy or self._on_reload is None:
            return
        self._on_reload()
        self._on_log("↻  Список целей обновлён.")

    def load_cleaners(self, cleaners: list[BaseCleaner]) -> None:
        self._cleaners = list(cleaners)
        self._selected.clear()
        self._results = []
        self._invalidate_plan()
        self._admin = is_admin()
        self._update_admin_pill()
        self._rebuild()
        self._update_cards()
        self._update_summary()
        self._set_result("")
        self.report_btn.configure(state="disabled")
        self.repeat_btn.configure(state="disabled")

    def _update_admin_pill(self) -> None:
        try:
            self.admin_pill.set_text(
                "admin" if self._admin else "без прав",
                "✓" if self._admin else "🔒",
            )
        except Exception:
            pass

    def _rebuild(self) -> None:
        for group in self._groups.values():
            group.destroy()
        self._groups.clear()
        self._rows.clear()

        for layer in LAYERS:
            cleaners = [c for c in self._cleaners if c.layer == layer]
            # Слой E может остаться без целей: карточка нужна ради «крупных файлов».
            if not cleaners and layer != LAYER_INVENTORY:
                continue
            group = _LayerGroup(self.list, self._theme, layer, self._toggle_layer)
            group.pack(fill="x", padx=2, pady=(2, 0))
            self._groups[layer] = group
            group.set_builder(partial(self._build_rows, cleaners=cleaners))

        self._sync_groups()
        self._update_hint()

    def _build_rows(
        self, group: _LayerGroup, cleaners: list[BaseCleaner],
    ) -> None:
        """Создать строки раскрытого слоя (102 строки ≈ 1100 виджетов)."""
        for cleaner in cleaners:
            row = _TargetRow(
                group.body, self._theme, cleaner, self._admin,
                on_toggle=self._set_target,
                on_info=self._show_details,
            )
            group.add_row(row)
            self._rows[cleaner.id] = row
        if group.layer == LAYER_INVENTORY:
            group.add_action(
                "🔎 Показать крупные файлы",
                self._show_large_files,
                "топ-50 на диске · только показ",
            )
        self._sync_rows()

    # ── выбор ────────────────────────────────────────

    def _set_target(self, cleaner: BaseCleaner, value: bool) -> None:
        if self._busy:
            self._sync_rows()
            return
        if value:
            self._selected.add(cleaner.id)
        else:
            self._selected.discard(cleaner.id)
        self._invalidate_plan()
        self._sync_rows()
        self._update_summary()

    def _card_clicked(self, layer: str) -> None:
        """Клик по карточке: выбрать слой целиком или снять его."""
        if self._busy:
            return
        cleaners = [c for c in self._cleaners if c.layer == layer]
        all_selected = bool(cleaners) and all(
            c.id in self._selected for c in cleaners
        )
        self._toggle_layer(layer, not all_selected)

    def _toggle_layer(self, layer: str, value: bool) -> None:
        if self._busy:
            self._sync_rows()
            return
        for cleaner in self._cleaners:
            if cleaner.layer != layer:
                continue
            if value:
                self._selected.add(cleaner.id)
            else:
                self._selected.discard(cleaner.id)
        self._invalidate_plan()
        self._sync_rows()
        self._update_summary()

    def select_safe_set(self) -> None:
        if self._busy:
            return
        self._selected = {
            cleaner.id
            for cleaner in self._cleaners
            if cleaner.layer == LAYER_SAFE
            and cleaner.recommended
            and not (cleaner.admin_required and not self._admin)
        }
        self._invalidate_plan()
        self._sync_rows()
        self._update_summary()
        self._on_log(
            f"🛡️  Безопасный набор: {len(self._selected)} "
            f"{_plural(len(self._selected), 'цель', 'цели', 'целей')}. "
            "Проверьте план перед очисткой."
        )

    def deselect_all(self) -> None:
        if self._busy:
            return
        self._selected.clear()
        self._invalidate_plan()
        self._sync_rows()
        self._update_summary()

    def _show_large_files(self) -> None:
        drive = self._get_drive() if self._get_drive is not None else None
        LargeFilesDialog(
            self, self._theme, drive=drive, on_log=self._on_log,
        )

    def _sync_rows(self) -> None:
        for cleaner_id, row in self._rows.items():
            row.set_selected(cleaner_id in self._selected)
        self._sync_groups()

    def _sync_groups(self) -> None:
        # Считаем по целям, а не по строкам: строки свёрнутых слоёв ещё не созданы.
        for layer, group in self._groups.items():
            cleaners = [c for c in self._cleaners if c.layer == layer]
            selected = sum(1 for c in cleaners if c.id in self._selected)
            size = sum(c.size for c in cleaners if c.scanned)
            scanned = any(c.scanned for c in cleaners)
            group.set_state(selected, len(cleaners), size, scanned)

    def _selected_cleaners(self) -> list[BaseCleaner]:
        return [c for c in self._cleaners if c.id in self._selected]

    def _invalidate_plan(self) -> None:
        self._plan = None
        self._plan_key = None
        self._plan_seconds = 0.0

    def _update_summary(self) -> None:
        count = len(self._selected)
        selected = self._selected_cleaners()
        size = sum(cleaner.size for cleaner in selected if cleaner.scanned)
        unknown = any(not cleaner.scanned for cleaner in selected)

        if count:
            text = (
                f"Выбрано: {count} {_plural(count, 'цель', 'цели', 'целей')} · "
                f"{format_bytes(size)}"
            )
            if unknown:
                text += " (часть размеров ещё не измерена)"
        else:
            text = "Ничего не выбрано"
        self.summary_label.configure(text=text)
        self.sel_label.configure(text=text)

        enabled = bool(count) and not self._busy
        state = "normal" if enabled else "disabled"
        self.plan_btn.configure(state=state)
        self.clean_btn.configure(state=state)

        self._update_cards()
        self._update_hint()

    def _update_cards(self) -> None:
        for layer, card in self._cards.items():
            cleaners = [c for c in self._cleaners if c.layer == layer]
            size = sum(c.size for c in cleaners if c.scanned)
            selected = sum(1 for c in cleaners if c.id in self._selected)
            card.set_stats(
                size, len(cleaners), selected,
                scanned=any(c.scanned for c in cleaners),
            )

    def _update_hint(self) -> None:
        if not self._cleaners:
            text = "Список целей пуст. Добавьте правила на экране «Очистка»."
        else:
            scanned = [c for c in self._cleaners if c.scanned]
            total = sum(c.size for c in scanned)
            if not scanned:
                text = (
                    "Нажмите «Анализировать», чтобы увидеть, "
                    "что можно освободить."
                )
            elif self._selected:
                text = (
                    "Проверьте план: что именно будет удалено, "
                    "на каком томе и какие файлы пропустятся."
                )
            else:
                text = (
                    f"Найдено {format_bytes(total)} в {len(scanned)} целях. "
                    "Ничего не выбрано — отметьте цели или нажмите "
                    "«Безопасный набор»."
                )
            errors = sum(1 for c in self._cleaners if c.scan_error)
            if errors:
                text += f" · ошибок сканирования: {errors}"
        self.hint.configure(text=text)

    # ── анализ ───────────────────────────────────────

    def start_scan(self) -> None:
        if self._busy:
            return
        if not self._cleaners:
            self._on_log("ℹ️  Список целей пуст — нечего анализировать.")
            return

        self._cancel.clear()
        self._invalidate_plan()
        self._selected.clear()
        self._results = []
        self._set_result("")
        self.report_btn.configure(state="disabled")
        self._sync_rows()
        self._update_summary()
        self._set_busy("scan")
        self._on_log("📡  Глубокая очистка: анализ целей…")

        def worker() -> None:
            try:
                self._scan_engine.scan_all(
                    self._cleaners,
                    auto_discover=False,
                    progress_callback=self._scan_progress,
                )
            except Exception as e:
                self._ui.post(self._on_log, f"❌ Ошибка анализа: {e}")
                log.exception("Ошибка анализа глубокой очистки")
            finally:
                self._ui.post(self._scan_done)

        threading.Thread(target=worker, daemon=True, name="deep-scan").start()

    def _scan_progress(self, done: int, total: int) -> None:
        pct = done / total if total > 0 else 0
        self._ui.post(self._set_progress, pct, f"Анализ: {done}/{total}")

    def _scan_done(self) -> None:
        self._set_busy("")
        for row in self._rows.values():
            row.update_state()
        self._sync_groups()
        self._update_cards()
        self._update_summary()

        scanned = [c for c in self._cleaners if c.scanned]
        total = sum(c.size for c in scanned)
        errors = sum(1 for c in self._cleaners if c.scan_error)
        if self._scan_engine.was_cancelled:
            self._on_log(
                f"⏹️  Анализ остановлен: обработано {len(scanned)} целей, "
                f"найдено {format_bytes(total)}"
            )
        else:
            self._on_log(
                f"✅  Найдено {format_bytes(total)} в {len(scanned)} целях."
            )
        if errors:
            self._on_log(f"⚠️  Не удалось проанализировать целей: {errors}")

    def stop(self) -> None:
        if not self._busy:
            return
        self._cancel.set()
        if self._busy == "scan":
            self._scan_engine.cancel()
        self._on_log("⏹️  Остановка…")
        self.stop_btn.configure(state="disabled")

    # ── план ─────────────────────────────────────────

    def show_plan(self) -> None:
        if self._busy or not self._selected:
            return
        if self._plan is not None and self._plan_key == frozenset(self._selected):
            self._show_plan_dialog(self._plan)
            return
        self._build_plan_async(self._show_plan_dialog)

    def _build_plan_async(self, callback: Callable[[OperationPlan], None]) -> None:
        cleaners = self._selected_cleaners()
        key = frozenset(self._selected)
        self._cancel.clear()
        self._set_busy("plan")
        self._set_progress(0, "План…")
        self._on_log("🧮  Строим план удаления…")

        def worker() -> None:
            token = set_scan_cancel(self._cancel)
            plan: OperationPlan | None = None
            error = ""
            seconds = 0.0
            try:
                started = time.perf_counter()
                plan = self._clean_engine.build_plan(cleaners)
                seconds = time.perf_counter() - started
            except Exception as e:
                error = str(e)
                log.exception("Ошибка построения плана")
            finally:
                reset_scan_cancel(token)
            self._ui.post(self._plan_ready, plan, key, callback, error, seconds)

        threading.Thread(target=worker, daemon=True, name="deep-plan").start()

    def _plan_ready(
        self,
        plan: OperationPlan | None,
        key: frozenset[str],
        callback: Callable[[OperationPlan], None],
        error: str,
        seconds: float = 0.0,
    ) -> None:
        self._set_busy("")
        if plan is None:
            self._on_log(f"❌ Не удалось построить план: {error or 'неизвестная ошибка'}")
            return

        self._plan = plan
        self._plan_key = key
        self._plan_seconds = seconds
        timing = f", построен за {seconds:.1f} с" if seconds > 0 else ""
        self._on_log(
            f"🧮  План: {plan.action_count} действий{timing}, "
            f"планируется {format_bytes(plan.total_bytes)}."
        )
        for warning in plan.warnings:
            self._on_log(f"    ⚠️ {warning}")
        if plan.total_bytes == 0 and plan.action_count == 0:
            messagebox.showinfo(
                "План пуст",
                "Выбранные цели уже пусты или недоступны.\n"
                "Проверьте права администратора и повторите анализ.",
            )
        callback(plan)

    def _plan_text(self, plan: OperationPlan) -> str:
        lines = [
            f"План глубокой очистки  #{plan.id}",
            f"Создан: {datetime.datetime.now():%Y-%m-%d %H:%M}",
            "",
            f"Целей: {len(plan.targets)} · действий: {plan.action_count}",
            f"Планируется освободить: {format_bytes(plan.total_bytes)}",
        ]
        if self._plan_seconds > 0:
            lines.append(
                f"Построен за {self._plan_seconds:.1f} с"
                + (f" · файлов: {plan.action_count}" if plan.action_count else "")
            )

        volumes = _volumes_text(plan.total_by_volume)
        if volumes:
            lines.extend(["", "По томам:", f"  {volumes}"])

        layers = plan.total_by_layer
        if layers:
            lines.extend(["", "По слоям:"])
            for layer in LAYERS:
                size = layers.get(layer, 0)
                if size:
                    lines.append(
                        f"  {layer} · {layer_title(layer):<22} {format_bytes(size)}"
                    )

        actions = [
            (action, target)
            for target in plan.targets
            for action in target.actions
            if action.bytes > 0
        ]
        actions.sort(key=lambda item: item[0].bytes, reverse=True)
        if actions:
            lines.extend(["", "Крупнейшие действия:"])
            for action, target in actions[:12]:
                lines.append(
                    f"  {format_bytes(action.bytes):>10}  "
                    f"{target.cleaner.name}  "
                    f"{_short_path(action.path)}"
                )

        losses = [
            target.cleaner for target in plan.targets
            if target.actions and target.cleaner.loss
        ]
        if losses:
            lines.extend(["", "Что изменится:"])
            for cleaner in losses[:8]:
                lines.append(f"  • {cleaner.name}: {_short(cleaner.loss, 150)}")

        warnings: list[str] = list(plan.warnings)  # запущенные приложения и др.
        for target in plan.targets:
            if target.blocked:
                warnings.append(f"{target.cleaner.name}: {target.blocked}")
            if target.truncated:
                warnings.append(
                    f"{target.cleaner.name}: слишком много файлов, "
                    "обработана только часть."
                )
        if plan.requires_admin and not is_admin():
            warnings.append(
                "Часть целей требует прав администратора и будет пропущена."
            )
        if any(t.layer == LAYER_LEFTOVERS for t in plan.targets):
            warnings.append(
                "Слой D: файлы будут перемещены в корзину, "
                "место освободится после её очистки."
            )
        if any(t.layer == LAYER_COMPONENTS for t in plan.targets):
            warnings.append(
                "Слой C — это не кэш: компоненты потребуется скачать заново."
            )
        if warnings:
            lines.extend(["", "Предупреждения:"])
            lines.extend(f"  • {_short(w, 170)}" for w in warnings[:8])

        if plan.total_bytes == 0:
            lines.extend([
                "",
                "Размер не определён: цели могут быть пусты или недоступны.",
            ])

        lines.extend([
            "",
            "Ничего не удаляется до подтверждения.",
            "Отмена во время очистки — между пачками файлов.",
        ])
        return "\n".join(lines)

    def _show_plan_dialog(self, plan: OperationPlan) -> None:
        window = ctk.CTkToplevel(self)
        window.title("План глубокой очистки")
        window.geometry("760x600")
        window.minsize(620, 460)
        window.attributes("-topmost", True)
        window.configure(fg_color=self._theme.colors.SURFACE)
        window.transient(self.winfo_toplevel())

        head = ctk.CTkFrame(window, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 8))
        MDLabel(
            head, self._theme, "План до удаления", role="on_surface",
            font=FONT_LABEL_LARGE, anchor="w",
        ).pack(anchor="w")
        MDLabel(
            head, self._theme,
            f"{len(plan.targets)} "
            f"{_plural(len(plan.targets), 'цель', 'цели', 'целей')} · "
            f"{plan.action_count} действий · "
            f"{format_bytes(plan.total_bytes)}"
            + (
                f" · построен за {self._plan_seconds:.1f} с"
                if self._plan_seconds > 0 else ""
            ),
            role="secondary", font=FONT_BODY, anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        text = MDTextbox(window, self._theme, font=FONT_MONO_SMALL)
        text.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        text.insert("1.0", self._plan_text(plan))
        text.configure(state="disabled")

        footer = ctk.CTkFrame(window, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 16))

        MDButton(
            footer, self._theme, "Экспорт JSON",
            lambda: self._export_plan(plan, "json", window),
            kind="outlined", width=120,
        ).pack(side="left")
        MDButton(
            footer, self._theme, "Экспорт CSV",
            lambda: self._export_plan(plan, "csv", window),
            kind="outlined", width=120,
        ).pack(side="left", padx=(6, 0))

        MDButton(
            footer, self._theme, "Закрыть", window.destroy,
            kind="text_muted", width=90,
        ).pack(side="right")

        def clean_from_dialog() -> None:
            window.destroy()
            self._confirm_clean(plan)

        if plan.action_count:
            MDButton(
                footer, self._theme, "Очистить по плану", clean_from_dialog,
                kind="filled", width=176,
            ).pack(side="right", padx=(0, 6))

    def _export_plan(self, plan: OperationPlan, kind: str, parent) -> None:
        suffix = ".json" if kind == "json" else ".csv"
        path = filedialog.asksaveasfilename(
            parent=parent, title="Экспорт плана очистки",
            defaultextension=suffix,
            initialfile=f"DiskCleaner-plan-{plan.id}{suffix}",
            filetypes=[("JSON", "*.json")] if kind == "json" else [("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            if kind == "json":
                target = export_plan_json(plan, path)
            else:
                target = export_plan_csv(plan, path)
        except OSError as e:
            messagebox.showerror("Экспорт плана", f"Не удалось сохранить: {e}")
            return
        self._on_log(f"💾  План #{plan.id} экспортирован: {target}")

    # ── очистка ──────────────────────────────────────

    def start_clean(self) -> None:
        if self._busy or not self._selected:
            return
        if self._plan is not None and self._plan_key == frozenset(self._selected):
            self._confirm_clean(self._plan)
            return
        self._build_plan_async(self._confirm_clean)

    def _confirm_clean(self, plan: OperationPlan) -> None:
        if not plan.action_count:
            messagebox.showinfo(
                "Нечего очищать",
                "В плане нет действий: выбранные цели уже пусты.",
            )
            return

        recycle_targets = [
            t for t in plan.targets if t.layer == LAYER_LEFTOVERS and t.actions
        ]
        components = [
            t for t in plan.targets if t.layer == LAYER_COMPONENTS and t.actions
        ]
        # Заблокированные цели делятся на два случая: без прав админа (будут
        # пропущены) и «только показ» (слой E — размеры в план освобождения
        # не входят вовсе).
        blocked_admin = [
            t for t in plan.targets if t.blocked and t.cleaner.is_actionable
        ]
        show_only = [
            t for t in plan.targets if t.blocked and not t.cleaner.is_actionable
        ]
        actionable = [
            t for t in plan.targets if t.actions and t.cleaner.is_actionable
        ]
        has_recycle_bin = any(t.cleaner.id == "recycle" for t in plan.targets)

        def _names(targets: list) -> str:
            return ", ".join(t.cleaner.name for t in targets)

        details = [
            f"Целей: {len(actionable)} · "
            f"действий: {sum(len(t.actions) for t in actionable)}",
            f"Планируется освободить: "
            f"{format_bytes(sum(t.planned_bytes for t in actionable))}",
        ]
        volumes: dict[str, int] = {}
        for target in actionable:
            for action in target.actions:
                volumes[action.volume] = (
                    volumes.get(action.volume, 0) + action.bytes
                )
        if volumes:
            details.append(f"По томам: {_volumes_text(volumes)}")

        if recycle_targets:
            recycled = sum(t.planned_bytes for t in recycle_targets)
            details.append(
                f"\n♻️  В корзину: {format_bytes(recycled)} — место "
                "освободится после очистки корзины."
            )
        if components:
            size = sum(t.planned_bytes for t in components)
            details.append(
                f"\n⚠️  Компоненты и модели: {format_bytes(size)}. "
                "Это не кэш — после удаления потребуется скачать заново."
            )
        for warning in plan.warnings:
            details.append(f"\n⚠️  {warning}")
        if show_only:
            details.append(
                f"\nℹ️  Только показ, без удаления: {_names(show_only)} — "
                "смотрите подсказку к цели."
            )
        if blocked_admin:
            details.append(
                f"\n🔒 Без прав администратора будет пропущено целей: "
                f"{len(blocked_admin)}."
            )
        if has_recycle_bin:
            details.append(
                "\n🗑️  Корзина будет очищена безвозвратно — "
                "восстановить файлы не получится."
            )

        running = {
            t.cleaner.id
            for t in actionable if not t.blocked
        }
        if "vss_cleanup" in running:
            details.append(
                "\n⚠️  Старые точки восстановления будут удалены безвозвратно "
                "(самая новая на каждом томе сохранится)."
            )
        if "hibernation" in running:
            details.append(
                "\n⚠️  Гибернация и быстрый запуск будут отключены. "
                "Вернуть: powercfg /hibernate on."
            )
        if "dism_cleanup" in running:
            details.append(
                "\n⚠️  DISM может работать до 15 минут — прерывать его нельзя."
            )

        details.append("\nПродолжить очистку по плану?")
        if not messagebox.askyesno(
            "Подтверждение глубокой очистки",
            "\n".join(details),
            icon="warning",
        ):
            return
        self._run_clean(plan)

    def _run_clean(self, plan: OperationPlan) -> None:
        options = CleanOptions(
            to_recycle=bool(self._config.get("to_recycle", False)),
            safe_mode=bool(self._config.get("safe_mode", True)),
        )
        self._cancel.clear()
        self._results = []
        self._set_result("")
        self._set_busy("clean")
        self._set_progress(0, "Очистка…")
        self._on_log(
            f"🧹  Очистка по плану #{plan.id}: "
            f"{format_bytes(plan.total_bytes)}…"
        )

        def worker() -> None:
            token = set_scan_cancel(self._cancel)
            if bool(ConfigManager().get("restore_point", False)):
                self._ui.post(self._on_log, "🛡️  Создание точки восстановления…")
                ok, message = create_restore_point()
                icon = "✅" if ok else "⚠️"
                self._ui.post(self._on_log, f"  {icon} {message}")
            results: list[CleanResult] = []
            try:
                results = self._clean_engine.clean_plan(
                    plan, options, self._clean_progress
                )
            except Exception as e:
                self._ui.post(self._on_log, f"❌ Ошибка очистки: {e}")
                log.exception("Ошибка глубокой очистки")
            finally:
                reset_scan_cancel(token)
                self._ui.post(self._clean_done, results, plan)

        threading.Thread(target=worker, daemon=True, name="deep-clean").start()

    def _clean_progress(
        self, done: int, total: int, result: CleanResult
    ) -> None:
        icon = {"OK": "✅", "ERR": "❌", "SKIP": "⏭️"}.get(result.status, "•")
        message = f"  {icon} {result.cleaner.name}: {result.detail}"
        if result.note:
            message += f" — {result.note}"
        self._ui.post(self._on_log, message)
        pct = done / total if total > 0 else 0
        self._ui.post(
            self._set_progress, pct,
            f"{done}/{total} · {result.cleaner.name}",
        )

    def _clean_done(
        self, results: list[CleanResult], plan: OperationPlan
    ) -> None:
        self._set_busy("")
        for row in self._rows.values():
            row.update_state()
        self._sync_groups()
        self._update_cards()

        if not results:
            self._update_summary()
            return

        self._results = results
        freed = sum(r.freed for r in results)
        planned = sum(r.planned for r in results)
        removed = sum(r.removed for r in results)
        recycled = sum(r.planned for r in results if r.recycled)
        errors = sum(len(r.errors) for r in results)

        # Агрегат причин по всем целям: {род: количество} (5B-1).
        kinds: dict[str, int] = {}
        for result in results:
            for kind, count in result.error_kinds.items():
                kinds[kind] = kinds.get(kind, 0) + count

        by_volume: dict[str, int] = {}
        for result in results:
            for volume, delta in result.volume_deltas.items():
                by_volume[volume] = by_volume.get(volume, 0) + delta

        self._selected.clear()
        self._invalidate_plan()
        self._sync_rows()
        self._update_summary()

        self._on_log(
            f"✅  Глубокая очистка: освобождено {format_bytes(freed)} "
            f"(план {format_bytes(planned)})."
        )
        if by_volume:
            self._on_log(f"📊  Подтверждено по томам: {_volumes_text(by_volume)}")
        if removed and not freed:
            self._on_log(
                f"📦  Удалено {format_bytes(removed)}, но свободное место "
                "не изменилось — данные могли занять другие процессы."
            )
        if recycled:
            self._on_log(
                f"🗑️  {format_bytes(recycled)} перемещено в корзину — "
                "место освободится после её очистки."
            )
        if errors:
            message = f"⚠️  Не удалось удалить объектов: {errors}."
            kinds_text = summarize_kinds(kinds)
            if kinds_text:
                message += f" Причины: {kinds_text}."
            advice = remediation(kinds)
            if advice:
                message += f" {advice.capitalize()}."
            self._on_log(message)
            shown = 0
            for result in results:
                for error in result.errors[:3]:
                    self._on_log(
                        f"    · {_short(error, 105)} — {_reason_of(error)}"
                    )
                    shown += 1
                    if shown >= 3:
                        break
                if shown >= 3:
                    break

        parts = [
            f"Освобождено: {format_bytes(freed)}",
            f"В корзину: {format_bytes(recycled)}",
        ]
        error_text = f"Ошибки: {errors}"
        if errors:
            kinds_text = summarize_kinds(kinds)
            if kinds_text:
                error_text = f"Ошибки: {errors} ({kinds_text})"
        parts.append(error_text)
        if by_volume:
            parts.append(f"По томам: {_volumes_text(by_volume)}")
        self._set_result(
            " · ".join(parts), "success" if freed or recycled else "warning"
        )

        self._save_history(results, freed)
        self.report_btn.configure(state="normal")
        self.recycle_btn.configure(state="normal")
        self.repeat_btn.configure(
            state="normal" if errors else "disabled"
        )
        self._on_log(f"🧮  План #{plan.id} выполнен.")

    def _save_report(self) -> None:
        if not self._results:
            return
        stamp = datetime.datetime.now()
        desktop = Path.home() / "Desktop"
        folder = desktop if desktop.exists() else Path.home()
        path = folder / f"diskcleaner_deep_{stamp:%Y%m%d_%H%M%S}.txt"
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write("=" * 56 + "\n")
                file.write("  🔍 DiskCleaner Pro — глубокая очистка\n")
                file.write(f"  {stamp:%Y-%m-%d %H:%M}\n")
                file.write("=" * 56 + "\n\n")
                for result in self._results:
                    icon = {"OK": "✅", "ERR": "❌", "SKIP": "⏭️"}.get(
                        result.status, "•"
                    )
                    file.write(f"{icon} {result.cleaner.name}: {result.detail}\n")
                    file.write(
                        f"   слой {result.cleaner.layer} · "
                        f"план {format_bytes(result.planned)} · "
                        f"освобождено {format_bytes(result.freed)} · "
                        f"удалено {format_bytes(result.removed)} · "
                        f"осталось {format_bytes(result.remaining)}\n"
                    )
                    if result.volumes:
                        file.write(f"   тома: {', '.join(result.volumes)}\n")
                    if result.recycled:
                        file.write("   перемещено в корзину\n")
                    if result.note:
                        file.write(f"   ⚠️ {result.note}\n")
                    for error in result.errors[:5]:
                        file.write(f"   · {error}\n")
                file.write(f"\n{'─' * 56}\n")
                file.write(
                    f"Освобождено: {format_bytes(sum(r.freed for r in self._results))}\n"
                )
                file.write(
                    "В корзину: "
                    f"{format_bytes(sum(r.planned for r in self._results if r.recycled))}\n"
                )
            self._on_log(f"📄  Отчёт сохранён: {path}")
        except Exception as e:
            self._on_log(f"❌  Не удалось сохранить отчёт: {e}")
            log.exception("Ошибка сохранения отчёта глубокой очистки")

    def _save_history(self, results: list[CleanResult], freed: int) -> None:
        try:
            payload = [
                {
                    "id": r.cleaner.id,
                    "name": r.cleaner.name,
                    "layer": r.cleaner.layer,
                    "status": r.status,
                    "planned": r.planned,
                    "freed": r.freed,
                    "removed": r.removed,
                    "remaining": r.remaining,
                    "recycled": r.recycled,
                    "confidence": r.confidence,
                    "volumes": list(r.volumes),
                    "note": r.note,
                    "errors": r.errors[:3],
                }
                for r in results
            ]
            HistoryManager().add_operation(payload, bytes_freed=freed, op_type="deep")
        except Exception as e:
            self._on_log(f"⚠️  История не сохранена: {e}")
            log.exception("Не удалось сохранить историю глубокой очистки")

    # ── детали, прогресс, результат ──────────────────

    def _show_details(self, cleaner: BaseCleaner) -> None:
        paths = list(cleaner.affected_paths())[:3]
        path_text = "\n".join(f"  {p}" for p in paths) or "  команда/системная операция"
        text = (
            f"Слой: {cleaner.layer} · {layer_title(cleaner.layer)}\n"
            f"Группа: {cleaner.group}\n\n"
            f"Пути:\n{path_text}\n\n"
            f"Почему: {cleaner.why or cleaner.description or '—'}\n\n"
            f"Что потеряю: {cleaner.loss or '—'}"
        )
        if cleaner.restore_hint:
            text += f"\n\nВосстановление: {cleaner.restore_hint}"
        messagebox.showinfo(cleaner.name, text)

    def _set_progress(self, value: float, label: str = "") -> None:
        if self._statusbar:
            self._statusbar.set_progress(value, label)
        self.progress.set(max(0.0, min(1.0, value)))

    def _set_busy(self, kind: str) -> None:
        self._busy = kind
        busy = bool(kind)
        self.analyze_btn.configure(state="disabled" if busy else "normal")
        self.stop_btn.configure(state="normal" if busy else "disabled")
        self.safe_btn.configure(state="disabled" if busy else "normal")
        self.clear_btn.configure(state="disabled" if busy else "normal")

        if busy:
            if not self.progress.winfo_manager():
                self.progress.pack(fill="x", padx=14, pady=(0, 9))
        else:
            self.progress.pack_forget()
            if self._statusbar:
                self._statusbar.set_progress(1.0)
        self._update_summary()

    def _set_result(self, text: str, role: str = "success") -> None:
        self.result_label.set_role(role)
        self.result_label.configure(text=text)
        if text:
            self.result_label.pack(anchor="w", pady=(0, 1), before=self.summary_label)
        else:
            self.result_label.pack_forget()

    # ── действия результата: корзина и повтор ────────

    def _open_recycle_bin(self) -> None:
        try:
            os.startfile("shell:RecycleBinFolder")  # noqa: S606
        except Exception as e:
            self._on_log(f"❌ Не удалось открыть корзину: {e}")

    def _repeat_clean(self) -> None:
        """Повторная очистка только тех целей, где остались ошибки."""
        failed = sorted(
            result.cleaner.id
            for result in (self._results or [])
            if result.errors
        )
        if not failed:
            messagebox.showinfo(
                "Повторить очистку",
                "Ошибок в последней очистке нет — повторять нечего.",
            )
            return
        self._selected = {identifier for identifier in failed}
        self._invalidate_plan()
        self._sync_rows()
        self._update_summary()
        self._on_log(
            f"↻  Повтор для целей с ошибками: {len(self._selected)}."
        )
        self.start_clean()

    # ── тема/жизненный цикл ──────────────────────────

    def refresh_theme(self) -> None:
        self._update_admin_pill()
        for row in self._rows.values():
            row.refresh_theme()
        self._update_cards()

    def destroy(self) -> None:
        try:
            self._cancel.set()
            self._ui.stop()
            self._scan_engine.shutdown()
        except Exception:
            pass
        super().destroy()
