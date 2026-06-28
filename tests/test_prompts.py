from __future__ import annotations

from codexbridge.prompts import build_implementation_prompt, build_plan_prompt


def test_plan_prompt_includes_no_edit_delete_commit_push_rules() -> None:
    prompt = build_plan_prompt("repo", "do work", "constraints")
    assert "Do not edit files" in prompt
    assert "Do not delete files" in prompt
    assert "Do not commit" in prompt
    assert "Do not push" in prompt
    assert "Inspect only" in prompt


def test_implementation_prompt_includes_allowed_files_and_no_push_rules() -> None:
    prompt = build_implementation_prompt(
        "repo", "approved", ["a.py"], ["python -m pytest"]
    )
    assert "a.py" in prompt
    assert "python -m pytest" in prompt
    assert "Do not push" in prompt
    assert "Do not commit" in prompt
    assert "Touch only allowed_files" in prompt
