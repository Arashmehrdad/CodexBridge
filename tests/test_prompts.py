from __future__ import annotations

from soma.prompts import build_implementation_prompt, build_plan_prompt


def test_plan_prompt_includes_no_edit_delete_commit_push_rules() -> None:
    prompt = build_plan_prompt("repo", "do work", "constraints")
    assert "Do not edit files" in prompt
    assert "Do not delete files" in prompt
    assert "Do not commit" in prompt
    assert "Do not push" in prompt
    assert "Inspect only" in prompt
    assert "Do not ask the user to send the actual task" in prompt
    assert "PLAN_STATUS: ready" in prompt


def test_implementation_prompt_includes_allowed_files_and_no_push_rules() -> None:
    prompt = build_implementation_prompt(
        "repo", "approved", ["a.py"], ["python -m pytest"]
    )
    assert "a.py" in prompt
    assert "python -m pytest" in prompt
    assert "Do not push" in prompt
    assert "Do not commit" in prompt
    assert "exclusive write allowlist" in prompt
    assert "temporary or diagnostic files" in prompt
    assert "Do not create a fallback document" in prompt
    assert "FINAL_STATUS: completed|blocked|failed" in prompt
    assert "PLAN_CONFORMANCE: yes|no" in prompt
