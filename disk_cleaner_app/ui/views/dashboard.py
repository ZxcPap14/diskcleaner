"""Главная — обзор состояния диска и быстрые действия (MD3)."""
from __future__ import annotations

from functools import partial
from typing import Any

import customtkinter as ctk

from disk_cleaner_app.cleaners.base import list_drives
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.ui.assets import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_HEADLINE,
    FONT_LABEL,
    FONT_TITLE_MEDIUM,
    SPACE_2,
    SPACE_3,
)
from disk_cleaner_app.ui.components.disk_gauge import DiskGauge
from disk_cleaner_app.ui.components.md3 import (
    MDButton,
    MDCard,
    MDLabel,
    MDOptionMenu,
    MDPill,
    MDScrollArea,
    PageHeader,
    SectionTitle,
)
from disk_cleaner_app.ui.theme import ThemeManager


class DashboardView(ctk.CTkFrame):
    """Главная страница: показатели, диск, быстрая очистка и топ целей."""

    STATS = (
        ("Свободно на диске", "◉", "primary_container"),
        ("Очищено всего", "↑", "secondary_container"),
        ("Выполнено очисток", "≡", "tertiary_container"),
    )

    def __init__(
        self,
        parent,
        theme: ThemeManager,
        on_quick_clean,
        on_clean_target=None,
        on_drive_change=None,
        on_deep_clean=None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._theme = theme
        self._on_quick_clean = on_quick_clean
        self._on_clean_target = on_clean_target
        self._on_drive_change = on_drive_change
        self._on_deep_clean = on_deep_clean
        self.configure(fg_color="transparent")
        self._free = 0
        self._total = 0
        self._drive: str | None = None
        self._targets: list[Any] = []
        self._last_clean: dict | None = None
        self._stat_values: list[ctk.CTkLabel] = []
        self._stat_badges: list[tuple[ctk.CTkFrame, ctk.CTkLabel, str]] = []
        self._build()

    # ── построение ───────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = PageHeader(
            self, self._theme,
            "Главная",
            "Состояние системы и быстрые действия",
            icon="⌂",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))
        MDPill(
            header.actions, self._theme,
            "Система готова", icon="●", tone="secondary_container",
        ).pack(side="right")

        body = MDScrollArea(self, self._theme)
        body.grid(row=1, column=0, sticky="nsew")
        self._body = body

        # ── Показатели ────────────────────────────────
        stats = ctk.CTkFrame(body, fg_color="transparent")
        stats.pack(fill="x", pady=(0, SPACE_3))
        for index, (title, icon, tone) in enumerate(self.STATS):
            stats.grid_columnconfigure(index, weight=1)
            self._build_stat_card(stats, index, title, icon, tone)

        # ── Диск и быстрая очистка ────────────────────
        middle = ctk.CTkFrame(body, fg_color="transparent")
        middle.pack(fill="x", pady=(0, SPACE_3))
        middle.grid_columnconfigure(0, weight=3)
        middle.grid_columnconfigure(1, weight=2)
        middle.grid_rowconfigure(0, weight=1)

        disk_card = MDCard(middle, self._theme, tone="low")
        disk_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_3))
        self._build_disk_card(disk_card)

        quick_card = MDCard(middle, self._theme, tone="primary_container")
        quick_card.grid(row=0, column=1, sticky="nsew")
        self._build_quick_card(quick_card)

        # ── Баннер «место заканчивается» (5C-1) ───────
        self.threshold_banner = MDCard(body, self._theme, tone="error_container")
        self._build_threshold_banner(self.threshold_banner)

        # ── Топ целей ─────────────────────────────────
        targets_card = MDCard(body, self._theme, tone="low")
        targets_card.pack(fill="x")
        self._targets_card = targets_card
        self._build_targets_card(targets_card)

        self.refresh_theme()

    def _build_stat_card(self, parent, column: int, title: str, icon: str, tone: str) -> None:
        card = MDCard(parent, self._theme, tone="low", height=100)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else SPACE_2, 0))
        card.grid_propagate(False)

        badge = ctk.CTkFrame(
            card, width=34, height=34, corner_radius=11,
            fg_color=getattr(self._theme.colors, tone.upper()),
        )
        badge.pack(side="left", padx=(16, 12), pady=16)
        badge.pack_propagate(False)
        icon_label = ctk.CTkLabel(
            badge, text=icon, font=("Segoe UI", 13, "bold"),
            text_color=getattr(self._theme.colors, f"ON_{tone.upper()}"),
        )
        icon_label.place(relx=0.5, rely=0.5, anchor="center")

        text = ctk.CTkFrame(card, fg_color="transparent")
        text.pack(side="left", fill="both", expand=True, pady=16)
        value = MDLabel(
            text, self._theme, "—", role="on_surface", font=FONT_HEADLINE,
            anchor="w",
        )
        value.pack(anchor="w")
        MDLabel(
            text, self._theme, title, role="secondary", font=FONT_LABEL, anchor="w",
        ).pack(anchor="w")
        self._stat_values.append(value)
        self._stat_badges.append((badge, icon_label, tone))

    def _build_disk_card(self, card: MDCard) -> None:
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 0))
        SectionTitle(top, self._theme, "Выбранный диск", "Заполненность тома").pack(
            side="left"
        )

        drive_values = [item[0] for item in list_drives()] or ["C:\\"]
        self._drive = self._drive or drive_values[0]
        self.drive_var = ctk.StringVar(value=self._drive)
        self.drive_menu = MDOptionMenu(
            top, self._theme, values=drive_values, variable=self.drive_var,
            command=self._on_drive_pick, width=156, height=34,
        )
        self.drive_menu.pack(side="right")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(8, 14))

        self.gauge = DiskGauge(
            body, size=160, theme=self._theme, bg=self._theme.colors.SURFACE_LOW,
        )
        self.gauge.pack(side="left", padx=(0, 18))

        info = ctk.CTkFrame(body, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        MDLabel(
            info, self._theme, "Свободное пространство", role="secondary",
            font=FONT_LABEL, anchor="w",
        ).pack(anchor="w", pady=(8, 0))
        self.free_value = MDLabel(
            info, self._theme, "—", role="on_surface", font=FONT_HEADLINE,
            anchor="w",
        )
        self.free_value.pack(anchor="w")

        self.gauge_label = MDLabel(
            info, self._theme, "Загрузка данных…", role="secondary",
            font=FONT_BODY, anchor="w", justify="left",
        )
        self.gauge_label.pack(anchor="w", pady=(10, 12))

        MDLabel(
            info, self._theme, "Данные SMART и проверка поверхности — в разделе «Диски».",
            role="muted", font=FONT_CAPTION, anchor="w", justify="left",
            wraplength=250,
        ).pack(anchor="w")

    def _build_quick_card(self, card: MDCard) -> None:
        c = self._theme.colors
        icon = ctk.CTkLabel(
            card, text="✦", font=("Segoe UI", 30),
            text_color=c.ON_PRIMARY_CONTAINER,
        )
        icon.pack(anchor="w", padx=20, pady=(18, 0))

        MDLabel(
            card, self._theme, "Быстрая очистка", role="primary_container",
            font=FONT_TITLE_MEDIUM, anchor="w",
        ).pack(anchor="w", padx=20, pady=(8, 2))
        MDLabel(
            card, self._theme,
            "Безопасный сценарий: найдём кэш, временные файлы и логи, "
            "затем покажем результат до удаления.",
            role="primary_container", font=FONT_BODY, anchor="w",
            justify="left", wraplength=270,
        ).pack(anchor="w", padx=20)

        MDButton(
            card, self._theme, "Сканировать и очистить", self._on_quick_clean,
            kind="filled", height=42, width=210,
        ).pack(anchor="w", padx=20, pady=(14, 6))
        MDLabel(
            card, self._theme, "Ничего не удаляется без подтверждения",
            role="primary_container", font=FONT_CAPTION, anchor="w",
        ).pack(anchor="w", padx=20, pady=(0, 16))

    def _build_targets_card(self, card: MDCard) -> None:
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 4))
        SectionTitle(
            top, self._theme, "Крупнейшие цели",
            "Появятся после сканирования на экране «Очистка»",
        ).pack(side="left")

        self.last_clean_label = MDLabel(
            top, self._theme, "Очисток ещё не было", role="muted",
            font=FONT_LABEL, anchor="e",
        )
        self.last_clean_label.pack(side="right")

        self.top_rows = ctk.CTkFrame(card, fg_color="transparent")
        self.top_rows.pack(fill="both", expand=True, padx=18, pady=(2, 14))
        self._render_targets()

    # ── топ целей ────────────────────────────────────

    def _render_targets(self) -> None:
        for child in self.top_rows.winfo_children():
            child.destroy()

        if not self._targets:
            empty = ctk.CTkFrame(self.top_rows, fg_color="transparent")
            empty.pack(fill="x", pady=8)
            MDLabel(
                empty, self._theme, "Пока нет данных",
                role="on_surface", font=FONT_TITLE_MEDIUM, anchor="w",
            ).pack(anchor="w")
            MDLabel(
                empty, self._theme,
                "Запустите сканирование — здесь появятся самые крупные цели.",
                role="secondary", font=FONT_BODY, anchor="w",
            ).pack(anchor="w")
            return

        c = self._theme.colors
        for index, cleaner in enumerate(self._targets[:5]):
            row = ctk.CTkFrame(
                self.top_rows, fg_color="transparent", height=34,
            )
            row.pack(fill="x", pady=1)

            md = getattr(cleaner, "safety", "🟢")
            MDLabel(
                row, self._theme, md, role="success" if md == "🟢" else "warning",
                font=FONT_LABEL, width=20, anchor="w",
            ).pack(side="left")
            MDLabel(
                row, self._theme, cleaner.name, role="on_surface",
                font=FONT_BODY, anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(4, 8))
            MDLabel(
                row, self._theme, format_bytes(max(0, cleaner.size)),
                role="secondary", font=FONT_TITLE_MEDIUM, anchor="e",
            ).pack(side="left")

            button = MDButton(
                row, self._theme, "Выбрать", partial(self._pick, cleaner),
                kind="text", width=74, height=28,
            )
            button.pack(side="right")
            if index < len(self._targets) - 1:
                ctk.CTkFrame(
                    self.top_rows, height=1, fg_color=c.OUTLINE_VARIANT,
                ).pack(fill="x", padx=(24, 0))

    def _pick(self, cleaner) -> None:
        if self._on_clean_target:
            self._on_clean_target(cleaner)

    def _on_drive_pick(self, value: str) -> None:
        self._drive = value
        if self._on_drive_change:
            self._on_drive_change(value)

    # ── баннер порога свободного места (5C-1) ────────

    def _build_threshold_banner(self, card: MDCard) -> None:
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=12)
        self.banner_text = MDLabel(
            row, self._theme, "", role="error_container",
            font=FONT_LABEL, anchor="w", justify="left", wraplength=520,
        )
        self.banner_text.pack(side="left", fill="x", expand=True)
        MDButton(
            row, self._theme, "Запустить глубокую очистку",
            self._on_deep_clean,
            kind="filled", width=210, height=38,
        ).pack(side="right", padx=(12, 0))

    def _update_threshold_banner(self) -> None:
        """Показать баннер, если свободного места меньше порога.

        Ничего не запускается автоматически: только предложение,
        выбор целей и подтверждение остаются за пользователем.
        """
        try:
            threshold_gb = float(ConfigManager().get("deep_threshold_gb", 10))
        except Exception:
            threshold_gb = 10.0
        visible = (
            threshold_gb > 0
            and self._total > 0
            and self._free > 0
            and self._free / (1024 ** 3) < threshold_gb
        )
        if not visible:
            self.threshold_banner.pack_forget()
            return
        free_gb = self._free / (1024 ** 3)
        self.banner_text.configure(
            text=(
                f"⚠️  Свободно {free_gb:.1f} ГБ — меньше порога "
                f"{threshold_gb:g} ГБ. Предлагаем глубокую очистку: "
                "безопасный набор уже выбран, подтвердите план и запускайте."
            )
        )
        try:
            self.threshold_banner.pack(
                fill="x", pady=(0, SPACE_3), before=self._targets_card
            )
        except Exception:
            self.threshold_banner.pack(fill="x", pady=(0, SPACE_3))

    # ── публичное API ────────────────────────────────

    def get_drive(self) -> str | None:
        return self._drive

    def set_drive(self, drive: str) -> None:
        values = list(self.drive_menu.cget("values"))
        if drive not in values:
            return
        self._drive = drive
        self.drive_var.set(drive)

    def set_targets(self, targets: list) -> None:
        self._targets = list(targets or [])
        self._render_targets()

    def set_last_clean(self, entry: dict | None) -> None:
        self._last_clean = entry
        c = self._theme.colors
        if not entry:
            self.last_clean_label.configure(
                text="Очисток ещё не было", text_color=c.TEXT_MUTED,
            )
            return
        date = str(entry.get("date", ""))[:16].replace("T", " ")
        self.last_clean_label.configure(
            text=f"Последняя: {format_bytes(int(entry.get('bytes_freed', 0)))}  ·  "
                 f"{entry.get('items_cleaned', 0)} целей  ·  {date}",
            text_color=c.ON_SURFACE_VARIANT,
        )

    def update_stats(
        self, free: int, total: int, total_freed: int, clean_count: int,
    ) -> None:
        self._free = free
        self._total = total
        labels = [
            format_bytes(free) if free > 0 else "—",
            format_bytes(total_freed),
            str(clean_count),
        ]
        for label, text in zip(self._stat_values, labels, strict=False):
            label.configure(text=text)

        self.gauge.set_values(free, total)
        if total <= 0:
            self.free_value.configure(text="—")
            self.gauge_label.configure(text="Нет данных о диске")
            self._update_threshold_banner()
            return

        used = total - free
        free_gb = free / (1024 ** 3)
        used_gb = used / (1024 ** 3)
        total_gb = total / (1024 ** 3)
        self.free_value.configure(text=f"{free_gb:.1f} ГБ")
        self.gauge_label.configure(
            text=f"Занято {used_gb:.1f} ГБ  ·  всего {total_gb:.1f} ГБ\n"
                 f"Свободно {100 * free / total:.0f}%  ·  "
                 f"заполнено {100 * used / total:.0f}%"
        )
        self._update_threshold_banner()

    def refresh_theme(self) -> None:
        c = self._theme.colors
        for badge, icon_label, tone in self._stat_badges:
            badge.configure(fg_color=getattr(c, tone.upper()))
            icon_label.configure(
                text_color=getattr(c, f"ON_{tone.upper()}")
            )
        body = getattr(self, "_body", None)
        if body is not None and hasattr(body, "_sync_scrollbar"):
            body._sync_scrollbar()
        try:
            self.gauge.configure(bg=c.SURFACE_LOW)
        except Exception:
            pass
        self._render_targets()
        self.set_last_clean(self._last_clean)
