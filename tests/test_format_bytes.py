"""Тесты форматирования размеров."""
from __future__ import annotations

import pytest

from disk_cleaner_app.models.item import format_bytes


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0 Б"),
        (1, "1 Б"),
        (512, "512 Б"),
        (1023, "1023 Б"),
        (1024, "1.0 КБ"),
        (1536, "1.5 КБ"),
        (1024 ** 2, "1.0 МБ"),
        (int(234.5 * 1024 ** 2), "234.5 МБ"),
        (int(1.5 * 1024 ** 3), "1.5 ГБ"),
        (int(2.25 * 1024 ** 4), "2.2 ТБ"),
    ],
)
def test_format_bytes(value: int, expected: str) -> None:
    assert format_bytes(value) == expected


def test_format_bytes_does_not_truncate_gigabytes() -> None:
    # Регрессия: раньше 1.5 ГиБ превращались в «1.0 ГБ» из-за целочисленного деления.
    assert format_bytes(int(1.5 * 1024 ** 3)) != "1.0 ГБ"


def test_format_bytes_negative_and_none() -> None:
    assert format_bytes(-1) == "0 Б"
    assert format_bytes(None) == "0 Б"
