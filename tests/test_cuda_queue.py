from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from soma.cuda_queue import CudaQueueStore
from soma.gateway_models import RunQueryRequest, RunStartRequest


def _acquire(
    queue: CudaQueueStore,
    run_id: str,
    repo_name: str,
    *,
    requested_at: float,
    now: float,
    owner_key: str,
) -> dict[str, object]:
    return queue.try_acquire(
        run_id,
        repo_name=repo_name,
        owner_pid=999_999,
        owner_identity=f"identity:{run_id}",
        owner_key=owner_key,
        requested_at=requested_at,
        now=now,
    )


def test_cuda_queue_is_fifo_exclusive_and_enforces_release_cooldown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soma.cuda_queue.process_matches_identity", lambda *_args: False)
    queue = CudaQueueStore(tmp_path)
    queue.enqueue("run_a", "repo_a", requested_at=1.0, now=1.0)
    queue.enqueue("run_b", "repo_b", requested_at=2.0, now=2.0)

    second_first = _acquire(
        queue,
        "run_b",
        "repo_b",
        requested_at=2.0,
        now=3.0,
        owner_key="owner-b",
    )
    assert second_first["state"] == "queued"
    assert second_first["queue_position"] == 2

    first = _acquire(
        queue,
        "run_a",
        "repo_a",
        requested_at=1.0,
        now=3.0,
        owner_key="owner-a",
    )
    assert first["state"] == "active"
    assert first["lease_generation"] == 1

    still_waiting = _acquire(
        queue,
        "run_b",
        "repo_b",
        requested_at=2.0,
        now=4.0,
        owner_key="owner-b",
    )
    assert still_waiting["state"] == "queued"

    assert queue.release(
        "run_a",
        owner_key="owner-a",
        lease_generation=1,
        now=5.0,
    ) is True
    cooldown = _acquire(
        queue,
        "run_b",
        "repo_b",
        requested_at=2.0,
        now=6.0,
        owner_key="owner-b",
    )
    assert cooldown["state"] == "queued"
    assert cooldown["cooldown_remaining_seconds"] == pytest.approx(1.0)

    second = _acquire(
        queue,
        "run_b",
        "repo_b",
        requested_at=2.0,
        now=7.01,
        owner_key="owner-b",
    )
    assert second["state"] == "active"
    assert second["lease_generation"] == 1


def test_cuda_queue_recovers_dead_stale_active_owner_but_not_before_cooldown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soma.cuda_queue.process_matches_identity", lambda *_args: False)
    queue = CudaQueueStore(tmp_path)
    first = _acquire(
        queue,
        "run_dead",
        "repo_a",
        requested_at=1.0,
        now=1.0,
        owner_key="dead-owner",
    )
    assert first["state"] == "active"
    queue.enqueue("run_next", "repo_b", requested_at=2.0, now=2.0)

    recovered_waiter = _acquire(
        queue,
        "run_next",
        "repo_b",
        requested_at=2.0,
        now=40.0,
        owner_key="next-owner",
    )
    assert recovered_waiter["state"] == "queued"
    snapshot = queue.snapshot(now=40.0)
    assert snapshot["active"] is None
    assert snapshot["cooldown_remaining_seconds"] == pytest.approx(2.0)

    acquired = _acquire(
        queue,
        "run_next",
        "repo_b",
        requested_at=2.0,
        now=42.01,
        owner_key="next-owner",
    )
    assert acquired["state"] == "active"


def test_cuda_queue_does_not_recover_while_bound_orphan_child_is_alive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_pid = 888_888
    monkeypatch.setattr(
        "soma.cuda_queue.process_matches_identity",
        lambda pid, _identity: int(pid or 0) == child_pid,
    )
    queue = CudaQueueStore(tmp_path)
    reservation = _acquire(
        queue,
        "run_parent",
        "repo_a",
        requested_at=1.0,
        now=1.0,
        owner_key="parent-owner",
    )
    generation = int(reservation["lease_generation"])
    assert queue.bind_child(
        "run_parent",
        owner_key="parent-owner",
        lease_generation=generation,
        child_pid=child_pid,
        child_identity="child-identity",
        now=2.0,
    ) is True
    queue.enqueue("run_wait", "repo_b", requested_at=3.0, now=3.0)

    waiting = _acquire(
        queue,
        "run_wait",
        "repo_b",
        requested_at=3.0,
        now=40.0,
        owner_key="wait-owner",
    )
    assert waiting["state"] == "queued"
    active = queue.snapshot(now=40.0)["active"]
    assert active["run_id"] == "run_parent"
    assert active["child_pid"] == child_pid
    assert active["child_identity_present"] is True

    monkeypatch.setattr("soma.cuda_queue.process_matches_identity", lambda *_args: False)
    recovered = _acquire(
        queue,
        "run_wait",
        "repo_b",
        requested_at=3.0,
        now=50.0,
        owner_key="wait-owner",
    )
    assert recovered["state"] == "queued"
    assert queue.snapshot(now=50.0)["active"] is None
    acquired = _acquire(
        queue,
        "run_wait",
        "repo_b",
        requested_at=3.0,
        now=52.01,
        owner_key="wait-owner",
    )
    assert acquired["state"] == "active"


def test_cuda_queue_fresh_heartbeat_prevents_live_reservation_steal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soma.cuda_queue.process_matches_identity", lambda *_args: False)
    queue = CudaQueueStore(tmp_path)
    first = _acquire(
        queue,
        "run_a",
        "repo_a",
        requested_at=1.0,
        now=1.0,
        owner_key="owner-a",
    )
    assert queue.heartbeat(
        "run_a", owner_key="owner-a", lease_generation=int(first["lease_generation"]), now=20.0
    ) is True
    queue.enqueue("run_b", "repo_b", requested_at=2.0, now=2.0)

    second = _acquire(
        queue,
        "run_b",
        "repo_b",
        requested_at=2.0,
        now=45.0,
        owner_key="owner-b",
    )
    assert second["state"] == "queued"
    assert queue.snapshot(now=45.0)["active"]["run_id"] == "run_a"


def test_cuda_queue_live_identity_prevents_recovery_even_if_heartbeat_is_late(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soma.cuda_queue.process_matches_identity", lambda *_args: True)
    queue = CudaQueueStore(tmp_path)
    _acquire(
        queue,
        "run_live",
        "repo_a",
        requested_at=1.0,
        now=1.0,
        owner_key="live-owner",
    )
    queue.enqueue("run_wait", "repo_b", requested_at=2.0, now=2.0)

    waiting = _acquire(
        queue,
        "run_wait",
        "repo_b",
        requested_at=2.0,
        now=100.0,
        owner_key="wait-owner",
    )
    assert waiting["state"] == "queued"
    assert queue.snapshot(now=100.0)["active"]["run_id"] == "run_live"


def test_cuda_queue_refreshes_old_claimant_before_stale_waiter_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soma.cuda_queue.process_matches_identity", lambda *_args: False)
    queue = CudaQueueStore(tmp_path)
    queue.enqueue("run_old", "repo_a", requested_at=1.0, now=1.0)
    queue.enqueue("run_claimant", "repo_b", requested_at=2.0, now=2.0)

    claimant = _acquire(
        queue,
        "run_claimant",
        "repo_b",
        requested_at=2.0,
        now=70.0,
        owner_key="claimant-owner",
    )
    assert claimant["state"] == "active"
    assert claimant["run_id"] == "run_claimant"


def test_cuda_queue_release_is_owner_and_generation_bound_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soma.cuda_queue.process_matches_identity", lambda *_args: False)
    queue = CudaQueueStore(tmp_path)
    reservation = _acquire(
        queue,
        "run_a",
        "repo_a",
        requested_at=1.0,
        now=1.0,
        owner_key="owner-a",
    )
    generation = int(reservation["lease_generation"])

    assert queue.release("run_a", owner_key="wrong", lease_generation=generation, now=2.0) is False
    assert queue.release("run_a", owner_key="owner-a", lease_generation=generation + 1, now=2.0) is False
    assert queue.snapshot(now=2.0)["active"]["run_id"] == "run_a"
    assert queue.release("run_a", owner_key="owner-a", lease_generation=generation, now=2.0) is True
    assert queue.release("run_a", owner_key="owner-a", lease_generation=generation, now=2.5) is True


def test_cuda_queue_snapshot_hides_owner_token_and_reports_fifo_waiters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soma.cuda_queue.process_matches_identity", lambda *_args: False)
    queue = CudaQueueStore(tmp_path)
    _acquire(
        queue,
        "run_a",
        "repo_a",
        requested_at=1.0,
        now=1.0,
        owner_key="secret-owner-key",
    )
    queue.enqueue("run_b", "repo_b", requested_at=2.0, now=2.0)
    snapshot = queue.snapshot(now=3.0)

    assert snapshot["mode"] == "exclusive_fifo"
    assert snapshot["active"]["run_id"] == "run_a"
    assert snapshot["queued"][0]["run_id"] == "run_b"
    assert snapshot["queued"][0]["queue_position"] == 1
    assert "owner_key" not in snapshot["active"]
    assert "owner_key" not in snapshot["queued"][0]


def test_cuda_resource_gateway_contract_is_explicit_and_strict() -> None:
    start_adapter = TypeAdapter(RunStartRequest)
    ordinary = start_adapter.validate_python(
        {"operation": "powershell", "repo_name": "soma", "argv": []}
    )
    assert ordinary.resource_class == "none"
    cuda = start_adapter.validate_python(
        {
            "operation": "powershell",
            "repo_name": "soma",
            "argv": [],
            "resource_class": "cuda_exclusive",
        }
    )
    assert cuda.resource_class == "cuda_exclusive"
    with pytest.raises(ValidationError):
        start_adapter.validate_python(
            {
                "operation": "powershell",
                "repo_name": "soma",
                "argv": [],
                "resource_class": "cuda_shared",
            }
        )

    query = TypeAdapter(RunQueryRequest).validate_python(
        {"operation": "resource_queue", "resource": "cuda", "limit": 7}
    )
    assert query.resource == "cuda"
    assert query.limit == 7
