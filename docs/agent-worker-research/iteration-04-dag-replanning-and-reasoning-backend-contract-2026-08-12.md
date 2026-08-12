# Iteration 4 - DAG, Replanning, and Reasoning Backend Contract

Date: 2026-08-12
Status: research only
Scope: immutable dependency graph representation, dependency satisfaction proofs, replanning/carry-forward semantics, active old-plan work, candidate topology, provider-neutral reasoning backend, native-agent provenance, and evidence-contract validation

## Guardrails

This iteration is research only. It does not authorize production implementation, schema migration, runtime activation, worker/model launch, benchmark execution, service restart, connector refresh, Hermes configuration change, commit, push, or changes to the separate normal-Chat tool UX implementation thread.

Only this journal file is authored by the agent-worker research thread.

At Iteration 4 start, Soma remained on `lane/memory-integration-foundation-1` at HEAD `b53404fa9600412a4b3dd0fafd664a856096257b`. The shared worktree already contained separate concurrent normal-Chat UX work, including tracked modifications to `soma/gateway_models.py`, `soma/server.py`, and `tests/test_tool_gateway_models.py`, plus untracked metadata/tests. Those files were not modified by this research iteration and are not evidence for the conclusions here.

Iteration 3 remains the immediate baseline, with these corrections already accepted as research conclusions:

- no new canonical `WorkPlan` identity;
- Mission / PlanRevision / WorkPackage / WorkPackageAttempt remain the leading company-domain decomposition identities;
- Task remains execution-attempt lifecycle identity;
- no separate work-unit state machine;
- worker roles remain profiles over capabilities/authority rather than hard canonical classes;
- provider-native subagents stay subordinate to one Task unless Soma requires independent durable ownership.

No model or agent worker was launched during Iteration 4. One deterministic local schema-validation exercise was performed in-memory against synthetic records only; it touched no repository or production state.

---

# 1. Exact questions investigated

1. Where should immutable WorkPackage dependency edges live: inside PlanRevision content, separate normalized rows, WorkPackage contracts, or some combination?
2. How can Soma validate a complete DAG before execution without creating mutable graph lifecycle state?
3. What exact constraints prevent cycles, cross-plan edges, stale package references, ambiguous dependency logic, and impossible predicates?
4. When a dependency is satisfied, what exact evidence identity must be frozen into the downstream attempt so later retries cannot silently change its inputs?
5. Can one accepted PlanRevision define a whole bounded package graph atomically without turning `reconcile_one` into a scheduler?
6. What can be safely reused across PlanRevisions: evidence, accepted outcomes, or both?
7. What should happen to old-plan Tasks that are still running when a new PlanRevision becomes current?
8. Should Soma support multiple concurrent WorkPackageAttempts for the same route-independent outcome in the first worker architecture?
9. What provider-neutral backend contract should represent a strong reasoning worker without making OpenAI, Codex, or any other provider canonical?
10. Which current OpenAI Responses Multi-agent / Agents SDK / Codex identifiers are strong enough for evidence provenance, and which are too provider-local or unstable to become Soma identity?
11. Can the Iteration 3 `EvidenceSubmissionV1` and `FanInV1` sketches actually validate execution, retrieval, scout, and reasoning submissions under one strict shape?
12. What research remains before freezing the 1/2/4/8 benchmark corpus and running any model experiments?

---

# 2. Repository facts relevant to Iteration 4

## 2.1 Company Kernel v1 still has no first-class dependency table

`Soma/company_kernel` currently contains Company, Mission, PlanRevision, WorkPackage, WorkPackageAttempt, AcceptanceCommit, and reconciliation schema/models.

The schema contains no immutable dependency-edge table. The accepted V3-1B architecture says WorkPackage contracts include dependency boundaries, but the source does not yet make those boundaries a machine-queryable graph relation.

This is intentional scope, not a bug. The accepted V3-1B first proof explicitly fixed WorkPackage topology to `single_active` and excluded parallel candidate topology/runtime orchestration.

## 2.2 PlanRevision is already the right graph identity

`PlanRevision` is:

- immutable;
- content-addressed through canonical JSON/hash;
- versioned by Mission;
- linked to its parent revision;
- selected as current through one Mission compare-and-set pointer.

Therefore the dependency graph should be a property of one exact PlanRevision. A mutable graph underneath an unchanged PlanRevision would violate the meaning of immutable accepted planning truth.

## 2.3 WorkPackage already owns route-neutral work intent

`WorkPackage` is immutable and route-neutral. Provider, model, argv, environment, session, Task, Run, PID, and worker identity are excluded from route-independent outcome identity.

This is exactly the right node abstraction for a deterministic company-level DAG.

## 2.4 WorkPackageAttempt already binds route choice to Task

Each WorkPackageAttempt links one route-specific attempt to exactly one canonical Task and preserves the route request hash plus optional supersession lineage.

This means dependency readiness should lead to WorkPackageAttempt/Task admission, not to a second runnable node lifecycle.

## 2.5 Current mutation serialization is narrower than the future company graph

Current repository mutation safety includes:

- repository-wide `OperationLockStore` ownership keyed by `repo_name` for current durable repository mutation;
- Hermes `ResourceMutationLocks` keyed by an explicit `resource_key`, serializing same-resource tool mutations while unrelated/read-only calls remain concurrent;
- ProjectScope resource/repository binding and Task/Run attempt coherence;
- task/run cancellation and containment evidence.

These are useful implementation precedents, but a future company-level mutation admission rule still needs one explicit resource/mandate contract that is independent of Hermes and not limited to repository-wide locks.

---

# 3. Dependency representation options

## Option A - dependencies only inside each WorkPackage contract

Example conceptually:

```text
WorkPackage B.contract.depends_on = [A]
```

### Advantages

- no new table;
- route-neutral and immutable;
- simple to serialize.

### Problems

- package-by-package definition means Soma cannot prove the complete graph is acyclic until all packages exist;
- there is no clean machine-level notion of a complete package set for one revision;
- forward references and partial graphs complicate restart/replay;
- dependency scans require parsing opaque contract JSON;
- atomic plan acceptance and graph validation become awkward.

### Decision

Not preferred for concurrent scheduling.

## Option B - dependencies only as separate immutable rows

Example conceptually:

```text
work_package_dependencies
  plan_revision_id
  upstream_work_package_id
  downstream_work_package_id
  requirement
  selector_ref/hash
```

### Advantages

- relational foreign keys and indexes;
- easy DAG queries and readiness checks;
- immutable edges can be validated transactionally.

### Problems

- without a content-addressed graph manifest, a PlanRevision hash does not necessarily bind the complete graph shape;
- adding/removing edges after plan selection would mutate accepted plan meaning even if rows themselves were append-only;
- need an exact definition of when the edge set is complete.

### Decision

Useful normalized representation, but insufficient alone.

## Option C - PlanRevision graph manifest plus immutable normalized child facts

This is the leading design.

One PlanRevision request carries a bounded, canonical graph manifest. The manifest is content-addressed and participates in accepted PlanRevision identity. The transaction then creates/validates:

- the immutable PlanRevision;
- every declared WorkPackage node;
- every immutable dependency edge;
- the current-plan compare-and-set pointer.

The graph is complete at the instant the PlanRevision becomes current.

The important authority rule is that the relational child records are not independently editable plan truth. They are the normalized durable facts of the exact content-addressed graph manifest. A consistency hash binds the complete set.

Candidate manifest:

```text
PlanGraphManifestV1
  graph_contract_version
  mission_id
  package_nodes[]
    package_key
    work_package_contract_hash
    target_resource_id
    evidence_requirements_hash?
  dependency_edges[]
    upstream_package_key
    downstream_package_key
    requirement
    evidence_selector_hash?
```

Candidate graph identity:

```text
graph_manifest_hash = H(
  domain = soma.company_kernel.plan_graph.v1,
  canonical_json(PlanGraphManifestV1)
)
```

`plan_contract_json` can bind the manifest through exact graph version/ref/hash rather than carrying an independently mutable copy.

### Decision

**Leading recommendation: PlanRevision is the immutable graph commit.** WorkPackages and dependency edges are normalized child facts bound to the same graph manifest hash.

This is a future architecture proposal only. It does not change current Company Kernel v1 source.

---

# 4. Atomic graph definition without a scheduler

The earlier V3-1B proposal described separate transitions for accepting a plan and defining one WorkPackage. That is appropriate for the original Kernel-of-One proof, but a concurrent worker graph benefits from a stronger boundary.

## Candidate future graph-capable PlanRevision transaction

Inside one bounded `BEGIN IMMEDIATE` transaction:

1. validate exact active ProjectScope generation;
2. validate Mission and expected current PlanRevision/state version;
3. validate accepted authority;
4. canonicalize the complete bounded graph manifest;
5. validate package-key uniqueness and contract hashes;
6. validate every dependency endpoint exists in the same manifest;
7. validate dependency vocabulary/selectors;
8. validate the graph is acyclic;
9. insert/verify immutable PlanRevision;
10. insert/verify every immutable WorkPackage declared by the manifest;
11. insert/verify every immutable dependency edge;
12. verify the normalized child-set hash equals the manifest hash;
13. compare-and-set Mission current PlanRevision and version counters;
14. commit.

Failure before commit leaves the prior plan current and no partial new graph.

Failure after commit leaves one complete new PlanRevision graph current.

## Why this is not a scheduler

Creating immutable graph facts is one company-domain plan transition. It does not:

- decide runtime Task state;
- loop over ready work forever;
- launch providers;
- retry Tasks;
- own worker leases;
- accept outcomes;
- mutate the graph after acceptance.

A later bounded coordinator may inspect the immutable graph and admit eligible WorkPackageAttempts, but graph creation itself remains a single deterministic authority transition.

## Boundedness

The future gate must choose explicit maximum package/edge counts before implementation. Iteration 4 does not freeze those numbers. The existing Workflow limit of 50 steps is useful precedent, not a required Company Kernel limit.

---

# 5. Exact DAG validation rules

A graph-capable PlanRevision should fail before becoming current if any rule below is violated.

## 5.1 Identity and scope

- every package belongs to the exact same Mission and PlanRevision;
- every package key is unique within the revision;
- every dependency endpoint resolves to one package in that same revision;
- cross-Mission and cross-PlanRevision edges are forbidden in the first graph version;
- package ProjectScope resource/generation must match the Mission ceiling.

Cross-plan evidence reuse is handled separately; it is not represented as a dependency edge.

## 5.2 Structural graph rules

- no self-edge;
- no duplicate canonical edge;
- no directed cycle;
- edge order in input does not affect graph identity;
- package order in input does not affect graph identity;
- all edges are conjunctive in graph v1: all declared prerequisites must be satisfied.

`OR`, threshold, quorum, voting, and arbitrary boolean dependency expressions are deferred. They add semantic/scheduling complexity and are unnecessary for the first worker proof.

## 5.3 Requirement vocabulary

Iteration 3's four candidate requirements remain useful:

### `accepted_outcome`

Satisfied only by one exact upstream AcceptanceCommit.

This remains the default for substantive dependencies where the downstream action relies on the upstream result being accepted as correct.

### `published_success`

Satisfied only by one exact successful canonical published result identity/hash.

Useful when mechanical successful artifact production is sufficient and executive acceptance is intentionally not required.

### `evidence_available`

Satisfied by one exact evidence reference/hash matching the edge's declared selector.

Useful for research, negative results, comparison, investigation, and synthesis.

### `settled`

Satisfied by exact terminal/containment evidence for the relevant upstream attempt set such that no existing attempt can continue producing a different result without an explicit successor attempt.

Useful for downstream comparison/post-mortem work that must proceed after failure as well as success.

## 5.4 Selector validation

An `evidence_available` edge must not contain an unbounded natural-language query that Soma must semantically interpret.

The selector should be an opaque reference/hash to a versioned evidence requirement defined by the upstream/downstream contracts.

Mechanical readiness checks resolve exact references/hashes. Semantic evidence adequacy remains with Sol/acceptance authority.

---

# 6. New important rule: freeze dependency satisfaction at admission

A graph predicate can be true at one moment and later acquire new evidence or a successor attempt. A downstream Task must not silently change its inputs after admission.

Therefore readiness evaluation needs a durable **dependency satisfaction proof** bound into the downstream attempt request/assignment.

Candidate research contract:

```text
DependencySatisfactionProofV1
  dependency_edge_ref
  requirement
  upstream_work_package_id
  upstream_outcome_id
  satisfying_authority_kind
  satisfying_ref
  satisfying_hash
  observed_task_or_kernel_version?
  observed_at
```

Examples:

- `accepted_outcome` -> exact `acceptance_commit_id` plus commit/effect hash;
- `published_success` -> exact Task/Run plus `result_published_hash` and public source hash;
- `evidence_available` -> exact evidence ref/hash selected by the declared evidence selector;
- `settled` -> exact terminal/containment attempt evidence and relevant state/result hash.

## Binding rule

The downstream WorkPackageAttempt's deterministic request hash must include the canonical set of dependency satisfaction proofs.

Consequences:

- response loss/replay returns the same downstream Task;
- a later upstream successor cannot silently alter an already-running downstream assignment;
- if new upstream evidence should change downstream work, create a successor downstream attempt or a new PlanRevision depending on whether route-neutral intent changed;
- restart reconstruction never needs to ask "what was ready at the time?" - the exact proof is already durable.

This closes a time-of-check/time-of-use gap that was not explicit in Iteration 3.

---

# 7. Cross-PlanRevision carry-forward

## 7.1 Outcome identity deliberately does not carry forward

Current route-independent `outcome_id` includes `plan_revision_id`.

Therefore an accepted outcome from PlanRevision N is not the same canonical outcome under PlanRevision N+1, even when a package looks textually similar.

This is useful. Replanning can change assumptions, dependencies, constraints, or acceptance context without mutating old truth.

## 7.2 Evidence can carry forward

A new WorkPackage may receive prior immutable evidence as an input/basis:

- prior AcceptanceCommit reference/hash;
- prior published result hash;
- prior EvidenceSubmission reference/hash;
- prior artifact hash;
- prior research/knowledge references where policy permits.

This is **evidence reuse**, not identity reuse.

## 7.3 Mechanical carry-forward checks

Before prior evidence is presented as reusable, Soma can mechanically verify exact facts such as:

- same project/resource/scope generation where required;
- prior source/result hash still matches durable evidence;
- evidence format/schema remains supported;
- declared freshness/expiry has not elapsed;
- immutable contract subsets explicitly marked as reuse-critical remain byte/hash identical.

Soma cannot mechanically decide that two changed natural-language contracts are semantically equivalent merely because they look similar.

## 7.4 Substantive compatibility remains a reasoning/acceptance judgment

If the new plan changed assumptions but Sol/executive judges old evidence still sufficient, that judgment should be recorded as acceptance/deliberation basis.

Do not use embeddings or model confidence as canonical compatibility identity.

## 7.5 Current v1 limitation

Current AcceptanceCommit requires an exact WorkPackageAttempt, Task, Run, and published result.

Therefore current Company Kernel v1 cannot represent "new outcome accepted purely by adopting a prior plan's AcceptanceCommit with no new Task".

Iteration 4 explicitly refuses to fake that by creating a no-op execution Task.

### First-proof recommendation

If a new-plan outcome can be cheaply confirmed from old evidence, create a bounded verification/reasoning Task that consumes the old evidence and publishes a new exact result for the new WorkPackage.

### Possible later extension

Only if measurements show significant redundant work, research a dedicated acceptance-adoption authority such as an `AcceptanceAdoption` fact or a versioned AcceptanceCommit basis variant. Such an extension would need:

- exact old AcceptanceCommit identity;
- compatibility proof references/hashes;
- current-plan acceptance authority;
- one-winner uniqueness for the new outcome;
- no fabricated Task/Run execution.

This extension is deferred.

---

# 8. Replanning while old-plan work is active

## 8.1 Plan currency is not cancellation

Selecting a new current PlanRevision changes company planning truth. It does not prove an already-started Task stopped.

This distinction is already consistent with Soma's organisational contract: revocation/cancellation and operational quiescence are separate facts.

## 8.2 Read-only old-plan work

Leading default:

- allow already-running read-only old-plan work to finish unless an authority explicitly cancels it;
- preserve its result/evidence;
- do not let it create new old-plan attempts after the new plan becomes current;
- do not automatically treat its outcome as accepted under the new plan;
- allow the new plan to consume the evidence explicitly if useful.

This avoids wasting harmless research already in flight.

## 8.3 Mutating old-plan work

A new PlanRevision may become current while an old Task still owns a mutation, but new conflicting mutation must remain blocked until the old mutation is terminal or mechanically contained/quiescent.

The authoritative controls remain:

- Task/Run cancellation and recovery;
- operation/resource lock ownership;
- process/provider containment evidence;
- mandate/revocation authority;
- external effect/idempotency evidence.

Plan selection alone must never release a lock or grant a competing writer.

## 8.4 Explicit authority actions

If the new plan makes an old Task undesirable, the executive/Sol may separately request:

- cancellation;
- mandate revocation/narrowing;
- containment;
- or deliberate continuation for evidence.

Those actions target the exact old Task/mandate/resource. They are not hidden side effects of changing `current_plan_revision_id`.

## 8.5 Uncertain old mutation

If Soma cannot prove whether the old mutation completed or can still mutate:

- retain ownership/quarantine as required;
- block conflicting new mutation;
- do not blindly retry either route;
- require external idempotency/effect evidence or explicit adjudication.

This keeps replanning from becoming a duplicate-effect escape hatch.

---

# 9. Parallel candidate attempts for one outcome

Current WorkPackage topology is `single_active`.

Iteration 4 considered a future topology allowing several concurrent attempts under one route-independent outcome.

## Potential benefit

For read-only reasoning/research, several independent routes can provide diversity and reduce correlated blind spots.

## Problems

- current AcceptanceCommit selects one attempt/result;
- multiple canonical attempts increase cost and fan-in burden;
- same-outcome attempts are harder to distinguish from duplicate work;
- any mutation makes competing attempts dangerous;
- if multiple results must be combined, the real work is a synthesis outcome rather than simply "choose one attempt."

## Decision for the first worker architecture

**Keep canonical WorkPackageAttempt topology `single_active`.**

Use one of two cleaner patterns for parallel intelligence:

1. model independent branches as separate WorkPackages in the immutable PlanRevision graph, with a downstream synthesis WorkPackage; or
2. let one reasoning Task use a provider-native subordinate subagent tree internally and publish one bounded evidence submission.

A future `parallel_evidence` attempt topology should be researched only if benchmarks show a material need that these two patterns cannot satisfy.

Mutation-capable parallel candidates remain out of scope.

---

# 10. Provider-neutral strong reasoning backend

## 10.1 Do not make OpenAI the Task identity

The canonical Task backend should name a provider-neutral execution class, conceptually something like:

```text
backend_kind = soma_reasoning_run
```

Provider/model/mode belong to the route-specific backend identity/descriptor, for example:

```text
provider = openai
model = gpt-5.6-sol
mode = responses_multi_agent
```

A future Claude, Codex, local model, or other strong provider should fit without changing WorkPackage/outcome identity.

## 10.2 Reuse the existing backend shape

The current `ExecutionBackend` protocol already has a useful minimal lifecycle shape:

- `reserve()`
- `start(...)`
- `query(...)`
- `cancel(...)`
- `result_reference(...)`

Iteration 4's leading recommendation is to generalize that concept into a provider-neutral Task backend contract rather than invent a second "agent lifecycle" API.

Candidate abstract shape:

```text
TaskBackend
  capabilities()
  reserve() -> soma-owned backend_ref
  start(spec, backend_ref) -> durable start receipt
  query(backend_ref) -> bounded observation
  cancel(backend_ref) -> cancellation receipt
  result_reference(backend_ref) -> exact published result identity
  evidence_reference(backend_ref) -> bounded provenance/evidence retrieval
```

The exact method/type names are not frozen.

## 10.3 ReasoningSpec - reference-first input

Candidate research fields:

```text
ReasoningSpecV1
  assignment_ref
  assignment_hash
  context_refs[]
  dependency_satisfaction_proofs[]
  output_contract_ref/hash       # EvidenceSubmissionV1 or successor
  tool_policy_ref/hash
  authority_ref/hash
  provider_route_ref/hash
  budgets
    wall_time
    output_bytes
    token/cost limits if policy supports them
    provider-internal concurrency limit
  continuation_policy
```

Large prompts, repository snapshots, secrets, and full evidence bodies should stay behind controlled references rather than being copied into canonical Task rows.

## 10.4 Backend reference ownership

`backend_ref` should be Soma-owned and reserved before provider launch, just as the current durable-run backend reserves a Run identity before starting work.

Provider-native IDs are subordinate bindings:

- OpenAI `response_id`;
- Agents SDK trace/response/session IDs;
- Codex thread/session IDs;
- Claude native session IDs;
- future provider IDs.

This preserves deterministic Task identity even if provider launch fails before returning its native ID.

## 10.5 Reasoning backend capability declarations

Following Soma's existing worker-adapter precedent, a reasoning backend/provider should explicitly declare supported / not-supported / unmeasured capabilities with evidence.

Candidate capability vocabulary:

- durable provider operation identity;
- exact query/recovery by provider ID;
- cancellation;
- resumable stream cursor;
- explicit session/continuation identity;
- structured final output validation;
- per-item agent provenance;
- per-tool-call attribution;
- usage/token/cost extraction;
- human-approval interruption/resume;
- provider-native subagents;
- bounded subagent concurrency control;
- read-only tool isolation;
- mutation broker compatibility;
- protocol-version/drift detection.

Absence is never interpreted as support.

---

# 11. OpenAI Responses API findings relevant to the backend

This section uses current official OpenAI primary documentation as of 2026-08-12.

## 11.1 Multi-agent is useful as a subordinate reasoning mode

Current Responses Multi-agent allows a root GPT-5.6 agent to create a hierarchical tree of subagents, coordinate them with hosted actions, and synthesize the final response.

OpenAI explicitly positions it for independent bounded work and recommends one agent instead for ordered chains, shared mutable-resource contention, and fixed deterministic execution graphs.

That reinforces the Soma split:

- deterministic graph above the provider in Mission/PlanRevision/WorkPackage;
- model-directed subagent tree below one reasoning Task when useful.

## 11.2 Agent paths are visible provider provenance

Current Multi-agent exposes hierarchical paths such as:

```text
/root
/root/researcher
/root/reviewer
/root/reviewer/tester
```

Output items/events carry an `agent` attribute with `agent.agent_name`.

This is strong enough to preserve provider-local provenance for one run.

It is **not** strong enough to become canonical Soma Task/Agent identity because:

- paths are provider-local;
- task names are chosen during provider orchestration;
- the feature/output schemas are beta and may change;
- a future provider will expose different identity shapes.

## 11.3 Hosted collaboration actions are traceable

Responses Multi-agent adds provider output items including:

- `multi_agent_call`;
- `multi_agent_call_output`;
- `agent_message`.

`call_id` links a hosted collaboration action to its output. `agent_message` exposes author/recipient direction, and agent-attributed events carry the provider-local agent path.

Soma can capture these as raw/versioned evidence.

## 11.4 Developer function calls are agent-attributed

Any agent in the tree may emit a developer-defined `function_call`. Current streaming examples attribute output items to the originating agent.

This can support useful audit evidence such as:

```text
provider run resp_X
agent /root/reviewer
function call call_Y
Soma tool get_evidence(...)
```

But authority must still come from Soma, not from `/root/reviewer` merely existing.

## 11.5 All Multi-agent children share the request tool set

Current Responses Multi-agent documentation says all agents in the tree have access to the tools configured on the request.

Therefore the first Soma reasoning backend should expose **read-only tools by default** to provider-native trees.

If mutation is later allowed, the actual tool broker must verify Task/mandate/resource authority on every protected call. A provider-local agent path cannot mint authority.

## 11.6 Multi-agent concurrency is provider-internal, not Soma graph concurrency

`max_concurrent_subagents` defaults to 3 and applies across descendants in the hosted tree.

This controls internal reasoning concurrency. It is distinct from Soma admitting 1/2/4/8 canonical WorkPackages.

The benchmark must measure these dimensions separately rather than mixing them.

## 11.7 Beta protocol drift matters

OpenAI explicitly labels Responses Multi-agent beta and notes item schemas may change.

Any future adapter must preserve raw items plus a reviewed protocol/version marker and fail closed when an unknown changed item would affect trusted result/provenance projection.

This mirrors Soma's existing Claude/Codex adapter protocol-drift approach.

---

# 12. Background durability and an explicit unknown

Current Responses background mode supports:

- asynchronous `response_id` identity;
- polling queued/in-progress requests by ID until terminal;
- cancellation by exact response ID;
- idempotent repeated cancellation;
- optional background streaming with `sequence_number` cursor;
- resuming a dropped stream from `starting_after=<cursor>` when the response was created with streaming enabled.

These properties map well to a future durable reasoning backend.

However, Iteration 4 did **not** find explicit official documentation proving that Responses Multi-agent beta and background mode are supported together as one durable combination.

Therefore:

```text
Responses background durability: supported for documented background Responses
Responses Multi-agent provenance/orchestration: supported as documented beta
Responses Multi-agent + background combined durability: UNMEASURED
```

Do not design production recovery around that combination until a dedicated provider pilot proves it.

The existing WebSocket Multi-agent examples do support `store: true`, `response_id`, function-output injection, and continuation via `previous_response_id`, which is promising but not equivalent to proof of background-mode behavior.

---

# 13. OpenAI Agents SDK findings

## 13.1 Result surfaces are rich enough for local evidence capture

Current Agents SDK `RunResult`/`RunResultStreaming` expose:

- final output;
- rich `new_items` with agent/tool/handoff/approval metadata;
- raw model responses;
- last agent;
- `last_response_id`;
- interruptions and resumable `RunState`;
- usage/context information.

This makes Agents SDK a viable provider runtime behind one Soma reasoning backend.

## 13.2 Structured output can be validated before publication

Agents can define an output type, and invalid structured final output is surfaced as a model behavior/validation failure rather than silently accepted.

A future Soma adapter can require an EvidenceSubmission schema and treat provider completion without a valid submission as failed/uncertain evidence rather than canonical success.

## 13.3 Tracing provides excellent provenance but cannot be sole authority

Agents SDK tracing exposes:

- `trace_id`;
- span IDs and parent IDs;
- agent spans;
- model generation spans;
- function-tool spans;
- handoff spans;
- timing;
- metadata/group IDs.

A Soma runtime could attach Task/Attempt identity in trace metadata for correlation.

But tracing must remain supplemental evidence, not the only canonical provenance path, because:

- tracing can be disabled;
- tracing is unavailable for OpenAI API organizations under ZDR;
- trace capture can include sensitive model/tool inputs/outputs unless configured otherwise;
- export timing is asynchronous by default.

The backend should persist the minimal required provider/result/provenance evidence locally/durably from runtime events/result objects, with traces as an observability enhancement.

## 13.4 Agents SDK durable integrations do not replace Soma

The current SDK documents external durable integrations including Dapr, Temporal, Restate, and DBOS.

Their existence confirms that agent loops often need an external durability layer. It does not justify replacing Soma's existing Task/Run/ProjectScope authority.

For Soma, the SDK should be a reasoning runtime behind the canonical backend boundary, not the company scheduler.

---

# 14. Codex subagent findings

Current official Codex documentation confirms:

- subagent workflows run independent work in parallel and return distilled results;
- read-heavy parallel tasks are the recommended starting point;
- parallel write-heavy workflows require more caution because conflicts/coordination overhead increase;
- subagents inherit parent permission/sandbox policy unless a custom agent overrides supported settings;
- custom agents can be explicitly read-only;
- agent threads are user-visible/inspectable in supported surfaces.

This supports Soma's read-only-first policy.

The documentation consulted does not establish one provider-neutral stable machine identifier for every Codex subagent thread that Soma can safely promote to canonical identity.

Therefore Codex subagent thread identity remains provider evidence pending a dedicated adapter/protocol pilot.

---

# 15. Candidate provider provenance envelope

Iteration 4 proposes one evidence-only provenance shape, not a canonical Task identity.

```text
ProviderProvenanceV1
  provider
  provider_mode
  protocol_or_api_version
  provider_run_ref
  response_or_session_ref?
  trace_ref?
  event_sequence?
  item_ref?
  item_type?
  provider_agent_path?
  provider_parent_agent_path?
  collaboration_action?
  call_id?
  author?
  recipient?
  raw_event_hash
  raw_event_ref
  captured_at
  identity_scope = provider_evidence_only
```

Rules:

- all provider identifiers remain opaque exact values;
- no path/name is normalized into a Soma Role or Task;
- raw provider event hash/reference is retained whenever a projected provenance claim matters;
- unknown protocol items fail closed if they could affect trusted result/provenance interpretation;
- provider-local path can label evidence but cannot grant tool/mutation authority;
- the final EvidenceSubmission refers to provenance records rather than copying full raw streams.

---

# 16. EvidenceSubmissionV1 strict research validation

Iteration 3 proposed a loose shape. Iteration 4 tested a stricter Pydantic-style research model in memory only.

No file was created and no production code was imported/changed.

## 16.1 Strict fields exercised

The synthetic model used:

- `extra = forbid` behavior;
- fixed `schema_version = evidence_submission.v1`;
- bounded summaries/statements/excerpts;
- SHA-256 shape validation where hashes are present;
- non-negative usage/byte fields;
- bounded arrays;
- exact work identity / assignment / producer structures;
- claim, evidence, artifact, uncertainty, blocker, usage, provenance, retrieval, and byte-accounting records;
- cross-reference validation between claims, evidence, and uncertainties;
- duplicate-ID rejection.

## 16.2 Four synthetic worker profiles

The same contract successfully validated four different evidence submissions:

| Synthetic producer | Disposition | Claims | Evidence | Result |
|---|---:|---:|---:|---|
| execution / durable command | complete | 1 | 1 | pass |
| repository retrieval | complete | 1 | 1 | pass |
| cheap scout reasoning | partial | 1 | 1 + uncertainty | pass |
| strong reasoning / multi-agent provenance | complete | 2 | 2 | pass |

This supports the Iteration 2/3 hypothesis that hard worker classes are unnecessary at the evidence boundary.

The same envelope can represent different producers because producer capability and evidence type vary while the submission contract remains stable.

## 16.3 Negative validation cases

The deterministic test rejected each of these as expected:

1. a claim referencing a nonexistent evidence ID;
2. duplicate evidence IDs;
3. an undeclared extra field inserted into the producer record;
4. an evidence excerpt exceeding the research bound.

No semantic model judgment was used.

## 16.4 What the validation does not prove

It does not prove:

- 12 KiB is the optimal byte budget;
- models will reliably emit the schema;
- every future domain fits without extension;
- the field names are final;
- evidence itself is true;
- semantic claims are correct.

It proves only that one strict reference-oriented envelope can structurally represent the four intended producer categories without adding worker-class-specific schema branches.

---

# 17. FanInV1 strict research validation

A strict research aggregate model was also validated in memory.

Rules tested included:

- unique expected/collected/missing unit refs;
- collected and missing sets must not overlap;
- collected + missing must exactly cover expected;
- one compact submission summary per collected unit;
- unique submission IDs;
- bounded structured conflicts/uncertainty references;
- non-negative response/usage fields.

A four-unit aggregate containing execution, retrieval, scout, and reasoning submissions passed.

Negative cases correctly rejected:

- a unit appearing in both collected and missing sets;
- a collected unit with no matching submission summary.

This validates the structural fan-in concept but not semantic synthesis quality.

---

# 18. Updated evidence/fan-in responsibility boundary

## Soma deterministic responsibilities

Soma may:

- validate schema and contract versions;
- validate IDs, hashes, refs, and assignment identity;
- validate dependency satisfaction proofs;
- enforce response/evidence/count budgets;
- reject duplicate/conflicting replay identity;
- verify expected-unit coverage;
- detect exact structured fact conflicts under assignment-provided fact keys;
- preserve provider provenance;
- aggregate usage/latency/byte counts;
- expose retrieval pointers to full evidence;
- preserve missing/blocked/uncertain submissions honestly.

## Sol / named reasoning authority responsibilities

Sol should:

- interpret natural-language claims;
- decide whether two differently worded claims conflict semantically;
- assess evidence relevance/quality;
- resolve contradictions;
- decide whether evidence is substantively sufficient;
- propose replans;
- decide whether carried-forward evidence remains intellectually valid;
- synthesize the final response/recommendation;
- perform or request substantive outcome acceptance where authorized.

This keeps Soma deterministic without making it stupid: Soma owns exact structure, continuity, and authority; Sol owns judgment.

---

# 19. Updated end-to-end architecture after Iteration 4

```text
Owner request
    |
ChatGPT / Sol
semantic decomposition + judgment
    |
Mission
    |
immutable PlanRevision
  exact graph manifest/hash
    |
  +---------------- package DAG ----------------+
  |                                             |
WorkPackage A                              WorkPackage B
  | dependency edge/proof                      |
  +-----------------------------> readiness ----+
                                                |
                                      WorkPackageAttempt
                                                |
                                           canonical Task
                                                |
                                provider-neutral TaskBackend
                                                |
                     +--------------------------+-------------------+
                     |                          |                   |
              local execution             retrieval          reasoning run
                                                                    |
                                                    provider-native tree
                                                  (optional subordinate)
                                                                    |
                                                          EvidenceSubmission
                     +--------------------------+-------------------+
                                                |
                                            FanInV1
                                                |
                                       Sol adjudication/synthesis
                                                |
                                          Acceptance / reply
```

Provider-native agents are beneath the Task/backend boundary unless Soma independently owns their work as separate WorkPackages/Tasks.

---

# 20. Facts, inferences, hypotheses, rejected ideas

## Facts

1. Company Kernel v1 has immutable PlanRevision/WorkPackage/Attempt identities but no first-class dependency table.
2. Current WorkPackage topology is fixed to `single_active`.
3. Current route-independent outcome identity includes PlanRevision and excludes provider/Task/Run route facts.
4. Current repository mutation locks are repository-wide; Hermes also has in-process explicit resource-key mutation serialization.
5. Responses Multi-agent beta exposes hierarchical provider agent paths, hosted collaboration items, call IDs, messages, and per-item agent attribution.
6. All Responses Multi-agent children receive the tools configured for the request.
7. Current Responses background mode provides response-ID polling, cancellation, and resumable streaming cursor semantics.
8. Current official docs consulted do not explicitly establish Multi-agent + background as one supported combined durability contract.
9. Agents SDK exposes rich result/new-item/raw-response/state/tracing metadata.
10. Agents SDK tracing can be disabled and is unavailable under ZDR, so it cannot be the sole canonical provenance source.
11. Codex guidance recommends read-heavy parallelism before write-heavy parallelism and supports read-only custom agent configurations.
12. The strict synthetic EvidenceSubmission/FanIn exercises passed the intended valid records and rejected the tested malformed records.

## Inferences

1. A complete bounded package DAG should be immutable at PlanRevision acceptance rather than assembled piecemeal after selection.
2. Normalized dependency rows are useful if they are hash-bound child facts of the PlanRevision graph, not a second editable plan source.
3. Dependency satisfaction must be frozen by exact reference/hash into downstream attempt identity.
4. Cross-plan evidence reuse is safe conceptually; cross-plan accepted-outcome identity reuse is not.
5. Read-only old-plan work can often safely finish after replan; mutation requires stronger containment/serialization.
6. Provider-native subagent paths are valuable provenance but poor canonical identity.
7. A provider-neutral reasoning backend can reuse Soma's existing reserve/start/query/cancel/result-reference lifecycle shape.
8. Strong provider trees should start read-only because provider orchestration can grant the same configured tool set to many children.

## Hypotheses for later measurement

1. Static immutable DAG revisions will be operationally simpler than dynamic graph mutation for personal-chief-of-staff workloads.
2. Freezing dependency proofs will materially improve reconnect/replay determinism and reduce stale-input bugs.
3. One canonical reasoning Task containing a native provider subagent tree will often be cheaper to coordinate than mirroring every provider child as a Soma Task.
4. Cross-plan evidence carry-forward plus cheap verification Tasks will remove most redundant work without needing AcceptanceAdoption in the first implementation.
5. The EvidenceSubmission/FanIn schema can stay near current bounds while supporting 1/2/4/8 benchmark runs.

## Rejected / deferred ideas

- mutable dependencies under an unchanged PlanRevision;
- a second graph lifecycle/status machine;
- cross-plan dependency edges in graph v1;
- semantic similarity as package/dependency identity;
- automatic transfer of AcceptanceCommit across plan revisions;
- fake no-op Task/Run solely to make an adopted old acceptance fit current schema;
- parallel mutation candidates for one WorkPackage outcome;
- `parallel_evidence` WorkPackageAttempt topology in the first worker architecture;
- provider-local agent path as canonical Soma Task/Role/authority identity;
- OpenAI Agents SDK tracing as sole canonical provenance;
- assuming Responses Multi-agent + background durability without measurement.

## Confirmed bugs

None recorded in Iteration 4.

Current limitations and intentionally inactive Company Kernel behavior are not bugs.

---

# 21. Leading Iteration 4 decisions

1. **PlanRevision becomes the immutable graph commit for concurrent company work.**
2. **A graph-capable revision should atomically bind a complete bounded package set and dependency set before becoming current.**
3. **Dependencies should have normalized immutable rows/facts hash-bound to the PlanRevision graph manifest.**
4. **Graph v1 is same-plan, acyclic, conjunctive, and uses a small typed requirement vocabulary.**
5. **Every admitted downstream Attempt must freeze exact dependency satisfaction refs/hashes into its request identity.**
6. **Evidence may carry across plan revisions; accepted outcome identity does not silently carry.**
7. **Plan selection never implies Task cancellation or resource quiescence.**
8. **Old read-only work may finish for evidence; conflicting old/new mutation remains serialized until terminal/contained.**
9. **Keep WorkPackageAttempt `single_active` in the first worker architecture. Use separate WorkPackages or provider-native subagents for parallel reasoning.**
10. **Use one provider-neutral reasoning backend class/contract above provider-specific runtime bindings.**
11. **Soma-owned backend reference is canonical at the backend boundary; provider response/session/trace IDs are subordinate evidence/bindings.**
12. **Provider-native agent paths/call IDs/messages are preserved as evidence-only provenance.**
13. **Reasoning provider capabilities must be explicit supported/not-supported/unmeasured declarations.**
14. **Read-only tools are the default for native subagent trees; mutation requires a Soma-enforced broker boundary.**
15. **EvidenceSubmissionV1/FanInV1 remain viable after strict synthetic structural validation across four producer profiles.**

These are research decisions/candidates, not authorization to implement them.

---

# 22. Next research questions - Iteration 5

1. **Graph manifest contract:** Freeze a concrete research-only `PlanGraphManifestV1` JSON/Pydantic schema and canonical graph-hash algorithm.
2. **Dependency proof contract:** Freeze `DependencySatisfactionProofV1` and test replay/change cases synthetically.
3. **Package graph transaction:** Write the exact future transaction/crash matrix for atomic PlanRevision + WorkPackages + edges + current-pointer CAS without implementing it.
4. **Reasoning backend protocol:** Freeze `ReasoningSpecV1`, `ReasoningBackendObservationV1`, result/evidence references, cancellation, uncertainty, and provider-binding records.
5. **OpenAI provider pilot design:** Design - but do not yet execute - a minimal Responses single-agent background pilot and a separate Multi-agent provenance pilot. Treat combined background+Multi-agent as a distinct gate.
6. **Agents SDK provider pilot design:** Decide whether raw result/new-item capture or a custom trace processor is the primary durable provenance path.
7. **Codex provider pilot design:** Identify the exact CLI/app-server protocol needed to measure stable subagent/thread provenance before considering Codex as a reasoning backend mode.
8. **Mutation broker contract:** Define the future provider-neutral protected-tool call envelope carrying Task, mandate, project/resource, idempotency, and provider provenance without trusting provider agent identity.
9. **Carry-forward benchmark:** Create synthetic replan cases testing old evidence reuse, active read-only work, active mutation containment, and stale dependency proofs.
10. **Benchmark corpus freeze:** Freeze the eight immutable work units and gold/evaluation criteria for the first 1/2/4/8 canonical concurrency benchmark.
11. **Benchmark dimensions:** Keep canonical WorkPackage concurrency separate from provider-internal subagent concurrency; define a second experiment for native Multi-agent only after the canonical benchmark.
12. **Normal Chat integration:** Define the minimal future high-level action that can submit/accept one bounded PlanRevision graph and later retrieve one coherent FanIn result without exposing internal worker chatter.

Iteration 4 ends here. No provider/model worker or 1/2/4/8 benchmark was executed.

---

# Sources consulted

## Soma repository evidence

- `soma/company_kernel/models.py`
- `soma/company_kernel/schema.py`
- `soma/company_kernel/store.py`
- `docs/V3_1B_KERNEL_OF_ONE_ARCHITECTURE_GATE_2026-08-02.md`
- `docs/V3_1B_KERNEL_OF_ONE_ARCHITECTURE_PROPOSAL_2026-08-02.md`
- `docs/V3_1B_KERNEL_OF_ONE_ARCHITECTURE_ACCEPTANCE_AUDIT_2026-08-02.md`
- `docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`
- `soma/tasks/models.py`
- `soma/tasks/backends.py`
- `soma/operation_locks.py`
- `soma/hermes_concurrency.py`
- `soma/hermes_service_gateway.py`
- Iterations 1-3 under `docs/agent-worker-research/`

## Current official OpenAI primary sources

- Responses Multi-agent: https://developers.openai.com/api/docs/guides/responses-multi-agent
- Responses Background mode: https://developers.openai.com/api/docs/guides/background
- GPT-5.6 model guidance: https://developers.openai.com/api/docs/guides/latest-model
- Agents SDK Results: https://openai.github.io/openai-agents-python/results/
- Agents SDK Running agents: https://openai.github.io/openai-agents-python/running_agents/
- Agents SDK Tracing: https://openai.github.io/openai-agents-python/tracing/
- Agents SDK tracing reference: https://openai.github.io/openai-agents-python/ref/tracing/
- ChatGPT/Codex Subagents: https://learn.chatgpt.com/docs/agent-configuration/subagents

## Synthetic research validation

One in-memory Pydantic-style validation exercise used only invented execution/retrieval/scout/reasoning submissions and aggregate records. No provider, repository worker, model, service, network call, or production database participated.
