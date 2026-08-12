"""G3.5 C1/C2/C4/C8 bounded fan-out/restart/FanIn mechanics proof.

Every parametrized concurrency run uses the same immutable eight-WorkPackage
shape and the same prepared reasoning assignments. Only canonical admission
concurrency changes. No real provider, scheduler loop, protected mutation, or
semantic adjudication participates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soma.company_kernel.coordinator import (
    AdmitReadyWorkRequestV1,
    PreparedReasoningAdmissionV1,
    admit_ready_work,
)
from soma.company_kernel.store import CompanyKernelStore
from soma.config import AppConfig, load_config
from soma.project_scope import ProjectScopeStore
from soma.reasoning.fake import FakeReasoningBackend
from soma.reasoning.models import ReasoningBudgetsV1, ReasoningSpecV1
from soma.reasoning.store import ReasoningBackendStore
from soma.tasks.manager import TaskManager
from soma.tasks.store import TaskStore
from soma.worker_evidence import (
    EvidenceAssignmentV1,
    EvidenceByteAccountingV1,
    EvidenceClaimV1,
    EvidenceProducerV1,
    EvidenceRecordV1,
    EvidenceSubmissionV1,
    EvidenceUsageV1,
    EvidenceWorkIdentityV1,
)
from soma.worker_evidence.fanin import synthesize_fanin


COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
PLAN_ID = "planrev_" + "3" * 24
PROJECT_ID = "Project_G3_Concurrency"
RESOURCE_ID = "Resource_G3_Concurrency"
OWNER = "owner-controller:g3-concurrency"
NOW = "2026-08-12T10:30:00+00:00"
UNIT_COUNT = 8
UNIT_KEYS = tuple(f"unit-{index:02d}" for index in range(1, UNIT_COUNT + 1))
PACKAGE_IDS = tuple("workpkg_" + f"{index:024x}" for index in range(1, UNIT_COUNT + 1))
OUTCOME_IDS = tuple(
    "outcome_" + f"{index + 32:024x}" for index in range(1, UNIT_COUNT + 1)
)


def _hash(character: str) -> str:
    return character * 64


def _config(tmp_path: Path) -> tuple[AppConfig, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    executable = tmp_path / "fake-pwsh.exe"
    executable.write_bytes(b"g3-concurrency-fixture")
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
        assignment_ref="assignment:g3-eight-unit-template",
        assignment_hash=_hash("a"),
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash=_hash("b"),
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash=_hash("c"),
        authority_ref="authority:g3-concurrency",
        authority_hash=_hash("d"),
        provider_route_ref="route:fake-g3-concurrency",
        provider_route_hash=_hash("e"),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _insert_eight_package_graph(store: CompanyKernelStore) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO companies(company_id, company_key, display_name, "
            "executive_authority_ref, creation_request_id, creation_request_hash, created_at) "
            "VALUES (?, 'g3-concurrency', 'G3 Concurrency', ?, 'company-request', ?, ?)",
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
            ) VALUES (?, ?, 'g3-concurrency-mission', ?, ?, 1, '{}', ?, ?, ?, NULL,
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
            ) VALUES (?, ?, 1, NULL, '{}', ?, '', '', ?, 'g3-concurrency-plan',
                      'plan-request', ?, ?)
            """,
            (PLAN_ID, MISSION_ID, _hash("4"), OWNER, _hash("5"), NOW),
        )
        conn.execute(
            "UPDATE missions SET current_plan_revision_id = ?, plan_state_version = 1, "
            "kernel_state_version = 1 WHERE mission_id = ?",
            (PLAN_ID, MISSION_ID),
        )
        for index, (package_id, package_key, outcome_id) in enumerate(
            zip(PACKAGE_IDS, UNIT_KEYS, OUTCOME_IDS, strict=True), start=1
        ):
            contract_hash = f"{index:x}" * 64
            contract_hash = contract_hash[:64]
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
                    PLAN_ID,
                    package_key,
                    outcome_id,
                    PROJECT_ID,
                    RESOURCE_ID,
                    contract_hash,
                    OWNER,
                    OWNER,
                    f"package:{package_key}",
                    _hash("6"),
                    NOW,
                ),
            )
        conn.execute(
            "INSERT INTO plan_graph_manifests(plan_revision_id, mission_id, schema_version, "
            "manifest_json, manifest_hash, package_count, edge_count, created_at) "
            "VALUES (?, ?, 'plan_graph_manifest.v1', '{}', ?, 8, 0, ?)",
            (PLAN_ID, MISSION_ID, _hash("7"), NOW),
        )


class SelectiveFakeReasoningBackend(FakeReasoningBackend):
    """Choose deterministic fake outcome from the frozen WorkPackage assignment ref."""

    def start(self, spec: ReasoningSpecV1, backend_ref: str):
        previous = self.case
        assignment = spec.assignment_ref
        if assignment == f"work-package:{PACKAGE_IDS[6]}":
            self.case = "provider_rejection"
        elif assignment == f"work-package:{PACKAGE_IDS[7]}":
            self.case = "timeout"
        else:
            self.case = "success"
        try:
            return super().start(spec, backend_ref)
        finally:
            self.case = previous


class LongRunningFirstFakeReasoningBackend(FakeReasoningBackend):
    def start(self, spec: ReasoningSpecV1, backend_ref: str):
        previous = self.case
        self.case = (
            "long_running"
            if spec.assignment_ref == f"work-package:{PACKAGE_IDS[0]}"
            else "success"
        )
        try:
            return super().start(spec, backend_ref)
        finally:
            self.case = previous


def _environment(tmp_path: Path, *, backend_cls=SelectiveFakeReasoningBackend):
    config, config_path, repo = _config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="g3-concurrency",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)
    kernel = CompanyKernelStore(config.resolve_runs_dir())
    assert kernel.init_db() == [1, 2, 3]
    _insert_eight_package_graph(kernel)
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    fake = backend_cls(reasoning_store, case="success")
    manager = TaskManager(
        config, config_path, reasoning_backend=fake, scope_store=scope
    )
    return config, config_path, manager, fake, kernel


def _restart(
    config: AppConfig, config_path: Path, *, backend_cls=SelectiveFakeReasoningBackend
):
    scope = ProjectScopeStore(config.resolve_runs_dir())
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    fake = backend_cls(reasoning_store, case="success")
    manager = TaskManager(
        config, config_path, reasoning_backend=fake, scope_store=scope
    )
    return manager, fake


def _prepared_routes() -> tuple[PreparedReasoningAdmissionV1, ...]:
    # Deliberately reverse caller order; the coordinator must use package_key order.
    return tuple(
        PreparedReasoningAdmissionV1(
            work_package_id=package_id,
            repo_name="sample",
            reasoning_spec=_spec(),
        )
        for package_id in reversed(PACKAGE_IDS)
    )


def _request(
    concurrency: int, *, controller_request_id: str
) -> AdmitReadyWorkRequestV1:
    return AdmitReadyWorkRequestV1(
        mission_id=MISSION_ID,
        expected_plan_revision_id=PLAN_ID,
        expected_plan_state_version=1,
        controller_request_id=controller_request_id,
        max_new_attempts=8,
        canonical_concurrency_limit=concurrency,
        prepared_admissions=_prepared_routes(),
    )


def _db_counts(kernel: CompanyKernelStore) -> dict[str, int]:
    with kernel.connect() as conn:
        return {
            "attempts": conn.execute(
                "SELECT COUNT(*) FROM work_package_attempts"
            ).fetchone()[0],
            "tasks": conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE task_kind = 'reasoning'"
            ).fetchone()[0],
            "backend_runs": conn.execute(
                "SELECT COUNT(*) FROM reasoning_backend_runs"
            ).fetchone()[0],
            "start_attempts": conn.execute(
                "SELECT COUNT(*) FROM reasoning_backend_start_attempts"
            ).fetchone()[0],
            "distinct_backend_refs": conn.execute(
                "SELECT COUNT(DISTINCT backend_ref) FROM reasoning_backend_start_attempts"
            ).fetchone()[0],
        }


def _attempt_rows(kernel: CompanyKernelStore):
    with kernel.connect() as conn:
        return conn.execute(
            """
            SELECT package.package_key, attempt.attempt_id, attempt.task_id,
                   task.state, task.backend_ref, backend.error_code,
                   backend.provider_status_raw
            FROM work_package_attempts attempt
            JOIN work_packages package ON package.work_package_id = attempt.work_package_id
            JOIN tasks task ON task.task_id = attempt.task_id
            JOIN reasoning_backend_runs backend ON backend.backend_ref = task.backend_ref
            ORDER BY package.package_key
            """
        ).fetchall()


def _run_until_all(
    manager: TaskManager,
    request: AdmitReadyWorkRequestV1,
    *,
    expected_new: int = UNIT_COUNT,
    max_passes: int = 16,
):
    admitted_keys: list[str] = []
    last = None
    package_to_key = dict(zip(PACKAGE_IDS, UNIT_KEYS, strict=True))
    for _ in range(max_passes):
        last = admit_ready_work(manager, request)
        admitted_keys.extend(
            package_to_key[item.work_package_id] for item in last.admitted
        )
        if len(set(admitted_keys)) == expected_new:
            return admitted_keys, last
    raise AssertionError("bounded coordinator did not admit all eight synthetic units")


@pytest.mark.parametrize("concurrency", [1, 2, 4, 8])
def test_same_eight_unit_shape_survives_c1_c2_c4_c8(
    tmp_path: Path, concurrency: int
) -> None:
    _config_obj, _config_path, manager, fake, kernel = _environment(tmp_path)
    request = _request(concurrency, controller_request_id=f"g3-c{concurrency}")

    admitted_keys, _last = _run_until_all(manager, request)

    assert admitted_keys == list(UNIT_KEYS)
    assert fake.provider_create_calls == 8
    assert _db_counts(kernel) == {
        "attempts": 8,
        "tasks": 8,
        "backend_runs": 8,
        "start_attempts": 8,
        "distinct_backend_refs": 8,
    }
    rows = _attempt_rows(kernel)
    assert [str(row["package_key"]) for row in rows] == list(UNIT_KEYS)
    assert [str(row["state"]) for row in rows[:6]] == ["completed"] * 6
    assert str(rows[6]["state"]) == "failed"
    assert str(rows[6]["error_code"]) == "fake_provider_rejected"
    assert str(rows[7]["state"]) == "failed"
    assert str(rows[7]["error_code"]) == "fake_timeout"

    before = _db_counts(kernel)
    replay = admit_ready_work(manager, request)
    assert replay.admitted == ()
    assert len(replay.replayed) == 8
    assert _db_counts(kernel) == before
    assert fake.provider_create_calls == 8


def test_restart_and_controller_reconnect_do_not_duplicate_backend_start(
    tmp_path: Path,
) -> None:
    config, config_path, manager, first_fake, kernel = _environment(tmp_path)
    request = _request(2, controller_request_id="g3-restart-c2")

    first_pass = admit_ready_work(manager, request)
    assert len(first_pass.admitted) == 2
    assert first_fake.provider_create_calls == 2
    assert _db_counts(kernel)["start_attempts"] == 2

    manager, second_fake = _restart(config, config_path)
    admitted_after_restart, _last = _run_until_all(
        manager, request, expected_new=UNIT_COUNT - 2
    )

    assert admitted_after_restart == list(UNIT_KEYS[2:])
    assert second_fake.provider_create_calls == 6
    assert first_fake.provider_create_calls + second_fake.provider_create_calls == 8
    assert _db_counts(kernel) == {
        "attempts": 8,
        "tasks": 8,
        "backend_runs": 8,
        "start_attempts": 8,
        "distinct_backend_refs": 8,
    }

    manager, third_fake = _restart(config, config_path)
    replay = admit_ready_work(manager, request)
    assert replay.admitted == ()
    assert len(replay.replayed) == 8
    assert third_fake.provider_create_calls == 0
    assert _db_counts(kernel)["start_attempts"] == 8


def test_cancellation_survives_reconnect_without_restarting_cancelled_unit(
    tmp_path: Path,
) -> None:
    config, config_path, manager, first_fake, kernel = _environment(
        tmp_path, backend_cls=LongRunningFirstFakeReasoningBackend
    )
    request = _request(1, controller_request_id="g3-cancel-c1")
    first_pass = admit_ready_work(manager, request)
    assert len(first_pass.admitted) == 1
    unit = first_pass.admitted[0]
    task = manager.store.get_task(unit.task_id)
    assert task.state.value == "running"

    cancelled = manager.cancel_task(
        unit.task_id,
        if_state_version=task.state_version,
        reason="G3.5 deterministic cancellation fixture",
        project_id=PROJECT_ID,
    )
    assert cancelled["state"] == "cancelled"
    assert first_fake.provider_cancel_calls == 1

    manager, second_fake = _restart(
        config, config_path, backend_cls=LongRunningFirstFakeReasoningBackend
    )
    reconnect = admit_ready_work(manager, request)
    assert len(reconnect.replayed) == 1
    assert len(reconnect.admitted) == 1
    assert second_fake.provider_create_calls == 1
    assert _db_counts(kernel)["start_attempts"] == 2
    with kernel.connect() as conn:
        row = conn.execute(
            "SELECT state FROM tasks WHERE task_id = ?", (unit.task_id,)
        ).fetchone()
        assert row is not None and str(row["state"]) == "cancelled"


def _success_submission(
    package_key: str, package_id: str, task_id: str
) -> EvidenceSubmissionV1:
    return EvidenceSubmissionV1(
        submission_id=f"submission-{package_key}",
        work_identity=EvidenceWorkIdentityV1(
            mission_id=MISSION_ID,
            plan_revision_id=PLAN_ID,
            work_package_id=package_id,
            task_id=task_id,
        ),
        assignment=EvidenceAssignmentV1(
            contract_ref=f"work-package:{package_id}",
            contract_hash=_hash("8"),
        ),
        producer=EvidenceProducerV1(
            backend_kind="soma_reasoning",
            provider="fake",
            model_or_profile="g3-concurrency-fixture",
        ),
        submission_disposition="complete",
        executive_summary=f"{package_key} completed with deterministic fake evidence.",
        claims=(
            EvidenceClaimV1(
                claim_id=f"claim-{package_key}",
                claim_class="observation",
                subject_key="unit_status",
                statement=f"{package_key} completed successfully.",
                supports_evidence_ids=(f"evidence-{package_key}",),
            ),
        ),
        evidence=(
            EvidenceRecordV1(
                evidence_id=f"evidence-{package_key}",
                source_kind="reasoning_backend_result",
                source_ref=f"task:{task_id}",
                source_hash=_hash("9"),
                fact_key="unit_status",
                fact_value="success",
            ),
        ),
        usage=EvidenceUsageV1(
            wall_time_seconds=1,
            input_tokens=10,
            output_tokens=5,
            cost_usd="0",
        ),
        byte_accounting=EvidenceByteAccountingV1(
            referenced_body_bytes=100,
            omitted_body_bytes=0,
        ),
    )


def test_failure_and_timeout_are_exact_missing_units_in_fanin(tmp_path: Path) -> None:
    _config_obj, _config_path, manager, fake, kernel = _environment(tmp_path)
    request = _request(8, controller_request_id="g3-fanin-c8")
    admitted_keys, _last = _run_until_all(manager, request)
    assert admitted_keys == list(UNIT_KEYS)
    assert fake.provider_create_calls == 8

    rows = _attempt_rows(kernel)
    submissions = {
        str(row["package_key"]): _success_submission(
            str(row["package_key"]),
            PACKAGE_IDS[index],
            str(row["task_id"]),
        )
        for index, row in enumerate(rows[:6])
    }
    fanin = synthesize_fanin(
        expected_unit_refs=UNIT_KEYS,
        submissions=submissions,
        assignment_fact_keys={unit: ("unit_status",) for unit in submissions},
        mission_id=MISSION_ID,
        plan_revision_id=PLAN_ID,
    )

    assert fanin.missing_unit_refs == ("unit-07", "unit-08")
    assert fanin.exact_counts.expected_units == 8
    assert fanin.exact_counts.collected_units == 6
    assert fanin.exact_counts.missing_units == 2
    assert fanin.exact_counts.structured_conflicts == 0
    assert fanin.exact_counts.exact_duplicates == 1
    assert fanin.response_bytes <= 64 * 1024
