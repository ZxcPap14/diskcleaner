"""Запущенные приложения, мешающие очистке их кэша.

Самая частая причина «освободилось 0» — занятые файлы браузера.
Один вызов ``tasklist /NH /FO CSV`` даёт список процессов; совпадение
с целью плана превращается в предупреждение до удаления.
"""
from __future__ import annotations

import csv
import io
import logging
import subprocess
from collections.abc import Iterable

log = logging.getLogger(__name__)

# target_id → имена процессов (без учёта регистра).
TARGET_PROCESSES: dict[str, tuple[str, ...]] = {
    "chrome_cache": ("chrome.exe",),
    "edge_cache": ("msedge.exe",),
    "yandex_cache": ("yandex.exe",),
    "brave_cache": ("brave.exe",),
    "vivaldi_cache": ("vivaldi.exe",),
    "opera_cache": ("opera.exe",),
    "firefox_cache": ("firefox.exe",),
    "telegram": ("telegram.exe",),
    "discord": ("discord.exe",),
    "slack": ("slack.exe",),
    "teams": ("teams.exe", "ms-teams.exe"),
    "zoom": ("zoom.exe",),
    "yamusic": ("yandexmusic.exe", "yamusic.exe"),
    "steam": ("steam.exe", "steamwebhelper.exe"),
    "vscode_ext": ("code.exe",),
}

# Печатные названия процессов для сообщений.
PROCESS_LABELS = {
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "yandex.exe": "Yandex Browser",
    "brave.exe": "Brave",
    "vivaldi.exe": "Vivaldi",
    "opera.exe": "Opera",
    "firefox.exe": "Firefox",
    "telegram.exe": "Telegram",
    "discord.exe": "Discord",
    "slack.exe": "Slack",
    "teams.exe": "Teams",
    "ms-teams.exe": "Teams",
    "zoom.exe": "Zoom",
    "yandexmusic.exe": "Яндекс Музыка",
    "yamusic.exe": "Яндекс Музыка",
    "steam.exe": "Steam",
    "steamwebhelper.exe": "Steam",
    "code.exe": "VS Code",
}


def running_processes(timeout: int = 30) -> set[str]:
    """Нижним регистром: имена процессов из tasklist; пусто при сбое."""
    try:
        result = subprocess.run(
            ["tasklist", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = result.stdout or ""
    except (OSError, subprocess.SubprocessError) as e:
        log.info("tasklist недоступен: %s", e)
        return set()

    names: set[str] = set()
    try:
        for row in csv.reader(io.StringIO(output)):
            if row:
                name = row[0].strip().lower()
                # tasklist всегда указывает расширение; строки без него —
                # мусор от кириллических текущих строк без колонок.
                if name.endswith(".exe"):
                    names.add(name)
    except csv.Error:
        # На странных локалях CSV может ломаться; пробуем грубый разбор.
        for line in output.splitlines():
            if line.startswith('"'):
                names.add(line.split('","')[0].strip('"').lower())
    return names


def detect_running(
    target_ids: Iterable[str], processes: set[str]
) -> dict[str, list[str]]:
    """target_id → названия запущенных приложений, его касающихся."""
    detected: dict[str, list[str]] = {}
    for target_id in target_ids:
        labels = [
            PROCESS_LABELS.get(name, name)
            for name in TARGET_PROCESSES.get(target_id, ())
            if name in processes
        ]
        if labels:
            detected[target_id] = labels
    return detected


def warnings_for_targets(
    target_ids: Iterable[str], processes: set[str] | None = None
) -> list[str]:
    """Предупреждения для плана: «Chrome запущен — файлы будут пропущены…»."""
    if processes is None:
        processes = running_processes()
    if not processes:
        return []
    detected = detect_running(target_ids, processes)
    warnings: list[str] = []
    for target_id in sorted(detected):
        labels = " и ".join(sorted(set(detected[target_id])))
        warnings.append(
            f"{labels} запущен — часть файлов кэша занята, "
            "она будет пропущена; остальное очистится."
        )
    return warnings
