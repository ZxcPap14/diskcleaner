"""
core.py — CleanupItem, helpers, конфиг, история
"""

import os
import shutil
import subprocess
import json
import sqlite3
import hashlib
import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional

# ─────────────────────────────────────────────
# Пути
# ─────────────────────────────────────────────

USER = Path.home()
LOCAL_APP_DATA = USER / "AppData" / "Local"
ROAMING_APP_DATA = USER / "AppData" / "Roaming"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(USER / "AppData" / "Roaming"))) / "DiskCleaner"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_DB = CONFIG_DIR / "history.db"
CUSTOM_RULES_FILE = CONFIG_DIR / "custom_rules.json"


# ─────────────────────────────────────────────
# Форматирование
# ─────────────────────────────────────────────

def format_bytes(b: int) -> str:
    """Форматирует байты в читаемый вид."""
    if b < 1024:
        return f"{b} Б"
    elif b < 1024 ** 2:
        return f"{b / 1024:.1f} КБ"
    elif b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f} МБ"
    else:
        return f"{b / 1024 ** 3:.2f} ГБ"


# ─────────────────────────────────────────────
# Работа с размером
# ─────────────────────────────────────────────

def get_dir_size(path: Path) -> int:
    """Быстро вычисляет размер папки (обходит ошибки доступа)."""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    fsize = entry.stat().st_size
                    if fsize > 0:
                        total += fsize
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError, FileNotFoundError):
        pass
    return total


def get_disk_free() -> tuple:
    """Возвращает (свободно_байт, всего_байт) для диска C:."""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-PSDrive C | ForEach-Object { Write-Output \"$($_.Free) $($_.Used)\" }"],
            capture_output=True, text=True, timeout=10
        )
        parts = result.stdout.strip().split()
        if len(parts) >= 2:
            free = int(parts[0])
            used = int(parts[1])
            return free, free + used
    except Exception:
        pass
    try:
        st = os.statvfs("C:\\")
        free = st.f_bavail * st.f_frsize
        total = st.f_blocks * st.f_frsize
        return free, total
    except Exception:
        return 0, 0


# ─────────────────────────────────────────────
# Безопасное удаление
# ─────────────────────────────────────────────

def safe_rmtree(path: Path, to_recycle: bool = True) -> bool:
    """
    Удаляет папку.
    to_recycle=True → использует PowerShell для перемещения в корзину (undo).
    to_recycle=False → полное удаление.
    """
    if not path.exists():
        return True
    if to_recycle:
        try:
            # PowerShell Move to Recycle Bin
            script = (
                f"$path = '{path.as_posix()}'; "
                f"$shell = New-Object -ComObject Shell.Application; "
                f"$item = $shell.Namespace(0).ParseName($path); "
                f"if ($item) {{ $item.InvokeVerb('delete') }}"
            )
            subprocess.run(["powershell", "-Command", script],
                           capture_output=True, timeout=30)
            return not path.exists()
        except Exception:
            pass
    try:
        shutil.rmtree(path, ignore_errors=True)
        return not path.exists()
    except Exception:
        return False


def safe_rm_contents(path: Path, to_recycle: bool = True) -> bool:
    """Удаляет содержимое папки, но не саму папку."""
    if not path.exists():
        return True
    try:
        for item in path.iterdir():
            try:
                if item.is_dir():
                    safe_rmtree(item, to_recycle)
                else:
                    if to_recycle:
                        _send_to_recycle(item)
                    else:
                        item.unlink(missing_ok=True)
            except Exception:
                continue
        return True
    except Exception:
        return False


def _send_to_recycle(path: Path):
    """Отправляет файл в корзину через PowerShell."""
    try:
        script = (
            f"$path = '{path.as_posix()}'; "
            f"$shell = New-Object -ComObject Shell.Application; "
            f"$item = $shell.Namespace(0).ParseName($path); "
            f"if ($item) {{ $item.InvokeVerb('delete') }}"
        )
        subprocess.run(["powershell", "-Command", script],
                       capture_output=True, timeout=15)
    except Exception:
        pass


# ─────────────────────────────────────────────
# Запуск команд
# ─────────────────────────────────────────────

def run_powershell(script: str, timeout: int = 60) -> tuple:
    """Запускает PowerShell скрипт, возвращает (stdout, stderr)."""
    try:
        result = subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "Timeout"
    except Exception as e:
        return "", str(e)


def run_cmd(command: str, timeout: int = 60) -> tuple:
    """Запускает cmd команду."""
    try:
        result = subprocess.run(
            ["cmd.exe", "/c", command],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "Timeout"
    except Exception as e:
        return "", str(e)


# ─────────────────────────────────────────────
# CleanupItem
# ─────────────────────────────────────────────

class SafetyLevel:
    SAFE = "🟢"
    CAUTION = "🟡"
    ADVANCED = "🔴"


@dataclass
class CleanupItem:
    """Одна цель очистки."""
    id: str
    name: str
    group: str
    description: str
    safety: str  # SafetyLevel
    get_size: Callable[[], int]
    clean: Callable[[], tuple[str, str]]
    size: int = 0
    scanned: bool = False
    file_count: int = 0
    can_preview: bool = False
    preview_path: Optional[str] = None


# ─────────────────────────────────────────────
# Конфиг
# ─────────────────────────────────────────────

def ensure_config():
    """Создаёт папку конфига если нет."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Загружает конфиг."""
    ensure_config()
    default = {
        "safe_mode": True,
        "to_recycle": True,
        "theme": "dark",
        "last_scan": None,
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update(data)
        except Exception:
            pass
    return default


def save_config(data: dict):
    """Сохраняет конфиг."""
    ensure_config()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────
# История (SQLite)
# ─────────────────────────────────────────────

def ensure_history_db():
    """Создаёт БД истории если нет."""
    ensure_config()
    try:
        conn = sqlite3.connect(str(HISTORY_DB))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                items_cleaned INTEGER,
                bytes_freed INTEGER,
                details TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


def add_history(items_cleaned: int, bytes_freed: int, details: str = ""):
    """Добавляет запись в историю."""
    try:
        ensure_history_db()
        conn = sqlite3.connect(str(HISTORY_DB))
        conn.execute(
            "INSERT INTO history (date, items_cleaned, bytes_freed, details) VALUES (?, ?, ?, ?)",
            (datetime.datetime.now().isoformat(), items_cleaned, bytes_freed, details)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_history(limit: int = 20) -> list:
    """Возвращает историю очисток."""
    try:
        ensure_history_db()
        conn = sqlite3.connect(str(HISTORY_DB))
        cursor = conn.execute(
            "SELECT date, items_cleaned, bytes_freed FROM history ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def get_total_freed() -> int:
    """Суммарное освобождённое место за всё время."""
    try:
        ensure_history_db()
        conn = sqlite3.connect(str(HISTORY_DB))
        cursor = conn.execute("SELECT COALESCE(SUM(bytes_freed), 0) FROM history")
        total = cursor.fetchone()[0]
        conn.close()
        return total
    except Exception:
        return 0


# ─────────────────────────────────────────────
# Пользовательские правила
# ─────────────────────────────────────────────

def load_custom_rules() -> list[dict]:
    """Загружает пользовательские пути для очистки."""
    ensure_config()
    if CUSTOM_RULES_FILE.exists():
        try:
            with open(CUSTOM_RULES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_custom_rules(rules: list[dict]):
    """Сохраняет пользовательские пути."""
    ensure_config()
    try:
        with open(CUSTOM_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_custom_rule(name: str, path: str, safety: str = SafetyLevel.CAUTION):
    """Добавляет пользовательское правило."""
    rules = load_custom_rules()
    rule_id = f"custom_{len(rules)}_{int(datetime.datetime.now().timestamp())}"
    rules.append({
        "id": rule_id,
        "name": name,
        "path": path,
        "safety": safety,
    })
    save_custom_rules(rules)
    return rule_id


def remove_custom_rule(rule_id: str):
    """Удаляет пользовательское правило."""
    rules = load_custom_rules()
    rules = [r for r in rules if r["id"] != rule_id]
    save_custom_rules(rules)


# ─────────────────────────────────────────────
# Экспорт отчёта
# ─────────────────────────────────────────────

def export_report(items: list, freed_bytes: int, filename: str):
    """Экспортирует отчёт об очистке в файл."""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("🧹 Отчёт об очистке DiskCleaner\n")
            f.write(f"Дата: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Освобождено: {format_bytes(freed_bytes)}\n")
            f.write("=" * 50 + "\n\n")
            for item in items:
                f.write(f"{'✅' if item.scanned else '❌'} {item.name}: {format_bytes(item.size)}\n")
            f.write(f"\nВсего: {format_bytes(freed_bytes)}\n")
        return True
    except Exception:
        return False
