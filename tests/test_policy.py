from __future__ import annotations

from codexbridge.policy import decide_implementation_task, decide_plan_task


def test_plan_jobs_are_auto_approved() -> None:
    decision = decide_plan_task("inspect docs")
    assert decision.accepted is True
    assert decision.tier == 1


def test_human_only_plan_is_refused() -> None:
    decision = decide_plan_task("use login credentials")
    assert decision.accepted is False
    assert decision.requires_human is True


def test_docs_only_implementation_is_auto_approved() -> None:
    decision = decide_implementation_task("edit docs", ["README.md", "docs/guide.md"], [])
    assert decision.accepted is True
    assert decision.tier == 1


def test_secret_like_files_are_refused() -> None:
    decision = decide_implementation_task("edit", [".env"], [])
    assert decision.accepted is False
    assert decision.requires_human is True


def test_normal_implementation_is_chatgpt_approved_tier() -> None:
    decision = decide_implementation_task("edit app", ["app.py"], ["python -m pytest"])
    assert decision.accepted is True
    assert decision.tier == 2
    assert decision.risk_level == "medium"
