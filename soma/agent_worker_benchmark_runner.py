"""Durable G6 canonical-concurrency benchmark trial runner.

The runner varies only Soma-level canonical WorkPackage/Task concurrency. Frozen
WorkPackage contracts and assignment packets stay unchanged across C1/C2/C4/C8.
Each new benchmark observation creates successor WorkPackageAttempts; exact
replay of one already-completed trial returns its immutable stored measurement
and never launches provider work again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final, Mapping

from pydantic import BaseModel, ConfigDict, Field

from soma.company_kernel import canonical_json
from soma.company_kernel.admission import (
    AdmissionError,
    AdmissionRequestV1,
    admit_reasoning_work_package,
)
from soma.company_kernel.models import work_package_contract_hash
from soma.company_kernel.store import CompanyKernelStore
from soma.reasoning.codex_g6_backend import (
    ResolvedG6Assignment,
    make_g6_reasoning_spec,
)
from soma.tasks.models import TaskState
from soma.worker_evidence.fanin import FanInV1, synthesize_fanin
from soma.worker_evidence.models import EvidenceSubmissionV1

from .agent_worker_benchmark import (
    EXPECTED_TRAP_DISPOSITIONS,
    FROZEN_RESEARCH_CORPUS_HASH,
    SOURCE_COMMIT,
    UNITS,
    assignment_packet_hash,
    build_assignment_packet,
    build_g6_plan_graph_manifest,
    build_work_package_contract,
    materialization_manifest_hash,
    work_package_contract_materials,
)


G6_TRIAL_MANIFEST_SCHEMA: Final[str] = "soma.agent_worker_benchmark.trial.v1"
G6_TRIAL_RESULT_SCHEMA: Final[str] = "soma.agent_worker_benchmark.trial_result.v1"
G6_TRIAL_METRICS_SCHEMA: Final[str] = "soma.agent_worker_benchmark.metrics.v1"
G6_ALLOWED_CONCURRENCY: Final[frozenset[int]] = frozenset({1, 2, 4, 8})
G6_ALLOWED_PHASES: Final[frozenset[str]] = frozenset({"screening", "confirmation"})
G6_EXPECTED_UNIT_IDS: Final[tuple[str, ...]] = tuple(unit.unit_id for unit in UNITS)
_TRIAL_COMPONENT_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


class G6BenchmarkRunnerError(RuntimeError):
    """G6 trial identity, graph, replay, or evidence cannot be trusted."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class G6UnitTrialResultV1(_FrozenModel):
    unit_id: str
    work_package_id: str
    controller_request_id: str
    supersedes_attempt_id: str | None = None
    attempt_id: str = ""
    task_id: str = ""
    backend_ref: str = ""
    task_state: str = ""
    created: bool = False
    latency_seconds: float = Field(ge=0)
    submission_present: bool = False
    assessment_present: bool = False
    error: str = ""


class G6MechanicalMetricsV1(_FrozenModel):
    schema_version: str = G6_TRIAL_METRICS_SCHEMA
    expected_units: int
    collected_submissions: int
    schema_valid_submission_rate: float = Field(ge=0, le=1)
    required_fact_keys: int
    covered_required_fact_keys: int
    required_fact_key_recall: float = Field(ge=0, le=1)
    evidence_reference_validity_rate: float = Field(ge=0, le=1)
    claims: int
    claims_without_support: int
    claims_without_support_rate: float = Field(ge=0, le=1)
    critical_trap_failures: int
    missing_units: int
    partial_units: int
    blocked_units: int
    uncertain_units: int
    fanin_structured_conflicts: int
    fanin_unresolved_uncertainties: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: str
    aggregate_submission_bytes: int
    fanin_response_bytes: int
    task_backend_starts: int
    automatic_retry_count: int
    deliberate_trial_repetition: bool
    fact_key_correctness: None = None
    evidence_precision: None = None
    unsupported_assertion_rate: None = None
    semantic_adjudication_required: bool = True


class G6TrialResultV1(_FrozenModel):
    schema_version: str = G6_TRIAL_RESULT_SCHEMA
    trial_id: str
    trial_manifest_hash: str
    phase: str
    condition: str
    canonical_concurrency_limit: int
    repetition_index: int
    mission_id: str
    plan_revision_id: str
    makespan_seconds: float = Field(ge=0)
    peak_active_canonical_tasks: int = Field(ge=0)
    unit_results: tuple[G6UnitTrialResultV1, ...]
    fanin_ref: str
    fanin_hash: str
    metrics: G6MechanicalMetricsV1
    replayed_stored_result: bool = False


@dataclass(frozen=True)
class G6PlanContext:
    mission_id: str
    plan_revision_id: str
    plan_state_version: int
    project_id: str
    resource_id: str
    scope_generation: int
    work_packages: Mapping[str, str]


SubmissionLoader = Callable[[str], EvidenceSubmissionV1 | None]
AssessmentLoader = Callable[[str], Mapping[str, Any] | None]


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _safe_trial_component(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not _TRIAL_COMPONENT_RE.fullmatch(normalized):
        raise G6BenchmarkRunnerError(
            f"{field_name} must match {_TRIAL_COMPONENT_RE.pattern!r}"
        )
    return normalized


def _condition_name(limit: int) -> str:
    if limit not in G6_ALLOWED_CONCURRENCY:
        raise G6BenchmarkRunnerError("G6 concurrency must be one of 1, 2, 4, 8")
    return f"C{limit}"


def validate_g6_plan(
    kernel_store: CompanyKernelStore,
    repo_root: Path,
    mission_id: str,
) -> G6PlanContext:
    """Validate one current accepted PlanRevision as the exact frozen eight-unit graph."""

    root = Path(repo_root).resolve()
    materials = work_package_contract_materials(root)
    with kernel_store.connect() as conn:
        mission = conn.execute(
            "SELECT * FROM missions WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        if mission is None:
            raise G6BenchmarkRunnerError("G6 Mission does not exist")
        plan_revision_id = str(mission["current_plan_revision_id"] or "")
        if not plan_revision_id:
            raise G6BenchmarkRunnerError("G6 Mission has no current PlanRevision")
        rows = conn.execute(
            "SELECT * FROM work_packages WHERE mission_id = ? AND plan_revision_id = ? "
            "ORDER BY package_key",
            (mission_id, plan_revision_id),
        ).fetchall()
        if [str(row["package_key"]) for row in rows] != list(G6_EXPECTED_UNIT_IDS):
            raise G6BenchmarkRunnerError(
                "current PlanRevision is not the exact B01-B08 benchmark graph"
            )
        edge_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM work_package_dependencies "
                "WHERE mission_id = ? AND plan_revision_id = ?",
                (mission_id, plan_revision_id),
            ).fetchone()[0]
        )
        if edge_count != 0:
            raise G6BenchmarkRunnerError("G6 benchmark graph must have zero dependency edges")
        graph_row = conn.execute(
            "SELECT * FROM plan_graph_manifests WHERE mission_id = ? AND plan_revision_id = ?",
            (mission_id, plan_revision_id),
        ).fetchone()
        if graph_row is None or int(graph_row["package_count"]) != 8 or int(
            graph_row["edge_count"]
        ) != 0:
            raise G6BenchmarkRunnerError("G6 plan graph manifest shape is not 8/0")

        package_ids: dict[str, str] = {}
        for row in rows:
            unit_id = str(row["package_key"])
            material = materials[unit_id]
            expected_contract = build_work_package_contract(root, unit_id)
            try:
                actual_contract = json.loads(str(row["contract_json"]))
            except json.JSONDecodeError as exc:
                raise G6BenchmarkRunnerError(
                    f"G6 WorkPackage {unit_id} contract is not JSON"
                ) from exc
            expected_hash = work_package_contract_hash(
                contract_version=material.contract_version,
                contract=expected_contract,
            )
            if (
                str(row["contract_version"]) != material.contract_version
                or actual_contract != expected_contract
                or str(row["contract_hash"]) != expected_hash
            ):
                raise G6BenchmarkRunnerError(
                    f"G6 WorkPackage {unit_id} contract drift detected"
                )
            package_ids[unit_id] = str(row["work_package_id"])

        expected_manifest = build_g6_plan_graph_manifest(
            root,
            mission_id=mission_id,
            project_id=str(mission["project_id"]),
            resource_id=str(mission["resource_id"]),
            scope_generation=int(mission["scope_generation"]),
        )
        if str(graph_row["manifest_hash"]) != expected_manifest.graph_manifest_hash:
            raise G6BenchmarkRunnerError("G6 graph manifest hash does not match frozen graph")

    return G6PlanContext(
        mission_id=mission_id,
        plan_revision_id=plan_revision_id,
        plan_state_version=int(mission["plan_state_version"]),
        project_id=str(mission["project_id"]),
        resource_id=str(mission["resource_id"]),
        scope_generation=int(mission["scope_generation"]),
        work_packages=package_ids,
    )


def make_g6_assignment_resolver(
    kernel_store: CompanyKernelStore,
    repo_root: Path,
) -> Callable[[str], ResolvedG6Assignment]:
    """Resolve only exact frozen current WorkPackage contracts into packet bytes."""

    root = Path(repo_root).resolve()

    def resolve(assignment_ref: str) -> ResolvedG6Assignment:
        prefix = "work-package:"
        if not assignment_ref.startswith(prefix):
            raise G6BenchmarkRunnerError("G6 assignment ref is not a WorkPackage ref")
        work_package_id = assignment_ref[len(prefix) :]
        with kernel_store.connect() as conn:
            row = conn.execute(
                "SELECT package.*, mission.current_plan_revision_id "
                "FROM work_packages package JOIN missions mission "
                "ON mission.mission_id = package.mission_id "
                "WHERE package.work_package_id = ?",
                (work_package_id,),
            ).fetchone()
        if row is None:
            raise G6BenchmarkRunnerError("G6 WorkPackage assignment does not exist")
        if str(row["plan_revision_id"]) != str(row["current_plan_revision_id"]):
            raise G6BenchmarkRunnerError("G6 WorkPackage assignment is not in current plan")
        unit_id = str(row["package_key"])
        if unit_id not in G6_EXPECTED_UNIT_IDS:
            raise G6BenchmarkRunnerError("G6 WorkPackage package_key is not B01-B08")
        expected_contract = build_work_package_contract(root, unit_id)
        actual_contract = json.loads(str(row["contract_json"]))
        expected_hash = work_package_contract_hash(
            contract_version=str(row["contract_version"]),
            contract=expected_contract,
        )
        if actual_contract != expected_contract or str(row["contract_hash"]) != expected_hash:
            raise G6BenchmarkRunnerError("G6 WorkPackage contract identity drift detected")
        packet = build_assignment_packet(root, unit_id)
        if assignment_packet_hash(root, unit_id) != expected_contract["benchmark"][
            "assignment_packet_sha256"
        ]:
            raise G6BenchmarkRunnerError("G6 packet hash drift detected")
        return ResolvedG6Assignment(
            packet_bytes=packet,
            assignment_hash=str(row["contract_hash"]),
            unit_id=unit_id,
        )

    return resolve


def make_g6_task_id_resolver(task_store) -> Callable[[str], str]:
    def resolve(backend_ref: str) -> str:
        task = task_store.find_by_backend_ref("soma_reasoning", backend_ref)
        return task.task_id if task is not None else ""

    return resolve


def _trial_descriptor(
    *,
    context: G6PlanContext,
    phase: str,
    concurrency_limit: int,
    repetition_index: int,
    repo_root: Path,
) -> dict[str, Any]:
    if phase not in G6_ALLOWED_PHASES:
        raise G6BenchmarkRunnerError(
            f"phase must be one of {sorted(G6_ALLOWED_PHASES)}"
        )
    if repetition_index < 1 or repetition_index > 99:
        raise G6BenchmarkRunnerError("repetition_index must be within 1..99")
    condition = _condition_name(concurrency_limit)
    root = Path(repo_root).resolve()
    return {
        "schema_version": G6_TRIAL_MANIFEST_SCHEMA,
        "phase": phase,
        "condition": condition,
        "canonical_concurrency_limit": concurrency_limit,
        "repetition_index": repetition_index,
        "mission_id": context.mission_id,
        "plan_revision_id": context.plan_revision_id,
        "source_commit": SOURCE_COMMIT,
        "frozen_research_corpus_hash": FROZEN_RESEARCH_CORPUS_HASH,
        "materialization_manifest_hash": materialization_manifest_hash(),
        "units": [
            {
                "unit_id": unit.unit_id,
                "work_package_id": context.work_packages[unit.unit_id],
                "assignment_packet_sha256": assignment_packet_hash(root, unit.unit_id),
            }
            for unit in UNITS
        ],
        "fixed_controls": {
            "provider_internal_concurrency_limit": 1,
            "mutation_policy": "read_only",
            "continuation_policy": "none",
            "evidence_contract": "evidence_submission.v1",
            "fanin_contract": "fanin.v1",
        },
    }


def _trial_identity(descriptor: Mapping[str, Any]) -> tuple[str, str]:
    payload = _json_bytes(descriptor)
    digest = _sha256(payload)
    return f"g6trial_{digest[:24]}", digest


class G6TrialStore:
    def __init__(self, runs_dir: Path) -> None:
        self.root = Path(runs_dir) / "agent_worker_benchmark_trials"

    def _directory(self, trial_id: str) -> Path:
        _safe_trial_component(trial_id, "trial_id")
        return self.root / trial_id

    def prepare(self, descriptor: Mapping[str, Any]) -> tuple[str, str]:
        trial_id, manifest_hash = _trial_identity(descriptor)
        directory = self._directory(trial_id)
        path = directory / "manifest.json"
        payload = _json_bytes(descriptor)
        if path.exists():
            existing = path.read_bytes()
            if _sha256(existing) != manifest_hash or existing != payload:
                raise G6BenchmarkRunnerError(
                    "existing G6 trial manifest does not match requested descriptor"
                )
            return trial_id, manifest_hash
        directory.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, payload)
        return trial_id, manifest_hash

    def load_result(self, trial_id: str) -> G6TrialResultV1 | None:
        path = self._directory(trial_id) / "result.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise G6BenchmarkRunnerError("stored G6 trial result is unreadable") from exc
        return G6TrialResultV1.model_validate(value)

    def write_fanin(self, trial_id: str, fanin: FanInV1) -> tuple[str, str]:
        payload = _json_bytes(fanin.model_dump(mode="json"))
        digest = _sha256(payload)
        path = self._directory(trial_id) / "fanin.json"
        _atomic_write(path, payload)
        return f"g6-trial:{trial_id}:fanin", digest

    def write_result(self, result: G6TrialResultV1) -> None:
        _atomic_write(
            self._directory(result.trial_id) / "result.json",
            _json_bytes(result.model_dump(mode="json")),
        )


@dataclass(frozen=True)
class _AdmissionPreparation:
    unit_id: str
    work_package_id: str
    controller_request_id: str
    supersedes_attempt_id: str | None


def _controller_request_id(trial_id: str, unit_id: str) -> str:
    digest = _sha256(f"{trial_id}\0{unit_id}".encode("utf-8"))
    return f"g6:{unit_id}:{digest[:32]}"


def _prepare_admissions(
    kernel_store: CompanyKernelStore,
    context: G6PlanContext,
    trial_id: str,
) -> tuple[_AdmissionPreparation, ...]:
    prepared: list[_AdmissionPreparation] = []
    with kernel_store.connect() as conn:
        for unit_id in G6_EXPECTED_UNIT_IDS:
            work_package_id = context.work_packages[unit_id]
            controller_request_id = _controller_request_id(trial_id, unit_id)
            existing = conn.execute(
                "SELECT attempt.*, task.state AS task_state "
                "FROM work_package_attempts attempt JOIN tasks task "
                "ON task.task_id = attempt.task_id "
                "WHERE attempt.controller_request_id = ?",
                (controller_request_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["work_package_id"]) != work_package_id:
                    raise G6BenchmarkRunnerError(
                        "G6 controller request is already bound to another WorkPackage"
                    )
                prepared.append(
                    _AdmissionPreparation(
                        unit_id=unit_id,
                        work_package_id=work_package_id,
                        controller_request_id=controller_request_id,
                        supersedes_attempt_id=(
                            str(existing["supersedes_attempt_id"])
                            if existing["supersedes_attempt_id"] is not None
                            else None
                        ),
                    )
                )
                continue

            rows = conn.execute(
                "SELECT attempt.*, task.state AS task_state "
                "FROM work_package_attempts attempt JOIN tasks task "
                "ON task.task_id = attempt.task_id "
                "WHERE attempt.work_package_id = ? ORDER BY attempt.created_at, attempt.attempt_id",
                (work_package_id,),
            ).fetchall()
            if not rows:
                supersedes = None
            else:
                active = [
                    row
                    for row in rows
                    if str(row["task_state"]) not in {
                        TaskState.COMPLETED.value,
                        TaskState.FAILED.value,
                        TaskState.CANCELLED.value,
                    }
                    and not str(row["containment_evidence_ref"] or "")
                ]
                if active:
                    raise G6BenchmarkRunnerError(
                        f"G6 unit {unit_id} has an active or uncontained prior Attempt"
                    )
                attempt_ids = {str(row["attempt_id"]) for row in rows}
                superseded = {
                    str(row["supersedes_attempt_id"])
                    for row in rows
                    if row["supersedes_attempt_id"] is not None
                }
                heads = sorted(attempt_ids - superseded)
                if len(heads) != 1:
                    raise G6BenchmarkRunnerError(
                        f"G6 unit {unit_id} does not have exactly one Attempt head"
                    )
                supersedes = heads[0]
            prepared.append(
                _AdmissionPreparation(
                    unit_id=unit_id,
                    work_package_id=work_package_id,
                    controller_request_id=controller_request_id,
                    supersedes_attempt_id=supersedes,
                )
            )
    return tuple(prepared)


class _CanonicalActivityCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)

    def exit(self) -> None:
        with self._lock:
            self.active -= 1
            if self.active < 0:  # pragma: no cover - defensive invariant
                raise RuntimeError("G6 canonical activity counter underflow")


def _mechanical_metrics(
    *,
    fanin: FanInV1,
    assessments: Mapping[str, Mapping[str, Any]],
    unit_results: tuple[G6UnitTrialResultV1, ...],
    deliberate_trial_repetition: bool,
) -> G6MechanicalMetricsV1:
    required = sum(len(unit.questions) for unit in UNITS)
    covered = 0
    trap_failures = 0
    claims = 0
    claims_without_support = 0
    for unit in UNITS:
        assessment = assessments.get(unit.unit_id)
        if assessment is None:
            continue
        claim_keys = {
            str(value) for value in (assessment.get("claim_fact_keys") or [])
        }
        required_keys = {question.fact_key for question in unit.questions}
        covered += len(claim_keys & required_keys)
        claims += int(assessment.get("claim_count") or 0)
        claims_without_support += int(assessment.get("claims_without_support") or 0)
        critical = assessment.get("critical_trap")
        disposition = (
            str(critical.get("disposition") or "")
            if isinstance(critical, Mapping)
            else ""
        )
        if disposition not in EXPECTED_TRAP_DISPOSITIONS[unit.unit_id]:
            trap_failures += 1

    expected_units = len(UNITS)
    collected = fanin.exact_counts.collected_units
    return G6MechanicalMetricsV1(
        expected_units=expected_units,
        collected_submissions=collected,
        schema_valid_submission_rate=collected / expected_units,
        required_fact_keys=required,
        covered_required_fact_keys=covered,
        required_fact_key_recall=covered / required,
        evidence_reference_validity_rate=collected / expected_units,
        claims=claims,
        claims_without_support=claims_without_support,
        claims_without_support_rate=(
            claims_without_support / claims if claims else 0.0
        ),
        critical_trap_failures=trap_failures,
        missing_units=fanin.exact_counts.missing_units,
        partial_units=fanin.exact_counts.partial_units,
        blocked_units=fanin.exact_counts.blocked_units,
        uncertain_units=fanin.exact_counts.uncertain_units,
        fanin_structured_conflicts=fanin.exact_counts.structured_conflicts,
        fanin_unresolved_uncertainties=fanin.exact_counts.unresolved_uncertainties,
        total_input_tokens=fanin.aggregate_usage.input_tokens,
        total_output_tokens=fanin.aggregate_usage.output_tokens,
        total_cost_usd=str(fanin.aggregate_usage.cost_usd),
        aggregate_submission_bytes=fanin.aggregate_usage.submission_bytes,
        fanin_response_bytes=fanin.response_bytes,
        task_backend_starts=sum(1 for item in unit_results if item.created),
        automatic_retry_count=0,
        deliberate_trial_repetition=deliberate_trial_repetition,
    )


def run_g6_trial(
    *,
    task_manager,
    kernel_store: CompanyKernelStore,
    repo_root: Path,
    mission_id: str,
    repo_name: str,
    phase: str,
    canonical_concurrency_limit: int,
    repetition_index: int,
    submission_loader: SubmissionLoader,
    assessment_loader: AssessmentLoader,
    trial_store: G6TrialStore | None = None,
) -> G6TrialResultV1:
    """Execute/replay one frozen G6 condition trial over canonical admissions."""

    context = validate_g6_plan(kernel_store, repo_root, mission_id)
    descriptor = _trial_descriptor(
        context=context,
        phase=phase,
        concurrency_limit=canonical_concurrency_limit,
        repetition_index=repetition_index,
        repo_root=repo_root,
    )
    store = trial_store or G6TrialStore(task_manager.store.runs_dir)
    trial_id, manifest_hash = store.prepare(descriptor)
    stored = store.load_result(trial_id)
    if stored is not None:
        if stored.trial_manifest_hash != manifest_hash:
            raise G6BenchmarkRunnerError("stored G6 result manifest identity mismatch")
        return stored.model_copy(update={"replayed_stored_result": True})

    admissions = _prepare_admissions(kernel_store, context, trial_id)
    activity = _CanonicalActivityCounter()
    started = time.monotonic()

    def execute(item: _AdmissionPreparation) -> G6UnitTrialResultV1:
        packet_hash = assignment_packet_hash(Path(repo_root), item.unit_id)
        spec = make_g6_reasoning_spec(
            assignment_ref=f"benchmark-packet:{item.unit_id}",
            assignment_hash=packet_hash,
        )
        request = AdmissionRequestV1(
            mission_id=context.mission_id,
            work_package_id=item.work_package_id,
            controller_request_id=item.controller_request_id,
            repo_name=repo_name,
            reasoning_spec=spec,
            expected_plan_revision_id=context.plan_revision_id,
            expected_plan_state_version=context.plan_state_version,
            supersedes_attempt_id=item.supersedes_attempt_id,
        )
        entered = False

        def after_commit(_attempt_id: str, _task_id: str) -> None:
            nonlocal entered
            activity.enter()
            entered = True

        unit_started = time.monotonic()
        try:
            result = admit_reasoning_work_package(
                task_manager,
                request,
                _after_commit_hook=after_commit,
            )
            task = task_manager.store.get_task(result.task_id)
            submission = submission_loader(task.backend_ref)
            assessment = assessment_loader(task.backend_ref)
            return G6UnitTrialResultV1(
                unit_id=item.unit_id,
                work_package_id=item.work_package_id,
                controller_request_id=item.controller_request_id,
                supersedes_attempt_id=item.supersedes_attempt_id,
                attempt_id=result.attempt_id,
                task_id=result.task_id,
                backend_ref=task.backend_ref,
                task_state=task.state.value,
                created=result.created,
                latency_seconds=max(0.0, time.monotonic() - unit_started),
                submission_present=submission is not None,
                assessment_present=assessment is not None,
            )
        except Exception as exc:
            return G6UnitTrialResultV1(
                unit_id=item.unit_id,
                work_package_id=item.work_package_id,
                controller_request_id=item.controller_request_id,
                supersedes_attempt_id=item.supersedes_attempt_id,
                latency_seconds=max(0.0, time.monotonic() - unit_started),
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if entered:
                activity.exit()

    unit_results_by_id: dict[str, G6UnitTrialResultV1] = {}
    with ThreadPoolExecutor(
        max_workers=canonical_concurrency_limit,
        thread_name_prefix=f"{trial_id}-{_condition_name(canonical_concurrency_limit)}",
    ) as executor:
        future_map = {executor.submit(execute, item): item.unit_id for item in admissions}
        for future in as_completed(future_map):
            unit_results_by_id[future_map[future]] = future.result()
    makespan = max(0.0, time.monotonic() - started)
    unit_results = tuple(unit_results_by_id[unit_id] for unit_id in G6_EXPECTED_UNIT_IDS)

    submissions: dict[str, EvidenceSubmissionV1] = {}
    assessments: dict[str, Mapping[str, Any]] = {}
    for result in unit_results:
        if not result.backend_ref:
            continue
        submission = submission_loader(result.backend_ref)
        if submission is not None:
            submissions[result.unit_id] = submission
        assessment = assessment_loader(result.backend_ref)
        if assessment is not None:
            assessments[result.unit_id] = assessment

    assignment_fact_keys = {
        unit.unit_id: tuple(question.fact_key for question in unit.questions)
        for unit in UNITS
    }
    fanin = synthesize_fanin(
        G6_EXPECTED_UNIT_IDS,
        submissions,
        assignment_fact_keys=assignment_fact_keys,
        mission_id=context.mission_id,
        plan_revision_id=context.plan_revision_id,
    )
    fanin_ref, fanin_hash = store.write_fanin(trial_id, fanin)

    deliberate_repetition = any(item.supersedes_attempt_id for item in admissions)
    metrics = _mechanical_metrics(
        fanin=fanin,
        assessments=assessments,
        unit_results=unit_results,
        deliberate_trial_repetition=deliberate_repetition,
    )
    result = G6TrialResultV1(
        trial_id=trial_id,
        trial_manifest_hash=manifest_hash,
        phase=phase,
        condition=_condition_name(canonical_concurrency_limit),
        canonical_concurrency_limit=canonical_concurrency_limit,
        repetition_index=repetition_index,
        mission_id=context.mission_id,
        plan_revision_id=context.plan_revision_id,
        makespan_seconds=makespan,
        peak_active_canonical_tasks=activity.peak,
        unit_results=unit_results,
        fanin_ref=fanin_ref,
        fanin_hash=fanin_hash,
        metrics=metrics,
    )
    store.write_result(result)
    return result
