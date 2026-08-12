"""G4.4 cross-plan protected-mutation containment and restart proofs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from soma.company_kernel.store import CompanyKernelStore
from soma.project_scope import ProjectScopeStore
from soma.protected_tools.broker import (
    ProtectedAdapterResultV1,
    ProtectedAuthoritySnapshotV1,
    ProtectedResourceUnavailable,
    ProtectedToolBroker,
)
from soma.protected_tools.models import ProtectedToolCallV1, ProtectedToolEffectV1
from soma.protected_tools.resource_guard import DurableProtectedResourceGuard
from soma.protected_tools.store import ProtectedToolStore
from soma.tasks.store import TaskStore


COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
OLD_PLAN_ID = "planrev_" + "3" * 24
NEW_PLAN_ID = "planrev_" + "4" * 24
OLD_PACKAGE_ID = "workpkg_" + "5" * 24
NEW_PACKAGE_ID = "workpkg_" + "6" * 24
OLD_OUTCOME_ID = "outcome_" + "7" * 24
NEW_OUTCOME_ID = "outcome_" + "8" * 24
OLD_ATTEMPT_ID = "wpattempt_" + "9" * 24
NEW_ATTEMPT_ID = "wpattempt_" + "a" * 24
OLD_TASK_ID = "task_20260812T120000Z_aaaaaaaaaaaa"
NEW_TASK_ID = "task_20260812T120100Z_bbbbbbbbbbbb"
OLD_BACKEND_REF = "reasoning-backend:old-plan"
NEW_BACKEND_REF = "reasoning-backend:new-plan"
PROJECT_ID = "Project_Protected_Replan"
RESOURCE_ID = "Resource_Protected_Replan"
RESOURCE_KEY = "repository:d:/github/soma"
OWNER = "owner-controller:protected-replan"
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
NOW_TEXT = NOW.isoformat()
PAYLOAD = b"protected replan payload"
PAYLOAD_HASH = sha256(PAYLOAD).hexdigest()


def _hash(character: str) -> str:
    return character * 64


def _route() -> str:
    return json.dumps(
        {
            "backend_kind": "soma_reasoning",
            "project_scope": {
                "project_id": PROJECT_ID,
                "resource_id": RESOURCE_ID,
                "scope_generation": 1,
            },
            "reasoning_spec": {"ref": "reasoning-spec:fixture", "hash": _hash("b")},
            "dependency_proof_refs": [],
            "supersedes_attempt_id": None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _insert_task_attempt(
    conn,
    *,
    plan_id: str,
    package_id: str,
    outcome_id: str,
    attempt_id: str,
    task_id: str,
    backend_ref: str,
    package_key: str,
    ordinal: int,
) -> None:
    conn.execute(
        """
        INSERT INTO work_packages(
            work_package_id, mission_id, plan_revision_id, package_key,
            outcome_id, project_id, target_resource_id, scope_generation,
            contract_version, contract_json, contract_hash, topology,
            accountable_owner_ref, acceptance_authority_ref,
            deliberation_ref, evidence_requirements_ref,
            evidence_requirements_hash, controller_request_id,
            request_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'v1', '{}', ?, 'single_active',
                  ?, ?, '', '', '', ?, ?, ?)
        """,
        (
            package_id,
            MISSION_ID,
            plan_id,
            package_key,
            outcome_id,
            PROJECT_ID,
            RESOURCE_ID,
            _hash("c"),
            OWNER,
            OWNER,
            f"package-request-{ordinal}",
            _hash("d"),
            NOW_TEXT,
        ),
    )
    conn.execute(
        """
        INSERT INTO tasks(
            task_id, task_kind, controller_request_id, request_hash,
            backend_kind, backend_executor, backend_ref, backend_identity_json,
            workspace_kind, workspace_ref, state, phase, state_version,
            created_at, updated_at, started_at
        ) VALUES (?, 'reasoning', ?, ?, 'soma_reasoning', 'reasoning_backend',
                  ?, '{}', 'repository', 'sample', 'running', 'backend_running',
                  5, ?, ?, ?)
        """,
        (
            task_id,
            f"task-request-{ordinal}",
            _hash("e"),
            backend_ref,
            NOW_TEXT,
            NOW_TEXT,
            NOW_TEXT,
        ),
    )
    conn.execute(
        """
        INSERT INTO work_package_attempts(
            attempt_id, work_package_id, outcome_id, task_id,
            route_request_hash, route_descriptor_json, supersedes_attempt_id,
            containment_evidence_ref, containment_evidence_hash,
            controller_request_id, request_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, '', '', ?, ?, ?)
        """,
        (
            attempt_id,
            package_id,
            outcome_id,
            task_id,
            _hash("f"),
            _route(),
            f"attempt-request-{ordinal}",
            _hash("1"),
            NOW_TEXT,
        ),
    )
    conn.execute(
        """
        INSERT INTO project_task_reservations(
            task_id, project_id, scope_generation, status, created_at, updated_at
        ) VALUES (?, ?, 1, 'attached', ?, ?)
        """,
        (task_id, PROJECT_ID, NOW_TEXT, NOW_TEXT),
    )
    conn.execute(
        """
        INSERT INTO project_run_attempts(
            run_id, project_id, task_id, resource_id, scope_generation,
            status, recovery_reason, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 1, 'attached', '', ?, ?)
        """,
        (backend_ref, PROJECT_ID, task_id, RESOURCE_ID, NOW_TEXT, NOW_TEXT),
    )


def _prepare_db(tmp_path: Path) -> tuple[Path, CompanyKernelStore]:
    runs = tmp_path / "runs"
    TaskStore(runs)
    scope = ProjectScopeStore(runs)
    scope.init_db()
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="protected-replan",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)

    kernel = CompanyKernelStore(runs)
    assert kernel.init_db() == [1, 2, 3]
    with kernel.connect() as conn:
        conn.execute(
            "INSERT INTO companies(company_id, company_key, display_name, executive_authority_ref, "
            "creation_request_id, creation_request_hash, created_at) "
            "VALUES (?, 'protected-replan', 'Protected Replan', ?, 'company-request', ?, ?)",
            (COMPANY_ID, OWNER, _hash("2"), NOW_TEXT),
        )
        conn.execute(
            """
            INSERT INTO missions(
                mission_id, company_id, mission_key, project_id, resource_id,
                scope_generation, mission_contract_json, mission_contract_hash,
                accountable_owner_ref, acceptance_authority_ref,
                current_plan_revision_id, plan_state_version, kernel_state_version,
                creation_request_id, creation_request_hash, created_at, updated_at
            ) VALUES (?, ?, 'protected-mission', ?, ?, 1, '{}', ?, ?, ?, NULL,
                      0, 0, 'mission-request', ?, ?, ?)
            """,
            (
                MISSION_ID,
                COMPANY_ID,
                PROJECT_ID,
                RESOURCE_ID,
                _hash("3"),
                OWNER,
                OWNER,
                _hash("4"),
                NOW_TEXT,
                NOW_TEXT,
            ),
        )
        conn.execute(
            """
            INSERT INTO plan_revisions(
                plan_revision_id, mission_id, revision_number, parent_plan_revision_id,
                plan_contract_json, plan_content_hash, deliberation_ref,
                deliberation_hash, accepted_by_ref, acceptance_basis_ref,
                controller_request_id, request_hash, accepted_at
            ) VALUES (?, ?, 1, NULL, '{}', ?, '', '', ?, 'old-plan',
                      'old-plan-request', ?, ?)
            """,
            (OLD_PLAN_ID, MISSION_ID, _hash("5"), OWNER, _hash("6"), NOW_TEXT),
        )
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = ?, plan_state_version = 1, "
            "kernel_state_version = 1 WHERE mission_id = ?",
            (OLD_PLAN_ID, MISSION_ID),
        )
        _insert_task_attempt(
            conn,
            plan_id=OLD_PLAN_ID,
            package_id=OLD_PACKAGE_ID,
            outcome_id=OLD_OUTCOME_ID,
            attempt_id=OLD_ATTEMPT_ID,
            task_id=OLD_TASK_ID,
            backend_ref=OLD_BACKEND_REF,
            package_key="old-package",
            ordinal=1,
        )
    return runs, kernel


def _select_new_plan(kernel: CompanyKernelStore) -> None:
    with kernel.connect() as conn:
        conn.execute(
            """
            INSERT INTO plan_revisions(
                plan_revision_id, mission_id, revision_number, parent_plan_revision_id,
                plan_contract_json, plan_content_hash, deliberation_ref,
                deliberation_hash, accepted_by_ref, acceptance_basis_ref,
                controller_request_id, request_hash, accepted_at
            ) VALUES (?, ?, 2, ?, '{}', ?, '', '', ?, 'new-plan',
                      'new-plan-request', ?, ?)
            """,
            (
                NEW_PLAN_ID,
                MISSION_ID,
                OLD_PLAN_ID,
                _hash("7"),
                OWNER,
                _hash("8"),
                (NOW + timedelta(minutes=1)).isoformat(),
            ),
        )
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = ?, plan_state_version = 2, "
            "kernel_state_version = 2, updated_at = ? WHERE mission_id = ?",
            (NEW_PLAN_ID, (NOW + timedelta(minutes=1)).isoformat(), MISSION_ID),
        )
        _insert_task_attempt(
            conn,
            plan_id=NEW_PLAN_ID,
            package_id=NEW_PACKAGE_ID,
            outcome_id=NEW_OUTCOME_ID,
            attempt_id=NEW_ATTEMPT_ID,
            task_id=NEW_TASK_ID,
            backend_ref=NEW_BACKEND_REF,
            package_key="new-package",
            ordinal=2,
        )


def _call(*, old: bool) -> ProtectedToolCallV1:
    task_id = OLD_TASK_ID if old else NEW_TASK_ID
    attempt_id = OLD_ATTEMPT_ID if old else NEW_ATTEMPT_ID
    backend_ref = OLD_BACKEND_REF if old else NEW_BACKEND_REF
    suffix = "old" if old else "new"
    return ProtectedToolCallV1(
        call_request_id=f"protected-replan-call-{suffix}",
        task_id=task_id,
        attempt_id=attempt_id,
        backend_ref=backend_ref,
        mandate_ref="mandate:protected-replan",
        mandate_hash=_hash("9"),
        mandate_version="v1",
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        capability_ref="capability:repository-write",
        capability_hash=_hash("a"),
        tool_operation_ref="tool-operation:fake-write",
        tool_operation_hash=_hash("b"),
        resource_key=RESOURCE_KEY,
        idempotency_key=f"soma-slot:protected-replan/{suffix}",
        payload_ref=f"payload:protected-replan/{suffix}",
        payload_hash=PAYLOAD_HASH,
        expected_task_state_version=5,
        expires_at=NOW + timedelta(hours=1),
        mutation_class="repository",
    )


class _AuthorityResolver:
    def resolve(self, call: ProtectedToolCallV1) -> ProtectedAuthoritySnapshotV1:
        return ProtectedAuthoritySnapshotV1(
            mandate_ref=call.mandate_ref,
            mandate_hash=call.mandate_hash,
            mandate_version=call.mandate_version,
            mandate_active=True,
            capability_ref=call.capability_ref,
            capability_hash=call.capability_hash,
            capability_possessed=True,
            tool_operation_ref=call.tool_operation_ref,
            tool_operation_hash=call.tool_operation_hash,
            tool_operation_enabled=True,
            idempotency_key=call.idempotency_key,
            idempotency_authorized=True,
        )


class _Adapter:
    def __init__(self, mode: str = "acknowledged") -> None:
        self.mode = mode
        self.calls = 0

    def execute(
        self, call: ProtectedToolCallV1, payload: bytes
    ) -> ProtectedAdapterResultV1:
        self.calls += 1
        assert payload == PAYLOAD
        if self.mode == "raise":
            raise RuntimeError("fixture transport disappeared after send")
        return ProtectedAdapterResultV1(
            disposition="acknowledged",
            external_effect_ref=f"fake-effect:{call.call_request_id}",
            external_effect_hash=_hash("c"),
            evidence_ref=f"fake-evidence:{call.call_request_id}",
            evidence_hash=_hash("d"),
        )


def _broker(runs: Path, adapter: _Adapter) -> ProtectedToolBroker:
    store = ProtectedToolStore(runs)
    return ProtectedToolBroker(
        store=store,
        authority_resolver=_AuthorityResolver(),
        resource_guard=DurableProtectedResourceGuard(store),
        adapter=adapter,
        clock=lambda: NOW + timedelta(minutes=2),
    )


def test_replan_does_not_cancel_old_task_and_uncertain_old_effect_blocks_new_writer(
    tmp_path: Path,
) -> None:
    runs, kernel = _prepare_db(tmp_path)
    old_call = _call(old=True)
    old_adapter = _Adapter(mode="raise")
    old_broker = _broker(runs, old_adapter)

    old_result = old_broker.execute(old_call, PAYLOAD)
    assert old_result.effect.disposition == "outcome_unknown"
    assert old_adapter.calls == 1
    assert (
        DurableProtectedResourceGuard(old_broker.store).get_lease(
            old_call.call_request_id
        )["state"]
        == "uncertain"
    )

    _select_new_plan(kernel)
    with kernel.connect() as conn:
        task_rows = conn.execute(
            "SELECT task_id, state FROM tasks WHERE task_id IN (?, ?) ORDER BY task_id",
            (OLD_TASK_ID, NEW_TASK_ID),
        ).fetchall()
        cancel_count = conn.execute(
            "SELECT COUNT(*) FROM task_commands WHERE task_id = ? AND command_kind = 'cancel'",
            (OLD_TASK_ID,),
        ).fetchone()[0]
    assert {str(row["task_id"]): str(row["state"]) for row in task_rows} == {
        OLD_TASK_ID: "running",
        NEW_TASK_ID: "running",
    }
    assert cancel_count == 0

    new_call = _call(old=False)
    new_adapter = _Adapter()
    new_broker = _broker(runs, new_adapter)
    with pytest.raises(ProtectedResourceUnavailable):
        new_broker.execute(new_call, PAYLOAD)
    assert new_adapter.calls == 0

    restarted_old_adapter = _Adapter()
    replay = _broker(runs, restarted_old_adapter).execute(old_call, PAYLOAD)
    assert replay.replayed is True
    assert replay.adapter_called is False
    assert replay.effect.effect_hash == old_result.effect.effect_hash
    assert restarted_old_adapter.calls == 0
    restarted_guard = DurableProtectedResourceGuard(ProtectedToolStore(runs))
    assert restarted_guard.get_lease(old_call.call_request_id)["state"] == "uncertain"

    contained = restarted_guard.contain_uncertainty(
        call_request_id=old_call.call_request_id,
        request_hash=old_call.request_hash,
        evidence_ref="containment:old-effect-mechanically-contained",
        evidence_hash=_hash("e"),
    )
    assert contained["state"] == "contained"

    new_result = new_broker.execute(new_call, PAYLOAD)
    assert new_result.effect.disposition == "acknowledged"
    assert new_adapter.calls == 1
    assert (
        DurableProtectedResourceGuard(new_broker.store).get_lease(
            new_call.call_request_id
        )["state"]
        == "released"
    )


def test_replay_reconciles_acknowledged_effect_persisted_before_lease_release(
    tmp_path: Path,
) -> None:
    runs, _kernel = _prepare_db(tmp_path)
    call = _call(old=True)
    store = ProtectedToolStore(runs)
    canonical, created = store.reserve_call(call)
    assert created is True
    guard = DurableProtectedResourceGuard(store)
    lease = guard.acquire(canonical)
    assert lease.acquired is True
    assert (
        store.claim_effect_boundary(
            call_request_id=canonical.call_request_id,
            request_hash=canonical.request_hash,
            evidence_ref=lease.evidence_ref,
            evidence_hash=lease.evidence_hash,
        )
        is True
    )
    effect = ProtectedToolEffectV1(
        call_request_id=canonical.call_request_id,
        request_hash=canonical.request_hash,
        disposition="acknowledged",
        external_effect_ref="fake-effect:crash-window",
        external_effect_hash=_hash("f"),
        evidence_ref="fake-evidence:effect-persisted",
        evidence_hash=_hash("1"),
        completed_at=NOW + timedelta(minutes=1),
    )
    stored, effect_created = store.record_effect(effect)
    assert effect_created is True
    assert guard.get_lease(canonical.call_request_id)["state"] == "held"

    adapter = _Adapter()
    replay = _broker(runs, adapter).execute(call, PAYLOAD)
    assert replay.replayed is True
    assert replay.adapter_called is False
    assert replay.effect.effect_hash == stored.effect_hash
    assert adapter.calls == 0
    assert (
        DurableProtectedResourceGuard(ProtectedToolStore(runs)).get_lease(
            canonical.call_request_id
        )["state"]
        == "released"
    )
