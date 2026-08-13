"""Durable Sol semantic adjudication for frozen G6 benchmark trials.

Mechanical benchmark metrics remain immutable in the trial result. This module
adds a separate hash-bound semantic review over that exact trial/FanIn identity,
so later concurrency conditions cannot move the C1 scoring baseline.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.agent_worker_benchmark import SOURCE_COMMIT
from soma.agent_worker_benchmark_runner import G6TrialResultV1


G6_SEMANTIC_ADJUDICATION_SCHEMA: Final[str] = (
    "soma.agent_worker_benchmark.semantic_adjudication.v1"
)
G6_SEMANTIC_SCORING_POLICY_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.semantic_scoring.v1"
)


class G6SemanticAdjudicationError(RuntimeError):
    """Semantic benchmark review cannot be trusted or persisted safely."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class G6SemanticConflictReviewV1(_FrozenModel):
    fact_key: str = Field(min_length=1, max_length=256)
    disposition: Literal["complementary", "substantive_conflict", "unresolved"]
    rationale: str = Field(min_length=1, max_length=2048)


class G6SemanticAdjudicationV1(_FrozenModel):
    schema_version: Literal[G6_SEMANTIC_ADJUDICATION_SCHEMA] = (
        G6_SEMANTIC_ADJUDICATION_SCHEMA
    )
    trial_id: str = Field(min_length=1, max_length=64)
    trial_manifest_hash: str = Field(min_length=64, max_length=64)
    fanin_hash: str = Field(min_length=64, max_length=64)
    source_commit: str = Field(min_length=40, max_length=40)
    evaluator: Literal["sol"] = "sol"
    scoring_policy_version: Literal[G6_SEMANTIC_SCORING_POLICY_VERSION] = (
        G6_SEMANTIC_SCORING_POLICY_VERSION
    )
    scoring_policy_hash: str = Field(min_length=64, max_length=64)
    required_fact_keys: int = Field(gt=0)
    correct_fact_keys: int = Field(ge=0)
    fact_key_correctness: float = Field(ge=0, le=1)
    required_fact_key_recall: float = Field(ge=0, le=1)
    claims: int = Field(gt=0)
    unsupported_claims: int = Field(ge=0)
    unsupported_assertion_rate: float = Field(ge=0, le=1)
    evidence_links: int = Field(gt=0)
    precise_evidence_links: int = Field(ge=0)
    evidence_precision: float = Field(ge=0, le=1)
    critical_trap_failures: int = Field(ge=0)
    missing_units: int = Field(ge=0)
    reported_unresolved_uncertainties: int = Field(ge=0)
    material_uncertainties: int = Field(ge=0)
    preserved_material_uncertainties: int = Field(ge=0)
    conflict_reviews: tuple[G6SemanticConflictReviewV1, ...] = ()
    baseline_eligible: bool
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_counts_and_ratios(self):
        if self.correct_fact_keys > self.required_fact_keys:
            raise ValueError("correct_fact_keys cannot exceed required_fact_keys")
        if self.unsupported_claims > self.claims:
            raise ValueError("unsupported_claims cannot exceed claims")
        if self.precise_evidence_links > self.evidence_links:
            raise ValueError("precise_evidence_links cannot exceed evidence_links")
        if self.preserved_material_uncertainties > self.material_uncertainties:
            raise ValueError(
                "preserved_material_uncertainties cannot exceed material_uncertainties"
            )
        expected = (
            self.correct_fact_keys / self.required_fact_keys,
            self.unsupported_claims / self.claims,
            self.precise_evidence_links / self.evidence_links,
        )
        observed = (
            self.fact_key_correctness,
            self.unsupported_assertion_rate,
            self.evidence_precision,
        )
        labels = (
            "fact_key_correctness",
            "unsupported_assertion_rate",
            "evidence_precision",
        )
        for label, actual, wanted in zip(labels, observed, expected, strict=True):
            if abs(actual - wanted) > 1e-12:
                raise ValueError(f"{label} does not match exact numerator/denominator")
        return self


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def semantic_scoring_policy() -> dict[str, object]:
    return {
        "schema_version": G6_SEMANTIC_SCORING_POLICY_VERSION,
        "fact_key_correctness": {
            "numerator": "semantically correct required fact keys",
            "denominator": "assignment-required fact keys",
        },
        "unsupported_assertion_rate": {
            "numerator": "structured claims not supported by frozen packet facts",
            "denominator": "structured claims",
            "maximum_for_quality_gate": 0.05,
        },
        "evidence_precision": {
            "numerator": (
                "published claim-to-evidence links whose cited passage supports "
                "or opposes the claim as declared"
            ),
            "denominator": "published claim-to-evidence links",
        },
        "candidate_relative_gate": {
            "required_fact_key_recall_floor": "C1 minus 0.02",
            "evidence_precision_floor": "C1 minus 0.02",
        },
        "mechanical_gate": {
            "critical_trap_failures": 0,
            "schema_valid_submission_rate": 1.0,
            "missing_units": 0,
        },
        "gold_mutation_after_candidate_results": ("forbidden_without_versioned_rerun"),
    }


def semantic_scoring_policy_hash() -> str:
    return _sha256(_canonical_json_bytes(semantic_scoring_policy()))


def build_semantic_adjudication(
    *,
    result: G6TrialResultV1,
    correct_fact_keys: int,
    unsupported_claims: int,
    evidence_links: int,
    precise_evidence_links: int,
    material_uncertainties: int,
    preserved_material_uncertainties: int,
    conflict_reviews: tuple[G6SemanticConflictReviewV1, ...] = (),
    notes: tuple[str, ...] = (),
) -> G6SemanticAdjudicationV1:
    metrics = result.metrics
    baseline_eligible = (
        metrics.critical_trap_failures == 0
        and metrics.schema_valid_submission_rate == 1.0
        and metrics.missing_units == 0
        and unsupported_claims / metrics.claims <= 0.05
    )
    return G6SemanticAdjudicationV1(
        trial_id=result.trial_id,
        trial_manifest_hash=result.trial_manifest_hash,
        fanin_hash=result.fanin_hash,
        source_commit=SOURCE_COMMIT,
        scoring_policy_hash=semantic_scoring_policy_hash(),
        required_fact_keys=metrics.required_fact_keys,
        correct_fact_keys=correct_fact_keys,
        fact_key_correctness=correct_fact_keys / metrics.required_fact_keys,
        required_fact_key_recall=metrics.required_fact_key_recall,
        claims=metrics.claims,
        unsupported_claims=unsupported_claims,
        unsupported_assertion_rate=unsupported_claims / metrics.claims,
        evidence_links=evidence_links,
        precise_evidence_links=precise_evidence_links,
        evidence_precision=precise_evidence_links / evidence_links,
        critical_trap_failures=metrics.critical_trap_failures,
        missing_units=metrics.missing_units,
        reported_unresolved_uncertainties=metrics.fanin_unresolved_uncertainties,
        material_uncertainties=material_uncertainties,
        preserved_material_uncertainties=preserved_material_uncertainties,
        conflict_reviews=conflict_reviews,
        baseline_eligible=baseline_eligible,
        notes=notes,
    )


def screening_quality_passes(
    *,
    result: G6TrialResultV1,
    adjudication: G6SemanticAdjudicationV1,
    c1_baseline: G6SemanticAdjudicationV1,
) -> bool:
    if (
        adjudication.trial_id != result.trial_id
        or adjudication.fanin_hash != result.fanin_hash
    ):
        raise G6SemanticAdjudicationError(
            "semantic adjudication does not match the supplied trial result"
        )
    return (
        result.metrics.critical_trap_failures == 0
        and result.metrics.schema_valid_submission_rate == 1.0
        and result.metrics.missing_units == 0
        and adjudication.unsupported_assertion_rate <= 0.05
        and result.metrics.required_fact_key_recall
        >= c1_baseline.required_fact_key_recall - 0.02
        and adjudication.evidence_precision >= c1_baseline.evidence_precision - 0.02
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class G6SemanticAdjudicationStore:
    def __init__(self, runs_dir: Path) -> None:
        self.root = Path(runs_dir) / "agent_worker_benchmark_trials"

    def _directory(self, trial_id: str) -> Path:
        if not trial_id.startswith("g6trial_") or len(trial_id) > 64:
            raise G6SemanticAdjudicationError("invalid G6 trial_id")
        return self.root / trial_id

    def load(self, trial_id: str) -> G6SemanticAdjudicationV1 | None:
        path = self._directory(trial_id) / "semantic_adjudication.json"
        if not path.exists():
            return None
        try:
            return G6SemanticAdjudicationV1.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise G6SemanticAdjudicationError(
                "stored G6 semantic adjudication is unreadable"
            ) from exc

    def write(self, adjudication: G6SemanticAdjudicationV1) -> tuple[str, str]:
        directory = self._directory(adjudication.trial_id)
        manifest_path = directory / "manifest.json"
        result_path = directory / "result.json"
        fanin_path = directory / "fanin.json"
        if (
            not manifest_path.exists()
            or not result_path.exists()
            or not fanin_path.exists()
        ):
            raise G6SemanticAdjudicationError(
                "G6 trial manifest/result/FanIn must exist before semantic adjudication"
            )
        if _sha256(manifest_path.read_bytes()) != adjudication.trial_manifest_hash:
            raise G6SemanticAdjudicationError("trial manifest hash mismatch")
        result = G6TrialResultV1.model_validate_json(
            result_path.read_text(encoding="utf-8")
        )
        if result.trial_id != adjudication.trial_id:
            raise G6SemanticAdjudicationError("stored trial identity mismatch")
        if result.trial_manifest_hash != adjudication.trial_manifest_hash:
            raise G6SemanticAdjudicationError("stored trial manifest identity mismatch")
        if result.fanin_hash != adjudication.fanin_hash:
            raise G6SemanticAdjudicationError("stored trial FanIn identity mismatch")
        if _sha256(fanin_path.read_bytes()) != adjudication.fanin_hash:
            raise G6SemanticAdjudicationError("stored FanIn body hash mismatch")

        payload = _canonical_json_bytes(adjudication.model_dump(mode="json"))
        path = directory / "semantic_adjudication.json"
        if path.exists():
            existing = path.read_bytes()
            if existing != payload:
                raise G6SemanticAdjudicationError(
                    "semantic adjudication is immutable once written"
                )
        else:
            _atomic_write(path, payload)
        digest = _sha256(payload)
        return f"g6-trial:{adjudication.trial_id}:semantic-adjudication", digest
