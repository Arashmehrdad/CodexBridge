# Soma Roadmap V3 Engineering Plan

## Status

Roadmap V2 is complete and preserved under [`docs/legacy/`](docs/legacy/). The Pre-Roadmap V3 bridge is also complete. This file remains the only concise active engineering plan.

The V3 autonomous-company architecture is owner-accepted after the 2026-07-31 hierarchical-intelligence organisational research closure. `RELIABILITY-1 — EXISTING-RUNTIME-HARDENING` is closed. `V3-1A — INTERACTIVE WORKER SUBSTRATE` is accepted and closed. The corrected `V3-1B — KERNEL OF ONE ARCHITECTURE GATE` and `V3-1B-SCHEMA-MODELS-1` are accepted. The later Agent/Worker program then added and accepted the bounded immutable PlanRevision DAG, dependency-proof admission, provider-neutral reasoning Task backend, evidence/FanIn boundary, protected mutation broker, and deterministic bounded coordinator without activating a live reasoning provider. That work is preserved in [`docs/agent-worker-research/AGENT_WORKER_CORE_ACCEPTANCE_2026-08-14.md`](docs/agent-worker-research/AGENT_WORKER_CORE_ACCEPTANCE_2026-08-14.md). It advanced V3-1B mechanics but did not by itself close the Kernel-of-One product lane. `V3-1B-BOOTSTRAP-PLAN-AUTHORITY-1` is now accepted: the trusted configuration-anchored Company/Mission root and bootstrapped PlanRevision authority are implemented and proven in source. Exact OutcomeAcceptance, projections/reconcile-one, strict company gateways, and live kernel activation are still absent. The active package is now [`V3-1B-OUTCOME-ACCEPTANCE-1`](docs/V3_1B_OUTCOME_ACCEPTANCE_1_GATE_2026-08-14.md). Real provider execution remains owner-disabled; public company operations, scheduled autonomy, worker-facing Soma MCP, V3-2 capability delegation, and later V3 outcomes remain inactive.

The architecture is [`docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md`](docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md), the reconciliation is [`docs/SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md`](docs/SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md), and the owner-accepted organisational contract is [`docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`](docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md). The completed V3-1A lane contract remains [`docs/V3_1A_INTERACTIVE_WORKER_SUBSTRATE_PLAN_2026-07-30.md`](docs/V3_1A_INTERACTIVE_WORKER_SUBSTRATE_PLAN_2026-07-30.md); the completed V3-1B architecture gate is [`docs/V3_1B_KERNEL_OF_ONE_ARCHITECTURE_GATE_2026-08-02.md`](docs/V3_1B_KERNEL_OF_ONE_ARCHITECTURE_GATE_2026-08-02.md), and the completed schema/models gate is [`docs/V3_1B_SCHEMA_MODELS_1_GATE_2026-08-02.md`](docs/V3_1B_SCHEMA_MODELS_1_GATE_2026-08-02.md).

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

## Engineering Progression Procedure

The active development agent owns routine engineering acceptance. At every package or lane boundary it must audit the objective acceptance gate against durable evidence. When the gate passes, it records the audit, closes the completed work, and proceeds to the next already-defined roadmap package without asking the owner for ceremonial approval.

Owner instruction is required only for a genuine product-direction choice, an unresolved risk or failed acceptance gate, an irreversible external action, production activation, deployment, purchase, credential/account action, push, or a scope change not already authorised by this roadmap. Silence or missing ceremony is never a reason to leave accepted engineering work parked.

After every accepted slice, material incident, acceptance decision, or roadmap transition, the development agent must update the authoritative result/gate documents and this plan, commit those records locally, and refresh canonical repository knowledge before beginning the next implementation package. Chat history alone is not accepted as project memory.

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
- Only the explicitly active V3 lane may change product behavior. Later V3 outcomes remain out of scope until separately activated.
- V3 uses progressive lifecycle convergence: generic execution responsibilities converge into canonical Task → Run as each lane touches them; irreducible domain facts remain with their domains.
- V3 uses hierarchical intelligence with delegated judgment: parents define purpose, authority, constraints, success, escalation, and reporting boundaries; capable children choose methods and escalate exceptions.
- Role, Agent identity, Assignment, Session, and Execution are distinct identities. Providers, models, accounts, conversations, and processes remain replaceable.
- Authority, collaboration, execution ownership, and resource capability are four linked but non-interchangeable graphs.
- Every active work item has exactly one accountable owner, and ownership transfer is atomic.
- Mandates are immutable, content-addressed, versioned, lineage-bound, and cannot grant authority or concrete capability the issuer does not possess.
- Revocation and cancellation deny new protected actions from one canonical linearization point; already-started work remains unresolved until containment, cancellation, recovery, or external confirmation proves its outcome.
- Soma proves procedural coherence and operational safety. Named acceptance authorities judge substantive correctness.

## Current V3-1B Checkpoint — Kernel of One

**Status:** architecture/schema foundations, Agent/Worker mechanics, and `V3-1B-BOOTSTRAP-PLAN-AUTHORITY-1` are accepted. `V3-1B-OUTCOME-ACCEPTANCE-1` is active.

**Accepted mechanics already present:** additive Company Kernel schema v3; immutable Company/Mission/PlanRevision/WorkPackage/Attempt/Acceptance records; trusted configuration-anchored Company/Mission bootstrap; bounded PlanRevision DAG and graph manifest; exact dependency proofs; current-plan reasoning admission through canonical Task; bounded coordinator; provider-neutral reasoning backend contract; protected mutation broker; evidence/FanIn mechanics. These mechanisms must be reused rather than rebuilt.

**Active package outcome:** add the smallest internal named-authority service that can create/replay exactly one immutable AcceptanceCommit only after verifying the exact current WorkPackage/outcome/attempt, canonical ProjectScope Task/Run binding, terminal successful Task and Run, published result hashes, explicit acceptance basis, immutable Company/Mission/WorkPackage acceptance authority, and Mission kernel CAS.

**Boundary:** no automatic/model-owned acceptance, live reasoning/provider activation, Codex use without a new explicit owner request, public company gateway, `reconcile_one`, worker-facing Soma MCP, Role/Assignment/delegation state, scheduled autonomy, external business mutation, deployment or push.

**Next transition after acceptance:** bounded V3-1B projections + `reconcile_one`, followed by strict owner/executive company gateways and a separate controlled live kernel activation gate.

## Completed Lane: V3-1A — Interactive Worker Substrate

**Status:** accepted and closed in source on 2026-08-02. Runtime activation remains pending a later controlled restart and connector refresh; no live-source claim is made before that gate.

**Result:** exact provider-session evidence, sanitised stand-in process identity, zero-orphan cancellation, non-terminal controller waiting, atomic `steer`/`supply_input`, single-claimer delivery, acknowledgement-proven resume, bounded checkpoint expiry, explicit recovery windows, canonical backend cancellation delegation, and race closure all passed without adding a second lifecycle authority. Final implementation commit: `bf455b1da14f1fd5f959483444efa66662a78844`. Full evidence is [`docs/V3_1A_INTERACTION_COMMANDS_1_COMPLETION_2026-08-02.md`](docs/V3_1A_INTERACTION_COMMANDS_1_COMPLETION_2026-08-02.md).

**Activation boundary:** the running Soma service remains on the prior build. Real provider execution and production activation remain inactive.

## Completed Lane: RELIABILITY-1 — Existing Runtime Hardening

**Status:** accepted and closed on 2026-08-02 after objective audit. All defects known at closure, `REL-001` through `REL-024`, are closed and live; later defects continue in the same ledger without reopening the lane. `REL-028` is closed and live after exact reproduction, regression validation, owner-approved restart/refresh, source/runtime/schema convergence, omitted-profile `hermes_python` execution, and pre-launch refusal of an explicit PowerShell mismatch. Restart/refresh convergence, disposable scenarios, integrity, documentation, and final quiet preflight passed for the original lane. The authoritative evidence is [`docs/RELIABILITY_1_GATE_AND_BUG_LEDGER_2026-08-01.md`](docs/RELIABILITY_1_GATE_AND_BUG_LEDGER_2026-08-01.md).

**Result:** the existing runtime is proven reliable across fresh-project onboarding, ProjectScope and memory, runtime/connector convergence, repository transactions, task/run durability, supervisor/workflow handoffs, restart recovery, isolation, integrity, evidence, and operational use. No push occurred.

## Completed Corrective Fix: MEMORY-REPOSITORY-ONBOARDING-1

**Status:** implementation accepted and live on 2026-08-01. The immediate `axon_modelling` repair and the public onboarding action are both active after the owner-approved Soma restart and connector refresh. Evidence is recorded in [`docs/MEMORY_REPOSITORY_ONBOARDING_1_RESULT_2026-08-01.md`](docs/MEMORY_REPOSITORY_ONBOARDING_1_RESULT_2026-08-01.md).

Newly discovered repositories remain read-only with respect to ProjectScope. Controllers may explicitly call `memory_bind_repository` to create or return one deterministic, idempotent repository binding and receive the exact scope required by canonical memory operations. Exact ProjectScope enforcement remains unchanged.

The active V3 interaction-foundation architecture review is not altered by this corrective fix.

## Completed Corrective Lane: REPO-DOCUMENT-EDITING-1

**Status:** both batches accepted and closed on 2026-07-31. The authoritative results are [`docs/REPO_DOCUMENT_EDITING_1_RESULT_2026-07-31.md`](docs/REPO_DOCUMENT_EDITING_1_RESULT_2026-07-31.md) and [`docs/REPO_DOCUMENT_EDITING_1_HISTORY_HYGIENE_RESULT_2026-07-31.md`](docs/REPO_DOCUMENT_EDITING_1_HISTORY_HYGIENE_RESULT_2026-07-31.md). V3-1A product implementation remains paused, and the documentation-only interaction-foundation architecture review is active again.

**Goal:** make the existing repository write surface safe and practical for coherent documentation changes, and close the proven browser-pulse handoff deadlock without broadening into the autonomous-company implementation.

### First corrective batch

1. Recognise every supervisor state that deliberately hands control back to ChatGPT or the owner, including `needs_external_coder` and `approval_required`, so the browser pulse cannot poll forever on a parked handoff.
2. Make line-range edits fail closed on missing anchors, invalid bounds, and same-file composition that could shift coordinates.
3. Add one hash-bound whole-file replacement operation for existing text files so a coherent document rewrite can be previewed, atomically applied, and committed once.
4. Add focused regression tests for the exact defects and preserve all current hash, preview, rollback, newline, and commit protections.

### Boundaries

- Do not add Markdown section intelligence, typed public edit unions, multi-commit drafting sessions, or unrelated repository tooling in this first batch.
- Do not weaken all-or-nothing preview validation, stale-hash checks, base-HEAD checks, rollback, or isolated commits.
- Do not resume V3-1A interaction implementation, launch provider agents, or change unrelated runtime authority.
- Preserve unrelated work and do not push.

### First-batch acceptance

The first batch is accepted: 109 focused tests and 77 adjacent server/payload tests passed; unsafe line-range cases reject deterministically; hash-bound whole-file replacement preserves explicit newline policy; the worktree closed clean; and all changes were locally committed with no push.

### Second-batch acceptance

The history-hygiene batch is accepted. `commit_mode="manual"` now supports preview → apply → inspect/test → explicit selected-file commit, while `auto` remains compatible. Manual apply followed by manual revert was proven to leave both HEAD and the worktree unchanged. Create/remove preview metadata and revert/cleanup/move automatic-commit metadata are supported. Validation passed with 450 focused tests plus 75 adjacent tests and 26 expected skips.

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

**Status:** **provider discovery and pilot sequence documentation-closed; production integration has not started.** The original decision remains in [`docs/MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md`](docs/MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md), the executed result is [`docs/PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md`](docs/PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md), and the accepted production boundary is [`docs/BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md`](docs/BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md).

The decision preserves Markdown + Git as canonical, Obsidian as owner workspace and Soma as authority. Basic Memory `0.22.1` passed the bounded compatibility pilot and is accepted as the replaceable local semantic provider only behind a minimal Soma binding and health guard. MCP Connector `0.28.1` remains rejected; no parallel provider trial or custom retrieval engine is authorized.

The black-box contract was executed hardest requirement first. Basic Memory rebuilt 7/7 entities per project from deleted derived state, failed closed from a deliberately partial interrupted index, passed every lexical canary and all four English/Persian directions, leaked no sibling result, reflected filesystem changes, survived three restart cycles and removed cleanly. Direct production use remains blocked by fail-open project omission, cloud fallback for unknown identity, insufficient provider-native completeness health and canonical Markdown mutation on first sync.

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

**Status:** **executed and documentation-closed** with outcome `accept_with_minimal_soma_health_and_binding_guard`. The gate remains in [`docs/PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md`](docs/PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md); the authoritative result is [`docs/PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md`](docs/PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md), with machine-readable evidence in [`docs/pilot-basic-memory-2-results-2026-07-28.json`](docs/pilot-basic-memory-2-results-2026-07-28.json) and [`docs/pilot-basic-memory-2-frozen-corpus-2026-07-28.json`](docs/pilot-basic-memory-2-frozen-corpus-2026-07-28.json).

Basic Memory `0.22.1` passed complete rebuild, partial-index fail-closed behaviour, all lexical canaries, the four-direction English/Persian matrix, sibling isolation, safe abstention, filesystem freshness, restart stability and clean removal. It requires a Soma guard because omitted identity routes to a configured project, unknown identity attempts cloud routing, `bm doctor` and `bm status --wait` cannot establish safe project health, the multilingual threshold requires frozen calibration, Windows installation needs the tested dependency pin, and first sync rewrites canonical Markdown.

No production integration begins from the pilot result alone.

### BASIC-MEMORY-GUARD-1 - Minimal Soma Binding and Health Guard

**Status:** **provider compatibility and no-mutation confirmation remain closed, but controller-production acceptance is superseded by the shared-memory architecture review.** The authoritative boundary remains [`docs/BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md`](docs/BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md), the implementation record is [`docs/BASIC_MEMORY_GUARD_1_IMPLEMENTATION_2026-07-28.md`](docs/BASIC_MEMORY_GUARD_1_IMPLEMENTATION_2026-07-28.md), and the live confirmation is [`docs/BASIC_MEMORY_GUARD_1_CONFIRMATION_2026-07-28.md`](docs/BASIC_MEMORY_GUARD_1_CONFIRMATION_2026-07-28.md).

Basic Memory `0.22.1` remains accepted as a replaceable local retrieval provider. The confirmed profile still requires `ensure_frontmatter_on_sync = false` plus `disable_permalinks = true`, and the measured provider, bilingual, isolation, fallback and cleanup evidence remains valid.

Post-confirmation repository review found that the current guard does not yet justify controller connection: health compares counts rather than exact indexed paths, failed provider output can be parsed, the frozen stack is not runtime-enforced, absent ProjectScope can be treated as active, the whole ambient environment is inherited, supersession is not crash-safe, integrity hashing excludes lifecycle/provenance, the canonical vault is hidden under `runs/`, owner notes are classified as malformed, and legacy writers still create a competing SQLite truth.

The guard is therefore a **provider adapter foundation**, not a production-ready memory authority. Semantic retrieval may not report healthy until exact path/hash reconciliation is proven; when the provider cannot expose sufficient evidence, canonical lexical retrieval ships and semantic mode remains disabled or explicitly non-authoritative.

### SOMA-SHARED-MEMORY-ARCH-1 - Canonical Shared Memory Architecture

**Status:** **owner-approved and documentation-closed.** The authoritative decision is [`docs/SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md`](docs/SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md), with machine-readable controls in [`docs/soma-shared-memory-architecture-decision-2026-07-28.json`](docs/soma-shared-memory-architecture-decision-2026-07-28.json).

Soma owns one coherent memory authority across ChatGPT, Claude Code and Hermes. `soma/knowledge/` becomes the foundation of `CanonicalMemoryService`; owner-visible Markdown in an external private Obsidian vault is canonical; SQLite catalogs and Basic Memory indexes are disposable; `soma/memory_guard/` is logically subordinate as the Basic Memory adapter; the old `soma/memory/` store becomes read-only compatibility/import state; and research remains a separate authority plane.

The first public contract uses named `memory_*` operations inside the existing `knowledge_query` and `knowledge_action` gateways. No new top-level memory gateways are added in the first lane. Supersession is immutable replacement-link-derived, complete context packets are persisted before bounded controller projection, project scope is exact through ProjectScope, and personal scope remains a later sibling authority.

The production external private Obsidian vault root is now owner-decided as `D:\SomaMemory`. Project memory resolves below `D:\SomaMemory\projects\<project_id>`. No real owner memory has been imported.

### MEMORY-INTEGRATION-FOUNDATION-1 - Canonical Authority and Guard Repair

**Status:** **implemented, validated, documentation-closed, and pushed on `lane/memory-integration-foundation-1`.** The authoritative result is [`docs/MEMORY_INTEGRATION_FOUNDATION_1_RESULT_2026-07-28.md`](docs/MEMORY_INTEGRATION_FOUNDATION_1_RESULT_2026-07-28.md), with the decisive provider measurement in [`docs/MEMORY_INTEGRATION_FOUNDATION_1_COVERAGE_MEASUREMENT_2026-07-28.md`](docs/MEMORY_INTEGRATION_FOUNDATION_1_COVERAGE_MEASUREMENT_2026-07-28.md).

All ten reviewed defects are repaired. `CanonicalMemoryService` now owns scope-bound canonical Markdown, compare-and-swap correction, link-derived crash-safe supersession, lifecycle, health, and exact persisted context packets. Five query and seven action operations use the existing knowledge gateways. Every legacy canonical writer is frozen or redirected, and rebuild work remains under the existing task/run authority.

The exact provider-membership measurement is negative. Basic Memory `0.22.1` exposes correct cardinality but only a capped ten-row activity feed, not the indexed set. Semantic retrieval is therefore disabled; canonical lexical retrieval ships and identifies itself honestly. A future provider that enumerates its full indexed membership can activate the implemented reconciliation path without changing authority.

Full regression: 2227 passed, 35 skipped. The disposable provider was removed completely. No owner memory, personal scope, bulk legacy migration, deployment, push, or provider-internal database dependency was introduced.

### SOMA-CANONICAL-MEMORY-VAULT-1 - Production Vault Root

**Status:** **owner-decided, locally configured, and documentation-closed.** The authoritative decision is [`docs/SOMA_CANONICAL_MEMORY_VAULT_DECISION_2026-07-28.md`](docs/SOMA_CANONICAL_MEMORY_VAULT_DECISION_2026-07-28.md), with machine-readable controls in [`docs/soma-canonical-memory-vault-decision-2026-07-28.json`](docs/soma-canonical-memory-vault-decision-2026-07-28.json).

The production external private Obsidian vault root is `D:\SomaMemory`. Project memory resolves below `D:\SomaMemory\projects\<project_id>`. Empty `projects`, `personal`, and `shared` scaffolding exists locally, and the ignored live `config.yaml` is configured with `canonical_vault_kind: external_private_vault`.

The path is outside code repositories, outside `runs/`, and outside cloud-synchronised user folders by default. No owner memory was imported, no personal scope was activated, no private Git repository or cloud sync was created, and the service was not restarted by the decision.

### MEMORY-REAL-PROJECT-TRIAL-1 - Bounded Cross-Controller Trial

**Status:** **executed, accepted, pushed, and documentation-closed.** The authoritative result is [`docs/MEMORY_REAL_PROJECT_TRIAL_1_RESULT_2026-07-28.md`](docs/MEMORY_REAL_PROJECT_TRIAL_1_RESULT_2026-07-28.md).

Nine reviewed Soma project memories are live under `D:\SomaMemory`. Canonical health is `healthy` at 9/9 with zero malformed, unadopted, or drifted records; provider health remains honestly `degraded`; production retrieval remains `catalog_lexical`. Fresh Claude Code, ChatGPT, and Hermes paths all completed the memory flow, including packet identity and hash-stable retrieval.

The closed trial does not authorise personal memory, bulk legacy import, unprovable semantic retrieval, automatic conversation ingestion, Git/cloud backup, or deployment.

### MEMORY-CONTROLLER-ERGONOMICS-1 - Scope Discovery and Save Ergonomics

**Status:** **implemented, validated, documentation-corrected, and pushed.** The result is [`docs/MEMORY_CONTROLLER_ERGONOMICS_1_RESULT_2026-07-29.md`](docs/MEMORY_CONTROLLER_ERGONOMICS_1_RESULT_2026-07-29.md).

Unlike the earlier memory lanes, this lane had no owner-authored decision document before execution. Its scope was selected at start time and bounded to two additive changes: `memory_scope` lets a controller discover the exact explicit project scope from a repository name, while every memory operation still refuses missing scope; and `memory_save` may derive a deterministic `vault_path` from kind and title, while an explicit path still wins and titles with no usable ASCII stem require an explicit path. Retrieval behavior, semantic activation, personal scope, legacy import, and automatic ingestion remain untouched.

The implementation passed 2252 tests with 35 skipped and live vault health remained `healthy` at 10/10 with zero drift. Fresh MCP discovery exposed the new operation, but the already-open ChatGPT connector session still advertised the previous `knowledge_query` schema and rejected `memory_scope` before runtime. That isolated connector-refresh question is now governed by the separate verification-only gate below.

### MEMORY-CONNECTOR-REFRESH-VERIFY-1 - Refreshed ChatGPT Connector Gate

**Status:** **executed, passed, pushed, and documentation-closed.** The authoritative gate is [`docs/MEMORY_CONNECTOR_REFRESH_VERIFY_1_GATE_2026-07-29.md`](docs/MEMORY_CONNECTOR_REFRESH_VERIFY_1_GATE_2026-07-29.md), and the result is [`docs/MEMORY_CONNECTOR_REFRESH_VERIFY_1_RESULT_2026-07-29.md`](docs/MEMORY_CONNECTOR_REFRESH_VERIFY_1_RESULT_2026-07-29.md).

Localhost and the public `mcp.spaceshipgames.win` tunnel advertised the same 32-gateway build and the same effective contract. After the ChatGPT connector refreshed, `capability_identity` converged with no mismatches, `memory_scope` returned the exact Soma project scope, `memory_health` succeeded at 10/10 with zero drift, and an unscoped health call remained refused. The original rejection was stale client discovery, not a server defect; no code, schema, configuration, credential, connector, provider, retrieval, or memory change was needed.

The result also records that the ubiquitous response field `schema_hash` is not an effective gateway-contract identity. Controllers must use `public_schema_hash`, `discovery_cache_generation`, or the per-operation hashes from `capability_identity`. Changing the legacy field's meaning would be a separate public-contract decision, not work authorised by this closed gate.

### PUBLIC-CAPABILITY-METADATA-1 - Effective Contract Identity

**Status:** **executed, accepted as `implemented-compatible`, pushed, and documentation-closed.** The authoritative gate is [`docs/PUBLIC_CAPABILITY_METADATA_1_GATE_2026-07-29.md`](docs/PUBLIC_CAPABILITY_METADATA_1_GATE_2026-07-29.md), and the result is [`docs/PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md`](docs/PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md).

The lane inventoried the public capability envelope and added `public_schema_hash` to every public response. The value is derived from the schemas actually served through MCP discovery, matching the `public_schema_hash` and `live_input_schema_hash` reported by `capability_identity`. It moves when the public input contract changes and remains stable across implementation-only builds. Discovery/runtime agreement, per-operation isolation, stale-value guidance, localhost/public-tunnel agreement, the strict `knowledge_action` output contract, and the full gateway inventory are regression-covered. Full validation passed with 2258 tests and 35 skips.

The legacy `schema_hash` remains present with its original `PATCH_OPERATION_SCHEMA` meaning and unchanged value; it is informational only and must not be used to detect gateway-contract changes. Controllers compare contracts with `public_schema_hash`, compare one operation with `operation_schema_hashes[gateway.operation]`, and use `discovery_cache_generation` to decide whether to refresh cached discovery. No memory or other gateway behaviour, connector credentials or internals, deployment state, or existing public field meaning changed.

### LEGACY-RETIREMENT-AUDIT-1 - Pre-V3 Compatibility and Retirement Map

**Status:** **executed and closed as `audit-complete`.** The gate remains [`docs/LEGACY_RETIREMENT_AUDIT_1_GATE_2026-07-29.md`](docs/LEGACY_RETIREMENT_AUDIT_1_GATE_2026-07-29.md); the authoritative result is [`docs/LEGACY_RETIREMENT_AUDIT_1_RESULT_2026-07-29.md`](docs/LEGACY_RETIREMENT_AUDIT_1_RESULT_2026-07-29.md), with item-level classification in [`docs/legacy-retirement-audit-1-manifest-2026-07-29.json`](docs/legacy-retirement-audit-1-manifest-2026-07-29.json). No product source, test, schema, configuration, durable state or external service was changed.

This audit-only gate classifies repository paths and subsystems as `keep_live`, `keep_compatibility_read`, `freeze_no_new_use`, `migrate_then_retire`, `remove_candidate`, `defer_v3_consolidation`, or `unknown_blocked`. It requires evidence across runtime registration, all public gateways, startup, configuration, packaging, durable state, migrations, tests, historical records and known external consumers. Static absence alone is never proof that a path is dead.

**Outcome: nothing tracked in the repository is removable before V3.** The single `remove_candidate` is the untracked `soma/codex_router/` cache residue, which is not a tracked-repository change. `soma/pilot_memory_1b/` is `keep_compatibility_read` despite having no production importer, because its modules are the live attestation for the published frozen-benchmark hashes, all three of which were verified to still reproduce. `soma/local_agent/orchestrator.py` is `unknown_blocked`: it is exported through `soma.local_agent.__all__` and the package-level `__getattr__`, so it is a public Python package surface even though it is not an MCP gateway, and unknown external import consumption blocks retirement. The generic `soma.knowledge` operations are `unknown_blocked` on unknown MCP controller usage. `soma/local_coding/` and the `RepoWikiService.wiki_exclusions` manifest field are `migrate_then_retire`. The execution planes are `defer_v3_consolidation`.

The audit's own next decision is a **measurement** lane, not a removal lane: external MCP operation usage and external package imports are the single missing evidence blocking the knowledge operations, the orchestrator and the deferred `schema_hash` deprecation alike.

The gate may write only its result, machine-readable manifest and closure update to this plan. It authorises no source or test deletion, public-contract change, migration, durable-state mutation, dependency or service change, lifecycle consolidation, deployment, or unrelated cleanup. Any actual removal requires a separate owner-approved implementation lane.

### EXTERNAL-CONSUMER-MEASUREMENT-1 - Bounded Public-Surface Usage Evidence

**Status:** **executed and closed as `measurement-complete`.** The gate remains in [`docs/EXTERNAL_CONSUMER_MEASUREMENT_1_GATE_2026-07-29.md`](docs/EXTERNAL_CONSUMER_MEASUREMENT_1_GATE_2026-07-29.md); the authoritative result is [`docs/EXTERNAL_CONSUMER_MEASUREMENT_1_RESULT_2026-07-29.md`](docs/EXTERNAL_CONSUMER_MEASUREMENT_1_RESULT_2026-07-29.md) with per-surface classification in [`docs/external-consumer-measurement-1-matrix-2026-07-29.json`](docs/external-consumer-measurement-1-matrix-2026-07-29.json). No measured surface was changed and no product state was modified.

**Outcome: one of the three blocked surfaces is now decidable, one cannot be measured without new instrumentation, and one was not an evidence question at all.** The exported `LocalAgentOrchestrator` and `classify_task` symbols move from `unknown_blocked` to no use found across a complete declared universe — all eight registered non-Soma repositories, the Hermes checkout, the Trading Lab checkout and installed distribution, Claude Code configuration and plugins, and every Python environment on this machine, where the only Soma installation is an editable install pointing at the repository itself. Recommendation `prepare_deprecation_gate`, requiring explicit written owner acceptance of residual external-import risk, because level-4 absence inside a declared universe is not proof of global non-use.

The six generic `soma.knowledge` operations remain `remain_unknown_blocked`, and the reason is structural rather than a gap in searching: Soma logs HTTP lines only, every MCP operation is a `POST /mcp`, and the operation name lives in the unlogged JSON-RPC body. In the current log window 264 of 270 requests arrived from outside this machine through the public tunnel, so the dominant traffic is both real and opaque. The lane also established that these operations are **not** aliases of the canonical `memory_*` family: their reads serve the same canonical records, but their writes target `runs/knowledge/projects/<pid>/vault` while `memory_save` targets `D:/SomaMemory`, with both sharing one catalog — so retirement is a data question, not a routing rename.

Legacy `schema_hash` is confirmed `keep_active`. It is not merely emitted: `system_query.capability_identity` accepts `expected_schema_hash` and compares it, returning `mismatches: ["connector_schema_hash"]` on divergence, which verifies the `keep_live` correction made at the close of `LEGACY-RETIREMENT-AUDIT-1` by measurement rather than argument. A name collision with the unrelated Hermes companion `schema_hash`, computed by `effective_schema_hash()` over Hermes tool definitions, was identified and excluded rather than reported as a mandatory live consumer.

The exact next owner decisions are: approve or decline a bounded orchestrator retirement gate that sequences `soma/local_coding` and `soma.memory.importers.import_runs` and preserves the three mixed test files; and decide whether to open a separate owner-reviewed gate recording MCP operation names and nothing else for a bounded window, which is the single missing capability behind every unanswerable public-operation retirement question. Optionally, approve scanning `D:/Github/llm-council` to close the last local blind spot. This lane added no telemetry, wrote no canonical state, scanned no unapproved root and recorded no addresses, prompts or request arguments.

### MCP-OPERATION-USAGE-INSTRUMENTATION-1 - Bounded Aggregate Operation Counters

**Status:** **cancelled by owner during the production window; temporary instrumentation and activation state removed; no retirement decision produced.** The authoritative gate is [`docs/MCP_OPERATION_USAGE_INSTRUMENTATION_1_GATE_2026-07-29.md`](docs/MCP_OPERATION_USAGE_INSTRUMENTATION_1_GATE_2026-07-29.md).

The owner-authorised aggregate-only window was started and later cancelled when the owner decided the added cleanup work was not worth further time. At cancellation it had observed 146 counted calls and 7 unmapped or rejected calls, so the incomplete window was not valid evidence under its own gate and produced no deprecation or retirement decision. No request or response content, per-call event, timestamp, client, address, session, project or repository identity was recorded.

The temporary activation variables and measurement artifact were removed, `soma/server.py` was restored to the product baseline, and the temporary counter module and focused test were deleted. The historical gate remains only as a record of the abandoned experiment. It authorises no deprecation, routing change, memory write, two-vault migration, permanent telemetry or Roadmap V3 implementation.

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

`DeusData/codebase-memory-mcp` is the preferred ready-made candidate for derived repository structure: symbols, calls, routes, architecture, source snippets, and change impact. It does not overlap with the owner-authored project-memory lane. The Basic Memory provider gate is now documentation-closed and its minimal guard decision is prepared; code intelligence remains inactive until the owner selects it, and neither provider replaces the repository, Git, `RepoWikiService`, canonical Markdown or Soma authority.

A future `PILOT-CODE-INTELLIGENCE-1` may test a pinned, checksum-verified binary through an explicit Soma project/repository binding, with cache outside the repository, `CBM_ALLOWED_ROOT` enforced, auto-index and auto-watch disabled, no installer edits, no `manage_adr`, no committed graph artifact, no subagents, and no push. The pilot is not active.

## Prerequisites Before Autonomous Scheduled Agent Work

These requirements do not block STABILIZE-1 or the early pilots, but autonomous scheduled agent work may not be enabled without both:

- project-scoped provider, model, token, usage, and cost accounting with ceilings that pause scheduled work;
- a fixed golden-task evaluation set that tests repository outcome, correctness, scope, evidence, and cleanliness before agent output is accepted.

## Roadmap V3 Active Sequence

Roadmap V3 remains outcome-led. It defines exact contracts and invariants only where identity, compatibility, durability, authority, or recovery require precision.

**Architecture status:** accepted and amended. The architecture, reconciliation, and hierarchical-intelligence contract are respectively [docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md](docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md), [docs/SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md](docs/SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md), and [docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md](docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md). Research is closed.

**Lifecycle policy:** progressive lifecycle convergence. No broad preliminary consolidation lane is required, and no duplicate generic lifecycle authority may be preserved indefinitely. Workflows and supervisors are generic lifecycle managers, not protected business domains. Their overlapping responsibilities must be projected or retired when later V3 lanes touch them. SSH activation, Trading Lab, memory, research, and business systems retain irreducible domain facts while their work execution converges on canonical tasks and runs.

**Sequence:** `V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1` → accepted and re-scoped interaction implementation → close V3-1A → V3-1B → V3-2 → bounded collaboration → temporary organisation → broader autonomous-company outcomes.

**Active lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`. Its only active package is [docs/V3_1A_INTERACTION_FOUNDATION_ARCHITECTURE_REVIEW_2026-07-31.md](docs/V3_1A_INTERACTION_FOUNDATION_ARCHITECTURE_REVIEW_2026-07-31.md). Product implementation is paused.

**Closed package:** `V3-1A-FOUNDATION-1 — Shared Contracts and Persistence` is accepted after independent audit and corrective commit `c11919e7410faef7c351b318de396000845e8e5a`. The acceptance evidence and recorded external cancellation baseline failure are in [docs/V3_1A_FOUNDATION_1_ACCEPTANCE_AUDIT_2026-07-30.md](docs/V3_1A_FOUNDATION_1_ACCEPTANCE_AUDIT_2026-07-30.md).

**Closed package:** `V3-1A-ADAPTER-CONTRACT-1 — Provider Adapter Contract and Protocol Fixtures` is accepted after independent audit and corrective commit `7d629c5bdd0ade1d3d0da262bcd8509f50744041`. The acceptance evidence is in [docs/V3_1A_ADAPTER_CONTRACT_1_ACCEPTANCE_AUDIT_2026-07-30.md](docs/V3_1A_ADAPTER_CONTRACT_1_ACCEPTANCE_AUDIT_2026-07-30.md).

**Closed package:** `V3-1A-PROCESS-IDENTITY-1 — Sanitised Launch and Owned-Tree Cancellation` is accepted after iterative corrective packages, with accepted runtime at `7cc66c50675a91ff958d39a3c53e6246a88268d6`. The original failed audits and corrective gates remain historical evidence; final acceptance is recorded in [docs/V3_1A_PROCESS_IDENTITY_1_FINAL_ACCEPTANCE_AUDIT_2026-07-31.md](docs/V3_1A_PROCESS_IDENTITY_1_FINAL_ACCEPTANCE_AUDIT_2026-07-31.md). Independent validation passed 413 focused tests plus one disclosed strict xfail, seven sharp regressions, and the uncontended full suite at 2556 passed, 35 skipped, 1 xfailed. The accepted contract includes exact process identities, zero raw-PID action, root-exit/tree-exit separation, lock retention on uncertainty, Windows `KILL_ON_JOB_CLOSE`, zero-descendant cancellation proof, honest publication retry, deterministic cancellation ordering, and zero generic lifecycle-authority increase.

**Active documentation package:** `V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1`. It freezes the interaction transaction, delivery-attempt, wait/resume, message-class, identity, and precedence contracts before implementation.

**Paused product package:** `V3-1A-INTERACTION-COMMANDS-1`. Its existing gate remains historical input and must be re-scoped and explicitly reactivated after the review passes. Real providers, later V3 outcomes, production activation, and push remain outside this package.

`MEMORY-INTEGRATION-FOUNDATION-1` is implemented and validated. `SOMA-CANONICAL-MEMORY-VAULT-1` selects and locally configures `D:\SomaMemory` as the production external private Obsidian vault. `MEMORY-REAL-PROJECT-TRIAL-1` is executed, accepted, pushed, and documentation-closed with Claude Code, ChatGPT, and Hermes verification complete. `MEMORY-CONTROLLER-ERGONOMICS-1` is implemented and documentation-closed; `MEMORY-CONNECTOR-REFRESH-VERIFY-1` is executed, passed, and closed with refreshed ChatGPT verification complete. `PUBLIC-CAPABILITY-METADATA-1` is executed, accepted as `implemented-compatible`, pushed, and closed; effective gateway-contract identity is now explicit while legacy `schema_hash` compatibility is preserved. `LEGACY-RETIREMENT-AUDIT-1` is executed and closed as `audit-complete` in [`docs/LEGACY_RETIREMENT_AUDIT_1_RESULT_2026-07-29.md`](docs/LEGACY_RETIREMENT_AUDIT_1_RESULT_2026-07-29.md), with item-level classification in [`docs/legacy-retirement-audit-1-manifest-2026-07-29.json`](docs/legacy-retirement-audit-1-manifest-2026-07-29.json); no product path was removed or modified. Nothing tracked in the repository is removable before V3: the only `remove_candidate` is the untracked `soma/codex_router/` build residue. `soma/pilot_memory_1b/` must be kept despite having no production importer, because its modules are the live attestation for the published frozen-benchmark hashes. `soma/local_agent/orchestrator.py` is `unknown_blocked` because it is exported through `soma.local_agent.__all__` and the package-level `__getattr__`, making it a public Python package surface with unknown external consumption. Retiring the generic `soma.knowledge` operations is `unknown_blocked` on the same missing external-consumer inventory that blocks `schema_hash` deprecation. `EXTERNAL-CONSUMER-MEASUREMENT-1` is executed and closed as `measurement-complete` in [`docs/EXTERNAL_CONSUMER_MEASUREMENT_1_RESULT_2026-07-29.md`](docs/EXTERNAL_CONSUMER_MEASUREMENT_1_RESULT_2026-07-29.md), with per-surface classification in [`docs/external-consumer-measurement-1-matrix-2026-07-29.json`](docs/external-consumer-measurement-1-matrix-2026-07-29.json); no measured surface was changed. The exported `LocalAgentOrchestrator` and `classify_task` symbols are no longer `unknown_blocked`: no use was found anywhere in the declared universe, and the only Soma installation on this machine is an editable install pointing at the repository itself, so the orchestrator is now `prepare_deprecation_gate` subject to explicit owner acceptance of residual external-import risk. The generic `soma.knowledge` operations stay blocked for a structural reason rather than a search gap, because Soma logs only `POST /mcp` HTTP lines while operation names travel in the unlogged body, and 264 of 270 requests in the current window came from outside this machine; those operations are also not aliases of `memory_*`, since their writes target a different vault root under a shared catalog. Legacy `schema_hash` is confirmed `keep_active` by measurement: `capability_identity` accepts and compares `expected_schema_hash`, and the similarly named Hermes companion field is a distinct value that was excluded rather than miscounted as a consumer. `MCP-OPERATION-USAGE-INSTRUMENTATION-1` was cancelled by the owner during its production window; its temporary instrumentation, activation state and measurement artifact were removed, and the incomplete and invalid window authorises no retirement conclusion. Deletion still requires a separate owner-approved implementation lane. Semantic retrieval remains disabled because Basic Memory cannot enumerate exact indexed membership; canonical lexical retrieval is the accepted production mode. A generic `continue` does not start the operation-usage instrumentation gate, import owner memory, activate personal scope, initialise Git/cloud sync, deploy, retire compatibility paths, or start another implementation lane. `PILOT-CODE-INTELLIGENCE-1` remains planned and inactive. `FUTURE-CORTANA-PRESENCE-AGENT-RESEARCH` remains parked.
