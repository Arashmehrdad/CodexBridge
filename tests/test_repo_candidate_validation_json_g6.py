from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import soma.repo_writer as rw
from soma.repo_candidate_validation import (
    JSON_CANDIDATE_VALIDATOR,
    JSON_DUPLICATE_KEY_POLICY,
    JSON_ENCODING_POLICY,
    JSON_NONFINITE_NUMBER_POLICY,
    MAX_CANDIDATE_DIAGNOSTIC_MESSAGE_CHARS,
    MAX_CANDIDATE_VALIDATION_FILE_BYTES,
    CandidateValidationBudget,
    validate_json_candidate,
    validate_python_candidate,
)
from soma.repo_patch_resolution_service import resolve_patch_preview
from soma.repo_writer import (
    apply_previewed_repo_change,
    get_patch_status,
    preview_repo_file_creation,
    preview_repo_patch,
    revert_managed_patch,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _patch_dir(runs: Path, patch_id: str) -> Path:
    return runs / "managed_patches" / patch_id


def _manifest(runs: Path, patch_id: str) -> dict:
    return json.loads(
        (_patch_dir(runs, patch_id) / "manifest.json").read_text(encoding="utf-8")
    )


def _invalid_json_source(
    repo: Path,
    runs: Path,
    *,
    name: str = "config.json",
) -> tuple[Path, bytes, bytes, dict]:
    target = repo / name
    baseline = b'{"enabled": true, "count": 1}\n'
    candidate = b'{"enabled": true, "count": }\n'
    _write(target, baseline)
    source = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": name,
                "expected_sha256": _sha(target),
                "old_text": baseline.decode(),
                "new_text": candidate.decode(),
            }
        ],
        runs,
    )
    return target, baseline, candidate, source


def test_g6_1_json_valid_baseline_and_candidate() -> None:
    candidate = b'{"name":"soma","items":[1,2,3],"ok":true}\n'
    result = validate_json_candidate(
        path="config.json",
        baseline_bytes=b'{"name":"soma","items":[1],"ok":true}\n',
        candidate_bytes=candidate,
    )

    assert result.language == "json"
    assert result.validator == JSON_CANDIDATE_VALIDATOR
    assert result.baseline_disposition == "valid"
    assert result.candidate_disposition == "valid"
    assert result.regression_detected is False
    assert result.diagnostic is None
    assert result.candidate_sha256 == hashlib.sha256(candidate).hexdigest()


def test_g6_1_valid_json_to_invalid_json_is_regression() -> None:
    result = validate_json_candidate(
        path="broken.json",
        baseline_bytes=b'{"value":1}\n',
        candidate_bytes=b'{\n  "value":\n}\n',
    )

    assert result.baseline_disposition == "valid"
    assert result.candidate_disposition == "invalid"
    assert result.regression_detected is True
    assert result.diagnostic is not None
    assert result.diagnostic.code == "json_syntax_error"
    assert result.diagnostic.line is not None
    assert result.diagnostic.column is not None
    assert len(result.diagnostic.message) <= MAX_CANDIDATE_DIAGNOSTIC_MESSAGE_CHARS


def test_g6_1_duplicate_member_names_are_rejected_and_policy_is_frozen() -> None:
    result = validate_json_candidate(
        path="duplicate.json",
        baseline_bytes=b'{"value":1}\n',
        candidate_bytes=b'{"value":1,"value":2}\n',
    )

    assert JSON_DUPLICATE_KEY_POLICY == "reject"
    assert result.candidate_disposition == "invalid"
    assert result.regression_detected is True
    assert result.diagnostic is not None
    assert result.diagnostic.code == "json_duplicate_key"
    assert "value" not in result.diagnostic.message


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity"])
def test_g6_1_nonfinite_json_constants_are_rejected(constant: bytes) -> None:
    result = validate_json_candidate(
        path="number.json",
        baseline_bytes=b'{"value":1}\n',
        candidate_bytes=b'{"value":' + constant + b"}\n",
    )

    assert JSON_NONFINITE_NUMBER_POLICY == "reject"
    assert result.candidate_disposition == "invalid"
    assert result.diagnostic is not None
    assert result.diagnostic.code == "json_nonfinite_number"


def test_g6_1_json_encoding_policy_is_strict_utf8() -> None:
    result = validate_json_candidate(
        path="encoding.json",
        baseline_bytes=b'{"value":"ok"}\n',
        candidate_bytes=b'{"value":"\xff"}\n',
    )

    assert JSON_ENCODING_POLICY == "utf-8-strict"
    assert result.candidate_disposition == "invalid"
    assert result.regression_detected is True
    assert result.diagnostic is not None
    assert result.diagnostic.code == "json_encoding_error"


def test_g6_1_complete_document_rejects_trailing_non_json_text() -> None:
    result = validate_json_candidate(
        path="trailing.json",
        baseline_bytes=b'{"value":1}\n',
        candidate_bytes=b'{"value":1}\nnot-json\n',
    )

    assert result.candidate_disposition == "invalid"
    assert result.diagnostic is not None
    assert result.diagnostic.code == "json_syntax_error"


@pytest.mark.parametrize("document", [b"42", b"true", b"null", b'"scalar"'])
def test_g6_1_complete_json_scalar_documents_are_valid(document: bytes) -> None:
    result = validate_json_candidate(
        path="scalar.json",
        baseline_bytes=b"null",
        candidate_bytes=document,
    )

    assert result.candidate_disposition == "valid"


def test_g6_1_large_numeric_token_is_syntax_valid_without_int_conversion() -> None:
    candidate = b'{"number":' + (b"9" * 10_000) + b"}\n"
    result = validate_json_candidate(
        path="huge_number.json",
        baseline_bytes=b'{"number":1}\n',
        candidate_bytes=candidate,
    )

    assert result.candidate_disposition == "valid"


def test_g6_1_excessive_nesting_becomes_bounded_invalid_evidence() -> None:
    candidate = (b"[" * 2_000) + b"0" + (b"]" * 2_000)
    result = validate_json_candidate(
        path="deep.json",
        baseline_bytes=b"[0]",
        candidate_bytes=candidate,
    )

    assert result.candidate_disposition == "invalid"
    assert result.diagnostic is not None
    assert result.diagnostic.code == "json_nesting_error"


def test_g6_1_exact_file_budget_boundary_and_next_byte_skip() -> None:
    prefix = b'{"payload":"'
    suffix = b'"}'
    fill = MAX_CANDIDATE_VALIDATION_FILE_BYTES - len(prefix) - len(suffix)
    exact = prefix + (b"a" * fill) + suffix
    assert len(exact) == MAX_CANDIDATE_VALIDATION_FILE_BYTES

    exact_result = validate_json_candidate(
        path="exact.json",
        baseline_bytes=None,
        candidate_bytes=exact,
    )
    too_large = exact + b" "
    large_result = validate_json_candidate(
        path="large.json",
        baseline_bytes=None,
        candidate_bytes=too_large,
    )

    assert exact_result.candidate_disposition == "valid"
    assert large_result.candidate_disposition == "budget_skipped"
    assert large_result.diagnostic is not None
    assert large_result.diagnostic.code == "candidate_file_budget_exceeded"


def test_g6_1_json_and_python_share_one_preview_budget_contract() -> None:
    budget = CandidateValidationBudget(max_files=1, clock=lambda: 0.0)
    json_result = validate_json_candidate(
        path="one.json",
        baseline_bytes=None,
        candidate_bytes=b'{"value":1}',
        budget=budget,
    )
    python_result = validate_python_candidate(
        path="two.py",
        baseline_bytes=None,
        candidate_bytes=b"value = 1\n",
        budget=budget,
    )

    assert json_result.candidate_disposition == "valid"
    assert python_result.candidate_disposition == "budget_skipped"
    assert budget.used_files == 1


def test_g6_1_modified_json_regression_requires_resolution_without_repair(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, _, source = _invalid_json_source(repo, runs)
    manifest = _manifest(runs, source["patch_id"])
    evidence = manifest["operations"][0]["candidate_validation"]

    assert target.read_bytes() == baseline
    assert source["ok"] is False
    assert source["applicable"] is False
    assert source["resolution_required"] is True
    assert source["repair_available"] is False
    assert source["repair_proposal_id"] == ""
    assert source["candidate_validation_status"] == "regression_detected"
    assert manifest["status"] == "preview_resolution_required"
    assert manifest["repair_proposal"] is None
    assert evidence["language"] == "json"
    assert evidence["regression_detected"] is True
    assert list(_patch_dir(runs, source["patch_id"]).glob("repair_payload_*.bin")) == []


def test_g6_1_json_never_calls_transport_repair_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "no_repair.json"
    _write(target, b'{"value":1}\n')

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "JSON candidate validation must not enter repair synthesis"
        )

    monkeypatch.setattr(rw, "build_patch_repair_proposal", forbidden)
    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": target.name,
                "expected_sha256": _sha(target),
                "old_text": '{"value":1}',
                "new_text": '{"value":}',
            }
        ],
        runs,
    )

    assert preview["resolution_required"] is True
    assert preview["repair_available"] is False


def test_g6_1_accept_original_is_explicit_json_validation_override(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, candidate, source = _invalid_json_source(repo, runs)

    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="g6-json-accept-original",
        decision="accept_original",
    )
    child_status = get_patch_status(repo, child["patch_id"], runs)
    source_status = get_patch_status(repo, source["patch_id"], runs)

    assert source_status["status"] == "resolved"
    assert child_status["status"] == "preview_ok"
    assert child_status["candidate_validation_override"] == "accept_original"
    assert child_status["candidate_validation_status"] == "regression_detected"

    applied = apply_previewed_repo_change(repo, child["patch_id"], runs)
    assert applied["ok"] is True
    assert target.read_bytes() == candidate
    reverted = revert_managed_patch(repo, child["patch_id"], runs)
    assert reverted["ok"] is True
    assert target.read_bytes() == baseline
    assert get_patch_status(repo, source["patch_id"], runs)["status"] == "resolved"


def test_g6_1_invalid_json_create_is_diagnostic_first_not_resolution_required(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    content = '{"created": }\n'

    preview = preview_repo_file_creation(repo, "created.json", content, runs)
    manifest = _manifest(runs, preview["patch_id"])
    evidence = manifest["operations"][0]["candidate_validation"]
    status = get_patch_status(repo, preview["patch_id"], runs)

    assert preview["ok"] is True
    assert preview["candidate_validation_status"] == "invalid"
    assert manifest["status"] == "preview_ok"
    assert manifest["repair_proposal"] is None
    assert evidence["language"] == "json"
    assert evidence["baseline_disposition"] == "not_applicable"
    assert evidence["candidate_disposition"] == "invalid"
    assert evidence["regression_detected"] is False
    assert status["applicable"] is True
    assert status["resolution_required"] is False
    assert status["candidate_validation_status"] == "invalid"

    applied = apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert applied["ok"] is True
    assert (repo / "created.json").read_text(encoding="utf-8") == content
    reverted = revert_managed_patch(repo, preview["patch_id"], runs)
    assert reverted["ok"] is True
    assert not (repo / "created.json").exists()


def test_g6_1_budget_skipped_json_candidate_does_not_gain_new_apply_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "budget.json"
    _write(target, b'{"value":1}\n')
    budget_type = rw.CandidateValidationBudget
    monkeypatch.setattr(
        rw,
        "CandidateValidationBudget",
        lambda: budget_type(max_files=0, clock=lambda: 0.0),
    )

    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": target.name,
                "expected_sha256": _sha(target),
                "old_text": '{"value":1}',
                "new_text": '{"value":}',
            }
        ],
        runs,
    )
    evidence = _manifest(runs, preview["patch_id"])["operations"][0][
        "candidate_validation"
    ]

    assert evidence["candidate_disposition"] == "budget_skipped"
    assert evidence["regression_detected"] is False
    assert preview["ok"] is True
    assert preview["applicable"] is True
    assert preview["resolution_required"] is False


def test_g6_1_valid_json_with_transport_looking_string_is_not_rewritten(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "literal.json"
    baseline = b'{"text":"safe"}\n'
    candidate = b'{"text":"}],\\"view\\":\\"full"}\n'
    _write(target, baseline)

    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": target.name,
                "expected_sha256": _sha(target),
                "old_text": baseline.decode(),
                "new_text": candidate.decode(),
            }
        ],
        runs,
    )

    assert preview["ok"] is True
    assert preview["resolution_required"] is False
    assert preview["repair_available"] is False
    assert _manifest(runs, preview["patch_id"])["repair_proposal"] is None


@pytest.mark.parametrize(
    ("name", "baseline", "candidate"),
    [
        ("config.toml", b"value = 1\n", b"value = [\n"),
        ("config.yaml", b"value: 1\n", b"value: [\n"),
        ("config.yml", b"value: 1\n", b"value: [\n"),
        ("config.xml", b"<root/>\n", b"<root>\n"),
    ],
)
def test_g6_2_g6_3_deferred_formats_remain_unvalidated(
    tmp_path: Path,
    name: str,
    baseline: bytes,
    candidate: bytes,
) -> None:
    repo = tmp_path / name.replace(".", "_")
    repo.mkdir()
    runs = tmp_path / f"runs_{name.replace('.', '_')}"
    target = repo / name
    _write(target, baseline)

    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": name,
                "expected_sha256": _sha(target),
                "old_text": baseline.decode(),
                "new_text": candidate.decode(),
            }
        ],
        runs,
    )
    manifest = _manifest(runs, preview["patch_id"])

    assert manifest["operations"][0]["candidate_validation"] is None
    assert preview["candidate_validation_status"] == "not_applicable"
    assert preview["resolution_required"] is False
    assert preview["repair_available"] is False
