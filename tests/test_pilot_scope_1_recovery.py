from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pydantic import Field

import soma.operation_locks as operation_locks
import soma.server as server
from soma.gateway_models import RunStatusQuery, TaskDurableCommandStart
from soma.hermes_service_gateway import HermesServiceGateway
from soma.operation_locks import OperationLockStore
from soma.tasks.models import make_task_id
from soma.tasks.store import TaskStore
from test_pilot_scope_1 import (
    PROJECT_ALPHA,
    PROJECT_BETA,
    REPO_ALIAS,
    SCHEMA_HASH,
    SCOPE_GENERATION,
    ImmediateHermesSupervisor,
    PilotProjectScopeStore,
    PilotScopeError,
    _reserve_real_task,
    _seed_projects,
)


RUN_RECOVERY = "20260727T130000Z_executable_profile_dddddddd"
RUN_ORPHAN = "20260727T130001Z_executable_profile_eeeeeeee"
RUN_HERMES_RESTART = "20260727T130002Z_hermes_service_ffffffff"


class PilotScopedTaskStart(TaskDurableCommandStart):
    """Proposed additive controller contract; project omission stays parseable."""

    project_id: str = Field(default="", max_length=128)


class PilotScopedRunStatusQuery(RunStatusQuery):
    """Proposed exact-run contract with an optional scope assertion."""

    project_id: str = Field(default="", max_length=128)


def test_restart_reconciles_reservations_and_preserves_process_lock_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    locks = OperationLockStore(runs_dir)
    scope = PilotProjectScopeStore(runs_dir)
    repo_alpha, _ = _seed_projects(scope, tmp_path)

    orphan_task_id = make_task_id()
    scope.reserve_task_attempt(
        project_id=PROJECT_ALPHA,
        task_id=orphan_task_id,
        run_id=RUN_ORPHAN,
        resource_id=repo_alpha,
    )
    recoverable_task_id = _reserve_real_task(
        task_store,
        scope,
        project_id=PROJECT_ALPHA,
        resource_id=repo_alpha,
        run_id=RUN_RECOVERY,
        request_id="request-recovery",
    )

    restarted_scope = PilotProjectScopeStore(runs_dir)
    reconciled = restarted_scope.reconcile_startup()
    assert reconciled == {
        "task_quarantined": 1,
        "attempt_recovery_pending": 1,
        "attempt_attached": 0,
        "attempt_quarantined": 0,
    }
    assert restarted_scope.reservation_status("task", orphan_task_id) == "quarantined"
    assert restarted_scope.reservation_status("attempt", RUN_ORPHAN) == "quarantined"
    assert (
        restarted_scope.reservation_status("attempt", RUN_RECOVERY)
        == "recovery_pending"
    )

    restarted_scope.claim_recovery(RUN_RECOVERY)
    run = locks.store.create_run(
        run_id=RUN_RECOVERY,
        repo_name=REPO_ALIAS,
        tool="executable_profile",
        run_dir=runs_dir / RUN_RECOVERY,
        input_data={"repo_name": REPO_ALIAS},
        worker_lease_token="lease-alpha",
    )
    restarted_scope.attach_task_attempt(recoverable_task_id, RUN_RECOVERY)
    acquired = locks.acquire(
        repo_name=REPO_ALIAS,
        tool="executable_profile",
        normalized_input={"repo_name": REPO_ALIAS},
        run_id=RUN_RECOVERY,
        owner_pid=901,
        owner_token="lease-alpha",
        lease_generation=1,
    )
    assert acquired.acquired is True
    observed = locks.store.get_run(RUN_RECOVERY)
    assert locks.store.claim_worker(
        RUN_RECOVERY,
        lease_token="lease-alpha",
        lease_generation=1,
        expected_state_version=observed["state_version"],
        worker_pid=902,
        worker_identity="902:windows:alpha",
    )

    # A server restart adopts the exact worker/lease without changing project.
    restarted_locks = OperationLockStore(runs_dir)
    current = restarted_locks.store.get_run(RUN_RECOVERY)
    adopted = restarted_locks.store.adopt_worker(
        RUN_RECOVERY,
        expected_state_version=current["state_version"],
        lease_token="lease-alpha",
        lease_generation=1,
        expected_heartbeat_at=current["heartbeat_at"],
    )
    assert adopted is not None
    assert restarted_scope.project_for_run(RUN_RECOVERY) == PROJECT_ALPHA
    assert restarted_locks.find_lock(REPO_ALIAS, RUN_RECOVERY) is not None

    # Cancellation pending retains the lock even after a dead-owner probe.
    current = restarted_locks.store.get_run(RUN_RECOVERY)
    cancelling = restarted_locks.store.conditional_update(
        RUN_RECOVERY,
        fields={
            "status": "cancellation_pending",
            "current_phase": "cancellation_pending",
        },
        expected_statuses=("running",),
        expected_state_version=current["state_version"],
        expected_lease_token="lease-alpha",
        expected_lease_generation=1,
    )
    assert cancelling is not None
    monkeypatch.setattr(
        operation_locks, "process_matches_identity", lambda _pid, _identity: False
    )
    monkeypatch.setattr(operation_locks, "process_is_running", lambda _pid: False)
    assert restarted_locks.recover_stale() == 0
    assert restarted_locks.find_lock(REPO_ALIAS, RUN_RECOVERY) is not None

    terminal = restarted_locks.store.transition_terminal(
        RUN_RECOVERY,
        status="cancelled",
        result={"ok": False, "cancelled": True},
        expected_statuses=("cancellation_pending",),
        expected_state_version=cancelling["state_version"],
        expected_lease_token="lease-alpha",
        expected_lease_generation=1,
    )
    assert terminal is not None
    assert restarted_locks.release(REPO_ALIAS, RUN_RECOVERY, "lease-alpha", 1)
    assert restarted_scope.project_for_run(RUN_RECOVERY) == PROJECT_ALPHA
    with pytest.raises(PilotScopeError, match="run project scope mismatch"):
        restarted_scope.require_run(PROJECT_BETA, RUN_RECOVERY)
    assert run["run_id"] == RUN_RECOVERY


def test_attached_attempt_without_run_is_quarantined(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    OperationLockStore(runs_dir)
    scope = PilotProjectScopeStore(runs_dir)
    repo_alpha, _ = _seed_projects(scope, tmp_path)
    task_id = _reserve_real_task(
        task_store,
        scope,
        project_id=PROJECT_ALPHA,
        resource_id=repo_alpha,
        run_id=RUN_RECOVERY,
        request_id="request-missing-run",
    )
    with scope.connect() as conn:
        conn.execute(
            "UPDATE pilot_scope_attempts SET status = 'attached' WHERE run_id = ?",
            (RUN_RECOVERY,),
        )

    restarted = PilotProjectScopeStore(runs_dir)
    result = restarted.reconcile_startup()

    assert result["attempt_quarantined"] == 1
    assert restarted.reservation_status("task", task_id) == "attached"
    assert restarted.reservation_status("attempt", RUN_RECOVERY) == "quarantined"


def test_hermes_restart_uses_durable_project_and_session_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    run_store = OperationLockStore(runs_dir).store
    scope = PilotProjectScopeStore(runs_dir)
    scope.create_project(PROJECT_ALPHA, "hermes-restart-alpha")
    scope.create_project(PROJECT_BETA, "hermes-restart-beta")
    scope.register_resource(
        resource_id="hermes_service_restart",
        resource_kind="service",
        opaque_ref="hermes-service",
        identity="hermes-service-restart-instance",
    )
    scope.bind_resource(PROJECT_ALPHA, "hermes_service_restart", access_mode="shared")
    scope.bind_resource(PROJECT_BETA, "hermes_service_restart", access_mode="shared")
    task_id = _reserve_real_task(
        task_store,
        scope,
        project_id=PROJECT_ALPHA,
        resource_id="hermes_service_restart",
        run_id=RUN_HERMES_RESTART,
        request_id="request-hermes-restart",
    )
    scope.bind_external_session(
        binding_id="binding-hermes-restart",
        project_id=PROJECT_ALPHA,
        task_id=task_id,
        run_id=RUN_HERMES_RESTART,
        provider_kind="hermes",
        provider_session_id="Session-Restart",
    )
    monkeypatch.setattr(
        "soma.hermes_service_gateway._make_run_id",
        lambda: RUN_HERMES_RESTART,
    )
    first_gateway = HermesServiceGateway(
        run_store=run_store,
        runs_dir=runs_dir,
        supervisor_factory=ImmediateHermesSupervisor,
    )
    response = first_gateway.execute(
        session_id="Session-Restart",
        operation="tool_search",
        payload={"query": "restart fixture"},
        expected_registry_generation=SCOPE_GENERATION,
        expected_schema_hash=SCHEMA_HASH,
    )
    scope.attach_task_attempt(task_id, RUN_HERMES_RESTART)
    first_gateway.close()

    restarted_scope = PilotProjectScopeStore(runs_dir)
    restarted_gateway = HermesServiceGateway(
        run_store=run_store,
        runs_dir=runs_dir,
        supervisor_factory=ImmediateHermesSupervisor,
    )
    try:
        restarted_scope.require_external_session(
            project_id=PROJECT_ALPHA,
            provider_kind="hermes",
            provider_session_id="Session-Restart",
            run_id=response["run_id"],
        )
        assert (
            restarted_gateway.get_result(
                run_id=response["run_id"], session_id="Session-Restart"
            )["status"]
            == "completed"
        )
        with pytest.raises(
            PilotScopeError, match="external session project scope mismatch"
        ):
            restarted_scope.require_external_session(
                project_id=PROJECT_BETA,
                provider_kind="hermes",
                provider_session_id="Session-Restart",
                run_id=response["run_id"],
            )
    finally:
        restarted_gateway.close()


def test_scope_migration_rolls_back_as_one_transaction(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    TaskStore(runs_dir)
    OperationLockStore(runs_dir)
    from test_pilot_scope_1 import MAIN_SCOPE_SCHEMA, _apply_script

    db_path = runs_dir / "soma.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            _apply_script(
                conn,
                MAIN_SCOPE_SCHEMA + "\nSELECT * FROM pilot_scope_forced_missing_table;",
            )
        pilot_tables = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name LIKE 'pilot_scope_%'"
        ).fetchall()
        migration = conn.execute(
            "SELECT 1 FROM soma_schema_migrations "
            "WHERE component = 'pilot_scope_1_fixture'"
        ).fetchone()
    finally:
        conn.close()

    assert pilot_tables == []
    assert migration is None


def test_mcp_contract_evolution_is_strict_additive_and_incumbent_compatible(
    tmp_path: Path,
) -> None:
    async def scoped_tools() -> dict[str, dict[str, Any]]:
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        return {
            name: tools[name].to_mcp_tool().model_dump(mode="json", by_alias=True)
            for name in ("task_query", "task_action", "run_query")
        }

    live = asyncio.run(scoped_tools())
    for name in ("task_query", "task_action", "run_query"):
        for variant in live[name]["inputSchema"]["oneOf"]:
            assert variant["additionalProperties"] is False

    incumbent_payload = {
        "operation": "start",
        "controller_request_id": "incumbent-controller",
        "repo_name": REPO_ALIAS,
    }
    incumbent = TaskDurableCommandStart.model_validate(incumbent_payload)
    proposed = PilotScopedTaskStart.model_validate(incumbent_payload)
    explicit = PilotScopedTaskStart.model_validate(
        {**incumbent_payload, "project_id": PROJECT_ALPHA}
    )
    assert incumbent.repo_name == proposed.repo_name == explicit.repo_name
    assert proposed.project_id == ""
    assert explicit.project_id == PROJECT_ALPHA

    incumbent_schema = TaskDurableCommandStart.model_json_schema()
    proposed_schema = PilotScopedTaskStart.model_json_schema()
    assert set(proposed_schema["properties"]) == {
        *incumbent_schema["properties"],
        "project_id",
    }
    assert proposed_schema["required"] == incumbent_schema["required"]
    assert proposed_schema["additionalProperties"] is False

    incumbent_run_payload = {"operation": "status", "run_id": RUN_RECOVERY}
    incumbent_run = RunStatusQuery.model_validate(incumbent_run_payload)
    proposed_run = PilotScopedRunStatusQuery.model_validate(incumbent_run_payload)
    explicit_run = PilotScopedRunStatusQuery.model_validate(
        {**incumbent_run_payload, "project_id": PROJECT_ALPHA}
    )
    assert incumbent_run.run_id == proposed_run.run_id == explicit_run.run_id
    assert proposed_run.project_id == ""
    assert explicit_run.project_id == PROJECT_ALPHA

    incumbent_run_schema = RunStatusQuery.model_json_schema()
    proposed_run_schema = PilotScopedRunStatusQuery.model_json_schema()
    assert set(proposed_run_schema["properties"]) == {
        *incumbent_run_schema["properties"],
        "project_id",
    }
    assert proposed_run_schema["required"] == incumbent_run_schema["required"]
    assert proposed_run_schema["additionalProperties"] is False

    # Exact-ID owner-controller reads remain usable, while worker access first
    # validates the sidecar scope.
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    run_store = OperationLockStore(runs_dir).store
    scope = PilotProjectScopeStore(runs_dir)
    repo_alpha, _ = _seed_projects(scope, tmp_path)
    task_id = _reserve_real_task(
        task_store,
        scope,
        project_id=PROJECT_ALPHA,
        resource_id=repo_alpha,
        run_id=RUN_RECOVERY,
        request_id="request-contract",
    )
    run_store.create_run(
        run_id=RUN_RECOVERY,
        repo_name=REPO_ALIAS,
        tool="executable_profile",
        run_dir=runs_dir / RUN_RECOVERY,
        input_data={"repo_name": REPO_ALIAS},
    )
    scope.attach_task_attempt(task_id, RUN_RECOVERY)
    assert run_store.get_run(RUN_RECOVERY)["run_id"] == RUN_RECOVERY
    scope.require_run(PROJECT_ALPHA, RUN_RECOVERY)
    with pytest.raises(PilotScopeError, match="run project scope mismatch"):
        scope.require_run(PROJECT_BETA, RUN_RECOVERY)
