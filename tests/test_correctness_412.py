"""Тесты 4.12.0 «Правильность»: возраст в clean(), 8.3-имена, covered-корни."""
from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path

from disk_cleaner_app.cleaners.base import (
    newest_mtime,
    safe_rm_contents_aged,
)
from disk_cleaner_app.cleaners.discover import (
    is_covered,
    reset_covered_cache,
)
from disk_cleaner_app.cleaners.safety import _long_form, is_dangerous_target
from disk_cleaner_app.cleaners.system import UserTempCleaner


def _age(path: Path, hours: float) -> None:
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


# ── возрастной фильтр при прямом clean() ────────────────


def test_aged_contents_removes_only_old_files(tmp_path: Path) -> None:
    old = tmp_path / "old.bin"
    fresh = tmp_path / "fresh.bin"
    old.write_bytes(b"x")
    fresh.write_bytes(b"y")
    nested_old = tmp_path / "sub" / "old2.bin"
    nested_old.parent.mkdir()
    nested_old.write_bytes(b"z")
    nested_fresh = tmp_path / "sub" / "fresh2.bin"
    nested_fresh.write_bytes(b"w")

    _age(old, 48)
    _age(nested_old, 48)

    assert safe_rm_contents_aged(tmp_path, 24, to_recycle=False) is True
    assert not old.exists()
    assert not nested_old.exists()
    assert fresh.exists()
    assert nested_fresh.exists()
    # Структура папок сохраняется — чистится содержимое, а не дерево.
    assert (tmp_path / "sub").is_dir()


def test_aged_contents_recycle_batches_paths(
    monkeypatch, tmp_path: Path
) -> None:
    import disk_cleaner_app.services.batch_delete as batch_mod

    old_a = tmp_path / "a.bin"
    old_b = tmp_path / "b.bin"
    old_a.write_bytes(b"x")
    old_b.write_bytes(b"y")
    _age(old_a, 48)
    _age(old_b, 48)

    calls: list[tuple[list[str], bool]] = []

    def fake_delete_many(paths, to_recycle=True, use_ifile=True):
        calls.append((list(paths), to_recycle))
        return {"deleted": list(paths), "failed": []}

    monkeypatch.setattr(batch_mod, "delete_many", fake_delete_many)

    assert safe_rm_contents_aged(tmp_path, 24, to_recycle=True) is True
    # Пакетный вызов на все старые файлы, а не PowerShell на каждый путь.
    assert len(calls) == 1
    assert calls[0][1] is True
    assert sorted(calls[0][0]) == [str(old_a), str(old_b)]


def test_user_temp_clean_keeps_fresh_files(monkeypatch, tmp_path: Path) -> None:
    temp = tmp_path / "temp"
    temp.mkdir()
    old = temp / "old.tmp"
    fresh = temp / "fresh.tmp"
    old.write_bytes(b"x")
    fresh.write_bytes(b"y")
    _age(old, 48)

    monkeypatch.setenv("TEMP", str(temp))
    status, _ = UserTempCleaner().clean()

    assert status == "OK"
    assert not old.exists()
    assert fresh.exists()


def test_newest_mtime_returns_none_for_unreadable(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert newest_mtime(missing) is None


def test_newest_mtime_empty_dir_is_old(tmp_path: Path) -> None:
    assert newest_mtime(tmp_path) == 0.0


# ── 8.3-имена в PathGuard ───────────────────────────────


def _short_path(path: Path) -> str:
    buf = ctypes.create_unicode_buffer(1024)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
    return buf.value if length else ""


def test_long_form_ignores_paths_without_tilde(tmp_path: Path) -> None:
    assert _long_form(tmp_path / "nope") == tmp_path / "nope"


def test_8_3_form_of_protected_path_is_flagged(tmp_path: Path) -> None:
    """Короткая запись (PROGRA~1-стиль) не обходит защиту путей."""
    home = Path.home()
    home_short = _short_path(home)
    if home_short and os.path.normcase(home_short) != os.path.normcase(str(home)):
        # На томе включены 8.3-имена: короткая форма домашнего каталога
        # обязана распознаваться как защищённая.
        assert is_dangerous_target(home_short) is True

    plain = tmp_path / "plain"
    plain.mkdir()
    assert is_dangerous_target(plain) is False


# ── covered-корни auto-discover ─────────────────────────


def test_covered_roots_match_builtin_affected_paths() -> None:
    """Каждый путь встроенных целей покрыт — списки не разъезжаются."""
    reset_covered_cache()
    from disk_cleaner_app.cleaners.aiml import AIML_CLEANERS
    from disk_cleaner_app.cleaners.apps import APP_CLEANERS
    from disk_cleaner_app.cleaners.browsers import BROWSER_CLEANERS
    from disk_cleaner_app.cleaners.devtools import DEVTOOLS_CLEANERS
    from disk_cleaner_app.cleaners.system import SYSTEM_CLEANERS
    from disk_cleaner_app.cleaners.uwp import UWP_CLEANERS

    for cleaner_class in (
        *SYSTEM_CLEANERS, *UWP_CLEANERS, *APP_CLEANERS, *DEVTOOLS_CLEANERS,
        *BROWSER_CLEANERS, *AIML_CLEANERS,
    ):
        cleaner = cleaner_class()
        for path in cleaner.affected_paths():
            assert is_covered(path), f"{cleaner.id}: {path}"


def test_vendor_subcaches_are_no_longer_hidden() -> None:
    """Корень вендора не покрывает соседние кэши: NV_Cache видим для discover."""
    reset_covered_cache()
    from disk_cleaner_app.cleaners.system import GpuShaderCacheCleaner

    paths = GpuShaderCacheCleaner().affected_paths()
    nvidia = [p for p in paths if p.name in ("DXCache", "GLCache")]
    assert nvidia, "ожидались пути NVIDIA-кэшей"

    vendor_root = nvidia[0].parent
    assert is_covered(nvidia[0])
    sibling = vendor_root / "NV_Cache"
    if sibling != nvidia[0]:
        assert not is_covered(sibling), f"{sibling} не должен быть покрыт"
    reset_covered_cache()
