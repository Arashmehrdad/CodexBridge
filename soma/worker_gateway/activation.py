"""Controlled V3-2 loopback activation proof.

This module is deliberately inert on import. ``run_activation`` mutates the live
Soma durable store only when ``execute=True`` and never changes the owner MCP,
Cloudflare, firewall, provider, or deployment configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing
import os
import re
import socket
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

import httpx
import uvicorn
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.client.transports import StreamableHttpTransport

from soma.capabilities import schema_hash
from soma.config import load_config
from soma.job_manager import make_run_id
from soma.project_scope import ProjectScopeStore
from soma.run_store import RunStore
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    TaskPhase,
    TaskState,
    make_task_id,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.store import TaskStore
from soma.worker_authority import (
    WorkerAuthorityService,
    WorkerCapabilityGrantIssueV1,
    WorkerOperationRegistry,
    WorkerOperationSpecV1,
    WorkerPrincipalIssueV1,
)
from soma.worker_authority.models import canonical_hash
from soma.worker_authority.store import WorkerAuthorityStore

from .transport import (
    WorkerDispatchContext,
    WorkerOperationDispatchRegistry,
    build_worker_mcp,
    make_worker_bearer,
)


EXPECTED_OWNER_TOOL_COUNT: Final[int] = 34
EXPECTED_OWNER_PUBLIC_SCHEMA_HASH: Final[str] = (
    "00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9"
)
ACTIVATION_OPERATION_REF: Final[str] = "worker-operation:v3-2-loopback-activation"
ACTIVATION_PARAMETER_CONTRACT: Final[dict[str, str]] = {"probe": "v3-2-loopback"}
ACTIVATION_ISSUER_REF: Final[str] = "owner-controller:v3-2-loopback-activation"
ACTIVATION_HOST: Final[str] = "127.0.0.1"
DEFAULT_OWNER_MCP_URL: Final[str] = "http://127.0.0.1:8000/mcp"


class ActivationError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(now: datetime | None = None) -> str:
    return (now or _utc_now()).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sqlite_backup(source_path: Path, destination_path: Path) -> dict[str, Any]:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(source_path, timeout=10)
    destination = sqlite3.connect(destination_path, timeout=10)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return {
        "path": str(destination_path),
        "size_bytes": destination_path.stat().st_size,
        "sha256": _sha256_file(destination_path),
    }


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((ACTIVATION_HOST, 0))
        return int(probe.getsockname()[1])


def _listening_rows(port: int) -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^\s*TCP\s+(\S+):(\d+)\s+(\S+)\s+LISTENING\s+(\d+)\s*$",
        re.IGNORECASE,
    )
    for line in completed.stdout.splitlines():
        match = pattern.match(line)
        if not match or int(match.group(2)) != int(port):
            continue
        rows.append(
            {
                "local_address": match.group(1),
                "port": int(match.group(2)),
                "remote": match.group(3),
                "pid": int(match.group(4)),
            }
        )
    return rows


def _wait_for_listener(port: int, pid: int, timeout_seconds: float = 15.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        rows = _listening_rows(port)
        matching = [row for row in rows if row["pid"] == pid]
        if matching:
            addresses = {str(row["local_address"]) for row in matching}
            if addresses != {ACTIVATION_HOST}:
                raise ActivationError(
                    f"worker listener escaped loopback isolation: {sorted(addresses)}"
                )
            return {"pid": pid, "port": port, "addresses": sorted(addresses)}
        time.sleep(0.2)
    raise ActivationError("worker loopback listener did not become ready")


def _wait_for_port_closed(port: int, timeout_seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _listening_rows(port):
            return True
        time.sleep(0.2)
    return not _listening_rows(port)


def _input_schema_hash(actions: list[dict[str, Any]]) -> str:
    schemas = {
        str(action.get("name", "")): action.get("inputSchema", {})
        for action in actions
        if str(action.get("name", ""))
    }
    return schema_hash(schemas)


async def _owner_identity(owner_mcp_url: str) -> dict[str, Any]:
    transport = StreamableHttpTransport(owner_mcp_url)
    async with Client(transport) as client:
        tools = await client.list_tools()
    actions = [tool.model_dump(mode="json", by_alias=True) for tool in tools]
    names = sorted(str(action.get("name", "")) for action in actions)
    return {
        "tool_count": len(actions),
        "tool_names": names,
        "public_schema_hash": _input_schema_hash(actions),
    }


def _assert_owner_identity(identity: dict[str, Any]) -> None:
    if int(identity.get("tool_count", -1)) != EXPECTED_OWNER_TOOL_COUNT:
        raise ActivationError(
            f"owner MCP tool count changed: {identity.get('tool_count')}"
        )
    if identity.get("public_schema_hash") != EXPECTED_OWNER_PUBLIC_SCHEMA_HASH:
        raise ActivationError(
            "owner MCP public schema hash differs from accepted V3-2 baseline"
        )


def _http_status_codes(exc: BaseException) -> set[int]:
    codes: set[int] = set()
    if isinstance(exc, httpx.HTTPStatusError):
        codes.add(exc.response.status_code)
    for nested in getattr(exc, "exceptions", ()):
        if isinstance(nested, BaseException):
            codes.update(_http_status_codes(nested))
    return codes


async def _worker_call(
    worker_url: str,
    bearer: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    transport = StreamableHttpTransport(worker_url, auth=BearerAuth(bearer))
    async with Client(transport) as client:
        result = await client.call_tool(tool_name, arguments)
    payload = result.structured_content
    if not isinstance(payload, dict):
        raise ActivationError(f"worker {tool_name} returned no structured object")
    return payload


async def _expect_auth_denial(worker_url: str, bearer: str) -> set[int]:
    transport = StreamableHttpTransport(worker_url, auth=BearerAuth(bearer))
    try:
        async with Client(transport):
            raise ActivationError("invalid worker authentication unexpectedly connected")
    except ActivationError:
        raise
    except Exception as exc:
        codes = _http_status_codes(exc)
        if 401 not in codes:
            raise ActivationError(
                f"worker authentication denial did not contain HTTP 401: {sorted(codes)}"
            ) from exc
        return codes


def _journal_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _worker_server_child(
    runs_dir: str,
    port: int,
    journal_path: str,
) -> None:
    spec = WorkerOperationSpecV1(
        operation_ref=ACTIVATION_OPERATION_REF,
        operation_kind="query",
        requires_session=False,
        allowed_task_states=(TaskState.RUNNING.value,),
        description="V3-2 loopback activation proof query.",
    )
    registry = WorkerOperationRegistry((spec,))
    authority = WorkerAuthorityService(Path(runs_dir), registry=registry)
    dispatch = WorkerOperationDispatchRegistry(registry)
    journal = Path(journal_path)

    def activation_handler(context: WorkerDispatchContext) -> dict[str, Any]:
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "controller_request_id": context.controller_request_id,
                        "grant_id": context.grant.grant_id,
                        "operation_ref": context.decision.operation_ref,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        return {
            "activation": "ok",
            "operation_ref": context.decision.operation_ref,
            "parameters": dict(context.parameters),
        }

    dispatch.register(ACTIVATION_OPERATION_REF, activation_handler)
    worker = build_worker_mcp(authority, dispatch)
    asgi = worker.http_app(path="/mcp", stateless_http=True)
    uvicorn.run(
        asgi,
        host=ACTIVATION_HOST,
        port=port,
        log_level="warning",
        access_log=False,
    )


def _terminate_process(process: multiprocessing.Process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(timeout=10)
    if process.is_alive():
        process.kill()
        process.join(timeout=5)


def _make_disposable_scope(
    *,
    runs_dir: Path,
    activation_dir: Path,
    suffix: str,
) -> dict[str, Any]:
    repo_dir = activation_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=False)
    git = subprocess.run(
        ["git", "init", "-q", str(repo_dir)],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if git.returncode != 0:
        raise ActivationError(f"git init failed: {git.stderr.strip()}")

    project_id = f"Project_V32WorkerActivation_{suffix}"
    resource_id = f"Resource_V32WorkerActivation_{suffix}"
    repo_name = f"v3_2_worker_activation_{suffix.lower()}"
    scope = ProjectScopeStore(runs_dir)
    bootstrap = scope.apply_bootstrap(
        project_id=project_id,
        project_key=f"v3-2-worker-activation-{suffix.lower()}",
        resource_id=resource_id,
        repo_name=repo_name,
        repository_root=repo_dir,
        access_mode="exclusive",
    )
    binding = scope.resolve_repository(
        project_id=project_id,
        repo_name=repo_name,
        repository_root=repo_dir,
    )
    return {
        "scope": scope,
        "binding": binding,
        "bootstrap": bootstrap,
        "project_id": project_id,
        "resource_id": resource_id,
        "repo_name": repo_name,
        "repo_dir": repo_dir,
    }


def _make_disposable_task_run(
    *,
    runs_dir: Path,
    scope: ProjectScopeStore,
    binding: Any,
    repo_name: str,
    activation_dir: Path,
    suffix: str,
) -> tuple[str, str, int]:
    run_id = make_run_id("worker_activation")
    task_id = make_task_id()
    normalized = normalize_durable_command_request(
        repo_name=repo_name,
        profile_id="v3_2_worker_activation",
        argv=["loopback-proof", suffix],
    )
    task_store = TaskStore(runs_dir)
    task_kwargs = {
        "task_id": task_id,
        "task_kind": TaskKind.DURABLE_COMMAND.value,
        "controller_request_id": f"v3-2-worker-activation-task-{suffix}",
        "request_hash": normalized_request_hash(normalized),
        "backend_kind": BackendKind.SOMA_DURABLE_RUN.value,
        "backend_executor": "worker_activation",
        "backend_ref": run_id,
        "backend_identity": {
            "engine": BackendKind.SOMA_DURABLE_RUN.value,
            "run_tool": "worker_activation",
            "repo_name": repo_name,
            "activation_suffix": suffix,
        },
        "objective_ref": f"activation:{suffix}:objective",
        "constraints_ref": f"activation:{suffix}:loopback-only",
        "workspace_kind": "repository",
        "workspace_ref": repo_name,
    }
    with task_store.transaction() as conn:
        scope.reserve_task_attempt(
            conn,
            binding=binding,
            task_id=task_id,
            run_id=run_id,
        )
        task, created = task_store.reserve_task_in_connection(conn, **task_kwargs)
        if not created:
            raise ActivationError("disposable activation Task unexpectedly replayed")
        scope.attach_task(conn, task.task_id)

    run_store = RunStore(runs_dir)
    run_store.create_run(
        run_id=run_id,
        repo_name=repo_name,
        tool="worker_activation",
        run_dir=activation_dir / "durable_run",
        input_data={
            "activation": "v3-2-worker-gateway",
            "project_id": binding.project_id,
            "resource_id": binding.resource_id,
        },
        status="running",
    )
    scope.attach_attempt(run_id, backend_kind=BackendKind.SOMA_DURABLE_RUN.value)
    running = task_store.conditional_update(
        task_id,
        fields={
            "state": TaskState.RUNNING.value,
            "phase": TaskPhase.BACKEND_RUNNING.value,
            "started_at": _utc_now().isoformat(),
        },
        expected_state_version=0,
        expected_states=(TaskState.ACCEPTED.value,),
    )
    if running is None:
        raise ActivationError("disposable activation Task failed to enter running state")
    verified_scope = scope.require_task_attempt(binding.project_id, task_id, run_id)
    if verified_scope.binding_status != "attached" or verified_scope.attempt_status != "attached":
        raise ActivationError("disposable activation Task/Run scope is not attached")
    return task_id, run_id, running.state_version


def _terminalize_task_run(
    runs_dir: Path,
    task_id: str,
    run_id: str,
    *,
    success: bool,
    summary: str,
) -> None:
    now = _utc_now().isoformat()
    task_store = TaskStore(runs_dir)
    try:
        task = task_store.get_task(task_id)
        if task.state not in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
            target = TaskState.COMPLETED if success else TaskState.FAILED
            task_store.conditional_update(
                task_id,
                fields={
                    "state": target.value,
                    "phase": TaskPhase.BACKEND_TERMINAL.value,
                    "ended_at": now,
                },
                expected_state_version=task.state_version,
                expected_states=(task.state.value,),
            )
    except (KeyError, ValueError):
        pass

    run_store = RunStore(runs_dir)
    try:
        run = run_store.get_run(run_id)
        if str(run.get("status")) not in {"completed", "failed", "cancelled", "timed_out"}:
            run_store.conditional_update(
                run_id,
                fields={
                    "status": "completed" if success else "failed",
                    "current_phase": "completed" if success else "failed",
                    "ended_at": now,
                    "exit_code": 0 if success else 1,
                    "summary": summary,
                },
                expected_state_version=int(run.get("state_version", 0)),
                reject_terminal=True,
            )
    except (KeyError, ValueError):
        pass


def inspect_activation(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    config = load_config(config_path, validate_repos=False)
    runs_dir = config.resolve_runs_dir()
    authority = WorkerAuthorityStore(runs_dir)
    return {
        "execute": False,
        "runs_dir": str(runs_dir),
        "database_path": str(authority.db_path),
        "database_exists": authority.db_path.exists(),
        "worker_authority_schema": authority.schema_state(),
        "expected_owner_tool_count": EXPECTED_OWNER_TOOL_COUNT,
        "expected_owner_public_schema_hash": EXPECTED_OWNER_PUBLIC_SCHEMA_HASH,
        "network_boundary": {"host": ACTIVATION_HOST, "public_route": False},
    }


def run_activation(
    config_path: str | Path = "config.yaml",
    *,
    execute: bool = False,
    owner_mcp_url: str = DEFAULT_OWNER_MCP_URL,
) -> dict[str, Any]:
    if not execute:
        return inspect_activation(config_path)

    config = load_config(config_path, validate_repos=False)
    runs_dir = config.resolve_runs_dir()
    authority_store = WorkerAuthorityStore(runs_dir)
    if not authority_store.db_path.exists():
        raise ActivationError(f"live Soma database does not exist: {authority_store.db_path}")

    now = _utc_now()
    suffix = uuid4().hex[:10]
    activation_id = f"v3_2_worker_gateway_activation_{_stamp(now)}_{suffix}"
    activation_dir = runs_dir / "v3_2_worker_gateway_activation" / activation_id
    activation_dir.mkdir(parents=True, exist_ok=False)
    result_path = activation_dir / "result.json"
    journal_path = activation_dir / "handler_journal.jsonl"
    backup_path = (
        runs_dir
        / "v3_2_worker_gateway_activation"
        / "backups"
        / f"soma_pre_worker_authority_{_stamp(now)}_{suffix}.sqlite3"
    )

    report: dict[str, Any] = {
        "activation_id": activation_id,
        "status": "running",
        "started_at": now.isoformat(),
        "network_boundary": {"host": ACTIVATION_HOST, "public_route": False},
        "owner_mcp_url": owner_mcp_url,
    }
    process: multiprocessing.Process | None = None
    task_id = ""
    run_id = ""
    principal_id = ""
    grant_id = ""
    grant_revoked = False
    principal_revoked = False
    success = False
    credential_once: str | None = None

    try:
        owner_before = asyncio.run(_owner_identity(owner_mcp_url))
        _assert_owner_identity(owner_before)
        report["owner_before"] = owner_before
        report["schema_before"] = authority_store.schema_state()
        report["database_backup"] = _sqlite_backup(authority_store.db_path, backup_path)

        migrations = authority_store.init_db()
        schema_after = authority_store.schema_state()
        if (
            schema_after.get("schema_version") != 1
            or not schema_after.get("up_to_date")
            or schema_after.get("missing_tables")
            or schema_after.get("missing_triggers")
        ):
            raise ActivationError("worker-authority schema did not converge to accepted v1")
        report["migrations_applied"] = migrations
        report["schema_after_migration"] = schema_after

        disposable = _make_disposable_scope(
            runs_dir=runs_dir,
            activation_dir=activation_dir,
            suffix=suffix,
        )
        task_id, run_id, task_state_version = _make_disposable_task_run(
            runs_dir=runs_dir,
            scope=disposable["scope"],
            binding=disposable["binding"],
            repo_name=disposable["repo_name"],
            activation_dir=activation_dir,
            suffix=suffix,
        )
        report["disposable_scope"] = {
            "project_id": disposable["project_id"],
            "resource_id": disposable["resource_id"],
            "repo_name": disposable["repo_name"],
            "scope_generation": disposable["binding"].scope_generation,
            "task_id": task_id,
            "run_id": run_id,
        }

        spec = WorkerOperationSpecV1(
            operation_ref=ACTIVATION_OPERATION_REF,
            operation_kind="query",
            requires_session=False,
            allowed_task_states=(TaskState.RUNNING.value,),
            description="V3-2 loopback activation proof query.",
        )
        registry = WorkerOperationRegistry((spec,))
        authority = WorkerAuthorityService(runs_dir, registry=registry)
        issue = authority.issue_principal(
            WorkerPrincipalIssueV1(
                controller_request_id=f"v3-2-worker-principal-{suffix}",
                project_id=disposable["project_id"],
                resource_id=disposable["resource_id"],
                scope_generation=disposable["binding"].scope_generation,
                task_id=task_id,
                run_id=run_id,
                session_binding_id="",
                role_ref="role-context:v3-2-activation-worker",
                mandate_ref=f"mandate:v3-2-activation:{suffix}",
                mandate_hash=canonical_hash({"activation_id": activation_id}),
                mandate_version="v1",
                issuer_ref=ACTIVATION_ISSUER_REF,
                expires_at=_utc_now() + timedelta(minutes=30),
            )
        )
        if not issue.created or not issue.credential_once:
            raise ActivationError("disposable worker principal was not newly issued")
        principal_id = issue.principal.principal_id
        credential_once = issue.credential_once
        grant, grant_created = authority.issue_grant(
            WorkerCapabilityGrantIssueV1(
                controller_request_id=f"v3-2-worker-grant-{suffix}",
                principal_id=principal_id,
                intent_ref=f"intent:v3-2-activation:{suffix}",
                intent_hash=canonical_hash({"intent": activation_id}),
                operation_ref=ACTIVATION_OPERATION_REF,
                operation_hash=spec.operation_hash,
                parameter_contract=ACTIVATION_PARAMETER_CONTRACT,
                issuer_ref=ACTIVATION_ISSUER_REF,
                expires_at=_utc_now() + timedelta(minutes=20),
            )
        )
        if not grant_created:
            raise ActivationError("disposable worker grant was not newly issued")
        grant_id = grant.grant_id
        bearer = make_worker_bearer(principal_id, credential_once)

        port = _reserve_loopback_port()
        context = multiprocessing.get_context("spawn")
        process = context.Process(
            target=_worker_server_child,
            args=(str(runs_dir), port, str(journal_path)),
            daemon=True,
        )
        process.start()
        listener = _wait_for_listener(port, process.pid or 0)
        worker_url = f"http://{ACTIVATION_HOST}:{port}/mcp"
        report["listener"] = {**listener, "url": worker_url}

        malformed_codes = asyncio.run(_expect_auth_denial(worker_url, "malformed-worker-bearer"))
        if _journal_count(journal_path) != 0:
            raise ActivationError("handler ran during malformed-authentication proof")

        discovered = asyncio.run(
            _worker_call(worker_url, bearer, "worker_capabilities", {})
        )
        if not discovered.get("ok"):
            raise ActivationError(f"authenticated capability discovery failed: {discovered}")
        capabilities = discovered.get("capabilities")
        if not isinstance(capabilities, list) or len(capabilities) != 1:
            raise ActivationError("authenticated discovery did not return exactly one capability")
        if capabilities[0].get("grant_id") != grant_id:
            raise ActivationError("authenticated discovery returned the wrong grant")

        invoked = asyncio.run(
            _worker_call(
                worker_url,
                bearer,
                "worker_invoke",
                {
                    "grant_id": grant_id,
                    "parameters": dict(ACTIVATION_PARAMETER_CONTRACT),
                    "expected_task_state_version": task_state_version,
                    "controller_request_id": f"v3-2-worker-invoke-{suffix}",
                },
            )
        )
        if not invoked.get("ok") or invoked.get("result", {}).get("activation") != "ok":
            raise ActivationError(f"exact worker invocation failed: {invoked}")
        if _journal_count(journal_path) != 1:
            raise ActivationError("exact worker invocation did not execute handler exactly once")

        wrong_parameters = asyncio.run(
            _worker_call(
                worker_url,
                bearer,
                "worker_invoke",
                {
                    "grant_id": grant_id,
                    "parameters": {"probe": "wrong"},
                    "expected_task_state_version": task_state_version,
                    "controller_request_id": f"v3-2-worker-wrong-params-{suffix}",
                },
            )
        )
        if wrong_parameters.get("error", {}).get("code") != "parameter_contract_mismatch":
            raise ActivationError(f"wrong-parameter denial drifted: {wrong_parameters}")
        stale_state = asyncio.run(
            _worker_call(
                worker_url,
                bearer,
                "worker_invoke",
                {
                    "grant_id": grant_id,
                    "parameters": dict(ACTIVATION_PARAMETER_CONTRACT),
                    "expected_task_state_version": task_state_version + 100,
                    "controller_request_id": f"v3-2-worker-stale-state-{suffix}",
                },
            )
        )
        if stale_state.get("error", {}).get("code") != "stale_task_state_version":
            raise ActivationError(f"stale-state denial drifted: {stale_state}")
        if _journal_count(journal_path) != 1:
            raise ActivationError("handler executed during pre-dispatch denial proof")

        authority.store.revoke(
            target_kind="grant",
            target_id=grant_id,
            controller_request_id=f"v3-2-worker-revoke-grant-{suffix}",
            reason_ref="reason:v3-2-activation-complete",
            reason_hash=canonical_hash({"reason": "activation-grant-revocation"}),
            issuer_ref=ACTIVATION_ISSUER_REF,
        )
        grant_revoked = True
        revoked_grant = asyncio.run(
            _worker_call(
                worker_url,
                bearer,
                "worker_invoke",
                {
                    "grant_id": grant_id,
                    "parameters": dict(ACTIVATION_PARAMETER_CONTRACT),
                    "expected_task_state_version": task_state_version,
                    "controller_request_id": f"v3-2-worker-after-revoke-{suffix}",
                },
            )
        )
        if revoked_grant.get("error", {}).get("code") != "grant_revoked":
            raise ActivationError(f"grant-revocation denial drifted: {revoked_grant}")
        if _journal_count(journal_path) != 1:
            raise ActivationError("handler executed after grant revocation")

        authority.store.revoke(
            target_kind="principal",
            target_id=principal_id,
            controller_request_id=f"v3-2-worker-revoke-principal-{suffix}",
            reason_ref="reason:v3-2-activation-complete",
            reason_hash=canonical_hash({"reason": "activation-principal-revocation"}),
            issuer_ref=ACTIVATION_ISSUER_REF,
        )
        principal_revoked = True
        principal_codes = asyncio.run(_expect_auth_denial(worker_url, bearer))

        serialized_public = json.dumps(
            {
                "discovery": discovered,
                "invoke": invoked,
                "wrong_parameters": wrong_parameters,
                "stale_state": stale_state,
                "revoked_grant": revoked_grant,
            },
            sort_keys=True,
        )
        if credential_once in serialized_public or issue.principal.verifier_hash in serialized_public:
            raise ActivationError("worker proof response leaked reusable authentication material")

        report["proof"] = {
            "malformed_auth_http_statuses": sorted(malformed_codes),
            "principal_id": principal_id,
            "grant_id": grant_id,
            "capability_count": len(capabilities),
            "exact_invoke_ok": True,
            "wrong_parameters_code": wrong_parameters.get("error", {}).get("code"),
            "stale_state_code": stale_state.get("error", {}).get("code"),
            "grant_revoked_code": revoked_grant.get("error", {}).get("code"),
            "principal_revoked_http_statuses": sorted(principal_codes),
            "handler_execution_count": _journal_count(journal_path),
            "secret_leak": False,
        }

        _terminate_process(process)
        if not _wait_for_port_closed(port):
            raise ActivationError("worker loopback listener remained open after teardown")
        report["listener_teardown"] = {
            "pid": process.pid,
            "port": port,
            "closed": True,
            "exit_code": process.exitcode,
        }
        process = None

        owner_after = asyncio.run(_owner_identity(owner_mcp_url))
        _assert_owner_identity(owner_after)
        if owner_after != owner_before:
            raise ActivationError("owner MCP discovery identity changed during worker activation")
        report["owner_after"] = owner_after
        report["worker_authority_counts"] = authority.store.table_counts()
        success = True
        report["status"] = "completed"
        report["ended_at"] = _utc_now().isoformat()
        return report
    except BaseException as exc:
        report["status"] = "failed"
        report["ended_at"] = _utc_now().isoformat()
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:1000]
        raise
    finally:
        if process is not None:
            port = int(report.get("listener", {}).get("port", 0) or 0)
            _terminate_process(process)
            if port:
                report["listener_teardown"] = {
                    "pid": process.pid,
                    "port": port,
                    "closed": _wait_for_port_closed(port),
                    "exit_code": process.exitcode,
                }
        cleanup_authority = WorkerAuthorityStore(runs_dir)
        if grant_id and not grant_revoked:
            try:
                cleanup_authority.revoke(
                    target_kind="grant",
                    target_id=grant_id,
                    controller_request_id=f"cleanup-revoke-grant-{suffix}",
                    reason_ref="reason:v3-2-activation-cleanup",
                    reason_hash=canonical_hash({"cleanup": "grant"}),
                    issuer_ref=ACTIVATION_ISSUER_REF,
                )
                grant_revoked = True
            except Exception:
                pass
        if principal_id and not principal_revoked:
            try:
                cleanup_authority.revoke(
                    target_kind="principal",
                    target_id=principal_id,
                    controller_request_id=f"cleanup-revoke-principal-{suffix}",
                    reason_ref="reason:v3-2-activation-cleanup",
                    reason_hash=canonical_hash({"cleanup": "principal"}),
                    issuer_ref=ACTIVATION_ISSUER_REF,
                )
                principal_revoked = True
            except Exception:
                pass
        if task_id and run_id:
            _terminalize_task_run(
                runs_dir,
                task_id,
                run_id,
                success=success,
                summary=(
                    "V3-2 worker gateway activation proof completed"
                    if success
                    else "V3-2 worker gateway activation proof failed"
                ),
            )
        report["disposable_authority_revoked"] = {
            "grant": grant_revoked,
            "principal": principal_revoked,
        }
        report["status"] = "completed" if success else report.get("status", "failed")
        report["ended_at"] = report.get("ended_at") or _utc_now().isoformat()
        _write_json_atomic(result_path, report)
        credential_once = None


def _main() -> int:
    parser = argparse.ArgumentParser(description="V3-2 worker gateway loopback activation proof")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--owner-mcp-url", default=DEFAULT_OWNER_MCP_URL)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = run_activation(
            args.config,
            execute=args.execute,
            owner_mcp_url=args.owner_mcp_url,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:1000]}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
