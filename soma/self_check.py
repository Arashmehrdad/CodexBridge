from __future__ import annotations

import argparse
import json
import sys
import time
from importlib import metadata
from pathlib import Path
from typing import Sequence

from .capabilities import PATCH_OPERATION_SCHEMA, capability_metadata
from .config import AppConfig, load_config
from .run_store import RunStore
from .supervisor_store import SupervisorStore


def _trading_lab_check() -> dict:
    try:
        from .trading_lab_adapter import package_identity

        identity = package_identity()
    except Exception as exc:
        return {"ok": False, "error": f"trading_lab unavailable: {exc}"}
    return {"ok": bool(identity.get("version")), **identity}


def _distribution_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return ""


def run_self_check(
    *,
    config: AppConfig | None = None,
    config_path: str | Path | None = "config.yaml",
) -> dict:
    """Run only cheap in-process readiness checks.

    This synchronous path never starts subprocesses, runs pytest or pip, calls
    Git, waits for a port, or launches another MCP server. Comprehensive
    validation is the durable PowerShell script reported in the result.
    """
    started = time.perf_counter()
    root = Path.cwd().resolve()
    checks: dict[str, dict] = {}

    modules = ("fastmcp", "pydantic", "yaml", "trading_lab")
    import_error = ""
    for module in modules:
        try:
            __import__(module)
        except Exception as exc:
            import_error = f"{module}: {exc}"
            break
    checks["imports"] = {
        "ok": not import_error,
        "modules": list(modules),
        "error": import_error,
    }
    checks["packages"] = {
        "ok": bool(_distribution_version("fastmcp") and _distribution_version("pydantic")),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "versions": {
            "soma": _distribution_version("soma"),
            "fastmcp": _distribution_version("fastmcp"),
            "pydantic": _distribution_version("pydantic"),
            "trading-lab": _distribution_version("trading-lab"),
        },
    }
    checks["trading_lab"] = _trading_lab_check()

    if config is None:
        try:
            config = load_config(config_path or "config.yaml")
            checks["config"] = {"ok": True, "path": str(config_path)}
        except Exception as exc:
            checks["config"] = {"ok": False, "path": str(config_path), "error": str(exc)}
    else:
        checks["config"] = {"ok": True, "path": str(config_path) if config_path else None}

    runs_dir = config.resolve_runs_dir() if config else root / "runs"
    try:
        store = RunStore(runs_dir)
        with store.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        mode = store.journal_mode()
        checks["run_store"] = {
            "ok": mode == "wal",
            "db_path": str(store.db_path),
            "journal_mode": mode,
        }
    except Exception as exc:
        checks["run_store"] = {"ok": False, "error": str(exc)}

    try:
        supervisor_store = SupervisorStore(runs_dir)
        required_tables = {
            "supervisors", "supervisor_events", "supervisor_run_links",
            "operation_locks", "supervisor_notifications",
        }
        with supervisor_store.connect() as conn:
            existing = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        missing = sorted(required_tables - existing)
        mode = supervisor_store.journal_mode()
        checks["supervisor_store"] = {
            "ok": mode == "wal" and not missing,
            "db_path": str(supervisor_store.db_path),
            "journal_mode": mode,
            "required_tables": sorted(required_tables),
            "missing_tables": missing,
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
    else:
        checks["supervisor_config"] = {"ok": False, "error": "config unavailable"}

    checks["service_identity"] = {
        "ok": True,
        **capability_metadata(PATCH_OPERATION_SCHEMA),
    }
    checks["comprehensive_validation"] = {
        "ok": True,
        "available": True,
        "execution": "run_start powershell",
        "script": "scripts/comprehensive_self_check.ps1",
        "includes": [
            "pip check", "full pytest", "git diff --check",
            "package identity", "MCP startup on a free port",
        ],
    }

    ok = all(check.get("ok", False) for check in checks.values())
    return {
        "ok": ok,
        "mode": "lightweight",
        "checks": checks,
        "duration_seconds": round(time.perf_counter() - started, 6),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run lightweight Soma self-checks.")
    parser.add_argument("--config", default="config.yaml")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run_self_check(config_path=args.config)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
