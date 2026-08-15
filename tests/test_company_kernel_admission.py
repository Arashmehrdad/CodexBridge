"""G3.4 bounded Company Kernel admission and proof-freezing tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from soma.company_kernel.admission import (
    MAX_ADMISSION_BATCH,
    AdmissionError,
    AdmissionRequestV1,
    _replay_existing_attempt,
    admit_work_package,
    admit_work_package_batch,
)
from soma.company_kernel.coordinator import (
    AdmitReadyWorkRequestV1,
    PreparedTaskAdmissionV1,
    admit_ready_work,
)
from soma.company_kernel.store import CompanyKernelStore
from soma.company_kernel.task_routes import (
    DurableCommandTaskRequestV1,
    ReasoningTaskRequestV1,
)
from soma.config import AppConfig, load_config
from soma.company_kernel.dependencies import EvidenceAvailableCandidateV1
from soma.project_scope import ProjectScopeStore
from soma.reasoning.backends import reasoning_spec_hash, reasoning_spec_ref
from soma.reasoning.fake import FakeReasoningBackend
from soma.reasoning.models import ReasoningBudgetsV1, ReasoningSpecV1
from soma.reasoning.store import ReasoningBackendStore
from soma.tasks.manager import TaskManager
from soma.tasks.store import TaskStore

COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
PLAN_ID = "planrev_" + "3" * 24
ROOT_PACKAGE_ID = "workpkg_" + "4" * 24
DOWNSTREAM_PACKAGE_ID = "workpkg_" + "5" * 24
ROOT_OUTCOME_ID = "outcome_" + "6" * 24
DOWNSTREAM_OUTCOME_ID = "outcome_" + "7" * 24
PROJECT_ID = "Project_Admission"
RESOURCE_ID = "Resource_Admission"
OWNER = "owner-controller:admission"
NOW = "2026-08-12T05:30:00+00:00"
EDGE_ID = "edge-evidence-admission"
SELECTOR_REF = "selector:upstream-evidence"


def _hash(character: str) -> str:
    return character * 64


def _config(tmp_path: Path) -> tuple[AppConfig, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    executable = Path(sys.executable)
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "executable_profiles:",
                "  powershell:",
                '    profile_id: "powershell"',
                "    enabled: true",
                f'    executable_path: "{executable.as_posix()}"',
                '    target: "local"',
                '    autonomy_profile: "permissive"',
                '    working_directory_policy: "arbitrary"',
                '    environment_policy: "arbitrary"',
                '    stdin_mode: "bytes"',
                '    stdout_mode: "protected_artifact"',
                '    stderr_mode: "protected_artifact"',
                "    allow_no_timeout: true",
                "    unrestricted_argv: true",
                "    unrestricted_paths: true",
                "    unrestricted_environment: true",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return load_config(config_path), config_path, repo


def _spec() -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref="assignment:template",
        assignment_hash=_hash("1"),
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash=_hash("2"),
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash=_hash("3"),
        authority_ref="authority:admission",
        authority_hash=_hash("4"),
        provider_route_ref="route:fake-admission",
        provider_route_hash=_hash("5"),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _insert_kernel_graph(store: CompanyKernelStore) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO companies(company_id, company_key, display_name, executive_authority_ref, creation_request_id, creation_request_hash, created_at) VALUES (?, 'admission-company', 'Admission Company', ?, 'company-request', ?, ?)",
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
            ) VALUES (?, ?, 'admission-mission', ?, ?, 1, '{}', ?, ?, ?, NULL, 0, 0, 'mission-request', ?, ?, ?)
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
            ) VALUES (?, ?, 1, NULL, '{}', ?, '', '', ?, 'admission-plan', 'plan-request', ?, ?)
            """,
            (PLAN_ID, MISSION_ID, _hash("4"), OWNER, _hash("5"), NOW),
        )
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = ?, plan_state_version = 1, kernel_state_version = 1 WHERE mission_id = ?",
            (PLAN_ID, MISSION_ID),
        )
        for package_id, package_key, outcome_id, contract_hash in (
            (ROOT_PACKAGE_ID, "root", ROOT_OUTCOME_ID, _hash("6")),
            (DOWNSTREAM_PACKAGE_ID, "downstream", DOWNSTREAM_OUTCOME_ID, _hash("7")),
        ):
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'v1', '{}', ?, 'single_active', ?, ?, '', '', '', ?, ?, ?)
                """,
                (
                    package_id,
                    MISSION_ID,
                    PLAN_ID,
                    package_key,
                    outcome_id,
                    PROJECT_ID,
                    RESOURCE_ID,
                    contract_hash,
                    OWNER,
                    OWNER,
                    f"package:{package_key}",
                    _hash("8"),
                    NOW,
                ),
            )
        conn.execute(
            "INSERT INTO plan_graph_manifests(plan_revision_id, mission_id, schema_version, manifest_json, manifest_hash, package_count, edge_count, created_at) VALUES (?, ?, 'plan_graph_manifest.v1', '{}', ?, 2, 1, ?)",
            (PLAN_ID, MISSION_ID, _hash("9"), NOW),
        )
        conn.execute(
            """
            INSERT INTO work_package_dependencies(
                edge_id, mission_id, plan_revision_id, upstream_work_package_id,
                downstream_work_package_id, requirement, evidence_selector_ref,
                evidence_selector_hash, edge_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, 'evidence_available', ?, ?, ?, ?)
            """,
            (
                EDGE_ID,
                MISSION_ID,
                PLAN_ID,
                ROOT_PACKAGE_ID,
                DOWNSTREAM_PACKAGE_ID,
                SELECTOR_REF,
                _hash("a"),
                _hash("b"),
                NOW,
            ),
        )


def _environment(tmp_path: Path, *, fake_case: str = "success"):
    config, config_path, repo = _config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="admission",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)
    kernel = CompanyKernelStore(config.resolve_runs_dir())
    assert kernel.init_db() == [1, 2, 3, 4]
    _insert_kernel_graph(kernel)
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    fake = FakeReasoningBackend(reasoning_store, case=fake_case)
    manager = TaskManager(
        config, config_path, reasoning_backend=fake, scope_store=scope
    )
    return manager, fake, kernel, scope


def _request(
    package_id: str, controller_request_id: str, *, with_evidence: bool = False
):
    evidence = {}
    if with_evidence:
        evidence = {
            EDGE_ID: EvidenceAvailableCandidateV1(
                selector_ref=SELECTOR_REF,
                selector_hash=_hash("a"),
                evidence_ref="artifact:upstream-evidence",
                evidence_hash=_hash("c"),
            )
        }
    return AdmissionRequestV1(
        mission_id=MISSION_ID,
        work_package_id=package_id,
        controller_request_id=controller_request_id,
        repo_name="sample",
        task_request=ReasoningTaskRequestV1(reasoning_spec=_spec()),
        evidence_candidates=evidence,
    )


def test_company_durable_route_does_not_require_reasoning_backend(tmp_path: Path) -> None:
    config, config_path, repo = _config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="admission",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)
    kernel = CompanyKernelStore(config.resolve_runs_dir())
    assert kernel.init_db() == [1, 2, 3, 4]
    _insert_kernel_graph(kernel)
    manager = TaskManager(config, config_path, scope_store=scope)
    assert manager._reasoning_backend is None

    request = AdmissionRequestV1(
        mission_id=MISSION_ID,
        work_package_id=ROOT_PACKAGE_ID,
        controller_request_id="admit-durable-without-reasoning",
        repo_name="sample",
        task_request=DurableCommandTaskRequestV1(
            profile_id="powershell",
            argv=("-c", "print('company-route-neutral')"),
            working_directory=str(repo),
        ),
    )
    result = admit_work_package(manager, request)
    task = manager.store.get_task(result.task_id)

    assert result.created is True
    assert result.task_start["ok"] is True
    assert task.task_kind.value == "durable_command"
    assert task.backend_kind.value == "soma_durable_run"
    assert task.backend_identity["work_package_attempt_ref"] == result.attempt_id
    with kernel.connect() as conn:
        attempt = conn.execute(
            "SELECT route_descriptor_json FROM work_package_attempts WHERE attempt_id = ?",
            (result.attempt_id,),
        ).fetchone()
    route = json.loads(str(attempt["route_descriptor_json"]))
    assert route["schema"] == "work_package_attempt_route.v2"
    assert route["task_route"]["task_kind"] == "durable_command"
    assert route["task_route"]["backend_kind"] == "soma_durable_run"
    assert "reasoning_spec" not in route


def test_explicit_reasoning_route_fails_without_reasoning_backend_without_reservation(
    tmp_path: Path,
) -> None:
    config, config_path, repo = _config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="admission",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)
    kernel = CompanyKernelStore(config.resolve_runs_dir())
    assert kernel.init_db() == [1, 2, 3, 4]
    _insert_kernel_graph(kernel)
    manager = TaskManager(config, config_path, scope_store=scope)
    request = AdmissionRequestV1(
        mission_id=MISSION_ID,
        work_package_id=ROOT_PACKAGE_ID,
        controller_request_id="admit-explicit-reasoning-without-backend",
        repo_name="sample",
        task_request=ReasoningTaskRequestV1(reasoning_spec=_spec()),
    )

    with pytest.raises(AdmissionError, match="soma_reasoning"):
        admit_work_package(manager, request)
    with kernel.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_package_attempts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_root_package_admission_reserves_attempt_task_scope_then_starts(
    tmp_path: Path,
) -> None:
    manager, fake, kernel, scope = _environment(tmp_path)
    result = admit_work_package(
        manager, _request(ROOT_PACKAGE_ID, "admit-root")
    )

    assert result.created is True
    assert result.proof_refs == ()
    assert result.task_start["state"] == "completed"
    assert result.task_start["task_id"] == result.task_id
    assert fake.provider_create_calls == 1
    attempt_scope = scope.scope_for_run(result.task_start["backend_reference"])
    assert attempt_scope.attempt_status == "attached"
    with kernel.connect() as conn:
        attempt = conn.execute(
            "SELECT * FROM work_package_attempts WHERE attempt_id = ?",
            (result.attempt_id,),
        ).fetchone()
        assert attempt is not None
        assert str(attempt["task_id"]) == result.task_id
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM dependency_satisfaction_proofs"
            ).fetchone()[0]
            == 0
        )


def test_downstream_without_required_evidence_is_not_admitted(tmp_path: Path) -> None:
    manager, fake, kernel, _scope = _environment(tmp_path)
    with pytest.raises(AdmissionError, match="evidence candidate is missing"):
        admit_work_package(
            manager, _request(DOWNSTREAM_PACKAGE_ID, "admit-blocked")
        )
    assert fake.provider_create_calls == 0
    with kernel.connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM dependency_satisfaction_proofs"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM work_package_attempts").fetchone()[0]
            == 0
        )


def test_downstream_admission_freezes_proof_into_attempt_and_task_identity(
    tmp_path: Path,
) -> None:
    manager, fake, kernel, _scope = _environment(tmp_path)
    request = _request(DOWNSTREAM_PACKAGE_ID, "admit-downstream", with_evidence=True)
    result = admit_work_package(manager, request)

    assert result.created is True
    assert len(result.proof_refs) == 1
    assert result.task_start["state"] == "completed"
    assert fake.provider_create_calls == 1
    with kernel.connect() as conn:
        proof = conn.execute("SELECT * FROM dependency_satisfaction_proofs").fetchone()
        attempt = conn.execute(
            "SELECT * FROM work_package_attempts WHERE attempt_id = ?",
            (result.attempt_id,),
        ).fetchone()
        assert proof is not None and attempt is not None
        route = json.loads(str(attempt["route_descriptor_json"]))
        assert route["dependency_proof_refs"] == [
            {"ref": result.proof_refs[0].ref, "hash": result.proof_refs[0].hash}
        ]
        assert str(proof["proof_hash"]) == result.proof_refs[0].hash
        target = conn.execute(
            "SELECT contract_hash FROM work_packages WHERE work_package_id = ?",
            (DOWNSTREAM_PACKAGE_ID,),
        ).fetchone()

    final_spec = request.task_request.reasoning_spec.model_copy(
        update={
            "assignment_ref": f"work-package:{DOWNSTREAM_PACKAGE_ID}",
            "assignment_hash": str(target["contract_hash"]),
            "dependency_proof_refs": result.proof_refs,
        }
    )
    task = manager.store.get_task(result.task_id)
    assert route["task_route"] == {
        "task_kind": "reasoning",
        "backend_kind": "soma_reasoning",
        "request_hash": route["task_route"]["request_hash"],
        "reasoning_spec": {
            "ref": reasoning_spec_ref(final_spec),
            "hash": reasoning_spec_hash(final_spec),
        },
    }
    assert task.request_hash != route["task_route"]["request_hash"]
    assert task.backend_identity["work_package_attempt_ref"] == result.attempt_id
    assert task.backend_identity["work_package_attempt_hash"] == result.attempt_hash

    replay_without_current_candidate = request.model_copy(
        update={"evidence_candidates": {}}
    )
    replay = admit_work_package(manager, replay_without_current_candidate)
    assert replay.created is False
    assert replay.attempt_id == result.attempt_id
    assert replay.task_id == result.task_id
    assert replay.proof_refs == result.proof_refs
    assert fake.provider_create_calls == 1


def test_response_loss_after_reservation_commit_replays_same_attempt_and_task(
    tmp_path: Path,
) -> None:
    manager, fake, kernel, _scope = _environment(tmp_path)
    request = _request(DOWNSTREAM_PACKAGE_ID, "admit-response-loss", with_evidence=True)

    def crash(attempt_id: str, task_id: str) -> None:
        assert attempt_id and task_id
        with kernel.connect() as conn:
            assert (
                conn.execute(
                    "SELECT 1 FROM work_package_attempts WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchone()
                is not None
            )
            assert (
                conn.execute(
                    "SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                is not None
            )
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM dependency_satisfaction_proofs"
                ).fetchone()[0]
                == 1
            )
        assert fake.provider_create_calls == 0
        raise RuntimeError("response-lost-after-admission-commit")

    with pytest.raises(RuntimeError, match="response-lost"):
        admit_work_package(manager, request, _after_commit_hook=crash)

    replay = admit_work_package(manager, request)
    assert replay.created is False
    assert replay.task_start["state"] == "completed"
    assert fake.provider_create_calls == 1
    with kernel.connect() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM work_package_attempts").fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM dependency_satisfaction_proofs"
            ).fetchone()[0]
            == 1
        )


def test_legacy_reasoning_coupled_route_v1_is_frozen_and_non_replayable(
    tmp_path: Path,
) -> None:
    manager, fake, _kernel, _scope = _environment(tmp_path)
    request = _request(ROOT_PACKAGE_ID, "legacy-v1-frozen")
    binding, effective_repo_name = manager._resolve_repository_binding(
        project_id=PROJECT_ID,
        repo_name="sample",
        working_directory="",
    )
    legacy_attempt = {
        "work_package_id": ROOT_PACKAGE_ID,
        "route_descriptor_json": json.dumps(
            {
                "schema": "work_package_attempt_route.v1",
                "dependency_proof_refs": [],
            }
        ),
    }

    with pytest.raises(AdmissionError, match="frozen and non-replayable"):
        _replay_existing_attempt(
            manager,
            request,
            binding=binding,
            effective_repo_name=effective_repo_name,
            existing_attempt=legacy_attempt,
        )
    assert fake.provider_create_calls == 0


def test_old_plan_package_cannot_be_newly_admitted_after_replan(tmp_path: Path) -> None:
    manager, fake, kernel, _scope = _environment(tmp_path)
    new_plan = "planrev_" + "d" * 24
    with kernel.connect() as conn:
        conn.execute(
            "INSERT INTO plan_revisions(plan_revision_id, mission_id, revision_number, parent_plan_revision_id, plan_contract_json, plan_content_hash, deliberation_ref, deliberation_hash, accepted_by_ref, acceptance_basis_ref, controller_request_id, request_hash, accepted_at) VALUES (?, ?, 2, ?, '{}', ?, '', '', ?, 'replan', 'replan-request', ?, ?)",
            (new_plan, MISSION_ID, PLAN_ID, _hash("d"), OWNER, _hash("e"), NOW),
        )
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = ?, plan_state_version = 2, kernel_state_version = 2 WHERE mission_id = ?",
            (new_plan, MISSION_ID),
        )
    with pytest.raises(AdmissionError, match="not in the current PlanRevision"):
        admit_work_package(
            manager, _request(ROOT_PACKAGE_ID, "admit-old-plan")
        )
    assert fake.provider_create_calls == 0


def test_existing_attempt_requires_explicit_successor_lineage_for_new_request(
    tmp_path: Path,
) -> None:
    manager, fake, _kernel, _scope = _environment(tmp_path)
    first = admit_work_package(
        manager, _request(ROOT_PACKAGE_ID, "admit-first")
    )
    assert first.task_start["state"] == "completed"
    with pytest.raises(AdmissionError, match="explicitly supersede"):
        admit_work_package(manager, _request(ROOT_PACKAGE_ID, "admit-second"))
    assert fake.provider_create_calls == 1


def test_single_active_blocks_new_route_until_prior_attempt_is_terminal_or_contained(
    tmp_path: Path,
) -> None:
    manager, fake, _kernel, _scope = _environment(tmp_path, fake_case="long_running")
    first = admit_work_package(
        manager, _request(ROOT_PACKAGE_ID, "admit-active-first")
    )
    assert first.task_start["state"] == "running"
    second = _request(ROOT_PACKAGE_ID, "admit-active-second").model_copy(
        update={"supersedes_attempt_id": first.attempt_id}
    )
    with pytest.raises(AdmissionError, match="single_active"):
        admit_work_package(manager, second)
    assert fake.provider_create_calls == 1


def test_changed_proof_set_can_create_explicit_successor_after_terminal_attempt(
    tmp_path: Path,
) -> None:
    manager, fake, kernel, _scope = _environment(tmp_path)
    first_request = _request(
        DOWNSTREAM_PACKAGE_ID, "admit-proof-first", with_evidence=True
    )
    first = admit_work_package(manager, first_request)
    assert first.task_start["state"] == "completed"

    changed_candidate = EvidenceAvailableCandidateV1(
        selector_ref=SELECTOR_REF,
        selector_hash=_hash("a"),
        evidence_ref="artifact:upstream-evidence-successor",
        evidence_hash=_hash("d"),
    )
    successor_request = _request(
        DOWNSTREAM_PACKAGE_ID, "admit-proof-successor", with_evidence=True
    ).model_copy(
        update={
            "supersedes_attempt_id": first.attempt_id,
            "evidence_candidates": {EDGE_ID: changed_candidate},
        }
    )
    successor = admit_work_package(manager, successor_request)

    assert successor.created is True
    assert successor.attempt_id != first.attempt_id
    assert successor.proof_refs != first.proof_refs
    assert fake.provider_create_calls == 2
    with kernel.connect() as conn:
        row = conn.execute(
            "SELECT supersedes_attempt_id FROM work_package_attempts WHERE attempt_id = ?",
            (successor.attempt_id,),
        ).fetchone()
        assert row is not None
        assert str(row["supersedes_attempt_id"]) == first.attempt_id


def _prepared(
    package_id: str,
    *,
    with_evidence: bool = False,
    supersedes_attempt_id: str | None = None,
) -> PreparedTaskAdmissionV1:
    request = _request(package_id, "prepared-template", with_evidence=with_evidence)
    return PreparedTaskAdmissionV1(
        work_package_id=package_id,
        repo_name=request.repo_name,
        task_request=request.task_request,
        supersedes_attempt_id=supersedes_attempt_id,
        evidence_candidates=request.evidence_candidates,
        published_success_candidates=request.published_success_candidates,
    )


def _coordinator_request(
    *prepared: PreparedTaskAdmissionV1,
    controller_request_id: str = "coordinator-fixture",
    concurrency: int = 1,
    max_new_attempts: int = 8,
) -> AdmitReadyWorkRequestV1:
    return AdmitReadyWorkRequestV1(
        mission_id=MISSION_ID,
        expected_plan_revision_id=PLAN_ID,
        expected_plan_state_version=1,
        controller_request_id=controller_request_id,
        max_new_attempts=max_new_attempts,
        canonical_concurrency_limit=concurrency,
        prepared_admissions=prepared,
    )


def test_coordinator_uses_package_key_order_and_not_ready_does_not_consume_capacity(
    tmp_path: Path,
) -> None:
    manager, fake, _kernel, _scope = _environment(tmp_path)
    result = admit_ready_work(
        manager,
        _coordinator_request(
            _prepared(ROOT_PACKAGE_ID),
            _prepared(DOWNSTREAM_PACKAGE_ID),
        ),
    )

    assert result.considered_package_keys == ("downstream", "root")
    assert [item.work_package_id for item in result.admitted] == [ROOT_PACKAGE_ID]
    assert result.deferred[0].work_package_id == DOWNSTREAM_PACKAGE_ID
    assert result.deferred[0].reason == "not_ready"
    assert fake.provider_create_calls == 1


def test_coordinator_c1_capacity_is_bounded_even_when_two_routes_are_ready(
    tmp_path: Path,
) -> None:
    manager, fake, _kernel, _scope = _environment(tmp_path, fake_case="long_running")
    result = admit_ready_work(
        manager,
        _coordinator_request(
            _prepared(ROOT_PACKAGE_ID),
            _prepared(DOWNSTREAM_PACKAGE_ID, with_evidence=True),
            concurrency=1,
            max_new_attempts=8,
        ),
    )

    assert result.considered_package_keys == ("downstream", "root")
    assert [item.work_package_id for item in result.admitted] == [DOWNSTREAM_PACKAGE_ID]
    assert result.active_attempts_before == 0
    assert result.active_attempts_after == 1
    assert any(
        item.work_package_id == ROOT_PACKAGE_ID and item.reason == "capacity"
        for item in result.deferred
    )
    assert fake.provider_create_calls == 1


def test_duplicate_coordinator_request_replays_without_duplicate_backend_start(
    tmp_path: Path,
) -> None:
    manager, fake, _kernel, _scope = _environment(tmp_path)
    request = _coordinator_request(
        _prepared(ROOT_PACKAGE_ID),
        controller_request_id="coordinator-replay",
    )
    first = admit_ready_work(manager, request)
    second = admit_ready_work(manager, request)

    assert len(first.admitted) == 1
    assert len(second.admitted) == 0
    assert len(second.replayed) == 1
    assert second.replayed[0].attempt_id == first.admitted[0].attempt_id
    assert second.replayed[0].task_id == first.admitted[0].task_id
    assert fake.provider_create_calls == 1


def test_coordinator_stale_plan_state_version_fails_closed(tmp_path: Path) -> None:
    manager, fake, kernel, _scope = _environment(tmp_path)
    request = _coordinator_request(_prepared(ROOT_PACKAGE_ID))
    with kernel.connect() as conn:
        conn.execute(
            "UPDATE missions SET plan_state_version = 2 WHERE mission_id = ?",
            (MISSION_ID,),
        )
    with pytest.raises(AdmissionError, match="plan_state_version"):
        admit_ready_work(manager, request)
    assert fake.provider_create_calls == 0


def test_batch_is_bounded_and_never_turns_into_scheduler_loop(tmp_path: Path) -> None:
    manager, _fake, _kernel, _scope = _environment(tmp_path)
    too_many = tuple(
        _request(ROOT_PACKAGE_ID, f"batch-{index}")
        for index in range(MAX_ADMISSION_BATCH + 1)
    )
    with pytest.raises(AdmissionError, match="exceeds this bounded pass"):
        admit_work_package_batch(manager, too_many)
    with pytest.raises(AdmissionError, match="within 1"):
        admit_work_package_batch(manager, (), max_batch=MAX_ADMISSION_BATCH + 1)
