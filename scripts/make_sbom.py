"""SBOM в формате CycloneDX 1.5 JSON по установленным зависимостям.

    python scripts/make_sbom.py [-o sbom.json]

Зависимости берутся из метаданных сборки (importlib.metadata), поэтому
версии в отчёте — те, с которыми приложение реально собрано.
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib import metadata
from pathlib import Path

APP_NAME = "diskcleaner-pro"
SBOM_FILE = "sbom.json"

# Что считаем своим продуктом: остальное — компоненты.
OWN_PACKAGES = ("diskcleaner-pro", "disk_cleaner_app")


def _requirements() -> list[str]:
    """Имена дистрибутивов из requirements.txt (без версий и маркеров)."""
    path = Path(__file__).resolve().parent.parent / "requirements.txt"
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = line.split("==")[0].split(">=")[0].split("<")[0].split(";")[0]
        if name.strip():
            names.append(name.strip())
    return names


def build_sbom(project_version: str | None = None) -> dict:
    if project_version:
        version = project_version
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from disk_cleaner_app import __version__ as version  # noqa: PLC0415

    components = []
    for name in _requirements():
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            # Не установлено в этом окружении — оставляем видимым, а не молчим.
            components.append({"type": "library", "name": name,
                               "version": "not-installed"})
            continue
        license_name = dist.metadata.get("License") or "unknown"
        components.append({
            "type": "library",
            "name": dist.metadata["Name"],
            "version": dist.version,
            "purl": f"pkg:pypi/{dist.metadata['Name'].lower()}@{dist.version}",
            "licenses": [{"license": {"name": license_name}}],
        })

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": APP_NAME,
                "version": version,
                "purl": f"pkg:pypi/{APP_NAME}@{version}",
            },
        },
        "components": sorted(components, key=lambda c: c["name"].lower()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="make_sbom.py")
    parser.add_argument("-o", "--out", default=str(Path("dist") / SBOM_FILE),
                        help=f"куда записать (по умолчанию {SBOM_FILE})")
    args = parser.parse_args()

    data = build_sbom()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"SBOM: {out} — {len(data['components'])} компонентов, "
          f"версия {data['metadata']['component']['version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
