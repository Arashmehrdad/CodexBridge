# SCOPE-FOUNDATION-1 Gate B — Live Schema Activation

**Date:** 2026-07-27
**Status:** executed, owner-reviewed, and accepted. ProjectScope v1 schema is live, empty, and inactive.
**Authorization:** owner approval recorded at
[`60f8bec`](../docs/SCOPE_FOUNDATION_1_GATE_B_PREPARATION_2026-07-27.md), for
one schema-only activation using the prepared procedure.
**Repository HEAD at execution:** `60f8bec3022f40f6dc2703214bf40759826aa105`,
clean working tree.

This activation created **schema only**. No project, resource, binding,
reservation, bootstrap event, or quarantine row exists. Scoped writes remain
disabled and enforcement remains `inactive`. Gate C is not started, no
historical record was classified, and nothing was pushed.

---

## 1. Result

All 32 verification gates passed. The migration applied once, cleanly, and
every incumbent identity is byte-for-byte unchanged.

| Step | Outcome |
|---|---|
| 1. Record HEAD and running build | `60f8bec`, build `1b7a0021933e0e79…` |
| 2. Verify quiet system | 0 operation locks, 0 active runs, both tasks terminal |
| 3. Stop server cleanly | PID 30920 stopped; child 29356 exited with it |
| 4. Durable verified backup | taken, logically identical to source |
| 5. Fresh disposable rehearsal | passed, directory removed |
| 6. One live apply | returned exactly `[1]` |
| 7. Post-migration verification | all incumbent identities unchanged |
| 8. Restart | server up, reconciliation clean |
| 9. Capability convergence | `converged: true`, `mismatches: []` |
| 10. ProjectScope reported | `schema_version: 1`, enforcement `inactive` |
| 11. Commit evidence | this record; not pushed |

## 2. Pre-activation state

Taken immediately before the migration, with the server stopped:

- live store: `130,281,472` bytes, mtime `2026-07-27T12:50:35Z`;
- runs: `4,688`; canonical tasks: `2` (one cancelled, one completed);
- run-ID hash: `bfb6d75f87ccbe8a0149b80d0e8dd852631e0c1e4c7a13aaf847cda85c1ebb7e`;
- task-ID hash: `f6f42e8b575375381d00cd86e107dd4c046efae95003e12b90052de18c13d241`;
- incumbent-schema hash: `197c30a8d3a797f3f54c0dc779da3b95eb9e5ed10755373e1bf609c1600755e3`;
- `integrity_check` = `ok`; `foreign_key_check` = 0 rows;
- zero `project%` tables; `soma_schema_migrations` held only
  `canonical_task_plane` v1.

These figures differ from the preparation manifest's snapshot (4,681 runs at
`12:59:12Z`) because ordinary durable traffic continued between preparation and
activation. The preparation document required a fresh snapshot at activation
for exactly this reason, and this is it.

## 3. Backup

```
runs/soma.sqlite3.backup-gate-b-20260727T131451Z
  size    130,494,464 bytes
  sha256  f47cc830c0ecc5f7cd13a1103a230adff0b645417dc4368dbdaa8b98e9af1296
```

Taken with the SQLite online backup API against the stopped store, so the WAL is
folded in. Verified to reproduce the source transaction logically: run count,
task count, run-ID hash, task-ID hash, incumbent-schema hash, integrity, and
foreign-key results all matched the source exactly. The backup lives under
`runs/`, which is git-ignored, and is the rollback artifact for this gate.

## 4. Rehearsal on that exact backup

A byte-identical copy of the backup was migrated in a temporary directory:

- first apply returned `[1]`; second apply returned `[]`;
- all nine sidecar tables present, all binding and quarantine tables empty;
- `scoped_writes_enabled = 0`, `ever_activated = 0`;
- exactly one marker: `project_scope / 1 / additive_project_identity_foundation`;
- incumbent state identical to source;
- temporary directory removed.

### Verifier note

The incumbent-schema hash excludes schema objects **by owning table**, not by
object name. SQLite creates auto-indexes for the new sidecar tables' `UNIQUE`
constraints, and those auto-indexes carry the sidecar `tbl_name`. Excluding by
name alone counts them as incumbent drift and produces a false mismatch — which
is what the preparation lane's first rehearsal pass hit. The exclusion used here
is by `tbl_name`, so it is correct by construction rather than by patch.

## 5. Live activation and verification

`ProjectScopeStore.init_db()` was applied once to the closed live store and
returned `[1]`. Re-running it returned `[]`.

Verified afterwards:

- all nine sidecar tables present, zero missing;
- every binding, reservation, bootstrap-event, and quarantine table **empty**;
- `scoped_writes_enabled = 0`, `ever_activated = 0`, enforcement `inactive`;
- run count `4,688` → `4,688`; task count `2` → `2`;
- run-ID hash, task-ID hash, and incumbent-schema hash **all unchanged**;
- `integrity_check` = `ok`; `foreign_key_check` = 0 rows;
- `canonical_task_plane` v1 marker still present alongside the new
  `project_scope` v1 marker;
- live store after migration: `130,596,864` bytes.

## 6. Post-restart runtime

Capability identity converged with **no mismatches**, on the same identities the
preparation document predicted:

- server build: `1b7a0021933e0e79da763e5de8cd2c1222336fec15d587408ab5d8f31646f572`;
- capability epoch: `1b7a0021933e-42bdb69d96fb`;
- public/runtime input schema hash:
  `5627542cd1fdf44e90562836b44f90130c75cc776fe371318c79a215108f5938`;
- discovery cache generation:
  `560b973d3ca51b7ee24a09f5c3ae2c6eb785bed396a6ab5214404a72fda15d78`.

All ten self-check categories passed. `task_query(capabilities)` now reports:

```json
"project_scope": {
  "schema_version": 1, "target_schema_version": 1, "up_to_date": true,
  "missing_tables": [],
  "scoped_writes_enabled": false, "enforcement_state": "inactive"
}
```

All six startup reconciliation paths reported `ok`, including the new
`project_scope` path (31 ms, nothing to examine because every sidecar table is
empty). This is the first live exercise of that path against an installed
schema.

An incumbent exact-ID read was confirmed unchanged after activation: run
`20260727T033409Z_executable_profile_84d39cd6` returned the same published
result hash `b12e400beb5eb8138765836d728667cb6dd48b1dcabb4b5be0114ef3669664e7`
observed before the migration.

## 7. Stop conditions

None were triggered. No run, worker, queue item, launch-pending record, or
operation lock was active; the backup verified; the fresh rehearsal matched the
migration shape; no identity, binding, reservation, bootstrap-event, or
quarantine row was created; scoped writes and `ever_activated` stayed `0`; no
incumbent count, hash, schema, or publication record changed; integrity and
foreign-key checks passed; the migration was one clean v1 application; and the
restarted runtime converged on the expected source and schema.

## 8. Rollback position

Rollback remains simple and non-destructive, and is unchanged from the
preparation basis:

1. stop the runtime;
2. leave the additive sidecar tables in place — they are empty and unread while
   enforcement is `inactive`;
3. run the pre-Gate-A revision `15de7ad3838439c827960ec361d2368d67d81ffe`, or
   restore `runs/soma.sqlite3.backup-gate-b-20260727T131451Z` if integrity or
   incumbent verification had failed;
4. do not drop sidecar tables automatically;
5. confirm exact-ID legacy reads and runtime health.

## 9. What remains unauthorized

Gate C project and repository bootstrap, scoped-write enablement, historical
assignment or quarantine writes, project-scoped memory, Obsidian integration,
PILOT-MEMORY-1, Hermes and other subsystem migration, and pushing local commits.

Scoped controller calls against the live endpoint remain deferred to Gate C, as
recorded in PLANS.md: Gate B creates schema only, so there is no binding for a
scoped call to resolve against. The scoped payload path itself was already
proved on a disposable store in
[`scope-foundation-1-gate-a-review-2026-07-27.md`](scope-foundation-1-gate-a-review-2026-07-27.md) §4.2.

## 10. Owner acceptance

**Decision:** accepted on 2026-07-27.

The owner review independently confirmed:

- the committed activation changed only the plan and Gate B evidence records;
- live task capabilities report ProjectScope schema v1 installed, with every
  table present, scoped writes disabled, and enforcement `inactive`;
- all ten runtime self-check categories pass;
- the repository is clean at activation commit
  `2cfbd1c153258e82aaa5f961767e25e043719793`, with no active runs or locks at
  the review checkpoint;
- incumbent run `20260727T033409Z_executable_profile_84d39cd6` still reports
  publication hash
  `b12e400beb5eb8138765836d728667cb6dd48b1dcabb4b5be0114ef3669664e7`;
- the rollback artifact independently re-opened read-only with integrity `ok`,
  4,688 runs, two tasks, zero `project%` tables, and sha256
  `f47cc830c0ecc5f7cd13a1103a230adff0b645417dc4368dbdaa8b98e9af1296`.

The 4,688-run count is point-in-time activation evidence. Ordinary durable
verification traffic after activation may increase the live run count without
changing this decision.

Gate B is closed. This acceptance does not authorize Gate C, scoped-write
enablement, project or repository bootstrap, historical disposition,
PILOT-MEMORY-1, Obsidian integration, Hermes changes, or a push.
