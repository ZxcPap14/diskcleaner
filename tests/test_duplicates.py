"""Тесты удаления дубликатов."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace

from disk_cleaner_app.services import duplicates as duplicates_module
from disk_cleaner_app.services.duplicates import (
    DuplicateFinder,
    arrange_groups,
    choose_original,
    is_junk_path,
)


def _pair(original: Path, duplicate: Path) -> dict:
    return {
        "name": original.name,
        "size": original.stat().st_size,
        "file1": str(original),
        "file2": str(duplicate),
    }


def test_delete_removes_only_second_file(tmp_path: Path) -> None:
    original = tmp_path / "a.bin"
    duplicate = tmp_path / "b.bin"
    original.write_bytes(b"x" * 200)
    duplicate.write_bytes(b"x" * 200)

    result = DuplicateFinder().delete_duplicates(
        [_pair(original, duplicate)], to_recycle=False
    )

    assert result["deleted"] == 1
    assert result["failed"] == 0
    assert result["freed"] == 200
    assert original.exists()
    assert not duplicate.exists()


def test_repeated_target_is_deleted_once(tmp_path: Path) -> None:
    original = tmp_path / "a.bin"
    duplicate = tmp_path / "b.bin"
    original.write_bytes(b"x" * 10)
    duplicate.write_bytes(b"x" * 10)
    pair = _pair(original, duplicate)

    result = DuplicateFinder().delete_duplicates([pair, pair], to_recycle=False)

    assert result["deleted"] == 1
    assert result["freed"] == 10


def test_missing_duplicate_is_reported(tmp_path: Path) -> None:
    original = tmp_path / "a.bin"
    original.write_bytes(b"x")
    pair = {
        "file1": str(original),
        "file2": str(tmp_path / "missing.bin"),
    }

    result = DuplicateFinder().delete_duplicates([pair], to_recycle=False)

    assert result["deleted"] == 0
    assert result["failed"] == 1
    assert "не найден" in result["errors"][0]


def test_missing_original_blocks_deletion(tmp_path: Path) -> None:
    duplicate = tmp_path / "b.bin"
    duplicate.write_bytes(b"x")
    pair = {
        "file1": str(tmp_path / "missing.bin"),
        "file2": str(duplicate),
    }

    result = DuplicateFinder().delete_duplicates([pair], to_recycle=False)

    assert result["deleted"] == 0
    assert result["failed"] == 1
    assert duplicate.exists()


def test_same_path_is_not_deleted(tmp_path: Path) -> None:
    original = tmp_path / "a.bin"
    original.write_bytes(b"x")
    pair = {"file1": str(original), "file2": str(original)}

    result = DuplicateFinder().delete_duplicates([pair], to_recycle=False)

    assert result["deleted"] == 0
    assert result["failed"] == 1
    assert original.exists()


def test_recycle_flag_is_passed(tmp_path: Path, monkeypatch) -> None:
    original = tmp_path / "a.bin"
    duplicate = tmp_path / "b.bin"
    original.write_bytes(b"x")
    duplicate.write_bytes(b"x")
    calls: list[bool] = []

    def fake_batch(paths, to_recycle=True):
        calls.append(bool(to_recycle))
        for path in paths:
            Path(path).unlink()
        return {
            "deleted": list(paths),
            "failed": [],
            "aborted": False,
            "error": 0,
            "fallback": False,
        }

    monkeypatch.setattr(duplicates_module, "delete_many", fake_batch)

    result = DuplicateFinder().delete_duplicates(
        [_pair(original, duplicate)], to_recycle=True
    )

    assert result["deleted"] == 1
    assert calls == [True]


def test_permanent_delete_uses_safe_remove(tmp_path: Path, monkeypatch) -> None:
    original = tmp_path / "a.bin"
    duplicate = tmp_path / "b.bin"
    original.write_bytes(b"x")
    duplicate.write_bytes(b"x")
    calls: list[bool] = []

    def fake_remove(path, to_recycle=None):
        calls.append(bool(to_recycle))
        path.unlink()
        return True

    monkeypatch.setattr(duplicates_module, "safe_remove", fake_remove)

    result = DuplicateFinder().delete_duplicates(
        [_pair(original, duplicate)], to_recycle=False
    )

    assert result["deleted"] == 1
    assert calls == [False]


def test_find_fast_groups_same_name_and_size(tmp_path: Path) -> None:
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    (tmp_path / "one" / "same.bin").write_bytes(b"x" * 200)
    (tmp_path / "two" / "same.bin").write_bytes(b"x" * 200)

    results = DuplicateFinder().find_fast(str(tmp_path), min_size_kb=0)

    assert len(results) == 1
    assert results[0]["count"] == 2


def test_find_exact_matches_identical_content(tmp_path: Path) -> None:
    (tmp_path / "copy1.bin").write_bytes(b"same" * 100)
    (tmp_path / "copy2.bin").write_bytes(b"same" * 100)
    (tmp_path / "other.bin").write_bytes(b"diff" * 100)

    results = DuplicateFinder().find_exact(str(tmp_path), min_size_kb=0)

    assert len(results) == 1
    pair = results[0]
    assert pair["size"] == 400
    assert {pair["file1"], pair["file2"]} == {
        str(tmp_path / "copy1.bin"),
        str(tmp_path / "copy2.bin"),
    }


def test_find_exact_ignores_same_prefix_with_different_tail(tmp_path: Path) -> None:
    prefix = b"p" * 128
    (tmp_path / "a.bin").write_bytes(prefix + b"one")
    (tmp_path / "b.bin").write_bytes(prefix + b"two")

    results = DuplicateFinder().find_exact(str(tmp_path), min_size_kb=0)

    assert results == []


def test_find_exact_honours_cancel(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 200)
    (tmp_path / "b.bin").write_bytes(b"x" * 200)
    cancel = threading.Event()
    cancel.set()

    results = DuplicateFinder().find_exact(str(tmp_path), min_size_kb=0, cancel=cancel)

    assert results == []


def test_find_exact_reports_progress(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 200)
    (tmp_path / "b.bin").write_bytes(b"x" * 200)
    calls: list[tuple[int, int, str]] = []

    DuplicateFinder().find_exact(
        str(tmp_path), min_size_kb=0,
        progress=lambda done, total, label: calls.append((done, total, label)),
    )

    assert calls
    assert any("BLAKE2b" in label for _, _, label in calls)


def test_disappearing_file_does_not_abort_exact_search(tmp_path: Path) -> None:
    """Регрессия: getsize вне try — файл, удалённый между хэшем и
    получением размера, ронял весь точный поиск."""
    finder = DuplicateFinder()
    original = tmp_path / "a.bin"
    victim = tmp_path / "victim.bin"
    payload = b"x" * (200 * 1024)
    original.write_bytes(payload)
    victim.write_bytes(payload)

    real_hash = DuplicateFinder._hash_file

    def hash_then_delete(fp: str, limit: int | None = None) -> str:
        digest = real_hash(fp, limit)
        if limit is None and fp.endswith("victim.bin"):
            os.remove(fp)
        return digest

    finder._hash_file = hash_then_delete  # type: ignore[method-assign]

    results = finder.find_exact(str(tmp_path), min_size_kb=100)

    assert results == []
    assert original.exists()


def test_find_exact_groups_returns_whole_group(tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.bin").write_bytes(b"same" * 100)
    (tmp_path / "d.bin").write_bytes(b"other" * 100)

    groups = DuplicateFinder().find_exact_groups(str(tmp_path), min_size_kb=0)

    assert len(groups) == 1
    group = groups[0]
    assert group["count"] == 3
    assert len(group["files"]) == 3
    assert group["size"] == 400
    assert group["wasted"] == 800
    assert group["name"].endswith("a.bin") or "a.bin" in group["name"]


def test_groups_are_sorted_by_wasted(tmp_path: Path) -> None:
    for name in ("s1", "s2"):
        (tmp_path / f"{name}.bin").write_bytes(b"x" * 100)
    for name in ("b1", "b2"):
        (tmp_path / f"{name}.bin").write_bytes(b"y" * 1000)

    groups = DuplicateFinder().find_exact_groups(str(tmp_path), min_size_kb=0)

    assert [g["size"] for g in groups] == [1000, 100]


def test_pairs_from_groups_match_legacy_format(tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.bin").write_bytes(b"same" * 100)

    finder = DuplicateFinder()
    groups = finder.find_exact_groups(str(tmp_path), min_size_kb=0)
    pairs = finder._pairs(groups)

    assert len(pairs) == 2
    assert all(p["file1"] == groups[0]["files"][0] for p in pairs)
    assert {p["file2"] for p in pairs} == set(groups[0]["files"][1:])


# ── авто-выбор оригинала ─────────────────────────────────


def _stat_map(mtimes: dict[str, float]):
    def fake(path: str) -> SimpleNamespace:
        if path not in mtimes:
            raise FileNotFoundError(path)
        return SimpleNamespace(st_mtime=mtimes[path])

    return fake


def _group(files: list[str], size: int = 100) -> dict:
    return {
        "name": "same.bin",
        "size": size,
        "files": list(files),
        "count": len(files),
        "wasted": size * (len(files) - 1),
    }


def test_is_junk_path_detects_temp_and_downloads() -> None:
    assert is_junk_path(r"C:\Users\me\AppData\Local\Temp\a.bin")
    assert is_junk_path(r"D:\Downloads\a.bin")
    assert not is_junk_path(r"D:\Photos\a.bin")


def test_choose_original_oldest_prefers_non_junk() -> None:
    files = [
        r"C:\Users\me\Downloads\a.bin",
        r"C:\Users\me\Docs\a.bin",
        r"C:\Users\me\Photos\a.bin",
    ]
    stat = _stat_map({
        files[0]: 100.0,
        files[1]: 200.0,
        files[2]: 300.0,
    })

    assert choose_original(files, "oldest", stat_fn=stat) == files[1]


def test_choose_original_newest_and_short_path() -> None:
    files = [r"C:\a\long\path\a.bin", r"C:\b\a.bin"]
    stat = _stat_map({files[0]: 100.0, files[1]: 200.0})

    assert choose_original(files, "newest", stat_fn=stat) == files[1]
    assert choose_original(files, "short_path", stat_fn=stat) == files[1]


def test_choose_original_never_prefers_unknown_mtime() -> None:
    files = [r"C:\unknown\a.bin", r"C:\known\a.bin"]
    stat = _stat_map({files[1]: 200.0})

    assert choose_original(files, "oldest", stat_fn=stat) == files[1]


def test_arrange_groups_protects_whitelist(tmp_path: Path) -> None:
    keep_dir = tmp_path / "keep"
    keep_dir.mkdir()
    old = tmp_path / "old.bin"
    kept = keep_dir / "kept.bin"
    extra = tmp_path / "extra.bin"
    for path in (old, kept, extra):
        path.write_bytes(b"x")
    stat = _stat_map({
        str(old): 100.0,
        str(kept): 200.0,
        str(extra): 300.0,
    })

    [group] = arrange_groups(
        [_group([str(extra), str(kept), str(old)])],
        whitelist=[str(keep_dir)],
        stat_fn=stat,
    )

    assert group["original"] == str(old)
    assert group["protected"] == [str(kept)]
    assert group["deletable"] == [str(extra)]
    assert group["wasted"] == 100


def test_arrange_groups_keeps_group_when_all_protected(tmp_path: Path) -> None:
    first = tmp_path / "a.bin"
    second = tmp_path / "b.bin"
    for path in (first, second):
        path.write_bytes(b"x")

    [group] = arrange_groups(
        [_group([str(first), str(second)])],
        whitelist=[str(tmp_path)],
        stat_fn=_stat_map({str(first): 100.0, str(second): 200.0}),
    )

    assert group["deletable"] == []
    assert group["wasted"] == 0
    assert len(group["protected"]) == 1
