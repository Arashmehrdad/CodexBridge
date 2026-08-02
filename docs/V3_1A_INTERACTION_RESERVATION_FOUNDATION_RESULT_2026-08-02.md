# V3-1A Interaction Reservation Foundation — Result

**Date:** 2026-08-02  
**Parent package:** `V3-1A-INTERACTION-COMMANDS-1`  
**Status:** accepted and closed as the first implementation slice  
**Commits:**

- `f6ba7ec42d9c5e1b59a26520a08abf130b1412ce` — canonical interaction command reservations
- `02ebc01a815bba309789871fa94160905308292e` — atomic message reservations and transport attempts

**Push:** not authorised and not performed.

## 1. Accepted outcome

Soma now has the durable reservation foundation required by the accepted interaction architecture without exposing a public interaction command or launching a provider.

One shared SQLite transaction can reserve:

- one canonical `steer` or `supply_input` task command;
- one subordinate generic message envelope;
- one complete normalized contract hash;
- exact project, resource, task, run, session, checkpoint, sender, recipient, and optional mandate references;
- one content-addressed payload identity;
- an initial message disposition proving that no transport attempt has begun.

A crash leaves both command and message records or neither. The worker substrate still cannot write canonical Task or Run lifecycle state.

## 2. Canonical command authority

The canonical task plane adds only two command kinds:

- `steer`;
- `supply_input`.

It adds no Task kind, backend kind, lease owner, scheduler, result publisher, or execution lifecycle. A connection-scoped command reservation primitive lets a narrow coordinator participate in the existing shared-main-store transaction while TaskStore remains the command authority.

Caller idempotency is unique per task and command kind. Identical replay returns the original command. A replay with changed requested or observed state-version identity fails explicitly.

## 3. Generic message contract

The subordinate message envelope records:

- canonical command ID;
- exact project/resource/task/run/session/checkpoint identities;
- sender and recipient references;
- optional mandate reference and version;
- typed message class;
- narrow public command kind;
- caller idempotency key;
- payload reference, hash, and byte count;
- requested task state version;
- complete contract hash;
- subordinate delivery disposition.

The complete contract hash covers every decision-bearing field. Changed recipient, checkpoint, session, payload, command kind, authority reference, or state version is therefore a conflict rather than an accidental replay.

Informational message classes exist as internal typed semantics but have no lifecycle behavior in this slice.

## 4. Transport-attempt evidence

Each message may receive at most one durable transport attempt. The attempt record distinguishes:

- claimed;
- outcome unknown;
- acknowledged;
- rejected;
- prevented.

A second sender cannot claim the message. An identical claimer replay receives the same durable attempt. Once the attempt becomes outcome-unknown, replay returns that same evidence and cannot create a resend.

Claim creation rechecks canonical precedence available at this layer, including terminal, cancellation-pending, recovery-pending, uncertain, superseded, session-binding, checkpoint-open, and checkpoint-expiry evidence. Attempt evidence does not resume a task, release ownership, or publish a result.

## 5. Historical compatibility

Worker-substrate schema v2 is additive:

- existing v1 tables remain unchanged and readable;
- no historical row is backfilled with invented sender, recipient, mandate, command, contract, or attempt evidence;
- new tables are `worker_messages` and `worker_transport_attempts`;
- subordinate columns and values avoid canonical lifecycle vocabulary;
- exact canonical task-command identity is read for correlation but never written by the substrate.

A SQLite backup of the live store was migrated twice. Both passes converged at task schema v2 and worker-substrate schema v2 with:

- `PRAGMA integrity_check = ok`;
- zero foreign-key violations;
- every expected table present;
- worker migration versions `[1, 2]` exactly once;
- no change to the live database migration count.

## 6. Reliability defect closed in source

The concurrency gate reproduced a Windows content-addressed payload race. Two identical writers could both observe an absent target; the winner installed the immutable blob, while the losing `os.replace` raised `PermissionError: [WinError 5]`.

The fix accepts a concurrent winner only after verifying that the installed regular file has the exact expected byte length and SHA-256. A missing or mismatched target remains a hard evidence conflict. Temporary files are removed in every path. The direct regression runs eight identical writes across four threads and proves one reference, one hash, exact bytes, and no surviving temporary file.

This is recorded as `REL-026`. It is source-fixed but not represented as live until the V3-1A source is activated through a later approved restart.

## 7. Validation

Focused gate:

- run `20260802T180753Z_executable_profile_f40652f8`;
- **95 passed**;
- covers atomic rollback, identical concurrency, conflicting replay, complete-contract identity, one transport claim, outcome-unknown no-resend, cancellation precedence, stale state refusal, checkpoint identity, payload secrecy, migration, and authority boundaries.

Adjacent gate:

- run `20260802T180848Z_executable_profile_3a00a9b8`;
- **270 passed, 1 expected xfail**;
- covers adapter contracts, worker process identity, cancellation authority and closure, and ProjectScope foundation.

Copied-live migration:

- run `20260802T180847Z_executable_profile_8563f697`;
- integrity and foreign keys green; migration idempotent; live source untouched.

Static gates:

- compilation passed;
- Ruff passed;
- `git diff --check` passed.

## 8. Authority delta

Added authority:

- canonical TaskStore recognises two new command kinds and remains their sole owner;
- WorkerSubstrateStore owns subordinate message and transport evidence only;
- InteractionCoordinator coordinates one shared transaction but owns no lifecycle state.

Not added:

- no second Task or Run lifecycle;
- no lock or resource owner;
- no process launcher or cancellation authority;
- no result or acceptance publisher;
- no scheduler, supervisor, team, role, mandate authority, or capability broker;
- no public operation;
- no real provider transport.

## 9. Next active slice

The next slice is the central non-terminal wait/resume transition policy:

- enter `awaiting_controller` atomically with one exact open checkpoint and deadline;
- preserve the same Task, Run, session, lease, and repository/resource ownership;
- keep ResultPublication and terminal timestamps untouched;
- resume only after exact acknowledged input and a fresh precedence check;
- make cancellation, expiry, supersession, stale state, and technical recovery outrank acknowledgement;
- recover acknowledgement-before-resume idempotently without sending again.

Public `steer` and `supply_input` remain inactive until this lifecycle layer and deterministic stand-in transport both pass.
