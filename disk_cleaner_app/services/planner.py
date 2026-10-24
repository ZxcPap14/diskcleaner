"""Планировщик глубокой очистки.

План — это список конкретных путей (или команд) с размерами и томами.
Он строится до удаления, проверяется на пересечения и защищённые пути,
а затем передаётся в ``CleanEngine``.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    get_dir_size,
    get_path_size,
    is_junction,
    scan_cancelled,
)
from disk_cleaner_app.cleaners.safety import is_dangerous_target
from disk_cleaner_app.models.target import LAYER_SAFE
from disk_cleaner_app.services import elevation

SYSTEM_DRIVE = (os.environ.get("SystemDrive", "C:") + "\\").upper()

# Верхняя граница числа действий одной цели: защита от дерева на миллион файлов.
MAX_ACTIONS = 200_000


def _key(path: Path) -> str:
    return os.path.normcase(str(path))


def volume_root(path: Path | str | None) -> str:
    """Корень тома для пути: ``C:\\``, ``D:\\`` или UNC-шара."""
    if path is None:
        return SYSTEM_DRIVE
    try:
        drive, _ = os.path.splitdrive(os.path.abspath(str(path)))
    except (OSError, ValueError):
        return SYSTEM_DRIVE
    if not drive:
        return SYSTEM_DRIVE
    if drive.startswith("\\\\"):
        return drive
    return drive.upper() + "\\"


def _cutoff(min_age_hours: int) -> float | None:
    if min_age_hours <= 0:
        return None
    return time.time() - min_age_hours * 3600


def _age_ok(path: Path, cutoff: float | None) -> bool:
    if cutoff is None:
        return True
    try:
        return path.stat().st_mtime <= cutoff
    except OSError:
        return False


def _walk_files(root: Path, cutoff: float | None):
    """Обойти файлы, не заходя в junction/symlink."""
    stack = [root]
    while stack:
        if scan_cancelled():
            return
        current = stack.pop()
        try:
            with os.scandir(str(current)) as it:
                entries = list(it)
        except (OSError, PermissionError):
            continue
        for entry in entries:
            if scan_cancelled():
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    child = Path(entry.path)
                    if child.is_symlink() or is_junction(child):
                        continue
                    stack.append(child)
                elif entry.is_file(follow_symlinks=False):
                    if cutoff is not None and entry.stat().st_mtime > cutoff:
                        continue
                    yield Path(entry.path)
            except (OSError, PermissionError):
                continue


def _iter_children(root: Path):
    """Прямые потомки папки; ссылки возвращаются как ссылки."""
    try:
        with os.scandir(str(root)) as it:
            entries = list(it)
    except (OSError, PermissionError):
        return
    for entry in entries:
        try:
            yield Path(entry.path)
        except OSError:
            continue


@dataclass(frozen=True)
class PlannedAction:
    """Одно действие плана."""

    target_id: str
    path: Path | None
    bytes: int
    volume: str
    action: str                 # "path" | "command"
    mtime: float = 0.0
    is_dir: bool = False
    reason: str = ""


@dataclass
class TargetPlan:
    """План одной цели."""

    cleaner: BaseCleaner
    actions: list[PlannedAction] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    mode: str = "command"       # "paths" | "command"
    planned_bytes: int = 0
    volumes: set[str] = field(default_factory=set)
    blocked: str = ""           # причина, по которой цель нельзя выполнить
    truncated: bool = False     # список действий ограничен сверху

    @property
    def target_id(self) -> str:
        return self.cleaner.id

    @property
    def requires_admin(self) -> bool:
        return bool(getattr(self.cleaner, "admin_required", False))

    @property
    def layer(self) -> str:
        return getattr(self.cleaner, "layer", LAYER_SAFE)

    def recalculate(self) -> None:
        self.planned_bytes = sum(a.bytes for a in self.actions)
        self.volumes = {a.volume for a in self.actions}


@dataclass
class OperationPlan:
    """Полный план операции."""

    targets: list[TargetPlan]
    warnings: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def total_bytes(self) -> int:
        return sum(t.planned_bytes for t in self.targets)

    @property
    def total_by_layer(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for target in self.targets:
            result[target.layer] = result.get(target.layer, 0) + target.planned_bytes
        return result

    @property
    def total_by_volume(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for target in self.targets:
            for action in target.actions:
                result[action.volume] = result.get(action.volume, 0) + action.bytes
        return result

    @property
    def requires_admin(self) -> bool:
        return any(t.requires_admin for t in self.targets)

    @property
    def action_count(self) -> int:
        return sum(len(t.actions) for t in self.targets)


class Planner:
    """Строит ``OperationPlan`` из выбранных очистителей."""

    def build(self, cleaners: list[BaseCleaner]) -> OperationPlan:
        plans = [self._plan_cleaner(c) for c in cleaners]
        self._resolve_overlaps(plans)
        self._collect_warnings(plans)
        return OperationPlan(targets=plans)

    # ── одна цель ─────────────────────────────────────

    def _plan_cleaner(self, cleaner: BaseCleaner) -> TargetPlan:
        paths = tuple(cleaner.affected_paths())
        if not paths:
            try:
                size = max(0, int(cleaner.get_size()))
            except Exception:
                size = max(0, int(getattr(cleaner, "size", 0) or 0))
            action = PlannedAction(
                target_id=cleaner.id,
                path=None,
                bytes=size,
                volume=SYSTEM_DRIVE,
                action="command",
                reason=getattr(cleaner, "why", "") or "системная операция",
            )
            plan = TargetPlan(
                cleaner=cleaner,
                actions=[action],
                mode="command",
                planned_bytes=size,
                volumes={SYSTEM_DRIVE},
            )
            return plan

        plan = TargetPlan(cleaner=cleaner, mode="paths")
        mode = getattr(cleaner, "delete_mode", "contents")
        cutoff = _cutoff(int(getattr(cleaner, "min_age_hours", 0) or 0))

        for raw in paths:
            if scan_cancelled():
                plan.skipped.append("сканирование отменено")
                break
            path = Path(os.path.abspath(str(raw)))
            if not os.path.lexists(str(path)):
                plan.skipped.append(f"нет пути: {path}")
                continue
            if is_dangerous_target(path):
                plan.skipped.append(f"защищённый путь: {path}")
                continue

            try:
                is_link = path.is_symlink() or is_junction(path)
            except OSError:
                is_link = False

            if is_link:
                plan.actions.append(PlannedAction(
                    target_id=cleaner.id,
                    path=path,
                    bytes=0,
                    volume=volume_root(path),
                    action="path",
                    reason="ссылка/junction: удаляется только сама ссылка",
                ))
                continue

            if path.is_file():
                if _age_ok(path, cutoff):
                    plan.actions.append(PlannedAction(
                        target_id=cleaner.id,
                        path=path,
                        bytes=get_path_size(path),
                        volume=volume_root(path),
                        action="path",
                        mtime=path.stat().st_mtime,
                        reason=_why(cleaner),
                    ))
                else:
                    plan.skipped.append(f"слишком новый файл: {path}")
                continue

            if not path.is_dir():
                plan.skipped.append(f"не файл и не папка: {path}")
                continue

            if mode == "remove":
                if not _age_ok(path, cutoff):
                    plan.skipped.append(f"слишком новая папка: {path}")
                    continue
                plan.actions.append(PlannedAction(
                    target_id=cleaner.id,
                    path=path,
                    bytes=get_dir_size(path),
                    volume=volume_root(path),
                    action="path",
                    mtime=_mtime(path),
                    is_dir=True,
                    reason=_why(cleaner),
                ))
                continue

            # contents: папку сохраняем, удаляем её содержимое.
            if cutoff is not None:
                for file_path in _walk_files(path, cutoff):
                    if len(plan.actions) >= MAX_ACTIONS:
                        plan.truncated = True
                        break
                    plan.actions.append(PlannedAction(
                        target_id=cleaner.id,
                        path=file_path,
                        bytes=get_path_size(file_path),
                        volume=volume_root(file_path),
                        action="path",
                        mtime=_mtime(file_path),
                        reason=_why(cleaner),
                    ))
            else:
                for child in _iter_children(path):
                    if len(plan.actions) >= MAX_ACTIONS:
                        plan.truncated = True
                        break
                    if is_dangerous_target(child):
                        plan.skipped.append(f"защищённый путь: {child}")
                        continue
                    is_child_link = False
                    try:
                        is_child_link = child.is_symlink() or is_junction(child)
                    except OSError:
                        pass
                    plan.actions.append(PlannedAction(
                        target_id=cleaner.id,
                        path=child,
                        bytes=0 if is_child_link else get_path_size(child),
                        volume=volume_root(child),
                        action="path",
                        mtime=_mtime(child),
                        is_dir=bool(child.is_dir() and not is_child_link),
                        reason=_why(cleaner),
                    ))

        plan.recalculate()
        return plan

    # ── пересечения ───────────────────────────────────

    def _resolve_overlaps(self, plans: list[TargetPlan]) -> None:
        items: list[tuple[int, PlannedAction]] = []
        for index, target in enumerate(plans):
            for action in target.actions:
                if action.path is not None:
                    items.append((index, action))

        # Сначала более короткие (родительские) пути, затем порядок целей.
        items.sort(key=lambda item: (len(str(item[1].path).split(os.sep)), item[0]))

        # normcase(path) -> принятое действие. Проверка пересечения — подъём
        # по родителям пути, а не сравнение со всеми принятыми (иначе план
        # на сотни тысяч файлов считался бы квадратично).
        kept: dict[str, PlannedAction] = {}
        dropped: dict[int, list[str]] = {}

        for index, action in items:
            path = action.path
            assert path is not None
            conflict = self._covering_action(path, kept)
            if conflict is not None:
                dropped.setdefault(index, []).append(
                    f"пересекается с «{conflict.target_id}»: {path}"
                )
                continue
            kept[_key(path)] = action

        kept_keys = {(key, action.target_id) for key, action in kept.items()}
        for index, target in enumerate(plans):
            if target.mode != "paths":
                continue
            target.actions = [
                a for a in target.actions
                if a.path is not None and (_key(a.path), a.target_id) in kept_keys
            ]
            target.skipped.extend(dropped.get(index, []))
            target.recalculate()

    @staticmethod
    def _covering_action(
        path: Path, kept: dict[str, PlannedAction]
    ) -> PlannedAction | None:
        """Принятое действие, покрывающее путь (сам путь или один из родителей)."""
        current = path
        while True:
            action = kept.get(_key(current))
            if action is not None:
                return action
            parent = current.parent
            if parent == current:
                return None
            current = parent

    # ── предупреждения ────────────────────────────────

    def _collect_warnings(self, plans: list[TargetPlan]) -> None:
        for target in plans:
            if target.actions and target.requires_admin and not elevation.is_admin():
                target.blocked = "Требуются права администратора."
            if not target.actions:
                target.skipped.append("нечего очищать")
            if target.truncated:
                target.skipped.append(
                    "слишком много файлов: обработана только часть, повторите очистку"
                )


def _why(cleaner: BaseCleaner) -> str:
    return getattr(cleaner, "why", "") or "временные данные, которые пересоздаются"


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
