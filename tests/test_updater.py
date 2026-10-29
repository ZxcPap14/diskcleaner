"""Тесты 4.20.0: проверка обновлений по JSON-манифесту (локальный сервер)."""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

from disk_cleaner_app.services import updater


class _Handler(BaseHTTPRequestHandler):
    body = b"{}"
    status = 200

    def do_GET(self) -> None:  # noqa: N802 - имя задаёт http.server
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args) -> None:
        pass


@contextmanager
def manifest_server(payload, status: int = 200, path: str = "latest.json"):
    """Поднять сервер на 127.0.0.1 со своим ответом и отдать URL."""
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    handler = type("H", (_Handler,), {"body": body, "status": status})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{path}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ── версии ───────────────────────────────────────────────


def test_parse_version_handles_prefix_and_garbage() -> None:
    assert updater.parse_version("v4.20.1") == (4, 20, 1)
    assert updater.parse_version("4.20") == (4, 20)
    assert updater.parse_version("") == ()
    assert updater.parse_version(None) == ()


def test_is_newer_compares_numerically() -> None:
    assert updater.is_newer("4.20.0", "4.19.0")
    assert updater.is_newer("4.9.10", "4.10.0") is False
    assert updater.is_newer("4.19.0", "4.19.0") is False


def test_is_newer_sees_new_1x_line_after_4x() -> None:
    assert updater.is_newer("1.1.0", "4.25.0")
    assert updater.is_newer("v1.1.0", "4.24.0")
    # Внутри новой линии сравнение обычное.
    assert updater.is_newer("1.0.0", "1.1.0") is False


# ── выключенная и ошибочная проверка ─────────────────────


def test_disabled_without_url() -> None:
    result = updater.check_for_updates("4.19.0", None)

    assert result["status"] == updater.STATUS_DISABLED
    assert result["url"] is None


def test_rejects_non_http_scheme() -> None:
    result = updater.check_for_updates("4.19.0", "file:///C:/latest.json")

    assert result["status"] == updater.STATUS_ERROR
    assert "http" in result["message"]


def test_unreachable_host_is_error_not_exception() -> None:
    result = updater.check_for_updates(
        "4.19.0", "http://127.0.0.1:1/latest.json", timeout=1.0
    )

    assert result["status"] == updater.STATUS_ERROR
    assert "Не удалось получить данные" in result["message"]


# ── живой манифест ───────────────────────────────────────


def test_newer_version_is_available() -> None:
    with manifest_server(
        {"version": "4.20.0", "url": "https://example.org/download"}
    ) as url:
        result = updater.check_for_updates("4.19.0", url)

    assert result["status"] == updater.STATUS_AVAILABLE
    assert result["latest"] == "4.20.0"
    assert result["url"] == "https://example.org/download"


def test_same_version_is_up_to_date() -> None:
    with manifest_server({"version": "4.19.0"}) as url:
        result = updater.check_for_updates("4.19.0", url)

    assert result["status"] == updater.STATUS_UP_TO_DATE
    # Ссылки в манифесте нет — отдаём адрес самого манифеста.
    assert result["url"] == url


def test_github_style_tag_is_understood() -> None:
    with manifest_server({"tag_name": "v4.21.0", "html_url": "https://x/release"}) as url:
        result = updater.check_for_updates("4.19.0", url)

    assert result["status"] == updater.STATUS_AVAILABLE
    assert result["latest"] == "v4.21.0"
    assert result["url"] == "https://x/release"


def test_human_page_wins_over_api_url() -> None:
    """У GitHub `url` — адрес API, ссылку в UI берём из `html_url`."""
    payload = {
        "tag_name": "v4.22.0",
        "url": "https://api.github.com/repos/x/y/releases/1",
        "html_url": "https://github.com/x/y/releases/tag/v4.22.0",
    }
    with manifest_server(payload) as url:
        result = updater.check_for_updates("4.21.1", url)

    assert result["url"] == "https://github.com/x/y/releases/tag/v4.22.0"


def test_broken_json_is_error() -> None:
    with manifest_server(b"not json at all") as url:
        result = updater.check_for_updates("4.19.0", url)

    assert result["status"] == updater.STATUS_ERROR
    assert "JSON" in result["message"]


def test_missing_version_is_error() -> None:
    with manifest_server({"notes": "без версии"}) as url:
        result = updater.check_for_updates("4.19.0", url)

    assert result["status"] == updater.STATUS_ERROR
    assert "версии" in result["message"]


def test_http_error_status_is_error() -> None:
    with manifest_server({"version": "4.20.0"}, status=404) as url:
        result = updater.check_for_updates("4.19.0", url)

    assert result["status"] == updater.STATUS_ERROR
    assert "HTTP 404" in result["message"]


def test_repo_shorthand_resolves_to_releases_api() -> None:
    assert updater.resolve_source("ZxcPap14/diskcleaner") == (
        "https://api.github.com/repos/ZxcPap14/diskcleaner/releases/latest"
    )


def test_explicit_url_is_kept_as_is() -> None:
    url = "https://example.org/manifest.json"
    assert updater.resolve_source(url) == url
    assert updater.resolve_source("") == ""
    assert updater.resolve_source(None) == ""


def test_github_without_releases_message() -> None:
    """404 от GitHub объясняется по-человечески, а не «HTTP 404»."""
    with manifest_server(
        {"message": "Not Found"}, status=404,
        path="repos/x/y/releases/latest",
    ) as url:
        result = updater.check_for_updates("4.19.0", url)

    assert result["status"] == updater.STATUS_ERROR
    assert "нет опубликованных релизов" in result["message"]


def test_should_check_when_never_checked() -> None:
    assert updater.should_check(None) is True
    assert updater.should_check(0) is True


def test_should_check_skips_recent_check() -> None:
    now = 1_000_000.0
    assert updater.should_check(now - 3600, now=now) is False
    assert updater.should_check(now - updater.CHECK_INTERVAL, now=now) is True


def test_should_check_treats_garbage_as_never_checked() -> None:
    assert updater.should_check("garbage") is True


def test_unreachable_github_host_is_network_error() -> None:
    result = updater.check_for_updates(
        "4.19.0", "http://127.0.0.1:1/repos/x/y/releases/latest", timeout=1.0
    )

    assert result["status"] == updater.STATUS_ERROR
    assert "Не удалось получить данные" in result["message"]
