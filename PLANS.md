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

**Status:** active - bounded investigation only. No production implementation is authorized by activation.

**Purpose:** prove that immutable project identity and external-session bindings can be introduced through the current canonical stores and projections without breaking existing clients.

The decisive test is confusion resistance: two deliberately similar projects must remain separated across tasks, runs, repositories, worktrees, evidence, retrieval, processes, credentials, and external bindings. Unscoped project work must fail closed.

### PILOT-MEMORY-1 - Smallest Durable Memory Baseline

**Status:** inactive. Do not activate automatically.

**Purpose:** test canonical Markdown plus Git, structured Soma metadata, and Obsidian as the owner-facing workspace before adding a graph or memory service.

The baseline must answer representative questions about exact recall, current versus superseded facts, source resolution, external edits, deletion, rebuild, and project isolation. A more complex memory provider advances only after a fixed benchmark demonstrates a real failure of the baseline.

## Prerequisites Before Autonomous Scheduled Agent Work

These requirements do not block STABILIZE-1 or the early pilots, but autonomous scheduled agent work may not be enabled without both:

- project-scoped provider, model, token, usage, and cost accounting with ceilings that pause scheduled work;
- a fixed golden-task evaluation set that tests repository outcome, correctness, scope, evidence, and cleanliness before agent output is accepted.

## Roadmap V3 Trigger

Roadmap V3 is written only after the bridge evidence is reviewed. It should convert accepted findings into a smaller implementation sequence for an independent durable project-aware control plane, using proven external components through narrow replaceable boundaries.

Roadmap V3 should remain an outcome-led engineering roadmap. It may define exact public contracts and invariants where compatibility requires precision, but it should not become a giant collection of pre-written coding instructions for agents.

Until then, a generic `continue` advances only the currently accepted STABILIZE-1 goal. It does not activate a pilot, revive a Roadmap V2 lane, or begin Roadmap V3 feature work.
