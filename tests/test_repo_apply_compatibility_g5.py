from __future__ import annotations

import ast
import builtins
import hashlib
import json
import subprocess
import tokenize
from pathlib import Path

import pytest

import soma.repo_writer as rw
from soma.payload_chunks import build_payload_parts
from soma.repo_patch_resolution_service import resolve_patch_preview
from soma.repo_writer import (
    apply_previewed_repo_change,
    get_patch_status,
    preview_repo_patch,
    revert_managed_patch,
)


V2_HISTORICAL_COMMIT = "44f0312"
V3_HISTORICAL_COMMIT = "b40d75d"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


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


def _repair_source(
    repo: Path,
    runs: Path,
    *,
    name: str = "repair_target.py",
    include_second_file: bool = False,
) -> tuple[Path, bytes, bytes, dict, Path | None, bytes | None]:
    target = repo / name
    baseline = b'assert ready == "ok"\nnext_call()\n'
    cut = baseline.index(b"\n")
    candidate = baseline[:cut] + b'}],"view":"full' + baseline[cut:]
    _write(target, baseline)
    operations = [
        {
            "type": "exact_text",
            "path": name,
            "expected_sha256": _sha(target),
            "old_text": baseline.decode(),
            "new_text": candidate.decode(),
        }
    ]
    second_target: Path | None = None
    second_baseline: bytes | None = None
    if include_second_file:
        second_target = repo / "ordinary.py"
        second_baseline = b"value = 1\n"
        _write(second_target, second_baseline)
        operations.append(
            {
                "type": "exact_text",
                "path": "ordinary.py",
                "expected_sha256": _sha(second_target),
                "old_text": "value = 1",
                "new_text": "value = 2",
            }
        )
    source = preview_repo_patch(repo, operations, runs)
    assert source["resolution_required"] is True
    assert source["repair_available"] is True
    return target, baseline, candidate, source, second_target, second_baseline


def _resolve_repair_child(
    repo: Path, runs: Path, *, request_id: str
) -> tuple[dict, dict]:
    _, _, _, source, _, _ = _repair_source(
        repo, runs, name=f"{request_id.replace('-', '_')}.py"
    )
    source_manifest = _manifest(runs, source["patch_id"])
    proposal_id = source_manifest["repair_proposal"]["proposal_id"]
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id=request_id,
        decision="accept_repair",
        proposal_id=proposal_id,
    )
    return source, child


def _write_historical_fixture_bundle(
    repo: Path,
    runs: Path,
    *,
    version: int,
    status: str = "preview_ok",
) -> tuple[Path, bytes, bytes, str]:
    if version not in {2, 3}:
        raise ValueError("historical fixture version must be 2 or 3")
    target = repo / f"legacy_v{version}.py"
    baseline = b"value = 1\n"
    payload = b"value = 2\n"
    _write(target, baseline)
    patch_id = f"20260815T12000{version}Z_patch_0000000{version}"
    patch_dir = _patch_dir(runs, patch_id)
    patch_dir.mkdir(parents=True)

    entry = {
        "index": 0,
        "action": "modify",
        "path": target.name,
        "current_sha256": _sha_bytes(baseline),
        "payload_file": "payload_0.bin",
        "payload_sha256": _sha_bytes(payload),
        "changed_lines": 2,
        "changed_bytes": 0,
    }
    if version == 2:
        # Exact v2 descriptor shape emitted at 44f0312.
        (patch_dir / "payload_0.bin").write_bytes(payload)
    else:
        # Exact v3 descriptor shape emitted at b40d75d.
        descriptor, parts = build_payload_parts(0, payload)
        entry.update(descriptor)
        for filename, data in parts:
            (patch_dir / filename).write_bytes(data)

    manifest = {
        "patch_id": patch_id,
        "bundle_version": version,
        "created_at": "2026-08-15T12:00:00+00:00",
        "repo_root": "",
        "repo_fingerprint": rw._repo_fingerprint(repo),
        "git_head_at_preview": rw._git_head(repo),
        "status": status,
        "operations": [entry],
        "errors": ["historical preview failure"] if status == "preview_failed" else [],
    }
    (patch_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (patch_dir / "preview.diff").write_text(
        "--- a/legacy.py\n+++ b/legacy.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n",
        encoding="utf-8",
    )
    return target, baseline, payload, patch_id


def test_g5_1_apply_selected_child_is_parser_and_repair_blind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, _, source, _, _ = _repair_source(repo, runs)
    proposal_id = _manifest(runs, source["patch_id"])["repair_proposal"]["proposal_id"]
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="g5-repair-blind",
        decision="accept_repair",
        proposal_id=proposal_id,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "apply authority must not invoke parser or repair intelligence"
        )

    monkeypatch.setattr(rw, "build_patch_repair_proposal", forbidden)
    monkeypatch.setattr(rw, "derive_authored_span_provenance", forbidden)
    monkeypatch.setattr(rw, "validate_python_candidate", forbidden)
    monkeypatch.setattr(builtins, "compile", forbidden)
    monkeypatch.setattr(ast, "parse", forbidden)
    monkeypatch.setattr(tokenize, "tokenize", forbidden)
    monkeypatch.setattr(tokenize, "generate_tokens", forbidden)

    applied = apply_previewed_repo_change(repo, child["patch_id"], runs)

    assert applied["ok"] is True
    assert target.read_bytes() == baseline
    source_status = get_patch_status(repo, source["patch_id"], runs)
    assert source_status["status"] == "resolved"


def test_g5_1_apply_uses_child_payload_not_resolution_decision_metadata(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, _, source, _, _ = _repair_source(repo, runs)
    proposal_id = _manifest(runs, source["patch_id"])["repair_proposal"]["proposal_id"]
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="g5-payload-selected",
        decision="accept_repair",
        proposal_id=proposal_id,
    )
    child_manifest = _manifest(runs, child["patch_id"])
    selected_payload = (
        _patch_dir(runs, child["patch_id"])
        / child_manifest["operations"][0]["payload_file"]
    ).read_bytes()
    assert selected_payload == baseline

    # Resolution metadata is provenance, never a second payload-selection control plane.
    child_manifest["resolution"]["decision"] = "accept_original"
    _write_manifest(runs, child["patch_id"], child_manifest)

    applied = apply_previewed_repo_change(repo, child["patch_id"], runs)

    assert applied["ok"] is True
    assert target.read_bytes() == selected_payload


@pytest.mark.parametrize("version", [2, 3])
def test_g5_2_actual_historical_preview_ok_fixture_applies(
    tmp_path: Path, version: int
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, _, payload, patch_id = _write_historical_fixture_bundle(
        repo, runs, version=version
    )

    applied = apply_previewed_repo_change(repo, patch_id, runs)

    assert applied["ok"] is True
    assert target.read_bytes() == payload
    assert _manifest(runs, patch_id)["bundle_version"] == version


@pytest.mark.parametrize("version", [2, 3])
def test_g5_2_actual_historical_preview_failed_fixture_is_rejected(
    tmp_path: Path, version: int
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, _, patch_id = _write_historical_fixture_bundle(
        repo, runs, version=version, status="preview_failed"
    )

    with pytest.raises(ValueError, match="preview had validation errors"):
        apply_previewed_repo_change(repo, patch_id, runs)
    assert target.read_bytes() == baseline


@pytest.mark.parametrize(
    "status", ["preview_resolution_required", "resolved", "resolution_pending"]
)
def test_g5_2_v4_source_resolution_states_are_not_applicable(
    tmp_path: Path, status: str
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "source_state.py"
    _write(target, b"value = 1\n")
    preview = preview_repo_patch(
        repo,
        [
            {
                "type": "exact_text",
                "path": target.name,
                "expected_sha256": _sha(target),
                "old_text": "value = 1",
                "new_text": "value = 2",
            }
        ],
        runs,
    )
    manifest = _manifest(runs, preview["patch_id"])
    assert manifest["bundle_version"] == 4
    manifest["status"] = status
    _write_manifest(runs, preview["patch_id"], manifest)

    with pytest.raises(ValueError, match="not applicable"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert target.read_bytes() == b"value = 1\n"


def test_g5_2_selected_v4_child_is_applicable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, _, source, _, _ = _repair_source(repo, runs)
    proposal_id = _manifest(runs, source["patch_id"])["repair_proposal"]["proposal_id"]
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="g5-v4-child",
        decision="accept_repair",
        proposal_id=proposal_id,
    )

    applied = apply_previewed_repo_change(repo, child["patch_id"], runs)

    assert applied["ok"] is True
    assert target.read_bytes() == baseline
    assert get_patch_status(repo, child["patch_id"], runs)["status"] == "applied"


def test_g5_2_future_bundle_version_fails_closed(tmp_path: Path) -> None:
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
                "path": target.name,
                "expected_sha256": _sha(target),
                "old_text": "value = 1",
                "new_text": "value = 2",
            }
        ],
        runs,
    )
    manifest = _manifest(runs, preview["patch_id"])
    manifest["bundle_version"] = 999
    _write_manifest(runs, preview["patch_id"], manifest)

    with pytest.raises(ValueError, match="opaque preview bundle"):
        apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert target.read_bytes() == b"value = 1\n"


def test_g5_1_selected_child_rechecks_repo_file_path_payload_and_limits(
    tmp_path: Path,
) -> None:
    # Repo binding.
    repo = tmp_path / "repo_binding"
    repo.mkdir()
    runs = tmp_path / "runs_binding"
    _, child = _resolve_repair_child(repo, runs, request_id="binding")
    other_repo = tmp_path / "other_repo"
    other_repo.mkdir()
    with pytest.raises(ValueError, match="does not belong"):
        apply_previewed_repo_change(other_repo, child["patch_id"], runs)

    # Current-file hash.
    repo = tmp_path / "repo_stale"
    repo.mkdir()
    runs = tmp_path / "runs_stale"
    source, child = _resolve_repair_child(repo, runs, request_id="stale")
    source_manifest = _manifest(runs, source["patch_id"])
    target = repo / source_manifest["operations"][0]["path"]
    _write(target, b"changed after resolution\n")
    with pytest.raises(ValueError, match="changed since preview"):
        apply_previewed_repo_change(repo, child["patch_id"], runs)

    # Lexical path safety.
    repo = tmp_path / "repo_path"
    repo.mkdir()
    runs = tmp_path / "runs_path"
    _, child = _resolve_repair_child(repo, runs, request_id="path")
    manifest = _manifest(runs, child["patch_id"])
    manifest["operations"][0]["path"] = "../escape.py"
    _write_manifest(runs, child["patch_id"], manifest)
    with pytest.raises(ValueError):
        apply_previewed_repo_change(repo, child["patch_id"], runs)

    # Payload hash.
    repo = tmp_path / "repo_payload"
    repo.mkdir()
    runs = tmp_path / "runs_payload"
    _, child = _resolve_repair_child(repo, runs, request_id="payload")
    manifest = _manifest(runs, child["patch_id"])
    payload_path = (
        _patch_dir(runs, child["patch_id"]) / manifest["operations"][0]["payload_file"]
    )
    payload_path.write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="payload verification failed"):
        apply_previewed_repo_change(repo, child["patch_id"], runs)

    # Recomputed apply limits, even if a child bundle is tampered consistently.
    repo = tmp_path / "repo_limit"
    repo.mkdir()
    runs = tmp_path / "runs_limit"
    _, child = _resolve_repair_child(repo, runs, request_id="limit")
    manifest = _manifest(runs, child["patch_id"])
    payload_path = (
        _patch_dir(runs, child["patch_id"]) / manifest["operations"][0]["payload_file"]
    )
    oversized = b"value = 1\n" * (rw.MAX_PATCH_LINES + 100)
    payload_path.write_bytes(oversized)
    manifest["operations"][0]["payload_sha256"] = _sha_bytes(oversized)
    manifest["operations"][0]["payload_size_bytes"] = len(oversized)
    manifest["operations"][0]["payload_chunks"] = []
    _write_manifest(runs, child["patch_id"], manifest)
    with pytest.raises(ValueError, match="changed-line limit"):
        apply_previewed_repo_change(repo, child["patch_id"], runs)


def test_g5_1_selected_child_rechecks_git_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Soma Test"], cwd=repo, check=True)
    target = repo / "head_guard.py"
    _write(target, b'assert ready == "ok"\nnext_call()\n')
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "baseline"], cwd=repo, check=True, capture_output=True
    )
    runs = tmp_path / "runs"
    baseline = target.read_bytes()
    cut = baseline.index(b"\n")
    candidate = baseline[:cut] + b'}],"view":"full' + baseline[cut:]
    source = preview_repo_patch(
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
    proposal_id = _manifest(runs, source["patch_id"])["repair_proposal"]["proposal_id"]
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="g5-head",
        decision="accept_repair",
        proposal_id=proposal_id,
    )
    (repo / "unrelated.txt").write_text("advance\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "advance head"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    with pytest.raises(ValueError, match="Git HEAD has changed since preview"):
        apply_previewed_repo_change(repo, child["patch_id"], runs)
    assert target.read_bytes() == baseline


@pytest.mark.parametrize("decision", ["accept_repair", "accept_original"])
def test_g5_3_selected_child_applies_and_reverts_with_provenance_intact(
    tmp_path: Path, decision: str
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, candidate, source, _, _ = _repair_source(repo, runs)
    source_manifest = _manifest(runs, source["patch_id"])
    proposal_id = source_manifest["repair_proposal"]["proposal_id"]
    kwargs = {"proposal_id": proposal_id} if decision == "accept_repair" else {}
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id=f"g5-{decision}",
        decision=decision,
        **kwargs,
    )
    child_manifest_before = _manifest(runs, child["patch_id"])
    resolution_before = json.loads(json.dumps(child_manifest_before["resolution"]))

    applied = apply_previewed_repo_change(repo, child["patch_id"], runs)
    expected = baseline if decision == "accept_repair" else candidate
    assert applied["ok"] is True
    assert target.read_bytes() == expected
    reverted = revert_managed_patch(repo, child["patch_id"], runs)

    assert reverted["ok"] is True
    assert target.read_bytes() == baseline
    child_manifest_after = _manifest(runs, child["patch_id"])
    source_manifest_after = _manifest(runs, source["patch_id"])
    assert child_manifest_after["status"] == "reverted"
    assert child_manifest_after["resolution"] == resolution_before
    assert source_manifest_after["status"] == "resolved"
    assert source_manifest_after["resolution"]["child_patch_id"] == child["patch_id"]
    assert source_manifest_after["resolution"]["decision"] == decision

    with pytest.raises(ValueError, match="not in 'applied' state"):
        revert_managed_patch(repo, source["patch_id"], runs)


def test_g5_3_selected_child_partial_write_failure_rolls_back_exact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target, baseline, _, source, second_target, second_baseline = _repair_source(
        repo, runs, include_second_file=True
    )
    assert second_target is not None
    assert second_baseline is not None
    source_manifest = _manifest(runs, source["patch_id"])
    proposal_id = source_manifest["repair_proposal"]["proposal_id"]
    child = resolve_patch_preview(
        repo,
        runs,
        source_patch_id=source["patch_id"],
        resolution_request_id="g5-partial-failure",
        decision="accept_repair",
        proposal_id=proposal_id,
    )
    original_atomic_write_bytes = rw._atomic_write_bytes
    apply_writes = {"count": 0}

    def fail_second_apply(path: Path, data: bytes, suffix: str) -> None:
        if suffix == ".soma_apply_tmp":
            apply_writes["count"] += 1
            if apply_writes["count"] == 2:
                raise OSError("simulated second selected-child write failure")
        original_atomic_write_bytes(path, data, suffix)

    monkeypatch.setattr(rw, "_atomic_write_bytes", fail_second_apply)

    with pytest.raises(RuntimeError, match="partial rollback attempted"):
        apply_previewed_repo_change(repo, child["patch_id"], runs)

    assert target.read_bytes() == baseline
    assert second_target.read_bytes() == second_baseline
    child_manifest = _manifest(runs, child["patch_id"])
    source_manifest_after = _manifest(runs, source["patch_id"])
    assert child_manifest["status"] == "failed"
    assert source_manifest_after["status"] == "resolved"
    assert source_manifest_after["resolution"]["child_patch_id"] == child["patch_id"]
