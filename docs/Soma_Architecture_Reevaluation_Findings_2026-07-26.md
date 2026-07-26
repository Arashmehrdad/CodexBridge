# Soma Architecture Re-evaluation Findings

**Date:** 2026-07-26  
**Status:** Decision record and implementation gate  
**Scope:** Five architecture evaluations by ChatGPT, Grok, Opus/Claude Code, GLM-5.2, and Kimi-K3, followed by owner-guided synthesis

## 1. Why this document exists

The revised Soma roadmap grew into a broad custom agent runtime covering projects, tasks, durable execution, agent sessions, memory, skills, knowledge systems, scheduling, model routing, browser and desktop automation, credentials, backup, provenance, and future Cortana presentation.

Before continuing that implementation sequence, the architecture was evaluated from five model perspectives: ChatGPT, Grok, Opus/Claude Code, GLM-5.2, and Kimi-K3. ChatGPT's evaluation was one of the five and was later also used to reconcile the findings with the owner's intent. The purpose was not to prove Soma was a mistake. It was to identify the smallest, strongest, most maintainable system that preserves the original vision without rebuilding mature tools unnecessarily.

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

## 2.1 Five evaluation perspectives

The review set was:

1. **ChatGPT** — independent architecture and ecosystem evaluation using the roadmap, prior Soma decisions, live bounded repository inspection through Soma, and external research. It recommended freezing the roadmap as an implementation sequence, preserving Soma as an independent durable control plane, testing ACP before building a custom worker layer, moving ProjectScope forward, beginning memory with Markdown plus SQLite, and treating OpenClaw as an optional later front door rather than an immediate foundation.
2. **Grok** — broad strategic comparison that strongly favoured reducing Soma and adopting an existing personal-agent gateway, especially OpenClaw.
3. **Opus/Claude Code** — direct repository-wide evaluation from inside the live codebase. It identified what is actually implemented, what remains speculative, where lifecycle systems overlap, and ACP as the largest missing standards opportunity.
4. **GLM-5.2** — ecosystem and target-architecture evaluation favouring a thin Soma sidecar with OpenClaw, Basic Memory, Graphiti, coding agents, and Stagehand.
5. **Kimi-K3** — broad specialist-tool evaluation covering Cognee, Mem0/OpenMemory, Basic Memory, Agent Fleet, OpenHands Agent Canvas, OpenClaw, LiteLLM, and other adoption candidates.

Opus/Claude Code had the deepest direct repository access and therefore receives the highest weight for claims about current Soma code, implemented capabilities, missing modules, duplication, and migration difficulty.

ChatGPT, Grok, GLM-5.2, and Kimi-K3 provide complementary architecture and ecosystem analysis. ChatGPT's role is explicitly dual: it supplied one of the five evaluations and subsequently helped the owner compare, challenge, and synthesize all five. External-tool claims remain subject to official-source verification and hands-on pilots; no model's architectural preference overrides repository evidence or the owner's accepted intent.

## 3. Strong consensus across the reviews

All five evaluations converged on the same high-level conclusion:

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
ChatGPT
executive controller / chief of staff
        │
        │ MCP
        ▼
Soma
independent durable project-aware control plane
├── projects and ProjectScope
├── work graph
├── canonical tasks and attempts
├── durable execution and reconciliation
├── repository and worktree truth
├── evidence and artifacts
├── schedules and event digest
├── controller checkpoints and handoffs
└── existing domain providers
        │
        ├── ACP → Claude Code / Codex / Hermes / compatible agents
        ├── MCP → Playwright and specialist tools
        ├── CLI → 1Password and Kopia
        └── Markdown + Git → readable memory, decisions, and skills
                              ↑
                         Obsidian
                 optional owner-facing workspace
                 and bounded Agent Fleet pilot

Optional later:
OpenClaw → Cortana, voice, mobile, messaging, and channel front door
Graphiti/Cognee/Mem0 → only after a memory benchmark proves added value
```

Soma remains an independent local service and MCP authority. It should not be rebased wholesale onto OpenClaw, OpenHands, Letta, Agent Fleet, or another host runtime.

## 5. Decisions currently favoured

### 5.1 Soma remains independent

OpenClaw is the strongest candidate for a future Cortana-style front door, channels, voice, phone, messaging, and owner-facing interaction. It should initially be treated as an external MCP client of Soma rather than Soma's foundation.

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

## 6. Areas intentionally not yet decided

The following remain pilot-gated rather than accepted architecture:

- whether ACP can recover an active coding-agent session after the Soma process is killed;
- whether CLI resume must supplement ACP session loading;
- how difficult it is to add immutable `project_id` across current stores and public projections;
- whether Markdown plus SQLite is sufficient for current-versus-superseded memory retrieval;
- whether Basic Memory, Graphiti, Cognee, or Mem0 provides measurable value beyond the baseline;
- whether Agent Fleet should remain only a disposable design study or become an owner-facing helper;
- whether OpenClaw is stable and useful enough on the owner's Windows environment to become the future Cortana front door;
- how much runtime provenance is actually necessary beyond executable, model, repository, lockfile, configuration, timing, and result identity.

No major roadmap rewrite should convert these unknowns into commitments before the pilots.

## 7. Immediate implementation gate

The current roadmap is frozen as an implementation sequence until three evidence-producing pilots finish.

### PILOT-ACP-1 — coding-agent supervision

**Budget:** up to three normal focused workdays, approximately 18–24 engineering hours in total. This is not continuous work and may be distributed across calendar days.

**Goal:** prove that Soma can control Claude Code and Codex through one worker-session contract while retaining canonical task identity and durable guarantees.

Required tests:

1. Create a Soma task and isolated worktree.
2. Start Claude Code through ACP.
3. Start Codex through ACP using the same Soma-facing contract.
4. Stream progress and tool activity without blocking Soma.
5. Supply a follow-up instruction to an active session.
6. Cancel during active work and verify no orphaned owned process tree remains.
7. Run two sessions concurrently in separate worktrees without interference.
8. Kill and restart Soma during a session.
9. Resume through ACP session loading or a documented CLI fallback.
10. Capture final diff, base revision, worker identity, session mapping, outcome, and evidence.

The pilot must remain isolated. Existing production gateways and worker paths are preserved until the result is accepted.

### PILOT-SCOPE-1 — ProjectScope retrofit spike

**Budget:** two to three focused workdays.

**Goal:** determine whether `project_id` can be introduced through the current canonical stores without breaking existing ChatGPT connector contracts.

Initial scope:

- projects;
- tasks;
- runs and attempts;
- memory records;
- repositories and worktrees;
- agent sessions;
- evidence and artifacts.

The confusion test uses two projects with deliberately similar filenames, technology stacks, service names, and task descriptions. Retrieval, locks, processes, repositories, memory, and evidence must remain isolated. Unscoped project operations must fail closed.

### PILOT-MEMORY-1 — canonical memory bake-off

**Budget:** two focused workdays after the first two pilots.

**Baseline:** Markdown + Git + Soma SQLite metadata/index, viewed through Obsidian.

**Candidates:** Basic Memory, a disposable Agent Fleet vault, and only one graph-oriented candidate selected from Graphiti, Cognee, or Mem0.

Use real Soma material containing accepted decisions, corrected decisions, superseded facts, preferences, project facts, task outcomes, and lessons.

Required questions:

```text
What is currently true?
What used to be true?
What replaced it?
Why did it change?
Which project owns it?
What is its source?
What should be included in a bounded ChatGPT context packet?
```

A more complex provider is promoted only when it produces a meaningful correctness or maintenance advantage over the baseline.

## 8. Deferred fourth pilot

### PILOT-CORTANA-1 — OpenClaw as an external front door

This occurs only after ACP, ProjectScope, and memory authority are clearer.

OpenClaw should initially operate as an external, disposable MCP client providing voice, messaging, mobile, or other Cortana-style surfaces. It must not own canonical Soma projects, tasks, schedules, repository mutations, or accepted memory.

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

> **PILOT-ACP-1: demonstrate Claude Code and Codex worker supervision through ACP while Soma retains task identity, worktree isolation, cancellation, restart recovery, and evidence.**

Before implementation begins, create a small pilot branch and an evidence checklist. Do not modify the production worker path or remove existing adapters during the experiment.
