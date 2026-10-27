"""Сжатие vhdx: diskpart-скрипт, остановка WSL, подсчёт выигрыша."""
from __future__ import annotations

from pathlib import Path

from disk_cleaner_app.services import wsl_compact

MODULE = "disk_cleaner_app.services.wsl_compact"


def test_compact_vhdx_builds_diskpart_script(tmp_path: Path, monkeypatch) -> None:
    vhdx = tmp_path / "ext4.vhdx"
    vhdx.write_bytes(b"x" * 32)
    scripts: list[str] = []

    def fake_run(args: list[str], timeout: int) -> tuple[int, str, str]:
        assert args[0] == "diskpart" and args[1] == "/s"
        scripts.append(Path(args[2]).read_text(encoding="utf-8"))
        return 0, "DiskPart successfully compacted the virtual disk file.", ""

    monkeypatch.setattr(MODULE + "._run", fake_run)

    ok, message = wsl_compact.compact_vhdx(vhdx)

    assert ok is True
    assert message == "сжато"
    assert f'select vdisk file="{vhdx}"' in scripts[0]
    assert "compact vdisk" in scripts[0]


def test_compact_vhdx_missing_file(tmp_path: Path) -> None:
    ok, message = wsl_compact.compact_vhdx(tmp_path / "nope.vhdx")

    assert ok is False
    assert "не найден" in message


def test_compact_vhdx_reports_error_line(tmp_path: Path, monkeypatch) -> None:
    vhdx = tmp_path / "ext4.vhdx"
    vhdx.write_bytes(b"x")
    monkeypatch.setattr(
        MODULE + "._run",
        lambda args, timeout: (1, "DiskPart has encountered an error: отказ в доступе", ""),
    )

    ok, message = wsl_compact.compact_vhdx(vhdx)

    assert ok is False
    assert "отказ в доступе" in message


def test_compact_paths_shuts_down_and_sums_delta(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "a.vhdx"
    second = tmp_path / "b.vhdx"
    first.write_bytes(b"x" * 100)
    second.write_bytes(b"x" * 50)
    calls: list[str] = []

    def fake_shutdown(timeout: int = 60) -> bool:
        calls.append("shutdown")
        return True

    def fake_compact(path: Path, timeout: int = 900) -> tuple[bool, str]:
        path.write_bytes(b"x" * 10)
        return True, "сжато"

    monkeypatch.setattr(MODULE + ".shutdown_wsl", fake_shutdown)
    monkeypatch.setattr(MODULE + ".compact_vhdx", fake_compact)

    freed, lines = wsl_compact.compact_paths([first, second])

    assert calls == ["shutdown"]
    assert freed == 90 + 40
    assert len(lines) == 2


def test_compact_paths_empty_does_not_touch_wsl(monkeypatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        MODULE + ".shutdown_wsl", lambda timeout=60: called.append("x") or True
    )

    assert wsl_compact.compact_paths([]) == (0, [])
    assert called == []
