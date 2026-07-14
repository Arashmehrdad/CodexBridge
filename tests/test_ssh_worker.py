from __future__ import annotations

from pathlib import Path

import pytest

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
        input_data={
            "host_id": "my_vps",
            "command_id": "uptime",
            "autonomy_profile": "chatgpt_delegated",
            "execution_mode": "structured",
            "permission_tier": "T0_READ_ONLY",
            "policy_decision": "allowed",
            "policy_authorized": True,
            "approval_source": "none",
        },
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
    assert result["autonomy_profile"] == "chatgpt_delegated"
    assert result["execution_mode"] == "structured"
    assert result["permission_tier"] == "T0_READ_ONLY"
    assert result["policy_decision"] == "allowed"
    assert result["policy_authorized"] is True
    assert result["approval_source"] == "none"
    assert result["writes_remote"] is False
    assert result["changed_files"] == []
    assert result["safety_failure"] is False
    assert result["remaining_risks"] == []
    assert (run_dir / "stdout.txt").read_text(encoding="utf-8") == "up 1 day\n"


def write_extended_ssh_config(config_path: Path, repo: Path, runs_dir: Path) -> None:
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "ssh:",
                "  enabled: true",
                "  allow_transfer: true",
                "  allow_deploy: true",
                "  allow_admin: true",
                "  hosts:",
                "    my_vps:",
                "      ssh_alias: my-vps",
                "      allowed_remote_roots: [/srv/app, /var/log]",
                "      allowed_executables: [docker, git, curl]",
                "      deployment_profiles:",
                "        sample_app:",
                "          repo_name: sample",
                "          remote_root: /srv/app",
                "          compose_file: docker-compose.yml",
                "      command_profiles:",
                "        - command_id: uptime",
                "          argv: [uptime]",
                "          watchdog_eligible: true",
                "        - command_id: write_marker",
                "          argv: [touch, /tmp/codexbridge-marker]",
                "          writes_remote: true",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("tool", "input_data", "executor_name", "message_category"),
    [
        (
            "ssh_command",
            {
                "host_id": "my_vps",
                "command_id": "uptime",
                "autonomy_profile": "readonly",
                "execution_mode": "reviewed_script",
            },
            "run_ssh_command",
            "denied",
        ),
        (
            "ssh_monitored_command",
            {
                "host_id": "my_vps",
                "command_id": "uptime",
                "autonomy_profile": "chatgpt_delegated",
                "execution_mode": "reviewed_script",
            },
            "start_monitored_ssh_command",
            "not implemented",
        ),
        (
            "ssh_action",
            {
                "host_id": "my_vps",
                "action": "service_restart",
                "autonomy_profile": "permissive",
                "execution_mode": "root_shell",
            },
            "run_ssh_action",
            "not implemented",
        ),
    ],
)
def test_ssh_worker_revalidates_policy_before_executor(
    monkeypatch,
    tmp_path: Path,
    tool: str,
    input_data: dict,
    executor_name: str,
    message_category: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T010000Z_ssh_policy_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool=tool,
        run_dir=run_dir,
        input_data=input_data,
    )
    executor_called = False

    def unexpected_executor(*args, **kwargs):
        nonlocal executor_called
        executor_called = True
        raise AssertionError("SSH executor must not run after policy rejection")

    monkeypatch.setattr(
        f"codexbridge.job_worker.{executor_name}", unexpected_executor
    )

    assert JobWorker(config_path, run_id).execute() == 1
    persisted = store.get_run(run_id)
    assert persisted["status"] == "failed"
    assert message_category in persisted["result"]["error"]
    assert persisted["result"]["safety_failure"] is True
    assert executor_called is False


@pytest.mark.parametrize(
    ("tool", "input_data", "executor_name", "message_category"),
    [
        (
            "ssh_command",
            {
                "host_id": "my_vps",
                "command_id": "uptime",
                "autonomy_profile": "chatgpt_delegated",
                "execution_mode": "structured",
                "permission_tier": "T4_WRITE_APPLY_CHATGPT_DELEGATED",
                "policy_decision": "allowed",
                "policy_authorized": True,
                "approval_source": "none",
            },
            "run_ssh_command",
            "does not match canonical",
        ),
        (
            "ssh_command",
            {
                "host_id": "my_vps",
                "command_id": "write_marker",
                "autonomy_profile": "chatgpt_delegated",
                "execution_mode": "structured",
                "permission_tier": "T4_WRITE_APPLY_CHATGPT_DELEGATED",
                "policy_decision": "needs_chatgpt_approval",
                "policy_authorized": True,
                "approval_source": "none",
            },
            "run_ssh_command",
            "requires ChatGPT",
        ),
        (
            "ssh_action",
            {
                "host_id": "my_vps",
                "action": "service_stop",
                "target": "sample.service",
                "confirmation": "CONFIRM_SSH_HIGH_RISK",
                "autonomy_profile": "permissive",
                "execution_mode": "structured",
                "permission_tier": "T6_HUMAN_ONLY_RISKY_ACTION",
                "policy_decision": "needs_human_approval",
                "policy_authorized": True,
                "approval_source": "chatgpt",
            },
            "run_ssh_action",
            "requires human approval",
        ),
    ],
)
def test_ssh_worker_rejects_tampered_policy_metadata_before_executor(
    monkeypatch,
    tmp_path: Path,
    tool: str,
    input_data: dict,
    executor_name: str,
    message_category: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T020000Z_ssh_policy_metadata_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool=tool,
        run_dir=run_dir,
        input_data=input_data,
    )
    executor_called = False

    def unexpected_executor(*args, **kwargs):
        nonlocal executor_called
        executor_called = True
        raise AssertionError("SSH executor must not run after policy rejection")

    monkeypatch.setattr(
        f"codexbridge.job_worker.{executor_name}", unexpected_executor
    )

    assert JobWorker(config_path, run_id).execute() == 1
    persisted = store.get_run(run_id)
    assert persisted["status"] == "failed"
    assert message_category in persisted["result"]["error"]
    assert persisted["result"]["safety_failure"] is True
    assert executor_called is False


def test_ssh_action_worker_persists_bounded_result(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T000001Z_ssh_action_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_action",
        run_dir=run_dir,
        input_data={
            "host_id": "my_vps",
            "action": "service_restart",
            "target": "sample.service",
        },
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_action",
        lambda config, host_id, action, **kwargs: {
            "ok": True,
            "host_id": host_id,
            "action": action,
            "writes_remote": True,
            "high_risk": False,
            "remote_state_verified": False,
            "argv": ["ssh", "<bounded remote argv>"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "restarted\n",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )

    assert JobWorker(config_path, run_id).execute() == 0
    result = store.get_run(run_id)["result"]
    assert result["status"] == "completed"
    assert result["tool"] == "ssh_action"
    assert result["action"] == "service_restart"
    assert result["autonomy_profile"] == "chatgpt_delegated"
    assert result["execution_mode"] == "structured"
    assert result["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert result["policy_decision"] == "needs_chatgpt_approval"
    assert result["policy_authorized"] is True
    assert result["approval_source"] == "chatgpt"
    assert result["remote_state_verified"] is False
    assert "cannot independently verify" in result["remaining_risks"][0]


def test_ssh_transfer_worker_persists_download_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T000002Z_ssh_transfer_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_transfer",
        run_dir=run_dir,
        input_data={
            "host_id": "my_vps",
            "direction": "download",
            "local_repo_name": "sample",
            "local_path": "api.log",
            "remote_path": "/var/log/api.log",
        },
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_transfer",
        lambda config, host_id, direction, **kwargs: {
            "ok": True,
            "host_id": host_id,
            "direction": direction,
            "local_path": str(run_dir / "downloads" / "api.log"),
            "remote_path": "/var/log/api.log",
            "destination": str(run_dir / "downloads" / "api.log"),
            "writes_remote": False,
            "remote_state_verified": False,
            "argv": ["scp", "<bounded scp arguments>"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )

    assert JobWorker(config_path, run_id).execute() == 0
    result = store.get_run(run_id)["result"]
    assert result["status"] == "completed"
    assert result["tool"] == "ssh_transfer"
    assert result["direction"] == "download"
    assert (run_dir / "transfer_result.json").is_file()


def test_ssh_deployment_worker_persists_step_evidence(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T000003Z_ssh_deployment_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_deployment",
        run_dir=run_dir,
        input_data={
            "host_id": "my_vps",
            "deployment_id": "sample_app",
            "confirmation": "CONFIRM_SSH_HIGH_RISK",
        },
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_deployment",
        lambda config, host_id, deployment_id, **kwargs: {
            "ok": True,
            "host_id": host_id,
            "deployment_id": deployment_id,
            "archive_path": str(run_dir / "sample.tar.gz"),
            "steps": [
                {"step": "upload", "ok": True},
                {"step": "health_check", "ok": True},
                {"step": "activate", "ok": True},
            ],
            "writes_remote": True,
            "remote_state_verified": False,
            "exit_code": 0,
            "timed_out": False,
            "output_truncated": False,
            "stdout": "healthy\n",
            "stderr": "",
            "error": "",
        },
    )

    assert JobWorker(config_path, run_id).execute() == 0
    result = store.get_run(run_id)["result"]
    assert result["status"] == "completed"
    assert result["tool"] == "ssh_deployment"
    assert result["deployment_id"] == "sample_app"
    assert result["test_results"][-1]["step"] == "activate"
    assert (run_dir / "deployment_result.json").is_file()
