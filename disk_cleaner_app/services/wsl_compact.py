"""Сжатие виртуальных дисков WSL2/Docker без удаления данных.

vhdx растёт, но сам не уменьшается: после удаления файлов внутри
дистрибутива место на хосте остаётся занятым. Штатный способ вернуть его —
остановить WSL и сжать образ через ``diskpart compact vdisk``.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

# Своё окно консоли diskpart пользователю не нужно.
CREATE_NO_WINDOW = 0x08000000


def _run(args: list[str], timeout: int) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, errors="replace",
            timeout=timeout, creationflags=CREATE_NO_WINDOW,
        )
        return (
            result.returncode,
            (result.stdout or "").strip(),
            (result.stderr or "").strip(),
        )
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except OSError as e:
        return -2, "", str(e)


def vhdx_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def shutdown_wsl(timeout: int = 60) -> bool:
    """Остановить WSL: без этого vhdx занят и сжатие невозможно."""
    rc, _out, _err = _run(["wsl.exe", "--shutdown"], timeout)
    return rc == 0


def _error_line(out: str, err: str) -> str:
    for line in (out + "\n" + err).splitlines():
        low = line.lower()
        if line.strip() and ("error" in low or "ошиб" in low or "0x" in low):
            return line.strip()
    return ""


def compact_vhdx(path: Path, timeout: int = 900) -> tuple[bool, str]:
    """Сжать один vhdx. Возвращает (успех, пояснение).

    diskpart, а не Optimize-VHD: модуль Hyper-V есть только в Pro/Enterprise.
    """
    if not path.is_file():
        return False, "файл не найден"

    script = f'select vdisk file="{path}"\ncompact vdisk\n'
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    )
    try:
        handle.write(script)
        handle.close()
        rc, out, err = _run(["diskpart", "/s", handle.name], timeout)
    finally:
        try:
            Path(handle.name).unlink(missing_ok=True)
        except OSError:
            pass

    if rc == -1:
        return False, "diskpart не завершился за отведённое время"
    if rc != 0:
        return False, _error_line(out, err) or f"diskpart завершился с кодом {rc}"
    return True, "сжато"


def compact_paths(paths: list[Path]) -> tuple[int, list[str]]:
    """Остановить WSL и сжать перечисленные образы.

    Возвращает (освобождено байт, строки отчёта по каждому файлу).
    """
    if not paths:
        return 0, []
    shutdown_wsl()
    freed = 0
    lines: list[str] = []
    for path in paths:
        before = vhdx_size(path)
        ok, message = compact_vhdx(path)
        after = vhdx_size(path)
        if ok:
            freed += max(0, before - after)
            lines.append(f"{path.name}: {before} → {after} байт")
        else:
            lines.append(f"{path.name}: не сжато ({message})")
    return freed, lines
