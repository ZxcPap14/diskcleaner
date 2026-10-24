"""ScanEngine — параллельное сканирование всех очистителей."""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    reset_scan_cancel,
    set_scan_cancel,
)
from disk_cleaner_app.cleaners.discover import auto_discover_items


class ScanEngine:
    """Движок сканирования: измеряет размер всех целей с возможностью отмены."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scan")
        self._cancel = threading.Event()
        self.was_cancelled = False

    def cancel(self) -> None:
        """Запросить остановку текущего сканирования."""
        self._cancel.set()

    def scan_all(
        self,
        cleaners: list[BaseCleaner],
        auto_discover: bool = True,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[BaseCleaner]:
        """Отсканировать все cleaner'ы параллельно.

        Возвращает те же объекты с заполненными .size и .scanned.
        Частично просканированные цели остаются ``scanned == False``.
        """
        self._cancel.clear()
        self.was_cancelled = False
        cleaners = self._dedupe(cleaners)

        if auto_discover:
            existing_ids = {c.id for c in cleaners}
            for a in auto_discover_items(cancel_event=self._cancel):
                if a.id not in existing_ids:
                    cleaners.append(a)
                    existing_ids.add(a.id)

        total = len(cleaners)
        futures = {
            self._executor.submit(self._scan_one, cleaner): cleaner
            for cleaner in cleaners
        }

        for i, future in enumerate(as_completed(futures)):
            if self._cancel.is_set():
                self.was_cancelled = True
                for pending in futures:
                    pending.cancel()
                break

            cleaner = futures[future]
            try:
                future.result()
            except Exception as e:  # ошибка одной цели не должна ломать скан
                cleaner.scan_error = str(e)
                cleaner.size = 0
            cleaner.scanned = True
            if progress_callback:
                try:
                    progress_callback(i + 1, total)
                except Exception:
                    # UI-ошибка не должна останавливать сканирование.
                    pass

        if self._cancel.is_set():
            self.was_cancelled = True
        return cleaners

    @staticmethod
    def _dedupe(cleaners: list[BaseCleaner]) -> list[BaseCleaner]:
        """Убрать цели с одинаковым id или одинаковым путём auto-discover."""
        result: list[BaseCleaner] = []
        ids: set[str] = set()
        paths: set[str] = set()
        for c in cleaners:
            if c.id in ids:
                continue
            preview = getattr(c, "preview_path", None)
            if preview:
                key = os.path.normcase(str(preview))
                if key in paths:
                    continue
                paths.add(key)
            ids.add(c.id)
            result.append(c)
        return result

    def _scan_one(self, cleaner: BaseCleaner) -> None:
        token = set_scan_cancel(self._cancel)
        try:
            cleaner.size = cleaner.get_size()
        finally:
            reset_scan_cancel(token)

    def shutdown(self) -> None:
        self._cancel.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
