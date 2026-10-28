from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import skill_store as store


SKILL_ROOT = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = Path(__file__).resolve().parent / "serve_dashboard.py"
RUNTIME_STATE_PATH = store.CENTER_HOME / "data" / "server-runtime.json"
SERVER_LOG_PATH = store.CENTER_HOME / "logs" / "server.log"
DEFAULT_PORT = 8765


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _health(port: int, timeout: float = 0.8) -> dict[str, Any] | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if response.status == 200 else None
    except (OSError, URLError, json.JSONDecodeError):
        return None


def _runtime() -> dict[str, Any]:
    state = _read_json(RUNTIME_STATE_PATH)
    port = int(state.get("port") or 0)
    state["running"] = bool(port and _health(port))
    return state


def _unlink_runtime_state() -> bool:
    for _ in range(12):
        try:
            RUNTIME_STATE_PATH.unlink(missing_ok=True)
            return True
        except PermissionError:
            time.sleep(0.05)
        except OSError:
            break
    return not RUNTIME_STATE_PATH.exists()


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            handle.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _center_write_check() -> tuple[bool, str]:
    try:
        target = store.CENTER_HOME / "data"
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="doctor-", dir=target, delete=True):
            pass
        return True, str(target)
    except OSError:
        return False, "The runtime data directory is not writable."


def doctor_report(port: int = DEFAULT_PORT) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, severity: str = "error") -> None:
        checks.append(
            {
                "name": name,
                "ok": bool(ok),
                "severity": "ok" if ok else severity,
                "detail": detail,
            }
        )

    add(
        "python",
        sys.version_info >= (3, 10),
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )
    add(
        "package",
        SERVER_SCRIPT.is_file() and (SKILL_ROOT / "assets" / "dashboard").is_dir(),
        str(SKILL_ROOT),
    )
    writable, write_detail = _center_write_check()
    add("runtime-directory", writable, write_detail)

    config = store.load_scan_sources()
    config_errors = [str(item) for item in config.get("_load_errors", [])]
    add(
        "scan-source-config",
        not config_errors,
        "Configuration is readable." if not config_errors else " ".join(config_errors),
    )

    if store.DB_PATH.is_file():
        try:
            connection = sqlite3.connect(
                store.DB_PATH.resolve().as_uri() + "?mode=ro",
                uri=True,
            )
            try:
                version = store._schema_version(connection)
            finally:
                connection.close()
            add(
                "database",
                version <= store.DATABASE_SCHEMA_VERSION,
                f"schema={version}; file={store.DB_PATH.name}",
            )
        except (OSError, sqlite3.Error, RuntimeError) as exc:
            add("database", False, f"Database check failed: {type(exc).__name__}")
    elif store.LEGACY_DB_PATH.is_file():
        add(
            "database",
            True,
            "Legacy database found; it will be copied into the isolated v2 database on first scan.",
            severity="warning",
        )
    else:
        add(
            "database",
            True,
            "Not initialized yet; the first start will create the v2 database.",
            severity="warning",
        )

    runtime = _runtime()
    if runtime.get("running"):
        add(
            "service",
            True,
            f"Running at {runtime.get('url') or f'http://127.0.0.1:{runtime.get('port')}'}",
        )
    else:
        available = _port_available(port)
        add(
            "service-port",
            available,
            f"Port {port} is available." if available else f"Port {port} is occupied by another process.",
        )

    failed = [item for item in checks if not item["ok"] and item["severity"] == "error"]
    return {
        "status": "pass" if not failed else "fail",
        "checks": checks,
        "center_home": str(store.CENTER_HOME),
        "database": str(store.DB_PATH),
        "runtime_state": str(RUNTIME_STATE_PATH),
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"Skill Center doctor: {report['status'].upper()}")
    for item in report["checks"]:
        marker = "OK" if item["ok"] else "WARN" if item["severity"] == "warning" else "FAIL"
        print(f"[{marker}] {item['name']}: {item['detail']}")
    print(f"Runtime: {report['center_home']}")


def command_doctor(args: argparse.Namespace) -> int:
    report = doctor_report(args.port)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0 if report["status"] == "pass" else 1


def command_status(args: argparse.Namespace) -> int:
    state = _runtime()
    payload = {
        "running": bool(state.get("running")),
        "pid": state.get("pid"),
        "port": state.get("port"),
        "url": state.get("url"),
        "runtime_state": str(RUNTIME_STATE_PATH),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif payload["running"]:
        print(f"Skill Center is running: {payload['url']}")
    else:
        print("Skill Center is not running. Use: python scripts/skill_center.py start --open")
    return 0 if payload["running"] else 1


def command_start(args: argparse.Namespace) -> int:
    state = _runtime()
    if state.get("running"):
        url = str(state.get("url") or f"http://127.0.0.1:{state['port']}/my-skills.html")
        print(f"Skill Center is already running: {url}")
        if args.open:
            webbrowser.open(url)
        return 0

    report = doctor_report(args.port)
    fatal = [item for item in report["checks"] if not item["ok"] and item["severity"] == "error"]
    if fatal:
        _print_report(report)
        print("Start cancelled. Fix the FAIL items or choose another port.")
        return 1

    SERVER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(SERVER_SCRIPT),
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
    ]
    creationflags = 0
    popen_options: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    else:
        popen_options["start_new_session"] = True
    with SERVER_LOG_PATH.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=creationflags,
            close_fds=True,
            **popen_options,
        )

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if _health(args.port):
            url = f"http://127.0.0.1:{args.port}/my-skills.html"
            print(f"Skill Center started: {url}")
            print(f"Server log: {SERVER_LOG_PATH}")
            if args.open:
                webbrowser.open(url)
            return 0
        if process.poll() is not None:
            break
        time.sleep(0.2)

    print(f"Skill Center did not start. Run doctor and inspect: {SERVER_LOG_PATH}")
    return 1


def command_stop(args: argparse.Namespace) -> int:
    state = _runtime()
    if not state.get("running"):
        _unlink_runtime_state()
        print("Skill Center is already stopped.")
        return 0
    token = str(state.get("token") or "")
    port = int(state["port"])
    request = Request(
        f"http://127.0.0.1:{port}/api/shutdown",
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Skill-Center-Token": token,
        },
    )
    try:
        with urlopen(request, timeout=2) as response:
            if response.status != 200:
                raise RuntimeError(f"unexpected status {response.status}")
    except (HTTPError, URLError, OSError, RuntimeError):
        print("Skill Center could not be stopped through its local control endpoint.")
        print(f"Run doctor and inspect: {SERVER_LOG_PATH}")
        return 1

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if not _health(port, timeout=0.2):
            if not _unlink_runtime_state():
                print("Skill Center stopped; stale runtime metadata will be cleaned on the next start.")
                return 0
            print("Skill Center stopped.")
            return 0
        time.sleep(0.15)
    print("The stop request was accepted, but the service is still responding.")
    return 1


def command_restart(args: argparse.Namespace) -> int:
    if command_stop(args) != 0:
        return 1
    return command_start(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start, inspect, and recover the local Skill Center.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start the dashboard in the background")
    start.add_argument("--port", type=int, default=DEFAULT_PORT)
    start.add_argument("--timeout", type=float, default=10.0)
    start.add_argument("--open", action="store_true", help="Open the dashboard after it is healthy")
    start.set_defaults(handler=command_start)

    stop = subparsers.add_parser("stop", help="Stop the background dashboard safely")
    stop.add_argument("--timeout", type=float, default=5.0)
    stop.set_defaults(handler=command_stop)

    restart = subparsers.add_parser("restart", help="Stop and start the dashboard")
    restart.add_argument("--port", type=int, default=DEFAULT_PORT)
    restart.add_argument("--timeout", type=float, default=10.0)
    restart.add_argument("--open", action="store_true")
    restart.set_defaults(handler=command_restart)

    status = subparsers.add_parser("status", help="Show whether the dashboard is running")
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=command_status)

    doctor = subparsers.add_parser("doctor", help="Check Python, paths, config, database, and port")
    doctor.add_argument("--port", type=int, default=DEFAULT_PORT)
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=command_doctor)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
