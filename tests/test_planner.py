"""Тесты планировщика глубокой очистки."""
from __future__ import annotations

import os
import time
from pathlib import Path

from helpers import FakeCleaner, PathCleaner

from disk_cleaner_app.services import planner as planner_module
from disk_cleaner_app.services.planner import (
    PlannedAction,
    Planner,
    TargetPlan,
    volume_root,
)


def _write(path: Path, size: int = 10) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def _age(path: Path, hours: float) -> None:
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


def test_contents_plan_lists_children_and_keeps_parent(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    _write(cache / "a.bin", 100)
    _write(cache / "sub" / "b.bin", 50)

    plan = Planner().build([PathCleaner([cache])])
    target = plan.targets[0]

    assert target.mode == "paths"
    assert target.planned_bytes == 150
    assert target.volumes == {volume_root(cache)}
    paths = {action.path for action in target.actions}
    assert cache / "a.bin" in paths
    assert cache / "sub" in paths
    # Сама папка не удаляется: чистим только содержимое.
    assert cache not in paths
    assert plan.total_by_volume[volume_root(cache)] == 150


def test_remove_mode_plans_the_folder_itself(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    _write(cache / "a.bin", 10)

    plan = Planner().build([PathCleaner([cache], delete_mode="remove")])
    actions = plan.targets[0].actions

    assert len(actions) == 1
    assert actions[0].path == cache
    assert actions[0].is_dir is True


def test_age_filter_skips_fresh_files(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    old = _write(cache / "old.tmp", 10)
    fresh = _write(cache / "fresh.tmp", 10)
    _age(old, 48)
    _age(fresh, 1)

    plan = Planner().build([PathCleaner([cache], min_age_hours=24)])
    paths = {action.path for action in plan.targets[0].actions}

    assert old in paths
    assert fresh not in paths
    assert plan.targets[0].planned_bytes == 10


def test_age_filter_skips_fresh_folder_in_remove_mode(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _write(fresh / "a.bin", 10)

    plan = Planner().build(
        [PathCleaner([fresh], delete_mode="remove", min_age_hours=24)]
    )
    target = plan.targets[0]

    assert target.actions == []
    assert any("слишком новая папка" in reason for reason in target.skipped)


def test_nested_targets_do_not_delete_the_same_path_twice(tmp_path: Path) -> None:
    parent = tmp_path / "root"
    child = parent / "cache"
    _write(child / "a.bin", 100)
    _write(parent / "other" / "b.bin", 50)

    plan = Planner().build(
        [
            PathCleaner([parent], cleaner_id="parent"),
            PathCleaner([child], cleaner_id="child"),
        ]
    )
    parent_plan, child_plan = plan.targets

    assert parent_plan.planned_bytes == 150
    assert child_plan.planned_bytes == 0
    assert child_plan.actions == []
    assert any("пересекается" in reason for reason in child_plan.skipped)

    all_paths = [a.path for a in parent_plan.actions] + [a.path for a in child_plan.actions]
    assert len(all_paths) == len(set(all_paths))
    assert plan.action_count == 2


def test_protected_paths_are_skipped(tmp_path: Path) -> None:
    safe = _write(tmp_path / "cache" / "a.bin", 10)
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))

    plan = Planner().build(
        [PathCleaner([Path.home(), system_root, safe])]
    )
    target = plan.targets[0]

    assert [action.path for action in target.actions] == [safe]
    skipped = " ".join(target.skipped)
    assert "защищённый путь" in skipped


def test_missing_paths_are_reported_not_fatal(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    plan = Planner().build([PathCleaner([missing])])
    target = plan.targets[0]

    assert target.actions == []
    assert any("нет пути" in reason for reason in target.skipped)


def test_command_target_reads_fresh_size() -> None:
    cleaner = FakeCleaner(size=99)
    cleaner._fake_size = 5   # get_size() возвращает 5, size остаётся 99

    plan = Planner().build([cleaner])

    assert plan.targets[0].mode == "command"
    assert plan.targets[0].planned_bytes == 5


def test_admin_target_is_blocked_without_rights(tmp_path: Path, monkeypatch) -> None:
    file = _write(tmp_path / "cache" / "a.bin", 10)
    cleaner = PathCleaner([file.parent], admin_required=True)

    monkeypatch.setattr(planner_module.elevation, "is_admin", lambda: False)
    blocked = Planner().build([cleaner]).targets[0]
    assert blocked.blocked

    monkeypatch.setattr(planner_module.elevation, "is_admin", lambda: True)
    allowed = Planner().build([cleaner]).targets[0]
    assert allowed.blocked == ""


def test_plan_totals_by_layer(tmp_path: Path) -> None:
    a = tmp_path / "a"
    _write(a / "file.bin", 100)
    b = tmp_path / "b"
    _write(b / "file.bin", 300)

    plan = Planner().build(
        [
            PathCleaner([a], cleaner_id="a", layer="A"),
            PathCleaner([b], cleaner_id="b", layer="C"),
        ]
    )

    assert plan.total_bytes == 400
    assert plan.total_by_layer == {"A": 100, "C": 300}
    assert plan.action_count == 2
    assert plan.id


def test_plan_marks_truncated_target(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    for index in range(5):
        _write(cache / f"{index}.bin", 1)

    monkeypatch.setattr(planner_module, "MAX_ACTIONS", 3)
    target = Planner().build([PathCleaner([cache])]).targets[0]

    assert len(target.actions) == 3
    assert target.truncated is True
    assert any("слишком много файлов" in reason for reason in target.skipped)


def test_overlap_reports_winning_target(tmp_path: Path) -> None:
    parent = tmp_path / "root"
    child = parent / "cache"
    _write(child / "a.bin", 100)

    plan = Planner().build(
        [
            PathCleaner([parent], cleaner_id="parent"),
            PathCleaner([child], cleaner_id="child"),
        ]
    )
    child_plan = plan.targets[1]

    assert child_plan.actions == []
    assert any(
        "пересекается с «parent»" in reason for reason in child_plan.skipped
    )


def test_overlap_resolution_is_not_quadratic() -> None:
    """Регрессия: сравнение каждого пути с каждым вешало большие планы.

    20 000 пересекающихся действий раньше требовали ~4·10⁸ сравнений.
    """
    parent_plan = TargetPlan(cleaner=FakeCleaner("parent"), mode="paths")
    child_plan = TargetPlan(cleaner=FakeCleaner("child"), mode="paths")
    base = Path("C:/dc_overlap_test/root")
    parent_plan.actions = [
        PlannedAction(
            target_id="parent", path=base / f"a{index:05d}",
            bytes=1, volume="C:\\", action="path",
        )
        for index in range(10_000)
    ]
    child_plan.actions = [
        PlannedAction(
            target_id="child", path=base / f"a{index:05d}" / "x.bin",
            bytes=1, volume="C:\\", action="path",
        )
        for index in range(10_000)
    ]

    Planner()._resolve_overlaps([parent_plan, child_plan])

    assert len(parent_plan.actions) == 10_000
    assert child_plan.actions == []
    assert len(child_plan.skipped) == 10_000


def test_whitelist_excludes_paths_from_plan(tmp_path: Path) -> None:
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "a.bin").write_bytes(b"x" * 10)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "b.bin").write_bytes(b"y" * 20)

    plan = Planner(whitelist=[str(keep)]).build([PathCleaner([keep, cache])])

    actions = plan.targets[0].actions
    assert [str(a.path) for a in actions] == [str(cache / "b.bin")]
    assert plan.targets[0].planned_bytes == 20
    assert any("белый список" in s for s in plan.targets[0].skipped)


def test_whitelist_covers_children(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    target.mkdir()
    (target / "sub").mkdir()
    (target / "sub" / "c.bin").write_bytes(b"z" * 5)

    plan = Planner(whitelist=[str(target / "sub")]).build([PathCleaner([target])])

    assert plan.targets[0].actions == []
