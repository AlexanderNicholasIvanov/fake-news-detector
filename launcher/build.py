"""Build the launcher binaries with PyInstaller.

Creates an isolated build venv, installs pinned PyInstaller + pywebview, and
produces two single-file executables in the repo root from one source
(run_fakenews.py); behaviour is selected at runtime by the executable's name:

    run-fakenews(.exe)   native desktop window (pywebview / WebView2), windowed
    stop-fakenews(.exe)  console tool (stops the native services it left running)

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

# (name, is_app). The app build bundles the webview backend; the console build
# (lazy-imports webview only at runtime, never reached) stays slim.
#
# The app is NOT built --windowed: it keeps a console subsystem (hidden at runtime
# via _hide_own_console) so spawned service processes inherit a console cleanly.
# Child processes are started with CREATE_NO_WINDOW so none of them pop a console.
TARGETS = [
    ("run-fakenews", True),
    ("stop-fakenews", False),
]


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

    for name, is_app in TARGETS:
        print(f"[build] bundling {name}{' (app)' if is_app else ''}")
        args = [
            py, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm",
            "--name", name,
            "--distpath", str(ROOT),
            "--workpath", str(BUILD / "work"),
            "--specpath", str(BUILD),
        ]
        if is_app:
            # Pull in the pywebview backend + WebView2 loader. Console subsystem is
            # kept (hidden at runtime); child services run with CREATE_NO_WINDOW.
            args += ["--collect-all", "webview"]
        args += [str(SOURCE)]
        subprocess.run(args, check=True)

    print(f"[build] done. Executables written to {ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
