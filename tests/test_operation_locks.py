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


def test_operation_lock_recovers_stale_dead_worker_before_server_pid(
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
    store.store.update_run(RUN_ID, worker_pid=222, pid=333)
    store.acquire(
        repo_name="sample",
        tool="project_command",
        normalized_input={"repo_name": "sample", "command_id": "pytest"},
        run_id=RUN_ID,
        owner_pid=111,
    )

    monkeypatch.setattr(
        operation_locks,
        "_pid_is_running",
        lambda pid: pid in {111},
    )

    assert store.recover_stale() == 1
