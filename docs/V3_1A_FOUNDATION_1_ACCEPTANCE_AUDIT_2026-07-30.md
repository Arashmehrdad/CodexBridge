# V3-1A-FOUNDATION-1 — Independent Acceptance Audit

**Date:** 2026-07-30
**Status:** accepted after audit corrections; implementation package closed.
**Lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Implementation commit:** `b2aa44709aa38a7563d457d42b29c9becbb3f17e`
**Audit-correction commit:** `c11919e7410faef7c351b318de396000845e8e5a`
**Push:** none authorised or performed.

## 1. Verdict

`V3-1A-FOUNDATION-1 — Shared Contracts and Persistence` is **accepted after corrections**.

The original implementation established the right additive shape: one internal `soma.worker_substrate` package, six subordinate tables in the existing Soma SQLite store, no provider launch, no public gateway, no task-plane enum expansion, no V3-1B authority, and no production activation.

The package did not pass independent audit unchanged. The audit found material fail-closed gaps in identity coherence, replay conflict detection, payload-reference integrity, evidence immutability, and concurrent migration initialisation. Those gaps were corrected in `c11919e7410faef7c351b318de396000845e8e5a` and regression-covered before acceptance.

## 2. Accepted authority boundary

Canonical owners remain unchanged:

- `TaskStore` / `TaskManager`: TaskAdmission, task state, task commands, checkpoints, links, and task reconciliation projection;
- `RunStore` / `JobManager`: run ownership, leases, launch, cancellation, recovery, terminal result, and ResultPublication;
- `ProjectScopeStore`: exact project, repository resource, task reservation, and run-attempt identity;
- `process_control`: process identity, tree termination, and PID-reuse protection.

The six worker-substrate tables own subordinate evidence only:

1. `worker_provider_sessions` — exact provider-native session binding;
2. `worker_interactions` — persist-before-send interaction intent and delivery evidence;
3. `worker_checkpoint_deadlines` — checkpoint deadline policy;
4. `worker_checkpoint_expiries` — immutable expiry evidence;
5. `worker_usage_events` — provider-native raw usage evidence;
6. `worker_child_processes` — observed provider-child PID/start identity.

They do not own task admission, generic task state, leases, cancellation, terminal results, ResultPublication, or OutcomeAcceptance.

## 3. Material findings and corrections

### 3.1 Canonical identity coherence

**Finding:** a provider session could be bound to an arbitrary `run_id`, project, resource, or task combination because the substrate table intentionally had no run foreign key and the store performed no equivalent canonical read proof.

**Correction:** binding now fails closed unless:

- the task exists;
- `tasks.backend_ref` is the exact run;
- the run exists;
- ProjectScope contains the exact project/task/run/resource attempt;
- the task reservation and attempt are not quarantined;
- the run repository matches the ProjectScope repository binding.

The store reads these authorities but never writes them.

### 3.2 Complete interaction idempotency

**Finding:** replay compared only payload hash, allowing the same task/idempotency key to change interaction kind, session, checkpoint, payload reference/length, or requested task state version.

**Correction:** replay now compares the complete command contract. Any changed field raises `InteractionConflict`; exact replay returns the original record.

### 3.3 Payload integrity

**Finding:** an external payload reference was length-checked but did not have to be the content-addressed path for the submitted SHA-256, and later reads did not verify content integrity.

**Correction:** payload references must be exact lowercase SHA-256 content addresses, existing bytes must match both declared length and digest, reads detect tampering, and concurrent temporary writes use unique names.

### 3.4 Immutable checkpoint and delivery evidence

**Finding:** checkpoint deadlines could be rebound, checkpoint-expiry replay could silently accept changed evidence, and terminal interaction delivery evidence could move backward.

**Correction:** checkpoint/task/session identity is proven, deadline policy is immutable, expiry requires the exact durable deadline and valid timestamps, changed replay raises `EvidenceConflict`, quiescent release requires proof, and terminal delivery evidence cannot regress.

### 3.5 Usage and process evidence binding

**Finding:** usage events and child-process observations could be written under one provider-session binding while naming a different task, run, provider, or native session. Immutable replay fields could also change silently.

**Correction:** every event is checked against its exact binding; negative token/sequence values and invalid process identifiers are refused; changed replay raises `EvidenceConflict`; non-finite provider cost text remains unparsed evidence rather than contaminating totals.

### 3.6 Concurrent migration initialisation

**Finding:** independent initialisers could both determine that migration version 1 was pending before either acquired the write lock.

**Correction:** each initialiser acquires `BEGIN IMMEDIATE` and rechecks migration state after acquiring the lock. Four concurrent initialisers converge on one migration record.

## 4. Validation evidence

### Focused substrate gate

- `43 passed in 8.73s`
- run: `20260730T143754Z_executable_profile_6ea81e5f`

The original 35 tests remain green. Eight audit-specific regressions cover canonical identity mismatch, complete command idempotency, payload tampering, deadline immutability, usage and process cross-binding, terminal delivery monotonicity, and concurrent migration initialisation.

### Adjacent runtime gate

- `211 passed, 1 deselected in 67.29s`
- group: `20260730T144122Z_powershell_group_00aae310`

Coverage includes canonical tasks, ProjectScope foundation/recovery/quarantine, JobManager, job worker, RunStore, CF1 RunStore baseline, and process control.

### Public-contract gate

- `203 passed in 7.66s`
- group: `20260730T144122Z_powershell_group_00aae310`

Coverage includes capability metadata, CF1 contract freeze, gateway inventories, durable command runner, and flat MCP input compatibility. No connector-visible contract changed.

### Mechanical authority gate

- writes target only the six substrate tables;
- reads target only substrate tables plus explicit canonical identity authorities;
- `TaskKind`, `BackendKind`, and `TaskCommandKind` remain unchanged;
- no baseline store method was removed or duplicated;
- `git diff --check` and Python compilation pass.

Evidence runs:

- authority audit: `20260730T144016Z_executable_profile_d87fa8d7`;
- method-surface audit: `20260730T144805Z_executable_profile_8f1714fd`.

## 5. Populated-store migration proof

A read-only SQLite transaction serialized the live database into a disposable snapshot. The snapshot contained:

- 5 canonical tasks;
- 5,253 canonical runs;
- identity digest `b2cabf3b22a5e9a78e4ad4980c2adb8315cc659877cff50403f5aee79bacb16d`.

After applying the substrate migration twice:

- task/run count and identity digest were unchanged;
- schema version was 1 on both openings;
- exactly one substrate migration record existed;
- `PRAGMA integrity_check` returned `ok`;
- `PRAGMA foreign_key_check` returned no rows;
- all six substrate tables contained zero rows.

Evidence run: `20260730T144726Z_executable_profile_56728174`.

The earlier raw-file copy rehearsal omitted active WAL rows and was rejected as invalid evidence. The accepted proof uses SQLite serialization from a query-only transaction.

## 6. Known external baseline failure

`tests/test_job_manager.py::test_cancel_run_marks_cancelled` still fails because the returned payload reports `cancelled: false` where the test expects `true`.

The failure was reproduced before and after the audit correction and is outside this package's import and diff footprint. It is not hidden or counted as green. It does not block the fixture-only adapter-contract gate, but it must be repaired or explicitly dispositioned before any V3-1A gate claims real provider-process cancellation or zero-orphan evidence.

Isolated evidence run: `20260730T144122Z_executable_profile_6a4e8c9f`.

## 7. Compatibility and authority delta

- Public schema change: none.
- Existing task/run record rewrite: none.
- Historical backfill: none.
- New task lifecycle authority: none.
- New run lifecycle authority: none.
- Generic authority delta: `+0`.
- Compatibility bridge: substrate initialisation applies task migrations before its own checkpoint foreign keys.
- Bridge retirement condition: one ordered migration registry owns dependency ordering in a later consolidation lane.

## 8. Acceptance decision

The foundation is closed at `c11919e7410faef7c351b318de396000845e8e5a`.

Accepted capabilities are limited to internal contracts and additive persistence. Nothing is wired into `server.py`; no provider process launches; no worker command is publicly callable; no production database received substrate rows; and no later V3 authority is implied.

The next bounded gate is [`V3_1A_ADAPTER_CONTRACT_1_GATE_2026-07-30.md`](V3_1A_ADAPTER_CONTRACT_1_GATE_2026-07-30.md).
