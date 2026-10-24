from pathlib import Path

path = Path(r"D:\projects\disk_cleen\disk_cleaner_app\ui\views\smart_clean.py")
text = path.read_text(encoding="utf-8")

start = text.index("    def _build(self) -> None:\n")
end = text.index("    # ── Mode switching ───────────────────────────────\n")

new_build = '''    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Очистка",
            "Безопасное сканирование и удаление временных данных",
            icon="✦",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        self.mode_var = ctk.StringVar(value="easy")
        self.mode_seg = MDSegmented(
            header.actions, self._theme,
            values=["Easy", "Advanced"],
            variable=self.mode_var,
            command=self._on_mode_change,
            width=230,
        )
        self.mode_seg.pack(side="right")
        try:
            self.mode_seg._buttons_dict["Easy"].configure(text="🟢  Easy")
            self.mode_seg._buttons_dict["Advanced"].configure(text="🔴  Advanced")
        except Exception:
            pass

        # ── Панель действий ───────────────────────────
        toolbar = MDCard(self, self._theme, tone="low")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(toolbar, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 4))

        self.scan_btn = MDButton(
            row, self._theme, "Сканировать", self.start_scan,
            kind="filled", width=136,
        )
        self.scan_btn.pack(side="left", padx=(0, 6))

        self.cancel_btn = MDButton(
            row, self._theme, "Стоп", self.cancel_scan,
            kind="outlined", width=82, state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=(0, 6))

        self.clean_btn = MDButton(
            row, self._theme, "Очистить", self.start_clean,
            kind="tonal", width=112,
        )
        self.clean_btn.pack(side="left", padx=(0, 6))

        self.preview_btn = MDButton(
            row, self._theme, "Предпросмотр", self.show_preview,
            kind="text", width=118,
        )
        self.preview_btn.pack(side="left")

        self.custom_btn = MDIconButton(
            row, self._theme, "＋", self._add_custom_rule,
            kind="tonal", size=36,
        )
        self.custom_btn.pack(side="right")

        self.sel_label = MDLabel(
            row, self._theme, "", role="secondary", font=FONT_LABEL,
        )
        self.sel_label.pack(side="right", padx=(8, 8))

        selectors = ctk.CTkFrame(toolbar, fg_color="transparent")
        selectors.pack(fill="x", padx=14, pady=(0, 10))

        MDLabel(
            selectors, self._theme, "Выбор", role="muted", font=FONT_CAPTION,
        ).pack(side="left", padx=(2, 8))

        MDButton(
            selectors, self._theme, "Всё", self.select_all,
            kind="text", width=58, height=28,
        ).pack(side="left")
        MDButton(
            selectors, self._theme, "Снять", self.deselect_all,
            kind="text_muted", width=66, height=28,
        ).pack(side="left")
        MDButton(
            selectors, self._theme, "Безопасные", self.select_safe,
            kind="text", width=104, height=28,
        ).pack(side="left")
        MDButton(
            selectors, self._theme, "Свернуть группы", self._collapse_groups,
            kind="text_muted", width=132, height=28,
        ).pack(side="right")
        MDButton(
            selectors, self._theme, "Развернуть", self._expand_groups,
            kind="text_muted", width=100, height=28,
        ).pack(side="right")
        MDButton(
            selectors, self._theme, "Сбросить сортировку", self._reset_sort,
            kind="text_muted", width=150, height=28,
        ).pack(side="right")

        # ── Таблица целей ─────────────────────────────
        tree_card = MDCard(self, self._theme, tone="low")
        tree_card.grid(row=2, column=0, sticky="nsew", pady=(0, SPACE_2))

        search_row = ctk.CTkFrame(tree_card, fg_color="transparent")
        search_row.pack(fill="x", padx=14, pady=(12, 8))

        MDLabel(
            search_row, self._theme, "⌕", role="secondary",
            font=("Segoe UI", 15),
        ).pack(side="left", padx=(0, 6))

        self.search_var = ctk.StringVar(value="")
        self.search_entry = MDEntry(
            search_row, self._theme, textvariable=self.search_var,
            placeholder_text="Поиск по названию или категории…",
            width=360,
        )
        self.search_entry.pack(side="left")

        self.filter_label = MDLabel(
            search_row, self._theme, "", role="muted", font=FONT_LABEL,
        )
        self.filter_label.pack(side="left", padx=(10, 0))

        MDButton(
            search_row, self._theme, "Группы", self._reset_sort,
            kind="text_muted", width=82, height=30,
        ).pack(side="right")

        self.tree = CleanerTree(tree_card, self._theme, self._config)
        self.tree.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self._search_trace = self.search_var.trace_add(
            "write", lambda *_: self._on_search()
        )

        MDLabel(
            self, self._theme,
            "Клик по названию категории сворачивает группу; клик по ☐ выбирает всю категорию.",
            role="muted", font=FONT_CAPTION, anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(0, 2))

'''
path.write_text(text[:start] + new_build + text[end:], encoding="utf-8")
print("patched _build")
