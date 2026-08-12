# Iteration 2 - Worker Contract, Durable Graph, and Evidence Baseline

Date: 2026-08-12
Status: research only
Scope: worker taxonomy, work-unit/DAG architecture, evidence contract, mutation authority, and future reasoning-backend fit

## Guardrails

This iteration is research only. It does not authorize production implementation, schema migration, worker activation, model invocation, service restart, connector refresh, Hermes configuration change, commit, or push.

Iteration 1 remains the capability baseline. In particular:

- the integrated Hermes companion is headless execution/tool infrastructure, not a reasoning subagent;
- parallel Hermes instances are execution concurrency, not independent intelligence;
- Soma's Hermes pin is compared only with the configured Hermes checkout's own Git HEAD;
- Sol remains the candidate user-facing reasoning/adjudication head;
- the hybrid architecture from Iteration 1 remains a hypothesis to test, not an accepted implementation plan.

## Exact questions investigated in Iteration 2

1. Should Soma define canonical worker classes such as `execution_worker`, `retrieval_worker`, `scout_worker`, and `reasoning_worker`, or use capability/authority descriptors instead?
2. Does Soma's existing durable workflow subsystem already provide the right DAG substrate, and can it safely become the future worker manager?
3. What is the minimum durable work-unit/graph contract that preserves the existing canonical Task -> Run authority instead of creating a second lifecycle?
4. How should dependencies, readiness, concurrency, cancellation, partial completion, duplicate prevention, recovery, and plan revision work at a high level?
5. What is the minimum useful evidence/fan-in envelope that separates evidence from worker interpretation and bounds result size?
6. How should mutation authority be represented so additional workers never multiply external-world authority accidentally?
7. Can future native OpenAI reasoning subagents, current Responses Multi-agent, Codex subagents, or Agents SDK specialists attach behind the same boundary without redesigning the durable graph?
8. What do modern durable orchestration systems such as LangGraph and Temporal suggest, and do they justify replacing Soma's current substrate?

This iteration does not execute the planned 1/2/4/8 worker benchmark. It designs the contract that the later benchmark would exercise.

---

# A. Repository baseline discovered in Iteration 2

## A1. Soma already has a durable workflow DAG schema

### Facts

`soma/workflows/models.py` already defines workflow steps with:

- stable step IDs;
- `depends_on` edges;
- `on_failure` behavior;
- per-step status and state version;
- optional child run identity;
- step result/artifact fields.

`WorkflowDefinition.validate_graph()` rejects:

- duplicate step IDs;
- dependencies on missing steps;
- dependencies on later steps;
- cycles.

The current model allows up to 50 workflow steps.

This means Soma does not need to rediscover basic DAG validation from first principles.

## A2. The existing workflow runtime is intentionally single-active-child

### Facts

Although the workflow schema can describe independent dependencies, `WorkflowWorker` runs one step at a time:

- `_next_pending_step()` returns one runnable pending step;
- `_start_step()` claims one step;
- the workflow record has one `active_child_run_id`;
- `WorkflowStore.claim_step()` requires `active_child_run_id IS NULL` before a step is claimed;
- startup reconciliation treats multiple running steps as an ownership inconsistency.

`WorkflowManager._child_ownership_problem()` explicitly returns an error when more than one workflow step is running.

**Conclusion:** the current workflow subsystem is a durable sequential dependency runner, not a concurrent fan-out/fan-in worker graph.

## A3. Existing workflows own their own lifecycle

### Facts

The workflow subsystem has its own:

- workflow lifecycle states;
- workflow worker PID/identity;
- worker lease token and generation;
- state version;
- cancellation state;
- recovery state;
- terminal publication state;
- step lifecycle.

This predates the newer canonical Task -> Run convergence.

The accepted V3-1A interactive-worker plan explicitly calls workflows and supervisors compatibility lifecycle managers and says that a later lane which first uses equivalent planning/collaboration territory must project or retire overlap under progressive convergence rather than casually add another authority.

### Inference

Expanding the existing workflow subsystem directly into the future heterogeneous worker manager would preserve useful code, but it would also preserve a second execution lifecycle beside the canonical Task plane. That is the wrong default architectural direction unless a later migration study proves that workflow lifecycle can first be projected into canonical Tasks.

## A4. Canonical Tasks already provide the better execution authority boundary

### Facts

The canonical Task plane already provides:

- canonical task identity;
- controller request idempotency and request hashing;
- parent task identity and typed task links;
- backend kind/executor/reference;
- backend reservation before launch;
- task state/version;
- cancellation commands;
- checkpoints;
- recovery/uncertainty;
- result/evidence references.

`TaskStore` explicitly does not own process, lease, lock, evidence-body, or result-body state. Those remain authoritative in the durable run/backend plane.

`TaskStore.reserve_task()` is transactional and a replayed controller request with the same normalized hash returns the existing task rather than creating duplicate work.

`tasks/projections.py` deliberately emits compact projections that reference authoritative evidence instead of copying stdout, stderr, manifests, or result bodies into the task response. The normal compact task budget is 12 KiB.

### Inference

The future worker architecture should preserve this direction: orchestration metadata may refer to canonical Tasks, but worker process/result authority should not migrate upward into a new graph manager.

## A5. Soma already uses capability declarations successfully

### Facts

`soma/worker_adapters/contract.py` defines a provider-neutral `Capability` vocabulary and a three-valued support model:

- `supported`;
- `not_supported`;
- `unmeasured`.

`ProviderCapabilities` refuses incomplete declarations: absence never implies support. Every declaration must carry evidence.

Current capabilities include structured streams, exact session identity, explicit resume, mid-turn steering, stdin prompt support, provider-reported cost, token breakdown, failure-event mapping, and orphan-free root cancellation.

Claude Code and Codex have different measured capability profiles. The adapter contract keeps provider claims separate from canonical Task success.

### Conclusion

Soma already has a proven internal design pattern for provider-neutral capability discovery that is stronger than a hard nominal worker-class enum.

## A6. Soma already separates message authority from lifecycle authority

### Facts

The interactive worker substrate deliberately has:

- no provider enum;
- no duplicate queued/running/terminal task vocabulary;
- provider/session/message records subordinate to Task/Run;
- content-addressed payload references;
- `mandate_ref` and `mandate_version` fields;
- sender/recipient identity;
- idempotency keys and contract hashes;
- explicit message classes including `EVIDENCE_SUBMISSION` and `OUTCOME_PROPOSAL`;
- transport attempt states that can become outcome-unknown rather than being blindly resent.

`InteractionCoordinator` atomically reserves a canonical TaskCommand and subordinate worker message in the same SQLite transaction and refuses stale task state versions.

### Conclusion

This is an important precedent for the future graph: subordinate orchestration records can be durable without becoming a second execution lifecycle.

---

# B. Worker taxonomy decision

## Candidate 1 - hard canonical worker classes

Proposed names from the research brief:

- `execution_worker`
- `retrieval_worker`
- `scout_worker`
- `reasoning_worker`

### Benefits

- easy for humans to understand;
- useful for dashboards and documentation;
- useful as default scheduling profiles;
- makes the distinction between headless execution and independent reasoning explicit.

### Problems

A real backend can cross these categories depending on configuration:

- Codex can be a read-only explorer, an implementation worker, or a strong reasoning agent;
- a Hermes tool worker may perform retrieval or execution without reasoning;
- a cheap model may be a scout for one assignment and a deterministic extractor for another;
- a future native OpenAI agent can have read-only, tool-rich, or reasoning-heavy configurations;
- tool and mutation authority can vary independently from reasoning strength.

Making these names schema identities would force migrations or awkward multi-class assignment whenever capability boundaries move.

## Candidate 2 - capability and authority descriptors

A worker/backend declares what it can actually do and what authority it may receive.

This follows Soma's existing adapter contract and current Codex custom-agent design more closely than a hard ontology does.

### Iteration 2 decision

**Use capability-first contracts as the canonical scheduling contract. Keep worker classes as optional role profiles/hints, not authoritative identity.**

A future worker descriptor should conceptually separate at least five dimensions:

1. **Cognition** - no model / model present / measured reasoning tier or model identity.
2. **Operational capabilities** - repo read, web retrieval, exact command execution, code execution, structured output, session resume, steering, etc.
3. **Evidence capabilities** - can cite stable source refs, artifact hashes, test results, structured claims, provenance.
4. **Authority/effect capabilities** - read-only versus eligible for explicitly delegated mutation; supported resource/operation classes.
5. **Runtime qualities** - cost/latency class, resumability, cancellation guarantees, isolation/sandbox, concurrency domain.

Suggested role profiles remain useful:

- `execution`: cognition not required; exact bounded work;
- `retrieval`: evidence acquisition with read-only authority;
- `scout`: model interpretation is advisory/untrusted until adjudicated;
- `reasoning`: independent model reasoning suitable for semantic analysis.

But these profiles are derived/default bundles over capabilities, not new canonical lifecycle kinds.

## Why this matches current external designs

Current Codex ships human-facing roles such as `worker` and `explorer`, while custom agents can independently configure model, reasoning effort, sandbox mode, MCP servers, and skills. This demonstrates that role names are useful UX labels but the real behavior is determined by underlying configuration/capabilities.

---

# C. Where the durable graph should live

Four structural options were compared.

## Option C1 - evolve the existing Workflow subsystem directly

### Advantages

- dependency validation already exists;
- cancellation/recovery/event history already exists;
- least new code if current workflow semantics were sufficient.

### Problems

- current runtime is single-active-child;
- workflow has its own lifecycle authority and worker lease;
- current step types are narrow and execution-specific;
- direct expansion would deepen overlap with canonical Task -> Run authority;
- V3-1A already identified workflows as compatibility lifecycle managers subject to later convergence.

### Verdict

**Do not choose the existing Workflow lifecycle as the canonical future worker manager by default.** Reuse algorithms/validation ideas where useful; preserve records for compatibility; study migration/projection separately if implementation is ever authorized.

## Option C2 - encode the whole graph only with Task parent/child links

### Advantages

- no new graph identity;
- lifecycle remains entirely canonical Task.

### Problems

Parent/child means containment, not dependency readiness. A real graph also needs:

- dependency edges;
- immutable plan revision/hash;
- required/optional unit semantics;
- graph concurrency budget;
- cancellation/completion policy;
- capability requirements;
- admission disposition for nodes that are planned but not yet executable;
- fan-in/evidence contract version.

Stuffing all of that into generic Task links would make the link table an implicit graph engine without a coherent plan contract.

### Verdict

Too thin as the complete architecture.

## Option C3 - create a new independent work-unit lifecycle beside Task

### Advantages

- graph-specific states can be designed freely;
- easiest to model `planned`, `ready`, `running`, `blocked`, `completed` in one table.

### Problem

This recreates the exact duplicate-lifecycle problem Soma's canonical Task plane was built to eliminate. It creates competing answers to questions such as "is this work running?", "who owns cancellation?", and "what result is authoritative?"

### Verdict

**Rejected as an architectural premise.**

## Option C4 - thin durable WorkPlan/graph sidecar bound to canonical Tasks

Shape:

```
owner / root task
      |
 durable WorkPlan revision
      |
  plan nodes + dependency edges
      |
 ready node admission
      |
 canonical child Task -> selected backend/run
      |
 authoritative result/evidence refs
      |
 bounded graph fan-in projection
      |
 Sol adjudication
```

### Authority rule

The graph sidecar may own planning/admission facts. It must not own execution lifecycle.

A plan node may be described as:

- planned;
- ready for admission;
- bound to a canonical Task;
- blocked before admission;
- superseded by a new plan revision.

It should **not** independently say:

- running;
- cancellation_pending;
- completed;
- failed;
- uncertain.

Once a node is bound to a Task, those execution facts come only from the canonical Task/backend projection.

### Iteration 2 decision

**C4 is the leading graph architecture.** It preserves canonical Task -> Run authority while giving Soma enough durable scheduling metadata to recover after Chat disconnects.

This remains a research decision, not implementation authorization.

---

# D. Work-unit identity and minimum WorkPlan contract

## D1. Avoid a second opaque execution identity

There are two legitimate identities:

1. a stable **plan-unit key** used before admission;
2. the canonical **task_id** after admission.

The plan-unit key is not a lifecycle owner. It is an immutable key inside one plan revision, for example `repo_architecture`, `web_openai`, `tests`, or an opaque/hash-derived equivalent.

When a node becomes runnable, Soma binds that node exactly once to one canonical Task. The binding is durable.

### Why this is preferable to pre-creating every Task

If every possible node were created as a Task immediately, a dependency failure would require pretending that never-started work had failed or been cancelled. The current canonical Task vocabulary has no clean `blocked-before-admission` / `skipped` terminal state.

Keeping blocked/unadmitted nodes in the plan layer avoids inventing execution outcomes for work that never received execution admission.

## D2. Candidate WorkPlan fields

Minimum root-level plan metadata:

- `plan_id`
- `root_task_id` or other canonical owner reference
- `plan_revision`
- `plan_hash`
- `objective_ref`
- `constraints_ref`
- `created_at`
- `max_concurrency`
- `completion_policy`
- `cancellation_policy`
- `evidence_contract_version`
- `supersedes_plan_id` / previous revision reference when applicable

Minimum node metadata:

- `unit_key`
- `assignment_ref`
- `assignment_hash`
- `depends_on[]`
- `required_capabilities`
- `required_authority`
- `required` versus optional/advisory semantics
- `timeout/deadline policy`
- `retry policy`
- `result/evidence contract version`
- `max_public_result_bytes`
- `admission_disposition` (`planned`, `ready`, `bound`, `blocked`, `superseded`)
- `task_id` once bound

### Deliberate omissions

Do not put worker PID, provider session state, process lease, canonical task status, stdout/stderr, or result bodies in the WorkPlan tables. Those already have authoritative owners.

## D3. Root identity remains a design question

A strong candidate is one future canonical orchestration/root Task whose backend is a deterministic Soma work-graph backend. Child work units then bind to child canonical Tasks with heterogeneous backends.

This gives the owner request one durable public identity and allows a disconnected Sol to reconnect through one root Task.

However, current `TaskKind` and `BackendKind` do not yet contain such a root type/backend. Whether to extend them or keep `plan_id` as the only public orchestration identity should be resolved before implementation.

Iteration 2 does not authorize or select a schema migration here.

---

# E. DAG and continuation semantics

## E1. Plan immutability

A running plan revision should be immutable in its decision-bearing fields.

Changing assignments, dependencies, authority, or required capability should produce a new plan revision/hash rather than silently changing the meaning of already admitted work.

Bound Tasks remain bound to the plan revision that admitted them.

## E2. Readiness

A node is ready only when its declared dependency rule is satisfied by authoritative dependency Task outcomes/evidence.

The default should be conservative:

- required dependencies must produce an acceptable terminal result;
- a failed/uncertain/cancelled required dependency blocks admission of dependents;
- optional/advisory dependencies may have separate explicit policy.

Readiness must be derived from durable state, not from the prior Chat transcript.

## E3. Concurrency

Effective concurrency should be the minimum of several independent ceilings:

- WorkPlan concurrency budget;
- backend/provider capacity;
- tool/provider rate limits;
- credential locks;
- resource mutation locks;
- machine/resource budgets;
- explicit unit authority constraints.

More ready units do not imply more runnable units.

## E4. Duplicate work prevention

At minimum:

- plan revision + unit key must be unique;
- assignment/constraint content is hashed;
- the node-to-Task binding is single-shot/idempotent;
- the derived controller request/idempotency identity must replay to the same canonical Task;
- a changed normalized assignment under the same identity is a conflict, not a second launch.

## E5. Cancellation

Root cancellation should:

- stop admitting unbound nodes;
- request canonical cancellation for every bound non-terminal child Task;
- retain mutation/resource ownership until child quiescence/termination or external reconciliation is proven;
- represent ambiguous external mutation outcomes as uncertainty rather than success.

The graph sidecar records suppression/admission facts; canonical Task/Run remains authoritative for cancellation state.

## E6. Retries

Automatic retry policy must depend on effect semantics, not worker class.

Safe default:

- read-only/retrieval work may retry bounded transient failures when its request is idempotent;
- deterministic local computation may retry under an exact input hash;
- mutation must not be automatically retried after dispatch if the outcome could be unknown;
- a new semantic attempt after an ambiguous mutation requires reconciliation or explicit owner/controller action.

## E7. Partial completion

The fan-in layer must be able to return useful evidence when some units fail or are blocked.

A graph should therefore distinguish:

- required units;
- optional/advisory units;
- missing evidence;
- failed execution;
- blocked-before-admission nodes;
- unresolved/uncertain tasks.

Partial completion is a first-class fan-in condition, not automatically a whole-graph failure.

## E8. Disconnect/reconnect

A disconnected Chat/Sol should not erase or recreate the work graph.

Soma should be able to continue only work whose semantics and authority are already durably determined. When fresh semantic judgment is required, the root work should stop at `AWAITING_CONTROLLER` rather than inventing a decision.

On reconnect, Sol should retrieve:

- current plan revision/hash;
- bound unit -> Task identities;
- authoritative task states;
- blocked/unadmitted nodes and reasons;
- bounded evidence fan-in;
- unresolved conflicts/uncertainties.

Sol can then adjudicate without replaying completed work.

---

# F. Evidence contract

## F1. Principle

The fan-in contract must optimize for **evidence density**, not transcript compression alone.

A worker transcript is debugging evidence. It should not be the normal synthesis input.

The normal synthesis input should expose concise claims tied to exact evidence references, while full transcripts/artifacts remain retrievable by reference when needed.

## F2. Reject one global `confidence` as a core authority field

A worker-global confidence number mixes several different concepts:

- source quality;
- extraction certainty;
- model self-confidence;
- coverage/completeness;
- inference strength.

A model can be confidently wrong. A headless execution worker may have no meaningful confidence at all.

### Decision

Do not make one worker-global `confidence` field part of the minimum core contract.

Use explicit uncertainty and per-claim evidence linkage instead. An optional backend-specific self-assessment may be preserved as non-authoritative metadata, but Sol must not treat it as evidence.

## F3. Minimum evidence/result envelope

Candidate compact core:

```
schema_version
unit_key
canonical_task_id
assignment_ref
assignment_hash
submission_status
claims[]
evidence[]
artifacts[]
uncertainties[]
blockers[]
metrics
provenance
```

### `submission_status`

This is the worker/result-envelope claim about its submission, for example:

- `complete`
- `partial`
- `blocked`

It is not a canonical Task state.

### `claims[]`

Each claim should contain only the minimum synthesis data:

- `claim_id`
- concise statement
- `claim_kind` (`observation`, `inference`, `recommendation` or similar)
- `evidence_ids[]`
- explicit uncertainty/caveat when applicable

A pure execution worker may submit zero semantic claims and only evidence/artifacts.

### `evidence[]`

Each evidence item should carry stable identity/provenance rather than a giant body:

- `evidence_id`
- `kind`
- authoritative `ref` or locator
- content/source hash when available
- observed/retrieved timestamp when material
- optional bounded excerpt/fact only when needed for synthesis

Examples include:

- run result reference;
- repository file + commit/line locator;
- test execution result hash;
- web source locator;
- structured tool result reference;
- protected artifact reference.

### `artifacts[]`

At minimum:

- reference/path identity;
- hash;
- media/content type if known;
- byte size.

### `uncertainties[]` and `blockers[]`

These are explicit text/code records of what the worker could not establish or complete. They are more actionable than a floating confidence number.

### `metrics`

Benchmark-relevant scalar metrics may include:

- elapsed time;
- worker/tool-call count;
- result bytes;
- provider-reported token/cost information when available.

### `provenance`

At minimum identify:

- backend/provider adapter identity;
- model identity when a model exists;
- backend run/session/result reference;
- evidence contract version.

Worker process IDs belong in diagnostic evidence, not the normal synthesis projection.

## F4. Evidence is not interpretation

A hard rule for future implementation:

- evidence items say **where the support came from and what bytes/result identity were observed**;
- claims say **what the worker concludes from that evidence**.

A claim without evidence can be preserved as an unsupported/advisory interpretation, but it must never be silently upgraded into an evidence item.

Conflicting worker claims should both reach Sol with their evidence references. The fan-in layer should not erase disagreement just to make a clean summary.

## F5. Result-size bounding

Use two levels:

1. per-unit public envelope budget;
2. graph fan-in aggregate budget.

When the aggregate exceeds the fan-in budget, trim low-priority excerpts/claims while preserving:

- unit identity;
- status;
- evidence/artifact references;
- blockers/uncertainties;
- retrieval instructions.

This extends the existing canonical Task projection philosophy rather than inventing a transcript compactor.

## F6. `suggested_followups`

Useful but not core.

Workers may optionally suggest follow-ups, but those are advisory claims. Sol owns semantic replanning. A worker should not be able to extend the durable graph merely by suggesting more work.

---

# G. Mutation authority

## G1. Capability is not authority

A backend may be technically capable of writing a repository or calling an external API. That must not imply that every work unit using the backend receives that authority.

Authority must be granted per admitted unit.

## G2. Default fan-out should be read-only

Parallel exploration, retrieval, test inspection, adversarial review, and reasoning are the safest high-value concurrency targets.

This aligns with current Codex guidance, which recommends starting parallel subagents on read-heavy exploration/tests/triage/summarization and warns that parallel writes increase conflict/coordination risk.

## G3. Candidate authority contract

A mutation-capable unit should carry an explicit authority reference/mandate describing at least:

- allowed effect class;
- target resource keys;
- allowed operation/action class;
- scope/project binding;
- idempotency identity;
- preconditions/state version where applicable;
- expiry/deadline;
- whether retry is allowed before dispatch;
- reconciliation requirement after ambiguous outcome.

The existing `mandate_ref`, resource mutation locks, ProjectScope, task/run state versions, and persist-before-send uncertainty semantics are strong building blocks.

## G4. Single-writer principle

Within one resource/authority domain, concurrent workers should not independently hold mutation authority unless the operation is proven commutative/idempotent under a stronger contract.

Safe default:

- many readers;
- one mutation owner per resource key;
- no automatic duplicate mutation after an uncertain dispatch.

## G5. Reasoning workers should not receive mutation authority by default

A strong reasoning worker can analyze and propose a mutation without performing it.

Preferred separation for risky work:

```
reasoning/review worker -> evidence + proposed action
              |
             Sol adjudication
              |
exact execution worker -> explicitly authorized mutation
```

This reduces the chance that increasing reasoning concurrency also increases external-world mutation authority.

---

# H. Fit with current OpenAI native agents

## H1. Responses API Multi-agent

### Current official facts

OpenAI's GPT-5.6 Responses Multi-agent beta allows a root model to spawn parallel subagents and synthesize their work.

OpenAI recommends it for independent bounded workstreams and explicitly recommends a single agent instead when agents would contend over a mutable resource or when the application requires a fixed deterministic graph.

`max_concurrent_subagents` defaults to 3 and is recommended for most workloads. OpenAI currently documents no fixed tree-depth or total-subagent-count limit.

Within the hosted team, all agents are described as equally capable and as having the same configured tool set.

### Implication for Soma

Treating each hosted OpenAI subagent as a canonical Soma work unit would give Soma weak control over child identity, deterministic scheduling, per-child tool authority, and recovery semantics.

**Leading mapping:** one canonical Soma reasoning Task may use one Responses Multi-agent tree internally as a reasoning backend invocation. Soma sees one bounded backend result/evidence envelope; OpenAI may use its own internal subagents inside that backend.

Do not mirror every hosted OpenAI child into Soma's canonical graph unless a future OpenAI contract exposes stable external child identity, cancellation/recovery, result identity, and authority scoping suitable for that mapping.

## H2. Agents SDK

OpenAI's Agents SDK documents `agents-as-tools` as the pattern where one manager retains ownership of the conversation/final answer and bounded specialist agents contribute results. This is conceptually close to Sol adjudicating worker evidence.

The SDK also supports code-directed orchestration, which is preferable when the application requires predictable deterministic behavior.

### Implication

Agents SDK specialists are a serious future reasoning-backend option, but the SDK does not remove Soma's need for durable local Task identity, effect authority, and recovery when external tools mutate the world.

## H3. Codex subagents

Current Codex subagents show that role profiles can be configured independently through model, reasoning effort, sandbox mode, MCP servers, and skills. Codex ships labels such as `worker` and `explorer`, but custom roles are intentionally narrow/configurable.

### Implication

This supports the Iteration 2 choice: role labels are useful scheduling/UI hints, while capability/authority declarations should be canonical.

---

# I. Modern durable-orchestration alternatives

## I1. LangGraph

Current LangGraph supports native fan-out/fan-in, parallel node execution, checkpointers, per-branch retry policies, and max concurrency. Its documentation notes that successful nodes in a failed parallel superstep can be checkpointed so those successful nodes need not repeat on resume.

### What Soma should learn from it

- checkpoint after meaningful work boundaries;
- do not rerun successful independent branches after another branch fails;
- retries should target failing branches;
- explicit max concurrency belongs in the graph contract;
- parallel output order must not be assumed.

### Why not adopt it automatically

Adding LangGraph as the canonical runtime would introduce a new orchestration state/checkpoint authority beside Soma's existing Task/Run stores and would require migration/operational work. Its value should be benchmarked against the thin WorkPlan sidecar rather than assumed.

## I2. Temporal

Temporal deliberately separates deterministic Workflow logic from side-effecting Activities. Workflow code must be deterministic because the service may replay it to reconstruct state; external calls belong in Activities. Temporal also has explicit cancellation semantics and durable event history.

### What Soma should learn from it

- keep durable orchestration decisions deterministic;
- isolate external side effects behind separately owned execution units;
- make replay/idempotency semantics explicit;
- cancellation of orchestration is not proof that an external side effect was reversed.

### Why not adopt it automatically

Soma already owns durable run identity, process containment, result publication, task recovery, and SQLite-backed continuity. Replacing that with Temporal would be a major platform migration and could duplicate or displace mature Soma authority.

Temporal is therefore a strong reference architecture, not the default implementation choice for this research track.

---

# J. Iteration 2 architectural baseline

## Decisions strengthened by evidence

### 1. Capability-first worker contract

Canonical scheduling should use explicit capabilities and authority requirements. `execution/retrieval/scout/reasoning` remain role profiles/hints.

### 2. Canonical Task -> Run remains execution authority

Do not add a second generic worker lifecycle.

### 3. Thin WorkPlan sidecar is the leading graph design

The sidecar owns immutable plan revisions, dependency/admission facts, unit requirements, graph policy, and Task binding. It does not own worker execution state.

### 4. Existing Workflow is a reference/compatibility subsystem, not the default new manager

Reuse ideas and possibly validation code later; do not deepen duplicate lifecycle authority without a convergence/migration study.

### 5. Evidence-reference-first fan-in

Normal Sol synthesis should receive claims linked to compact evidence references and artifacts, not full transcripts.

### 6. Worker interpretation never becomes evidence by declaration

Evidence and claims are separate fields and separate authority concepts.

### 7. Mutation authority is orthogonal to worker intelligence

More workers must not mean more writers. Read-only fan-out is the default; mutation requires explicit per-unit authority and resource ownership.

### 8. Native OpenAI multi-agent can fit behind the backend boundary

A hosted OpenAI agent tree can be one reasoning backend invocation without owning Soma's durable graph. This lets Soma benefit from stronger native subagents later without redesigning plan identity, evidence format, cancellation policy, or fan-in.

---

# K. Facts, inferences, hypotheses, rejected ideas

## Confirmed facts

1. Soma already validates workflow dependency DAGs.
2. The current workflow runtime supports only one active child and treats multiple running steps as an ownership inconsistency.
3. Existing workflows maintain their own lifecycle/lease/recovery authority separate from canonical Tasks.
4. The accepted V3-1A architecture explicitly preserves Task -> Run authority and treats workflow/supervisor overlap as future convergence territory.
5. Canonical Tasks already support parent relationships, backend references, CAS state, cancellation/recovery, and evidence/result references.
6. Canonical task projections already use bounded evidence-by-reference rather than copying result bodies.
7. Soma worker adapters already use complete provider-neutral capability declarations with supported/not-supported/unmeasured evidence.
8. The worker substrate already stores `mandate_ref`, project/resource/task/run identities, content hashes, idempotency identities, and outcome-unknown transport states without adding a second task lifecycle.
9. Current OpenAI Responses Multi-agent is model-directed, favors independent bounded work, and is not recommended for fixed deterministic graphs/shared mutable-resource contention.
10. Current Codex guidance favors read-heavy parallel subagent workloads before write-heavy parallel work.
11. LangGraph and Temporal both reinforce explicit durability, replay/idempotency, and separation of orchestration from side effects, though through different runtime models.

## Inferences

1. A capability/authority descriptor is more future-proof than a hard worker-class enum.
2. A thin WorkPlan sidecar can provide durable fan-out/fan-in without displacing Task/Run authority.
3. Plan nodes should exist durably before execution admission, but should bind to one canonical Task only when admitted.
4. WorkPlan admission dispositions are orchestration metadata, not a duplicate worker lifecycle.
5. Evidence-linked claims will reduce Sol synthesis burden more safely than transcript summarization alone.
6. Global worker confidence is a weak contract; explicit evidence linkage and uncertainty are more useful.
7. Future OpenAI hosted agent trees are likely safer as one reasoning-backend invocation than as one-to-one canonical Soma child tasks under the current API contract.

## Hypotheses to test later

1. A WorkPlan sidecar can be kept small enough that extending Task links alone is not preferable.
2. Lazily binding runnable plan nodes to Tasks provides cleaner blocked/skipped semantics than pre-creating every Task.
3. A 12-32 KiB per-unit evidence envelope plus a bounded aggregate fan-in will preserve answer quality while materially reducing synthesis tokens.
4. Four parallel read/research workers will often provide the best latency/coverage tradeoff, while eight will increase duplication and fan-in burden on many tasks.
5. Resource-scoped single-writer admission will prevent most mutation races without unnecessarily serializing read-only work.
6. One Soma reasoning Task backed by an internal OpenAI Multi-agent tree can outperform a one-model reasoning backend while preserving the same external evidence contract.

## Rejected ideas in Iteration 2

- **Hard-code `execution/retrieval/scout/reasoning` as the canonical worker identity.** Rejected as too rigid; keep them as profiles/hints over explicit capabilities.
- **Promote the existing Workflow lifecycle directly into the future worker manager.** Rejected as the default because it is sequential today and duplicates Task lifecycle authority.
- **Create a second generic running/completed work-unit state machine beside Task.** Rejected because it recreates competing lifecycle truth.
- **Use Task parent/child links alone as the whole graph contract.** Rejected as insufficient for plan revisions, dependency readiness, admission policy, and graph-wide limits.
- **Treat worker self-confidence as evidence.** Rejected.
- **Give every reasoning worker the same mutation tools simply because the backend supports them.** Rejected.
- **Mirror every current Responses Multi-agent child directly into Soma's canonical graph.** Rejected under the current API contract; the hosted tree does not expose the deterministic per-child authority/ownership contract Soma requires.
- **Adopt LangGraph or Temporal merely because they are modern.** Rejected as a premise; they remain comparison/reference architectures until migration cost and measurable benefit justify adoption.

## Confirmed bugs

None recorded in Iteration 2.

The existing single-active-child Workflow behavior is intentional architecture, not a bug.

---

# L. Candidate fan-out/fan-in shape after Iteration 2

```
owner request
     |
 Sol semantic decomposition
     |
 one durable root / WorkPlan revision
     |
 +--- planned nodes + dependency edges ---+
 |                                       |
 readiness + capability/authority matching
 |                                       |
 +---- canonical Task admission ----------+
          |          |          |
        Task A     Task B     Task C
          |          |          |
       backend     backend     backend
       execution   retrieval   reasoning
          |          |          |
       evidence    evidence    evidence
          +----------+----------+
                     |
            bounded fan-in envelope
                     |
              Sol adjudication
                     |
              final synthesis
```

The `backend` labels are implementations. The graph contract is provider-neutral.

---

# M. Next research questions for Iteration 3

1. **Root identity:** Should one future root/orchestration canonical Task own the WorkPlan, or should `plan_id` remain the public orchestration identity?
2. **Plan revision semantics:** Exactly what can change in a new plan revision while existing child Tasks are running, and how are unchanged units reused without replay?
3. **Node admission state:** Is `planned/ready/bound/blocked/superseded` the minimal non-lifecycle disposition set, or can it be reduced further?
4. **Task binding:** What deterministic controller request/idempotency identity should bind a plan unit to one canonical Task?
5. **Dependency success contract:** Does readiness depend on Task terminal state, published result classification, explicit Sol acceptance, or evidence predicates?
6. **Retry/attempt model:** Should a retry remain one Task/backend attempt, become a successor Task, or use a subordinate attempt identity?
7. **Fan-in schema validation:** Define a concrete JSON Schema/Pydantic sketch and test it against execution, retrieval, scout, and reasoning examples without implementing it in production.
8. **Conflict adjudication:** How should fan-in flag contradictory claims and missing evidence so Sol can efficiently request only the evidence needed to resolve them?
9. **Budget policy:** What per-unit and aggregate byte/token bounds should be used in the 1/2/4/8 benchmark?
10. **Parallel benchmark design:** Freeze representative tasks, success criteria, duplicate-work metrics, synthesis burden metrics, and recovery tests before executing any experiment.
11. **Mutation admission:** Define the minimum resource/mandate contract and exact ambiguous-outcome rule before any multi-worker mutation experiment.
12. **Normal Chat integration:** Determine the minimum future public Soma action/query pair that can expose one root operation and one coherent fan-in result without leaking worker-level tool-call noise.

Iteration 2 ends here. No worker/model parallelism experiment was launched.

---

# Sources consulted

## Soma repository evidence

Primary files/documents inspected:

- `soma/workflows/models.py`
- `soma/workflows/manager.py`
- `soma/workflows/store.py`
- `soma/workflows/worker.py`
- `soma/tasks/models.py`
- `soma/tasks/store.py`
- `soma/tasks/manager.py`
- `soma/tasks/projections.py`
- `soma/worker_adapters/contract.py`
- `soma/worker_adapters/codex.py`
- `soma/worker_adapters/claude_code.py`
- `soma/worker_substrate/models.py`
- `soma/worker_substrate/coordinator.py`
- `soma/worker_substrate/dispatch.py`
- `docs/V3_1A_INTERACTIVE_WORKER_SUBSTRATE_PLAN_2026-07-30.md`
- `docs/agent-worker-research/iteration-01-current-capability-and-architecture-baseline-2026-08-12.md`

## Current official OpenAI primary sources

- Responses API Multi-agent: https://developers.openai.com/api/docs/guides/responses-multi-agent
- Agents SDK orchestration: https://openai.github.io/openai-agents-python/multi_agent/
- Current model / Programmatic Tool Calling guidance: https://developers.openai.com/api/docs/guides/latest-model
- ChatGPT/Codex Subagents: https://learn.chatgpt.com/docs/agent-configuration/subagents

## Modern orchestration comparison sources

- LangGraph Graph API / parallel fan-out-fan-in: https://docs.langchain.com/oss/python/langgraph/use-graph-api
- LangGraph persistence/interrupt material consulted during comparison: https://docs.langchain.com/oss/python/langgraph/persistence
- Temporal Python workflow basics: https://docs.temporal.io/develop/python/workflows/basics
- Temporal Python activity basics: https://docs.temporal.io/develop/python/activities/basics
- Temporal Python cancellation: https://docs.temporal.io/develop/python/workflows/cancellation
