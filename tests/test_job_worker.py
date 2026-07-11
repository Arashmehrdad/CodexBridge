from __future__ import annotations

import subprocess
from pathlib import Path

from codexbridge.job_worker import JobWorker
from codexbridge.run_store import RunStore, utc_now


def write_config(
    config_path: Path, repo: Path, runs_dir: Path, extra_lines: list[str] | None = None
) -> None:
    lines = [
        "repos:",
        "  sample:",
        f'    path: "{repo.as_posix()}"',
    ]
    if extra_lines:
        lines.extend(extra_lines)
    lines.append(f'runs_dir: "{runs_dir.as_posix()}"')
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_fake_codex_process(monkeypatch, run_dir: Path, output: str) -> None:
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._resolve_codex_executable",
        lambda self: "codex",
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._codex_exec_help",
        lambda self, _executable: "",
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._codex_exec_args",
        lambda self, _executable, _sandbox, _help_text, _prompt, writable_dirs=None: [
            "codex"
        ],
    )

    class FakePipe:
        def readline(self) -> str:
            return ""

        def close(self) -> None:
            return None

    class FakeProcess:
        pid = 123
        stdout = FakePipe()
        stderr = FakePipe()

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(
        "codexbridge.job_worker.subprocess.Popen", lambda *args, **kwargs: FakeProcess()
    )
    (run_dir / "stdout.txt").write_text(output, encoding="utf-8")
    monkeypatch.setattr(
        "codexbridge.job_worker._stream_pipe",
        lambda pipe, output_path, sink, limit=40000, on_output=None: sink.extend(
            output_path.read_text(encoding="utf-8").splitlines(keepends=True)
            if output_path.exists()
            else []
        ),
    )


def test_blocked_zero_exit_run_is_persisted_as_failed(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260629T000000Z_codex_implement_task_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="codex_implement_task",
        run_dir=run_dir,
        input_data={"repo_name": "sample"},
    )
    worker = JobWorker(config_path, run_id)
    result = {
        "run_id": run_id,
        "repo_name": "sample",
        "tool": "codex_implement_task",
        "status": "failed",
        "exit_code": 0,
        "started_at": utc_now(),
        "ended_at": utc_now(),
        "duration_seconds": 0.0,
        "changed_files": [],
        "git_status": "## main\n",
        "diff_stat": "",
        "tests_run": [],
        "test_results": "",
        "summary": "Access to the path is denied.",
        "remaining_risks": ["Codex final response reports an implementation blocker"],
        "blocked": True,
        "blockers": ["Codex final response reports an implementation blocker"],
        "error": "Codex final response reports an implementation blocker",
        "safety_failure": False,
    }
    monkeypatch.setattr(worker, "_execute_inner", lambda _started_at: result)

    assert worker.execute() == 1
    persisted = store.get_run(run_id)
    assert persisted["status"] == "failed"
    assert persisted["exit_code"] == 0
    assert persisted["error"]


def test_project_command_worker_persists_output_and_isolates_pytest(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260701T000000Z_project_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )
    captured: dict = {}

    def fake_run(profile, cwd, *, extra_env=None):
        captured["profile"] = profile
        captured["cwd"] = cwd
        captured["extra_env"] = dict(extra_env or {})
        return {
            "ok": True,
            "command_id": "pytest",
            "argv": ["python", "-m", "pytest", "-q"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "1 passed\n",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_worker.run_command_profile", fake_run)
    monkeypatch.setattr("codexbridge.job_worker.git_tools.git_status", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.diff_stat", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.changed_files", lambda _: [])
    worker = JobWorker(config_path, run_id)

    assert worker.execute() == 0
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert result["command_id"] == "pytest"
    assert result["timed_out"] is False
    assert Path(result["temporary_directory"]).is_dir()
    assert Path(result["pytest_basetemp"]).is_dir()
    assert captured["cwd"] == repo
    assert captured["extra_env"]["TMP"] == result["temporary_directory"]
    assert "--basetemp=" in captured["extra_env"]["PYTEST_ADDOPTS"]
    assert (run_dir / "stdout.txt").read_text(encoding="utf-8") == "1 passed\n"


def test_docker_action_worker_persists_bounded_result(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "docker-compose.yml").write_text(
        "services:\n  api:\n    image: example/api\n", encoding="utf-8"
    )
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_config(
        config_path,
        repo,
        runs_dir,
        extra_lines=["docker:", "  enabled: true"],
    )
    run_id = "20260701T000000Z_docker_action_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="docker_action",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "action": "compose_up",
            "services": ["api"],
            "build": True,
        },
    )
    captured = {}

    def fake_run(config, repo_root, repo_config, action, **kwargs):
        captured["action"] = action
        captured["kwargs"] = kwargs
        return {
            "ok": True,
            "action": action,
            "argv": ["docker", "compose", "up", "--detach", "api"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "started\n",
            "stderr": "",
            "output_truncated": False,
            "high_risk": False,
            "writes_files": False,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_worker.run_docker_action", fake_run)
    monkeypatch.setattr("codexbridge.job_worker.git_tools.git_status", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.diff_stat", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.changed_files", lambda _: [])
    worker = JobWorker(config_path, run_id)

    assert worker.execute() == 0
    result = store.get_run(run_id)["result"]
    assert result["status"] == "completed"
    assert result["tool"] == "docker_action"
    assert result["action"] == "compose_up"
    assert result["high_risk"] is False
    assert captured["kwargs"]["services"] == ["api"]
    assert (run_dir / "stdout.txt").read_text(encoding="utf-8") == "started\n"


def test_project_command_worker_rebuilds_scoped_pytest_profile(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    target_file = repo / "tests" / "test_api.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260701T000000Z_project_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "command_id": "pytest_path",
            "path": r"tests\test_api.py::test_ok",
        },
    )
    captured: dict = {}

    def fake_run(profile, cwd, *, extra_env=None):
        captured["profile"] = profile
        captured["cwd"] = cwd
        captured["extra_env"] = dict(extra_env or {})
        return {
            "ok": True,
            "command_id": "pytest_path",
            "argv": list(profile.argv),
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "1 passed\n",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_worker.run_command_profile", fake_run)
    monkeypatch.setattr("codexbridge.job_worker.git_tools.git_status", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.diff_stat", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.changed_files", lambda _: [])
    worker = JobWorker(config_path, run_id)

    assert worker.execute() == 0
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert captured["cwd"] == repo
    assert captured["profile"].argv == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_api.py::test_ok",
    ]
    assert captured["extra_env"]["TMP"] == result["temporary_directory"]
    assert "--basetemp=" in captured["extra_env"]["PYTEST_ADDOPTS"]
    assert result["command_id"] == "pytest_path"
    assert result["path"] == "tests/test_api.py::test_ok"
    assert result["tests_run"] == ["pytest_path:tests/test_api.py::test_ok"]
    assert result["argv"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_api.py::test_ok",
    ]


def test_project_command_worker_reports_only_introduced_changes(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    existing = repo / "preexisting.txt"
    existing.write_text("dirty\n", encoding="utf-8")
    target = repo / "generated.txt"
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260701T000001Z_project_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={"repo_name": "sample", "command_id": "git_status"},
    )

    def fake_run(profile, cwd, *, extra_env=None):
        target.write_text("new\n", encoding="utf-8")
        return {
            "ok": True,
            "command_id": "git_status",
            "argv": list(profile.argv),
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_worker.run_command_profile", fake_run)
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.git_status",
        lambda _: " M preexisting.txt\n?? generated.txt\n",
    )
    monkeypatch.setattr("codexbridge.job_worker.git_tools.diff_stat", lambda _: "")
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.changed_files",
        lambda _: ["preexisting.txt", "generated.txt"],
    )

    worker = JobWorker(config_path, run_id)
    worker.execute()
    result = store.get_run(run_id)["result"]

    assert result["changed_files"] == ["generated.txt"]
    assert result["preserved_preexisting_changes"] == ["preexisting.txt"]


def test_project_command_worker_resolves_profiles_case_insensitively(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "    command_profiles:",
                "      - command_id: custom",
                '        argv: ["python", "-c", "print(1)"]',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260701T000002Z_project_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="Sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={"repo_name": "Sample", "command_id": "custom"},
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.run_command_profile",
        lambda profile, cwd, *, extra_env=None: {
            "ok": True,
            "command_id": "custom",
            "argv": list(profile.argv),
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )
    monkeypatch.setattr("codexbridge.job_worker.git_tools.git_status", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.diff_stat", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.changed_files", lambda _: [])

    worker = JobWorker(config_path, run_id)

    assert worker.execute() == 0
    result = store.get_run(run_id)["result"]
    assert result["repo_name"] == "Sample"
    assert result["command_id"] == "custom"


def test_implementation_worker_requires_all_manifest_ids_to_finish_completed(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260701T000003Z_codex_implement_task_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="codex_implement_task",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "approved_plan": "REQ-001 one\nREQ-002 two",
            "allowed_files": ["README.md"],
            "tests": ["python -m pytest -q"],
            "requirement_manifest": [
                {"requirement_id": "REQ-001", "text": "REQ-001 one", "mandatory": True},
                {"requirement_id": "REQ-002", "text": "REQ-002 two", "mandatory": True},
            ],
        },
    )
    worker = JobWorker(config_path, run_id)
    monkeypatch.setattr("codexbridge.job_worker.git_tools.git_status", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.diff_stat", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.changed_files", lambda _: [])
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_managed_artifacts", lambda _repo_root: set()
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.cleanup_new_managed_artifacts",
        lambda _repo_root, _before: [],
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_workspace", lambda _repo_root, _ignored=(): {}
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._resolve_codex_executable",
        lambda self: "codex",
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._codex_exec_help",
        lambda self, _executable: "",
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._codex_exec_args",
        lambda self, _executable, _sandbox, _help_text, _prompt, writable_dirs=None: [
            "codex"
        ],
    )

    class FakePipe:
        def readline(self) -> str:
            return ""

        def close(self) -> None:
            return None

    class FakeProcess:
        pid = 123
        stdout = FakePipe()
        stderr = FakePipe()

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(
        "codexbridge.job_worker.subprocess.Popen", lambda *args, **kwargs: FakeProcess()
    )
    (run_dir / "stdout.txt").write_text(
        "\n".join(
            [
                "COMPLETED_REQUIREMENT: REQ-001 one",
                "VALIDATION_STATUS: passed",
                "FINAL_STATUS: completed",
                "PLAN_CONFORMANCE: yes",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "codexbridge.job_worker._stream_pipe",
        lambda pipe, output_path, sink, limit=40000, on_output=None: sink.extend(
            output_path.read_text(encoding="utf-8").splitlines(keepends=True)
            if output_path.exists()
            else []
        ),
    )

    assert worker.execute() == 0
    persisted = store.get_run(run_id)
    assert persisted["status"] == "partial"
    assert persisted["result"]["missing_requirements"] == ["REQ-002"]
    assert persisted["result"]["mandatory_incomplete"] == ["REQ-002"]


def test_implementation_worker_finalizes_commit_after_success(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_config(config_path, repo, runs_dir)
    run_id = "20260707T000001Z_codex_implement_task_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="codex_implement_task",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "approved_plan": "Update README",
            "allowed_files": ["README.md"],
            "tests": ["python -m pytest -q"],
        },
    )
    install_fake_codex_process(
        monkeypatch,
        run_dir,
        "\n".join(
            [
                "VALIDATION_STATUS: passed",
                "FINAL_STATUS: completed",
                "PLAN_CONFORMANCE: yes",
                "BLOCKERS: none",
            ]
        ),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_managed_artifacts", lambda _repo_root: set()
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.cleanup_new_managed_artifacts",
        lambda _repo_root, _before: [],
    )
    workspace_sequences = iter([{}, {"README.md": (1, 2)}])
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_workspace",
        lambda _repo_root, _ignored=(): next(workspace_sequences),
    )
    changed_sequences = iter([[], ["README.md"], []])
    status_sequences = iter(["", " M README.md\n", ""])
    diff_sequences = iter([" README.md | 1 +\n", ""])
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.changed_files",
        lambda _repo_root: next(changed_sequences),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.git_status",
        lambda _repo_root: next(status_sequences),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.diff_stat",
        lambda _repo_root: next(diff_sequences),
    )
    captured: dict[str, object] = {}

    def fake_finalize(
        self, repo_root: Path, changed_files: list[str], *, tool_name: str
    ):
        captured["changed_files"] = list(changed_files)
        captured["tool_name"] = tool_name
        return {
            "commit_required": True,
            "commit_attempted": True,
            "commit_hash": "a" * 40,
            "commit_error": "",
            "commit_result": {
                "ok": True,
                "remaining_dirty_files": [],
                "git_status": "",
            },
        }

    monkeypatch.setattr(JobWorker, "_finalize_commit", fake_finalize)

    worker = JobWorker(config_path, run_id)
    assert worker.execute() == 0
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert captured["changed_files"] == ["README.md"]
    assert captured["tool_name"] == "codex_implement_task"
    assert result["commit_attempted"] is True
    assert result["commit_hash"] == "a" * 40
    assert result["git_status"] == ""
    assert result["diff_stat"] == ""


def test_implementation_worker_validation_failure_does_not_commit(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_config(config_path, repo, runs_dir)
    run_id = "20260707T000002Z_codex_implement_task_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="codex_implement_task",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "approved_plan": "Update README",
            "allowed_files": ["README.md"],
            "tests": ["python -m pytest -q"],
        },
    )
    install_fake_codex_process(
        monkeypatch,
        run_dir,
        "\n".join(
            [
                "VALIDATION_STATUS: failed",
                "FINAL_STATUS: completed",
                "PLAN_CONFORMANCE: yes",
                "BLOCKERS: none",
            ]
        ),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_managed_artifacts", lambda _repo_root: set()
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.cleanup_new_managed_artifacts",
        lambda _repo_root, _before: [],
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_workspace", lambda _repo_root, _ignored=(): {}
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.changed_files",
        lambda _repo_root: [] if not hasattr(_repo_root, "unused") else [],
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.git_status", lambda _repo_root: ""
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.diff_stat", lambda _repo_root: ""
    )

    def unexpected_finalize(*args, **kwargs):
        raise AssertionError("finalize should not be called")

    monkeypatch.setattr(JobWorker, "_finalize_commit", unexpected_finalize)

    worker = JobWorker(config_path, run_id)
    assert worker.execute() == 1
    persisted = store.get_run(run_id)
    assert persisted["status"] == "failed"
    assert persisted["result"]["commit_attempted"] is False
    assert "VALIDATION_STATUS: failed" in persisted["result"]["error"]


def test_implementation_worker_commit_failure_prevents_completed_status(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_config(config_path, repo, runs_dir)
    run_id = "20260707T000003Z_codex_implement_task_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="codex_implement_task",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "approved_plan": "Update README",
            "allowed_files": ["README.md"],
            "tests": ["python -m pytest -q"],
        },
    )
    install_fake_codex_process(
        monkeypatch,
        run_dir,
        "\n".join(
            [
                "VALIDATION_STATUS: passed",
                "FINAL_STATUS: completed",
                "PLAN_CONFORMANCE: yes",
                "BLOCKERS: none",
            ]
        ),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_managed_artifacts", lambda _repo_root: set()
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.cleanup_new_managed_artifacts",
        lambda _repo_root, _before: [],
    )
    workspace_sequences = iter([{}, {"README.md": (1, 2)}])
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_workspace",
        lambda _repo_root, _ignored=(): next(workspace_sequences),
    )
    changed_sequences = iter([[], ["README.md"], ["README.md"]])
    status_sequences = iter(["", " M README.md\n", " M README.md\n"])
    diff_sequences = iter(["", " README.md | 1 +\n", " README.md | 1 +\n"])
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.changed_files",
        lambda _repo_root: next(changed_sequences),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.git_status",
        lambda _repo_root: next(status_sequences),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.diff_stat",
        lambda _repo_root: next(diff_sequences),
    )
    monkeypatch.setattr(
        JobWorker,
        "_finalize_commit",
        lambda self, repo_root, changed_files, *, tool_name: {
            "commit_required": True,
            "commit_attempted": True,
            "commit_hash": "",
            "commit_error": "simulated commit failure",
            "commit_result": {"ok": False},
        },
    )

    worker = JobWorker(config_path, run_id)
    assert worker.execute() == 1
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "failed"
    assert result["error"] == "simulated commit failure"
    assert "Automatic commit finalization failed" in result["remaining_risks"][0]


def test_project_command_worker_commits_only_for_write_profiles(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_config(
        config_path,
        repo,
        runs_dir,
        [
            "    command_profiles:",
            "      - command_id: writer",
            '        argv: ["python", "-c", "print(1)"]',
            "        writes_files: true",
            "      - command_id: reader",
            '        argv: ["python", "-c", "print(1)"]',
            "        writes_files: false",
        ],
    )
    store = RunStore(runs_dir)
    writer_run_id = "20260707T000004Z_project_command_deadbeef"
    writer_run_dir = runs_dir / writer_run_id
    writer_run_dir.mkdir(parents=True)
    store.create_run(
        run_id=writer_run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=writer_run_dir,
        input_data={"repo_name": "sample", "command_id": "writer"},
    )
    reader_run_id = "20260707T000005Z_project_command_deadbeef"
    reader_run_dir = runs_dir / reader_run_id
    reader_run_dir.mkdir(parents=True)
    store.create_run(
        run_id=reader_run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=reader_run_dir,
        input_data={"repo_name": "sample", "command_id": "reader"},
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.run_command_profile",
        lambda profile, cwd, *, extra_env=None: {
            "ok": True,
            "command_id": profile.command_id,
            "argv": list(profile.argv),
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )
    workspace_sequences = iter(
        [
            {},
            {"generated.txt": (1, 2)},
            {},
            {},
        ]
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_workspace",
        lambda _repo_root, _ignored=(): next(workspace_sequences),
    )
    changed_sequences = iter([[], ["generated.txt"], [], [], []])
    status_sequences = iter(["", " M generated.txt\n", "", "", ""])
    diff_sequences = iter(["", " generated.txt | 1 +\n", "", "", ""])
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.changed_files",
        lambda _repo_root: next(changed_sequences),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.git_status",
        lambda _repo_root: next(status_sequences),
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.diff_stat",
        lambda _repo_root: next(diff_sequences),
    )
    calls: list[tuple[str, list[str]]] = []

    def fake_finalize(
        self, repo_root: Path, changed_files: list[str], *, tool_name: str
    ):
        calls.append((tool_name, list(changed_files)))
        return {
            "commit_required": True,
            "commit_attempted": True,
            "commit_hash": "b" * 40,
            "commit_error": "",
            "commit_result": {"ok": True},
        }

    monkeypatch.setattr(JobWorker, "_finalize_commit", fake_finalize)

    assert JobWorker(config_path, writer_run_id).execute() == 0
    assert JobWorker(config_path, reader_run_id).execute() == 0

    writer_result = store.get_run(writer_run_id)["result"]
    reader_result = store.get_run(reader_run_id)["result"]
    assert calls == [("project_command", ["generated.txt"])]
    assert writer_result["commit_attempted"] is True
    assert reader_result["commit_attempted"] is False


def test_codex_timeout_terminates_process_tree_and_records_report(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_config(config_path, repo, runs_dir)
    run_id = "20260707T000006Z_codex_plan_task_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="codex_plan_task",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "task": "Inspect documentation",
            "constraints": "",
        },
    )

    class FakePipe:
        def readline(self) -> str:
            return ""

        def close(self) -> None:
            return None

    class TimedOutProcess:
        pid = 4321
        stdout = FakePipe()
        stderr = FakePipe()

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("codex", timeout)

    popen_kwargs: dict[str, object] = {}

    def fake_popen(*args, **kwargs):
        popen_kwargs.update(kwargs)
        return TimedOutProcess()

    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._resolve_codex_executable",
        lambda self: "codex",
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._codex_exec_help",
        lambda self, _executable: "",
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._codex_exec_args",
        lambda self, _executable, _sandbox, _help_text, _prompt, writable_dirs=None: [
            "codex"
        ],
    )
    monkeypatch.setattr("codexbridge.job_worker.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "codexbridge.job_worker.process_group_popen_kwargs",
        lambda: {"creationflags": 512},
    )
    terminations: list[int] = []
    monkeypatch.setattr(
        "codexbridge.job_worker.terminate_process_tree",
        lambda pid: terminations.append(pid)
        or {
            "pid": pid,
            "method": "simulated_tree",
            "termination_attempted": True,
            "forced": True,
            "exit_code": 0,
            "terminated": True,
            "error": "",
        },
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_managed_artifacts", lambda _repo_root: set()
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.cleanup_new_managed_artifacts",
        lambda _repo_root, _before: [],
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.snapshot_workspace", lambda _repo_root, _ignored=(): {}
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.changed_files", lambda _repo_root: []
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.git_status", lambda _repo_root: ""
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.diff_stat", lambda _repo_root: ""
    )

    worker = JobWorker(config_path, run_id)

    assert worker.execute() == 124
    result = store.get_run(run_id)["result"]
    events = store.get_events(run_id, 50)
    assert popen_kwargs["creationflags"] == 512
    assert terminations == [4321]
    assert result["status"] == "timed_out"
    assert result["codex_exit_code"] == 124
    timeout_event = next(event for event in events if event["stage"] == "codex" and "timed out" in event["message"])
    assert timeout_event["data"]["termination"]["terminated"] is True
