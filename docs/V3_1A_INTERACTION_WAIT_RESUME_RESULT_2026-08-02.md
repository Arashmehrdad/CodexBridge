# V3-1A Interaction Wait/Resume — Result

**Date:** 2026-08-02  
**Parent package:** `V3-1A-INTERACTION-COMMANDS-1`  
**Status:** accepted and closed as the lifecycle-semantics slice  
**Commits:**

- `c89ead7f173a1d93bdfd961824db523dc4f70489` — atomic non-terminal controller waiting
- `ac490f2f040251c83373afdb7e529389ec653cc5` — acknowledged input resume semantics

**Push:** not authorised and not performed.

## 1. Accepted outcome

Soma now has one central policy for entering and leaving a non-terminal controller wait without creating a second Task, Run, checkpoint, delivery, or publication lifecycle.

The same canonical Task, Run, ProjectScope, provider-session binding, worker lease, worker PID/start identity, repository lock, and result-publication identity are preserved across:

1. `running` → `awaiting_controller`;
2. one exact open checkpoint plus bounded deadline;
3. durable `supply_input` reservation and acknowledged transport evidence;
4. `awaiting_controller` → `running` after all precedence checks pass.

Historical `needs_input` rows remain terminal compatibility records and are never reinterpreted as resumable V3 work.

## 2. Atomic wait entry

One shared SQLite transaction:

- validates ProjectScope, Task/Run, session, and state-version identity;
- derives one deterministic checkpoint identity from the task and caller wait identity;
- creates one exact open checkpoint and bounded deadline;
- moves Task to `awaiting_controller` with an explicit task phase;
- moves Run to non-terminal `awaiting_controller` with `requires_human=true`;
- appends correlated Task and Run events carrying the wait contract hash.

The transition refuses terminal result or publication evidence, ended runs, stale versions, wrong scope/session, a second open checkpoint, or a deadline that is not in the future. A failure after any intermediate write rolls back every authority record.

The transition does not:

- set `ended_at`;
- write a terminal result;
- invoke ResultPublication;
- release the repository lock;
- change worker lease, PID, start identity, or process ownership.

Identical and concurrent replay converges on one checkpoint, one deadline, one pair of events, and one canonical Task/Run transition.

## 3. Acknowledged input resume

Resume accepts only one exact generic message that:

- belongs to the waiting Task/Run/session/checkpoint;
- is a canonical `supply_input` command;
- has command or decision semantics, not informational semantics;
- is durably acknowledged;
- has one acknowledged transport attempt with a non-empty evidence reference.

Before resuming, the central policy rechecks:

- ProjectScope and provider-session binding;
- Task and Run waiting states and state versions;
- exact open checkpoint and checkpoint-required version;
- message requested state version;
- bounded deadline and durable expiry evidence;
- cancellation, supersession, terminal result, and publication state;
- canonical worker lease token/generation;
- PID-reuse-resistant worker PID/start identity.

One transaction then:

- resolves the checkpoint exactly once;
- completes the exact canonical task command;
- clears the Task checkpoint reference;
- returns the same Task and Run to running;
- clears `requires_human`;
- appends correlated Task and Run resume events.

The transaction preserves the same lock, session, Task ID, Run ID, worker identity, lease identity, and publication state.

## 4. Crash, replay, and precedence evidence

The focused gate proves:

- crash after durable acknowledgement but before resume is repaired by a fresh policy instance without sending again;
- repeated and concurrent resume calls converge on one canonical transition and one event pair;
- outcome-unknown delivery is not resumptive and is never resent;
- progress reports remain lifecycle-inert even when acknowledged;
- cancellation after acknowledgement outranks resume;
- elapsed deadline and durable expiry-row evidence outrank resume;
- supersession outranks resume;
- unverified session identity blocks resume;
- missing worker start identity blocks resume;
- stale state versions leave the checkpoint open;
- failure after checkpoint resolution rolls the checkpoint, command, Task, Run, events, and lock state back atomically.

Acknowledgement is therefore evidence, not lifecycle authority.

## 5. Authority delta

Added:

- connection-scoped Task command completion and checkpoint resolution;
- connection-scoped Task/Run state and event primitives;
- one central wait/resume policy over existing authorities;
- distinct non-terminal Run status `awaiting_controller`.

Not added:

- no new Task or Run manager;
- no new scheduler, lease owner, lock owner, process owner, result publisher, or acceptance authority;
- no public interaction command;
- no provider process or account use;
- no direct worker Soma MCP access;
- no reinterpretation or migration of historical `needs_input` rows.

## 6. Validation

Resume-specific gate:

- `20260802T183927Z_executable_profile_eb5ab51c` — **24 passed**.

Full authority gate:

- `20260802T184042Z_executable_profile_d3da975b` — **153 passed**.

Runtime-adjacent gate:

- `20260802T184042Z_executable_profile_083711e0` — **384 passed, 1 expected xfail**.

Server and public-contract gate:

- `20260802T184042Z_executable_profile_a0a976a9` — **341 passed**.

Static gates:

- compilation passed;
- Ruff passed;
- `git diff --check` passed.

## 7. Next active slice

The next slice is deterministic stand-in dispatch and narrow public interaction commands:

- one provider-neutral internal transport port;
- deterministic acknowledgement, rejection, uncertainty, and crash-window stand-ins;
- dispatch only after durable attempt claim;
- capability-honest `steer` behavior;
- exact `supply_input` wait/resume integration;
- public `task_action` request models and discovery derived from the same runtime contract;
- no payload echo and no payload in logs, events, argv, or ordinary projections;
- no real Claude Code or Codex process, account, prompt, or stream.

Real provider execution remains a later package.
