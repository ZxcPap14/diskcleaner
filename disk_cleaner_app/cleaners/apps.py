"""💬 Очистители приложений: Discord, Telegram, Slack, Zoom, Steam, etc."""
from __future__ import annotations

import os
from pathlib import Path

from disk_cleaner_app.cleaners.base import BaseCleaner, get_dir_size, safe_rm_contents
from disk_cleaner_app.models.item import GROUP_APPS, SafetyLevel, format_bytes
from disk_cleaner_app.models.target import LAYER_COMPONENTS, LAYER_SAFE
from disk_cleaner_app.services import wsl_compact
from disk_cleaner_app.services.elevation import is_admin

LOCAL = Path.home() / "AppData" / "Local"
ROAMING = Path.home() / "AppData" / "Roaming"
TEMP = Path.home() / "AppData" / "Local" / "Temp"


class DiscordCacheCleaner(BaseCleaner):
    id = "discord"
    name = "💬 Discord Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Discord\\app-*\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш Discord пересоздаётся; вход и настройки не затрагиваются."
    loss = "Каналы и вложения будут загружаться чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        base = LOCAL / "Discord"
        if not base.exists():
            return ()
        paths: list[Path] = []
        for folder in base.iterdir():
            if not folder.is_dir():
                continue
            for sub in ("Cache", "Code Cache", "GPUCache"):
                p = folder / sub
                if p.exists():
                    paths.append(p)
        return tuple(paths)

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if p.exists() and not safe_rm_contents(p):
                ok = False
        return ("OK", "Discord cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Discord"
        )


class TelegramCacheCleaner(BaseCleaner):
    id = "telegram"
    name = "💬 Telegram Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Telegram Desktop\\tdata\\user_data\\cache"
    safety = SafetyLevel.CAUTION
    layer = LAYER_SAFE
    why = "Медиа-кэш Telegram можно удалить; ключи и сессии в tdata не трогаем."
    loss = "Медиа будет скачано заново; аккаунт и история не пострадают."
    restore_hint = "Откройте Telegram — кэш заполнится сам."

    def _cache_dirs(self) -> list[Path]:
        user_data = ROAMING / "Telegram Desktop" / "tdata" / "user_data"
        if not user_data.exists():
            return []
        allowed = {"cache", "media_cache", "webview"}
        return [
            p for p in user_data.iterdir()
            if p.is_dir() and p.name.lower() in allowed
        ]

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._cache_dirs())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self._cache_dirs())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self._cache_dirs():
            if not safe_rm_contents(p):
                ok = False
        return ("OK", "Telegram cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Telegram и повторите."
        )


class SlackCacheCleaner(BaseCleaner):
    id = "slack"
    name = "💬 Slack Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Slack\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш Slack пересоздаётся; сообщения хранятся на сервере."
    loss = "Каналы будут загружаться чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        base = ROAMING / "Slack"
        candidates = [
            base / "Cache",
            base / "Code Cache",
            base / "GPUCache",
            base / "Service Worker" / "CacheStorage",
        ]
        return tuple(p for p in candidates if p.exists())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if not safe_rm_contents(p):
                ok = False
        return ("OK", "Slack cache очищен") if ok else ("ERR", "Ошибка")


class TeamsCacheCleaner(BaseCleaner):
    id = "teams"
    name = "💬 Microsoft Teams Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Microsoft\\Teams\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш классического Teams; сообщения и файлы хранятся в облаке."
    loss = "Teams загрузится чуть медленнее; вход сохраняется."

    def affected_paths(self) -> tuple[Path, ...]:
        base = ROAMING / "Microsoft" / "Teams"
        candidates = [
            base / "Cache",
            base / "Code Cache",
            base / "GPUCache",
            base / "Service Worker" / "CacheStorage",
        ]
        return tuple(p for p in candidates if p.exists())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if not safe_rm_contents(p):
                ok = False
        return ("OK", "Teams cache очищен") if ok else ("ERR", "Ошибка")


class ZoomCacheCleaner(BaseCleaner):
    id = "zoom"
    name = "💬 Zoom Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Zoom\\cache и logs"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш и логи Zoom; папку data с настройками не трогаем."
    loss = "Логи и временные файлы будут созданы заново."

    def affected_paths(self) -> tuple[Path, ...]:
        base = ROAMING / "Zoom"
        candidates = [base / "cache", base / "logs"]
        return tuple(p for p in candidates if p.exists())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = True
        for p in self.affected_paths():
            if not safe_rm_contents(p):
                ok = False
        return ("OK", "Zoom cache очищен") if ok else ("ERR", "Ошибка")


class YaMusicCacheCleaner(BaseCleaner):
    id = "yamusic"
    name = "🎵 Яндекс Музыка Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Yandex\\YandexMusic\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш музыки; треки скачаются заново."
    loss = "Офлайн-кэш пропадёт; плейлисты и аккаунт сохранятся."

    def affected_paths(self) -> tuple[Path, ...]:
        p = LOCAL / "Yandex" / "YandexMusic" / "Cache"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Яндекс Музыка cache очищен") if ok else ("ERR", "Ошибка")


class SteamCacheCleaner(BaseCleaner):
    id = "steam"
    name = "🎮 Steam HTML Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Steam\\htmlcache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "HTML-кэш клиента Steam; не связан с файлами игр."
    loss = "Магазин и библиотека загрузятся чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        p = LOCAL / "Steam" / "htmlcache"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Steam cache очищен") if ok else ("ERR", "Ошибка")


class SteamDepotCacheCleaner(BaseCleaner):
    id = "steam_depot"
    name = "🎮 Steam Depot Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Steam\\depotcache"
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    delete_mode = "remove"
    recommended = False
    why = "Манифесты установленных игр; Steam может проверить файлы заново."
    loss = "Проверка игр станет дольше; сами игры не удаляются."
    restore_hint = "Steam восстановит манифесты при следующем запуске."

    def affected_paths(self) -> tuple[Path, ...]:
        p = LOCAL / "Steam" / "depotcache"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Steam depot cache очищен") if ok else ("ERR", "Ошибка")


class ObsidianCacheCleaner(BaseCleaner):
    id = "obsidian"
    name = "📝 Obsidian Cache"
    group = GROUP_APPS
    description = "%RoamingAppData%\\Obsidian\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    why = "Кэш Obsidian; заметки и настройки хранятся отдельно."
    loss = "Заметки откроются чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        p = ROAMING / "Obsidian" / "Cache"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Obsidian cache очищен") if ok else ("ERR", "Ошибка")


class EpicGamesCacheCleaner(BaseCleaner):
    id = "epic"
    name = "🎮 Epic Games Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\EpicGamesLauncher\\Saved\\WebCache*"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Web-кэш лаунчера Epic Games; игры и вход не затрагиваются."
    loss = "Магазин Epic загрузится чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        base = LOCAL / "EpicGamesLauncher" / "Saved"
        if not base.exists():
            return ()
        return tuple(p for p in base.iterdir() if p.is_dir() and
                     p.name.lower().startswith("webcache"))

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Epic Games cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Epic Games Launcher"
        )


class AdobeCacheCleaner(BaseCleaner):
    id = "adobe"
    name = "🎨 Adobe Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Adobe\\Common\\Media Cache Files"
    safety = SafetyLevel.CAUTION
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш медиа Premiere/Media Encoder; пересоздаётся при открытии проектов."
    loss = "Открытие проектов с видео станет дольше (рендер превью заново)."
    restore_hint = "Adobe пересоздаст кэш автоматически."

    def affected_paths(self) -> tuple[Path, ...]:
        p = LOCAL / "Adobe" / "Common" / "Media Cache Files"
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Adobe media cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте приложения Adobe"
        )


class JavaCacheCleaner(BaseCleaner):
    id = "java_cache"
    name = "☕ Java Deployment Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\..\\LocalLow\\Sun\\Java\\Deployment\\cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш Java-аплетов и Web Start; пересоздаётся при необходимости."
    loss = "Первый запуск Java-приложений будет чуть дольше."

    def affected_paths(self) -> tuple[Path, ...]:
        p = (
            Path.home() / "AppData" / "LocalLow" / "Sun" / "Java" / "Deployment" / "cache"
        )
        return (p,) if p.exists() else ()

    def get_size(self) -> int:
        return get_dir_size(self.affected_paths()[0]) if self.affected_paths() else 0

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Java cache очищен") if ok else ("ERR", "Ошибка")


class WSLVhdxInfoCleaner(BaseCleaner):
    """Сжатие vhdx-дисков WSL2/Docker: данные внутри дистрибутива сохраняются."""

    id = "wsl_vhdx"
    name = "🐧 WSL: сжатие виртуальных дисков"
    group = GROUP_APPS
    description = (
        "wsl --shutdown + diskpart compact vdisk для ext4.vhdx WSL2 и Docker. "
        "Образ не удаляется, лишние блоки возвращаются хосту."
    )
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    admin_required = True
    recommended = False
    why = (
        "vhdx растёт, но не сжимается сам: после удаления файлов внутри WSL "
        "место на хосте остаётся занятым."
    )
    loss = (
        "Ничего не удаляется. WSL и Docker Desktop будут остановлены на время "
        "сжатия (от минуты до получаса в зависимости от размера)."
    )
    restore_hint = "Откат не нужен: данные внутри дистрибутива не меняются."

    def _vhdx(self) -> tuple[Path, ...]:
        base = LOCAL / "Packages"
        hits: list[Path] = []
        if base.exists():
            for distro in base.glob("CanonicalGroupLimited*"):
                p = distro / "LocalState" / "ext4.vhdx"
                if p.is_file():
                    hits.append(p)
        # Docker Desktop: тот же WSL2-механизм, тот же сценарий сжатия.
        docker = LOCAL / "Docker" / "wsl"
        for candidate in (docker / "disk" / "docker_data.vhdx",
                          docker / "data" / "ext4.vhdx"):
            if candidate.is_file():
                hits.append(candidate)
        return tuple(hits)

    def affected_paths(self) -> tuple[Path, ...]:
        # Командная цель: удалять пути движком нельзя, только сжимать.
        return ()

    def get_size(self) -> int:
        return sum(wsl_compact.vhdx_size(p) for p in self._vhdx())

    def clean(self) -> tuple[str, str]:
        paths = self._vhdx()
        if not paths:
            return ("SKIP", "Образы WSL/Docker не найдены.")
        if not is_admin():
            return ("ERR", "Нужны права администратора: сжатие выполняет diskpart.")
        freed, lines = wsl_compact.compact_paths(list(paths))
        details = "; ".join(lines)
        if freed > 0:
            return ("OK", f"Освобождено {format_bytes(freed)}. {details}")
        return (
            "OK",
            f"Сжатие выполнено, но размер не уменьшился (данные внутри образа "
            f"занимают всё место). {details}",
        )


class BattleNetCacheCleaner(BaseCleaner):
    """Кэш лаунчера Battle.net (квоты, агент, куки) — не файлы игр."""

    id = "battle_net"
    name = "🎮 Battle.net Cache"
    group = GROUP_APPS
    description = "%ProgramData%\\Battle.net\\Agent\\BlizzCache и кэши лаунчера"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш лаунчера Battle.net; игры и вход не затрагиваются."
    loss = "Лаунчер Battle.net загрузится чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        candidates = (
            data / "Battle.net" / "Agent" / "BlizzCache",
            data / "Battle.net" / "Agent" / "blizzard" / "Support",
            data / "Blizzard Entertainment" / "Battle.net" / "Cache",
        )
        return tuple(p for p in candidates if p.is_dir())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Battle.net cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Battle.net"
        )


class GogGalaxyCacheCleaner(BaseCleaner):
    """Web-кэш GOG Galaxy; библиотека игр хранится отдельно."""

    id = "gog_galaxy"
    name = "🎮 GOG Galaxy Cache"
    group = GROUP_APPS
    description = "%LocalAppData% и %ProgramData%\\GOG.com\\Galaxy\\webcache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Web-кэш и HTML-хранилища GOG Galaxy; игры и вход не затрагиваются."
    loss = "Интерфейс Galaxy загрузится чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        candidates = (
            LOCAL / "GOG.com" / "Galaxy" / "webcache",
            LOCAL / "GOG.com" / "Galaxy" / "webcache.inherited",
            data / "GOG.com" / "Galaxy" / "webcache",
        )
        return tuple(p for p in candidates if p.is_dir())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "GOG Galaxy cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте GOG Galaxy"
        )


class SpotifyCacheCleaner(BaseCleaner):
    """Офлайн-хранилище Spotify: персистентный кэш, а не временный."""

    id = "spotify"
    name = "🎵 Spotify Cache"
    group = GROUP_APPS
    description = "%AppData%\\Spotify\\Storage, %LocalAppData%\\Spotify\\Data"
    safety = SafetyLevel.CAUTION
    layer = LAYER_COMPONENTS
    recommended = False
    delete_mode = "contents"
    why = (
        "Хранилище кэша Spotify — один из самых больших кэшей на десктопе. "
        "Внутри могут быть и офлайн-загрузки, поэтому цель не выбрана по "
        "умолчанию и требует подтверждения."
    )
    loss = (
        "Офлайн-загрузки музыки пропадут и будут скачаны заново; "
        "логин, плейлисты и настройки не затрагиваются."
    )

    def affected_paths(self) -> tuple[Path, ...]:
        candidates = (
            ROAMING / "Spotify" / "Storage",
            LOCAL / "Spotify" / "Data",
        )
        return tuple(p for p in candidates if p.is_dir())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Spotify cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Spotify"
        )


class TeamsNewCacheCleaner(BaseCleaner):
    """Новые Teams (пакет MSTeams): только веб-кэши, LocalState не трогаем."""

    id = "teams_new"
    name = "💬 Teams (новый) Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\Packages\\MSTeams_8wekyb3d8bbwe (веб-кэши)"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = (
        "Веб-кэш нового Teams (EBWebView). LocalState и LocalCache целиком "
        "не трогаются — там настройки и вход."
    )
    loss = "Чаты и файлы загрузятся чуть медленнее; вход и история не затрагиваются."

    _WEBVIEW_SUBS = (
        ("Cache",),
        ("Code Cache",),
        ("GPUCache",),
        ("Service Worker", "CacheStorage"),
        ("Service Worker", "ScriptCache"),
    )

    def _candidates(self) -> list[Path]:
        base = (
            LOCAL / "Packages" / "MSTeams_8wekyb3d8bbwe"
            / "LocalCache" / "Microsoft" / "Teams"
        )
        paths: list[Path] = []
        webview_default = base / "EBWebView" / "Default"
        for sub in self._WEBVIEW_SUBS:
            paths.append(webview_default.joinpath(*sub))
        for sub in self._WEBVIEW_SUBS[:3]:
            paths.append(base.joinpath(*sub))
        return [p for p in paths if p.is_dir()]

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(self._candidates())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Teams (новый) cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Teams"
        )


class DiscordVariantsCacheCleaner(BaseCleaner):
    """PTB и Canary-версии Discord с теми же кэшами, что и основной."""

    id = "discord_ptb_canary"
    name = "💬 Discord PTB/Canary Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\DiscordPTB, DiscordCanary (Cache, Code Cache, GPUCache)"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "remove"
    why = "Кэш тестовых версий Discord пересоздаётся; вход и настройки не затрагиваются."
    loss = "Каналы и вложения будут загружаться чуть медленнее."

    def affected_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        for base_name in ("DiscordPTB", "DiscordCanary"):
            base = LOCAL / base_name
            if not base.exists():
                continue
            for folder in base.iterdir():
                if not folder.is_dir():
                    continue
                for sub in ("Cache", "Code Cache", "GPUCache"):
                    p = folder / sub
                    if p.exists():
                        paths.append(p)
        return tuple(paths)

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Discord PTB/Canary cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Discord"
        )


class QBittorrentCacheCleaner(BaseCleaner):
    """Кэш qBittorrent; fastresume и torrent-файлы не трогаем."""

    id = "qbittorrent"
    name = "🌀 qBittorrent Cache"
    group = GROUP_APPS
    description = "%LocalAppData%\\qBittorrent\\cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "contents"
    why = "Внутренний кэш qBittorrent; список раздач (fastresume) не затрагивается."
    loss = "Практически незаметно: кэш пересоздаётся на лету."

    def affected_paths(self) -> tuple[Path, ...]:
        candidates = (
            LOCAL / "qBittorrent" / "cache",
            ROAMING / "qBittorrent" / "cache",
        )
        return tuple(p for p in candidates if p.is_dir())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "qBittorrent cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте qBittorrent"
        )


class AdobeCameraRawCacheCleaner(BaseCleaner):
    """Кэш превью Camera Raw: тяжёлый, пересоздаётся из оригиналов."""

    id = "adobe_camera_raw"
    name = "🎨 Adobe Camera Raw Cache"
    group = GROUP_APPS
    description = "%AppData%\\Adobe\\CameraRaw\\Cache"
    safety = SafetyLevel.SAFE
    layer = LAYER_SAFE
    delete_mode = "contents"
    why = "Кэш превью RAW-файлов; оригиналы не трогаются."
    loss = "Lightroom/ACR перестроит превью при следующем просмотре."

    def affected_paths(self) -> tuple[Path, ...]:
        candidate = ROAMING / "Adobe" / "CameraRaw" / "Cache"
        return (candidate,) if candidate.is_dir() else ()

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", "Camera Raw cache очищен") if ok else (
            "ERR", "Часть кэша занята — закройте Adobe-приложения"
        )


APP_CLEANERS = [
    DiscordCacheCleaner,
    DiscordVariantsCacheCleaner,
    TelegramCacheCleaner,
    SlackCacheCleaner,
    TeamsCacheCleaner,
    TeamsNewCacheCleaner,
    ZoomCacheCleaner,
    YaMusicCacheCleaner,
    SpotifyCacheCleaner,
    SteamCacheCleaner,
    SteamDepotCacheCleaner,
    ObsidianCacheCleaner,
    EpicGamesCacheCleaner,
    AdobeCacheCleaner,
    AdobeCameraRawCacheCleaner,
    JavaCacheCleaner,
    QBittorrentCacheCleaner,
    WSLVhdxInfoCleaner,
    BattleNetCacheCleaner,
    GogGalaxyCacheCleaner,
]
