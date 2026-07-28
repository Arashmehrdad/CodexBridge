# Soma Pre-Roadmap V3 Engineering Plan

## Status

Roadmap V2 is complete and preserved under [`docs/legacy/`](docs/legacy/). This file is now the only active engineering plan.

The purpose of this bridge phase is narrow: repair the live kernel issues discovered by the architecture re-evaluation, run the bounded adoption pilots that answer the remaining implementation questions, and then write Roadmap V3 from evidence rather than assumption.

The accepted decision record is [`docs/Soma_Architecture_Reevaluation_Findings_2026-07-26.md`](docs/Soma_Architecture_Reevaluation_Findings_2026-07-26.md).

Historical records:

- [`docs/legacy/Soma_Roadmap_V2_Final_Active_Plan_2026-07-26.md`](docs/legacy/Soma_Roadmap_V2_Final_Active_Plan_2026-07-26.md)
- [`docs/legacy/Soma_Roadmap_V2_Achievement_Record_2026-07-18.md`](docs/legacy/Soma_Roadmap_V2_Achievement_Record_2026-07-18.md)
- [`docs/legacy/Soma_Roadmap_V2_Strategic_Architecture_2026-07-26.md`](docs/legacy/Soma_Roadmap_V2_Strategic_Architecture_2026-07-26.md)

## Planning Style: Goals, Not Recipes

Coding agents must receive room to solve engineering problems.

This plan defines:

- the outcome to achieve;
- the reason it matters;
- non-negotiable invariants;
- evidence required for acceptance;
- boundaries that prevent collateral damage.

It deliberately does not prescribe exact files, classes, functions, schemas, algorithms, or step-by-step edits. An assigned agent should inspect the live implementation, choose the smallest coherent design, and explain important trade-offs through evidence. Existing mechanisms should be reused when they are sound, but the agent may choose a better implementation when the accepted outcome is met more cleanly.

Task prompts derived from this plan should contain the problem, known evidence, required outcomes, constraints, and acceptance gate. They should not pre-solve the coding task for the agent.

Agents may challenge an assumption, propose a simpler route, or adjust their internal decomposition. They may not silently change the accepted goal, create a second authority, weaken durability, discard evidence, or broaden the batch into unrelated architecture.

## Governing Boundaries

- Soma remains the independent durable, project-aware control plane.
- One authority owns each concern; integrations keep exact Soma identifiers and projections rather than competing truth.
- Supported controllers reach Soma directly through its vendor-neutral MCP endpoint; an owner-facing companion or shell does not proxy ordinary capability calls.
- Hermes remains Soma's accepted and integrated companion and capability foundation. Future companion, voice, or channel work begins from measured Hermes-specific gaps rather than a new parallel shell.
- OpenClaw is rejected from the target architecture. Its pilot is closed, and no further OpenClaw version, Claude-backend, ACPX, voice, or channel testing is planned.
- Historical evidence, opaque identifiers, compatibility, and recovery remain intact.
- Failures and uncertainty must be published honestly rather than converted into apparent success.
- Existing production paths remain available until a replacement is proven and accepted.
- Preserve unrelated work. Do not reset, clean, stash, rewrite history, or push unless the owner explicitly requests it.
- Validation should be proportional to risk: focused evidence first, adjacent regression coverage next, and broader gates when the change can affect the whole runtime.
- Roadmap V3 feature construction is out of scope during this bridge phase.

## Completed Lane: STABILIZE-1

**Status:** accepted and closed.

**Goal:** make the current Soma kernel safe and economical to keep modifying before any new architecture is promoted.

### Required outcomes

1. **Stop active evidence amplification.** Managed repository changes and comparable operations must stop copying repository-scale manifests, status output, and repeated inventories into ordinary run-result records. Result growth should reflect the operation, not the size of the repository.

2. **Keep complete evidence without duplicating it.** Large authoritative bodies remain immutable and retrievable through exact references and hashes, while the queryable run record remains compact and useful.

3. **Repair existing amplified history safely.** Existing large records receive a resumable, hash-verified migration path. Old and migrated records remain readable until reconstructability has been proven; opaque identities and protected evidence are never rewritten or discarded merely to reduce storage.

4. **Make reconciliation failure visible.** Failures in every existing startup reconciliation path must become durable, observable, and retrievable through the appropriate status, health, event, or evidence surface. Soma must never continue silently after losing recovery information.

5. **Restore repository-wiki hygiene.** Confirmed tool-owned and generated paths must not pollute repository knowledge. Managed repository changes should lead to a fresh wiki generation or an explicit, durable freshness failure rather than an unnoticed stale state.

6. **Map lifecycle ownership before consolidation.** Produce an evidence-grounded inventory of the current run, task, workflow, supervisor, long-run, Hermes, SSH, and related lifecycle authorities, including where ownership overlaps and what must remain compatible. This is an inventory and recommendation, not permission for a broad consolidation refactor inside STABILIZE-1.

### Acceptance gate

STABILIZE-1 is accepted only when evidence demonstrates that:

- representative managed repository operations no longer store repository-scale result bodies;
- exact authoritative evidence remains retrievable and hash-verifiable;
- migration can resume after interruption and old-versus-new reads remain compatible;
- reconciliation failures are observable across all identified startup paths;
- tool-owned paths are excluded from repository knowledge and freshness failure cannot disappear;
- the lifecycle-authority inventory is complete enough to guide, but not predetermine, Roadmap V3;
- focused and proportional regression gates pass;
- no unrelated owner work is changed and nothing is pushed.

The agent implementing STABILIZE-1 owns its technical design and decomposition. The measured findings and invariants above are binding; the implementation route is not.

## Pre-Roadmap V3 Gates After STABILIZE-1

These gates are ordered but not automatically active. Each begins only after the prior result is reviewed and the owner selects it.

### PILOT-ACP-1 - Worker Session Boundary

**Status:** evaluated and declined.

**Purpose:** determine whether ACP can serve as Soma's standard coding-agent session boundary for Claude Code and Codex while Soma retains task, project, workspace, cancellation, evidence, and acceptance authority.

The pilot should prove useful streaming, steering, cancellation, concurrency, restart recovery, and honest fallback behaviour. Its main decision is whether ACP session recovery is sufficient, whether provider CLI resume is also required, or whether a small custom component remains justified.

This is a bounded pilot, not permission to build the full worker plane.

### PILOT-OPENCLAW-1 - External Shell Boundary

**Status:** evaluated and rejected.

The incumbent and incremental-value gates are decisive. Hermes is already the accepted and integrated companion and capability layer wired to Soma, while Claude and Codex both reach Soma directly through vendor-neutral MCP. OpenClaw satisfies no unmet requirement and would duplicate the established architecture.

The account-coupled Codex Apps route worked but was rejected as the canonical path. OpenClaw's local Codex MCP projection failed, profile isolation was partial, a pinned build installed an unpinned Codex dependency, and the bundled ClawHub installer appeared by default. Shutdown, port cleanup, and repository isolation succeeded.

Retain direct controller-to-Soma MCP and Hermes as the companion foundation. OpenClaw is not part of the target architecture, and no unresolved OpenClaw voice or channel role remains. The closure evidence and completed post-review cleanup are recorded in [`docs/pilot-openclaw-1-evidence-2026-07-27.md`](docs/pilot-openclaw-1-evidence-2026-07-27.md).

### PILOT-SCOPE-1 - Project Isolation Seam

**Status:** evaluated, owner-reviewed, and accepted with outcome **proceed**. The pilot is closed; no production implementation or historical assignment is authorized by this decision.

**Purpose:** prove that immutable project identity and external-session bindings can be introduced through the current canonical stores and projections without breaking existing clients.

The decisive test is confusion resistance: two deliberately similar projects must remain separated across tasks, runs, repositories, worktrees, evidence, retrieval, processes, credentials, and external bindings. Unscoped project work must fail closed.

The completed evidence is recorded in [`docs/pilot-scope-1-evidence-2026-07-27.md`](docs/pilot-scope-1-evidence-2026-07-27.md). The additive sidecar passed focused isolation tests across the incumbent task, run, repository, worktree, memory, artifact, credential-reference, process, cancellation, restart, lock, projection, and Hermes boundaries. Transactional migration and rollback passed on disposable copies of both live stores, whose source hashes remained unchanged. Strict additive task/run MCP schemas preserve incumbent payloads. The owner reviewed and accepted the deterministic [`backfill/quarantine manifest`](docs/pilot-scope-1-backfill-quarantine-manifest-2026-07-27.json): 2,083 mappings remain candidate-only, 2,589 runs default to quarantine, and no inferred assignment is authorized. The final pilot outcome is **proceed**. Production implementation and live historical disposition require separate lanes and approval.

### SCOPE-FOUNDATION-1 - Additive Project Identity Foundation

**Status:** **SCOPE-FOUNDATION-1 is live and recovery-closed.** Gate A and Gate B are accepted; `GATE-C-PREREQ-1` and ProjectScope schema v2 are accepted and live; Gate C is executed with ProjectScope `2 / 2`, scoped writes enabled, enforcement `enforced`, `ever_activated = 1`, one exact Soma project/repository binding, and complete controller proof across Claude, ChatGPT, and the attached CodexBridge Soma plugin. The malformed first proof task has been terminally resolved through the public atomic recovery surface as failed, quarantined, and superseded by the successful proof task—no backend run, result, or evidence was fabricated. Live durable state has three task reservations and three run attempts, of which two are attached and one is quarantined; quarantine and adjudication each contain exactly one resolved record. Integrity is `ok`, foreign-key violations are zero, the worktree is clean, and nothing is pushed. The schema-v2 preparation/activation records remain in [`docs/SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_PREPARATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_PREPARATION_2026-07-27.md) and [`docs/SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_2026-07-27.md). Gate C and its recovery closure are authoritative in [`docs/SCOPE_FOUNDATION_1_GATE_C_ACTIVATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_GATE_C_ACTIVATION_2026-07-27.md) and [`docs/scope-foundation-1-gate-c-activation-2026-07-27.json`](docs/scope-foundation-1-gate-c-activation-2026-07-27.json). The pre-cutover backup remains a comparison reference, not a restore target. Historical backfill/disposition, memory activation, Hermes migration, unrelated cleanup, and push remain outside this lane.

Gate B preparation is recorded in [`docs/SCOPE_FOUNDATION_1_GATE_B_PREPARATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_GATE_B_PREPARATION_2026-07-27.md), with a machine-readable rehearsal manifest in [`docs/scope-foundation-1-gate-b-preparation-2026-07-27.json`](docs/scope-foundation-1-gate-b-preparation-2026-07-27.json). The activation itself is recorded in [`docs/scope-foundation-1-gate-b-activation-2026-07-27.md`](docs/scope-foundation-1-gate-b-activation-2026-07-27.md), with machine-readable evidence in [`docs/scope-foundation-1-gate-b-activation-2026-07-27.json`](docs/scope-foundation-1-gate-b-activation-2026-07-27.json). All 32 verification gates passed: the migration applied once, run/task counts and stable ID hashes were unchanged, the incumbent schema hash was unchanged, integrity and foreign-key checks passed, and every identity, binding, reservation, bootstrap-event, and quarantine table is empty with `scoped_writes_enabled = 0` and enforcement `inactive`. The rollback backup is `runs/soma.sqlite3.backup-gate-b-20260727T131451Z` (sha256 `f47cc830c0ecc5f7cd13a1103a230adff0b645417dc4368dbdaa8b98e9af1296`).

Gate C preparation is recorded in [`docs/SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md), with a machine-readable manifest in [`docs/scope-foundation-1-gate-c-preparation-2026-07-27.json`](docs/scope-foundation-1-gate-c-preparation-2026-07-27.json). The proposed exact identities are `proj_a144f759-1619-4276-9292-28704b6611f4` and `res_5b67936d-9599-4f08-b817-b3c30564400f`, bound exclusively to canonical repository root `d:/github/soma` with identity hash `1f7c8e8726a452826177d0fb06d08b0e73df3695cd9e52f3a37d9b53cd451441`. Live preview was conflict-free and made zero writes; an exact-ID disposable cutover rehearsal passed bootstrap, idempotency, enforcement, pause rollback, integrity, and foreign-key checks. The quarantine-remedy prerequisite is now accepted, and the schema-v2 activation it depended on is executed and verified. **Gate C was owner-approved, executed, and verified on 2026-07-27**: the exact reviewed identity is bootstrapped and scoped writes are live with enforcement `enforced` and `ever_activated = 1`. The activation is recorded in [`docs/SCOPE_FOUNDATION_1_GATE_C_ACTIVATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_GATE_C_ACTIVATION_2026-07-27.md), with machine-readable evidence in [`docs/scope-foundation-1-gate-c-activation-2026-07-27.json`](docs/scope-foundation-1-gate-c-activation-2026-07-27.json). No documented stop condition fired. The reviewed input, outcome, and evidence-event hashes reproduced exactly, bootstrap was idempotent, and the restarted runtime converged with `mismatches: []` and clean startup reconciliation. The pre-cutover backup is `runs/gate-c-20260727T195813Z/soma-pre-gate-c-backup.sqlite3` (sha256 `ad6661de99c6ad7decf2df4e8ac797224ecad24d1d15f3f88fbc0da7b949b900`); because a scoped task now exists it is a comparison reference, **not** a restore target.

Gate C controller proof is complete across Claude, ChatGPT, and Codex. Codex used the attached CodexBridge Soma plugin for an exact scoped replay and status read with no shell, CLI, subprocess, new reservation, run attempt, or backend execution. This proves that attached plugin route; it does not independently prove the separately installed global `soma` namespace. The malformed first proof task (`task_20260727T200608Z_8719fe3d9754`) is no longer unresolved: the tested public `resolve_recovery` operation atomically moved it to terminal `failed / resolved`, quarantined its reservation and attempt, preserved the missing backend and empty result/evidence references, recorded one immutable `superseded` adjudication and one supersedes link to `task_20260727T200740Z_8f8995778083`, and replayed idempotently. The recovery incident is closed.

Gate A passed the full implementation and disposable-store gates. The owner ratified project-less access as an owner-controller compatibility path only, terminal evidence-preserving quarantine with an explicit adjudication/supersession prerequisite before Gate C, and the v1 one-task/one-run-attempt invariant. No additional Claude CLI retry is required. Successful live scoped controller calls are deferred until Gate C because Gate B creates schema only.

The smallest coherent production lane is a main-store ProjectScope v1 sidecar for **new canonical task/run work only**. It establishes immutable projects, repository-resource bindings, task scope reservations, run-attempt reservations, deterministic recovery/quarantine evidence, and optional strict MCP project assertions while preserving the incumbent task, run, process, result, evidence, and operation-lock authorities.

Memory, Hermes and other external sessions, worktrees, credentials, other legacy run producers, and historical assignment are explicit exclusions. Live schema activation and project/repository bootstrap are separate post-implementation owner gates. The full outcome-led proposal, invariants, migration boundaries, compatibility contract, acceptance evidence, retry limits, and stop conditions are in [`docs/SCOPE_FOUNDATION_1_PRODUCTION_LANE_PROPOSAL_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_PRODUCTION_LANE_PROPOSAL_2026-07-27.md).

### PILOT-MEMORY-1 - Smallest Durable Memory Baseline

**Status:** the original ten-note shadow benchmark is closed as valid **limitation evidence**, not baseline acceptance. It passed 7/7 clean substring-oriented classes but did not discriminate on supersession depth, semantic retrieval, metadata drift, or scale. Its evidence remains in [`docs/pilot-memory-1-shadow-baseline-2026-07-27.md`](docs/pilot-memory-1-shadow-baseline-2026-07-27.md) and [`docs/pilot-memory-1-shadow-benchmark-2026-07-27.json`](docs/pilot-memory-1-shadow-benchmark-2026-07-27.json).

### PILOT-MEMORY-1B - Hardened Shadow Benchmark

**Status:** closed on 2026-07-28 as an overbuilt experiment. Its committed evidence is retained, but no Agent 2 review, score expansion, observation period, custom retrieval development, or production use is authorized. The package under `soma/pilot_memory_1b/` is historical evidence only.

### MEMORY-DECISION-1 - Ready-Made Memory Provider Selection

**Status:** superseded before provider-pilot execution. The historical Basic Memory-first decision remains in [`docs/MEMORY_PROVIDER_DECISION_2026-07-28.md`](docs/MEMORY_PROVIDER_DECISION_2026-07-28.md) and [`docs/memory-provider-decision-2026-07-28.json`](docs/memory-provider-decision-2026-07-28.json). No Basic Memory installation or pilot execution occurred under it.

### MEMORY-PROVIDER-SOLUTION-DISCOVERY-2 - Trustworthy Local Project Memory

**Status:** **accepted and documentation-closed; implementation has not started.** The authoritative decision is [`docs/MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md`](docs/MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md), with machine-readable controls in [`docs/memory-provider-solution-discovery-2026-07-28.json`](docs/memory-provider-solution-discovery-2026-07-28.json).

The decision preserves Markdown + Git as canonical, Obsidian as owner workspace and Soma as authority. It selects Basic Memory Local for one bounded compatibility pilot, preserves a materially changed MCP Connector release for later re-test, rejects parallel provider trials and custom retrieval, and treats provider state as disposable.

The hardest requirement is tested first: delete all derived state, rebuild from unchanged Markdown, account for every eligible synthetic file, survive restart/interruption, and prove incomplete state cannot masquerade as healthy. The provider-independent black-box contract uses per-file lexical and semantic canaries, explicit OS-manifest versus provider accounting, a four-direction English/Persian matrix, filesystem create/edit/rename/delete freshness, and safe abstention. A single sentinel is not accepted as completeness proof, and an empty nonsense-query result is not treated as a dead index.

### KNOWLEDGE-LAYER-1 - Soma External Research Knowledge Platform

**Status:** architecture corrected after the initial `df83a6a` Markdown foundation. The owner explicitly selected the SeedMind-style external research platform for Soma. The full ownership and public contract are in [`docs/SOMA_KNOWLEDGE_LAYER.md`](docs/SOMA_KNOWLEDGE_LAYER.md). This lane does not reactivate H2, TL5, SSH expansion, autonomous crawling, or other paused roadmap work.

**Goal:** preserve completed, explicitly owner-requested research so ChatGPT, Claude Code, and Hermes recover the same original sources, provenance, reviewed claims, contradictory evidence, research questions, candidates, decisions, and historical context through Soma.

**Corrected production boundary:** a project-isolated content-addressed raw archive is canonical for original artifacts. A structured SQLite research overlay is canonical for source versions, ingestion lifecycle, reviewed research state, relationships, audit records, and supersession. RAGFlow is a disposable parsing/OCR/chunk/embedding/retrieval layer. Markdown and Obsidian are optional owner-readable projections. Soma owns exact ProjectScope identity, routing, health, continuity, and the two existing public knowledge gateways.

**Initial foundation disposition:** `soma.knowledge` and its Markdown catalog remain supported for generic notes and legacy public operations, but Markdown is no longer described as the authoritative research system. Generic records are not silently promoted into reviewed claims or evidence.

**Implemented corrective scope:** digest-only immutable archive objects outside SQLite and Git; manual URL-capture/local-file/captured-artifact imports; immutable traceable source versions; packet-level idempotent SQLite transactions; claims and exact evidence roles including support, contradiction, qualification, replication, and failed replication; questions, candidates, decisions, generated summaries, relationships, analysis/audit state; reproducible context packets; layered archive/overlay/index/projection health; checksummed overlay export/restore; and a replaceable RAGFlow gateway/rebuild boundary.

**Non-goals:** no crawler, scheduler, autonomous discovery, mass ingestion, custom OCR/parser/vector engine, automatic truth adjudication, generated-to-reviewed promotion, source blobs in SQLite/Git, or second task/run lifecycle.

**Acceptance:** prove idempotent import, changed-byte version lineage, raw-object immutability and SHA-256 verification, no SQLite source blobs, coexisting supporting and contradictory evidence, restart-safe decisions and supersession, sibling isolation, one explicit ChatGPT preservation flow, one reproducible later context packet, RAGFlow deletion/rebuild without canonical overlay loss, overlay export/restore, connector-safe public contracts, legacy compatibility, and full validation.

**Next batch after acceptance:** configure and validate a real project-bound RAGFlow deployment through the existing durable task/run authority, then run one bounded owner research preservation and later retrieval trial. Do not enable autonomous source collection.

### OBSIDIAN-MCP-DECISION-1 - Obsidian-Native Memory Access

**Status:** architecture accepted and documentation-closed; frozen MCP Connector release `0.28.1` was tested and rejected for the current provider lane. The reconciled decision is [`docs/OBSIDIAN_MCP_DECISION_2026-07-28.md`](docs/OBSIDIAN_MCP_DECISION_2026-07-28.md), with machine-readable disposition in [`docs/obsidian-mcp-decision-2026-07-28.json`](docs/obsidian-mcp-decision-2026-07-28.json).

The decisive blockers are incomplete index rebuild, stale healthy success from the incomplete index and silent multilingual-model failure. The rename path remains unsafe as observed, but its root cause is not proven because the Obsidian automatic-link-update setting was not recorded. Core tool expansion is downgraded to a manageable integration weakness for the owner's single-user, loopback-only laptop and requires a future Soma allowlist rather than provider rejection by itself.

The only permitted custom component after provider acceptance is a thin Soma project-binding, health, tool-allowlist, path-validation and provenance guard with literal Markdown fallback. It may not implement storage, embeddings, ranking, semantic search, graph traversal or provider repair.

### PILOT-BASIC-MEMORY-1 - Historical First-Draft Gate

**Status:** superseded before execution and permanently inactive. The preserved historical gate remains in [`docs/PILOT_BASIC_MEMORY_1_GATE_2026-07-28.md`](docs/PILOT_BASIC_MEMORY_1_GATE_2026-07-28.md) and [`docs/pilot-basic-memory-1-gate-2026-07-28.json`](docs/pilot-basic-memory-1-gate-2026-07-28.json). It cannot be reactivated.

### PILOT-BASIC-MEMORY-2 - Provider Health and Bilingual Compatibility Gate

**Status:** **gate prepared; execution has not started.** The authoritative gate is [`docs/PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md`](docs/PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md), with machine-readable boundaries in [`docs/pilot-basic-memory-2-gate-2026-07-28.json`](docs/pilot-basic-memory-2-gate-2026-07-28.json).

The gate uses one controller, no coding agents or subagents, two project-constrained Basic Memory processes, two disposable seven-note projects, per-file lexical and semantic canaries, one frozen local multilingual model, official full rebuild/reset commands, an interrupted-rebuild stale-success test, all four English/Persian query directions, OS create/edit/rename/delete freshness, minimum provider-specific omission/isolation/Markdown checks, three restart cycles and complete removal. It installs only inside `runs/pilots/basic-memory-2/`, touches no production memory or client configuration, performs no source patch or custom retrieval, and does not push.

A subsequent owner instruction such as `continue` executes only this gate. Gate preparation itself authorizes no provider installation or production integration.

### PILOT-OBSIDIAN-MCP-1 - Obsidian-Native Compatibility Gate

**Status:** **executed and documentation-closed** with outcome `reject_mcp_connector_activate_basic_memory_comparison`. The gate remains in [`docs/PILOT_OBSIDIAN_MCP_1_GATE_2026-07-28.md`](docs/PILOT_OBSIDIAN_MCP_1_GATE_2026-07-28.md); the authoritative result is [`docs/PILOT_OBSIDIAN_MCP_1_RESULT_2026-07-28.md`](docs/PILOT_OBSIDIAN_MCP_1_RESULT_2026-07-28.md) with machine-readable evidence in [`docs/pilot-obsidian-mcp-1-results-2026-07-28.json`](docs/pilot-obsidian-mcp-1-results-2026-07-28.json).

The executed gate used one controller, two disposable project vaults, the community-store MCP Connector release, fixed Core tool loading, direct loopback HTTP with per-vault bearer authentication, command execution and web fetch disabled, native multilingual embeddings, Obsidian CLI and Bases checks, strict Soma-to-vault binding, external-edit and link-integrity checks, Windows restart checks, full semantic-index rebuild and clean uninstall. It includes no coding agents, subagents, custom retrieval, production memory, client auto-configuration or push.

The provider passed loopback authentication, strict sibling isolation, English and Persian same-language paraphrase retrieval, structured access and Markdown survival. It was rejected because incomplete-index rebuild and stale healthy success reproduced, while the required multilingual path silently failed. Post-pilot review records the rename root cause as unproven and the Core expansion issue as manageable through a future Soma allowlist under the owner's actual threat model. Cleanup completed without loss of canonical Markdown.

### FUTURE-CORTANA-PRESENCE-AGENT-RESEARCH - Parked Two-Speed Conversation

**Status:** parked future research; no active lane, provider choice, API spend, browser automation, voice integration or telephony work. The preserved concept is [`docs/FUTURE_CONVERSATIONAL_PRESENCE_AGENT_RESEARCH.md`](docs/FUTURE_CONVERSATIONAL_PRESENCE_AGENT_RESEARCH.md).

The future architecture separates a fast presence agent for immediate acknowledgement, bounded clarification, interruption and truthful progress narration from a heavy reasoning backend that performs research, judgment and tools through Soma. The same packet-bound pattern may later support prepared phone calls with owner-approved facts, answers, limits, escalation and human takeover. Nemotron-family models, ElevenLabs-style speech infrastructure, browser/API backends and telephony providers remain candidates to re-research later, not current selections.

This research remains behind durable memory continuity and derived code intelligence unless the owner explicitly reprioritizes it.

### CODE-INTELLIGENCE-DECISION-1 - Codebase Memory MCP

**Status:** **accepted as planned but inactive.** The authoritative boundary is [`docs/CODEBASE_MEMORY_MCP_DECISION_2026-07-28.md`](docs/CODEBASE_MEMORY_MCP_DECISION_2026-07-28.md), with machine-readable controls in [`docs/codebase-memory-mcp-decision-2026-07-28.json`](docs/codebase-memory-mcp-decision-2026-07-28.json).

`DeusData/codebase-memory-mcp` is the preferred ready-made candidate for derived repository structure: symbols, calls, routes, architecture, source snippets, and change impact. It does not overlap with the owner-authored project-memory lane. Basic Memory is the active prepared provider gate, not code intelligence, and neither provider replaces the repository, Git, `RepoWikiService`, canonical Markdown or Soma authority.

A future `PILOT-CODE-INTELLIGENCE-1` may test a pinned, checksum-verified binary through an explicit Soma project/repository binding, with cache outside the repository, `CBM_ALLOWED_ROOT` enforced, auto-index and auto-watch disabled, no installer edits, no `manage_adr`, no committed graph artifact, no subagents, and no push. The pilot is not active.

## Prerequisites Before Autonomous Scheduled Agent Work

These requirements do not block STABILIZE-1 or the early pilots, but autonomous scheduled agent work may not be enabled without both:

- project-scoped provider, model, token, usage, and cost accounting with ceilings that pause scheduled work;
- a fixed golden-task evaluation set that tests repository outcome, correctness, scope, evidence, and cleanliness before agent output is accepted.

## Roadmap V3 Trigger

Roadmap V3 is written only after the bridge evidence is reviewed. It should convert accepted findings into a smaller implementation sequence for an independent durable project-aware control plane, using proven external components through narrow replaceable boundaries.

Roadmap V3 should remain an outcome-led engineering roadmap. It may define exact public contracts and invariants where compatibility requires precision, but it should not become a giant collection of pre-written coding instructions for agents.

`PILOT-OBSIDIAN-MCP-1` is closed. `PILOT-BASIC-MEMORY-1` is historical and permanently inactive. `PILOT-BASIC-MEMORY-2` is the only prepared executable memory gate and is not yet running; a generic `continue` executes that gate only. `PILOT-CODE-INTELLIGENCE-1` remains planned and inactive until the Basic Memory result is documentation-closed. `FUTURE-CORTANA-PRESENCE-AGENT-RESEARCH` is parked and creates no implementation authority. No provider alternatives, code-intelligence pilot or voice work may overlap. A generic `continue` does not authorize production integration, Roadmap V3 feature work or push.
