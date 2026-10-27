"""Слой D: пустые папки и битые ярлыки — в корзину, откуда всё возвращается."""
from __future__ import annotations

import os
import time
from pathlib import Path

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    get_path_size,
    run_powershell,
)
from disk_cleaner_app.models.item import GROUP_SYSTEM, SafetyLevel
from disk_cleaner_app.models.target import LAYER_LEFTOVERS

USER = Path.home()
PROGRAMDATA = Path(os.environ.get("ProgramData", r"C:\ProgramData"))

# Только личные папки: OneDrive и облачные плейсхолдеры не трогаем.
PERSONAL_DIRS = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")

SHORTCUT_DIRS = (
    USER / "Desktop",
    USER / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu",
    PROGRAMDATA / "Microsoft" / "Windows" / "Start Menu",
)

MAX_DEPTH = 6


def empty_folders(roots: tuple[Path, ...], max_age_hours: int) -> list[Path]:
    """Пустые папки старше срока (корни сканирования не возвращаются)."""
    cutoff = time.time() - max_age_hours * 3600
    found: list[Path] = []
    for root in roots:
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            path = Path(dirpath)
            if path == root:
                continue
            if len(path.parts) - base_depth > MAX_DEPTH:
                dirnames.clear()
                continue
            if dirnames or filenames:
                continue
            try:
                if path.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            found.append(path)
    return found


def broken_shortcuts(roots: tuple[Path, ...]) -> list[Path]:
    """Ярлыки .lnk, чья цель больше не существует.

    Пустой TargetPath — ярлык UWP-приложения (``explorer.exe shell:…``),
    такие пропускаем: Test-Path по ним ничего не значит.
    """
    existing = [str(p) for p in roots if p.is_dir()]
    if not existing:
        return []
    quoted = ",".join("'" + p.replace("'", "''") + "'" for p in existing)
    script = (
        "$ErrorActionPreference='SilentlyContinue'\n"
        "$sh = New-Object -ComObject WScript.Shell\n"
        f"foreach ($d in @({quoted})) {{\n"
        "  Get-ChildItem -LiteralPath $d -Filter *.lnk -Recurse |\n"
        "  ForEach-Object {\n"
        "    $t = ''\n"
        "    try { $t = $sh.CreateShortcut($_.FullName).TargetPath } catch { }\n"
        "    if ($t -and -not (Test-Path -LiteralPath $t)) { $_.FullName }\n"
        "  }\n"
        "}\n"
    )
    out, _err = run_powershell(script, timeout=120)
    result: list[Path] = []
    for line in out.splitlines():
        line = line.strip()
        if line.lower().endswith(".lnk"):
            result.append(Path(line))
    return result


def _move_to_recycle(paths: list[Path]) -> tuple[str, str]:
    from disk_cleaner_app.services.batch_delete import delete_many

    if not paths:
        return ("OK", "Нечего удалять")
    result = delete_many([str(p) for p in paths], to_recycle=True)
    moved = len(result.get("deleted", []))
    failed = len(result.get("failed", []))
    detail = f"В корзину отправлено: {moved}"
    if failed:
        detail += f", не удалось: {failed}"
    return ("OK", detail)


class EmptyFoldersCleaner(BaseCleaner):
    """Пустые папки в личных каталогах: только в корзину и только старые."""

    id = "empty_folders"
    name = "📁 Пустые папки"
    group = GROUP_SYSTEM
    description = (
        "Пустые папки в Desktop, Documents, Downloads, Pictures, Music, Videos "
        "старше 30 дней."
    )
    safety = SafetyLevel.CAUTION
    layer = LAYER_LEFTOVERS
    recommended = False
    min_age_hours = 24 * 30
    why = "Пустые папки мешают навигации и попадают в индексацию поиска."
    loss = "Пустую папку придётся создать заново, если она понадобится."
    restore_hint = "Корзина: папки возвращаются на место до её очистки."

    def _folders(self) -> list[Path]:
        roots = tuple(USER / name for name in PERSONAL_DIRS if (USER / name).is_dir())
        return empty_folders(roots, self.min_age_hours)

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._folders())

    def get_size(self) -> int:
        # Папки пустые: считаем только сами каталоги, чтобы цель была видна в плане.
        return sum(get_path_size(p) for p in self._folders())

    def clean(self) -> tuple[str, str]:
        return _move_to_recycle(self._folders())


class BrokenShortcutsCleaner(BaseCleaner):
    """Ярлыки на удалённые программы: цель проверяется по файловой системе."""

    id = "broken_shortcuts"
    name = "🔗 Битые ярлыки"
    group = GROUP_SYSTEM
    description = "Ярлыки .lnk с рабочего стола и из меню «Пуск», чья цель удалена."
    safety = SafetyLevel.SAFE
    layer = LAYER_LEFTOVERS
    recommended = False
    min_age_hours = 24
    why = "Ярлык на удалённую программу только вводит в заблуждение."
    loss = "Ярлык исчезнет с рабочего стола или из меню «Пуск»."
    restore_hint = "Корзина, либо создайте ярлык заново."

    def _links(self) -> list[Path]:
        return broken_shortcuts(SHORTCUT_DIRS)

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._links())

    def get_size(self) -> int:
        return sum(get_path_size(p) for p in self._links())

    def clean(self) -> tuple[str, str]:
        return _move_to_recycle(self._links())
