from __future__ import annotations

import json
import sys
from functools import wraps
from typing import Any, Callable

from .capabilities import capability_metadata
from .gateway_models import KnowledgeActionRequest, KnowledgeQueryRequest
from .public_projection_contract import (
    apply_compact_projection_envelope,
    public_projection_schema_properties,
)


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

WIKI_REFRESH_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **public_projection_schema_properties(),
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "status": {"type": "string"},
        "wiki_root": {"type": "string"},
        "pages": {"type": "array", "items": {"type": "string"}},
        "source_file_count": {"type": "integer"},
        "changed_source_files": {"type": "array", "items": {"type": "string"}},
        "scan_truncated": {"type": "boolean"},
        "stale": {"type": "boolean"},
        "generation_id": {"type": "string"},
        "indexed_head": {"type": "string"},
        "indexed_branch": {"type": "string"},
        "source_generation": {"type": "integer"},
        "indexed_source_generation": {"type": "integer"},
        "incremental": {"type": "boolean"},
        "refresh_operation_id": {"type": "string"},
        "server_build_hash": {"type": "string"},
        "schema_hash": {"type": "string"},
        "capability_epoch": {"type": "string"},
        "error": {"type": "string"},
        "truncated": {"type": "boolean"},
        "has_more": {"type": "boolean"},
        "response_budget_bytes": {"type": "integer"},
        "response_bytes": {"type": "integer"},
        "page_count": {"type": "integer"},
        "changed_source_file_count": {"type": "integer"},
    },
    "required": [
        "ok",
        "repo_name",
        "status",
        "wiki_root",
        "pages",
        "source_file_count",
        "changed_source_files",
        "scan_truncated",
        "error",
    ],
}
WIKI_PAGE_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **public_projection_schema_properties(),
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "status": {"type": "string"},
        "page": {"type": "string"},
        "content": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "truncated": {"type": "boolean"},
        "has_more": {"type": "boolean"},
        "response_budget_bytes": {"type": "integer"},
        "response_bytes": {"type": "integer"},
        "page_count": {"type": "integer"},
        "changed_source_file_count": {"type": "integer"},
        "generation_id": {"type": "string"},
        "stale": {"type": "boolean"},
        "indexed_head": {"type": "string"},
        "indexed_branch": {"type": "string"},
        "source_generation": {"type": "integer"},
        "indexed_source_generation": {"type": "integer"},
        "server_build_hash": {"type": "string"},
        "schema_hash": {"type": "string"},
        "capability_epoch": {"type": "string"},
        "error": {"type": "string"},
    },
    "required": [
        "ok",
        "repo_name",
        "page",
        "content",
        "size_bytes",
        "truncated",
        "error",
    ],
}
KNOWLEDGE_SEARCH_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **public_projection_schema_properties(),
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "query": {"type": "string"},
        "wiki_hits": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "page": {"type": "string"},
                    "line": {"type": "integer"},
                    "snippet": {"type": "string"},
                },
                "required": ["source", "page", "line", "snippet"],
            },
        },
        "memory_hits": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "memory_id": {"type": "string"},
                    "memory_type": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "repo_name": {"type": "string"},
                },
                "required": [
                    "memory_id",
                    "memory_type",
                    "title",
                    "summary",
                    "tags",
                    "repo_name",
                ],
            },
        },
        "generation_id": {"type": "string"},
        "stale": {"type": "boolean"},
        "indexed_head": {"type": "string"},
        "indexed_branch": {"type": "string"},
        "source_generation": {"type": "integer"},
        "indexed_source_generation": {"type": "integer"},
        "server_build_hash": {"type": "string"},
        "schema_hash": {"type": "string"},
        "capability_epoch": {"type": "string"},
        "error": {"type": "string"},
        "response_bytes": {"type": "integer"},
        "response_budget_bytes": {"type": "integer"},
        "truncated": {"type": "boolean"},
        "has_more": {"type": "boolean"},
    },
    "required": ["ok", "repo_name", "query", "wiki_hits", "memory_hits", "error"],
}
MEMORY_WRITE_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **public_projection_schema_properties(),
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "memory_id": {"type": "string"},
        "memory_type": {"type": "string"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "server_build_hash": {"type": "string"},
        "schema_hash": {"type": "string"},
        "capability_epoch": {"type": "string"},
        "error": {"type": "string"},
        "truncated": {"type": "boolean"},
        "has_more": {"type": "boolean"},
        "response_budget_bytes": {"type": "integer"},
        "response_bytes": {"type": "integer"},
    },
    "required": [
        "ok",
        "repo_name",
        "memory_id",
        "memory_type",
        "title",
        "summary",
        "error",
    ],
}
WIKI_REFRESH_COMPACT_OUTPUT = {
    # Compact refresh acknowledgements project bounded counts instead of the
    # full page and changed-file arrays, and always carry the compact envelope.
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **public_projection_schema_properties(),
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "status": {"type": "string"},
        "wiki_root": {"type": "string"},
        "summary": {"type": "string"},
        "incremental": {"type": "boolean"},
        "scan_truncated": {"type": "boolean"},
        "stale": {"type": "boolean"},
        "generation_id": {"type": "string"},
        "indexed_head": {"type": "string"},
        "indexed_branch": {"type": "string"},
        "source_generation": {"type": "integer"},
        "indexed_source_generation": {"type": "integer"},
        "refresh_operation_id": {"type": "string"},
        "server_build_hash": {"type": "string"},
        "schema_hash": {"type": "string"},
        "capability_epoch": {"type": "string"},
        "error": {"type": "string"},
        "truncated": {"type": "boolean"},
        "has_more": {"type": "boolean"},
        "response_budget_bytes": {"type": "integer"},
        "response_bytes": {"type": "integer"},
        "page_count": {"type": "integer"},
        "changed_source_file_count": {"type": "integer"},
    },
    "required": [
        "ok",
        "repo_name",
        "status",
        "wiki_root",
        "scan_truncated",
        "error",
        "view",
        "projection_version",
        "non_authoritative",
        "notice",
        "response_budget_bytes",
        "response_bytes",
    ],
}
KNOWLEDGE_ACTION_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **WIKI_REFRESH_OUTPUT["properties"],
        **MEMORY_WRITE_OUTPUT["properties"],
    },
    "required": ["ok", "repo_name", "error"],
    "oneOf": [
        WIKI_REFRESH_OUTPUT,
        WIKI_REFRESH_COMPACT_OUTPUT,
        MEMORY_WRITE_OUTPUT,
    ],
}
KNOWLEDGE_QUERY_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {"ok": {"type": "boolean"}, "error": {"type": "string"}},
}


def _active_server_config(mcp: Any):
    """Return configuration from the module that owns this exact MCP instance.

    ``python -m codexbridge.server`` executes the server as ``__main__``. Importing
    ``codexbridge.server`` again would create a second module with a separate
    ``_config`` global. Resolve the module that owns the active MCP object instead,
    then cache its latest configuration on that MCP instance for diagnostics only.
    """
    for module in tuple(sys.modules.values()):
        if module is None or getattr(module, "mcp", None) is not mcp:
            continue
        getter = getattr(module, "get_config", None)
        if not callable(getter):
            continue
        try:
            config = getter()
        except RuntimeError:
            continue
        setattr(mcp, "_codexbridge_runtime_config", config)
        return config

    raise RuntimeError(
        "CodexBridge active MCP owner/config could not be resolved"
    )


def _runtime_context(mcp: Any, repo_name: str):
    from .config import resolve_repo_identity

    config = _active_server_config(mcp)
    canonical_name, repo_root, _ = resolve_repo_identity(config, repo_name)
    return config, repo_root, canonical_name


def _memory_hit(record) -> dict[str, Any]:
    memory_type = getattr(record.memory_type, "value", str(record.memory_type))
    return {
        "memory_id": record.memory_id,
        "memory_type": memory_type,
        "title": record.title,
        "summary": record.summary,
        "tags": list(record.tags),
        "repo_name": record.repo_name or "",
    }


def _with_capability_metadata(
    result: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    enriched = dict(result)
    for key, value in capability_metadata(schema).items():
        enriched.setdefault(key, value)
    return enriched


def _bounded_knowledge_search(result: dict[str, Any], budget: int = 12 * 1024) -> dict[str, Any]:
    """Keep knowledge search deterministic and connector-safe while preserving freshness metadata."""
    bounded = apply_compact_projection_envelope(dict(result))
    bounded["truncated"] = False
    bounded["has_more"] = False
    bounded["response_budget_bytes"] = budget
    bounded["response_bytes"] = 0
    while len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > budget:
        wiki_hits = bounded.get("wiki_hits") or []
        memory_hits = bounded.get("memory_hits") or []
        if wiki_hits:
            wiki_hits.pop()
        elif memory_hits:
            memory_hits.pop()
        else:
            for key in ("query", "indexed_branch", "indexed_head"):
                if bounded.get(key):
                    bounded[key] = bounded[key][:256]
                    break
            else:
                bounded["truncated"] = True
                break
        bounded["truncated"] = True
        bounded["has_more"] = True
    bounded["response_bytes"] = len(
        json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    return bounded


def _bounded_wiki_page(result: dict[str, Any], budget: int) -> dict[str, Any]:
    bounded = apply_compact_projection_envelope(dict(result))
    bounded["has_more"] = False
    bounded["response_budget_bytes"] = budget
    bounded.setdefault("truncated", False)
    while len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > budget:
        content = str(bounded.get("content") or "")
        if not content:
            break
        bounded["content"] = content[: max(0, len(content) - 512)]
        bounded["truncated"] = True
        bounded["has_more"] = True
    bounded["response_bytes"] = len(
        json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    return bounded


def _bounded_knowledge_action(result: dict[str, Any], budget: int) -> dict[str, Any]:
    if budget < 1024 or budget > 64 * 1024:
        raise ValueError("response_budget_bytes must be between 1024 and 65536")
    compact: dict[str, Any] = {
        key: result[key]
        for key in (
            "ok", "repo_name", "status", "wiki_root", "memory_id", "memory_type",
            "title", "incremental", "scan_truncated", "stale", "generation_id",
            "indexed_head", "indexed_branch", "source_generation",
            "indexed_source_generation", "refresh_operation_id", "error",
            "server_build_hash", "schema_hash", "capability_epoch",
        )
        if key in result
    }
    for key in ("title", "error"):
        if compact.get(key):
            compact[key] = str(compact[key])[:512]
    if "summary" in result:
        compact["summary"] = str(result.get("summary") or "")[:512]
    for key in ("pages", "changed_source_files"):
        if key in result:
            compact[f"{key[:-1]}_count"] = len(result.get(key) or [])
    apply_compact_projection_envelope(compact)
    compact["truncated"] = False
    compact["has_more"] = False
    compact["response_budget_bytes"] = budget
    encoded = json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > budget:
        # Empty rather than remove: "summary" stays schema-required for
        # memory-write acknowledgements even when the budget forces truncation.
        if "summary" in compact:
            compact["summary"] = ""
        compact["truncated"] = True
        compact["has_more"] = True
    compact["response_bytes"] = len(
        json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    return compact


def register_knowledge_tools(mcp: Any) -> None:
    """Register knowledge tools exactly once on a FastMCP instance."""
    if getattr(mcp, "_codexbridge_knowledge_tools_registered", False):
        return

    from .memory.repository import ProjectMemoryRepository
    from .operation_locks import repository_operation_lock
    from .repo_wiki import RepoWikiService

    def refresh_repo_wiki(repo_name: str, force: bool = False) -> dict:
        """Generate or incrementally refresh the repository-local CodexBridge wiki."""
        try:
            config, repo_root, canonical_name = _runtime_context(mcp, repo_name)
            with repository_operation_lock(
                config.resolve_runs_dir(),
                repo_name=canonical_name,
                tool="refresh_repo_wiki",
                normalized_input={"force": force},
            ):
                service = RepoWikiService(repo_root, canonical_name)
                git_dir = repo_root / ".git"
                if git_dir.is_dir() and not (git_dir / "HEAD").is_file():
                    service._git_list_source_candidates = lambda: None
                return _with_capability_metadata(
                    service.refresh(force=force), WIKI_REFRESH_OUTPUT
                )
        except Exception as exc:
            return _with_capability_metadata(
                {
                    "ok": False,
                    "repo_name": repo_name,
                    "status": "failed",
                    "wiki_root": ".codexbridge/wiki",
                    "pages": [],
                    "source_file_count": 0,
                    "changed_source_files": [],
                    "scan_truncated": False,
                    "generation_id": "",
                    "indexed_head": "",
                    "indexed_branch": "",
                    "source_generation": 0,
                    "indexed_source_generation": 0,
                    "incremental": False,
                    "refresh_operation_id": "",
                    "error": str(exc),
                },
                WIKI_REFRESH_OUTPUT,
            )

    def read_repo_wiki(repo_name: str, page: str = "overview.md") -> dict:
        """Read one generated repository wiki page by safe relative page name."""
        try:
            _, repo_root, canonical_name = _runtime_context(mcp, repo_name)
            return _with_capability_metadata(
                RepoWikiService(repo_root, canonical_name).read_page(page),
                WIKI_PAGE_OUTPUT,
            )
        except Exception as exc:
            return _with_capability_metadata(
                {
                    "ok": False,
                    "repo_name": repo_name,
                    "status": (
                        "corrupt"
                        if any(
                            marker in str(exc).lower()
                            for marker in ("current.json", "generation", "manifest_sha256")
                        )
                        else "not_found"
                        if isinstance(exc, FileNotFoundError)
                        else "failed"
                    ),
                    "page": page,
                    "content": "",
                    "size_bytes": 0,
                    "truncated": False,
                    "generation_id": "",
                    "stale": False,
                    "indexed_head": "",
                    "indexed_branch": "",
                    "source_generation": 0,
                    "indexed_source_generation": 0,
                    "error": str(exc),
                },
                WIKI_PAGE_OUTPUT,
            )

    def search_repo_knowledge(
        repo_name: str,
        query: str,
        limit: int = 10,
        include_global_memory: bool = False,
        response_budget_bytes: int = 12 * 1024,
        view: str = "compact",
    ) -> dict:
        """Search the repository wiki and repository-scoped memory in one call."""
        if view not in {"compact", "full"}:
            raise ValueError("view must be compact or full")
        try:
            config, repo_root, canonical_name = _runtime_context(mcp, repo_name)
            maximum = max(1, min(limit, 50))
            wiki = RepoWikiService(repo_root, canonical_name).search_with_metadata(
                query, limit=maximum
            )
            memory = ProjectMemoryRepository(config=config)
            result = memory.search(
                query,
                repo_name=canonical_name,
                include_global=include_global_memory,
                limit=maximum,
            )
            memory_hits = [_memory_hit(record) for record in result.records]
            response = _with_capability_metadata(
                {
                    "ok": True,
                    "repo_name": canonical_name,
                    "query": query,
                    "wiki_hits": wiki["hits"],
                    "memory_hits": memory_hits,
                    "generation_id": wiki["generation_id"],
                    "stale": wiki["stale"],
                    "indexed_head": wiki["indexed_head"],
                    "indexed_branch": wiki["indexed_branch"],
                    "source_generation": wiki["source_generation"],
                    "indexed_source_generation": wiki["indexed_source_generation"],
                    "error": "",
                },
                KNOWLEDGE_SEARCH_OUTPUT,
            )
            if view == "full":
                return response
            return _bounded_knowledge_search(response, response_budget_bytes)
        except Exception as exc:
            return _with_capability_metadata(
                {
                    "ok": False,
                    "repo_name": repo_name,
                    "query": query,
                    "wiki_hits": [],
                    "memory_hits": [],
                    "generation_id": "",
                    "stale": False,
                    "indexed_head": "",
                    "indexed_branch": "",
                    "source_generation": 0,
                    "indexed_source_generation": 0,
                    "error": str(exc),
                },
                KNOWLEDGE_SEARCH_OUTPUT,
            )

    def remember_repo_decision(
        repo_name: str,
        decision: str,
        accepted_by: str = "chatgpt",
    ) -> dict:
        """Persist an architectural or product decision scoped to one repository."""
        try:
            if not decision.strip():
                raise ValueError("decision must not be empty")
            config, repo_root, canonical_name = _runtime_context(mcp, repo_name)
            memory = ProjectMemoryRepository(config=config)
            record = memory.remember_decision(
                decision.strip(),
                repo_name=canonical_name,
                repo_path=repo_root,
                accepted_by=accepted_by.strip() or None,
            )
            return _with_capability_metadata(
                {
                    "ok": True,
                    "repo_name": canonical_name,
                    "memory_id": record.memory_id,
                    "memory_type": record.memory_type.value,
                    "title": record.title,
                    "summary": record.summary,
                    "error": "",
                },
                MEMORY_WRITE_OUTPUT,
            )
        except Exception as exc:
            return _with_capability_metadata(
                {
                    "ok": False,
                    "repo_name": repo_name,
                    "memory_id": "",
                    "memory_type": "",
                    "title": "",
                    "summary": "",
                    "error": str(exc),
                },
                MEMORY_WRITE_OUTPUT,
            )

    @mcp.tool(output_schema=KNOWLEDGE_QUERY_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
    def knowledge_query(request: KnowledgeQueryRequest) -> dict:
        """Read-only gateway for repository wiki pages and isolated knowledge search."""
        if request.operation == "read_wiki":
            page = read_repo_wiki(request.repo_name, request.page)
            if request.view == "full":
                return page
            if request.response_budget_bytes < 1024 or request.response_budget_bytes > 64 * 1024:
                raise ValueError("response_budget_bytes must be between 1024 and 65536")
            return _bounded_wiki_page(page, request.response_budget_bytes)
        return search_repo_knowledge(
            request.repo_name,
            request.query,
            request.limit,
            request.include_global_memory,
            request.response_budget_bytes,
            request.view,
        )

    @mcp.tool(output_schema=KNOWLEDGE_ACTION_OUTPUT, annotations=WRITE_ANNOTATIONS)
    def knowledge_action(request: KnowledgeActionRequest) -> dict:
        """Write gateway for repository wiki refresh and repository-scoped decisions."""
        if request.action == "refresh_wiki":
            result = refresh_repo_wiki(request.repo_name, request.force)
        else:
            result = remember_repo_decision(
                request.repo_name, request.decision, request.accepted_by
            )
        if request.view == "full":
            return result
        return _bounded_knowledge_action(result, request.response_budget_bytes)

    setattr(mcp, "_codexbridge_knowledge_tools_registered", True)


def install_knowledge_tools() -> None:
    """
    Install a small FastMCP run hook so tools are registered before serving.

    This avoids a dependency cycle: package initialisation happens before
    ``codexbridge.server`` creates its FastMCP instance, while the tool bodies
    resolve server configuration only when they are invoked.
    """
    from fastmcp import FastMCP

    if getattr(FastMCP, "_codexbridge_knowledge_hook_installed", False):
        return

    original_run: Callable[..., Any] = FastMCP.run

    @wraps(original_run)
    def run_with_knowledge(self, *args, **kwargs):
        register_knowledge_tools(self)
        return original_run(self, *args, **kwargs)

    FastMCP.run = run_with_knowledge
    setattr(FastMCP, "_codexbridge_knowledge_hook_installed", True)
