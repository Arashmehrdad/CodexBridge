"""G3.4 deterministic FanInV1 structural, conflict, coverage and budget proofs."""

from __future__ import annotations

from collections import OrderedDict

import pytest

from soma.worker_evidence import (
    EvidenceArtifactV1,
    EvidenceAssignmentV1,
    EvidenceBlockerV1,
    EvidenceByteAccountingV1,
    EvidenceClaimV1,
    EvidenceHashedReferenceV1,
    EvidenceProducerV1,
    EvidenceRecordV1,
    EvidenceSubmissionV1,
    EvidenceUncertaintyV1,
    EvidenceUsageV1,
    EvidenceWorkIdentityV1,
)
from soma.worker_evidence.fanin import (
    FANIN_HARD_CEILING_BYTES,
    FANIN_NORMAL_TARGET_BYTES,
    FanInValidationError,
    synthesize_fanin,
)

MISSION_ID = "mission_" + "1" * 24
PLAN_ID = "planrev_" + "2" * 24
SYNTHESIS_PACKAGE_ID = "workpkg_" + "3" * 24


def _hash(character: str) -> str:
    return character * 64


def _package(index: int) -> str:
    return "workpkg_" + f"{index:024x}"


def _submission(
    index: int,
    *,
    backend_kind: str = "retrieval_worker",
    disposition: str = "complete",
    fact_key: str | None = "api_version",
    fact_value=2,
    source_hash: str | None = None,
    summary: str | None = None,
    uncertainties: tuple[EvidenceUncertaintyV1, ...] = (),
    blockers: tuple[EvidenceBlockerV1, ...] = (),
) -> EvidenceSubmissionV1:
    evidence = ()
    claims = ()
    if fact_key is not None:
        evidence = (
            EvidenceRecordV1(
                evidence_id=f"evidence-{index}",
                source_kind="repository_file",
                source_ref=f"repo:file:{index}",
                source_hash=source_hash if source_hash is not None else _hash("a"),
                fact_key=fact_key,
                fact_value=fact_value,
            ),
        )
        claims = (
            EvidenceClaimV1(
                claim_id=f"claim-{index}",
                claim_class="observation",
                subject_key=fact_key,
                statement=f"Exact structured fact for unit {index}.",
                supports_evidence_ids=(f"evidence-{index}",),
            ),
        )
    return EvidenceSubmissionV1(
        submission_id=f"submission-{index}",
        work_identity=EvidenceWorkIdentityV1(
            mission_id=MISSION_ID,
            plan_revision_id=PLAN_ID,
            work_package_id=_package(index),
            task_id=f"task_fixture_{index}",
        ),
        assignment=EvidenceAssignmentV1(
            contract_ref=f"assignment:{index}",
            contract_hash=_hash("b"),
        ),
        producer=EvidenceProducerV1(
            backend_kind=backend_kind,
            provider=("fake" if backend_kind == "soma_reasoning" else None),
            model_or_profile=f"profile-{index}",
        ),
        submission_disposition=disposition,
        executive_summary=(
            summary if summary is not None else f"Unit {index} evidence."
        ),
        claims=claims,
        evidence=evidence,
        artifacts=(
            EvidenceArtifactV1(
                artifact_ref=f"artifact:{index}",
                artifact_hash=_hash("c"),
                media_type="text/plain",
                role="supporting_log",
            ),
        ),
        uncertainties=uncertainties,
        blockers=blockers,
        usage=EvidenceUsageV1(
            wall_time_seconds=1.5,
            input_tokens=10,
            output_tokens=5,
            cost_usd="0.001",
        ),
        provenance=(
            EvidenceHashedReferenceV1(ref=f"provenance:{index}", hash=_hash("d")),
        ),
        full_evidence_retrieval=(
            EvidenceHashedReferenceV1(ref=f"full:{index}", hash=_hash("e")),
        ),
        byte_accounting=EvidenceByteAccountingV1(
            referenced_body_bytes=100,
            omitted_body_bytes=1000,
        ),
    )


def _fanin(expected, submissions, *, keys=None):
    return synthesize_fanin(
        expected_unit_refs=expected,
        submissions=submissions,
        assignment_fact_keys=keys or {},
        mission_id=MISSION_ID,
        plan_revision_id=PLAN_ID,
        synthesis_work_package_id=SYNTHESIS_PACKAGE_ID,
    )


def test_expected_coverage_and_incomplete_units_are_explicit() -> None:
    uncertain = EvidenceUncertaintyV1(
        uncertainty_id="uncertain-3",
        kind="source_gap",
        statement="One bounded source remains unavailable.",
    )
    blocker = EvidenceBlockerV1(
        blocker_id="blocked-2",
        kind="missing_input",
        statement="Required source is unavailable.",
        requested_input_ref="input:fixture",
    )
    submissions = {
        "unit-1": _submission(1),
        "unit-2": _submission(
            2, disposition="blocked", fact_key=None, blockers=(blocker,)
        ),
        "unit-3": _submission(
            3,
            disposition="uncertain",
            fact_key=None,
            uncertainties=(uncertain,),
        ),
        "unit-4": _submission(4, disposition="partial", fact_key=None),
    }
    fanin = _fanin(
        ["unit-1", "unit-2", "unit-3", "unit-4", "unit-5"],
        submissions,
        keys={"unit-1": ("api_version",)},
    )

    assert fanin.collected_unit_refs == ("unit-1", "unit-2", "unit-3", "unit-4")
    assert fanin.missing_unit_refs == ("unit-5",)
    assert fanin.blocked_unit_refs == ("unit-2",)
    assert fanin.uncertain_unit_refs == ("unit-3",)
    assert fanin.partial_unit_refs == ("unit-4",)
    assert fanin.exact_counts.expected_units == 5
    assert fanin.exact_counts.collected_units == 4
    assert fanin.exact_counts.missing_units == 1
    assert fanin.exact_counts.unresolved_uncertainties == 1
    assert fanin.exact_counts.blockers == 1


def test_exact_structured_conflict_has_no_winner() -> None:
    submissions = {
        "unit-a": _submission(1, fact_value=2),
        "unit-b": _submission(2, fact_value=3),
    }
    fanin = _fanin(
        ["unit-a", "unit-b"],
        submissions,
        keys={"unit-a": ("api_version",), "unit-b": ("api_version",)},
    )

    assert fanin.exact_counts.structured_conflicts == 1
    conflict = fanin.structured_conflicts[0]
    assert conflict.fact_key == "api_version"
    assert {variant.fact_value_json for variant in conflict.variants} == {"2", "3"}
    assert not hasattr(conflict, "winner")


def test_exact_duplicate_fact_value_is_not_a_conflict() -> None:
    submissions = {
        "unit-a": _submission(1, fact_value=2),
        "unit-b": _submission(2, fact_value=2),
    }
    fanin = _fanin(
        ["unit-a", "unit-b"],
        submissions,
        keys={"unit-a": ("api_version",), "unit-b": ("api_version",)},
    )
    assert fanin.exact_counts.structured_conflicts == 0
    assert fanin.exact_counts.exact_duplicates == 1
    assert fanin.exact_duplicates[0].fact_key == "api_version"
    assert fanin.exact_duplicates[0].fact_value_json == "2"


def test_fact_keys_must_be_assignment_provided() -> None:
    with pytest.raises(FanInValidationError, match="assignment-provided"):
        _fanin(["unit-a"], {"unit-a": _submission(1)})
    with pytest.raises(FanInValidationError, match="not assignment-provided"):
        _fanin(
            ["unit-a"],
            {"unit-a": _submission(1)},
            keys={"unit-a": ("different_key",)},
        )


def test_evidence_requires_exact_source_hash() -> None:
    submission = _submission(1)
    payload = submission.model_dump(mode="python")
    evidence = list(payload["evidence"])
    evidence[0]["source_hash"] = None
    payload["evidence"] = tuple(evidence)
    unhashed = EvidenceSubmissionV1.model_validate(payload)
    with pytest.raises(FanInValidationError, match="lacks exact source_hash"):
        _fanin(
            ["unit-a"],
            {"unit-a": unhashed},
            keys={"unit-a": ("api_version",)},
        )


def test_order_invariance_covers_units_conflicts_and_hashes() -> None:
    first = _submission(1, fact_value=2)
    second = _submission(2, fact_value=3)
    keys = {"unit-a": ("api_version",), "unit-b": ("api_version",)}
    forward = _fanin(
        ["unit-b", "unit-a"],
        OrderedDict((("unit-a", first), ("unit-b", second))),
        keys=keys,
    )
    reversed_input = _fanin(
        ["unit-a", "unit-b"],
        OrderedDict((("unit-b", second), ("unit-a", first))),
        keys=keys,
    )
    assert forward.model_dump(mode="json") == reversed_input.model_dump(mode="json")


def test_retrieval_pointers_preserve_submission_and_full_evidence_identity() -> None:
    fanin = _fanin(
        ["unit-a"],
        {"unit-a": _submission(1)},
        keys={"unit-a": ("api_version",)},
    )
    refs = {(item.kind, item.ref, item.hash) for item in fanin.evidence_retrievals}
    summary = fanin.submission_summaries[0]
    assert ("submission", summary.submission_ref, summary.submission_hash) in refs
    assert ("full_evidence", "full:1", _hash("e")) in refs
    assert fanin.has_more is True


def test_four_provider_neutral_producer_profiles_share_one_shape() -> None:
    submissions = {
        "execution": _submission(1, backend_kind="soma_durable_run"),
        "retrieval": _submission(2, backend_kind="retrieval_worker"),
        "scout": _submission(3, backend_kind="scout_worker"),
        "reasoning": _submission(4, backend_kind="soma_reasoning"),
    }
    keys = {unit: ("api_version",) for unit in submissions}
    fanin = _fanin(list(submissions), submissions, keys=keys)
    assert {item.backend_kind for item in fanin.submission_summaries} == {
        "soma_durable_run",
        "retrieval_worker",
        "scout_worker",
        "soma_reasoning",
    }
    assert fanin.exact_counts.submissions == 4


def test_large_compact_fanin_externalizes_prose_before_hard_ceiling() -> None:
    expected = [f"unit-{index:02d}" for index in range(32)]
    submissions = {
        unit: _submission(
            index + 1,
            fact_key=None,
            summary=("x" * 1000),
        )
        for index, unit in enumerate(expected)
    }
    fanin = _fanin(expected, submissions)
    assert fanin.response_bytes == fanin.serialized_bytes
    assert fanin.response_bytes <= FANIN_HARD_CEILING_BYTES
    assert fanin.truncated is True
    assert fanin.has_more is True
    assert all(item.executive_summary == "" for item in fanin.submission_summaries)
    assert fanin.response_bytes > 0
    assert FANIN_NORMAL_TARGET_BYTES < FANIN_HARD_CEILING_BYTES


def test_unexpected_submission_is_rejected() -> None:
    with pytest.raises(FanInValidationError, match="unexpected unit"):
        _fanin(
            ["unit-a"],
            {"unit-b": _submission(1, fact_key=None)},
        )
