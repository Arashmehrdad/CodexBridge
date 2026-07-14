from __future__ import annotations

import json
from pathlib import Path

from codexbridge.return_loop.models import ReturnLoopStatus
from codexbridge.return_loop.pulse_contract import (
    build_report_manifest,
    discover_ready_reports,
    mark_sent_by_external_pulsesender,
)


def test_regeneration_preserves_external_delivery_state(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    root = runs_dir / "jobs" / "job_delivered"
    root.mkdir(parents=True)
    resume_path = root / "resume_prompt.txt"
    report_path = root / "job_report.md"
    result_path = root / "result.json"
    resume_path.write_text("safe resume", encoding="utf-8")
    report_path.write_text("safe report", encoding="utf-8")
    result_path.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    ready = build_report_manifest(
        artifact_type="combined",
        artifact_id="job_delivered",
        source_kind="job",
        source_status="completed",
        report_path=report_path,
        resume_prompt_path=resume_path,
        result_json_path=result_path,
        recommended_next_action="review",
        question_for_chatgpt="continue?",
    )
    manifest_path = root / "pulse_manifest.json"
    delivered = mark_sent_by_external_pulsesender(
        manifest_path,
        "2026-05-11T00:00:00+00:00",
        sender_id="pulse",
        delivery_hash="abc",
    )
    original_report_hash = ready.report_sha256
    report_path.write_text("updated safe report", encoding="utf-8")

    regenerated = build_report_manifest(
        artifact_type="combined",
        artifact_id="job_delivered",
        source_kind="job",
        source_status="completed",
        report_path=report_path,
        resume_prompt_path=resume_path,
        result_json_path=result_path,
        recommended_next_action="review",
        question_for_chatgpt="continue?",
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert regenerated.status == ReturnLoopStatus.SENT_BY_EXTERNAL_PULSESENDER
    assert regenerated.ready is False
    assert regenerated.delivered is True
    assert regenerated.sent_at == delivered.sent_at
    assert regenerated.sender_id == "pulse"
    assert regenerated.delivery_hash == "abc"
    assert regenerated.created_at == delivered.created_at
    assert regenerated.audit_event_id == delivered.audit_event_id
    assert regenerated.report_sha256 != original_report_hash
    assert payload["status"] == "sent_by_external_pulsesender"
    assert discover_ready_reports(runs_dir) == []
