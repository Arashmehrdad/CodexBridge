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

**Status:** Gate A implemented and owner-accepted at `e306d5c9ef0826967c28b63db465b64c1dc0efa2`. **Gate B executed, owner-reviewed, and accepted on 2026-07-27**: ProjectScope v1 schema is live, empty, and inactive. **Gate C is prepared but remains unapproved and non-executable.** `GATE-C-PREREQ-1` is **owner-accepted and closed** after the idempotency correction at `22fd884`. **ProjectScope schema v2 activation is now prepared but remains unauthorized and unexecuted**; the review package is [`docs/SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_PREPARATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_PREPARATION_2026-07-27.md), with machine-readable evidence in [`docs/scope-foundation-1-project-scope-v2-activation-preparation-2026-07-27.json`](docs/scope-foundation-1-project-scope-v2-activation-preparation-2026-07-27.json). A current-store disposable rehearsal applied exactly `[2]` then `[]`, added only the reviewed empty adjudication table and index, preserved incumbent identities/publication evidence, and left the live store at v1 with settings `[0, 0]`. Historical disposition, Gate C, memory integration, Hermes, unrelated cleanup, and push remain unauthorized.

Gate B preparation is recorded in [`docs/SCOPE_FOUNDATION_1_GATE_B_PREPARATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_GATE_B_PREPARATION_2026-07-27.md), with a machine-readable rehearsal manifest in [`docs/scope-foundation-1-gate-b-preparation-2026-07-27.json`](docs/scope-foundation-1-gate-b-preparation-2026-07-27.json). The activation itself is recorded in [`docs/scope-foundation-1-gate-b-activation-2026-07-27.md`](docs/scope-foundation-1-gate-b-activation-2026-07-27.md), with machine-readable evidence in [`docs/scope-foundation-1-gate-b-activation-2026-07-27.json`](docs/scope-foundation-1-gate-b-activation-2026-07-27.json). All 32 verification gates passed: the migration applied once, run/task counts and stable ID hashes were unchanged, the incumbent schema hash was unchanged, integrity and foreign-key checks passed, and every identity, binding, reservation, bootstrap-event, and quarantine table is empty with `scoped_writes_enabled = 0` and enforcement `inactive`. The rollback backup is `runs/soma.sqlite3.backup-gate-b-20260727T131451Z` (sha256 `f47cc830c0ecc5f7cd13a1103a230adff0b645417dc4368dbdaa8b98e9af1296`).

Gate C preparation is recorded in [`docs/SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md), with a machine-readable manifest in [`docs/scope-foundation-1-gate-c-preparation-2026-07-27.json`](docs/scope-foundation-1-gate-c-preparation-2026-07-27.json). The proposed exact identities are `proj_a144f759-1619-4276-9292-28704b6611f4` and `res_5b67936d-9599-4f08-b817-b3c30564400f`, bound exclusively to canonical repository root `d:/github/soma` with identity hash `1f7c8e8726a452826177d0fb06d08b0e73df3695cd9e52f3a37d9b53cd451441`. Live preview was conflict-free and made zero writes; an exact-ID disposable cutover rehearsal passed bootstrap, idempotency, enforcement, pause rollback, integrity, and foreign-key checks. The quarantine-remedy prerequisite is now accepted. Gate C remains blocked only by the separately reviewed and owner-approved schema-v2 activation, followed by a fresh exact-identity preview and explicit Gate C approval.

Gate A passed the full implementation and disposable-store gates. The owner ratified project-less access as an owner-controller compatibility path only, terminal evidence-preserving quarantine with an explicit adjudication/supersession prerequisite before Gate C, and the v1 one-task/one-run-attempt invariant. No additional Claude CLI retry is required. Successful live scoped controller calls are deferred until Gate C because Gate B creates schema only.

The smallest coherent production lane is a main-store ProjectScope v1 sidecar for **new canonical task/run work only**. It establishes immutable projects, repository-resource bindings, task scope reservations, run-attempt reservations, deterministic recovery/quarantine evidence, and optional strict MCP project assertions while preserving the incumbent task, run, process, result, evidence, and operation-lock authorities.

Memory, Hermes and other external sessions, worktrees, credentials, other legacy run producers, and historical assignment are explicit exclusions. Live schema activation and project/repository bootstrap are separate post-implementation owner gates. The full outcome-led proposal, invariants, migration boundaries, compatibility contract, acceptance evidence, retry limits, and stop conditions are in [`docs/SCOPE_FOUNDATION_1_PRODUCTION_LANE_PROPOSAL_2026-07-27.md`](docs/SCOPE_FOUNDATION_1_PRODUCTION_LANE_PROPOSAL_2026-07-27.md).

### PILOT-MEMORY-1 - Smallest Durable Memory Baseline

**Status:** started in **shadow mode** on 2026-07-27; not activated, not integrated, and holding no authority. Do not activate automatically.

The shadow baseline and its fixed benchmark are recorded in [`docs/pilot-memory-1-shadow-baseline-2026-07-27.md`](docs/pilot-memory-1-shadow-baseline-2026-07-27.md), with results in [`docs/pilot-memory-1-shadow-benchmark-2026-07-27.json`](docs/pilot-memory-1-shadow-benchmark-2026-07-27.json). Markdown plus Git plus Obsidian-native links, with a derive-on-read index and mandatory project scope, passed all seven required question classes in a disposable vault. That is **not** a finding that the baseline is sufficient: the corpus is small and synthetic, and every probe is a substring match. The benchmark does not yet discriminate, so it cannot yet justify or exclude a graph or memory service. The next step, when selected, is to harden the benchmark on superseding chains, meaning-based retrieval, frontmatter drift, and scale — not to adopt a provider. The owner review accepts this as valid **limitation evidence**, not as baseline acceptance or provider rejection. Shadow observation may continue; production memory authority and integration remain inactive.

**Purpose:** test canonical Markdown plus Git, structured Soma metadata, and Obsidian as the owner-facing workspace before adding a graph or memory service.

The baseline must answer representative questions about exact recall, current versus superseded facts, source resolution, external edits, deletion, rebuild, and project isolation. A more complex memory provider advances only after a fixed benchmark demonstrates a real failure of the baseline.

## Prerequisites Before Autonomous Scheduled Agent Work

These requirements do not block STABILIZE-1 or the early pilots, but autonomous scheduled agent work may not be enabled without both:

- project-scoped provider, model, token, usage, and cost accounting with ceilings that pause scheduled work;
- a fixed golden-task evaluation set that tests repository outcome, correctness, scope, evidence, and cleanliness before agent output is accepted.

## Roadmap V3 Trigger

Roadmap V3 is written only after the bridge evidence is reviewed. It should convert accepted findings into a smaller implementation sequence for an independent durable project-aware control plane, using proven external components through narrow replaceable boundaries.

Roadmap V3 should remain an outcome-led engineering roadmap. It may define exact public contracts and invariants where compatibility requires precision, but it should not become a giant collection of pre-written coding instructions for agents.

Until a new lane is explicitly selected, a generic `continue` does not begin production implementation, activate PILOT-MEMORY-1, revive a Roadmap V2 lane, or start Roadmap V3 feature work.
