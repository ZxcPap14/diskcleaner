"""ConfigManager — чтение/запись config.json в %APPDATA%/DiskCleaner."""
from __future__ import annotations

import datetime
import json
import os
import uuid
from pathlib import Path

from disk_cleaner_app.cleaners.safety import is_protected_path, validate_custom_path
from disk_cleaner_app.models.item import SafetyLevel

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "DiskCleaner"
CONFIG_FILE = CONFIG_DIR / "config.json"
CUSTOM_RULES_FILE = CONFIG_DIR / "custom_rules.json"

# Версия формата экспорта: позволяет менять структуру без «тихого» импорта.
EXPORT_SCHEMA = 1

DEFAULT_CONFIG: dict = {
    "safe_mode": True,
    # Кэши удаляются безвозвратно: корзина не освобождает место до её очистки.
    "to_recycle": False,
    "theme": "dark",
    "last_scan": None,
    # owner/repo на GitHub или прямой адрес JSON-манифеста (см. services/updater.py).
    "update_source": "ZxcPap14/diskcleaner",
}

_VALID_THEMES = ("dark", "light", "system")
_VALID_SAFETY = (SafetyLevel.SAFE, SafetyLevel.CAUTION, SafetyLevel.ADVANCED)


def _atomic_write_json(path: Path, payload) -> None:
    """Записать JSON через временный файл (без «полузаписанного» конфига)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _valid_config_value(key: str, value) -> bool:
    """Проверить тип значения настройки перед импортом."""
    if key in ("safe_mode", "to_recycle"):
        return isinstance(value, bool)
    if key == "theme":
        return value in _VALID_THEMES
    if key == "last_scan":
        return value is None or isinstance(value, str)
    return key in DEFAULT_CONFIG


class ConfigManager:
    """Управление конфигурацией приложения."""

    def __init__(self) -> None:
        self._data: dict = {}
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.load()

    # ── config ────────────────────────────────────────────

    def load(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        # Валидный JSON может оказаться не объектом (массив, строка) —
        # это повреждённый конфиг, работаем с настройками по умолчанию.
        if not isinstance(self._data, dict):
            self._data = {}
        for k, v in DEFAULT_CONFIG.items():
            self._data.setdefault(k, v)
        return self._data

    def save(self) -> None:
        """Атомарная запись, чтобы не потерять конфиг при сбое."""
        _atomic_write_json(CONFIG_FILE, self._data)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

    # ── экспорт/импорт ────────────────────────────────────

    def export_config(self, path: str | Path) -> Path:
        """Сохранить настройки и правила в один JSON-файл.

        Файл пишется атомарно; путь назначения выбирает пользователь.
        """
        target = Path(path)
        if target.suffix.lower() != ".json":
            target = target.with_suffix(".json")
        payload = {
            "app": "DiskCleaner",
            "schema": EXPORT_SCHEMA,
            "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "config": {k: self._data.get(k, v) for k, v in DEFAULT_CONFIG.items()},
            "custom_rules": self.load_custom_rules(),
        }
        _atomic_write_json(target, payload)
        return target

    def import_config(
        self,
        path: str | Path,
        merge: bool = True,
    ) -> dict:
        """Загрузить настройки и правила из файла экспорта.

        ``merge=True`` добавляет правила к существующим (дубликаты по пути
        пропускаются), ``merge=False`` заменяет список правил целиком.
        Неизвестные/небезопасные значения пропускаются, а не ломают импорт.

        Возвращает ``{"config": int, "rules": int, "skipped": [str]}``.
        """
        source = Path(path)
        try:
            with open(source, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"Не удалось прочитать файл: {e}") from e

        if not isinstance(payload, dict):
            raise ValueError("Файл не похож на экспорт DiskCleaner.")

        schema = payload.get("schema")
        if schema is not None and not isinstance(schema, int):
            raise ValueError("Некорректная версия формата экспорта.")
        if isinstance(schema, int) and schema > EXPORT_SCHEMA:
            raise ValueError(
                "Файл создан более новой версией DiskCleaner "
                f"(schema {schema} > {EXPORT_SCHEMA})."
            )

        raw_config = payload.get("config", {})
        if not isinstance(raw_config, dict):
            raise ValueError("Раздел «config» повреждён.")
        raw_rules = payload.get("custom_rules", [])
        if not isinstance(raw_rules, list):
            raise ValueError("Раздел «custom_rules» повреждён.")
        if not raw_config and not raw_rules:
            raise ValueError("В файле нет настроек или правил.")

        skipped: list[str] = []
        applied = 0
        for key, value in raw_config.items():
            if key not in DEFAULT_CONFIG or not _valid_config_value(key, value):
                skipped.append(f"Настройка «{key}»: недопустимое значение")
                continue
            self._data[key] = value
            applied += 1

        existing = self.load_custom_rules() if merge else []
        seen = {
            (os.path.normcase(str(r.get("path", ""))), str(r.get("name", "")))
            for r in existing
        }
        used_ids = {str(r.get("id", "")) for r in existing}
        added = 0

        for index, rule in enumerate(raw_rules):
            if not isinstance(rule, dict):
                skipped.append(f"Правило #{index + 1}: не объект")
                continue

            name = str(rule.get("name", "")).strip()
            path_value = str(rule.get("path", "")).strip()
            if not name or not path_value:
                skipped.append(f"Правило #{index + 1}: нет названия или пути")
                continue
            # Наличие пути не требуется: импорт возможен на другой машине.
            if is_protected_path(path_value):
                skipped.append(f"Правило «{name}»: защищённый путь")
                continue

            key = (os.path.normcase(str(Path(path_value).expanduser())), name)
            if key in seen:
                skipped.append(f"Правило «{name}»: уже существует")
                continue
            seen.add(key)

            rule_id = str(rule.get("id", "")).strip()
            if not rule_id or rule_id in used_ids:
                rule_id = f"custom_{uuid.uuid4().hex[:12]}"
            used_ids.add(rule_id)

            safety = rule.get("safety", SafetyLevel.CAUTION)
            if safety not in _VALID_SAFETY:
                safety = SafetyLevel.CAUTION

            existing.append({
                "id": rule_id,
                "name": name,
                "path": str(Path(path_value).expanduser()),
                "safety": safety,
            })
            added += 1

        self.save()
        self.save_custom_rules(existing)
        return {"config": applied, "rules": added, "skipped": skipped}

    # ── custom rules ─────────────────────────────────────

    def load_custom_rules(self) -> list[dict]:
        if CUSTOM_RULES_FILE.exists():
            try:
                with open(CUSTOM_RULES_FILE, encoding="utf-8") as f:
                    rules = json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
            if isinstance(rules, list):
                return [r for r in rules if isinstance(r, dict)]
        return []

    def save_custom_rules(self, rules: list[dict]) -> None:
        _atomic_write_json(CUSTOM_RULES_FILE, rules)

    def add_custom_rule(self, name: str, path: str, safety: str = "🟡") -> str:
        """Добавить правило. Бросает ValueError для недопустимого пути."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Укажите название правила.")

        error = validate_custom_path(path)
        if error:
            raise ValueError(error)

        rules = self.load_custom_rules()
        rid = f"custom_{uuid.uuid4().hex[:12]}"
        rules.append({
            "id": rid,
            "name": name,
            "path": str(Path(path).expanduser()),
            "safety": safety,
        })
        self.save_custom_rules(rules)
        return rid

    def remove_custom_rule(self, rule_id: str) -> None:
        rules = [r for r in self.load_custom_rules() if r.get("id") != rule_id]
        self.save_custom_rules(rules)

    def update_custom_rule(
        self,
        rule_id: str,
        name: str,
        path: str,
        safety: str = SafetyLevel.CAUTION,
    ) -> None:
        """Изменить существующее правило. Бросает ValueError как add."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Укажите название правила.")

        error = validate_custom_path(path)
        if error:
            raise ValueError(error)
        if safety not in _VALID_SAFETY:
            safety = SafetyLevel.CAUTION

        rules = self.load_custom_rules()
        for rule in rules:
            if rule.get("id") == rule_id:
                rule["name"] = name
                rule["path"] = str(Path(path).expanduser())
                rule["safety"] = safety
                break
        else:
            raise ValueError("Правило не найдено — возможно, оно уже удалено.")
        self.save_custom_rules(rules)
