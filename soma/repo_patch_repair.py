"""Deterministic repair-proposal primitives for managed repository previews.

Gate 2 builds conservative evidence only. Nothing in this module applies source
bytes or chooses a repair on behalf of a controller.
"""

from __future__ import annotations

import hashlib
import io
import token
import tokenize
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .repo_candidate_validation import CandidateValidationV1


AUTHORED_SPAN_SCHEMA_VERSION: Final[str] = "repo_authored_span_provenance.v1"
TRANSPORT_LEAK_SCHEMA_VERSION: Final[str] = "repo_transport_leak_candidate.v1"
PYTHON_LOGICAL_LINE_PROOF_SCHEMA_VERSION: Final[str] = (
    "repo_python_logical_line_proof.v1"
)
PATCH_REPAIR_PROPOSAL_SCHEMA_VERSION: Final[str] = "repo_patch_repair_proposal.v1"
TRAILING_COMMIT_TITLE_RULE_ID: Final[str] = (
    "repo_preview.patch.trailing_commit_title.v1"
)
TRAILING_VIEW_RULE_ID: Final[str] = "repo_preview.patch.trailing_view.v1"
MAX_TRANSPORT_DELETED_EXCERPT_CHARS: Final[int] = 256

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


class TransportLeakCandidateV1(_FrozenRepairModel):
    """One exact deletion candidate produced by a versioned transport rule."""

    schema_version: Literal[TRANSPORT_LEAK_SCHEMA_VERSION] = TRANSPORT_LEAK_SCHEMA_VERSION
    rule_id: Literal[
        "repo_preview.patch.trailing_commit_title.v1",
        "repo_preview.patch.trailing_view.v1",
    ]
    rule_version: Literal["v1"] = "v1"
    operation_index: int = Field(ge=0)
    primitive: DirectRepairPrimitive
    deletion_start_byte: int = Field(ge=0)
    deletion_end_byte: int = Field(gt=0)
    deleted_bytes_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    deleted_excerpt_bounded: str = Field(max_length=MAX_TRANSPORT_DELETED_EXCERPT_CHARS)

    @model_validator(mode="after")
    def _validate_range(self):
        if self.deletion_end_byte <= self.deletion_start_byte:
            raise ValueError("transport deletion range must be non-empty")
        return self


class PythonLogicalLineProofV1(_FrozenRepairModel):
    """Mechanical proof that one deletion lands on a Python logical-line end."""

    schema_version: Literal[PYTHON_LOGICAL_LINE_PROOF_SCHEMA_VERSION] = (
        PYTHON_LOGICAL_LINE_PROOF_SCHEMA_VERSION
    )
    passed: bool
    reason: str = Field(min_length=1, max_length=128)
    deletion_start_byte: int = Field(ge=0)
    deletion_end_byte: int = Field(gt=0)
    original_candidate_invalid: bool
    repaired_candidate_valid: bool
    token_spans_cut: bool
    horizontal_whitespace_only: bool
    next_token_name: str | None = Field(default=None, max_length=64)
    repaired_candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PythonValidationSummaryV1(_FrozenRepairModel):
    baseline_disposition: str = Field(min_length=1, max_length=32)
    candidate_disposition: str = Field(min_length=1, max_length=32)
    regression_detected: bool
    diagnostic_code: str = Field(default="", max_length=128)


class RepairPayloadDescriptorV1(_FrozenRepairModel):
    file: str = Field(min_length=1, max_length=128, pattern=r"^repair_payload_[a-f0-9]{16}\.bin$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)


class PatchRepairProposalV1(_FrozenRepairModel):
    """One deterministic deletion-only proposal; never an apply decision."""

    schema_version: Literal[PATCH_REPAIR_PROPOSAL_SCHEMA_VERSION] = (
        PATCH_REPAIR_PROPOSAL_SCHEMA_VERSION
    )
    proposal_id: str = Field(pattern=r"^repair_[a-f0-9]{16}$")
    rule_id: Literal[
        "repo_preview.patch.trailing_commit_title.v1",
        "repo_preview.patch.trailing_view.v1",
    ]
    rule_version: Literal["v1"] = "v1"
    path: str = Field(min_length=1, max_length=1024)
    operation_index: int = Field(ge=0)
    primitive: DirectRepairPrimitive
    original_candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    repaired_candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    replacement_span_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    deletion_start_byte: int = Field(ge=0)
    deletion_end_byte: int = Field(gt=0)
    deleted_bytes_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    deleted_excerpt_bounded: str = Field(max_length=MAX_TRANSPORT_DELETED_EXCERPT_CHARS)
    python_validation_before: PythonValidationSummaryV1
    python_validation_after: PythonValidationSummaryV1
    logical_line_gate: PythonLogicalLineProofV1
    repaired_payload_descriptor: RepairPayloadDescriptorV1
    created_at: str = Field(min_length=1, max_length=128)


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


def _line_suffix_end(candidate_bytes: bytes, start: int) -> int:
    cr = candidate_bytes.find(b"\r", start)
    lf = candidate_bytes.find(b"\n", start)
    endings = [position for position in (cr, lf) if position >= 0]
    return min(endings) if endings else len(candidate_bytes)


def _bounded_deleted_excerpt(deleted: bytes) -> str:
    text = deleted.decode("utf-8", errors="backslashreplace")
    return text[:MAX_TRANSPORT_DELETED_EXCERPT_CHARS]


def detect_transport_leak_candidates(
    *,
    candidate_bytes: bytes,
    provenance: AuthoredSpanProvenanceV1,
) -> tuple[TransportLeakCandidateV1, ...]:
    """Detect only the two recovered schema-bound trailing transport signatures.

    Detection never proves intent and never selects bytes. A caller must require
    exactly one candidate and separately prove language structure before it may
    construct a repair proposal.
    """

    if not isinstance(candidate_bytes, bytes):
        raise TypeError("candidate_bytes must be bytes")
    if provenance.disposition != "owned":
        return ()
    if provenance.primitive not in {"exact_text", "line_range", "python_ast"}:
        return ()
    assert provenance.candidate_start_byte is not None
    assert provenance.candidate_end_byte is not None

    rules: tuple[tuple[str, bytes], ...] = (
        (TRAILING_COMMIT_TITLE_RULE_ID, b'}],"commit_title":"'),
        (TRAILING_VIEW_RULE_ID, b'}],"view":"'),
    )
    results: list[TransportLeakCandidateV1] = []
    owned_start = provenance.candidate_start_byte
    owned_end = provenance.candidate_end_byte

    for rule_id, marker in rules:
        search_at = owned_start
        while search_at < owned_end:
            match = candidate_bytes.find(marker, search_at, owned_end)
            if match < 0:
                break
            deletion_end = _line_suffix_end(candidate_bytes, match)
            if deletion_end <= owned_end:
                deleted = candidate_bytes[match:deletion_end]
                results.append(
                    TransportLeakCandidateV1(
                        rule_id=rule_id,
                        operation_index=provenance.operation_index,
                        primitive=provenance.primitive,
                        deletion_start_byte=match,
                        deletion_end_byte=deletion_end,
                        deleted_bytes_sha256=hashlib.sha256(deleted).hexdigest(),
                        deleted_excerpt_bounded=_bounded_deleted_excerpt(deleted),
                    )
                )
            search_at = match + len(marker)

    return tuple(sorted(results, key=lambda item: (item.deletion_start_byte, item.rule_id)))


def apply_transport_deletion(
    candidate_bytes: bytes,
    deletion: TransportLeakCandidateV1,
) -> bytes:
    """Delete exactly the detected byte interval and nothing else."""

    start = deletion.deletion_start_byte
    end = deletion.deletion_end_byte
    if end > len(candidate_bytes):
        raise ValueError("transport deletion exceeds candidate size")
    deleted = candidate_bytes[start:end]
    if hashlib.sha256(deleted).hexdigest() != deletion.deleted_bytes_sha256:
        raise ValueError("transport deletion bytes do not match detector evidence")
    return candidate_bytes[:start] + candidate_bytes[end:]


def _python_compiles(source: bytes, path: str) -> bool:
    try:
        compile(source, path, "exec", dont_inherit=True, optimize=0)
    except (SyntaxError, UnicodeError, ValueError):
        return False
    return True


def _line_byte_starts(text: str) -> tuple[list[str], list[int]]:
    lines = text.splitlines(keepends=True)
    if not lines and text == "":
        lines = [""]
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line.encode("utf-8"))
    return lines, starts


def _token_position_to_byte(
    lines: list[str],
    starts: list[int],
    row: int,
    column: int,
    source_size: int,
) -> int:
    if row < 1:
        return 0
    if row > len(lines):
        return source_size
    line = lines[row - 1]
    bounded_column = min(max(column, 0), len(line))
    return starts[row - 1] + len(line[:bounded_column].encode("utf-8"))


def prove_python_logical_line_deletion(
    *,
    path: str,
    candidate_bytes: bytes,
    deletion: TransportLeakCandidateV1,
) -> PythonLogicalLineProofV1:
    """Apply the exact G2.3 Python structural gate to one detected deletion."""

    original_invalid = not _python_compiles(candidate_bytes, path)
    try:
        repaired = apply_transport_deletion(candidate_bytes, deletion)
    except ValueError:
        repaired = candidate_bytes
    repaired_sha = hashlib.sha256(repaired).hexdigest()
    repaired_valid = _python_compiles(repaired, path)

    base = {
        "deletion_start_byte": deletion.deletion_start_byte,
        "deletion_end_byte": deletion.deletion_end_byte,
        "original_candidate_invalid": original_invalid,
        "repaired_candidate_valid": repaired_valid,
        "repaired_candidate_sha256": repaired_sha,
    }
    if not original_invalid:
        return PythonLogicalLineProofV1(
            passed=False,
            reason="original_candidate_valid",
            token_spans_cut=False,
            horizontal_whitespace_only=False,
            next_token_name=None,
            **base,
        )
    if not repaired_valid:
        return PythonLogicalLineProofV1(
            passed=False,
            reason="repaired_candidate_invalid",
            token_spans_cut=False,
            horizontal_whitespace_only=False,
            next_token_name=None,
            **base,
        )

    try:
        text = repaired.decode("utf-8")
        lines, starts = _line_byte_starts(text)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (UnicodeDecodeError, IndentationError, tokenize.TokenError, SyntaxError):
        return PythonLogicalLineProofV1(
            passed=False,
            reason="tokenize_failed",
            token_spans_cut=False,
            horizontal_whitespace_only=False,
            next_token_name=None,
            **base,
        )

    cut = deletion.deletion_start_byte
    positioned: list[tuple[tokenize.TokenInfo, int, int]] = []
    for info in tokens:
        start = _token_position_to_byte(
            lines, starts, info.start[0], info.start[1], len(repaired)
        )
        end = _token_position_to_byte(
            lines, starts, info.end[0], info.end[1], len(repaired)
        )
        positioned.append((info, start, end))

    spans_cut = any(start < cut < end for _, start, end in positioned)
    if spans_cut:
        return PythonLogicalLineProofV1(
            passed=False,
            reason="token_spans_deletion_cut",
            token_spans_cut=True,
            horizontal_whitespace_only=False,
            next_token_name=None,
            **base,
        )

    next_token: tuple[tokenize.TokenInfo, int, int] | None = None
    for positioned_token in positioned:
        info, start, _ = positioned_token
        if info.type == token.ENDMARKER and start < cut:
            continue
        if start >= cut:
            next_token = positioned_token
            break
    if next_token is None:
        return PythonLogicalLineProofV1(
            passed=False,
            reason="no_token_after_deletion_cut",
            token_spans_cut=False,
            horizontal_whitespace_only=False,
            next_token_name=None,
            **base,
        )

    info, token_start, _ = next_token
    gap = repaired[cut:token_start]
    horizontal_only = all(byte in b" \t\f" for byte in gap)
    token_name = token.tok_name.get(info.type, str(info.type))
    if not horizontal_only:
        return PythonLogicalLineProofV1(
            passed=False,
            reason="non_horizontal_bytes_after_cut",
            token_spans_cut=False,
            horizontal_whitespace_only=False,
            next_token_name=token_name,
            **base,
        )
    if info.type != token.NEWLINE:
        return PythonLogicalLineProofV1(
            passed=False,
            reason="next_token_not_logical_newline",
            token_spans_cut=False,
            horizontal_whitespace_only=True,
            next_token_name=token_name,
            **base,
        )
    return PythonLogicalLineProofV1(
        passed=True,
        reason="logical_newline",
        token_spans_cut=False,
        horizontal_whitespace_only=True,
        next_token_name=token_name,
        **base,
    )


def _validation_summary(validation: CandidateValidationV1) -> PythonValidationSummaryV1:
    return PythonValidationSummaryV1(
        baseline_disposition=validation.baseline_disposition,
        candidate_disposition=validation.candidate_disposition,
        regression_detected=validation.regression_detected,
        diagnostic_code=(validation.diagnostic.code if validation.diagnostic else ""),
    )


def build_patch_repair_proposal(
    *,
    path: str,
    candidate_bytes: bytes,
    candidate_validation: CandidateValidationV1 | dict,
    provenance: AuthoredSpanProvenanceV1 | dict,
    created_at: str,
) -> tuple[PatchRepairProposalV1 | None, bytes | None]:
    """Build at most one mechanically proven proposal for one candidate.

    Any ambiguity or failed gate returns ``(None, None)``. The original invalid
    candidate remains authoritative source-preview evidence.
    """

    try:
        validation = (
            candidate_validation
            if isinstance(candidate_validation, CandidateValidationV1)
            else CandidateValidationV1.model_validate(candidate_validation)
        )
        authored = (
            provenance
            if isinstance(provenance, AuthoredSpanProvenanceV1)
            else AuthoredSpanProvenanceV1.model_validate(provenance)
        )
        if not validation.regression_detected:
            return None, None
        if validation.baseline_disposition != "valid":
            return None, None
        if validation.candidate_disposition != "invalid":
            return None, None
        if authored.disposition != "owned" or authored.candidate_span_sha256 is None:
            return None, None

        detections = detect_transport_leak_candidates(
            candidate_bytes=candidate_bytes,
            provenance=authored,
        )
        if len(detections) != 1:
            return None, None
        deletion = detections[0]
        proof = prove_python_logical_line_deletion(
            path=path,
            candidate_bytes=candidate_bytes,
            deletion=deletion,
        )
        if not proof.passed:
            return None, None
        repaired = apply_transport_deletion(candidate_bytes, deletion)
        repaired_sha = hashlib.sha256(repaired).hexdigest()
        if repaired_sha != proof.repaired_candidate_sha256:
            return None, None

        original_sha = hashlib.sha256(candidate_bytes).hexdigest()
        identity = "\0".join(
            (
                "soma.repo_patch_repair_proposal.v1",
                deletion.rule_id,
                path,
                str(deletion.operation_index),
                deletion.primitive,
                original_sha,
                repaired_sha,
                authored.candidate_span_sha256,
                str(deletion.deletion_start_byte),
                str(deletion.deletion_end_byte),
                deletion.deleted_bytes_sha256,
            )
        ).encode("utf-8")
        suffix = hashlib.sha256(identity).hexdigest()[:16]
        proposal_id = f"repair_{suffix}"
        descriptor = RepairPayloadDescriptorV1(
            file=f"repair_payload_{suffix}.bin",
            sha256=repaired_sha,
            size_bytes=len(repaired),
        )
        before = _validation_summary(validation)
        after = PythonValidationSummaryV1(
            baseline_disposition=validation.baseline_disposition,
            candidate_disposition="valid",
            regression_detected=False,
            diagnostic_code="",
        )
        proposal = PatchRepairProposalV1(
            proposal_id=proposal_id,
            rule_id=deletion.rule_id,
            path=path,
            operation_index=deletion.operation_index,
            primitive=deletion.primitive,
            original_candidate_sha256=original_sha,
            repaired_candidate_sha256=repaired_sha,
            replacement_span_hash=authored.candidate_span_sha256,
            deletion_start_byte=deletion.deletion_start_byte,
            deletion_end_byte=deletion.deletion_end_byte,
            deleted_bytes_sha256=deletion.deleted_bytes_sha256,
            deleted_excerpt_bounded=deletion.deleted_excerpt_bounded,
            python_validation_before=before,
            python_validation_after=after,
            logical_line_gate=proof,
            repaired_payload_descriptor=descriptor,
            created_at=created_at,
        )
        return proposal, repaired
    except (TypeError, ValueError):
        return None, None
