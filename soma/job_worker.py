from __future__ import annotations

import argparse
from base64 import b64decode
from collections.abc import Collection
import json
import os
import posixpath
import subprocess
import threading
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Callable, Literal, Sequence

from . import git_tools
from .cloudflare_tools import authorize_cloudflare_profile, run_cloudflare_action
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
    run_command_profile,
)
from .config import (
    AppConfig,
    SSHDeploymentProfileConfig,
    load_config,
    resolve_repo,
    resolve_repo_config,
)
from .docker_tools import build_docker_action, run_docker_action
from .events import ArtifactWriter, redact_and_truncate
from .executable_profiles import resolve_verified_local_executable
from .executable_staging import validate_executable_staging_manifest
from .external_fixtures import fetch_validate_and_discard
from .hermes_companion_client import parse_companion_result
from .gateway_models import (
    SSHReviewedScriptAction,
    SSHRootShellAction,
    validate_reviewed_ssh_script_request,
    validate_root_ssh_shell_request,
)
from .managed_artifacts import apply_managed_artifact_cleanup
from .operation_locks import OperationLockStore
from .parallel_groups import refill_powershell_groups, repository_lock_required_for_run
from .process_control import (
    process_group_popen_kwargs,
    process_identity,
    terminate_process_tree,
    capture_launch_identity,
)
from .run_store import TERMINAL_STATUSES, RunStore
from .transfer_manifests import build_upload_transfer_manifest
from .run_publication import publish_run_result
from .run_guards import (
    classify_git_attribution,
    snapshot_workspace,
)
from .repo_wiki import mark_repo_wiki_stale
from .repo_reader import analyze_text_file
from . import repo_writer
from .remote_controller_state import validate_remote_controller_state_contract
from .remote_powershell import (
    complete_remote_powershell_artifact_manifest,
    complete_remote_powershell_executable_evidence,
    decode_remote_powershell_stdin,
    validate_remote_powershell_durable_input,
)
from .safety import validate_repo_relative_path
from .ssh_commands import (
    resolve_ssh_command_profile,
    resolve_ssh_connection,
    resolve_ssh_host,
    run_ssh_command,
    run_ssh_payload,
)
from .ssh_policy import (
    IMPLEMENTED_SSH_EXECUTION_MODES,
    authorize_ssh_action_launch,
    authorize_ssh_reviewed_script_launch,
    authorize_ssh_root_shell_launch,
)
from .ssh_staging import validate_ssh_staging_manifest
from .ssh_activation import run_ssh_profile_activation
from .ssh_watchdog import (
    probe_remote_controller_state,
    start_monitored_ssh_command,
    validate_monitored_command_start,
)
from .ssh_tools import (
    _is_secret_path,
    _resolve_deployment,
    _safe_name,
    build_ssh_action,
    run_ssh_action,
    run_ssh_deployment,
    run_ssh_transfer,
    validate_remote_path,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration(started_at: str, ended_at: str) -> float:
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)
    return round((ended - started).total_seconds(), 3)


_SSH_POLICY_METADATA_FIELDS = (
    "autonomy_profile",
    "execution_mode",
    "permission_tier",
    "policy_decision",
    "policy_authorized",
    "approval_source",
)


def _ssh_policy_metadata(policy) -> dict[str, object]:
    return {
        "autonomy_profile": policy.autonomy_profile,
        "execution_mode": policy.execution_mode,
        "permission_tier": policy.permission_tier.value,
        "policy_decision": policy.decision.value,
        "policy_authorized": policy.authorized,
        "approval_source": policy.approval_source,
    }


def _persisted_ssh_approval_source(input_data: dict) -> str:
    missing = sorted(
        field for field in _SSH_POLICY_METADATA_FIELDS if field not in input_data
    )
    if missing:
        raise ValueError(
            f"Incomplete persisted SSH policy metadata; missing: {missing}"
        )

    approval_source = str(input_data["approval_source"])
    if approval_source not in {"none", "chatgpt", "human"}:
        raise ValueError(f"Invalid persisted SSH approval_source: {approval_source!r}")
    return approval_source


def _validate_persisted_ssh_policy_metadata(
    input_data: dict,
    policy,
) -> dict[str, object]:
    metadata = _ssh_policy_metadata(policy)
    persisted = {
        field: input_data.get(field) for field in _SSH_POLICY_METADATA_FIELDS
    }
    canonical = {field: metadata[field] for field in _SSH_POLICY_METADATA_FIELDS}
    if persisted != canonical:
        raise ValueError(
            "Persisted SSH policy metadata does not match canonical worker revalidation"
        )
    return metadata


def _persisted_permissive_ssh_profile(
    input_data: dict,
) -> Literal["permissive"]:
    autonomy_profile = str(input_data["autonomy_profile"])
    if autonomy_profile != "permissive":
        raise ValueError(
            "Input should be 'permissive' for persisted SSH autonomy_profile"
        )
    return "permissive"


def _authorize_persisted_ssh_policy(
    input_data: dict,
    *,
    writes_remote: bool,
    monitored: bool = False,
    high_risk: bool = False,
    implemented_modes: Collection[str] = IMPLEMENTED_SSH_EXECUTION_MODES,
) -> dict[str, object]:
    approval_source = _persisted_ssh_approval_source(input_data)
    policy = authorize_ssh_action_launch(
        autonomy_profile=_persisted_permissive_ssh_profile(input_data),
        execution_mode=str(input_data["execution_mode"]),
        writes_remote=writes_remote,
        monitored=monitored,
        high_risk=high_risk,
        chatgpt_approval_granted=approval_source == "chatgpt",
        human_approval_granted=approval_source == "human",
        implemented_modes=implemented_modes,
    )
    return _validate_persisted_ssh_policy_metadata(input_data, policy)


def _authorize_persisted_ssh_reviewed_script_policy(
    input_data: dict,
    request: SSHReviewedScriptAction,
) -> dict[str, object]:
    approval_source = _persisted_ssh_approval_source(input_data)
    policy = authorize_ssh_reviewed_script_launch(
        autonomy_profile=request.autonomy_profile,
        execution_mode=request.execution_mode,
        writes_remote=request.writes_remote,
        high_risk=request.high_risk,
        model_approval_granted=approval_source == "chatgpt",
    )
    return _validate_persisted_ssh_policy_metadata(input_data, policy)


def _authorize_persisted_ssh_root_shell_policy(
    input_data: dict,
    request: SSHRootShellAction,
) -> dict[str, object]:
    approval_source = _persisted_ssh_approval_source(input_data)
    if approval_source != "none":
        raise ValueError("Permissive SSH root shell does not accept approval evidence")
    policy = authorize_ssh_root_shell_launch(
        autonomy_profile=request.autonomy_profile,
        execution_mode=request.execution_mode,
    )
    return _validate_persisted_ssh_policy_metadata(input_data, policy)


_SSH_SCRIPT_NEWLINE_METADATA_FIELDS = frozenset(
    {"submitted_script_sha256", "line_endings_normalized"}
)


def _validate_ssh_script_newline_metadata(
    input_data: dict,
    canonical_script_sha256: str,
) -> dict[str, object]:
    normalized = input_data.get("line_endings_normalized", False)
    submitted = input_data.get("submitted_script_sha256", canonical_script_sha256)
    if not isinstance(normalized, bool):
        raise ValueError("Persisted SSH script newline metadata is invalid")
    if (
        not isinstance(submitted, str)
        or len(submitted) != 64
        or any(character not in "0123456789abcdef" for character in submitted)
    ):
        raise ValueError("Persisted SSH script submitted hash is invalid")
    if normalized == (submitted == canonical_script_sha256):
        raise ValueError("Persisted SSH script newline metadata is inconsistent")
    return {
        "submitted_script_sha256": submitted,
        "line_endings_normalized": normalized,
    }


_REVIEWED_SCRIPT_REQUEST_FIELDS = frozenset(SSHReviewedScriptAction.model_fields)
_REVIEWED_SCRIPT_PERSISTED_FIELDS = (
    _REVIEWED_SCRIPT_REQUEST_FIELDS
    | frozenset(_SSH_POLICY_METADATA_FIELDS)
    | _SSH_SCRIPT_NEWLINE_METADATA_FIELDS
    | {"staging_manifest"}
)


def _validate_ssh_reviewed_script_worker_input(
    config: AppConfig,
    input_data: dict,
) -> tuple[SSHReviewedScriptAction, dict[str, object], dict[str, object]]:
    missing = sorted(
        field
        for field in _REVIEWED_SCRIPT_REQUEST_FIELDS - {"arguments"}
        if field not in input_data
    )
    if missing:
        raise ValueError(
            f"Incomplete persisted reviewed SSH script metadata; missing: {missing}"
        )
    unexpected = sorted(set(input_data) - _REVIEWED_SCRIPT_PERSISTED_FIELDS)
    if unexpected:
        raise ValueError(
            "Unexpected persisted reviewed SSH script metadata fields: "
            f"{unexpected}"
        )

    request_payload = {
        field: input_data[field]
        for field in _REVIEWED_SCRIPT_REQUEST_FIELDS
        if field in input_data
    }
    request = validate_reviewed_ssh_script_request(request_payload)
    host = resolve_ssh_host(config, request.host_id)
    resolve_ssh_connection(host, config.ssh)
    policy_metadata = _authorize_persisted_ssh_reviewed_script_policy(
        input_data,
        request,
    )
    newline_metadata = _validate_ssh_script_newline_metadata(
        input_data,
        request.script_sha256,
    )
    return request, policy_metadata, newline_metadata


_ROOT_SHELL_REQUEST_FIELDS = frozenset(SSHRootShellAction.model_fields)
_ROOT_SHELL_PERSISTED_FIELDS = (
    _ROOT_SHELL_REQUEST_FIELDS
    | frozenset(_SSH_POLICY_METADATA_FIELDS)
    | _SSH_SCRIPT_NEWLINE_METADATA_FIELDS
)


def _validate_ssh_root_shell_worker_input(
    config: AppConfig,
    input_data: dict,
) -> tuple[SSHRootShellAction, dict[str, object], dict[str, object]]:
    missing = sorted(
        field for field in _ROOT_SHELL_REQUEST_FIELDS if field not in input_data
    )
    if missing:
        raise ValueError(
            f"Incomplete persisted SSH root shell metadata; missing: {missing}"
        )
    unexpected = sorted(set(input_data) - _ROOT_SHELL_PERSISTED_FIELDS)
    if unexpected:
        raise ValueError(
            f"Unexpected persisted SSH root shell metadata fields: {unexpected}"
        )
    request = validate_root_ssh_shell_request(
        {field: input_data[field] for field in _ROOT_SHELL_REQUEST_FIELDS}
    )
    host = resolve_ssh_host(config, request.host_id)
    resolve_ssh_connection(host, config.ssh)
    policy_metadata = _authorize_persisted_ssh_root_shell_policy(
        input_data,
        request,
    )
    newline_metadata = _validate_ssh_script_newline_metadata(
        input_data,
        request.script_sha256,
    )
    return request, policy_metadata, newline_metadata


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_ssh_transfer_worker_input(
    config: AppConfig,
    input_data: dict,
    run_dir: Path,
) -> tuple[str, Path, bool, bool]:
    if not config.ssh.allow_transfer:
        raise ValueError("SSH transfer capability is disabled by allow_transfer")
    direction = str(input_data.get("direction", "")).strip().lower()
    if direction not in {"upload", "download"}:
        raise ValueError("direction must be 'upload' or 'download'")

    overwrite = bool(input_data.get("overwrite", False))
    confirmation = str(input_data.get("confirmation", ""))
    if overwrite and confirmation != config.ssh.confirmation_token:
        raise ValueError(
            "Overwrite transfer requires the configured SSH confirmation token"
        )

    host_id = str(input_data["host_id"])
    host = resolve_ssh_host(config, host_id)
    resolve_ssh_connection(host, config.ssh)
    remote_path = validate_remote_path(
        host,
        str(input_data.get("remote_path", "")),
        sensitive=True,
    )
    repo_root = resolve_repo(config, str(input_data["local_repo_name"]))
    local_path = str(input_data.get("local_path", ""))
    recursive = bool(input_data.get("recursive", False))

    manifest = input_data.get("transfer_manifest")
    if manifest is not None and (
        not isinstance(manifest, dict) or manifest.get("version") != 1
    ):
        raise ValueError("Persisted SSH transfer manifest is invalid")

    if direction == "upload":
        local = validate_repo_relative_path(repo_root, local_path)
        if not local.exists():
            raise ValueError(f"Local upload path does not exist: {local_path}")
        if local.is_dir() and not recursive:
            raise ValueError("Directory upload requires recursive=true")
        if _is_secret_path(local.as_posix()):
            raise ValueError(
                "Secret-like local files cannot be uploaded through Soma"
            )
        expected_kind = "file" if local.is_file() else "directory"
        if manifest is not None:
            if manifest.get("source_kind") != expected_kind:
                raise ValueError("Persisted SSH transfer source kind does not match")
            current_manifest = build_upload_transfer_manifest(local)
            if manifest != current_manifest:
                if expected_kind == "file":
                    if manifest.get("source_size_bytes") != current_manifest.get(
                        "source_size_bytes"
                    ):
                        raise ValueError("SSH upload source size changed after acceptance")
                    raise ValueError("SSH upload source SHA-256 changed after acceptance")
                raise ValueError(
                    "SSH recursive upload source changed after acceptance"
                )
    else:
        requested_name = (
            Path(local_path).name if local_path else PurePosixPath(remote_path).name
        )
        if not requested_name or requested_name in {".", ".."}:
            requested_name = "downloaded-artifact"
        destination = run_dir / "downloads" / requested_name
        if manifest is not None and (
            manifest.get("source_kind") != "remote"
            or manifest.get("staging_relative_path") != f"downloads/{requested_name}"
        ):
            raise ValueError("Persisted SSH download staging path does not match")
        if destination.exists() and not overwrite:
            raise ValueError(
                f"Download destination already exists: {destination.name}"
            )

    return direction, repo_root, direction == "upload", overwrite


def _validate_ssh_deployment_worker_input(
    config: AppConfig,
    input_data: dict,
    run_id: str,
) -> tuple[SSHDeploymentProfileConfig, Path]:
    if not config.ssh.allow_deploy:
        raise ValueError("SSH deployment capability is disabled by allow_deploy")
    confirmation = str(input_data.get("confirmation", ""))
    if confirmation != config.ssh.confirmation_token:
        raise ValueError(
            "SSH deployment requires the configured confirmation token"
        )

    host_id = str(input_data["host_id"])
    deployment_id = str(input_data["deployment_id"])
    host = resolve_ssh_host(config, host_id)
    resolve_ssh_connection(host, config.ssh)
    deployment = _resolve_deployment(config, host_id, deployment_id)
    repo_root = resolve_repo(config, deployment.repo_name)
    source_root = validate_repo_relative_path(repo_root, deployment.local_subdir)
    if not source_root.is_dir():
        raise ValueError("Deployment local_subdir must resolve to a directory")

    release_root = validate_remote_path(
        host,
        posixpath.join(deployment.remote_root, "releases", run_id),
        sensitive=True,
    )
    validate_remote_path(
        host,
        posixpath.join(deployment.remote_root, "current"),
        sensitive=True,
    )
    validate_remote_path(
        host,
        posixpath.join(
            deployment.remote_root,
            ".soma",
            f"{run_id}.tar.gz",
        ),
        sensitive=True,
    )
    for remote_source, release_target in deployment.shared_files.items():
        validate_remote_path(host, remote_source, sensitive=True)
        validate_remote_path(
            host,
            posixpath.join(release_root, release_target),
            sensitive=True,
        )
    if deployment.compose_file:
        validate_remote_path(
            host,
            posixpath.join(release_root, deployment.compose_file),
        )
    if deployment.compose_project_name:
        _safe_name(deployment.compose_project_name, "compose_project_name")
    for service in deployment.compose_services:
        _safe_name(service, "service")
    if deployment.env_file:
        validate_remote_path(host, deployment.env_file, sensitive=True)
    if deployment.service_name:
        _safe_name(deployment.service_name, "service_name")
    if deployment.health_command_id:
        resolve_ssh_command_profile(
            config,
            host_id,
            deployment.health_command_id,
        )
    return deployment, repo_root


def _stream_pipe(
    pipe,
    output_path: Path,
    sink: list[str],
    limit: int = 40000,
    on_output: Callable[[], None] | None = None,
) -> None:
    with output_path.open("a", encoding="utf-8", errors="replace") as handle:
        for line in iter(pipe.readline, ""):
            handle.write(line)
            handle.flush()
            if sum(len(item) for item in sink) < limit:
                sink.append(line)
            if on_output is not None:
                on_output()
    pipe.close()


def _stream_binary_pipe(
    pipe,
    output_path: Path,
    sink: bytearray,
    limit: int,
    on_output: Callable[[], None] | None = None,
) -> None:
    with output_path.open("wb") as handle:
        while True:
            chunk = pipe.read(65536)
            if not chunk:
                break
            handle.write(chunk)
            handle.flush()
            if len(sink) < limit:
                sink.extend(chunk[: max(0, limit - len(sink))])
            if on_output is not None:
                on_output()
    pipe.close()


class JobWorker:
    def __init__(
        self, config_path: Path, run_id: str, lease_token: str | None = None
    ):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.store = RunStore(self.config.resolve_runs_dir())
        self.locks = OperationLockStore(self.config.resolve_runs_dir())
        self.run = self.store.get_run(run_id)
        self.run_id = run_id
        self.worker_lease_token = (
            str(lease_token)
            if lease_token is not None
            else str(self.run.get("worker_lease_token") or "")
        )
        self.worker_lease_generation = int(self.run.get("lease_generation") or 1)
        self.repository_lock_required = repository_lock_required_for_run(
            self.run, self.config.resolve_runs_dir()
        )
        self.artifacts = ArtifactWriter(Path(self.run["run_dir"]))
        self._started_monotonic = 0.0
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._last_output_heartbeat = 0.0

    def event(
        self, level: str, stage: str, message: str, data: dict | None = None
    ) -> bool:
        active = self.store.update_worker_progress(
            self.run_id,
            lease_token=self.worker_lease_token,
            lease_generation=self.worker_lease_generation,
            phase=stage,
            progress=data or {},
            elapsed_seconds=self._elapsed_seconds(),
        )
        if not active:
            return False
        lock_active = True
        if self.repository_lock_required:
            lock_active = self.locks.heartbeat(
                self.run["repo_name"],
                self.run_id,
                self.worker_lease_token,
                self.worker_lease_generation,
            )
        if self.worker_lease_token and not lock_active:
            return False
        event = self.store.append_event(
            self.run_id,
            level=level,
            stage=stage,
            message=message,
            data=redact_and_truncate(data or {}),
            update_run_metadata=False,
        )
        self.artifacts.append_event(event)
        return True

    def _elapsed_seconds(self) -> float:
        if not self._started_monotonic:
            return 0.0
        return round(max(0.0, time.monotonic() - self._started_monotonic), 3)

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(5.0):
            try:
                run_active = self.store.heartbeat_worker(
                    self.run_id,
                    lease_token=self.worker_lease_token,
                    lease_generation=self.worker_lease_generation,
                    elapsed_seconds=self._elapsed_seconds(),
                    progress_updates={"worker_pid": os.getpid()},
                )
                lock_active = True
                if self.repository_lock_required:
                    lock_active = self.locks.heartbeat(
                        self.run["repo_name"],
                        self.run_id,
                        self.worker_lease_token,
                        self.worker_lease_generation,
                    )
                if not run_active or (self.worker_lease_token and not lock_active):
                    self._heartbeat_stop.set()
                    return
            except Exception:
                continue

    def _note_output(self) -> None:
        now = time.monotonic()
        if now - self._last_output_heartbeat < 1.0:
            return
        self._last_output_heartbeat = now
        self.store.heartbeat_worker(
            self.run_id,
            lease_token=self.worker_lease_token,
            lease_generation=self.worker_lease_generation,
            elapsed_seconds=self._elapsed_seconds(),
            progress_updates={"last_output_at": _utc_now()},
        )

    COMMIT_EVIDENCE_ARTIFACT = "commit_evidence.json"

    def _mark_wiki_stale_with_evidence(
        self, repo_root: Path, repo_name: str, *, reason: str
    ) -> dict[str, object]:
        """Mark repository knowledge stale, publishing failure explicitly.

        A managed change must lead to a fresh generation or to a visible
        freshness failure. It must never leave repository knowledge quietly
        stale, and a bookkeeping failure must not be reported as a failed
        commit: the commit already succeeded.
        """
        try:
            return mark_repo_wiki_stale(repo_root, repo_name, reason=reason)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            self.event(
                "error",
                "repo_wiki",
                "Repository knowledge could not be marked stale after a managed change",
                {"repo_name": repo_name, "reason": reason, "error": detail[:500]},
            )
            return {
                "ok": False,
                "stale": None,
                "freshness_known": False,
                "reason": reason,
                "error": detail[:500],
                "recommended_action": (
                    "Repository knowledge may be stale. Refresh the repository "
                    "wiki before relying on it."
                ),
            }

    def _compact_commit_data(self, commit_data: dict[str, object]) -> dict[str, object]:
        """Keep the run record compact while preserving complete commit evidence.

        The authoritative stage manifests, Git status, and dirty-file inventories
        are repository-scale. They are written once to a protected run artifact
        and referenced by SHA-256 so the durable run result stays proportional to
        the operation rather than to the repository.
        """
        commit_result = commit_data.get("commit_result")
        if not isinstance(commit_result, dict):
            return commit_data
        compact_result, full_body = git_tools.compact_commit_result(commit_result)
        preserved = commit_data.get("preserved_preexisting_changes")
        compact_preserved = None
        if isinstance(preserved, list):
            full_body["preserved_preexisting_changes"] = preserved
            compact_preserved = git_tools._compact_path_list(preserved)
        if not full_body:
            return commit_data
        updated = dict(commit_data)
        reference: dict[str, object] = {
            "artifact": self.COMMIT_EVIDENCE_ARTIFACT,
            "fields": sorted(full_body),
            "available": False,
        }
        try:
            payload = json.dumps(full_body, sort_keys=True, ensure_ascii=False)
            self.artifacts.write_protected_text(self.COMMIT_EVIDENCE_ARTIFACT, payload)
            reference.update(
                {
                    "available": True,
                    "sha256": sha256(payload.encode("utf-8")).hexdigest(),
                    "size_bytes": len(payload.encode("utf-8")),
                }
            )
        except OSError as exc:
            # Never convert an evidence-write failure into apparent success: keep
            # the full body inline so nothing is lost, and report the failure.
            self.event(
                "warning",
                "evidence",
                "Commit evidence artifact could not be written; retaining inline body",
                {"artifact": self.COMMIT_EVIDENCE_ARTIFACT, "error": str(exc)[:500]},
            )
            return commit_data
        updated["commit_result"] = compact_result
        if compact_preserved is not None:
            updated["preserved_preexisting_changes"] = compact_preserved
        updated["commit_evidence_ref"] = reference
        return updated

    def _finalize_commit(
        self,
        repo_root: Path,
        changed_files: list[str],
        *,
        tool_name: str,
        commit_title: str = "",
        commit_description: str = "",
    ) -> dict[str, object]:
        return self._compact_commit_data(
            git_tools.finalize_explicit_changes(
                repo_root,
                changed_files,
                tool_name=tool_name,
                run_id=self.run_id,
                commit_title=commit_title or None,
                commit_description=commit_description,
            )
        )

    def execute(self) -> int:
        current_before_start = self.store.get_run(self.run_id)
        if current_before_start["status"] == "cancelled":
            return 0
        worker_pid = os.getpid()
        worker_identity = process_identity(worker_pid)
        claimed = self.store.claim_worker(
            self.run_id,
            lease_token=self.worker_lease_token,
            lease_generation=self.worker_lease_generation,
            expected_state_version=int(current_before_start["state_version"]),
            worker_pid=worker_pid,
            worker_identity=worker_identity,
        )
        if not claimed:
            return 1
        lock_claimed = True
        if self.repository_lock_required:
            lock_claimed = self.locks.claim_owner(
                current_before_start["repo_name"],
                self.run_id,
                owner_pid=worker_pid,
                owner_token=self.worker_lease_token,
                lease_generation=self.worker_lease_generation,
            )
        self.run = self.store.get_run(self.run_id)
        if self.worker_lease_token and not lock_claimed:
            self.store.mark_recovery_pending(
                self.run_id,
                "Worker claimed run lease but repository lock ownership did not match",
                expected_statuses=("running",),
                expected_state_version=int(self.run["state_version"]),
                expected_lease_token=self.worker_lease_token,
                expected_lease_generation=self.worker_lease_generation,
                expected_heartbeat_at=self.run.get("heartbeat_at"),
            )
            return 1
        started_at = str(self.run.get("started_at") or _utc_now())
        self._started_monotonic = time.monotonic()
        self.event(
            "info",
            "worker",
            "Worker claimed durable execution lease",
            {
                "worker_pid": worker_pid,
                "worker_identity_recorded": bool(worker_identity),
            },
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"soma-heartbeat-{self.run_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()
        try:
            result = self._execute_inner(started_at)
            result.setdefault("stdout", "")
            result.setdefault("stderr", "")
            exit_code = result.get("exit_code")
            result.setdefault(
                "process_success", exit_code == 0 if exit_code is not None else None
            )
            result.setdefault(
                "classification",
                "process_failure"
                if exit_code not in {None, 0}
                else (
                    "semantic_failure"
                    if result.get("status") in {"failed", "partial"}
                    else "success"
                ),
            )
            status = str(
                result.get("status")
                or (
                    "failed"
                    if result.get("safety_failure")
                    or result.get("blocked")
                    or result.get("exit_code", 1) != 0
                    else "completed"
                )
            )
            ended_at = result["ended_at"]
            current = self.store.get_run(self.run_id)
            if status in TERMINAL_STATUSES:
                expected_terminal_statuses = ("running",)
                if self.run["tool"] == "ssh_monitored_command" and status in {
                    "cancelled",
                    "timed_out",
                }:
                    expected_terminal_statuses = ("running", "cancellation_pending")
                persisted = self.store.transition_terminal(
                    self.run_id,
                    status=status,
                    result=result,
                    expected_statuses=expected_terminal_statuses,
                    expected_state_version=int(current["state_version"]),
                    expected_lease_token=self.worker_lease_token,
                    expected_lease_generation=self.worker_lease_generation,
                    ended_at=ended_at,
                    duration_seconds=result["duration_seconds"],
                    exit_code=result.get("exit_code"),
                    summary=result.get("summary", ""),
                    error=result.get("error", ""),
                    safety_failure=result.get("safety_failure", False),
                )
            elif status == "cancellation_pending":
                persisted = self.store.conditional_update(
                    self.run_id,
                    fields={
                        "status": "cancellation_pending",
                        "current_phase": "cancellation_pending",
                        "ended_at": None,
                        "duration_seconds": result["duration_seconds"],
                        "exit_code": result.get("exit_code"),
                        "summary": result.get("summary", ""),
                        "error": result.get("error", ""),
                        "safety_failure": result.get("safety_failure", False),
                        "result_json": result,
                    },
                    expected_statuses=("running",),
                    expected_state_version=int(current["state_version"]),
                    expected_lease_token=self.worker_lease_token,
                    expected_lease_generation=self.worker_lease_generation,
                    reject_terminal=True,
                )
            else:
                raise ValueError(f"Unsupported worker result status: {status}")
            if persisted is None:
                winner = self.store.get_run(self.run_id)
                if winner["status"] in TERMINAL_STATUSES:
                    publication = publish_run_result(self.store, self.run_id)
                    if not publication["ok"]:
                        self.store.append_event(
                            self.run_id,
                            level="error",
                            stage="result_publication",
                            message="Canonical result publication failed",
                            data={"error": publication["error"]},
                            update_run_metadata=False,
                        )
                if (
                    winner.get("worker_lease_token") == self.worker_lease_token
                    and int(winner.get("lease_generation") or 1)
                    == self.worker_lease_generation
                ):
                    event = self.store.append_event(
                        self.run_id,
                        level="warning",
                        stage="result_race",
                        message="Worker result lost a conditional state transition",
                        data={"attempted_status": status, "winner": winner["status"]},
                        update_run_metadata=False,
                    )
                    self.artifacts.append_event(event)
                return (
                    int(result.get("exit_code") or 0)
                    if winner["status"] in TERMINAL_STATUSES
                    or winner["status"] == "cancellation_pending"
                    else 1
                )
            if status in TERMINAL_STATUSES:
                publication = publish_run_result(self.store, self.run_id)
                if not publication["ok"]:
                    self.store.append_event(
                        self.run_id,
                        level="error",
                        stage="result_publication",
                        message="Canonical result publication failed",
                        data={"error": publication["error"]},
                        update_run_metadata=False,
                    )
            level = (
                "info"
                if status == "completed"
                else "warning"
                if status in {"partial", "cancelled", "timed_out"}
                else "error"
            )
            event = self.store.append_event(
                self.run_id,
                level=level,
                stage="result",
                message=f"Run {status}",
                data={"exit_code": result.get("exit_code")},
                update_run_metadata=False,
            )
            self.artifacts.append_event(event)
            worker_exit_code = int(result.get("exit_code") or 0)
            return (
                1
                if status in {"failed", "cancellation_pending"}
                and worker_exit_code == 0
                else worker_exit_code
            )
        except Exception as exc:
            ended_at = _utc_now()
            result = self._error_result(started_at, ended_at, exc)
            progress = dict(self.store.get_run(self.run_id).get("progress") or {})
            remote_process = dict(progress.get("remote_process") or {})
            remote_identity_known = bool(
                self.run["tool"] == "ssh_monitored_command"
                and remote_process.get("pid")
                and remote_process.get("pgid")
                and remote_process.get("start_time_ticks")
            )
            failure_status = (
                "cancellation_pending" if remote_identity_known else "failed"
            )
            if remote_identity_known:
                result.update(
                    {
                        "status": "cancellation_pending",
                        "error": (
                            "Worker failed after remote launch; remote exit is unconfirmed: "
                            + str(exc)
                        ),
                        "safety_failure": True,
                        "remote_process": remote_process,
                    }
                )
            current = self.store.get_run(self.run_id)
            if remote_identity_known:
                persisted = self.store.conditional_update(
                    self.run_id,
                    fields={
                        "status": "cancellation_pending",
                        "current_phase": "cancellation_pending",
                        "ended_at": None,
                        "duration_seconds": result["duration_seconds"],
                        "exit_code": 1,
                        "summary": result["summary"],
                        "error": result["error"],
                        "safety_failure": True,
                        "result_json": result,
                    },
                    expected_statuses=("running",),
                    expected_state_version=int(current["state_version"]),
                    expected_lease_token=self.worker_lease_token,
                    expected_lease_generation=self.worker_lease_generation,
                    reject_terminal=True,
                )
            else:
                persisted = self.store.transition_terminal(
                    self.run_id,
                    status="failed",
                    result=result,
                    expected_statuses=("running",),
                    expected_state_version=int(current["state_version"]),
                    expected_lease_token=self.worker_lease_token,
                    expected_lease_generation=self.worker_lease_generation,
                    ended_at=ended_at,
                    duration_seconds=result["duration_seconds"],
                    exit_code=1,
                    summary=result["summary"],
                    error=result["error"],
                    safety_failure=True,
                )
            if persisted is not None:
                if failure_status in TERMINAL_STATUSES:
                    publication = publish_run_result(self.store, self.run_id)
                    if not publication["ok"]:
                        self.store.append_event(
                            self.run_id,
                            level="error",
                            stage="result_publication",
                            message="Canonical result publication failed",
                            data={"error": publication["error"]},
                            update_run_metadata=False,
                        )
                event = self.store.append_event(
                    self.run_id,
                    level="error",
                    stage=(
                        "cancellation_pending" if remote_identity_known else "result"
                    ),
                    message=(
                        "Run requires remote recovery"
                        if remote_identity_known
                        else "Run failed"
                    ),
                    data={"error": str(exc)},
                    update_run_metadata=False,
                )
                self.artifacts.append_event(event)
            else:
                winner = self.store.get_run(self.run_id)
                if winner["status"] in TERMINAL_STATUSES:
                    publish_run_result(self.store, self.run_id)
            return 1
        finally:
            self._heartbeat_stop.set()
            if self._heartbeat_thread is not None:
                self._heartbeat_thread.join(timeout=2)
            final_status = str(self.store.get_run(self.run_id).get("status") or "")
            if self.repository_lock_required and final_status != "cancellation_pending":
                self.locks.release(
                    self.run["repo_name"],
                    self.run_id,
                    self.worker_lease_token,
                    self.worker_lease_generation,
                )

    def _execute_executable_profile(self, started_at: str, input_data: dict) -> dict:
        profile, executable_identity = resolve_verified_local_executable(
            self.config,
            str(input_data["profile_id"]),
        )
        if input_data.get("executable_identity") != executable_identity:
            raise ValueError(
                "Persisted executable identity does not match worker revalidation"
            )
        if str(input_data.get("autonomy_profile", "")) != profile.autonomy_profile:
            raise ValueError("Persisted executable autonomy profile does not match config")
        if str(input_data.get("target", "")) != "local":
            raise ValueError("Executable worker only supports local targets")

        argv = input_data.get("argv")
        if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
            raise ValueError("Persisted executable argv must be a list of strings")
        command = [str(executable_identity["executable_path"]), *argv]
        working_directory = str(input_data.get("working_directory") or "")
        cwd = Path(working_directory) if working_directory else None
        if cwd is not None and (
            not cwd.is_absolute() or not cwd.is_dir() or cwd.is_symlink()
        ):
            raise ValueError("Persisted executable working directory is invalid")

        environment = input_data.get("environment")
        if not isinstance(environment, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in environment.items()
        ):
            raise ValueError("Persisted executable environment must be string pairs")
        process_env = os.environ.copy() if input_data.get("inherit_environment") else {}
        process_env.update(environment)

        run_dir = Path(self.run["run_dir"])
        staging_manifest = input_data.get("staging_manifest")
        output_entries: list[dict[str, object]] = []
        if staging_manifest is not None:
            if not isinstance(staging_manifest, dict):
                raise ValueError("Persisted executable staging manifest is invalid")
            stdin_payload, output_paths, output_entries = (
                validate_executable_staging_manifest(
                    run_dir,
                    staging_manifest,
                    run_id=self.run_id,
                    lease_generation=self.worker_lease_generation,
                )
            )
            stdout_path = output_paths["stdout"]
            stderr_path = output_paths["stderr"]
        else:
            stdin_mode = str(input_data.get("stdin_mode", "none"))
            if stdin_mode == "text":
                stdin_payload = str(input_data.get("stdin_text") or "").encode("utf-8")
            elif stdin_mode == "bytes":
                try:
                    stdin_payload = b64decode(
                        str(input_data.get("stdin_base64") or ""), validate=True
                    )
                except Exception as exc:
                    raise ValueError("Persisted executable binary stdin is invalid") from exc
            elif stdin_mode == "none":
                stdin_payload = None
            else:
                raise ValueError(f"Unsupported executable stdin mode: {stdin_mode}")
            stdout_path = run_dir / "stdout.bin"
            stderr_path = run_dir / "stderr.bin"

        timeout_value = input_data.get("timeout_seconds")
        timeout_seconds = None if timeout_value is None else int(timeout_value)
        public_limit = int(input_data.get("public_output_max_bytes") or 40000)
        self.event(
            "info",
            "executable",
            "Starting configured executable directly",
            {
                "profile_id": profile.profile_id,
                "executable_path": executable_identity["executable_path"],
                "argv_count": len(argv),
                "shell": False,
            },
        )
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=process_env,
            stdin=subprocess.PIPE if stdin_payload is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            **process_group_popen_kwargs(),
        )
        # Capture or contain: an executable child attached with an empty
        # identity is unterminable under the no-raw-PID rule, so it must not
        # reach a healthy attachment.
        child_identity = capture_launch_identity(process)
        try:
            attached = self.store.attach_child_pid(
                self.run_id,
                child_pid=process.pid,
                child_identity=child_identity,
                lease_token=self.worker_lease_token,
                lease_generation=self.worker_lease_generation,
            )
        except Exception:
            # Persistence failed after creation. Stop the exact process through
            # creator-held ownership before surfacing the failure.
            try:
                process.kill()
            except Exception:
                pass
            terminate_process_tree(process.pid)
            raise
        if not attached:
            terminate_process_tree(process.pid)
            raise RuntimeError("Worker lease was lost before child process attachment")
        self.event(
            "info",
            "executable",
            "Configured executable process spawned",
            {"pid": process.pid, "profile_id": profile.profile_id},
        )

        stdout_buffer = bytearray()
        stderr_buffer = bytearray()
        stdout_thread = threading.Thread(
            target=_stream_binary_pipe,
            args=(process.stdout, stdout_path, stdout_buffer, public_limit, self._note_output),
        )
        stderr_thread = threading.Thread(
            target=_stream_binary_pipe,
            args=(process.stderr, stderr_path, stderr_buffer, public_limit, self._note_output),
        )
        stdout_thread.start()
        stderr_thread.start()
        if process.stdin is not None:
            try:
                process.stdin.write(stdin_payload or b"")
                process.stdin.flush()
            finally:
                process.stdin.close()

        termination: dict[str, object] = {"terminated": False}
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            termination = terminate_process_tree(process.pid)
            exit_code = 124
            self.event(
                "error",
                "executable",
                "Configured executable timed out; process-tree termination requested",
                {"pid": process.pid, "termination": termination},
            )
        stdout_thread.join(timeout=10)
        stderr_thread.join(timeout=10)
        ended_at = _utc_now()
        stdout = bytes(stdout_buffer).decode("utf-8", errors="replace")
        stderr = bytes(stderr_buffer).decode("utf-8", errors="replace")
        hermes_response = None
        companion_metadata = input_data.get("hermes_companion")
        if companion_metadata is not None:
            if not isinstance(companion_metadata, dict):
                raise ValueError("Persisted Hermes companion metadata is invalid")
            hermes_response = parse_companion_result(
                stdout,
                expected_operation=str(companion_metadata.get("operation") or ""),
                expected_registry_generation=companion_metadata.get(
                    "expected_registry_generation"
                ),
                expected_schema_hash=str(
                    companion_metadata.get("expected_schema_hash") or ""
                ),
            )
        status = "completed" if exit_code == 0 else "failed"
        if timed_out and termination.get("terminated"):
            status = "timed_out"
        elif timed_out:
            status = "cancellation_pending"
        staged_artifacts = []
        for entry in output_entries:
            stream = str(entry["stream"])
            path = stdout_path if stream == "stdout" else stderr_path
            staged_artifacts.append(
                {
                    **entry,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                    "invoking_run_id": self.run_id,
                    "lease_generation": self.worker_lease_generation,
                }
            )
        return {
            "tool": "executable_profile",
            "profile_id": profile.profile_id,
            "argv": argv,
            "executable_identity": executable_identity,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "status": status,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "termination": termination,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_artifact": stdout_path.name,
            "stderr_artifact": stderr_path.name,
            "staged_artifacts": staged_artifacts,
            "stdout_bytes": stdout_path.stat().st_size,
            "stderr_bytes": stderr_path.stat().st_size,
            "hermes_companion": companion_metadata,
            "hermes_response": hermes_response,
            "output_truncated": (
                stdout_path.stat().st_size > len(stdout_buffer)
                or stderr_path.stat().st_size > len(stderr_buffer)
            ),
            "summary": (stdout or stderr).strip()[:public_limit],
        }

    def _execute_inner(self, started_at: str) -> dict:
        input_data = self.run["input"]
        tool = self.run["tool"]

        if tool == "executable_profile":
            return self._execute_executable_profile(started_at, input_data)
        if tool == "cloudflare_action":
            return self._execute_cloudflare_action(started_at, input_data)
        if tool == "ssh_command":
            return self._execute_ssh_command(started_at, input_data)
        if tool == "ssh_monitored_command":
            return self._execute_ssh_monitored_command(started_at, input_data)
        if tool == "remote_powershell":
            return self._execute_remote_powershell(started_at, input_data)
        if tool == "ssh_reviewed_script":
            return self._execute_ssh_reviewed_script(started_at, input_data)
        if tool == "ssh_root_shell":
            return self._execute_ssh_root_shell(started_at, input_data)
        if tool == "ssh_action":
            return self._execute_ssh_action(started_at, input_data)
        if tool == "ssh_transfer":
            return self._execute_ssh_transfer(started_at, input_data)
        if tool == "ssh_deployment":
            return self._execute_ssh_deployment(started_at, input_data)
        if tool == "ssh_profile_activation":
            return self._execute_ssh_profile_activation(started_at, input_data)

        repo_name = input_data["repo_name"]
        repo_root = resolve_repo(self.config, repo_name)

        if tool == "repo_apply":
            return self._execute_repo_apply(started_at, repo_name, repo_root, input_data)
        if tool == "project_command":
            return self._execute_project_command(
                started_at, repo_name, repo_root, input_data
            )
        if tool == "docker_action":
            return self._execute_docker_action(
                started_at, repo_name, repo_root, input_data
            )
        if tool == "external_fixture_validation":
            return self._execute_external_fixture_validation(
                started_at, repo_name, input_data
            )

        raise ValueError(f"Unsupported async tool: {tool}")

    def _execute_ssh_reviewed_script(
        self,
        started_at: str,
        input_data: dict,
    ) -> dict:
        request, policy_metadata, newline_metadata = (
            _validate_ssh_reviewed_script_worker_input(
                self.config,
                input_data,
            )
        )
        run_dir = Path(self.run["run_dir"])
        staging_manifest = input_data.get("staging_manifest")
        staged_artifacts: list[dict[str, object]] = []
        if staging_manifest is not None:
            if not isinstance(staging_manifest, dict):
                raise ValueError("Persisted SSH staging manifest is invalid")
            staged_script, output_paths, output_entries = validate_ssh_staging_manifest(
                run_dir,
                staging_manifest,
                tool="ssh_reviewed_script",
                run_id=self.run_id,
                lease_generation=self.worker_lease_generation,
            )
            if staged_script is None or sha256(staged_script.encode("utf-8")).hexdigest() != request.script_sha256:
                raise ValueError("Reviewed-script staged input does not match the approved hash")
            execution_script = staged_script
        else:
            execution_script = request.script
            output_paths = {"stdout": run_dir / "stdout.txt", "stderr": run_dir / "stderr.txt"}
            output_entries = []
        self.event(
            "info",
            "ssh_reviewed_script",
            "Starting hash-pinned reviewed SSH script",
            {
                "host_id": request.host_id,
                "interpreter": request.interpreter,
                "arguments": list(request.arguments),
                "script_sha256": request.script_sha256,
                **newline_metadata,
                "timeout_seconds": request.timeout_seconds,
                "writes_remote": request.writes_remote,
                "high_risk": request.high_risk,
                **policy_metadata,
            },
        )
        command_result = dict(
            redact_and_truncate(
                run_ssh_payload(
                    self.config,
                    request.host_id,
                    request.interpreter,
                    execution_script,
                    payload_sha256=request.script_sha256,
                    arguments=request.arguments,
                    timeout_seconds=request.timeout_seconds,
                    writes_remote=request.writes_remote,
                )
            )
        )
        stdout = str(command_result.get("stdout", ""))
        stderr = str(command_result.get("stderr", ""))
        self.artifacts.write_protected_text("stdout.txt", stdout)
        self.artifacts.write_protected_text("stderr.txt", stderr)
        for entry in output_entries:
            path = output_paths[str(entry["stream"])]
            staged_artifacts.append(
                {
                    **entry,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                    "invoking_run_id": self.run_id,
                    "lease_generation": self.worker_lease_generation,
                }
            )
        timed_out = bool(command_result.get("timed_out"))
        status = (
            "timed_out"
            if timed_out
            else "completed"
            if command_result.get("ok")
            else "failed"
        )
        output_summary = (stdout or stderr).strip()
        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{request.host_id}",
            "tool": "ssh_reviewed_script",
            "host_id": request.host_id,
            "ssh_alias": str(command_result.get("ssh_alias", "")),
            "interpreter": request.interpreter,
            "arguments": list(request.arguments),
            "script_sha256": request.script_sha256,
            **newline_metadata,
            **policy_metadata,
            "writes_remote": request.writes_remote,
            "high_risk": request.high_risk,
            "remote_state_verified": False,
            "status": status,
            "exit_code": int(command_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": output_summary,
            "summary": output_summary[-4000:] if output_summary else "Reviewed SSH script finished",
            "remaining_risks": [
                "Soma cannot independently verify the resulting remote state"
            ]
            if request.writes_remote
            else [],
            "error": str(command_result.get("error", "")),
            "safety_failure": False,
            "timed_out": timed_out,
            "output_truncated": bool(command_result.get("output_truncated")),
            "argv": list(command_result.get("argv", [])),
            "command_result": command_result,
            "staged_artifacts": staged_artifacts,
        }

    def _execute_ssh_root_shell(
        self,
        started_at: str,
        input_data: dict,
    ) -> dict:
        request, policy_metadata, newline_metadata = (
            _validate_ssh_root_shell_worker_input(
                self.config,
                input_data,
            )
        )
        self.event(
            "info",
            "ssh_root_shell",
            "Starting permissive hash-pinned SSH root shell",
            {
                "host_id": request.host_id,
                "script_sha256": request.script_sha256,
                **newline_metadata,
                "timeout_seconds": request.timeout_seconds,
                **policy_metadata,
            },
        )
        full_command_result = run_ssh_payload(
            self.config,
            request.host_id,
            "bash",
            request.script,
            payload_sha256=request.script_sha256,
            timeout_seconds=request.timeout_seconds,
            writes_remote=True,
            root_required=True,
        )
        full_stdout = str(full_command_result.get("stdout", ""))
        full_stderr = str(full_command_result.get("stderr", ""))
        self.artifacts.write_protected_text("stdout.txt", full_stdout)
        self.artifacts.write_protected_text("stderr.txt", full_stderr)
        command_result = dict(redact_and_truncate(full_command_result))
        stdout = str(command_result.get("stdout", ""))
        stderr = str(command_result.get("stderr", ""))
        timed_out = bool(command_result.get("timed_out"))
        status = (
            "timed_out"
            if timed_out
            else "completed"
            if command_result.get("ok")
            else "failed"
        )
        output_summary = (stdout or stderr).strip()
        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{request.host_id}",
            "tool": "ssh_root_shell",
            "host_id": request.host_id,
            "ssh_alias": str(command_result.get("ssh_alias", "")),
            "interpreter": "bash",
            "script_sha256": request.script_sha256,
            **newline_metadata,
            **policy_metadata,
            "writes_remote": True,
            "high_risk": True,
            "root_identity_verified": bool(
                command_result.get("root_identity_verified")
            ),
            "remote_state_verified": False,
            "status": status,
            "exit_code": int(command_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": output_summary,
            "summary": output_summary[-4000:] if output_summary else "SSH root shell finished",
            "remaining_risks": [
                "Soma cannot independently verify the resulting remote state"
            ],
            "error": str(command_result.get("error", "")),
            "safety_failure": False,
            "timed_out": timed_out,
            "output_truncated": bool(command_result.get("output_truncated")),
            "argv": list(command_result.get("argv", [])),
            "command_result": command_result,
        }

    def _execute_ssh_command(self, started_at: str, input_data: dict) -> dict:
        host_id = str(input_data["host_id"])
        command_id = str(input_data["command_id"])
        _, profile = resolve_ssh_command_profile(self.config, host_id, command_id)
        policy_metadata = _authorize_persisted_ssh_policy(
            input_data,
            writes_remote=profile.writes_remote,
        )
        self.event(
            "info",
            "ssh",
            "Starting allowlisted SSH command",
            {"host_id": host_id, "command_id": command_id},
        )
        command_result = run_ssh_command(self.config, host_id, command_id)
        safe_command_result = dict(redact_and_truncate(command_result))
        command_result = safe_command_result
        stdout = str(safe_command_result.get("stdout", ""))
        stderr = str(safe_command_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)

        risks: list[str] = []
        if command_result.get("timed_out"):
            risks.append("SSH command timed out; inspect saved output before retrying")
        if command_result.get("writes_remote"):
            risks.append(
                "Soma cannot independently verify the resulting remote state"
            )
        output_summary = (stdout or stderr).strip()
        summary = (
            output_summary[-4000:]
            if output_summary
            else (
                f"SSH command {command_id} completed with exit code "
                f"{command_result.get('exit_code')}"
            )
        )
        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{host_id}",
            "tool": "ssh_command",
            "host_id": host_id,
            "ssh_alias": str(command_result.get("ssh_alias", "")),
            "command_id": command_id,
            **policy_metadata,
            "writes_remote": bool(command_result.get("writes_remote")),
            "remote_state_verified": False,
            "status": "completed" if command_result.get("ok") else "failed",
            "exit_code": int(command_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": output_summary,
            "summary": summary,
            "remaining_risks": risks,
            "error": str(command_result.get("error", "")),
            "safety_failure": False,
            "timed_out": bool(command_result.get("timed_out")),
            "output_truncated": bool(command_result.get("output_truncated")),
            "argv": list(command_result.get("argv", [])),
            "command_result": command_result,
        }

    def _execute_remote_powershell(self, started_at: str, input_data: dict) -> dict:
        validated = validate_remote_powershell_durable_input(
            input_data,
            run_id=self.run_id,
            lease_generation=self.worker_lease_generation,
        )
        request = dict(validated["remote_powershell_request"])
        binding = dict(validated["remote_powershell_binding"])
        controller_state = dict(validated["remote_controller_state"])
        host_id = str(validated["host_id"])
        run_dir = Path(self.run["run_dir"])

        def on_progress(progress_updates: dict) -> None:
            current = self.store.get_run(self.run_id)
            progress = dict(current.get("progress") or {})
            progress.update(progress_updates)
            self.store.set_progress(
                self.run_id,
                phase="remote_powershell",
                progress=progress,
                elapsed_seconds=self._elapsed_seconds(),
            )

        def on_event(level: str, stage: str, data: dict) -> None:
            self.event(level, stage, "Remote PowerShell controller sample", data)

        def cancellation_check() -> bool:
            progress = dict(self.store.get_run(self.run_id).get("progress") or {})
            return bool(progress.get("cancellation_requested_at"))

        command_result = dict(
            redact_and_truncate(
                start_monitored_ssh_command(
                    self.config,
                    host_id,
                    str(binding["command_id"]),
                    run_dir=run_dir,
                    on_progress=on_progress,
                    on_event=on_event,
                    cancellation_check=cancellation_check,
                    controller_state=controller_state,
                    remote_argv=list(binding["remote_argv"]),
                    working_directory=str(request["working_directory"]),
                    environment=dict(request["environment"]),
                    stdin_bytes=decode_remote_powershell_stdin(request),
                    timeout_seconds=binding["timeout_seconds"],
                )
            )
        )
        stdout = str(command_result.get("stdout", ""))
        stderr = str(command_result.get("stderr", ""))
        self.artifacts.write_protected_text("stdout.txt", stdout)
        self.artifacts.write_protected_text("stderr.txt", stderr)

        accepted_manifest = dict(validated["remote_powershell_artifact_manifest"])
        publications: dict[str, dict[str, object]] = {}
        for stream in accepted_manifest["streams"]:
            stream_name = str(stream["stream"])
            transfer = run_ssh_transfer(
                self.config,
                host_id,
                "download",
                repo_root=run_dir,
                local_path=f"remote-{stream_name}.bin",
                remote_path=str(stream["remote_path"]),
                run_dir=run_dir,
                overwrite=True,
                confirmation=self.config.ssh.confirmation_token,
            )
            if not transfer.get("ok"):
                raise RuntimeError(
                    f"Remote PowerShell {stream_name} artifact retrieval failed: "
                    f"{transfer.get('error', 'unknown transfer failure')}"
                )
            downloaded = Path(str(transfer["local_path"]))
            destination = run_dir / str(stream["local_relative_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(downloaded, destination)
            size_bytes = destination.stat().st_size
            sha256_value = _sha256_file(destination)
            if size_bytes != int(transfer.get("download_size_bytes", -1)):
                raise RuntimeError(
                    f"Remote PowerShell {stream_name} artifact size verification failed"
                )
            if sha256_value != str(transfer.get("download_sha256", "")):
                raise RuntimeError(
                    f"Remote PowerShell {stream_name} artifact SHA-256 verification failed"
                )
            publications[stream_name] = {
                "size_bytes": size_bytes,
                "sha256": sha256_value,
            }
        artifact_manifest = complete_remote_powershell_artifact_manifest(
            accepted_manifest,
            publications=publications,
        )
        self.artifacts.write_json("remote_powershell_artifacts.json", artifact_manifest)
        probe = probe_remote_controller_state(self.config, host_id, controller_state)
        observed_result = dict(probe.get("result") or {})
        observed_evidence = observed_result.get("executable_evidence")
        if not isinstance(observed_evidence, dict):
            observed_state = dict(probe.get("state") or {})
            observed_evidence = dict(observed_state.get("execution") or {}).get(
                "observed_executable_evidence"
            )
        executable_evidence = complete_remote_powershell_executable_evidence(
            dict(validated["remote_powershell_executable_evidence"]),
            observed=dict(observed_evidence or {}),
        )
        self.artifacts.write_json(
            "remote_powershell_executable_evidence.json", executable_evidence
        )
        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{host_id}",
            "tool": "remote_powershell",
            "host_id": host_id,
            "request_fingerprint": request["request_fingerprint"],
            "artifact_manifest": artifact_manifest,
            "executable_evidence": executable_evidence,
            "remote_process": dict(command_result.get("remote_process") or {}),
            "status": str(command_result.get("status", "failed")),
            "exit_code": int(command_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": (stdout or stderr).strip(),
            "summary": (stdout or stderr).strip()[:500],
            "remaining_risks": [],
            "error": str(command_result.get("error", "")),
            "safety_failure": bool(command_result.get("safety_failure", False)),
            "timed_out": bool(command_result.get("timed_out", False)),
            "output_truncated": bool(command_result.get("output_truncated", False)),
            "argv": list(command_result.get("argv", [])),
            "command_result": command_result,
        }

    def _execute_ssh_monitored_command(self, started_at: str, input_data: dict) -> dict:
        host_id = str(input_data["host_id"])
        command_id = str(input_data["command_id"])
        _, profile = validate_monitored_command_start(
            self.config, host_id, command_id
        )
        policy_metadata = _authorize_persisted_ssh_policy(
            input_data,
            writes_remote=profile.writes_remote,
            monitored=True,
        )
        remote_controller_state = input_data.get("remote_controller_state")
        if remote_controller_state is not None:
            if not isinstance(remote_controller_state, dict):
                raise ValueError("Persisted remote-controller state contract is invalid")
            validate_remote_controller_state_contract(
                remote_controller_state,
                run_id=self.run_id,
                host_id=host_id,
                command_id=command_id,
                lease_generation=self.worker_lease_generation,
                remote_argv=list(profile.argv),
                timeout_seconds=profile.timeout_seconds,
            )
        run_dir = Path(self.run["run_dir"])
        staging_manifest = input_data.get("staging_manifest")
        staged_artifacts: list[dict[str, object]] = []
        if staging_manifest is not None:
            if not isinstance(staging_manifest, dict):
                raise ValueError("Persisted SSH staging manifest is invalid")
            _, output_paths, output_entries = validate_ssh_staging_manifest(
                run_dir,
                staging_manifest,
                tool="ssh_monitored_command",
                run_id=self.run_id,
                lease_generation=self.worker_lease_generation,
            )
        else:
            output_paths = {
                "stdout": run_dir / "stdout.txt",
                "stderr": run_dir / "stderr.txt",
            }
            output_entries = []
        self.event(
            "info",
            "ssh_monitored_command",
            "Starting monitored SSH command",
            {"host_id": host_id, "command_id": command_id},
        )

        def on_progress(progress_updates: dict) -> None:
            current = self.store.get_run(self.run_id)
            progress = dict(current.get("progress") or {})
            progress.update(progress_updates)
            self.store.set_progress(
                self.run_id,
                phase="ssh_monitored_command",
                progress=progress,
                elapsed_seconds=self._elapsed_seconds(),
            )

        def on_event(level: str, stage: str, data: dict) -> None:
            self.event(level, stage, "Monitored SSH watchdog sample", data)

        def cancellation_check() -> bool:
            progress = dict(self.store.get_run(self.run_id).get("progress") or {})
            return bool(progress.get("cancellation_requested_at"))

        command_result = dict(
            redact_and_truncate(
                start_monitored_ssh_command(
                    self.config,
                    host_id,
                    command_id,
                    run_dir=run_dir,
                    on_progress=on_progress,
                    on_event=on_event,
                    cancellation_check=cancellation_check,
                    controller_state=remote_controller_state,
                )
            )
        )
        stdout = str(command_result.get("stdout", ""))
        stderr = str(command_result.get("stderr", ""))
        self.artifacts.write_protected_text("stdout.txt", stdout)
        self.artifacts.write_protected_text("stderr.txt", stderr)
        for entry in output_entries:
            path = output_paths[str(entry["stream"])]
            staged_artifacts.append(
                {
                    **entry,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                    "invoking_run_id": self.run_id,
                    "lease_generation": self.worker_lease_generation,
                }
            )
        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{host_id}",
            "tool": "ssh_monitored_command",
            "host_id": host_id,
            "ssh_alias": str(command_result.get("ssh_alias", "")),
            "command_id": command_id,
            **policy_metadata,
            "writes_remote": bool(command_result.get("writes_remote")),
            "remote_process": dict(command_result.get("remote_process") or {}),
            "watchdog_mode": str(command_result.get("watchdog_mode", "observe_only")),
            "automatic_termination_active": bool(
                command_result.get("automatic_termination_active")
            ),
            "termination": dict(command_result.get("termination") or {}),
            "watchdog_samples": list(command_result.get("watchdog_samples") or []),
            "status": str(command_result.get("status", "failed")),
            "exit_code": int(command_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": (stdout or stderr).strip(),
            "summary": (
                (stdout or stderr).strip()
                or f"Monitored SSH command {command_id} finished"
            )[-4000:],
            "remaining_risks": [],
            "error": str(command_result.get("error", "")),
            "safety_failure": bool(command_result.get("safety_failure")),
            "timed_out": bool(command_result.get("timed_out")),
            "output_truncated": bool(command_result.get("output_truncated")),
            "command_result": command_result,
            "staged_artifacts": staged_artifacts,
        }

    def _execute_ssh_action(self, started_at: str, input_data: dict) -> dict:
        host_id = str(input_data["host_id"])
        action = str(input_data["action"])
        kwargs = {
            "target": str(input_data.get("target", "")),
            "source": str(input_data.get("source", "")),
            "destination": str(input_data.get("destination", "")),
            "path": str(input_data.get("path", "")),
            "deployment_id": str(input_data.get("deployment_id", "")),
            "command_id": str(input_data.get("command_id", "")),
            "packages": list(input_data.get("packages") or []),
            "executable": str(input_data.get("executable", "")),
            "args": list(input_data.get("args") or []),
            "force": bool(input_data.get("force", False)),
            "confirmation": str(input_data.get("confirmation", "")),
        }
        spec = build_ssh_action(self.config, host_id, action, **kwargs)
        policy_metadata = _authorize_persisted_ssh_policy(
            input_data,
            writes_remote=spec.writes_remote,
            high_risk=spec.high_risk,
        )
        self.event(
            "warning" if input_data.get("confirmation") else "info",
            "ssh_action",
            "Starting bounded SSH action",
            {"host_id": host_id, "action": action},
        )
        command_result = dict(
            redact_and_truncate(run_ssh_action(self.config, host_id, action, **kwargs))
        )
        stdout = str(command_result.get("stdout", ""))
        stderr = str(command_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)
        ended_at = _utc_now()
        risks: list[str] = []
        if command_result.get("high_risk"):
            risks.append("High-risk SSH action executed after explicit confirmation")
        if command_result.get("timed_out"):
            risks.append("SSH action timed out; inspect durable output before retrying")
        risks.append("Soma cannot independently verify the final remote state")
        output_summary = (stdout or stderr).strip()
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{host_id}",
            "tool": "ssh_action",
            "host_id": host_id,
            "action": action,
            **policy_metadata,
            "writes_remote": bool(command_result.get("writes_remote", True)),
            "high_risk": bool(command_result.get("high_risk", False)),
            "remote_state_verified": False,
            "status": "completed" if command_result.get("ok") else "failed",
            "exit_code": int(command_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": output_summary,
            "summary": output_summary[-4000:]
            if output_summary
            else f"SSH action {action} finished",
            "remaining_risks": risks,
            "error": str(command_result.get("error", "")),
            "safety_failure": False,
            "timed_out": bool(command_result.get("timed_out")),
            "output_truncated": bool(command_result.get("output_truncated")),
            "argv": list(command_result.get("argv", [])),
            "command_result": command_result,
        }

    def _execute_cloudflare_action(self, started_at: str, input_data: dict) -> dict:
        repo_name = str(input_data["repo_name"])
        profile_id = str(input_data["profile_id"])
        action = str(input_data["action"])
        canonical_repo_name, _ = authorize_cloudflare_profile(
            self.config, repo_name, profile_id
        )
        repo_root = resolve_repo(self.config, canonical_repo_name)
        self.event(
            "warning" if input_data.get("confirmation") else "info",
            "cloudflare_action",
            "Starting bounded Cloudflare action",
            {
                "repo_name": canonical_repo_name,
                "profile_id": profile_id,
                "action": action,
            },
        )
        action_result = dict(
            redact_and_truncate(
                run_cloudflare_action(
                    self.config,
                    profile_id,
                    action,
                    resource_id=str(input_data.get("resource_id", "")),
                    payload=dict(input_data.get("payload") or {}),
                    confirmation=str(input_data.get("confirmation", "")),
                    repo_root=repo_root,
                )
            )
        )
        stdout = str(action_result.get("stdout", ""))
        stderr = str(action_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)
        self.artifacts.write_json("cloudflare_result.json", action_result)
        ended_at = _utc_now()
        risks: list[str] = []
        if action_result.get("high_risk"):
            risks.append(
                "High-risk Cloudflare action executed after explicit confirmation"
            )
        risks.append(
            "Cloudflare state changed; final edge propagation is not independently verified"
        )
        output_summary = (stdout or stderr).strip()
        return {
            "run_id": self.run_id,
            "repo_name": canonical_repo_name,
            "tool": "cloudflare_action",
            "cloudflare_profile_id": profile_id,
            "profile_id": profile_id,
            "action": action,
            "writes_remote": True,
            "high_risk": bool(action_result.get("high_risk", False)),
            "remote_state_verified": False,
            "status": "completed" if action_result.get("ok") else "failed",
            "exit_code": int(action_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": action_result,
            "summary": output_summary[-4000:]
            if output_summary
            else f"Cloudflare action {action} finished",
            "remaining_risks": risks,
            "error": str(action_result.get("error", "")),
            "safety_failure": False,
            "timed_out": bool(action_result.get("timed_out")),
            "output_truncated": bool(action_result.get("output_truncated")),
            "method": str(action_result.get("method", "")),
            "path": str(action_result.get("path", "")),
            "cloudflare_result": action_result,
        }

    def _execute_ssh_transfer(self, started_at: str, input_data: dict) -> dict:
        host_id = str(input_data["host_id"])
        run_dir = Path(self.run["run_dir"])
        direction, repo_root, writes_remote, high_risk = (
            _validate_ssh_transfer_worker_input(
                self.config,
                input_data,
                run_dir,
            )
        )
        policy_metadata = _authorize_persisted_ssh_policy(
            input_data,
            writes_remote=writes_remote,
            high_risk=high_risk,
        )
        self.event(
            "warning" if input_data.get("overwrite") else "info",
            "ssh_transfer",
            "Starting bounded SSH transfer",
            {"host_id": host_id, "direction": direction},
        )
        transfer_result = dict(
            redact_and_truncate(
                run_ssh_transfer(
                    self.config,
                    host_id,
                    direction,
                    repo_root=repo_root,
                    local_path=str(input_data.get("local_path", "")),
                    remote_path=str(input_data.get("remote_path", "")),
                    run_dir=run_dir,
                    recursive=bool(input_data.get("recursive", False)),
                    overwrite=bool(input_data.get("overwrite", False)),
                    confirmation=str(input_data.get("confirmation", "")),
                )
            )
        )
        stdout = str(transfer_result.get("stdout", ""))
        stderr = str(transfer_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)
        self.artifacts.write_json("transfer_result.json", transfer_result)
        ended_at = _utc_now()
        risks: list[str] = []
        if direction == "upload":
            risks.append(
                "Upload changed remote state; final remote state is not independently verified"
            )
        if transfer_result.get("timed_out"):
            risks.append("SSH transfer timed out; inspect artifacts before retrying")
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{host_id}",
            "tool": "ssh_transfer",
            "host_id": host_id,
            "direction": direction,
            **policy_metadata,
            "writes_remote": writes_remote,
            "high_risk": high_risk,
            "status": "completed" if transfer_result.get("ok") else "failed",
            "exit_code": int(transfer_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": transfer_result,
            "summary": (
                f"SSH {direction} completed: {transfer_result.get('destination', '')}"
                if transfer_result.get("ok")
                else f"SSH {direction} failed"
            ),
            "remaining_risks": risks,
            "error": str(transfer_result.get("error", "")),
            "safety_failure": False,
            "timed_out": bool(transfer_result.get("timed_out")),
            "output_truncated": bool(transfer_result.get("output_truncated")),
            "transfer_result": transfer_result,
        }

    def _execute_ssh_profile_activation(
        self, started_at: str, input_data: dict
    ) -> dict:
        change_id = str(input_data.get("change_id") or "").strip()
        if not change_id:
            raise ValueError("SSH profile activation input is missing change_id")
        self.event(
            "info",
            "ssh_profile_activation",
            "Starting durable SSH profile activation",
            {
                "change_id": change_id,
                "host_id": str(input_data.get("host_id") or ""),
                "activation_intent": str(
                    input_data.get("activation_intent") or ""
                ),
            },
        )
        activation_result = run_ssh_profile_activation(
            self.config_path,
            self.config.resolve_runs_dir(),
            change_id,
            self.run_id,
        )
        self.artifacts.write_json(
            "ssh_profile_activation_result.json", activation_result
        )
        ended_at = _utc_now()
        ok = bool(activation_result.get("ok"))
        state = str(activation_result.get("activation_state") or "")
        remaining_risks: list[str] = []
        if state == "RECOVERY_REQUIRED":
            remaining_risks.append(
                "SSH profile activation could not prove rollback; inspect transaction evidence before retrying"
            )
        elif state == "ROLLED_BACK":
            remaining_risks.append(
                "Candidate activation failed and local state was rolled back"
            )
        self.event(
            "info" if ok else "warning",
            "ssh_profile_activation",
            "Durable SSH profile activation finished",
            {
                "change_id": change_id,
                "activation_state": state,
                "ok": ok,
            },
        )
        return {
            "run_id": self.run_id,
            "repo_name": "__soma_config__",
            "tool": "ssh_profile_activation",
            "change_id": change_id,
            "host_id": str(input_data.get("host_id") or ""),
            "activation_intent": str(
                input_data.get("activation_intent") or ""
            ),
            "status": "completed" if ok else "failed",
            "exit_code": 0 if ok else 1,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": activation_result,
            "summary": (
                "SSH profile activation completed transactionally"
                if ok
                else f"SSH profile activation ended {state or 'failed'}"
            ),
            "remaining_risks": remaining_risks,
            "error": str(activation_result.get("error") or ""),
            "safety_failure": state == "RECOVERY_REQUIRED",
            "timed_out": False,
            "output_truncated": False,
            "activation_result": activation_result,
        }

    def _execute_ssh_deployment(self, started_at: str, input_data: dict) -> dict:
        host_id = str(input_data["host_id"])
        deployment_id = str(input_data["deployment_id"])
        run_dir = Path(self.run["run_dir"])
        deployment, repo_root = _validate_ssh_deployment_worker_input(
            self.config,
            input_data,
            self.run_id,
        )
        policy_metadata = _authorize_persisted_ssh_policy(
            input_data,
            writes_remote=True,
            high_risk=True,
        )
        self.event(
            "warning",
            "ssh_deployment",
            "Starting confirmed archive deployment",
            {
                "host_id": host_id,
                "deployment_id": deployment_id,
                "repo_name": deployment.repo_name,
            },
        )
        deployment_result = dict(
            redact_and_truncate(
                run_ssh_deployment(
                    self.config,
                    host_id,
                    deployment_id,
                    repo_root=repo_root,
                    run_dir=run_dir,
                    run_id=self.run_id,
                    confirmation=str(input_data.get("confirmation", "")),
                )
            )
        )
        self.artifacts.write_json("deployment_result.json", deployment_result)
        stdout = str(deployment_result.get("stdout", ""))
        stderr = str(deployment_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)
        ended_at = _utc_now()
        risks = [
            "Deployment changed remote state; inspect deployment steps and health output",
            "Soma cannot independently prove application-level correctness",
        ]
        if deployment_result.get("timed_out"):
            risks.append(
                "Deployment timed out; do not retry before checking the active release"
            )
        return {
            "run_id": self.run_id,
            "repo_name": f"ssh:{host_id}",
            "tool": "ssh_deployment",
            "host_id": host_id,
            "deployment_id": deployment_id,
            "source_repo_name": deployment.repo_name,
            **policy_metadata,
            "writes_remote": True,
            "high_risk": True,
            "status": "completed" if deployment_result.get("ok") else "failed",
            "exit_code": int(deployment_result.get("exit_code", 1)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": deployment_result.get("steps", []),
            "summary": (
                f"Deployment {deployment_id} completed"
                if deployment_result.get("ok")
                else str(deployment_result.get("error", "Deployment failed"))
            ),
            "remaining_risks": risks,
            "error": str(deployment_result.get("error", "")),
            "safety_failure": False,
            "timed_out": bool(deployment_result.get("timed_out")),
            "output_truncated": bool(deployment_result.get("output_truncated")),
            "deployment_result": deployment_result,
        }

    def _execute_external_fixture_validation(
        self,
        started_at: str,
        repo_name: str,
        input_data: dict,
    ) -> dict:
        run_dir = Path(self.run["run_dir"])
        self.event(
            "info",
            "external_fixture",
            "Fetching hash-pinned external fixture",
            {"validation": str(input_data.get("validation", "none"))},
        )
        fixture_result = fetch_validate_and_discard(
            self.config.external_fixtures,
            url=str(input_data["url"]),
            expected_sha256=str(input_data["expected_sha256"]),
            validation=str(input_data.get("validation", "none")),
            run_dir=run_dir,
        )
        self.artifacts.write_json("external_fixture_result.json", fixture_result)
        ended_at = _utc_now()
        ok = bool(fixture_result.get("ok"))
        return {
            "run_id": self.run_id,
            "repo_name": repo_name,
            "tool": "external_fixture_validation",
            "status": "completed" if ok else "failed",
            "exit_code": 0 if ok else 1,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [str(input_data.get("validation", "none"))],
            "test_results": fixture_result,
            "summary": (
                "External fixture hash verified, validated, and discarded"
                if ok
                else "External fixture validation failed and the fixture was discarded"
            ),
            "remaining_risks": [],
            "error": str(fixture_result.get("error", "")),
            "safety_failure": False,
            "fixture": fixture_result,
        }

    def _execute_docker_action(
        self,
        started_at: str,
        repo_name: str,
        repo_root: Path,
        input_data: dict,
    ) -> dict:
        _, repo_config = resolve_repo_config(self.config, repo_name)
        kwargs = {
            "target": str(input_data.get("target", "")),
            "destination": str(input_data.get("destination", "")),
            "services": list(input_data.get("services") or []),
            "command_id": str(input_data.get("command_id", "")),
            "context": str(input_data.get("context", ".")),
            "dockerfile": str(input_data.get("dockerfile", "")),
            "build": bool(input_data.get("build", False)),
            "force": bool(input_data.get("force", False)),
            "confirmation": str(input_data.get("confirmation", "")),
        }
        action = str(input_data["action"])
        spec = build_docker_action(
            self.config, repo_root, repo_config, action, **kwargs
        )
        git_before = git_tools.git_status(repo_root)
        diff_before = git_tools.diff_stat(repo_root)
        dirty_before = git_tools.changed_files(repo_root)
        workspace_before = snapshot_workspace(
            repo_root, [self.config.resolve_runs_dir()]
        )
        self.artifacts.write_text("git_before.txt", git_before)
        self.event(
            "warning" if spec.high_risk else "info",
            "docker",
            "Starting bounded Docker action",
            {
                "action": action,
                "high_risk": spec.high_risk,
                "timeout_seconds": spec.timeout_seconds,
            },
        )
        command_result = run_docker_action(
            self.config, repo_root, repo_config, action, **kwargs
        )
        stdout = str(command_result.get("stdout", ""))
        stderr = str(command_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)

        git_after = git_tools.git_status(repo_root)
        diff_after = git_tools.diff_stat(repo_root)
        changed_after = git_tools.changed_files(repo_root)
        workspace_after = snapshot_workspace(
            repo_root, [self.config.resolve_runs_dir()]
        )
        introduced_changes, preserved_preexisting_changes = classify_git_attribution(
            changed_after, workspace_before, workspace_after, dirty_before
        )
        self.artifacts.write_text("git_after.txt", git_after)
        self.artifacts.write_text("diff_stat.txt", diff_after)

        safety_failure = bool(
            not spec.writes_files
            and (git_before != git_after or diff_before != diff_after)
        )
        risks: list[str] = []
        if spec.high_risk:
            risks.append("High-risk Docker action executed after explicit confirmation")
        if safety_failure:
            risks.append("Docker action unexpectedly changed repository state")
        if command_result.get("timed_out"):
            risks.append(
                "Docker action timed out; inspect durable output before retrying"
            )

        terminal_status = (
            "timed_out"
            if command_result.get("timed_out")
            else "completed"
            if command_result.get("ok") and not safety_failure
            else "failed"
        )
        commit_data = {
            "commit_required": False,
            "commit_attempted": False,
            "commit_hash": "",
            "commit_error": "",
            "commit_result": {"ok": True, "reason": "not_applicable"},
        }
        if terminal_status == "completed" and spec.writes_files:
            commit_data = self._finalize_commit(
                repo_root, introduced_changes, tool_name="docker_action"
            )
            git_after = git_tools.git_status(repo_root)
            diff_after = git_tools.diff_stat(repo_root)
            if commit_data["commit_attempted"] and commit_data["commit_error"]:
                terminal_status = "failed"
                risks.append(
                    f"Automatic commit finalization failed: {commit_data['commit_error']}"
                )

        output_summary = (stdout or stderr).strip()
        ended_at = _utc_now()
        return {
            "run_id": self.run_id,
            "repo_name": repo_name,
            "tool": "docker_action",
            "action": action,
            "status": terminal_status,
            "exit_code": int(command_result.get("exit_code", 1)),
            "stdout": stdout,
            "stderr": stderr,
            "process_success": int(command_result.get("exit_code", 1)) == 0,
            "classification": (
                "timeout"
                if command_result.get("timed_out")
                else "process_failure"
                if int(command_result.get("exit_code", 1)) != 0
                else "semantic_failure"
                if safety_failure
                else "success"
            ),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": introduced_changes,
            "introduced_changes": introduced_changes,
            "preserved_preexisting_changes": preserved_preexisting_changes,
            "git_status": git_after,
            "diff_stat": diff_after,
            "tests_run": [],
            "test_results": output_summary,
            "summary": output_summary[-4000:]
            if output_summary
            else f"Docker action {action} finished",
            "remaining_risks": risks,
            "error": commit_data["commit_error"]
            or str(command_result.get("error", "")),
            "safety_failure": safety_failure,
            "timed_out": bool(command_result.get("timed_out")),
            "output_truncated": bool(command_result.get("output_truncated")),
            "argv": list(command_result.get("argv", [])),
            "high_risk": spec.high_risk,
            "writes_files": spec.writes_files,
            "command_result": command_result,
            **commit_data,
        }

    def _execute_repo_apply(
        self,
        started_at: str,
        repo_name: str,
        repo_root: Path,
        input_data: dict,
    ) -> dict:
        operation = str(input_data["operation"])
        runs_dir = self.config.resolve_runs_dir()
        if operation == "previewed_change":
            result = repo_writer.apply_previewed_repo_change(
                repo_root, str(input_data["patch_id"]), runs_dir
            )
        elif operation == "cleanup":
            result = apply_managed_artifact_cleanup(
                repo_root, runs_dir, str(input_data["cleanup_id"])
            )
        elif operation == "revert":
            result = repo_writer.revert_managed_patch(
                repo_root, str(input_data["patch_id"]), runs_dir
            )
        else:
            result = repo_writer.move_repo_file(
                repo_root,
                str(input_data["source_path"]),
                str(input_data["destination_path"]),
                str(input_data["expected_sha256"]),
                runs_dir,
            )
        result = dict(result)
        result["run_id"] = self.run_id
        result["operation"] = operation
        result["started_at"] = started_at
        if result.get("ok") and result.get("changed_files"):
            commit_data = self._finalize_commit(
                repo_root,
                list(result["changed_files"]),
                tool_name="repo_apply",
                commit_title=str(result.get("commit_title") or ""),
                commit_description=str(result.get("commit_description") or ""),
            )
            result.update(commit_data)
            if commit_data.get("commit_attempted") and commit_data.get("commit_error"):
                result["ok"] = False
                result["status"] = "commit_failed"
                result["error"] = commit_data["commit_error"]
            else:
                result["wiki_freshness"] = self._mark_wiki_stale_with_evidence(
                    repo_root, repo_name, reason="repo_apply"
                )
        result.setdefault("status", "completed" if result.get("ok") else "failed")
        if result["status"] not in TERMINAL_STATUSES:
            result["status"] = "completed" if result.get("ok") else "failed"
        result.setdefault("error", "")
        ended_at = str(result.get("ended_at") or _utc_now())
        result["ended_at"] = ended_at
        result.setdefault("duration_seconds", _duration(started_at, ended_at))
        result.setdefault("exit_code", 0 if result["status"] == "completed" else 1)
        result.setdefault("process_success", result["exit_code"] == 0)
        result.setdefault(
            "classification",
            "success" if result["status"] == "completed" else "semantic_failure",
        )
        result.setdefault(
            "summary",
            result.get("error")
            or f"Repository apply {operation} {result['status']}",
        )
        result.setdefault("remaining_risks", [])
        result.setdefault("safety_failure", False)
        return result

    def _execute_project_command(
        self,
        started_at: str,
        repo_name: str,
        repo_root: Path,
        input_data: dict,
    ) -> dict:
        command_id = str(input_data["command_id"])
        normalized_target = ""
        if command_id == PYTEST_PATH_COMMAND_ID:
            normalized_target = build_pytest_path_profile(
                repo_root, str(input_data["path"])
            ).argv[-1]
            profile = build_pytest_path_profile(repo_root, normalized_target)
        elif command_id == PY_COMPILE_PATH_COMMAND_ID:
            normalized_target = build_py_compile_path_profile(
                repo_root, str(input_data["path"])
            ).argv[-1]
            profile = build_py_compile_path_profile(repo_root, normalized_target)
        elif command_id == BASH_N_PATH_COMMAND_ID:
            normalized_target = build_bash_n_path_profile(
                repo_root, str(input_data["path"])
            ).argv[-1]
            profile = build_bash_n_path_profile(repo_root, normalized_target)
        elif command_id == JSON_VALIDATE_PATH_COMMAND_ID:
            normalized_target = build_json_validate_path_profile(
                repo_root, str(input_data["path"])
            ).argv[-1]
            profile = build_json_validate_path_profile(repo_root, normalized_target)
        elif command_id == GIT_READONLY_COMMAND_ID:
            normalized_target = str(input_data.get("operation", ""))
            profile = build_git_readonly_profile(normalized_target)
        else:
            _, repo_config = resolve_repo_config(self.config, repo_name)
            repo_profiles = list(repo_config.command_profiles or [])
            profile = resolve_command_profile(command_id, repo_profiles)
        requested_timeout = input_data.get("timeout_seconds")
        if requested_timeout is not None:
            timeout_value = int(requested_timeout)
            if timeout_value < 1 or timeout_value > 604_800:
                raise ValueError("validator timeout_seconds must be between 1 and 604800")
            profile.timeout_seconds = timeout_value
        run_dir = Path(self.run["run_dir"])
        temp_root = run_dir / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        extra_env = {
            "TMP": str(temp_root),
            "TEMP": str(temp_root),
            "TMPDIR": str(temp_root),
        }
        pytest_temp = run_dir / "pytest-tmp"
        if command_id in {"pytest", PYTEST_PATH_COMMAND_ID} or "pytest" in profile.argv:
            pytest_temp.mkdir(parents=True, exist_ok=True)
            existing_addopts = os.environ.get("PYTEST_ADDOPTS", "").strip()
            basetemp = f'--basetemp="{pytest_temp.as_posix()}"'
            extra_env["PYTEST_ADDOPTS"] = " ".join(
                value for value in (existing_addopts, basetemp) if value
            )

        git_before = git_tools.git_status(repo_root)
        diff_before = git_tools.diff_stat(repo_root)
        dirty_before = git_tools.changed_files(repo_root)
        workspace_before = snapshot_workspace(
            repo_root, [self.config.resolve_runs_dir()]
        )
        self.artifacts.write_text("git_before.txt", git_before)
        self.event(
            "info",
            "command",
            "Starting allowlisted project command",
            {
                "command_id": command_id,
                "timeout_seconds": profile.timeout_seconds,
                "temporary_directory": str(temp_root),
                "path": normalized_target,
            },
        )
        command_result = run_command_profile(profile, repo_root, extra_env=extra_env)
        stdout = str(command_result.get("stdout", ""))
        stderr = str(command_result.get("stderr", ""))
        self.artifacts.write_text("stdout.txt", stdout)
        self.artifacts.write_text("stderr.txt", stderr)

        git_after = git_tools.git_status(repo_root)
        diff_after = git_tools.diff_stat(repo_root)
        changed_after = git_tools.changed_files(repo_root)
        workspace_after = snapshot_workspace(
            repo_root, [self.config.resolve_runs_dir()]
        )
        introduced_changes, preserved_preexisting_changes = classify_git_attribution(
            changed_after, workspace_before, workspace_after, dirty_before
        )
        self.artifacts.write_text("git_after.txt", git_after)
        self.artifacts.write_text("diff_stat.txt", diff_after)

        safety_failure = bool(
            not profile.writes_files
            and (git_before != git_after or diff_before != diff_after)
        )
        risks: list[str] = []
        if safety_failure:
            risks.append("Read-only command changed repository state")
        if command_result.get("timed_out"):
            risks.append(
                "Project command timed out; inspect saved output before retrying"
            )

        output_summary = (stdout or stderr).strip()
        summary = (
            output_summary[-4000:]
            if output_summary
            else (
                f"Project command {command_id} completed with exit code "
                f"{command_result.get('exit_code')}"
            )
        )
        errors = [str(command_result.get("error", "")).strip()]
        if safety_failure:
            errors.append("Read-only command changed repository state")
        error = "; ".join(item for item in errors if item)
        commit_data = {
            "commit_required": False,
            "commit_attempted": False,
            "commit_hash": "",
            "commit_error": "",
            "commit_result": {
                "ok": True,
                "reason": "not_applicable",
            },
        }
        terminal_status = (
            "timed_out"
            if command_result.get("timed_out")
            else "completed"
            if command_result.get("ok") and not safety_failure
            else "failed"
        )
        if terminal_status == "completed" and profile.writes_files:
            commit_data = self._finalize_commit(
                repo_root,
                introduced_changes,
                tool_name="project_command",
            )
            git_after = git_tools.git_status(repo_root)
            diff_after = git_tools.diff_stat(repo_root)
            changed_after = git_tools.changed_files(repo_root)
            if commit_data["commit_attempted"] and commit_data["commit_error"]:
                terminal_status = "failed"
                risks.append(
                    f"Automatic commit finalization failed: {commit_data['commit_error']}"
                )

        validation = None
        if command_id in {
            PY_COMPILE_PATH_COMMAND_ID,
            BASH_N_PATH_COMMAND_ID,
            JSON_VALIDATE_PATH_COMMAND_ID,
        }:
            target_analysis = analyze_text_file(repo_root / normalized_target)
            validation = {
                "ok": int(command_result.get("exit_code", 1)) == 0,
                "error_count": 0 if int(command_result.get("exit_code", 1)) == 0 else 1,
                "representative_errors": [str(stderr).strip()[:1024]]
                if str(stderr).strip()
                else [],
                "truncated": len(str(stderr).encode("utf-8")) > 1024,
                "target_sha256": target_analysis["sha256"],
                "target_size_bytes": target_analysis["size_bytes"],
                "target_total_lines": target_analysis["total_lines"],
                "newline_diagnostic": target_analysis["newline_diagnostic"],
            }

        ended_at = _utc_now()
        tests_run = (
            [f"{command_id}:{normalized_target}"] if normalized_target else [command_id]
        )
        return {
            "run_id": self.run_id,
            "repo_name": repo_name,
            "tool": "project_command",
            "command_id": command_id,
            "path": normalized_target,
            "status": terminal_status,
            "exit_code": int(command_result.get("exit_code", 1)),
            "stdout": stdout,
            "stderr": stderr,
            "process_success": int(command_result.get("exit_code", 1)) == 0,
            "classification": (
                "timeout"
                if command_result.get("timed_out")
                else "process_failure"
                if int(command_result.get("exit_code", 1)) != 0
                else "semantic_failure"
                if safety_failure
                else "success"
            ),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": introduced_changes,
            "introduced_changes": introduced_changes,
            "preserved_preexisting_changes": preserved_preexisting_changes,
            "git_status": git_after,
            "diff_stat": diff_after,
            "tests_run": tests_run,
            "test_results": output_summary,
            "summary": summary,
            "remaining_risks": risks,
            "error": commit_data["commit_error"] or error,
            "safety_failure": safety_failure,
            "timed_out": bool(command_result.get("timed_out")),
            "output_truncated": bool(command_result.get("output_truncated")),
            "validation": validation,
            "argv": list(command_result.get("argv", [])),
            "temporary_directory": str(temp_root),
            "pytest_basetemp": str(pytest_temp) if pytest_temp.exists() else "",
            "command_result": command_result,
            **commit_data,
        }

    def _error_result(self, started_at: str, ended_at: str, exc: Exception) -> dict:
        return {
            "run_id": self.run_id,
            "repo_name": self.run.get("repo_name", ""),
            "tool": self.run.get("tool", ""),
            "status": "failed",
            "exit_code": 1,
            "stdout": "",
            "stderr": "",
            "process_success": False,
            "classification": "infrastructure_failure",
            "cancelled": False,
            "timed_out": False,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration(started_at, ended_at),
            "changed_files": [],
            "git_status": "",
            "diff_stat": "",
            "tests_run": [],
            "test_results": "",
            "summary": str(exc),
            "remaining_risks": ["Async worker failed"],
            "error": str(exc),
            "safety_failure": True,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a queued Soma job.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--lease-token", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config).resolve()
    worker = JobWorker(
        config_path, args.run_id, lease_token=args.lease_token
    )
    exit_code = worker.execute()
    try:
        config = load_config(config_path)

        def spawn_worker(run_id: str, lease_token: str) -> subprocess.Popen:
            return subprocess.Popen(
                [
                    os.sys.executable,
                    "-m",
                    "soma.job_worker",
                    "--config",
                    str(config_path),
                    "--run-id",
                    run_id,
                    "--lease-token",
                    lease_token,
                ],
                cwd=Path.cwd(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=os.name != "nt",
                **process_group_popen_kwargs(),
            )

        from .job_manager import JobManager

        JobManager(config, config_path).enforce_powershell_group_failure_policy(
            args.run_id
        )
        refill_powershell_groups(config=config, spawn_worker=spawn_worker)
    except Exception:
        # Refill is restart-reconciled; never mask the completed child's exit state.
        pass
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
