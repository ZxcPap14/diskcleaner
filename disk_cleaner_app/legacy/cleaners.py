"""
cleaners.py — 30+ целей очистки по группам
"""

import os
from pathlib import Path
from disk_cleaner_app.legacy.core import (
    CleanupItem, SafetyLevel,
    USER, LOCAL_APP_DATA, ROAMING_APP_DATA,
    get_dir_size, format_bytes,
    safe_rmtree, safe_rm_contents,
    run_powershell, run_cmd,
)


def define_items() -> list[CleanupItem]:
    """Создаёт и возвращает список всех целей очистки."""
    items = []

    # ─────────────────────────────────────────────
    # 🖥️ СИСТЕМА
    # ─────────────────────────────────────────────

    # --- Корзина ---
    def scan_recycle():
        try:
            return get_dir_size(Path("C:\\$RECYCLE.BIN"))
        except Exception:
            return 0

    def clean_recycle():
        out, err = run_powershell("Clear-RecycleBin -Force 2>$null")
        if "Не удается" in err or "Cannot" in err:
            try:
                for p in Path("C:\\$RECYCLE.BIN").iterdir():
                    safe_rmtree(p, to_recycle=False)
            except Exception:
                pass
            return "OK", "Корзина очищена"
        return "OK", "Корзина очищена"

    items.append(CleanupItem(
        id="recycle", name="🗑️ Корзина", group="🖥️ Система",
        description="C:\\$RECYCLE.BIN — удалённые файлы",
        safety=SafetyLevel.SAFE,
        get_size=scan_recycle, clean=clean_recycle,
        can_preview=False,
    ))

    # --- C:\Temp ---
    def scan_c_temp():
        p = Path("C:\\Temp")
        return get_dir_size(p) if p.exists() else 0

    def clean_c_temp():
        ok = safe_rm_contents(Path("C:\\Temp"))
        return ("OK", "C:\\Temp очищен") if ok else ("ERR", "Не удалось очистить C:\\Temp")

    items.append(CleanupItem(
        id="c_temp", name="📁 C:\\Temp", group="🖥️ Система",
        description="Временные файлы в корне C:",
        safety=SafetyLevel.SAFE,
        get_size=scan_c_temp, clean=clean_c_temp,
        can_preview=True, preview_path="C:\\Temp",
    ))

    # --- Windows Temp ---
    def scan_win_temp():
        p = Path("C:\\Windows\\Temp")
        return get_dir_size(p) if p.exists() else 0

    def clean_win_temp():
        ok = safe_rm_contents(Path("C:\\Windows\\Temp"))
        return ("OK", "Windows Temp очищен") if ok else ("ERR", "Не удалось очистить")

    items.append(CleanupItem(
        id="win_temp", name="🪟 Windows Temp", group="🖥️ Система",
        description="C:\\Windows\\Temp — системные временные файлы",
        safety=SafetyLevel.SAFE,
        get_size=scan_win_temp, clean=clean_win_temp,
        can_preview=True, preview_path="C:\\Windows\\Temp",
    ))

    # --- User Temp ---
    def scan_user_temp():
        p = LOCAL_APP_DATA / "Temp"
        return get_dir_size(p) if p.exists() else 0

    def clean_user_temp():
        ok = safe_rm_contents(LOCAL_APP_DATA / "Temp")
        return ("OK", "User Temp очищен") if ok else ("ERR", "Не удалось очистить")

    items.append(CleanupItem(
        id="user_temp", name="👤 User Temp", group="🖥️ Система",
        description=f"{LOCAL_APP_DATA}\\Temp",
        safety=SafetyLevel.SAFE,
        get_size=scan_user_temp, clean=clean_user_temp,
        can_preview=True, preview_path=str(LOCAL_APP_DATA / "Temp"),
    ))

    # --- Thumbnails (эскизы) ---
    def scan_thumbs():
        p = LOCAL_APP_DATA / "Microsoft" / "Windows" / "Explorer"
        return get_dir_size(p) if p.exists() else 0

    def clean_thumbs():
        ok = safe_rm_contents(LOCAL_APP_DATA / "Microsoft" / "Windows" / "Explorer")
        return ("OK", "Thumbnails очищены") if ok else ("ERR", "Не удалось очистить")

    items.append(CleanupItem(
        id="thumbs", name="🖼️ Thumbnails кеш", group="🖥️ Система",
        description="Эскизы изображений (авто-восстановятся)",
        safety=SafetyLevel.SAFE,
        get_size=scan_thumbs, clean=clean_thumbs,
    ))

    # --- Prefetch ---
    def scan_prefetch():
        p = Path("C:\\Windows\\Prefetch")
        return get_dir_size(p) if p.exists() else 0

    def clean_prefetch():
        ok = safe_rm_contents(Path("C:\\Windows\\Prefetch"), to_recycle=False)
        return ("OK", "Prefetch очищен") if ok else ("ERR", "Не удалось очистить")

    items.append(CleanupItem(
        id="prefetch", name="⚡ Prefetch", group="🖥️ Система",
        description="Кеш предзагрузки приложений",
        safety=SafetyLevel.CAUTION,
        get_size=scan_prefetch, clean=clean_prefetch,
    ))

    # --- Windows Error Reporting ---
    def scan_wer():
        p = LOCAL_APP_DATA / "Microsoft" / "Windows" / "WER"
        return get_dir_size(p) if p.exists() else 0

    def clean_wer():
        ok = safe_rm_contents(LOCAL_APP_DATA / "Microsoft" / "Windows" / "WER")
        return ("OK", "WER очищен") if ok else ("ERR", "Не удалось очистить")

    items.append(CleanupItem(
        id="wer", name="📋 WER (Error Reports)", group="🖥️ Система",
        description="Отчёты об ошибках Windows",
        safety=SafetyLevel.SAFE,
        get_size=scan_wer, clean=clean_wer,
    ))

    # --- Memory dumps ---
    def scan_dumps():
        total = 0
        for f in Path("C:\\").glob("*.dmp"):
            try:
                total += f.stat().st_size
            except Exception:
                pass
        for f in Path("C:\\Windows").glob("*.dmp"):
            try:
                total += f.stat().st_size
            except Exception:
                pass
        return total

    def clean_dumps():
        count = 0
        for pattern in ["C:\\*.dmp", "C:\\Windows\\*.dmp"]:
            out, err = run_cmd(f"del /f /q {pattern} 2>nul")
            count += 1
        return ("OK", "Дампы памяти удалены") if count else ("OK", "Дампов не найдено")

    items.append(CleanupItem(
        id="dumps", name="💾 Memory dumps", group="🖥️ Система",
        description="Файлы дампов памяти (*.dmp)",
        safety=SafetyLevel.SAFE,
        get_size=scan_dumps, clean=clean_dumps,
    ))

    # --- Windows Update Cache ---
    def scan_wu():
        p = Path("C:\\Windows\\SoftwareDistribution\\Download")
        return get_dir_size(p) if p.exists() else 0

    def clean_wu():
        ok = safe_rm_contents(Path("C:\\Windows\\SoftwareDistribution\\Download"), to_recycle=False)
        return ("OK", "Windows Update кеш очищен") if ok else ("ERR", "Не удалось очистить")

    items.append(CleanupItem(
        id="wu_cache", name="🔄 Windows Update кеш", group="🖥️ Система",
        description="C:\\Windows\\SoftwareDistribution\\Download",
        safety=SafetyLevel.ADVANCED,
        get_size=scan_wu, clean=clean_wu,
    ))

    # --- Font cache ---
    def scan_font():
        p = Path("C:\\Windows\\ServiceProfiles\\LocalService\\AppData\\Local\\FontCache")
        return get_dir_size(p) if p.exists() else 0

    def clean_font():
        p = Path("C:\\Windows\\ServiceProfiles\\LocalService\\AppData\\Local\\FontCache")
        ok = safe_rm_contents(p)
        return ("OK", "Font cache очищен") if ok else ("OK", "Font cache не найден")

    items.append(CleanupItem(
        id="font_cache", name="🔤 Font cache", group="🖥️ Система",
        description="Кеш шрифтов Windows",
        safety=SafetyLevel.CAUTION,
        get_size=scan_font, clean=clean_font,
    ))

    # --- DNS cache (через ipconfig) ---
    def scan_dns():
        return 0  # размер неизвестен, но очистка полезна

    def clean_dns():
        out, err = run_cmd("ipconfig /flushdns 2>&1")
        if "успешно" in out.lower() or "successfully" in out.lower():
            return ("OK", "DNS кеш очищен")
        return ("OK", "DNS кеш очищен")

    items.append(CleanupItem(
        id="dns_cache", name="🌐 DNS cache", group="🖥️ Система",
        description="Кеш DNS (ipconfig /flushdns)",
        safety=SafetyLevel.SAFE,
        get_size=scan_dns, clean=clean_dns,
    ))

    # ─────────────────────────────────────────────
    # 🌐 БРАУЗЕРЫ
    # ─────────────────────────────────────────────

    def chrome_dir():
        return LOCAL_APP_DATA / "Google" / "Chrome" / "User Data" / "Default"

    def _make_browser_cache(name, emoji, data_dir, safety, desc=""):
        """Создаёт 3 цели для браузера: Cache, Code Cache, Service Worker."""
        items_list = []

        for sub, label in [("Cache", "Cache"), ("Code Cache", "Code Cache"),
                           ("Service Worker/CacheStorage", "Service Worker")]:
            sub_path = data_dir / sub

            def scan_fn(p=sub_path):
                return get_dir_size(p) if p.exists() else 0

            def clean_fn(p=sub_path, l=label):
                ok = safe_rm_contents(p)
                return ("OK", f"{emoji} {l} очищен") if ok else ("ERR", f"{l} занят")

            item_id = f"{name}_{sub.lower().replace('/', '_')}"
            items_list.append(CleanupItem(
                id=item_id, name=f"{emoji} {name} {label}",
                group="🌐 Браузеры",
                description=desc or f"Кеш {label}",
                safety=safety,
                get_size=scan_fn, clean=clean_fn,
            ))
        return items_list

    chrome_items = _make_browser_cache(
        "Chrome", "🌐", chrome_dir(), SafetyLevel.SAFE,
        "Кеш Google Chrome"
    )
    items.extend(chrome_items)

    # Edge (Chromium-based)
    edge_dir = LOCAL_APP_DATA / "Microsoft" / "Edge" / "User Data" / "Default"
    if edge_dir.exists():
        edge_items = _make_browser_cache(
            "Edge", "🌐", edge_dir, SafetyLevel.SAFE
        )
        items.extend(edge_items)

    # YandexBrowser
    yandex_dir = LOCAL_APP_DATA / "Yandex" / "YandexBrowser" / "User Data" / "Default"
    if yandex_dir.exists():
        yandex_items = _make_browser_cache(
            "YandexBrowser", "🌐", yandex_dir, SafetyLevel.SAFE
        )
        items.extend(yandex_items)

    # Firefox
    def _find_firefox_profile():
        profiles = ROAMING_APP_DATA / "Mozilla" / "Firefox" / "Profiles"
        if not profiles.exists():
            return None
        for p in profiles.iterdir():
            if p.is_dir() and (p / "cache2").exists():
                return p
        return None

    def scan_firefox():
        prof = _find_firefox_profile()
        if not prof:
            return 0
        total = 0
        for sub in ["cache2", "offlinecache"]:
            sp = prof / sub
            if sp.exists():
                total += get_dir_size(sp)
        return total

    def clean_firefox():
        prof = _find_firefox_profile()
        if not prof:
            return ("OK", "Firefox не найден")
        for sub in ["cache2", "offlinecache"]:
            sp = prof / sub
            if sp.exists():
                safe_rm_contents(sp)
        return ("OK", "Firefox кеш очищен")

    items.append(CleanupItem(
        id="firefox_cache", name="🦊 Firefox cache", group="🌐 Браузеры",
        description="cache2 + offlinecache",
        safety=SafetyLevel.SAFE,
        get_size=scan_firefox, clean=clean_firefox,
    ))

    # ─────────────────────────────────────────────
    # 📦 DEV TOOLS
    # ─────────────────────────────────────────────

    # npm
    def scan_npm():
        p = LOCAL_APP_DATA / "npm-cache"
        return get_dir_size(p) if p.exists() else 0

    def clean_npm():
        out, err = run_cmd("npm cache clean --force 2>&1")
        return ("OK", "npm cache очищен") if not err else ("OK", "npm cache очищен")

    items.append(CleanupItem(
        id="npm", name="📦 npm cache", group="📦 Dev Tools",
        description=f"{LOCAL_APP_DATA}\\npm-cache",
        safety=SafetyLevel.SAFE,
        get_size=scan_npm, clean=clean_npm,
    ))

    # pip
    def scan_pip():
        p = LOCAL_APP_DATA / "pip"
        return get_dir_size(p) if p.exists() else 0

    def clean_pip():
        out, err = run_cmd("pip cache purge 2>&1")
        return ("OK", "pip cache очищен") if "removed" in out.lower() else ("OK", out.strip()[:100])

    items.append(CleanupItem(
        id="pip", name="🐍 pip cache", group="📦 Dev Tools",
        description=f"{LOCAL_APP_DATA}\\pip",
        safety=SafetyLevel.SAFE,
        get_size=scan_pip, clean=clean_pip,
    ))

    # Yarn
    def scan_yarn():
        p = LOCAL_APP_DATA / "Yarn"
        return get_dir_size(p) if p.exists() else 0

    def clean_yarn():
        ok = safe_rmtree(LOCAL_APP_DATA / "Yarn")
        return ("OK", "Yarn cache удалён") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="yarn", name="🧶 Yarn cache", group="📦 Dev Tools",
        description=f"{LOCAL_APP_DATA}\\Yarn",
        safety=SafetyLevel.SAFE,
        get_size=scan_yarn, clean=clean_yarn,
    ))

    # uv
    def scan_uv():
        p = LOCAL_APP_DATA / "uv" / "cache"
        return get_dir_size(p) if p.exists() else 0

    def clean_uv():
        out, err = run_cmd("uv cache clean --force 2>&1")
        return ("OK", "uv cache очищен") if not err else ("WARN", f"uv: {err[:80]}")

    items.append(CleanupItem(
        id="uv", name="🧪 uv cache", group="📦 Dev Tools",
        description=f"{LOCAL_APP_DATA}\\uv\\cache",
        safety=SafetyLevel.SAFE,
        get_size=scan_uv, clean=clean_uv,
    ))

    # Bun
    def scan_bun():
        p = USER / ".bun" / "install"
        return get_dir_size(p) if p.exists() else 0

    def clean_bun():
        ok = safe_rmtree(USER / ".bun" / "install")
        return ("OK", "Bun cache удалён") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="bun", name="🥟 Bun cache", group="📦 Dev Tools",
        description="~/.bun/install",
        safety=SafetyLevel.SAFE,
        get_size=scan_bun, clean=clean_bun,
    ))

    # Rust (puccinialin)
    def scan_rust():
        p = LOCAL_APP_DATA / "puccinialin"
        return get_dir_size(p) if p.exists() else 0

    def clean_rust():
        ok = safe_rmtree(LOCAL_APP_DATA / "puccinialin")
        return ("OK", "Rust toolchain удалён") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="rust", name="🦀 Rust cache (puccinialin)", group="📦 Dev Tools",
        description="Автоустановленный Rust toolchain",
        safety=SafetyLevel.SAFE,
        get_size=scan_rust, clean=clean_rust,
    ))

    # Gradle
    def scan_gradle():
        p = USER / ".gradle" / "caches"
        return get_dir_size(p) if p.exists() else 0

    def clean_gradle():
        ok = safe_rmtree(USER / ".gradle" / "caches")
        return ("OK", "Gradle cache удалён") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="gradle", name="📦 Gradle cache", group="📦 Dev Tools",
        description="~/.gradle/caches",
        safety=SafetyLevel.SAFE,
        get_size=scan_gradle, clean=clean_gradle,
    ))

    # Playwright
    def scan_playwright():
        p = LOCAL_APP_DATA / "ms-playwright"
        return get_dir_size(p) if p.exists() else 0

    def clean_playwright():
        ok = safe_rmtree(LOCAL_APP_DATA / "ms-playwright")
        return ("OK", "Playwright браузеры удалены") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="playwright", name="🎭 Playwright браузеры", group="📦 Dev Tools",
        description="Браузеры для тестов",
        safety=SafetyLevel.SAFE,
        get_size=scan_playwright, clean=clean_playwright,
    ))

    # VS Code extensions
    def scan_vscode():
        p = USER / ".vscode" / "extensions"
        return get_dir_size(p) if p.exists() else 0

    def clean_vscode():
        ok = safe_rmtree(USER / ".vscode" / "extensions")
        return ("OK", "VS Code extensions удалены") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="vscode_ext", name="🧩 VS Code extensions", group="📦 Dev Tools",
        description="Расширения (переустановятся)",
        safety=SafetyLevel.CAUTION,
        get_size=scan_vscode, clean=clean_vscode,
    ))

    # Antigravity IDE extensions
    def scan_antigravity():
        p = USER / ".antigravity-ide" / "extensions"
        return get_dir_size(p) if p.exists() else 0

    def clean_antigravity():
        ok = safe_rmtree(USER / ".antigravity-ide" / "extensions")
        return ("OK", "Antigravity extensions удалены") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="antigravity_ext", name="🧩 Antigravity IDE ext", group="📦 Dev Tools",
        description="Расширения Antigravity IDE",
        safety=SafetyLevel.CAUTION,
        get_size=scan_antigravity, clean=clean_antigravity,
    ))

    # ─────────────────────────────────────────────
    # 🤖 AI/ML
    # ─────────────────────────────────────────────

    # Whisper
    def scan_whisper():
        p = USER / ".cache" / "whisper"
        return get_dir_size(p) if p.exists() else 0

    def clean_whisper():
        ok = safe_rmtree(USER / ".cache" / "whisper")
        return ("OK", "Whisper модель удалена") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="whisper", name="🎙️ Whisper модель", group="🤖 AI/ML",
        description="Модель распознавания речи (~3.5 ГБ)",
        safety=SafetyLevel.SAFE,
        get_size=scan_whisper, clean=clean_whisper,
    ))

    # HuggingFace
    def scan_hf():
        p = USER / ".cache" / "huggingface"
        return get_dir_size(p) if p.exists() else 0

    def clean_hf():
        ok = safe_rmtree(USER / ".cache" / "huggingface")
        return ("OK", "HuggingFace кеш удалён") if ok else ("ERR", "Не удалось удалить")

    items.append(CleanupItem(
        id="huggingface", name="🤗 HuggingFace кеш", group="🤖 AI/ML",
        description="Модели HuggingFace",
        safety=SafetyLevel.SAFE,
        get_size=scan_hf, clean=clean_hf,
    ))

    # LM Studio
    def scan_lmstudio():
        p = USER / ".lmstudio"
        return get_dir_size(p) if p.exists() else 0

    def clean_lmstudio():
        for sub in ["bin", "extensions"]:
            safe_rmtree(USER / ".lmstudio" / sub)
        return ("OK", "LM Studio кеш удалён")

    items.append(CleanupItem(
        id="lmstudio", name="🤖 LM Studio cache", group="🤖 AI/ML",
        description="Бинарники и расширения",
        safety=SafetyLevel.SAFE,
        get_size=scan_lmstudio, clean=clean_lmstudio,
    ))

    # ─────────────────────────────────────────────
    # 💬 ПРИЛОЖЕНИЯ
    # ─────────────────────────────────────────────

    # Discord
    def scan_discord():
        p = LOCAL_APP_DATA / "Discord"
        if not p.exists():
            return 0
        total = 0
        for d in p.iterdir():
            if d.is_dir():
                for sub in ["Cache", "Code Cache"]:
                    sp = d / sub
                    if sp.exists():
                        total += get_dir_size(sp)
        return total

    def clean_discord():
        p = LOCAL_APP_DATA / "Discord"
        if not p.exists():
            return ("OK", "Discord не найден")
        count = 0
        for d in p.iterdir():
            if d.is_dir():
                for sub in ["Cache", "Code Cache"]:
                    sp = d / sub
                    if sp.exists():
                        if safe_rm_contents(sp):
                            count += 1
        return ("OK", f"Discord кеш очищен ({count} папок)") if count else ("WARN", "Кеш не найден (возможно, запущен)")

    items.append(CleanupItem(
        id="discord", name="💬 Discord кеш", group="💬 Приложения",
        description="Кеш Discord (Cache, Code Cache)",
        safety=SafetyLevel.SAFE,
        get_size=scan_discord, clean=clean_discord,
    ))

    # Telegram
    def scan_telegram():
        p = ROAMING_APP_DATA / "Telegram Desktop" / "tdata" / "user_data"
        if not p.exists():
            return 0
        total = 0
        for folder in ["cache", "media_cache"]:
            sp = p / folder
            if sp.exists():
                total += get_dir_size(sp)
        return total

    def clean_telegram():
        p = ROAMING_APP_DATA / "Telegram Desktop" / "tdata" / "user_data"
        if not p.exists():
            return ("OK", "Telegram не найден")
        folders = []
        for folder in ["cache", "media_cache"]:
            sp = p / folder
            if sp.exists():
                safe_rm_contents(sp)
                folders.append(folder)
        if folders:
            return ("OK", f"Telegram кеш очищен: {', '.join(folders)}")
        return ("WARN", "Кеш не найден (возможно, запущен)")

    items.append(CleanupItem(
        id="telegram", name="✈️ Telegram кеш", group="💬 Приложения",
        description="Кеш медиа Telegram",
        safety=SafetyLevel.SAFE,
        get_size=scan_telegram, clean=clean_telegram,
    ))

    # Slack
    def scan_slack():
        p = ROAMING_APP_DATA / "Slack" / "Cache"
        return get_dir_size(p) if p.exists() else 0

    def clean_slack():
        ok = safe_rm_contents(ROAMING_APP_DATA / "Slack" / "Cache")
        return ("OK", "Slack кеш очищен") if ok else ("OK", "Slack не найден")

    items.append(CleanupItem(
        id="slack", name="💬 Slack кеш", group="💬 Приложения",
        description="Кеш Slack",
        safety=SafetyLevel.SAFE,
        get_size=scan_slack, clean=clean_slack,
    ))

    # Zoom
    def scan_zoom():
        p = ROAMING_APP_DATA / "Zoom" / "data"
        return get_dir_size(p) if p.exists() else 0

    def clean_zoom():
        p = ROAMING_APP_DATA / "Zoom" / "data"
        if p.exists():
            safe_rm_contents(p)
            return ("OK", "Zoom кеш очищен")
        return ("OK", "Zoom не найден")

    items.append(CleanupItem(
        id="zoom", name="🎥 Zoom cache", group="💬 Приложения",
        description="Кеш Zoom",
        safety=SafetyLevel.SAFE,
        get_size=scan_zoom, clean=clean_zoom,
    ))

    # YandexMusic
    def scan_yamusic():
        p = ROAMING_APP_DATA / "YandexMusic"
        return get_dir_size(p) if p.exists() else 0

    def clean_yamusic():
        ok = safe_rm_contents(ROAMING_APP_DATA / "YandexMusic")
        return ("OK", "YandexMusic кеш очищен") if ok else ("OK", "Не найден")

    items.append(CleanupItem(
        id="yamusic", name="🎵 YandexMusic cache", group="💬 Приложения",
        description="Кеш музыки",
        safety=SafetyLevel.CAUTION,
        get_size=scan_yamusic, clean=clean_yamusic,
    ))

    # Steam cache
    def scan_steam():
        p = LOCAL_APP_DATA / "Steam"
        if not p.exists():
            return 0
        total = 0
        for sub in ["htmlcache", "appcache"]:
            sp = p / sub
            if sp.exists():
                total += get_dir_size(sp)
        return total

    def clean_steam():
        found = False
        for sub in ["htmlcache", "appcache"]:
            sp = LOCAL_APP_DATA / "Steam" / sub
            if sp.exists():
                safe_rm_contents(sp)
                found = True
        return ("OK", "Steam кеш очищен") if found else ("OK", "Steam не найден")

    items.append(CleanupItem(
        id="steam", name="🎮 Steam cache", group="💬 Приложения",
        description="Кеш Steam (htmlcache, appcache)",
        safety=SafetyLevel.SAFE,
        get_size=scan_steam, clean=clean_steam,
    ))

    # ─────────────────────────────────────────────
    # 🧩 ПОЛЬЗОВАТЕЛЬСКИЕ ПРАВИЛА
    # ─────────────────────────────────────────────

    from disk_cleaner_app.legacy.core import load_custom_rules

    custom_rules = load_custom_rules()
    for rule in custom_rules:
        rpath = Path(rule["path"])
        rid = rule.get("id", f"custom_{len(items)}")
        rname = rule.get("name", rpath.name)

        def make_custom_size_fn(p: Path) -> callable:
            return lambda: get_dir_size(p) if p.exists() else 0

        def make_custom_clean_fn(p: Path) -> callable:
            def clean():
                if p.is_dir():
                    ok = safe_rm_contents(p)
                else:
                    try:
                        p.unlink(missing_ok=True)
                        ok = True
                    except Exception:
                        ok = False
                return ("OK", f"{p.name} очищен") if ok else ("ERR", f"Не удалось удалить {p.name}")
            return clean

        items.append(CleanupItem(
            id=rid,
            name=f"📌 {rname}",
            group="🧩 Пользовательские",
            description=str(rpath),
            safety=rule.get("safety", SafetyLevel.CAUTION),
            get_size=make_custom_size_fn(rpath),
            clean=make_custom_clean_fn(rpath),
            can_preview=rpath.is_dir() if rpath.exists() else False,
            preview_path=str(rpath) if rpath.is_dir() else None,
        ))

    return items
