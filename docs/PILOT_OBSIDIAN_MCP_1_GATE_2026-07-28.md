# PILOT-OBSIDIAN-MCP-1 - Obsidian-Native Memory Compatibility Gate

**Date:** 2026-07-28
**Status:** gate prepared; execution has not started.
**Decision source:** [`OBSIDIAN_MCP_DECISION_2026-07-28.md`](OBSIDIAN_MCP_DECISION_2026-07-28.md)
**Candidate:** MCP Connector by istefox.
**Scope:** disposable compatibility trial of the official Obsidian application and community-store plugin only.

## Purpose

Determine whether Obsidian plus MCP Connector can serve as Soma's ready-made project-memory access layer while preserving:

- Markdown + Git as canonical content;
- Obsidian as the owner-facing and first runtime surface;
- local semantic, graph and structured access through official provider capabilities;
- Soma authority over exact project identity, vault binding, routing, provenance, continuity and acceptance;
- complete reversibility without losing canonical notes.

This is a product compatibility trial. It contains no model training, custom retrieval engine, provider source patch, agent swarm or production integration.

## Execution ownership

One controller executes the gate through Soma. No coding agent or subagent is required. No Basic Memory or Codebase Memory pilot may run in parallel.

The gate is documentation-complete. A subsequent owner instruction such as `continue` executes only this gate without another design ceremony.

## Fixed boundaries

- Inventory and record the installed stable Obsidian version before any change.
- Freeze the exact MCP Connector community-store release, manifest, source repository, license and available package/file hashes before enabling it.
- Prefer the official Obsidian community store. Do not use BRAT unless the community-store release is unavailable, and treat that as a stop for owner review.
- Use disposable vaults only under `runs/pilots/obsidian-mcp-1/`; do not open or index an owner production vault.
- Do not modify global MCP configuration, Claude/Codex settings, `AGENTS.md`, hooks, skills, shell profiles, browser policy or repository source files.
- Do not use auto-write client configuration, `.mcpb`, `mcp-remote`, or direct Claude/Codex configuration. Test the provider directly over loopback HTTP through Soma or the official MCP Inspector.
- Keep the server on hardcoded loopback with bearer authentication. Never bind to LAN interfaces or expose the token in committed evidence.
- Use the fixed **Core** tool profile. Adaptive and All profiles are forbidden in the first pilot.
- Disable command execution, web fetch, arbitrary command invocation and every unnecessary open-world capability.
- Phase A is read-only. Do not invoke a write or destructive tool until authentication and project isolation pass.
- Use native on-device embeddings only. Do not install Smart Connections, configure hosted APIs or use an external embedding service.
- For the bilingual check, use Multilingual-E5 or the provider's documented non-Latin recommendation and record the exact model/cache behavior.
- Keep plugin-generated state, model caches, indexes and logs disposable. Canonical notes must remain ordinary Markdown.
- Do not mutate live ProjectScope, Soma stores, production bindings, `.soma/wiki/`, Hermes memory or owner secrets.
- Do not push.

## Identity and vault-isolation setup

Use exactly two deliberately similar disposable vaults:

1. `soma-pilot-vault`, associated only in pilot evidence with Soma project ID `proj_a144f759-1619-4276-9292-28704b6611f4`;
2. `soma-lab-pilot-vault`, associated with synthetic Soma project ID `proj_0cf013d0-191b-57f4-a84b-7a43819a1578`.

Record for each project:

```text
Soma project_id
  -> disposable vault resource ID/root
  -> Obsidian vault identity
  -> fixed loopback port
  -> secret reference for the per-vault bearer token
  -> frozen plugin/model generation
```

Never store bearer tokens in tracked documentation. Use redacted secret references and hashes where useful.

Prefer unique fixed ports when both vaults are open. Sequential activation is acceptable only when the final architecture explicitly constrains one provider/vault process per project session. Default-port contention must be tested and recorded rather than silently avoided.

A project-less, unknown-project, wrong-project, archived or mismatched request must be rejected by the Soma-side pilot binding before any provider call. The provider's active vault or current window must never select project identity.

## Disposable note set

Create 16-24 ordinary Markdown notes across facts, decisions, lessons, procedures and daily notes. Include:

- deliberately conflicting sibling-project ports and concurrency limits;
- current and superseded facts with explicit source and status properties;
- ordinary `[[WikiLinks]]`, backlinks and properties;
- one small `.base` view over project notes;
- English and Persian notes plus paraphrased questions in both languages;
- one manually edited note, one renamed note and one deleted note;
- no private conversation history or production data.

Do not copy question wording into note titles. Record plain per-question observations; do not build a scoring framework or tune the note set after results.

## Required checks

### Installation and source integrity

- the plugin installs and enables only inside each disposable vault;
- version, manifest and relevant installed-file hashes match the frozen release evidence;
- no executable or configuration is written outside approved Obsidian/plugin/cache locations;
- disabling and uninstalling the plugin leaves the Markdown vault readable.

### Transport and authentication

- the MCP endpoint binds only to `127.0.0.1`;
- missing and incorrect bearer tokens are rejected;
- token rotation invalidates the previous token;
- `get_server_info` and `tools/list` work repeatedly through direct HTTP;
- the advertised Core surface is static and cannot self-activate additional tools;
- command execution and web fetch remain unavailable or rejected;
- tool annotations accurately identify read-only, destructive and open-world behavior.

### Windows reliability

- ten sequential read/search/property/graph calls complete without fatal shutdown or hanging;
- three full Obsidian/plugin restart cycles preserve notes and index consistency;
- closing Obsidian makes the endpoint fail clearly rather than returning stale success;
- reopening restores the correct project endpoint, token and index;
- simultaneous unique-port operation or the documented sequential constraint behaves predictably;
- cancellation or forced close never corrupts canonical Markdown.

### Obsidian-native structured access

- the official Obsidian CLI can identify the vault and perform bounded read/search operations;
- a `.base` view queries note properties and returns structured output;
- notes remain ordinary Markdown and YAML properties editable in Obsidian;
- link-aware rename preserves wikilinks and backlinks;
- external/manual edits are reflected by metadata, text search and semantic indexing;
- rename and deletion remove stale results after the documented provider update path.

### Retrieval and provenance

- `search_vault_simple` retrieves exact terms with path and line grounding;
- `search_vault_smart` handles the fixed English paraphrases without a custom retriever;
- the selected multilingual model handles the fixed Persian and cross-language questions;
- properties, tags, backlinks and outgoing links answer the fixed structured and relation questions;
- semantic results identify the source note and line position;
- no note from the sibling vault appears through the wrong project binding;
- every durable answer can be re-grounded to vault-relative path, file hash and Git/source generation.

### Write phase after isolation passes

Enable only the minimum note-write tools needed for the disposable trial. Verify:

- creating and patching a note produces clean Markdown diffs;
- properties round-trip without destroying unrelated frontmatter;
- rename uses Obsidian link-aware behavior;
- delete behavior is explicit and recoverable from Git/evidence;
- a wrong-project or unbound write is rejected before the provider call.

Command execution remains disabled throughout.

### Rebuild and removal

- preserve Markdown and Git, then remove only provider/plugin index state through the documented reset, disable or reinstall path;
- rebuild the semantic index from the unchanged vault;
- repeat representative literal, semantic, Persian and graph queries;
- disable and uninstall MCP Connector from both disposable vaults;
- verify Markdown, properties, links and Bases remain intact;
- remove disposable vaults only after evidence hashes are recorded;
- prove no provider process, token, plugin state, model cache or client configuration remains outside approved removable locations.

## Exact outcomes

The pilot returns one of four results:

### `accept_obsidian_native_stack`

Use when the provider is reliable, semantic and structured retrieval are useful, canonical Markdown survives rebuild/removal, and exact per-project vault isolation is enforceable without additional code beyond existing Soma routing.

### `accept_with_minimal_soma_binding_guard`

Use when the provider otherwise passes but requires a narrow Soma guard for exact project-to-vault/endpoint binding, omission rejection, tool-class gating, path validation or provenance re-grounding. The guard may not implement retrieval or provider behavior.

### `reject_mcp_connector_activate_basic_memory_comparison`

Use when Obsidian uptime, Windows reliability, authentication, project isolation, multilingual retrieval, rebuild or clean removal fails a named requirement after one clean rerun. Preserve the failure and reactivate the existing Basic Memory gate only for that named gap.

### `inconclusive`

Use only when one reproducible environment or test-harness defect prevents judging provider behavior. Permit one bounded correction and do not broaden the lane.

## Stop conditions

Stop immediately and preserve evidence when:

- the endpoint binds beyond loopback;
- missing or wrong authentication is accepted;
- any sibling-vault content appears through a scoped project binding;
- the plugin or installer modifies global/client/repository configuration;
- Adaptive or All tool loading, command execution, web fetch or uncontrolled tool activation is required;
- provider state becomes the only copy of canonical information;
- a production vault, private memory or owner secret is needed;
- plugin source or Obsidian source must be patched;
- a custom embedding, retrieval, ranking, graph or benchmark implementation is proposed;
- Windows hangs, stale-success behavior or Markdown corruption repeats after one clean rerun;
- the index cannot be rebuilt from the vault or removed safely;
- unrelated repository changes appear;
- the pilot exceeds one focused controller session without a single bounded blocker.

A stop is a valid result and activates no alternative automatically except the explicitly documented Basic Memory comparison after owner-visible closure.

## Required evidence

The final record must include:

- frozen Obsidian, plugin, manifest, source, license and hash information;
- both Soma IDs, vault roots/identities, fixed ports, redacted token references and plugin/model generations;
- initial and final `tools/list` plus provider settings proving the fixed restricted surface;
- missing-token, wrong-token and token-rotation observations;
- exact official CLI/MCP operations and output hashes;
- per-check observations for literal, semantic, Persian, structured and graph retrieval;
- project omission, wrong-project and sibling-isolation results;
- external edit, rename, deletion and link-integrity evidence;
- restart, endpoint-down and index-rebuild evidence;
- plugin disable/uninstall and cleanup proof;
- repository preflight showing clean worktree, no running work, no locks and no push;
- one exact outcome above.

## After this gate

- Basic Memory remains a preserved inactive fallback unless this gate returns `reject_mcp_connector_activate_basic_memory_comparison`.
- `PILOT-CODE-INTELLIGENCE-1` remains planned but inactive until the memory result is documentation-closed.
- No production memory integration begins without a separate acceptance decision.
