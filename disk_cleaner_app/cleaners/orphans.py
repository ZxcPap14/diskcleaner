"""🧹 Остатки удалённых программ в AppData (слой D, только корзина).

Сравниваем папки верхнего уровня ``%LocalAppData%``/``%AppData%`` с
установленными программами (реестр Windows). Если по имени нет никакого
совпадения, папка старше 90 дней и не входит в запретный список — считаем
её «остатком». Удаление — целиком в корзину, только по выбору пользователя.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from disk_cleaner_app.cleaners.base import BaseCleaner, get_dir_size, safe_remove
from disk_cleaner_app.models.item import GROUP_APPS, SafetyLevel
from disk_cleaner_app.models.target import LAYER_LEFTOVERS

log = logging.getLogger(__name__)

LOCAL_APPDATA = Path.home() / "AppData" / "Local"
ROAMING_APPDATA = Path.home() / "AppData" / "Roaming"

# Возраст, с которого папка считается остатком (90 дней).
ORPHAN_MIN_AGE_DAYS = 90

# Папки, которые никогда не считаем остатком: системные и составные
# (у вендоров сотни продуктов под одной папкой), кэши пакетных менеджеров
# (у них свои цели очистки) и логи/телеметрия.
ALWAYS_EXCLUDE = {
    "cache", "caches", "temp", "tmp", "common", "packages", "squirreltemp",
    "microsoft", "microsoftedge", "chromium", "desktopapphelper",
    # пакетные менеджеры и toolchains: у них свои цели очистки
    "npm-cache", "npm", "pip", "yarn", "uv", "bun", "conda", "nuget",
    "cargo", "go", "gradle", "maven", "rust", "deno", "pnpm",
    # общие корзины/логи/телеметрия разных программ
    "logs", "log", "crashreports", "sentry", "squirrel", "crashdumps",
    "webcache", "gpucache", "d3dscache",
}

_WORD_RE = re.compile(r"[^a-zа-я0-9]+")


def normalize_name(name: str) -> str:
    """Нормализовать имя: нижний регистр, без пунктуации."""
    return _WORD_RE.sub(" ", name.lower()).strip()


def compact_name(normalized: str) -> str:
    """Имя без пробелов — для сравнения «yandexbrowser» ↔ «yandex browser»."""
    return normalized.replace(" ", "")


# Запретный список в нормализованном виде: дефисы и пунктуация в именах
# папок не должны обходить проверку (npm-cache → «npm cache»).
_EXCLUDE_NORMALIZED = {normalize_name(name) for name in ALWAYS_EXCLUDE}
_EXCLUDE_NORMALIZED |= {compact_name(name) for name in _EXCLUDE_NORMALIZED}


def _installed_names() -> set[str]:
    """Имена установленных программ и издателей (нормализованные)."""
    try:
        from disk_cleaner_app.services.uninstaller import AppUninstaller

        apps = AppUninstaller().get_installed()
    except Exception:
        log.info("Список установленных программ недоступен", exc_info=True)
        return set()
    names: set[str] = set()
    for app in apps:
        for key in ("name", "publisher"):
            raw = str(app.get(key, "") or "")
            normalized = normalize_name(raw)
            if normalized:
                names.add(normalized)
                names.add(compact_name(normalized))
    return names


def _is_orphan(
    candidate: str, installed_names: set[str], roots_children: set[str]
) -> bool:
    """Решение по одной папке: нет совпадений с программами и не в deny-list."""
    normalized = normalize_name(candidate)
    if not normalized:
        return False
    if normalized in _EXCLUDE_NORMALIZED:
        return False
    if compact_name(normalized) in _EXCLUDE_NORMALIZED:
        return False
    # Совпадение с любой программой или издателем (в обе стороны).
    probe = (normalized, compact_name(normalized))
    for other in installed_names:
        if not other:
            continue
        for form in probe:
            if form and (form in other or other in form):
                return False
    # Совпадение с соседней папкой корня (защита от vendor-папок).
    for neighbour in roots_children:
        if neighbour == candidate:
            continue
        other = normalize_name(neighbour)
        if other and (normalized in other or other in normalized):
            return False
    return True


def _age_days(path: Path) -> float | None:
    """Возраст папки по mtime; None, если не удалось прочитать."""
    try:
        return (time.time() - path.stat().st_mtime) / 86_400
    except OSError:
        return None


class OrphanAppDataCleaner(BaseCleaner):
    """Остатки программ, которых больше нет среди установленных.

    По умолчанию ничего не выбрано: `recommended = False` и слой D
    гарантируют корзину. Каждый путь — отдельное действие плана.
    """

    id = "orphan_appdata"
    name = "🧹 Остатки удалённых программ (AppData)"
    group = GROUP_APPS
    description = (
        f"Папки в AppData без установленной программы; старше "
        f"{ORPHAN_MIN_AGE_DAYS} дней. Только корзина."
    )
    safety = SafetyLevel.ADVANCED
    layer = LAYER_LEFTOVERS
    admin_required = False
    recommended = False
    delete_mode = "remove"        # папка целиком
    min_age_hours = ORPHAN_MIN_AGE_DAYS * 24
    why = "Программа удалена, а её папка с конфигами осталась и занимает место."
    loss = (
        "Если папка принадлежит ещё кому-то (сохранения, конфиги), "
        "они пропадут после очистки корзины."
    )
    restore_hint = "Всё перемещается в корзину — восстановление доступно."

    def affected_paths(self) -> tuple[Path, ...]:
        installed = _installed_names()
        orphans: list[Path] = []
        for root in (LOCAL_APPDATA, ROAMING_APPDATA):
            if not root.is_dir():
                continue
            try:
                children = [
                    entry.name for entry in root.iterdir() if entry.is_dir()
                ]
            except OSError:
                continue
            child_set = set(children)
            for name in children:
                candidate = root / name
                if not _is_orphan(name, installed, child_set):
                    continue
                age = _age_days(candidate)
                if age is not None and age >= ORPHAN_MIN_AGE_DAYS:
                    orphans.append(candidate)
        return tuple(orphans)

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for path in self.affected_paths():
            if path.exists() and not safe_remove(path, to_recycle=True):
                ok = False
        return ("OK", "Остатки перемещены в корзину") if ok else (
            "ERR", "Часть папок занята — повторите позже"
        )
