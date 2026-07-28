# MEMORY-PROVIDER-SOLUTION-DISCOVERY-2 — Trustworthy Local Project Memory

**Date:** 2026-07-28
**Status:** accepted discovery; provider pilot executed and documentation-closed; production integration has not started.
**Decision level:** C — foundational durability and continuity boundary.
**Method:** `preimplementation-solution-discovery` plus the owner's evidence-first, reversible, lowest-complexity decision rules.
**Post-pilot disposition:** Basic Memory `0.22.1` passed the complete-rebuild, interrupted-rebuild, bilingual, isolation, freshness, restart and removal gates with outcome `accept_with_minimal_soma_health_and_binding_guard`. The authoritative result is [`PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md`](PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md); the accepted production boundary is [`BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md`](BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md).

## Capability

Provide local, project-scoped semantic memory over owner-readable Markdown so a fresh AI controller can recover current project context without trusting an opaque or silently incomplete derived index.

The provider must remain replaceable. Markdown + Git are canonical; Obsidian remains the owner workspace; Soma owns exact project identity, provider binding, routing, provenance, health acceptance and lifecycle decisions.

## Hard requirements

- rebuild every derived index from unchanged canonical Markdown;
- expose enough evidence to distinguish complete, incomplete, degraded and failed state;
- never present an incomplete or unavailable index as healthy success;
- support useful English and Persian retrieval, including both cross-language directions;
- detect out-of-band create, edit, rename and delete operations within a bounded interval;
- reject or prevent ambiguous project selection and sibling-project leakage;
- preserve ordinary Markdown and Git compatibility through restart, cancellation, rebuild and removal;
- run locally on the owner's Windows 11 laptop without hosted embeddings or cloud memory;
- remain behind a narrow Soma-owned binding, health and provenance boundary;
- require no custom storage, embeddings, ranking, semantic search or graph engine.

## Non-goals

- choosing a universally best memory product;
- building a custom Soma retrieval engine;
- running multiple provider pilots in parallel;
- importing private or production memory during comparison;
- solving every Obsidian file-management workflow before retrieval is trustworthy;
- treating enterprise multi-user threat assumptions as requirements for a single-owner loopback laptop.

## Failing layers identified

### Index rebuild and completeness

The frozen MCP Connector `0.28.1` release produced a one-record semantic index for a seven-note vault after rebuild attempts. This is a provider index-lifecycle failure.

### Stale success

The same provider served results with `status: ok` from the one-record index and supplied no completeness signal. This is a provider health-contract failure and the decisive blocker.

### Rename and link integrity

The unattended Obsidian rename path moved files, hung and did not rewrite incoming links. The pilot did not record the Obsidian **Automatically update internal links** setting, so the root cause is not yet established. This remains a reproducible unsafe operation, but not proven evidence that Obsidian's link-aware API is fundamentally broken.

### Tool-surface expansion

The frozen release exposed activation tools in Core despite the intended fixed profile. On the owner's personal loopback-only laptop this is a manageable integration weakness rather than a provider-selection blocker. Soma can enforce an exact allowlist. The current upstream README states that Core does not expose activation tools, so a later release re-test should verify the shipped artifact rather than trust documentation alone.

## Current source findings

Basic Memory's current official documentation establishes a serious next candidate:

- local Markdown is canonical and the database is a secondary index;
- Windows x86-64 is supported for the default local FastEmbed path;
- `bm reindex --full`, project-specific reindex and `bm reset --reindex` are official rebuild paths that retain files;
- `bm project info --json` reports project statistics and embedding coverage;
- project resolution can be constrained with `BASIC_MEMORY_MCP_PROJECT`, while `default_project = null` disables automatic fallback;
- the local embedding model, dimensions and similarity threshold are configurable;
- filesystem sync is enabled by default with a documented debounce;
- MCP tools expose explicit project parameters and external project IDs.

These are claims to test, not acceptance evidence.

Current research also corrected three external leads:

- **SeekLink** has strong read-only `status` and `doctor` surfaces and hybrid retrieval, but its own package documentation says Windows is not a first-class supported path and its demonstrated bilingual focus is English/Chinese, not Persian.
- **Obsidian Semantic MCP** offers direct filesystem watching, explicit reindexing, PostgreSQL/pgvector and Ollama, but introduces a substantially heavier Docker/database/model stack and its installer registers global MCP configuration.
- **Semantic Search for Obsidian** is an experimental UI plugin using generated CSV files and a configured embedding API; its official repository does not establish a production MCP server. It is not a current provider candidate.

## Serious shortlist

| Criterion | Basic Memory Local | Later MCP Connector release | Alternative provider after failure | Custom Soma engine |
|---|---|---|---|---|
| Canonical Markdown | Pass by documented architecture; verify | Pass in pilot | Candidate-dependent | Possible but duplicates mature work |
| Rebuild and health evidence | Unknown; strongest official controls | Failed in `0.28.1` | Unknown | Could build, but high burden |
| English/Persian retrieval | Unknown; configurable local model | Same-language passed; cross-language failed | Unknown | Unknown and unnecessary now |
| Windows fit | Documented Windows x86-64 support | Native Obsidian/Windows | SeekLink weak; heavier option possible | High implementation cost |
| Project isolation | Explicit constraint available; verify | Passed strongly | Unknown | Would duplicate Soma authority |
| Replaceability | High behind process/MCP boundary | High | Candidate-dependent | Low because Soma would own the engine |
| Complexity | Low-to-medium | Lowest if fixed upstream | Medium-to-high | Highest |
| Decision | **Next bounded pilot** | Preserve for release re-test | Research only after Basic Memory failure | Reject |

## Black-box provider contract

The comparison harness treats the provider as an opaque, untrusted process and uses OS-level Markdown truth plus deterministic queries.

### 1. Per-file ingestion canaries

Every synthetic note receives:

- a unique lexical token for exact text search;
- a unique natural-language concept for semantic paraphrase search.

One canary proves only one file. The gate therefore verifies every file in the small corpus rather than calling a single sentinel “completeness.”

### 2. Bilingual matrix

Run all four directions against fixed English and Persian notes:

- English note → English query;
- Persian note → Persian query;
- Persian note → English query;
- English note → Persian query.

The corpus avoids shared proper nouns and copied wording that could create accidental lexical matches.

### 3. Explicit accounting

Compare the OS manifest with provider statistics and indexed-note/embedding coverage where available. Every eligible path must be accounted for as indexed, intentionally excluded, zero-content or failed. A bare `ok` is insufficient.

### 4. Rebuild and restart

Delete provider state while retaining Markdown, use only official full rebuild/reset commands, verify every per-file canary, restart repeatedly, and repeat the checks. An interrupted rebuild must not become healthy until recovery is complete.

### 5. Filesystem desynchronization

Create, edit, rename and delete notes through the OS. Verify that the provider returns the new content/path, stops returning the old path and removes deleted content within the bounded synchronization interval.

This tests watcher and index freshness. It does not claim that an OS rename should rewrite Obsidian wikilinks.

### 6. Abstention, not forced noise

A nonsense query may legitimately return no results because Basic Memory documents a minimum similarity threshold. Empty results are not proof of a dead index, and low or negative nearest-neighbour results are not proof of health. Index health is established independently through known-hit canaries and accounting.

### 7. Minimum provider-specific safety

Evidence from MCP Connector does not transfer to Basic Memory. The new provider still receives a compact project-constraint, sibling-isolation, Markdown-integrity and clean-removal check. These checks are safety prerequisites, not a repeated broad benchmark.

## Decision

**Adopt for pilot, then wrap only if it passes:** execute one focused Basic Memory Local compatibility gate through a single project-constrained process per synthetic Soma project.

The decisive sequence is:

1. prove complete rebuild and fail-closed health;
2. prove a working local multilingual model and the four-direction bilingual matrix;
3. prove OS create/edit/rename/delete freshness;
4. run only the minimum provider-specific project isolation and Markdown safety checks;
5. cleanly remove all provider state.

Do not begin a SeekLink, Obsidian Semantic MCP or MCP Connector re-test in parallel. Do not build a custom retriever.

## Why this is the best patch

- It attacks the exact blocker first instead of broadening the benchmark.
- Basic Memory already documents official rebuild, reset, project constraint, project statistics, local Windows embeddings and configurable models.
- It keeps the architecture reversible: Markdown and Soma identity remain independent of the provider.
- It avoids throwing away MCP Connector's excellent retrieval and isolation evidence; a later fixed release can re-enter through the same black-box contract.
- It fits the owner's actual threat model: health and correctness are critical, while local tool expansion is handled by a cheap Soma allowlist.
- It converts Gemini's useful black-box idea into correct tests without adopting the incorrect “empty result means dead index” rule.

## Reversibility

The provider receives no canonical authority. Soma stores only the exact project/provider binding, frozen provider/model generation, health disposition and source provenance. Removing the provider leaves Markdown + Git and Obsidian intact.

The same black-box contract can later test a new MCP Connector release or one alternative provider without changing the canonical memory model.

## Replacement triggers

Reopen provider selection when:

- Basic Memory fails complete rebuild or serves stale success after one clean rerun;
- no supported local model passes the English/Persian matrix;
- Windows process reliability repeats a fatal failure;
- project isolation or canonical Markdown integrity fails;
- a newer MCP Connector release explicitly changes the failed index/health behavior and passes a source-diff preflight;
- a different Windows-capable provider demonstrates materially better health evidence with no unacceptable complexity.

## Compact preflight

### Capability
Trustworthy local, project-scoped semantic memory over canonical Markdown.

### Decision level
C.

### Existing solutions checked
MCP Connector `0.28.1`, Basic Memory Local, SeekLink, Obsidian Semantic MCP and Semantic Search for Obsidian.

### Shortlist
1. Adopt/validate: Basic Memory Local.
2. Re-test later: a materially changed MCP Connector release.
3. Alternative after failure: one Windows-viable ready-made provider selected by a fresh bounded comparison.

### Hardest requirement
Delete all derived state, rebuild from Markdown, prove every synthetic file is represented, and prove incomplete state cannot masquerade as healthy.

### Spike result
Basic Memory `0.22.1` passed complete rebuild from deleted derived state, failed closed from a deliberately partial interrupted rebuild, returned all four English/Persian directions at rank 1 under the frozen multilingual model, preserved sibling isolation, reflected filesystem changes, survived three restart cycles and removed cleanly. It requires a Soma guard because omitted identity routes, unknown identity attempts cloud routing, provider health commands do not prove project completeness and first sync rewrites canonical Markdown.

### Recommended path
Proceed only through [`BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md`](BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md). Do not begin another provider comparison.

### Remaining unknowns
- whether disabling `ensure_frontmatter_on_sync`, or the exact supported equivalent, preserves full provider operation while leaving canonical Markdown byte-identical;
- the exact production manifest-versus-provider coverage evidence available through the narrow adapter;
- whether the measured multilingual threshold remains suitable beyond the frozen pilot corpus.

### Implementation gate
**Proceed with the minimal guard only after a no-mutation confirmation.** The decision authorizes no production memory import, client configuration or push.

## Primary sources reviewed

- `https://docs.basicmemory.com/reference/cli-reference`
- `https://docs.basicmemory.com/reference/configuration`
- `https://docs.basicmemory.com/concepts/semantic-search`
- `https://docs.basicmemory.com/reference/mcp-tools-reference`
- `https://docs.basicmemory.com/reference/technical-information`
- `https://github.com/istefox/obsidian-mcp-connector`
- `https://github.com/istefox/obsidian-mcp-connector/blob/main/CHANGELOG.md`
- `https://github.com/obsidianmd/obsidian-help/blob/master/en/Linking%20notes%20and%20files/Internal%20links.md`
- `https://pypi.org/project/seeklink/`
- `https://github.com/celstnblacc/obsidian-semantic-mcp`
- `https://github.com/bbawj/obsidian-semantic-search`
