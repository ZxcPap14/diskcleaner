"""SBOM-скрипт: валидный CycloneDX с версией приложения и зависимостями."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "make_sbom.py"


def test_sbom_written_with_components(tmp_path: Path) -> None:
    out = tmp_path / "sbom.json"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "-o", str(out)],
        capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["bomFormat"] == "CycloneDX"
    assert data["specVersion"] == "1.5"
    component = data["metadata"]["component"]
    assert component["name"] == "diskcleaner-pro"
    from disk_cleaner_app import __version__

    assert component["version"] == __version__
    names = [c["name"].lower() for c in data["components"]]
    assert "customtkinter" in names
    assert names == sorted(names)
