# Soma — ChatGPT Agentic Runtime Audit and Strategic Roadmap

## Status of this document

This document is a **strategic architecture and implementation roadmap**, not a claim that the described end state already exists.

It refines the prior Codex-generated audit by:

- preserving the correct “ChatGPT as the reasoning interface, Soma as the agent runtime” architecture;
- separating unrestricted execution from network exposure;
- making the private tunnel or loopback boundary explicit;
- keeping Windows as the first implementation target while preserving a portable core;
- removing coding-agent execution entirely: Soma generates provider-neutral external-coder handoffs for manual use instead of invoking any coding agent;
- removing unused or duplicate systems only after their useful behavior has migrated;
- requiring focused tests and acceptance evidence for implementation even though the original audit could not run them;
- retaining CF1 as the sole active engineering lane until its exit gate passes.

All repository-specific claims, counts, live-service observations, and implementation details must be refreshed against the current branch, HEAD, active durable runs, worktree, service build, and connector schema before this roadmap is merged into the canonical repository plan.

---

## 1. Product definition

Soma is not merely a remote command runner and not a clone of the Codex or Hermes user interfaces.

The intended product is:

> **A headless, owner-trusted, model-independent agent runtime and control plane whose primary reasoning client and user interface is ChatGPT.**

ChatGPT remains responsible for:

- conversation;
- general reasoning;
- planning;
- judgment;
- supervision;
- deciding when more evidence is needed;
- deciding when work should continue, pause, retry, branch, or stop;
- synthesizing results from tools and delegated workers.

Soma provides the infrastructure beneath ChatGPT:

- unrestricted host execution;
- full computer and filesystem control;
- native capabilities;
- Hermes and external MCP capabilities;
- skills and context retrieval;
- durable long-running tasks;
- workflows and schedules;
- child-task delegation and parallel execution;
- restart recovery;
- exact cancellation;
- memory and evidence;
- browser and desktop control;
- observability and compact result delivery.

Phone, browser, desktop, and future ChatGPT clients are interchangeable access surfaces. Remote continuity is important, but it is one capability among many and not the organizing architecture.

### Target relationship

```text
ChatGPT
  reasoning + planning + supervision + user interaction
        |
        v
Compact Soma control protocol
        |
        v
Soma agent runtime
  tasks + capabilities + skills + memory + workflows
  delegation + scheduling + computer control + evidence
        |
        v
Local and remote execution environments
```

Soma must not introduce a competing general-purpose reasoning model or a second primary user interface.

---

## 2. Trust and security model

### 2.1 Owner-trusted execution

Soma is intentionally unrestricted after a trusted connection reaches it.

It should not contain:

- per-command approval prompts;
- artificial autonomy tiers;
- executable allowlists;
- sandbox requirements;
- separate approval records for ordinary execution;
- confirmation phrases used as pseudo-permission barriers;
- automatic denials based on program name or command category.

Correctness controls remain mandatory:

- content hashes;
- idempotency;
- resource leases;
- stale-version detection;
- exact process identity;
- cancellation scoping;
- mutation reconciliation;
- repository/worktree isolation;
- artifact provenance;
- deterministic rollback or uncertainty reporting.

These are correctness and durability mechanisms, not user-permission gates.

### 2.2 Network trust boundary

Unrestricted execution does **not** mean unrestricted network exposure.

The deployment invariant is:

> Soma is reachable only through loopback, an authenticated private tunnel, or an equivalent owner-controlled network boundary.

Soma may remain application-layer unauthenticated inside that trusted boundary, but documentation and deployment checks must clearly state:

- never expose the MCP/control endpoint directly to the public internet;
- bind to loopback by default;
- remote access must pass through the owner’s private tunnel or equivalent protected channel;
- connector identity and transport metadata are correlation data, not an internal permission system.

The private tunnel is the security perimeter. Soma is the unrestricted owner-controlled execution service behind it.

---

## 3. Governing architectural principles

1. **ChatGPT is the sole general reasoning and supervision layer.**
2. **Soma is headless infrastructure, not a second assistant application.**
3. **The durable execution kernel is an asset to evolve, not replace.**
4. **Every public response is compact by default and exact evidence remains retrievable.**
5. **Every side effect has durable identity, evidence, cancellation semantics, and reconciliation behavior.**
6. **No general capability requires a configured Git repository.**
7. **Native tools, Hermes, MCP servers, and future runtimes appear through one capability model.**
8. **No coding agent is ever executed by Soma: coding work leaves through a provider-neutral external-coder handoff that the owner supplies manually to Claude Code, Codex, Gemini CLI, or another tool.**
9. **Legacy systems are removed only after their useful semantics have migrated and passed acceptance.**
10. **Windows is the first production target; the core is designed for later Linux and macOS adapters.**
11. **No implementation phase is complete without focused tests and observable acceptance evidence.**
12. **The roadmap is migrated incrementally; no all-at-once rewrite of durable state.**

---

## 4. Audit verdict

Soma has already outgrown its original “bridge” framing. Its strongest foundation is durable execution:

- persist-before-launch semantics;
- launcher, worker, and child process identity;
- leases and heartbeats;
- exact cancellation work;
- restart reconciliation;
- repository locks;
- durable outputs and artifacts;
- terminal result publication;
- repository inspection and managed mutation;
- workflow, supervisor, SSH, Docker, Cloudflare, trading, and Hermes foundations.

The primary architectural problem is not lack of raw capability. It is fragmentation:

- multiple lifecycle authorities;
- multiple overlapping supervisor/coding/job paths;
- inconsistent public response sizes;
- no canonical parent/child task model;
- no unified capability broker;
- no native skill plane;
- memory that is not yet a deterministic task-context system;
- Hermes H2 foundations that are not yet the production capability service;
- no general browser/desktop provider contract;
- no durable scheduler;
- Windows-specific assumptions embedded through the execution layer;
- unused or duplicate historical systems that increase maintenance and connector weight.

The correct strategy is:

> Consolidate around the accepted durable kernel, build a canonical task and capability plane, progressively migrate existing domains into it, then remove obsolete paths.

---

## 5. Current systems to preserve, migrate, or retire

### Preserve and strengthen

- root durable run store and worker lease model;
- exact process identity and cancellation;
- repository locks and mutation evidence;
- terminal publication and protected artifacts;
- workflows where they provide deterministic task graphs;
- SSH transport and remote durability features that local process execution cannot replace;
- repository, Docker, Cloudflare, knowledge, trading, and other domain capabilities as provider implementations;
- Hermes H1 as a bounded compatibility/fallback path;
- Hermes H2 process and identity foundations;
- provider-neutral external-coder handoff generation (manual use only);
- repository wiki and SQLite memory as storage foundations.

### Migrate before removal

- legacy job lifecycle behavior;
- supervisor recovery and continuation behavior;
- local-coding state;
- synchronous coding-agent result paths;
- approval-oriented `needs_input` or `needs_approval` transitions;
- dashboard/TUI operational information that is still useful;
- keyword local-agent behavior that contains reusable routing or context logic.

### Retire after successful migration

- unused Ollama/local general-reasoning path;
- automatic or implicit coding-agent routing (removed);
- synchronous coding-agent bypass paths (removed);
- duplicate supervisor stacks;
- duplicate local-coding state;
- legacy job manager;
- dashboard and service TUI;
- obsolete approval, policy-tier, autonomy-profile, and confirmation artifacts;
- server monkey patches and duplicate schema/catalog registration paths.

Removal must reduce weight without discarding recovery, continuation, cancellation, evidence, or operator-diagnostic behavior.

---

## 6. Target public architecture

### 6.1 Compact control surface

The long-term public surface should converge toward a small number of stable gateways.

#### Task query

```text
status
list
wait
events
children
result
deliveries
```

#### Task action

```text
start
steer
submit_input
pause
resume
cancel
retry
```

#### Capability query

```text
search
describe
catalog_delta
provider_health
resource
prompt
```

#### Capability action

```text
invoke
reload_provider
```

#### Context query

```text
skill_search
skill_describe
skill_resource
memory_search
context_packet
```

#### Context action

```text
remember
archive
import
refresh_repository_knowledge
```

#### Schedule query/action

```text
list
status
history
create
update
pause
resume
trigger
remove
```

#### Evidence query

```text
index
metadata
tail
range
search
content
```

Existing domain gateways remain compatibility adapters while their implementations become capability providers.

### 6.2 Core types

#### Task

A canonical task contains:

- `task_id`;
- optional parent task;
- client request ID and normalized request hash;
- objective reference;
- task kind;
- executor/provider identity;
- workspace/resource leases;
- state and phase;
- decision `state_version`;
- child task references;
- result reference;
- evidence references;
- timestamps;
- recovery and reconciliation state.

Suggested states:

```text
accepted
queued
running
awaiting_chatgpt
paused
cancellation_pending
recovery_pending
completed
failed
cancelled
uncertain
```

There is no approval state.

#### Task checkpoint

A checkpoint contains:

- question or judgment requirement;
- expected input schema;
- context/evidence references;
- the task state version against which ChatGPT must respond.

#### Capability identity

A capability identity contains:

- capability ID;
- provider ID and provider kind;
- provider revision;
- catalog generation;
- schema hash;
- platform requirements;
- availability;
- informational side-effect metadata;
- cancellation and reconciliation support.

Side-effect metadata informs ChatGPT. It never acts as an internal permission gate.

#### Context packet

A context packet contains:

- objective;
- constraints;
- selected skills;
- relevant memories and decisions;
- workspace snapshot;
- child summaries;
- exact evidence references;
- deterministic byte budget.

#### Resource lease

Resource leases cover:

- repositories;
- files;
- worktrees;
- services;
- ports;
- browser profiles;
- displays;
- devices;
- external mutation targets.

---

## 7. Corrected implementation roadmap

## Priority 0 — Complete CF1

CF1 remains the sole active engineering lane until its exit gate passes.

### Objectives

- scalar SQL-backed summaries;
- compact status/control projections;
- state-version polling;
- stable cursors;
- bounded terminal projections;
- exact evidence retrieval;
- repository progressive disclosure;
- connector-visible footprint reduction;
- compact conformance across every public gateway.

### Required invariants

- full authoritative records remain unchanged;
- current durable worker, lock, cancellation, recovery, and publication semantics remain unchanged;
- existing frozen full-response cursor reconstruction remains available explicitly;
- errors, partial outcomes, ambiguous mutations, cleanup failures, and reconciliation requirements remain visible;
- no request body, environment, stdin, script, raw argv, credential, or local path appears in an ordinary compact response;
- every omitted detail has an exact evidence path.

### Exit gate

- at least 90% representative connector-visible session reduction;
- 20-run compact summary at or below the accepted size target;
- unchanged polling below 1 KB;
- every public operation has a bounded default;
- exact authoritative reconstruction and hash equality;
- no worker-path performance or durability regression.

No post-CF1 implementation phase becomes active until CF1 is accepted and the canonical roadmap explicitly selects the next lane.

---

## Phase 1 — Canonical task plane before destructive cleanup

Build the replacement control model before deleting old lifecycle systems.

### Deliverables

- canonical `tasks`, `task_links`, `task_commands`, `task_checkpoints`, and task events;
- link tasks initially to existing run, workflow, supervisor, Hermes, SSH, and command-group identities;
- top-level idempotency using client request ID plus normalized request hash;
- one public task identity independent of executor;
- state-version-guarded steer, input, pause, resume, retry, and cancel commands;
- `awaiting_chatgpt` as the universal judgment/input transition;
- separate storage of ChatGPT’s decision and the resolved executable input;
- compact parent/child task queries;
- compatibility adapters for existing run/workflow/supervisor operations.

### Migration rule

Do not rewrite all historical durable state at once. New tasks use the canonical plane; old rows remain readable through adapters and migrate only when necessary.

### Exit gate

ChatGPT can supervise every existing execution type through one compact task protocol without losing existing recovery or evidence behavior.

---

## Phase 2 — Kernel consolidation and permission-system removal

Once the canonical task plane can replace useful behavior, consolidate lifecycle authority.

### Deliverables

- one process-owned application container for stores, managers, providers, platform adapters, and routers;
- one schema-version table with ordered transactional migrations;
- workers refuse incompatible schema versions;
- one authoritative path for launch, worker lease, state transition, cancellation, result publication, and recovery;
- startup reconciliation failures become durable evidence and unhealthy readiness;
- all progress updates use lease-generation compare-and-set;
- crash-safe journaling for multi-file rollback/revert;
- migration of useful supervisor and legacy-job behavior into tasks/workflows;
- removal of approval tiers, autonomy profiles, confirmation phrases, and runtime `allow_*` gates after compatibility migration;
- legacy approval rows become historical or conservative `awaiting_chatgpt` checkpoints; they are never auto-executed;
- old `allowed_files` becomes optional scope/evidence metadata, not authorization.

### External-coder policy

Soma does not execute any coding agent. When coding work is required, Soma
generates a bounded, provider-neutral external-coder handoff (objective,
repository state, evidence, approved scope, constraints, validation
commands, expected completion report) and parks the work in
`needs_external_coder`. The owner supplies the handoff manually to Claude
Code, Codex, Gemini CLI, or another coding agent, then returns the results
to Soma for validation and evidence capture. Historical
`codex_plan_task` / `codex_implement_task` records remain readable as
legacy read-only run types.

### Exit gate

One kernel owns every active lifecycle decision, and the obsolete permission system is removed without losing correctness or migration safety.

---

## Phase 3 — Windows-first unrestricted host execution

### Architecture

Introduce portable interfaces for:

- process spawning;
- process/start identity;
- process-tree termination;
- shell/interpreter discovery;
- path semantics;
- filesystem operations;
- environment handling;
- background execution;
- service lifecycle.

### Windows implementation first

Complete and accept:

- direct executable plus argv execution;
- PowerShell, pwsh, and cmd interpreter adapters;
- unrestricted whole-machine filesystem read/write/append/patch/copy/move/delete/search;
- arbitrary absolute working directories;
- durable background execution;
- Windows Job Objects or equivalent owned-tree cancellation;
- process creation-time and identity evidence;
- Windows Service installation and lifecycle;
- resource leases for files, services, ports, repositories, and other mutation targets.

General command and filesystem work must not require a configured repository.

### Portability rule

Interfaces must not hard-code Windows assumptions into task, capability, evidence, or scheduler schemas. Linux and macOS adapters come later and must not block the usable Windows runtime.

### Exit gate

The Windows implementation provides truthful unrestricted host execution, exact cancellation, restart reconciliation, and evidence through the canonical task plane.

---

## Phase 4 — Unified capability broker and Hermes H2

### Deliverables

Implement a provider contract with:

```text
snapshot
search
describe
invoke
cancel
health
reload
resource
prompt
```

Providers include:

- native Soma capabilities;
- persistent Hermes H2;
- Hermes H1 fallback;
- external MCP tools/resources/prompts;
- external-coder handoff generation (manual use only);
- future browser, desktop, and media providers.

### Hermes H2 completion

- service supervision;
- worker replacement;
- restart adoption;
- health and readiness;
- atomic catalog-generation reload;
- concurrent session isolation;
- public routing;
- provider-level cancellation;
- persisted provider identity, catalog generation, schema hash, accepted argument hash, and result identity;
- large-result spill to artifacts;
- stale-schema rejection;
- last-known-healthy catalog retention.

Hermes is the primary aggregator for Hermes built-ins, plugins, and connected MCP servers. Hermes is not the controlling general agent.

### Exit gate

ChatGPT can search, describe, and durably invoke native, Hermes, plugin, and MCP capabilities without loading the entire catalog.

---

## Phase 5 — Skills, memory, and deterministic context

### Skills

Support `SKILL.md`-style packages from:

- project roots;
- user roots;
- bundled Soma skills;
- Hermes skill roots.

Index only metadata first:

- name;
- description;
- version;
- source;
- digest;
- platform requirements;
- resources;
- required capabilities.

Progressive loading order:

1. metadata search;
2. full skill instructions;
3. individual resources.

Skills provide instructions and resources to ChatGPT. Skill prose is never executed directly.

### Memory

Extend the existing SQLite memory and repository wiki rather than creating another disconnected store.

Add:

- task summaries;
- decisions;
- reusable recipes;
- artifact lineage;
- child summaries;
- repository/workspace snapshots;
- supersession;
- expiry;
- confidence;
- source references.

Automatically store structured terminal facts and artifact metadata. ChatGPT remains responsible for semantic decisions and conclusions.

### Future repository structural intelligence

Extend the existing repository wiki rather than adopting Graphify or another product as a second knowledge system. Evaluate and selectively port useful open-source features behind Soma's repository-isolation and evidence contracts:

- Tree-sitter AST indexing for definitions, imports, calls, inheritance, and cross-file relationships;
- provenance on every relationship: `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`;
- graph reads such as neighbour, path, and explain queries alongside ordinary lexical search;
- automatic subsystem/community detection to seed hierarchical architecture summaries;
- first-class rationale nodes for `WHY`, `NOTE`, `HACK`, ADR, and RFC references;
- incremental refresh that reparses changed files, removes stale graph facts, and reconnects affected relationships.

Keep Soma authoritative for repository scoping, decisions, roadmap history, evidence, architecture summaries, memory, and compact context-packet generation. Do not copy Graphify's viewer, assistant hooks, complete CLI, document/media ingestion, or dependency graph unless a later measured need justifies them.

Begin with a read-only pilot against Soma and SeedMind and compare the enhanced wiki with the current implementation on a fixed set of real repository questions. Promote features only when they improve answer correctness, provenance, refresh cost, or context compactness without creating a competing source of truth.

Before copying upstream code, re-check its current licence, preserve required copyright and notice text, mark adaptations, and record imported files and source revisions in `THIRD_PARTY_NOTICES.md`. Similar independently implemented architectural ideas do not require code attribution.

### Context packets

Build deterministic context packets under CF1 budgets using:

- objective and constraints;
- selected skills;
- relevant decisions and memories;
- current workspace identity;
- child summaries;
- exact evidence references.

Do not persist complete ChatGPT conversation history as a substitute for task context.

### Exit gate

ChatGPT can resume complex work from a compact, source-linked context packet and progressively retrieve skills or evidence.

---

## Phase 6 — Delegation, parallel workers, workflows, and worktrees

### Child tasks

ChatGPT may explicitly create child tasks with:

- objective;
- context packet;
- selected skills;
- workspace;
- executor/provider;
- expected output schema;
- resource limits.

Soma schedules, observes, recovers, and reports children. It does not invent their objectives.

### Worker adapters

- native command execution;
- capability invocation;
- external-coder handoff generation;
- deterministic workflows;
- configured external agent runtimes.

### Parallel execution

Generalize parallel PowerShell groups into platform-neutral parent/child execution with:

- configurable capacity;
- fair queuing;
- independent leases;
- independent evidence;
- independent cancellation;
- restart adoption.

Capacity is resource management, not authorization.

### Worktrees

- reserve;
- create;
- bind to child task;
- record base commit;
- preserve on failure;
- inspect diff;
- integrate only when ChatGPT explicitly requests;
- clean up after acknowledgement.

### Workflows

Extend to:

- typed DAG steps;
- parallel ready nodes;
- retries;
- timeouts;
- compensation;
- explicit uncertainty;
- `awaiting_chatgpt`;
- submit input;
- continue;
- revise;
- retry step.

Retire duplicate supervisor systems only after their useful behavior exists through tasks and workflows.

### Exit gate

ChatGPT can delegate isolated work, run children in parallel, steer them, recover them after restart, and receive bounded summaries with exact evidence on demand.

---

## Phase 7 — Browser, desktop, and multimodal capability providers

Browser and desktop control are capability providers, not another user interface.

### Browser provider

Required contract:

- create/recover session;
- list pages;
- navigate;
- inspect DOM/accessibility state;
- interact;
- bounded script execution;
- screenshot;
- download/upload;
- wait;
- close;
- cancel owned activity.

Prefer a Hermes-backed provider if it satisfies identity, durability, cancellation, artifact, and recovery requirements. Otherwise use a direct Playwright/CDP provider.

### Desktop provider

Platform-specific adapters provide:

- displays and windows;
- screenshot;
- accessibility snapshot;
- pointer;
- keyboard;
- focus;
- wait;
- cancellation;
- close/recover session.

Windows implementation comes first. macOS and Linux adapters arrive in the later portability phase.

### Artifacts

Generalize evidence descriptors for:

- images;
- PDFs;
- audio;
- video;
- archives;
- downloads;
- arbitrary binary files.

Return compact descriptors by default and content only on explicit request.

PulseSender-specific browser assumptions should eventually be replaced by the general browser provider. Return delivery remains a separate concern.

### Exit gate

ChatGPT can inspect and operate browser and Windows desktop applications with durable session ownership, exact cancellation, and compact artifact retrieval.

---

## Phase 8 — Durable scheduling, continuity, and return delivery

### Scheduler

Support:

- one-shot schedules;
- recurring schedules;
- timezone;
- pause/resume;
- update/remove;
- trigger-now;
- history;
- deterministic missed-run policy;
- atomic attempt claiming;
- restart deduplication.

Schedules launch deterministic task or workflow templates. They do not start a hidden general reasoning loop.

When new judgment is required, the task transitions to `awaiting_chatgpt`.

### Delivery outbox

Persist terminal and waiting-input notifications separately from task outcome.

Polling and task discovery remain authoritative because an MCP server cannot always initiate a new ChatGPT turn.

Optional delivery adapters may include:

- PulseSender/browser delivery;
- file;
- webhook;
- future platform-supported notification channels.

Delivery failure never changes task outcome.

Compact return messages contain only:

- task ID;
- state;
- state version;
- instruction to query the task.

### Exit gate

Deterministic work continues unattended, survives restart, requests ChatGPT judgment when necessary, and remains discoverable even if notification delivery fails.

---

## Phase 9 — Linux and macOS execution adapters

This is a planned portability phase, not an early Windows release blocker.

### Linux

- direct execution;
- process identity and process-group cancellation;
- unrestricted filesystem;
- systemd;
- browser provider;
- accessibility/input provider where supported;
- restart reconciliation and acceptance.

### macOS

- direct execution;
- process identity;
- process-group cancellation;
- unrestricted filesystem;
- launchd;
- Accessibility/CGEvent desktop adapter;
- browser provider;
- restart reconciliation and acceptance.

### Cross-platform acceptance

Each platform must truthfully support the same advertised core contracts. Platform-specific optional capabilities remain explicitly marked rather than simulated.

### Exit gate

Windows, Linux, and macOS expose the same canonical task, capability, evidence, scheduler, and unrestricted host-execution contracts for supported features.

---

## Phase 10 — Observability, packaging, and legacy removal

### Observability

Expose compact structured:

- liveness;
- readiness;
- provider health;
- task health;
- resource leases;
- reconciliation state;
- storage usage;
- diagnostic bundles;
- trace/request IDs.

Do not build another dashboard.

### Distribution

Add reproducible:

- Python/runtime version pinning;
- dependency lockfiles;
- `serve`;
- `install-service`;
- `status`;
- `doctor`;
- `migrate`;
- `backup`;
- `restore`;
- `upgrade`.

Support SQLite-consistent backup, migration, retention, and artifact cleanup.

### Final cleanup

After migration and acceptance, remove:

- legacy job manager;
- duplicate supervisors;
- unused Ollama/local reasoning;
- automatic coding-agent routing (removed);
- synchronous coding-agent bypasses (removed);
- duplicate local-coding state;
- dashboard and service TUI;
- obsolete approval and autonomy artifacts;
- server monkey patches;
- duplicate schema/catalog paths.

Domain-specific systems such as Trading Lab remain optional providers rather than core-lifecycle owners.

### Exit gate

A fresh installation exposes a reproducible, compact, headless agent runtime without duplicate reasoning systems, lifecycle stores, or abandoned interfaces.

---

## 8. Testing and acceptance policy

The original audit did not run tests because its sandbox could not access the required real execution environment and Soma was concurrently occupied.

That limitation applies only to the audit.

Every implementation batch must include:

1. focused unit/regression tests;
2. adjacent integration tests;
3. durable live validation where the feature requires process, restart, cancellation, browser, desktop, scheduler, or provider evidence;
4. `git diff --check`;
5. local selected-file commit;
6. no push unless explicitly requested.

Milestone evidence must cover:

- idempotent duplicate starts;
- restart during launch;
- restart during execution;
- cancellation and cancellation uncertainty;
- workflow continuation;
- provider reload;
- Hermes concurrency;
- artifact reconstruction;
- worktree isolation;
- scheduled deduplication;
- delivery failure independence;
- connector-visible compactness;
- authoritative hash equality.

No phase may claim completion from documentation, commit titles, or mocked results alone.

---

## 9. Adoption and reconciliation procedure

Before this roadmap is merged into repository documentation:

1. inspect current branch and full HEAD;
2. inspect tracked and untracked worktree state;
3. inspect active durable runs, workflows, supervisors, and repository locks;
4. inspect the current running service build hash and capability schema;
5. revalidate every repository-specific audit finding against current source;
6. classify findings as confirmed, superseded, or already implemented;
7. preserve current CF1 work and completed evidence;
8. add this document as the strategic post-CF1 roadmap;
9. update `PLANS.md` with only:
   - the product contract;
   - trust-boundary invariant;
   - link to this document;
   - CF1 as sole active lane;
   - ranked post-CF1 phase order;
10. do not activate Phase 1 until CF1 passes its exit gate.

---

## 10. Non-goals

Soma will not become:

- a separate ChatGPT clone;
- a second general-purpose reasoning model;
- a mandatory desktop companion;
- a dashboard-first product;
- a fork of Hermes;
- an executor of any coding agent (Codex, Claude Code, Gemini CLI, or otherwise);
- a public unauthenticated internet service;
- a system that executes skill prose directly;
- an architecture that retries externally ambiguous mutations automatically;
- a monolithic rewrite that discards accepted durable evidence.

---

## 11. Final strategic sequence

```text
Priority 0  Complete CF1
Phase 1     Canonical task plane
Phase 2     Kernel consolidation and permission removal
Phase 3     Windows-first unrestricted host execution
Phase 4     Unified capability broker and Hermes H2
Phase 5     Skills, memory, and deterministic context
Phase 6     Delegation, parallel workers, workflows, and worktrees
Phase 7     Browser, desktop, and multimodal providers
Phase 8     Scheduling, continuity, and return delivery
Phase 9     Linux and macOS adapters
Phase 10    Observability, packaging, and final legacy removal
```

This order ensures that:

- the current conversation-footprint problem is solved first;
- replacement task semantics exist before legacy controls are removed;
- the useful Windows agent becomes real before cross-platform completion;
- Hermes and external MCP capabilities join one broker;
- skills and context exist before broad delegation;
- delegation exists before unattended scheduling becomes powerful;
- browser and desktop control use the same durable task/evidence model;
- cleanup occurs only after migration is proven.
