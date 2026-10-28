"""Страница «Программы»: установленные приложения, размеры и удаление.

Обёртка над :class:`AppUninstaller` без Tk: те же данные, но отдача в виде
словарей для JS. Размеры папок считаются в фоне — реестр отдаёт только
оценку, а она у половины программ нулевая.
"""
from __future__ import annotations

import threading
from typing import Any

from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.services.uninstaller import AppUninstaller

BATCH = 15


def _date(raw: str) -> str:
    """``20261028`` → ``28.10.2026``."""
    raw = str(raw or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[6:8]}.{raw[4:6]}.{raw[:4]}"
    return raw


class ProgramsService:
    """Список установленных программ и их штатное удаление."""

    def __init__(self) -> None:
        self._uninstaller = AppUninstaller()
        self._apps: list[dict[str, Any]] = []
        self._loaded = False
        self._measuring = False
        self._lock = threading.Lock()

    def _row(self, app: dict[str, Any]) -> dict[str, Any]:
        real = app.get("real_size")
        if real:
            size_text = format_bytes(int(real))
        else:
            kb = int(app.get("size_kb") or 0)
            size_text = format_bytes(kb * 1024) if kb > 0 else ""
        return {
            "id": app.get("registry_key") or app.get("name", ""),
            "name": app.get("name", ""),
            "version": app.get("version", ""),
            "publisher": app.get("publisher", ""),
            "drive": app.get("drive", ""),
            "date": _date(app.get("install_date", "")),
            "size_text": size_text,
            "measured": bool(real),
        }

    def state(self) -> dict[str, Any]:
        with self._lock:
            apps = list(self._apps)
        rows = [self._row(app) for app in apps]
        drives = sorted({row["drive"] for row in rows if row["drive"]})
        return {
            "apps": rows,
            "count": len(rows),
            "drives": drives,
            "measuring": self._measuring,
        }

    def load(self) -> dict[str, Any]:
        if not self._loaded:
            apps = self._uninstaller.get_installed()
            with self._lock:
                self._apps = apps
                self._loaded = True
        return self.state()

    def measure(self, notify: Any) -> None:
        """Посчитать реальные размеры папок в фоне и отдать порциями."""
        with self._lock:
            if self._measuring:
                return
            self._measuring = True
            apps = [a for a in self._apps if str(a.get("install_location", "")).strip()]
        try:
            batch: list[dict[str, Any]] = []
            for app in apps:
                try:
                    size = self._uninstaller.install_size(app)
                except Exception:
                    size = None
                if size:
                    app["real_size"] = size
                    batch.append({"id": self._row(app)["id"], "size_text": format_bytes(size)})
                if len(batch) >= BATCH:
                    notify(batch)
                    batch = []
            if batch:
                notify(batch)
        finally:
            with self._lock:
                self._measuring = False

    def uninstall(self, app_id: str) -> dict[str, Any]:
        """Запустить штатный деинсталлятор выбранной программы."""
        with self._lock:
            app = next(
                (a for a in self._apps
                 if (a.get("registry_key") or a.get("name", "")) == app_id),
                None,
            )
        if app is None:
            return {"ok": False, "logs": ["Программа не найдена в списке."]}
        logs = self._uninstaller.uninstall(app)
        with self._lock:
            if self._apps:
                self._apps = [a for a in self._apps if a is not app]
        return {"ok": True, "logs": logs, "state": self.state()}
