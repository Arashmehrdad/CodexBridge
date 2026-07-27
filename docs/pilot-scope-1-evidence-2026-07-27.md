# PILOT-SCOPE-1 Evidence and Execution Record

**Status:** active — bounded investigation only.

**Current verdict:** proceed with the bounded investigation. The disposable
schema proof passed its first confusion test, but the pilot has not passed its
full exit gate and no production implementation is authorized.

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
- [x] Baseline task, memory, artifact, and SSH-binding tests:
  `57 passed in 7.90s`.
- [ ] Production-shaped migration test on a disposable copy of the live stores.
- [ ] Lock, process, cancellation, and restart confusion tests.
- [ ] Credential and Hermes session-binding confusion tests.
- [ ] Memory query/deduplication confusion tests through the real repository API.
- [ ] Public task/run projection and response-budget compatibility tests.
- [ ] Backfill and quarantine manifest reviewed by the owner.
- [ ] Final proceed, scope-cut, switch, blocked, or stop decision.

## Ranked next actions

1. Write the production-shaped sidecar schema and migration as a disposable
   test fixture only, including the separate-memory-store boundary.
2. Run the two-project confusion matrix through real `TaskStore`, `RunStore`,
   memory repository, operation-lock, artifact, and Hermes gateway fakes.
3. Produce a deterministic backfill/quarantine manifest containing counts and
   hashes, not inferred assignments.
4. Exercise current MCP task/run projections with additive project fields and
   verify CF1 budgets and exact-ID retrieval.
5. Present the pilot verdict and smallest implementation batch for owner
   approval. Do not merge the proof into production code during this pilot.

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
