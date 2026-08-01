from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .run_store import LEGACY_READ_ONLY_TOOLS, RUN_ID_PATTERN, TERMINAL_STATUSES


_MAX_LEGACY_JSON_BYTES = 8 * 1024 * 1024


def _read_json_object(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Legacy run evidence is not a regular file: {path.name}")
    if path.stat().st_size > _MAX_LEGACY_JSON_BYTES:
        raise ValueError(f"Legacy run evidence exceeds the read limit: {path.name}")
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Legacy run evidence must contain a JSON object: {path.name}")
    return value, raw


def _created_at_from_run_id(run_id: str) -> str:
    observed = datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ").replace(
        tzinfo=timezone.utc
    )
    return observed.isoformat()


def _legacy_status(result: dict[str, Any]) -> str:
    explicit = str(result.get("status") or "")
    if explicit in TERMINAL_STATUSES:
        return explicit
    if bool(result.get("blocked")) or result.get("blockers"):
        return "needs_input"
    if bool(result.get("safety_failure")):
        return "failed"
    exit_code = result.get("exit_code")
    if isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0:
        return "failed"
    # Historical results written before the SQLite authority often omitted a
    # status. `partial` is terminal but does not invent full success.
    return "partial"


def load_legacy_filesystem_run(runs_root: Path, run_id: str) -> dict[str, Any] | None:
    """Read one inert pre-database Codex run without creating new authority."""
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"Invalid run_id: {run_id}")
    tool = run_id[17:-9]
    if tool not in LEGACY_READ_ONLY_TOOLS:
        return None

    root = runs_root.resolve()
    candidate = runs_root / run_id
    if candidate.is_symlink() or not candidate.is_dir():
        return None
    run_dir = candidate.resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("Legacy run directory escapes the configured runs root") from exc

    input_path = run_dir / "input.json"
    result_path = run_dir / "result.json"
    if not input_path.exists() or not result_path.exists():
        return None
    input_data, input_json = _read_json_object(input_path)
    result, result_json = _read_json_object(result_path)

    reported_run_id = str(result.get("run_id") or "")
    if reported_run_id and reported_run_id != run_id:
        raise ValueError("Legacy result identity does not match its directory")
    reported_tool = str(result.get("tool") or "")
    if reported_tool and reported_tool != tool:
        raise ValueError("Legacy result tool identity does not match its directory")
    input_repo = str(input_data.get("repo_name") or "")
    result_repo = str(result.get("repo_name") or "")
    if input_repo and result_repo and input_repo != result_repo:
        raise ValueError("Legacy input and result repository identities disagree")

    status = _legacy_status(result)
    started_at = str(result.get("started_at") or "") or None
    ended_at = str(result.get("ended_at") or "") or None
    created_at = started_at or _created_at_from_run_id(run_id)
    repo_name = result_repo or input_repo
    return {
        "run_id": run_id,
        "repo_name": repo_name,
        "tool": tool,
        "status": status,
        "risk_level": "legacy_read_only",
        "requires_human": False,
        "created_at": created_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": result.get("duration_seconds"),
        "elapsed_seconds": result.get("duration_seconds") or 0.0,
        "pid": 0,
        "launcher_pid": 0,
        "worker_pid": 0,
        "state_version": 0,
        "worker_claimed_at": None,
        "launch_attempts": 0,
        "current_phase": "legacy_evidence",
        "heartbeat_at": None,
        "exit_code": result.get("exit_code"),
        "summary": str(result.get("summary") or ""),
        "error": str(result.get("error") or ""),
        "safety_failure": bool(result.get("safety_failure")),
        "recovery_reason": "",
        "run_dir": str(run_dir),
        "input": input_data,
        "input_json": input_json,
        "progress": {},
        "result": result,
        "result_json": result_json,
        "public_result": {},
        "public_result_status": "not_materialized",
        "public_result_schema_version": "",
        "public_result_source_sha256": "",
        "result_publication_status": "legacy_filesystem_only",
        "result_published_hash": "",
        "result_published_at": None,
        "result_publication_error": "",
        "legacy_filesystem_only": True,
        "database_record_present": False,
        "authoritative_storage": f"runs/{run_id}",
    }
