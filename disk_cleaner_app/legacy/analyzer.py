"""
analyzer.py — Disk Analyzer, Big Files, Duplicates, Empty Folders
"""

import os
import hashlib
from pathlib import Path
from typing import Optional
from disk_cleaner_app.legacy.core import format_bytes, get_dir_size


# ─────────────────────────────────────────────
# DISK ANALYZER — топ папок
# ─────────────────────────────────────────────

def scan_top_folders(root: str = "C:\\", limit: int = 50) -> list[dict]:
    """
    Сканирует корневые папки и возвращает топ-N по размеру.
    """
    results = []
    try:
        for entry in os.scandir(root):
            if entry.is_dir():
                try:
                    size = get_dir_size(Path(entry.path))
                    results.append({
                        "name": entry.name,
                        "path": entry.path,
                        "size": size,
                        "type": "folder",
                    })
                except Exception:
                    continue
        results.sort(key=lambda x: x["size"], reverse=True)
    except Exception:
        pass
    return results[:limit]


def scan_large_files(root: str, min_size_mb: int = 500, limit: int = 100) -> list[dict]:
    """
    Ищет файлы больше min_size_mb.
    Сканирует рекурсивно: C:\\Users, C:\\ProgramData, C:\\Temp, корень C:
    """
    min_size = min_size_mb * 1024 * 1024
    results = []
    scan_dirs = []

    if root == "C:\\":
        scan_dirs = [
            "C:\\Users",
            "C:\\ProgramData",
            "C:\\Temp",
        ]
        # Вершина C:\
        try:
            for entry in os.scandir("C:\\"):
                if entry.is_file():
                    try:
                        fsize = entry.stat().st_size
                        if fsize >= min_size:
                            results.append({
                                "name": entry.name,
                                "path": entry.path,
                                "size": fsize,
                            })
                    except Exception:
                        continue
        except Exception:
            pass
    else:
        scan_dirs = [root]

    for sdir in scan_dirs:
        try:
            for dirpath, dirnames, filenames in os.walk(sdir):
                # Skip Windows/System directories for speed
                skip_dirs = {"windows", "winxsxs", "system32", "syswow64",
                             "assembly", "installer", "msocache"}
                dirnames[:] = [d for d in dirnames if d.lower() not in skip_dirs]

                for fname in filenames:
                    try:
                        fpath = os.path.join(dirpath, fname)
                        fsize = os.path.getsize(fpath)
                        if fsize >= min_size:
                            results.append({
                                "name": fname,
                                "path": fpath,
                                "size": fsize,
                            })
                            if len(results) >= limit:
                                return results
                    except Exception:
                        continue

                if len(results) >= limit:
                    break
        except Exception:
            continue

    results.sort(key=lambda x: x["size"], reverse=True)
    return results[:limit]


# ─────────────────────────────────────────────
# DUPLICATE FINDER
# ─────────────────────────────────────────────

def find_duplicates_fast(root: str, min_size_kb: int = 100) -> list[dict]:
    """
    Быстрый поиск дубликатов: по имени + размеру.
    """
    min_size = min_size_kb * 1024
    seen = {}  # (name, size) -> path
    duplicates = []

    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip system dirs
            skip = {"windows", "winxsxs", "system32", "syswow64",
                    "$recycle.bin", "boot", "program files", "program files (x86)"}
            dirnames[:] = [d for d in dirnames if d.lower() not in skip]

            for fname in filenames:
                try:
                    fpath = os.path.join(dirpath, fname)
                    fsize = os.path.getsize(fpath)
                    if fsize < min_size:
                        continue

                    key = (fname.lower(), fsize)
                    if key in seen:
                        duplicates.append({
                            "name": fname,
                            "size": fsize,
                            "file1": seen[key],
                            "file2": fpath,
                        })
                    else:
                        seen[key] = fpath
                except Exception:
                    continue
    except Exception:
        pass

    return duplicates


def find_duplicates_exact(root: str, min_size_kb: int = 100) -> list[dict]:
    """
    Точный поиск дубликатов: по MD5 хэшу.
    """
    min_size = min_size_kb * 1024
    size_groups = {}
    duplicates = []

    # Шаг 1: группировка по размеру
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            skip = {"windows", "winxsxs", "system32", "syswow64",
                    "$recycle.bin", "boot", "program files", "program files (x86)"}
            dirnames[:] = [d for d in dirnames if d.lower() not in skip]

            for fname in filenames:
                try:
                    fpath = os.path.join(dirpath, fname)
                    fsize = os.path.getsize(fpath)
                    if fsize < min_size:
                        continue
                    size_groups.setdefault(fsize, []).append(fpath)
                except Exception:
                    continue
    except Exception:
        pass

    # Шаг 2: внутри групп одинакового размера — MD5
    for fsize, paths in size_groups.items():
        if len(paths) < 2:
            continue
        hash_map = {}
        for fpath in paths:
            try:
                h = _md5_file(fpath)
                hash_map.setdefault(h, []).append(fpath)
            except Exception:
                continue

        for h, dupe_paths in hash_map.items():
            if len(dupe_paths) >= 2:
                for i in range(1, len(dupe_paths)):
                    duplicates.append({
                        "name": Path(dupe_paths[0]).name,
                        "size": fsize,
                        "file1": dupe_paths[0],
                        "file2": dupe_paths[i],
                    })

    return duplicates


def _md5_file(fpath: str, chunk_size: int = 65536) -> str:
    """MD5 хэш файла."""
    h = hashlib.md5()
    with open(fpath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ─────────────────────────────────────────────
# EMPTY FOLDER FINDER
# ─────────────────────────────────────────────

def find_empty_folders(root: str) -> list[str]:
    """Находит пустые папки внутри root."""
    empty = []

    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Папка пуста если нет файлов и нет непустых подпапок
            if not filenames and not dirnames:
                empty.append(dirpath)
    except Exception:
        pass

    return empty


def remove_empty_folders(folders: list[str]) -> tuple[int, list[str]]:
    """Удаляет пустые папки. Возвращает (удалено, ошибки)."""
    removed = 0
    errors = []
    # Удаляем в обратном порядке (сначала вложенные)
    for fpath in sorted(folders, reverse=True):
        try:
            Path(fpath).rmdir()
            removed += 1
        except Exception as e:
            errors.append(fpath)
    return removed, errors


# ─────────────────────────────────────────────
# STARTUP MANAGER
# ─────────────────────────────────────────────

def get_startup_items() -> list[dict]:
    """Получает список программ в автозагрузке."""
    items = []

    # HKCU Run
    try:
        out, _ = subprocess_run(f'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" 2>nul')
        if out:
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].startswith("HKEY"):
                    continue
                if line.strip() and "    " in line:
                    name = line.split("    ")[0].strip()
                    items.append({"name": name, "source": "HKCU\\Run"})
    except Exception:
        pass

    # HKLM Run
    try:
        out, _ = subprocess_run(f'reg query "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" 2>nul')
        if out:
            for line in out.splitlines():
                if line.strip() and "    " in line:
                    name = line.split("    ")[0].strip()
                    items.append({"name": name, "source": "HKLM\\Run"})
    except Exception:
        pass

    # Startup folder
    try:
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if startup.exists():
            for f in startup.iterdir():
                items.append({"name": f.name, "source": "Startup Folder", "path": str(f)})
    except Exception:
        pass

    return items


def subprocess_run(cmd: str) -> tuple:
    """Внутренняя утилита."""
    import subprocess
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.stdout, r.stderr
    except Exception as e:
        return "", str(e)
