"""Fake-News Detector launcher.

Built with PyInstaller (see build.py) into two single-file binaries from this one
source; behaviour is chosen by the executable's own name:

    run-fakenews.exe   -> a native desktop window (pywebview / Edge WebView2):
                          shows a loading screen while it runs preflight checks,
                          brings the Docker stack up, waits for the API to be
                          healthy, then loads the dashboard inside the window.
                          No browser, no console, no address bar.
    stop-fakenews.exe   -> a small console tool: `docker compose down`.

Hidden mode for testing: pass --selfcheck to run the full startup sequence in the
console (no window) and exit 0/1 — used to validate the frozen exe headlessly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

API_HEALTH = "http://localhost:8000/health"
DASHBOARD = "http://localhost:5173"
OLLAMA_TAGS = "http://localhost:11434/api/tags"
HEALTH_TIMEOUT_S = 240

def _hide_own_console() -> None:
    """Hide this process's console window (Windows) so the app shows only its
    native window. Only hides a console THIS process owns - never a shared parent
    terminal - so launching from a shell doesn't hide the shell. Keeping a (hidden)
    console means docker subprocesses inherit it and run fast; a fully console-less
    process makes the docker CLI's daemon calls crawl."""
    if os.name != "nt":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not hwnd:
            return
        owner_pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value == os.getpid():
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def _trace(msg: str) -> None:
    """Append a line to FND_TRACE if set. Lets us observe the windowed (console-
    less) app's teardown path during testing."""
    path = os.environ.get("FND_TRACE")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.monotonic():10.2f}  {msg}\n")
    except Exception:
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
    if not env_path.exists() and example.exists():
        shutil.copyfile(example, env_path)


# ------------------------------------------------------------ stack control (io)
def _run(cmd: list[str], cwd: Path | None = None, capture: bool = False):
    kw: dict = {"text": True}
    if capture:
        kw["capture_output"] = True
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, **kw)


def docker_present() -> bool:
    return shutil.which("docker") is not None


def docker_running() -> bool:
    return _run(["docker", "info"], capture=True).returncode == 0


def http_json(url: str, timeout: float = 4.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_status(env: dict[str, str]) -> tuple[str, str]:
    """(level, message): level is 'ok' or 'warn'. Non-fatal — the stack still
    ingests + serves the dashboard without Ollama; only scoring needs it."""
    model = env.get("SCORING_MODEL", "qwen3:14b")
    try:
        tags = http_json(OLLAMA_TAGS)
    except (urllib.error.URLError, OSError, ValueError):
        return "warn", ("Ollama not reachable - scoring will be idle. Start Ollama "
                        "with OLLAMA_HOST=0.0.0.0:11434.")
    names = {m.get("name", "") for m in tags.get("models", [])}
    if model in names or any(n.split(":")[0] == model.split(":")[0] for n in names):
        return "ok", f"Ollama running, '{model}' available"
    return "warn", f"Ollama running but '{model}' not pulled (run: ollama pull {model})"


def compose_up(root: Path) -> tuple[bool, str]:
    proc = _run(["docker", "compose", "up", "--build", "-d"], cwd=root, capture=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out


def compose_down(root: Path) -> tuple[bool, str]:
    # `kill` first: an immediate SIGKILL to every container. Without it, `down`
    # tries a graceful stop and blocks on the worker mid-LLM-call until the
    # ~60s COMPOSE_HTTP_TIMEOUT - so teardown crawled. kill + down -t 0 is ~5s
    # even under load. The named Postgres volume survives (close != wipe data).
    kw = {"cwd": str(root), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    subprocess.run(["docker", "compose", "kill"], **kw)
    proc = subprocess.run(
        ["docker", "compose", "down", "-t", "0", "--remove-orphans"], **kw
    )
    return proc.returncode == 0, ""


def wait_for_health(timeout_s: int = HEALTH_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if http_json(API_HEALTH, timeout=3.0).get("status") == "ok":
                return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(2)
    return False


# ----------------------------------------------------------------- app (window)
_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>
  :root { color-scheme: dark; }
  html,body { margin:0; height:100%; background:#0f172a; color:#e2e8f0;
    font-family:'Segoe UI',system-ui,sans-serif; }
  .wrap { height:100%; display:flex; align-items:center; justify-content:center; }
  .card { width:520px; padding:36px 40px; }
  .brand { font-size:22px; font-weight:600; letter-spacing:.2px; }
  .brand .dot { color:#38bdf8; }
  .sub { color:#94a3b8; font-size:13px; margin-top:4px; margin-bottom:26px; }
  ul { list-style:none; padding:0; margin:0; }
  li { display:flex; align-items:flex-start; gap:12px; padding:7px 0; font-size:14px; }
  .ico { width:18px; height:18px; flex:none; margin-top:1px; border-radius:50%;
    display:inline-block; }
  .pending .ico { border:2px solid #334155; border-top-color:#38bdf8;
    animation:spin .8s linear infinite; }
  .ok .ico { background:#22c55e; }
  .warn .ico { background:#f59e0b; }
  .err .ico { background:#ef4444; }
  .ok .txt { color:#cbd5e1; } .pending .txt { color:#e2e8f0; }
  .warn .txt { color:#fbbf24; } .err .txt { color:#fca5a5; }
  .hint { margin-top:22px; font-size:12px; color:#64748b; white-space:pre-wrap; }
  @keyframes spin { to { transform:rotate(360deg); } }
</style></head><body><div class="wrap"><div class="card">
  <div class="brand">Fake-News <span class="dot">Detector</span></div>
  <div class="sub">starting up&hellip;</div>
  <ul>__ROWS__</ul>
  <div class="hint">__HINT__</div>
</div></div></body></html>"""

_STATE_CLASS = {"..": "pending", "ok": "ok", "warn": "warn", "err": "err"}


class AppUI:
    """Renders the loading screen into the pywebview window as steps progress."""

    def __init__(self) -> None:
        self.window = None
        self.steps: list[list[str]] = []  # [state, text]
        self.hint = ""

    def _render(self) -> None:
        rows = "".join(
            f'<li class="{_STATE_CLASS.get(s, "pending")}">'
            f'<span class="ico"></span><span class="txt">{t}</span></li>'
            for s, t in self.steps
        )
        html = _PAGE.replace("__ROWS__", rows).replace("__HINT__", self.hint)
        if self.window is not None:
            try:
                self.window.load_html(html)
            except Exception:
                pass  # window may already be closing

    def initial_html(self) -> str:
        return _PAGE.replace("__ROWS__", "").replace("__HINT__", "")

    def begin(self, text: str) -> None:
        self.steps.append(["..", text])
        self._render()

    def set_last(self, state: str, text: str | None = None) -> None:
        if not self.steps:
            self.steps.append([state, text or ""])
        else:
            self.steps[-1][0] = state
            if text is not None:
                self.steps[-1][1] = text
        self._render()

    def add(self, state: str, text: str) -> None:
        self.steps.append([state, text])
        self._render()

    def set_hint(self, text: str) -> None:
        self.hint = text
        self._render()


def _message_box(title: str, text: str) -> None:
    """Last-resort native dialog if the webview itself can't start (Windows)."""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
            return
        except Exception:
            pass
    print(f"{title}: {text}", file=sys.stderr)


def do_app(root: Path) -> None:
    _hide_own_console()  # show only the native window, not a console
    try:
        import webview  # lazy: only the run binary bundles this
    except Exception as exc:  # pragma: no cover - bundling/runtime guard
        _message_box(
            "Fake-News Detector",
            f"Could not start the app window ({exc}).\n\n"
            "Opening the dashboard in your browser instead once it's ready.",
        )
        ensure_env_file(root)
        if docker_present() and docker_running():
            compose_up(root)
            wait_for_health()
        webbrowser.open(DASHBOARD)
        return

    env = load_env(root)
    ui = AppUI()
    window = webview.create_window(
        "Fake-News Detector", html=ui.initial_html(), width=1180, height=820,
        min_size=(900, 600),
    )
    ui.window = window
    closing = threading.Event()

    def worker() -> None:
        try:
            ensure_env_file(root)

            ui.begin("Checking Docker engine")
            if not docker_present():
                ui.set_last("err", "Docker is not installed or not on PATH")
                ui.set_hint("Install Docker Desktop, then reopen this app:\n"
                            "https://www.docker.com/products/docker-desktop/")
                return
            if not docker_running():
                ui.set_last("err", "Docker engine isn't running")
                ui.set_hint("Start Docker Desktop, wait until it's ready, then "
                            "reopen this app.")
                return
            ui.set_last("ok", "Docker engine running")

            ui.begin("Checking Ollama + model")
            level, msg = ollama_status(env)
            ui.set_last("ok" if level == "ok" else "warn", msg)

            if closing.is_set():
                return
            ui.begin("Starting containers (first run builds images - can take minutes)")
            ok, out = compose_up(root)
            if not ok:
                ui.set_last("err", "Failed to start containers")
                ui.set_hint(out[-700:].strip())
                return
            ui.set_last("ok", "Containers started")

            ui.begin("Waiting for the API to be healthy")
            if wait_for_health():
                ui.set_last("ok", "API healthy")
            else:
                ui.set_last("warn", "API slow to start - loading anyway")

            if closing.is_set():
                return
            ui.add("..", "Loading dashboard")
            window.load_url(DASHBOARD)
        except Exception as exc:  # never leave the window stuck on a spinner
            if not closing.is_set():
                ui.add("err", f"Startup error: {exc!r}")

    def _on_closing(*_args, **_kwargs):
        _trace("closing event fired")
        closing.set()  # flag teardown the moment the close begins

    window.events.closing += _on_closing

    # Test hook: FND_TEST_AUTOCLOSE=<seconds> closes the window like clicking the X
    # (window.destroy()), so teardown can be verified without a human at the GUI.
    _autoclose = os.environ.get("FND_TEST_AUTOCLOSE")
    if _autoclose:
        def _auto() -> None:
            time.sleep(float(_autoclose))
            _trace("autoclose: calling window.destroy()")
            try:
                window.destroy()
                _trace("autoclose: destroy() returned")
            except Exception as exc:
                _trace(f"autoclose: destroy() raised {exc!r}")
        threading.Thread(target=_auto, daemon=True).start()

    work = threading.Thread(target=worker, daemon=True)
    work.start()
    _trace("calling webview.start()")
    webview.start()  # blocks until the window is closed
    _trace("webview.start() returned")

    # Window closed -> shut down everything this app started. Containers + network
    # go; the named Postgres volume is kept (close != wipe data). Host Ollama is a
    # shared service we didn't start, so it's left alone.
    closing.set()
    work.join(timeout=2)
    if docker_present():
        _trace("compose_down begin")
        ok, _out = compose_down(root)
        _trace(f"compose_down end ok={ok}")


# --------------------------------------------------------------- console modes
def do_stop(root: Path) -> int:
    print("\n  Fake-News Detector - stopping\n  " + "=" * 30 + "\n")
    if not docker_present():
        print(" [XX]  Docker is not on PATH.")
        input("\nPress Enter to close this window...")
        return 1
    ok, out = compose_down(root)
    print(out.rstrip())
    print(" [OK]  stack stopped." if ok else " [XX]  `docker compose down` failed.")
    input("\nPress Enter to close this window...")
    return 0 if ok else 1


def do_selfcheck(root: Path) -> int:
    """Run the full startup sequence in the console (no window). For testing."""
    print("[selfcheck] root:", root)
    ensure_env_file(root)
    env = load_env(root)
    if not docker_present():
        print("[selfcheck] FAIL: docker not found"); return 1
    if not docker_running():
        print("[selfcheck] FAIL: docker engine not running"); return 1
    print("[selfcheck] docker ok")
    print("[selfcheck] ollama:", ollama_status(env))
    ok, _ = compose_up(root)
    print("[selfcheck] compose up:", "ok" if ok else "FAIL")
    if not ok:
        return 1
    healthy = wait_for_health()
    print("[selfcheck] api healthy:", healthy)
    return 0 if healthy else 1


def main() -> int:
    root = find_project_root()
    exe_name = Path(sys.argv[0]).stem.lower()
    if "--selfcheck" in sys.argv:
        return do_selfcheck(root)
    if "stop" in exe_name:
        return do_stop(root)
    do_app(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
