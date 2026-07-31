# V3-1A-LAUNCH-FAILURE-CONTAINMENT-1 — Identity-Safe Fresh-Launch Cleanup

**Date:** 2026-07-31
**Status:** active bounded corrective subgate inside `V3-1A-PROCESS-IDENTITY-1`.
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Depends on:** failed audit [`V3_1A_CANCELLATION_CLOSURE_1_ACCEPTANCE_AUDIT_2026-07-31.md`](V3_1A_CANCELLATION_CLOSURE_1_ACCEPTANCE_AUDIT_2026-07-31.md)
**Repository baseline:** `46cab50b09dd1443a144911a18539ded221e3685`
**Push:** not authorised.

## 1. Objective

Close the final process-identity boundary: a fresh local launch that cannot be attached, identified, or durably owned must never trigger raw-PID action, terminalise uncertainty, or release mutation ownership while the created process may remain active.

This package is deliberately smaller than the preceding closure gate. It does not redesign cancellation, publication, environment policy, Job Object crash containment, provider adapters, task commands, or public gateways. It must preserve every accepted result from `89fb199` while correcting fresh-launch failure proof and its caller dispositions.

Do not start `V3-1A-INTERACTION-COMMANDS-1` in the same run.

## 2. Binding contract

The owner-approved no-raw-PID rule remains unchanged:

> A live PID without an exact matching recorded start identity is never terminated, enumerated as an owned tree, or treated as absent. Unprovable ownership becomes durable uncertainty and retains or quarantines mutation ownership.

Creator-held ownership permits action through an exact `subprocess.Popen` process handle or an already-established kernel Job Object. It does not permit a later call to `terminate_process_tree(pid)` merely because the PID originally came from that handle.

Once a start identity is captured, cleanup may use identity-scoped termination and must re-verify absence of that exact process.

## 3. Required corrections

### 3.1 Structured fresh-launch containment result

Replace the ambiguous `LaunchIdentityUnavailable` promise with a result or exception contract that distinguishes at least:

- identity captured and process remains active;
- identity unavailable but exact creator-held process stop is confirmed;
- identity unavailable and exact creator-held stop is unconfirmed;
- cleanup error with bounded evidence.

The evidence must include only safe process facts such as PID, method, whether creator-handle kill was attempted, whether exact-handle wait/poll confirmed exit, and a bounded error. It must not claim that descendants are gone unless a Job Object or another ownership primitive proves it.

A caller must never infer `termination_confirmed=True` from exception type alone.

### 3.2 Remove raw-PID fallback without identity

`capture_launch_identity` or its replacement must not call:

- `terminate_process_tree(pid)`;
- descendant enumeration from the numeric PID;
- identity-scoped termination with an empty identity.

when process-start identity capture failed.

Permitted actions are limited to:

- exact creator-held `Popen.kill` / `terminate`;
- exact creator-handle `wait` / `poll` verification;
- termination/query through a Job Object that was established before the process ran;
- another ownership primitive that does not infer ownership from a live PID number.

If exact-handle stop cannot be proven, return durable uncertainty. Do not silently upgrade it to containment success.

### 3.3 Identity-proven cleanup after identity capture

Replace raw `terminate_process_tree(process.pid)` cleanup in the touched canonical paths with identity-scoped termination using the captured identity:

- JobManager initial launch lease loss;
- JobManager recovery relaunch lease loss;
- parallel-group initial child launch lease loss;
- parallel-group refill lease loss;
- executable-child attachment exception;
- executable-child attachment returning false;
- executable-child timeout.

Each path must:

1. use the exact captured `launcher_identity` or `child_identity`;
2. refuse action if the live identity differs or becomes unreadable;
3. re-verify absence after termination;
4. expose a confirmed or uncertain result to the lifecycle owner;
5. never trust the termination primitive's return value by itself.

Do not broaden this subgate into unrelated SSH, workflow, supervisor, or remote-process cleanup.

### 3.4 Caller disposition on confirmed containment

When fresh-launch cleanup proves the exact created process stopped and no owned descendant uncertainty exists, the existing failure path may:

- fail the run as infrastructure failure;
- publish the canonical terminal result;
- release the repository lock under existing ownership rules;
- continue group refill/failure policy where already authorised.

This path must be explicitly tested so safe ordinary launch failure remains usable.

### 3.5 Caller disposition on unconfirmed containment

When fresh-launch cleanup cannot prove the exact process stopped:

- do not transition to terminal `failed`, `cancelled`, or `completed`;
- do not publish a terminal result;
- do not release the repository lock;
- do not refill a concurrency slot as though the worker is gone;
- persist a bounded recovery/uncertainty reason;
- retain or quarantine mutation ownership;
- require explicit recovery adjudication.

Use the existing canonical run plane. Prefer `recovery_pending` unless a more precise existing non-terminal state is already authoritative for the path. Do not add a second lifecycle manager or a new public state solely for this package.

Parallel-group status must project the uncertain child honestly rather than counting it as an ordinary terminal failure.

### 3.6 PID reuse adversarial safety

Add an adversarial test in which:

1. identity capture fails for the exact newly created process;
2. creator-handle kill/wait reports failure or uncertainty;
3. the numeric PID appears live afterwards as a simulated different occupant;
4. no PID-based terminator or descendant enumeration is called;
5. the new occupant is untouched;
6. the run remains non-terminal and its lock remains held or quarantined.

This test must fail the `89fb199` behavior reproduced by audit run `20260731T033806Z_executable_profile_76000fa9`.

### 3.7 Behavioral launcher and child tests

Replace source-string and conditional evidence with executed behavior.

Required launcher tests:

- JobManager initial launch persists non-empty identity;
- JobManager recovery relaunch persists non-empty identity;
- parallel-group initial child launch persists non-empty identity;
- parallel-group refill persists non-empty identity;
- each path rejects or marks uncertain when identity capture fails;
- each lease-loss cleanup uses identity-scoped termination;
- no test verdict depends on host PID allocation.

Required child tests:

- identity-capture failure executes creator-handle cleanup and never calls raw PID termination;
- attachment exception executes identity-scoped cleanup;
- attachment false executes identity-scoped cleanup;
- timeout executes identity-scoped cleanup;
- unconfirmed cleanup prevents normal terminal success and preserves uncertainty.

Static assertions such as searching source text for `process.kill()` do not satisfy this gate.

### 3.8 Pin real publication retry evidence

The runtime publication behavior passed independent audit and does not need redesign. Replace or supplement the lambda-only committed test with a real publication regression that:

- forces `atomic_write_json` failure after proven zero-process termination;
- verifies durable `result_publication_status == "failed"`;
- verifies lock release under the accepted zero-process policy;
- retries through real `publish_run_result`;
- verifies identical authoritative result JSON and source hash;
- verifies no repeated termination;
- verifies idempotent success after publication.

The independent passing probe is `20260731T034049Z_executable_profile_b626710b`.

### 3.9 Correct CF1 classification reporting

At the current baseline, `launcher_identity` and `child_identity` are classified in `RUN_SCALAR_SUMMARY_COLUMNS`, not `RUN_INTERNAL_ONLY_COLUMNS`, although actual public projections exclude their values.

Choose one explicit outcome:

- move both columns to `RUN_INTERNAL_ONLY_COLUMNS` and update the CF1 inventory tests if that is the intended classification; or
- leave the classification unchanged and state it accurately in completion evidence.

Do not confuse inventory classification with actual projection exposure. The pre-existing `worker_identity` exposure through `get_status` remains outside this subgate and must stay explicitly documented rather than silently changed.

## 4. Required validation

Minimum focused evidence:

- identity-less creator-handle cleanup makes zero raw-PID termination calls;
- handle kill failure and wait timeout produce uncertainty, not claimed containment;
- simulated PID reuse occupant is untouched;
- initial JobManager uncertainty retains the repository lock and remains non-terminal;
- recovery relaunch uncertainty remains recovery-pending and retains ownership;
- parallel initial/refill uncertainty does not free a slot as terminal failure;
- all seven identity-proven cleanup paths use captured identity and absence verification;
- all four launcher paths persist non-empty identity in executed tests;
- child identity and attachment failures are behaviorally tested;
- real publication failure/retry regression passes;
- CF1 classification statement matches live constants;
- launcher/child values remain absent from public projections.

Regression floor:

- the **286 passed, 1 xfailed** focused suite remains green;
- the **272 passed** adjacent audit selection remains green;
- Windows `KILL_ON_JOB_CLOSE` crash proof remains green;
- public gateway/schema hashes remain unchanged;
- populated RunStore migration remains additive and idempotent;
- no process or cancellation test is deselected.

## 5. Acceptance gate

`V3-1A-PROCESS-IDENTITY-1` closes only when:

- no fresh-launch path acts on a live PID without exact identity or kernel ownership proof;
- containment evidence distinguishes confirmed stop from uncertainty;
- uncertainty cannot become terminal failure with lock release;
- all touched post-identity cleanup is identity-scoped and re-verified;
- launcher and child failure tests execute real behavior rather than inspect source strings;
- real publication retry evidence is pinned in the repository;
- CF1 classification is reported accurately;
- all previously accepted closure results remain intact;
- authority delta remains zero;
- focused and adjacent suites pass;
- worktree is clean, an independent acceptance audit is recorded, and nothing is pushed.

## 6. Explicit exclusions

- real Claude Code or Codex launch;
- provider accounts, authentication, installation, upgrade or purchase;
- live provider prompts or streams;
- native steering, supplied input, pause or resume;
- `STEER`, `SUPPLY_INPUT` or new task commands;
- operational `AWAITING_CONTROLLER`;
- public worker gateway or direct worker Soma MCP access;
- new supervisor, handle-keeper, process lifecycle or result publisher;
- workflow/supervisor migration;
- broad SSH or remote-process cleanup;
- V3-1B work;
- deployment, production activation, unrelated cleanup or push.

## 7. Stop conditions

Stop and return to architecture review if:

- safe launch-failure containment requires killing a live process by PID without identity;
- uncertainty cannot retain or quarantine mutation ownership in the existing run plane;
- a second durable process lifecycle is required;
- a new public run state or gateway is required solely to close this package;
- the correction would weaken KILL_ON_JOB_CLOSE, cancellation publication honesty, or the no-raw-PID contract;
- the package expands into interaction commands or provider execution.

## 8. Completion report

Report:

1. structured fresh-launch containment contract;
2. exact removal of identity-less raw-PID action;
3. all identity-proven cleanup paths changed;
4. confirmed-containment lifecycle behavior;
5. uncertain-containment lifecycle and lock behavior;
6. PID-reuse adversarial result;
7. behavioral launcher and child tests;
8. real publication retry regression;
9. CF1 classification outcome;
10. focused and adjacent validation;
11. migration and public-contract evidence;
12. authority delta;
13. known limitations;
14. local commit hashes;
15. whether `V3-1A-PROCESS-IDENTITY-1` is ready for independent acceptance.

Do not start the next gate.
