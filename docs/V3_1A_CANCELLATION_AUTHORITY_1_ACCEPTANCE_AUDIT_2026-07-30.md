# V3-1A-CANCELLATION-AUTHORITY-1 — Independent Acceptance Audit

**Date:** 2026-07-30
**Verdict:** not accepted; final closure subgate required.
**Implementation commit audited:** `c1c5b535e9bb95b14b701546ce716653faf6688d`
**Parent gate:** `V3-1A-PROCESS-IDENTITY-1`
**Push:** not authorised.

## 1. Summary

The corrective package materially improves Soma's process safety. It adds canonical launcher and child start identities, replaces canonical local raw-PID cancellation with identity-scoped termination, establishes real Windows Job Object containment for stand-in trees, closes several environment bypasses, repairs the host-dependent PID-12345 test, and preserves the existing Task → Run authority.

The package does not close the gate. Independent adversarial review reproduced three fail-open or incomplete boundaries and found two launch paths that were omitted from the claimed identity coverage. Publication retry remains unproved and its current response semantics contradict the active gate. Restart containment is fail-closed but cannot guarantee that an orphaned provider stops after a Soma crash.

The package remains implemented but unaccepted. No interaction-command work is active.

## 2. Evidence that passed

- focused worker/process/adapter/foundation suites: **267 passed**;
- adjacent JobManager, job_worker, RunStore, process_control, ProjectScope, canonical task, capability and CF1 suites: **217 passed**;
- no test was deselected;
- real Windows Job Object tests proved root/child/grandchild containment, root-exit orphan membership, late-descendant containment and empty-job verification;
- PID mismatch and unreadable identity paths refuse termination;
- the known `test_cancel_run_marks_cancelled` baseline now passes;
- additive RunStore migration and public gateway/schema compatibility tests pass;
- authority delta remains zero;
- worktree was clean at the audited commit.

Durable validation references:

- focused suites: `20260730T180446Z_executable_profile_d155f0af`;
- adjacent suites: `20260730T180713Z_executable_profile_3ba526ce`.

## 3. Acceptance blockers

### 3.1 Empty subordinate rows can still publish while a kernel job is non-empty

`CancellationProof.may_publish_terminal_cancellation` returns `canonical_pre_launch_proven` directly for `NOTHING_RECORDED`. It does not also require the kernel job to be empty.

The audit constructed a proof with:

- `NOTHING_RECORDED`;
- `canonical_pre_launch_proven=True`;
- `job_proof_available=True`;
- `job_assigned_pids=(4242,)`.

The implementation returned `publish_with_live_job=True`.

Durable probe: `20260730T180446Z_executable_profile_88e32943`.

Canonical pre-launch proof and a non-empty kernel job are contradictory evidence. Contradiction must become uncertainty; terminal publication is forbidden.

### 3.2 Canonical launch coverage is incomplete

The completion report says every RunStore launcher attachment was updated, but `parallel_groups.py` still has two `record_worker_launch(...)` paths that omit `launcher_identity`:

- initial group child launch;
- refill launch after a concurrency slot opens.

A live parallel-group launcher therefore has no provable canonical ownership and becomes deliberately uncancellable under the owner-approved contract.

The direct JobManager and job_worker paths also accept a newly launched process when `process_identity(pid)` returns an empty string. The audit demonstrated a live launcher being accepted as `queued` with `launcher_identity=''`.

Durable probe: `20260730T180935Z_executable_profile_d0b7fead`.

Historical empty identities must remain uncertain. Newly launched processes must not be durably attached as healthy when start identity capture fails.

### 3.3 `allowlist_extra` remains an unrestricted inherited-configuration escape hatch

The package protects known recursion, Soma/MCP and secret-shaped names, but an arbitrary inherited tool setting can still be reintroduced by name. Values admitted through `allowlist_extra` are not checked for credential shapes.

The audit reproduced:

- `PYTHONPATH=C:/attacker` reaching the child;
- `MY_HARMLESS_SETTING=sk-...` reaching the child.

Durable probe: `20260730T180839Z_executable_profile_a35a365c`.

This violates the gate's positive-policy requirement and its ban on arbitrary inherited tool configuration.

### 3.4 Publication failure is stored but the cancellation response reports success

After proven termination, forcing ResultPublication to fail produced:

- cancellation response `ok=True`;
- durable run status `cancelled`;
- durable publication status `failed`;
- repository lock already released.

A second `cancel_run` call published successfully without repeating termination, which shows the underlying publication function is retryable. But the first response does not agree with publication state and the required retry evidence is absent from the suite.

Durable probe: `20260730T180907Z_executable_profile_18cca202`.

Process absence may justify releasing mutation ownership, but it does not justify representing publication as successful. The response must expose the partial outcome honestly and retry must prove exact-result idempotency.

### 3.5 Restart containment does not satisfy the first-provider safety boundary

The implementation correctly measures that a named Windows job cannot be reopened after its last handle closes. The process-local registry therefore loses containment proof across a Soma restart. Cancellation then becomes `UNCERTAIN`, but live provider descendants may continue mutating without a controller.

Failing closed prevents false terminal publication, but it does not prevent orphan work. V3-1A requires recovery evidence for a Soma restart while a provider session remains active. The process gate cannot claim that cancellation genuinely wins while a controller crash may leave the worker alive and uncontainable.

## 4. Additional audit corrections

- `launcher_identity` and `child_identity` are not exposed by the actual public summary/control projections, but they were added to `RUN_SCALAR_SUMMARY_COLUMNS`, not `RUN_INTERNAL_ONLY_COLUMNS`. Future completion reports must distinguish CF1 column classification from actual public projection.
- `test_cancel_run_terminates_child_then_worker_and_releases_lock` now checks report ordering over already-dead PIDs; it no longer proves real termination-call ordering. The closing package must restore a deterministic identity-matched ordering test without touching real host processes.
- The module-level exited-PID fixture is safer than literal PID 12345 but can theoretically be reused before a later test. Deterministic cancellation tests should mock identity/running state explicitly rather than depend on host PID reuse timing.

## 5. Restart-containment decision

For the first real provider launch, Soma will use Windows Job Objects with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.

Rationale:

- Soma's company state and provider-native session identity are durable;
- worker processes are bounded, disposable and resumable;
- an uncontrolled orphan that can continue repository mutation is worse than interrupted work;
- a separate long-lived handle-keeper would add another process owner and lifecycle before the role-scoped broker exists.

Therefore a Soma crash must stop the contained worker tree. Restart adoption of an already-running local provider process is deferred. Recovery will use the exact durable native-session identity and a new canonical route attempt when later authorised.

## 6. Authority disposition

`RunStore` and `JobManager` remain canonical for cancellation state, terminal transition, lock release and ResultPublication. `process_control` and Windows containment remain process-proof mechanisms. The worker substrate remains subordinate evidence.

The required corrections add no lifecycle authority. Generic authority delta must remain **zero**.

## 7. Disposition

- `V3-1A-CANCELLATION-AUTHORITY-1`: implemented but not accepted;
- active final corrective subgate: [`V3_1A_CANCELLATION_CLOSURE_1_GATE_2026-07-30.md`](V3_1A_CANCELLATION_CLOSURE_1_GATE_2026-07-30.md);
- `V3-1A-PROCESS-IDENTITY-1`: remains unaccepted;
- `V3-1A-INTERACTION-COMMANDS-1`: inactive;
- real Claude/Codex launch, provider accounts, live prompts, public worker access, V3-1B, production activation and push: forbidden.
