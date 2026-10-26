"""BaseCleaner — абстрактный класс для всех целей очистки."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

# ── Опции операции очистки ─────────────────────────────

@dataclass(frozen=True)
class CleanOptions:
    """Параметры, которые применяются ко всем очистителям в рамках одной операции."""

    to_recycle: bool = False
    safe_mode: bool = True


_DEFAULT_OPTIONS = CleanOptions()
_CURRENT_OPTIONS: ContextVar[CleanOptions] = ContextVar(
    "disk_cleaner_options", default=_DEFAULT_OPTIONS
)


def set_clean_options(options: CleanOptions):
    """Установить опции для текущего потока. Возвращает токен для reset."""
    return _CURRENT_OPTIONS.set(options)


def reset_clean_options(token) -> None:
    _CURRENT_OPTIONS.reset(token)


def current_clean_options() -> CleanOptions:
    return _CURRENT_OPTIONS.get()


# ── Отмена сканирования ────────────────────────────────

_SCAN_CANCEL: ContextVar[threading.Event | None] = ContextVar(
    "disk_cleaner_scan_cancel", default=None
)


def set_scan_cancel(event: threading.Event):
    """Привязать событие отмены к текущему потоку сканирования."""
    return _SCAN_CANCEL.set(event)


def reset_scan_cancel(token) -> None:
    _SCAN_CANCEL.reset(token)


def scan_cancelled() -> bool:
    event = _SCAN_CANCEL.get()
    return bool(event is not None and event.is_set())


class BaseCleaner(ABC):
    """Одна цель очистки: знает как посчитать размер и как очистить."""

    # ── поля, переопределяемые в наследниках ──
    id: str = ""
    name: str = ""
    group: str = ""
    description: str = ""
    safety: str = "🟢"
    can_preview: bool = False
    preview_path: str | None = None

    # ── метаданные глубокой очистки ──
    layer: str = "A"
    min_age_hours: int = 0
    admin_required: bool = False
    recommended: bool = True
    why: str = ""
    loss: str = ""
    restore_hint: str = ""
    paths: tuple[Path, ...] = ()
    delete_mode: str = "contents"   # contents | remove

    def __init__(self) -> None:
        self._size: int = 0
        self._scanned: bool = False
        self.scan_error: str = ""

    @abstractmethod
    def get_size(self) -> int:
        """Посчитать занимаемое место в байтах."""
        ...

    @abstractmethod
    def clean(self) -> tuple[str, str]:
        """Очистить. Возвращает (статус, детали)."""
        ...

    def preview(self) -> list[dict]:
        """Вернуть список файлов для предпросмотра (опционально)."""
        return []

    def affected_paths(self) -> tuple[Path, ...]:
        """Пути, которые цель реально затрагивает.

        Пустой кортеж означает «цель не файловая»: движок вызовет ``clean()``
        (службы, корзина, DISM, DNS и т. п.).
        """
        return tuple(self.paths)

    @property
    def is_path_target(self) -> bool:
        return bool(self.affected_paths())

    @property
    def size(self) -> int:
        return self._size

    @size.setter
    def size(self, v: int) -> None:
        self._size = v

    @property
    def scanned(self) -> bool:
        return self._scanned

    @scanned.setter
    def scanned(self, v: bool) -> None:
        self._scanned = v

    @property
    def is_actionable(self) -> bool:
        """Можно ли запускать очистку, даже если размер равен нулю.

        Например, сброс DNS-кэша не освобождает место, но является полезным действием.
        """
        return True

    def to_item(self):
        """Конвертировать в CleanupItem для GUI."""
        from disk_cleaner_app.models.item import CleanupItem
        return CleanupItem(
            id=self.id,
            name=self.name,
            group=self.group,
            description=self.description,
            safety=self.safety,
            get_size=self.get_size,
            clean=self.clean,
            size=self._size,
            scanned=self._scanned,
            can_preview=self.can_preview,
            preview_path=self.preview_path,
        )


# ── Вспомогательные функции ────────────────────────────

def _resolve_to_recycle(to_recycle: bool | None) -> bool:
    """Явное значение имеет приоритет, иначе берём опции текущей операции."""
    if to_recycle is None:
        return current_clean_options().to_recycle
    return bool(to_recycle)


def is_junction(path: Path) -> bool:
    """Является ли путь junction/reparse point (Windows)."""
    try:
        checker = getattr(path, "is_junction", None)
        if checker is not None:
            return bool(checker())
        return False
    except OSError:
        return False


def get_dir_size(path: Path) -> int:
    """Рекурсивный подсчёт размера папки (без перехода по junction/symlink).

    Прерывается, если в текущем потоке запрошена отмена сканирования.
    """
    total = 0
    try:
        with os.scandir(str(path)) as it:
            for e in it:
                if scan_cancelled():
                    return total
                try:
                    if e.is_dir(follow_symlinks=False):
                        child = Path(e.path)
                        # Не идём внутрь junction/symlink: иначе можно
                        # посчитать (и позже удалить) чужие файлы.
                        if child.is_symlink() or is_junction(child):
                            continue
                        total += get_dir_size(child)
                    elif e.is_file(follow_symlinks=False):
                        total += e.stat().st_size
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return total


def get_file_size(path: Path) -> int:
    """Размер одного файла."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def get_path_size(path: Path) -> int:
    """Размер файла или папки. Ссылки и junction не разворачиваются."""
    try:
        if path.is_symlink() or is_junction(path):
            return 0
        if path.is_dir():
            return get_dir_size(path)
        return path.stat().st_size
    except OSError:
        return 0


def _on_rm_error(func, path, exc) -> None:
    """Снять атрибут «только чтение» и повторить удаление."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def safe_rmtree(path: Path, to_recycle: bool | None = None) -> bool:
    """Удалить папку (в корзину или навсегда).

    ``None`` означает «взять значение из текущих CleanOptions».
    Возвращает True только если путь действительно исчез.
    """
    path = Path(path)
    if not os.path.lexists(str(path)):
        return True

    # Ссылки и junction удаляем как ссылку — никогда не идём внутрь.
    if path.is_symlink() or is_junction(path):
        try:
            if path.is_symlink():
                os.unlink(str(path))
            else:
                os.rmdir(str(path))
            return not os.path.lexists(str(path))
        except OSError:
            return False

    use_recycle = _resolve_to_recycle(to_recycle)
    if use_recycle:
        if not _send_to_recycle(path):
            return False
        return not os.path.lexists(str(path))

    try:
        shutil.rmtree(str(path), onexc=_on_rm_error)
    except OSError:
        # Частично удалённую папку считаем неудачей.
        return not os.path.lexists(str(path))
    return not os.path.lexists(str(path))


def safe_rm_contents(path: Path, to_recycle: bool | None = None) -> bool:
    """Очистить содержимое папки (саму папку оставить)."""
    path = Path(path)
    if not os.path.lexists(str(path)):
        return True

    use_recycle = _resolve_to_recycle(to_recycle)
    ok = True

    try:
        with os.scandir(str(path)) as it:
            entries = list(it)
    except OSError:
        return False

    for entry in entries:
        child = Path(entry.path)
        try:
            if is_junction(child):
                os.rmdir(str(child))
            elif entry.is_symlink():
                os.unlink(str(child))
            elif entry.is_dir(follow_symlinks=False):
                if not safe_rmtree(child, use_recycle):
                    ok = False
            else:
                if use_recycle:
                    if not _send_to_recycle(child):
                        ok = False
                else:
                    try:
                        os.unlink(str(child))
                    except PermissionError:
                        # Read-only файл: снимаем атрибут и пробуем ещё раз.
                        try:
                            os.chmod(str(child), stat.S_IWRITE)
                            os.unlink(str(child))
                        except OSError:
                            ok = False
                    except OSError:
                        ok = False
        except OSError:
            ok = False
    return ok


def safe_rm_contents_aged(
    path: Path, min_age_hours: int, to_recycle: bool | None = None
) -> bool:
    """Очистить содержимое папки, трогая только файлы старше ``min_age_hours``.

    Возрастное обещание цели (``min_age_hours``) должно работать и при прямом
    вызове ``clean()`` — как при планировании. Свежие файлы и структура папок
    остаются на месте; junction/symlink не разворачиваются и не удаляются.
    """
    path = Path(path)
    if not os.path.lexists(str(path)):
        return True

    cutoff = time.time() - max(0, int(min_age_hours)) * 3600
    use_recycle = _resolve_to_recycle(to_recycle)

    targets: list[str] = []
    stack = [path]
    while stack and not scan_cancelled():
        current = stack.pop()
        try:
            with os.scandir(str(current)) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            if scan_cancelled():
                break
            child = Path(entry.path)
            try:
                if child.is_symlink() or is_junction(child):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(child)
                elif entry.stat().st_mtime <= cutoff:
                    targets.append(str(child))
            except OSError:
                continue

    if not targets:
        return True

    if not use_recycle:
        ok = True
        for target in targets:
            try:
                os.unlink(target)
            except PermissionError:
                try:
                    os.chmod(target, stat.S_IWRITE)
                    os.unlink(target)
                except OSError:
                    ok = False
            except OSError:
                ok = False
        return ok

    # Корзина — пакетно, одной операцией на пачку путей.
    from disk_cleaner_app.services.batch_delete import delete_many

    ok = True
    for start in range(0, len(targets), 2000):
        if scan_cancelled():
            return False
        chunk = targets[start:start + 2000]
        result = delete_many(chunk, to_recycle=True)
        if result.get("failed"):
            ok = False
    return ok


def newest_mtime(path: Path) -> float | None:
    """Самый свежий mtime файла внутри каталога (junction не разворачиваются).

    ``None`` — папку не удалось прочитать целиком: состояние неизвестно,
    вызывающий код обязан считать такую папку «свежей» и не удалять.
    """
    newest: float | None = None
    stack = [Path(path)]
    while stack:
        if scan_cancelled():
            return None
        current = stack.pop()
        try:
            with os.scandir(str(current)) as it:
                entries = list(it)
        except (OSError, PermissionError):
            return None
        for entry in entries:
            if scan_cancelled():
                return None
            try:
                if entry.is_dir(follow_symlinks=False):
                    child = Path(entry.path)
                    if child.is_symlink() or is_junction(child):
                        continue
                    stack.append(child)
                elif entry.is_file(follow_symlinks=False):
                    mtime = entry.stat().st_mtime
                    newest = mtime if newest is None else max(newest, mtime)
            except (OSError, PermissionError):
                continue
    return newest if newest is not None else 0.0


def _ps_quote(value: str) -> str:
    """Безопасно заключить строку в одинарные кавычки PowerShell."""
    return "'" + str(value).replace("'", "''") + "'"


def _wait_until_gone(path: str, timeout: float = 5.0) -> bool:
    """Подождать, пока путь исчезнет (корзина перемещает файлы асинхронно)."""
    deadline = time.monotonic() + timeout
    while True:
        if not os.path.lexists(path):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _send_to_recycle(path: Path) -> bool:
    """Отправить файл/папку в корзину через Shell.Application.

    Возвращает True только если путь исчез с исходного места.
    """
    abs_path = str(Path(path).absolute())
    ps = (
        "$ErrorActionPreference = 'Stop'; "
        "$shell = New-Object -ComObject Shell.Application; "
        f"$item = $shell.Namespace(0).ParseName({_ps_quote(abs_path)}); "
        "if ($item) { $item.InvokeVerb('delete') } else { exit 2 }"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    if r.returncode != 0:
        return False
    return _wait_until_gone(abs_path)


def safe_remove(path: Path, to_recycle: bool | None = None) -> bool:
    """Удалить файл, ссылку или папку, соблюдая политику корзины."""
    path = Path(path)
    if not os.path.lexists(str(path)):
        return True

    if path.is_symlink() or is_junction(path):
        try:
            if path.is_symlink():
                os.unlink(str(path))
            else:
                os.rmdir(str(path))
            return not os.path.lexists(str(path))
        except OSError:
            return False

    if path.is_dir():
        return safe_rmtree(path, to_recycle)

    if _resolve_to_recycle(to_recycle):
        return _send_to_recycle(path)

    try:
        os.unlink(str(path))
        return True
    except OSError:
        return False


def run_powershell(script: str, timeout: int = 60) -> tuple[str, str]:
    """Выполнить PowerShell скрипт, вернуть (stdout, stderr)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, errors="replace", timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT"
    except Exception as e:
        return "", str(e)


def run_cmd(command: str, timeout: int = 60) -> tuple[str, str]:
    """Выполнить cmd команду."""
    try:
        r = subprocess.run(
            ["cmd", "/c", command],
            capture_output=True, text=True, errors="replace", timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return "", str(e)


def get_disk_free(root: str | None = None) -> tuple[int, int]:
    """Вернуть (free_bytes, total_bytes) для диска.

    ``root`` — корень вида ``D:\\``; по умолчанию системный диск.
    """
    root = root or (os.environ.get("SystemDrive", "C:") + "\\")
    try:
        import ctypes
        free = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            root, None, ctypes.byref(total), ctypes.byref(free),
        )
        return free.value, total.value
    except Exception:
        return 0, 0


def list_drives() -> list[tuple[str, int, int]]:
    """Готовые диски: [(корень, свободно, всего)].

    Пустые приводы (CD/DVD, отключённые диски) отбрасываются.
    """
    roots: list[str] = []
    try:
        roots = list(os.listdrives())  # Python 3.12+, Windows
    except (AttributeError, OSError):
        roots = []

    if not roots:
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            roots = [
                f"{chr(ord('A') + i)}:\\"
                for i in range(26) if mask & (1 << i)
            ]
        except Exception:
            roots = []

    if not roots:
        roots = [os.environ.get("SystemDrive", "C:") + "\\"]

    drives: list[tuple[str, int, int]] = []
    for root in roots:
        free, total = get_disk_free(root)
        if total > 0:
            drives.append((root, free, total))

    system = os.path.normcase(os.environ.get("SystemDrive", "C:") + "\\")
    drives.sort(key=lambda item: os.path.normcase(item[0]) != system)
    return drives
