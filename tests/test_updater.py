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
def manifest_server(payload, status: int = 200):
    """Поднять сервер на 127.0.0.1 со своим ответом и отдать URL."""
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    handler = type("H", (_Handler,), {"body": body, "status": status})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/latest.json"
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
    assert "Не удалось получить манифест" in result["message"]


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
