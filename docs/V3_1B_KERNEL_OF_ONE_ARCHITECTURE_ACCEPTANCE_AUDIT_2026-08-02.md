# V3-1B — Kernel of One Architecture Acceptance Audit

**Date:** 2026-08-02
**Gate:** [`V3_1B_KERNEL_OF_ONE_ARCHITECTURE_GATE_2026-08-02.md`](V3_1B_KERNEL_OF_ONE_ARCHITECTURE_GATE_2026-08-02.md)
**Proposal:** [`V3_1B_KERNEL_OF_ONE_ARCHITECTURE_PROPOSAL_2026-08-02.md`](V3_1B_KERNEL_OF_ONE_ARCHITECTURE_PROPOSAL_2026-08-02.md)
**Verdict:** accepted after one material architecture correction and repeated adversarial audit
**Implementation effect:** closes the documentation-only architecture gate and permits only the separately bounded schema/models implementation gate
**Runtime effect:** none; no provider, gateway, scheduler, company action, external mutation, restart, refresh, deployment, or production activation is authorised
**Push:** not authorised and not performed

## 1. Audit basis

The audit was performed from repository evidence rather than the handover alone. The reviewed authority set included:

- `PLANS.md`;
- the V3-1B architecture gate and proposal;
- the accepted V3-1A completion record;
- the reliability incident ledger;
- the V3 autonomous-company roadmap and reconciliation;
- the owner-accepted hierarchical-intelligence organisational contract;
- live ProjectScope, Task, Run, workflow and supervisor compatibility evidence named by the proposal;
- copied-live SQLite execution of SQL extracted directly from the proposal.

Preflight before editing observed branch `lane/memory-integration-foundation-1` at `61162fadde65895f780deaf51039c12639834e56`, a clean tracked worktree, no active or queued Soma runs, and no repository locks. The audit did not restart or refresh Soma, change shared configuration, launch a provider, mutate the live database directly, or push.

## 2. Prior adversarial evidence independently considered

The proposal already preserved these preparatory runs:

- `20260802T210313Z_executable_profile_627dc9b7` — initial proposal SQL applied to a copied live database and passed foreign-key checking;
- `20260802T210346Z_executable_profile_a50e7121` — the diagnostic harness supplied 18 values to a 17-column table; no schema conclusion was valid;
- `20260802T210419Z_executable_profile_0415a02c` — exposed cross-Mission and cross-Company relationship defects in the initial proposal;
- `20260802T210938Z_executable_profile_bcaf527a` — hardened nine-block schema passed copied-live integrity and rejected the documented cross-scope, cross-outcome, mutation and acceptance mismatches;
- `20260802T205709Z_executable_profile_445b7e9d` — compatibility census found 12 workflows, 21 supervisors, 12 canonical Tasks, 7,058 durable Runs and eight exact ProjectScope records, with no active planning or implementing supervisor requiring conversion.

Those runs were treated as evidence, not as a substitute for the independent audit below.

## 3. Independent audit sequence

### 3.1 Clean repository and execution probe

Run `20260802T212932Z_executable_profile_c0979ae7` confirmed the exact repository HEAD before audit work.

### 3.2 Failed diagnostic with no architecture conclusion

Run `20260802T213015Z_executable_profile_26a12502` failed because the independent harness assumed `projects.lifecycle` instead of the actual `projects.lifecycle_state` column. Exception cleanup then retained the copied SQLite handle long enough to produce a Windows file-in-use error. The run did not reach the authority test, changed no tracked file, and supports no schema conclusion.

Run `20260802T213026Z_executable_profile_578227b1` then introspected the live read-only schema and established the correct column names before the diagnostic was rewritten.

### 3.3 Material defect reproduced

Run `20260802T213048Z_executable_profile_4eeb8543` extracted all nine SQL blocks from the proposal, applied them to a copied live database, and obtained:

- `integrity_check: ok`;
- empty foreign-key check;
- no direct live-database mutation;
- successful insertion of a Company with executive `authority:executive:A` and a Mission whose accountable owner and acceptance authority were unrelated references.

This was a material architecture defect. The proposal compared later plan, package and acceptance references to the Mission, but the Mission itself was not transactionally bounded to the Company executive. A free-form Mission reference could therefore manufacture authority contrary to the architecture gate and organisational contract.

### 3.4 Correction

The proposal was corrected before acceptance:

1. the first Company executive is resolved from trusted owner-controller bootstrap configuration; a request may assert the expected reference but cannot create it;
2. `companies` exposes a composite unique Company/executive key;
3. Mission accountable-owner and acceptance-authority references both have composite foreign keys to that immutable Company executive;
4. PlanRevision `accepted_by_ref` has a composite foreign key to the Mission acceptance authority;
5. WorkPackage owner and acceptance references have a composite foreign key to the Mission authority pair;
6. AcceptanceCommit authority participates in its composite WorkPackage foreign key;
7. bootstrap, public-contract, validation and acceptance text now forbid caller-created root authority, delegation, substitution or transfer in V3-1B.

The correction deliberately does not add Role, Assignment, delegation, capability or ownership-transfer product state. Those remain later concerns.

### 3.5 Repeated copied-live adversarial proof

Run `20260802T213318Z_executable_profile_a81607d5` repeated the copied-live proof against the corrected proposal. It applied all nine SQL blocks and reported:

- `integrity_check: ok`;
- empty foreign-key check;
- mismatched Mission authority rejected;
- mismatched PlanRevision authority rejected;
- mismatched WorkPackage authority rejected;
- valid single-executive Company → Mission → PlanRevision → WorkPackage chain allowed;
- Mission, plan and AcceptanceCommit authority foreign-key chains present.

### 3.6 Final mechanical authority audit

Run `20260802T213429Z_executable_profile_9c35d4b0` mechanically inspected the corrected proposal and passed every check:

- all seven company-domain tables present;
- no WorkPackage or WorkPackageAttempt status, state, PID, process, lease, lock, result, publication or worker authority column;
- one current-plan pointer and compare-and-set protocol present;
- unique one-winner AcceptanceCommit by `outcome_id` present;
- fixed `single_active` topology and one-successor index present;
- provider, model, executable profile, argv, environment, session, Task ID and Run ID excluded from outcome identity;
- root authority configuration anchoring and all downstream authority foreign keys present;
- owner waiting reuses the same V3-1A Task, Run and session;
- research and knowledge remain non-authoritative;
- workflow/supervisor retirement condition is named;
- no provider, department or scheduler is required.

## 4. Gate-by-gate findings

### 4.1 All new state is irreducible company-domain state — pass

Company, Mission, immutable accepted PlanRevision, bounded WorkPackage, route-independent outcome identity, immutable WorkPackageAttempt linkage, AcceptanceCommit and bounded reconciliation receipts express company intent, authority and substantive acceptance that do not exist in ProjectScope, Task, Run or ResultPublication.

No proposed table owns execution progress. WorkPackage execution state is a rebuildable projection from immutable kernel facts plus ProjectScope, canonical Task, canonical Run, interaction, containment and publication evidence.

### 4.2 Existing canonical authority remains unchanged — pass

The proposal explicitly leaves these authorities intact:

- ProjectScope: project, repository, resource, Task and Run coherence;
- TaskStore/TaskManager: admission, task state, commands, waiting and checkpoints;
- RunStore/JobManager/workers/process control/locks: execution, cancellation, containment, recovery and evidence;
- WorkerSubstrateStore: provider-session and interaction evidence;
- ResultPublication: exact public Run result identity.

The kernel does not create a package lifecycle, package process, package lock, package result or package publication authority.

### 4.3 One-current PlanRevision is transactionally enforceable — pass

Only `missions.current_plan_revision_id` denotes currency. PlanRevision rows are immutable. Selection inserts or verifies the accepted revision and updates the current pointer plus version counters inside one `BEGIN IMMEDIATE` transaction under expected current ID and `plan_state_version`. Failure leaves either the old current revision or exactly the new one; concurrent different selections have one compare-and-set winner.

### 4.4 One-winner AcceptanceCommit is transactionally enforceable — pass

`acceptance_commits.outcome_id` is unique. Eligibility is checked inside one shared transaction against exact ProjectScope generation, current plan, WorkPackage, attempt, Task, Run, published result hash, public source hash, safety state and fixed acceptance authority. Exact replay returns the existing commit; a different attempt, result, authority, basis or request under the same outcome cannot create a second winner.

### 4.5 Route-independent outcome identity is clean — pass

Outcome identity derives from versioned outcome normalization, Mission, accepted PlanRevision, exact bounded outcome contract and exact target ProjectScope resource/generation. It excludes provider, model, executable profile, argv, environment, session, Task ID and Run ID. Route-specific values live only in WorkPackageAttempt and canonical Task requests.

### 4.6 Default route attempts cannot fork — pass

The only v1 topology is `single_active`. Attempt reservation runs under `BEGIN IMMEDIATE`, reads all attempts for the outcome with canonical Task/Run state, refuses another non-terminal route without verified containment, requires any supersession to name the exact latest attempt, and enforces one successor per superseded attempt. Task, ProjectScope attempt binding and WorkPackageAttempt reservation share one transaction.

### 4.7 Supersession requires terminal or mechanical containment evidence — pass

A route may be superseded only when its canonical Task/Run is terminal or existing process, cancellation, operation-lock and containment evidence mechanically proves that the prior route cannot continue mutating. Opaque text or model confidence is explicitly insufficient. Any implementation must preserve this verification boundary rather than merely storing the evidence reference.

### 4.8 Crash windows cannot fabricate execution, publication or acceptance — pass

The crash matrix preserves these linearization points:

- no partial plan currency outside its transaction;
- no attempt row before shared Task/ProjectScope reservation commits;
- a committed Task without a Run follows canonical missing-backend recovery;
- uncertain sends are never blindly retried;
- terminal unpublished Runs remain unpublished;
- published results without AcceptanceCommit become candidates only;
- interrupted acceptance leaves zero or one immutable winner;
- reconciliation replay returns one exact receipt/effect or retries once.

The kernel never launches directly, fabricates a Run, publishes a result or infers acceptance from process success.

### 4.9 Owner waiting reuses V3-1A — pass

`awaiting_controller` remains canonical Task/Run state. The package projection reads it; restart repair uses exact V3-1A checkpoint/session evidence; `task_action(supply_input)` resumes the same Task, Run and session. The kernel stores no duplicate wait state and does not replay worker conversation.

### 4.10 Research and knowledge remain non-authoritative — pass

Research, alternatives, dissent, reviews and knowledge records may be referenced as deliberation, basis or evidence. They cannot select the current plan, admit a Task, publish a Run result or create OutcomeAcceptance. Only the named fixed authority acting through the exact company transaction may create PlanRevision currency or AcceptanceCommit.

### 4.11 Workflow/supervisor compatibility has a canonical side and retirement condition — pass

The named replacement path is PlanRevision/WorkPackage → canonical Task → canonical Run/ResultPublication → AcceptanceCommit. Workflow and supervisor records remain historical generic lifecycle managers and opaque evidence references; they are never backfilled or reused as company authority. Retirement requires measured zero active generic executions and zero start consumers before new generic starts are disabled, while historical query/cancellation/archive access remains.

### 4.12 No provider, department, scheduler or external mutation is required — pass

The first implementation may be proven entirely through additive schema/models and copied-live migration tests. Real Claude Code, Codex or other providers, departments, permanent teams, a worker capability broker, scheduled reconciliation, business-system mutation, deployment and production activation are explicit exclusions.

### 4.13 Authority and capability cannot be minted — pass after correction

The root executive is configuration-anchored rather than caller-created. In v1 that same immutable identity is the Company executive, Mission accountable owner and Mission acceptance authority. Composite foreign keys carry the ceiling into PlanRevision, WorkPackage and AcceptanceCommit. V3-1B exposes no delegation, authority expansion, substitution, transfer or capability-grant operation.

## 5. Compatibility and migration conclusion

The copied-live proofs support an additive `company_kernel` schema migration without backfill. Existing ProjectScope, Task, Run, workflow and supervisor rows remain the canonical historical records. Fresh and copied-live databases must converge through ordered idempotent component migrations with foreign keys enabled. Runtime operations must refuse absent or older schema versions.

The live service remains on its existing build. This audit does not claim source/runtime/connector convergence for V3-1B and does not authorise a restart or connector refresh.

## 6. Recorded diagnostic incidents and ambiguities

The audit preserves these non-product incidents rather than silently discarding them:

- three capability-discovery calls used unsupported operations on `run_start`, `system_query` and `repo_preview`; each was rejected by schema validation before execution or mutation;
- one repository-wide search for an execution-profile name timed out after examining 1,769 files; no conclusion was drawn and the actual `run_start` contract was used directly;
- run `20260802T213015Z_executable_profile_26a12502` used the wrong ProjectScope column and leaked the copied SQLite handle during exception cleanup; no architecture conclusion was drawn;
- the canonical memory provider was degraded to lexical fallback during the audit, so repository files and exact live schema evidence remained the primary authority.

These observations do not indicate a Soma product failure. The genuine proposal defect was the authority-ceiling gap reproduced by run `20260802T213048Z_executable_profile_4eeb8543` and corrected before acceptance.

## 7. Acceptance decision

The corrected proposal satisfies the architecture gate.

The documentation-only `V3-1B — Kernel of One Architecture Gate` is accepted and closed. The next authorised package is only `V3-1B-SCHEMA-MODELS-1`: additive schema, immutable models, ordered migration registration, fresh/copy-live migration proof and constraint tests. It does not authorise company actions, public gateways, attempt reservation, Task or Run launch, outcome acceptance, providers, scheduling, external mutation, restart, connector refresh, deployment or push.

Any implementation that weakens the fixed executive ceiling, duplicates canonical lifecycle state, adds package execution ownership, accepts an unpublished result, or requires live providers must stop and return to architecture review.
