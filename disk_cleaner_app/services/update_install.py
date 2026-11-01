"""Скачивание и установка обновления поверх текущей папки приложения.

Работающий exe заменить нельзя, поэтому порядок такой: скачать zip →
распаковать во временную папку → запустить отдельный PowerShell-скрипт,
который дождётся выхода процесса, скопирует файлы поверх папки установки и
снова запустит exe → приложение закрывается само.

Ничего не удаляется: robocopy копирует с перезаписью, поэтому пользовательские
файлы рядом с exe и в %APPDATA% остаются на месте.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Больше этого обновление не принимаем: чужой сервер не должен забить диск.
MAX_DOWNLOAD = 300 * 1024 * 1024
TIMEOUT = 60.0


class UpdateError(RuntimeError):
    """Обновление не удалось; текст показывается пользователю."""


@dataclass
class Staged:
    """Распакованное обновление, готовое к применению."""

    source: Path      # папка с новыми файлами (там же новый exe)
    work_dir: Path    # временная папка, удаляется скриптом после копирования
    exe_name: str


def install_root() -> Path:
    """Папка установки — та, где лежит запущенный exe."""
    if not getattr(sys, "frozen", False):
        raise UpdateError(
            "Обновление доступно только для собранного приложения."
        )
    return Path(sys.executable).resolve().parent


def download(url: str, target: Path, timeout: float = TIMEOUT) -> Path:
    if not url.lower().startswith(("http://", "https://")):
        raise UpdateError("Адрес обновления должен начинаться с http(s)://")
    request = urllib.request.Request(url, headers={"User-Agent": "DiskCleaner"})
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with target.open("wb") as handle:
                while chunk := response.read(1024 * 256):
                    written += len(chunk)
                    if written > MAX_DOWNLOAD:
                        raise UpdateError("Файл обновления слишком большой.")
                    handle.write(chunk)
    except urllib.error.HTTPError as e:
        raise UpdateError(f"Не удалось скачать обновление: HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"Не удалось скачать обновление: {e}") from e
    if written == 0:
        raise UpdateError("Сервер вернул пустой файл обновления.")
    return target


def verify_sha256(path: Path, digest: str | None) -> None:
    """Сверить скачанный файл с ``sha256:<hex>`` из описания релиза."""
    if not digest:
        return
    expected = digest.split(":", 1)[-1].strip().lower()
    if len(expected) != 64:
        log.warning("Неизвестный формат хэша обновления: %r", digest)
        return
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise UpdateError("Контрольная сумма обновления не совпала.")


def _payload_dir(root: Path) -> Path:
    """Если в архиве одна папка верхнего уровня — обновление внутри неё."""
    entries = list(root.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return root


def stage(
    url: str, digest: str | None = None, timeout: float = TIMEOUT
) -> Staged:
    """Скачать и распаковать обновление; замена файлов — в apply()."""
    work_dir = Path(tempfile.mkdtemp(prefix="DiskCleanerUpdate-"))
    try:
        archive = download(url, work_dir / "update.zip", timeout=timeout)
        verify_sha256(archive, digest)
        unpacked = work_dir / "app"
        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(unpacked)
        except (zipfile.BadZipFile, OSError) as e:
            raise UpdateError(f"Архив обновления повреждён: {e}") from e
        source = _payload_dir(unpacked)
        exe_name = Path(sys.executable).name
        if not (source / exe_name).is_file():
            raise UpdateError(f"В обновлении нет {exe_name}.")
        return Staged(source=source, work_dir=work_dir, exe_name=exe_name)
    except BaseException:
        _remove(work_dir)
        raise


def _remove(path: Path) -> None:
    for attempt in range(3):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            if attempt == 2:
                log.warning("Не удалось удалить %s", path)
            else:
                time.sleep(0.5)


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def updater_script(staged: Staged, target: Path) -> Path:
    """Скрипт, который заменит файлы после выхода приложения и запустит его."""
    script = staged.work_dir / "apply-update.ps1"
    log_path = staged.work_dir / "update.log"
    body = f"""$ErrorActionPreference = 'Continue'
$oldPid = {os.getpid()}
while (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {{
    Start-Sleep -Milliseconds 400
}}
Start-Sleep -Milliseconds 600
& robocopy {_ps_quote(str(staged.source))} {_ps_quote(str(target))} /E /R:10 /W:1 /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -ge 8) {{
    "robocopy failed: $LASTEXITCODE" | Out-File -Encoding utf8 {_ps_quote(str(log_path))}
    exit 1
}}
Start-Process -FilePath (Join-Path {_ps_quote(str(target))} {_ps_quote(staged.exe_name)})
Start-Sleep -Milliseconds 800
Remove-Item -LiteralPath {_ps_quote(str(staged.work_dir))} -Recurse -Force -ErrorAction SilentlyContinue
"""
    # utf-8-sig: Windows PowerShell 5.1 читает файл без BOM как ANSI и ломает
    # кириллицу в путях.
    script.write_text(body, encoding="utf-8-sig")
    return script


def apply(staged: Staged) -> Path:
    """Запустить фоновый скрипт замены файлов; приложение должно закрыться."""
    target = install_root()
    if not os.access(target, os.W_OK):
        raise UpdateError(
            f"Нет прав на запись в {target}. Запустите приложение "
            "с правами администратора."
        )
    script = updater_script(staged, target)
    args = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden", "-File", str(script),
    ]
    detach = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    # Приложение может работать внутри job-объекта (запуск из терминала или
    # планировщика): тогда потомок умирает вместе с ним. Пробуем вырваться,
    # а если job это запрещает — обычный отвязанный запуск.
    for flags in (detach | breakaway, detach):
        try:
            subprocess.Popen(args, creationflags=flags, close_fds=True)
            break
        except OSError as exc:
            error = exc
    else:
        raise UpdateError(f"Не удалось запустить обновление: {error}")
    log.info("Обновление запущено: %s -> %s", staged.source, target)
    return target
