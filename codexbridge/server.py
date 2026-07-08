from __future__ import annotations

import argparse
import inspect
import json
import socket
import time
import urllib.error
import urllib.request
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from typing import Sequence

from fastmcp import FastMCP

from .capabilities import PATCH_OPERATION_SCHEMA, capability_metadata
from .config import (
    AppConfig,
    load_config,
    resolve_repo_config,
    resolve_repo_identity,
)
from .docker_tools import (
    docker_health as _docker_health,
    list_docker_capabilities as _list_docker_capabilities,
    run_docker_inspection as _run_docker_inspection,
)
from .git_tools import CommitMetadataError
from .git_tools import commit_all_changes as _commit_all_changes
from .git_tools import commit_selected_files as commit_files
from .git_tools import dry_run_stage_manifest as _dry_run_stage_manifest
from .git_tools import changed_files as _changed_files
from .git_tools import diff_stat, git_status, inspect_status
from .git_tools import finalize_explicit_changes
from .git_tools import inspect_status_compact
from .git_tools import inspect_commit_range as _inspect_commit_range
from .git_tools import git_diff as _git_diff_raw
from .git_tools import create_branch as _git_create_branch
from .git_tools import stage_all as _stage_all
from .git_tools import unstage_all as _unstage_all
from .job_manager import JobManager
from .managed_artifacts import (
    apply_managed_artifact_cleanup as _apply_managed_artifact_cleanup,
    preview_managed_artifact_cleanup as _preview_managed_artifact_cleanup,
)
from .operation_locks import repository_operation_lock
from . import repo_reader as _repo_reader
from . import repo_writer as _repo_writer
from .command_profiles import (
    build_git_readonly_profile,
    resolve_command_profile,
    run_command_profile,
)
from .runner import latest_run_result as latest_artifact_result
from .service_reload import apply_reloaded_config, reload_service as _reload_service
from .self_check import run_self_check
from .supervisor_service import SupervisorService
from .ssh_commands import list_ssh_capabilities as _list_ssh_capabilities
from .ssh_commands import ssh_host_health as _ssh_host_health
from .ssh_tools import enrich_ssh_capabilities as _enrich_ssh_capabilities
from .ssh_tools import run_ssh_inspection as _run_ssh_inspection
from .local_agent.models import LocalModelStatus
from .local_agent.ollama_adapter import OllamaChatAdapter


mcp = FastMCP("CodexBridge")
_PROCESS_CAPABILITY_METADATA = capability_metadata(PATCH_OPERATION_SCHEMA)
_original_mcp_tool = mcp.tool


def _tool_with_capability_metadata(*tool_args, **tool_kwargs):
    register = _original_mcp_tool(*tool_args, **tool_kwargs)

    def decorate(function):
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def async_wrapped(*args, **kwargs):
                result = await function(*args, **kwargs)
                if isinstance(result, dict):
                    result = dict(result)
                    for key, value in _PROCESS_CAPABILITY_METADATA.items():
                        result.setdefault(key, value)
                return result

            return register(async_wrapped)

        @wraps(function)
        def sync_wrapped(*args, **kwargs):
            result = function(*args, **kwargs)
            if isinstance(result, dict):
                result = dict(result)
                for key, value in _PROCESS_CAPABILITY_METADATA.items():
                    result.setdefault(key, value)
            return result

        return register(sync_wrapped)

    return decorate


mcp.tool = _tool_with_capability_metadata
_config: AppConfig | None = None
_config_path: Path | None = None
READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}
CODEX_WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
GENERIC_OBJECT_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": "string"},
        "message": {"type": "string"},
        "status": {"type": "string"},
    },
}
RUN_RESULT_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "run_id": {"type": "string"},
        "status": {"type": "string"},
        "repo_name": {"type": "string"},
        "result": {"type": "object", "additionalProperties": True},
        "error": {"type": "string"},
    },
}
RUN_LIST_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "runs": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "result": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "error": {"type": "string"},
    },
}
EVENT_LIST_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "run_id": {"type": "string"},
        "supervisor_id": {"type": "string"},
        "events": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "notifications": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "error": {"type": "string"},
    },
}
SUPERVISOR_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "supervisor_id": {"type": "string"},
        "status": {"type": "string"},
        "result": {"type": "object", "additionalProperties": True},
        "error": {"type": "string"},
    },
}
SELF_CHECK_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "checks": {"type": "object", "additionalProperties": True},
        "error": {"type": "string"},
    },
}
REPO_STATUS_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "branch": {"type": "string"},
        "status": {"type": "string"},
        "git_status": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "diff_stat": {"type": "string"},
        "recent_commits": {"type": "array", "items": {"type": "string"}},
        "manifest": {"type": "object", "additionalProperties": True},
        "error": {"type": "string"},
    },
}
REPO_STATUS_COMPACT_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "branch": {"type": "string"},
        "diff_stat": {"type": "string"},
        "recent_commits": {"type": "array", "items": {"type": "string"}},
        "complete_status_scan": {"type": "boolean"},
        "total_status_entry_count": {"type": "integer"},
        "returned_entry_count": {"type": "integer"},
        "collapsed_tool_owned_count": {"type": "integer"},
        "sampled_tool_owned_count": {"type": "integer"},
        "unsampled_tool_owned_count": {"type": "integer"},
        "files": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "tool_owned_summary": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "total_bytes": {"type": "integer"},
                "root_group_counts": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "sample": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": True},
                },
                "truncated": {"type": "boolean"},
            },
        },
        "fallback_tool": {"type": "string"},
        "error": {"type": "string"},
    },
}
CODEX_PLAN_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "plan": {"type": "string"},
        "result": {"type": "object", "additionalProperties": True},
        "error": {"type": "string"},
    },
}
CODEX_IMPLEMENT_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "tests": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "result": {"type": "object", "additionalProperties": True},
        "error": {"type": "string"},
    },
}
COMMIT_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "files_validated": {"type": "boolean"},
        "commit_hash": {"type": "string"},
        "remaining_dirty_files": {
            "type": "array",
            "items": {"type": "string"},
        },
        "git_status": {"type": "string"},
        "blocked_field": {"type": "string"},
        "reason_code": {"type": "string"},
        "reason": {"type": "string"},
        "error": {"type": "string"},
    },
}
LIST_REPO_FILES_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "directory": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "count": {"type": "integer"},
        "truncated": {"type": "boolean"},
        "max_results": {"type": "integer"},
        "error": {"type": "string"},
    },
}
READ_REPO_FILE_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "path": {"type": "string"},
        "content": {"type": "string"},
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
        "total_lines": {"type": "integer"},
        "size_bytes": {"type": "integer"},
        "sha256": {"type": "string"},
        "git_head": {"type": "string"},
        "truncated": {"type": "boolean"},
        "error": {"type": "string"},
    },
}
SEARCH_REPO_TEXT_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "query": {"type": "string"},
        "directory": {"type": "string"},
        "case_sensitive": {"type": "boolean"},
        "hits": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                    "snippet": {"type": "string"},
                },
            },
        },
        "count": {"type": "integer"},
        "truncated": {"type": "boolean"},
        "max_results": {"type": "integer"},
        "error": {"type": "string"},
    },
}
RECENTLY_MODIFIED_FILES_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "path": {"type": "string"},
                    "mtime": {"type": "number"},
                },
            },
        },
        "count": {"type": "integer"},
        "limit": {"type": "integer"},
        "error": {"type": "string"},
    },
}
REPO_GIT_STATUS_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "status": {"type": "string"},
        "error": {"type": "string"},
    },
}
REPO_GIT_DIFF_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "path": {"type": "string"},
        "staged": {"type": "boolean"},
        "diff": {"type": "string"},
        "truncated": {"type": "boolean"},
        "error": {"type": "string"},
    },
}
COMMIT_RANGE_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "base_commit": {"type": "string"},
        "head_commit": {"type": "string"},
        "name_status": {"type": "string"},
        "diff_stat": {"type": "string"},
        "diff": {"type": "string"},
        "truncated": {"type": "boolean"},
        "error": {"type": "string"},
    },
}
PREVIEW_PATCH_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "patch_id": {"type": "string"},
        "repo_name": {"type": "string"},
        "diff": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "changed_lines": {"type": "integer"},
        "changed_bytes": {"type": "integer"},
        "git_head": {"type": "string"},
        "validation_errors": {"type": "array", "items": {"type": "string"}},
        "error": {"type": "string"},
    },
}
APPLY_PATCH_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "patch_id": {"type": "string"},
        "repo_name": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "path": {"type": "string"},
                    "sha256": {"type": "string"},
                },
            },
        },
        "git_head": {"type": "string"},
        "error": {"type": "string"},
    },
}
CREATE_FILE_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "path": {"type": "string"},
        "sha256": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "error": {"type": "string"},
    },
}
DELETE_FILE_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "path": {"type": "string"},
        "rollback_id": {"type": "string"},
        "error": {"type": "string"},
    },
}
MOVE_FILE_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "source_path": {"type": "string"},
        "destination_path": {"type": "string"},
        "sha256": {"type": "string"},
        "rollback_id": {"type": "string"},
        "error": {"type": "string"},
    },
}
REVERT_PATCH_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "patch_id": {"type": "string"},
        "repo_name": {"type": "string"},
        "reverted_files": {"type": "array", "items": {"type": "string"}},
        "error": {"type": "string"},
    },
}
RUN_COMMAND_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "command_id": {"type": "string"},
        "argv": {"type": "array", "items": {"type": "string"}},
        "exit_code": {"type": "integer"},
        "timed_out": {"type": "boolean"},
        "duration_seconds": {"type": "number"},
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
        "output_truncated": {"type": "boolean"},
        "error": {"type": "string"},
    },
}
GIT_LOG_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "commits": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "sha": {"type": "string"},
                    "author_name": {"type": "string"},
                    "author_email": {"type": "string"},
                    "date": {"type": "string"},
                    "subject": {"type": "string"},
                },
            },
        },
        "count": {"type": "integer"},
        "path": {"type": "string"},
        "error": {"type": "string"},
    },
}
READ_REPO_FILES_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "results": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "count": {"type": "integer"},
        "truncated_batch": {"type": "boolean"},
        "error": {"type": "string"},
    },
}
CREATE_BRANCH_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "branch_name": {"type": "string"},
        "error": {"type": "string"},
    },
}
LOCAL_MODEL_HEALTH_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "status": {
            "type": "string",
            "enum": [
                "ok",
                "disabled",
                "unavailable",
                "timeout",
                "failed",
                "model_missing",
            ],
        },
        "enabled": {"type": "boolean"},
        "base_url": {"type": "string"},
        "model": {"type": "string"},
        "models_endpoint_reachable": {"type": "boolean"},
        "configured_model_available": {"type": ["boolean", "null"]},
        "completion_succeeded": {"type": "boolean"},
        "duration_seconds": {"type": "number"},
        "timeout_seconds": {"type": "integer"},
        "error": {"type": "string"},
        "audit_event_id": {"type": ["string", "null"]},
    },
}


class _StructuredListResult(dict):
    def __init__(self, list_key: str, payload: dict):
        super().__init__(payload)
        self._list_key = list_key

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._list_key)[key]
        return super().__getitem__(key)


def _normalize_text_lines(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if not isinstance(value, str):
        return []
    return [line for line in (part.strip() for part in value.splitlines()) if line]


def _wrap_item_list(
    key: str, owner_id_key: str, owner_id: str, items: list[dict]
) -> dict:
    return _StructuredListResult(
        key,
        {
            "ok": True,
            owner_id_key: owner_id,
            key: items,
            "error": "",
        },
    )


def _local_model_urlopen(request: urllib.request.Request, timeout_seconds: int) -> Any:
    return urllib.request.urlopen(request, timeout=timeout_seconds)


def _local_model_transport(
    request: urllib.request.Request, timeout_seconds: int
) -> Any:
    return urllib.request.urlopen(request, timeout=timeout_seconds)


def _safe_local_model_error(text: object) -> str:
    return str(text)[:500]


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")
    except Exception:
        return ""


def _extract_model_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Malformed local model /models response: missing data list")
    ids = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
    return ids


try:
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")
except Exception:
    # FastMCP custom routes are a convenience, not the readiness contract.
    pass


def set_config(config: AppConfig, config_path: Path | None = None) -> None:
    global _config, _config_path
    _config = config
    _config_path = config_path


def get_config() -> AppConfig:
    if _config is None:
        raise RuntimeError("CodexBridge config has not been loaded")
    return _config


def get_config_path() -> Path | None:
    return _config_path


def get_job_manager() -> JobManager:
    return JobManager(get_config(), get_config_path())


def get_supervisor_service() -> SupervisorService:
    return SupervisorService(get_config(), get_config_path())


def _repo_context(repo_name: str) -> tuple[str, Path, str]:
    canonical_name, repo_root, _ = resolve_repo_identity(get_config(), repo_name)
    return canonical_name, repo_root, repo_name


def _with_capability_metadata(result: dict[str, Any]) -> dict[str, Any]:
    result.update(capability_metadata(PATCH_OPERATION_SCHEMA))
    return result


def _locked_repo_operation(
    repo_name: str,
    tool: str,
    normalized_input: dict[str, Any],
    operation: Callable[[Path], dict[str, Any]],
    *,
    finalize_commit: bool = False,
) -> dict[str, Any]:
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    with repository_operation_lock(
        get_config().resolve_runs_dir(),
        repo_name=canonical_name,
        tool=tool,
        normalized_input=normalized_input,
    ):
        result = operation(repo_root)
        if result.get("ok") and finalize_commit:
            commit_data = finalize_explicit_changes(
                repo_root,
                result.get("changed_files") or [],
                tool_name=tool,
            )
            result = dict(result)
            result.update(commit_data)
            if commit_data["commit_attempted"] and commit_data["commit_error"]:
                result["ok"] = False
                result["status"] = "commit_failed"
                result["error"] = commit_data["commit_error"]
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
async def list_capabilities() -> dict:
    """Read-only: return the authoritative live tool list and schema epoch."""
    tools = await mcp.list_tools()
    actions = [tool.to_mcp_tool().model_dump(mode="json") for tool in tools]
    result: dict[str, Any] = {
        "ok": True,
        "actions": actions,
        "action_names": sorted(str(action.get("name", "")) for action in actions),
        "patch_operation_schema": PATCH_OPERATION_SCHEMA,
        "error": "",
    }
    return _with_capability_metadata(result)


@mcp.tool(output_schema=REPO_STATUS_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def inspect_repo_status(repo_name: str) -> dict:
    """Read-only: return git status, branch, recent commits, changed files, and diff stat."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = dict(inspect_status(repo_root))
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    result["ok"] = True
    result["recent_commits"] = _normalize_text_lines(result.get("recent_commits"))
    changed_files = result.get("changed_files")
    if isinstance(changed_files, list):
        result["changed_files"] = [str(item) for item in changed_files]
    else:
        result["changed_files"] = _normalize_text_lines(changed_files)
    diff_stat = result.get("diff_stat")
    result["diff_stat"] = diff_stat if isinstance(diff_stat, str) else ""
    git_status_text = result.get("git_status")
    result["git_status"] = git_status_text if isinstance(git_status_text, str) else ""
    return result


@mcp.tool(output_schema=REPO_STATUS_COMPACT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def inspect_repo_status_compact(repo_name: str) -> dict:
    """Read-only: return a compact repository status with tool-owned changes summarized."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = dict(inspect_status_compact(repo_root))
    result.pop("git_status", None)
    result.pop("manifest", None)
    result.pop("tool_owned", None)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    result["ok"] = True
    result["recent_commits"] = _normalize_text_lines(result.get("recent_commits"))
    diff_stat = result.get("diff_stat")
    result["diff_stat"] = diff_stat if isinstance(diff_stat, str) else ""
    return result


@mcp.tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def codex_plan_task(repo_name: str, task: str, constraints: str = "") -> dict:
    """Compatibility alias: queue a durable plan-only Codex run and return its run ID."""
    result = get_job_manager().start_plan(repo_name, task, constraints)
    result["deprecated_sync_alias"] = True
    result["replacement_tool"] = "start_codex_plan_task_async"
    return result


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=CODEX_WRITE_ANNOTATIONS)
def codex_implement_task(
    repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]
) -> dict:
    """Compatibility alias: queue durable Codex implementation and return its run ID."""
    result = get_job_manager().start_implementation(
        repo_name, approved_plan, allowed_files, tests
    )
    result["deprecated_sync_alias"] = True
    result["replacement_tool"] = "start_codex_implement_task_async"
    return result


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_latest_run_result(repo_name: str = "", tool: str = "") -> dict:
    """Read-only: return the most recent saved CodexBridge run result."""
    config = get_config()
    requested_name = repo_name or None
    repo_name = repo_name or None
    tool = tool or None
    if repo_name or tool:
        result = get_job_manager().latest_result(repo_name=repo_name, tool=tool)
        canonical_name = result.get("repo_name")
        if requested_name and canonical_name and requested_name != canonical_name:
            result = dict(result)
            result["requested_repo_name"] = requested_name
        return result
    try:
        return get_job_manager().latest_result()
    except Exception:
        return latest_artifact_result(config.resolve_runs_dir())


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def git_diff_summary(repo_name: str) -> dict:
    """Read-only: return git status and diff stat for a whitelisted repo."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = {
        "ok": True,
        "repo_name": canonical_name,
        "git_status": git_status(repo_root),
        "diff_stat": diff_stat(repo_root),
        "error": "",
    }
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=COMMIT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def commit_selected_files(
    repo_name: str,
    files: list[str],
    title: str,
    description: str = "",
) -> dict:
    """Stage and commit only validated repository files.

    The title and description are inert Git metadata passed as argv values;
    they are never executed. This tool never pushes.
    """
    config = get_config()
    canonical_name, repo_root, requested_name = _repo_context(repo_name)

    try:
        with repository_operation_lock(
            config.resolve_runs_dir(),
            repo_name=canonical_name,
            tool="commit_selected_files",
            normalized_input={
                "files": files,
                "title": title,
                "description": description,
            },
        ):
            result = commit_files(repo_root, files, title, description)
    except CommitMetadataError as exc:
        return {
            "ok": False,
            "repo_name": canonical_name,
            "files_validated": exc.files_validated,
            "blocked_field": exc.field,
            "reason_code": exc.reason_code,
            "reason": exc.reason,
            "error": exc.reason,
        }

    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def dry_run_stage_manifest(repo_name: str, include_ignored: bool = False) -> dict:
    """Read-only: preview which files would be staged without changing git state."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _dry_run_stage_manifest(repo_root, include_ignored=include_ignored)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def stage_all(repo_name: str) -> dict:
    """Write tool: stage all repository changes and return before/after manifest details."""
    config = get_config()
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    with repository_operation_lock(
        config.resolve_runs_dir(),
        repo_name=canonical_name,
        tool="stage_all",
        normalized_input={"repo_name": canonical_name},
    ):
        result = _stage_all(repo_root)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def unstage_all(repo_name: str) -> dict:
    """Write tool: unstage all currently staged changes and return before/after manifest details."""
    config = get_config()
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    with repository_operation_lock(
        config.resolve_runs_dir(),
        repo_name=canonical_name,
        tool="unstage_all",
        normalized_input={"repo_name": canonical_name},
    ):
        result = _unstage_all(repo_root)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=COMMIT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def commit_all_changes(repo_name: str, title: str, description: str = "") -> dict:
    """Write tool: stage and commit all current repository changes with validated metadata. Never pushes."""
    config = get_config()
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    try:
        with repository_operation_lock(
            config.resolve_runs_dir(),
            repo_name=canonical_name,
            tool="commit_all_changes",
            normalized_input={"title": title, "description": description},
        ):
            result = _commit_all_changes(repo_root, title, description)
    except CommitMetadataError as exc:
        return {
            "ok": False,
            "repo_name": canonical_name,
            "files_validated": exc.files_validated,
            "blocked_field": exc.field,
            "reason_code": exc.reason_code,
            "reason": exc.reason,
            "error": exc.reason,
        }
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=SELF_CHECK_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def run_local_self_check() -> dict:
    """Read-only: run local setup, test, git, and MCP transport readiness checks."""
    config = get_config()
    return run_self_check(config=config, config_path=get_config_path(), live_port=8765)


@mcp.tool(output_schema=LOCAL_MODEL_HEALTH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def local_model_health() -> dict:
    """Read-only: verify configured Ollama/OpenAI-compatible local model connectivity with a tiny smoke prompt."""
    config = get_config().local_model
    started = time.monotonic()
    base_url = config.base_url.rstrip("/")
    result = {
        "ok": False,
        "status": "disabled",
        "enabled": bool(config.enabled),
        "base_url": base_url,
        "model": config.model,
        "models_endpoint_reachable": False,
        "configured_model_available": None,
        "completion_succeeded": False,
        "duration_seconds": 0.0,
        "timeout_seconds": config.timeout_seconds,
        "error": "",
        "audit_event_id": None,
    }
    if not config.enabled:
        result["error"] = "Local model is disabled."
        result["duration_seconds"] = time.monotonic() - started
        return result

    try:
        models_request = urllib.request.Request(f"{base_url}/models", method="GET")
        models_response = _local_model_urlopen(models_request, config.timeout_seconds)
        status_code = int(
            getattr(models_response, "status", getattr(models_response, "code", 200))
        )
        raw_body = models_response.read().decode("utf-8")
        if status_code < 200 or status_code >= 300:
            result["status"] = "failed"
            result["error"] = (
                f"Local model /models HTTP status {status_code}: {_safe_local_model_error(raw_body)}"
            )
            return _finish_local_model_health(result, started)
        model_ids = _extract_model_ids(json.loads(raw_body))
        result["models_endpoint_reachable"] = True
        result["configured_model_available"] = config.model in model_ids
        if not result["configured_model_available"]:
            result["status"] = "model_missing"
            result["error"] = (
                f"Configured local model is not listed by /models: {config.model}"
            )
            return _finish_local_model_health(result, started)
    except urllib.error.HTTPError as exc:
        result["status"] = "failed"
        result["error"] = (
            f"Local model /models HTTP status {exc.code}: {_safe_local_model_error(_read_http_error(exc))}"
        )
        return _finish_local_model_health(result, started)
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", None)
        result["status"] = (
            "timeout"
            if isinstance(exc, (TimeoutError, socket.timeout))
            or isinstance(reason, (TimeoutError, socket.timeout))
            else "unavailable"
        )
        result["error"] = _safe_local_model_error(exc)
        return _finish_local_model_health(result, started)
    except TimeoutError as exc:
        result["status"] = "timeout"
        result["error"] = _safe_local_model_error(exc)
        return _finish_local_model_health(result, started)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        result["status"] = "failed"
        result["error"] = _safe_local_model_error(exc)
        return _finish_local_model_health(result, started)

    smoke = OllamaChatAdapter(
        base_url=base_url,
        model=config.model,
        timeout_seconds=config.timeout_seconds,
        temperature=config.temperature,
        max_tokens=min(config.max_tokens, 16),
        transport=_local_model_transport,
    ).call(
        task_type="local_model_health",
        messages=[
            {
                "role": "system",
                "content": "You are a health check endpoint. Reply with OK.",
            },
            {"role": "user", "content": "Reply with OK."},
        ],
        max_tokens=min(config.max_tokens, 16),
    )
    result["audit_event_id"] = smoke.audit_event_id
    result["completion_succeeded"] = smoke.status == LocalModelStatus.SUCCESS
    if smoke.status == LocalModelStatus.SUCCESS:
        result["ok"] = True
        result["status"] = "ok"
    elif smoke.status == LocalModelStatus.TIMEOUT:
        result["status"] = "timeout"
        result["error"] = smoke.error
    elif smoke.status == LocalModelStatus.UNAVAILABLE:
        result["status"] = "unavailable"
        result["error"] = smoke.error
    else:
        result["status"] = "failed"
        result["error"] = (
            smoke.error
            or f"Local model smoke prompt failed with status: {smoke.status.value}"
        )
    return _finish_local_model_health(result, started)


def _finish_local_model_health(result: dict, started: float) -> dict:
    result["duration_seconds"] = time.monotonic() - started
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_docker_capabilities(repo_name: str = "") -> dict:
    """Read-only: list bounded Docker operations, risk gates, and configured exec profiles."""
    config = get_config()
    if not repo_name:
        return _list_docker_capabilities(config)
    canonical_name, _repo_root, requested_name = _repo_context(repo_name)
    _, repo_config = resolve_repo_config(config, canonical_name)
    result = _list_docker_capabilities(config, repo_config)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def docker_health() -> dict:
    """Read-only: verify Docker Engine and Docker Compose connectivity."""
    return _docker_health(get_config())


@mcp.tool(
    output_schema=RUN_COMMAND_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def docker_inspect(
    repo_name: str,
    operation: str,
    target: str = "",
    service: str = "",
    tail: int = 200,
) -> dict:
    """Read-only: run one fixed Docker or Compose inspection operation."""
    config = get_config()
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    _, repo_config = resolve_repo_config(config, canonical_name)
    result = _run_docker_inspection(
        config,
        repo_root,
        repo_config,
        operation,
        target=target,
        service=service,
        tail=tail,
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_ssh_capabilities() -> dict:
    """Read-only: list SSH hosts, inspections, actions, transfers, deployments, and risk gates."""
    config = get_config()
    return _enrich_ssh_capabilities(config, _list_ssh_capabilities(config))


@mcp.tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def ssh_host_health(host_id: str) -> dict:
    """Read-only: test one configured SSH alias with a fixed non-interactive command."""
    return _ssh_host_health(get_config(), host_id)


@mcp.tool(
    output_schema=RUN_COMMAND_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def ssh_inspect(
    host_id: str,
    operation: str,
    path: str = "",
    target: str = "",
    deployment_id: str = "",
    tail: int = 200,
) -> dict:
    """Read-only: run one bounded SSH system, service, log, Git, Docker, or file inspection."""
    return _run_ssh_inspection(
        get_config(),
        host_id,
        operation,
        path=path,
        target=target,
        deployment_id=deployment_id,
        tail=tail,
    )


@mcp.tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_external_fixture_validation_async(
    repo_name: str,
    url: str,
    expected_sha256: str,
    validation: str = "none",
) -> dict:
    """Queue hash-pinned validation of one allowlisted HTTPS fixture in run storage."""
    return get_job_manager().start_external_fixture_validation(
        repo_name,
        url,
        expected_sha256,
        validation,
    )


@mcp.tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_command_async(host_id: str, command_id: str) -> dict:
    """Write async tool: queue one configured SSH command by host ID and command ID."""
    return get_job_manager().start_ssh_command(host_id, command_id)


@mcp.tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_action_async(
    host_id: str,
    action: str,
    target: str = "",
    source: str = "",
    destination: str = "",
    path: str = "",
    deployment_id: str = "",
    command_id: str = "",
    packages: list[str] = [],
    executable: str = "",
    args: list[str] = [],
    force: bool = False,
    confirmation: str = "",
) -> dict:
    """Write async tool: queue one bounded SSH administration, Git, service, or Compose action."""
    return get_job_manager().start_ssh_action(
        host_id,
        action,
        target=target,
        source=source,
        destination=destination,
        path=path,
        deployment_id=deployment_id,
        command_id=command_id,
        packages=packages,
        executable=executable,
        args=args,
        force=force,
        confirmation=confirmation,
    )


@mcp.tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_transfer_async(
    host_id: str,
    direction: str,
    repo_name: str,
    local_path: str,
    remote_path: str,
    recursive: bool = False,
    overwrite: bool = False,
    confirmation: str = "",
) -> dict:
    """Write async tool: queue a repository-scoped upload or run-artifact download using SCP."""
    return get_job_manager().start_ssh_transfer(
        host_id,
        direction,
        repo_name=repo_name,
        local_path=local_path,
        remote_path=remote_path,
        recursive=recursive,
        overwrite=overwrite,
        confirmation=confirmation,
    )


@mcp.tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_deployment_async(
    host_id: str,
    deployment_id: str,
    confirmation: str,
) -> dict:
    """Write async tool: deploy a configured repository as an archive release and activate it remotely."""
    return get_job_manager().start_ssh_deployment(
        host_id,
        deployment_id,
        confirmation=confirmation,
    )


@mcp.tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def start_codex_plan_task_async(
    repo_name: str, task: str, constraints: str = ""
) -> dict:
    """Read-only async tool: queue a plan-only Codex job and return a durable run_id immediately."""
    return get_job_manager().start_plan(repo_name, task, constraints)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=CODEX_WRITE_ANNOTATIONS)
def start_codex_implement_task_async(
    repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]
) -> dict:
    """Write async tool: queue an approved implementation Codex job and return a durable run_id immediately."""
    return get_job_manager().start_implementation(
        repo_name, approved_plan, allowed_files, tests
    )


@mcp.tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_docker_action_async(
    repo_name: str,
    action: str,
    target: str = "",
    destination: str = "",
    services: list[str] = [],
    command_id: str = "",
    context: str = ".",
    dockerfile: str = "",
    build: bool = False,
    force: bool = False,
    confirmation: str = "",
) -> dict:
    """Write async tool: queue one bounded Docker action; high-risk actions require config opt-in and confirmation."""
    return get_job_manager().start_docker_action(
        repo_name,
        action,
        target=target,
        destination=destination,
        services=services,
        command_id=command_id,
        context=context,
        dockerfile=dockerfile,
        build=build,
        force=force,
        confirmation=confirmation,
    )


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_project_command_async(repo_name: str, command_id: str) -> dict:
    """Write async tool: queue an allowlisted project command and return a durable run_id immediately."""
    return get_job_manager().start_project_command(repo_name, command_id)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_pytest_path_async(repo_name: str, path: str) -> dict:
    """Write async tool: queue scoped pytest for one validated repo-relative target and return a durable run_id immediately."""
    return get_job_manager().start_pytest_path(repo_name, path)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_py_compile_path_async(repo_name: str, path: str) -> dict:
    """Write async tool: queue py_compile validation for one validated repo-relative Python target."""
    return get_job_manager().start_py_compile_path(repo_name, path)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_bash_n_path_async(repo_name: str, path: str) -> dict:
    """Write async tool: queue bash -n validation for one validated repo-relative shell target."""
    return get_job_manager().start_bash_n_path(repo_name, path)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_json_validation_path_async(repo_name: str, path: str) -> dict:
    """Write async tool: queue JSON syntax validation for one validated repo-relative target."""
    return get_job_manager().start_json_validation_path(repo_name, path)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_git_readonly_async(repo_name: str, operation: str) -> dict:
    """Write async tool: queue one allowlisted read-only git inspection operation and return a durable run_id."""
    build_git_readonly_profile(operation)
    return get_job_manager().start_git_readonly(repo_name, operation)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_status(run_id: str) -> dict:
    """Read-only: return durable status metadata for a queued/running/completed async run."""
    return get_job_manager().get_status(run_id)


@mcp.tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_events(run_id: str, limit: int = 50) -> dict:
    """Read-only: return recent timeline events for an async run."""
    return _wrap_item_list(
        "events", "run_id", run_id, get_job_manager().get_events(run_id, limit)
    )


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_result(run_id: str) -> dict:
    """Read-only: return the final or current structured result for an async run."""
    return get_job_manager().get_result(run_id)


@mcp.tool(output_schema=RUN_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_runs(repo_name: str = "", status: str = "", limit: int = 20) -> dict:
    """Read-only: list recent async runs with optional repo/status filters."""
    return {
        "ok": True,
        "runs": get_job_manager().list_runs(
            repo_name=repo_name or None, status=status or None, limit=limit
        ),
        "error": "",
    }


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def cancel_run(run_id: str) -> dict:
    """Write tool: request cancellation of a running async job without deleting artifacts."""
    return get_job_manager().cancel_run(run_id)


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def reload_service(modules: list[str] = []) -> dict:
    """Write tool: reload supported CodexBridge modules and refresh in-memory config when possible."""
    result = _reload_service(get_config_path(), modules=modules)
    if result["ok"] and get_config_path() is not None:
        set_config(apply_reloaded_config(get_config_path()), get_config_path())
    return result


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_supervised_recovery_task(
    repo_name: str,
    objective: str,
    task: str,
    constraints: str = "",
    source_run_id: str = "",
    autonomy_profile: str = "balanced",
) -> dict:
    """Write tool: create a supervisor and advance it one safe step."""
    return get_supervisor_service().start_supervised_recovery_task(
        repo_name, objective, task, constraints, source_run_id or None, autonomy_profile
    )


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_status(supervisor_id: str) -> dict:
    """Read-only: return enriched supervisor status."""
    return get_supervisor_service().get_status(supervisor_id)


@mcp.tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_events(supervisor_id: str, limit: int = 50) -> dict:
    """Read-only: return ordered supervisor events."""
    return _wrap_item_list(
        "events",
        "supervisor_id",
        supervisor_id,
        get_supervisor_service().get_events(supervisor_id, limit),
    )


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_result(supervisor_id: str) -> dict:
    """Read-only: return supervisor result metadata and linked run references."""
    return get_supervisor_service().get_result(supervisor_id)


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
def resume_supervisor(supervisor_id: str) -> dict:
    """Write tool: advance a supervisor exactly one safe step."""
    return get_supervisor_service().resume(supervisor_id)


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
def pause_supervisor(supervisor_id: str) -> dict:
    """Write tool: pause a queued or needs_input supervisor."""
    return get_supervisor_service().pause(supervisor_id)


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
def cancel_supervisor(supervisor_id: str) -> dict:
    """Write tool: cancel a supervisor and active child if present."""
    return get_supervisor_service().cancel(supervisor_id)


@mcp.tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_notifications(
    supervisor_id: str, delivery_status: str = "", limit: int = 50
) -> dict:
    """Read-only: return persisted supervisor notification rows."""
    return _wrap_item_list(
        "notifications",
        "supervisor_id",
        supervisor_id,
        get_supervisor_service().get_notifications(
            supervisor_id, delivery_status or None, limit
        ),
    )


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_resume_prompt(supervisor_id: str) -> dict:
    """Read-only: return the canonical supervisor resume prompt if present."""
    return get_supervisor_service().get_resume_prompt(supervisor_id)


@mcp.tool(output_schema=LIST_REPO_FILES_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_repo_files(
    repo_name: str, directory: str = "", max_results: int = 500
) -> dict:
    """Read-only: list files in a repository directory. Returns repo-relative POSIX paths only."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.list_repo_files(
        repo_root, directory=directory, max_results=max_results
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=READ_REPO_FILE_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def read_repo_file(
    repo_name: str, path: str, start_line: int = 1, end_line: int = 0
) -> dict:
    """Read-only: read a text file from a repository. Rejects binary files, caps output, and redacts secrets."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.read_repo_file(
        repo_root, path, start_line=start_line, end_line=end_line
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=SEARCH_REPO_TEXT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def search_repo_text(
    repo_name: str,
    query: str,
    directory: str = "",
    max_results: int = 50,
    case_sensitive: bool = False,
) -> dict:
    """Read-only: search for a literal string in repository text files. Returns path, line, and redacted snippets."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.search_repo_text(
        repo_root,
        query,
        directory=directory,
        max_results=max_results,
        case_sensitive=case_sensitive,
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(
    output_schema=RECENTLY_MODIFIED_FILES_OUTPUT, annotations=READ_ONLY_ANNOTATIONS
)
def get_recently_modified_files(repo_name: str, limit: int = 50) -> dict:
    """Read-only: list files sorted by filesystem mtime, newest first. Reflects unsaved changes immediately."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.get_recently_modified_files(repo_root, limit=limit)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=REPO_GIT_STATUS_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def repo_git_status(repo_name: str) -> dict:
    """Read-only: return raw git status --short --branch output for a whitelisted repository."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    status_text = git_status(repo_root)
    result = {
        "ok": True,
        "repo_name": canonical_name,
        "status": status_text,
        "error": "",
    }
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=REPO_GIT_DIFF_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def repo_git_diff(repo_name: str, path: str = "", staged: bool = False) -> dict:
    """Read-only: return git diff output, optionally scoped to one validated relative path or the staging area."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _git_diff_raw(repo_root, path=path, staged=staged)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=COMMIT_RANGE_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def inspect_commit_range(repo_name: str, base_commit: str, head_commit: str) -> dict:
    """Read-only: inspect an exact commit range using only two full commit hashes."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _inspect_commit_range(repo_root, base_commit, head_commit)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


def _get_runs_dir() -> "Path":
    return get_config().resolve_runs_dir()


@mcp.tool(output_schema=PREVIEW_PATCH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def preview_repo_patch(repo_name: str, operations: list[dict]) -> dict:
    """Read-only: validate patch operations and return a unified diff with a patch_id. Makes no changes."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_writer.preview_repo_patch(repo_root, operations, _get_runs_dir())
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=PREVIEW_PATCH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def preview_repo_file_creation(repo_name: str, path: str, content: str) -> dict:
    """Read-only: validate a repo file creation, persist an opaque local payload, and return a patch_id with preview diff."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_writer.preview_repo_file_creation(
        repo_root, path, content, _get_runs_dir()
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=PREVIEW_PATCH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def preview_repo_file_removal(repo_name: str, path: str, expected_sha256: str) -> dict:
    """Read-only: validate a repo file removal and return a patch_id with preview diff. Stores no source payload."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_writer.preview_repo_file_removal(
        repo_root, path, expected_sha256, _get_runs_dir()
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_patch_status(repo_name: str, patch_id: str) -> dict:
    """Read-only: return the durable lifecycle state for one managed patch."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_writer.get_patch_status(repo_root, patch_id, _get_runs_dir())
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def preview_managed_artifact_cleanup(repo_name: str, roots: list[str] = []) -> dict:
    """Preview cleanup of registered tool-owned scratch files only."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _preview_managed_artifact_cleanup(
        repo_root, _get_runs_dir(), roots or None
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def apply_managed_artifact_cleanup(repo_name: str, cleanup_id: str) -> dict:
    """Apply a hash-verified cleanup preview for registered tool-owned artifacts."""
    return _locked_repo_operation(
        repo_name,
        "apply_managed_artifact_cleanup",
        {"cleanup_id": cleanup_id},
        lambda repo_root: _apply_managed_artifact_cleanup(
            repo_root, _get_runs_dir(), cleanup_id
        ),
    )


@mcp.tool(output_schema=APPLY_PATCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
def apply_repo_patch(repo_name: str, operations: list[dict], patch_id: str) -> dict:
    """Write tool: apply a patch previously validated by preview_repo_patch. Rechecks all hashes before writing."""
    return _locked_repo_operation(
        repo_name,
        "apply_repo_patch",
        {"patch_id": patch_id, "operations": operations},
        lambda repo_root: _repo_writer.apply_repo_patch(
            repo_root, operations, patch_id, _get_runs_dir()
        ),
        finalize_commit=True,
    )


@mcp.tool(output_schema=APPLY_PATCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
def apply_previewed_repo_change(repo_name: str, patch_id: str) -> dict:
    """Write tool: apply a previewed repository change using only the opaque local preview bundle identified by patch_id."""
    return _locked_repo_operation(
        repo_name,
        "apply_previewed_repo_change",
        {"patch_id": patch_id},
        lambda repo_root: _repo_writer.apply_previewed_repo_change(
            repo_root, patch_id, _get_runs_dir()
        ),
        finalize_commit=True,
    )


@mcp.tool(output_schema=CREATE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
def create_repo_file(repo_name: str, path: str, content: str) -> dict:
    """Write tool: create a new file in the repository. Rejects existing files and applies all path/content safety checks."""
    return _locked_repo_operation(
        repo_name,
        "create_repo_file",
        {"path": path, "content_sha256": _repo_writer._sha256_text(content)},
        lambda repo_root: _repo_writer.create_repo_file(repo_root, path, content),
        finalize_commit=True,
    )


@mcp.tool(output_schema=DELETE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
def delete_repo_file(repo_name: str, path: str, expected_sha256: str) -> dict:
    """Write tool: delete a file after verifying its SHA-256. Saves rollback content."""
    return _locked_repo_operation(
        repo_name,
        "delete_repo_file",
        {"path": path, "expected_sha256": expected_sha256},
        lambda repo_root: _repo_writer.delete_repo_file(
            repo_root, path, expected_sha256, _get_runs_dir()
        ),
        finalize_commit=True,
    )


@mcp.tool(output_schema=MOVE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
def move_repo_file(
    repo_name: str,
    source_path: str,
    destination_path: str,
    expected_sha256: str,
) -> dict:
    """Write tool: move a file to a new repo-relative path after verifying its SHA-256. Saves rollback information."""
    return _locked_repo_operation(
        repo_name,
        "move_repo_file",
        {
            "source_path": source_path,
            "destination_path": destination_path,
            "expected_sha256": expected_sha256,
        },
        lambda repo_root: _repo_writer.move_repo_file(
            repo_root,
            source_path,
            destination_path,
            expected_sha256,
            _get_runs_dir(),
        ),
        finalize_commit=True,
    )


@mcp.tool(output_schema=REVERT_PATCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
def revert_managed_patch(repo_name: str, patch_id: str) -> dict:
    """Write tool: revert a previously applied managed patch using saved rollback content. Never uses git reset."""
    return _locked_repo_operation(
        repo_name,
        "revert_managed_patch",
        {"patch_id": patch_id},
        lambda repo_root: _repo_writer.revert_managed_patch(
            repo_root, patch_id, _get_runs_dir()
        ),
        finalize_commit=True,
    )


@mcp.tool(output_schema=RUN_COMMAND_OUTPUT, annotations=WRITE_ANNOTATIONS)
def run_project_command(repo_name: str, command_id: str) -> dict:
    """Run one allowlisted synchronous command under the repository operation lock."""
    config = get_config()
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    _, repo_config = resolve_repo_config(config, canonical_name)
    repo_profiles = list(repo_config.command_profiles or [])
    profile = resolve_command_profile(command_id, repo_profiles)
    if profile.async_only:
        result = {
            "ok": False,
            "repo_name": canonical_name,
            "command_id": command_id,
            "argv": list(profile.argv),
            "exit_code": 2,
            "timed_out": False,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "status": "async_required",
            "async_required": True,
            "error": (
                f"Command '{command_id}' is configured for durable async "
                "execution. Use start_project_command_async."
            ),
        }
        if requested_name != canonical_name:
            result["requested_repo_name"] = requested_name
        return result

    def run_profile_with_attribution(root: Path) -> dict[str, Any]:
        dirty_before = set(_changed_files(root))
        result = dict(run_command_profile(profile, root))
        dirty_after = _changed_files(root)
        result["changed_files"] = [
            path for path in dirty_after if path not in dirty_before
        ]
        return result

    return _locked_repo_operation(
        repo_name,
        "run_project_command",
        {"command_id": command_id},
        run_profile_with_attribution,
        finalize_commit=profile.writes_files,
    )


@mcp.tool(output_schema=GIT_LOG_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def git_log(repo_name: str, limit: int = 20, path: str = "") -> dict:
    """Read-only: return structured git log entries, optionally scoped to a file path."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.git_log(repo_root, limit=limit, path=path)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=READ_REPO_FILES_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def read_repo_files(repo_name: str, requests: list[dict]) -> dict:
    """Read-only: read up to 20 files in one call. Each request has path, start_line, end_line."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.read_repo_files(repo_root, requests)
    result["repo_name"] = canonical_name
    for item in result.get("results", []):
        item["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@mcp.tool(output_schema=CREATE_BRANCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
def create_git_branch(repo_name: str, branch_name: str) -> dict:
    """Write tool: create a new local git branch. Rejects protected names and existing branches."""
    from .repo_writer import (
        _PROTECTED_BRANCHES,
        _PROTECTED_BRANCH_PREFIXES,
        _BRANCH_NAME_RE,
    )

    config = get_config()
    canonical_name, repo_root, requested_name = _repo_context(repo_name)

    if not branch_name or not _BRANCH_NAME_RE.match(branch_name):
        return {
            "ok": False,
            "repo_name": repo_name,
            "branch_name": branch_name,
            "error": f"Invalid branch name: {branch_name!r}",
        }
    lower = branch_name.lower()
    if lower in _PROTECTED_BRANCHES:
        return {
            "ok": False,
            "repo_name": repo_name,
            "branch_name": branch_name,
            "error": f"Branch name is protected: {branch_name!r}",
        }
    for prefix in _PROTECTED_BRANCH_PREFIXES:
        if lower.startswith(prefix):
            return {
                "ok": False,
                "repo_name": repo_name,
                "branch_name": branch_name,
                "error": f"Branch name matches protected prefix '{prefix}': {branch_name!r}",
            }
    from .git_tools import git_branch_list

    existing = git_branch_list(repo_root)
    if branch_name in existing:
        return {
            "ok": False,
            "repo_name": repo_name,
            "branch_name": branch_name,
            "error": f"Branch already exists: {branch_name!r}",
        }
    with repository_operation_lock(
        config.resolve_runs_dir(),
        repo_name=canonical_name,
        tool="create_git_branch",
        normalized_input={"branch_name": branch_name},
    ):
        result = _git_create_branch(repo_root, branch_name)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CodexBridge MCP server.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument(
        "--transport",
        choices=["http", "streamable-http", "stdio", "sse"],
        default="http",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run_server(args: argparse.Namespace) -> None:
    config_path = Path(args.config).resolve()
    set_config(load_config(config_path), config_path)
    try:
        get_job_manager().reconcile_startup()
    except Exception:
        pass
    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return
    mcp.run(transport=args.transport, host=args.host, port=args.port, path=args.path)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    run_server(args)


if __name__ == "__main__":
    main()
