from __future__ import annotations

import pytest

from soma.remote_resource_enforcement import (
    DEFAULT_CONSERVATIVE_MEMORY_BYTES,
    DEFAULT_GRACEFUL_MEMORY_BYTES,
    DEFAULT_HARD_MEMORY_BYTES,
    RemoteMemoryPolicy,
    evaluate_remote_memory_sample,
)


def test_default_thresholds_match_r5_contract() -> None:
    policy = RemoteMemoryPolicy()

    assert policy.to_metadata() == {
        "conservative_bytes": DEFAULT_CONSERVATIVE_MEMORY_BYTES,
        "graceful_bytes": DEFAULT_GRACEFUL_MEMORY_BYTES,
        "hard_bytes": DEFAULT_HARD_MEMORY_BYTES,
    }


@pytest.mark.parametrize(
    ("sample", "action", "threshold_name"),
    [
        (DEFAULT_CONSERVATIVE_MEMORY_BYTES - 1, "continue", ""),
        (DEFAULT_CONSERVATIVE_MEMORY_BYTES, "continue", "conservative"),
        (DEFAULT_GRACEFUL_MEMORY_BYTES, "graceful_terminate", "graceful"),
        (DEFAULT_HARD_MEMORY_BYTES, "hard_terminate", "hard"),
    ],
)
def test_absolute_threshold_paths_are_deterministic(
    sample: int,
    action: str,
    threshold_name: str,
) -> None:
    result = evaluate_remote_memory_sample(
        memory_current_bytes=sample,
        policy=RemoteMemoryPolicy(),
        host_memory_percent=99.0,
    )

    assert result["decision"]["action"] == action
    assert result["decision"]["threshold_name"] == threshold_name
    assert result["decision"]["absolute_cgroup_evaluated_first"] is True
    assert result["sample"]["host_memory_percent"] == 99.0


def test_permissive_policy_can_raise_or_disable_thresholds() -> None:
    raised = RemoteMemoryPolicy(
        conservative_bytes=50_000_000_000,
        graceful_bytes=55_000_000_000,
        hard_bytes=60_000_000_000,
    )
    disabled = RemoteMemoryPolicy(
        conservative_bytes=None,
        graceful_bytes=None,
        hard_bytes=None,
    )

    raised_result = evaluate_remote_memory_sample(
        memory_current_bytes=48_000_000_000,
        policy=raised,
    )
    disabled_result = evaluate_remote_memory_sample(
        memory_current_bytes=100_000_000_000,
        policy=disabled,
    )

    assert raised_result["decision"]["action"] == "continue"
    assert raised_result["policy"] == raised.to_metadata()
    assert disabled_result["decision"] == {
        "action": "continue",
        "threshold_name": "",
        "threshold_bytes": None,
        "absolute_cgroup_evaluated_first": True,
    }
    assert disabled_result["policy"] == disabled.to_metadata()


def test_invalid_policy_and_samples_are_rejected() -> None:
    with pytest.raises(ValueError, match="ordered"):
        RemoteMemoryPolicy(
            conservative_bytes=45,
            graceful_bytes=40,
            hard_bytes=48,
        )
    with pytest.raises(ValueError, match="positive"):
        RemoteMemoryPolicy(conservative_bytes=0)
    with pytest.raises(ValueError, match="non-negative"):
        evaluate_remote_memory_sample(
            memory_current_bytes=-1,
            policy=RemoteMemoryPolicy(),
        )
    with pytest.raises(ValueError, match="between 0 and 100"):
        evaluate_remote_memory_sample(
            memory_current_bytes=1,
            policy=RemoteMemoryPolicy(),
            host_memory_percent=100.1,
        )
