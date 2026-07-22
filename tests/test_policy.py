from __future__ import annotations

from soma.policy import (
    BalancedAutonomyProfile,
    decide_implementation_task,
    decide_plan_task,
    evaluate_implementation_profile,
    evaluate_plan_profile,
)


def test_plan_jobs_are_auto_approved() -> None:
    decision = decide_plan_task("inspect docs")
    assert decision.accepted is True
    assert decision.tier == 1


def test_human_only_plan_is_refused() -> None:
    decision = decide_plan_task("use login credentials")
    assert decision.accepted is False
    assert decision.requires_human is True


def test_docs_only_implementation_is_auto_approved() -> None:
    decision = decide_implementation_task(
        "edit docs", ["README.md", "docs/guide.md"], []
    )
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


def test_balanced_profile_allows_default_plan_and_implementation_tiers() -> None:
    profile = BalancedAutonomyProfile()
    assert (
        evaluate_plan_profile(decide_plan_task("inspect docs"), profile).allowed is True
    )
    assert (
        evaluate_implementation_profile(
            decide_implementation_task("edit app", ["app.py"], []),
            profile,
            allowed_files=["app.py"],
            tests=[],
        ).allowed
        is True
    )


def test_profile_hard_stops_rejected_and_human_required_decisions() -> None:
    profile = BalancedAutonomyProfile()
    result = evaluate_plan_profile(decide_plan_task("use login credentials"), profile)
    assert result.allowed is False
    assert "policy_rejected" in result.hard_stop["reasons"]
    assert "requires_human" in result.hard_stop["reasons"]


def test_conservative_profile_blocks_tier_two_implementation() -> None:
    profile = BalancedAutonomyProfile(max_implementation_tier=1)
    result = evaluate_implementation_profile(
        decide_implementation_task("edit app", ["app.py"], ["python -m pytest"]),
        profile,
        allowed_files=["app.py"],
        tests=["python -m pytest"],
        profile_name="conservative",
    )
    assert result.allowed is False
    assert "implementation_tier_exceeds_profile" in result.hard_stop["reasons"]


def test_profile_can_require_tests_for_non_docs_changes() -> None:
    profile = BalancedAutonomyProfile(
        max_implementation_tier=2, require_tests_for_non_docs_changes=True
    )
    result = evaluate_implementation_profile(
        decide_implementation_task("edit app", ["app.py"], []),
        profile,
        allowed_files=["app.py"],
        tests=[],
    )
    assert result.allowed is False
    assert "tests_required_for_non_docs_changes" in result.hard_stop["reasons"]
