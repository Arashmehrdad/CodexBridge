from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import soma.repo_writer as rw
from soma.repo_patch_resolution import build_resolution_request
from soma.repo_patch_resolution_service import resolve_patch_preview
from soma.repo_writer import (
    apply_previewed_repo_change,
    get_patch_status,
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


def _write_manifest(runs: Path, patch_id: str, manifest: dict) -> None:
    (_patch_dir(runs, patch_id) / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _incident_b(repo: Path, runs: Path, name: str = "incident_b.py") -> tuple[Path, bytes, bytes, dict]:
    target = repo / name
    baseline = b'assert ready == "ok"\nnext_call()\n'
    cut = baseline.index(b"\n")
    leaked = b'}],"view":"full'
    candidate = baseline[:cut] + leaked + baseline[cut:]
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
        commit_title="Repair fixture",
        commit_description="preserve controller intent",
    )
    assert preview["resolution_required"] is True
    assert preview["repair_available"] is True
    return target, baseline, candidate, preview


def _incident_a_no_proposal(repo: Path, runs: Path) -> dict:
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
    assert preview["resolution_required"] is True
    assert preview["repair_available"] is False
    return preview


def test_accept_repair_selects_preserved_payload_without_rerunning_detector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, candidate, source = _incident_b(repo, runs)
    source_id = source["patch_id"]
    source_manifest_before = _manifest(runs, source_id)
    proposal_id = source_manifest_before["repair_proposal"]["proposal_id"]

    def forbidden_detector(*args, **kwargs):
        raise AssertionError("repair detector/search must not run during resolution")

    monkeypatch.setattr(rw, "build_patch_repair_proposal", forbidden_detector)
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source_id,
        resolution_request_id="resolve-repair-1",
        decision="accept_repair",
        proposal_id=proposal_id,
    )

    assert child["ok"] is True
    assert child["applicable"] is True
    assert child["decision"] == "accept_repair"
    assert target.read_bytes() == baseline
    source_manifest = _manifest(runs, source_id)
    child_manifest = _manifest(runs, child["patch_id"])
    assert source_manifest["status"] == "resolved"
    assert child_manifest["status"] == "preview_ok"
    assert child_manifest["resolution_role"] == "child"
    assert child_manifest["resolution"]["source_patch_id"] == source_id
    assert child_manifest["resolution"]["source_repair_proposal"]["proposal_id"] == proposal_id
    source_payload = (
        _patch_dir(runs, source_id) / source_manifest["operations"][0]["payload_file"]
    ).read_bytes()
    child_payload = (
        _patch_dir(runs, child["patch_id"])
        / child_manifest["operations"][0]["payload_file"]
    ).read_bytes()
    assert source_payload == candidate
    assert child_payload == baseline
    assert source_manifest["repair_proposal"] == source_manifest_before["repair_proposal"]


def test_exact_resolution_replay_returns_same_child(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _, _, _, source = _incident_b(repo, runs)
    proposal_id = _manifest(runs, source["patch_id"])["repair_proposal"]["proposal_id"]

    first = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="same-request",
        decision="accept_repair",
        proposal_id=proposal_id,
    )
    replay = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="same-request",
        decision="accept_repair",
        proposal_id=proposal_id,
    )

    assert replay["patch_id"] == first["patch_id"]
    assert replay["idempotent_replay"] is True


def test_same_request_id_changed_decision_conflicts_after_resolution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _, _, _, source = _incident_b(repo, runs)
    proposal_id = _manifest(runs, source["patch_id"])["repair_proposal"]["proposal_id"]
    resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="conflict-request",
        decision="accept_repair",
        proposal_id=proposal_id,
    )

    with pytest.raises(ValueError, match="already resolved by a different request"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=source["patch_id"],
            resolution_request_id="conflict-request",
            decision="accept_original",
        )


def test_wrong_proposal_rejects_without_claiming_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _, _, _, source = _incident_b(repo, runs)

    with pytest.raises(ValueError, match="repair proposal mismatch"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=source["patch_id"],
            resolution_request_id="wrong-proposal",
            decision="accept_repair",
            proposal_id="repair_ffffffffffffffff",
        )
    manifest = _manifest(runs, source["patch_id"])
    assert manifest["status"] == "preview_resolution_required"
    assert "resolution_pending" not in manifest


def test_accept_repair_without_proposal_fails_without_claiming_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    source = _incident_a_no_proposal(repo, runs)

    with pytest.raises(ValueError, match="has no repair proposal"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=source["patch_id"],
            resolution_request_id="no-proposal",
            decision="accept_repair",
            proposal_id="repair_0123456789abcdef",
        )
    manifest = _manifest(runs, source["patch_id"])
    assert manifest["status"] == "preview_resolution_required"
    assert "resolution_pending" not in manifest


def test_accept_original_creates_explicit_override_child_and_normal_apply_revert(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, candidate, source = _incident_b(repo, runs)

    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="accept-original-1",
        decision="accept_original",
    )
    child_manifest = _manifest(runs, child["patch_id"])
    assert child_manifest["candidate_validation_override"] == "accept_original"
    assert child_manifest["resolution"]["candidate_validation_override"] == "accept_original"
    assert (
        _patch_dir(runs, child["patch_id"])
        / child_manifest["operations"][0]["payload_file"]
    ).read_bytes() == candidate
    assert _manifest(runs, source["patch_id"])["status"] == "resolved"

    applied = apply_previewed_repo_change(repo, child["patch_id"], runs)
    assert applied["ok"] is True
    assert target.read_bytes() == candidate
    reverted = revert_managed_patch(repo, child["patch_id"], runs)
    assert reverted["ok"] is True
    assert target.read_bytes() == baseline
    assert _manifest(runs, source["patch_id"])["status"] == "resolved"


def test_unknown_wrong_repo_non_resolution_and_stale_source_fail(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    with pytest.raises(ValueError, match="Unknown source patch_id"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id="20260815T010203Z_patch_aaaaaaaa",
            resolution_request_id="unknown",
            decision="accept_original",
        )

    target, _, _, source = _incident_b(repo, runs)
    other_repo = tmp_path / "other"
    other_repo.mkdir()
    with pytest.raises(ValueError, match="does not belong"):
        resolve_patch_preview(
            other_repo,
            runs,
            source_patch_id=source["patch_id"],
            resolution_request_id="wrong-repo",
            decision="accept_original",
        )

    target.write_text("changed = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed since source preview"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=source["patch_id"],
            resolution_request_id="stale-source",
            decision="accept_original",
        )
    assert "resolution_pending" not in _manifest(runs, source["patch_id"])

    clean = repo / "clean.py"
    _write(clean, b"value = 1\n")
    valid = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": "clean.py",
                "expected_sha256": _sha(clean),
                "old_text": "value = 1",
                "new_text": "value = 2",
            }
        ],
        runs,
    )
    with pytest.raises(ValueError, match="not resolution-required"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=valid["patch_id"],
            resolution_request_id="not-needed",
            decision="accept_original",
        )


def test_deterministic_child_collision_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _, _, _, source = _incident_b(repo, runs)
    source_manifest = _manifest(runs, source["patch_id"])
    proposal_id = source_manifest["repair_proposal"]["proposal_id"]
    _, _, child_id = build_resolution_request(
        source_patch_id=source["patch_id"],
        resolution_request_id="collision",
        decision="accept_repair",
        proposal_id=proposal_id,
        source_manifest=source_manifest,
    )
    child_dir = _patch_dir(runs, child_id)
    child_dir.mkdir(parents=True)
    (child_dir / "manifest.json").write_text(
        json.dumps(
            {
                "patch_id": child_id,
                "bundle_version": 4,
                "status": "preview_ok",
                "resolution": {"schema_version": "repo_patch_resolution_record.v1"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Deterministic child collision"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=source["patch_id"],
            resolution_request_id="collision",
            decision="accept_repair",
            proposal_id=proposal_id,
        )


def test_resolution_rechecks_path_operation_payload_and_size_safety(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"

    _, _, _, path_source = _incident_b(repo, runs, "path_case.py")
    manifest = _manifest(runs, path_source["patch_id"])
    manifest["operations"][0]["path"] = "../escape.py"
    _write_manifest(runs, path_source["patch_id"], manifest)
    with pytest.raises(ValueError):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=path_source["patch_id"],
            resolution_request_id="path-escape",
            decision="accept_original",
        )

    _, _, _, op_source = _incident_b(repo, runs, "op_case.py")
    manifest = _manifest(runs, op_source["patch_id"])
    manifest["operations"][0]["action"] = "future_action"
    _write_manifest(runs, op_source["patch_id"], manifest)
    with pytest.raises(ValueError, match="invalid resolution operation"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=op_source["patch_id"],
            resolution_request_id="bad-op",
            decision="accept_original",
        )

    _, _, _, payload_source = _incident_b(repo, runs, "payload_case.py")
    manifest = _manifest(runs, payload_source["patch_id"])
    payload = _patch_dir(runs, payload_source["patch_id"]) / manifest["operations"][0]["payload_file"]
    payload.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="payload verification failed"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=payload_source["patch_id"],
            resolution_request_id="tampered-payload",
            decision="accept_original",
        )

    _, _, _, count_source = _incident_b(repo, runs, "count_case.py")
    manifest = _manifest(runs, count_source["patch_id"])
    manifest["operations"] = [
        dict(manifest["operations"][0]) for _ in range(rw.MAX_PATCH_FILES + 1)
    ]
    _write_manifest(runs, count_source["patch_id"], manifest)
    with pytest.raises(ValueError, match="file limit"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=count_source["patch_id"],
            resolution_request_id="too-many-files",
            decision="accept_original",
        )

    _, _, _, size_source = _incident_b(repo, runs, "size_case.py")
    manifest = _manifest(runs, size_source["patch_id"])
    source_dir = _patch_dir(runs, size_source["patch_id"])
    payload = source_dir / manifest["operations"][0]["payload_file"]
    oversized = b"value = '" + (b"a" * (rw.MAX_PATCH_BYTES + 100)) + b"'\n"
    payload.write_bytes(oversized)
    manifest["operations"][0]["payload_sha256"] = hashlib.sha256(oversized).hexdigest()
    manifest["operations"][0]["payload_size_bytes"] = len(oversized)
    manifest["operations"][0]["payload_chunks"] = []
    _write_manifest(runs, size_source["patch_id"], manifest)
    with pytest.raises(ValueError, match="changed-byte limit"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=size_source["patch_id"],
            resolution_request_id="oversized",
            decision="accept_original",
        )


def test_resolution_rechecks_git_head_when_available(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Soma Test"], cwd=repo, check=True)
    runs = tmp_path / "runs"
    _incident_b(repo, runs, "head_case.py")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, check=True, capture_output=True)

    target, baseline, candidate, source = _incident_b(repo, runs, "head_case.py")
    # The helper rewrites the same baseline and source is now bound to the baseline commit.
    assert target.read_bytes() == baseline
    (repo / "unrelated.txt").write_text("new head\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "move head"], cwd=repo, check=True, capture_output=True)
    assert candidate != baseline

    with pytest.raises(ValueError, match="Git HEAD has changed"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=source["patch_id"],
            resolution_request_id="stale-head",
            decision="accept_original",
        )


def test_source_and_child_status_remain_independent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, _, source = _incident_b(repo, runs)
    source_before = get_patch_status(repo, source["patch_id"], runs)
    assert source_before["status"] == "preview_resolution_required"
    assert source_before["resolution_required"] is True
    assert source_before["repair_available"] is True
    assert source_before["resolution_choices"] == ["accept_repair", "accept_original"]
    proposal_id = source_before["repair_proposal_id"]
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="lifecycle",
        decision="accept_repair",
        proposal_id=proposal_id,
    )

    source_status = get_patch_status(repo, source["patch_id"], runs)
    child_status = get_patch_status(repo, child["patch_id"], runs)
    assert source_status["status"] == "resolved"
    assert source_status["applicable"] is False
    assert source_status["child_patch_id"] == child["patch_id"]
    assert source_status["decision"] == "accept_repair"
    assert source_status["resolution_request_id"] == "lifecycle"
    assert child_status["status"] == "preview_ok"
    assert child_status["applicable"] is True
    assert child_status["resolution_role"] == "child"
    assert child_status["source_patch_id"] == source["patch_id"]
    assert child_status["decision"] == "accept_repair"
    assert child_status["proposal_id"] == proposal_id
    with pytest.raises(ValueError, match="not applicable.*resolved"):
        apply_previewed_repo_change(repo, source["patch_id"], runs)
    apply_previewed_repo_change(repo, child["patch_id"], runs)
    assert target.read_bytes() == baseline
    assert get_patch_status(repo, source["patch_id"], runs)["status"] == "resolved"
    assert get_patch_status(repo, child["patch_id"], runs)["status"] == "applied"
    revert_managed_patch(repo, child["patch_id"], runs)
    assert get_patch_status(repo, source["patch_id"], runs)["status"] == "resolved"
    assert get_patch_status(repo, child["patch_id"], runs)["status"] == "reverted"


def test_resolution_status_recovers_from_managed_files_in_fresh_process(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    _, _, _, source = _incident_b(repo, runs, "restart_case.py")
    proposal_id = _manifest(runs, source["patch_id"])["repair_proposal"]["proposal_id"]
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="fresh-process",
        decision="accept_repair",
        proposal_id=proposal_id,
    )

    project_root = Path(__file__).resolve().parents[1]
    script = (
        "import json,sys; from pathlib import Path; "
        "from soma.repo_writer import get_patch_status; "
        "repo=Path(sys.argv[1]); runs=Path(sys.argv[2]); "
        "print(json.dumps([get_patch_status(repo,sys.argv[3],runs),"
        "get_patch_status(repo,sys.argv[4],runs)]))"
    )
    recovered = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(repo),
            str(runs),
            source["patch_id"],
            child["patch_id"],
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    source_status, child_status = json.loads(recovered.stdout)
    assert source_status["status"] == "resolved"
    assert source_status["child_patch_id"] == child["patch_id"]
    assert child_status["status"] == "preview_ok"
    assert child_status["source_patch_id"] == source["patch_id"]
    assert child_status["resolution_request_id"] == "fresh-process"


def test_symlink_and_binary_rechecks_fail_closed_when_supported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, _, _, source = _incident_b(repo, runs, "binary_case.py")
    binary = b"\x00binary\x00"
    target.write_bytes(binary)
    manifest = _manifest(runs, source["patch_id"])
    manifest["operations"][0]["current_sha256"] = hashlib.sha256(binary).hexdigest()
    _write_manifest(runs, source["patch_id"], manifest)
    with pytest.raises(ValueError, match="Binary files are not supported"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=source["patch_id"],
            resolution_request_id="binary",
            decision="accept_original",
        )

    symlink_target = repo / "real.py"
    symlink_path = repo / "link.py"
    _write(symlink_target, b"value = 1\n")
    try:
        os.symlink(symlink_target, symlink_path)
    except (OSError, NotImplementedError):
        return
    # A source manifest is constructed from a normal file and then the path is
    # swapped to a symlink with the same bytes; resolution must still refuse it.
    symlink_path.unlink()
    _write(symlink_path, b'assert ready == "ok"\nnext_call()\n')
    _, _, _, link_source = _incident_b(repo, runs, "link.py")
    symlink_path.unlink()
    os.symlink(symlink_target, symlink_path)
    manifest = _manifest(runs, link_source["patch_id"])
    manifest["operations"][0]["current_sha256"] = _sha(symlink_target)
    _write_manifest(runs, link_source["patch_id"], manifest)
    with pytest.raises(ValueError, match="Symlinks are not allowed"):
        resolve_patch_preview(
            repo,
            runs,
            source_patch_id=link_source["patch_id"],
            resolution_request_id="symlink",
            decision="accept_original",
        )
