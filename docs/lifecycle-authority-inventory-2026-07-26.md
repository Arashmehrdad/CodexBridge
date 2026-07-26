# Lifecycle Authority Inventory

**Date:** 2026-07-26
**Lane:** STABILIZE-1, outcome 6
**Status:** Inventory and recommendation. **Not** authorization to consolidate.

## Purpose and scope

`PLANS.md` outcome 6 asks for an evidence-grounded map of the current lifecycle
authorities, where ownership overlaps, and what must remain compatible — as
input to Roadmap V3, explicitly *not* as permission for a consolidation
refactor inside STABILIZE-1.

Everything below was read from the live repository on 2026-07-26. No source
file was modified while producing it. Where a claim is an inference rather than
a direct reading, it is marked **[inference]**.

---

## 1. The authorities

Nine subsystems make lifecycle decisions. They are not peers: they differ in
whether they persist state, whether they can recover, and whether anything can
cancel them.

| # | Authority | Primary modules | Persistent state | Recovers on restart | Cancellable |
|---|---|---|---|---|---|
| 1 | Durable runs | `run_store.py`, `job_manager.py`, `job_worker.py` | `runs`, `events` | yes | yes |
| 2 | Canonical tasks | `tasks/{store,manager,models,backends,schema,projections}.py` | `tasks`, `task_links`, `task_commands`, `task_checkpoints`, `task_events` | yes | yes (`cancel` only) |
| 3 | Workflows | `workflows/{store,manager,worker,publication,reporter}.py` | `workflows`, `workflow_steps`, `workflow_events` | yes | yes |
| 4 | Supervisors | `supervisor_{store,engine,service,notifications}.py`, `supervisor/` | `supervisors`, `supervisor_events`, `supervisor_run_links`, `supervisor_notifications` | partial **[inference]** | yes |
| 5 | Command / parallel groups | `parallel_groups.py` | `command_groups`, `command_group_children` | via run refill | yes (`cancel_powershell_group`) |
| 6 | Long-run jobs | `jobs/long_run_manager.py` | delegates to a job store | unclear **[inference]** | not directly |
| 7 | Hermes service | `hermes_service*.py`, `hermes_concurrency.py` | state file on disk | adopt-or-replace | yes |
| 8 | SSH activation | `ssh_activation.py`, `ssh_watchdog.py` | config + runs dir | yes (coordinator loop) | n/a |
| 9 | Local coding | `local_coding/local_coding_manager.py` | **files only** — no SQLite | no **[inference]** | no |

### Operation-lock service

`operation_locks.py` is not a lifecycle owner but is a shared dependency of
several. It owns the `operation_locks` table and is the single resource-lease
authority. This one is correctly centralised and should stay that way.

---

## 2. Where authority actually overlaps

### 2.1 Three terminal-state vocabularies that do not agree

| Authority | Terminal states |
|---|---|
| Runs (`run_store.py:25`) | `completed`, `partial`, `failed`, `cancelled`, `timed_out`, **`needs_input`** |
| Workflows (`workflows/manager.py:29`) | `COMPLETED`, `FAILED`, `CANCELLED`, **`NEEDS_APPROVAL`**, **`NEEDS_INPUT`**, `REPORTED` |
| Tasks (`tasks/models.py:56`) | `completed`, `failed`, `cancelled` |

Two consequences.

First, runs and workflows treat *waiting for a human* as **terminal**, while
the canonical task plane models it as the non-terminal `awaiting_controller`.
These are incompatible models of the same situation, and the accepted
architecture is the task one.

Second, `NEEDS_APPROVAL` is live approval machinery in the workflow terminal
set. The accepted owner decision retires approval as an execution gate, and the
task plane already has no approval state. This is the clearest example of an
authority encoding a superseded decision.

### 2.2 Runs are the only backend the task plane can adopt

`tasks/backends.py` defines an `ExecutionBackend` protocol
(`reserve`/`start`/`query`/`cancel`/`result_reference`) with exactly one
implementation: `DurableRunBackend`. `TaskLinkTargetKind` has exactly two
members — `TASK` and `DURABLE_RUN`.

So workflows, supervisors, command groups, long-run jobs, Hermes sessions, and
SSH work **cannot currently be represented as tasks at all**. The canonical
plane is real but covers one of nine authorities.

`TaskCommandKind` likewise has a single member, `CANCEL`. `steer`, `input`,
`pause`, `resume`, and `retry` are specified in the roadmap and not
implemented.

### 2.3 Two independent lease implementations

Lease/generation logic appears in `run_store.py` (68 references) and
`workflows/store.py` (98 references) as separate implementations of the same
compare-and-set concept. Supervisors and tasks have none of their own and
depend on whichever authority underlies them **[inference]**.

The roadmap's stated principle is one authoritative lease model. There are two,
and the larger one is in workflows.

### 2.4 Two result-publication paths

`run_publication.py` + `run_public_result.py` publish run results;
`workflows/publication.py` publishes workflow results. Both implement
terminal-publication semantics. Outcome 1 of this lane had to teach
`run_public_result.py` about the compact evidence shape; the workflow path was
not affected and was not updated, so the two can drift the same way the
tool-owned path definitions drifted.

### 2.5 `recovery_pending` is set by five modules

`job_manager.py` (10 references), `workflows/manager.py` (7),
`tasks/manager.py` (5), `workflows/worker.py` (4), `workflows/store.py` (4),
`run_store.py` (4), `parallel_groups.py` (2). The *concept* is consistent; the
implementations are independent. Nothing aggregates them into one answer to
"what is currently stuck?" **[inference]**

### 2.6 Schema ownership escapes the stores

Nine modules create tables. Two of them are not stores and reach into another
store's connection and its private helper:

- `operation_locks.py` — `self.store.connect()`, `self.store._ensure_column(...)` at lines 55, 61, 67
- `parallel_groups.py` — inline `CREATE TABLE` for `command_groups` and `command_group_children`, plus `self.store._ensure_column(...)`

Calling a private method across a module boundary means the run store cannot
change its migration mechanism without silently breaking two callers.

Two modules added during this lane, `reconciliation_status.py` and
`evidence_backfill.py`, also create their own tables. That was deliberate and
is noted here for completeness rather than defended: they are maintenance and
observability tables, not lifecycle state, but they do add to the count.

### 2.7 One authority persists nothing durable

`local_coding/local_coding_manager.py` writes `proposal.json`, `preview.diff`,
`preview.md`, `policy_result.json`, `approval_request.json`, and
`original_snapshot.txt` into a run directory via `atomic_write_*`. There is no
SQLite state, so it cannot be queried, reconciled, or recovered like the
others, and it still references `policy_engine.approval_store` — retired
approval machinery.

### 2.8 Startup reconciliation is five call sites, not one contract

Fixed for *visibility* in this lane (`7665f32`), but the structure remains:
`reconcile_startup` in `job_manager.py`, `workflows/manager.py`, and
`tasks/manager.py`; `_reconcile_previous_state` in
`hermes_service_supervisor.py`; `reconcile_pending_ssh_activations` in
`ssh_activation.py`. Five different names and signatures for one concept.

---

## 3. What must remain compatible

Anything Roadmap V3 does has to preserve these. They are load-bearing for the
connected ChatGPT client or for historical evidence.

1. **The public gateway operation names and schemas.** `run_query`,
   `run_start`, `task_query`, `task_action`, `workflow_query`,
   `workflow_action`, `supervisor_query`, `supervisor_action`, `ssh_query`,
   `ssh_action`, `ssh_inspect`, `repo_*`, `system_*`. The connector depends on
   these.
2. **Run IDs and the `RUN_ID_PATTERN`** (`run_store.py:24`). Opaque identity
   that appears in evidence, artifacts, and run directories.
3. **`LEGACY_READ_ONLY_TOOLS`** (`run_store.py:36`) — `codex_plan_task` and
   `codex_implement_task` records stay readable while no new instances can be
   created. Any consolidation must keep reading them.
4. **Evidence hashes and the compact/authoritative split**, including the
   `commit_evidence_ref` shape introduced by `3f8f529` and backfilled by
   `03d293e` across 256 rows.
5. **`public_result_source_sha256` as a cache-validity key**, not a seal.
   Rewriting `result_json` correctly invalidates the projection and triggers
   lazy re-materialization. This is what made the backfill safe.
6. **The `soma_schema_migrations` chain** and ordered transactional migrations.
7. **Existing terminal values in stored rows.** Even after the vocabularies are
   unified, historical `needs_input` and `NEEDS_APPROVAL` rows must remain
   readable.

---

## 4. Dead and superseded code found while mapping

Recorded because it is cheap to find now and expensive to rediscover later.
None of it was changed.

| Finding | Location | Note |
|---|---|---|
| `wiki_exclusions` constructor argument is never passed by any call site | `repo_wiki.py:164` | Every construction is `RepoWikiService(repo_root, repo_name)`. The configuration path has always been dead; only hardcoded sets were ever effective. Found during outcome 5. |
| Approval machinery still referenced | `local_coding_manager.py:179`, `policy/approval_store.py` | Contradicts the accepted owner decision retiring approval gates |
| `NEEDS_APPROVAL` in the workflow terminal set | `workflows/manager.py:33` | Same |
| `soma/codex_router/` contains only `__pycache__` | — | No source; stale artifact directory |
| `local_agent/` general reasoning path | `local_agent/orchestrator.py` (731 LOC) | Roadmap marks unused local reasoning paths for retirement |

---

## 5. Recommendation for Roadmap V3

Ordered by ratio of risk removed to effort. This is a recommendation only.

**First — unify the state vocabulary, not the code.** Map runs and workflows
onto the task states, with `needs_input` and `NEEDS_INPUT` becoming
`awaiting_controller` and `NEEDS_APPROVAL` becoming a compatibility-only read
mapping. This removes the contradiction without moving any execution logic, and
it is a precondition for anything else.

**Second — widen the task plane before retiring anything.** Add backends and
`TaskLinkTargetKind` members for workflows and supervisors so more than one of
nine authorities is representable. The `ExecutionBackend` protocol already
exists and only needs implementations. Until this lands, "one canonical task
plane" describes one execution type.

**Third — give startup reconciliation one contract.** The durable status
surface from `7665f32` already exists; the five call sites can adopt a shared
signature behind it without changing what each one does internally.

**Fourth — return schema ownership to the stores.** Give `RunStore` a public
migration helper so `operation_locks.py` and `parallel_groups.py` stop calling
`_ensure_column`. Small, mechanical, removes a real coupling.

**Fifth — decide `local_coding`'s fate explicitly.** It is a lifecycle
authority with no durable state that still depends on retired approval
machinery. Either give it durable state or retire it; leaving it is the worst
option.

**Explicitly not recommended now:** merging the two lease implementations or
the two publication paths. Both are correct in isolation, both are heavily
covered by tests, and merging them touches the recovery paths that make Soma
worth keeping. They should follow the task plane widening, not precede it.

---

## 6. Method and limits

Read from the live tree on 2026-07-26 via targeted reads of the modules named
above, table-creation and state-vocabulary greps across `soma/`, and the public
operation inventory in `cf1_gateway_operation_inventory.py`.

Limits worth stating:

- Recovery behaviour for supervisors, long-run jobs, and `local_coding` was
  inferred from structure, not from executing restart scenarios. Those three
  rows are the least reliable in the table.
- No runtime tracing was performed. Overlaps are established from code and
  schema, not from observed concurrent execution.
- The `runs` and `command_groups` row counts in the live store were not
  re-surveyed for this document; outcome 3 measured them and they have since
  changed.
