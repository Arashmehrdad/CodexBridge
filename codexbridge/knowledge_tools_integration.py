from __future__ import annotations

from functools import wraps
from typing import Any, Callable


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
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "status": {"type": "string"},
        "wiki_root": {"type": "string"},
        "pages": {"type": "array", "items": {"type": "string"}},
        "source_file_count": {"type": "integer"},
        "changed_source_files": {"type": "array", "items": {"type": "string"}},
        "scan_truncated": {"type": "boolean"},
        "error": {"type": "string"},
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
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "page": {"type": "string"},
        "content": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "truncated": {"type": "boolean"},
        "error": {"type": "string"},
    },
    "required": ["ok", "repo_name", "page", "content", "size_bytes", "truncated", "error"],
}
KNOWLEDGE_SEARCH_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
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
                "required": ["memory_id", "memory_type", "title", "summary", "tags", "repo_name"],
            },
        },
        "error": {"type": "string"},
    },
    "required": ["ok", "repo_name", "query", "wiki_hits", "memory_hits", "error"],
}
MEMORY_WRITE_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "repo_name": {"type": "string"},
        "memory_id": {"type": "string"},
        "memory_type": {"type": "string"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "error": {"type": "string"},
    },
    "required": ["ok", "repo_name", "memory_id", "memory_type", "title", "summary", "error"],
}


def _runtime_context(repo_name: str):
    from .config import resolve_repo
    from .server import get_config

    config = get_config()
    repo_root = resolve_repo(config, repo_name)
    return config, repo_root


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


def register_knowledge_tools(mcp: Any) -> None:
    """Register knowledge tools exactly once on a FastMCP instance."""
    if getattr(mcp, "_codexbridge_knowledge_tools_registered", False):
        return

    from .memory.repository import ProjectMemoryRepository
    from .repo_wiki import RepoWikiService

    @mcp.tool(output_schema=WIKI_REFRESH_OUTPUT, annotations=WRITE_ANNOTATIONS)
    def refresh_repo_wiki(repo_name: str, force: bool = False) -> dict:
        """Generate or incrementally refresh the repository-local CodexBridge wiki."""
        try:
            _, repo_root = _runtime_context(repo_name)
            return RepoWikiService(repo_root, repo_name).refresh(force=force)
        except Exception as exc:
            return {
                "ok": False,
                "repo_name": repo_name,
                "status": "failed",
                "wiki_root": ".codexbridge/wiki",
                "pages": [],
                "source_file_count": 0,
                "changed_source_files": [],
                "scan_truncated": False,
                "error": str(exc),
            }

    @mcp.tool(output_schema=WIKI_PAGE_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
    def read_repo_wiki(repo_name: str, page: str = "overview.md") -> dict:
        """Read one generated repository wiki page by safe relative page name."""
        try:
            _, repo_root = _runtime_context(repo_name)
            return RepoWikiService(repo_root, repo_name).read_page(page)
        except Exception as exc:
            return {
                "ok": False,
                "repo_name": repo_name,
                "page": page,
                "content": "",
                "size_bytes": 0,
                "truncated": False,
                "error": str(exc),
            }

    @mcp.tool(output_schema=KNOWLEDGE_SEARCH_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
    def search_repo_knowledge(
        repo_name: str,
        query: str,
        limit: int = 10,
        include_global_memory: bool = False,
    ) -> dict:
        """Search the repository wiki and repository-scoped memory in one call."""
        try:
            config, repo_root = _runtime_context(repo_name)
            maximum = max(1, min(limit, 50))
            wiki_hits = RepoWikiService(repo_root, repo_name).search(query, limit=maximum)
            memory = ProjectMemoryRepository(config=config)
            result = memory.search(
                query,
                repo_name=repo_name,
                include_global=include_global_memory,
                limit=maximum,
            )
            memory_hits = [_memory_hit(record) for record in result.records]
            return {
                "ok": True,
                "repo_name": repo_name,
                "query": query,
                "wiki_hits": wiki_hits,
                "memory_hits": memory_hits,
                "error": "",
            }
        except Exception as exc:
            return {
                "ok": False,
                "repo_name": repo_name,
                "query": query,
                "wiki_hits": [],
                "memory_hits": [],
                "error": str(exc),
            }

    @mcp.tool(output_schema=MEMORY_WRITE_OUTPUT, annotations=WRITE_ANNOTATIONS)
    def remember_repo_decision(
        repo_name: str,
        decision: str,
        accepted_by: str = "chatgpt",
    ) -> dict:
        """Persist an architectural or product decision scoped to one repository."""
        try:
            if not decision.strip():
                raise ValueError("decision must not be empty")
            config, repo_root = _runtime_context(repo_name)
            memory = ProjectMemoryRepository(config=config)
            record = memory.remember_decision(
                decision.strip(),
                repo_name=repo_name,
                repo_path=repo_root,
                accepted_by=accepted_by.strip() or None,
            )
            return {
                "ok": True,
                "repo_name": repo_name,
                "memory_id": record.memory_id,
                "memory_type": record.memory_type.value,
                "title": record.title,
                "summary": record.summary,
                "error": "",
            }
        except Exception as exc:
            return {
                "ok": False,
                "repo_name": repo_name,
                "memory_id": "",
                "memory_type": "",
                "title": "",
                "summary": "",
                "error": str(exc),
            }

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
