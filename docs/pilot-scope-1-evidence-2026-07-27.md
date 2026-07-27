# PILOT-SCOPE-1 Evidence and Execution Record

**Status:** closed — owner-reviewed outcome: **proceed**.

**Final verdict:** owner review accepts the deterministic backfill/quarantine
manifest and the additive sidecar seam. PILOT-SCOPE-1 is complete. This decision
authorizes planning a smallest production implementation lane only; it does not
authorize production code, live migration, historical assignment, backfill, or
quarantine.

## Purpose

Determine whether immutable project identity and opaque external-session
bindings can be introduced through Soma's current canonical stores and public
projections without breaking existing controller workflows.

The pilot must force one of these outcomes:

- **Proceed:** the smallest project-identity seam is proven across every
  in-scope resource and existing clients remain compatible.
- **Proceed with scope cut:** the canonical task/run seam is proven, but one or
  more optional provider bindings must remain deferred behind a named gate.
- **Switch strategy:** the additive retrofit cannot enforce isolation and a
  bounded store migration or replacement is required.
- **Blocked:** owner mapping, credentials, live external state, or a production
  mutation is required to gather the next evidence.
- **Stop:** the proposed seam would introduce a second authority, silently infer
  ownership, or weaken an existing durability invariant.

## Accepted boundaries

- Project isolation is a correctness invariant, not a permission system.
- Soma owns canonical project identity and scope.
- One authority owns each concern. Events, evidence, and artifacts retain exact
  opaque task or run references and inherit project identity through that
  authority rather than copying mutable project labels.
- No mutable process-global "current project" is permitted.
- Unscoped project-owned work must fail closed.
- Cross-project access requires an explicit typed binding.
- Existing opaque task, run, session, repository, worktree, evidence, and
  artifact identifiers must remain exact.
- This pilot does not authorize production schema, API, configuration, or
  runtime changes.

## Non-goals

- Building the full project or work-graph plane.
- Activating PILOT-MEMORY-1.
- Retrofitting workflows, supervisors, schedules, browsers, containers, or
  every legacy provider during this investigation.
- Backfilling or quarantining live records.
- Treating repository names, paths, controller conversations, or similar
  content as project authority.

## Baseline checkpoint

The checkpoint was taken on branch
`feature/chatgpt-companion-cycle` at
`5e6a40d879f82e35935446d7e9c3894b2028a75b`.

- The tracked worktree was clean.
- Soma reported no running, queued, or launch-pending runs and no repository
  locks.
- `project_id` and `ProjectScope` occur zero times in production Python and
  tests.
- The live `runs/soma.sqlite3` contained 4,672 runs, 25,672 run events, two
  canonical tasks, two task/run links, and no active operation locks.
- The live memory store contained 100 records: 98 under the free-text
  `project_key` `codexbridge` and two under `soma`.
- The active configuration contained nine repository entries with nine distinct
  resolved root identities. It contained no canonical SSH project bindings and
  one legacy nested SSH deployment binding.

Raw SQLite inspection reported `foreign_keys=0` because the evidence connection
was deliberately opened directly in read-only mode. Soma's `RunStore`,
`TaskStore`, `ProjectMemoryStore`, and other owned stores enable
`PRAGMA foreign_keys = ON` on every application connection. The pilot must test
that pragma explicitly on every new store path.

## Current authority and gap map

| Concern | Current authority | Isolation gap |
|---|---|---|
| Tasks | `tasks.task_id` in `soma.sqlite3` | No project identity; parent and polymorphic task links do not prove equal scope. |
| Runs/attempts | `runs.run_id` plus `repo_name` | `repo_name` is not project identity; Hermes and SSH runs often use service or host labels. |
| Repositories | ignored `config.yaml` mapping from `repo_name` to path | No opaque repository ID, project binding, lifecycle, or shared-resource class. |
| Worktrees | resolved Git/config paths | No canonical worktree record or project binding. |
| Locks/processes | repository/host label, run ID, lease and process identity | Durable ownership is strong, but project ownership is absent. |
| Memory | separate SQLite store with mutable `project_key` | General search/recent/latest paths can be global; duplicate detection is global by source or content hash and can merge identical cross-project records. |
| Hermes sessions | exact `(run_id, request_id, session_id)` ownership | Exact session isolation exists, but no project or task binding exists and runs use `repo_name="hermes-service"`. |
| Other external sessions | none | No canonical provider-neutral session-binding store exists. |
| Evidence/artifacts | exact run ID, run directory, manifests, hashes | Safe containment exists, but retrieval by exact run ID does not validate a project scope. |
| Credentials | global configuration sources and provider-specific locks | No canonical project/shared-resource binding. |

The current memory behaviour is the clearest measured correctness defect for
the future retrofit:

- `ProjectMemoryStore.search`, `recent`, and `latest_by_type` permit unscoped
  retrieval.
- `ProjectMemoryRepository.search` explicitly preserves historical global
  search when neither repository nor project is supplied.
- duplicate detection compares `source_kind + source_id` or `content_sha256`
  globally, so two projects with the same filename, source ID, or content can
  collapse into one record.

## Historical backfill measurement

A read-only classifier compared all 4,672 live runs with the current nine
configured repository identities:

| Classification | Runs |
|---|---:|
| Direct current repository match | 1,920 |
| One repository candidate found in structured input | 163 |
| No safe candidate | 2,589 |
| Multiple candidates | 0 |

This is not permission to apply the 2,083 apparent mappings. Historical names
such as `codexbridge`, `tradinglab`, and `Wan2.2`, and host-scoped values such as
`ssh:andia_server`, require an explicit migration map or quarantine decision.
Names and content similarity must not become project authority.

The two current canonical tasks both bind to workspace `repository:soma`, so
their candidate mapping is simple but still must be recorded by an explicit
backfill decision.

## Disposable confusion proof

One in-memory SQLite proof modeled two projects with deliberately identical:

- repository alias `mirror-api`;
- task objective `Fix service/api.py timeout`;
- branch name `feature/fix-timeout`;
- memory source `service/api.py`;
- memory content and content hash.

The proof used:

- canonical `projects`;
- sidecar `project_tasks` and pre-launch `project_attempts`;
- opaque repositories plus project-repository bindings;
- project-owned worktrees;
- provider-neutral external-session bindings;
- project-scoped memory uniqueness;
- task-link scope guards;
- evidence inheriting scope through its exact run reference.

The first execution stopped before inserting fixtures because the disposable
fixture supplied one extra SQL value. One focused correction was made and the
single allowed evidence-fix rerun passed.

Measured results:

- both identical memory records survived under different project IDs;
- project A retrieval returned only project A;
- evidence resolved to project A through its exact run ID;
- a memory insert without `project_id` failed its `NOT NULL` constraint;
- a cross-project task link failed the scope trigger;
- a cross-project backend-run link failed the scope trigger;
- a cross-project external-session binding failed its composite foreign key;
- `PRAGMA foreign_keys` was enabled and `foreign_key_check` returned no
  violations;
- the current project-less `task_action(start)` payload still parsed;
- the same repository alias bound to two projects was detected as ambiguous and
  failed closed rather than choosing one.

This proves the feasibility of an additive identity seam. It does not yet prove
the production store migration, live process/lock/credential behaviour, public
projection budgets, or restart reconciliation.

## Production-shaped real-store checkpoint

The second checkpoint is preserved as
`tests/test_pilot_scope_1.py`. It remains test-only and uses temporary
databases, the real Soma stores, and a Hermes supervisor fake. No live schema,
configuration, record, process, credential, or artifact was changed.

The test sidecar reserves exact task and run IDs before the incumbent
`TaskStore` and `RunStore` insert their authoritative rows. SQLite triggers then
reject a task, task link, run, memory record, or operation lock that lacks the
matching reservation. This avoids adding columns to the current strict task
row model and preserves persist-before-launch ordering.

Five pilot tests passed:

1. **Additive and fail-closed migration.** Reapplying the fixture migration was
   idempotent, the incumbent task schema remained readable, foreign-key checks
   were clean, and unscoped task/run inserts failed.
2. **Real task, run, repository, worktree, process, and lock stores.** Two
   projects used the same repository alias, task objective, filename, and
   branch name but retained distinct opaque repository, worktree, task, run,
   worker-process, and project identities. Cross-project task links failed.
3. **Project-first memory.** Identical source IDs, content, and content hashes
   survived under different projects; retrieval filtered by project before
   matching and deduplication. The incumbent raw memory search still returned
   both projects, confirming that project workers require the scoped adapter.
4. **Evidence, credentials, and projection.** Artifacts inherited project
   identity through the exact run ID; cross-project artifact access failed; a
   credential reference became visible to the second project only after an
   explicit shared-resource binding; additive project fields remained within
   the task response budget.
5. **Hermes binding before execution.** The test reserved the exact Hermes run
   and session binding before the gateway created its durable run. The result
   remained readable through the owning session and project; the other project
   failed its scope check.

Focused validation passed:

- `ruff format --check tests/test_pilot_scope_1.py`;
- `ruff check tests/test_pilot_scope_1.py`;
- 93 focused tests covering the pilot plus the incumbent task, memory, lock,
  Hermes, artifact, and SSH-binding suites.

## Recovery, migration, and public-contract checkpoint

The third checkpoint adds `tests/test_pilot_scope_1_recovery.py` and extends the
test-only sidecar. Ten pilot tests now pass. The added cases establish:

1. **Deterministic reservation recovery.** A reserved attempt without a run
   moves to `recovery_pending` and can be claimed once. A missing canonical task
   and an attached attempt whose run disappeared are quarantined with
   deterministic SHA-256 evidence rather than guessed into a project.
2. **Process, cancellation, and lock continuity.** Restart adoption retained
   the exact project, worker lease, generation, process identity, and incumbent
   operation lock. `cancellation_pending` retained the lock after a dead-owner
   probe; only the lease-owned terminal cancellation released it. The proof did
   not introduce a second lock authority.
3. **Hermes restart continuity.** Closing and recreating the gateway preserved
   the exact Hermes session/run/project binding. The owning project could read
   the completed result and the confusing second project failed closed.
4. **Transactional migration rollback.** A forced failure after the sidecar
   statements rolled back all pilot tables and the migration marker as one
   transaction.
5. **Strict additive MCP evolution.** The live FastMCP schemas for
   `task_query`, `task_action`, and `run_query` remain strict. Incumbent
   project-less task-start and exact-run-status payloads parse unchanged under
   proposed subclasses that add only an optional `project_id`. Required fields
   and `additionalProperties: false` remain unchanged. Owner exact-ID reads
   remain usable, while scoped worker reads validate the exact project first.

Existing direct Claude and Codex access already established transport-level
client neutrality through Soma's live MCP endpoint. This checkpoint deliberately
did not publish the proposed test schema to that endpoint: doing so would have
crossed the pilot boundary into a production contract mutation. The schema
inspection plus incumbent-payload proof is the strongest connector compatibility
evidence available without that mutation.

## Disposable live-store-copy migration

The fixture migration was applied to SQLite backup copies created from both
live stores. A second main-store copy received a forced failing statement to
exercise rollback. The source databases were opened read-only for classification
and copied to a temporary directory; all temporary copies were removed after
the run.

| Check | Main-store copy | Memory-store copy |
|---|---:|---:|
| Backup-copy bytes before migration | 130,179,072 | 282,624 |
| Bytes after migration | 130,277,376 | 294,912 |
| Migration time | 0.0027 s | 0.0022 s |
| Integrity check | `ok` | `ok` |
| Foreign-key violations | 0 | 0 |
| Pilot tables | 9 | 1 |

The main backup's byte size differs from the physical live database because
SQLite backup materializes a consistent view that includes WAL state. The live
main file remained 130,039,808 bytes. SHA-256 hashes of both live files were
identical before and after the experiment:

- `runs/soma.sqlite3`:
  `8bf4452d80a923c7ed15e2c560efcb18ffd5f0724520f460e937c5c90cad49db`;
- `runs/memory/project_memory.sqlite3`:
  `07aedf6db312bb3ba588e117921b4d3f8f06d9123fc1de3809558ef24bba9d4a`.

The forced failure reported
`no such table: pilot_scope_forced_missing_table`. It left zero pilot tables,
zero pilot migration rows, and an `ok` integrity check.

## Deterministic backfill/quarantine manifest

The review artifact is
[`pilot-scope-1-backfill-quarantine-manifest-2026-07-27.json`](pilot-scope-1-backfill-quarantine-manifest-2026-07-27.json).
Its canonical SHA-256, computed with `manifest_sha256` omitted, is
`d3b58d94ed3acac19bfbc1418bf17463fe563ea7122bfc917b1581bc3ad6a917`.

The manifest records counts and sorted opaque-ID hashes rather than applying
assignments:

- 1,920 runs have a direct exact current-repository candidate;
- 163 have one exact candidate in a structured repository field;
- zero have multiple exact candidates;
- 2,589 have no safe candidate and default to quarantine;
- the two canonical tasks have a simple `repository:soma` candidate;
- the 98 `codexbridge` memory records default to quarantine until an explicit
  owner mapping, while the two `soma` records remain candidates only.

Candidate does not mean approved. Repository names, paths, content, host labels,
and controller conversations remain locators, never authority. No live record
was assigned, backfilled, or quarantined.

## Owner review and accepted disposition

Owner review on 2026-07-27 independently verified the manifest's canonical
SHA-256 and arithmetic: all 4,672 runs are accounted for, with 2,083 candidate
records, 2,589 quarantine-default records, and zero multiple-candidate records.
The accepted disposition is:

- the 2,083 run mappings remain **candidate-only** and must not be applied
  automatically;
- the 2,589 runs with no safe candidate default to quarantine;
- the 98 legacy `codexbridge` memory records default to quarantine until an
  explicit owner mapping exists;
- the two `soma` memory records and two canonical tasks remain candidate-only;
- zero ambiguous classifications does not promote repository names, paths, or
  structured content into project authority;
- any later live assignment requires a separate, explicit migration map and
  owner approval in the production implementation lane.

The final pilot outcome is **proceed** with the additive project-identity seam.
The test-only schema proves the architecture and invariants; it is not itself a
production migration or permission to mutate historical state.

### Measured integration requirements

The proof narrows the production work but does not authorize it:

- Task and run IDs must be allocated and scope-reserved before the incumbent
  store insert. A failed attachment needs deterministic reconciliation of the
  reserved sidecar records.
- The separate memory database cannot have a SQLite foreign key to the main
  project registry. The adapter therefore validates the authoritative project
  generation before reserving memory, and startup reconciliation must quarantine
  orphaned or stale-generation reservations.
- Current memory deduplication and global search need a project-first adapter or
  store change. Filtering their current global result afterward is not
  acceptable.
- Hermes currently allocates its run ID inside the gateway. Production
  integration needs a narrow pre-reservation hook or a caller-supplied reserved
  run ID; the test used a fixed generator to prove that seam.
- `operation_locks.repo_name` safely over-serializes two distinct repositories
  that use the same alias. It prevents concurrent mutation, but the canonical
  lock key must eventually be the resource identity while preserving the one
  existing lock authority.
- The production MCP contract must preserve the tested optional-field shape and
  strict schemas. A later implementation batch must repeat the direct Claude and
  Codex live invocation after that production contract changes.

## Working seam under investigation

The leading design is additive and preserves incumbent authorities:

1. `projects` owns immutable `project_id`, lifecycle, and scope generation.
2. `project_tasks` binds each canonical task to exactly one project.
3. `project_attempts` reserves the exact future run ID and its project before
   launch, preserving persist-before-launch without requiring a run row first.
4. opaque repository and worktree registries bind exact resources to projects;
   shared repositories are explicit shared resources.
5. external sessions use one provider-neutral binding keyed by provider kind
   and the exact opaque provider session ID.
6. task/run events, evidence, and artifacts keep only their exact parent
   reference and inherit scope through it.
7. existing controller starts without `project_id` may resolve only through one
   explicit, unique repository binding. Unknown or ambiguous bindings fail
   closed. New worker-facing paths carry explicit scope.
8. legacy unscoped records are quarantined until an explicit migration map
   exists; they are never treated as owner-global automatically.

Sidecar bindings are preferred for the first proof because adding columns
directly to `tasks` would make the current `SELECT *` plus Pydantic
`extra="forbid"` row mapper reject the new column during mixed-version or
rollback operation. The pilot must either retain sidecars as the authoritative
binding or prove an ordered migration that avoids this compatibility hazard.

## Questions and workstreams

### 1. Canonical schema and migration

Evidence required:

- ordered schema proposal with immutable IDs and lifecycle states;
- exact foreign keys, uniqueness constraints, and scope triggers;
- fresh-database, existing-database, rollback, and interrupted-migration tests;
- explicit treatment of the separate memory database.

Decision:

- proceed only if new project work cannot exist without one authoritative
  binding and old unscoped work is quarantined.

### 2. Task, run, lock, and process propagation

Evidence required:

- project/task/attempt reservation is atomic before launch;
- worker, child-process, cancellation, restart adoption, and operation-lock
  paths retain the same scope;
- same repository shared across projects remains serialized by the one
  repository resource lock while ownership remains attributable.

Decision:

- stop if project scope creates a second lock system or weakens lease/process
  identity.

### 3. Repository and worktree identity

Evidence required:

- canonical path and Windows volume/case identity;
- explicit exclusive/shared repository bindings;
- worktree containment, branch identity, and cross-project mutation tests.

Decision:

- paths and `repo_name` remain locators only; ambiguity fails closed.

### 4. Memory and retrieval

Evidence required:

- project scope is mandatory before filtering, ranking, or deduplication;
- identical records in two projects remain distinct;
- supersession cannot cross projects without an explicit typed link;
- owner-global access is explicit rather than the result of omission.

Decision:

- the existing unscoped global paths cannot be used by project workers.

### 5. External sessions and credentials

Evidence required:

- exact Codex, Claude/ACP, and Hermes session IDs can bind to one task/project
  without copying provider state;
- result, cancel, resume, and reconcile validate the binding;
- credential references are explicit project or shared-resource bindings and
  secret material never enters projections.

Decision:

- provider-specific tables do not become competing project authorities.

### 6. Controller compatibility and projections

Evidence required:

- existing direct-controller task and run workflows remain usable;
- optional project fields are additive and stay within CF1 response budgets;
- an omitted project can resolve only through a unique explicit binding;
- worker-facing and ambiguous operations fail closed.

Decision:

- no static vendor catalogue, controller-specific schema, or silent
  conversation-derived scope is accepted.

## Evidence checklist

- [x] Owner activation recorded.
- [x] Clean preflight with no live runs or locks.
- [x] Live source and schema inventory.
- [x] Historical-run backfill classification.
- [x] Disposable two-project schema proof.
- [x] Production-shaped sidecar fixture on temporary real Soma stores.
- [x] Real-store confusion proof for tasks, runs, repositories, worktrees,
  memory, artifacts, explicit credential bindings, and Hermes session binding.
- [x] Additive task projection fields remained within the CF1 byte budget at the
  projection-function boundary.
- [x] Baseline task, memory, artifact, and SSH-binding tests:
  `57 passed in 7.90s`.
- [x] Extended focused validation: `93 passed in 18.13s`.
- [x] Production-shaped migration test on disposable copies of the live stores;
  both live file hashes remained unchanged.
- [x] Lock, process, cancellation, and restart confusion tests.
- [x] Explicit credential-reference binding and Hermes
  restart/reconciliation confusion tests.
- [x] Strict additive public MCP task/run schema, incumbent-payload, and
  prior direct-controller transport compatibility evidence.
- [x] Backfill and quarantine manifest reviewed and accepted by the owner.
- [x] Final decision: **proceed** with the additive project-identity seam.

## Post-pilot next actions

1. Define the smallest production implementation lane from the accepted
   sidecar seam and measured integration requirements.
2. Keep every historical candidate unassigned until a separate explicit
   migration map is reviewed and approved; unresolved records remain
   quarantine-default.
3. Keep PILOT-MEMORY-1 inactive until separately selected. Do not copy the
   test fixture wholesale into production or begin implementation implicitly.

## Loop avoidance rules

- One primary confusion matrix and one evidence-fix rerun per workstream.
- One production-shaped sidecar design; switch only if a named invariant fails.
- No more than one compatibility adapter for incumbent controller calls.
- No inferred backfill attempts. Unresolved records go directly to quarantine.
- After one focused fix pass, a still-failing quality gate is reported rather
  than expanded into unrelated cleanup.

## Stop conditions

Pause and report if:

- a live schema or record mutation is required;
- active runs, workers, or locks appear before a mutation experiment;
- project scope would duplicate task, run, lock, evidence, repository, or
  provider-session authority;
- a mapping depends on name similarity, content similarity, path prefix, or
  controller conversation;
- a required public-contract change is controller-vendor-specific;
- secret material would enter evidence or projections;
- the next step requires owner approval for historical mapping or quarantine.

## Completion definition

PILOT-SCOPE-1 completes only when the evidence checklist is complete and the
record declares one explicit outcome. A passing outcome requires two confusing
projects to remain isolated across tasks, attempts, repositories, worktrees,
memory, retrieval, locks, processes, credentials, external sessions, evidence,
and artifacts; unscoped and cross-project operations must fail closed; existing
controller workflows must remain usable; and the owner must review the
backfill/quarantine plan before any production implementation begins.
