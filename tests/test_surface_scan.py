"""Тесты вспомогательных функций проверки поверхности."""
from __future__ import annotations

from disk_cleaner_app.services.surface_scan import (
    ALIGNMENT,
    _aligned,
    disk_path,
    format_duration,
    format_speed,
    plan_size,
)


def test_disk_path() -> None:
    assert disk_path(0) == "\\\\.\\PhysicalDrive0"
    assert disk_path("2") == "\\\\.\\PhysicalDrive2"


def test_plan_size_limits() -> None:
    assert plan_size(1000, None) == 1000
    assert plan_size(1000, 400) == 400
    assert plan_size(1000, 5000) == 1000
    assert plan_size(0, None) == 0


def test_sector_alignment() -> None:
    assert _aligned(0) == 0
    assert _aligned(ALIGNMENT) == ALIGNMENT
    assert _aligned(ALIGNMENT + 1) == ALIGNMENT
    assert _aligned(4097) == 4096


def test_format_speed() -> None:
    assert format_speed(0) == "0 Б/с"
    assert format_speed(1024) == "1 КБ/с"
    assert format_speed(1024 ** 2 * 1.5) == "1.5 МБ/с"
    assert format_speed(1024 ** 3 * 2) == "2.00 ГБ/с"


def test_format_duration() -> None:
    assert format_duration(0) == "0 с"
    assert format_duration(65) == "1 мин 05 с"
    assert format_duration(3661) == "1 ч 01 мин"
