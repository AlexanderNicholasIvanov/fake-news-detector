"""Build the launcher binary with PyInstaller.

Creates an isolated build venv, installs pinned PyInstaller + pywebview, and
produces a single-file executable in the repo root from run_fakenews.py:

    run-fakenews(.exe)   native desktop window (pywebview / WebView2). Double-click
                         to launch the whole stack; close the window to shut it all
                         down (services + bundled PostgreSQL).

Usage:  python launcher/build.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

PYINSTALLER = "pyinstaller==6.21.0"
PYWEBVIEW = "pywebview==6.2.1"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / "run_fakenews.py"
BUILD = HERE / "_build"
VENV = BUILD / "venv"

# A single app build. It bundles the pywebview backend + WebView2 loader.
#
# The app is NOT built --windowed: it keeps a console subsystem (hidden at runtime
# via _hide_own_console) so spawned service processes inherit a console cleanly.
# Child processes are started with CREATE_NO_WINDOW so none of them pop a console.
APP_NAME = "run-fakenews"


def venv_python(v: Path) -> Path:
    return v / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    BUILD.mkdir(exist_ok=True)
    print(f"[build] creating venv at {VENV}")
    venv.EnvBuilder(with_pip=True, clear=True).create(VENV)
    py = str(venv_python(VENV))

    print(f"[build] installing {PYINSTALLER} + {PYWEBVIEW}")
    subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([py, "-m", "pip", "install", "-q", PYINSTALLER, PYWEBVIEW], check=True)

    print(f"[build] bundling {APP_NAME}")
    args = [
        py, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm",
        "--name", APP_NAME,
        "--distpath", str(ROOT),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        # Pull in the pywebview backend + WebView2 loader. Console subsystem is
        # kept (hidden at runtime); child services run with CREATE_NO_WINDOW.
        "--collect-all", "webview",
        str(SOURCE),
    ]
    subprocess.run(args, check=True)

    print(f"[build] done. Executable written to {ROOT / (APP_NAME + '.exe')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
