# V3-1A-CANCELLATION-AUTHORITY-1 — Identity-Proven Canonical Cancellation

**Date:** 2026-07-30
**Status:** implementation submitted at `c1c5b535e9bb95b14b701546ce716653faf6688d`; independent acceptance failed; final closure subgate active.
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Depends on:** failed acceptance audit [`V3_1A_PROCESS_IDENTITY_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_PROCESS_IDENTITY_1_ACCEPTANCE_AUDIT_2026-07-30.md)
**Repository baseline:** `99bb7631d38cf8e6391d7a5d7d0168fd46faf96d`
**Push:** not authorised.

**Audit:** [`V3_1A_CANCELLATION_AUTHORITY_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_CANCELLATION_AUTHORITY_1_ACCEPTANCE_AUDIT_2026-07-30.md)
**Final corrective gate:** [`V3_1A_CANCELLATION_CLOSURE_1_GATE_2026-07-30.md`](V3_1A_CANCELLATION_CLOSURE_1_GATE_2026-07-30.md)

This corrective package remains unaccepted. Its final closure work is governed by the linked gate; no interaction-command or later V3 package is active.

## 1. Objective

Close the process-identity gate by making local cancellation identity-proven from canonical launch through terminal publication.

This is a corrective package, not a new roadmap lane. It may strengthen `RunStore`, `JobManager`, `process_control`, and the internal `worker_process` boundary only where required to remove raw-PID action, contain attachment failures, and prove zero owned descendants. It does not authorise real Claude or Codex launch.

## 2. Owner-approved cancellation contract

The owner approved the following externally visible safety behavior on 2026-07-30:

> When a PID is live but Soma lacks an exact matching recorded process-start identity, Soma must not terminate it. The canonical run remains `cancellation_pending`, durable uncertainty is recorded, and the repository lock remains held.

A live PID with a mismatching identity is a different process. Soma must not terminate or enumerate that process tree. The original recorded process may be treated as absent only when identity mismatch is positively proven.

Tests must supply valid ownership evidence. They may not restore green status by allowing raw-PID termination or weakening terminal-cancellation assertions.

## 3. Canonical authority boundary

- `RunStore` owns durable launcher, worker, and child process identities as part of the canonical run record.
- `JobManager` owns cancellation state, terminal transition, lock release, and ResultPublication.
- `process_control` owns exact process identity, kernel-backed containment primitives, and identity-scoped termination evidence.
- `WorkerSubstrateStore.worker_child_processes` remains subordinate provider-tree observation evidence.
- `worker_process` may construct and verify cancellation proof; it may not publish run state or results.

No new lifecycle manager, lease authority, result publisher, repository lock, task command, or public gateway is permitted.

## 4. Required outcomes

### 4.1 Canonical launcher and child identity

Add additive, migration-safe canonical run fields for:

- `launcher_identity` paired with `launcher_pid`;
- `child_identity` paired with `pid`.

Capture them at the same canonical attachment points that persist the corresponding PIDs. Existing `worker_identity` remains authoritative for `worker_pid`.

Requirements:

- populated databases migrate idempotently without historical invention;
- historical live PIDs with empty identities remain uncertain, never retroactively trusted;
- read/public projections remain compatible unless an additive internal field is intentionally surfaced;
- all ownership-sensitive writes remain compare-and-swap or lease-scoped where the existing path requires it.

### 4.2 Identity-first local cancellation

Before local cancellation acts on launcher, worker, child, provider root, or descendant:

1. require a recorded start identity;
2. read the live identity;
3. if the exact identity matches, termination may proceed;
4. if the PID is not running, the recorded process is absent;
5. if the live identity differs, refuse action against the new occupant and record PID-reuse evidence;
6. if the live identity cannot be read, refuse termination and keep cancellation pending.

No descendant enumeration may occur until the root identity is proven to match.

### 4.3 Kernel-backed Windows containment

Parent-link snapshots and `taskkill /T` may remain supporting mechanisms, but they are insufficient as the sole zero-descendant proof.

For Windows stand-in launch, introduce a kernel-backed Job Object or an equivalently strong owned-process containment primitive that:

- is created before or immediately around process creation without an uncontained healthy window;
- assigns the root before attachment can report healthy;
- contains later descendants even if the root exits or descendants are reparented;
- supports bounded termination of the owned job;
- supports a post-termination proof that no process remains assigned;
- fails closed when assignment or query is unavailable;
- does not require a provider binary or provider account.

Any unavoidable micro-window must be described and tested with containment fallback. The gate may not claim zero descendants from parent-table enumeration alone.

### 4.4 Attachment failure containment

After a process is created, any failure to capture or persist root/descendant identity must:

- refuse `ATTACHED`;
- mark the provider binding unverified or uncertain;
- terminate or contain the entire kernel-owned process set;
- report containment proof honestly;
- retain uncertainty if zero processes cannot be proven.

Identity-less descendants may not be silently skipped while attachment reports healthy.

### 4.5 Environment additions remain fail closed

`allowlist_extra` and `environment_additions` must not reintroduce:

- provider recursion markers;
- Soma/MCP/controller configuration;
- secret-shaped names;
- arbitrary inherited tool configuration.

Define a narrow positive policy for deliberate internal additions. Reject forbidden names and values before process creation. Evidence continues to record names and classifications only, never values.

### 4.6 Empty evidence is not proof

`NOTHING_RECORDED` must not independently authorise terminal cancellation.

A no-process terminal path is permitted only when `JobManager` proves from canonical run state and launch evidence that process creation never occurred. Otherwise an empty subordinate process set is uncertainty and the lock remains held.

### 4.7 Canonical publication and retry

After zero-owned-process proof:

- terminal cancellation transition remains canonical and idempotent;
- ResultPublication failure is persisted honestly;
- retry publishes the exact same terminal result without repeating unsafe termination;
- lock release follows proven process absence and canonical ownership rules;
- cancellation response, durable state, terminal result, publication state, and lock state agree.

The package must not fabricate publication success merely because process termination succeeded.

## 5. Required tests

### Canonical identity and migration

- additive migration on a representative populated RunStore;
- launcher/child identities are captured with their PIDs;
- historical PID with empty identity is uncertain and never terminated;
- PID reuse mismatch causes zero termination calls;
- identity-read failure causes zero termination calls, cancellation pending, and lock retention.

### Environment and attachment

- recursion, MCP, and secret-shaped names are rejected from both extras and additions;
- root identity failure after creation contains the job/tree;
- descendant enumeration failure contains the job/tree;
- descendant identity failure contains the job/tree;
- descendant persistence failure contains the job/tree;
- no failure path reports healthy attachment while a process may remain.

### Cancellation topology and races

- real Windows Job Object root/child/grandchild termination proof;
- root exits while a child or grandchild remains assigned, then cancellation proves the job empty;
- a late descendant spawned during cancellation remains contained and is terminated;
- cancellation races normal root exit;
- taskkill or another termination primitive reports success while a process remains, and publication is refused;
- cancellation replay after confirmed termination is idempotent;
- empty subordinate rows without canonical pre-launch proof do not authorise publication.

### Publication and compatibility

- `test_cancel_run_marks_cancelled` is repaired with provable fixture ownership;
- the existing child-then-worker ordering and lock assertions remain meaningful;
- publication failure after termination proof is persisted and succeeds on retry;
- public gateway/schema inventories remain unchanged unless an explicitly reviewed additive change is unavoidable;
- accepted 34 process, 208 adapter/foundation, and adjacent run/process suites remain green.

## 6. Acceptance gate

This corrective package closes only when:

- every local termination target is identity-proven;
- no raw-PID termination path remains in canonical local cancellation;
- kernel-backed containment proves zero owned Windows descendants, including after root exit and reparenting;
- environment extras/additions cannot bypass sanitisation;
- every post-launch attachment failure is contained or durably uncertain;
- terminal cancellation cannot follow empty subordinate evidence without canonical pre-launch proof;
- publication retry evidence is complete;
- the known host-dependent cancellation test is deterministic and green;
- focused and adjacent suites pass without deselecting a process/cancellation failure;
- authority delta remains zero;
- worktree is clean, acceptance evidence is recorded, and nothing is pushed.

## 7. Explicit exclusions

- real Claude Code or Codex launch;
- provider authentication, accounts, installation, upgrade, or subscription purchase;
- live provider prompts or streams;
- provider-native steering or supplied input;
- `STEER`, `SUPPLY_INPUT`, pause, resume, or new task commands;
- operational `AWAITING_CONTROLLER` continuation;
- public worker gateway or direct worker Soma MCP access;
- V3-1B Company/Mission/PlanRevision/WorkPackage/AcceptanceCommit work;
- workflow or supervisor migration;
- deployment, production activation, unrelated cleanup, or push.

## 8. Stop conditions

Stop and return to architecture review if:

- Windows kernel-backed containment cannot be implemented without a second lifecycle or ownership authority;
- a provider process must be launched to prove containment;
- canonical cancellation must terminate a live process without exact ownership proof;
- terminal publication or lock release can occur while an owned process may remain;
- migration would invent identities for historical records;
- safe correction requires weakening an accepted external cancellation guarantee;
- the package expands into interaction commands, V3-1B, or broad lifecycle consolidation.

## 9. Completion report

Report:

1. exact canonical identity fields and migration;
2. all launch/attachment points updated;
3. Windows containment design and alternatives rejected;
4. identity-first cancellation behavior;
5. environment correction;
6. attachment crash-window evidence;
7. root-exit, late-descendant, normal-exit-race, and publication-retry results;
8. cancellation baseline correction;
9. focused and adjacent validation;
10. authority and public-contract delta;
11. known limitations;
12. local commit hashes;
13. exact next V3-1A gate.

Do not start the next gate.
