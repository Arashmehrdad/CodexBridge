"""G4.3 mechanical protected broker validation using fake external tools only."""

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
    ProtectedResourceLeaseV1,
    ProtectedResourceUnavailable,
    ProtectedToolBroker,
)
from soma.protected_tools.models import (
    ProtectedProviderProvenanceRefV1,
    ProtectedToolCallV1,
)
from soma.protected_tools.store import ProtectedToolStore
from soma.tasks.store import TaskStore


COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
PLAN_ID = "planrev_" + "3" * 24
PACKAGE_ID = "workpkg_" + "4" * 24
OUTCOME_ID = "outcome_" + "5" * 24
ATTEMPT_ID = "wpattempt_" + "6" * 24
TASK_ID = "task_20260812T113000Z_aaaaaaaaaaaa"
BACKEND_REF = "reasoning-backend:protected-broker"
PROJECT_ID = "Project_Protected_Broker"
RESOURCE_ID = "Resource_Protected_Broker"
OWNER = "owner-controller:protected-broker"
NOW = datetime(2026, 8, 12, 11, 30, tzinfo=timezone.utc)
NOW_TEXT = NOW.isoformat()
PAYLOAD = b"protected fake payload"


def _hash(character: str) -> str:
    return character * 64


def _payload_hash() -> str:
    return sha256(PAYLOAD).hexdigest()


def _prepare_db(tmp_path: Path):
    runs = tmp_path / "runs"
    TaskStore(runs)
    scope = ProjectScopeStore(runs)
    scope.init_db()
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="protected-broker",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)
    kernel = CompanyKernelStore(runs)
    assert kernel.init_db() == [1, 2, 3]

    route = {
        "backend_kind": "soma_reasoning",
        "project_scope": {
            "project_id": PROJECT_ID,
            "resource_id": RESOURCE_ID,
            "scope_generation": 1,
        },
        "reasoning_spec": {"ref": "reasoning-spec:fixture", "hash": _hash("a")},
        "dependency_proof_refs": [],
        "supersedes_attempt_id": None,
    }
    with kernel.connect() as conn:
        conn.execute(
            "INSERT INTO companies(company_id, company_key, display_name, "
            "executive_authority_ref, creation_request_id, creation_request_hash, created_at) "
            "VALUES (?, 'protected-broker', 'Protected Broker', ?, 'company-request', ?, ?)",
            (COMPANY_ID, OWNER, _hash("1"), NOW_TEXT),
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
                _hash("2"),
                OWNER,
                OWNER,
                _hash("3"),
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
            ) VALUES (?, ?, 1, NULL, '{}', ?, '', '', ?, 'protected-plan',
                      'plan-request', ?, ?)
            """,
            (PLAN_ID, MISSION_ID, _hash("4"), OWNER, _hash("5"), NOW_TEXT),
        )
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = ?, plan_state_version = 1, "
            "kernel_state_version = 1 WHERE mission_id = ?",
            (PLAN_ID, MISSION_ID),
        )
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
            ) VALUES (?, ?, ?, 'protected-package', ?, ?, ?, 1, 'v1', '{}', ?,
                      'single_active', ?, ?, '', '', '', 'package-request', ?, ?)
            """,
            (
                PACKAGE_ID,
                MISSION_ID,
                PLAN_ID,
                OUTCOME_ID,
                PROJECT_ID,
                RESOURCE_ID,
                _hash("6"),
                OWNER,
                OWNER,
                _hash("7"),
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
            ) VALUES (?, 'reasoning', 'task-request', ?, 'soma_reasoning',
                      'reasoning_backend', ?, '{}', 'repository', 'sample',
                      'running', 'backend_running', 5, ?, ?, ?)
            """,
            (TASK_ID, _hash("8"), BACKEND_REF, NOW_TEXT, NOW_TEXT, NOW_TEXT),
        )
        conn.execute(
            """
            INSERT INTO work_package_attempts(
                attempt_id, work_package_id, outcome_id, task_id,
                route_request_hash, route_descriptor_json, supersedes_attempt_id,
                containment_evidence_ref, containment_evidence_hash,
                controller_request_id, request_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, '', '', 'attempt-request', ?, ?)
            """,
            (
                ATTEMPT_ID,
                PACKAGE_ID,
                OUTCOME_ID,
                TASK_ID,
                _hash("9"),
                json.dumps(route, sort_keys=True, separators=(",", ":")),
                _hash("a"),
                NOW_TEXT,
            ),
        )
        conn.execute(
            """
            INSERT INTO project_task_reservations(
                task_id, project_id, scope_generation, status, created_at, updated_at
            ) VALUES (?, ?, 1, 'attached', ?, ?)
            """,
            (TASK_ID, PROJECT_ID, NOW_TEXT, NOW_TEXT),
        )
        conn.execute(
            """
            INSERT INTO project_run_attempts(
                run_id, project_id, task_id, resource_id, scope_generation,
                status, recovery_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, 'attached', '', ?, ?)
            """,
            (BACKEND_REF, PROJECT_ID, TASK_ID, RESOURCE_ID, NOW_TEXT, NOW_TEXT),
        )
    return runs, kernel


def _call(**overrides) -> ProtectedToolCallV1:
    payload = {
        "call_request_id": "protected-broker-call-1",
        "task_id": TASK_ID,
        "attempt_id": ATTEMPT_ID,
        "backend_ref": BACKEND_REF,
        "mandate_ref": "mandate:protected-broker",
        "mandate_hash": _hash("b"),
        "mandate_version": "v1",
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "scope_generation": 1,
        "capability_ref": "capability:repository-write",
        "capability_hash": _hash("c"),
        "tool_operation_ref": "tool-operation:fake-write",
        "tool_operation_hash": _hash("d"),
        "resource_key": "repository:d:/github/soma",
        "idempotency_key": "soma-slot:protected-broker/action-1",
        "payload_ref": "payload:protected-broker",
        "payload_hash": _payload_hash(),
        "expected_task_state_version": 5,
        "expires_at": NOW + timedelta(minutes=30),
        "mutation_class": "repository",
        "provider_provenance_refs": (
            ProtectedProviderProvenanceRefV1(
                ref="provider-call:broker-1", hash=_hash("e")
            ),
        ),
    }
    payload.update(overrides)
    return ProtectedToolCallV1(**payload)


def _snapshot(call: ProtectedToolCallV1, **overrides) -> ProtectedAuthoritySnapshotV1:
    payload = {
        "mandate_ref": call.mandate_ref,
        "mandate_hash": call.mandate_hash,
        "mandate_version": call.mandate_version,
        "mandate_active": True,
        "capability_ref": call.capability_ref,
        "capability_hash": call.capability_hash,
        "capability_possessed": True,
        "tool_operation_ref": call.tool_operation_ref,
        "tool_operation_hash": call.tool_operation_hash,
        "tool_operation_enabled": True,
        "idempotency_key": call.idempotency_key,
        "idempotency_authorized": True,
        "approval_required": False,
        "approval_valid": False,
    }
    payload.update(overrides)
    return ProtectedAuthoritySnapshotV1(**payload)


class FakeAuthorityResolver:
    def __init__(self, overrides=None):
        self.overrides = dict(overrides or {})
        self.calls = 0

    def resolve(self, call: ProtectedToolCallV1) -> ProtectedAuthoritySnapshotV1:
        self.calls += 1
        return _snapshot(call, **self.overrides)


class FakeResourceGuard:
    def __init__(self, *, available: bool = True):
        self.available = available
        self.acquire_calls = 0
        self.release_calls = 0
        self.held: set[str] = set()

    def acquire(self, call: ProtectedToolCallV1) -> ProtectedResourceLeaseV1:
        self.acquire_calls += 1
        owner = f"task:{call.task_id}/attempt:{call.attempt_id}"
        if not self.available or call.resource_key in self.held:
            return ProtectedResourceLeaseV1(
                acquired=False,
                resource_key=call.resource_key,
                owner_ref=owner,
                evidence_ref="lease-evidence:busy",
                evidence_hash=_hash("f"),
                reason="resource busy",
            )
        self.held.add(call.resource_key)
        return ProtectedResourceLeaseV1(
            acquired=True,
            resource_key=call.resource_key,
            owner_ref=owner,
            lease_ref=f"fake-lease:{call.resource_key}",
            evidence_ref="lease-evidence:acquired",
            evidence_hash=_hash("f"),
        )

    def release(self, lease: ProtectedResourceLeaseV1) -> None:
        self.release_calls += 1
        self.held.discard(lease.resource_key)


class FakeProtectedAdapter:
    def __init__(self, *, mode: str = "acknowledged", hook=None):
        self.mode = mode
        self.hook = hook
        self.calls = 0

    def execute(
        self, call: ProtectedToolCallV1, payload: bytes
    ) -> ProtectedAdapterResultV1:
        self.calls += 1
        assert payload == PAYLOAD
        if self.hook is not None:
            self.hook(call)
        if self.mode == "raise":
            raise RuntimeError("fake external transport disappeared after send")
        if self.mode == "rejected":
            return ProtectedAdapterResultV1(
                disposition="rejected",
                evidence_ref="fake-adapter:rejected",
                evidence_hash=_hash("1"),
            )
        if self.mode == "outcome_unknown":
            return ProtectedAdapterResultV1(
                disposition="outcome_unknown",
                evidence_ref="fake-adapter:ambiguous",
                evidence_hash=_hash("2"),
            )
        return ProtectedAdapterResultV1(
            disposition="acknowledged",
            external_effect_ref="fake-effect:1",
            external_effect_hash=_hash("3"),
            evidence_ref="fake-adapter:acknowledged",
            evidence_hash=_hash("4"),
        )


def _broker(
    tmp_path: Path,
    *,
    authority_overrides=None,
    resource_guard=None,
    adapter=None,
):
    runs, kernel = _prepare_db(tmp_path)
    resolver = FakeAuthorityResolver(authority_overrides)
    guard = resource_guard or FakeResourceGuard()
    fake = adapter or FakeProtectedAdapter()
    broker = ProtectedToolBroker(
        store=ProtectedToolStore(runs),
        authority_resolver=resolver,
        resource_guard=guard,
        adapter=fake,
        clock=lambda: NOW,
    )
    return broker, resolver, guard, fake, kernel


def _accepted_cancel(kernel: CompanyKernelStore) -> None:
    with kernel.connect() as conn:
        conn.execute(
            """
            INSERT INTO task_commands(
                command_id, task_id, command_kind, controller_request_id,
                requested_state_version, observed_state_version, status,
                reason, created_at, completed_at
            ) VALUES ('taskcmd_cancel_fixture', ?, 'cancel', 'cancel-request',
                      5, 5, 'accepted', 'fixture cancellation', ?, NULL)
            """,
            (TASK_ID, NOW_TEXT),
        )


def test_happy_path_revalidates_authority_and_calls_fake_adapter_once(
    tmp_path: Path,
) -> None:
    broker, resolver, guard, adapter, _kernel = _broker(tmp_path)
    result = broker.execute(_call(), PAYLOAD)

    assert result.effect.disposition == "acknowledged"
    assert result.effect.external_effect_ref == "fake-effect:1"
    assert result.adapter_called is True
    assert result.replayed is False
    assert resolver.calls == 1
    assert guard.acquire_calls == 1
    assert guard.release_calls == 1
    assert adapter.calls == 1


def test_exact_replay_with_new_provider_provenance_never_calls_adapter_twice(
    tmp_path: Path,
) -> None:
    broker, resolver, guard, adapter, _kernel = _broker(tmp_path)
    first = broker.execute(_call(), PAYLOAD)
    replay_call = _call(
        call_request_id="protected-broker-provider-retry",
        provider_provenance_refs=(
            ProtectedProviderProvenanceRefV1(
                ref="provider-thread:new", hash=_hash("9")
            ),
        ),
    )
    second = broker.execute(replay_call, PAYLOAD)

    assert second.replayed is True
    assert second.adapter_called is False
    assert second.call.call_request_id == first.call.call_request_id
    assert second.effect.effect_hash == first.effect.effect_hash
    assert adapter.calls == 1
    assert guard.acquire_calls == 1
    assert resolver.calls == 1


@pytest.mark.parametrize(
    ("call_overrides", "expected_evidence"),
    [
        ({"expected_task_state_version": 6}, "stale_task_state_version"),
        ({"backend_ref": "reasoning-backend:wrong"}, "backend_binding_mismatch"),
        ({"attempt_id": "wpattempt_" + "7" * 24}, "attempt_binding_mismatch"),
        ({"scope_generation": 2}, "attempt_scope_mismatch"),
        ({"expires_at": NOW}, "call_expired"),
    ],
)
def test_durable_task_attempt_scope_and_expiry_failures_prevent_before_adapter(
    tmp_path: Path, call_overrides, expected_evidence: str
) -> None:
    broker, _resolver, guard, adapter, _kernel = _broker(tmp_path)
    result = broker.execute(_call(**call_overrides), PAYLOAD)
    assert result.effect.disposition == "prevented"
    assert result.effect.evidence_ref == f"broker-prevented:{expected_evidence}"
    assert result.adapter_called is False
    assert guard.acquire_calls == 0
    assert adapter.calls == 0


def test_payload_hash_is_revalidated_from_actual_bytes(tmp_path: Path) -> None:
    broker, _resolver, guard, adapter, _kernel = _broker(tmp_path)
    result = broker.execute(_call(), b"different bytes")
    assert result.effect.disposition == "prevented"
    assert result.effect.evidence_ref == "broker-prevented:payload_hash_mismatch"
    assert guard.acquire_calls == 0
    assert adapter.calls == 0


@pytest.mark.parametrize(
    ("authority_overrides", "expected_code"),
    [
        ({"mandate_active": False}, "mandate_mismatch"),
        ({"mandate_version": "v2"}, "mandate_mismatch"),
        ({"capability_possessed": False}, "capability_mismatch"),
        ({"tool_operation_enabled": False}, "tool_operation_mismatch"),
        ({"idempotency_authorized": False}, "idempotency_unauthorized"),
        (
            {
                "approval_required": True,
                "approval_valid": False,
                "approval_evidence_ref": "",
                "approval_evidence_hash": "",
            },
            "approval_missing",
        ),
    ],
)
def test_mechanical_authority_resolver_failures_prevent_effect(
    tmp_path: Path, authority_overrides, expected_code: str
) -> None:
    broker, resolver, guard, adapter, _kernel = _broker(
        tmp_path, authority_overrides=authority_overrides
    )
    result = broker.execute(_call(), PAYLOAD)
    assert result.effect.disposition == "prevented"
    assert result.effect.evidence_ref == f"broker-prevented:{expected_code}"
    assert resolver.calls == 1
    assert guard.acquire_calls == 0
    assert adapter.calls == 0


def test_valid_required_approval_is_mechanical_hashed_evidence(tmp_path: Path) -> None:
    broker, _resolver, _guard, adapter, _kernel = _broker(
        tmp_path,
        authority_overrides={
            "approval_required": True,
            "approval_valid": True,
            "approval_evidence_ref": "approval:fixture",
            "approval_evidence_hash": _hash("5"),
        },
    )
    result = broker.execute(_call(), PAYLOAD)
    assert result.effect.disposition == "acknowledged"
    assert adapter.calls == 1


def test_cancellation_precedence_blocks_new_effect(tmp_path: Path) -> None:
    broker, _resolver, guard, adapter, kernel = _broker(tmp_path)
    _accepted_cancel(kernel)
    result = broker.execute(_call(), PAYLOAD)
    assert result.effect.disposition == "prevented"
    assert result.effect.evidence_ref == "broker-prevented:cancellation_precedence"
    assert guard.acquire_calls == 0
    assert adapter.calls == 0


def test_old_plan_attempt_cannot_start_new_protected_effect(tmp_path: Path) -> None:
    broker, _resolver, guard, adapter, kernel = _broker(tmp_path)
    with kernel.connect() as conn:
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = NULL, plan_state_version = 2 "
            "WHERE mission_id = ?",
            (MISSION_ID,),
        )
    result = broker.execute(_call(), PAYLOAD)
    assert result.effect.disposition == "prevented"
    assert result.effect.evidence_ref == "broker-prevented:attempt_not_current_plan"
    assert guard.acquire_calls == 0
    assert adapter.calls == 0


def test_transient_resource_contention_leaves_call_reserved_for_safe_retry(
    tmp_path: Path,
) -> None:
    guard = FakeResourceGuard(available=False)
    broker, _resolver, _same_guard, adapter, _kernel = _broker(
        tmp_path, resource_guard=guard
    )
    call = _call()
    with pytest.raises(ProtectedResourceUnavailable):
        broker.execute(call, PAYLOAD)
    observation = broker.store.get_observation(call.call_request_id)
    assert observation["delivery_state"] == "reserved"
    assert observation["effect"] is None
    assert adapter.calls == 0

    guard.available = True
    result = broker.execute(call, PAYLOAD)
    assert result.effect.disposition == "acknowledged"
    assert adapter.calls == 1


def test_adapter_exception_after_effect_boundary_becomes_outcome_unknown_and_holds_lease(
    tmp_path: Path,
) -> None:
    guard = FakeResourceGuard()
    adapter = FakeProtectedAdapter(mode="raise")
    broker, _resolver, _guard, _adapter, _kernel = _broker(
        tmp_path, resource_guard=guard, adapter=adapter
    )
    call = _call()
    first = broker.execute(call, PAYLOAD)
    assert first.effect.disposition == "outcome_unknown"
    assert first.adapter_called is True
    assert adapter.calls == 1
    assert guard.release_calls == 0

    replay = broker.execute(call, PAYLOAD)
    assert replay.replayed is True
    assert replay.adapter_called is False
    assert replay.effect.effect_hash == first.effect.effect_hash
    assert adapter.calls == 1
    assert guard.release_calls == 0


def test_restart_after_effect_boundary_without_terminal_result_never_resends(
    tmp_path: Path,
) -> None:
    runs, _kernel = _prepare_db(tmp_path)
    store = ProtectedToolStore(runs)
    call, _ = store.reserve_call(_call())
    store.claim_effect_boundary(
        call_request_id=call.call_request_id,
        request_hash=call.request_hash,
        evidence_ref="lease-evidence:crash-window",
        evidence_hash=_hash("6"),
    )
    adapter = FakeProtectedAdapter()
    broker = ProtectedToolBroker(
        store=ProtectedToolStore(runs),
        authority_resolver=FakeAuthorityResolver(),
        resource_guard=FakeResourceGuard(),
        adapter=adapter,
        clock=lambda: NOW,
    )
    result = broker.execute(_call(), PAYLOAD)
    assert result.effect.disposition == "outcome_unknown"
    assert result.adapter_called is False
    assert result.replayed is True
    assert adapter.calls == 0


def test_cancellation_arriving_after_effect_boundary_does_not_fabricate_reversal(
    tmp_path: Path,
) -> None:
    runs, kernel = _prepare_db(tmp_path)

    def cancel_during_adapter(_call_value):
        _accepted_cancel(kernel)

    guard = FakeResourceGuard()
    adapter = FakeProtectedAdapter(hook=cancel_during_adapter)
    broker = ProtectedToolBroker(
        store=ProtectedToolStore(runs),
        authority_resolver=FakeAuthorityResolver(),
        resource_guard=guard,
        adapter=adapter,
        clock=lambda: NOW,
    )
    result = broker.execute(_call(), PAYLOAD)
    assert result.effect.disposition == "acknowledged"
    assert result.effect.external_effect_ref == "fake-effect:1"
    assert adapter.calls == 1
    assert guard.release_calls == 1


def test_rejected_external_result_releases_resource_and_is_durable(
    tmp_path: Path,
) -> None:
    guard = FakeResourceGuard()
    adapter = FakeProtectedAdapter(mode="rejected")
    broker, _resolver, _guard, _adapter, _kernel = _broker(
        tmp_path, resource_guard=guard, adapter=adapter
    )
    result = broker.execute(_call(), PAYLOAD)
    assert result.effect.disposition == "rejected"
    assert guard.release_calls == 1
    assert broker.execute(_call(), PAYLOAD).replayed is True
    assert adapter.calls == 1
