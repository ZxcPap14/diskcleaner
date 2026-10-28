"""PyInstaller build script: python build.py

Собирает один exe-файл без консоли. Легаси-модули (core.py, gui.py, cleaners.py,
scanners.py, analyzer.py в корне пакета) исключены из сборки: приложение их не
использует, но и удалять их без решения владельца проекта нельзя.

Флаг ``--uac-admin`` добавляет в exe манифест requireAdministrator: Windows
будет запрашивать UAC при каждом запуске. По умолчанию приложение стартует
без повышения прав (UAC — по кнопке 🛡️).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Консоль Windows часто cp1251 и не умеет печатать эмодзи.
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        continue
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

APP_NAME = "DiskCleaner"
MAIN_SCRIPT = os.path.join("disk_cleaner_app", "__main__.py")
DIST_DIR = "dist"
BUILD_DIR = "build"
ICON_PATH = os.path.join("assets", "diskcleaner.ico")
VERSION_FILE = os.path.join(BUILD_DIR, "version_info.txt")

# Старые монолитные модули: в сборку не попадают.
# NumPy/SciPy/pandas/matplotlib попадают в граф зависимостей только через
# необязательный `squarify.plot` (matplotlib) и весят ~25 МБ, хотя приложение
# их не импортирует. AVIF/WebP-плагины Pillow тоже не нужны: CustomTkinter
# рисует PNG/ICO. Без них установщик вдвое меньше.
EXCLUDES = [
    "disk_cleaner_app.legacy",
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "PIL._avif",
    "PIL._webp",
]


def clean_old_builds() -> None:
    for directory in (BUILD_DIR, DIST_DIR):
        if os.path.exists(directory):
            shutil.rmtree(directory)


def project_version() -> str:
    """Прочитать версию из `disk_cleaner_app/__init__.py`."""
    try:
        text = Path("disk_cleaner_app", "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def write_version_file(version: str) -> str:
    """Сгенерировать version resource для свойств exe."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    parts = [p for p in version.split(".") if p.isdigit()]
    while len(parts) < 4:
        parts.append("0")
    nums = tuple(int(p) for p in parts[:4])
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={nums},
    prodvers={nums},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'ZCode'),
        StringStruct('FileDescription', 'DiskCleaner Pro - очистка и диагностика диска'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'DiskCleaner'),
        StringStruct('LegalCopyright', 'MIT License'),
        StringStruct('OriginalFilename', 'DiskCleaner.exe'),
        StringStruct('ProductName', 'DiskCleaner Pro'),
        StringStruct('ProductVersion', '{version}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(VERSION_FILE, "w", encoding="utf-8") as handle:
        handle.write(content)
    return os.path.abspath(VERSION_FILE)


def build_command(
    uac_admin: bool = False,
    version_file: str | None = None,
    web: bool = False,
) -> list[str]:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--clean",
        "--noconfirm",
        "--name", "DiskCleanerWeb" if web else APP_NAME,
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        "--specpath", BUILD_DIR,
        "--collect-data", "customtkinter",
        "--hidden-import", "customtkinter",
        "--hidden-import", "squarify",
        # pystray выбирает бэкенд динамически — без этого трей молча
        # отсутствует в собранном exe.
        "--hidden-import", "pystray",
        "--hidden-import", "pystray._win32",
    ]
    if web:
        # pywebview грузит WinForms-бэкенд и WebView2-лоадер по имени
        # (pythonnet/clr), поэтому их нужно тянуть целиком, а не по импортам.
        cmd += [
            "--collect-all", "webview",
            "--hidden-import", "webview.platforms.winforms",
            "--hidden-import", "clr",
            "--hidden-import", "pythonnet",
        ]
    if os.path.exists(ICON_PATH):
        cmd += ["--icon", os.path.abspath(ICON_PATH)]
    assets_dir = os.path.abspath("assets")
    if os.path.isdir(assets_dir):
        # Иконка трея лежит в assets; onefile кладёт её в _MEIPASS.
        cmd += ["--add-data", f"{assets_dir}{os.pathsep}assets"]
    if version_file:
        cmd += ["--version-file", version_file]
    if uac_admin:
        # Манифест requireAdministrator: UAC при каждом запуске.
        cmd.append("--uac-admin")
    if web:
        webui_dir = os.path.abspath(os.path.join("disk_cleaner_app", "webui"))
        cmd += ["--add-data", f"{webui_dir}{os.pathsep}disk_cleaner_app/webui"]
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    cmd.append(
        os.path.join("disk_cleaner_app", "web", "shell.py") if web else MAIN_SCRIPT
    )
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сборка DiskCleaner.exe")
    parser.add_argument(
        "--uac-admin",
        action="store_true",
        help="встроить манифест requireAdministrator (UAC при запуске)",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="собрать новый интерфейс на WebView2 (DiskCleanerWeb.exe)",
    )
    args = parser.parse_args(argv)

    clean_old_builds()
    version = project_version()
    version_file = write_version_file(version)
    cmd = build_command(
        uac_admin=args.uac_admin, version_file=version_file, web=args.web
    )

    print("🛠️  Building", APP_NAME, f"v{version}", "...")
    if os.path.exists(ICON_PATH):
        print("🎨  Иконка:", ICON_PATH)
    if args.uac_admin:
        print("🛡️  Манифест: requireAdministrator (UAC при каждом запуске)")
    print(" ".join(cmd))
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print("❌ Build failed.")
        return result.returncode

    exe_path = os.path.join(
        DIST_DIR, "DiskCleanerWeb.exe" if args.web else f"{APP_NAME}.exe"
    )
    if not os.path.exists(exe_path):
        print("❌ Build finished, but exe not found:", exe_path)
        return 1

    print(f"✅ Build complete: {exe_path}")
    print(f"Size: {os.path.getsize(exe_path) / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
