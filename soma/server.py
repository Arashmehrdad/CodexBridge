from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import inspect
import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Literal
from typing import Sequence

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult

from .capabilities import PATCH_OPERATION_SCHEMA, capability_metadata, schema_hash, server_build_hash
from .mcp_flat_input import FlatGatewayTool, flatten_request_input_schema
from .public_projection_contract import (
    NON_AUTHORITATIVE_NOTICE,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
    apply_compact_projection_envelope,
)
from .cf1_gateway_operation_inventory import (
    CF1_GATEWAY_OPERATION_INVENTORY_VERSION,
    operation_names_by_gateway,
)
from .cloudflare_tools import authorize_cloudflare_profile
from .cloudflare_tools import cloudflare_health as _cloudflare_health
from .cloudflare_tools import (
    list_cloudflare_capabilities as _list_cloudflare_capabilities,
)
from .cloudflare_tools import run_cloudflare_inspection as _run_cloudflare_inspection
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
from .git_tools import CommitMetadataError, CommitPolicyError
from .git_tools import commit_all_changes as _commit_all_changes
from .git_tools import commit_selected_files as commit_files
from .git_tools import dry_run_stage_manifest as _dry_run_stage_manifest
from .git_tools import diff_stat, git_head, git_status, inspect_status
from .git_tools import finalize_explicit_changes
from .git_tools import inspect_status_compact
from .git_tools import inspect_commit_range as _inspect_commit_range
from .git_tools import git_diff as _git_diff_raw
from .git_tools import git_diff_snapshot as _git_diff_snapshot
from .git_tools import create_branch as _git_create_branch
from .git_tools import stage_all as _stage_all
from .git_tools import unstage_all as _unstage_all
from .job_manager import JobManager
from .hermes_companion_client import build_companion_launch, start_companion_request
from .hermes_concurrency import HermesConcurrencyControls, ToolLimitRule
from .hermes_service_gateway import (
    HermesServiceGateway,
    build_supervisor_from_config,
)
from .run_store import RunStore
from .managed_artifacts import (
    apply_managed_artifact_cleanup as _apply_managed_artifact_cleanup,
    preview_managed_artifact_cleanup as _preview_managed_artifact_cleanup,
)
from .operation_locks import repository_operation_lock
from .project_scope import ProjectScopeError, ProjectScopeStore
from . import reconciliation_status
from . import repo_reader as _repo_reader
from . import repo_writer as _repo_writer
from .repo_wiki import mark_repo_wiki_stale
from .run_query_chunks import decode_run_reference
from .service_reload import (
    apply_reloaded_config,
    get_reload_status as _get_reload_status,
    register_active_config,
    reload_service as _reload_service,
    rollback_service as _rollback_service,
    validate_config_candidate as _validate_config_candidate,
)
from .self_check import run_self_check
from .supervisor_service import SupervisorService
from . import trading_lab_adapter
from .trading_lab_adapter import (
    ActionRequest as TradingActionRequest,
    ActionState,
    ActionType as TradingActionType,
    CapabilityRole as TradingCapabilityRole,
    COMPATIBILITY_READ_OPERATIONS,
    DEPRECATED_QUERY_NOTICE,
    DEPRECATED_QUERY_OPERATIONS,
    EXPOSURE_READ_OPERATIONS,
    ExecutionMode as TradingExecutionMode,
    SUPPORTED_SESSION_CALENDARS,
    SUPPORTED_TIMEFRAMES,
    resolve_calendar,
    resolve_timeframe,
    JOURNAL_QUERY_OPERATIONS,
    ModelApprovalDecision,
    MT5Provider,
    ResearchSource,
    SignalDecisionV2,
    SignalRejectedError,
    SignalSubmissionV2,
    redact_health,
)
from .ssh_commands import list_ssh_capabilities as _list_ssh_capabilities
from .ssh_commands import ssh_host_health as _ssh_host_health
from .ssh_credentials import probe_ssh_credential_source as _probe_ssh_credential_source
from .ssh_activation import (
    activation_status as _ssh_activation_status,
    reconcile_pending_ssh_activations as _reconcile_pending_ssh_activations,
)
from .ssh_capabilities import (
    capability_snapshot_projection as _capability_snapshot_projection,
    read_capability_snapshot as _read_ssh_capability_snapshot,
)
from .ssh_project_bindings import (
    list_ssh_project_bindings as _list_ssh_project_bindings,
)
from .ssh_profile_manager import (
    get_ssh_profile_change_status as _get_ssh_profile_change_status,
    preview_ssh_profile_change as _preview_ssh_profile_change,
)
from .ssh_tools import enrich_ssh_capabilities as _enrich_ssh_capabilities
from .ssh_tools import run_ssh_capability_snapshot as _run_ssh_capability_snapshot
from .ssh_tools import run_ssh_environment_probe as _run_ssh_environment_probe
from .ssh_tools import run_ssh_gpu_telemetry as _run_ssh_gpu_telemetry
from .ssh_tools import run_ssh_inspection as _run_ssh_inspection
from .ssh_tools import (
    run_ssh_project_binding_validation as _run_ssh_project_binding_validation,
)
from .local_agent.models import LocalModelStatus
from .local_agent.ollama_adapter import OllamaChatAdapter
from .tasks import TaskManager
from .workflows import WorkflowManager
from .gateway_models import (
    RepoApplyRequest,
    RepoCommitRequest,
    RepoPreviewRequest,
    RepoQueryRequest,
    RunStartRequest,
    RunQueryRequest,
    DockerActionRequest,
    DockerQueryRequest,
    CloudflareActionRequest,
    CloudflareQueryRequest,
    SSHActionRequest,
    SSHQueryRequest,
    SystemActionRequest,
    SystemQueryRequest,
    SSHInspectRequest,
    SupervisorActionRequest,
    SupervisorQueryRequest,
    TaskActionRequest,
    TaskQueryRequest,
    TradingActionSubmitRequest,
    TradingCompanionActionRequest,
    TradingQueryRequest,
    TradingRuntimeControlRequest,
    TradingSignalCancelRequest,
    TradingSignalGetRequest,
    TradingSignalListRequest,
    TradingSignalSubmitRequest,
    WorkflowActionRequest,
    WorkflowQueryRequest,
)


mcp = FastMCP("Soma")
_PROCESS_CAPABILITY_METADATA = capability_metadata(PATCH_OPERATION_SCHEMA)
_original_mcp_tool = mcp.tool


#: Advertised input schemas, captured as each public tool registers.
#:
#: Every accessor on the tool registry is async, so a response cannot ask
#: discovery what the live contract is without either driving an event loop from
#: inside one or paying a full two-pass discovery per call. Recording the schema
#: object at registration gives the same objects discovery serves, synchronously
#: and once. A test asserts this agrees with the discovery-derived
#: `public_schema_hash`, so the two can never drift apart unnoticed.
_PUBLIC_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {}
_PUBLIC_CONTRACT_HASH_CACHE: str = ""


def _record_public_input_schema(tool: Any) -> None:
    """Invalidate the memo when the advertised surface gains a tool.

    The schema itself is deliberately not captured here. FastMCP inlines
    ``$defs`` and dereferences the union branches when it *advertises* a tool,
    so neither ``tool.parameters`` nor a registration-time ``to_mcp_tool()``
    reproduces what a connector actually caches. Hashing either would yield an
    identity no client could reproduce -- authoritative-looking and wrong.
    """
    global _PUBLIC_CONTRACT_HASH_CACHE
    if getattr(tool, "name", ""):
        _PUBLIC_CONTRACT_HASH_CACHE = ""


def refresh_public_contract_hash() -> str:
    """Compute the effective public contract identity from served discovery.

    Called once at startup, after every tool has registered, so responses can
    stamp the identity synchronously without driving discovery per call. Safe
    to call again; it is idempotent for an unchanged surface.
    """
    global _PUBLIC_CONTRACT_HASH_CACHE
    try:
        from .knowledge_tools_integration import register_knowledge_tools

        register_knowledge_tools(mcp)
        tools = asyncio.run(mcp.list_tools())
    except Exception:
        # Never let identity computation break startup or a response: an absent
        # field is honest, a wrong one is not.
        return _PUBLIC_CONTRACT_HASH_CACHE
    _PUBLIC_INPUT_SCHEMAS.clear()
    for tool in tools:
        action = tool.to_mcp_tool().model_dump(mode="json")
        name = str(action.get("name", "") or "")
        served = action.get("inputSchema")
        if name and isinstance(served, dict):
            _PUBLIC_INPUT_SCHEMAS[name] = served
    _PUBLIC_CONTRACT_HASH_CACHE = _input_schema_hash_from_actions(
        [
            {"name": name, "inputSchema": schema}
            for name, schema in _PUBLIC_INPUT_SCHEMAS.items()
        ]
    )
    return _PUBLIC_CONTRACT_HASH_CACHE


def public_contract_hash() -> str:
    """Identity of the effective public input contract.

    Derived only from the advertised input schemas, so adding or changing a
    public operation moves it while an implementation-only edit does not. This
    is the field to compare when asking "did the contract change?"; the legacy
    `schema_hash` cannot answer that question -- see
    `docs/PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md`.

    Returns an empty string when discovery has not run yet and cannot be driven
    from the current context, and the field is then omitted rather than guessed.
    """
    if _PUBLIC_CONTRACT_HASH_CACHE:
        return _PUBLIC_CONTRACT_HASH_CACHE
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return refresh_public_contract_hash()
    return ""


def _with_process_capability_metadata(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    enriched = dict(result)
    for key, value in _PROCESS_CAPABILITY_METADATA.items():
        enriched.setdefault(key, value)
    # Additive and never a redefinition: `schema_hash` keeps the value and
    # meaning it has always had, and this is the field that actually tracks the
    # public contract.
    contract = public_contract_hash()
    if contract:
        enriched.setdefault("public_schema_hash", contract)
    return enriched


def _mcp_content_payload(result: dict[str, Any]) -> str:
    """Serialize the compact public projection into a text content block.

    MCP spec 2025-06-18 (Server/Tools, Structured Content) requires a tool that
    returns structured content to *also* serialize that same JSON into a text
    content block for backwards compatibility. ChatGPT reads
    ``structuredContent``; Claude, LangChain's MCP adapters, Agent Zero, and
    most other clients read ``content[].text``. Both channels therefore carry
    the same information.

    The payload here is the identical dict that populates ``structuredContent``
    (already the view-specific compact/full/legacy projection produced upstream,
    including its byte-budget trimming), so no projection logic is duplicated or
    re-expanded here. It is rendered with the canonical compact separators used
    by the CF1 byte-budget accounting so the serialized text the model actually
    consumes never exceeds what ``response_budget_bytes`` bounded.
    """
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _account_text_block_bytes(result: dict[str, Any]) -> dict[str, Any]:
    """Refresh ``response_bytes`` to the size of the serialized text block.

    Upstream projections estimate ``response_bytes`` from the pre-transport
    projection alone. Now that ``content[].text`` is the channel the model
    consumes, the accounting must reflect that serialized block, including the
    fixed capability-metadata envelope the transport layer merges in. Only
    results that already report ``response_bytes`` are touched; the value is
    resolved to a fixed point because the recorded integer's own width feeds
    back into the serialized length.
    """
    if not isinstance(result.get("response_bytes"), int) or isinstance(
        result.get("response_bytes"), bool
    ):
        return result
    updated = dict(result)
    for _ in range(4):
        size = len(_mcp_content_payload(updated).encode("utf-8"))
        if size == updated["response_bytes"]:
            break
        updated["response_bytes"] = size
    return updated


def _mcp_transport_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    accounted = _account_text_block_bytes(result)
    return ToolResult(
        content=_mcp_content_payload(accounted),
        structured_content=accounted,
    )


def _register_public_tool(function, tool_args: tuple, tool_kwargs: dict) -> None:
    """Register one public tool, flattening a ``request`` envelope if present.

    FastMCP derives ``inputSchema`` from the function signature, so every
    gateway declared as ``tool(request: Union)`` advertised a mandatory outer
    ``request`` object. Registering a :class:`FlatGatewayTool` and replacing its
    advertised schema hoists the discriminated union to the argument root while
    the wrapped signature — and therefore FastMCP's own argument validation
    against the operation models — stays exactly as it was.

    Tools that are already flat (``cancel_run``) yield no flattened schema and
    fall back to unmodified FastMCP registration.
    """
    flat_tool = None
    if not tool_args:
        candidate = FlatGatewayTool.from_function(function, **tool_kwargs)
        flat_schema = flatten_request_input_schema(candidate.parameters)
        if flat_schema is not None:
            candidate.parameters = flat_schema
            flat_tool = candidate
    if flat_tool is None:
        registered = _original_mcp_tool(*tool_args, **tool_kwargs)(function)
        _record_public_input_schema(registered)
        return
    mcp.add_tool(flat_tool)
    _record_public_input_schema(flat_tool)


def _tool_with_capability_metadata(*tool_args, **tool_kwargs):
    def decorate(function):
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def direct_async_wrapped(*args, **kwargs):
                return _with_process_capability_metadata(
                    await function(*args, **kwargs)
                )

            @wraps(function)
            async def mcp_async_wrapped(*args, **kwargs):
                return _mcp_transport_result(
                    await direct_async_wrapped(*args, **kwargs)
                )

            _register_public_tool(mcp_async_wrapped, tool_args, tool_kwargs)
            return direct_async_wrapped

        @wraps(function)
        def direct_sync_wrapped(*args, **kwargs):
            return _with_process_capability_metadata(function(*args, **kwargs))

        @wraps(function)
        def mcp_sync_wrapped(*args, **kwargs):
            return _mcp_transport_result(direct_sync_wrapped(*args, **kwargs))

        _register_public_tool(mcp_sync_wrapped, tool_args, tool_kwargs)
        return direct_sync_wrapped

    return decorate


def _internal_tool(*tool_args, **tool_kwargs):
    # Preserve direct Python compatibility without publishing an MCP action.
    del tool_args, tool_kwargs

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

            return async_wrapped

        @wraps(function)
        def sync_wrapped(*args, **kwargs):
            result = function(*args, **kwargs)
            if isinstance(result, dict):
                result = dict(result)
                for key, value in _PROCESS_CAPABILITY_METADATA.items():
                    result.setdefault(key, value)
            return result

        return sync_wrapped

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
WORKFLOW_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "ok": {"type": "boolean"},
        "workflow_id": {"type": "string"},
        "repo_name": {"type": "string"},
        "status": {"type": "string"},
        "terminal_status": {"type": "string"},
        "steps": {
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
        "head_commit": {"type": "string"},
        "git_status": {"type": "string"},
        "staged": {"type": "array", "items": {"type": "string"}},
        "unstaged": {"type": "array", "items": {"type": "string"}},
        "untracked": {"type": "array", "items": {"type": "string"}},
        "deleted": {"type": "array", "items": {"type": "string"}},
        "renamed": {"type": "array", "items": {"type": "string"}},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "total_changed_file_count": {"type": "integer"},
        "diff_stat": {"type": "string"},
        "recent_commits": {"type": "array", "items": {"type": "string"}},
        "manifest": {"type": "object", "additionalProperties": True},
        "generated_at": {"type": "number"},
        "duration_ms": {"type": "number"},
        "fresh": {"type": "boolean"},
        "source": {"type": "string"},
        "truncated": {"type": "boolean"},
        "recommended_action": {"type": "string"},
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
        "file_path": {"type": "string"},
        "case_sensitive": {"type": "boolean"},
        "file_patterns": {"type": "array", "items": {"type": "string"}},
        "budget_ms": {"type": "integer"},
        "status": {"type": "string"},
        "fresh": {"type": "boolean"},
        "partial_results": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "files_examined": {"type": "integer"},
        "duration_ms": {"type": "number"},
        "recommended_action": {"type": "string"},
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
        "partial": {"type": "boolean"},
        "timeout": {"type": "boolean"},
        "has_more": {"type": "boolean"},
        "next_cursor": {"type": "string"},
        "snapshot_sha256": {"type": "string"},
        "response_bytes": {"type": "integer"},
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
        "fresh": {"type": "boolean"},
        "source": {"type": "string"},
        "generated_at": {"type": "number"},
        "duration_ms": {"type": "number"},
        "recommended_action": {"type": "string"},
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
        "view": {"type": "string"},
        "snapshot_id": {"type": "string"},
        "expected_snapshot_id": {"type": "string"},
        "hunk_id": {"type": "string"},
        "hunk": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "hunks": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "file_count": {"type": "integer"},
        "hunk_count": {"type": "integer"},
        "additions": {"type": "integer"},
        "deletions": {"type": "integer"},
        "full_retrieval": {"type": "string"},
        "response_bytes": {"type": "integer"},
        "fresh": {"type": "boolean"},
        "status": {"type": "string"},
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
    register_active_config(config, config_path)


def get_config() -> AppConfig:
    if _config is None:
        raise RuntimeError("Soma config has not been loaded")
    return _config


def get_config_path() -> Path | None:
    return _config_path


def get_job_manager() -> JobManager:
    return JobManager(get_config(), get_config_path())


def get_workflow_manager() -> WorkflowManager:
    return WorkflowManager(get_config(), get_config_path())


def get_task_manager() -> TaskManager:
    return TaskManager(get_config(), get_config_path())


def get_project_scope_store() -> ProjectScopeStore:
    """Return the non-migrating ProjectScope adapter for the current main store."""
    return ProjectScopeStore(get_config().resolve_runs_dir())


_hermes_service_gateway: HermesServiceGateway | None = None
_hermes_service_gateway_lock = threading.Lock()


def get_hermes_service_gateway() -> HermesServiceGateway:
    """Long-lived shared-service gateway; workers outlive individual calls."""
    global _hermes_service_gateway
    with _hermes_service_gateway_lock:
        if _hermes_service_gateway is None:
            _hermes_service_gateway = _build_hermes_service_gateway()
        return _hermes_service_gateway


def _build_hermes_service_gateway() -> HermesServiceGateway:
    config = get_config()
    service_config = config.hermes_service
    fallback_starter = None
    if (
        service_config.fallback_enabled
        and service_config.fallback_repo_name
        and service_config.checkout
    ):

        def fallback_starter(
            *,
            operation: str,
            payload: dict[str, Any],
            expected_registry_generation: int,
            expected_schema_hash: str,
        ) -> dict:
            launch = build_companion_launch(
                profile_id=service_config.fallback_profile_id,
                checkout=service_config.checkout,
                operation=operation,
                payload=payload,
                expected_registry_generation=expected_registry_generation,
                expected_schema_hash=expected_schema_hash,
                hermes_home=service_config.hermes_home or None,
            )
            return start_companion_request(
                get_job_manager(),
                service_config.fallback_repo_name,
                launch,
            )

    return HermesServiceGateway(
        run_store=RunStore(config.resolve_runs_dir()),
        runs_dir=config.resolve_runs_dir(),
        supervisor_factory=lambda: build_supervisor_from_config(config),
        fallback_starter=fallback_starter,
        concurrency=HermesConcurrencyControls.from_rules(
            tuple(
                ToolLimitRule(
                    pattern=limit.pattern,
                    max_concurrent=limit.max_concurrent,
                    min_interval_seconds=limit.min_interval_seconds,
                )
                for limit in service_config.tool_limits
            )
        ),
    )


def get_supervisor_service() -> SupervisorService:
    return SupervisorService(get_config(), get_config_path())


def _trading_json(value: Any) -> Any:
    if is_dataclass(value):
        return _trading_json(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _trading_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_trading_json(item) for item in value]
    return value


def _configured_mt5_provider() -> MT5Provider:
    return trading_lab_adapter.configured_mt5_provider(get_config())


def _trading_services():
    """The Trading Lab domain services for the active configuration."""
    return trading_lab_adapter.services(get_config())


def _repo_context(repo_name: str) -> tuple[str, Path, str]:
    canonical_name, repo_root, _ = resolve_repo_identity(get_config(), repo_name)
    return canonical_name, repo_root, repo_name


def _with_capability_metadata(result: dict[str, Any]) -> dict[str, Any]:
    result.update(_PROCESS_CAPABILITY_METADATA)
    return result


def _mark_wiki_stale_safely(
    repo_root: Path, repo_name: str, reason: str
) -> dict[str, Any]:
    try:
        return mark_repo_wiki_stale(repo_root, repo_name, reason=reason)
    except Exception as exc:
        return {"ok": False, "stale": None, "error": str(exc)}


def _operation_identity_metadata(
    *,
    actions: list[dict[str, Any]] | None = None,
    live_input_schema_hash: str = "",
) -> dict[str, Any]:
    """Build identities from the actual effective public input schemas."""
    operation_inventory = {
        gateway: sorted(names) for gateway, names in operation_names_by_gateway().items()
    }
    operation_inventory_hash = schema_hash(operation_inventory)
    public_schema_hash = live_input_schema_hash or _input_schema_hash_from_actions(
        actions or []
    )
    discovery_cache_generation = schema_hash(
        {
            "inventory_version": CF1_GATEWAY_OPERATION_INVENTORY_VERSION,
            "operation_inventory_hash": operation_inventory_hash,
            "public_schema_hash": public_schema_hash,
            "server_build_hash": _PROCESS_CAPABILITY_METADATA["server_build_hash"],
            "capability_epoch": _PROCESS_CAPABILITY_METADATA["capability_epoch"],
        }
    )
    return {
        "operation_inventory_hash": operation_inventory_hash,
        "operation_inventory_gateway_count": len(operation_inventory),
        "public_schema_hash": public_schema_hash,
        "runtime_input_schema_hash": public_schema_hash,
        "discovery_cache_generation": discovery_cache_generation,
        "operation_inventory": operation_inventory,
    }


def _input_schema_hash_from_actions(actions: list[dict[str, Any]]) -> str:
    """Hash the live gateway input schemas in deterministic name order."""
    schemas = {
        str(action.get("name", "")): action.get("inputSchema", {})
        for action in actions
        if str(action.get("name", ""))
    }
    return schema_hash(schemas)


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
            repo_policy = get_config().repos[canonical_name]
            commit_data = finalize_explicit_changes(
                repo_root,
                result.get("changed_files") or [],
                tool_name=tool,
                require_commit_report=repo_policy.require_commit_report,
            )
            result = dict(result)
            result.update(commit_data)
            if commit_data["commit_attempted"] and commit_data["commit_error"]:
                result["ok"] = False
                result["status"] = "commit_failed"
                result["error"] = commit_data["commit_error"]
        if result.get("ok") and result.get("changed_files"):
            result["wiki_freshness"] = _mark_wiki_stale_safely(
                repo_root, canonical_name, tool
            )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
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
    result.update(
        {
            key: value
            for key, value in _operation_identity_metadata(actions=actions).items()
            if key != "operation_inventory"
        }
    )
    result["live_input_schema_hash"] = result["public_schema_hash"]
    return _with_capability_metadata(result)


def _list_capabilities_sync() -> dict[str, Any]:
    """Resolve live tool discovery for the synchronous system gateway."""
    try:
        tools = asyncio.run(mcp.list_tools())
    except RuntimeError as exc:
        return {
            "ok": False,
            "actions": [],
            "action_names": [],
            "error": f"live capability discovery unavailable: {exc}",
            **_PROCESS_CAPABILITY_METADATA,
        }
    actions = [tool.to_mcp_tool().model_dump(mode="json") for tool in tools]
    result = {
            "ok": True,
            "actions": actions,
            "action_names": sorted(str(action.get("name", "")) for action in actions),
            "patch_operation_schema": PATCH_OPERATION_SCHEMA,
            "error": "",
        }
    result.update(
        {
            key: value
            for key, value in _operation_identity_metadata(actions=actions).items()
            if key != "operation_inventory"
        }
    )
    result["live_input_schema_hash"] = result["public_schema_hash"]
    return _with_capability_metadata(result)


def _system_capabilities_result() -> dict[str, Any]:
    """Preserve synchronous compatibility while resolving the real async gateway."""
    discovered = list_capabilities()
    if isinstance(discovered, dict):
        return discovered
    if inspect.iscoroutine(discovered):
        discovered.close()
    return _list_capabilities_sync()


def _live_operation_schema_hashes_sync() -> tuple[dict[str, str], str, bool, str]:
    """Return live per-operation identities and two-pass discovery stability."""
    try:
        from .knowledge_tools_integration import register_knowledge_tools

        register_knowledge_tools(mcp)
        first_tools = asyncio.run(mcp.list_tools())
        second_tools = asyncio.run(mcp.list_tools())
    except Exception as exc:
        return {}, f"live operation-schema discovery unavailable: {exc}", False, ""

    def _hashes(tools: list[Any]) -> tuple[dict[str, str], list[str]]:
        hashes: dict[str, str] = {}
        collisions: set[str] = set()

        def _record(tool_name: str, operation_name: str, current_schema: dict[str, Any]) -> None:
            qualified_name = f"{tool_name}.{operation_name}"
            current_hash = schema_hash(current_schema)
            previous_hash = hashes.get(qualified_name)
            if previous_hash is not None and previous_hash != current_hash:
                collisions.add(qualified_name)
                return
            hashes[qualified_name] = current_hash

        for tool in tools:
            action = tool.to_mcp_tool().model_dump(mode="json")
            tool_name = str(action.get("name", "")).strip()
            root = action.get("inputSchema")
            if not tool_name or not isinstance(root, dict):
                continue
            # Public gateways now advertise the discriminated union at the
            # argument root; the legacy ``request`` envelope is still resolved
            # so a non-flattened tool keeps its per-operation identities.
            variants = root.get("oneOf")
            if not isinstance(variants, list):
                request_schema = (root.get("properties") or {}).get("request")
                if isinstance(request_schema, dict):
                    variants = request_schema.get("oneOf")
                    if not isinstance(variants, list):
                        variants = [request_schema]
                elif isinstance(root.get("properties"), dict):
                    variants = [root]
                else:
                    _record(tool_name, "invoke", root)
                    continue
            for variant in variants:
                current = variant
                seen: set[str] = set()
                while isinstance(current, dict) and "$ref" in current:
                    reference = str(current["$ref"])
                    if reference in seen or not reference.startswith("#/"):
                        break
                    seen.add(reference)
                    resolved: Any = root
                    for part in reference[2:].split("/"):
                        resolved = resolved[part.replace("~1", "/").replace("~0", "~")]
                    current = resolved
                if not isinstance(current, dict):
                    continue
                operation_names: list[str] = []
                properties = current.get("properties") or {}
                for discriminator_name in ("operation", "action"):
                    discriminator = properties.get(discriminator_name)
                    if not isinstance(discriminator, dict):
                        continue
                    if "const" in discriminator:
                        operation_names.append(str(discriminator["const"]))
                    values = discriminator.get("enum")
                    if isinstance(values, list):
                        operation_names.extend(str(value) for value in values)
                for operation_name in operation_names or ["invoke"]:
                    _record(tool_name, operation_name, current)
        return hashes, sorted(collisions)

    first_hashes, first_collisions = _hashes(first_tools)
    second_hashes, second_collisions = _hashes(second_tools)
    first_actions = [tool.to_mcp_tool().model_dump(mode="json") for tool in first_tools]
    second_actions = [tool.to_mcp_tool().model_dump(mode="json") for tool in second_tools]
    first_input_schema_hash = _input_schema_hash_from_actions(first_actions)
    second_input_schema_hash = _input_schema_hash_from_actions(second_actions)
    collisions = sorted(set(first_collisions) | set(second_collisions))
    if collisions:
        return (
            second_hashes,
            f"live operation-schema collisions: {', '.join(collisions)}",
            False,
            second_input_schema_hash,
        )
    return (
        second_hashes,
        "",
        first_hashes == second_hashes and first_input_schema_hash == second_input_schema_hash,
        second_input_schema_hash,
    )


@_internal_tool(output_schema=REPO_STATUS_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def inspect_repo_status(
    repo_name: str,
    view: str = "full",
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: return git status, branch, recent commits, changed files, and diff stat."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    try:
        result = dict(inspect_status(repo_root))
    except Exception as exc:
        result = {
            "ok": False,
            "status": "failed",
            "fresh": False,
            "source": "live_git",
            "generated_at": time.time(),
            "duration_ms": 0.0,
            "error": str(exc),
            "recommended_action": "Retry the live repository-status check; do not use a cached snapshot.",
        }
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    result.setdefault("ok", False)
    result.setdefault("status", "unavailable")
    result.setdefault("fresh", False)
    result.setdefault("source", "live_git")
    result.setdefault("head_commit", "")
    result.setdefault("generated_at", time.time())
    result.setdefault("duration_ms", 0.0)
    result.setdefault("truncated", False)
    result.setdefault(
        "recommended_action",
        "Retry the live repository-status check; do not use a cached snapshot.",
    )
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
    for key in ("staged", "unstaged", "untracked", "deleted", "renamed"):
        value = result.get(key)
        result[key] = [str(item) for item in value] if isinstance(value, list) else []
    result["total_changed_file_count"] = int(
        result.get("total_changed_file_count") or len(result["changed_files"])
    )
    if view == "full":
        return result
    compact = {
        key: result.get(key)
        for key in (
            "ok",
            "repo_name",
            "status",
            "fresh",
            "source",
            "head_commit",
            "generated_at",
            "duration_ms",
            "total_changed_file_count",
            "changed_files",
            "recent_commits",
            "diff_stat",
            "git_status",
            "error",
            "recommended_action",
        )
    }
    compact["changed_files"] = list(compact.get("changed_files") or [])
    compact["recent_commits"] = list(compact.get("recent_commits") or [])
    compact["truncated"] = False
    compact["has_more"] = False
    compact["response_budget_bytes"] = response_budget_bytes
    if "requested_repo_name" in result:
        compact["requested_repo_name"] = result["requested_repo_name"]
    while len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        if compact["changed_files"]:
            compact["changed_files"].pop()
        elif compact["recent_commits"]:
            compact["recent_commits"].pop()
        else:
            compact["git_status"] = ""
            compact["diff_stat"] = ""
            compact["recommended_action"] = ""
        compact["truncated"] = True
        compact["has_more"] = True
        if not compact["changed_files"] and not compact["recent_commits"] and not compact["git_status"] and not compact["diff_stat"] and not compact["recommended_action"]:
            break
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact
    return result


@_internal_tool(output_schema=REPO_STATUS_COMPACT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def inspect_repo_status_compact(
    repo_name: str,
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: return a compact repository status with tool-owned changes summarized."""
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    try:
        result = dict(inspect_status_compact(repo_root))
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "status": "timed_out",
            "fresh": False,
            "source": "live_git",
            "error": str(exc),
            "recommended_action": "Retry the live repository-status check; do not use a cached snapshot.",
        }
    except Exception as exc:
        result = {
            "ok": False,
            "status": "failed",
            "fresh": False,
            "source": "live_git",
            "error": str(exc),
            "recommended_action": "Retry the live repository-status check; do not use a cached snapshot.",
        }
    result.pop("git_status", None)
    result.pop("manifest", None)
    result.pop("tool_owned", None)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    result.setdefault("ok", False)
    result.setdefault("fresh", True if result["ok"] else False)
    result.setdefault("source", "live_git")
    result["recent_commits"] = _normalize_text_lines(result.get("recent_commits"))
    diff_stat = result.get("diff_stat")
    result["diff_stat"] = diff_stat if isinstance(diff_stat, str) else ""
    result["view"] = "compact"
    result["projection_version"] = PUBLIC_PROJECTION_SCHEMA_VERSION
    result["non_authoritative"] = True
    result["notice"] = NON_AUTHORITATIVE_NOTICE
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        if result["changed_files"]:
            result["changed_files"].pop()
        elif result["recent_commits"]:
            result["recent_commits"].pop()
        elif result["diff_stat"]:
            result["diff_stat"] = ""
        elif result.get("recommended_action"):
            result["recommended_action"] = ""
        else:
            break
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


def _latest_artifact_result(runs_dir: Path) -> dict:
    """Return the newest saved run result artifact from the runs directory."""
    candidates = sorted(
        runs_dir.glob("*/result.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No run results found")
    return json.loads(candidates[0].read_text(encoding="utf-8"))


@_internal_tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_latest_run_result(repo_name: str = "", tool: str = "") -> dict:
    """Read-only: return the most recent saved Soma run result."""
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
        return _latest_artifact_result(config.resolve_runs_dir())


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
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


@_internal_tool(output_schema=COMMIT_OUTPUT, annotations=WRITE_ANNOTATIONS)
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
            repo_policy = config.repos[canonical_name]
            result = commit_files(
                repo_root,
                files,
                title,
                description,
                refuse_unrelated_staged_files=repo_policy.refuse_unrelated_staged_files,
                require_commit_report=repo_policy.require_commit_report,
            )
    except (CommitMetadataError, CommitPolicyError) as exc:
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
    if result.get("ok") and result.get("commit_hash"):
        result["wiki_freshness"] = _mark_wiki_stale_safely(
            repo_root, canonical_name, "commit_selected_files"
        )
    return result


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def dry_run_stage_manifest(repo_name: str, include_ignored: bool = False) -> dict:
    """Read-only: preview which files would be staged without changing git state."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _dry_run_stage_manifest(repo_root, include_ignored=include_ignored)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
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
    if result.get("ok") and result.get("changed_files"):
        result["wiki_freshness"] = _mark_wiki_stale_safely(
            repo_root, canonical_name, "stage_all"
        )
    return result


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@_internal_tool(output_schema=COMMIT_OUTPUT, annotations=WRITE_ANNOTATIONS)
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
            repo_policy = config.repos[canonical_name]
            result = _commit_all_changes(
                repo_root,
                title,
                description,
                commit_mode=repo_policy.commit_mode,
                require_commit_report=repo_policy.require_commit_report,
            )
    except (CommitMetadataError, CommitPolicyError) as exc:
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
    if result.get("ok") and result.get("commit_hash"):
        result["wiki_freshness"] = _mark_wiki_stale_safely(
            repo_root, canonical_name, "commit_all_changes"
        )
    return result


@_internal_tool(output_schema=SELF_CHECK_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def run_local_self_check() -> dict:
    """Read-only: run lightweight in-process Soma readiness checks."""
    config = get_config()
    return run_self_check(config=config, config_path=get_config_path())


def _bounded_self_check_response(result: dict[str, Any], response_budget_bytes: int) -> dict:
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    checks: dict[str, Any] = {}
    for name, check in (result.get("checks") or {}).items():
        if not isinstance(check, dict):
            checks[str(name)] = {"ok": False, "error": "invalid check payload"}
            continue
        compact = {"ok": bool(check.get("ok", False))}
        for key in ("status", "error", "warning", "exit_code", "duration_seconds"):
            if key in check and key != "error":
                compact[key] = check[key]
        if check.get("error"):
            compact["error"] = str(check["error"])[:512]
        checks[str(name)] = compact
    response = {
        "ok": bool(result.get("ok", False)),
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "checks": checks,
        "check_count": len(checks),
        "truncated": False,
        "has_more": False,
        "response_budget_bytes": response_budget_bytes,
    }
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        if response["checks"]:
            response["checks"].pop(next(reversed(response["checks"])))
            response["truncated"] = True
            response["has_more"] = True
            continue
        break
    response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    return response


def _bounded_system_query_response(result: dict[str, Any], response_budget_bytes: int) -> dict:
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact: dict[str, Any] = {
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
    }
    truncated = False
    for key, value in result.items():
        if isinstance(value, (bool, int, float)) or value is None:
            compact[key] = value
        elif isinstance(value, str):
            text = value[:512]
            compact[key] = text
            truncated = truncated or len(text) != len(value)
        elif isinstance(value, list):
            if key == "mismatches":
                compact[key] = [str(item)[:128] for item in value[:20]]
                truncated = truncated or len(compact[key]) != len(value)
            else:
                compact[f"{key}_count"] = len(value)
                truncated = True
        elif isinstance(value, dict):
            nested: dict[str, Any] = {}
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, (bool, int, float)) or nested_value is None:
                    nested[nested_key] = nested_value
                elif isinstance(nested_value, str):
                    nested[nested_key] = nested_value[:256]
                    truncated = truncated or len(nested[nested_key]) != len(nested_value)
            compact[key] = nested
            if len(nested) != len(value):
                compact[f"{key}_count"] = len(value)
                truncated = True
        else:
            compact[key] = str(value)[:256]
            truncated = True
    compact["truncated"] = truncated
    compact["has_more"] = truncated
    compact["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        candidates = [
            key
            for key in compact
            if key not in {"truncated", "has_more", "response_budget_bytes", "response_bytes", "ok"}
        ]
        if not candidates:
            break
        compact.pop(max(candidates, key=lambda key: len(json.dumps(compact[key], ensure_ascii=False))))
        compact["truncated"] = True
        compact["has_more"] = True
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


@_internal_tool(output_schema=LOCAL_MODEL_HEALTH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
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


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_docker_capabilities(
    repo_name: str = "",
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: list bounded Docker operations, risk gates, and configured exec profiles."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    config = get_config()
    if not repo_name:
        result = _list_docker_capabilities(config)
    else:
        canonical_name, _repo_root, requested_name = _repo_context(repo_name)
        _, repo_config = resolve_repo_config(config, canonical_name)
        result = _list_docker_capabilities(config, repo_config)
        result["repo_name"] = canonical_name
        if requested_name != canonical_name:
            result["requested_repo_name"] = requested_name
    if view == "full":
        return result
    result.update(
        {
            "view": "compact",
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        reduced = False
        for key in ("actions", "exec_profiles", "read_only_operations"):
            value = result.get(key)
            if isinstance(value, list) and value:
                value.pop()
                reduced = True
                break
        if not reduced:
            break
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def docker_health(
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: verify Docker Engine and Docker Compose connectivity."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    result = _docker_health(get_config())
    if view == "full":
        return result
    result.update(
        {
            "view": "compact",
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        reduced = False
        for key in ("engine", "compose"):
            value = result.get(key)
            if isinstance(value, dict) and value:
                value.pop(next(reversed(value)))
                reduced = True
                break
        if not reduced and isinstance(result.get("error"), str) and result["error"]:
            result["error"] = ""
            reduced = True
        if not reduced:
            break
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(
    output_schema=RUN_COMMAND_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def docker_inspect(
    repo_name: str,
    operation: str,
    target: str = "",
    service: str = "",
    tail: int = 200,
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: run one fixed Docker or Compose inspection operation."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
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
    if view == "full":
        return result
    result.setdefault("truncated", False)
    result["response_budget_bytes"] = response_budget_bytes
    result["has_more"] = False
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        reduced = False
        for key in ("stdout", "stderr", "error"):
            value = result.get(key)
            if isinstance(value, str) and value:
                encoded = value.encode("utf-8")
                result[key] = encoded[: max(0, len(encoded) - 1024)].decode(
                    "utf-8", errors="ignore"
                )
                reduced = True
                break
        if not reduced and isinstance(result.get("argv"), list) and result["argv"]:
            result["argv"].pop()
            reduced = True
        if not reduced:
            break
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_cloudflare_capabilities(
    repo_name: str,
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: list Cloudflare capabilities and profiles authorized for one repository."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    result = _list_cloudflare_capabilities(get_config(), repo_name)
    if view == "full":
        return result
    result.update(
        {
            "view": "compact",
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        reduced = False
        for key in ("actions", "profiles", "zones", "resources"):
            value = result.get(key)
            if isinstance(value, list) and value:
                value.pop()
                reduced = True
                break
        if not reduced:
            break
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def cloudflare_health(
    repo_name: str,
    profile_id: str,
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: verify an authorized repository Cloudflare profile and token."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    config = get_config()
    canonical_repo_name, _ = authorize_cloudflare_profile(config, repo_name, profile_id)
    result = _cloudflare_health(config, profile_id)
    result["repo_name"] = canonical_repo_name
    if view == "full":
        return result
    result.update(
        {
            "view": "compact",
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        reduced = False
        for key in ("engine", "token", "profile", "details"):
            value = result.get(key)
            if isinstance(value, dict) and value:
                value.pop(next(reversed(value)))
                reduced = True
                break
        if not reduced and isinstance(result.get("error"), str) and result["error"]:
            result["error"] = ""
            reduced = True
        if not reduced:
            break
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def cloudflare_inspect(
    repo_name: str,
    profile_id: str,
    operation: str,
    resource_id: str = "",
    name: str = "",
    record_type: str = "",
    since_minutes: int = 60,
    page: int = 1,
    per_page: int = 100,
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: run one bounded Cloudflare inspection for an authorized repository."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    config = get_config()
    canonical_repo_name, _ = authorize_cloudflare_profile(config, repo_name, profile_id)
    result = _run_cloudflare_inspection(
        config,
        profile_id,
        operation,
        resource_id=resource_id,
        name=name,
        record_type=record_type,
        since_minutes=since_minutes,
        page=page,
        per_page=per_page,
    )
    result["repo_name"] = canonical_repo_name
    if view == "full":
        return result
    result.setdefault("truncated", False)
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        reduced = False
        payload = result.get("result")
        if isinstance(payload, list) and payload:
            payload.pop()
            reduced = True
        elif isinstance(payload, dict) and payload:
            payload.pop(next(reversed(payload)))
            reduced = True
        elif isinstance(result.get("result_info"), dict) and result["result_info"]:
            result["result_info"].pop(next(reversed(result["result_info"])))
            reduced = True
        elif isinstance(result.get("error"), str) and result["error"]:
            result["error"] = ""
            reduced = True
        if not reduced:
            break
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_cloudflare_action_async(
    repo_name: str,
    profile_id: str,
    action: str,
    resource_id: str = "",
    payload: dict[str, Any] = {},
    confirmation: str = "",
) -> dict:
    """Write async tool: queue one bounded Cloudflare DNS, cache, zone, ruleset, or tunnel action."""
    return get_job_manager().start_cloudflare_action(
        repo_name,
        profile_id,
        action,
        resource_id=resource_id,
        payload=payload,
        confirmation=confirmation,
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_ssh_capabilities() -> dict:
    """Read-only: list SSH hosts, inspections, actions, transfers, deployments, and risk gates."""
    config = get_config()
    return _enrich_ssh_capabilities(config, _list_ssh_capabilities(config))


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def probe_ssh_credential_source(
    source_path: str = "",
    source_type: str = "auto",
    host_hint: str = "",
    field_overrides: dict[str, str] = {},
) -> dict:
    """Read-only: inspect one local SSH credential source without returning values."""
    return _probe_ssh_credential_source(
        _get_runs_dir(),
        source_path=source_path,
        source_type=source_type,
        host_hint=host_hint,
        field_overrides=field_overrides,
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def preview_ssh_profile_change(
    action: str,
    host_id: str,
    host_config: dict[str, Any] = {},
    command_id: str = "",
    command_profile: dict[str, Any] = {},
    credential_source_id: str = "",
    credential_source: dict[str, Any] = {},
    project_bindings: dict[str, Any] = {},
    activation_intent: str = "existing_host",
) -> dict:
    """Read-only: validate and preview one structured SSH host or command-profile config change."""
    config_path = get_config_path()
    if config_path is None:
        raise ValueError("SSH profile management requires a config file path")
    return _preview_ssh_profile_change(
        config_path,
        _get_runs_dir(),
        action,
        host_id,
        host_config=host_config or None,
        command_id=command_id,
        command_profile=command_profile or None,
        credential_source_id=credential_source_id,
        credential_source=credential_source or None,
        project_bindings=project_bindings or None,
        activation_intent=activation_intent,
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_ssh_profile_change_status(change_id: str) -> dict:
    """Read-only: return profile preview plus durable activation lifecycle metadata."""
    config_path = get_config_path()
    if config_path is None:
        raise ValueError("SSH profile management requires a config file path")
    result = _get_ssh_profile_change_status(
        config_path, _get_runs_dir(), change_id
    )
    activation = _ssh_activation_status(_get_runs_dir(), change_id)
    if activation.get("state") != "not_started":
        result["activation"] = activation
        result["run_id"] = str(activation.get("run_id") or "")
        result["activation_state"] = str(activation.get("state") or "")
    return result


def _bounded_ssh_query_response(result: dict[str, Any], budget: int) -> dict[str, Any]:
    if budget < 1024 or budget > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact: dict[str, Any] = {
        key: result[key]
        for key in (
            "ok", "enabled", "status", "change_id", "probe_id", "action",
            "host_id", "command_id", "created_at", "applied_at", "failed_at",
            "base_config_sha256", "candidate_config_sha256", "ready_for_binding",
            "source_type", "source_basename", "source_path_identity_sha256",
            "source_version_sha256", "snapshot_id", "snapshot_sha256",
            "schema_version", "collected_at", "binding_id", "repo_name",
            "activation_state", "run_id", "accepted", "activation_intent",
            "required_capabilities_ok", "memory_total_bytes",
            "root_disk_free_bytes", "gpu_available", "gpu_device_count",
            "writes_remote", "high_risk", "error",
        )
        if key in result
    }
    compact.update(
        {
            "view": "compact",
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    for key in ("error",):
        if compact.get(key):
            compact[key] = str(compact[key])[:512]
    hosts = result.get("hosts")
    if isinstance(hosts, list):
        compact["host_count"] = len(hosts)
        compact["command_count"] = sum(
            len(host.get("commands") or []) for host in hosts if isinstance(host, dict)
        )
    diff = result.get("capability_diff")
    if isinstance(diff, dict):
        compact["capability_diff_counts"] = {
            key: len(value or [])
            for key, value in diff.items()
            if isinstance(value, list)
        }
    if result.get("probe_id"):
        for key in (
            "discovered_names", "field_mapping", "field_candidates", "missing_fields",
            "ambiguous_fields", "endpoint_validation", "refusals", "warnings",
        ):
            value = result.get(key)
            if value not in (None, {}, []):
                compact[key] = value
        key_file = result.get("key_file")
        if isinstance(key_file, dict):
            compact["key_file"] = {
                key: key_file[key]
                for key in (
                    "ok", "basename", "size_bytes", "path_identity_sha256",
                    "file_version_sha256", "public_key_fingerprint", "refusals",
                    "warnings",
                )
                if key in key_file
            }
    for key in (
        "available_tools", "available_capabilities", "required_capabilities",
        "missing_required_capabilities", "unknown_required_capabilities",
        "failed_checks", "preparation_required_checks",
    ):
        value = result.get(key)
        if isinstance(value, list):
            compact[key] = list(value)
    for key in ("operating_system", "identity"):
        value = result.get(key)
        if isinstance(value, dict):
            compact[key] = dict(value)
    bindings = result.get("bindings")
    if isinstance(bindings, list):
        compact["bindings"] = [
            {
                key: item[key]
                for key in (
                    "binding_id", "host_id", "repo_name", "source", "remote_root",
                    "required_capabilities", "allow_first_deployment",
                    "health_command_id",
                )
                if isinstance(item, dict) and key in item
            }
            for item in bindings
            if isinstance(item, dict)
        ]
        compact["binding_count"] = len(bindings)
    checks = result.get("checks")
    if isinstance(checks, list):
        compact["checks"] = [dict(item) for item in checks if isinstance(item, dict)]
        compact["check_count"] = len(checks)
    capability = result.get("capability_snapshot")
    if isinstance(capability, dict):
        compact["capability_snapshot"] = {
            key: capability[key]
            for key in (
                "ok", "snapshot_id", "snapshot_sha256", "host_id", "status",
                "required_capabilities_ok", "missing_required_capabilities",
                "unknown_required_capabilities",
            )
            if key in capability
        }
    compact["truncated"] = False
    compact["has_more"] = bool(result.get("capability_diff") or result.get("hosts"))
    compact["response_budget_bytes"] = budget
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    while compact["response_bytes"] > budget:
        reduced = False
        names = compact.get("discovered_names")
        if isinstance(names, list) and names:
            names.pop()
            reduced = True
        else:
            candidates = compact.get("field_candidates")
            if isinstance(candidates, dict):
                candidate_key = next(
                    (key for key, value in reversed(list(candidates.items())) if value),
                    "",
                )
                if candidate_key:
                    candidates[candidate_key].pop()
                    reduced = True
            if not reduced:
                for list_key in (
                    "checks", "bindings", "available_tools", "available_capabilities",
                    "required_capabilities", "missing_required_capabilities",
                    "unknown_required_capabilities", "failed_checks",
                    "preparation_required_checks",
                ):
                    values = compact.get(list_key)
                    if isinstance(values, list) and values:
                        values.pop()
                        reduced = True
                        break
        if not reduced:
            break
        compact["truncated"] = True
        compact["has_more"] = True
        compact["response_bytes"] = len(
            json.dumps(compact, ensure_ascii=False).encode("utf-8")
        )
    return compact


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def apply_ssh_profile_change(change_id: str) -> dict:
    """Write tool: start durable candidate validation and transactional activation."""
    if get_config_path() is None:
        raise ValueError("SSH profile management requires a config file path")
    return get_job_manager().start_ssh_profile_activation(change_id)


@_internal_tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def ssh_host_health(host_id: str) -> dict:
    """Read-only: test one configured SSH alias with a fixed non-interactive command."""
    return _ssh_host_health(get_config(), host_id)


@_internal_tool(
    output_schema=RUN_COMMAND_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def ssh_environment_probe(host_id: str) -> dict:
    """Read-only: collect structured OS, Python, CUDA, GPU, memory, disk, and watchdog metadata."""
    return _run_ssh_environment_probe(get_config(), host_id)


@_internal_tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def ssh_gpu_telemetry(host_id: str) -> dict:
    """Read-only: collect structured NVIDIA GPU utilization, memory, temperature, power, and process metadata."""
    return _run_ssh_gpu_telemetry(get_config(), host_id)


@_internal_tool(
    output_schema=RUN_COMMAND_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def ssh_inspect_legacy(
    host_id: str,
    operation: str,
    path: str = "",
    target: str = "",
    deployment_id: str = "",
    tail: int = 200,
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: run one bounded SSH system, service, log, Git, Docker, or file inspection."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    result = _run_ssh_inspection(
        get_config(),
        host_id,
        operation,
        path=path,
        target=target,
        deployment_id=deployment_id,
        tail=tail,
    )
    if view == "full":
        return result
    apply_compact_projection_envelope(result)
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        reduced = False
        for key in ("stdout", "stderr", "error"):
            value = result.get(key)
            if isinstance(value, str) and value:
                encoded = value.encode("utf-8")
                result[key] = encoded[: max(0, len(encoded) - 1024)].decode(
                    "utf-8", errors="ignore"
                )
                reduced = True
                break
        if not reduced and isinstance(result.get("argv"), list) and result["argv"]:
            result["argv"].pop()
            reduced = True
        if not reduced:
            break
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@mcp.tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def ssh_inspect(request: SSHInspectRequest) -> dict:
    """Read-only SSH gateway for strict health, telemetry, and bounded inspections."""
    if request.operation == "host_health":
        result = ssh_host_health(request.host_id)
    elif request.operation == "environment_probe":
        result = ssh_environment_probe(request.host_id)
    elif request.operation == "gpu_telemetry":
        result = ssh_gpu_telemetry(request.host_id)
    else:
        return ssh_inspect_legacy(
            request.host_id,
            request.inspection,
            path=request.path,
            target=request.target,
            deployment_id=request.deployment_id,
            tail=request.tail,
            response_budget_bytes=request.response_budget_bytes,
            view=request.view,
        )
    if request.view == "full":
        return result
    return _bounded_system_query_response(result, request.response_budget_bytes)


@_internal_tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_command_async(
    host_id: str,
    command_id: str,
    autonomy_profile: Literal["permissive"] = "permissive",
    execution_mode: str = "structured",
) -> dict:
    """Write async tool: queue one configured SSH command by host ID and command ID."""
    return get_job_manager().start_ssh_command(
        host_id,
        command_id,
        autonomy_profile=autonomy_profile,
        execution_mode=execution_mode,
    )


@_internal_tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_monitored_command_async(
    host_id: str,
    command_id: str,
    autonomy_profile: Literal["permissive"] = "permissive",
    execution_mode: str = "structured",
) -> dict:
    """Write async tool: queue one opt-in monitored SSH command by host ID and command ID."""
    return get_job_manager().start_ssh_monitored_command(
        host_id,
        command_id,
        autonomy_profile=autonomy_profile,
        execution_mode=execution_mode,
    )


@_internal_tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_reviewed_script_async(
    host_id: str,
    interpreter: str,
    script: str,
    script_sha256: str,
    arguments: list[str] | None = None,
    timeout_seconds: int = 3600,
    writes_remote: bool = True,
    high_risk: bool = False,
    autonomy_profile: Literal["permissive"] = "permissive",
    execution_mode: str = "reviewed_script",
) -> dict:
    """Queue a hash-pinned reviewed SSH script for remote execution."""
    return get_job_manager().start_ssh_reviewed_script(
        host_id,
        interpreter,
        script,
        script_sha256,
        arguments=arguments,
        timeout_seconds=timeout_seconds,
        writes_remote=writes_remote,
        high_risk=high_risk,
        autonomy_profile=autonomy_profile,
        execution_mode=execution_mode,
    )


@_internal_tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_root_shell_async(
    host_id: str,
    script: str,
    script_sha256: str,
    timeout_seconds: int = 3600,
    autonomy_profile: Literal["permissive"] = "permissive",
    execution_mode: str = "root_shell",
) -> dict:
    """Queue a permissive hash-pinned root shell and verify effective UID remotely."""
    return get_job_manager().start_ssh_root_shell(
        host_id,
        script,
        script_sha256,
        timeout_seconds=timeout_seconds,
        autonomy_profile=autonomy_profile,
        execution_mode=execution_mode,
    )


@_internal_tool(
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
    autonomy_profile: Literal["permissive"] = "permissive",
    execution_mode: str = "structured",
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
        autonomy_profile=autonomy_profile,
        execution_mode=execution_mode,
    )


@_internal_tool(
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
    autonomy_profile: Literal["permissive"] = "permissive",
    execution_mode: str = "structured",
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
        autonomy_profile=autonomy_profile,
        execution_mode=execution_mode,
        confirmation=confirmation,
    )


@_internal_tool(
    output_schema=RUN_RESULT_OUTPUT,
    annotations={**WRITE_ANNOTATIONS, "openWorldHint": True},
)
def start_ssh_deployment_async(
    host_id: str,
    deployment_id: str,
    confirmation: str,
    autonomy_profile: Literal["permissive"] = "permissive",
    execution_mode: str = "structured",
) -> dict:
    """Write async tool: deploy a configured repository as an archive release and activate it remotely."""
    return get_job_manager().start_ssh_deployment(
        host_id,
        deployment_id,
        autonomy_profile=autonomy_profile,
        execution_mode=execution_mode,
        confirmation=confirmation,
    )


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def docker_query(request: DockerQueryRequest) -> dict:
    """Read-only Docker gateway for capabilities, health, and bounded inspection."""
    if request.operation == "capabilities":
        return list_docker_capabilities(
            request.repo_name, request.response_budget_bytes, request.view
        )
    if request.operation == "health":
        return docker_health(request.response_budget_bytes, request.view)
    return docker_inspect(
        request.repo_name,
        request.inspection,
        request.target,
        request.service,
        request.tail,
        request.response_budget_bytes,
        request.view,
    )


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations={**WRITE_ANNOTATIONS, "openWorldHint": True})
def docker_action(request: DockerActionRequest) -> dict:
    """Write Docker gateway for bounded configured actions and confirmations."""
    return start_docker_action_async(
        request.repo_name,
        request.action,
        target=request.target,
        destination=request.destination,
        services=request.services,
        command_id=request.command_id,
        context=request.context,
        dockerfile=request.dockerfile,
        build=request.build,
        force=request.force,
        confirmation=request.confirmation,
    )


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True})
def cloudflare_query(request: CloudflareQueryRequest) -> dict:
    """Read-only Cloudflare gateway for authorized capabilities, health, and inspection."""
    if request.operation == "capabilities":
        return list_cloudflare_capabilities(
            request.repo_name, request.response_budget_bytes, request.view
        )
    if request.operation == "health":
        return cloudflare_health(
            request.repo_name, request.profile_id, request.response_budget_bytes, request.view
        )
    return cloudflare_inspect(
        request.repo_name, request.profile_id, request.inspection,
        resource_id=request.resource_id, name=request.name, record_type=request.record_type,
        since_minutes=request.since_minutes, page=request.page, per_page=request.per_page,
        response_budget_bytes=request.response_budget_bytes, view=request.view,
    )


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations={**WRITE_ANNOTATIONS, "openWorldHint": True})
def cloudflare_action(request: CloudflareActionRequest) -> dict:
    """Write Cloudflare gateway for profile-authorized bounded actions."""
    return start_cloudflare_action_async(
        request.repo_name, request.profile_id, request.action,
        resource_id=request.resource_id, payload=request.payload,
        confirmation=request.confirmation,
    )


@mcp.tool(
    output_schema=GENERIC_OBJECT_OUTPUT,
    annotations={**READ_ONLY_ANNOTATIONS, "openWorldHint": True},
)
def ssh_query(request: SSHQueryRequest) -> dict:
    """Read-only SSH gateway for capability, credential, profile, and binding operations."""
    if request.operation == "capabilities":
        result = list_ssh_capabilities()
    elif request.operation == "credential_probe":
        result = probe_ssh_credential_source(
            request.source_path,
            request.source_type,
            request.host_hint,
            request.field_overrides,
        )
    elif request.operation == "profile_status":
        result = get_ssh_profile_change_status(request.change_id)
    elif request.operation == "capability_snapshot":
        if request.snapshot_id:
            full_snapshot = _read_ssh_capability_snapshot(
                _get_runs_dir(),
                host_id=request.host_id,
                snapshot_id=request.snapshot_id,
            )
            result = (
                full_snapshot
                if request.view == "full"
                else _capability_snapshot_projection(full_snapshot)
            )
        else:
            projection = _run_ssh_capability_snapshot(
                get_config(),
                request.host_id,
                endpoint_route="public_query",
                required_capabilities=request.required_capabilities,
            )
            result = (
                _read_ssh_capability_snapshot(
                    _get_runs_dir(),
                    host_id=request.host_id,
                    snapshot_id=str(projection["snapshot_id"]),
                )
                if request.view == "full"
                else projection
            )
    elif request.operation == "project_bindings":
        bindings = _list_ssh_project_bindings(get_config())
        if request.host_id:
            bindings = [
                item for item in bindings
                if str(item.get("host_id") or "") == request.host_id
            ]
        result = {
            "ok": True,
            "status": "available",
            "host_id": request.host_id,
            "bindings": bindings,
            "error": "",
        }
    elif request.operation == "project_binding_validation":
        result = _run_ssh_project_binding_validation(
            get_config(),
            request.binding_id,
            host_id=request.host_id,
            capability_snapshot_id=request.capability_snapshot_id,
        )
    else:
        result = preview_ssh_profile_change(
            request.action,
            request.host_id,
            request.host_config,
            request.command_id,
            request.command_profile,
            request.credential_source_id,
            request.credential_source,
            request.project_bindings,
            request.activation_intent,
        )
    if request.view == "full":
        return result
    return _bounded_ssh_query_response(result, request.response_budget_bytes)


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations={**WRITE_ANNOTATIONS, "openWorldHint": True})
def ssh_action(request: SSHActionRequest) -> dict:
    """Write SSH gateway for structured, reviewed-script, and root-shell runs."""
    if request.action == "profile_apply":
        result = apply_ssh_profile_change(request.change_id)
        if request.view == "full":
            return result
        run_id = str(result.get("run_id") or "")
        projection_keys = {
            "accepted", "status", "run_id", "repo_name", "change_id",
            "host_id", "activation_intent", "risk_level", "requires_human",
            "reason", "duplicate", "error", "ok",
        }
        compact = apply_compact_projection_envelope(
            {
                key: result[key]
                for key in projection_keys
                if key in result
            }
        )
        compact["ok"] = bool(result.get("accepted", result.get("ok", False)))
        truncated = any(key not in projection_keys for key in result)
        for key in ("reason", "error"):
            if isinstance(compact.get(key), str) and len(compact[key]) > 512:
                compact[key] = compact[key][:512]
                truncated = True
        if run_id:
            compact["polling"] = {
                "tool": "run_query",
                "request": {"operation": "control", "run_id": run_id},
            }
            compact["evidence"] = {
                "tool": "run_query",
                "request": {"operation": "terminal", "run_id": run_id},
            }
        compact["truncated"] = truncated
        compact["has_more"] = truncated
        compact["response_budget_bytes"] = request.response_budget_bytes
        compact["response_bytes"] = len(
            json.dumps(compact, ensure_ascii=False).encode("utf-8")
        )
        return compact
    if request.action == "command":
        return start_ssh_command_async(
            request.host_id,
            request.command_id,
            autonomy_profile=request.autonomy_profile,
            execution_mode=request.execution_mode,
        )
    if request.action == "monitored_command":
        return start_ssh_monitored_command_async(
            request.host_id,
            request.command_id,
            autonomy_profile=request.autonomy_profile,
            execution_mode=request.execution_mode,
        )
    if request.action == "reviewed_script":
        return start_ssh_reviewed_script_async(
            request.host_id,
            request.interpreter,
            request.script,
            request.script_sha256,
            arguments=request.arguments,
            timeout_seconds=request.timeout_seconds,
            writes_remote=request.writes_remote,
            high_risk=request.high_risk,
            autonomy_profile=request.autonomy_profile,
            execution_mode=request.execution_mode,
        )
    if request.action == "root_shell":
        return start_ssh_root_shell_async(
            request.host_id,
            request.script,
            request.script_sha256,
            timeout_seconds=request.timeout_seconds,
            autonomy_profile=request.autonomy_profile,
            execution_mode=request.execution_mode,
        )
    if request.action == "administration":
        return start_ssh_action_async(
            request.host_id, request.ssh_action, target=request.target,
            source=request.source, destination=request.destination, path=request.path,
            deployment_id=request.deployment_id, command_id=request.command_id,
            packages=request.packages, executable=request.executable, args=request.args,
            force=request.force, confirmation=request.confirmation,
            autonomy_profile=request.autonomy_profile,
            execution_mode=request.execution_mode,
        )
    if request.action == "transfer":
        return start_ssh_transfer_async(
            request.host_id, request.direction, request.repo_name,
            request.local_path, request.remote_path, request.recursive,
            request.overwrite, request.confirmation,
            autonomy_profile=request.autonomy_profile,
            execution_mode=request.execution_mode,
        )
    return start_ssh_deployment_async(
        request.host_id, request.deployment_id, request.confirmation,
        autonomy_profile=request.autonomy_profile,
        execution_mode=request.execution_mode,
    )


@_internal_tool(
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


@_internal_tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_local_powershell_async(
    repo_name: str,
    profile_id: str,
    argv: list[str],
    *,
    working_directory: str = "",
    environment: dict[str, str] | None = None,
    stdin_text: str | None = None,
    stdin_base64: str | None = None,
    timeout_seconds: int | None = None,
    return_when: str = "accepted",
    wait_seconds: float = 0.0,
) -> dict:
    """Durably launch PowerShell and optionally wait briefly for a terminal projection."""
    stdin_bytes = None
    if stdin_base64 is not None:
        try:
            stdin_bytes = base64.b64decode(stdin_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("stdin_base64 must contain valid base64") from exc
    manager = get_job_manager()
    response = manager.start_executable_profile(
        repo_name,
        profile_id,
        argv,
        working_directory=working_directory,
        environment=environment,
        stdin_text=stdin_text,
        stdin_bytes=stdin_bytes,
        timeout_seconds=timeout_seconds,
    )
    response.setdefault(
        "polling",
        {"tool": "run_query", "request": {"operation": "status", "run_id": response.get("run_id", "")}},
    )
    response.setdefault(
        "evidence",
        {"tool": "run_query", "request": {"operation": "terminal", "run_id": response.get("run_id", "")}},
    )
    if return_when == "accepted":
        response["return_when"] = "accepted"
        return response
    if return_when != "terminal_or_timeout":
        raise ValueError("return_when must be accepted or terminal_or_timeout")
    return manager.wait_for_terminal_or_timeout(response, wait_seconds)


@_internal_tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_remote_powershell_async(
    host_id: str,
    executable_path: str,
    argv: list[str],
    *,
    working_directory: str = "",
    environment: dict[str, str] | None = None,
    stdin_base64: str | None = None,
    timeout_seconds: int | None = None,
) -> dict:
    """Write async tool: launch unrestricted PowerShell on a registered permissive remote host."""
    stdin_bytes = None
    if stdin_base64 is not None:
        try:
            stdin_bytes = base64.b64decode(stdin_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("stdin_base64 must contain valid base64") from exc
    return get_job_manager().start_remote_powershell(
        host_id,
        executable_path,
        argv,
        working_directory=working_directory,
        environment=environment,
        stdin_bytes=stdin_bytes,
        timeout_seconds=timeout_seconds,
    )


@_internal_tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_local_powershell_group_async(
    repo_name: str,
    children: list[dict[str, Any]],
    *,
    requested_concurrency: int | None = None,
    repository_lock_policy: str = "none",
    failure_policy: str = "continue_all",
) -> dict:
    """Write async tool: durably accept and launch a parallel unrestricted PowerShell command group."""
    decoded_children: list[dict[str, Any]] = []
    for child in children:
        normalized = dict(child)
        stdin_base64 = normalized.pop("stdin_base64", None)
        if stdin_base64 is not None:
            try:
                normalized["stdin_bytes"] = base64.b64decode(
                    stdin_base64, validate=True
                )
            except (binascii.Error, ValueError) as exc:
                raise ValueError("stdin_base64 must contain valid base64") from exc
        decoded_children.append(normalized)
    return get_job_manager().start_powershell_group(
        repo_name,
        decoded_children,
        requested_concurrency=requested_concurrency,
        repository_lock_policy=repository_lock_policy,
        failure_policy=failure_policy,
    )


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def run_start(request: RunStartRequest) -> dict:
    """Write gateway for durable validation and unrestricted permissive PowerShell runs."""
    if request.operation == "hermes_service":
        return get_hermes_service_gateway().execute(
            session_id=request.session_id,
            operation=request.service_operation,
            payload=request.payload,
            expected_registry_generation=request.expected_registry_generation,
            expected_schema_hash=request.expected_schema_hash,
            worker_wait_timeout_seconds=request.worker_wait_timeout_seconds,
        )
    if request.operation == "hermes_companion":
        launch = build_companion_launch(
            profile_id=request.profile_id,
            checkout=request.checkout,
            operation=request.companion_operation,
            payload=request.payload,
            expected_registry_generation=request.expected_registry_generation,
            expected_schema_hash=request.expected_schema_hash,
            hermes_home=request.hermes_home or None,
            timeout_seconds=request.timeout_seconds,
        )
        return start_companion_request(get_job_manager(), request.repo_name, launch)
    if request.operation == "remote_powershell":
        return start_remote_powershell_async(
            request.host_id,
            request.executable_path,
            request.argv,
            working_directory=request.working_directory,
            environment=request.environment,
            stdin_base64=request.stdin_base64,
            timeout_seconds=request.timeout_seconds,
        )
    if request.operation == "powershell_group":
        return start_local_powershell_group_async(
            request.repo_name,
            [child.model_dump() for child in request.children],
            requested_concurrency=request.requested_concurrency,
            repository_lock_policy=request.repository_lock_policy,
            failure_policy=request.failure_policy,
        )
    if request.operation == "powershell":
        return start_local_powershell_async(
            request.repo_name,
            request.profile_id,
            request.argv,
            working_directory=request.working_directory,
            environment=request.environment,
            stdin_text=request.stdin_text,
            stdin_base64=request.stdin_base64,
            timeout_seconds=request.timeout_seconds,
            return_when=request.return_when,
            wait_seconds=request.wait_seconds,
        )
    raise ValueError(f"Unsupported run_start operation: {request.operation}")


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def task_query(request: TaskQueryRequest) -> dict:
    """Read-only gateway for canonical task capabilities, status, result, events, and links."""
    manager = get_task_manager()
    if request.operation == "capabilities":
        return manager.capabilities(budget=request.response_budget_bytes)
    if request.operation == "status":
        return manager.get_status(
            request.task_id,
            project_id=request.project_id,
            budget=request.response_budget_bytes,
        )
    if request.operation == "result":
        return manager.get_result(
            request.task_id,
            project_id=request.project_id,
            budget=request.response_budget_bytes,
        )
    if request.operation == "events":
        return manager.get_events(
            request.task_id,
            project_id=request.project_id,
            limit=request.limit,
            after_id=request.after_id,
            budget=request.response_budget_bytes,
        )
    if request.operation == "quarantine":
        return manager.list_quarantine(
            request.project_id,
            limit=request.limit,
            budget=request.response_budget_bytes,
        )
    return manager.get_links(
        request.task_id,
        project_id=request.project_id,
        limit=request.limit,
        budget=request.response_budget_bytes,
    )


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def task_action(request: TaskActionRequest) -> dict:
    """Write gateway for canonical starts, cancellation, and recovery disposition."""
    manager = get_task_manager()
    if request.operation == "start":
        return manager.start_durable_command(
            controller_request_id=request.controller_request_id,
            project_id=request.project_id,
            repo_name=request.repo_name,
            profile_id=request.profile_id,
            argv=list(request.argv),
            working_directory=request.working_directory,
            environment=dict(request.environment),
            stdin_text=request.stdin_text,
            stdin_base64=request.stdin_base64,
            timeout_seconds=request.timeout_seconds,
            parent_task_id=request.parent_task_id,
            budget=request.response_budget_bytes,
        )
    if request.operation == "resolve_recovery":
        return manager.resolve_recovery(
            project_id=request.project_id,
            task_id=request.task_id,
            if_state_version=request.if_state_version,
            successor_task_id=request.successor_task_id,
            reason=request.reason,
            idempotency_key=request.idempotency_key,
            budget=request.response_budget_bytes,
        )
    if request.operation == "adjudicate_quarantine":
        return manager.adjudicate_quarantine(
            project_id=request.project_id,
            record_kind=request.record_kind,
            record_id=request.record_id,
            disposition=request.disposition,
            reason=request.reason,
            idempotency_key=request.idempotency_key,
            successor_task_id=request.successor_task_id,
            budget=request.response_budget_bytes,
        )
    return manager.cancel_task(
        request.task_id,
        project_id=request.project_id,
        if_state_version=request.if_state_version,
        reason=request.reason,
        controller_request_id=request.controller_request_id,
        budget=request.response_budget_bytes,
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def hermes_service_health() -> dict:
    """Read-only: shared Hermes service health, identity, and supervision evidence."""
    return get_hermes_service_gateway().health()


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def hermes_service_cancel(run_id: str, request_id: str, session_id: str) -> dict:
    """Write: cancel one owned shared-service Hermes request by its exact identity triple."""
    return get_hermes_service_gateway().cancel(
        run_id=run_id, request_id=request_id, session_id=session_id
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def hermes_service_result(run_id: str, session_id: str) -> dict:
    """Read-only: durable shared-service result, released only to the owning session."""
    return get_hermes_service_gateway().get_result(
        run_id=run_id, session_id=session_id
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def hermes_service_reload_registry() -> dict:
    """Write: atomically publish one new Hermes registry generation to the shared service."""
    return get_hermes_service_gateway().reload_registry()


@_internal_tool(output_schema=WORKFLOW_OUTPUT, annotations=WRITE_ANNOTATIONS)
def start_workflow(repo_name: str, objective: str, steps: list[dict[str, Any]]) -> dict:
    """Write async tool: queue one durable validated workflow and return its workflow ID immediately."""
    return get_workflow_manager().start_workflow(repo_name, objective, steps)


@_internal_tool(output_schema=WORKFLOW_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_workflow_status(workflow_id: str) -> dict:
    """Read-only: return durable status metadata for one workflow."""
    return get_workflow_manager().get_status(workflow_id)


@_internal_tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_workflow_events(
    workflow_id: str,
    limit: int = 100,
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: return ordered workflow events."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    result = _wrap_item_list(
        "events",
        "workflow_id",
        workflow_id,
        get_workflow_manager().get_events(workflow_id, limit),
    )
    if view == "full":
        return result
    apply_compact_projection_envelope(result)
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        events = result.get("events")
        if not isinstance(events, list) or not events:
            break
        events.pop()
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(output_schema=WORKFLOW_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_workflow_result(workflow_id: str) -> dict:
    """Read-only: return the latest durable workflow snapshot."""
    return get_workflow_manager().get_result(workflow_id)


def _truncate_workflow_text(value: Any, maximum_bytes: int = 512) -> str:
    encoded = str(value or "").encode("utf-8")
    return encoded[:maximum_bytes].decode("utf-8", errors="ignore")


def _bounded_workflow_response(workflow: dict[str, Any], response_budget_bytes: int) -> dict:
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    steps = []
    for step in workflow.get("steps", []):
        steps.append(
            {
                "id": step.get("id"),
                "type": step.get("type"),
                "status": step.get("status"),
                "depends_on": step.get("depends_on", []),
                "child_run_id": step.get("child_run_id"),
                "summary": _truncate_workflow_text(step.get("summary")),
                "error": _truncate_workflow_text(step.get("error")),
            }
        )
    response = {
        "ok": bool(workflow.get("ok", True)),
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "workflow_id": workflow.get("workflow_id"),
        "repo_name": workflow.get("repo_name"),
        "status": workflow.get("status"),
        "terminal_status": workflow.get("terminal_status", ""),
        "created_at": workflow.get("created_at"),
        "updated_at": workflow.get("updated_at"),
        "started_at": workflow.get("started_at"),
        "ended_at": workflow.get("ended_at"),
        "active_child_run_id": workflow.get("active_child_run_id"),
        "state_version": workflow.get("state_version"),
        "launch_attempts": workflow.get("launch_attempts"),
        "publication_status": workflow.get("publication_status"),
        "step_count": workflow.get("step_count", len(steps)),
        "steps": steps,
        "error": workflow.get("error", ""),
        "truncated": False,
        "has_more": False,
        "response_budget_bytes": response_budget_bytes,
    }
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        if response["steps"]:
            response["steps"].pop()
            response["truncated"] = True
            response["has_more"] = True
            continue
        break
    response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    return response


@_internal_tool(output_schema=WORKFLOW_OUTPUT, annotations=WRITE_ANNOTATIONS)
def cancel_workflow(workflow_id: str) -> dict:
    """Write tool: cancel a workflow and request cancellation of its active child run."""
    return get_workflow_manager().cancel_workflow(workflow_id)


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def workflow_query(request: WorkflowQueryRequest) -> dict:
    """Read-only gateway for durable workflow status, events, and results."""
    if request.operation == "status":
        workflow = get_workflow_status(request.workflow_id)
        if request.view == "full":
            return workflow
        return _bounded_workflow_response(workflow, request.response_budget_bytes)
    if request.operation == "events":
        return get_workflow_events(
            request.workflow_id,
            request.limit,
            request.response_budget_bytes,
            request.view,
        )
    workflow = get_workflow_result(request.workflow_id)
    if request.view == "full":
        return workflow
    return _bounded_workflow_response(workflow, request.response_budget_bytes)


@mcp.tool(output_schema=WORKFLOW_OUTPUT, annotations=WRITE_ANNOTATIONS)
def workflow_action(request: WorkflowActionRequest) -> dict:
    """Write gateway for validated workflow starts and cancellations."""
    if request.action == "start":
        return start_workflow(request.repo_name, request.objective, request.steps)
    result = cancel_workflow(request.workflow_id)
    if request.view == "full":
        return result
    return _bounded_workflow_response(result, request.response_budget_bytes)


@_internal_tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_status(run_id: str) -> dict:
    """Read-only: return the compact lifecycle projection for routine polling."""
    return get_job_manager().get_lifecycle_status(run_id)


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_input(
    run_id: str,
    view: str = "compact",
    cursor: str = "",
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: explicitly retrieve bounded submitted-input evidence."""
    return get_job_manager().get_input(
        run_id,
        view=view,
        cursor=cursor,
        response_budget_bytes=response_budget_bytes,
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_control_status(
    run_id: str, if_state_version: int | None = None
) -> dict:
    """Read-only: report heartbeat, process-tree, cancellation, and lock state for one run."""
    manager = get_job_manager()
    if if_state_version is None:
        return manager.get_control_status(run_id)
    return manager.get_control_status(run_id, if_state_version=if_state_version)


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_output(
    run_id: str,
    stream: str = "combined",
    tail_bytes: int = 20000,
    view: str = "legacy",
    response_budget_bytes: int | None = None,
) -> dict:
    """Read-only: return a bounded redacted tail of durable stdout and/or stderr."""
    if view not in {"compact", "full", "legacy"}:
        raise ValueError("view must be compact, full, or legacy")
    if view == "legacy":
        return get_job_manager().get_output(run_id, stream, tail_bytes)
    return get_job_manager().get_output(
        run_id,
        stream,
        tail_bytes,
        response_budget_bytes,
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_operation_locks(
    repo_name: str = "",
    include_stale: bool = True,
    limit: int = 50,
    view: str = "compact",
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: list durable repository, SSH-host, and configuration operation locks."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    all_locks = get_job_manager().list_operation_locks(
        repo_name or None, include_stale=include_stale
    )
    if view == "full":
        return {"ok": True, "locks": all_locks, "count": len(all_locks), "error": ""}
    locks = list(all_locks[:limit])
    response = apply_compact_projection_envelope(
        {
            "ok": True,
            "locks": locks,
            "count": len(locks),
            "has_more": len(locks) < len(all_locks),
            "truncated": False,
            "response_budget_bytes": response_budget_bytes,
            "error": "",
        }
    )
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > response_budget_bytes and response["locks"]:
        response["locks"].pop()
        response["truncated"] = True
        response["has_more"] = True
    response["response_bytes"] = len(
        json.dumps(response, ensure_ascii=False).encode("utf-8")
    )
    return response


def _bounded_preflight_response(response: dict[str, Any], budget: int = 12 * 1024) -> dict:
    apply_compact_projection_envelope(response)
    response["response_budget_bytes"] = budget
    response["truncated"] = False
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > budget:
        if response["locks"]:
            response["locks"].pop()
        else:
            active = next((items for items in response["runs"].values() if items), None)
            if active is not None:
                active.pop()
            elif response["tracked_worktree"].get("files"):
                response["tracked_worktree"]["files"].pop()
            else:
                response["truncated"] = True
                break
        response["truncated"] = True
    response["response_bytes"] = len(
        json.dumps(response, ensure_ascii=False).encode("utf-8")
    )
    return response


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_repository_preflight(repo_name: str, include_stale: bool = False) -> dict:
    """Read-only: return one bounded repository/work preflight projection."""
    try:
        canonical_name, repo_root, requested_name = _repo_context(repo_name)
        status = dict(inspect_repo_status_compact(repo_name))
        manager = get_job_manager()
        runs: dict[str, list[dict[str, Any]]] = {}
        for state in ("running", "queued", "launch_pending"):
            page = manager.list_run_summaries(
                repo_name=canonical_name, status=state, limit=20, cursor=None
            )
            runs[state] = [
                {
                    key: item.get(key, "")
                    for key in (
                        "run_id",
                        "status",
                        "tool",
                        "phase",
                        "created_at",
                        "updated_at",
                    )
                    if key in item
                }
                for item in page.get("runs", [])
            ]
        tracked = {
            "clean": not bool(status.get("total_status_entry_count", 0)),
            "branch": status.get("branch", ""),
            "head_commit": git_head(repo_root),
            "changed_file_count": int(status.get("total_status_entry_count", 0) or 0),
            "collapsed_tool_owned_count": int(
                status.get("collapsed_tool_owned_count", 0) or 0
            ),
            "tool_owned_summary": status.get("tool_owned_summary", {}),
            "files": status.get("files", []),
            "fresh": bool(status.get("fresh", False)),
            "status": status.get("status", "unavailable"),
        }
        response: dict[str, Any] = {
            "ok": bool(status.get("ok", False)),
            "operation": "preflight",
            "repo_name": canonical_name,
            "tracked_worktree": tracked,
            "runs": runs,
            "locks": manager.list_operation_locks(
                canonical_name, include_stale=include_stale
            ),
            "live_capability_epoch": _PROCESS_CAPABILITY_METADATA.get(
                "capability_epoch", ""
            ),
            "source": "live",
            "error": status.get("error", ""),
        }
        if requested_name != canonical_name:
            response["requested_repo_name"] = requested_name
        return _bounded_preflight_response(response)
    except Exception as exc:
        return _bounded_preflight_response(
            {
                "ok": False,
                "operation": "preflight",
                "repo_name": repo_name,
                "tracked_worktree": {"files": []},
                "runs": {"running": [], "queued": [], "launch_pending": []},
                "locks": [],
                "live_capability_epoch": _PROCESS_CAPABILITY_METADATA.get(
                    "capability_epoch", ""
                ),
                "source": "unavailable",
                "error": str(exc),
            }
        )


@_internal_tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_events(
    run_id: str,
    limit: int = 20,
    after_id: int | None = None,
    cursor: str = "",
) -> dict:
    """Read-only: return a bounded forward-pollable event page for an async run."""
    return get_job_manager().get_event_page(
        run_id,
        limit,
        after_id,
        cursor or None,
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_terminal_result(run_id: str) -> dict:
    """Read-only: return the bounded source-hash-bound terminal projection."""
    return get_job_manager().get_terminal_result(run_id)


@_internal_tool(output_schema=RUN_RESULT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_result(run_id: str) -> dict:
    """Read-only: return the final or current structured result for an async run."""
    return get_job_manager().get_result(run_id)


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_run_summary(run_id: str) -> dict:
    """Read-only: return a bounded non-authoritative scalar summary for one run."""
    return get_job_manager().get_run_summary(run_id)


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_run_summaries(
    repo_name: str = "",
    status: str = "",
    tool: str = "",
    limit: int = 10,
    cursor: str = "",
) -> dict:
    """Read-only: return a stable bounded page of scalar run summaries."""
    return get_job_manager().list_run_summaries(
        repo_name=repo_name or None,
        status=status or None,
        tool=tool or None,
        limit=limit,
        cursor=cursor or None,
    )


@_internal_tool(output_schema=RUN_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_runs(repo_name: str = "", status: str = "", limit: int = 20) -> dict:
    """Read-only: list recent async runs with optional repo/status filters."""
    return {
        "ok": True,
        "runs": get_job_manager().list_runs(
            repo_name=repo_name or None, status=status or None, limit=limit
        ),
        "error": "",
    }


def _bounded_cancel_response(result: dict[str, Any], budget: int) -> dict[str, Any]:
    if budget < 1024 or budget > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact = {
        key: result[key]
        for key in ("ok", "run_id", "group_id", "status", "repo_name", "error", "message")
        if key in result
    }
    compact.update(
        {
            "view": "compact",
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    for key in ("error", "message"):
        if compact.get(key):
            compact[key] = str(compact[key])[:512]
    for key in ("process_tree", "children", "diagnostics"):
        if isinstance(result.get(key), list):
            compact[f"{key}_count"] = len(result[key])
    compact["truncated"] = False
    compact["has_more"] = any(key in result for key in ("process_tree", "children", "diagnostics"))
    compact["response_budget_bytes"] = budget
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


@mcp.tool(output_schema=RUN_RESULT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def cancel_run(
    run_id: str,
    view: Literal["compact", "full"] = "compact",
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Write tool: request cancellation of one durable run or PowerShell command group."""
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    if "_powershell_group_" in run_id:
        result = get_job_manager().cancel_powershell_group(run_id)
    else:
        result = get_job_manager().cancel_run(run_id)
    if view == "full":
        return result
    return _bounded_cancel_response(result, response_budget_bytes)


def _truncate_group_text(value: Any, maximum_bytes: int = 512) -> str:
    text = str(value or "")
    encoded = text.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return text
    return encoded[:maximum_bytes].decode("utf-8", errors="ignore")


def _bounded_group_response(group: dict[str, Any], response_budget_bytes: int) -> dict:
    children = []
    for child in group.get("children", []):
        children.append(
            {
                key: (
                    _truncate_group_text(child.get(key))
                    if key in {"summary", "error"}
                    else child.get(key)
                )
                for key in (
                    "position",
                    "run_id",
                    "status",
                    "current_phase",
                    "summary",
                    "error",
                    "exit_code",
                    "started_at",
                    "ended_at",
                )
            }
        )
    response = {
        "ok": True,
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "group_id": group.get("group_id"),
        "repo_name": group.get("repo_name"),
        "status": group.get("status"),
        "mode": group.get("mode"),
        "failure_policy": group.get("failure_policy"),
        "repository_lock_policy": group.get("repository_lock_policy"),
        "requested_concurrency": group.get("requested_concurrency"),
        "created_at": group.get("created_at"),
        "ended_at": group.get("ended_at"),
        "child_count": group.get("child_count", len(children)),
        "terminal_child_count": group.get("terminal_child_count"),
        "status_counts": group.get("status_counts", {}),
        "children": children,
        "truncated": False,
        "has_more": False,
        "response_budget_bytes": response_budget_bytes,
    }
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        if response["children"]:
            response["children"].pop()
            response["truncated"] = True
            response["has_more"] = True
            continue
        for field in ("summary", "error"):
            for child in response["children"]:
                child[field] = _truncate_group_text(child.get(field), 128)
        break
    response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    return response


def _run_scope_guard(
    request: RunQueryRequest,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    project_id = str(getattr(request, "project_id", "") or "")
    if not project_id:
        return None, None
    encoded_run_id = str(getattr(request, "run_id", "") or "")
    try:
        reference = decode_run_reference(encoded_run_id)
        run_id = reference.resource_id if reference is not None else encoded_run_id
        scope = get_project_scope_store().require_run(project_id, run_id)
    except (ValueError, ProjectScopeError) as exc:
        return (
            {
                "ok": False,
                "operation": str(request.operation),
                "run_id": encoded_run_id,
                "project_id": project_id,
                "error_code": "project_scope_mismatch",
                "error": str(exc),
            },
            None,
        )
    return None, scope.to_dict()


def _add_run_scope_projection(
    request: RunQueryRequest,
    scope: dict[str, Any] | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(scope, dict):
        return result
    projected = dict(result)
    # ProjectScope is authoritative for these reserved identity fields. A
    # backend result must never be able to shadow them.
    projected.update(scope)

    if int(projected.get("byte_budget") or 0):
        projected = _finalize_scoped_run_projection(
            request=request,
            scope=scope,
            projected=projected,
            budget_key="byte_budget",
            size_key="payload_bytes",
            canonical=True,
        )
    elif int(projected.get("response_budget_bytes") or 0):
        projected = _finalize_scoped_run_projection(
            request=request,
            scope=scope,
            projected=projected,
            budget_key="response_budget_bytes",
            size_key="response_bytes",
            canonical=False,
        )
    return projected


def _finalize_scoped_run_projection(
    *,
    request: RunQueryRequest,
    scope: dict[str, Any],
    projected: dict[str, Any],
    budget_key: str,
    size_key: str,
    canonical: bool,
) -> dict[str, Any]:
    budget = int(projected[budget_key])

    def encoded_size(value: dict[str, Any]) -> int:
        kwargs: dict[str, Any] = {"ensure_ascii": False}
        if canonical:
            kwargs.update({"separators": (",", ":"), "sort_keys": True})
        return len(json.dumps(value, **kwargs).encode("utf-8"))

    accounted = dict(projected)
    accounted[size_key] = 0
    for _ in range(8):
        measured = encoded_size(accounted)
        if accounted[size_key] == measured:
            break
        accounted[size_key] = measured
    if encoded_size(accounted) <= budget:
        return accounted

    bounded = {
        "ok": False,
        "operation": str(request.operation),
        "project_id": str(scope.get("project_id") or ""),
        "error_code": "project_scope_projection_budget_exceeded",
        "error": "Scoped run projection exceeds the declared response budget",
        budget_key: budget,
        size_key: 0,
    }
    for _ in range(8):
        measured = encoded_size(bounded)
        if bounded[size_key] == measured:
            break
        bounded[size_key] = measured
    return bounded


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def run_query(request: RunQueryRequest) -> dict:
    """Read-only gateway for durable run summaries, status, evidence, lists, and locks."""
    scope_error, scope = _run_scope_guard(request)
    if scope_error is not None:
        return scope_error
    if request.operation == "summary":
        return _add_run_scope_projection(
            request, scope, get_run_summary(request.run_id)
        )
    if request.operation == "summary_list":
        return list_run_summaries(
            request.repo_name,
            request.status,
            request.tool,
            request.limit,
            request.cursor,
        )
    if request.operation == "status":
        return _add_run_scope_projection(
            request, scope, get_run_status(request.run_id)
        )
    if request.operation == "input":
        return _add_run_scope_projection(
            request,
            scope,
            get_run_input(
                request.run_id,
                request.view,
                request.cursor,
                request.response_budget_bytes,
            ),
        )
    if request.operation == "control":
        return _add_run_scope_projection(
            request,
            scope,
            get_run_control_status(request.run_id, request.if_state_version),
        )
    if request.operation == "output":
        return _add_run_scope_projection(
            request,
            scope,
            get_run_output(
                request.run_id,
                request.stream,
                request.tail_bytes,
                request.view,
                request.response_budget_bytes,
            ),
        )
    if request.operation == "events":
        return _add_run_scope_projection(
            request,
            scope,
            get_run_events(
                request.run_id,
                request.limit,
                request.after_id,
                request.cursor,
            ),
        )
    if request.operation == "terminal":
        return _add_run_scope_projection(
            request, scope, get_run_terminal_result(request.run_id)
        )
    if request.operation == "result":
        if request.view == "full":
            return _add_run_scope_projection(
                request, scope, get_run_result(request.run_id)
            )
        return _add_run_scope_projection(
            request, scope, get_run_terminal_result(request.run_id)
        )
    if request.operation in {"group_status", "group_result"}:
        group = get_job_manager().get_powershell_group(request.group_id)
        if request.view == "full":
            return group
        return _bounded_group_response(group, request.response_budget_bytes)
    if request.operation == "list":
        return list_runs(request.repo_name, request.status, request.limit)
    if request.operation == "preflight":
        return get_repository_preflight(request.repo_name, request.include_stale)
    return list_operation_locks(
        request.repo_name,
        request.include_stale,
        request.limit,
        request.view,
        request.response_budget_bytes,
    )


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def reload_service(modules: list[str] = []) -> dict:
    """Write tool: reload supported Soma modules and refresh in-memory config when possible."""
    result = _reload_service(get_config_path(), modules=modules)
    if result["ok"] and get_config_path() is not None:
        set_config(apply_reloaded_config(get_config_path()), get_config_path())
    return result


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def validate_service_config() -> dict:
    """Read-only: validate the current config candidate without activating it."""
    return _validate_config_candidate(get_config_path())


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_service_reload_status() -> dict:
    """Read-only: return structured config lifecycle metadata for reload status."""
    return _get_reload_status()


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def rollback_service() -> dict:
    """Write tool: restore the previous last-known-good in-memory configuration."""
    result = _rollback_service()
    rolled_back_config = result.pop("config", None)
    if result.get("ok") and isinstance(rolled_back_config, AppConfig):
        set_config(rolled_back_config, get_config_path())
    return result


def _bounded_system_action_response(result: dict[str, Any], response_budget_bytes: int) -> dict:
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact: dict[str, Any] = {
        key: result[key]
        for key in ("ok", "reloaded", "resolved_modules", "restart_required", "rolled_back", "message", "error")
        if key in result
    }
    compact.update(
        {
            "view": "compact",
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    for key in ("message", "error"):
        if compact.get(key):
            compact[key] = str(compact[key])[:512]
    lifecycle = result.get("config_lifecycle")
    if isinstance(lifecycle, dict):
        compact["config_lifecycle"] = {
            key: lifecycle[key]
            for key in ("last_operation", "last_status", "last_error", "has_active_config", "has_last_known_good_config", "has_previous_config")
            if key in lifecycle
        }
        if compact["config_lifecycle"].get("last_error"):
            compact["config_lifecycle"]["last_error"] = str(compact["config_lifecycle"]["last_error"])[:512]
    compact["reloaded_count"] = len(result.get("reloaded") or [])
    compact["restart_required_count"] = len(result.get("restart_required") or [])
    compact["truncated"] = False
    compact["has_more"] = False
    compact["response_budget_bytes"] = response_budget_bytes
    encoded = json.dumps(compact, ensure_ascii=False).encode("utf-8")
    if len(encoded) > response_budget_bytes:
        for key in ("resolved_modules", "restart_required", "reloaded"):
            if key in compact:
                compact.pop(key)
                compact["truncated"] = True
                compact["has_more"] = True
                encoded = json.dumps(compact, ensure_ascii=False).encode("utf-8")
                if len(encoded) <= response_budget_bytes:
                    break
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


def _capability_identity_result(request: SystemQueryRequest) -> dict[str, Any]:
    source_build = server_build_hash()
    source_schema = schema_hash(PATCH_OPERATION_SCHEMA)
    (
        live_operation_schema_hashes,
        live_schema_error,
        discovery_passes_converged,
        live_input_schema_hash,
    ) = _live_operation_schema_hashes_sync()
    identity = _operation_identity_metadata(
        live_input_schema_hash=live_input_schema_hash
    )
    operation_inventory = identity["operation_inventory"]
    operation_inventory_hash = identity["operation_inventory_hash"]
    public_schema_hash = identity["public_schema_hash"]
    discovery_cache_generation = identity["discovery_cache_generation"]
    inventory_operation_names = {
        f"{gateway}.{operation}"
        for gateway, names in operation_inventory.items()
        for operation in names
    }
    running_build = _PROCESS_CAPABILITY_METADATA["server_build_hash"]
    running_schema = _PROCESS_CAPABILITY_METADATA["schema_hash"]
    running_epoch = _PROCESS_CAPABILITY_METADATA["capability_epoch"]
    mismatches: list[str] = []
    if source_build != running_build:
        mismatches.append("source_running_server_build_hash")
    if source_schema != running_schema:
        mismatches.append("source_running_schema_hash")
    if request.expected_server_build_hash and request.expected_server_build_hash != running_build:
        mismatches.append("connector_server_build_hash")
    if request.expected_schema_hash and request.expected_schema_hash != running_schema:
        mismatches.append("connector_schema_hash")
    connector_schema_hash = request.expected_connector_schema_hash
    if (
        connector_schema_hash
        and connector_schema_hash != public_schema_hash
    ):
        mismatches.append("connector_public_schema_hash")
    if request.expected_capability_epoch and request.expected_capability_epoch != running_epoch:
        mismatches.append("connector_capability_epoch")
    if (
        request.expected_operation_inventory_hash
        and request.expected_operation_inventory_hash != operation_inventory_hash
    ):
        mismatches.append("connector_operation_inventory_hash")
    if (
        request.expected_public_schema_hash
        and request.expected_public_schema_hash != public_schema_hash
    ):
        mismatches.append("connector_public_schema_hash")
    if (
        request.expected_discovery_cache_generation
        and request.expected_discovery_cache_generation != discovery_cache_generation
    ):
        mismatches.append("connector_discovery_cache_generation")
    if (
        request.expected_live_input_schema_hash
        and request.expected_live_input_schema_hash != live_input_schema_hash
    ):
        mismatches.append("connector_live_input_schema_hash")
    if live_schema_error:
        mismatches.append("live_operation_schema_discovery")
    elif not discovery_passes_converged:
        mismatches.append("live_operation_schema_discovery_pass_mismatch")
    else:
        for operation_name in sorted(inventory_operation_names - set(live_operation_schema_hashes)):
            mismatches.append(f"operation_missing:{operation_name}")
        for operation_name in sorted(set(live_operation_schema_hashes) - inventory_operation_names):
            mismatches.append(f"operation_extra:{operation_name}")
        for operation_name, expected_hash in sorted(
            request.expected_operation_schema_hashes.items()
        ):
            actual_hash = live_operation_schema_hashes.get(operation_name)
            if actual_hash is None:
                mismatches.append(f"connector_operation_missing:{operation_name}")
            elif actual_hash != expected_hash:
                mismatches.append(f"connector_operation_schema:{operation_name}")
    return {
        "ok": not mismatches,
        "converged": not mismatches,
        "source_server_build_hash": source_build,
        "source_schema_hash": source_schema,
        "running_server_build_hash": running_build,
        "running_schema_hash": running_schema,
        "running_capability_epoch": running_epoch,
        "public_schema_hash": public_schema_hash,
        "connector_schema_hash": connector_schema_hash,
        "discovery_cache_generation": discovery_cache_generation,
        "operation_schema_hashes": live_operation_schema_hashes,
        "operation_schema_key_format": "gateway.operation",
        "operation_schema_count": len(live_operation_schema_hashes),
        "operation_schema_error": live_schema_error,
        "live_input_schema_hash": live_input_schema_hash,
        "runtime_input_schema_hash": identity["runtime_input_schema_hash"],
        "discovery_pass_count": 2,
        "discovery_passes_converged": discovery_passes_converged,
        "operation_inventory_hash": operation_inventory_hash,
        "operation_inventory_gateway_count": len(operation_names_by_gateway()),
        "mismatches": mismatches,
        "error": "capability identities do not converge" if mismatches else "",
        "refresh_guidance": (
            "refresh connector schema and discovery cache, then retry capability_identity"
            if mismatches
            else ""
        ),
    }


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def system_query(request: SystemQueryRequest) -> dict:
    """Read-only system gateway for capabilities, health, configuration validation, and reload status."""
    if request.operation == "capability_identity":
        result = _capability_identity_result(request)
    elif request.operation == "capabilities":
        result = _system_capabilities_result()
    elif request.operation == "self_check":
        result = run_local_self_check()
        if request.view == "full":
            return result
        return _bounded_self_check_response(result, request.response_budget_bytes)
    elif request.operation == "local_model_health":
        result = local_model_health()
    elif request.operation == "validate_config":
        result = validate_service_config()
    else:
        result = get_service_reload_status()
    if request.view == "full":
        return result
    return _bounded_system_query_response(result, request.response_budget_bytes)


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def system_action(request: SystemActionRequest) -> dict:
    """Write system gateway for validated reload and last-known-good rollback."""
    if request.action == "reload":
        result = reload_service(request.modules)
    else:
        result = rollback_service()
    if request.view == "full":
        return result
    return _bounded_system_action_response(result, request.response_budget_bytes)


@_internal_tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@_internal_tool(output_schema=SUPERVISOR_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_status(supervisor_id: str) -> dict:
    """Read-only: return enriched supervisor status."""
    return get_supervisor_service().get_status(supervisor_id)


@_internal_tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_events(
    supervisor_id: str,
    limit: int = 50,
    response_budget_bytes: int = 12 * 1024,
    view: str = "compact",
) -> dict:
    """Read-only: return ordered supervisor events."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    result = _wrap_item_list(
        "events",
        "supervisor_id",
        supervisor_id,
        get_supervisor_service().get_events(supervisor_id, limit),
    )
    if view == "full":
        return result
    apply_compact_projection_envelope(result)
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        events = result.get("events")
        if not isinstance(events, list) or not events:
            break
        events.pop()
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(output_schema=SUPERVISOR_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_result(supervisor_id: str) -> dict:
    """Read-only: return supervisor result metadata and linked run references."""
    return get_supervisor_service().get_result(supervisor_id)


@_internal_tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
def resume_supervisor(supervisor_id: str) -> dict:
    """Write tool: advance a supervisor exactly one safe step."""
    return get_supervisor_service().resume(supervisor_id)


@_internal_tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
def pause_supervisor(supervisor_id: str) -> dict:
    """Write tool: pause a queued or needs_input supervisor."""
    return get_supervisor_service().pause(supervisor_id)


@_internal_tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
def cancel_supervisor(supervisor_id: str) -> dict:
    """Write tool: cancel a supervisor and active child if present."""
    return get_supervisor_service().cancel(supervisor_id)


@_internal_tool(output_schema=EVENT_LIST_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_notifications(
    supervisor_id: str,
    delivery_status: str = "",
    limit: int = 50,
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: return persisted supervisor notification rows."""
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    result = _wrap_item_list(
        "notifications",
        "supervisor_id",
        supervisor_id,
        get_supervisor_service().get_notifications(
            supervisor_id, delivery_status or None, limit
        ),
    )
    apply_compact_projection_envelope(result)
    result["truncated"] = False
    result["has_more"] = False
    result["response_budget_bytes"] = response_budget_bytes
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        notifications = result.get("notifications")
        if not isinstance(notifications, list) or not notifications:
            break
        notifications.pop()
        result["truncated"] = True
        result["has_more"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


@_internal_tool(output_schema=SUPERVISOR_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_supervisor_resume_prompt(supervisor_id: str) -> dict:
    """Read-only: return the canonical supervisor resume prompt if present."""
    return get_supervisor_service().get_resume_prompt(supervisor_id)


def _bounded_supervisor_resume_prompt(
    supervisor_id: str, response_budget_bytes: int
) -> dict:
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    source = get_supervisor_resume_prompt(supervisor_id)
    content = str(source.get("content") or "")
    response = {
        "ok": True,
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "supervisor_id": source.get("supervisor_id", supervisor_id),
        "exists": bool(source.get("exists")),
        "content": content,
        "truncated": False,
        "has_more": False,
        "response_budget_bytes": response_budget_bytes,
    }
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        if not response["content"]:
            break
        current = response["content"].encode("utf-8")
        response["content"] = current[: max(0, len(current) - 512)].decode(
            "utf-8", errors="ignore"
        )
        response["truncated"] = True
        response["has_more"] = True
    response["content_bytes"] = len(content.encode("utf-8"))
    response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    return response


def _bounded_supervisor_snapshot(snapshot: dict[str, Any], response_budget_bytes: int) -> dict:
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact = {
        key: snapshot[key]
        for key in (
            "ok",
            "supervisor_id",
            "repo_name",
            "status",
            "terminal_status",
            "created_at",
            "updated_at",
            "started_at",
            "ended_at",
            "active_child_status",
            "active_child_run_id",
            "publication_status",
            "error",
            "failure_summary",
            "recommended_next_action",
        )
        if key in snapshot
    }
    compact.update(
        {
            "view": "compact",
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    for field in ("summary", "failure_summary", "recommended_next_action"):
        if compact.get(field):
            compact[field] = str(compact[field])[:512]
    compact["run_link_count"] = len(snapshot.get("run_links") or [])
    compact["plan_result_present"] = bool(snapshot.get("plan_result"))
    compact["implementation_result_present"] = bool(snapshot.get("implementation_result"))
    compact["truncated"] = False
    compact["has_more"] = False
    compact["response_budget_bytes"] = response_budget_bytes
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def supervisor_query(request: SupervisorQueryRequest) -> dict:
    """Read-only gateway for durable supervisor state and notifications."""
    if request.operation == "status":
        snapshot = get_supervisor_status(request.supervisor_id)
        if request.view == "full":
            return snapshot
        return _bounded_supervisor_snapshot(snapshot, request.response_budget_bytes)
    if request.operation == "events":
        return get_supervisor_events(
            request.supervisor_id,
            request.limit,
            request.response_budget_bytes,
            request.view,
        )
    if request.operation == "result":
        snapshot = get_supervisor_result(request.supervisor_id)
        if request.view == "full":
            return snapshot
        return _bounded_supervisor_snapshot(snapshot, request.response_budget_bytes)
    if request.operation == "notifications":
        if request.view == "full":
            return {
                "ok": True,
                "supervisor_id": request.supervisor_id,
                "notifications": get_supervisor_service().get_notifications(
                    request.supervisor_id,
                    request.delivery_status or None,
                    request.limit,
                ),
            }
        return get_supervisor_notifications(
            request.supervisor_id,
            request.delivery_status,
            request.limit,
            request.response_budget_bytes,
        )
    if request.view == "full":
        return get_supervisor_resume_prompt(request.supervisor_id)
    return _bounded_supervisor_resume_prompt(
        request.supervisor_id, request.response_budget_bytes
    )


@mcp.tool(output_schema=SUPERVISOR_OUTPUT, annotations=WRITE_ANNOTATIONS)
def supervisor_action(request: SupervisorActionRequest) -> dict:
    """Write gateway for validated supervisor lifecycle transitions."""
    if request.action == "start":
        return start_supervised_recovery_task(
            request.repo_name,
            request.objective,
            request.task,
            request.constraints,
            request.source_run_id,
            request.autonomy_profile,
        )
    if request.action == "resume":
        result = resume_supervisor(request.supervisor_id)
    elif request.action == "pause":
        result = pause_supervisor(request.supervisor_id)
    else:
        result = cancel_supervisor(request.supervisor_id)
    if request.view == "full":
        return result
    return _bounded_supervisor_snapshot(result, request.response_budget_bytes)


def _bounded_trading_scalar_response(response: dict[str, Any], budget: int) -> dict[str, Any]:
    if budget < 1024 or budget > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact = apply_compact_projection_envelope(dict(response))
    compact["truncated"] = False
    compact["has_more"] = False
    compact["response_budget_bytes"] = budget
    if len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > budget:
        result = compact.get("result")
        if isinstance(result, dict):
            compact["result"] = {
                key: value
                for key, value in result.items()
                if isinstance(value, (bool, int, float)) or key in {"symbol", "status", "connected"}
            }
        else:
            compact["result"] = str(result or "")[:512]
        compact["truncated"] = True
        compact["has_more"] = True
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def trading_query(request: TradingQueryRequest) -> dict:
    """Read-only gateway for the configured demo MT5 market-data adapter."""
    trading = get_config().trading
    if not trading.enabled:
        return {"ok": False, "status": "disabled", "error": "Trading is disabled"}
    if request.operation in DEPRECATED_QUERY_OPERATIONS:
        return {
            "ok": False,
            "status": "deprecated",
            "operation": request.operation,
            "error": DEPRECATED_QUERY_NOTICE,
        }
    if request.operation in _TRADING_JOURNAL_OPERATIONS:
        return _trading_journal_query(request)
    if request.operation in _TRADING_EXPOSURE_OPERATIONS:
        try:
            result = _trading_exposure_result(
                request.symbol,
                _resolved_trading_execution_mode(request.execution_mode),
            )
        except Exception as exc:
            return {"ok": False, "status": "provider_error", "error": str(exc)}
        response = {
            "ok": True,
            "operation": request.operation,
            "symbol": request.symbol or trading.symbol,
            "result": _trading_json(result),
        }
        if request.view == "full":
            return response
        return _bounded_trading_exposure_response(
            response, request.response_budget_bytes
        )
    if request.operation == "configuration":
        response = {
            "ok": True,
            "operation": request.operation,
            "result": _trading_json(_trading_configuration_result()),
        }
        if request.view == "full":
            return response
        return _bounded_trading_scalar_response(
            response, request.response_budget_bytes
        )
    provider = _configured_mt5_provider()
    try:
        health = provider.connect()
        if request.operation == "health":
            response = {"ok": True, "operation": request.operation, "result": _trading_json(health)}
            if request.view == "full":
                return response
            return _bounded_trading_scalar_response(response, request.response_budget_bytes)
        if not health.connected:
            return {"ok": False, "status": "disconnected", "error": "MT5 terminal is disconnected", "health": _trading_json(health)}
        if health.account_environment != "demo":
            return {"ok": False, "status": "wrong_environment", "error": "MT5 account is not a demo account", "health": _trading_json(health)}
        if request.operation == "symbols":
            result = provider.list_symbols(request.query)
        elif request.operation == "specification":
            result = provider.symbol_specification(trading.symbol)
        elif request.operation == "tick":
            result = provider.latest_tick(trading.symbol)
        elif request.operation in _TRADING_CANDLE_SERIES_OPERATIONS:
            if request.response_budget_bytes < 1024 or request.response_budget_bytes > 64 * 1024:
                raise ValueError("response_budget_bytes must be between 1024 and 65536")
            if request.operation == "candles":
                completed, developing = provider.candles(
                    trading.symbol,
                    request.timeframe or trading.timeframe,
                    completed_count=(
                        request.completed_count
                        if request.completed_count is not None
                        else trading.candle_count
                    ),
                )
            else:
                # The H1/H4 aliases name their own period regardless of
                # what the configured timeframe happens to be.
                candle_reader = (
                    provider.h1_candles
                    if request.operation == "h1_candles"
                    else provider.h4_candles
                )
                completed, developing = candle_reader(
                    trading.symbol, completed_count=request.completed_count
                )
            result = {"completed": completed, "developing": developing}
        elif request.operation == "candle_boundary":
            # The live probe: newest tick plus the newest few bars. It is
            # never answered from the analysis window, so a rate series
            # still catching up after a terminal restart is reported as
            # unsynchronised rather than mistaken for a dead feed.
            result = provider.candle_boundary(
                trading.symbol,
                request.timeframe or trading.timeframe,
                probe_bars=(
                    request.probe_bars
                    if request.probe_bars is not None
                    else trading.boundary_probe_bars
                ),
            )
        elif request.operation == "historical_candles":
            if request.response_budget_bytes < 1024 or request.response_budget_bytes > 64 * 1024:
                raise ValueError("response_budget_bytes must be between 1024 and 65536")
            result = provider.historical_candles(
                trading.symbol,
                request.timeframe or trading.timeframe,
                count=(
                    request.count
                    if request.count is not None
                    else trading.candle_count
                ),
            )
        else:
            if request.response_budget_bytes < 1024 or request.response_budget_bytes > 64 * 1024:
                raise ValueError("response_budget_bytes must be between 1024 and 65536")
            result = provider.historical_ticks(trading.symbol, request.start_utc, request.end_utc)
        response = {"ok": True, "operation": request.operation, "symbol": trading.symbol, "result": _trading_json(result)}
        if request.operation in {"specification", "tick", "candle_boundary"}:
            # Bounded objects: one specification, one tick, or one boundary
            # carrying at most a developing and a just-closed candle.
            if request.view == "full":
                return response
            return _bounded_trading_scalar_response(response, request.response_budget_bytes)
        if request.view == "full":
            return response
        apply_compact_projection_envelope(response)
        if request.operation == "symbols":
            response["truncated"] = False
            response["has_more"] = False
            response["response_budget_bytes"] = request.response_budget_bytes
            while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > request.response_budget_bytes:
                symbols = response.get("result")
                if isinstance(symbols, list) and symbols:
                    symbols.pop()
                else:
                    break
                response["truncated"] = True
                response["has_more"] = True
            response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        if request.operation == "historical_ticks":
            response["truncated"] = False
            response["has_more"] = False
            response["response_budget_bytes"] = request.response_budget_bytes
            while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > request.response_budget_bytes:
                ticks = response.get("result")
                if isinstance(ticks, list) and ticks:
                    ticks.pop()
                else:
                    break
                response["truncated"] = True
                response["has_more"] = True
            response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        if request.operation in _TRADING_CANDLE_SERIES_OPERATIONS:
            response["truncated"] = False
            response["has_more"] = False
            response["response_budget_bytes"] = request.response_budget_bytes
            while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > request.response_budget_bytes:
                candles = response["result"].get("completed")
                if isinstance(candles, list) and candles:
                    candles.pop()
                elif isinstance(response["result"].get("developing"), dict) and response["result"]["developing"]:
                    response["result"]["developing"].pop(next(reversed(response["result"]["developing"])))
                else:
                    break
                response["truncated"] = True
                response["has_more"] = True
            response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        if request.operation == "historical_candles":
            response["truncated"] = False
            response["has_more"] = False
            response["response_budget_bytes"] = request.response_budget_bytes
            while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > request.response_budget_bytes:
                # The series is oldest-first, so dropping the front keeps
                # the bars nearest the decision boundary. The classified
                # gaps stay put: a trimmed window never looks gap-free.
                candles = response["result"].get("candles")
                if isinstance(candles, list) and candles:
                    candles.pop(0)
                else:
                    break
                response["truncated"] = True
                response["has_more"] = True
            response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        return response
    except Exception as exc:
        return {"ok": False, "status": "provider_error", "error": str(exc)}
    finally:
        provider.close()


_TRADING_JOURNAL_OPERATIONS = frozenset(JOURNAL_QUERY_OPERATIONS)

#: Reads that return a completed/developing candle pair and share one
#: budget-trimming rule. ``candles`` is the timeframe-agnostic operation;
#: the other two are the H1/H4 compatibility aliases the trading domain
#: still exposes, named here from its own inventory rather than by hand.
_TRADING_CANDLE_SERIES_OPERATIONS = frozenset(
    {"candles", *COMPATIBILITY_READ_OPERATIONS}
)

#: The live execution-book read. Named from the package inventory rather
#: than by hand, so a host cannot serve an operation the domain does not
#: declare, or miss one it does.
_TRADING_EXPOSURE_OPERATIONS = frozenset(EXPOSURE_READ_OPERATIONS)

#: Bytes the transport adds after a gateway body returns: the fixed
#: capability envelope plus the refreshed ``response_bytes`` value.
_TRADING_RESPONSE_ENVELOPE_BYTES = (
    len(
        json.dumps(_PROCESS_CAPABILITY_METADATA, ensure_ascii=False).encode("utf-8")
    )
    + 32
)


def _bounded_trading_exposure_response(
    response: dict[str, Any], response_budget_bytes: int
) -> dict[str, Any]:
    """Trim the book to its budget without ever implying it is empty.

    Positions are dropped before orders, and the derived totals and the
    unprotected-ticket list always survive: a truncated snapshot that
    still reports twelve positions and three unprotected tickets is
    honest, while one trimmed to an empty list would read as flat.
    """
    result = response["result"]
    response["truncated"] = False
    response["has_more"] = False
    response["response_budget_bytes"] = response_budget_bytes
    # The transport merges a fixed capability envelope and refreshes
    # response_bytes after this returns, so the budget is reserved against
    # the delivered response rather than against the payload alone.
    limit_bytes = response_budget_bytes - _TRADING_RESPONSE_ENVELOPE_BYTES
    while (
        len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > limit_bytes
    ):
        if result.get("positions"):
            result["positions"].pop()
        elif result.get("pending_orders"):
            result["pending_orders"].pop()
        else:
            break
        response["truncated"] = True
        response["has_more"] = True
    result["returned_position_count"] = len(result.get("positions") or [])
    result["returned_pending_order_count"] = len(result.get("pending_orders") or [])
    response["response_bytes"] = len(
        json.dumps(response, ensure_ascii=False).encode("utf-8")
    )
    return response


#: Runtime-control actions that change trading runtime state. ``status`` is
#: deliberately absent: observing the runtime stays available even when the
#: owner has switched mutations off, so an unattended cycle can always
#: report what it found without being able to act on it.
_TRADING_RUNTIME_MUTATIONS = frozenset(
    {"start", "stop", "kill_switch_on", "kill_switch_off", "supervise_now", "analyze_now"}
)


def _resolved_trading_execution_mode(requested: str | None) -> str:
    return requested or get_config().trading.default_execution_mode


def _resolved_trading_policy_id(requested: str | None) -> str:
    return requested or get_config().trading.default_policy_id


def _resolved_trading_capability_role(
    requested: str | None, execution_mode: str
) -> str:
    """The role that matches the resolved mode, unless one was stated.

    A contradictory explicit pair never reaches here: the request model
    refuses it, because choosing for the caller would decide whether a real
    demo order is placed.
    """
    if requested is not None:
        return requested
    return (
        "broker_demo_agent"
        if execution_mode == "broker_demo"
        else "internal_paper_agent"
    )


def _trading_exposure_result(
    symbol: str, execution_mode: str
) -> dict[str, Any]:
    """The live execution book, projected without the journal.

    A broker-demo read opens the configured provider and re-verifies the
    demo account before answering; a paper read needs no provider. The
    derived totals travel with the snapshot because a supervising cycle
    asks the same questions of it every pass, and deriving them here means
    every caller derives them the same way.
    """
    provider = None
    try:
        if execution_mode == "broker_demo":
            provider = _configured_mt5_provider()
            _require_demo_provider(provider)
        executor = _trading_executor_for_mode(execution_mode, provider)
        exposure = _trading_services().broker_exposure(
            executor, symbol=symbol or None
        )
    finally:
        if provider is not None:
            provider.close()

    return {
        "mode": exposure.mode,
        "account_environment": exposure.account_environment,
        "symbol_filter": exposure.symbol_filter,
        "complete": exposure.complete,
        "observed_at_utc": exposure.observed_at_utc,
        "flat": exposure.flat,
        "position_count": exposure.position_count,
        "pending_order_count": exposure.pending_order_count,
        "open_volume_lots": exposure.open_volume_lots,
        "net_volume_lots": exposure.net_volume_lots,
        "unprotected_position_tickets": list(
            exposure.unprotected_position_tickets
        ),
        "positions": [
            {
                "ticket": position.ticket,
                "symbol": position.symbol,
                "direction": position.direction,
                "volume_lots": position.volume_lots,
                "entry_price": position.entry_price,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
                "current_price": position.current_price,
                "unrealized_profit": position.unrealized_profit,
                "opened_at_utc": position.opened_at_utc,
                "protected": position.protected,
            }
            for position in exposure.positions
        ],
        "pending_orders": [
            {
                "ticket": order.ticket,
                "symbol": order.symbol,
                "direction": order.direction,
                "volume_lots": order.volume_lots,
                "price": order.price,
                "order_kind": order.order_kind,
                "stop_loss": order.stop_loss,
                "take_profit": order.take_profit,
                "placed_at_utc": order.placed_at_utc,
                "expires_at_utc": order.expires_at_utc,
            }
            for order in exposure.pending_orders
        ],
        "exposure_authority": "execution_backend",
    }


def _trading_configuration_result() -> dict[str, Any]:
    """Report the settings the domain actually resolved, not Soma's copy.

    ``TradingLabSettings`` normalizes a configured alias like ``1H`` to its
    canonical period and validates the session calendar, so reading the
    resolved object back is the only honest answer to "what is in effect".
    The account environment is observed from the terminal and is therefore
    best effort: this read has to keep working while the terminal is down,
    which is exactly when a controller most needs to know its configuration.
    """
    config = get_config()
    trading = config.trading
    settings = _trading_services().settings
    timeframe = resolve_timeframe(settings.timeframe)
    calendar = resolve_calendar(settings.session_calendar)

    account_environment = ""
    account_environment_error = ""
    provider = None
    try:
        provider = _configured_mt5_provider()
        account_environment = str(provider.connect().account_environment or "")
    except Exception as exc:
        account_environment_error = str(exc)
    finally:
        if provider is not None:
            provider.close()

    return {
        "enabled": bool(trading.enabled),
        "provider": trading.provider,
        "symbol": settings.symbol,
        "configured_account_environment": trading.account_environment,
        "account_environment": account_environment,
        "account_environment_error": account_environment_error,
        "timeframe": timeframe.name,
        "timeframe_label": timeframe.label,
        "timeframe_seconds": timeframe.seconds,
        "candle_count": settings.candle_count,
        "session_calendar": calendar.name,
        "session_calendar_description": calendar.description,
        "boundary_probe_bars": settings.boundary_probe_bars,
        "maximum_tick_age_seconds": settings.maximum_tick_age_seconds,
        "provider_utc_offset_seconds": settings.provider_utc_offset_seconds,
        "default_execution_mode": trading.default_execution_mode,
        "default_policy_id": trading.default_policy_id,
        "runtime_control_mutations_enabled": bool(
            trading.runtime_control_mutations_enabled
        ),
        "supported_timeframes": list(SUPPORTED_TIMEFRAMES),
        "supported_session_calendars": list(SUPPORTED_SESSION_CALENDARS),
        "configuration_authority": "trading_lab.service:TradingLabSettings",
    }


def _trading_dir() -> Path:
    return trading_lab_adapter.trading_dir(get_config())


def _trading_signal_records_json(records: Any) -> list[dict[str, Any]]:
    return [_trading_json(record) for record in records]


def _trading_journal_query(request: Any) -> dict:
    """Journal-backed Trading Lab reads; no provider connection required.

    Every read is answered by the trading_lab services container. This
    function only shapes the public response: serialization, the compact
    payload elision, and the response envelope stay with Soma.
    """
    try:
        operation = request.operation
        lab = _trading_services()
        if operation == "market_packet_get":
            packet = lab.market_packet_get(request.packet_id)
            result: Any = _trading_json(packet)
            if request.view != "full":
                result.pop("payload", None)
        elif operation == "market_packet_list":
            page = lab.market_packet_list(
                limit=request.limit, offset=request.offset
            )
            listed = []
            for packet in page.packets:
                item = _trading_json(packet)
                item.pop("payload", None)
                listed.append(item)
            result = {
                "packets": listed,
                "total": page.total,
                "offset": page.offset,
            }
        elif operation == "outcome_get":
            result = _trading_json(lab.outcome_get(request.signal_id))
        elif operation == "outcome_list":
            page = lab.outcome_list(
                limit=request.limit,
                offset=request.offset,
                status=request.status,
                experiment_id=request.experiment_id,
            )
            result = {
                "outcomes": _trading_signal_records_json(page.outcomes),
                "total": page.total,
                "offset": page.offset,
            }
        elif operation == "rejection_list":
            page = lab.rejection_list(
                limit=request.limit, offset=request.offset
            )
            result = {
                "rejections": _trading_signal_records_json(page.rejections),
                "offset": page.offset,
            }
        elif operation == "data_quality":
            report = lab.data_quality(
                start_utc=request.start_utc,
                end_utc=request.end_utc,
                max_gap_seconds=request.max_gap_seconds,
            )
            result = {
                "symbol": report.symbol,
                "tick_count": report.tick_count,
                "range_hash": report.range_hash,
                "gaps": _trading_json(list(report.gaps)),
            }
        elif operation == "calibration_report":
            result = lab.calibration_report(
                experiment_id=request.experiment_id,
                period_start_utc=request.period_start_utc,
                period_end_utc=request.period_end_utc,
                period_basis=request.period_basis,
            )
        elif operation == "replay_report":
            result = lab.replay_report(
                experiment_id=request.experiment_id,
                threshold_start=request.threshold_start,
                threshold_end=request.threshold_end,
                allow_stacking=request.allow_stacking,
                fixed_notional_usd=request.fixed_notional_usd,
                per_trade_cost_usd=request.per_trade_cost_usd,
                initial_equity_usd=request.initial_equity_usd,
                minimum_sample=request.minimum_sample,
                period_start_utc=request.period_start_utc,
                period_end_utc=request.period_end_utc,
                period_basis=request.period_basis,
            )
        elif operation == "action_get":
            result = _trading_json(lab.action_get(request.action_id))
        elif operation == "action_list":
            page = lab.action_list(
                limit=request.limit,
                offset=request.offset,
                state=request.state,
                symbol=request.symbol,
            )
            result = {
                "actions": _trading_signal_records_json(page.actions),
                "total": page.total,
                "offset": page.offset,
            }
        elif operation == "companion_get":
            result = _trading_json(
                lab.companion_get(request.companion_run_id, sync=request.sync)
            )
        elif operation == "companion_list":
            page = lab.companion_list(limit=request.limit, offset=request.offset)
            result = {
                "runs": _trading_signal_records_json(page.runs),
                "total": page.total,
                "offset": page.offset,
            }
        elif operation == "runtime_status":
            report = lab.runtime_status_report(event_limit=20)
            result = {
                "status": _trading_json(report.status),
                "kill_switch": _trading_json(report.kill_switch),
                "recent_events": list(report.recent_events),
            }
        elif operation == "demo_performance":
            performance = lab.demo_performance(limit=request.limit)
            result = {
                "confirmed_demo_actions": _trading_signal_records_json(
                    performance.confirmed_demo_actions
                ),
                "count": performance.count,
            }
        else:  # reconciliation_report
            report = lab.reconciliation_report(
                limit=request.limit, offset=request.offset
            )
            result = {
                "reconciliations": _trading_signal_records_json(
                    report.reconciliations
                ),
                "offset": report.offset,
            }
        response = {
            "ok": True,
            "operation": operation,
            "result": result,
        }
        if request.view == "full":
            return response
        return _bounded_trading_scalar_response(
            response, request.response_budget_bytes
        )
    except KeyError as exc:
        return {"ok": False, "status": "not_found", "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "status": "journal_error", "error": str(exc)}


def _signal_record_json(record: Any) -> dict[str, Any]:
    return _trading_json(record)


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def trading_signal_submit(request: TradingSignalSubmitRequest) -> dict:
    """Submit one immutable packet-bound demo Trading Lab signal."""
    if not get_config().trading.enabled:
        return {"ok": False, "status": "disabled", "error": "Trading is disabled"}
    submission = SignalSubmissionV2(
        packet_id=request.packet_id,
        decision=SignalDecisionV2(request.decision),
        confidence=request.confidence,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        reason=request.reason,
        news_context=request.news_context,
        model_version=request.model_version,
        prompt_version=request.prompt_version,
        policy_id=_resolved_trading_policy_id(request.policy_id),
        execution_mode=_resolved_trading_execution_mode(request.execution_mode),
        experiment_id=request.experiment_id,
        submitted_at_utc=datetime.now(timezone.utc),
    )
    try:
        record = _trading_services().signal_submit(
            request.idempotency_key, submission
        )
    except SignalRejectedError as exc:
        return {
            "ok": False,
            "status": "rejected",
            "rejection": _trading_json(exc.rejection),
        }
    signal = _signal_record_json(record)
    if request.view == "full":
        return {"ok": True, "signal": signal}
    return _compact_trading_signal_response(signal, request.response_budget_bytes)


def _compact_trading_signal_response(signal: dict[str, Any], response_budget_bytes: int) -> dict:
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    signal = dict(signal)
    for field in ("reason", "news_context"):
        if field in signal:
            signal[field] = str(signal[field])[:512]
    response = apply_compact_projection_envelope(
        {
            "ok": True,
            "signal": signal,
            "truncated": False,
            "has_more": False,
            "response_budget_bytes": response_budget_bytes,
        }
    )
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > response_budget_bytes:
        reduced = False
        for field in ("news_context", "reason"):
            value = response["signal"].get(field, "")
            if value:
                next_value = value[: max(0, len(value) - 128)]
                response["signal"][field] = next_value
                reduced = next_value != value
                if reduced:
                    break
        if not reduced:
            break
        response["truncated"] = True
        response["has_more"] = True
    response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    return response


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def trading_signal_get(request: TradingSignalGetRequest) -> dict:
    """Read one immutable Trading Lab signal."""
    signal = _signal_record_json(
        _trading_services().signal_get(request.signal_id)
    )
    if request.view == "full":
        return {"ok": True, "signal": signal}
    return _compact_trading_signal_response(signal, request.response_budget_bytes)


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def trading_signal_list(request: TradingSignalListRequest) -> dict:
    """Paginated read over the complete immutable signal journal."""
    if request.response_budget_bytes < 1024 or request.response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    page = _trading_services().signal_list(
        limit=request.limit,
        offset=request.offset,
        status=request.status,
        experiment_id=request.experiment_id,
    )
    total = page.total
    signals = [_signal_record_json(record) for record in page.signals]
    if request.view == "full":
        return {
            "ok": True,
            "signals": signals,
            "total": total,
            "offset": request.offset,
        }
    response = apply_compact_projection_envelope(
        {
            "ok": True,
            "signals": signals,
            "total": total,
            "offset": request.offset,
            "truncated": False,
            "has_more": request.offset + len(signals) < total,
            "response_budget_bytes": request.response_budget_bytes,
        }
    )
    while len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > request.response_budget_bytes:
        if not response["signals"]:
            break
        response["signals"].pop()
        response["truncated"] = True
        response["has_more"] = True
    response["response_bytes"] = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    return response


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def trading_signal_cancel_before_entry(request: TradingSignalCancelRequest) -> dict:
    """Cancel one submitted signal before entry without editing its payload."""
    record = _trading_services().signal_cancel_before_entry(
        request.signal_id, request.reason
    )
    signal = _signal_record_json(record)
    if request.view == "full":
        return {"ok": True, "signal": signal}
    return _compact_trading_signal_response(signal, request.response_budget_bytes)


def _trading_executor_for_mode(mode: str, provider: Any | None):
    return trading_lab_adapter.executor_for_mode(
        get_config(), mode, provider
    )


def _require_demo_provider(provider: Any) -> Any:
    health = provider.connect()
    if not health.connected:
        raise RuntimeError("MT5 terminal is disconnected")
    if health.account_environment != "demo":
        raise RuntimeError("MT5 account is not a demo account")
    return health


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def trading_companion_action(request: TradingCompanionActionRequest) -> dict:
    """Run one strict scheduled Trading Lab companion step.

    Start binds research to a fresh packet; decide stores a packet-bound signal;
    review stores ChatGPT's second-pass decision; execute derives every trade
    fact from the approved immutable signal and accepts only volume.
    """
    if not get_config().trading.enabled:
        return {"ok": False, "status": "disabled", "error": "Trading is disabled"}

    lab = _trading_services()
    provider = None
    try:
        if request.action == "start":
            provider = _configured_mt5_provider()
            _require_demo_provider(provider)
            started = lab.companion_start(
                provider,
                idempotency_key=request.idempotency_key,
                task_invocation_id=request.task_invocation_id,
                research_summary=request.research_summary,
                research_sources=tuple(
                    ResearchSource(
                        title=source.title,
                        reference=source.reference,
                        published_at_utc=source.published_at_utc,
                    )
                    for source in request.research_sources
                ),
                scheduled_for_utc=request.scheduled_for_utc,
                now=datetime.now(timezone.utc),
                completed_count=(
                    request.completed_count
                    if request.completed_count is not None
                    else get_config().trading.candle_count
                ),
                timeframe=request.timeframe,
            )
            response = {
                "ok": True,
                "action": request.action,
                "run": _trading_json(started.run),
                "packet": _trading_json(started.packet),
            }
        elif request.action == "decide":
            decided = lab.companion_decide(
                request.companion_run_id,
                request.signal_idempotency_key,
                decision=SignalDecisionV2(request.decision),
                confidence=request.confidence,
                stop_loss=request.stop_loss,
                take_profit=request.take_profit,
                reason=request.reason,
                news_context=request.news_context,
                model_version=request.model_version,
                prompt_version=request.prompt_version,
                policy_id=_resolved_trading_policy_id(request.policy_id),
                execution_mode=_resolved_trading_execution_mode(
                    request.execution_mode
                ),
                experiment_id=request.experiment_id,
                submitted_at_utc=request.submitted_at_utc,
            )
            response = {
                "ok": True,
                "action": request.action,
                "run": _trading_json(decided.run),
                "signal": _trading_json(decided.signal),
            }
        elif request.action == "review":
            reviewed = lab.companion_approve(
                request.companion_run_id,
                request.approval_idempotency_key,
                decision=ModelApprovalDecision(request.decision),
                reason=request.reason,
                model_version=request.model_version,
                prompt_version=request.prompt_version,
                approved_at_utc=request.approved_at_utc,
            )
            response = {
                "ok": True,
                "action": request.action,
                "run": _trading_json(reviewed.run),
                "signal": _trading_json(reviewed.signal),
            }
        else:
            run = lab.companion_get(request.companion_run_id)
            if run.signal_id is None:
                raise RuntimeError("companion cycle has no directional signal")
            signal = lab.signal_get(run.signal_id)
            mode = TradingExecutionMode(signal.execution_mode)
            role = TradingCapabilityRole(
                "broker_demo_agent"
                if mode is TradingExecutionMode.BROKER_DEMO
                else "internal_paper_agent"
            )
            if mode is TradingExecutionMode.BROKER_DEMO:
                provider = _configured_mt5_provider()
                _require_demo_provider(provider)
            executor = _trading_executor_for_mode(mode.value, provider)
            executed = lab.companion_execute(
                request.companion_run_id,
                TradingActionRequest(
                    idempotency_key=request.idempotency_key,
                    action_type=TradingActionType.MARKET_ENTRY,
                    origin="model",
                    capability_role=role,
                    execution_mode=mode,
                    policy_id=signal.policy_id,
                    experiment_id=signal.experiment_id,
                    symbol=signal.symbol,
                    signal_id=signal.signal_id,
                    direction=signal.decision.value,
                    volume_lots=request.volume_lots,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                ),
                executor,
            )
            response = {
                "ok": executed.action.state
                in (ActionState.RECONCILED, ActionState.BROKER_CONFIRMED),
                "action": request.action,
                "run": _trading_json(executed.run),
                "trading_action": _trading_json(executed.action),
            }
        if request.view == "full":
            return response
        return _bounded_trading_scalar_response(
            response, request.response_budget_bytes
        )
    except SignalRejectedError as exc:
        return {
            "ok": False,
            "status": "rejected",
            "rejection": _trading_json(exc.rejection),
        }
    except KeyError as exc:
        return {"ok": False, "status": "not_found", "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "status": "companion_error", "error": str(exc)}
    finally:
        if provider is not None:
            provider.close()


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def trading_action_submit(request: TradingActionSubmitRequest) -> dict:
    """One guarded model trading action through the full gateway pipeline:
    validation, policies, fresh price, normalization, risk, margin,
    order_check, idempotent durable submission, broker reconciliation.
    Demo-only; raw order_send is unreachable."""
    if not get_config().trading.enabled:
        return {"ok": False, "status": "disabled", "error": "Trading is disabled"}
    execution_mode = _resolved_trading_execution_mode(request.execution_mode)
    capability_role = _resolved_trading_capability_role(
        request.capability_role, execution_mode
    )
    action_request = TradingActionRequest(
        idempotency_key=request.idempotency_key,
        action_type=TradingActionType(request.action_type),
        origin="model",
        capability_role=TradingCapabilityRole(capability_role),
        execution_mode=TradingExecutionMode(execution_mode),
        policy_id=_resolved_trading_policy_id(request.policy_id),
        experiment_id=request.experiment_id,
        symbol=request.symbol,
        signal_id=request.signal_id,
        direction=request.direction,
        volume_lots=request.volume_lots,
        price=request.price,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        position_ticket=request.position_ticket,
        order_ticket=request.order_ticket,
        params=dict(request.params),
    )
    provider = None
    try:
        if execution_mode == "broker_demo":
            provider = _configured_mt5_provider()
            _require_demo_provider(provider)
        executor = _trading_executor_for_mode(execution_mode, provider)
        record = _trading_services().action_submit(action_request, executor)
    except Exception as exc:
        return {"ok": False, "status": "gateway_error", "error": str(exc)}
    finally:
        if provider is not None:
            provider.close()
    response = {
        "ok": record.state
        in (ActionState.RECONCILED, ActionState.BROKER_CONFIRMED),
        "action": _trading_json(record),
    }
    if request.view == "full":
        return response
    return _bounded_trading_scalar_response(
        response, request.response_budget_bytes
    )


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def trading_runtime_control(request: TradingRuntimeControlRequest) -> dict:
    """Start/stop/status, kill switch, and manual runtime passes."""
    trading = get_config().trading
    if not trading.enabled:
        return {"ok": False, "status": "disabled", "error": "Trading is disabled"}
    if (
        request.action in _TRADING_RUNTIME_MUTATIONS
        and not trading.runtime_control_mutations_enabled
    ):
        # Reporting the reachable action keeps a caller that wanted to look
        # at the runtime from concluding the runtime itself is broken.
        return {
            "ok": False,
            "status": "runtime_control_disabled",
            "action": request.action,
            "error": (
                "Trading runtime control mutations are disabled by "
                "configuration; runtime status remains readable"
            ),
            "available_actions": ["status"],
        }
    lab = _trading_services()
    now = datetime.now(timezone.utc)
    provider = None
    try:
        if request.action == "start":
            result: Any = _trading_json(lab.runtime_start(now=now))
        elif request.action == "stop":
            result = _trading_json(lab.runtime_stop(request.reason, now=now))
        elif request.action == "status":
            status = lab.runtime_status()
            result = {
                "status": _trading_json(status.status),
                "kill_switch": _trading_json(status.kill_switch),
            }
        elif request.action == "kill_switch_on":
            result = _trading_json(
                lab.kill_switch_on(request.reason, at_utc=now)
            )
        elif request.action == "kill_switch_off":
            result = _trading_json(
                lab.kill_switch_off(request.reason, at_utc=now)
            )
        else:
            provider = _configured_mt5_provider()
            health = provider.connect()
            if not health.connected:
                return {
                    "ok": False,
                    "status": "disconnected",
                    "error": "MT5 terminal is disconnected",
                    "health": redact_health(health),
                }
            if health.account_environment != "demo":
                return {
                    "ok": False,
                    "status": "wrong_environment",
                    "error": "MT5 account is not a demo account",
                    "health": redact_health(health),
                }
            executor = _trading_executor_for_mode(
                request.execution_mode, provider
            )
            if request.action == "supervise_now":
                result = _trading_json(
                    lab.supervise_now(provider, executor, now=now)
                )
            else:
                result = _trading_json(
                    lab.analyze_now(provider, executor, now=now)
                )
    except Exception as exc:
        return {"ok": False, "status": "runtime_error", "error": str(exc)}
    finally:
        if provider is not None:
            provider.close()
    response = {"ok": True, "action": request.action, "result": result}
    if request.view == "full":
        return response
    return _bounded_trading_scalar_response(
        response, request.response_budget_bytes
    )


@_internal_tool(output_schema=LIST_REPO_FILES_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def list_repo_files(
    repo_name: str,
    directory: str = "",
    max_results: int = 500,
    view: str = "full",
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: list files in a repository directory. Returns repo-relative POSIX paths only."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if max_results < 1 or max_results > 5_000:
        raise ValueError("max_results must be between 1 and 5000")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.list_repo_files(
        repo_root, directory=directory, max_results=max_results
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    if view == "full":
        return result
    files = list(result.get("files") or [])
    compact = {
        "ok": result.get("ok", False),
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "repo_name": result.get("repo_name", canonical_name),
        "directory": result.get("directory", directory),
        "files": files,
        "count": len(files),
        "total_count": result.get("count", len(files)),
        "truncated": bool(result.get("truncated", False)),
        "has_more": bool(result.get("truncated", False)),
        "response_budget_bytes": response_budget_bytes,
        "error": result.get("error", ""),
    }
    if "requested_repo_name" in result:
        compact["requested_repo_name"] = result["requested_repo_name"]
    while len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > response_budget_bytes and compact["files"]:
        compact["files"].pop()
        compact["truncated"] = True
        compact["has_more"] = True
    compact["count"] = len(compact["files"])
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact
    return result


@_internal_tool(output_schema=READ_REPO_FILE_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
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


@_internal_tool(output_schema=SEARCH_REPO_TEXT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def search_repo_text(
    repo_name: str,
    query: str,
    directory: str = "",
    max_results: int = 50,
    case_sensitive: bool = False,
    file_patterns: list[str] | None = None,
    budget_ms: int = 5_000,
    file_path: str = "",
    cursor: str = "",
    response_budget_bytes: int | None = _repo_reader.DEFAULT_SEARCH_RESPONSE_BYTES,
) -> dict:
    """Read-only: search for a literal string in repository text files. Returns path, line, and redacted snippets."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.search_repo_text(
        repo_root,
        query,
        directory=directory,
        max_results=max_results,
        case_sensitive=case_sensitive,
        file_patterns=file_patterns,
        budget_ms=budget_ms,
        file_path=file_path,
        cursor=cursor,
        response_budget_bytes=response_budget_bytes,
    )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@_internal_tool(
    output_schema=RECENTLY_MODIFIED_FILES_OUTPUT, annotations=READ_ONLY_ANNOTATIONS
)
def get_recently_modified_files(
    repo_name: str,
    limit: int = 50,
    view: str = "full",
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: list files sorted by filesystem mtime, newest first. Reflects unsaved changes immediately."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.get_recently_modified_files(repo_root, limit=limit)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    if view == "full":
        return result
    files = list(result.get("files") or [])
    compact = {
        "ok": result.get("ok", False),
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "repo_name": result.get("repo_name", canonical_name),
        "files": files,
        "count": len(files),
        "total_count": result.get("count", len(files)),
        "truncated": False,
        "has_more": False,
        "response_budget_bytes": response_budget_bytes,
        "error": result.get("error", ""),
    }
    if "requested_repo_name" in result:
        compact["requested_repo_name"] = result["requested_repo_name"]
    while len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > response_budget_bytes and compact["files"]:
        compact["files"].pop()
        compact["truncated"] = True
        compact["has_more"] = True
    compact["count"] = len(compact["files"])
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact
    return result


@_internal_tool(output_schema=REPO_GIT_STATUS_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def repo_git_status(repo_name: str) -> dict:
    """Read-only: return raw git status --short --branch output for a whitelisted repository."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    started = time.monotonic()
    try:
        status_text = git_status(repo_root)
        result = {
            "ok": True,
            "repo_name": canonical_name,
            "status": status_text,
            "fresh": True,
            "source": "live_git",
            "generated_at": time.time(),
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "recommended_action": "",
            "error": "",
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "repo_name": canonical_name,
            "status": "timed_out",
            "fresh": False,
            "source": "live_git",
            "generated_at": time.time(),
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "recommended_action": "Retry the live repository-status check; do not use a cached snapshot.",
            "error": str(exc),
        }
    except Exception as exc:
        result = {
            "ok": False,
            "repo_name": canonical_name,
            "status": "failed",
            "fresh": False,
            "source": "live_git",
            "generated_at": time.time(),
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "recommended_action": "Retry the live repository-status check; do not use a cached snapshot.",
            "error": str(exc),
        }
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@_internal_tool(output_schema=REPO_GIT_DIFF_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def repo_git_diff(
    repo_name: str,
    path: str = "",
    staged: bool = False,
    view: str = "legacy",
    snapshot_id: str = "",
    hunk_id: str = "",
    response_budget_bytes: int = 32 * 1024,
) -> dict:
    """Read-only: return git diff output, optionally scoped to one validated relative path or the staging area."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    if view == "legacy":
        result = _git_diff_raw(repo_root, path=path, staged=staged)
    else:
        result = _git_diff_snapshot(
            repo_root,
            path=path,
            staged=staged,
            view=view,
            snapshot_id=snapshot_id,
            hunk_id=hunk_id,
            response_budget_bytes=response_budget_bytes,
        )
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@_internal_tool(output_schema=COMMIT_RANGE_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def inspect_commit_range(repo_name: str, base_commit: str, head_commit: str) -> dict:
    """Read-only: inspect an exact commit range using only two full commit hashes."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _inspect_commit_range(repo_root, base_commit, head_commit)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


def _bounded_commit_range_response(result: dict[str, Any], budget: int) -> dict[str, Any]:
    if budget < 1024 or budget > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact = {
        key: result[key]
        for key in (
            "ok", "repo_name", "requested_repo_name", "base_commit", "head_commit", "error"
        )
        if key in result
    }
    compact["name_status_count"] = len(
        [line for line in str(result.get("name_status") or "").splitlines() if line]
    )
    compact["diff_stat"] = str(result.get("diff_stat") or "")[:2048]
    compact["diff_bytes"] = len(str(result.get("diff") or "").encode("utf-8"))
    compact["truncated"] = bool(result.get("diff") or result.get("name_status"))
    compact["has_more"] = compact["truncated"]
    compact["response_budget_bytes"] = budget
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


def _get_runs_dir() -> "Path":
    return get_config().resolve_runs_dir()


@_internal_tool(output_schema=PREVIEW_PATCH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def preview_repo_patch(
    repo_name: str,
    operations: list[dict],
    commit_title: str = "",
    commit_description: str = "",
) -> dict:
    """Read-only: validate patch operations and return a unified diff with a patch_id. Makes no changes."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    if commit_title or commit_description:
        result = _repo_writer.preview_repo_patch(
            repo_root,
            operations,
            _get_runs_dir(),
            commit_title=commit_title,
            commit_description=commit_description,
        )
    else:
        result = _repo_writer.preview_repo_patch(repo_root, operations, _get_runs_dir())
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@_internal_tool(output_schema=PREVIEW_PATCH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
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


@_internal_tool(output_schema=PREVIEW_PATCH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
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


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def get_patch_status(
    repo_name: str,
    patch_id: str,
    view: str = "full",
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: return the durable lifecycle state for one managed patch."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_writer.get_patch_status(repo_root, patch_id, _get_runs_dir())
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    if view == "full":
        return result
    changed_files = list(result.get("changed_files") or [])
    errors = list(result.get("errors") or [])
    apply_result = result.get("apply_result")
    compact = {
        "ok": result.get("ok", False),
        "repo_name": result.get("repo_name", canonical_name),
        "patch_id": result.get("patch_id", patch_id),
        "status": result.get("status", "unknown"),
        "created_at": result.get("created_at", ""),
        "applied_at": result.get("applied_at", ""),
        "reverted_at": result.get("reverted_at", ""),
        "changed_files": changed_files,
        "changed_file_count": len(changed_files),
        "error_count": len(errors),
        "apply_ok": bool(apply_result.get("ok")) if isinstance(apply_result, dict) else False,
        "truncated": False,
        "has_more": False,
        "response_budget_bytes": response_budget_bytes,
        "error": result.get("error", ""),
    }
    if "requested_repo_name" in result:
        compact["requested_repo_name"] = result["requested_repo_name"]
    while len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > response_budget_bytes and compact["changed_files"]:
        compact["changed_files"].pop()
        compact["truncated"] = True
        compact["has_more"] = True
    compact["changed_file_count"] = len(compact["changed_files"])
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
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


@_internal_tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@_internal_tool(output_schema=APPLY_PATCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@_internal_tool(output_schema=APPLY_PATCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@_internal_tool(output_schema=CREATE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
def create_repo_file(repo_name: str, path: str, content: str) -> dict:
    """Write tool: create a new file in the repository. Rejects existing files and applies all path/content safety checks."""
    return _locked_repo_operation(
        repo_name,
        "create_repo_file",
        {"path": path, "content_sha256": _repo_writer._sha256_text(content)},
        lambda repo_root: _repo_writer.create_repo_file(repo_root, path, content),
        finalize_commit=True,
    )


@_internal_tool(output_schema=DELETE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@_internal_tool(output_schema=MOVE_FILE_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@_internal_tool(output_schema=REVERT_PATCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@_internal_tool(output_schema=GIT_LOG_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def git_log(
    repo_name: str,
    limit: int = 20,
    path: str = "",
    view: str = "full",
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    """Read-only: return structured git log entries, optionally scoped to a file path."""
    if view not in {"compact", "full"}:
        raise ValueError("view must be compact or full")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if response_budget_bytes < 1024 or response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.git_log(repo_root, limit=limit, path=path)
    result["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    if view == "full":
        return result
    commits = list(result.get("commits") or [])
    compact = {
        "ok": result.get("ok", False),
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "repo_name": result.get("repo_name", canonical_name),
        "path": result.get("path", path),
        "commits": commits,
        "count": len(commits),
        "total_count": result.get("count", len(commits)),
        "truncated": False,
        "has_more": False,
        "response_budget_bytes": response_budget_bytes,
        "error": result.get("error", ""),
    }
    if "requested_repo_name" in result:
        compact["requested_repo_name"] = result["requested_repo_name"]
    while len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > response_budget_bytes and compact["commits"]:
        compact["commits"].pop()
        compact["truncated"] = True
        compact["has_more"] = True
    compact["count"] = len(compact["commits"])
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact
    return result


@_internal_tool(output_schema=READ_REPO_FILES_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def read_repo_files(
    repo_name: str, requests: list[dict], response_budget_bytes: int = 48 * 1024
) -> dict:
    """Read-only: return bounded streaming file windows with hash-bound continuation."""
    canonical_name, repo_root, requested_name = _repo_context(repo_name)
    result = _repo_reader.read_repo_files(
        repo_root, requests, response_budget_bytes=response_budget_bytes
    )
    result["repo_name"] = canonical_name
    for item in result.get("results", []):
        item["repo_name"] = canonical_name
    if requested_name != canonical_name:
        result["requested_repo_name"] = requested_name
    return result


@_internal_tool(output_schema=CREATE_BRANCH_OUTPUT, annotations=WRITE_ANNOTATIONS)
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


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def repo_query(request: RepoQueryRequest) -> dict:
    """Read-only gateway for bounded repository inspection and patch lifecycle status."""
    try:
        _repo_context(request.repo_name)
    except ValueError as exc:
        return {
            "ok": False,
            "repo_name": request.repo_name,
            "status": "invalid_repo_resolution",
            "error": str(exc),
        }
    if request.operation == "status":
        return inspect_repo_status(
            request.repo_name,
            request.view,
            request.response_budget_bytes,
        )
    if request.operation == "compact_status":
        return inspect_repo_status_compact(
            request.repo_name,
            request.response_budget_bytes,
        )
    if request.operation == "patch_status":
        return get_patch_status(
            request.repo_name,
            request.patch_id,
            request.view,
            request.response_budget_bytes,
        )
    if request.operation == "list_files":
        return list_repo_files(
            request.repo_name,
            request.directory,
            request.max_results,
            request.view,
            request.response_budget_bytes,
        )
    if request.operation == "read_files":
        return read_repo_files(
            request.repo_name, request.requests, request.response_budget_bytes
        )
    if request.operation == "search_text":
        return search_repo_text(
            request.repo_name,
            request.query,
            request.directory,
            request.max_results,
            request.case_sensitive,
            request.file_patterns,
            request.budget_ms,
            request.file_path,
            request.cursor,
            request.response_budget_bytes,
        )
    if request.operation == "recent_files":
        return get_recently_modified_files(
            request.repo_name,
            request.limit,
            request.view,
            request.response_budget_bytes,
        )
    if request.operation == "diff":
        return repo_git_diff(
            request.repo_name,
            request.path,
            request.staged,
            request.view,
            request.snapshot_id,
            request.hunk_id,
            request.response_budget_bytes,
        )
    if request.operation == "log":
        return git_log(
            request.repo_name,
            request.limit,
            request.path,
            request.view,
            request.response_budget_bytes,
        )
    result = inspect_commit_range(request.repo_name, request.base_commit, request.head_commit)
    if request.view == "full":
        return result
    return _bounded_commit_range_response(result, request.response_budget_bytes)


def _bounded_repo_preview_response(result: dict[str, Any], budget: int) -> dict[str, Any]:
    if budget < 1024 or budget > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact = {
        key: result[key]
        for key in (
            "ok", "operation", "patch_id", "cleanup_id", "repo_name", "requested_repo_name",
            "git_head", "changed_lines", "logical_changed_lines",
            "newline_only_changed_lines", "changed_bytes", "commit_title",
            "error",
        )
        if key in result
    }
    for key in ("error", "commit_title"):
        if compact.get(key):
            compact[key] = str(compact[key])[:512]
    compact["changed_file_count"] = len(result.get("changed_files") or [])
    compact["validation_error_count"] = len(result.get("validation_errors") or [])
    compact["warning_count"] = len(result.get("warnings") or [])
    compact["newline_diagnostic_count"] = len(result.get("newline_diagnostics") or [])
    compact["diff_bytes"] = len(str(result.get("diff") or "").encode("utf-8"))
    compact["truncated"] = bool(
        result.get("diff")
        or result.get("changed_files")
        or result.get("validation_errors")
        or result.get("warnings")
        or result.get("newline_diagnostics")
    )
    compact["has_more"] = compact["truncated"]
    compact["response_budget_bytes"] = budget
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
def repo_preview(request: RepoPreviewRequest) -> dict:
    """Read-only gateway that produces opaque managed repository change previews."""
    if request.operation == "patch":
        result = preview_repo_patch(
            request.repo_name,
            request.operations,
            request.commit_title,
            request.commit_description,
        )
    elif request.operation == "create_file":
        result = preview_repo_file_creation(request.repo_name, request.path, request.content)
    elif request.operation == "remove_file":
        result = preview_repo_file_removal(
            request.repo_name, request.path, request.expected_sha256
        )
    else:
        result = preview_managed_artifact_cleanup(request.repo_name, request.roots)
    if request.view == "full":
        return result
    return _bounded_repo_preview_response(result, request.response_budget_bytes)


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def repo_apply(request: RepoApplyRequest) -> dict:
    """Write gateway for hash-verified preview application, cleanup, rollback, and moves."""
    payload = request.model_dump(exclude={"operation", "repo_name"})
    response = get_job_manager().start_repo_apply(
        request.repo_name, request.operation, payload
    )
    ack = {
        "ok": bool(response.get("accepted")),
        "accepted": bool(response.get("accepted")),
        "status": response.get("status", "refused"),
        "operation": request.operation,
        "repo_name": response.get("repo_name", request.repo_name),
        "transaction_id": response.get("run_id", ""),
        "run_id": response.get("run_id", ""),
        "patch_id": getattr(request, "patch_id", ""),
        "cleanup_id": getattr(request, "cleanup_id", ""),
        "polling": {
            "tool": "run_query",
            "request": {
                "operation": "control",
                "run_id": response.get("run_id", ""),
            },
        },
        "evidence": {
            "tool": "run_query",
            "request": {
                "operation": "terminal",
                "run_id": response.get("run_id", ""),
            },
        },
        "reason": response.get("reason", ""),
        "duplicate": bool(response.get("duplicate", False)),
        "error": response.get("error", ""),
    }
    return _bounded_preflight_response(
        {
            "locks": [],
            "runs": {"running": [], "queued": [], "launch_pending": []},
            "tracked_worktree": {"files": []},
            **ack,
        },
        budget=4 * 1024,
    )


@mcp.tool(output_schema=GENERIC_OBJECT_OUTPUT, annotations=WRITE_ANNOTATIONS)
def repo_commit(request: RepoCommitRequest) -> dict:
    """Write gateway for protected local branch creation and selected-file commits only."""
    if request.operation == "create_branch":
        result = create_git_branch(request.repo_name, request.branch_name)
    else:
        result = commit_selected_files(
            request.repo_name, request.files, request.title, request.description
        )
    if request.view == "full":
        return result
    if request.response_budget_bytes < 1024 or request.response_budget_bytes > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact = apply_compact_projection_envelope(
        {
            key: result[key]
            for key in (
                "ok",
                "operation",
                "status",
                "repo_name",
                "branch_name",
                "commit_hash",
                "commit_attempted",
                "commit_metadata_sha256",
                "error",
                "message",
            )
            if key in result
        }
    )
    compact["changed_files"] = [str(path) for path in result.get("changed_files", [])]
    compact["truncated"] = False
    compact["has_more"] = False
    compact["response_budget_bytes"] = request.response_budget_bytes
    while len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > request.response_budget_bytes:
        if compact["changed_files"]:
            compact["changed_files"].pop()
            compact["truncated"] = True
            compact["has_more"] = True
            continue
        for key in ("message", "error"):
            if compact.get(key):
                compact[key] = str(compact[key])[:128]
                compact["truncated"] = True
                compact["has_more"] = True
                break
        else:
            break
    compact["response_bytes"] = len(json.dumps(compact, ensure_ascii=False).encode("utf-8"))
    return compact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Soma MCP server.")
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


def _reload_ssh_activation_config(config_path: Path) -> dict[str, Any]:
    result = _reload_service(config_path, modules=["config"])
    if result.get("ok"):
        set_config(apply_reloaded_config(config_path), config_path)
    return {
        "ok": bool(result.get("ok")),
        "status": str(result.get("status") or ""),
        "error": str(result.get("error") or ""),
    }


def _reconcile_ssh_activation_once(config_path: Path) -> list[dict[str, Any]]:
    return _reconcile_pending_ssh_activations(
        config_path,
        get_config().resolve_runs_dir(),
        reload_callback=_reload_ssh_activation_config,
    )


def _ssh_activation_coordinator_loop(
    config_path: Path,
    stop_event: threading.Event,
) -> None:
    runs_dir = get_config().resolve_runs_dir()
    last_ok: bool | None = None
    while not stop_event.is_set():
        try:
            _reconcile_ssh_activation_once(config_path)
            failure = None
        except Exception as exc:
            failure = exc
        # The loop runs continuously, so only state changes are recorded. A
        # recurring failure must still be visible, and a recovery must clear it.
        if (failure is None) != last_ok:
            last_ok = failure is None
            try:
                reconciliation_status.resolve(
                    runs_dir,
                    reconciliation_status.PATH_SSH_ACTIVATION_COORDINATOR,
                    ok=failure is None,
                    detail=""
                    if failure is None
                    else f"{type(failure).__name__}: {failure}",
                    exception_type="" if failure is None else type(failure).__name__,
                    process_id=os.getpid(),
                )
            except Exception:
                pass
        stop_event.wait(0.25)


def run_server(args: argparse.Namespace) -> None:
    config_path = Path(args.config).resolve()
    set_config(load_config(config_path), config_path)
    runs_dir = get_config().resolve_runs_dir()
    process_id = os.getpid()
    with reconciliation_status.ReconciliationRecorder(
        runs_dir, reconciliation_status.PATH_SSH_ACTIVATION, process_id=process_id
    ):
        _reconcile_ssh_activation_once(config_path)
    coordinator_stop = threading.Event()
    coordinator = threading.Thread(
        target=_ssh_activation_coordinator_loop,
        args=(config_path, coordinator_stop),
        name="soma-ssh-activation-coordinator",
        daemon=True,
    )
    coordinator.start()
    try:
        # A reconciliation failure means recovery information was lost for that
        # subsystem. Startup continues so one broken subsystem cannot make the
        # service unreachable, but the failure is durable and readiness reports
        # it rather than the service appearing healthy.
        with reconciliation_status.ReconciliationRecorder(
            runs_dir, reconciliation_status.PATH_JOB_RUNS, process_id=process_id
        ):
            get_job_manager().reconcile_startup()
        with reconciliation_status.ReconciliationRecorder(
            runs_dir, reconciliation_status.PATH_WORKFLOWS, process_id=process_id
        ):
            get_workflow_manager().reconcile_startup()
        with reconciliation_status.ReconciliationRecorder(
            runs_dir,
            reconciliation_status.PATH_PROJECT_SCOPE,
            process_id=process_id,
        ):
            get_project_scope_store().reconcile_startup()
        with reconciliation_status.ReconciliationRecorder(
            runs_dir, reconciliation_status.PATH_TASKS, process_id=process_id
        ):
            get_task_manager().reconcile_startup()
        # Every registry accessor is async, so the effective contract identity
        # is computed once here -- after all registration, before serving --
        # and stamped synchronously on responses thereafter.
        refresh_public_contract_hash()
        if args.transport == "stdio":
            mcp.run(transport="stdio")
            return
        mcp.run(transport=args.transport, host=args.host, port=args.port, path=args.path)
    finally:
        coordinator_stop.set()
        coordinator.join(timeout=2.0)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    run_server(args)


if __name__ == "__main__":
    main()
