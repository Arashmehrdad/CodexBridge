# V3-1A — Interactive Worker Substrate

**Date:** 2026-07-30
**Status:** active lane; the interaction-foundation architecture review is accepted and `V3-1A-INTERACTION-COMMANDS-1` is the sole active implementation package. Real provider execution, production activation, deployment, and push remain unauthorised.
**Activation baseline:** `lane/memory-integration-foundation-1` at `dc24bcd2642e7c15b6ff524ec0edea500daf93d5`.
**Architecture:** [`SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md`](SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md)
**Reconciliation:** [`SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md`](SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md)
**Organisational contract:** [`SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`](SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md)
**Accepted review:** [`V3_1A_INTERACTION_FOUNDATION_ARCHITECTURE_REVIEW_2026-07-31.md`](V3_1A_INTERACTION_FOUNDATION_ARCHITECTURE_REVIEW_2026-07-31.md)
**Acceptance audit:** [`V3_1A_INTERACTION_FOUNDATION_ARCH_REVIEW_ACCEPTANCE_AUDIT_2026-08-02.md`](V3_1A_INTERACTION_FOUNDATION_ARCH_REVIEW_ACCEPTANCE_AUDIT_2026-08-02.md)

## 1. Goal

Extend Soma's existing canonical Task → Run authority with one bounded, provider-neutral interactive worker substrate for Claude Code and Codex native sessions.

The lane proves that a short worker session can be launched, steered, supplied input, suspended for a controller, recovered by exact provider identity after process death, cancelled without an orphan, and measured without creating a second execution lifecycle or relying on conversation history as canonical state.

## 2. Why this lane comes first

The Company Kernel requires interactive chunk-by-chunk work. The repository already owns durable task identity, run leases, process reconciliation, cancellation, result publication, ProjectScope, evidence, and repository locks. It does not yet own the production contract for provider-native session identity, crash-safe interaction delivery, non-terminal controller waiting, exact session resume, child-process start identity, or native usage events.

The accepted provider pilot proved capability availability. It did not implement this integration.

## 3. Binding authority boundary

### Canonical owners retained

- `TaskStore` and `TaskManager`: public work identity, TaskAdmission, state, task commands, checkpoints, links, and reconciliation projection.
- `RunStore`, `JobManager`, and `job_worker`: process/worker leases, launch, running state, cancellation, recovery, terminal result, and ResultPublication.
- `ProjectScope`: exact project/resource binding and task/run reservations.
- `OperationLockStore`: repository write ownership where required.
- `process_control`: process-start identity, tree termination, and PID-reuse protection.

### Subordinate records this lane may add

- provider-session binding: exact project/task/run/provider/native-session/adapter/protocol identity and recovery cursor;
- interaction delivery: persist-before-send messages, payload references/hashes, acknowledgements, and durable uncertain delivery;
- provider-child identity: PID plus process-start identity and cancellation evidence;
- raw usage events: provider-native token, cost, turn, and session units with deterministic deduplication.

These records may not own task admission, queued/running/waiting/terminal state, leases, cancellation, result publication, or executive outcome acceptance.

### Progressive convergence

This lane consolidates worker waiting, steering, supplied input, cancellation, and provider-session recovery into the canonical Task → Run path.

Workflows and supervisors are generic compatibility lifecycle managers. V3-1A does not need their multi-step territory and must not broaden into their migration. A later lane that first uses equivalent planning or collaboration responsibilities must project or retire the overlap under the progressive-convergence gate.

## 4. Terminology

- **TaskAdmission:** durable admission to the canonical task plane. Existing `TaskState.ACCEPTED` means this only.
- **ResultPublication:** a run published an exact terminal result and hash.
- **OutcomeAcceptance:** later V3-1B executive selection of one published result for one WorkPackage outcome.
- **Provider session:** opaque native conversation/session identity subordinate to one canonical run.
- **Interaction delivery:** transport evidence for steering or supplied input; it is not a task lifecycle.

## 5. Required outcomes

1. One additive interactive-worker task contract launches through the existing Task → Run authority.
2. A provider-neutral adapter contract supports exact native session identity, event parsing, explicit-ID resume, usage extraction, cancellation, and declared capability support.
3. Claude closes steering, supplied input, explicit resume, cancellation, context-retention, and raw-usage gates.
4. Codex closes exact identity, explicit resume, cancellation, context-retention, and raw-usage gates. Steering remains honestly unsupported until measured and implemented.
5. Interaction messages are committed before send, deduplicated by caller identity and payload hash, and acknowledged durably.
6. Unprovable send/ack crash windows become durable uncertainty; they are never blindly resent.
7. `AWAITING_CONTROLLER` is operationally non-terminal and resumes the same task/run/provider session.
8. Every open controller checkpoint has a durable deadline and explicit expiry disposition.
9. Provider child PID and process-start identity are persisted before the session can report healthy running state.
10. Cancellation verifies zero owned descendants before terminal cancellation publication.
11. Raw provider usage is stored without inventing missing dollar values and can be aggregated by session, run, and task.
12. Launch uses an exact executable identity and a sanitised environment with provider-recursion markers, inherited MCP configuration, and unrelated credentials removed.
13. Protocol fixtures are versioned, parser drift fails closed, and unknown provider events cannot fabricate progress or success.
14. The worker receives no direct Soma MCP access and cannot discover or invoke a Soma operation.
15. Existing task, run, ProjectScope, workflow, supervisor, SSH, Trading Lab, memory, research, and public-gateway compatibility remains intact.

## 6. Waiting and timeout invariants

Every controller-wait checkpoint has a durable deadline or explicit no-deadline owner policy. The production default is bounded.

On expiry:

1. record an immutable checkpoint-expiry event;
2. attempt a bounded provider-native pause when supported, otherwise request canonical cancellation/containment;
3. transition to `PAUSED` and release repository/resource ownership only after the provider worker and all owned descendants are confirmed quiescent or terminated and the provider session remains explicitly resumable;
4. otherwise transition to `UNCERTAIN`, retain ownership or quarantine as required, and require recovery adjudication.

Timeout never means permission to release a lock while a process may still mutate.

## 7. Session invalidation and recovery

Recovery always uses an exact stored native session identity. “Resume last” is forbidden.

If the native session is missing, invalid, corrupt, protocol-incompatible, or cannot be proven to match the binding:

- preserve the original task, run, workspace, interaction, and provider evidence;
- publish durable recovery uncertainty with a precise reason;
- do not automatically launch a clean replacement attempt;
- allow an executive recovery action to adopt existing evidence, supersede through a new canonical task/run, or stop.

A fresh attempt is a new route-specific canonical task, not silent continuation of the invalid session.

## 8. Interaction command invariants

V3-1A may add task commands for steering and supplying input. Each command requires:

- caller-provided idempotency identity;
- exact task ID and requested task state version;
- payload reference and content hash rather than secret-bearing command-line text;
- expected checkpoint/session identity where applicable;
- one durable delivery disposition: pending, acknowledged, rejected, or uncertain;
- replay conflict when the same idempotency identity carries different content.

Cancellation wins races against steering or input. A late acknowledgement cannot restore a cancelled task.

## 9. Parallel implementation streams

Shared contracts and migrations are frozen first. After that, bounded non-overlapping streams may proceed:

### A. Provider adapter

Native Claude and Codex command construction, event fixtures, session identity, explicit resume, capability declaration, and usage parsing.

### B. Durability and interaction

Additive session, message/acknowledgement, checkpoint, and raw-usage persistence plus task command semantics.

### C. Process and security

Sanitised environment, executable identity, provider-child process-start identity, cancellation, descendant proof, and secret/MCP exclusion.

### D. Verification

Crash-window, replay, restart, protocol-drift, cancellation, ProjectScope, compatibility, and Windows process integration tests.

One integration owner reconciles shared files. Two streams may not edit the same authority-bearing file concurrently without an explicit handoff.

## 10. Required evidence

### Interaction durability

- crash after message commit but before send;
- crash after send but before acknowledgement;
- crash after acknowledgement but before task transition;
- duplicate same-content replay;
- conflicting-content replay;
- steering racing cancellation;
- input resolving a stale checkpoint.

### Recovery

- Soma restart while adapter/provider session remains active;
- adapter death with provider child still active;
- explicit-ID resume after all worker processes stop;
- missing/corrupt native session produces uncertainty, not blind restart;
- checkpoint deadline expiry across restart;
- stale or mismatched provider-session binding fails closed.

### Process and security

- PID reuse or child start-identity mismatch;
- Windows tree cancellation for Claude and Codex;
- zero owned descendants before terminal cancellation;
- sanitised environment excludes provider recursion, MCP, and unrelated credential variables;
- no worker Soma MCP discovery or invocation.

### Usage and protocol

- duplicate usage events across resume are deduplicated;
- Claude provider-reported USD remains raw evidence;
- Codex token counts remain raw evidence without fabricated USD;
- known fixtures parse deterministically;
- unknown or changed events fail closed without invented success.

### Compatibility

- existing canonical task recovery and JobManager recovery tests pass;
- legacy durable-command requests and hashes remain unchanged;
- public schema changes are additive and receive connector-refresh evidence;
- existing workflow/supervisor records remain readable;
- ProjectScope strict isolation remains enforced;
- no historical record is backfilled with invented session or usage identity.

## 11. Stop conditions

Stop and return to architecture review when:

- a provider session needs its own queued/running/terminal lifecycle manager;
- `needs_input` must be reinterpreted incompatibly instead of adding an interactive path;
- a message can be delivered twice after a crash or replay;
- checkpoint expiry releases ownership while mutation may continue;
- cancellation can publish terminal state with an owned descendant alive;
- explicit-ID resume cannot be distinguished from starting a fresh session;
- provider protocol drift can fabricate a successful result;
- worker execution requires direct Soma MCP access;
- implementation requires V3-1B, departments, generic mutation, or broad lifecycle consolidation;
- existing task/run or ProjectScope compatibility cannot be preserved.

## 12. Acceptance gate

V3-1A closes only when:

- all required outcomes are implemented and evidenced;
- focused and adjacent regression tests pass;
- at least one real Windows subprocess integration path passes for each provider;
- restart, interaction, cancellation, protocol, and usage evidence is preserved with exact hashes/references;
- the authority-delta audit confirms no new generic lifecycle authority;
- the worktree is clean and the documentation/result record is complete;
- nothing is pushed without separate owner instruction.

## 13. Explicit exclusions

- V3-1B Company, Mission, PlanRevision, WorkPackage, WorkPackageAttempt, or AcceptanceCommit implementation;
- direct worker Soma MCP access or the role-scoped capability broker;
- departments, collaboration rooms, organisation reconciliation, or A/B/C comparison;
- scheduled autonomous continuation;
- generic external mutation, CRM, billing, Higgsfield, Tavus, or workspace integration;
- company-global memory or third-party personal-data architecture;
- workflow/supervisor migration beyond documenting the authority boundary;
- unrelated retirement, cleanup, deployment, or push.

## 14. Completion report

Report:

- files and public contracts changed;
- provider capabilities actually proven;
- tests and real-process evidence;
- task/run authority delta;
- compatibility bridges and retirement conditions;
- known limitations;
- exact next V3-1A package or, only after lane closure, the decision for V3-1B.

## 15. Current package status

### V3-1A-FOUNDATION-1 — accepted and closed

The shared contracts and additive persistence package is accepted after independent audit and corrective commit `c11919e7410faef7c351b318de396000845e8e5a`. Its evidence is [`V3_1A_FOUNDATION_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_FOUNDATION_1_ACCEPTANCE_AUDIT_2026-07-30.md).

The accepted foundation remains inert: no provider process launch, public worker operation, task-command expansion, or production substrate row exists.

### V3-1A-ADAPTER-CONTRACT-1 — accepted and closed

The provider-neutral adapter and fixture package is accepted after independent audit and corrective commit `7d629c5bdd0ade1d3d0da262bcd8509f50744041`. Its evidence is [`V3_1A_ADAPTER_CONTRACT_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_ADAPTER_CONTRACT_1_ACCEPTANCE_AUDIT_2026-07-30.md).

The accepted adapter remains inert. It launches no provider, applies no environment, publishes no task outcome, and exposes no public operation.

### V3-1A-PROCESS-IDENTITY-1 — accepted and closed

The cumulative process-identity chain is accepted at runtime commit `7cc66c50675a91ff958d39a3c53e6246a88268d6`. The original submissions and failed audits are retained as evidence of the corrective path; the final verdict is [`V3_1A_PROCESS_IDENTITY_1_FINAL_ACCEPTANCE_AUDIT_2026-07-31.md`](V3_1A_PROCESS_IDENTITY_1_FINAL_ACCEPTANCE_AUDIT_2026-07-31.md).

The accepted boundary includes sanitised stand-in launch, exact launcher/child identities, identity-proven cancellation, positive environment policy, `KILL_ON_JOB_CLOSE`, root-exit/tree-exit separation, zero-descendant proof, lock retention on uncertainty, honest publication retry, deterministic cancellation ordering, additive migration, compatibility preservation, and zero generic lifecycle-authority increase.

### SOMA-V3-ORG-CONTRACT-1 — owner-accepted

The authoritative organisational model is [`SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`](SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md).

### V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1 — accepted and closed

The package [`V3_1A_INTERACTION_FOUNDATION_ARCHITECTURE_REVIEW_2026-07-31.md`](V3_1A_INTERACTION_FOUNDATION_ARCHITECTURE_REVIEW_2026-07-31.md) passed independent audit. The accepted transaction, delivery-attempt, wait/resume, message-class, identity, and precedence contract is recorded in [`V3_1A_INTERACTION_FOUNDATION_ARCH_REVIEW_ACCEPTANCE_AUDIT_2026-08-02.md`](V3_1A_INTERACTION_FOUNDATION_ARCH_REVIEW_ACCEPTANCE_AUDIT_2026-08-02.md).

### V3-1A-INTERACTION-COMMANDS-1 — active

The implementation gate is [`V3_1A_INTERACTION_COMMANDS_1_GATE_2026-07-31.md`](V3_1A_INTERACTION_COMMANDS_1_GATE_2026-07-31.md). It is reactivated around the smallest durable communication substrate and must implement the acceptance-audit corrections before any real provider package.

Real providers, permanent teams, broad capability delegation, V3-1B work, and production activation remain later and inactive.
