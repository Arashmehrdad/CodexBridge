# CODE-INTELLIGENCE-DECISION-1 - Codebase Memory MCP Boundary

**Date:** 2026-07-28
**Status:** accepted as a planned, inactive derived code-intelligence component.
**Decision scope:** architecture placement only; no installation or pilot activation.

## Decision

Add `DeusData/codebase-memory-mcp` to the Soma plan as the preferred ready-made candidate for **derived repository code intelligence**.

It does not overlap with the selected memory architecture:

- **Markdown + Git + Obsidian + MCP Connector** cover owner-readable project knowledge, decisions, lessons, procedures, continuity, and personal/project memory. Basic Memory Local remains only a headless fallback after a named failure.
- **Codebase Memory MCP** derives structural facts from source repositories: symbols, definitions, imports, call paths, routes, impact, architecture, and source snippets.
- **Soma** remains the authority for project identity, repository binding, source generation, provenance, permissions, lifecycle, evidence, and controller routing.

Codebase Memory MCP is therefore an index and query provider, not a memory authority.

## Non-overlap boundary

| Concern | Authority or provider |
|---|---|
| Source files and Git history | Repository itself |
| Repository identity and approved root | Soma ProjectScope/resource binding |
| Tasks, runs, evidence and lifecycle | Soma |
| Owner-authored decisions, lessons and continuity | Markdown + Git, edited in Obsidian and served first through MCP Connector |
| Existing repository wiki and evidence references | Soma `RepoWikiService` and canonical repository evidence |
| Structural code graph, call paths and impact analysis | Codebase Memory MCP as a disposable derived index |
| Architectural decision records | Owner Markdown/Soma evidence; **not** Codebase Memory `manage_adr` |

Answers from Codebase Memory MCP must be re-grounded to exact repository paths, symbols, source generations, and file hashes before Soma presents them as durable evidence.

## Why this candidate fits

The official project provides a local, MIT-licensed, single-binary MCP server that builds a persistent SQLite-backed code graph from tree-sitter analysis. It exposes source search, graph search, architecture summaries, call-path tracing, change-impact mapping, snippets, and read-only graph queries without requiring an external LLM or hosted API.

This is a better fit than Graphify for the first code-intelligence pilot because it is narrower, easier to isolate, available on Windows, and directly exposes MCP tools. Graphify remains declined as a parallel pilot; it may be reconsidered only if Codebase Memory MCP fails a named cross-source or visualization requirement.

## Approved future pilot boundary

A future `PILOT-CODE-INTELLIGENCE-1` may test the official binary through a Soma-owned process boundary. It is not active after this decision.

The pilot must use:

- an explicitly pinned release and verified checksum;
- manual binary placement or installer `--skip-config`; never automatic agent configuration;
- an explicit Soma `project_id -> approved repository resource -> provider project` binding;
- `CBM_ALLOWED_ROOT` restricted to the approved repository root;
- `CBM_CACHE_DIR` outside the repository;
- auto-index disabled initially;
- auto-watch disabled initially;
- explicit indexing only;
- no committed `.codebase-memory/` graph artifact;
- no modification of `.claude`, `.codex`, `AGENTS.md`, hooks, skills, shell profiles, or global MCP configuration;
- one controller and no subagent swarm;
- local-only processing and no push.

## Allowed pilot capabilities

The pilot may evaluate only read/derive operations needed for coding assistance:

- `index_repository`;
- `list_projects` and `index_status`;
- `get_graph_schema`;
- `search_graph` and `search_code`;
- `trace_call_path`;
- `detect_changes`;
- `get_code_snippet`;
- `get_architecture`;
- read-only `query_graph`.

## Excluded capabilities

- `manage_adr`, because architectural decisions remain owner-authored Markdown/Soma evidence;
- `ingest_traces` in the first pilot;
- automatic installer edits to agent configuration or instruction files;
- background watchers or auto-indexing before explicit reliability acceptance;
- provider-owned project identity inference from current working directory;
- provider graph artifacts committed to the repository;
- replacement of `RepoWikiService`, Git, source files, Obsidian/MCP Connector, the preserved Basic Memory fallback, or Soma evidence;
- production controller dependency before a separate acceptance decision.

## Acceptance questions for a future pilot

1. Can it index the approved Soma repository on Windows without changing the repository or agent configuration?
2. Do structural queries materially reduce file reads and tokens while preserving correctness?
3. Can every answer be grounded to exact source files, symbols, and repository generation?
4. Does explicit project selection prevent cross-repository leakage?
5. Can the cache be deleted and rebuilt completely from the repository?
6. Does cancellation, restart and stale-index detection behave safely?
7. Does it add value beyond the incumbent `RepoWikiService` rather than duplicating it?

Failure leaves the existing repository tools and wiki untouched. No custom code-intelligence engine is authorized merely because this candidate fails; only a named minimum gap may be considered afterward.

## Official project reviewed

- `DeusData/codebase-memory-mcp`
- Current official README reviewed on 2026-07-28.
- License: MIT.
