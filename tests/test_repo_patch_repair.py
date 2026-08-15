from __future__ import annotations

import hashlib
import random

import pytest

from soma.repo_candidate_validation import validate_python_candidate
from soma.repo_patch_repair import (
    AUTHORED_SPAN_SCHEMA_VERSION,
    TRAILING_COMMIT_TITLE_RULE_ID,
    TRAILING_VIEW_RULE_ID,
    PATCH_REPAIR_PROPOSAL_SCHEMA_VERSION,
    TransportLeakCandidateV1,
    apply_transport_deletion,
    build_patch_repair_proposal,
    canonical_direct_repair_primitive,
    derive_authored_span_provenance,
    detect_transport_leak_candidates,
    prove_python_logical_line_deletion,
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
def test_direct_repair_aliases_collapse_to_three_public_primitives(
    alias: str, expected: str
) -> None:
    assert canonical_direct_repair_primitive(alias) == expected


def test_single_direct_edit_owns_only_certainly_changed_candidate_bytes() -> None:
    baseline = b"prefix old suffix\n"
    candidate = b'prefix new}],"view":"full suffix\n'

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
    assert span == b'new}],"view":"full'
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
    baseline = b'fixture = \'}],"view":"full\'\nvalue = 1\n'
    candidate = b'fixture = \'}],"view":"full\'\nvalue = 2\n'
    evidence = derive_authored_span_provenance(
        baseline_bytes=baseline,
        candidate_bytes=candidate,
        operation_index=0,
        operation_type="exact_text",
        operation_count=1,
    )

    assert evidence.disposition == "owned"
    assert evidence.candidate_start_byte is not None
    assert evidence.candidate_start_byte > candidate.index(b'}],"view"')


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

    assert (
        detect_transport_leak_candidates(
            candidate_bytes=candidate,
            provenance=provenance,
        )
        == ()
    )


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
    assert (
        detect_transport_leak_candidates(
            candidate_bytes=candidate,
            provenance=provenance,
        )
        == ()
    )


def test_multiple_reviewed_signatures_remain_multiple_candidates() -> None:
    candidate = b'first = 1}],"view":"full }],"commit_title":"second\n'
    hits = detect_transport_leak_candidates(
        candidate_bytes=candidate,
        provenance=_owned(candidate),
    )

    assert len(hits) == 2
    assert {hit.rule_id for hit in hits} == {
        TRAILING_VIEW_RULE_ID,
        TRAILING_COMMIT_TITLE_RULE_ID,
    }


LEAK = b'}],"view":"full'


def _deletion_for_injected_leak(
    repaired: bytes, cut: int
) -> tuple[bytes, TransportLeakCandidateV1]:
    candidate = repaired[:cut] + LEAK + repaired[cut:]
    deletion = TransportLeakCandidateV1(
        rule_id=TRAILING_VIEW_RULE_ID,
        operation_index=0,
        primitive="exact_text",
        deletion_start_byte=cut,
        deletion_end_byte=cut + len(LEAK),
        deleted_bytes_sha256=hashlib.sha256(LEAK).hexdigest(),
        deleted_excerpt_bounded=LEAK.decode(),
    )
    return candidate, deletion


def _prove_injected(repaired: bytes, cut: int):
    candidate, deletion = _deletion_for_injected_leak(repaired, cut)
    proof = prove_python_logical_line_deletion(
        path="fixture.py",
        candidate_bytes=candidate,
        deletion=deletion,
    )
    assert apply_transport_deletion(candidate, deletion) == repaired
    return proof


def test_incident_b_passes_logical_newline_gate() -> None:
    baseline = (
        b"def check(conn):\n"
        b'    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"\n'
        b'    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []\n'
    )
    marker = b'}],"view":"full'
    cut = baseline.index(b"\n", baseline.index(b"integrity_check"))
    candidate = baseline[:cut] + marker + baseline[cut:]
    provenance = derive_authored_span_provenance(
        baseline_bytes=baseline,
        candidate_bytes=candidate,
        operation_index=0,
        operation_type="exact_text",
        operation_count=1,
    )
    hits = detect_transport_leak_candidates(
        candidate_bytes=candidate,
        provenance=provenance,
    )

    assert len(hits) == 1
    proof = prove_python_logical_line_deletion(
        path="incident_b.py",
        candidate_bytes=candidate,
        deletion=hits[0],
    )
    assert proof.passed is True
    assert proof.next_token_name == "NEWLINE"
    assert proof.reason == "logical_newline"


def test_incident_a_adjacent_string_trap_fails_on_nl() -> None:
    intended = (
        b"__all__ = [\n"
        b'    "SettledSatisfactionV1",\n'
        b'    "WorkPackage",\n'
        b'    "WorkPackageAttempt",\n'
        b'    "canonical_hash",\n'
        b"]\n"
    )
    bad_prefix = b'    "WorkPackage"'
    start = intended.index(b'    "WorkPackage",')
    after_entry = start + len(bad_prefix)
    candidate = (
        intended[:start]
        + bad_prefix
        + b'}],"commit_title":"G1.2 additive Company Kernel graph schema v2'
        + intended[after_entry + 1 :]
    )
    provenance = derive_authored_span_provenance(
        baseline_bytes=intended,
        candidate_bytes=candidate,
        operation_index=0,
        operation_type="exact_text",
        operation_count=1,
    )
    hits = detect_transport_leak_candidates(
        candidate_bytes=candidate,
        provenance=provenance,
    )

    assert len(hits) == 1
    proof = prove_python_logical_line_deletion(
        path="incident_a.py",
        candidate_bytes=candidate,
        deletion=hits[0],
    )
    assert proof.repaired_candidate_valid is True
    assert proof.passed is False
    assert proof.next_token_name == "NL"
    assert proof.reason == "next_token_not_logical_newline"


@pytest.mark.parametrize(
    ("repaired", "cut_marker", "expected_reason"),
    [
        (b'value = func(\n    "x"\n)\n', b'"x"', "next_token_not_logical_newline"),
        (b"values = [\n    1\n]\n", b"1\n", "next_token_not_logical_newline"),
        (b'values = {\n    "a": 1\n}\n', b"1\n", "next_token_not_logical_newline"),
        (b"values = (\n    1\n)\n", b"1\n", "next_token_not_logical_newline"),
        (b"values = {\n    1\n}\n", b"1\n", "next_token_not_logical_newline"),
        (
            b"values = [x\n    for x in range(3)\n]\n",
            b"x\n",
            "next_token_not_logical_newline",
        ),
        (b"value = 1 + 2\n", b"1", "next_token_not_logical_newline"),
        (b"value = obj.attr\n", b"obj", "next_token_not_logical_newline"),
        (b"value = obj[0]\n", b"obj", "next_token_not_logical_newline"),
        (b"value = 1 \\\n    + 2\n", b"1 ", "non_horizontal_bytes_after_cut"),
        (b"value = 1  # comment\n", b"1", "next_token_not_logical_newline"),
        (b"value = 1; other = 2\n", b"1", "next_token_not_logical_newline"),
        (b'value = f"hello {name}"\n', b"hello ", "next_token_not_logical_newline"),
    ],
)
def test_structural_hazards_are_rejected(
    repaired: bytes, cut_marker: bytes, expected_reason: str
) -> None:
    marker_start = repaired.index(cut_marker)
    cut = marker_start + len(cut_marker.rstrip(b"\n"))
    proof = _prove_injected(repaired, cut)

    assert proof.passed is False
    assert proof.reason == expected_reason


@pytest.mark.parametrize(
    "repaired",
    [
        "پیام = 'سلام'\n".encode(),
        b"value = 1\r\n",
        b"value = 1",
        b"value = 1   \n",
    ],
)
def test_complete_logical_line_variants_pass(repaired: bytes) -> None:
    newline_positions = [
        pos for pos in (repaired.find(b"\r"), repaired.find(b"\n")) if pos >= 0
    ]
    cut = min(newline_positions) if newline_positions else len(repaired)
    if cut and repaired[:cut].endswith(b"   "):
        cut -= 3
    proof = _prove_injected(repaired, cut)

    assert proof.passed is True
    assert proof.next_token_name == "NEWLINE"


def test_fixed_seed_adversarial_corpus_is_deterministic_and_bounded() -> None:
    rng = random.Random(20260815)
    accepted = 0
    rejected = 0
    for index in range(64):
        value = rng.randrange(1, 100000)
        if index % 2 == 0:
            repaired = f"value_{index} = {value}\n".encode()
            proof = _prove_injected(repaired, repaired.index(b"\n"))
            assert proof.passed is True
            accepted += 1
        else:
            repaired = f"values_{index} = [\n    {value}\n]\n".encode()
            cut = repaired.index(b"\n", repaired.index(str(value).encode()))
            proof = _prove_injected(repaired, cut)
            assert proof.passed is False
            assert proof.next_token_name == "NL"
            rejected += 1

    assert (accepted, rejected) == (32, 32)


def _proposal_inputs(baseline: bytes, candidate: bytes):
    validation = validate_python_candidate(
        path="proposal.py",
        baseline_bytes=baseline,
        candidate_bytes=candidate,
    )
    provenance = derive_authored_span_provenance(
        baseline_bytes=baseline,
        candidate_bytes=candidate,
        operation_index=0,
        operation_type="exact_text",
        operation_count=1,
    )
    return validation, provenance


def test_incident_b_builds_one_deterministic_repair_proposal() -> None:
    baseline = b'assert ready == "ok"\nnext_call()\n'
    cut = baseline.index(b"\n")
    candidate = baseline[:cut] + LEAK + baseline[cut:]
    validation, provenance = _proposal_inputs(baseline, candidate)

    first, repaired = build_patch_repair_proposal(
        path="proposal.py",
        candidate_bytes=candidate,
        candidate_validation=validation,
        provenance=provenance,
        created_at="2026-08-15T00:00:00Z",
    )
    replay, replay_bytes = build_patch_repair_proposal(
        path="proposal.py",
        candidate_bytes=candidate,
        candidate_validation=validation,
        provenance=provenance,
        created_at="2026-08-15T00:00:01Z",
    )

    assert first is not None
    assert replay is not None
    assert repaired == baseline
    assert replay_bytes == baseline
    assert first.schema_version == PATCH_REPAIR_PROPOSAL_SCHEMA_VERSION
    assert first.proposal_id == replay.proposal_id
    assert first.rule_id == TRAILING_VIEW_RULE_ID
    assert first.logical_line_gate.passed is True
    assert first.python_validation_before.candidate_disposition == "invalid"
    assert first.python_validation_after.candidate_disposition == "valid"
    assert (
        first.repaired_payload_descriptor.sha256 == hashlib.sha256(baseline).hexdigest()
    )
    assert first.repaired_payload_descriptor.size_bytes == len(baseline)


def test_incident_a_does_not_build_repair_proposal_even_when_deletion_compiles() -> (
    None
):
    baseline = b'items = [\n    "WorkPackage",\n    "Next",\n]\n'
    start = baseline.index(b'    "WorkPackage",')
    bad_prefix = b'    "WorkPackage"'
    candidate = (
        baseline[:start]
        + bad_prefix
        + b'}],"commit_title":"unsafe'
        + baseline[start + len(bad_prefix) + 1 :]
    )
    validation, provenance = _proposal_inputs(baseline, candidate)

    proposal, repaired = build_patch_repair_proposal(
        path="proposal.py",
        candidate_bytes=candidate,
        candidate_validation=validation,
        provenance=provenance,
        created_at="2026-08-15T00:00:00Z",
    )

    assert validation.regression_detected is True
    assert proposal is None
    assert repaired is None


def test_multiple_plausible_transport_deletions_emit_no_proposal() -> None:
    baseline = b"value = 1\n"
    candidate = b'value = 1}],"view":"full }],"commit_title":"also\n'
    validation, provenance = _proposal_inputs(baseline, candidate)

    proposal, repaired = build_patch_repair_proposal(
        path="proposal.py",
        candidate_bytes=candidate,
        candidate_validation=validation,
        provenance=provenance,
        created_at="2026-08-15T00:00:00Z",
    )

    assert proposal is None
    assert repaired is None


def test_non_regression_never_builds_proposal() -> None:
    baseline = b"value = (\n"
    candidate = b'value = (}],"view":"full\n'
    validation, provenance = _proposal_inputs(baseline, candidate)

    proposal, repaired = build_patch_repair_proposal(
        path="proposal.py",
        candidate_bytes=candidate,
        candidate_validation=validation,
        provenance=provenance,
        created_at="2026-08-15T00:00:00Z",
    )

    assert validation.regression_detected is False
    assert proposal is None
    assert repaired is None


def test_proposal_deleted_excerpt_is_bounded() -> None:
    baseline = b'assert ready == "ok"\n'
    cut = baseline.index(b"\n")
    leak = b'}],"view":"' + (b"x" * 2000)
    candidate = baseline[:cut] + leak + baseline[cut:]
    validation, provenance = _proposal_inputs(baseline, candidate)

    proposal, repaired = build_patch_repair_proposal(
        path="proposal.py",
        candidate_bytes=candidate,
        candidate_validation=validation,
        provenance=provenance,
        created_at="2026-08-15T00:00:00Z",
    )

    assert proposal is not None
    assert repaired == baseline
    assert len(proposal.deleted_excerpt_bounded) == 256
