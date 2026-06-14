"""Fake-News Detector launcher.

A single, dependency-free executable (built with PyInstaller - see build.py) that
brings the whole stack up and opens the dashboard. The SAME source is built into
two binaries; behaviour is chosen by the executable's own name:

    run-fakenews.exe   -> preflight checks, `docker compose up --build -d`,
                          wait for the API to be healthy, open the dashboard
    stop-fakenews.exe  -> `docker compose down`

Only the Python standard library is used, so the frozen exe needs nothing on the
target machine except Docker (and Ollama for scoring).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

API_HEALTH = "http://localhost:8000/health"
DASHBOARD = "http://localhost:5173"
OLLAMA_TAGS = "http://localhost:11434/api/tags"
HEALTH_TIMEOUT_S = 240


# ---------------------------------------------------------------- presentation
def say(prefix: str, msg: str) -> None:
    print(f" {prefix}  {msg}", flush=True)


def ok(msg: str) -> None:
    say("[OK]", msg)


def warn(msg: str) -> None:
    say("[! ]", msg)


def step(msg: str) -> None:
    say("[..]", msg)


def fail_and_exit(msg: str, code: int = 1) -> None:
    say("[XX]", msg)
    pause()
    sys.exit(code)


def pause() -> None:
    # Keep the window open when double-clicked from Explorer.
    try:
        input("\nPress Enter to close this window...")
    except EOFError:
        pass


# ---------------------------------------------------------------- project setup
def find_project_root() -> Path:
    """Walk up from the executable/script until docker-compose.yml is found."""
    if getattr(sys, "frozen", False):
        start = Path(sys.executable).resolve().parent
    else:
        start = Path(__file__).resolve().parent
    for d in (start, *start.parents):
        if (d / "docker-compose.yml").exists():
            return d
    return start


def load_env(root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for name in (".env", ".env.example"):
        p = root / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
        break
    return env


def ensure_env_file(root: Path) -> None:
    env_path = root / ".env"
    example = root / ".env.example"
    if env_path.exists():
        ok(".env present")
    elif example.exists():
        shutil.copyfile(example, env_path)
        ok("created .env from .env.example")
    else:
        warn("no .env or .env.example found - using compose defaults")


# ---------------------------------------------------------------- prerequisites
def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, **kw)


def check_docker() -> None:
    if shutil.which("docker") is None:
        fail_and_exit(
            "Docker is not installed or not on PATH. Install Docker Desktop: "
            "https://www.docker.com/products/docker-desktop/"
        )
    # `docker info` fails fast if the daemon/Desktop isn't running.
    proc = run(["docker", "info"], capture_output=True)
    if proc.returncode != 0:
        fail_and_exit(
            "Docker is installed but the engine isn't running. "
            "Start Docker Desktop, wait for it to be ready, then run this again."
        )
    ok("Docker engine is running")


def http_json(url: str, timeout: float = 4.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_ollama(env: dict[str, str]) -> None:
    """Scoring needs Ollama on the host with the configured model. Non-fatal:
    the stack still ingests + serves the dashboard without it."""
    model = env.get("SCORING_MODEL", "qwen3:14b")
    try:
        tags = http_json(OLLAMA_TAGS)
    except (urllib.error.URLError, OSError, ValueError):
        warn(
            "Ollama not reachable at localhost:11434 - ingestion/dashboard will "
            "work but scoring will not. Start Ollama with the server bound to all "
            "interfaces:  set OLLAMA_HOST=0.0.0.0:11434  then restart Ollama."
        )
        return
    names = {m.get("name", "") for m in tags.get("models", [])}
    if model in names or any(n.split(":")[0] == model.split(":")[0] for n in names):
        ok(f"Ollama is running and '{model}' is available")
    else:
        warn(
            f"Ollama is running but '{model}' isn't pulled. Run:  ollama pull {model}"
        )


# ---------------------------------------------------------------- stack control
def compose_up(root: Path) -> None:
    step("starting the stack (docker compose up --build -d) - first run pulls images...")
    proc = run(["docker", "compose", "up", "--build", "-d"], cwd=str(root))
    if proc.returncode != 0:
        fail_and_exit("`docker compose up` failed (see output above).")
    ok("containers started")


def wait_for_health(root: Path) -> bool:
    step(f"waiting for the API to be healthy (up to {HEALTH_TIMEOUT_S}s)...")
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            data = http_json(API_HEALTH, timeout=3.0)
            if data.get("status") == "ok":
                ok("API is healthy")
                return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        print("    .", end="", flush=True)
        time.sleep(3)
    print()
    warn("API didn't report healthy in time. It may still be starting - check "
         "`docker compose logs api`. Opening the dashboard anyway.")
    return False


def do_run(root: Path) -> None:
    print("\n  Fake-News Detector - launcher\n  " + "=" * 30 + "\n")
    ensure_env_file(root)
    env = load_env(root)
    check_docker()
    check_ollama(env)
    compose_up(root)
    wait_for_health(root)
    step(f"opening the dashboard at {DASHBOARD}")
    webbrowser.open(DASHBOARD)
    print()
    ok("Up and running.")
    print(f"""
  Dashboard : {DASHBOARD}
  API docs  : http://localhost:8000/docs
  Logs      : docker compose logs -f worker
  Stop      : run stop-fakenews.exe  (or: docker compose down)
""")
    pause()


def do_stop(root: Path) -> None:
    print("\n  Fake-News Detector - stopping\n  " + "=" * 30 + "\n")
    if shutil.which("docker") is None:
        fail_and_exit("Docker is not on PATH.")
    proc = run(["docker", "compose", "down"], cwd=str(root))
    if proc.returncode != 0:
        fail_and_exit("`docker compose down` failed (see output above).")
    ok("stack stopped.")
    pause()


def main() -> None:
    root = find_project_root()
    exe_name = Path(sys.argv[0]).stem.lower()
    if "stop" in exe_name:
        do_stop(root)
    else:
        do_run(root)


if __name__ == "__main__":
    main()
