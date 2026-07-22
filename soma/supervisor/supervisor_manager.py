from __future__ import annotations

from pathlib import Path

from soma.config import AppConfig, LocalSupervisorConfig
from soma.job_manager import JobManager

from .models import (
    SupervisorResult,
    SupervisorStatus,
    SupervisorStatusResult,
    SupervisorTaskRequest,
)
from .supervisor_flow import SupervisorFlow
from .supervisor_reporter import generate_supervisor_report
from .supervisor_store import LocalSupervisorStore


class LocalSupervisorManager:
    def __init__(
        self,
        *,
        supervisors_dir: Path,
        config: LocalSupervisorConfig | None = None,
        command_runner=None,
        app_config: AppConfig | None = None,
        config_path: Path | None = None,
        job_manager: JobManager | None = None,
        codex_router=None,
        memory_repository=None,
        local_model=None,
    ):
        self.store = LocalSupervisorStore(supervisors_dir)
        self.config = config or LocalSupervisorConfig()
        self.flow = SupervisorFlow(
            store=self.store,
            config=self.config,
            command_runner=command_runner,
            app_config=app_config,
            config_path=config_path,
            job_manager=job_manager,
            codex_router=codex_router,
            memory_repository=memory_repository,
            local_model=local_model,
        )

    def start_supervised_task(self, request: SupervisorTaskRequest) -> SupervisorResult:
        return self.flow.start_supervised_task(request)

    def get_status(self, supervisor_id: str) -> SupervisorStatusResult:
        return SupervisorStatusResult(
            run=self.store.get(supervisor_id), events=self.store.events(supervisor_id)
        )

    def list_runs(self, limit: int = 20):
        return self.store.list(limit)

    def cancel(self, supervisor_id: str) -> SupervisorResult:
        run = self.store.update(
            supervisor_id,
            status=SupervisorStatus.CANCELLED,
            next_recommended_action="Supervisor was cancelled.",
        )
        report = generate_supervisor_report(run)
        self.store.append_event(
            supervisor_id, stage="cancelled", message="Supervisor cancelled"
        )
        return SupervisorResult(
            run=run,
            report_path=report.report_path,
            resume_prompt_path=report.resume_prompt_path,
            pulse_manifest_path=report.pulse_manifest_path,
        )

    def resume(self, supervisor_id: str) -> SupervisorStatusResult:
        return self.get_status(supervisor_id)

    def generate_report(self, supervisor_id: str) -> SupervisorResult:
        run = self.store.get(supervisor_id)
        report = generate_supervisor_report(run)
        self.store.append_event(
            supervisor_id,
            stage="report_generated",
            message="Supervisor report generated",
        )
        return SupervisorResult(
            run=run,
            report_path=report.report_path,
            resume_prompt_path=report.resume_prompt_path,
            pulse_manifest_path=report.pulse_manifest_path,
        )
