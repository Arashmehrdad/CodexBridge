# Iteration 3 - Identity, Revision, Attempt, and Fan-In Contract

Date: 2026-08-12
Status: research only
Scope: root identity, plan revision semantics, dependency/readiness rules, Task binding and retries, evidence/fan-in schema, mutation admission, and 1/2/4/8 benchmark design

## Guardrails

This iteration is research only. It does not authorize production implementation, schema migration, runtime activation, worker/model launch, service restart, connector refresh, Hermes configuration change, commit, push, or changes to the separate normal-Chat tool UX implementation thread.

Only this journal file is authored by the agent-worker research thread.

During Iteration 3, the shared Soma worktree contained concurrent normal-Chat UX work including `soma/public_tool_metadata.py`, `tests/test_public_tool_metadata.py`, and later unstaged edits to `soma/gateway_models.py` and `soma/server.py`. Those files were intentionally not inspected as part of this research question, not modified, not staged, and not incorporated into this journal's architecture conclusions.

Iteration 1 remains the capability baseline. Iteration 2 remains useful but receives one material correction here: the proposed generic `WorkPlan` sidecar is no longer the leading identity design after reconciling it with the already-accepted inactive V3-1B Company Kernel.

---

# 1. Exact questions investigated

1. What should be the semantic root identity for decomposed agentic work: a root Task, a new WorkPlan, or existing Mission/PlanRevision identity?
2. What exact semantics should an immutable plan revision have while prior work is running, completed, published, or accepted?
3. Can Iteration 2's proposed `planned/ready/bound/blocked/superseded` node dispositions be eliminated and derived from existing records?
4. How should dependencies between parallel work units be represented and what exact predicate makes a dependency satisfied?
5. What deterministic idempotency identity should bind one route attempt to exactly one canonical Task?
6. What counts as a retry of the same attempt, a successor attempt, or a new plan/outcome?
7. When should a native OpenAI/Codex subagent become a canonical Soma Task, and when should it remain subordinate to one Task/backend invocation?
8. What concrete evidence-submission envelope can cover execution, retrieval, scout, and reasoning work without copying transcripts into Task state?
9. What should Soma's deterministic fan-in layer do versus what should Sol semantically adjudicate?
10. What byte/token budgets should be used for the first 1/2/4/8 worker benchmark?
11. What exact benchmark design can compare concurrency fairly without changing the amount of required work between worker counts?
12. What mutation-admission rule prevents parallel reasoning/execution from multiplying external-world authority?
13. What is the single future integration point to normal Chat without merging this research with the separate UX implementation thread?

No benchmark or worker/model experiment is executed in Iteration 3.

---

# 2. Major repository discovery: V3-1B already owns the plan-domain identities

## 2.1 Facts

The inactive Company Kernel in `soma/company_kernel` already defines and has accepted architecture for:

- `Company`;
- `Mission`;
- immutable `PlanRevision`;
- immutable route-neutral `WorkPackage`;
- route-independent `outcome_id`;
- immutable route-specific `WorkPackageAttempt` linked to one canonical Task;
- immutable `AcceptanceCommit` selecting one exact published result;
- bounded reconciliation receipts.

The source models explicitly state that execution state remains in canonical Task and Run planes.

The Company Kernel store is currently schema-only/inactive. Its source has no Company/Mission/plan/package/attempt/acceptance runtime actions, and `schema_state()` reports `active_capability: False` even when the schema is present.

The accepted architecture explicitly forbids WorkPackage/Attempt status, PID, process, lease, lock, result, publication, cancellation, or recovery authority.

## 2.2 Important existing identity separation

The accepted route-independent outcome identity includes:

- `mission_id`;
- `plan_revision_id`;
- `package_key`;
- route-neutral WorkPackage contract hash;
- exact `project_id` / `resource_id` / scope generation.

It explicitly excludes provider, model, executable profile, argv, environment, native session, Task ID, Run ID, PID, and worker ID.

Route-specific facts instead belong to `WorkPackageAttempt` and canonical Task/Run evidence.

This is already almost exactly the identity separation required by the future worker architecture.

## 2.3 Iteration 2 correction

Iteration 2 proposed a thin `WorkPlan` sidecar owning immutable plan revision, graph dependencies, admission facts, and Task bindings.

After inspecting V3-1B, **a new canonical `WorkPlan` identity is no longer the leading design**. It would overlap with `Mission -> PlanRevision -> WorkPackage -> WorkPackageAttempt` and risk creating a second plan-domain truth.

The useful part of Iteration 2 survives as a *conceptual work graph*, but its durable identity should preferentially reuse the Company Kernel for mission-level decomposed work.

---

# 3. Root identity decision

## 3.1 Atomic work

For one bounded operation that does not require durable decomposition, the canonical Task remains sufficient.

Examples:

- run one exact command;
- perform one bounded retrieval operation;
- execute one reasoning backend request when all internal subagent activity can be treated as one provider/backend invocation.

No Mission or plan graph should be required merely because an implementation happens to use multiple OS processes or hosted subagents internally.

## 3.2 Decomposed mission-level work

For work that genuinely requires multiple independently durable outcomes, the leading identity stack is:

```text
Mission
  -> current immutable PlanRevision
      -> WorkPackage A
      -> WorkPackage B
      -> WorkPackage C
           -> WorkPackageAttempt
                -> canonical Task
                     -> backend / Run / provider session
```

### Decision

- `Mission` is the long-lived semantic root.
- `PlanRevision` is the exact accepted plan identity.
- `WorkPackage` is the route-neutral durable unit/outcome contract.
- `WorkPackageAttempt` is a route-specific attempt record.
- canonical `Task` owns execution lifecycle for that attempt.
- backend/Run/provider session owns technical execution evidence beneath Task.

A separate root Task should **not** own Mission or PlanRevision identity merely to make a tree shape convenient.

## 3.3 Two-level architecture, not one universal graph

The architecture therefore has two useful modes:

```text
simple bounded work
owner -> Sol -> Task -> backend -> evidence

multi-unit agentic work
owner -> Sol -> Mission/PlanRevision -> WorkPackages -> Attempts -> Tasks -> evidence -> Sol
```

This prevents every tiny command from becoming a Company/Mission while also preventing mission-level decomposition from being squeezed into Task parent pointers.

---

# 4. Temporary native subagents are not automatically canonical Tasks

## Facts from Soma organisational contract

The accepted organisational contract explicitly states that a temporary subagent does not become a new canonical task, plan, or acceptance authority merely because it is a separate model session.

## Current OpenAI facts

Responses API Multi-agent allows a root GPT-5.6 agent to create a tree of hosted subagents. The root synthesizes the final response. Agent paths such as `/root/researcher` are visible, `list_agents` can expose the current tree/statuses, and the request can bound simultaneous active subagents with `max_concurrent_subagents`. The default/recommended value is 3. The total number/depth is not fixed.

All agents in one current Multi-agent request share the request's configured tools. OpenAI recommends Multi-agent for independent bounded work and recommends one agent instead when agents contend over shared mutable resources or when a fixed deterministic execution graph is required.

Codex similarly exposes subagent threads and returns their summaries to the main agent. Subagents inherit the parent permission mode by default, although custom Codex agents can be configured read-only.

## Decision rule

A separate model/session becomes a canonical Soma Task **only when Soma needs independent durable work ownership** such as:

- independent cancellation/recovery;
- an independently accepted/published route attempt;
- distinct mutation authority or ProjectScope reservation;
- independently addressable result/evidence identity across reconnects;
- independent retry/supersession semantics.

A hosted/native subagent should remain subordinate to one Task when it is merely an internal reasoning strategy whose whole externally meaningful outcome is the parent backend result.

### Consequence

A future reasoning backend may legitimately be:

```text
one WorkPackageAttempt
  -> one canonical reasoning Task
      -> one OpenAI Responses Multi-agent request
          -> root + hosted subagent tree
      -> one bounded evidence submission
```

Soma need not mirror every hosted child into TaskStore.

---

# 5. PlanRevision semantics

## 5.1 Facts already accepted by V3-1B

PlanRevision rows are immutable.

Only `missions.current_plan_revision_id` denotes currency. Selection is compare-and-set using the expected current revision and `plan_state_version` inside one transaction.

A replan does not mutate old WorkPackages. In the V3-1B first proof, WorkPackages belonging to a non-current plan are ineligible for new attempts or AcceptanceCommit.

`outcome_id` includes `plan_revision_id`; therefore an otherwise identical package under a new plan has a different route-independent outcome identity.

## 5.2 No silent cross-revision reuse

This design intentionally makes plan revision semantically meaningful.

Therefore Iteration 3 rejects automatic reuse such as:

- silently attaching a prior Task to a new plan;
- silently treating an old accepted outcome as the new plan's accepted outcome;
- silently reclassifying an in-flight old WorkPackage as current;
- deriving equivalence through semantic similarity.

If a new PlanRevision wants to reuse old work, that reuse should be explicit evidence/input lineage rather than identity collapse.

## 5.3 Candidate future carry-forward rule

A later design may permit a current WorkPackage to cite a prior published or accepted outcome as an input/evidence reference, e.g.:

```text
new WorkPackage
  requires evidence from accept_<old outcome>
```

That would avoid unnecessary recomputation without pretending the old outcome has the new plan's identity.

This is a future hypothesis only; current Company Kernel v1 has no such carry-forward field/action.

## 5.4 Replanning while old work is still running

Current accepted V3-1B architecture says non-current packages cannot receive new attempts or acceptance, but it does not make plan selection itself proof that an already-running old Task has stopped.

That is correct mechanically: selecting a new plan cannot fabricate cancellation or containment.

For future mutation-capable multi-worker execution, however, the executive must explicitly decide what to do with active old-plan attempts:

- allow read-only work to finish as evidence;
- cancel it;
- revoke future protected authority and contain already-started effects;
- explicitly preserve it if the new plan still wants the work.

**Research risk, not a confirmed bug:** future plan activation needs an explicit active-attempt disposition policy before broad mutation is allowed. Plan supersession must not silently become operational revocation, and it also must not silently leave unwanted mutation authority running.

---

# 6. Eliminate the proposed node mini-lifecycle

Iteration 2 considered non-lifecycle node dispositions such as:

`planned / ready / bound / blocked / superseded`

Iteration 3 finds that most of these can be derived from existing immutable facts.

| Concept | Existing/candidate source of truth |
|---|---|
| planned | WorkPackage exists under an accepted PlanRevision |
| ready | dependency predicates are currently satisfied |
| bound/admitted | a WorkPackageAttempt linked to a canonical Task exists |
| running/etc. | canonical Task/Run projection only |
| blocked | one or more dependency predicates are unsatisfied/impossible |
| superseded route | immutable WorkPackageAttempt.supersedes_attempt_id chain |
| accepted | AcceptanceCommit exists for the outcome |

### Decision

Do **not** introduce a generic durable `work_unit_state` or node-state enum merely to cache these projections.

If a later scheduler wants a materialized readiness cache for performance, it must remain rebuildable/non-authoritative.

This substantially shrinks the Iteration 2 design.

---

# 7. Dependency contract

## 7.1 Current gap

Company Kernel v1 names dependency boundaries as part of the WorkPackage contract, but its schema does not currently provide a first-class immutable WorkPackage dependency relation or machine-readable dependency predicate table.

This is not a bug: V3-1B v1 explicitly excluded parallel candidate topology and runtime orchestration. It becomes a design requirement only when this research advances to concurrent WorkPackage scheduling.

## 7.2 Candidate dependency edge

A future immutable dependency relation needs at minimum:

```text
mission_id
plan_revision_id
upstream_work_package_id
upstream_outcome_id
downstream_work_package_id
requirement
optional evidence_selector_ref/hash
```

Edges belong to one exact PlanRevision and never change in place.

## 7.3 Dependency requirement vocabulary

One universal notion of "success" is not enough. A downstream synthesis branch and a deployment branch need different prerequisites.

Candidate minimal requirement set:

### `settled`

The upstream attempt is no longer capable of producing a new result without an explicit successor attempt.

Useful for comparison/synthesis tasks that must inspect failures as well as successes.

### `published_success`

Canonical Task/Run reached the required successful terminal classification and the exact result is durably published.

Useful where downstream work needs a mechanically completed artifact but does not require substantive executive acceptance.

### `accepted_outcome`

An exact AcceptanceCommit exists for the upstream route-independent outcome.

This should be the default for substantive dependencies between Company Kernel WorkPackages when downstream action relies on the upstream result being *correct*, not merely executed.

### `evidence_available`

A specified immutable evidence reference/hash exists even if the upstream substantive outcome was not accepted.

Useful for research branches, negative results, failed experiments, or post-mortem synthesis.

## 7.4 Why Task `completed` alone is insufficient

Task completion proves execution lifecycle. It does not prove that:

- the result was published;
- the result matches required evidence;
- the result is substantively correct;
- an executive/acceptance authority accepted the outcome.

Therefore dependency readiness must be an explicit plan-domain predicate, not hidden logic that equates process success with business/reasoning success.

## 7.5 Fan-in barriers

A downstream synthesis package can depend on each upstream package with `settled` or `evidence_available`, allowing it to run even if some branches failed.

A downstream mutation/deployment package should normally depend on `accepted_outcome`.

This gives fan-out/fan-in deterministic mechanics while preserving Sol/executive semantic judgment.

---

# 8. Task binding and idempotency

## 8.1 Existing facts

Canonical Task has one `controller_request_id` and normalized request hash. Replaying an identical request returns the existing Task; conflicting content under the same request identity fails.

WorkPackageAttempt already stores:

- `work_package_id`;
- `outcome_id`;
- one unique `task_id`;
- `route_request_hash`;
- route descriptor;
- optional `supersedes_attempt_id`;
- its own controller request and request hash.

The accepted architecture reserves WorkPackageAttempt + ProjectScope + Task atomically.

## 8.2 Candidate deterministic attempt-binding identity

Instead of a human/controller inventing an arbitrary retry key, a future coordinator can derive the attempt reservation identity from exact material such as:

```text
soma.company_kernel.attempt_binding.v1
mission_id
plan_revision_id
work_package_id
outcome_id
project_id
resource_id
scope_generation
supersedes_attempt_id | FIRST
route_request_hash
```

Hashing this material produces one stable reservation key for the same intended attempt.

### Properties

- response loss + exact replay returns the same attempt and same Task;
- changing provider/model/profile/route changes `route_request_hash` and therefore the attempt identity;
- retrying after a terminal/contained prior route changes `supersedes_attempt_id`, creating a new attempt even if the route configuration is otherwise identical;
- cross-scope replay cannot collide because scope identity participates;
- no semantic matching is used.

## 8.3 Task controller request identity

A candidate Task controller request could be deterministically namespaced from the immutable attempt identity, for example conceptually:

```text
task request identity = H("kernel-attempt-task-v1", attempt_id)
```

The exact string format remains a later implementation question. The important rule is one attempt -> one Task reservation identity.

---

# 9. Retry and successor taxonomy

"Retry" is too overloaded. Iteration 3 separates four layers.

## 9.1 Layer A - transport/internal transient retry

Examples:

- safe read-only HTTP retry;
- provider rate-limit retry;
- reconnecting a transport before outcome is known.

This may occur inside the same canonical Task/Attempt **only when the operation is proven retry-safe or protected by the same external idempotency identity**.

Temporal's current documentation is a useful reference: Activities are at-least-once, so idempotency is strongly recommended; a worker may complete an external effect and crash before reporting it, causing a retry. The idempotency key must remain stable across those retries.

## 9.2 Layer B - canonical backend recovery

Examples:

- Soma worker restart;
- exact provider-session resume;
- process relaunch where canonical recovery rules prove it is safe.

This stays the same Task/Attempt because no new substantive route was chosen.

If delivery/effect outcome is unknown, automatic resend is forbidden.

## 9.3 Layer C - route successor attempt

Examples:

- switch model/provider/profile;
- rerun after terminal failure;
- retry a reasoning route from a clean session after the prior session is invalid;
- repeat the same route after prior route is terminal/contained.

This is a **new WorkPackageAttempt + new canonical Task** under the same route-independent WorkPackage/outcome, with explicit `supersedes_attempt_id`.

The prior attempt is preserved as evidence.

## 9.4 Layer D - replan

If purpose, constraints, dependencies, acceptance basis, or route-neutral outcome contract changes materially, create a new PlanRevision and new WorkPackage/outcome identity.

This is not a retry.

## 9.5 External mutation ambiguity

If an external mutation may have happened but cannot be proven, neither Layer A nor Layer C may blindly repeat it.

The route remains uncertain until:

- the external system confirms the idempotency key/result;
- containment/effect evidence is established;
- or an explicit authority adjudicates a safe successor action.

---

# 10. Concrete evidence submission contract - research sketch

This is a design sketch, not production code or an accepted schema.

The contract intentionally separates worker claims from evidence identity and from canonical Task state.

```text
EvidenceSubmissionV1
  schema_version
  submission_id
  work_identity
    mission_id?
    plan_revision_id?
    work_package_id?
    outcome_id?
    attempt_id?
    task_id
    backend_ref?
  assignment
    contract_ref
    contract_hash
  producer
    backend_kind
    provider?
    model_or_profile?
    adapter_id?
    native_session_ref?
  submission_disposition
    complete | partial | blocked | uncertain
  executive_summary
  claims[]
  evidence[]
  artifacts[]
  uncertainties[]
  blockers[]
  usage
  provenance
  full_evidence_retrieval
  byte_accounting
```

`submission_disposition` describes the evidence submission, not Task lifecycle.

## 10.1 Claim record

Candidate fields:

```text
claim_id
claim_class = observation | inference | recommendation | negative_finding
subject_key?          # assignment-provided structured key, never semantic inference
statement
supports_evidence_ids[]
opposes_evidence_ids[]
uncertainty_ids[]
```

No global worker confidence is required.

If a domain genuinely has calibrated probabilities, those belong in domain evidence, not a generic "confidence" authority field.

## 10.2 Evidence record

Candidate fields:

```text
evidence_id
source_kind
source_ref
source_hash?
locator?              # line range, URL fragment, artifact offset, query key, etc.
observed_at?
content_type?
excerpt?              # tightly bounded optional excerpt
fact_key?             # only when assignment/domain provides one
fact_value?           # structured value for deterministic conflict checks
```

Full documents/logs/results stay behind references.

## 10.3 Artifact record

```text
artifact_ref
artifact_hash
media_type
role
```

## 10.4 Uncertainty record

```text
uncertainty_id
kind
statement
related_claim_ids[]
required_resolution?
```

Uncertainty is first-class evidence, not a reason to fabricate a best guess.

## 10.5 Blocker record

```text
blocker_id
kind
statement
related_dependency_ref?
requested_input_ref?
```

A worker may propose a next action, but retry authority remains outside the submission.

---

# 11. Fan-in envelope and deterministic vs semantic responsibilities

## 11.1 Candidate aggregate envelope

```text
FanInV1
  mission_id?
  plan_revision_id?
  synthesis_work_package_id?
  expected_unit_refs[]
  collected_unit_refs[]
  missing_unit_refs[]
  submissions[]            # compact identities/summaries/claim refs
  structured_conflicts[]   # exact-key conflicts only
  unresolved_uncertainties[]
  evidence_retrievals[]
  aggregate_usage
  truncated
  has_more
  response_bytes
```

## 11.2 What Soma may do deterministically

Soma can safely:

- validate schema/hash/reference integrity;
- verify assignment/work identity;
- enforce byte/count budgets;
- detect duplicate submission IDs/hashes;
- verify all expected units are represented or explicitly missing;
- group claims by assignment-provided `subject_key`;
- flag conflicting exact `fact_value` values under the same explicit `fact_key`;
- compute usage/latency/byte totals;
- provide retrieval pointers to complete evidence.

## 11.3 What Soma should not pretend to decide

Soma should not deterministically infer that two natural-language claims are semantically contradictory merely because embeddings or keyword similarity say so.

Soma should not decide substantive correctness from majority vote, model confidence, provider identity, or process success.

Those semantic functions remain with Sol or another named acceptance/reasoning authority.

## 11.4 Conflict adjudication flow

```text
structured fan-in
   -> exact structural conflicts flagged by Soma
   -> Sol reads claims/evidence refs
   -> if unresolved, request targeted evidence or one bounded verifier task
   -> Sol/executive accepts/rejects/synthesizes
```

The goal is targeted follow-up, not dumping every transcript into the root context.

---

# 12. Evidence budgets for the first benchmark

These are benchmark baselines, not production limits.

## Candidate baseline

- per-unit compact evidence submission target: **12 KiB**;
- per-unit hard benchmark maximum before externalizing detail: **32 KiB**;
- aggregate fan-in target: **48 KiB**;
- aggregate hard public envelope ceiling: **64 KiB**;
- full source/log/artifact bodies always referenced separately;
- maximum 8 primary claims per unit in the compact envelope;
- maximum 8 direct evidence references per claim;
- executive summary target <= 1 KiB per unit.

### Why 12 KiB

Canonical Task compact responses already use a 12 KiB default and 64 KiB public maximum. Aligning the experiment with existing Soma response economics makes the benchmark representative instead of designing an unlimited research-only format.

### Hypothesis

A structured 12 KiB submission containing claims + evidence pointers will preserve more synthesis quality per token than a larger free-form worker summary.

This must be tested rather than assumed.

---

# 13. 1 / 2 / 4 / 8 worker benchmark design

No experiment is run here. Iteration 3 freezes a candidate design so later execution cannot be tuned after seeing results.

## 13.1 Fairness principle

The **number of required work units stays fixed at eight**.

Worker count changes only the number of simultaneously available worker lanes:

```text
1 worker  -> processes 8 fixed units sequentially
2 workers -> 2 lanes over the same 8 units
4 workers -> 4 lanes over the same 8 units
8 workers -> 8 lanes over the same 8 units
```

This avoids the unfair comparison where the 8-worker condition is simply assigned eight times as much investigation.

Each work unit has the same immutable assignment/contract hash across conditions.

## 13.2 Benchmark family A - partitioned repository exploration

Create one frozen repository snapshot with eight independent target areas.

Each unit answers a bounded set of factual architecture questions with line/file evidence.

Gold set:

- predefined true findings;
- predefined planted/known edge cases;
- exact source references.

Measures coverage without external-web drift.

## 13.3 Benchmark family B - frozen-source research

Use eight frozen documents/source packets rather than live web for the primary reproducibility run.

Each unit extracts supported facts, disagreements, and uncertainty under the same evidence schema.

A later secondary run may use live web to test retrieval variability, but it should not be the only benchmark because source changes would confound worker-count comparisons.

## 13.4 Benchmark family C - adversarial architecture review

Freeze one design containing a known set of seeded flaws across eight concern areas, for example:

- duplicate authority;
- retry ambiguity;
- stale version acceptance;
- shared mutable-state race;
- missing cancellation ownership;
- evidence without provenance;
- hidden provider coupling;
- unbounded fan-in.

Workers receive independent review assignments. Sol synthesizes the fan-in without seeing the gold set.

## 13.5 Benchmark family D - recovery/reconnect

Later, with explicit authorization, interrupt one lane after durable reservation at a defined point and verify:

- completed units do not repeat;
- ambiguous units do not blindly resend;
- missing unit is recoverable from durable identity;
- Sol reconnect can reconstruct pending/complete work without conversation replay;
- duplicate external effects remain zero.

This family is designed now but not executed.

## 13.6 Metrics

### Quality

- true-positive findings;
- false-positive/unsupported findings;
- recall against gold set;
- precision;
- evidence coverage ratio;
- unsupported-claim rate;
- unresolved contradiction count;
- final Sol synthesis correctness.

### Duplication / coordination

- duplicate finding rate;
- pairwise claim overlap;
- redundant evidence retrieval count;
- number of cross-worker conflicts;
- number of targeted follow-up requests required.

### Performance

- wall-clock time to all required units settled;
- time to first useful evidence;
- worker idle time;
- scheduling overhead;
- fan-in assembly latency;
- Sol synthesis latency.

### Cost/context

- worker input/output tokens;
- root synthesis input/output tokens;
- total tokens;
- provider-reported cost where available;
- compact evidence bytes;
- full evidence bytes retrieved by Sol;
- proportion of full evidence that actually had to enter synthesis context.

### Durability

- replayed completed units (target 0);
- duplicate mutation/effect count (target 0);
- uncertain units safely preserved;
- reconnect reconstruction success.

## 13.7 Repetition

Candidate first execution plan: three repetitions per worker-count condition per benchmark family, with fixed assignment ordering rotated between repetitions.

More repetitions may be needed if latency/model variance is high. The experiment should report distributions, not only the best run.

## 13.8 Primary hypothesis

Four workers may provide the best latency/coverage/synthesis-burden tradeoff on many eight-unit read-heavy tasks; eight may improve latency on highly independent work but increase token duplication, coordination, and fan-in burden.

This remains a hypothesis. OpenAI currently recommends a default Multi-agent concurrency of 3 for most workloads, which is useful external evidence that "maximum parallelism" should not be assumed optimal, but it is not a Soma benchmark result.

---

# 14. Mutation admission

## 14.1 Default rule

Parallel worker/reasoning fan-out is **read-only by default**.

Having reasoning capability does not imply mutation authority.

## 14.2 Candidate protected-action mandate

Before a WorkPackageAttempt may mutate an external/repository resource, Soma should be able to prove a mandate containing or referencing at minimum:

```text
mission_id
plan_revision_id
work_package_id
outcome_id
attempt_id
task_id
project_id
resource_id
scope_generation
action_class
allowed mutation scope
prohibited actions
idempotency identity / external idempotency key when applicable
expiry / version
issuer / accountable owner / acceptance authority
```

The exact record type belongs to later authority/capability work; this iteration defines only the requirement.

## 14.3 Single-writer rule

For mutation-capable work:

- many read-only workers may inspect the same resource;
- at most one active writer mandate owns the same mutation scope/resource unless the domain explicitly proves commutativity/isolation;
- writers to demonstrably independent resources may run concurrently;
- repository/worktree mutation should use exact ownership/lock boundaries rather than optimistic model cooperation.

## 14.4 Current OpenAI Multi-agent implication

Current Responses Multi-agent gives every agent in the tree access to the tools configured for that request.

Therefore a future Soma OpenAI reasoning-backend adapter should initially expose **read-only tools only** to a hosted Multi-agent tree unless Soma can mechanically enforce per-call/per-agent mutation authority at the broker boundary.

Do not rely on the root model's prompt to prevent a child from using a tool that the API exposes to every agent.

## 14.5 Unknown mutation outcome

If a mutating call is attempted and its result is unknown:

- freeze automatic retry;
- retain resource ownership/quarantine as required;
- query the external system by exact idempotency/effect identity where possible;
- require containment/effect adjudication before a successor route receives overlapping write authority.

---

# 15. Reconciliation with modern durable orchestration references

## 15.1 LangGraph

Current LangGraph persistence reinforces several useful patterns:

- checkpoint state at graph super-step boundaries;
- persist successful node writes even when another parallel node in the same super-step fails;
- resume without rerunning already-successful nodes;
- explicit node retry policies;
- bounded `max_concurrency`;
- separate input/output schemas and state reducers.

The relevant lesson for Soma is **persist branch completion before fan-in and never replay successful branches merely because another branch failed**.

Soma already has stronger domain authority separation than a generic graph state object, so this remains a reference pattern rather than a migration argument.

## 15.2 Temporal

Current Temporal guidance reinforces:

- deterministic orchestration should not be the place for failure-prone side effects;
- side-effecting Activities are at-least-once and should be idempotent;
- transient and permanent failures require different retry treatment;
- a stable external idempotency key must survive Activity retry;
- retrying an entire workflow is generally the wrong response to a local side-effect failure.

This strongly supports the Iteration 3 four-layer retry taxonomy and Soma's existing "outcome unknown -> no blind resend" rule.

---

# 16. Future normal-Chat integration boundary

This research does not redesign the separate normal-Chat tool UX implementation.

The only future integration point remains:

```text
one meaningful Chat/Sol action
   -> one durable mission/plan operation or one atomic Task
   -> Soma internally admits bounded WorkPackages/Attempts/Tasks when applicable
   -> workers/backends produce structured evidence
   -> one bounded fan-in result
   -> Sol synthesizes one coherent answer
```

## Key constraint

A future high-level Chat action should be an **adapter over existing canonical identities**, not a new orchestration identity.

For decomposed company-style work, it should create/select/reconcile Mission/PlanRevision/WorkPackage facts and canonical Tasks rather than creating a parallel `WorkPlan` lifecycle.

For atomic work, it should continue to use canonical Task directly.

Exactly how many company-domain transitions one public call may atomically request remains unresolved. Existing V3-1B `reconcile_one` intentionally performs at most one transition, which is excellent for authority proof but potentially too chatty for a future one-action user experience. That question belongs in a later integration iteration, not this normal-Chat UX thread.

---

# 17. Facts, inferences, hypotheses, rejected ideas, and bugs

## Facts

1. Company Kernel v1 already defines Mission, PlanRevision, WorkPackage, WorkPackageAttempt and AcceptanceCommit identities while keeping execution state in Task/Run.
2. Company Kernel runtime capability remains inactive; the current store exposes schema inspection/migration only.
3. PlanRevision and WorkPackage rows are immutable and current plan selection is a Mission compare-and-set pointer.
4. WorkPackage outcome identity includes PlanRevision and excludes route/provider/session/Task/Run details.
5. WorkPackageAttempt links one route-specific attempt to one unique canonical Task and supports an immutable supersession chain.
6. Company Kernel v1 only permits `single_active` attempt topology for one outcome.
7. AcceptanceCommit is unique by outcome and binds one exact published Task/Run result.
8. Company Kernel v1 does not currently define a first-class dependency edge table for WorkPackages.
9. Canonical Task remains single-kind/single-backend in the current source (`durable_command` / `soma_durable_run`).
10. Current OpenAI Responses Multi-agent is beta for GPT-5.6, provides hosted agent-tree actions/status, defaults/recommends max concurrent subagents of 3, and gives all tree agents the request's available tools.
11. OpenAI recommends one agent rather than Multi-agent for shared mutable-resource contention or fixed deterministic execution graphs.
12. OpenAI Agents SDK exposes final output, rich run items, raw responses, resumable RunState, and immutable outer tool-call metadata for nested agent-as-tool runs.
13. Current Codex subagents return summaries to the main thread and inherit parent permissions by default; custom agents can override sandbox configuration such as read-only mode.
14. LangGraph persists successful parallel-node writes so completed branches need not rerun after another branch fails.
15. Temporal documents at-least-once Activity execution and recommends stable idempotency keys across retries.

## Inferences

1. Creating a new canonical `WorkPlan` identity would likely duplicate Company Kernel plan-domain authority.
2. Mission -> PlanRevision -> WorkPackage -> Attempt -> Task is a cleaner mission-level decomposition stack than root Task -> child Task graph alone.
3. Most proposed work-node disposition state can be derived and should not be persisted canonically.
4. Dependency satisfaction needs typed predicates; Task completion is not a sufficient universal prerequisite.
5. A hosted native subagent tree is often best treated as internal implementation of one reasoning Task rather than mirrored one-for-one into TaskStore.
6. A compact evidence contract should emphasize claim-to-evidence linkage, hashes, provenance, and uncertainty rather than worker confidence.
7. Current OpenAI Multi-agent shared-tool visibility makes direct mutating tools unsafe as a default reasoning-backend capability.
8. The fairest 1/2/4/8 benchmark keeps eight immutable work units constant and varies only available concurrency.

## Hypotheses to test later

1. 12 KiB structured evidence submissions will preserve synthesis quality while materially reducing context compared with free-form worker transcripts.
2. Four lanes will often dominate eight on total cost/duplication while retaining most latency benefit for eight-unit read-heavy work.
3. Explicit dependency requirements (`settled`, `published_success`, `accepted_outcome`, `evidence_available`) are sufficient for the first concurrent WorkPackage DAG.
4. New-plan packages can safely reuse prior accepted work through explicit evidence lineage without weakening plan-specific outcome identity.
5. One reasoning Task backed by a native multi-agent tree can improve coverage without requiring Soma to understand the provider's internal child lifecycle.

## Rejected ideas

- **New generic WorkPlan as a canonical mission-level identity.** Rejected as leading design after discovery of Company Kernel overlap.
- **Root Task owns the plan.** Rejected for mission-level work because Task is execution identity, not plan authority.
- **Persist `planned/ready/bound/blocked` as another generic lifecycle.** Rejected; derive these facts.
- **Task completed == dependency satisfied for every edge.** Rejected.
- **Reuse old outcome silently when a new PlanRevision has equivalent text.** Rejected.
- **Every native provider subagent becomes a canonical Task.** Rejected.
- **Worker confidence controls fan-in or acceptance.** Rejected.
- **Expose mutation tools to every hosted reasoning subagent and rely on prompts to behave.** Rejected.
- **Blindly retry an ambiguous external mutation.** Rejected.
- **Change amount of work when comparing 1/2/4/8 workers.** Rejected as an invalid benchmark.

## Confirmed bugs

None recorded in Iteration 3.

Two architecture gaps/risks are explicitly **not bugs** because the relevant runtime capability is inactive/excluded today:

- Company Kernel v1 has no first-class concurrent WorkPackage dependency relation yet.
- replan semantics do not yet define a broad mutation-era policy for disposition/revocation of already-running old-plan attempts.

---

# 18. Iteration 3 architecture after correction

```text
                              ChatGPT / Sol
                           semantic reasoning head
                                    |
                       +------------+-------------+
                       |                          |
                atomic bounded work        decomposed mission
                       |                          |
                  canonical Task                Mission
                       |                          |
                    backend                 PlanRevision
                       |                    /     |      \
                    evidence         WorkPackage WorkPackage WorkPackage
                                           |          |          |
                                        Attempt    Attempt    Attempt
                                           |          |          |
                                         Task       Task       Task
                                           |          |          |
                                        backend    backend    reasoning backend
                                                                   |
                                                        optional native subagent tree
                                           \          |          /
                                            structured evidence
                                                   |
                                              bounded fan-in
                                                   |
                                             Sol adjudication
                                                   |
                                          Acceptance / synthesis
```

The provider/native-agent tree is below the canonical Task boundary unless it independently needs Soma-level work ownership.

---

# 19. Iteration 3 decisions

### Leading decisions

1. **Retire `WorkPlan` as a proposed new canonical identity.** Reuse Mission/PlanRevision/WorkPackage for mission-level decomposition.
2. **Do not create a root Task merely to own a work graph.** Task remains execution-attempt identity.
3. **Do not add a work-unit mini-lifecycle.** Derive readiness/binding/blocking from immutable plan/package/dependency/attempt plus Task/Run state.
4. **Model dependencies explicitly and type their satisfaction predicate.** Default substantive dependency should require accepted outcome, not process completion.
5. **One WorkPackageAttempt maps to one canonical Task.** Provider-native subagents remain subordinate unless independently durable.
6. **Route retry creates a successor Attempt/Task; backend recovery stays same Attempt/Task; replan creates new plan/outcome.**
7. **Evidence fan-in is claims + provenance + references + uncertainty, not transcript aggregation.**
8. **Deterministic Soma fan-in performs structural validation only; Sol handles semantic conflict/adjudication.**
9. **Parallel work is read-only by default; mutation requires exact resource/mandate/idempotency ownership.**
10. **Benchmark eight fixed work units at concurrency 1/2/4/8.** Do not vary the required work.

These are research decisions/candidates, not authorization to implement them.

---

# 20. Next research questions - Iteration 4

1. **Dependency representation:** Should WorkPackage dependency edges be explicit immutable rows, canonical content inside PlanRevision, or both with hash-verified consistency?
2. **Graph validation:** What exact constraints prevent cycles, cross-plan edges, stale package keys, and dependency predicates that can never become true?
3. **Parallel package creation:** How should one accepted PlanRevision atomically define a bounded package set/graph without making `reconcile_one` an unbounded scheduler?
4. **Cross-plan evidence reuse:** Define an explicit carry-forward/adoption contract that can reuse prior accepted evidence without collapsing outcome identity.
5. **Active old-plan work:** Define exact replan dispositions for read-only vs mutating in-flight attempts and how mandate revocation/cancellation/containment interacts with plan currency.
6. **Parallel candidates for one outcome:** When is a future topology allowing multiple concurrent attempts for the same WorkPackage useful, and how does one-winner acceptance avoid wasted mutation or duplicated effects?
7. **Reasoning backend contract:** Define the provider-neutral start/query/cancel/result/evidence interface for a strong model backend, including Responses Multi-agent/Agents SDK mapping.
8. **Native subagent provenance:** Determine which stable agent-path/tool-call/session metadata OpenAI exposes sufficiently to preserve evidence provenance without pretending it is canonical Soma identity.
9. **Evidence schema validation:** Turn `EvidenceSubmissionV1` and `FanInV1` into strict research-only JSON/Pydantic examples and test them against four synthetic worker types without production implementation.
10. **Benchmark corpus:** Freeze the exact repo/source/adversarial benchmark packets and gold answers before any 1/2/4/8 execution.
11. **Budget sensitivity:** Compare 6/12/24 KiB evidence submissions and 24/48/64 KiB aggregate fan-in limits in the benchmark design.
12. **Normal-Chat high-level action:** Research whether one user-visible action can safely reserve a whole bounded plan/package graph while preserving Company Kernel transaction/authority invariants, without changing the separate UX thread.

Iteration 3 ends here. No worker/model experiment was launched.

---

# Sources consulted

## Soma repository evidence

- `soma/company_kernel/models.py`
- `soma/company_kernel/schema.py`
- `soma/company_kernel/store.py`
- `docs/V3_1B_KERNEL_OF_ONE_ARCHITECTURE_GATE_2026-08-02.md`
- `docs/V3_1B_KERNEL_OF_ONE_ARCHITECTURE_PROPOSAL_2026-08-02.md`
- `docs/V3_1B_KERNEL_OF_ONE_ARCHITECTURE_ACCEPTANCE_AUDIT_2026-08-02.md`
- `docs/V3_1B_SCHEMA_MODELS_1_GATE_2026-08-02.md`
- `docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`
- `soma/tasks/models.py`
- `soma/tasks/backends.py`
- `soma/parallel_groups.py`
- Iteration 1 and Iteration 2 agent-worker research journals

## Current official OpenAI primary sources

- Responses API Multi-agent: https://developers.openai.com/api/docs/guides/responses-multi-agent
- Responses API Background mode: https://developers.openai.com/api/docs/guides/background
- OpenAI Agents SDK results/state: https://openai.github.io/openai-agents-python/results/
- OpenAI Agents SDK agents/orchestration: https://openai.github.io/openai-agents-python/agents/
- OpenAI ChatGPT/Codex Subagents: https://learn.chatgpt.com/docs/agent-configuration/subagents
- GPT-5.6 model/tool guidance: https://developers.openai.com/api/docs/guides/latest-model

## Modern orchestration reference sources

- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph Graph API / retry/concurrency: https://docs.langchain.com/oss/python/langgraph/use-graph-api
- Temporal Python developer guide: https://docs.temporal.io/develop/python
- Temporal Python error handling/idempotent activities: https://docs.temporal.io/develop/python/best-practices/error-handling
