"""G4.1 pure protected mutation authority/effect contract proofs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from soma.protected_tools import (
    PROTECTED_TOOL_CALL_SCHEMA_VERSION,
    PROTECTED_TOOL_EFFECT_SCHEMA_VERSION,
    ProtectedProviderProvenanceRefV1,
    ProtectedToolCallV1,
    ProtectedToolEffectV1,
)


ATTEMPT_ID = "wpattempt_" + "1" * 24
NOW = datetime(2026, 8, 12, 11, 0, tzinfo=timezone.utc)


def _hash(character: str) -> str:
    return character * 64


def _call(**overrides) -> ProtectedToolCallV1:
    payload = {
        "call_request_id": "protected-call-record-1",
        "task_id": "task-protected-fixture",
        "attempt_id": ATTEMPT_ID,
        "backend_ref": "reasoning-backend:fixture",
        "mandate_ref": "mandate:fixture",
        "mandate_hash": _hash("a"),
        "mandate_version": "v7",
        "project_id": "Project_Protected_Fixture",
        "resource_id": "Resource_Protected_Fixture",
        "scope_generation": 3,
        "capability_ref": "capability:repository-write",
        "capability_hash": _hash("b"),
        "tool_operation_ref": "tool-operation:repo-apply-v1",
        "tool_operation_hash": _hash("c"),
        "resource_key": "repository:d:/github/soma",
        "idempotency_key": "soma-slot:mission-1/package-2/action-3",
        "payload_ref": "payload:patch-123",
        "payload_hash": _hash("d"),
        "expected_task_state_version": 11,
        "expires_at": NOW + timedelta(minutes=15),
        "mutation_class": "repository",
        "provider_provenance_refs": (
            ProtectedProviderProvenanceRefV1(
                ref="provider-trace:alpha",
                hash=_hash("e"),
            ),
        ),
    }
    payload.update(overrides)
    return ProtectedToolCallV1(**payload)


def _effect(**overrides) -> ProtectedToolEffectV1:
    payload = {
        "call_request_id": "protected-call-record-1",
        "request_hash": _call().request_hash,
        "disposition": "acknowledged",
        "external_effect_ref": "repo-commit:abc123",
        "external_effect_hash": _hash("f"),
        "evidence_ref": "evidence:repo-commit-abc123",
        "evidence_hash": _hash("0"),
        "completed_at": NOW + timedelta(minutes=1),
    }
    payload.update(overrides)
    return ProtectedToolEffectV1(**payload)


def test_schema_versions_and_vocabularies_are_frozen() -> None:
    assert _call().schema_version == PROTECTED_TOOL_CALL_SCHEMA_VERSION
    assert _effect().schema_version == PROTECTED_TOOL_EFFECT_SCHEMA_VERSION
    for mutation_class in (
        "repository",
        "external_system",
        "deployment",
        "communication",
        "financial",
        "generic",
    ):
        assert _call(mutation_class=mutation_class).mutation_class == mutation_class
    for disposition in ("prevented", "rejected", "outcome_unknown"):
        effect = _effect(
            disposition=disposition,
            external_effect_ref=None,
            external_effect_hash=None,
        )
        assert effect.disposition == disposition


def test_provider_provenance_and_call_record_id_do_not_move_request_hash() -> None:
    baseline = _call()
    changed = _call(
        call_request_id="protected-call-record-2",
        provider_provenance_refs=(
            ProtectedProviderProvenanceRefV1(
                ref="provider-thread:totally-different",
                hash=_hash("9"),
            ),
            ProtectedProviderProvenanceRefV1(
                ref="provider-call:another-id",
                hash=_hash("8"),
            ),
        ),
    )
    assert changed.request_hash == baseline.request_hash
    assert "provider_provenance_refs" not in baseline.request_identity_payload()
    assert "call_request_id" not in baseline.request_identity_payload()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "task-protected-other"),
        ("attempt_id", "wpattempt_" + "2" * 24),
        ("backend_ref", "reasoning-backend:other"),
        ("mandate_ref", "mandate:other"),
        ("mandate_hash", _hash("1")),
        ("mandate_version", "v8"),
        ("project_id", "Project_Other"),
        ("resource_id", "Resource_Other"),
        ("scope_generation", 4),
        ("capability_ref", "capability:other"),
        ("capability_hash", _hash("2")),
        ("tool_operation_ref", "tool-operation:other"),
        ("tool_operation_hash", _hash("3")),
        ("resource_key", "repository:d:/github/other"),
        ("idempotency_key", "soma-slot:different"),
        ("payload_ref", "payload:other"),
        ("payload_hash", _hash("4")),
        ("expected_task_state_version", 12),
        ("expires_at", NOW + timedelta(minutes=30)),
        ("mutation_class", "external_system"),
    ],
)
def test_every_authority_effect_dimension_moves_request_hash(field: str, value) -> None:
    assert _call(**{field: value}).request_hash != _call().request_hash


def test_invalid_kernel_attempt_hashes_and_naive_expiry_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _call(attempt_id="attempt-not-canonical")
    with pytest.raises(ValidationError):
        _call(payload_hash="not-a-hash")
    with pytest.raises(ValidationError, match="timezone-aware"):
        _call(expires_at=datetime(2026, 8, 12, 11, 0))


def test_provider_provenance_requires_unique_exact_hashed_refs() -> None:
    ref = ProtectedProviderProvenanceRefV1(ref="provider-call:x", hash=_hash("a"))
    with pytest.raises(ValidationError, match="unique"):
        _call(provider_provenance_refs=(ref, ref))


def test_acknowledged_effect_requires_exact_external_effect_and_evidence() -> None:
    acknowledged = _effect()
    assert acknowledged.external_effect_ref == "repo-commit:abc123"
    with pytest.raises(ValidationError, match="acknowledged"):
        _effect(external_effect_ref=None, external_effect_hash=None)
    with pytest.raises(ValidationError):
        _effect(evidence_hash="bad")


def test_prevented_and_rejected_cannot_claim_external_effect_identity() -> None:
    for disposition in ("prevented", "rejected"):
        with pytest.raises(ValidationError, match="cannot claim"):
            _effect(disposition=disposition)


def test_external_effect_ref_and_hash_must_appear_together() -> None:
    with pytest.raises(ValidationError, match="appear together"):
        _effect(external_effect_hash=None)
    with pytest.raises(ValidationError, match="appear together"):
        _effect(external_effect_ref=None)


def test_outcome_unknown_allows_no_fabricated_external_effect() -> None:
    effect = _effect(
        disposition="outcome_unknown",
        external_effect_ref=None,
        external_effect_hash=None,
        evidence_ref="evidence:ambiguous-provider-ack",
        evidence_hash=_hash("7"),
    )
    assert effect.disposition == "outcome_unknown"
    assert effect.external_effect_ref is None


def test_effect_hash_excludes_local_record_id_and_completion_time() -> None:
    baseline = _effect()
    changed = _effect(
        call_request_id="protected-call-record-replayed",
        completed_at=NOW + timedelta(hours=1),
    )
    assert changed.effect_hash == baseline.effect_hash
    assert "call_request_id" not in baseline.effect_identity_payload()
    assert "completed_at" not in baseline.effect_identity_payload()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_hash", _hash("1")),
        ("disposition", "outcome_unknown"),
        ("external_effect_ref", "repo-commit:def456"),
        ("external_effect_hash", _hash("2")),
        ("evidence_ref", "evidence:other"),
        ("evidence_hash", _hash("3")),
    ],
)
def test_effect_evidence_dimensions_move_effect_hash(field: str, value) -> None:
    overrides = {field: value}
    if field == "disposition":
        overrides.update(external_effect_ref=None, external_effect_hash=None)
    assert _effect(**overrides).effect_hash != _effect().effect_hash


def test_effect_completion_time_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _effect(completed_at=datetime(2026, 8, 12, 11, 0))
