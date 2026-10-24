from pathlib import Path

path = Path(r"D:\projects\disk_cleen\disk_cleaner_app\ui\views\history.py")
text = path.read_text(encoding="utf-8")
start = text.index("    def _build(self) -> None:\n")
end = text.index("    def _small_button(self, parent, text: str, command, width: int = 100,\n")

new_build = '''    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "История операций",
            "Журнал очисток с фильтрами и экспортом отчётов",
            icon="≡",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        MDButton(
            header.actions, self._theme, "JSON", lambda: self._export("json"),
            kind="outlined", width=78, height=34,
        ).pack(side="right")
        MDButton(
            header.actions, self._theme, "CSV", lambda: self._export("csv"),
            kind="tonal", width=78, height=34,
        ).pack(side="right", padx=(0, 6))

        # ── Фильтры ───────────────────────────────────
        filters = MDCard(self, self._theme, tone="low")
        filters.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(filters, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 6))

        MDLabel(
            row, self._theme, "С", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(0, 4))
        self.from_var = ctk.StringVar(value="")
        MDEntry(
            row, self._theme, textvariable=self.from_var, width=110,
            placeholder_text="ГГГГ-ММ-ДД",
        ).pack(side="left")

        MDLabel(
            row, self._theme, "по", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(8, 4))
        self.to_var = ctk.StringVar(value="")
        MDEntry(
            row, self._theme, textvariable=self.to_var, width=110,
            placeholder_text="ГГГГ-ММ-ДД",
        ).pack(side="left")

        MDLabel(
            row, self._theme, "⌕", role="secondary", font=("Segoe UI", 14),
        ).pack(side="left", padx=(12, 4))
        self.query_var = ctk.StringVar(value="")
        MDEntry(
            row, self._theme, textvariable=self.query_var,
            placeholder_text="Цель, статус или заметка…",
        ).pack(side="left", fill="x", expand=True)

        MDButton(
            row, self._theme, "Применить", self._apply,
            kind="filled", width=102, height=32,
        ).pack(side="left", padx=(8, 0))
        MDButton(
            row, self._theme, "Сбросить", self._reset,
            kind="text_muted", width=88, height=32,
        ).pack(side="left", padx=(4, 0))

        self.hint_label = MDLabel(
            filters, self._theme,
            "Дата — включительно; пустое поле не ограничивает.",
            role="muted", font=FONT_CAPTION, anchor="w",
        )
        self.hint_label.pack(fill="x", padx=14, pady=(0, 10))

        self._search_trace = self.query_var.trace_add(
            "write", lambda *_: self._apply()
        )

        # ── Таблица и детали ──────────────────────────
        table_card = MDCard(self, self._theme, tone="low")
        table_card.grid(row=2, column=0, sticky="nsew", pady=(0, SPACE_2))

        style_treeview("History", self._theme, row_height=30)
        cols = ("date", "items", "freed", "targets")
        self.tree = ttk.Treeview(
            table_card, columns=cols, show="headings",
            selectmode="browse", style="History.Treeview",
        )
        self.tree.heading("date", text="Дата")
        self.tree.heading("items", text="Целей", anchor="center")
        self.tree.heading("freed", text="Освобождено", anchor="e")
        self.tree.heading("targets", text="Цели")
        self.tree.column("date", width=150, minwidth=120, stretch=False)
        self.tree.column("items", width=64, minwidth=50, anchor="center", stretch=False)
        self.tree.column("freed", width=118, minwidth=90, anchor="e", stretch=False)
        self.tree.column("targets", width=430, minwidth=200)

        self._table_scroll = ctk.CTkScrollbar(
            table_card, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.tree.configure(yscrollcommand=self._table_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(14, 2), pady=(12, 2))
        self._table_scroll.pack(side="right", fill="y", padx=(0, 10), pady=(12, 2))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        details_card = MDCard(self, self._theme, tone="low")
        details_card.grid(row=3, column=0, sticky="ew")

        details_top = ctk.CTkFrame(details_card, fg_color="transparent")
        details_top.pack(fill="x", padx=14, pady=(10, 4))
        SectionTitle(
            details_top, self._theme, "Детали записи",
            "Что именно было очищено и с каким результатом",
        ).pack(side="left")

        self.details = MDTextbox(
            details_card, self._theme, height=96, font=FONT_MONO_SMALL,
        )
        self.details.pack(fill="x", padx=14, pady=(0, 8))
        self._set_details("Выберите запись, чтобы увидеть детали очистки.")

        self.status_label = MDLabel(
            self, self._theme, "", role="muted", font=FONT_CAPTION, anchor="w",
        )
        self.grid_rowconfigure(4, weight=0)
        self.status_label.grid(row=4, column=0, sticky="ew", pady=(2, 0))

'''
path.write_text(text[:start] + new_build + text[end:], encoding="utf-8")
print("patched history build")
