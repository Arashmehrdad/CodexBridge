# TASK-1 — Canonical Task Plane Foundation

Status: **complete; implementation, focused and full-suite validation, static gates, isolated source startup, controlled live restart, and live task-backed acceptance closed on 2026-07-25**.

This document records the contracts, compatibility guarantees, migration boundaries, and acceptance evidence for the first bounded batch of roadmap Phase 1. It is an evidence record, not an owner decision document.

---

## 1. What was added

One controller-neutral canonical task identity above Soma's existing durable execution engine, as an additive compatibility layer.

```text
canonical task
  -> references one selected execution backend
  -> maps to an existing durable run
  -> reuses the existing worker, lease, cancellation, evidence, result, and recovery systems
```

No second execution engine, worker, lease, lock, evidence store, result authority, scheduler, or repository authority was created. No legacy run, workflow, supervisor, or domain system was deleted or broadly refactored.

New source:

| File | Responsibility |
| --- | --- |
| `soma/tasks/models.py` | typed task models, controller-neutral state vocabulary, request normalization and hashing, backend-status mapping |
| `soma/tasks/schema.py` | ordered transactional migrations and schema-state reporting |
| `soma/tasks/store.py` | canonical task identity, typed links, commands, checkpoints, events; compare-and-set updates |
| `soma/tasks/backends.py` | execution-backend contract plus the first, default durable-run backend adapter |
| `soma/tasks/manager.py` | idempotent creation, version-guarded cancellation, restart-safe reconciliation |
| `soma/tasks/projections.py` | compact public projections that reference existing evidence |

Public surface: `task_query` and `task_action` in `soma/server.py`, taking the public gateway count from 30 to 32.

---

## 2. Canonical task versus backend-run authority

The single most important boundary in this batch.

| Concern | Authority | Notes |
| --- | --- | --- |
| Canonical public task identity | `soma/tasks/store.py` (`tasks`) | opaque `task_id`, never lowercased or normalized before lookup |
| Typed relationships | `task_links` | `parent`, `child`, `backend_run`, `related`, `supersedes` |
| Task commands | `task_commands` | every command records requested and observed state versions |
| Controller checkpoints | `task_checkpoints` | schema present; not exercised by this batch |
| Task lifecycle events | `task_events` | durable evidence for reconciliation decisions and failures |
| Worker, process, PID, lease, lock lifecycle | existing durable run store | unchanged |
| Cancellation ownership and process-tree termination | existing durable run engine | unchanged |
| Result body, result publication, result hashes | existing durable run store | unchanged |
| Protected artifacts, stdout, stderr, durable input | existing run evidence | unchanged |

The canonical task stores *references*, never copies:

- `backend_ref` — the authoritative `run_id`;
- `objective_ref` and `constraints_ref` — `run_input:<run_id>`;
- `result_ref` — the authoritative `run_id`;
- `result_hash` — the run's own `result_published_hash`;
- `evidence_ref` — `run_terminal:<run_id>`.

`task_query.result` reports `result_authority: "durable_run"` and `result_duplicated_into_task: false`, and carries the run's `public_result_source_sha256`, `public_result_status`, `result_publication_status`, `result_published_hash`, and `result_published_at`. It contains no `result`, `stdout`, or `stderr` field.

---

## 3. Schema and migration

Component `canonical_task_plane`, schema version **1**, recorded in `soma_schema_migrations (component, version, name, applied_at)`.

Tables added to the existing `runs/soma.sqlite3` database: `tasks`, `task_links`, `task_commands`, `task_checkpoints`, `task_events`.

Migration properties:

- each migration runs in its own `BEGIN IMMEDIATE` transaction on a dedicated connection and rolls back completely on failure;
- migrations are applied in ascending order and recorded, so a restart never re-applies one;
- no existing table is altered, rewritten, dropped, or backfilled;
- a fresh database and an existing run database converge on the same schema;
- `tasks.controller_request_id` carries a unique index (top-level idempotency);
- `tasks(backend_kind, backend_ref)` carries a partial unique index for non-empty references, so one durable run can never be owned by two canonical tasks.

Rollback boundary: the migration is additive, so reverting the code leaves five unused tables and one migration row behind. Nothing in the legacy run, workflow, or supervisor path reads them, so a code rollback needs no data rollback. Dropping the tables is safe but discards canonical task identity, so it is not automated.

---

## 4. State and command contracts

Complete controller-neutral state vocabulary:

```text
accepted
queued
running
awaiting_controller
paused
cancellation_pending
recovery_pending
completed
failed
cancelled
uncertain
```

There is no approval state, no permission tier, no autonomy gate, no confirmation phrase, and no controller-specific value. `awaiting_chatgpt`, `needs_approval`, and `needs_chatgpt_approval` are absent from the model and asserted absent by test.

Terminal task states are `completed`, `failed`, and `cancelled`.

Durable run status maps to task state conservatively:

| Backend run status | Task state |
| --- | --- |
| `launch_pending`, `queued` | `queued` |
| `running` | `running` |
| `cancellation_pending` | `cancellation_pending` |
| `recovery_pending` | `recovery_pending` |
| `completed` | `completed` |
| `partial` | `completed` (finished, not asserted successful; the outcome stays in the referenced run result) |
| `timed_out`, `failed` | `failed` |
| `cancelled` | `cancelled` |
| `needs_input` | `awaiting_controller` |
| anything unmapped | `uncertain` |

`task_action` operations:

- `start` — one canonical task backed by the durable local command engine;
- `cancel` — the one version-guarded command in this batch.

`task_query` operations: `capabilities`, `status`, `result`, `events`, `links`.

Cancellation contract:

- `if_state_version` is required;
- a matching version delegates to the existing run engine, which owns the process tree;
- a stale version is rejected with `error_code: "stale_state_version"` plus the current state version, and a `rejected_stale_version` command row is recorded; the backend is never signalled;
- the task reports `cancellation_pending` while the worker still owns termination, and only reports `cancelled` once the run row is `cancelled`;
- a repeated cancellation of a terminal task returns `already_terminal: true` and does not signal the backend, so no unrelated process can be targeted;
- if the backend run record is absent, cancellation is refused with `backend_run_not_found` and no cancellation is claimed.

---

## 5. Idempotency

Top-level keys: `controller_request_id` plus a normalized request hash.

- same request ID and same normalized request → the existing task is returned with `created: false`, `idempotent_replay: true`, and nothing is launched;
- same request ID and a different normalized request → `controller_request_hash_conflict` reporting both hashes;
- concurrent duplicates → one `BEGIN IMMEDIATE` reservation wins; losers read the winner's task and never call the backend;
- restart or retry → the durable run identity was reserved *before* the task row was committed and is owned by that task, so a second backend run cannot be created.

The normalized form deliberately excludes the controller request ID (it answers "is this the same request?", not "who asked?"), and normalizes stdin to a content-identity descriptor so `stdin_text` and an equivalent `stdin_base64` hash identically.

Secret containment: the task row stores only the 64-character hash. `argv`, `environment`, and stdin never reach `tasks`, `task_events`, or any public task projection; they remain in the existing durable run input record with its established protection and redaction.

---

## 6. Compact query examples

```powershell
# start
# task_action
#   {"operation":"start","controller_request_id":"my-request-1","repo_name":"soma",
#    "profile_id":"powershell","working_directory":"D:/Github/Soma",
#    "argv":["-NoProfile","-Command","Write-Output ok"],"timeout_seconds":120}

# poll
# task_query {"operation":"status","task_id":"task_..."}

# compact result reference
# task_query {"operation":"result","task_id":"task_..."}

# authoritative evidence, unchanged legacy path
# run_query {"operation":"terminal","run_id":"<backend_reference>"}

# version-guarded cancellation
# task_action {"operation":"cancel","task_id":"task_...","if_state_version":3}
```

Default responses are compact and include `task_id`, `state`, `phase`, `state_version`, `task_kind`, `backend_kind`, `backend_executor`, `backend_reference`, `backend_status`, parent identity, `created_at`/`started_at`/`ended_at`/`reconciled_at`, a checkpoint summary, link counts, retrieval requests for the task result and the authoritative run evidence, and the standard CF1 envelope plus `server_build_hash`, `schema_hash`, and `capability_epoch`.

Measured live response sizes against a 12 KiB budget: `status` 2,177 bytes; `result` 2,534 bytes; `capabilities` 1,779 bytes.

---

## 7. Compatibility guarantees

Proven by test and by live acceptance:

- `run_start` behaviour is unchanged; the durable local start path is delegated to, never forked;
- `run_query` status, output, result, terminal, events, cancellation, evidence, and recovery behaviour is unchanged;
- `cancel_run` is unchanged;
- no existing run record requires a destructive migration;
- legacy runs remain fully readable and simply have no canonical task;
- a new task-backed run is representable without changing any direct legacy caller;
- the gateway count, operation inventory (`cf1.3.gateway-operations.v11`), schema hashes, MCP `content[].text` transport, flat argument-root transport, compact projections, and discovery caches were all updated consistently.

No historical run database backfill was performed, and no persistent task identity was invented for an old record.

---

## 8. Restart-safe reconciliation

Reconciliation reuses the existing startup reconciliation pattern and adds no background lifecycle engine. `TaskManager.reconcile_startup()` is called at server startup next to the existing run and workflow reconcilers.

Cases handled:

| Case | Outcome |
| --- | --- |
| task exists and backend run exists | task projection adopts the backend status |
| task exists but backend launch did not complete | `recovery_pending`, reason `backend_launch_incomplete` |
| backend run completed while the task projection was stale | terminal state plus published result linkage |
| server restarted while the backend worker is active | running task adopted, `recovery_state: none` |
| backend cancellation pending | `cancellation_pending`, no cancellation claimed |
| terminal backend result exists but result linkage was unpublished | linkage repaired to the run id, hash, and evidence reference |
| duplicate reconciler execution | unchanged projection performs no write; a losing compare-and-set re-reads rather than overwrites |
| missing backend record for a started task | `uncertain`, reason `backend_run_record_missing` |
| backend identity mismatch | `uncertain`, reason `backend_identity_mismatch` |
| reconciliation raised | durable `startup_recovery` error event, reported in the summary, never silently swallowed |

Reconciliation never guesses and never invents success.

---

## 9. Validation evidence

### Static gates

| Gate | Result |
| --- | --- |
| `python -m ruff check soma tests` | All checks passed |
| `python -m compileall -q soma tests` | clean |
| `python -m pip check` | No broken requirements found |
| `git diff --check` | clean |

### Focused suites

| Suite | Result |
| --- | --- |
| `tests/test_canonical_task_plane.py` | 41 passed |
| gateway contract suites (`test_public_gateway_inventory`, `test_cf1_gateway_operation_inventory`, `test_mcp_flat_input_contract`, `test_transport_content_text_gate`) | 203 passed, 26 skipped |
| `tests/test_mcp_action_discovery.py` | 28 passed |
| adjacent compatibility (`test_run_store`, `test_job_manager`, `test_run_public_projections`, `test_public_result_gateway`, `test_workflow_durability`, `test_supervisor_store`, `test_server`) | 188 passed |

### Complete suite

`python -m pytest -q` → **1917 passed, 35 skipped** in 335.62s (baseline before this batch: 1864 passed, 35 skipped).

### Isolated source server

Source server started on a free port with a temporary config and temporary runs directory:

- `/health` returned `OK`;
- 32 tools advertised, including `task_query` and `task_action`;
- `task_query` operations `capabilities`, `events`, `links`, `result`, `status`;
- `task_action` operations `cancel`, `start`;
- `operation_inventory_gateway_count` 32, `operation_schema_count` 207, discovery passes converged;
- source build hash `3ca1a1abd9384901691c921e956c230a12fe007d091ff4945c198030d27e8a69`;
- an unknown `task_id` returned `error_code: "task_not_found"` rather than a fabricated projection.

### Controlled live restart and convergence

Restarted with the supported service controller (`scripts/manage_soma_service.ps1 restart`), which explicitly left the Cloudflare tunnel unchanged. The controller's 30-second readiness window expired while startup reconciliation was still running; the service became ready shortly afterwards and `status` reported ready. The venv launcher and its interpreter child are one logical server, confirmed by parent/child process identity.

Live convergence after restart:

| Identity | Value |
| --- | --- |
| `source_server_build_hash` | `3ca1a1abd9384901691c921e956c230a12fe007d091ff4945c198030d27e8a69` |
| `running_server_build_hash` | `3ca1a1abd9384901691c921e956c230a12fe007d091ff4945c198030d27e8a69` |
| `running_schema_hash` | `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888` |
| `capability_epoch` | `3ca1a1abd938-42bdb69d96fb` |
| `public_schema_hash` | `780dedc521c0e4e1724848826a270fe0b60618333229c9fee8ef9e2cf404efff` |
| `operation_inventory_hash` | `2673fe42d7722a70ab0e59688dc820c29e2953b8e4d16db0b71c5d5c85c615c9` |
| `discovery_cache_generation` | `26a733a2cd8bd53ea5d12688d1dcfee1e34ce5ebc60be42d8d47139998b09ad4` |
| `operation_inventory_gateway_count` | 32 |
| `converged` | true, no mismatches |

### Live task-backed acceptance

One harmless local command through the canonical task plane on the running service:

| Field | Value |
| --- | --- |
| canonical task | `task_20260725T114648Z_19cd9d57aaee` |
| backend run | `20260725T114648Z_executable_profile_e5186cdc` |
| accepted state | `queued` / `backend_launching`, `state_version` 1 |
| terminal state | `completed` / `result_published`, `state_version` 2 |
| `result_reference` | `20260725T114648Z_executable_profile_e5186cdc` |
| `result_hash` | `92e1ccd006aab3e653d38fec166060b6694234abb2178c371084a88364b9e7bb` |
| `evidence_reference` | `run_terminal:20260725T114648Z_executable_profile_e5186cdc` |
| task `public_result_source_sha256` | `010562473bea830d43ff1619e718cd9bf7135f7bded1160850fa751a5a56ae15` |
| `run_query.terminal` `source_result_sha256` | `010562473bea830d43ff1619e718cd9bf7135f7bded1160850fa751a5a56ae15` (identical) |
| task events | `reserved`, `backend_attachment`, `reconcile` |
| task links | `backend_run` → the run above, only |
| idempotent replay | same `task_id`, `created: false`, no second run |
| different-hash replay | `controller_request_hash_conflict` |
| stale cancel | `stale_state_version`, current version 2 |
| terminal cancel | `already_terminal: true`, no backend signal |
| legacy direct `run_start` | `20260725T114651Z_executable_profile_51d53385`, terminal `completed` |

Live version-guarded cancellation of a real process:

| Field | Value |
| --- | --- |
| canonical task | `task_20260725T114748Z_06a2add4ca6e` |
| backend run | `20260725T114748Z_executable_profile_df1c448b` |
| cancel at `state_version` | 3 |
| task state after cancel | `cancelled`, `cancellation_claimed: true` |
| backend cancellation | `termination_confirmed: true`, run status `cancelled` |
| task events | `reserved`, `backend_attachment`, `reconcile`, `cancel`, `cancel` |
| repeated cancel | `already_terminal: true`, no backend signal |
| operation locks afterwards | 0 |

All 19 live task-cycle checks and all 9 live cancellation checks passed.

---

## 10. What remains for Phase 2

Honest remaining limitations of this batch:

- only one execution backend is mapped: the durable local command (`executable_profile`) path. Workflow, supervisor, SSH, Hermes companion and service, remote PowerShell, command-group, and domain executions are not yet canonical tasks;
- only `cancel` is implemented as a version-guarded command. `steer`, `input`, `pause`, `resume`, and `retry` are not implemented, and `paused` and `awaiting_controller` are reachable in the model but not exercised by this backend beyond the `needs_input` mapping;
- `task_checkpoints` exists and is queryable through the checkpoint summary, but no checkpoint is created by this batch, so controller checkpoint round-trips remain future work;
- `recovery_pending` and `uncertain` are reported honestly but there is no automated repair command; recovery is currently an explicit controller decision;
- no historical run is represented as a canonical task, and no read adapter invents task identity for legacy records;
- the application container, one shared lease/lock migration, legacy permission removal, scheduler, browser, desktop, Temporal, memory sidecars, capability-broker migration, and worktrees remain out of scope, as does any legacy deletion.

Phase 2 selection remains an explicit owner decision.
