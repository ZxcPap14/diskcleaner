"""Сборка релиза DiskCleaner Pro: exe → установщик NSIS → portable ZIP.

Пример:
    python build_installer.py
    python build_installer.py --makensis "C:\\Program Files (x86)\\NSIS\\makensis.exe"
    python build_installer.py --no-build

По умолчанию сначала вызывается ``build.py`` (PyInstaller onefile), затем
компилируется ``installer/DiskCleaner.nsi`` и создаётся портативный архив.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        continue
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP_EXE = "DiskCleaner.exe"
INSTALLER_SCRIPT = ROOT / "installer" / "DiskCleaner.nsi"


def project_version() -> str:
    text = (ROOT / "disk_cleaner_app" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("Не удалось определить версию приложения")
    return match.group(1)


def find_makensis(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_path = os.environ.get("MAKENSIS")
    if env_path:
        candidates.append(Path(env_path))
    which = shutil.which("makensis")
    if which:
        candidates.append(Path(which))
    candidates += [
        Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
        Path(r"C:\Program Files\NSIS\makensis.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "Не найден makensis.exe.\n"
        "Установите NSIS 3.x (https://nsis.sourceforge.io/Download) "
        "или укажите путь через --makensis / переменную MAKENSIS."
    )


def nsis_environment(makensis: Path) -> dict[str, str]:
    """Для распакованного portable-NSIS задать NSISDIR."""
    env = os.environ.copy()
    if env.get("NSISDIR"):
        return env
    parent = makensis.parent
    if parent.name.lower() == "bin" and (parent.parent / "Stubs").is_dir():
        env["NSISDIR"] = str(parent.parent)
    elif (parent / "Stubs").is_dir():
        env["NSISDIR"] = str(parent)
    return env


def find_signtool(explicit: str | None) -> Path | None:
    """Найти signtool.exe: аргумент, SIGNTOOL, PATH или Windows Kits."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_path = os.environ.get("SIGNTOOL")
    if env_path:
        candidates.append(Path(env_path))
    which = shutil.which("signtool")
    if which:
        candidates.append(Path(which))
    for root in (
        Path(r"C:\Program Files (x86)\Windows Kits\10\bin"),
        Path(r"C:\Program Files\Windows Kits\10\bin"),
    ):
        if root.is_dir():
            candidates += sorted(root.glob("*/x64/signtool.exe"), reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def sign_file(path: Path, signtool: Path, cert: str, timestamp: str) -> None:
    """Подписать файл сертификатом из хранилища и проверить подпись."""
    cmd = [
        str(signtool), "sign", "/sha1", cert, "/fd", "sha256",
        "/tr", timestamp, "/td", "sha256", str(path),
    ]
    print(f"🔏  Подпись {path.name} ...")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"signtool sign завершился с кодом {result.returncode}")
    verify = subprocess.run(
        [str(signtool), "verify", "/pa", "/v", str(path)], cwd=ROOT,
    )
    if verify.returncode != 0:
        raise SystemExit(f"Подпись {path.name} не прошла проверку")


def run_build(uac_admin: bool) -> None:
    cmd = [sys.executable, str(ROOT / "build.py")]
    if uac_admin:
        cmd.append("--uac-admin")
    print("🛠️  Сборка exe через build.py ...")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def run_makensis(makensis: Path, version: str, setup_path: Path) -> None:
    cmd = [
        str(makensis),
        "/V2",
        f"/DAPP_VERSION={version}",
        f"/DSOURCE_DIR={DIST}",
        f"/DPROJECT_DIR={ROOT}",
        f"/DOUTPUT_FILE={setup_path}",
        str(INSTALLER_SCRIPT),
    ]
    print("📦  Компиляция установщика NSIS ...")
    result = subprocess.run(
        cmd, cwd=ROOT, env=nsis_environment(makensis),
    )
    if result.returncode != 0:
        raise SystemExit(
            f"makensis завершился с кодом {result.returncode}"
        )


def make_portable(version: str) -> Path:
    zip_path = DIST / f"DiskCleaner-{version}-portable.zip"
    print("🗜️  Создание portable ZIP ...")
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        archive.write(DIST / APP_EXE, APP_EXE)
        archive.write(ROOT / "README.md", "README.md")
        archive.write(ROOT / "LICENSE", "LICENSE")
    return zip_path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_hashes(paths: list[Path]) -> Path:
    target = DIST / "SHA256SUMS.txt"
    lines = [f"{sha256(path)}  {path.name}" for path in paths]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def human_size(path: Path) -> str:
    return f"{path.stat().st_size / 1024 / 1024:.1f} MB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Собрать DiskCleaner.exe, установщик и portable ZIP"
    )
    parser.add_argument(
        "--makensis",
        help="путь к makensis.exe (по умолчанию ищется в PATH и Program Files)",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="не запускать build.py, использовать готовый dist\\DiskCleaner.exe",
    )
    parser.add_argument(
        "--uac-admin",
        action="store_true",
        help="собрать exe с манифестом requireAdministrator",
    )
    parser.add_argument(
        "--sign-cert",
        help="SHA-1 отпечаток сертификата для signtool (SmartScreen)",
    )
    parser.add_argument(
        "--sign-tool",
        help="путь к signtool.exe (по умолчанию ищется в PATH и Windows Kits)",
    )
    parser.add_argument(
        "--timestamp-url",
        default="http://timestamp.digicert.com",
        help="сервер метки времени для подписи",
    )
    args = parser.parse_args(argv)

    version = project_version()
    print(f"🚀  DiskCleaner Pro {version}")

    if not args.no_build:
        run_build(args.uac_admin)

    exe_path = DIST / APP_EXE
    if not exe_path.is_file():
        raise SystemExit(f"Не найден {exe_path}. Запустите build.py.")

    signtool: Path | None = None
    if args.sign_cert:
        signtool = find_signtool(args.sign_tool)
        if signtool is None:
            raise SystemExit(
                "Не найден signtool.exe. Установите Windows SDK или укажите "
                "--sign-tool / переменную SIGNTOOL."
            )
        print(f"🔏  signtool: {signtool}")
        sign_file(exe_path, signtool, args.sign_cert, args.timestamp_url)
    else:
        print("ℹ️  Сертификат не указан: exe и установщик останутся неподписанными "
              "(SmartScreen может предупредить).")

    makensis = find_makensis(args.makensis)
    print(f"🔧  NSIS: {makensis}")
    setup_path = DIST / f"DiskCleaner-Setup-{version}.exe"
    run_makensis(makensis, version, setup_path)
    if not setup_path.is_file():
        raise SystemExit(f"Установщик не создан: {setup_path}")
    if signtool is not None:
        sign_file(setup_path, signtool, args.sign_cert, args.timestamp_url)

    portable_path = make_portable(version)
    hashes = write_hashes([exe_path, setup_path, portable_path])

    print("\n✅  Готово:")
    print(f"   exe:        {exe_path}  ({human_size(exe_path)})")
    print(f"   установщик: {setup_path}  ({human_size(setup_path)})")
    print(f"   portable:   {portable_path}  ({human_size(portable_path)})")
    print(f"   хэши:       {hashes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
