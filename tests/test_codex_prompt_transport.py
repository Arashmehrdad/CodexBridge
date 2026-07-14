from __future__ import annotations

from pathlib import Path

from codexbridge.job_worker import JobWorker
from codexbridge.run_store import RunStore


class FakePipe:
    def readline(self) -> str:
        return ""

    def close(self) -> None:
        return None


class FakeProcess:
    pid = 2468
    stdout = FakePipe()
    stderr = FakePipe()

    def wait(self, timeout=None) -> int:
        return 0


def test_durable_codex_worker_uses_file_stdin_and_isolated_environment(
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
    run_id = "20260714T000000Z_codex_plan_task_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    task = "Inspect the bridge\nConfirm prompt transport"
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="codex_plan_task",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "task": task,
            "constraints": "Do not edit files",
        },
    )

    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._resolve_codex_executable",
        lambda self: "codex.exe",
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.CodexRunner._codex_exec_help",
        lambda self, _executable: "--sandbox",
    )
    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = list(args)
        captured["stdin_text"] = kwargs["stdin"].read()
        captured["env"] = dict(kwargs["env"])
        return FakeProcess()

    monkeypatch.setattr("codexbridge.job_worker.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "codexbridge.job_worker._stream_pipe",
        lambda pipe, output_path, sink, limit=40000, on_output=None: sink.extend(
            ["Bridge inspection complete\n", "PLAN_STATUS: ready\n"]
            if output_path.name == "stdout.txt"
            else []
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
        "codexbridge.job_worker.git_tools.changed_files", lambda _repo_root: []
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.git_status", lambda _repo_root: ""
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.git_tools.diff_stat", lambda _repo_root: ""
    )
    monkeypatch.setenv("MCP_FAKE_CONNECTOR", "must-not-leak")

    assert JobWorker(config_path, run_id).execute() == 0

    env = captured["env"]
    assert captured["args"][-1] == "-"
    assert task in captured["stdin_text"]
    assert "PLAN-ONLY mode" in captured["stdin_text"]
    assert "MCP_FAKE_CONNECTOR" not in env
    assert env["CODEXBRIDGE_CONNECTOR_ISOLATION"] == "enabled"
    assert env["TMP"] == str(run_dir / "tmp")
    assert store.get_run(run_id)["status"] == "completed"
