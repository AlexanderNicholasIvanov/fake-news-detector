"""Fake-News Detector launcher (native, no Docker).

Built with PyInstaller (see build.py) into a single binary, run-fakenews.exe:

    Double-click  -> a native desktop window (pywebview / Edge WebView2): shows a
                     loading screen while it runs preflight checks, starts the
                     bundled PostgreSQL, applies DB migrations, starts the API +
                     worker + Vite dev server as native processes, waits for the
                     API to be healthy, then loads the dashboard inside the window.
                     No browser, no console, no address bar.
    Close window  -> shuts the whole stack down (services + the PostgreSQL it
                     started). One exe is the entire lifecycle.

The stack runs natively against the bundled portable PostgreSQL (with pgvector)
and the host's Ollama. There is no containerisation: the API and worker run from
backend/.venv, the frontend from its npm dev server. One-time setup (PostgreSQL,
venv, frontend deps, DB role/extension) is done by scripts/setup-native.ps1.

Hidden mode for testing: pass --selfcheck to run the full startup sequence in the
console (no window) and exit 0/1 — used to validate the frozen exe headlessly.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
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

DB_HOST = "localhost"
DB_PORT = 5432

# Windows process-creation flag: don't pop a console window for child processes.
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _hide_own_console() -> None:
    """Hide this process's console window (Windows) so the app shows only its
    native window. Only hides a console THIS process owns - never a shared parent
    terminal - so launching from a shell doesn't hide the shell."""
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
    """Walk up from the executable/script until the repo root is found.

    The root is identified by the backend package (backend/app); docker-compose.yml
    is no longer required (the stack runs natively) but is still accepted as a
    marker for repos that still carry it.
    """
    if getattr(sys, "frozen", False):
        start = Path(sys.executable).resolve().parent
    else:
        start = Path(__file__).resolve().parent
    for d in (start, *start.parents):
        if (d / "backend" / "app").is_dir() or (d / "docker-compose.yml").exists():
            return d
    return start


def backend_dir(root: Path) -> Path:
    return root / "backend"


def frontend_dir(root: Path) -> Path:
    return root / "frontend"


def venv_python(root: Path) -> Path:
    name = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return backend_dir(root) / ".venv" / name


def log_dir(root: Path) -> Path:
    d = root / "logs"
    d.mkdir(exist_ok=True)
    return d


def pid_file(root: Path) -> Path:
    return root / ".fnd-pids"


# Bundled (portable) PostgreSQL — conda-forge build under %LOCALAPPDATA%, managed
# by this launcher (it isn't a Windows service). Set up by scripts/setup-native.ps1.
def pg_base() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "FakeNewsDetector"


def pg_bin() -> Path:
    return pg_base() / "pg" / "Library" / "bin"


def pg_data() -> Path:
    return pg_base() / "pgdata"


def pg_log() -> Path:
    return pg_base() / "pg.log"


def pg_installed() -> bool:
    return (pg_bin() / "pg_ctl.exe").exists() and (pg_data() / "PG_VERSION").exists()


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


# ------------------------------------------------------------------- preflight
def http_json(url: str, timeout: float = 4.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def postgres_reachable(host: str = DB_HOST, port: int = DB_PORT, timeout: float = 2.0) -> bool:
    """TCP-connect to Postgres. A reachable port is enough for preflight — the API
    surfaces auth/schema errors with a real message if creds are wrong."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def prerequisites_ready(root: Path) -> tuple[bool, str]:
    """One-time native setup present? (bundled PostgreSQL + backend venv + frontend deps)."""
    if not (pg_bin() / "pg_ctl.exe").exists():
        return False, "bundled PostgreSQL missing"
    if not (pg_data() / "PG_VERSION").exists():
        return False, "PostgreSQL data dir not initialized"
    if not venv_python(root).exists():
        return False, "backend venv missing"
    if not (frontend_dir(root) / "node_modules").is_dir():
        return False, "frontend node_modules missing"
    return True, ""


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


# ------------------------------------------------------------- stack control (io)
def _run(cmd: list[str], cwd: Path | None = None, capture: bool = False,
         env: dict | None = None):
    kw: dict = {"text": True}
    if capture:
        kw["capture_output"] = True
    if os.name == "nt":
        kw["creationflags"] = _CREATE_NO_WINDOW
    if env is not None:
        kw["env"] = env
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, **kw)


def child_env(root: Path) -> dict:
    """os.environ overlaid with .env values, so spawned api/worker get DATABASE_URL,
    OLLAMA_BASE_URL, etc. regardless of cwd (compose used to inject these)."""
    return {**os.environ, **load_env(root)}


def _pg_ctl(*args: str) -> int:
    """Run pg_ctl with all stdio detached to DEVNULL.

    Capturing pg_ctl's pipes deadlocks on Windows: the postmaster it starts inherits
    the stdout/stderr pipe and holds it open for the server's whole lifetime, so a
    PIPE read in the parent never reaches EOF and subprocess.run() blocks forever —
    even though the server came up fine. DEVNULL means there's no pipe to inherit.
    """
    flags = _CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(
        [str(pg_bin() / "pg_ctl.exe"), *args],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags,
    ).returncode


def start_postgres() -> bool:
    """Start the bundled PostgreSQL if it isn't already listening. Returns True iff
    THIS call started it (so teardown knows whether to stop it). Raises on failure."""
    if postgres_reachable():
        return False  # already running (we didn't start it; leave it alone on close)
    if not pg_installed():
        raise RuntimeError("bundled PostgreSQL is not set up")
    _pg_ctl("-D", str(pg_data()), "-l", str(pg_log()), "-o", "-p 5432", "-w", "start")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if postgres_reachable():
            return True
        time.sleep(1)
    raise RuntimeError("PostgreSQL did not start within 30s (see pg.log)")


def stop_postgres() -> None:
    """Fast-stop the bundled PostgreSQL (only call if we started it)."""
    if not pg_installed():
        return
    _pg_ctl("-D", str(pg_data()), "-m", "fast", "stop")


def run_migrations(root: Path) -> tuple[bool, str]:
    """alembic upgrade head — the API container used to do this; natively the
    launcher must, before the API/worker touch the schema."""
    py = str(venv_python(root))
    proc = _run([py, "-m", "alembic", "upgrade", "head"],
                cwd=backend_dir(root), capture=True, env=child_env(root))
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out


def _spawn(cmd: list[str], cwd: Path, logfile: Path,
           env: dict | None = None) -> subprocess.Popen:
    log = open(logfile, "a", encoding="utf-8", buffering=1)
    flags = _CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        cmd, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, creationflags=flags, env=env,
    )


def start_stack(root: Path) -> list[subprocess.Popen]:
    """Start API (uvicorn), worker, and the Vite dev server as native processes.
    Records their PIDs to the pid file so stop-fakenews can reach them too."""
    py = str(venv_python(root))
    logs = log_dir(root)
    env = child_env(root)
    procs: list[subprocess.Popen] = []

    procs.append(_spawn(
        [py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        backend_dir(root), logs / "api.log", env=env,
    ))
    procs.append(_spawn(
        [py, "-m", "app.worker"], backend_dir(root), logs / "worker.log", env=env,
    ))
    npm = shutil.which("npm") or shutil.which("npm.cmd") or "npm.cmd"
    procs.append(_spawn(
        [npm, "run", "dev"], frontend_dir(root), logs / "frontend.log", env=env,
    ))

    pid_file(root).write_text(
        "\n".join(str(p.pid) for p in procs), encoding="utf-8"
    )
    return procs


def _taskkill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def stop_stack(root: Path, procs: list[subprocess.Popen] | None = None) -> None:
    """Kill every service process (and its child tree). PostgreSQL is a separate
    Windows service we don't own (it holds the data) so it's left running; the
    host's Ollama is left alone too."""
    pids: list[int] = []
    if procs:
        pids = [p.pid for p in procs]
    else:
        pf = pid_file(root)
        if pf.exists():
            pids = [int(x) for x in pf.read_text(encoding="utf-8").split() if x.strip().isdigit()]
    for pid in pids:
        _taskkill_tree(pid)
    pf = pid_file(root)
    if pf.exists():
        try:
            pf.unlink()
        except OSError:
            pass


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


_SETUP_HINT = ("Run the one-time setup first (PowerShell):\n"
               "  scripts\\setup-native.ps1")


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
        ok, _ = prerequisites_ready(root)
        if ok:
            try:
                start_postgres()
            except Exception:
                pass
            if postgres_reachable():
                run_migrations(root)
                start_stack(root)
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
    procs: list[subprocess.Popen] = []
    started_pg = [False]  # True iff we started PostgreSQL (so we stop it on close)

    def worker() -> None:
        try:
            ensure_env_file(root)

            ui.begin("Checking app setup")
            ready, why = prerequisites_ready(root)
            if not ready:
                ui.set_last("err", f"Setup incomplete - {why}")
                ui.set_hint(_SETUP_HINT)
                return
            ui.set_last("ok", "PostgreSQL + backend venv + frontend deps present")

            ui.begin("Starting PostgreSQL")
            try:
                started_pg[0] = start_postgres()
            except Exception as exc:
                ui.set_last("err", f"Could not start PostgreSQL: {exc}")
                ui.set_hint(_SETUP_HINT)
                return
            ui.set_last("ok", "PostgreSQL running"
                        + (" (started)" if started_pg[0] else " (already running)"))

            ui.begin("Checking Ollama + model")
            level, msg = ollama_status(env)
            ui.set_last("ok" if level == "ok" else "warn", msg)

            if closing.is_set():
                return
            ui.begin("Applying database migrations")
            ok, out = run_migrations(root)
            if not ok:
                ui.set_last("err", "Migration failed")
                ui.set_hint(out[-700:].strip())
                return
            ui.set_last("ok", "Database up to date")

            if closing.is_set():
                return
            ui.begin("Starting services (API, worker, frontend)")
            procs.extend(start_stack(root))
            ui.set_last("ok", "Services started")

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

    # Window closed -> stop everything this app started: the service processes, and
    # the bundled PostgreSQL but only if WE started it (data persists in the data
    # dir, so close != wipe). The host's Ollama is a shared service, left alone.
    closing.set()
    work.join(timeout=2)
    _trace("stop_stack begin")
    stop_stack(root, procs)
    if started_pg[0]:
        _trace("stop_postgres begin")
        stop_postgres()
    _trace("teardown end")


# --------------------------------------------------------------- console mode
def do_selfcheck(root: Path) -> int:
    """Run the full startup sequence in the console (no window). For testing."""
    print("[selfcheck] root:", root)
    ensure_env_file(root)
    env = load_env(root)
    ready, why = prerequisites_ready(root)
    if not ready:
        print(f"[selfcheck] FAIL: setup incomplete - {why}"); return 1
    print("[selfcheck] setup ok")
    started_pg = False
    try:
        started_pg = start_postgres()
    except Exception as exc:
        print(f"[selfcheck] FAIL: postgres start - {exc}"); return 1
    print("[selfcheck] postgres ok", "(started)" if started_pg else "(already running)")
    procs = []
    try:
        print("[selfcheck] ollama:", ollama_status(env))
        ok, out = run_migrations(root)
        print("[selfcheck] migrations:", "ok" if ok else "FAIL")
        if not ok:
            print(out[-700:]); return 1
        procs = start_stack(root)
        healthy = wait_for_health()
        print("[selfcheck] api healthy:", healthy)
    finally:
        stop_stack(root, procs)
        if started_pg:
            stop_postgres()
    return 0 if healthy else 1


def main() -> int:
    root = find_project_root()
    if "--selfcheck" in sys.argv:
        return do_selfcheck(root)
    do_app(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
