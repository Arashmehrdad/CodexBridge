# Soma — Agentic Runtime Audit and Strategic Roadmap (Revised)

## Status, authority, and current baseline

This document is a **strategic architecture and implementation roadmap**. It describes the intended direction of Soma and the ordered migration path; it is not proof that every described capability already exists.

This revision consolidates:

- the live repository audit;
- the completed CF1 evidence and cross-client MCP transport fix;
- the independent Claude architecture audit;
- the ecosystem and third-party integration research;
- the Apache-2.0 compatibility review;
- the live repository-wiki investigation;
- owner corrections and accepted product decisions.

Arash is the owner and final decision-maker for scope, risk acceptance, security posture, integrations, and roadmap priority. Audits and research reports are evidence and recommendations, not authority. Where this roadmap conflicts with a later explicit owner instruction or `AGENTS.md`, the later owner instruction and `AGENTS.md` take precedence.

### Historical audit baseline captured for this revision

The branch and HEAD below identify the repository state examined during this audit. They are intentionally preserved as historical audit evidence and are not intended to track the repository's current HEAD while the architecture remains under review.

- Branch: `feature/domain-tool-gateway-migration`
- Verified HEAD during the revision: `33623c404477165c07e9cc914cac46b365ee4d7a`
- CF1 implementation and acceptance: **complete**
- Cross-client MCP compatibility: **fixed**
- CF1 remaining work: documentation reconciliation only
- Active implementation lane: whichever bounded post-CF1 batch Arash explicitly selects
- Phase 1 first bounded batch (TASK-1 — Canonical Task Plane Foundation): **implemented and accepted on 2026-07-25**; see `docs/task1-canonical-task-plane-evidence.md`. Phase 1 as a whole is not complete: only the durable local command backend is mapped, only `cancel` is version-guarded, and no checkpoint round-trip exists yet.
- Recommended next implementation lane: the remainder of **Phase 1** (additional backend mappings, the remaining version-guarded commands, and controller checkpoints), then **Phase 2**. This document does not activate either automatically.

### Publication reconciliation status

This audit remains under owner review. Its captured baseline should remain frozen until the architecture is accepted. When this document is promoted into the replacement implementation roadmap, reconcile the new roadmap against the live branch, HEAD, completed lanes, active lane, worktree, running service, and public schemas. Preserve this audit baseline as historical evidence and archive the existing V2 roadmap as a clearly labelled legacy roadmap rather than rewriting its history.

The repository and service continue to evolve. Before implementing any phase, re-run preflight, inspect the live branch and worktree, verify the running service build and schemas, and re-check any external project whose licence or architecture could have changed.

---

## 1. Product definition

Soma is a local, durable, model-independent agent runtime, project coordination system, and engineering control plane.

Its purpose is:

> **To let Arash give ChatGPT an owner-level outcome such as “build this SaaS,” after which ChatGPT can plan the work, decompose it into a project-aware agent swarm, delegate to the best available coding or operational specialists, review and replan from evidence, while Soma preserves identity, isolation, durable execution, tools, knowledge, and continuity underneath the whole operation.**

ChatGPT is Arash's primary executive controller and chief of staff. It interprets owner intent, forms and revises the project plan, chooses specialists, delegates work, resolves cross-cutting judgment, and presents the final outcome. Soma remains controller-portable at its protocol boundary so durability is not technically trapped inside one vendor, but that portability does not flatten the intended product relationship or turn every worker into an equal authority.

Alternate or supporting controllers may include:

- Claude;
- Hermes;
- another MCP-capable assistant;
- a future local or remote controller.

A specialised worker may be:

- Codex CLI or another coding-agent runtime;
- Claude Code or another coding specialist;
- Hermes;
- a native Soma executor;
- an external MCP server;
- a browser or desktop agent;
- a repository-intelligence sidecar;
- another replaceable provider or agent runtime.

Soma supplies:

- canonical project, task, agent-session, and run identity;
- a project-aware work graph spanning goals, dependencies, assignments, workspaces, artifacts, decisions, and status;
- durable execution, leases, recovery, cancellation, and reconciliation;
- repository inspection and managed mutation;
- isolated workspaces and worktrees for parallel specialists;
- local and remote host execution;
- provider and agent-worker discovery, routing, invocation, and supervision;
- skills and deterministic context;
- memory and repository knowledge;
- evidence, artifacts, hashes, validation, and result publication;
- workflows, swarm delegation, scheduling, and return delivery;
- browser, desktop, and multimodal capability providers;
- compact progressive disclosure for ChatGPT and other connected clients.

### Target relationship

```text
                         Arash
                            |
                            v
          ChatGPT executive controller / chief of staff
        plan | decompose | delegate | review | replan
                            |
                            v
             Compact controller and interaction surface
                            |
                            v
+----------------------------------------------------------------+
| Soma application container                                     |
|                                                                |
| Project and work-graph plane    Canonical task plane            |
| Agent-worker registry           Capability broker               |
| Execution/workspace backends    Context, memory, and skills      |
| Evidence and artifact service   Repository knowledge             |
| Scheduler, events, and delivery outbox                          |
+----------------------------------------------------------------+
          |                         |                         |
          v                         v                         v
 Native capabilities        Specialist agent swarm       Knowledge graphs
 repo / shell / SSH         Codex / Claude Code          Graphify / Graphiti
 Docker / browser           Hermes / future agents       workspace projections
 domain providers           local or remote
```

Soma must not become tied to one model vendor, one conversation history, one coding tool, or one external agent framework. Replaceability protects the infrastructure; it does not remove ChatGPT's default executive role for Arash.

### Executive controller versus specialist worker

ChatGPT is the primary reasoning and project-direction controller and uses Soma's compact contracts to create plans, delegate work, inspect evidence, revise the work graph, and integrate results. Soma is the durable coordination substrate: it remembers which project is which, what every task depends on, which agent owns it, where its workspace lives, what it produced, and what still blocks completion.

Soma is explicitly allowed to launch, supervise, resume, steer, and cancel coding-agent CLIs and other model-agent processes through versioned agent-worker adapters. Codex CLI, Claude Code, Hermes, and future specialists may reason, use tools, and modify isolated workspaces within their delegated task contracts. They do not own the global project plan, silently cross project boundaries, or publish unvalidated output as final truth.

Every agent session is bound to an exact project, task, role, workspace or worktree, context packet, skill set, implementation version, model identity where available, budget, and evidence stream. ChatGPT receives compact progress, conflicts, reviews, and checkpoints and may replan without losing the history of earlier assignments. A handoff packet remains useful as an export format, but it is no longer the only permitted relationship with an external coding agent.

---

## 2. Trust and security model

### 2.1 Owner-trusted unrestricted execution

Soma is intentionally an unrestricted owner-controlled execution service after a trusted connection reaches it.

It does not require:

- per-command approval prompts;
- permission tiers as execution gates;
- autonomy profiles as execution gates;
- executable allowlists as user-permission barriers;
- confirmation phrases used as pseudo-permissions;
- model-specific approval records for ordinary execution;
- automatic denial based only on program name or command category.

Do not reintroduce those mechanisms through a framework integration, workflow engine, gateway, or audit recommendation unless Arash explicitly changes the decision.

### 2.2 Correctness and durability controls remain mandatory

Removing permission machinery does not remove engineering controls. Soma must preserve:

- exact request and executable identity;
- content hashes and immutable evidence references;
- idempotency;
- resource leases;
- stale-version detection;
- compare-and-set transitions;
- exact process and process-start identity;
- cancellation scoping;
- repository and worktree isolation;
- atomic result publication;
- mutation reconciliation;
- artifact provenance;
- rollback evidence;
- uncertainty reporting;
- secret redaction from public projections.

These mechanisms protect correctness and recoverability. They are not user-permission gates.

### 2.3 Network boundary

The unrestricted runtime must remain behind an owner-controlled network boundary.

- Bind to loopback by default.
- Never expose the unrestricted MCP or execution endpoint directly to the public internet.
- Remote access must use an authenticated private tunnel or equivalent owner-controlled transport.
- Connector and client identity may support correlation, continuity, and ownership, but must not recreate the removed approval system.
- External sidecars and providers must follow the same private-boundary rule unless their own exposure is explicitly designed and reviewed.

---

## 3. Governing architectural principles

1. **Controller neutrality.** ChatGPT, Claude, Hermes, and future clients use the same durable contracts.
2. **Integrate before rebuilding.** Prefer proven libraries, services, MCP servers, and provider adapters when they save meaningful implementation and maintenance effort.
3. **Soma keeps canonical authority.** External tools must not silently become the public source of truth for tasks, evidence, memory policy, repository identity, or lifecycle state.
4. **The existing durable kernel is an asset.** Consolidate and abstract it before considering replacement.
5. **One canonical task plane.** Every executor maps into one public task identity and command model.
6. **One authoritative resource-lock and lease model.** Do not add independent lock systems.
7. **One process-level application container.** Stores, managers, providers, routers, platform adapters, and telemetry are created once and injected.
8. **Typed provider and worker boundaries.** Kernel-to-worker communication uses versioned schemas rather than implementation-object coupling.
9. **Progressive disclosure by default.** Preserve authoritative detail once; return only the compact useful projection until exact evidence is requested.
10. **Inline reads, durable writes.** Fast bounded reads may return immediately; long-running or mutating work returns a canonical task identity.
11. **Windows first, portable core.** Windows is the first production target; task, evidence, capability, and scheduler schemas remain platform-neutral.
12. **No big-bang migration.** Add replacement contracts, adapt old systems, prove acceptance, then remove obsolete paths.
13. **Small external pilots.** External components enter through reversible, measured pilots before promotion.
14. **Licensing is an architecture constraint.** Soma targets Apache-2.0 and must preserve compatible distribution boundaries.
15. **Audits do not overrule the owner.** A recommendation becomes direction only after owner acceptance.
16. **Documentation preserves achievements.** Completed milestones and historical evidence are retained instead of being erased from an active plan.

---

## 4. Audit verdict

### 4.1 Confirmed strengths

Soma already has substantial proven infrastructure:

- persist-before-launch durable runs;
- launcher, worker, and child-process identity;
- leases, heartbeats, cancellation, and restart reconciliation;
- durable outputs and artifacts;
- protected result publication;
- repository inspection and hash-verified managed mutation;
- repository locks;
- workflows, supervisors, SSH, Docker, Cloudflare, Trading Lab, and Hermes foundations;
- compact public projections and exact evidence retrieval;
- cross-client MCP transport compatibility;
- repository wiki and SQLite memory foundations.

This is not an agent demo or a thin model wrapper. It is already a durable runtime with real operational history.

### 4.2 Confirmed structural problems

The main weakness is fragmentation rather than lack of capability:

- multiple lifecycle authorities and overlapping stores;
- legacy job, supervisor, workflow, and local-coding paths;
- policy and approval machinery that no longer matches the accepted owner model;
- controller-specific persisted terminology;
- no canonical parent/child task plane;
- provider discovery and invocation spread across domain gateways;
- a large server composition surface;
- no single process-level application container;
- no unified execution-backend or workspace-provider abstraction;
- no durable scheduler contract;
- repository wiki refresh is not automatically orchestrated;
- memory, wiki, evidence, and context packets risk becoming overlapping truth systems;
- browser and desktop control are not yet general providers;
- Windows assumptions remain embedded in execution paths;
- external integrations have not yet been governed by a consistent boundary and licence policy.

### 4.3 Important corrections to external audits

The following owner corrections are binding:

- CF1 is complete; stale documentation does not make it an active blockade.
- Soma is model-independent; ChatGPT is not the sole architecturally privileged controller.
- Owner-trusted unrestricted execution is accepted; do not revive permission tiers or approval gates.
- Hermes remains a strategic controller/worker/provider integration, not a rejected platform.
- OpenClaw, OpenHands, goose, Letta, LangGraph, AutoGen/AG2, browser-use, and similar projects may be architecture mines or isolated providers even when wholesale adoption is rejected.
- Temporal is not an immediate replacement for Soma’s durable engine. It is a possible later optional execution backend.
- Docker or Microsoft MCP gateways are not automatically required; use them only when a demonstrated routing, profile, or deployment problem justifies a second gateway.
- Watchman must not be selected on reputation alone; Windows-first watcher behavior and packaging must be measured.
- Graphify may augment repository intelligence, but it must not replace Soma’s wiki and evidence authority.
- External recommendations mentioning approvals or policy layers must be translated into Soma’s accepted dispatch, validation, routing, evaluation, and durability model.

---

## 5. External-component integration policy

### 5.1 Integration classifications

Every serious candidate receives one primary classification:

- **A — Use directly as an external service or MCP server**
- **B — Wrap as a Soma capability or worker provider**
- **C — Embed as a library**
- **D — Port selected licence-compatible modules**
- **E — Reimplement only the architectural idea**
- **F — Reject or defer**

“Reject wholesale adoption” does not mean ignoring useful isolated capabilities. Soma may use one subsystem from a broader agent product through a clean boundary.

### 5.2 Candidate evaluation record

Before promotion, record:

- project and source revision;
- exact capability supplied;
- maturity and maintenance activity;
- platform support, especially Windows;
- language and runtime;
- extension and deployment model;
- integration classification;
- exact boundary with Soma;
- persistence and authority model;
- dependency weight;
- licence expression and transitive licence closure;
- expected implementation time saved;
- integration and long-term maintenance cost;
- security and network assumptions;
- tests and documentation quality;
- rollback method;
- pilot acceptance metrics.

Do not select a project because of stars, marketing claims, or feature count.

### 5.3 Canonical-authority rule

External components may own their internal implementation state, but Soma remains authoritative for the public contract.

| Concern | Canonical owner |
|---|---|
| Public task identity and parent/child relationships | Soma |
| Controller-visible task state and commands | Soma |
| Resource leases and repository isolation | Soma |
| Evidence IDs, hashes, artifacts, and result publication | Soma |
| Execution-attempt identity, immutable runtime manifests, compatibility decisions, and provenance links | Soma |
| Repository identity and final grounded repository answers | Soma |
| Memory policy, provenance, and context-packet selection | Soma |
| Provider-local cache, browser session internals, parser cache, or workflow-engine internals | External component behind an adapter |
| External component health and revision | Provider record in Soma |

For any task assigned to an external execution backend, Soma stores the backend identity and mapping. One task must not have two competing active lifecycle owners.

### 5.4 Licence and distribution policy

Soma’s target project licence is **Apache-2.0**. The repository is not considered distribution-ready merely because this roadmap states that target; the release phase must add and validate the actual `LICENSE`, `NOTICE`, third-party notices, and SBOM.

Default policy:

- Apache-2.0, MIT, BSD, ISC, and similarly permissive components may be embedded or selectively ported after notice review.
- MPL/EPL components require preserved file boundaries and explicit review.
- LGPL components require a deliberate library boundary and compliance plan.
- GPL/AGPL components must not be copied or loaded into the Soma process when the goal is an Apache-2.0 distributable. Use a genuinely separate process, MCP server, or service when appropriate.
- Proprietary components require contract review.
- Every candidate must be evaluated on the final distributed dependency closure, not only the root repository licence.
- Preserve upstream licence text, copyright, applicable `NOTICE` content, modified-file notices, source revision, and imported-file inventory.
- Generate and retain SPDX or CycloneDX evidence for release artifacts.
- Do not copy Git source for the repository watcher; implement independently or use a compatible dependency.

The detailed third-party licensing report may be maintained as a companion policy document, but the roadmap remains self-contained on the binding architectural rules.

---

## 6. Current ecosystem decisions

### 6.1 Prepare or integrate when the owning phase opens

These are high-confidence components or directions, not permission to skip phase order.

| Candidate | Classification | Intended use | Boundary |
|---|---:|---|---|
| Hermes H2 | B | Persistent controller/worker and capability aggregation | Provider/worker under Soma task and evidence contracts |
| OpenTelemetry | C | Cross-process tracing, metrics, and correlation | Embedded SDK plus optional collector |
| Tree-sitter | C | Incremental structural parsing | Embedded repository-intelligence primitive |
| Playwright | B or A | Deterministic browser automation and evidence capture | Isolated browser provider or MCP worker |
| FastMCP | C | MCP protocol plumbing where it reduces boilerplate | Library below Soma’s public domain contracts |
| `uv` | B | Initial Python lock, exact environment sync, managed interpreter, and CycloneDX export tool | Soma owns runtime-manifest identity and accepts other ecosystem-native lock providers |
| Syft | B | Optional cross-ecosystem SBOM generation for reusable runtime bundles and release artifacts | Inventory evidence only; never execution or package authority |
| APScheduler | C | Lightweight trigger calculation and recurring jobs | Behind Soma’s canonical schedule/task store |

### 6.2 Pilot later, behind explicit boundaries

| Candidate | Classification | Pilot purpose | Promotion constraint |
|---|---:|---|---|
| `lastmile-ai/mcp-agent` | D or narrow C | Application-container, connection-manager, and workflow-pattern comparison | Must not create a shadow task plane |
| Graphify-Labs/graphify | A or narrow C | Derived project knowledge-graph pilot across code, documentation, configuration, schemas, and selected media | Structural code facts may be imported from deterministic local extraction; semantic and inferred relations must remain provenance-labelled, rebuildable, and re-grounded to Soma source/evidence references |
| Stagehand | C | Semantic action discovery above Playwright | Raw DOM/screenshot fallback and deterministic evidence remain available |
| Temporal | A | Optional execution backend for one isolated long-running workflow | Soma task identity and result publication remain canonical |
| Mem0 | B | Derived preference/retrieval memory | Must be rebuildable from Soma-owned sources |
| Graphiti | B | Initial temporal context-graph provider for decisions, task history, skill learning, and continuity | Derived and rebuildable from Soma-owned sources; accepted facts, provenance, temporal validity, export, and provider replacement remain under Soma contracts |
| `watchfiles` | C | Initial embedded Windows-first repository-change notification adapter | Low-latency hints only; Soma owns durable generations, reconciliation, queues, and public events. Native `ReadDirectoryChangesW` and Watchman remain replaceable benchmark candidates. |
| Docker MCP Gateway | A | Third-party MCP profile packaging if a real need exists | No duplicate canonical capability registry |
| Microsoft MCP Gateway | A | Hosted multi-session routing if scale justifies it | No unnecessary second control plane |
| Supergateway | A | Transport conversion for an otherwise blocked MCP server | Edge shim only |

### 6.3 Study and borrow ideas; do not adopt wholesale

| Project family | Useful ideas |
|---|---|
| OpenHands | Workspace/provider abstraction; action/observation structure; local, Docker, and remote workspaces |
| AutoGen Core / AG2 | Typed worker messages, capability advertisement, host/worker separation |
| Letta | Explicit context hierarchy and server-owned persistent state concepts |
| goose | Portable recipes, skills, extension packaging, provider-neutral UX |
| LangGraph | State-machine and resumable workflow ideas |
| OpenClaw | Isolated capabilities and packaging patterns; never arbitrary in-process plugin authority |
| browser-use | Browser-agent techniques only when Playwright and Stagehand are insufficient |
| Zep | Comparator for managed context infrastructure, not a canonical Soma dependency |

### 6.4 Explicitly avoid

Avoid:

- wholesale replacement of Soma with another agent framework or “agent OS”;
- a second canonical task, memory, evidence, repository, or scheduler authority;
- arbitrary third-party plugins loaded into the Soma kernel process;
- strong-copyleft code copied into the Apache-target Soma codebase;
- a gateway added only because it is fashionable;
- a hosted memory or browser service that makes local continuity dependent on one vendor;
- any integration that cannot be removed without losing canonical Soma records.

---

## 7. Target architecture

### 7.1 Soma application container

Create one process-level `SomaApplication` or equivalent container that owns and injects:

- configuration;
- schema and migration service;
- project and portfolio registry;
- canonical work-graph and projection service;
- task store and task manager;
- agent-worker registry and session manager;
- run/workflow compatibility adapters;
- resource lease and lock service;
- execution-backend registry;
- provider registry and connection manager;
- context, memory, skill, and repository-knowledge services;
- evidence, artifact, validation, and integration service;
- scheduler and delivery outbox;
- event router;
- telemetry and usage accounting;
- readiness and reconciliation state.

Do not continue discovering these services through scattered globals and server-level monkey patches.

### 7.2 Canonical project, portfolio, and work-graph plane

An owner outcome such as “build this SaaS” is represented as a durable project, not as a loose collection of unrelated prompts and processes.

A canonical project contains at least:

- `project_id` and optional portfolio or product identity;
- owner objective, success criteria, constraints, and current lifecycle state;
- repositories, workspaces, services, environments, and deployment targets;
- plan generation and accepted work-breakdown version;
- milestones, work packages, and project-scoped budgets;
- decision, memory, skill, and knowledge namespaces;
- active task, agent-session, artifact, release, and evidence references;
- project-level reconciliation and completion state;
- timestamps and provenance.

Every task, agent session, workflow, worktree, artifact, decision, skill binding, model invocation, build, deployment, and evidence record must bind to one primary `project_id`. Cross-project work uses explicit typed source and target links; a worker must never infer that two repositories, tasks, or similarly named artifacts belong to the same project.

Soma owns a versioned work graph whose useful edge types include:

```text
PART_OF
DEPENDS_ON
BLOCKS
ASSIGNED_TO
OPERATES_IN
READS
CHANGES
PRODUCES
CONSUMES
VALIDATES
REVIEWS
INTEGRATES
DEPLOYS
DERIVED_FROM
SUPERSEDES
```

The graph supports bounded views over:

- portfolio and project identity;
- goals, milestones, tasks, dependencies, and critical path;
- agent roles, sessions, assignments, capacity, and handoffs;
- repositories, workspaces, worktrees, branches, files, and services;
- artifacts, evidence, tests, builds, releases, and deployments;
- decisions, skills, memories, and their effect on work.

This coordination graph is projected from Soma-owned canonical records and events. Graphify enriches project structure, Graphiti enriches temporal and relational context, and the knowledge workspace supplies owner-readable knowledge; none of them replaces canonical project, task, assignment, artifact, or dependency state.

Public graph queries and events must let ChatGPT and the future Cortana interface answer, without reading private databases directly:

```text
which project is this
what belongs here
what depends on this
who or what owns it
where is the active workspace
what changed
what was produced
what conflicts
what is blocked
what should run next
why was this decision made
```

### 7.3 Canonical task plane

A canonical task contains:

- `task_id`, required `project_id`, and immutable attempt identities;
- runtime-manifest references for every launched attempt or resumed agent session;
- optional plan, milestone, work-package, parent-task, and typed-link references;
- controller request ID and normalized request hash;
- objective, acceptance criteria, and constraints references;
- task kind and swarm role;
- controller identity where relevant;
- selected agent worker, executor, provider, or backend;
- workspace and resource leases;
- state and phase;
- `state_version`;
- checkpoint references;
- child task references;
- result and evidence references;
- recovery and reconciliation state;
- timestamps.

Controller-neutral states should include:

```text
accepted
queued
running
awaiting_controller
paused
cancellation_pending
recovery_pending
completed
failed
cancelled
uncertain
```

There is no approval state.

A checkpoint contains:

- question, missing input, or judgment requirement;
- expected input schema;
- source context and evidence references;
- the task state version against which the controller must respond.

### 7.4 Execution-backend contract

Hide current and future engines behind one contract:

```python
class ExecutionBackend:
    async def start(self, task_spec): ...
    async def query(self, backend_ref): ...
    async def signal(self, backend_ref, command): ...
    async def cancel(self, backend_ref): ...
    async def reconcile(self, backend_ref): ...
    async def result(self, backend_ref): ...
```

The existing Soma durable engine is the first and default backend.

Temporal, another workflow service, or a future remote worker runtime may be added only as optional backends. Backend selection is persisted at task creation and must not change silently while a task is active.

### 7.5 Workspace-provider contract

Use one platform-neutral workspace contract inspired by the strongest parts of OpenHands without adopting its product shell:

```text
execute
read_file
write_file
patch_file
list_files
search
upload
download
start_process
query_process
cancel_process
inspect_process
stream_events
snapshot
close
```

Expected implementations:

```text
WindowsLocalWorkspace
SSHWorkspace
DockerWorkspace
HermesWorkspace
BrowserWorkspace
FutureLinuxWorkspace
FutureMacOSWorkspace
```

Each implementation maps to the same task, lease, cancellation, evidence, and artifact model.

### 7.6 Capability provider contract

A provider exposes:

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

Provider identity includes:

- provider ID and kind;
- implementation revision;
- schema and operation hashes;
- catalog generation;
- platform requirements;
- supported operations;
- health;
- load/capacity where relevant;
- cancellation and reconciliation support;
- persistence and external-authority metadata.

Persistent providers may keep warm connections. Transient providers may connect for one invocation. The kernel should not import detailed knowledge of every provider.

### 7.7 Agent-worker contract

Model-agent specialists are integrated through a contract distinct from deterministic capability invocation:

```python
class AgentWorkerAdapter:
    async def discover(self): ...
    async def describe(self, worker_id): ...
    async def start_session(self, assignment): ...
    async def supply_input(self, session_ref, input): ...
    async def query(self, session_ref): ...
    async def stream_events(self, session_ref, cursor): ...
    async def checkpoint(self, session_ref): ...
    async def cancel(self, session_ref): ...
    async def reconcile(self, session_ref): ...
    async def result(self, session_ref): ...
    async def close(self, session_ref): ...
```

Initial adapters may target Codex CLI, Claude Code, Hermes, and other explicitly selected local or remote coding agents. The adapter normalizes lifecycle and evidence without pretending that different agents have identical private features.

Persist for every session:

- canonical `agent_session_id`, `project_id`, and `task_id`;
- worker adapter, tool, implementation version, and executable identity;
- resolved model/provider identity where available;
- role, assignment contract, expected output, and acceptance criteria;
- context-packet, skill, prompt, and configuration digests;
- workspace, worktree, branch, environment, and resource leases;
- tool and capability grants required by the assignment;
- budget, usage, progress cursor, checkpoint, and recovery state;
- transcript or event-artifact references;
- produced artifacts, proposed changes, reviews, tests, and final result.

Agent workers receive only project- and task-scoped context unless an explicit typed cross-project dependency requires more. Their output is a proposal or work product until the relevant validation and integration gates accept it. Agent replacement, restart adoption, and resumption must not change project or task identity.

### 7.8 Execution runtime manifest and capsule contract

Every durable task attempt, workflow execution, consequential capability run, and agent session binds one immutable `runtime_manifest_id` before execution begins. The manifest is the frozen receipt for what was requested, what was actually resolved, what environment ran, and what outputs were produced.

Use a Soma-owned schema inspired by SLSA provenance and the in-toto attestation model without making either project a runtime dependency. Separate:

- requested worker, backend, model, skills, inputs, and constraints;
- resolved dependencies and exact runtime identities;
- run details, fallbacks, timestamps, process or container identity, outcome, and output digests.

Canonicalize the JSON representation before hashing and identify it by SHA-256. The first implementation should use a deterministic JSON canonicalization compatible with RFC 8785 semantics. Once sealed, a manifest is immutable. Any change to a resolved worker, model, executable, skill, provider schema, configuration, dependency lock, container image, or workspace starting state creates a new attempt and a new manifest rather than rewriting history.

A manifest records at minimum:

- `runtime_manifest_id`, schema version, task attempt, project, task, workflow, and agent-session references;
- Soma build or source revision and runtime schema version;
- requested and resolved worker, adapter, backend, provider, and model identities, including fallback reasons;
- executable path, SHA-256, reported version, package/source identity where available, and platform signature information;
- OS build, architecture, interpreter, shell, container, remote-host, and workspace-provider identity as applicable;
- provider catalog generation and invoked operation schema hashes;
- exact promoted skill versions, digests, and resolved dependency graph;
- context-packet, prompt/template, configuration-generation, and safe environment-description digests;
- repository identity, base commit, branch, worktree, source snapshot, and dirty-state or patch-artifact digest;
- language/runtime lockfile identities and dependency-inventory references;
- resource and credential references without secret values;
- started, resumed, migrated, and completed timestamps;
- results, artifacts, tests, reviews, evidence, and output digests.

Use the strongest practical identity method for each environment:

- Windows host CLIs: resolved executable path, SHA-256, file/product version, Authenticode status and signer when present, package-manager/source identity where known, OS build, architecture, and shell identity;
- Python: interpreter identity plus a `uv.lock` or standards-compatible `pylock.toml` digest, the `uv` version, and proof of locked exact synchronization; `uv` is the initial Soma and Python-worker choice, not a universal project requirement;
- containers: immutable OCI image and platform digests rather than mutable tags;
- Node, Rust, Java, .NET, and other ecosystems: native lockfile digest, runtime and package-manager versions, and an exact-sync or equivalent verification result;
- remote workers: host-profile and binding identity plus the actual deployment build, image, executable, or environment revision.

A reusable runtime bundle may hold stable environment material referenced by many attempt manifests. Optional Syft-generated CycloneDX or SPDX inventory may attach to a registered bundle or release artifact; a full SBOM is not required for every small task attempt.

Classify replay honestly:

```text
IDENTIFIED       exact observed identities and inputs are recorded
RECONSTRUCTABLE  required pinned dependencies and runtime material remain obtainable
REPLAYABLE       the operation is deterministic enough to expect equivalent rerun behavior
```

Every attempt must be `IDENTIFIED`. Model-agent sessions and hosted-model calls must not claim byte-for-byte replay merely because the same public model name was recorded. Store provider response IDs, model revision when exposed, parameters, tool-schema hashes, and timestamps, then mark replayability honestly.

Recovery follows one explicit path:

1. resume under the same runtime manifest and available compatible bundle;
2. create a new attempt manifest after an explicit compatibility-approved worker or environment transition;
3. create a migration record linking `migrates_from` and `resumes_from` manifests;
4. enter `recovery_pending` when compatibility or required runtime material cannot be proven.

Fallback, reassignment, upgrade, or migration must record both requested and actual resolved runtime identities. Old runtime bundles and worker versions remain retained while active tasks or configured replay-retention windows can still reach them; cleanup uses reachability and retention evidence rather than age alone.

Every consequential result and artifact links back to the producing runtime manifest. Soma may later emit in-toto-compatible attestations or signed envelopes for release, export, or cross-machine verification, but local task durability does not depend on deploying a separate attestation service.

### Runtime-history exit gate

After an upgrade or restart, Soma can prove which exact runtime produced every result, distinguish requested from actual worker/model selection, resume only under a verified compatible environment, create an explicit new attempt for any transition, and refuse silent substitution. Deterministic work can be reconstructed or replayed where its recorded class promises it; model-agent work remains fully traceable without making a false determinism claim.

### 7.9 Typed worker messages

Use versioned serializable messages between the kernel and process/host boundaries:

```text
CapabilityAdvertised
PlanProposed
AssignmentCreated
TaskAssigned
TaskAccepted
ProgressReported
CheckpointRequested
InputSupplied
ArtifactProduced
ReviewReported
IntegrationProposed
CancellationRequested
AgentSessionRecovered
TaskCompleted
TaskFailed
WorkerHealthReported
ProviderCatalogChanged
```

This enables local-to-remote migration without coupling the kernel to one worker implementation.

### 7.10 Context hierarchy

Keep context sources explicit and project-scoped:

1. current project identity, owner objective, accepted plan, and work-graph position;
2. current task objective, acceptance criteria, constraints, role, and checkpoint;
3. project-scoped decisions, skills, dependencies, and critical facts;
4. live repository source and the exact assigned workspace, worktree, branch, and environment state;
5. current repository wiki, Graphify structure, and relevant project artifacts;
6. current run/task evidence, reviews, integration state, and child summaries;
7. accepted owner knowledge and bounded Graphiti temporal context;
8. archival project memory;
9. external MCP, graph, or retrieval providers.

A task from one project must not receive another project's context merely because names, technologies, or repository paths look similar. Explicit typed cross-project links are the only normal bridge. The hierarchy prevents projects, memory, wiki, evidence, agent transcripts, and chat history from becoming competing or accidentally mixed truth systems.

---

## 8. Systems to preserve, migrate, or retire

### Preserve and strengthen

- root durable run store and worker lease model;
- exact process identity and owned-tree cancellation;
- repository locks and mutation evidence;
- result publication and protected artifacts;
- repository inspection and managed mutation;
- deterministic workflows where useful;
- SSH and remote durability;
- Docker, Cloudflare, Trading Lab, and other domain providers;
- Hermes H1 compatibility path while H2 becomes production-ready;
- Hermes H2 process, identity, concurrency, and catalog foundations;
- external-coder handoff generation;
- repository wiki and SQLite memory storage foundations;
- CF1 progressive-disclosure and evidence-reconstruction contracts.

### Migrate before removal

- legacy job lifecycle behavior;
- supervisor recovery and continuation behavior;
- local-coding state;
- synchronous coding-result paths;
- controller-specific `awaiting_chatgpt` values;
- approval-oriented `needs_input` or `needs_approval` values;
- useful dashboard/TUI diagnostics;
- duplicated schema and catalog registration;
- policy-tier, approval-store, confirmation, and `allow_*` fields needed only for historical readability;
- keyword local-agent behavior containing reusable routing or context logic.

### Retire after successful migration

- legacy permission and approval gates;
- duplicate supervisor stacks;
- duplicate local-coding state;
- legacy job manager;
- synchronous coding-agent bypasses;
- automatic vendor-specific coding-agent routing;
- unused general-purpose local reasoning paths;
- dashboard and service TUI after useful diagnostics move to compact queries;
- server monkey patches;
- duplicate capability catalogs and schema paths;
- any external pilot that fails its acceptance or creates a competing authority.

### Historical preservation

Before removing a substantial legacy subsystem:

- record what it achieved;
- record the commits or evidence that proved it;
- identify the behavior migrated elsewhere;
- preserve schema-read compatibility where required;
- record the deletion boundary and rollback path.

Use an achievement or migration record rather than erasing project history from the active roadmap.

---

## 9. External-pilot protocol

Every external integration begins as a small, independently reviewable pilot.

A pilot specification must contain:

- objective;
- candidate project and pinned revision;
- classification A–F;
- exact Soma-owned boundary;
- files/modules likely affected;
- external state created;
- licence and notice work;
- acceptance tests;
- failure and rollback method;
- observability requirements;
- time-box;
- promotion or rejection metrics.

Default pilot rules:

- start read-only where possible;
- use one repository, tenant, browser profile, or workflow;
- do not migrate canonical state into the pilot;
- do not delete the previous implementation;
- preserve raw evidence for comparison;
- remove the pilot cleanly if it fails;
- capture actual implementation time saved, not estimates alone.

A component is promoted only when it improves one or more of:

- correctness;
- durability;
- implementation speed;
- maintenance burden;
- provenance;
- context compactness;
- operator visibility;
- platform support.

Feature count alone is not a promotion criterion.

---

## 10. Corrected implementation roadmap

## Closed milestone — CF1 Chat Footprint and Progressive Disclosure

CF1 is complete and accepted.

Completed outcomes include:

- scalar SQL-backed run summaries;
- compact control polling and events;
- bounded terminal projections;
- exact evidence reconstruction;
- repository read/search/diff progressive disclosure;
- response budgets across public gateways;
- representative connector-visible footprint reduction above target;
- authoritative result and hash preservation;
- MCP cross-client compatibility through both structured content and populated `content[].text`.

Any remaining CF1 wording in older documentation is a documentation defect, not an implementation blockade.

Preserve detailed CF1 evidence in the achievement record. Do not keep CF1 labelled as the sole active engineering lane.

---

## Phase 1 — Canonical task plane before destructive cleanup

Build the replacement control model before removing old lifecycle systems.

### Deliverables

- canonical `tasks`, `task_links`, `task_commands`, `task_checkpoints`, and task events;
- one public task identity independent of executor;
- links from new tasks to existing run, workflow, supervisor, Hermes, SSH, and command-group identities;
- top-level idempotency using controller request ID plus normalized request hash;
- controller-neutral states, especially `awaiting_controller`;
- state-version-guarded steer, input, pause, resume, retry, and cancel;
- explicit storage of controller input and resolved executable input;
- compact task, parent, child, checkpoint, result, and evidence queries;
- compatibility adapters for existing public run/workflow/supervisor operations;
- backend identity field for future optional execution engines;
- no deletion of legacy stores in this phase.

### Recommended first bounded batch

1. add canonical task tables and models;
2. map one existing durable run type into a task;
3. implement compact task status/result queries;
4. implement one version-guarded command;
5. add migration and adapter tests;
6. prove old run queries remain unchanged.

### Exit gate

Every current execution type can be represented and supervised through one compact task protocol without losing recovery, cancellation, or evidence behavior.

---

## Phase 2 — Application container, lifecycle consolidation, and legacy permission removal

### Deliverables

- one process-owned application container;
- one schema-version table with ordered transactional migrations;
- immutable execution-attempt and runtime-manifest storage with content-addressed identity;
- runtime-bundle registration, compatibility evaluation, reachability, retention, and migration links;
- incompatible workers fail readiness honestly;
- one authoritative path for launch, worker lease, state transition, cancellation, publication, and recovery;
- all ownership-sensitive progress updates use lease-generation compare-and-set;
- startup reconciliation failures become durable evidence and unhealthy readiness;
- crash-safe journaling for multi-file rollback/revert;
- migration of useful supervisor and legacy-job behavior into tasks/workflows;
- migration of controller-specific persisted values through explicit compatibility mappings;
- removal of permission tiers, approval gates, autonomy gates, confirmation phrases, and runtime `allow_*` barriers after historical compatibility is preserved;
- `allowed_files` becomes optional scope/evidence metadata rather than authorization;
- baseline OpenTelemetry trace IDs propagated through task, run, provider, and evidence operations;
- evaluation of FastMCP only where it removes protocol boilerplate without changing Soma contracts.

### Application-container pilot input

Study `mcp-agent` for:

- one application context per process;
- provider/server registry;
- connection manager;
- execution-backend abstraction;
- async task handles.

Borrow or port only the parts that fit Soma. Do not import a second task authority.

### Exit gate

One Soma kernel owns every active lifecycle decision, obsolete permission machinery is no longer an execution gate, and service composition no longer depends on scattered global initialization.

---

## Phase 3 — Windows-first unrestricted host execution and workspace abstraction

### Deliverables

- platform-neutral process, filesystem, service, and workspace interfaces;
- direct executable plus argv execution;
- PowerShell, pwsh, and cmd adapters;
- unrestricted whole-machine filesystem operations;
- arbitrary absolute working directories;
- durable background execution;
- Windows Job Objects or equivalent owned-tree cancellation;
- process creation-time and canonical identity evidence;
- executable SHA-256, file/product version, Authenticode status/signer, OS build, architecture, shell, and package/source identity capture for runtime manifests;
- Windows Service installation and lifecycle;
- resource leases for files, services, ports, repositories, browser profiles, and mutation targets;
- `WindowsLocalWorkspace` behind the common workspace contract;
- SSH and Docker workspace adapters mapped into the same contract.

General host work must not require a configured Git repository.

### Exit gate

Windows execution is truthful, unrestricted, durable, recoverable, and controllable through the canonical task and workspace contracts.

---

## Phase 4 — Unified capability broker and Hermes H2

### Deliverables

- provider registry and provider manifests;
- capability search, describe, invoke, cancel, health, reload, resource, and prompt operations;
- atomic catalog generations;
- per-operation schema hashes;
- stale-schema rejection;
- provider capacity and health reporting;
- large-result spill to artifacts;
- compatibility adapters for existing domain gateways;
- provider-neutral client discovery.

### Hermes H2 completion

- service supervision;
- worker replacement and restart adoption;
- health and readiness;
- concurrent session isolation;
- controller and worker modes;
- public routing through the capability broker;
- persisted provider, catalog, schema, argument, and result identities;
- provider-level cancellation;
- last-known-healthy catalog retention.

Hermes is an accepted strategic integration. It may act as a connected controller, a specialised worker, and an aggregator for Hermes built-ins, plugins, and external MCP servers. It does not replace Soma’s canonical task, evidence, or memory authority.

### Gateway rule

Do not add Docker MCP Gateway, Microsoft MCP Gateway, or another gateway by default. Pilot one only when there is a concrete packaging, profile, remote-routing, multi-session, or deployment problem that Soma’s broker should not solve itself.

### Exit gate

Any supported controller can progressively discover and durably invoke native, Hermes, plugin, and external MCP capabilities without loading a full catalog or creating a second authority.

---

## Phase 5 — Live repository knowledge, skill plane, knowledge workspace, temporal context graph, and deterministic context

### 5.1 Live repository wiki

The existing `RepoWikiService` remains the publication engine because it already provides:

- immutable generations;
- atomic `CURRENT.json`;
- refresh locking;
- incremental scan/reuse;
- source-generation and stale tracking;
- hash verification;
- previous-generation readability;
- detection of source changes during refresh.

Add missing orchestration:

- Soma-owned recursive repository-watcher adapter, initially backed by `watchfiles`;
- normalization of watcher notifications into low-latency repository-change hints;
- debounced and coalesced changed paths;
- durable repository-change journal with monotonic event IDs and cursor-based reads;
- controller-visible events for change detection, refresh queueing, refresh start, generation publication, refresh failure, reconciliation, and watcher degradation;
- one refresh queue and worker per repository;
- desired generation and pending changed paths persisted durably;
- incremental refresh through the existing service;
- loop until indexed generation catches desired generation;
- startup reconciliation;
- periodic manifest/hash reconciliation for shutdown gaps, missed events, overflow, and watcher failure;
- stale-aware reads that serve the last complete generation and queue refresh;
- failure events and readiness visibility.

The watcher is never repository authority. The live filesystem, source hashes, and published repository generations remain authoritative. Watcher events are hints that cause Soma to inspect and reconcile the repository. The public change stream must remain Soma-owned so controllers and the future Cortana dashboard do not depend on a watcher-specific API or direct database access.

Exclude:

```text
.git/
.soma/wiki/
.claude/worktrees/
.codex-tmp/
virtual environments
caches
artifacts
generated media
credentials
secrets
```

Do not modify Git, Git configuration, or Git fsmonitor.

### Windows watcher decision

Use `watchfiles` as the initial embedded Windows-first notification source behind a Soma-owned watcher adapter. This choice minimizes integration and packaging cost while preserving replacement freedom. `watchfiles` supplies only recursive change notifications; it does not own repository truth, durable generations, refresh state, or public event semantics.

Retain these as measured replacement or recovery candidates rather than current dependencies:

- native `ReadDirectoryChangesW` when direct Windows control demonstrates a material correctness or performance advantage;
- Watchman when repository scale, daemon-based clocks, or recrawl behavior justifies its additional service and packaging boundary.

Acceptance must cover:

- create, modify, rename, and delete;
- burst coalescing;
- durable event ordering and cursor continuation;
- overflow or missed-event reconciliation;
- watcher shutdown or failure followed by hash/manifest recovery;
- restart with pending refresh and unpublished change events;
- source changes during generation;
- refresh failure before publication;
- no indexing of excluded paths;
- controller-visible watcher degradation and refresh status;
- bounded idle and refresh cost;
- clean adapter replacement without changing public repository-event or generation contracts.

### 5.2 Structural and derived project knowledge graphs

Adopt Tree-sitter as the first low-level candidate for deterministic structural extraction of:

- definitions and symbols;
- imports;
- calls;
- inheritance;
- block boundaries;
- cross-file relationships;
- incremental changed-file parsing.

Pilot the exact `Graphify-Labs/graphify` project as a derived, read-only project knowledge graph. Its useful reference patterns include:

- deterministic local AST extraction for code;
- one graph spanning code, documentation, configuration, schemas, and selected media;
- machine-readable `graph.json`, human-readable reports, and an interactive graph view;
- community and high-connectivity-node discovery;
- path, neighbour, explanation, rationale, and impact queries;
- explicit distinction between facts extracted from source and relations inferred during graph construction;
- MCP access for bounded graph traversal rather than loading the complete graph into controller context.

Every graph node and edge exposed through Soma must carry source class and provenance, including at minimum:

```text
EXTRACTED
INFERRED
AMBIGUOUS
```

For code, prefer deterministic local extraction. Semantic passes over documents, PDFs, images, audio, or video must record the model/provider, source digest, extraction revision, and confidence. Inferred or ambiguous relations must never be presented as equivalent to exact source facts.

Add Soma-owned graph contracts for:

```text
neighbours
path
explain
subsystem
rationale
impact
```

The repository watcher and durable source-generation journal should drive incremental graph refresh. Each imported graph generation must be tied to the repository source generation, indexed file hashes, Graphify revision, extraction configuration, and graph schema version. Startup and periodic reconciliation must detect stale, partial, or missed updates.

Graphify remains a replaceable derived index. `RepoWikiService`, the live repository, source hashes, and Soma evidence remain authoritative. Soma must re-ground useful graph answers to exact files, lines, symbols, documents, generations, and evidence references. Graphify's interactive graph may inspire the future Cortana interface, but controllers and the dashboard must use Soma-owned query and event contracts rather than depend directly on `graph.html`, `graph.json`, or a Graphify-specific API.

### 5.3 Skill plane

Skills are a first-class Soma plane, not merely documents stored in the knowledge workspace. The knowledge workspace is the owner-facing authoring and review surface; Soma owns promoted skill identity, immutable versions, validation evidence, task binding, invocation provenance, supersession, and rollback.

Support portable `SKILL.md`-style packages and compatible recipes from:

- project roots;
- user roots;
- bundled Soma roots;
- Hermes roots;
- future compatible provider roots;
- knowledge-workspace drafts exported through a provider-neutral package contract.

Use deterministic precedence:

```text
task-pinned version
project scope
user scope
bundled Soma scope
provider-imported scope
```

Conflicting IDs must not be silently merged or overwritten. Index metadata before loading full content:

- stable skill ID;
- name and description;
- skill type;
- version and digest;
- source and source revision;
- project/user/provider scope;
- platform requirements;
- required capabilities;
- declared inputs and outputs;
- resources and dependencies;
- deterministic steps where applicable;
- validation status;
- promotion, supersession, and rollback references.

Distinguish at least:

- instruction skills for reasoning and domain guidance;
- capability recipes for ordered typed-tool use;
- workflow templates for durable multi-step execution;
- context skills for deterministic knowledge selection and formatting;
- evaluator skills for acceptance and evidence review;
- transformation skills for deterministic artifact conversion.

Use the lifecycle:

```text
draft
→ candidate
→ validated
→ promoted immutable version
→ active
→ superseded or withdrawn
```

A freely editable knowledge-workspace note is never an active runtime version. Promotion creates an immutable, content-addressed package with validation evidence, capability compatibility, source provenance, and a rollback target. A running task binds the exact skill ID, version, digest, resolved dependencies, and selected resources; later workspace edits or promotions cannot alter that task silently.

Skill selection may be explicit or assisted, but it must be explainable and constrained by scope, capability availability, platform compatibility, version requirements, task objective, and owner preference. Record why each skill was selected. Skill dependencies must be declared and resolved as a bounded acyclic graph; reject missing dependencies, cycles, ambiguous providers, and incompatible versions.

Skill prose is instruction input; it is never executed directly. Consequential actions still pass through typed Soma capabilities, providers, tasks, runs, and evidence contracts.

Add a Soma-owned skill-learning projector over canonical task and run evidence:

```text
task outcomes and evidence
→ recurring success or friction analysis
→ proposed lesson or candidate skill revision
→ validation and comparison
→ explicit owner promotion
```

Use Agent Fleet and similar systems as architecture references for human-readable task/run records, reflection over accumulated history, and proposals for reusable skills. Do not adopt their task runtime, scheduler, memory authority, or agent plane wholesale. Soma may generate candidate skill packages and suggested revisions, but it must never self-modify an active skill or promote a candidate without explicit owner acceptance.

The skill plane must retain:

- task and run evidence that motivated a candidate;
- test or dry-run evidence;
- declared input/output validation;
- capability and platform checks;
- invocation history and outcome metrics;
- supersession and withdrawal reasons;
- complete portable export independent of the selected knowledge-workspace provider.

### Skill-plane exit gate

A controller can deterministically discover, select, bind, and invoke a versioned skill through Soma capabilities; task execution retains immutable skill bindings; workspace edits cannot silently alter behavior; skill proposals are evidence-linked and owner-promoted; older versions remain replayable; and the complete skill corpus can be exported without dependence on one controller, agent runtime, or knowledge-workspace product.

### 5.4 Canonical memory and knowledge workspace

Soma requires an owner-readable knowledge workspace for decisions, memories, lessons, project knowledge, procedures, and skill authoring. The workspace provider is selected through a bounded pilot; Anytype is the primary graph-native candidate and a plain Markdown/JSON representation is the mandatory portable baseline. Obsidian, SiYuan, or another compatible provider may be evaluated without changing Soma contracts.

The knowledge workspace is the human-facing authoring, browsing, annotation, and correction surface. It must not own operational task state, run state, evidence identity, promoted skill versions, or the only copy of machine-critical provenance.

Soma-owned canonical records retain:

- task and run summaries;
- accepted owner decisions and rationale;
- reusable procedures and promoted skill references;
- artifact lineage;
- child summaries;
- repository/workspace snapshots;
- supersession, expiry, and validity metadata;
- confidence and authority class;
- exact source and evidence references;
- workspace object IDs and export digests where applicable.

Every knowledge-workspace adapter must support deterministic import or export, stable identity mapping, change detection, provider removal, and full reconstruction of Soma-owned indexes. Workspace graph links are useful human-authored relationships, but they do not silently override canonical task, evidence, skill, or repository records.

### 5.5 Temporal context graph

Graphiti is selected as the initial temporal context-graph provider for Phase 5 rather than deferred as an unspecified later experiment. Its role is to strengthen continuity before broad delegation and scheduling by connecting changing facts, decisions, task outcomes, conversations, projects, people, skills, and evidence over time.

Graphiti is a derived intelligence layer, not a competing memory authority. Soma owns the ingestion journal, canonical entity IDs, accepted-fact policy, source authority, provenance, exports, rebuild procedure, and public query contracts. Graphiti may index accepted owner knowledge, selected conversation episodes, canonical task/run summaries, skill-learning evidence, repository decisions, and knowledge-workspace records. It must never become the sole copy of an important fact.

Use shared Soma entity identities so one concept may map safely across systems:

```text
Soma canonical entity ID
├── knowledge-workspace object ID
├── Graphiti entity or episode ID
├── Graphify project node ID
├── task and run IDs
├── repository file or symbol reference
└── evidence reference
```

The authority split is:

- live repository, source hashes, and `RepoWikiService` generations for repository truth;
- canonical task, run, evidence, skill, and structured-memory stores for operational and machine-critical truth;
- accepted owner records in the knowledge workspace for human-authored knowledge;
- Graphify for derived project structure and cross-source project relationships;
- Graphiti for derived temporal context, relationship retrieval, superseded facts, and historical continuity.

Add Soma-owned temporal-context contracts for at least:

```text
current_facts
fact_history
related_context
why
superseded_by
source_episodes
context_subgraph
```

Every returned fact or relationship must include authority class, source references, temporal validity, confidence where inferred, and whether it is accepted, derived, superseded, or disputed. Inferred Graphiti relationships must not be written back into the knowledge workspace as owner-authored facts. They may be published as proposals for review.

Graphiti ingestion must be incremental and durable. Store source episode identity, source digest, ingestion revision, extraction provider/model where used, graph schema version, processing status, and retry state. Startup and periodic reconciliation must recover missed or partial ingestion. Complete export and rebuild from Soma-owned sources are mandatory.

The Phase 5 pilot corpus begins with:

- accepted architecture and owner decisions;
- roadmap and task-history transitions;
- canonical task summaries and meaningful outcomes;
- skill proposals, promotions, failures, and supersession;
- selected project and preference memories;
- exact evidence and workspace-source links.

Promotion requires proving that the temporal graph improves retrieval of current versus superseded facts, preserves source provenance, survives restart and provider loss, exports completely, rebuilds deterministically enough for its role, and provides enough value to justify its backing-service and model costs.

Mem0 may still be studied for narrow preference or retrieval use, but it must not duplicate the temporal-context authority or create another competing memory plane. Do not adopt Letta, Zep, or another agent platform as the primary task or memory authority.

### 5.6 Context packets

Build deterministic, byte-budgeted context packets containing:

- objective and constraints;
- current checkpoint;
- selected immutable skill versions;
- current accepted decisions and relevant superseded history;
- a bounded Graphiti context subgraph with provenance;
- relevant knowledge-workspace records;
- repository/workspace identity and Graphify references;
- child summaries;
- exact evidence references;
- source freshness and temporal-validity metadata.

Context construction must query through Soma-owned contracts. Controllers must not depend directly on Anytype, Graphiti, Graphify, or their private storage schemas. Do not persist an entire controller conversation as a substitute for durable task context.

### Exit gate

A controller can resume complex work from a compact, source-linked packet; repository knowledge refreshes automatically; structural and temporal answers are provenance-grounded; current and superseded decisions are distinguished correctly; the knowledge workspace remains replaceable; and Graphiti can be disabled, exported, rebuilt, or replaced without losing canonical knowledge or operational continuity.

---

## Phase 6 — Project decomposition, agent swarms, parallel work, integration, and optional execution backends

### Owner outcome to accepted project plan

ChatGPT, acting as executive controller, can turn one owner-level outcome into a versioned project plan containing:

- product objective and acceptance criteria;
- architecture and major decisions;
- milestones and work packages;
- typed task and dependency graph;
- specialist roles and capability requirements;
- repository, service, environment, artifact, and deployment boundaries;
- validation and integration strategy;
- budgets, concurrency, and checkpoint rules.

The plan is durable and revisable. Replanning creates a new generation with explicit supersession; it does not erase completed work or silently reinterpret active assignments.

### Child tasks and swarm assignments

An accepted plan may create child tasks with:

- required `project_id` and work-graph position;
- objective, acceptance criteria, and dependency references;
- project-scoped context packet and selected skills;
- specialist role and candidate agent-worker requirements;
- isolated workspace or worktree;
- expected work products and output schema;
- validation, review, and integration requirements;
- resource and usage budgets.

ChatGPT may decompose and revise the work. Once the owner outcome and plan boundaries are established, Soma may instantiate ready child tasks, route them to compatible workers, retry or reassign failed work, and advance satisfied dependencies without asking Arash to approve every ordinary step. Soma must not invent unrelated product goals or silently cross project boundaries.

### Agent-worker adapters

Initial worker families include:

- Codex CLI adapter;
- Claude Code adapter;
- Hermes agent-worker adapter;
- native deterministic execution;
- capability invocation worker;
- browser or desktop agent worker;
- deterministic workflow worker;
- external-coder export and import compatibility;
- optional remote agent or external execution backend.

Each adapter must prove start, progress, checkpoint, input, cancellation, restart reconciliation, result capture, workspace isolation, identity provenance, and clean removal. Worker-specific strengths remain discoverable so ChatGPT can choose a coding implementer, researcher, reviewer, tester, browser specialist, deployment specialist, or other role deliberately.

### Swarm coordination

Generalize current parallel groups into a project-aware coordination engine with:

- dependency-aware ready queues and critical-path visibility;
- capability, role, health, cost, and capacity-aware routing;
- independent agent sessions, leases, evidence, cancellation, and budgets;
- explicit artifact ownership and producer/consumer links;
- structured progress, handoff, review, and completion summaries;
- dynamic reassignment and replacement without losing task identity;
- restart adoption and reconciliation of live agent processes;
- detection of stale assignments, duplicate work, blocked dependencies, and orphan sessions;
- controller-visible reasons for every assignment and replan;
- portfolio isolation so simultaneous projects cannot contaminate one another.

Capacity and budget are resource management, not authorization.

### Workspace and worktree isolation

For repository work:

- reserve a repository and mutation scope;
- create one task- or agent-owned worktree where parallel mutation requires it;
- bind project, task, agent session, base commit, branch, and workspace identity;
- keep unrelated agents out of the same mutable worktree;
- exclude temporary worktrees from canonical wiki/search unless queried explicitly;
- preserve failed work for inspection;
- record diffs, generated artifacts, tests, and provenance;
- detect overlapping changes and integration conflicts;
- clean up only after result acknowledgement and evidence retention.

### Review, validation, and integration

Agent output is not automatically accepted because an agent reports success. Support independent roles and gates for:

- implementation;
- test generation and execution;
- code and architecture review;
- security, dependency, and licence review where relevant;
- UI or browser verification;
- merge and integration planning;
- build, deployment, and smoke validation.

Soma records proposed changes and evidence. ChatGPT may accept, revise, reject, or delegate corrective work. Integration into a canonical branch, release, environment, or deployed product occurs only through the project integration contract and remains traceable to producing tasks and agents.

### Workflows

Support:

- typed DAG steps and graph-derived readiness;
- parallel ready nodes;
- retries, timeouts, and worker reassignment;
- compensation;
- explicit uncertainty;
- `awaiting_controller` for strategic judgment rather than routine execution;
- submit input;
- continue, revise, replan, and retry-step commands;
- stable project, task, agent, artifact, and evidence IDs across recovery.

Study mcp-agent and LangGraph for patterns, but keep project plans, workflow definitions, assignments, and task identity Soma-owned.

### Temporal pilot

Only after the execution-backend contract and canonical task plane are stable:

- run one isolated long-running workflow on Temporal;
- persist the Soma task-to-workflow mapping;
- prove safe process-kill recovery;
- prove no duplicate evidence publication;
- prove cancellation and checkpoint/input propagation;
- prove clean rollback to the native backend.

Temporal is promoted only if measured savings and durability benefits exceed the operational cost of running a second execution service.

### Exit gate

From one owner-level project objective, ChatGPT can create and revise a durable work graph, assign multiple isolated specialist agents, run independent and dependent work in parallel, recover or replace workers, detect conflicts and project leakage, validate and integrate their outputs, and return a coherent tested project state with exact provenance. The same controller can supervise multiple simultaneous projects without confusing their tasks, repositories, contexts, agents, artifacts, or decisions.

---

## Phase 7 — Browser, desktop, and multimodal providers

### Deterministic browser baseline

Use Playwright as the first candidate through an isolated provider or MCP worker.

Required contract:

- create and recover session;
- list pages;
- navigate;
- inspect DOM and accessibility state;
- interact;
- bounded script execution;
- screenshot;
- download and upload;
- wait;
- cancel owned activity;
- close;
- publish evidence artifacts.

Soma owns browser-profile leases, task identity, evidence descriptors, and final result publication.

### Higher-level browser pilots

Stagehand may be layered above Playwright for volatile sites where semantic action discovery and extraction outperform deterministic selectors.

Every Stagehand result must retain:

- schema-validated output;
- raw DOM or accessibility evidence where available;
- screenshot fallback;
- controller-visible uncertainty.

Use browser-use only as a tightly isolated experiment if Playwright plus Stagehand cannot satisfy a measured need. Do not adopt a hosted browser/memory control plane by default.

### Desktop provider

Windows-first adapters expose:

- displays and windows;
- screenshots;
- accessibility snapshots;
- pointer;
- keyboard;
- focus;
- wait;
- cancellation;
- session recovery and close.

### Multimodal artifacts

Generalize evidence descriptors for:

- images;
- PDFs;
- audio;
- video;
- archives;
- downloads;
- arbitrary binary files.

Compact descriptors are returned by default. Content is retrieved explicitly.

### Exit gate

A connected controller can operate browser and Windows desktop applications with durable ownership, exact cancellation, source-linked evidence, and compact artifact retrieval.

---

## Phase 8 — Durable scheduling, continuity, and return delivery

### Canonical scheduler model

Support:

- one-shot schedules;
- recurring schedules;
- timezone and DST correctness;
- pause, resume, update, remove, and trigger-now;
- history;
- deterministic missed-run policy;
- atomic attempt claiming;
- restart deduplication;
- condition-watch evaluation;
- task or workflow templates.

Schedules launch canonical tasks. They do not start a hidden general reasoning loop.

When new judgment is required, the task transitions to `awaiting_controller`.

### APScheduler boundary

APScheduler may supply trigger calculation, recurrence handling, and lightweight wake-up mechanics. Soma remains authoritative for:

- schedule identity;
- schedule state;
- attempt history;
- claim ownership;
- launched task identity;
- missed-run and deduplication policy.

Do not let an APScheduler job store become a second public schedule authority.

### Delivery outbox

Persist notification and return-delivery attempts separately from task outcome.

Polling and task discovery remain authoritative because an MCP server cannot always initiate a new controller turn.

Adapters may include:

- PulseSender/browser delivery;
- file;
- webhook;
- future supported notification channels.

Delivery failure never changes task outcome.

### Exit gate

Deterministic work continues unattended, survives restart, requests controller input when needed, and remains discoverable even when notification delivery fails.

---

## Phase 9 — Linux and macOS adapters

This phase follows a usable Windows implementation.

### Linux

- direct execution;
- process identity and process-group cancellation;
- unrestricted filesystem;
- systemd service lifecycle;
- workspace provider;
- browser provider;
- accessibility/input provider where supported;
- restart reconciliation.

### macOS

- direct execution;
- process identity and process-group cancellation;
- unrestricted filesystem;
- launchd service lifecycle;
- workspace provider;
- Accessibility/CGEvent desktop provider;
- browser provider;
- restart reconciliation.

### Exit gate

Windows, Linux, and macOS expose the same canonical task, capability, evidence, scheduler, and workspace contracts for the features they truthfully support.

---

## Phase 10 — Observability, packaging, licensing, and final legacy removal

OpenTelemetry instrumentation begins earlier as an enabling capability. This phase completes the operator and distribution story.

### Observability

Expose compact structured:

- liveness and readiness;
- provider and worker health;
- task and workflow health;
- leases and reconciliation state;
- storage use;
- diagnostic bundles;
- trace and request IDs;
- retry, latency, and failure metrics;
- external-backend mappings.

Use an OpenTelemetry collector or compatible export path. Do not make another dashboard mandatory.

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
- `upgrade`;
- rollback;
- configuration migration.

### Apache-2.0 release work

Before public distribution:

- add the actual Apache-2.0 `LICENSE`;
- add `NOTICE` where required;
- add or generate `THIRD_PARTY_NOTICES.md`;
- preserve upstream notices and changed-file markers;
- scan direct and transitive dependencies;
- generate SPDX or CycloneDX SBOM;
- inspect final wheels, installers, archives, containers, and bundled binaries;
- archive licence-scan and release evidence.

Candidate tooling includes Licensee for root sanity checks, ScanCode for file-level scanning, ORT for dependency and report workflows, FOSSology for ambiguous reviews, and License-Eye or an equivalent CI gate. Tool adoption must remain proportionate to the release workflow.

### Final cleanup

After migration and acceptance, remove:

- legacy job manager;
- duplicate supervisors;
- duplicate local-coding state;
- obsolete permission and approval machinery;
- unused local general-reasoning paths;
- synchronous coding-agent bypasses;
- duplicate schema/catalog paths;
- dashboard and service TUI after diagnostic migration;
- server monkey patches;
- failed external pilots and abandoned adapters.

Domain systems such as Trading Lab remain optional providers rather than core lifecycle owners.

### Exit gate

A fresh installation exposes a reproducible, compact, model-independent runtime without duplicate lifecycle authorities, hidden policy gates, abandoned interfaces, or unresolved third-party licensing obligations.

---

## 11. Testing and acceptance policy

Every implementation batch includes validation proportionate to the changed behavior.

### Core requirements

- focused unit and regression tests;
- adjacent integration tests;
- real Windows process/filesystem tests where platform semantics matter;
- durable live validation for restart, cancellation, browser, scheduler, or provider work;
- `git diff --check`;
- selected-file local commit;
- no push unless explicitly requested.

### Permanent crash-window coverage

Test relevant boundaries including:

- server restart while a detached worker remains active;
- worker death while a child process remains active;
- process-launch failure after durable record creation;
- crash after claim before launch;
- crash after launch before child attachment;
- concurrent reconcilers;
- cancellation racing completion;
- PID reuse;
- duplicate idempotency request;
- task command against a stale state version;
- external backend recovery;
- result publication after backend retry;
- source changes during wiki refresh;
- watcher overflow or missed events;
- refresh failure before atomic publication;
- browser worker death with a leased profile;
- coding-agent process death before and after checkpoint publication;
- agent-session restart or replacement without project/task identity drift;
- runtime component upgrade while an attempt is active;
- requested worker or model falling back to a different resolved runtime;
- missing old executable, lockfile, container digest, or runtime bundle during recovery;
- manifest tampering, hash mismatch, or attempted in-place manifest mutation;
- deterministic replay claim rejected for a non-deterministic model-agent session;
- two simultaneous projects with similar names, files, stacks, or objectives remaining isolated;
- stale assignment after plan revision;
- duplicate agent work against one task;
- overlapping worktree edits and integration conflicts;
- artifact produced for the wrong project or task being rejected;
- dependency completion racing project replanning;
- scheduler restart before and after attempt claim;
- delivery failure after terminal task completion.

### Integration-specific acceptance

An external provider must prove:

- exact version and schema identity;
- runtime-manifest capture of requested and actual resolved identity;
- compatibility behavior across adapter, executable, schema, and model changes;
- health and readiness;
- bounded timeouts;
- cancellation behavior;
- restart or failure behavior;
- artifact and evidence publication;
- no secret leakage;
- no hidden canonical authority;
- clean disable/remove path;
- licence and notice compliance.

### Documentation-only work

For prose-only roadmap changes:

- inspect the scoped diff;
- run `git diff --check`;
- verify only intended documentation files changed;
- commit only selected documentation files;
- preserve unrelated dirty and tool-owned evidence;
- do not run the full test suite unless explicitly requested.

Never claim validation that was not run.

---

## 12. Documentation and achievement discipline

Use documents for distinct purposes:

- `AGENTS.md`: permanent owner decisions and working rules;
- `PLANS.md`: concise current active lane and immediate decisions;
- this roadmap: strategic architecture, order, and exit gates;
- achievement records: completed milestones, measurements, commits, and legacy preservation;
- audit reports: evidence and recommendations;
- pilot evidence: bounded observations and promotion decisions;
- licensing policy: third-party compatibility and release obligations.

When a milestone completes:

1. preserve its outcome and permanent invariants;
2. move detailed chronological evidence to an achievement record;
3. remove stale “sole active priority” wording;
4. record the next owner-selected lane;
5. do not delete historical evidence merely to shorten the plan.

Before retiring old systems, create or update a legacy-achievement and migration record describing what they enabled and where their useful behavior moved.

---

## 13. Recommended next bounded batch

The originally recommended non-destructive Phase 1 slice was implemented and accepted as **TASK-1 — Canonical Task Plane Foundation** on 2026-07-25:

- canonical task schema and ordered transactional migration — done;
- controller-neutral task states — done, complete vocabulary, no approval state;
- mapping for one existing durable run type — done, the durable local command (`executable_profile`) path;
- compact task status and result projection — done, referencing the authoritative run result and hashes;
- one version-guarded command — done, `task_action.cancel`;
- adapter and migration tests — done, plus crash-window and compatibility coverage;
- no legacy deletion — honoured;
- no Temporal, browser, memory sidecar, or gateway integration in the same batch — honoured.

The next recommended batch is therefore the **remainder of Phase 1**:

- map a second existing execution type (workflow, supervisor, SSH, or command group) onto the same task contract;
- add the remaining version-guarded commands (`steer`, `input`, `pause`, `resume`, `retry`);
- exercise controller checkpoints and `awaiting_controller` end to end;
- add an explicit repair path for `recovery_pending` and `uncertain` tasks.

This recommendation is not an activation. Arash selects the batch.

A small cross-cutting observability trace may be included only when it directly helps validate the task path and does not expand scope into a full telemetry project.

---

## 14. Non-goals

Soma will not become:

- a clone or fork of ChatGPT, Claude, Hermes, OpenClaw, OpenHands, or another agent product;
- dependent on one controller vendor;
- a second mandatory user interface;
- a public unauthenticated execution service;
- a system that executes skill prose directly;
- an architecture with competing canonical task, memory, evidence, repository, or schedule stores;
- a wholesale Temporal, LangGraph, Letta, Mem0, Graphiti, or Graphify migration;
- a platform that loads arbitrary unreviewed third-party plugins into the kernel;
- an unscoped peer-agent swarm that shares one mutable workspace, loses project identity, invents unrelated objectives, or allows workers to overwrite the executive project plan;
- a system that modifies Git or Git configuration to maintain the repository wiki;
- an Apache-target codebase containing copied GPL/AGPL implementation code;
- a monolithic rewrite that discards proven durability or historical evidence;
- a project that rejects useful external components merely because they originated in a broader agent product.

---

## 15. Final strategic sequence

```text
Closed       CF1 Chat Footprint and Progressive Disclosure
Phase 1      Canonical task plane
Phase 2      Application container, lifecycle consolidation, and legacy permission removal
Phase 3      Windows-first unrestricted host execution and workspace abstraction
Phase 4      Unified capability broker and Hermes H2
Phase 5      Live repository knowledge, skill plane, knowledge workspace, temporal context graph, and deterministic context
Phase 6      Project decomposition, agent swarms, parallel work, integration, and optional backends
Phase 7      Browser, desktop, and multimodal providers
Phase 8      Durable scheduling, continuity, and return delivery
Phase 9      Linux and macOS adapters
Phase 10     Observability, packaging, licensing, and final legacy removal
```

The sequence is intentionally conservative:

- replacement task semantics exist before destructive cleanup;
- the existing durable engine remains primary until a measured optional-backend pilot proves value;
- Windows host execution becomes coherent before cross-platform expansion;
- Hermes and external tools enter through one provider model;
- repository knowledge becomes live before derived project and temporal graphs are trusted;
- the skill plane, owner knowledge workspace, temporal context graph, and deterministic context exist before broad delegation;
- canonical project identity and the work graph prevent cross-project confusion before agent swarms expand;
- project decomposition, agent-worker, review, integration, and workflow semantics exist before unattended scheduling expands;
- Playwright supplies deterministic browser primitives before higher-level browser agents;
- observability begins early but distribution hardening and final cleanup happen after migrations are proven;
- external components save implementation time without taking ownership of Soma’s identity or history.

The architectural destination is not “Soma implements everything itself.”

It is:

> **ChatGPT remains Arash's executive brain for intent, planning, delegation, review, and replanning; Soma owns the durable project graph, identity, isolation, execution, evidence, and orchestration; and replaceable specialist agents provide implementation and operational capability without losing track of which project, task, workspace, artifact, or decision belongs where.**
