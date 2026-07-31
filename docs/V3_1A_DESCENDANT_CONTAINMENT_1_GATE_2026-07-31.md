# V3-1A-DESCENDANT-CONTAINMENT-1 — Root Exit Is Not Tree Exit

**Date:** 2026-07-31
**Status:** active bounded corrective subgate inside `V3-1A-PROCESS-IDENTITY-1`.
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Depends on:** failed audit [`V3_1A_LAUNCH_FAILURE_CONTAINMENT_1_ACCEPTANCE_AUDIT_2026-07-31.md`](V3_1A_LAUNCH_FAILURE_CONTAINMENT_1_ACCEPTANCE_AUDIT_2026-07-31.md)
**Repository baseline:** `acaf9b289ec683a93f469fc523184637c51ec5dc`
**Push:** not authorised.

## 1. Objective

Close the last demonstrated process-containment contradiction: confirmation that a fresh launch's root `Popen` process exited must not authorise terminal failure, ResultPublication, lock release, or parallel-slot refill while a descendant from that launch may remain active.

This package preserves the accepted parts of `b6adcae`:

- zero raw-PID action after identity-capture failure;
- structured containment evidence;
- `recovery_pending` and lock retention for unconfirmed cleanup;
- identity-scoped post-identity cleanup;
- positive environment policy;
- cancellation publication honesty and retry;
- Windows `KILL_ON_JOB_CLOSE` crash containment;
- deterministic cancellation ordering;
- accurate CF1 reporting and public projection exclusion.

Do not start interaction commands, real providers, V3-1B, or production activation.

## 2. Binding invariant

> Root exit is not tree exit. Terminal launch failure and mutation-lock release require proof that no process created by the launch can remain active.

A creator-held `Popen` handle proves facts about the root process only. It does not prove that descendants are absent.

After start-identity capture fails:

- parent-table enumeration, PID reuse inference, and raw-PID tree termination remain forbidden;
- creator-handle kill/wait may prove the root exited but cannot, by itself, prove terminal-safe containment;
- a Job Object or equivalent ownership primitive must have been established before the process ran to prove the owned tree empty;
- absent tree-empty proof, the run remains non-terminal and retains or quarantines mutation ownership.

## 3. Required corrections

### 3.1 Separate root and tree proof

`LaunchContainment` must represent at least:

- identity captured;
- root exit confirmed;
- owned-tree empty proven;
- root exit unconfirmed;
- cleanup error.

A single property named `stop_confirmed` may not mean root-only exit while callers interpret it as terminal-safe tree containment.

Use an explicit terminal-safety property such as `owned_tree_empty`, `terminal_containment_proven`, or equivalent. It is true only when:

- a pre-established Job Object or equivalent primitive proves no assigned member remains; or
- another enforced launch invariant proves descendants could not have been created before attachment.

No timing assumption is an invariant.

### 3.2 Bare creator-handle behavior

When identity capture fails and only the bare creator handle is available:

- killing and reaping the root may be recorded as `root_exit_confirmed=True`;
- terminal containment remains unproven;
- the canonical run becomes or remains `recovery_pending`;
- ResultPublication is not called;
- repository lock ownership is retained or quarantined;
- parallel-group status remains active;
- no refill slot is released.

This applies to all five current `capture_launch_identity` callers:

1. JobManager initial launcher;
2. JobManager recovery relaunch;
3. parallel initial launcher;
4. parallel refill launcher;
5. executable child.

### 3.3 Tree-proven terminal behavior

A terminal infrastructure failure is allowed only when owned-tree absence is proven.

The first implementation may choose either:

- pre-establish Windows Job Object containment before the process is resumed and pass that proof through identity capture; or
- conservatively keep all identity-capture failures non-terminal until explicit recovery adjudication.

Do not add a handle keeper, supervisor lifecycle, new public run state, or second process owner.

If Job Objects are used:

- assignment must occur before the process can spawn descendants;
- `KILL_ON_JOB_CLOSE` remains enabled;
- terminal-safe proof requires the job to be empty after cleanup;
- normal release of an already-empty job remains safe;
- non-Windows paths degrade honestly to non-terminal uncertainty unless an equivalent primitive exists.

### 3.4 Canonical lifecycle correction

JobManager, JobWorker, and parallel-group callers must branch on terminal tree proof, not root exit.

When only root exit is known:

- do not call `fail_infrastructure` or `transition_terminal`;
- do not call `publish_run_result`;
- do not release repository locks;
- do not count a group child as terminal;
- persist bounded evidence stating root exit was confirmed but descendant absence was not.

### 3.5 Escaped-descendant regressions

Add a real behavioral regression equivalent to audit run `20260731T052128Z_executable_profile_061e12e8`:

1. a root process immediately spawns a child;
2. identity capture fails;
3. creator-handle cleanup kills and reaps the root;
4. the child remains alive temporarily;
5. containment reports root exit but not terminal tree proof;
6. no PID-based action is taken against the child;
7. cleanup allows the short-lived child to exit naturally after the assertion.

Add a canonical JobManager regression equivalent to audit run `20260731T052343Z_executable_profile_da5d64cb` proving:

- durable status is `recovery_pending`;
- terminal result remains unpublished;
- repository lock remains present;
- descendant is still alive at the observation point.

Add parallel initial/refill and executable-child equivalents or a shared behavioral fixture that executes all caller dispositions.

### 3.6 Replace the unsafe confirmed-handle test

`test_confirmed_identity_capture_failure_remains_terminal_and_releases_lock` currently proves only root exit with a fake handle and encodes the unsafe assumption.

Replace it with one of:

- a pre-established Job Object empty proof that legitimately permits terminal failure and lock release; or
- a root-only proof that remains `recovery_pending` and retains the lock.

Fake handles that cannot spawn descendants cannot establish tree containment.

### 3.7 Pin the integrated publication retry path

Preserve the real direct `publish_run_result` retry test, and add or restore an integrated cancellation regression that uses the real publisher and real `atomic_write_json` failure to prove in one path:

- zero-process cancellation proof;
- durable terminal winner unchanged;
- first publication status `failed`;
- lock release under the accepted zero-process policy;
- retry through `cancel_run` or the authoritative public retry route;
- identical result JSON and source hash;
- no repeated termination;
- idempotent success after publication.

This is evidence closure only; do not redesign publication.

## 4. Required validation

Minimum focused evidence:

- direct root → child escape probe passes with terminal containment false;
- canonical JobManager escaped-descendant path remains `recovery_pending` with lock retained and no publication;
- recovery relaunch root-only cleanup remains non-terminal;
- parallel initial and refill root-only cleanup remain active and consume their slots;
- executable-child root-only cleanup propagates recovery uncertainty;
- Job Object empty proof, if implemented, permits terminal failure safely;
- identity-less PID-reuse safety remains green;
- all seven post-identity cleanup paths remain identity-scoped;
- integrated real publication retry is pinned;
- CF1 and public projection assertions remain green;
- Windows `KILL_ON_JOB_CLOSE` crash proof remains green.

Regression floors:

- candidate's changed-package focused suite remains green;
- prior **286 passed, 1 xfailed** process/adapter/foundation floor remains green;
- prior **272 passed** adjacent selection remains green;
- full repository suite remains green with no newly skipped process/cancellation test;
- public gateway/schema hashes remain unchanged;
- populated RunStore migration remains additive and idempotent;
- changed-file Ruff, `pip check`, and `git diff --check` pass.

## 5. Acceptance gate

`V3-1A-PROCESS-IDENTITY-1` closes only when:

- no identity-capture failure can terminalise while a descendant may remain active;
- root-exit evidence is distinct from owned-tree absence proof;
- creator-handle-only cleanup remains non-terminal;
- terminal failure and lock release require tree-empty proof;
- escaped-descendant behavior is pinned through helper and canonical lifecycle tests;
- PID-reuse safety, post-identity cleanup, publication retry, Job Object crash policy, environment policy, cancellation ordering, projection exclusion, migration, and compatibility remain intact;
- authority delta remains zero;
- worktree is clean, an independent acceptance audit is recorded, and nothing is pushed.

## 6. Explicit exclusions

- real Claude Code or Codex launch;
- provider accounts, authentication, installation, upgrade or purchase;
- live provider prompts or streams;
- steering, supplied input, pause or resume;
- new task commands or operational `AWAITING_CONTROLLER`;
- public worker gateway or direct worker Soma MCP access;
- new supervisor, handle keeper, process lifecycle or result publisher;
- workflow/supervisor migration;
- broad SSH or remote-process cleanup;
- V3-1B work;
- deployment, production activation, unrelated cleanup or push.

## 7. Stop conditions

Stop and return to architecture review if:

- tree-safe proof requires raw-PID action after identity capture failed;
- the only solution requires a new durable process owner;
- uncertainty cannot remain in the existing canonical run plane;
- a new public state or gateway is required solely for this correction;
- KILL_ON_JOB_CLOSE or the no-raw-PID contract would be weakened;
- the package expands into provider execution or interaction commands.

## 8. Completion report

Report:

1. root-exit versus tree-empty contract;
2. caller behavior without tree proof;
3. tree-proven terminal path, if implemented;
4. all five capture callers;
5. escaped-descendant helper and canonical lifecycle results;
6. parallel and executable-child behavior;
7. integrated publication retry evidence;
8. retained PID-reuse and identity-scoped cleanup evidence;
9. focused and full validation;
10. migration and public-contract evidence;
11. authority delta;
12. known platform limitations;
13. local commit hashes;
14. whether `V3-1A-PROCESS-IDENTITY-1` is ready for independent acceptance.

Do not start the next gate.
