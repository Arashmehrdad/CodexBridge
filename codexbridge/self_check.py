from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import AppConfig, load_config
from .run_store import RunStore
from .supervisor_store import SupervisorStore


def _run(command: list[str], cwd: Path, timeout: int = 120) -> dict:
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_seconds": round(time.time() - started, 3),
            "ok": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "Command timed out",
            "duration_seconds": round(time.time() - started, 3),
            "ok": False,
        }


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _endpoint_reachable(url: str, timeout: float = 2.0) -> dict:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return {"url": url, "status": response.status, "ok": response.status < 500}
    except HTTPError as exc:
        return {"url": url, "status": exc.code, "ok": exc.code < 500, "error": str(exc)}
    except URLError as exc:
        return {"url": url, "status": None, "ok": False, "error": str(exc.reason)}
    except OSError as exc:
        return {"url": url, "status": None, "ok": False, "error": str(exc)}


def _wait_for_endpoint(url: str, timeout_seconds: float = 10.0) -> dict:
    deadline = time.time() + timeout_seconds
    last = {"url": url, "ok": False, "error": "not checked"}
    while time.time() < deadline:
        last = _endpoint_reachable(url)
        if last["ok"]:
            return last
        time.sleep(0.25)
    return last


def _start_server_probe(
    config_path: Path, host: str, port: int, path: str, cwd: Path
) -> dict:
    command = [
        sys.executable,
        "-m",
        "codexbridge.server",
        "--config",
        str(config_path),
        "--transport",
        "http",
        "--host",
        host,
        "--port",
        str(port),
        "--path",
        path,
    ]
    process = subprocess.Popen(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    url = f"http://{host}:{port}{path}"
    try:
        readiness = _wait_for_endpoint(url)
        poll = process.poll()
        process_started = poll is None
        return {
            "command": command,
            "process_started": process_started,
            "endpoint": readiness,
            "transport_ready": process_started and readiness["ok"],
            "ok": process_started and readiness["ok"],
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def run_self_check(
    *,
    config: AppConfig | None = None,
    config_path: str | Path | None = "config.yaml",
    live_host: str = "127.0.0.1",
    live_port: int | None = None,
    live_path: str = "/mcp",
    run_live_server: bool = True,
    run_tests: bool = True,
) -> dict:
    root = Path.cwd().resolve()
    checks: dict[str, dict] = {}

    checks["imports"] = {"ok": True, "modules": ["fastmcp", "pydantic", "yaml"]}
    for module in checks["imports"]["modules"]:
        try:
            __import__(module)
        except Exception as exc:
            checks["imports"] = {"ok": False, "module": module, "error": str(exc)}
            break

    if config is None:
        try:
            config = load_config(config_path or "config.yaml")
            checks["config"] = {"ok": True, "path": str(config_path)}
        except Exception as exc:
            checks["config"] = {
                "ok": False,
                "path": str(config_path),
                "error": str(exc),
            }
    else:
        checks["config"] = {
            "ok": True,
            "path": str(config_path) if config_path else None,
        }

    checks["pip_check"] = _run([sys.executable, "-m", "pip", "check"], root)
    checks["git_status"] = _run(["git", "status", "--short", "--branch"], root)
    if not (root / ".git").exists() and not checks["git_status"]["ok"]:
        checks["git_status"]["ok"] = True
        checks["git_status"]["warning"] = (
            "CodexBridge workspace is not a git repo; target repos are validated from config."
        )
    if run_tests:
        checks["pytest"] = _run(
            [sys.executable, "-m", "pytest", "-q"], root, timeout=300
        )

    try:
        store = RunStore(config.resolve_runs_dir() if config else root / "runs")
        checks["run_store"] = {
            "ok": store.journal_mode() == "wal",
            "db_path": str(store.db_path),
            "journal_mode": store.journal_mode(),
        }
    except Exception as exc:
        checks["run_store"] = {"ok": False, "error": str(exc)}

    try:
        supervisor_store = SupervisorStore(
            config.resolve_runs_dir() if config else root / "runs"
        )
        required_tables = {
            "supervisors",
            "supervisor_events",
            "supervisor_run_links",
            "operation_locks",
            "supervisor_notifications",
        }
        with supervisor_store.connect() as conn:
            existing_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        missing_tables = sorted(required_tables - existing_tables)
        journal_mode = supervisor_store.journal_mode()
        checks["supervisor_store"] = {
            "ok": journal_mode == "wal" and not missing_tables,
            "db_path": str(supervisor_store.db_path),
            "journal_mode": journal_mode,
            "required_tables": sorted(required_tables),
            "missing_tables": missing_tables,
        }
    except Exception as exc:
        checks["supervisor_store"] = {"ok": False, "error": str(exc)}

    if config:
        supervisors = config.supervisors
        notifications = supervisors.notifications
        default_profile = supervisors.default_autonomy_profile
        checks["supervisor_config"] = {
            "ok": default_profile in supervisors.autonomy_profiles,
            "default_autonomy_profile": default_profile,
            "available_profiles": sorted(supervisors.autonomy_profiles),
            "notifications_enabled": notifications.enabled,
            "notification_sinks": {
                "file_enabled": notifications.file.enabled,
                "webhook_enabled": notifications.webhook.enabled,
                "windows_toast_enabled": notifications.windows_toast.enabled,
            },
        }
        supervisor_prompt_root = config.resolve_runs_dir() / "supervisors"
        checks["supervisor_resume_prompts"] = {
            "ok": config.resolve_runs_dir().exists(),
            "root": str(supervisor_prompt_root),
            "pattern": str(
                supervisor_prompt_root / "<supervisor_id>" / "resume_prompt.txt"
            ),
        }
    else:
        checks["supervisor_config"] = {"ok": False, "error": "config unavailable"}
        checks["supervisor_resume_prompts"] = {
            "ok": False,
            "error": "config unavailable",
        }

    if run_live_server:
        if config_path is None:
            checks["transport"] = {
                "ok": False,
                "transport_ready": False,
                "error": "config_path is required for live server startup probe",
            }
        elif not checks["config"]["ok"] or not checks["imports"]["ok"]:
            checks["transport"] = {
                "ok": False,
                "transport_ready": False,
                "error": "Skipping server probe because config or imports failed",
            }
        else:
            port = live_port or _free_port(live_host)
            checks["transport"] = _start_server_probe(
                Path(config_path).resolve(), live_host, port, live_path, root
            )
    else:
        checks["transport"] = {"ok": True, "transport_ready": None, "skipped": True}

    ok = all(check.get("ok", False) for check in checks.values())
    return {"ok": ok, "checks": checks}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CodexBridge local self-checks.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 chooses a free port")
    parser.add_argument("--path", default="/mcp")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-live-server", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run_self_check(
        config_path=args.config,
        live_host=args.host,
        live_port=args.port or None,
        live_path=args.path,
        run_tests=not args.skip_tests,
        run_live_server=not args.skip_live_server,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
