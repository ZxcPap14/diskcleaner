"""Тесты скачивания и подготовки обновления (без запуска установки)."""
from __future__ import annotations

import hashlib
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from disk_cleaner_app.services import update_install


class _Handler(BaseHTTPRequestHandler):
    body = b""

    def do_GET(self) -> None:  # noqa: N802 - имя задаёт http.server
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args) -> None:
        pass


def serve(body: bytes) -> str:
    handler = type("H", (_Handler,), {"body": body})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/app.zip"


def make_zip(tmp_path: Path, exe_name: str, prefix: str = "") -> bytes:
    path = tmp_path / "payload.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{prefix}{exe_name}", b"MZ")
        archive.writestr(f"{prefix}_internal/data.txt", b"data")
    return path.read_bytes()


def test_download_rejects_non_http() -> None:
    with pytest.raises(update_install.UpdateError):
        update_install.download("file:///C:/app.zip", Path("unused"))


def test_download_writes_file(tmp_path: Path) -> None:
    url = serve(b"payload")
    target = update_install.download(url, tmp_path / "app.zip", timeout=5.0)

    assert target.read_bytes() == b"payload"


def test_verify_sha256_accepts_and_rejects(tmp_path: Path) -> None:
    path = tmp_path / "app.zip"
    path.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()

    update_install.verify_sha256(path, f"sha256:{digest}")
    update_install.verify_sha256(path, None)
    with pytest.raises(update_install.UpdateError):
        update_install.verify_sha256(path, "sha256:" + "0" * 64)


def test_stage_unpacks_flat_archive(tmp_path: Path) -> None:
    exe_name = Path(sys.executable).name
    url = serve(make_zip(tmp_path, exe_name))
    staged = update_install.stage(url, timeout=5.0)

    assert (staged.source / exe_name).is_file()
    assert staged.exe_name == exe_name
    assert staged.work_dir.is_dir()


def test_stage_unwraps_single_root_folder(tmp_path: Path) -> None:
    exe_name = Path(sys.executable).name
    url = serve(make_zip(tmp_path, exe_name, prefix="DiskCleanerWeb/"))
    staged = update_install.stage(url, timeout=5.0)

    assert staged.source.name == "DiskCleanerWeb"
    assert (staged.source / exe_name).is_file()


def test_stage_rejects_archive_without_exe(tmp_path: Path) -> None:
    url = serve(make_zip(tmp_path, "Other.exe"))
    with pytest.raises(update_install.UpdateError):
        update_install.stage(url, timeout=5.0)


def test_stage_rejects_broken_archive(tmp_path: Path) -> None:
    url = serve(b"not a zip")
    with pytest.raises(update_install.UpdateError):
        update_install.stage(url, timeout=5.0)


def test_install_root_requires_frozen() -> None:
    if getattr(sys, "frozen", False):  # pragma: no cover - только exe-сборка
        pytest.skip("в собранном приложении проверка не имеет смысла")
    with pytest.raises(update_install.UpdateError):
        update_install.install_root()


def test_updater_script_quotes_paths_and_waits(tmp_path: Path) -> None:
    staged = update_install.Staged(
        source=tmp_path / "new app", work_dir=tmp_path, exe_name="DiskCleaner.exe",
    )
    script = update_install.updater_script(staged, Path(r"C:\Users\O'Neil\App"))

    text = script.read_text(encoding="utf-8-sig")
    assert "'C:\\Users\\O''Neil\\App'" in text
    assert "robocopy" in text
    assert "Start-Process" in text
    assert script.read_bytes().startswith(b"\xef\xbb\xbf")


def test_apply_spawns_hidden_powershell(monkeypatch, tmp_path: Path) -> None:
    staged = update_install.Staged(
        source=tmp_path / "new", work_dir=tmp_path, exe_name="DiskCleaner.exe",
    )
    calls: list[tuple[list[str], int]] = []

    def fake_popen(args, creationflags=0, **kwargs):
        calls.append((args, creationflags))

    monkeypatch.setattr(update_install, "install_root", lambda: tmp_path)
    monkeypatch.setattr(update_install.subprocess, "Popen", fake_popen)

    assert update_install.apply(staged) == tmp_path
    args, flags = calls[0]
    assert args[0] == "powershell"
    assert str(tmp_path / "apply-update.ps1") in args
    assert flags & update_install.subprocess.DETACHED_PROCESS


def test_apply_reports_spawn_failure(monkeypatch, tmp_path: Path) -> None:
    staged = update_install.Staged(
        source=tmp_path / "new", work_dir=tmp_path, exe_name="DiskCleaner.exe",
    )

    def boom(*args, **kwargs):
        raise OSError("access denied")

    monkeypatch.setattr(update_install, "install_root", lambda: tmp_path)
    monkeypatch.setattr(update_install.subprocess, "Popen", boom)

    with pytest.raises(update_install.UpdateError):
        update_install.apply(staged)
