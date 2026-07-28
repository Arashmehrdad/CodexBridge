# BASIC-MEMORY-GUARD-1 — Minimal Soma Binding and Health Guard

**Date:** 2026-07-28
**Status:** provider compatibility and no-mutation confirmation remain closed; production controller acceptance is superseded and blocked by [`SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md`](SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md).
**Decision level:** C — foundational durability and continuity boundary.
**Evidence source:** [`PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md`](PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md)
**Live confirmation:** [`BASIC_MEMORY_GUARD_1_CONFIRMATION_2026-07-28.md`](BASIC_MEMORY_GUARD_1_CONFIRMATION_2026-07-28.md)
**Machine-readable controls:** [`basic-memory-minimal-guard-decision-2026-07-28.json`](basic-memory-minimal-guard-decision-2026-07-28.json)

## Decision

Adopt Basic Memory `0.22.1` as Soma's replaceable local semantic-memory provider, but only behind a minimal Soma-owned project-binding and health guard.

The provider passed complete rebuild from Markdown, interrupted-rebuild fail-closed behaviour, all four English/Persian retrieval directions, sibling isolation, filesystem freshness, restart stability and clean removal. It is not granted direct authority because omitted project identity routes to a configured project, unknown project identity attempts cloud routing, provider health commands do not prove project completeness, the default multilingual threshold is unsuitable, and first sync rewrites canonical Markdown.

No production integration, owner-memory import or client configuration is authorized by this decision alone.


## Post-confirmation architecture correction

The later repo-grounded shared-memory review found that this guard is not yet a sufficient production controller boundary. The current health path compares canonical-file count with provider entity count rather than exact path/hash membership; provider stdout may be parsed without a successful exit; runtime provider identity is not enforced; absent ProjectScope can be treated as active; the full ambient environment is inherited; and the canonical service still has crash-safety, hashing, vault-location and legacy-writer defects.

The live confirmation remains valid evidence for provider behaviour, no-mutation configuration, sibling isolation, bounded fallback and cleanup. Its `proven_complete` result must be understood as count reconciliation for that synthetic corpus, not exact manifest proof for production memory.

The accepted successor decision is `SOMA-SHARED-MEMORY-ARCH-1`. Controller connection is blocked until `MEMORY-INTEGRATION-FOUNDATION-1` repairs the documented defects and either proves exact provider path/hash reconciliation or leaves semantic mode disabled/non-authoritative.

## Authority and ownership

- Owner-readable Markdown remains canonical for durable owner-authored memory and lifecycle metadata.
- Obsidian remains the owner-facing workspace over the same files.
- Optional private Git may preserve owner-visible history and backup, but canonical correctness does not depend on every mutation being committed.
- Soma remains the sole authority for exact `project_id`, provider/project/root binding, routing, health acceptance, lifecycle, provenance and public controller access.
- Basic Memory owns only disposable local parsing, embeddings and semantic retrieval.
- Provider databases, indexes, caches and model state must remain reconstructable and removable without loss of canonical memory.
- ChatGPT, Claude Code and Hermes must reach the same memory through Soma's project-scoped contract rather than through separate client-specific provider configuration.

## Required guard outcomes

### Exact identity and local-only routing

Every provider call must begin with an exact active Soma `project_id` and resolve through one approved binding to the intended provider project, constrained process and canonical Markdown root.

Omitted, unknown, archived, suspended, mismatched or sibling identity must fail before provider invocation. Provider defaults, current working directory, active Obsidian vault and previously selected Basic Memory project must never infer identity.

Cloud routing, remote sync and hosted embeddings must be impossible in the accepted local profile, not merely unavailable because credentials happen to be absent.

### Honest completeness and recovery health

Soma must compare the canonical OS Markdown manifest with provider-visible project/entity/embedding coverage and publish healthy, rebuilding, degraded or unavailable state honestly.

Semantic retrieval is blocked whenever complete coverage cannot be proven. A previous healthy generation may remain available only when it is explicitly identified as stale and cannot be confused with the current canonical generation.

`bm doctor` is not a project-completeness oracle. `bm status --wait` is not an accepted synchronization or readiness mechanism because the tested release livelocked. Full synchronization and recovery use the working official `bm reindex` path or a later verified equivalent.

### Canonical Markdown integrity

The confirmed production profile must set both `ensure_frontmatter_on_sync = false` and `disable_permalinks = true`. The first setting alone did not prevent mutation; `disable_permalinks` is the measured control that stopped provider-authored `permalink:` insertion, while the first setting remains defence in depth.

The bounded live confirmation proved that project registration, initial indexing, three repeated synchronizations, complete index deletion and full rebuild leave canonical Markdown byte-identical. The tested release can therefore operate without rewriting canonical files under the confirmed profile.

Provider metadata may exist only where the owner has explicitly adopted it as part of the canonical Markdown contract.

### Retrieval configuration and fallback

The accepted evidence stack is:

- Basic Memory `0.22.1`;
- FastEmbed `0.8.0`;
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`;
- `litellm 1.91.4` on Windows;
- measured semantic threshold `0.30` for the frozen pilot corpus.

These values are evidence-bound starting points, not universal defaults. Any changed provider, model, dependency resolution or threshold requires a bounded compatibility check before its health disposition becomes accepted.

When semantic health is unavailable, Soma must retain bounded direct canonical Markdown read and literal-search access. This fallback may not become a custom embedding, ranking or semantic-retrieval engine.

### Tool and path boundary

Expose only the provider operations needed for approved project retrieval, status evidence and rebuild. Validate every returned or written path against the bound canonical root. Do not forward cloud, activation, open-world fetch, arbitrary command execution or destructive cross-project operations.

Long rebuild work may use Soma's existing task and run authority. The adapter must not create another task, lease, cancellation or recovery plane.

## Explicit non-goals

The guard may not implement:

- canonical memory storage;
- embeddings or model hosting;
- ranking or semantic search;
- graph traversal;
- provider repair or source patching;
- autonomous memory curation;
- personal-profile inference;
- conversation-history import;
- cross-project sharing;
- cloud synchronization;
- a second public memory authority.

MemAgent-style curation, Honcho-style relational inference and temporal graph projections remain separate future derived layers. They do not enter this integration lane.

## Implementation acceptance

A future implementation lane is accepted only when evidence proves:

- exact ProjectScope binding for at least two deliberately similar sibling projects;
- omission, unknown-project, inactive-project and wrong-project requests fail before provider invocation;
- no cloud-routing path is reachable from the production profile;
- the frozen local provider/model environment installs reproducibly on Windows without global changes;
- provider indexing and full rebuild leave canonical Markdown byte-identical;
- every eligible canonical file is accounted for after initial index, restart, full deletion/rebuild and one interrupted rebuild;
- partial or uncertain coverage blocks semantic retrieval and cannot report healthy success;
- English and Persian same-language and cross-language retrieval remain useful under a frozen benchmark;
- returned paths remain within the bound project root and no sibling result appears;
- bounded direct Markdown fallback remains usable while the semantic provider is unavailable;
- provider removal leaves canonical Markdown, Git history and Obsidian use intact;
- existing Soma task, ProjectScope, knowledge and controller compatibility remains intact;
- focused and proportional regression gates pass;
- nothing is pushed without explicit owner instruction.

## Replacement and stop triggers

Stop or reopen provider selection when:

- canonical files are still rewritten after the no-mutation profile is applied;
- project omission or wrong-project routing can reach the provider;
- any cloud fallback remains reachable;
- incomplete state can masquerade as healthy;
- a supported local multilingual model no longer passes the frozen bilingual gate;
- sibling-project leakage occurs;
- Windows reliability repeats a fatal failure;
- removal cannot restore a provider-free canonical workspace;
- the proposed patch expands into custom storage or retrieval behaviour.

## Next permitted lane

The next permitted memory lane is `MEMORY-INTEGRATION-FOUNDATION-1` under [`SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md`](SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md). Direct controller connection is not permitted before the documented guard, canonical-lifecycle, vault and legacy-authority defects are repaired. This does not authorize production owner-memory import, personal-memory activation, another provider comparison, MemAgent integration, code-intelligence activation, voice work or push.
