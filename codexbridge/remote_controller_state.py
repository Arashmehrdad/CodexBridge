from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from .remote_resource_enforcement import RemoteMemoryPolicy

REMOTE_CONTROLLER_STATE_VERSION = 1
REMOTE_CONTROLLER_VERSION = "codexbridge-remote-controller-v1"


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_remote_controller_state_contract(
    *,
    run_id: str,
    host_id: str,
    command_id: str,
    lease_generation: int,
    remote_argv: list[str],
    timeout_seconds: int | None,
    memory_policy: RemoteMemoryPolicy | None = None,
) -> dict[str, Any]:
    normalized_timeout = None if timeout_seconds is None else int(timeout_seconds)
    accepted_memory_policy = memory_policy or RemoteMemoryPolicy()
    request_identity = {
        "host_id": host_id,
        "command_id": command_id,
        "remote_argv": list(remote_argv),
        "timeout_seconds": normalized_timeout,
    }
    idempotency_key = _canonical_sha256(request_identity)
    execution_id = _canonical_sha256(
        {
            "run_id": run_id,
            "lease_generation": int(lease_generation),
            "idempotency_key": idempotency_key,
        }
    )[:32]
    remote_state_dir = f".codexbridge/jobs/{execution_id}"
    controller_fingerprint = _canonical_sha256(
        {
            "version": REMOTE_CONTROLLER_VERSION,
            "contract_version": REMOTE_CONTROLLER_STATE_VERSION,
        }
    )
    return {
        "version": REMOTE_CONTROLLER_STATE_VERSION,
        "request_id": run_id,
        "execution_id": execution_id,
        "idempotency_key": idempotency_key,
        "host_id": host_id,
        "command_id": command_id,
        "lease_generation": int(lease_generation),
        "controller": {
            "version": REMOTE_CONTROLLER_VERSION,
            "fingerprint": controller_fingerprint,
        },
        "remote": {
            "state_dir": remote_state_dir,
            "state_path": f"{remote_state_dir}/state.json",
            "input_path": f"{remote_state_dir}/input.json",
            "stdout_path": f"{remote_state_dir}/stdout.bin",
            "stderr_path": f"{remote_state_dir}/stderr.bin",
            "result_path": f"{remote_state_dir}/result.json",
            "pid": None,
            "pgid": None,
            "process_start_identity": "",
            "authoritative_state": "launch_pending",
            "heartbeat_at": "",
            "cancellation_requested_at": "",
            "cancellation_completed_at": "",
            "publication_state": "pending",
            "cleanup_state": "pending",
        },
        "local": {
            "remote_job_id": execution_id,
            "remote_state_dir": remote_state_dir,
            "remote_pid": None,
            "remote_pgid": None,
            "remote_process_start_identity": "",
            "last_authoritative_heartbeat": "",
            "publication_state": "pending",
            "cleanup_state": "pending",
            "reconciliation_state": "not_started",
            "uncertainty_state": "none",
        },
        "execution": {
            "argv_sha256": _canonical_sha256(list(remote_argv)),
            "timeout_seconds": normalized_timeout,
            "executable_identity": str(remote_argv[0]) if remote_argv else "",
            "shell_identity": "direct_argv",
            "resource_monitor_state": {
                "status": "not_started",
                "memory_policy": accepted_memory_policy.to_metadata(),
                "latest_sample": None,
                "latest_decision": None,
                "sampled_at": "",
            },
        },
    }


def reconcile_remote_controller_state(
    contract: dict[str, Any],
    observed: dict[str, Any] | None,
) -> dict[str, Any]:
    if observed is None:
        return {
            "reconciliation_state": "uncertain",
            "uncertainty_state": "network_or_state_unavailable",
            "adoptable": False,
            "terminal": False,
            "authoritative_state": "unknown",
            "remote_process": {},
            "result": {},
        }

    if (
        observed.get("request_id") != contract.get("request_id")
        or observed.get("execution_id") != contract.get("execution_id")
        or observed.get("idempotency_key") != contract.get("idempotency_key")
        or observed.get("controller") != contract.get("controller")
    ):
        raise ValueError("Remote-controller state identity does not match accepted contract")

    remote = dict(observed.get("remote") or {})
    authoritative_state = str(remote.get("authoritative_state", "unknown"))
    process = {
        "pid": remote.get("pid"),
        "pgid": remote.get("pgid"),
        "start_time_ticks": str(remote.get("process_start_identity", "")),
        "execution_id": observed.get("execution_id"),
        "state_path": remote.get("state_path"),
        "authoritative_state": authoritative_state,
        "heartbeat_at": remote.get("heartbeat_at"),
        "durable_ownership": bool(remote.get("pid") and remote.get("pgid")),
    }
    live = authoritative_state in {"launch_pending", "running", "cancellation_pending"}
    terminal = authoritative_state in {"completed", "failed", "cancelled", "timed_out"}
    if live:
        return {
            "reconciliation_state": "adopted",
            "uncertainty_state": "none",
            "adoptable": True,
            "terminal": False,
            "authoritative_state": authoritative_state,
            "remote_process": process,
            "result": {},
        }
    if terminal:
        return {
            "reconciliation_state": "terminal_observed",
            "uncertainty_state": "none",
            "adoptable": False,
            "terminal": True,
            "authoritative_state": authoritative_state,
            "remote_process": process,
            "result": dict(observed.get("result") or {}),
        }
    return {
        "reconciliation_state": "uncertain",
        "uncertainty_state": "invalid_authoritative_state",
        "adoptable": False,
        "terminal": False,
        "authoritative_state": authoritative_state,
        "remote_process": process,
        "result": {},
    }


def validate_remote_controller_state_contract(
    contract: dict[str, Any],
    *,
    run_id: str,
    host_id: str,
    command_id: str,
    lease_generation: int,
    remote_argv: list[str],
    timeout_seconds: int | None,
    memory_policy: RemoteMemoryPolicy | None = None,
) -> dict[str, Any]:
    expected = build_remote_controller_state_contract(
        run_id=run_id,
        host_id=host_id,
        command_id=command_id,
        lease_generation=lease_generation,
        remote_argv=remote_argv,
        timeout_seconds=timeout_seconds,
        memory_policy=memory_policy,
    )
    if contract != expected:
        raise ValueError("Remote-controller state contract changed after acceptance")
    return expected
