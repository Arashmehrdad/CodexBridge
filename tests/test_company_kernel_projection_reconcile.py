"""V3-1B no-cache projections and receipt-only reconcile_one proofs."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from soma.company_kernel.acceptance import OutcomeAcceptanceRequestV1, accept_outcome
from soma.company_kernel.projections import CompanyKernelProjectionService
from soma.company_kernel.reconciliation import (
    ReconcileOneRequestV1,
    ReconciliationConflict,
    reconcile_one,
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


OWNER = "owner-controller:projection-reconcile"
COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
PLAN_ID = "planrev_" + "3" * 24
PACKAGE_ID = "workpkg_" + "4" * 24
OUTCOME_ID = "outcome_" + "5" * 24
ATTEMPT_ID = "wpattempt_" + "6" * 24
PROJECT_ID = "Project_Projection_Reconcile"
RESOURCE_ID = "Resource_Projection_Reconcile"
NOW = "2026-08-14T11:00:00+00:00"
RESULT_HASH = "a" * 64
SOURCE_HASH = "b" * 64
BASIS_HASH = "c" * 64


def _hash(character: str) -> str:
    return character * 64


def _config(tmp_path: Path) -> tuple[AppConfig, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return (
        AppConfig(
            repos={"sample": RepoConfig(path=str(repo))},
            company_kernel=CompanyKernelRuntimeConfig(
                enabled=True,
                executive_authority_ref=OWNER,
            ),
            config_dir=tmp_path,
        ),
        repo,
    )


def _insert_kernel_target(store: CompanyKernelStore) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO companies(company_id, company_key, display_name, "
            "executive_authority_ref, creation_request_id, creation_request_hash, created_at) "
            "VALUES (?, 'projection-company', 'Projection Company', ?, "
            "'projection-company-request', ?, ?)",
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
            ) VALUES (?, ?, 'projection-mission', ?, ?, 1, '{}', ?, ?, ?,
                      NULL, 0, 0, 'projection-mission-request', ?, ?, ?)
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
            ) VALUES (?, ?, 1, NULL, '{}', ?, '', '', ?, 'projection-plan',
                      'projection-plan-request', ?, ?)
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
            ) VALUES (?, ?, ?, 'projection', ?, ?, ?, 1, 'v1', '{}', ?,
                      'single_active', ?, ?, '', '', '', 'projection-package-request', ?, ?)
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


def _base_environment(tmp_path: Path):
    config, repo = _config(tmp_path)
    store = CompanyKernelStore(config.resolve_runs_dir())
    assert store.init_db() == [1, 2, 3, 4]
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="projection-reconcile",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    _insert_kernel_target(store)
    return config, repo, store, scope


def _reserve_scope_and_task(
    *,
    config: AppConfig,
    repo: Path,
    scope: ProjectScopeStore,
    task_store: TaskStore,
    task_id: str,
    backend_ref: str,
    backend_kind: str,
    task_kind: str,
    executor: str,
    request_id: str,
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
    task_store.reserve_task(
        task_id=task_id,
        task_kind=task_kind,
        controller_request_id=request_id,
        request_hash=_hash("d"),
        backend_kind=backend_kind,
        backend_executor=executor,
        backend_ref=backend_ref,
        backend_identity={"repo_name": "sample"},
    )
    with scope.transaction() as conn:
        scope.attach_task(conn, task_id)
    assert scope.attach_attempt(backend_ref, backend_kind=backend_kind) is True


def _insert_attempt(
    store: CompanyKernelStore,
    *,
    task_id: str,
    attempt_id: str = ATTEMPT_ID,
    supersedes_attempt_id: str | None = None,
    request_suffix: str = "1",
) -> None:
    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO work_package_attempts(
                attempt_id, work_package_id, outcome_id, task_id,
                route_request_hash, route_descriptor_json, supersedes_attempt_id,
                containment_evidence_ref, containment_evidence_hash,
                controller_request_id, request_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, '{}', ?, '', '', ?, ?, ?)
            """,
            (
                attempt_id,
                PACKAGE_ID,
                OUTCOME_ID,
                task_id,
                _hash("8"),
                supersedes_attempt_id,
                f"projection-attempt-{request_suffix}",
                _hash("9"),
                NOW,
            ),
        )


def _add_durable_attempt(
    config: AppConfig,
    repo: Path,
    store: CompanyKernelStore,
    scope: ProjectScopeStore,
    *,
    task_state: str = "accepted",
    task_phase: str = "accepted",
    recovery_state: str = "none",
    run_status: str = "pending",
    published: bool = False,
    terminal_unpublished: bool = False,
    attempt_id: str = ATTEMPT_ID,
    supersedes_attempt_id: str | None = None,
    request_suffix: str = "1",
):
    run_store = RunStore(config.resolve_runs_dir())
    task_store = TaskStore(config.resolve_runs_dir())
    run_id = f"20260814T11{int(request_suffix):02d}00Z_fixture_{int(request_suffix):08x}"
    run_dir = config.resolve_runs_dir() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="executable_profile",
        run_dir=run_dir,
        input_data={"fixture": request_suffix},
        status=run_status,
    )
    task_id = make_task_id()
    _reserve_scope_and_task(
        config=config,
        repo=repo,
        scope=scope,
        task_store=task_store,
        task_id=task_id,
        backend_ref=run_id,
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        executor="executable_profile",
        request_id=f"projection-task-{request_suffix}",
    )
    _insert_attempt(
        store,
        task_id=task_id,
        attempt_id=attempt_id,
        supersedes_attempt_id=supersedes_attempt_id,
        request_suffix=request_suffix,
    )
    with store.connect() as conn:
        if published:
            conn.execute(
                "UPDATE runs SET status = 'completed', exit_code = 0, "
                "safety_failure = 0, recovery_reason = '', "
                "result_publication_status = 'published', result_published_hash = ?, "
                "result_published_at = ?, result_publication_error = '', "
                "public_result_source_sha256 = ?, public_result_status = 'ready', "
                "public_result_error = '' WHERE run_id = ?",
                (RESULT_HASH, NOW, SOURCE_HASH, run_id),
            )
            task_state = "completed"
            task_phase = "result_published"
            conn.execute(
                "UPDATE tasks SET state = ?, phase = ?, recovery_state = 'none', "
                "recovery_reason = '', result_ref = ?, result_hash = ?, evidence_ref = ?, "
                "ended_at = ?, updated_at = ? WHERE task_id = ?",
                (
                    task_state,
                    task_phase,
                    run_id,
                    RESULT_HASH,
                    f"run_terminal:{run_id}",
                    NOW,
                    NOW,
                    task_id,
                ),
            )
        elif terminal_unpublished:
            conn.execute(
                "UPDATE runs SET status = 'completed', exit_code = 0, "
                "safety_failure = 0, recovery_reason = '', "
                "result_publication_status = 'not_published' WHERE run_id = ?",
                (run_id,),
            )
            conn.execute(
                "UPDATE tasks SET state = 'completed', phase = 'backend_terminal', "
                "recovery_state = 'none', recovery_reason = '', ended_at = ?, "
                "updated_at = ? WHERE task_id = ?",
                (NOW, NOW, task_id),
            )
        else:
            checkpoint = "checkpoint:owner" if task_state == "awaiting_controller" else ""
            conn.execute(
                "UPDATE tasks SET state = ?, phase = ?, recovery_state = ?, "
                "recovery_reason = ?, checkpoint_ref = ?, updated_at = ? WHERE task_id = ?",
                (
                    task_state,
                    task_phase,
                    recovery_state,
                    "projection-fixture" if recovery_state != "none" else "",
                    checkpoint,
                    NOW,
                    task_id,
                ),
            )
    return task_id, run_id


def _reasoning_spec() -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref="assignment:projection-reconcile",
        assignment_hash=_hash("1"),
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash=_hash("2"),
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash=_hash("3"),
        authority_ref="authority:projection-reconcile",
        authority_hash=_hash("4"),
        provider_route_ref="route:fake-projection-reconcile",
        provider_route_hash=_hash("5"),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _add_reasoning_published_attempt(
    config: AppConfig,
    repo: Path,
    store: CompanyKernelStore,
    scope: ProjectScopeStore,
):
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    fake = FakeReasoningBackend(reasoning_store, case="success")
    backend_ref = fake.reserve()
    observation = fake.start(_reasoning_spec(), backend_ref)
    assert observation.result_ref is not None
    assert observation.result_hash is not None
    assert observation.evidence_index_ref is not None
    task_store = TaskStore(config.resolve_runs_dir())
    task_id = make_task_id()
    _reserve_scope_and_task(
        config=config,
        repo=repo,
        scope=scope,
        task_store=task_store,
        task_id=task_id,
        backend_ref=backend_ref,
        backend_kind=BackendKind.SOMA_REASONING.value,
        task_kind=TaskKind.REASONING.value,
        executor="reasoning_backend",
        request_id="projection-task-reasoning",
    )
    _insert_attempt(store, task_id=task_id)
    with store.connect() as conn:
        conn.execute(
            "UPDATE tasks SET state = 'completed', phase = 'result_published', "
            "recovery_state = 'none', recovery_reason = '', result_ref = ?, "
            "result_hash = ?, evidence_ref = ?, ended_at = ?, updated_at = ? "
            "WHERE task_id = ?",
            (
                observation.result_ref,
                observation.result_hash,
                observation.evidence_index_ref,
                NOW,
                NOW,
                task_id,
            ),
        )
    return fake, task_id, backend_ref, observation.result_hash


def _accept_durable(
    config: AppConfig,
    store: CompanyKernelStore,
    scope: ProjectScopeStore,
    *,
    task_id: str,
    run_id: str,
):
    return accept_outcome(
        config,
        OutcomeAcceptanceRequestV1(
            controller_request_id="projection-acceptance-1",
            company_id=COMPANY_ID,
            mission_id=MISSION_ID,
            plan_revision_id=PLAN_ID,
            work_package_id=PACKAGE_ID,
            outcome_id=OUTCOME_ID,
            attempt_id=ATTEMPT_ID,
            task_id=task_id,
            backend_kind="soma_durable_run",
            backend_ref=run_id,
            project_id=PROJECT_ID,
            resource_id=RESOURCE_ID,
            scope_generation=1,
            expected_kernel_state_version=1,
            result_published_hash=RESULT_HASH,
            public_result_source_sha256=SOURCE_HASH,
            acceptance_authority_ref=OWNER,
            acceptance_basis_ref="owner-review:projection",
            acceptance_basis_hash=BASIS_HASH,
        ),
        store=store,
        scope_store=scope,
        accepted_at=NOW,
    )


def _table_fingerprint(store: CompanyKernelStore) -> dict[str, tuple[int, str]]:
    import hashlib

    with store.connect() as conn:
        names = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        result: dict[str, tuple[int, str]] = {}
        for name in names:
            rows = conn.execute(f'SELECT * FROM "{name}"').fetchall()
            material = sorted(repr(tuple(row)) for row in rows)
            digest = hashlib.sha256("\0".join(material).encode("utf-8")).hexdigest()
            result[name] = (len(rows), digest)
        return result


def _receipt_count(store: CompanyKernelStore) -> int:
    with store.connect() as conn:
        return int(
            conn.execute("SELECT COUNT(*) FROM kernel_reconciliation_receipts").fetchone()[0]
        )


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


def test_company_mission_plan_and_not_started_package_projection_are_exact_and_read_only(
    tmp_path: Path,
) -> None:
    _config_obj, _repo, store, _scope = _base_environment(tmp_path)
    before = _table_fingerprint(store)
    service = CompanyKernelProjectionService(store)

    company = service.company(COMPANY_ID)
    mission = service.mission(MISSION_ID)
    plan = service.plan_revision(PLAN_ID)
    package = service.work_package(PACKAGE_ID)
    after = _table_fingerprint(store)

    assert company.mission_ids == (MISSION_ID,)
    assert company.mission_count == 1
    assert company.executive_authority_ref == OWNER
    assert mission.current_plan_revision_id == PLAN_ID
    assert mission.scope.valid is True
    assert mission.current_package_count == 1
    assert mission.accepted_outcome_count == 0
    assert mission.open_outcome_count == 1
    assert plan.current is True
    assert plan.package_count == 1
    assert plan.edge_count == 0
    assert package.state == "not_started"
    assert package.attempt_count == 0
    assert before == after


def test_projection_payloads_bound_mission_and_attempt_identity_lists(
    tmp_path: Path,
) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    with store.connect() as conn:
        for index in range(70):
            mission_id = f"mission_{index + 100:024x}"
            conn.execute(
                """
                INSERT INTO missions(
                    mission_id, company_id, mission_key, project_id, resource_id,
                    scope_generation, mission_contract_json, mission_contract_hash,
                    accountable_owner_ref, acceptance_authority_ref,
                    current_plan_revision_id, plan_state_version, kernel_state_version,
                    creation_request_id, creation_request_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, '{}', ?, ?, ?, NULL, 0, 0, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    COMPANY_ID,
                    f"bounded-mission-{index}",
                    PROJECT_ID,
                    RESOURCE_ID,
                    _hash("2"),
                    OWNER,
                    OWNER,
                    f"bounded-mission-request-{index}",
                    _hash("3"),
                    NOW,
                    NOW,
                ),
            )
    task_store = TaskStore(config.resolve_runs_dir())
    for index in range(70):
        task_id = make_task_id()
        task_store.reserve_task(
            task_id=task_id,
            task_kind=TaskKind.DURABLE_COMMAND.value,
            controller_request_id=f"bounded-task-{index}",
            request_hash=_hash("d"),
            backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
            backend_executor="executable_profile",
            backend_ref="",
            backend_identity={},
        )
        _insert_attempt(
            store,
            task_id=task_id,
            attempt_id=f"wpattempt_{index + 100:024x}",
            request_suffix=f"bounded-{index}",
        )

    service = CompanyKernelProjectionService(store)
    company = service.company(COMPANY_ID)
    package = service.work_package(PACKAGE_ID)

    assert company.mission_count == 71
    assert len(company.mission_ids) == 64
    assert company.mission_ids_truncated is True
    assert package.attempt_count == 70
    assert len(package.attempts) == 64
    assert package.attempts_truncated is True
    assert package.state == "uncertain"


def test_projection_rebuild_from_fresh_service_is_identical(tmp_path: Path) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _add_durable_attempt(config, repo, store, scope, task_state="running", task_phase="backend_running")

    first = CompanyKernelProjectionService(store).work_package(PACKAGE_ID)
    rebuilt = CompanyKernelProjectionService.from_runs_dir(
        config.resolve_runs_dir()
    ).work_package(PACKAGE_ID)

    assert first == rebuilt
    assert first.model_dump(mode="json") == rebuilt.model_dump(mode="json")


@pytest.mark.parametrize(
    ("task_state", "phase", "recovery", "expected"),
    [
        ("accepted", "accepted", "none", "attempt_admitted"),
        ("queued", "backend_reserved", "none", "queued"),
        ("running", "backend_running", "none", "running"),
        ("awaiting_controller", "awaiting_controller", "none", "awaiting_controller"),
        ("cancellation_pending", "cancellation_requested", "none", "cancellation_pending"),
        ("recovery_pending", "recovery", "pending", "recovery_pending"),
        ("uncertain", "recovery", "unresolved", "uncertain"),
        ("failed", "backend_terminal", "none", "failed_without_acceptance"),
        ("cancelled", "backend_terminal", "none", "failed_without_acceptance"),
    ],
)
def test_task_lifecycle_projects_without_copying_execution_state(
    tmp_path: Path,
    task_state: str,
    phase: str,
    recovery: str,
    expected: str,
) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _add_durable_attempt(
        config,
        repo,
        store,
        scope,
        task_state=task_state,
        task_phase=phase,
        recovery_state=recovery,
    )

    projection = CompanyKernelProjectionService(store).work_package(PACKAGE_ID)

    assert projection.state == expected
    assert projection.attempts[0].state == expected
    assert projection.attempts[0].task_state == task_state


def test_reserved_scoped_backend_attempt_is_admitted_not_scope_invalid(
    tmp_path: Path,
) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _task_id, run_id = _add_durable_attempt(config, repo, store, scope)
    with store.connect() as conn:
        conn.execute(
            "UPDATE project_run_attempts SET status = 'reserved' WHERE run_id = ?",
            (run_id,),
        )

    projection = CompanyKernelProjectionService(store).work_package(PACKAGE_ID)

    assert projection.scope.valid is True
    assert projection.state == "attempt_admitted"
    assert projection.attempts[0].project_attempt_status == "reserved"


def test_completed_unpublished_and_published_candidate_are_distinct(tmp_path: Path) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _add_durable_attempt(
        config,
        repo,
        store,
        scope,
        terminal_unpublished=True,
    )
    service = CompanyKernelProjectionService(store)
    assert service.work_package(PACKAGE_ID).state == "terminal_unpublished"

    with store.connect() as conn:
        run_id = str(conn.execute("SELECT backend_ref FROM tasks").fetchone()[0])
        task_id = str(conn.execute("SELECT task_id FROM tasks").fetchone()[0])
        conn.execute(
            "UPDATE runs SET result_publication_status = 'published', "
            "result_published_hash = ?, result_published_at = ?, "
            "result_publication_error = '', public_result_source_sha256 = ? "
            "WHERE run_id = ?",
            (RESULT_HASH, NOW, SOURCE_HASH, run_id),
        )
        conn.execute(
            "UPDATE tasks SET phase = 'result_published', result_ref = ?, "
            "result_hash = ?, evidence_ref = ? WHERE task_id = ?",
            (run_id, RESULT_HASH, f"run_terminal:{run_id}", task_id),
        )

    published = service.work_package(PACKAGE_ID)
    assert published.state == "published_awaiting_acceptance"
    assert published.published_result_hash == RESULT_HASH


def test_durable_published_candidate_requires_exact_source_and_task_evidence(
    tmp_path: Path,
) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    task_id, run_id = _add_durable_attempt(
        config, repo, store, scope, published=True
    )
    service = CompanyKernelProjectionService(store)
    assert service.work_package(PACKAGE_ID).state == "published_awaiting_acceptance"

    with store.connect() as conn:
        conn.execute(
            "UPDATE runs SET public_result_source_sha256 = '' WHERE run_id = ?",
            (run_id,),
        )
    assert service.work_package(PACKAGE_ID).state == "uncertain"

    with store.connect() as conn:
        conn.execute(
            "UPDATE runs SET public_result_source_sha256 = ? WHERE run_id = ?",
            (SOURCE_HASH, run_id),
        )
        conn.execute(
            "UPDATE tasks SET evidence_ref = 'run_terminal:wrong' WHERE task_id = ?",
            (task_id,),
        )
    assert service.work_package(PACKAGE_ID).state == "uncertain"


def test_noncurrent_historical_package_keeps_lifecycle_with_currency_flag(
    tmp_path: Path,
) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _add_durable_attempt(config, repo, store, scope, published=True)
    with store.connect() as conn:
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = NULL WHERE mission_id = ?",
            (MISSION_ID,),
        )

    projection = CompanyKernelProjectionService(store).work_package(PACKAGE_ID)

    assert projection.current_plan is False
    assert projection.scope.valid is True
    assert projection.state == "published_awaiting_acceptance"


def test_reasoning_published_candidate_requires_no_synthetic_run(tmp_path: Path) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    fake, _task_id, _backend_ref, result_hash = _add_reasoning_published_attempt(
        config, repo, store, scope
    )
    with store.connect() as conn:
        runs_before = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    projection = CompanyKernelProjectionService(store).work_package(PACKAGE_ID)

    with store.connect() as conn:
        runs_after = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    assert projection.state == "published_awaiting_acceptance"
    assert projection.published_result_hash == result_hash
    assert projection.attempts[0].backend_kind == "soma_reasoning"
    assert fake.provider_create_calls == 1
    assert runs_before == runs_after == 0


def test_reasoning_candidate_requires_full_evidence_and_exact_task_linkage(
    tmp_path: Path,
) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _fake, task_id, backend_ref, _result_hash = _add_reasoning_published_attempt(
        config, repo, store, scope
    )
    service = CompanyKernelProjectionService(store)
    assert service.work_package(PACKAGE_ID).state == "published_awaiting_acceptance"

    with store.connect() as conn:
        original = conn.execute(
            "SELECT provider_provenance_index_ref, provider_provenance_index_hash "
            "FROM reasoning_backend_runs WHERE backend_ref = ?",
            (backend_ref,),
        ).fetchone()
        assert original is not None
        conn.execute(
            "UPDATE reasoning_backend_runs SET provider_provenance_index_ref = '', "
            "provider_provenance_index_hash = '' WHERE backend_ref = ?",
            (backend_ref,),
        )
    assert service.work_package(PACKAGE_ID).state == "terminal_unpublished"

    with store.connect() as conn:
        conn.execute(
            "UPDATE reasoning_backend_runs SET provider_provenance_index_ref = ?, "
            "provider_provenance_index_hash = ? WHERE backend_ref = ?",
            (str(original[0]), str(original[1]), backend_ref),
        )
        conn.execute(
            "UPDATE tasks SET evidence_ref = 'evidence-index:wrong' WHERE task_id = ?",
            (task_id,),
        )
    assert service.work_package(PACKAGE_ID).state == "uncertain"


def test_acceptance_overrides_later_scope_invalidity_for_historical_outcome(tmp_path: Path) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    task_id, run_id = _add_durable_attempt(
        config, repo, store, scope, published=True
    )
    accepted = _accept_durable(config, store, scope, task_id=task_id, run_id=run_id)
    with store.connect() as conn:
        conn.execute(
            "UPDATE projects SET lifecycle_state = 'archived', scope_generation = 2 "
            "WHERE project_id = ?",
            (PROJECT_ID,),
        )

    projection = CompanyKernelProjectionService(store).work_package(PACKAGE_ID)

    assert projection.state == "accepted"
    assert projection.scope.valid is False
    assert projection.acceptance_commit_id == accepted.acceptance.acceptance_commit_id
    assert projection.published_result_hash == RESULT_HASH


def test_scope_invalid_outweighs_active_unaccepted_execution(tmp_path: Path) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _add_durable_attempt(config, repo, store, scope, task_state="running", task_phase="backend_running")
    with store.connect() as conn:
        conn.execute(
            "UPDATE projects SET lifecycle_state = 'suspended' WHERE project_id = ?",
            (PROJECT_ID,),
        )

    projection = CompanyKernelProjectionService(store).work_package(PACKAGE_ID)

    assert projection.state == "scope_invalid"
    assert projection.scope.reason == "project_suspended"


def test_superseded_route_is_attempt_only_and_head_drives_package(tmp_path: Path) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    first_task, _first_run = _add_durable_attempt(
        config,
        repo,
        store,
        scope,
        task_state="failed",
        task_phase="backend_terminal",
        request_suffix="1",
    )
    second_attempt_id = "wpattempt_" + "7" * 24
    second_task, _second_run = _add_durable_attempt(
        config,
        repo,
        store,
        scope,
        task_state="queued",
        task_phase="backend_reserved",
        attempt_id=second_attempt_id,
        supersedes_attempt_id=ATTEMPT_ID,
        request_suffix="2",
    )

    projection = CompanyKernelProjectionService(store).work_package(PACKAGE_ID)

    by_task = {attempt.task_id: attempt for attempt in projection.attempts}
    assert by_task[first_task].state == "superseded_route"
    assert by_task[second_task].state == "queued"
    assert projection.current_attempt_id == second_attempt_id
    assert projection.state == "queued"


def _no_op_request(**changes) -> ReconcileOneRequestV1:
    payload = {
        "company_id": COMPANY_ID,
        "mission_id": MISSION_ID,
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "scope_generation": 1,
        "executive_authority_ref": OWNER,
        "trigger_kind": "owner_turn",
        "trigger_ref": "owner-turn:projection-1",
        "expected_kernel_state_version": 1,
        "selected_transition": "no_op",
        "target_ref": "",
        "target_hash": "",
    }
    payload.update(changes)
    return ReconcileOneRequestV1.model_validate(payload)


def _candidate_request(**changes) -> ReconcileOneRequestV1:
    payload = {
        "company_id": COMPANY_ID,
        "mission_id": MISSION_ID,
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "scope_generation": 1,
        "executive_authority_ref": OWNER,
        "trigger_kind": "package_completion",
        "trigger_ref": "package-completion:projection-1",
        "expected_kernel_state_version": 1,
        "selected_transition": "acceptance_candidate_ready",
        "target_ref": PACKAGE_ID,
        "target_hash": RESULT_HASH,
    }
    payload.update(changes)
    return ReconcileOneRequestV1.model_validate(payload)


def test_owner_turn_no_op_receipt_is_single_replayable_and_kernel_neutral(
    tmp_path: Path,
) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    request = _no_op_request()

    first = reconcile_one(config, request, store=store, created_at=NOW)
    replay = reconcile_one(
        config,
        request,
        store=store,
        created_at="2026-08-14T12:00:00+00:00",
    )

    assert first.created is True
    assert first.receipt.selected_transition == "no_op"
    assert replay.created is False
    assert replay.replay_kind == "trigger"
    assert replay.receipt == first.receipt
    assert _receipt_count(store) == 1
    assert _kernel_version(store) == 1


def test_exact_reconciliation_replay_survives_later_scope_and_kernel_changes(
    tmp_path: Path,
) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    request = _no_op_request()
    first = reconcile_one(config, request, store=store, created_at=NOW)
    with store.connect() as conn:
        conn.execute(
            "UPDATE projects SET lifecycle_state = 'archived', scope_generation = 2 "
            "WHERE project_id = ?",
            (PROJECT_ID,),
        )
        conn.execute(
            "UPDATE missions SET kernel_state_version = 2 WHERE mission_id = ?",
            (MISSION_ID,),
        )

    replay = reconcile_one(config, request, store=store, created_at=NOW)

    assert replay.created is False
    assert replay.receipt == first.receipt
    assert _receipt_count(store) == 1


def test_package_completion_records_candidate_without_acceptance_or_kernel_mutation(
    tmp_path: Path,
) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _add_durable_attempt(config, repo, store, scope, published=True)
    before = _table_fingerprint(store)

    result = reconcile_one(config, _candidate_request(), store=store, created_at=NOW)

    assert result.created is True
    assert result.receipt.selected_transition == "acceptance_candidate_ready"
    assert result.receipt.target_ref == PACKAGE_ID
    assert _receipt_count(store) == 1
    assert _acceptance_count(store) == 0
    assert _kernel_version(store) == 1
    after = _table_fingerprint(store)
    changed = {name for name in before if before[name] != after[name]}
    assert changed == {"kernel_reconciliation_receipts"}


@pytest.mark.parametrize(
    "setup",
    ["not_started", "terminal_unpublished", "accepted", "archived", "non_current"],
)
def test_candidate_reconciliation_requires_exact_current_published_unaccepted_package(
    tmp_path: Path,
    setup: str,
) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    if setup == "terminal_unpublished":
        _add_durable_attempt(config, repo, store, scope, terminal_unpublished=True)
    elif setup in {"accepted", "archived", "non_current"}:
        task_id, run_id = _add_durable_attempt(
            config, repo, store, scope, published=True
        )
        if setup == "accepted":
            _accept_durable(config, store, scope, task_id=task_id, run_id=run_id)
        elif setup == "archived":
            with store.connect() as conn:
                conn.execute(
                    "UPDATE projects SET lifecycle_state = 'archived' WHERE project_id = ?",
                    (PROJECT_ID,),
                )
        else:
            with store.connect() as conn:
                conn.execute(
                    "UPDATE missions SET current_plan_revision_id = NULL WHERE mission_id = ?",
                    (MISSION_ID,),
                )

    request = _candidate_request(
        expected_kernel_state_version=2 if setup == "accepted" else 1
    )
    with pytest.raises(ReconciliationConflict):
        reconcile_one(config, request, store=store, created_at=NOW)

    assert _receipt_count(store) == 0


def test_candidate_wrong_publication_hash_fails_closed(tmp_path: Path) -> None:
    config, repo, store, scope = _base_environment(tmp_path)
    _add_durable_attempt(config, repo, store, scope, published=True)

    with pytest.raises(ReconciliationConflict, match="publication hash"):
        reconcile_one(
            config,
            _candidate_request(target_hash="f" * 64),
            store=store,
            created_at=NOW,
        )

    assert _receipt_count(store) == 0


def test_unsupported_reconcile_transition_is_rejected_before_mutation(tmp_path: Path) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    payload = _no_op_request().model_dump(mode="json")
    payload["selected_transition"] = "plan_selected"

    with pytest.raises(ValidationError):
        ReconcileOneRequestV1.model_validate(payload)

    assert _receipt_count(store) == 0
    assert _kernel_version(store) == 1


def test_same_trigger_changed_effect_material_fails_closed(tmp_path: Path) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    request = _no_op_request()
    reconcile_one(config, request, store=store, created_at=NOW)
    changed = _no_op_request(expected_kernel_state_version=2)

    with pytest.raises(ReconciliationConflict, match="different transition/effect"):
        reconcile_one(config, changed, store=store, created_at=NOW)

    assert _receipt_count(store) == 1
    assert _kernel_version(store) == 1


def test_wrong_executive_or_scope_fails_before_receipt(tmp_path: Path) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    wrong_authority = _no_op_request(
        executive_authority_ref="owner-controller:someone-else"
    )
    with pytest.raises(ReconciliationConflict, match="trusted configuration"):
        reconcile_one(config, wrong_authority, store=store, created_at=NOW)

    wrong_scope = _no_op_request(project_id="Other_Project")
    with pytest.raises(ReconciliationConflict, match="ProjectScope"):
        reconcile_one(config, wrong_scope, store=store, created_at=NOW)

    assert _receipt_count(store) == 0


@pytest.mark.parametrize("phase", ["before_receipt_insert", "after_receipt_insert"])
def test_reconcile_faults_leave_zero_receipt_and_no_other_mutation(
    tmp_path: Path,
    phase: str,
) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    before = _table_fingerprint(store)

    def inject(current: str, _conn: sqlite3.Connection) -> None:
        if current == phase:
            raise RuntimeError(f"fault:{phase}")

    with pytest.raises(RuntimeError, match=f"fault:{phase}"):
        reconcile_one(
            config,
            _no_op_request(),
            store=store,
            created_at=NOW,
            _fault_injector=inject,
        )

    assert _receipt_count(store) == 0
    assert _table_fingerprint(store) == before


def test_concurrent_identical_reconcile_converges_to_one_receipt(tmp_path: Path) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    request = _no_op_request()

    def invoke():
        return reconcile_one(config, request, store=store, created_at=NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: invoke(), range(2)))

    assert sorted(result.created for result in results) == [False, True]
    assert results[0].receipt == results[1].receipt
    assert _receipt_count(store) == 1
    assert _kernel_version(store) == 1


def test_concurrent_conflicting_reconcile_has_one_winner(tmp_path: Path) -> None:
    config, _repo, store, _scope = _base_environment(tmp_path)
    requests = [
        _no_op_request(expected_kernel_state_version=version)
        for version in (1, 2)
    ]

    def invoke(request: ReconcileOneRequestV1):
        try:
            return reconcile_one(config, request, store=store, created_at=NOW)
        except ReconciliationConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, requests))

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ReconciliationConflict) for result in results) == 1
    assert _receipt_count(store) == 1
    assert _kernel_version(store) == 1
