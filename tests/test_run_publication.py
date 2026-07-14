from __future__ import annotations

import json
from pathlib import Path

from codexbridge.run_publication import publish_run_result
from codexbridge.run_store import RunStore, utc_now


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
        "codexbridge.run_publication.atomic_write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    published = publish_run_result(store, run_id)

    current = store.get_run(run_id)
    assert published["ok"] is False
    assert current["status"] == "completed"
    assert current["result"] == winner
    assert current["result_publication_status"] == "failed"
    assert "disk full" in current["result_publication_error"]
