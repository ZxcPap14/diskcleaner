"""Цель DISM (WinSxS): коды выхода, таймаут, freed только по дельте."""
from __future__ import annotations

import pytest

from disk_cleaner_app.cleaners.system import DismCleanupCleaner, store_summary
from disk_cleaner_app.models.target import LAYER_SYSTEM

MODULE = "disk_cleaner_app.cleaners.system"


def test_get_size_is_zero_win_sxs_logical_size_is_meaningless() -> None:
    # Логический размер WinSxS почти не меняется (жёсткие ссылки):
    # честное «освобождено» даёт только дельта тома.
    assert DismCleanupCleaner().get_size() == 0


def test_is_command_target_b_layer_admin() -> None:
    cleaner = DismCleanupCleaner()
    assert cleaner.affected_paths() == ()
    assert cleaner.layer == LAYER_SYSTEM
    assert cleaner.admin_required is True
    assert "/StartComponentCleanup" in cleaner.description
    assert "без /ResetBase" in cleaner.description


def test_clean_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: False)
    status, detail = DismCleanupCleaner().clean()
    assert status == "ERR"
    assert "администратора" in detail


def test_clean_ok(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run_tool(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
        calls.append(args)
        if "/AnalyzeComponentStore" in args:
            return (0, "Хранилище компонентов : 7.42 GB\n"
                       "Количество пакетов, подлежащих очистке : 3\n", "")
        return (0, "Operazione completata.", "")

    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(MODULE + ".run_tool", fake_run_tool)
    status, detail = DismCleanupCleaner().clean()

    assert status == "OK"
    # Сначала анализ «сколько вернётся», потом сама очистка.
    assert "/AnalyzeComponentStore" in calls[0]
    assert calls[1][:4] == ["dism", "/Online", "/Cleanup-Image", "/StartComponentCleanup"]
    assert timeout_disallowed(calls) is False
    assert "WinSxS" in detail
    assert "7.42 GB" in detail


def test_analyze_failure_is_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_tool(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
        if "/AnalyzeComponentStore" in args:
            return (87, "", "ошибка 0x800f081f")
        return (0, "готово", "")

    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(MODULE + ".run_tool", fake_run_tool)
    status, detail = DismCleanupCleaner().clean()

    assert status == "OK"
    assert "Было:" not in detail


def test_store_summary_keeps_report_lines() -> None:
    text = (
        "Deployment Image Servicing and Management tool\n"
        "\n"
        "Actual Size of Component Store : 7.42 GB\n"
        "Shared with Windows : 6.80 GB\n"
        "\n"
        "The operation completed successfully.\n"
    )
    summary = store_summary(text)

    assert "Actual Size of Component Store" in summary
    assert "Shared with Windows" in summary
    assert "Deployment Image" not in summary


def timeout_disallowed(calls: list[list[str]]) -> bool:
    # /ResetBase никогда не передаётся в DISM по решению плана v4.8.0.
    return any("/ResetBase" in arg for args in calls for arg in args)


def test_clean_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(
        MODULE + ".run_tool", lambda args, timeout=60: (-1, "", "TIMEOUT")
    )
    status, detail = DismCleanupCleaner().clean()

    assert status == "ERR"
    assert "15 минут" in detail


def test_clean_error_code_in_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE + ".is_admin", lambda: True)
    monkeypatch.setattr(
        MODULE + ".run_tool",
        lambda args, timeout=60: (1638, "", "Ошибка 0x800f0906"),
    )
    status, detail = DismCleanupCleaner().clean()

    assert status == "ERR"
    assert "1638" in detail
    assert "0x800f0906" in detail
