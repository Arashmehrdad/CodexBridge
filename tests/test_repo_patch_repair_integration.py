from __future__ import annotations

import hashlib
import json
from pathlib import Path

from soma.repo_writer import preview_repo_patch


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _manifest(runs: Path, patch_id: str) -> tuple[Path, dict]:
    patch_dir = runs / "managed_patches" / patch_id
    return patch_dir, json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))


def test_g2_4_incident_b_persists_separate_repair_payload_without_selecting_it(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runs = tmp_path / "runs"
    target = repo / "incident_b.py"
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
                "path": "incident_b.py",
                "expected_sha256": _sha(target),
                "old_text": baseline.decode(),
                "new_text": candidate.decode(),
            }
        ],
        runs,
    )
    patch_dir, manifest = _manifest(runs, preview["patch_id"])
    entry = manifest["operations"][0]
    proposal = manifest["repair_proposal"]

    assert preview["ok"] is True
    assert manifest["status"] == "preview_ok"
    assert entry["candidate_validation"]["regression_detected"] is True
    assert entry["authored_span_provenance"]["disposition"] == "owned"
    assert proposal is not None
    assert proposal["rule_id"] == "repo_preview.patch.trailing_view.v1"
    assert (patch_dir / entry["payload_file"]).read_bytes() == candidate
    repair_descriptor = proposal["repaired_payload_descriptor"]
    repair_bytes = (patch_dir / repair_descriptor["file"]).read_bytes()
    assert repair_bytes == baseline
    assert hashlib.sha256(repair_bytes).hexdigest() == repair_descriptor["sha256"]
    assert entry["payload_sha256"] != repair_descriptor["sha256"]
    assert target.read_bytes() == baseline


def test_g2_4_incident_a_persists_no_proposal(tmp_path: Path) -> None:
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

    assert preview["ok"] is True
    assert manifest["operations"][0]["candidate_validation"]["regression_detected"] is True
    assert manifest["repair_proposal"] is None
    assert list(patch_dir.glob("repair_payload_*.bin")) == []
    assert target.read_bytes() == baseline


def test_g2_4_multiple_file_proposals_are_not_guessed(tmp_path: Path) -> None:
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

    assert preview["ok"] is True
    assert manifest["repair_proposal"] is None
    assert list(patch_dir.glob("repair_payload_*.bin")) == []
