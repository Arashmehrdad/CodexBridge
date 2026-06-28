from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codexbridge.jobs.long_run_manager import LongRunJobManager
from codexbridge.jobs.models import JobStatus


class FakeProcess:
    def __init__(self, returncode: int | None = 0):
        self.pid = 4321
        self.returncode = returncode
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


def fake_popen(
    returncode: int | None = 0,
    stdout_text: str = "out\n",
    stderr_text: str = "",
    artifact: bool = False,
):
    calls: list[dict[str, Any]] = []

    def factory(argv: list[str], **kwargs: Any) -> FakeProcess:
        calls.append({"argv": argv, **kwargs})
        kwargs["stdout"].write(stdout_text)
        kwargs["stdout"].flush()
        kwargs["stderr"].write(stderr_text)
        kwargs["stderr"].flush()
        if artifact:
            artifacts = Path(kwargs["cwd"]) / "artifacts"
            artifacts.mkdir(exist_ok=True)
            (artifacts / "out.txt").write_text("artifact", encoding="utf-8")
            (artifacts / ".env").write_text("SECRET=value", encoding="utf-8")
        return FakeProcess(returncode)

    return factory, calls


def test_unknown_job_profile_is_blocked_and_does_not_call_subprocess(
    tmp_path: Path,
) -> None:
    factory, calls = fake_popen()
    result = LongRunJobManager(
        runs_dir=tmp_path / "runs", popen_factory=factory
    ).start_job(profile_id="missing", repo_path=tmp_path)

    assert result.job.status == JobStatus.PROFILE_MISSING
    assert calls == []


def test_disabled_job_profile_is_blocked(tmp_path: Path) -> None:
    factory, calls = fake_popen()
    result = LongRunJobManager(
        runs_dir=tmp_path / "runs", popen_factory=factory
    ).start_job(profile_id="disabled_demo", repo_path=tmp_path)

    assert result.job.status == JobStatus.BLOCKED
    assert calls == []


def test_arbitrary_shell_like_profile_text_is_rejected(tmp_path: Path) -> None:
    factory, calls = fake_popen()
    result = LongRunJobManager(
        runs_dir=tmp_path / "runs", popen_factory=factory
    ).start_job(profile_id="python -c import os", repo_path=tmp_path)

    assert result.job.status == JobStatus.PROFILE_MISSING
    assert calls == []


def test_missing_repo_path_is_handled_cleanly(tmp_path: Path) -> None:
    factory, calls = fake_popen()
    result = LongRunJobManager(
        runs_dir=tmp_path / "runs", popen_factory=factory
    ).start_job(profile_id="dummy_success", repo_path=tmp_path / "missing")

    assert result.job.status == JobStatus.REPO_MISSING
    assert result.job.error
    assert calls == []


def test_timeout_escalation_above_profile_limit_is_rejected(tmp_path: Path) -> None:
    factory, calls = fake_popen()
    result = LongRunJobManager(
        runs_dir=tmp_path / "runs", popen_factory=factory
    ).start_job(profile_id="dummy_success", repo_path=tmp_path, timeout_seconds=31)

    assert result.job.status == JobStatus.PERMISSION_DENIED
    assert "timeout" in result.job.error.lower()
    assert calls == []


def test_start_job_creates_artifacts_and_initial_result(tmp_path: Path) -> None:
    factory, calls = fake_popen(returncode=None)
    result = LongRunJobManager(
        runs_dir=tmp_path / "runs", popen_factory=factory
    ).start_job(profile_id="dummy_success", repo_path=tmp_path)

    assert result.job.status == JobStatus.RUNNING
    assert result.job.result_json_path.match("*/runs/jobs/*/result.json")
    assert result.job.events_path.exists()
    assert result.job.stdout_path.exists()
    assert result.job.stderr_path.exists()
    assert calls[0]["shell"] is False
    payload = json.loads(result.job.result_json_path.read_text(encoding="utf-8"))
    assert payload["job_id"] == result.job.job_id
    assert payload["job_profile"] == "dummy_success"
    assert payload["status"] == "running"
    assert payload["working_directory"] == str(tmp_path.resolve())
    assert payload["argv"]
    assert payload["audit_event_id"]


def test_successful_job_transitions_to_completed_and_reported(tmp_path: Path) -> None:
    factory, _calls = fake_popen(returncode=0, stdout_text="done\n", artifact=True)
    manager = LongRunJobManager(runs_dir=tmp_path / "runs", popen_factory=factory)
    start = manager.start_job(profile_id="dummy_success", repo_path=tmp_path)
    result = manager.refresh_status(start.job.job_id)

    assert result.job.status == JobStatus.COMPLETED
    assert result.job.exit_code == 0
    assert result.job.stdout_path.read_text(encoding="utf-8") == "done\n"
    assert (result.job.result_json_path.parent / "job_report.md").exists()
    assert (result.job.result_json_path.parent / "resume_prompt.txt").exists()
    assert any(path.name == "out.txt" for path in result.job.artifact_paths)
    assert not any(path.name == ".env" for path in result.job.artifact_paths)


def test_failing_job_transitions_to_failed(tmp_path: Path) -> None:
    factory, _calls = fake_popen(returncode=2, stderr_text="failed\n")
    manager = LongRunJobManager(runs_dir=tmp_path / "runs", popen_factory=factory)
    start = manager.start_job(profile_id="dummy_failure", repo_path=tmp_path)
    result = manager.refresh_status(start.job.job_id)

    assert result.job.status == JobStatus.FAILED
    assert result.job.exit_code == 2
    assert "non-zero" in result.job.failure_summary
    assert result.job.stderr_path.read_text(encoding="utf-8") == "failed\n"


def test_timeout_job_transitions_to_timeout(tmp_path: Path) -> None:
    factory, _calls = fake_popen(returncode=None)
    manager = LongRunJobManager(runs_dir=tmp_path / "runs", popen_factory=factory)
    start = manager.start_job(profile_id="dummy_timeout", repo_path=tmp_path)
    manager.processes[start.job.job_id]._codexbridge_started_monotonic -= 2
    result = manager.refresh_status(start.job.job_id)

    assert result.job.status == JobStatus.TIMEOUT
    assert result.job.exit_code is None
    assert "timed out" in result.job.failure_summary


def test_cancel_job_transitions_to_cancelled(tmp_path: Path) -> None:
    factory, _calls = fake_popen(returncode=None)
    manager = LongRunJobManager(runs_dir=tmp_path / "runs", popen_factory=factory)
    start = manager.start_job(profile_id="sleep_short", repo_path=tmp_path)
    cancel = manager.cancel_job(start.job.job_id)
    status = manager.get_status(start.job.job_id)

    assert cancel.status == JobStatus.CANCELLED
    assert status.job.status == JobStatus.CANCELLED
    assert (status.job.result_json_path.parent / "job_report.md").exists()
    assert (status.job.result_json_path.parent / "resume_prompt.txt").exists()


def test_list_jobs_and_get_status_return_known_jobs(tmp_path: Path) -> None:
    factory, _calls = fake_popen(returncode=None)
    manager = LongRunJobManager(runs_dir=tmp_path / "runs", popen_factory=factory)
    start = manager.start_job(profile_id="dummy_success", repo_path=tmp_path)

    assert manager.get_status(start.job.job_id).job.job_id == start.job.job_id
    assert [job.job_id for job in manager.list_jobs()] == [start.job.job_id]


def test_refresh_status_does_not_block_for_running_job(tmp_path: Path) -> None:
    factory, _calls = fake_popen(returncode=None)
    manager = LongRunJobManager(runs_dir=tmp_path / "runs", popen_factory=factory)
    start = manager.start_job(profile_id="sleep_short", repo_path=tmp_path)
    result = manager.refresh_status(start.job.job_id)

    assert result.job.status == JobStatus.RUNNING


def test_job_modules_do_not_import_codex_pulsesender_browser_or_ollama() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("codexbridge/jobs").glob("*.py")
    )

    assert "CodexRunner" not in source
    assert "import PulseSender" not in source
    assert "from PulseSender" not in source
    assert "playwright" not in source.lower()
    assert "selenium" not in source.lower()
    assert "ollama" not in source.lower()
