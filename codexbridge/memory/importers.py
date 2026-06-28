from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from codexbridge.return_loop.pulse_contract import discover_ready_reports

from .models import MemoryRecord, MemoryType
from .repository import ProjectMemoryRepository
from .redaction import detect_sensitivity


class ImportResult(BaseModel):
    imported: int = 0
    skipped_duplicate: int = 0
    skipped_sensitive: int = 0
    skipped_missing: int = 0
    memory_ids: list[str] = Field(default_factory=list)


def import_command_result(
    repo: ProjectMemoryRepository, result_json_path: Path
) -> ImportResult:
    path = Path(result_json_path)
    if not path.exists():
        return ImportResult(skipped_missing=1)
    data = _read_json(path)
    summary = f"Command {data.get('command_id', '')} finished with status {data.get('status', '')}"
    content = "\n".join(
        [
            summary,
            f"exit_code: {data.get('exit_code')}",
            f"duration_seconds: {data.get('duration_seconds')}",
            f"stdout_path: {data.get('stdout_path')}",
            f"stderr_path: {data.get('stderr_path')}",
        ]
    )
    return _create_safe(
        repo,
        MemoryRecord(
            memory_type=MemoryType.RUN,
            title=summary,
            summary=summary,
            content=content,
            tags=["command_result", "run_memory"],
            source_kind="command_result",
            source_id=str(data.get("run_id") or path),
            source_path=path,
            artifact_paths=_paths(
                [
                    data.get("stdout_path"),
                    data.get("stderr_path"),
                    data.get("result_path"),
                ]
            ),
            metadata={
                key: data.get(key)
                for key in (
                    "run_id",
                    "command_id",
                    "status",
                    "exit_code",
                    "duration_seconds",
                )
            },
        ),
    )


def import_job_result(
    repo: ProjectMemoryRepository, result_json_path: Path
) -> ImportResult:
    path = Path(result_json_path)
    if not path.exists():
        return ImportResult(skipped_missing=1)
    data = _read_json(path)
    job_id = str(data.get("job_id") or path.parent.name)
    report_path = path.parent / "job_report.md"
    resume_path = path.parent / "resume_prompt.txt"
    manifest_path = path.parent / "pulse_manifest.json"
    summary = f"Job {job_id} profile {data.get('job_profile', '')} finished with status {data.get('status', '')}"
    content = "\n".join(
        [
            summary,
            f"exit_code: {data.get('exit_code')}",
            f"duration_seconds: {data.get('duration_seconds')}",
            f"failure_summary: {data.get('failure_summary', '')}",
            f"recommended_next_action: {data.get('next_recommended_action', '')}",
        ]
    )
    return _create_safe(
        repo,
        MemoryRecord(
            memory_type=MemoryType.JOB,
            repo_name=data.get("repo_name"),
            repo_path=Path(data["repo_path"]) if data.get("repo_path") else None,
            title=summary,
            summary=summary,
            content=content,
            tags=["job_memory", "job_result"],
            source_kind="job_result",
            source_id=job_id,
            source_path=path,
            artifact_paths=[
                item
                for item in [
                    path,
                    report_path,
                    resume_path,
                    manifest_path,
                    *_paths(data.get("artifact_paths", [])),
                ]
                if item.exists()
            ],
            metadata={
                "job_id": job_id,
                "job_profile": data.get("job_profile"),
                "status": data.get("status"),
                "exit_code": data.get("exit_code"),
                "duration_seconds": data.get("duration_seconds"),
                "metrics_summary": data.get("metrics_summary", {}),
                "question_for_chatgpt": _manifest_question(manifest_path),
            },
        ),
    )


def import_pulse_manifest(
    repo: ProjectMemoryRepository, manifest_path: Path
) -> ImportResult:
    path = Path(manifest_path)
    if not path.exists():
        return ImportResult(skipped_missing=1)
    data = _read_json(path)
    summary = f"Return-loop manifest {data.get('artifact_id', path.parent.name)} is {data.get('status', '')}"
    return _create_safe(
        repo,
        MemoryRecord(
            memory_type=MemoryType.ARTIFACT,
            title=summary,
            summary=summary,
            content=f"recommended_next_action: {data.get('recommended_next_action', '')}\nquestion_for_chatgpt: {data.get('question_for_chatgpt', '')}",
            tags=["return_loop", "artifact_memory"],
            source_kind="pulse_manifest",
            source_id=str(data.get("artifact_id") or path),
            source_path=path,
            artifact_paths=_paths(
                [
                    data.get("report_path"),
                    data.get("resume_prompt_path"),
                    data.get("result_json_path"),
                ]
            ),
            metadata={
                key: data.get(key)
                for key in (
                    "artifact_id",
                    "status",
                    "ready",
                    "source_kind",
                    "source_status",
                )
            },
        ),
    )


def import_agents_md(repo: ProjectMemoryRepository, agents_path: Path) -> ImportResult:
    path = Path(agents_path)
    if not path.exists():
        return ImportResult(skipped_missing=1)
    text = path.read_text(encoding="utf-8")
    return _create_safe(
        repo,
        MemoryRecord(
            memory_type=MemoryType.STATIC,
            title="AGENTS.md project rules",
            summary="Persistent project instructions from AGENTS.md",
            content=text,
            tags=["project_rules", "static_memory"],
            source_kind="agents_md",
            source_id=str(path.resolve()),
            source_path=path,
            artifact_paths=[path],
        ),
    )


def import_runs(
    repo: ProjectMemoryRepository, runs_dir: Path, *, max_files: int = 200
) -> ImportResult:
    result = ImportResult()
    files = list((Path(runs_dir) / "local_agent" / "commands").glob("*/result.json"))[
        :max_files
    ]
    files += list((Path(runs_dir) / "jobs").glob("*/result.json"))[:max_files]
    for manifest in discover_ready_reports(Path(runs_dir))[:max_files]:
        files.append(manifest.resume_prompt_path.parent / "pulse_manifest.json")
    for path in files[:max_files]:
        if path.name == "pulse_manifest.json":
            imported = import_pulse_manifest(repo, path)
        elif "\\jobs\\" in str(path) or "/jobs/" in str(path):
            imported = import_job_result(repo, path)
        else:
            imported = import_command_result(repo, path)
        result.imported += imported.imported
        result.skipped_duplicate += imported.skipped_duplicate
        result.skipped_sensitive += imported.skipped_sensitive
        result.skipped_missing += imported.skipped_missing
        result.memory_ids.extend(imported.memory_ids)
    return result


def _create_safe(repo: ProjectMemoryRepository, record: MemoryRecord) -> ImportResult:
    if detect_sensitivity("\n".join([record.title, record.summary, record.content])):
        return ImportResult(skipped_sensitive=1)
    before = {
        item.memory_id
        for item in repo.store.list_records(include_archived=True, limit=500)
    }
    created = repo.store.create(record)
    if created.memory_id in before:
        return ImportResult(skipped_duplicate=1, memory_ids=[created.memory_id])
    return ImportResult(imported=1, memory_ids=[created.memory_id])


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _paths(values) -> list[Path]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [Path(value) for value in values if value]


def _manifest_question(manifest_path: Path) -> str:
    if not manifest_path.exists():
        return ""
    try:
        return str(_read_json(manifest_path).get("question_for_chatgpt", ""))
    except Exception:
        return ""
