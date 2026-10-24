"""StartupManager — безопасное управление автозагрузкой (реестр + Startup).

Отключение записи реестра не удаляет её безвозвратно: команда, тип и имя
сохраняются в ``startup_backup.json`` и могут быть восстановлены кнопкой
«Включить». Для папки Startup файл переименовывается в ``*.disabled``.
"""
from __future__ import annotations

import base64
import json
import os
import time
import winreg
from pathlib import Path
from typing import cast

from disk_cleaner_app.models.config import CONFIG_DIR

STARTUP_EXTENSIONS = (".lnk", ".url", ".bat", ".cmd", ".vbs", ".ps1", ".exe")

# Типы, значение которых нельзя восстановить из строки command.
_NON_STRING_TYPES = (
    winreg.REG_BINARY,
    winreg.REG_DWORD,
    winreg.REG_DWORD_BIG_ENDIAN,
    winreg.REG_MULTI_SZ,
    winreg.REG_QWORD,
)


def encode_reg_value(value: object) -> object:
    """Привести значение реестра к JSON-совместимому виду."""
    if isinstance(value, bytes):
        return {"b64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (list, int, str)) or value is None:
        return value
    return str(value)


def decode_reg_value(raw: object, value_type: int) -> object:
    """Восстановить значение из резервной копии по типу."""
    if isinstance(raw, dict) and "b64" in raw:
        try:
            return base64.b64decode(str(raw["b64"]))
        except (ValueError, TypeError):
            return b""
    if value_type == winreg.REG_BINARY and isinstance(raw, str):
        return raw.encode("utf-8")
    return raw

# (корень, подраздел, отображаемое имя источника)
RUN_KEYS = (
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
        "HKLM (32-bit)",
    ),
)

_HIVES = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKLM (32-bit)": winreg.HKEY_LOCAL_MACHINE,
}


class StartupManager:
    """Чтение, отключение и восстановление записей автозагрузки."""

    def __init__(
        self,
        startup_folder: Path | None = None,
        backup_file: Path | None = None,
    ) -> None:
        appdata = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        self._startup_folder = startup_folder or (
            appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        )
        self._backup_file = backup_file or (CONFIG_DIR / "startup_backup.json")
        self.last_error = ""

    # ── чтение ───────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """Все записи автозагрузки, включая отключённые."""
        items = self._read_registry() + self._read_startup_folder()
        items.extend(self._read_disabled_registry(items))

        seen: set[str] = set()
        unique: list[dict] = []
        for item in items:
            item_id = str(item.get("id", ""))
            if item_id and item_id not in seen:
                seen.add(item_id)
                unique.append(item)
        unique.sort(key=lambda i: (not i.get("enabled", False), i.get("name", "").lower()))
        return unique

    def _read_registry(self) -> list[dict]:
        items: list[dict] = []
        for hkey, subkey, source in RUN_KEYS:
            try:
                with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ) as key:
                    index = 0
                    while True:
                        try:
                            name, value, value_type = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        index += 1
                        if not name:
                            continue
                        items.append({
                            "id": f"reg:{source}:{name}",
                            "name": name,
                            "command": str(value),
                            "source": source,
                            "enabled": True,
                            "kind": "registry",
                            "hive": source,
                            "reg_key": subkey,
                            "reg_name": name,
                            "value_type": value_type,
                        })
            except OSError:
                # Нет доступа к HKLM без прав администратора — не ошибка чтения.
                continue
        return items

    def _read_startup_folder(self) -> list[dict]:
        items: list[dict] = []
        if not self._startup_folder.exists():
            return items

        try:
            entries = list(self._startup_folder.iterdir())
        except OSError:
            return items

        for entry in entries:
            try:
                if not entry.is_file():
                    continue
            except OSError:
                continue

            if entry.name.lower().endswith(".disabled"):
                original_name = entry.name[: -len(".disabled")]
                if not self._is_startup_file(original_name):
                    continue
                original = entry.with_name(original_name)
                if original.exists():
                    # Есть и активный, и отключённый файл — активный важнее.
                    continue
                items.append({
                    "id": f"file:{original}",
                    "name": original.stem,
                    "command": str(original),
                    "source": "Папка Startup",
                    "enabled": False,
                    "kind": "startup_folder",
                    "path": str(original),
                    "disabled_path": str(entry),
                })
            elif self._is_startup_file(entry.name):
                items.append({
                    "id": f"file:{entry}",
                    "name": entry.stem,
                    "command": str(entry),
                    "source": "Папка Startup",
                    "enabled": True,
                    "kind": "startup_folder",
                    "path": str(entry),
                })
        return items

    @staticmethod
    def _is_startup_file(name: str) -> bool:
        return Path(name).suffix.lower() in STARTUP_EXTENSIONS

    def _read_disabled_registry(self, current: list[dict]) -> list[dict]:
        """Добавить записи из резервной копии, которых нет в реестре."""
        active_ids = {item.get("id") for item in current}
        disabled: list[dict] = []
        for entry in self._load_backup():
            item_id = str(entry.get("id", ""))
            if not item_id or item_id in active_ids:
                continue
            disabled.append({
                "id": item_id,
                "name": entry.get("name", "?"),
                "command": entry.get("command", ""),
                "source": entry.get("hive", "?"),
                "enabled": False,
                "kind": "registry",
                "hive": entry.get("hive", ""),
                "reg_key": entry.get("reg_key", ""),
                "reg_name": entry.get("reg_name", ""),
                "value_type": entry.get("value_type", winreg.REG_SZ),
                "backup_id": item_id,
            })
        return disabled

    # ── отключение / включение ───────────────────────────

    def disable_item(self, item: dict) -> bool:
        """Отключить запись с сохранением возможности восстановления."""
        self.last_error = ""
        if not item.get("enabled", True):
            return True

        kind = item.get("kind")
        if kind == "startup_folder":
            return self._disable_startup_file(item)
        if kind == "registry":
            return self._disable_registry(item)

        self.last_error = "Неизвестный тип записи."
        return False

    def enable_item(self, item: dict) -> bool:
        """Включить ранее отключённую запись."""
        self.last_error = ""
        if item.get("enabled", False):
            return True

        kind = item.get("kind")
        if kind == "startup_folder":
            return self._enable_startup_file(item)
        if kind == "registry":
            return self._enable_registry(item)

        self.last_error = "Неизвестный тип записи."
        return False

    def _disable_startup_file(self, item: dict) -> bool:
        path = Path(item.get("path", ""))
        disabled = path.with_name(path.name + ".disabled")
        if disabled.exists() and not path.exists():
            return True
        if not path.is_file():
            self.last_error = "Файл автозагрузки не найден."
            return False

        if path == disabled or disabled.exists():
            self.last_error = "Резервная копия уже существует."
            return False

        try:
            path.rename(disabled)
        except OSError as e:
            self.last_error = f"Не удалось переименовать файл: {e}"
            return False
        return True

    def _enable_startup_file(self, item: dict) -> bool:
        path = Path(item.get("path", ""))
        disabled_value = item.get("disabled_path", "")
        disabled = Path(disabled_value) if disabled_value else path.with_name(
            path.name + ".disabled"
        )

        if path.exists():
            return True
        if not disabled.exists():
            self.last_error = "Резервная копия файла не найдена."
            return False
        if path.name.lower().endswith(".disabled"):
            self.last_error = "Некорректное имя файла."
            return False

        try:
            disabled.rename(path)
        except OSError as e:
            self.last_error = f"Не удалось восстановить файл: {e}"
            return False
        return True

    def _disable_registry(self, item: dict) -> bool:
        hive_name = item.get("hive", "")
        reg_key = item.get("reg_key", "")
        reg_name = item.get("reg_name", "")
        hkey = _HIVES.get(hive_name)
        if hkey is None or not reg_key or not reg_name:
            self.last_error = "Некорректная запись реестра."
            return False

        try:
            value, value_type = self._read_value(hkey, reg_key, reg_name)
        except OSError as e:
            self.last_error = f"Не удалось прочитать запись: {e}"
            return False

        entry = {
            "id": item.get("id", f"reg:{hive_name}:{reg_name}"),
            "name": reg_name,
            "command": str(value),
            # Исходное значение с типом: str(value) портит REG_BINARY и
            # REG_MULTI_SZ, и восстановление становится невозможным.
            "value_raw": encode_reg_value(value),
            "hive": hive_name,
            "reg_key": reg_key,
            "reg_name": reg_name,
            "value_type": value_type,
            "disabled_at": int(time.time()),
        }

        # Сначала сохраняем копию, только потом удаляем значение.
        backup = self._load_backup()
        backup = [e for e in backup if e.get("id") != entry["id"]]
        backup.append(entry)
        if not self._save_backup(backup):
            self.last_error = "Не удалось сохранить резервную копию."
            return False

        try:
            with winreg.OpenKey(hkey, reg_key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, reg_name)
        except OSError as e:
            self._remove_from_backup(entry["id"])
            self.last_error = (
                "Не удалось удалить запись (нужны права администратора)." if hive_name != "HKCU"
                else f"Не удалось удалить запись: {e}"
            )
            return False

        if self._value_exists(hkey, reg_key, reg_name):
            self.last_error = "Запись всё ещё присутствует в реестре."
            return False
        return True

    def _enable_registry(self, item: dict) -> bool:
        entry = self._find_backup(str(item.get("id", "")))
        if entry is None:
            entry = self._find_backup(
                f"reg:{item.get('hive', '')}:{item.get('reg_name', '')}"
            )
        if entry is None:
            self.last_error = "Резервная копия записи не найдена."
            return False

        hive_name = entry.get("hive", "")
        hkey = _HIVES.get(hive_name)
        reg_key = entry.get("reg_key", "")
        reg_name = entry.get("reg_name", "")
        if hkey is None or not reg_key or not reg_name:
            self.last_error = "Повреждена резервная копия записи."
            return False

        if self._value_exists(hkey, reg_key, reg_name):
            self._remove_from_backup(entry["id"])
            return True

        value_type = int(entry.get("value_type", winreg.REG_SZ))
        raw = entry.get("value_raw")
        if raw is None:
            # Старая резервная копия без исходного значения: строку command
            # нельзя записать как бинарный тип — сохраняем хотя бы как REG_SZ.
            value = entry.get("command", "")
            if value_type in _NON_STRING_TYPES:
                value_type = winreg.REG_SZ
        else:
            value = decode_reg_value(raw, value_type)
        # Тип значения определяется во время выполнения (из бэкапа),
        # поэтому для mypy приводим его к допустимому объединению.
        typed_value = cast("int | str | list[str] | bytes", value)
        try:
            with winreg.CreateKeyEx(hkey, reg_key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, reg_name, 0, value_type, typed_value)
        except (OSError, TypeError, ValueError) as e:
            self.last_error = (
                "Для восстановления нужны права администратора." if hive_name != "HKCU"
                else f"Не удалось восстановить запись: {e}"
            )
            return False

        if not self._value_exists(hkey, reg_key, reg_name):
            self.last_error = "Запись не появилась в реестре после восстановления."
            return False

        self._remove_from_backup(entry["id"])
        return True

    # ── добавление ───────────────────────────────────────

    def add_item(self, name: str, command: str) -> bool:
        """Добавить запись в HKCU Run с проверкой результата."""
        self.last_error = ""
        name = (name or "").strip()
        command = (command or "").strip()
        if not name or not command:
            self.last_error = "Укажите название и команду."
            return False

        subkey = RUN_KEYS[0][1]
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        except OSError as e:
            self.last_error = f"Не удалось добавить запись: {e}"
            return False
        return self._value_exists(winreg.HKEY_CURRENT_USER, subkey, name)

    # ── резервные копии ──────────────────────────────────

    def _load_backup(self) -> list[dict]:
        if not self._backup_file.exists():
            return []
        try:
            data = json.loads(self._backup_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [entry for entry in data if isinstance(entry, dict)]

    def _save_backup(self, entries: list[dict]) -> bool:
        try:
            self._backup_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._backup_file.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._backup_file)
            return True
        except OSError:
            return False

    def _find_backup(self, entry_id: str) -> dict | None:
        for entry in self._load_backup():
            if entry.get("id") == entry_id:
                return entry
        return None

    def _remove_from_backup(self, entry_id: str) -> None:
        backup = [e for e in self._load_backup() if e.get("id") != entry_id]
        self._save_backup(backup)

    # ── winreg helpers ───────────────────────────────────

    @staticmethod
    def _read_value(hkey, reg_key: str, reg_name: str) -> tuple[object, int]:
        with winreg.OpenKey(hkey, reg_key, 0, winreg.KEY_READ) as key:
            return winreg.QueryValueEx(key, reg_name)

    @staticmethod
    def _value_exists(hkey, reg_key: str, reg_name: str) -> bool:
        try:
            StartupManager._read_value(hkey, reg_key, reg_name)
            return True
        except OSError:
            return False
