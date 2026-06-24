from __future__ import annotations

import json
from pathlib import Path

from codexbridge.dashboard import get_dashboard_summary
from codexbridge.memory.repository import ProjectMemoryRepository


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_dashboard_summary_empty_runs_dir(tmp_path: Path) -> None:
    summary = get_dashboard_summary(tmp_path / "runs", include_memory=False)

    assert summary.health.ok is True
    assert summary.commands == []
    assert summary.jobs == []
    assert summary.repo_status.status == "artifact_missing"


def test_dashboard_collects_known_artifacts(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_json(runs / "local_agent" / "commands" / "cmd1" / "result.json", {"run_id": "cmd1", "command_id": "git_status", "status": "success", "created_at": "2026-01-01T00:00:00Z", "argv": ["git", "status"], "exit_code": 0})
    write_json(runs / "jobs" / "job1" / "result.json", {"job_id": "job1", "status": "completed", "job_profile": "dummy_success", "created_at": "2026-01-02T00:00:00Z"})
    write_json(runs / "supervisors" / "sup1" / "result.json", {"supervisor_id": "sup1", "status": "completed", "objective": "inspect", "created_at": "2026-01-03T00:00:00Z", "codex_invoked": False})
    write_json(runs / "approvals" / "approval1.json", {"approval_request_id": "approval1", "status": "pending", "required_approver": "chatgpt", "action_type": "local_coding_apply", "created_at": "2026-01-04T00:00:00Z"})
    write_json(runs / "codex_escalations" / "codex1" / "packet.json", {"escalation_id": "codex1", "objective": "fix failing test", "created_at": "2026-01-05T00:00:00Z"})
    write_json(runs / "jobs" / "job1" / "pulse_manifest.json", {"artifact_id": "job1", "status": "ready", "ready": True, "delivered": False, "created_at": "2026-01-06T00:00:00Z", "updated_at": "2026-01-06T00:00:00Z"})
    write_json(runs / "jobs" / "job1" / "pulse_delivery_ack.json", {"ack": True})
    write_json(runs / "local_coding" / "edit1" / "proposal.json", {"edit_id": "edit1", "status": "approval_required", "objective": "fix typo in README", "target_file": "README.md", "created_at": "2026-01-07T00:00:00Z"})

    summary = get_dashboard_summary(runs, include_memory=False)

    assert summary.commands[0].id == "cmd1"
    assert summary.jobs[0].id == "job1"
    assert summary.supervisors[0].id == "sup1"
    assert summary.approvals[0].id == "approval1"
    assert summary.codex_escalations[0].id == "codex1"
    assert summary.return_loop[0].readiness == "acknowledged"
    assert summary.local_coding[0].id == "edit1"
    assert summary.repo_status.latest_git_status_artifact is not None


def test_dashboard_collects_current_root_runs_without_result_json(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    run_id = "20260512T181658Z_codex_plan_task_660e6d2c"
    write_json(
        runs / run_id / "input.json",
        {
            "repo_name": "stream_alpha",
            "task": "Read-only project salvage assessment",
        },
    )
    write_jsonl(
        runs / run_id / "events.jsonl",
        [
            {"stage": "queued", "timestamp": "2026-05-12T18:16:58+00:00", "message": "Run queued"},
            {"stage": "codex", "timestamp": "2026-05-12T18:16:59+00:00", "message": "Codex process spawned"},
        ],
    )

    summary = get_dashboard_summary(runs, include_memory=False)

    assert summary.runs[0].id == run_id
    assert summary.runs[0].status == "running"
    assert summary.runs[0].repo_name == "stream_alpha"
    assert summary.runs[0].summary == "Read-only project salvage assessment"
    assert summary.runs[0].artifact_path == runs / run_id / "input.json"


def test_dashboard_malformed_large_sensitive_and_limit_handling(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_json(runs / "local_agent" / "commands" / "cmd1" / "result.json", {"run_id": "cmd1", "command_id": "pytest", "status": "failed", "error": "password=abc123", "created_at": "2026-01-01T00:00:00Z"})
    (runs / "jobs" / "bad").mkdir(parents=True)
    (runs / "jobs" / "bad" / "result.json").write_text("{bad", encoding="utf-8")
    write_json(runs / "jobs" / "huge" / "result.json", {"blob": "x" * 1000})
    write_json(runs / "jobs" / "job1" / "result.json", {"job_id": "job1", "status": "completed", "created_at": "2026-01-02T00:00:00Z"})
    write_json(runs / "jobs" / "job2" / "result.json", {"job_id": "job2", "status": "completed", "created_at": "2026-01-03T00:00:00Z"})

    summary = get_dashboard_summary(runs, limit=1, max_file_bytes=300, include_memory=False)

    assert len(summary.jobs) == 1
    assert "malformed_json" in " ".join(summary.health.errors)
    assert "skipped_large_artifact" in " ".join(summary.health.errors)
    assert "abc123" not in summary.commands[0].error
    assert "[REDACTED]" in summary.commands[0].error


def test_dashboard_memory_overview_with_temporary_store(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    repository = ProjectMemoryRepository(db_path=runs / "memory" / "project_memory.sqlite3")
    repository.remember_project_fact("Validation recipe lives in README", repo_name="repo")

    summary = get_dashboard_summary(runs, memory_repository=repository)

    assert summary.memory.total_records >= 1
    assert summary.memory.recent[0].source_kind == "memory"


def test_dashboard_collectors_stay_under_runs_dir(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    outside = tmp_path / "outside"
    write_json(outside / "result.json", {"run_id": "outside"})
    write_json(runs / "jobs" / "job1" / "result.json", {"job_id": "job1", "status": "completed"})

    summary = get_dashboard_summary(runs, include_memory=False)

    assert [job.id for job in summary.jobs] == ["job1"]
