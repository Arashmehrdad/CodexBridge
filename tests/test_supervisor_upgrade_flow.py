from __future__ import annotations

from pathlib import Path

import pytest

from soma.external_coder.models import (
    ExternalCoderHandoffArtifact,
    ExternalCoderHandoffResult,
    ExternalCoderHandoffStatus,
)
from soma.local_agent.models import (
    CommandRunResult,
    CommandRunStatus,
    PermissionTier,
)
from soma.return_loop.models import ReportManifest
from soma.run_store import utc_now
from soma.supervisor import (
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


class FakeHandoffGenerator:
    def __init__(
        self,
        status: ExternalCoderHandoffStatus = ExternalCoderHandoffStatus.HANDOFF_READY,
        *,
        base_dir: Path | None = None,
    ):
        self.status = status
        self.base_dir = base_dir or Path.cwd() / "runs"
        self.calls = []

    def generate_handoff(self, request):
        self.calls.append(request)
        handoff_dir = (
            self.base_dir / "external_coder_handoffs" / request.handoff_id
        )
        handoff_dir.mkdir(parents=True, exist_ok=True)
        handoff_path = handoff_dir / "handoff.json"
        handoff_path.write_text("{}", encoding="utf-8")
        return ExternalCoderHandoffResult(
            handoff_id=request.handoff_id,
            status=self.status,
            artifacts=ExternalCoderHandoffArtifact(
                handoff_id=request.handoff_id,
                handoff_dir=handoff_dir,
                handoff_json_path=handoff_path,
                prompt_path=handoff_dir / "prompt.txt",
                context_manifest_path=handoff_dir / "context_manifest.json",
                policy_result_path=handoff_dir / "policy_result.json",
            ),
            reasons=["fake_generator"],
            audit_event_id="audit_external_coder",
        )


def make_manager(
    tmp_path: Path, *, runner=None, generator=None
) -> LocalSupervisorManager:
    return LocalSupervisorManager(
        supervisors_dir=tmp_path / "runs" / "supervisors",
        command_runner=runner or FakeCommandRunner(),
        handoff_generator=generator or FakeHandoffGenerator(base_dir=tmp_path / "runs"),
    )


def test_supervisor_requires_explicit_execution_context(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires durable application context"):
        LocalSupervisorManager(
            supervisors_dir=tmp_path / "runs" / "supervisors",
            handoff_generator=FakeHandoffGenerator(base_dir=tmp_path / "runs"),
        )


def test_local_only_supervisor_completes_without_handoff(tmp_path: Path) -> None:
    generator = FakeHandoffGenerator(base_dir=tmp_path / "runs")
    manager = make_manager(tmp_path, generator=generator)

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_local",
            objective="inspect repo",
            validation_commands=["git_status"],
        )
    )

    run_dir = tmp_path / "runs" / "supervisors" / "supervisor_local"
    assert result.run.status == SupervisorStatus.COMPLETED
    assert generator.calls == []
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
    assert "Soma supervisor completed." in resume
    assert "external_coder_invoked: False" in resume


def test_edit_task_reaches_needs_external_coder_with_handoff(tmp_path: Path) -> None:
    generator = FakeHandoffGenerator(base_dir=tmp_path / "runs")
    manager = make_manager(tmp_path, generator=generator)

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_edit",
            objective="fix failing test",
            validation_commands=["git_status"],
        )
    )

    assert result.run.status == SupervisorStatus.NEEDS_EXTERNAL_CODER
    assert result.run.external_coder_handoff_id is not None
    assert result.run.external_coder_handoff_path is not None
    assert len(generator.calls) == 1
    # The handoff request model has no invocation affordance at all.
    assert not hasattr(generator.calls[0], "invoke_codex")
    assert (
        tmp_path
        / "runs"
        / "supervisors"
        / "supervisor_edit"
        / "external_coder_handoff_ref.json"
    ).exists()
    resume = (
        tmp_path / "runs" / "supervisors" / "supervisor_edit" / "resume_prompt.txt"
    ).read_text(encoding="utf-8")
    assert "external_coder_invoked: False" in resume
    assert "manually" in result.run.next_recommended_action


def test_approval_required_handoff_maps_to_approval_status(tmp_path: Path) -> None:
    generator = FakeHandoffGenerator(
        ExternalCoderHandoffStatus.APPROVAL_REQUIRED, base_dir=tmp_path / "runs"
    )
    manager = make_manager(tmp_path, generator=generator)

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_approval",
            objective="fix failing test",
            validation_commands=["git_status"],
        )
    )

    assert result.run.status == SupervisorStatus.APPROVAL_REQUIRED
    assert "handoff" in result.run.next_recommended_action.lower()


def test_blocked_handoff_maps_to_blocked_status(tmp_path: Path) -> None:
    generator = FakeHandoffGenerator(
        ExternalCoderHandoffStatus.BLOCKED, base_dir=tmp_path / "runs"
    )
    manager = make_manager(tmp_path, generator=generator)

    result = manager.start_supervised_task(
        SupervisorTaskRequest(
            supervisor_id="supervisor_handoff_blocked",
            objective="fix failing test",
            validation_commands=["git_status"],
        )
    )

    assert result.run.status == SupervisorStatus.BLOCKED


def test_policy_blocked_sensitive_task_stops_before_validation_and_handoff(
    tmp_path: Path,
) -> None:
    runner = FakeCommandRunner()
    generator = FakeHandoffGenerator(base_dir=tmp_path / "runs")
    manager = make_manager(tmp_path, runner=runner, generator=generator)

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
    assert generator.calls == []
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


def test_legacy_codex_supervisor_statuses_remain_parseable() -> None:
    for legacy in (
        "codex_not_needed",
        "codex_packet_ready",
        "invoking_codex",
        "validating_after_codex",
    ):
        assert SupervisorStatus(legacy).value == legacy


def test_supervisor_package_introduces_no_pulsesender_browser_or_subprocess_imports() -> (
    None
):
    package = Path("soma/supervisor")
    text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    assert "PulseSender" not in text
    assert "playwright" not in text
    assert "selenium" not in text
    assert "subprocess" not in text
