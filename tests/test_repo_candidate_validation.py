from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

import soma.repo_candidate_validation as validation
from soma.repo_candidate_validation import (
    CANDIDATE_VALIDATION_SCHEMA_VERSION,
    MAX_CANDIDATE_DIAGNOSTIC_MESSAGE_CHARS,
    MAX_CANDIDATE_VALIDATION_FILE_BYTES,
    MAX_CANDIDATE_VALIDATION_FILES,
    MAX_CANDIDATE_VALIDATION_TOTAL_BYTES,
    MAX_CANDIDATE_VALIDATION_WALL_SECONDS,
    CandidateValidationBudget,
    validate_python_candidate,
)


def test_baseline_valid_candidate_valid() -> None:
    candidate = b"value = 2\n"
    result = validate_python_candidate(
        path="sample.py",
        baseline_bytes=b"value = 1\n",
        candidate_bytes=candidate,
    )

    assert result.schema_version == CANDIDATE_VALIDATION_SCHEMA_VERSION
    assert result.language == "python"
    assert result.baseline_disposition == "valid"
    assert result.candidate_disposition == "valid"
    assert result.regression_detected is False
    assert result.diagnostic is None
    assert result.candidate_sha256 == hashlib.sha256(candidate).hexdigest()
    assert result.candidate_size_bytes == len(candidate)


def test_baseline_valid_candidate_invalid_is_regression() -> None:
    result = validate_python_candidate(
        path="broken.py",
        baseline_bytes=b"value = 1\n",
        candidate_bytes=b"value = (\n",
    )

    assert result.baseline_disposition == "valid"
    assert result.candidate_disposition == "invalid"
    assert result.regression_detected is True
    assert result.diagnostic is not None
    assert result.diagnostic.code == "python_syntax_error"
    assert result.diagnostic.line == 1
    assert result.diagnostic.exception_type == "SyntaxError"


def test_baseline_invalid_candidate_invalid_is_not_new_regression() -> None:
    result = validate_python_candidate(
        path="already_broken.py",
        baseline_bytes=b"baseline = (\n",
        candidate_bytes=b"candidate = (\n",
    )

    assert result.baseline_disposition == "invalid"
    assert result.candidate_disposition == "invalid"
    assert result.regression_detected is False


def test_create_candidate_has_no_baseline_authority() -> None:
    result = validate_python_candidate(
        path="created.py",
        baseline_bytes=None,
        candidate_bytes=b"created = (\n",
    )

    assert result.baseline_disposition == "not_applicable"
    assert result.candidate_disposition == "invalid"
    assert result.regression_detected is False


def test_syntax_diagnostic_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_compile(*_args, **_kwargs):
        raise SyntaxError("x" * (MAX_CANDIDATE_DIAGNOSTIC_MESSAGE_CHARS * 4))

    monkeypatch.setattr(validation, "compile", fail_compile, raising=False)
    result = validate_python_candidate(
        path="bounded.py",
        baseline_bytes=None,
        candidate_bytes=b"x = 1\n",
    )

    assert result.candidate_disposition == "invalid"
    assert result.diagnostic is not None
    assert len(result.diagnostic.message) == MAX_CANDIDATE_DIAGNOSTIC_MESSAGE_CHARS


def test_unicode_python_candidate_compiles() -> None:
    candidate = "π = 3.14\nپیام = 'سلام'\n".encode()
    result = validate_python_candidate(
        path="unicode.py",
        baseline_bytes=b"value = 1\n",
        candidate_bytes=candidate,
    )

    assert result.candidate_disposition == "valid"


@pytest.mark.parametrize(
    "candidate",
    [
        b"alpha = 1\nbeta = 2\n",
        b"alpha = 1\r\nbeta = 2\r\n",
        b"alpha = 1",
    ],
)
def test_newline_forms_and_missing_eof_newline_compile(candidate: bytes) -> None:
    result = validate_python_candidate(
        path="newlines.py",
        baseline_bytes=b"alpha = 0\n",
        candidate_bytes=candidate,
    )

    assert result.candidate_disposition == "valid"


def test_exact_512kib_candidate_is_allowed_and_next_byte_is_skipped() -> None:
    exact = b"#" + (b"a" * (MAX_CANDIDATE_VALIDATION_FILE_BYTES - 1))
    exact_result = validate_python_candidate(
        path="exact.py",
        baseline_bytes=None,
        candidate_bytes=exact,
    )
    too_large = exact + b"a"
    large_result = validate_python_candidate(
        path="large.py",
        baseline_bytes=None,
        candidate_bytes=too_large,
    )

    assert exact_result.candidate_size_bytes == MAX_CANDIDATE_VALIDATION_FILE_BYTES
    assert exact_result.candidate_disposition == "valid"
    assert large_result.candidate_disposition == "budget_skipped"
    assert large_result.diagnostic is not None
    assert large_result.diagnostic.code == "candidate_file_budget_exceeded"


def test_per_preview_file_budget_accounting() -> None:
    budget = CandidateValidationBudget(max_files=2)

    first = validate_python_candidate(
        path="one.py", baseline_bytes=None, candidate_bytes=b"x = 1\n", budget=budget
    )
    second = validate_python_candidate(
        path="two.py", baseline_bytes=None, candidate_bytes=b"x = 2\n", budget=budget
    )
    third = validate_python_candidate(
        path="three.py", baseline_bytes=None, candidate_bytes=b"x = 3\n", budget=budget
    )

    assert first.candidate_disposition == "valid"
    assert second.candidate_disposition == "valid"
    assert third.candidate_disposition == "budget_skipped"
    assert third.diagnostic is not None
    assert third.diagnostic.code == "candidate_file_count_budget_exhausted"
    assert budget.used_files == 2
    assert budget.used_bytes == 12


def test_per_preview_total_byte_budget_accounting() -> None:
    budget = CandidateValidationBudget(max_total_bytes=8)

    first = validate_python_candidate(
        path="one.py", baseline_bytes=None, candidate_bytes=b"x=1\n", budget=budget
    )
    second = validate_python_candidate(
        path="two.py", baseline_bytes=None, candidate_bytes=b"y=2\n", budget=budget
    )
    third = validate_python_candidate(
        path="three.py", baseline_bytes=None, candidate_bytes=b"z\n", budget=budget
    )

    assert first.candidate_disposition == "valid"
    assert second.candidate_disposition == "valid"
    assert third.candidate_disposition == "budget_skipped"
    assert third.diagnostic is not None
    assert third.diagnostic.code == "candidate_total_byte_budget_exhausted"
    assert budget.used_files == 2
    assert budget.used_bytes == 8


def test_budget_skip_is_deterministic() -> None:
    budget_a = CandidateValidationBudget(max_files=0, clock=lambda: 10.0)
    budget_b = CandidateValidationBudget(max_files=0, clock=lambda: 10.0)

    first = validate_python_candidate(
        path="same.py",
        baseline_bytes=b"x=0\n",
        candidate_bytes=b"x=1\n",
        budget=budget_a,
    )
    second = validate_python_candidate(
        path="same.py",
        baseline_bytes=b"x=0\n",
        candidate_bytes=b"x=1\n",
        budget=budget_b,
    )

    assert first == second
    assert first.baseline_disposition == "not_checked"
    assert first.candidate_disposition == "budget_skipped"
    assert first.diagnostic is not None
    assert first.diagnostic.code == "candidate_file_count_budget_exhausted"


def test_wall_budget_can_be_tested_without_sleeping() -> None:
    budget = CandidateValidationBudget(max_wall_seconds=0.0, clock=lambda: 50.0)
    result = validate_python_candidate(
        path="wall.py",
        baseline_bytes=b"x=0\n",
        candidate_bytes=b"x=1\n",
        budget=budget,
    )

    assert result.candidate_disposition == "budget_skipped"
    assert result.diagnostic is not None
    assert result.diagnostic.code == "candidate_wall_time_budget_exhausted"


def test_default_budget_constants_are_frozen() -> None:
    budget = CandidateValidationBudget(clock=lambda: 0.0)

    assert budget.max_file_bytes == MAX_CANDIDATE_VALIDATION_FILE_BYTES == 512 * 1024
    assert (
        budget.max_total_bytes
        == MAX_CANDIDATE_VALIDATION_TOTAL_BYTES
        == 2 * 1024 * 1024
    )
    assert budget.max_files == MAX_CANDIDATE_VALIDATION_FILES == 20
    assert budget.max_wall_seconds == MAX_CANDIDATE_VALIDATION_WALL_SECONDS == 2.0


def test_validation_does_not_import_or_execute_source(tmp_path: Path) -> None:
    fake_module = "soma_candidate_validation_should_never_import_this"
    target = tmp_path / "should_not_exist.txt"
    source = (
        f"import {fake_module}\n"
        f"open({str(target)!r}, 'w', encoding='utf-8').write('executed')\n"
        "raise RuntimeError('executed')\n"
    ).encode()

    assert fake_module not in sys.modules
    result = validate_python_candidate(
        path="no_execute.py",
        baseline_bytes=b"x = 1\n",
        candidate_bytes=source,
    )

    assert result.candidate_disposition == "valid"
    assert fake_module not in sys.modules
    assert target.exists() is False


def test_validation_does_not_read_or_write_path(tmp_path: Path) -> None:
    claimed_path = tmp_path / "not_a_real_repo_file.py"
    result = validate_python_candidate(
        path=str(claimed_path),
        baseline_bytes=None,
        candidate_bytes=b"value = 1\n",
    )

    assert result.candidate_disposition == "valid"
    assert claimed_path.exists() is False
