from __future__ import annotations

import json
from pathlib import Path

from soma.run_publication import (
    publish_run_result,
    terminal_result_publication_needs_repair,
)
from soma.run_store import RunStore, utc_now


def _terminal_run(tmp_path: Path, result: dict) -> tuple[RunStore, str, Path]:
    runs_dir = tmp_path / "runs"
    store = RunStore(runs_dir)
    run_id = "20260714T000000Z_project_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )
    current = store.get_run(run_id)
    assert store.transition_terminal(
        run_id,
        status="completed",
        result=result,
        expected_statuses=("queued",),
        expected_state_version=current["state_version"],
        ended_at=utc_now(),
    )
    return store, run_id, run_dir


def test_publication_uses_database_winner_and_repairs_losing_artifact(
    tmp_path: Path,
) -> None:
    winner = {"run_id": "winner", "status": "completed", "summary": "winner"}
    store, run_id, run_dir = _terminal_run(tmp_path, winner)
    (run_dir / "result.json").write_text(
        json.dumps({"status": "completed", "summary": "loser"}), encoding="utf-8"
    )

    published = publish_run_result(store, run_id)

    assert published["ok"] is True
    assert json.loads((run_dir / "result.json").read_text(encoding="utf-8")) == winner
    assert store.get_run(run_id)["result"] == winner
    assert store.get_run(run_id)["result_publication_status"] == "published"


def test_publication_failure_preserves_terminal_database_result(
    monkeypatch, tmp_path: Path
) -> None:
    winner = {"run_id": "winner", "status": "completed", "summary": "database"}
    store, run_id, _ = _terminal_run(tmp_path, winner)
    monkeypatch.setattr(
        "soma.run_publication.atomic_write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    published = publish_run_result(store, run_id)

    current = store.get_run(run_id)
    assert published["ok"] is False
    assert current["status"] == "completed"
    assert current["result"] == winner
    assert current["result_publication_status"] == "failed"
    assert "disk full" in current["result_publication_error"]


def test_real_publication_retry_preserves_authoritative_source_and_is_idempotent(
    monkeypatch, tmp_path: Path
) -> None:
    winner = {"run_id": "winner", "status": "completed", "summary": "database"}
    store, run_id, run_dir = _terminal_run(tmp_path, winner)
    from soma import run_publication

    real_atomic_write_json = run_publication.atomic_write_json
    write_attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal write_attempts
        write_attempts += 1
        if write_attempts == 1:
            raise OSError("simulated publication failure")
        return real_atomic_write_json(*args, **kwargs)

    monkeypatch.setattr(run_publication, "atomic_write_json", fail_once)
    first = publish_run_result(store, run_id)
    failed = store.get_run(run_id)
    authoritative_result = failed["result"]
    source_hash = failed["public_result_source_sha256"]

    second = publish_run_result(store, run_id)
    published = store.get_run(run_id)
    third = publish_run_result(store, run_id)

    assert first["ok"] is False
    assert failed["result_publication_status"] == "failed"
    assert second["ok"] is True
    assert third["ok"] is True
    assert published["result"] == authoritative_result == winner
    assert published["public_result_source_sha256"] == source_hash
    assert json.loads((run_dir / "result.json").read_text(encoding="utf-8")) == winner
    assert write_attempts == 2


def test_publication_repair_check_detects_only_broken_terminal_evidence(
    tmp_path: Path,
) -> None:
    winner = {"run_id": "winner", "status": "completed", "summary": "database"}
    store, run_id, run_dir = _terminal_run(tmp_path, winner)
    pending = store.get_result_source_snapshot(run_id)
    assert terminal_result_publication_needs_repair(pending) is True

    assert publish_run_result(store, run_id)["ok"] is True
    healthy = store.get_result_source_snapshot(run_id)
    assert terminal_result_publication_needs_repair(healthy) is False
    listed = store.list_terminal_runs()[0]
    assert "result_json" not in listed
    assert terminal_result_publication_needs_repair(listed) is False

    (run_dir / "result.json").write_text("{}\n", encoding="utf-8")
    damaged = store.get_result_source_snapshot(run_id)
    assert terminal_result_publication_needs_repair(damaged) is True
