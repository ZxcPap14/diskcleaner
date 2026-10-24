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
from disk_cleaner_app.services.batch_delete import delete_many

ProgressCallback = Callable[[int, int, str], None]

PARTIAL_CHUNK = 64 * 1024
HASH_CHUNK = 256 * 1024
DEFAULT_HASH = "blake2b"


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

        return self._groups_to_results(groups)

    # ── точный поиск ─────────────────────────────────────

    def find_exact(
        self,
        root: str,
        min_size_kb: int = 100,
        cancel: threading.Event | None = None,
        progress: ProgressCallback | None = None,
    ) -> list[dict]:
        """Точный поиск: размер → частичный хэш → полный BLAKE2b."""
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

        return self._groups_to_results(final_groups)

    def _groups_to_results(self, groups: dict) -> list[dict]:
        """Конвертировать группы в список пар (оригинал, дубликат)."""
        results = []
        for _key, files in groups.items():
            if len(files) < 2:
                continue
            try:
                sz = os.stat(files[0]).st_size
            except OSError:
                continue

            for i in range(1, len(files)):
                results.append({
                    "name": os.path.basename(files[0]),
                    "size": sz,
                    "file1": files[0],
                    "file2": files[i],
                    "count": len(files),
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
