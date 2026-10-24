"""Общие тестовые двойники."""
from __future__ import annotations

from collections.abc import Callable

from disk_cleaner_app.cleaners.base import BaseCleaner
from disk_cleaner_app.models.item import SafetyLevel


class FakeCleaner(BaseCleaner):
    """Очиститель-заглушка без обращения к диску."""

    def __init__(
        self,
        cleaner_id: str = "fake",
        name: str = "Fake",
        size: int = 0,
        preview_path: str | None = None,
        reply: tuple[str, str] = ("OK", "ok"),
        on_clean: Callable[[FakeCleaner], None] | None = None,
    ) -> None:
        super().__init__()
        self.id = cleaner_id
        self.name = name
        self.group = "Test"
        self.description = ""
        self.safety = SafetyLevel.SAFE
        self.preview_path = preview_path
        self.size = size
        self._fake_size = size
        self._reply = reply
        self._on_clean = on_clean
        self._deleted = False

    def get_size(self) -> int:
        return 0 if self._deleted else self._fake_size

    def clean(self) -> tuple[str, str]:
        status, detail = self._reply
        if status == "OK" and self._on_clean is not None:
            self._on_clean(self)
            self._deleted = True
        return status, detail


class PathCleaner(BaseCleaner):
    """Очиститель с реальными путями на диске (для тестов планировщика)."""

    def __init__(
        self,
        paths,
        cleaner_id: str = "paths",
        name: str = "Paths",
        delete_mode: str = "contents",
        min_age_hours: int = 0,
        admin_required: bool = False,
        layer: str = "A",
        recommended: bool = True,
    ) -> None:
        super().__init__()
        self.id = cleaner_id
        self.name = name
        self.group = "Test"
        self.description = ""
        self.safety = SafetyLevel.SAFE
        self.paths = tuple(paths)
        self.delete_mode = delete_mode
        self.min_age_hours = min_age_hours
        self.admin_required = admin_required
        self.layer = layer
        self.recommended = recommended

    def get_size(self) -> int:
        total = 0
        for path in self.paths:
            if path.is_file():
                total += path.stat().st_size
            elif path.is_dir():
                total += sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        return total

    def clean(self) -> tuple[str, str]:
        return ("OK", "ok")
