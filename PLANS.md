# CodexBridge Roadmap Status

## Executive Decision

The next development phase is **Durable Execution Recovery and Ownership**.

The workflow orchestrator, supervisors, direct async runs, return-loop artifacts, and dashboard are implemented foundations, but the latest audit found critical crash and restart windows. Feature expansion is paused until accepted work can be safely reconciled without duplicate execution, premature lock release, orphan children, or incorrect terminal reporting.

This is an execution-layer problem. The policy layer remains separate and should not be weakened to compensate for lifecycle defects.

## Completed Foundations

- Repository-scoped MCP read/write controls with capability metadata.
- SQLite-backed async run records through `JobManager` and `RunStore`.
- Supervisor planning/implementation flow with return-loop artifacts.
- Durable workflow models, persistence, worker, reporter, MCP tools, and dashboard visibility.
- Read-only local dashboard for runs, jobs, workflows, supervisors, approvals, escalations, and return-loop state.
- Structured events, results, output artifacts, operation locks, cancellation paths, and heartbeats.

These foundations are useful but are not proof of restart-safe execution.

## Current Batch: P0 Durable Execution Recovery and Ownership

Status: planned and ready for implementation.

### Audit Findings Driving This Batch

1. Startup reconciliation marks ordinary `running` runs failed without first verifying whether the detached worker or child is still active.
2. Stale-lock recovery can then release the repository lock while the original process continues.
3. The manager-stored worker PID can differ from the PID reported by the executing worker.
4. `queued` runs are not reconciled and can remain stranded after partial launch failure.
5. Workflow and supervisor child launches are split across multiple non-transactional writes, creating orphan/duplicate-child crash windows.
6. Workflow workers are relaunched without an atomic lease claim.
7. Supervisor and direct-run repository ownership use separate lock systems.
8. `LongRunJobManager` keeps live process ownership only in memory and cannot safely recover after manager recreation.
9. Database state, result artifacts, events, and delivery manifests can diverge across crashes.

## P0 Workstream A - Canonical Worker Identity and Leases

Goal: make process ownership verifiable rather than PID-only.

Deliverables:

- Worker registers its real PID in the canonical `worker_pid` field.
- Add a durable worker lease/ownership token generated before launch and presented by the worker.
- Persist process-start identity where available so PID reuse is detectable.
- Store launcher PID separately when a launcher/wrapper exists.
- Heartbeats update the canonical lease, not only a nested progress field.
- Control/status output distinguishes launcher, worker, and child identity.

Acceptance criteria:

- A live worker is not misidentified because the launcher PID exited or changed.
- A reused unrelated PID cannot satisfy ownership validation.
- Cancellation and reconciliation target the verified worker/child identities.

## P0 Workstream B - Process-Aware Startup Reconciliation

Goal: restart without converting active work into false failure.

Deliverables:

- Reconcile `queued`, `launch_pending`, `running`, and `cancellation_pending` runs.
- Adopt a verifiably active worker and refresh its lease.
- Relaunch an idempotently claimable queued run when no worker ever started.
- Move uncertain ownership to `recovery_pending` or an equivalent conservative state.
- Preserve repository locks whenever execution may still be active.
- Emit durable reconciliation events and expose failures; do not swallow exceptions.

Acceptance criteria:

- Restarting the MCP server while a worker is active does not mark the run failed.
- A dead worker with no live child reaches a deterministic infrastructure-failure result.
- A live child with a dead worker remains locked and recoverable/cancellable.
- A stranded queued run is relaunched once or terminated cleanly.

## P0 Workstream C - Transactional and Idempotent Launch Boundaries

Goal: make partial launches recoverable without duplicate work.

Deliverables:

- Add durable launch-intent/checkpoint state before `Popen` or child-run creation.
- Associate every launch with an idempotency key and lease generation.
- On launch failure, atomically record terminal infrastructure failure and release the owned lock.
- Add compare-and-swap/versioned transitions for claim, start, cancel, complete, timeout, and recovery.
- Ensure terminal database status and structured result are committed together.

Acceptance criteria:

- A crash before process creation does not strand a lock.
- A crash after process creation but before attachment does not create an orphan followed by a duplicate.
- Cancellation and completion races have one deterministic winner and preserve the other event as audit history.

## P0 Workstream D - Workflow and Supervisor Recovery

Goal: recover parent-child orchestration safely.

Deliverables:

- Workflow step states distinguish `pending`, `launch_pending`, `running`, and terminal states.
- Persist child launch intent before starting a child.
- Attach child IDs idempotently using the launch key.
- Recover a `running` or `launch_pending` step with no child ID.
- Add a single-worker workflow lease with atomic claim/renewal.
- Apply the same launch/attachment protocol to supervisor plan and implementation children.
- Add startup reconciliation for active supervisors and their implementation locks.

Acceptance criteria:

- No workflow step can spin forever as `running` without a child or recovery decision.
- Two reconcilers cannot launch two workers or children for the same workflow state.
- A supervisor crash after child launch resumes from the attached child rather than starting another.

## P0 Workstream E - Unified Repository Ownership

Goal: one authoritative lock and lease model for repository-changing execution.

Deliverables:

- Define a common repository ownership record for direct runs, workflows, and supervisors.
- Migrate or bridge `repo_write_locks` and `operation_locks` without opening an overlap window.
- Associate locks with run/supervisor/workflow lease generation.
- Make lock release conditional on current ownership.
- Keep conservative lock retention for monitored remote execution.

Acceptance criteria:

- Direct runs, supervisor implementation, and workflow writes cannot execute concurrently against the same repository unless explicitly permitted.
- A stale owner cannot release a lock acquired by a newer lease generation.

## P1 Workstream - Unified Durable Jobs and Audit Consistency

Begin only after P0 passes.

- Migrate `LongRunJobManager` workloads onto `JobManager`/`RunStore`, or add equivalent durable process adoption and reconciliation.
- Use atomic replacement for result/event snapshot artifacts.
- Preserve PulseSender `delivered` state during report regeneration.
- Add a durable reconciliation report visible in the dashboard.
- Define retention/repair tooling for inconsistent historical records.

## Required Validation Matrix

Targeted deterministic tests:

- active worker survives server restart
- worker death with live child
- `Popen` failure after run persistence
- queued worker dies before status transition
- workflow crash before child launch
- workflow crash after child launch before attachment
- concurrent workflow reconciliation
- cancellation versus completion race
- supervisor crash after plan launch
- supervisor crash after implementation launch and lock acquisition
- stale lease cannot complete or unlock a newer run
- long-job manager recreation
- delivered manifest regeneration

Real-process Windows integration tests:

- worker registers canonical PID/lease
- server process exits while detached worker continues
- reconciliation adopts or conservatively contains the worker
- verified process-tree cancellation releases the lock only after exit

Repository validation:

```powershell
python -m pytest -q
python -m pip check
```

## Implementation Batch Order

### Batch D1 - Worker identity and startup reconciliation

Status: **implemented and validated**.

Delivered:

- Persist `launch_pending` before worker process creation and record launcher PID separately from the canonical worker PID.
- Generate a per-run worker lease token before launch; require the worker to present that token before executing work.
- Register the executing worker's actual PID and process-start identity in canonical run fields.
- Scope worker heartbeats and repository-lock release to the current lease token.
- Reconcile `launch_pending`, `queued`, `running`, `cancellation_pending`, and `recovery_pending` records without treating server restart alone as run failure.
- Adopt a verifiably active worker, contain uncertain legacy records in `recovery_pending`, retain locks while execution may still be active, and fail a verified dead worker deterministically.
- Relaunch a stranded queued worker at most once, then fail it cleanly if bounded launch attempts are exhausted.
- Convert post-persistence process-launch failures into structured infrastructure failures and release only the matching owned lock.
- Record reconciliation exceptions as durable error events and move affected runs to `recovery_pending` rather than silently discarding the failure.
- Hide worker lease tokens from public run status and list responses.
- Add deterministic tests plus a real Windows process-start identity check.

Validation evidence:

- `tests/test_job_manager.py`: 35 passed.
- `tests/test_run_store.py`: 11 passed.
- Full repository suite: 879 passed, 1 skipped.
- `python -m pip check`: no broken requirements found.
- Live Windows workers registered canonical PID and process-start identity during validation runs.
- Live restart/adoption run `20260713T142018Z_project_command_41e46612` preserved worker PID `26696`, recorded the reconciliation event `Active worker identity verified after server restart`, retained the original repository lock while active, completed once with exit code `0`, and released the lock only after terminal persistence.
- The adopted worker completed the full suite with 879 passed and 1 skipped after the service restart.

Boundaries not yet claimed:

- The outer startup wrapper in `server.py` still catches reconciliation exceptions; per-run reconciliation failures are now durable, but service-level startup reporting remains a follow-up.
- Workflow launch and child attachment recovery were completed in D3; supervisor attachment recovery remains D4.
- D1 proves direct-run restart adoption for the tested Windows worker path; broader crash races and concurrent ownership transitions remain part of D2.

### Batch D2 - Conditional transitions and launch-state completion

Status: **implemented and validated**.

Delivered:

- Added durable `state_version` and `lease_generation` fields to direct-run records, with backward-compatible SQLite migration.
- Added a trusted-field conditional update primitive that supports expected status, state version, lease token, lease generation, and observed heartbeat predicates and verifies the affected-row count.
- Made worker claim single-winner and restricted it to the current `launch_pending` or `queued` execution generation.
- Scoped worker heartbeat, progress, child-PID attachment, completion, timeout, failure, and repository-lock release to the active lease token and generation.
- Made terminal status and structured `result_json` visible in one conditional database update and prevented stale or duplicate writers from overwriting terminal state.
- Made cancellation claim `cancellation_pending` before process termination, so cancellation versus completion has one deterministic database winner and unconfirmed termination retains the lock.
- Made startup adoption and recovery compare the observed state and heartbeat, so a fresh active-worker heartbeat defeats a stale recovery decision.
- Added an atomic relaunch reservation that rotates the lease token and generation and transfers repository-lock ownership in the same SQLite transaction.
- Prevented duplicate reconcilers from both adopting or relaunching the same run and rejected late claims from the replaced worker generation.
- Made operation-lock heartbeat and release return explicit success only for matching run, token, and generation ownership.
- Preserved D1 Windows worker identity and restart-adoption behaviour while keeping workflow and supervisor execution unchanged for D3 and D4.

Validation evidence:

- `tests/test_run_store.py`: 15 passed.
- `tests/test_operation_locks.py`: 11 passed.
- `tests/test_job_manager.py`: 39 passed.
- `tests/test_job_worker.py`: 17 passed.
- Full repository suite: 890 passed, 1 skipped.
- `python -m pip check`: no broken requirements found.
- Full-suite run `20260713T152727Z_project_command_3e56509b` completed through the hardened lease/version path with exit code `0` and terminal `state_version` `2`.
- Local Ollama health passed with configured model `qwen2.5-coder:7b`; the local health/inference timeout was increased to 120 seconds to cover cold model loading.

Boundaries not yet claimed:

- Workflow worker leases and crash-safe child attachment were completed in D3.
- Supervisor child attachment and shared lock unification remain D4.
- Human-readable result artifacts may still be written before a losing database terminal transition; the database remains authoritative, while atomic artifact reconciliation remains in the later return-loop consistency batch.

### Batch D3 - Workflow worker lease and child attachment

Status: **implemented and validated**.

Delivered guarantees:

- Workflow workers now use durable lease tokens, lease generations, state versions, recorded process identity, and bounded launch attempts.
- Initial workflow worker claims and restart relaunches use conditional transitions, preventing stale launchers or duplicate reconcilers from taking ownership.
- Workflow heartbeats, terminal transitions, step updates, and event writes are scoped to the active lease generation.
- Child run IDs are reserved before execution and attached atomically when a workflow step is claimed.
- Direct-run launch APIs accept the reserved run ID, closing the crash window where a child could start before the workflow recorded its identity.
- A stale workflow worker cannot update a step, clear a newer active child, complete a replacement generation, or overwrite a concurrent terminal transition.
- Workflow cancellation and terminal reporting use conditional durable state transitions rather than unconditional lifecycle writes.
- Existing direct-run D2 lease and lock behavior remains intact.

Validation evidence:

- Workflow-focused suite: `6 passed`.
- Workflow plus direct-run integration suite: `62 passed`.
- D2+D3 durability suite: `88 passed`.
- Full repository suite: `890 passed, 1 skipped`.
- `python -m pip check`: no broken requirements found.
- The repository worktree was clean after commit `477286c`.

Boundaries not yet claimed:

- Supervisor child attachment and shared repository lock unification remain D4.
- Legacy unattended-job migration and return-loop delivery-state consistency remain D5.
- Human-readable report artifacts can still be generated around a losing database transition; the database remains authoritative until D5 reconciles artifact publication state.

### Large `run_query` transport checkpoint

Status: **live validated**.

Validation evidence:

- A live `run_query list` snapshot contained `16,922,105` serialized characters and returned a bounded first chunk with `offset = 0`, `next_offset = 16384`, and `complete = false`.
- The returned v2 cursor advanced the same frozen snapshot to `offset = 16384` and `next_offset = 32768` with the same payload SHA-256 (`0bfa6c99f8173bad57711237f5495c0b9c4884e44139e77357e9dd16c4668d76`).
- The continuation returned no `cursor_stale` error after connector refresh and service restart.
- Validation stopped after the second chunk; the remaining payload was intentionally not retrieved.

### Batch D4 - Supervisor child attachment and lock unification

Status: **implemented and validated**.

Delivered guarantees:

- D4a added supervisor state versions, compare-and-swap lifecycle transitions, reserved child run IDs, durable pre-launch attachment, and restart adoption/relaunch using the same child identity.
- Supervisor plan and implementation completion, failure, cancellation, and terminal side effects now occur only after the matching supervisor state transition wins.
- D4b removed the separate supervisor `repo_write_locks` authority and migrates existing databases by dropping its legacy table and index during supervisor-store initialization.
- Supervisor implementation children now use the same authoritative `operation_locks` record as direct runs, with the child run ID and lease generation recorded in supervisor metadata.
- Repository contention is reported as a CAS-guarded `needs_input` state without launching a duplicate implementation child.
- Restarted supervisors retain the same implementation child identity and shared ownership metadata rather than creating a replacement child.
- Repository-lock release remains owned by the child run's token and lease generation; supervisors no longer perform an unconditional independent unlock.
- Existing stale-generation protection prevents an older owner from releasing a successor's repository lock.

Validation evidence:

- Supervisor store suite: `9 passed`.
- Supervisor engine suite: `29 passed`.
- Shared operation-lock suite: `11 passed`.
- Supervisor self-check suite: `4 passed`.
- Supervisor service suite: `12 passed`.
- Full repository suite: `901 passed, 1 skipped`.
- `python -m pip check`: no broken requirements found.
- D4b implementation checkpoints: `c0c7604`, `6a1ecad`, and `92f7706`.

Boundaries not yet claimed:

- Human-readable report artifacts can still be generated around a losing database transition; the database remains authoritative.
- Legacy long-job execution is contained in D5 rather than made restart-adoptable.

### Batch D5 - Legacy long-job containment and return-loop consistency

Status: **implemented and validated**.

Delivered guarantees:

- `LongRunJobManager` is disabled by default so new unattended work cannot enter the in-memory-only ownership path.
- Explicit `allow_legacy_execution=True` retains compatibility mechanics for deterministic tests only; supplying a custom process factory does not silently enable legacy execution.
- Recreated managers conservatively move unowned `created`, `queued`, or `running` legacy jobs to `needs_input`, generate report/resume/manifest artifacts, and record an ownership-unavailable event.
- Cancellation without an owned live process handle no longer falsely reports `cancelled`; it remains `needs_input` pending manual verification.
- Supervisor resume prompts are published through atomic replacement, and unverified child cancellation remains conservatively resumable after service restart without relaunching the child or duplicating its event.
- Return-loop manifest regeneration recomputes current file paths, hashes, and sizes while preserving an externally delivered manifest's sent status, delivery metadata, original creation time, and audit identity.
- Delivered manifests remain undiscoverable as ready after regeneration.
- Local-agent job command parsing preserves the exact case of opaque job IDs, preventing Windows path lookup from succeeding while in-memory process ownership lookup fails.

Validation evidence:

- Legacy long-job suite: `15 passed`.
- Local-agent job orchestration suite: `4 passed`.
- Existing PulseSender contract suite: `6 passed`.
- Delivery-regeneration regression: `1 passed`.
- Full repository suite: `905 passed, 1 skipped`.
- `python -m pip check`: no broken requirements found.
- D5 implementation checkpoints: `542abc1`, `d131eb8`, `43f540c`, `2893440`, `bf8dbb9`, `eadcb24`, and `86bab3e`.

Boundaries not claimed:

- `LongRunJobManager` has not been migrated into a restart-adoptable process manager; it remains compatibility/test-only.
- Durable remote SSH jobs, permissive shell execution, global transfer roots, absolute cgroup limits, and remote restart adoption are separate follow-up batches.
- The earlier Codex stdin transport failures were repaired and live-validated in T1.

Each batch must be independently reviewable, tested, and committed. Do not combine the remote-execution expansion into one broad refactor.

## Explicitly Deferred

Do not prioritize these until P0 is complete:

- ChatGPT Apps SDK live-status component
- new dashboard write controls
- broader local-model coding permissions
- additional workflow step types
- production deployment automation
- public/main branch push automation

## Exit Gate

The durability gate is complete only when all of the following are true:

- Accepted work has a durable launch intent before execution.
- Every active process has verified ownership identity and renewable lease state.
- Startup reconciliation cannot convert an unverified active run into ordinary failure.
- Repository locks cannot be released by stale or uncertain owners.
- Workflow/supervisor child launch is idempotent across every tested crash boundary.
- Queued and running work reaches a deterministic recoverable or terminal state after restart.
- Legacy unattended jobs are migrated or explicitly blocked from durable routing.
- Full tests and Windows process integration tests pass.
- Documentation no longer claims restart safety beyond the proven guarantees.

## T1 - Codex prompt transport repair

Status: **implemented and validated**.

Delivered guarantees:

- Synchronous and durable Codex execution now share one UTF-8 file-backed prompt-stream helper.
- Durable plan and implementation workers pass that stream as stdin when invoking `codex exec -`; prompts are no longer omitted or placed on the Windows command line.
- Durable workers now use the same connector-isolated child environment as the synchronous runner, while preserving run-specific temporary directories.
- A dedicated durable-worker regression reads the inherited stdin file and verifies the complete multiline plan prompt, trailing `-` argument, connector-variable filtering, and temp environment.
- Live plan run `20260714T034343Z_codex_plan_task_379223ec` received the exact marker `T1_STDIN_PROBE_20260714`, returned `PLAN_STATUS: ready`, exited `0`, changed no files, and left the branch clean.

Validation evidence:

- Prompt transport regression: `1 passed`.
- `CodexRunner` suite: `18 passed`.
- Durable worker suite: `17 passed`.
- Full repository suite: `906 passed, 1 skipped`.
- `python -m pip check`: no broken requirements found.
- T1 implementation checkpoints: `4f0dab8` and `e995386`.

Observed non-blocking CLI noise:

- The live plan logged a Vercel MCP authorization warning and PowerShell profile language-mode warnings, but continued successfully and returned the correct plan. These are external session noise, not prompt-transport failures.

## Next Feature Batch

### R1 - Global remote policy and request contract

- Connect SSH execution modes to the canonical autonomy profiles.
- Preserve structured execution for every profile, reviewed scripts for delegated/permissive use, and unrestricted root shell only for permissive use.
- Keep all transport, execution, transfer, monitoring, cancellation, and reconciliation logic repository-independent.

Wan2.2 paid-pod work remains blocked until the complete generic SSH acceptance gate passes. UI expansion remains deferred behind execution correctness.
