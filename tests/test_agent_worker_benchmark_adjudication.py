"""Durable Sol adjudication contract tests for the frozen G6 benchmark."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from soma.agent_worker_benchmark_adjudication import (
    G6SemanticAdjudicationError,
    G6SemanticAdjudicationStore,
    G6SemanticConflictReviewV1,
    build_semantic_adjudication,
    screening_quality_passes,
    semantic_scoring_policy_hash,
)
from soma.agent_worker_benchmark_runner import (
    G6MechanicalMetricsV1,
    G6TrialResultV1,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _result(*, fanin_hash: str = "b" * 64) -> G6TrialResultV1:
    return G6TrialResultV1(
        trial_id="g6trial_" + "1" * 24,
        trial_manifest_hash="a" * 64,
        phase="screening",
        condition="C1",
        canonical_concurrency_limit=1,
        repetition_index=1,
        mission_id="mission_" + "2" * 24,
        plan_revision_id="planrev_" + "3" * 24,
        makespan_seconds=100.0,
        peak_active_canonical_tasks=1,
        unit_results=(),
        fanin_ref="g6-trial:test:fanin",
        fanin_hash=fanin_hash,
        metrics=G6MechanicalMetricsV1(
            expected_units=8,
            collected_submissions=8,
            schema_valid_submission_rate=1.0,
            required_fact_keys=40,
            covered_required_fact_keys=40,
            required_fact_key_recall=1.0,
            evidence_reference_validity_rate=1.0,
            claims=41,
            claims_without_support=0,
            claims_without_support_rate=0.0,
            critical_trap_failures=0,
            missing_units=0,
            partial_units=0,
            blocked_units=0,
            uncertain_units=0,
            fanin_structured_conflicts=1,
            fanin_unresolved_uncertainties=2,
            total_input_tokens=500_000,
            total_output_tokens=7_000,
            total_cost_usd="0",
            aggregate_submission_bytes=180_000,
            fanin_response_bytes=48_000,
            task_backend_starts=8,
            automatic_retry_count=0,
            deliberate_trial_repetition=True,
        ),
    )


def _adjudication(result: G6TrialResultV1):
    return build_semantic_adjudication(
        result=result,
        correct_fact_keys=40,
        unsupported_claims=0,
        evidence_links=181,
        precise_evidence_links=181,
        material_uncertainties=2,
        preserved_material_uncertainties=2,
        conflict_reviews=(
            G6SemanticConflictReviewV1(
                fact_key="hermes.supervisor_worker_ceiling",
                disposition="complementary",
                rationale=(
                    "A configured ceiling of 32 and the absence of evidence for the "
                    "current configured count are compatible claims."
                ),
            ),
        ),
    )


def test_c1_semantic_scores_are_exact_and_policy_hash_is_stable() -> None:
    result = _result()
    first = _adjudication(result)
    second = _adjudication(result)

    assert first == second
    assert first.scoring_policy_hash == semantic_scoring_policy_hash()
    assert first.fact_key_correctness == 1.0
    assert first.unsupported_assertion_rate == 0.0
    assert first.evidence_precision == 1.0
    assert first.baseline_eligible is True
    assert first.reported_unresolved_uncertainties == 2
    assert first.preserved_material_uncertainties == 2


def test_screening_quality_gate_uses_frozen_c1_relative_thresholds() -> None:
    result = _result()
    baseline = _adjudication(result)

    assert screening_quality_passes(
        result=result,
        adjudication=baseline,
        c1_baseline=baseline,
    )

    degraded = baseline.model_copy(
        update={
            "unsupported_claims": 3,
            "unsupported_assertion_rate": 3 / 41,
        }
    )
    assert not screening_quality_passes(
        result=result,
        adjudication=degraded,
        c1_baseline=baseline,
    )


def test_store_binds_manifest_result_and_fanin_and_is_immutable(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    result = _result()
    adjudication = _adjudication(result)
    directory = runs_dir / "agent_worker_benchmark_trials" / result.trial_id
    directory.mkdir(parents=True)

    manifest = b"{}"
    fanin = b'{"fanin":"fixture"}'
    result = result.model_copy(
        update={
            "trial_manifest_hash": _sha(manifest),
            "fanin_hash": _sha(fanin),
        }
    )
    adjudication = _adjudication(result)
    (directory / "manifest.json").write_bytes(manifest)
    (directory / "fanin.json").write_bytes(fanin)
    (directory / "result.json").write_text(
        json.dumps(
            result.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    store = G6SemanticAdjudicationStore(runs_dir)
    first_ref, first_hash = store.write(adjudication)
    second_ref, second_hash = store.write(adjudication)

    assert first_ref == second_ref
    assert first_hash == second_hash
    assert store.load(result.trial_id) == adjudication

    changed = adjudication.model_copy(update={"notes": ("different review",)})
    with pytest.raises(G6SemanticAdjudicationError, match="immutable"):
        store.write(changed)


def test_store_rejects_wrong_fanin_identity(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    result = _result()
    directory = runs_dir / "agent_worker_benchmark_trials" / result.trial_id
    directory.mkdir(parents=True)
    manifest = b"{}"
    fanin = b'{"fanin":"fixture"}'
    result = result.model_copy(
        update={
            "trial_manifest_hash": _sha(manifest),
            "fanin_hash": _sha(fanin),
        }
    )
    (directory / "manifest.json").write_bytes(manifest)
    (directory / "fanin.json").write_bytes(fanin)
    (directory / "result.json").write_text(
        result.model_dump_json(),
        encoding="utf-8",
    )
    adjudication = _adjudication(result).model_copy(update={"fanin_hash": "f" * 64})

    with pytest.raises(G6SemanticAdjudicationError, match="FanIn identity mismatch"):
        G6SemanticAdjudicationStore(runs_dir).write(adjudication)
