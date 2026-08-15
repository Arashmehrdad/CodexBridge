from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .cloudflare_tools import authorize_cloudflare_profile, build_cloudflare_action
from .command_profiles import (
    BASH_N_PATH_COMMAND_ID,
    GIT_READONLY_COMMAND_ID,
    JSON_VALIDATE_PATH_COMMAND_ID,
    PYTEST_PATH_COMMAND_ID,
    PY_COMPILE_PATH_COMMAND_ID,
    build_bash_n_path_profile,
    build_git_readonly_profile,
    build_json_validate_path_profile,
    build_py_compile_path_profile,
    build_pytest_path_profile,
    resolve_command_profile,
)
from .config import AppConfig, resolve_repo, resolve_repo_config
from .docker_tools import build_docker_action
from .events import ArtifactWriter, redact_and_truncate
from .external_fixtures import validate_fixture_request
from .executable_profiles import build_local_executable_run_request
from .executable_staging import (
    build_executable_staging_manifest,
    stage_executable_input,
)
from .gateway_models import (
    canonicalize_hash_pinned_ssh_script,
    validate_reviewed_ssh_script_request,
    validate_root_ssh_shell_request,
)
from .operation_locks import OperationLockStore
from .public_projection_contract import (
    DEFAULT_PUBLIC_BYTE_BUDGETS,
    NON_AUTHORITATIVE_NOTICE,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
    PublicView,
    truncate_utf8,
)
from .parallel_groups import (
    ParallelGroupStore,
    launch_powershell_group,
    refill_powershell_groups,
    repository_lock_required_for_run,
)
from .policy import PolicyDecision
from .process_control import (
    process_group_popen_kwargs,
    process_is_running,
    process_matches_identity,
    terminate_process_tree,
    identity_scoped_termination,
    capture_launch_identity,
    LaunchIdentityUnavailable,
    ProcessContainmentUncertain,
    require_identity_scoped_cleanup,
)
from .run_query_chunks import (
    RUN_REFERENCE_PREFIX,
    chunk_payload,
    decode_list_reference,
    decode_run_reference,
    list_resource_id,
    redact_payload,
)
from .run_store import (
    LEGACY_READ_ONLY_TOOLS,
    RUN_SUMMARY_MAX_LIMIT,
    TERMINAL_STATUSES,
    RunRequestConflict,
    RunStore,
    validate_run_id,
)
from .run_public_result import (
    PUBLIC_RESULT_SCHEMA_VERSION,
    PUBLIC_RESULT_STATUS_FALLBACK,
    PUBLIC_RESULT_STATUS_READY,
    authoritative_result_sha256,
    build_pending_public_result,
    build_public_result_fallback,
    build_public_result_projection,
)
from .run_publication import (
    materialize_public_result,
    publish_run_result,
    terminal_result_publication_needs_repair,
)
from .run_artifacts import read_redacted_output_tail, resolve_output_artifacts
from .legacy_run_reader import load_legacy_filesystem_run
from .remote_controller_state import (
    build_remote_controller_state_contract,
    reconcile_remote_controller_state,
)
from .remote_powershell import (
    build_remote_powershell_durable_input,
    build_remote_powershell_request,
)
from .ssh_staging import build_ssh_staging_manifest, stage_ssh_inputs
from .ssh_profile_manager import get_ssh_profile_change_status
from .transfer_manifests import build_upload_transfer_manifest
from .safety import redact_secret_values, validate_repo_relative_path
from .ssh_commands import (
    resolve_ssh_command_profile,
    resolve_ssh_connection,
    resolve_ssh_host,
)
from .ssh_policy import (
    SSHActionAuthorizationResult,
    authorize_ssh_action_launch,
    authorize_ssh_reviewed_script_launch,
    authorize_ssh_root_shell_launch,
)
from .ssh_watchdog import (
    cancel_remote_controller,
    probe_remote_controller_state,
    validate_monitored_command_start,
)
from .ssh_tools import build_ssh_action, validate_remote_path

if TYPE_CHECKING:
    from .continuations.store import ContinuationStore


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_run_id(tool: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tool = "".join(char if char.isalnum() else "_" for char in tool.lower())
    return f"{timestamp}_{safe_tool}_{uuid4().hex[:8]}"


def _ssh_policy_metadata(policy: SSHActionAuthorizationResult) -> dict[str, object]:
    return {
        "autonomy_profile": policy.autonomy_profile,
        "execution_mode": policy.execution_mode,
        "permission_tier": policy.permission_tier.value,
        "policy_decision": policy.decision.value,
        "policy_authorized": policy.authorized,
        "approval_source": policy.approval_source,
    }


RUN_PUBLIC_SUMMARY_FIELDS = (
    "run_id",
    "repo_name",
    "tool",
    "status",
    "risk_level",
    "requires_human",
    "created_at",
    "started_at",
    "ended_at",
    "duration_seconds",
    "state_version",
    "launch_attempts",
    "recovery_reason",
    "exit_code",
    "summary",
    "error",
    "safety_failure",
    "current_phase",
    "elapsed_seconds",
    "heartbeat_at",
    "heartbeat_age_seconds",
    "worker_stale",
    "result_publication_status",
    "result_published_hash",
    "result_published_at",
    "result_publication_error",
    "legacy_filesystem_only",
    "database_record_present",
    "authoritative_storage",
)
RUN_SUMMARY_TEXT_BYTE_LIMITS = {
    "summary": 2048,
    "error": 2048,
    "recovery_reason": 512,
    "result_publication_error": 512,
}
RUN_SUMMARY_LIST_TEXT_BYTE_LIMITS = {
    "summary": 256,
    "error": 256,
    "recovery_reason": 128,
    "result_publication_error": 128,
}
RUN_PUBLIC_CONTROL_FIELDS = (
    "run_id",
    "repo_name",
    "tool",
    "status",
    "risk_level",
    "requires_human",
    "state_version",
    "created_at",
    "started_at",
    "ended_at",
    "duration_seconds",
    "lease_generation",
    "worker_claimed_at",
    "launch_attempts",
    "current_phase",
    "elapsed_seconds",
    "heartbeat_at",
    "heartbeat_age_seconds",
    "worker_stale",
    "launcher_pid",
    "launcher_running",
    "worker_pid",
    "worker_identity_present",
    "worker_running",
    "child_pid",
    "child_running",
    "last_output_at",
    "cancellation_requested_at",
    "lock",
    "result_publication_status",
    "result_published_hash",
    "result_published_at",
    "result_publication_error",
    "exit_code",
    "details_available",
    "summary",
    "error",
    "safety_failure",
    "recovery_reason",
    "legacy_filesystem_only",
    "database_record_present",
    "authoritative_storage",
)
RUN_CONTROL_TEXT_BYTE_LIMITS = {
    "summary": 1024,
    "error": 1536,
    "recovery_reason": 512,
    "result_publication_error": 1024,
}
RUN_EVENT_TEXT_BYTE_LIMITS = {
    "level": 64,
    "stage": 128,
    "message": 1024,
}
RUN_EVENT_DATA_BYTE_LIMIT = 2048


def _canonical_public_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _project_run_summary(
    run: dict,
    *,
    text_limits: dict[str, int],
    divisor: int = 1,
) -> dict:
    projected = {
        field: run[field] for field in RUN_PUBLIC_SUMMARY_FIELDS if field in run
    }
    truncated_fields: dict[str, dict[str, object]] = {}
    for field, maximum_bytes in text_limits.items():
        value = projected.get(field)
        if value is None:
            continue
        safe_value = redact_secret_values(str(value))
        truncated = truncate_utf8(safe_value, max(0, maximum_bytes // divisor))
        projected[field] = truncated.text
        if truncated.truncated:
            truncated_fields[field] = {
                "original_bytes": truncated.original_bytes,
                "returned_bytes": truncated.returned_bytes,
                "omitted_sha256": truncated.omitted_sha256,
            }
    if truncated_fields:
        projected["truncated_fields"] = truncated_fields
    return projected


def _finalize_compact_projection(payload: dict, byte_budget: int) -> dict:
    result = dict(payload)
    result.pop("payload_bytes", None)
    result["payload_bytes"] = len(_canonical_public_json_bytes(result))
    if len(_canonical_public_json_bytes(result)) > byte_budget:
        raise ValueError(
            "Compact run response exceeds its serialized UTF-8 byte budget"
        )
    return result


def _compact_projection_metadata(
    byte_budget: int, *, view: PublicView = PublicView.SUMMARY
) -> dict:
    return {
        "view": view.value,
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "byte_budget": byte_budget,
    }


def _build_run_summary_response(run: dict) -> dict:
    byte_budget = DEFAULT_PUBLIC_BYTE_BUDGETS.run_summary
    for divisor in (1, 2, 4, 8, 16, 32, 64, 128, 256, 1024, 4096):
        payload = {
            "ok": True,
            "operation": "summary",
            "run": _project_run_summary(
                run,
                text_limits=RUN_SUMMARY_TEXT_BYTE_LIMITS,
                divisor=divisor,
            ),
            "authoritative_operation": "status",
            "error": "",
            **_compact_projection_metadata(byte_budget),
        }
        try:
            return _finalize_compact_projection(payload, byte_budget)
        except ValueError:
            continue
    raise ValueError("Run summary cannot fit its public byte budget")


def _build_run_summary_list_response(
    page: dict,
    *,
    requested_limit: int,
    byte_limited: bool,
    projected_runs: list[dict] | None = None,
) -> dict:
    byte_budget = DEFAULT_PUBLIC_BYTE_BUDGETS.run_list
    selected_runs = (
        [
            _project_run_summary(
                run,
                text_limits=RUN_SUMMARY_LIST_TEXT_BYTE_LIMITS,
            )
            for run in page["runs"]
        ]
        if projected_runs is None
        else list(projected_runs)
    )
    if len(selected_runs) != len(page["runs"]):
        raise ValueError("Projected run-summary count does not match the source page")
    payload = {
        "ok": True,
        "operation": "summary_list",
        "runs": selected_runs,
        "limit": page["limit"],
        "requested_limit": requested_limit,
        "returned_count": len(page["runs"]),
        "byte_limited": byte_limited,
        "has_more": page["has_more"],
        "next_cursor": page["next_cursor"],
        "ordering": page["ordering"],
        "authoritative_operation": "list",
        "error": "",
        **_compact_projection_metadata(byte_budget),
    }
    return _finalize_compact_projection(payload, byte_budget)


def _project_run_control(control: dict, *, divisor: int = 1) -> dict:
    projected = {
        field: control[field] for field in RUN_PUBLIC_CONTROL_FIELDS if field in control
    }
    truncated_fields: dict[str, dict[str, object]] = {}
    for field, maximum_bytes in RUN_CONTROL_TEXT_BYTE_LIMITS.items():
        value = projected.get(field)
        if value is None:
            continue
        safe_value = redact_secret_values(str(value))
        truncated = truncate_utf8(safe_value, max(0, maximum_bytes // divisor))
        projected[field] = truncated.text
        if truncated.truncated:
            truncated_fields[field] = {
                "original_bytes": truncated.original_bytes,
                "returned_bytes": truncated.returned_bytes,
                "omitted_sha256": truncated.omitted_sha256,
            }
    if truncated_fields:
        projected["truncated_fields"] = truncated_fields
    return projected


def _build_run_control_response(control: dict, *, operation: str = "control") -> dict:
    if operation not in {"status", "control"}:
        raise ValueError("run lifecycle operation must be status or control")
    byte_budget = DEFAULT_PUBLIC_BYTE_BUDGETS.run_control
    for divisor in (1, 2, 4, 8, 16, 32, 64, 128, 256, 1024, 4096):
        payload = {
            "ok": True,
            "operation": operation,
            "unchanged": False,
            **_project_run_control(control, divisor=divisor),
            "authoritative_operation": "status",
            **_compact_projection_metadata(byte_budget, view=PublicView.STANDARD),
        }
        try:
            return _finalize_compact_projection(payload, byte_budget)
        except ValueError:
            continue
    raise ValueError(f"Run {operation} response cannot fit its public byte budget")


def _build_unchanged_control_response(run_id: str, state_version: int) -> dict:
    byte_budget = DEFAULT_PUBLIC_BYTE_BUDGETS.unchanged_poll
    return _finalize_compact_projection(
        {
            "ok": True,
            "operation": "control",
            "unchanged": True,
            "run_id": run_id,
            "state_version": state_version,
            "authoritative_operation": "status",
            "error": "",
            **_compact_projection_metadata(byte_budget, view=PublicView.STANDARD),
        },
        byte_budget,
    )


def _project_run_event(event: dict) -> dict:
    projected = {
        field: event[field]
        for field in ("id", "timestamp", "run_id", "level", "stage", "message")
        if field in event
    }
    truncated_fields: dict[str, dict[str, object]] = {}
    for field, maximum_bytes in RUN_EVENT_TEXT_BYTE_LIMITS.items():
        safe_value = redact_secret_values(str(projected.get(field) or ""))
        truncated = truncate_utf8(safe_value, maximum_bytes)
        projected[field] = truncated.text
        if truncated.truncated:
            truncated_fields[field] = {
                "original_bytes": truncated.original_bytes,
                "returned_bytes": truncated.returned_bytes,
                "omitted_sha256": truncated.omitted_sha256,
            }

    safe_data = redact_and_truncate(event.get("data", {}), 512)
    encoded_data = _canonical_public_json_bytes(safe_data)
    if len(encoded_data) <= RUN_EVENT_DATA_BYTE_LIMIT:
        projected["data"] = safe_data
    else:
        preview = truncate_utf8(
            encoded_data.decode("utf-8", errors="replace"),
            RUN_EVENT_DATA_BYTE_LIMIT,
        )
        projected["data"] = {
            "truncated": True,
            "original_bytes": len(encoded_data),
            "returned_bytes": preview.returned_bytes,
            "content_sha256": sha256(encoded_data).hexdigest(),
            "preview": preview.text,
        }
    if truncated_fields:
        projected["truncated_fields"] = truncated_fields
    return projected


def _build_run_event_response(
    page: dict,
    *,
    requested_limit: int,
    byte_limited: bool,
    projected_events: list[dict] | None = None,
) -> dict:
    byte_budget = DEFAULT_PUBLIC_BYTE_BUDGETS.events
    events = (
        [_project_run_event(event) for event in page["events"]]
        if projected_events is None
        else list(projected_events)
    )
    if len(events) != len(page["events"]):
        raise ValueError("Projected event count does not match the source page")
    return _finalize_compact_projection(
        {
            "ok": True,
            "operation": "events",
            "run_id": events[0]["run_id"] if events else page.get("run_id", ""),
            "events": events,
            "limit": page["limit"],
            "requested_limit": requested_limit,
            "returned_count": len(events),
            "byte_limited": byte_limited,
            "has_more": page["has_more"],
            "next_after_id": page["next_after_id"],
            "next_cursor": page["next_cursor"],
            "ordering": page["ordering"],
            "cursor_expires_at_utc": page["cursor_expires_at_utc"],
            "authoritative_operation": "events",
            "error": "",
            **_compact_projection_metadata(byte_budget, view=PublicView.STANDARD),
        },
        byte_budget,
    )


def _fit_output_response(response: dict, response_budget_bytes: int) -> None:
    budget = max(4 * 1024, min(int(response_budget_bytes), 12 * 1024))
    response["response_budget_bytes"] = budget
    response["truncated"] = False
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > budget:
        candidates = [
            (name, item.get("text", ""))
            for name, item in response.get("streams", {}).items()
            if isinstance(item, dict) and item.get("text")
        ]
        if not candidates:
            response["truncated"] = True
            break
        name, text = max(candidates, key=lambda pair: len(pair[1]))
        encoded = text.encode("utf-8")
        reduced = max(0, len(encoded) - max(256, len(encoded) // 4))
        response["streams"][name]["text"] = encoded[:reduced].decode(
            "utf-8", errors="ignore"
        )
        response["streams"][name]["truncated"] = True
        response["truncated"] = True
    response["response_bytes"] = len(
        json.dumps(response, ensure_ascii=False).encode("utf-8")
    )


STARTUP_TERMINAL_ARTIFACT_AUDIT_LIMIT = 100


class JobManager:
    def __init__(self, config: AppConfig, config_path: Path | None):
        self.config = config
        self.config_path = config_path
        self.store = RunStore(config.resolve_runs_dir())
        self.locks = OperationLockStore(config.resolve_runs_dir())
        self._continuation_store: "ContinuationStore | None" = None
        self._remote_reconciliation_lock = threading.Lock()
        self._remote_reconciliation_pollers: set[str] = set()

    @property
    def continuation_store(self) -> "ContinuationStore":
        """Lazily initialize continuation persistence only for associated Runs."""
        if self._continuation_store is None:
            from .continuations.store import ContinuationStore

            self._continuation_store = ContinuationStore(self.config.resolve_runs_dir())
        return self._continuation_store

    def _require_active_ssh_autonomy_profile(self, autonomy_profile: str) -> None:
        if autonomy_profile != "permissive":
            raise ValueError(
                f"SSH autonomy profile '{autonomy_profile}' is not supported; "
                "only 'permissive' is active"
            )

    def reconcile_startup(self) -> int:
        reconciled = 0
        recoverable_runs = self.store.list_recoverable_runs()
        recoverable_ids = {run["run_id"] for run in recoverable_runs}
        for run in recoverable_runs:
            try:
                self._reconcile_run(run)
            except Exception as exc:
                reason = f"Startup reconciliation failed: {exc}"
                self.store.mark_recovery_pending(
                    run["run_id"],
                    reason,
                    expected_statuses=(str(run["status"]),),
                    expected_state_version=int(run.get("state_version") or 0),
                    expected_lease_token=str(run.get("worker_lease_token") or ""),
                    expected_lease_generation=int(run.get("lease_generation") or 1),
                    expected_heartbeat_at=run.get("heartbeat_at"),
                )
                self._append_recovery_event(
                    run,
                    level="error",
                    message=reason,
                    data={"exception_type": type(exc).__name__},
                )
            reconciled += 1
        repair_candidates = {
            run["run_id"]: run
            for run in self.store.list_terminal_publication_repair_candidates(
                public_result_schema_version=PUBLIC_RESULT_SCHEMA_VERSION
            )
            if run["run_id"] not in recoverable_ids
        }
        for run in self.store.list_recent_terminal_runs(
            STARTUP_TERMINAL_ARTIFACT_AUDIT_LIMIT
        ):
            if (
                run["run_id"] not in recoverable_ids
                and terminal_result_publication_needs_repair(run)
            ):
                repair_candidates[run["run_id"]] = run
        for run in repair_candidates.values():
            try:
                publication = publish_run_result(self.store, run["run_id"])
                if not publication["ok"]:
                    self._append_recovery_event(
                        run,
                        level="error",
                        message="Canonical terminal result publication failed",
                        data={"error": publication["error"]},
                    )
            except Exception as exc:
                reason = f"Startup result publication repair failed: {exc}"
                self._append_recovery_event(
                    run,
                    level="error",
                    message=reason,
                    data={"exception_type": type(exc).__name__},
                )
            reconciled += 1
        self.locks.recover_stale()
        reconciled += len(
            refill_powershell_groups(
                config=self.config,
                spawn_worker=self._spawn_worker,
            )
        )
        return reconciled

    def _start_remote_reconciliation_poller(self, run_id: str) -> bool:
        with self._remote_reconciliation_lock:
            if run_id in self._remote_reconciliation_pollers:
                return False
            self._remote_reconciliation_pollers.add(run_id)

        def poll() -> None:
            try:
                while True:
                    current = self.store.get_run(run_id)
                    if current["status"] in TERMINAL_STATUSES:
                        return
                    if current["tool"] not in {
                        "ssh_monitored_command",
                        "remote_powershell",
                    }:
                        return
                    contract = current.get("input", {}).get("remote_controller_state")
                    if not isinstance(contract, dict):
                        return
                    self._reconcile_run(current)
                    current = self.store.get_run(run_id)
                    if current["status"] in TERMINAL_STATUSES:
                        return
                    time.sleep(5.0)
            finally:
                with self._remote_reconciliation_lock:
                    self._remote_reconciliation_pollers.discard(run_id)

        threading.Thread(
            target=poll,
            name=f"soma-remote-reconcile-{run_id}",
            daemon=True,
        ).start()
        return True

    def _worker_command(self, run_id: str, lease_token: str) -> list[str]:
        return [
            sys.executable,
            "-m",
            "soma.job_worker",
            "--config",
            str(self.config_path),
            "--run-id",
            run_id,
            "--lease-token",
            lease_token,
        ]

    def _spawn_worker(self, run_id: str, lease_token: str):
        return subprocess.Popen(
            self._worker_command(run_id, lease_token),
            cwd=Path.cwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=os.name != "nt",
            **process_group_popen_kwargs(),
        )

    def _append_recovery_event(
        self,
        run: dict,
        *,
        level: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        event = self.store.append_event(
            run["run_id"],
            level=level,
            stage="reconcile",
            message=message,
            data=data or {},
            update_run_metadata=False,
        )
        ArtifactWriter(Path(run["run_dir"])).append_event(event)

    def _fail_recovery(self, run: dict, reason: str) -> bool:
        lease_token = str(run.get("worker_lease_token") or "")
        lease_generation = int(run.get("lease_generation") or 1)
        failed = self.store.fail_infrastructure(
            run["run_id"],
            reason,
            expected_statuses=(str(run["status"]),),
            expected_state_version=int(run.get("state_version") or 0),
            expected_lease_token=lease_token,
            expected_lease_generation=lease_generation,
            expected_heartbeat_at=run.get("heartbeat_at"),
        )
        if failed is None:
            return False
        publication = publish_run_result(self.store, run["run_id"])
        if not publication["ok"]:
            self._append_recovery_event(
                run,
                level="error",
                message="Canonical terminal result publication failed",
                data={"error": publication["error"]},
            )
        self.locks.release(
            run["repo_name"],
            run["run_id"],
            lease_token,
            lease_generation,
        )
        self._append_recovery_event(run, level="error", message=reason)
        return True

    def _reconcile_run(self, run: dict) -> None:
        run_id = run["run_id"]
        status = str(run.get("status") or "")
        lease_token = str(run.get("worker_lease_token") or "")
        lease_generation = int(run.get("lease_generation") or 1)
        state_version = int(run.get("state_version") or 0)
        observed_heartbeat = run.get("heartbeat_at")
        worker_pid = int(run.get("worker_pid") or 0)
        worker_identity = str(run.get("worker_identity") or "")
        launcher_pid = int(run.get("launcher_pid") or 0)
        child_pid = int(run.get("pid") or 0)
        worker_verified = process_matches_identity(worker_pid, worker_identity)
        launcher_running = process_is_running(launcher_pid)
        child_running = process_is_running(child_pid)

        if worker_verified:
            adopted = self.store.adopt_worker(
                run_id,
                expected_state_version=state_version,
                lease_token=lease_token,
                lease_generation=lease_generation,
                expected_heartbeat_at=observed_heartbeat,
            )
            current = adopted or self.store.get_run(run_id)
            if adopted is None and not (
                current["status"] == "running"
                and str(current.get("worker_lease_token") or "") == lease_token
                and int(current.get("lease_generation") or 1) == lease_generation
                and process_matches_identity(
                    int(current.get("worker_pid") or 0),
                    str(current.get("worker_identity") or ""),
                )
            ):
                return
            lock_claimed = True
            if repository_lock_required_for_run(run, self.config.resolve_runs_dir()):
                lock_claimed = self.locks.claim_owner(
                    run["repo_name"],
                    run_id,
                    owner_pid=int(current.get("worker_pid") or worker_pid),
                    owner_token=lease_token,
                    lease_generation=lease_generation,
                )
            if not lock_claimed:
                reason = "Verified worker could not reclaim matching repository lock ownership"
                contained = self.store.mark_recovery_pending(
                    run_id,
                    reason,
                    expected_statuses=("running",),
                    expected_state_version=int(current["state_version"]),
                    expected_lease_token=lease_token,
                    expected_lease_generation=lease_generation,
                    expected_heartbeat_at=current.get("heartbeat_at"),
                )
                if contained is not None:
                    self._append_recovery_event(run, level="error", message=reason)
                return
            if adopted is not None:
                self._append_recovery_event(
                    run,
                    level="info",
                    message="Active worker identity verified after server restart",
                    data={"worker_pid": worker_pid},
                )
            return

        if run["tool"] in {"ssh_monitored_command", "remote_powershell"}:
            contract = run.get("input", {}).get("remote_controller_state")
            if isinstance(contract, dict):
                probe = probe_remote_controller_state(
                    self.config,
                    str(run["input"]["host_id"]),
                    contract,
                )
                observed = probe.get("state") if probe.get("ok") else None
                if isinstance(observed, dict) and isinstance(probe.get("result"), dict):
                    observed = dict(observed)
                    observed["result"] = dict(probe["result"])
                reconciled_remote = reconcile_remote_controller_state(
                    contract, observed
                )
                progress = dict(run.get("progress") or {})
                progress.update(
                    {
                        "remote_reconciliation": reconciled_remote,
                        "remote_probe_error": str(probe.get("error", "")),
                    }
                )
                remote_process = dict(reconciled_remote.get("remote_process") or {})
                if remote_process:
                    progress["remote_process"] = remote_process
                if reconciled_remote.get("terminal"):
                    remote_result = dict(reconciled_remote.get("result") or {})
                    authoritative_state = str(
                        reconciled_remote.get("authoritative_state") or "failed"
                    )
                    terminal_status = (
                        authoritative_state
                        if authoritative_state in TERMINAL_STATUSES
                        else "failed"
                    )
                    ended_at = str(
                        remote_result.get("ended_at")
                        or datetime.now(timezone.utc).isoformat()
                    )
                    exit_code = int(remote_result.get("returncode", 1))
                    result = {
                        "run_id": run_id,
                        "repo_name": run["repo_name"],
                        "tool": str(run["tool"]),
                        "host_id": str(run["input"]["host_id"]),
                        "command_id": str(run["input"]["command_id"]),
                        "status": terminal_status,
                        "exit_code": exit_code,
                        "started_at": str(
                            run.get("started_at") or run.get("created_at") or ended_at
                        ),
                        "ended_at": ended_at,
                        "duration_seconds": float(run.get("elapsed_seconds") or 0.0),
                        "summary": f"Remote controller reported {authoritative_state}",
                        "error": ""
                        if exit_code == 0
                        else f"Remote command exited with code {exit_code}",
                        "safety_failure": False,
                        "remote_process": remote_process,
                        "remote_controller_result": remote_result,
                        "reconciled_after_restart": True,
                    }
                    persisted = self.store.transition_terminal(
                        run_id,
                        status=terminal_status,
                        result=result,
                        expected_statuses=(status,),
                        expected_state_version=state_version,
                        expected_lease_token=lease_token,
                        expected_lease_generation=lease_generation,
                        ended_at=ended_at,
                        duration_seconds=result["duration_seconds"],
                        exit_code=exit_code,
                        summary=result["summary"],
                        error=result["error"],
                        safety_failure=False,
                    )
                    if persisted is not None:
                        publication = publish_run_result(self.store, run_id)
                        if not publication["ok"]:
                            self._append_recovery_event(
                                run,
                                level="error",
                                message="Canonical terminal result publication failed",
                                data={"error": publication["error"]},
                            )
                        self.locks.release(
                            run["repo_name"], run_id, lease_token, lease_generation
                        )
                        self._append_recovery_event(
                            run,
                            level="info",
                            message="Terminal remote-controller evidence reconciled after restart",
                            data={"authoritative_state": authoritative_state},
                        )
                    return
                reason = (
                    "Matching remote controller adopted after restart"
                    if reconciled_remote.get("adoptable")
                    else "Remote controller state remains uncertain after restart"
                )
                pending = self.store.conditional_update(
                    run_id,
                    fields={
                        "status": "recovery_pending",
                        "current_phase": "remote_reconciliation",
                        "ended_at": None,
                        "progress_json": progress,
                        "error": "" if reconciled_remote.get("adoptable") else reason,
                        "recovery_reason": reason,
                        "safety_failure": not bool(reconciled_remote.get("adoptable")),
                    },
                    expected_statuses=(status,),
                    expected_state_version=state_version,
                    expected_lease_token=lease_token,
                    expected_lease_generation=lease_generation,
                    expected_heartbeat_at=observed_heartbeat,
                    reject_terminal=True,
                )
                if pending is not None:
                    self._append_recovery_event(
                        run,
                        level="info"
                        if reconciled_remote.get("adoptable")
                        else "warning",
                        message=reason,
                        data={
                            "reconciliation_state": reconciled_remote.get(
                                "reconciliation_state"
                            ),
                            "uncertainty_state": reconciled_remote.get(
                                "uncertainty_state"
                            ),
                        },
                    )
                    if reconciled_remote.get("adoptable"):
                        self._start_remote_reconciliation_poller(run_id)
                return
            reason = "Monitored remote execution lacks a durable controller contract"
            pending = self.store.mark_recovery_pending(
                run_id,
                reason,
                expected_statuses=(status,),
                expected_state_version=state_version,
                expected_lease_token=lease_token,
                expected_lease_generation=lease_generation,
                expected_heartbeat_at=observed_heartbeat,
            )
            if pending is not None:
                self._append_recovery_event(run, level="warning", message=reason)
            return

        if child_running:
            reason = (
                "Worker ownership is unavailable while a child process remains active"
            )
            recovered = self.store.mark_recovery_pending(
                run_id,
                reason,
                expected_statuses=(status,),
                expected_state_version=state_version,
                expected_lease_token=lease_token,
                expected_lease_generation=lease_generation,
                expected_heartbeat_at=observed_heartbeat,
            )
            if recovered is not None:
                self._append_recovery_event(
                    run,
                    level="warning",
                    message=reason,
                    data={"child_pid": child_pid},
                )
            return

        if status in {"launch_pending", "queued"}:
            if run["tool"] in LEGACY_READ_ONLY_TOOLS:
                reason = (
                    "Legacy Codex run cannot be relaunched: Codex execution "
                    "has been removed from Soma. The record remains readable."
                )
                contained = self.store.mark_recovery_pending(
                    run_id,
                    reason,
                    expected_statuses=(status,),
                    expected_state_version=state_version,
                    expected_lease_token=lease_token,
                    expected_lease_generation=lease_generation,
                    expected_heartbeat_at=observed_heartbeat,
                )
                if contained is not None:
                    self._append_recovery_event(run, level="warning", message=reason)
                return
            if launcher_running:
                self._append_recovery_event(
                    run,
                    level="warning",
                    message="Launcher remains active; awaiting canonical worker claim",
                    data={"launcher_pid": launcher_pid},
                )
                return
            if int(run.get("launch_attempts") or 0) < 2:
                new_lease_token = uuid4().hex
                logical_id = str(run.get("logical_run_request_id") or "")
                refreshed_input = (
                    self._rebuild_logical_run_input_for_lease(
                        run, lease_generation + 1
                    )
                    if logical_id
                    else None
                )
                repository_lock_required = bool(
                    (run.get("input") or {}).get("repository_lock_required", True)
                )
                if logical_id and not repository_lock_required:
                    assert refreshed_input is not None
                    reservation = self.store.reserve_next_unlocked_launch(
                        run_id=run_id,
                        expected_statuses=(status,),
                        expected_state_version=state_version,
                        expected_lease_token=str(
                            run.get("worker_lease_token") or ""
                        ),
                        expected_lease_generation=lease_generation,
                        new_lease_token=new_lease_token,
                        input_data=refreshed_input,
                    )
                else:
                    reservation = self.locks.reserve_next_launch(
                        repo_name=run["repo_name"],
                        run_id=run_id,
                        expected_statuses=(status,),
                        expected_state_version=state_version,
                        expected_owner_token=str(
                            run.get("worker_lease_token") or ""
                        ),
                        expected_lease_generation=lease_generation,
                        new_owner_token=new_lease_token,
                        owner_pid=os.getpid(),
                        input_data=refreshed_input,
                    )
                if reservation is None:
                    return
                try:
                    if refreshed_input is not None:
                        refreshed_run = self.store.get_run(run_id)
                        self._materialize_logical_run_launch_artifacts(
                            refreshed_run, refreshed_input
                        )
                    process = self._spawn_worker(run_id, new_lease_token)
                    launcher_identity = capture_launch_identity(process)
                    launched = self.store.record_worker_launch(
                        run_id,
                        process.pid,
                        launcher_identity=launcher_identity,
                        expected_state_version=int(reservation["state_version"]),
                        expected_lease_token=new_lease_token,
                        expected_lease_generation=int(reservation["lease_generation"]),
                        increment_attempt=False,
                    )
                    if repository_lock_required:
                        self.locks.heartbeat(
                            run["repo_name"],
                            run_id,
                            new_lease_token,
                            int(reservation["lease_generation"]),
                        )
                    current = launched or self.store.get_run(run_id)
                    if not (
                        str(current.get("worker_lease_token") or "") == new_lease_token
                        and int(current.get("lease_generation") or 1)
                        == int(reservation["lease_generation"])
                    ):
                        # Identity was captured above, so the PID is meaningful
                        # and cleanup is identity-scoped and re-verified.
                        require_identity_scoped_cleanup(
                            process.pid, launcher_identity, process=process
                        )
                        return
                    self._append_recovery_event(
                        run,
                        level="warning",
                        message="Stranded queued worker relaunched once",
                        data={
                            "launcher_pid": process.pid,
                            "lease_generation": int(reservation["lease_generation"]),
                        },
                    )
                except (LaunchIdentityUnavailable, ProcessContainmentUncertain) as exc:
                    current = self.store.get_run(run_id)
                    if str(
                        current.get("worker_lease_token") or ""
                    ) == new_lease_token and int(
                        current.get("lease_generation") or 1
                    ) == int(reservation["lease_generation"]):
                        containment = (
                            exc.containment.to_dict()
                            if isinstance(exc, LaunchIdentityUnavailable)
                            else exc.report
                        )
                        if (
                            isinstance(exc, LaunchIdentityUnavailable)
                            and exc.containment.terminal_containment_proven
                        ):
                            self._fail_recovery(
                                current,
                                f"Worker relaunch failed during startup recovery: {exc}",
                            )
                        else:
                            reason = (
                                "Worker relaunch containment is uncertain; "
                                "mutation ownership retained"
                            )
                            pending = self.store.mark_recovery_pending(
                                run_id,
                                reason,
                                expected_statuses=(str(current["status"]),),
                                expected_state_version=int(current["state_version"]),
                                expected_lease_token=new_lease_token,
                                expected_lease_generation=int(
                                    reservation["lease_generation"]
                                ),
                                expected_heartbeat_at=current.get("heartbeat_at"),
                            )
                            if pending is not None:
                                self._append_recovery_event(
                                    current,
                                    level="error",
                                    message=reason,
                                    data={"containment": containment},
                                )
                    return
                except Exception as exc:
                    current = self.store.get_run(run_id)
                    if str(
                        current.get("worker_lease_token") or ""
                    ) == new_lease_token and int(
                        current.get("lease_generation") or 1
                    ) == int(reservation["lease_generation"]):
                        self._fail_recovery(
                            current,
                            f"Worker relaunch failed during startup recovery: {exc}",
                        )
                return
            self._fail_recovery(
                run, "Queued run exhausted its bounded worker launch attempts"
            )
            return

        if status == "running":
            if worker_pid and worker_identity:
                self._fail_recovery(
                    run, "Verified worker process is no longer active after restart"
                )
                return
            reason = "Running legacy record has no verifiable worker identity"
            recovered = self.store.mark_recovery_pending(
                run_id,
                reason,
                expected_statuses=("running",),
                expected_state_version=state_version,
                expected_lease_token=lease_token,
                expected_lease_generation=lease_generation,
                expected_heartbeat_at=observed_heartbeat,
            )
            if recovered is not None:
                self._append_recovery_event(run, level="warning", message=reason)
            return

        if status in {"cancellation_pending", "recovery_pending"}:
            self._append_recovery_event(
                run,
                level="warning",
                message="Conservative recovery state retained pending operator action",
            )

    def start_executable_profile(
        self,
        repo_name: str,
        profile_id: str,
        argv: list[str],
        *,
        working_directory: str = "",
        environment: dict[str, str] | None = None,
        stdin_text: str | None = None,
        stdin_bytes: bytes | None = None,
        timeout_seconds: int | None = None,
        reserved_run_id: str | None = None,
        logical_run_request_id: str = "",
        continuation_context_ref: str = "",
        hermes_companion: dict | None = None,
    ) -> dict:
        resolve_repo(self.config, repo_name)
        request = build_local_executable_run_request(
            self.config,
            profile_id,
            argv,
            working_directory=working_directory,
            default_working_directory=str(resolve_repo(self.config, repo_name)),
            environment=environment,
            stdin_text=stdin_text,
            stdin_bytes=stdin_bytes,
            timeout_seconds=timeout_seconds,
        )
        timeout = request.get("timeout_seconds")
        estimated_minutes = 1 if timeout is None else max(1, (int(timeout) + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=4,
            risk_level="high",
            requires_human=False,
            reason="Enabled permissive executable profile is approved for durable execution",
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        input_data = {"repo_name": repo_name, **request}
        if hermes_companion is not None:
            if not isinstance(hermes_companion, dict):
                raise ValueError("Hermes companion metadata must be a mapping")
            input_data["hermes_companion"] = dict(hermes_companion)
            input_data["repository_lock_required"] = False
        response = self._create_and_launch(
            "executable_profile",
            repo_name,
            input_data,
            decision,
            reserved_run_id=reserved_run_id,
            logical_run_request_id=logical_run_request_id,
            continuation_context_ref=continuation_context_ref,
        )
        response.setdefault("repo_name", repo_name)
        response["profile_id"] = profile_id
        return response

    def wait_for_terminal_or_timeout(
        self, start_response: dict, wait_seconds: float
    ) -> dict:
        """Wait at most 20 seconds for terminal publication without cancelling."""
        bounded_wait = float(wait_seconds)
        if bounded_wait < 0.0 or bounded_wait > 20.0:
            raise ValueError("wait_seconds must be between 0 and 20")
        response = dict(start_response)
        run_id = str(response.get("run_id") or "")
        response["return_when"] = "terminal_or_timeout"
        response["wait_seconds"] = bounded_wait
        response.setdefault(
            "polling",
            {"tool": "run_query", "request": {"operation": "status", "run_id": run_id}},
        )
        response.setdefault(
            "evidence",
            {
                "tool": "run_query",
                "request": {"operation": "terminal", "run_id": run_id},
            },
        )
        if not response.get("accepted") or not run_id:
            response["inline_completion"] = False
            return response

        deadline = time.monotonic() + bounded_wait
        while True:
            snapshot = self.store.get_run_summary(run_id)
            if str(snapshot.get("status") or "") in TERMINAL_STATUSES:
                terminal = dict(self.get_terminal_result(run_id))
                terminal.update(
                    {
                        "accepted": True,
                        "inline_completion": True,
                        "return_when": "terminal_or_timeout",
                        "wait_seconds": bounded_wait,
                    }
                )
                return terminal
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                response["inline_completion"] = False
                response["wait_timed_out"] = True
                response["status"] = str(
                    snapshot.get("status") or response.get("status") or "queued"
                )
                response["state_version"] = int(snapshot.get("state_version") or 0)
                return response
            time.sleep(min(0.05, remaining))

    def start_powershell_group(
        self,
        repo_name: str,
        children: list[dict],
        *,
        requested_concurrency: int | None = None,
        repository_lock_policy: str = "none",
        failure_policy: str = "continue_all",
    ) -> dict:
        return launch_powershell_group(
            config=self.config,
            repo_name=repo_name,
            children=children,
            spawn_worker=self._spawn_worker,
            requested_concurrency=requested_concurrency,
            repository_lock_policy=repository_lock_policy,
            failure_policy=failure_policy,
        )

    def get_powershell_group(self, group_id: str) -> dict:
        return ParallelGroupStore(self.config.resolve_runs_dir()).refresh_group(
            group_id
        )

    def cancel_powershell_group(self, group_id: str) -> dict:
        store = ParallelGroupStore(self.config.resolve_runs_dir())
        group = store.get_group(group_id)
        pending_statuses = {"pending", "launch_pending", "queued", "recovery_pending"}
        children = sorted(
            group["children"],
            key=lambda child: (
                0 if str(child["status"]) in pending_statuses else 1,
                int(child["position"]),
            ),
        )
        cancellations: list[dict] = []
        for child in children:
            if str(child["status"]) in TERMINAL_STATUSES:
                continue
            cancellations.append(
                self.cancel_run(str(child["run_id"]), suppress_group_refill=True)
            )
        refill_powershell_groups(
            config=self.config,
            spawn_worker=self._spawn_worker,
        )
        refreshed = store.refresh_group(group_id)
        return {
            "ok": all(
                bool(item.get("termination_confirmed")) for item in cancellations
            ),
            "group_id": group_id,
            "status": refreshed["status"],
            "cancelled": refreshed["status"] == "cancelled",
            "children": cancellations,
            "result": refreshed["result"],
        }

    def enforce_powershell_group_failure_policy(self, run_id: str) -> dict | None:
        store = ParallelGroupStore(self.config.resolve_runs_dir())
        try:
            group = store.get_group_for_child(run_id)
        except KeyError:
            return None
        if (
            str(group.get("failure_policy") or "continue_all")
            != "cancel_remaining_on_failure"
        ):
            return None
        failed_child = store.store.get_run(run_id)
        if str(failed_child.get("status") or "") not in {"failed", "timed_out"}:
            return None
        cancellations: list[dict] = []
        for child in group["children"]:
            child_run_id = str(child["run_id"])
            if child_run_id == run_id or str(child["status"]) in TERMINAL_STATUSES:
                continue
            cancellations.append(
                self.cancel_run(child_run_id, suppress_group_refill=True)
            )
        refill_powershell_groups(
            config=self.config,
            spawn_worker=self._spawn_worker,
        )
        refreshed = store.refresh_group(str(group["group_id"]))
        return {
            "group_id": str(group["group_id"]),
            "trigger_run_id": run_id,
            "cancelled_children": cancellations,
            "status": refreshed["status"],
            "result": refreshed["result"],
        }

    def start_project_command(
        self, repo_name: str, command_id: str, *, reserved_run_id: str | None = None
    ) -> dict:
        resolve_repo(self.config, repo_name)
        _, repo_config = resolve_repo_config(self.config, repo_name)
        repo_profiles = list(repo_config.command_profiles or [])
        profile = resolve_command_profile(command_id, repo_profiles)
        estimated_minutes = max(1, (profile.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=1,
            risk_level="low" if not profile.writes_files else "medium",
            requires_human=False,
            reason="Allowlisted project command is approved for durable async execution",
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        response = self._create_and_launch(
            "project_command",
            repo_name,
            {"repo_name": repo_name, "command_id": command_id},
            decision,
            reserved_run_id=reserved_run_id,
        )
        response.setdefault("repo_name", repo_name)
        response["command_id"] = command_id
        return response

    def start_repo_apply(
        self, repo_name: str, operation: str, payload: dict[str, object]
    ) -> dict:
        """Durably record and launch one managed repository apply request."""
        resolve_repo(self.config, repo_name)
        if operation not in {"previewed_change", "cleanup", "revert", "move_file"}:
            raise ValueError(f"Unsupported repository apply operation: {operation}")
        input_data = {"repo_name": repo_name, "operation": operation, **payload}
        decision = PolicyDecision(
            accepted=True,
            tier=4,
            risk_level="medium",
            requires_human=False,
            reason="Hash-verified managed repository apply is approved for durable execution",
            estimated_duration_minutes=1,
            recommended_check_after_minutes=1,
        )
        response = self._create_and_launch(
            "repo_apply", repo_name, input_data, decision
        )
        response.setdefault("repo_name", repo_name)
        response["operation"] = operation
        return response

    def start_pytest_path(
        self, repo_name: str, path: str, *, reserved_run_id: str | None = None
    ) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        profile = build_pytest_path_profile(repo_root, path)
        decision = PolicyDecision(
            accepted=True,
            tier=1,
            risk_level="low",
            requires_human=False,
            reason="Allowlisted scoped pytest command is approved for durable async execution",
            estimated_duration_minutes=max(1, (profile.timeout_seconds + 59) // 60),
            recommended_check_after_minutes=min(
                2, max(1, (profile.timeout_seconds + 59) // 60)
            ),
        )
        normalized_target = profile.argv[-1]
        response = self._create_and_launch(
            "project_command",
            repo_name,
            {
                "repo_name": repo_name,
                "command_id": PYTEST_PATH_COMMAND_ID,
                "path": normalized_target,
            },
            decision,
            reserved_run_id=reserved_run_id,
        )
        response.setdefault("repo_name", repo_name)
        response["command_id"] = PYTEST_PATH_COMMAND_ID
        response["path"] = normalized_target
        return response

    def start_py_compile_path(
        self, repo_name: str, path: str, *, timeout_seconds: int | None = None
    ) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        profile = build_py_compile_path_profile(repo_root, path)
        return self._start_validated_path_command(
            repo_name,
            command_id=PY_COMPILE_PATH_COMMAND_ID,
            normalized_target=profile.argv[-1],
            timeout_seconds=timeout_seconds or profile.timeout_seconds,
            reason="Allowlisted py_compile path validation is approved for durable async execution",
        )

    def start_bash_n_path(
        self, repo_name: str, path: str, *, timeout_seconds: int | None = None
    ) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        profile = build_bash_n_path_profile(repo_root, path)
        return self._start_validated_path_command(
            repo_name,
            command_id=BASH_N_PATH_COMMAND_ID,
            normalized_target=profile.argv[-1],
            timeout_seconds=timeout_seconds or profile.timeout_seconds,
            reason="Allowlisted bash -n path validation is approved for durable async execution",
        )

    def start_json_validation_path(
        self, repo_name: str, path: str, *, timeout_seconds: int | None = None
    ) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        profile = build_json_validate_path_profile(repo_root, path)
        return self._start_validated_path_command(
            repo_name,
            command_id=JSON_VALIDATE_PATH_COMMAND_ID,
            normalized_target=profile.argv[-1],
            timeout_seconds=timeout_seconds or profile.timeout_seconds,
            reason="Allowlisted JSON validation path is approved for durable async execution",
        )

    def start_git_readonly(
        self, repo_name: str, operation: str, *, reserved_run_id: str | None = None
    ) -> dict:
        resolve_repo(self.config, repo_name)
        profile = build_git_readonly_profile(operation)
        decision = PolicyDecision(
            accepted=True,
            tier=1,
            risk_level="low",
            requires_human=False,
            reason="Allowlisted read-only git operation is approved for durable async execution",
            estimated_duration_minutes=max(1, (profile.timeout_seconds + 59) // 60),
            recommended_check_after_minutes=1,
        )
        response = self._create_and_launch(
            "project_command",
            repo_name,
            {
                "repo_name": repo_name,
                "command_id": GIT_READONLY_COMMAND_ID,
                "operation": operation,
            },
            decision,
            reserved_run_id=reserved_run_id,
        )
        response.setdefault("repo_name", repo_name)
        response["command_id"] = GIT_READONLY_COMMAND_ID
        response["operation"] = operation
        return response

    def start_docker_action(
        self,
        repo_name: str,
        action: str,
        *,
        target: str = "",
        destination: str = "",
        services: list[str] | None = None,
        command_id: str = "",
        context: str = ".",
        dockerfile: str = "",
        build: bool = False,
        force: bool = False,
        confirmation: str = "",
    ) -> dict:
        repo_root = resolve_repo(self.config, repo_name)
        _, repo_config = resolve_repo_config(self.config, repo_name)
        normalized_services = list(services or [])
        spec = build_docker_action(
            self.config,
            repo_root,
            repo_config,
            action,
            target=target,
            destination=destination,
            services=normalized_services,
            command_id=command_id,
            context=context,
            dockerfile=dockerfile,
            build=build,
            force=force,
            confirmation=confirmation,
        )
        estimated_minutes = max(1, (spec.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=3 if spec.high_risk else 2,
            risk_level="high" if spec.high_risk else "medium",
            requires_human=False,
            reason=(
                "Explicitly confirmed high-risk Docker action is approved"
                if spec.high_risk
                else "Bounded Docker action is approved for durable async execution"
            ),
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        input_data = {
            "repo_name": repo_name,
            "action": action,
            "target": target,
            "destination": destination,
            "services": normalized_services,
            "command_id": command_id,
            "context": context,
            "dockerfile": dockerfile,
            "build": build,
            "force": force,
            "confirmation": confirmation,
        }
        response = self._create_and_launch(
            "docker_action", repo_name, input_data, decision
        )
        response.setdefault("repo_name", repo_name)
        response["action"] = action
        response["high_risk"] = spec.high_risk
        return response

    def start_external_fixture_validation(
        self,
        repo_name: str,
        url: str,
        expected_sha256: str,
        validation: str = "none",
    ) -> dict:
        resolve_repo(self.config, repo_name)
        validate_fixture_request(
            self.config.external_fixtures,
            url,
            expected_sha256,
            validation,
        )
        estimated_minutes = max(
            1, (self.config.external_fixtures.timeout_seconds + 59) // 60
        )
        decision = PolicyDecision(
            accepted=True,
            tier=2,
            risk_level="medium",
            requires_human=False,
            reason=(
                "Hash-pinned fixture from an allowlisted HTTPS host is approved "
                "for isolated durable validation"
            ),
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        return self._create_and_launch(
            "external_fixture_validation",
            repo_name,
            {
                "repo_name": repo_name,
                "url": url,
                "expected_sha256": expected_sha256.lower(),
                "validation": validation,
            },
            decision,
        )

    def start_ssh_command(
        self,
        host_id: str,
        command_id: str,
        *,
        autonomy_profile: str = "permissive",
        execution_mode: str = "structured",
    ) -> dict:
        self._require_active_ssh_autonomy_profile(autonomy_profile)
        _, profile = resolve_ssh_command_profile(self.config, host_id, command_id)
        policy = authorize_ssh_action_launch(
            autonomy_profile=autonomy_profile,
            execution_mode=execution_mode,
            writes_remote=profile.writes_remote,
            chatgpt_approval_granted=True,
        )
        policy_metadata = _ssh_policy_metadata(policy)
        estimated_minutes = max(1, (profile.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=2 if profile.writes_remote else 1,
            risk_level="medium" if profile.writes_remote else "low",
            requires_human=False,
            reason="Allowlisted SSH command is approved for durable async execution",
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        response = self._create_and_launch(
            "ssh_command",
            f"ssh:{host_id}",
            {
                "host_id": host_id,
                "command_id": command_id,
                **policy_metadata,
            },
            decision,
        )
        response["host_id"] = host_id
        response["command_id"] = command_id
        response["writes_remote"] = profile.writes_remote
        response.update(policy_metadata)
        return response

    def start_ssh_monitored_command(
        self,
        host_id: str,
        command_id: str,
        *,
        autonomy_profile: str = "permissive",
        execution_mode: str = "structured",
    ) -> dict:
        self._require_active_ssh_autonomy_profile(autonomy_profile)
        host, profile = validate_monitored_command_start(
            self.config, host_id, command_id
        )
        policy = authorize_ssh_action_launch(
            autonomy_profile=autonomy_profile,
            execution_mode=execution_mode,
            writes_remote=profile.writes_remote,
            monitored=True,
            chatgpt_approval_granted=True,
        )
        policy_metadata = _ssh_policy_metadata(policy)
        estimated_minutes = max(1, (profile.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=2 if profile.writes_remote else 1,
            risk_level="medium" if profile.writes_remote else "low",
            requires_human=False,
            reason="Opt-in monitored SSH command is approved for durable async execution",
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        response = self._create_and_launch(
            "ssh_monitored_command",
            f"ssh:{host_id}",
            {
                "host_id": host_id,
                "command_id": command_id,
                **policy_metadata,
            },
            decision,
        )
        response["host_id"] = host_id
        response["command_id"] = command_id
        response.update(policy_metadata)
        response["writes_remote"] = profile.writes_remote
        response["watchdog_mode"] = host.watchdog.enforcement_mode
        response["automatic_termination_active"] = bool(
            host.watchdog.enabled
            and host.watchdog.enforcement_mode == "terminate"
            and host.watchdog.allow_automatic_termination
            and profile.watchdog_eligible
        )
        return response

    def start_remote_powershell(
        self,
        host_id: str,
        executable_path: str,
        argv: list[str],
        *,
        working_directory: str = "",
        environment: dict[str, str] | None = None,
        stdin_bytes: bytes | None = None,
        timeout_seconds: int | None = None,
        logical_run_request_id: str = "",
        continuation_context_ref: str = "",
    ) -> dict:
        request = build_remote_powershell_request(
            host_id=host_id,
            executable_path=executable_path,
            argv=argv,
            working_directory=working_directory,
            environment=environment,
            stdin_bytes=stdin_bytes,
            timeout_seconds=timeout_seconds,
        )
        resolve_ssh_connection(resolve_ssh_host(self.config, host_id), self.config.ssh)
        estimated_minutes = max(1, ((timeout_seconds or 60) + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=3,
            risk_level="high",
            requires_human=False,
            reason="Permissive remote PowerShell is approved for durable monitored execution",
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        response = self._create_and_launch(
            "remote_powershell",
            f"ssh:{host_id}",
            {"remote_powershell_request": request},
            decision,
            logical_run_request_id=logical_run_request_id,
            continuation_context_ref=continuation_context_ref,
        )
        response["host_id"] = host_id
        response["request_fingerprint"] = request["request_fingerprint"]
        return response

    def start_ssh_reviewed_script(
        self,
        host_id: str,
        interpreter: str,
        script: str,
        script_sha256: str,
        *,
        arguments: list[str] | None = None,
        timeout_seconds: int = 3600,
        writes_remote: bool = True,
        high_risk: bool = False,
        autonomy_profile: str = "permissive",
        execution_mode: str = "reviewed_script",
    ) -> dict:
        self._require_active_ssh_autonomy_profile(autonomy_profile)
        submitted_script_sha256 = script_sha256
        script, script_sha256, line_endings_normalized = (
            canonicalize_hash_pinned_ssh_script(
                interpreter,
                script,
                script_sha256,
            )
        )
        request = validate_reviewed_ssh_script_request(
            {
                "action": "reviewed_script",
                "host_id": host_id,
                "interpreter": interpreter,
                "arguments": list(arguments or []),
                "script": script,
                "script_sha256": script_sha256,
                "timeout_seconds": timeout_seconds,
                "writes_remote": writes_remote,
                "high_risk": high_risk,
                "autonomy_profile": autonomy_profile,
                "execution_mode": execution_mode,
            }
        )
        host = resolve_ssh_host(self.config, request.host_id)
        resolve_ssh_connection(host, self.config.ssh)
        policy = authorize_ssh_reviewed_script_launch(
            autonomy_profile=request.autonomy_profile,
            execution_mode=request.execution_mode,
            writes_remote=request.writes_remote,
            high_risk=request.high_risk,
            model_approval_granted=True,
        )
        policy_metadata = _ssh_policy_metadata(policy)
        decision = PolicyDecision(
            accepted=True,
            tier=3 if request.high_risk else 2 if request.writes_remote else 1,
            risk_level=(
                "high"
                if request.high_risk
                else "medium"
                if request.writes_remote
                else "low"
            ),
            requires_human=False,
            reason="Hash-pinned reviewed SSH script is approved for remote execution",
            estimated_duration_minutes=max(1, (request.timeout_seconds + 59) // 60),
            recommended_check_after_minutes=min(
                2, max(1, (request.timeout_seconds + 59) // 60)
            ),
        )
        input_data = request.model_dump(mode="python")
        input_data.update(
            {
                "submitted_script_sha256": submitted_script_sha256,
                "line_endings_normalized": line_endings_normalized,
                **policy_metadata,
            }
        )
        response = self._create_and_launch(
            "ssh_reviewed_script",
            f"ssh:{request.host_id}",
            input_data,
            decision,
        )
        response["host_id"] = request.host_id
        response["interpreter"] = request.interpreter
        response["arguments"] = list(request.arguments)
        response["script_sha256"] = request.script_sha256
        response["submitted_script_sha256"] = submitted_script_sha256
        response["line_endings_normalized"] = line_endings_normalized
        response["writes_remote"] = request.writes_remote
        response["high_risk"] = request.high_risk
        response.update(policy_metadata)
        return response

    def start_ssh_root_shell(
        self,
        host_id: str,
        script: str,
        script_sha256: str,
        *,
        timeout_seconds: int = 3600,
        autonomy_profile: str = "permissive",
        execution_mode: str = "root_shell",
    ) -> dict:
        self._require_active_ssh_autonomy_profile(autonomy_profile)
        submitted_script_sha256 = script_sha256
        script, script_sha256, line_endings_normalized = (
            canonicalize_hash_pinned_ssh_script(
                "bash",
                script,
                script_sha256,
            )
        )
        request = validate_root_ssh_shell_request(
            {
                "action": "root_shell",
                "host_id": host_id,
                "script": script,
                "script_sha256": script_sha256,
                "timeout_seconds": timeout_seconds,
                "writes_remote": True,
                "high_risk": True,
                "autonomy_profile": autonomy_profile,
                "execution_mode": execution_mode,
            }
        )
        host = resolve_ssh_host(self.config, request.host_id)
        resolve_ssh_connection(host, self.config.ssh)
        policy = authorize_ssh_root_shell_launch(
            autonomy_profile=request.autonomy_profile,
            execution_mode=request.execution_mode,
        )
        policy_metadata = _ssh_policy_metadata(policy)
        decision = PolicyDecision(
            accepted=True,
            tier=3,
            risk_level="high",
            requires_human=False,
            reason="Permissive hash-pinned root shell is approved for remote execution",
            estimated_duration_minutes=max(1, (request.timeout_seconds + 59) // 60),
            recommended_check_after_minutes=min(
                2, max(1, (request.timeout_seconds + 59) // 60)
            ),
        )
        input_data = request.model_dump(mode="python")
        input_data.update(
            {
                "submitted_script_sha256": submitted_script_sha256,
                "line_endings_normalized": line_endings_normalized,
                **policy_metadata,
            }
        )
        response = self._create_and_launch(
            "ssh_root_shell",
            f"ssh:{request.host_id}",
            input_data,
            decision,
        )
        response["host_id"] = request.host_id
        response["script_sha256"] = request.script_sha256
        response["submitted_script_sha256"] = submitted_script_sha256
        response["line_endings_normalized"] = line_endings_normalized
        response["writes_remote"] = True
        response["high_risk"] = True
        response.update(policy_metadata)
        return response

    def start_ssh_action(
        self,
        host_id: str,
        action: str,
        *,
        target: str = "",
        source: str = "",
        destination: str = "",
        path: str = "",
        deployment_id: str = "",
        command_id: str = "",
        packages: list[str] | None = None,
        executable: str = "",
        args: list[str] | None = None,
        force: bool = False,
        confirmation: str = "",
        autonomy_profile: str = "permissive",
        execution_mode: str = "structured",
    ) -> dict:
        self._require_active_ssh_autonomy_profile(autonomy_profile)
        normalized_packages = list(packages or [])
        normalized_args = list(args or [])
        spec = build_ssh_action(
            self.config,
            host_id,
            action,
            target=target,
            source=source,
            destination=destination,
            path=path,
            deployment_id=deployment_id,
            command_id=command_id,
            packages=normalized_packages,
            executable=executable,
            args=normalized_args,
            force=force,
            confirmation=confirmation,
        )
        policy = authorize_ssh_action_launch(
            autonomy_profile=autonomy_profile,
            execution_mode=execution_mode,
            writes_remote=spec.writes_remote,
            high_risk=spec.high_risk,
            chatgpt_approval_granted=True,
            human_approval_granted=spec.high_risk,
        )
        policy_metadata = _ssh_policy_metadata(policy)
        estimated_minutes = max(1, (spec.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=3 if spec.high_risk else 2,
            risk_level="high" if spec.high_risk else "medium",
            requires_human=False,
            reason=(
                "Explicitly confirmed high-risk SSH action is approved"
                if spec.high_risk
                else "Bounded SSH action is approved for durable execution"
            ),
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        input_data = {
            "host_id": host_id,
            "action": action,
            "target": target,
            "source": source,
            "destination": destination,
            "path": path,
            "deployment_id": deployment_id,
            "command_id": command_id,
            "packages": normalized_packages,
            "executable": executable,
            "args": normalized_args,
            "force": force,
            "confirmation": confirmation,
            **policy_metadata,
        }
        response = self._create_and_launch(
            "ssh_action", f"ssh:{host_id}", input_data, decision
        )
        response["host_id"] = host_id
        response["action"] = action
        response["high_risk"] = spec.high_risk
        response.update(policy_metadata)
        return response

    def start_ssh_transfer(
        self,
        host_id: str,
        direction: str,
        *,
        repo_name: str,
        local_path: str,
        remote_path: str,
        recursive: bool = False,
        overwrite: bool = False,
        confirmation: str = "",
        autonomy_profile: str = "permissive",
        execution_mode: str = "structured",
    ) -> dict:
        self._require_active_ssh_autonomy_profile(autonomy_profile)
        if not self.config.ssh.allow_transfer:
            raise ValueError("SSH transfer capability is disabled by allow_transfer")
        direction = str(direction or "").strip().lower()
        if direction not in {"upload", "download"}:
            raise ValueError("direction must be 'upload' or 'download'")
        if overwrite and confirmation != self.config.ssh.confirmation_token:
            raise ValueError(
                "Overwrite transfer requires the configured SSH confirmation token"
            )
        host = resolve_ssh_host(self.config, host_id)
        validate_remote_path(host, remote_path, sensitive=True)
        repo_root = resolve_repo(self.config, repo_name)
        transfer_manifest: dict[str, object]
        if direction == "upload":
            local = validate_repo_relative_path(repo_root, local_path)
            if not local.exists():
                raise ValueError(f"Local upload path does not exist: {local_path}")
            if local.is_dir() and not recursive:
                raise ValueError("Directory upload requires recursive=true")
            transfer_manifest = build_upload_transfer_manifest(local)
        else:
            requested_name = (
                Path(local_path).name if local_path else Path(remote_path).name
            )
            if not requested_name or requested_name in {".", ".."}:
                requested_name = "downloaded-artifact"
            transfer_manifest = {
                "version": 1,
                "source_kind": "remote",
                "staging_relative_path": f"downloads/{requested_name}",
            }
        policy = authorize_ssh_action_launch(
            autonomy_profile=autonomy_profile,
            execution_mode=execution_mode,
            writes_remote=direction == "upload",
            high_risk=overwrite,
            chatgpt_approval_granted=True,
            human_approval_granted=overwrite,
        )
        policy_metadata = _ssh_policy_metadata(policy)
        decision = PolicyDecision(
            accepted=True,
            tier=3 if overwrite else 2,
            risk_level="high" if overwrite else "medium",
            requires_human=False,
            reason="Bounded SCP transfer is approved for durable execution",
            estimated_duration_minutes=max(
                1, (self.config.ssh.transfer_timeout_seconds + 59) // 60
            ),
            recommended_check_after_minutes=2,
        )
        input_data = {
            "host_id": host_id,
            "direction": direction,
            "local_repo_name": repo_name,
            "local_path": local_path,
            "remote_path": remote_path,
            "recursive": recursive,
            "overwrite": overwrite,
            "confirmation": confirmation,
            "transfer_manifest": transfer_manifest,
            **policy_metadata,
        }
        response = self._create_and_launch(
            "ssh_transfer", f"ssh:{host_id}", input_data, decision
        )
        response["host_id"] = host_id
        response["direction"] = direction
        response.update(policy_metadata)
        return response

    def start_ssh_profile_activation(self, change_id: str) -> dict:
        status = get_ssh_profile_change_status(
            self.config_path,
            self.config.resolve_runs_dir(),
            change_id,
        )
        if status.get("status") != "previewed":
            raise ValueError(
                "SSH profile activation requires a previewed profile change"
            )
        decision = PolicyDecision(
            accepted=True,
            tier=4,
            risk_level="high",
            requires_human=False,
            reason=(
                "Owner-selected SSH profile activation is approved for durable "
                "candidate validation and transactional local configuration apply"
            ),
            estimated_duration_minutes=10,
            recommended_check_after_minutes=2,
        )
        input_data = {
            "change_id": change_id,
            "action": str(status.get("action") or ""),
            "host_id": str(status.get("host_id") or ""),
            "activation_intent": str(status.get("activation_intent") or ""),
            "candidate_config_sha256": str(status.get("candidate_config_sha256") or ""),
        }
        response = self._create_and_launch(
            "ssh_profile_activation",
            "__soma_config__",
            input_data,
            decision,
        )
        response.update(
            {
                "change_id": change_id,
                "host_id": input_data["host_id"],
                "activation_intent": input_data["activation_intent"],
            }
        )
        return response

    def start_ssh_deployment(
        self,
        host_id: str,
        deployment_id: str,
        *,
        confirmation: str,
        autonomy_profile: str = "permissive",
        execution_mode: str = "structured",
    ) -> dict:
        self._require_active_ssh_autonomy_profile(autonomy_profile)
        if not self.config.ssh.allow_deploy:
            raise ValueError("SSH deployment capability is disabled by allow_deploy")
        if confirmation != self.config.ssh.confirmation_token:
            raise ValueError(
                "SSH deployment requires the configured confirmation token"
            )
        host = resolve_ssh_host(self.config, host_id)
        deployment = host.deployment_profiles.get(deployment_id)
        if deployment is None:
            raise ValueError(
                f"Unknown deployment_id: {deployment_id!r}. "
                f"Allowed: {sorted(host.deployment_profiles)}"
            )
        resolve_repo(self.config, deployment.repo_name)
        validate_remote_path(host, deployment.remote_root, sensitive=True)
        policy = authorize_ssh_action_launch(
            autonomy_profile=autonomy_profile,
            execution_mode=execution_mode,
            writes_remote=True,
            high_risk=True,
            chatgpt_approval_granted=True,
            human_approval_granted=True,
        )
        policy_metadata = _ssh_policy_metadata(policy)
        decision = PolicyDecision(
            accepted=True,
            tier=3,
            risk_level="high",
            requires_human=False,
            reason="Confirmed archive-based SSH deployment is approved",
            estimated_duration_minutes=max(
                5, (self.config.ssh.transfer_timeout_seconds + 59) // 60
            ),
            recommended_check_after_minutes=2,
        )
        input_data = {
            "host_id": host_id,
            "deployment_id": deployment_id,
            "confirmation": confirmation,
            **policy_metadata,
        }
        response = self._create_and_launch(
            "ssh_deployment", f"ssh:{host_id}", input_data, decision
        )
        response["host_id"] = host_id
        response["deployment_id"] = deployment_id
        response.update(policy_metadata)
        return response

    def start_cloudflare_action(
        self,
        repo_name: str,
        profile_id: str,
        action: str,
        *,
        resource_id: str = "",
        zone_id: str = "",
        zone_name: str = "",
        payload: dict | None = None,
        confirmation: str = "",
    ) -> dict:
        canonical_repo_name, _ = authorize_cloudflare_profile(
            self.config, repo_name, profile_id
        )
        normalized_payload = dict(payload or {})
        spec = build_cloudflare_action(
            self.config,
            profile_id,
            action,
            resource_id=resource_id,
            payload=normalized_payload,
            confirmation=confirmation,
            zone_id=zone_id,
            zone_name=zone_name,
        )
        estimated_minutes = max(1, (spec.timeout_seconds + 59) // 60)
        decision = PolicyDecision(
            accepted=True,
            tier=3 if spec.high_risk else 2,
            risk_level="high" if spec.high_risk else "medium",
            requires_human=False,
            reason=(
                "Explicitly confirmed high-risk Cloudflare action is approved"
                if spec.high_risk
                else "Bounded Cloudflare action is approved for durable execution"
            ),
            estimated_duration_minutes=estimated_minutes,
            recommended_check_after_minutes=min(2, estimated_minutes),
        )
        input_data = {
            "repo_name": canonical_repo_name,
            "profile_id": profile_id,
            "action": action,
            "resource_id": resource_id,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "payload": normalized_payload,
            "confirmation": confirmation,
        }
        response = self._create_and_launch(
            "cloudflare_action",
            f"cloudflare:{canonical_repo_name}:{profile_id}",
            input_data,
            decision,
        )
        response["repo_name"] = canonical_repo_name
        response["profile_id"] = profile_id
        response["action"] = action
        response["high_risk"] = spec.high_risk
        return response

    @staticmethod
    def _logical_run_request_hash(
        tool: str, repo_name: str, input_data: dict[str, Any]
    ) -> str:
        """Hash only effect-defining normalized inputs, never response controls."""
        effect_input = dict(input_data)
        effect_input.pop("requested_repo_name", None)
        payload = {
            "tool": str(tool),
            "repo_name": str(repo_name),
            "input": effect_input,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _logical_run_replay_response(
        run: dict[str, Any],
        decision: PolicyDecision,
        *,
        repo_name: str,
        requested_repo_name: str,
        logical_run_request_id: str,
        request_hash: str,
        continuation_context_ref: str = "",
    ) -> dict:
        response = decision.to_start_response(
            run_id=str(run["run_id"]), status=str(run["status"])
        )
        response["repo_name"] = repo_name
        if requested_repo_name != repo_name:
            response["requested_repo_name"] = requested_repo_name
        response["logical_run_request_id"] = logical_run_request_id
        response["request_hash"] = request_hash
        if continuation_context_ref:
            response["continuation_context_ref"] = continuation_context_ref
        response["replayed"] = True
        return response

    @staticmethod
    def _logical_run_origin_error_response(
        decision: PolicyDecision,
        *,
        logical_run_request_id: str,
        continuation_context_ref: str,
        error_code: str,
        reason: str,
        existing_run: dict[str, Any] | None = None,
    ) -> dict:
        return {
            "run_id": "" if existing_run is None else str(existing_run.get("run_id") or ""),
            "accepted": False,
            "status": "conflict" if error_code == "continuation_origin_conflict" else "refused",
            "estimated_duration_minutes": 0,
            "recommended_check_after_minutes": 0,
            "risk_level": decision.risk_level,
            "requires_human": False,
            "reason": reason,
            "error_code": error_code,
            "logical_run_request_id": logical_run_request_id,
            "continuation_context_ref": continuation_context_ref,
            "replayed": False,
        }

    @staticmethod
    def _logical_run_conflict_response(
        conflict: RunRequestConflict,
        decision: PolicyDecision,
        *,
        logical_run_request_id: str,
        request_hash: str,
    ) -> dict:
        existing = conflict.run
        return {
            "run_id": str(existing.get("run_id") or ""),
            "accepted": False,
            "status": "conflict",
            "estimated_duration_minutes": 0,
            "recommended_check_after_minutes": 0,
            "risk_level": decision.risk_level,
            "requires_human": False,
            "reason": str(conflict),
            "error_code": "logical_run_request_hash_conflict",
            "logical_run_request_id": logical_run_request_id,
            "existing_request_hash": str(existing.get("request_hash") or ""),
            "submitted_request_hash": request_hash,
            "replayed": False,
        }

    @staticmethod
    def _rebuild_logical_run_input_for_lease(
        run: dict[str, Any], lease_generation: int
    ) -> dict[str, Any]:
        input_data = dict(run.get("input") or {})
        tool = str(run.get("tool") or "")
        run_id = str(run.get("run_id") or "")
        if tool == "executable_profile":
            input_data["staging_manifest"] = build_executable_staging_manifest(
                input_data,
                run_id=run_id,
                lease_generation=lease_generation,
            )
            return input_data
        if tool == "remote_powershell":
            request = input_data.get("remote_powershell_request")
            if not isinstance(request, dict):
                raise ValueError("Remote PowerShell durable request is missing")
            return build_remote_powershell_durable_input(
                request,
                run_id=run_id,
                lease_generation=lease_generation,
            )
        raise ValueError(f"Unsupported logical Run recovery tool: {tool!r}")

    @staticmethod
    def _materialize_logical_run_launch_artifacts(
        run: dict[str, Any], input_data: dict[str, Any]
    ) -> None:
        run_dir = Path(str(run["run_dir"]))
        run_dir.mkdir(parents=True, exist_ok=True)
        artifacts = ArtifactWriter(run_dir)
        if str(run.get("tool") or "") == "executable_profile":
            manifest = input_data.get("staging_manifest")
            if not isinstance(manifest, dict):
                raise ValueError("Executable staging manifest is missing")
            stage_executable_input(run_dir, input_data, dict(manifest))
        artifacts.write_json("input.json", input_data)

    def _create_and_launch_logical_request(
        self,
        tool: str,
        repo_name: str,
        input_data: dict[str, Any],
        decision: PolicyDecision,
        *,
        requested_repo_name: str,
        logical_run_request_id: str,
        continuation_context_ref: str = "",
        reserved_run_id: str | None = None,
    ) -> dict:
        """Atomically admit one keyed single-Run request before worker launch."""
        from .continuations.store import (
            ContinuationClosed,
            ContinuationRequestConflict,
            ContinuationStore,
            EffectOriginConflict,
            StaleContinuationContract,
        )

        logical_id = str(logical_run_request_id or "").strip()
        if not logical_id:
            raise ValueError("logical_run_request_id must not be blank")
        if len(logical_id) > 128:
            raise ValueError("logical_run_request_id must be at most 128 characters")
        context_ref = str(continuation_context_ref or "").strip()
        if len(context_ref) > 128:
            raise ValueError("continuation_context_ref must be at most 128 characters")
        continuation_store = self.continuation_store if context_ref else None
        if tool not in {"executable_profile", "remote_powershell"}:
            raise ValueError(
                f"logical Run request identity is unsupported for tool {tool!r}"
            )

        request_hash = self._logical_run_request_hash(tool, repo_name, input_data)
        run_id = reserved_run_id or make_run_id(tool)
        validate_run_id(run_id)
        lease_token = uuid4().hex

        durable_input = dict(input_data)
        if tool == "remote_powershell":
            request = durable_input.get("remote_powershell_request")
            if not isinstance(request, dict):
                raise ValueError("Remote PowerShell durable request is missing")
            durable_input = build_remote_powershell_durable_input(
                request,
                run_id=run_id,
                lease_generation=1,
            )
        else:
            durable_input["staging_manifest"] = build_executable_staging_manifest(
                durable_input,
                run_id=run_id,
                lease_generation=1,
            )

        repository_lock_required = durable_input.get("repository_lock_required", True)
        if not isinstance(repository_lock_required, bool):
            raise ValueError("repository_lock_required must be boolean")
        if not repository_lock_required and not (
            tool == "executable_profile"
            and isinstance(durable_input.get("hermes_companion"), dict)
        ):
            raise ValueError(
                "Only Hermes companion executable runs may disable the repository lock"
            )

        run_dir = self.config.resolve_runs_dir() / run_id
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = self.store.find_by_logical_request_in_connection(
                conn, logical_id
            )
            if existing is not None:
                if str(existing.get("request_hash") or "") != request_hash:
                    raise RunRequestConflict(existing, request_hash)
                existing_link = ContinuationStore.find_effect_link_in_connection(
                    conn,
                    effect_kind="run",
                    effect_id=str(existing["run_id"]),
                )
                if context_ref:
                    if existing_link is None:
                        raise EffectOriginConflict(
                            f"run {existing['run_id']} was originally unassociated; "
                            "continuation origin cannot be attached after the fact"
                        )
                    if existing_link.contract_revision_id != context_ref:
                        raise EffectOriginConflict(
                            f"run {existing['run_id']} already has continuation origin "
                            f"{existing_link.continuation_id}/"
                            f"{existing_link.contract_revision_id}"
                        )
                elif existing_link is not None:
                    raise EffectOriginConflict(
                        f"run {existing['run_id']} was originally associated with "
                        f"{existing_link.continuation_id}/"
                        f"{existing_link.contract_revision_id}; origin cannot be omitted on replay"
                    )
                conn.commit()
                return self._logical_run_replay_response(
                    existing,
                    decision,
                    repo_name=repo_name,
                    requested_repo_name=requested_repo_name,
                    logical_run_request_id=logical_id,
                    request_hash=request_hash,
                    continuation_context_ref=context_ref,
                )

            if continuation_store is not None:
                continuation_store.require_current_open_context_in_connection(
                    conn, context_ref
                )

            if repository_lock_required:
                acquisition = self.locks.acquire_in_connection(
                    conn,
                    repo_name=repo_name,
                    tool=tool,
                    normalized_input=durable_input,
                    run_id=run_id,
                    owner_pid=os.getpid(),
                    owner_token=lease_token,
                    lease_generation=1,
                )
                if not acquisition.acquired:
                    conn.commit()
                    return {
                        "run_id": "",
                        "accepted": False,
                        "status": "refused",
                        "estimated_duration_minutes": 0,
                        "recommended_check_after_minutes": 0,
                        "risk_level": decision.risk_level,
                        "requires_human": False,
                        "reason": acquisition.reason,
                        "duplicate": acquisition.duplicate,
                        "logical_run_request_id": logical_id,
                        "logical_request_consumed": False,
                    }

            reserved, created = self.store.reserve_run_in_connection(
                conn,
                run_id=run_id,
                repo_name=repo_name,
                tool=tool,
                run_dir=run_dir,
                input_data=durable_input,
                logical_run_request_id=logical_id,
                request_hash=request_hash,
                risk_level=decision.risk_level,
                requires_human=decision.requires_human,
                status="launch_pending",
                worker_lease_token=lease_token,
            )
            if not created:
                conn.commit()
                return self._logical_run_replay_response(
                    reserved,
                    decision,
                    repo_name=repo_name,
                    requested_repo_name=requested_repo_name,
                    logical_run_request_id=logical_id,
                    request_hash=request_hash,
                )
            if repository_lock_required and not self.locks.bind_run_ownership_in_connection(
                conn,
                repo_name=repo_name,
                run_id=run_id,
                owner_token=lease_token,
                lease_generation=1,
            ):
                raise RuntimeError(
                    "Durable run could not bind repository lock ownership"
                )
            if continuation_store is not None:
                continuation_store.insert_effect_link_in_connection(
                    conn,
                    continuation_context_ref=context_ref,
                    effect_kind="run",
                    effect_id=run_id,
                    controller_request_id=logical_id,
                )
            conn.commit()
        except RunRequestConflict as exc:
            conn.rollback()
            return self._logical_run_conflict_response(
                exc,
                decision,
                logical_run_request_id=logical_id,
                request_hash=request_hash,
            )
        except StaleContinuationContract as exc:
            conn.rollback()
            return self._logical_run_origin_error_response(
                decision,
                logical_run_request_id=logical_id,
                continuation_context_ref=context_ref,
                error_code="stale_continuation_contract",
                reason=str(exc),
            )
        except ContinuationClosed as exc:
            conn.rollback()
            return self._logical_run_origin_error_response(
                decision,
                logical_run_request_id=logical_id,
                continuation_context_ref=context_ref,
                error_code="continuation_closed",
                reason=str(exc),
            )
        except (EffectOriginConflict, ContinuationRequestConflict) as exc:
            conn.rollback()
            return self._logical_run_origin_error_response(
                decision,
                logical_run_request_id=logical_id,
                continuation_context_ref=context_ref,
                error_code="continuation_origin_conflict",
                reason=str(exc),
                existing_run=self.store.find_by_logical_request(logical_id),
            )
        except KeyError as exc:
            conn.rollback()
            return self._logical_run_origin_error_response(
                decision,
                logical_run_request_id=logical_id,
                continuation_context_ref=context_ref,
                error_code="continuation_context_not_found",
                reason=str(exc),
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        try:
            accepted_run = self.store.get_run(run_id)
            self._materialize_logical_run_launch_artifacts(
                accepted_run, durable_input
            )
            artifacts = ArtifactWriter(run_dir)
            event = self.store.append_event(
                run_id,
                level="info",
                stage="launch_pending",
                message="Durable worker launch intent recorded",
                data={
                    "tool": tool,
                    "logical_run_request_id": logical_id,
                },
            )
            artifacts.append_event(event)
            launch_intent = self.store.get_run(run_id)
            process = self._spawn_worker(run_id, lease_token)
            launcher_identity = capture_launch_identity(process)
            launched = self.store.record_worker_launch(
                run_id,
                process.pid,
                launcher_identity=launcher_identity,
                expected_state_version=int(launch_intent["state_version"]),
                expected_lease_token=lease_token,
                expected_lease_generation=int(launch_intent["lease_generation"]),
            )
            current = launched or self.store.get_run(run_id)
            if not (
                str(current.get("worker_lease_token") or "") == lease_token
                and int(current.get("lease_generation") or 1) == 1
                and current["status"] in {"queued", "running"}
            ):
                require_identity_scoped_cleanup(
                    process.pid, launcher_identity, process=process
                )
                raise RuntimeError("Initial worker launch lost durable lease ownership")
            if repository_lock_required:
                self.locks.heartbeat(repo_name, run_id, lease_token, 1)
            event = self.store.append_event(
                run_id,
                level="info",
                stage="worker",
                message="Worker launcher process started",
                data={"launcher_pid": process.pid},
            )
            artifacts.append_event(event)
        except Exception as exc:
            reason = f"Worker launch failed after durable acceptance: {exc}"
            containment_uncertain = (
                isinstance(exc, LaunchIdentityUnavailable)
                and not exc.containment.terminal_containment_proven
            ) or isinstance(exc, ProcessContainmentUncertain)
            current = self.store.get_run(run_id)
            if containment_uncertain:
                containment = (
                    exc.containment.to_dict()
                    if isinstance(exc, LaunchIdentityUnavailable)
                    else exc.report
                )
                pending = self.store.mark_recovery_pending(
                    run_id,
                    reason,
                    expected_statuses=(str(current["status"]),),
                    expected_state_version=int(current["state_version"]),
                    expected_lease_token=str(current.get("worker_lease_token") or ""),
                    expected_lease_generation=int(
                        current.get("lease_generation") or 1
                    ),
                    expected_heartbeat_at=current.get("heartbeat_at"),
                )
                if pending is not None:
                    event = self.store.append_event(
                        run_id,
                        level="error",
                        stage="recovery_pending",
                        message=reason,
                        data={"containment": containment},
                        update_run_metadata=False,
                    )
                    if run_dir.exists():
                        ArtifactWriter(run_dir).append_event(event)
                return {
                    "run_id": run_id,
                    "accepted": False,
                    "status": "recovery_pending",
                    "estimated_duration_minutes": 0,
                    "recommended_check_after_minutes": 0,
                    "risk_level": decision.risk_level,
                    "requires_human": False,
                    "reason": reason,
                    "logical_run_request_id": logical_id,
                    "request_hash": request_hash,
                    "replayed": False,
                }

            failed = self.store.fail_infrastructure(
                run_id,
                reason,
                expected_statuses=(str(current["status"]),),
                expected_state_version=int(current["state_version"]),
                expected_lease_token=str(current.get("worker_lease_token") or ""),
                expected_lease_generation=int(current.get("lease_generation") or 1),
                expected_heartbeat_at=current.get("heartbeat_at"),
            )
            if failed is not None:
                publication = publish_run_result(self.store, run_id)
                if not publication["ok"]:
                    self._append_recovery_event(
                        current,
                        level="error",
                        message="Canonical terminal result publication failed",
                        data={"error": publication["error"]},
                    )
                event = self.store.append_event(
                    run_id,
                    level="error",
                    stage="launch_failed",
                    message=reason,
                    data={},
                    update_run_metadata=False,
                )
                if run_dir.exists():
                    ArtifactWriter(run_dir).append_event(event)
                if repository_lock_required:
                    self.locks.release(
                        repo_name,
                        run_id,
                        str(current.get("worker_lease_token") or ""),
                        int(current.get("lease_generation") or 1),
                    )
            return {
                "run_id": run_id,
                "accepted": False,
                "status": "failed",
                "estimated_duration_minutes": 0,
                "recommended_check_after_minutes": 0,
                "risk_level": decision.risk_level,
                "requires_human": False,
                "reason": reason,
                "logical_run_request_id": logical_id,
                "request_hash": request_hash,
                "replayed": False,
            }

        response = decision.to_start_response(run_id=run_id, status="queued")
        response["repo_name"] = repo_name
        if requested_repo_name != repo_name:
            response["requested_repo_name"] = requested_repo_name
        response["logical_run_request_id"] = logical_id
        response["request_hash"] = request_hash
        if context_ref:
            response["continuation_context_ref"] = context_ref
        response["replayed"] = False
        return response

    def _create_and_launch(
        self,
        tool: str,
        repo_name: str,
        input_data: dict,
        decision,
        *,
        reserved_run_id: str | None = None,
        logical_run_request_id: str = "",
        continuation_context_ref: str = "",
    ) -> dict:
        if tool in LEGACY_READ_ONLY_TOOLS:
            raise ValueError(
                f"Run tool '{tool}' is a legacy read-only type: Soma no "
                "longer executes Codex and cannot create new instances. "
                "Generate an external-coder handoff instead."
            )
        requested_repo_name = repo_name
        input_data = dict(input_data)
        if not (
            repo_name == "__soma_config__"
            or repo_name.startswith(("ssh:", "cloudflare:"))
        ):
            resolve_repo(self.config, repo_name)
            canonical_repo_name, _ = resolve_repo_config(self.config, repo_name)
            repo_name = canonical_repo_name
            if "repo_name" in input_data:
                input_data["repo_name"] = canonical_repo_name
            input_data["requested_repo_name"] = requested_repo_name

        if self.config_path is None:
            return {
                "run_id": "",
                "accepted": False,
                "status": "refused",
                "estimated_duration_minutes": 0,
                "recommended_check_after_minutes": 0,
                "risk_level": "high",
                "requires_human": False,
                "reason": "Async jobs require a config file path",
            }

        context_ref = str(continuation_context_ref or "").strip()
        if context_ref and not logical_run_request_id:
            return self._logical_run_origin_error_response(
                decision,
                logical_run_request_id="",
                continuation_context_ref=context_ref,
                error_code="continuation_context_requires_logical_run_request_id",
                reason=(
                    "continuation_context_ref requires logical_run_request_id so Run "
                    "origin replay remains immutable and recoverable"
                ),
            )
        if logical_run_request_id:
            return self._create_and_launch_logical_request(
                tool,
                repo_name,
                input_data,
                decision,
                requested_repo_name=requested_repo_name,
                logical_run_request_id=logical_run_request_id,
                continuation_context_ref=context_ref,
                reserved_run_id=reserved_run_id,
            )

        run_id = reserved_run_id or make_run_id(tool)
        validate_run_id(run_id)
        lease_token = uuid4().hex
        if tool == "remote_powershell":
            request = input_data.get("remote_powershell_request")
            if not isinstance(request, dict):
                raise ValueError("Remote PowerShell durable request is missing")
            input_data = build_remote_powershell_durable_input(
                request,
                run_id=run_id,
                lease_generation=1,
            )
        elif tool == "executable_profile":
            input_data["staging_manifest"] = build_executable_staging_manifest(
                input_data,
                run_id=run_id,
                lease_generation=1,
            )
        elif tool in {"ssh_reviewed_script", "ssh_monitored_command"}:
            input_data["staging_manifest"] = build_ssh_staging_manifest(
                tool=tool,
                run_id=run_id,
                lease_generation=1,
                script=str(input_data.get("script") or "")
                if tool == "ssh_reviewed_script"
                else None,
            )
            if tool == "ssh_monitored_command":
                _, monitored_profile = validate_monitored_command_start(
                    self.config,
                    str(input_data["host_id"]),
                    str(input_data["command_id"]),
                )
                input_data["remote_controller_state"] = (
                    build_remote_controller_state_contract(
                        run_id=run_id,
                        host_id=str(input_data["host_id"]),
                        command_id=str(input_data["command_id"]),
                        lease_generation=1,
                        remote_argv=list(monitored_profile.argv),
                        timeout_seconds=monitored_profile.timeout_seconds,
                    )
                )
        repository_lock_required = input_data.get("repository_lock_required", True)
        if not isinstance(repository_lock_required, bool):
            raise ValueError("repository_lock_required must be boolean")
        if not repository_lock_required and not (
            tool == "executable_profile"
            and isinstance(input_data.get("hermes_companion"), dict)
        ):
            raise ValueError(
                "Only Hermes companion executable runs may disable the repository lock"
            )
        if repository_lock_required:
            acquisition = self.locks.acquire(
                repo_name=repo_name,
                tool=tool,
                normalized_input=input_data,
                run_id=run_id,
                owner_pid=os.getpid(),
                owner_token=lease_token,
                lease_generation=1,
            )
            if not acquisition.acquired:
                return {
                    "run_id": "",
                    "accepted": False,
                    "status": "refused",
                    "estimated_duration_minutes": 0,
                    "recommended_check_after_minutes": 0,
                    "risk_level": decision.risk_level,
                    "requires_human": False,
                    "reason": acquisition.reason,
                    "duplicate": acquisition.duplicate,
                }
        run_dir = self.config.resolve_runs_dir() / run_id
        run_created = False
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            artifacts = ArtifactWriter(run_dir)
            if tool == "executable_profile":
                stage_executable_input(
                    run_dir,
                    input_data,
                    dict(input_data["staging_manifest"]),
                )
            elif tool in {"ssh_reviewed_script", "ssh_monitored_command"}:
                stage_ssh_inputs(
                    run_dir,
                    script=str(input_data.get("script") or "")
                    if tool == "ssh_reviewed_script"
                    else None,
                    manifest=dict(input_data["staging_manifest"]),
                )
            artifact_input = dict(input_data)
            if (
                tool in {"ssh_reviewed_script", "ssh_root_shell"}
                and "script" in artifact_input
            ):
                artifact_input["script"] = "[REDACTED]"
            artifacts.write_json("input.json", artifact_input)
            self.store.create_run(
                run_id=run_id,
                repo_name=repo_name,
                tool=tool,
                run_dir=run_dir,
                input_data=input_data,
                risk_level=decision.risk_level,
                requires_human=decision.requires_human,
                status="launch_pending",
                worker_lease_token=lease_token,
            )
            run_created = True
            if repository_lock_required and not self.locks.bind_run_ownership(
                repo_name,
                run_id,
                lease_token,
                1,
            ):
                raise RuntimeError(
                    "Durable run could not bind repository lock ownership"
                )
            event = self.store.append_event(
                run_id,
                level="info",
                stage="launch_pending",
                message="Durable worker launch intent recorded",
                data={"tool": tool},
            )
            artifacts.append_event(event)
            launch_intent = self.store.get_run(run_id)
            process = self._spawn_worker(run_id, lease_token)
            launcher_identity = capture_launch_identity(process)
            launched = self.store.record_worker_launch(
                run_id,
                process.pid,
                launcher_identity=launcher_identity,
                expected_state_version=int(launch_intent["state_version"]),
                expected_lease_token=lease_token,
                expected_lease_generation=int(launch_intent["lease_generation"]),
            )
            current = launched or self.store.get_run(run_id)
            if not (
                str(current.get("worker_lease_token") or "") == lease_token
                and int(current.get("lease_generation") or 1) == 1
                and current["status"] in {"queued", "running"}
            ):
                require_identity_scoped_cleanup(
                    process.pid, launcher_identity, process=process
                )
                raise RuntimeError("Initial worker launch lost durable lease ownership")
            if repository_lock_required:
                self.locks.heartbeat(repo_name, run_id, lease_token, 1)
            event = self.store.append_event(
                run_id,
                level="info",
                stage="worker",
                message="Worker launcher process started",
                data={"launcher_pid": process.pid},
            )
            artifacts.append_event(event)
        except Exception as exc:
            reason = f"Worker launch failed after durable acceptance: {exc}"
            containment_uncertain = (
                isinstance(exc, LaunchIdentityUnavailable)
                and not exc.containment.terminal_containment_proven
            ) or isinstance(exc, ProcessContainmentUncertain)
            if run_created:
                current = self.store.get_run(run_id)
                if containment_uncertain:
                    containment = (
                        exc.containment.to_dict()
                        if isinstance(exc, LaunchIdentityUnavailable)
                        else exc.report
                    )
                    pending = self.store.mark_recovery_pending(
                        run_id,
                        reason,
                        expected_statuses=(str(current["status"]),),
                        expected_state_version=int(current["state_version"]),
                        expected_lease_token=str(
                            current.get("worker_lease_token") or ""
                        ),
                        expected_lease_generation=int(
                            current.get("lease_generation") or 1
                        ),
                        expected_heartbeat_at=current.get("heartbeat_at"),
                    )
                    if pending is not None:
                        event = self.store.append_event(
                            run_id,
                            level="error",
                            stage="recovery_pending",
                            message=reason,
                            data={"containment": containment},
                            update_run_metadata=False,
                        )
                        ArtifactWriter(run_dir).append_event(event)
                    return {
                        "run_id": run_id,
                        "accepted": False,
                        "status": "recovery_pending",
                        "estimated_duration_minutes": 0,
                        "recommended_check_after_minutes": 0,
                        "risk_level": decision.risk_level,
                        "requires_human": False,
                        "reason": reason,
                    }
                failed = self.store.fail_infrastructure(
                    run_id,
                    reason,
                    expected_statuses=(str(current["status"]),),
                    expected_state_version=int(current["state_version"]),
                    expected_lease_token=str(current.get("worker_lease_token") or ""),
                    expected_lease_generation=int(current.get("lease_generation") or 1),
                    expected_heartbeat_at=current.get("heartbeat_at"),
                )
                if failed is not None:
                    publication = publish_run_result(self.store, run_id)
                    if not publication["ok"]:
                        self._append_recovery_event(
                            current,
                            level="error",
                            message="Canonical terminal result publication failed",
                            data={"error": publication["error"]},
                        )
                    event = self.store.append_event(
                        run_id,
                        level="error",
                        stage="launch_failed",
                        message=reason,
                        data={},
                        update_run_metadata=False,
                    )
                    ArtifactWriter(run_dir).append_event(event)
                    if repository_lock_required:
                        self.locks.release(
                            repo_name,
                            run_id,
                            str(current.get("worker_lease_token") or ""),
                            int(current.get("lease_generation") or 1),
                        )
            elif repository_lock_required:
                self.locks.release(repo_name, run_id, lease_token, 1)
            return {
                "run_id": run_id if run_created else "",
                "accepted": False,
                "status": "failed",
                "estimated_duration_minutes": 0,
                "recommended_check_after_minutes": 0,
                "risk_level": decision.risk_level,
                "requires_human": False,
                "reason": reason,
            }
        response = decision.to_start_response(run_id=run_id, status="queued")
        response["repo_name"] = repo_name
        if requested_repo_name != repo_name:
            response["requested_repo_name"] = requested_repo_name
        return response

    def _start_validated_path_command(
        self,
        repo_name: str,
        *,
        command_id: str,
        normalized_target: str,
        timeout_seconds: int,
        reason: str,
    ) -> dict:
        if int(timeout_seconds) < 1 or int(timeout_seconds) > 604_800:
            raise ValueError("validator timeout_seconds must be between 1 and 604800")
        decision = PolicyDecision(
            accepted=True,
            tier=1,
            risk_level="low",
            requires_human=False,
            reason=reason,
            estimated_duration_minutes=max(1, (timeout_seconds + 59) // 60),
            recommended_check_after_minutes=min(
                2, max(1, (timeout_seconds + 59) // 60)
            ),
        )
        response = self._create_and_launch(
            "project_command",
            repo_name,
            {
                "repo_name": repo_name,
                "command_id": command_id,
                "path": normalized_target,
                "timeout_seconds": int(timeout_seconds),
            },
            decision,
        )
        response.setdefault("repo_name", repo_name)
        response["command_id"] = command_id
        response["path"] = normalized_target
        return response

    @staticmethod
    def _public_run(run: dict) -> dict:
        public = dict(run)
        public.pop("worker_lease_token", None)
        # V3-1A-CANCELLATION-CLOSURE-1 3.8: process-start identities are
        # ownership proofs, not controller-facing state. Presence is already
        # exposed through the control projection's worker_identity_present.
        public.pop("launcher_identity", None)
        public.pop("child_identity", None)
        if public.get("tool") in {"ssh_reviewed_script", "ssh_root_shell"}:
            input_data = dict(public.get("input") or {})
            if "script" in input_data:
                input_data["script"] = "[REDACTED]"
            public["input"] = input_data
        return redact_payload(public)

    def _legacy_run(self, run_id: str) -> dict:
        try:
            legacy = load_legacy_filesystem_run(
                self.config.resolve_runs_dir(), run_id
            )
        except ValueError as exc:
            raise KeyError(f"Legacy run evidence is unavailable: {exc}") from exc
        if legacy is None:
            raise KeyError(f"Run not found: {run_id}")
        return legacy

    def _get_run_or_legacy(self, run_id: str) -> dict:
        try:
            return self.store.get_run(run_id)
        except KeyError:
            return self._legacy_run(run_id)

    def get_status_payload(self, run_id: str) -> dict:
        try:
            run = self._get_run_or_legacy(run_id)
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        return self._public_run(run)

    def get_status(self, run_id: str) -> dict:
        reference = decode_run_reference(run_id)
        actual_run_id = reference.resource_id if reference else run_id
        if reference:
            return chunk_payload(
                "status",
                actual_run_id,
                lambda: self.get_status_payload(actual_run_id),
                reference.cursor,
            )
        return redact_and_truncate(self.get_status_payload(actual_run_id))

    def get_events(
        self, run_id: str, limit: int = 50, after_id: int | None = None
    ) -> list[dict]:
        try:
            return redact_and_truncate(self.store.get_events(run_id, limit, after_id))
        except KeyError:
            self._legacy_run(run_id)
            return []

    def get_event_page(
        self,
        run_id: str,
        limit: int = 20,
        after_id: int | None = None,
        cursor: str | None = None,
    ) -> dict:
        requested_limit = limit
        legacy = False
        try:
            page = self.store.get_event_page(
                run_id,
                limit=limit,
                after_id=after_id,
                cursor=cursor,
            )
        except KeyError:
            self._legacy_run(run_id)
            if cursor:
                raise ValueError("Legacy filesystem runs have no event cursor")
            page = {
                "events": [],
                "limit": max(1, min(int(limit), 500)),
                "has_more": False,
                "next_after_id": max(0, int(after_id or 0)),
                "next_cursor": "",
                "ordering": "id ASC",
                "cursor_expires_at_utc": "",
            }
            legacy = True
        page["run_id"] = run_id
        if not page["events"]:
            response = _build_run_event_response(
                page,
                requested_limit=requested_limit,
                byte_limited=False,
            )
            if legacy:
                response.update(
                    {
                        "legacy_filesystem_only": True,
                        "database_record_present": False,
                        "events_available": False,
                    }
                )
                response = _finalize_compact_projection(
                    response, DEFAULT_PUBLIC_BYTE_BUDGETS.events
                )
            return response

        projected_events = [_project_run_event(event) for event in page["events"]]
        for returned_count in range(len(page["events"]), 0, -1):
            candidate = (
                page
                if returned_count == len(page["events"])
                else self.store.truncate_event_page(page, returned_count)
            )
            try:
                return _build_run_event_response(
                    candidate,
                    requested_limit=requested_limit,
                    byte_limited=returned_count < len(page["events"]),
                    projected_events=projected_events[:returned_count],
                )
            except ValueError:
                continue
        raise ValueError("Run event page cannot fit its public byte budget")

    def _lifecycle_observation(self, run_id: str) -> dict:
        try:
            run, worker_identity = self.store.get_run_control_observation(run_id)
        except KeyError:
            run = self._legacy_run(run_id)
            worker_identity = ""
        launcher_pid = int(run.get("launcher_pid") or 0)
        worker_pid = int(run.get("worker_pid") or 0)
        child_pid = int(run.get("pid") or 0)
        control = dict(run)
        control.update(
            {
                "launcher_pid": launcher_pid,
                "launcher_running": process_is_running(launcher_pid),
                "worker_pid": worker_pid,
                "worker_identity_present": bool(worker_identity),
                "worker_running": process_matches_identity(worker_pid, worker_identity),
                "child_pid": child_pid,
                "child_running": process_is_running(child_pid),
                "lock": self.locks.find_lock(run["repo_name"], run_id) or {},
                "details_available": {
                    "input": True,
                    "output": True,
                    "result": True,
                    "terminal": True,
                    "events": not bool(run.get("legacy_filesystem_only")),
                },
            }
        )
        return control

    def get_lifecycle_status(self, run_id: str) -> dict:
        """Return only the bounded lifecycle projection used for routine polling."""
        try:
            observation = self._lifecycle_observation(run_id)
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        return _build_run_control_response(observation, operation="status")

    def get_control_status(
        self, run_id: str, if_state_version: int | None = None
    ) -> dict:
        try:
            if if_state_version is not None:
                try:
                    snapshot = self.store.get_run_control_snapshot(run_id)
                except KeyError:
                    snapshot = self._legacy_run(run_id)
                state_version = int(snapshot.get("state_version") or 0)
                if int(if_state_version) == state_version:
                    return _build_unchanged_control_response(run_id, state_version)
            observation = self._lifecycle_observation(run_id)
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        return _build_run_control_response(observation, operation="control")

    @staticmethod
    def _input_field_metadata(value: Any) -> dict[str, Any]:
        encoded = json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
        ).encode("ascii")
        return {
            "type": type(value).__name__,
            "bytes": len(encoded),
            "sha256": sha256(encoded).hexdigest(),
        }

    def get_input(
        self,
        run_id: str,
        *,
        view: str = "compact",
        cursor: str = "",
        response_budget_bytes: int = 12 * 1024,
    ) -> dict:
        """Return bounded metadata or a cursor-paged redacted input representation."""
        if view not in {"compact", "full"}:
            raise ValueError("input view must be compact or full")
        if response_budget_bytes < 1024 or response_budget_bytes > 12 * 1024:
            raise ValueError(
                "input response_budget_bytes must be between 1024 and 12288"
            )
        try:
            try:
                snapshot = self.store.get_run_input_snapshot(run_id)
            except KeyError:
                legacy = self._legacy_run(run_id)
                snapshot = {
                    **legacy,
                    "input_json": legacy["input_json"],
                    "input": legacy["input"],
                }
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        authoritative_bytes = snapshot["input_json"].encode("utf-8")
        public_input = redact_payload(snapshot["input"])
        public_bytes = json.dumps(
            public_input,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("ascii")
        metadata = {
            "ok": True,
            "operation": "input",
            "run_id": snapshot["run_id"],
            "repo_name": snapshot["repo_name"],
            "tool": snapshot["tool"],
            "status": snapshot["status"],
            "state_version": snapshot["state_version"],
            "authoritative_input_bytes": len(authoritative_bytes),
            "authoritative_input_sha256": sha256(authoritative_bytes).hexdigest(),
            "public_input_bytes": len(public_bytes),
            "public_input_sha256": sha256(public_bytes).hexdigest(),
            "secrets_redacted": public_input != snapshot["input"],
            "fields": {
                str(key): self._input_field_metadata(value)
                for key, value in sorted(snapshot["input"].items())
            },
            "authoritative_storage": (
                snapshot.get("authoritative_storage", "runs/soma.sqlite3")
                + ("/input.json" if snapshot.get("legacy_filesystem_only") else ":input_json")
            ),
            "complete_authoritative_input_preserved": True,
            "legacy_filesystem_only": bool(snapshot.get("legacy_filesystem_only")),
            "database_record_present": not bool(snapshot.get("legacy_filesystem_only")),
            "error": "",
        }
        if view == "full" or cursor:
            return chunk_payload(
                "input",
                run_id,
                {**metadata, "input": public_input},
                cursor,
            )
        compact = {
            **metadata,
            "view": "compact",
            "truncated": False,
            "has_more": bool(public_input),
            "full_retrieval": {
                "tool": "run_query",
                "request": {"operation": "input", "run_id": run_id, "view": "full"},
            },
            "response_budget_bytes": response_budget_bytes,
        }
        while (
            len(_canonical_public_json_bytes(compact)) > response_budget_bytes
            and compact["fields"]
        ):
            compact["fields"].pop(next(reversed(compact["fields"])))
            compact["truncated"] = True
        compact["response_bytes"] = len(_canonical_public_json_bytes(compact))
        return compact

    def get_output(
        self,
        run_id: str,
        stream: str = "combined",
        tail_bytes: int = 20000,
        response_budget_bytes: int | None = None,
    ) -> dict:
        validate_run_id(run_id)
        normalized_stream = str(stream or "combined").strip().lower()
        if normalized_stream not in {"stdout", "stderr", "combined"}:
            raise ValueError("stream must be stdout, stderr, or combined")
        bounded_tail = max(1, min(int(tail_bytes), 200000))
        run = self._get_run_or_legacy(run_id)
        artifacts = resolve_output_artifacts(run, self.config.resolve_runs_dir())
        selected = (
            [normalized_stream]
            if normalized_stream in {"stdout", "stderr"}
            else ["stdout", "stderr"]
        )
        streams = {
            name: read_redacted_output_tail(
                artifacts[name], run_id=run_id, tail_bytes=bounded_tail
            )
            for name in selected
        }
        response = {
            "ok": True,
            "run_id": run_id,
            "status": run["status"],
            "stream": normalized_stream,
            "tail_bytes": bounded_tail,
            "streams": streams,
            "legacy_filesystem_only": bool(run.get("legacy_filesystem_only")),
            "database_record_present": not bool(run.get("legacy_filesystem_only")),
            "error": "",
        }
        if response_budget_bytes is not None:
            _fit_output_response(response, response_budget_bytes)
        return response

    def list_operation_locks(
        self, repo_name: str | None = None, *, include_stale: bool = True
    ) -> list[dict]:
        normalized_name = repo_name or None
        if normalized_name and not normalized_name.startswith(
            ("ssh:", "cloudflare:", "__")
        ):
            normalized_name, _ = resolve_repo_config(self.config, normalized_name)
        return redact_and_truncate(
            self.locks.list_locks(normalized_name, include_stale=include_stale)
        )

    def get_terminal_result(self, run_id: str) -> dict:
        """Return the bounded durable terminal projection without decoding full JSON."""
        try:
            try:
                snapshot = self.store.get_public_result_snapshot(run_id)
            except KeyError:
                legacy = self._legacy_run(run_id)
                projection = build_public_result_projection(
                    legacy,
                    dict(legacy.get("result") or {}),
                    authoritative_result_sha256(str(legacy["result_json"])),
                )
                projection["legacy_filesystem_only"] = True
                projection["database_record_present"] = False
                projection["evidence"] = {
                    **dict(projection.get("evidence") or {}),
                    "authoritative_storage": legacy["authoritative_storage"] + "/result.json",
                }
                projection["payload_bytes"] = 0
                for _ in range(4):
                    measured = len(_canonical_public_json_bytes(projection))
                    if projection["payload_bytes"] == measured:
                        break
                    projection["payload_bytes"] = measured
                if len(_canonical_public_json_bytes(projection)) > DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result:
                    raise ValueError("Legacy terminal result exceeds its public byte budget")
                return projection
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        if snapshot["status"] not in TERMINAL_STATUSES:
            return build_pending_public_result(snapshot)

        stored = snapshot.get("public_result") or {}
        if (
            stored
            and snapshot.get("public_result_schema_version")
            == PUBLIC_RESULT_SCHEMA_VERSION
            and snapshot.get("public_result_status")
            in {PUBLIC_RESULT_STATUS_READY, PUBLIC_RESULT_STATUS_FALLBACK}
            and snapshot.get("public_result_source_sha256")
        ):
            return dict(stored)

        try:
            return materialize_public_result(self.store, run_id)
        except Exception as exc:
            return build_public_result_fallback(
                snapshot,
                str(snapshot.get("public_result_source_sha256") or ""),
                f"{type(exc).__name__}: {exc}",
            )

    def get_result_payload(self, run_id: str) -> dict:
        try:
            run = self._get_run_or_legacy(run_id)
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        result = dict(run.get("result") or {})
        if result:
            if run.get("legacy_filesystem_only"):
                result.update({"legacy_filesystem_only": True, "database_record_present": False})
            return result
        return {
            "run_id": run["run_id"],
            "repo_name": run["repo_name"],
            "tool": run["tool"],
            "status": run["status"],
            "exit_code": run["exit_code"],
            "stdout": "",
            "stderr": "",
            "process_success": None,
            "classification": "pending",
            "started_at": run["started_at"],
            "ended_at": run["ended_at"],
            "duration_seconds": run["duration_seconds"],
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": "",
            "summary": run["summary"],
            "remaining_risks": [],
            "error": run["error"],
            "safety_failure": run["safety_failure"],
            "cancelled": False,
            "timed_out": False,
        }

    def get_result(self, run_id: str) -> dict:
        # Ordinary run IDs are overwhelmingly the hot path. Avoid reference
        # decoding and the extra payload-routing layer unless the opaque prefix
        # is actually present; this retains identical lookup/redaction behavior.
        if not run_id.startswith(RUN_REFERENCE_PREFIX):
            try:
                run = self._get_run_or_legacy(run_id)
            except (ValueError, KeyError) as exc:
                return self._run_lookup_error(run_id, exc)
            result = dict(run.get("result") or {})
            if result:
                if run.get("legacy_filesystem_only"):
                    result.update({"legacy_filesystem_only": True, "database_record_present": False})
                return redact_and_truncate(result)
            return redact_and_truncate(self.get_result_payload(run_id))

        reference = decode_run_reference(run_id)
        if reference is None:  # Defensive: prefix and decoder must agree.
            raise RuntimeError("Run-query reference prefix was not decoded")
        return chunk_payload(
            "result",
            reference.resource_id,
            lambda: self.get_result_payload(reference.resource_id),
            reference.cursor,
        )

    @staticmethod
    def _run_lookup_error(run_id: str, exc: Exception) -> dict:
        malformed = isinstance(exc, ValueError)
        return {
            "ok": False,
            "run_id": run_id,
            "status": "invalid" if malformed else "not_found",
            "classification": "lookup_error",
            "error_code": "invalid_run_id" if malformed else "run_not_found",
            "error": str(exc),
            "result_available": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }

    @staticmethod
    def _cancellation_result(
        run: dict, ended_at: str, error: str, progress: dict
    ) -> dict:
        return {
            "run_id": run["run_id"],
            "repo_name": run["repo_name"],
            "tool": run["tool"],
            "status": "cancelled",
            "classification": "cancelled",
            "process_success": None,
            "exit_code": run.get("exit_code"),
            "stdout": "",
            "stderr": "",
            "started_at": run.get("started_at"),
            "ended_at": ended_at,
            "duration_seconds": run.get("duration_seconds"),
            "summary": error,
            "error": error,
            "cancelled": True,
            "cancellation": progress,
            "timed_out": False,
            "safety_failure": False,
            "changed_files": [],
            "tests_run": [],
            "remaining_risks": [],
        }

    def get_run_summary(self, run_id: str) -> dict:
        try:
            try:
                run = self.store.get_run_summary(run_id)
            except KeyError:
                run = self._legacy_run(run_id)
        except (ValueError, KeyError) as exc:
            lookup = self._run_lookup_error(run_id, exc)
            return _finalize_compact_projection(
                {
                    "ok": False,
                    "operation": "summary",
                    "run_id": run_id,
                    "status": lookup["status"],
                    "error_code": lookup["error_code"],
                    "error": redact_secret_values(str(exc)),
                    "authoritative_operation": "status",
                    **_compact_projection_metadata(
                        DEFAULT_PUBLIC_BYTE_BUDGETS.run_summary
                    ),
                },
                DEFAULT_PUBLIC_BYTE_BUDGETS.run_summary,
            )
        return _build_run_summary_response(run)

    def list_run_summaries(
        self,
        repo_name: str | None = None,
        status: str | None = None,
        tool: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
    ) -> dict:
        canonical_repo_name = None
        if repo_name:
            canonical_repo_name, _ = resolve_repo_config(self.config, repo_name)
        requested_limit = max(1, min(int(limit), RUN_SUMMARY_MAX_LIMIT))
        byte_budget = DEFAULT_PUBLIC_BYTE_BUDGETS.run_list
        page = self.store.list_run_summaries(
            repo_name=canonical_repo_name or repo_name or None,
            status=status or None,
            tool=tool or None,
            limit=requested_limit,
            cursor=cursor or None,
            byte_budget=byte_budget,
        )
        if not page["runs"]:
            return _build_run_summary_list_response(
                page,
                requested_limit=requested_limit,
                byte_limited=False,
            )

        projected_runs = [
            _project_run_summary(
                run,
                text_limits=RUN_SUMMARY_LIST_TEXT_BYTE_LIMITS,
            )
            for run in page["runs"]
        ]
        for returned_count in range(len(page["runs"]), 0, -1):
            candidate = (
                page
                if returned_count == len(page["runs"])
                else self.store.truncate_run_summary_page(
                    page,
                    returned_count,
                    repo_name=canonical_repo_name or repo_name or None,
                    status=status or None,
                    tool=tool or None,
                    source_cursor=cursor or None,
                    byte_budget=byte_budget,
                )
            )
            try:
                return _build_run_summary_list_response(
                    candidate,
                    requested_limit=requested_limit,
                    byte_limited=returned_count < len(page["runs"]),
                    projected_runs=projected_runs[:returned_count],
                )
            except ValueError:
                continue
        raise ValueError("A compact run-list item cannot fit the public byte budget")

    def list_runs_payload(
        self, repo_name: str | None = None, status: str | None = None, limit: int = 20
    ) -> list[dict]:
        canonical_repo_name = None
        if repo_name:
            canonical_repo_name, _ = resolve_repo_config(self.config, repo_name)
        runs = self.store.list_runs(
            repo_name=canonical_repo_name or repo_name or None,
            status=status or None,
            limit=limit,
        )
        return [self._public_run(run) for run in runs]

    def list_runs(
        self, repo_name: str | None = None, status: str | None = None, limit: int = 20
    ) -> list[dict]:
        reference = decode_list_reference(repo_name)
        actual_repo_name = reference.resource_id if reference else repo_name
        if reference:
            transported = chunk_payload(
                "list",
                list_resource_id(actual_repo_name or "", status or "", limit),
                lambda: self.list_runs_payload(
                    repo_name=actual_repo_name or None,
                    status=status,
                    limit=limit,
                ),
                reference.cursor,
            )
            return transported if isinstance(transported, list) else [transported]
        return redact_and_truncate(
            self.list_runs_payload(
                repo_name=actual_repo_name or None,
                status=status,
                limit=limit,
            )
        )

    def latest_result(
        self, repo_name: str | None = None, tool: str | None = None
    ) -> dict:
        canonical_repo_name = None
        if repo_name:
            canonical_repo_name, _ = resolve_repo_config(self.config, repo_name)
        run = self.store.latest_run(
            repo_name=canonical_repo_name or repo_name or None,
            tool=tool or None,
        )
        return self.get_result(run["run_id"])

    def cancel_run(self, run_id: str, *, suppress_group_refill: bool = False) -> dict:
        try:
            validate_run_id(run_id)
            run = self.store.get_run(run_id)
        except (ValueError, KeyError) as exc:
            return self._run_lookup_error(run_id, exc)
        if run["status"] in TERMINAL_STATUSES:
            publication = publish_run_result(self.store, run_id)
            if publication["ok"]:
                self.locks.release(
                    run["repo_name"],
                    run_id,
                    str(run.get("worker_lease_token") or ""),
                    int(run.get("lease_generation") or 1),
                )
            # Retry path. The terminal transition already happened, so this
            # republishes the exact same canonical result and never re-runs
            # termination.
            return {
                "ok": bool(publication["ok"]),
                "run_id": run_id,
                "status": run["status"],
                "cancelled": False,
                "termination_confirmed": True,
                "publication_ok": bool(publication["ok"]),
                "publication_error": str(publication.get("error") or ""),
                "reason": "Run is already terminal",
            }
        if run["status"] == "cancellation_pending":
            return {
                "ok": False,
                "run_id": run_id,
                "status": "cancellation_pending",
                "cancelled": False,
                "terminated": False,
                "termination_confirmed": False,
                "reason": "Cancellation is already pending",
            }

        lease_token = str(run.get("worker_lease_token") or "")
        lease_generation = int(run.get("lease_generation") or 1)
        requested_at = datetime.now(timezone.utc).isoformat()
        progress = dict(run.get("progress") or {})
        progress["cancellation_requested_at"] = requested_at
        pending = self.store.conditional_update(
            run_id,
            fields={
                "status": "cancellation_pending",
                "current_phase": "cancellation_pending",
                "progress_json": progress,
            },
            expected_statuses=(str(run["status"]),),
            expected_state_version=int(run.get("state_version") or 0),
            expected_lease_token=lease_token,
            expected_lease_generation=lease_generation,
            reject_terminal=True,
        )
        if pending is None:
            winner = self.store.get_run(run_id)
            winner_terminal = winner["status"] in TERMINAL_STATUSES
            if winner_terminal:
                publication = publish_run_result(self.store, run_id)
                if publication["ok"]:
                    self.locks.release(
                        run["repo_name"], run_id, lease_token, lease_generation
                    )
            published = bool(publication["ok"]) if winner_terminal else False
            return {
                "ok": winner_terminal and published,
                "run_id": run_id,
                "status": winner["status"],
                "cancelled": winner["status"] == "cancelled",
                "terminated": False,
                "termination_confirmed": winner_terminal,
                "publication_ok": published,
                "publication_error": (
                    str(publication.get("error") or "") if winner_terminal else ""
                ),
                "reason": "Cancellation lost a concurrent state transition",
            }

        child_pid = int(run.get("pid") or 0)
        worker_pid = int(run.get("worker_pid") or 0)
        launcher_pid = int(run.get("launcher_pid") or 0)

        def persist_progress() -> None:
            self.store.conditional_update(
                run_id,
                fields={
                    "current_phase": "cancellation_pending",
                    "progress_json": progress,
                    "elapsed_seconds": float(run.get("elapsed_seconds") or 0.0),
                },
                expected_statuses=("cancellation_pending",),
                expected_lease_token=lease_token,
                expected_lease_generation=lease_generation,
                bump_state_version=False,
            )

        def finish_cancel(
            *,
            error: str,
            reports: list[dict],
            terminated: bool,
            message: str,
        ) -> dict:
            current = self.store.get_run(run_id)
            ended_at = datetime.now(timezone.utc).isoformat()
            result = self._cancellation_result(current, ended_at, error, progress)
            cancelled = self.store.transition_terminal(
                run_id,
                status="cancelled",
                result=result,
                expected_statuses=("cancellation_pending",),
                expected_state_version=int(current["state_version"]),
                expected_lease_token=lease_token,
                expected_lease_generation=lease_generation,
                ended_at=ended_at,
                duration_seconds=current.get("duration_seconds"),
                exit_code=current.get("exit_code"),
                summary=error,
                error=error,
                progress=progress,
            )
            if cancelled is None:
                winner = self.store.get_run(run_id)
                winner_terminal = winner["status"] in TERMINAL_STATUSES
                if winner_terminal:
                    publication = publish_run_result(self.store, run_id)
                    if publication["ok"]:
                        self.locks.release(
                            run["repo_name"], run_id, lease_token, lease_generation
                        )
                published = bool(publication["ok"]) if winner_terminal else False
                return {
                    "ok": winner_terminal and published,
                    "run_id": run_id,
                    "status": winner["status"],
                    "cancelled": winner["status"] == "cancelled",
                    "terminated": terminated,
                    "termination_confirmed": winner_terminal,
                    "termination_reports": reports,
                    "publication_ok": published,
                    "publication_error": (
                        str(publication.get("error") or "") if winner_terminal else ""
                    ),
                    "reason": "Final cancellation lost a concurrent state transition",
                }
            publication = publish_run_result(self.store, run_id)
            if not publication["ok"]:
                self._append_recovery_event(
                    run,
                    level="error",
                    message="Canonical terminal result publication failed",
                    data={"error": publication["error"]},
                )
            # Lock policy for V3-1A-CANCELLATION-CLOSURE-1: once zero owned
            # processes is proven nothing can still mutate the repository, so the
            # lock is released even when publication fails. The response below
            # must then be honest that the cancellation is only partial.
            self.locks.release(run["repo_name"], run_id, lease_token, lease_generation)
            event = self.store.append_event(
                run_id,
                level="warning",
                stage="cancel",
                message=message,
                data={"termination_reports": reports},
                update_run_metadata=False,
            )
            ArtifactWriter(Path(run["run_dir"])).append_event(event)
            if not suppress_group_refill:
                refill_powershell_groups(
                    config=self.config,
                    spawn_worker=self._spawn_worker,
                )
            # Termination and publication are reported separately. A caller must
            # not be able to read a publication failure as complete success, so
            # ok follows publication while the proven facts stay visible.
            return {
                "ok": bool(publication["ok"]),
                "run_id": run_id,
                "status": "cancelled",
                "cancelled": True,
                "terminated": terminated,
                "termination_confirmed": True,
                "termination_reports": reports,
                "publication_ok": bool(publication["ok"]),
                "publication_error": str(publication.get("error") or ""),
                "retry_hint": (
                    ""
                    if publication["ok"]
                    else "Terminal state is durable; retry cancel_run to republish "
                    "the same result without repeating termination."
                ),
            }

        if run["tool"] in {"ssh_monitored_command", "remote_powershell"}:
            if not launcher_pid and not worker_pid and not child_pid:
                return finish_cancel(
                    error="Run cancelled before monitored SSH launch",
                    reports=[],
                    terminated=False,
                    message="Monitored SSH run cancelled before launch",
                )
            if worker_pid > 0 and process_is_running(worker_pid):
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": False,
                    "termination_confirmed": False,
                    "reason": "Cancellation recorded; attached worker owns remote termination",
                }

            remote_process = dict(progress.get("remote_process") or {})
            if not remote_process:
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": False,
                    "termination_confirmed": False,
                    "reason": "Worker is unavailable and remote process identity is unknown; lock retained",
                }
            controller_state = run.get("input", {}).get("remote_controller_state")
            if not isinstance(controller_state, dict):
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": False,
                    "termination_confirmed": False,
                    "reason": "Authoritative remote-controller contract is unavailable; lock retained",
                }
            termination = cancel_remote_controller(
                self.config,
                str(run["input"]["host_id"]),
                controller_state,
                {
                    **remote_process,
                    "command_id": str(run["input"]["command_id"]),
                },
                requested_at=requested_at,
                grace_seconds=int(progress.get("termination_grace_seconds") or 5),
            )
            progress["remote_termination"] = termination
            if not termination.get("terminated") or not termination.get(
                "completion_persisted"
            ):
                persist_progress()
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": False,
                    "termination_confirmed": False,
                    "termination_reports": [termination],
                    "reason": "Remote termination could not be confirmed; lock retained",
                }

            reports: list[dict] = []
            if child_pid > 0 and process_is_running(child_pid):
                report = terminate_process_tree(child_pid)
                report["role"] = "child"
                reports.append(report)
            progress["termination_reports"] = reports
            if not all(bool(report.get("terminated")) for report in reports):
                persist_progress()
                return {
                    "ok": False,
                    "run_id": run_id,
                    "status": "cancellation_pending",
                    "cancelled": False,
                    "terminated": True,
                    "termination_confirmed": False,
                    "termination_reports": [termination, *reports],
                    "reason": "Remote exit confirmed but local SSH termination is unconfirmed; lock retained",
                }
            return finish_cancel(
                error="Run cancelled after verified remote termination",
                reports=[termination, *reports],
                terminated=True,
                message="Monitored SSH run cancelled after verified remote termination",
            )

        # V3-1A-CANCELLATION-AUTHORITY-1, owner-approved 2026-07-30: a live PID
        # without an exact matching recorded start identity is never terminated.
        # Soma cannot prove it owns that process, so the run stays
        # cancellation_pending and the repository lock stays held rather than
        # Soma force-killing a process that may belong to someone else.
        pids: list[tuple[str, int, str]] = []
        if child_pid > 0:
            pids.append(("child", child_pid, str(run.get("child_identity") or "")))
        if worker_pid > 0 and worker_pid != child_pid:
            pids.append(("worker", worker_pid, str(run.get("worker_identity") or "")))
        if (
            launcher_pid > 0
            and launcher_pid != child_pid
            and launcher_pid != worker_pid
        ):
            pids.append(
                ("launcher", launcher_pid, str(run.get("launcher_identity") or ""))
            )
        reports: list[dict] = []
        for role, pid, recorded_identity in pids:
            report = identity_scoped_termination(
                pid, recorded_identity, terminate=terminate_process_tree
            )
            report["role"] = role
            reports.append(report)
        termination_confirmed = (
            not pids
            and run["status"]
            in {"pending", "launch_pending", "queued", "recovery_pending"}
        ) or (
            bool(reports) and all(bool(report.get("terminated")) for report in reports)
        )
        progress["termination_reports"] = reports

        if not termination_confirmed:
            persist_progress()
            event = self.store.append_event(
                run_id,
                level="error",
                stage="cancellation_pending",
                message="Cancellation requested but process termination is unconfirmed",
                data={"termination_reports": reports},
                update_run_metadata=False,
            )
            ArtifactWriter(Path(run["run_dir"])).append_event(event)
            return {
                "ok": False,
                "run_id": run_id,
                "status": "cancellation_pending",
                "cancelled": False,
                "terminated": False,
                "termination_confirmed": False,
                "termination_reports": reports,
                "reason": "Process termination could not be confirmed; lock retained",
            }

        return finish_cancel(
            error="Run cancelled by request",
            reports=reports,
            terminated=bool(reports),
            message="Run cancelled after process-tree termination was confirmed",
        )
