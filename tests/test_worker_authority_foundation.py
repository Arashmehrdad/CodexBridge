"""V3-2-AUTHORITY-FOUNDATION-1 positive worker authority proofs."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from soma.project_scope import ProjectScopeStore
from soma.protected_tools.models import ProtectedToolCallV1
from soma.run_store import RunStore
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    TaskPhase,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.store import TaskStore
from soma.worker_authority import (
    WORKER_AUTHORITY_SCHEMA_VERSION,
    WorkerAuthorityConflict,
    WorkerAuthorityService,
    WorkerAuthorityStore,
    WorkerAuthorizationDenied,
    WorkerAuthorizationRequestV1,
    WorkerCapabilityGrantIssueV1,
    WorkerOperationRegistry,
    WorkerOperationSpecV1,
    WorkerPrincipalIssueV1,
    WorkerProtectedAuthorityResolver,
)
from soma.worker_substrate import (
    SessionBindingDisposition,
    WorkerSubstrateStore,
)


PROJECT_ID = "Project_Worker_Authority"
RESOURCE_ID = "Resource_Worker_Authority"
TASK_ID = "task_20260814T160000Z_aaaaaaaaaaaa"
RUN_ID = "20260814T160000Z_worker_aaaaaaaa"
OWNER = "owner-controller:worker-authority"
ROLE = "role-context:implementation-worker"
MANDATE_REF = "mandate:worker-authority-fixture"
MANDATE_HASH = "a" * 64
INTENT_REF = "intent:worker-authority-fixture"
INTENT_HASH = "b" * 64
NOW = datetime(2026, 8, 14, 16, 0, tzinfo=timezone.utc)


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


QUERY_SPEC = WorkerOperationSpecV1(
    operation_ref="worker-operation:inspect-result",
    operation_kind="query",
    requires_session=True,
    allowed_task_states=("running",),
    description="Read one bounded worker result projection.",
)
PROTECTED_SPEC = WorkerOperationSpecV1(
    operation_ref="worker-operation:fake-protected-write",
    operation_kind="protected_mutation",
    requires_session=True,
    allowed_task_states=("running",),
    description="Fixture-only protected mutation identity.",
)
APPROVAL_PROTECTED_SPEC = WorkerOperationSpecV1(
    operation_ref="worker-operation:approval-protected-write",
    operation_kind="protected_mutation",
    requires_session=True,
    allowed_task_states=("running",),
    approval_required=True,
    description="Fixture-only protected mutation requiring independent approval.",
)


def _prepare(tmp_path: Path):
    runs = tmp_path / "runs"
    authority_store = WorkerAuthorityStore(runs)
    assert authority_store.is_installed() is False
    assert authority_store.init_db() == [1]
    assert authority_store.init_db() == []

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    scope = ProjectScopeStore(runs)
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="worker-authority",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )

    run_store = RunStore(runs)
    run_store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="fixture",
        run_dir=runs / RUN_ID,
        input_data={"fixture": True},
        status="running",
    )
    task_store = TaskStore(runs)
    normalized = normalize_durable_command_request(
        repo_name="sample",
        profile_id="fixture",
        argv=["fixture"],
    )
    task_store.reserve_task(
        task_id=TASK_ID,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id="worker-authority-task",
        request_hash=normalized_request_hash(normalized),
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="fixture",
        backend_ref=RUN_ID,
        backend_identity={"run_id": RUN_ID},
    )
    running = task_store.conditional_update(
        TASK_ID,
        fields={
            "state": "running",
            "phase": TaskPhase.BACKEND_RUNNING.value,
            "started_at": NOW.isoformat(),
        },
        expected_state_version=0,
        expected_states=("accepted",),
    )
    assert running is not None
    assert running.state_version == 1

    with scope.connect() as conn:
        conn.execute(
            "INSERT INTO project_task_reservations("
            "task_id, project_id, scope_generation, status, created_at, updated_at) "
            "VALUES (?, ?, 1, 'attached', ?, ?)",
            (TASK_ID, PROJECT_ID, NOW.isoformat(), NOW.isoformat()),
        )
        conn.execute(
            "INSERT INTO project_run_attempts("
            "run_id, project_id, task_id, resource_id, scope_generation, status, "
            "recovery_reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, 'attached', '', ?, ?)",
            (RUN_ID, PROJECT_ID, TASK_ID, RESOURCE_ID, NOW.isoformat(), NOW.isoformat()),
        )

    substrate = WorkerSubstrateStore(runs)
    binding, created = substrate.bind_provider_session(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=TASK_ID,
        run_id=RUN_ID,
        provider="fixture_provider",
        native_session_id="Provider-Native-Session-MixedCase-001",
        adapter_id="soma.adapter.fixture",
        adapter_version="1",
        protocol_id="fixture.protocol",
        protocol_version="1",
    )
    assert created is True
    assert binding.disposition is SessionBindingDisposition.BOUND

    registry = WorkerOperationRegistry(
        (QUERY_SPEC, PROTECTED_SPEC, APPROVAL_PROTECTED_SPEC)
    )
    service = WorkerAuthorityService(runs, registry=registry)
    return runs, service, task_store, scope, substrate, binding


def _issue(
    service: WorkerAuthorityService,
    binding_id: str,
    *,
    now: datetime = NOW,
    **overrides,
):
    payload = {
        "controller_request_id": "worker-principal-request-1",
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "scope_generation": 1,
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "session_binding_id": binding_id,
        "role_ref": ROLE,
        "mandate_ref": MANDATE_REF,
        "mandate_hash": MANDATE_HASH,
        "mandate_version": "v1",
        "issuer_ref": OWNER,
        "expires_at": NOW + timedelta(hours=2),
    }
    payload.update(overrides)
    return service.issue_principal(WorkerPrincipalIssueV1(**payload), now=now)


def _grant(
    service: WorkerAuthorityService,
    principal_id: str,
    *,
    spec: WorkerOperationSpecV1 = QUERY_SPEC,
    parameters: dict | None = None,
    request_id: str = "worker-grant-request-1",
    now: datetime = NOW,
):
    return service.issue_grant(
        WorkerCapabilityGrantIssueV1(
            controller_request_id=request_id,
            principal_id=principal_id,
            intent_ref=INTENT_REF,
            intent_hash=INTENT_HASH,
            operation_ref=spec.operation_ref,
            operation_hash=spec.operation_hash,
            parameter_contract=parameters or {},
            issuer_ref=OWNER,
            expires_at=NOW + timedelta(hours=1),
        ),
        now=now,
    )


def _auth_request(issue, grant, **overrides):
    payload = {
        "principal_id": issue.principal.principal_id,
        "credential": issue.credential_once,
        "grant_id": grant.grant_id,
        "role_ref": ROLE,
        "mandate_ref": MANDATE_REF,
        "mandate_hash": MANDATE_HASH,
        "mandate_version": "v1",
        "intent_ref": INTENT_REF,
        "intent_hash": INTENT_HASH,
        "operation_ref": grant.operation_ref,
        "operation_hash": grant.operation_hash,
        "parameters": grant.parameter_contract,
        "expected_task_state_version": 1,
    }
    payload.update(overrides)
    return WorkerAuthorizationRequestV1(**payload)


def test_schema_is_explicit_additive_and_inert_until_init(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    TaskStore(runs)
    store = WorkerAuthorityStore(runs)
    assert store.is_installed() is False
    before = sqlite3.connect(runs / "soma.sqlite3").execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'worker_authority%'"
    ).fetchall()
    assert before == []
    assert store.init_db() == [1]
    state = store.schema_state()
    assert state["schema_version"] == WORKER_AUTHORITY_SCHEMA_VERSION
    assert state["up_to_date"] is True
    assert state["live_worker_surface"] is False
    assert store.table_counts() == {
        "worker_principals": 0,
        "worker_capability_grants": 0,
        "worker_authority_revocations": 0,
    }


def test_principal_credential_is_one_time_and_never_persisted_plaintext(tmp_path: Path) -> None:
    runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    assert issued.created is True
    assert issued.credential_once is not None
    assert issued.credential_once.startswith("wa1_")
    assert issued.credential_once not in str(issued.principal.public_projection())
    assert "verifier_hash" not in issued.principal.public_projection()

    replay = _issue(service, binding.session_binding_id)
    assert replay.created is False
    assert replay.principal.principal_id == issued.principal.principal_id
    assert replay.credential_once is None

    db_path = runs / "soma.sqlite3"
    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            "SELECT verifier_hash, principal_json FROM worker_principals "
            "WHERE principal_id = ?",
            (issued.principal.principal_id,),
        ).fetchone()
    assert stored is not None
    assert stored[0] == issued.principal.verifier_hash
    assert issued.credential_once not in stored[1]
    for candidate in (db_path, Path(str(db_path) + "-wal")):
        if candidate.exists():
            assert issued.credential_once.encode("utf-8") not in candidate.read_bytes()


def test_principal_replay_conflict_and_wrong_credential_fail_closed(tmp_path: Path) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    expired_replay = _issue(
        service,
        binding.session_binding_id,
        now=NOW + timedelta(hours=3),
    )
    assert expired_replay.created is False
    assert expired_replay.principal.principal_id == issued.principal.principal_id
    assert expired_replay.credential_once is None
    with pytest.raises(WorkerAuthorityConflict):
        _issue(
            service,
            binding.session_binding_id,
            now=NOW + timedelta(hours=3),
            role_ref="role-context:different",
        )
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authenticate(issued.principal.principal_id, "wa1_wrong-secret")
    assert excinfo.value.code == "credential_invalid"


def test_principal_issue_rejects_wrong_scope_task_run_and_session(tmp_path: Path) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    cases = (
        {"controller_request_id": "wrong-resource", "resource_id": "Resource_Other"},
        {"controller_request_id": "wrong-task", "task_id": "task_20260814T160000Z_bbbbbbbbbbbb"},
        {"controller_request_id": "wrong-run", "run_id": "20260814T160000Z_worker_bbbbbbbb"},
        {"controller_request_id": "wrong-session", "session_binding_id": "wsession_20260814T160000Z_bbbbbbbbbbbb"},
    )
    for override in cases:
        with pytest.raises(WorkerAuthorizationDenied):
            _issue(service, binding.session_binding_id, **override)


def test_no_grant_means_no_operation_and_exact_grant_authorizes(tmp_path: Path) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    fake_grant_id = "wgrant_" + "f" * 24
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(
            WorkerAuthorizationRequestV1(
                principal_id=issued.principal.principal_id,
                credential=issued.credential_once,
                grant_id=fake_grant_id,
                role_ref=ROLE,
                mandate_ref=MANDATE_REF,
                mandate_hash=MANDATE_HASH,
                mandate_version="v1",
                intent_ref=INTENT_REF,
                intent_hash=INTENT_HASH,
                operation_ref=QUERY_SPEC.operation_ref,
                operation_hash=QUERY_SPEC.operation_hash,
                parameters={},
                expected_task_state_version=1,
            ),
            now=NOW,
        )
    assert excinfo.value.code == "grant_missing"

    grant, created = _grant(service, issued.principal.principal_id)
    assert created is True
    decision = service.authorize(_auth_request(issued, grant), now=NOW)
    assert decision.authorized is True
    assert decision.principal_id == issued.principal.principal_id
    assert decision.grant_id == grant.grant_id
    assert decision.task_id == TASK_ID
    assert decision.run_id == RUN_ID


def test_grant_replay_converges_and_content_duplicate_conflicts(tmp_path: Path) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    first, created = _grant(service, issued.principal.principal_id)
    replay, replay_created = _grant(service, issued.principal.principal_id)
    expired_replay, expired_replay_created = _grant(
        service,
        issued.principal.principal_id,
        now=NOW + timedelta(hours=3),
    )
    assert created is True
    assert replay_created is False
    assert expired_replay_created is False
    assert replay.grant_id == first.grant_id
    assert expired_replay.grant_id == first.grant_id
    with pytest.raises(WorkerAuthorityConflict):
        _grant(
            service,
            issued.principal.principal_id,
            request_id="different-controller-request",
        )
    with pytest.raises(WorkerAuthorityConflict):
        _grant(
            service,
            issued.principal.principal_id,
            now=NOW + timedelta(hours=3),
            parameters={"different": True},
        )


def test_operation_description_is_not_authority_identity() -> None:
    changed_description = QUERY_SPEC.model_copy(
        update={"description": "Different documentation wording only."}
    )
    changed_policy = QUERY_SPEC.model_copy(update={"approval_required": True})
    assert changed_description.operation_hash == QUERY_SPEC.operation_hash
    assert changed_policy.operation_hash != QUERY_SPEC.operation_hash


def test_wrong_authenticated_principal_cannot_use_another_principal_grant(tmp_path: Path) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    first = _issue(service, binding.session_binding_id)
    first_grant, _ = _grant(service, first.principal.principal_id)
    second = _issue(
        service,
        binding.session_binding_id,
        controller_request_id="worker-principal-request-2",
    )
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(_auth_request(second, first_grant), now=NOW)
    assert excinfo.value.code == "grant_principal_mismatch"


def test_role_mandate_intent_operation_state_and_parameters_are_exact(tmp_path: Path) -> None:
    _runs, service, task_store, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    grant, _ = _grant(service, issued.principal.principal_id, parameters={"view": "summary"})
    cases = (
        {"role_ref": "role-context:other"},
        {"mandate_hash": "c" * 64},
        {"intent_hash": "d" * 64},
        {"operation_ref": PROTECTED_SPEC.operation_ref, "operation_hash": PROTECTED_SPEC.operation_hash},
        {"parameters": {"view": "full"}},
        {"expected_task_state_version": 999},
    )
    for override in cases:
        with pytest.raises(WorkerAuthorizationDenied):
            service.authorize(_auth_request(issued, grant, **override), now=NOW)

    changed = task_store.conditional_update(
        TASK_ID,
        fields={"state": "paused", "phase": ""},
        expected_state_version=1,
        expected_states=("running",),
    )
    assert changed is not None
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(
            _auth_request(issued, grant, expected_task_state_version=2),
            now=NOW,
        )
    assert excinfo.value.code == "task_state_not_allowed"


def test_scope_generation_and_session_disposition_are_revalidated(tmp_path: Path) -> None:
    _runs, service, _task, scope, substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    grant, _ = _grant(service, issued.principal.principal_id)
    substrate.set_binding_disposition(
        binding.session_binding_id,
        disposition=SessionBindingDisposition.MISMATCH_DETECTED,
        reason="fixture mismatch",
    )
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(_auth_request(issued, grant), now=NOW)
    assert excinfo.value.code == "session_not_bound"

    substrate.set_binding_disposition(
        binding.session_binding_id,
        disposition=SessionBindingDisposition.BOUND,
        reason="fixture restored",
    )
    with scope.connect() as conn:
        conn.execute(
            "UPDATE projects SET scope_generation = 2, updated_at = ? WHERE project_id = ?",
            (NOW.isoformat(), PROJECT_ID),
        )
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(_auth_request(issued, grant), now=NOW)
    assert excinfo.value.code == "project_scope_mismatch"


def test_task_cancellation_precedence_denies_new_actions(tmp_path: Path) -> None:
    _runs, service, _task, scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    grant, _ = _grant(service, issued.principal.principal_id)
    with scope.connect() as conn:
        conn.execute(
            "INSERT INTO task_commands("
            "command_id, task_id, command_kind, controller_request_id, "
            "requested_state_version, observed_state_version, status, reason, created_at) "
            "VALUES ('taskcmd_20260814T160000Z_bbbbbbbbbbbb', ?, 'cancel', "
            "'cancel-fixture', 1, 1, 'accepted', 'fixture', ?)",
            (TASK_ID, NOW.isoformat()),
        )
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(_auth_request(issued, grant), now=NOW)
    assert excinfo.value.code == "cancellation_precedence"


def test_principal_and_grant_revocations_deny_new_actions(tmp_path: Path) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    grant, _ = _grant(service, issued.principal.principal_id)
    revoked, created = service.store.revoke(
        target_kind="grant",
        target_id=grant.grant_id,
        controller_request_id="revoke-grant-1",
        reason_ref="reason:test",
        reason_hash=_hash("revoke-grant"),
        issuer_ref=OWNER,
        revoked_at=NOW,
    )
    assert created is True
    replay, replay_created = service.store.revoke(
        target_kind="grant",
        target_id=grant.grant_id,
        controller_request_id="revoke-grant-1",
        reason_ref="reason:test",
        reason_hash=_hash("revoke-grant"),
        issuer_ref=OWNER,
        revoked_at=NOW + timedelta(minutes=1),
    )
    assert replay_created is False
    assert replay.revocation_id == revoked.revocation_id
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(_auth_request(issued, grant), now=NOW)
    assert excinfo.value.code == "grant_revoked"

    other = _issue(
        service,
        binding.session_binding_id,
        controller_request_id="worker-principal-request-2",
    )
    other_grant, _ = _grant(
        service,
        other.principal.principal_id,
        request_id="worker-grant-request-2",
    )
    service.store.revoke(
        target_kind="principal",
        target_id=other.principal.principal_id,
        controller_request_id="revoke-principal-1",
        reason_ref="reason:test",
        reason_hash=_hash("revoke-principal"),
        issuer_ref=OWNER,
        revoked_at=NOW,
    )
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(_auth_request(other, other_grant), now=NOW)
    assert excinfo.value.code == "principal_revoked"


def test_expiry_denies_principal_and_grant(tmp_path: Path) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    grant, _ = _grant(service, issued.principal.principal_id)
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(_auth_request(issued, grant), now=NOW + timedelta(hours=1, seconds=1))
    assert excinfo.value.code == "grant_expired"
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        service.authorize(_auth_request(issued, grant), now=NOW + timedelta(hours=2))
    assert excinfo.value.code == "principal_expired"


def test_provider_local_ids_are_provenance_not_authority_identity(tmp_path: Path) -> None:
    runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    grant, _ = _grant(service, issued.principal.principal_id)
    principal_json = service.store.get_principal(issued.principal.principal_id).model_dump(mode="json")
    grant_json = service.store.get_grant(grant.grant_id).model_dump(mode="json")
    serialized = str(principal_json) + str(grant_json)
    assert "fixture_provider" not in serialized
    assert "Provider-Native-Session-MixedCase-001" not in serialized
    assert "soma.adapter.fixture" not in serialized
    assert binding.session_binding_id in serialized
    assert service.authorize(_auth_request(issued, grant), now=NOW).authorized is True
    assert (runs / "soma.sqlite3").exists()


def test_reopen_preserves_same_authority_result(tmp_path: Path) -> None:
    runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    grant, _ = _grant(service, issued.principal.principal_id)
    first = service.authorize(_auth_request(issued, grant), now=NOW)
    reopened = WorkerAuthorityService(
        runs,
        registry=WorkerOperationRegistry(
            (QUERY_SPEC, PROTECTED_SPEC, APPROVAL_PROTECTED_SPEC)
        ),
    )
    second = reopened.authorize(_auth_request(issued, grant), now=NOW)
    assert second == first


def test_protected_resolver_yields_only_g4_snapshot_and_no_effect_record(tmp_path: Path) -> None:
    runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    payload_hash = _hash("fake protected payload")
    parameters = {
        "resource_key": "repository:fixture",
        "payload_hash": payload_hash,
        "mutation_class": "repository",
    }
    grant, _ = _grant(
        service,
        issued.principal.principal_id,
        spec=PROTECTED_SPEC,
        parameters=parameters,
    )
    idempotency = service.protected_idempotency_key(grant)
    call = ProtectedToolCallV1(
        call_request_id="protected-worker-call-1",
        task_id=TASK_ID,
        attempt_id="wpattempt_aaaaaaaaaaaaaaaaaaaaaaaa",
        backend_ref=RUN_ID,
        mandate_ref=MANDATE_REF,
        mandate_hash=MANDATE_HASH,
        mandate_version="v1",
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        capability_ref=grant.capability_ref,
        capability_hash=grant.capability_hash,
        tool_operation_ref=grant.operation_ref,
        tool_operation_hash=grant.operation_hash,
        resource_key=parameters["resource_key"],
        idempotency_key=idempotency,
        payload_ref="payload:fixture",
        payload_hash=payload_hash,
        expected_task_state_version=1,
        expires_at=NOW + timedelta(minutes=30),
        mutation_class="repository",
        provider_provenance_refs=(),
    )
    with sqlite3.connect(runs / "soma.sqlite3") as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='protected_tool_calls'"
        ).fetchone()[0]
    assert before == 0
    snapshot = WorkerProtectedAuthorityResolver(service, now=NOW).resolve(call)
    assert snapshot.capability_possessed is True
    assert snapshot.tool_operation_enabled is True
    assert snapshot.idempotency_authorized is True
    assert snapshot.capability_ref == grant.capability_ref
    with sqlite3.connect(runs / "soma.sqlite3") as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='protected_tool_calls'"
        ).fetchone()[0]
    assert after == 0


def test_protected_resolver_carries_reviewed_approval_requirement_without_evidence(
    tmp_path: Path,
) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    payload_hash = _hash("approval protected payload")
    parameters = {
        "resource_key": "repository:approval-fixture",
        "payload_hash": payload_hash,
        "mutation_class": "repository",
    }
    grant, _ = _grant(
        service,
        issued.principal.principal_id,
        spec=APPROVAL_PROTECTED_SPEC,
        parameters=parameters,
        request_id="worker-grant-approval-request-1",
    )
    call = ProtectedToolCallV1(
        call_request_id="protected-worker-call-approval",
        task_id=TASK_ID,
        attempt_id="wpattempt_bbbbbbbbbbbbbbbbbbbbbbbb",
        backend_ref=RUN_ID,
        mandate_ref=MANDATE_REF,
        mandate_hash=MANDATE_HASH,
        mandate_version="v1",
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        capability_ref=grant.capability_ref,
        capability_hash=grant.capability_hash,
        tool_operation_ref=grant.operation_ref,
        tool_operation_hash=grant.operation_hash,
        resource_key=parameters["resource_key"],
        idempotency_key=service.protected_idempotency_key(grant),
        payload_ref="payload:approval-fixture",
        payload_hash=payload_hash,
        expected_task_state_version=1,
        expires_at=NOW + timedelta(minutes=30),
        mutation_class="repository",
        provider_provenance_refs=(),
    )
    snapshot = WorkerProtectedAuthorityResolver(service, now=NOW).resolve(call)
    assert snapshot.approval_required is True
    assert snapshot.approval_valid is False
    assert snapshot.approval_evidence_ref == ""
    assert snapshot.approval_evidence_hash == ""


def test_protected_resolver_denies_wrong_contract_and_marks_wrong_idempotency(tmp_path: Path) -> None:
    _runs, service, _task, _scope, _substrate, binding = _prepare(tmp_path)
    issued = _issue(service, binding.session_binding_id)
    payload_hash = _hash("fake protected payload")
    parameters = {
        "resource_key": "repository:fixture",
        "payload_hash": payload_hash,
        "mutation_class": "repository",
    }
    grant, _ = _grant(
        service,
        issued.principal.principal_id,
        spec=PROTECTED_SPEC,
        parameters=parameters,
    )
    base = {
        "call_request_id": "protected-worker-call-2",
        "task_id": TASK_ID,
        "attempt_id": "wpattempt_aaaaaaaaaaaaaaaaaaaaaaaa",
        "backend_ref": RUN_ID,
        "mandate_ref": MANDATE_REF,
        "mandate_hash": MANDATE_HASH,
        "mandate_version": "v1",
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "scope_generation": 1,
        "capability_ref": grant.capability_ref,
        "capability_hash": grant.capability_hash,
        "tool_operation_ref": grant.operation_ref,
        "tool_operation_hash": grant.operation_hash,
        "resource_key": "repository:fixture",
        "idempotency_key": "wrong-idempotency-key",
        "payload_ref": "payload:fixture",
        "payload_hash": payload_hash,
        "expected_task_state_version": 1,
        "expires_at": NOW + timedelta(minutes=30),
        "mutation_class": "repository",
        "provider_provenance_refs": (),
    }
    resolver = WorkerProtectedAuthorityResolver(service, now=NOW)
    snapshot = resolver.resolve(ProtectedToolCallV1(**base))
    assert snapshot.idempotency_authorized is False
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        resolver.resolve(ProtectedToolCallV1(**{**base, "payload_hash": _hash("wrong")}))
    assert excinfo.value.code == "parameter_contract_mismatch"
