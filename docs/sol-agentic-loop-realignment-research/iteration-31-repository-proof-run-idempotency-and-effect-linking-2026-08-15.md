# Iteration 31 - Repository Proof: Direct Run Idempotency and Continuation Effect Linking

Date: 2026-08-15
Status: RESEARCH EVIDENCE / IMPLEMENTATION REQUIREMENT CORRECTION
Scope: validate two infrastructure recommendations from Iteration 30 directly against the current Soma repository
Implementation authorization: none

---

# Executive verdict

Both recommendations survive repository audit, but they do not have the same current implementation readiness.

## Recommendation A - general direct Run idempotency

**CONFIRMED AS A REAL REPOSITORY GAP AND A WELL-PLACED SOMA IMPROVEMENT.**

Current direct `run_start` paths do not expose or persist a stable logical request identity equivalent to canonical Task `controller_request_id + request_hash`.

A retry after a lost response can therefore become a new logical Run invocation rather than a replay of the original Run. Existing repository locks are not a durable idempotency contract and cannot substitute for one.

The correct home is the existing Run authority:

```text
RunStart public request
 -> JobManager normalization/admission
 -> RunStore logical request reservation/replay
 -> canonical Run identity
 -> worker launch/recovery
```

Do not solve this by wrapping every direct Run in Task or by making continuation own Run execution.

## Recommendation B - atomic continuation effect linking

**CONFIRMED AS A CORRECT ARCHITECTURAL REQUIREMENT, WITH AN IMPORTANT IMPLEMENTATION DISTINCTION.**

For canonical Task effects, the repository already exposes the exact shared-transaction seam needed for atomic linking.

For direct Run effects, the same SQLite database is shared, but `RunStore.create_run()` currently owns its own connection and transaction. Therefore atomic Run + continuation-link reservation does **not** exist yet.

The correct requirement is:

```text
Task association:
  use existing caller-owned Task transaction seam

Run association:
  first add a caller-owned / connection-scoped Run reservation seam
  then reserve Run row + continuation effect link atomically
  commit before worker launch
```

Do not claim atomic Run effect linking before that seam exists and is proven.

---

# 1. Repository state examined

Primary current files:

```text
soma/run_store.py
soma/job_manager.py
soma/gateway_models.py
soma/tasks/schema.py
soma/tasks/store.py
soma/tasks/manager.py
soma/tasks/backends.py
soma/workflows/worker.py
soma/company_kernel/schema.py
```

The analysis deliberately compares direct Run behavior against already accepted Soma patterns rather than importing a foreign execution architecture.

---

# 2. Direct Run start currently lacks logical replay identity

`RunStore` creates the authoritative `runs` table in `runs/soma.sqlite3`.

Current identity is:

```text
run_id TEXT PRIMARY KEY
```

The Run row has no generic equivalent of:

```text
controller_request_id
request_hash
```

There is no unique logical invocation identity by which a repeated direct `run_start` request can say:

```text
this is the same logical request as before
```

rather than:

```text
please create another Run
```

`RunStore.create_run()` currently performs an unconditional insert by `run_id`:

```text
INSERT INTO runs (...)
```

and returns that Run.

There is no lookup-before-create by stable logical request ID and no same-ID/different-hash conflict contract.

Conclusion: the direct Run authority currently has identity for **execution instances**, not for **logical request replay**.

---

# 3. Public `run_start` does not currently provide that identity

Current `RunStartRequest` variants include forms such as:

```text
LocalPowerShellStart
RemotePowerShellStart
ParallelPowerShellStart
HermesCompanionStart
HermesServiceStart
```

The ordinary direct Run request models do not expose one generic stable controller request identity.

`ParallelPowerShellChild` has a child-local `idempotency_key`, but that is not a general top-level direct Run replay contract and does not solve ordinary `powershell` / `remote_powershell` / other durable Run starts.

This confirms the gap exists at the public invocation boundary as well as in RunStore persistence.

---

# 4. JobManager creates a fresh execution identity for ordinary direct starts

`JobManager._create_and_launch()` currently does:

```text
run_id = reserved_run_id or make_run_id(tool)
```

For an ordinary public direct start, `reserved_run_id` is absent, so a new Run ID is allocated for each invocation.

The function then:

```text
acquires applicable operation lock
creates run directory
writes/stages input artifacts
creates Run row as launch_pending
records durable launch intent
spawns worker
records worker launch identity
```

This is good persist-before-worker-launch behavior.

But it does not answer a different question:

```text
Was this invocation already durably accepted earlier under the same logical request?
```

If a response is lost after acceptance/launch and the caller repeats the same public request, there is no general persisted logical request identity that maps the retry back to the original Run.

That is the exact reason general Run idempotency is useful.

---

# 5. Repository locking is not Run idempotency

Soma operation locks can reject a duplicate active operation on a locked repository when the tool/input fingerprint matches.

That does not provide the same contract as durable logical request replay.

Reasons:

1. operation locks are scoped to active resource/repository ownership, not permanent logical request identity;
2. after terminal completion/release, the same request can legitimately acquire the lock again;
3. some Run paths may use different lock semantics or intentionally no repository lock;
4. a duplicate-active refusal does not return the canonical prior Run as an idempotent replay contract;
5. idempotency must survive response loss and caller retry independently of whether a resource is still locked.

Therefore:

```text
operation lock != idempotency key
```

Both may coexist, but they solve different problems.

---

# 6. Canonical Task already proves the desired Soma-native pattern

The Task plane provides the strongest local precedent.

`tasks` includes:

```text
controller_request_id TEXT NOT NULL
request_hash TEXT NOT NULL
```

with:

```text
UNIQUE INDEX idx_tasks_controller_request
ON tasks(controller_request_id)
```

`TaskStore.reserve_task_in_connection()` performs:

```text
find existing by controller_request_id

if found:
    same request_hash -> return existing Task, created=False
    different request_hash -> TaskRequestConflict

else:
    insert canonical Task
```

`TaskManager.start_durable_command()` also handles concurrent identical requests and explicitly returns the winner rather than launching a second backend Run.

The source comment states the intended invariant directly:

```text
Concurrent identical request won the reservation.
Never launch a second backend run.
```

This is not a speculative foreign pattern. Soma already uses it successfully for canonical Task creation.

---

# 7. Therefore the direct Run recommendation should mirror the semantic pattern, not Task itself

The recommended Run contract is:

```text
logical_run_request_id
normalized_request_hash
```

Semantics:

```text
new request ID
 -> reserve one canonical Run

same request ID + same normalized hash
 -> return the existing Run
 -> do not launch another worker

same request ID + different normalized hash
 -> hard request identity conflict

concurrent same ID + same hash
 -> exactly one Run reservation wins
 -> all callers resolve to that Run
```

Naming remains an implementation-plan choice. The important part is the identity semantics, not whether the field is literally named `controller_request_id`.

The logical request identity must remain distinct from `run_id`:

```text
logical request ID = invocation/replay identity
run_id             = canonical execution identity
```

This preserves existing Run semantics and makes retries safe.

---

# 8. Existing reserved Run IDs prove identity can be allocated before launch

Soma already supports an internal `reserved_run_id` seam.

Examples:

```text
DurableRunBackend.reserve()
 -> make_run_id(...)

DurableRunBackend.start(..., backend_ref)
 -> JobManager.start_executable_profile(..., reserved_run_id=backend_ref)
```

Canonical Task therefore owns a Run identity before the Run worker is started.

The Workflow worker uses the same architectural pattern:

```text
allocate child_run_id
claim/persist workflow step with child_run_id
start JobManager child using reserved_run_id=child_run_id
verify launched run_id == child_run_id
```

This proves an important point for future implementation:

> Run identity reservation-before-launch already fits Soma's execution architecture.

What direct Run idempotency lacks is persistent **logical request replay**, not the ability to predetermine a Run ID.

---

# 9. Task effect linking has a real atomic transaction seam today

`TaskStore` uses the same `runs/soma.sqlite3` database as RunStore.

`tasks/schema.py` states explicitly that Task tables live next to the authoritative `runs` table in the existing database.

`TaskStore.transaction()` exposes a public narrow caller-owned `BEGIN IMMEDIATE` transaction.

`TaskStore.reserve_task_in_connection()` accepts that caller-owned SQLite connection.

`TaskManager.start_durable_command()` already uses this seam to atomically coordinate:

```text
ProjectScope task-attempt reservation
canonical Task reservation
ProjectScope Task attachment
```

before backend execution.

Therefore, if continuation persistence is also placed in the existing main Soma SQLite store as Iteration 30 proposes, a future Task effect association can mechanically do:

```text
BEGIN IMMEDIATE
  validate current continuation contract/context ref
  reserve canonical Task via reserve_task_in_connection
  insert continuation_effect_link(task_id, ...)
COMMIT

existing Task backend starts afterward
```

That is a repository-backed claim, not an architectural guess.

---

# 10. Direct Run effect linking does NOT yet have the same seam

Although RunStore and TaskStore use the same database path:

```text
runs/soma.sqlite3
```

current `RunStore.create_run()` opens its own connection internally:

```text
with self.connect() as conn:
    INSERT INTO runs ...
```

There is currently no public equivalent of:

```text
reserve_run_in_connection(conn, ...)
```

Therefore a future continuation component cannot today place:

```text
Run reservation
+
continuation effect link
```

inside one caller-owned SQLite transaction.

This is the key correction to the earlier shorthand claim.

The theory must say:

> Atomic Task effect linking is already supported by an existing transaction seam. Atomic direct Run effect linking requires adding an equivalent connection-scoped Run reservation primitive first.

---

# 11. Correct Run-side target seam

The implementation thread should investigate a narrow RunStore primitive conceptually equivalent to:

```text
reserve_run_in_connection(
    conn,
    logical_request_id,
    request_hash,
    run_id,
    repo_name,
    tool,
    run_dir,
    input_data,
    ...,
)
```

It should perform only durable reservation/replay logic.

It must not spawn a worker.

Desired transaction when continuation association is requested:

```text
prepare/stage non-authoritative filesystem material as needed

BEGIN IMMEDIATE
  replay/conflict check by logical Run request ID
  reserve canonical Run row as launch_pending if new
  insert continuation effect link if new
COMMIT

if replay:
  return existing Run
  do not launch again

if newly reserved:
  continue through existing JobManager launch/recovery machinery
```

Exact filesystem ordering is an implementation concern and must preserve current recovery invariants. A leftover pre-created run directory is preferable to a duplicate external effect; no worker may launch before the durable Run reservation and requested continuation link are committed.

---

# 12. Why effect linking belongs beside reservation rather than after launch

If linking is performed only after an effect has already launched:

```text
reserve/launch Run E
 -> client/Chat disappears
 -> continuation link never written
```

then fresh Sol may have to infer association from timing/input similarity.

That is exactly the ambiguity the effect-link feature exists to remove.

For supported associated effects, the durable relationship should therefore exist no later than canonical effect reservation.

The effect authority still owns execution:

```text
Task owns Task state
Run owns Run state
ProjectScope owns scope authority
JobManager owns worker launch/recovery
```

The continuation link is only provenance/origin.

It must not become a second executor or lifecycle authority.

---

# 13. Effect-link omission remains allowed

Iteration 30 deliberately keeps continuation association optional.

Ordinary Soma calls must remain valid without a continuation context ref.

Therefore effect linking is not a universal security boundary and Soma must not claim:

```text
all effects belonging to an objective are known
```

It can only claim:

```text
these canonical effects were mechanically associated with this continuation/context revision
```

This honesty boundary remains part of the accepted design.

---

# 14. Required proof obligations for direct Run idempotency

The implementation thread should not declare the feature accepted without at least these mechanical proofs:

1. same logical request ID + same normalized request -> same Run ID;
2. same logical request ID + different normalized request -> hard conflict;
3. two concurrent identical starts -> one Run row and one worker launch;
4. response lost after durable acceptance -> retry returns the same Run;
5. response lost after worker launch -> retry returns the same Run and does not spawn another worker;
6. replay after terminal completion -> same historical Run, not a new execution;
7. ordinary request without logical idempotency identity preserves existing behavior if backward compatibility requires it;
8. repository-lock duplicate detection remains independent and is not treated as replay identity;
9. Run ID remains canonical execution identity;
10. recovery_pending/outcome uncertainty is replayed conservatively rather than retried as a new Run.

---

# 15. Required proof obligations for atomic effect linking

## Task

1. current continuation context/contract validated inside caller-owned transaction;
2. canonical Task reserved through `reserve_task_in_connection`;
3. continuation effect link inserted in same transaction;
4. any link failure rolls back Task reservation;
5. backend execution begins only after commit;
6. replayed Task request returns existing Task/link without duplicate execution;
7. current Task truth remains in Task authority, never copied into continuation table.

## Run

1. connection-scoped Run reservation primitive exists;
2. logical Run replay check and Run reservation occur inside caller-owned transaction;
3. continuation effect link is inserted in the same transaction as new Run reservation;
4. worker launch occurs only after commit;
5. link failure means no worker launch;
6. lost response replay resolves by logical Run request identity;
7. Run recovery/lifecycle remains solely under RunStore/JobManager;
8. no filesystem staging failure may be interpreted as successful external effect execution;
9. no continuation component launches or retries the worker itself.

---

# 16. Interaction with ProjectScope and resource locks

Neither improvement replaces existing mechanical authorities.

Direct Run idempotency answers:

```text
is this the same logical invocation?
```

ProjectScope answers:

```text
is this project/resource binding valid/current?
```

Operation/resource locking answers:

```text
may this concrete effect execute concurrently on this resource?
```

Continuation effect linking answers:

```text
which active objective/context revision mechanically originated this canonical effect?
```

These are orthogonal concerns and should remain orthogonal in implementation.

---

# 17. Repository-backed final recommendation

## Direct Run idempotency

Keep as an approved general Soma improvement.

Repository evidence proves:

- the direct Run plane lacks stable logical request replay identity;
- JobManager currently generates a new Run ID for ordinary direct starts;
- operation locks are not a persistent replay contract;
- canonical Task already proves request-ID + request-hash replay semantics inside Soma;
- reserved Run identities already work before launch in Task and Workflow paths.

Therefore the recommendation is strong enough for implementation planning.

## Atomic effect linking

Keep as an approved continuation requirement, with precise wording:

```text
Task:
  atomic reservation + link is supported by current shared transaction seam.

Run:
  atomic reservation + link is the target invariant,
  but implementation must first add a connection-scoped Run reservation/replay seam.
```

Do not describe atomic Run effect linking as an existing capability.

---

# 18. Final verdict

**PASS WITH ONE IMPORTANT IMPLEMENTATION PRECONDITION.**

The two infrastructure recommendations are now backed directly by current Soma source rather than by general architectural preference.

Accepted theory:

```text
A. General direct Run idempotency
   -> real current gap
   -> belongs in Run authority
   -> request identity + normalized hash replay
   -> Run ID remains execution identity

B. Continuation effect linking
   -> provenance only, not execution authority
   -> Task can use existing caller-owned SQLite transaction
   -> Run requires new connection-scoped reservation seam first
   -> reserve/link before worker launch
```

No reasoning schema, model formatting contract, semantic evidence list, or new execution engine is required by either improvement.
