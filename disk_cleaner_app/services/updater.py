"""Проверка обновлений по JSON-манифесту, адрес которого задан в настройках.

Манифест: ``{"version": "4.20.0", "url": "https://…", "notes": "…"}``.
Понимаем и GitHub-релиз (``tag_name``/``name``), чтобы формат не пришлось
менять, если появится канал релизов. Сеть — единственный источник данных,
поэтому все ошибки возвращаются строкой статуса, а не исключением.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

STATUS_DISABLED = "disabled"
STATUS_UP_TO_DATE = "up-to-date"
STATUS_AVAILABLE = "available"
STATUS_ERROR = "error"

# Больше манифеста не читаем: чужой сервер не должен забить память.
MAX_BYTES = 64 * 1024
TIMEOUT = 5.0


def parse_version(text: object) -> tuple[int, ...]:
    """``v4.20.1`` → ``(4, 20, 1)``; хвост и мусор отбрасываются."""
    numbers = re.findall(r"\d+", str(text or ""))
    return tuple(int(n) for n in numbers[:4])


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def _result(status: str, message: str, latest: str | None = None,
            url: str | None = None) -> dict:
    return {"status": status, "message": message, "latest": latest, "url": url}


def check_for_updates(
    current_version: str,
    url: str | None = None,
    timeout: float = TIMEOUT,
) -> dict:
    """Сравнить текущую версию с манифестом. Никогда не бросает."""
    url = (url or "").strip()
    if not url:
        return _result(
            STATUS_DISABLED,
            "Адрес манифеста не задан — проверка обновлений выключена.",
        )
    if not url.lower().startswith(("http://", "https://")):
        return _result(STATUS_ERROR, "Адрес должен начинаться с http:// или https://.")

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read(MAX_BYTES)
    except (urllib.error.URLError, OSError, ValueError) as e:
        return _result(STATUS_ERROR, f"Не удалось получить манифест: {e}")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _result(STATUS_ERROR, "Манифест не является корректным JSON.")
    if not isinstance(payload, dict):
        return _result(STATUS_ERROR, "Манифест должен быть JSON-объектом.")

    latest = payload.get("version") or payload.get("tag_name") or payload.get("name")
    if not latest or not parse_version(latest):
        return _result(STATUS_ERROR, "В манифесте нет номера версии.")
    latest = str(latest)
    page = str(payload.get("url") or payload.get("html_url") or url)

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
