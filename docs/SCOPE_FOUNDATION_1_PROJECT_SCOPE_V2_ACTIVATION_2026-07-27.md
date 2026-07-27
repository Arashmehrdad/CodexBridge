# SCOPE-FOUNDATION-1 ProjectScope Schema v2 Activation

**Date:** 2026-07-27
**Status:** owner-approved, executed, and verified.
**Scope executed:** schema-only ProjectScope v1 -> v2 against `runs/soma.sqlite3`.

This records the execution of the procedure prepared in
[`SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_PREPARATION_2026-07-27.md`](SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_PREPARATION_2026-07-27.md).

## What was authorized and what stayed excluded

The owner approved one live schema-v2 activation using the prepared
stop/backup/rehearse/apply/verify procedure. Not executed, unchanged, and still
unauthorized: Gate C, project or repository bootstrap, scoped-write enablement,
quarantine adjudication or historical disposition, memory, Obsidian, Hermes,
Codebase Memory, other lifecycle producer migration, `_pytest-cf1-temp` cleanup,
and push.

## Preflight

- branch `feature/chatgpt-companion-cycle`; HEAD `a69096fce4630860bcb0e63b3b9f96effd238c62`;
- source delta since the preparation HEAD `da418d70` was `PLANS.md` plus the two
  preparation documents only, so no code changed between review and execution;
- worktree clean; zero running, queued, and launch-pending runs; zero locks;
- live ProjectScope `1 / 1`, scoped writes disabled, enforcement `inactive`;
- running build `1b7a0021933e...`, capability epoch `1b7a0021933e-42bdb69d96fb`.

Soma was stopped with `manage_soma_service.ps1 -Action stop`. The Cloudflare
tunnel was intentionally left configured, so the public upstream was
unavailable for the maintenance window rather than reconfigured. Zero
`soma.server` processes and zero port-8000 listeners were confirmed before any
database access.

## Fresh baseline and backup

Preparation counts were **not** reused as the rollback baseline. Three runs had
been recorded since preparation, which is exactly why the procedure required a
fresh closed-store snapshot.

- backup: `runs/scope-v2-activation-20260727T193134Z/soma-pre-v2-backup.sqlite3`;
- backup SHA-256: `aeb034931d48548ab9d1001dfe1390caf612621acb44db3912eee2d2dcddeb04`;
- backup size: `131,211,264` bytes;
- runs: `4,723` (preparation observed `4,720`);
- canonical tasks: `2`;
- run-ID hash: `6264307e148fea81009628af00a6a86d9fb6aeeb4f4f01020cd3a9fe710f3c89`;
- task-ID hash: `f6f42e8b575375381d00cd86e107dd4c046efae95003e12b90052de18c13d241`;
- publication projection hash: `f6db23263c3c0779c1cf8c25b37f676313ce8b2af0b933a5030f8ea534d0790f`;
- integrity `ok`; foreign-key violations `0`; settings `[0, 0]`;
- ProjectScope markers before: exactly `(project_scope, 1, additive_project_identity_foundation)`.

The backup was verified to logically equal the closed live store across
incumbent identities, publication evidence, and the full `sqlite_master` object
set before any migration was attempted.

## Rehearsal on a disposable copy of that exact backup

All twelve checks passed, `[2]` then `[]`, and the live store was re-verified as
untouched afterwards. The disposable directory was removed
(`temporary_items_remaining = 0`).

Both reviewed object hashes reproduced exactly:

- adjudication table SHA-256 `b72af7e92f31e8fcf4ecb95675ddf5354b2c6a93c95041766442afe266f8bac9`;
- adjudication index SHA-256 `cf39f40cac9a8b0a29d0b3915058b066d68d4df24127ccef57ddaca1c253e5e5`.

### Enumeration note

The preparation recorded new objects as exactly the adjudication table and its
named index. A raw `sqlite_master` diff also surfaces three
`sqlite_autoindex_project_scope_adjudications_*` entries. These are not extra
unreviewed objects: SQLite materializes one implicit index per `PRIMARY KEY` or
`UNIQUE` clause, and each was matched back to a constraint declared in the
reviewed table SQL rather than exempted by name. The verified index shape is:

- `pk` on `(adjudication_id)`;
- `u` on `(record_kind, record_id)`;
- `u` on `(project_id, record_kind, record_id, idempotency_key)`;
- `c` on `(project_id, created_at)` - the reviewed named index.

## Live application

- first `ProjectScopeStore.init_db()` returned `[2]`;
- second returned `[]`;
- ProjectScope markers after: `(1, additive_project_identity_foundation)` and
  `(2, quarantine_adjudication_path)`;
- only the reviewed table and named index were added, plus the three constraint
  indexes above; no existing SQLite object changed or was removed;
- `request_hash` present and constrained to `length(request_hash) = 64`;
- adjudication table empty; every scope data table empty;
- settings remained `[0, 0]`;
- run/task counts, both stable ID hashes, and the publication projection hash
  were identical to the fresh backup;
- integrity `ok`; foreign-key violations `0`.

## Restart and convergence

Soma was restarted from current source with `-Action start` (PID `32476`).

- capability identity `converged: true` with `mismatches: []`;
- running build advanced `1b7a0021933e...` -> `198835df5c9c...`;
- capability epoch `198835df5c9c-42bdb69d96fb`;
- operation inventory `212` -> `214`, the two new quarantine operations;
- task capabilities report ProjectScope `schema_version 2`, `target 2`,
  `up_to_date: true`, `missing_tables: []`, `project_scope_adjudications`
  present, `scoped_writes_enabled: false`, `enforcement_state: inactive`.

## Quarantine surface probe

`task_query` operation `quarantine` was called with an explicit nonexistent
project ID and no fixture was created. It returned `ok: true` with zero records.

The preparation predicted this would "fail safely because no project exists".
The surface is a project-filtered list query, so the safe outcome is an empty
result rather than an error. `ProjectScopeStore.list_quarantine` first calls
`_require_adjudication_schema()`, so the successful call is direct positive
evidence that the v2 table is present and load-bearing on the live store. After
the probe, every scope data table was re-confirmed at zero rows and settings
remained `[0, 0]`.

## Post-activation state

```
ProjectScope schema: 2
Runtime target:      2
Adjudications table: present and empty
Scoped writes:       disabled
Enforcement:         inactive
Projects/bindings:   empty
Push:                none
```

## Rollback position

No post-backup durable run/task/evidence mutation was required, and the
migration is additive. The verified pre-activation backup above remains the
restore point. Per the prepared rollback boundary, `project_scope_adjudications`
must never be dropped automatically, and any future restoration must first
compare durable identities against that backup.

## Next decision

Gate C remains blocked and unauthorized. It now requires a fresh exact-identity
preview followed by explicit, separate Gate C approval.
