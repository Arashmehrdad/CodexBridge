from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from codexbridge.config import AppConfig, RepoConfig
from codexbridge.return_loop.report_manifest import file_sha256
from codexbridge.workflows.manager import WorkflowManager
from codexbridge.workflows.models import WorkflowStatus, WorkflowStepStatus
from codexbridge.workflows.publication import publish_workflow
from codexbridge.workflows.reporter import generate_workflow_report, write_workflow_snapshot
from codexbridge.workflows.store import WorkflowStore


def _config(tmp_path: Path) -> tuple[AppConfig, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    return AppConfig(repos={"repo": RepoConfig(path=str(repo))}, runs_dir=str(tmp_path / "runs"), config_dir=tmp_path), config_path


@pytest.fixture
def durable_tmp_path() -> Path:
    path = (Path("runs") / "pytest_tmp" / uuid4().hex).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def _create(store: WorkflowStore, workflow_id: str = "workflow"):
    return store.create_workflow(
        workflow_id=workflow_id,
        repo_name="repo",
        objective="durability",
        worker_lease_token="old-token",
        lease_generation=1,
        launch_attempts=1,
        steps=[
            {
                "id": "one",
                "order_index": 0,
                "type": "project_command",
                "parameters": {"command_id": "ok"},
                "depends_on": [],
                "on_failure": "stop",
            }
        ],
    )


def test_stale_generation_cannot_mutate_claimed_step_after_replacement(durable_tmp_path: Path) -> None:
    config, _ = _config(durable_tmp_path)
    store = WorkflowStore(config.resolve_runs_dir())
    workflow = _create(store)
    workflow = store.claim_worker("workflow", lease_token="old-token", lease_generation=1, expected_state_version=workflow.state_version, worker_pid=1, worker_identity="old") and store.get_workflow("workflow")
    claimed = store.claim_step("workflow", "one", lease_token="old-token", lease_generation=1, child_run_id="child", expected_workflow_state_version=workflow.state_version, expected_step_state_version=workflow.steps[0].state_version)
    assert claimed is not None
    reserved = store.reserve_next_launch("workflow", expected_statuses=(WorkflowStatus.RUNNING,), expected_state_version=claimed.state_version, expected_lease_token="old-token", expected_lease_generation=1, expected_heartbeat_at=claimed.heartbeat_at, new_lease_token="new-token")
    assert reserved is not None
    stale = store.conditional_update_step("workflow", "one", fields={"status": WorkflowStepStatus.PASSED}, expected_statuses=(WorkflowStepStatus.RUNNING,), lease_token="old-token", lease_generation=1, expected_state_version=claimed.steps[0].state_version, expected_child_run_id="child", expected_workflow_state_version=claimed.state_version)
    assert stale is None
    assert store.get_workflow("workflow").steps[0].status == WorkflowStepStatus.RUNNING


def test_verified_launcher_prevents_replacement_generation(durable_tmp_path: Path) -> None:
    config, config_path = _config(durable_tmp_path)
    launches: list[int] = []
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: launches.append(10) or 10, identity_reader=lambda _pid: "launcher-10", identity_checker=lambda _pid, identity: identity == "launcher-10")
    started = manager.start_workflow("repo", "x", [{"id": "one", "type": "project_command", "parameters": {"command_id": "ok"}}])
    assert manager.reconcile_startup() == 0
    assert launches == [10]
    assert manager.reconcile_startup() == 0


def test_live_legacy_pid_enters_recovery_without_relaunch_or_termination(durable_tmp_path: Path) -> None:
    config, config_path = _config(durable_tmp_path)
    launches: list[int] = []
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: launches.append(20) or 20, process_checker=lambda pid: pid == 99)
    workflow = _create(manager.store)
    manager.store.update_workflow("workflow", status=WorkflowStatus.RUNNING, worker_pid=99)
    assert manager.reconcile_startup() == 0
    current = manager.store.get_workflow("workflow")
    assert current.status == WorkflowStatus.RECOVERY_PENDING
    assert launches == []


def test_one_replacement_is_reserved_after_prior_identity_is_absent(durable_tmp_path: Path) -> None:
    config, config_path = _config(durable_tmp_path)
    launches: list[int] = []
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: launches.append(20) or 20, process_checker=lambda _pid: False)
    manager.start_workflow("repo", "x", [{"id": "one", "type": "project_command", "parameters": {"command_id": "ok"}}])
    assert manager.reconcile_startup() == 1
    assert len(launches) == 2


def test_durable_child_id_is_retained_across_worker_replacement(durable_tmp_path: Path) -> None:
    config, config_path = _config(durable_tmp_path)
    launches: list[int] = []

    class ChildManager:
        def get_status(self, _run_id: str):
            return {"status": "running"}

    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: launches.append(20) or 20, process_checker=lambda _pid: False, job_manager_factory=ChildManager)
    workflow = _create(manager.store)
    claimed = manager.store.claim_worker("workflow", lease_token="old-token", lease_generation=1, expected_state_version=workflow.state_version, worker_pid=1, worker_identity="")
    assert claimed
    running = manager.store.claim_step("workflow", "one", lease_token="old-token", lease_generation=1, child_run_id="child-1", expected_workflow_state_version=manager.store.get_workflow("workflow").state_version, expected_step_state_version=0)
    assert running is not None
    manager.store.update_workflow("workflow", worker_pid=None, launcher_pid=None, worker_identity="", launcher_identity="")
    assert manager.reconcile_startup() == 1
    current = manager.store.get_workflow("workflow")
    assert current.active_child_run_id == "child-1"
    assert current.steps[0].child_run_id == "child-1"
    assert len(launches) == 1


def test_cancellation_stays_pending_when_child_does_not_become_terminal(durable_tmp_path: Path) -> None:
    config, config_path = _config(durable_tmp_path)

    class ChildManager:
        def cancel_run(self, run_id: str):
            return {"ok": True, "run_id": run_id, "status": "queued"}

        def get_status(self, _run_id: str):
            return {"status": "running"}

    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 11, process_checker=lambda _pid: False, job_manager_factory=ChildManager)
    workflow = _create(manager.store)
    manager.store.update_workflow("workflow", status=WorkflowStatus.RUNNING, active_child_run_id="child")
    manager.store.update_step("workflow", "one", status=WorkflowStepStatus.RUNNING, child_run_id="child")
    result = manager.cancel_workflow("workflow")
    assert result["cancelled"] is False
    assert manager.store.get_workflow("workflow").status == WorkflowStatus.CANCELLATION_PENDING


def test_cancellation_stays_pending_when_legacy_process_termination_is_uncertain(durable_tmp_path: Path) -> None:
    config, config_path = _config(durable_tmp_path)
    terminated: list[int] = []
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 11, process_checker=lambda pid: pid == 11, termination_fn=lambda pid: terminated.append(int(pid or 0)) or {"pid": pid, "terminated": True})
    _create(manager.store)
    manager.store.update_workflow("workflow", status=WorkflowStatus.RUNNING, launcher_pid=11)
    result = manager.cancel_workflow("workflow")
    assert result["cancelled"] is False
    assert terminated == []
    assert manager.store.get_workflow("workflow").status == WorkflowStatus.CANCELLATION_PENDING


def test_cancellation_publishes_only_after_owned_processes_are_confirmed(durable_tmp_path: Path) -> None:
    config, config_path = _config(durable_tmp_path)
    alive = {"worker": True}

    def identity_checker(_pid: int | None, identity: str | None) -> bool:
        return bool(identity and alive["worker"])

    def terminate(pid: int | None):
        alive["worker"] = False
        return {"pid": pid, "terminated": True}

    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 11, identity_checker=identity_checker, identity_reader=lambda _pid: "worker", process_checker=lambda _pid: True, termination_fn=terminate)
    workflow = _create(manager.store)
    manager.store.update_workflow("workflow", status=WorkflowStatus.RUNNING, worker_pid=11, worker_identity="worker")
    result = manager.cancel_workflow("workflow")
    assert result["cancelled"] is True
    final = manager.store.get_workflow("workflow")
    assert final.status == WorkflowStatus.REPORTED
    assert final.terminal_status == WorkflowStatus.CANCELLED
    assert final.publication_status == "published"


def test_terminal_publication_repairs_repeated_crash_windows_and_wins_from_database(durable_tmp_path: Path) -> None:
    config, _ = _config(durable_tmp_path)
    store = WorkflowStore(config.resolve_runs_dir())
    workflow = _create(store)
    running = store.conditional_update_workflow("workflow", fields={"status": WorkflowStatus.FAILED, "terminal_status": WorkflowStatus.FAILED, "ended_at": "now"}, expected_statuses=(WorkflowStatus.QUEUED,), expected_state_version=workflow.state_version, expected_lease_token="old-token", expected_lease_generation=1)
    assert running is not None
    first = publish_workflow(store, config.resolve_runs_dir(), "workflow")
    second = publish_workflow(store, config.resolve_runs_dir(), "workflow")
    assert first.terminal_status == WorkflowStatus.FAILED
    assert second.status == WorkflowStatus.REPORTED
    assert second.publication_status == "published"
    assert second.publication_hash == first.publication_hash


def test_stale_generation_cannot_append_guarded_event(durable_tmp_path: Path) -> None:
    config, _ = _config(durable_tmp_path)
    store = WorkflowStore(config.resolve_runs_dir())
    workflow = _create(store)
    reserved = store.reserve_next_launch(
        "workflow",
        expected_statuses=(WorkflowStatus.QUEUED,),
        expected_state_version=workflow.state_version,
        expected_lease_token="lease-1",
        expected_lease_generation=1,
        expected_heartbeat_at=workflow.heartbeat_at,
        new_lease_token="lease-2",
    )
    assert reserved is not None
    event = store.append_event(
        "workflow",
        level="info",
        stage="stale",
        message="stale worker event",
        update_workflow_metadata=False,
        expected_lease_token="lease-1",
        expected_lease_generation=1,
        expected_statuses=(WorkflowStatus.QUEUED,),
        expected_state_version=workflow.state_version,
    )
    assert event is None
    assert store.get_events("workflow") == []


def test_running_external_step_without_child_enters_recovery_pending(
    durable_tmp_path: Path,
) -> None:
    config, config_path = _config(durable_tmp_path)
    launches: list[int] = []
    manager = WorkflowManager(
        config,
        config_path,
        worker_launcher=lambda *_args: launches.append(20) or 20,
        process_checker=lambda _pid: False,
    )
    _create(manager.store)
    manager.store.update_workflow("workflow", status=WorkflowStatus.RUNNING)
    manager.store.update_step(
        "workflow", "one", status=WorkflowStepStatus.RUNNING, child_run_id=None
    )
    assert manager.reconcile_startup() == 0
    assert manager.store.get_workflow("workflow").status == WorkflowStatus.RECOVERY_PENDING
    assert launches == []


def test_cancellation_waits_when_verified_termination_is_not_confirmed(
    durable_tmp_path: Path,
) -> None:
    config, config_path = _config(durable_tmp_path)
    manager = WorkflowManager(
        config,
        config_path,
        worker_launcher=lambda *_args: 11,
        process_checker=lambda _pid: True,
        identity_checker=lambda _pid, identity: identity == "worker-11",
        identity_reader=lambda _pid: "worker-11",
        termination_fn=lambda pid: {"pid": pid, "terminated": True},
    )
    _create(manager.store)
    manager.store.update_workflow(
        "workflow",
        status=WorkflowStatus.RUNNING,
        worker_pid=11,
        worker_identity="worker-11",
    )
    result = manager.cancel_workflow("workflow")
    assert result["ok"] is False
    assert result["cancelled"] is False
    assert manager.store.get_workflow("workflow").status == WorkflowStatus.CANCELLATION_PENDING


def test_repeated_startup_does_not_duplicate_replacement_or_durable_child(
    durable_tmp_path: Path,
) -> None:
    config, config_path = _config(durable_tmp_path)
    launches: list[int] = []

    def identity_checker(pid: int | None, identity: str | None) -> bool:
        return pid == 20 and identity == "new-launcher"

    manager = WorkflowManager(
        config,
        config_path,
        worker_launcher=lambda *_args: launches.append(20) or 20,
        process_checker=lambda _pid: False,
        identity_reader=lambda pid: "new-launcher" if pid == 20 else "",
        identity_checker=identity_checker,
    )
    workflow = _create(manager.store)
    assert manager.store.claim_worker(
        "workflow",
        lease_token="lease-1",
        lease_generation=1,
        expected_state_version=workflow.state_version,
        worker_pid=10,
        worker_identity="old-worker",
    )
    current = manager.store.get_workflow("workflow")
    claimed = manager.store.claim_step(
        "workflow",
        "one",
        lease_token="lease-1",
        lease_generation=1,
        child_run_id="child-1",
        expected_workflow_state_version=current.state_version,
        expected_step_state_version=current.steps[0].state_version,
    )
    assert claimed is not None
    assert manager.reconcile_startup() == 1
    assert manager.reconcile_startup() == 0
    final = manager.store.get_workflow("workflow")
    assert launches == [20]
    assert final.lease_generation == 2
    assert final.active_child_run_id == "child-1"
    assert final.steps[0].child_run_id == "child-1"
    assert final.steps[0].child_launch_attempts == 1


def test_startup_repairs_terminal_publication_crash_windows_and_corruption(
    durable_tmp_path: Path,
) -> None:
    config, config_path = _config(durable_tmp_path)
    manager = WorkflowManager(
        config,
        config_path,
        worker_launcher=lambda *_args: 1,
        process_checker=lambda _pid: False,
    )
    workflow = _create(manager.store)
    terminal = manager.store.conditional_update_workflow(
        "workflow",
        fields={
            "status": WorkflowStatus.FAILED,
            "terminal_status": WorkflowStatus.FAILED,
            "ended_at": "now",
            "failure_summary": "database winner",
        },
        expected_statuses=(WorkflowStatus.QUEUED,),
        expected_state_version=workflow.state_version,
        expected_lease_token="lease-1",
        expected_lease_generation=1,
    )
    assert terminal is not None
    write_workflow_snapshot(config.resolve_runs_dir(), terminal, [])
    generate_workflow_report(config.resolve_runs_dir(), terminal)
    assert manager.store.get_workflow("workflow").status == WorkflowStatus.FAILED

    assert manager.reconcile_startup() == 0
    published = manager.store.get_workflow("workflow")
    assert published.status == WorkflowStatus.REPORTED
    publication_hash = published.publication_hash
    root = config.resolve_runs_dir() / "workflows" / "workflow"
    (root / "workflow_report.md").write_text("corrupt", encoding="utf-8")
    (root / "result.json").write_text("{broken", encoding="utf-8")

    assert manager.reconcile_startup() == 0
    repaired = manager.store.get_workflow("workflow")
    manifest = json.loads((root / "pulse_manifest.json").read_text(encoding="utf-8"))
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    assert repaired.status == WorkflowStatus.REPORTED
    assert repaired.publication_hash == publication_hash
    assert result["terminal_status"] == WorkflowStatus.FAILED.value
    assert "database winner" in (root / "workflow_report.md").read_text(encoding="utf-8")
    assert manifest["report_sha256"] == file_sha256(root / "workflow_report.md")
    assert manifest["content_sha256"] == file_sha256(root / "resume_prompt.txt")
    assert manifest["result_sha256"] == file_sha256(root / "result.json")


def test_stale_finalizer_publishes_only_the_database_winner(
    durable_tmp_path: Path,
) -> None:
    config, config_path = _config(durable_tmp_path)
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 1)
    stale = _create(manager.store)
    winner = manager.store.conditional_update_workflow(
        "workflow",
        fields={
            "status": WorkflowStatus.FAILED,
            "terminal_status": WorkflowStatus.FAILED,
            "ended_at": "now",
            "failure_summary": "winner failed",
        },
        expected_statuses=(WorkflowStatus.QUEUED,),
        expected_state_version=stale.state_version,
        expected_lease_token="lease-1",
        expected_lease_generation=1,
    )
    assert winner is not None
    final = manager._finalize_terminal_workflow(stale)
    payload = json.loads(
        (
            config.resolve_runs_dir()
            / "workflows"
            / "workflow"
            / "result.json"
        ).read_text(encoding="utf-8")
    )
    assert final.terminal_status == WorkflowStatus.FAILED
    assert payload["terminal_status"] == WorkflowStatus.FAILED.value
    assert payload["failure_summary"] == "winner failed"


def test_needs_approval_terminal_is_reported_and_ready(durable_tmp_path: Path) -> None:
    config, config_path = _config(durable_tmp_path)
    manager = WorkflowManager(config, config_path, worker_launcher=lambda *_args: 1)
    workflow = _create(manager.store)
    terminal = manager.store.conditional_update_workflow(
        "workflow",
        fields={
            "status": WorkflowStatus.NEEDS_APPROVAL,
            "terminal_status": WorkflowStatus.NEEDS_APPROVAL,
            "ended_at": "now",
        },
        expected_statuses=(WorkflowStatus.QUEUED,),
        expected_state_version=workflow.state_version,
        expected_lease_token="lease-1",
        expected_lease_generation=1,
    )
    assert terminal is not None
    assert manager.reconcile_startup() == 0
    final = manager.store.get_workflow("workflow")
    manifest = json.loads(
        (
            config.resolve_runs_dir()
            / "workflows"
            / "workflow"
            / "pulse_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert final.status == WorkflowStatus.REPORTED
    assert final.terminal_status == WorkflowStatus.NEEDS_APPROVAL
    assert manifest["source_status"] == WorkflowStatus.NEEDS_APPROVAL.value
    assert manifest["ready"] is True
