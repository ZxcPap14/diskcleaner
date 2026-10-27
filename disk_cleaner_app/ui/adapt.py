"""Адаптивная вёрстка: перенос текста по фактической ширине контейнера.

Фиксированный ``wraplength`` (620, 720, 820 px) вёл себя одинаково при
1024 и 1600 px: на узком окне текст уезжал за край, на широком висел
узкой колонкой. Ширина считается от родителя, но не раздувается
бесконечно — иначе строка становится нечитаемо длинной.

Один обработчик ``<Configure>`` на окно, а не по одному на подпись:
иначе на каждый шаг ресайза Tk дёргает сотни Python-колбэков.
"""
from __future__ import annotations

from typing import Any

import customtkinter as ctk

from disk_cleaner_app.ui.debounce import DebouncedEvent

MIN_WRAP = 120
MAX_GROWTH = 1.4

_labels: list[tuple[Any, int, int]] = []
_hooks: dict[int, DebouncedEvent] = {}


def _apply_all() -> None:
    alive: list[tuple[Any, int, int]] = []
    for label, pad, limit in _labels:
        try:
            width = label.master.winfo_width()
            current = int(float(label.cget("wraplength")))
        except Exception:
            continue  # виджет уничтожен — выбрасываем из реестра
        if width >= MIN_WRAP + pad:
            target = max(MIN_WRAP, min(width - pad, limit))
            if current != target:
                try:
                    label.configure(wraplength=target)
                except Exception:
                    continue
        alive.append((label, pad, limit))
    _labels[:] = alive


def adapt_wrap(label: Any, pad: int = 24) -> None:
    """Держать ``wraplength`` подписи в пределах ширины родителя."""
    try:
        base = int(float(label.cget("wraplength")))
    except Exception:
        return
    if base <= 0:
        return
    _labels.append((label, pad, int(base * MAX_GROWTH)))
    root = label.winfo_toplevel()
    if id(root) not in _hooks:
        hook = DebouncedEvent(root, _apply_all)
        _hooks[id(root)] = hook
        root.bind("<Configure>", hook, add="+")


def adapt_tree(widget: Any) -> int:
    """Включить адаптивный перенос у всех подписей с ``wraplength``."""
    count = _scan(widget)
    _apply_all()
    return count


def _scan(widget: Any) -> int:
    count = 0
    try:
        children = widget.winfo_children()
    except Exception:
        return 0
    for child in children:
        if isinstance(child, ctk.CTkLabel):
            try:
                if int(float(child.cget("wraplength"))) > 0:
                    adapt_wrap(child)
                    count += 1
            except Exception:
                pass
        count += _scan(child)
    return count
