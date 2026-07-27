# SCOPE-FOUNDATION-1 Gate A — Independent Review

**Date:** 2026-07-27
**Subject:** commit `e306d5c9ef0826967c28b63db465b64c1dc0efa2`, "Implement SCOPE-FOUNDATION-1 Gate A"
**Reviewer:** Claude controller, connected directly to Soma MCP.
**Status:** reviewed. Gate A implementation is sound. Three items are referred to
the owner for ratification before Gate B.

**Scope of this record:** a review only. It authorizes no push, no live schema
activation, no bootstrap, and no server restart.

---

## 1. Verdict

The commit does what the lane authorized and does not do what the lane
excluded. Every validation figure in the implementation handover reproduced
independently. The implementation is accepted as reviewed; closure of the
controller-evidence requirement is addressed in §4.

## 2. Independently reproduced validation

| Check | Reported | Reproduced |
|---|---|---|
| Full suite | 2055 passed, 35 skipped | **2055 passed, 35 skipped**, 368.64s, exit 0 |
| Gate A tests | 19 passed | **19 passed** |
| Ruff check, changed files | passed | **passed** |

## 3. Structural findings

### 3.1 The migration cannot touch an incumbent table

The rehearsal evidence (4,677 runs and 2 tasks retaining identical ID hashes on
a disposable copy) is corroboration. The stronger guarantee is structural, and
was obtained by parsing the migration rather than running it.

`_MIGRATION_0001` contains **11 `CREATE` statements and 1 `INSERT`**, and zero
`ALTER`, `DROP`, `UPDATE`, or `DELETE`. Every object named is new:

```
idx_project_attempt_task, idx_project_repository_locator,
project_repository_bindings, project_resource_bindings, project_resources,
project_run_attempts, project_scope_bootstrap_events, project_scope_quarantine,
project_scope_settings, project_task_reservations, projects
```

An additive-only migration cannot corrupt what it never addresses. This holds
regardless of which store it is applied to, which a single rehearsal cannot
establish.

### 3.2 Gate A is dormant on the live store

Verified read-only against `runs/soma.sqlite3`:

- `soma_schema_migrations` holds exactly one row, `canonical_task_plane` v1.
- Zero tables matching `project%`.
- `ProjectScopeStore.is_installed()` is therefore false, so `connect()` — and
  its `PRAGMA journal_mode = WAL` — is never reached during startup
  reconciliation. The new `PATH_PROJECT_SCOPE` startup path returns
  `available: false` and records a healthy no-op.

The running server is build `31fb4407965b880a…`; the Gate A tree is
`1b7a0021933e0e79…`. The live `capability_identity` already reports
`mismatches: ["source_running_server_build_hash"]`, which is exactly this
divergence and is self-consistent with an unrestarted server.

### 3.3 Correction to the handover's live-store measurement

The handover states the live database "remained unchanged at 130,039,808 bytes
with timestamp 2026-07-27 00:18:42 UTC". At review time it measured
**130,256,896 bytes, 2026-07-27 12:03:36 UTC**.

The claim was true when taken. The change is ordinary traffic from the running
server, including this review's own read-only MCP calls, and is not attributable
to Gate A — the schema check in §3.2 was re-run afterwards and still found zero
`project%` tables. The figure should not be carried forward as a standing
invariant; §3.1 and §3.2 are the durable statements.

## 4. Controller evidence (invariant 7)

Invariant 7 requires that current Claude and Codex controllers can use both
incumbent and scoped MCP payloads **directly against Soma**. The implementation
lane's two Claude attempts failed inside a CLI subprocess before reaching model
or tool execution, and the retry allowance was reported exhausted.

A CLI subprocess is not what invariant 7 describes, and
[`pilot-openclaw-1-evidence-2026-07-27.md`](pilot-openclaw-1-evidence-2026-07-27.md)
Finding 3 already established that both controllers reach Soma's MCP endpoint
directly. The evidence was obtained on that route instead, consuming no retry
allowance.

### 4.1 Incumbent half — satisfied live

Three live calls against the running server, over the same loopback
streamable-http endpoint, all successful:

| Call | Evidence |
|---|---|
| `system_query(capability_identity)` | returned running build/schema/epoch identities |
| `task_query(capabilities)` | `canonical_task_plane` v1, all five tables present |
| `run_query(summary_list, limit=3)` | live runs, `snapshot_watermark: 4677` |

The watermark independently matches the 4,677 runs counted in the
implementation lane's disposable rehearsal.

### 4.2 Scoped half — satisfied at the tool boundary, not on the wire

The running server cannot accept a scoped payload: it predates the commit and
advertises `task_query` and `run_query` without `project_id`. Proving the scoped
half against the live endpoint would require restarting the server on
`e306d5c`, which is outside Gate A.

The gap was instead closed on a **disposable store** — explicitly authorized by
the lane — by driving the real MCP tool objects with raw controller payloads.
This is a level the existing Gate A tests do not reach: they assert on the
advertised JSON schema, and they call `server.run_query(Model(...))` with an
already-constructed pydantic object. Neither exercises a raw dict passing
through the flat-input wrapper and discriminated-union validation, which is what
a controller actually sends.

Seven checks, all passing:

1. Scoped `task_query status` accepted over a raw flat payload;
   `project_binding_status: attached`.
2. Flat and legacy `{"request": {...}}` wrapped scoped payloads produce
   byte-identical responses.
3. Cross-project `task_query` fails closed with `project_scope_mismatch` and
   discloses neither `task_kind` nor `backend_reference`.
4. Incumbent `task_query status` with no `project_id` is unchanged.
5. Scoped `run_query status` accepted; cross-project denied with
   `project_scope_mismatch`.
6. An unknown project on `task_action start` fails closed with
   `project_scope_resolution_failed` and **no backend launch**.
7. An unknown extra field is still rejected — strict schemas survive the
   additive change.

**What remains unproven** is only the network transport of a scoped payload,
which is byte-identical in mechanism to the incumbent transport exercised in
§4.1. The recommendation is to fold the scoped live pass into Gate B, where a
restart occurs regardless, rather than spend a retry allowance on the CLI route
that PILOT-OPENCLAW-1 rejected.

## 5. Referred to the owner for ratification before Gate B

These are not defects against Gate A. They are semantics that Gate A leaves
inert and Gate B would activate, and each deserves an explicit decision rather
than inheritance by default.

### 5.1 Project-less callers reach more than invariant 6 authorizes

Invariant 6 permits owner-controller exact-ID reads **"for legacy unscoped
records"**. The implementation is broader: a caller omitting `project_id`
replays a *scoped* task, receives its `task_id`, and is told its `project_id`.
This is deliberate and asserted at
[`test_project_scope_foundation.py:817`](../tests/test_project_scope_foundation.py:817).

The resulting asymmetry should be stated plainly:

- **Writes are fail-closed.** Under enforcement, an omitted `project_id`
  resolves to exactly one active binding or errors as ambiguous.
- **Reads are fail-closed only for callers who declare a project.** An omitted
  `project_id` remains a master key on exact IDs, including for scoped records.

Gate A therefore delivers the isolation *seam* and the scope *authority*. It
does not yet deliver an isolation *guarantee* against an undeclared caller.

### 5.2 Quarantine is one-way

No code path leaves `quarantined`. `attach_attempt` moves only from `reserved`
or `recovery_pending`, and `require_task_attempt` excludes quarantined attempts.
A quarantined task becomes permanently unreadable and unstartable by a scoped
caller, recoverable only by manual SQL. Inert while dormant; an operator remedy
is needed before enforcement.

### 5.3 `UNIQUE(task_id)` forecloses a second attempt

`project_run_attempts` carries `UNIQUE(task_id)`, so a task can hold at most one
attempt row. This is consistent with today's 1:1 task-to-run model and with the
single reservation site in `TaskManager.start_durable_command`. But the table
name and the `recovery_pending` state both imply eventual multi-attempt
semantics, which would require a further migration.

### 5.4 Minor

- `project_binding_status` is now emitted on **every** task projection,
  defaulting to `legacy_unassigned` for unscoped records. Additive, but
  consumers pinning field sets will observe it. CF1 `schema_hash` is unaffected;
  it hashes only `PATCH_OPERATION_SCHEMA`.
- `run_query` with a `project_id` fails closed on `summary_list` and the
  `group_*` operations, which carry no `run_id`. Safe, but there is no scoped
  list operation.
- A restart on `e306d5c` will change `server_build_hash`, `capability_epoch`,
  `public_schema_hash`, `live_input_schema_hash`, and
  `discovery_cache_generation`, because the input schemas gained `project_id`.
  Consumers pinning those values should expect a mismatch on the Gate B restart.
- `reconcile_startup` joins `tasks` and `runs` unguarded. Harmless on any store
  that has the incumbent plane, which is every store that reaches it today.

## 6. Lane compliance

| Requirement | State |
|---|---|
| Work committed locally, not pushed | held — **three** commits are unpushed: `224ad11`, `15de7ad`, `e306d5c` |
| Gate B live schema activation | not performed |
| Gate C project/repository bootstrap | not performed |
| Historical disposition | not performed; no historical record written |
| Memory, Hermes, other run producers | untouched |
| Tests against fresh/disposable stores only | held — §4.2 used a temporary directory |
