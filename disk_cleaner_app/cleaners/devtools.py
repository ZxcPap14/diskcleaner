"""📦 Очистители Dev Tools: npm, pip, yarn, uv, rust, gradle, etc."""
from __future__ import annotations

from pathlib import Path

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    get_dir_size,
    get_path_size,
    safe_rm_contents,
)
from disk_cleaner_app.models.item import GROUP_DEVTOOLS, SafetyLevel
from disk_cleaner_app.models.target import LAYER_COMPONENTS, LAYER_SAFE

LOCAL = Path.home() / "AppData" / "Local"
ROAMING = Path.home() / "AppData" / "Roaming"
USER = Path.home()


class _PathCacheCleaner(BaseCleaner):
    """Кэш, который можно удалить целиком и который создастся заново."""

    group = GROUP_DEVTOOLS
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш пакетного менеджера; пакеты скачаются заново при необходимости."
    loss = "Следующая установка зависимостей будет дольше."

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(p for p in self.paths if p.exists())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if p.exists() and not safe_rm_contents(p):
                ok = False
        return ("OK", f"{self.name} очищен") if ok else ("ERR", "Ошибка очистки кэша")


class NPmCacheCleaner(_PathCacheCleaner):
    id = "npm"
    name = "📦 npm cache"
    description = "%LocalAppData%\\npm-cache"
    paths = (LOCAL / "npm-cache",)


class PipCacheCleaner(_PathCacheCleaner):
    id = "pip"
    name = "📦 pip cache"
    description = "%LocalAppData%\\pip\\cache"
    paths = (LOCAL / "pip" / "cache",)


class YarnCacheCleaner(_PathCacheCleaner):
    id = "yarn"
    name = "📦 yarn cache"
    description = "%LocalAppData%\\Yarn\\Cache"
    paths = (LOCAL / "Yarn" / "Cache",)


class UvCacheCleaner(_PathCacheCleaner):
    id = "uv"
    name = "📦 uv cache"
    description = "%LocalAppData%\\uv\\cache"
    paths = (LOCAL / "uv" / "cache",)


class BunCacheCleaner(_PathCacheCleaner):
    id = "bun"
    name = "📦 bun cache"
    description = "%LocalAppData%\\bun\\cache"
    paths = (LOCAL / "bun" / "cache",)


class RustCacheCleaner(_PathCacheCleaner):
    id = "rust"
    name = "🦀 Rust cache"
    description = "%LocalAppData%\\rustup\\cache, cargo\\registry\\cache"
    paths = (
        LOCAL / "rustup" / "cache",
        LOCAL / "cargo" / "registry" / "cache",
    )


class GradleCacheCleaner(_PathCacheCleaner):
    id = "gradle"
    name = "📦 Gradle caches"
    description = "%LocalAppData%\\gradle\\caches"
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    recommended = False
    paths = (LOCAL / "gradle" / "caches",)
    why = "Кэш зависимостей Gradle; сборка скачает их заново."
    loss = "Следующая сборка будет заметно дольше, особенно без сети."


class PlaywrightBrowsersCleaner(BaseCleaner):
    id = "playwright"
    name = "🎭 Playwright browsers"
    group = GROUP_DEVTOOLS
    description = "%USER%\\.cache\\ms-playwright"
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    recommended = False
    delete_mode = "remove"
    paths = (USER / ".cache" / "ms-playwright",)
    why = "Браузеры для тестов; переустанавливаются командой playwright install."
    loss = "Тесты не запустятся, пока браузеры не будут скачаны заново."
    restore_hint = "python -m playwright install"

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Playwright browsers очищены") if ok else ("ERR", "Ошибка")


class VSCodeCacheCleaner(BaseCleaner):
    id = "vscode_ext"
    name = "📝 VS Code Cache"
    group = GROUP_DEVTOOLS
    description = "VS Code cache и недокачанные VSIX"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш редактора и временные .tgz; сами расширения не трогаем."
    loss = "Редактор запустится чуть медленнее; расширения сохранятся."

    def affected_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        ext = USER / ".vscode" / "extensions"
        if ext.exists():
            paths.extend(p for p in ext.glob("_*.tgz") if p.is_file())
        for base in (ROAMING / "Code", LOCAL / "Code"):
            for sub in ("Cache", "CachedData", "GPUCache"):
                p = base / sub
                if p.exists():
                    paths.append(p)
        return tuple(paths)

    def get_size(self) -> int:
        return sum(get_path_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    ok = False
            elif not safe_rm_contents(p):
                ok = False
        return ("OK", "VS Code cache очищен") if ok else ("ERR", "Ошибка")


class AntigravityExtensionsCleaner(BaseCleaner):
    """Оставлен для совместимости, но НЕ входит в реестр.

    ``~/.antigravity/extensions`` — это установленные расширения, а не кэш.
    """

    id = "antigravity_ext"
    name = "🐍 Antigravity Extensions"
    group = GROUP_DEVTOOLS
    description = "%USER%\\.antigravity\\extensions"
    safety = SafetyLevel.ADVANCED
    layer = LAYER_COMPONENTS
    recommended = False
    paths = (USER / ".antigravity" / "extensions",)
    why = "Это установленные расширения, а не кэш. Удаление сломает среду."
    loss = "Расширения придётся устанавливать заново."
    restore_hint = "Переустановите расширения вручную."

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        return ("SKIP", "Цель отключена: это установленные расширения, а не кэш.")


DEVTOOLS_CLEANERS = [
    NPmCacheCleaner,
    PipCacheCleaner,
    YarnCacheCleaner,
    UvCacheCleaner,
    BunCacheCleaner,
    RustCacheCleaner,
    GradleCacheCleaner,
    PlaywrightBrowsersCleaner,
    VSCodeCacheCleaner,
]
