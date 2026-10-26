"""📦 Очистители Dev Tools: npm, pip, yarn, uv, rust, gradle, docker, etc."""
from __future__ import annotations

import shutil
import subprocess
import time
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
    description = "rustup\\cache, cargo registry (cache, src) и git db"
    paths = (
        LOCAL / "rustup" / "cache",
        LOCAL / "cargo" / "registry" / "cache",
        LOCAL / "cargo" / "registry" / "src",
        LOCAL / "cargo" / "git" / "db",
        USER / ".cargo" / "registry" / "cache",
        USER / ".cargo" / "registry" / "src",
        USER / ".cargo" / "git" / "db",
    )


class GoBuildCacheCleaner(_PathCacheCleaner):
    id = "go_build"
    name = "📦 Go build cache"
    description = "%LocalAppData%\\go-build"
    paths = (LOCAL / "go-build",)
    why = "Компиляционный кэш Go; пересоздаётся при сборке."
    loss = "Первая сборка после очистки будет дольше."


class GoModCacheCleaner(_PathCacheCleaner):
    id = "go_mod"
    name = "📦 Go module cache"
    description = "%UserProfile%\\go\\pkg\\mod"
    paths = (USER / "go" / "pkg" / "mod",)
    why = "Кэш скачанных модулей Go; пакеты скачаются заново при необходимости."
    loss = "Следующая сборка скачает модули заново, особенно без сети."


class PnpmStoreCleaner(_PathCacheCleaner):
    id = "pnpm"
    name = "📦 pnpm store"
    description = "%LocalAppData%\\pnpm\\store, pnpm-cache"
    paths = (
        LOCAL / "pnpm" / "store",
        LOCAL / "pnpm" / "cache",
        LOCAL / "pnpm-cache",
    )
    why = (
        "Хранилище пакетов pnpm. Существующие node_modules не ломаются: "
        "файлы жёстких ссылок живут независимо от store."
    )
    loss = "Новые зависимости скачаются заново."


class DenoCacheCleaner(_PathCacheCleaner):
    id = "deno"
    name = "📦 Deno cache"
    description = "%LocalAppData%\\deno"
    paths = (LOCAL / "deno",)


class PoetryCacheCleaner(_PathCacheCleaner):
    id = "poetry"
    name = "📦 Poetry cache"
    description = "%LocalAppData%\\pypoetry\\Cache"
    paths = (LOCAL / "pypoetry" / "Cache",)


class PipxCacheCleaner(_PathCacheCleaner):
    id = "pipx"
    name = "📦 pipx cache"
    description = "%LocalAppData%\\pipx\\cache"
    paths = (LOCAL / "pipx" / "cache",)


class CypressCacheCleaner(_PathCacheCleaner):
    id = "cypress"
    name = "📦 Cypress binary cache"
    description = "%LocalAppData%\\Cypress\\Cache (браузеры Cypress)"
    paths = (LOCAL / "Cypress" / "Cache",)
    why = "Скачанные бинарники Cypress; скачаются заново при следующем запуске."
    loss = "cypress install потребуется снова (~200 МБ трафика)."


class PuppeteerCacheCleaner(_PathCacheCleaner):
    id = "puppeteer"
    name = "📦 Puppeteer cache"
    description = "%UserProfile%\\.cache\\puppeteer (браузеры Puppeteer)"
    paths = (USER / ".cache" / "puppeteer",)


class GradleCacheCleaner(_PathCacheCleaner):
    id = "gradle"
    name = "📦 Gradle caches"
    description = "%LocalAppData%\\gradle\\caches, %UserProfile%\\.gradle\\caches"
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    recommended = False
    paths = (
        LOCAL / "gradle" / "caches",
        USER / ".gradle" / "caches",
    )
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


class _EditorCacheCleaner(BaseCleaner):
    """Общая механика для VS Code и форков: кэши редактора + VSIX-хвосты."""

    group = GROUP_DEVTOOLS
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш редактора и временные .tgz; сами расширения и настройки не трогаем."
    loss = "Редактор запустится чуть медленнее; расширения сохранятся."

    # Подкаталоги в Roaming- и Local-базах данных редактора.
    _ROAMING_SUBS = (
        ("Cache",),
        ("CachedData",),
        ("Code Cache",),
        ("GPUCache",),
        ("Service Worker", "CacheStorage"),
        ("Service Worker", "ScriptCache"),
        ("CachedExtensionVSIXs",),
        ("logs",),
        ("CrashReports",),
    )
    _LOCAL_SUBS = (
        ("Cache",),
        ("CachedData",),
        ("Code Cache",),
        ("GPUCache",),
    )

    roaming_bases: tuple[Path, ...] = ()
    local_bases: tuple[Path, ...] = ()
    extensions_dirs: tuple[Path, ...] = ()

    def affected_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        for ext_dir in self.extensions_dirs:
            if ext_dir.exists():
                paths.extend(p for p in ext_dir.glob("_*.tgz") if p.is_file())
        for base in (*self.roaming_bases, *self.local_bases):
            subs = self._ROAMING_SUBS if base in self.roaming_bases else self._LOCAL_SUBS
            for sub in subs:
                p = base.joinpath(*sub)
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
        return ("OK", f"{self.name} очищен") if ok else ("ERR", "Ошибка")


class VSCodeCacheCleaner(_EditorCacheCleaner):
    id = "vscode_ext"
    name = "📝 VS Code Cache"
    description = "VS Code cache (Code Cache, Service Worker, logs) и недокачанные VSIX"
    roaming_bases = (ROAMING / "Code",)
    local_bases = (LOCAL / "Code",)
    extensions_dirs = (USER / ".vscode" / "extensions",)


class VSCodiumCacheCleaner(_EditorCacheCleaner):
    id = "vscodium_ext"
    name = "📝 VSCodium Cache"
    description = "VSCodium cache и недокачанные VSIX"
    roaming_bases = (ROAMING / "VSCodium",)
    local_bases = (LOCAL / "VSCodium",)
    extensions_dirs = (USER / ".vscodium" / "extensions",)


class CursorCacheCleaner(_EditorCacheCleaner):
    id = "cursor_ext"
    name = "📝 Cursor Cache"
    description = "Cursor cache и недокачанные VSIX"
    roaming_bases = (ROAMING / "Cursor",)
    local_bases = (LOCAL / "Cursor",)
    extensions_dirs = (USER / ".cursor" / "extensions",)


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


def _run_docker(args: list[str], timeout: int = 60) -> tuple[str, str]:
    """Выполнить команду docker CLI. Возвращает (stdout, stderr)."""
    if shutil.which("docker") is None:
        return "", "DOCKER_NOT_INSTALLED"
    try:
        r = subprocess.run(
            ["docker", *args],
            capture_output=True, text=True, errors="replace", timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return "", str(e)
    if r.returncode != 0:
        return r.stdout.strip(), r.stderr.strip() or f"exit {r.returncode}"
    return r.stdout.strip(), ""


def _parse_docker_size(text: str) -> int:
    """«1.02GB», «12.3MB», «85.9kB», «0B» -> байты."""
    multipliers = {"b": 1, "kb": 10**3, "mb": 10**6, "gb": 10**9, "tb": 10**12}
    s = text.strip().lower().replace(" ", "")
    num = ""
    while s and (s[0].isdigit() or s[0] == "."):
        num += s[0]
        s = s[1:]
    if not num:
        return 0
    try:
        value = float(num)
    except ValueError:
        return 0
    return int(value * multipliers.get(s, 1))


class DockerSystemCleaner(BaseCleaner):
    """docker system prune: остановленные контейнеры, висячие образы, кэш сборки.

    Нефайловая цель (affected_paths пуст): очистку выполняет сам docker CLI.
    """

    id = "docker"
    name = "🐳 Docker system prune"
    group = GROUP_DEVTOOLS
    description = "Остановленные контейнеры, неиспользуемые сети, висячие образы и кэш сборки"
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    recommended = False
    delete_mode = "remove"
    admin_required = False
    why = (
        "docker system prune -f удаляет остановленные контейнеры, неиспользуемые "
        "сети, висячие образы и кэш сборки (тома не трогаются)."
    )
    loss = "Остановленные контейнеры исчезнут; образы и кэш скачаются/соберутся заново."
    restore_hint = "docker pull <образ> или повторная сборка"

    # (время замера, размер, scan_error): daemon не опрашиваем чаще раза в 5 минут.
    _size_cache: tuple[float, int, str] | None = None
    _SIZE_TTL = 300.0

    def affected_paths(self) -> tuple[Path, ...]:
        return ()

    def get_size(self) -> int:
        cached = DockerSystemCleaner._size_cache
        if cached is not None and time.monotonic() - cached[0] < self._SIZE_TTL:
            self.scan_error = cached[2]
            return cached[1]

        self.scan_error = ""
        out, err = _run_docker(["info", "--format", "{{.ServerVersion}}"], timeout=20)
        if err:
            self.scan_error = "Docker не установлен или не запущен"
            result = 0
        else:
            out, _ = _run_docker(
                ["system", "df", "--format", "{{.Type}}\t{{.Reclaimable}}"],
                timeout=30,
            )
            # Reclaimable вида «1.02GB (52%)»: берём абсолютную часть до скобок.
            result = sum(
                _parse_docker_size(line.split("\t")[1].split(" (")[0])
                for line in out.splitlines()
                if "\t" in line
            )

        DockerSystemCleaner._size_cache = (time.monotonic(), result, self.scan_error)
        return result

    def clean(self) -> tuple[str, str]:
        DockerSystemCleaner._size_cache = None
        out, err = _run_docker(["info", "--format", "{{.ServerVersion}}"], timeout=20)
        if err:
            return ("ERR", "Docker не установлен или не запущен")
        out, err = _run_docker(["system", "prune", "-f"], timeout=300)
        if err:
            return ("ERR", f"docker system prune: {err.strip().splitlines()[-1]}")
        for line in out.splitlines():
            if "total reclaimed space:" in line.lower():
                return ("OK", f"Docker: освобождено {line.split(':', 1)[1].strip()}")
        return ("OK", "Docker prune выполнен")


class NuGetCacheCleaner(_PathCacheCleaner):
    id = "nuget"
    name = "📦 NuGet cache"
    description = "%LocalAppData%\\NuGet: v3-cache, http-cache, plugins-cache"
    paths = (
        LOCAL / "NuGet" / "v3-cache",
        LOCAL / "NuGet" / "http-cache",
        LOCAL / "NuGet" / "plugins-cache",
    )


class NuGetPackagesCleaner(_PathCacheCleaner):
    id = "nuget_packages"
    name = "📦 NuGet global packages"
    description = "%UserProfile%\\.nuget\\packages — глобальный кэш пакетов"
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    recommended = False
    paths = (USER / ".nuget" / "packages",)
    why = (
        "Глобальный кэш распакованных NuGet-пакетов; restore скачает их заново. "
        "Не выбран по умолчанию: после очистки сборки без сети невозможны."
    )
    loss = "dotnet restore / сборка скачает пакеты заново (крупный трафик)."


class MavenCacheCleaner(_PathCacheCleaner):
    id = "maven"
    name = "📦 Maven repository (~\\.m2)"
    description = "%UserProfile%\\.m2\\repository — артефакты скачаются заново"
    paths = (USER / ".m2" / "repository",)
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS


class CondaCacheCleaner(_PathCacheCleaner):
    id = "conda"
    name = "📦 Conda pkgs cache"
    description = "%UserProfile%\\.conda\\pkgs (кэш пакетов conda)"
    paths = (USER / ".conda" / "pkgs",)


DEVTOOLS_CLEANERS = [
    NPmCacheCleaner,
    PipCacheCleaner,
    YarnCacheCleaner,
    UvCacheCleaner,
    BunCacheCleaner,
    PnpmStoreCleaner,
    DenoCacheCleaner,
    PoetryCacheCleaner,
    PipxCacheCleaner,
    RustCacheCleaner,
    GoBuildCacheCleaner,
    GoModCacheCleaner,
    GradleCacheCleaner,
    PlaywrightBrowsersCleaner,
    CypressCacheCleaner,
    PuppeteerCacheCleaner,
    VSCodeCacheCleaner,
    VSCodiumCacheCleaner,
    CursorCacheCleaner,
    DockerSystemCleaner,
    NuGetCacheCleaner,
    NuGetPackagesCleaner,
    MavenCacheCleaner,
    CondaCacheCleaner,
]
