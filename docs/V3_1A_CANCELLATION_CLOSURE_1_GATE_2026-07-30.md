# V3-1A-CANCELLATION-CLOSURE-1 — Publication, Identity Capture, and Crash Containment

**Date:** 2026-07-30
**Status:** implementation submitted at `89fb199c4a1a62fc464eed38d6b2836b3094941b`; independent acceptance failed; bounded launch-failure-containment correction active.
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Depends on:** failed audit [`V3_1A_CANCELLATION_AUTHORITY_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_CANCELLATION_AUTHORITY_1_ACCEPTANCE_AUDIT_2026-07-30.md)
**Repository baseline:** `123ca40294fa5bd35061e47eb7b88b0f221e83e6`
**Push:** not authorised.

**Audit:** [`V3_1A_CANCELLATION_CLOSURE_1_ACCEPTANCE_AUDIT_2026-07-31.md`](V3_1A_CANCELLATION_CLOSURE_1_ACCEPTANCE_AUDIT_2026-07-31.md)
**Active corrective gate:** [`V3_1A_LAUNCH_FAILURE_CONTAINMENT_1_GATE_2026-07-31.md`](V3_1A_LAUNCH_FAILURE_CONTAINMENT_1_GATE_2026-07-31.md)

This closure package remains unaccepted. Its retained corrections must not regress while the linked launch-failure-containment gate closes the remaining identity-less raw-PID and lock-release uncertainty boundary. No interaction-command or later V3 package is active.

## 1. Objective

Close the remaining process-identity and cancellation contradictions without expanding into interaction commands or real provider execution.

This package must make every newly launched canonical local process identity-proven, make empty-row cancellation proof consistent with kernel evidence, make environment extras genuinely positive-policy, prove honest publication failure and retry, and ensure a Soma crash cannot leave a Windows provider tree running without a controller.

This is the final corrective package for `V3-1A-PROCESS-IDENTITY-1`. Do not start `V3-1A-INTERACTION-COMMANDS-1` in the same run.

## 2. Binding decisions

### 2.1 No raw-PID termination

The existing owner-approved rule remains unchanged:

> A live PID without an exact matching recorded start identity is never terminated. The run remains `cancellation_pending`, durable uncertainty is recorded, and the repository lock remains held while ownership is unprovable.

A direct `subprocess.Popen` process handle may be used to contain a process immediately after creation and before healthy durable attachment. That is exact creator-held ownership, not raw-PID inference.

### 2.2 Crash policy for first provider launch

Windows Job Objects must use `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` for the first provider-capable substrate.

A Soma crash or process exit therefore stops the contained worker tree. This is intentional:

- company, task, run, session and interaction state remain durable;
- worker processes are bounded and disposable;
- exact provider-native session resume is the recovery mechanism;
- uncontrolled orphan mutation is forbidden;
- restart adoption of a still-running local worker is deferred;
- no separate handle-keeper or supervisor lifecycle may be introduced here.

## 3. Required corrections

### 3.1 Contradictory empty-row evidence

For `CancellationDisposition.NOTHING_RECORDED`, terminal publication requires all of the following:

- canonical pre-launch proof is true;
- no kernel job is known to contain a process;
- if kernel proof is available, the assigned-PID set is empty;
- no surviving or late-descendant evidence exists;
- no contradictory launch/attachment evidence exists.

A non-empty kernel job always blocks publication. Canonical pre-launch proof plus live kernel membership is contradiction and becomes `UNCERTAIN`.

Add an adversarial regression equivalent to the audit probe that currently returns `publish_with_live_job=True`.

### 3.2 Complete canonical launcher identity coverage

Update every RunStore launcher attachment path, including both paths in `parallel_groups.py`:

- initial parallel child launch;
- refill launch after a concurrency slot opens;
- initial JobManager launch;
- JobManager recovery relaunch.

For every newly created launcher:

1. capture process-start identity before healthy durable attachment;
2. reject an empty identity;
3. contain/stop the exact newly created process through its creator-held process handle and verify exit;
4. do not persist a healthy queued/running attachment with empty identity;
5. preserve legacy rows with empty identity as uncertainty without backfill.

Do not make `RunStore.record_worker_launch` globally reject empty identity if that would break historical/migration compatibility. Enforce the fresh-launch invariant at authoritative callers and with focused tests.

### 3.3 Complete canonical child identity coverage

`job_worker` must not attach a newly created executable child with `child_identity=''`.

On identity-capture or persistence failure after `Popen`:

- stop the exact process through creator-held ownership;
- contain its process group/tree as safely as the existing launcher allows;
- verify the root is absent;
- fail the worker operation rather than report healthy attachment;
- never release normal terminal success while a child may remain.

Add focused tests for empty child identity and attachment write failure. Tests may use deterministic fake process handles and synthetic identity readers; they must not target host processes.

### 3.4 Positive policy for inherited extras

`allowlist_extra` may not admit arbitrary inherited names.

Use one of these safe designs:

- a frozen explicit set of reviewed inherited names; or
- remove free-form extras entirely until a provider fixture proves one is required.

The initial safe set may be empty.

Requirements:

- `PYTHONPATH`, `PYTHONHOME`, `NODE_OPTIONS`, Git override/config variables, provider base URLs, proxy/tool configuration and unknown arbitrary names are refused unless explicitly frozen and justified;
- values admitted from the parent are checked for credential shapes as well as names;
- `environment_additions` remains restricted to the reserved internal namespace and credential-safe values;
- evidence contains names/classifications only;
- no silent drop that makes a caller believe a forbidden request was honoured.

The existing test that treats `MY_HARMLESS_SETTING` as safe must be replaced with a true positive-policy test.

### 3.5 Honest cancellation publication and retry

After zero-process proof and canonical terminal transition, forced ResultPublication failure must produce an honest partial response.

Required behavior:

- durable status remains the exact terminal winner (`cancelled`);
- durable publication status is `failed` with bounded error evidence;
- cancellation response does not claim overall publication success;
- response exposes termination confirmation and publication failure distinctly;
- process termination is never repeated on publication retry;
- retry publishes the exact same canonical terminal result and source hash;
- retry is idempotent after success;
- no second terminal transition is attempted;
- lock policy is explicit and tested.

Lock policy for this gate:

- once zero owned processes is proven, the repository mutation lock may be released even if publication fails;
- the response must nevertheless return a partial/failure outcome and a clear retry path;
- publication failure may not be represented as `ok=True` without an explicit subordinate `publication_ok=False` contract that public callers cannot mistake for complete success.

Prefer `ok=False`, `cancelled=True`, `termination_confirmed=True`, `publication_ok=False`, and durable retry evidence unless existing public-contract compatibility requires an equally explicit alternative.

### 3.6 Crash-safe Windows containment

Configure the Job Object extended limit with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` before the suspended root is resumed.

Required proof:

- a helper/controller process creates the job, assigns a sleeping root that spawns descendants, then exits abruptly without calling cancellation;
- all job members exit because the final job handle closes;
- no parent-table inference is used as the decisive proof;
- normal explicit cancellation still terminates and proves the job empty;
- normal handle release after an already-empty job is safe;
- the implementation does not create a new supervisor or durable process lifecycle;
- module documentation no longer suggests named-job reopen provides restart adoption.

If KILL_ON_JOB_CLOSE cannot be established and proven on the supported Windows host, stop. Do not substitute process-local registry survival or parent enumeration.

### 3.7 Deterministic cancellation tests

Restore a meaningful child → worker → launcher ordering test using synthetic PIDs with mocked running/identity state and a termination spy. It must prove calls occur in order without touching real processes.

Replace module-level exited-PID dependence where it affects cancellation correctness. Host PID allocation and reuse must not determine a test verdict.

### 3.8 Public/internal identity classification

Do not expose launcher or child identity values through public summaries, control responses, events or gateway schemas.

Add direct assertions over the actual RunStore public summary/control projections. Completion reporting must state accurately whether CF1 baseline inventory classifies the columns as scalar or internal-only; classification naming must not be confused with public exposure.

## 4. Required validation

Run focused tests first, then the complete previously accepted gates and adjacent suites.

Minimum focused evidence:

- non-empty job plus `NOTHING_RECORDED` cannot publish;
- all four canonical RunStore launcher paths persist non-empty identity;
- fresh launcher identity failure leaves no live process and no healthy attachment;
- fresh child identity failure leaves no live process and no healthy attachment;
- parallel initial and refill cancellation remain operable;
- arbitrary inherited extra name is refused;
- secret-shaped inherited extra value is refused;
- reviewed safe extra, if any, is admitted deliberately;
- publication fails after termination proof, returns honest partial outcome, and succeeds on exact retry without another termination call;
- KILL_ON_JOB_CLOSE crash simulation kills root, child and grandchild;
- deterministic child/worker/launcher ordering;
- actual public projections contain no identity values.

Regression floor:

- all 267 focused worker/process/adapter/foundation tests;
- all 217 adjacent tests;
- public gateway/schema and CF1 inventory hashes remain compatible;
- populated RunStore migration remains additive and idempotent;
- no process/cancellation test is deselected.

## 5. Acceptance gate

The process-identity gate closes only when:

- no contradictory evidence can authorise terminal cancellation;
- every new canonical launcher and child attachment has non-empty start identity or is contained and rejected;
- every parallel-group launcher path is covered;
- environment extras cannot bypass the positive policy by name or value;
- publication failure and retry are proven end to end;
- a Soma crash kills the entire Windows job tree;
- cancellation ordering tests are deterministic and meaningful;
- no identity value leaks through public projections;
- authority delta remains zero;
- all focused and adjacent tests pass;
- worktree is clean, an acceptance audit is recorded, and nothing is pushed.

## 6. Explicit exclusions

- real Claude Code or Codex launch;
- provider accounts, authentication, installation, upgrade or subscription purchase;
- live provider prompts or streams;
- native steering, supplied input, pause or resume;
- `STEER`, `SUPPLY_INPUT` or new task commands;
- operational `AWAITING_CONTROLLER`;
- public worker gateway or direct worker Soma MCP access;
- long-lived containment supervisor or handle-keeper;
- workflow/supervisor migration;
- V3-1B work;
- deployment, production activation, unrelated cleanup or push.

## 7. Stop conditions

Stop and return to architecture review if:

- crash containment requires a second lifecycle authority;
- a newly launched process must remain active without start identity;
- a live PID must be terminated without exact ownership proof;
- terminal publication can occur while the kernel reports assigned processes;
- safe publication retry requires changing the authoritative terminal result;
- public compatibility can be preserved only by hiding a misleading success response;
- the package expands into interaction commands or real provider execution.

## 8. Completion report

Report:

1. empty-row contradiction fix;
2. every canonical launcher and child attachment point;
3. fresh identity-capture failure containment;
4. inherited-extra positive policy;
5. exact publication failure/response/retry behavior;
6. KILL_ON_JOB_CLOSE implementation and crash proof;
7. deterministic ordering and fixture corrections;
8. public projection evidence;
9. focused and adjacent validation;
10. migration and compatibility evidence;
11. authority delta;
12. known limitations;
13. local commit hashes;
14. whether `V3-1A-PROCESS-IDENTITY-1` is ready for independent acceptance.

Do not start the next gate.
