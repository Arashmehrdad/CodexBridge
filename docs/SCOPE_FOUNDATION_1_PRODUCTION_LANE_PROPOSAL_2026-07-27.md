# SCOPE-FOUNDATION-1 Production Lane Proposal

**Status:** accepted — Gate A active. Gate B and Gate C remain inactive and require separate explicit owner approval.

**Current verdict:** **proceed with scope cut**. Implement the smallest useful
production authority seam for new canonical task/run work in the main Soma
store. Do not include memory, Hermes, worktrees, credentials, other legacy run
producers, or historical disposition in this lane.

**Owner decision — 2026-07-27:** accepted without edits. Gate A is active and
authorizes production code plus tests against fresh databases and disposable store
copies only. It does not authorize a live schema mutation, live project or
repository bootstrap, historical assignment or quarantine writes, memory or
Hermes integration, or a push.

## Purpose

Introduce immutable project identity as a production correctness boundary for
new canonical durable-command tasks without turning the first implementation
lane into an all-runtime migration.

This lane converts the accepted PILOT-SCOPE-1 result into a bounded coding
batch. It establishes the authoritative chain:

`project -> repository resource -> canonical task -> durable run attempt`

Evidence and artifacts continue to inherit project scope through exact task or
run references. The existing task, run, process, lease, result, evidence, and
operation-lock authorities remain authoritative for their current concerns.

## Decisions already accepted

- Soma owns canonical project identity and scope.
- Project isolation is a correctness invariant, not a permission system.
- `project_id` is immutable and opaque. It is never lowercased, normalized, or
  inferred from a label, path, repository name, host, content, or conversation.
- `repo_name` and a resolved path are locators, not project authority.
- New project-owned work fails closed when its binding is missing, stale, or
  ambiguous.
- One authority owns each concern; scope must not introduce another task, run,
  process, evidence, result, scheduler, or lock authority.
- Existing opaque identifiers remain exact.
- The accepted historical manifest is evidence, not an assignment map.
- PILOT-MEMORY-1 remains inactive.

## Production outcome

When this lane is complete:

1. Soma has one durable, queryable project registry and one generic resource
   registry in `runs/soma.sqlite3`.
2. A repository resource can be explicitly bound to one or more projects with
   an explicit access mode. Identical aliases do not establish identity.
3. Every new project-aware canonical task reserves its exact task ID, run ID,
   project ID, repository resource ID, and project generation before the
   incumbent task or run can launch.
4. Canonical task start, status, result, events, links, and cancellation can
   assert project scope. Cross-project reads, links, cancellation, and resource
   use fail before returning data or signalling a process.
5. Missing attachment and restart windows resolve deterministically to
   attachment, `recovery_pending`, or quarantine. They never guess ownership or
   duplicate a launch.
6. Existing owner-controller exact-ID reads remain available for legacy
   unscoped records. Their readability does not promote them into a project.
7. Current Claude and Codex controllers can use both incumbent and scoped MCP
   payloads directly against Soma.
8. No historical task, run, memory, or quarantine record is written by the
   schema migration or this implementation lane.

## In scope

### Project and repository-resource authority

Add one production project-scope component responsible for:

- immutable projects, lifecycle state, and scope generation;
- opaque resources and stable identity hashes;
- explicit project-resource bindings and access mode;
- explicit repository bindings;
- canonical task scope reservations;
- durable run-attempt scope reservations;
- reservation recovery and deterministic quarantine evidence;
- exact task/run-to-project resolution and scope assertions.

Project labels and repository aliases may be useful lookup values. They never
replace the opaque IDs or stable resource identity.

The implementation may choose its internal class and table names. It should
remain recognizably aligned with the accepted sidecar proof, and should be a
small dedicated component rather than spreading project SQL across task, run,
gateway, and server modules.

### Canonical task/run integration

Integrate only the existing canonical `task_action` durable-command path and
its exact task/run reads and controls:

- resolve an explicit project and repository binding;
- reserve task and run scope before the incumbent task/run records and before
  launch;
- include resolved project and resource identity in the normalized request
  hash so an idempotent replay cannot cross projects;
- preserve historical request hashes: a bound task compares the scoped
  normalized hash, while a legacy unbound task continues to compare its legacy
  hash; old hashes are never rewritten;
- enforce same-project parent-task and typed task/run links;
- accept the bound repository root or an already validated contained working
  directory; reject an external worktree path until a later worktree scope lane
  exists;
- preserve incumbent task state-version, run lease, process identity,
  cancellation, publication, and evidence behavior;
- reconcile reserved, attached, and recovery-pending scope records at startup
  with compare-and-set or equivalent conditional transitions.

A direct legacy `RunStore` producer is not project-owned merely because the
new component exists. It remains an explicitly legacy, unscoped path until a
later bounded lane migrates that producer.

### Public compatibility surface

Add `project_id` as an optional field only to the affected strict task/run MCP
variants.

- Existing required fields do not change.
- `additionalProperties: false` remains in force.
- An explicit `project_id` is validated before any read or mutation.
- An omitted project on canonical task start may resolve only through exactly
  one explicit active repository binding. Zero or multiple bindings fail
  closed.
- Omitted project scope on owner exact-ID reads preserves incumbent access,
  including historical legacy records, and reports them as
  `legacy_unassigned` rather than implying owner-global project scope.
- Project-aware internal and worker-facing callers must provide or resolve a
  project; they may not use owner-global omission as a fallback.
- Additive project fields appear in compact responses only when backed by an
  authoritative binding and must remain within existing response budgets.
- Global/list queries do not silently become project-scoped in this lane.

### Minimal bootstrap capability

Provide one bounded, idempotent owner operation or equivalent internal service
for explicitly creating projects, registering repository resources, and
binding them. It must:

- accept or return exact opaque IDs;
- preview normalized identities and conflicts before applying a binding;
- reject ambiguous or conflicting identities;
- preserve an evidence record of the explicit input and outcome;
- never scan current runs, tasks, memory, or conversations to infer ownership.

The exact project/repository bootstrap map is an owner input at a later
activation gate. This proposal does not supply or apply it.

## Permanent invariants

### Authority and identity

- The project-scope component is the sole authority for project identity and
  project-resource/task/run bindings.
- `TaskStore` remains authoritative for canonical task state.
- `RunStore` remains authoritative for run, worker, process, lease, result, and
  publication state.
- `OperationLockStore` remains the only repository-operation lock authority.
- Artifact and evidence stores retain exact run references; they do not copy a
  mutable project label as independent truth.
- All opaque IDs are compared and stored exactly.

### Persist-before-launch and recovery

- Task ID, run ID, project ID, resource ID, generation, and launch intent are
  durably reserved before process creation.
- Project scope cannot weaken current idempotency, lease generation, process
  identity, state-version, cancellation, or terminal-publication guards.
- One failed immediate attachment moves to a durable recovery state; it does
  not start an inline relaunch loop.
- One reconciler claims a scope record per generation. Concurrent reconcilers
  cannot both attach, adopt, quarantine, or relaunch it.
- Missing, stale-generation, or contradictory records are reported and moved
  to recovery or quarantine. Ownership is never guessed.

### Isolation

- A task has exactly one project.
- A run attempt has exactly one project, one canonical task, and one resource
  binding in this lane.
- A parent task and typed task/run link must resolve to the same project.
- A supplied project assertion is checked before result, event, artifact,
  cancellation, or process access.
- Shared repository access is explicit. Sharing does not create a second lock
  system or permit cross-project task/run access.

## Migration boundaries

### Main-store ProjectScope v1

Use a new ordered migration component in `runs/soma.sqlite3`. The migration is
additive:

- create only project-scope sidecar tables, indexes, constraints, and its
  component/version marker;
- do not add columns to `tasks` or `runs`;
- do not drop, rewrite, or backfill incumbent tables;
- do not create project, resource, task, run, or quarantine assignments;
- execute the whole version in one `BEGIN IMMEDIATE` transaction;
- enable foreign keys on every owned connection;
- be idempotent on fresh and existing databases;
- roll back every v1 object and its marker when any statement fails.

Avoid a global `runs` or `operation_locks` insert trigger in this lane. Soma has
multiple incumbent unscoped run producers; globally blocking them would make
this an all-runtime migration. The scope-aware canonical-task coordinator must
enforce the boundary for project-owned work, and consistency checks must detect
any scoped task/run that bypasses it.

Adding columns directly to `tasks` is excluded because `TaskStore` reads
`SELECT *` into strict Pydantic records. Sidecars preserve previous-version
read compatibility and provide a safer application rollback boundary.

### Separate memory-store boundary

Do not change `runs/memory/project_memory.sqlite3` in this lane. No project
memory API may be advertised as safe for project workers until a later,
separately approved scope lane makes project filtering precede matching,
ranking, and deduplication.

This exclusion does not activate PILOT-MEMORY-1 and does not decide the future
Markdown/SQLite memory baseline. It simply prevents this foundation lane from
silently widening into memory architecture.

### Historical boundary

The schema-only migration must leave all sidecar binding and quarantine tables
empty.

- 2,083 historical runs remain candidate-only.
- 2,589 runs remain quarantine-default, not written as quarantined.
- Two canonical tasks and two `soma` memory records remain candidate-only.
- Ninety-eight `codexbridge` memory records remain quarantine-default.

Any historical disposition requires a separate lane with an owner-approved
exact-ID map, dry-run counts and hashes, rollback evidence, and another explicit
approval. Repository names, paths, structured input, host labels, and
conversations cannot become migration authority.

## Activation and rollback gates

### Gate A — implementation and disposable evidence

Owner activation of SCOPE-FOUNDATION-1 authorizes production code and tests
against fresh databases and disposable copies only. It does not authorize a
live schema mutation or live bootstrap.

Gate A must produce the complete acceptance evidence below and a clean local
commit.

### Gate B — live schema-only activation

Requires a separate explicit owner approval after Gate A review. Preconditions:

- no active runs, workers, or operation locks;
- verified live backup and source hashes;
- disposable-copy rehearsal against the then-current database;
- migration preview showing zero identity or quarantine assignments;
- documented previous-version read compatibility and rollback procedure.

If approved, Gate B creates schema only. It does not create a project or bind a
repository.

### Gate C — project/repository bootstrap and scoped cutover

Requires another explicit owner approval of exact immutable project IDs and
exact resource bindings. The bootstrap evidence must contain the reviewed
input, normalized resource identities, conflict checks, and resulting hashes.

After scoped writes exist, a write-capable downgrade is unsafe because an older
writer cannot enforce their project boundary. Rollback then means disabling
scoped mutation or entering maintenance while retaining a scope-aware binary.
Concurrent old and new writers are forbidden. Additive sidecar tables are
retained; they are never auto-dropped during rollback.

Historical assignment is not part of Gate C.

## Compatibility requirements

- Preserve all existing task/run required fields, defaults, discriminator
  values, and strict-schema behavior.
- Preserve current controller request idempotency. Its normalized hash must
  include authoritative project/resource identity.
- Preserve legacy request hashes and replay behavior for unbound historical
  tasks; never rewrite them into the scoped hash scheme.
- Preserve owner exact-ID lookup for legacy unscoped tasks and runs.
- Label uncertainty honestly: absence of a scope row means legacy/unscoped, not
  owner-global or implicitly current-project.
- Keep controller-neutral persisted terminology.
- Preserve exact error/result/evidence references and public-result hashes.
- Preserve CF1 compact response limits.
- Repeat direct Claude and Codex MCP calls after the production schema changes;
  test both incumbent project-less reads and explicit scoped workflows.
- Do not require a vendor catalogue, shell proxy, or controller conversation to
  resolve project scope.

## Expected implementation areas

The implementing agent should confirm the live repository before editing.
Likely bounded areas are:

- a new `soma/project_scope/` component for models, migrations, store/service,
  reconciliation, and projections;
- `soma/tasks/manager.py` for scoped canonical reservation, attachment, lookup,
  cancellation, and reconciliation;
- `soma/gateway_models.py` and `soma/server.py` for optional strict MCP inputs
  and minimal bootstrap/query routing;
- `soma/tasks/projections.py` for bounded authoritative project fields;
- a narrow `RunStore` integration seam only if needed to preserve atomic
  reservation/creation evidence;
- focused project-scope tests plus adjacent task, run, gateway, lock, process,
  cancellation, publication, and artifact regression tests.

Do not copy the pilot fixture wholesale. Production code must use the
repository's ordered migration and durable error-publication conventions.

## Questions and workstreams

### 1. Production sidecar and bootstrap

Evidence required:

- ordered v1 schema and store API;
- explicit identity normalization and conflict behavior;
- idempotent preview/apply bootstrap behavior;
- no inferred or historical writes.

Decision:

- proceed only if schema activation leaves every binding/quarantine table empty
  and bootstrap requires explicit owner-supplied identity.

### 2. Canonical task/run reservation

Evidence required:

- project/resource/task/run reservation precedes incumbent inserts and launch;
- idempotent replay cannot cross projects;
- parent/link scope checks;
- deterministic recovery for every changed crash window.

Decision:

- stop if the lane must migrate unrelated run producers or weakens incumbent
  task/run lifecycle authority.

### 3. Exact read/control isolation

Evidence required:

- explicit project assertions on task/run reads and cancellation;
- cross-project reads, artifacts, links, and signals fail closed;
- omitted owner exact-ID reads remain compatible and are honestly identified
  as legacy when no scope binding exists.

Decision:

- stop on any result, event, artifact, process, or cancellation confusion.

### 4. MCP and projection compatibility

Evidence required:

- strict schema snapshots before and after;
- only optional fields added;
- incumbent payload parse/replay tests;
- direct Claude and Codex calls;
- compact response measurements.

Decision:

- stop if a controller-specific schema, required-field change, or CF1 budget
  regression is necessary.

## Acceptance evidence checklist

### Schema and migration

- [ ] Fresh-database migration.
- [ ] Disposable current-main-store-copy migration.
- [ ] Second application is a no-op.
- [ ] Forced mid-migration failure leaves no v1 objects or marker.
- [ ] Integrity and foreign-key checks pass.
- [ ] Pre-existing task/run counts and stable ID hashes remain unchanged.
- [ ] New scope binding and quarantine tables are empty after schema-only
  migration.
- [ ] The previous application revision exercises its promised legacy read path
  against a migrated copy.

### Isolation and durability

- [ ] Two projects with identical repository aliases, objectives, filenames,
  and branches retain distinct project/resource/task/run identities.
- [ ] Explicit, omitted-unique, omitted-unknown, and omitted-ambiguous project
  starts produce the required outcomes.
- [ ] Parent-task, task-link, run-link, exact read, artifact read, and
  cancellation confusion tests fail closed.
- [ ] Reservation-before-insert and persist-before-launch ordering is proven.
- [ ] Crash after scope reservation, after task insert, after run insert, and
  before/after attachment is deterministic.
- [ ] Concurrent startup reconcilers cannot double-attach or duplicate launch.
- [ ] Cancellation racing completion preserves current CAS, lease, process,
  lock, and terminal-publication invariants.
- [ ] Opaque IDs survive storage, lookup, projection, cancellation, and restart
  byte-for-byte.

### Compatibility and quality

- [ ] MCP schema diff shows optional additions only and remains strict.
- [ ] Incumbent task/run payload and idempotent replay tests pass.
- [ ] Direct Claude and Codex MCP calls pass for incumbent and scoped cases.
- [ ] Project fields remain within task/run CF1 response budgets.
- [ ] Existing task, run, lock, worker identity, cancellation, publication,
  artifact, and gateway suites pass.
- [ ] Ruff format/check passes on changed Python.
- [ ] Configured type checking, full pytest, `pip check`, and configured
  pre-commit/security gates pass.
- [ ] Scoped diff shows no unrelated files, live data, credentials, generated
  evidence, or memory changes.
- [ ] Work is committed locally and not pushed.

## Retry and loop-avoidance rules

- One sidecar architecture. Re-scope rather than build a parallel alternative.
- One migration attempt per process startup; zero automatic in-process retries.
- One immediate reservation/attachment attempt. Failure becomes durable
  recovery state.
- One compare-and-set reconciliation claim per record per pass and at most one
  adopt-or-relaunch decision per run per project generation.
- One focused implementation-fix pass after a failing quality gate. A second
  related failure is reported rather than expanded into unrelated cleanup.
- One direct Claude and one direct Codex compatibility pass after local tests;
  one bounded environment-fix rerun per client.
- A failed live migration rolls back, disables scoped mutation, and is
  reproduced once on a fresh copy. Another live attempt requires owner review.

## Stop conditions

Stop and report if:

- project ownership must be inferred;
- columns must be added to `tasks` or `runs`;
- unrelated run producers must be migrated for this lane to work;
- a global run/lock trigger would break incumbent producers;
- the memory database, Hermes, worktrees, credentials, or historical records
  become necessary for the foundation to function;
- an existing required MCP field, discriminator, or strict-schema behavior
  must change;
- any cross-project read, mutation, cancellation, artifact access, or task/run
  link succeeds;
- a second task, run, resource, process, evidence, result, or lock authority is
  introduced;
- restart recovery can launch or attach the same run twice;
- migration rollback, integrity, foreign-key, previous-version read, or public
  response-budget evidence fails;
- secrets enter schema, logs, evidence, or projections;
- a live mutation is required before its explicit owner gate.

## Explicit exclusions

- No live database migration or bootstrap during plan or Gate A work.
- No historical assignment, backfill, or quarantine writes.
- No project-scoped memory implementation or PILOT-MEMORY-1 activation.
- No Hermes or other external-session integration.
- No credential storage or provider-specific credential binding.
- No worktree registry or worktree lifecycle changes.
- No external worktree path acceptance; contained working directories remain
  usable through the bound repository resource.
- No operation-lock key migration and no second lock system.
- No SSH, workflow, supervisor, scheduler, browser, desktop, container, or
  Trading Lab migration.
- No general worker plane, ACP/ACPX, OpenClaw, voice, or channel work.
- No permission tiers, approval prompts, allowlists, or autonomy gates.
- No Roadmap V3 rewrite.

## Completion definition

SCOPE-FOUNDATION-1 implementation is ready for owner review only when Gate A
evidence is complete and demonstrates:

- one production project/resource/task/run sidecar authority for new canonical
  work;
- fail-closed confusion resistance without inferred ownership;
- unchanged incumbent task/run/process/lock/result/evidence authorities;
- additive migration and previous-version read compatibility;
- deterministic crash and restart behavior;
- strict, compact, vendor-neutral MCP compatibility;
- no live or historical mutation;
- a clean local commit with nothing pushed.

Completion of Gate A does not authorize Gate B or Gate C. Memory, Hermes,
worktrees, credentials, other run producers, and historical disposition remain
separate owner-selected lanes.

## Ranked next actions

1. Owner accepts, edits, or declines this production lane.
2. If accepted, activate Gate A only and assign an engineering lead with a
   durability/recovery reviewer.
3. Review Gate A evidence and the proposed live schema migration separately.
4. If Gate B is later approved and succeeds, prepare an exact project/repository
   bootstrap manifest for Gate C owner review.
5. Keep all excluded concerns inactive until separately selected.
