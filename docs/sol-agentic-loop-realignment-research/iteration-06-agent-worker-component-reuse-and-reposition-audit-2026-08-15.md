# Iteration 6 - Agent/Worker Component Reuse and Reposition Audit

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected: `fef45702367ecf1015a1ab95139547f172ab588f`

## Scope

Iterations 1-5 established a corrected baseline:

- normal Chat should gain a lightweight durable Sol control loop;
- Work keeps its own native agentic reasoning/planning layer;
- canonical Task remains external/action execution truth;
- the minimal Chat loop currently needs only a tiny objective record, loop-to-Task membership with last-consumed Task-observation fingerprints, and an idempotent loop command journal;
- no external reasoning backend is required for the core loop.

Iteration 6 audits the expensive Agent/Worker implementation and nearby legacy orchestration code against that corrected architecture.

The purpose is **not** to decide what code to delete today. It is to determine which components are:

- KEEP;
- MOVE / REPOSITION;
- RENAME;
- MAKE OPTIONAL;
- DEPRECATE;
- REMOVE eventually;

while preserving historical evidence and avoiding a destructive “throw away Agent/Worker” reaction.

No implementation or cleanup is authorized by this document.

## Hard constraints

No runtime/service restart, Company activation, reasoning-provider activation, Codex use, provider generation, production config change, push, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

Company remains frozen.

An unrelated working-tree file, `soma/repo_patch_repair.py`, was present during this iteration and was left untouched.

Classification labels:

- **REPOSITORY FACT** - current source/docs/Git evidence.
- **OWNER REQUIREMENT** - explicit owner direction.
- **INFERENCE** - supported architectural classification, not implementation authority.
- **OPEN QUESTION** - intentionally unresolved.

---

# 1. Executive finding

**INFERENCE**

The Agent/Worker programme is not mostly wasted work.

Its durable lower layers are generally strong and often align well with the corrected Sol-centric architecture:

```text
canonical identity
persist-before-effect
backend abstraction
recovery / uncertainty
process ownership
capability scoping
bounded evidence
provenance
fan-out / fan-in mechanics
```

The architectural drift is concentrated higher up:

```text
semantic task classification
planning/routing heuristics
local-model reasoning
reasoning worker as semantic actor
reasoning backend as a core architectural axis
Supervisor / LocalAgent deciding next action
Company admission depending on reasoning-provider work
```

So the likely cleanup shape is:

```text
KEEP the nervous system.
REMOVE or isolate the accidental second brain.
```

That distinction should govern all later implementation planning.

---

# 2. Canonical Task plane

## Evidence

**REPOSITORY FACT**

The Task plane owns:

- stable Task identity;
- controller request idempotency/hash conflict detection;
- backend identity/reference;
- state/version CAS;
- commands;
- checkpoints;
- links;
- result/evidence references;
- recovery/uncertainty;
- compact public projections.

The Task store explicitly does not own process/evidence/result bodies.

## Classification

**KEEP - CORE.**

## Corrected role

Canonical Task is the durable identity for one action/execution attempt beneath either:

```text
normal Chat Sol loop
```

or:

```text
Work native agentic loop
```

Task must not become the user-goal/cognitive-loop identity.

## Important future change

The minimal Sol-loop work may need an atomic loop-to-Task ownership attachment, but that should extend/cooperate with Task reservation rather than fork Task execution semantics.

---

# 3. Generic `ExecutionBackend` / durable Run backend

## Evidence

**REPOSITORY FACT**

`soma/tasks/backends.py` defines a provider-neutral `ExecutionBackend` contract:

```text
reserve
start
query
cancel
result_reference
```

`DurableRunBackend` adapts the existing JobManager/RunStore engine rather than duplicating it.

## Classification

**KEEP - CORE.**

## Corrected role

This is exactly the sort of abstraction Soma needs:

```text
Task identity
 -> selected execution backend
 -> bounded observation/result reference
```

The interface itself does not imply a second reasoning model.

The core Sol loop should depend on this execution truth, not on a model-provider route.

---

# 4. RunStore / JobManager / durable execution

## Evidence

**REPOSITORY FACT**

`JobManager` / RunStore provide the mature durable execution plane:

- persisted launch identity;
- worker/process state;
- heartbeat and recovery;
- cancellation;
- external tools/providers;
- artifacts;
- result publication;
- compact polling projections;
- long-running execution;
- SSH/Cloudflare/Docker/local executable routes.

The public run surface already supports cheap unchanged polling via state version.

## Classification

**KEEP - CORE.**

## Corrected role

This is one of Soma's main reasons to exist. It should remain below canonical Task and the future lightweight Sol loop.

No cognitive semantics need to move into JobManager.

---

# 5. `awaiting_controller`, checkpoints, and interaction transitions

## Evidence

**REPOSITORY FACT**

The worker substrate provides:

- atomic non-terminal controller wait;
- durable checkpoint identity;
- exact context/evidence refs;
- acknowledged input/resume;
- stale-version protection;
- transport ambiguity handling;
- restart/recovery semantics.

## Classification

**KEEP - CORE MECHANIC.**

## Corrected role

Use it when one still-running Task genuinely requires controller/Sol input before the same action can continue.

Do **not** overload it for the goal-level case where a Task is already terminal and Sol needs to decide what to do next. The lightweight loop observation fingerprint handles that case.

---

# 6. Worker interaction substrate

## Evidence

**REPOSITORY FACT**

The interactive worker substrate deliberately avoids becoming another lifecycle authority:

- provider sessions are subordinate binding facts;
- messages are subordinate to Task/Run;
- payloads are references;
- commands bind to exact Task state versions;
- delivery is persist-before-send;
- unknown send outcome is preserved rather than blindly retried.

## Classification

**KEEP / REPOSITION AS OPTIONAL SPECIALIST INFRASTRUCTURE.**

## Corrected role

This is useful whenever a real subordinate provider/session exists, such as:

- optional external specialist agent;
- interactive coding/research provider;
- future provider session requiring steering/input.

The normal Chat Sol loop itself does not require a subordinate provider session.

---

# 7. Worker authority / capability broker

## Evidence

**REPOSITORY FACT**

`soma/worker_authority` implements a provider-neutral positive-capability authority system.

A worker principal is bounded by exact:

- ProjectScope resource/generation;
- Task/Run;
- optional session;
- role/mandate;
- expiry;
- operation hash;
- parameter contract;
- current Task state version.

Authorization revalidates scope and cancellation state every time.

The module explicitly says worker credentials do **not** create Task, Run, ProjectScope, provider-session, role, or protected-effect authority.

## Classification

**KEEP / REPOSITION - OPTIONAL SUBORDINATE-WORKER SECURITY INFRASTRUCTURE.**

## Corrected role

This is valuable if Soma allows any subordinate worker - reasoning or non-reasoning - to call Soma tools.

It should not be part of the normal Chat Sol-loop happy path because Sol already uses the owner/controller Soma surface.

Conceptually:

```text
Sol/Work owner surface
    !=
restricted subordinate worker surface
```

The worker authority work is therefore not evidence that workers should own reasoning. It is good containment if workers exist.

---

# 8. Isolated worker MCP gateway

## Evidence

**REPOSITORY FACT**

`soma/worker_gateway/transport.py` creates a separate authenticated FastMCP app with only:

```text
worker_capabilities
worker_invoke
```

It:

- does not reuse the owner/executive public gateway names;
- requires exact grant-bound invocation;
- has no name-based fallback;
- bounds parameters/results;
- redacts sensitive fields;
- does not directly expose protected mutation dispatch in the source-only package.

## Classification

**KEEP / MAKE OPTIONAL.**

## Corrected role

Retain as a safe tool interface for deliberately spawned/attached subordinate workers.

Do not expose or activate it merely to make normal Chat agentic.

It is an **authority boundary**, not a cognitive layer.

---

# 9. Worker process launch and containment

## Evidence

**REPOSITORY FACT**

`soma/worker_process` contains strong process ownership mechanics:

- executable identity verification;
- sanitized environment;
- Windows Job Object containment;
- root starts suspended and is contained before first instruction;
- KILL_ON_JOB_CLOSE;
- persist process identity before reporting ready;
- contain tree if identity/persistence becomes uncertain;
- descendant ownership evidence;
- no uncontrolled orphan worker after controller death.

The current stand-in launcher explicitly does not launch Codex or Claude.

## Classification

**KEEP - LOWER-LEVEL EXECUTION SAFETY.**

## Corrected role

Reusable for any local subordinate process whose process tree Soma owns.

This survives regardless of whether the process is:

- a coding specialist;
- retrieval worker;
- deterministic helper;
- future optional model runtime.

It does not belong in the simple loop unless a selected Task backend actually needs it.

---

# 10. Worker EvidenceSubmission contract

## Evidence

**REPOSITORY FACT**

`EvidenceSubmissionV1` is a bounded structured envelope that separates:

- producer claims;
- exact evidence/provenance;
- artifacts;
- uncertainty/blockers;
- usage;
- retrieval references;
- canonical Task identity.

It permits claim classes including observation, inference, recommendation, and negative finding.

## Classification

**KEEP / MAKE OPTIONAL - SPECIALIST EVIDENCE CONTRACT.**

## Corrected role

Use when a genuine specialist producer returns semantic claims that Sol must later inspect/adjudicate.

Examples:

- external research agent;
- optional reasoning specialist;
- independent verifier;
- bounded parallel scout.

Do **not** require every ordinary Soma Task result to become an EvidenceSubmission. Canonical Task/Run result/evidence references are already sufficient for the normal Sol loop.

This keeps the simple path small.

---

# 11. FanInV1

## Evidence

**REPOSITORY FACT**

FanIn is deterministic/mechanical:

- expected-unit coverage;
- missing/partial/blocked/uncertain unit accounting;
- exact submission hashes;
- exact structured fact-key conflicts;
- duplicate detection;
- provenance/retrieval pointers;
- bounded usage and size.

It explicitly does **not** decide which contradictory claim is true.

## Classification

**KEEP / MAKE OPTIONAL - TRUE PARALLEL SPECIALIST FAN-IN.**

## Corrected role

FanIn is useful when Sol or Work intentionally delegated several independent specialist units and wants one mechanically complete packet back.

It is not required for:

- one normal action;
- sequential `reason -> act -> observe -> reason`;
- long-running single Tasks;
- Work's own native subagent aggregation unless Soma independently owns those specialist outputs.

So FanIn survives, but it moves off the normal Chat critical path.

---

# 12. Parallel command groups

## Evidence

**REPOSITORY FACT**

`parallel_groups.py` provides durable exact-command fan-out:

- parent group identity;
- child Run reservation before launch;
- per-child idempotency key;
- concurrency ceilings;
- failure policy;
- aggregate status derived from child Run truth;
- refill/claim mechanics;
- cancellation support.

## Classification

**KEEP - DETERMINISTIC EXECUTION PRIMITIVE.**

## Corrected role

This is “more hands,” not “more minds.”

Sol can decide several independent mechanical actions are safe to run concurrently. Soma executes and reports them without creating reasoning workers.

This is exactly the sort of parallelism that should remain available even if every reasoning-worker route is disabled.

---

# 13. ReasoningSpec / reasoning backend protocol

## Evidence

**REPOSITORY FACT**

`soma/reasoning` contains strong provider-operation durability contracts:

- frozen assignment/context refs;
- output/tool/authority/provider-route hashes;
- explicit budgets;
- continuation policy;
- mutation policy;
- provider binding identity;
- send-boundary ambiguity;
- provider terminal claims;
- result/evidence publication;
- cancellation uncertainty.

The reasoning store persists subordinate provider facts and does not mutate canonical Task/Run/ProjectScope lifecycle directly.

## Classification

**REPOSITION + RENAME CANDIDATE + MAKE OPTIONAL.**

## Why the mechanics should survive

Persist-before-provider-send, exact provider binding, outcome-unknown handling, and bounded publication are valuable for any remote intelligent specialist.

## Why the concept should move

The word **reasoning** currently makes this look like Soma's core cognitive engine.

Under the corrected architecture it is better understood as something like:

```text
optional model specialist backend
optional intelligent-provider operation
specialist analysis backend
```

Exact naming is deferred.

## Important rule

The minimal normal-Chat Sol loop must have **zero dependency** on this package being enabled.

---

# 14. `TaskKind.REASONING` / `BackendKind.SOMA_REASONING`

## Evidence

**REPOSITORY FACT**

These became first-class canonical Task/backend values during G2 on 2026-08-12.

They let a model/provider operation itself become a canonical Task, with Task lifecycle reconciled from subordinate provider evidence.

## Classification

**RE-EVALUATE; LIKELY SUPERSEDE/RENAME OR CONFINE TO OPTIONAL SPECIALIST TASKS.**

## Reason

The problem is not that a specialist model operation can never be a Task. If Sol deliberately asks an external specialist to do bounded work, a canonical Task is a reasonable durable owner.

The problem is treating **reasoning** as the architecture that makes Chat agentic.

Therefore a later migration plan should distinguish:

```text
optional specialist intelligent Task
```

from:

```text
core Sol reasoning turn
```

The latter must never be represented as a subordinate backend Task merely to continue normal Chat.

Historical enum values/gates should probably be superseded compatibly rather than rewritten in place.

---

# 15. Codex repository reasoning backend/runtime

## Evidence

**REPOSITORY FACT**

The current production implementation behind the reasoning runtime is:

`CodexRepositoryReasoningBackend`

It uses Codex App Server repository integration and is gated by `reasoning.enabled`.

The backend is read-only, pins a committed source snapshot, disables provider-internal subagents, and publishes bounded evidence.

Production reasoning remains disabled.

## Classification

**MAKE OPTIONAL / PROVIDER-SPECIFIC SPECIALIST ADAPTER.**

## Owner boundary

**OWNER REQUIREMENT**

Codex may only be used after explicit owner authorization.

Therefore:

- core Soma/Chat loop must work with this code absent/disabled;
- no auto-routing from normal Chat to Codex;
- no “Chat mode means start reasoning backend” behavior;
- provider-specific Codex naming stays below a generic optional specialist interface.

The existing owner gate is useful and should not be weakened.

---

# 16. Hermes

## Prior repository finding

**REPOSITORY FACT**

The integrated Hermes companion is explicitly headless and rejects model-runtime initialization. Parallel Hermes workers are execution/tool concurrency, not independent reasoning minds.

## Classification

**KEEP - TOOL/EXECUTION BACKEND.**

## Corrected role

Hermes gives Sol/Work access to tools and external capabilities.

Do not promote integrated Hermes to a reasoning brain.

A separately configured model-backed Hermes instance could only be an optional specialist if intentionally designed/authorized later.

---

# 17. LocalAgentOrchestrator

## Evidence

**REPOSITORY FACT**

`soma/local_agent/orchestrator.py` classifies natural-language objectives using keyword heuristics and routes them to:

- commands;
- local model reasoning;
- long-run jobs;
- memory;
- policy;
- external coder;
- supervisor;
- local coding;
- dashboard.

It contains a `LOCAL_MODEL_REASONING` route and delegates semantic task classification/routing inside Soma.

## Classification

**DEPRECATE AS CORE ORCHESTRATOR; SALVAGE MECHANICAL ADAPTERS.**

## Reason

This is a historical “local agent decides what the user meant” layer.

That duplicates Sol's role directly.

Normal Chat does not need Soma to parse “fix / inspect / test / deploy” and decide which cognitive route to take. Sol already understands the request and can choose the appropriate Soma operation.

## Salvage candidates

- durable command adapters;
- audit helpers;
- report formatting;
- compatibility entry points if current users/tests depend on them.

Do not retain the natural-language classifier/local-model router as the canonical future path.

---

# 18. DurableProjectCommandRunner

## Evidence

**REPOSITORY FACT**

The durable command runner adapts legacy immediate-result commands onto canonical JobManager/RunStore execution.

It uses reviewed command IDs, repo resolution, timeout ceilings, and durable Runs.

## Classification

**KEEP TEMPORARILY / COMPATIBILITY ADAPTER; CONVERGE WHERE POSSIBLE.**

## Corrected role

The useful part is not “local agent reasoning.” It is a compatibility wrapper over durable command execution.

If direct canonical Task/Run gateways now cover the same use cases cleanly, later cleanup can retire duplicate wrappers after measuring consumers/tests.

---

# 19. Legacy `LongRunJobManager` under `soma/jobs`

## Evidence

**REPOSITORY FACT**

The older `LongRunJobManager` owns an in-memory `processes` map.

Its default path now blocks legacy execution with the explicit message:

> Legacy in-memory long-run execution is disabled because process ownership cannot survive manager recreation.

It tells callers to route unattended work through durable `JobManager` and `RunStore`.

## Classification

**DEPRECATE / RETIRE EXECUTION PATH.**

## Salvage candidates

- report-generation format if still useful;
- historical read compatibility;
- job profile definitions if any still have consumers.

The durable JobManager/RunStore path is the correct execution authority.

There is no reason for the Sol loop to revive the weaker job manager.

---

# 20. Supervisor

## Evidence

**REPOSITORY FACT**

Supervisor has its own lifecycle:

```text
inspecting
planning
validating_locally
needs_external_coder
needs_input
completed
...
```

`SupervisorFlow`:

- inspects;
- creates a plan;
- classifies whether external coding is needed via text heuristics;
- may use a local model to generate a plan summary;
- validates;
- chooses an external-coder handoff path;
- writes `next_recommended_action` and `question_for_chatgpt`.

## Classification

**DEPRECATE AS COGNITIVE/ORCHESTRATION AUTHORITY.**

## Why

It performs exactly the kind of planning/routing that should return to Sol.

The corrected loop should look like:

```text
Sol inspects result
Sol decides whether code work is needed
Sol chooses next Soma action
```

not:

```text
Sol -> Supervisor -> Supervisor plans/routes -> Sol reviews recommendation
```

## Salvage candidates

- durable validation execution;
- report generation;
- resume/report artifact formatting;
- perhaps inert handoff packaging.

Supervisor should be treated as a legacy compatibility lifecycle until later retirement/convergence analysis is complete.

---

# 21. External coder handoff

## Evidence

**REPOSITORY FACT**

The current external-coder package explicitly creates **inert artifacts only**.

Its model/docs state Soma does not:

- launch;
- supervise;
- select;
- route to

an external coding agent.

However the generator still uses keyword heuristics to decide whether a handoff is needed.

## Classification

**KEEP PACKET/CONTEXT GENERATION; REMOVE/DEPRECATE SEMANTIC ROUTING HEURISTICS.**

## Corrected role

If Sol/owner has already decided an external specialist is appropriate, Soma can produce a bounded, provenance-rich handoff artifact.

Soma should not infer from user prose that an external coder is needed.

Conceptually:

```text
Sol decision
 -> explicit generate_handoff
 -> inert artifact
```

This is compatible with Codex/Claude being optional and owner-controlled.

---

# 22. Workflow subsystem

## Evidence

**REPOSITORY FACT**

Workflow has its own lifecycle, worker lease/process, fixed step graph, child Run ownership, recovery, cancellation, and publication.

It is durable and robust, but predates canonical Task convergence and remains a second lifecycle authority.

## Classification

**REPOSITION AS EXPLICIT DETERMINISTIC WORKFLOW; LATER CONVERGENCE/LEGACY CLEANUP.**

## Corrected role

Workflow is useful when the controller already knows a fixed deterministic sequence that does not need fresh Sol judgment between every step.

It should not:

- create plans from semantic intent;
- become the normal Chat cognitive loop;
- decide when a changed observation requires replanning.

The useful recovery/cancellation/child-execution mechanics can remain while a later lane determines whether workflow steps should project into or migrate onto canonical Tasks.

---

# 23. Return loop / PulseSender artifacts

## Evidence

**REPOSITORY FACT**

`soma/return_loop` explicitly treats delivery separately:

```text
send_policy = external_pulsesender_only
soma_sends_messages = false
controls_browser = false
```

It provides:

- atomic report/prompt writes;
- readiness manifests;
- hashes/size/sensitivity checks;
- externally marked delivery status.

## Classification

**KEEP / OPTIONAL TRANSPORT ADAPTER CONTRACT.**

## Corrected role

Exactly as the owner clarified:

- not part of reasoning ownership;
- not required for the core Sol loop;
- optional convenience for waking/delivering later;
- manual wake-up/polling remains valid.

Atomic writer utilities are independently useful.

A future Chrome extension can consume equivalent durable continuation/report facts without changing loop architecture.

---

# 24. Memory / knowledge

## Prior finding

**REPOSITORY FACT**

Soma has durable project/knowledge/memory stores and is actively converging memory authority.

The local-agent legacy memory write path is already frozen in favor of canonical knowledge actions.

## Classification

**KEEP CANONICAL MEMORY/KNOWLEDGE; DEPRECATE DUPLICATE LEGACY MEMORY ROUTES.**

## Corrected role

Memory stores durable facts/decisions/context.

The Sol loop references memory where useful but does not rely on fuzzy memory retrieval to answer transactional questions such as whether a Task observation was already consumed.

---

# 25. Company / Mission / Plan / WorkPackage

## Boundary

**OWNER REQUIREMENT**

Company is frozen and this iteration does not alter it.

## Preliminary classification only

**OPEN QUESTION / LATER ITERATION.**

Company/Mission/Plan may still be valuable for explicit long-horizon organizational programmes.

But the current architecture contains admission paths that became entangled with reasoning-provider Tasks. Those relationships require a dedicated research iteration.

Nothing in the minimal Sol loop should depend on Company.

---

# 26. Component matrix

This matrix is provisional research output, not a removal plan.

| Component | Classification | Corrected role |
|---|---|---|
| Canonical Task | KEEP | Durable action/execution identity |
| RunStore / JobManager | KEEP | Durable process/external execution authority |
| ExecutionBackend protocol | KEEP | Backend-neutral execution seam |
| DurableRunBackend | KEEP | Default execution backend |
| Task checkpoints / `awaiting_controller` | KEEP | Running action waiting for Sol/controller input |
| Task result/evidence refs | KEEP | Observation/evidence source for Sol |
| Interaction substrate | KEEP / OPTIONAL | Interactive subordinate-provider sessions |
| Worker authority | KEEP / REPOSITION | Restricted capability grants for optional workers |
| Worker gateway | KEEP / OPTIONAL | Isolated subordinate-worker tool surface |
| Worker process containment | KEEP | Safe owned subordinate process trees |
| EvidenceSubmissionV1 | KEEP / OPTIONAL | Structured semantic specialist evidence |
| FanInV1 | KEEP / OPTIONAL | Mechanical aggregate for true parallel specialist work |
| Parallel command groups | KEEP | Deterministic execution fan-out |
| Reasoning backend lifecycle/store | REPOSITION / RENAME / OPTIONAL | Durable intelligent-provider/specialist operation mechanics |
| `TaskKind.REASONING` | RE-EVALUATE | Optional specialist Task at most; never Sol's own turn |
| `SOMA_REASONING` backend | RE-EVALUATE | Compatibility/optional specialist backend, not core axis |
| Codex repository backend/runtime | MAKE OPTIONAL | Explicitly owner-authorized specialist adapter |
| Hermes headless tool runtime | KEEP | Tool/execution capability, not reasoning brain |
| LocalAgentOrchestrator | DEPRECATE CORE | Semantic routing returns to Sol; salvage adapters |
| DurableProjectCommandRunner | KEEP/CONVERGE | Legacy compatibility over durable Runs |
| legacy LongRunJobManager | DEPRECATE | Durable JobManager/RunStore supersedes execution |
| Supervisor | DEPRECATE COGNITIVE ROLE | Salvage validation/reporting/handoff pieces |
| External coder packet generator | KEEP / REPOSITION | Explicit Sol-requested inert handoff; no semantic auto-routing |
| Workflow | REPOSITION / LEGACY CONVERGENCE | Explicit deterministic workflow only |
| Return-loop/PulseSender contract | KEEP / OPTIONAL | Delivery transport only |
| Canonical memory/knowledge | KEEP | Durable context/facts; not loop transactional state |
| Legacy local-agent memory writes | DEPRECATE | Already frozen toward canonical knowledge |
| Company/Mission/Plan | FROZEN / LATER AUDIT | Optional higher-order structure only if justified |

---

# 27. What should be on the normal-Chat critical path

After this audit, the normal path should stay extremely small:

```text
Normal Chat / Sol
    |
optional lightweight controller loop
    |
canonical Task
    |
ExecutionBackend
    |
Durable Run / tools / external environment
    |
Task result/evidence/recovery observation
    |
lightweight loop detects unconsumed change
    |
Sol reasons again
```

Not on the default critical path:

```text
Supervisor
LocalAgentOrchestrator
reasoning provider
Codex
worker gateway
WorkerEvidence/FanIn
Workflow
Company
PulseSender
```

Those remain optional/specialized/legacy layers invoked only when their actual function is needed.

This is the most important architectural simplification of Iteration 6.

---

# 28. What should be on Work's path

```text
Work native agentic loop
    |
canonical Task
    |
ExecutionBackend / tools / durable Run
    |
result/evidence/recovery
    |
Work native loop continues
```

Optional subordinate-worker security/evidence machinery may still be used when Work deliberately spawns or delegates external work through Soma, but Soma does not become the Work planner.

---

# 29. Terminology cleanup candidates

No rename is authorized yet, but the audit identifies misleading terms.

## `reasoning backend`

Current term implies a core cognition provider.

Possible future conceptual replacements:

- intelligent specialist backend;
- model specialist backend;
- delegated analysis backend;
- provider operation backend.

The best name should describe **optional delegated work**, not cognition ownership.

## `reasoning worker`

Should mean only an explicitly delegated specialist with an independent model loop, never Sol itself and never a prerequisite for normal Chat.

## `worker`

Should remain a subordinate execution/capability principal, not a synonym for “agentic brain.”

## `controller`

In the normal-Chat add-on, the controller is Sol/ChatGPT's decision authority. Soma mechanically preserves controller-visible state but does not become semantic controller.

## `agent`

Use carefully. `LocalAgentOrchestrator` is historical terminology that currently bundles heuristics/routing/model use. The corrected core loop is **Sol agentic behavior with Soma durability**, not a Soma local agent.

---

# 30. Historical evidence should be superseded, not rewritten

**INFERENCE**

Accepted Agent/Worker gates proved real mechanical properties. Rewriting them would destroy useful historical evidence.

Later cleanup should therefore:

1. leave accepted gate/result documents intact;
2. create an explicit realignment/supersession decision document;
3. say which architectural interpretation is no longer current;
4. preserve tests/mechanics that remain valid;
5. migrate terminology/runtime routes prospectively.

For example, G2 can remain truthful evidence that a provider-neutral reasoning Task path was implemented and tested. A later document can supersede the assumption that this path is the default agentic architecture.

---

# 31. Risks of over-cleaning

## Removing worker authority because “workers were a mistake”

Bad: optional future workers would regain owner-level tool access or require rebuilding a capability broker.

## Removing reasoning-store ambiguity semantics

Bad: any future external intelligent provider would again face duplicate-send/provider-binding risks.

## Removing FanIn entirely

Bad: true bounded parallel specialist work would lose deterministic coverage/provenance aggregation.

## Removing workflows immediately

Bad: current deterministic workflow users/tests may depend on their recovery/cancellation behavior.

## Deleting historical acceptance docs

Bad: destroys evidence and makes future archaeology harder.

The correct cleanup is **layer repositioning and convergence**, not a purge.

---

# 32. Risks of under-cleaning

## Leaving LocalAgent/Supervisor as normal semantic routers

Risk: Sol still competes with a second planner and user intent is classified by keyword heuristics.

## Leaving `reasoning backend` presented as the core agentic engine

Risk: future implementation again routes normal Chat cognition to Codex/provider models.

## Requiring WorkerEvidence/FanIn for every Task

Risk: simple actions become expensive and cumbersome.

## Requiring Workflow/Company for ordinary goals

Risk: user-facing complexity and duplicated planning state.

## Keeping two long-run execution authorities

Risk: inconsistent ownership/recovery and needless maintenance.

---

# 33. New understanding after Iteration 6

The cleanup problem is now much narrower than the original brief feared.

**INFERENCE**

The likely transformation is:

```text
CURRENT DRIFTED INTERPRETATION
Sol
 -> Soma orchestration/reasoning workers
 -> provider/model workers
 -> evidence
 -> Sol adjudicates

CORRECTED INTERPRETATION
Sol
 -> lightweight durable objective/observation bookkeeping when needed
 -> canonical Task / durable execution
 -> observation
 -> Sol

OPTIONAL SIDE BRANCH
Sol explicitly delegates bounded specialist work
 -> canonical specialist Task
 -> restricted worker/provider infrastructure
 -> EvidenceSubmission/FanIn if needed
 -> Sol adjudicates
```

Most Agent/Worker mechanics fit naturally into the **optional side branch** rather than the core path.

That is likely the cleanest way to preserve the investment without preserving the architectural mistake.

---

# 34. Open questions for Iteration 7

The next research should focus on **optional specialist/subagent boundaries and the atomic loop-to-Task seam**, because those are now the two places where the corrected architecture could still accidentally drift.

Questions:

1. What exact conditions justify a specialist worker versus letting Sol do the reasoning directly?
2. What work is appropriate for native Work subagents, optional normal-Chat specialists, Codex, Hermes execution, or deterministic parallel groups?
3. Should an optional intelligent specialist retain a canonical Task kind distinct from durable command, and if so what neutral terminology fits?
4. How should provider-native child agents map to Soma evidence without becoming canonical Tasks unless Soma actually owns their external effects?
5. Can worker authority/gateway remain completely dormant unless a real subordinate worker is attached?
6. What is the cleanest transactional mechanism for atomically creating a loop-owned Task without forking TaskManager?
7. How should a loop attach an already-existing read-only/result Task safely?
8. Which old Supervisor/LocalAgent public gateways or users/tests would block retirement?
9. Which workflow users/tests require compatibility before convergence?
10. Which Company/Plan assumptions explicitly depend on reasoning Task admission and must be audited later while Company stays frozen?

No implementation plan should be written yet.

---

# Sources inspected

## Core Task/execution

- `soma/tasks/models.py`
- `soma/tasks/store.py`
- `soma/tasks/backends.py`
- `soma/tasks/manager.py`
- `soma/job_manager.py`
- `soma/parallel_groups.py`

## Worker substrate / authority / process ownership

- `soma/worker_substrate/*`
- `soma/worker_authority/models.py`
- `soma/worker_authority/authority.py`
- `soma/worker_gateway/models.py`
- `soma/worker_gateway/transport.py`
- `soma/worker_process/launch.py`
- `soma/worker_process/containment.py`

## Evidence / reasoning provider

- `soma/worker_evidence/models.py`
- `soma/worker_evidence/fanin.py`
- `soma/reasoning/models.py`
- `soma/reasoning/backends.py`
- `soma/reasoning/store.py`
- `soma/reasoning/runtime.py`
- `soma/reasoning/codex_repository_backend.py`

## Legacy/compatibility orchestration

- `soma/local_agent/orchestrator.py`
- `soma/local_agent/durable_command_runner.py`
- `soma/jobs/long_run_manager.py`
- `soma/jobs/models.py`
- `soma/supervisor/models.py`
- `soma/supervisor/supervisor_flow.py`
- `soma/workflows/manager.py`
- `soma/external_coder/models.py`
- `soma/external_coder/handoff_generator.py`

## Delivery

- `soma/return_loop/models.py`
- `soma/return_loop/atomic_writer.py`
- `soma/return_loop/__init__.py`

## Prior research

- `docs/sol-agentic-loop-realignment-research/iteration-01-current-chatgpt-work-native-agent-reality-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-02-original-intent-drift-and-normal-chat-addon-boundary-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-03-minimal-durable-sol-control-loop-state-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-04-mode-aware-chat-vs-work-integration-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-05-minimal-loop-contract-pressure-test-2026-08-15.md`
- `docs/agent-worker-research/*` G1-G6 research/acceptance material inspected in prior iterations.
