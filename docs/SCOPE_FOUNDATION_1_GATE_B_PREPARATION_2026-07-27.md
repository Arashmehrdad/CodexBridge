# SCOPE-FOUNDATION-1 Gate B Preparation

**Status:** prepared for owner review. Gate B is not authorized and has not been
executed. Gate C remains inactive.

## Decision requested

Approve or decline one live **schema-only** activation of ProjectScope v1 in
`runs/soma.sqlite3`.

Approval would authorize only the additive migration and its verification. It
would not create a project, bind a repository, enable scoped writes, classify
historical records, activate memory, or begin Gate C.

## Current live state

The refreshed runtime is healthy and converged on Gate A code:

- server build: `1b7a0021933e0e79da763e5de8cd2c1222336fec15d587408ab5d8f31646f572`;
- capability epoch: `1b7a0021933e-42bdb69d96fb`;
- public/runtime input schema hash:
  `5627542cd1fdf44e90562836b44f90130c75cc776fe371318c79a215108f5938`;
- discovery converged with no mismatches;
- all ten compact self-check categories passed;
- ProjectScope schema version is `0`;
- no ProjectScope tables exist;
- scoped writes are disabled and enforcement is `inactive`.

A server restart loaded the Gate A code and additive MCP fields but did not run
the migration. That is the expected pre-Gate-B state.

## Current-store disposable rehearsal

A consistent SQLite online backup was taken inside one read transaction and
migrated only in a disposable temporary directory. The source database was not
changed.

Authoritative evidence run:
`20260727T125908Z_executable_profile_f66990c8`.

Point-in-time source evidence at `2026-07-27T12:59:12Z`:

- runs: `4,681`;
- canonical tasks: `2`;
- run-ID hash:
  `b4e6c7bb84680eac05092577b98e192798dc916d4ed63b5817f0e215a1551522`;
- task-ID hash:
  `f01ebfd5f61eeef8f3703966ef99f528feb1cca0fef937f9dbce29850d0e0285`;
- incumbent-schema hash:
  `59481e61b17bd2ec36f67866a1d9f4311af96189d27eeadc60735f01b8fb4deb`;
- disposable backup SHA-256:
  `df9adb4959946da228a83f17d058e78755d261ff9b900b1c75e2eaed62df48ab`.

Rehearsal result:

- the backup matched the source transaction exactly;
- first migration application returned `[1]`;
- second application returned `[]`;
- run count, task count, run-ID hash, task-ID hash, and incumbent-schema hash
  remained identical;
- all project, resource, binding, reservation, bootstrap-event, and quarantine
  tables remained empty;
- `scoped_writes_enabled = 0` and `ever_activated = 0`;
- integrity check returned `ok`;
- foreign-key check returned zero rows;
- the expected ProjectScope v1 tables and migration marker were present;
- all disposable preparation directories were removed.

The first rehearsal pass produced a false incumbent-schema mismatch because the
measurement included SQLite auto-indexes belonging to the newly created sidecar
tables. No live file was changed. The single focused evidence-fix rerun excluded
objects by owning table and passed. This correction concerns the verifier, not
the migration.

Counts and file metadata are point-in-time evidence. Ordinary durable traffic
continues to change them; Gate B must take a fresh snapshot immediately before
activation.

## Compatibility and rollback basis

Gate A already proved that the pre-Gate-A application revision can read runs
and tasks from a migrated current-store copy. The migration adds sidecar tables
only and does not alter incumbent table schemas.

Before Gate C, rollback is simple and non-destructive:

1. stop the runtime;
2. keep the additive ProjectScope tables in place;
3. run the known pre-Gate-A application revision
   `15de7ad3838439c827960ec361d2368d67d81ffe`, or restore the fresh Gate B
   backup if integrity or incumbent-state verification failed;
4. do not drop sidecar tables automatically;
5. confirm exact-ID legacy reads and runtime health.

If a migration statement fails, its `BEGIN IMMEDIATE` transaction must roll
back the whole ProjectScope version and marker. A second live migration attempt
requires another owner review.

## Gate B activation procedure

This sequence may run only after explicit owner approval.

1. Record the expected repository HEAD and running build.
2. Prevent new work and verify no running, queued, launch-pending, worker, or
   operation-lock state.
3. Stop the Soma server cleanly. The tunnel may remain up, but the upstream is
   expected to be unavailable during the maintenance window.
4. Create a new durable timestamped SQLite backup outside the repository's
   tracked files. Record its SHA-256, size, integrity result, foreign-key result,
   run/task counts, and stable ID hashes. Verify the backup equals the source
   transaction logically.
5. Rehearse ProjectScope v1 once more on a disposable copy of that exact backup.
6. Apply `ProjectScopeStore.init_db()` once to the closed live store.
7. Verify:
   - exactly the ProjectScope v1 marker was added;
   - all expected sidecar tables exist;
   - every identity, binding, reservation, bootstrap-event, and quarantine
     table is empty;
   - scoped writes and `ever_activated` remain `0`;
   - incumbent run/task counts and stable ID hashes match the fresh backup;
   - incumbent schema hash is unchanged;
   - integrity and foreign-key checks pass.
8. Restart Soma and refresh the tunnel/connector.
9. Verify capability identity convergence and self-check success.
10. Verify task capabilities report ProjectScope schema version `1`, no missing
    tables, scoped writes disabled, and enforcement `inactive`.
11. Commit only the Gate B evidence and plan status. Do not push unless
    separately instructed.

## Stop conditions

Stop without retrying or widening scope if:

- any run, worker, queue item, launch-pending record, or operation lock is active;
- the fresh backup cannot be created or verified;
- the fresh rehearsal differs from this migration shape;
- the migration would create any project, resource, binding, reservation,
  bootstrap-event, or quarantine row;
- scoped writes or `ever_activated` becomes true;
- an incumbent count, ID hash, table schema, result hash, or publication record
  changes;
- integrity or foreign-key checks fail;
- migration output is not one clean v1 application;
- the restarted runtime does not converge on the expected source and schema;
- Gate C identity input becomes necessary.

## Explicit non-authorizations

Gate B preparation and activation do not authorize:

- project or repository bootstrap;
- scoped task creation or project enforcement;
- historical assignment or quarantine writes;
- project-scoped memory, Obsidian integration, or PILOT-MEMORY-1;
- Hermes, credential, worktree, lock-key, workflow, supervisor, SSH, container,
  browser, desktop, scheduler, or Trading Lab migration;
- pushing local commits.

## Owner decision language

A sufficient approval is:

> Approve SCOPE-FOUNDATION-1 Gate B schema-only activation using the prepared
> procedure. Do not perform Gate C, enable scoped writes, create bindings,
> classify historical records, activate memory, or push.
