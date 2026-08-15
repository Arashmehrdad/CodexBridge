# Canonical Soma Project Memory Contract

**Status:** normative controller contract  
**Canonical vault:** `D:\SomaMemory\projects\<project_id>`

## Meaning of “project memory”

When the owner says **project memory**, **Soma project memory**, **update project memory**, or equivalent wording while Soma is the named runtime, the request targets Soma’s canonical external-vault project memory.

The request is satisfied only by the canonical `memory_*` workflow exposed through `knowledge_query` and `knowledge_action`.

Creating or updating any of the following does **not** satisfy the request:

- `MEMORY.md` or another controller-local memory file;
- `docs/PROJECT_MEMORY.md` or another repository handoff document;
- `.soma/wiki/` or `refresh_wiki`;
- `remember_decision`, `save_knowledge`, or another legacy repository-knowledge write;
- an ordinary repository file created as a substitute for canonical memory.

A repository handoff document or wiki refresh may be performed **in addition** when separately required. It is never a substitute for canonical memory.

## Distinct Soma-owned surfaces

1. **Canonical project memory** — owner-readable Markdown under `D:\SomaMemory\projects\<project_id>`, addressed through an exact ProjectScope and written by `memory_save` or `memory_supersede`.
2. **Repository handoff documents** — Git-versioned project files such as `docs/PROJECT_MEMORY.md`, edited through repository operations.
3. **Generated repository wiki** — disposable `.soma/wiki` cache refreshed by `refresh_wiki`.
4. **Legacy repository knowledge** — non-canonical Markdown under `runs/knowledge/projects/<project_id>/vault`, written by legacy operations such as `save_knowledge`.

These surfaces have different authority and lifecycle rules. Controllers must not merge them merely because each may contain the word “memory.”

## Required canonical workflow

1. Call `knowledge_query(operation="memory_scope", repo_name="...")`.
2. When the repository is known but unbound, call `knowledge_action(action="memory_bind_repository", repo_name="...")`, then call `memory_scope` again. `memory_scope` is read-only and must never create authority.
3. Retrieve relevant current records through `memory_search` or `memory_context`.
4. Use `memory_save` for a new independent durable record. Use `memory_supersede` only when the successor and every predecessor are unambiguous from the existing record chain and project authority.
5. If several records could plausibly be the predecessor and Soma has no contractual basis to choose, stop and report the ambiguity. Do not guess, silently fork the chain, or replace records by title or `kind` alone.
6. Verify the exact write through `memory_get`.
7. Check `memory_health` for structural canonical-vault and catalog integrity. A structurally `healthy` result does not prove lineage coherence or repository freshness.

Every mutation must keep the exact ProjectScope explicit. Repository discovery and current working directory are not authority for a memory write.

## Wiki and handoff separation

`refresh_wiki` is a separate cache operation. Its branch, HEAD, generation, and stale fields verify wiki freshness only.

A repository handoff such as `docs/PROJECT_MEMORY.md` is repository documentation. It may be updated and committed under that repository’s own rules, but it does not mutate canonical Soma memory.

## Completion statement

A controller claiming that Soma project memory was updated must identify:

- the resolved ProjectScope;
- the canonical operation used;
- the written `knowledge_id` and vault path;
- the exact `memory_get` verification;
- structural `memory_health` status;
- any unresolved lineage or freshness ambiguity.

Without that evidence, the controller must not claim that canonical Soma project memory was updated.
