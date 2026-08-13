"""Durable real-provider runtime wiring for the frozen G6 benchmark.

This module keeps benchmark state isolated under a dedicated runs directory while
using the real Company Kernel, ProjectScope, canonical Task, reasoning store,
and Codex G6 backend implementations. It also enforces a durable conservative
model-turn ceiling before a benchmark trial may start.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from soma.agent_worker_benchmark import (
    assignment_packet_hash,
    build_g6_plan_graph_manifest,
    work_package_contract_materials,
)
from soma.agent_worker_benchmark_runner import (
    G6_EXPECTED_UNIT_IDS,
    G6TrialResultV1,
    prepare_g6_unit_admission,
    run_g6_trial,
    validate_g6_plan,
)
from soma.company_kernel import MISSION_ID_DOMAIN, canonical_hash, canonical_json
from soma.company_kernel.admission import (
    AdmissionRequestV1,
    admit_reasoning_work_package,
)
from soma.company_kernel.service import accept_plan_graph
from soma.company_kernel.store import CompanyKernelStore
from soma.config import AppConfig
from soma.project_scope import ProjectScopeStore
from soma.reasoning.codex_g6_backend import (
    CODEX_G6_MODEL,
    CodexG6ReasoningBackend,
    default_codex_g6_client_factory,
    default_codex_g6_preflight,
    execution_contract_hash,
    make_g6_reasoning_spec,
)
from soma.reasoning.store import ReasoningBackendStore
from soma.tasks.manager import TaskManager
from soma.tasks.store import TaskStore


G6_REAL_COMPANY_ID = "company_" + "c" * 24
G6_REAL_MISSION_ID = "mission_" + "d" * 24
G6_REAL_PROJECT_ID = "Project_G6_Real_Benchmark"
G6_REAL_RESOURCE_ID = "Resource_G6_Real_Benchmark"
G6_REAL_OWNER = "owner-controller:g6-real-benchmark"
G6_REAL_CREATED_AT = "2026-08-13T00:00:00+00:00"
G6_QUOTA_SCHEMA = "soma.agent_worker_benchmark.provider_quota.v1"
G6_SMOKE_SCHEMA = "soma.agent_worker_benchmark.provider_smoke.v1"


class G6RuntimeError(RuntimeError):
    """The real G6 runtime cannot preserve identity, isolation, or quota."""


@dataclass(frozen=True)
class G6Runtime:
    repo_root: Path
    repo_name: str
    runs_dir: Path
    config: AppConfig
    task_store: TaskStore
    scope_store: ProjectScopeStore
    kernel_store: CompanyKernelStore
    reasoning_store: ReasoningBackendStore
    reasoning_backend: CodexG6ReasoningBackend
    task_manager: TaskManager


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _ensure_company_and_mission(kernel: CompanyKernelStore) -> None:
    mission_contract = {
        "purpose": "run the frozen G6 real-provider canonical concurrency benchmark"
    }
    with kernel.connect() as conn:
        company = conn.execute(
            "SELECT * FROM companies WHERE company_id = ?", (G6_REAL_COMPANY_ID,)
        ).fetchone()
        if company is None:
            conn.execute(
                "INSERT INTO companies(company_id, company_key, display_name, "
                "executive_authority_ref, creation_request_id, creation_request_hash, created_at) "
                "VALUES (?, 'g6-real-company', 'G6 Real Benchmark Company', ?, ?, ?, ?)",
                (
                    G6_REAL_COMPANY_ID,
                    G6_REAL_OWNER,
                    "g6-real-company-create",
                    _sha256_text("g6-real-company-create"),
                    G6_REAL_CREATED_AT,
                ),
            )
        elif str(company["executive_authority_ref"]) != G6_REAL_OWNER:
            raise G6RuntimeError("existing G6 benchmark Company authority drifted")

        mission = conn.execute(
            "SELECT * FROM missions WHERE mission_id = ?", (G6_REAL_MISSION_ID,)
        ).fetchone()
        if mission is None:
            conn.execute(
                """
                INSERT INTO missions(
                    mission_id, company_id, mission_key, project_id, resource_id,
                    scope_generation, mission_contract_json, mission_contract_hash,
                    accountable_owner_ref, acceptance_authority_ref,
                    current_plan_revision_id, plan_state_version, kernel_state_version,
                    creation_request_id, creation_request_hash, created_at, updated_at
                ) VALUES (?, ?, 'g6-real-mission', ?, ?, 1, ?, ?, ?, ?, NULL, 0, 0, ?, ?, ?, ?)
                """,
                (
                    G6_REAL_MISSION_ID,
                    G6_REAL_COMPANY_ID,
                    G6_REAL_PROJECT_ID,
                    G6_REAL_RESOURCE_ID,
                    canonical_json(mission_contract),
                    canonical_hash(MISSION_ID_DOMAIN, mission_contract),
                    G6_REAL_OWNER,
                    G6_REAL_OWNER,
                    "g6-real-mission-create",
                    _sha256_text("g6-real-mission-create"),
                    G6_REAL_CREATED_AT,
                    G6_REAL_CREATED_AT,
                ),
            )
        else:
            durable = (
                str(mission["company_id"]),
                str(mission["project_id"]),
                str(mission["resource_id"]),
                int(mission["scope_generation"]),
                str(mission["accountable_owner_ref"]),
                str(mission["acceptance_authority_ref"]),
            )
            expected = (
                G6_REAL_COMPANY_ID,
                G6_REAL_PROJECT_ID,
                G6_REAL_RESOURCE_ID,
                1,
                G6_REAL_OWNER,
                G6_REAL_OWNER,
            )
            if durable != expected:
                raise G6RuntimeError("existing G6 benchmark Mission identity drifted")
        conn.commit()


def _cached_preflight(
    factory: Callable[[], Mapping[str, Any]],
) -> Callable[[], Mapping[str, Any]]:
    lock = threading.Lock()
    cached: dict[str, Any] | None = None

    def check() -> Mapping[str, Any]:
        nonlocal cached
        with lock:
            if cached is None:
                cached = dict(factory())
            return dict(cached)

    return check


def prepare_g6_runtime(
    *,
    repo_root: Path,
    base_config: AppConfig,
    config_path: Path | None,
    repo_name: str = "soma",
    runtime_root: Path | None = None,
    client_factory=None,
    preflight=None,
) -> G6Runtime:
    """Create or reopen the isolated durable canonical G6 runtime."""

    root = Path(repo_root).resolve()
    if repo_name not in base_config.repos:
        raise G6RuntimeError(f"repository {repo_name!r} is absent from configuration")
    configured_root = Path(base_config.repos[repo_name].path).resolve()
    if configured_root != root:
        raise G6RuntimeError("configured G6 repository root does not match repo_root")

    runs_dir = Path(
        runtime_root or (root / "runs" / "agent_worker_benchmark" / "runtime")
    ).resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    config = base_config.model_copy(update={"runs_dir": str(runs_dir)})

    task_store = TaskStore(runs_dir)
    scope = ProjectScopeStore(runs_dir)
    scope.init_db()
    scope.apply_bootstrap(
        project_id=G6_REAL_PROJECT_ID,
        project_key="g6-real-benchmark",
        resource_id=G6_REAL_RESOURCE_ID,
        repo_name=repo_name,
        repository_root=root,
        access_mode="exclusive",
    )
    scope.set_scoped_writes_enabled(True)

    kernel = CompanyKernelStore(runs_dir)
    kernel.init_db()
    _ensure_company_and_mission(kernel)
    graph = build_g6_plan_graph_manifest(
        root,
        mission_id=G6_REAL_MISSION_ID,
        project_id=G6_REAL_PROJECT_ID,
        resource_id=G6_REAL_RESOURCE_ID,
        scope_generation=1,
    )
    accept_plan_graph(
        kernel,
        company_id=G6_REAL_COMPANY_ID,
        mission_id=G6_REAL_MISSION_ID,
        expected_current_plan_revision_id=None,
        expected_plan_state_version=0,
        expected_kernel_state_version=0,
        project_id=G6_REAL_PROJECT_ID,
        resource_id=G6_REAL_RESOURCE_ID,
        scope_generation=1,
        controller_request_id="g6-real-graph-accept",
        accepted_by_ref=G6_REAL_OWNER,
        acceptance_basis_ref="owner-authorized frozen G6 benchmark",
        plan_contract_base={"purpose": "run frozen G6 real-provider benchmark"},
        graph_manifest=graph,
        work_package_contracts=work_package_contract_materials(root),
        accepted_at=G6_REAL_CREATED_AT,
    )

    reasoning_store = ReasoningBackendStore(runs_dir)
    from soma.agent_worker_benchmark_runner import (
        make_g6_assignment_resolver,
        make_g6_task_id_resolver,
    )

    effective_client_factory = client_factory or default_codex_g6_client_factory(root)
    effective_preflight = preflight or default_codex_g6_preflight(root)
    backend = CodexG6ReasoningBackend(
        reasoning_store,
        assignment_resolver=make_g6_assignment_resolver(kernel, root),
        task_id_resolver=make_g6_task_id_resolver(task_store),
        client_factory=effective_client_factory,
        preflight=_cached_preflight(effective_preflight),
        working_directory=root,
    )
    manager = TaskManager(
        config,
        config_path,
        reasoning_backend=backend,
        store=task_store,
        scope_store=scope,
    )
    return G6Runtime(
        repo_root=root,
        repo_name=repo_name,
        runs_dir=runs_dir,
        config=config,
        task_store=task_store,
        scope_store=scope,
        kernel_store=kernel,
        reasoning_store=reasoning_store,
        reasoning_backend=backend,
        task_manager=manager,
    )


def provider_send_boundaries_crossed(runtime: G6Runtime) -> int:
    """Conservatively count starts that crossed the durable provider send boundary."""

    db_path = runtime.runs_dir / "soma.sqlite3"
    with sqlite3.connect(db_path) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM reasoning_backend_start_attempts "
                "WHERE disposition IN ('outcome_unknown', 'accepted_bound', 'rejected')"
            ).fetchone()[0]
        )


def provider_model_generations_observed(runtime: G6Runtime) -> int:
    """Count durable evidence that a provider request actually reached generation."""

    db_path = runtime.runs_dir / "soma.sqlite3"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT backend_ref, provider_operation_ref FROM reasoning_backend_runs"
        ).fetchall()
    observed = 0
    for backend_ref, operation_ref in rows:
        marker = (
            runtime.runs_dir
            / "reasoning_backend_evidence"
            / str(backend_ref)
            / "model_generation_observed.json"
        )
        if not marker.exists():
            continue
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise G6RuntimeError(
                f"invalid durable generation marker for {backend_ref}"
            ) from exc
        if value.get(
            "schema"
        ) != "soma.reasoning.codex_g6.model_generation_observed.v1" or value.get(
            "provider_operation_ref"
        ) != str(operation_ref):
            raise G6RuntimeError(
                f"generation marker identity mismatch for {backend_ref}"
            )
        observed += 1
    return observed


def ensure_model_turn_ceiling(runtime: G6Runtime, ceiling: int) -> dict[str, Any]:
    """Freeze one durable G6 quota ceiling; changing it requires a new explicit act."""

    if ceiling < 1:
        raise G6RuntimeError("model-turn ceiling must be positive")
    path = runtime.runs_dir / "provider_quota.json"
    used = provider_send_boundaries_crossed(runtime)
    expected = {
        "schema_version": G6_QUOTA_SCHEMA,
        "provider_route": "codex_app_server_chatgpt",
        "model": CODEX_G6_MODEL,
        "model_turn_ceiling": int(ceiling),
    }
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != expected:
            raise G6RuntimeError(
                "durable G6 model-turn ceiling differs from requested ceiling"
            )
    else:
        if used > ceiling:
            raise G6RuntimeError(
                "observed provider sends already exceed requested ceiling"
            )
        _atomic_json(path, expected)
    return {
        **expected,
        "provider_send_boundaries_crossed": used,
        "model_generations_observed": provider_model_generations_observed(runtime),
    }


def extend_model_turn_ceiling(
    runtime: G6Runtime,
    *,
    expected_ceiling: int,
    new_ceiling: int,
) -> dict[str, Any]:
    """Explicitly and monotonically extend the durable G6 model-generation ceiling."""

    if new_ceiling <= expected_ceiling:
        raise G6RuntimeError("new model-turn ceiling must exceed expected ceiling")
    path = runtime.runs_dir / "provider_quota.json"
    if not path.exists():
        raise G6RuntimeError("durable G6 model-turn ceiling does not exist")
    existing = json.loads(path.read_text(encoding="utf-8"))
    expected_existing = {
        "schema_version": G6_QUOTA_SCHEMA,
        "provider_route": "codex_app_server_chatgpt",
        "model": CODEX_G6_MODEL,
        "model_turn_ceiling": int(expected_ceiling),
    }
    if existing != expected_existing:
        raise G6RuntimeError(
            "durable G6 model-turn ceiling does not match explicitly expected ceiling"
        )
    generated = provider_model_generations_observed(runtime)
    if generated > new_ceiling:
        raise G6RuntimeError("observed model generations already exceed new ceiling")
    updated = {**expected_existing, "model_turn_ceiling": int(new_ceiling)}
    _atomic_json(path, updated)
    return ensure_model_turn_ceiling(runtime, new_ceiling)


def _smoke_identity(
    runtime: G6Runtime, unit_id: str
) -> tuple[str, str, dict[str, Any]]:
    if unit_id not in G6_EXPECTED_UNIT_IDS:
        raise G6RuntimeError(f"unknown G6 smoke unit {unit_id!r}")
    context = validate_g6_plan(
        runtime.kernel_store, runtime.repo_root, G6_REAL_MISSION_ID
    )
    descriptor = {
        "schema_version": G6_SMOKE_SCHEMA,
        "purpose": "qualify one real provider execution contract before benchmark screening",
        "unit_id": unit_id,
        "mission_id": context.mission_id,
        "plan_revision_id": context.plan_revision_id,
        "work_package_id": context.work_packages[unit_id],
        "assignment_packet_sha256": assignment_packet_hash(runtime.repo_root, unit_id),
        "provider_execution_contract_hash": execution_contract_hash(),
    }
    payload = json.dumps(
        descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"g6smoke_{digest[:24]}", digest, descriptor


def run_real_g6_smoke(
    runtime: G6Runtime,
    *,
    unit_id: str,
    model_turn_ceiling: int,
) -> dict[str, Any]:
    """Run/replay one canonical unit solely to qualify the current provider contract."""

    quota = ensure_model_turn_ceiling(runtime, model_turn_ceiling)
    generated = int(quota["model_generations_observed"])
    if generated + 1 > model_turn_ceiling:
        raise G6RuntimeError(
            "G6 model-generation ceiling would be exceeded by smoke: "
            f"generated={generated}, worst_case_new=1, ceiling={model_turn_ceiling}"
        )

    smoke_id, manifest_hash, descriptor = _smoke_identity(runtime, unit_id)
    directory = runtime.runs_dir / "agent_worker_benchmark_smokes" / smoke_id
    manifest_path = directory / "manifest.json"
    result_path = directory / "result.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != descriptor:
            raise G6RuntimeError("stored G6 smoke manifest identity drifted")
    else:
        _atomic_json(manifest_path, descriptor)
    if result_path.exists():
        stored = json.loads(result_path.read_text(encoding="utf-8"))
        if stored.get("smoke_manifest_hash") != manifest_hash:
            raise G6RuntimeError("stored G6 smoke result manifest identity drifted")
        return {**stored, "replayed_stored_result": True}

    context = validate_g6_plan(
        runtime.kernel_store, runtime.repo_root, G6_REAL_MISSION_ID
    )
    prepared = prepare_g6_unit_admission(
        runtime.kernel_store,
        context,
        smoke_id,
        unit_id,
    )
    packet_hash = assignment_packet_hash(runtime.repo_root, unit_id)
    spec = make_g6_reasoning_spec(
        assignment_ref=f"benchmark-packet:{unit_id}",
        assignment_hash=packet_hash,
    )
    request = AdmissionRequestV1(
        mission_id=context.mission_id,
        work_package_id=prepared.work_package_id,
        controller_request_id=prepared.controller_request_id,
        repo_name=runtime.repo_name,
        reasoning_spec=spec,
        expected_plan_revision_id=context.plan_revision_id,
        expected_plan_state_version=context.plan_state_version,
        supersedes_attempt_id=prepared.supersedes_attempt_id,
    )
    admission = admit_reasoning_work_package(runtime.task_manager, request)
    task = runtime.task_store.get_task(admission.task_id)
    observation = runtime.reasoning_store.query(task.backend_ref)
    submission = runtime.reasoning_backend.load_evidence_submission(task.backend_ref)
    assessment = runtime.reasoning_backend.load_benchmark_assessment(task.backend_ref)
    output = {
        "schema_version": G6_SMOKE_SCHEMA,
        "smoke_id": smoke_id,
        "smoke_manifest_hash": manifest_hash,
        "unit_id": unit_id,
        "provider_execution_contract_hash": execution_contract_hash(),
        "work_package_id": prepared.work_package_id,
        "supersedes_attempt_id": prepared.supersedes_attempt_id,
        "attempt_id": admission.attempt_id,
        "task_id": admission.task_id,
        "backend_ref": task.backend_ref,
        "task_state": task.state.value,
        "created": admission.created,
        "provider_operation_ref": observation.provider_operation_ref or "",
        "provider_status_raw": observation.provider_status_raw or "",
        "provider_terminal_claim": observation.provider_terminal_claim,
        "output_contract_disposition": observation.output_contract_disposition,
        "error_code": observation.error_code or "",
        "raw_provider_evidence_root_ref": observation.raw_provider_evidence_root_ref
        or "",
        "raw_provider_evidence_root_hash": observation.raw_provider_evidence_root_hash
        or "",
        "submission_present": submission is not None,
        "assessment_present": assessment is not None,
        "success": (
            task.state.value == "completed"
            and observation.output_contract_disposition == "valid"
            and submission is not None
            and assessment is not None
        ),
        "provider_send_boundaries_crossed": provider_send_boundaries_crossed(runtime),
        "model_generations_observed": provider_model_generations_observed(runtime),
        "replayed_stored_result": False,
    }
    _atomic_json(result_path, output)
    return output


def run_real_g6_trial(
    runtime: G6Runtime,
    *,
    phase: str,
    concurrency: int,
    repetition: int,
    model_turn_ceiling: int,
) -> G6TrialResultV1:
    """Run one real trial only when eight worst-case new sends fit the frozen ceiling."""

    quota = ensure_model_turn_ceiling(runtime, model_turn_ceiling)
    generated = int(quota["model_generations_observed"])
    if generated + 8 > model_turn_ceiling:
        raise G6RuntimeError(
            "G6 model-generation ceiling would be exceeded: "
            f"generated={generated}, worst_case_new=8, ceiling={model_turn_ceiling}"
        )
    return run_g6_trial(
        task_manager=runtime.task_manager,
        kernel_store=runtime.kernel_store,
        repo_root=runtime.repo_root,
        mission_id=G6_REAL_MISSION_ID,
        repo_name=runtime.repo_name,
        phase=phase,
        canonical_concurrency_limit=concurrency,
        repetition_index=repetition,
        submission_loader=runtime.reasoning_backend.load_evidence_submission,
        assessment_loader=runtime.reasoning_backend.load_benchmark_assessment,
    )
