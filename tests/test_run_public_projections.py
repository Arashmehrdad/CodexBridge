from __future__ import annotations

from hashlib import sha256

import pytest

from codexbridge.public_projection_contract import (
    DEFAULT_PUBLIC_BYTE_BUDGETS,
    NON_AUTHORITATIVE_NOTICE,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
    ArtifactVisibility,
    CompactCursorBinding,
    NormalizedOutcome,
    PublicByteBudgets,
    PublicView,
    truncate_utf8,
)


def test_public_projection_contract_is_versioned_and_explicitly_non_authoritative() -> None:
    assert PUBLIC_PROJECTION_SCHEMA_VERSION == "cf1.v1"
    assert "non-authoritative" in NON_AUTHORITATIVE_NOTICE
    assert "authoritative record remains available" in NON_AUTHORITATIVE_NOTICE
    assert {view.value for view in PublicView} == {"summary", "standard", "full"}


def test_normalized_outcomes_preserve_operational_distinctions() -> None:
    assert {outcome.value for outcome in NormalizedOutcome} == {
        "pending",
        "success",
        "partial",
        "validation_failure",
        "policy_denial",
        "needs_input",
        "cancellation_requested",
        "cancellation_verified",
        "cancellation_uncertain",
        "infrastructure_failure",
        "cleanup_incomplete",
        "ambiguous_side_effect",
        "reconciliation_required",
        "unknown_failure",
    }
    assert {visibility.value for visibility in ArtifactVisibility} == {
        "public",
        "protected",
        "internal_only",
        "reviewed_script_excluded",
    }


def test_default_public_byte_budgets_match_cf1_exit_gates() -> None:
    assert DEFAULT_PUBLIC_BYTE_BUDGETS == PublicByteBudgets(
        run_list=12 * 1024,
        run_summary=6 * 1024,
        terminal_result=12 * 1024,
        unchanged_poll=1024,
        events=12 * 1024,
        repository_search=16 * 1024,
        repository_read_batch=48 * 1024,
        repository_diff=32 * 1024,
        unsolicited_response=64 * 1024,
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_public_byte_budgets_reject_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        PublicByteBudgets(run_list=value)  # type: ignore[arg-type]


def test_truncate_utf8_preserves_unicode_boundaries_and_omitted_identity() -> None:
    value = "ab😀cd"
    result = truncate_utf8(value, 5)

    assert result.text == "ab"
    assert result.original_bytes == len(value.encode("utf-8"))
    assert result.returned_bytes == 2
    assert result.truncated is True
    assert result.omitted_sha256 == sha256("😀cd".encode("utf-8")).hexdigest()


def test_truncate_utf8_returns_identity_free_complete_value() -> None:
    result = truncate_utf8("complete", 8)

    assert result.text == "complete"
    assert result.original_bytes == 8
    assert result.returned_bytes == 8
    assert result.truncated is False
    assert result.omitted_sha256 is None


@pytest.mark.parametrize("maximum_bytes", [-1, True, 1.5])
def test_truncate_utf8_rejects_invalid_budgets(maximum_bytes: object) -> None:
    with pytest.raises(ValueError):
        truncate_utf8("value", maximum_bytes)  # type: ignore[arg-type]


def test_compact_cursor_binding_requires_content_bound_fields() -> None:
    binding = CompactCursorBinding(
        operation="run_summary_list",
        filters_sha256="a" * 64,
        ordering="created_at DESC, run_id DESC",
        view=PublicView.SUMMARY,
        projection_version=PUBLIC_PROJECTION_SCHEMA_VERSION,
        byte_budget=DEFAULT_PUBLIC_BYTE_BUDGETS.run_list,
        snapshot_boundary="2026-07-20T23:00:00Z",
        final_sort_key="2026-07-20T22:59:00Z/run-1",
        expires_at_utc="2026-07-20T23:10:00Z",
    )

    assert binding.view is PublicView.SUMMARY
    assert binding.byte_budget == 12 * 1024


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", ""),
        ("filters_sha256", "not-a-hash"),
        ("ordering", ""),
        ("projection_version", ""),
        ("byte_budget", 0),
        ("snapshot_boundary", ""),
        ("final_sort_key", ""),
        ("expires_at_utc", ""),
    ],
)
def test_compact_cursor_binding_rejects_incomplete_identity(field: str, value: object) -> None:
    values = {
        "operation": "run_summary_list",
        "filters_sha256": "a" * 64,
        "ordering": "created_at DESC, run_id DESC",
        "view": PublicView.SUMMARY,
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "byte_budget": 12 * 1024,
        "snapshot_boundary": "2026-07-20T23:00:00Z",
        "final_sort_key": "2026-07-20T22:59:00Z/run-1",
        "expires_at_utc": "2026-07-20T23:10:00Z",
    }
    values[field] = value

    with pytest.raises(ValueError):
        CompactCursorBinding(**values)  # type: ignore[arg-type]
