from __future__ import annotations

import json
from pathlib import Path

import pytest

import soma.repo_patch_evidence as evidence
import soma.repo_writer as rw
from soma.repo_patch_evidence import summarize_patch_evidence


def _patch_id(index: int) -> str:
    return f"20260815T0101{index:02d}Z_patch_{index:08x}"


def _write_manifest(
    runs: Path,
    repo: Path,
    index: int,
    *,
    status: str = "preview_ok",
    operations: list[dict] | None = None,
    repair_proposal: dict | None = None,
    resolution: dict | None = None,
    resolution_role: str | None = None,
    repo_fingerprint: str | None = None,
) -> str:
    patch_id = _patch_id(index)
    patch_dir = runs / rw.MANAGED_PATCHES_DIR / patch_id
    patch_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "patch_id": patch_id,
        "bundle_version": 4,
        "repo_fingerprint": (
            rw._repo_fingerprint(repo) if repo_fingerprint is None else repo_fingerprint
        ),
        "status": status,
        "operations": operations or [],
        "repair_proposal": repair_proposal,
    }
    if resolution is not None:
        manifest["resolution"] = resolution
    if resolution_role is not None:
        manifest["resolution_role"] = resolution_role
    (patch_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return patch_id


def _validation(
    disposition: str,
    *,
    language: str = "python",
    elapsed_ms: float = 0.5,
    size_bytes: int = 100,
) -> dict:
    return {
        "schema_version": "repo_candidate_validation.v1",
        "path": "sample.py",
        "language": language,
        "baseline_disposition": "valid",
        "candidate_disposition": disposition,
        "validator": "test.validator",
        "validator_version": "v1",
        "candidate_sha256": "0" * 64,
        "candidate_size_bytes": size_bytes,
        "diagnostic": None,
        "elapsed_ms": elapsed_ms,
        "regression_detected": disposition == "invalid",
    }


def _op(validation: object) -> dict:
    return {"action": "modify", "path": "sample.py", "candidate_validation": validation}


def test_g7_empty_summary_is_explicit_and_read_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"

    result = summarize_patch_evidence(repo, runs)

    assert result["schema_version"] == "repo_patch_evidence_summary.v1"
    assert result["source"] == "managed_patch_manifests"
    assert result["patches_examined"] == 0
    assert result["candidate_validations_attempted"] == 0
    assert result["resolution_decisions"] == {
        "accept_repair": 0,
        "accept_original": 0,
    }
    assert result["privacy"] == {
        "payload_files_read": False,
        "patch_ids_emitted": False,
        "source_bodies_emitted": False,
    }
    assert result["authority"] == {
        "writes_state": False,
        "silent_auto_resolution_authorized": False,
    }
    assert result["unavailable_metrics"]["resolution_conflicts_or_stale_failures"] == (
        "not_available_from_managed_patch_manifests"
    )
    assert result["unavailable_metrics"]["intentional_abandonment"] == (
        "not_inferred_from_unresolved_state"
    )
    assert not runs.exists()


def test_g7_counts_validation_dispositions_languages_and_buckets(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"

    validations = [
        _validation("valid", elapsed_ms=0.5, size_bytes=100),
        _validation("invalid", language="json", elapsed_ms=1.0, size_bytes=1024),
        _validation("budget_skipped", elapsed_ms=5.0, size_bytes=16 * 1024),
        _validation("valid", elapsed_ms=25.0, size_bytes=64 * 1024),
        _validation("valid", elapsed_ms=100.0, size_bytes=256 * 1024),
        _validation("budget_skipped", elapsed_ms=250.0, size_bytes=512 * 1024),
    ]
    _write_manifest(
        runs,
        repo,
        1,
        operations=[_op(item) for item in validations],
    )

    result = summarize_patch_evidence(repo, runs)

    assert result["candidate_validations_attempted"] == 6
    assert result["candidate_validation_dispositions"] == {
        "budget_skipped": 2,
        "invalid": 1,
        "valid": 3,
    }
    assert result["candidate_validation_languages"] == {"json": 1, "python": 5}
    assert result["validation_elapsed_ms_buckets"] == {
        "lt_1_ms": 1,
        "1_to_lt_5_ms": 1,
        "5_to_lt_25_ms": 1,
        "25_to_lt_100_ms": 1,
        "gte_100_ms": 2,
        "invalid_or_missing": 0,
    }
    assert result["candidate_size_bytes_buckets"] == {
        "lt_1_kib": 1,
        "1_to_lt_16_kib": 1,
        "16_to_lt_64_kib": 1,
        "64_to_lt_256_kib": 1,
        "256_to_lt_512_kib": 1,
        "gte_512_kib": 1,
        "invalid_or_missing": 0,
    }


def test_g7_resolution_child_does_not_double_count_source_evidence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    proposal = {
        "proposal_id": "repair_0123456789abcdef",
        "rule_id": "repo_preview.patch.trailing_view.v1",
    }
    resolution = {"decision": "accept_repair"}
    source_id = _write_manifest(
        runs,
        repo,
        2,
        status="resolved",
        operations=[_op(_validation("invalid"))],
        repair_proposal=proposal,
        resolution=resolution,
    )
    child_id = _write_manifest(
        runs,
        repo,
        3,
        status="preview_ok",
        operations=[_op(_validation("valid"))],
        repair_proposal=None,
        resolution={"source_patch_id": source_id, "decision": "accept_repair"},
        resolution_role="child",
    )
    assert source_id != child_id

    result = summarize_patch_evidence(repo, runs)

    assert result["patches_examined"] == 2
    assert result["source_manifests"] == 1
    assert result["child_manifests_ignored"] == 1
    assert result["candidate_validations_attempted"] == 1
    assert result["candidate_validation_dispositions"] == {"invalid": 1}
    assert result["repair_proposals_by_rule_id"] == {
        "repo_preview.patch.trailing_view.v1": 1
    }
    assert result["resolution_decisions"] == {
        "accept_repair": 1,
        "accept_original": 0,
    }


def test_g7_accept_original_after_proposal_is_review_signal_not_false_positive_verdict(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _write_manifest(
        runs,
        repo,
        4,
        status="resolved",
        operations=[_op(_validation("invalid"))],
        repair_proposal={
            "proposal_id": "repair_fedcba9876543210",
            "rule_id": "repo_preview.patch.trailing_commit_title.v1",
        },
        resolution={"decision": "accept_original"},
    )

    result = summarize_patch_evidence(repo, runs)

    assert result["resolution_decisions"] == {
        "accept_repair": 0,
        "accept_original": 1,
    }
    assert result["accept_original_after_repair_proposal_review_signals"] == 1
    assert "false_positive" not in json.dumps(result, sort_keys=True)


def test_g7_unresolved_source_is_counted_without_claiming_intentional_abandonment(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _write_manifest(
        runs,
        repo,
        5,
        status="preview_resolution_required",
        operations=[_op(_validation("invalid"))],
    )

    result = summarize_patch_evidence(repo, runs)

    assert result["currently_unresolved_resolution_required_sources"] == 1
    assert result["unavailable_metrics"]["intentional_abandonment"] == (
        "not_inferred_from_unresolved_state"
    )
    assert "abandoned_without_resolution" not in result


def test_g7_foreign_and_unbound_manifests_are_not_mixed_into_repo_summary(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _write_manifest(
        runs,
        repo,
        6,
        operations=[_op(_validation("valid"))],
        repo_fingerprint="f" * 64,
    )
    _write_manifest(
        runs,
        repo,
        7,
        operations=[_op(_validation("invalid"))],
        repo_fingerprint="",
    )

    result = summarize_patch_evidence(repo, runs)

    assert result["patches_examined"] == 2
    assert result["foreign_or_unbound_manifests_skipped"] == 2
    assert result["source_manifests"] == 0
    assert result["candidate_validations_attempted"] == 0


def test_g7_malformed_validation_record_is_counted_without_leaking_content(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    secret = "MODEL_SOURCE_BODY_SHOULD_NOT_LEAK"
    _write_manifest(
        runs,
        repo,
        8,
        operations=[
            {"action": "modify", "path": "x.py", "candidate_validation": secret},
            _op({"language": "python", "candidate_disposition": ""}),
        ],
    )

    result = summarize_patch_evidence(repo, runs)
    rendered = json.dumps(result, sort_keys=True)

    assert result["malformed_validation_records"] == 2
    assert result["candidate_validations_attempted"] == 0
    assert secret not in rendered
    assert _patch_id(8) not in rendered


def test_g7_invalid_metric_values_go_to_explicit_invalid_buckets(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    bad_elapsed = _validation("valid")
    bad_elapsed["elapsed_ms"] = "slow"
    bad_elapsed["candidate_size_bytes"] = -1
    _write_manifest(runs, repo, 9, operations=[_op(bad_elapsed)])

    result = summarize_patch_evidence(repo, runs)

    assert result["candidate_validations_attempted"] == 1
    assert result["validation_elapsed_ms_buckets"]["invalid_or_missing"] == 1
    assert result["candidate_size_bytes_buckets"]["invalid_or_missing"] == 1


def test_g7_repair_rules_are_counted_by_rule_id_without_proposal_body(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _write_manifest(
        runs,
        repo,
        10,
        repair_proposal={
            "proposal_id": "repair_aaaaaaaaaaaaaaaa",
            "rule_id": "repo_preview.patch.trailing_view.v1",
            "deleted_excerpt_bounded": "DO_NOT_EXPORT_THIS_EXCERPT",
        },
    )
    _write_manifest(
        runs,
        repo,
        11,
        repair_proposal={
            "proposal_id": "repair_bbbbbbbbbbbbbbbb",
            "rule_id": "repo_preview.patch.trailing_view.v1",
        },
    )
    _write_manifest(
        runs,
        repo,
        12,
        repair_proposal={"proposal_id": "repair_cccccccccccccccc", "rule_id": ""},
    )

    result = summarize_patch_evidence(repo, runs)
    rendered = json.dumps(result, sort_keys=True)

    assert result["repair_proposals_by_rule_id"] == {
        "repo_preview.patch.trailing_view.v1": 2,
        "unknown": 1,
    }
    assert "DO_NOT_EXPORT_THIS_EXCERPT" not in rendered
    assert "repair_aaaaaaaaaaaaaaaa" not in rendered


def test_g7_summary_reads_manifest_files_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    patch_id = _write_manifest(
        runs,
        repo,
        13,
        operations=[_op(_validation("valid"))],
    )
    patch_dir = runs / rw.MANAGED_PATCHES_DIR / patch_id
    (patch_dir / "payload_0.bin").write_bytes(b"SECRET_PAYLOAD_BODY")
    (patch_dir / "repair_payload_aaaaaaaaaaaaaaaa.bin").write_bytes(
        b"SECRET_REPAIR_BODY"
    )

    real_read_bytes = Path.read_bytes
    reads: list[str] = []

    def guarded_read_bytes(path: Path) -> bytes:
        reads.append(path.name)
        if path.name != "manifest.json":
            raise AssertionError(
                f"G7 evidence summary opened payload file: {path.name}"
            )
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    result = summarize_patch_evidence(repo, runs)

    assert result["candidate_validations_attempted"] == 1
    assert reads == ["manifest.json"]


def test_g7_bad_manifest_does_not_abort_other_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _write_manifest(runs, repo, 14, operations=[_op(_validation("valid"))])
    bad_id = _patch_id(15)
    bad_dir = runs / rw.MANAGED_PATCHES_DIR / bad_id
    bad_dir.mkdir(parents=True)
    (bad_dir / "manifest.json").write_text("{not-json", encoding="utf-8")

    result = summarize_patch_evidence(repo, runs)

    assert result["patches_examined"] == 2
    assert result["manifest_read_errors"] == 1
    assert result["candidate_validations_attempted"] == 1


def test_g7_oversized_manifest_is_bounded_and_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    patch_id = _patch_id(16)
    patch_dir = runs / rw.MANAGED_PATCHES_DIR / patch_id
    patch_dir.mkdir(parents=True)
    manifest = patch_dir / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(evidence, "MAX_EVIDENCE_MANIFEST_BYTES", 1)
    result = summarize_patch_evidence(repo, runs)

    assert result["patches_examined"] == 1
    assert result["manifest_read_errors"] == 1
    assert result["source_manifests"] == 0


def test_g7_managed_patch_root_symlink_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    runs.mkdir()
    root = runs / rw.MANAGED_PATCHES_DIR
    try:
        root.symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation unavailable")

    with pytest.raises(ValueError, match="regular directory"):
        summarize_patch_evidence(repo, runs)


def test_g7_summary_does_not_mutate_manifests(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    patch_id = _write_manifest(
        runs,
        repo,
        17,
        status="preview_resolution_required",
        operations=[_op(_validation("invalid"))],
    )
    manifest = runs / rw.MANAGED_PATCHES_DIR / patch_id / "manifest.json"
    before = manifest.read_bytes()

    first = summarize_patch_evidence(repo, runs)
    second = summarize_patch_evidence(repo, runs)

    assert first == second
    assert manifest.read_bytes() == before


def test_g7_no_silent_auto_resolution_authority_is_exported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _write_manifest(
        runs,
        repo,
        18,
        status="preview_resolution_required",
        operations=[_op(_validation("invalid"))],
        repair_proposal={
            "proposal_id": "repair_dddddddddddddddd",
            "rule_id": "repo_preview.patch.trailing_view.v1",
        },
    )

    result = summarize_patch_evidence(repo, runs)

    assert result["repair_proposals_by_rule_id"] == {
        "repo_preview.patch.trailing_view.v1": 1
    }
    assert result["authority"]["silent_auto_resolution_authorized"] is False
    assert result["currently_unresolved_resolution_required_sources"] == 1


def test_g7_manifest_scan_budget_is_newest_first_and_explicitly_truncated(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _write_manifest(runs, repo, 19, operations=[_op(_validation("invalid"))])
    _write_manifest(runs, repo, 20, operations=[_op(_validation("valid"))])
    _write_manifest(
        runs,
        repo,
        21,
        operations=[_op(_validation("budget_skipped"))],
    )

    result = summarize_patch_evidence(repo, runs, max_manifests=2)

    assert result["scan_order"] == "newest_patch_id_first"
    assert result["manifest_scan_limit"] == 2
    assert result["matching_patch_directories_discovered"] == 3
    assert result["scan_truncated"] is True
    assert result["patches_examined"] == 2
    assert result["source_manifests"] == 2
    assert result["candidate_validation_dispositions"] == {
        "budget_skipped": 1,
        "valid": 1,
    }


@pytest.mark.parametrize(
    "max_manifests",
    [0, -1, True, evidence.MAX_EVIDENCE_MANIFEST_SCAN + 1],
)
def test_g7_manifest_scan_budget_rejects_invalid_values(
    tmp_path: Path,
    max_manifests: object,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(ValueError, match="max_manifests must be between"):
        summarize_patch_evidence(
            repo,
            tmp_path / "runs",
            max_manifests=max_manifests,  # type: ignore[arg-type]
        )
