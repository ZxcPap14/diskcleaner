"""🪟 UWP/Store-приложения: кэши внутри %LocalAppData%\\Packages.

Затрагиваем только каталоги, которые Windows определяет как временные:
``AC\\INetCache``, ``AC\\Temp`` и ``TempState``. ``LocalCache`` и
``LocalState`` сознательно не трогаем — там приложения держат настройки
и состояние, а не кэш. Сама папка пакета остаётся на месте: чистится
содержимое, вход в приложения и их данные не затрагиваются.
"""
from __future__ import annotations

from pathlib import Path

from disk_cleaner_app.cleaners.base import BaseCleaner, get_dir_size, safe_rm_contents
from disk_cleaner_app.models.item import GROUP_SYSTEM, SafetyLevel
from disk_cleaner_app.models.target import LAYER_SAFE

LOCAL = Path.home() / "AppData" / "Local"

# Имена подкаталогов пакета, которые безопасно очищать по содержимому.
_CACHE_SUBDIRS = (
    ("AC", "INetCache"),
    ("AC", "Temp"),
    ("TempState",),
)


def package_cache_dirs(packages_root: Path) -> list[Path]:
    """Существующие кэш-каталоги всех UWP-пакетов."""
    if not packages_root.is_dir():
        return []
    found: list[Path] = []
    try:
        packages = [p for p in packages_root.iterdir() if p.is_dir()]
    except OSError:
        return []
    for package in packages:
        for parts in _CACHE_SUBDIRS:
            candidate = package.joinpath(*parts)
            try:
                if candidate.is_dir():
                    found.append(candidate)
            except OSError:
                continue
    return found


class UwpAppCachesCleaner(BaseCleaner):
    """Кэши UWP/Store-приложений: INetCache, AC\\Temp и TempState."""

    id = "uwp_caches"
    name = "🪟 Кэши UWP/Store-приложений"
    group = GROUP_SYSTEM
    description = "%LocalAppData%\\Packages\\*\\AC\\INetCache, AC\\Temp, TempState"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "contents"
    why = (
        "Windows определяет TempState как каталог, который можно очищать, "
        "а INetCache — это кэш веб-данных пакетов. Настройки и вход "
        "приложений (LocalState, LocalCache) не затрагиваются."
    )
    loss = "Плитки/приложения перезагрузят веб-данные; данные пользователя остаются."

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(package_cache_dirs(LOCAL / "Packages"))

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        cleaned = 0
        for path in self.affected_paths():
            if safe_rm_contents(path):
                cleaned += 1
            else:
                ok = False
        if not ok:
            return ("OK", (
                f"Кэши пакетов очищены частично ({cleaned}); "
                "часть файлов занята запущенными приложениями"
            ))
        return ("OK", f"Кэши пакетов очищены: {cleaned} каталогов")


UWP_CLEANERS: list[type[BaseCleaner]] = [UwpAppCachesCleaner]
