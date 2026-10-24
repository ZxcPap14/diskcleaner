"""Тесты честного результата очистки."""
from __future__ import annotations

import pytest
from helpers import FakeCleaner

from disk_cleaner_app.cleaners.base import CleanOptions
from disk_cleaner_app.services import cleaner as cleaner_module
from disk_cleaner_app.services.cleaner import CleanEngine


def _patch_free(monkeypatch, values: list[int]) -> None:
    """Подменить свободное место на диске последовательностью значений."""
    iterator = iter(values)
    monkeypatch.setattr(cleaner_module, "get_disk_free", lambda: (next(iterator), 0))


def test_successful_clean_uses_real_free_space_delta(monkeypatch) -> None:
    _patch_free(monkeypatch, [10_000, 12_000])
    cleaner = FakeCleaner(size=1_000, on_clean=lambda c: None)
    results = CleanEngine().clean_selected([cleaner])

    assert len(results) == 1
    result = results[0]
    assert result.status == "OK"
    assert result.planned == 1_000
    assert result.freed == 2_000
    assert result.remaining == 0
    assert cleaner.size == 0


def test_no_actual_deletion_is_reported_as_error(monkeypatch) -> None:
    _patch_free(monkeypatch, [100_000, 100_000])
    cleaner = FakeCleaner(size=2 * 1024 * 1024)
    results = CleanEngine().clean_selected([cleaner])

    result = results[0]
    assert result.status == "ERR"
    assert result.freed == 0
    assert result.remaining == 2 * 1024 * 1024
    assert "права администратора" in result.note


def test_exception_inside_cleaner_does_not_break_batch(monkeypatch) -> None:
    _patch_free(monkeypatch, [0, 0, 0, 0])

    class Broken(FakeCleaner):
        def clean(self):
            raise RuntimeError("boom")

    good = FakeCleaner(cleaner_id="good", size=10, on_clean=lambda c: None)
    results = CleanEngine().clean_selected([Broken(cleaner_id="bad"), good])

    assert [r.status for r in results] == ["ERR", "OK"]
    assert results[0].freed == 0


def test_recycled_files_are_not_reported_as_free_space(monkeypatch) -> None:
    _patch_free(monkeypatch, [50_000, 50_000])
    cleaner = FakeCleaner(size=1_000, on_clean=lambda c: None)
    results = CleanEngine().clean_selected(
        [cleaner], options=CleanOptions(to_recycle=True)
    )

    result = results[0]
    assert result.status == "OK"
    assert result.freed == 0
    assert result.recycled is True
    assert "корзин" in result.note


def test_zero_size_action_is_not_an_error(monkeypatch) -> None:
    _patch_free(monkeypatch, [0, 0])
    cleaner = FakeCleaner(size=0, on_clean=lambda c: None)
    results = CleanEngine().clean_selected([cleaner])

    result = results[0]
    assert result.status == "OK"
    assert result.freed == 0
    assert result.note == ""


def test_progress_callback_receives_every_result(monkeypatch) -> None:
    _patch_free(monkeypatch, [0, 0, 0, 0])
    seen: list[str] = []
    cleaners = [FakeCleaner(cleaner_id=f"c{i}", size=1) for i in range(2)]

    CleanEngine().clean_selected(
        cleaners, progress_callback=lambda done, total, result: seen.append(result.cleaner.id)
    )

    assert seen == ["c0", "c1"]


@pytest.mark.parametrize("status", ["OK", "ERR"])
def test_result_keeps_cleaner_reference(monkeypatch, status: str) -> None:
    _patch_free(monkeypatch, [0, 0])
    cleaner = FakeCleaner(size=0, reply=(status, "detail"))
    result = CleanEngine().clean_selected([cleaner])[0]
    assert result.cleaner is cleaner
    assert result.detail == "detail"
