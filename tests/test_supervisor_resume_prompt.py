from __future__ import annotations

from pathlib import Path

from codexbridge.supervisor_resume_prompt import (
    PULSESENDER_DELIVERY_NOTE,
    build_resume_prompt,
    supervisor_prompt_path,
    write_resume_prompt,
)


SUPERVISOR_ID = "20260428T120000Z_supervisor_abcdef12"
RUN_ID = "20260428T120001Z_codex_plan_task_12345678"


def supervisor(status: str, metadata: dict | None = None, **overrides) -> dict:
    data = {
        "supervisor_id": SUPERVISOR_ID,
        "repo_name": "codexbridge",
        "status": status,
        "objective": "resume work",
        "summary": "summary",
        "error": "",
        "metadata": metadata or {},
        "run_links": [{"run_id": RUN_ID, "link_type": "plan"}],
    }
    data.update(overrides)
    return data


def test_needs_input_prompt_includes_plan_result_and_artifact_references(
    tmp_path: Path,
) -> None:
    prompt = build_resume_prompt(
        supervisor("needs_input", {"plan_result": {"summary": "plan ready"}}),
        tmp_path / "runs",
    )
    assert "You are Codex resuming a CodexBridge supervisor context." in prompt
    assert "status: needs_input" in prompt
    assert f"plan: {RUN_ID}" in prompt
    assert str(tmp_path / "runs" / RUN_ID / "result.json") in prompt
    assert "Review the plan result" in prompt


def test_prompt_includes_pulsesender_delivery_note_once_near_top(
    tmp_path: Path,
) -> None:
    prompt = build_resume_prompt(supervisor("needs_input"), tmp_path)
    assert PULSESENDER_DELIVERY_NOTE in prompt
    assert prompt.count(PULSESENDER_DELIVERY_NOTE) == 1
    assert prompt.index(PULSESENDER_DELIVERY_NOTE) < prompt.index("repo_name:")
    assert prompt.index(PULSESENDER_DELIVERY_NOTE) < prompt.index("Hard Rules:")
    for prohibited in (
        "cookies",
        "tokens",
        "browser profile data",
        "internal browser state",
    ):
        assert prohibited not in PULSESENDER_DELIVERY_NOTE.lower()


def test_blocked_needs_input_prompt_has_blocked_guidance(tmp_path: Path) -> None:
    prompt = build_resume_prompt(
        supervisor(
            "needs_input", {"blocked": {"reason": "repo_write_lock_unavailable"}}
        ),
        tmp_path,
    )
    assert "repo_write_lock_unavailable" in prompt
    assert "Resolve the blocking condition" in prompt


def test_failed_cancelled_and_completed_guidance(tmp_path: Path) -> None:
    assert "safe recovery plan" in build_resume_prompt(
        supervisor("failed", error="failed"), tmp_path
    )
    assert "Confirm cancellation" in build_resume_prompt(
        supervisor("cancelled"), tmp_path
    )
    assert "Review the final result" in build_resume_prompt(
        supervisor("completed"), tmp_path
    )


def test_prompt_redacts_secret_like_and_truncates_oversized_fields(
    tmp_path: Path,
) -> None:
    prompt = build_resume_prompt(
        supervisor(
            "failed",
            {"hard_stop": {"reason": "API_KEY=abc123", "large": "x" * 3000}},
            error="token: secret-value",
        ),
        tmp_path,
    )
    assert "abc123" not in prompt
    assert "secret-value" not in prompt
    assert "[truncated" in prompt


def test_write_resume_prompt_uses_canonical_path(tmp_path: Path) -> None:
    path = write_resume_prompt(
        tmp_path / "runs", supervisor("completed"), tmp_path / "runs"
    )
    assert path == supervisor_prompt_path(tmp_path / "runs", SUPERVISOR_ID)
    assert path.exists()
