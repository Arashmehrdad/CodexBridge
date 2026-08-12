"""Frozen G6 agent/worker canonical-concurrency benchmark package.

The Iteration-5 research record freezes the source commit, per-blob SHA-256
values, eight unit definitions, and a research corpus hash. It does not record
the canonical serialization recipe or concrete lane-ID strings used when that
research hash was calculated. This module therefore preserves that research
hash as inherited provenance and independently verifies every source blob.

Implementation packet identity is calculated separately from a fully explicit
materialization manifest so no missing research detail is silently invented.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final


CORPUS_IDENTITY_DOMAIN: Final[str] = "soma.agent_worker_benchmark.corpus.v1"
SOURCE_REPOSITORY: Final[str] = "soma"
SOURCE_COMMIT: Final[str] = "b53404fa9600412a4b3dd0fafd664a856096257b"
FROZEN_RESEARCH_CORPUS_HASH: Final[str] = (
    "a5feb6f20076bf17e64b51b66b65186b4b132417edeede83b7717472ac1df998"
)
ITERATION_5_SHA256: Final[str] = (
    "dc9afbfd94525890922225839488cc7b25e9798d0c61271d4bf3f0ea97d19cdb"
)
ASSIGNMENT_SCHEMA_VERSION: Final[str] = "soma.agent_worker_benchmark.assignment.v1"
MATERIALIZATION_SCHEMA_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.materialization.v1"
)
QUESTION_RUBRIC_VERSION: Final[str] = "g6-question-rubric.v1"
EVIDENCE_CONTRACT_VERSION: Final[str] = "evidence_submission.v1"
EVIDENCE_NORMAL_TARGET_BYTES: Final[int] = 12 * 1024
EVIDENCE_HARD_CEILING_BYTES: Final[int] = 32 * 1024


@dataclass(frozen=True)
class BenchmarkSource:
    path: str
    sha256: str


@dataclass(frozen=True)
class BenchmarkQuestion:
    fact_key: str
    question: str


@dataclass(frozen=True)
class BenchmarkUnit:
    unit_id: str
    lane_id: str
    title: str
    sources: tuple[BenchmarkSource, ...]
    questions: tuple[BenchmarkQuestion, ...]
    critical_trap: str
    expected_trap_disposition: str


UNITS: Final[tuple[BenchmarkUnit, ...]] = (
    BenchmarkUnit(
        unit_id="B01",
        lane_id="task_backend_authority",
        title="canonical Task/backend authority",
        sources=(
            BenchmarkSource(
                "soma/tasks/models.py",
                "d39aded14ca13647d2ed050b903eee53444d0b210b621db79a2c752c6521db63",
            ),
            BenchmarkSource(
                "soma/tasks/backends.py",
                "8e03377677eb72bf253a803cc18beeb516b570a89a63b689e9f0a5a21b57d522",
            ),
            BenchmarkSource(
                "soma/tasks/projections.py",
                "12755aa32b417025e52600bff3ca4afc39bd88d5a7365f6a1c19a246578187cb",
            ),
        ),
        questions=(
            BenchmarkQuestion(
                "task.canonical_state_owner",
                "what owns canonical task lifecycle?",
            ),
            BenchmarkQuestion(
                "task.current_task_kind_set",
                "how many current TaskKind values are implemented in this source?",
            ),
            BenchmarkQuestion(
                "task.current_backend_kind_set",
                "how many current BackendKind values are implemented?",
            ),
            BenchmarkQuestion(
                "task.result_body_policy",
                "does the Task plane copy full authoritative result/evidence bodies?",
            ),
            BenchmarkQuestion(
                "task.backend_protocol_shape",
                "which lifecycle operations does the current backend Protocol expose?",
            ),
        ),
        critical_trap=(
            "TaskState.ACCEPTED means the substantive WorkPackage outcome was accepted."
        ),
        expected_trap_disposition=(
            "false; Task admission and substantive outcome acceptance are distinct concepts"
        ),
    ),
    BenchmarkUnit(
        unit_id="B02",
        lane_id="company_kernel_identity_authority",
        title="Company Kernel identity/authority",
        sources=(
            BenchmarkSource(
                "soma/company_kernel/models.py",
                "180bf13fdb5c777d579a34d1e056cfc85345453ddac9ef1c6e2c6356b35eff89",
            ),
            BenchmarkSource(
                "soma/company_kernel/schema.py",
                "4e19c27a18c685a1ccc866d37242f3aafc6131bd701971ee2517016cf5c0ed17",
            ),
        ),
        questions=(
            BenchmarkQuestion(
                "kernel.plan_revision_immutability",
                "what makes PlanRevision an immutable company-domain fact?",
            ),
            BenchmarkQuestion(
                "kernel.work_package_route_neutrality",
                "which route-specific fields are forbidden from route-neutral WorkPackage identity?",
            ),
            BenchmarkQuestion(
                "kernel.outcome_identity_inputs",
                "which exact plan/scope/package facts contribute to outcome identity?",
            ),
            BenchmarkQuestion(
                "kernel.attempt_task_binding",
                "how does WorkPackageAttempt relate to canonical Task?",
            ),
            BenchmarkQuestion(
                "kernel.topology_v1",
                "what WorkPackage topology is currently allowed?",
            ),
        ),
        critical_trap="WorkPackage stores its own running/completed execution lifecycle.",
        expected_trap_disposition="false",
    ),
    BenchmarkUnit(
        unit_id="B03",
        lane_id="hermes_headless_concurrency",
        title="Hermes headless/concurrency substrate",
        sources=(
            BenchmarkSource(
                "soma/hermes_companion_protocol.py",
                "17565bf31fb729b70ab2f7b460637168372570661c1712a7abd7731bc4d91259",
            ),
            BenchmarkSource(
                "soma/hermes_service_supervisor.py",
                "2a6c04546326edb84061091b55e4b91bfde7f341e2281d3acf78e0cf4c950c85",
            ),
            BenchmarkSource(
                "soma/hermes_concurrency.py",
                "20ad0f2ec31f4fe0530ee8992433692c12101c6b9981dfdec9457e5dd1ea9309",
            ),
        ),
        questions=(
            BenchmarkQuestion(
                "hermes.model_runtime_policy",
                "what proves the companion is headless?",
            ),
            BenchmarkQuestion(
                "hermes.pinned_revision",
                "what exact Hermes revision is accepted by the protocol?",
            ),
            BenchmarkQuestion(
                "hermes.supervisor_worker_ceiling",
                "what is the code ceiling for supervised workers?",
            ),
            BenchmarkQuestion(
                "hermes.concurrency_meaning",
                "does more supervised worker capacity imply more independent reasoning minds?",
            ),
            BenchmarkQuestion(
                "hermes.resource_mutation_lock",
                "how are same-resource mutations serialized in the Hermes service layer?",
            ),
        ),
        critical_trap=(
            "MAX_SUPERVISED_WORKERS = 32 proves Soma currently runs 32 Hermes workers."
        ),
        expected_trap_disposition=(
            "false; a code ceiling is not current configured capacity"
        ),
    ),
    BenchmarkUnit(
        unit_id="B04",
        lane_id="workflow_parallel_substrates",
        title="legacy Workflow versus parallel-run substrates",
        sources=(
            BenchmarkSource(
                "soma/workflows/models.py",
                "e8fbacf95d2af7e95209dff6ec6b332b7f487b1743f69a41b317a4a561085bb1",
            ),
            BenchmarkSource(
                "soma/workflows/worker.py",
                "1329b34caaadad5bbcb782bb2db1f5f0ea611a22febda264471d9241af66cf4d",
            ),
            BenchmarkSource(
                "soma/parallel_groups.py",
                "e36145491349ab9fc774c586530cbf0dd28b9d4dc8f7ee5e2f02c52e1182bbee",
            ),
        ),
        questions=(
            BenchmarkQuestion(
                "workflow.graph_validation",
                "what dependency validation exists?",
            ),
            BenchmarkQuestion(
                "workflow.active_child_cardinality",
                "how many active child runs does the Workflow runtime own at once?",
            ),
            BenchmarkQuestion(
                "workflow.readiness_rule",
                "how does _next_pending_step() determine readiness?",
            ),
            BenchmarkQuestion(
                "parallel_group.child_identity",
                "what durable identities/keys are reserved for parallel command children?",
            ),
            BenchmarkQuestion(
                "parallel_group.relationship_to_workflow",
                "is the parallel command group the same lifecycle system as Workflow?",
            ),
        ),
        critical_trap=(
            "Because Workflow accepts a DAG definition, its runtime already performs "
            "concurrent fan-out/fan-in across independent steps."
        ),
        expected_trap_disposition="false",
    ),
    BenchmarkUnit(
        unit_id="B05",
        lane_id="provider_adapter_capability_truth",
        title="provider-adapter capability truth",
        sources=(
            BenchmarkSource(
                "soma/worker_adapters/contract.py",
                "dc7b4d9c54dd4bbac8cb9c6469acf4f6bf2c38e2131d9f340bd02fa3ce133653",
            ),
            BenchmarkSource(
                "soma/worker_adapters/codex.py",
                "64f2f9e0f6ac588b9f4d4e78a6a1eb14f6d77696a78827c92431e9244fba7dcd",
            ),
            BenchmarkSource(
                "soma/worker_adapters/claude_code.py",
                "02173b0ad5643c601b0e484a339d8057d63c435ec6f210eb6b2c935a5c4cfd06",
            ),
        ),
        questions=(
            BenchmarkQuestion(
                "adapter.capability_declaration_completeness",
                "what happens if a capability is omitted?",
            ),
            BenchmarkQuestion(
                "adapter.capability_support_vocabulary",
                "what are the three support values?",
            ),
            BenchmarkQuestion(
                "adapter.provider_completion_semantics",
                "is a provider completion event canonical Task success?",
            ),
            BenchmarkQuestion(
                "adapter.protocol_uncertainty",
                "what kinds of stream evidence force fail-closed uncertainty?",
            ),
            BenchmarkQuestion(
                "adapter.cancellation_measurement",
                "what does current evidence say about orphan-free root cancellation for Claude Code and Codex?",
            ),
        ),
        critical_trap=(
            "An undeclared provider capability may be treated as supported when the "
            "adapter does not say otherwise."
        ),
        expected_trap_disposition=(
            "false; incomplete declarations are refused"
        ),
    ),
    BenchmarkUnit(
        unit_id="B06",
        lane_id="interaction_delivery_durability",
        title="interaction delivery durability",
        sources=(
            BenchmarkSource(
                "soma/worker_substrate/models.py",
                "bfbcc8c3b88a3065d846a72b01b375d9853bc1618cd4033563a1f4375c75fb64",
            ),
            BenchmarkSource(
                "soma/worker_substrate/coordinator.py",
                "62ca7ae5737009c324f45a6994cac5a10a8fe8d1a101b1502b219e43022f152f",
            ),
            BenchmarkSource(
                "soma/worker_substrate/dispatch.py",
                "d8134e563d1dfb21a67372233f3ba3f3f2a4a560dd76501427c09ff1c015b7f7",
            ),
        ),
        questions=(
            BenchmarkQuestion(
                "interaction.atomic_reservation",
                "which canonical/subordinate records are reserved together?",
            ),
            BenchmarkQuestion(
                "interaction.persist_before_send",
                "what is durable before the transport call occurs?",
            ),
            BenchmarkQuestion(
                "interaction.outcome_unknown_rule",
                "what happens after an ambiguous post-claim transport failure?",
            ),
            BenchmarkQuestion(
                "interaction.authority_fields",
                "which project/resource/task/run/session/mandate identities are carried?",
            ),
            BenchmarkQuestion(
                "interaction.lifecycle_ownership",
                "does the interaction message become a second running Task lifecycle?",
            ),
        ),
        critical_trap=(
            "If transport raises after the durable send claim, recovery may safely "
            "resend the message automatically."
        ),
        expected_trap_disposition="false",
    ),
    BenchmarkUnit(
        unit_id="B07",
        lane_id="project_scope_mutation_containment",
        title="ProjectScope and mutation containment",
        sources=(
            BenchmarkSource(
                "soma/project_scope/store.py",
                "2b7ff63cf289612385bc591a1860657264163da194c0d76fd9929435bacd5a06",
            ),
            BenchmarkSource(
                "soma/operation_locks.py",
                "c5b4b2938ab407b71db65eba88a70ae82b06361de23d81d333655f38750ccb18",
            ),
        ),
        questions=(
            BenchmarkQuestion(
                "scope.binding_identity",
                "what exact project/resource/repository facts are validated?",
            ),
            BenchmarkQuestion(
                "scope.transaction_pattern",
                "what transaction pattern protects scope mutations/reservations?",
            ),
            BenchmarkQuestion(
                "lock.current_granularity",
                "what is the current OperationLockStore lock key/granularity?",
            ),
            BenchmarkQuestion(
                "lock.duplicate_detection",
                "how is duplicate active operation input identified?",
            ),
            BenchmarkQuestion(
                "lock.stale_ownership",
                "what evidence is considered before stale ownership is reclaimed?",
            ),
        ),
        critical_trap=(
            "An organisational/model role that is allowed to propose repository work "
            "automatically owns the repository operation lock."
        ),
        expected_trap_disposition=(
            "unsupported/false; concrete lock ownership is mechanical, not inferred "
            "from reasoning authority"
        ),
    ),
    BenchmarkUnit(
        unit_id="B08",
        lane_id="run_publication_recovery_truth",
        title="Run/publication/recovery truth",
        sources=(
            BenchmarkSource(
                "soma/run_store.py",
                "f2fb3407330e6247b89c620706cc431ce79e78222d17edbe913e0ca8917b550b",
            ),
            BenchmarkSource(
                "soma/run_public_result.py",
                "c1ee8dfad1be401f99a6ce535c1861d095f90adba75c89572e3b79fe14993be2",
            ),
        ),
        questions=(
            BenchmarkQuestion(
                "run.terminal_status_vocabulary",
                "what current durable Run statuses are terminal?",
            ),
            BenchmarkQuestion(
                "run.awaiting_controller_semantics",
                "how is current non-terminal owner waiting represented?",
            ),
            BenchmarkQuestion(
                "run.legacy_model_tools",
                "what is the status of historical Codex run-tool identifiers?",
            ),
            BenchmarkQuestion(
                "run.publication_identity",
                "which fields establish durable public-result publication identity?",
            ),
            BenchmarkQuestion(
                "run.normalized_outcome_separation",
                "does public projection success alone create Company Kernel OutcomeAcceptance?",
            ),
        ),
        critical_trap=(
            "Historical needs_input rows are the same non-terminal interactive state "
            "used by the current V3 interactive path."
        ),
        expected_trap_disposition=(
            "false; historical needs_input is terminal compatibility data while current "
            "interactive waiting uses awaiting_controller"
        ),
    ),
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def unit_by_id(unit_id: str) -> BenchmarkUnit:
    for unit in UNITS:
        if unit.unit_id == unit_id:
            return unit
    raise KeyError(unit_id)


def source_manifest() -> dict[str, Any]:
    """Return the fully explicit implementation materialization manifest."""

    return {
        "schema_version": MATERIALIZATION_SCHEMA_VERSION,
        "research_identity": {
            "domain": CORPUS_IDENTITY_DOMAIN,
            "repository": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            "frozen_research_corpus_hash": FROZEN_RESEARCH_CORPUS_HASH,
            "iteration_5_sha256": ITERATION_5_SHA256,
            "research_hash_serialization_recorded": False,
        },
        "units": [
            {
                "unit_id": unit.unit_id,
                "lane_id": unit.lane_id,
                "sources": [
                    {"path": source.path, "sha256": source.sha256}
                    for source in unit.sources
                ],
            }
            for unit in UNITS
        ],
    }


def materialization_manifest_hash() -> str:
    return sha256_hex(canonical_json_bytes(source_manifest()))


def _git_blob(repo_root: Path, source: BenchmarkSource) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{SOURCE_COMMIT}:{source.path}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Unable to read frozen source {source.path!r}: {message}")
    return completed.stdout


def verify_frozen_sources(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    verified: list[dict[str, Any]] = []
    for unit in UNITS:
        for source in unit.sources:
            blob = _git_blob(repo_root, source)
            actual = sha256_hex(blob)
            if actual != source.sha256:
                raise ValueError(
                    f"Frozen source hash mismatch for {source.path}: "
                    f"expected {source.sha256}, got {actual}"
                )
            verified.append(
                {
                    "unit_id": unit.unit_id,
                    "path": source.path,
                    "sha256": actual,
                    "bytes": len(blob),
                }
            )
    return {
        "ok": True,
        "repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "frozen_research_corpus_hash": FROZEN_RESEARCH_CORPUS_HASH,
        "materialization_manifest_hash": materialization_manifest_hash(),
        "unit_count": len(UNITS),
        "source_count": len(verified),
        "verified_sources": verified,
    }


def build_assignment_packet(repo_root: Path, unit_id: str) -> bytes:
    """Materialize one byte-stable assignment from frozen Git blobs, never worktree files."""

    unit = unit_by_id(unit_id)
    sources: list[dict[str, Any]] = []
    for source in unit.sources:
        blob = _git_blob(Path(repo_root).resolve(), source)
        actual = sha256_hex(blob)
        if actual != source.sha256:
            raise ValueError(
                f"Frozen source hash mismatch for {source.path}: "
                f"expected {source.sha256}, got {actual}"
            )
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Frozen benchmark source is not UTF-8: {source.path}") from exc
        sources.append(
            {
                "path": source.path,
                "sha256": source.sha256,
                "content": text,
            }
        )

    packet = {
        "schema_version": ASSIGNMENT_SCHEMA_VERSION,
        "corpus": {
            "repository": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            "frozen_research_corpus_hash": FROZEN_RESEARCH_CORPUS_HASH,
            "materialization_manifest_hash": materialization_manifest_hash(),
        },
        "unit": {
            "unit_id": unit.unit_id,
            "lane_id": unit.lane_id,
            "title": unit.title,
        },
        "rubric": {
            "version": QUESTION_RUBRIC_VERSION,
            "questions": [
                {"fact_key": question.fact_key, "question": question.question}
                for question in unit.questions
            ],
            "critical_trap": unit.critical_trap,
            "expected_trap_disposition": unit.expected_trap_disposition,
        },
        "output_contract": {
            "schema_version": EVIDENCE_CONTRACT_VERSION,
            "normal_target_bytes": EVIDENCE_NORMAL_TARGET_BYTES,
            "hard_ceiling_bytes": EVIDENCE_HARD_CEILING_BYTES,
        },
        "instruction": (
            "Using only the supplied frozen source packet, answer the unit's exact "
            "fact-key questions. For each claim classify it as observation, inference, "
            "recommendation, or negative_finding; bind it to the assignment-provided "
            "fact_key when one exists; cite exact source path plus bounded locator; "
            "attach the source hash; say uncertain/unsupported when the packet does not "
            "establish a claim; do not import knowledge from other Soma files, chat "
            "history, web sources, or provider reputation; do not implement or modify "
            "anything. Return only the required structured evidence payload."
        ),
        "sources": sources,
    }
    return canonical_json_bytes(packet)


def assignment_packet_hash(repo_root: Path, unit_id: str) -> str:
    return sha256_hex(build_assignment_packet(repo_root, unit_id))
