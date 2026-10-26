"""DuplicateFinder — поиск дубликатов: быстрый (имя+размер) и точный (хеш)."""
from __future__ import annotations

import hashlib
import os
import threading
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from disk_cleaner_app.cleaners.base import safe_remove
from disk_cleaner_app.cleaners.safety import is_whitelisted
from disk_cleaner_app.services.batch_delete import delete_many

ProgressCallback = Callable[[int, int, str], None]

PARTIAL_CHUNK = 64 * 1024
HASH_CHUNK = 256 * 1024
DEFAULT_HASH = "blake2b"

# Правила выбора оригинала внутри группы дубликатов.
ORIGINAL_POLICIES = {
    "oldest": "Самый старый",
    "newest": "Самый новый",
    "short_path": "Короткий путь",
}
_JUNK_PARTS = {"temp", "tmp", "downloads"}


def is_junk_path(path: str | Path) -> bool:
    """Лежит ли файл в Temp/Downloads/Tmp — такие копии удаляем первыми."""
    try:
        parts = Path(path).parts
    except (OSError, ValueError):
        return False
    return any(part.lower() in _JUNK_PARTS for part in parts)


def choose_original(
    files: list[str],
    policy: str = "oldest",
    *,
    junk_first: bool = True,
    stat_fn: Callable[[str], os.stat_result] = os.stat,
) -> str:
    """Выбрать файл-оригинал: его не удаляем, остальные — кандидаты в корзину.

    ``junk_first`` опускает копии из Temp/Downloads в конец, чтобы оригиналом
    осталась «настоящая» копия пользователя. Неизвестный mtime никогда не
    выигрывает у известного.
    """
    if not files:
        return ""
    if len(files) == 1:
        return files[0]

    def sort_key(path: str) -> tuple:
        try:
            mtime = stat_fn(path).st_mtime
            unknown = 0
        except OSError:
            mtime = 0.0
            unknown = 1
        junk = is_junk_path(path) if junk_first else False
        if policy == "newest":
            moment = -mtime
        elif policy == "short_path":
            moment = 0.0
        else:  # oldest — безопасный вариант по умолчанию
            moment = mtime
        return (junk, unknown, moment, len(str(path)), str(path).casefold())

    return min(files, key=sort_key)


def arrange_groups(
    groups: list[dict],
    policy: str = "oldest",
    whitelist: list[str] | tuple[str, ...] = (),
    *,
    junk_first: bool = True,
    stat_fn: Callable[[str], os.stat_result] = os.stat,
) -> list[dict]:
    """Переставить файлы в группах: [оригинал, защищённые, к удалению].

    Пути из белого списка («никогда не удалять») остаются в группе, но
    никогда не попадают в ``deletable``. Группы без файлов к удалению
    сохраняются для показа с пустым ``deletable``.
    """
    out: list[dict] = []
    for group in groups:
        files = [str(f) for f in group.get("files", [])]
        if len(files) < 2:
            continue
        original = choose_original(files, policy, junk_first=junk_first, stat_fn=stat_fn)
        rest = [f for f in files if os.path.normcase(f) != os.path.normcase(original)]
        protected = [f for f in rest if is_whitelisted(f, whitelist)]
        protected_keys = {os.path.normcase(f) for f in protected}
        deletable = [f for f in rest if os.path.normcase(f) not in protected_keys]
        out.append({
            **group,
            "files": [original, *protected, *deletable],
            "original": original,
            "protected": protected,
            "deletable": deletable,
            "wasted": int(group.get("size", 0)) * len(deletable),
        })
    return out


class DuplicateFinder:
    """Поиск дублирующихся файлов.

    Точный режим трёхфазный: размер → частичный хэш (64 КБ) → полный BLAKE2b.
    Полный хэш считается только для файлов, совпавших по первым килобайтам.
    """

    def __init__(self, max_results: int = 200) -> None:
        self._min_size_kb: int = 100
        self._max_results = max_results

    # ── быстрый поиск ────────────────────────────────────

    def find_fast(
        self,
        root: str,
        min_size_kb: int = 100,
        cancel: threading.Event | None = None,
        progress: ProgressCallback | None = None,
    ) -> list[dict]:
        """Быстрый поиск: группировка по (имя_файла, размер)."""
        return self._pairs(self.find_fast_groups(
            root, min_size_kb=min_size_kb, cancel=cancel, progress=progress
        ))

    def find_fast_groups(
        self,
        root: str,
        min_size_kb: int = 100,
        cancel: threading.Event | None = None,
        progress: ProgressCallback | None = None,
    ) -> list[dict]:
        """Быстрый поиск, результат — группы из N≥2 одинаковых файлов."""
        self._min_size_kb = min_size_kb
        groups: dict[tuple, list[str]] = defaultdict(list)
        scanned = 0

        for dirpath, _dirs, filenames in os.walk(root):
            if cancel is not None and cancel.is_set():
                break
            for fn in filenames:
                try:
                    fp = os.path.join(dirpath, fn)
                    st = os.stat(fp)
                    if st.st_size < min_size_kb * 1024:
                        continue
                    key = (fn.lower(), st.st_size)
                    groups[key].append(fp)
                except (OSError, PermissionError):
                    continue
                scanned += 1
                if progress and scanned % 500 == 0:
                    progress(scanned, 0, f"Проверено файлов: {scanned}")

        return self._group_list(groups)

    # ── точный поиск ─────────────────────────────────────

    def find_exact(
        self,
        root: str,
        min_size_kb: int = 100,
        cancel: threading.Event | None = None,
        progress: ProgressCallback | None = None,
    ) -> list[dict]:
        """Точный поиск: размер → частичный хэш → полный BLAKE2b."""
        return self._pairs(self.find_exact_groups(
            root, min_size_kb=min_size_kb, cancel=cancel, progress=progress
        ))

    def find_exact_groups(
        self,
        root: str,
        min_size_kb: int = 100,
        cancel: threading.Event | None = None,
        progress: ProgressCallback | None = None,
    ) -> list[dict]:
        """Точный поиск, результат — группы из N≥2 идентичных файлов."""
        self._min_size_kb = min_size_kb

        # Фаза 1: группировка по размеру (файлы одного размера — кандидаты).
        size_groups: dict[int, list[str]] = defaultdict(list)
        for dirpath, _dirs, filenames in os.walk(root):
            if cancel is not None and cancel.is_set():
                return []
            for fn in filenames:
                try:
                    fp = os.path.join(dirpath, fn)
                    st = os.stat(fp)
                    if st.st_size < min_size_kb * 1024:
                        continue
                    size_groups[st.st_size].append(fp)
                except (OSError, PermissionError):
                    continue

        candidates = [files for files in size_groups.values() if len(files) > 1]
        total = sum(len(files) for files in candidates)
        if total == 0:
            return []

        # Фаза 2: частичный хэш первых 64 КБ.
        partial_groups: dict[tuple, list[str]] = defaultdict(list)
        processed = 0
        for files in candidates:
            for fp in files:
                if cancel is not None and cancel.is_set():
                    return []
                try:
                    # Размер берём вместе с хэшем: файл может исчезнуть
                    # между вызовами — тогда кандидат просто пропускается.
                    digest = self._hash_file(fp, limit=PARTIAL_CHUNK)
                    size = os.path.getsize(fp)
                except OSError:
                    continue
                partial_groups[(size, digest)].append(fp)
                processed += 1
                if progress:
                    progress(processed, total, "Быстрое сравнение (64 КБ)")

        # Фаза 3: полный хэш только для совпавших по префиксу.
        remaining = sum(len(files) for files in partial_groups.values() if len(files) > 1)
        final_groups: dict[tuple, list[str]] = defaultdict(list)
        processed = 0
        for (_size, _partial), files in partial_groups.items():
            if len(files) < 2:
                continue
            for fp in files:
                if cancel is not None and cancel.is_set():
                    return []
                try:
                    digest = self._hash_file(fp)
                    size = os.path.getsize(fp)
                except OSError:
                    continue
                final_groups[(size, digest)].append(fp)
                processed += 1
                if progress and remaining:
                    progress(processed, remaining, "Полное сравнение (BLAKE2b)")

        return self._group_list(final_groups)

    def _group_list(self, groups: dict, limit: int | None = None) -> list[dict]:
        """Конвертировать словарь групп в список групп-описаний.

        Каждая группа: name, size, files (первый — оригинал), count, wasted.
        Сортировка по «занятому зря» месту (убывание).
        """
        max_groups = limit if limit is not None else self._max_results
        out: list[dict] = []
        for _key, files in groups.items():
            if len(files) < 2:
                continue
            try:
                sz = os.stat(files[0]).st_size
            except OSError:
                continue
            out.append({
                "name": os.path.basename(files[0]),
                "size": sz,
                "files": list(files),
                "count": len(files),
                "wasted": sz * (len(files) - 1),
            })
        out.sort(key=lambda g: g["wasted"], reverse=True)
        return out[:max_groups]

    def _pairs(self, groups: list[dict]) -> list[dict]:
        """Развернуть группы в список пар (оригинал, дубликат)."""
        results = []
        for group in groups:
            files = group["files"]
            for i in range(1, len(files)):
                results.append({
                    "name": group["name"],
                    "size": group["size"],
                    "file1": files[0],
                    "file2": files[i],
                    "count": group["count"],
                })
                if len(results) >= self._max_results:
                    return results
        return results

    @staticmethod
    def _hash_file(fpath: str, limit: int | None = None) -> str:
        """BLAKE2b-16 хеш файла; ``limit`` ограничивает чтение префиксом."""
        h = hashlib.blake2b(digest_size=16)
        remaining = limit
        with open(fpath, "rb") as f:
            while True:
                if remaining is not None and remaining <= 0:
                    break
                size = HASH_CHUNK if remaining is None else min(HASH_CHUNK, remaining)
                chunk = f.read(size)
                if not chunk:
                    break
                h.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
        return h.hexdigest()

    # ── удаление ─────────────────────────────────────────

    def delete_duplicates(
        self,
        duplicates: list[dict],
        to_recycle: bool = True,
    ) -> dict:
        """Удалить второй файл каждой пары.

        Оригинал (``file1``) не трогаем. Повторяющиеся ``file2`` удаляются
        только один раз. По умолчанию файлы отправляются в корзину одним
        пакетным вызовом оболочки Windows.
        """
        result: dict[str, Any] = {
            "deleted": 0, "failed": 0, "freed": 0, "errors": []
        }
        handled: set[str] = set()
        targets: list[tuple[str, int]] = []

        for pair in duplicates:
            original = str(pair.get("file1", ""))
            target = str(pair.get("file2", ""))
            if not target:
                continue

            key = os.path.normcase(target)
            if key in handled:
                continue
            handled.add(key)

            original_path = Path(original)
            target_path = Path(target)
            if key == os.path.normcase(original):
                result["failed"] += 1
                result["errors"].append(f"Пропуск (совпадает с оригиналом): {target}")
                continue
            if not original_path.exists():
                result["failed"] += 1
                result["errors"].append(f"Пропуск (оригинал не найден): {original}")
                continue
            if not target_path.is_file():
                result["failed"] += 1
                result["errors"].append(f"Пропуск (файл не найден): {target}")
                continue

            try:
                size = target_path.stat().st_size
            except OSError:
                size = 0
            targets.append((str(target_path), size))

        if not targets:
            return result

        if to_recycle:
            batch = delete_many([path for path, _ in targets], to_recycle=True)
            removed = {os.path.normcase(p) for p in batch["deleted"]}
            for path, size in targets:
                if os.path.normcase(path) in removed:
                    result["deleted"] += 1
                    result["freed"] += size
                else:
                    result["failed"] += 1
                    result["errors"].append(f"Не удалось переместить в корзину: {path}")
            return result

        for path, size in targets:
            if safe_remove(Path(path), to_recycle=False):
                result["deleted"] += 1
                result["freed"] += size
            else:
                result["failed"] += 1
                result["errors"].append(f"Не удалось удалить: {path}")

        return result
