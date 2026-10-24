"""Честный учёт очистки: дельта по каждому тому, корзина, частичный отказ."""
from __future__ import annotations

import os
from pathlib import Path

from helpers import PathCleaner

from disk_cleaner_app.cleaners.base import CleanOptions
from disk_cleaner_app.services import cleaner as cleaner_module
from disk_cleaner_app.services.cleaner import CleanEngine
from disk_cleaner_app.services.planner import volume_root


def _write(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


class _DeleteSpy:
    """Подмена delete_many: имитирует удаление без COM-оболочки."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.recycle_flags: list[bool] = []
        self.fail = fail or set()

    def __call__(self, paths, to_recycle: bool = False, use_ifile: bool = True):
        self.calls.append(list(paths))
        self.recycle_flags.append(bool(to_recycle))
        deleted: list[str] = []
        failed: list[str] = []
        for raw in paths:
            key = str(Path(raw))
            if key in self.fail:
                failed.append(raw)
                continue
            try:
                Path(raw).unlink()
            except OSError:
                failed.append(raw)
                continue
            deleted.append(raw)
        return {
            "deleted": deleted,
            "failed": failed,
            "aborted": False,
            "error": 0,
            "fallback": False,
        }


def _free_sequence(monkeypatch, volume: str, values: list[int]) -> None:
    iterator = iter(values)

    def fake_free(root: str | None = None) -> tuple[int, int]:
        assert root == volume
        return next(iterator), 0

    monkeypatch.setattr(cleaner_module, "get_disk_free", fake_free)


def test_freed_is_delta_on_the_affected_volume(tmp_path: Path, monkeypatch) -> None:
    file = _write(tmp_path / "cache" / "a.bin", 4_000)
    volume = volume_root(file)
    _free_sequence(monkeypatch, volume, [10_000, 14_000])
    monkeypatch.setattr(cleaner_module, "delete_many", _DeleteSpy())

    cleaner = PathCleaner([file])
    result = CleanEngine().clean_selected([cleaner])[0]

    assert result.status == "OK"
    assert result.planned == 4_000
    assert result.removed == 4_000
    assert result.volume_delta == 4_000
    assert result.volume_deltas == {volume: 4_000}
    assert result.freed == 4_000
    assert result.volumes == (volume,)
    assert result.confidence == "high"
    assert result.remaining == 0
    assert cleaner.size == 0


def test_recycled_bytes_are_not_counted_as_freed(tmp_path: Path, monkeypatch) -> None:
    file = _write(tmp_path / "docs" / "a.txt", 1_000)
    volume = volume_root(file)
    _free_sequence(monkeypatch, volume, [5_000, 5_000])
    monkeypatch.setattr(cleaner_module, "delete_many", _DeleteSpy())

    cleaner = PathCleaner([file])
    result = CleanEngine().clean_selected(
        [cleaner], options=CleanOptions(to_recycle=True)
    )[0]

    assert result.status == "OK"
    assert result.removed == 1_000
    assert result.freed == 0
    assert result.recycled is True
    assert "корзин" in result.note


def test_zero_free_space_delta_is_marked_as_estimate(tmp_path: Path, monkeypatch) -> None:
    file = _write(tmp_path / "cache" / "a.bin", 2_000)
    volume = volume_root(file)
    _free_sequence(monkeypatch, volume, [8_000, 8_000])
    monkeypatch.setattr(cleaner_module, "delete_many", _DeleteSpy())

    cleaner = PathCleaner([file])
    result = CleanEngine().clean_selected([cleaner])[0]

    assert result.status == "OK"
    assert result.removed == 2_000
    assert result.volume_delta == 0
    assert result.confidence == "estimate"
    assert result.freed == 0


def test_partial_failure_keeps_success_and_reports_rest(tmp_path: Path, monkeypatch) -> None:
    first = _write(tmp_path / "cache" / "a.bin", 1_000)
    second = _write(tmp_path / "cache" / "b.bin", 3_000)
    volume = volume_root(first)
    _free_sequence(monkeypatch, volume, [0, 1_000])
    monkeypatch.setattr(
        cleaner_module, "delete_many", _DeleteSpy(fail={str(second)})
    )

    cleaner = PathCleaner([first, second])
    result = CleanEngine().clean_selected([cleaner])[0]

    assert result.status == "OK"
    assert result.removed == 1_000
    assert result.errors == [str(second)]
    assert result.remaining == 3_000
    assert "частично" in result.note


def test_delete_is_chunked(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    for index in range(5):
        _write(cache / f"{index}.bin", 1)
    volume = volume_root(cache)
    _free_sequence(monkeypatch, volume, [0, 5])
    spy = _DeleteSpy()
    monkeypatch.setattr(cleaner_module, "delete_many", spy)
    monkeypatch.setattr(cleaner_module, "DELETE_CHUNK", 2)

    cleaner = PathCleaner([cache])
    CleanEngine().clean_selected([cleaner])

    assert [len(call) for call in spy.calls] == [2, 2, 1]


def test_admin_target_is_skipped_without_rights(tmp_path: Path, monkeypatch) -> None:
    from disk_cleaner_app.services import planner as planner_module

    file = _write(tmp_path / "cache" / "a.bin", 10)
    monkeypatch.setattr(planner_module.elevation, "is_admin", lambda: False)
    called = _DeleteSpy()
    monkeypatch.setattr(cleaner_module, "delete_many", called)

    cleaner = PathCleaner([file.parent], admin_required=True)
    result = CleanEngine().clean_selected([cleaner])[0]

    assert result.status == "SKIP"
    assert "права администратора" in result.note
    assert result.freed == 0
    assert called.calls == []
    assert file.exists()


def test_empty_path_target_is_skipped(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "absent"
    called = _DeleteSpy()
    monkeypatch.setattr(cleaner_module, "delete_many", called)

    result = CleanEngine().clean_selected([PathCleaner([missing])])[0]

    assert result.status == "SKIP"
    assert result.planned == 0
    assert called.calls == []


def test_command_target_calls_clean(monkeypatch) -> None:
    from helpers import FakeCleaner

    sequence = iter([0, 500])
    monkeypatch.setattr(
        cleaner_module, "get_disk_free", lambda root=None: (next(sequence), 0)
    )
    cleaner = FakeCleaner(size=500, on_clean=lambda c: None)

    result = CleanEngine().clean_selected([cleaner])[0]

    assert result.status == "OK"
    assert result.freed == 500
    assert result.volumes == (
        (os.environ.get("SystemDrive", "C:") + "\\").upper(),
    )
