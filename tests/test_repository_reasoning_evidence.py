from __future__ import annotations

import hashlib

import pytest

from soma.reasoning.repository_evidence import (
    RepositoryEvidenceError,
    RepositoryReasoningClaimV1,
    RepositoryReasoningPayloadV1,
    RepositorySourceLocatorV1,
    build_evidence_submission,
    resolve_source_locator,
    semantic_output_schema,
    validate_semantic_mechanics,
)
from soma.worker_evidence.models import EvidenceWorkIdentityV1


class FrozenSources:
    def __init__(self, sources: dict[str, bytes]):
        self.sources = sources

    def load(self, source_path: str) -> bytes:
        if source_path not in self.sources:
            raise RepositoryEvidenceError(f"unknown frozen source: {source_path}")
        return self.sources[source_path]


def _payload(claim: RepositoryReasoningClaimV1) -> RepositoryReasoningPayloadV1:
    return RepositoryReasoningPayloadV1(
        submission_disposition="complete",
        executive_summary="summary",
        claims=(claim,),
    )


def test_mechanical_validation_does_not_judge_semantic_support() -> None:
    loader = FrozenSources({"module.py": b"alpha\nbeta\ngamma\n"})
    claim = RepositoryReasoningClaimV1(
        claim_id="c1",
        claim_class="observation",
        statement="This is deliberately not proven by alpha.",
        evidence_locations=(
            RepositorySourceLocatorV1(source_path="module.py", start_line=1, end_line=1),
        ),
    )
    validate_semantic_mechanics(_payload(claim), loader)


def test_locator_materializes_exact_frozen_lines_and_hash() -> None:
    body = b"one\ntwo\nthree\nfour\n"
    loader = FrozenSources({"src/example.py": body})
    path, digest, selected = resolve_source_locator(
        loader,
        RepositorySourceLocatorV1(source_path="src/example.py", start_line=2, end_line=3),
    )
    assert path == "src/example.py"
    assert digest == hashlib.sha256(body).hexdigest()
    assert selected == "two\nthree"


def test_locator_rejects_escape_and_out_of_range() -> None:
    with pytest.raises(ValueError):
        RepositorySourceLocatorV1(source_path="../secret.txt", start_line=1, end_line=1)
    loader = FrozenSources({"x.py": b"one\ntwo\n"})
    with pytest.raises(RepositoryEvidenceError, match="exceeds line count"):
        resolve_source_locator(
            loader,
            RepositorySourceLocatorV1(source_path="x.py", start_line=1, end_line=3),
        )


def test_long_worker_selected_range_is_mechanically_valid() -> None:
    body = "\n".join(f"line-{index}" for index in range(1, 31)).encode("utf-8")
    claim = RepositoryReasoningClaimV1(
        claim_id="wide",
        claim_class="inference",
        statement="Worker chose a broad source range.",
        evidence_locations=(
            RepositorySourceLocatorV1(source_path="wide.py", start_line=1, end_line=30),
        ),
    )
    validate_semantic_mechanics(_payload(claim), FrozenSources({"wide.py": body}))


def test_provider_schema_is_strict_without_semantic_quality_rules() -> None:
    schema = semantic_output_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    locator = schema["$defs"]["RepositorySourceLocatorV1"]
    assert locator["additionalProperties"] is False
    assert set(locator["required"]) == set(locator["properties"])


def test_submission_is_support_only_and_preserves_uncited_claims() -> None:
    body = b"first\nsecond\nthird\n"
    loader = FrozenSources({"src/a.py": body})
    cited = RepositoryReasoningClaimV1(
        claim_id="c1",
        claim_class="negative_finding",
        subject_key="runtime.behavior",
        statement="Worker conclusion.",
        evidence_locations=(
            RepositorySourceLocatorV1(source_path="src/a.py", start_line=2, end_line=3),
        ),
    )
    submission = build_evidence_submission(
        payload=_payload(cited),
        loader=loader,
        source_revision_ref="git:0123456789abcdef0123456789abcdef01234567",
        work_identity=EvidenceWorkIdentityV1(task_id="task_1", backend_ref="reasoning_1"),
        assignment_ref="assignment:1",
        assignment_hash=hashlib.sha256(b"assignment").hexdigest(),
        backend_kind="soma_reasoning",
        provider="fake",
        model_or_profile="fake",
    )
    evidence = submission.evidence[0]
    assert evidence.source_hash == hashlib.sha256(body).hexdigest()
    assert evidence.excerpt == "second\nthird"
    assert submission.claims[0].supports_evidence_ids == (evidence.evidence_id,)
    assert submission.claims[0].opposes_evidence_ids == ()

    uncited = cited.model_copy(update={"claim_id": "c2", "evidence_locations": ()})
    uncited_submission = build_evidence_submission(
        payload=_payload(uncited),
        loader=FrozenSources({}),
        source_revision_ref="git:0123456789abcdef0123456789abcdef01234567",
        work_identity=EvidenceWorkIdentityV1(task_id="task_2", backend_ref="reasoning_2"),
        assignment_ref="assignment:2",
        assignment_hash=hashlib.sha256(b"assignment-2").hexdigest(),
        backend_kind="soma_reasoning",
        provider=None,
        model_or_profile=None,
    )
    assert uncited_submission.claims[0].supports_evidence_ids == ()
    assert uncited_submission.evidence == ()
