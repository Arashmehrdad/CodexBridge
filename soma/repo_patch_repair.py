"""Deterministic repair-proposal primitives for managed repository previews.

Gate 2 builds conservative evidence only. Nothing in this module applies source
bytes or chooses a repair on behalf of a controller.
"""

from __future__ import annotations

import hashlib
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AUTHORED_SPAN_SCHEMA_VERSION: Final[str] = "repo_authored_span_provenance.v1"

DirectRepairPrimitive = Literal["exact_text", "line_range", "python_ast"]
AuthoredSpanDisposition = Literal[
    "owned",
    "ambiguous_composition",
    "unsupported_primitive",
    "no_changed_span",
]


class _FrozenRepairModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthoredSpanProvenanceV1(_FrozenRepairModel):
    """Bounded proof of which direct operation owns candidate bytes."""

    schema_version: Literal[AUTHORED_SPAN_SCHEMA_VERSION] = AUTHORED_SPAN_SCHEMA_VERSION
    operation_index: int = Field(ge=0)
    primitive: str = Field(min_length=1, max_length=64)
    disposition: AuthoredSpanDisposition
    candidate_start_byte: int | None = Field(default=None, ge=0)
    candidate_end_byte: int | None = Field(default=None, ge=0)
    candidate_span_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _validate_owned_span(self):
        if self.disposition == "owned":
            if self.candidate_start_byte is None or self.candidate_end_byte is None:
                raise ValueError("owned provenance requires a candidate byte span")
            if self.candidate_end_byte <= self.candidate_start_byte:
                raise ValueError("owned provenance requires a non-empty candidate byte span")
            if self.candidate_span_sha256 is None:
                raise ValueError("owned provenance requires a candidate span hash")
        elif any(
            value is not None
            for value in (
                self.candidate_start_byte,
                self.candidate_end_byte,
                self.candidate_span_sha256,
            )
        ):
            raise ValueError("non-owned provenance must not claim a candidate byte span")
        return self


def canonical_direct_repair_primitive(operation_type: str) -> DirectRepairPrimitive | None:
    """Collapse internal aliases without exposing them as repair policy names."""

    normalized = operation_type.strip()
    if normalized in {"", "exact_text", "replace_exact", "modify"}:
        return "exact_text"
    if normalized in {"line_range", "replace_lines"}:
        return "line_range"
    if normalized in {"python_ast", "ast_python"}:
        return "python_ast"
    return None


def _changed_candidate_span(baseline: bytes, candidate: bytes) -> tuple[int, int] | None:
    """Return the minimal byte interval certainly introduced by one edit.

    The interval is deliberately narrower than an authored replacement when the
    replacement shares a prefix/suffix with baseline content. That makes later
    deletion ownership conservative: bytes outside this certainly-changed range
    are never considered repair-owned.
    """

    prefix = 0
    prefix_limit = min(len(baseline), len(candidate))
    while prefix < prefix_limit and baseline[prefix] == candidate[prefix]:
        prefix += 1

    baseline_suffix = len(baseline)
    candidate_suffix = len(candidate)
    while (
        baseline_suffix > prefix
        and candidate_suffix > prefix
        and baseline[baseline_suffix - 1] == candidate[candidate_suffix - 1]
    ):
        baseline_suffix -= 1
        candidate_suffix -= 1

    if candidate_suffix <= prefix:
        return None
    return prefix, candidate_suffix


def derive_authored_span_provenance(
    *,
    baseline_bytes: bytes,
    candidate_bytes: bytes,
    operation_index: int,
    operation_type: str,
    operation_count: int,
) -> AuthoredSpanProvenanceV1:
    """Derive conservative candidate-byte ownership for one direct edit."""

    if not isinstance(baseline_bytes, bytes) or not isinstance(candidate_bytes, bytes):
        raise TypeError("baseline_bytes and candidate_bytes must be bytes")
    if operation_count < 1:
        raise ValueError("operation_count must be positive")

    primitive = canonical_direct_repair_primitive(operation_type)
    if primitive is None:
        return AuthoredSpanProvenanceV1(
            operation_index=operation_index,
            primitive=operation_type or "unknown",
            disposition="unsupported_primitive",
        )
    if operation_count != 1:
        return AuthoredSpanProvenanceV1(
            operation_index=operation_index,
            primitive=primitive,
            disposition="ambiguous_composition",
        )

    span = _changed_candidate_span(baseline_bytes, candidate_bytes)
    if span is None:
        return AuthoredSpanProvenanceV1(
            operation_index=operation_index,
            primitive=primitive,
            disposition="no_changed_span",
        )
    start, end = span
    return AuthoredSpanProvenanceV1(
        operation_index=operation_index,
        primitive=primitive,
        disposition="owned",
        candidate_start_byte=start,
        candidate_end_byte=end,
        candidate_span_sha256=hashlib.sha256(candidate_bytes[start:end]).hexdigest(),
    )
