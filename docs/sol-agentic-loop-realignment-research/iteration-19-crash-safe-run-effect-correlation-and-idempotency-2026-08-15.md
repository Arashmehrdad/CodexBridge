# Iteration 19 - Crash-Safe Run Effect Correlation and Idempotency

Date: 2026-08-15
Status: RESEARCH - focused alternative search after Iteration 17 attack
Track: Sol-centric agent interface / semantic continuation

---

# Research question

Iteration 17 found that Iteration 16 was too optimistic when it treated canonical Task and direct durable Run as equally strong `control_effect` sources.

Current Task creation already has durable controller request identity + request hash replay semantics.

Current direct `run_start` families do not expose an equivalent public stable request identity. `JobManager._create_and_launch()` normally generates a fresh Run ID internally.

This iteration asks:

> How should direct durable Run effects gain crash-safe correlation and idempotent replay without forcing every Run through canonical Task or creating a second generic executor?

---

# 1. Current Soma facts

## RunStore

Current `runs` rows have:

```text
run_id
repo_name
tool
status
state_version
input_json
result publication fields
worker/process identity
...
```

but no generic:

```text
controller_request_id
request_hash
```

`RunStore.create_run()` is a direct insert keyed by `run_id`.

## JobManager

Current `_create_and_launch()`:

1. normalizes repo/config inputs;
2. generates `run_id = reserved_run_id or make_run_id(tool)`;
3. acquires operation/repository lock when required;
4. creates run directory and input artifacts;
5. inserts durable Run row with status `launch_pending`;
6. records launch intent event;
7. starts worker;
8. records worker identity/state.

Internal `reserved_run_id` support already exists for selected callers such as canonical Task backend integration, but public `run_start` request variants do not expose a generic reserved ID or controller request identity.

## OperationLockStore

The repo lock can identify duplicate *active* tool/input fingerprints while a lock is held.

That is useful concurrency containment but is not durable request idempotency:

- it disappears when the operation releases the lock;
- it is repo-scoped rather than global logical-request scoped;
- some Run paths may not use the repository lock;
- it does not provide replay semantics after completion.

## Canonical Task precedent

TaskStore already does the stronger pattern:

```text
controller_request_id UNIQUE
request_hash
find_by_controller_request()
atomic reserve
same request + same hash -> return existing Task
same request + different hash -> conflict
```

The backend Run identity is reserved before external execution begins.

This is the semantic behavior direct Run creation is missing.

---

# 2. External durable-execution evidence

AWS Step Functions Standard `StartExecution` is idempotent for the same execution name and input while the execution is running: replay returns the same execution rather than creating another effect. Same name with different input conflicts.

Source:
- https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartExecution.html

Azure Durable external events explicitly document at-least-once delivery and recommend a unique ID for deduplication.

Source:
- https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-external-events

The general lesson is not to copy workflow engines. It is narrower:

> a side-effecting durable request that may be replayed across crashes needs a stable logical request identity plus payload-equivalence checking at the authority that actually launches the effect.

---

# 3. Alternative A - force direct Runs through canonical Task

Shape:

```text
Sol
 -> Task.start(controller_request_id)
 -> Task reserves backend Run
 -> Run launches
```

## Strengths

- already proven Task idempotency;
- backend identity reservation already exists;
- crash correlation is strong.

## Failures

### Semantic over-wrapping

Cloudflare/SSH/Docker/generic durable Run families already have Run as their direct canonical execution authority.

Wrapping every direct effect in Task merely for correlation makes Task a universal effect envelope again.

### Public/tool complexity

Sol would need to route ordinary domain actions through Task abstractions instead of natural domain gateways.

### Wrong architecture pressure

It would reward the exact Task-centric drift that Iterations 11-17 removed.

## Verdict

REJECT as the generic solution.

Task remains correct where Task is already the canonical effect authority.

---

# 4. Alternative B - expose caller-supplied stable `run_id`

Shape:

```text
run_start(..., run_id = stable_id)
```

Caller retries with the same ID after response loss.

## Strengths

- simple correlation;
- `run_id` already uniquely identifies Run authority;
- internal `reserved_run_id` proves much of the machinery can accept a preselected ID.

## Failures

### Existing replay behavior is not idempotent

Current `_create_and_launch()` creates the run directory before RunStore insert.

Retry after a completed/partially created Run can hit:

```text
run directory already exists
run row already exists
```

rather than intentionally returning the original Run projection.

### Caller now owns Run identity semantics

A public execution identity is being overloaded as both:

- canonical effect identity;
- client logical request/idempotency identity.

Those are related but not identical concepts.

### Different request under same Run ID

The design still needs normalized request hash conflict detection, so caller-supplied Run ID alone does not remove the core missing primitive.

## Verdict

IMPROVEMENT but insufficient alone.

A reserved Run ID can remain an internal optimization, but it should not be the entire public idempotency contract.

---

# 5. Alternative C - stable logical request identity on canonical Run creation

Shape:

```text
run_start(
  ...,
  controller_request_id = R
)

RunStore / JobManager normalize request -> H

R absent:
  current ordinary behavior may remain

R present:
  existing R + same H -> return existing Run
  existing R + different H -> conflict
  no R -> reserve one Run identity, then launch once
```

Conceptual Run additions:

```text
controller_request_id
request_hash
```

with partial/conditional uniqueness for non-empty request IDs.

## Strengths

### Authority-local idempotency

The authority that actually launches the direct Run owns replay protection.

No continuation-specific executor is needed.

### Preserves effect neutrality

Task effects use Task idempotency.

Direct Run effects use Run idempotency.

Continuation only derives/provides a stable request identity; it does not wrap either authority.

### Stable crash correlation

A pending effect intent can deterministically derive or store:

```text
run controller_request_id = continuation/intent scoped request identity
```

After response loss, fresh Sol can query/replay the exact request identity instead of searching recent Runs heuristically.

### General Soma improvement

This helps any caller that needs safe retry of durable Run creation, not just semantic continuation.

## Verdict

PREFERRED.

---

# 6. Alternative D - separate continuation-side effect reservation table

Shape:

```text
continuation_effect_reservations
  intent_id
  normalized request hash
  future effect kind
  maybe reserved run id
```

Then continuation launches the ordinary Run and later binds it.

## Strengths

- continuation can know intent identity before launch;
- no immediate change to Run public contract.

## Failures

### Idempotency is at the wrong layer

If the launch request is replayed, the Run authority still does not know it is a replay.

### Split authority

Continuation would become responsible for proving whether a Run launch already happened while RunStore remains unaware of the logical request identity.

### Pressure toward second executor

To close the gap robustly, the continuation layer would eventually need to mediate every launch.

That is exactly what this architecture should avoid.

## Verdict

REJECT as the primary fix.

Pending effect intent remains useful semantic provenance, but it must not substitute for effect-authority idempotency.

---

# 7. Preferred Run idempotency semantics

The public field name is still an implementation-planning choice. Existing Soma vocabulary strongly suggests `controller_request_id` for consistency with Task.

Required semantics when present:

```text
logical request ID R
normalized request hash H
```

### Replay

```text
existing R, existing H == H
 -> do not launch
 -> return existing Run identity/current projection
 -> created/replayed marker as appropriate
```

### Conflict

```text
existing R, existing H != H
 -> reject request identity/hash conflict
 -> do not launch
```

### First acceptance

```text
no existing R
 -> establish Run identity under unique R
 -> external launch can happen at most once from this accepted request reservation
```

---

# 8. Reservation ordering

A naive design that merely writes `controller_request_id` when `create_run()` is already called is not enough to reason about all races.

The launch path must guarantee that two concurrent requests with the same R cannot both pass the durable acceptance boundary and launch.

A compatible direction with current JobManager is:

1. normalize public request and compute H;
2. look up existing R before acquiring/launching;
3. perform existing policy/scope/lock preflight;
4. establish the Run row containing R/H **before worker/external launch**;
5. rely on DB uniqueness to choose one winner under concurrent insertion;
6. loser finds winner and returns replay/conflict;
7. only the winning durable Run reaches worker launch.

Important nuance:

- preflight refusal before any Run row/effect exists may remain retryable under the same logical request;
- durable acceptance must precede external launch;
- once accepted, same R must not create another Run.

The exact lock/row ordering needs implementation-level fault injection because current run directory/artifact creation occurs before the Run row insert.

---

# 9. Run directory/artifact race

Current sequence creates `run_dir` before DB Run insert.

With request-id concurrency, two requests on different lock domains or lock-free paths could potentially create separate temporary directories before the DB uniqueness winner is known.

This is not an external-effect duplication if only the DB winner launches, but implementation planning should avoid orphan artifacts.

Possible implementation patterns:

### Pattern 1 - durable row reservation first

Reserve Run row/R/H first, then create artifacts.

If artifact creation fails, mark the accepted Run as infrastructure failure/recovery state.

This gives the cleanest authoritative boundary.

### Pattern 2 - staged temporary artifact directory

Build in a temporary request-scoped staging location, reserve DB Run, then atomically promote staging only for the winner.

More machinery; likely unnecessary unless row-first staging conflicts with protected artifact assumptions.

Preferred for planning review: **row reservation first**, because current Run recovery semantics already know how to represent launch failure after durable acceptance.

---

# 10. Do not use OperationLock as idempotency authority

OperationLock remains resource serialization.

It may help a concurrent duplicate discover an active owner Run, but it must not be the canonical replay mechanism because:

- it is transient;
- it is scoped to repository/resource lock semantics;
- some effects may not use it;
- completed requests must still replay deterministically.

Keep:

```text
resource lock = conflict containment
request ID/hash = logical effect idempotency
```

separate.

---

# 11. Continuation integration

Continuation pending intent should hold or deterministically derive a stable logical effect request ID.

Example concept:

```text
intent_id = I
continuation_id = C

effect_request_id = H("soma.continuation.effect.v1", C, I)
```

The exact derivation domain belongs in implementation planning.

Then:

```text
Sol reserves intent I under continuation CAS
 -> calls direct run action using effect_request_id
 -> Run authority replay-protects launch
 -> returned run_id is linked as continuation source/provenance
```

If Chat disappears after launch response is lost:

```text
fresh Sol reuses effect_request_id
 -> Run authority returns original Run
 -> no heuristic "search recent runs" needed
```

This is a major improvement over Iteration 16.

---

# 12. Source adapter capability classes

Until Run idempotency exists, continuation must not advertise all direct Run actions as equally crash-safe controlled effects.

Conceptually distinguish:

```text
idempotent_effect_start
  stable request identity + hash conflict + replay

stable_effect_identity_only
  exact Run/Task identity once known, but launch replay not protected

best_effort_correlation
  only heuristic/provider evidence after a gap
```

Current canonical Task start qualifies for the first class.

Current generic direct Run start does not yet.

After preferred Run enhancement, selected Run families can qualify too.

---

# 13. Public compatibility

Do not require existing casual `run_start` callers to invent a request ID if they do not need retry semantics.

Preferred compatibility direction:

```text
controller_request_id = optional for ordinary direct calls
```

but continuation-controlled long effects require it.

This keeps fast-path ergonomics intact while giving strong callers a strong contract.

If implementation evidence shows optional idempotency creates confusing dual semantics, the plan can reconsider making it required for mutating durable Run starts, but that is not required by this research.

---

# 14. What about Cloudflare / SSH / Docker provider idempotency?

Run-level idempotency prevents Soma from launching the same accepted request twice.

It does **not** magically make every downstream provider operation exactly-once if a worker crashes after the provider commits but before Soma records success.

That existing problem remains represented by Run recovery/outcome uncertainty and provider-specific reconciliation.

Correct layered contract:

```text
controller request replay
 -> exactly one canonical Run launch attempt identity

inside Run/provider execution
 -> existing provider-specific outcome/recovery semantics
```

Do not overclaim end-to-end exactly-once external effects.

---

# 15. Failure tests

## Request replay

- same request ID + same normalized request -> same Run, no second worker launch;
- same request ID + different normalized request -> conflict;
- replay after Run completion -> original Run;
- replay after Run failure/recovery_pending -> original Run.

## Concurrency

- two simultaneous identical requests -> one Run row, one worker launch;
- simultaneous same ID/different hash -> one winner, one conflict;
- same ID on different repo/lock domains still cannot launch twice;
- lock-free eligible path still cannot launch twice.

## Fault boundaries

- crash after Run reservation before artifact staging -> durable failed/recoverable Run, replay returns same identity;
- crash after artifacts before worker -> same Run;
- crash after worker spawn before response -> replay finds same Run;
- response loss after accepted start -> replay returns same Run.

## Compatibility

- request ID omitted -> existing ordinary Run behavior remains valid;
- Task-backed Run path remains intact;
- no Task wrapper added around direct domain actions.

---

# 16. Result

**Iteration 19 verdict: ACCEPT ALTERNATIVE C.**

Best current architecture:

> Add provider-neutral stable logical request identity + normalized request hash replay semantics to the canonical Run creation authority itself. Keep caller-visible Run identity separate. Reserve durable Run authority before external launch. Continuation derives/provides the stable request identity for tracked effects but does not become an executor.

Reject:

- Task-wrapping every Run;
- caller-supplied Run ID as the sole idempotency mechanism;
- continuation-side reservation as a substitute for Run authority replay protection;
- OperationLock fingerprints as durable idempotency.

---

# Next research question

Iteration 20 should now solve the related same-continuation split-brain problem:

> How can multiple Sol/Chat contexts read/reason concurrently while preventing stale contexts from independently crossing the same durable side-effect boundary - without leases or locks around reasoning?
