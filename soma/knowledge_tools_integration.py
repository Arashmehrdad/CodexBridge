from __future__ import annotations

import hashlib
import json
import sys
from functools import wraps
from pathlib import Path
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
PROJECT_KNOWLEDGE_ACTION_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **public_projection_schema_properties(),
        "ok": {"type": "boolean"},
        "project_id": {"type": "string"},
        "repo_name": {"type": "string"},
        "operation": {"type": "string"},
        "knowledge_id": {"type": "string"},
        "revision": {"type": "integer"},
        "status": {"type": "string"},
        "canonical_path": {"type": "string"},
        "source_count": {"type": "integer"},
        "source_id": {"type": "string"},
        "source_version_id": {"type": "string"},
        "sha256": {"type": "string"},
        "archive_path": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "ingestion_status": {"type": "string"},
        "reused": {"type": "boolean"},
        "packet_id": {"type": "string"},
        "entity_counts": {"type": "object"},
        "dataset_id": {"type": "string"},
        "indexed_count": {"type": "integer"},
        "failed_count": {"type": "integer"},
        "malformed_count": {"type": "integer"},
        "error": {"type": "string"},
        "truncated": {"type": "boolean"},
        "has_more": {"type": "boolean"},
        "response_budget_bytes": {"type": "integer"},
        "response_bytes": {"type": "integer"},
    },
    "required": ["ok", "project_id", "repo_name", "operation", "error"],
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
#: Canonical memory mutation acknowledgement.
#:
#: `content_sha256` is required rather than optional: it is the token the next
#: compare-and-swap correction needs, so a caller that cannot see it cannot
#: safely correct what it just wrote.
CANONICAL_MEMORY_ACTION_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **public_projection_schema_properties(),
        "ok": {"type": "boolean"},
        "project_id": {"type": "string"},
        "repo_name": {"type": "string"},
        "operation": {"type": "string"},
        "memory_id": {"type": "string"},
        "memory_type": {"type": "string"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "status": {"type": "string"},
        "vault_path": {"type": "string"},
        "content_sha256": {"type": "string"},
        "revision": {"type": "integer"},
        "indexed_count": {"type": "integer"},
        "malformed_count": {"type": "integer"},
        "unadopted_count": {"type": "integer"},
        "drifted_count": {"type": "integer"},
        "generation": {"type": "integer"},
        "task_id": {"type": "string"},
        "run_id": {"type": "string"},
        "server_build_hash": {"type": "string"},
        "schema_hash": {"type": "string"},
        "capability_epoch": {"type": "string"},
        "error": {"type": "string"},
        "truncated": {"type": "boolean"},
        "has_more": {"type": "boolean"},
        "response_budget_bytes": {"type": "integer"},
        "response_bytes": {"type": "integer"},
    },
    "required": ["ok", "project_id", "repo_name", "operation", "error"],
}

KNOWLEDGE_ACTION_OUTPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **WIKI_REFRESH_OUTPUT["properties"],
        **MEMORY_WRITE_OUTPUT["properties"],
        **CANONICAL_MEMORY_ACTION_OUTPUT["properties"],
    },
    "required": ["ok", "repo_name", "error"],
    # `anyOf`, not `oneOf`. Every variant shares the same minimal failure shape
    # -- ok/project_id/repo_name/operation/error -- so a refusal legitimately
    # satisfies more than one, and `oneOf` would reject a correct response for
    # being *too* conformant. The constraint that matters is per-variant:
    # `additionalProperties: False` plus each variant's own required keys.
    "anyOf": [
        WIKI_REFRESH_OUTPUT,
        WIKI_REFRESH_COMPACT_OUTPUT,
        MEMORY_WRITE_OUTPUT,
        PROJECT_KNOWLEDGE_ACTION_OUTPUT,
        CANONICAL_MEMORY_ACTION_OUTPUT,
    ],
}
KNOWLEDGE_QUERY_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
    "properties": {"ok": {"type": "boolean"}, "error": {"type": "string"}},
}


def _active_server_config(mcp: Any):
    """Return configuration from the module that owns this exact MCP instance.

    ``python -m soma.server`` executes the server as ``__main__``. Importing
    ``soma.server`` again would create a second module with a separate
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
        setattr(mcp, "_soma_runtime_config", config)
        return config

    raise RuntimeError("Soma active MCP owner/config could not be resolved")


def _runtime_context(mcp: Any, repo_name: str):
    from .config import resolve_repo_identity

    config = _active_server_config(mcp)
    canonical_name, repo_root, _ = resolve_repo_identity(config, repo_name)
    return config, repo_root, canonical_name


def _project_knowledge_context(mcp: Any, project_id: str, repo_name: str):
    from .knowledge import KnowledgeService
    from .project_scope import ProjectScopeStore

    config, repo_root, canonical_name = _runtime_context(mcp, repo_name)
    binding = ProjectScopeStore(config.resolve_runs_dir()).resolve_repository(
        project_id=project_id,
        repo_name=canonical_name,
        repository_root=repo_root,
    )
    knowledge_root = config.resolve_runs_dir() / "knowledge"
    service = KnowledgeService(
        vault_root=knowledge_root / "projects" / binding.project_id / "vault",
        db_path=knowledge_root / "knowledge.sqlite3",
    )
    return service, binding, canonical_name


def _memory_retrieval_state() -> tuple[str, str]:
    """Published provider health and retrieval mode.

    `MEMORY-INTEGRATION-FOUNDATION-1` step 2 measured that Basic Memory 0.22.1
    cannot prove which files a generation indexed, so semantic retrieval is not
    permitted and Soma answers from the canonical catalog, which is complete by
    construction. The published state says exactly that rather than presenting a
    lexical answer as a semantic one.
    """
    from .memory_guard.health import PROVIDER_MEMBERSHIP_AVAILABLE

    if PROVIDER_MEMBERSHIP_AVAILABLE:
        return "healthy", "semantic"
    return "degraded", "catalog_lexical"


def _launch_memory_rebuild(mcp: Any, request: Any, binding: Any) -> dict[str, Any]:
    """Hand a provider rebuild to Soma's existing durable task authority.

    The adapter describes the work and this function submits it; neither creates
    a task, lease, cancellation or recovery plane. Cancellation, retry, restart
    reconciliation and result publication are already owned by TaskManager and
    the durable run engine, and a second lifecycle would be a second truth about
    whether a rebuild is running.

    A rebuild is only useful once semantic retrieval can be trusted, which step
    2 measured is not yet the case, so the request is accepted and refused here
    with the reason rather than launching work whose result cannot be believed.
    """
    from .memory_guard.health import PROVIDER_MEMBERSHIP_AVAILABLE

    if not PROVIDER_MEMBERSHIP_AVAILABLE:
        raise ValueError(
            "provider rebuild is not launched because semantic retrieval is "
            "disabled: the accepted provider interface cannot prove which files "
            "an index generation contains, so a completed rebuild would not "
            "establish coverage. Canonical lexical retrieval needs no rebuild; "
            "use memory_sync_provider to reconcile the canonical catalog"
        )

    from .tasks.manager import TaskManager  # pragma: no cover - unreachable today

    manager = TaskManager(_active_server_config(mcp))
    return manager.start_durable_command(
        controller_request_id=request.controller_request_id,
        project_id=binding.project_id,
        repo_name=binding.repo_name,
        argv=[],
        working_directory=binding.repository_root,
    )


def _canonical_memory_context(mcp: Any, project_id: str, repo_name: str):
    """Resolve one bound `CanonicalMemoryService`, or refuse.

    `project_id` may be empty for the legacy compatibility aliases: ProjectScope
    then resolves the repository's single active project and refuses when that
    is ambiguous. Every named memory operation supplies it explicitly.
    """
    from .knowledge import CanonicalMemoryService, KnowledgeService, PacketStore
    from .knowledge.scope import MemoryScope, ScopeRefused
    from .project_scope import ProjectScopeStore

    config, repo_root, canonical_name = _runtime_context(mcp, repo_name)
    try:
        binding = ProjectScopeStore(config.resolve_runs_dir()).resolve_repository(
            project_id=project_id,
            repo_name=canonical_name,
            repository_root=repo_root,
        )
    except Exception as exc:
        # A canonical write without authoritative scope is exactly the second
        # authority this architecture removes, so refuse -- but say why in terms
        # the caller can act on rather than leaking a storage-layer error.
        raise ScopeRefused(
            f"canonical memory for {canonical_name!r} requires an exact active "
            f"ProjectScope binding, which could not be resolved: {exc}"
        ) from exc
    runs_dir = config.resolve_runs_dir()
    vault_root = config.canonical_memory.resolve_vault_root(
        runs_dir, binding.project_id
    )
    knowledge = KnowledgeService(
        vault_root=vault_root,
        db_path=runs_dir / "knowledge" / "knowledge.sqlite3",
    )
    service = CanonicalMemoryService(
        knowledge,
        MemoryScope(
            kind="project",
            project_id=binding.project_id,
            repo_name=canonical_name,
        ),
        packet_store=PacketStore(runs_dir / "knowledge" / "packets"),
    )
    return service, binding, canonical_name


def _memory_scope_discovery(mcp: Any, request: Any) -> dict:
    """Answer "which scope do my memory calls need?" for one repository.

    Returns the scope object ready to send back verbatim, so a controller that
    knows only a repository name can address its own project. The scope is
    still required explicitly on every subsequent call: discovery stays a
    separate, visible step rather than becoming a silent default.
    """
    from .knowledge.scope import ScopeRefused

    try:
        service, _binding, canonical_name = _canonical_memory_context(
            mcp, request.project_id, request.repo_name
        )
    except Exception as exc:
        return {
            "ok": False,
            "project_id": request.project_id,
            "repo_name": request.repo_name,
            "operation": "memory_scope",
            "error": str(exc)
            if isinstance(exc, ScopeRefused)
            else f"memory scope could not be resolved: {exc}",
        }
    health = service.knowledge.health(service.scope.project_id)
    return {
        "ok": True,
        "project_id": service.scope.project_id,
        "repo_name": canonical_name,
        "operation": "memory_scope",
        "error": "",
        # Ready to send back verbatim as the `scope` argument.
        "scope": service.scope.to_dict(),
        "canonical_health": health.status,
        "canonical_count": health.canonical_count,
        "vault_root": str(service.knowledge.vault_root),
    }


def _project_research_context(mcp: Any, project_id: str, repo_name: str):
    from .project_scope import ProjectScopeStore
    from .research import ResearchPlatformService

    config, repo_root, canonical_name = _runtime_context(mcp, repo_name)
    binding = ProjectScopeStore(config.resolve_runs_dir()).resolve_repository(
        project_id=project_id,
        repo_name=canonical_name,
        repository_root=repo_root,
    )
    service = ResearchPlatformService(
        config.resolve_runs_dir() / "research",
        binding.project_id,
    )
    return service, binding, canonical_name


def _knowledge_record_projection(record: Any, *, include_body: bool) -> dict[str, Any]:
    projected = {
        "knowledge_id": record.knowledge_id,
        "project_id": record.project_id,
        "kind": record.kind,
        "title": record.title,
        "summary": record.summary,
        "status": record.status,
        "review_state": record.review_state,
        "tags": list(record.tags),
        "revision": record.revision,
        "vault_path": record.vault_path,
        "content_sha256": record.content_sha256,
        "updated_at": record.updated_at,
        "sources": [item.model_dump(mode="json") for item in record.sources],
        "locators": [item.model_dump(mode="json") for item in record.locators],
        "supersedes_ids": list(record.supersedes_ids),
    }
    if include_body:
        projected["body"] = record.body
    return projected


def _bounded_project_result(result: dict[str, Any], budget: int) -> dict[str, Any]:
    bounded = apply_compact_projection_envelope(dict(result))
    bounded.setdefault("truncated", False)
    bounded.setdefault("has_more", False)
    bounded["response_budget_bytes"] = budget
    bounded["response_bytes"] = 0
    while (
        len(
            json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        > budget
    ):
        removed = False
        for key in (
            "retrieved_passages",
            "evidence",
            "claims",
            "questions",
            "candidates",
            "decisions",
            "citations",
            "records",
        ):
            values = bounded.get(key) or []
            if values:
                values.pop()
                removed = True
                break
        if removed:
            bounded["truncated"] = True
            bounded["has_more"] = True
            continue
        record = bounded.get("record") or {}
        body = str(record.get("body") or "")
        if body:
            record["body"] = body[: max(0, len(body) - 1024)]
            bounded["truncated"] = True
            bounded["has_more"] = True
            continue
        bounded["error"] = str(bounded.get("error") or "")[:256]
        break
    bounded["response_bytes"] = len(
        json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    return bounded


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


def _bounded_knowledge_search(
    result: dict[str, Any], budget: int = 12 * 1024
) -> dict[str, Any]:
    """Keep knowledge search deterministic and connector-safe while preserving freshness metadata."""
    bounded = apply_compact_projection_envelope(dict(result))
    bounded["truncated"] = False
    bounded["has_more"] = False
    bounded["response_budget_bytes"] = budget
    bounded["response_bytes"] = 0
    while (
        len(
            json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        > budget
    ):
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
    while (
        len(
            json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        > budget
    ):
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
            "ok",
            "repo_name",
            "status",
            "wiki_root",
            "memory_id",
            "memory_type",
            "title",
            "incremental",
            "scan_truncated",
            "stale",
            "generation_id",
            "indexed_head",
            "indexed_branch",
            "source_generation",
            "indexed_source_generation",
            "refresh_operation_id",
            # Canonical memory acknowledgements. `content_sha256` is not
            # diagnostic decoration: it is the token the caller needs for the
            # next compare-and-swap, so dropping it under budget would make
            # correction impossible rather than merely terser.
            "project_id",
            "operation",
            "content_sha256",
            "revision",
            # A derived location the caller did not choose is not decoration;
            # dropping it under budget would leave the record unfindable.
            "vault_path",
            "scope",
            "vault_root",
            "canonical_count",
            "indexed_count",
            "malformed_count",
            "unadopted_count",
            "drifted_count",
            "generation",
            "task_id",
            "run_id",
            "error",
            "server_build_hash",
            "schema_hash",
            "capability_epoch",
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
    encoded = json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
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
    if getattr(mcp, "_soma_knowledge_tools_registered", False):
        return

    from .knowledge import KnowledgeInput, SourceLocator, SourceReference
    from .memory.repository import ProjectMemoryRepository
    from .operation_locks import repository_operation_lock
    from .repo_wiki import RepoWikiService

    def refresh_repo_wiki(repo_name: str, force: bool = False) -> dict:
        """Generate or incrementally refresh the repository-local Soma wiki."""
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
                    "wiki_root": ".soma/wiki",
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
                            for marker in (
                                "current.json",
                                "generation",
                                "manifest_sha256",
                            )
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
        """Persist an architectural or product decision scoped to one repository.

        Compatibility alias. This used to write into the legacy SQLite memory
        store, which SOMA-SHARED-MEMORY-ARCH-1 retires as a competing content
        authority -- the same decision could otherwise exist in two places with
        two lifecycles. The operation name, request shape and response shape are
        unchanged; the destination is now canonical Markdown, so the record
        gains provenance, supersession and owner-readable storage.
        """
        try:
            text = decision.strip()
            if not text:
                raise ValueError("decision must not be empty")
            service, binding, canonical_name = _canonical_memory_context(
                mcp, "", repo_name
            )
            digest = hashlib.sha256(
                f"{binding.project_id}\0{text}".encode("utf-8")
            ).hexdigest()
            record = service.save(
                KnowledgeInput(
                    project_id=binding.project_id,
                    vault_path=f"decisions/{digest[:16]}.md",
                    kind="decision",
                    title=(text.splitlines()[0][:200] or "Decision"),
                    summary=text[:300],
                    body=text,
                    tags=["decision"],
                    authority_class="controller_memory",
                    controller=(accepted_by.strip() or "chatgpt")[:128],
                    idempotency_key=f"remember_decision:{digest}",
                )
            )
            return _with_capability_metadata(
                {
                    "ok": True,
                    "repo_name": canonical_name,
                    "memory_id": record.knowledge_id,
                    "memory_type": "decision_memory",
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

    def save_project_knowledge(request: Any, *, supersede: bool = False) -> dict:
        from .knowledge import KnowledgeInput, SourceLocator, SourceReference
        from .memory.redaction import detect_sensitivity

        try:
            service, binding, canonical_name = _project_knowledge_context(
                mcp, request.project_id, request.repo_name
            )
            sensitive = detect_sensitivity(
                "\n".join((request.title, request.summary, request.body))
            )
            if sensitive:
                raise ValueError(f"Sensitive knowledge content blocked: {sensitive}")
            note = KnowledgeInput(
                project_id=binding.project_id,
                vault_path=request.vault_path,
                kind=request.kind,
                title=request.title,
                summary=request.summary,
                body=request.body,
                tags=request.tags,
                review_state=request.review_state,
                idempotency_key=request.idempotency_key,
                sources=[
                    SourceReference(**source.model_dump()) for source in request.sources
                ],
                locators=[
                    SourceLocator(**locator.model_dump())
                    for locator in request.locators
                ],
                metadata={"language": request.language, "gateway": "knowledge_action"},
            )
            record = (
                service.supersede(note, request.supersedes_ids)
                if supersede
                else service.save(note)
            )
            return {
                "ok": True,
                "project_id": binding.project_id,
                "repo_name": canonical_name,
                "operation": "supersede" if supersede else "save",
                "knowledge_id": record.knowledge_id,
                "revision": record.revision,
                "status": record.status,
                "canonical_path": str(
                    Path(service.vault_root) / Path(record.vault_path)
                ),
                "source_count": len(record.sources),
                "error": "",
            }
        except Exception as exc:
            return {
                "ok": False,
                "project_id": request.project_id,
                "repo_name": request.repo_name,
                "operation": "supersede" if supersede else "save",
                "error": str(exc),
            }

    def rebuild_project_knowledge(request: Any) -> dict:
        try:
            service, binding, canonical_name = _project_knowledge_context(
                mcp, request.project_id, request.repo_name
            )
            result = service.rebuild(binding.project_id)
            return {
                "ok": result.malformed_count == 0,
                "project_id": binding.project_id,
                "repo_name": canonical_name,
                "operation": "rebuild",
                "status": "healthy" if result.malformed_count == 0 else "degraded",
                "indexed_count": result.indexed_count,
                "malformed_count": result.malformed_count,
                "error": ""
                if result.malformed_count == 0
                else "Malformed notes excluded",
            }
        except Exception as exc:
            return {
                "ok": False,
                "project_id": request.project_id,
                "repo_name": request.repo_name,
                "operation": "rebuild",
                "error": str(exc),
            }

    def import_research_source(request: Any) -> dict:
        from hashlib import sha256

        from .research import SourceImportDraft

        try:
            service, binding, canonical_name = _project_research_context(
                mcp, request.project_id, request.repo_name
            )
            draft = SourceImportDraft(
                project_id=binding.project_id,
                canonical_uri=request.canonical_uri,
                title=request.title,
                source_type=request.source_type,
                retrieved_at=request.retrieved_at,
                origin_namespace=request.origin_namespace,
                origin_key=request.origin_key or request.canonical_uri,
            )
            if request.content_text:
                content = request.content_text.encode("utf-8")
                if request.expected_sha256 and (
                    sha256(content).hexdigest() != request.expected_sha256.lower()
                ):
                    raise ValueError(
                        "source content SHA-256 does not match expected_sha256"
                    )
                result = service.import_bytes(
                    draft,
                    content,
                    original_name=request.original_name,
                    media_type=request.media_type or "text/plain",
                    index=request.index,
                )
            else:
                source_path = Path(
                    request.local_path or request.captured_artifact_path
                ).resolve()
                if request.expected_sha256:
                    digest = sha256()
                    with source_path.open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != request.expected_sha256.lower():
                        raise ValueError(
                            "source file SHA-256 does not match expected_sha256"
                        )
                result = service.import_file(draft, source_path, index=request.index)
            return {
                "ok": True,
                "project_id": binding.project_id,
                "repo_name": canonical_name,
                "operation": "import_research_source",
                "source_id": result.source_id,
                "source_version_id": result.source_version_id,
                "sha256": result.source_sha256,
                "archive_path": result.archive_path,
                "size_bytes": result.size_bytes,
                "ingestion_status": result.ingestion_status,
                "reused": result.reused,
                "error": "",
            }
        except Exception as exc:
            return {
                "ok": False,
                "project_id": request.project_id,
                "repo_name": request.repo_name,
                "operation": "import_research_source",
                "error": str(exc),
            }

    def preserve_research_packet(request: Any) -> dict:
        from .research import ResearchPacketDraft

        try:
            service, binding, canonical_name = _project_research_context(
                mcp, request.project_id, request.repo_name
            )
            payload = dict(request.packet)
            payload.setdefault("project_id", binding.project_id)
            for field in (
                "claims",
                "evidence",
                "questions",
                "candidates",
                "decisions",
                "experiments",
                "summaries",
                "relationships",
            ):
                for item in payload.get(field, []):
                    item.setdefault("project_id", binding.project_id)
            if payload.get("analysis_run"):
                payload["analysis_run"].setdefault("project_id", binding.project_id)
            packet = ResearchPacketDraft.model_validate(payload)
            preserved = service.preserve_packet(packet)
            return {
                "ok": True,
                "project_id": binding.project_id,
                "repo_name": canonical_name,
                "operation": "preserve_research_packet",
                "packet_id": preserved.packet_id,
                "status": (
                    "idempotent_replay" if preserved.idempotent_replay else "preserved"
                ),
                "entity_counts": {
                    key: len(value) for key, value in preserved.entity_ids.items()
                },
                "error": "",
            }
        except Exception as exc:
            return {
                "ok": False,
                "project_id": request.project_id,
                "repo_name": request.repo_name,
                "operation": "preserve_research_packet",
                "error": str(exc),
            }

    def rebuild_research_index(request: Any) -> dict:
        try:
            service, binding, canonical_name = _project_research_context(
                mcp, request.project_id, request.repo_name
            )
            result = service.rebuild_index()
            return {
                "ok": result.failed_count == 0,
                "project_id": binding.project_id,
                "repo_name": canonical_name,
                "operation": "rebuild_research_index",
                "dataset_id": result.dataset_id,
                "indexed_count": result.indexed_count,
                "failed_count": result.failed_count,
                "status": "healthy" if result.failed_count == 0 else "degraded",
                "error": "",
            }
        except Exception as exc:
            return {
                "ok": False,
                "project_id": request.project_id,
                "repo_name": request.repo_name,
                "operation": "rebuild_research_index",
                "status": "not_configured",
                "error": str(exc),
            }

    def memory_query_operation(request: Any) -> dict:
        """The named memory partition: canonical, scope-bound, honest about mode.

        Separate from the research operations on the same gateway and from the
        legacy repo-scoped `search`. A memory record never acquires research
        authority by being returned here.
        """
        operation = request.operation
        if operation == "memory_scope":
            return _memory_scope_discovery(mcp, request)
        try:
            service, _binding, canonical_name = _canonical_memory_context(
                mcp, request.scope.project_id, request.scope.repo_name
            )
            provider_health, retrieval_mode = _memory_retrieval_state()
            base = {
                "ok": True,
                "project_id": service.scope.project_id,
                "repo_name": canonical_name,
                "operation": operation,
                "error": "",
            }
            if operation == "memory_search":
                outcome = service.search(
                    request.query,
                    limit=request.limit,
                    include_non_authoritative=request.include_non_authoritative,
                    provider_health=provider_health,
                    retrieval_mode=retrieval_mode,
                )
                return {
                    **base,
                    **outcome.to_dict(),
                    "records": [
                        service.project_record(record) for record in outcome.records
                    ],
                }
            if operation == "memory_get":
                record = service.get(request.knowledge_id)
                projected = service.project_record(record)
                if request.view == "full":
                    projected["body"] = record.body
                return {**base, "record": projected}
            if operation == "memory_health":
                health = service.knowledge.health(service.scope.project_id)
                return {
                    **base,
                    "canonical_health": health.status,
                    "provider_health": provider_health,
                    "retrieval_mode": retrieval_mode,
                    **health.model_dump(mode="json"),
                }
            if operation == "memory_context":
                packet = service.build_packet(
                    request.query,
                    limit=request.limit,
                    provider_health=provider_health,
                    retrieval_mode=retrieval_mode,
                )
                return {**base, **packet.to_dict()}
            if operation == "memory_packet_get":
                return {**base, **service.packets.get(request.packet_id)}
            raise ValueError(f"unsupported memory operation: {operation!r}")
        except Exception as exc:
            return {
                "ok": False,
                "project_id": request.scope.project_id,
                "repo_name": request.scope.repo_name,
                "operation": operation,
                "error": str(exc),
            }

    @mcp.tool(output_schema=KNOWLEDGE_QUERY_OUTPUT, annotations=READ_ONLY_ANNOTATIONS)
    def knowledge_query(request: KnowledgeQueryRequest) -> dict:
        """Read-only gateway for repository wiki pages and isolated knowledge search."""
        if request.operation in {
            "memory_scope",
            "memory_search",
            "memory_get",
            "memory_health",
            "memory_context",
            "memory_packet_get",
        }:
            return _bounded_project_result(
                memory_query_operation(request), request.response_budget_bytes
            )
        if request.operation in {
            "get_research_source",
            "get_claim_evidence",
            "list_research_questions",
            "list_research_decisions",
            "search_research",
            "build_context_packet",
            "research_health",
        }:
            try:
                service, binding, canonical_name = _project_research_context(
                    mcp, request.project_id, request.repo_name
                )
                base = {
                    "ok": True,
                    "project_id": binding.project_id,
                    "repo_name": canonical_name,
                    "operation": request.operation,
                    "contract_version": "soma.research.v1",
                    "error": "",
                }
                if request.operation == "get_research_source":
                    record = (
                        service.get_source(request.source_id)
                        if request.source_id
                        else service.get_source_version(request.source_version_id)
                    )
                    result = {**base, "record": record.model_dump(mode="json")}
                elif request.operation == "get_claim_evidence":
                    result = {
                        **base,
                        "records": [
                            item.model_dump(mode="json")
                            for item in service.claim_evidence(request.claim_id)
                        ],
                    }
                elif request.operation == "list_research_questions":
                    result = {
                        **base,
                        "records": [
                            item.model_dump(mode="json")
                            for item in service.list_questions()[: request.limit]
                        ],
                    }
                elif request.operation == "list_research_decisions":
                    result = {
                        **base,
                        "records": [
                            item.model_dump(mode="json")
                            for item in service.list_decisions()[: request.limit]
                        ],
                    }
                elif request.operation in {
                    "search_research",
                    "build_context_packet",
                }:
                    packet = service.build_context_packet(
                        request.query, limit=request.limit
                    )
                    payload = packet.model_dump(mode="json")
                    if request.operation == "search_research":
                        payload = {
                            "query": packet.query,
                            "retrieved_passages": packet.retrieved_passages,
                            "citations": packet.citations,
                            "content_sha256": packet.content_sha256,
                        }
                    result = {**base, **payload}
                else:
                    result = {
                        **base,
                        **service.health().model_dump(mode="json"),
                    }
            except Exception as exc:
                result = {
                    "ok": False,
                    "project_id": request.project_id,
                    "repo_name": request.repo_name,
                    "operation": request.operation,
                    "error": str(exc),
                }
            return _bounded_project_result(result, request.response_budget_bytes)
        if request.operation in {
            "search_knowledge",
            "get_knowledge",
            "knowledge_health",
        }:
            try:
                service, binding, canonical_name = _project_knowledge_context(
                    mcp, request.project_id, request.repo_name
                )
                if request.operation == "search_knowledge":
                    page = service.search(
                        binding.project_id,
                        request.query,
                        limit=request.limit,
                        current_only=request.current_only,
                        cursor=request.cursor,
                    )
                    result = {
                        "ok": True,
                        "project_id": binding.project_id,
                        "repo_name": canonical_name,
                        "operation": "search",
                        "query": request.query,
                        "records": [
                            _knowledge_record_projection(
                                record, include_body=request.view == "full"
                            )
                            for record in page.records
                        ],
                        "total": page.total,
                        "next_cursor": page.next_cursor or "",
                        "has_more": page.has_more,
                        "error": "",
                    }
                elif request.operation == "get_knowledge":
                    record = service.get(binding.project_id, request.knowledge_id)
                    result = {
                        "ok": True,
                        "project_id": binding.project_id,
                        "repo_name": canonical_name,
                        "operation": "get",
                        "record": _knowledge_record_projection(
                            record, include_body=request.view == "full"
                        ),
                        "error": "",
                    }
                else:
                    health = service.health(binding.project_id)
                    result = {
                        "ok": True,
                        "project_id": binding.project_id,
                        "repo_name": canonical_name,
                        "operation": "health",
                        **health.model_dump(mode="json"),
                        "error": "",
                    }
            except Exception as exc:
                result = {
                    "ok": False,
                    "project_id": request.project_id,
                    "repo_name": request.repo_name,
                    "operation": request.operation,
                    "error": str(exc),
                }
            return _bounded_project_result(result, request.response_budget_bytes)
        if request.operation == "read_wiki":
            page = read_repo_wiki(request.repo_name, request.page)
            if request.view == "full":
                return page
            if (
                request.response_budget_bytes < 1024
                or request.response_budget_bytes > 64 * 1024
            ):
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

    def memory_action_operation(request: Any) -> dict:
        """Canonical memory writes. One authority, one write path."""
        action = request.action
        try:
            service, binding, canonical_name = _canonical_memory_context(
                mcp, request.scope.project_id, request.scope.repo_name
            )
            base = {
                "ok": True,
                "project_id": binding.project_id,
                "repo_name": canonical_name,
                "operation": action,
                "error": "",
            }

            if action in {"memory_save", "memory_supersede"}:
                note = KnowledgeInput(
                    project_id=binding.project_id,
                    vault_path=request.vault_path,
                    kind=request.kind,
                    title=request.title,
                    summary=request.summary,
                    body=request.body,
                    tags=list(request.tags),
                    review_state=request.review_state,
                    valid_from=request.valid_from,
                    valid_until=request.valid_until,
                    controller=request.controller,
                    task_id=request.task_id,
                    run_id=request.run_id,
                    idempotency_key=request.idempotency_key,
                    authority_class="controller_memory",
                    sources=[
                        SourceReference(**item.model_dump())
                        for item in request.sources
                    ],
                    locators=[
                        SourceLocator(**item.model_dump())
                        for item in request.locators
                    ],
                )
                record = (
                    service.supersede(note, list(request.supersedes_ids))
                    if action == "memory_supersede"
                    else service.save(note)
                )
                return {
                    **base,
                    "memory_id": record.knowledge_id,
                    "memory_type": f"{record.kind}_memory",
                    "title": record.title,
                    "summary": record.summary,
                    "content_sha256": record.content_sha256,
                    "revision": record.revision,
                    # Always echoed, because it may have been derived: a caller
                    # must never have to guess where its own record landed.
                    "vault_path": record.vault_path,
                }

            if action == "memory_accept_drift":
                record = service.accept_drift(
                    request.knowledge_id,
                    accepted_sha256=request.accepted_sha256,
                )
                return {
                    **base,
                    "memory_id": record.knowledge_id,
                    "memory_type": f"{record.kind}_memory",
                    "title": record.title,
                    "status": record.status,
                    "content_sha256": record.content_sha256,
                    "revision": record.revision,
                }

            if action in {
                "memory_mark_disputed",
                "memory_archive",
                "memory_reject",
            }:
                status = {
                    "memory_mark_disputed": "disputed",
                    "memory_archive": "archived",
                    "memory_reject": "rejected",
                }[action]
                record = service.set_status(
                    request.knowledge_id,
                    status,
                    expected_sha256=request.expected_sha256,
                )
                return {
                    **base,
                    "memory_id": record.knowledge_id,
                    "memory_type": f"{record.kind}_memory",
                    "title": record.title,
                    "summary": record.summary,
                    "status": record.status,
                    "content_sha256": record.content_sha256,
                }

            if action == "memory_sync_provider":
                result = service.knowledge.rebuild(binding.project_id)
                health = service.knowledge.health(binding.project_id)
                return {
                    **base,
                    "indexed_count": result.indexed_count,
                    "malformed_count": result.malformed_count,
                    "unadopted_count": result.unadopted_count,
                    "drifted_count": result.drifted_count,
                    "status": health.status,
                    "generation": health.generation,
                }

            if action == "memory_rebuild_index":
                return {**base, **_launch_memory_rebuild(mcp, request, binding)}

            raise ValueError(f"unsupported memory action: {action!r}")
        except Exception as exc:
            return {
                "ok": False,
                "project_id": request.scope.project_id,
                "repo_name": request.scope.repo_name,
                "operation": action,
                "error": str(exc),
            }

    @mcp.tool(output_schema=KNOWLEDGE_ACTION_OUTPUT, annotations=WRITE_ANNOTATIONS)
    def knowledge_action(request: KnowledgeActionRequest) -> dict:
        """Write gateway for repository wiki refresh and repository-scoped decisions."""
        if request.action in {
            "memory_save",
            "memory_supersede",
            "memory_mark_disputed",
            "memory_archive",
            "memory_reject",
            "memory_accept_drift",
            "memory_rebuild_index",
            "memory_sync_provider",
        }:
            return _bounded_knowledge_action(
                memory_action_operation(request), request.response_budget_bytes
            )
        if request.action == "refresh_wiki":
            result = refresh_repo_wiki(request.repo_name, request.force)
        elif request.action == "remember_decision":
            result = remember_repo_decision(
                request.repo_name, request.decision, request.accepted_by
            )
        elif request.action == "save_knowledge":
            result = save_project_knowledge(request)
        elif request.action == "supersede_knowledge":
            result = save_project_knowledge(request, supersede=True)
        elif request.action == "import_research_source":
            result = import_research_source(request)
        elif request.action == "preserve_research_packet":
            result = preserve_research_packet(request)
        elif request.action == "rebuild_research_index":
            result = rebuild_research_index(request)
        else:
            result = rebuild_project_knowledge(request)
        if request.view == "full":
            if request.action in {
                "save_knowledge",
                "supersede_knowledge",
                "rebuild_knowledge",
                "import_research_source",
                "preserve_research_packet",
                "rebuild_research_index",
            }:
                return _bounded_project_result(result, request.response_budget_bytes)
            return result
        if request.action in {
            "save_knowledge",
            "supersede_knowledge",
            "rebuild_knowledge",
            "import_research_source",
            "preserve_research_packet",
            "rebuild_research_index",
        }:
            return _bounded_project_result(result, request.response_budget_bytes)
        return _bounded_knowledge_action(result, request.response_budget_bytes)

    setattr(mcp, "_soma_knowledge_tools_registered", True)


def install_knowledge_tools() -> None:
    """
    Install a small FastMCP run hook so tools are registered before serving.

    This avoids a dependency cycle: package initialisation happens before
    ``soma.server`` creates its FastMCP instance, while the tool bodies
    resolve server configuration only when they are invoked.
    """
    from fastmcp import FastMCP

    if getattr(FastMCP, "_soma_knowledge_hook_installed", False):
        return

    original_run: Callable[..., Any] = FastMCP.run

    @wraps(original_run)
    def run_with_knowledge(self, *args, **kwargs):
        register_knowledge_tools(self)
        return original_run(self, *args, **kwargs)

    FastMCP.run = run_with_knowledge
    setattr(FastMCP, "_soma_knowledge_hook_installed", True)
