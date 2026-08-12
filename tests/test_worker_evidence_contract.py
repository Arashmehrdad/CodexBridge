"""G2.1 bounded EvidenceSubmissionV1 contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from soma.worker_evidence import (
    EVIDENCE_SUBMISSION_HARD_CEILING_BYTES,
    EVIDENCE_SUBMISSION_NORMAL_TARGET_BYTES,
    EVIDENCE_SUBMISSION_SCHEMA_VERSION,
    MAX_EVIDENCE_ARTIFACTS,
    MAX_EVIDENCE_BLOCKERS,
    MAX_EVIDENCE_CLAIMS,
    MAX_EVIDENCE_EXCERPT_CHARACTERS,
    MAX_EVIDENCE_PROVENANCE_REFS,
    MAX_EVIDENCE_RECORDS,
    MAX_EVIDENCE_UNCERTAINTIES,
    MAX_EXECUTIVE_SUMMARY_UTF8_BYTES,
    EvidenceArtifactV1,
    EvidenceAssignmentV1,
    EvidenceBlockerV1,
    EvidenceClaimV1,
    EvidenceHashedReferenceV1,
    EvidenceProducerV1,
    EvidenceRecordV1,
    EvidenceSubmissionV1,
    EvidenceUncertaintyV1,
    EvidenceWorkIdentityV1,
)


MISSION_ID = "mission_" + "1" * 24
PLAN_ID = "planrev_" + "2" * 24
PACKAGE_ID = "workpkg_" + "3" * 24
OUTCOME_ID = "outcome_" + "4" * 24
ATTEMPT_ID = "wpattempt_" + "5" * 24


def _hash(character: str) -> str:
    return character * 64


def _base_submission(**overrides) -> EvidenceSubmissionV1:
    evidence = EvidenceRecordV1(
        evidence_id="evidence-1",
        source_kind="repository_file",
        source_ref="repo:soma:soma/tasks/models.py",
        source_hash=_hash("a"),
        locator="lines:1-20",
        excerpt="Task is canonical lifecycle authority.",
        fact_key="task_authority",
        fact_value="canonical",
    )
    claim = EvidenceClaimV1(
        claim_id="claim-1",
        claim_class="observation",
        subject_key="task_authority",
        statement="The source identifies Task as canonical lifecycle authority.",
        supports_evidence_ids=(evidence.evidence_id,),
    )
    values = {
        "submission_id": "submission-1",
        "work_identity": EvidenceWorkIdentityV1(
            mission_id=MISSION_ID,
            plan_revision_id=PLAN_ID,
            work_package_id=PACKAGE_ID,
            outcome_id=OUTCOME_ID,
            attempt_id=ATTEMPT_ID,
            task_id="task_fixture",
            backend_ref="backend_fixture",
        ),
        "assignment": EvidenceAssignmentV1(
            contract_ref="assignment:fixture",
            contract_hash=_hash("b"),
        ),
        "producer": EvidenceProducerV1(
            backend_kind="reasoning",
            provider="fake",
            model_or_profile="deterministic",
            adapter_id="fake-v1",
        ),
        "submission_disposition": "complete",
        "executive_summary": "One bounded source-grounded finding.",
        "claims": (claim,),
        "evidence": (evidence,),
        "artifacts": (
            EvidenceArtifactV1(
                artifact_ref="artifact:result",
                artifact_hash=_hash("c"),
                media_type="application/json",
                role="result",
            ),
        ),
        "provenance": (
            EvidenceHashedReferenceV1(ref="provenance:event-1", hash=_hash("d")),
        ),
        "full_evidence_retrieval": (
            EvidenceHashedReferenceV1(ref="retrieval:full-1", hash=_hash("e")),
        ),
    }
    values.update(overrides)
    return EvidenceSubmissionV1(**values)


def test_frozen_evidence_bounds_are_exact() -> None:
    assert EVIDENCE_SUBMISSION_SCHEMA_VERSION == "evidence_submission.v1"
    assert EVIDENCE_SUBMISSION_NORMAL_TARGET_BYTES == 12 * 1024
    assert EVIDENCE_SUBMISSION_HARD_CEILING_BYTES == 32 * 1024
    assert MAX_EXECUTIVE_SUMMARY_UTF8_BYTES == 1024
    assert MAX_EVIDENCE_CLAIMS == 12
    assert MAX_EVIDENCE_RECORDS == 24
    assert MAX_EVIDENCE_ARTIFACTS == 12
    assert MAX_EVIDENCE_UNCERTAINTIES == 12
    assert MAX_EVIDENCE_BLOCKERS == 8
    assert MAX_EVIDENCE_EXCERPT_CHARACTERS == 512
    assert MAX_EVIDENCE_PROVENANCE_REFS == 64


def test_common_envelope_accepts_multiple_producer_profiles() -> None:
    profiles = (
        EvidenceProducerV1(
            backend_kind="durable_command", model_or_profile="powershell"
        ),
        EvidenceProducerV1(backend_kind="retrieval", adapter_id="repo-reader"),
        EvidenceProducerV1(
            backend_kind="reasoning",
            provider="fake",
            model_or_profile="scout",
        ),
        EvidenceProducerV1(
            backend_kind="reasoning",
            provider="fake",
            model_or_profile="strong",
            native_session_ref="session:provider-native-tree",
        ),
    )

    submissions = [_base_submission(producer=producer) for producer in profiles]

    assert all(
        submission.schema_version == "evidence_submission.v1"
        for submission in submissions
    )
    assert all(
        submission.serialized_bytes <= EVIDENCE_SUBMISSION_HARD_CEILING_BYTES
        for submission in submissions
    )


def test_claim_classes_are_explicit_not_generic_confidence() -> None:
    for claim_class in (
        "observation",
        "inference",
        "recommendation",
        "negative_finding",
    ):
        claim = EvidenceClaimV1(
            claim_id=f"claim-{claim_class}",
            claim_class=claim_class,
            statement="bounded statement",
        )
        assert claim.claim_class == claim_class

    with pytest.raises(ValidationError):
        EvidenceClaimV1(
            claim_id="claim-confidence",
            claim_class="confidence",
            statement="not a valid evidence claim class",
        )


def test_executive_summary_enforces_utf8_bytes_not_only_characters() -> None:
    assert len(("é" * 512).encode("utf-8")) == 1024
    accepted = _base_submission(executive_summary="é" * 512)
    assert accepted.executive_summary == "é" * 512

    with pytest.raises(ValidationError, match="UTF-8 bytes"):
        _base_submission(executive_summary="é" * 513)


def test_claim_and_record_count_bounds_are_enforced() -> None:
    claims = tuple(
        EvidenceClaimV1(
            claim_id=f"claim-{index}",
            claim_class="observation",
            statement="bounded",
        )
        for index in range(MAX_EVIDENCE_CLAIMS + 1)
    )
    with pytest.raises(ValidationError):
        _base_submission(claims=claims, evidence=())

    records = tuple(
        EvidenceRecordV1(
            evidence_id=f"evidence-{index}",
            source_kind="fixture",
            source_ref=f"ref:{index}",
        )
        for index in range(MAX_EVIDENCE_RECORDS + 1)
    )
    with pytest.raises(ValidationError):
        _base_submission(claims=(), evidence=records)


def test_other_frozen_collection_bounds_are_enforced() -> None:
    artifacts = tuple(
        EvidenceArtifactV1(
            artifact_ref=f"artifact:{index}",
            artifact_hash=_hash("a"),
            media_type="text/plain",
            role="evidence",
        )
        for index in range(MAX_EVIDENCE_ARTIFACTS + 1)
    )
    with pytest.raises(ValidationError):
        _base_submission(artifacts=artifacts)

    uncertainties = tuple(
        EvidenceUncertaintyV1(
            uncertainty_id=f"uncertainty-{index}",
            kind="unknown",
            statement="bounded",
        )
        for index in range(MAX_EVIDENCE_UNCERTAINTIES + 1)
    )
    with pytest.raises(ValidationError):
        _base_submission(uncertainties=uncertainties)

    blockers = tuple(
        EvidenceBlockerV1(
            blocker_id=f"blocker-{index}",
            kind="missing_input",
            statement="bounded",
        )
        for index in range(MAX_EVIDENCE_BLOCKERS + 1)
    )
    with pytest.raises(ValidationError):
        _base_submission(blockers=blockers)


def test_excerpt_is_bounded_to_512_characters() -> None:
    assert (
        EvidenceRecordV1(
            evidence_id="evidence-max",
            source_kind="fixture",
            source_ref="fixture:max",
            excerpt="x" * 512,
        ).excerpt
        == "x" * 512
    )

    with pytest.raises(ValidationError):
        EvidenceRecordV1(
            evidence_id="evidence-too-long",
            source_kind="fixture",
            source_ref="fixture:too-long",
            excerpt="x" * 513,
        )


def test_duplicate_ids_and_broken_cross_references_fail_closed() -> None:
    duplicate = EvidenceRecordV1(
        evidence_id="duplicate",
        source_kind="fixture",
        source_ref="fixture:duplicate",
    )
    with pytest.raises(ValidationError, match="evidence IDs"):
        _base_submission(claims=(), evidence=(duplicate, duplicate))

    broken_claim = EvidenceClaimV1(
        claim_id="broken",
        claim_class="observation",
        statement="references missing evidence",
        supports_evidence_ids=("does-not-exist",),
    )
    with pytest.raises(ValidationError, match="unknown evidence IDs"):
        _base_submission(claims=(broken_claim,))


def test_uncertainty_cross_references_are_mechanical() -> None:
    uncertainty = EvidenceUncertaintyV1(
        uncertainty_id="uncertainty-1",
        kind="missing_source",
        statement="A required source is missing.",
        related_claim_ids=("claim-does-not-exist",),
    )
    with pytest.raises(ValidationError, match="unknown claim IDs"):
        _base_submission(uncertainties=(uncertainty,))


def test_producer_is_strict_and_transcripts_cannot_leak_into_envelope() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceProducerV1(
            backend_kind="reasoning",
            provider="fake",
            raw_transcript="forbidden body",
        )

    payload = _base_submission().model_dump(mode="python")
    payload["transcript"] = "full provider transcript"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceSubmissionV1.model_validate(payload)


def test_12_kib_is_target_not_rejection_boundary() -> None:
    claims = tuple(
        EvidenceClaimV1(
            claim_id=f"large-{index}",
            claim_class="observation",
            statement="x" * 3000,
        )
        for index in range(4)
    )
    submission = _base_submission(
        claims=claims, evidence=(), artifacts=(), provenance=()
    )

    assert submission.serialized_bytes > EVIDENCE_SUBMISSION_NORMAL_TARGET_BYTES
    assert submission.serialized_bytes <= EVIDENCE_SUBMISSION_HARD_CEILING_BYTES
    assert submission.within_normal_target is False


def test_32_kib_hard_serialized_ceiling_rejects_oversized_envelope() -> None:
    claims = tuple(
        EvidenceClaimV1(
            claim_id=f"oversized-{index}",
            claim_class="observation",
            statement="x" * 3000,
        )
        for index in range(MAX_EVIDENCE_CLAIMS)
    )

    with pytest.raises(ValidationError, match="hard serialized ceiling"):
        _base_submission(claims=claims, evidence=(), artifacts=(), provenance=())


def test_provenance_ref_bound_is_enforced() -> None:
    provenance = tuple(
        EvidenceHashedReferenceV1(ref=f"provenance:{index}", hash=_hash("f"))
        for index in range(MAX_EVIDENCE_PROVENANCE_REFS + 1)
    )
    with pytest.raises(ValidationError):
        _base_submission(provenance=provenance)
