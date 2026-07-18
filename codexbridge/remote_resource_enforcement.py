from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_CONSERVATIVE_MEMORY_BYTES = 40_000_000_000
DEFAULT_GRACEFUL_MEMORY_BYTES = 45_000_000_000
DEFAULT_HARD_MEMORY_BYTES = 48_000_000_000

ResourceAction = Literal["continue", "graceful_terminate", "hard_terminate"]


@dataclass(frozen=True)
class RemoteMemoryPolicy:
    conservative_bytes: int | None = DEFAULT_CONSERVATIVE_MEMORY_BYTES
    graceful_bytes: int | None = DEFAULT_GRACEFUL_MEMORY_BYTES
    hard_bytes: int | None = DEFAULT_HARD_MEMORY_BYTES

    def __post_init__(self) -> None:
        values = [
            value
            for value in (
                self.conservative_bytes,
                self.graceful_bytes,
                self.hard_bytes,
            )
            if value is not None
        ]
        if any(value <= 0 for value in values):
            raise ValueError("Remote memory thresholds must be positive when enabled")
        if values != sorted(values):
            raise ValueError(
                "Remote memory thresholds must be ordered conservative <= graceful <= hard"
            )

    def to_metadata(self) -> dict[str, int | None]:
        return {
            "conservative_bytes": self.conservative_bytes,
            "graceful_bytes": self.graceful_bytes,
            "hard_bytes": self.hard_bytes,
        }


def evaluate_remote_memory_sample(
    *,
    memory_current_bytes: int,
    policy: RemoteMemoryPolicy,
    host_memory_percent: float | None = None,
) -> dict[str, Any]:
    """Evaluate absolute cgroup memory before optional host-percentage evidence."""

    current = int(memory_current_bytes)
    if current < 0:
        raise ValueError("Remote memory sample must be non-negative")
    if host_memory_percent is not None and not 0 <= float(host_memory_percent) <= 100:
        raise ValueError("Host memory percentage must be between 0 and 100")

    action: ResourceAction = "continue"
    threshold_name = ""
    threshold_bytes: int | None = None
    if policy.hard_bytes is not None and current >= policy.hard_bytes:
        action = "hard_terminate"
        threshold_name = "hard"
        threshold_bytes = policy.hard_bytes
    elif policy.graceful_bytes is not None and current >= policy.graceful_bytes:
        action = "graceful_terminate"
        threshold_name = "graceful"
        threshold_bytes = policy.graceful_bytes
    elif policy.conservative_bytes is not None and current >= policy.conservative_bytes:
        threshold_name = "conservative"
        threshold_bytes = policy.conservative_bytes

    return {
        "sample": {
            "memory_current_bytes": current,
            "host_memory_percent": (
                None if host_memory_percent is None else float(host_memory_percent)
            ),
        },
        "policy": policy.to_metadata(),
        "decision": {
            "action": action,
            "threshold_name": threshold_name,
            "threshold_bytes": threshold_bytes,
            "absolute_cgroup_evaluated_first": True,
        },
    }
