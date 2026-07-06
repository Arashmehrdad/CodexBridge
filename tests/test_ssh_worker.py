from __future__ import annotations

from pathlib import Path

from codexbridge.job_worker import JobWorker
from codexbridge.run_store import RunStore


def test_ssh_command_worker_persists_output(monkeypatch, tmp_path: Path) -> None:
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
                "ssh:",
                "  enabled: true",
                "  hosts:",
                "    my_vps:",
                "      ssh_alias: my-vps",
                "      command_profiles:",
                "        - command_id: uptime",
                "          argv: [uptime]",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260706T000000Z_ssh_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_command",
        run_dir=run_dir,
        input_data={"host_id": "my_vps", "command_id": "uptime"},
    )

    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_command",
        lambda config, host_id, command_id: {
            "ok": True,
            "host_id": host_id,
            "ssh_alias": "my-vps",
            "command_id": command_id,
            "writes_remote": False,
            "remote_state_verified": False,
            "argv": ["ssh.exe", "my-vps", "uptime"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "up 1 day\n",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )
    worker = JobWorker(config_path, run_id)

    assert worker.execute() == 0
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert result["tool"] == "ssh_command"
    assert result["repo_name"] == "ssh:my_vps"
    assert result["host_id"] == "my_vps"
    assert result["command_id"] == "uptime"
    assert result["writes_remote"] is False
    assert result["changed_files"] == []
    assert result["safety_failure"] is False
    assert result["remaining_risks"] == []
    assert (run_dir / "stdout.txt").read_text(encoding="utf-8") == "up 1 day\n"
