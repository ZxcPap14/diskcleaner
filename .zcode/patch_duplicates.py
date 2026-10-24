from pathlib import Path

path = Path(r"D:\projects\disk_cleen\disk_cleaner_app\ui\views\duplicates.py")
text = path.read_text(encoding="utf-8")
start = text.index("    def _build(self) -> None:\n")
end = text.index("    def _browse(self) -> None:\n")

new_build = '''    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(
            self, self._theme,
            "Дубликаты",
            "Найдите одинаковые файлы и освободите место без риска",
            icon="⧉",
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_3))

        # ── Параметры поиска ──────────────────────────
        search_card = MDCard(self, self._theme, tone="low")
        search_card.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_2))

        path_row = ctk.CTkFrame(search_card, fg_color="transparent")
        path_row.pack(fill="x", padx=14, pady=(12, 6))

        MDLabel(
            path_row, self._theme, "Папка поиска", role="muted",
            font=FONT_LABEL,
        ).pack(side="left", padx=(2, 8))

        self.dup_path = ctk.StringVar(value=str(Path.home()))
        MDEntry(
            path_row, self._theme, textvariable=self.dup_path,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        MDIconButton(
            path_row, self._theme, "…", self._browse, kind="tonal", size=36,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        actions = ctk.CTkFrame(search_card, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(0, 12))

        self.fast_btn = MDButton(
            actions, self._theme, "Быстрый поиск", self._start_fast,
            kind="filled", width=136,
        )
        self.fast_btn.pack(side="left", padx=(0, 6))

        self.exact_btn = MDButton(
            actions, self._theme, "Точный · BLAKE2b", self._start_exact,
            kind="tonal", width=164,
        )
        self.exact_btn.pack(side="left", padx=(0, 6))

        self.cancel_btn = MDButton(
            actions, self._theme, "Стоп", self._cancel_search,
            kind="outlined", width=74, state="disabled",
        )
        self.cancel_btn.pack(side="left")

        self.delete_btn = MDButton(
            actions, self._theme, "В корзину", self._delete_duplicates,
            kind="danger_tonal", width=112, state="disabled",
        )
        self.delete_btn.pack(side="right")

        self.dup_status = MDLabel(
            actions, self._theme, "Готово к поиску", role="secondary",
            font=FONT_LABEL,
        )
        self.dup_status.pack(side="right", padx=(0, 12))

        # ── Результаты ────────────────────────────────
        results = MDCard(self, self._theme, tone="low")
        results.grid(row=2, column=0, sticky="nsew")

        title_row = ctk.CTkFrame(results, fg_color="transparent")
        title_row.pack(fill="x", padx=14, pady=(12, 6))
        SectionTitle(
            title_row, self._theme, "Результаты",
            "В каждой паре удаляется только второй файл",
        ).pack(side="left")

        self.dup_text = MDTextbox(results, self._theme, font=FONT_MONO)
        self.dup_text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

'''
path.write_text(text[:start] + new_build + text[end:], encoding="utf-8")
print("patched duplicates build")
