from __future__ import annotations

from hashlib import sha256
import json
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
            "autonomy_profile": "balanced",
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
    assert result["autonomy_profile"] == "balanced"
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


def _canonical_reviewed_script_input() -> dict:
    script = "set -euo pipefail\nprintf '%s\\n' REVIEWED_SCRIPT_MARKER\n"
    return {
        "action": "reviewed_script",
        "host_id": "my_vps",
        "interpreter": "bash",
        "arguments": [],
        "script": script,
        "script_sha256": sha256(script.encode("utf-8")).hexdigest(),
        "timeout_seconds": 3600,
        "writes_remote": True,
        "high_risk": True,
        "autonomy_profile": "balanced",
        "execution_mode": "reviewed_script",
        "permission_tier": "T4_WRITE_APPLY_CHATGPT_DELEGATED",
        "policy_decision": "needs_chatgpt_approval",
        "policy_authorized": True,
        "approval_source": "chatgpt",
    }


def _create_reviewed_script_run(
    tmp_path: Path,
    input_data: dict,
) -> tuple[Path, RunStore, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260715T000000Z_ssh_reviewed_script_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_reviewed_script",
        run_dir=run_dir,
        input_data=input_data,
    )
    return config_path, store, run_id


def _block_all_ssh_executors(monkeypatch) -> list[str]:
    called: list[str] = []

    def unexpected(*args, **kwargs):
        del args, kwargs
        called.append("executor")
        raise AssertionError("No SSH executor may run before request revalidation")

    for name in (
        "run_ssh_payload",
        "run_ssh_command",
        "start_monitored_ssh_command",
        "run_ssh_action",
        "run_ssh_transfer",
        "run_ssh_deployment",
    ):
        monkeypatch.setattr(f"codexbridge.job_worker.{name}", unexpected)
    return called


def test_reviewed_script_worker_revalidates_and_executes_exact_payload(
    monkeypatch, tmp_path: Path
) -> None:
    input_data = _canonical_reviewed_script_input()
    input_data.update(
        interpreter="pwsh",
        arguments=["safe value", "--mode=test"],
        autonomy_profile="permissive",
    )
    config_path, store, run_id = _create_reviewed_script_run(tmp_path, input_data)
    executor_calls = _block_all_ssh_executors(monkeypatch)
    captured: dict = {}

    def execute_payload(config, host_id, interpreter, payload, **kwargs):
        del config
        captured.update(
            host_id=host_id,
            interpreter=interpreter,
            payload=payload,
            kwargs=kwargs,
        )
        return {
            "ok": True,
            "host_id": host_id,
            "ssh_alias": "my-vps",
            "interpreter": interpreter,
            "payload_sha256": kwargs["payload_sha256"],
            "writes_remote": kwargs["writes_remote"],
            "remote_state_verified": False,
            "root_identity_verified": False,
            "argv": ["ssh.exe", "my-vps", "<reviewed script via stdin>"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "reviewed payload finished\n",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_worker.run_ssh_payload", execute_payload)

    assert JobWorker(config_path, run_id).execute() == 0

    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert result["tool"] == "ssh_reviewed_script"
    assert result["script_sha256"] == input_data["script_sha256"]
    assert result["approval_source"] == "chatgpt"
    assert result["safety_failure"] is False
    assert result["command_result"]["stdout"] == "reviewed payload finished\n"
    assert captured["host_id"] == "my_vps"
    assert captured["interpreter"] == "pwsh"
    assert captured["payload"] == input_data["script"]
    assert captured["kwargs"] == {
        "payload_sha256": input_data["script_sha256"],
        "arguments": ["safe value", "--mode=test"],
        "timeout_seconds": 3600,
        "writes_remote": True,
    }
    assert "REVIEWED_SCRIPT_MARKER" not in json.dumps(result)
    assert "REVIEWED_SCRIPT_MARKER" not in json.dumps(store.get_events(run_id))
    assert executor_calls == []


def test_reviewed_script_worker_persists_timeout_and_partial_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    input_data = _canonical_reviewed_script_input()
    config_path, store, run_id = _create_reviewed_script_run(tmp_path, input_data)
    _block_all_ssh_executors(monkeypatch)
    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_payload",
        lambda config, host_id, interpreter, payload, **kwargs: {
            "ok": False,
            "host_id": host_id,
            "ssh_alias": "my-vps",
            "interpreter": interpreter,
            "payload_sha256": kwargs["payload_sha256"],
            "writes_remote": kwargs["writes_remote"],
            "remote_state_verified": False,
            "root_identity_verified": False,
            "argv": ["ssh.exe", "my-vps", "<reviewed script via stdin>"],
            "exit_code": 124,
            "timed_out": True,
            "duration_seconds": 2.0,
            "stdout": "partial reviewed stdout\n",
            "stderr": "partial reviewed stderr\n",
            "output_truncated": False,
            "error": "Timed out after 2s",
        },
    )

    assert JobWorker(config_path, run_id).execute() == 124

    persisted = store.get_run(run_id)
    result = persisted["result"]
    run_dir = Path(persisted["run_dir"])
    assert persisted["status"] == "timed_out"
    assert result["status"] == "timed_out"
    assert result["timed_out"] is True
    assert result["exit_code"] == 124
    assert result["error"] == "Timed out after 2s"
    assert (run_dir / "stdout.txt").read_text(encoding="utf-8") == (
        "partial reviewed stdout\n"
    )
    assert (run_dir / "stderr.txt").read_text(encoding="utf-8") == (
        "partial reviewed stderr\n"
    )
    assert "REVIEWED_SCRIPT_MARKER" not in json.dumps(result)


@pytest.mark.parametrize(
    ("field", "value", "remove", "message_category"),
    [
        ("script", None, True, "Incomplete persisted reviewed SSH script metadata"),
        ("script", "echo altered\\n", False, "SHA-256"),
        ("script_sha256", "0" * 64, False, "SHA-256"),
        ("autonomy_profile", "conservative", False, "denied profile/mode"),
        ("execution_mode", "root_shell", False, "reviewed_script"),
        ("approval_source", None, True, "Incomplete persisted SSH policy metadata"),
        ("approval_source", "human", False, "ChatGPT delegated approval"),
        ("unexpected_command", "whoami", False, "Unexpected persisted"),
    ],
)
def test_reviewed_script_worker_rejects_tampered_metadata_before_executor(
    monkeypatch,
    tmp_path: Path,
    field: str,
    value: object,
    remove: bool,
    message_category: str,
) -> None:
    input_data = _canonical_reviewed_script_input()
    if remove:
        input_data.pop(field)
    else:
        input_data[field] = value
    config_path, store, run_id = _create_reviewed_script_run(tmp_path, input_data)
    executor_calls = _block_all_ssh_executors(monkeypatch)

    assert JobWorker(config_path, run_id).execute() == 1

    result = store.get_run(run_id)["result"]
    assert result["safety_failure"] is True
    assert message_category in result["error"]
    assert "REVIEWED_SCRIPT_MARKER" not in json.dumps(result)
    assert executor_calls == []


def _canonical_root_shell_input() -> dict:
    script = "id -u\nprintf '%s\\n' ROOT_SHELL_MARKER\n"
    return {
        "action": "root_shell",
        "host_id": "my_vps",
        "script": script,
        "script_sha256": sha256(script.encode("utf-8")).hexdigest(),
        "timeout_seconds": 3600,
        "writes_remote": True,
        "high_risk": True,
        "autonomy_profile": "permissive",
        "execution_mode": "root_shell",
        "permission_tier": "T4_WRITE_APPLY_CHATGPT_DELEGATED",
        "policy_decision": "allowed",
        "policy_authorized": True,
        "approval_source": "none",
    }


def _create_root_shell_run(
    tmp_path: Path,
    input_data: dict,
) -> tuple[Path, RunStore, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260715T000000Z_ssh_root_shell_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_root_shell",
        run_dir=run_dir,
        input_data=input_data,
    )
    return config_path, store, run_id


def test_root_shell_worker_revalidates_executes_and_verifies_root_identity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    input_data = _canonical_root_shell_input()
    config_path, store, run_id = _create_root_shell_run(tmp_path, input_data)
    executor_calls = _block_all_ssh_executors(monkeypatch)
    captured: dict = {}

    def execute_payload(config, host_id, interpreter, payload, **kwargs):
        del config
        captured.update(
            host_id=host_id,
            interpreter=interpreter,
            payload=payload,
            kwargs=kwargs,
        )
        return {
            "ok": True,
            "host_id": host_id,
            "ssh_alias": "my-vps",
            "interpreter": interpreter,
            "payload_sha256": kwargs["payload_sha256"],
            "writes_remote": True,
            "remote_state_verified": False,
            "root_identity_verified": True,
            "argv": ["ssh.exe", "my-vps", "<root shell via stdin>"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "root payload finished\n",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_worker.run_ssh_payload", execute_payload)

    assert JobWorker(config_path, run_id).execute() == 0

    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert result["tool"] == "ssh_root_shell"
    assert result["root_identity_verified"] is True
    assert result["approval_source"] == "none"
    assert result["command_result"]["root_identity_verified"] is True
    assert result["command_result"]["stdout"] == "root payload finished\n"
    assert captured["host_id"] == "my_vps"
    assert captured["interpreter"] == "bash"
    assert captured["payload"] == input_data["script"]
    assert captured["kwargs"] == {
        "payload_sha256": input_data["script_sha256"],
        "timeout_seconds": 3600,
        "writes_remote": True,
        "root_required": True,
    }
    assert "ROOT_SHELL_MARKER" not in json.dumps(result)
    assert "ROOT_SHELL_MARKER" not in json.dumps(store.get_events(run_id))
    assert executor_calls == []


def test_root_shell_worker_fails_when_remote_identity_is_not_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    input_data = _canonical_root_shell_input()
    config_path, store, run_id = _create_root_shell_run(tmp_path, input_data)
    _block_all_ssh_executors(monkeypatch)

    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_payload",
        lambda config, host_id, interpreter, payload, **kwargs: {
            "ok": False,
            "host_id": host_id,
            "ssh_alias": "my-vps",
            "interpreter": interpreter,
            "payload_sha256": kwargs["payload_sha256"],
            "writes_remote": True,
            "remote_state_verified": False,
            "root_identity_verified": False,
            "argv": ["ssh.exe", "my-vps", "<root shell via stdin>"],
            "exit_code": 126,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "",
            "stderr": "CodexBridge root shell requires effective UID 0\n",
            "output_truncated": False,
            "error": "CodexBridge root shell requires effective UID 0",
        },
    )

    assert JobWorker(config_path, run_id).execute() == 126

    persisted = store.get_run(run_id)
    assert persisted["status"] == "failed"
    assert persisted["result"]["root_identity_verified"] is False
    assert "effective UID 0" in persisted["result"]["error"]


@pytest.mark.parametrize(
    ("field", "value", "message_category"),
    [
        ("script", "echo altered\\n", "SHA-256"),
        ("approval_source", "chatgpt", "does not accept approval evidence"),
        ("unexpected_command", "whoami", "Unexpected persisted"),
    ],
)
def test_root_shell_worker_rejects_tampered_metadata_before_executor(
    monkeypatch,
    tmp_path: Path,
    field: str,
    value: object,
    message_category: str,
) -> None:
    input_data = _canonical_root_shell_input()
    input_data[field] = value
    config_path, store, run_id = _create_root_shell_run(tmp_path, input_data)
    executor_calls = _block_all_ssh_executors(monkeypatch)

    assert JobWorker(config_path, run_id).execute() == 1

    result = store.get_run(run_id)["result"]
    assert result["safety_failure"] is True
    assert message_category in result["error"]
    assert "ROOT_SHELL_MARKER" not in json.dumps(result)
    assert executor_calls == []


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
                "      watchdog:",
                "        enabled: true",
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
                "autonomy_profile": "conservative",
                "execution_mode": "reviewed_script",
                "permission_tier": "T0_READ_ONLY",
                "policy_decision": "denied",
                "policy_authorized": False,
                "approval_source": "none",
            },
            "run_ssh_command",
            "denied",
        ),
        (
            "ssh_monitored_command",
            {
                "host_id": "my_vps",
                "command_id": "uptime",
                "autonomy_profile": "balanced",
                "execution_mode": "reviewed_script",
                "permission_tier": "T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB",
                "policy_decision": "allowed",
                "policy_authorized": True,
                "approval_source": "none",
            },
            "start_monitored_ssh_command",
            "not implemented",
        ),
        (
            "ssh_action",
            {
                "host_id": "my_vps",
                "action": "service_restart",
                "target": "sample.service",
                "autonomy_profile": "permissive",
                "execution_mode": "root_shell",
                "permission_tier": "T4_WRITE_APPLY_CHATGPT_DELEGATED",
                "policy_decision": "allowed",
                "policy_authorized": True,
                "approval_source": "none",
            },
            "run_ssh_action",
            "not implemented",
        ),
        (
            "ssh_action",
            {
                "host_id": "my_vps",
                "action": "service_restart",
                "target": "sample.service",
            },
            "run_ssh_action",
            "Incomplete persisted SSH policy metadata",
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
                "autonomy_profile": "balanced",
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
                "autonomy_profile": "balanced",
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
            "autonomy_profile": "balanced",
            "execution_mode": "structured",
            "permission_tier": "T4_WRITE_APPLY_CHATGPT_DELEGATED",
            "policy_decision": "needs_chatgpt_approval",
            "policy_authorized": True,
            "approval_source": "chatgpt",
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
    assert result["autonomy_profile"] == "balanced"
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
            "autonomy_profile": "balanced",
            "execution_mode": "structured",
            "permission_tier": "T0_READ_ONLY",
            "policy_decision": "allowed",
            "policy_authorized": True,
            "approval_source": "none",
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
    assert result["autonomy_profile"] == "balanced"
    assert result["execution_mode"] == "structured"
    assert result["permission_tier"] == "T0_READ_ONLY"
    assert result["policy_decision"] == "allowed"
    assert result["policy_authorized"] is True
    assert result["approval_source"] == "none"
    assert result["writes_remote"] is False
    assert result["high_risk"] is False
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
            "autonomy_profile": "balanced",
            "execution_mode": "structured",
            "permission_tier": "T6_HUMAN_ONLY_RISKY_ACTION",
            "policy_decision": "needs_human_approval",
            "policy_authorized": True,
            "approval_source": "human",
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
    assert result["autonomy_profile"] == "balanced"
    assert result["execution_mode"] == "structured"
    assert result["permission_tier"] == "T6_HUMAN_ONLY_RISKY_ACTION"
    assert result["policy_decision"] == "needs_human_approval"
    assert result["policy_authorized"] is True
    assert result["approval_source"] == "human"
    assert result["writes_remote"] is True
    assert result["high_risk"] is True
    assert result["test_results"][-1]["step"] == "activate"
    assert (run_dir / "deployment_result.json").is_file()


def _canonical_upload_input() -> dict:
    return {
        "host_id": "my_vps",
        "direction": "upload",
        "local_repo_name": "sample",
        "local_path": "deploy.txt",
        "remote_path": "/srv/app/incoming/deploy.txt",
        "recursive": False,
        "overwrite": False,
        "confirmation": "",
        "autonomy_profile": "balanced",
        "execution_mode": "structured",
        "permission_tier": "T4_WRITE_APPLY_CHATGPT_DELEGATED",
        "policy_decision": "needs_chatgpt_approval",
        "policy_authorized": True,
        "approval_source": "chatgpt",
    }


def _canonical_deployment_input(confirmation: str) -> dict:
    return {
        "host_id": "my_vps",
        "deployment_id": "sample_app",
        "confirmation": confirmation,
        "autonomy_profile": "balanced",
        "execution_mode": "structured",
        "permission_tier": "T6_HUMAN_ONLY_RISKY_ACTION",
        "policy_decision": "needs_human_approval",
        "policy_authorized": True,
        "approval_source": "human",
    }


def test_ssh_transfer_worker_revalidates_canonical_upload_policy(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "deploy.txt").write_text("deploy\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T030000Z_ssh_transfer_a1b2c3d4"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_transfer",
        run_dir=run_dir,
        input_data=_canonical_upload_input(),
    )
    executor_called = False

    def successful_transfer(config, host_id, direction, **kwargs):
        nonlocal executor_called
        executor_called = True
        return {
            "ok": True,
            "host_id": host_id,
            "direction": direction,
            "local_path": str(repo / "deploy.txt"),
            "remote_path": "/srv/app/incoming/deploy.txt",
            "destination": "/srv/app/incoming/deploy.txt",
            "writes_remote": True,
            "remote_state_verified": False,
            "argv": ["scp", "<bounded scp arguments>"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_transfer",
        successful_transfer,
    )

    assert JobWorker(config_path, run_id).execute() == 0
    assert executor_called is True
    result = store.get_run(run_id)["result"]
    assert result["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert result["policy_decision"] == "needs_chatgpt_approval"
    assert result["policy_authorized"] is True
    assert result["approval_source"] == "chatgpt"
    assert result["writes_remote"] is True
    assert result["high_risk"] is False


@pytest.mark.parametrize(
    ("field", "value", "message_category"),
    [
        ("autonomy_profile", "permissive", "does not match canonical"),
        ("execution_mode", "reviewed_script", "not implemented"),
        ("permission_tier", "T0_READ_ONLY", "does not match canonical"),
        ("policy_decision", "allowed", "does not match canonical"),
        ("policy_authorized", False, "does not match canonical"),
        ("approval_source", "none", "requires ChatGPT"),
    ],
)
def test_ssh_transfer_worker_rejects_tampered_policy_before_executor(
    monkeypatch,
    tmp_path: Path,
    field: str,
    value: object,
    message_category: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "deploy.txt").write_text("deploy\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T040000Z_ssh_transfer_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    input_data = _canonical_upload_input()
    input_data[field] = value
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_transfer",
        run_dir=run_dir,
        input_data=input_data,
    )
    executor_called = False

    def unexpected_executor(*args, **kwargs):
        nonlocal executor_called
        executor_called = True
        raise AssertionError("SSH transfer executor must not run after rejection")

    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_transfer",
        unexpected_executor,
    )

    assert JobWorker(config_path, run_id).execute() == 1
    result = store.get_run(run_id)["result"]
    assert message_category in result["error"]
    assert result["safety_failure"] is True
    assert executor_called is False


def test_ssh_transfer_worker_rejects_partial_policy_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "deploy.txt").write_text("deploy\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T050000Z_ssh_transfer_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    input_data = _canonical_upload_input()
    input_data.pop("approval_source")
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_transfer",
        run_dir=run_dir,
        input_data=input_data,
    )
    executor_called = False

    def unexpected_executor(*args, **kwargs):
        nonlocal executor_called
        executor_called = True
        raise AssertionError("SSH transfer executor must not run after rejection")

    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_transfer",
        unexpected_executor,
    )

    assert JobWorker(config_path, run_id).execute() == 1
    result = store.get_run(run_id)["result"]
    assert "Incomplete persisted SSH policy metadata" in result["error"]
    assert result["safety_failure"] is True
    assert executor_called is False


@pytest.mark.parametrize("confirmation", ["", "INVALID_CONFIRMATION"])
def test_ssh_deployment_worker_rejects_invalid_confirmation_before_executor(
    monkeypatch,
    tmp_path: Path,
    confirmation: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T060000Z_ssh_deployment_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_deployment",
        run_dir=run_dir,
        input_data=_canonical_deployment_input(confirmation),
    )
    executor_called = False

    def unexpected_executor(*args, **kwargs):
        nonlocal executor_called
        executor_called = True
        raise AssertionError("SSH deployment executor must not run after rejection")

    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_deployment",
        unexpected_executor,
    )

    assert JobWorker(config_path, run_id).execute() == 1
    result = store.get_run(run_id)["result"]
    assert "confirmation token" in result["error"]
    assert result["safety_failure"] is True
    assert executor_called is False


def test_ssh_transfer_worker_rejects_invalid_direction_before_executor(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    write_extended_ssh_config(config_path, repo, runs_dir)
    run_id = "20260706T070000Z_ssh_transfer_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    input_data = _canonical_upload_input()
    input_data["direction"] = "sideways"
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:my_vps",
        tool="ssh_transfer",
        run_dir=run_dir,
        input_data=input_data,
    )
    executor_called = False

    def unexpected_executor(*args, **kwargs):
        nonlocal executor_called
        executor_called = True
        raise AssertionError("SSH transfer executor must not run after rejection")

    monkeypatch.setattr(
        "codexbridge.job_worker.run_ssh_transfer",
        unexpected_executor,
    )

    assert JobWorker(config_path, run_id).execute() == 1
    result = store.get_run(run_id)["result"]
    assert "direction must be" in result["error"]
    assert result["safety_failure"] is True
    assert executor_called is False
