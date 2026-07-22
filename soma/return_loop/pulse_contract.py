from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from soma.config import ReturnLoopConfig
from soma.run_store import utc_now

from .atomic_writer import atomic_write_json
from .models import ReportManifest, ReportReadinessResult, ReturnLoopStatus
from .report_manifest import (
    file_sha256,
    file_size,
    read_stable_bytes,
    sensitivity_flags_for_text,
    sha256_bytes,
)

READY_SOURCE_STATUSES = {
    "completed",
    "failed",
    "timeout",
    "cancelled",
    "needs_input",
    "needs_approval",
    "reported",
    "blocked",
    "approval_required",
    "codex_packet_ready",
}


def _read_existing_manifest(manifest_path: Path) -> ReportManifest | None:
    if not manifest_path.exists() or not manifest_path.is_file():
        return None
    try:
        return ReportManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None


def build_job_report_manifest(
    *,
    job_id: str,
    source_status: str,
    report_path: Path,
    resume_prompt_path: Path,
    result_json_path: Path,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    artifact_paths: list[Path] | None = None,
    recommended_next_action: str = "",
    question_for_chatgpt: str = "",
    config: ReturnLoopConfig | None = None,
) -> ReportManifest:
    return build_report_manifest(
        artifact_type="combined",
        artifact_id=job_id,
        source_kind="job",
        source_status=source_status,
        report_path=report_path,
        resume_prompt_path=resume_prompt_path,
        result_json_path=result_json_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        artifact_paths=artifact_paths or [],
        recommended_next_action=recommended_next_action,
        question_for_chatgpt=question_for_chatgpt,
        config=config,
    )


def build_report_manifest(
    *,
    artifact_type: str,
    artifact_id: str,
    source_kind: str,
    source_status: str,
    report_path: Path,
    resume_prompt_path: Path,
    result_json_path: Path,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    artifact_paths: list[Path] | None = None,
    recommended_next_action: str = "",
    question_for_chatgpt: str = "",
    config: ReturnLoopConfig | None = None,
) -> ReportManifest:
    settings = config or ReturnLoopConfig()
    now = utc_now()
    manifest_path = resume_prompt_path.parent / "pulse_manifest.json"
    existing_manifest = _read_existing_manifest(manifest_path)
    status, blocked_reason, sensitivity_flags, hashes, sizes = _evaluate_files(
        report_path=report_path,
        resume_prompt_path=resume_prompt_path,
        result_json_path=result_json_path,
        source_status=source_status,
        settings=settings,
    )
    manifest = ReportManifest(
        schema_version=settings.manifest_schema_version,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        conversation_target=settings.conversation_target,
        status=status,
        ready=status == ReturnLoopStatus.READY,
        delivered=False,
        created_at=now,
        updated_at=now,
        report_path=report_path,
        resume_prompt_path=resume_prompt_path,
        result_json_path=result_json_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        artifact_paths=artifact_paths or [],
        content_sha256=hashes.get("content", ""),
        report_sha256=hashes.get("report", ""),
        result_sha256=hashes.get("result", ""),
        content_bytes=sizes.get("content", 0),
        report_bytes=sizes.get("report", 0),
        result_bytes=sizes.get("result", 0),
        max_content_bytes=settings.max_resume_prompt_bytes,
        max_report_bytes=settings.max_report_bytes,
        sensitivity_flags=sensitivity_flags,
        blocked_reason=blocked_reason,
        recommended_next_action=recommended_next_action,
        question_for_chatgpt=question_for_chatgpt,
        source_kind=source_kind,
        source_status=source_status,
        send_policy="external_pulsesender_only",
        audit_event_id=f"return_loop_{uuid4().hex}",
    )
    if existing_manifest is not None and (
        existing_manifest.delivered
        or existing_manifest.status
        == ReturnLoopStatus.SENT_BY_EXTERNAL_PULSESENDER
    ):
        manifest.status = ReturnLoopStatus.SENT_BY_EXTERNAL_PULSESENDER
        manifest.ready = False
        manifest.delivered = True
        manifest.created_at = existing_manifest.created_at
        manifest.sent_at = existing_manifest.sent_at
        manifest.sender_id = existing_manifest.sender_id
        manifest.delivery_hash = existing_manifest.delivery_hash
        manifest.audit_event_id = (
            existing_manifest.audit_event_id or manifest.audit_event_id
        )
    atomic_write_json(manifest_path, manifest.to_dict())
    return manifest


def check_report_readiness(
    manifest_path: Path, *, config: ReturnLoopConfig | None = None
) -> ReportReadinessResult:
    if not manifest_path.exists():
        return ReportReadinessResult(
            manifest_path=manifest_path,
            status=ReturnLoopStatus.INVALID,
            ready=False,
            blocked_reason="Manifest is missing.",
        )
    manifest = ReportManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if (
        manifest.status == ReturnLoopStatus.SENT_BY_EXTERNAL_PULSESENDER
        or manifest.delivered
    ):
        return ReportReadinessResult(
            manifest_path=manifest_path,
            status=manifest.status,
            ready=False,
            blocked_reason="Already delivered.",
            manifest=manifest,
        )
    settings = config or ReturnLoopConfig(
        max_resume_prompt_bytes=manifest.max_content_bytes,
        max_report_bytes=manifest.max_report_bytes,
    )
    status, blocked_reason, sensitivity_flags, hashes, sizes = _evaluate_files(
        report_path=manifest.report_path,
        resume_prompt_path=manifest.resume_prompt_path,
        result_json_path=manifest.result_json_path,
        source_status=manifest.source_status,
        settings=settings,
    )
    manifest.status = status
    manifest.ready = status == ReturnLoopStatus.READY
    manifest.updated_at = utc_now()
    manifest.blocked_reason = blocked_reason
    manifest.sensitivity_flags = sensitivity_flags
    manifest.content_sha256 = hashes.get("content", "")
    manifest.report_sha256 = hashes.get("report", "")
    manifest.result_sha256 = hashes.get("result", "")
    manifest.content_bytes = sizes.get("content", 0)
    manifest.report_bytes = sizes.get("report", 0)
    manifest.result_bytes = sizes.get("result", 0)
    atomic_write_json(manifest_path, manifest.to_dict())
    return ReportReadinessResult(
        manifest_path=manifest_path,
        status=status,
        ready=manifest.ready,
        blocked_reason=blocked_reason,
        sensitivity_flags=sensitivity_flags,
        manifest=manifest,
    )


def mark_sent_by_external_pulsesender(
    manifest_path: Path,
    sent_at: str,
    *,
    sender_id: str | None = None,
    delivery_hash: str | None = None,
) -> ReportManifest:
    manifest = ReportManifest.model_validate_json(
        Path(manifest_path).read_text(encoding="utf-8")
    )
    manifest.status = ReturnLoopStatus.SENT_BY_EXTERNAL_PULSESENDER
    manifest.ready = False
    manifest.delivered = True
    manifest.sent_at = sent_at
    manifest.sender_id = sender_id
    manifest.delivery_hash = delivery_hash
    manifest.updated_at = utc_now()
    atomic_write_json(Path(manifest_path), manifest.to_dict())
    return manifest


def discover_ready_reports(runs_dir: Path) -> list[ReportManifest]:
    runs_dir = Path(runs_dir)
    manifests: list[ReportManifest] = []
    for root in (runs_dir / "jobs", runs_dir / "supervisors", runs_dir / "workflows"):
        if not root.exists():
            continue
        for manifest_path in root.glob("*/pulse_manifest.json"):
            manifest = ReportManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            if (
                manifest.ready
                and manifest.status == ReturnLoopStatus.READY
                and not manifest.delivered
            ):
                manifests.append(manifest)
    manifests.sort(key=lambda item: (item.created_at, item.artifact_id))
    return manifests


def _evaluate_files(
    *,
    report_path: Path | None,
    resume_prompt_path: Path | None,
    result_json_path: Path | None,
    source_status: str,
    settings: ReturnLoopConfig,
) -> tuple[ReturnLoopStatus, str, list[str], dict[str, str], dict[str, int]]:
    required = [
        ("resume prompt", resume_prompt_path),
        ("report", report_path),
        ("result json", result_json_path),
    ]
    missing = [name for name, path in required if path is None or not path.exists()]
    if missing:
        return (
            ReturnLoopStatus.INVALID,
            f"Missing required files: {', '.join(missing)}",
            [],
            {},
            {},
        )
    if source_status not in READY_SOURCE_STATUSES:
        return (
            ReturnLoopStatus.BLOCKED,
            f"Source status is not ready: {source_status}",
            [],
            {},
            {},
        )

    sizes = {
        "content": file_size(resume_prompt_path),
        "report": file_size(report_path),
        "result": file_size(result_json_path),
    }
    if sizes["content"] > settings.max_resume_prompt_bytes:
        return (
            ReturnLoopStatus.TOO_LARGE,
            "Resume prompt exceeds max bytes.",
            [],
            {},
            sizes,
        )
    if sizes["report"] > settings.max_report_bytes:
        return ReturnLoopStatus.TOO_LARGE, "Report exceeds max bytes.", [], {}, sizes

    try:
        resume_bytes, resume_stable = read_stable_bytes(
            resume_prompt_path, require_stable=settings.require_stable_file_check
        )
        report_bytes, report_stable = read_stable_bytes(
            report_path, require_stable=settings.require_stable_file_check
        )
        result_bytes, result_stable = read_stable_bytes(
            result_json_path, require_stable=settings.require_stable_file_check
        )
    except OSError as exc:
        return (
            ReturnLoopStatus.INVALID,
            f"Could not read required files: {exc}",
            [],
            {},
            sizes,
        )
    if not (resume_stable and report_stable and result_stable):
        return (
            ReturnLoopStatus.STALE,
            "Required files were not stable across reads.",
            [],
            {},
            sizes,
        )

    text = "\n".join(
        [
            resume_bytes.decode("utf-8", errors="replace"),
            report_bytes.decode("utf-8", errors="replace"),
        ]
    )
    sensitivity_flags = sensitivity_flags_for_text(text)
    if sensitivity_flags:
        return (
            ReturnLoopStatus.SENSITIVE,
            "Sensitive marker detected in report or resume prompt.",
            sensitivity_flags,
            {},
            sizes,
        )

    hashes = {
        "content": sha256_bytes(resume_bytes),
        "report": sha256_bytes(report_bytes),
        "result": file_sha256(result_json_path),
    }
    return ReturnLoopStatus.READY, "", [], hashes, sizes
