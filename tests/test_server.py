from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from codexbridge.config import AppConfig, RepoConfig
from codexbridge.git_tools import CommitMetadataError
from codexbridge.server import parse_args
import codexbridge.server as server
import pytest


@pytest.fixture
def tmp_path() -> Path:
    path = (Path("runs") / "pytest_tmp" / uuid4().hex).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_server_cli_defaults_to_http_mcp_path() -> None:
    args = parse_args([])
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"


def test_server_cli_supports_explicit_mcp_command() -> None:
    args = parse_args(
        [
            "--config",
            "config.yaml",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--path",
            "/mcp",
        ]
    )
    assert args.config == "config.yaml"
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"


def test_server_cli_preserves_stdio_mode() -> None:
    args = parse_args(["--transport", "stdio"])
    assert args.transport == "stdio"


class FakeSupervisorService:
    def start_supervised_recovery_task(self, *args):
        return {"tool": "start", "args": args}

    def get_status(self, supervisor_id):
        return {"tool": "status", "supervisor_id": supervisor_id}

    def get_events(self, supervisor_id, limit):
        return [{"tool": "events", "limit": limit}]

    def get_result(self, supervisor_id):
        return {"tool": "result"}

    def resume(self, supervisor_id):
        return {"tool": "resume"}

    def pause(self, supervisor_id):
        return {"tool": "pause"}

    def cancel(self, supervisor_id):
        return {"tool": "cancel"}

    def get_notifications(self, supervisor_id, delivery_status, limit):
        return [
            {
                "tool": "notifications",
                "delivery_status": delivery_status,
                "limit": limit,
            }
        ]

    def get_resume_prompt(self, supervisor_id):
        return {"tool": "prompt"}


class FakeWorkflowManager:
    def start_workflow(self, repo_name, objective, steps):
        return {
            "tool": "start_workflow",
            "repo_name": repo_name,
            "objective": objective,
            "steps": steps,
        }

    def get_status(self, workflow_id):
        return {"tool": "workflow_status", "workflow_id": workflow_id}

    def get_events(self, workflow_id, limit):
        return [{"tool": "workflow_events", "workflow_id": workflow_id, "limit": limit}]

    def get_result(self, workflow_id):
        return {"tool": "workflow_result", "workflow_id": workflow_id}

    def cancel_workflow(self, workflow_id):
        return {"tool": "cancel_workflow", "workflow_id": workflow_id}


def test_server_supervisor_tool_functions_delegate(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "get_supervisor_service", lambda: FakeSupervisorService()
    )
    supervisor_id = "20260428T120000Z_supervisor_abcdef12"
    assert (
        server.start_supervised_recovery_task("repo", "objective", "task")["tool"]
        == "start"
    )
    assert server.get_supervisor_status(supervisor_id)["tool"] == "status"
    assert server.get_supervisor_events(supervisor_id, 5)["events"][0]["limit"] == 5
    assert server.get_supervisor_result(supervisor_id)["tool"] == "result"
    assert server.resume_supervisor(supervisor_id)["tool"] == "resume"
    assert server.pause_supervisor(supervisor_id)["tool"] == "pause"
    assert server.cancel_supervisor(supervisor_id)["tool"] == "cancel"
    assert (
        server.get_supervisor_notifications(supervisor_id, "pending", 3)[
            "notifications"
        ][0]["delivery_status"]
        == "pending"
    )
    assert server.get_supervisor_resume_prompt(supervisor_id)["tool"] == "prompt"


def test_server_workflow_tool_functions_delegate(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_workflow_manager", lambda: FakeWorkflowManager())
    workflow_id = "20260711T203357Z_workflow_deadbeef"
    started = server.start_workflow(
        "repo",
        "objective",
        [{"id": "one", "type": "project_command", "parameters": {"command_id": "pytest"}}],
    )
    assert started["tool"] == "start_workflow"
    assert server.get_workflow_status(workflow_id)["tool"] == "workflow_status"
    assert server.get_workflow_events(workflow_id, 7)["events"][0]["limit"] == 7
    assert server.get_workflow_result(workflow_id)["tool"] == "workflow_result"
    assert server.cancel_workflow(workflow_id)["tool"] == "cancel_workflow"


def test_server_docker_tools_delegate(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  api:\n    image: example/api\n", encoding="utf-8"
    )
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        docker={"enabled": True},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_list_docker_capabilities",
        lambda cfg, repo_config=None: {
            "ok": True,
            "enabled": cfg.docker.enabled,
            "actions": ["compose_up"],
            "error": "",
        },
    )
    monkeypatch.setattr(
        server,
        "_docker_health",
        lambda cfg: {"ok": True, "enabled": cfg.docker.enabled, "error": ""},
    )
    monkeypatch.setattr(
        server,
        "_run_docker_inspection",
        lambda cfg, root, repo_config, operation, **kwargs: {
            "ok": True,
            "action": operation,
            "argv": ["docker", "compose", "ps"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "ok",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )

    class FakeJobs:
        def start_docker_action(self, repo_name, action, **kwargs):
            return {
                "ok": True,
                "run_id": "run_docker",
                "repo_name": repo_name,
                "action": action,
                "kwargs": kwargs,
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())

    assert server.list_docker_capabilities("repo")["enabled"] is True
    assert server.docker_health()["ok"] is True
    assert server.docker_inspect("repo", "compose_ps")["action"] == "compose_ps"
    queued = server.start_docker_action_async(
        "repo", "compose_up", services=["api"], build=True
    )
    assert queued["run_id"] == "run_docker"
    assert queued["kwargs"]["services"] == ["api"]
    assert queued["kwargs"]["build"] is True


def test_server_cloudflare_tools_delegate(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={
            "repo": RepoConfig(path=str(tmp_path), cloudflare_profiles=["production"])
        },
        cloudflare={
            "enabled": True,
            "allow_dns_write": True,
            "profiles": {
                "production": {
                    "zone_id": "a" * 32,
                    "zone_name": "example.com",
                    "allowed_dns_names": ["api.example.com"],
                }
            },
        },
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_list_cloudflare_capabilities",
        lambda cfg, repo_name="": {
            "ok": True,
            "enabled": cfg.cloudflare.enabled,
            "actions": ["dns_create"],
            "error": "",
        },
    )
    monkeypatch.setattr(
        server,
        "_cloudflare_health",
        lambda cfg, profile_id: {
            "ok": True,
            "profile_id": profile_id,
            "zone_name": "example.com",
            "error": "",
        },
    )
    monkeypatch.setattr(
        server,
        "_run_cloudflare_inspection",
        lambda cfg, profile_id, operation, **kwargs: {
            "ok": True,
            "profile_id": profile_id,
            "operation": operation,
            "result": [{"id": "c" * 32}],
            "error": "",
        },
    )

    class FakeJobs:
        def start_cloudflare_action(self, repo_name, profile_id, action, **kwargs):
            return {
                "ok": True,
                "run_id": "run_cloudflare",
                "repo_name": repo_name,
                "profile_id": profile_id,
                "action": action,
                "kwargs": kwargs,
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())

    assert server.list_cloudflare_capabilities("repo")["actions"] == ["dns_create"]
    assert server.cloudflare_health("repo", "production")["zone_name"] == "example.com"
    inspected = server.cloudflare_inspect(
        "repo",
        "production",
        "dns_records",
        name="api.example.com",
        record_type="A",
    )
    assert inspected["operation"] == "dns_records"
    queued = server.start_cloudflare_action_async(
        "repo",
        "production",
        "dns_create",
        payload={
            "type": "A",
            "name": "api.example.com",
            "content": "192.0.2.10",
        },
    )
    assert queued["run_id"] == "run_cloudflare"
    assert queued["kwargs"]["payload"]["name"] == "api.example.com"


def test_server_extended_ssh_tools_delegate(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        ssh={
            "enabled": True,
            "allow_transfer": True,
            "allow_deploy": True,
            "allow_admin": True,
            "hosts": {
                "my_vps": {
                    "ssh_alias": "my-vps",
                    "allowed_remote_roots": ["/srv/app", "/var/log"],
                    "allowed_executables": ["docker", "git", "curl"],
                    "deployment_profiles": {
                        "app": {"repo_name": "repo", "remote_root": "/srv/app"}
                    },
                }
            },
        },
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_list_ssh_capabilities",
        lambda cfg: {"ok": True, "enabled": True, "hosts": [], "error": ""},
    )
    monkeypatch.setattr(
        server,
        "_enrich_ssh_capabilities",
        lambda cfg, result: {**result, "actions": ["service_restart"]},
    )
    monkeypatch.setattr(
        server,
        "_ssh_host_health",
        lambda cfg, host_id: {"ok": True, "host_id": host_id, "status": "ok"},
    )
    monkeypatch.setattr(
        server,
        "_run_ssh_inspection",
        lambda cfg, host_id, operation, **kwargs: {
            "ok": True,
            "host_id": host_id,
            "operation": operation,
            "stdout": "healthy",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "output_truncated": False,
            "error": "",
        },
    )

    class FakeJobs:
        def start_ssh_monitored_command(self, host_id, command_id):
            return {
                "ok": True,
                "run_id": "run_monitored",
                "host_id": host_id,
                "command_id": command_id,
            }

        def start_ssh_action(self, host_id, action, **kwargs):
            return {
                "ok": True,
                "run_id": "run_action",
                "host_id": host_id,
                "action": action,
                "kwargs": kwargs,
            }

        def start_ssh_transfer(self, host_id, direction, **kwargs):
            return {
                "ok": True,
                "run_id": "run_transfer",
                "host_id": host_id,
                "direction": direction,
                "kwargs": kwargs,
            }

        def start_ssh_deployment(self, host_id, deployment_id, **kwargs):
            return {
                "ok": True,
                "run_id": "run_deploy",
                "host_id": host_id,
                "deployment_id": deployment_id,
                "kwargs": kwargs,
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())

    assert server.list_ssh_capabilities()["actions"] == ["service_restart"]
    assert server.ssh_host_health("my_vps")["status"] == "ok"
    assert server.ssh_inspect("my_vps", "uptime")["stdout"] == "healthy"
    action = server.start_ssh_action_async(
        "my_vps", "service_restart", target="app.service"
    )
    transfer = server.start_ssh_transfer_async(
        "my_vps",
        "upload",
        "repo",
        "README.md",
        "/srv/app/README.md",
    )
    deployment = server.start_ssh_deployment_async(
        "my_vps", "app", "CONFIRM_SSH_HIGH_RISK"
    )
    assert action["run_id"] == "run_action"
    assert action["kwargs"]["target"] == "app.service"
    assert transfer["run_id"] == "run_transfer"
    assert transfer["kwargs"]["repo_name"] == "repo"
    assert deployment["run_id"] == "run_deploy"
    assert deployment["kwargs"]["confirmation"] == "CONFIRM_SSH_HIGH_RISK"
    monitored = server.start_ssh_monitored_command_async("my_vps", "uptime")
    assert monitored["run_id"] == "run_monitored"


def test_commit_tool_returns_structured_metadata_rejection(
    monkeypatch,
    tmp_path,
) -> None:
    config = AppConfig(repos={"repo": RepoConfig(path=str(tmp_path))})
    config.config_dir = tmp_path
    monkeypatch.setattr(server, "get_config", lambda: config)
    monkeypatch.setattr(
        server,
        "_repo_context",
        lambda _repo_name: ("repo", tmp_path, "repo"),
    )
    monkeypatch.setattr(
        server,
        "repository_operation_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )

    def reject_metadata(*_args, **_kwargs):
        raise CommitMetadataError(
            "description",
            "too_long",
            "Commit description exceeds the configured limit",
            files_validated=True,
        )

    monkeypatch.setattr(server, "commit_files", reject_metadata)

    result = server.commit_selected_files(
        "repo",
        ["safe.txt"],
        "fix: metadata handling",
        "ordinary description",
    )

    expected = {
        "ok": False,
        "repo_name": "repo",
        "files_validated": True,
        "blocked_field": "description",
        "reason_code": "too_long",
        "reason": "Commit description exceeds the configured limit",
        "error": "Commit description exceeds the configured limit",
    }
    assert {key: result[key] for key in expected} == expected
    assert len(result["server_build_hash"]) == 64
    assert len(result["schema_hash"]) == 64
    assert result["capability_epoch"]


def test_reload_service_delegates_and_refreshes_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    refreshed = {"done": False}

    monkeypatch.setattr(server, "get_config_path", lambda: config_path)
    monkeypatch.setattr(
        server,
        "_reload_service",
        lambda *_args, **_kwargs: {
            "ok": True,
            "reloaded": ["config"],
            "requested_modules": ["config"],
            "resolved_modules": [],
            "restart_required": [],
            "message": "",
        },
    )
    monkeypatch.setattr(
        server,
        "apply_reloaded_config",
        lambda path: refreshed.update(done=path == config_path) or object(),
    )
    monkeypatch.setattr(server, "set_config", lambda *_args, **_kwargs: None)

    result = server.reload_service(["config"])

    assert result["ok"] is True
    assert refreshed["done"] is True


def test_server_reload_lifecycle_tools_delegate(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_validate_config_candidate",
        lambda path: {"ok": True, "candidate_config_path": str(path), "error": ""},
    )
    monkeypatch.setattr(
        server,
        "_get_reload_status",
        lambda: {"ok": True, "status": "active", "error": ""},
    )
    monkeypatch.setattr(
        server,
        "_rollback_service",
        lambda: {"ok": True, "rolled_back": True, "config": config, "error": ""},
    )

    assert server.validate_service_config()["ok"] is True
    assert server.get_service_reload_status()["status"] == "active"
    assert server.rollback_service()["rolled_back"] is True


def test_repo_context_discovers_direct_child_repo_without_explicit_entry(
    tmp_path,
) -> None:
    root = tmp_path / "Github"
    known = root / "Known"
    known.mkdir(parents=True)
    (known / ".git").mkdir()
    andia_repo = root / "Andia_Beauty"
    andia_repo.mkdir(parents=True)
    (andia_repo / ".git").mkdir()
    config = AppConfig(
        repos={"known": RepoConfig(path=str(known))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")

    canonical_name, repo_root, requested_name = server._repo_context("Andia_Beauty")

    assert canonical_name == "andia_beauty"
    assert repo_root == andia_repo.resolve()
    assert requested_name == "Andia_Beauty"
    canonical_context = server._repo_context("andia_beauty")
    assert canonical_context[0] == canonical_name
    assert canonical_context[1] == repo_root


def test_run_project_command_accepts_case_insensitive_repo_name(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={
            "codexbridge": RepoConfig(
                path=str(tmp_path),
                command_profiles=[
                    {"command_id": "custom", "argv": ["python", "-c", "print(1)"]}
                ],
            )
        },
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "run_command_profile",
        lambda profile, repo_root: {
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
    monkeypatch.setattr(
        server,
        "repository_operation_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )

    result = server.run_project_command("CodexBridge", "custom")

    assert result["ok"] is True
    assert result["repo_name"] == "codexbridge"
    assert result["requested_repo_name"] == "CodexBridge"


def test_run_project_command_finalizes_write_profile_changes(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={
            "repo": RepoConfig(
                path=str(tmp_path),
                command_profiles=[
                    {
                        "command_id": "generate",
                        "argv": ["python", "-c", "print(1)"],
                        "writes_files": True,
                    }
                ],
            )
        },
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "repository_operation_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    states = iter(
        [
            ["preexisting.txt"],
            ["preexisting.txt", "generated.txt"],
        ]
    )
    monkeypatch.setattr(server, "_changed_files", lambda _root: next(states))
    monkeypatch.setattr(
        server,
        "run_command_profile",
        lambda profile, repo_root: {
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
    finalized: list[list[str]] = []
    monkeypatch.setattr(
        server,
        "finalize_explicit_changes",
        lambda repo_root, paths, *, tool_name, run_id="", require_commit_report=True: (
            finalized.append(list(paths))
            or {
                "commit_required": True,
                "commit_attempted": True,
                "commit_hash": "abc123",
                "commit_error": "",
                "commit_result": {"ok": True},
            }
        ),
    )

    result = server.run_project_command("repo", "generate")

    assert result["ok"] is True
    assert finalized == [["generated.txt"]]
    assert result["commit_hash"] == "abc123"


def test_commit_all_changes_rejected_by_repo_policy(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "repository_operation_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )

    result = server.commit_all_changes("repo", "chore: everything")

    assert result["ok"] is False
    assert result["reason_code"] == "commit_all_disabled"
    assert result["blocked_field"] == "policy"


def test_commit_selected_files_respects_repo_policy_options(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={
            "repo": RepoConfig(
                path=str(tmp_path),
                refuse_unrelated_staged_files=False,
                require_commit_report=False,
            )
        },
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "repository_operation_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    captured: dict[str, object] = {}

    def fake_commit(repo_root, files, title, description="", **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "commit_hash": "a" * 40,
            "files_validated": True,
            "error": "",
        }

    monkeypatch.setattr(server, "commit_files", fake_commit)

    result = server.commit_selected_files("repo", ["safe.txt"], "fix: scoped")

    assert result["ok"] is True
    assert captured["refuse_unrelated_staged_files"] is False
    assert captured["require_commit_report"] is False


def test_preview_tools_preserve_canonical_repo_name(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"codexbridge": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_repo_writer",
        type(
            "Writer",
            (),
            {
                "preview_repo_patch": staticmethod(
                    lambda repo_root, operations, runs_dir: {
                        "ok": True,
                        "patch_id": "patch_1",
                        "diff": "",
                        "changed_files": [],
                        "changed_lines": 0,
                        "changed_bytes": 0,
                        "git_head": "",
                        "validation_errors": [],
                        "error": "",
                    }
                )
            },
        ),
    )

    result = server.preview_repo_patch("CodexBridge", [])

    assert result["repo_name"] == "codexbridge"
    assert result["requested_repo_name"] == "CodexBridge"


def test_direct_write_tools_finalize_commits(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        runs_dir=str(tmp_path / "runs"),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "repository_operation_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(server, "_get_runs_dir", lambda: tmp_path / "runs")
    finalized: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        server,
        "finalize_explicit_changes",
        lambda repo_root, paths, *, tool_name, run_id="", require_commit_report=True: (
            finalized.append((tool_name, list(paths)))
            or {
                "commit_required": True,
                "commit_attempted": True,
                "commit_hash": "a" * 40,
                "commit_error": "",
                "commit_result": {"ok": True},
            }
        ),
    )
    monkeypatch.setattr(
        server,
        "_repo_writer",
        type(
            "Writer",
            (),
            {
                "apply_repo_patch": staticmethod(
                    lambda repo_root, operations, patch_id, runs_dir: {
                        "ok": True,
                        "patch_id": patch_id,
                        "repo_name": "",
                        "changed_files": ["patched.py"],
                        "results": [{"path": "patched.py", "sha256": "a" * 64}],
                        "git_head": "b" * 40,
                        "error": "",
                    }
                ),
                "apply_previewed_repo_change": staticmethod(
                    lambda repo_root, patch_id, runs_dir: {
                        "ok": True,
                        "patch_id": patch_id,
                        "repo_name": "",
                        "changed_files": ["previewed.py"],
                        "results": [{"path": "previewed.py", "sha256": "a" * 64}],
                        "git_head": "b" * 40,
                        "error": "",
                    }
                ),
                "create_repo_file": staticmethod(
                    lambda repo_root, path, content: {
                        "ok": True,
                        "repo_name": "",
                        "path": path,
                        "changed_files": [path],
                        "sha256": "a" * 64,
                        "size_bytes": len(content),
                        "error": "",
                    }
                ),
                "delete_repo_file": staticmethod(
                    lambda repo_root, path, expected_sha256, runs_dir: {
                        "ok": True,
                        "repo_name": "",
                        "path": path,
                        "changed_files": [path],
                        "rollback_id": "delete_1",
                        "error": "",
                    }
                ),
                "move_repo_file": staticmethod(
                    lambda repo_root, source_path, destination_path, expected_sha256, runs_dir: {
                        "ok": True,
                        "repo_name": "",
                        "source_path": source_path,
                        "destination_path": destination_path,
                        "changed_files": [source_path, destination_path],
                        "sha256": "a" * 64,
                        "rollback_id": "move_1",
                        "error": "",
                    }
                ),
                "revert_managed_patch": staticmethod(
                    lambda repo_root, patch_id, runs_dir: {
                        "ok": True,
                        "patch_id": patch_id,
                        "repo_name": "",
                        "reverted_files": ["reverted.py"],
                        "changed_files": ["reverted.py"],
                        "error": "",
                    }
                ),
                "_sha256_text": staticmethod(lambda content: "c" * 64),
            },
        ),
    )

    assert server.apply_repo_patch("repo", [], "patch_1")["commit_attempted"] is True
    assert (
        server.apply_previewed_repo_change("repo", "patch_2")["commit_attempted"]
        is True
    )
    assert (
        server.create_repo_file("repo", "new.py", "pass\n")["commit_attempted"] is True
    )
    assert (
        server.delete_repo_file("repo", "old.py", "a" * 64)["commit_attempted"] is True
    )
    assert (
        server.move_repo_file("repo", "src.py", "dst.py", "a" * 64)["commit_attempted"]
        is True
    )
    assert server.revert_managed_patch("repo", "patch_3")["commit_attempted"] is True
    assert finalized == [
        ("apply_repo_patch", ["patched.py"]),
        ("apply_previewed_repo_change", ["previewed.py"]),
        ("create_repo_file", ["new.py"]),
        ("delete_repo_file", ["old.py"]),
        ("move_repo_file", ["src.py", "dst.py"]),
        ("revert_managed_patch", ["reverted.py"]),
    ]


def test_direct_write_commit_failure_returns_commit_failed_status(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        runs_dir=str(tmp_path / "runs"),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "repository_operation_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        server,
        "finalize_explicit_changes",
        lambda repo_root, paths, *, tool_name, run_id="", require_commit_report=True: {
            "commit_required": True,
            "commit_attempted": True,
            "commit_hash": "",
            "commit_error": "simulated commit failure",
            "commit_result": {"ok": False},
        },
    )
    monkeypatch.setattr(
        server,
        "_repo_writer",
        type(
            "Writer",
            (),
            {
                "create_repo_file": staticmethod(
                    lambda repo_root, path, content: {
                        "ok": True,
                        "repo_name": "",
                        "path": path,
                        "changed_files": [path],
                        "sha256": "a" * 64,
                        "size_bytes": len(content),
                        "error": "",
                    }
                ),
                "_sha256_text": staticmethod(lambda content: "c" * 64),
            },
        ),
    )

    result = server.create_repo_file("repo", "new.py", "pass\n")

    assert result["ok"] is False
    assert result["status"] == "commit_failed"
    assert result["commit_error"] == "simulated commit failure"
    assert result["path"] == "new.py"


def test_dry_run_stage_manifest_accepts_include_ignored(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        server,
        "_dry_run_stage_manifest",
        lambda repo_root, include_ignored=False: captured.setdefault(
            "value",
            {
                "ok": True,
                "staged": [],
                "unstaged": [],
                "untracked": [],
                "deleted": [],
                "ignored": [".codexbridge/wiki/overview.md"] if include_ignored else [],
                "renamed": [],
                "tool_owned": [],
                "files": [],
                "git_status": "",
            },
        ),
    )

    result = server.dry_run_stage_manifest("repo", include_ignored=True)

    assert result["ignored"] == [".codexbridge/wiki/overview.md"]


def test_inspect_commit_range_uses_canonical_repo_context(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"codexbridge": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_inspect_commit_range",
        lambda repo_root, base_commit, head_commit: {
            "ok": True,
            "base_commit": base_commit,
            "head_commit": head_commit,
            "name_status": "M\tREADME.md\n",
            "diff_stat": " README.md | 1 +\n",
            "diff": "diff --git a/README.md b/README.md\n",
            "truncated": False,
            "error": "",
        },
    )

    result = server.inspect_commit_range("CodexBridge", "a" * 40, "b" * 40)

    assert result["repo_name"] == "codexbridge"
    assert result["requested_repo_name"] == "CodexBridge"


def test_inspect_repo_status_compact_normalizes_live_git_shapes(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "inspect_status_compact",
        lambda repo_root: {
            "branch": "main",
            "recent_commits": "abc123 first\n\ndef456 second\n",
            "diff_stat": " 1 file changed\n",
            "complete_status_scan": True,
            "total_status_entry_count": 2,
            "returned_entry_count": 1,
            "collapsed_tool_owned_count": 1,
            "sampled_tool_owned_count": 1,
            "unsampled_tool_owned_count": 0,
            "files": [
                {
                    "path": "codexbridge/server.py",
                    "size_bytes": 1,
                    "line_count": 1,
                    "tool_owned": False,
                    "index_status": "M",
                    "worktree_status": " ",
                }
            ],
            "tool_owned_summary": {
                "total_bytes": 3,
                "root_group_counts": {".codex-tmp": 1},
                "sample": [
                    {
                        "path": ".codex-tmp/run.txt",
                        "size_bytes": 3,
                        "line_count": 1,
                        "tool_owned": True,
                        "index_status": "?",
                        "worktree_status": "?",
                    }
                ],
                "truncated": False,
            },
            "fallback_tool": "inspect_repo_status",
        },
    )

    result = server.inspect_repo_status_compact("repo")

    assert result["recent_commits"] == ["abc123 first", "def456 second"]
    assert "changed_files" not in result
    assert "git_status" not in result
    assert result["tool_owned_summary"]["sample"][0]["path"] == ".codex-tmp/run.txt"


def test_repo_status_compact_schema_uses_new_compact_fields() -> None:
    properties = server.REPO_STATUS_COMPACT_OUTPUT["properties"]

    assert "changed_files" not in properties
    assert "complete_status_scan" in properties
    assert "total_status_entry_count" in properties
    assert "returned_entry_count" in properties
    assert "collapsed_tool_owned_count" in properties
    assert "sampled_tool_owned_count" in properties
    assert "unsampled_tool_owned_count" in properties
    assert "complete_scan" not in properties
    assert "omitted_tool_owned_count" not in properties

    summary_properties = properties["tool_owned_summary"]["properties"]
    assert "count" not in summary_properties
    assert "total_known_line_count" not in summary_properties


def test_server_ssh_profile_preview_and_status_delegate(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(repo))},
        config_dir=tmp_path,
        runs_dir=str(tmp_path / "runs"),
    )
    server.set_config(config, config_path)
    captured: dict[str, object] = {}

    def fake_preview(path, runs_dir, action, host_id, **kwargs):
        captured.update(
            {
                "path": path,
                "runs_dir": runs_dir,
                "action": action,
                "host_id": host_id,
                **kwargs,
            }
        )
        return {"ok": True, "change_id": "change_1", "status": "previewed"}

    monkeypatch.setattr(server, "_preview_ssh_profile_change", fake_preview)
    monkeypatch.setattr(
        server,
        "_get_ssh_profile_change_status",
        lambda path, runs_dir, change_id: {
            "ok": True,
            "change_id": change_id,
            "status": "previewed",
            "path": str(path),
            "runs_dir": str(runs_dir),
        },
    )

    preview = server.preview_ssh_profile_change(
        "add_host", "beta", host_config={"ssh_alias": "beta-host"}
    )
    status = server.get_ssh_profile_change_status("change_1")

    assert preview["change_id"] == "change_1"
    assert captured["path"] == config_path
    assert captured["runs_dir"] == tmp_path / "runs"
    assert captured["action"] == "add_host"
    assert captured["host_id"] == "beta"
    assert captured["host_config"] == {"ssh_alias": "beta-host"}
    assert status["change_id"] == "change_1"


def test_server_apply_ssh_profile_change_uses_global_lock_and_activates(
    monkeypatch, tmp_path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(repo))},
        config_dir=tmp_path,
        runs_dir=str(tmp_path / "runs"),
    )
    server.set_config(config, config_path)
    locks: list[dict[str, object]] = []
    activated: list[tuple[object, object]] = []

    def fake_lock(*args, **kwargs):
        locks.append({"args": args, **kwargs})
        return nullcontext()

    def fake_apply(path, runs_dir, change_id, *, activate):
        activation = activate(path)
        return {
            "ok": True,
            "change_id": change_id,
            "status": "applied",
            "activation": activation,
            "runs_dir": str(runs_dir),
        }

    monkeypatch.setattr(server, "repository_operation_lock", fake_lock)
    monkeypatch.setattr(server, "_apply_ssh_profile_change", fake_apply)
    monkeypatch.setattr(
        server,
        "_reload_service",
        lambda path, modules: {"ok": True, "status": "active", "modules": modules},
    )
    monkeypatch.setattr(server, "apply_reloaded_config", lambda path: config)
    monkeypatch.setattr(
        server,
        "set_config",
        lambda active, path=None: activated.append((active, path)),
    )

    result = server.apply_ssh_profile_change("change_1")

    assert result["ok"] is True
    assert result["activation"]["modules"] == ["config"]
    assert locks[0]["repo_name"] == "__codexbridge_config__"
    assert locks[0]["tool"] == "apply_ssh_profile_change"
    assert locks[0]["normalized_input"] == {"change_id": "change_1"}
    assert activated == [(config, config_path)]


def test_server_run_control_output_and_lock_tools_delegate(monkeypatch) -> None:
    class Manager:
        def get_control_status(self, run_id):
            return {"ok": True, "run_id": run_id, "status": "running"}

        def get_output(self, run_id, stream, tail_bytes):
            return {
                "ok": True,
                "run_id": run_id,
                "stream": stream,
                "tail_bytes": tail_bytes,
            }

        def list_operation_locks(self, repo_name=None, *, include_stale=True):
            return [
                {
                    "repo_name": repo_name or "sample",
                    "run_id": "run_1",
                    "stale": not include_stale,
                }
            ]

    monkeypatch.setattr(server, "get_job_manager", lambda: Manager())

    control = server.get_run_control_status("run_1")
    output = server.get_run_output("run_1", "stdout", 123)
    locks = server.list_operation_locks("sample", include_stale=False)

    assert control["run_id"] == "run_1"
    assert output["ok"] is True
    assert output["run_id"] == "run_1"
    assert output["stream"] == "stdout"
    assert output["tail_bytes"] == 123
    assert output["server_build_hash"]
    assert output["schema_hash"]
    assert output["capability_epoch"]
    assert locks["ok"] is True
    assert locks["count"] == 1
    assert locks["locks"][0]["repo_name"] == "sample"


def test_server_ssh_probe_tools_delegate_to_structured_collectors(monkeypatch) -> None:
    config = object()
    calls: list[tuple[str, object, str]] = []
    monkeypatch.setattr(server, "get_config", lambda: config)
    monkeypatch.setattr(
        server,
        "_run_ssh_environment_probe",
        lambda active, host_id: (
            calls.append(("environment", active, host_id))
            or {"ok": True, "host_id": host_id, "status": "ok"}
        ),
    )
    monkeypatch.setattr(
        server,
        "_run_ssh_gpu_telemetry",
        lambda active, host_id: (
            calls.append(("gpu", active, host_id))
            or {"ok": True, "host_id": host_id, "status": "ok"}
        ),
    )

    environment = server.ssh_environment_probe("gpu_host")
    gpu = server.ssh_gpu_telemetry("gpu_host")

    assert environment["host_id"] == "gpu_host"
    assert gpu["host_id"] == "gpu_host"
    assert calls == [
        ("environment", config, "gpu_host"),
        ("gpu", config, "gpu_host"),
    ]
    assert environment["server_build_hash"]
    assert gpu["schema_hash"]
