from pathlib import Path

path = Path(r"D:\projects\disk_cleen\disk_cleaner_app\ui\views\startup.py")
text = path.read_text(encoding="utf-8")
start = text.index("    def _build(self) -> None:\n")
end = text.index("    def refresh(self) -> None:\n")

new_build = '''    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Автозагрузка",
            "Управление программами, которые запускаются вместе с Windows",
            icon="↗",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        MDButton(
            header.actions, self._theme, "Обновить", self.refresh,
            kind="text_muted", width=94, height=34,
        ).pack(side="right")

        controls = MDCard(self, self._theme, tone="low")
        controls.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(controls, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)

        self.disable_btn = MDButton(
            row, self._theme, "Отключить", self._disable_selected,
            kind="outlined", width=108, height=34,
        )
        self.disable_btn.pack(side="left", padx=(0, 6))

        self.enable_btn = MDButton(
            row, self._theme, "Включить", self._enable_selected,
            kind="tonal", width=100, height=34,
        )
        self.enable_btn.pack(side="left", padx=(0, 6))

        MDButton(
            row, self._theme, "Добавить", self._add_dialog,
            kind="filled", width=104, height=34,
        ).pack(side="left")

        self.info_label = MDLabel(
            row, self._theme, "Загрузка…", role="secondary", font=FONT_LABEL,
        )
        self.info_label.pack(side="right")
        self.add_label = MDLabel(
            row, self._theme, "", role="muted", font=FONT_LABEL,
        )
        self.add_label.pack(side="right", padx=(0, 10))

        # ── Таблица ───────────────────────────────────
        table_card = MDCard(self, self._theme, tone="low")
        table_card.grid(row=2, column=0, sticky="nsew")

        title_row = ctk.CTkFrame(table_card, fg_color="transparent")
        title_row.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            title_row, self._theme, "Записи автозагрузки",
            "Отключение сохраняет запись и позволяет вернуть её позже",
        ).pack(side="left")

        style_treeview("Startup", self._theme, row_height=32)
        cols = ("name", "status", "command", "source")
        self.tree = ttk.Treeview(
            table_card, columns=cols, show="headings",
            selectmode="browse", height=12, style="Startup.Treeview",
        )
        self.tree.heading("name", text="Имя")
        self.tree.heading("status", text="Статус", anchor="center")
        self.tree.heading("command", text="Команда")
        self.tree.heading("source", text="Источник")
        self.tree.column("name", width=200, minwidth=150)
        self.tree.column("status", width=90, minwidth=76, anchor="center", stretch=False)
        self.tree.column("command", width=420, minwidth=220)
        self.tree.column("source", width=110, minwidth=90)

        self._table_scroll = ctk.CTkScrollbar(
            table_card, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.tree.configure(yscrollcommand=self._table_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(14, 2), pady=(0, 12))
        self._table_scroll.pack(side="right", fill="y", padx=(0, 10), pady=(0, 12))
        self._paint_tags()

        self.refresh()

'''
path.write_text(text[:start] + new_build + text[end:], encoding="utf-8")
print("patched startup build")
