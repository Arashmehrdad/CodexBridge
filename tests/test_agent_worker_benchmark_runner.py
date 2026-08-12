"""G6.2 canonical trial-runner proofs with scripted provider clients only."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from soma.agent_worker_benchmark import (
    UNITS,
    build_g6_plan_graph_manifest,
    work_package_contract_materials,
)
from soma.agent_worker_benchmark_runner import (
    G6BenchmarkRunnerError,
    make_g6_assignment_resolver,
    make_g6_task_id_resolver,
    run_g6_trial,
    validate_g6_plan,
)
from soma.company_kernel import MISSION_ID_DOMAIN, canonical_hash, canonical_json
from soma.company_kernel.service import accept_plan_graph
from soma.company_kernel.store import CompanyKernelStore
from soma.config import load_config
from soma.project_scope import ProjectScopeStore
from soma.reasoning.benchmark_evidence import BENCHMARK_SEMANTIC_SCHEMA_VERSION
from soma.reasoning.codex_app_server import CodexTurnEvidence
from soma.reasoning.codex_g6_backend import (
    CODEX_G6_MODEL,
    CODEX_G6_PROTOCOL_MANIFEST_SHA256,
    CodexG6ReasoningBackend,
)
from soma.reasoning.store import ReasoningBackendStore
from soma.tasks.manager import TaskManager
from soma.tasks.store import TaskStore


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPANY_ID = "company_" + "a" * 24
MISSION_ID = "mission_" + "b" * 24
PROJECT_ID = "Project_G6_Benchmark"
RESOURCE_ID = "Resource_G6_Benchmark"
OWNER = "owner-controller:g6-benchmark"
NOW = "2026-08-12T16:00:00+00:00"


def _hash(character: str) -> str:
    return character * 64


def _config(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    executable = tmp_path / "fake-pwsh.exe"
    executable.write_bytes(b"g6-runner-fixture")
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


def _prepare_kernel_and_scope(tmp_path: Path):
    config, config_path, repo = _config(tmp_path)
    task_store = TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="g6-benchmark",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)
    kernel = CompanyKernelStore(config.resolve_runs_dir())
    assert kernel.init_db() == [1, 2, 3]
    mission_contract = {"purpose": "scripted G6 benchmark proof"}
    with kernel.connect() as conn:
        conn.execute(
            "INSERT INTO companies(company_id, company_key, display_name, executive_authority_ref, creation_request_id, creation_request_hash, created_at) "
            "VALUES (?, 'g6-company', 'G6 Company', ?, 'g6-company-create', ?, ?)",
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
            ) VALUES (?, ?, 'g6-mission', ?, ?, 1, ?, ?, ?, ?, NULL, 0, 0, ?, ?, ?, ?)
            """,
            (
                MISSION_ID,
                COMPANY_ID,
                PROJECT_ID,
                RESOURCE_ID,
                canonical_json(mission_contract),
                canonical_hash(MISSION_ID_DOMAIN, mission_contract),
                OWNER,
                OWNER,
                "g6-mission-create",
                _hash("2"),
                NOW,
                NOW,
            ),
        )

    graph = build_g6_plan_graph_manifest(
        REPO_ROOT,
        mission_id=MISSION_ID,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
    )
    accepted = accept_plan_graph(
        kernel,
        company_id=COMPANY_ID,
        mission_id=MISSION_ID,
        expected_current_plan_revision_id=None,
        expected_plan_state_version=0,
        expected_kernel_state_version=0,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        controller_request_id="g6-graph-accept",
        accepted_by_ref=OWNER,
        acceptance_basis_ref="scripted G6 graph acceptance",
        plan_contract_base={"purpose": "run frozen G6 benchmark"},
        graph_manifest=graph,
        work_package_contracts=work_package_contract_materials(REPO_ROOT),
        accepted_at=NOW,
    )
    assert accepted.created is True
    return config, config_path, repo, task_store, scope, kernel, accepted


def _semantic_from_prompt(prompt: str) -> str:
    marker = "ASSIGNMENT JSON:\n"
    assert marker in prompt
    packet = json.loads(prompt.split(marker, 1)[1])
    questions = packet["rubric"]["questions"]
    claims = [
        {
            "claim_id": f"claim_{index}",
            "claim_class": "observation",
            "subject_key": question["fact_key"],
            "statement": f"Scripted claim for {question['fact_key']}.",
            "supports_evidence_ids": [],
            "opposes_evidence_ids": [],
            "uncertainty_ids": [],
        }
        for index, question in enumerate(questions, start=1)
    ]
    return json.dumps(
        {
            "schema_version": BENCHMARK_SEMANTIC_SCHEMA_VERSION,
            "submission_disposition": "complete",
            "executive_summary": "Scripted source-bounded G6 result.",
            "claims": claims,
            "evidence": [],
            "uncertainties": [],
            "blockers": [],
            "critical_trap": {
                "disposition": "false",
                "statement": "The frozen critical trap is false in this scripted fixture.",
                "supports_evidence_ids": [],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class _ClientFactory:
    def __init__(self, delay_seconds: float = 0.06) -> None:
        self.delay_seconds = delay_seconds
        self._lock = threading.Lock()
        self.created = 0

    def __call__(self):
        with self._lock:
            self.created += 1
            number = self.created
        return _ScriptedClient(number, self.delay_seconds)


class _ScriptedClient:
    def __init__(self, number: int, delay_seconds: float) -> None:
        self.thread_id = f"thr_g6_{number:04d}"
        self.turn_id = f"turn_g6_{number:04d}"
        self.delay_seconds = delay_seconds
        self.agent_message = ""
        self.server_requests: list[dict] = []
        self.closed = False

    def start_thread(self, *, working_directory: str, model: str = "") -> dict:
        assert Path(working_directory).is_absolute()
        assert model == CODEX_G6_MODEL
        return {"thread": {"id": self.thread_id}}

    def begin_turn(self, **kwargs) -> int:
        assert kwargs["model"] == CODEX_G6_MODEL
        assert kwargs["effort"] == "low"
        self.agent_message = _semantic_from_prompt(kwargs["prompt"])
        return 3

    def wait_for_turn_started(self, *, thread_id: str, timeout_seconds: float) -> str:
        assert thread_id == self.thread_id
        assert timeout_seconds > 0
        return self.turn_id

    def wait_for_turn_completed(
        self, *, thread_id: str, turn_id: str, timeout_seconds: float
    ) -> CodexTurnEvidence:
        assert (thread_id, turn_id) == (self.thread_id, self.turn_id)
        time.sleep(self.delay_seconds)
        return CodexTurnEvidence(
            thread_id=self.thread_id,
            turn_id=self.turn_id,
            status="completed",
            events=(
                {"method": "turn/started", "params": {"threadId": self.thread_id}},
                {"method": "turn/completed", "params": {"threadId": self.thread_id}},
            ),
            agent_message=self.agent_message,
            token_usage_events=(
                {
                    "tokenUsage": {
                        "total": {
                            "inputTokens": 100,
                            "cachedInputTokens": 0,
                            "outputTokens": 20,
                            "reasoningOutputTokens": 5,
                            "totalTokens": 120,
                        }
                    }
                },
            ),
        )

    def interrupt_turn(self, *, thread_id: str, turn_id: str) -> dict:
        raise AssertionError("scripted G6 runner does not cancel")

    def read_thread(self, thread_id: str, *, include_turns: bool = True) -> dict:
        return {"thread": {"id": thread_id, "turns": []}}

    def close(self) -> None:
        self.closed = True


def _environment(tmp_path: Path, *, delay_seconds: float = 0.06):
    config, config_path, repo, task_store, scope, kernel, accepted = (
        _prepare_kernel_and_scope(tmp_path)
    )
    reasoning_store = ReasoningBackendStore(config.resolve_runs_dir())
    clients = _ClientFactory(delay_seconds)
    backend = CodexG6ReasoningBackend(
        reasoning_store,
        assignment_resolver=make_g6_assignment_resolver(kernel, REPO_ROOT),
        task_id_resolver=make_g6_task_id_resolver(task_store),
        client_factory=clients,
        preflight=lambda: {
            "auth_type": "chatgpt",
            "protocol_manifest_sha256": CODEX_G6_PROTOCOL_MANIFEST_SHA256,
            "models": [CODEX_G6_MODEL],
            "model_available": True,
        },
        working_directory=repo,
    )
    manager = TaskManager(
        config,
        config_path,
        reasoning_backend=backend,
        scope_store=scope,
    )
    return manager, backend, clients, kernel, accepted


def _run(
    manager, backend, kernel, *, condition: int, repetition: int = 1, phase="screening"
):
    return run_g6_trial(
        task_manager=manager,
        kernel_store=kernel,
        repo_root=REPO_ROOT,
        mission_id=MISSION_ID,
        repo_name="sample",
        phase=phase,
        canonical_concurrency_limit=condition,
        repetition_index=repetition,
        submission_loader=backend.load_evidence_submission,
        assessment_loader=backend.load_benchmark_assessment,
    )


def test_current_plan_and_assignment_resolver_preserve_exact_frozen_contract(
    tmp_path: Path,
) -> None:
    manager, backend, _clients, kernel, accepted = _environment(
        tmp_path, delay_seconds=0
    )
    context = validate_g6_plan(kernel, REPO_ROOT, MISSION_ID)

    assert context.plan_revision_id == accepted.plan_revision_id
    assert list(context.work_packages) == [unit.unit_id for unit in UNITS]
    resolver = make_g6_assignment_resolver(kernel, REPO_ROOT)
    unit_id = "B01"
    resolved = resolver(f"work-package:{context.work_packages[unit_id]}")
    assert resolved.unit_id == unit_id
    assert resolved.assignment_hash != resolved.packet_sha256
    assert resolved.packet_bytes
    assert manager._reasoning_backend.kind == "soma_reasoning"


def test_c1_c2_c4_c8_use_exact_canonical_peak_and_successor_attempts(
    tmp_path: Path,
) -> None:
    manager, backend, clients, kernel, _accepted = _environment(tmp_path)
    results = [
        _run(manager, backend, kernel, condition=condition)
        for condition in (1, 2, 4, 8)
    ]

    assert [result.condition for result in results] == ["C1", "C2", "C4", "C8"]
    assert [result.peak_active_canonical_tasks for result in results] == [1, 2, 4, 8]
    assert clients.created == 32
    assert all(result.metrics.expected_units == 8 for result in results)
    assert all(result.metrics.collected_submissions == 8 for result in results), [
        (
            result.condition,
            result.metrics.collected_submissions,
            [
                (
                    unit.unit_id,
                    unit.task_state,
                    unit.submission_present,
                    unit.assessment_present,
                    unit.error,
                )
                for unit in result.unit_results
            ],
        )
        for result in results
    ]
    assert all(result.metrics.schema_valid_submission_rate == 1 for result in results)
    assert all(result.metrics.required_fact_key_recall == 1 for result in results)
    assert all(result.metrics.critical_trap_failures == 0 for result in results)
    assert all(result.metrics.missing_units == 0 for result in results)
    assert all(result.metrics.task_backend_starts == 8 for result in results)
    assert all(result.metrics.automatic_retry_count == 0 for result in results)
    assert results[0].metrics.deliberate_trial_repetition is False
    assert all(result.metrics.deliberate_trial_repetition for result in results[1:])
    assert results[-1].makespan_seconds < results[0].makespan_seconds

    with kernel.connect() as conn:
        for unit in UNITS:
            rows = conn.execute(
                "SELECT attempt_id, supersedes_attempt_id FROM work_package_attempts "
                "WHERE work_package_id = ? ORDER BY created_at, attempt_id",
                (results[0].unit_results[int(unit.unit_id[1:]) - 1].work_package_id,),
            ).fetchall()
            assert len(rows) == 4
            assert rows[0]["supersedes_attempt_id"] is None
            for index in range(1, 4):
                assert str(rows[index]["supersedes_attempt_id"]) == str(
                    rows[index - 1]["attempt_id"]
                )


def test_exact_trial_replay_returns_stored_measurement_without_provider_start(
    tmp_path: Path,
) -> None:
    manager, backend, clients, kernel, _accepted = _environment(tmp_path)
    first = _run(manager, backend, kernel, condition=4)
    creates_after_first = clients.created

    replay = _run(manager, backend, kernel, condition=4)

    assert replay.trial_id == first.trial_id
    assert replay.trial_manifest_hash == first.trial_manifest_hash
    assert replay.replayed_stored_result is True
    assert clients.created == creates_after_first == 8
    assert replay.unit_results == first.unit_results
    assert replay.makespan_seconds == first.makespan_seconds


def test_new_confirmation_repetition_creates_one_exact_successor_per_unit(
    tmp_path: Path,
) -> None:
    manager, backend, clients, kernel, _accepted = _environment(
        tmp_path, delay_seconds=0
    )
    first = _run(
        manager, backend, kernel, condition=2, phase="confirmation", repetition=1
    )
    second = _run(
        manager, backend, kernel, condition=2, phase="confirmation", repetition=2
    )

    assert first.trial_id != second.trial_id
    assert clients.created == 16
    assert all(item.created for item in second.unit_results)
    assert all(item.supersedes_attempt_id for item in second.unit_results)
    assert second.metrics.deliberate_trial_repetition is True


def test_active_prior_head_blocks_whole_new_trial_before_any_provider_start(
    tmp_path: Path,
) -> None:
    manager, backend, clients, kernel, _accepted = _environment(
        tmp_path, delay_seconds=0
    )
    first = _run(manager, backend, kernel, condition=1)
    prior_creates = clients.created
    active_task_id = first.unit_results[0].task_id
    with manager.store.connect() as conn:
        conn.execute(
            "UPDATE tasks SET state = 'running', ended_at = NULL WHERE task_id = ?",
            (active_task_id,),
        )

    with pytest.raises(G6BenchmarkRunnerError, match="active or uncontained"):
        _run(manager, backend, kernel, condition=2)

    assert clients.created == prior_creates
    with kernel.connect() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM work_package_attempts").fetchone()[0]
            == 8
        )


def test_trial_artifacts_are_durable_and_semantic_metrics_remain_explicitly_unadjudicated(
    tmp_path: Path,
) -> None:
    manager, backend, _clients, kernel, _accepted = _environment(
        tmp_path, delay_seconds=0
    )
    result = _run(manager, backend, kernel, condition=8)
    directory = (
        manager.store.runs_dir / "agent_worker_benchmark_trials" / result.trial_id
    )

    assert (directory / "manifest.json").is_file()
    assert (directory / "fanin.json").is_file()
    assert (directory / "result.json").is_file()
    assert result.metrics.claims == 40
    assert result.metrics.claims_without_support == 40
    assert result.metrics.claims_without_support_rate == 1
    assert result.metrics.fact_key_correctness is None
    assert result.metrics.evidence_precision is None
    assert result.metrics.unsupported_assertion_rate is None
    assert result.metrics.semantic_adjudication_required is True
