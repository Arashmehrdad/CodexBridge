from __future__ import annotations

from pathlib import Path

import codexbridge.operation_locks as operation_locks
from codexbridge.operation_locks import OperationLockStore


RUN_ID = "20260706T120000Z_project_command_deadbeef"


def test_operation_lock_rejects_duplicate_active_task(tmp_path: Path) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )

    first = store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={"repo_name": "sample", "command_id": "pytest"},
        run_id=RUN_ID,
    )
    second = store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={"repo_name": "sample", "command_id": "pytest"},
        run_id="20260706T120001Z_project_command_deadbeef",
    )

    assert first.acquired is True
    assert second.acquired is False
    assert second.duplicate is True


def test_operation_lock_release_allows_next_task(tmp_path: Path) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={"repo_name": "sample", "command_id": "pytest"},
        run_id=RUN_ID,
    )

    store.release("sample", RUN_ID)

    next_lock = store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={"repo_name": "sample", "command_id": "pytest"},
        run_id="20260706T120001Z_project_command_deadbeef",
    )
    assert next_lock.acquired is True


def test_operation_lock_retains_nonterminal_run_for_manager_reconciliation(
    tmp_path: Path, monkeypatch
) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={"repo_name": "sample", "command_id": "pytest"},
        status="running",
    )
    store.store.update_run(
        RUN_ID, worker_pid=222, worker_identity="222:windows:1", pid=333
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={"repo_name": "sample", "command_id": "pytest"},
        run_id=RUN_ID,
        owner_pid=111,
    )
    monkeypatch.setattr(
        operation_locks, "process_matches_identity", lambda _pid, _identity: False
    )
    monkeypatch.setattr(
        operation_locks, "process_is_running", lambda _pid: False
    )

    assert store.recover_stale() == 0
    assert store.find_lock("sample", RUN_ID) is not None


def test_operation_lock_removes_terminal_dead_owner(
    tmp_path: Path, monkeypatch
) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
        status="failed",
    )
    store.store.update_run(
        RUN_ID, worker_pid=222, worker_identity="222:windows:1"
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={},
        run_id=RUN_ID,
        owner_pid=111,
    )
    monkeypatch.setattr(
        operation_locks, "process_matches_identity", lambda _pid, _identity: False
    )
    monkeypatch.setattr(
        operation_locks, "process_is_running", lambda _pid: False
    )

    assert store.recover_stale() == 1
    assert store.find_lock("sample", RUN_ID) is None


def test_operation_lock_retains_terminal_run_with_verified_worker(
    tmp_path: Path, monkeypatch
) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
        status="failed",
    )
    store.store.update_run(
        RUN_ID, worker_pid=222, worker_identity="222:windows:1"
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={},
        run_id=RUN_ID,
        owner_pid=111,
    )
    monkeypatch.setattr(
        operation_locks,
        "process_matches_identity",
        lambda pid, identity: pid == 222 and identity == "222:windows:1",
    )
    monkeypatch.setattr(
        operation_locks, "process_is_running", lambda _pid: False
    )

    assert store.recover_stale() == 0
    assert store.find_lock("sample", RUN_ID) is not None


def test_operation_lock_listing_is_sanitized_and_filterable(tmp_path: Path) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={"repo_name": "sample", "command_id": "pytest"},
        run_id=RUN_ID,
        owner_pid=123,
    )

    listed = store.list_locks("SAMPLE")

    assert len(listed) == 1
    assert listed[0]["repo_name"] == "sample"
    assert listed[0]["run_id"] == RUN_ID
    assert listed[0]["run_status"] == "queued"
    assert "input_fingerprint" not in listed[0]
    assert "owner_token" not in listed[0]
    found = store.find_lock("sample", RUN_ID)
    assert found is not None
    assert found["run_id"] == listed[0]["run_id"]
    assert found["repo_name"] == listed[0]["repo_name"]
    assert found["tool"] == listed[0]["tool"]


def test_operation_lock_release_requires_matching_owner_token(tmp_path: Path) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={},
        run_id=RUN_ID,
        owner_token="lease-new",
    )

    store.release("sample", RUN_ID, "lease-old")
    assert store.find_lock("sample", RUN_ID) is not None
    store.release("sample", RUN_ID, "lease-new")
    assert store.find_lock("sample", RUN_ID) is None


def test_operation_lock_listing_can_hide_stale_rows(
    tmp_path: Path, monkeypatch
) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={},
        run_id=RUN_ID,
    )
    monkeypatch.setattr(store, "_is_stale", lambda _conn, _row: True)

    assert store.list_locks(include_stale=False) == []
    assert store.list_locks(include_stale=True)[0]["stale"] is True


def test_cancellation_pending_lock_is_retained_after_owner_exit(
    tmp_path: Path, monkeypatch
) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="ssh:my_vps",
        tool="ssh_monitored_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={"host_id": "my_vps", "command_id": "uptime"},
        status="cancellation_pending",
    )
    store.acquire(
        repo_name="ssh:my_vps",
        tool="ssh_monitored_command",
        normalized_input={"host_id": "my_vps", "command_id": "uptime"},
        run_id=RUN_ID,
        owner_pid=999,
    )
    monkeypatch.setattr(operation_locks, "_pid_is_running", lambda _pid: False)

    assert store.recover_stale() == 0
    lock = store.find_lock("ssh:my_vps", RUN_ID)
    assert lock is not None
    assert lock["run_status"] == "cancellation_pending"
    assert lock["stale"] is False


def test_stale_generation_cannot_release_newer_lock(tmp_path: Path) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
        worker_lease_token="lease-new",
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={},
        run_id=RUN_ID,
        owner_token="lease-new",
        lease_generation=2,
    )

    assert store.release("sample", RUN_ID, "lease-new", 1) is False
    assert store.release("sample", RUN_ID, "lease-old", 2) is False
    assert store.find_lock("sample", RUN_ID) is not None
    assert store.release("sample", RUN_ID, "lease-new", 2) is True
    assert store.find_lock("sample", RUN_ID) is None


def test_launch_reservation_is_single_winner_and_rejects_late_claim(
    tmp_path: Path,
) -> None:
    store = OperationLockStore(tmp_path / "runs")
    store.store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
        status="queued",
        worker_lease_token="lease-old",
    )
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={},
        run_id=RUN_ID,
        owner_pid=111,
        owner_token="lease-old",
        lease_generation=1,
    )
    observed = store.store.get_run(RUN_ID)

    winner = store.reserve_next_launch(
        repo_name="sample",
        run_id=RUN_ID,
        expected_statuses=("queued",),
        expected_state_version=observed["state_version"],
        expected_owner_token="lease-old",
        expected_lease_generation=1,
        new_owner_token="lease-new",
        owner_pid=222,
    )
    loser = store.reserve_next_launch(
        repo_name="sample",
        run_id=RUN_ID,
        expected_statuses=("queued",),
        expected_state_version=observed["state_version"],
        expected_owner_token="lease-old",
        expected_lease_generation=1,
        new_owner_token="lease-other",
        owner_pid=333,
    )

    assert winner is not None
    assert loser is None
    current = store.store.get_run(RUN_ID)
    assert current["status"] == "launch_pending"
    assert current["worker_lease_token"] == "lease-new"
    assert current["lease_generation"] == 2
    assert current["launch_attempts"] == 1
    assert (
        store.store.claim_worker(
            RUN_ID,
            lease_token="lease-old",
            lease_generation=1,
            worker_pid=444,
            worker_identity="444:windows:1",
        )
        is False
    )
    assert store.store.claim_worker(
        RUN_ID,
        lease_token="lease-new",
        lease_generation=2,
        expected_state_version=current["state_version"],
        worker_pid=555,
        worker_identity="555:windows:1",
    )
    lock = store.find_lock("sample", RUN_ID)
    assert lock is not None
    assert lock["lease_generation"] == 2
