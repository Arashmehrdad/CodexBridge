"""G2.1 pure ReasoningSpecV1 contract tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from soma.reasoning import (
    MAX_PROVIDER_INTERNAL_CONCURRENCY,
    MAX_REASONING_CONTEXT_REFS,
    MAX_REASONING_DEPENDENCY_PROOF_REFS,
    MAX_REASONING_OUTPUT_BYTES,
    MAX_REASONING_WALL_TIME_SECONDS,
    MIN_PROVIDER_INTERNAL_CONCURRENCY,
    MIN_REASONING_OUTPUT_BYTES,
    MIN_REASONING_WALL_TIME_SECONDS,
    REASONING_SPEC_SCHEMA_VERSION,
    ReasoningBudgetsV1,
    ReasoningHashedReferenceV1,
    ReasoningSpecV1,
)


def _hash(character: str) -> str:
    return character * 64


def _ref(name: str, marker: str = "a") -> ReasoningHashedReferenceV1:
    return ReasoningHashedReferenceV1(ref=name, hash=_hash(marker))


def _budgets(**overrides) -> ReasoningBudgetsV1:
    values = {
        "wall_time_seconds": 600,
        "output_bytes": 32 * 1024,
        "input_token_limit": 100_000,
        "output_token_limit": 10_000,
        "cost_limit_usd": Decimal("5.00"),
        "provider_internal_concurrency_limit": 1,
    }
    values.update(overrides)
    return ReasoningBudgetsV1(**values)


def _spec(**overrides) -> ReasoningSpecV1:
    values = {
        "assignment_ref": "assignment:work-package-attempt",
        "assignment_hash": _hash("1"),
        "context_refs": (_ref("context:repo", "2"),),
        "dependency_proof_refs": (_ref("proof:dependency", "3"),),
        "output_contract_ref": "contract:evidence-submission-v1",
        "output_contract_hash": _hash("4"),
        "tool_policy_ref": "tool-policy:read-only-repo",
        "tool_policy_hash": _hash("5"),
        "authority_ref": "authority:task-mandate",
        "authority_hash": _hash("6"),
        "provider_route_ref": "route:fake-reasoning",
        "provider_route_hash": _hash("7"),
        "budgets": _budgets(),
        "continuation_policy": "none",
        "mutation_policy": "read_only",
    }
    values.update(overrides)
    return ReasoningSpecV1(**values)


def test_reasoning_spec_frozen_shape_and_bounds_are_exact() -> None:
    assert REASONING_SPEC_SCHEMA_VERSION == "reasoning_spec.v1"
    assert MAX_REASONING_CONTEXT_REFS == 64
    assert MAX_REASONING_DEPENDENCY_PROOF_REFS == 64
    assert MIN_REASONING_WALL_TIME_SECONDS == 1
    assert MAX_REASONING_WALL_TIME_SECONDS == 86_400
    assert MIN_REASONING_OUTPUT_BYTES == 1024
    assert MAX_REASONING_OUTPUT_BYTES == 262_144
    assert MIN_PROVIDER_INTERNAL_CONCURRENCY == 1
    assert MAX_PROVIDER_INTERNAL_CONCURRENCY == 8

    spec = _spec()
    assert spec.schema_version == "reasoning_spec.v1"
    assert spec.provider_route_ref == "route:fake-reasoning"
    assert spec.mutation_policy == "read_only"


def test_context_and_dependency_proof_reference_bounds_are_enforced() -> None:
    context = tuple(_ref(f"context:{index}") for index in range(64))
    proofs = tuple(_ref(f"proof:{index}", "b") for index in range(64))
    accepted = _spec(context_refs=context, dependency_proof_refs=proofs)
    assert len(accepted.context_refs) == 64
    assert len(accepted.dependency_proof_refs) == 64

    with pytest.raises(ValidationError):
        _spec(context_refs=tuple(_ref(f"context:{index}") for index in range(65)))
    with pytest.raises(ValidationError):
        _spec(
            dependency_proof_refs=tuple(
                _ref(f"proof:{index}", "c") for index in range(65)
            )
        )


def test_reference_hashes_are_exact_sha256_shapes() -> None:
    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        ReasoningHashedReferenceV1(ref="context:bad", hash="not-a-hash")

    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        _spec(provider_route_hash="bad")


def test_wall_time_output_bytes_and_internal_concurrency_bounds() -> None:
    assert _budgets(wall_time_seconds=1).wall_time_seconds == 1
    assert _budgets(wall_time_seconds=86_400).wall_time_seconds == 86_400
    assert _budgets(output_bytes=1024).output_bytes == 1024
    assert _budgets(output_bytes=262_144).output_bytes == 262_144
    assert (
        _budgets(
            provider_internal_concurrency_limit=1
        ).provider_internal_concurrency_limit
        == 1
    )
    assert (
        _budgets(
            provider_internal_concurrency_limit=8
        ).provider_internal_concurrency_limit
        == 8
    )

    for values in (
        {"wall_time_seconds": 0},
        {"wall_time_seconds": 86_401},
        {"output_bytes": 1023},
        {"output_bytes": 262_145},
        {"provider_internal_concurrency_limit": 0},
        {"provider_internal_concurrency_limit": 9},
    ):
        with pytest.raises(ValidationError):
            _budgets(**values)


def test_optional_token_and_cost_budgets_must_be_positive_when_present() -> None:
    assert _budgets(
        input_token_limit=None, output_token_limit=None, cost_limit_usd=None
    )

    for values in (
        {"input_token_limit": 0},
        {"output_token_limit": 0},
        {"cost_limit_usd": Decimal("0")},
        {"cost_limit_usd": Decimal("-1")},
    ):
        with pytest.raises(ValidationError):
            _budgets(**values)


def test_continuation_and_mutation_policies_are_closed_vocabularies() -> None:
    for continuation in (
        "none",
        "explicit_provider_identity",
        "provider_managed",
    ):
        assert (
            _spec(continuation_policy=continuation).continuation_policy == continuation
        )

    for mutation in ("read_only", "protected_broker_only"):
        assert _spec(mutation_policy=mutation).mutation_policy == mutation

    with pytest.raises(ValidationError):
        _spec(continuation_policy="implicit_session_guess")
    with pytest.raises(ValidationError):
        _spec(mutation_policy="direct_write")


def test_duplicate_reference_identity_is_rejected() -> None:
    duplicate = _ref("context:duplicate")
    with pytest.raises(ValidationError, match="context_refs must contain unique refs"):
        _spec(context_refs=(duplicate, duplicate))

    proof = _ref("proof:duplicate", "b")
    with pytest.raises(
        ValidationError, match="dependency_proof_refs must contain unique refs"
    ):
        _spec(dependency_proof_refs=(proof, proof))


def test_provider_route_is_explicit_subordinate_routing_material() -> None:
    spec = _spec(
        provider_route_ref="route:openai-profile-strong",
        provider_route_hash=_hash("d"),
        continuation_policy="explicit_provider_identity",
        mutation_policy="protected_broker_only",
    )

    assert spec.provider_route_ref == "route:openai-profile-strong"
    assert spec.continuation_policy == "explicit_provider_identity"
    assert spec.mutation_policy == "protected_broker_only"


def test_prompt_bodies_transcripts_and_secrets_are_not_spec_fields() -> None:
    payload = _spec().model_dump(mode="python")
    for forbidden_field in ("prompt", "transcript", "repository_body", "secret"):
        changed = dict(payload)
        changed[forbidden_field] = "forbidden inline body"
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            ReasoningSpecV1.model_validate(changed)


def test_spec_is_frozen() -> None:
    spec = _spec()
    with pytest.raises(ValidationError):
        spec.mutation_policy = "protected_broker_only"
