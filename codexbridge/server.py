from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from fastmcp import FastMCP

from .config import AppConfig, load_config, resolve_repo
from .git_tools import commit_selected_files as commit_files
from .git_tools import diff_stat, git_status, inspect_status
from .runner import CodexRunner, latest_run_result
from .self_check import run_self_check


mcp = FastMCP("CodexBridge")
_config: AppConfig | None = None
_config_path: Path | None = None

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


@mcp.tool()
def inspect_repo_status(repo_name: str) -> dict:
    """Read-only: return git status, branch, recent commits, changed files, and diff stat."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return inspect_status(repo_root)


@mcp.tool()
def codex_plan_task(repo_name: str, task: str, constraints: str = "") -> dict:
    """Read-only: ask Codex to inspect only and return a plan. Must not edit files."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return CodexRunner(config).plan_task(repo_name, repo_root, task, constraints)


@mcp.tool()
def codex_implement_task(repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]) -> dict:
    """Write tool: ask Codex to implement only the approved plan and avoid unrelated files."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return CodexRunner(config).implement_task(repo_name, repo_root, approved_plan, allowed_files, tests)


@mcp.tool()
def get_latest_run_result() -> dict:
    """Read-only: return the most recent saved CodexBridge run result."""
    config = get_config()
    return latest_run_result(config.resolve_runs_dir())


@mcp.tool()
def git_diff_summary(repo_name: str) -> dict:
    """Read-only: return git status and diff stat for a whitelisted repo."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return {"git_status": git_status(repo_root), "diff_stat": diff_stat(repo_root)}


@mcp.tool()
def commit_selected_files(repo_name: str, files: list[str], title: str, description: str = "") -> dict:
    """Write tool: stage and commit only the provided files. Never pushes."""
    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return commit_files(repo_root, files, title, description)


@mcp.tool()
def run_local_self_check() -> dict:
    """Read-only: run local setup, test, git, and MCP transport readiness checks."""
    config = get_config()
    return run_self_check(config=config, config_path=get_config_path(), live_port=8765)


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
    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return
    mcp.run(transport=args.transport, host=args.host, port=args.port, path=args.path)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    run_server(args)


if __name__ == "__main__":
    main()
