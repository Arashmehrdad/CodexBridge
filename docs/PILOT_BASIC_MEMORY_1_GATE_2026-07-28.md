# PILOT-BASIC-MEMORY-1 - Ready-Made Local Memory Compatibility Gate

**Date:** 2026-07-28
**Status:** historical; superseded before execution by [`PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md`](PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md).
**Original decision source:** [`MEMORY_PROVIDER_DECISION_2026-07-28.md`](MEMORY_PROVIDER_DECISION_2026-07-28.md)
**Replacement decision source:** [`MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md`](MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md)
**Scope:** preserved first-draft compatibility gate; it never executed.

## Supersession notice

This gate did not execute and authorizes no installation. `PILOT-OBSIDIAN-MCP-1` later produced the named provider-health failures, but the resulting research materially changed the test design. The executable successor is `PILOT-BASIC-MEMORY-2`, which tests rebuild completeness and stale-success first, adds the four-direction English/Persian matrix, separates filesystem freshness from Obsidian link rewriting, and retains minimum provider-specific isolation and Markdown-integrity checks.

## Historical purpose

Determine whether Basic Memory Local can serve as Soma's ready-made project-memory provider while preserving the accepted architecture:

- Markdown + Git remain canonical;
- Obsidian remains the owner-facing workspace;
- Basic Memory supplies local MCP/search/context capabilities as a replaceable process;
- Soma remains authority for exact project identity, provider binding, routing, provenance, continuity, and acceptance.

This is a product compatibility trial, not a model experiment. It includes no model training, fine-tuning, custom ranking, retrieval-engine development, benchmark framework, or provider source modification.

## Execution ownership

The historical pilot would have been executed by one controller through Soma using official provider commands and MCP tools, with no coding agent, subagent, or parallel Codebase Memory pilot.

This historical gate is not executable through a generic `continue` and cannot be reactivated. While the successor gate is active, a generic `continue` executes only `PILOT-BASIC-MEMORY-2`.

## Fixed boundaries

- Use one exact official Basic Memory release, resolved and recorded immediately before installation.
- Freeze the package version, installer/runtime version, download source, and available cryptographic hashes before the first measured operation.
- Use an isolated disposable directory under `runs/pilots/basic-memory-1/`; do not install globally or modify Soma's `.venv`.
- Do not modify PATH, shell profiles, global MCP configuration, Claude/Codex settings, `AGENTS.md`, hooks, skills, or repository source files.
- Force local operation. Do not enable Basic Memory Cloud, remote sync, promotions, telemetry, or hosted model/API dependencies.
- Use provider-built local embeddings only when supported by the frozen official release. Do not configure an external LLM or embedding API.
- Use synthetic or sanitized notes only. Do not import private conversation history, personal memory, production project notes, `.soma/wiki/`, Hermes memory, or owner secrets.
- Keep all provider configuration, project directories, databases, embeddings, caches, and model files disposable and outside tracked repository paths.
- Do not mutate live ProjectScope, Soma memory tables, MCP schemas, repository bindings, or production controller configuration.
- Do not patch Basic Memory source. A provider defect is evidence, not permission to repair the provider.
- Do not push.

## Identity and isolation setup

Use exactly two deliberately similar disposable projects:

1. `soma-pilot`, associated in pilot evidence with Soma project ID `proj_a144f759-1619-4276-9292-28704b6611f4`;
2. `soma-lab-pilot`, associated with synthetic Soma project ID `proj_0cf013d0-191b-57f4-a84b-7a43819a1578`.

After project creation, record each Basic Memory external project UUID. The pilot binding is:

```text
Soma project_id -> Basic Memory external project UUID -> disposable Markdown root
```

Every automated read, write, search, edit, context, and delete operation must name the provider project UUID or run inside an official single-project constraint. The trial must never treat Basic Memory's default-project fallback as authoritative.

Test omission explicitly. A project-less provider call may reveal provider behavior, but Soma compatibility passes only when the intended future boundary can reject omission before ambiguous provider routing. When the official provider cannot fail closed itself, record that as a named **minimal binding-guard requirement**, not as permission to build a memory engine.

## Disposable note set

Create 12-20 human-readable Markdown notes split across facts, decisions, lessons, and procedures. Include deliberately conflicting sibling-project facts, such as different runtime ports and concurrency limits, plus ordinary links between notes.

The note set must support these named questions without copying the question wording into titles:

- Which socket number accepts service connections?
- How many jobs may run at once?
- Why is hiding skipped review items dangerous?
- Can a read query stall the process saving data?
- What happens when a caller names the wrong project owner?
- Which procedure depends on taking a verified backup?

This is a small product check, not a scoring competition. For each question, record whether the intended note appears in the first three provider results and whether any sibling-project result appears. Do not calculate aggregate retrieval scores, train a model, tune note wording after results, or add a custom search layer.

## Required checks

### Installation and Windows reliability

- isolated installation succeeds without requiring a global compiler or global runtime change;
- version and help commands are repeatable;
- ten sequential official read/write/search operations complete without a fatal interpreter error;
- three clean stop/start cycles preserve files and provider index consistency;
- cancellation or forced stop leaves no corrupt canonical Markdown;
- `doctor` or the provider's official consistency check passes before and after restart.

### Markdown and Obsidian compatibility

- notes created by Basic Memory are ordinary readable Markdown;
- the disposable project root opens as an Obsidian vault or can be inspected through Obsidian without conversion;
- a manual/Obsidian edit is detected and searchable after the official sync/reindex path;
- a renamed and deleted note is reflected correctly;
- Basic Memory metadata does not prevent ordinary manual editing or Git tracking.

### Retrieval and context

- literal search retrieves the intended notes;
- built-in vector or hybrid search handles the six named paraphrases without a custom retriever;
- linked-context/build-context follows the small relation chain and remains grounded to source Markdown;
- result records expose enough path/permalink/source information for Soma to preserve provenance;
- no sibling-project note appears in a scoped result.

### Rebuild and removal

- delete only the provider database/index while retaining Markdown;
- rebuild completely using official commands;
- repeat representative literal, semantic, and linked-context queries successfully;
- remove the whole disposable provider runtime and configuration;
- confirm the canonical Markdown remains readable and complete before final cleanup;
- remove the disposable Markdown projects after evidence hashes are recorded.

## Preliminary observations to retest, not accepted evidence

A prematurely started disposable probe was removed and is not acceptance evidence. It surfaced three items that this gate must check deliberately:

- the first local project may become Basic Memory's default automatically;
- content/MCP tools expose external project UUIDs, while some maintenance commands may select projects by name;
- a batch of Windows CLI writes emitted a fatal interpreter-shutdown warning despite creating the files.

The gate starts from zero provider state and must reproduce or disprove these observations cleanly.

## Acceptance outcomes

The pilot returns exactly one result:

### `accept_ready_made_provider`

Use when official Basic Memory behavior is reliable, Markdown remains canonical, scoped operations remain isolated, Obsidian/manual edits work, retrieval is useful, and the index rebuild/removal succeeds. A narrow Soma process/MCP integration proposal may then be prepared.

### `accept_with_minimal_binding_guard`

Use only when the provider otherwise passes but cannot itself reject omitted project identity. The required Soma addition must be limited to exact binding validation and process routing; it may not implement storage, search, embeddings, ranking, graph traversal, or provider behavior.

### `reject_provider`

Use when Windows reliability repeatedly fails, project isolation cannot be trusted, canonical information exists only in provider state, external edits/rebuild are unreliable, semantic/context retrieval provides no useful gain, or clean removal fails.

### `inconclusive`

Use only for one reproducible test-harness or environment defect that prevents judging provider behavior. Permit one bounded correction; do not broaden the lane.

## Stop conditions

Stop immediately and preserve evidence when:

- any sibling-project result appears in a scoped operation;
- provider state becomes the only copy of canonical information;
- the provider or installer modifies global/user/repository configuration outside the disposable root;
- cloud routing, remote sync, telemetry, or hosted API use is required;
- private or production memory is needed to continue;
- Basic Memory source must be patched;
- a custom retrieval, embedding, ranking, graph, or benchmark implementation is proposed;
- Windows process shutdown or database corruption repeats after one clean rerun;
- generated state cannot be removed safely;
- unrelated repository changes appear;
- the pilot exceeds one focused controller session without a single bounded blocker.

A stop is a valid result. It does not automatically select Mem0, Cognee, Graphiti, or custom development.

## Required evidence

The final record must contain:

- frozen version/source/hash information;
- isolated paths used and proof no global configuration changed;
- both Soma IDs, provider UUIDs, and Markdown roots;
- exact official commands/MCP operations;
- per-check pass/fail observations and relevant output hashes;
- Windows restart and consistency results;
- project-omission and sibling-isolation results;
- Obsidian/manual-edit evidence;
- index deletion/rebuild evidence;
- cleanup proof;
- repository preflight showing a clean worktree, no running work, no locks, and no push;
- one of the four exact acceptance outcomes above.

## After this gate

`PILOT-CODE-INTELLIGENCE-1` remains planned but inactive and must not overlap this pilot. It may begin only after the Basic Memory result is documentation-closed.
