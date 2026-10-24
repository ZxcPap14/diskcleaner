"""🖥️ Системные очистители: корзина, temp, prefetch, thumbs, WER, DNS, etc."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from disk_cleaner_app.cleaners.base import (
    BaseCleaner,
    get_dir_size,
    get_path_size,
    list_drives,
    run_cmd,
    run_powershell,
    safe_rm_contents,
)
from disk_cleaner_app.models.item import GROUP_SYSTEM, SafetyLevel
from disk_cleaner_app.models.target import LAYER_SAFE, LAYER_SYSTEM
from disk_cleaner_app.services.elevation import is_admin

USER = Path.home()
LOCAL_APPDATA = USER / "AppData" / "Local"
ROAMING_APPDATA = USER / "AppData" / "Roaming"
WINDIR = Path(os.environ.get("SystemRoot", "C:\\Windows"))
PROGRAMDATA = Path(os.environ.get("ProgramData", "C:\\ProgramData"))


# ── Корзина ────────────────────────────────────────────

class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004


def _recycle_size(root: str) -> int:
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(info)
    try:
        hr = ctypes.windll.shell32.SHQueryRecycleBinW(root, ctypes.byref(info))
    except (AttributeError, OSError):
        return 0
    return int(info.i64Size) if hr == 0 else 0


def _recycle_total() -> int:
    total = 0
    for root, _free, _total in list_drives():
        total += _recycle_size(root)
    return total


class RecycleBinCleaner(BaseCleaner):
    id = "recycle"
    name = "🗑️ Корзина"
    group = GROUP_SYSTEM
    description = "Корзина на всех готовых томах"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Файлы в корзине уже удалены пользователем и занимают место на всех томах."
    loss = "Восстановить файлы из корзины после очистки нельзя."
    restore_hint = "Откат невозможен; очищайте только если файлы больше не нужны."

    def get_size(self) -> int:
        total = _recycle_total()
        if total:
            return total
        # Fallback для систем без Shell API.
        rb = Path(os.environ.get("SystemDrive", "C:") + "\\$Recycle.Bin")
        return get_dir_size(rb) if rb.exists() else 0

    def clean(self) -> tuple[str, str]:
        failures: list[str] = []
        before = _recycle_total()
        for root, _free, _total in list_drives():
            try:
                hr = ctypes.windll.shell32.SHEmptyRecycleBinW(
                    None, root,
                    SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND,
                )
                # 0x8000FFFF — корзина уже пуста, это не ошибка.
                if hr not in (0, -2147418113):
                    failures.append(f"{root}: 0x{hr & 0xFFFFFFFF:08X}")
            except (AttributeError, OSError) as e:
                failures.append(f"{root}: {e}")

        if not is_admin() and before and _recycle_total() >= before:
            return "ERR", "Не удалось очистить корзину: нужны права администратора."
        if failures:
            return "ERR", "Корзина очищена не полностью: " + "; ".join(failures[:3])
        return "OK", "Корзина очищена на всех томах"


# ── Temp ───────────────────────────────────────────────

class WindowsTempCleaner(BaseCleaner):
    id = "win_temp"
    name = "🗂️ Windows Temp"
    group = GROUP_SYSTEM
    description = "C:\\Windows\\Temp (старше 24 часов)"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    admin_required = True
    min_age_hours = 24
    paths = (WINDIR / "Temp",)
    why = "Временные файлы Windows; свежие не трогаем, чтобы не сломать установку."
    loss = "Только временные файлы старше суток; приложения создадут их заново."

    def get_size(self) -> int:
        return get_dir_size(WINDIR / "Temp")

    def clean(self) -> tuple[str, str]:
        ok = safe_rm_contents(WINDIR / "Temp", to_recycle=False)
        return ("OK", "Windows Temp очищен") if ok else ("ERR", "Ошибка очистки Windows Temp")


class UserTempCleaner(BaseCleaner):
    id = "user_temp"
    name = "🗂️ Пользовательские Temp"
    group = GROUP_SYSTEM
    description = "%TEMP% (старше 24 часов)"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    min_age_hours = 24
    why = "Временные файлы пользователя; возрастной фильтр защищает активные установщики."
    loss = "Только временные файлы старше суток; приложения создадут их заново."

    @property
    def _temp(self) -> Path:
        return Path(os.environ.get("TEMP", LOCAL_APPDATA / "Temp"))

    def affected_paths(self) -> tuple[Path, ...]:
        return (self._temp,)

    def get_size(self) -> int:
        return get_dir_size(self._temp)

    def clean(self) -> tuple[str, str]:
        ok = safe_rm_contents(self._temp, to_recycle=False)
        return ("OK", "Temp очищен") if ok else ("ERR", "Ошибка очистки Temp")


# ── Prefetch ───────────────────────────────────────────

class PrefetchCleaner(BaseCleaner):
    id = "prefetch"
    name = "⚡ Prefetch"
    group = GROUP_SYSTEM
    description = "C:\\Windows\\Prefetch"
    safety = SafetyLevel.CAUTION
    layer = LAYER_SYSTEM
    admin_required = True
    recommended = False
    paths = (WINDIR / "Prefetch",)
    why = "Windows сам управляет Prefetch; место обычно небольшое."
    loss = "Первый запуск программ может стать медленнее. По умолчанию выключено."

    def get_size(self) -> int:
        return get_dir_size(WINDIR / "Prefetch")

    def clean(self) -> tuple[str, str]:
        ok = safe_rm_contents(WINDIR / "Prefetch", to_recycle=False)
        return ("OK", "Prefetch очищен") if ok else ("ERR", "Ошибка")


# ── Эскизы ─────────────────────────────────────────────

class ThumbnailCacheCleaner(BaseCleaner):
    id = "thumbs"
    name = "🖼️ Кэш эскизов"
    group = GROUP_SYSTEM
    description = "thumbcache_*.db, iconcache_*.db"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Базы эскизов и иконок пересоздаются проводником автоматически."
    loss = "Проводник заново построит миниатюры; окна не закрываются."

    def _files(self) -> list[Path]:
        base = LOCAL_APPDATA / "Microsoft" / "Windows" / "Explorer"
        if not base.exists():
            return []
        files = list(base.glob("thumbcache_*.db"))
        files += list(base.glob("iconcache_*.db"))
        return [p for p in files if p.is_file()]

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._files())

    def get_size(self) -> int:
        return sum(get_path_size(p) for p in self._files())

    def clean(self) -> tuple[str, str]:
        # Explorer не убиваем: занятые файлы просто пропускаются.
        ok = True
        for p in self._files():
            try:
                p.unlink()
            except OSError:
                ok = False
        return ("OK", "Кэш эскизов очищен") if ok else (
            "ERR", "Часть файлов занята проводником — закройте окна и повторите."
        )


# ── WER и дампы ────────────────────────────────────────

class WindowsErrorReportingCleaner(BaseCleaner):
    id = "wer"
    name = "📋 Отчёты об ошибках (WER)"
    group = GROUP_SYSTEM
    description = "%LocalAppData%\\Microsoft\\Windows\\WER"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    paths = (LOCAL_APPDATA / "Microsoft" / "Windows" / "WER",)
    why = "Отчёты о падениях нужны только для разбора; старые можно удалить."
    loss = "После удаления нельзя разобрать причину старых падений."

    def get_size(self) -> int:
        p = self.paths[0]
        return get_dir_size(p) if p.exists() else 0

    def clean(self) -> tuple[str, str]:
        p = self.paths[0]
        if not p.exists():
            return ("OK", "Нет отчётов WER")
        ok = safe_rm_contents(p, to_recycle=False)
        return ("OK", "WER очищен") if ok else ("ERR", "Ошибка")


class SystemWerCleaner(BaseCleaner):
    id = "wer_system"
    name = "📋 Системные отчёты WER"
    group = GROUP_SYSTEM
    description = "%ProgramData%\\Microsoft\\Windows\\WER"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    admin_required = True
    paths = (PROGRAMDATA / "Microsoft" / "Windows" / "WER",)
    why = "Системные отчёты о падениях; требуют прав администратора."
    loss = "Нельзя разобрать старые системные падения."

    def get_size(self) -> int:
        p = self.paths[0]
        return get_dir_size(p) if p.exists() else 0

    def clean(self) -> tuple[str, str]:
        ok = safe_rm_contents(self.paths[0], to_recycle=False)
        return ("OK", "Системный WER очищен") if ok else (
            "ERR", "Нужны права администратора или файлы заняты."
        )


class CrashDumpsCleaner(BaseCleaner):
    id = "crash_dumps"
    name = "💥 Дампы приложений"
    group = GROUP_SYSTEM
    description = "%LocalAppData%\\CrashDumps"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    paths = (LOCAL_APPDATA / "CrashDumps",)
    why = "Дампы упавших приложений нужны только для отладки."
    loss = "Нельзя разобрать причину старых падений приложений."

    def get_size(self) -> int:
        p = self.paths[0]
        return get_dir_size(p) if p.exists() else 0

    def clean(self) -> tuple[str, str]:
        ok = safe_rm_contents(self.paths[0], to_recycle=False)
        return ("OK", "Дампы приложений очищены") if ok else ("ERR", "Ошибка")


class MemoryDumpsCleaner(BaseCleaner):
    id = "dumps"
    name = "🧠 Дампы памяти"
    group = GROUP_SYSTEM
    description = "C:\\Windows\\Minidump, MEMORY.DMP, LiveKernelReports"
    safety = SafetyLevel.SAFE
    layer = LAYER_SYSTEM
    admin_required = True
    paths = (
        WINDIR / "Minidump",
        WINDIR / "MEMORY.DMP",
        WINDIR / "LiveKernelReports",
    )
    why = "Системные дампы нужны только для разбора падений; могут занимать гигабайты."
    loss = "Нельзя разобрать причину старых системных падений."

    def get_size(self) -> int:
        return sum(get_path_size(p) for p in self.paths if p.exists())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.paths:
            if p.is_file():
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    ok = False
            elif p.exists():
                if not safe_rm_contents(p, to_recycle=False):
                    ok = False
        return ("OK", "Дампы удалены") if ok else (
            "ERR", "Часть дампов занята или нет прав администратора"
        )


# ── Windows Update / Delivery Optimization ─────────────

class WindowsUpdateCacheCleaner(BaseCleaner):
    id = "wu_cache"
    name = "🔄 Кэш Windows Update"
    group = GROUP_SYSTEM
    description = "C:\\Windows\\SoftwareDistribution\\Download"
    safety = SafetyLevel.CAUTION
    layer = LAYER_SYSTEM
    admin_required = True
    recommended = False
    why = "Скачанные обновления можно загрузить заново; службы останавливаются на время."
    loss = "Обновления будут скачаны повторно; текущая установка не затрагивается."
    restore_hint = "Проверить обновления в Windows Update."

    def get_size(self) -> int:
        p = WINDIR / "SoftwareDistribution" / "Download"
        return get_dir_size(p) if p.exists() else 0

    def clean(self) -> tuple[str, str]:
        if not is_admin():
            return ("ERR", "Нужны права администратора: службы WU не будут остановлены.")
        # Службы, которые работали до очистки, обязаны работать после;
        # маркер SVC_DOWN в stdout — exit-код PowerShell теряется в run_powershell.
        ps = (
            "$ErrorActionPreference='Stop'; "
            "$svc=@('wuauserv','bits','dosvc'); "
            "$was=@{}; foreach($s in $svc){ $was[$s]=(Get-Service $s -ErrorAction SilentlyContinue).Status }; "
            "try { foreach($s in $svc){ Stop-Service $s -Force -ErrorAction SilentlyContinue }; "
            f"Remove-Item '{WINDIR / 'SoftwareDistribution' / 'Download'}\\*' -Recurse -Force -ErrorAction Stop "
            "} finally { foreach($s in $svc){ if($was[$s] -eq 'Running'){ Start-Service $s -ErrorAction SilentlyContinue } } }; "
            "$down=@(); foreach($s in $svc){ "
            "if($was[$s] -eq 'Running' -and (Get-Service $s -ErrorAction SilentlyContinue).Status -ne 'Running'){ $down+=$s } "
            "}; if($down.Count){ 'SVC_DOWN: ' + ($down -join ',') } else { 'OK' }"
        )
        out, err = run_powershell(ps, timeout=60)
        if err:
            return ("ERR", f"Ошибка очистки WU: {err[:200]}")
        if "SVC_DOWN" in out:
            return (
                "ERR",
                f"Кэш очищен, но службы не восстановлены: {out.split(':', 1)[-1][:120]}",
            )
        if "OK" not in out:
            return ("ERR", f"Неожиданный ответ очистки WU: {out[:200]}")
        return ("OK", "Кэш Windows Update очищен, службы восстановлены")


class DeliveryOptimizationCleaner(BaseCleaner):
    id = "delivery_opt"
    name = "📦 Delivery Optimization"
    group = GROUP_SYSTEM
    description = "Delete-DeliveryOptimizationCache"
    safety = SafetyLevel.CAUTION
    layer = LAYER_SYSTEM
    admin_required = True
    recommended = False
    why = "Кэш раздачи обновлений между устройствами; поддерживаемая команда Windows."
    loss = "Обновления будут скачаны заново; настройки DO не меняются."
    restore_hint = "Windows заново заполнит кэш при обновлении."

    def get_size(self) -> int:
        candidates = (
            WINDIR / "ServiceProfiles" / "NetworkService" / "AppData" / "Local"
            / "Microsoft" / "Windows" / "DeliveryOptimization" / "Cache",
            WINDIR / "SoftwareDistribution" / "DeliveryOptimization",
        )
        return sum(get_dir_size(p) for p in candidates if p.exists())

    def clean(self) -> tuple[str, str]:
        if not is_admin():
            return ("ERR", "Нужны права администратора.")
        out, err = run_powershell(
            "Delete-DeliveryOptimizationCache -Force -ErrorAction Stop; 'OK'",
            timeout=60,
        )
        if err or "OK" not in out:
            return ("ERR", f"Не удалось очистить DO: {err[:200] or out[:200]}")
        return ("OK", "Кэш Delivery Optimization очищен")


# ── Служебные ──────────────────────────────────────────

class FontCacheCleaner(BaseCleaner):
    id = "font_cache"
    name = "🔤 Кэш шрифтов"
    group = GROUP_SYSTEM
    description = "%LocalAppData%\\Microsoft\\Windows\\FontCache"
    safety = SafetyLevel.CAUTION
    layer = LAYER_SYSTEM
    recommended = False
    paths = (LOCAL_APPDATA / "Microsoft" / "Windows" / "FontCache",)
    why = "Кэш шрифтов; выгода обычно небольшая, а риск сбоя выше пользы."
    loss = "Возможны временные проблемы с отображением шрифтов."

    def get_size(self) -> int:
        p = self.paths[0]
        return get_dir_size(p) if p.exists() else 0

    def clean(self) -> tuple[str, str]:
        ok = safe_rm_contents(self.paths[0], to_recycle=False)
        return ("OK", "Кэш шрифтов очищен") if ok else ("ERR", "Ошибка")


class DNSCacheCleaner(BaseCleaner):
    id = "dns_cache"
    name = "🌐 DNS Cache"
    group = GROUP_SYSTEM
    description = "ipconfig /flushdns"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Сброс DNS-кэша — полезное действие, но он не освобождает место."
    loss = "Ничего не теряется; кэш заполнится заново."

    def get_size(self) -> int:
        return 0

    def clean(self) -> tuple[str, str]:
        run_cmd("ipconfig /flushdns")
        return ("OK", "DNS кэш сброшен")


class CbsLogsCleaner(BaseCleaner):
    id = "cbs_logs"
    name = "📝 Логи обслуживания Windows"
    group = GROUP_SYSTEM
    description = "CBS / DISM / Panther (старше 30 дней)"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    admin_required = True
    min_age_hours = 24 * 30
    paths = (
        WINDIR / "Logs" / "CBS",
        WINDIR / "Logs" / "DISM",
        WINDIR / "Panther",
    )
    why = "Диагностические логи старше 30 дней; свежие нужны для поддержки."
    loss = "Нельзя разобрать старые логи обслуживания."

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.paths if p.exists())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.paths:
            if p.exists() and not safe_rm_contents(p, to_recycle=False):
                ok = False
        return ("OK", "Логи очищены") if ok else ("ERR", "Часть логов занята или нет прав")


class GpuShaderCacheCleaner(BaseCleaner):
    id = "gpu_cache"
    name = "🎮 Кэш шейдеров GPU"
    group = GROUP_SYSTEM
    description = "D3DSCache, NVIDIA DXCache/GLCache, AMD, Intel"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    paths = (
        LOCAL_APPDATA / "D3DSCache",
        LOCAL_APPDATA / "NVIDIA" / "DXCache",
        LOCAL_APPDATA / "NVIDIA" / "GLCache",
        LOCAL_APPDATA / "AMD" / "DxCache",
        LOCAL_APPDATA / "AMD" / "GLCache",
        LOCAL_APPDATA / "Intel" / "ShaderCache",
    )
    why = "Скомпилированные шейдеры; драйвер соберёт их заново при первом запуске игры."
    loss = "Первый запуск игры или 3D-приложения будет немного дольше."

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.paths if p.exists())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.paths:
            if p.exists() and not safe_rm_contents(p, to_recycle=False):
                ok = False
        return ("OK", "Кэш шейдеров очищен") if ok else (
            "ERR", "Часть кэша занята игрой или драйвером — закройте приложения."
        )


class InternetCacheCleaner(BaseCleaner):
    id = "inet_cache"
    name = "🌐 Кэш интернета (INetCache)"
    group = GROUP_SYSTEM
    description = "%LocalAppData%\\Microsoft\\Windows\\INetCache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    paths = (LOCAL_APPDATA / "Microsoft" / "Windows" / "INetCache",)
    why = "Кэш WinINet/WebView2; страницы и ресурсы загрузятся заново."
    loss = "Некоторые встроенные страницы откроются чуть медленнее."

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.paths if p.exists())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.paths:
            if p.exists() and not safe_rm_contents(p, to_recycle=False):
                ok = False
        return ("OK", "INetCache очищен") if ok else (
            "ERR", "Часть файлов занята — закройте приложения и повторите."
        )


# ── Список всех системных очистителей ──
SYSTEM_CLEANERS = [
    RecycleBinCleaner,
    WindowsTempCleaner,
    UserTempCleaner,
    CrashDumpsCleaner,
    ThumbnailCacheCleaner,
    WindowsErrorReportingCleaner,
    SystemWerCleaner,
    MemoryDumpsCleaner,
    CbsLogsCleaner,
    WindowsUpdateCacheCleaner,
    DeliveryOptimizationCleaner,
    DNSCacheCleaner,
    GpuShaderCacheCleaner,
    InternetCacheCleaner,
    PrefetchCleaner,
]
