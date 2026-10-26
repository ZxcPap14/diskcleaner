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


# ── диски, портативные программы ────────────────────────


def test_drive_of_extracts_drive_letter() -> None:
    assert AppUninstaller._drive_of(r"C:\Program Files\App") == "C:"
    assert AppUninstaller._drive_of(r'd="D:\Apps"') == ""
    assert AppUninstaller._drive_of(r'"E:\Tools\App"') == "E:"
    assert AppUninstaller._drive_of("") == ""
    assert AppUninstaller._drive_of(r"relative\path") == ""


def test_dedupe_keeps_same_name_on_different_drives() -> None:
    apps = [
        {"name": "App", "install_location": r"C:\Apps\App"},
        {"name": "App", "install_location": r"D:\Apps\App"},
        {"name": "App", "install_location": r"C:\Apps\App"},  # дубликат реестра
        {"name": "Solo", "install_location": ""},
        {"name": "Solo", "install_location": ""},
    ]
    result = AppUninstaller._dedupe_apps(apps)

    names = [(a["name"], a["install_location"]) for a in result]
    assert names == [
        ("App", r"C:\Apps\App"),
        ("App", r"D:\Apps\App"),
        ("Solo", ""),
    ]


def test_get_portable_finds_dirs_with_exe(tmp_path: Path) -> None:
    portable_app = tmp_path / "MyPortable"
    portable_app.mkdir()
    (portable_app / "app.exe").write_bytes(b"MZ")

    nested = tmp_path / "Bundled"
    (nested / "bin").mkdir(parents=True)
    (nested / "bin" / "tool.exe").write_bytes(b"MZ")

    empty = tmp_path / "NoProgram"
    empty.mkdir()
    (empty / "readme.txt").write_text("hello")

    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    found = uninstaller.get_portable(drives=[str(tmp_path)], known_locations=[])

    names = {item["name"] for item in found}
    assert names == {"MyPortable", "Bundled"}
    assert all(item["portable"] for item in found)
    assert all(item["install_location"] for item in found)


def test_get_portable_skips_service_dirs_and_known(tmp_path: Path) -> None:
    app_dir = tmp_path / "Registered"
    app_dir.mkdir()
    (app_dir / "app.exe").write_bytes(b"MZ")

    junk = tmp_path / "$RECYCLE.BIN"
    junk.mkdir()

    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    found = uninstaller.get_portable(
        drives=[str(tmp_path)], known_locations=[str(app_dir)]
    )

    assert found == []


def test_inside_known_checks_prefix() -> None:
    known = {r"c:\apps\tool"}
    assert AppUninstaller._inside_known(r"C:\apps\tool\app.exe", known)
    assert not AppUninstaller._inside_known(r"C:\apps\tools\app.exe", known)
    assert not AppUninstaller._inside_known(r"C:\apps\toolkit.exe", known)


def test_portable_install_date_from_folder_mtime(tmp_path: Path) -> None:
    app_dir = tmp_path / "MyPortable"
    app_dir.mkdir()
    (app_dir / "app.exe").write_bytes(b"MZ")

    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    found = uninstaller.get_portable(drives=[str(tmp_path)], known_locations=[])

    assert len(found) == 1
    date = found[0]["install_date"]
    assert len(date) == 8 and date.isdigit()


def test_remove_portable_sends_folder_to_recycle(
    tmp_path: Path, monkeypatch
) -> None:
    import disk_cleaner_app.services.uninstaller as module

    app_dir = tmp_path / "MyPortable"
    app_dir.mkdir()
    (app_dir / "app.exe").write_bytes(b"MZ")

    calls: list[tuple[list[str], bool]] = []

    def fake_delete_many(paths, to_recycle=True, use_ifile=True):
        calls.append((list(paths), to_recycle))
        return {"deleted": list(paths), "failed": []}

    monkeypatch.setattr(module, "delete_many", fake_delete_many)

    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    logs = uninstaller.remove_portable(
        {"name": "MyPortable", "install_location": str(app_dir)}
    )

    assert calls == [([str(app_dir)], True)]
    assert any("корзину" in line for line in logs)


def test_remove_portable_refuses_unsafe_paths(tmp_path: Path, monkeypatch) -> None:
    import disk_cleaner_app.services.uninstaller as module

    calls: list[list[str]] = []
    monkeypatch.setattr(
        module, "delete_many",
        lambda paths, to_recycle=True, use_ifile=True: calls.extend(paths)
        or {"deleted": [], "failed": []},
    )

    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    logs = uninstaller.remove_portable({"install_location": str(Path.home())})

    assert calls == []
    assert any("небезопасный путь" in line for line in logs)


def test_safe_remove_target_refuses_roots_and_windows(tmp_path: Path) -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])

    assert uninstaller._is_safe_remove_target(tmp_path) is True
    assert uninstaller._is_safe_remove_target(tmp_path / "missing") is False

    root = Path(tmp_path.anchor)  # корень тома
    assert uninstaller._is_safe_remove_target(root) is False

    windows_like = tmp_path / "Windows" / "Tools"
    windows_like.mkdir(parents=True)
    assert uninstaller._is_safe_remove_target(windows_like) is False


def test_safe_remove_target_blocks_forbidden_components(tmp_path: Path) -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    svi = tmp_path / "System Volume Information"  # name check via component
    svi.mkdir()

    assert uninstaller._is_safe_remove_target(svi) is False


# ── диаграмма и строки списка ───────────────────────────


def test_chart_data_top_and_rest() -> None:
    from disk_cleaner_app.ui.views.uninstaller import UninstallerView

    apps = [
        {"name": f"App{i}", "real_size": 1000 - i} for i in range(15)
    ]
    data = UninstallerView._chart_data(apps, top=10)

    assert len(data) == 11
    assert data[0] == ("App0", 1000)
    assert data[-1][0] == "Остальные: 5"
    assert data[-1][1] == sum(1000 - i for i in range(10, 15))


def test_chart_data_skips_zero_sizes() -> None:
    from disk_cleaner_app.ui.views.uninstaller import UninstallerView

    apps = [{"name": "Big", "real_size": 500}, {"name": "Unknown", "real_size": None}]
    data = UninstallerView._chart_data(apps)

    assert data == [("Big", 500)]


def test_row_values_marks_portable_and_disk() -> None:
    from disk_cleaner_app.ui.views.uninstaller import UninstallerView

    installed = UninstallerView._row_values(
        {"name": "App", "version": "1.0", "drive": "C:", "real_size": 2048,
         "install_date": "20260102"}
    )
    assert installed == ("App", "C:", "1.0", "2.0 КБ", "2026-01-02")

    portable = UninstallerView._row_values(
        {"name": "Tool", "portable": True, "drive": "D:", "real_size": None}
    )
    assert portable[0] == "📦 Tool"
    assert portable[1] == "D:"

    unknown = UninstallerView._row_values({"name": "X"})
    assert unknown[1] == "—"


# ── UWP/Store и точка восстановления (4.16.0) ───────────


def test_parse_uwp_records_filters_frameworks_and_builds_commands() -> None:
    import json

    location = str(Path("C:") / "Program Files" / "WindowsApps" / "Calc")
    raw = json.dumps([
        {
            "name": "Microsoft.WindowsCalculator",
            "fullname": "Micro.Calc_1.0_x64__8weky",
            "version": "1.0",
            "publisher": "Microsoft",
            "location": location,
        },
        {
            "name": "Microsoft.VCLibs",
            "fullname": "Micro.VCLibs_1_x64__8weky",
            "version": "1.0",
            "publisher": "Microsoft",
            "location": "",
        },
        {"name": "", "fullname": "Broken", "version": "", "publisher": "",
         "location": ""},
    ])
    # Фреймворк отфильтрован ещё в PowerShell (IsFramework), до парсера
    # доходят только удаляемые пакеты; битые записи пропускает парсер.
    apps = AppUninstaller.parse_uwp_records(raw)

    assert len(apps) == 1
    app = apps[0]
    assert app["name"] == "Microsoft.WindowsCalculator"
    assert app["uwp"] is True
    assert app["drive"] == "C:"
    assert "Remove-AppxPackage -Package 'Micro.Calc_1.0_x64__8weky'" in app["uninstall_string"]
    assert app["uninstall_string"] == app["quiet_uninstall"]


def test_parse_uwp_records_handles_single_object_and_garbage() -> None:
    single = '{"name": "App", "fullname": "App_1_x64__8weky", "version": "1", "publisher": "", "location": ""}'
    apps = AppUninstaller.parse_uwp_records(single)
    assert len(apps) == 1

    assert AppUninstaller.parse_uwp_records("") == []
    assert AppUninstaller.parse_uwp_records("не json") == []
    assert AppUninstaller.parse_uwp_records("[]") == []


def test_restore_point_logs_disabled_or_empty() -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])
    calls: list[str] = []

    def fake_point(description: str) -> tuple[bool, str]:
        calls.append(description)
        return True, "Точка восстановления создана"

    assert uninstaller.restore_point_logs([], fake_point, enabled=True) == []
    assert uninstaller.restore_point_logs(
        [{"name": "A"}], fake_point, enabled=False
    ) == []
    assert calls == []


def test_restore_point_logs_success_and_failure() -> None:
    uninstaller = AppUninstaller(appdata_roots=[], program_roots=[])

    def ok_point(description: str) -> tuple[bool, str]:
        assert description == "DiskCleaner Pro — перед удалением программ"
        return True, "Точка восстановления создана"

    logs = uninstaller.restore_point_logs([{"name": "A"}], ok_point, enabled=True)
    assert logs == ["🛡️  Точка восстановления создана"]

    def fail_point(_description: str) -> tuple[bool, str]:
        return False, "Точка восстановления не создана: нужны права администратора"

    logs = uninstaller.restore_point_logs([{"name": "A"}], fail_point, enabled=True)
    assert logs and "продолжится без неё" in logs[0]


def test_uwp_note_in_confirmation() -> None:
    from disk_cleaner_app.ui.views.uninstaller import UninstallerView

    uwp_apps = [{"name": f"App{i}", "uwp": True} for i in range(5)]
    note = UninstallerView._uwp_note(uwp_apps)
    assert "Remove-AppxPackage" in note
    assert "App0, App1, App2" in note and "и ещё 2" in note

    assert UninstallerView._uwp_note([{"name": "Win32"}]) == ""
    assert UninstallerView._uwp_note([]) == ""


def test_row_values_marks_uwp() -> None:
    from disk_cleaner_app.ui.views.uninstaller import UninstallerView

    row = UninstallerView._row_values(
        {"name": "Microsoft.WindowsCalculator", "uwp": True, "drive": "C:"}
    )
    assert row[0] == "🪟 Microsoft.WindowsCalculator"
