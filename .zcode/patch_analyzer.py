from pathlib import Path

path = Path(r"D:\projects\disk_cleen\disk_cleaner_app\ui\views\analyzer.py")
text = path.read_text(encoding="utf-8")
start = text.index("    def _build(self) -> None:\n")
end = text.index("    # ── Analysis modes ──────────────────────────────\n")

new_build = '''    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Анализ диска",
            "Крупные папки, файлы, пустые каталоги и treemap",
            icon="▤",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        self.refresh_btn = MDButton(
            header.actions, self._theme, "Обновить", self._refresh_analysis,
            kind="text_muted", width=94, height=34,
        )
        self.refresh_btn.pack(side="right", padx=(4, 0))

        self.cancel_btn = MDButton(
            header.actions, self._theme, "Стоп", self._cancel_analysis,
            kind="outlined", width=78, height=34, state="disabled",
        )
        self.cancel_btn.pack(side="right", padx=(4, 0))

        self.back_btn = MDButton(
            header.actions, self._theme, "Назад", self._treemap_back,
            kind="outlined", width=86, height=34, state="disabled",
        )
        self.back_btn.pack(side="right", padx=(4, 0))

        self.treemap_btn = MDButton(
            header.actions, self._theme,
            f"Treemap · {self._drive_root()}", self._show_treemap_root,
            kind="filled", width=170, height=34,
        )
        self.treemap_btn.pack(side="right")

        # ── Инструменты анализа ───────────────────────
        tools = MDCard(self, self._theme, tone="low")
        tools.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        row = ctk.CTkFrame(tools, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(11, 5))

        MDLabel(
            row, self._theme, "Быстрый отчёт", role="muted",
            font=FONT_CAPTION,
        ).pack(side="left", padx=(0, 8))

        for text, cmd, kind, width in [
            ("Топ папок", "top", "tonal", 100),
            ("Файлы > 500 МБ", "big500", "outlined", 124),
            ("Файлы > 1 ГБ", "big1024", "outlined", 118),
            ("Пустые папки", "empty", "outlined", 118),
            ("Автозагрузка", "startup", "text", 106),
        ]:
            MDButton(
                row, self._theme, text, lambda m=cmd: self._run_analysis(m),
                kind=kind, width=width, height=32,
            ).pack(side="left", padx=(0, 6))

        self.remove_empty_btn = MDButton(
            row, self._theme, "Удалить пустые", self._remove_empty,
            kind="danger_text", width=126, height=32, state="disabled",
        )
        self.remove_empty_btn.pack(side="right")

        self.breadcrumb = MDLabel(
            tools, self._theme, "", role="muted", font=FONT_LABEL, anchor="w",
        )
        self.breadcrumb.pack(fill="x", padx=14, pady=(0, 10))
        self._update_breadcrumb(f"Диск: {self._drive_root()}")

        # ── Результаты ────────────────────────────────
        results = MDCard(self, self._theme, tone="low")
        results.grid(row=2, column=0, sticky="nsew")
        self._results_card = results

        self.pane = ctk.CTkFrame(results, fg_color="transparent")
        self.pane.pack(fill="both", expand=True, padx=12, pady=12)

        self.text_result = MDTextbox(
            self.pane, self._theme, font=FONT_MONO,
            fg_color=self._theme.colors.SURFACE_LOWEST,
        )
        self.text_result.pack(fill="both", expand=True)
        self.text_result.bind("<Button-3>", self._show_context_menu)

        self.treemap_canvas = TreemapCanvas(
            self.pane,
            on_open_folder=self._on_treemap_drill,
            on_breadcrumb=lambda t: self._update_breadcrumb(t),
            theme=self._theme,
            bg=self._theme.colors.SURFACE_LOWEST,
        )

'''
path.write_text(text[:start] + new_build + text[end:], encoding="utf-8")
print("patched analyzer build")
