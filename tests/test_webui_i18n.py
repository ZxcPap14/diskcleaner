"""Локализация интерфейса: каждый русский текст разметки есть в словаре."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

WEBUI = Path(__file__).resolve().parent.parent / "disk_cleaner_app" / "webui"
SKIP_TAGS = {"script", "style"}
ATTRS = ("placeholder", "title", "aria-label")


class _Texts(HTMLParser):
    """Собирает тексты элементов и подписей-атрибутов."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.texts: set[str] = set()
        self._skip = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
        for name, value in attrs:
            if name in ATTRS and value and value.strip():
                self.texts.add(value.strip())

    def handle_endtag(self, tag) -> None:
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data) -> None:
        text = data.strip()
        if self._skip or not text:
            return
        # «Освобождено 1,2 ГБ» — статика со значением, её переводит tf/подстановка.
        self.texts.add(text)


def html_texts() -> set[str]:
    parser = _Texts()
    parser.feed((WEBUI / "index.html").read_text(encoding="utf-8"))
    return parser.texts


def ui_en() -> dict[str, str]:
    text = (WEBUI / "i18n.js").read_text(encoding="utf-8")
    block = text.split("const UI_EN = {", 1)[1].split("\n};", 1)[0]
    pairs = re.findall(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', block)
    return {_unescape(key): _unescape(value) for key, value in pairs}


def _unescape(raw: str) -> str:
    """В файле строки с кавычками и обратными слэшами записаны как в JS."""
    return raw.replace('\\"', '"').replace("\\\\", "\\")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _bare(text: str) -> str:
    """Подпись без ведущей иконки: «✕ без прав» → «без прав»."""
    return re.sub(r"^[\W_]+", "", text)


def test_every_static_text_is_translated() -> None:
    keys = {_norm(key) for key in ui_en()}
    keys |= {_bare(key) for key in keys}
    # Числа, проценты и латиница перевода не требуют.
    cyrillic = re.compile(r"[\u0400-\u04FF]")
    missing = sorted(
        text for text in html_texts()
        if cyrillic.search(text) and _norm(text) not in keys and _bare(_norm(text)) not in keys
    )

    assert not missing, "нет перевода: " + "; ".join(missing[:10])


def test_translations_are_not_empty() -> None:
    empty = [key for key, value in ui_en().items() if not value.strip()]

    assert not empty


def test_html_loads_i18n_before_app() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")

    assert html.index("i18n.js") < html.index("app.js")
