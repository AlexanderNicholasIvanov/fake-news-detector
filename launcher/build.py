"""Build the launcher binaries with PyInstaller.

Creates an isolated build venv, installs a pinned PyInstaller, and produces two
single-file executables in the repo root from one source (run_fakenews.py); the
behaviour is selected at runtime by the executable's name:

    run-fakenews(.exe)   stop-fakenews(.exe)

Usage:  python launcher/build.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

PYINSTALLER = "pyinstaller==6.21.0"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / "run_fakenews.py"
BUILD = HERE / "_build"
VENV = BUILD / "venv"


def venv_python(v: Path) -> Path:
    return v / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    BUILD.mkdir(exist_ok=True)
    print(f"[build] creating venv at {VENV}")
    venv.EnvBuilder(with_pip=True, clear=True).create(VENV)
    py = str(venv_python(VENV))

    print(f"[build] installing {PYINSTALLER}")
    subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([py, "-m", "pip", "install", "-q", PYINSTALLER], check=True)

    for name in ("run-fakenews", "stop-fakenews"):
        print(f"[build] bundling {name}")
        subprocess.run(
            [
                py, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm",
                "--name", name,
                "--distpath", str(ROOT),
                "--workpath", str(BUILD / "work"),
                "--specpath", str(BUILD),
                str(SOURCE),
            ],
            check=True,
        )

    print(f"[build] done. Executables written to {ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
