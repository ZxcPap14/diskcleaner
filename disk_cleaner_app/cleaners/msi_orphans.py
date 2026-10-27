"""Осиротевшие установщики MSI/MSP в ``C:\\Windows\\Installer``.

Неудачные установки и обновления оставляют там файлы, на которые больше не
ссылается ни один установленный продукт. Проверяем именно реестр установщика
(``LocalPackage``), а не WMI ``Win32_Product``: обращение к последнему запускает
перенастройку продуктов. Удалённое уходит в корзину — это и есть карантин.
"""
from __future__ import annotations

import os
import winreg
from pathlib import Path

from disk_cleaner_app.cleaners.base import BaseCleaner, get_path_size
from disk_cleaner_app.models.item import GROUP_SYSTEM, SafetyLevel
from disk_cleaner_app.models.target import LAYER_LEFTOVERS

INSTALLER_DIR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Installer"
USERDATA_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData"
LOCAL_PACKAGE = "localpackage"
MAX_DEPTH = 6


def _walk_local_package(
    path: str, view: int, depth: int = 0,
):
    """Все значения LocalPackage в ветке (рекурсивно, только чтение)."""
    if depth > MAX_DEPTH:
        return
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0,
                             winreg.KEY_READ | view)
    except OSError:
        return
    with key:
        index = 0
        while True:
            try:
                name, value, _kind = winreg.EnumValue(key, index)
            except OSError:
                break
            index += 1
            if name.lower() == LOCAL_PACKAGE and isinstance(value, str) and value:
                yield value
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(key, index)
            except OSError:
                break
            index += 1
            yield from _walk_local_package(f"{path}\\{sub}", view, depth + 1)


def referenced_packages() -> set[str]:
    """Имена файлов установщиков, на которые ссылаются продукты и патчи."""
    names: set[str] = set()
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        for value in _walk_local_package(USERDATA_KEY, view):
            names.add(Path(value.replace("/", "\\")).name.lower())
    return names


def orphan_files(installer_dir: Path, referenced: set[str]) -> list[Path]:
    """MSI/MSP, которых нет среди используемых установщиком."""
    try:
        entries = list(installer_dir.iterdir())
    except OSError:
        return []
    return [
        p for p in entries
        if p.is_file()
        and p.suffix.lower() in (".msi", ".msp")
        and p.name.lower() not in referenced
    ]


class MsiOrphanCleaner(BaseCleaner):
    """Слой D: лишние MSI/MSP — в корзину, откуда их можно вернуть."""

    id = "msi_orphans"
    name = "🧾 Осиротевшие установщики MSI/MSP"
    group = GROUP_SYSTEM
    description = (
        f"Файлы в {INSTALLER_DIR}, на которые не ссылается ни один "
        "установленный продукт или патч."
    )
    safety = SafetyLevel.ADVANCED
    layer = LAYER_LEFTOVERS
    admin_required = True
    recommended = False
    min_age_hours = 24 * 7
    why = (
        "После неудачных установок и обновлений остаются MSI/MSP, которые "
        "установщик Windows уже не использует (обычно 1–5 ГБ)."
    )
    loss = (
        "Если файл всё же нужен, починка или удаление этой программы не "
        "сработает — вернуть можно из корзины до её очистки."
    )
    restore_hint = "Корзина: восстановите файл в C:\\Windows\\Installer."

    def _orphans(self) -> list[Path]:
        # Без кэша: движок после очистки пересчитывает get_size(), и кэш
        # показал бы «удалено частично» на уже удалённых файлах.
        return orphan_files(INSTALLER_DIR, referenced_packages())

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._orphans())

    def get_size(self) -> int:
        return sum(get_path_size(p) for p in self._orphans())

    def clean(self) -> tuple[str, str]:
        """В корзину: восстановление возможно до её очистки."""
        from disk_cleaner_app.services.batch_delete import delete_many

        paths = [str(p) for p in self._orphans() if p.exists()]
        if not paths:
            return ("OK", "Осиротевших установщиков не найдено")
        result = delete_many(paths, to_recycle=True)
        moved = len(result.get("deleted", []))
        failed = len(result.get("failed", []))
        detail = f"В корзину отправлено: {moved}"
        if failed:
            detail += f", не удалось: {failed}"
        return ("OK", detail)
