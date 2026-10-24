# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec, синхронизированный с build.py.

Собирать: python -m PyInstaller DiskCleaner.spec --noconfirm
(обычно достаточно `python build.py`).
"""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("customtkinter")

hiddenimports = ["customtkinter", "squarify"]

# Легаси-модули не используются приложением и не включаются в сборку.
EXCLUDES = ["disk_cleaner_app.legacy"]


a = Analysis(
    ["disk_cleaner_app/__main__.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DiskCleaner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    icon="assets/diskcleaner.ico",
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
