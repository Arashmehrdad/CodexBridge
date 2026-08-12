# Iteration 5 - Frozen Graph, Reasoning, Broker, and Benchmark Contracts

Date: 2026-08-12
Status: research only; contract-freeze candidate
Scope: graph-manifest identity, dependency-proof identity, graph transaction/crash semantics, reasoning-backend protocol, provider pilot designs, protected mutation broker, evidence bounds, and frozen 1/2/4/8 benchmark corpus

## Guardrails

This iteration is research only. It does not authorize production implementation, schema migration, runtime activation, provider/model launch, benchmark execution, service restart, connector refresh, Hermes configuration change, commit, push, external mutation, purchase, or changes to the separate normal-Chat tool UX implementation thread.

Only this journal file is authored by the agent-worker research thread.

At Iteration 5 start, Soma remained on `lane/memory-integration-foundation-1` at HEAD `b53404fa9600412a4b3dd0fafd664a856096257b`. The shared worktree already contained the research journals plus separate concurrent normal-Chat UX work. This iteration does not modify or depend on that concurrent implementation work.

No provider, model, Codex, Claude, Hermes model runtime, or native subagent was launched. Deterministic contract checks used invented in-memory records only.

Iteration 4 remains the immediate architecture baseline:

- Mission / PlanRevision / WorkPackage / WorkPackageAttempt are the company-domain decomposition identities;
- PlanRevision is the candidate immutable graph commit;
- Task remains canonical execution-attempt lifecycle identity;
- no separate work-unit state machine exists;
- dependency satisfaction is frozen at downstream admission;
- WorkPackageAttempt remains `single_active` in the first worker architecture;
- provider-native subagents remain subordinate to one Task unless Soma independently needs durable ownership;
- a provider-neutral reasoning backend sits below Task and above provider-specific runtime bindings;
- read-only reasoning is the default, and protected mutation requires a Soma-enforced broker.

---

# 1. Exact questions investigated

1. What exact `PlanGraphManifestV1` fields can be content-addressed without creating a circular dependency on `plan_revision_id`, `work_package_id`, or `outcome_id`?
2. What package/edge bounds should the first graph contract freeze?
3. What exact canonicalization makes graph identity independent of input list ordering?
4. What exact tagged `DependencySatisfactionProofV1` shape can represent `accepted_outcome`, `published_success`, `evidence_available`, and `settled` without semantic inference?
5. Which proof fields belong to stable dependency identity versus audit metadata that must not perturb replay identity?
6. What exact all-or-nothing transaction and crash behavior should create a PlanRevision, its packages, its dependency facts, and the current-plan CAS pointer?
7. What should `ReasoningSpecV1`, reasoning-backend observation, provider binding, result, evidence, cancellation, and uncertainty look like without creating a second Task lifecycle?
8. What happens if a provider create/start call may have been accepted but Soma crashes or loses the response before receiving a provider operation ID?
9. What current OpenAI capabilities are sufficiently documented to design provider pilots, and what remains unmeasured?
10. What should be the primary durable provenance path for OpenAI Agents SDK runs when tracing may be disabled or unavailable?
11. Is Codex CLI or Codex App Server the better future pilot boundary for deep subagent/thread provenance?
12. What exact protected-tool envelope lets a provider-native agent request mutation without the provider-local agent identity becoming authority?
13. Which fields may participate in protected-effect idempotency identity, and which are evidence-only metadata?
14. What exact evidence/fan-in limits should be frozen before experiments?
15. What exact eight-work-unit corpus, source commit, file hashes, gold facts, traps, metrics, and quality gates should define the first 1/2/4/8 canonical-concurrency benchmark?
16. How must canonical WorkPackage concurrency be separated from provider-internal subagent concurrency so the benchmark measures one variable at a time?

---

# 2. Source baseline and contract-freeze discipline

## 2.1 Repository source point

All benchmark source packets in this iteration are frozen to committed Soma source at:

```text
b53404fa9600412a4b3dd0fafd664a856096257b
```

Untracked research journals and concurrent normal-Chat UX edits are not benchmark inputs.

A future benchmark runner must read the exact committed bytes or an immutable copied packet whose per-file hashes match this journal. It must not silently read newer worktree content.

## 2.2 Current source principles reused

Repository evidence continues to support these patterns:

- canonical Task projections are compact and evidence-by-reference, with a 12 KiB default response budget;
- provider adapters distinguish provider claims from canonical Task truth;
- provider capabilities are explicit `supported`, `not_supported`, or `unmeasured` declarations;
- interaction delivery persists and claims before send, and records outcome uncertainty rather than blindly resending after an ambiguous send;
- ProjectScope and Run/Task stores already support shared SQLite `BEGIN IMMEDIATE` coordination;
- Workflow provides useful historical DAG-validation precedent but also demonstrates why a second lifecycle manager should not be copied;
- current WorkPackage outcome identity depends on PlanRevision identity, while provider/Task/Run route facts are deliberately excluded.

Iteration 5 extends these principles only as research contracts. It does not alter current source.

---

# 3. Frozen research contract: `PlanGraphManifestV1`

## 3.1 Important identity correction: avoid a circular plan identity

Iteration 4's conceptual manifest was intentionally loose. Iteration 5 freezes an important correction.

A graph manifest **must not contain `plan_revision_id`** when the accepted PlanRevision contract itself binds the graph manifest hash. Otherwise identity becomes circular:

```text
plan_revision_id
  depends on plan_contract
      depends on graph_hash
          depends on manifest
              depends on plan_revision_id   <- cycle
```

The same applies to `work_package_id` and `outcome_id`, because current route-independent WorkPackage/outcome identities themselves include `plan_revision_id`.

Therefore the graph manifest contains only pre-PlanRevision, route-neutral graph material:

- Mission identity;
- exact ProjectScope identity/generation;
- package keys;
- route-neutral WorkPackage contract hashes;
- target resource identity;
- optional evidence-requirements hashes;
- dependency edges expressed by package keys;
- dependency requirement and optional evidence-selector identity.

After the graph hash is bound into the accepted plan contract and the PlanRevision identity exists, Soma may derive/store WorkPackage/outcome identities and normalized dependency rows under that PlanRevision.

## 3.2 Contract

Research schema:

```text
PlanGraphManifestV1
  schema_version = "plan_graph_manifest.v1"
  mission_id
  project_id
  resource_id
  scope_generation >= 1
  package_nodes[1..32]
    package_key
    work_package_contract_hash
    target_resource_id
    evidence_requirements_hash?
  dependency_edges[0..128]
    upstream_package_key
    downstream_package_key
    requirement
      accepted_outcome
      published_success
      evidence_available
      settled
    evidence_selector_ref?   # evidence_available only
    evidence_selector_hash?  # evidence_available only
```

The manifest deliberately excludes:

- PlanRevision ID;
- WorkPackage ID;
- outcome ID;
- provider/model;
- backend kind/reference;
- Task/Run/session/process identity;
- mutable runtime state;
- readiness state;
- timestamps;
- list position as semantic ordering.

## 3.3 First-version bounds

Iteration 5 freezes the research candidate limits:

```text
MAX_PACKAGES_PER_PLAN_GRAPH = 32
MAX_DEPENDENCY_EDGES_PER_PLAN_GRAPH = 128
```

Rationale:

- 32 packages is well above the intended 1/2/4/8 personal-chief-of-staff fan-out scale;
- 128 edges permits a moderately connected DAG without allowing an accidental repository-scale graph;
- the limits keep validation, atomic insertion, compact projection, and fan-in analysis bounded;
- the legacy Workflow system's 50-step ceiling is useful precedent that Soma already values bounded graphs, but it is not copied as authority;
- these are v1 research limits, not a claim that 32/128 are universal future ceilings.

Changing these limits later is a versioned contract change, not silent runtime policy drift.

## 3.4 Canonicalization

Graph identity must be independent of caller list order.

Canonical payload rules:

1. package nodes sorted by exact `package_key`;
2. dependency edges sorted lexicographically by:
   - `upstream_package_key`;
   - `downstream_package_key`;
   - `requirement`;
   - `evidence_selector_hash` or empty string;
3. JSON UTF-8, sorted keys, compact separators, no inferred normalization of opaque identifiers;
4. hashes lowercase SHA-256;
5. timestamps and generated IDs excluded.

Candidate identity:

```text
graph_manifest_hash = SHA256(
  "soma.company_kernel.plan_graph.v1\0" + canonical_json(manifest_identity_payload)
)
```

A deterministic in-memory test created the same graph in forward and reversed input order. Both produced:

```text
3619bb7d748a2cbe26b64d2c5510251f4f69d0de0b5fc585c25530ce86f81483
```

## 3.5 Structural validation

The v1 graph is invalid if:

- package set is empty;
- package count exceeds 32;
- edge count exceeds 128;
- a package key is empty or duplicated;
- a dependency endpoint is missing;
- an edge points from a package to itself;
- the same canonical edge appears twice;
- a directed cycle exists;
- an unknown requirement is supplied;
- `evidence_available` lacks exact selector ref/hash;
- a non-`evidence_available` edge carries an evidence selector;
- package target resource escapes the Mission/ProjectScope ceiling;
- a route-specific provider/Task/Run identity appears in route-neutral graph material.

All dependency edges are conjunctive in graph v1. Arbitrary boolean logic, OR branches, thresholds, voting, and quorums remain deferred.

The deterministic synthetic test explicitly rejected:

- a cycle;
- an edge to a missing package;
- `evidence_available` without its required selector.

## 3.6 Normalized child facts

A future relational implementation may store normalized immutable package and dependency facts for efficient querying.

Those facts do not become a second plan source.

Consistency rule:

```text
reconstruct route-neutral manifest projection from normalized rows
-> canonicalize using PlanGraphManifestV1 rules
-> hash
-> must equal PlanRevision-bound graph_manifest_hash
```

A normalized dependency row can gain a post-PlanRevision durable ID derived from exact PlanRevision + endpoint package identities + requirement + selector hash. That row ID is not part of pre-PlanRevision graph identity.

---

# 4. Frozen research contract: `DependencySatisfactionProofV1`

## 4.1 Why a tagged proof is required

`accepted_outcome`, `published_success`, `evidence_available`, and `settled` are mechanically different statements. One generic `satisfying_ref` string is too weak because it lets code accidentally accept the wrong evidence class.

Iteration 5 freezes a discriminated proof family.

## 4.2 Common envelope

```text
DependencySatisfactionProofV1
  schema_version = "dependency_satisfaction_proof.v1"
  edge_id
  edge_hash
  requirement
  upstream_work_package_id
  upstream_outcome_id
  downstream_work_package_id
  satisfaction              # discriminated union matching requirement
  observed_kernel_state_version
  observed_at
  proof_hash
```

## 4.3 Satisfaction variants

### `accepted_outcome`

```text
kind = accepted_outcome
acceptance_commit_id
acceptance_commit_hash
```

The commit must match the exact upstream outcome and authoritative acceptance relationship.

### `published_success`

```text
kind = published_success
attempt_id
task_id
run_id
result_published_hash
public_result_source_sha256
```

The canonical Task/Run relationship and published successful result must match exactly.

### `evidence_available`

```text
kind = evidence_available
evidence_ref
evidence_hash
evidence_selector_hash
```

`evidence_selector_hash` must equal the selector bound into the dependency edge.

### `settled`

```text
kind = settled
attempt_set_hash
head_attempt_id?
settlement_ref
settlement_hash
settlement_class = terminal | cancelled | contained | uncertain_contained
```

`settled` is a statement about the **known upstream attempt set**, not merely one terminal Task. `attempt_set_hash` is therefore mandatory.

If a new upstream successor attempt later appears, the old proof remains truthful about the prior admission moment, but a new downstream admission must evaluate the new attempt set rather than silently reusing the old proof.

## 4.4 Stable proof identity versus audit metadata

A subtle replay rule is frozen here.

`observed_at` must not participate in `proof_hash`; otherwise identical proof reconstruction at a later time would fabricate a different dependency identity.

Likewise, `observed_kernel_state_version` is audit/reconstruction metadata and should not by itself perturb proof identity when unrelated Mission state changes.

Candidate stable identity material:

```text
edge_hash
requirement
upstream_work_package_id
upstream_outcome_id
downstream_work_package_id
canonical satisfaction union
```

Candidate hash:

```text
proof_hash = SHA256(
  "soma.company_kernel.dependency_proof.v1\0" +
  canonical_json(stable_proof_identity_material)
)
```

`observed_kernel_state_version` and `observed_at` remain immutable audit fields on the stored proof record but are excluded from this stable hash.

The admission transaction still verifies that the relevant PlanRevision is current and that the referenced satisfaction evidence exists at the observed version.

## 4.5 Binding to a downstream Attempt

The canonical set of dependency proof IDs/hashes must participate in the downstream WorkPackageAttempt request/assignment identity.

Consequences:

- exact replay after response loss returns the same intended Attempt/Task;
- later upstream evidence cannot mutate an already-running assignment;
- reconnect recovery does not need to reconstruct what happened to be ready earlier;
- a changed satisfying result produces a new dependency proof and therefore a new downstream route request;
- semantic changes to downstream purpose/constraints still require a new PlanRevision rather than abusing a route retry.

A deterministic synthetic tagged-union test accepted valid examples and rejected a proof whose `requirement` and satisfaction `kind` disagreed.

---

# 5. Frozen graph-definition transaction and crash matrix

## 5.1 One bounded transaction

A future graph-capable PlanRevision acceptance should use one shared `BEGIN IMMEDIATE` transaction.

Candidate sequence:

1. verify Company Kernel target schema/version and feature activation gate;
2. resolve exact Company/Mission and configured acceptance authority;
3. re-resolve active ProjectScope and exact scope generation;
4. read Mission current PlanRevision and expected `plan_state_version` / `kernel_state_version`;
5. validate caller controller-request identity and replay hash;
6. validate/canonicalize `PlanGraphManifestV1`;
7. compute `graph_manifest_hash`;
8. canonicalize accepted PlanRevision contract that binds exact graph version/hash;
9. derive or verify immutable PlanRevision identity;
10. insert or verify exact PlanRevision replay;
11. derive and insert/verify every immutable WorkPackage under that PlanRevision;
12. derive and insert/verify normalized dependency-edge facts;
13. reconstruct the normalized graph projection and require its hash to equal `graph_manifest_hash`;
14. compare-and-set `missions.current_plan_revision_id`, plan version, and kernel version under the expected old values;
15. commit.

No Task/Run/provider launch occurs in this transaction.

## 5.2 Crash/replay matrix

| Crash/failure window | Durable truth | Recovery rule |
|---|---|---|
| Before transaction | old plan only | identical request may start normally |
| During graph validation | no new rows | reject; old plan remains current |
| After PlanRevision insert but before all packages | transaction uncommitted | rollback leaves no partial graph |
| After packages but before all edges | transaction uncommitted | rollback leaves no partial graph |
| Child-set/manifest hash mismatch | transaction uncommitted | reject/rollback; this is structural uncertainty, not partial acceptance |
| Current-plan CAS loses race | transaction uncommitted | rollback complete candidate graph or verify exact replay; never publish two current plans |
| Commit succeeds, response lost | complete graph + one current pointer | controller request/hash replay returns the same accepted graph |
| Same request ID, different graph hash | existing request identity conflicts | fail closed |
| Same graph content submitted in different list order | same canonical graph hash | no distinct graph identity |
| Same Mission graph content already accepted under a different request | no second content-identical PlanRevision should be fabricated | resolve exact existing immutable content under service-layer replay rules; do not bypass unique content identity |
| ProjectScope generation changes before commit | expected scope no longer valid | fail/rollback |
| ProjectScope generation changes after commit | old graph remains immutable evidence, but later mutation/admission fails current scope checks | no retroactive rewrite |

## 5.3 Graph admission is a separate transition

After graph acceptance, a bounded coordinator may inspect dependency predicates and admit eligible WorkPackageAttempts.

That coordinator must not:

- mutate the graph;
- create its own package lifecycle state;
- spin forever as a hidden scheduler;
- infer semantic dependency satisfaction;
- bypass Task/ProjectScope reservation;
- accept results.

One future public owner action may reserve a bounded set of currently eligible attempts, but the exact batching operation remains a later implementation decision.

---

# 6. Frozen research contract: provider-neutral reasoning backend

## 6.1 Authority boundary

Reasoning is another Task backend, not a second Task manager.

Canonical identity:

```text
WorkPackageAttempt -> canonical Task -> Soma-owned reasoning backend_ref
```

Provider-native identities are subordinate bindings/evidence:

```text
OpenAI response ID
Agents SDK response/trace/session state
Codex thread/session ID
future provider operation/session IDs
```

Provider completion remains a claim until the backend has a valid bounded result/evidence object and Task/Run authority projects canonical outcome.

## 6.2 `ReasoningSpecV1`

Research schema:

```text
ReasoningSpecV1
  schema_version = "reasoning_spec.v1"
  assignment_ref
  assignment_hash
  context_refs[0..64]
    ref
    hash
  dependency_proof_refs[0..64]
    ref
    hash
  output_contract_ref
  output_contract_hash
  tool_policy_ref
  tool_policy_hash
  authority_ref
  authority_hash
  provider_route_ref
  provider_route_hash
  budgets
    wall_time_seconds: 1..86400
    output_bytes: 1024..262144
    input_token_limit?
    output_token_limit?
    cost_limit_usd?
    provider_internal_concurrency_limit: 1..8
  continuation_policy
    none
    explicit_provider_identity
    provider_managed
  mutation_policy
    read_only
    protected_broker_only
```

Large prompt bodies, repositories, transcripts, secrets, or evidence bodies are references, not canonical Task-row payloads.

The `provider_internal_concurrency_limit <= 8` is a Soma v1 bounded policy candidate, not a claim that all providers support eight agents or that eight is optimal.

## 6.3 Start-attempt truth

A reasoning backend needs a subordinate durable start-attempt record because a provider create call has its own ambiguity window.

Candidate dispositions:

```text
not_attempted
claimed_not_sent
accepted_bound
rejected
outcome_unknown
```

Protocol:

1. reserve Soma-owned `backend_ref` before any provider call;
2. persist exact start request hash and a single-claimer start attempt;
3. call provider;
4. if provider returns a stable operation/session ID, atomically bind that exact ID to `backend_ref`;
5. if provider definitely rejects before accepting work, record `rejected`;
6. if transport/process failure occurs after the call may have reached the provider but before Soma captured a recoverable provider ID, record `outcome_unknown`;
7. do **not** blindly submit a second provider create request unless caller idempotency/recovery has been explicitly proven for that provider protocol.

This deliberately mirrors Soma's existing persist-before-send interaction semantics.

A durable provider ID solves recovery only **after the ID is known**. It does not magically close the create-ack crash window.

## 6.4 `ReasoningBackendObservationV1`

The backend observation is evidence for Task reconciliation, not canonical lifecycle authority.

Research shape:

```text
ReasoningBackendObservationV1
  backend_ref
  exists
  start_delivery_disposition
    not_attempted | claimed_not_sent | accepted_bound | rejected | outcome_unknown
  provider_binding_disposition
    unbound | bound | uncertain
  provider_operation_ref?
  provider_status_raw?
  provider_terminal_claim
    none | success | failure | cancelled | incomplete
  continuation_ref?
  last_event_cursor?
  output_contract_disposition
    not_available | valid | invalid | uncertain
  result_ref?
  result_hash?
  evidence_index_ref?
  evidence_index_hash?
  usage_summary?
  error_code?
```

TaskManager/backend reconciliation decides canonical Task state from this evidence plus provider/backend policy. The observation itself must not expose `TaskState` values as provider truth.

## 6.5 Result and evidence references

A successful reasoning backend publication should expose bounded references, not copy full provider transcripts:

```text
ReasoningResultReferenceV1
  backend_ref
  output_contract_version
  evidence_submission_ref
  evidence_submission_hash
  provider_binding_ref/hash
  provider_provenance_index_ref/hash
  raw_provider_evidence_root_ref/hash
  usage_ref/hash?
  published_at
```

Full raw provider events remain behind controlled evidence retrieval.

## 6.6 Capability declarations

Every provider/mode binding must explicitly declare each relevant capability as:

```text
supported
not_supported
unmeasured
```

with evidence.

Candidate capability vocabulary:

- durable provider operation identity;
- exact lookup/recovery by provider ID;
- provider cancellation;
- resumable stream cursor;
- explicit continuation/session identity;
- structured final-output enforcement;
- raw provider-event preservation;
- per-item agent attribution;
- per-tool-call attribution;
- provider-native subagents;
- bounded provider-internal concurrency control;
- usage/token extraction;
- provider-reported cost extraction;
- human-approval interruption/resume;
- read-only tool isolation;
- protected mutation-broker compatibility;
- protocol-version/drift detection;
- create-request idempotency/recovery after lost acknowledgement.

Absence is never support.

---

# 7. Current OpenAI provider findings and pilot design

This section uses official OpenAI primary documentation current during Iteration 5. It distinguishes documented capability from planned measurement.

## 7.1 Responses Multi-agent

Official documentation describes Responses Multi-agent for GPT-5.6 as a beta model-directed hierarchy where a root can create parallel subagents, route messages, and synthesize results.

Documented properties relevant to Soma include:

- independent bounded work is the intended strong use case;
- fixed deterministic graphs and shared mutable-resource contention are weaker fits;
- provider-native agent paths and agent-attributed output items are visible;
- multi-agent collaboration creates typed items such as `multi_agent_call`, `multi_agent_call_output`, and `agent_message`;
- collaboration call/output pairs carry call IDs;
- developer function calls can be attributed to the originating provider agent;
- all agents in the hosted tree use the tools configured on the request;
- `max_concurrent_subagents` defaults to 3 and is provider-internal concurrency, not Soma WorkPackage concurrency.

Architecture consequence:

- deterministic Mission/PlanRevision/WorkPackage graph remains above the provider;
- a native Multi-agent tree remains below one reasoning Task unless Soma independently needs separate durable ownership;
- first provider-native trees should receive read-only surfaces by default;
- provider-local paths/call IDs are evidence, not authority.

## 7.2 Responses background durability

Official background-mode documentation supports:

- asynchronous response identity;
- polling by exact response ID while queued/in-progress;
- cancellation by exact response ID;
- repeated cancellation being idempotent;
- background streaming with event sequence numbers;
- dropped-stream continuation using a `starting_after` cursor when created in the supported streaming mode.

These are promising building blocks **after Soma has captured the response ID**.

Iteration 5 did not find official documentation establishing a caller-controlled create-request idempotency key for the Responses create call. Therefore no architecture claim is made that an ambiguous create acknowledgement can always be safely retried.

## 7.3 Explicit unknown: Multi-agent + background

Official material separately documents Multi-agent and background mode. This research still does not have primary-source proof establishing the combined `Multi-agent + background` mode as one supported durable contract.

Status remains:

```text
Responses background durability: SUPPORTED as documented
Responses Multi-agent orchestration/provenance: SUPPORTED as beta documentation describes
Responses Multi-agent + background combination: UNMEASURED
```

No production recovery design may assume that combined capability until a dedicated pilot proves it.

## 7.4 Pilot OAI-R1: single-agent Responses background durability

Design only; do not execute without owner authorization.

Purpose: measure the durable provider-operation boundary before adding subagents.

Use:

- one read-only synthetic/repository assignment;
- structured `EvidenceSubmissionV1` output;
- no external mutation;
- no Multi-agent;
- background mode;
- `store`/stream settings exactly as official protocol requires;
- a Soma-side reserved synthetic backend identity.

Questions:

1. How soon and under what client events is `response_id` durably available?
2. Can Soma poll the exact operation after controller/process restart?
3. Does cancel by exact response ID converge idempotently?
4. Does a dropped background stream resume from the last captured sequence cursor without duplicate trusted projection?
5. What raw events/status values occur during queued/running/completed/failed/cancelled?
6. Can final structured output be validated and hashed deterministically?
7. What usage/cost fields are available?
8. What failure evidence exists if the create request may have been sent but no response ID is returned to the caller?

The last question is a required stop condition. If the create-ack window cannot be made recoverable/idempotent, Soma must preserve `outcome_unknown` rather than retrying blindly.

## 7.5 Pilot OAI-R2: Responses Multi-agent provenance

Design only; separate from OAI-R1.

Purpose: measure evidence provenance, not durability.

Use:

- read-only tool surface;
- one bounded root task that naturally benefits from 2-3 independent subagents;
- provider-internal concurrency bounded explicitly;
- raw provider items captured locally;
- no background-mode assumption;
- no protected mutation.

Measure:

- provider run/response IDs;
- hierarchical agent paths/names;
- collaboration call/output IDs;
- author/recipient direction;
- function-call origin attribution;
- event ordering;
- raw-item schema/version drift signals;
- whether a final EvidenceSubmission can reference compact provenance without copying the provider transcript.

Do not promote any provider agent path into a Soma Task/Role/mandate identity.

## 7.6 Pilot OAI-R3: combined durability gate

Only after OAI-R1 and OAI-R2 pass, test the combination of Multi-agent with durable/background continuation.

Until then, this combination remains unmeasured.

## 7.7 Agents SDK provenance design

Current Agents SDK result surfaces expose locally inspectable `new_items`, raw model responses, final output, the last agent, response IDs, interruptions, and resumable run state. Tracing adds trace/span/parent relationships and tool/handoff observability, but tracing can be disabled and is unavailable for OpenAI API organizations using ZDR.

Therefore the primary durable evidence path for a future Agents SDK backend should be:

```text
locally captured result/new_items/raw_responses/run state
    -> content-addressed Soma evidence
```

Tracing is supplemental:

```text
trace/span metadata
    -> optional correlated observability evidence
```

Tracing must not be the only evidence needed to reconstruct provenance or publish a result.

### Pilot OAI-A1

Design only.

Questions:

1. Can every agent/tool/handoff item needed for Soma provenance be captured from local result/event surfaces with tracing disabled?
2. Does `last_response_id` support exact server-managed continuation for the relevant OpenAI model path?
3. Can interrupted approval state be serialized/recovered safely without replaying a protected tool action?
4. What exact fields survive process restart versus only in-memory agent objects?
5. Can Soma store minimal provenance without sensitive model/tool payloads?
6. Do raw-response/item schemas carry enough protocol identity to fail closed on drift?

## 7.8 Codex App Server is the better deep-provenance pilot boundary

Soma already has a measured Codex `exec --json` adapter for a bounded provider session. That remains useful.

For **deep subagent/thread provenance**, current official Codex App Server documentation offers a richer future measurement surface than treating CLI text output as the universal protocol:

- JSON-RPC over the documented App Server transport;
- thread start/resume identities;
- thread/session identities;
- thread lineage fields such as parent/ancestor relationships in documented list surfaces;
- source kinds that distinguish subagent-related threads/events;
- generated JSON schema support for the installed App Server protocol;
- streamed turn/item lifecycle events.

The App Server WebSocket transport is documented as experimental, so the first pilot should prefer the documented stdio JSON-RPC boundary rather than treating WebSocket behavior as production proof.

### Pilot CDX-R1

Design only.

Questions:

1. Does one root Codex thread expose stable child/subagent thread IDs during a real parallel read-only task?
2. Can child lineage be reconstructed after the root client process restarts?
3. Which `sourceKind`, `parentThreadId`, `ancestorThreadId`, session, turn, and item fields are present in the exact installed protocol version?
4. Can generated JSON schemas be frozen with the adapter and used to detect protocol drift?
5. What cancellation semantics apply to root and child threads?
6. Does root cancellation mechanically contain all child work, or must Soma retain external process/tree containment as it does today?
7. Which identifiers remain provider evidence rather than durable Soma identity?

No Codex/App Server process is launched in Iteration 5.

---

# 8. Frozen research contract: protected mutation broker

## 8.1 Why a broker is required

A strong provider tree may contain many independent reasoning agents, but provider-local existence must never multiply external-world authority.

Every protected mutation crosses a Soma-controlled mechanical boundary.

The broker validates:

- canonical Task/Attempt identity and currentness;
- cancellation precedence;
- active mandate/version;
- ProjectScope project/resource/generation;
- concrete capability possession;
- tool-operation contract;
- resource ownership/serialization;
- idempotency identity;
- expiry;
- payload content hash;
- any required approval/authority evidence.

Only then may the actual mutation tool be called.

## 8.2 `ProtectedToolCallV1`

Research shape:

```text
ProtectedToolCallV1
  schema_version = "protected_tool_call.v1"
  call_request_id
  task_id
  attempt_id
  backend_ref
  mandate_ref
  mandate_hash
  mandate_version
  project_id
  resource_id
  scope_generation
  capability_ref
  capability_hash
  tool_operation_ref
  tool_operation_hash
  resource_key
  idempotency_key
  payload_ref
  payload_hash
  expected_task_state_version
  expires_at
  mutation_class
    repository
    external_system
    deployment
    communication
    financial
    generic
  provider_provenance_refs[]   # evidence-only correlation
```

## 8.3 Critical identity rule: provider provenance is not effect identity

Provider-local agent path, function-call ID, trace ID, response ID, or thread ID **must not participate in the canonical protected-effect idempotency hash**.

Reason:

A provider may legitimately retry/re-emit the same logical protected call under a different provider-local call ID. If provider IDs were part of effect identity, the second emission could become a new mutation rather than converge on the first one.

Canonical protected-call request identity should derive from Soma authority/effect material such as:

```text
task_id
attempt_id
backend_ref
mandate/version
project/resource/scope generation
capability
tool operation
resource key
Soma-issued/validated idempotency key
payload hash
```

Provider provenance is stored as one or more evidence links against that canonical call request.

This preserves useful attribution without allowing provider-local identifiers to mint a new effect.

## 8.4 Idempotency-key authority

A provider model must not be trusted to invent arbitrary external-effect identity.

The protected operation's idempotency key should be:

- derived/issued by Soma from an assignment-defined action slot; or
- supplied through a mechanically validated contract under the active mandate.

Repeating the same key with different payload/tool/resource material is a conflict, not a second action.

## 8.5 `ProtectedToolEffectV1`

```text
ProtectedToolEffectV1
  schema_version = "protected_tool_effect.v1"
  call_request_id
  request_hash
  disposition
    prevented
    rejected
    acknowledged
    outcome_unknown
  external_effect_ref?
  external_effect_hash?
  evidence_ref
  evidence_hash
  completed_at
```

Rules:

- `acknowledged` requires durable effect/evidence identity appropriate to the tool;
- `outcome_unknown` is terminal for automatic send retry until exact external evidence resolves it;
- cancellation after an external action begins does not fabricate reversal;
- resource ownership is released only according to the real containment/effect contract;
- provider confidence or natural-language claims never substitute for effect proof.

---

# 9. Evidence/fan-in research bounds frozen for the first experiments

Iteration 4 validated one common strict envelope structurally across execution, retrieval, scout, and reasoning producer examples.

Iteration 5 freezes first-experiment bounds so the benchmark cannot expand outputs opportunistically by worker count.

## 9.1 `EvidenceSubmissionV1` bounds

```text
schema version: evidence_submission.v1
normal target serialized bytes: 12 KiB
hard serialized ceiling: 32 KiB
max executive summary: 1024 UTF-8 bytes
max claims: 12
max evidence records: 24
max artifacts: 12
max uncertainties: 12
max blockers: 8
max excerpt per evidence record: 512 characters
max provenance refs: 64
```

Full logs/documents/provider streams remain behind exact references.

The 12 KiB normal target intentionally aligns with Soma's current compact Task-response scale. The 32 KiB ceiling is escape capacity for evidence-rich lanes, not a new default.

## 9.2 `FanInV1` bounds

```text
normal target serialized bytes: 48 KiB
hard serialized ceiling: 64 KiB
max expected units: 32
max compact submission summaries: 32
max structured exact-key conflicts: 64
max unresolved uncertainty refs: 64
```

When compact fan-in exceeds the normal target, low-priority excerpts and repeated prose are removed before identities/hashes/missing-unit facts are dropped.

`truncated`, `has_more`, exact counts, and evidence retrieval pointers remain explicit.

## 9.3 Stable fact keys

For deterministic benchmark evaluation, assignments may define exact `fact_key` / `subject_key` vocabulary.

Workers may not invent canonical semantic keys and then claim Soma discovered equivalence. Assignment-provided keys allow Soma to mechanically detect contradictory structured values and duplicate assigned work without embedding-based semantic authority.

---

# 10. Frozen 1/2/4/8 canonical-concurrency benchmark corpus

## 10.1 Experiment question

The benchmark asks:

> Holding source material, assignments, backend/model, budgets, output schema, and synthesis method constant, what changes when Soma admits the same eight independent evidence WorkPackages with canonical concurrency 1, 2, 4, or 8?

It does **not** ask how many provider-native subagents are optimal.

Provider-internal subagents are disabled for this benchmark. That is a separate later experiment.

## 10.2 Frozen source corpus identity

Repository:

```text
soma
```

Commit:

```text
b53404fa9600412a4b3dd0fafd664a856096257b
```

Corpus identity domain:

```text
soma.agent_worker_benchmark.corpus.v1
```

Canonical corpus-manifest hash:

```text
a5feb6f20076bf17e64b51b66b65186b4b132417edeede83b7717472ac1df998
```

The corpus manifest contains only unit IDs, lane IDs, source paths, source SHA-256 values, repository name, and exact commit. Assignment text/gold rubric is versioned separately so source corpus identity does not change when evaluator wording is clarified without changing evidence bytes.

## 10.3 B01 - canonical Task/backend authority

Sources:

```text
soma/tasks/models.py
  d39aded14ca13647d2ed050b903eee53444d0b210b621db79a2c752c6521db63
soma/tasks/backends.py
  8e03377677eb72bf253a803cc18beeb516b570a89a63b689e9f0a5a21b57d522
soma/tasks/projections.py
  12755aa32b417025e52600bff3ca4afc39bd88d5a7365f6a1c19a246578187cb
```

Required fact keys/questions:

1. `task.canonical_state_owner` - what owns canonical task lifecycle?
2. `task.current_task_kind_set` - how many current TaskKind values are implemented in this source?
3. `task.current_backend_kind_set` - how many current BackendKind values are implemented?
4. `task.result_body_policy` - does the Task plane copy full authoritative result/evidence bodies?
5. `task.backend_protocol_shape` - which lifecycle operations does the current backend Protocol expose?

Critical trap:

```text
TaskState.ACCEPTED means the substantive WorkPackage outcome was accepted.
```

Expected answer: false. Task admission and substantive outcome acceptance are distinct concepts.

## 10.4 B02 - Company Kernel identity/authority

Sources:

```text
soma/company_kernel/models.py
  180bf13fdb5c777d579a34d1e056cfc85345453ddac9ef1c6e2c6356b35eff89
soma/company_kernel/schema.py
  4e19c27a18c685a1ccc866d37242f3aafc6131bd701971ee2517016cf5c0ed17
```

Required fact keys/questions:

1. `kernel.plan_revision_immutability` - what makes PlanRevision an immutable company-domain fact?
2. `kernel.work_package_route_neutrality` - which route-specific fields are forbidden from route-neutral WorkPackage identity?
3. `kernel.outcome_identity_inputs` - which exact plan/scope/package facts contribute to outcome identity?
4. `kernel.attempt_task_binding` - how does WorkPackageAttempt relate to canonical Task?
5. `kernel.topology_v1` - what WorkPackage topology is currently allowed?

Critical trap:

```text
WorkPackage stores its own running/completed execution lifecycle.
```

Expected answer: false.

## 10.5 B03 - Hermes headless/concurrency substrate

Sources:

```text
soma/hermes_companion_protocol.py
  17565bf31fb729b70ab2f7b460637168372570661c1712a7abd7731bc4d91259
soma/hermes_service_supervisor.py
  2a6c04546326edb84061091b55e4b91bfde7f341e2281d3acf78e0cf4c950c85
soma/hermes_concurrency.py
  20ad0f2ec31f4fe0530ee8992433692c12101c6b9981dfdec9457e5dd1ea9309
```

Required fact keys/questions:

1. `hermes.model_runtime_policy` - what proves the companion is headless?
2. `hermes.pinned_revision` - what exact Hermes revision is accepted by the protocol?
3. `hermes.supervisor_worker_ceiling` - what is the code ceiling for supervised workers?
4. `hermes.concurrency_meaning` - does more supervised worker capacity imply more independent reasoning minds?
5. `hermes.resource_mutation_lock` - how are same-resource mutations serialized in the Hermes service layer?

Critical trap:

```text
MAX_SUPERVISED_WORKERS = 32 proves Soma currently runs 32 Hermes workers.
```

Expected answer: false; a code ceiling is not current configured capacity.

## 10.6 B04 - legacy Workflow versus parallel-run substrates

Sources:

```text
soma/workflows/models.py
  e8fbacf95d2af7e95209dff6ec6b332b7f487b1743f69a41b317a4a561085bb1
soma/workflows/worker.py
  1329b34caaadad5bbcb782bb2db1f5f0ea611a22febda264471d9241af66cf4d
soma/parallel_groups.py
  e36145491349ab9fc774c586530cbf0dd28b9d4dc8f7ee5e2f02c52e1182bbee
```

Required fact keys/questions:

1. `workflow.graph_validation` - what dependency validation exists?
2. `workflow.active_child_cardinality` - how many active child runs does the Workflow runtime own at once?
3. `workflow.readiness_rule` - how does `_next_pending_step()` determine readiness?
4. `parallel_group.child_identity` - what durable identities/keys are reserved for parallel command children?
5. `parallel_group.relationship_to_workflow` - is the parallel command group the same lifecycle system as Workflow?

Critical trap:

```text
Because Workflow accepts a DAG definition, its runtime already performs concurrent fan-out/fan-in across independent steps.
```

Expected answer: false.

## 10.7 B05 - provider-adapter capability truth

Sources:

```text
soma/worker_adapters/contract.py
  dc7b4d9c54dd4bbac8cb9c6469acf4f6bf2c38e2131d9f340bd02fa3ce133653
soma/worker_adapters/codex.py
  64f2f9e0f6ac588b9f4d4e78a6a1eb14f6d77696a78827c92431e9244fba7dcd
soma/worker_adapters/claude_code.py
  02173b0ad5643c601b0e484a339d8057d63c435ec6f210eb6b2c935a5c4cfd06
```

Required fact keys/questions:

1. `adapter.capability_declaration_completeness` - what happens if a capability is omitted?
2. `adapter.capability_support_vocabulary` - what are the three support values?
3. `adapter.provider_completion_semantics` - is a provider completion event canonical Task success?
4. `adapter.protocol_uncertainty` - what kinds of stream evidence force fail-closed uncertainty?
5. `adapter.cancellation_measurement` - what does current evidence say about orphan-free root cancellation for Claude Code and Codex?

Critical trap:

```text
An undeclared provider capability may be treated as supported when the adapter does not say otherwise.
```

Expected answer: false; incomplete declarations are refused.

## 10.8 B06 - interaction delivery durability

Sources:

```text
soma/worker_substrate/models.py
  bfbcc8c3b88a3065d846a72b01b375d9853bc1618cd4033563a1f4375c75fb64
soma/worker_substrate/coordinator.py
  62ca7ae5737009c324f45a6994cac5a10a8fe8d1a101b1502b219e43022f152f
soma/worker_substrate/dispatch.py
  d8134e563d1dfb21a67372233f3ba3f3f2a4a560dd76501427c09ff1c015b7f7
```

Required fact keys/questions:

1. `interaction.atomic_reservation` - which canonical/subordinate records are reserved together?
2. `interaction.persist_before_send` - what is durable before the transport call occurs?
3. `interaction.outcome_unknown_rule` - what happens after an ambiguous post-claim transport failure?
4. `interaction.authority_fields` - which project/resource/task/run/session/mandate identities are carried?
5. `interaction.lifecycle_ownership` - does the interaction message become a second running Task lifecycle?

Critical trap:

```text
If transport raises after the durable send claim, recovery may safely resend the message automatically.
```

Expected answer: false.

## 10.9 B07 - ProjectScope and mutation containment

Sources:

```text
soma/project_scope/store.py
  2b7ff63cf289612385bc591a1860657264163da194c0d76fd9929435bacd5a06
soma/operation_locks.py
  c5b4b2938ab407b71db65eba88a70ae82b06361de23d81d333655f38750ccb18
```

Required fact keys/questions:

1. `scope.binding_identity` - what exact project/resource/repository facts are validated?
2. `scope.transaction_pattern` - what transaction pattern protects scope mutations/reservations?
3. `lock.current_granularity` - what is the current OperationLockStore lock key/granularity?
4. `lock.duplicate_detection` - how is duplicate active operation input identified?
5. `lock.stale_ownership` - what evidence is considered before stale ownership is reclaimed?

Critical trap:

```text
An organisational/model role that is allowed to propose repository work automatically owns the repository operation lock.
```

Expected answer: unsupported/false; concrete lock ownership is mechanical, not inferred from reasoning authority.

## 10.10 B08 - Run/publication/recovery truth

Sources:

```text
soma/run_store.py
  f2fb3407330e6247b89c620706cc431ce79e78222d17edbe913e0ca8917b550b
soma/run_public_result.py
  c1ee8dfad1be401f99a6ce535c1861d095f90adba75c89572e3b79fe14993be2
```

Required fact keys/questions:

1. `run.terminal_status_vocabulary` - what current durable Run statuses are terminal?
2. `run.awaiting_controller_semantics` - how is current non-terminal owner waiting represented?
3. `run.legacy_model_tools` - what is the status of historical Codex run-tool identifiers?
4. `run.publication_identity` - which fields establish durable public-result publication identity?
5. `run.normalized_outcome_separation` - does public projection success alone create Company Kernel OutcomeAcceptance?

Critical trap:

```text
Historical `needs_input` rows are the same non-terminal interactive state used by the current V3 interactive path.
```

Expected answer: false; historical `needs_input` is terminal compatibility data, while current interactive waiting uses `awaiting_controller`.

---

# 11. Benchmark common assignment contract

Every B01-B08 unit receives only its immutable source packet and this common instruction family:

```text
Using only the supplied frozen source packet, answer the unit's exact fact-key questions.

For each claim:
- classify it as observation, inference, recommendation, or negative_finding;
- bind it to the assignment-provided fact_key when one exists;
- cite exact source path + bounded locator/reference;
- attach the source/evidence hash where available;
- say uncertain/unsupported when the packet does not establish a claim;
- do not import knowledge from other Soma files, chat history, web sources, or provider reputation;
- do not implement or modify anything.

Return EvidenceSubmissionV1 only.
```

The assignment packet hash includes:

- corpus manifest hash;
- unit ID;
- exact question/rubric version;
- EvidenceSubmission contract version and byte limits.

All four concurrency conditions receive byte-identical assignment packets.

---

# 12. Benchmark conditions

## 12.1 Canonical concurrency only

```text
C1: max 1 canonical WorkPackage/Task active at once
C2: max 2
C4: max 4
C8: max 8
```

Every condition executes **all eight** B01-B08 units.

Nothing about decomposition, source coverage, questions, output schema, or required facts changes between conditions.

## 12.2 Fixed controls

Across C1/C2/C4/C8 keep constant:

- exact corpus commit/hashes;
- exact eight work units;
- exact assignment packets;
- same provider/backend/model version;
- same reasoning settings;
- same tool policy;
- same read-only authority;
- same per-unit time/token/output limits;
- same EvidenceSubmission contract;
- same FanIn contract;
- same final synthesis instruction/model;
- provider-internal subagent concurrency disabled/1;
- no external mutation;
- no changing internet sources;
- no conversation-history carry-over between unit workers.

This isolates Soma-level concurrency as the independent variable.

## 12.3 Do not confuse two experiments

Canonical benchmark:

```text
8 Soma WorkPackages / Tasks
provider-internal subagents disabled
vary Soma concurrency 1/2/4/8
```

Later native-agent benchmark:

```text
1 Soma reasoning Task
vary provider-internal subagent topology/concurrency
```

Do not combine these in the first measurement.

---

# 13. Benchmark metrics and predeclared quality gate

## 13.1 Deterministic lane-quality metrics

Each lane has assignment-provided fact keys and a frozen gold rubric.

Measure:

- required fact-key recall;
- fact-key correctness;
- evidence-reference validity;
- evidence precision: does cited evidence actually support the structured claim?
- unsupported-assertion rate;
- critical-trap failures;
- missing/partial/uncertain unit count;
- schema-valid submission rate.

The benchmark should not award points merely for verbose prose.

## 13.2 Aggregate/synthesis metrics

Measure:

- final architecture conclusion correctness;
- required cross-lane coverage;
- whether conflicts/uncertainties are preserved rather than erased;
- whether synthesis invents facts not present in fan-in evidence;
- synthesis input bytes/tokens;
- synthesis output tokens;
- aggregate evidence bytes;
- exact missing-unit reporting.

## 13.3 Efficiency metrics

Measure:

- wall-clock makespan from first admission to fan-in readiness;
- per-unit latency;
- total provider input/output tokens;
- provider-reported cost when available;
- total Task/backend starts;
- retry/recovery count;
- evidence bytes per useful required fact;
- duplicate-work ratio using assignment-defined fact keys rather than embedding similarity.

## 13.4 Quality gate before claiming a concurrency win

A non-C1 condition is not considered an architectural improvement merely because it is faster.

Candidate must satisfy all of:

```text
critical trap failures = 0
schema-valid submission rate = 100%
unsupported assertion rate <= 5%
fact-key recall no more than 2 percentage points below confirmed C1 baseline
evidence precision no more than 2 percentage points below confirmed C1 baseline
no missing unit hidden from FanInV1
```

Among candidates that pass quality gates:

1. prefer lower confirmed wall-clock makespan;
2. if makespan differs by <= 5%, prefer lower total provider cost/tokens;
3. if still effectively tied, prefer lower synthesis input burden/evidence bytes.

No preference for 4 or 8 workers is hard-coded. The earlier "4 may be a sweet spot" remains a hypothesis only.

## 13.5 Repetition strategy

To control cost without pretending one noisy run is proof:

### Phase A - screening

Run one C1, C2, C4, and C8 trial.

No architecture choice is accepted from Phase A alone.

### Phase B - confirmation

Take C1 plus the two best non-C1 candidates that passed the screening quality gate. Run each condition two additional times.

This yields three observations per confirmed condition while avoiding automatic expenditure on obviously bad candidates.

If Phase A leaves only one non-C1 candidate, confirm C1 and that candidate only.

Condition execution order in the confirmation phase should be randomized/predeclared so time-of-day/provider load is less confounded with one concurrency value.

## 13.6 Recovery tests are separate

Controller disconnect/reconnect, provider loss, one-unit timeout, and stale dependency-proof recovery are important but are not mixed into the baseline concurrency benchmark.

After selecting a viable concurrency condition, run a separate recovery matrix so ordinary throughput and failure recovery remain distinguishable measurements.

---

# 14. Benchmark gold-rubric discipline

The frozen benchmark should maintain two distinct evaluator layers.

## Mechanical evaluator

Can score:

- JSON/schema validity;
- required unit/fact-key coverage;
- exact source path/hash existence;
- line/locator validity;
- exact enum/value questions;
- declared trap yes/no correctness;
- duplicate IDs;
- evidence byte limits;
- missing-unit honesty.

## Sol/human semantic evaluator

Needed for:

- whether a cited passage actually supports a nuanced natural-language inference;
- architecture synthesis quality;
- whether a recommendation follows reasonably from facts;
- whether an uncertainty was material.

The semantic evaluator is not allowed to silently change gold source facts after seeing which concurrency condition produced them. Any rubric correction is versioned and reruns affected comparisons.

---

# 15. Provider pilot ordering after contract freeze

If the owner later authorizes experiments, Iteration 5 recommends this order:

```text
1. OAI-R1 - single-agent Responses background durability
2. OAI-R2 - Responses Multi-agent provenance, read-only
3. OAI-A1 - Agents SDK local provenance/state, tracing supplemental
4. CDX-R1 - Codex App Server subagent/thread provenance
5. OAI-R3 - only then test Multi-agent + durable/background combination
6. canonical 1/2/4/8 benchmark once one reasoning backend path is sufficiently durable
7. provider-internal native-subagent benchmark separately
8. protected mutation experiments only after broker authority is implemented/reviewed
```

This ordering prioritizes recovering one reasoning operation correctly before multiplying it.

---

# 16. Facts, inferences, hypotheses, rejected ideas, and bugs

## Facts from Soma source

1. Current canonical Task projections are compact and reference authoritative evidence instead of duplicating result bodies.
2. Current `ExecutionBackend` already has a reserve/start/query/cancel/result-reference shape useful as a reasoning-backend precedent.
3. Current Company Kernel WorkPackage outcome identity includes PlanRevision identity and excludes provider/Task/Run route fields.
4. Current WorkPackageAttempt binds one unique canonical Task and v1 topology is `single_active`.
5. Current Workflow graph validation is bounded but its worker owns one active child at a time.
6. Current provider adapter contract refuses incomplete capability declarations and treats provider completion/failure as claims, not canonical Task state.
7. Current worker-substrate dispatch persists/claims before transport and records ambiguous post-claim sends as outcome unknown with resend forbidden.
8. Current ProjectScope/Task/Run stores provide transaction/idempotency primitives that a future graph coordinator can compose rather than replace.
9. Current repository OperationLockStore is repository-granular; it is not a general arbitrary-resource capability broker.
10. Historical Codex run-tool identifiers in RunStore are inert read-only compatibility values, while current interactive waiting uses `awaiting_controller` rather than historical terminal `needs_input`.

## Facts from current official OpenAI documentation

1. Responses Multi-agent is a beta GPT-5.6 feature for model-directed parallel subagent work.
2. OpenAI documents it as useful for independent bounded work and less suitable for fixed deterministic graphs or shared mutable-resource contention.
3. Multi-agent output exposes provider-local agent attribution and collaboration/tool-call evidence useful for provenance.
4. Multi-agent agents receive the request's configured tools, so provider-local child identity alone is not an authority boundary.
5. Background Responses expose durable response IDs, polling, cancellation, and documented stream-resume cursor behavior after a response is created in the supported mode.
6. The official material consulted did not establish a caller-provided Responses create idempotency contract that closes an acknowledgement-loss window.
7. The official material consulted did not establish Multi-agent + background as one combined supported durability contract; this remains unmeasured.
8. Agents SDK result surfaces expose locally inspectable run items/raw responses/final output/state, while tracing can be disabled and is unavailable under ZDR.
9. Codex App Server documents richer thread/session/lineage/protocol surfaces than the simple CLI adapter alone, and generated schemas provide a plausible drift-control mechanism.

## Inferences / design conclusions

1. `PlanGraphManifestV1` must be independent of post-plan IDs to avoid circular content identity.
2. 32 packages / 128 edges is a reasonable first bounded graph contract for personal orchestration, subject to later measurement.
3. Dependency proof identity should exclude timestamps and unrelated version churn while retaining exact satisfying evidence identity.
4. `settled` needs an attempt-set hash, not merely a terminal Task reference.
5. Reasoning-provider start delivery needs its own durable uncertainty record before provider-native operation identity is known.
6. Provider-local agent/call IDs should be evidence-only for protected mutations and excluded from canonical effect idempotency identity.
7. Agents SDK local result/item capture should be primary provenance; traces should be supplemental.
8. Codex App Server stdio JSON-RPC is the leading deep-provenance pilot target, while existing CLI adapter evidence remains useful for current bounded Codex sessions.
9. Canonical WorkPackage concurrency and native-provider subagent concurrency must be benchmarked separately.

## Hypotheses for measurement

1. C4 will often provide most of the latency benefit of C8 with less fan-in/duplication burden, but the benchmark is explicitly designed not to assume this.
2. Freezing dependency proofs will materially improve deterministic recovery after reconnect/restart.
3. A single Soma reasoning Task backed by native provider subagents will often be simpler than mirroring provider children into canonical Tasks.
4. The 12 KiB normal EvidenceSubmission target and 48 KiB FanIn target will preserve adequate source-grounded quality for the eight-lane benchmark.
5. Responses background mode can serve as a durable reasoning backend after the provider operation ID is known; the create-ack window may still require explicit uncertainty handling.

## Rejected ideas

- including `plan_revision_id`, `work_package_id`, or `outcome_id` inside pre-PlanRevision graph identity;
- list order affecting graph identity;
- dynamic graph mutation under an unchanged PlanRevision;
- one untyped dependency reference for all satisfaction classes;
- timestamp-dependent dependency proof identity;
- treating one terminal upstream Task as sufficient proof that an entire attempt set is settled;
- assuming a provider create call can always be retried safely after acknowledgement loss;
- treating provider completion as canonical Task success;
- provider-local agent path/call ID as mutation authority or external-effect idempotency identity;
- tracing as the sole Agents SDK provenance source;
- using Codex experimental WebSocket App Server transport as first production proof;
- mixing Soma 1/2/4/8 WorkPackage concurrency with provider-native subagent concurrency in one benchmark;
- giving C8 more work or more source coverage than C1;
- accepting a faster condition if it loses material evidence quality;
- running recovery fault injection inside the baseline throughput comparison.

## Confirmed bugs

None recorded in Iteration 5.

The create-ack uncertainty discussed for future provider runtimes is an architecture risk/unmeasured contract boundary, not a confirmed OpenAI or Soma bug.

---

# 17. Iteration 5 frozen research decisions

1. **`PlanGraphManifestV1` excludes PlanRevision/WorkPackage/outcome IDs to avoid circular identity.**
2. **Graph v1 freezes 32 packages and 128 dependency edges as research bounds.**
3. **Graph identity is order-insensitive via explicit canonical sorting and domain-separated SHA-256.**
4. **PlanRevision remains the immutable graph commit; normalized package/edge facts must reconstruct to the same graph hash.**
5. **`DependencySatisfactionProofV1` is a strict tagged union for accepted outcome, published success, evidence available, and settled.**
6. **Dependency proof stable identity excludes observation timestamp and unrelated kernel-version churn.**
7. **`settled` binds an exact upstream attempt-set hash.**
8. **Downstream Attempt identity binds exact dependency-proof refs/hashes.**
9. **Graph acceptance is one bounded all-or-nothing transaction ending in current-plan CAS.**
10. **Reasoning is a provider-neutral Task backend, not a second agent lifecycle authority.**
11. **Soma reserves backend identity and start-attempt truth before provider create/send.**
12. **A provider create request with unknown acknowledgement and no proven recovery/idempotency becomes `outcome_unknown`; no blind resubmit.**
13. **Provider operation/session/agent/trace IDs remain subordinate bindings/evidence.**
14. **Agents SDK local items/raw responses/state are primary provenance; tracing is supplemental.**
15. **Codex App Server stdio JSON-RPC is the leading future deep-subagent provenance pilot surface.**
16. **Every protected mutation crosses a Soma broker that revalidates Task, mandate, scope, capability, lock, idempotency, expiry, and payload hash.**
17. **Provider-local provenance does not participate in canonical external-effect identity.**
18. **EvidenceSubmission normal target/hard ceiling freeze at 12 KiB / 32 KiB for first experiments; FanIn at 48 KiB / 64 KiB.**
19. **The canonical concurrency corpus is frozen to eight source lanes at Soma commit `b53404f`, corpus hash `a5feb6f20076bf17e64b51b66b65186b4b132417edeede83b7717472ac1df998`.**
20. **C1/C2/C4/C8 execute the same eight units; only Soma admission concurrency changes.**
21. **Provider-internal subagents are disabled in the canonical benchmark and measured separately later.**
22. **No concurrency value is preferred before quality-gated measurement.**

These are research contract decisions/candidates only. They do not authorize implementation.

---

# 18. What remains before any experiment is authorized

The architecture is now sufficiently specified that more broad conceptual research is unlikely to be the highest-value next step.

The next useful work is an **experiment gate/preflight**, not immediate execution.

Exact next questions:

1. Which reasoning backend/provider/model should be used for the first low-cost durability pilot, and what credentials/cost ceiling would that require?
2. What exact disposable provider-test packet will OAI-R1 use so no mutable repository/business side effect is possible?
3. What exact event/result fields must OAI-R1 capture before the pilot can be accepted?
4. What constitutes a reproducible create-ack ambiguity test without manufacturing unsafe duplicate provider work?
5. What exact current provider pricing/token ceiling should be budgeted before any 8-unit benchmark is authorized?
6. Should the first benchmark use the strongest reasoning model or a cheaper fixed model to measure scheduler behavior before a quality benchmark with the strongest model?
7. How should the frozen gold rubric be stored/versioned without modifying production authority code?
8. What exact read-only adapter or packet-delivery path feeds the frozen commit bytes to workers without relying on a changing worktree?
9. What synthetic crash/replay tests can be completed without any provider/model call before the provider pilot?
10. What explicit owner authorization phrase/gate should be required before spending provider quota or launching model workers?
11. After a durable single-agent reasoning backend passes, should canonical C1/C2/C4/C8 be measured before native Multi-agent, or should OAI-R2 provenance be completed first? Leading recommendation: provenance pilot first, canonical benchmark second.
12. What measured result would justify implementation of graph/dependency schemas versus continuing to use the current single-active Kernel-of-One shape?

Iteration 5 ends here. No provider/model experiment, benchmark run, production implementation, commit, push, restart, or connector refresh was performed.

---

# Sources consulted

## Soma repository evidence

- `soma/tasks/models.py`
- `soma/tasks/backends.py`
- `soma/tasks/projections.py`
- `soma/company_kernel/models.py`
- `soma/company_kernel/schema.py`
- `soma/hermes_companion_protocol.py`
- `soma/hermes_service_supervisor.py`
- `soma/hermes_concurrency.py`
- `soma/workflows/models.py`
- `soma/workflows/worker.py`
- `soma/parallel_groups.py`
- `soma/worker_adapters/contract.py`
- `soma/worker_adapters/codex.py`
- `soma/worker_adapters/claude_code.py`
- `soma/worker_substrate/models.py`
- `soma/worker_substrate/coordinator.py`
- `soma/worker_substrate/dispatch.py`
- `soma/project_scope/store.py`
- `soma/operation_locks.py`
- `soma/run_store.py`
- `soma/run_public_result.py`
- Iterations 1-4 under `docs/agent-worker-research/`

## Current official OpenAI primary sources

- Responses Multi-agent: `https://developers.openai.com/api/docs/guides/responses-multi-agent`
- Responses Background mode: `https://developers.openai.com/api/docs/guides/background`
- GPT-5.6 / current model guidance: `https://developers.openai.com/api/docs/guides/latest-model`
- OpenAI Agents SDK Results: `https://openai.github.io/openai-agents-python/results/`
- OpenAI Agents SDK running agents / RunConfig: `https://openai.github.io/openai-agents-python/running_agents/`
- OpenAI Agents SDK tracing: `https://openai.github.io/openai-agents-python/tracing/`
- OpenAI Agents SDK tracing reference: `https://openai.github.io/openai-agents-python/ref/tracing/`
- Codex App Server: official Codex developer documentation for App Server protocol, thread/session lifecycle, generated schemas, and streamed items
- ChatGPT/Codex Subagents: official OpenAI agent-configuration documentation

## Synthetic research validation

In-memory Pydantic-style checks only:

- `PlanGraphManifestV1` order-independence, cycle/missing-endpoint/selector rejection;
- `DependencySatisfactionProofV1` tagged-union matching;
- `ReasoningSpecV1` bounded/reference-first shape;
- protected mutation request/effect structural shape;
- benchmark corpus-manifest canonical hashing.

No synthetic check wrote repository source, opened a provider session, or changed production state.
