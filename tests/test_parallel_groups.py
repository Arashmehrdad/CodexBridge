from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codexbridge.parallel_groups import ParallelGroupStore


def child_spec(runs_dir: Path, suffix: str) -> dict:
    run_id = f"20260716T040000Z_executable_profile_{suffix}"
    return {
        "run_id": run_id,
        "idempotency_key": f"child-{suffix}",
        "run_dir": runs_dir / run_id,
        "worker_lease_token": f"lease-{suffix}",
        "input_data": {
            "repo_name": "sample",
            "profile_id": "powershell",
            "argv": ["-NoProfile", "-Command", f"Write-Output '{suffix}'"],
        },
    }


def test_reserve_group_atomically_persists_parent_and_all_children(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    store = ParallelGroupStore(runs_dir)
    children = [child_spec(runs_dir, "a1b2c3d4"), child_spec(runs_dir, "b2c3d4e5")]

    group = store.reserve_group(
        group_id="20260716T040000Z_powershell_group_c3d4e5f6",
        repo_name="sample",
        children=children,
        requested_concurrency=2,
        input_data={"autonomy_profile": "permissive"},
    )

    assert group["status"] == "launch_pending"
    assert group["mode"] == "all_at_once"
    assert group["failure_policy"] == "continue_all"
    assert group["repository_lock_policy"] == "none"
    assert group["requested_concurrency"] == 2
    assert group["input"] == {"autonomy_profile": "permissive"}
    assert group["child_run_ids"] == [child["run_id"] for child in children]
    for child in children:
        run = store.store.get_run(child["run_id"])
        assert run["status"] == "launch_pending"
        assert run["current_phase"] == "launch_pending"
        assert run["worker_lease_token"] == child["worker_lease_token"]
        assert run["input"] == child["input_data"]


def test_reserve_group_rolls_back_parent_and_children_on_conflict(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    store = ParallelGroupStore(runs_dir)
    existing = child_spec(runs_dir, "a1b2c3d4")
    store.store.create_run(
        run_id=existing["run_id"],
        repo_name="sample",
        tool="executable_profile",
        run_dir=existing["run_dir"],
        input_data=existing["input_data"],
        status="launch_pending",
        worker_lease_token=existing["worker_lease_token"],
    )

    group_id = "20260716T040000Z_powershell_group_d4e5f6a7"
    with pytest.raises(sqlite3.IntegrityError):
        store.reserve_group(
            group_id=group_id,
            repo_name="sample",
            children=[existing, child_spec(runs_dir, "b2c3d4e5")],
        )

    with pytest.raises(KeyError):
        store.get_group(group_id)
    with pytest.raises(KeyError):
        store.store.get_run("20260716T040000Z_executable_profile_b2c3d4e5")


def test_reserve_group_rejects_duplicate_idempotency_keys_before_write(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    store = ParallelGroupStore(runs_dir)
    first = child_spec(runs_dir, "a1b2c3d4")
    second = child_spec(runs_dir, "b2c3d4e5")
    second["idempotency_key"] = first["idempotency_key"]
    group_id = "20260716T040000Z_powershell_group_e5f6a7b8"

    with pytest.raises(ValueError, match="Duplicate child idempotency_key"):
        store.reserve_group(
            group_id=group_id,
            repo_name="sample",
            children=[first, second],
        )

    with pytest.raises(KeyError):
        store.get_group(group_id)
