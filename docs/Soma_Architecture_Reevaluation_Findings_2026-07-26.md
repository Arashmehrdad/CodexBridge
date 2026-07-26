# Soma Architecture Re-evaluation Findings

**Date:** 2026-07-26  
**Status:** Decision record and implementation gate  
**Scope:** Six architecture evaluations by ChatGPT, Grok, Opus/Claude Code, GLM-5.2, Kimi-K3, and GPT-5.6 Sol Ultra, followed by owner-guided synthesis

## 1. Why this document exists

The revised Soma roadmap grew into a broad custom agent runtime covering projects, tasks, durable execution, agent sessions, memory, skills, knowledge systems, scheduling, model routing, browser and desktop automation, credentials, backup, provenance, and future Cortana presentation.

Before continuing that implementation sequence, the architecture was evaluated from six model perspectives: ChatGPT, Grok, Opus/Claude Code, GLM-5.2, Kimi-K3, and GPT-5.6 Sol Ultra using multiple specialist subagents. ChatGPT's evaluation was one of the six and was later also used to reconcile the findings with the owner's intent. The purpose was not to prove Soma was a mistake. It was to identify the smallest, strongest, most maintainable system that preserves the original vision without rebuilding mature tools unnecessarily.

The governing principle is now:

```text
ADOPT a proven tool where it satisfies the requirement
→ ADAPT or WRAP it where a bounded extension is enough
→ BORROW proven mechanics where direct adoption is unsuitable
→ BUILD only after a real requirement and a measured gap are demonstrated
```

The existing roadmap is therefore temporarily treated as a **requirements catalogue**, not an automatic implementation sequence.

## 2. Evidence classes

Future architecture decisions must distinguish three kinds of evidence:

```text
REPO-VERIFIED
Confirmed directly against the current Soma repository and live implementation.

EXTERNALLY-VERIFIED
Confirmed from official documentation, repositories, release material, or direct testing of candidate tools.

PROPOSED
An architectural inference that still requires a bounded pilot.
```

## 2.1 Six evaluation perspectives

The review set was:

1. **ChatGPT** — independent architecture and ecosystem evaluation using the roadmap, prior Soma decisions, live bounded repository inspection through Soma, and external research. It recommended freezing the roadmap as an implementation sequence, preserving Soma as an independent durable control plane, testing ACP before building a custom worker layer, moving ProjectScope forward, beginning memory with Markdown plus SQLite, and initially treating OpenClaw as an external front door rather than Soma's foundation.
2. **Grok** — broad strategic comparison that strongly favoured reducing Soma and adopting an existing personal-agent gateway, especially OpenClaw.
3. **Opus/Claude Code** — direct repository-wide evaluation from inside the live codebase. It identified what is actually implemented, what remains speculative, where lifecycle systems overlap, and ACP as the largest missing standards opportunity.
4. **GLM-5.2** — ecosystem and target-architecture evaluation favouring a thin Soma sidecar with OpenClaw, Basic Memory, Graphiti, coding agents, and Stagehand.
5. **Kimi-K3** — broad specialist-tool evaluation covering Cognee, Mem0/OpenMemory, Basic Memory, Agent Fleet, OpenHands Agent Canvas, OpenClaw, LiteLLM, and other adoption candidates.
6. **GPT-5.6 Sol Ultra with specialist subagents** — combined runtime-candidate, memory/workspace, and live-repository review. It endorsed the OpenClaw-shell plus Soma-kernel direction, found immediate repository issues that outrank new feature construction, rejected Agent Fleet as an execution authority while preserving its UX ideas, and proposed a measurable integration and latency gate.

Opus/Claude Code and GPT-5.6 Sol Ultra both inspected the live repository directly. Opus receives the highest weight for its repository-wide code-grounded findings; the Sol Ultra review adds a second direct audit plus specialist ecosystem analysis and concrete operational measurements.

ChatGPT, Grok, GLM-5.2, and Kimi-K3 provide complementary architecture and ecosystem analysis. ChatGPT's role is explicitly dual: it supplied one of the six evaluations and subsequently helped the owner compare, challenge, and synthesize all six. External-tool claims remain subject to official-source verification and hands-on pilots; no model's architectural preference overrides repository evidence or the owner's accepted intent.

## 3. Strong consensus across the reviews

All six evaluations converged on the same high-level conclusion:

> Soma should not continue expanding into a complete personal-agent operating system. It should become a smaller durable, project-aware coordination and control plane, while mature specialist tools are adopted through standard interfaces.

The reviews consistently preserve the following Soma responsibilities:

- canonical project and task identity;
- fail-closed project isolation;
- work graph and typed project relationships;
- durable runs, process identity, cancellation, leases, and restart reconciliation;
- exact repository, worktree, branch, and source truth;
- hash-verified mutation, evidence, artifacts, and result publication;
- compact progressive-disclosure MCP contracts for ChatGPT;
- existing Cloudflare, Docker, SSH, Hermes, Trading Lab, and other domain providers;
- owner-controlled recovery and replacement of external components.

They also consistently challenge or reduce:

- a large custom application container;
- a custom agent framework and broad worker-adapter hierarchy;
- five overlapping memory and knowledge systems;
- a custom browser or desktop automation engine;
- enterprise-scale runtime capsule and replay machinery;
- multiple schedulers and task authorities;
- premature Graphiti, Graphify, Anytype, model-routing, and swarm commitments;
- broad packaging and distribution work before the personal system is useful.

## 4. Current architectural direction

The current best synthesis is:

```text
Owner / ChatGPT executive controller
        │
        ▼
OpenClaw candidate shell
├── chat, voice, channels, sessions, and notifications
├── convenience schedules and browser automation
├── Codex app-server / ACP coding sessions
└── exact Soma MCP references and projections
        │
        │ MCP
        ▼
Soma
independent durable project-aware kernel
├── projects and ProjectScope
├── sparse work graph and canonical tasks
├── durable execution, leases, cancellation, and reconciliation
├── repository and worktree truth
├── immutable artifacts, evidence hashes, and result references
├── controller checkpoints, external bindings, and event digest
└── existing domain providers
        │
        ├── ACP / external session bindings → coding agents
        ├── MCP → specialist tools
        ├── CLI → 1Password and Kopia
        └── Markdown + Git → readable memory, decisions, and skills
                              ↑
                         Obsidian
                 owner-facing workspace over ordinary files

Conditional only after measured failure:
Basic Memory / Graphiti / Cognee / Mem0 / OpenHands
```

The governing rule is:

> **One authority per concern; every other component stores only an exact opaque reference.**

Soma remains an independent local service and MCP authority. It should not be rebased wholesale onto OpenClaw, OpenHands, Letta, Agent Fleet, or another host runtime.

## 5. Decisions currently favoured

### 5.1 Soma remains independent

OpenClaw is now the leading candidate for the Cortana-style shell: chat, voice, channels, sessions, convenience scheduling, browser interaction, coding-session UX, and owner-facing presentation. It should be piloted now as an external MCP client and shell around Soma, not adopted as Soma's durable authority or codebase foundation.

This avoids:

- rewriting the current Python system into a different host runtime;
- accepting another product's task, schedule, memory, and session stores as canonical;
- coupling Soma to an upstream release cadence and plugin API;
- weakening Windows-first process and repository guarantees;
- rebuilding Soma's differentiators inside a codebase we do not control.

### 5.2 ACP is the leading worker-integration candidate

The planned coding-agent adapter substantially overlaps with the Agent Client Protocol. ACP should be tested as the standard worker-session interface for Claude Code, Codex, Hermes, OpenHands, OpenCode, and compatible future agents.

The intended relationship is:

```text
Soma task
→ project-scoped isolated worktree
→ ACP session
→ specialist coding agent
→ streamed progress and steering
→ Soma cancellation, reconciliation, validation, evidence, and publication
```

Soma keeps canonical task identity, project scope, worktree assignment, evidence, and acceptance. The worker retains its provider-local session state behind an adapter mapping.

### 5.3 Memory begins with the smallest viable authority split

The preferred baseline is:

```text
Markdown + Git
→ canonical owner-readable memories, decisions, lessons, and skill documents

Soma SQLite
→ structured operational records, stable IDs, scope, provenance, validity,
  supersession, indexes, and retrieval metadata

Obsidian
→ optional human-facing reader/editor over ordinary files

Agent Fleet
→ bounded pilot and source of reflection, two-tier memory,
  contradiction consolidation, and skill-proposal mechanics
```

Graphiti, Cognee, Mem0, Basic Memory, or another memory service must not be added merely because it is impressive. A more complex memory provider wins only when a real benchmark shows that the Markdown plus SQLite baseline cannot answer important questions reliably.

### 5.4 Project isolation remains custom and moves forward

The reviews agree that fail-closed project scope is one of Soma's clearest differentiators. Existing personal-agent systems generally isolate agents, sessions, or workspaces, but do not enforce one project identity across storage, retrieval, processes, worktrees, ports, credentials, browser profiles, schedules, evidence, and derived knowledge.

ProjectScope therefore remains a Soma-owned correctness invariant rather than a feature delegated to another runtime.

### 5.5 Existing durable execution and repository truth remain valuable

The direct repository review identified the strongest implemented assets as:

- durable runs with persistence-before-launch;
- leases, compare-and-swap transitions, and reconciliation;
- exact process identity and owned-tree cancellation;
- managed repository mutation with hash verification and rollback evidence;
- worktree and Git truth;
- immutable repository-wiki generations;
- compact MCP projections and progressive disclosure;
- working provider foundations and domain integrations.

The re-evaluation is a reduction of speculative expansion, not a rejection of this working foundation.

### 5.6 Sixth-review live-repository findings accepted for action

The sixth evaluation identified immediate repository concerns that take precedence over adding new architecture:

1. **Evidence amplification in SQLite.** At review time, `runs/soma.sqlite3` was approximately 1.03 GB; about 954 MB was attributed to `runs.result_json`, and a small number of `repo_apply` results retained very large duplicated manifests. Full evidence must remain immutable, but SQLite should retain compact scalar results, hashes, and artifact references rather than duplicate large protected artifacts.
2. **Reconciliation failures can disappear.** Startup reconciliation exceptions were found to be caught without durable publication. Soma must surface these failures through durable events, health/status, and evidence rather than silently continuing.
3. **Repository-wiki exclusions and freshness need correction.** The wiki was stale during inspection, and generated/tool-owned paths including `.claude/worktrees/` and `.codex-tmp/` require explicit exclusion and reconciliation coverage.
4. **The canonical task plane remains intentionally thin.** It currently lacks `project_id`, has a narrow backend and command surface, and should receive the minimal project-identity seam before a universal work graph is attempted.
5. **Lifecycle authority is already duplicated.** Runs, workflows, supervisor variants, long-run jobs, and local-agent orchestration retain overlapping lifecycle logic. Consolidation must precede another lifecycle owner.

These values are a dated repository observation, not permanent constants. The architectural conclusion is permanent: large evidence bodies belong in immutable artifacts, while canonical stores retain compact queryable identity and references.

## 6. Areas intentionally not yet decided

The following remain pilot-gated rather than accepted architecture:

- whether ACP can recover an active coding-agent session after the Soma process is killed;
- whether CLI resume must supplement ACP session loading;
- how difficult it is to add immutable `project_id` across current stores and public projections;
- whether Markdown plus SQLite is sufficient for current-versus-superseded memory retrieval;
- whether Basic Memory, Graphiti, Cognee, or Mem0 provides measurable value beyond the baseline;
- whether Agent Fleet should remain only a disposable design study or become an owner-facing helper;
- whether OpenClaw passes the owner's Windows, restart, authority-separation, latency, and maintenance gates as the Cortana shell;
- how much runtime provenance is actually necessary beyond executable, model, repository, lockfile, configuration, timing, and result identity.

No major roadmap rewrite should convert these unknowns into commitments before the pilots.

## 7. Immediate implementation gate

The current roadmap is frozen as an implementation sequence. The accepted order begins with stabilising the live kernel, then tests the proposed shell and coding path together.

### STABILIZE-1 — current Soma evidence and recovery hygiene

This is the next implementation batch. It must remain bounded and preserve all historical evidence.

Required outcomes:

1. Replace duplicated large manifests in `runs.result_json` with compact scalar results plus immutable artifact references and hashes.
2. Provide a compatibility and migration path for existing large records; do not rewrite or discard opaque IDs or protected evidence.
3. Publish startup and periodic reconciliation failures durably through events, health/status, and retrievable evidence.
4. Add `.claude/worktrees/`, `.codex-tmp/`, and other confirmed tool-owned paths to repository-wiki exclusions.
5. Reconcile wiki freshness reliably after managed repository mutations and record failures rather than hiding them.
6. Produce a lifecycle-authority inventory identifying runs, workflows, supervisor variants, long-run jobs, and local-agent ownership before consolidation work begins.

### PILOT-OPENCLAW-ACP-1 — shell, MCP authority split, and coding session

**Budget:** three to five normal focused workdays. This is a total engineering budget, not continuous work.

**Goal:** prove the proposed architecture end to end without transferring canonical authority away from Soma.

Pilot path:

```text
OpenClaw shell
→ exact Soma MCP operation
→ stable canonical Soma task ID
→ Codex app-server or ACP coding session
→ managed worktree
→ Soma monitoring, cancellation, evidence, and result projection
```

Required tests:

1. Install a pinned OpenClaw build on the owner's Windows environment with one owner-only surface.
2. Connect outbound to Soma through MCP without changing existing canonical schemas.
3. Read, create, monitor, cancel, and retrieve one Soma durable task.
4. Start one Codex app-server or ACP coding session bound to the exact Soma task ID.
5. Use one managed worktree and preserve dirty/unpushed state honestly.
6. Restart OpenClaw during a main turn, cron/convenience task, coding session, and raw background process.
7. Restart Soma independently and verify canonical state remains consistent.
8. Duplicate a submission and verify no duplicate irreversible action occurs.
9. Drop the connection and delay final delivery; lost shell work must be reported honestly.
10. Measure incremental OpenClaw-to-Soma overhead, task submission, runtime spawn, recovery, idle burden, and daily operator maintenance.

Pass only when Soma remains authoritative, exact IDs survive, no irreversible action duplicates, removal of OpenClaw leaves Soma data intact, and the measured overhead and maintenance are acceptable.

### PILOT-SCOPE-1 — ProjectScope retrofit spike

**Budget:** two to three focused workdays after the combined shell pilot.

**Goal:** determine whether `project_id` and opaque external-session bindings can be introduced through the current canonical stores without breaking existing ChatGPT connector contracts.

Initial scope:

- projects;
- tasks;
- runs and attempts;
- memory records;
- repositories and worktrees;
- external OpenClaw, Codex, ACP, Hermes, or OpenHands bindings;
- evidence and artifacts.

The confusion test uses two projects with deliberately similar filenames, technology stacks, service names, and task descriptions. Retrieval, locks, processes, repositories, memory, and evidence must remain isolated. Unscoped project operations must fail closed.

### PILOT-MEMORY-1 — Obsidian and canonical Markdown baseline

**Budget:** one focused build day plus two normal usage days.

**Baseline:** canonical Markdown + Git, Soma IDs/revision metadata, and Obsidian as the owner-facing application.

Use 50–100 representative records and a fixed question set covering exact recall, current versus superseded facts, source resolution, project isolation, external file edits, deletion, and complete index rebuild.

Start with the lightest available index. Compare Basic Memory only when the baseline misses a named project, source, relation, or independent-access requirement. Use Agent Fleet only in a disposable vault to extract UX mechanics such as reflection, proposal queues, bounded working memory, and Wiki Keeper behaviour.

A graph-memory candidate is not installed unless the baseline fails a fixed temporal or relationship benchmark. Graphiti, Cognee, Mem0, and Letta must not become parallel authorities.

## 8. Conditional later comparisons

### PILOT-OPENHANDS-1

Run only when OpenClaw's Codex/ACP path leaves a measured coding-control gap. OpenHands advances only when it materially improves completion time, cancellation/resumption, or workspace control after accounting for Docker and Windows operational burden.

### PILOT-GRAPH-MEMORY-1

Run only after the Markdown baseline fails. Promote a graph provider only when it produces a clear correctness gain, preserves source resolution and current-fact precision, rebuilds from canonical files, and introduces zero project leakage.

## 9. Stop conditions

A pilot is not allowed to quietly become production architecture.

Stop and review when:

- its time budget is exhausted;
- implementation starts changing unrelated public contracts;
- it requires deletion of a working fallback before proving replacement;
- a candidate introduces a second canonical authority;
- a tool cannot be removed without losing important records;
- Windows operation or restart recovery fails repeatedly;
- project scope cannot be enforced;
- the measured benefit does not justify its services, latency, or maintenance burden.

Failure is useful evidence. The result should identify the exact missing capability and the minimum custom component required, rather than restarting a broad design effort.

## 10. Working classification

The current classification is:

> **Reduce Soma to an independent, durable, project-aware control plane; adopt standard worker and tool interfaces; preserve repository truth and recovery; build new subsystems only after bounded pilots demonstrate an unmet requirement.**

This finding does not yet rewrite or delete the detailed roadmap. It establishes the gate and evidence process by which the roadmap will be reduced once the pilots answer the major uncertainties.

## 11. Next action

The next concrete engineering activity is:

> **STABILIZE-1: compact duplicated run-result evidence into immutable artifact references, durably surface reconciliation failures, correct repository-wiki exclusions and freshness handling, and inventory existing lifecycle authorities.**

After STABILIZE-1 is accepted, run **PILOT-OPENCLAW-ACP-1** as the first end-to-end architecture test. Preserve the production worker paths and existing public gateways until the replacement evidence is accepted.
