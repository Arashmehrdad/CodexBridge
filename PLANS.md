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
- Workflow and supervisor launch/attachment recovery remain for D3 and D4.
- D1 proves direct-run restart adoption for the tested Windows worker path; broader crash races and concurrent ownership transitions remain part of D2.

### Batch D2 - Conditional transitions and launch-state completion

Add compare-and-swap/versioned ownership transitions for claim, cancellation, completion, timeout, recovery, and lock release. Complete deterministic race handling now that D1 provides durable launch intent, lease tokens, bounded relaunch, and launch-failure rollback.

### Batch D3 - Workflow worker lease and child attachment

Harden `codexbridge/workflows/` around crash-safe step claims and idempotent child attachment.

### Batch D4 - Supervisor child attachment and lock unification

Harden `supervisor_engine.py`, `supervisor_service.py`, and the shared repository ownership model.

### Batch D5 - Legacy long-job migration and return-loop consistency

Remove in-memory-only ownership from unattended jobs and preserve delivery state during report regeneration.

Each batch must be independently reviewable, tested, and committed. Do not combine all five into one broad refactor.

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

## Next Feature Batch After the Gate

After P0/P1 completion, reassess the optional ChatGPT-native live-status component. Keep it distinct from the existing local read-only dashboard and do not let UI work precede execution correctness.
