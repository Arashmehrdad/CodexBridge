from __future__ import annotations

import copy
import json
import threading
from hashlib import sha256
from pathlib import Path

import pytest

from codexbridge.config import (
    AppConfig,
    CloudflareProfileConfig,
    CodexConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHDeploymentProfileConfig,
    SSHHostConfig,
)
from codexbridge.job_manager import JobManager
from codexbridge.parallel_groups import ParallelGroupStore


class FakeProcess:
    pid = 12345


def make_git_repo(path: Path) -> None:
    path.mkdir()
    (path / ".git").mkdir()


def make_manager(
    tmp_path: Path, monkeypatch, *, codex_enabled: bool = True
) -> JobManager:
    repo = tmp_path / "repo"
    make_git_repo(repo)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        codex=CodexConfig(enabled=codex_enabled),
        ssh=SSHConfig(
            enabled=True,
            hosts={
                "my_vps": SSHHostConfig(
                    ssh_alias="my-vps",
                    command_profiles=[
                        SSHCommandProfileConfig(
                            command_id="uptime",
                            argv=["uptime"],
                            timeout_seconds=30,
                            watchdog_eligible=True,
                        ),
                        SSHCommandProfileConfig(
                            command_id="write_marker",
                            argv=["touch", "/tmp/codexbridge-marker"],
                            timeout_seconds=30,
                            writes_remote=True,
                        ),
                    ],
                    watchdog={"enabled": True},
                )
            },
        ),
        config_dir=tmp_path,
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )
    return JobManager(config, config_path)


def test_start_powershell_group_delegates_to_two_phase_launcher(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    observed = {}

    def fake_launch(**kwargs):
        observed.update(kwargs)
        return {"accepted": True, "group_id": "group_1"}

    monkeypatch.setattr("codexbridge.job_manager.launch_powershell_group", fake_launch)
    children = [{"idempotency_key": "one", "argv": ["-Command", "one"]}]

    result = manager.start_powershell_group(
        "sample",
        children,
        requested_concurrency=1,
        repository_lock_policy="none",
    )

    assert result == {"accepted": True, "group_id": "group_1"}
    assert observed["config"] is manager.config
    assert observed["repo_name"] == "sample"
    assert observed["children"] == children
    assert observed["spawn_worker"] == manager._spawn_worker
    assert observed["requested_concurrency"] == 1
    assert observed["repository_lock_policy"] == "none"


def test_cancel_powershell_group_cancels_pending_before_active(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    store = ParallelGroupStore(manager.config.resolve_runs_dir())
    group_id = "20260716T053700Z_powershell_group_a1b2c3d4"
    children = []
    for index, suffix in enumerate(("b2c3d4e5", "c3d4e5f6")):
        run_id = f"20260716T053700Z_executable_profile_{suffix}"
        run_dir = manager.config.resolve_runs_dir() / run_id
        run_dir.mkdir(parents=True)
        children.append(
            {
                "run_id": run_id,
                "idempotency_key": f"child-{index}",
                "run_dir": run_dir,
                "worker_lease_token": f"lease-{index}",
                "input_data": {"repo_name": "sample"},
                "initial_status": "launch_pending" if index == 0 else "pending",
            }
        )
    store.reserve_group(
        group_id=group_id,
        repo_name="sample",
        children=children,
    )
    first = store.store.get_run(children[0]["run_id"])
    store.store.conditional_update(
        first["run_id"],
        fields={"status": "running", "current_phase": "running"},
        expected_statuses=("launch_pending",),
        expected_state_version=int(first["state_version"]),
        expected_lease_token=first["worker_lease_token"],
        expected_lease_generation=int(first["lease_generation"]),
    )
    observed: list[str] = []

    def fake_cancel(run_id: str, *, suppress_group_refill: bool = False) -> dict:
        assert suppress_group_refill is True
        observed.append(run_id)
        run = store.store.get_run(run_id)
        store.store.transition_terminal(
            run_id,
            status="cancelled",
            result={"run_id": run_id, "status": "cancelled"},
            expected_statuses=(str(run["status"]),),
            expected_state_version=int(run["state_version"]),
            expected_lease_token=run["worker_lease_token"],
            expected_lease_generation=int(run["lease_generation"]),
            summary="cancelled",
        )
        return {"run_id": run_id, "termination_confirmed": True}

    monkeypatch.setattr(manager, "cancel_run", fake_cancel)

    result = manager.cancel_powershell_group(group_id)

    assert observed == [children[1]["run_id"], children[0]["run_id"]]
    assert result["ok"] is True
    assert result["cancelled"] is True
    assert result["status"] == "cancelled"
    assert result["result"]["status_counts"] == {"cancelled": 2}


def test_codex_disabled_refuses_plan_and_implementation(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch, codex_enabled=False)

    plan = manager.start_plan("sample", "inspect docs")
    implementation = manager.start_implementation(
        "sample", "edit docs", ["README.md"], []
    )

    for response in (plan, implementation):
        assert response["accepted"] is False
        assert response["status"] == "refused"
        assert response["run_id"] is None
        assert response["reason"] == "Codex execution is disabled by configuration"


def test_start_async_plan_creates_run_and_event(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    assert response["accepted"] is True
    assert response["run_id"]
    status = manager.get_status(response["run_id"])
    assert status["status"] == "queued"
    events = manager.get_events(response["run_id"])
    assert events[-1]["stage"] == "worker"


def test_start_async_implementation_validates_files(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_implementation("sample", "edit docs", ["README.md"], [])
    assert response["accepted"] is True
    status = manager.get_status(response["run_id"])
    assert status["tool"] == "codex_implement_task"
    assert status["input"]["requirement_manifest"] == []


def test_start_async_implementation_persists_requirement_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_implementation(
        "sample",
        "REQ-001 Independent requirement accounting\nREQ-002 Canonical repository identity",
        ["README.md"],
        [],
    )

    manifest = manager.get_status(response["run_id"])["input"]["requirement_manifest"]
    assert manifest == [
        {
            "requirement_id": "REQ-001",
            "text": "REQ-001 Independent requirement accounting",
            "mandatory": True,
        },
        {
            "requirement_id": "REQ-002",
            "text": "REQ-002 Canonical repository identity",
            "mandatory": True,
        },
    ]


def test_start_async_project_command_creates_durable_run(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_project_command("sample", "pytest")

    assert response["accepted"] is True
    assert response["repo_name"] == "sample"
    assert response["command_id"] == "pytest"
    assert response["run_id"]
    status = manager.get_status(response["run_id"])
    assert status["tool"] == "project_command"
    assert status["input"]["command_id"] == "pytest"


def test_start_docker_action_creates_durable_run(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    (repo / "docker-compose.yml").write_text(
        "services:\n  api:\n    image: example/api\n", encoding="utf-8"
    )
    manager.config.docker.enabled = True

    response = manager.start_docker_action(
        "sample", "compose_up", services=["api"], build=True
    )

    assert response["accepted"] is True
    assert response["action"] == "compose_up"
    assert response["high_risk"] is False
    status = manager.get_status(response["run_id"])
    assert status["tool"] == "docker_action"
    assert status["input"]["services"] == ["api"]
    assert status["input"]["build"] is True


def test_start_high_risk_docker_action_requires_confirmed_gate(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.config.docker.enabled = True
    manager.config.docker.allow_prune = True

    response = manager.start_docker_action(
        "sample",
        "image_prune",
        confirmation=manager.config.docker.confirmation_token,
    )

    assert response["accepted"] is True
    assert response["high_risk"] is True
    status = manager.get_status(response["run_id"])
    assert status["risk_level"] == "high"
    assert status["input"]["action"] == "image_prune"


def test_start_pytest_path_persists_normalized_target(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    target_file = tmp_path / "repo" / "tests" / "test_api.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    response = manager.start_pytest_path("sample", r"tests\test_api.py::test_ok")

    assert response["accepted"] is True
    assert response["repo_name"] == "sample"
    assert response["command_id"] == "pytest_path"
    assert response["path"] == "tests/test_api.py::test_ok"
    status = manager.get_status(response["run_id"])
    assert status["tool"] == "project_command"
    assert status["input"]["command_id"] == "pytest_path"
    assert status["input"]["path"] == "tests/test_api.py::test_ok"
    input_data = json.loads(
        (tmp_path / "runs" / response["run_id"] / "input.json").read_text(
            encoding="utf-8"
        )
    )
    assert input_data["command_id"] == "pytest_path"
    assert input_data["path"] == "tests/test_api.py::test_ok"


def test_start_ssh_command_creates_durable_run(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_ssh_command("my_vps", "uptime")

    assert response["accepted"] is True
    assert response["host_id"] == "my_vps"
    assert response["command_id"] == "uptime"
    assert response["writes_remote"] is False
    status = manager.get_status(response["run_id"])
    assert status["repo_name"] == "ssh:my_vps"
    assert status["tool"] == "ssh_command"
    assert status["input"] == {
        "host_id": "my_vps",
        "command_id": "uptime",
        "autonomy_profile": "permissive",
        "execution_mode": "structured",
        "permission_tier": "T0_READ_ONLY",
        "policy_decision": "allowed",
        "policy_authorized": True,
        "approval_source": "none",
    }
    assert response["autonomy_profile"] == "permissive"
    assert response["execution_mode"] == "structured"
    assert response["permission_tier"] == "T0_READ_ONLY"
    assert response["policy_decision"] == "allowed"
    assert response["policy_authorized"] is True
    assert response["approval_source"] == "none"


def test_start_ssh_monitored_command_creates_durable_run(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_ssh_monitored_command("my_vps", "uptime")

    assert response["accepted"] is True
    assert response["host_id"] == "my_vps"
    assert response["command_id"] == "uptime"
    assert response["watchdog_mode"] == "observe_only"
    status = manager.get_status(response["run_id"])
    assert status["tool"] == "ssh_monitored_command"
    assert {
        key: value
        for key, value in status["input"].items()
        if key not in {"staging_manifest", "remote_controller_state"}
    } == {
        "host_id": "my_vps",
        "command_id": "uptime",
        "autonomy_profile": "permissive",
        "execution_mode": "structured",
        "permission_tier": "T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB",
        "policy_decision": "allowed",
        "policy_authorized": True,
        "approval_source": "none",
    }
    controller_state = status["input"]["remote_controller_state"]
    assert controller_state["request_id"] == response["run_id"]
    assert controller_state["host_id"] == "my_vps"
    assert controller_state["command_id"] == "uptime"
    assert controller_state["lease_generation"] == 1
    assert controller_state["remote"]["authoritative_state"] == "launch_pending"
    assert controller_state["local"]["reconciliation_state"] == "not_started"
    assert controller_state["remote"]["state_dir"].startswith(".codexbridge/jobs/")
    assert controller_state["local"]["remote_job_id"] == controller_state["execution_id"]
    manifest = status["input"]["staging_manifest"]
    assert manifest["tool"] == "ssh_monitored_command"
    assert manifest["invoking_run_id"] == response["run_id"]
    assert manifest["lease_generation"] == 1
    assert manifest["inputs"] == []
    assert manifest["outputs"] == [
        {
            "stream": "stdout",
            "relative_path": "stdout.txt",
            "classification": "protected_evidence",
        },
        {
            "stream": "stderr",
            "relative_path": "stderr.txt",
            "classification": "protected_evidence",
        },
    ]
    assert response["autonomy_profile"] == "permissive"
    assert response["execution_mode"] == "structured"
    assert response["permission_tier"] == "T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB"
    assert response["policy_decision"] == "allowed"
    assert response["policy_authorized"] is True
    assert response["approval_source"] == "none"


def test_start_ssh_write_command_is_directly_authorized_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_ssh_command("my_vps", "write_marker")

    status = manager.get_status(response["run_id"])
    assert response["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert response["policy_decision"] == "allowed"
    assert response["policy_authorized"] is True
    assert response["approval_source"] == "none"
    assert status["input"]["permission_tier"] == response["permission_tier"]
    assert status["input"]["policy_decision"] == response["policy_decision"]
    assert status["input"]["approval_source"] == "none"


def test_permissive_ssh_write_command_is_directly_authorized(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_ssh_command(
        "my_vps", "write_marker", autonomy_profile="permissive"
    )

    assert response["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert response["policy_decision"] == "allowed"
    assert response["approval_source"] == "none"


def test_ssh_tier_denial_creates_no_run_or_lock(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="only 'permissive' is active"): 
        manager.start_ssh_command(
            "my_vps", "write_marker", autonomy_profile="conservative"
        )

    assert manager.store.list_runs() == []
    assert manager.locks.list_locks() == []


def test_conservative_monitored_read_requires_human_approval_before_launch(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="only 'permissive' is active"): 
        manager.start_ssh_monitored_command(
            "my_vps", "uptime", autonomy_profile="conservative"
        )

    assert manager.store.list_runs() == []
    assert manager.locks.list_locks() == []


def test_confirmed_high_risk_ssh_action_records_human_approval(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.config.ssh.allow_admin = True

    response = manager.start_ssh_action(
        "my_vps",
        "service_stop",
        target="sample.service",
        confirmation=manager.config.ssh.confirmation_token,
        autonomy_profile="permissive",
    )

    status = manager.get_status(response["run_id"])
    assert response["high_risk"] is True
    assert response["permission_tier"] == "T6_HUMAN_ONLY_RISKY_ACTION"
    assert response["policy_decision"] == "needs_human_approval"
    assert response["policy_authorized"] is True
    assert response["approval_source"] == "human"
    assert status["input"]["permission_tier"] == response["permission_tier"]
    assert status["input"]["approval_source"] == "human"


def test_start_ssh_action_transfer_and_deployment_create_durable_runs(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    host = manager.config.ssh.hosts["my_vps"]
    host.allowed_remote_roots = ["/srv/app", "/var/log"]
    host.allowed_executables = ["docker", "git", "curl"]
    host.deployment_profiles = {
        "sample_app": SSHDeploymentProfileConfig(
            repo_name="sample",
            remote_root="/srv/app",
            compose_file="docker-compose.yml",
            health_command_id="uptime",
        )
    }
    manager.config.ssh.allow_transfer = True
    manager.config.ssh.allow_deploy = True
    manager.config.ssh.allow_admin = True
    local_file = tmp_path / "repo" / "deploy.txt"
    local_file.write_text("deploy\n", encoding="utf-8")

    action = manager.start_ssh_action(
        "my_vps",
        "service_restart",
        target="sample.service",
        autonomy_profile="permissive",
        execution_mode="structured",
    )
    assert action["accepted"] is True
    assert action["action"] == "service_restart"
    assert action["autonomy_profile"] == "permissive"
    assert action["execution_mode"] == "structured"
    assert action["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert action["policy_decision"] == "allowed"
    assert action["policy_authorized"] is True
    assert action["approval_source"] == "none"
    assert (
        manager.get_status(action["run_id"])["input"]["autonomy_profile"]
        == "permissive"
    )
    assert manager.get_status(action["run_id"])["tool"] == "ssh_action"
    manager.locks.release("ssh:my_vps", action["run_id"])

    transfer = manager.start_ssh_transfer(
        "my_vps",
        "upload",
        repo_name="sample",
        local_path="deploy.txt",
        remote_path="/srv/app/incoming/deploy.txt",
    )
    assert transfer["accepted"] is True
    assert transfer["direction"] == "upload"
    assert transfer["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert transfer["policy_decision"] == "allowed"
    assert transfer["policy_authorized"] is True
    assert transfer["approval_source"] == "none"
    transfer_status = manager.get_status(transfer["run_id"])
    assert transfer_status["tool"] == "ssh_transfer"
    upload_bytes = local_file.read_bytes()
    assert transfer_status["input"]["transfer_manifest"] == {
        "version": 1,
        "source_kind": "file",
        "source_size_bytes": len(upload_bytes),
        "source_sha256": sha256(upload_bytes).hexdigest(),
    }
    assert transfer_status["input"]["permission_tier"] == transfer["permission_tier"]
    assert transfer_status["input"]["approval_source"] == "none"
    manager.locks.release("ssh:my_vps", transfer["run_id"])

    deployment = manager.start_ssh_deployment(
        "my_vps",
        "sample_app",
        confirmation=manager.config.ssh.confirmation_token,
    )
    assert deployment["accepted"] is True
    assert deployment["deployment_id"] == "sample_app"
    assert deployment["permission_tier"] == "T6_HUMAN_ONLY_RISKY_ACTION"
    assert deployment["policy_decision"] == "needs_human_approval"
    assert deployment["policy_authorized"] is True
    assert deployment["approval_source"] == "human"
    deployment_status = manager.get_status(deployment["run_id"])
    assert deployment_status["tool"] == "ssh_deployment"
    assert deployment_status["risk_level"] == "high"
    assert deployment_status["input"]["permission_tier"] == deployment["permission_tier"]
    assert deployment_status["input"]["approval_source"] == "human"


def test_ssh_transfer_profiles_gate_upload_and_allow_download(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    host = manager.config.ssh.hosts["my_vps"]
    host.allowed_remote_roots = ["/srv/app"]
    manager.config.ssh.allow_transfer = True
    local_file = tmp_path / "repo" / "deploy.txt"
    local_file.write_text("deploy\n", encoding="utf-8")

    with pytest.raises(ValueError, match="only 'permissive' is active"): 
        manager.start_ssh_transfer(
            "my_vps",
            "upload",
            repo_name="sample",
            local_path="deploy.txt",
            remote_path="/srv/app/deploy.txt",
            autonomy_profile="conservative",
        )

    assert manager.store.list_runs() == []
    assert manager.locks.list_locks() == []

    download = manager.start_ssh_transfer(
        "my_vps",
        "download",
        repo_name="sample",
        local_path="artifact.log",
        remote_path="/srv/app/artifact.log",
        autonomy_profile="permissive",
    )
    download_status = manager.get_status(download["run_id"])
    assert download_status["input"]["transfer_manifest"] == {
        "version": 1,
        "source_kind": "remote",
        "staging_relative_path": "downloads/artifact.log",
    }
    assert download["permission_tier"] == "T0_READ_ONLY"
    assert download["policy_decision"] == "allowed"
    assert download["approval_source"] == "none"


def test_disabled_ssh_autonomy_profile_creates_no_run_or_lock(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="only 'permissive' is active"):
        manager.start_ssh_command(
            "my_vps",
            "uptime",
            autonomy_profile="balanced",
        )

    assert manager.store.list_runs() == []
    assert manager.locks.list_locks() == []


def test_reviewed_script_launch_persists_exact_request_and_redacts_public_views(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    script = "set -euo pipefail\nprintf '%s\\n' REVIEWED_SCRIPT_MARKER\n"
    digest = sha256(script.encode("utf-8")).hexdigest()

    response = manager.start_ssh_reviewed_script(
        "my_vps",
        "bash",
        script,
        digest,
        arguments=["--mode", "safe value"],
        autonomy_profile="permissive",
    )

    assert response["accepted"] is True
    assert response["script_sha256"] == digest
    assert response["arguments"] == ["--mode", "safe value"]
    assert response["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert response["policy_decision"] == "allowed"
    assert response["policy_authorized"] is True
    assert response["approval_source"] == "none"
    assert "script" not in response

    stored = manager.store.get_run(response["run_id"])
    assert stored["tool"] == "ssh_reviewed_script"
    assert stored["input"]["script"] == script
    assert stored["input"]["interpreter"] == "bash"
    assert stored["input"]["arguments"] == ["--mode", "safe value"]
    assert stored["input"]["script_sha256"] == digest
    assert stored["input"]["autonomy_profile"] == "permissive"
    assert stored["input"]["execution_mode"] == "reviewed_script"
    assert stored["input"]["writes_remote"] is True
    assert stored["input"]["high_risk"] is False
    assert stored["input"]["approval_source"] == "none"

    public = manager.get_status(response["run_id"])
    assert public["input"]["script"] == "[REDACTED]"
    artifact = json.loads(
        (Path(stored["run_dir"]) / "input.json").read_text(encoding="utf-8")
    )
    assert artifact["script"] == "[REDACTED]"
    assert "REVIEWED_SCRIPT_MARKER" not in json.dumps(artifact)
    manager.locks.release("ssh:my_vps", response["run_id"])


def test_reviewed_script_read_only_still_uses_dedicated_model_policy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    script = "uptime\n"
    digest = sha256(script.encode("utf-8")).hexdigest()

    permissive = manager.start_ssh_reviewed_script(
        "my_vps",
        "sh",
        script,
        digest,
        writes_remote=False,
        autonomy_profile="permissive",
    )
    assert permissive["writes_remote"] is False
    assert permissive["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert permissive["policy_decision"] == "allowed"
    assert permissive["approval_source"] == "none"
    manager.locks.release("ssh:my_vps", permissive["run_id"])


def test_reviewed_script_high_risk_classification_uses_model_approval(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    script = "set -euo pipefail\nuptime\n"
    digest = sha256(script.encode("utf-8")).hexdigest()

    response = manager.start_ssh_reviewed_script(
        "my_vps",
        "bash",
        script,
        digest,
        autonomy_profile="permissive",
        high_risk=True,
    )

    assert response["accepted"] is True
    assert response["risk_level"] == "high"
    assert response["requires_human"] is False
    assert response["high_risk"] is True
    assert response["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert response["policy_decision"] == "allowed"
    assert response["approval_source"] == "none"
    stored = manager.store.get_run(response["run_id"])
    assert stored["input"]["high_risk"] is True
    assert stored["input"]["approval_source"] == "none"
    manager.locks.release("ssh:my_vps", response["run_id"])


def test_root_shell_launch_persists_exact_request_and_redacts_public_views(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    script = "id -u\nprintf '%s\\n' ROOT_SHELL_MARKER\n"
    digest = sha256(script.encode("utf-8")).hexdigest()

    response = manager.start_ssh_root_shell(
        "my_vps",
        script,
        digest,
    )

    assert response["accepted"] is True
    assert response["risk_level"] == "high"
    assert response["requires_human"] is False
    assert response["permission_tier"] == "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    assert response["policy_decision"] == "allowed"
    assert response["policy_authorized"] is True
    assert response["approval_source"] == "none"
    assert response["writes_remote"] is True
    assert response["high_risk"] is True
    assert "script" not in response

    stored = manager.store.get_run(response["run_id"])
    assert stored["tool"] == "ssh_root_shell"
    assert stored["input"]["script"] == script
    assert stored["input"]["script_sha256"] == digest
    assert stored["input"]["autonomy_profile"] == "permissive"
    assert stored["input"]["execution_mode"] == "root_shell"
    assert stored["input"]["approval_source"] == "none"

    public = manager.get_status(response["run_id"])
    assert public["input"]["script"] == "[REDACTED]"
    artifact = json.loads(
        (Path(stored["run_dir"]) / "input.json").read_text(encoding="utf-8")
    )
    assert artifact["script"] == "[REDACTED]"
    assert "ROOT_SHELL_MARKER" not in json.dumps(artifact)
    manager.locks.release("ssh:my_vps", response["run_id"])


def test_root_shell_rejects_nonpermissive_profile_without_run_or_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    script = "id -u\n"

    with pytest.raises(ValueError, match="only 'permissive' is active"):
        manager.start_ssh_root_shell(
            "my_vps",
            script,
            sha256(script.encode("utf-8")).hexdigest(),
            autonomy_profile="balanced",
        )

    assert manager.store.list_runs() == []
    assert manager.locks.list_locks() == []


def test_reviewed_script_denied_profile_creates_no_run_or_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    script = "uptime\n"

    with pytest.raises(ValueError, match="only 'permissive' is active"):
        manager.start_ssh_reviewed_script(
            "my_vps",
            "sh",
            script,
            sha256(script.encode("utf-8")).hexdigest(),
            autonomy_profile="conservative",
        )

    assert manager.store.list_runs() == []
    assert manager.locks.list_locks() == []


@pytest.mark.parametrize(
    ("autonomy_profile", "execution_mode", "message_category"),
    [
        ("conservative", "reviewed_script", "only 'permissive' is active"),
        ("balanced", "reviewed_script", "only 'permissive' is active"),
    ],
)
def test_denied_ssh_launch_creates_no_run_or_lock(
    tmp_path: Path,
    monkeypatch,
    autonomy_profile: str,
    execution_mode: str,
    message_category: str,
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match=message_category):
        manager.start_ssh_command(
            "my_vps",
            "uptime",
            autonomy_profile=autonomy_profile,
            execution_mode=execution_mode,
        )

    assert manager.store.list_runs() == []
    assert manager.locks.list_locks() == []


def test_ssh_transfer_overwrite_and_deployment_require_confirmation(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    host = manager.config.ssh.hosts["my_vps"]
    host.allowed_remote_roots = ["/srv/app"]
    host.deployment_profiles = {
        "sample_app": SSHDeploymentProfileConfig(
            repo_name="sample", remote_root="/srv/app"
        )
    }
    manager.config.ssh.allow_transfer = True
    manager.config.ssh.allow_deploy = True

    with pytest.raises(ValueError, match="confirmation token"):
        manager.start_ssh_transfer(
            "my_vps",
            "download",
            repo_name="sample",
            local_path="artifact.log",
            remote_path="/srv/app/artifact.log",
            overwrite=True,
        )
    with pytest.raises(ValueError, match="confirmation token"):
        manager.start_ssh_deployment("my_vps", "sample_app", confirmation="")


def test_start_cloudflare_action_creates_durable_run(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.config.cloudflare.enabled = True
    manager.config.cloudflare.allow_dns_write = True
    manager.config.repos["sample"].cloudflare_profiles = ["production"]
    manager.config.cloudflare.profiles = {
        "production": CloudflareProfileConfig(
            zone_id="a" * 32,
            zone_name="example.com",
            allowed_dns_names=["api.example.com"],
        )
    }

    response = manager.start_cloudflare_action(
        "sample",
        "production",
        "dns_create",
        payload={
            "type": "A",
            "name": "api.example.com",
            "content": "192.0.2.10",
            "ttl": 1,
            "proxied": True,
        },
    )

    assert response["accepted"] is True
    assert response["repo_name"] == "sample"
    assert response["profile_id"] == "production"
    assert response["action"] == "dns_create"
    assert response["high_risk"] is False
    status = manager.get_status(response["run_id"])
    assert status["repo_name"] == "cloudflare:sample:production"
    assert status["tool"] == "cloudflare_action"
    assert status["risk_level"] == "medium"


def test_cloudflare_high_risk_action_requires_confirmation(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.config.cloudflare.enabled = True
    manager.config.cloudflare.allow_delete = True
    manager.config.repos["sample"].cloudflare_profiles = ["production"]
    manager.config.cloudflare.profiles = {
        "production": CloudflareProfileConfig(
            zone_id="a" * 32,
            zone_name="example.com",
            allowed_dns_names=["api.example.com"],
        )
    }

    with pytest.raises(ValueError, match="requires confirmation token"):
        manager.start_cloudflare_action(
            "sample", "production", "dns_delete", resource_id="c" * 32
        )


def test_cloudflare_action_rejects_unauthorized_repository(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.config.cloudflare.enabled = True
    manager.config.cloudflare.allow_dns_write = True
    manager.config.cloudflare.profiles = {
        "production": CloudflareProfileConfig(
            zone_id="a" * 32,
            zone_name="example.com",
            allowed_dns_names=["api.example.com"],
        )
    }

    with pytest.raises(ValueError, match="not authorized"):
        manager.start_cloudflare_action(
            "sample",
            "production",
            "dns_create",
            payload={
                "type": "A",
                "name": "api.example.com",
                "content": "192.0.2.10",
            },
        )


def test_cancel_run_marks_cancelled(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "codexbridge.job_manager.subprocess.run", lambda *args, **kwargs: None
    )
    response = manager.start_plan("sample", "inspect docs")
    cancelled = manager.cancel_run(response["run_id"])
    assert cancelled["cancelled"] is True
    assert manager.get_status(response["run_id"])["status"] == "cancelled"
    first = manager.get_result(response["run_id"])
    second = manager.get_result(response["run_id"])
    assert first == second
    assert first["status"] == "cancelled"
    assert first["cancelled"] is True
    assert first["stdout"] == ""
    assert first["stderr"] == ""


def test_reconcile_startup_contains_legacy_running_record_without_identity(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(
        response["run_id"],
        status="running",
        launcher_pid=None,
        worker_pid=None,
        worker_identity="",
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.process_is_running", lambda _pid: False
    )

    assert manager.reconcile_startup() == 1

    status = manager.get_status(response["run_id"])
    assert status["status"] == "recovery_pending"
    assert "no verifiable worker identity" in status["recovery_reason"]
    assert manager.locks.find_lock("sample", response["run_id"]) is not None


def test_reconcile_startup_adopts_verified_active_worker(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(
        response["run_id"],
        status="running",
        launcher_pid=None,
        worker_pid=222,
        worker_identity="222:windows:100",
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.process_matches_identity",
        lambda pid, identity: pid == 222 and identity == "222:windows:100",
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.process_is_running", lambda _pid: False
    )

    assert manager.reconcile_startup() == 1

    status = manager.get_status(response["run_id"])
    assert status["status"] == "running"
    assert manager.locks.find_lock("sample", response["run_id"]) is not None
    assert any(
        "identity verified" in event["message"]
        for event in manager.get_events(response["run_id"])
    )


def test_reconcile_startup_fails_dead_claimed_worker_and_releases_lock(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(
        response["run_id"],
        status="running",
        launcher_pid=None,
        worker_pid=222,
        worker_identity="222:windows:100",
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.process_matches_identity",
        lambda _pid, _identity: False,
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.process_is_running", lambda _pid: False
    )

    assert manager.reconcile_startup() == 1

    assert manager.get_status(response["run_id"])["status"] == "failed"
    result = manager.get_result(response["run_id"])
    assert result["classification"] == "infrastructure_failure"
    assert manager.locks.find_lock("sample", response["run_id"]) is None


def test_reconcile_startup_relaunches_stranded_queued_worker_once(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(response["run_id"], launcher_pid=None)
    monkeypatch.setattr(
        "codexbridge.job_manager.process_is_running", lambda _pid: False
    )

    assert manager.reconcile_startup() == 1

    internal = manager.store.get_run(response["run_id"])
    assert internal["status"] == "queued"
    assert internal["launch_attempts"] == 2
    assert internal["launcher_pid"] == 12345
    assert internal["lease_generation"] == 2


def test_reconcile_startup_records_failure_and_retains_lock(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    monkeypatch.setattr(
        manager,
        "_reconcile_run",
        lambda _run: (_ for _ in ()).throw(RuntimeError("reconcile boom")),
    )

    assert manager.reconcile_startup() == 1

    status = manager.get_status(response["run_id"])
    assert status["status"] == "recovery_pending"
    assert "reconcile boom" in status["recovery_reason"]
    assert manager.locks.find_lock("sample", response["run_id"]) is not None
    assert any(
        event["stage"] == "reconcile" and event["level"] == "error"
        for event in manager.get_events(response["run_id"])
    )


def test_reconcile_startup_repairs_terminal_result_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    results = {
        "20260714T000010Z_project_command_deadbeef": {
            "status": "completed",
            "value": "missing",
        },
        "20260714T000011Z_project_command_deadbeef": {
            "status": "completed",
            "value": "invalid",
        },
        "20260714T000012Z_project_command_deadbeef": {
            "status": "completed",
            "value": "contradictory",
        },
    }
    for run_id, result in results.items():
        run_dir = Path(manager.config.resolve_runs_dir()) / run_id
        run_dir.mkdir(parents=True)
        manager.store.create_run(
            run_id=run_id,
            repo_name="sample",
            tool="project_command",
            run_dir=run_dir,
            input_data={"repo_name": "sample", "command_id": "pytest"},
        )
        current = manager.store.get_run(run_id)
        assert manager.store.transition_terminal(
            run_id,
            status="completed",
            result=result,
            expected_statuses=("queued",),
            expected_state_version=current["state_version"],
        )
    (
        Path(manager.config.resolve_runs_dir()) / list(results)[1] / "result.json"
    ).write_text("not json", encoding="utf-8")
    (
        Path(manager.config.resolve_runs_dir()) / list(results)[2] / "result.json"
    ).write_text(
        json.dumps({"status": "completed", "value": "loser"}), encoding="utf-8"
    )

    assert manager.reconcile_startup() == 3

    for run_id, result in results.items():
        artifact = (
            Path(manager.config.resolve_runs_dir()) / run_id / "result.json"
        )
        assert json.loads(artifact.read_text(encoding="utf-8")) == result
        assert (
            manager.store.get_run(run_id)["result_publication_status"] == "published"
        )


def test_unknown_and_malformed_run_ids_are_structured(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    unknown = "20260711T000000Z_project_command_deadbeef"

    for lookup in (manager.get_status, manager.get_result, manager.cancel_run):
        missing = lookup(unknown)
        malformed = lookup("not-a-run-id")
        assert missing["ok"] is False
        assert missing["error_code"] == "run_not_found"
        assert malformed["ok"] is False
        assert malformed["error_code"] == "invalid_run_id"


def test_start_async_duplicate_project_command_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    first = manager.start_project_command("sample", "pytest")
    second = manager.start_project_command("sample", "pytest")

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["run_id"] == ""
    assert second["reason"] == "duplicate active task"
    assert second["duplicate"] is True


def test_start_async_without_config_path_returns_schema_safe_refusal(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    manager.config_path = None

    response = manager.start_project_command("sample", "pytest")

    assert response["accepted"] is False
    assert response["run_id"] == ""
    assert response["status"] == "refused"
    assert response["reason"] == "Async jobs require a config file path"


def test_start_json_validation_path_persists_normalized_target(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    target_file = tmp_path / "repo" / "data" / "config.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text('{"ok": true}\n', encoding="utf-8")

    response = manager.start_json_validation_path("sample", r"data\config.json")

    assert response["accepted"] is True
    assert response["path"] == "data/config.json"


def test_start_project_command_accepts_case_insensitive_repo_name(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_project_command("Sample", "pytest")

    assert response["accepted"] is True
    assert response["repo_name"] == "sample"
    assert response["requested_repo_name"] == "Sample"


def test_list_runs_and_latest_result_use_canonical_repo_filters(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("Sample", "inspect docs")
    run_id = response["run_id"]
    manager.store.update_run(
        run_id,
        status="completed",
        result_json={"run_id": run_id, "repo_name": "sample", "summary": "done"},
    )

    listed = manager.list_runs(repo_name="Sample")
    latest = manager.latest_result(repo_name="Sample")

    assert listed[0]["repo_name"] == "sample"
    assert latest["repo_name"] == "sample"


def test_worker_launch_uses_independent_process_group_options(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(
        "codexbridge.job_manager.process_group_popen_kwargs",
        lambda: {"creationflags": 512},
    )
    monkeypatch.setattr("codexbridge.job_manager.subprocess.Popen", fake_popen)

    response = manager.start_plan("sample", "inspect docs")

    assert response["accepted"] is True
    assert captured["creationflags"] == 512


def test_cancel_run_is_fail_closed_when_termination_is_unconfirmed(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    monkeypatch.setattr(
        "codexbridge.job_manager.terminate_process_tree",
        lambda pid: {
            "pid": pid,
            "method": "simulated",
            "termination_attempted": True,
            "forced": False,
            "exit_code": 1,
            "terminated": False,
            "error": "still running",
        },
    )

    cancelled = manager.cancel_run(response["run_id"])

    assert cancelled["ok"] is False
    assert cancelled["cancelled"] is False
    assert cancelled["termination_confirmed"] is False
    status = manager.get_status(response["run_id"])
    assert status["status"] == "cancellation_pending"
    assert status["current_phase"] == "cancellation_pending"
    assert manager.locks.find_lock("sample", response["run_id"]) is not None


def test_cancel_run_terminates_child_then_worker_and_releases_lock(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(response["run_id"], pid=222, worker_pid=111)
    terminated: list[int] = []

    def fake_terminate(pid):
        terminated.append(pid)
        return {
            "pid": pid,
            "method": "simulated",
            "termination_attempted": True,
            "forced": False,
            "exit_code": 0,
            "terminated": True,
            "error": "",
        }

    monkeypatch.setattr(
        "codexbridge.job_manager.terminate_process_tree", fake_terminate
    )

    cancelled = manager.cancel_run(response["run_id"])

    assert terminated == [222, 111, 12345]
    assert cancelled["ok"] is True
    assert cancelled["cancelled"] is True
    assert cancelled["termination_confirmed"] is True
    assert manager.get_status(response["run_id"])["status"] == "cancelled"
    assert manager.locks.find_lock("sample", response["run_id"]) is None


def test_cancel_pending_parallel_child_without_process_is_terminal(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    run_id = "20260716T060000Z_executable_profile_a1b2c3d4"
    run_dir = manager.config.resolve_runs_dir() / run_id
    run_dir.mkdir(parents=True)
    manager.store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="executable_profile",
        run_dir=run_dir,
        input_data={"profile_id": "powershell", "argv": ["-Command", "sleep"]},
        status="pending",
        worker_lease_token="pending-child-lease",
    )

    cancelled = manager.cancel_run(run_id)

    assert cancelled["ok"] is True
    assert cancelled["cancelled"] is True
    assert cancelled["termination_confirmed"] is True
    assert manager.get_status(run_id)["status"] == "cancelled"


def test_cancel_monitored_run_without_remote_metadata_stays_pending(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_ssh_monitored_command("my_vps", "uptime")

    cancelled = manager.cancel_run(response["run_id"])

    assert cancelled["ok"] is False
    assert cancelled["termination_confirmed"] is False
    assert "remote process identity is unknown" in cancelled["reason"]
    assert "lock retained" in cancelled["reason"]


def test_cancel_monitored_run_persists_remote_completion_before_local_terminal(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_ssh_monitored_command("my_vps", "uptime")
    run_id = response["run_id"]
    current = manager.store.get_run(run_id)
    progress = dict(current.get("progress") or {})
    progress.update(
        {
            "remote_process": {
                "pid": 321,
                "pgid": 321,
                "start_time_ticks": "98765",
            },
            "termination_grace_seconds": 5,
        }
    )
    manager.store.update_run(
        run_id,
        status="running",
        launcher_pid=12345,
        worker_pid=None,
        pid=None,
        progress_json=progress,
    )
    observed: dict = {}

    def fake_cancel(config, host_id, contract, remote_process, *, requested_at, grace_seconds):
        del config
        observed.update(
            {
                "host_id": host_id,
                "contract": contract,
                "remote_process": remote_process,
                "requested_at": requested_at,
                "grace_seconds": grace_seconds,
            }
        )
        return {
            "identity_verified": True,
            "request_persisted": True,
            "term_sent": True,
            "kill_sent": False,
            "terminated": True,
            "already_exited": False,
            "identity_changed": False,
            "completion_persisted": True,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_manager.cancel_remote_controller", fake_cancel)

    cancelled = manager.cancel_run(run_id)

    assert cancelled["ok"] is True
    assert cancelled["status"] == "cancelled"
    assert cancelled["termination_confirmed"] is True
    assert observed["host_id"] == "my_vps"
    assert observed["contract"] == current["input"]["remote_controller_state"]
    assert observed["remote_process"]["pid"] == 321
    assert observed["grace_seconds"] == 5
    assert observed["requested_at"]
    terminal = manager.store.get_run(run_id)
    assert terminal["status"] == "cancelled"
    assert terminal["progress"]["remote_termination"]["completion_persisted"] is True


def test_cancel_monitored_run_natural_completion_race_publishes_winner_once(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_ssh_monitored_command("my_vps", "uptime")
    run_id = response["run_id"]
    current = manager.store.get_run(run_id)
    progress = dict(current.get("progress") or {})
    progress["remote_process"] = {
        "pid": 321,
        "pgid": 321,
        "start_time_ticks": "98765",
    }
    manager.store.update_run(
        run_id,
        status="running",
        launcher_pid=12345,
        worker_pid=None,
        pid=None,
        progress_json=progress,
    )
    publications: list[str] = []

    def fake_publish(store, published_run_id):
        del store
        publications.append(published_run_id)
        return {"ok": True, "error": ""}

    def fake_cancel(config, host_id, contract, remote_process, *, requested_at, grace_seconds):
        del config, host_id, contract, remote_process, requested_at, grace_seconds
        pending = manager.store.get_run(run_id)
        completed = manager.store.transition_terminal(
            run_id,
            status="completed",
            result={"run_id": run_id, "status": "completed", "summary": "remote done"},
            expected_statuses=("cancellation_pending",),
            expected_state_version=int(pending["state_version"]),
            expected_lease_token=pending["worker_lease_token"],
            expected_lease_generation=int(pending["lease_generation"]),
            summary="remote done",
        )
        assert completed is not None
        return {
            "identity_verified": True,
            "request_persisted": True,
            "term_sent": False,
            "kill_sent": False,
            "terminated": True,
            "already_exited": True,
            "identity_changed": False,
            "completion_persisted": True,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_manager.publish_run_result", fake_publish)
    monkeypatch.setattr("codexbridge.job_manager.cancel_remote_controller", fake_cancel)

    cancelled = manager.cancel_run(run_id)

    assert cancelled["ok"] is True
    assert cancelled["status"] == "completed"
    assert cancelled["cancelled"] is False
    assert cancelled["termination_confirmed"] is True
    assert publications == [run_id]
    assert manager.store.get_run(run_id)["status"] == "completed"
    assert manager.locks.find_lock("sample", run_id) is None


def test_restart_reconciles_completed_remote_cancellation_once(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_ssh_monitored_command("my_vps", "uptime")
    run_id = response["run_id"]
    current = manager.store.get_run(run_id)
    manager.store.update_run(
        run_id,
        status="cancellation_pending",
        launcher_pid=None,
        worker_pid=None,
        pid=None,
    )
    observed = copy.deepcopy(current["input"]["remote_controller_state"])
    observed["remote"].update(
        {
            "pid": 321,
            "pgid": 321,
            "process_start_identity": "98765",
            "authoritative_state": "cancelled",
            "heartbeat_at": "2026-07-17T18:00:00Z",
            "cancellation_requested_at": "2026-07-17T17:59:00Z",
            "cancellation_completed_at": "2026-07-17T18:00:00Z",
            "publication_state": "ready",
        }
    )
    remote_result = {
        "returncode": -15,
        "ended_at": "2026-07-17T18:00:00Z",
        "authoritative_state": "cancelled",
    }
    publications: list[str] = []

    monkeypatch.setattr("codexbridge.job_manager.process_matches_identity", lambda *_: False)
    monkeypatch.setattr("codexbridge.job_manager.process_is_running", lambda *_: False)
    monkeypatch.setattr(
        "codexbridge.job_manager.probe_remote_controller_state",
        lambda *_: {"ok": True, "state": observed, "result": remote_result, "error": ""},
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.publish_run_result",
        lambda store, published_run_id: (
            publications.append(published_run_id) or {"ok": True, "error": ""}
        ),
    )

    stale = manager.store.get_run(run_id)
    manager._reconcile_run(stale)
    manager._reconcile_run(stale)

    terminal = manager.store.get_run(run_id)
    assert terminal["status"] == "cancelled"
    assert terminal["result"]["remote_controller_result"] == remote_result
    assert publications == [run_id]
    assert manager.locks.find_lock("sample", run_id) is None


def test_get_output_returns_bounded_live_tails(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    run = manager.store.get_run(response["run_id"])
    run_dir = Path(run["run_dir"])
    (run_dir / "stdout.txt").write_text("0123456789abcdef", encoding="utf-8")

    output = manager.get_output(response["run_id"], "combined", tail_bytes=6)

    assert output["ok"] is True
    assert output["tail_bytes"] == 6
    assert output["streams"]["stdout"]["text"] == "abcdef"
    assert output["streams"]["stdout"]["truncated"] is True
    assert output["streams"]["stderr"]["available"] is False


def test_get_control_status_reports_process_and_lock_state(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    monkeypatch.setattr(
        "codexbridge.job_manager.process_is_running", lambda pid: pid == 12345
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.process_matches_identity",
        lambda _pid, _identity: False,
    )

    control = manager.get_control_status(response["run_id"])

    assert control["ok"] is True
    assert control["launcher_pid"] == 12345
    assert control["launcher_running"] is True
    assert control["worker_pid"] == 0
    assert control["worker_running"] is False
    assert control["child_running"] is False
    assert control["lock"]["run_id"] == response["run_id"]


def test_launch_failure_after_persistence_is_terminal_and_unlocks(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "codexbridge.job_manager.subprocess.Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("launch boom")),
    )

    response = manager.start_plan("sample", "inspect docs")

    assert response["accepted"] is False
    assert response["status"] == "failed"
    assert response["run_id"]
    status = manager.get_status(response["run_id"])
    assert status["status"] == "failed"
    assert "worker_lease_token" not in status
    assert manager.get_result(response["run_id"])["classification"] == (
        "infrastructure_failure"
    )
    assert manager.locks.find_lock("sample", response["run_id"]) is None


def test_public_run_views_hide_worker_lease_token(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")

    assert manager.store.get_run(response["run_id"])["worker_lease_token"]
    assert "worker_lease_token" not in manager.get_status(response["run_id"])
    assert "worker_lease_token" not in manager.list_runs()[0]


def test_list_operation_locks_accepts_canonical_case_filter(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")

    locks = manager.list_operation_locks("Sample")

    assert [item["run_id"] for item in locks] == [response["run_id"]]


def test_duplicate_reconcilers_cannot_both_relaunch(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(response["run_id"], launcher_pid=None)
    observed = manager.store.get_run(response["run_id"])
    monkeypatch.setattr(
        "codexbridge.job_manager.process_is_running", lambda _pid: False
    )
    launches: list[str] = []

    def spawn(run_id: str, lease_token: str):
        launches.append(lease_token)
        return FakeProcess()

    monkeypatch.setattr(manager, "_spawn_worker", spawn)

    manager._reconcile_run(observed)
    manager._reconcile_run(observed)

    current = manager.store.get_run(response["run_id"])
    assert len(launches) == 1
    assert current["lease_generation"] == 2
    assert current["worker_lease_token"] == launches[0]
    assert current["launch_attempts"] == 2


def test_duplicate_reconcilers_record_one_adoption(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(
        response["run_id"],
        status="running",
        launcher_pid=None,
        worker_pid=222,
        worker_identity="222:windows:100",
    )
    observed = manager.store.get_run(response["run_id"])
    monkeypatch.setattr(
        "codexbridge.job_manager.process_matches_identity",
        lambda pid, identity: pid == 222 and identity == "222:windows:100",
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.process_is_running", lambda _pid: False
    )

    manager._reconcile_run(observed)
    manager._reconcile_run(observed)

    adoption_events = [
        event
        for event in manager.get_events(response["run_id"])
        if "identity verified" in event["message"]
    ]
    assert len(adoption_events) == 1
    assert manager.get_status(response["run_id"])["status"] == "running"


def test_remote_reconciliation_poller_deduplicates_and_stops_at_terminal(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_ssh_monitored_command("my_vps", "uptime")
    run_id = response["run_id"]
    current = manager.store.get_run(run_id)
    manager.store.conditional_update(
        run_id,
        fields={"status": "recovery_pending", "current_phase": "remote_reconciliation"},
        expected_statuses=(str(current["status"]),),
        expected_state_version=int(current["state_version"]),
        expected_lease_token=current["worker_lease_token"],
        expected_lease_generation=int(current["lease_generation"]),
    )
    started: list[object] = []
    released = threading.Event()

    class FakeThread:
        def __init__(self, *, target, name, daemon):
            assert name == f"codexbridge-remote-reconcile-{run_id}"
            assert daemon is True
            self.target = target

        def start(self):
            started.append(self.target)

    monkeypatch.setattr("codexbridge.job_manager.threading.Thread", FakeThread)

    assert manager._start_remote_reconciliation_poller(run_id) is True
    assert manager._start_remote_reconciliation_poller(run_id) is False
    assert len(started) == 1

    def fake_reconcile(run: dict) -> None:
        latest = manager.store.get_run(run_id)
        manager.store.transition_terminal(
            run_id,
            status="completed",
            result={"run_id": run_id, "status": "completed", "summary": "remote done"},
            expected_statuses=(str(latest["status"]),),
            expected_state_version=int(latest["state_version"]),
            expected_lease_token=latest["worker_lease_token"],
            expected_lease_generation=int(latest["lease_generation"]),
            summary="remote done",
        )
        released.set()

    monkeypatch.setattr(manager, "_reconcile_run", fake_reconcile)
    started[0]()

    assert released.is_set()
    assert manager.store.get_run(run_id)["status"] == "completed"
    assert run_id not in manager._remote_reconciliation_pollers


def test_cancellation_claim_prevents_late_completion(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(
        response["run_id"],
        status="running",
        launcher_pid=None,
        worker_pid=None,
        worker_identity="",
    )
    observed = manager.store.get_run(response["run_id"])

    cancelled = manager.cancel_run(response["run_id"])
    late_completion = manager.store.transition_terminal(
        response["run_id"],
        status="completed",
        result={"status": "completed", "summary": "late"},
        expected_statuses=("running",),
        expected_state_version=observed["state_version"],
        expected_lease_token=observed["worker_lease_token"],
        expected_lease_generation=observed["lease_generation"],
    )

    assert cancelled["status"] == "cancellation_pending"
    assert late_completion is None
    assert manager.get_status(response["run_id"])["status"] == (
        "cancellation_pending"
    )


def test_completion_prevents_late_cancellation(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(response["run_id"], status="running")
    observed = manager.store.get_run(response["run_id"])
    completed = manager.store.transition_terminal(
        response["run_id"],
        status="completed",
        result={"status": "completed", "summary": "winner"},
        expected_statuses=("running",),
        expected_state_version=observed["state_version"],
        expected_lease_token=observed["worker_lease_token"],
        expected_lease_generation=observed["lease_generation"],
    )

    cancelled = manager.cancel_run(response["run_id"])

    assert completed is not None
    assert cancelled["status"] == "completed"
    assert cancelled["cancelled"] is False
    assert manager.get_result(response["run_id"])["summary"] == "winner"
