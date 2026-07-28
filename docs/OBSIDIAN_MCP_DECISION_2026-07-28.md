# OBSIDIAN-MCP-DECISION-1 - Obsidian-Native Memory Access

**Date:** 2026-07-28
**Status:** architecture accepted and documentation-closed; MCP Connector `0.28.1` was subsequently tested and rejected for the current provider lane.
**Decision scope:** architecture selection, provider ordering and post-pilot disposition; no production integration.
**Supersedes:** the Basic Memory-first ordering in [`MEMORY_PROVIDER_DECISION_2026-07-28.md`](MEMORY_PROVIDER_DECISION_2026-07-28.md).

## Decision

Use the lightest file-first architecture and validate providers behind it:

1. **Markdown + Git** remain the durable, owner-readable canonical content layer.
2. **Obsidian** remains the owner-facing workspace and preferred native surface over those files.
3. **MCP Connector by istefox** was the correct first candidate to test; frozen release `0.28.1` is rejected because rebuild completeness and healthy-state reporting could not be trusted.
4. **Soma** remains the sole authority for exact `project_id`, provider/vault binding, routing, provenance, health acceptance, continuity, and lifecycle decisions.
5. **Basic Memory Local** advances through the focused [`PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md`](PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md), prepared from [`MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md`](MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md).
6. A materially changed MCP Connector release may later re-enter through the same black-box provider contract; the architecture is not abandoned because one release failed.

No production vault, provider integration, client configuration, custom retrieval or owner-memory import is authorized by this decision.

## Why this aligns with the accepted plan

The accepted architecture required canonical Markdown + Git, Soma IDs and revision metadata, Obsidian as the owner-facing application, and the lightest available index before comparing Basic Memory.

Current Obsidian now supplies an official CLI and Bases over ordinary Markdown and properties. MCP Connector adds an in-process MCP server, local semantic embeddings, graph and metadata operations, and typed source-grounded results without introducing a separate memory service. This is therefore the closest ready-made implementation of the original Obsidian-first baseline.

## Selected candidate

The selected first candidate is the Obsidian community plugin **MCP Connector** (`istefox/obsidian-mcp-connector`). The version reviewed for this decision was `0.28.1`; the pilot must freeze the actual community-store release available at execution time.

Relevant provider characteristics:

- the MCP server runs inside Obsidian and listens only on hardcoded loopback HTTP;
- every request requires a per-vault bearer token;
- native semantic search runs on-device through Transformers.js;
- MiniLM, Gemma 300M and Multilingual-E5 providers are available without a hosted embedding API;
- semantic and text results are grounded to note paths and line positions;
- the embedding index is derived and incrementally updated by file;
- current upstream documentation describes Core as a fixed surface without activation tools, but the frozen `0.28.1` artifact exposed activation tools and could expand live; future acceptance must test the shipped artifact rather than trust documentation;
- command execution is opt-in, deny-by-default and remained disabled in the pilot;
- vault access uses Obsidian APIs, but the unattended rename path hung and left incoming links unchanged in the pilot; the Obsidian **Automatically update internal links** setting was not recorded, so the precise root cause remains unproven;
- the plugin is MIT-licensed and desktop-only.

## Post-pilot interpretation

The authoritative execution result is [`PILOT_OBSIDIAN_MCP_1_RESULT_2026-07-28.md`](PILOT_OBSIDIAN_MCP_1_RESULT_2026-07-28.md).

The decisive blockers are:

- an index rebuild that represented only one of seven notes;
- healthy-looking semantic success from that incomplete index;
- a multilingual configuration that silently produced no usable index or results.

The remaining findings are treated differently:

- **Rename:** the operation is unsafe as observed, but the pilot did not establish whether Obsidian was waiting for a link-update confirmation because the automatic-link-update setting was not frozen. A later connector re-test must record that setting and separate Obsidian UI rename, provider rename and raw OS rename.
- **Tool expansion:** on the owner's single-user, loopback-only personal laptop, this is a manageable integration weakness rather than a selection blocker. A future Soma boundary must expose an exact allowlist and never forward activation, open-world fetch, command-execution or destructive tools unless separately authorized.
- **Passed evidence:** MCP Connector proved excellent same-language semantic retrieval, strict sibling-vault isolation, authentication and canonical Markdown survival. That evidence supports the architecture and a future release re-test, but it does not transfer as a safety certificate to another provider.

## Intended boundary

```text
Soma project_id
  -> Soma-owned project/vault binding
  -> approved Obsidian vault root
  -> fixed loopback endpoint + secret reference
  -> MCP Connector Core tool surface
  -> ordinary Markdown and properties
  -> disposable local semantic index
```

Soma must validate the binding before every provider call. Provider defaults, active-vault state, current working directory, endpoint discovery, and note metadata must never infer or replace Soma project identity.

## Minimum permitted Soma addition

MCP Connector does not natively understand Soma `project_id`. The only custom work anticipated is a thin authority guard that:

- resolves an exact approved `project_id -> vault resource -> endpoint/token reference` binding;
- rejects omitted, unknown, suspended, archived or mismatched project identity before calling the provider;
- permits only the approved tool class and vault for that project;
- validates returned and written vault-relative paths;
- re-grounds durable answers to exact Markdown path, file hash and Git/source generation.

This guard may not implement storage, embeddings, ranking, semantic search, graph traversal, note lifecycle, or provider behavior.

## Non-overlap with Codebase Memory MCP

- **MCP Connector** serves owner-authored project knowledge, decisions, lessons, procedures, continuity, links, properties and semantic retrieval from the Obsidian vault.
- **Codebase Memory MCP** remains a separate derived index for source-code symbols, call paths, architecture and change impact.
- **Soma** owns project and repository identity, typed bindings, lifecycle, evidence and controller routing for both.

Neither provider replaces Git, the repository, `RepoWikiService`, canonical evidence, or the other provider's narrow concern.

## Candidate disposition

### MCP Connector - first pilot completed; current release rejected

It remained the best first test of the Obsidian-native baseline and proved real retrieval and isolation value. Release `0.28.1` is not accepted because incomplete index state could masquerade as healthy. Preserve it for a materially changed release re-test rather than production use.

### Semantic Notes Vault MCP - runner-up

Retained as a security-oriented alternative because it documents path and permission controls. It is not selected first because the available documentation does not establish the same native on-device vector-retrieval capability as clearly as MCP Connector.

### Analogy - deferred

Provides native vault embeddings, ChromaDB and a companion MCP server, but is younger and operationally heavier. It may be reconsidered only if MCP Connector fails a named semantic or scope requirement.

### Basic Memory Local - next focused provider pilot

It is now the selected candidate for one bounded health and bilingual compatibility gate. The gate tests full rebuild, interrupted-rebuild state, English/Persian retrieval, filesystem freshness and minimum provider-specific isolation/Markdown safety. It is not accepted or integrated yet.

### Obsidian Memory MCP - not selected as authority

Its transparent Markdown entities and wikilinks are useful design references, but an agent-maintained entity/relation authority would overlap with Soma provenance, supersession and lifecycle ownership.

## Known risks to measure

- Obsidian must be running for the in-process server.
- The plugin is a community plugin and is not manually audited by Obsidian staff.
- The provider does not supply Soma project identity and may require one vault per project for strong isolation.
- Multiple enabled vaults can contend for the default port unless unique fixed ports or sequential activation are used.
- The first native model use downloads and caches an embedding model locally.
- Windows `mcp-remote` behavior is irrelevant to this pilot because Soma must test direct loopback HTTP rather than editing external client configurations.
- The plugin exposes open-world and write capabilities that must be disabled or excluded from the first phase.

## Current decision rule

- Execute only `PILOT-BASIC-MEMORY-2`, hardest requirement first.
- Accept a provider only when derived state can be deleted and rebuilt from Markdown, every eligible synthetic file is accounted for, and incomplete state cannot masquerade as healthy.
- Permit only a minimal Soma binding/health/provenance guard after provider acceptance; do not implement provider behavior.
- On Basic Memory rejection, perform one fresh bounded alternative discovery. Do not automatically install SeekLink, Obsidian Semantic MCP, a new MCP Connector release or a custom retriever.
- Keep `PILOT-CODE-INTELLIGENCE-1` inactive until the memory result is documentation-closed.

## Official sources reviewed

- MCP Connector community-plugin documentation: `https://community.obsidian.md/plugins/mcp-tools-istefox`
- MCP Connector repository: `https://github.com/istefox/obsidian-mcp-connector`
- Obsidian CLI documentation: `https://obsidian.md/help/cli`
- Obsidian Bases documentation: `https://obsidian.md/help/bases`
- Obsidian 1.12 CLI changelog: `https://obsidian.md/changelog/2026-02-10-desktop-v1.12.0/`
