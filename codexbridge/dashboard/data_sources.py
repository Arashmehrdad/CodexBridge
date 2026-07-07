from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from codexbridge.memory.repository import ProjectMemoryRepository
from codexbridge.memory.redaction import detect_sensitivity, redact_sensitive_text

from .models import (
    DashboardApprovalSummary,
    DashboardCodexEscalationSummary,
    DashboardCommandSummary,
    DashboardHealthResult,
    DashboardItem,
    DashboardJobSummary,
    DashboardLocalCodingSummary,
    DashboardMemorySummary,
    DashboardRepoStatusSummary,
    DashboardReturnLoopSummary,
    DashboardRunSummary,
    DashboardSummary,
    DashboardSupervisorSummary,
)

T = TypeVar("T", bound=DashboardItem)


def get_dashboard_summary(
    runs_dir: Path,
    *,
    limit: int = 50,
    max_file_bytes: int = 200000,
    include_memory: bool = True,
    include_repo_status: bool = True,
    memory_repository: ProjectMemoryRepository | None = None,
) -> DashboardSummary:
    runs_dir = Path(runs_dir).resolve()
    errors: list[str] = []
    summary = DashboardSummary(
        health=DashboardHealthResult(ok=True, read_only=True, runs_dir=runs_dir),
        runs=_bounded(
            _collect_root_runs(runs_dir, limit, max_file_bytes, errors), limit
        ),
        commands=_bounded(
            _collect_commands(runs_dir, limit, max_file_bytes, errors), limit
        ),
        jobs=_bounded(_collect_jobs(runs_dir, limit, max_file_bytes, errors), limit),
        supervisors=_bounded(
            _collect_supervisors(runs_dir, limit, max_file_bytes, errors), limit
        ),
        approvals=_bounded(
            _collect_approvals(runs_dir, limit, max_file_bytes, errors), limit
        ),
        codex_escalations=_bounded(
            _collect_codex_escalations(runs_dir, limit, max_file_bytes, errors), limit
        ),
        return_loop=_bounded(
            _collect_return_loop(runs_dir, limit, max_file_bytes, errors), limit
        ),
        local_coding=_bounded(
            _collect_local_coding(runs_dir, limit, max_file_bytes, errors), limit
        ),
        memory=_collect_memory(runs_dir, limit, memory_repository, errors)
        if include_memory
        else DashboardMemorySummary(),
        repo_status=_collect_repo_status(runs_dir, limit, max_file_bytes, errors)
        if include_repo_status
        else DashboardRepoStatusSummary(status="disabled"),
    )
    summary.health.errors = errors
    summary.health.ok = not errors
    return summary


def _collect_root_runs(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> list[DashboardRunSummary]:
    items = []
    seen_run_dirs: set[Path] = set()
    for path in _safe_glob(runs_dir, "*/result.json", limit, max_file_bytes, errors):
        if any(
            part
            in {
                "jobs",
                "supervisors",
                "local_agent",
                "local_coding",
                "codex_escalations",
            }
            for part in path.relative_to(runs_dir).parts
        ):
            continue
        data = _read_json(path, runs_dir, max_file_bytes, errors)
        if data is None:
            continue
        seen_run_dirs.add(path.parent.resolve())
        items.append(
            DashboardRunSummary(
                id=str(data.get("run_id") or path.parent.name),
                status=str(data.get("status") or ""),
                created_at=str(data.get("created_at") or path.parent.name),
                updated_at=str(data.get("updated_at") or ""),
                ended_at=str(data.get("ended_at") or ""),
                repo_name=data.get("repo_name"),
                repo_path=_path_or_none(data.get("repo_path")),
                artifact_path=path,
                summary=_safe_text(
                    str(data.get("summary") or data.get("objective") or "")
                ),
                error=_safe_text(str(data.get("error") or "")),
            )
        )
    for path in _safe_glob(runs_dir, "*/input.json", limit, max_file_bytes, errors):
        if any(
            part
            in {
                "jobs",
                "supervisors",
                "local_agent",
                "local_coding",
                "codex_escalations",
            }
            for part in path.relative_to(runs_dir).parts
        ):
            continue
        if path.parent.resolve() in seen_run_dirs:
            continue
        data = _read_json(path, runs_dir, max_file_bytes, errors)
        if data is None:
            continue
        events_path = path.parent / "events.jsonl"
        events = (
            _read_jsonl(events_path, runs_dir, max_file_bytes, errors)
            if events_path.exists()
            else []
        )
        last_event = events[-1] if events else {}
        started_at = str(
            (events[0] if events else {}).get("timestamp") or path.parent.name
        )
        updated_at = str(last_event.get("timestamp") or "")
        stage = str(last_event.get("stage") or "")
        status = "running" if stage in {"worker", "codex"} else (stage or "queued")
        items.append(
            DashboardRunSummary(
                id=path.parent.name,
                status=status,
                created_at=started_at,
                updated_at=updated_at,
                repo_name=data.get("repo_name"),
                artifact_path=path,
                summary=_safe_text(
                    str(data.get("task") or data.get("objective") or "")
                ),
                error="",
            )
        )
    return _sort_items(items)


def _collect_commands(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> list[DashboardCommandSummary]:
    items = []
    for path in _safe_glob(
        runs_dir / "local_agent" / "commands",
        "*/result.json",
        limit,
        max_file_bytes,
        errors,
    ):
        data = _read_json(path, runs_dir, max_file_bytes, errors)
        if data is None:
            continue
        items.append(
            DashboardCommandSummary(
                id=str(data.get("run_id") or path.parent.name),
                command_id=str(data.get("command_id") or ""),
                status=str(data.get("status") or ""),
                created_at=str(data.get("created_at") or ""),
                repo_name=data.get("repo_name"),
                repo_path=_path_or_none(data.get("repo_path")),
                artifact_path=path,
                summary=_safe_text(" ".join(data.get("argv") or [])),
                error=_safe_text(str(data.get("error") or "")),
                exit_code=data.get("exit_code"),
            )
        )
    return _sort_items(items)


def _collect_jobs(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> list[DashboardJobSummary]:
    items = []
    for path in _safe_glob(
        runs_dir / "jobs", "*/result.json", limit, max_file_bytes, errors
    ):
        data = _read_json(path, runs_dir, max_file_bytes, errors)
        if data is None:
            continue
        job = data.get("job") if isinstance(data.get("job"), dict) else data
        items.append(
            DashboardJobSummary(
                id=str(job.get("job_id") or path.parent.name),
                status=str(job.get("status") or ""),
                created_at=str(job.get("created_at") or ""),
                updated_at=str(job.get("updated_at") or ""),
                ended_at=str(job.get("ended_at") or ""),
                repo_name=job.get("repo_name"),
                repo_path=_path_or_none(job.get("repo_path")),
                artifact_path=path,
                summary=_safe_text(
                    str(job.get("summary") or job.get("job_profile") or "")
                ),
                failure_summary=_safe_text(str(job.get("failure_summary") or "")),
                next_recommended_action=_safe_text(
                    str(job.get("next_recommended_action") or "")
                ),
                job_profile=str(job.get("job_profile") or job.get("profile_id") or ""),
            )
        )
    return _sort_items(items)


def _collect_supervisors(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> list[DashboardSupervisorSummary]:
    items = []
    for path in _safe_glob(
        runs_dir / "supervisors", "*/result.json", limit, max_file_bytes, errors
    ):
        data = _read_json(path, runs_dir, max_file_bytes, errors)
        if data is None:
            continue
        items.append(
            DashboardSupervisorSummary(
                id=str(data.get("supervisor_id") or path.parent.name),
                status=str(data.get("status") or ""),
                created_at=str(data.get("created_at") or ""),
                updated_at=str(data.get("updated_at") or ""),
                ended_at=str(data.get("ended_at") or ""),
                repo_name=data.get("repo_name"),
                repo_path=_path_or_none(data.get("repo_path")),
                artifact_path=path,
                summary=_safe_text(
                    str(
                        data.get("local_plan_summary")
                        or data.get("local_inspection_summary")
                        or data.get("objective")
                        or ""
                    )
                ),
                failure_summary=_safe_text(str(data.get("failure_summary") or "")),
                next_recommended_action=_safe_text(
                    str(data.get("next_recommended_action") or "")
                ),
                codex_invoked=bool(data.get("codex_invoked")),
                codex_packet_path=_path_or_none(data.get("codex_packet_path")),
            )
        )
    return _sort_items(items)


def _collect_approvals(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> list[DashboardApprovalSummary]:
    items = []
    for path in _safe_glob(
        runs_dir / "approvals", "*.json", limit, max_file_bytes, errors
    ):
        data = _read_json(path, runs_dir, max_file_bytes, errors)
        if data is None:
            continue
        items.append(
            DashboardApprovalSummary(
                id=str(data.get("approval_request_id") or path.stem),
                status=str(data.get("status") or ""),
                created_at=str(data.get("created_at") or ""),
                updated_at=str(data.get("decided_at") or ""),
                repo_name=data.get("repo_name"),
                repo_path=_path_or_none(data.get("repo_path")),
                artifact_path=path,
                summary=_safe_text("; ".join(data.get("reasons") or [])),
                required_approver=str(data.get("required_approver") or ""),
                action_type=str(data.get("action_type") or ""),
            )
        )
    return _sort_items(items)


def _collect_codex_escalations(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> list[DashboardCodexEscalationSummary]:
    items = []
    for path in _safe_glob(
        runs_dir / "codex_escalations", "*/packet.json", limit, max_file_bytes, errors
    ):
        data = _read_json(path, runs_dir, max_file_bytes, errors)
        if data is None:
            continue
        result_path = path.parent / "codex_result.json"
        invocation_path = path.parent / "codex_invocation.json"
        items.append(
            DashboardCodexEscalationSummary(
                id=str(data.get("escalation_id") or path.parent.name),
                status="invoked"
                if result_path.exists() or invocation_path.exists()
                else "packet_ready",
                created_at=str(data.get("created_at") or ""),
                repo_name=data.get("repo_name"),
                repo_path=_path_or_none(data.get("repo_path")),
                artifact_path=path,
                summary=_safe_text(str(data.get("objective") or "")),
                packet_path=path,
                codex_invoked=result_path.exists() or invocation_path.exists(),
            )
        )
    return _sort_items(items)


def _collect_return_loop(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> list[DashboardReturnLoopSummary]:
    items = []
    for root in (runs_dir / "jobs", runs_dir / "supervisors"):
        for path in _safe_glob(
            root, "*/pulse_manifest.json", limit, max_file_bytes, errors
        ):
            data = _read_json(path, runs_dir, max_file_bytes, errors)
            if data is None:
                continue
            ack_path = path.parent / "pulse_delivery_ack.json"
            items.append(
                DashboardReturnLoopSummary(
                    id=str(data.get("artifact_id") or path.parent.name),
                    status=str(data.get("status") or ""),
                    created_at=str(data.get("created_at") or ""),
                    updated_at=str(data.get("updated_at") or ""),
                    artifact_path=path,
                    summary=_safe_text(str(data.get("recommended_next_action") or "")),
                    readiness="acknowledged"
                    if ack_path.exists()
                    else ("ready" if data.get("ready") else "not_ready"),
                    blocked_reason=_safe_text(str(data.get("blocked_reason") or "")),
                    ready=bool(data.get("ready")),
                    delivered=bool(data.get("delivered")) or ack_path.exists(),
                )
            )
    return _sort_items(items)


def _collect_local_coding(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> list[DashboardLocalCodingSummary]:
    items = []
    for path in _safe_glob(
        runs_dir / "local_coding", "*/proposal.json", limit, max_file_bytes, errors
    ):
        data = _read_json(path, runs_dir, max_file_bytes, errors)
        if data is None:
            continue
        apply_path = path.parent / "apply_result.json"
        rollback_path = path.parent / "rollback_result.json"
        status = str(data.get("status") or "")
        if rollback_path.exists():
            status = "rolled_back"
        elif apply_path.exists():
            apply_data = _read_json(apply_path, runs_dir, max_file_bytes, errors) or {}
            status = str(apply_data.get("status") or "applied")
        items.append(
            DashboardLocalCodingSummary(
                id=str(data.get("edit_id") or path.parent.name),
                status=status,
                created_at=str(data.get("created_at") or ""),
                repo_name=data.get("repo_name"),
                repo_path=_path_or_none(data.get("repo_path")),
                artifact_path=path,
                summary=_safe_text(str(data.get("objective") or "")),
                target_file=_path_or_none(data.get("target_file")),
                approval_request_id=data.get("approval_request_id"),
            )
        )
    return _sort_items(items)


def _collect_memory(
    runs_dir: Path,
    limit: int,
    memory_repository: ProjectMemoryRepository | None,
    errors: list[str],
) -> DashboardMemorySummary:
    try:
        repository = memory_repository or ProjectMemoryRepository(
            db_path=runs_dir / "memory" / "project_memory.sqlite3"
        )
        records = repository.store.recent(limit=limit)
        return DashboardMemorySummary(
            total_records=len(repository.store.recent(limit=500)),
            recent=[
                DashboardItem(
                    id=record.memory_id,
                    source_kind="memory",
                    status="archived" if record.archived else "active",
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    repo_name=record.repo_name,
                    repo_path=record.repo_path,
                    artifact_path=record.source_path,
                    summary=_safe_text(record.summary),
                )
                for record in records
            ],
        )
    except Exception as exc:
        errors.append(f"memory: {exc}")
        return DashboardMemorySummary(error=str(exc))


def _collect_repo_status(
    runs_dir: Path, limit: int, max_file_bytes: int, errors: list[str]
) -> DashboardRepoStatusSummary:
    commands = _collect_commands(runs_dir, limit, max_file_bytes, errors)
    for command in commands:
        if command.command_id == "git_status":
            return DashboardRepoStatusSummary(
                latest_git_status_artifact=command.artifact_path,
                summary=command.summary,
                status=command.status,
            )
    return DashboardRepoStatusSummary(
        status="artifact_missing", summary="No existing git_status artifact found."
    )


def _safe_glob(
    root: Path, pattern: str, limit: int, max_file_bytes: int, errors: list[str]
) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    paths = []
    for path in root.glob(pattern):
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        if path.is_file() and path.stat().st_size <= max_file_bytes:
            paths.append(path)
        elif path.is_file():
            errors.append(f"skipped_large_artifact:{path}")
    paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return paths[: max(1, min(limit * 5, 500))]


def _read_json(
    path: Path, runs_dir: Path, max_file_bytes: int, errors: list[str]
) -> dict[str, Any] | None:
    try:
        path.resolve().relative_to(runs_dir.resolve())
    except ValueError:
        return None
    try:
        if path.stat().st_size > max_file_bytes:
            errors.append(f"skipped_large_artifact:{path}")
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_json:{path}:{exc}")
        return None


def _read_jsonl(
    path: Path, runs_dir: Path, max_file_bytes: int, errors: list[str]
) -> list[dict[str, Any]]:
    try:
        path.resolve().relative_to(runs_dir.resolve())
    except ValueError:
        return []
    try:
        if path.stat().st_size > max_file_bytes:
            errors.append(f"skipped_large_artifact:{path}")
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records
    except Exception as exc:
        errors.append(f"malformed_jsonl:{path}:{exc}")
        return []


def _sort_items(items: list[T]) -> list[T]:
    return sorted(
        items,
        key=lambda item: item.updated_at or item.ended_at or item.created_at or item.id,
        reverse=True,
    )


def _bounded(items: list[T], limit: int) -> list[T]:
    return items[: max(1, min(limit, 500))]


def _safe_text(text: str, max_chars: int = 500) -> str:
    if detect_sensitivity(text):
        text = redact_sensitive_text(text)
    return text[:max_chars]


def _path_or_none(value: Any) -> Path | None:
    if not value:
        return None
    return Path(str(value))
