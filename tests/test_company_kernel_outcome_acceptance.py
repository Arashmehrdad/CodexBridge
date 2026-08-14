"""V3-1B exact provider-neutral OutcomeAcceptance authority proofs."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from soma.company_kernel.acceptance import (
    OutcomeAcceptanceConflict,
    OutcomeAcceptanceRequestV1,
    accept_outcome,
)
from soma.company_kernel.dependencies import (
    DependencyEdgeContextV1,
    evaluate_accepted_outcome,
)
from soma.company_kernel.store import CompanyKernelStore
from soma.config import AppConfig, CompanyKernelRuntimeConfig, RepoConfig
from soma.project_scope.store import ProjectScopeStore
from soma.reasoning.fake import FakeReasoningBackend
from soma.reasoning.models import ReasoningBudgetsV1, ReasoningSpecV1
from soma.reasoning.store import ReasoningBackendStore
from soma.run_store import RunStore
from soma.tasks.models import BackendKind, TaskKind, make_task_id
from soma.tasks.store import TaskStore


OWNER = "owner-controller:outcome-acceptance"
COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
PLAN_ID = "planrev_" + "3" * 24
PACKAGE_ID = "workpkg_" + "4" * 24
OUTCOME_ID = "outcome_" + "5" * 24
ATTEMPT_ID = "wpattempt_" + "6" * 24
PROJECT_ID = "Project_Outcome_Acceptance"
RESOURCE_ID = "Resource_Outcome_Acceptance"
NOW = "2026-08-14T10:00:00+00:00"
RESULT_HASH = "a" * 64
SOURCE_HASH = "b" * 64
BASIS_HASH = "c" * 64


def _hash(character: str) -> str:
    return character * 64


def _config(tmp_path: Path) -> tuple[AppConfig, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        company_kernel=CompanyKernelRuntimeConfig(
            enabled=True,
            executive_authority_ref=OWNER,
        ),
        config_dir=tmp_path,
    )
    return config, repo


def _reasoning_spec() -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref="assignment:outcome-acceptance",
        assignment_hash=_hash("1"),
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash=_hash("2"),
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash=_hash("3"),
        authority_ref="authority:outcome-acceptance",
        authority_hash=_hash("4"),
        provider_route_ref="route:fake-outcome-acceptance",
        provider_route_hash=_hash("5"),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _insert_kernel_target(store: CompanyKernelStore, task_id: str) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO companies(company_id, company_key, display_name, "
            "executive_authority_ref, creation_request_id, creation_request_hash, created_at) "
            "VALUES (?, 'outcome-acceptance-company', 'Outcome Acceptance Company', ?, "
            "'outcome-company-request', ?, ?)",
            (COMPANY_ID, OWNER, _hash("1"), NOW),
        )
        conn.execute(
            """
            INSERT INTO missions(
                mission_id, company_id, mission_key, project_id, resource_id,
                scope_generation, mission_contract_json, mission_contract_hash,
                accountable_owner_ref, acceptance_authority_ref,
                current_plan_revision_id, plan_state_version, kernel_state_version,
                creation_request_id, creation_request_hash, created_at, updated_at
            ) VALUES (?, ?, 'outcome-acceptance-mission', ?, ?, 1, '{}', ?, ?, ?,
                      NULL, 0, 0, 'outcome-mission-request', ?, ?, ?)
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
                NOW,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO plan_revisions(
                plan_revision_id, mission_id, revision_number, parent_plan_revision_id,
                plan_contract_json, plan_content_hash, deliberation_ref,
                deliberation_hash, accepted_by_ref, acceptance_basis_ref,
                controller_request_id, request_hash, accepted_at
            ) VALUES (?, ?, 1, NULL, '{}', ?, '', '', ?, 'owner-plan',
                      'outcome-plan-request', ?, ?)
            """,
            (PLAN_ID, MISSION_ID, _hash("4"), OWNER, _hash("5"), NOW),
        )
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = ?, plan_state_version = 1, "
            "kernel_state_version = 1, updated_at = ? WHERE mission_id = ?",
            (PLAN_ID, NOW, MISSION_ID),
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
            ) VALUES (?, ?, ?, 'outcome', ?, ?, ?, 1, 'v1', '{}', ?,
                      'single_active', ?, ?, '', '', '', 'outcome-package-request', ?, ?)
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
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO work_package_attempts(
                attempt_id, work_package_id, outcome_id, task_id,
                route_request_hash, route_descriptor_json, supersedes_attempt_id,
                containment_evidence_ref, containment_evidence_hash,
                controller_request_id, request_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, '{}', NULL, '', '',
                      'outcome-attempt-request', ?, ?)
            """,
            (
                ATTEMPT_ID,
                PACKAGE_ID,
                OUTCOME_ID,
                task_id,
                _hash("8"),
                _hash("9"),
                NOW,
            ),
        )


def _attach_scope(
    scope: ProjectScopeStore,
    *,
    repo: Path,
    task_id: str,
    backend_ref: str,
    backend_kind: str,
) -> None:
    binding = scope.resolve_repository(
        project_id=PROJECT_ID,
        repo_name="sample",
        repository_root=repo,
    )
    with scope.transaction() as conn:
        scope.reserve_task_attempt(
            conn,
            binding=binding,
            task_id=task_id,
            run_id=backend_ref,
        )
        scope.attach_task(conn, task_id)
    assert scope.attach_attempt(backend_ref, backend_kind=backend_kind) is True


def _finish_task(
    store: CompanyKernelStore,
    *,
    task_id: str,
    result_ref: str,
    result_hash: str,
    evidence_ref: str,
) -> None:
    with store.connect() as conn:
        conn.execute(
            "UPDATE tasks SET state = 'completed', phase = 'result_published', "
            "recovery_state = 'none', recovery_reason = '', result_ref = ?, "
            "result_hash = ?, evidence_ref = ?, ended_at = ?, updated_at = ? "
            "WHERE task_id = ?",
            (
                result_ref,
                result_hash,
                evidence_ref,
                NOW,
                NOW,
                task_id,
            ),
        )


def _durable_environment(tmp_path: Path):
    config, repo = _config(tmp_path)
    store = CompanyKernelStore(config.resolve_runs_dir())
    assert store.init_db() == [1, 2, 3, 4]
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="outcome-acceptance",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    run_store = RunStore(config.resolve_runs_dir())
    run_id = "20260814T100000Z_fixture_abcdef12"
    run_dir = config.resolve_runs_dir() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="executable_profile",
        run_dir=run_dir,
        input_data={"fixture": True},
        status="completed",
    )
    task_store = TaskStore(config.resolve_runs_dir())
    task_id = make_task_id()
    task_store.reserve_task(
        task_id=task_id,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id="outcome-task-durable",
        request_hash=_hash("d"),
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="executable_profile",
        backend_ref=run_id,
        backend_identity={"run_id": run_id, "repo_name": "sample"},
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE runs SET status = 'completed', exit_code = 0, safety_failure = 0, "
            "recovery_reason = '', result_publication_status = 'published', "
            "result_published_hash = ?, result_published_at = ?, "
            "result_publication_error = '', public_result_source_sha256 = ?, "
            "public_result_status = 'ready', public_result_error = '' "
            "WHERE run_id = ?",
            (RESULT_HASH, NOW, SOURCE_HASH, run_id),
        )
    _finish_task(
        store,
        task_id=task_id,
        result_ref=run_id,
        result_hash=RESULT_HASH,
        evidence_ref=f"run_terminal:{run_id}",
    )
    _attach_scope(
        scope,
        repo=repo,
        task_id=task_id,
        backend_ref=run_id,
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
    )
    _insert_kernel_target(store, task_id)
    return config, store, scope, task_id, run_id, RESULT_HASH, SOURCE_HASH


def _reasoning_environment(tmp_path: Path):
    config, repo = _config(tmp_path)
    store = CompanyKernelStore(config.resolve_runs_dir())
    assert store.init_db() == [1, 2, 3, 4]
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="outcome-acceptance",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    fake = FakeReasoningBackend(reasoning_store, case="success")
    backend_ref = fake.reserve()
    observation = fake.start(_reasoning_spec(), backend_ref)
    assert observation.result_ref is not None
    assert observation.result_hash is not None
    assert observation.evidence_index_ref is not None
    result_ref = observation.result_ref
    result_hash = observation.result_hash
    evidence_index_ref = observation.evidence_index_ref
    task_store = TaskStore(config.resolve_runs_dir())
    task_id = make_task_id()
    task_store.reserve_task(
        task_id=task_id,
        task_kind=TaskKind.REASONING.value,
        controller_request_id="outcome-task-reasoning",
        request_hash=_hash("e"),
        backend_kind=BackendKind.SOMA_REASONING.value,
        backend_executor="reasoning_backend",
        backend_ref=backend_ref,
        backend_identity={"repo_name": "sample"},
    )
    _finish_task(
        store,
        task_id=task_id,
        result_ref=result_ref,
        result_hash=result_hash,
        evidence_ref=evidence_index_ref,
    )
    _attach_scope(
        scope,
        repo=repo,
        task_id=task_id,
        backend_ref=backend_ref,
        backend_kind=BackendKind.SOMA_REASONING.value,
    )
    _insert_kernel_target(store, task_id)
    return config, store, scope, fake, task_id, backend_ref, result_hash


def _request(
    *,
    task_id: str,
    backend_kind: str,
    backend_ref: str,
    result_hash: str,
    source_hash: str,
    controller_request_id: str = "outcome-accept-request-1",
    **changes,
) -> OutcomeAcceptanceRequestV1:
    payload = {
        "controller_request_id": controller_request_id,
        "company_id": COMPANY_ID,
        "mission_id": MISSION_ID,
        "plan_revision_id": PLAN_ID,
        "work_package_id": PACKAGE_ID,
        "outcome_id": OUTCOME_ID,
        "attempt_id": ATTEMPT_ID,
        "task_id": task_id,
        "backend_kind": backend_kind,
        "backend_ref": backend_ref,
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "scope_generation": 1,
        "expected_kernel_state_version": 1,
        "result_published_hash": result_hash,
        "public_result_source_sha256": source_hash,
        "acceptance_authority_ref": OWNER,
        "acceptance_basis_ref": "owner-review:outcome-acceptance",
        "acceptance_basis_hash": BASIS_HASH,
    }
    payload.update(changes)
    return OutcomeAcceptanceRequestV1.model_validate(payload)


def _acceptance_count(store: CompanyKernelStore) -> int:
    with store.connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM acceptance_commits").fetchone()[0])


def _kernel_version(store: CompanyKernelStore) -> int:
    with store.connect() as conn:
        return int(
            conn.execute(
                "SELECT kernel_state_version FROM missions WHERE mission_id = ?",
                (MISSION_ID,),
            ).fetchone()[0]
        )


def test_durable_run_acceptance_is_atomic_exact_and_request_replay_is_stable(
    tmp_path: Path,
) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )

    first = accept_outcome(
        config,
        request,
        store=store,
        scope_store=scope,
        accepted_at=NOW,
    )
    replay = accept_outcome(
        config,
        request,
        store=store,
        scope_store=scope,
        accepted_at="2026-08-14T11:00:00+00:00",
    )

    assert first.created is True
    assert first.replay_kind == "none"
    assert first.acceptance.backend_kind == "soma_durable_run"
    assert first.acceptance.backend_ref == run_id
    assert first.acceptance.run_id == run_id
    assert first.acceptance.result_published_hash == result_hash
    assert first.acceptance.public_result_source_sha256 == source_hash
    assert replay.created is False
    assert replay.replay_kind == "request"
    assert replay.request_hash == first.request_hash
    assert replay.acceptance == first.acceptance
    assert _acceptance_count(store) == 1
    assert _kernel_version(store) == 2


def test_reasoning_acceptance_uses_published_evidence_without_synthetic_run(
    tmp_path: Path,
) -> None:
    config, store, scope, fake, task_id, backend_ref, result_hash = (
        _reasoning_environment(tmp_path)
    )
    with store.connect() as conn:
        runs_before = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    request = _request(
        task_id=task_id,
        backend_kind="soma_reasoning",
        backend_ref=backend_ref,
        result_hash=result_hash,
        source_hash=result_hash,
    )

    result = accept_outcome(
        config,
        request,
        store=store,
        scope_store=scope,
        accepted_at=NOW,
    )

    with store.connect() as conn:
        runs_after = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    assert result.created is True
    assert result.acceptance.backend_kind == "soma_reasoning"
    assert result.acceptance.backend_ref == backend_ref
    assert result.acceptance.run_id is None
    assert result.acceptance.result_published_hash == result_hash
    assert result.acceptance.public_result_source_sha256 == result_hash
    assert fake.provider_create_calls == 1
    assert runs_before == runs_after == 0
    assert _acceptance_count(store) == 1
    assert _kernel_version(store) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"company_id": "company_" + "a" * 24},
        {"mission_id": "mission_" + "a" * 24},
        {"plan_revision_id": "planrev_" + "a" * 24},
        {"work_package_id": "workpkg_" + "a" * 24},
        {"outcome_id": "outcome_" + "a" * 24},
        {"attempt_id": "wpattempt_" + "a" * 24},
        {"task_id": "task_20260814T100000Z_aaaaaaaaaaaa"},
        {"backend_ref": "20260814T100000Z_fixture_deadbeef"},
        {"project_id": "Other_Project"},
        {"resource_id": "Other_Resource"},
        {"scope_generation": 2},
        {"expected_kernel_state_version": 2},
        {"result_published_hash": "d" * 64},
        {"public_result_source_sha256": "e" * 64},
    ],
)
def test_exact_identity_scope_version_and_publication_assertions_fail_closed(
    tmp_path: Path,
    changes: dict,
) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    request_args = {
        "task_id": task_id,
        "backend_kind": "soma_durable_run",
        "backend_ref": run_id,
        "result_hash": result_hash,
        "source_hash": source_hash,
    }
    request_args.update(changes)
    request = _request(**request_args)

    with pytest.raises(OutcomeAcceptanceConflict):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


def test_wrong_named_authority_is_rejected_before_mutation(tmp_path: Path) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
        acceptance_authority_ref="owner-controller:someone-else",
    )

    with pytest.raises(OutcomeAcceptanceConflict, match="trusted configuration"):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("state", "failed"),
        ("state", "cancelled"),
        ("recovery_state", "unresolved"),
        ("phase", "backend_terminal"),
        ("task_kind", "reasoning"),
        ("backend_executor", "reasoning_backend"),
    ],
)
def test_non_success_or_uncertain_task_never_accepts(
    tmp_path: Path,
    column: str,
    value: str,
) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    with store.connect() as conn:
        conn.execute(f"UPDATE tasks SET {column} = ? WHERE task_id = ?", (value, task_id))
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )

    with pytest.raises(OutcomeAcceptanceConflict):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("status", "failed"),
        ("exit_code", None),
        ("safety_failure", 1),
        ("recovery_reason", "uncertain_worker"),
        ("result_publication_status", "not_published"),
        ("result_publication_error", "publication_failed"),
    ],
)
def test_invalid_durable_run_publication_never_accepts(
    tmp_path: Path,
    column: str,
    value,
) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    with store.connect() as conn:
        conn.execute(f"UPDATE runs SET {column} = ? WHERE run_id = ?", (value, run_id))
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )

    with pytest.raises(OutcomeAcceptanceConflict):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("provider_binding_disposition", "uncertain"),
        ("provider_operation_ref", ""),
        ("provider_terminal_claim", "failure"),
        ("output_contract_disposition", "invalid"),
        ("output_contract_version", ""),
        ("error_code", "provider_error"),
        ("cancellation_disposition", "uncertain"),
        ("result_published_at", None),
    ],
)
def test_invalid_reasoning_publication_never_accepts(
    tmp_path: Path,
    column: str,
    value,
) -> None:
    config, store, scope, _fake, task_id, backend_ref, result_hash = (
        _reasoning_environment(tmp_path)
    )
    with store.connect() as conn:
        conn.execute(
            f"UPDATE reasoning_backend_runs SET {column} = ? WHERE backend_ref = ?",
            (value, backend_ref),
        )
    request = _request(
        task_id=task_id,
        backend_kind="soma_reasoning",
        backend_ref=backend_ref,
        result_hash=result_hash,
        source_hash=result_hash,
    )

    with pytest.raises(OutcomeAcceptanceConflict):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


def test_reasoning_missing_evidence_index_pair_never_accepts(tmp_path: Path) -> None:
    config, store, scope, _fake, task_id, backend_ref, result_hash = (
        _reasoning_environment(tmp_path)
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE reasoning_backend_runs SET evidence_index_ref = '', "
            "evidence_index_hash = '' WHERE backend_ref = ?",
            (backend_ref,),
        )
    request = _request(
        task_id=task_id,
        backend_kind="soma_reasoning",
        backend_ref=backend_ref,
        result_hash=result_hash,
        source_hash=result_hash,
    )

    with pytest.raises(OutcomeAcceptanceConflict, match="evidence_index_ref"):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


def test_reasoning_task_evidence_reference_mismatch_never_accepts(tmp_path: Path) -> None:
    config, store, scope, _fake, task_id, backend_ref, result_hash = (
        _reasoning_environment(tmp_path)
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE tasks SET evidence_ref = 'evidence-index:wrong' WHERE task_id = ?",
            (task_id,),
        )
    request = _request(
        task_id=task_id,
        backend_kind="soma_reasoning",
        backend_ref=backend_ref,
        result_hash=result_hash,
        source_hash=result_hash,
    )

    with pytest.raises(OutcomeAcceptanceConflict, match="evidence reference"):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


def test_durable_task_evidence_reference_mismatch_never_accepts(tmp_path: Path) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE tasks SET evidence_ref = 'run_terminal:wrong' WHERE task_id = ?",
            (task_id,),
        )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )

    with pytest.raises(OutcomeAcceptanceConflict, match="evidence reference"):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


def test_archived_scope_and_noncurrent_plan_block_new_acceptance_but_not_exact_replay(
    tmp_path: Path,
) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )
    accepted = accept_outcome(
        config, request, store=store, scope_store=scope, accepted_at=NOW
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE projects SET lifecycle_state = 'archived', scope_generation = 2 "
            "WHERE project_id = ?",
            (PROJECT_ID,),
        )
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = NULL WHERE mission_id = ?",
            (MISSION_ID,),
        )

    replay = accept_outcome(
        config,
        request,
        store=store,
        scope_store=scope,
        accepted_at="2026-08-14T12:00:00+00:00",
    )

    assert replay.created is False
    assert replay.acceptance == accepted.acceptance
    assert _acceptance_count(store) == 1
    assert _kernel_version(store) == 2


def test_archived_scope_blocks_new_acceptance(tmp_path: Path) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE projects SET lifecycle_state = 'archived', scope_generation = 2 "
            "WHERE project_id = ?",
            (PROJECT_ID,),
        )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )

    with pytest.raises(OutcomeAcceptanceConflict):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


def test_noncurrent_plan_blocks_new_acceptance(tmp_path: Path) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = NULL WHERE mission_id = ?",
            (MISSION_ID,),
        )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )

    with pytest.raises(OutcomeAcceptanceConflict, match="current PlanRevision"):
        accept_outcome(config, request, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


def test_same_controller_changed_basis_and_second_request_for_outcome_fail_closed(
    tmp_path: Path,
) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    first = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )
    accept_outcome(config, first, store=store, scope_store=scope, accepted_at=NOW)

    changed = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
        acceptance_basis_hash="f" * 64,
    )
    with pytest.raises(OutcomeAcceptanceConflict, match="controller request conflicts"):
        accept_outcome(config, changed, store=store, scope_store=scope, accepted_at=NOW)

    second = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
        controller_request_id="outcome-accept-request-2",
    )
    with pytest.raises(OutcomeAcceptanceConflict, match="already has"):
        accept_outcome(config, second, store=store, scope_store=scope, accepted_at=NOW)

    assert _acceptance_count(store) == 1
    assert _kernel_version(store) == 2


@pytest.mark.parametrize(
    "phase",
    ["before_acceptance_insert", "after_acceptance_insert", "after_mission_cas"],
)
def test_faults_leave_old_or_new_atomic_state_only(tmp_path: Path, phase: str) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )

    def inject(current: str, _conn: sqlite3.Connection) -> None:
        if current == phase:
            raise RuntimeError(f"fault:{phase}")

    with pytest.raises(RuntimeError, match=f"fault:{phase}"):
        accept_outcome(
            config,
            request,
            store=store,
            scope_store=scope,
            accepted_at=NOW,
            _fault_injector=inject,
        )

    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1


def test_concurrent_identical_acceptance_converges_to_one_commit(tmp_path: Path) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )

    def invoke():
        return accept_outcome(
            config,
            request,
            store=store,
            scope_store=scope,
            accepted_at=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: invoke(), range(2)))

    assert sorted(result.created for result in results) == [False, True]
    assert results[0].acceptance == results[1].acceptance
    assert _acceptance_count(store) == 1
    assert _kernel_version(store) == 2


def test_concurrent_conflicting_acceptance_has_one_winner(tmp_path: Path) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    requests = [
        _request(
            task_id=task_id,
            backend_kind="soma_durable_run",
            backend_ref=run_id,
            result_hash=result_hash,
            source_hash=source_hash,
            controller_request_id=f"outcome-race-{index}",
            acceptance_basis_hash=character * 64,
        )
        for index, character in enumerate(("c", "d"), start=1)
    ]

    def invoke(request: OutcomeAcceptanceRequestV1):
        try:
            return accept_outcome(
                config,
                request,
                store=store,
                scope_store=scope,
                accepted_at=NOW,
            )
        except OutcomeAcceptanceConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, requests))

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, OutcomeAcceptanceConflict) for result in results) == 1
    assert _acceptance_count(store) == 1
    assert _kernel_version(store) == 2


def test_resulting_acceptance_commit_satisfies_exact_accepted_outcome_dependency(
    tmp_path: Path,
) -> None:
    config, store, scope, task_id, run_id, result_hash, source_hash = (
        _durable_environment(tmp_path)
    )
    request = _request(
        task_id=task_id,
        backend_kind="soma_durable_run",
        backend_ref=run_id,
        result_hash=result_hash,
        source_hash=source_hash,
    )
    accepted = accept_outcome(
        config, request, store=store, scope_store=scope, accepted_at=NOW
    )
    context = DependencyEdgeContextV1(
        mission_id=MISSION_ID,
        plan_revision_id=PLAN_ID,
        edge_id="edge-accepted-outcome",
        edge_hash=_hash("f"),
        requirement="accepted_outcome",
        upstream_work_package_id=PACKAGE_ID,
        upstream_outcome_id=OUTCOME_ID,
        downstream_work_package_id="workpkg_" + "7" * 24,
        observed_kernel_state_version=2,
    )

    proof = evaluate_accepted_outcome(
        context,
        accepted.acceptance,
        observed_at=NOW,
    )

    assert proof.requirement == "accepted_outcome"
    assert proof.upstream_work_package_id == PACKAGE_ID
    assert proof.upstream_outcome_id == OUTCOME_ID
    assert proof.observed_kernel_state_version == 2
