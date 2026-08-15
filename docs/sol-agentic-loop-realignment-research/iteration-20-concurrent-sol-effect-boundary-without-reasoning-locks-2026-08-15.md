# Iteration 20 - Concurrent Sol Effect Boundary Without Reasoning Locks

Date: 2026-08-15
Status: RESEARCH - focused alternative search after Iteration 17 attack
Track: Sol-centric agent interface / semantic continuation

---

# Research question

Iteration 17 identified a split-brain case:

```text
Chat A resumes continuation at version V
Chat B resumes same continuation at version V
A reasons
B reasons
A launches side effect E1
B launches conflicting/duplicate side effect E2
only later does one discover stale state at checkpoint time
```

A CAS only at semantic checkpoint is too late because external effects may already have launched.

But a reasoning lock/lease is also wrong because:

- Sol reasoning should remain lock-free;
- multiple Chats may read/reason concurrently;
- one reasoning episode may legitimately issue several independent tool calls in parallel;
- long-lived leases introduce recovery/ownership complexity and reproduce workflow-runner semantics.

This iteration asks:

> What is the smallest durable effect boundary that allows concurrent reasoning but prevents stale Sol contexts from independently crossing the same continuation control state into new durable effects?

---

# 1. External runtime evidence

## Codex app-server expected active-turn identity

Codex `turn/steer` requires `expectedTurnId`. If the expected turn does not match the currently active turn, the request fails rather than steering a different concurrent turn.

Source:
- https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md

This is not directly our architecture, but it demonstrates a useful principle:

> side-effecting/steering mutation can be guarded by expected current identity without locking the model's reasoning itself.

## OpenAI Agents SDK server-managed conversation locking

The Agents SDK documents `conversation_locked` retry behavior for server-managed conversations, reflecting that mutation of one conversation has a concurrency boundary even while model/application logic remains outside that lock.

Source:
- https://openai.github.io/openai-agents-python/running_agents/

For Soma, the preferred mechanism should be optimistic CAS rather than a long-held conversation lock because Soma does not own the model runner.

## Current Soma Task CAS

Canonical Task already uses `state_version` compare-and-set for ownership-sensitive mutations.

This makes optimistic expected-version admission a native Soma pattern.

---

# 2. Alternative A - one active continuation lease / reasoning owner

Shape:

```text
resume continuation
 -> acquire controller lease
 -> only lease holder may reason/act
 -> renew/release lease
```

## Strengths

- straightforward exclusion;
- duplicate side-effect decisions become unlikely.

## Failures

### Violates the owner concurrency requirement

Reasoning itself becomes serialized.

### Crash recovery burden

Lease expiry, stale holder detection, takeover, heartbeat and clock behavior become new infrastructure.

### Wrong ownership level

Soma would be claiming ownership over the cognitive session rather than only protecting durable mutations.

### Work/native agent conflicts

A native Work context or another legitimate controller surface could be artificially blocked even for read-only reasoning.

## Verdict

REJECT.

No reasoning lease in the core.

---

# 3. Alternative B - rely on effect-authority idempotency only

After Iteration 19, direct Run can eventually replay-protect a stable logical request identity. Task already can.

Could that alone solve split-brain?

Only if both stale Sol contexts choose the **same logical request identity**.

But they may independently decide different requests:

```text
A: deploy config X
B: deploy config Y
```

Both can be individually idempotent and still conflict semantically.

Effect-authority idempotency prevents duplicate replay of one logical request; it does not prove that the requesting Sol context was still current for the continuation.

## Verdict

NECESSARY but INSUFFICIENT.

---

# 4. Alternative C - CAS only when writing next capsule

Shape:

```text
reason
launch effects
later checkpoint(expected_version=V)
```

## Failure

CAS happens after the irreversible boundary.

The stale context can already have mutated the world.

## Verdict

REJECT.

This was the hidden weakness in Iteration 16.

---

# 5. Alternative D - pre-effect optimistic reservation

Shape:

```text
Sol reasons freely from continuation version V
 -> decides one or more tracked durable effects
 -> reserves effect intent(s) under expected version V
 -> short SQLite CAS commits reservation and advances continuation version
 -> only after commit may those reserved effects launch
```

If another Sol context also reasons from V:

```text
first reservation wins
second reservation sees stale version
second launches nothing
second must resume/reconcile
```

## Strengths

- no reasoning lock;
- stale side-effect decision is rejected before launch;
- uses native Soma optimistic concurrency style;
- effect authority remains Task/Run/domain authority;
- reservation is semantic provenance, not execution.

## Verdict

PREFERRED.

But one refinement is required: reservation must support **batches**.

---

# 6. Why single-intent reservation is too restrictive

The researched Sol/Codex reasoning trajectory can decide several independent operations at once.

Example:

```text
inspect logs A
inspect status B
run test C
```

or even several independent durable effects:

```text
start benchmark A
start benchmark B
start benchmark C
```

A naive API:

```text
reserve_intent(I1, expected=V) -> V+1
reserve_intent(I2, expected=V) -> stale
```

would force artificial serial reasoning/re-read cycles.

That is not acceptable.

---

# 7. Preferred operation - atomic batch intent reservation

Conceptual mutation:

```text
reserve_effect_intents(
  continuation_id,
  expected_state_version = V,
  intents = [I1, I2, ... In],
  controller_request_id
)
```

Inside one short SQLite transaction:

1. validate continuation is open;
2. validate current contract revision / expected control state if supplied;
3. validate `expected_state_version == current state_version`;
4. replay/hash conflict check command request;
5. validate each intent is bounded and non-executable;
6. derive/reserve stable intent identities and effect request identities;
7. insert all intents;
8. increment continuation state version once;
9. commit.

After commit, Sol may launch the reserved effects sequentially or in parallel.

This preserves multi-tool freedom while closing stale-controller admission.

---

# 8. A new independent authority is justified

Iteration 16 placed pending effect intents inside the handoff capsule.

That is no longer sufficient.

Effect intent has its own lifecycle:

```text
reserved
launching / launch_requested?    # only if useful mechanically
bound
unbound_uncertain
superseded
abandoned
```

It can change after a capsule without requiring a new Sol semantic handoff.

Therefore the clean normalized architecture adds:

```text
continuation_effect_intents
```

Conceptual fields:

```text
intent_id
continuation_id
reservation_batch_id / command id
basis_state_version
basis_contract_revision_id
semantic_purpose
requested_effect_kind
normalized_request_fingerprint_or_ref
stable_effect_request_id
status
effect_source_kind?
effect_source_id?
created_at
bound_at
resolved_at
safe metadata
```

The table contains **intent/correlation state only**.

It never executes work.

---

# 9. Why intent should not be overloaded into `continuation_commands`

`continuation_commands` is a mutation idempotency/CAS audit journal.

An effect intent is durable domain state that must remain queryable after the command completes and may later transition from unbound to bound/abandoned/uncertain.

Stuffing intent state into command result blobs would:

- make command journal a hidden state authority;
- complicate indexed lookup by effect request identity;
- blur mutation audit and active semantic provenance.

## Verdict

Keep separate.

The architecture now has six normalized continuation concerns:

```text
controller_continuations
continuation_contract_revisions
continuation_capsules
continuation_effect_intents
continuation_sources
continuation_commands
```

Again, table count is not an objective.

---

# 10. Intent reservation is not an execution queue

Hard invariant:

```text
reserved intent -> NO automatic launch
```

Only Sol/Work/controller calls the normal Task/Run/domain gateway.

Soma continuation code may return:

```text
intent_id
stable_effect_request_id
request fingerprint/ref
```

but never invokes the effect because the intent exists.

This preserves Sol as semantic action authority.

---

# 11. Binding after launch

After the canonical effect gateway returns:

```text
Task ID or Run ID or other supported effect identity
```

Sol/controller binds the intent mechanically:

```text
bind_effect(
  continuation_id,
  intent_id,
  source_kind,
  source_id,
  expected intent status/version
)
```

For Task/Run with stable effect request identity, Soma can additionally verify that the canonical effect's request identity matches the intent's reserved request identity.

Binding does not grant new control authority to continuation.

It establishes provenance:

```text
this canonical effect corresponds to this previously admitted Sol intent
```

---

# 12. Crash windows

## A. crash before reservation

No continuation effect authority exists.

Any unpersisted Sol thought is lost, which is honest.

## B. crash after reservation before launch

Intent exists, effect absent.

Resume reports:

```text
reserved_unbound
```

Fresh Sol decides whether it should still be launched under current contract/world state.

No automatic execution.

## C. crash after launch before response/link

With Iteration 19 Run/Task request idempotency:

```text
intent has stable_effect_request_id
canonical effect authority can replay/find original effect
```

Fresh Sol reconciles/binds without heuristic recent-run matching.

## D. crash after effect link before capsule

Intent/source truth survives.

Latest semantic handoff may be old; resume exposes effect/source as post-frontier state.

---

# 13. Contract changes after intent reservation

Suppose:

```text
intent I reserved under contract V3
owner changes contract to V4 before I launches
```

The intent record carries `basis_contract_revision_id = V3`.

The continuation layer must not auto-cancel or auto-launch.

If Sol later attempts launch, guidance should require reconciliation against current contract.

For stronger mechanical protection, launch-capable continuation guidance can require a fresh validation command that checks the intent is still admitted under current continuation version before using its stable request ID.

But avoid turning Soma into a semantic validator of whether V4 still permits I.

Fresh Sol performs that judgment.

---

# 14. Do we need a second pre-launch CAS after reservation?

Potential race:

```text
reserve I under V3
contract changes to V4
old Chat still holds I and launches it
```

A single reservation CAS does not prevent this later stale launch.

There are three alternatives.

## 14.1 Treat reservation as durable launch authorization forever

Reject.

That would let old intent ignore later owner contract changes.

## 14.2 Require immediate launch after reservation and assume no intervening mutation

Reject as a correctness assumption.

Async UI/tool timing can create a gap.

## 14.3 Require an effect-dispatch claim immediately before launch

Preferred for **continuation-controlled durable effects**.

Conceptually:

```text
claim_effect_dispatch(
  continuation_id,
  intent_id,
  expected_continuation_state_version,
  expected_contract_revision_id
)
```

The claim:

- is a tiny CAS;
- marks the intent dispatchable/claimed under the then-current control state;
- returns the stable effect request ID;
- does not launch anything.

After claim, the controller immediately calls the canonical effect gateway.

Question: can another contract update occur after claim but before provider call? Yes. No distributed architecture can make an arbitrary remote call atomic with a local SQLite contract mutation without moving execution into the continuation authority.

Therefore the correct boundary is:

> dispatch claim proves the effect decision was current at a precise local admission instant; it cannot guarantee no owner instruction arrives microseconds later before the external call.

That is the same kind of unavoidable boundary present in ordinary interactive tool calls.

Do not introduce a long-held lock to close an impossible distributed gap.

---

# 15. Can reserve + dispatch claim be one operation?

Usually yes when Sol is ready to call immediately.

A useful API may support:

```text
admit_effect_batch(...)
```

that both creates intents and marks them dispatch-admitted under one current continuation version.

Then Sol immediately calls the returned stable effect request IDs.

For planned-but-not-yet-ready effects, use reservation only and require later claim.

This gives both:

- efficient multi-effect dispatch;
- durable paused intent when needed.

Exact API naming belongs in planning.

---

# 16. Batch claim and parallel effects

To preserve parallelism:

```text
claim_effect_batch([I1, I2, I3], expected=V)
```

should validate/claim all in one CAS and return all stable effect request identities.

Then Sol may call the canonical gateways in parallel.

If one external call fails before acceptance, other claimed intents remain individually reconcilable.

Do not make failure of one auto-cancel unrelated claimed effects unless Sol explicitly chooses that policy.

---

# 17. What increments continuation `state_version`?

Conservative v1 recommendation:

Increment for controller-semantic mutations that could invalidate a stale effect decision:

- contract revision;
- capsule checkpoint;
- effect intent reservation/dispatch claim;
- effect intent abandonment/supersession;
- continuation complete/cancel;
- source registration/retirement when it changes the controller's declared relevant world set.

Pure read/resume does not increment.

Mechanical source-state changes in underlying Task/Run do not mutate continuation root; they are discovered through source tokens.

Binding a canonical effect to an already admitted intent may increment for conservative stale-controller rejection, but planning should test whether this creates needless contention.

False-positive staleness is acceptable if bounded; stale effect launch is not.

---

# 18. Same-continuation multi-Chat semantics

The resulting contract is intentionally optimistic:

```text
many Sol contexts may:
  read
  resume
  inspect evidence
  reason

only a current context may:
  revise contract
  checkpoint semantic handoff
  admit/claim tracked durable effects
  close continuation
```

Two stale contexts do not require a lease.

The first durable semantic mutation wins CAS.

The other receives stale state and re-reasons from current truth.

This is exactly the desired authority boundary.

---

# 19. Effect-authority idempotency remains separate

Continuation CAS answers:

```text
Was this Sol context current enough to admit this effect intent?
```

Task/Run request idempotency answers:

```text
Has this logical effect request already been launched/accepted?
```

Provider/recovery semantics answer:

```text
Did the external world actually commit the operation?
```

These are three distinct layers.

Do not collapse them.

---

# 20. Failure tests

## Split brain

- A and B both resume V10;
- A claims intent batch under V10 -> succeeds, root V11;
- B claims under V10 -> stale, launches nothing.

## Parallelism

- one current Sol reserves/claims 5 independent intents in one batch;
- all 5 may launch concurrently after admission;
- no forced sequential CAS per effect.

## Contract race

- intent reserved under contract R3;
- contract advances R4;
- dispatch claim expecting R3/current old version fails;
- fresh Sol decides whether to supersede/recreate intent.

## Crash

- reservation survives restart;
- reserved intent never auto-executes;
- claimed intent with lost launch response reconciles via stable effect request identity;
- no duplicate Run/Task launch on retry.

## Locks

- reasoning/read/resume takes no repo mutation lock;
- effect admission uses only short SQLite transaction;
- no transaction spans model reasoning or external effect call.

---

# 21. Result

**Iteration 20 verdict: ACCEPT optimistic batch effect admission.**

Best current architecture:

```text
concurrent Sol reasoning is allowed
        |
        v
tracked durable side-effect boundary
        |
 optimistic continuation CAS
 reserve/claim one or many effect intents
        |
        v
stable effect request identities
        |
        v
canonical Task/Run/domain gateways
```

Add `continuation_effect_intents` as an independent non-executable authority.

No reasoning lease.

No Task loop.

No continuation executor.

Support batch admission so multi-tool/parallel reasoning is not artificially serialized.

---

# Next research question

Iteration 21 should attack source coverage/control semantics from Iteration 17:

> What should `continuation_sources` mean if registration cannot imply global observation or exclusive control ownership, and how should resume communicate coverage/consistency honestly without becoming a universal watcher framework?
