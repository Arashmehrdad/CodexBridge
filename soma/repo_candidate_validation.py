"""Pure bounded candidate-language validation for managed repository previews.

This module has no repository, network, model, import, or execution authority. It
receives already-materialized source bytes and returns deterministic mechanical
validation evidence suitable for later attachment to an opaque preview bundle.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CANDIDATE_VALIDATION_SCHEMA_VERSION: Final[str] = "repo_candidate_validation.v1"
PYTHON_CANDIDATE_VALIDATOR: Final[str] = "python.compile"
PYTHON_CANDIDATE_VALIDATOR_VERSION: Final[str] = (
    f"{sys.implementation.name}-{sys.version_info.major}."
    f"{sys.version_info.minor}.{sys.version_info.micro}"
)
JSON_CANDIDATE_VALIDATOR: Final[str] = "json.loads.strict"
JSON_CANDIDATE_VALIDATOR_VERSION: Final[str] = (
    f"{sys.implementation.name}-{sys.version_info.major}."
    f"{sys.version_info.minor}.{sys.version_info.micro}"
)
JSON_ENCODING_POLICY: Final[str] = "utf-8-strict"
JSON_DUPLICATE_KEY_POLICY: Final[str] = "reject"
JSON_NONFINITE_NUMBER_POLICY: Final[str] = "reject"

MAX_CANDIDATE_VALIDATION_FILE_BYTES: Final[int] = 512 * 1024
MAX_CANDIDATE_VALIDATION_TOTAL_BYTES: Final[int] = 2 * 1024 * 1024
MAX_CANDIDATE_VALIDATION_FILES: Final[int] = 20
MAX_CANDIDATE_VALIDATION_WALL_SECONDS: Final[float] = 2.0
MAX_CANDIDATE_DIAGNOSTIC_MESSAGE_CHARS: Final[int] = 512
MAX_CANDIDATE_DIAGNOSTIC_EXCEPTION_CHARS: Final[int] = 128

CandidateLanguage = Literal["python", "json", "toml", "none"]
BaselineDisposition = Literal["valid", "invalid", "not_applicable", "not_checked"]
CandidateDisposition = Literal["valid", "invalid", "budget_skipped", "not_applicable"]


class _FrozenCandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CandidateDiagnosticV1(_FrozenCandidateModel):
    """One bounded mechanical validation diagnostic."""

    code: str = Field(min_length=1, max_length=128)
    message: str = Field(
        min_length=1, max_length=MAX_CANDIDATE_DIAGNOSTIC_MESSAGE_CHARS
    )
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    exception_type: str | None = Field(
        default=None, max_length=MAX_CANDIDATE_DIAGNOSTIC_EXCEPTION_CHARS
    )


class CandidateValidationV1(_FrozenCandidateModel):
    """Bounded deterministic validation evidence for one materialized candidate."""

    schema_version: Literal[CANDIDATE_VALIDATION_SCHEMA_VERSION] = (
        CANDIDATE_VALIDATION_SCHEMA_VERSION
    )
    path: str = Field(min_length=1, max_length=1024)
    language: CandidateLanguage
    baseline_disposition: BaselineDisposition
    candidate_disposition: CandidateDisposition
    validator: str = Field(min_length=1, max_length=128)
    validator_version: str = Field(min_length=1, max_length=128)
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_size_bytes: int = Field(ge=0)
    diagnostic: CandidateDiagnosticV1 | None = None
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    regression_detected: bool

    @model_validator(mode="after")
    def _validate_consistency(self):
        expected_regression = (
            self.baseline_disposition == "valid"
            and self.candidate_disposition == "invalid"
        )
        if self.regression_detected != expected_regression:
            raise ValueError(
                "regression_detected must mean baseline valid and candidate invalid"
            )
        if self.candidate_disposition == "invalid" and self.diagnostic is None:
            raise ValueError("invalid candidate validation requires a diagnostic")
        if self.candidate_disposition == "budget_skipped" and self.diagnostic is None:
            raise ValueError(
                "budget-skipped candidate validation requires a diagnostic"
            )
        return self


@dataclass
class CandidateValidationBudget:
    """Shared per-preview candidate-validation accounting and wall-time budget."""

    max_file_bytes: int = MAX_CANDIDATE_VALIDATION_FILE_BYTES
    max_total_bytes: int = MAX_CANDIDATE_VALIDATION_TOTAL_BYTES
    max_files: int = MAX_CANDIDATE_VALIDATION_FILES
    max_wall_seconds: float = MAX_CANDIDATE_VALIDATION_WALL_SECONDS
    clock: Callable[[], float] = time.perf_counter
    used_files: int = field(default=0, init=False)
    used_bytes: int = field(default=0, init=False)
    _started_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_file_bytes < 0:
            raise ValueError("max_file_bytes must be non-negative")
        if self.max_total_bytes < 0:
            raise ValueError("max_total_bytes must be non-negative")
        if self.max_files < 0:
            raise ValueError("max_files must be non-negative")
        if not math.isfinite(self.max_wall_seconds) or self.max_wall_seconds < 0:
            raise ValueError("max_wall_seconds must be finite and non-negative")
        self._started_at = self.clock()

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.clock() - self._started_at)

    def reserve(self, candidate_size_bytes: int) -> str | None:
        """Reserve one candidate or return a deterministic skip-reason code."""

        if candidate_size_bytes < 0:
            raise ValueError("candidate_size_bytes must be non-negative")
        if candidate_size_bytes > self.max_file_bytes:
            return "candidate_file_budget_exceeded"
        if self.used_files >= self.max_files:
            return "candidate_file_count_budget_exhausted"
        if self.used_bytes + candidate_size_bytes > self.max_total_bytes:
            return "candidate_total_byte_budget_exhausted"
        if self.elapsed_seconds >= self.max_wall_seconds:
            return "candidate_wall_time_budget_exhausted"
        self.used_files += 1
        self.used_bytes += candidate_size_bytes
        return None


def _bounded_message(value: object, *, fallback: str) -> str:
    text = " ".join(str(value or fallback).splitlines()).strip() or fallback
    return text[:MAX_CANDIDATE_DIAGNOSTIC_MESSAGE_CHARS]


def _syntax_diagnostic(exc: BaseException) -> CandidateDiagnosticV1:
    line: int | None = None
    column: int | None = None
    message_source: object = exc
    if isinstance(exc, SyntaxError):
        message_source = exc.msg
        if isinstance(exc.lineno, int) and exc.lineno >= 1:
            line = exc.lineno
        if isinstance(exc.offset, int) and exc.offset >= 1:
            column = exc.offset
    return CandidateDiagnosticV1(
        code="python_syntax_error",
        message=_bounded_message(
            message_source, fallback="Python candidate is invalid"
        ),
        line=line,
        column=column,
        exception_type=type(exc).__name__[:MAX_CANDIDATE_DIAGNOSTIC_EXCEPTION_CHARS],
    )


def _compile_disposition(
    source: bytes, path: str
) -> tuple[Literal["valid", "invalid"], CandidateDiagnosticV1 | None]:
    try:
        compile(source, path, "exec", dont_inherit=True, optimize=0)
    except (SyntaxError, UnicodeError, ValueError) as exc:
        return "invalid", _syntax_diagnostic(exc)
    return "valid", None


class _DuplicateJsonKey(ValueError):
    pass


class _InvalidJsonConstant(ValueError):
    pass


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_nonfinite_json_constant(value: str) -> object:
    raise _InvalidJsonConstant(value)


def _json_diagnostic(exc: BaseException) -> CandidateDiagnosticV1:
    if isinstance(exc, UnicodeDecodeError):
        return CandidateDiagnosticV1(
            code="json_encoding_error",
            message="JSON candidate must be valid UTF-8",
            exception_type=type(exc).__name__,
        )
    if isinstance(exc, _DuplicateJsonKey):
        return CandidateDiagnosticV1(
            code="json_duplicate_key",
            message="JSON object contains a duplicate member name",
            exception_type=type(exc).__name__,
        )
    if isinstance(exc, _InvalidJsonConstant):
        return CandidateDiagnosticV1(
            code="json_nonfinite_number",
            message="JSON candidate contains a non-finite numeric constant",
            exception_type=type(exc).__name__,
        )
    if isinstance(exc, RecursionError):
        return CandidateDiagnosticV1(
            code="json_nesting_error",
            message="JSON candidate nesting exceeds parser limits",
            exception_type=type(exc).__name__,
        )
    line: int | None = None
    column: int | None = None
    message_source: object = exc
    if isinstance(exc, json.JSONDecodeError):
        message_source = exc.msg
        if exc.lineno >= 1:
            line = exc.lineno
        if exc.colno >= 1:
            column = exc.colno
    return CandidateDiagnosticV1(
        code="json_syntax_error",
        message=_bounded_message(message_source, fallback="JSON candidate is invalid"),
        line=line,
        column=column,
        exception_type=type(exc).__name__[:MAX_CANDIDATE_DIAGNOSTIC_EXCEPTION_CHARS],
    )


def _json_disposition(
    source: bytes,
) -> tuple[Literal["valid", "invalid"], CandidateDiagnosticV1 | None]:
    try:
        text = source.decode("utf-8", errors="strict")
        json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_constant,
            parse_int=str,
            parse_float=str,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateJsonKey,
        _InvalidJsonConstant,
        RecursionError,
    ) as exc:
        return "invalid", _json_diagnostic(exc)
    return "valid", None


def _elapsed_ms(clock: Callable[[], float], started_at: float) -> float:
    return max(0.0, (clock() - started_at) * 1000.0)


def validate_python_candidate(
    *,
    path: str,
    candidate_bytes: bytes,
    baseline_bytes: bytes | None,
    budget: CandidateValidationBudget | None = None,
) -> CandidateValidationV1:
    """Compile Python source without importing or executing it.

    ``baseline_bytes=None`` represents a create-file candidate. Budget accounting
    charges one materialized candidate file/byte body, while wall time covers all
    parser work including optional baseline compilation.
    """

    if not isinstance(candidate_bytes, bytes):
        raise TypeError("candidate_bytes must be bytes")
    if baseline_bytes is not None and not isinstance(baseline_bytes, bytes):
        raise TypeError("baseline_bytes must be bytes or None")

    active_budget = budget or CandidateValidationBudget()
    started_at = active_budget.clock()
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_size_bytes = len(candidate_bytes)
    skip_reason = active_budget.reserve(candidate_size_bytes)
    if skip_reason is not None:
        return CandidateValidationV1(
            path=path,
            language="python",
            baseline_disposition=(
                "not_applicable" if baseline_bytes is None else "not_checked"
            ),
            candidate_disposition="budget_skipped",
            validator=PYTHON_CANDIDATE_VALIDATOR,
            validator_version=PYTHON_CANDIDATE_VALIDATOR_VERSION,
            candidate_sha256=candidate_sha256,
            candidate_size_bytes=candidate_size_bytes,
            diagnostic=CandidateDiagnosticV1(
                code=skip_reason,
                message=f"Python candidate validation skipped: {skip_reason}",
            ),
            elapsed_ms=_elapsed_ms(active_budget.clock, started_at),
            regression_detected=False,
        )

    baseline_disposition: BaselineDisposition
    if baseline_bytes is None:
        baseline_disposition = "not_applicable"
    else:
        baseline_disposition, _ = _compile_disposition(baseline_bytes, path)

    candidate_disposition, diagnostic = _compile_disposition(candidate_bytes, path)
    return CandidateValidationV1(
        path=path,
        language="python",
        baseline_disposition=baseline_disposition,
        candidate_disposition=candidate_disposition,
        validator=PYTHON_CANDIDATE_VALIDATOR,
        validator_version=PYTHON_CANDIDATE_VALIDATOR_VERSION,
        candidate_sha256=candidate_sha256,
        candidate_size_bytes=candidate_size_bytes,
        diagnostic=diagnostic,
        elapsed_ms=_elapsed_ms(active_budget.clock, started_at),
        regression_detected=(
            baseline_disposition == "valid" and candidate_disposition == "invalid"
        ),
    )


def validate_json_candidate(
    *,
    path: str,
    candidate_bytes: bytes,
    baseline_bytes: bytes | None,
    budget: CandidateValidationBudget | None = None,
) -> CandidateValidationV1:
    """Validate one complete UTF-8 JSON document without executing source.

    Duplicate object member names and non-finite numeric constants are rejected
    explicitly so validation does not inherit permissive ``json.loads`` behavior.
    ``baseline_bytes=None`` is diagnostic-only create-file validation and cannot
    establish a regression by itself.
    """

    if not isinstance(candidate_bytes, bytes):
        raise TypeError("candidate_bytes must be bytes")
    if baseline_bytes is not None and not isinstance(baseline_bytes, bytes):
        raise TypeError("baseline_bytes must be bytes or None")

    active_budget = budget or CandidateValidationBudget()
    started_at = active_budget.clock()
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_size_bytes = len(candidate_bytes)
    skip_reason = active_budget.reserve(candidate_size_bytes)
    if skip_reason is not None:
        return CandidateValidationV1(
            path=path,
            language="json",
            baseline_disposition=(
                "not_applicable" if baseline_bytes is None else "not_checked"
            ),
            candidate_disposition="budget_skipped",
            validator=JSON_CANDIDATE_VALIDATOR,
            validator_version=JSON_CANDIDATE_VALIDATOR_VERSION,
            candidate_sha256=candidate_sha256,
            candidate_size_bytes=candidate_size_bytes,
            diagnostic=CandidateDiagnosticV1(
                code=skip_reason,
                message=f"JSON candidate validation skipped: {skip_reason}",
            ),
            elapsed_ms=_elapsed_ms(active_budget.clock, started_at),
            regression_detected=False,
        )

    baseline_disposition: BaselineDisposition
    if baseline_bytes is None:
        baseline_disposition = "not_applicable"
    else:
        baseline_disposition, _ = _json_disposition(baseline_bytes)

    candidate_disposition, diagnostic = _json_disposition(candidate_bytes)
    return CandidateValidationV1(
        path=path,
        language="json",
        baseline_disposition=baseline_disposition,
        candidate_disposition=candidate_disposition,
        validator=JSON_CANDIDATE_VALIDATOR,
        validator_version=JSON_CANDIDATE_VALIDATOR_VERSION,
        candidate_sha256=candidate_sha256,
        candidate_size_bytes=candidate_size_bytes,
        diagnostic=diagnostic,
        elapsed_ms=_elapsed_ms(active_budget.clock, started_at),
        regression_detected=(
            baseline_disposition == "valid" and candidate_disposition == "invalid"
        ),
    )
