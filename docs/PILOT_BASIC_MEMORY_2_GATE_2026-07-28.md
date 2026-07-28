# PILOT-BASIC-MEMORY-2 — Provider Health and Bilingual Compatibility Gate

**Date:** 2026-07-28
**Status:** gate prepared; execution has not started.
**Decision source:** [`MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md`](MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md)
**Supersedes before execution:** [`PILOT_BASIC_MEMORY_1_GATE_2026-07-28.md`](PILOT_BASIC_MEMORY_1_GATE_2026-07-28.md)
**Scope:** one focused disposable Basic Memory Local compatibility trial.

## Purpose

Determine whether Basic Memory Local can provide trustworthy local project memory over canonical Markdown by passing the exact failures that stopped MCP Connector `0.28.1`:

1. complete rebuild from files;
2. no stale healthy success from an incomplete index;
3. working English/Persian same-language and cross-language retrieval;
4. bounded out-of-band file freshness.

This gate adds only minimum provider-specific project-isolation, Markdown-integrity and removal checks. It is not a broad benchmark and does not compare multiple providers in parallel.

## Execution authority

A subsequent owner instruction such as `continue` executes only this gate through one controller. It does not authorize production integration, a second provider pilot, custom retrieval, code-intelligence work or push.

No coding agent or subagent participates. The controller uses official Basic Memory commands and MCP tools plus standard OS file operations against disposable state.

## Fixed boundaries

- Resolve the current official Basic Memory Local release immediately before installation and freeze version, source, installer/runtime version and available cryptographic hashes.
- Disable automatic provider updates for the pilot after the release is frozen.
- Install only in an isolated disposable environment under `runs/pilots/basic-memory-2/`; do not modify Soma's `.venv` or global Python tooling.
- Do not modify PATH, shell profiles, global MCP configuration, Claude/Codex settings, `AGENTS.md`, hooks, skills or repository source.
- Use local mode only. Do not enable Basic Memory Cloud, remote sync, hosted embeddings, OpenAI embeddings, telemetry or promotions.
- Use only local FastEmbed-compatible models supported by the frozen official release.
- Use synthetic notes only. Do not import production project notes, private conversations, owner memory, `.soma/wiki/`, Hermes memory or secrets.
- Keep provider configuration, databases, embeddings, caches and model files disposable and outside tracked repository paths.
- Do not mutate live ProjectScope, Soma memory tables, MCP schemas, production bindings or controller configuration.
- Do not patch provider source. A defect is evidence.
- Do not push.

## Threat model and tool boundary

This is a single-owner personal Windows laptop. Local tool-surface expansion is not a provider-selection blocker by itself.

Any future integration must still place Basic Memory behind a Soma allowlist and exact project binding, but this gate does not build that adapter. It proves whether the provider itself is trustworthy enough to justify a later minimal wrapper.

## Exact project setup

Create exactly two similar disposable projects:

1. provider project `soma-pilot`, associated in evidence with Soma project ID `proj_a144f759-1619-4276-9292-28704b6611f4`;
2. provider project `soma-lab-pilot`, associated with synthetic Soma project ID `proj_0cf013d0-191b-57f4-a84b-7a43819a1578`.

Record each provider external project UUID and Markdown root.

Run one Basic Memory MCP process per project with `BASIC_MEMORY_MCP_PROJECT` set to the exact project. Set `default_project = null` where supported. Every MCP operation must also name the explicit project when the tool accepts one.

The compatibility boundary passes only if:

- omitted or wrong project identity cannot silently route to the sibling project;
- each process remains constrained to its approved project;
- no sibling result appears in any known-hit or nonsense query;
- provider external IDs and paths remain stable across restart.

## Frozen synthetic corpus

Use 14 Markdown notes: seven per project. Keep structure and note count fixed after the corpus is frozen.

Every note contains:

- one unique cryptographically random lexical canary;
- one unique natural-language semantic concept;
- a stable physical filename;
- ordinary frontmatter and at least one ordinary wikilink.

The two projects contain deliberately conflicting facts and parallel topics so accidental sibling leakage is visible.

Create at least:

- two English notes;
- two Persian notes;
- one English/Persian paired concept in each direction;
- one empty or frontmatter-only note to test explicit zero-content accounting;
- one note reserved for out-of-band edit/rename/delete operations.

Freeze and hash:

- every file path and byte content;
- the OS Markdown manifest;
- lexical canaries;
- semantic questions and expected note paths;
- link expectations;
- project mapping.

Do not tune note wording after results.

## Test order — hardest requirement first

### Phase A — installation and preflight

1. Freeze the official release and isolated installation path.
2. Verify the provider's version/help output and exact configuration.
3. Confirm no global or client configuration changed.
4. Record available official status, project-info, reindex, reset, sync and MCP surfaces.
5. Resolve and freeze one local multilingual FastEmbed model supported by the release. If none can be configured locally, record a hard requirement failure and stop before broad testing.

### Phase B — initial accounting and known-hit proof

1. Create the frozen corpus through OS file writes.
2. Wait no longer than ten seconds after the provider's documented sync debounce unless official status reports active work.
3. Capture OS file count and hashes.
4. Capture `bm status`, `bm project info --json`, sync status and any embedding-coverage or indexed-note telemetry.
5. Query every lexical canary through exact/literal search; each note must return itself at rank 1.
6. Query every natural-language canary through semantic or hybrid search; each intended note must appear in the first three results.
7. Record every path, rank, score, provider state and sibling result.

A single sentinel is not completeness evidence. Every eligible synthetic file must be accounted for.

### Phase C — delete and rebuild from canonical Markdown

1. Stop the constrained MCP processes cleanly.
2. Hash the canonical Markdown again.
3. Delete only provider databases, search indexes and embeddings while retaining Markdown.
4. Use official `bm reset --reindex`, `bm reindex --full` or the exact current equivalent, targeted to each project.
5. Capture command output, exit status, elapsed time and provider telemetry.
6. Restart the constrained MCP processes.
7. Repeat every lexical and semantic known-hit query.
8. Reconcile OS manifest, provider note count, embedding coverage and indexed paths.
9. Require canonical Markdown to remain byte-identical.

Pass requires all eligible files to be accounted for and all non-zero-content notes to pass their known-hit probes.

### Phase D — interrupted rebuild and stale-success check

1. Start one clean full rebuild after deleting derived state.
2. Interrupt the provider once during active indexing using the narrowest process stop available.
3. Restart without changing Markdown.
4. Query status and one known hit before recovery is complete.
5. The provider must report incomplete/degraded/building state or refuse semantic success; it must not claim healthy completeness from a partial index.
6. Complete one official recovery/rebuild and repeat all known-hit and accounting checks.

If partial state is served as healthy success, rerun once from zero provider state. A second occurrence is an immediate rejection.

### Phase E — bilingual matrix

Using the frozen local multilingual model, run all four directions:

- English note → English query;
- Persian note → Persian query;
- Persian note → English query;
- English note → Persian query.

Each expected note must appear in the first three results, with no sibling-project result. Queries must not copy distinctive proper nouns, dates or canary tokens from the note.

The default English-only model may be measured as diagnostic evidence but does not satisfy this requirement.

### Phase F — filesystem freshness

Using standard OS operations rather than provider write tools:

1. create a note and verify retrieval at the new path;
2. edit its unique concept and verify the old concept disappears and the new concept appears;
3. rename the file and verify the new path is returned and the old path disappears;
4. delete the file and verify it is no longer returned.

Use a bounded ten-second wait after each change unless provider telemetry reports active work. One clean rerun is allowed for a timing-only miss.

This phase tests watcher and index freshness. It does not require an OS rename to rewrite Obsidian wikilinks.

### Phase G — project isolation and omission

- run the same lexical and semantic questions against both constrained processes;
- deliberately pass the sibling project name/UUID where the official tool permits;
- omit project identity where possible;
- verify that no operation silently falls back into the wrong project;
- record whether the provider itself fails closed or a minimal Soma binding guard would be required.

Provider evidence from MCP Connector is not inherited here.

### Phase H — safe abstention

1. Record the configured `semantic_min_similarity` or current equivalent.
2. Send one fixed nonsense query.
3. Accept an empty result or explicit low-confidence abstention.
4. Do not treat unrelated low-score output as proof that the index is healthy.
5. Establish health only through known-hit probes and accounting.

A temporary diagnostic run with threshold zero may be used to inspect raw scores, but it cannot determine acceptance.

### Phase I — Markdown, Obsidian and link behavior

- open or inspect the same Markdown roots with Obsidian without conversion;
- verify provider metadata remains human-readable and Git-compatible;
- verify ordinary wikilinks remain intact through provider sync/rebuild;
- prefer stable physical filenames with editable `title`/`aliases` for normal memory evolution;
- record the provider's optional `update_permalinks_on_move` behavior separately;
- do not reject the provider merely because an OS rename does not rewrite Obsidian links.

The previous MCP Connector link-aware rename issue requires a separate later re-test with Obsidian's **Automatically update internal links** setting explicitly recorded.

### Phase J — restart, removal and cleanup

- complete three clean stop/start cycles;
- repeat representative known-hit, bilingual and project-isolation queries after each restart;
- remove the provider runtime, databases, embeddings, caches and disposable configuration;
- verify canonical Markdown remains readable and complete;
- hash final evidence, then remove the disposable Markdown projects;
- confirm no provider processes, listeners, global configuration or residue remain.

## Acceptance outcomes

Return exactly one outcome.

### `accept_basic_memory_provider`

Use only when complete rebuild, interrupted-rebuild health, bilingual retrieval, filesystem freshness, project isolation, Markdown integrity, Windows reliability and clean removal all pass without requiring Soma changes beyond an ordinary adapter.

### `accept_with_minimal_soma_health_and_binding_guard`

Use only when provider behavior otherwise passes but project omission or health evidence requires a thin Soma guard that:

- resolves exact `project_id -> provider UUID -> constrained process -> Markdown root`;
- rejects omitted, wrong or inactive project identity;
- compares provider project statistics/embedding coverage with an OS manifest;
- blocks semantic use when completeness cannot be proven;
- enforces an exact tool allowlist and validates returned paths;
- falls back to canonical literal Markdown access when semantic health is unavailable.

The guard may not implement storage, embeddings, ranking, semantic search, graph traversal or provider repair.

### `reject_basic_memory_activate_single_alternative_discovery`

Use when complete rebuild or stale-success fails twice, no local multilingual model passes, Windows reliability repeats a fatal failure, sibling isolation fails, canonical Markdown is damaged, or provider state cannot be cleanly removed.

Rejection does not automatically select another provider. It authorizes one bounded solution-discovery update choosing either a materially changed MCP Connector release or one Windows-viable ready-made alternative.

### `inconclusive`

Use only for one reproducible harness or environment defect that prevents judging provider behavior. Permit one bounded correction and rerun; do not broaden the lane.

## Stop conditions

Stop and preserve evidence when:

- any sibling-project result appears in a scoped operation;
- incomplete derived state is reported or served as healthy twice;
- canonical information exists only in provider state;
- Markdown corruption appears;
- no supported local multilingual model can be configured;
- a repeated Windows fatal interpreter/database failure occurs;
- global/user/client/repository configuration changes outside the approved root;
- cloud, remote sync, hosted embeddings or private memory are required;
- provider source modification or custom retrieval is proposed;
- cleanup cannot safely remove generated state;
- unrelated repository changes appear;
- the pilot exceeds one focused controller session without a single bounded blocker.

A stop is a valid result.

## Required evidence

The result must record:

- frozen provider, installer/runtime and model versions with hashes;
- isolated paths and proof no global/client configuration changed;
- both Soma IDs, provider IDs, constrained process settings and Markdown roots;
- frozen corpus manifest, canaries and question hashes;
- OS manifest versus provider note/embedding accounting before and after rebuild;
- every known-hit result with path, rank and score;
- interrupted-rebuild state and stale-success observation;
- all four bilingual directions;
- OS create/edit/rename/delete freshness;
- project omission, wrong-project and sibling-isolation results;
- Markdown/Obsidian/link observations;
- restart and cleanup proof;
- repository preflight showing a clean worktree, no active runs, no locks and no push;
- one exact acceptance outcome.

## After this gate

No production memory integration begins automatically.

- An acceptance result permits preparation of a minimal Soma adapter/health-guard decision only.
- A rejection permits one fresh, bounded alternative-provider discovery; no provider starts automatically.
- `PILOT-CODE-INTELLIGENCE-1` remains inactive until this result is documentation-closed.
- A generic `continue` while this gate is active executes this gate only and never authorizes push.
