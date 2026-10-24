"""
gui.py — DiskCleaner Fluent Design v3.1
Ice & Lavender, Treemap, исправленная смена темы
"""

import os, tkinter as tk, threading, datetime
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import customtkinter as ctk
import squarify

from disk_cleaner_app.legacy.core import (
    format_bytes, get_disk_free, SafetyLevel,
    load_config, save_config, add_history, get_history, get_total_freed,
    load_custom_rules, add_custom_rule, export_report,
)
from disk_cleaner_app.legacy.cleaners import define_items
from disk_cleaner_app.legacy.scanners import auto_discover_items, preview_cache_files
from disk_cleaner_app.legacy.analyzer import (
    scan_top_folders, scan_large_files,
    find_duplicates_fast, find_duplicates_exact,
    find_empty_folders, get_startup_items,
)

# ── Палитра ──
ICE = "#6ee7b7"
ICE_DARK = "#3b9e7a"
LAVENDER = "#a78bfa"
LAVENDER_DARK = "#7c3aed"
BG_CARD = "#16162a"
BG_DEEP = "#0c0c18"
BORDER_CARD = "#2a2a50"
TEXT_PRI = "#f0f0ff"
TEXT_SEC = "#9090b0"
TEXT_MUTED = "#606080"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class DiskCleanerApp:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("🧹 DiskCleaner — Очиститель Диска")
        self.root.geometry("1050x720")
        self.root.minsize(850, 600)

        self.config = load_config()
        self.items = define_items()
        self.auto_items = []
        self.var_map = {}
        self.freed_bytes = 0
        self.cleaned_items = []
        self.active_view = "cleaner"

        ctk.set_appearance_mode(self.config.get("theme", "dark"))
        self.root.configure(fg_color=BG_DEEP)

        self._build_ui()
        self._switch_view("cleaner")
        self._update_disk_info()

        self.root.bind("<Control-s>", lambda e: self.start_scan())
        self.root.bind("<Control-c>", lambda e: self.start_clean())
        self.root.bind("<Control-a>", lambda e: self.select_all())
        self.root.mainloop()

    # ─────────────────────────────────────
    # СБОРКА UI
    # ─────────────────────────────────────

    def _build_ui(self):
        # Всё в одном главном контейнере с отступами
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=14, pady=14)

        self._build_header(main)
        self._build_nav(main)
        self._build_content(main)
        self._build_bottom(main)
        self._build_views()

    def _build_header(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                             border_width=1, border_color=BORDER_CARD)
        card.pack(fill="x", pady=(0, 8))

        # Строка: лого | прогресс-бар | история
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(8, 6))

        # Лого
        ctk.CTkLabel(row, text="🧹  DiskCleaner",
                      font=("Segoe UI", 15, "bold"),
                      text_color=TEXT_PRI).pack(side="left")

        # Прогресс-бар + метка
        bar_frame = ctk.CTkFrame(row, fg_color="transparent")
        bar_frame.pack(side="left", fill="x", expand=True, padx=(20, 10))

        self.disk_bar = ctk.CTkProgressBar(bar_frame, height=5, corner_radius=3,
                                            progress_color=ICE, fg_color="#1e1e3a")
        self.disk_bar.pack(fill="x")
        self.disk_bar.set(0.8)

        self.disk_label = ctk.CTkLabel(bar_frame, text="💾 Загрузка...",
                                        font=("Segoe UI", 9), text_color=TEXT_SEC, anchor="w")
        self.disk_label.pack(fill="x")

        # История
        ctk.CTkLabel(row, text="📈", font=("Segoe UI", 12),
                      text_color=TEXT_MUTED).pack(side="left")
        self.hist_label = ctk.CTkLabel(row, text="0", font=("Segoe UI", 11, "bold"),
                                        text_color=ICE)
        self.hist_label.pack(side="left", padx=(2, 0))

        # Кнопка темы (☀️/🌙)
        self.theme_btn = ctk.CTkButton(
            row, text="🌙" if self.config.get("theme", "dark") == "dark" else "☀️",
            command=self._toggle_theme,
            fg_color="transparent", hover_color="#1e1e3e",
            text_color=TEXT_SEC, corner_radius=6, width=32, height=28,
            font=("Segoe UI", 12)
        )
        self.theme_btn.pack(side="right", padx=(5, 0))

        # Кнопка настроек (⚙️ быстрая)
        ctk.CTkButton(
            row, text="⚙️", command=lambda: self._switch_view("settings"),
            fg_color="transparent", hover_color="#1e1e3e",
            text_color=TEXT_SEC, corner_radius=6, width=32, height=28,
            font=("Segoe UI", 12)
        ).pack(side="right", padx=(2, 0))

    def _build_nav(self, parent):
        nav_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER_CARD)
        nav_frame.pack(fill="x", pady=(0, 8))

        # Кнопки навигации
        self.nav_btns = {}
        for i, (text, vid, color) in enumerate([
            ("🧹  Очистка", "cleaner", ICE),
            ("📊  Анализ", "analyzer", LAVENDER),
            ("🔍  Дубликаты", "duplicates", LAVENDER),
            ("⚙️  Настройки", "settings", TEXT_SEC),
        ]):
            btn = ctk.CTkButton(
                nav_frame, text=text,
                font=("Segoe UI", 12, "bold"),
                fg_color="transparent", text_color=TEXT_MUTED,
                hover_color="#1e1e3e", corner_radius=8,
                command=lambda v=vid: self._switch_view(v),
                height=30
            )
            btn.pack(side="left", padx=(4, 0) if i > 0 else (8, 0), pady=6)
            self.nav_btns[vid] = btn

    def _switch_view(self, vid):
        self.active_view = vid
        for _vid, btn in self.nav_btns.items():
            btn.configure(
                text_color=TEXT_PRI if _vid == vid else TEXT_MUTED,
                fg_color="#1e1e3e" if _vid == vid else "transparent"
            )
        for v in self.views.values():
            v.pack_forget()
        if vid in self.views:
            self.views[vid].pack(fill="both", expand=True)
            if vid == "settings":
                self._refresh_settings()

    def _build_content(self, parent):
        self.content_card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                                          border_width=1, border_color=BORDER_CARD)
        self.content_card.pack(fill="both", expand=True)

        self.views_frame = ctk.CTkFrame(self.content_card, fg_color="transparent")
        self.views_frame.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_bottom(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                             border_width=1, border_color=BORDER_CARD)
        card.pack(fill="x", pady=(8, 0))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(6, 4))

        self.status_bar = ctk.CTkLabel(row, text="💡 Нажми «Сканировать»",
                                        font=("Segoe UI", 11), text_color=TEXT_SEC,
                                        anchor="w")
        self.status_bar.pack(side="left", fill="x", expand=True)

        self.progress_label = ctk.CTkLabel(row, text="", font=("Segoe UI", 10),
                                            text_color=TEXT_MUTED)
        self.progress_label.pack(side="right", padx=(10, 0))

        self.progress = ctk.CTkProgressBar(card, height=4, corner_radius=2,
                                            progress_color=ICE, fg_color="#1e1e3a")
        self.progress.pack(fill="x", padx=14, pady=(0, 4))
        self.progress.set(0)

        # Лог
        self.log_toggle = ctk.CTkButton(
            card, text="📋  Показать лог",
            command=self._toggle_log,
            fg_color="transparent", hover_color="#1e1e3e",
            text_color=TEXT_MUTED, font=("Segoe UI", 10),
            anchor="w", corner_radius=6, height=22
        )
        self.log_toggle.pack(anchor="w", padx=14, pady=(0, 4))

        self.log_text = ctk.CTkTextbox(
            card, height=80, font=("Consolas", 9),
            fg_color=BG_DEEP, text_color=TEXT_SEC,
            corner_radius=8, wrap="word"
        )

    def _toggle_log(self):
        if self.log_text.winfo_viewable():
            self.log_text.pack_forget()
            self.log_toggle.configure(text="📋  Показать лог")
        else:
            self.log_text.pack(fill="x", padx=14, pady=(0, 8))
            self.log_toggle.configure(text="📋  Скрыть лог")

    # ─────────────────────────────────────
    # ТЕМА
    # ─────────────────────────────────────

    def _toggle_theme(self):
        current = self.config.get("theme", "dark")
        new = "light" if current == "dark" else "dark"
        self.config["theme"] = new
        save_config(self.config)
        ctk.set_appearance_mode(new)
        self.root.configure(fg_color="#f0f0f0" if new == "light" else BG_DEEP)
        self.theme_btn.configure(text="☀️" if new == "dark" else "🌙")
        # Force rebuild of views to apply new theme colors
        for v in self.views.values():
            v.configure(fg_color="transparent")
        self._log(f"🎨 Тема: {new}")

    # ─────────────────────────────────────
    # ВЬЮХИ
    # ─────────────────────────────────────

    def _build_views(self):
        self.views = {}
        self._build_cleaner_view()
        self._build_analyzer_view()
        self._build_duplicates_view()
        self._build_settings_view()

    # ─── Cleaner ────────────────────────────

    def _build_cleaner_view(self):
        v = ctk.CTkFrame(self.views_frame, fg_color="transparent")
        self.views["cleaner"] = v

        # Кнопки
        ctrl = ctk.CTkFrame(v, fg_color="transparent")
        ctrl.pack(fill="x", pady=(0, 6))

        self.scan_btn = ctk.CTkButton(
            ctrl, text="📡  Сканировать", command=self.start_scan,
            fg_color=ICE, hover_color=ICE_DARK, corner_radius=8,
            font=("Segoe UI", 11, "bold"), height=32
        )
        self.scan_btn.pack(side="left", padx=(0, 4))

        self.clean_btn = ctk.CTkButton(
            ctrl, text="🧹  Очистить", command=self.start_clean,
            fg_color=LAVENDER, hover_color=LAVENDER_DARK, corner_radius=8,
            font=("Segoe UI", 11, "bold"), height=32
        )
        self.clean_btn.pack(side="left", padx=(0, 4))

        self.preview_btn = ctk.CTkButton(
            ctrl, text="👁️ Preview", command=self.show_preview,
            fg_color="#2a2a4e", hover_color="#3a3a6e", corner_radius=8,
            font=("Segoe UI", 10), height=32
        )
        self.preview_btn.pack(side="left", padx=(0, 10))

        ctk.CTkButton(ctrl, text="✅ Всё", command=self.select_all,
                       fg_color="transparent", hover_color="#1e1e3e",
                       text_color=ICE, corner_radius=8,
                       font=("Segoe UI", 11), height=32
                       ).pack(side="left", padx=(0, 2))
        ctk.CTkButton(ctrl, text="❌ Снять", command=self.deselect_all,
                       fg_color="transparent", hover_color="#1e1e3e",
                       text_color=TEXT_MUTED, corner_radius=8,
                       font=("Segoe UI", 11), height=32
                       ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(ctrl, text="➕", command=self.add_custom_rule_dialog,
                       fg_color="transparent", hover_color="#1e1e3e",
                       text_color=TEXT_MUTED, width=30, height=32,
                       corner_radius=8, font=("Segoe UI", 14)
                       ).pack(side="right")

        # Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Ice.Treeview",
                        background="#12122a", foreground=TEXT_PRI,
                        fieldbackground="#12122a", rowheight=28,
                        font=("Segoe UI", 10))
        style.configure("Ice.Treeview.Heading",
                        background="#1a1a38", foreground=TEXT_SEC,
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Ice.Treeview", background=[("selected", "#2a2a5e")])
        style.map("Ice.Treeview.Heading", background=[("active", "#1e1e42")])

        cols = ("check", "name", "size", "safety", "group")
        self.tree = ttk.Treeview(v, columns=cols, show="headings",
                                  selectmode="none", style="Ice.Treeview", height=14)
        self.tree.heading("check", text="")
        self.tree.heading("name", text="Цель очистки")
        self.tree.heading("size", text="Размер", anchor="e")
        self.tree.heading("safety", text="", anchor="center")
        self.tree.heading("group", text="Категория")
        self.tree.column("check", width=35, minwidth=30, anchor="center", stretch=False)
        self.tree.column("name", width=400, minwidth=280)
        self.tree.column("size", width=130, minwidth=90, anchor="e")
        self.tree.column("safety", width=35, minwidth=30, anchor="center")
        self.tree.column("group", width=140, minwidth=100)
        self.tree.tag_configure("safe", foreground=ICE)
        self.tree.tag_configure("caution", foreground="#fbbf24")
        self.tree.tag_configure("advanced", foreground="#f87171")
        self.tree.tag_configure("not_scanned", foreground=TEXT_MUTED)

        scroll = ctk.CTkScrollbar(v, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

    # ─── Analyzer ──────────────────────────

    def _build_analyzer_view(self):
        v = ctk.CTkFrame(self.views_frame, fg_color="transparent")
        self.views["analyzer"] = v

        # Верх: бар + кнопки
        top = ctk.CTkFrame(v, fg_color="transparent")
        top.pack(fill="x", pady=(0, 6))

        self.ana_disk = ctk.CTkProgressBar(top, height=6, corner_radius=3,
                                            progress_color=ICE, fg_color="#1e1e3a")
        self.ana_disk.pack(fill="x", pady=(0, 3))
        self.ana_disk.set(0.8)

        self.ana_label = ctk.CTkLabel(top, text="💾 Загрузка...",
                                       font=("Segoe UI", 9), text_color=TEXT_SEC)
        self.ana_label.pack(anchor="w")

        btns = ctk.CTkFrame(v, fg_color="transparent")
        btns.pack(fill="x", pady=(4, 6))

        for text, cmd, color in [
            ("📁  Топ папок", "top", ICE),
            ("📄  >500 МБ", "big500", LAVENDER),
            ("📄  >1 ГБ", "big1024", LAVENDER),
            ("📂  Пустые папки", "empty", "#fbbf24"),
            ("🚀  Автозагрузка", "startup", TEXT_SEC),
            ("🗺️  Treemap", "treemap", ICE),
        ]:
            ctk.CTkButton(btns, text=text,
                           command=lambda m=cmd: self._run_analyzer(m),
                           fg_color="#1e1e3e", hover_color="#2a2a5e",
                           text_color=color, corner_radius=8,
                           font=("Segoe UI", 10), height=30
                           ).pack(side="left", padx=(0, 4))

        # Результаты: текст + treemap canvas
        self.ana_pane = ctk.CTkFrame(v, fg_color="transparent")
        self.ana_pane.pack(fill="both", expand=True)

        self.ana_text = ctk.CTkTextbox(self.ana_pane, font=("Consolas", 10),
                                        fg_color=BG_DEEP, text_color=TEXT_SEC,
                                        corner_radius=8, wrap="word")
        self.ana_text.pack(fill="both", expand=True)

        # Canvas для treemap
        self.treemap_canvas = tk.Canvas(
            self.ana_pane, bg="#12122a", highlightthickness=0,
            cursor="hand2"
        )
        self.treemap_canvas.bind("<Motion>", self._treemap_hover)
        self.treemap_canvas.bind("<Button-1>", self._treemap_click)
        self.treemap_rects = []

    # ─── Duplicates ────────────────────────

    def _build_duplicates_view(self):
        v = ctk.CTkFrame(self.views_frame, fg_color="transparent")
        self.views["duplicates"] = v

        ctk.CTkLabel(v, text="🔍  Поиск дубликатов",
                      font=("Segoe UI", 14, "bold"),
                      text_color=LAVENDER).pack(anchor="w", pady=(0, 8))

        pf = ctk.CTkFrame(v, fg_color="transparent")
        pf.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(pf, text="Папка:", font=("Segoe UI", 10),
                      text_color=TEXT_SEC).pack(side="left", padx=(0, 6))

        self.dup_path = ctk.StringVar(value="C:\\Users\\zxcpap14")
        ctk.CTkEntry(pf, textvariable=self.dup_path, font=("Segoe UI", 10),
                      corner_radius=8, fg_color=BG_DEEP,
                      border_color=BORDER_CARD, height=30
                      ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(pf, text="📁", command=self._browse_dup,
                       fg_color="#1e1e3e", hover_color="#2a2a5e",
                       corner_radius=8, width=30, height=30
                       ).pack(side="right")

        bf = ctk.CTkFrame(v, fg_color="transparent")
        bf.pack(fill="x", pady=(2, 6))

        self.dup_fast = ctk.CTkButton(bf, text="⚡  Быстрый", command=self._start_dup_fast,
                                       fg_color=ICE, hover_color=ICE_DARK,
                                       corner_radius=8, font=("Segoe UI", 10), height=30)
        self.dup_fast.pack(side="left", padx=(0, 4))

        self.dup_exact = ctk.CTkButton(bf, text="🎯  Точный (MD5)", command=self._start_dup_exact,
                                        fg_color=LAVENDER, hover_color=LAVENDER_DARK,
                                        corner_radius=8, font=("Segoe UI", 10), height=30)
        self.dup_exact.pack(side="left", padx=(0, 4))

        self.dup_status = ctk.CTkLabel(bf, text="", font=("Segoe UI", 10), text_color=TEXT_MUTED)
        self.dup_status.pack(side="right")

        self.dup_text = ctk.CTkTextbox(v, font=("Consolas", 10),
                                        fg_color=BG_DEEP, text_color=TEXT_SEC,
                                        corner_radius=8, wrap="word")
        self.dup_text.pack(fill="both", expand=True)

    # ─── Settings ──────────────────────────

    def _build_settings_view(self):
        v = ctk.CTkFrame(self.views_frame, fg_color="transparent")
        self.views["settings"] = v

        ctk.CTkLabel(v, text="⚙️  Настройки",
                      font=("Segoe UI", 14, "bold"),
                      text_color=TEXT_PRI).pack(anchor="w", pady=(0, 10))

        # Тема
        f1 = ctk.CTkFrame(v, fg_color=BG_DEEP, corner_radius=10)
        f1.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(f1, text="Тема:", font=("Segoe UI", 12),
                      text_color=TEXT_PRI).pack(anchor="w", padx=14, pady=(10, 4))

        tv = ctk.StringVar(value=self.config.get("theme", "dark"))
        ctk.CTkOptionMenu(f1, values=["dark", "light", "system"],
                           variable=tv, font=("Segoe UI", 11), corner_radius=8,
                           fg_color="#1e1e3a", button_color=LAVENDER,
                           dropdown_fg_color="#1e1e3a",
                           command=lambda v: self._set_theme(v)
                           ).pack(anchor="w", padx=14, pady=(0, 10))

        # Корзина
        f2 = ctk.CTkFrame(v, fg_color=BG_DEEP, corner_radius=10)
        f2.pack(fill="x", pady=(0, 6))

        self.recycle_var = ctk.BooleanVar(value=self.config.get("to_recycle", True))
        ctk.CTkSwitch(f2, text="🗑️  Перемещать в корзину",
                       variable=self.recycle_var, command=self._save_settings,
                       font=("Segoe UI", 11), progress_color=ICE,
                       fg_color="#1e1e3a"
                       ).pack(anchor="w", padx=14, pady=(10, 10))

        # Безопасный режим
        f3 = ctk.CTkFrame(v, fg_color=BG_DEEP, corner_radius=10)
        f3.pack(fill="x", pady=(0, 6))

        self.safe_var = ctk.BooleanVar(value=self.config.get("safe_mode", True))
        ctk.CTkSwitch(f3, text="🛡️  Безопасный режим (только 🟢)",
                       variable=self.safe_var, command=self._save_settings,
                       font=("Segoe UI", 11), progress_color=LAVENDER,
                       fg_color="#1e1e3a"
                       ).pack(anchor="w", padx=14, pady=(10, 10))

        # История
        f4 = ctk.CTkFrame(v, fg_color=BG_DEEP, corner_radius=10)
        f4.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(f4, text="📋  История очисток",
                      font=("Segoe UI", 12, "bold"),
                      text_color=ICE).pack(anchor="w", padx=14, pady=(8, 4))

        self.hist_text = ctk.CTkTextbox(f4, height=70, font=("Consolas", 9),
                                         fg_color=BG_CARD, text_color=TEXT_SEC,
                                         corner_radius=8, wrap="word")
        self.hist_text.pack(fill="x", padx=14, pady=(2, 8))

        # Правила
        f5 = ctk.CTkFrame(v, fg_color=BG_DEEP, corner_radius=10)
        f5.pack(fill="x")

        ctk.CTkLabel(f5, text="🧩  Пользовательские правила",
                      font=("Segoe UI", 12, "bold"),
                      text_color=LAVENDER).pack(anchor="w", padx=14, pady=(8, 4))

        self.rules_text = ctk.CTkTextbox(f5, height=60, font=("Consolas", 9),
                                          fg_color=BG_CARD, text_color=TEXT_SEC,
                                          corner_radius=8, wrap="word")
        self.rules_text.pack(fill="x", padx=14, pady=(2, 8))

    # ─────────────────────────────────────
    # TREEVIEW
    # ─────────────────────────────────────

    def _populate_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.var_map.clear()
        for item in self.items + self.auto_items:
            v = ctk.BooleanVar(value=True)
            self.var_map[item.id] = v
            sz = "—" if not item.scanned else format_bytes(item.size)
            tag = "safe" if item.safety == SafetyLevel.SAFE else \
                  "caution" if item.safety == SafetyLevel.CAUTION else "advanced"
            if not item.scanned and item.size == 0:
                tag = "not_scanned"
            self.tree.insert("", "end", iid=item.id,
                              values=("☑", f"  {item.name}", sz, item.safety, item.group),
                              tags=(tag,))

    def _on_tree_click(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid or iid not in self.var_map:
            return
        self.var_map[iid].set(not self.var_map[iid].get())
        vals = list(self.tree.item(iid, "values"))
        if vals:
            vals[0] = "☑" if self.var_map[iid].get() else "☐"
            self.tree.item(iid, values=vals)

    def select_all(self):
        for v in self.var_map.values():
            v.set(True)
        for iid in self.var_map:
            vals = list(self.tree.item(iid, "values"))
            if vals:
                vals[0] = "☑"
                self.tree.item(iid, values=vals)

    def deselect_all(self):
        for v in self.var_map.values():
            v.set(False)
        for iid in self.var_map:
            vals = list(self.tree.item(iid, "values"))
            if vals:
                vals[0] = "☐"
                self.tree.item(iid, values=vals)

    # ─────────────────────────────────────
    # СКАНИРОВАНИЕ
    # ─────────────────────────────────────

    def start_scan(self):
        self.scan_btn.configure(state="disabled")
        self.clean_btn.configure(state="disabled")
        self.progress.set(0)
        n = len(self.items) + 5
        step = 1.0 / n

        def worker():
            for i, item in enumerate(self.items):
                item.size = item.get_size()
                item.scanned = True
                self.root.after(0, lambda v=(i+1)*step: self.progress.set(v))
            try:
                self.auto_items = auto_discover_items()
                for a in self.auto_items:
                    a.scanned = True
            except Exception:
                pass
            self.root.after(0, self._scan_done)

        threading.Thread(target=worker, daemon=True).start()

    def _scan_done(self):
        self._populate_tree()
        self.scan_btn.configure(state="normal")
        self.clean_btn.configure(state="normal")
        self.progress.set(1.0)
        total = sum(x.size for x in self.items + self.auto_items)
        self.status_bar.configure(text=f"✅ Найдено: {format_bytes(total)}",
                                   text_color=ICE)
        self._update_disk_info()

    # ─────────────────────────────────────
    # ПРЕДПРОСМОТР
    # ─────────────────────────────────────

    def show_preview(self):
        sel = [i for i in self.items + self.auto_items
               if self.var_map.get(i.id, ctk.BooleanVar()).get()
               and i.can_preview and i.preview_path]
        if not sel:
            return
        item = sel[0]
        p = Path(item.preview_path)
        if not p.exists():
            return
        files = preview_cache_files(p) or []
        text = f"📂 {item.preview_path}\n{'─'*50}\n"
        for f in files:
            text += f"  {'📁' if f['is_dir'] else '📄'}  {f['name']}\n"
        w = ctk.CTkToplevel(self.root)
        w.title(f"👁️ {item.name}")
        w.geometry("600x400")
        t = ctk.CTkTextbox(w, font=("Consolas", 9),
                             fg_color=BG_DEEP, text_color=TEXT_SEC, corner_radius=8)
        t.pack(fill="both", expand=True, padx=10, pady=10)
        t.insert("1.0", text)
        t.configure(state="disabled")

    # ─────────────────────────────────────
    # ОЧИСТКА
    # ─────────────────────────────────────

    def start_clean(self):
        sel = [i for i in self.items + self.auto_items
               if self.var_map.get(i.id, ctk.BooleanVar()).get() and i.size > 0]
        if not sel:
            return
        total = sum(i.size for i in sel)
        if not messagebox.askyesno("", f"Очистить {len(sel)} целей?\n+{format_bytes(total)}"):
            return
        self.scan_btn.configure(state="disabled")
        self.clean_btn.configure(state="disabled")
        self.progress.set(0)
        self.freed_bytes = 0
        self.cleaned_items = []
        step = 1.0 / len(sel)

        def worker():
            for i, item in enumerate(sel):
                st, detail = item.clean()
                freed = item.size if st == "OK" else 0
                self.freed_bytes += freed
                if freed > 0:
                    self.cleaned_items.append(item)
                self.root.after(0, lambda v=(i+1)*step: self.progress.set(v))
            self.root.after(0, self._clean_done, len(sel))

        threading.Thread(target=worker, daemon=True).start()

    def _clean_done(self, n):
        self.scan_btn.configure(state="normal")
        self.progress.set(1.0)
        self.status_bar.configure(text=f"✅ Освобождено: {format_bytes(self.freed_bytes)}",
                                   text_color=ICE)
        self._update_disk_info()
        if self.freed_bytes > 0:
            add_history(n, self.freed_bytes)
        if self.freed_bytes > 100e6 and messagebox.askyesno("", "Сохранить отчёт?"):
            fn = f"diskcleaner_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
            fp = os.path.join(os.path.expanduser("~"), "Desktop", fn)
            if export_report(self.cleaned_items, self.freed_bytes, fp):
                self._log(f"📄 Отчёт: {fp}")

    # ─────────────────────────────────────
    # ПРАВИЛА
    # ─────────────────────────────────────

    def add_custom_rule_dialog(self):
        w = ctk.CTkToplevel(self.root)
        w.title("➕ Свой путь")
        w.geometry("420x200")
        w.attributes("-topmost", True)
        nv, pv = ctk.StringVar(), ctk.StringVar()
        for lbl, var in [("Название:", nv), ("Путь:", pv)]:
            ctk.CTkLabel(w, text=lbl, font=("Segoe UI", 10),
                          text_color=TEXT_SEC).pack(pady=(6, 2))
            ctk.CTkEntry(w, textvariable=var, font=("Segoe UI", 10),
                          corner_radius=8).pack(padx=20, fill="x")

        def save():
            n, p = nv.get().strip(), pv.get().strip()
            if not n or not p:
                return
            if not os.path.exists(p) and not messagebox.askyesno("", "Путь не существует?"):
                return
            add_custom_rule(n, p)
            self.items = define_items()
            self._populate_tree()
            w.destroy()

        ctk.CTkButton(w, text="💾 Сохранить", command=save,
                       fg_color=ICE, hover_color=ICE_DARK,
                       corner_radius=8).pack(pady=12)

    # ─────────────────────────────────────
    # АНАЛИЗАТОР
    # ─────────────────────────────────────

    def _run_analyzer(self, mode):
        if mode == "treemap":
            self._show_treemap()
            return
        self.ana_text.pack(fill="both", expand=True)
        self.treemap_canvas.pack_forget()
        self.ana_text.configure(state="normal")
        self.ana_text.delete("1.0", "end")
        self.ana_text.insert("1.0", "🔄 Сканирование...")
        self.ana_text.configure(state="disabled")
        threading.Thread(target=lambda: self._analyze_worker(mode), daemon=True).start()

    def _analyze_worker(self, mode):
        text = ""
        if mode == "top":
            text = "📊  ТОП-50 ПАПОК\n" + "═" * 50 + "\n"
            for i, f in enumerate(scan_top_folders("C:\\", 50), 1):
                b = "▓" * min(int(f["size"] / (1024**3)) + 1, 25)
                text += f"{i:2d}. {f['name']:35s} {format_bytes(f['size']):>10s}  {b}\n"
        elif mode.startswith("big"):
            mb = int(mode[3:])
            text = f"📄  ФАЙЛЫ >{mb} МБ\n" + "═" * 50 + "\n"
            for i, f in enumerate(scan_large_files("C:\\", mb, 50), 1):
                text += f"{i:2d}. {format_bytes(f['size']):>10s}  {f['name']}\n     📍 {f['path']}\n"
        elif mode == "empty":
            empty = find_empty_folders("C:\\Users")
            text = f"📂  ПУСТЫЕ ПАПКИ: {len(empty)}\n" + "═" * 50 + "\n"
            for f in empty[:30]:
                text += f"  📁 {f}\n"
            if len(empty) > 30:
                text += f"  ... +{len(empty)-30}\n"
        elif mode == "startup":
            items = get_startup_items()
            text = f"🚀  АВТОЗАГРУЗКА: {len(items)}\n" + "═" * 50 + "\n"
            for s in items:
                text += f"  • {s['name']}\n"
        self.root.after(0, lambda t=text: self._show_ana_text(t))

    def _show_ana_text(self, text):
        self.ana_text.configure(state="normal")
        self.ana_text.delete("1.0", "end")
        self.ana_text.insert("1.0", text)
        self.ana_text.configure(state="disabled")

    # ─────────────────────────────────────
    # TREEMAP (WinDirStat)
    # ─────────────────────────────────────

    def _show_treemap(self):
        self.ana_text.pack_forget()
        self.treemap_canvas.pack(fill="both", expand=True)
        self.treemap_canvas.delete("all")
        self.treemap_rects = []

        threading.Thread(target=self._treemap_worker, daemon=True).start()

    def _treemap_worker(self):
        folders = scan_top_folders("C:\\", 30)
        if not folders:
            self.root.after(0, lambda: self.treemap_canvas.create_text(
                300, 200, text="Нет данных", fill=TEXT_MUTED,
                font=("Segoe UI", 14)))
            return

        names = [f["name"] for f in folders]
        sizes = [max(f["size"], 1) for f in folders]

        # Цвета по группам
        palette = ["#6ee7b7", "#a78bfa", "#fbbf24", "#f87171",
                    "#60a5fa", "#34d399", "#f472b6", "#f97316",
                    "#22d3ee", "#e879f9", "#a3e635", "#fb923c"]

        cw, ch = 680, 360  # Canvas size
        norm = squarify.normalize_sizes(sizes, cw, ch)
        rects = squarify.squarify(norm, 0, 0, cw, ch)

        drawn = []
        for i, r in enumerate(rects):
            color = palette[i % len(palette)]
            drawn.append({
                "x": r["x"], "y": r["y"],
                "w": r["dx"], "h": r["dy"],
                "name": names[i] if i < len(names) else f"#{i}",
                "size": sizes[i] if i < len(sizes) else 0,
                "color": color,
            })

        self.root.after(0, lambda d=drawn: self._draw_treemap(d))

    def _draw_treemap(self, rects):
        self.treemap_canvas.delete("all")
        self.treemap_rects = rects
        pad = 2

        for r in rects:
            x0, y0 = r["x"] + pad, r["y"] + pad
            x1, y1 = r["x"] + r["w"] - pad, r["y"] + r["h"] - pad
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue

            r["canvas_id"] = self.treemap_canvas.create_rectangle(
                x0, y0, x1, y1,
                fill=r["color"], outline=BG_CARD, width=2
            )

            # Текст, если влезает
            if x1 - x0 > 40 and y1 - y0 > 20:
                txt = f"{r['name']}\n{format_bytes(r['size'])}"
                self.treemap_canvas.create_text(
                    (x0 + x1) / 2, (y0 + y1) / 2,
                    text=txt, fill="#0c0c18", font=("Segoe UI", 8, "bold"),
                    justify="center"
                )

    def _treemap_hover(self, e):
        """Подсветка при наведении."""
        for r in self.treemap_rects:
            cid = r.get("canvas_id")
            if cid:
                self.treemap_canvas.itemconfig(cid, width=2)
        for r in self.treemap_rects:
            cid = r.get("canvas_id")
            if not cid:
                continue
            coords = self.treemap_canvas.coords(cid)
            if len(coords) >= 4:
                if coords[0] <= e.x <= coords[2] and coords[1] <= e.y <= coords[3]:
                    self.treemap_canvas.itemconfig(cid, width=3, outline="white")
                    break

    def _treemap_click(self, e):
        """Открыть папку при клике."""
        for r in self.treemap_rects:
            cid = r.get("canvas_id")
            if not cid:
                continue
            coords = self.treemap_canvas.coords(cid)
            if len(coords) >= 4:
                if coords[0] <= e.x <= coords[2] and coords[1] <= e.y <= coords[3]:
                    path = f"C:\\{r['name']}"
                    if os.path.exists(path):
                        os.startfile(path)
                    break

    # ─────────────────────────────────────
    # ДУБЛИКАТЫ
    # ─────────────────────────────────────

    def _start_dup_fast(self):
        self.dup_status.configure(text="⚡")
        threading.Thread(target=self._dup_worker("fast"), daemon=True).start()

    def _start_dup_exact(self):
        self.dup_status.configure(text="🎯")
        threading.Thread(target=self._dup_worker("exact"), daemon=True).start()

    def _dup_worker(self, mode):
        fn = find_duplicates_fast if mode == "fast" else find_duplicates_exact
        dups = fn(self.dup_path.get())
        text = f"{'⚡ Быстрый' if mode == 'fast' else '🎯 MD5'}: {len(dups)} дубликатов\n"
        text += "═" * 50 + "\n"
        for d in dups[:50]:
            text += f"📄 {d['name']:40s} {format_bytes(d['size'])}\n  1: {d['file1']}\n  2: {d['file2']}\n\n"
        self.root.after(0, lambda t=text, n=len(dups): self._show_dup(t, n))

    def _show_dup(self, text, n):
        self.dup_text.configure(state="normal")
        self.dup_text.delete("1.0", "end")
        self.dup_text.insert("1.0", text)
        self.dup_text.configure(state="disabled")
        self.dup_status.configure(text=f"✅ {n}")

    # ─────────────────────────────────────
    # НАСТРОЙКИ
    # ─────────────────────────────────────

    def _set_theme(self, theme):
        self.config["theme"] = theme
        save_config(self.config)
        ctk.set_appearance_mode(theme)
        self.root.configure(fg_color="#f0f0f0" if theme == "light" else BG_DEEP)
        self.theme_btn.configure(text="☀️" if theme == "dark" else "🌙")

    def _save_settings(self):
        self.config["to_recycle"] = self.recycle_var.get()
        self.config["safe_mode"] = self.safe_var.get()
        save_config(self.config)

    def _refresh_settings(self):
        for w, data in [(self.hist_text, get_history(10)),
                         (self.rules_text, load_custom_rules())]:
            w.configure(state="normal")
            w.delete("1.0", "end")
            if data:
                for row in (data if isinstance(data, list) else []):
                    if isinstance(row, tuple):
                        w.insert("end", f"  • {row[0][:19]} — {row[1]} целей, {format_bytes(row[2])}\n")
                    elif isinstance(row, dict):
                        w.insert("end", f"  • {row.get('name')} → {row.get('path')}\n")
                if isinstance(data[0], tuple):
                    w.insert("end", f"\n  📊 Всего: {format_bytes(get_total_freed())}\n")
            else:
                w.insert("end", "  (пусто)\n")
            w.configure(state="disabled")

    # ─────────────────────────────────────
    # ОБНОВЛЕНИЕ ДИСКА
    # ─────────────────────────────────────

    def _update_disk_info(self):
        free, total = get_disk_free()
        if total <= 0:
            return
        pct = free / total
        self.disk_bar.set(1 - pct)
        gb = free / (1024**3)
        self.disk_label.configure(
            text=f"💾  Свободно: {gb:.1f} ГБ  |  "
                 f"Занято: {(total-free)/(1024**3):.1f} / {total/(1024**3):.1f} ГБ")
        try:
            self.ana_disk.set(1 - pct)
            self.ana_label.configure(text=f"💾  {gb:.1f} ГБ свободно из {total/(1024**3):.1f} ГБ")
        except Exception:
            pass
        tf = get_total_freed()
        self.hist_label.configure(text=f"{format_bytes(tf)}")

    # ─────────────────────────────────────
    # ХЕЛПЕРЫ
    # ─────────────────────────────────────

    def _browse_dup(self):
        p = filedialog.askdirectory(initialdir="C:\\Users\\zxcpap14")
        if p:
            self.dup_path.set(p)

    def _log(self, msg):
        if not hasattr(self, "log_text"):
            return
        ts = datetime.datetime.now().strftime("%H:%M")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main():
    DiskCleanerApp()
