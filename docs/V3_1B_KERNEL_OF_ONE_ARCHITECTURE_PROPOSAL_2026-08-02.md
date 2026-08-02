# V3-1B — Kernel of One Architecture Proposal

**Date:** 2026-08-02  
**Status:** proposed for independent acceptance audit  
**Gate:** [`V3_1B_KERNEL_OF_ONE_ARCHITECTURE_GATE_2026-08-02.md`](V3_1B_KERNEL_OF_ONE_ARCHITECTURE_GATE_2026-08-02.md)  
**Implementation effect:** none; this document does not authorise product code  
**Push:** not authorised

## 1. Decision summary

V3-1B should add one small company-domain authority around the existing canonical ProjectScope → Task → Run → ResultPublication chain.

The kernel owns only:

- one stable Company reference;
- one Mission bound to one exact active ProjectScope generation;
- immutable accepted PlanRevision records and one current-plan pointer guarded by compare-and-set;
- immutable bounded WorkPackage contracts;
- route-independent outcome identity;
- immutable WorkPackageAttempt links to route-specific canonical Tasks;
- one immutable AcceptanceCommit selecting one exact published result hash;
- one bounded reconciliation receipt per owner-turn or package-completion trigger.

The kernel does **not** own:

- task admission or task lifecycle;
- run execution, process identity, leases, locks, cancellation, containment, or recovery;
- ResultPublication;
- worker interaction delivery;
- provider sessions;
- research truth, knowledge truth, or semantic identity;
- departments, assignments, capability grants, scheduling, deployment, or external mutation.

WorkPackage execution status is always a projection over canonical Task and Run evidence. There is no `work_package_status`, `attempt_status`, package worker lease, package process ID, package result JSON, package publication state, or package lock.

## 2. Repository-grounded authority inventory

### 2.1 ProjectScope — reused unchanged

Repository evidence:

- `projects` owns `project_id`, lifecycle and `scope_generation`;
- `project_resource_bindings` and `project_repository_bindings` own exact resource/repository coherence;
- `project_task_reservations` and `project_run_attempts` bind canonical Task and Run attempts to one project generation;
- `resolve_repository`, `require_task`, `require_task_attempt`, `require_run`, `reserve_task_attempt`, `require_launchable_attempt`, `attach_task`, and `attach_attempt` fail closed on wrong project, resource, generation, lifecycle or backend identity;
- all records share `runs/soma.sqlite3` and support `BEGIN IMMEDIATE` coordination.

Kernel use:

- Mission stores `project_id`, `resource_id`, and `scope_generation` as exact binding identity;
- every kernel mutation re-resolves the active binding inside the same transaction;
- a changed or archived ProjectScope blocks new plan, package, attempt, reconciliation and acceptance transitions;
- the kernel never updates ProjectScope lifecycle or reservations directly except through the existing ProjectScope coordinator during canonical Task admission.

### 2.2 Canonical Task plane — reused unchanged

Repository evidence:

- TaskAdmission is `TaskState.ACCEPTED`, not deliverable acceptance;
- TaskStore owns task identity, state, commands, links, checkpoints and compare-and-set state versions;
- one controller request ID owns at most one Task;
- one backend reference is owned by at most one Task;
- TaskStore exposes a shared main-store transaction and connection-scoped reserve/update/event primitives;
- `TaskState.AWAITING_CONTROLLER`, exact checkpoints and V3-1A interaction commands already provide non-terminal owner decision waiting and resume.

Kernel use:

- every route attempt is one normal canonical Task;
- `work_package_attempts.task_id` is an immutable foreign key/reference, not a copied task row;
- provider/profile/argv/model changes create a new Task request hash and a new WorkPackageAttempt under the same route-independent outcome;
- owner input continues through `task_action(supply_input)` against the exact Task/session/checkpoint;
- the kernel never writes Task state directly.

### 2.3 Durable Run and ResultPublication — reused unchanged

Repository evidence:

- RunStore owns run state, state version, worker lease, process identity, cancellation evidence, repository lock correlation, result JSON and publication metadata;
- only canonical terminal Runs may publish;
- `result_publication_status = 'published'` plus `result_published_hash`, `result_published_at`, and source-bound public projection metadata establish durable publication identity;
- publication is idempotent and repairable without changing the authoritative terminal result.

Kernel use:

- an attempt’s Run is derived from its Task backend reference and ProjectScope attempt binding;
- AcceptanceCommit eligibility requires the exact Run to be terminal and canonically published;
- AcceptanceCommit binds `result_published_hash` and `public_result_source_sha256` as evidence, but substantive acceptance is created only by the named acceptance authority;
- the kernel never publishes, rewrites or repairs Run results.

### 2.4 Worker substrate — referenced, never extended by V3-1B

V3-1A owns provider-session, message, attempt, checkpoint-deadline and expiry evidence. V3-1B uses those only through canonical Task projections. It adds no provider or communication table and launches no real provider.

### 2.5 Research and knowledge — non-authoritative references

The research overlay already preserves candidates, alternatives, supporting/opposing claims, challenged or unresolved claims, decisions, experiments and relationships. Canonical knowledge preserves versioned project records, sources, supersession and review metadata.

Kernel rule:

- a WorkPackage or AcceptanceCommit may store opaque `deliberation_ref`, `evidence_ref`, `acceptance_basis_ref` and their hashes;
- research `DecisionStatus.ACCEPTED`, candidate acceptance, knowledge `status='current'`, model confidence or review state never creates PlanRevision currency, Task admission, ResultPublication or OutcomeAcceptance;
- deleting/rebuilding research or knowledge projections cannot change any kernel record.

### 2.6 Workflows and supervisors — legacy compatibility only

Repository evidence:

- `workflows` owns a second status machine, worker lease, active child, cancellation, result and publication;
- `supervisors` owns another status machine, child routing, approval metadata, cancellation and resume prompts;
- they are generic lifecycle managers, not protected business domains;
- live census on 2026-08-02 found 12 workflows, all `reported`, and 21 supervisors with only `needs_input`, `failed` or `cancelled`; no workflow was active and no supervisor was `planning` or `implementing`.

Kernel rule:

- no V3-1B operation creates, updates or treats a workflow/supervisor record as company authority;
- optional explicit legacy references may appear in read-only projections only;
- no legacy row is backfilled or guessed into a Company, Mission, PlanRevision, WorkPackage, Task attempt or AcceptanceCommit;
- legacy query/cancel surfaces remain available for historical records during the proof;
- retirement condition: once no non-terminal legacy consumer depends on new starts and the company kernel has passed its live proof, new generic workflow/supervisor starts become disabled while query, evidence and bounded cancellation remain for historical rows.

The canonical side of the compatibility bridge is CompanyKernel → canonical Task/Run. The legacy side is informational only.

## 3. Identity and canonicalisation

All canonical JSON uses UTF-8, sorted keys, compact separators and explicit schema/domain versions. Semantic similarity is forbidden for identity, replay or supersession.

### 3.1 Identity domains

```text
soma.company_kernel.company.v1
soma.company_kernel.mission.v1
soma.company_kernel.plan_revision.v1
soma.company_kernel.work_package.v1
soma.company_kernel.outcome.v1
soma.company_kernel.attempt.v1
soma.company_kernel.acceptance.v1
soma.company_kernel.reconciliation.v1
```

### 3.2 Opaque identities

```text
company_<24 lowercase hex>
mission_<24 lowercase hex>
planrev_<24 lowercase hex>
workpkg_<24 lowercase hex>
outcome_<24 lowercase hex>
wpattempt_<24 lowercase hex>
accept_<24 lowercase hex>
kreconcile_<24 lowercase hex>
```

IDs are derived from exact domain-separated identity fields and hashes. They are not inferred from names or natural language.

### 3.3 Route-independent outcome identity

`outcome_id` is derived from:

- `mission_id`;
- accepted `plan_revision_id`;
- versioned WorkPackage intent/contract hash;
- exact ProjectScope `resource_id` and `scope_generation`;
- explicit `package_key`.

It excludes:

- provider;
- model;
- executable profile;
- argv;
- environment;
- session;
- Task ID;
- Run ID.

Those route-specific facts belong to WorkPackageAttempt and canonical Task/Run evidence.

## 4. Additive schema v1

Component: `company_kernel`  
Database: existing `runs/soma.sqlite3`  
Migration: additive through `soma_schema_migrations`; no existing table rewrite, drop or backfill.

### 4.1 `companies`

```sql
CREATE TABLE companies (
    company_id TEXT PRIMARY KEY,
    company_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    executive_authority_ref TEXT NOT NULL,
    creation_request_id TEXT NOT NULL UNIQUE,
    creation_request_hash TEXT NOT NULL CHECK(length(creation_request_hash) = 64),
    created_at TEXT NOT NULL
)
```

First proof rule: exactly one explicitly addressed Company is used. The schema does not assume a global singleton so tests and future projects remain isolated.

### 4.2 `missions`

```sql
CREATE TABLE missions (
    mission_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    mission_key TEXT NOT NULL,
    project_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    scope_generation INTEGER NOT NULL CHECK(scope_generation >= 1),
    mission_contract_json TEXT NOT NULL,
    mission_contract_hash TEXT NOT NULL CHECK(length(mission_contract_hash) = 64),
    accountable_owner_ref TEXT NOT NULL,
    acceptance_authority_ref TEXT NOT NULL,
    current_plan_revision_id TEXT,
    plan_state_version INTEGER NOT NULL DEFAULT 0,
    kernel_state_version INTEGER NOT NULL DEFAULT 0,
    creation_request_id TEXT NOT NULL UNIQUE,
    creation_request_hash TEXT NOT NULL CHECK(length(creation_request_hash) = 64),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(company_id, mission_key),
    UNIQUE(mission_id, company_id),
    UNIQUE(mission_id, project_id, resource_id, scope_generation),
    FOREIGN KEY(company_id) REFERENCES companies(company_id),
    FOREIGN KEY(project_id, resource_id)
        REFERENCES project_resource_bindings(project_id, resource_id),
    FOREIGN KEY(mission_id, current_plan_revision_id)
        REFERENCES plan_revisions(mission_id, plan_revision_id)
        DEFERRABLE INITIALLY DEFERRED
)
```

The first proof has one fixed executive/accountable owner. Dynamic Role, Assignment and ownership-transfer tables remain deferred. A different executive identity requires a later explicit authority package, not an update hidden inside V3-1B.

Mission operational health is projected from its active ProjectScope and current plan. V3-1B stores no process-like Mission status.

### 4.3 `plan_revisions`

Only accepted PlanRevisions enter this table. Drafts, alternatives and dissent remain research/knowledge references until accepted.

```sql
CREATE TABLE plan_revisions (
    plan_revision_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    revision_number INTEGER NOT NULL CHECK(revision_number >= 1),
    parent_plan_revision_id TEXT,
    plan_contract_json TEXT NOT NULL,
    plan_content_hash TEXT NOT NULL CHECK(length(plan_content_hash) = 64),
    deliberation_ref TEXT NOT NULL DEFAULT '',
    deliberation_hash TEXT NOT NULL DEFAULT '',
    accepted_by_ref TEXT NOT NULL,
    acceptance_basis_ref TEXT NOT NULL DEFAULT '',
    controller_request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
    accepted_at TEXT NOT NULL,
    UNIQUE(mission_id, plan_revision_id),
    UNIQUE(mission_id, revision_number),
    UNIQUE(mission_id, plan_content_hash),
    UNIQUE(mission_id, controller_request_id),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id),
    FOREIGN KEY(mission_id, parent_plan_revision_id)
        REFERENCES plan_revisions(mission_id, plan_revision_id)
)
```

Rows are immutable. Current-plan selection lives only in `missions.current_plan_revision_id` and is changed by one compare-and-set transaction.

### 4.4 `work_packages`

```sql
CREATE TABLE work_packages (
    work_package_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    plan_revision_id TEXT NOT NULL,
    package_key TEXT NOT NULL,
    outcome_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    target_resource_id TEXT NOT NULL,
    scope_generation INTEGER NOT NULL CHECK(scope_generation >= 1),
    contract_version TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    contract_hash TEXT NOT NULL CHECK(length(contract_hash) = 64),
    topology TEXT NOT NULL DEFAULT 'single_active'
        CHECK(topology IN ('single_active')),
    accountable_owner_ref TEXT NOT NULL,
    acceptance_authority_ref TEXT NOT NULL,
    deliberation_ref TEXT NOT NULL DEFAULT '',
    evidence_requirements_ref TEXT NOT NULL DEFAULT '',
    controller_request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
    created_at TEXT NOT NULL,
    UNIQUE(work_package_id, outcome_id),
    UNIQUE(work_package_id, mission_id, outcome_id),
    UNIQUE(mission_id, plan_revision_id, package_key),
    UNIQUE(mission_id, controller_request_id),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id),
    FOREIGN KEY(mission_id, plan_revision_id)
        REFERENCES plan_revisions(mission_id, plan_revision_id),
    FOREIGN KEY(mission_id, project_id, target_resource_id, scope_generation)
        REFERENCES missions(mission_id, project_id, resource_id, scope_generation),
    FOREIGN KEY(project_id, target_resource_id)
        REFERENCES project_resource_bindings(project_id, resource_id)
)
```

The contract is bounded and route-neutral. It includes purpose, expected outcome, scope, constraints, permitted/prohibited actions, success evidence, escalation, reporting, accountable owner and acceptance authority. It excludes provider/profile/argv/session/process details.

There is deliberately no WorkPackage execution status or result field.

### 4.5 `work_package_attempts`

```sql
CREATE TABLE work_package_attempts (
    attempt_id TEXT PRIMARY KEY,
    work_package_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL,
    task_id TEXT NOT NULL UNIQUE,
    route_request_hash TEXT NOT NULL CHECK(length(route_request_hash) = 64),
    route_descriptor_json TEXT NOT NULL,
    supersedes_attempt_id TEXT,
    containment_evidence_ref TEXT NOT NULL DEFAULT '',
    containment_evidence_hash TEXT NOT NULL DEFAULT '',
    controller_request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
    created_at TEXT NOT NULL,
    UNIQUE(attempt_id, work_package_id, outcome_id),
    UNIQUE(attempt_id, work_package_id, outcome_id, task_id),
    UNIQUE(outcome_id, controller_request_id),
    FOREIGN KEY(work_package_id, outcome_id)
        REFERENCES work_packages(work_package_id, outcome_id),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(supersedes_attempt_id, work_package_id, outcome_id)
        REFERENCES work_package_attempts(attempt_id, work_package_id, outcome_id)
)
```

Additional index:

```sql
CREATE UNIQUE INDEX idx_work_package_attempt_single_successor
ON work_package_attempts(supersedes_attempt_id)
WHERE supersedes_attempt_id IS NOT NULL;
```

Attempt rows are immutable links. Their execution state is projected from `tasks`, the Task backend reference, `runs`, ProjectScope attempt binding and ResultPublication.

### 4.6 `acceptance_commits`

```sql
CREATE TABLE acceptance_commits (
    acceptance_commit_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    work_package_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL UNIQUE,
    attempt_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    result_published_hash TEXT NOT NULL
        CHECK(length(result_published_hash) = 64),
    public_result_source_sha256 TEXT NOT NULL
        CHECK(length(public_result_source_sha256) = 64),
    acceptance_authority_ref TEXT NOT NULL,
    acceptance_basis_ref TEXT NOT NULL,
    acceptance_basis_hash TEXT NOT NULL DEFAULT '',
    controller_request_id TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
    accepted_at TEXT NOT NULL,
    FOREIGN KEY(mission_id, company_id)
        REFERENCES missions(mission_id, company_id),
    FOREIGN KEY(work_package_id, mission_id, outcome_id)
        REFERENCES work_packages(work_package_id, mission_id, outcome_id),
    FOREIGN KEY(attempt_id, work_package_id, outcome_id, task_id)
        REFERENCES work_package_attempts(
            attempt_id, work_package_id, outcome_id, task_id
        ),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
)
```

The unique `outcome_id` is the one-winner OutcomeAcceptance authority. Exact replay returns the existing row; any different result, attempt, authority or basis under the same outcome or request identity fails closed.

AcceptanceCommit never updates Task or Run.

### 4.7 `kernel_reconciliation_receipts`

```sql
CREATE TABLE kernel_reconciliation_receipts (
    reconciliation_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    trigger_kind TEXT NOT NULL
        CHECK(trigger_kind IN ('owner_turn', 'package_completion')),
    trigger_ref TEXT NOT NULL,
    observed_kernel_state_version INTEGER NOT NULL,
    selected_transition TEXT NOT NULL CHECK(selected_transition IN (
        'no_op',
        'plan_selected',
        'package_defined',
        'attempt_reserved',
        'acceptance_candidate_ready',
        'outcome_accepted'
    )),
    target_ref TEXT NOT NULL DEFAULT '',
    effect_hash TEXT NOT NULL CHECK(length(effect_hash) = 64),
    created_at TEXT NOT NULL,
    UNIQUE(mission_id, trigger_kind, trigger_ref),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
)
```

This is idempotency/audit evidence, not a scheduler or execution state machine.

### 4.8 Database-enforced immutability

Service-layer field allowlists and compare-and-set checks remain required, but they are not the only protection. The database rejects mutation of immutable company facts even if future code bypasses the intended store API.

```sql
CREATE TRIGGER companies_no_update
BEFORE UPDATE ON companies
BEGIN SELECT RAISE(ABORT, 'companies are immutable'); END;
CREATE TRIGGER companies_no_delete
BEFORE DELETE ON companies
BEGIN SELECT RAISE(ABORT, 'companies are immutable'); END;

CREATE TRIGGER plan_revisions_no_update
BEFORE UPDATE ON plan_revisions
BEGIN SELECT RAISE(ABORT, 'plan revisions are immutable'); END;
CREATE TRIGGER plan_revisions_no_delete
BEFORE DELETE ON plan_revisions
BEGIN SELECT RAISE(ABORT, 'plan revisions are immutable'); END;

CREATE TRIGGER work_packages_no_update
BEFORE UPDATE ON work_packages
BEGIN SELECT RAISE(ABORT, 'work packages are immutable'); END;
CREATE TRIGGER work_packages_no_delete
BEFORE DELETE ON work_packages
BEGIN SELECT RAISE(ABORT, 'work packages are immutable'); END;

CREATE TRIGGER work_package_attempts_no_update
BEFORE UPDATE ON work_package_attempts
BEGIN SELECT RAISE(ABORT, 'work package attempts are immutable'); END;
CREATE TRIGGER work_package_attempts_no_delete
BEFORE DELETE ON work_package_attempts
BEGIN SELECT RAISE(ABORT, 'work package attempts are immutable'); END;

CREATE TRIGGER acceptance_commits_no_update
BEFORE UPDATE ON acceptance_commits
BEGIN SELECT RAISE(ABORT, 'acceptance commits are immutable'); END;
CREATE TRIGGER acceptance_commits_no_delete
BEFORE DELETE ON acceptance_commits
BEGIN SELECT RAISE(ABORT, 'acceptance commits are immutable'); END;

CREATE TRIGGER kernel_reconciliation_receipts_no_update
BEFORE UPDATE ON kernel_reconciliation_receipts
BEGIN SELECT RAISE(ABORT, 'reconciliation receipts are immutable'); END;
CREATE TRIGGER kernel_reconciliation_receipts_no_delete
BEFORE DELETE ON kernel_reconciliation_receipts
BEGIN SELECT RAISE(ABORT, 'reconciliation receipts are immutable'); END;

CREATE TRIGGER missions_immutable_identity
BEFORE UPDATE OF
    company_id, mission_key, project_id, resource_id, scope_generation,
    mission_contract_json, mission_contract_hash,
    accountable_owner_ref, acceptance_authority_ref,
    creation_request_id, creation_request_hash, created_at
ON missions
BEGIN SELECT RAISE(ABORT, 'mission identity and contract are immutable'); END;
CREATE TRIGGER missions_no_delete
BEFORE DELETE ON missions
BEGIN SELECT RAISE(ABORT, 'missions are immutable'); END;
```

The only Mission fields the v1 store may update are `current_plan_revision_id`, `plan_state_version`, `kernel_state_version`, and `updated_at`, under exact compare-and-set. Triggers do not replace dynamic validation of active ProjectScope generation, canonical Task/Run state, process containment, or publication hashes.

## 5. Transaction protocols

Every company-domain write uses `BEGIN IMMEDIATE` on the shared main database. Every request carries exact project, mission, expected version and controller idempotency identity.

### 5.1 Bootstrap Company and Mission

1. Resolve exact active ProjectScope repository binding.
2. Canonicalise Company and Mission requests.
3. Check existing request IDs and hashes.
4. Insert Company if absent.
5. Insert Mission with exact `project_id`, `resource_id`, `scope_generation`, owner and acceptance authority.
6. Commit.

Replay with identical hashes returns existing records. A changed request under the same identity fails. No existing ProjectScope row is altered.

### 5.2 Accept and select PlanRevision

Inputs include `expected_current_plan_revision_id` and `expected_plan_state_version`.

Inside one transaction:

1. re-resolve active ProjectScope and exact generation;
2. read Mission under expected versions;
3. require `accepted_by_ref == mission.acceptance_authority_ref` for the kernel-of-one proof;
4. canonicalise and hash the accepted plan;
5. insert immutable PlanRevision or verify exact replay;
6. update `missions.current_plan_revision_id`, `plan_state_version + 1`, `kernel_state_version + 1` under compare-and-set;
7. commit.

Failure before commit leaves the previous plan current. Failure after commit leaves exactly the new revision current. Concurrent selection has one winner.

### 5.3 Define WorkPackage

Inside one transaction:

1. validate active ProjectScope generation;
2. require the supplied PlanRevision is the Mission’s current revision;
3. require owner and acceptance authority match the Mission;
4. canonicalise the bounded route-neutral contract;
5. derive `outcome_id` without route fields;
6. insert immutable WorkPackage or verify exact replay;
7. increment Mission `kernel_state_version` under compare-and-set;
8. commit.

A replan does not mutate old WorkPackages. Packages under a non-current plan are ineligible for new attempts or acceptance in the first proof.

### 5.4 Reserve one route attempt

Inputs carry exact WorkPackage/outcome identity, expected Mission kernel version, canonical Task request and optional `supersedes_attempt_id`.

Inside one shared transaction:

1. validate active ProjectScope and current PlanRevision;
2. read every existing attempt for the outcome and join canonical Tasks/Runs;
3. under `single_active`, refuse a second non-terminal route unless the prior attempt is terminal or existing canonical process/cancellation/lock evidence proves containment;
4. if superseding, require the exact latest attempt and one-successor uniqueness;
5. canonicalise route-specific Task request; provider/profile/argv changes affect only this route hash;
6. reserve ProjectScope Task/Run attempt through the existing coordinator;
7. reserve canonical Task through TaskStore;
8. attach ProjectScope Task reservation;
9. insert immutable WorkPackageAttempt linked to that Task;
10. increment Mission `kernel_state_version` under compare-and-set;
11. commit.

Existing TaskManager then owns durable Run creation and launch. A crash after Task/attempt reservation but before Run creation follows the already-proven canonical missing-backend recovery path. The kernel does not launch directly or fabricate a Run.

Containment evidence is accepted only after verification against existing canonical process, Run, operation-lock and cancellation evidence. An arbitrary string or model claim is insufficient.

### 5.5 Create AcceptanceCommit

Inputs carry exact outcome, attempt, Task, Run, published hash, source hash, authority, basis and expected Mission kernel version.

Inside one transaction:

1. validate active ProjectScope generation and current PlanRevision;
2. require WorkPackage/outcome/attempt/Task relationships match exactly;
3. require ProjectScope `require_task_attempt` succeeds;
4. require Task is canonical terminal success and its result identity matches the Run;
5. require Run is terminal, not uncertain or safety-failed, with `result_publication_status='published'`;
6. require supplied `result_published_hash` and `public_result_source_sha256` exactly equal durable Run metadata;
7. require named acceptance authority equals WorkPackage and Mission authority;
8. require the acceptance basis reference/hash is present;
9. insert AcceptanceCommit under unique outcome and request identities;
10. increment Mission `kernel_state_version` under compare-and-set;
11. commit.

No automatic acceptance follows from process success, Task `ACCEPTED`, research review, publication or verifier confidence.

### 5.6 `reconcile_one`

`reconcile_one` is an owner/executive-facing bounded coordinator, not a loop or scheduler.

Inputs:

- `mission_id` and exact ProjectScope;
- `trigger_kind`: `owner_turn` or `package_completion`;
- unique `trigger_ref`;
- expected Mission kernel version;
- one explicitly requested transition or observation target.

Rules:

- at most one company-domain transition is selected;
- the trigger receipt and selected transition/effect are committed atomically when they share the database;
- an identical trigger replay returns the existing receipt;
- a different action under the same trigger fails;
- package completion may record `acceptance_candidate_ready` but cannot create AcceptanceCommit without a named authority request;
- owner turn may select one plan, define one package, reserve one attempt, accept one outcome or record a no-op;
- no recursive tick, background schedule, hidden retry or multi-package loop is introduced;
- canonical TaskManager/Run authorities perform any execution effect.

## 6. Derived projections

No canonical WorkPackage execution-state column exists.

A query may derive:

```text
not_started
attempt_admitted
queued
running
awaiting_controller
cancellation_pending
recovery_pending
uncertain
terminal_unpublished
published_awaiting_acceptance
accepted
failed_without_acceptance
superseded_route
scope_invalid
```

Derivation sources:

- immutable Company/Mission/Plan/Package/Attempt/Acceptance records;
- current ProjectScope lifecycle and generation;
- canonical Task state and checkpoint;
- Task backend reference;
- canonical Run state, safety/recovery and publication metadata;
- existing lock/containment evidence.

Deleting any optional projection cache and rebuilding from these records changes no canonical row. The first proof should avoid a materialised cache entirely.

## 7. Owner-decision continuity

When a package’s Task needs owner input:

1. canonical Task enters non-terminal `awaiting_controller` with exact checkpoint/session/deadline;
2. WorkPackage projection reports `awaiting_controller` by reading that Task;
3. restart repair uses V3-1A Task/Run/session evidence;
4. owner response uses exact `task_action(supply_input)`;
5. the same Task/Run/session resumes;
6. WorkPackage, outcome and attempt identities remain unchanged;
7. no worker conversation is replayed by the kernel.

The company kernel stores no duplicate waiting state.

## 8. Crash and replay matrix

| Window | Durable truth after crash | Recovery rule |
|---|---|---|
| Before Company/Mission commit | no kernel record | identical request may retry |
| Company/Mission transaction committed, response lost | exact rows exist | request/hash replay returns same identities |
| PlanRevision inserted before current-plan update | impossible outside one transaction | transaction rollback leaves old current plan |
| Current-plan CAS committed, response lost | one new current pointer | replay returns selected revision |
| WorkPackage insert interrupted | no partial package | identical request retries |
| Attempt reserved before Task reservation | impossible in shared transaction | rollback |
| Task/ProjectScope/attempt committed before Run creation | canonical admitted Task and immutable attempt, no Run | existing missing-backend recovery; no duplicate attempt |
| Run created/launched, response lost | canonical Task/Run own execution | query by exact Task/attempt; no kernel relaunch |
| Route send uncertain | V3-1A attempt evidence | no blind resend |
| Prior route non-terminal, new route requested | prior Task/Run still authoritative | reject unless terminal or verified contained |
| Result terminal before publication | Run terminal, unpublished | existing ResultPublication repair; no acceptance |
| Publication committed before AcceptanceCommit | exact published hash, no outcome winner | surface acceptance candidate; do not rerun or fabricate acceptance |
| Acceptance insert interrupted | transaction rollback or one immutable winner | exact replay; unique outcome prevents second winner |
| Acceptance response lost | one winner exists | request/hash replay returns same commit |
| Owner checkpoint open during restart | canonical Task wait evidence | resume exact Task/session through V3-1A |
| Plan changes while package result is pending | old package references non-current plan | first proof refuses new attempt/acceptance; executive may create a current-plan package explicitly |
| ProjectScope generation changes | stored mission generation becomes stale | every mutation fails; projection reports scope invalid |
| `reconcile_one` response lost | one receipt/effect or none | exact trigger replay returns receipt or retries once |

## 9. Public contract proposal

New owner/executive gateways are strict discriminated unions derived from the same request models used at runtime.

### 9.1 `company_query`

Operations:

- `capabilities`
- `mission_status`
- `current_plan`
- `work_package`
- `outcome_status`
- `acceptance_commit`
- `reconciliation_receipt`

Every scoped query requires exact `company_id`, `mission_id`, `project_id` and `repo_name` as applicable. Compact default budget: 12 KiB. Full maximum: 64 KiB. Contract JSON is omitted from compact projections; hashes and opaque refs remain.

### 9.2 `company_action`

Operations:

- `bootstrap_kernel`
- `accept_plan_revision`
- `define_work_package`
- `reserve_attempt`
- `accept_outcome`
- `reconcile_one`

Every write requires:

- exact ProjectScope;
- controller request/idempotency identity;
- expected Mission/plan/kernel version where applicable;
- named accountable/acceptance authority;
- bounded request and response budgets;
- `extra='forbid'` schema behavior.

No operation accepts raw credentials, provider accounts, arbitrary shell, deployment, external mutation or legacy workflow/supervisor identity as authority.

### 9.3 Capability honesty

Until implementation and activation:

- gateway operations are absent;
- V3-1B capability is `documentation_only` or unavailable;
- real provider and scheduled reconciliation are false;
- no public schema advertises implementation before source and runtime converge.

## 10. Legacy lifecycle convergence plan

### Canonical replacement path

```text
legacy objective / step / supervisor plan
    → immutable PlanRevision / WorkPackage contract
    → route-specific canonical Task
    → canonical Run and ResultPublication
    → AcceptanceCommit
```

### Compatibility bridge

- legacy records may be named by opaque evidence references only;
- legacy result/publication fields never satisfy AcceptanceCommit eligibility;
- legacy child runs may be inspected only through their canonical Run records;
- V3-1B projections do not copy legacy statuses.

### Retirement condition

After the kernel-of-one proof and live activation show that owner/executive work uses company actions plus canonical Tasks/Runs:

1. measure external consumers of workflow/supervisor start operations;
2. require zero active generic workflow/supervisor executions;
3. disable new generic starts;
4. preserve query, evidence, cancellation and archival reads for historical identities;
5. remove compatibility projection only when no retained record or consumer needs it.

This prevents both a disruptive global migration and permanent duplicate lifecycle growth.

## 11. Migration and compatibility strategy

- Add component `company_kernel` v1 through ordered per-version transactions.
- Fresh and copied-live databases must converge identically.
- No current row is backfilled.
- Existing 12 workflows, 21 supervisors, 12 Tasks, 7,058 Runs and ProjectScope records remain byte-for-byte unchanged by migration.
- Foreign keys point only to stable existing identities.
- Every migration may be applied twice idempotently.
- Rollback of a failed migration leaves no company-kernel table partially active.
- Runtime code must refuse operations when schema is absent or below target version.
- Source activation requires a later controlled restart/connector refresh and copied-live rehearsal.

## 12. Validation plan

### 12.1 Schema and compatibility

- fresh database migration;
- copied-live migration twice;
- integrity check and foreign-key check;
- no existing table/row/hash/mtime mutation beyond migration metadata;
- absent-schema and older-schema refusal;
- no backfill from workflows/supervisors.

### 12.2 Identity and scope

- deterministic exact IDs and hashes;
- semantic-similar but byte-different contract remains different;
- wrong project/resource/generation/lifecycle fails;
- cross-project Task/Run/acceptance fails;
- archived ProjectScope blocks mutation.

### 12.3 Plan currency

- first accepted plan;
- concurrent same revision converges;
- concurrent different revisions have one CAS winner;
- stale plan version rejected;
- crash leaves old or new current, never neither/both;
- immutable revision rows cannot update.

### 12.4 WorkPackage and outcomes

- route-neutral outcome stable across provider/profile/argv changes;
- changed outcome contract creates different outcome;
- package under non-current plan cannot launch or accept;
- contract owner/acceptance authority mismatch rejected;
- package has no lifecycle/result columns.

### 12.5 Attempt admission and supersession

- WorkPackageAttempt + ProjectScope + Task reservation atomicity;
- identical replay returns same attempt/task;
- conflicting replay rejected;
- one non-terminal attempt under concurrent callers;
- terminal prior route permits controlled successor;
- non-terminal route requires verified containment;
- one prior attempt cannot fork to two successors;
- crash before Run creation uses existing Task recovery and creates no duplicate attempt;
- no workflow/supervisor row created.

### 12.6 Acceptance

- exact published winner accepted once;
- duplicate exact replay converges;
- different result under same outcome rejected;
- unpublished, wrong hash, mutated source, wrong Task/Run, wrong scope, safety-failed, uncertain or non-current-plan result rejected;
- research/knowledge accepted status cannot create AcceptanceCommit;
- crash after publication does not rerun;
- crash during acceptance leaves zero or one winner;
- Task/Run rows are unchanged by acceptance.

### 12.7 Waiting and reconciliation

- package projection follows canonical `awaiting_controller`;
- restart and supply-input resume same Task/Run/session;
- `reconcile_one` performs at most one transition;
- owner-turn and package-completion trigger replay is idempotent;
- package completion only surfaces candidate, never auto-accepts;
- no scheduler/background loop.

### 12.8 Projection and lifecycle authority

- delete/rebuild projection produces identical output and zero canonical changes;
- machine audit finds no package status, PID, lease, lock, result or publication ownership;
- workflows/supervisors remain untouched and informational;
- existing ProjectScope, Task, Run, publication, interaction, cancellation and full repository suites remain green.

## 13. Initial implementation slicing recommendation

Only after independent architecture acceptance:

1. **Schema and models:** additive tables, hashes, immutable models and copied-live migration proof.
2. **Plan and package authority:** Company/Mission bootstrap, PlanRevision CAS and immutable WorkPackage definition.
3. **Attempt coordinator:** atomic WorkPackageAttempt + ProjectScope + canonical Task admission; no real provider.
4. **Acceptance authority:** exact published-hash eligibility and one-winner AcceptanceCommit.
5. **Projection and `reconcile_one`:** bounded owner/package triggers and no-cache rebuild proof.
6. **Strict public gateways:** schema/runtime/discovery alignment and capability honesty.
7. **Live activation gate:** controlled restart/refresh, disposable kernel-of-one proof and legacy-start retirement measurement.

Each slice must close with focused tests, adjacent authority tests, full regression, evidence documentation, clean worktree, local commit, and canonical knowledge refresh.

## 14. Explicit exclusions

- real Claude Code, Codex or other provider launch;
- provider account/authentication/install/upgrade/purchase;
- worker-facing Soma MCP;
- Role, Agent, Assignment, department or permanent-team tables;
- dynamic capability broker;
- parallel candidate topology;
- scheduled autonomy or background reconciliation;
- external business mutation;
- deployment, production activation, credentials, push or release;
- automatic substantive acceptance;
- migration/backfill of workflow or supervisor rows;
- semantic matching for identity or replay.

## 15. Acceptance recommendation

The proposal should be accepted only if independent audit confirms:

- all new state is irreducible company-domain state;
- ProjectScope/Task/Run/ResultPublication remain canonical and unchanged;
- one-current plan and one-winner acceptance are transactionally enforceable;
- route-independent outcome and route-specific attempt identity are cleanly separated;
- default attempt concurrency cannot fork;
- crash windows cannot fabricate execution or acceptance;
- owner waiting reuses V3-1A exactly;
- legacy lifecycle compatibility has a named canonical side and retirement condition;
- implementation can proceed without real providers, departments or production activation.
