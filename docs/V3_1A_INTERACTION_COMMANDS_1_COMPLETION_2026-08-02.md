# V3-1A Interaction Commands — Completion and Lane Audit

**Date:** 2026-08-02  
**Package:** `V3-1A-INTERACTION-COMMANDS-1`  
**Parent lane:** `V3-1A — Interactive Worker Substrate`  
**Verdict:** accepted and closed in source  
**Final implementation commit:** `bf455b1da14f1fd5f959483444efa66662a78844`  
**Push:** not authorised and not performed  
**Runtime activation:** pending a later controlled restart and connector refresh; no live-source claim is made before that gate

## 1. Accepted result

The interaction package now closes the controller-communication lifecycle over the existing canonical Task → Run authority without creating another task, run, lock, process, publication, scheduler, or acceptance authority.

The completed chain provides:

- canonical `steer` and `supply_input` command reservation;
- one shared transaction for canonical command plus subordinate typed message;
- complete sender, recipient, project, resource, task, run, provider-session, checkpoint, mandate, payload, state-version, and contract identity;
- one durable single-claimer transport attempt;
- non-terminal `awaiting_controller` Task and Run semantics;
- exact checkpoint and bounded deadline creation;
- acknowledgement-proven resume of the same Task, Run, session, worker identity, lease, and lock;
- deterministic provider-neutral stand-in transport and strict public `task_action` operations;
- idempotent checkpoint expiry with explicit recovery-window classification;
- canonical cancellation delegation through the existing durable backend;
- lock and resource ownership retention unless existing canonical authority proves quiescence or termination;
- crash, replay, cancellation, expiry, late-input, and late-acknowledgement race closure.

Real provider execution remains inactive. This lane proves the durable interaction contract and its authority boundaries; it does not claim a live Claude Code or Codex transport.

## 2. Implementation chain

The accepted interaction implementation is cumulative:

- `f6ba7ec42d9c5e1b59a26520a08abf130b1412ce` — canonical interaction command reservation;
- `02ebc01a815bba309789871fa94160905308292e` — complete message contract, atomic reservation, and transport-attempt foundation;
- `c89ead7f173a1d93bdfd961824db523dc4f70489` — atomic non-terminal controller waiting;
- `ac490f2f040251c83373afdb7e529389ec653cc5` — acknowledgement-driven resume;
- `06d75ca197eb43fc9a356e1a7f9315241d0e7193` — deterministic dispatch and strict public interaction actions;
- `bf455b1da14f1fd5f959483444efa66662a78844` — checkpoint expiry, recovery classification, backend cancellation delegation, and race closure.

Supporting evidence:

- [`V3_1A_INTERACTION_RESERVATION_FOUNDATION_RESULT_2026-08-02.md`](V3_1A_INTERACTION_RESERVATION_FOUNDATION_RESULT_2026-08-02.md)
- [`V3_1A_INTERACTION_WAIT_RESUME_RESULT_2026-08-02.md`](V3_1A_INTERACTION_WAIT_RESUME_RESULT_2026-08-02.md)
- [`V3_1A_DETERMINISTIC_INTERACTION_ACTIONS_RESULT_2026-08-02.md`](V3_1A_DETERMINISTIC_INTERACTION_ACTIONS_RESULT_2026-08-02.md)

## 3. Expiry and recovery closure

One central transition policy now classifies the exact checkpoint state as one of:

- no input reserved;
- pending and never attempted;
- in flight at expiry;
- unresolved claimed attempt;
- outcome unknown;
- acknowledged before resume;
- checkpoint resolved before Run resume;
- rejected before expiry.

The expiry transaction verifies the exact ProjectScope, Task, Run, session binding, checkpoint, deadline, state versions, and non-terminal status. It then records one immutable expiry, closes the exact checkpoint, marks only still-reserved messages expired, reserves one canonical cancellation command, moves the Task to cancellation/recovery pending, and writes correlated Task and Run evidence.

After that transaction commits, `TaskManager` delegates cancellation to the existing durable backend authority. The expiry coordinator does not terminate processes, publish results, release operation locks, or claim ownership transfer. Backend failure remains durable recovery evidence and restart repair can complete only the already-reserved cancellation path.

A late acknowledgement from a send already in flight remains preserved as transport evidence but cannot resume an expired checkpoint. Replay cannot resend the message. Late input, stale version, wrong checkpoint, wrong session, wrong scope, terminal state, and superseded state all fail closed.

## 4. Authority audit

Machine-checked final authority delta:

- new lifecycle table: **no**;
- new Task or Run lifecycle owner: **no**;
- new lock or lease owner: **no**;
- new scheduler or supervisor: **no**;
- new ResultPublication or OutcomeAcceptance authority: **no**;
- ownership release from expiry coordinator: **no**;
- cancellation delegated to existing durable backend: **yes**;
- explicit recovery windows: **yes**;
- real provider execution: **no**;
- worker-facing Soma MCP access: **no**.

`TaskStore` and `TaskManager` remain canonical for Task state and commands. `RunStore`, `JobManager`, process control, operation locks, and ResultPublication remain canonical for execution and containment. `WorkerSubstrateStore` records only subordinate provider-session, message, attempt, deadline, expiry, usage, and child-process evidence.

## 5. Validation

Final expiry and interaction-focused rerun:

- `20260802T201350Z_executable_profile_54bcc7b6` — **112 passed**.

Cancellation, process, lock, guard, and JobManager regression:

- `20260802T201500Z_executable_profile_7be640ea` — **189 passed, 1 expected xfail**.

Public gateway, request-model, discovery, inventory, and server regression:

- `20260802T201500Z_executable_profile_151ce173` — **184 passed**.

A first full run, `20260802T201810Z_executable_profile_b85239b8`, was cancelled by a separate request after 522 seconds. It emitted no test-failure result and is not used as acceptance evidence.

The clean replacement full repository baseline passed:

- `20260802T202857Z_executable_profile_0bba06f8` — **2673 passed, 35 skipped, 1 expected xfail** in 653.06 seconds.

Final mechanical and authority group:

- `20260802T204142Z_powershell_group_1fd90929` — compilation, Ruff, `git diff --check`, dependency integrity, and machine-checkable authority audit all passed.

## 6. Reliability and investigation notes

The first dedicated in-flight expiry replay test expected `ResumeTransitionConflict` on replay. The implementation correctly rejected earlier during atomic command reservation because expiry had advanced the Task state version, producing `InteractionStateConflict`. The assertion was corrected to the actual fail-closed boundary; no product defect was assigned.

A broad read-only source scan was blocked before execution by an external safety classifier. Bounded repository inspections replaced it and no state changed.

The cancelled first full baseline was replaced rather than interpreted. The replacement passed completely, proving that the cancellation was not accepted as validation evidence.

## 7. V3-1A lane audit

The parent V3-1A outcomes are now covered by the accepted foundation, adapter, process-identity, cancellation, interaction, wait/resume, dispatch, and expiry packages:

- exact provider-session binding and additive persistence;
- provider protocol fixtures and fail-closed capability declarations;
- fixed sanitised stand-in launch environment;
- exact launcher and provider-child process identity;
- identity-proven zero-orphan cancellation and lock retention on uncertainty;
- raw provider-native usage evidence;
- non-terminal waiting and bounded expiry;
- crash-safe steering and supplied input;
- restart repair without blind resend;
- invalid or uncertain session/transport states preserved for adjudication;
- no direct worker access to Soma MCP.

Therefore `V3-1A — Interactive Worker Substrate` is accepted and closed in source. Its new source is not yet active in the running service; activation remains a separate controlled operational gate and does not block architecture work on the next roadmap outcome.

## 8. Next roadmap decision

The current authoritative V3 sequence names `V3-1B — Kernel of One` next. The immediate next package is a documentation-only architecture gate, not implementation and not a real-provider launch.

That gate must prove how Company, Mission, immutable current PlanRevision, bounded WorkPackage, route-specific canonical Task attempts, route-independent outcome identity, and one crash-safe AcceptanceCommit fit around existing ProjectScope, Task, Run, and ResultPublication authority without copying their lifecycle.

Real provider execution, production activation, departments, broad worker capabilities, external business mutation, deployment, and push remain inactive.

## 9. Memory continuity procedure

After every accepted slice, material incident, acceptance decision, or roadmap transition, the development agent must update the authoritative result/gate documents and `PLANS.md`, commit those records locally, and refresh canonical repository knowledge before beginning the next implementation package. Chat history alone is not accepted as project memory.
