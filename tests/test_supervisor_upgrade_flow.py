from __future__ import annotations

from pathlib import Path

from codexbridge.config import LocalSupervisorConfig
from codexbridge.codex_router.models import CodexEscalationStatus, CodexRouterResult
from codexbridge.codex_router.models import CodexInvocationResult
from codexbridge.local_agent.models import (
    CommandRunResult,
    CommandRunStatus,
    PermissionTier,
)
from codexbridge.return_loop.models import ReportManifest
from codexbridge.run_store import utc_now
from codexbridge.supervisor import (
    LocalSupervisorManager,
    SupervisorStatus,
    SupervisorTaskRequest,
)


class FakeCommandRunner:
    def __init__(self, statuses: dict[str, CommandRunStatus] | None = None):
        self.statuses = statuses or {}
        self.calls: list[str] = []

    def run_project_command(
        self, *, command_id: str, repo_name=None, repo_path=None, **kwargs
    ):
        self.calls.append(command_id)
        status = self.statuses.get(command_id, CommandRunStatus.SUCCESS)
        exit_code = 0 if status == CommandRunStatus.SUCCESS else 1
        return CommandRunResult(
            run_id=f"run_{command_id}",
            command_id=command_id,
            repo_name=repo_name,
            repo_path=Path(repo_path) if repo_path else None,
            working_directory=Path(repo_path) if repo_path else Path.cwd(),
            argv=["fake", command_id],
            permission_tier=PermissionTier.SAFE_LOCAL_TEST
            if command_id in {"pytest", "pip_check"}
            else PermissionTier.READ_ONLY,
            status=status,
            exit_code=exit_code,
            duration_seconds=0.01,
            timeout_seconds=1,
            timed_out=False,
            stdout_path=Path("stdout.txt"),
            stderr_path=Path("stderr.txt"),
            result_path=Path("result.json"),
            audit_event_id=f"audit_{command_id}",
            created_at=utc_now(),
            error="" if status == CommandRunStatus.SUCCESS else "failed",
        )


class FakeCodexRouter:
    def __init__(
        self,
        status: CodexEscalationStatus = CodexEscalationStatus.PACKET_READY,
        *,
        invoked: bool = False,
    ):
        self.status = status
        self.invoked = invoked
        self.calls = []

    def route_escalation(self, request):
        self.calls.append(request)
        packet_dir = Path.cwd() / "runs" / "codex_escalations" / request.escalation_id
        packet_dir.mkdir(parents=True, exist_ok=True)
        packet_path = packet_dir / "packet.json"
        packet_path.write_text("{}", encoding="utf-8")
        return CodexRouterResult(
            escalation_id=request.escalation_id,
            status=self.status,
            artifacts={
                "escalation_id": request.escalation_id,
                "packet_dir": packet_dir,
                "packet_json_path": packet_path,
                "prompt_path": packet_dir / "prompt.txt",
                "context_manifest_path": packet_dir / "context_manifest.json",
                "policy_result_path": packet_dir / "policy_result.json",
            },
            invocation_result=CodexInvocationResult(
                status=self.status, invoked=self.invoked
            )
            if self.invoked
            else None,
            reasons=["fake_router"],
            audit_event_id="audit_codex_router",
        )


def make_manager(tmp_path: Path, *, runner=None, router=None) -> LocalSupervisorManager:
    return LocalSupervisorManager(
        supervisors_dir=tmp_path / "runs" / "supervisors",
        command_runner=runner or FakeCommandRunner(),
        codex_router=router or FakeCodexRouter(),
    )


def test_local_only_supervisor_completes_without_codex_packet(tmp_path: Path) -> None:
    router = FakeCodexRouter()
    manager = make_manager(tmp_path, router=router)

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_local",
            objective="inspect repo",
            validation_commands=["git_status"],
        )
    )

    run_dir = tmp_path / "runs" / "supervisors" / "supervisor_local"
    assert result.run.status == SupervisorStatus.COMPLETED
    assert router.calls == []
    assert (run_dir / "result.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "local_inspection.json").exists()
    assert (run_dir / "local_plan.json").exists()
    assert (run_dir / "validation_results.json").exists()
    assert (run_dir / "supervisor_report.md").exists()
    assert (run_dir / "resume_prompt.txt").exists()
    assert (run_dir / "pulse_manifest.json").exists()
    manifest = ReportManifest.model_validate_json(
        (run_dir / "pulse_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.ready is True
    assert manifest.source_kind == "supervisor"
    resume = (run_dir / "resume_prompt.txt").read_text(encoding="utf-8")
    assert "CodexBridge supervisor completed." in resume
    assert "codex_invoked: False" in resume


def test_edit_task_creates_codex_packet_without_invocation_by_default(
    tmp_path: Path,
) -> None:
    router = FakeCodexRouter(CodexEscalationStatus.PACKET_READY)
    manager = make_manager(tmp_path, router=router)

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_edit",
            objective="fix failing test",
            validation_commands=["git_status"],
        )
    )

    assert result.run.status == SupervisorStatus.CODEX_PACKET_READY
    assert result.run.codex_invoked is False
    assert result.run.codex_escalation_id is not None
    assert result.run.codex_packet_path is not None
    assert len(router.calls) == 1
    assert router.calls[0].invoke_codex is False
    assert (
        tmp_path / "runs" / "supervisors" / "supervisor_edit" / "codex_packet_ref.json"
    ).exists()


def test_codex_invocation_flag_is_only_passed_when_enabled(tmp_path: Path) -> None:
    router = FakeCodexRouter(CodexEscalationStatus.INVOKED, invoked=True)
    manager = LocalSupervisorManager(
        supervisors_dir=tmp_path / "runs" / "supervisors",
        config=LocalSupervisorConfig(supervisor_codex_invocation_enabled=True),
        command_runner=FakeCommandRunner(),
        codex_router=router,
    )

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_invoke",
            objective="fix failing test",
            validation_commands=["git_status"],
        )
    )

    assert router.calls[0].invoke_codex is True
    assert result.run.codex_invoked is True
    assert result.run.status == SupervisorStatus.COMPLETED
    assert (
        tmp_path
        / "runs"
        / "supervisors"
        / "supervisor_invoke"
        / "post_validation_results.json"
    ).exists()


def test_policy_blocked_sensitive_task_stops_before_validation_and_codex(
    tmp_path: Path,
) -> None:
    runner = FakeCommandRunner()
    router = FakeCodexRouter()
    manager = make_manager(tmp_path, runner=runner, router=router)

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_blocked",
            objective="use API key password to deploy",
            validation_commands=["git_status"],
        )
    )

    run_dir = tmp_path / "runs" / "supervisors" / "supervisor_blocked"
    assert result.run.status == SupervisorStatus.BLOCKED
    assert runner.calls == []
    assert router.calls == []
    assert "REDACTED" in (run_dir / "result.json").read_text(encoding="utf-8")
    assert (
        "password"
        not in (run_dir / "resume_prompt.txt").read_text(encoding="utf-8").lower()
    )


def test_unknown_validation_command_is_rejected_without_execution(
    tmp_path: Path,
) -> None:
    runner = FakeCommandRunner()
    manager = make_manager(tmp_path, runner=runner)

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_unknown_command",
            objective="inspect repo",
            validation_commands=["unknown_command"],
        )
    )

    assert result.run.status == SupervisorStatus.NEEDS_INPUT
    assert runner.calls == []
    assert result.run.validation_results[0]["status"] == "blocked"
    assert result.run.validation_results[0]["error"] == "unknown_validation_command"


def test_cancel_and_resume_are_status_oriented(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_cancel",
            objective="inspect repo",
            validation_commands=["git_status"],
        )
    )

    cancelled = manager.cancel("supervisor_cancel")
    resumed = manager.resume("supervisor_cancel")

    assert cancelled.run.status == SupervisorStatus.CANCELLED
    assert resumed.run.status == SupervisorStatus.CANCELLED
    assert (
        tmp_path / "runs" / "supervisors" / "supervisor_cancel" / "pulse_manifest.json"
    ).exists()


def test_supervisor_package_introduces_no_pulsesender_browser_or_subprocess_imports() -> (
    None
):
    package = Path("codexbridge/supervisor")
    text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    assert "PulseSender" not in text
    assert "playwright" not in text
    assert "selenium" not in text
    assert "subprocess" not in text
