from __future__ import annotations

import argparse
import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from typing import Sequence

from fastmcp import FastMCP

from .config import AppConfig, load_config, resolve_repo
from .git_tools import CommitMetadataError
from .git_tools import commit_selected_files as commit_files
from .git_tools import diff_stat, git_status, inspect_status
from .git_tools import git_diff as _git_diff_raw
from .git_tools import create_branch as _git_create_branch
from .job_manager import JobManager
from . import repo_reader as _repo_reader
from . import repo_writer as _repo_writer
from .command_profiles import resolve_command_profile, run_command_profile
from .runner import CodexRunner, latest_run_result as latest_artifact_result
from .self_check import run_self_check
from .supervisor_service import SupervisorService
from .local_agent.models import LocalModelStatus
from .local_agent.ollama_adapter import OllamaChatAdapter


mcp = FastMCP("CodexBridge")
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


@mcp.tool(output_schema=REPO_STATUS_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def inspect_repo_status(repo_name: str) -> dict:
    """Read-only: return git status, branch, recent commits, changed files, and diff stat."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = dict(inspect_status(repo_root))
    result["repo_name"] = repo_name
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


@mcp.tool(
    output_schema=CODEX_PLAN_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def codex_plan_task(repo_name: str, task: str, constraints: str = "") -> dict:
    """Read-only: ask Codex to inspect only and return a plan. Must not edit files."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return CodexRunner(config).plan_task(repo_name, repo_root, task, constraints)


@mcp.tool(output_schema=CODEX_IMPLEMENT_OUTPUT, annotations=CODEX_WRITE_ANNOTATIONS)
def codex_implement_task(
    repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]
) -> dict:
    """Write tool: ask Codex to implement only the approved plan and avoid unrelated files."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return CodexRunner(config).implement_task(
        repo_name, repo_root, approved_plan, allowed_files, tests
    )


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_latest_run_result(repo_name: str = "", tool: str = "") -> dict:
    """Read-only: return the most recent saved CodexBridge run result."""
    config = get_config()
    repo_name = repo_name or None
    tool = tool or None
    if repo_name or tool:
        return get_job_manager().latest_result(repo_name=repo_name, tool=tool)
    try:
        return get_job_manager().latest_result()
    except Exception:
        return latest_artifact_result(config.resolve_runs_dir())


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def git_diff_summary(repo_name: str) -> dict:
    """Read-only: return git status and diff stat for a whitelisted repo."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return {"git_status": git_status(repo_root), "diff_stat": diff_stat(repo_root)}


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
    repo_root = resolve_repo(config, repo_name)

    try:
        result = commit_files(
            repo_root,
            files,
            title,
            description,
        )
    except CommitMetadataError as exc:
        return {
            "ok": False,
            "repo_name": repo_name,
            "files_validated": exc.files_validated,
            "blocked_field": exc.field,
            "reason_code": exc.reason_code,
            "reason": exc.reason,
            "error": exc.reason,
        }

    result["repo_name"] = repo_name
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
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_reader.list_repo_files(
        repo_root, directory=directory, max_results=max_results
    )
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=READ_REPO_FILE_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def read_repo_file(
    repo_name: str, path: str, start_line: int = 1, end_line: int = 0
) -> dict:
    """Read-only: read a text file from a repository. Rejects binary files, caps output, and redacts secrets."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_reader.read_repo_file(
        repo_root, path, start_line=start_line, end_line=end_line
    )
    result["repo_name"] = repo_name
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
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_reader.search_repo_text(
        repo_root,
        query,
        directory=directory,
        max_results=max_results,
        case_sensitive=case_sensitive,
    )
    result["repo_name"] = repo_name
    return result


@mcp.tool(
    output_schema=RECENTLY_MODIFIED_FILES_OUTPUT, annotations=READ_ONLY_ANNOTATIONS
)
def get_recently_modified_files(repo_name: str, limit: int = 50) -> dict:
    """Read-only: list files sorted by filesystem mtime, newest first. Reflects unsaved changes immediately."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_reader.get_recently_modified_files(repo_root, limit=limit)
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=REPO_GIT_STATUS_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def repo_git_status(repo_name: str) -> dict:
    """Read-only: return raw git status --short --branch output for a whitelisted repository."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    status_text = git_status(repo_root)
    return {"ok": True, "repo_name": repo_name, "status": status_text, "error": ""}


@mcp.tool(output_schema=REPO_GIT_DIFF_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def repo_git_diff(repo_name: str, path: str = "", staged: bool = False) -> dict:
    """Read-only: return git diff output, optionally scoped to one validated relative path or the staging area."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _git_diff_raw(repo_root, path=path, staged=staged)
    result["repo_name"] = repo_name
    return result


def _get_runs_dir() -> "Path":
    return get_config().resolve_runs_dir()


@mcp.tool(output_schema=PREVIEW_PATCH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def preview_repo_patch(repo_name: str, operations: list[dict]) -> dict:
    """Read-only: validate patch operations and return a unified diff with a patch_id. Makes no changes."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_writer.preview_repo_patch(repo_root, operations, _get_runs_dir())
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=APPLY_PATCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
def apply_repo_patch(repo_name: str, operations: list[dict], patch_id: str) -> dict:
    """Write tool: apply a patch previously validated by preview_repo_patch. Rechecks all hashes before writing."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_writer.apply_repo_patch(
        repo_root, operations, patch_id, _get_runs_dir()
    )
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=CREATE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
def create_repo_file(repo_name: str, path: str, content: str) -> dict:
    """Write tool: create a new file in the repository. Rejects existing files and applies all path/content safety checks."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_writer.create_repo_file(repo_root, path, content)
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=DELETE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
def delete_repo_file(repo_name: str, path: str, expected_sha256: str) -> dict:
    """Write tool: delete a file after verifying its SHA-256. Saves rollback content."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_writer.delete_repo_file(
        repo_root, path, expected_sha256, _get_runs_dir()
    )
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=MOVE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
def move_repo_file(
    repo_name: str,
    source_path: str,
    destination_path: str,
    expected_sha256: str,
) -> dict:
    """Write tool: move a file to a new repo-relative path after verifying its SHA-256. Saves rollback information."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_writer.move_repo_file(
        repo_root, source_path, destination_path, expected_sha256, _get_runs_dir()
    )
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=REVERT_PATCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
def revert_managed_patch(repo_name: str, patch_id: str) -> dict:
    """Write tool: revert a previously applied managed patch using saved rollback content. Never uses git reset."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_writer.revert_managed_patch(repo_root, patch_id, _get_runs_dir())
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=RUN_COMMAND_OUTPUT, annotations=WRITE_ANNOTATIONS)
def run_project_command(repo_name: str, command_id: str) -> dict:
    """Write tool: run an allowlisted project command by command_id. Uses subprocess with shell=False."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    repo_profiles = list(config.repos[repo_name].command_profiles or [])
    profile = resolve_command_profile(command_id, repo_profiles)
    result = run_command_profile(profile, repo_root)
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=GIT_LOG_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def git_log(repo_name: str, limit: int = 20, path: str = "") -> dict:
    """Read-only: return structured git log entries, optionally scoped to a file path."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_reader.git_log(repo_root, limit=limit, path=path)
    result["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=READ_REPO_FILES_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def read_repo_files(repo_name: str, requests: list[dict]) -> dict:
    """Read-only: read up to 20 files in one call. Each request has path, start_line, end_line."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    result = _repo_reader.read_repo_files(repo_root, requests)
    result["repo_name"] = repo_name
    for item in result.get("results", []):
        item["repo_name"] = repo_name
    return result


@mcp.tool(output_schema=CREATE_BRANCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
def create_git_branch(repo_name: str, branch_name: str) -> dict:
    """Write tool: create a new local git branch. Rejects protected names and existing branches."""
    import re as _re
    from .repo_writer import (
        _PROTECTED_BRANCHES,
        _PROTECTED_BRANCH_PREFIXES,
        _BRANCH_NAME_RE,
    )

    config = get_config()
    repo_root = resolve_repo(config, repo_name)

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
    try:
        _git_create_branch(repo_root, branch_name)
    except ValueError as exc:
        return {
            "ok": False,
            "repo_name": repo_name,
            "branch_name": branch_name,
            "error": str(exc),
        }

    return {"ok": True, "repo_name": repo_name, "branch_name": branch_name, "error": ""}


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
