from __future__ import annotations

import json
from pathlib import Path

from codexbridge.memory.importers import (
    import_agents_md,
    import_command_result,
    import_job_result,
    import_pulse_manifest,
    import_runs,
)
from codexbridge.memory.repository import ProjectMemoryRepository
from codexbridge.return_loop.pulse_contract import build_report_manifest


def repo(tmp_path: Path) -> ProjectMemoryRepository:
    return ProjectMemoryRepository(
        db_path=tmp_path / "runs" / "memory" / "project_memory.sqlite3"
    )


def test_command_result_importer_stores_concise_artifact_memory(tmp_path: Path) -> None:
    result_dir = tmp_path / "runs" / "local_agent" / "commands" / "run1"
    result_dir.mkdir(parents=True)
    result_path = result_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "run_id": "run1",
                "command_id": "pytest",
                "status": "success",
                "exit_code": 0,
                "duration_seconds": 1.0,
                "stdout_path": str(result_dir / "stdout.txt"),
                "stderr_path": str(result_dir / "stderr.txt"),
                "result_path": str(result_path),
            }
        ),
        encoding="utf-8",
    )

    imported = import_command_result(repo(tmp_path), result_path)

    assert imported.imported == 1


def test_job_result_importer_stores_job_memory_with_paths_and_status(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / "runs" / "jobs" / "job1"
    job_dir.mkdir(parents=True)
    result_path = job_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "job_id": "job1",
                "job_profile": "dummy_success",
                "status": "completed",
                "exit_code": 0,
                "duration_seconds": 2,
                "failure_summary": "",
                "next_recommended_action": "review",
                "artifact_paths": [],
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "job_report.md").write_text("report", encoding="utf-8")
    (job_dir / "resume_prompt.txt").write_text("resume", encoding="utf-8")

    memory_repo = repo(tmp_path)
    imported = import_job_result(memory_repo, result_path)
    latest = memory_repo.latest_job_summary()

    assert imported.imported == 1
    assert latest is not None
    assert latest.metadata["job_id"] == "job1"
    assert latest.metadata["status"] == "completed"


def test_pulse_manifest_importer_stores_artifact_memory_without_sending(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / "runs" / "jobs" / "job2"
    job_dir.mkdir(parents=True)
    (job_dir / "resume_prompt.txt").write_text("resume", encoding="utf-8")
    (job_dir / "job_report.md").write_text("report", encoding="utf-8")
    (job_dir / "result.json").write_text("{}", encoding="utf-8")
    build_report_manifest(
        artifact_type="combined",
        artifact_id="job2",
        source_kind="job",
        source_status="completed",
        report_path=job_dir / "job_report.md",
        resume_prompt_path=job_dir / "resume_prompt.txt",
        result_json_path=job_dir / "result.json",
    )

    memory_repo = repo(tmp_path)
    imported = import_pulse_manifest(memory_repo, job_dir / "pulse_manifest.json")
    record = memory_repo.store.list_records()[0]

    assert imported.imported == 1
    assert record.source_kind == "pulse_manifest"
    assert record.metadata["ready"] is True


def test_agents_md_importer_is_explicit_only(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Rules\nUse minimal edits.", encoding="utf-8")

    imported = import_agents_md(repo(tmp_path), agents)

    assert imported.imported == 1


def test_import_runs_deduplicates_and_bounds_files(tmp_path: Path) -> None:
    result_dir = tmp_path / "runs" / "local_agent" / "commands" / "run1"
    result_dir.mkdir(parents=True)
    result_path = result_dir / "result.json"
    result_path.write_text(
        json.dumps({"run_id": "run1", "command_id": "pytest", "status": "success"}),
        encoding="utf-8",
    )
    memory_repo = repo(tmp_path)

    first = import_runs(memory_repo, tmp_path / "runs")
    second = import_runs(memory_repo, tmp_path / "runs")

    assert first.imported == 1
    assert second.skipped_duplicate >= 1
