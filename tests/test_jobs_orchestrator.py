from __future__ import annotations

from pathlib import Path

from soma.jobs.long_run_manager import LongRunJobManager
from soma.jobs.models import JobStatus
from soma.local_agent import LocalAgentOrchestrator
from soma.local_agent.models import LocalAgentTaskType, RoutingDecision


class FakeProcess:
    pid = 99

    def poll(self):
        return None

    def terminate(self):
        pass


def fake_popen(argv, **kwargs):
    kwargs["stdout"].write("started\n")
    kwargs["stdout"].flush()
    return FakeProcess()


def legacy_manager(tmp_path: Path) -> LongRunJobManager:
    return LongRunJobManager(
        runs_dir=tmp_path / "runs",
        popen_factory=fake_popen,
        allow_legacy_execution=True,
    )


def test_orchestrator_routes_explicit_long_job_start_status_and_cancel(
    tmp_path: Path,
) -> None:
    manager = legacy_manager(tmp_path)
    orchestrator = LocalAgentOrchestrator(job_manager=manager)

    start = orchestrator.handle_task(
        {"objective": "start long job profile dummy_success", "repo_path": tmp_path}
    )
    job_id = start.job_result.job.job_id
    assert job_id in manager.processes
    status = orchestrator.handle_task(f"check job status {job_id}")
    assert job_id in manager.processes
    assert manager.store.get_job(job_id).status == JobStatus.RUNNING
    cancel = orchestrator.handle_task(f"cancel job {job_id}")

    assert start.task_type == LocalAgentTaskType.LONG_RUN_JOB
    assert start.routing_decision == RoutingDecision.LOCAL_ONLY
    assert start.job_result.job.status == JobStatus.RUNNING
    assert status.job_result.job.job_id == job_id
    assert cancel.job_result.status == JobStatus.CANCELLED
    assert start.audit_event.metadata["external_coder_invoked"] is False


def test_orchestrator_routes_generate_job_report(tmp_path: Path) -> None:
    manager = legacy_manager(tmp_path)
    orchestrator = LocalAgentOrchestrator(job_manager=manager)
    start = orchestrator.handle_task(
        {"objective": "start long job profile dummy_success", "repo_path": tmp_path}
    )

    report = orchestrator.handle_task(
        f"generate job report {start.job_result.job.job_id}"
    )

    assert report.job_result.report_path.exists()
    assert report.job_result.resume_prompt_path.exists()


def test_default_orchestrator_blocks_legacy_long_job_start(tmp_path: Path) -> None:
    result = LocalAgentOrchestrator(
        job_manager=LongRunJobManager(runs_dir=tmp_path / "runs")
    ).handle_task(
        {"objective": "start long job profile dummy_success", "repo_path": tmp_path}
    )

    assert result.job_result.job.status == JobStatus.BLOCKED


def test_orchestrator_does_not_route_edit_tasks_to_job_manager(tmp_path: Path) -> None:
    manager = LongRunJobManager(runs_dir=tmp_path / "runs")
    result = LocalAgentOrchestrator(job_manager=manager).handle_task(
        "fix and refactor the long job manager"
    )

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.job_result is None
