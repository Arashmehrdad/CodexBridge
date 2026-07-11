from __future__ import annotations

import json
from pathlib import Path

import pytest

from codexbridge.config import (
    AppConfig,
    CloudflareProfileConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHDeploymentProfileConfig,
    SSHHostConfig,
)
from codexbridge.job_manager import JobManager


class FakeProcess:
    pid = 12345


def make_git_repo(path: Path) -> None:
    path.mkdir()
    (path / ".git").mkdir()


def make_manager(tmp_path: Path, monkeypatch) -> JobManager:
    repo = tmp_path / "repo"
    make_git_repo(repo)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
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
                        )
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
    assert status["input"] == {"host_id": "my_vps", "command_id": "uptime"}


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
    assert status["input"] == {"host_id": "my_vps", "command_id": "uptime"}


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
        "my_vps", "service_restart", target="sample.service"
    )
    assert action["accepted"] is True
    assert action["action"] == "service_restart"
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
    assert manager.get_status(transfer["run_id"])["tool"] == "ssh_transfer"
    manager.locks.release("ssh:my_vps", transfer["run_id"])

    deployment = manager.start_ssh_deployment(
        "my_vps",
        "sample_app",
        confirmation=manager.config.ssh.confirmation_token,
    )
    assert deployment["accepted"] is True
    assert deployment["deployment_id"] == "sample_app"
    deployment_status = manager.get_status(deployment["run_id"])
    assert deployment_status["tool"] == "ssh_deployment"
    assert deployment_status["risk_level"] == "high"


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


def test_reconcile_startup_marks_running_failed(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(response["run_id"], status="running")
    assert manager.reconcile_startup() == 1
    assert manager.get_status(response["run_id"])["status"] == "failed"


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
    assert status["status"] == "queued"
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

    assert terminated == [222, 111]
    assert cancelled["ok"] is True
    assert cancelled["cancelled"] is True
    assert cancelled["termination_confirmed"] is True
    assert manager.get_status(response["run_id"])["status"] == "cancelled"
    assert manager.locks.find_lock("sample", response["run_id"]) is None


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

    control = manager.get_control_status(response["run_id"])

    assert control["ok"] is True
    assert control["worker_pid"] == 12345
    assert control["worker_running"] is True
    assert control["child_running"] is False
    assert control["lock"]["run_id"] == response["run_id"]


def test_list_operation_locks_accepts_canonical_case_filter(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")

    locks = manager.list_operation_locks("Sample")

    assert [item["run_id"] for item in locks] == [response["run_id"]]
