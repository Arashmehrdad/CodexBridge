from __future__ import annotations

from pathlib import Path

import pytest

from soma.config import AppConfig, RepoConfig
from soma.run_store import RunStore
from soma.supervisor_engine import FakeChildJobBackend
from soma.supervisor_resume_prompt import write_resume_prompt
from soma.supervisor_service import SupervisorService


RUN_ID = "20260428T120000Z_codex_plan_task_abcdef12"


class StubSupervisorService(SupervisorService):
    def __init__(
        self, config: AppConfig, config_path: Path | None, jobs: FakeChildJobBackend
    ):
        super().__init__(config, config_path)
        self.jobs = jobs

    def child_backend(self):
        return self.jobs


def make_git_repo(path: Path) -> None:
    path.mkdir()
    (path / ".git").mkdir()


def make_service(
    tmp_path: Path,
) -> tuple[StubSupervisorService, FakeChildJobBackend, AppConfig]:
    repo = tmp_path / "repo"
    make_git_repo(repo)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"soma": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    jobs = FakeChildJobBackend()
    return StubSupervisorService(config, config_path, jobs), jobs, config


def create_source_run(config: AppConfig) -> None:
    store = RunStore(config.resolve_runs_dir())
    store.create_run(
        run_id=RUN_ID,
        repo_name="soma",
        tool="codex_plan_task",
        run_dir=config.resolve_runs_dir() / RUN_ID,
        input_data={},
    )


def active_run_id(supervisor: dict) -> str:
    return supervisor["metadata"]["active_child"]["run_id"]


def supervisor_metadata() -> dict:
    return {
        "plan": {"task": "task", "constraints": ""},
        "active_child": None,
        "plan_result": None,
        "approval": None,
        "implementation_result": None,
        "implementation_lock": None,
        "blocked": None,
        "policy": {"profile": {"name": "balanced"}},
        "hard_stop": None,
    }


def attach_historical_child(
    service: SupervisorService,
    jobs: FakeChildJobBackend,
    supervisor: dict,
    *,
    kind: str = "plan",
    seed_job: bool = True,
):
    """Model a supervisor whose child predates the Codex-execution removal."""
    if seed_job:
        job = jobs.seed(kind)
        run_id = job.run_id
    else:
        job = None
        run_id = f"20260428T120099Z_codex_{kind}_task_deadbeef"
    attached = service.store.attach_child(
        supervisor["supervisor_id"],
        run_id=run_id,
        link_type=kind,
        child_kind=kind,
        target_status="planning" if kind == "plan" else "implementing",
        metadata=dict(supervisor["metadata"]),
        expected_statuses=(supervisor["status"],),
        expected_state_version=int(supervisor["state_version"]),
    )
    assert attached is not None
    return attached, job


def needs_input(service: StubSupervisorService, jobs: FakeChildJobBackend) -> dict:
    created = service.store.create_supervisor(
        repo_name="soma", objective="objective", metadata=supervisor_metadata()
    )
    attached, job = attach_historical_child(service, jobs, created, kind="plan")
    jobs.complete(job.run_id, summary="plan", result={"plan": "ok"})
    return service.resume(created["supervisor_id"])


def test_start_supervised_recovery_task_generates_handoff_and_links_source_run(
    tmp_path: Path,
) -> None:
    service, jobs, config = make_service(tmp_path)
    create_source_run(config)
    supervisor = service.start_supervised_recovery_task(
        "soma", "objective", "task", source_run_id=RUN_ID
    )
    assert supervisor["status"] == "needs_external_coder"
    assert supervisor["run_links"][0]["link_type"] == "source"
    assert len(supervisor["run_links"]) == 1
    # No child run of any kind is created or launched.
    assert jobs.jobs == {}
    handoff = supervisor["metadata"]["external_coder_handoff"]
    assert handoff["status"] == "handoff_ready"
    assert Path(handoff["prompt_path"]).is_file()


def test_source_run_must_match_repo(tmp_path: Path) -> None:
    service, _jobs, config = make_service(tmp_path)
    RunStore(config.resolve_runs_dir()).create_run(
        run_id=RUN_ID,
        repo_name="other",
        tool="codex_plan_task",
        run_dir=config.resolve_runs_dir() / RUN_ID,
        input_data={},
    )
    with pytest.raises(ValueError, match="source_run_id"):
        service.start_supervised_recovery_task(
            "soma", "objective", "task", source_run_id=RUN_ID
        )


def test_unknown_autonomy_profile_rejected(tmp_path: Path) -> None:
    service, _jobs, _config = make_service(tmp_path)
    with pytest.raises(ValueError, match="Unknown autonomy_profile"):
        service.start_supervised_recovery_task(
            "soma", "objective", "task", autonomy_profile="missing"
        )


def test_get_status_enriches_supervisor(tmp_path: Path) -> None:
    service, _jobs, _config = make_service(tmp_path)
    supervisor = service.start_supervised_recovery_task(
        "soma", "objective", "task"
    )
    status = service.get_status(supervisor["supervisor_id"])
    assert status["status"] == "needs_external_coder"
    assert status["resume_prompt_path"].endswith("resume_prompt.txt")
    assert status["resume_prompt_exists"] is True
    assert status["pending_notifications"] == 1


def test_get_events_returns_limited_ordered_events(tmp_path: Path) -> None:
    service, _jobs, _config = make_service(tmp_path)
    supervisor = service.start_supervised_recovery_task(
        "soma", "objective", "task"
    )
    events = service.get_events(supervisor["supervisor_id"], limit=1)
    assert len(events) == 1
    assert events[0]["stage"] == "needs_external_coder"


def test_get_result_surfaces_plan_and_implementation_results(tmp_path: Path) -> None:
    service, jobs, _config = make_service(tmp_path)
    current = needs_input(service, jobs)
    implementing = service.store.update_supervisor(
        current["supervisor_id"],
        status="completed",
        metadata_json={
            **current["metadata"],
            "implementation_result": {"summary": "done"},
        },
    )
    result = service.get_result(implementing["supervisor_id"])
    assert result["plan_result"]["plan"] == "ok"
    assert result["implementation_result"]["summary"] == "done"


def test_get_resume_prompt_existing_and_missing(tmp_path: Path) -> None:
    service, jobs, config = make_service(tmp_path)
    current = needs_input(service, jobs)
    missing = service.get_resume_prompt("20260428T120001Z_supervisor_abcdef12")
    assert missing["exists"] is False
    write_resume_prompt(config.resolve_runs_dir(), current)
    existing = service.get_resume_prompt(current["supervisor_id"])
    assert existing["exists"] is True
    assert "You are an external coding agent resuming" in existing["content"]


def test_get_notifications_filters_status_and_limit(tmp_path: Path) -> None:
    service, _jobs, _config = make_service(tmp_path)
    supervisor = service.start_supervised_recovery_task(
        "soma", "objective", "use login credentials"
    )
    notes = service.get_notifications(
        supervisor["supervisor_id"], delivery_status="pending", limit=1
    )
    assert len(notes) == 1
    with pytest.raises(ValueError, match="Invalid delivery_status"):
        service.get_notifications(
            supervisor["supervisor_id"], delivery_status="unknown"
        )


def test_resume_advances_queued_to_needs_external_coder(tmp_path: Path) -> None:
    service, jobs, _config = make_service(tmp_path)
    created = service.store.create_supervisor(
        repo_name="soma",
        objective="objective",
        metadata=supervisor_metadata(),
    )
    resumed = service.resume(created["supervisor_id"])
    assert resumed["status"] == "needs_external_coder"
    assert jobs.jobs == {}


def test_restart_resumes_queued_supervisor_without_launching_anything(
    tmp_path: Path,
) -> None:
    service, jobs, config = make_service(tmp_path)
    created = service.store.create_supervisor(
        repo_name="soma",
        objective="objective",
        metadata=supervisor_metadata(),
    )

    recreated = StubSupervisorService(config, service.config_path, jobs)
    resumed = recreated.resume(created["supervisor_id"])
    handoff_id = resumed["metadata"]["external_coder_handoff"]["handoff_id"]
    resumed_again = recreated.resume(created["supervisor_id"])

    assert resumed["status"] == "needs_external_coder"
    assert resumed_again["status"] == "needs_external_coder"
    assert (
        resumed_again["metadata"]["external_coder_handoff"]["handoff_id"]
        == handoff_id
    )
    assert jobs.jobs == {}


def test_resume_historical_planning_and_approval_generate_handoff(
    tmp_path: Path,
) -> None:
    service, jobs, _config = make_service(tmp_path)
    current = needs_input(service, jobs)
    assert current["status"] == "needs_input"

    from soma.supervisor_engine import SupervisorEngine

    engine = SupervisorEngine(service.store, jobs)
    parked = engine.approve_plan(
        current["supervisor_id"], "approved", ["README.md"], []
    )
    assert parked["status"] == "needs_external_coder"
    assert (
        parked["metadata"]["external_coder_handoff"]["kind"] == "implementation"
    )
    # Resume keeps the parked state; nothing further is executed.
    resumed = service.resume(current["supervisor_id"])
    assert resumed["status"] == "needs_external_coder"


def test_pause_supervisor_supported_states_and_rejections(tmp_path: Path) -> None:
    service, _jobs, _config = make_service(tmp_path)
    created = service.store.create_supervisor(
        repo_name="soma", objective="objective", metadata=supervisor_metadata()
    )
    paused = service.pause(created["supervisor_id"])
    assert paused["status"] == "paused"
    resumed = service.resume(created["supervisor_id"])
    assert resumed["status"] == "needs_external_coder"

    with pytest.raises(ValueError, match="queued or needs_input"):
        service.pause(resumed["supervisor_id"])


def test_cancel_supervisor_delegates_engine_cancel(tmp_path: Path) -> None:
    service, jobs, _config = make_service(tmp_path)
    created = service.store.create_supervisor(
        repo_name="soma", objective="objective", metadata=supervisor_metadata()
    )
    attached, job = attach_historical_child(service, jobs, created, kind="plan")
    cancelled = service.cancel(created["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert jobs.get(job.run_id).cancel_requested is True


def test_restart_preserves_unverified_child_cancellation_state(
    tmp_path: Path,
) -> None:
    service, jobs, config = make_service(tmp_path)
    created = service.store.create_supervisor(
        repo_name="soma", objective="objective", metadata=supervisor_metadata()
    )
    attached, _job = attach_historical_child(
        service, jobs, created, kind="plan", seed_job=False
    )
    child_run_id = active_run_id(attached)

    blocked = service.cancel(created["supervisor_id"])
    events_before_restart = service.get_events(created["supervisor_id"])

    assert blocked["status"] == "needs_input"
    assert blocked["metadata"]["active_child"]["run_id"] == child_run_id
    assert sum(
        event["stage"] == "cancellation_unverified" for event in events_before_restart
    ) == 1

    recreated = StubSupervisorService(config, service.config_path, jobs)
    recovered = recreated.get_status(created["supervisor_id"])
    events_after_restart = recreated.get_events(created["supervisor_id"])

    assert recovered["status"] == "needs_input"
    assert recovered["metadata"]["active_child"]["run_id"] == child_run_id
    assert recovered["active_child_status"] == {
        "run_id": child_run_id,
        "status": "unknown",
    }
    assert jobs.jobs == {}
    assert events_after_restart == events_before_restart
