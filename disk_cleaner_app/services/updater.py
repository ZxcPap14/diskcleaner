"""Проверка обновлений: последний релиз GitHub или свой JSON-манифест.

По умолчанию источник — ``owner/repo`` на GitHub, тогда берётся
``/releases/latest`` (draft и prerelease API не отдаёт). Можно указать и
прямой http(s)-адрес манифеста вида
``{"version": "4.21.0", "url": "https://…"}``.

Сеть — единственный источник данных, поэтому все ошибки возвращаются
строкой статуса, а не исключением.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

STATUS_DISABLED = "disabled"
STATUS_UP_TO_DATE = "up-to-date"
STATUS_AVAILABLE = "available"
STATUS_ERROR = "error"

# Больше манифеста не читаем: чужой сервер не должен забить память.
MAX_BYTES = 64 * 1024
TIMEOUT = 5.0

GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")

# Автопроверка при старте — не чаще раза в сутки.
CHECK_INTERVAL = 24 * 60 * 60


def should_check(
    last_check: float | None,
    now: float | None = None,
    interval: float = CHECK_INTERVAL,
) -> bool:
    """Пора ли проверять обновления: нет отметки или она старше суток."""
    try:
        last = float(last_check or 0)
    except (TypeError, ValueError):
        return True
    return (now if now is not None else time.time()) - last >= interval


def resolve_source(value: str | None) -> str:
    """``owner/repo`` → адрес последнего релиза GitHub; http(s) — как есть."""
    value = (value or "").strip()
    if not value.lower().startswith(("http://", "https://")) and _REPO_RE.match(value):
        return GITHUB_API.format(repo=value)
    return value



def parse_version(text: object) -> tuple[int, ...]:
    """``v4.20.1`` → ``(4, 20, 1)``; хвост и мусор отбрасываются."""
    numbers = re.findall(r"\d+", str(text or ""))
    return tuple(int(n) for n in numbers[:4])


def is_newer(latest: str, current: str) -> bool:
    latest_parts = parse_version(latest)
    current_parts = parse_version(current)
    # Новая нумерация 1.x пошла после 4.x (сменился движок интерфейса),
    # поэтому старые 4.x обязаны видеть 1.x как обновление.
    if current_parts and latest_parts and current_parts[0] >= 4 and latest_parts[0] == 1:
        return True
    return latest_parts > current_parts


def _result(status: str, message: str, latest: str | None = None,
            url: str | None = None) -> dict:
    return {"status": status, "message": message, "latest": latest, "url": url}


def check_for_updates(
    current_version: str,
    url: str | None = None,
    timeout: float = TIMEOUT,
) -> dict:
    """Сравнить текущую версию с релизом/манифестом. Никогда не бросает."""
    url = resolve_source(url)
    if not url:
        return _result(
            STATUS_DISABLED,
            "Источник обновлений не задан — проверка выключена.",
        )
    if not url.lower().startswith(("http://", "https://")):
        return _result(STATUS_ERROR, "Адрес должен начинаться с http:// или https://.")

    request = urllib.request.Request(
        url,
        headers={
            # GitHub без User-Agent отвечает 403.
            "User-Agent": f"DiskCleaner/{current_version}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES)
    except urllib.error.HTTPError as e:
        if e.code == 404 and "/releases/latest" in url:
            return _result(
                STATUS_ERROR, "В репозитории ещё нет опубликованных релизов."
            )
        return _result(STATUS_ERROR, f"Не удалось получить данные: HTTP {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return _result(STATUS_ERROR, f"Не удалось получить данные: {e}")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _result(STATUS_ERROR, "Ответ не является корректным JSON.")
    if not isinstance(payload, dict):
        return _result(STATUS_ERROR, "Ответ должен быть JSON-объектом.")

    latest = payload.get("version") or payload.get("tag_name") or payload.get("name")
    if not latest or not parse_version(latest):
        return _result(STATUS_ERROR, "В ответе нет номера версии.")
    latest = str(latest)
    # html_url — человеческая страница релиза, url у GitHub ведёт в API.
    page = str(payload.get("html_url") or payload.get("url") or url)

    if is_newer(latest, current_version):
        return _result(
            STATUS_AVAILABLE,
            f"Доступна версия {latest} (у вас {current_version}).",
            latest, page,
        )
    return _result(
        STATUS_UP_TO_DATE, f"Установлена последняя версия {current_version}.",
        latest, page,
    )
