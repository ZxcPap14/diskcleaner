"""AppUninstaller — запуск штатного деинсталлятора и поиск остатков.

Остатки НИКОГДА не удаляются автоматически: сначала ``find_leftovers``
возвращает список кандидатов, пользователь подтверждает его в UI, и только
потом вызывается ``remove_leftovers``.
"""
from __future__ import annotations

import ctypes
import datetime
import os
import string
import subprocess
import winreg
from collections.abc import Callable
from pathlib import Path

from disk_cleaner_app.cleaners.base import get_dir_size
from disk_cleaner_app.services.batch_delete import delete_many

_DRIVE_FIXED = 3
# FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM — служебные каталоги тома.
_ATTR_SKIP = 0x6
_PORTABLE_SKIP_NAMES = {
    "$recycle.bin",
    "system volume information",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "users",
    "perflogs",
    "recovery",
    "documents and settings",
}
_FORBIDDEN_COMPONENTS = {
    "$recycle.bin",
    "system volume information",
    "windows",
}


def _drive_type(root: str) -> int:
    """Тип диска через GetDriveTypeW (3 — фиксированный)."""
    try:
        return int(
            ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
        )
    except Exception:
        return 0


class AppUninstaller:
    """Менеджер удаления программ и безопасной очистки остатков."""

    REG_KEYS = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    _HIVES = {
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
    }

    def __init__(
        self,
        appdata_roots: list[Path] | None = None,
        program_roots: list[Path] | None = None,
    ) -> None:
        home = Path.home()
        programdata = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        self._appdata_roots = appdata_roots or [
            home / "AppData" / "Local",
            home / "AppData" / "Roaming",
            home / "AppData" / "LocalLow",
            programdata,
        ]
        self._program_roots = program_roots or [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ]

    # ── установленные программы ─────────────────────────

    def get_installed(self) -> list[dict]:
        """Получить список установленных программ (все диски).

        Записи с одинаковым именем, но разными путями установки
        (например, одна программа на C: и на D:) не склеиваются.
        """
        apps: list[dict] = []

        for hkey, key_path in self.REG_KEYS:
            try:
                with winreg.OpenKey(hkey, key_path) as key:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            i += 1
                            app = self._read_app(hkey, key_path, subkey_name)
                            if app and app["name"]:
                                apps.append(app)
                        except OSError:
                            break
            except OSError:
                continue

        apps = self._dedupe_apps(apps)
        apps.sort(key=lambda x: x["name"].lower())
        return apps

    @staticmethod
    def _dedupe_apps(apps: list[dict]) -> list[dict]:
        """Убрать дубликаты реестра: имя + путь установки."""
        seen: set[str] = set()
        result: list[dict] = []
        for app in apps:
            name = str(app.get("name", "")).casefold()
            location = os.path.normcase(
                str(app.get("install_location", "") or "").strip().strip('"')
            )
            key = f"{name}|{location}" if location else name
            if key in seen:
                continue
            seen.add(key)
            result.append(app)
        return result

    def _read_app(self, hkey, key_path: str, subkey: str) -> dict | None:
        """Прочитать информацию о программе из подраздела реестра."""
        try:
            with winreg.OpenKey(hkey, f"{key_path}\\{subkey}") as sk:
                name = self._reg_get(sk, "DisplayName", "").strip()
                if not name:
                    return None

                uninstall = self._reg_get(sk, "UninstallString", "").strip()
                quiet = self._reg_get(sk, "QuietUninstallString", "").strip()
                version = self._reg_get(sk, "DisplayVersion", "").strip()
                publisher = self._reg_get(sk, "Publisher", "").strip()
                install_date = self._reg_get(sk, "InstallDate", "").strip()
                estimated_size = self._reg_get(sk, "EstimatedSize", "0")
                try:
                    size_kb = int(estimated_size)
                except ValueError:
                    size_kb = 0

                install_loc = self._reg_get(sk, "InstallLocation", "").strip()

                return {
                    "name": name,
                    "version": version,
                    "publisher": publisher,
                    "install_date": install_date,
                    "size_kb": size_kb,
                    "uninstall_string": uninstall,
                    "quiet_uninstall": quiet,
                    "install_location": install_loc,
                    "drive": self._drive_of(install_loc),
                    "registry_key": f"{key_path}\\{subkey}",
                    "uninstall_key": subkey,
                }
        except OSError:
            return None

    @staticmethod
    def _drive_of(install_location: str) -> str:
        """Буква диска из пути установки («C:») или пустая строка."""
        raw = str(install_location or "").strip().strip('"')
        if not raw:
            return ""
        drive = os.path.splitdrive(raw)[0]
        return drive.upper() if len(drive) == 2 and drive.endswith(":") else ""

    # ── диски и портативные программы ────────────────────

    def get_drives(self) -> list[str]:
        """Фиксированные диски в виде ['C:', 'D:']."""
        drives: list[str] = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            try:
                if not Path(root).exists():
                    continue
            except OSError:
                continue
            if _drive_type(root) == _DRIVE_FIXED:
                drives.append(f"{letter}:")
        return drives

    def get_portable(
        self,
        drives: list[str] | None = None,
        known_locations: list[str] | None = None,
        max_results: int = 300,
    ) -> list[dict]:
        """Найти портативные программы: каталоги верхнего уровня с .exe,
        у которых нет своей записи в реестре.

        Служебные и скрытые каталоги, а также каталоги, полностью покрытые
        зарегистрированными путями установки, пропускаются. Ничего не
        удаляет и не запускает.
        """
        if drives is None:
            drives = self.get_drives()
        known = {
            os.path.normcase(str(loc).strip().strip('"').rstrip("\\"))
            for loc in (known_locations or [])
            if str(loc).strip().strip('"')
        }

        portable: list[dict] = []
        for drive in drives:
            if len(portable) >= max_results:
                break
            root = drive if str(drive).endswith("\\") else f"{drive}\\"
            try:
                entries = sorted(
                    (e for e in os.scandir(root) if e.is_dir()),
                    key=lambda e: e.name.casefold(),
                )
            except OSError:
                continue
            for entry in entries:
                if len(portable) >= max_results:
                    break
                if self._skip_portable_dir(entry):
                    continue
                location = entry.path
                if os.path.normcase(location) in known:
                    continue
                exes = self._dir_exes(Path(location))
                if not exes:
                    continue
                if all(self._inside_known(exe, known) for exe in exes):
                    continue
                portable.append({
                    "name": entry.name,
                    "version": "",
                    "publisher": "",
                    "install_date": self._date_of_mtime(entry),
                    "size_kb": 0,
                    "uninstall_string": "",
                    "quiet_uninstall": "",
                    "install_location": location,
                    "drive": drive.upper()[:2],
                    "registry_key": "",
                    "uninstall_key": "",
                    "portable": True,
                })
        return portable

    @staticmethod
    def _skip_portable_dir(entry: os.DirEntry) -> bool:
        """Скрытые, системные и заведомо не-программные каталоги."""
        try:
            attrs = entry.stat().st_file_attributes
        except (OSError, AttributeError):
            return True
        if attrs & _ATTR_SKIP:
            return True
        return entry.name.casefold() in _PORTABLE_SKIP_NAMES

    @staticmethod
    def _dir_exes(path: Path, limit: int = 3) -> list[str]:
        """До ``limit`` .exe в каталоге; иначе — на один уровень ниже."""
        found: list[str] = []
        try:
            for entry in os.scandir(path):
                if entry.is_file() and entry.name.casefold().endswith(".exe"):
                    found.append(entry.path)
                    if len(found) >= limit:
                        return found
        except OSError:
            return found
        try:
            for entry in os.scandir(path):
                if not entry.is_dir():
                    continue
                try:
                    for nested in os.scandir(entry.path):
                        if nested.is_file() and nested.name.casefold().endswith(".exe"):
                            found.append(nested.path)
                            if len(found) >= limit:
                                return found
                except OSError:
                    continue
        except OSError:
            pass
        return found

    @staticmethod
    def _inside_known(exe: str, known: set[str]) -> bool:
        """Путь .exe лежит внутри зарегистрированного пути установки."""
        normalized = os.path.normcase(str(exe))
        for loc in known:
            if normalized.startswith(loc + os.sep) or normalized == loc:
                return True
        return False

    @staticmethod
    def _date_of_mtime(entry: os.DirEntry) -> str:
        """Дата каталога в формате реестра ГГГГММДД или пустая строка."""
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            return ""
        try:
            return datetime.date.fromtimestamp(mtime).strftime("%Y%m%d")
        except (OSError, OverflowError, ValueError):
            return ""

    def remove_portable(self, app: dict) -> list[str]:
        """Убрать папку портативной программы в корзину (обратимо)."""
        raw = str(app.get("install_location", "") or "").strip().strip('"')
        path = Path(raw) if raw else None
        if path is None or not self._is_safe_remove_target(path):
            return [f"⚠️  Отказ: небезопасный путь «{raw or '?'}» — папка не удалена."]
        batch = delete_many([str(path)], to_recycle=True)
        deleted = {os.path.normcase(str(p)) for p in batch["deleted"]}
        if os.path.normcase(str(path)) in deleted:
            return [f"🗑️  Папка перемещена в корзину: {path}"]
        return [f"❌ Не удалось удалить: {path}"]

    @classmethod
    def _is_safe_remove_target(cls, path: Path) -> bool:
        """Папку портативной программы можно убрать только целиком и неслужебную."""
        try:
            path = path.expanduser().absolute()
        except (OSError, ValueError):
            return False
        if not path.is_dir() or path.parent == path:
            return False
        if not cls._is_safe_target(path):
            return False
        for component in path.parts[1:]:
            if component.casefold() in _FORBIDDEN_COMPONENTS:
                return False
        return True

    def _reg_get(self, key, value: str, default: str = "") -> str:
        """Безопасно получить значение из реестра."""
        try:
            return winreg.QueryValueEx(key, value)[0]
        except OSError:
            return default

    # ── официальное удаление ────────────────────────────

    def uninstall(self, app: dict) -> list[str]:
        """Запустить штатный деинсталлятор. Остатки не трогает."""
        logs: list[str] = []
        uninst = app.get("quiet_uninstall", "") or app.get("uninstall_string", "")
        if not uninst:
            logs.append("⚠️  Штатный деинсталлятор не найден в реестре.")
            return logs

        logs.append(f"🔄 Запуск: {uninst[:120]}")
        try:
            result = subprocess.run(
                uninst,
                shell=True,
                timeout=900,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                logs.append("✅ Деинсталлятор завершён")
            else:
                logs.append(
                    f"⚠️  Деинсталлятор завершился с кодом {result.returncode}. "
                    "Возможно, требуется диалог или права администратора."
                )
        except subprocess.TimeoutExpired:
            logs.append("⚠️  Деинсталлятор превысил время ожидания (15 минут).")
        except OSError as e:
            logs.append(f"❌ Ошибка запуска: {e}")

        logs.append("ℹ️  Остатки не удалены автоматически — используйте «Найти остатки».")
        return logs

    # ── реальный размер и очередь ───────────────────────

    def install_size(self, app: dict) -> int | None:
        """Размер установочной папки, если ``InstallLocation`` известен.

        ``None`` означает «посчитать нельзя»: путь пуст, не существует,
        указывает на защищённый каталог или на корень тома.
        """
        raw = str(app.get("install_location", "") or "").strip().strip('"')
        if not raw:
            return None
        try:
            path = Path(raw).expanduser()
        except (OSError, ValueError):
            return None
        if not self._is_safe_target(path):
            return None
        try:
            if path.is_dir():
                return get_dir_size(path)
            return path.stat().st_size
        except OSError:
            return None

    def uninstall_many(
        self,
        apps: list[dict],
        on_log: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[str]:
        """Запустить деинсталляторы по очереди.

        ``on_log`` вызывается из текущего (рабочего) потока для каждой
        строки — UI обязан переключаться в свой поток сам. ``should_stop``
        проверяется перед следующей программой: текущий деинсталлятор
        не прерывается.
        """
        logs: list[str] = []
        total = len(apps)
        completed = 0

        def emit(line: str) -> None:
            logs.append(line)
            if on_log is not None:
                on_log(line)

        for index, app in enumerate(apps, 1):
            if should_stop is not None and should_stop():
                break
            name = str(app.get("name", "?"))
            emit(f"▶ [{index}/{total}] {name}")
            for line in self.uninstall(app):
                emit(line)
            completed += 1

        if completed < total:
            emit(f"⏹ Остановлено: выполнено {completed} из {total}.")
        elif total:
            emit(f"✅ Очередь завершена: {completed} программ.")
        return logs

    # ── поиск остатков (без удаления) ───────────────────

    def find_leftovers(self, app: dict, level: str = "safe") -> list[dict]:
        """Найти возможные остатки программы.

        level: "safe" — установочная папка + точные имена в AppData;
               "moderate" — плюс каталоги Program Files;
               "advanced" — плюс записи реестра.

        Возвращает кандидатов; ничего не удаляет.
        """
        app_name = str(app.get("name", "")).strip()
        publisher = str(app.get("publisher", "")).strip()
        if len(app_name) < 2:
            return []

        level = level.lower()
        candidates: list[dict] = []

        install_loc = str(app.get("install_location", "")).strip()
        if install_loc:
            path = Path(install_loc)
            if self._is_safe_target(path):
                candidates.append(self._candidate_path(path, "Установочная папка"))

        if level in ("safe", "moderate", "advanced"):
            candidates.extend(self._find_in_appdata(app_name, publisher))

        if level in ("moderate", "advanced"):
            candidates.extend(self._find_in_programs(app_name, publisher))

        if level == "advanced":
            candidates.extend(self._find_in_registry(app_name))

        return self._dedupe(candidates)

    def _find_in_appdata(self, app_name: str, publisher: str) -> list[dict]:
        candidates: list[dict] = []
        for base in self._appdata_roots:
            if not base.is_dir():
                continue
            direct = self._match_child(base, app_name)
            if direct is not None:
                candidates.append(self._candidate_path(direct, "Данные приложения"))
            if publisher:
                pub_dir = self._match_child(base, publisher)
                if pub_dir is not None:
                    nested = self._match_child(pub_dir, app_name)
                    if nested is not None:
                        candidates.append(self._candidate_path(nested, "Данные приложения"))
        return candidates

    def _find_in_programs(self, app_name: str, publisher: str) -> list[dict]:
        candidates: list[dict] = []
        for base in self._program_roots:
            if not base.is_dir():
                continue
            direct = self._match_child(base, app_name)
            if direct is not None:
                candidates.append(self._candidate_path(direct, "Program Files"))
            if publisher:
                pub_dir = self._match_child(base, publisher)
                if pub_dir is not None:
                    nested = self._match_child(pub_dir, app_name)
                    if nested is not None:
                        candidates.append(self._candidate_path(nested, "Program Files"))
        return candidates

    def _find_in_registry(self, app_name: str) -> list[dict]:
        candidates: list[dict] = []
        for hive_name, hkey in self._HIVES.items():
            for software_path in ("Software", r"SOFTWARE\WOW6432Node"):
                path = f"{software_path}\\{app_name}"
                try:
                    with winreg.OpenKey(hkey, path, 0, winreg.KEY_READ):
                        pass
                except OSError:
                    continue
                candidates.append({
                    "kind": "registry",
                    "path": f"{hive_name}\\{path}",
                    "label": "Раздел реестра",
                    "size": 0,
                    "hive": hive_name,
                    "reg_key": path,
                })
        return candidates

    @staticmethod
    def _match_child(base: Path, name: str) -> Path | None:
        """Найти дочерний элемент с точно таким же именем (без учёта регистра)."""
        target = name.strip().casefold()
        if len(target) < 2:
            return None
        try:
            for child in base.iterdir():
                if child.name.casefold() == target:
                    return child
        except OSError:
            return None
        return None

    def _candidate_path(self, path: Path, label: str) -> dict:
        try:
            size = get_dir_size(path) if path.is_dir() else path.stat().st_size
        except OSError:
            size = 0
        return {
            "kind": "dir" if path.is_dir() else "file",
            "path": str(path),
            "label": label,
            "size": size,
        }

    @staticmethod
    def _is_safe_target(path: Path) -> bool:
        """Разрешить удаление только вложенных, не системных путей."""
        try:
            path = path.expanduser().absolute()
        except (OSError, ValueError):
            return False
        if not path.exists():
            return False
        if path.parent == path:
            return False

        protected = {
            Path(os.environ.get("SystemRoot", r"C:\Windows")),
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")),
            Path.home(),
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / "Downloads",
        }
        normalized = {os.path.normcase(str(p)) for p in protected}
        if os.path.normcase(str(path)) in normalized:
            return False

        # Внутри C:\Windows удалять нельзя ничего.
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        try:
            if path.is_relative_to(windows):
                return False
        except ValueError:
            pass
        return True

    def _dedupe(self, candidates: list[dict]) -> list[dict]:
        seen: set[str] = set()
        result: list[dict] = []
        for candidate in candidates:
            key = os.path.normcase(str(candidate.get("path", "")))
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        result.sort(key=lambda c: (c.get("kind") != "registry", str(c.get("path", "")).lower()))
        return result

    # ── удаление подтверждённых остатков ────────────────

    def remove_leftovers(self, leftovers: list[dict]) -> list[str]:
        """Удалить только переданные (уже подтверждённые) кандидаты.

        Файловые остатки удаляются одним пакетным вызовом оболочки,
        разделы реестра — по одному (пустые ключи).
        """
        logs: list[str] = []
        paths: list[Path] = []

        for item in leftovers:
            if item.get("kind") == "registry":
                continue
            path = Path(str(item.get("path", "")))
            if not self._is_safe_target(path):
                logs.append(f"  ⚠️  Пропущено (небезопасный путь): {path}")
                continue
            paths.append(path)

        if paths:
            batch = delete_many([str(p) for p in paths], to_recycle=False)
            removed = {os.path.normcase(str(p)) for p in batch["deleted"]}
            for path in paths:
                if os.path.normcase(str(path)) in removed:
                    logs.append(f"  🗑️  Удалено: {path}")
                else:
                    logs.append(f"  ❌ Не удалось удалить: {path}")

        for item in leftovers:
            if item.get("kind") == "registry":
                logs.append(self._remove_registry(item))

        return logs

    def _remove_registry(self, item: dict) -> str:
        hive_name = str(item.get("hive", ""))
        reg_key = str(item.get("reg_key", ""))
        hkey = self._HIVES.get(hive_name)
        if hkey is None or not reg_key:
            return f"  ⚠️  Пропущен раздел реестра: {item.get('path', '?')}"
        try:
            winreg.DeleteKey(hkey, reg_key)
            return f"  🗑️  Реестр: {item.get('path')}"
        except OSError:
            return (
                f"  ⚠️  Раздел не пуст или нет прав: {item.get('path')} "
                "(удалите вручную через regedit)"
            )
