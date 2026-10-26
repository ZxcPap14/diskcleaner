"""Защита от удаления критических путей.

Используется для пользовательских правил и любых путей, которые вводит человек.
Встроенные очистители работают по доверенным путям и этот модуль не используют,
однако общие проверки (корень диска, системные каталоги) полезны всем.
"""
from __future__ import annotations

import os
from pathlib import Path

# Каталоги, которые нельзя удалять и внутри которых нельзя создавать правила.
_PROTECTED_SYSTEM = (
    Path(os.environ.get("SystemRoot", r"C:\Windows")),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    Path(os.environ.get("ProgramData", r"C:\ProgramData")),
)

# Личные папки: запрещено удалять саму папку, но можно её отдельные подпапки.
_PROTECTED_USER = tuple(
    Path.home() / name
    for name in (
        "Desktop", "Documents", "Downloads", "Pictures",
        "Music", "Videos", "OneDrive", ".ssh", ".config",
    )
)

# Подпапки системных каталогов, которые очистители используют штатно.
# Это исключения из запрета «внутри Windows/ProgramData ничего не трогать».
_SAFE_SYSTEM_SUBDIRS = (
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Prefetch",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Minidump",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "MEMORY.DMP",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "LiveKernelReports",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Logs" / "CBS",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Logs" / "DISM",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Panther",
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SoftwareDistribution" / "Download",
    (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "ServiceProfiles" / "NetworkService" / "AppData" / "Local"
        / "Microsoft" / "Windows" / "DeliveryOptimization" / "Cache"
    ),
    Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    / "Microsoft" / "Windows" / "WER",
)


def _strip_win_tail(path: str) -> str:
    """Убрать хвостовые точки и пробелы из компонентов пути.

    Win32 сам отбрасывает их при разборе («C:\\Windows » — это
    «C:\\Windows»), поэтому защита путей обязана делать то же самое,
    иначе запрет обходится добавлением точки в конец.
    """
    parts = path.split("\\")
    fixed = []
    for part in parts:
        is_drive = len(part) == 2 and part[1] == ":"
        if part and not is_drive:
            part = part.rstrip(". ")
        fixed.append(part)
    return "\\".join(fixed)


def _long_form(path: Path) -> Path:
    """Развернуть 8.3-компоненты пути (C:\\PROGRA~1) в длинные имена.

    normcase не сопоставляет «PROGRA~1» и «Program Files», поэтому без
    разворота защита обходится короткой записью. GetLongPathNameW требует
    существующий путь — для несуществующего возвращаем как есть. Вызов
    делаем только для путей с «~»: иначе это лишний системный вызов на
    каждый путь плана (до 200 000).
    """
    text = str(path)
    if "~" not in text:
        return path
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(1024)
        length = ctypes.windll.kernel32.GetLongPathNameW(text, buf, len(buf))
        if 0 < length < len(buf):
            return Path(buf.value)
    except Exception:
        pass
    return path


def _norm(path: str | Path) -> Path:
    """Нормализовать путь без обращения к диску (8.3 — с обращением)."""
    try:
        p = Path(path).expanduser().absolute()
    except (OSError, ValueError):
        p = Path(str(path))
    p = _long_form(p)
    text = os.path.normpath(_strip_win_tail(str(p)))
    return Path(os.path.normcase(text))


def _is_ancestor_or_same(candidate: Path, root: Path) -> bool:
    """True, если candidate == root или является его родителем."""
    try:
        return candidate == root or root.is_relative_to(candidate)
    except ValueError:
        return False


def _is_within(candidate: Path, root: Path) -> bool:
    """True, если candidate == root или лежит внутри root."""
    try:
        return candidate == root or candidate.is_relative_to(root)
    except ValueError:
        return False


def is_protected_path(path: str | Path) -> bool:
    """Запрещён ли путь для удаления целиком.

    Запрещены: корни дисков, системные каталоги (и всё внутри них),
    домашний каталог и его родители, а также сами личные папки пользователя.
    Подпапки личных папок разрешены — их можно указывать в правилах.
    """
    if path is None or not str(path).strip():
        return True

    p = _norm(path)

    # Корень диска (C:\, D:\).
    if p.parent == p:
        return True

    # Нельзя удалять сам домашний каталог или что-то выше него.
    try:
        home = _norm(Path.home())
        if _is_ancestor_or_same(p, home):
            return True
    except (OSError, ValueError):
        pass

    for root in _PROTECTED_SYSTEM:
        root_n = _norm(root)
        # Сам системный каталог, его родители и всё содержимое.
        if _is_ancestor_or_same(p, root_n) or _is_within(p, root_n):
            return True

    for root in _PROTECTED_USER:
        if _is_ancestor_or_same(p, _norm(root)):
            return True

    return False


def is_dangerous_target(path: str | Path) -> bool:
    """Запрещён ли путь как *цель удаления* для встроенного очистителя.

    Отличается от :func:`is_protected_path` тем, что разрешает известные
    безопасные подпапки Windows (Temp, Prefetch, SoftwareDistribution\\Download
    и т. п.), но по-прежнему запрещает корни, домашний каталог,
    Program Files и весь остальной Windows/ProgramData.
    """
    if path is None or not str(path).strip():
        return True

    p = _norm(path)

    if p.parent == p:
        return True

    try:
        home = _norm(Path.home())
        if p == home or home.is_relative_to(p):
            return True
    except (OSError, ValueError):
        pass

    # Сами личные папки удалять нельзя; их подпапки — можно (custom rules).
    if any(p == _norm(root) for root in _PROTECTED_USER):
        return True

    for safe in _SAFE_SYSTEM_SUBDIRS:
        if _is_within(p, _norm(safe)):
            return False

    for root in _PROTECTED_SYSTEM:
        root_n = _norm(root)
        if _is_ancestor_or_same(p, root_n) or _is_within(p, root_n):
            return True

    return False


def validate_custom_path(path: str | Path) -> str:
    """Проверить путь пользовательского правила.

    Возвращает пустую строку, если путь допустим, иначе — текст ошибки.
    """
    raw = str(path or "").strip()
    if not raw:
        return "Путь не указан."

    expanded = Path(raw).expanduser()
    try:
        exists = expanded.exists()
    except OSError:
        exists = False
    if not exists:
        return f"Путь не существует: {raw}"
    if not (expanded.is_dir() or expanded.is_file()):
        return f"Путь не является файлом или папкой: {raw}"
    if is_protected_path(expanded):
        return "Этот путь защищён: удаление запрещено."
    return ""


def is_whitelisted(path: str | Path, entries: list[str] | tuple[str, ...]) -> bool:
    """Попадает ли путь в белый список («никогда не удалять»).

    Запись белого списка защищает сам путь и всё его содержимое.
    """
    if not entries:
        return False
    target = _norm(path)
    for entry in entries:
        text = str(entry).strip()
        if not text:
            continue
        if _is_within(target, _norm(text)):
            return True
    return False
