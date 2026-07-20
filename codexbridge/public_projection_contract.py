from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Final


PUBLIC_PROJECTION_SCHEMA_VERSION: Final[str] = "cf1.v1"
NON_AUTHORITATIVE_NOTICE: Final[str] = (
    "This is a non-authoritative public projection. "
    "The complete authoritative record remains available through explicit evidence retrieval."
)


class PublicView(str, Enum):
    SUMMARY = "summary"
    STANDARD = "standard"
    FULL = "full"


class NormalizedOutcome(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    PARTIAL = "partial"
    VALIDATION_FAILURE = "validation_failure"
    POLICY_DENIAL = "policy_denial"
    NEEDS_INPUT = "needs_input"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLATION_VERIFIED = "cancellation_verified"
    CANCELLATION_UNCERTAIN = "cancellation_uncertain"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    CLEANUP_INCOMPLETE = "cleanup_incomplete"
    AMBIGUOUS_SIDE_EFFECT = "ambiguous_side_effect"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    UNKNOWN_FAILURE = "unknown_failure"


class ArtifactVisibility(str, Enum):
    PUBLIC = "public"
    PROTECTED = "protected"
    INTERNAL_ONLY = "internal_only"
    REVIEWED_SCRIPT_EXCLUDED = "reviewed_script_excluded"


@dataclass(frozen=True)
class PublicByteBudgets:
    run_list: int = 12 * 1024
    run_summary: int = 6 * 1024
    terminal_result: int = 12 * 1024
    unchanged_poll: int = 1024
    events: int = 12 * 1024
    repository_search: int = 16 * 1024
    repository_read_batch: int = 48 * 1024
    repository_diff: int = 32 * 1024
    unsolicited_response: int = 64 * 1024

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer byte budget")
        if self.run_list > self.unsolicited_response:
            raise ValueError("run_list budget exceeds unsolicited_response budget")
        if self.run_summary > self.unsolicited_response:
            raise ValueError("run_summary budget exceeds unsolicited_response budget")
        if self.terminal_result > self.unsolicited_response:
            raise ValueError("terminal_result budget exceeds unsolicited_response budget")
        if self.events > self.unsolicited_response:
            raise ValueError("events budget exceeds unsolicited_response budget")
        if self.repository_search > self.unsolicited_response:
            raise ValueError("repository_search budget exceeds unsolicited_response budget")
        if self.repository_read_batch > self.unsolicited_response:
            raise ValueError("repository_read_batch budget exceeds unsolicited_response budget")
        if self.repository_diff > self.unsolicited_response:
            raise ValueError("repository_diff budget exceeds unsolicited_response budget")


DEFAULT_PUBLIC_BYTE_BUDGETS: Final[PublicByteBudgets] = PublicByteBudgets()


@dataclass(frozen=True)
class TruncatedUtf8:
    text: str
    original_bytes: int
    returned_bytes: int
    truncated: bool
    omitted_sha256: str | None


def truncate_utf8(value: str, maximum_bytes: int) -> TruncatedUtf8:
    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) or maximum_bytes < 0:
        raise ValueError("maximum_bytes must be a non-negative integer")
    encoded = str(value).encode("utf-8")
    original_bytes = len(encoded)
    if original_bytes <= maximum_bytes:
        return TruncatedUtf8(
            text=str(value),
            original_bytes=original_bytes,
            returned_bytes=original_bytes,
            truncated=False,
            omitted_sha256=None,
        )

    prefix = encoded[:maximum_bytes]
    while prefix:
        try:
            decoded = prefix.decode("utf-8")
            break
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    else:
        decoded = ""

    omitted = encoded[len(prefix) :]
    return TruncatedUtf8(
        text=decoded,
        original_bytes=original_bytes,
        returned_bytes=len(prefix),
        truncated=True,
        omitted_sha256=sha256(omitted).hexdigest(),
    )


@dataclass(frozen=True)
class CompactCursorBinding:
    operation: str
    filters_sha256: str
    ordering: str
    view: PublicView
    projection_version: str
    byte_budget: int
    snapshot_boundary: str
    final_sort_key: str
    expires_at_utc: str

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise ValueError("operation must not be empty")
        if len(self.filters_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.filters_sha256.lower()
        ):
            raise ValueError("filters_sha256 must be a SHA-256 value")
        if not self.ordering.strip():
            raise ValueError("ordering must not be empty")
        if not self.projection_version.strip():
            raise ValueError("projection_version must not be empty")
        if isinstance(self.byte_budget, bool) or not isinstance(self.byte_budget, int) or self.byte_budget <= 0:
            raise ValueError("byte_budget must be a positive integer")
        if not self.snapshot_boundary.strip():
            raise ValueError("snapshot_boundary must not be empty")
        if not self.final_sort_key.strip():
            raise ValueError("final_sort_key must not be empty")
        if not self.expires_at_utc.strip():
            raise ValueError("expires_at_utc must not be empty")
