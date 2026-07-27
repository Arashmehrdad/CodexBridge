# SCOPE-FOUNDATION-1 ProjectScope Schema v2 Activation Preparation

**Date:** 2026-07-27
**Status:** prepared for owner review; not authorized or executed.
**Live state:** ProjectScope v1 remains installed, empty, and inactive. Scoped writes are disabled.
**Purpose:** activate only the accepted quarantine-adjudication schema added by `GATE-C-PREREQ-1`.

## Decision boundary

This package prepares one **schema-only** ProjectScope v1 ΓåÆ v2 activation against `runs/soma.sqlite3`.

It does not authorize or perform:

- project or repository bootstrap;
- Gate C;
- scoped-write enablement;
- quarantine adjudication or historical disposition;
- memory, Obsidian, Hermes, Codebase Memory, or other provider integration;
- migration of worktrees, credentials, locks, workflows, supervisors, SSH, scheduler, Trading Lab, or legacy run producers;
- cleanup of `_pytest-cf1-temp`;
- push.

`GATE-C-PREREQ-1` is owner-accepted and closed. The only purpose of v2 is to add its empty adjudication table and index before Gate C is considered.

## Source and runtime state

Preparation repository state:

- branch: `feature/chatgpt-companion-cycle`;
- source HEAD: `da418d70e89236d4e31c70b08a43fbc685baa6d6`;
- accepted prerequisite implementation: `22fd884bf685d766fcdad2b9ca017cede4acf183`;
- prerequisite acceptance: `b3a5f01a449d086698a6bbd18abaf7ce0380df46`;
- worktree clean;
- no running, queued, or launch-pending work;
- no operation locks.

The running server intentionally remains on the previously accepted v1 build:

- server build: `1b7a0021933e0e79da763e5de8cd2c1222336fec15d587408ab5d8f31646f572`;
- schema hash: `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`;
- capability epoch: `1b7a0021933e-42bdb69d96fb`;
- ProjectScope schema/target: `1 / 1`;
- enforcement: `inactive`.

No restart has loaded the v2 source yet. That avoids advertising an unapplied migration as a runtime regression before owner approval.

## Disposable current-store rehearsal

A consistent SQLite online backup was created from the live v1 store inside a read transaction and migrated only in a disposable directory.

Authoritative evidence run:

`20260727T191822Z_executable_profile_80bee901`

The first wrapper attempt, `20260727T191745Z_executable_profile_c43a5551`, failed before database access because the temporary Python script could not import the repository package. The corrected wrapper explicitly added the repository root and propagated the process exit code. No live mutation occurred in either attempt.

Point-in-time source evidence:

- snapshot: `2026-07-27T19:18:29.211939+00:00`;
- runs: `4,720`;
- canonical tasks: `2`;
- run-ID hash: `7047e12fe65f655ad864237f7abfdbdc79589d5555f7816035a8e8cb7e00b1a5`;
- task-ID hash: `20ad5dbff226e5c31de618d541dc434570243a785f8ab7722ff87eb61738e8f6`;
- publication projection hash: `69409019b78b91ab88ca15be1c0ee71cd64a9552798d0a2b487616196a4e1a2f`;
- source integrity: `ok`;
- source foreign-key violations: `0`;
- source settings: `scoped_writes_enabled = 0`, `ever_activated = 0`;
- disposable pre-migration backup SHA-256: `3576d1b3ec02dd591301dae2b3a9d23bb61d8c99b504df50a9fcda965092aba6`;
- disposable pre-migration backup size: `131,137,536` bytes.

The backup matched the source transaction logically before migration.

### Rehearsal result

All twelve checks passed:

1. first migration application returned exactly `[2]`;
2. second application returned `[]`;
3. the only new SQLite objects were `project_scope_adjudications` and `idx_project_adjudication_project`;
4. every pre-existing SQLite object remained byte-identical at the schema-SQL level;
5. run/task counts and stable ID hashes were unchanged;
6. publication projection hash was unchanged;
7. the table contains the required immutable `request_hash` column;
8. the adjudication table remained empty;
9. all project/resource/binding/reservation/quarantine/bootstrap/adjudication data tables remained empty;
10. `scoped_writes_enabled = 0` and `ever_activated = 0` remained unchanged;
11. integrity returned `ok`;
12. foreign-key check returned zero rows.

Exact v2 object hashes:

- adjudication table schema SHA-256: `b72af7e92f31e8fcf4ecb95675ddf5354b2c6a93c95041766442afe266f8bac9`;
- adjudication index schema SHA-256: `cf39f40cac9a8b0a29d0b3915058b066d68d4df24127ccef57ddaca1c253e5e5`;
- migrated disposable database SHA-256: `46a79adcfe5b2adc8c681ec1ac14c11695def8ae3c5a126bf92f7ed20cc80a99`.

The disposable directory was removed (`temporary_items_remaining = 0`). A final read-only check confirmed the live database still has only ProjectScope v1, no adjudication table, zero scope data rows, and settings `[0, 0]`.

Counts and hashes are point-in-time preparation evidence. Activation must take a fresh closed-store snapshot and must not reuse these values as its rollback baseline.

## Prepared live activation sequence

Execution requires a separate explicit owner approval.

1. Record the expected repository HEAD and the currently running build.
2. Verify a clean worktree and no running, queued, launch-pending, worker, supervisor, workflow, or operation-lock state that could write the main store.
3. Stop Soma cleanly and prevent concurrent old or new writers. The connector may remain configured, but the upstream is expected to be unavailable during maintenance.
4. Create a fresh durable timestamped SQLite backup outside tracked repository files using the SQLite backup API. Record path, SHA-256, size, integrity, foreign-key result, run/task counts, stable ID hashes, publication hash, schema objects, migration markers, and ProjectScope settings.
5. Verify that exact backup logically equals the closed live store.
6. Rehearse v1 ΓåÆ v2 on a disposable copy of that exact backup. Require the same twelve checks and exact v2 object hashes recorded above.
7. Apply `ProjectScopeStore.init_db()` once to the closed live store. Require result `[2]`.
8. Apply it a second time. Require result `[]`.
9. Before restart, verify:
   - the v2 marker is exactly `('project_scope', 2, 'quarantine_adjudication_path')`;
   - the only new SQLite objects are the reviewed adjudication table and index;
   - `request_hash` is present and constrained;
   - the adjudication table is empty;
   - all other scope data tables remain empty;
   - settings remain `[0, 0]`;
   - incumbent counts, ID hashes, publication hash, and existing schema objects match the fresh backup;
   - integrity is `ok` and foreign-key check is empty.
10. Start only the current source-aware runtime containing accepted v2 code.
11. Refresh discovery/connector state and verify build/schema/capability convergence.
12. Verify task capabilities report ProjectScope schema `2`, target `2`, no missing tables, scoped writes disabled, and enforcement `inactive`.
13. Query the new quarantine surface with an explicit project ID only to confirm the operation fails safely because no project exists; do not create a project or adjudication fixture on the live store.
14. Commit only activation evidence and plan status. Do not push.

## Rollback boundary

Before any post-backup durable mutation, migration or restart verification failure permits restoring the fresh backup after stopping all writers.

After any post-backup durable run/task/evidence mutation, do not restore blindly because that would erase authoritative work. Instead:

1. stop writers;
2. keep the additive v2 table in place;
3. run the last known v1-compatible runtime if necessaryΓÇöthe extra empty table is sidecar-only;
4. compare the fresh backup with current durable identities before considering restoration;
5. never drop `project_scope_adjudications` automatically.

Because Gate C and scoped writes remain disabled, no project reservation or adjudication may be created during this activation.

## Stop conditions

Stop without retrying or widening scope if:

- any writer, worker, queue item, launch-pending record, workflow, supervisor action, or lock is active;
- the fresh backup cannot be created and verified;
- live ProjectScope is not exactly v1 with settings `[0, 0]` and all scope data tables empty;
- the fresh rehearsal does not return `[2]` then `[]`;
- any existing SQLite object changes;
- any object beyond the reviewed table, index, and migration marker appears;
- `request_hash` or any reviewed constraint is absent;
- an adjudication or other scope data row appears;
- a run/task count, stable ID hash, publication hash, or incumbent schema object changes;
- integrity or foreign-key verification fails;
- the restarted runtime does not converge on schema `2 / 2` and enforcement `inactive`;
- Gate C identity data becomes necessary;
- `_pytest-cf1-temp` or any unrelated cleanup becomes entangled with the migration.

A failed execution requires a fresh preparation review before another live attempt.

## Owner approval language

A sufficient approval is:

> Approve one live ProjectScope schema-v2 activation using the prepared stop/backup/rehearse/apply/verify procedure. Do not execute Gate C, bootstrap a project or repository, enable scoped writes, adjudicate historical records, activate memory or Hermes, clean unrelated files, or push.
