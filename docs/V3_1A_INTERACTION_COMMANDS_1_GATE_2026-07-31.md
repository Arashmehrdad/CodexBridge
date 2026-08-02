# V3-1A-INTERACTION-COMMANDS-1 — Canonical Controller Interaction and Non-Terminal Waiting

**Date:** 2026-07-31
**Status:** accepted and closed in source. Completion: [`V3_1A_INTERACTION_COMMANDS_1_COMPLETION_2026-08-02.md`](V3_1A_INTERACTION_COMMANDS_1_COMPLETION_2026-08-02.md).
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Depends on:** accepted process-identity foundation, the owner-accepted hierarchical-intelligence contract, accepted [`V3_1A_INTERACTION_FOUNDATION_ARCHITECTURE_REVIEW_2026-07-31.md`](V3_1A_INTERACTION_FOUNDATION_ARCHITECTURE_REVIEW_2026-07-31.md), and its binding [`V3_1A_INTERACTION_FOUNDATION_ARCH_REVIEW_ACCEPTANCE_AUDIT_2026-08-02.md`](V3_1A_INTERACTION_FOUNDATION_ARCH_REVIEW_ACCEPTANCE_AUDIT_2026-08-02.md)
**Activation baseline:** `dc24bcd2642e7c15b6ff524ec0edea500daf93d5`
**Push:** not authorised.

## 1. Objective

Make controller interaction a real part of the existing canonical Task → Run lifecycle without launching a real provider.

This package must prove that Soma can:

- enter a genuinely non-terminal controller-wait state;
- expose an exact durable checkpoint with a bounded deadline;
- accept version-guarded `STEER` and `SUPPLY_INPUT` task commands;
- persist interaction payload and delivery intent before any transport attempt;
- resume the same task, run, provider-session binding, and checkpoint after acknowledged input;
- fail closed on crash windows, replay conflicts, delivery ambiguity, cancellation races, and deadline expiry.

The package is an interaction and lifecycle-semantics gate. It is not a provider-launch gate.

## 1.1 Accepted architecture corrections

The architecture hold is closed. Implementation must follow the binding acceptance audit and add, at minimum:

1. one generic typed internal message envelope while public operations remain only `steer` and `supply_input`;
2. exact sender and recipient references plus an optional mandate/version reference, without implementing permanent roles or authority graphs;
3. one normalized complete contract hash covering every decision-bearing identity and field;
4. connection-scoped canonical command and subordinate message inserts under one shared `TaskStore.transaction()` boundary;
5. a separate durable transport-attempt record and single-claimer transition that distinguishes never attempted from outcome unknown;
6. one central wait/resume and precedence policy that rechecks cancellation, expiry, supersession, authority version, checkpoint, session, ProjectScope, and technical execution state;
7. typed informational message classes that cannot change lifecycle or imply substantive acceptance;
8. zero blind resend from uncertain or outcome-unknown attempts;
9. an authority-delta audit proving the package added no generic lifecycle manager, lock owner, result publisher, scheduler, or acceptance authority.

The current worker-substrate v1 records are inert historical-compatible foundations. Their existing rows must not be backfilled with invented sender, recipient, mandate, contract, or attempt evidence.

## 1.2 Implementation progress

The reservation foundation is accepted and closed at commits `f6ba7ec42d9c5e1b59a26520a08abf130b1412ce` and `02ebc01a815bba309789871fa94160905308292e`. Its result is [`V3_1A_INTERACTION_RESERVATION_FOUNDATION_RESULT_2026-08-02.md`](V3_1A_INTERACTION_RESERVATION_FOUNDATION_RESULT_2026-08-02.md).

Completed:

- canonical `steer` and `supply_input` command reservation;
- one shared transaction for canonical command plus subordinate generic message;
- exact sender, recipient, session, checkpoint, optional mandate, payload, state-version, and complete contract identity;
- one durable single-claimer transport attempt;
- outcome-unknown evidence that cannot create a resend;
- additive schema v2 with copied-live migration proof;
- Windows-safe concurrent content-addressed payload writes.

The lifecycle-semantics slice is accepted and closed at commits `c89ead7f173a1d93bdfd961824db523dc4f70489` and `ac490f2f040251c83373afdb7e529389ec653cc5`. Its result is [`V3_1A_INTERACTION_WAIT_RESUME_RESULT_2026-08-02.md`](V3_1A_INTERACTION_WAIT_RESUME_RESULT_2026-08-02.md).

Completed:

- central atomic non-terminal `awaiting_controller` transition;
- exact checkpoint and bounded deadline creation;
- historical terminal `needs_input` compatibility;
- evidence-proven resume of the same Task, Run, session, worker identity, lease, and lock;
- central cancellation, expiry, supersession, stale-state, and technical-recovery precedence;
- restart repair for acknowledgement-before-resume without resend;
- idempotent and concurrent wait/resume convergence;
- rollback after intermediate checkpoint, command, Task, or Run mutation.

The deterministic transport/public-command slice is accepted and closed at commit `06d75ca197eb43fc9a356e1a7f9315241d0e7193`, incorporating the reconciled work from commits `105da47dde70bafae38764808605c86e47b91b9e` and `3c94db4df67399a9ddfa236b48c3d3985f59892c`. Its result is [`V3_1A_DETERMINISTIC_INTERACTION_ACTIONS_RESULT_2026-08-02.md`](V3_1A_DETERMINISTIC_INTERACTION_ACTIONS_RESULT_2026-08-02.md).

Completed:

- one provider-neutral reference-only interaction transport port;
- deterministic acknowledgement, rejection, outcome-unknown, and crash-window stand-ins;
- one durable single-claimer dispatcher with no resend from unresolved or uncertain attempts;
- capability-honest Claude steering and explicit Codex steering refusal;
- narrow strict public `steer` and `supply_input` task actions;
- payload secrecy and bounded no-echo public projections;
- public discovery, runtime models, TaskManager behavior, and CF1 inventory convergence;
- fresh-process import-order repair and permanent regression;
- full repository regression floor of 2657 passed, 35 skipped, and 1 expected xfail.

The final expiry/recovery slice is accepted and closed at commit `bf455b1da14f1fd5f959483444efa66662a78844`. Its completion and parent-lane audit is [`V3_1A_INTERACTION_COMMANDS_1_COMPLETION_2026-08-02.md`](V3_1A_INTERACTION_COMMANDS_1_COMPLETION_2026-08-02.md).

Completed:

- one central idempotent checkpoint-expiry processor;
- explicit recovery classification for pending, claimed, uncertain, acknowledged, resolved, rejected, and in-flight windows;
- atomic checkpoint expiry, message expiry, canonical cancellation reservation, and correlated Task/Run evidence;
- cancellation delegation through the existing durable backend authority;
- no ownership release from the expiry coordinator;
- restart repair after expiry-before-delegation;
- cancellation-before-send, cancellation-during-send, late-acknowledgement, late-input, stale-version, and replay closure;
- focused, adjacent, public-contract, full-repository, static, dependency, and authority gates.

Final full regression: **2673 passed, 35 skipped, 1 expected xfail**. Real provider execution remains inactive and the running service remains on the prior build.

## 2. Existing authorities that remain canonical

- `TaskStore` and `TaskManager` own task identity, task state, task commands, state-version guards, checkpoints, and public task projections.
- `RunStore`, `JobManager`, and `job_worker` own durable execution, leases, process ownership, cancellation, terminal transitions, repository locks, evidence, and ResultPublication.
- `WorkerSubstrateStore` owns subordinate provider-session, interaction-delivery, checkpoint-deadline, expiry, usage, and provider-child evidence only.
- `ProjectScope` owns project, repository, task, run, and resource coherence.
- Provider adapters declare capabilities and parse protocol evidence; they do not own task state or canonical success.

No new lifecycle manager, result publisher, lease owner, scheduler, supervisor, or approval authority may be introduced.

## 3. Binding lifecycle contract

### 3.1 Non-terminal waiting

`AWAITING_CONTROLLER` must become operationally non-terminal.

The implementation must not continue treating a controller wait as a finished durable run. Prefer a new canonical durable-run status such as `awaiting_controller` rather than changing the meaning of historical `needs_input` rows in place.

A waiting run must retain:

- its canonical task and run identity;
- the same provider-session binding;
- the same repository/resource ownership unless quiescence is separately proven;
- its state version, lease generation, and recovery evidence;
- one exact open checkpoint;
- one durable bounded deadline or an explicit owner-approved no-deadline policy.

Entering controller wait must not write a terminal result, mark `ended_at`, publish ResultPublication, or release locks merely because input is required.

### 3.2 Waiting transition

The transition into `AWAITING_CONTROLLER` must be compare-and-set guarded and durably couple:

1. the canonical task/run identity;
2. an open task checkpoint;
3. the exact provider-session binding when one exists;
4. checkpoint context and expected input schema;
5. a checkpoint deadline record;
6. a non-terminal run/task state transition;
7. an event that lets recovery distinguish a completed transition from a crash window.

Use one transaction where the records share the same SQLite database. Where a filesystem payload must be written first, it remains inert until the database transaction commits.

### 3.3 Resume after input

Acknowledged supplied input may return the same task and run from `AWAITING_CONTROLLER` to `RUNNING` only when:

- task state version matches the command request;
- the checkpoint is still open;
- the checkpoint belongs to the same task;
- the expected provider-session binding matches exactly;
- the interaction delivery is durably `acknowledged`;
- cancellation has not won;
- deadline expiry or recovery adjudication has not superseded the checkpoint.

The checkpoint resolves exactly once. Repeated identical acknowledgement is idempotent. Conflicting acknowledgement or input is rejected.

## 4. Task command contract

### 4.1 Additive command kinds

Add canonical task commands:

- `steer`;
- `supply_input`.

`cancel` remains unchanged and authoritative.

The task capability projection and public `task_action` discovery may advertise the new commands only when runtime validation and manager behavior accept the exact same request shape.

### 4.2 Common command fields

Each interaction command requires:

- exact `project_id` and `task_id`;
- `if_state_version`;
- caller-provided idempotency identity;
- exact interaction kind;
- payload bytes supplied through the gateway but stored content-addressed outside the database;
- payload reference, SHA-256, and byte count in durable records;
- expected provider-session binding identity;
- expected checkpoint identity where applicable;
- bounded public response and no payload echo.

The command line, event message, exception text, and ordinary task/run rows must never contain the secret-bearing payload.

### 4.3 `SUPPLY_INPUT`

`SUPPLY_INPUT` is valid only against the exact open checkpoint of a task currently awaiting controller input.

It must:

1. validate ProjectScope and task/run/session/checkpoint coherence;
2. verify the requested task state version;
3. persist the payload content-addressed;
4. atomically reserve the canonical task command and subordinate interaction intent before delivery;
5. attempt delivery once through the provider-neutral transport port;
6. durably record acknowledged, rejected, or uncertain evidence;
7. resolve the checkpoint and resume the same run only after durable acknowledgement.

A rejected command leaves the checkpoint open unless the rejection proves the checkpoint or session invalid, in which case the task becomes recovery-pending or uncertain with explicit evidence.

### 4.4 `STEER`

`STEER` may be accepted only while the task is non-terminal and the bound adapter honestly declares steering support for that provider/session mode.

It does not require an open input checkpoint unless the command names one. It never resolves an unrelated checkpoint.

Codex steering remains unsupported unless a genuine reviewed protocol fixture and adapter capability already prove otherwise. The gate must not fabricate support merely to exercise the command.

## 5. Persist-before-send and delivery evidence

No interaction transport may be called until both of these are durable:

- the canonical task-command reservation;
- the subordinate interaction record with payload identity and delivery `pending`.

The implementation may use a shared transaction or an explicit coordinator over the shared database, but it must preserve the authority boundary: the substrate does not become the task-command owner, and TaskStore does not become provider-delivery evidence storage.

Delivery dispositions remain:

- `pending` — durably reserved, not yet proven delivered;
- `acknowledged` — exact provider/session evidence confirms acceptance;
- `rejected` — exact evidence confirms refusal without ambiguity;
- `uncertain` — a send or acknowledgement crash window cannot be adjudicated safely.

`pending` may be attempted once. `uncertain` is never blindly resent. Recovery must require exact provider evidence or explicit adjudication.

## 6. Deterministic transport boundary

Add or complete one internal provider-neutral interaction transport interface with deterministic stand-in implementations for tests.

The transport accepts only:

- exact session binding;
- interaction identity and kind;
- content-addressed payload reference;
- expected checkpoint identity;
- adapter capability evidence.

It returns structured acknowledgement, rejection, or uncertainty evidence.

This gate must not:

- execute Claude Code or Codex;
- invoke a provider account;
- send a live provider prompt;
- parse a new live stream;
- use stdin or an external process as a disguised provider transport.

Frozen fixtures may be used only to verify contract mapping and capability honesty.

## 7. Cancellation, concurrency, and replay

Cancellation wins every race.

Required invariants:

- cancellation requested before delivery prevents transport;
- cancellation racing delivery leaves the task cancellation-pending or cancelled, never resumed;
- a late acknowledgement cannot reopen a cancelled or terminal task;
- a late supplied input cannot resolve an expired, cancelled, superseded, or differently versioned checkpoint;
- steering cannot advance task state by itself;
- same idempotency key plus identical full command contract returns the existing command and interaction;
- same idempotency key plus different payload, kind, session, checkpoint, or requested state version raises an explicit replay conflict;
- concurrent identical requests create one durable command and one interaction;
- concurrent conflicting requests produce one winner and one conflict, not duplicate sends.

## 8. Deadline and expiry behavior

Every production-default controller checkpoint is bounded.

Expiry processing must:

1. observe the deadline against the exact open checkpoint;
2. record one immutable expiry event idempotently;
3. refuse late input from resolving the expired checkpoint;
4. request bounded pause or cancellation through existing canonical process authority when appropriate;
5. release repository/resource ownership only after accepted quiescence or zero-descendant proof;
6. otherwise move to recovery-pending or uncertain and retain/quarantine ownership.

The clock alone never authorises lock release, terminal publication, or a fresh provider attempt.

## 9. Recovery behavior

Recovery must distinguish:

- interaction durably pending and never attempted;
- transport attempted but acknowledgement absent;
- acknowledged interaction whose checkpoint transition was interrupted;
- checkpoint resolved but task/run resume transition interrupted;
- checkpoint expired while delivery was in flight;
- invalid or mismatched provider-session identity.

Recovery may complete an idempotent local projection when exact durable evidence already proves the outcome. It may not resend uncertain interaction bytes or create a clean replacement provider session silently.

## 10. Required tests

Minimum behavioral evidence:

- enter `AWAITING_CONTROLLER` with open checkpoint and bounded deadline;
- waiting is absent from terminal run/task vocabularies and ResultPublication is not invoked;
- waiting retains repository ownership unless quiescence is proven;
- acknowledged `SUPPLY_INPUT` resolves the exact checkpoint and resumes the same task/run/session;
- rejected input leaves an honest open or recovery state;
- uncertain delivery remains non-terminal and is not resent;
- `STEER` succeeds only for a capability-declared stand-in adapter;
- Codex steering is rejected as unsupported;
- payload never appears in argv, events, ordinary database projections, logs, or public responses;
- payload reference integrity and tamper detection remain green;
- stale state version, wrong project, wrong task, wrong session, wrong checkpoint, closed checkpoint, and terminal task all fail closed;
- identical replay is idempotent; conflicting replay is rejected;
- persist-before-send is proven by a transport spy that inspects durable records during dispatch;
- simulated crash before send leaves pending unsent evidence;
- simulated crash after send before acknowledgement becomes uncertain and is not retried;
- cancellation-before-send, cancellation-during-send, and late-acknowledgement races all preserve cancellation authority;
- deadline expiry records one immutable event and never releases ownership without quiescence proof;
- recovery completes only evidence-proven local projections;
- public discovery and runtime schemas remain identical;
- existing process, cancellation, ProjectScope, task-plane, adapter, and substrate suites remain green.

## 11. Regression floor

At minimum preserve:

- the accepted process/cancellation focused gate: **413 passed, 1 xfailed**;
- the full repository baseline: **2556 passed, 35 skipped, 1 xfailed**;
- Windows `KILL_ON_JOB_CLOSE`, PID-reuse, escaped-descendant, cancellation ordering, publication retry, and lock-retention evidence;
- additive RunStore and substrate migrations;
- no direct worker Soma MCP access;
- no increase in generic lifecycle authority beyond the explicitly authorised task command kinds and canonical non-terminal state semantics.

## 12. Explicit exclusions

- real Claude Code or Codex launch;
- provider accounts, authentication, installation, upgrade, or purchase;
- live provider prompts or streams;
- provider-specific transport implementation;
- automatic clean-session replacement;
- pause/resume beyond the exact checkpoint semantics required here;
- broad workflow or supervisor migration;
- worker-facing Soma MCP or capability broker work;
- Company Kernel or V3-1B work;
- departments, scheduling, business mutations, deployment, production activation, or push;
- fixing the pre-existing `worker_identity` public exposure unless separately authorised.

## 13. Stop conditions

Stop and return to architecture review if:

- interaction delivery requires a second task or run lifecycle;
- the substrate would need to write canonical task state directly;
- payload bytes must be placed in command lines, events, or ordinary public records;
- waiting cannot remain non-terminal under canonical Task → Run;
- cancellation cannot deterministically win against delivery and acknowledgement;
- uncertain delivery would need automatic resend;
- expiry would require lock release without quiescence proof;
- provider execution is required to demonstrate the contract;
- public discovery and runtime validation cannot be derived from the same request models.

## 14. Completion report

Report:

1. canonical waiting state and durable checkpoint transition;
2. task command and gateway additions;
3. command/interaction atomicity or recovery protocol;
4. payload storage and secrecy evidence;
5. transport interface and capability declarations;
6. `SUPPLY_INPUT` behavior;
7. `STEER` behavior and unsupported-provider handling;
8. delivery dispositions and crash-window recovery;
9. cancellation and concurrency race results;
10. checkpoint deadline and expiry results;
11. migration and compatibility evidence;
12. focused and full validation;
13. authority and public-contract delta;
14. known limitations;
15. local commit hashes;
16. exact next gate recommendation.

Implement this package under the accepted audit and stop at its completion gate. Do not begin real provider execution, production activation, deployment, push, V3-1B, or broader organisational state.
