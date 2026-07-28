# Memory Adoption Decision and PILOT-BASIC-MEMORY-1

**Date:** 2026-07-28
**Status:** decision accepted; bounded local provider pilot active.
**Starting HEAD:** `f5114ba29e4264f51319f20ddbc4ae57ecac2bb9`

## Decision

Use **Basic Memory Local** as the first ready-made memory provider candidate, with **Obsidian** as the owner-facing editor and visual workspace.

Soma remains the only authority for project identity, bindings, task continuity, provenance, acceptance, and routing. Basic Memory is a replaceable process/service behind a Soma-owned boundary. Its Markdown files are owner-readable canonical content for the pilot; its SQLite/vector index is derived and disposable.

The pinned pilot release is **Basic Memory 0.22.1**. The pilot uses local mode only, a dedicated configuration directory, a dedicated project root, local FastEmbed semantic search, no cloud account, no network embedding API, no automatic upgrade, and no telemetry or promotional events.

## Why this candidate wins the first trial

Basic Memory already provides the pieces the custom benchmark was beginning to recreate:

- plain Markdown files compatible with Git and Obsidian;
- MCP read/write/search tools;
- local SQLite indexing;
- local semantic and hybrid search on Windows;
- wikilinks, observations, relations, and context building;
- stable external project UUIDs and explicit `project_id` tool parameters;
- rebuildable indexes and official consistency tooling.

Obsidian alone remains the interface, not the AI memory service. Community semantic-search plugins are optional later UX choices; they do not replace a stable MCP provider boundary.

## Closure of PILOT-MEMORY-1B

`PILOT-MEMORY-1B` is closed as an **overbuilt experimental detour**. No Agent 2 correction, F1 expansion, two-day observation, production integration, or further custom retrieval development is authorized.

The experiment remains in Git as non-production evidence because it established one useful fact: exact lexical retrieval works well on literal wording, while paraphrased questions expose a meaning-retrieval gap. Its custom package is not a production component, is not imported by Soma runtime, and must not be extended into a competing memory engine.

## Provider boundary

For the pilot:

```text
Soma project_id
  -> exact provider binding
  -> one constrained Basic Memory project/process
  -> Markdown project directory
  -> derived Basic Memory index
  -> Obsidian opens the same Markdown directory
```

Basic Memory's own default-project fallback is not trusted as a Soma routing decision. Each pilot process is constrained to one approved provider project. Soma records the exact mapping between its project ID and the provider's external UUID. Controllers do not infer identity from a folder, project name, note path, conversation, or Obsidian vault name.

No Basic Memory project becomes canonical project authority. No provider identifier replaces Soma's `project_id`.

## Pilot configuration

- package: `basic-memory==0.22.1`;
- execution: pinned `uvx`, avoiding an automatically upgrading global installation;
- config isolation: `BASIC_MEMORY_CONFIG_DIR` points to a disposable pilot directory;
- project-root constraint: `BASIC_MEMORY_PROJECT_ROOT` points to the disposable pilot root;
- local routing: `BASIC_MEMORY_FORCE_LOCAL=true`;
- telemetry/promotions disabled: `BASIC_MEMORY_NO_PROMOS=1` and `cloud_promo_opt_out=true`;
- semantic provider: local FastEmbed;
- corpus: a small sanitized Markdown project outside tracked repository paths;
- generated index and configuration: disposable;
- no cloud sync, import of private conversations, production vault, or owner memory.

## Acceptance test

This is a product-fit test, not a model-training or scoring project. One controller runs it; no subagents.

Pass only when the pinned ready-made product demonstrates:

1. installation and startup on Windows from the isolated configuration;
2. creation and discovery of one provider project with its exact external UUID;
3. file creation through official Basic Memory tools and immediate readability as ordinary Markdown;
4. direct external Markdown editing followed by automatic or explicit reindex visibility;
5. exact search for literal identifiers;
6. semantic or hybrid retrieval of the four preserved paraphrase cases from the prior experiment;
7. relation/context navigation through official tools;
8. constrained project routing with no result from the sibling project;
9. deletion of the derived database followed by a complete rebuild from Markdown;
10. successful official status/doctor checks;
11. clean removal of the disposable project, config, and index;
12. zero Soma runtime/schema/store changes and no push.

Results are pass/fail with short factual notes. Do not build a custom evaluator, ranking layer, adapter framework, corpus generator, or benchmark package.

## Stop conditions

Stop rather than code around the provider when:

- Windows local operation is unreliable;
- project-constrained operation cannot be established;
- explicit provider UUID routing is unavailable or inconsistent;
- semantic search needs a hosted API;
- Markdown is not sufficient to reconstruct the provider index;
- the provider modifies or hides canonical files in a way Obsidian cannot use;
- removal would lose canonical knowledge;
- meeting the gate requires changes to Basic Memory source, a custom retrieval engine, or a second authority;
- any production Soma, Hermes, MCP, ProjectScope, `.soma/wiki/`, or owner-memory surface must change.

A failure selects a different ready-made candidate. It does not authorize custom memory construction.

## Decision after the pilot

- **Accept Basic Memory:** prepare a separate narrow Soma provider-binding proposal.
- **Reject Basic Memory:** preserve the exact failed requirement and test one alternative ready-made provider.
- **Inconclusive:** permit one configuration-only rerun; no source changes.

No production memory activation occurs in this lane.
