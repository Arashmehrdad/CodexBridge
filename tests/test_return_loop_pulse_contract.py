from __future__ import annotations

import json
from pathlib import Path

from codexbridge.config import ReturnLoopConfig
from codexbridge.return_loop.models import ReturnLoopStatus
from codexbridge.return_loop.pulse_contract import (
    build_report_manifest,
    check_report_readiness,
    discover_ready_reports,
    mark_sent_by_external_pulsesender,
)
from codexbridge.run_store import utc_now


def write_report_set(root: Path, source_status: str = "completed", resume: str = "safe resume", report: str = "safe report") -> Path:
    root.mkdir(parents=True)
    (root / "resume_prompt.txt").write_text(resume, encoding="utf-8")
    (root / "job_report.md").write_text(report, encoding="utf-8")
    (root / "result.json").write_text(json.dumps({"status": source_status}), encoding="utf-8")
    manifest = build_report_manifest(
        artifact_type="combined",
        artifact_id=root.name,
        source_kind="job",
        source_status=source_status,
        report_path=root / "job_report.md",
        resume_prompt_path=root / "resume_prompt.txt",
        result_json_path=root / "result.json",
        recommended_next_action="review",
        question_for_chatgpt="continue?",
    )
    assert manifest.artifact_id == root.name
    return root / "pulse_manifest.json"


def test_manifest_includes_required_paths_hashes_and_ready_status(tmp_path: Path) -> None:
    manifest_path = write_report_set(tmp_path / "runs" / "jobs" / "job1")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1"
    assert payload["artifact_type"] == "combined"
    assert payload["conversation_target"] == "codexbridge_gpt"
    assert payload["status"] == "ready"
    assert payload["ready"] is True
    assert payload["send_policy"] == "external_pulsesender_only"
    assert payload["resume_prompt_path"].endswith("resume_prompt.txt")
    assert payload["report_path"].endswith("job_report.md")
    assert payload["result_json_path"].endswith("result.json")
    assert payload["content_sha256"]
    assert payload["report_sha256"]
    assert payload["result_sha256"]


def test_readiness_check_requires_existing_manifest_and_files(tmp_path: Path) -> None:
    missing = check_report_readiness(tmp_path / "missing" / "pulse_manifest.json")

    assert missing.status == ReturnLoopStatus.INVALID
    assert missing.ready is False

    manifest_path = write_report_set(tmp_path / "runs" / "jobs" / "job2")
    (manifest_path.parent / "resume_prompt.txt").unlink()
    result = check_report_readiness(manifest_path)
    assert result.status == ReturnLoopStatus.INVALID
    assert "Missing" in result.blocked_reason


def test_manifest_blocks_too_large_resume_prompt(tmp_path: Path) -> None:
    root = tmp_path / "runs" / "jobs" / "job3"
    root.mkdir(parents=True)
    (root / "resume_prompt.txt").write_text("x" * 50, encoding="utf-8")
    (root / "job_report.md").write_text("safe", encoding="utf-8")
    (root / "result.json").write_text("{}", encoding="utf-8")

    manifest = build_report_manifest(
        artifact_type="combined",
        artifact_id="job3",
        source_kind="job",
        source_status="completed",
        report_path=root / "job_report.md",
        resume_prompt_path=root / "resume_prompt.txt",
        result_json_path=root / "result.json",
        config=ReturnLoopConfig(max_resume_prompt_bytes=20),
    )

    assert manifest.status == ReturnLoopStatus.TOO_LARGE
    assert manifest.ready is False


def test_manifest_blocks_sensitive_content(tmp_path: Path) -> None:
    manifest_path = write_report_set(tmp_path / "runs" / "jobs" / "job4", resume="contains API key")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["status"] == "sensitive"
    assert payload["ready"] is False
    assert "API_KEY" in payload["sensitivity_flags"]


def test_discover_ready_reports_returns_only_ready_unsent_reports(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    ready_path = write_report_set(runs / "jobs" / "job_ready")
    write_report_set(runs / "jobs" / "job_sensitive", resume="secret token")
    outside = tmp_path / "outside" / "jobs" / "job_outside"
    write_report_set(outside)
    mark_sent_by_external_pulsesender(ready_path, utc_now(), sender_id="test")

    write_report_set(runs / "supervisors" / "supervisor_ready")
    reports = discover_ready_reports(runs)

    assert [report.artifact_id for report in reports] == ["supervisor_ready"]


def test_mark_sent_by_external_pulsesender_updates_manifest_atomically(tmp_path: Path) -> None:
    manifest_path = write_report_set(tmp_path / "runs" / "jobs" / "job5")

    manifest = mark_sent_by_external_pulsesender(manifest_path, "2026-05-11T00:00:00+00:00", sender_id="pulse", delivery_hash="abc")

    assert manifest.status == ReturnLoopStatus.SENT_BY_EXTERNAL_PULSESENDER
    assert manifest.ready is False
    assert manifest.delivered is True
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["sender_id"] == "pulse"
    assert payload["delivery_hash"] == "abc"
