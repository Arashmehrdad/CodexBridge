from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from soma.config import (
    AppConfig,
    ExecutableProfileConfig,
    ParallelExecutionConfig,
    RepoConfig,
)
from soma.parallel_groups import (
    ParallelGroupStore,
    launch_powershell_group,
    refill_powershell_groups,
)
from soma.process_control import (
    LaunchContainment,
    LaunchContainmentDisposition,
    LaunchIdentityUnavailable,
)


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


def parallel_config(tmp_path: Path, *, max_concurrent: int | None = None) -> AppConfig:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    executable = tmp_path / "pwsh.exe"
    executable.write_bytes(b"fake-powershell")
    return AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        executable_profiles={
            "powershell": ExecutableProfileConfig(
                profile_id="powershell",
                enabled=True,
                executable_path=str(executable),
                unrestricted_argv=True,
                stdin_mode="text",
            )
        },
        parallel_execution=ParallelExecutionConfig(
            enabled=True,
            max_concurrent_powershell=max_concurrent,
        ),
        config_dir=tmp_path,
    )


@pytest.fixture(autouse=True)
def _synthetic_launch_identity(monkeypatch):
    """Deterministic identity reader for the synthetic launcher handles.

    These fakes are not live processes, so a real capture would correctly refuse
    to attach them. A synthetic reader keeps the fixture's ownership provable
    without spawning real processes or letting host PID allocation decide a
    verdict.
    """
    monkeypatch.setattr(
        "soma.parallel_groups.capture_launch_identity",
        lambda process, **_kwargs: f"{process.pid}:synthetic:1",
    )


class FakeProcess:
    def __init__(self, pid: int):
        self.pid = pid


def test_launch_group_reserves_and_materializes_every_child_before_first_spawn(
    tmp_path: Path,
) -> None:
    config = parallel_config(tmp_path)
    runs_dir = config.resolve_runs_dir()
    run_ids = [
        "20260716T050000Z_executable_profile_a1b2c3d4",
        "20260716T050000Z_executable_profile_b2c3d4e5",
    ]
    group_id = "20260716T050000Z_powershell_group_c3d4e5f6"
    observed_spawns: list[str] = []

    def spawn_worker(run_id: str, lease_token: str) -> FakeProcess:
        assert lease_token
        if not observed_spawns:
            store = ParallelGroupStore(runs_dir)
            for child_run_id in run_ids:
                assert store.store.get_run(child_run_id)["status"] == "launch_pending"
                assert (runs_dir / child_run_id / "input.json").is_file()
                assert (runs_dir / child_run_id / "events.jsonl").is_file()
        observed_spawns.append(run_id)
        return FakeProcess(12000 + len(observed_spawns))

    result = launch_powershell_group(
        config=config,
        repo_name="sample",
        group_id=group_id,
        children=[
            {
                "run_id": run_ids[0],
                "idempotency_key": "first",
                "argv": ["-NoProfile", "-Command", "Write-Output first"],
            },
            {
                "run_id": run_ids[1],
                "idempotency_key": "second",
                "argv": ["-NoProfile", "-Command", "Write-Output second"],
            },
        ],
        spawn_worker=spawn_worker,
    )

    assert result["accepted"] is True
    assert result["child_run_ids"] == run_ids
    assert result["launched_run_ids"] == run_ids
    assert result["pending_run_ids"] == []
    assert observed_spawns == run_ids
    store = ParallelGroupStore(runs_dir)
    assert [store.store.get_run(run_id)["status"] for run_id in run_ids] == [
        "queued",
        "queued",
    ]
    assert all(store.store.get_run(run_id)["launcher_identity"] for run_id in run_ids)


def test_parallel_initial_launch_uncertainty_remains_active(
    tmp_path: Path, monkeypatch
) -> None:
    config = parallel_config(tmp_path)
    run_id = "20260716T050050Z_executable_profile_a1b2c3d4"
    group_id = "20260716T050050Z_powershell_group_c3d4e5f6"

    def refuse(process, **_kwargs):
        raise LaunchIdentityUnavailable(
            LaunchContainment(
                disposition=LaunchContainmentDisposition.ROOT_EXIT_CONFIRMED,
                pid=process.pid,
                kill_attempted=True,
                root_exit_confirmed=True,
                owned_tree_empty=False,
                method="creator_handle",
                error="simulated root exit without tree proof",
            )
        )

    monkeypatch.setattr("soma.parallel_groups.capture_launch_identity", refuse)
    result = launch_powershell_group(
        config=config,
        repo_name="sample",
        group_id=group_id,
        children=[
            {
                "run_id": run_id,
                "idempotency_key": "uncertain",
                "argv": ["-NoProfile", "-Command", "Write-Output uncertain"],
            }
        ],
        spawn_worker=lambda *_args: FakeProcess(4242),
    )

    store = ParallelGroupStore(config.resolve_runs_dir())
    run = store.store.get_run(run_id)
    group = store.refresh_group(group_id)
    assert result["accepted"] is True
    assert run["status"] == "recovery_pending"
    assert group["status"] == "running"
    assert group["result"]["terminal_child_count"] == 0


def test_launch_group_respects_global_powershell_concurrency_limit(
    tmp_path: Path,
) -> None:
    config = parallel_config(tmp_path, max_concurrent=1)
    run_ids = [
        "20260716T050100Z_executable_profile_a1b2c3d4",
        "20260716T050100Z_executable_profile_b2c3d4e5",
    ]
    spawned: list[str] = []

    result = launch_powershell_group(
        config=config,
        repo_name="sample",
        group_id="20260716T050100Z_powershell_group_c3d4e5f6",
        children=[
            {"run_id": run_ids[0], "idempotency_key": "first", "argv": ["one"]},
            {"run_id": run_ids[1], "idempotency_key": "second", "argv": ["two"]},
        ],
        spawn_worker=lambda run_id, lease_token: (
            spawned.append(run_id) or FakeProcess(13000)
        ),
    )

    assert spawned == [run_ids[0]]
    assert result["launched_run_ids"] == [run_ids[0]]
    assert result["pending_run_ids"] == [run_ids[1]]
    store = ParallelGroupStore(config.resolve_runs_dir())
    assert store.store.get_run(run_ids[0])["status"] == "queued"
    assert store.store.get_run(run_ids[1])["status"] == "pending"
    recoverable_ids = {run["run_id"] for run in store.store.list_recoverable_runs()}
    assert run_ids[1] not in recoverable_ids


def test_claim_pending_launches_respects_global_and_group_limits(
    tmp_path: Path,
) -> None:
    config = parallel_config(tmp_path, max_concurrent=2)
    runs_dir = config.resolve_runs_dir()
    store = ParallelGroupStore(runs_dir)
    first_group = "20260716T051000Z_powershell_group_a1b2c3d4"
    second_group = "20260716T051001Z_powershell_group_b2c3d4e5"
    first_children = [
        child_spec(runs_dir, "c1d2e3f4"),
        child_spec(runs_dir, "d2e3f4a5"),
    ]
    second_children = [child_spec(runs_dir, "e3f4a5b6")]
    for child in [*first_children, *second_children]:
        child["initial_status"] = "pending"
    store.reserve_group(
        group_id=first_group,
        repo_name="sample",
        children=first_children,
        requested_concurrency=1,
    )
    store.reserve_group(
        group_id=second_group,
        repo_name="sample",
        children=second_children,
    )

    claimed = store.claim_pending_launches(max_concurrent_powershell=2)

    assert [run["run_id"] for run in claimed] == [
        first_children[0]["run_id"],
        second_children[0]["run_id"],
    ]
    assert (
        store.store.get_run(first_children[0]["run_id"])["status"] == "launch_pending"
    )
    assert store.store.get_run(first_children[1]["run_id"])["status"] == "pending"
    assert (
        store.store.get_run(second_children[0]["run_id"])["status"] == "launch_pending"
    )
    assert store.claim_pending_launches(max_concurrent_powershell=2) == []


def test_claim_pending_launches_refills_one_terminal_slot_exactly_once(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    store = ParallelGroupStore(runs_dir)
    children = [
        child_spec(runs_dir, "f4a5b6c7"),
        child_spec(runs_dir, "a5b6c7d8"),
    ]
    children[1]["initial_status"] = "pending"
    store.reserve_group(
        group_id="20260716T051100Z_powershell_group_b6c7d8e9",
        repo_name="sample",
        children=children,
        requested_concurrency=1,
    )
    first = store.store.get_run(children[0]["run_id"])
    store.store.conditional_update(
        first["run_id"],
        fields={"status": "completed", "current_phase": "result"},
        expected_statuses=("launch_pending",),
        expected_state_version=int(first["state_version"]),
        expected_lease_token=first["worker_lease_token"],
        expected_lease_generation=int(first["lease_generation"]),
    )

    claimed = store.claim_pending_launches(max_concurrent_powershell=1)

    assert [run["run_id"] for run in claimed] == [children[1]["run_id"]]
    assert store.claim_pending_launches(max_concurrent_powershell=1) == []


def test_refill_persists_identity_and_retains_uncertain_child(
    tmp_path: Path, monkeypatch
) -> None:
    config = parallel_config(tmp_path, max_concurrent=1)
    run_ids = [
        "20260716T051150Z_executable_profile_a1b2c3d4",
        "20260716T051150Z_executable_profile_b2c3d4e5",
    ]
    group_id = "20260716T051150Z_powershell_group_c3d4e5f6"
    launch_powershell_group(
        config=config,
        repo_name="sample",
        group_id=group_id,
        children=[
            {"run_id": run_ids[0], "idempotency_key": "first", "argv": ["one"]},
            {"run_id": run_ids[1], "idempotency_key": "second", "argv": ["two"]},
        ],
        spawn_worker=lambda *_args: FakeProcess(13001),
    )
    store = ParallelGroupStore(config.resolve_runs_dir())
    first = store.store.get_run(run_ids[0])
    store.store.transition_terminal(
        run_ids[0],
        status="completed",
        result={"run_id": run_ids[0], "status": "completed"},
        expected_statuses=("queued",),
        expected_state_version=int(first["state_version"]),
        expected_lease_token=first["worker_lease_token"],
        expected_lease_generation=int(first["lease_generation"]),
    )

    assert refill_powershell_groups(
        config=config,
        spawn_worker=lambda *_args: FakeProcess(13002),
    ) == [run_ids[1]]
    assert store.store.get_run(run_ids[1])["launcher_identity"] == "13002:synthetic:1"

    third = child_spec(config.resolve_runs_dir(), "c3d4e5f6")
    third["initial_status"] = "pending"
    second_group = "20260716T051151Z_powershell_group_d4e5f6a7"
    store.reserve_group(
        group_id=second_group,
        repo_name="sample",
        children=[third],
        requested_concurrency=1,
    )
    second = store.store.get_run(run_ids[1])
    store.store.transition_terminal(
        run_ids[1],
        status="completed",
        result={"run_id": run_ids[1], "status": "completed"},
        expected_statuses=("queued",),
        expected_state_version=int(second["state_version"]),
        expected_lease_token=second["worker_lease_token"],
        expected_lease_generation=int(second["lease_generation"]),
    )

    def refuse(process, **_kwargs):
        raise LaunchIdentityUnavailable(
            LaunchContainment(
                disposition=LaunchContainmentDisposition.ROOT_EXIT_CONFIRMED,
                pid=process.pid,
                kill_attempted=True,
                root_exit_confirmed=True,
                owned_tree_empty=False,
                method="creator_handle",
                error="simulated refill root exit without tree proof",
            )
        )

    monkeypatch.setattr("soma.parallel_groups.capture_launch_identity", refuse)
    assert (
        refill_powershell_groups(
            config=config,
            spawn_worker=lambda *_args: FakeProcess(13003),
        )
        == []
    )
    assert store.store.get_run(third["run_id"])["status"] == "recovery_pending"
    assert store.refresh_group(second_group)["status"] == "running"


def test_group_child_repository_lock_policy_defaults_to_required(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    store = ParallelGroupStore(runs_dir)
    child = child_spec(runs_dir, "a6b7c8d9")
    store.reserve_group(
        group_id="20260716T051500Z_powershell_group_b7c8d9e0",
        repo_name="sample",
        children=[child],
        repository_lock_policy="none",
    )

    assert store.repository_lock_required_for_child(child["run_id"]) is False
    assert (
        store.repository_lock_required_for_child(
            "20260716T051500Z_executable_profile_c8d9e0f1"
        )
        is True
    )


def test_refresh_group_publishes_durable_aggregate_state(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ParallelGroupStore(runs_dir)
    children = [
        child_spec(runs_dir, "b7c8d9e0"),
        child_spec(runs_dir, "c8d9e0f1"),
    ]
    group_id = "20260716T052000Z_powershell_group_d9e0f1a2"
    store.reserve_group(
        group_id=group_id,
        repo_name="sample",
        children=children,
    )

    running = store.refresh_group(group_id)

    assert running["status"] == "launch_pending"
    assert running["result"]["child_count"] == 2
    assert running["result"]["terminal_child_count"] == 0
    assert running["result"]["status_counts"] == {"launch_pending": 2}

    for child in children:
        run = store.store.get_run(child["run_id"])
        store.store.transition_terminal(
            child["run_id"],
            status="completed",
            result={
                "run_id": child["run_id"],
                "status": "completed",
                "stdout_artifact": "stdout.bin",
                "stderr_artifact": "stderr.bin",
            },
            expected_statuses=("launch_pending",),
            expected_state_version=int(run["state_version"]),
            expected_lease_token=run["worker_lease_token"],
            expected_lease_generation=int(run["lease_generation"]),
            summary="completed",
        )

    completed = store.refresh_group(group_id)

    assert completed["status"] == "completed"
    assert completed["ended_at"]
    assert completed["result"]["terminal_child_count"] == 2
    assert completed["result"]["status_counts"] == {"completed": 2}
    assert [child["status"] for child in completed["children"]] == [
        "completed",
        "completed",
    ]
    assert [child["artifacts"] for child in completed["children"]] == [
        {"stdout_artifact": "stdout.bin", "stderr_artifact": "stderr.bin"},
        {"stdout_artifact": "stdout.bin", "stderr_artifact": "stderr.bin"},
    ]


def test_refresh_group_marks_mixed_terminal_failure(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ParallelGroupStore(runs_dir)
    children = [
        child_spec(runs_dir, "d9e0f1a2"),
        child_spec(runs_dir, "e0f1a2b3"),
    ]
    group_id = "20260716T052100Z_powershell_group_f1a2b3c4"
    store.reserve_group(group_id=group_id, repo_name="sample", children=children)

    for child, status in zip(children, ("completed", "failed"), strict=True):
        run = store.store.get_run(child["run_id"])
        store.store.transition_terminal(
            child["run_id"],
            status=status,
            result={"run_id": child["run_id"], "status": status},
            expected_statuses=("launch_pending",),
            expected_state_version=int(run["state_version"]),
            expected_lease_token=run["worker_lease_token"],
            expected_lease_generation=int(run["lease_generation"]),
            summary=status,
            error="boom" if status == "failed" else "",
        )

    group = store.refresh_group(group_id)

    assert group["status"] == "failed"
    assert group["result"]["status_counts"] == {"completed": 1, "failed": 1}


def test_launch_group_validation_failure_writes_nothing(tmp_path: Path) -> None:
    config = parallel_config(tmp_path)
    group_id = "20260716T050200Z_powershell_group_c3d4e5f6"

    with pytest.raises(ValueError, match="requires argv"):
        launch_powershell_group(
            config=config,
            repo_name="sample",
            group_id=group_id,
            children=[
                {"idempotency_key": "first", "argv": ["one"]},
                {"idempotency_key": "second", "argv": "not-a-list"},
            ],
            spawn_worker=lambda run_id, lease_token: FakeProcess(14000),
        )

    store = ParallelGroupStore(config.resolve_runs_dir())
    with pytest.raises(KeyError):
        store.get_group(group_id)
    assert not any(config.resolve_runs_dir().glob("*_executable_profile_*"))
