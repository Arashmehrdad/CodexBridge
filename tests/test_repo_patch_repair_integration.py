from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import soma.repo_writer as rw
from soma.repo_writer import (
    apply_previewed_repo_change,
    apply_repo_patch,
    preview_repo_patch,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _manifest(runs: Path, patch_id: str) -> tuple[Path, dict]:
    patch_dir = runs / "managed_patches" / patch_id
    return patch_dir, json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))


def _incident_b(repo: Path, runs: Path) -> tuple[Path, bytes, bytes, list[dict], dict]:
    target = repo / "incident_b.py"
    baseline = b'assert ready == "ok"\nnext_call()\n'
    cut = baseline.index(b"\n")
    leaked = b'}],"view":"full'
    candidate = baseline[:cut] + leaked + baseline[cut:]
    _write(target, baseline)
    operations = [
        {
            "type": "exact_text",
            "path": "incident_b.py",
            "expected_sha256": _sha(target),
            "old_text": baseline.decode(),
            "new_text": candidate.decode(),
        }
    ]
    preview = preview_repo_patch(repo, operations, runs)
    return target, baseline, candidate, operations, preview


def test_g2_5_incident_b_is_resolution_required_with_separate_repair_payload(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, candidate, _, preview = _incident_b(repo, runs)
    patch_dir, manifest = _manifest(runs, preview["patch_id"])
    entry = manifest["operations"][0]
    proposal = manifest["repair_proposal"]

    assert preview["ok"] is False
    assert preview["applicable"] is False
    assert preview["resolution_required"] is True
    assert preview["repair_available"] is True
    assert preview["repair_proposal_id"] == proposal["proposal_id"]
    assert manifest["status"] == "preview_resolution_required"
    assert entry["candidate_validation"]["regression_detected"] is True
    assert entry["authored_span_provenance"]["disposition"] == "owned"
    assert proposal["rule_id"] == "repo_preview.patch.trailing_view.v1"
    assert (patch_dir / entry["payload_file"]).read_bytes() == candidate
    repair_descriptor = proposal["repaired_payload_descriptor"]
    repair_bytes = (patch_dir / repair_descriptor["file"]).read_bytes()
    assert repair_bytes == baseline
    assert hashlib.sha256(repair_bytes).hexdigest() == repair_descriptor["sha256"]
    assert entry["payload_sha256"] != repair_descriptor["sha256"]
    assert target.read_bytes() == baseline


def test_g2_5_incident_a_requires_resolution_without_proposal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "incident_a.py"
    baseline = b'items = [\n    "WorkPackage",\n    "Next",\n]\n'
    start = baseline.index(b'    "WorkPackage",')
    prefix = b'    "WorkPackage"'
    candidate = (
        baseline[:start]
        + prefix
        + b'}],"commit_title":"unsafe'
        + baseline[start + len(prefix) + 1 :]
    )
    _write(target, baseline)
    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": "incident_a.py",
                "expected_sha256": _sha(target),
                "old_text": baseline.decode(),
                "new_text": candidate.decode(),
            }
        ],
        runs,
    )
    patch_dir, manifest = _manifest(runs, preview["patch_id"])

    assert preview["ok"] is False
    assert preview["applicable"] is False
    assert preview["resolution_required"] is True
    assert preview["repair_available"] is False
    assert manifest["status"] == "preview_resolution_required"
    assert manifest["operations"][0]["candidate_validation"]["regression_detected"] is True
    assert manifest["repair_proposal"] is None
    assert list(patch_dir.glob("repair_payload_*.bin")) == []
    assert target.read_bytes() == baseline


def test_g2_5_multiple_file_proposals_are_not_guessed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    operations = []
    for name in ("one.py", "two.py"):
        target = repo / name
        baseline = f'{name.replace(".py", "")} = 1\n'.encode()
        cut = baseline.index(b"\n")
        candidate = baseline[:cut] + b'}],"view":"full' + baseline[cut:]
        _write(target, baseline)
        operations.append(
            {
                "type": "exact_text",
                "path": name,
                "expected_sha256": _sha(target),
                "old_text": baseline.decode(),
                "new_text": candidate.decode(),
            }
        )

    preview = preview_repo_patch(repo, operations, runs)
    patch_dir, manifest = _manifest(runs, preview["patch_id"])

    assert preview["ok"] is False
    assert preview["resolution_required"] is True
    assert preview["repair_available"] is False
    assert manifest["repair_proposal"] is None
    assert list(patch_dir.glob("repair_payload_*.bin")) == []


def test_g2_5_resolution_required_source_is_blocked_by_both_apply_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, _, operations, preview = _incident_b(repo, runs)

    with pytest.raises(ValueError, match="not applicable.*preview_resolution_required"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert target.read_bytes() == baseline

    with pytest.raises(ValueError, match="not applicable.*preview_resolution_required"):
        apply_repo_patch(repo, operations, preview["patch_id"], runs)
    assert target.read_bytes() == baseline


def test_g2_5_ordinary_valid_preview_remains_applicable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "valid.py"
    _write(target, b"value = 1\n")
    operations = [
        {
            "type": "exact_text",
            "path": "valid.py",
            "expected_sha256": _sha(target),
            "old_text": "value = 1",
            "new_text": "value = 2",
        }
    ]

    preview = preview_repo_patch(repo, operations, runs)
    _, manifest = _manifest(runs, preview["patch_id"])

    assert preview["ok"] is True
    assert preview["applicable"] is True
    assert preview["resolution_required"] is False
    assert manifest["status"] == "preview_ok"
    applied = apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert applied["ok"] is True
    assert target.read_text(encoding="utf-8") == "value = 2\n"


def test_g2_5_legacy_operation_apply_still_accepts_preview_ok(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "legacy_apply.py"
    _write(target, b"value = 1\n")
    operations = [
        {
            "type": "exact_text",
            "path": "legacy_apply.py",
            "expected_sha256": _sha(target),
            "old_text": "value = 1",
            "new_text": "value = 2",
        }
    ]
    preview = preview_repo_patch(repo, operations, runs)

    applied = apply_repo_patch(repo, operations, preview["patch_id"], runs)

    assert applied["ok"] is True
    assert target.read_text(encoding="utf-8") == "value = 2\n"


def test_g2_5_baseline_invalid_candidate_is_not_newly_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "already_invalid.py"
    baseline = b"value = (\n"
    candidate = b"value = (1\n"
    _write(target, baseline)

    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": "already_invalid.py",
                "expected_sha256": _sha(target),
                "old_text": baseline.decode(),
                "new_text": candidate.decode(),
            }
        ],
        runs,
    )
    _, manifest = _manifest(runs, preview["patch_id"])
    validation = manifest["operations"][0]["candidate_validation"]

    assert validation["baseline_disposition"] == "invalid"
    assert validation["candidate_disposition"] == "invalid"
    assert validation["regression_detected"] is False
    assert preview["ok"] is True
    assert preview["applicable"] is True
    assert preview["resolution_required"] is False
    assert manifest["status"] == "preview_ok"


def test_g2_5_budget_skipped_candidate_is_not_newly_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "budget.py"
    _write(target, b"value = 1\n")
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
                "path": "budget.py",
                "expected_sha256": _sha(target),
                "old_text": "value = 1",
                "new_text": "value = 2",
            }
        ],
        runs,
    )
    _, manifest = _manifest(runs, preview["patch_id"])
    validation = manifest["operations"][0]["candidate_validation"]

    assert validation["candidate_disposition"] == "budget_skipped"
    assert validation["regression_detected"] is False
    assert preview["ok"] is True
    assert preview["applicable"] is True
    assert preview["resolution_required"] is False
    assert manifest["status"] == "preview_ok"


def test_g2_5_unknown_future_status_is_not_freshly_applicable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "future.py"
    _write(target, b"value = 1\n")
    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": "future.py",
                "expected_sha256": _sha(target),
                "old_text": "value = 1",
                "new_text": "value = 2",
            }
        ],
        runs,
    )
    patch_dir, manifest = _manifest(runs, preview["patch_id"])
    manifest["status"] = "future_non_applicable_state"
    (patch_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="not applicable.*future_non_applicable_state"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert target.read_bytes() == b"value = 1\n"
