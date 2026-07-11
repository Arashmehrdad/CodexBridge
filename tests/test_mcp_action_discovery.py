from __future__ import annotations

import asyncio
import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any

from jsonschema import Draft202012Validator, validate

from codexbridge.config import AppConfig, LocalModelConfig, RepoConfig
from codexbridge.knowledge_tools_integration import register_knowledge_tools
import codexbridge.server as server


ACTION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
EXPECTED_EXPOSED_ACTIONS = {
    "list_capabilities",
    "inspect_repo_status",
    "inspect_repo_status_compact",
    "codex_plan_task",
    "codex_implement_task",
    "get_latest_run_result",
    "git_diff_summary",
    "commit_selected_files",
    "run_local_self_check",
    "local_model_health",
    "list_docker_capabilities",
    "docker_health",
    "docker_inspect",
    "start_docker_action_async",
    "list_cloudflare_capabilities",
    "cloudflare_health",
    "cloudflare_inspect",
    "start_cloudflare_action_async",
    "list_ssh_capabilities",
    "preview_ssh_profile_change",
    "get_ssh_profile_change_status",
    "apply_ssh_profile_change",
    "ssh_host_health",
    "ssh_environment_probe",
    "ssh_gpu_telemetry",
    "ssh_inspect",
    "start_ssh_command_async",
    "start_ssh_monitored_command_async",
    "start_ssh_action_async",
    "start_ssh_transfer_async",
    "start_ssh_deployment_async",
    "start_external_fixture_validation_async",
    "start_codex_plan_task_async",
    "start_codex_implement_task_async",
    "start_project_command_async",
    "start_pytest_path_async",
    "start_py_compile_path_async",
    "start_bash_n_path_async",
    "start_json_validation_path_async",
    "start_git_readonly_async",
    "get_run_status",
    "get_run_control_status",
    "get_run_output",
    "list_operation_locks",
    "get_run_events",
    "get_run_result",
    "list_runs",
    "cancel_run",
    "reload_service",
    "validate_service_config",
    "get_service_reload_status",
    "rollback_service",
    "start_supervised_recovery_task",
    "get_supervisor_status",
    "get_supervisor_events",
    "get_supervisor_result",
    "resume_supervisor",
    "pause_supervisor",
    "cancel_supervisor",
    "get_supervisor_notifications",
    "get_supervisor_resume_prompt",
    # repo reader tools (batch)
    "list_repo_files",
    "read_repo_file",
    "search_repo_text",
    "get_recently_modified_files",
    "repo_git_status",
    "repo_git_diff",
    "inspect_commit_range",
    # controlled local coding tools
    "preview_repo_patch",
    "preview_repo_file_creation",
    "preview_repo_file_removal",
    "get_patch_status",
    "preview_managed_artifact_cleanup",
    "apply_managed_artifact_cleanup",
    "apply_repo_patch",
    "apply_previewed_repo_change",
    "create_repo_file",
    "delete_repo_file",
    "move_repo_file",
    "revert_managed_patch",
    "run_project_command",
    "git_log",
    "read_repo_files",
    "create_git_branch",
    "dry_run_stage_manifest",
    "stage_all",
    "unstage_all",
    "commit_all_changes",
}
RETIRED_DIRECT_ACTIONS = {
    "apply_repo_patch",
    "codex_implement_task",
    "codex_plan_task",
    "commit_all_changes",
    "create_repo_file",
    "delete_repo_file",
    "dry_run_stage_manifest",
    "get_latest_run_result",
    "get_supervisor_notifications",
    "get_supervisor_resume_prompt",
    "git_diff_summary",
    "read_repo_file",
    "repo_git_status",
    "run_project_command",
    "ssh_host_health",
    "stage_all",
    "unstage_all",
}
WORKFLOW_AND_KNOWLEDGE_ACTIONS = {
    "cancel_workflow",
    "get_workflow_events",
    "get_workflow_result",
    "get_workflow_status",
    "read_repo_wiki",
    "refresh_repo_wiki",
    "remember_repo_decision",
    "search_repo_knowledge",
    "start_workflow",
}
EXPECTED_EXPOSED_ACTIONS = (
    EXPECTED_EXPOSED_ACTIONS - RETIRED_DIRECT_ACTIONS
) | WORKFLOW_AND_KNOWLEDGE_ACTIONS
assert len(EXPECTED_EXPOSED_ACTIONS) == 80

REALISTIC_ACTION_OUTPUTS = {
    "list_capabilities": {
        "ok": True,
        "action_names": ["list_capabilities"],
        "actions": [],
        "patch_operation_schema": {"type": "object"},
        "server_build_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "capability_epoch": "aaaaaaaaaaaa-bbbbbbbbbbbb",
        "error": "",
    },
    "inspect_repo_status": {
        "ok": True,
        "repo_name": "repo",
        "branch": "main",
        "git_status": "## main\n M codexbridge/server.py\n",
        "recent_commits": ["abc123 hotfix", "def456 previous change"],
        "diff_stat": " codexbridge/server.py | 10 +++++-----\n 1 file changed, 5 insertions(+), 5 deletions(-)\n",
        "changed_files": ["codexbridge/server.py"],
    },
    "inspect_repo_status_compact": {
        "ok": True,
        "repo_name": "repo",
        "branch": "main",
        "recent_commits": ["abc123 hotfix", "def456 previous change"],
        "diff_stat": " codexbridge/server.py | 10 +++++-----\n 1 file changed, 5 insertions(+), 5 deletions(-)\n",
        "complete_status_scan": True,
        "total_status_entry_count": 2,
        "returned_entry_count": 1,
        "collapsed_tool_owned_count": 1,
        "sampled_tool_owned_count": 1,
        "unsampled_tool_owned_count": 0,
        "files": [
            {
                "path": "codexbridge/server.py",
                "size_bytes": 10,
                "line_count": 1,
                "tool_owned": False,
                "index_status": "M",
                "worktree_status": " ",
            }
        ],
        "tool_owned_summary": {
            "total_bytes": 4,
            "root_group_counts": {".codex-tmp": 1},
            "sample": [
                {
                    "path": ".codex-tmp/run.txt",
                    "size_bytes": 4,
                    "line_count": 1,
                    "tool_owned": True,
                    "index_status": "?",
                    "worktree_status": "?",
                }
            ],
            "truncated": False,
        },
        "fallback_tool": "inspect_repo_status",
        "error": "",
    },
    "codex_plan_task": {
        "ok": True,
        "run_id": "run_plan_alias",
        "status": "queued",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "codex_implement_task": {
        "ok": True,
        "run_id": "run_implement_alias",
        "status": "queued",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "get_latest_run_result": {
        "ok": True,
        "run_id": "run_1",
        "status": "completed",
        "repo_name": "repo",
        "result": {"summary": "done"},
        "error": "",
    },
    "git_diff_summary": {
        "git_status": "## main\n M codexbridge/server.py\n",
        "diff_stat": " 1 file changed\n",
    },
    "commit_selected_files": {
        "ok": True,
        "repo_name": "repo",
        "commit_sha": "abc123",
        "files": ["codexbridge/server.py"],
        "message": "hotfix",
        "error": "",
    },
    "dry_run_stage_manifest": {
        "ok": True,
        "repo_name": "repo",
        "status": "preview",
        "error": "",
        "staged_files": ["codexbridge/server.py"],
        "unstaged_files": ["tests/test_server.py"],
    },
    "stage_all": {
        "ok": True,
        "repo_name": "repo",
        "status": "staged",
        "error": "",
        "before": {"staged_files": []},
        "after": {"staged_files": ["codexbridge/server.py"]},
    },
    "unstage_all": {
        "ok": True,
        "repo_name": "repo",
        "status": "unstaged",
        "error": "",
        "before": {"staged_files": ["codexbridge/server.py"]},
        "after": {"staged_files": []},
    },
    "commit_all_changes": {
        "ok": True,
        "repo_name": "repo",
        "files_validated": True,
        "commit_hash": "a" * 40,
        "remaining_dirty_files": [],
        "git_status": "",
        "blocked_field": "",
        "reason_code": "",
        "reason": "",
        "error": "",
    },
    "run_local_self_check": {
        "ok": True,
        "checks": {"pytest": {"ok": True}, "pip_check": {"ok": True}},
        "error": "",
    },
    "local_model_health": {
        "ok": True,
        "status": "ok",
        "enabled": True,
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2",
        "models_endpoint_reachable": True,
        "configured_model_available": True,
        "completion_succeeded": True,
        "duration_seconds": 0.1,
        "timeout_seconds": 30,
        "error": "",
        "audit_event_id": "audit_1",
    },
    "list_docker_capabilities": {
        "ok": True,
        "enabled": True,
        "executable": "docker",
        "read_only_operations": ["compose_ps"],
        "actions": ["compose_up"],
        "high_risk_actions": {"image_prune": "allow_prune"},
        "high_risk_gates": {"allow_prune": True},
        "confirmation_token": "CONFIRM_DOCKER_HIGH_RISK",
        "compose_files": ["docker-compose.yml"],
        "project_name": "sample",
        "exec_profiles": [],
        "arbitrary_shell_supported": False,
        "arbitrary_argv_supported": False,
        "error": "",
    },
    "docker_health": {
        "ok": True,
        "enabled": True,
        "engine": {"ok": True},
        "compose": {"ok": True},
        "error": "",
    },
    "docker_inspect": {
        "ok": True,
        "repo_name": "repo",
        "action": "compose_ps",
        "argv": ["docker", "compose", "ps"],
        "exit_code": 0,
        "timed_out": False,
        "duration_seconds": 0.1,
        "stdout": "api running",
        "stderr": "",
        "output_truncated": False,
        "error": "",
    },
    "start_docker_action_async": {
        "ok": True,
        "run_id": "run_docker",
        "status": "queued",
        "repo_name": "repo",
        "action": "compose_up",
        "result": {},
        "error": "",
    },
    "list_cloudflare_capabilities": {
        "ok": True,
        "enabled": False,
        "api_base_url": "https://api.cloudflare.com/client/v4",
        "token_env": "CLOUDFLARE_API_TOKEN",
        "read_only_operations": ["dns_records"],
        "actions": ["dns_create"],
        "gates": {"allow_dns_write": False},
        "profiles": [],
        "arbitrary_http_supported": False,
        "raw_graphql_supported": False,
        "error": "",
    },
    "cloudflare_health": {
        "ok": True,
        "profile_id": "production",
        "token_status": {"status": "active"},
        "zone_id_configured": True,
        "account_id_configured": True,
        "zone_name": "example.com",
        "error": "",
    },
    "cloudflare_inspect": {
        "ok": True,
        "profile_id": "production",
        "operation": "dns_records",
        "method": "GET",
        "path": "/zones/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/dns_records",
        "status_code": 200,
        "duration_seconds": 0.1,
        "result": [],
        "result_info": {},
        "messages": [],
        "exit_code": 0,
        "timed_out": False,
        "stdout": "{}",
        "stderr": "",
        "output_truncated": False,
        "writes_remote": False,
        "high_risk": False,
        "error": "",
    },
    "start_cloudflare_action_async": {
        "ok": True,
        "run_id": "run_cloudflare",
        "status": "queued",
        "profile_id": "production",
        "action": "dns_create",
        "high_risk": False,
        "result": {},
        "error": "",
    },
    "list_ssh_capabilities": {
        "ok": True,
        "enabled": True,
        "hosts": [
            {
                "host_id": "my_vps",
                "ssh_alias": "my-vps",
                "commands": [
                    {
                        "command_id": "uptime",
                        "description": "Show server uptime",
                        "timeout_seconds": 30,
                        "writes_remote": False,
                    }
                ],
            }
        ],
        "error": "",
    },
    "preview_ssh_profile_change": {
        "ok": True,
        "change_id": "20260711T120000Z_sshcfg_1234abcd",
        "status": "previewed",
        "action": "add_host",
        "host_id": "my_vps",
        "command_id": "",
        "created_at": "2026-07-11T12:00:00+00:00",
        "applied_at": "",
        "failed_at": "",
        "base_config_sha256": "a" * 64,
        "candidate_config_sha256": "b" * 64,
        "capability_diff": {
            "hosts_added": ["my_vps"],
            "hosts_removed": [],
            "hosts_changed": [],
        },
        "error": "",
    },
    "get_ssh_profile_change_status": {
        "ok": True,
        "change_id": "20260711T120000Z_sshcfg_1234abcd",
        "status": "previewed",
        "action": "add_host",
        "host_id": "my_vps",
        "command_id": "",
        "created_at": "2026-07-11T12:00:00+00:00",
        "applied_at": "",
        "failed_at": "",
        "base_config_sha256": "a" * 64,
        "candidate_config_sha256": "b" * 64,
        "capability_diff": {
            "hosts_added": ["my_vps"],
            "hosts_removed": [],
            "hosts_changed": [],
        },
        "error": "",
    },
    "apply_ssh_profile_change": {
        "ok": True,
        "change_id": "20260711T120000Z_sshcfg_1234abcd",
        "status": "applied",
        "action": "add_host",
        "host_id": "my_vps",
        "command_id": "",
        "config_sha256": "b" * 64,
        "capability_diff": {
            "hosts_added": ["my_vps"],
            "hosts_removed": [],
            "hosts_changed": [],
        },
        "activation": {"ok": True, "status": "active"},
        "idempotent_replay": False,
        "error": "",
    },
    "ssh_host_health": {
        "ok": True,
        "status": "ok",
        "host_id": "my_vps",
        "ssh_alias": "my-vps",
        "exit_code": 0,
        "error": "",
    },
    "ssh_environment_probe": {
        "ok": True,
        "host_id": "my_vps",
        "status": "ok",
        "environment": {
            "os": "Linux 6.8.0 x86_64",
            "working_directory": "/workspace",
            "python": {"version": "3.12.3", "virtual_env": "/opt/venv"},
            "torch": {"version": "2.7.0", "cuda_available": True},
            "cuda_compiler": "Cuda compilation tools, release 12.8",
            "system_memory": {"used_percent": 40.0},
            "root_disk": {"free_percent": 60.0},
        },
        "gpu": {"ok": True, "device_count": 1, "devices": []},
        "checks": {},
        "watchdog": {
            "enabled": False,
            "enforcement_mode": "observe_only",
            "status": "disabled",
            "can_terminate_remote_processes": False,
            "checks": [],
            "breaches": [],
        },
        "writes_remote": False,
        "high_risk": False,
        "error": "",
    },
    "ssh_gpu_telemetry": {
        "ok": True,
        "host_id": "my_vps",
        "status": "ok",
        "available": True,
        "device_count": 1,
        "process_count": 1,
        "devices": [
            {
                "index": 0,
                "name": "NVIDIA A40",
                "memory_used_percent": 50.0,
                "gpu_utilization_percent": 80.0,
                "temperature_c": 70.0,
            }
        ],
        "processes": [{"pid": 1234, "process_name": "python3"}],
        "checks": {},
        "watchdog": {
            "enabled": False,
            "enforcement_mode": "observe_only",
            "status": "disabled",
            "can_terminate_remote_processes": False,
            "checks": [],
            "breaches": [],
        },
        "writes_remote": False,
        "high_risk": False,
        "error": "",
    },
    "ssh_inspect": {
        "ok": True,
        "host_id": "my_vps",
        "operation": "git_status",
        "argv": ["ssh", "<bounded remote argv>"],
        "exit_code": 0,
        "timed_out": False,
        "duration_seconds": 0.1,
        "stdout": "## main",
        "stderr": "",
        "output_truncated": False,
        "writes_remote": False,
        "high_risk": False,
        "error": "",
    },
    "start_external_fixture_validation_async": {
        "ok": True,
        "run_id": "run_fixture",
        "status": "queued",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "start_ssh_command_async": {
        "ok": True,
        "run_id": "run_remote",
        "status": "queued",
        "host_id": "my_vps",
        "command_id": "uptime",
        "writes_remote": False,
        "result": {},
        "error": "",
    },
    "start_ssh_monitored_command_async": {
        "ok": True,
        "run_id": "run_monitored",
        "status": "queued",
        "host_id": "my_vps",
        "command_id": "uptime",
        "writes_remote": False,
        "watchdog_mode": "observe_only",
        "automatic_termination_active": False,
        "result": {},
        "error": "",
    },
    "start_ssh_action_async": {
        "ok": True,
        "run_id": "run_ssh_action",
        "status": "queued",
        "host_id": "my_vps",
        "action": "service_restart",
        "high_risk": False,
        "result": {},
        "error": "",
    },
    "start_ssh_transfer_async": {
        "ok": True,
        "run_id": "run_ssh_transfer",
        "status": "queued",
        "host_id": "my_vps",
        "direction": "upload",
        "result": {},
        "error": "",
    },
    "start_ssh_deployment_async": {
        "ok": True,
        "run_id": "run_ssh_deploy",
        "status": "queued",
        "host_id": "my_vps",
        "deployment_id": "app",
        "result": {},
        "error": "",
    },
    "start_codex_plan_task_async": {
        "ok": True,
        "run_id": "run_2",
        "status": "queued",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "start_codex_implement_task_async": {
        "ok": True,
        "run_id": "run_3",
        "status": "queued",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "start_project_command_async": {
        "ok": True,
        "run_id": "run_4",
        "status": "queued",
        "repo_name": "repo",
        "command_id": "pytest",
        "result": {},
        "error": "",
    },
    "start_pytest_path_async": {
        "ok": True,
        "run_id": "run_5",
        "status": "queued",
        "repo_name": "repo",
        "command_id": "pytest_path",
        "path": "tests/test_api.py::test_ok",
        "result": {},
        "error": "",
    },
    "start_py_compile_path_async": {
        "ok": True,
        "run_id": "run_6",
        "status": "queued",
        "repo_name": "repo",
        "command_id": "py_compile_path",
        "path": "codexbridge/server.py",
        "result": {},
        "error": "",
    },
    "start_bash_n_path_async": {
        "ok": True,
        "run_id": "run_7",
        "status": "queued",
        "repo_name": "repo",
        "command_id": "bash_n_path",
        "path": "scripts/check.sh",
        "result": {},
        "error": "",
    },
    "start_json_validation_path_async": {
        "ok": True,
        "run_id": "run_8",
        "status": "queued",
        "repo_name": "repo",
        "command_id": "json_validation_path",
        "path": "config/settings.json",
        "result": {},
        "error": "",
    },
    "start_git_readonly_async": {
        "ok": True,
        "run_id": "run_9",
        "status": "queued",
        "repo_name": "repo",
        "command_id": "git_readonly",
        "result": {},
        "error": "",
    },
    "get_run_status": {
        "ok": True,
        "run_id": "run_2",
        "status": "running",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "get_run_control_status": {
        "ok": True,
        "run_id": "run_2",
        "repo_name": "repo",
        "tool": "project_command",
        "status": "running",
        "current_phase": "command",
        "heartbeat_age_seconds": 1.5,
        "worker_stale": False,
        "worker_pid": 123,
        "worker_running": True,
        "child_pid": 456,
        "child_running": True,
        "lock": {"repo_name": "repo", "run_id": "run_2"},
        "error": "",
    },
    "get_run_output": {
        "ok": True,
        "run_id": "run_2",
        "status": "running",
        "stream": "combined",
        "tail_bytes": 20000,
        "streams": {
            "stdout": {
                "text": "running\n",
                "size_bytes": 8,
                "truncated": False,
                "available": True,
            },
            "stderr": {
                "text": "",
                "size_bytes": 0,
                "truncated": False,
                "available": False,
            },
        },
        "error": "",
    },
    "list_operation_locks": {
        "ok": True,
        "locks": [
            {
                "repo_name": "repo",
                "tool": "project_command",
                "run_id": "run_2",
                "heartbeat_age_seconds": 1.0,
                "stale": False,
            }
        ],
        "count": 1,
        "error": "",
    },
    "get_run_events": {
        "ok": True,
        "run_id": "run_2",
        "events": [{"stage": "queued", "message": "Run queued"}],
        "error": "",
    },
    "get_run_result": {
        "ok": True,
        "run_id": "run_2",
        "status": "completed",
        "repo_name": "repo",
        "result": {"summary": "done"},
        "error": "",
    },
    "list_runs": {
        "ok": True,
        "runs": [{"run_id": "run_1", "status": "completed", "repo_name": "repo"}],
        "error": "",
    },
    "cancel_run": {
        "run_id": "run_2",
        "status": "cancelled",
        "cancelled": True,
        "terminated": True,
    },
    "reload_service": {
        "ok": True,
        "status": "reloaded",
        "message": "",
        "error": "",
        "config_lifecycle": {
            "active_config_path": "D:\\Github\\CodexBridge\\config.yaml",
            "active_loaded_at": "2026-07-11T02:57:19Z",
            "last_known_good_loaded_at": "2026-07-11T02:57:19Z",
            "previous_loaded_at": "2026-07-11T02:55:00Z",
            "last_validated_at": "2026-07-11T02:57:10Z",
            "last_candidate_path": "D:\\Github\\CodexBridge\\config.yaml",
            "last_operation": "reload",
            "last_status": "reloaded",
            "last_error": "",
            "has_active_config": True,
            "has_last_known_good_config": True,
            "has_previous_config": True,
        },
        "patch_operation_schema": {"type": "object"},
        "server_build_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "capability_epoch": "aaaaaaaaaaaa-bbbbbbbbbbbb",
    },
    "validate_service_config": {
        "ok": True,
        "validated": True,
        "candidate_config_path": "D:\\Github\\CodexBridge\\config.yaml",
        "validated_at": "2026-07-11T02:57:10Z",
        "message": "Configuration candidate validated successfully.",
        "error": "",
        "config_lifecycle": {
            "active_config_path": "D:\\Github\\CodexBridge\\config.yaml",
            "active_loaded_at": "2026-07-11T02:57:19Z",
            "last_known_good_loaded_at": "2026-07-11T02:57:19Z",
            "previous_loaded_at": "2026-07-11T02:55:00Z",
            "last_validated_at": "2026-07-11T02:57:10Z",
            "last_candidate_path": "D:\\Github\\CodexBridge\\config.yaml",
            "last_operation": "validate",
            "last_status": "validated",
            "last_error": "",
            "has_active_config": True,
            "has_last_known_good_config": True,
            "has_previous_config": True,
        },
        "patch_operation_schema": {"type": "object"},
        "server_build_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "capability_epoch": "aaaaaaaaaaaa-bbbbbbbbbbbb",
    },
    "get_service_reload_status": {
        "ok": True,
        "status": "validated",
        "message": "",
        "error": "",
        "config_lifecycle": {
            "active_config_path": "D:\\Github\\CodexBridge\\config.yaml",
            "active_loaded_at": "2026-07-11T02:57:19Z",
            "last_known_good_loaded_at": "2026-07-11T02:57:19Z",
            "previous_loaded_at": "2026-07-11T02:55:00Z",
            "last_validated_at": "2026-07-11T02:57:10Z",
            "last_candidate_path": "D:\\Github\\CodexBridge\\config.yaml",
            "last_operation": "validate",
            "last_status": "validated",
            "last_error": "",
            "has_active_config": True,
            "has_last_known_good_config": True,
            "has_previous_config": True,
        },
        "patch_operation_schema": {"type": "object"},
        "server_build_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "capability_epoch": "aaaaaaaaaaaa-bbbbbbbbbbbb",
    },
    "rollback_service": {
        "ok": True,
        "rolled_back": True,
        "message": "Rolled back to the previous last-known-good configuration.",
        "error": "",
        "config_lifecycle": {
            "active_config_path": "D:\\Github\\CodexBridge\\config.yaml",
            "active_loaded_at": "2026-07-11T02:58:00Z",
            "last_known_good_loaded_at": "2026-07-11T02:55:00Z",
            "previous_loaded_at": "2026-07-11T02:55:00Z",
            "last_validated_at": "2026-07-11T02:57:10Z",
            "last_candidate_path": "D:\\Github\\CodexBridge\\config.yaml",
            "last_operation": "rollback",
            "last_status": "rolled_back",
            "last_error": "",
            "has_active_config": True,
            "has_last_known_good_config": True,
            "has_previous_config": True,
        },
        "patch_operation_schema": {"type": "object"},
        "server_build_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "capability_epoch": "aaaaaaaaaaaa-bbbbbbbbbbbb",
    },
    "start_supervised_recovery_task": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "queued",
        "result": {"summary": "queued"},
        "error": "",
    },
    "get_supervisor_status": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "needs_input",
        "result": {"summary": "waiting"},
        "error": "",
    },
    "get_supervisor_events": {
        "ok": True,
        "supervisor_id": "sup_1",
        "events": [{"stage": "planning", "message": "tick"}],
        "error": "",
    },
    "get_supervisor_result": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "completed",
        "result": {"summary": "done"},
        "error": "",
    },
    "resume_supervisor": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "queued",
        "result": {"summary": "resumed"},
        "error": "",
    },
    "pause_supervisor": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "paused",
        "result": {"summary": "paused"},
        "error": "",
    },
    "cancel_supervisor": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "cancelled",
        "result": {"summary": "cancelled"},
        "error": "",
    },
    "get_supervisor_notifications": {
        "ok": True,
        "supervisor_id": "sup_1",
        "notifications": [{"id": 1, "delivery_status": "pending", "channel": "file"}],
        "error": "",
    },
    "get_supervisor_resume_prompt": {
        "supervisor_id": "sup_1",
        "exists": True,
        "path": "D:\\Github\\CodexBridge\\runs\\supervisors\\sup_1\\resume_prompt.txt",
        "content": "resume prompt",
    },
    # repo reader tools (batch)
    "list_repo_files": {
        "ok": True,
        "repo_name": "repo",
        "directory": "",
        "files": ["codexbridge/__init__.py", "codexbridge/server.py"],
        "count": 2,
        "truncated": False,
        "max_results": 500,
        "error": "",
    },
    "read_repo_file": {
        "ok": True,
        "repo_name": "repo",
        "path": "README.md",
        "content": "# CodexBridge\n",
        "start_line": 1,
        "end_line": 1,
        "total_lines": 1,
        "size_bytes": 16,
        "sha256": "a" * 64,
        "git_head": "b" * 40,
        "truncated": False,
        "error": "",
    },
    "search_repo_text": {
        "ok": True,
        "repo_name": "repo",
        "query": "def main",
        "directory": "",
        "case_sensitive": False,
        "hits": [
            {
                "path": "codexbridge/server.py",
                "line": 10,
                "snippet": "def main() -> None:",
            }
        ],
        "count": 1,
        "truncated": False,
        "max_results": 50,
        "error": "",
    },
    "get_recently_modified_files": {
        "ok": True,
        "repo_name": "repo",
        "files": [{"path": "codexbridge/server.py", "mtime": 1720000000.0}],
        "count": 1,
        "limit": 50,
        "error": "",
    },
    "repo_git_status": {
        "ok": True,
        "repo_name": "repo",
        "status": "## main\n M codexbridge/server.py\n",
        "error": "",
    },
    "repo_git_diff": {
        "ok": True,
        "repo_name": "repo",
        "path": "",
        "staged": False,
        "diff": "diff --git a/codexbridge/server.py b/codexbridge/server.py\n",
        "truncated": False,
        "error": "",
    },
    "inspect_commit_range": {
        "ok": True,
        "repo_name": "repo",
        "base_commit": "a" * 40,
        "head_commit": "b" * 40,
        "name_status": "M\tREADME.md\n",
        "diff_stat": " README.md | 1 +\n",
        "diff": "diff --git a/README.md b/README.md\n",
        "truncated": False,
        "error": "",
    },
    # controlled local coding tools
    "preview_repo_patch": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "diff": "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-old\n+new\n",
        "changed_files": ["README.md"],
        "changed_lines": 2,
        "changed_bytes": 3,
        "git_head": "b" * 40,
        "validation_errors": [],
        "error": "",
    },
    "preview_repo_file_creation": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "diff": "--- a/docs/new.py\n+++ b/docs/new.py\n@@ -0,0 +1 @@\n+print('hi')\n",
        "changed_files": ["docs/new.py"],
        "changed_lines": 1,
        "changed_bytes": 12,
        "git_head": "b" * 40,
        "validation_errors": [],
        "error": "",
    },
    "preview_repo_file_removal": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "diff": "--- a/docs/old.py\n+++ b/docs/old.py\n@@ -1 +0,0 @@\n-print('bye')\n",
        "changed_files": ["docs/old.py"],
        "changed_lines": 1,
        "changed_bytes": 13,
        "git_head": "b" * 40,
        "validation_errors": [],
        "error": "",
    },
    "get_patch_status": {
        "ok": True,
        "repo_name": "repo",
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "status": "applied",
        "changed_files": ["README.md"],
        "apply_result": {"ok": True},
        "error": "",
    },
    "preview_managed_artifact_cleanup": {
        "ok": True,
        "repo_name": "repo",
        "cleanup_id": "20260624T120000Z_cleanup_abcd1234",
        "status": "previewed",
        "artifacts": [{"path": ".codex-tmp/a", "sha256": "a" * 64}],
        "file_count": 1,
        "total_bytes": 1,
        "error": "",
    },
    "apply_managed_artifact_cleanup": {
        "ok": True,
        "repo_name": "repo",
        "cleanup_id": "20260624T120000Z_cleanup_abcd1234",
        "status": "applied",
        "removed_files": [".codex-tmp/a"],
        "missing_files": [],
        "idempotent_replay": False,
        "error": "",
    },
    "apply_repo_patch": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "changed_files": ["README.md"],
        "results": [{"path": "README.md", "sha256": "a" * 64}],
        "git_head": "b" * 40,
        "error": "",
    },
    "apply_previewed_repo_change": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "changed_files": ["docs/new.py"],
        "results": [{"path": "docs/new.py", "sha256": "a" * 64}],
        "git_head": "b" * 40,
        "error": "",
    },
    "create_repo_file": {
        "ok": True,
        "repo_name": "repo",
        "path": "docs/new.md",
        "sha256": "a" * 64,
        "size_bytes": 10,
        "error": "",
    },
    "delete_repo_file": {
        "ok": True,
        "repo_name": "repo",
        "path": "docs/old.md",
        "rollback_id": "20260624T120000Z_delete_abcd1234",
        "error": "",
    },
    "move_repo_file": {
        "ok": True,
        "repo_name": "repo",
        "source_path": "docs/old.md",
        "destination_path": "docs/new.md",
        "sha256": "a" * 64,
        "rollback_id": "20260624T120000Z_move_abcd1234",
        "error": "",
    },
    "revert_managed_patch": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "reverted_files": ["README.md"],
        "error": "",
    },
    "run_project_command": {
        "ok": False,
        "repo_name": "repo",
        "command_id": "pytest",
        "argv": ["python", "-m", "pytest", "-q"],
        "exit_code": 2,
        "timed_out": False,
        "duration_seconds": 0.0,
        "stdout": "",
        "stderr": "",
        "output_truncated": False,
        "status": "async_required",
        "async_required": True,
        "error": "Use start_project_command_async.",
    },
    "git_log": {
        "ok": True,
        "repo_name": "repo",
        "commits": [
            {
                "sha": "a" * 40,
                "author_name": "Dev",
                "author_email": "d@example.com",
                "date": "2026-06-24",
                "subject": "fix: patch",
            }
        ],
        "count": 1,
        "path": "",
        "error": "",
    },
    "read_repo_files": {
        "ok": True,
        "repo_name": "repo",
        "results": [
            {"ok": True, "path": "README.md", "content": "# hi\n", "error": ""}
        ],
        "count": 1,
        "truncated_batch": False,
        "error": "",
    },
    "create_git_branch": {
        "ok": True,
        "repo_name": "repo",
        "branch_name": "feature/my-branch",
        "error": "",
    },
}


REALISTIC_ACTION_OUTPUTS.update(
    {
        "start_workflow": {
            "ok": True,
            "workflow_id": "workflow_1",
            "repo_name": "repo",
            "status": "queued",
            "terminal_status": "",
            "steps": [],
            "error": "",
        },
        "get_workflow_status": {
            "ok": True,
            "workflow_id": "workflow_1",
            "repo_name": "repo",
            "status": "reported",
            "terminal_status": "completed",
            "steps": [],
            "error": "",
        },
        "get_workflow_events": {
            "ok": True,
            "workflow_id": "workflow_1",
            "events": [],
            "notifications": [],
            "error": "",
        },
        "get_workflow_result": {
            "ok": True,
            "workflow_id": "workflow_1",
            "repo_name": "repo",
            "status": "reported",
            "terminal_status": "completed",
            "steps": [],
            "error": "",
        },
        "cancel_workflow": {
            "ok": True,
            "workflow_id": "workflow_1",
            "repo_name": "repo",
            "status": "reported",
            "terminal_status": "cancelled",
            "steps": [],
            "error": "",
        },
        "refresh_repo_wiki": {
            "ok": True,
            "repo_name": "repo",
            "status": "unchanged",
            "wiki_root": ".codexbridge/wiki",
            "pages": ["overview.md"],
            "source_file_count": 1,
            "changed_source_files": [],
            "scan_truncated": False,
            "error": "",
        },
        "read_repo_wiki": {
            "ok": True,
            "repo_name": "repo",
            "page": "overview.md",
            "content": "# Overview\n",
            "size_bytes": 11,
            "truncated": False,
            "error": "",
        },
        "search_repo_knowledge": {
            "ok": True,
            "repo_name": "repo",
            "query": "workflow",
            "wiki_hits": [],
            "memory_hits": [],
            "error": "",
        },
        "remember_repo_decision": {
            "ok": True,
            "repo_name": "repo",
            "memory_id": "memory_1",
            "memory_type": "decision_memory",
            "title": "Decision",
            "summary": "Repository-scoped decision.",
            "error": "",
        },
    }
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any] | str, status: int = 200):
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        if isinstance(self.payload, str):
            return self.payload.encode("utf-8")
        return json.dumps(self.payload).encode("utf-8")


def discovered_actions() -> list[dict]:
    async def _list() -> list[dict]:
        register_knowledge_tools(server.mcp)
        tools = await server.mcp.list_tools()
        return [tool.to_mcp_tool().model_dump(mode="json") for tool in tools]

    return asyncio.run(_list())


def test_mcp_action_discovery_is_json_serializable() -> None:
    actions = discovered_actions()

    encoded = json.dumps(actions, sort_keys=True)

    assert "cancel_run" in encoded
    assert len(actions) == len(EXPECTED_EXPOSED_ACTIONS)


def test_mcp_action_names_are_unique_stable_and_valid() -> None:
    actions = discovered_actions()
    names = [action["name"] for action in actions]

    assert set(names) == EXPECTED_EXPOSED_ACTIONS
    assert len(names) == len(set(names))
    assert all(ACTION_NAME_RE.match(name) for name in names)


def test_mcp_actions_have_descriptions_annotations_and_valid_input_schemas() -> None:
    for action in discovered_actions():
        assert action["description"]
        assert len(action["description"]) <= 300
        schema = action["inputSchema"]
        Draft202012Validator.check_schema(schema)
        assert schema["type"] == "object"
        assert "anyOf" not in json.dumps(schema)
        assert "oneOf" not in json.dumps(schema)
        annotations = action["annotations"]
        assert isinstance(annotations, dict)
        assert isinstance(annotations["readOnlyHint"], bool)
        assert isinstance(annotations["destructiveHint"], bool)
        assert isinstance(annotations["idempotentHint"], bool)
        assert isinstance(annotations["openWorldHint"], bool)
        assert action["outputSchema"] is not None
        Draft202012Validator.check_schema(action["outputSchema"])


def test_mcp_risky_actions_are_not_marked_read_only_or_destructive() -> None:
    actions = {action["name"]: action for action in discovered_actions()}
    write_actions = {
        "codex_implement_task",
        "commit_selected_files",
        "start_codex_implement_task_async",
        "start_docker_action_async",
        "start_cloudflare_action_async",
        "start_project_command_async",
        "start_pytest_path_async",
        "start_py_compile_path_async",
        "start_bash_n_path_async",
        "start_json_validation_path_async",
        "start_git_readonly_async",
        "start_ssh_command_async",
        "start_ssh_monitored_command_async",
        "start_ssh_action_async",
        "start_ssh_transfer_async",
        "start_ssh_deployment_async",
        "apply_ssh_profile_change",
        "start_external_fixture_validation_async",
        "cancel_run",
        "start_workflow",
        "cancel_workflow",
        "refresh_repo_wiki",
        "remember_repo_decision",
        "reload_service",
        "rollback_service",
        "start_supervised_recovery_task",
        "resume_supervisor",
        "pause_supervisor",
        "cancel_supervisor",
        # controlled local coding tools
        "apply_managed_artifact_cleanup",
        "apply_repo_patch",
        "apply_previewed_repo_change",
        "create_repo_file",
        "delete_repo_file",
        "move_repo_file",
        "revert_managed_patch",
        "run_project_command",
        "create_git_branch",
        "stage_all",
        "unstage_all",
        "commit_all_changes",
    }
    for name, action in actions.items():
        annotations = action["annotations"]
        if name in write_actions:
            assert annotations["readOnlyHint"] is False
            assert annotations["destructiveHint"] is False
        else:
            assert annotations["readOnlyHint"] is True


def test_apply_previewed_repo_change_schema_is_opaque() -> None:
    actions = {action["name"]: action for action in discovered_actions()}
    schema = actions["apply_previewed_repo_change"]["inputSchema"]
    properties = schema["properties"]

    assert set(properties) == {"repo_name", "patch_id"}
    assert set(schema.get("required", [])) == {"repo_name", "patch_id"}


def test_currently_exposed_batch_actions_are_discoverable() -> None:
    actions = {action["name"]: action for action in discovered_actions()}

    assert len(actions) == 80
    assert RETIRED_DIRECT_ACTIONS.isdisjoint(actions)
    for name in WORKFLOW_AND_KNOWLEDGE_ACTIONS:
        assert name in actions
    for name in {
        "get_run_control_status",
        "get_run_output",
        "list_operation_locks",
        "ssh_environment_probe",
        "ssh_gpu_telemetry",
    }:
        assert name in actions

def test_all_mcp_action_output_schemas_are_json_serializable_and_valid() -> None:
    for action in discovered_actions():
        encoded = json.dumps(action["outputSchema"], sort_keys=True)
        assert encoded
        Draft202012Validator.check_schema(action["outputSchema"])


def test_realistic_outputs_validate_against_public_action_output_schemas() -> None:
    actions = {action["name"]: action for action in discovered_actions()}

    assert set(REALISTIC_ACTION_OUTPUTS) == set(actions) | RETIRED_DIRECT_ACTIONS

    for name, action in actions.items():
        sample = REALISTIC_ACTION_OUTPUTS[name]
        json.dumps(sample, sort_keys=True)
        validate(instance=sample, schema=action["outputSchema"])

def test_run_local_self_check_output_matches_schema(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "run_self_check",
        lambda **kwargs: {"ok": True, "checks": {}, "error": ""},
    )
    action = {item["name"]: item for item in discovered_actions()}[
        "run_local_self_check"
    ]

    result = server.run_local_self_check()

    validate(instance=result, schema=action["outputSchema"])


def test_local_model_health_disabled_does_not_call_http(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("no HTTP call expected")
        ),
    )
    action = {item["name"]: item for item in discovered_actions()}["local_model_health"]

    result = server.local_model_health()

    assert result["status"] == "disabled"
    assert result["ok"] is False
    assert result["models_endpoint_reachable"] is False
    validate(instance=result, schema=action["outputSchema"])


def test_local_model_health_success_uses_models_and_tiny_completion(
    monkeypatch, tmp_path
) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True, model="llama3.2", timeout_seconds=5),
    )
    server.set_config(config, tmp_path / "config.yaml")
    captured: dict[str, Any] = {}

    def fake_models(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["models_url"] = request.full_url
        captured["models_timeout"] = timeout
        return FakeResponse({"data": [{"id": "llama3.2"}]})

    def fake_completion(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["completion_url"] = request.full_url
        captured["completion_timeout"] = timeout
        captured["completion_body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(server, "_local_model_urlopen", fake_models)
    monkeypatch.setattr(server, "_local_model_transport", fake_completion)
    action = {item["name"]: item for item in discovered_actions()}["local_model_health"]

    result = server.local_model_health()

    assert captured["models_url"] == "http://localhost:11434/v1/models"
    assert captured["models_timeout"] == 5
    assert captured["completion_url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["completion_timeout"] == 5
    assert captured["completion_body"]["model"] == "llama3.2"
    assert captured["completion_body"]["max_tokens"] == 16
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["configured_model_available"] is True
    assert result["completion_succeeded"] is True
    validate(instance=result, schema=action["outputSchema"])


def test_local_model_health_connection_failure_returns_unavailable(
    monkeypatch, tmp_path
) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda request, timeout: (_ for _ in ()).throw(
            urllib.error.URLError("refused")
        ),
    )

    result = server.local_model_health()

    assert result["status"] == "unavailable"
    assert result["ok"] is False
    assert result["completion_succeeded"] is False


def test_local_model_health_timeout_returns_timeout(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda request, timeout: (_ for _ in ()).throw(
            urllib.error.URLError(socket.timeout("timed out"))
        ),
    )

    result = server.local_model_health()

    assert result["status"] == "timeout"
    assert result["ok"] is False


def test_local_model_health_model_missing_does_not_run_completion(
    monkeypatch, tmp_path
) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True, model="missing-model"),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda request, timeout: FakeResponse({"data": [{"id": "llama3.2"}]}),
    )
    monkeypatch.setattr(
        server,
        "_local_model_transport",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("completion should not run")
        ),
    )

    result = server.local_model_health()

    assert result["status"] == "model_missing"
    assert result["configured_model_available"] is False
    assert result["completion_succeeded"] is False


def test_local_model_health_malformed_models_response_returns_failed(
    monkeypatch, tmp_path
) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda request, timeout: FakeResponse({"models": ["llama3.2"]}),
    )

    result = server.local_model_health()

    assert result["status"] == "failed"
    assert result["ok"] is False
    assert result["completion_succeeded"] is False


def test_sync_pytest_requires_durable_async_execution(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "run_command_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("sync pytest must not launch")
        ),
    )

    result = server.run_project_command("repo", "pytest")

    assert result["ok"] is False
    assert result["status"] == "async_required"
    assert result["async_required"] is True
    assert "start_project_command_async" in result["error"]


def test_start_project_command_async_delegates_to_job_manager(monkeypatch) -> None:
    class FakeJobManager:
        def start_project_command(self, repo_name, command_id):
            return {
                "run_id": "run_4",
                "accepted": True,
                "status": "queued",
                "repo_name": repo_name,
                "command_id": command_id,
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobManager())

    result = server.start_project_command_async("repo", "pytest")

    assert result["accepted"] is True
    assert result["run_id"] == "run_4"
    assert result["command_id"] == "pytest"


def test_start_pytest_path_async_delegates_to_job_manager(monkeypatch) -> None:
    class FakeJobManager:
        def start_pytest_path(self, repo_name, path):
            return {
                "run_id": "run_5",
                "accepted": True,
                "status": "queued",
                "repo_name": repo_name,
                "command_id": "pytest_path",
                "path": path,
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobManager())

    result = server.start_pytest_path_async("repo", "tests/test_api.py::test_ok")

    assert result["accepted"] is True
    assert result["run_id"] == "run_5"
    assert result["command_id"] == "pytest_path"
    assert result["path"] == "tests/test_api.py::test_ok"


def test_start_pytest_path_async_schema_is_exact() -> None:
    actions = {action["name"]: action for action in discovered_actions()}
    schema = actions["start_pytest_path_async"]["inputSchema"]
    properties = schema["properties"]

    assert set(properties) == {"repo_name", "path"}
    assert set(schema.get("required", [])) == {"repo_name", "path"}
    assert actions["start_pytest_path_async"]["annotations"]["readOnlyHint"] is False


def test_new_async_path_and_git_tool_schemas_are_exact() -> None:
    actions = {action["name"]: action for action in discovered_actions()}

    for name in {
        "start_py_compile_path_async",
        "start_bash_n_path_async",
        "start_json_validation_path_async",
    }:
        schema = actions[name]["inputSchema"]
        assert set(schema["properties"]) == {"repo_name", "path"}
        assert set(schema.get("required", [])) == {"repo_name", "path"}
        assert actions[name]["annotations"]["readOnlyHint"] is False

    git_schema = actions["start_git_readonly_async"]["inputSchema"]
    assert set(git_schema["properties"]) == {"repo_name", "operation"}
    assert set(git_schema.get("required", [])) == {"repo_name", "operation"}
    assert actions["start_git_readonly_async"]["annotations"]["readOnlyHint"] is False

    commit_range_schema = actions["inspect_commit_range"]["inputSchema"]
    assert set(commit_range_schema["properties"]) == {
        "repo_name",
        "base_commit",
        "head_commit",
    }
    assert set(commit_range_schema.get("required", [])) == {
        "repo_name",
        "base_commit",
        "head_commit",
    }

    assert "dry_run_stage_manifest" in RETIRED_DIRECT_ACTIONS
    assert "dry_run_stage_manifest" not in actions

    compact_status_schema = actions["inspect_repo_status_compact"]["inputSchema"]
    assert set(compact_status_schema["properties"]) == {"repo_name"}
    assert set(compact_status_schema.get("required", [])) == {"repo_name"}


def test_cloudflare_tool_input_schemas_are_exact() -> None:
    actions = {action["name"]: action for action in discovered_actions()}

    capabilities_schema = actions["list_cloudflare_capabilities"]["inputSchema"]
    assert set(capabilities_schema["properties"]) == {"repo_name"}
    assert set(capabilities_schema.get("required", [])) == {"repo_name"}

    health_schema = actions["cloudflare_health"]["inputSchema"]
    assert set(health_schema["properties"]) == {"repo_name", "profile_id"}
    assert set(health_schema.get("required", [])) == {"repo_name", "profile_id"}

    inspect_schema = actions["cloudflare_inspect"]["inputSchema"]
    assert set(inspect_schema["properties"]) == {
        "repo_name",
        "profile_id",
        "operation",
        "resource_id",
        "name",
        "record_type",
        "since_minutes",
        "page",
        "per_page",
    }
    assert set(inspect_schema.get("required", [])) == {
        "repo_name",
        "profile_id",
        "operation",
    }

    action_schema = actions["start_cloudflare_action_async"]["inputSchema"]
    assert set(action_schema["properties"]) == {
        "repo_name",
        "profile_id",
        "action",
        "resource_id",
        "payload",
        "confirmation",
    }
    assert set(action_schema.get("required", [])) == {
        "repo_name",
        "profile_id",
        "action",
    }
    assert (
        actions["start_cloudflare_action_async"]["annotations"]["readOnlyHint"] is False
    )


def test_remote_capability_tools_delegate(monkeypatch) -> None:
    config = object()
    monkeypatch.setattr(server, "get_config", lambda: config)
    monkeypatch.setattr(
        server,
        "_list_ssh_capabilities",
        lambda received: {"ok": received is config, "enabled": True, "hosts": []},
    )
    monkeypatch.setattr(
        server,
        "_ssh_host_health",
        lambda received, host_id: {
            "ok": received is config,
            "status": "ok",
            "host_id": host_id,
        },
    )
    monkeypatch.setattr(
        server,
        "_enrich_ssh_capabilities",
        lambda received, result: {**result, "enriched": received is config},
    )

    listed = getattr(server, "list_ssh_capabilities")()
    health = getattr(server, "ssh_host_health")("my_vps")

    assert listed["ok"] is True
    assert health["ok"] is True
    assert health["status"] == "ok"
    assert health["host_id"] == "my_vps"
    assert len(health["server_build_hash"]) == 64
    assert len(health["schema_hash"]) == 64
    assert health["capability_epoch"]


def test_start_remote_command_async_delegates(monkeypatch) -> None:
    method_name = "start_ssh_command"

    def start(self, host_id, command_id):
        return {
            "run_id": "run_remote",
            "accepted": True,
            "status": "queued",
            "host_id": host_id,
            "command_id": command_id,
            "writes_remote": False,
        }

    fake_manager = type("FakeJobManager", (), {method_name: start})()
    monkeypatch.setattr(server, "get_job_manager", lambda: fake_manager)

    result = getattr(server, "start_ssh_command_async")("my_vps", "uptime")

    assert result["accepted"] is True
    assert result["run_id"] == "run_remote"
    assert result["host_id"] == "my_vps"
    assert result["command_id"] == "uptime"


def test_start_remote_monitored_command_async_delegates(monkeypatch) -> None:
    def start(self, host_id, command_id):
        return {
            "run_id": "run_monitored",
            "accepted": True,
            "status": "queued",
            "host_id": host_id,
            "command_id": command_id,
        }

    fake_manager = type("FakeJobManager", (), {"start_ssh_monitored_command": start})()
    monkeypatch.setattr(server, "get_job_manager", lambda: fake_manager)

    result = getattr(server, "start_ssh_monitored_command_async")("my_vps", "uptime")

    assert result["accepted"] is True
    assert result["run_id"] == "run_monitored"


def test_remote_tool_input_schemas_are_exact() -> None:
    actions = {action["name"]: action for action in discovered_actions()}
    list_name = "list_ssh_capabilities"
    start_name = "start_ssh_command_async"
    monitored_name = "start_ssh_monitored_command_async"

    assert set(actions[list_name]["inputSchema"]["properties"]) == set()
    for name in {"ssh_environment_probe", "ssh_gpu_telemetry"}:
        schema = actions[name]["inputSchema"]
        assert set(schema["properties"]) == {"host_id"}
        assert set(schema.get("required", [])) == {"host_id"}
    assert set(actions[start_name]["inputSchema"]["properties"]) == {
        "host_id",
        "command_id",
    }
    assert set(actions[start_name]["inputSchema"].get("required", [])) == {
        "host_id",
        "command_id",
    }
    assert set(actions[monitored_name]["inputSchema"]["properties"]) == {
        "host_id",
        "command_id",
    }


def test_list_runs_output_matches_schema(monkeypatch) -> None:
    class FakeJobManager:
        def list_runs(self, repo_name=None, status=None, limit=20):
            return [
                {
                    "run_id": "run_1",
                    "status": "completed",
                    "repo_name": repo_name or "repo",
                }
            ]

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobManager())
    action = {item["name"]: item for item in discovered_actions()}["list_runs"]

    result = server.list_runs(repo_name="repo")

    validate(instance=result, schema=action["outputSchema"])


def test_run_status_events_result_and_supervisor_schemas_are_present() -> None:
    actions = {item["name"]: item for item in discovered_actions()}
    for name in {
        "get_run_status",
        "get_run_control_status",
        "get_run_output",
        "get_run_events",
        "get_run_result",
        "list_operation_locks",
        "get_supervisor_status",
        "get_supervisor_events",
        "get_supervisor_result",
        "get_workflow_status",
        "get_workflow_events",
        "get_workflow_result",
    }:
        assert actions[name]["outputSchema"] is not None


def test_inspect_repo_status_normalizes_live_git_shapes(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "inspect_status",
        lambda repo_root: {
            "branch": "main",
            "git_status": "## main\n M codexbridge/server.py\n",
            "recent_commits": "abc123 first\n\ndef456 second\n",
            "diff_stat": " 1 file changed\n",
            "changed_files": ["codexbridge/server.py"],
        },
    )
    action = {item["name"]: item for item in discovered_actions()}[
        "inspect_repo_status"
    ]

    result = server.inspect_repo_status("repo")

    assert result["recent_commits"] == ["abc123 first", "def456 second"]
    assert result["changed_files"] == ["codexbridge/server.py"]
    validate(instance=result, schema=action["outputSchema"])


def test_inspect_repo_status_compact_excludes_full_status_payload(
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
            "recent_commits": "abc123 first\n",
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
                "total_bytes": 4,
                "root_group_counts": {".codex-tmp": 1},
                "sample": [
                    {
                        "path": ".codex-tmp/run.txt",
                        "size_bytes": 4,
                        "line_count": 1,
                        "tool_owned": True,
                        "index_status": "?",
                        "worktree_status": "?",
                    }
                ],
                "truncated": False,
            },
            "fallback_tool": "inspect_repo_status",
            "git_status": "## main\n M codexbridge/server.py\n",
            "manifest": {"git_status": "## main\n M codexbridge/server.py\n"},
        },
    )
    action = {item["name"]: item for item in discovered_actions()}[
        "inspect_repo_status_compact"
    ]

    result = server.inspect_repo_status_compact("repo")

    assert "git_status" not in result
    assert "manifest" not in result
    validate(instance=result, schema=action["outputSchema"])


def test_event_list_actions_return_wrapped_dicts(monkeypatch, tmp_path) -> None:
    class FakeJobManager:
        def get_events(self, run_id, limit=50):
            return [{"stage": "queued", "message": "Run queued"}]

    class FakeSupervisorService:
        def get_events(self, supervisor_id, limit=50):
            return [{"stage": "planning", "message": "Supervisor tick"}]

        def get_notifications(self, supervisor_id, delivery_status=None, limit=50):
            return [{"id": 1, "delivery_status": "pending"}]

    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobManager())
    monkeypatch.setattr(
        server, "get_supervisor_service", lambda: FakeSupervisorService()
    )
    actions = {item["name"]: item for item in discovered_actions()}

    run_events = server.get_run_events("run_1")
    supervisor_events = server.get_supervisor_events("sup_1")
    notifications = server.get_supervisor_notifications("sup_1")

    assert run_events["run_id"] == "run_1"
    assert supervisor_events["supervisor_id"] == "sup_1"
    assert notifications["supervisor_id"] == "sup_1"
    validate(instance=run_events, schema=actions["get_run_events"]["outputSchema"])
    validate(
        instance=supervisor_events,
        schema=actions["get_supervisor_events"]["outputSchema"],
    )
    validate(instance=notifications, schema=server.EVENT_LIST_OUTPUT)
