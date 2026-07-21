from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from codexbridge.cf1_contract_freeze import (
    ARTIFACT_VISIBILITY_SEMANTICS,
    CF1_COMPATIBILITY_INVARIANTS,
    CF1_CONTRACT_FREEZE_VERSION,
    DEFAULT_DECISION_VERSION_POLICY,
    DEFAULT_PUBLIC_FIELD_BYTE_BUDGETS,
    NORMALIZED_OUTCOME_SEMANTICS,
    PUBLIC_REDACTION_RULES,
    CompatibilityInvariant,
    NonDecisionTransition,
    OutcomeAction,
    OutcomeDecisionClass,
    RedactionAction,
    validate_cf1_contract_freeze,
)
from codexbridge.public_projection_contract import (
    DEFAULT_PUBLIC_BYTE_BUDGETS,
    ArtifactVisibility,
    DecisionRelevantTransition,
    NormalizedOutcome,
    PublicView,
    StaleContentResponse,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_symbol(reference: str) -> object:
    module_name, symbol_path = reference.split(":", 1)
    value: object = importlib.import_module(module_name)
    for part in symbol_path.split("."):
        value = getattr(value, part)
    return value


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def test_cf1_contract_freeze_is_versioned_and_complete() -> None:
    validate_cf1_contract_freeze()

    assert CF1_CONTRACT_FREEZE_VERSION == "cf1.0.contract-freeze.v1"
    assert {item.invariant for item in CF1_COMPATIBILITY_INVARIANTS} == set(
        CompatibilityInvariant
    )
    assert set(NORMALIZED_OUTCOME_SEMANTICS) == set(NormalizedOutcome)
    assert set(ARTIFACT_VISIBILITY_SEMANTICS) == set(ArtifactVisibility)


def test_normalized_outcomes_cannot_collapse_failure_or_uncertainty_into_success() -> None:
    success_like = {
        outcome
        for outcome, semantics in NORMALIZED_OUTCOME_SEMANTICS.items()
        if semantics.success_like
    }

    assert success_like == {NormalizedOutcome.SUCCESS}
    assert NORMALIZED_OUTCOME_SEMANTICS[NormalizedOutcome.SUCCESS].action_required is (
        OutcomeAction.NONE
    )
    assert NORMALIZED_OUTCOME_SEMANTICS[NormalizedOutcome.PARTIAL].decision_class is (
        OutcomeDecisionClass.DEGRADED
    )
    assert NORMALIZED_OUTCOME_SEMANTICS[
        NormalizedOutcome.VALIDATION_FAILURE
    ].must_expose_error is True
    assert NORMALIZED_OUTCOME_SEMANTICS[
        NormalizedOutcome.CANCELLATION_UNCERTAIN
    ].must_expose_reconciliation is True
    assert NORMALIZED_OUTCOME_SEMANTICS[
        NormalizedOutcome.AMBIGUOUS_SIDE_EFFECT
    ].action_required is OutcomeAction.RECONCILE
    assert NORMALIZED_OUTCOME_SEMANTICS[
        NormalizedOutcome.RECONCILIATION_REQUIRED
    ].action_required is OutcomeAction.RECONCILE


def test_per_field_budgets_are_utf8_byte_limits_below_whole_response_gates() -> None:
    budgets = DEFAULT_PUBLIC_FIELD_BYTE_BUDGETS

    assert budgets.summary == 2 * 1024
    assert budgets.error == 4 * 1024
    assert budgets.path == 1024
    assert budgets.test_message == 2 * 1024
    assert budgets.diagnostic == 4 * 1024
    assert budgets.artifact_reference == 1024
    assert budgets.artifact_reference_count == 20
    assert budgets.changed_file_count == 50
    assert budgets.summary < DEFAULT_PUBLIC_BYTE_BUDGETS.run_summary
    assert budgets.error < DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result
    assert budgets.diagnostic < DEFAULT_PUBLIC_BYTE_BUDGETS.unsolicited_response


@pytest.mark.parametrize("field_name", DEFAULT_PUBLIC_FIELD_BYTE_BUDGETS.__dict__)
def test_per_field_budgets_reject_non_positive_values(field_name: str) -> None:
    values = dict(DEFAULT_PUBLIC_FIELD_BYTE_BUDGETS.__dict__)
    values[field_name] = 0

    with pytest.raises(ValueError):
        type(DEFAULT_PUBLIC_FIELD_BYTE_BUDGETS)(**values)


def test_redaction_contract_covers_secrets_scripts_bulk_inputs_paths_and_artifacts() -> None:
    rules = {rule.name: rule for rule in PUBLIC_REDACTION_RULES}

    assert set(rules) == {
        "secret_values",
        "reviewed_scripts",
        "bulk_request_fields",
        "local_paths",
        "protected_artifacts",
        "internal_ownership",
    }
    assert rules["secret_values"].action is RedactionAction.REDACT_PUBLIC
    assert set(rules["secret_values"].views) == set(PublicView)
    assert rules["reviewed_scripts"].action is RedactionAction.EXCLUDE_PUBLIC
    assert "script" in rules["reviewed_scripts"].fields
    assert rules["bulk_request_fields"].action is (
        RedactionAction.OMIT_ORDINARY_VIEWS
    )
    assert {"argv", "environment", "stdin"} <= set(
        rules["bulk_request_fields"].fields
    )
    assert rules["protected_artifacts"].action is RedactionAction.HANDLE_ONLY
    assert rules["internal_ownership"].action is RedactionAction.EXCLUDE_PUBLIC
    assert "worker_lease_token" in rules["internal_ownership"].fields


def test_artifact_visibility_contract_separates_public_protected_and_excluded_bytes() -> None:
    public = ARTIFACT_VISIBILITY_SEMANTICS[ArtifactVisibility.PUBLIC]
    protected = ARTIFACT_VISIBILITY_SEMANTICS[ArtifactVisibility.PROTECTED]
    internal = ARTIFACT_VISIBILITY_SEMANTICS[ArtifactVisibility.INTERNAL_ONLY]
    script = ARTIFACT_VISIBILITY_SEMANTICS[
        ArtifactVisibility.REVIEWED_SCRIPT_EXCLUDED
    ]

    assert public.exact_bytes_allowed is True
    assert protected.ordinary_view == "identity_handle_only"
    assert protected.exact_bytes_allowed is True
    assert internal.exact_bytes_allowed is False
    assert script.exact_bytes_allowed is False
    assert internal.explicit_retrieval == "not_publicly_retrievable"
    assert script.explicit_retrieval == "not_publicly_retrievable"


def test_decision_version_policy_increments_for_decisions_but_not_heartbeats() -> None:
    policy = DEFAULT_DECISION_VERSION_POLICY

    assert set(policy.increment_for) == set(DecisionRelevantTransition)
    assert set(policy.stable_for) == set(NonDecisionTransition)
    assert NonDecisionTransition.HEARTBEAT_REFRESH in policy.stable_for
    assert NonDecisionTransition.ELAPSED_TIME_REFRESH in policy.stable_for


def test_stale_content_contract_requires_two_distinct_sha256_identities() -> None:
    response = StaleContentResponse(expected_sha256="a" * 64, current_sha256="b" * 64)

    assert response.reason == "stale_content"
    with pytest.raises(ValueError, match="must differ"):
        StaleContentResponse(expected_sha256="a" * 64, current_sha256="a" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        StaleContentResponse(expected_sha256="not-a-hash", current_sha256="b" * 64)


def test_compatibility_invariant_implementation_symbols_resolve() -> None:
    for evidence in CF1_COMPATIBILITY_INVARIANTS:
        for reference in evidence.implementation_paths:
            assert _resolve_symbol(reference) is not None, reference


def test_compatibility_invariant_regression_test_ids_exist() -> None:
    cached_functions: dict[Path, set[str]] = {}

    for evidence in CF1_COMPATIBILITY_INVARIANTS:
        for test_id in evidence.regression_tests:
            relative_path, test_name = test_id.split("::", 1)
            path = REPO_ROOT / relative_path
            assert path.is_file(), test_id
            functions = cached_functions.setdefault(path, _test_functions(path))
            assert test_name in functions, test_id


def test_compatibility_invariant_evidence_is_unique_and_descriptive() -> None:
    all_test_ids = [
        test_id
        for evidence in CF1_COMPATIBILITY_INVARIANTS
        for test_id in evidence.regression_tests
    ]

    assert len(CF1_COMPATIBILITY_INVARIANTS) == 7
    assert all(evidence.preserved_behavior for evidence in CF1_COMPATIBILITY_INVARIANTS)
    assert len(set(all_test_ids)) < len(all_test_ids)
    assert any(
        evidence.invariant is CompatibilityInvariant.FULL_RUN_TRANSPORT
        and "exactly reconstructable" in evidence.preserved_behavior
        for evidence in CF1_COMPATIBILITY_INVARIANTS
    )
