from pathlib import Path

path = Path(r"D:\projects\disk_cleen\disk_cleaner_app\ui\views\disks.py")
text = path.read_text(encoding="utf-8")
start = text.index("    def _build(self) -> None:\n")
end = text.index("    # ── Данные ──────────────────────────────────────\n")

new_build = '''    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Диски и здоровье",
            "SMART-показатели и проверка поверхности без записи",
            icon="◉",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        self.refresh_btn = MDButton(
            header.actions, self._theme, "Обновить", self.refresh,
            kind="tonal", width=104, height=34,
        )
        self.refresh_btn.pack(side="right")

        # ── Таблица дисков ────────────────────────────
        table_card = MDCard(self, self._theme, tone="low")
        table_card.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        top = ctk.CTkFrame(table_card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            top, self._theme, "Физические диски",
            "Выберите строку, чтобы увидеть подробности",
        ).pack(side="left")

        style_treeview("Disks", self._theme, row_height=30)
        self.tree = ttk.Treeview(
            table_card, columns=(
                "index", "model", "bus", "size", "health", "temp", "hours", "wear",
            ),
            show="headings", selectmode="browse", style="Disks.Treeview", height=4,
        )
        columns: list[tuple[str, str, int, Literal["center", "w", "e"]]] = [
            ("index", "№", 38, "center"),
            ("model", "Модель", 220, "w"),
            ("bus", "Шина", 78, "w"),
            ("size", "Объём", 92, "e"),
            ("health", "Здоровье", 100, "center"),
            ("temp", "Темп.", 62, "e"),
            ("hours", "Наработка", 94, "e"),
            ("wear", "Износ", 62, "e"),
        ]
        for column, title, width, anchor in columns:
            self.tree.heading(column, text=title)
            self.tree.column(
                column, width=width, anchor=anchor, stretch=column == "model",
            )

        scroll = ctk.CTkScrollbar(
            table_card, command=self.tree.yview, width=10,
            fg_color="transparent", button_color=self._theme.colors.OUTLINE_VARIANT,
            button_hover_color=self._theme.colors.OUTLINE,
        )
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="x", expand=True, padx=(14, 2), pady=(0, 12))
        scroll.pack(side="right", fill="y", padx=(0, 10), pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._paint_tree_tags()

        # ── Подробности ───────────────────────────────
        details_card = MDCard(self, self._theme, tone="low")
        details_card.grid(row=2, column=0, sticky="nsew", pady=(0, SPACE_2))

        details_top = ctk.CTkFrame(details_card, fg_color="transparent")
        details_top.pack(fill="x", padx=14, pady=(12, 4))
        SectionTitle(
            details_top, self._theme, "Состояние выбранного диска",
            "Данные SMART; часть полей доступна только с правами администратора",
        ).pack(side="left")

        self.details = MDTextbox(
            details_card, self._theme, height=104, font=FONT_MONO_SMALL,
        )
        self.details.pack(fill="x", padx=14, pady=(0, 12))
        self._set_details("Нажмите «Обновить», чтобы прочитать SMART-данные.")

        # ── Проверка поверхности ──────────────────────
        scan_card = MDCard(self, self._theme, tone="low")
        scan_card.grid(row=3, column=0, sticky="nsew")

        head = ctk.CTkFrame(scan_card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 4))
        SectionTitle(
            head, self._theme, "Проверка поверхности",
            "Аналог Victoria read test: последовательное чтение без записи. "
            "Диск не изменяется.",
        ).pack(side="left")

        controls = ctk.CTkFrame(scan_card, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=(2, 6))

        MDLabel(
            controls, self._theme, "Диск", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(0, 4))
        self.disk_var = ctk.StringVar(value="—")
        self.disk_menu = MDOptionMenu(
            controls, self._theme, values=["—"], variable=self.disk_var,
            command=self._on_disk_pick, width=230, height=34,
        )
        self.disk_menu.pack(side="left", padx=(0, 10))

        MDLabel(
            controls, self._theme, "Объём", role="muted", font=FONT_LABEL,
        ).pack(side="left", padx=(0, 4))
        self.size_var = ctk.StringVar(value="1 ГБ")
        MDOptionMenu(
            controls, self._theme, values=list(SCAN_SIZES), variable=self.size_var,
            width=108, height=34,
        ).pack(side="left", padx=(0, 10))

        self.start_btn = MDButton(
            controls, self._theme, "Проверить", self._start_scan,
            kind="filled", width=112, height=34, state="disabled",
        )
        self.start_btn.pack(side="left", padx=(0, 6))

        self.cancel_btn = MDButton(
            controls, self._theme, "Стоп", self._cancel_scan,
            kind="outlined", width=72, height=34, state="disabled",
        )
        self.cancel_btn.pack(side="left")

        self.admin_label = MDLabel(
            scan_card, self._theme, "", role="warning", font=FONT_CAPTION, anchor="w",
        )
        self.admin_label.pack(fill="x", padx=14)

        self.progress = MDProgress(scan_card, self._theme, height=8)
        self.progress.pack(fill="x", padx=14, pady=(6, 4))
        self.progress.set(0)

        self.scan_status = MDLabel(
            scan_card, self._theme, "Готово к проверке.", role="secondary",
            font=FONT_LABEL, anchor="w",
        )
        self.scan_status.pack(fill="x", padx=14)

        self.scan_result = MDTextbox(
            scan_card, self._theme, height=104, font=FONT_MONO_SMALL,
        )
        self.scan_result.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        self._set_scan_result("")

'''
path.write_text(text[:start] + new_build + text[end:], encoding="utf-8")
print("patched disks build")
