# Iteration 23 - Adversarial Simplification: Effect-Intent Removal and Decision-Basis CAS

Date: 2026-08-15
Status: RESEARCH - adversarial attack on Iterations 18-22 convergence
Track: Sol-centric agent interface / semantic continuation

---

# Research question

Iteration 22 produced a six-authority continuation design including `continuation_effect_intents` and hybrid single/batch admission.

This iteration attacks that result from the opposite direction:

> Did we solve a real correctness problem by adding durable effect intents, or did we recreate coordination ceremony that can be eliminated when canonical Task/Run identity can be reserved atomically at the effect boundary?

It also attacks a missing correctness dimension:

> Even if the Sol context has the current continuation version, what prevents it from launching an effect based on external source evidence that became stale after Sol read it?

---

# 1. Attack: root CAS alone does not protect decision evidence

Consider:

```text
Continuation control version = V10
Task T state_version = 4

Sol reads T@4
Sol decides effect E because of T@4

T changes to state_version 5
Continuation root remains V10

Sol submits E with expected continuation V10
```

If effect admission checks only:

```text
continuation state_version
current contract revision
```

then E is admitted even though its decision basis is stale.

This is a material flaw in Iterations 20-22.

External Task/Run/source changes deliberately do not increment continuation root state. Therefore an effect boundary must be able to stale-check the **material decision-basis observations** that Sol relied on.

---

# 2. Decision basis is not the entire continuation source set

Requiring every effect admission to validate every registered source would create false staleness and unnecessary I/O.

Example:

```text
registered sources = 20
E depends only on Task T and current repo HEAD
```

A log-only evidence source changing should not block E.

Therefore Sol/controller should submit a bounded `decision_basis` containing only the source tokens materially relied upon for the effect decision.

Conceptually:

```text
decision_basis:
  - source kind/id
    expected observation token/version
```

Soma performs only mechanical stale checks.

It does not decide which sources *should* have been material; that remains Sol's responsibility.

---

# 3. Decision-basis capability classes

## Local transactional source

Examples:

- canonical Task row/version/event watermark;
- canonical Run row/version;
- ProjectScope generation/status;
- local Knowledge revision.

Where the source uses the same SQLite authority, the effect-admission transaction can validate the expected version/token before commit.

Strong guarantee:

```text
expected local basis still matched at local admission commit
```

## Repository snapshot

Repo state is filesystem/Git state, not the same SQLite transaction.

Gateway can refresh/validate expected HEAD/worktree fingerprint immediately before local admission, and a repo-mutation gateway may then acquire the existing repository mutation lock according to normal effect semantics.

Do not claim distributed atomicity between Git filesystem snapshot and SQLite unless the concrete gateway establishes it.

## Remote/provider snapshot

Re-read before admission if necessary, but no local transaction can freeze the remote provider.

Record freshness/observed-at semantics and accept the inherent gap.

The adapter capability vector from Iteration 21 must tell Sol how strong the check is.

---

# 4. Attack: `continuation_effect_intents` duplicates canonical effect reservation for immediate local effects

Iteration 22's immediate path proposed one transaction containing:

```text
EffectIntent
canonical Task/Run reservation
source relation
continuation CAS
```

After that transaction commits, the durable Task/Run identity already proves:

- which canonical effect was admitted;
- exact effect request identity/hash;
- effect lifecycle/recovery;
- source identity;
- when it was admitted;
- how it can be queried/replayed.

If the continuation source relation/command receipt also records:

```text
continuation ID
contract revision basis
decision-basis ref/hash
semantic purpose
controller request identity
```

then a separate immediate-effect intent row adds little independent truth.

It becomes a second pre-effect identity that immediately collapses into the canonical effect.

## Verdict

For **immediate effects whose canonical identity can be reserved atomically**, a separate EffectIntent authority is unnecessary.

---

# 5. Minimal immediate-effect atomic admission

Preferred local strong path:

```text
Sol chooses concrete effect E
   |
   v
existing canonical gateway receives:
  ordinary effect request
  optional continuation_admission
   |
   v
pure validation/policy/scope normalization
   |
   v
obtain/acquire any normal effect-specific resource lock if required
without holding a model/reasoning lock
   |
   v
short local transaction:
  validate continuation open
  validate expected continuation control version
  validate expected governing contract revision
  validate submitted local decision-basis tokens where feasible
  reserve canonical Task or Run under stable logical request ID/hash
  insert/update continuation source relation to canonical effect
  write continuation command/admission receipt
  advance continuation control version
commit
   |
   v
existing TaskManager/JobManager/domain gateway launches effect after commit
```

No `continuation_effect_intents` row required.

---

# 6. Crash semantics improve

Because canonical effect identity is reserved in the same transaction as continuation admission:

## Crash before transaction commit

No admitted effect exists.

Replay/stale-controller behavior is clean.

## Crash after commit before worker/provider launch

Canonical Task/Run exists in pre-launch state.

Existing effect recovery can represent launch failure/recovery.

Fresh Sol sees exact effect identity through continuation source relation.

## Crash after launch before response

Stable effect request identity replays to same Task/Run.

No heuristic binding required.

This is stronger and simpler than separate intent -> launch -> bind for supported paths.

---

# 7. What about semantic purpose/provenance?

Do not need a separate intent row solely for semantic purpose.

Store bounded admission metadata with the continuation relation/command receipt, for example:

```text
source relation:
  relation = initiated_effect
  canonical effect kind/id
  admission_command_id
  governing_contract_revision_id
  decision_basis_hash/ref
  semantic_purpose summary
```

Canonical effect remains execution truth.

Continuation command remains mutation audit.

Source relation remains durable relevance/provenance.

No hidden queue is introduced.

---

# 8. Attack: deferred intents are being treated as a core requirement without evidence

The original owner need is to let Sol continue reasoning across interruptions, not to build a durable future-work queue.

A deferred statement such as:

```text
"later deploy X"
```

can already live safely as non-executable Sol handoff state:

```text
working plan / unresolved next action / resume focus
```

If fresh Sol resumes, it re-evaluates whether deploying X is still correct.

That is often **better** than giving the planned action its own durable effect-intent lifecycle.

## Verdict

Deferred effect intent is not required for v1 semantic continuation.

If a future real workflow proves a need for durable pre-authorized future effects, research that primitive separately.

Do not pre-build it now.

---

# 9. Attack: parallel mutating effect batch may be overengineering

Iteration 20/22 preserved a batch admission primitive because one model episode may emit multiple tool calls.

But not every tool call needs continuation-side mutation admission.

Important distinctions:

### Parallel reads

No effect admission needed.

Sol should freely issue many reads/queries in parallel.

### Existing parallel execution authority

Soma already has explicit mechanical group/parallel command facilities where appropriate. A group can itself be one canonical durable effect identity.

### Several unrelated durable mutations across different gateways

Possible, but materially riskier and less common than parallel reads.

We do not yet have owner evidence that v1 semantic continuation must atomically admit arbitrary heterogeneous mutating calls as one batch.

## Verdict

Do **not** make heterogeneous effect batch admission a v1 architectural requirement.

V1 strong tracked effects may serialize **effect admission boundaries** while reasoning and read parallelism remain unrestricted.

This is not a reasoning lock.

Later add batch admission only if real workflows show meaningful lost efficiency.

---

# 10. Does sequential effect admission cripple Sol?

No.

The restriction is narrow:

```text
for multiple independently side-effecting tracked mutations on the same continuation,
strong continuation admission occurs one canonical effect at a time
```

Sol may still:

- reason freely;
- perform unlimited independent reads in parallel;
- use an existing canonical parallel-group tool as one effect;
- launch effects on unrelated continuations/projects concurrently;
- decide the next effect immediately after receiving admission/result identity.

This is far less invasive than a reasoning lease.

Given the architecture goal of helping rather than burdening Sol, v1 should prefer this simpler guarantee.

---

# 11. Same-continuation split brain with minimal inline CAS

```text
A and B both resume continuation at V10

A chooses effect EA
B chooses effect EB

A gateway:
  validates basis
  CAS V10 -> V11
  atomically reserves canonical effect EA
  succeeds

B gateway:
  attempts expected V10
  stale_continuation
  reserves no canonical effect
  launches nothing
```

This solves the material split-brain mutation problem without durable effect intent state.

---

# 12. Same reasoning episode wants E1 then E2

After E1 admission, gateway result should return:

```text
continuation_state_version = V11
canonical_effect_id = E1
```

Sol can immediately issue E2 with V11.

This is ordinary optimistic concurrency, not a workflow step machine.

The model does not need to call `resume` unless new external evidence must be reconciled.

---

# 13. API ergonomics

Single tracked effect request needs only bounded optional metadata conceptually:

```text
continuation_admission:
  continuation_id
  expected_state_version
  expected_contract_revision_id
  decision_basis[]
  semantic_purpose?
  controller_request_id / stable operation identity
```

Some values can be derived by the continuation-aware skill/tool wrapper later, but the effect gateway must receive enough explicit identity to enforce stale-controller and request replay semantics.

The effect response should surface:

```text
continuation_state_version
canonical effect identity
admission status/replay status
```

Normal calls without continuation metadata remain unchanged.

---

# 14. Attack: command journal may be redundant with canonical effect request idempotency

For an immediate effect, canonical Task/Run request identity handles effect replay.

Why also record a continuation command?

Because they answer different questions:

```text
Task/Run request identity:
  is this the same logical external effect request?

continuation command/admission receipt:
  did continuation C at control version V admit this canonical effect under contract R and decision basis B?
```

That receipt is useful for:

- CAS replay/conflict;
- audit/provenance;
- continuation state-version advancement;
- reconstructing why the source relation exists.

Therefore command journal still has independent value, but should store only bounded mutation metadata/result refs.

PASS.

---

# 15. Attack: source relation could become duplicate admission state

Source relation should not copy full effect request or lifecycle.

Minimal relation:

```text
continuation_id
source kind/id
relation = initiated_effect
origin admission command id
registered/retired metadata
```

Optional bounded provenance refs/hashes may point to the admission receipt.

Do not duplicate Task/Run status or request payload.

PASS after normalization.

---

# 16. Attack: atomic Task/Run reservation assumption does not cover every Soma mutation gateway

Correct.

Strong inline admission should be **capability-gated**.

A gateway/source family qualifies for strong continuation-tracked effect admission only if it can prove:

1. pure validation before external mutation;
2. stable logical request identity/hash;
3. canonical effect identity can be durably reserved before external side effect;
4. replay returns the same canonical effect;
5. continuation CAS/source relation can be established before launch;
6. scope/authorization can be revalidated;
7. recovery represents launch/provider uncertainty honestly.

Task is close/already strong.

Run becomes strong after Iteration 19's reservation/idempotency work.

Other direct/non-Run gateways must not be silently upgraded.

---

# 17. Weak/unsupported effect paths

For a gateway that cannot meet strong admission requirements:

```text
continuation tracking class = observation_only / posthoc_reference / unsupported_strong_effect
```

Sol can still use the tool normally if authorized.

But Soma should not claim crash-safe continuation admission for that effect.

If the effect matters to future handoff, Sol may:

- checkpoint before the call;
- perform the call;
- register resulting canonical/source evidence if available;
- leave uncertainty explicit after crash.

Do not build a universal wrapper just to make every legacy path look equally strong.

---

# 18. Decision-basis stale checking is capability-gated too

A basis token can have different strengths:

```text
local_atomic_version
local_preflight_snapshot
provider_reported_snapshot
history_watermark
```

Effect admission should return exactly which checks were performed.

Conceptual response:

```text
decision_basis_validation:
  T: atomic_match
  repo: preflight_snapshot_match
  remote_service: observed_match_at T0 (non-atomic)
```

This helps fresh/current Sol understand the residual race without Soma making semantic judgments.

---

# 19. Do we need to persist every effect decision basis?

Not full raw data.

Persist bounded token/ref/hash material sufficient to explain the admission boundary:

```text
basis source identity
expected token/version
validation strength/result
```

Large evidence remains in canonical source authority/retrieval refs.

This is provenance, not chain-of-thought.

---

# 20. Corrected continuation authority set after attack

`continuation_effect_intents` is no longer justified for v1.

Preferred normalized core returns to **five** concerns, but for a different reason than Iteration 16's earlier four-table aesthetic:

```text
1. controller_continuations
   lifecycle, control CAS, current contract/capsule pointers

2. continuation_contract_revisions
   immutable governing controller contract revisions/provenance

3. continuation_capsules
   Sol handoff + basis contract revision + declared source basis frontier

4. continuation_sources
   canonical external relevance/provenance relationships

5. continuation_commands
   idempotent/CAS mutation and effect-admission receipts
```

Canonical Task/Run itself replaces the need for an immediate effect-intent authority.

---

# 21. What moved out of v1

Not rejected forever, but evidence-gated future capabilities:

```text
durable deferred effect intents
heterogeneous effect admission batches
pre-authorized future work queue semantics
exclusive continuation effect ownership
universal effect wrapper
```

If later owner workflows need them, research from real failures rather than anticipation.

---

# 22. Revised common tracked effect flow

```text
Sol reasons using current context/evidence
   |
   v
Sol selects existing canonical gateway E
   |
   v
E validates request + continuation admission metadata
   |
   v
mechanical stale checks:
  continuation version
  governing contract revision
  material decision-basis tokens according to adapter strength
   |
   v
one short local transaction:
  canonical Task/Run request reservation
  continuation source lineage
  admission command receipt
  continuation version CAS
commit
   |
   v
existing executor launches E
   |
   v
canonical effect recovery/evidence
   |
   v
Sol reasons further
```

This is still not a fixed reasoning loop.

---

# 23. Fresh-context resume after simplification

Resume needs:

```text
current ContractRevision + provenance
latest Sol handoff capsule + basis contract revision
contract changed since handoff?
registered source observations/deltas + adapter strengths
coverage uncertainty
canonical initiated effects through source relations
admission/effect uncertainty from underlying Task/Run
retrieval refs
```

There is no separate pending-intent list in v1.

If a planned action never reached canonical admission before Chat died, it exists only in the prior Sol handoff as a provisional next action and fresh Sol re-evaluates it.

This is semantically desirable.

---

# 24. Failure tests added by this iteration

## Decision basis

- continuation V10 unchanged, Task basis changes v4 -> v5 before effect admission -> admission rejects stale basis;
- unrelated registered source changes -> no rejection if not in submitted material decision basis;
- remote basis check reports non-atomic validation strength honestly.

## Split brain

- A/B at same continuation V; first strong effect admission wins, second launches nothing.

## Crash

- commit before launch leaves canonical Task/Run identity and continuation relation; restart recovers exact effect;
- no unbound intent artifact required.

## UX

- one tracked effect remains one effect-gateway call;
- no reserve/claim/bind choreography;
- no effect-intent list to maintain.

## Capability gating

- unsupported legacy effect cannot claim strong admission;
- normal untracked use remains available.

---

# 25. Result

**Iteration 23 verdict: SIMPLIFY.**

The strongest current alternative is **not** the six-table effect-intent architecture from Iterations 20-22.

For v1, remove `continuation_effect_intents` and use:

> optimistic inline continuation admission + material decision-basis stale checking + atomic reservation of the existing canonical Task/Run effect identity + continuation source/admission receipt in the same local durability boundary.

This yields:

- no reasoning lock;
- same-continuation stale-controller protection;
- no Task-as-universal wrapper;
- no second executor;
- no durable future-work queue;
- one-call common UX;
- stronger crash semantics for supported Task/Run effects;
- honest weaker classes for unsupported gateways;
- five normalized continuation concerns.

The major new correction relative to Iteration 22 is **decision-basis CAS**: continuation control version alone is insufficient because external world sources evolve independently.

---

# Next research question

Iteration 24 should perform a final focused convergence attack on the five-authority architecture, especially:

- whether `decision_basis` asks too much of Sol;
- how the model learns/retains source tokens without clutter;
- whether command/source metadata can represent effect admission without duplication;
- whether contract revision + capsule + source frontier creates redundant history;
- what minimum public surface can expose all of this naturally to normal Chat;
- whether any important crash/concurrency case still requires a sixth authority.
