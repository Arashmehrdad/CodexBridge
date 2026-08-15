from __future__ import annotations

import hashlib

import pytest

from soma.repo_patch_repair import (
    AUTHORED_SPAN_SCHEMA_VERSION,
    TRAILING_COMMIT_TITLE_RULE_ID,
    TRAILING_VIEW_RULE_ID,
    canonical_direct_repair_primitive,
    derive_authored_span_provenance,
    detect_transport_leak_candidates,
)


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("exact_text", "exact_text"),
        ("replace_exact", "exact_text"),
        ("modify", "exact_text"),
        ("line_range", "line_range"),
        ("replace_lines", "line_range"),
        ("python_ast", "python_ast"),
        ("ast_python", "python_ast"),
    ],
)
def test_direct_repair_aliases_collapse_to_three_public_primitives(alias: str, expected: str) -> None:
    assert canonical_direct_repair_primitive(alias) == expected


def test_single_direct_edit_owns_only_certainly_changed_candidate_bytes() -> None:
    baseline = b"prefix old suffix\n"
    candidate = b"prefix new}],\"view\":\"full suffix\n"

    evidence = derive_authored_span_provenance(
        baseline_bytes=baseline,
        candidate_bytes=candidate,
        operation_index=4,
        operation_type="exact_text",
        operation_count=1,
    )

    assert evidence.schema_version == AUTHORED_SPAN_SCHEMA_VERSION
    assert evidence.operation_index == 4
    assert evidence.primitive == "exact_text"
    assert evidence.disposition == "owned"
    assert evidence.candidate_start_byte is not None
    assert evidence.candidate_end_byte is not None
    span = candidate[evidence.candidate_start_byte : evidence.candidate_end_byte]
    assert span == b"new}],\"view\":\"full"
    assert evidence.candidate_span_sha256 == hashlib.sha256(span).hexdigest()


@pytest.mark.parametrize("primitive", ["exact_text", "line_range", "python_ast"])
def test_multi_operation_composition_is_explicitly_ambiguous(primitive: str) -> None:
    evidence = derive_authored_span_provenance(
        baseline_bytes=b"value = 1\n",
        candidate_bytes=b"value = 2\n",
        operation_index=0,
        operation_type=primitive,
        operation_count=2,
    )

    assert evidence.disposition == "ambiguous_composition"
    assert evidence.candidate_start_byte is None
    assert evidence.candidate_end_byte is None
    assert evidence.candidate_span_sha256 is None


def test_unsupported_primitive_cannot_claim_authored_bytes() -> None:
    evidence = derive_authored_span_provenance(
        baseline_bytes=b"value = 1\n",
        candidate_bytes=b"value = 2\n",
        operation_index=0,
        operation_type="unified_diff",
        operation_count=1,
    )

    assert evidence.disposition == "unsupported_primitive"
    assert evidence.candidate_start_byte is None


def test_preexisting_suspicious_bytes_are_outside_owned_changed_span() -> None:
    baseline = b"fixture = '}],\"view\":\"full'\nvalue = 1\n"
    candidate = b"fixture = '}],\"view\":\"full'\nvalue = 2\n"
    evidence = derive_authored_span_provenance(
        baseline_bytes=baseline,
        candidate_bytes=candidate,
        operation_index=0,
        operation_type="exact_text",
        operation_count=1,
    )

    assert evidence.disposition == "owned"
    assert evidence.candidate_start_byte is not None
    assert evidence.candidate_start_byte > candidate.index(b'}],\"view\"')


def test_no_changed_span_never_claims_ownership() -> None:
    evidence = derive_authored_span_provenance(
        baseline_bytes=b"same\n",
        candidate_bytes=b"same\n",
        operation_index=0,
        operation_type="exact_text",
        operation_count=1,
    )

    assert evidence.disposition == "no_changed_span"
    assert evidence.candidate_span_sha256 is None


def test_provenance_requires_positive_operation_count() -> None:
    with pytest.raises(ValueError, match="operation_count"):
        derive_authored_span_provenance(
            baseline_bytes=b"a\n",
            candidate_bytes=b"b\n",
            operation_index=0,
            operation_type="exact_text",
            operation_count=0,
        )


def _owned(candidate: bytes, baseline: bytes = b"safe\n"):
    return derive_authored_span_provenance(
        baseline_bytes=baseline,
        candidate_bytes=candidate,
        operation_index=0,
        operation_type="exact_text",
        operation_count=1,
    )


@pytest.mark.parametrize(
    ("candidate", "rule_id", "deleted"),
    [
        (
            b'assert ready == "ok"}],"view":"full\nnext_call()\n',
            TRAILING_VIEW_RULE_ID,
            b'}],"view":"full',
        ),
        (
            b'"WorkPackage"}],"commit_title":"G1.2 additive Company Kernel graph schema v2\n"Next",\n',
            TRAILING_COMMIT_TITLE_RULE_ID,
            b'}],"commit_title":"G1.2 additive Company Kernel graph schema v2',
        ),
    ],
)
def test_recovered_transport_signatures_are_detected_exactly(
    candidate: bytes, rule_id: str, deleted: bytes
) -> None:
    provenance = _owned(candidate)
    hits = detect_transport_leak_candidates(
        candidate_bytes=candidate,
        provenance=provenance,
    )

    assert len(hits) == 1
    hit = hits[0]
    assert hit.rule_id == rule_id
    assert candidate[hit.deletion_start_byte : hit.deletion_end_byte] == deleted
    assert hit.operation_index == 0
    assert hit.primitive == "exact_text"


@pytest.mark.parametrize(
    "lookalike",
    [
        b'assert ready == "ok"}],"commit_description":"not-a-v1-rule\n',
        b'assert ready == "ok"}],"expected_sha256":"abc\n',
        b'assert ready == "ok"}],"View":"full\n',
    ],
)
def test_unreviewed_outer_field_lookalikes_do_not_match(lookalike: bytes) -> None:
    hits = detect_transport_leak_candidates(
        candidate_bytes=lookalike,
        provenance=_owned(lookalike),
    )

    assert hits == ()


def test_preexisting_signature_outside_owned_span_is_not_detected() -> None:
    baseline = b'fixture = "}],\\"view\\":\\"full"\nvalue = 1\n'
    candidate = b'fixture = "}],\\"view\\":\\"full"\nvalue = 2\n'
    provenance = derive_authored_span_provenance(
        baseline_bytes=baseline,
        candidate_bytes=candidate,
        operation_index=0,
        operation_type="exact_text",
        operation_count=1,
    )

    assert detect_transport_leak_candidates(
        candidate_bytes=candidate,
        provenance=provenance,
    ) == ()


def test_ambiguous_multi_operation_provenance_disables_detection() -> None:
    candidate = b'assert ready == "ok"}],"view":"full\n'
    provenance = derive_authored_span_provenance(
        baseline_bytes=b'assert ready == "ok"\n',
        candidate_bytes=candidate,
        operation_index=0,
        operation_type="exact_text",
        operation_count=2,
    )

    assert provenance.disposition == "ambiguous_composition"
    assert detect_transport_leak_candidates(
        candidate_bytes=candidate,
        provenance=provenance,
    ) == ()


def test_multiple_reviewed_signatures_remain_multiple_candidates() -> None:
    candidate = (
        b'first = 1}],"view":"full '
        b'}],"commit_title":"second\n'
    )
    hits = detect_transport_leak_candidates(
        candidate_bytes=candidate,
        provenance=_owned(candidate),
    )

    assert len(hits) == 2
    assert {hit.rule_id for hit in hits} == {
        TRAILING_VIEW_RULE_ID,
        TRAILING_COMMIT_TITLE_RULE_ID,
    }
