from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from codexbridge.events import redact_and_truncate
from codexbridge.public_projection_contract import (
    DEFAULT_PUBLIC_BYTE_BUDGETS,
    NormalizedOutcome,
)
from codexbridge.run_public_result import (
    PUBLIC_RESULT_SCHEMA_VERSION,
    PUBLIC_RESULT_STATUS_FALLBACK,
    PUBLIC_RESULT_STATUS_NOT_MATERIALIZED,
    PUBLIC_RESULT_STATUS_READY,
    authoritative_result_sha256,
    build_public_result_projection,
    canonical_public_json_bytes,
    normalized_outcome,
)
from codexbridge.run_publication import materialize_public_result, publish_run_result
from codexbridge.run_store import RunStore, utc_now


RUN_ID = "20260722T040000Z_project_command_c0ffee00"
PUBLIC_RESULT_COLUMNS = {
    "public_result_json",
    "public_result_schema_version",
    "public_result_source_sha256",
    "public_result_status",
    "public_result_error",
}


def _terminal_run(
    tmp_path: Path,
    result: dict,
    *,
    status: str = "completed",
) -> tuple[RunStore, str, Path]:
    runs_dir = tmp_path / "runs"
    store = RunStore(runs_dir)
    run_dir = runs_dir / RUN_ID
    run_dir.mkdir(parents=True)
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )
    current = store.get_run(RUN_ID)
    transitioned = store.transition_terminal(
        RUN_ID,
        status=status,
        result=result,
        expected_statuses=("queued",),
        expected_state_version=current["state_version"],
        ended_at=utc_now(),
        summary=str(result.get("summary") or ""),
        error=str(result.get("error") or ""),
        safety_failure=bool(result.get("safety_failure")),
    )
    assert transitioned is not None
    return store, RUN_ID, run_dir


def _raw_result_json(store: RunStore, run_id: str) -> str:
    with store.connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    assert row is not None
    return str(row["result_json"])


def test_publication_materializes_source_bound_bounded_redacted_projection(
    tmp_path: Path,
) -> None:
    result = {
        "status": "completed",
        "classification": "success",
        "process_success": True,
        "summary": "api_key=topsecret completed",
        "error": "",
        "stdout": "raw stdout must not be in compact projection",
        "stderr": "raw stderr must not be in compact projection",
        "argv": ["python", "-m", "pytest"],
        "environment": {"TOKEN": "private"},
        "changed_files": [f"src/file_{index}.py" for index in range(40)],
        "remaining_risks": ["none"],
        "staged_artifacts": [
            {
                "classification": "protected_evidence",
                "relative_path": "stdout.bin",
                "sha256": "a" * 64,
                "size_bytes": 123,
                "stream": "stdout",
            }
        ],
    }
    store, run_id, run_dir = _terminal_run(tmp_path, result)

    published = publish_run_result(store, run_id)
    current = store.get_run(run_id)
    projection = current["public_result"]
    raw_result_json = _raw_result_json(store, run_id)
    serialized_projection = canonical_public_json_bytes(projection)

    assert published["ok"] is True
    assert current["result"] == result
    assert current["public_result_status"] == PUBLIC_RESULT_STATUS_READY
    assert current["public_result_schema_version"] == PUBLIC_RESULT_SCHEMA_VERSION
    assert current["public_result_source_sha256"] == authoritative_result_sha256(
        raw_result_json
    )
    assert projection["source_result_sha256"] == current["public_result_source_sha256"]
    assert projection["payload_bytes"] == len(serialized_projection)
    assert len(serialized_projection) <= DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result
    assert b"topsecret" not in serialized_projection
    assert b"[REDACTED]" in serialized_projection
    assert b"raw stdout" not in serialized_projection
    assert b"raw stderr" not in serialized_projection
    assert b'"argv"' not in serialized_projection
    assert b'"environment"' not in serialized_projection

    expected_artifact = (
        json.dumps(redact_and_truncate(result), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    assert (run_dir / "result.json").read_bytes() == expected_artifact
    assert published["hash"] == hashlib.sha256(expected_artifact).hexdigest()


def test_large_projection_is_deterministic_and_prefix_bounded() -> None:
    result = {
        "status": "completed",
        "classification": "success",
        "process_success": True,
        "summary": "🙂" * 20_000,
        "error": "x" * 20_000,
        "changed_files": [f"src/file_{index:04d}.py" for index in range(1_000)],
        "remaining_risks": [f"risk-{index}-" + "y" * 500 for index in range(100)],
        "validation_results": [{"name": f"test-{index}", "ok": True} for index in range(200)],
    }
    run = {
        "run_id": RUN_ID,
        "repo_name": "sample",
        "tool": "project_command",
        "status": "completed",
        "summary": result["summary"],
        "error": result["error"],
        "safety_failure": False,
    }
    source_sha256 = authoritative_result_sha256(json.dumps(result, sort_keys=True))

    first = build_public_result_projection(run, result, source_sha256)
    second = build_public_result_projection(run, result, source_sha256)
    serialized = canonical_public_json_bytes(first)

    assert first == second
    assert first["payload_bytes"] == len(serialized)
    assert len(serialized) <= DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result
    assert first["result"]["changed_files"] == [
        f"src/file_{index:04d}.py" for index in range(20)
    ]
    assert first["result"]["truncated_fields"]
    assert first["result"]["truncated_collections"]


def test_managed_apply_projection_exposes_bounded_terminal_metadata() -> None:
    run = {
        "run_id": RUN_ID,
        "repo_name": "sample",
        "tool": "repo_apply",
        "status": "completed",
    }
    result = {
        "status": "completed",
        "operation": "previewed_change",
        "patch_id": "patch_123",
        "commit_hash": "a" * 40,
        "idempotent_replay": False,
        "changed_files": [f"src/file_{index}.py" for index in range(100)],
        "preserved_preexisting_changes": ["README.md", "notes.txt"],
        "validation_results": [{"ok": True}, {"ok": False}, {"ok": True}],
        "stdout": "secret output must remain evidence-only",
    }

    projection = build_public_result_projection(
        run, result, authoritative_result_sha256(json.dumps(result, sort_keys=True))
    )

    managed = projection["result"]["managed_apply"]
    assert managed["operation"] == "previewed_change"
    assert managed["patch_id"] == "patch_123"
    assert managed["commit_hash"] == "a" * 40
    assert managed["preserved_work"] == {"count": 2}
    assert managed["validation_summary"] == {"total": 3, "passed": 2, "failed": 1}
    assert "stdout" not in projection["result"]
    assert len(canonical_public_json_bytes(projection)) <= DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result


@pytest.mark.parametrize(
    ("run", "result", "expected"),
    [
        ({"status": "completed"}, {"classification": "success"}, NormalizedOutcome.SUCCESS),
        ({"status": "partial"}, {}, NormalizedOutcome.PARTIAL),
        ({"status": "failed"}, {"classification": "validation_failure"}, NormalizedOutcome.VALIDATION_FAILURE),
        ({"status": "failed", "safety_failure": True}, {}, NormalizedOutcome.POLICY_DENIAL),
        ({"status": "needs_input"}, {}, NormalizedOutcome.NEEDS_INPUT),
        ({"status": "failed"}, {"classification": "cancellation_requested"}, NormalizedOutcome.CANCELLATION_REQUESTED),
        ({"status": "cancelled"}, {}, NormalizedOutcome.CANCELLATION_VERIFIED),
        ({"status": "failed"}, {"classification": "cancellation_uncertain"}, NormalizedOutcome.CANCELLATION_UNCERTAIN),
        ({"status": "timed_out"}, {}, NormalizedOutcome.INFRASTRUCTURE_FAILURE),
        ({"status": "failed"}, {"classification": "cleanup_incomplete"}, NormalizedOutcome.CLEANUP_INCOMPLETE),
        ({"status": "failed"}, {"classification": "ambiguous_side_effect"}, NormalizedOutcome.AMBIGUOUS_SIDE_EFFECT),
        ({"status": "failed"}, {"classification": "reconciliation_required"}, NormalizedOutcome.RECONCILIATION_REQUIRED),
    ],
)
def test_normalized_outcomes_cover_required_terminal_classes(
    run: dict, result: dict, expected: NormalizedOutcome
) -> None:
    assert normalized_outcome(run, result) is expected


def test_projector_failure_publishes_bounded_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = {"status": "completed", "summary": "winner"}
    store, run_id, _run_dir = _terminal_run(tmp_path, result)
    monkeypatch.setattr(
        "codexbridge.run_publication.build_public_result_projection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("projector boom")),
    )

    published = publish_run_result(store, run_id)
    current = store.get_run(run_id)
    projection = current["public_result"]

    assert published["ok"] is True
    assert current["result_publication_status"] == "published"
    assert current["public_result_status"] == PUBLIC_RESULT_STATUS_FALLBACK
    assert "projector boom" in current["public_result_error"]
    assert projection["projection_status"] == PUBLIC_RESULT_STATUS_FALLBACK
    assert projection["payload_bytes"] == len(canonical_public_json_bytes(projection))
    assert projection["payload_bytes"] <= DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result


def test_fallback_failure_still_publishes_emergency_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = {"status": "completed", "summary": "winner"}
    store, run_id, _run_dir = _terminal_run(tmp_path, result)
    monkeypatch.setattr(
        "codexbridge.run_publication.build_public_result_projection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("primary boom")),
    )
    monkeypatch.setattr(
        "codexbridge.run_publication.build_public_result_fallback",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fallback boom")),
    )

    published = publish_run_result(store, run_id)
    current = store.get_run(run_id)
    projection = current["public_result"]

    assert published["ok"] is True
    assert current["result_publication_status"] == "published"
    assert current["public_result_status"] == PUBLIC_RESULT_STATUS_FALLBACK
    assert "primary boom" in current["public_result_error"]
    assert "fallback boom" in current["public_result_error"]
    assert projection["payload_bytes"] == len(canonical_public_json_bytes(projection))
    assert projection["payload_bytes"] <= DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result


def test_legacy_terminal_row_materializes_once_and_reuses_projection(
    tmp_path: Path,
) -> None:
    result = {"status": "completed", "classification": "success", "summary": "legacy"}
    store, run_id, _run_dir = _terminal_run(tmp_path, result)
    before = store.get_run(run_id)

    assert before["public_result_status"] == PUBLIC_RESULT_STATUS_NOT_MATERIALIZED
    first = materialize_public_result(store, run_id)
    after_first = store.get_run(run_id)
    second = materialize_public_result(store, run_id)
    after_second = store.get_run(run_id)

    assert first == second
    assert after_first["public_result_status"] == PUBLIC_RESULT_STATUS_READY
    assert after_first["state_version"] == before["state_version"] + 1
    assert after_second["state_version"] == after_first["state_version"]
    assert after_second["public_result_source_sha256"] == authoritative_result_sha256(
        _raw_result_json(store, run_id)
    )

    public_snapshot = store.get_public_result_snapshot(run_id)
    assert "result_json" not in public_snapshot
    assert "result" not in public_snapshot
    assert public_snapshot["public_result"] == first


def test_stale_projection_binding_rebuilds_with_compare_and_set(tmp_path: Path) -> None:
    result = {"status": "completed", "classification": "success", "summary": "current"}
    store, run_id, _run_dir = _terminal_run(tmp_path, result)
    original = materialize_public_result(store, run_id)
    current = store.get_run(run_id)
    store.update_run(
        run_id,
        public_result_schema_version="legacy.schema",
        public_result_source_sha256="0" * 64,
    )
    stale = store.get_run(run_id)

    rebuilt = materialize_public_result(store, run_id)
    refreshed = store.get_run(run_id)

    assert rebuilt == original
    assert refreshed["public_result_schema_version"] == PUBLIC_RESULT_SCHEMA_VERSION
    assert refreshed["public_result_source_sha256"] == authoritative_result_sha256(
        _raw_result_json(store, run_id)
    )
    assert refreshed["state_version"] == stale["state_version"] + 1
    assert refreshed["state_version"] > current["state_version"]


def test_existing_database_migrates_public_result_columns_in_place(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    store = RunStore(runs_dir)
    with store.connect() as conn:
        for column in sorted(PUBLIC_RESULT_COLUMNS):
            conn.execute(f"ALTER TABLE runs DROP COLUMN {column}")
        before = {
            row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
    assert PUBLIC_RESULT_COLUMNS.isdisjoint(before)

    migrated = RunStore(runs_dir)
    with migrated.connect() as conn:
        after = {
            row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }

    assert PUBLIC_RESULT_COLUMNS <= after
