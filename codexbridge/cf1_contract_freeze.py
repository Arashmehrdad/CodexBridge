from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from codexbridge.public_projection_contract import (
    ArtifactVisibility,
    DecisionRelevantTransition,
    NormalizedOutcome,
    PublicView,
)


CF1_CONTRACT_FREEZE_VERSION: Final[str] = "cf1.0.contract-freeze.v1"


class OutcomeDecisionClass(str, Enum):
    ONGOING = "ongoing"
    SUCCESS = "success"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILURE = "failure"
    UNCERTAIN = "uncertain"
    CANCELLED = "cancelled"


class OutcomeAction(str, Enum):
    NONE = "none"
    MONITOR = "monitor"
    REVIEW_PARTIAL = "review_partial"
    FIX_VALIDATION = "fix_validation"
    CHANGE_REQUEST = "change_request"
    PROVIDE_INPUT = "provide_input"
    VERIFY_CANCELLATION = "verify_cancellation"
    REVIEW_CANCELLATION = "review_cancellation"
    RETRY_OR_REPAIR = "retry_or_repair"
    COMPLETE_CLEANUP = "complete_cleanup"
    RECONCILE = "reconcile"
    INVESTIGATE = "investigate"


@dataclass(frozen=True)
class OutcomeSemantics:
    decision_class: OutcomeDecisionClass
    action_required: OutcomeAction
    success_like: bool
    must_expose_error: bool
    must_expose_reconciliation: bool


NORMALIZED_OUTCOME_SEMANTICS: Final[dict[NormalizedOutcome, OutcomeSemantics]] = {
    NormalizedOutcome.PENDING: OutcomeSemantics(
        OutcomeDecisionClass.ONGOING, OutcomeAction.MONITOR, False, False, False
    ),
    NormalizedOutcome.SUCCESS: OutcomeSemantics(
        OutcomeDecisionClass.SUCCESS, OutcomeAction.NONE, True, False, False
    ),
    NormalizedOutcome.PARTIAL: OutcomeSemantics(
        OutcomeDecisionClass.DEGRADED,
        OutcomeAction.REVIEW_PARTIAL,
        False,
        True,
        False,
    ),
    NormalizedOutcome.VALIDATION_FAILURE: OutcomeSemantics(
        OutcomeDecisionClass.FAILURE,
        OutcomeAction.FIX_VALIDATION,
        False,
        True,
        False,
    ),
    NormalizedOutcome.POLICY_DENIAL: OutcomeSemantics(
        OutcomeDecisionClass.BLOCKED,
        OutcomeAction.CHANGE_REQUEST,
        False,
        True,
        False,
    ),
    NormalizedOutcome.NEEDS_INPUT: OutcomeSemantics(
        OutcomeDecisionClass.BLOCKED,
        OutcomeAction.PROVIDE_INPUT,
        False,
        False,
        False,
    ),
    NormalizedOutcome.CANCELLATION_REQUESTED: OutcomeSemantics(
        OutcomeDecisionClass.ONGOING,
        OutcomeAction.VERIFY_CANCELLATION,
        False,
        False,
        False,
    ),
    NormalizedOutcome.CANCELLATION_VERIFIED: OutcomeSemantics(
        OutcomeDecisionClass.CANCELLED,
        OutcomeAction.REVIEW_CANCELLATION,
        False,
        False,
        False,
    ),
    NormalizedOutcome.CANCELLATION_UNCERTAIN: OutcomeSemantics(
        OutcomeDecisionClass.UNCERTAIN,
        OutcomeAction.RECONCILE,
        False,
        True,
        True,
    ),
    NormalizedOutcome.INFRASTRUCTURE_FAILURE: OutcomeSemantics(
        OutcomeDecisionClass.FAILURE,
        OutcomeAction.RETRY_OR_REPAIR,
        False,
        True,
        False,
    ),
    NormalizedOutcome.CLEANUP_INCOMPLETE: OutcomeSemantics(
        OutcomeDecisionClass.DEGRADED,
        OutcomeAction.COMPLETE_CLEANUP,
        False,
        True,
        False,
    ),
    NormalizedOutcome.AMBIGUOUS_SIDE_EFFECT: OutcomeSemantics(
        OutcomeDecisionClass.UNCERTAIN,
        OutcomeAction.RECONCILE,
        False,
        True,
        True,
    ),
    NormalizedOutcome.RECONCILIATION_REQUIRED: OutcomeSemantics(
        OutcomeDecisionClass.UNCERTAIN,
        OutcomeAction.RECONCILE,
        False,
        True,
        True,
    ),
    NormalizedOutcome.UNKNOWN_FAILURE: OutcomeSemantics(
        OutcomeDecisionClass.FAILURE,
        OutcomeAction.INVESTIGATE,
        False,
        True,
        False,
    ),
}


@dataclass(frozen=True)
class PublicFieldByteBudgets:
    summary: int = 2 * 1024
    error: int = 4 * 1024
    path: int = 1024
    test_message: int = 2 * 1024
    diagnostic: int = 4 * 1024
    artifact_reference: int = 1024
    artifact_reference_count: int = 20
    changed_file_count: int = 50

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


DEFAULT_PUBLIC_FIELD_BYTE_BUDGETS: Final[PublicFieldByteBudgets] = (
    PublicFieldByteBudgets()
)


class RedactionAction(str, Enum):
    REDACT_PUBLIC = "redact_public"
    EXCLUDE_PUBLIC = "exclude_public"
    OMIT_ORDINARY_VIEWS = "omit_ordinary_views"
    HANDLE_ONLY = "handle_only"


@dataclass(frozen=True)
class PublicRedactionRule:
    name: str
    fields: tuple[str, ...]
    action: RedactionAction
    views: tuple[PublicView, ...]
    rationale: str


PUBLIC_REDACTION_RULES: Final[tuple[PublicRedactionRule, ...]] = (
    PublicRedactionRule(
        name="secret_values",
        fields=("password", "secret", "token", "credential", "api_key", "bearer"),
        action=RedactionAction.REDACT_PUBLIC,
        views=(PublicView.SUMMARY, PublicView.STANDARD, PublicView.FULL),
        rationale="Secret-like keys and values never appear verbatim in a public view.",
    ),
    PublicRedactionRule(
        name="reviewed_scripts",
        fields=("reviewed_script", "root_shell_script", "script"),
        action=RedactionAction.EXCLUDE_PUBLIC,
        views=(PublicView.SUMMARY, PublicView.STANDARD, PublicView.FULL),
        rationale="Exact reviewed scripts remain protected evidence, not public payloads.",
    ),
    PublicRedactionRule(
        name="bulk_request_fields",
        fields=("argv", "environment", "stdin", "request_body", "patch"),
        action=RedactionAction.OMIT_ORDINARY_VIEWS,
        views=(PublicView.SUMMARY, PublicView.STANDARD),
        rationale="Ordinary projections carry bounded intent and evidence handles only.",
    ),
    PublicRedactionRule(
        name="local_paths",
        fields=("run_dir", "absolute_path", "staging_path", "executable_path"),
        action=RedactionAction.OMIT_ORDINARY_VIEWS,
        views=(PublicView.SUMMARY, PublicView.STANDARD),
        rationale="Local filesystem internals are not required for ordinary decisions.",
    ),
    PublicRedactionRule(
        name="protected_artifacts",
        fields=("protected_evidence", "stdout", "stderr", "binary_artifact"),
        action=RedactionAction.HANDLE_ONLY,
        views=(PublicView.SUMMARY, PublicView.STANDARD),
        rationale="Public views expose immutable evidence identity rather than artifact bytes.",
    ),
    PublicRedactionRule(
        name="internal_ownership",
        fields=("worker_lease_token", "repository_lock_token", "approval_secret"),
        action=RedactionAction.EXCLUDE_PUBLIC,
        views=(PublicView.SUMMARY, PublicView.STANDARD, PublicView.FULL),
        rationale="Internal ownership and approval tokens are never public data.",
    ),
)


@dataclass(frozen=True)
class ArtifactVisibilitySemantics:
    ordinary_view: str
    explicit_retrieval: str
    exact_bytes_allowed: bool


ARTIFACT_VISIBILITY_SEMANTICS: Final[
    dict[ArtifactVisibility, ArtifactVisibilitySemantics]
] = {
    ArtifactVisibility.PUBLIC: ArtifactVisibilitySemantics(
        ordinary_view="bounded_metadata_or_content",
        explicit_retrieval="manifest_validated",
        exact_bytes_allowed=True,
    ),
    ArtifactVisibility.PROTECTED: ArtifactVisibilitySemantics(
        ordinary_view="identity_handle_only",
        explicit_retrieval="trusted_manifest_validated",
        exact_bytes_allowed=True,
    ),
    ArtifactVisibility.INTERNAL_ONLY: ArtifactVisibilitySemantics(
        ordinary_view="excluded",
        explicit_retrieval="not_publicly_retrievable",
        exact_bytes_allowed=False,
    ),
    ArtifactVisibility.REVIEWED_SCRIPT_EXCLUDED: ArtifactVisibilitySemantics(
        ordinary_view="excluded",
        explicit_retrieval="not_publicly_retrievable",
        exact_bytes_allowed=False,
    ),
}


class NonDecisionTransition(str, Enum):
    HEARTBEAT_REFRESH = "heartbeat_refresh"
    ELAPSED_TIME_REFRESH = "elapsed_time_refresh"


@dataclass(frozen=True)
class DecisionVersionPolicy:
    increment_for: tuple[DecisionRelevantTransition, ...]
    stable_for: tuple[NonDecisionTransition, ...]


DEFAULT_DECISION_VERSION_POLICY: Final[DecisionVersionPolicy] = DecisionVersionPolicy(
    increment_for=tuple(DecisionRelevantTransition),
    stable_for=tuple(NonDecisionTransition),
)


class CompatibilityInvariant(str, Enum):
    FULL_RUN_TRANSPORT = "full_run_transport"
    RECURSIVE_REDACTION = "recursive_redaction"
    REVIEWED_SCRIPT_MASKING = "reviewed_script_masking"
    REPOSITORY_PATH_SAFETY = "repository_path_safety"
    REPOSITORY_FILE_HASHING = "repository_file_hashing"
    COMPACT_REPOSITORY_STATUS = "compact_repository_status"
    OPAQUE_MANAGED_WRITE_IDENTITY = "opaque_managed_write_identity"


@dataclass(frozen=True)
class CompatibilityInvariantEvidence:
    invariant: CompatibilityInvariant
    implementation_paths: tuple[str, ...]
    regression_tests: tuple[str, ...]
    preserved_behavior: str

    def __post_init__(self) -> None:
        if not self.implementation_paths or not self.regression_tests:
            raise ValueError("compatibility evidence requires implementation paths and tests")
        if any(":" not in path for path in self.implementation_paths):
            raise ValueError("implementation paths must use module:symbol form")
        if any("::test_" not in test_id for test_id in self.regression_tests):
            raise ValueError("regression tests must use path::test_name form")
        if not self.preserved_behavior.strip():
            raise ValueError("preserved_behavior must not be empty")


CF1_COMPATIBILITY_INVARIANTS: Final[
    tuple[CompatibilityInvariantEvidence, ...]
] = (
    CompatibilityInvariantEvidence(
        CompatibilityInvariant.FULL_RUN_TRANSPORT,
        ("codexbridge.run_query_chunks:chunk_payload",),
        (
            "tests/test_run_query_chunks.py::test_large_status_round_trips_without_total_data_loss",
            "tests/test_run_query_chunks.py::test_status_cursor_uses_frozen_snapshot_when_run_changes",
            "tests/test_run_query_chunks.py::test_large_result_uses_same_cursor_contract",
            "tests/test_run_query_chunks.py::test_large_list_returns_one_bounded_transport_item_per_call",
        ),
        "The explicit full view remains frozen, redacted, SHA-256-bound, and exactly reconstructable.",
    ),
    CompatibilityInvariantEvidence(
        CompatibilityInvariant.RECURSIVE_REDACTION,
        (
            "codexbridge.run_query_chunks:_redact_value",
            "codexbridge.safety:redact_secret_values",
        ),
        (
            "tests/test_run_query_chunks.py::test_large_status_round_trips_without_total_data_loss",
            "tests/test_events.py::test_redaction_and_truncation_nested_values",
        ),
        "Nested secret-like keys and values remain recursively redacted.",
    ),
    CompatibilityInvariantEvidence(
        CompatibilityInvariant.REVIEWED_SCRIPT_MASKING,
        ("codexbridge.job_manager:JobManager.start_ssh_reviewed_script",),
        (
            "tests/test_job_manager.py::test_reviewed_script_launch_persists_exact_request_and_redacts_public_views",
            "tests/test_job_manager.py::test_root_shell_launch_persists_exact_request_and_redacts_public_views",
        ),
        "Exact scripts remain durable protected inputs while public and ordinary artifacts are masked.",
    ),
    CompatibilityInvariantEvidence(
        CompatibilityInvariant.REPOSITORY_PATH_SAFETY,
        (
            "codexbridge.safety:validate_repo_relative_path",
            "codexbridge.repo_reader:_resolve_and_validate",
        ),
        (
            "tests/test_repo_reader.py::test_read_repo_file_rejects_bad_paths",
            "tests/test_repo_reader.py::test_read_repo_file_rejects_symlink_to_outside",
            "tests/test_repo_writer.py::test_apply_previewed_repo_change_rejects_payload_filename_traversal",
        ),
        "Absolute, UNC, wildcard, traversal, blocked-root, and link escapes remain rejected.",
    ),
    CompatibilityInvariantEvidence(
        CompatibilityInvariant.REPOSITORY_FILE_HASHING,
        (
            "codexbridge.repo_reader:read_repo_file",
            "codexbridge.repo_writer:_sha256_file",
        ),
        (
            "tests/test_repo_writer.py::test_create_repo_file_succeeds",
            "tests/test_repo_writer.py::test_apply_previewed_repo_change_rejects_tampered_payload",
        ),
        "Repository content and managed payloads remain bound to SHA-256 identities.",
    ),
    CompatibilityInvariantEvidence(
        CompatibilityInvariant.COMPACT_REPOSITORY_STATUS,
        ("codexbridge.git_tools:inspect_status_compact",),
        (
            "tests/test_git_tools.py::test_inspect_status_compact_payload_is_small_and_preserves_meaningful_entries",
        ),
        "Compact status continues to preserve meaningful changes while collapsing tool-owned noise.",
    ),
    CompatibilityInvariantEvidence(
        CompatibilityInvariant.OPAQUE_MANAGED_WRITE_IDENTITY,
        (
            "codexbridge.repo_writer:preview_repo_patch",
            "codexbridge.repo_writer:apply_previewed_repo_change",
        ),
        (
            "tests/test_repo_writer.py::test_apply_previewed_repo_change_rejects_tampered_payload",
            "tests/test_repo_writer.py::test_apply_previewed_repo_change_rejects_payload_filename_traversal",
            "tests/test_repo_writer.py::test_apply_previewed_repo_change_rejects_payload_symlink",
        ),
        "Managed writes remain preview-first, opaque-ID addressed, and hash verified before application.",
    ),
)


def validate_cf1_contract_freeze() -> None:
    if set(NORMALIZED_OUTCOME_SEMANTICS) != set(NormalizedOutcome):
        raise ValueError("normalized outcome semantics are incomplete")
    success_like = {
        outcome for outcome, semantics in NORMALIZED_OUTCOME_SEMANTICS.items()
        if semantics.success_like
    }
    if success_like != {NormalizedOutcome.SUCCESS}:
        raise ValueError("only normalized success may be success-like")
    if set(ARTIFACT_VISIBILITY_SEMANTICS) != set(ArtifactVisibility):
        raise ValueError("artifact visibility semantics are incomplete")
    if set(DEFAULT_DECISION_VERSION_POLICY.increment_for) != set(
        DecisionRelevantTransition
    ):
        raise ValueError("decision-version increment policy is incomplete")
    invariant_names = [item.invariant for item in CF1_COMPATIBILITY_INVARIANTS]
    if set(invariant_names) != set(CompatibilityInvariant):
        raise ValueError("compatibility invariant evidence is incomplete")
    if len(invariant_names) != len(set(invariant_names)):
        raise ValueError("compatibility invariant evidence contains duplicates")


validate_cf1_contract_freeze()
