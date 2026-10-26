"""📜 JSON-цели очистки: новые очистители без релиза.

Два источника декларативных целей:
- встроенный список (константа ``BUILTIN_TARGETS_JSON``) — то, что раньше
  требовало релиза;
- пользовательский файл ``%APPDATA%\\DiskCleaner\\custom_targets.json`` —
  правится без пересборки, реестр подхватывает его при следующем скане.

Поддерживаются только файловые цели (paths): команды, WMI и API остаются
в коде, потому что там нужен настоящий Python. Каждая цель проходит
валидацию схемы и защиту путей (``is_dangerous_target``): корни дисков,
Windows, Program Files и домашний каталог в JSON указать нельзя.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    get_path_size,
    safe_remove,
    safe_rm_contents,
    safe_rm_contents_aged,
)
from disk_cleaner_app.cleaners.safety import is_dangerous_target
from disk_cleaner_app.models.item import (
    GROUP_AIML,
    GROUP_APPS,
    GROUP_BROWSERS,
    GROUP_DEVTOOLS,
    GROUP_SYSTEM,
    SafetyLevel,
)
from disk_cleaner_app.models.target import (
    LAYER_COMPONENTS,
    LAYER_LEFTOVERS,
    LAYER_SAFE,
    LAYER_SYSTEM,
)

log = logging.getLogger(__name__)

USER_TARGETS_FILENAME = "custom_targets.json"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,63}$")

_GROUPS = {
    "system": GROUP_SYSTEM,
    "browsers": GROUP_BROWSERS,
    "apps": GROUP_APPS,
    "devtools": GROUP_DEVTOOLS,
    "aiml": GROUP_AIML,
}
_LAYERS = {LAYER_SAFE, LAYER_SYSTEM, LAYER_COMPONENTS, LAYER_LEFTOVERS}
_SAFETIES = {
    "safe": SafetyLevel.SAFE,
    "caution": SafetyLevel.CAUTION,
    "advanced": SafetyLevel.ADVANCED,
}
_DELETE_MODES = {"contents", "remove"}

# Встроенный набор. Уровень A/B/C; цели здесь — не замена кодовым, а
# способ добавить новую папку между релизами.
BUILTIN_TARGETS_JSON = """
{
  "version": 1,
  "targets": [
    {
      "id": "onedrive_logs",
      "name": "☁️ Логи OneDrive",
      "group": "system",
      "layer": "A",
      "safety": "safe",
      "paths": ["%LOCALAPPDATA%\\\\Microsoft\\\\OneDrive\\\\logs"],
      "delete_mode": "contents",
      "min_age_hours": 0,
      "admin_required": false,
      "recommended": true,
      "why": "Диагностические логи клиента OneDrive; синхронизация их не использует.",
      "loss": "Практически незаметно: логи создаются заново."
    },
    {
      "id": "steam_dumps",
      "name": "🎮 Дампы Steam",
      "group": "apps",
      "layer": "A",
      "safety": "safe",
      "paths": ["%LOCALAPPDATA%\\\\Steam\\\\dumps"],
      "delete_mode": "contents",
      "min_age_hours": 0,
      "admin_required": false,
      "recommended": true,
      "why": "Крэш-дампы клиента Steam; игры и сохранения не затрагиваются.",
      "loss": "Дампы падений не отправить в поддержку Steam — обычно они и не нужны."
    },
    {
      "id": "qbittorrent_logs",
      "name": "🌀 Логи qBittorrent",
      "group": "apps",
      "layer": "A",
      "safety": "safe",
      "paths": [
        "%LOCALAPPDATA%\\\\qBittorrent\\\\logs",
        "%APPDATA%\\\\qBittorrent\\\\logs"
      ],
      "delete_mode": "contents",
      "min_age_hours": 0,
      "admin_required": false,
      "recommended": true,
      "why": "Текстовые логи клиента qBittorrent; раздачи и настройки не затрагиваются.",
      "loss": "История событий клиента в текстовом виде пропадёт — обычно она не нужна."
    }
  ]
}
"""


# ── валидация схемы ──────────────────────────────────────


def validate_target(spec: Any) -> list[str]:
    """Ошибки декларации цели; пустой список — декларация валидна."""
    if not isinstance(spec, dict):
        return ["цель должна быть объектом"]
    errors: list[str] = []

    target_id = str(spec.get("id") or "")
    if not _ID_RE.match(target_id):
        errors.append(f"id «{target_id}»: нужен шаблон a-z0-9_, 3–64 символов")

    if not str(spec.get("name") or "").strip():
        errors.append("name не указан")

    group = str(spec.get("group") or "")
    if group not in _GROUPS:
        errors.append(f"group «{group}»: разрешены {', '.join(_GROUPS)}")

    layer = str(spec.get("layer") or "")
    if layer not in _LAYERS:
        errors.append(f"layer «{layer}»: разрешены {', '.join(sorted(_LAYERS))}")

    safety = str(spec.get("safety") or "")
    if safety not in _SAFETIES:
        errors.append(f"safety «{safety}»: разрешены {', '.join(_SAFETIES)}")

    paths = spec.get("paths")
    if not isinstance(paths, list) or not paths:
        errors.append("paths: нужен непустой список строк")
    else:
        for raw in paths:
            if not isinstance(raw, str) or not raw.strip():
                errors.append("paths: пустой или нестроковый путь")
                continue
            resolved = expand_target_path(raw)
            if is_dangerous_target(resolved):
                errors.append(f"путь защищён и запрещён в JSON: {raw}")

    mode = str(spec.get("delete_mode") or "contents")
    if mode not in _DELETE_MODES:
        errors.append(f"delete_mode «{mode}»: разрешены contents, remove")

    if not str(spec.get("why") or "").strip():
        errors.append("why не указан — цель обязана объяснять себя")
    if not str(spec.get("loss") or "").strip():
        errors.append("loss не указан — цель обязана предупреждать")

    min_age = spec.get("min_age_hours", 0)
    if not isinstance(min_age, int) or isinstance(min_age, bool) or min_age < 0:
        errors.append("min_age_hours: целое число ≥ 0")

    return errors


def expand_target_path(raw: str) -> Path:
    """Развернуть %ENV% и ~ в пути цели."""
    text = str(raw).strip().strip('"')
    try:
        return Path(os.path.expandvars(text)).expanduser()
    except (OSError, ValueError):
        return Path(text)


def parse_targets_json(raw: str) -> list[dict]:
    """Разобрать JSON-документ; битый документ → пустой список с логом."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("JSON-цели не разобраны: %s", e)
        return []
    if not isinstance(payload, dict):
        return []
    targets = payload.get("targets")
    if not isinstance(targets, list):
        return []
    return [item for item in targets if isinstance(item, dict)]


# ── очиститель из декларации ─────────────────────────────


def make_target_cleaner(spec: dict) -> BaseCleaner | None:
    """Собрать BaseCleaner из валидной декларации (или None)."""
    if validate_target(spec):
        return None

    paths = tuple(
        p for p in (expand_target_path(str(raw)) for raw in spec["paths"])
        if p.exists()
    )
    if not paths:
        return None

    min_age = int(spec.get("min_age_hours", 0) or 0)
    resolved_mode = str(spec.get("delete_mode") or "contents")
    spec_paths = paths
    spec_age = min_age

    class JsonTargetCleaner(BaseCleaner):
        id = str(spec["id"])
        name = str(spec["name"])
        group = _GROUPS[str(spec["group"])]
        description = " · ".join(str(p) for p in paths)
        safety = _SAFETIES[str(spec["safety"])]
        layer = str(spec["layer"])
        min_age_hours = min_age
        admin_required = bool(spec.get("admin_required", False))
        recommended = bool(spec.get("recommended", True))
        why = str(spec["why"])
        loss = str(spec["loss"])
        restore_hint = str(spec.get("restore_hint") or "")
        delete_mode = resolved_mode
        can_preview = True
        preview_path = str(spec_paths[0])

        def affected_paths(self) -> tuple[Path, ...]:
            return spec_paths

        def get_size(self) -> int:
            return sum(get_path_size(p) for p in spec_paths)

        def clean(self) -> tuple[str, str]:
            ok = True
            for path in spec_paths:
                if resolved_mode == "remove":
                    if not safe_remove(path, to_recycle=False):
                        ok = False
                elif spec_age > 0:
                    if not safe_rm_contents_aged(path, spec_age, to_recycle=False):
                        ok = False
                elif not safe_rm_contents(path, to_recycle=False):
                    ok = False
            label = self.name.split("]", 1)[-1].strip() or self.id
            return ("OK", f"{label}: очищено") if ok else (
                "ERR", f"{self.id}: часть файлов занята или нет прав"
            )

    cleaner = JsonTargetCleaner()
    cleaner._size = cleaner.get_size()
    cleaner._scanned = True
    return cleaner


def _user_targets_path() -> Path:
    from disk_cleaner_app.models.config import CONFIG_DIR

    return CONFIG_DIR / USER_TARGETS_FILENAME


def load_json_targets(user_path: Path | None = None) -> list[BaseCleaner]:
    """Встроенные + пользовательские цели; невалидные пропускаются с логом.

    id пользовательского файла имеет приоритет: он позволяет заменить
    встроенную декларацию, а не задвоить её.
    """
    cleaners: list[BaseCleaner] = []
    seen: set[str] = set()

    sources: list[tuple[str, list[dict]]] = [
        ("builtin", parse_targets_json(BUILTIN_TARGETS_JSON)),
    ]
    path = user_path or _user_targets_path()
    try:
        if path.is_file():
            sources.append((str(path), parse_targets_json(path.read_text(encoding="utf-8"))))
    except OSError:
        log.warning("Не удалось прочитать %s", path, exc_info=True)

    for source, specs in sources:
        for spec in specs:
            spec_id = str(spec.get("id") or "")
            errors = validate_target(spec)
            if errors:
                log.warning(
                    "JSON-цель из %s пропущена (%s): %s",
                    source, spec_id or "?", "; ".join(errors),
                )
                continue
            if spec_id in seen:
                log.info("JSON-цель %s уже загружена — пропущена (%s)", spec_id, source)
                continue
            cleaner = make_target_cleaner(spec)
            if cleaner is None:
                # Валидна, но ни один путь не существует — это нормально.
                continue
            seen.add(spec_id)
            cleaners.append(cleaner)
    return cleaners
