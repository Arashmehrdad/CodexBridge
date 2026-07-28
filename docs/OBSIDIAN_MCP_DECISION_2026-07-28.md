# OBSIDIAN-MCP-DECISION-1 - Obsidian-Native Memory Access

**Date:** 2026-07-28
**Status:** accepted and documentation-closed.
**Decision scope:** architecture selection and provider ordering only; no plugin installation or pilot execution.
**Supersedes:** the Basic Memory-first ordering in [`MEMORY_PROVIDER_DECISION_2026-07-28.md`](MEMORY_PROVIDER_DECISION_2026-07-28.md).

## Decision

Use the lightest Obsidian-native stack first:

1. **Markdown + Git** remain the durable, owner-readable canonical content layer.
2. **Obsidian** is both the owner-facing workspace and the first runtime surface for structured and automated access.
3. **MCP Connector by istefox** is the selected first candidate for local semantic retrieval and MCP access inside Obsidian.
4. **Soma** remains the sole authority for exact `project_id`, vault binding, routing, provenance, acceptance, continuity, and lifecycle decisions.
5. **Basic Memory Local** is deferred as a headless fallback and advances only after a named Obsidian-native failure.

No plugin, vault, model, client configuration, or production-memory integration is authorized by this decision alone.

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
- the fixed Core profile exposes a small static tool surface and cannot self-promote additional tools;
- command execution is opt-in, deny-by-default and must remain disabled in the first pilot;
- vault access uses Obsidian APIs, preserving normal link-aware rename and metadata behavior;
- the plugin is MIT-licensed and desktop-only.

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

### MCP Connector - selected for the first pilot

Best fit for the Obsidian-first baseline because it combines local semantic retrieval, graph access, structured note operations and a local authenticated MCP endpoint without a second memory service.

### Semantic Notes Vault MCP - runner-up

Retained as a security-oriented alternative because it documents path and permission controls. It is not selected first because the available documentation does not establish the same native on-device vector-retrieval capability as clearly as MCP Connector.

### Analogy - deferred

Provides native vault embeddings, ChromaDB and a companion MCP server, but is younger and operationally heavier. It may be reconsidered only if MCP Connector fails a named semantic or scope requirement.

### Basic Memory Local - headless fallback

Remains the preferred fallback when Obsidian cannot remain running reliably, independent/headless operation is mandatory, or a safe project boundary cannot be achieved with the Obsidian-native stack.

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

## Decision rule after the pilot

- Accept the Obsidian-native stack when local semantic retrieval, structured access, restart behavior, project isolation, rebuild and removal all pass.
- Accept with only a minimal Soma binding guard when the provider passes but cannot itself reject missing Soma project identity.
- Activate the preserved Basic Memory comparison only after a named headless, reliability, or isolation failure.
- Do not move directly to Mem0, Cognee, Graphiti, Analogy or custom retrieval development.

## Official sources reviewed

- MCP Connector community-plugin documentation: `https://community.obsidian.md/plugins/mcp-tools-istefox`
- MCP Connector repository: `https://github.com/istefox/obsidian-mcp-connector`
- Obsidian CLI documentation: `https://obsidian.md/help/cli`
- Obsidian Bases documentation: `https://obsidian.md/help/bases`
- Obsidian 1.12 CLI changelog: `https://obsidian.md/changelog/2026-02-10-desktop-v1.12.0/`
