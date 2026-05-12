from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from fastmcp import FastMCP

from .config import AppConfig, load_config, resolve_repo
from .git_tools import commit_selected_files as commit_files
from .git_tools import diff_stat, git_status, inspect_status
from .job_manager import JobManager
from .runner import CodexRunner, latest_run_result as latest_artifact_result
from .self_check import run_self_check
from .supervisor_service import SupervisorService


mcp = FastMCP("CodexBridge")
_config: AppConfig | None = None
_config_path: Path | None = None
READ_ONLY_ANNOTATIONS = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
WRITE_ANNOTATIONS = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
CODEX_WRITE_ANNOTATIONS = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}
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
        "runs": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "result": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "error": {"type": "string"},
    },
}
EVENT_LIST_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "events": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "notifications": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "result": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
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
        "changed_files": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "diff_stat": {},
        "recent_commits": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
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
        "tests": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
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
        "commit_sha": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "message": {"type": "string"},
        "error": {"type": "string"},
    },
}

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
    return inspect_status(repo_root)


@mcp.tool(output_schema=CODEX_PLAN_OUTPUT, annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True})
def codex_plan_task(repo_name: str, task: str, constraints: str = "") -> dict:
    """Read-only: ask Codex to inspect only and return a plan. Must not edit files."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return CodexRunner(config).plan_task(repo_name, repo_root, task, constraints)


@mcp.tool(output_schema=CODEX_IMPLEMENT_OUTPUT, annotations=CODEX_WRITE_ANNOTATIONS)
def codex_implement_task(repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]) -> dict:
    """Write tool: ask Codex to implement only the approved plan and avoid unrelated files."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return CodexRunner(config).implement_task(repo_name, repo_root, approved_plan, allowed_files, tests)


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
def commit_selected_files(repo_name: str, files: list[str], title: str, description: str = "") -> dict:
    """Write tool: stage and commit only the provided files. Never pushes."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return commit_files(repo_root, files, title, description)


@mcp.tool(output_schema=SELF_CHECK_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def run_local_self_check() -> dict:
    """Read-only: run local setup, test, git, and MCP transport readiness checks."""
    config = get_config()
    return run_self_check(config=config, config_path=get_config_path(), live_port=8765)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True})
def start_codex_plan_task_async(repo_name: str, task: str, constraints: str = "") -> dict:
    """Read-only async tool: queue a plan-only Codex job and return a durable run_id immediately."""
    return get_job_manager().start_plan(repo_name, task, constraints)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=CODEX_WRITE_ANNOTATIONS)
def start_codex_implement_task_async(repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]) -> dict:
    """Write async tool: queue an approved implementation Codex job and return a durable run_id immediately."""
    return get_job_manager().start_implementation(repo_name, approved_plan, allowed_files, tests)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_status(run_id: str) -> dict:
    """Read-only: return durable status metadata for a queued/running/completed async run."""
    return get_job_manager().get_status(run_id)


@mcp.tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_events(run_id: str, limit: int = 50) -> list[dict]:
    """Read-only: return recent timeline events for an async run."""
    return get_job_manager().get_events(run_id, limit)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_result(run_id: str) -> dict:
    """Read-only: return the final or current structured result for an async run."""
    return get_job_manager().get_result(run_id)


@mcp.tool(output_schema=RUN_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_runs(repo_name: str = "", status: str = "", limit: int = 20) -> list[dict]:
    """Read-only: list recent async runs with optional repo/status filters."""
    return get_job_manager().list_runs(repo_name=repo_name or None, status=status or None, limit=limit)


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
    return get_supervisor_service().start_supervised_recovery_task(repo_name, objective, task, constraints, source_run_id or None, autonomy_profile)


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_status(supervisor_id: str) -> dict:
    """Read-only: return enriched supervisor status."""
    return get_supervisor_service().get_status(supervisor_id)


@mcp.tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_events(supervisor_id: str, limit: int = 50) -> list[dict]:
    """Read-only: return ordered supervisor events."""
    return get_supervisor_service().get_events(supervisor_id, limit)


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
def get_supervisor_notifications(supervisor_id: str, delivery_status: str = "", limit: int = 50) -> list[dict]:
    """Read-only: return persisted supervisor notification rows."""
    return get_supervisor_service().get_notifications(supervisor_id, delivery_status or None, limit)


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_resume_prompt(supervisor_id: str) -> dict:
    """Read-only: return the canonical supervisor resume prompt if present."""
    return get_supervisor_service().get_resume_prompt(supervisor_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CodexBridge MCP server.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--transport", choices=["http", "streamable-http", "stdio", "sse"], default="http")
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
