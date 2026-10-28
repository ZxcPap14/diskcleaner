"""Дубликаты: поиск одинаковых файлов и удаление лишних копий."""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.duplicates import DuplicateFinder, arrange_groups

log = logging.getLogger(__name__)

MAX_GROUPS = 80


class DuplicatesService:
    """Обёртка над DuplicateFinder для веб-интерфейса."""

    def __init__(self) -> None:
        self._finder = DuplicateFinder(max_results=MAX_GROUPS)
        self._config = ConfigManager()
        self._raw: list[dict[str, Any]] = []
        self._cancel = threading.Event()
        self._busy = False
        self._root = str(Path.home())
        self._mode = "fast"

    def _whitelist(self) -> list[str]:
        """Белый список из настроек: такие пути не попадают в корзину."""
        try:
            raw = self._config.get("whitelist", [])
        except Exception:
            return []
        if isinstance(raw, list):
            return [str(w) for w in raw if str(w).strip()]
        return []

    # ── данные ───────────────────────────────────────

    def _describe(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for index, group in enumerate(self._raw):
            original = group.get("original") or group["files"][0]
            protected = {os.path.normcase(p) for p in group.get("protected", [])}
            files = []
            for path in group["files"]:
                item = Path(path)
                norm = os.path.normcase(path)
                files.append({
                    "path": str(item),
                    "name": item.name,
                    "dir": str(item.parent),
                    "original": norm == os.path.normcase(original),
                    "locked": norm in protected,
                })
            deletable = group.get("deletable", [])
            out.append({
                "id": str(index),
                "name": group["name"],
                "size": group["size"],
                "size_text": format_bytes(group["size"]),
                "count": len(files),
                "wasted_text": format_bytes(group.get("wasted", group["size"] * (len(files) - 1))),
                "locked": len(protected),
                "deletable": len(deletable),
                "files": files,
            })
        return out

    def state(self) -> dict[str, Any]:
        groups = self._describe()
        wasted = sum(
            g["size"] * (len(g["files"]) - 1) for g in self._raw
        )
        return {
            "root": self._root,
            "mode": self._mode,
            "busy": self._busy,
            "groups": groups,
            "count": len(groups),
            "wasted": wasted,
            "wasted_text": format_bytes(wasted) if wasted else "0 Б",
        }

    def set_root(self, path: str) -> dict[str, Any]:
        candidate = Path(str(path or "").strip().strip('"'))
        if candidate.is_dir():
            self._root = str(candidate)
        return self.state()

    # ── поиск ────────────────────────────────────────

    def scan(
        self,
        mode: str,
        progress: Callable[[int, str], None],
        done: Callable[[dict[str, Any]], None],
    ) -> None:
        if self._busy:
            return
        self._busy = True
        self._mode = "exact" if mode == "exact" else "fast"
        self._cancel.clear()
        root = self._root

        def report(scanned: int, _total: int, text: str) -> None:
            progress(scanned, text)

        def worker() -> None:
            try:
                if self._mode == "exact":
                    groups = self._finder.find_exact_groups(
                        root, cancel=self._cancel, progress=report
                    )
                else:
                    groups = self._finder.find_fast_groups(
                        root, cancel=self._cancel, progress=report
                    )
                self._raw = arrange_groups(
                    groups[:MAX_GROUPS], "oldest", self._whitelist()
                )
            except Exception:  # noqa: BLE001
                log.warning("Поиск дубликатов не удался", exc_info=True)
                self._raw = []
            finally:
                self._busy = False
                done(self.state())

        threading.Thread(target=worker, name="dup-scan", daemon=True).start()

    def stop(self) -> dict[str, Any]:
        self._cancel.set()
        return self.state()

    # ── удаление ─────────────────────────────────────

    def delete(self, paths: list[str], to_recycle: bool) -> dict[str, Any]:
        """Удалить отмеченные копии; оригинал и белый список не трогаем."""
        chosen = {str(p) for p in paths}
        pairs: list[dict[str, Any]] = []
        for group in self._raw:
            original = group.get("original") or group["files"][0]
            protected = {
                os.path.normcase(p) for p in group.get("protected", [])
            }
            for path in group["files"][1:]:
                if path not in chosen:
                    continue
                if os.path.normcase(path) in protected:
                    log.warning("Путь из белого списка не удаляется: %s", path)
                    continue
                pairs.append({
                    "name": group["name"],
                    "size": group["size"],
                    "file1": original,
                    "file2": path,
                    "count": len(group["files"]),
                })
        if not pairs:
            return {"deleted": 0, "failed": 0, "freed_text": "0 Б", "state": self.state()}
        result = self._finder.delete_duplicates(pairs, to_recycle=to_recycle)
        remaining: list[dict[str, Any]] = []
        for group in self._raw:
            files = [p for p in group["files"] if p not in chosen]
            if len(files) >= 2:
                remaining.append({**group, "files": files})
        self._raw = remaining
        return {
            "deleted": result.get("deleted", 0),
            "failed": result.get("failed", 0),
            "freed_text": format_bytes(result.get("freed", 0)),
            "errors": result.get("errors", [])[:20],
            "state": self.state(),
        }
