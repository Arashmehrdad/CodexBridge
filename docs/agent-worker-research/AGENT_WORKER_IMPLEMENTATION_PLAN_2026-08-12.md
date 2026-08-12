# Soma Agent / Worker Architecture - Canonical Implementation Plan

Date: 2026-08-12
Status: HOLD - DO NOT EXECUTE UNTIL THE NORMAL-CHAT TOOL UX LANE IS COMPLETE AND ACCEPTED
Research basis: Iterations 1-5 under `docs/agent-worker-research/`
Frozen research source point: `b53404fa9600412a4b3dd0fafd664a856096257b`
Frozen benchmark corpus hash: `a5feb6f20076bf17e64b51b66b65186b4b132417edeede83b7717472ac1df998`

## 1. Purpose

This plan converts the completed agent/worker architecture research into a bounded implementation program for Soma.

The target architecture is:

```text
Owner
  |
ChatGPT / Sol
semantic reasoning + decomposition
  |
Mission
  |
immutable PlanRevision
exact graph manifest/hash
  |
+---------------- WorkPackage DAG ----------------+
|                                                 |
WorkPackage                                 WorkPackage
|                                                 |
dependency satisfaction proofs                    |
|                                                 |
+------------------- readiness -------------------+
                                                  |
                                       WorkPackageAttempt
                                                  |
                                           canonical Task
                                                  |
                                      provider-neutral backend
                         +----------------+----------------+
                         |                |                |
                     execution        retrieval        reasoning
                                                          |
                                                native provider
                                                 subagent tree
                                                when beneficial
                                                          |
                                              EvidenceSubmission
                         +----------------+----------------+
                                                  |
                                                FanIn
                                                  |
                                                 Sol
                                       adjudication + synthesis
```

Soma owns durable identity, deterministic graph mechanics, admission, cancellation, recovery, evidence identity, authority, and exact external-effect protection.

Sol remains the semantic reasoning head. Soma must not become a competing planner/reasoning brain.

This plan does not authorize implementation while the normal-Chat Tool UX lane is active.

---

# 2. Non-negotiable architecture invariants

Every implementation stage must preserve these rules.

1. No new canonical `WorkPlan` identity.
2. Mission is the long-lived semantic root for decomposed work.
3. PlanRevision is the exact immutable accepted plan/graph commit.
4. WorkPackage is route-neutral durable work/outcome intent.
5. WorkPackageAttempt is route-specific and remains `single_active` in v1.
6. Canonical Task owns execution-attempt lifecycle.
7. Run/provider/process/session identity remains subordinate execution evidence.
8. Provider-native subagents stay below one canonical Task unless Soma independently needs durable ownership of that child.
9. Worker role labels are capability profiles, not a new canonical enum/lifecycle.
10. Plan graph facts never become a second runnable lifecycle machine.
11. Readiness is derived mechanically from immutable graph facts plus exact dependency proofs.
12. Semantic correctness/acceptance remains with Sol / configured acceptance authority, never inferred from Task completion.
13. Provider completion is a claim until canonical Task/backend reconciliation publishes valid bounded evidence/result identity.
14. Provider-local agent/call/thread/trace IDs are provenance only.
15. Provider-local IDs never mint canonical external-effect idempotency.
16. Soma-owned backend identity is reserved before provider create/start.
17. Ambiguous provider create acknowledgement becomes `outcome_unknown`; no blind duplicate create.
18. Protected mutation is read-only by default and must cross a Soma-controlled broker.
19. Selecting a new PlanRevision is not cancellation and must not fabricate containment.
20. Old-plan read-only work may finish as evidence; conflicting mutation authority must be contained before new conflicting mutation is admitted.
21. Dependency satisfaction is frozen into the downstream WorkPackageAttempt at admission.
22. Evidence crosses worker boundaries as bounded claims + references + provenance, not transcript aggregation.
23. Canonical WorkPackage concurrency and provider-internal subagent concurrency are separate experiments.
24. No concurrency value is preferred before quality-gated measurement.

If any stage requires violating one of these invariants, stop as BLOCKED and revise the architecture deliberately rather than improvising.

---

# 3. Current repository baseline and implementation seams

Research source point: `b53404fa9600412a4b3dd0fafd664a856096257b`.

Important current seams at that source point:

## 3.1 Company Kernel

Current package:

```text
soma/company_kernel/
  __init__.py
  models.py
  schema.py
  store.py
```

Current state:

- schema version 1;
- models exist for Company, Mission, PlanRevision, WorkPackage, WorkPackageAttempt, AcceptanceCommit, KernelReconciliationReceipt;
- schema/store are deliberately inactive;
- `CompanyKernelStore` has schema inspection/migration only;
- no runtime Company/Mission/plan/package/attempt/acceptance gateway exists;
- no dependency-edge table exists;
- WorkPackage topology is `single_active`;
- PlanRevision and WorkPackage facts are immutable;
- `missions.current_plan_revision_id` is the mutable current-plan pointer.

## 3.2 Canonical Task plane

Current Task plane already provides the strongest implementation precedent:

```text
reserve backend identity
-> reserve Task
-> start backend
-> query bounded observation
-> cancel backend
-> publish result/evidence reference
-> reconcile canonical Task state
```

Relevant files:

```text
soma/tasks/models.py
soma/tasks/backends.py
soma/tasks/store.py
soma/tasks/manager.py
soma/tasks/projections.py
```

Current v1 implementation only has:

```text
TaskKind.DURABLE_COMMAND
BackendKind.SOMA_DURABLE_RUN
```

Do not fork Task lifecycle for reasoning work. Extend backend selection behind Task.

## 3.3 Shared SQLite transaction precedent

Company Kernel, Task, ProjectScope, and Run facts live in the shared `runs/soma.sqlite3` database.

Use existing `BEGIN IMMEDIATE` patterns and connection-scoped Task/ProjectScope methods rather than inventing a second transaction coordinator.

## 3.4 Mutation/resource authority

Existing useful precedents:

```text
ProjectScopeStore
OperationLockStore
Hermes ResourceMutationLocks
Task/Run cancellation + containment evidence
worker-substrate persist-before-send delivery
```

These are precedents, not yet the final provider-neutral protected mutation broker.

---

# 4. Global execution discipline

This plan is intentionally split into micro-stages.

For Luna/Codex/Claude or any later implementation agent, one invocation executes exactly one named stage.

Every stage follows:

```text
READ required evidence
VERIFY entry conditions
MAKE only stage-authorized changes
RUN exact validation
WRITE/RETURN acceptance report
STOP
```

Never instruct an implementation agent with only `continue`.

Use:

```text
Execute <exact stage ID and title> only.
Stop after the acceptance report.
Do not begin the next stage.
```

On discrepancy:

```text
STATUS: BLOCKED
expected state
observed state
exact discrepancy
affected files/symbols
safest options
STOP
```

Global prohibitions unless a later exact stage explicitly authorizes them:

- no push;
- no service restart;
- no ChatGPT connector refresh;
- no Plugin installation;
- no real provider/model worker launch;
- no paid provider use;
- no protected/external mutation experiment;
- no wiki refresh;
- no canonical-memory mutation;
- no unrelated refactor;
- no global EOL normalization;
- no touching unrelated owner work;
- no combining this lane with normal-Chat Tool UX implementation.

---

# 5. HOLD / entry gate

## HOLD-0 - Wait for current normal-Chat UX lane

This agent/worker implementation must remain dormant until the current normal-Chat Tool UX program reaches a stable accepted checkpoint.

Minimum entry conditions:

1. the UX implementation stage currently in progress is accepted;
2. its intended local commits are complete;
3. no unresolved B/B1/B2/B3/B4 repair work remains;
4. any required live UX A/B gates have either completed or the owner explicitly parks them;
5. the owner explicitly says to begin the agent/worker implementation lane.

Do not infer permission merely because the UX files look idle.

---

# 6. P0 - Preserve research and reconcile post-UX source drift

## P0.1 - Preserve the agent/worker research bundle

Purpose: make the five research iterations plus this implementation plan a durable local baseline after the current UX lane is complete.

Include only:

```text
docs/agent-worker-research/iteration-01-current-capability-and-architecture-baseline-2026-08-12.md
docs/agent-worker-research/iteration-02-worker-contract-dag-and-evidence-baseline-2026-08-12.md
docs/agent-worker-research/iteration-03-identity-revision-attempt-and-fanin-contract-2026-08-12.md
docs/agent-worker-research/iteration-04-dag-replanning-and-reasoning-backend-contract-2026-08-12.md
docs/agent-worker-research/iteration-05-frozen-graph-reasoning-broker-and-benchmark-contracts-2026-08-12.md
docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md
```

Required checks:

- Iteration 5 SHA-256 remains `dc9afbfd94525890922225839488cc7b25e9798d0c61271d4bf3f0ea97d19cdb` unless an explicitly reviewed research correction occurred;
- no production source enters the commit;
- unrelated owner files are excluded;
- local commit only;
- no push.

Endpoint: one research/plan preservation commit; STOP.

## P0.2 - Post-UX architecture drift audit

Purpose: research was frozen against `b53404f`; implementation will begin from a later HEAD. Reconcile exact drift before touching architecture.

Compare the implementation HEAD against `b53404f` for at least:

```text
soma/company_kernel/
soma/tasks/
soma/project_scope/
soma/operation_locks.py
soma/hermes_companion_protocol.py
soma/hermes_service_supervisor.py
soma/hermes_concurrency.py
soma/workflows/
soma/parallel_groups.py
soma/worker_adapters/
soma/worker_substrate/
soma/run_store.py
soma/run_public_result.py
```

Classify every relevant difference as:

```text
compatible
requires-plan-adjustment
invalidates-research-assumption
unrelated
```

Hard rule: do not adapt production architecture during this audit.

If a research assumption is invalidated, update this plan/research reconciliation first and STOP.

Endpoint: `docs/agent-worker-research/P0_2_POST_UX_DRIFT_ACCEPTANCE_<date>.md`; no production change; STOP.

---

# 7. G1 - Immutable graph contracts and PlanRevision graph transaction

Implementation Gate 1 establishes graph identity and storage while keeping the Company Kernel runtime inactive and launching no Task/provider.

## G1.1 - Pure graph and dependency contract models

Create:

```text
soma/company_kernel/graph_models.py
tests/test_company_kernel_graph_contracts.py
```

Do not alter database schema yet.

Implement versioned pure contracts:

```text
PlanGraphManifestV1
PlanGraphNodeV1
PlanGraphDependencyEdgeV1
DependencySatisfactionProofV1
AcceptedOutcomeSatisfactionV1
PublishedSuccessSatisfactionV1
EvidenceAvailableSatisfactionV1
SettledSatisfactionV1
```

Freeze constants:

```text
PLAN_GRAPH_SCHEMA_VERSION = "plan_graph_manifest.v1"
DEPENDENCY_PROOF_SCHEMA_VERSION = "dependency_satisfaction_proof.v1"
MAX_PACKAGES_PER_PLAN_GRAPH = 32
MAX_DEPENDENCY_EDGES_PER_PLAN_GRAPH = 128
```

Identity domains:

```text
soma.company_kernel.plan_graph.v1
soma.company_kernel.dependency_edge.v1
soma.company_kernel.dependency_proof.v1
```

Manifest fields exactly follow Iteration 5:

```text
mission_id
project_id
resource_id
scope_generation
package_nodes[1..32]
  package_key
  work_package_contract_hash
  target_resource_id
  evidence_requirements_hash?
dependency_edges[0..128]
  upstream_package_key
  downstream_package_key
  requirement
  evidence_selector_ref?
  evidence_selector_hash?
```

Manifest must reject:

- PlanRevision ID;
- WorkPackage ID;
- outcome ID;
- Task/Run/provider/session/process route facts;
- duplicate package keys;
- missing endpoints;
- self edges;
- duplicate canonical edges;
- cycles;
- unknown dependency requirements;
- invalid evidence selector rules;
- package/resource escape from Mission scope ceiling.

Canonicalization:

1. nodes sort by `package_key`;
2. edges sort by upstream key, downstream key, requirement, selector hash-or-empty;
3. UTF-8 JSON, sorted keys, compact separators, `ensure_ascii=False`;
4. lowercase SHA-256;
5. timestamps/generated IDs excluded.

Dependency requirements exactly:

```text
accepted_outcome
published_success
evidence_available
settled
```

`DependencySatisfactionProofV1.proof_hash` stable material excludes `observed_at` and `observed_kernel_state_version`.

`settled` requires `attempt_set_hash`.

Tests must prove:

- forward/reversed manifest inputs produce identical graph hash;
- cycle rejection;
- missing endpoint rejection;
- duplicate edge/node rejection;
- selector rules;
- route-specific identity rejection;
- dependency proof union tag must match requirement;
- timestamp/version changes alone do not change proof hash;
- satisfying identity changes do change proof hash.

Endpoint: pure contracts pass; Company Kernel schema/runtime still unchanged; STOP.

## G1.2 - Additive Company Kernel graph schema v2

Modify:

```text
soma/company_kernel/models.py
soma/company_kernel/schema.py
soma/company_kernel/store.py
soma/company_kernel/__init__.py
tests/test_company_kernel_schema_models.py
```

Bump only:

```text
COMPANY_KERNEL_SCHEMA_VERSION: 1 -> 2
```

Do not rewrite migration 1.

Add migration 2 with these immutable normalized graph tables.

### `plan_graph_manifests`

Columns:

```text
plan_revision_id TEXT PRIMARY KEY
mission_id TEXT NOT NULL
schema_version TEXT NOT NULL
manifest_json TEXT NOT NULL
manifest_hash TEXT NOT NULL CHECK(length(manifest_hash)=64)
package_count INTEGER NOT NULL CHECK(package_count BETWEEN 1 AND 32)
edge_count INTEGER NOT NULL CHECK(edge_count BETWEEN 0 AND 128)
created_at TEXT NOT NULL
```

Constraints:

- FK `(mission_id, plan_revision_id)` -> `plan_revisions`;
- UNIQUE `(mission_id, manifest_hash)`;
- immutable update/delete triggers.

### `work_package_dependencies`

Before creating composite FKs, add a unique index proving WorkPackage plan membership:

```text
(work_package_id, mission_id, plan_revision_id)
```

Columns:

```text
edge_id TEXT PRIMARY KEY
mission_id TEXT NOT NULL
plan_revision_id TEXT NOT NULL
upstream_work_package_id TEXT NOT NULL
downstream_work_package_id TEXT NOT NULL
requirement TEXT NOT NULL
evidence_selector_ref TEXT NOT NULL DEFAULT ''
evidence_selector_hash TEXT NOT NULL DEFAULT ''
edge_hash TEXT NOT NULL CHECK(length(edge_hash)=64)
created_at TEXT NOT NULL
```

Constraints:

- upstream != downstream;
- requirement in the frozen four-value vocabulary;
- selector ref/hash required together only for `evidence_available`;
- non-evidence requirements carry no selector;
- both package FKs include mission + plan revision;
- UNIQUE `(plan_revision_id, edge_hash)`;
- immutable update/delete triggers.

Do NOT add dependency-proof storage in G1.2; proofs are admission facts and belong to G3.

Migration tests:

- v1 -> v2 additive migration preserves all incumbent rows;
- fresh v2 install is complete/idempotent/inactive;
- rollback is all-or-nothing;
- foreign-key/integrity check passes;
- graph tables immutable;
- malformed selector/requirement/self-edge rejected by DB where mechanically enforceable;
- no existing PlanRevision/WorkPackage rows are backfilled or inferred.

Endpoint: schema v2 exists but `active_capability` remains false; STOP.

## G1.3 - Atomic graph-capable PlanRevision acceptance service

Create:

```text
soma/company_kernel/service.py
tests/test_company_kernel_graph_service.py
```

Add a shared `BEGIN IMMEDIATE` transaction context to `CompanyKernelStore` if not already present.

Implement an internal service only. No public gateway and no runtime activation.

Primary operation:

```text
accept_plan_graph(...)
```

Input must include:

- exact company/mission identity;
- expected current PlanRevision ID or explicit no-current marker;
- expected `plan_state_version`;
- expected `kernel_state_version`;
- exact active ProjectScope project/resource/generation;
- caller controller request ID;
- accepted-by/acceptance-basis refs;
- route-neutral plan contract base;
- full `PlanGraphManifestV1`;
- exact WorkPackage contract material keyed by manifest `package_key`.

Reserved contract rule:

- callers may not pre-populate the reserved `plan_graph` field in the plan contract base;
- service constructs the accepted plan contract by adding exactly:

```json
"plan_graph": {
  "schema_version": "plan_graph_manifest.v1",
  "manifest_hash": "<64 hex>"
}
```

This prevents caller/manifest disagreement while avoiding circular identity.

One transaction must:

1. verify schema target/version and inactive internal gate;
2. resolve exact Company/Mission and acceptance authority;
3. re-resolve active ProjectScope generation;
4. check expected current plan and version counters;
5. normalize controller request and detect replay/hash conflict;
6. validate/canonicalize graph;
7. compute manifest hash;
8. construct accepted plan contract with graph version/hash;
9. derive/verify immutable PlanRevision identity using existing Company Kernel identity helpers;
10. insert/verify exact PlanRevision replay;
11. derive/insert/verify all WorkPackages;
12. derive/insert/verify normalized dependency rows;
13. insert exact manifest row;
14. reconstruct route-neutral manifest from normalized rows and require hash equality;
15. CAS Mission `current_plan_revision_id`, `plan_state_version`, `kernel_state_version`;
16. commit.

No Task/backend/provider launch occurs inside this transaction.

Crash/replay tests must cover all Iteration-5 windows:

- before transaction;
- validation rejection;
- partial package insert rollback;
- partial edge insert rollback;
- reconstruction/hash mismatch rollback;
- current-plan CAS race rollback;
- commit succeeds/response lost exact replay;
- same request ID/different graph conflict;
- reordered identical graph convergence;
- ProjectScope generation change before commit rejection;
- ProjectScope change after commit leaves immutable historical graph intact.

Endpoint: internal graph acceptance transaction proven on disposable stores; Company Kernel remains publicly inactive; STOP.

## G1.4 - Gate 1 acceptance

Run:

- all Company Kernel model/schema tests;
- graph contract tests;
- graph service transaction/crash tests;
- Task/ProjectScope regression suites affected by shared schema/transactions;
- SQLite `integrity_check` / `foreign_key_check` in tests;
- Ruff/check and EOL diagnostics for touched existing files.

Create:

```text
docs/agent-worker-research/G1_GRAPH_CONTRACT_ACCEPTANCE_<date>.md
```

Hard endpoint:

- no public Company Kernel action;
- no Task launched;
- no reasoning backend;
- no provider;
- no scheduler;
- no service restart;
- no commit until explicitly authorized stage.

STOP.

---

# 8. G2 - Provider-neutral reasoning backend with deterministic fake backend

Implementation Gate 2 proves that strong reasoning can exist beneath canonical Task without introducing a second lifecycle authority.

No real OpenAI/Codex/Claude provider is used in G2.

## G2.1 - EvidenceSubmission and reasoning-spec contracts

Create:

```text
soma/worker_evidence/__init__.py
soma/worker_evidence/models.py
soma/reasoning/__init__.py
soma/reasoning/models.py
tests/test_worker_evidence_contract.py
tests/test_reasoning_contract.py
```

Implement `EvidenceSubmissionV1` with frozen bounds:

```text
schema_version = evidence_submission.v1
normal target = 12 KiB
hard ceiling = 32 KiB
max executive summary = 1024 UTF-8 bytes
max claims = 12
max evidence records = 24
max artifacts = 12
max uncertainties = 12
max blockers = 8
max excerpt = 512 chars/evidence record
max provenance refs = 64
```

Evidence claims must distinguish:

```text
observation
inference
recommendation
negative_finding
```

Evidence bodies/logs/transcripts remain references.

Implement `ReasoningSpecV1` exactly from Iteration 5:

- assignment ref/hash;
- context refs/hashes <=64;
- dependency-proof refs/hashes <=64;
- output contract ref/hash;
- tool policy ref/hash;
- authority ref/hash;
- provider route ref/hash;
- bounded wall time/output bytes/tokens/cost/internal concurrency;
- continuation policy;
- mutation policy = `read_only | protected_broker_only`.

Route/provider identity belongs in ReasoningSpec/backend binding, not WorkPackage identity.

Endpoint: pure bounded models only; STOP.

## G2.2 - Durable reasoning backend store and protocol

Create:

```text
soma/reasoning/schema.py
soma/reasoning/store.py
soma/reasoning/backends.py
soma/reasoning/fake.py
tests/test_reasoning_backend_store.py
tests/test_fake_reasoning_backend.py
```

Use a separate additive schema component:

```text
component = reasoning_backend
version = 1
```

The reasoning backend store is subordinate execution evidence, not canonical Task state.

Persist at minimum:

### `reasoning_backend_runs`

- Soma-owned `backend_ref` primary identity;
- exact ReasoningSpec ref/hash;
- provider route ref/hash;
- start-delivery disposition;
- provider binding disposition;
- provider operation ref if known;
- raw provider status claim;
- output contract disposition;
- result/evidence refs+hashes;
- cancellation/evidence fields;
- created/updated timestamps.

### `reasoning_backend_start_attempts`

- one bounded start-attempt identity;
- backend_ref;
- exact start request hash;
- claim/disposition;
- provider operation ref if captured;
- outcome_unknown evidence;
- timestamps.

Start dispositions exactly:

```text
not_attempted
claimed_not_sent
accepted_bound
rejected
outcome_unknown
```

Provider binding dispositions:

```text
unbound
bound
uncertain
```

Implement provider-neutral protocol mirroring Task backend shape:

```text
reserve()
start(spec, backend_ref)
query(backend_ref)
cancel(backend_ref)
result_reference(backend_ref)
```

Observation shape must not use TaskState as provider truth.

Create a deterministic fake backend supporting scripted cases:

- success;
- provider rejection;
- long-running/cancellable;
- malformed output;
- result publication;
- crash before send;
- ambiguous create acknowledgement -> `outcome_unknown`;
- restart/query recovery by backend_ref.

Hard rule: outcome_unknown never automatically creates a second provider start.

Endpoint: fake reasoning backend semantics proven without Task integration; STOP.

## G2.3 - Task backend registry and reasoning Task integration

Modify carefully:

```text
soma/tasks/models.py
soma/tasks/backends.py
soma/tasks/manager.py
soma/tasks/projections.py
relevant Task schema/tests only if required
```

Add provider-neutral canonical values:

```text
TaskKind.REASONING = "reasoning"
BackendKind.SOMA_REASONING = "soma_reasoning"
```

Do not add provider names to TaskKind/BackendKind.

Refactor TaskManager from one implicit backend property to an explicit backend registry keyed by persisted BackendKind while preserving the durable-run default path exactly.

Required registry behavior:

- active Task never changes backend kind;
- durable command requests continue resolving to DurableRunBackend;
- reasoning requests resolve only to configured reasoning backend;
- missing/unknown backend becomes recovery/uncertain, never fallback to another engine.

Add an INTERNAL manager operation such as:

```text
start_reasoning_task(...)
```

No public MCP gateway change in G2.3.

Reasoning Task normalized request must bind:

- ReasoningSpec ref/hash;
- ProjectScope project/resource/generation;
- WorkPackageAttempt/dependency proof refs when supplied;
- selected backend kind;
- no provider-local operation ID.

Reserve order:

```text
backend_ref first
-> Task + ProjectScope reservation in shared transaction
-> durable reasoning start-attempt claim
-> fake backend start
```

Reconciliation uses `ReasoningBackendObservationV1` as evidence and projects canonical Task state.

Tests must prove:

- durable command legacy hashes/behavior unchanged;
- reasoning Task idempotency/replay;
- reasoning backend_ref uniquely owned by one Task;
- backend start response loss recovers without duplicate start;
- ambiguous provider create leaves Task recovery_pending/uncertain according to exact policy and does not auto-resubmit;
- cancellation delegates to reasoning backend;
- malformed/missing evidence never produces completed success;
- valid EvidenceSubmission publication produces bounded result/evidence references, not transcript bodies.

Endpoint: fake reasoning Tasks work internally; no public provider/model; STOP.

## G2.4 - Gate 2 recovery matrix and acceptance

Fault-inject at least:

- crash after backend_ref reserve / before Task commit;
- crash after Task commit / before backend start claim;
- crash after start claim / before fake provider acknowledgement;
- accepted provider binding / response lost;
- backend process restart;
- cancellation during running;
- invalid result contract;
- duplicate controller request;
- conflicting duplicate request;
- ambiguous create acknowledgement.

Create:

```text
docs/agent-worker-research/G2_REASONING_BACKEND_ACCEPTANCE_<date>.md
```

Hard endpoint: deterministic fake reasoning backend only; STOP.

---

# 9. G3 - Dependency admission, bounded fan-out/fan-in, restart/replay

G3 turns immutable graph facts into bounded canonical Task admissions while keeping semantic planning and acceptance outside Soma.

## G3.1 - Dependency-proof persistence schema

Add Company Kernel migration 3 only after G1/G2 are accepted.

Create immutable table:

### `dependency_satisfaction_proofs`

Columns include:

```text
proof_id PRIMARY KEY
proof_hash UNIQUE
edge_id
edge_hash
requirement
upstream_work_package_id
upstream_outcome_id
downstream_work_package_id
satisfaction_json
observed_kernel_state_version
observed_at
created_at
```

Stable proof hash excludes observed timestamp/version but stored record preserves them.

FK proof edge/package identity exactly.

No mutable `ready` table and no WorkPackage lifecycle state column.

Endpoint: schema/storage only; STOP.

## G3.2 - Mechanical dependency evaluator

Create:

```text
soma/company_kernel/dependencies.py
tests/test_company_kernel_dependency_evaluator.py
```

For one current PlanRevision, evaluator may only determine mechanically:

```text
accepted_outcome
published_success
evidence_available
settled
```

It must never infer semantic evidence adequacy.

Exact predicates:

- `accepted_outcome`: exact AcceptanceCommit matches upstream outcome;
- `published_success`: exact WorkPackageAttempt -> Task -> Run publication identity and successful public result evidence;
- `evidence_available`: exact selector ref/hash resolves to exact evidence ref/hash;
- `settled`: exact known upstream attempt set is terminal/cancelled/contained/uncertain-contained and produces a deterministic `attempt_set_hash`.

A proof is created only inside downstream admission transaction after rechecking current PlanRevision + ProjectScope.

Endpoint: evaluator/proof construction only; no scheduler loop; STOP.

## G3.3 - Bounded admission coordinator

Create:

```text
soma/company_kernel/coordinator.py
tests/test_company_kernel_admission.py
```

Coordinator is deterministic mechanics, not a semantic planner.

Provide one bounded operation conceptually:

```text
admit_ready_work(
  mission_id,
  expected_plan_revision_id,
  expected_plan_state_version,
  max_new_attempts,
  canonical_concurrency_limit,
  controller_request_id
)
```

V1 bounds:

- plan graph max 32 packages;
- canonical concurrency accepted values for benchmark path: 1, 2, 4, 8;
- no hidden infinite polling loop;
- one call admits at most a caller-specified bounded number <=32;
- deterministic package ordering (package_key) for equivalent readiness.

Within one `BEGIN IMMEDIATE` admission transaction for each admitted package:

1. re-read current Mission/PlanRevision/version;
2. verify package belongs to current plan;
3. verify no active single_active attempt exists;
4. evaluate all dependency edges;
5. persist exact dependency satisfaction proofs;
6. construct route request/assignment identity including sorted proof refs/hashes;
7. reserve WorkPackageAttempt identity;
8. reserve backend_ref;
9. reserve canonical Task + ProjectScope attempt coherently;
10. bind WorkPackageAttempt -> Task;
11. commit admission facts;
12. only after commit may backend start occur.

If backend launch then fails/ambiguously starts, canonical Task/backend recovery owns it; do not roll back the accepted attempt identity.

No acceptance outcome is created by coordinator.

No provider/model selection is inferred; the route descriptor/provider route ref is supplied by Sol/owner-approved plan material.

Tests:

- independent packages admitted up to limit;
- dependency-blocked packages not admitted;
- exact deterministic selection under same state;
- duplicate/replay returns same attempts;
- concurrent admission cannot produce two active attempts for single_active package;
- later upstream successor cannot mutate existing downstream proof set;
- changed proof set produces successor downstream attempt when route-neutral intent unchanged;
- changed route-neutral intent requires new PlanRevision;
- stale plan/version rejects;
- ProjectScope generation drift rejects;
- no hidden scheduler state exists.

Endpoint: bounded fan-out admission works with fake backends; STOP.

## G3.4 - FanInV1

Create:

```text
soma/worker_evidence/fanin.py
tests/test_worker_fanin.py
```

Freeze bounds:

```text
normal target 48 KiB
hard ceiling 64 KiB
max expected units 32
max compact submission summaries 32
max exact-key conflicts 64
max unresolved uncertainty refs 64
```

Fan-in mechanically validates:

- expected unit coverage;
- schema-valid EvidenceSubmissionV1;
- exact submission/evidence hashes;
- assignment-provided fact keys;
- duplicate fact-key values;
- exact structured conflicts;
- missing/partial/uncertain units;
- byte budgets;
- provenance refs.

Fan-in must not:

- semantically decide which contradictory claim is true;
- accept WorkPackage outcomes;
- infer equivalence from embeddings/prose;
- hide missing units.

Output preserves:

```text
truncated
has_more
exact counts
retrieval pointers
conflict refs
uncertainty refs
```

Sol consumes FanInV1 and performs semantic adjudication/synthesis.

Endpoint: deterministic fan-in contract proven; STOP.

## G3.5 - Restart/replay and concurrency mechanics with fake workers

Using fake execution/retrieval/reasoning workers only, exercise:

```text
C1
C2
C4
C8
```

This stage is a scheduler mechanics proof, NOT the frozen provider benchmark.

Test:

- same immutable eight-unit shape or synthetic equivalent;
- only admission concurrency changes;
- process restart during fan-out;
- one unit timeout;
- one unit failure;
- stale dependency-proof reconstruction;
- controller disconnect/reconnect;
- duplicate coordinator request;
- cancellation;
- no duplicate Task/backend starts;
- fan-in exact missing-unit reporting.

Endpoint: mechanical fan-out/fan-in survives restart with fake workers; STOP.

## G3.6 - Gate 3 acceptance

Create:

```text
docs/agent-worker-research/G3_DAG_ADMISSION_FANIN_ACCEPTANCE_<date>.md
```

Run all affected Company Kernel/Task/ProjectScope/reasoning/evidence tests and full regression suite.

Hard endpoint: still no real reasoning provider and no protected mutation broker use; STOP.

---

# 10. G4 - Protected mutation broker

No real provider mutation may be authorized until this gate is accepted.

## G4.1 - Protected mutation contracts

Create:

```text
soma/protected_tools/__init__.py
soma/protected_tools/models.py
tests/test_protected_tool_contracts.py
```

Implement `ProtectedToolCallV1` and `ProtectedToolEffectV1` from Iteration 5.

Protected call authority material:

```text
call_request_id
task_id
attempt_id
backend_ref
mandate_ref/hash/version
project_id
resource_id
scope_generation
capability_ref/hash
tool_operation_ref/hash
resource_key
Soma-issued/validated idempotency_key
payload_ref/hash
expected_task_state_version
expires_at
mutation_class
provider_provenance_refs[]  # evidence only
```

Provider-local IDs MUST NOT enter the canonical request/effect hash.

Mutation classes:

```text
repository
external_system
deployment
communication
financial
generic
```

Effect dispositions:

```text
prevented
rejected
acknowledged
outcome_unknown
```

Endpoint: pure contracts; STOP.

## G4.2 - Durable broker store / idempotency

Create:

```text
soma/protected_tools/schema.py
soma/protected_tools/store.py
tests/test_protected_tool_store.py
```

Separate additive schema component.

Persist request identity before invoking protected effect.

Rules:

- same idempotency key + same exact authority/effect payload -> replay same canonical request/effect;
- same key + different payload/tool/resource/authority -> hard conflict;
- provider provenance may append evidence correlation but never changes request identity;
- ambiguous external outcome -> `outcome_unknown`, automatic resend forbidden;
- cancellation after effect begins does not fabricate reversal.

Endpoint: storage/idempotency only; STOP.

## G4.3 - Mechanical broker validation

Create:

```text
soma/protected_tools/broker.py
tests/test_protected_tool_broker.py
```

Before executing any protected operation, revalidate in one bounded path:

1. Task ID/state/version/currentness;
2. WorkPackageAttempt exact binding/current plan rules;
3. cancellation precedence;
4. mandate ref/hash/version;
5. ProjectScope project/resource/generation;
6. capability ref/hash;
7. exact tool-operation contract hash;
8. resource-key lock/ownership;
9. expiry;
10. payload hash;
11. Soma idempotency identity;
12. required approval/authority evidence where applicable.

First tests use deterministic fake protected tools only.

Mutation broker must not accept natural-language provider confidence as authority.

Endpoint: fake protected effects only; STOP.

## G4.4 - Resource contention / old-plan containment

Prove:

- two read-only reasoning Tasks may coexist;
- two independent resources may mutate concurrently when authority allows;
- same resource protected mutation serializes;
- selecting a new PlanRevision does not automatically cancel an old writer;
- conflicting new writer remains blocked until old writer is terminal or mechanically contained/quiescent;
- old read-only work may finish and publish evidence;
- provider-native child count does not multiply mutation authority;
- outcome_unknown retains resource/effect uncertainty according to real containment policy.

Endpoint: mutation safety proven with fake tools; STOP.

## G4.5 - Gate 4 acceptance

Full affected + full suite.

Create:

```text
docs/agent-worker-research/G4_PROTECTED_MUTATION_BROKER_ACCEPTANCE_<date>.md
```

No real external mutation experiment yet; STOP.

---

# 11. G5 - Real read-only reasoning-provider pilots

G5 is the first stage that may spend provider quota or launch a real reasoning provider.

Every substage requires a fresh explicit owner authorization naming the pilot and cost ceiling.

Before G5, re-check current official provider documentation because OpenAI/Codex/provider capabilities are time-sensitive.

Do not rely on the August 2026 research description if current primary documentation changed.

## G5.0 - Provider pilot preflight

No provider call.

Choose exact:

- provider/backend path;
- model/version;
- credential source;
- cost/token ceiling;
- disposable read-only assignment packet;
- output contract;
- event fields to capture;
- timeout;
- cancellation procedure;
- create-ack ambiguity test design.

Owner must approve exact pilot and spend ceiling.

STOP.

## G5.1 - OAI-R1 single-agent durable Responses pilot

Read-only only.

No Multi-agent.

Measure:

- response ID capture timing;
- exact poll/recovery after client restart;
- cancel convergence/idempotency;
- stream cursor continuation when supported;
- raw statuses/events;
- structured EvidenceSubmission validation;
- usage/cost extraction;
- create-ack uncertainty when no response ID is captured.

Promotion requirement:

- known provider ID recovery works;
- cancellation semantics measured;
- output/evidence publishing deterministic;
- create-ack unknown does not trigger blind duplicate create.

STOP.

## G5.2 - OAI-R2 Responses Multi-agent provenance pilot

Separate from durability experiment.

Read-only tools only.

Use one Soma reasoning Task with bounded 2-3 provider-native subagents.

Measure provider-local:

- agent paths/names;
- collaboration call/output IDs;
- function-call origin;
- message direction;
- event ordering;
- schema/version drift;
- compact provenance references.

Do not mirror provider children into canonical Tasks unless a measured requirement for independent Soma ownership appears.

STOP.

## G5.3 - OAI-A1 Agents SDK provenance/state pilot

Primary evidence must come from locally captured run result/items/raw responses/state.

Tracing remains supplemental.

Measure interruption/resume and exact state persistence without protected mutation.

STOP.

## G5.4 - CDX-R1 Codex App Server provenance pilot

Prefer documented stdio JSON-RPC.

Measure:

- root/child thread identities;
- parent/ancestor lineage;
- source kind;
- process restart reconstruction;
- generated protocol schema freeze/drift detection;
- root/child cancellation containment.

Do not replace existing Codex adapter merely because App Server is richer; promote only if measured benefit/contract quality warrants it.

STOP.

## G5.5 - OAI-R3 combined Multi-agent + durable/background gate

Only after OAI-R1 and OAI-R2 pass.

Until this exact stage passes, combined Multi-agent + background remains UNMEASURED and must not be assumed by production recovery logic.

STOP.

## G5.6 - Select first production-capable reasoning backend

Compare measured provider paths by:

- durable operation identity;
- recovery;
- cancellation;
- structured output;
- provenance;
- protocol drift detection;
- cost;
- latency;
- native subagent support;
- read-only isolation;
- broker compatibility;
- create-ack uncertainty behavior.

Outcome exactly one:

```text
PROMOTE_<BACKEND>
KEEP_FAKE_ONLY_AND_RESEARCH_MORE
```

No architecture winner by provider reputation alone.

STOP.

---

# 12. G6 - Frozen canonical 1/2/4/8 benchmark

Run only after one reasoning backend path is sufficiently durable and read-only.

## G6.1 - Materialize frozen benchmark package

Source commit remains:

```text
b53404fa9600412a4b3dd0fafd664a856096257b
```

Corpus hash remains:

```text
a5feb6f20076bf17e64b51b66b65186b4b132417edeede83b7717472ac1df998
```

The benchmark runner must read exact committed bytes or immutable copied packets with matching per-file hashes, never current worktree content.

Eight units exactly:

```text
B01 canonical Task/backend authority
B02 Company Kernel identity/authority
B03 Hermes headless/concurrency
B04 Workflow vs parallel-run substrates
B05 provider-adapter capability truth
B06 interaction-delivery durability
B07 ProjectScope/mutation containment
B08 Run/publication/recovery truth
```

All assignment packets byte-identical between concurrency conditions.

Provider-native subagents disabled/1.

STOP.

## G6.2 - Screening C1/C2/C4/C8

Run one trial each:

```text
C1 max 1 canonical WorkPackage/Task active
C2 max 2
C4 max 4
C8 max 8
```

All eight units execute under every condition.

Fixed controls:

- same source packet;
- same assignments;
- same provider/backend/model version;
- same reasoning settings;
- same tool policy/read-only authority;
- same budgets;
- same EvidenceSubmission/FanIn contracts;
- same final synthesis instruction/model;
- no internet-source variation;
- no worker conversation-history carryover.

Quality gate:

```text
critical trap failures = 0
schema-valid submission rate = 100%
unsupported assertion rate <= 5%
fact-key recall no more than 2 percentage points below confirmed C1
evidence precision no more than 2 percentage points below confirmed C1
no hidden missing unit
```

No winner from screening alone.

STOP.

## G6.3 - Confirmation

Take C1 plus the two best non-C1 quality-passing candidates.

Run each two more times for three observations/condition.

If only one non-C1 passes, confirm only C1 + that candidate.

Predeclare/randomize condition execution order to reduce provider-load/time confounding.

Winner selection among quality-passing conditions:

1. lower confirmed wall-clock makespan;
2. if <=5% makespan difference, lower cost/tokens;
3. if still tied, lower synthesis input/evidence bytes.

Possible outcome:

```text
CANONICAL_CONCURRENCY = 1 | 2 | 4 | 8
```

No hard-coded preference for 4 or 8.

STOP.

## G6.4 - Separate recovery matrix

After concurrency selection, inject separately:

- controller disconnect/reconnect;
- provider loss;
- one-unit timeout;
- stale dependency-proof recovery;
- one-unit cancellation;
- backend restart;
- fan-in partial/missing evidence.

Do not mix this with throughput benchmark results.

STOP.

---

# 13. G7 - Provider-native subagent benchmark

Only after canonical concurrency has been selected.

This is a different experiment:

```text
1 canonical Soma reasoning Task
vary provider-native subagent topology/concurrency
```

Compare:

- single agent;
- 2 subagents;
- provider-recommended/default topology;
- higher bounded topology only if supported and justified.

Measure:

- answer/evidence quality;
- provenance clarity;
- duplicate work;
- latency;
- token/cost;
- synthesis burden;
- cancellation/recovery;
- whether native children need independent Soma ownership.

Do not change canonical WorkPackage concurrency during this experiment.

STOP.

---

# 14. Public/runtime activation boundary

The implementation gates above should initially remain internal/tested unless an explicit activation stage is approved.

Do not automatically expose Company Kernel graph operations as new MCP tools merely because the internals work.

After G1-G6 acceptance, perform a separate architecture decision:

```text
Should normal ChatGPT see:
- explicit Mission/Plan graph tools,
- one higher-level bounded orchestration action,
- only existing Task surfaces while orchestration remains internal,
- or Plugin/Skill-mediated workflow guidance?
```

This decision must be informed by the completed normal-Chat Tool UX project rather than reopening its architecture implicitly.

Any public gateway change requires:

- explicit operation inventory change;
- public input-schema/descriptor identity review;
- normal-Chat routing/UX tests;
- service activation gate;
- connector Refresh only with owner authorization.

---

# 15. Commit strategy

Prefer one local commit per accepted implementation gate or tightly coherent micro-stage cluster, not one giant agent-system commit.

Suggested checkpoints:

```text
P0 research baseline
G1 graph contracts/schema/service
G2 reasoning backend + fake integration
G3 admission/fan-in/recovery mechanics
G4 protected mutation broker
G5 provider pilot adapters/evidence only after measured acceptance
G6 benchmark evidence/results
```

No push unless explicitly requested.

Never include concurrent/unrelated owner files in these commits.

---

# 16. Rollback principles

Every gate must preserve a clean rollback path.

- additive schema migrations are never silently removed from a live DB; rollback means disable capability/use, not destructive schema rollback;
- graph facts are immutable historical evidence;
- old PlanRevisions remain queryable;
- provider adapters can be disabled without rewriting Task history;
- fake reasoning backend remains available for deterministic regression tests even after a real backend is added;
- protected broker refusal is safer than bypass;
- uncertain external/provider outcomes remain explicit rather than rewritten as failure/success;
- public activation changes are separate from internal source acceptance.

---

# 17. Definition of done

The agent/worker architecture is complete only when all required gates demonstrate:

1. immutable bounded PlanRevision DAG contract;
2. deterministic graph hash independent of caller ordering;
3. atomic PlanRevision + WorkPackage + dependency creation;
4. exact dependency proof identities frozen at downstream admission;
5. no second work-unit lifecycle state machine;
6. provider-neutral reasoning Task backend with reserve/start/query/cancel/result reference;
7. safe create-ack uncertainty behavior;
8. bounded EvidenceSubmission and deterministic FanIn;
9. bounded restart-safe fan-out/fan-in;
10. provider-neutral protected mutation broker;
11. provider-native provenance remains evidence rather than authority;
12. real reasoning backend selected through measured read-only pilot evidence;
13. canonical 1/2/4/8 concurrency selected through the frozen quality-gated benchmark;
14. provider-native subagent concurrency measured separately;
15. normal-Chat integration chosen only after the existing Tool UX architecture is accounted for;
16. full regression suite passes;
17. no unapproved push/external mutation/provider spend.

Final architecture should remain:

```text
Sol chooses/decomposes/adjudicates
        |
Soma persists exact graph + authority + durable attempts
        |
Tasks own execution lifecycle
        |
provider-neutral workers/backends
        |
bounded evidence
        |
Soma deterministic fan-in
        |
Sol synthesis/acceptance
```

---

# 18. Promotion ladder / hard stop

```text
Current normal-Chat UX work not complete
    -> HOLD

UX work complete + owner opens worker lane
    -> P0

G1 graph contracts fail
    -> STOP / repair G1

G1 passes
    -> G2 fake reasoning backend

G2 fails recovery/idempotency
    -> STOP; no provider pilot

G2 passes
    -> G3 deterministic DAG admission/fan-in

G3 fails restart/replay
    -> STOP; no provider pilot

G3 passes
    -> G4 protected mutation broker

G4 fails authority/idempotency
    -> STOP; no provider mutation

G4 passes
    -> G5 read-only provider pilots with explicit spend approval

No provider path meets durability/evidence gate
    -> keep fake/internal architecture and research provider boundary

One provider path passes
    -> G6 canonical 1/2/4/8 benchmark

G6 selects concurrency
    -> G7 separate provider-native subagent benchmark

Only after all required evidence
    -> decide public/normal-Chat activation surface
```

No stage automatically starts the next stage.

---

# 19. Research references

Canonical research inputs:

```text
docs/agent-worker-research/iteration-01-current-capability-and-architecture-baseline-2026-08-12.md
docs/agent-worker-research/iteration-02-worker-contract-dag-and-evidence-baseline-2026-08-12.md
docs/agent-worker-research/iteration-03-identity-revision-attempt-and-fanin-contract-2026-08-12.md
docs/agent-worker-research/iteration-04-dag-replanning-and-reasoning-backend-contract-2026-08-12.md
docs/agent-worker-research/iteration-05-frozen-graph-reasoning-broker-and-benchmark-contracts-2026-08-12.md
```

Iteration 5 SHA-256:

```text
dc9afbfd94525890922225839488cc7b25e9798d0c61271d4bf3f0ea97d19cdb
```

Frozen benchmark corpus:

```text
source commit:
b53404fa9600412a4b3dd0fafd664a856096257b

corpus hash:
a5feb6f20076bf17e64b51b66b65186b4b132417edeede83b7717472ac1df998
```

This plan intentionally preserves those research identities while requiring a post-UX drift audit before production implementation begins.
