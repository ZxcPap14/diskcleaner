"""CleanEngine — безопасное удаление выбранных целей по плану."""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    CleanOptions,
    get_disk_free,
    reset_clean_options,
    scan_cancelled,
    set_clean_options,
)
from disk_cleaner_app.models.config import ConfigManager
from disk_cleaner_app.models.item import format_bytes
from disk_cleaner_app.models.target import LAYER_LEFTOVERS
from disk_cleaner_app.services.batch_delete import delete_many
from disk_cleaner_app.services.planner import (
    OperationPlan,
    Planner,
    TargetPlan,
    volume_root,
)

SYSTEM_DRIVE = (os.environ.get("SystemDrive", "C:") + "\\").upper()

# Размер пачки: между пачками можно отменить операцию.
DELETE_CHUNK = 2_000


@dataclass
class CleanResult:
    """Результат одной операции очистки."""

    cleaner: BaseCleaner
    status: str  # "OK" | "ERR" | "SKIP"
    detail: str
    planned: int = 0          # сколько планировали освободить
    freed: int = 0            # реальное изменение свободного места
    remaining: int = 0        # сколько осталось после очистки
    note: str = ""            # предупреждение/пояснение
    recycled: bool = False

    # ── детализация глубокой очистки ──
    removed: int = 0          # сумма размеров подтверждённо удалённых объектов
    volume_delta: int = 0     # сумма дельт по затронутым томам
    volume_deltas: dict[str, int] = field(default_factory=dict)
    volumes: tuple[str, ...] = ()
    confidence: str = "high"  # high | estimate
    errors: list[str] = field(default_factory=list)


def _config_whitelist() -> list[str]:
    """Белый список путей из настроек (list[str]; некорректное — пусто)."""
    try:
        raw = ConfigManager().get("whitelist", [])
    except Exception:
        return []
    if isinstance(raw, list):
        return [str(w) for w in raw if str(w).strip()]
    return []


class CleanEngine:
    """Движок очистки: строит план и выполняет его последовательно."""

    def build_plan(
        self, cleaners: list[BaseCleaner], whitelist: list[str] | None = None
    ) -> OperationPlan:
        if whitelist is None:
            whitelist = _config_whitelist()
        return Planner(whitelist).build(cleaners)

    def clean_selected(
        self,
        cleaners: list[BaseCleaner],
        options: CleanOptions | None = None,
        progress_callback: Callable[[int, int, CleanResult], None] | None = None,
    ) -> list[CleanResult]:
        """Очистить выбранные цели одну за другой.

        Для файловых целей удаление идёт пакетно через оболочку Windows,
        для командных — вызывается ``cleaner.clean()``.
        """
        return self.clean_plan(
            self.build_plan(cleaners), options, progress_callback
        )

    def clean_plan(
        self,
        plan: OperationPlan,
        options: CleanOptions | None = None,
        progress_callback: Callable[[int, int, CleanResult], None] | None = None,
    ) -> list[CleanResult]:
        """Выполнить уже построенный план.

        Это важно для глубокой очистки: пользователь подтверждает конкретный
        список действий, и удаляется именно он, без повторного планирования.
        """
        options = options or CleanOptions()
        token = set_clean_options(options)
        results: list[CleanResult] = []
        total = len(plan.targets)

        try:
            for i, target in enumerate(plan.targets):
                result = self._clean_target(target, options)
                results.append(result)
                if progress_callback:
                    try:
                        progress_callback(i + 1, total, result)
                    except Exception:
                        pass
        finally:
            reset_clean_options(token)

        return results

    # ── одна цель ────────────────────────────────────

    def _clean_target(self, target: TargetPlan, options: CleanOptions) -> CleanResult:
        cleaner = target.cleaner
        planned = max(0, int(target.planned_bytes))
        volumes = tuple(sorted(target.volumes or {SYSTEM_DRIVE}))

        if target.blocked:
            cleaner.size = planned
            cleaner.scanned = True
            return CleanResult(
                cleaner=cleaner,
                status="SKIP",
                detail=target.blocked,
                planned=planned,
                freed=0,
                remaining=planned,
                note=target.blocked,
                volumes=volumes,
            )

        if target.mode == "paths" and not target.actions:
            cleaner.size = 0
            cleaner.scanned = True
            return CleanResult(
                cleaner=cleaner,
                status="SKIP",
                detail="Нечего очищать",
                planned=0,
                freed=0,
                remaining=0,
                volumes=volumes,
            )

        before = {volume: _free(volume) for volume in volumes}
        removed = 0
        errors: list[str] = []
        # Пользовательские данные (слой D) всегда отправляем в корзину.
        use_recycle = bool(options.to_recycle or target.layer == LAYER_LEFTOVERS)

        try:
            if target.mode == "command":
                status, detail = cleaner.clean()
            else:
                status, detail, removed, errors = self._clean_paths(
                    target, options, use_recycle
                )
        except Exception as e:  # очиститель не должен ронять весь процесс
            status, detail = "ERR", str(e)

        after = {volume: _free(volume) for volume in volumes}
        deltas = {v: max(0, after.get(v, 0) - before.get(v, 0)) for v in volumes}
        volume_delta = sum(deltas.values())
        freed = volume_delta if status == "OK" else 0

        try:
            remaining = max(0, int(cleaner.get_size()))
        except Exception:
            remaining = max(0, planned - removed)

        cleaner.size = remaining
        cleaner.scanned = True

        recycled = bool(
            use_recycle
            and (removed > 0 or (target.mode == "command" and planned > 0))
            and freed == 0
            and remaining == 0
        )

        confidence = "high"
        if status == "OK" and removed > 0 and volume_delta == 0 and not use_recycle:
            confidence = "estimate"

        status, note = self._analyze(
            status=status,
            planned=planned,
            freed=freed,
            remaining=remaining,
            recycled=recycled,
            removed=removed,
            errors=errors,
            mode=target.mode,
        )

        return CleanResult(
            cleaner=cleaner,
            status=status,
            detail=detail,
            planned=planned,
            freed=freed,
            remaining=remaining,
            note=note,
            recycled=recycled,
            removed=removed,
            volume_delta=volume_delta,
            volume_deltas={v: d for v, d in deltas.items() if d > 0},
            volumes=volumes,
            confidence=confidence,
            errors=errors[:10],
        )

    def _clean_paths(
        self,
        target: TargetPlan,
        options: CleanOptions,
        to_recycle: bool | None = None,
    ) -> tuple[str, str, int, list[str]]:
        recycle = options.to_recycle if to_recycle is None else bool(to_recycle)
        paths = [
            str(action.path) for action in target.actions
            if action.path is not None
        ]
        actions = {
            os.path.normcase(str(action.path)): action
            for action in target.actions
            if action.path is not None
        }
        if not paths:
            return "OK", "Нечего очищать", 0, []

        deleted_all: list[str] = []
        failed_all: list[str] = []
        aborted = False

        for start in range(0, len(paths), DELETE_CHUNK):
            if scan_cancelled():
                aborted = True
                break
            chunk = paths[start:start + DELETE_CHUNK]
            result = delete_many(chunk, to_recycle=recycle)
            deleted_all.extend(result.get("deleted", []))
            failed_all.extend(result.get("failed", []))
            if result.get("aborted"):
                aborted = True
                break

        deleted_keys = {os.path.normcase(p) for p in deleted_all}
        removed = sum(
            action.bytes for key, action in actions.items()
            if key in deleted_keys
        )

        if aborted:
            return "ERR", "Операция прервана системой или пользователем", removed, failed_all
        if not deleted_all and failed_all:
            return "ERR", f"Не удалось удалить объектов: {len(failed_all)}", 0, failed_all
        if failed_all:
            detail = (
                f"Удалено объектов: {len(deleted_all)}; "
                f"не удалось: {len(failed_all)}"
            )
            return "OK", detail, removed, failed_all
        return "OK", f"Удалено объектов: {len(deleted_all)}", removed, []

    # ── анализ результата ────────────────────────────

    @staticmethod
    def _analyze(
        status: str,
        planned: int,
        freed: int,
        remaining: int,
        recycled: bool,
        removed: int = 0,
        errors: list[str] | None = None,
        mode: str = "command",
    ) -> tuple[str, str]:
        """Скорректировать статус и сформировать понятное пояснение."""
        errors = errors or []
        note = ""

        if status != "OK":
            if planned > 0 and remaining >= planned:
                note = (
                    "Данные не удалены: возможно, нужны права администратора "
                    "или файлы заняты."
                )
            elif errors:
                note = f"Не удалось удалить объектов: {len(errors)}."
            return status, note

        if planned <= 0:
            return status, note

        if mode == "paths":
            if removed == 0 and planned > 1024 * 1024:
                return "ERR", (
                    "Не удалось удалить данные (нужны права администратора "
                    "или файлы заняты другим процессом)."
                )
            if remaining > 0:
                note = f"Удалено частично: осталось {format_bytes(remaining)}."
            elif errors:
                note = f"Часть файлов пропущена: {len(errors)}."
            elif recycled:
                note = "Перемещено в корзину: место освободится после очистки корзины."
            elif removed > 0 and freed == 0:
                note = (
                    "Файлы удалены, но свободное место не изменилось: "
                    "его могли занять другие процессы."
                )
            return status, note

        # Командные цели: сохраняем прежнюю эвристику.
        if remaining >= planned and planned > 1024 * 1024:
            return "ERR", (
                "Не удалось удалить данные (нужны права администратора "
                "или файлы заняты другим процессом)."
            )

        if remaining > 0:
            note = f"Удалено частично: осталось {format_bytes(remaining)}."
        elif recycled:
            note = "Перемещено в корзину: место освободится после очистки корзины."

        return status, note

    # ── совместимость ────────────────────────────────

    @staticmethod
    def _verify_remaining(cleaner: BaseCleaner, planned: int, freed: int) -> int:
        if planned <= 0:
            return 0
        if freed >= planned * 0.9:
            return max(0, planned - freed)
        try:
            return max(0, int(cleaner.get_size()))
        except Exception:
            return planned

    def get_total_freed(self, results: list[CleanResult]) -> int:
        return sum(r.freed for r in results)


def _free(volume: str) -> int:
    """Свободное место на томе с совместимостью со старыми тестами."""
    try:
        return int(get_disk_free(volume)[0])
    except TypeError:
        # Некоторые тесты подменяют get_disk_free() функцией без аргументов.
        return int(get_disk_free()[0])


def volume_for(path) -> str:
    """Публичный helper для UI/отчётов."""
    return volume_root(path)
