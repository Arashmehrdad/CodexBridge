from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path

import pytest

from soma import evidence_backfill
from soma.evidence_backfill import (
    EVIDENCE_ARTIFACT,
    STATE_ALREADY_COMPACT,
    STATE_FAILED,
    STATE_MIGRATED,
    run_backfill,
)
from soma.run_store import RunStore


def _amplified_result(tool_owned_count: int) -> dict:
    tool_owned = [f".codex-tmp/scratch-{i:05d}.txt" for i in range(tool_owned_count)]
    manifest = {
        "ok": True,
        "staged": ["real.txt"],
        "unstaged": [],
        "untracked": tool_owned + ["other.txt"],
        "deleted": [],
        "ignored": [],
        "renamed": [],
        "tool_owned": tool_owned,
        "files": [
            {"path": path, "tool_owned": True, "size_bytes": 4, "line_count": 1}
            for path in tool_owned
        ]
        + [{"path": "real.txt", "tool_owned": False, "size_bytes": 9, "line_count": 1}],
        "git_status": "\n".join(f"?? {path}" for path in tool_owned),
    }
    return {
        "ok": True,
        "changed_files": ["real.txt"],
        "preserved_preexisting_changes": list(tool_owned),
        "commit_result": {
            "ok": True,
            "commit_hash": "b" * 40,
            "stage_manifest_before": manifest,
            "stage_manifest_after": manifest,
            "git_status": manifest["git_status"],
            "remaining_dirty_files": list(tool_owned),
            "error": "",
        },
    }


@pytest.fixture()
def store(tmp_path: Path) -> tuple[Path, RunStore, str, dict]:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    store = RunStore(runs_dir)
    run_id = "20260726T120000Z_repo_apply_aaaaaaaa"
    run_dir = runs_dir / run_id
    run_dir.mkdir()
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="repo_apply",
        run_dir=run_dir,
        input_data={"paths": ["real.txt"]},
        status="succeeded",
    )
    result = _amplified_result(3000)
    with store.connect() as conn:
        conn.execute(
            "UPDATE runs SET result_json = ?, status = 'succeeded' WHERE run_id = ?",
            (json.dumps(result), run_id),
        )
    return runs_dir / "soma.sqlite3", store, run_id, result


def _row(database: Path, run_id: str) -> sqlite3.Row:
    connection = sqlite3.connect(database.as_posix())
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    finally:
        connection.close()


def test_dry_run_changes_nothing(store) -> None:
    database, _, run_id, _ = store
    before = _row(database, run_id)["result_json"]

    summary = run_backfill(database, apply_changes=False)

    assert summary["states"].get(STATE_MIGRATED) == 1
    assert _row(database, run_id)["result_json"] == before
    assert not (database.parent / run_id / EVIDENCE_ARTIFACT).exists()


def test_backfill_preserves_complete_evidence_and_verifies_by_hash(store) -> None:
    database, _, run_id, original = store
    original_bytes = len(_row(database, run_id)["result_json"])

    summary = run_backfill(database, apply_changes=True)
    assert summary["failures"] == []
    assert summary["states"].get(STATE_MIGRATED) == 1

    row = _row(database, run_id)
    migrated = json.loads(row["result_json"])
    assert len(row["result_json"]) < original_bytes / 50

    reference = migrated["commit_evidence_ref"]
    assert reference["backfilled"] is True
    artifact = Path(row["run_dir"]) / EVIDENCE_ARTIFACT
    raw = artifact.read_bytes()
    assert sha256(raw).hexdigest() == reference["sha256"]
    assert len(raw) == reference["size_bytes"]

    # The externalized body must be complete and untruncated, because the
    # database row was the only complete copy before migration.
    body = json.loads(raw)
    commit = original["commit_result"]
    assert body["stage_manifest_before"] == commit["stage_manifest_before"]
    assert body["stage_manifest_after"] == commit["stage_manifest_after"]
    assert body["git_status"] == commit["git_status"]
    assert body["remaining_dirty_files"] == commit["remaining_dirty_files"]
    assert body["preserved_preexisting_changes"] == original[
        "preserved_preexisting_changes"
    ]

    # Correctness-relevant state survives inline.
    assert migrated["commit_result"]["commit_hash"] == "b" * 40
    assert migrated["commit_result"]["stage_manifest_after"]["staged"] == ["real.txt"]


def test_backfill_leaves_opaque_identity_untouched(store) -> None:
    database, _, run_id, _ = store
    before = dict(_row(database, run_id))

    run_backfill(database, apply_changes=True)

    after = dict(_row(database, run_id))
    changed = {key for key in before if before[key] != after[key]}
    assert changed == {"result_json"}


def test_backfill_is_resumable_and_idempotent(store) -> None:
    database, _, run_id, _ = store

    first = run_backfill(database, apply_changes=True)
    assert first["states"].get(STATE_MIGRATED) == 1
    migrated_json = _row(database, run_id)["result_json"]

    second = run_backfill(database, apply_changes=True)

    assert second["resumed_from"] == 1
    assert second["states"].get(STATE_MIGRATED) is None
    assert second["reclaimed_bytes"] == 0
    assert _row(database, run_id)["result_json"] == migrated_json


def test_already_compact_rows_are_not_rewritten(store) -> None:
    database, _, run_id, _ = store
    run_backfill(database, apply_changes=True)
    migrated_json = _row(database, run_id)["result_json"]

    # Clear progress so the row is re-examined rather than skipped by resume.
    connection = sqlite3.connect(database.as_posix())
    connection.execute("DELETE FROM evidence_backfill_progress")
    connection.commit()
    connection.close()

    summary = run_backfill(database, apply_changes=True, minimum_bytes=0)

    assert summary["states"].get(STATE_ALREADY_COMPACT, 0) >= 1
    assert summary["states"].get(STATE_MIGRATED) is None
    assert _row(database, run_id)["result_json"] == migrated_json


def test_artifact_write_failure_leaves_the_row_untouched(store, monkeypatch) -> None:
    database, _, run_id, _ = store
    before = _row(database, run_id)["result_json"]

    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(evidence_backfill, "_write_verified_artifact", explode)

    summary = run_backfill(database, apply_changes=True)

    assert summary["states"].get(STATE_FAILED) == 1
    assert summary["failures"][0]["run_id"] == run_id
    assert _row(database, run_id)["result_json"] == before


def test_projection_change_blocks_migration(store, monkeypatch) -> None:
    database, _, run_id, _ = store
    before = _row(database, run_id)["result_json"]
    calls = {"n": 0}

    def drifting_projection(*_args, **_kwargs):
        calls["n"] += 1
        return {"probe": calls["n"]}

    monkeypatch.setattr(
        evidence_backfill, "build_public_result_projection", drifting_projection
    )

    summary = run_backfill(database, apply_changes=True)

    assert summary["states"].get(STATE_FAILED) == 1
    assert "projection would change" in summary["failures"][0]["detail"]
    assert _row(database, run_id)["result_json"] == before
    assert not (Path(_row(database, run_id)["run_dir"]) / EVIDENCE_ARTIFACT).exists()


def test_artifact_root_redirects_writes_for_isolated_rehearsal(store, tmp_path) -> None:
    database, _, run_id, _ = store
    sandbox = tmp_path / "sandbox"

    run_backfill(database, apply_changes=True, artifact_root=sandbox)

    live_run_dir = Path(_row(database, run_id)["run_dir"])
    assert not (live_run_dir / EVIDENCE_ARTIFACT).exists()
    assert (sandbox / run_id / EVIDENCE_ARTIFACT).is_file()
