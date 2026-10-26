"""Тесты поиска и удаления остатков программы."""
from __future__ import annotations

import os
from pathlib import Path

from disk_cleaner_app.services.uninstaller import AppUninstaller


def _make_tree(root: Path, name: str, size: int = 100) -> Path:
    target = root / name
    target.mkdir(parents=True)
    (target / "file.bin").write_bytes(b"x" * size)
    return target


def test_find_leftovers_finds_install_and_appdata(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Local"
    programs = tmp_path / "Program Files"
    appdata.mkdir(parents=True)
    programs.mkdir(parents=True)

    install = _make_tree(programs, "TestApp")
    local = _make_tree(appdata, "TestApp")
    _make_tree(appdata, "TestApp Helper")  # НЕ должно совпадать

    uninstaller = AppUninstaller(
        appdata_roots=[appdata],
        program_roots=[programs],
    )
    app = {"name": "TestApp", "install_location": str(install)}

    leftovers = uninstaller.find_leftovers(app, "safe")
    paths = {os.path.normcase(item["path"]) for item in leftovers}

    assert os.path.normcase(str(install)) in paths
    assert os.path.normcase(str(local)) in paths
    assert not any("Helper" in item["path"] for item in leftovers)
    assert all(item["size"] > 0 for item in leftovers)
    assert all(item["kind"] == "dir" for item in leftovers)


def test_publisher_subfolder_is_found(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    publisher_dir = appdata / "TestCorp"
    publisher_dir.mkdir(parents=True)
    nested = _make_tree(publisher_dir, "TestApp")

    uninstaller = AppUninstaller(appdata_roots=[appdata], program_roots=[])
    app = {"name": "TestApp", "publisher": "TestCorp"}

    leftovers = uninstaller.find_leftovers(app, "safe")

    assert [os.path.normcase(i["path"]) for i in leftovers] == [
        os.path.normcase(str(nested))
    ]


def test_unsafe_install_location_is_ignored(tmp_path: Path) -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    app = {"name": "TestApp", "install_location": str(Path.home())}

    assert uninstaller.find_leftovers(app, "safe") == []


def test_system_subfolder_is_unsafe() -> None:
    windows_system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    assert AppUninstaller._is_safe_target(windows_system32) is False


def test_remove_leftovers_only_deletes_confirmed(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Local"
    appdata.mkdir(parents=True)
    target = _make_tree(appdata, "TestApp")
    keep = _make_tree(appdata, "OtherApp")

    uninstaller = AppUninstaller(appdata_roots=[appdata], program_roots=[])
    leftovers = [{
        "kind": "dir",
        "path": str(target),
        "label": "Данные приложения",
        "size": 100,
    }]

    logs = uninstaller.remove_leftovers(leftovers)

    assert not target.exists()
    assert keep.exists()
    assert any("Удалено" in line for line in logs)


def test_remove_leftovers_skips_unsafe_path(tmp_path: Path) -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    leftovers = [{
        "kind": "dir",
        "path": str(Path.home()),
        "label": "Дом",
        "size": 0,
    }]

    logs = uninstaller.remove_leftovers(leftovers)

    assert Path.home().exists()
    assert any("небезопасный путь" in line for line in logs)


def test_short_app_name_is_ignored(tmp_path: Path) -> None:
    uninstaller = AppUninstaller(appdata_roots=[tmp_path], program_roots=[])
    assert uninstaller.find_leftovers({"name": "A"}, "safe") == []


def test_duplicates_are_removed_from_candidates(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Local"
    appdata.mkdir(parents=True)
    target = _make_tree(appdata, "TestApp")

    uninstaller = AppUninstaller(appdata_roots=[appdata], program_roots=[])
    app = {"name": "TestApp", "install_location": str(target)}

    leftovers = uninstaller.find_leftovers(app, "safe")

    assert len(leftovers) == 1


def test_install_date_label_formats_registry_value() -> None:
    from disk_cleaner_app.ui.views.uninstaller import UninstallerView

    assert UninstallerView._install_date_label({"install_date": "20260115"}) == "2026-01-15"
    assert UninstallerView._install_date_label({"install_date": ""}) == "—"
    assert UninstallerView._install_date_label({}) == "—"
    assert UninstallerView._install_date_label({"install_date": "bad"}) == "—"


def test_install_size_counts_install_folder(tmp_path: Path) -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    target = tmp_path / "TestApp"
    (target / "sub").mkdir(parents=True)
    (target / "a.bin").write_bytes(b"x" * 300)
    (target / "sub" / "b.bin").write_bytes(b"y" * 200)

    size = uninstaller.install_size({"install_location": str(target)})

    assert size == 500


def test_install_size_handles_quotes_and_files(tmp_path: Path) -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    target = tmp_path / "app.exe"
    target.write_bytes(b"z" * 42)

    assert uninstaller.install_size({"install_location": f'"{target}"'}) == 42


def test_install_size_returns_none_for_missing_or_unsafe(tmp_path: Path) -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])

    assert uninstaller.install_size({}) is None
    assert uninstaller.install_size({"install_location": ""}) is None
    assert uninstaller.install_size(
        {"install_location": str(tmp_path / "missing")}
    ) is None
    assert uninstaller.install_size(
        {"install_location": str(Path.home())}
    ) is None


class _FakeUninstaller(AppUninstaller):
    def __init__(self) -> None:
        super().__init__(appdata_roots=[], program_roots=[])
        self.calls: list[str] = []

    def uninstall(self, app: dict) -> list[str]:
        self.calls.append(str(app.get("name")))
        return [f"✅ {app.get('name')} удалена"]


def test_uninstall_many_runs_in_order() -> None:
    fake = _FakeUninstaller()
    apps = [{"name": "A"}, {"name": "B"}, {"name": "C"}]

    logs = fake.uninstall_many(apps)

    assert fake.calls == ["A", "B", "C"]
    assert "[1/3] A" in logs[0]
    assert logs[-1].startswith("✅ Очередь завершена: 3")


def test_uninstall_many_stops_before_next_app() -> None:
    fake = _FakeUninstaller()
    stop = {"value": False}

    def on_log(line: str) -> None:
        if line.startswith("▶ [1/"):
            stop["value"] = True

    logs = fake.uninstall_many(
        [{"name": "A"}, {"name": "B"}],
        on_log=on_log,
        should_stop=lambda: stop["value"],
    )

    assert fake.calls == ["A"]
    assert logs[-1] == "⏹ Остановлено: выполнено 1 из 2."


def test_uninstall_many_handles_empty_list() -> None:
    assert _FakeUninstaller().uninstall_many([]) == []


def test_size_text_shows_real_estimate_and_pending() -> None:
    from disk_cleaner_app.ui.views.uninstaller import UninstallerView

    assert UninstallerView._size_text({"real_size": 1024}) == "1.0 КБ"
    assert UninstallerView._size_text({"real_size": None}) == "—"
    assert UninstallerView._size_text(
        {"size_kb": 2048, "install_location": r"C:\App"}
    ) == "≈ 2.0 МБ"
    assert UninstallerView._size_text({"install_location": r"C:\App"}) == "…"
    assert UninstallerView._size_text({}) == "—"


def test_size_key_prefers_real_size() -> None:
    from disk_cleaner_app.ui.views.uninstaller import UninstallerView

    assert UninstallerView._size_key({"real_size": 10, "size_kb": 1}) == 10
    assert UninstallerView._size_key({"size_kb": 1}) == 1024
