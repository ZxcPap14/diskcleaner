"""Тесты 4.19.0: автозапуск самого приложения и трей."""
from __future__ import annotations

import sys
import winreg

import disk_cleaner_app.services.tray_icon as tray
from disk_cleaner_app.services.autostart_self import (
    autostart_command,
    get_autostart,
    set_autostart,
)
from disk_cleaner_app.services.tray_icon import TrayController, tray_available

# Временный подраздел HKCU: пишем в реестр только сюда, чистим в конце.
TEST_KEY = r"Software\DiskCleanerSelfTest\Run"


def _cleanup_key() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
    except OSError:
        pass


# ── команда автозапуска ──────────────────────────────────


def test_autostart_command_uses_tray_flag(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    command = autostart_command()
    assert "--tray" in command
    assert "-m disk_cleaner_app" in command

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command = autostart_command()
    assert "--tray" in command
    assert sys.executable in command


# ── реестр (временный подраздел HKCU) ────────────────────


def test_set_and_get_autostart_roundtrip() -> None:
    try:
        assert get_autostart(TEST_KEY) is None

        ok, message = set_autostart(True, key_path=TEST_KEY)
        assert ok and "включён" in message
        value = get_autostart(TEST_KEY)
        assert value is not None and "--tray" in value

        ok, message = set_autostart(False, key_path=TEST_KEY)
        assert ok and "выключен" in message
        assert get_autostart(TEST_KEY) is None

        # Повторное выключение — не ошибка.
        ok, message = set_autostart(False, key_path=TEST_KEY)
        assert ok and "и так" in message
    finally:
        _cleanup_key()


# ── трей ─────────────────────────────────────────────────


def test_tray_available_matches_import() -> None:
    # На машине с установленным pystray — True; главное, что не падает.
    assert isinstance(tray_available(), bool)


def test_tray_controller_without_pystray(monkeypatch) -> None:
    """Без pystray контроллер честно сообщает о недоступности."""
    monkeypatch.setitem(sys.modules, "pystray", None)

    calls: list[str] = []
    controller = TrayController(
        on_show=lambda: calls.append("show"),
        on_quick_clean=lambda: calls.append("clean"),
        on_quit=lambda: calls.append("quit"),
    )
    assert controller.start() is False
    assert controller.running is False
    controller.stop()  # не должен падать на пустом контроллере


def test_tray_controller_callbacks_reach_targets(monkeypatch) -> None:
    """Колбэки pystray доходят до целей контроллера."""
    calls: list[str] = []
    controller = TrayController(
        on_show=lambda: calls.append("show"),
        on_quick_clean=lambda: calls.append("clean"),
        on_quit=lambda: calls.append("quit"),
    )
    controller._show()
    controller._quick_clean()
    controller._quit()
    assert calls == ["show", "clean", "quit"]


def test_icon_image_loads() -> None:
    """Заглушка/иконка создаётся независимо от наличия assets."""
    image = tray._load_icon_image()
    assert image.size == (64, 64) or image.size == (256, 256) or image.size


def test_icon_image_taken_from_meipass_when_frozen(
    monkeypatch, tmp_path
) -> None:
    """onefile распаковывает assets в _MEIPASS, а не рядом с exe."""
    from PIL import Image

    (tmp_path / "assets").mkdir()
    Image.new("RGB", (16, 16), "#FF0000").save(
        tmp_path / "assets" / "diskcleaner.ico"
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert tray._load_icon_image().size == (16, 16)


# ── трей веб-версии ──────────────────────────────────────


def test_web_tray_reports_unavailable_without_pystray(monkeypatch) -> None:
    from disk_cleaner_app.web.tray import WebTray

    monkeypatch.setitem(sys.modules, "pystray", None)
    web_tray = WebTray(on_show=lambda: None, on_quit=lambda: None)

    assert web_tray.start() is False
    assert web_tray.running is False
    web_tray.stop()


def test_web_tray_skips_second_quick_clean() -> None:
    """Пока идёт тихая очистка, повторный клик её не дублирует."""
    import threading

    from disk_cleaner_app.web.tray import WebTray

    web_tray = WebTray(on_show=lambda: None, on_quit=lambda: None)
    running = threading.Thread(target=threading.Event().wait, daemon=True)
    running.start()
    web_tray._clean = running

    web_tray.quick_clean()

    assert web_tray._clean is running
