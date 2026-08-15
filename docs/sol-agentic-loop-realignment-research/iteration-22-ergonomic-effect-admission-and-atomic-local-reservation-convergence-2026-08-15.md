# Iteration 22 - Ergonomic Effect Admission and Atomic Local Reservation Convergence

Date: 2026-08-15
Status: RESEARCH - convergence and UX attack after Iterations 18-21
Track: Sol-centric agent interface / semantic continuation

---

# Research question

Iterations 18-21 corrected major weaknesses:

- immutable controller contract revisions instead of contract-in-capsule;
- Run authority request idempotency instead of Task wrapping;
- optimistic pre-effect admission instead of reasoning locks;
- source relevance/provenance instead of control ownership/global coverage.

But Iteration 20's explicit flow can become operationally ugly:

```text
reserve intent
claim dispatch
call effect gateway
bind effect
register source
```

If Sol must manually execute that ceremony for every tracked effect, Soma has become harder to use than the capability it is meant to provide.

This iteration asks:

> Can Soma preserve the corrected durability/concurrency guarantees while keeping the natural interaction `Sol -> existing Soma tool -> result -> Sol` for the common single-effect case?

---

# 1. UX invariant

The architecture should optimize for:

```text
Sol decides to use a tool
 -> calls the natural tool
 -> Soma handles mechanical durability
```

not:

```text
Sol becomes a transaction coordinator for Soma metadata
```

Explicit continuation operations should appear only when they represent genuinely independent semantic actions:

- open/close continuation;
- revise governing contract;
- semantic handoff checkpoint;
- deliberately reserve future/deferred effect intent;
- deliberately admit a parallel batch when several effects are emitted as one reasoning decision.

Mechanical correlation around one immediate effect should be hidden behind the existing gateway boundary where safe.

---

# 2. Current Soma fact: Task and Run share local SQLite authority

Canonical Task, RunStore, ProjectScope and current Company/continuation research all use the same `runs/soma.sqlite3` durable authority.

TaskStore already exposes connection-scoped reservation (`reserve_task_in_connection`) for atomic coordination with ProjectScope.

RunStore does not yet expose equivalent request-id reservation, but Iteration 19 proposes exactly that enhancement.

This creates a stronger option than Iteration 16 assumed:

> For local canonical Task/Run effect identities, continuation intent admission and canonical effect identity reservation can often happen in the same short SQLite transaction before launch.

That can eliminate the launch-to-link gap rather than merely reconcile it later.

---

# 3. Alternative A - explicit multi-call admission for every tracked effect

Flow:

```text
continuation_action.reserve_intent
continuation_action.claim_dispatch
run_start / task_action / cloudflare_action / ...
continuation_action.bind_effect
continuation_action.register_source
```

## Strengths

- clean conceptual separation;
- easy to reason about each phase;
- no gateway changes beyond Run idempotency.

## Failure

Too much controller ceremony.

It would train Sol to manage Soma internals rather than solve the owner's objective.

The UX cost is especially bad for normal Chat where the continuation add-on should mostly disappear during active work.

## Verdict

REJECT as the default single-effect path.

Keep explicit intent operations for deferred/batch cases only.

---

# 4. Alternative B - continuation becomes a universal effect dispatcher

Flow:

```text
continuation_action.execute(intent/tool/request)
 -> continuation chooses/calls Task/Run/domain backend
```

## Strengths

- one call for Sol;
- continuation can atomically manage intent/effect identity.

## Failure

This creates a second generic executor/router beneath existing Soma gateways.

It would:

- duplicate domain tool contracts;
- make continuation responsible for routing/execution;
- reintroduce architecture pressure toward workflow semantics;
- reduce the value of natural Cloudflare/SSH/Docker/repo/Task gateways.

## Verdict

REJECT.

Continuation must not execute effects merely because it tracks them.

---

# 5. Alternative C - optional continuation admission metadata on existing gateways

Preferred common path:

```text
Sol -> existing effect gateway(
         normal effect request,
         optional continuation_admission = {...}
       )
```

The existing gateway remains the effect authority/entry point.

A small shared continuation-admission helper performs only mechanical local coordination immediately before canonical effect reservation/launch.

Conceptual metadata:

```text
continuation_id
expected_state_version
basis_contract_revision_id
intent_id
semantic_purpose
# or a pre-admitted batch token for batch mode
```

Exact schema belongs in planning.

## Verdict

PREFERRED for one immediate tracked effect.

---

# 6. Inline single-effect admission sequence

The safest order is:

```text
Sol chooses effect E
   |
   v
existing gateway receives E + continuation metadata
   |
   v
perform ordinary pure validation/policy/scope normalization first
(no external mutation yet)
   |
   v
short SQLite transaction:
  validate continuation open/current expected version
  validate basis contract revision current
  reserve dispatch-admitted EffectIntent I
  derive stable effect request identity R
  reserve canonical Task/Run effect identity using R
  link intent -> canonical effect
  register initiated_effect source relation
  advance continuation control version
commit
   |
   v
existing gateway launches canonical effect after commit
   |
   v
normal Task/Run recovery handles launch failure/outcome uncertainty
```

This is much stronger than:

```text
checkpoint intent
launch
hope to bind later
```

for local Task/Run effects.

---

# 7. Why this is not a continuation executor

The shared helper never decides:

- which tool to call;
- whether the effect is semantically correct;
- request payload;
- retry strategy;
- next action;
- completion.

Sol has already chosen the concrete canonical gateway and request.

The helper only establishes:

```text
current continuation admission
stable logical effect request identity
canonical effect identity/provenance
```

before the gateway performs the execution it already owns.

This is analogous to ProjectScope/Task admission coordination, not semantic routing.

---

# 8. Run requirement from Iteration 19 becomes clearer

For this atomic local pattern, RunStore should eventually expose a connection-scoped reservation seam similar in spirit to TaskStore:

```text
reserve_run_in_connection(
  conn,
  run_id,
  controller_request_id,
  request_hash,
  normalized durable input,
  initial status = launch_pending
)
```

The exact API can differ.

Essential property:

> canonical Run identity/request acceptance exists durably before worker/provider launch and can participate in the same local transaction as continuation effect intent/source linkage.

Then a Chat crash after commit is not ambiguous:

- intent exists;
- Run identity exists;
- source relation exists;
- worker may or may not have launched;
- canonical Run recovery tells fresh Sol the truth.

---

# 9. Task path is already close to this architecture

TaskStore already supports connection-scoped reservation and durable backend identity reservation before launch.

Therefore a future continuation-aware Task start can potentially atomically coordinate:

```text
continuation intent
ProjectScope reservation
Task reservation
backend Run reservation/reference
source relation
```

inside the smallest feasible local transaction, then call existing TaskManager launch after commit.

Do not create a new Task launcher.

---

# 10. Domain Run gateways remain natural

Example:

```text
cloudflare_action(..., continuation_admission=...)
```

still means:

```text
Cloudflare gateway validates/builds Cloudflare action
JobManager/Run authority durably reserves Run
worker performs Cloudflare action
```

The continuation helper only adds an atomic provenance/admission seam before launch.

Same principle can apply to SSH/Docker/PowerShell where the action already resolves to canonical Run.

---

# 11. Fast path remains untouched

If no continuation tracking is needed:

```text
cloudflare_action(normal request)
run_start(normal request)
task_action(normal request)
```

behaves normally.

No continuation lookup.

No effect-intent row.

No extra controller ceremony.

This is essential.

---

# 12. Parallel multi-effect case cannot be solved by independent inline CAS

Suppose one Sol reasoning episode wants:

```text
E1, E2, E3 in parallel
```

If each independent gateway call carries:

```text
expected_state_version = V
```

then first inline admission advances V and the other two fail stale.

Changing inline admission so they all silently accept V would reopen split-brain admission.

Therefore a true parallel decision needs a distinct batch primitive.

---

# 13. Preferred parallel path - explicit batch admission once

Flow:

```text
Sol decides independent effects [E1, E2, E3]
   |
   v
continuation_action.admit_effect_batch(
  expected_state_version=V,
  basis_contract_revision=R,
  normalized intent descriptors [I1,I2,I3]
)
   |
one short CAS transaction
   |
returns stable admissions/tokens/request IDs
   |
   +--> gateway E1(admission_token A1)
   +--> gateway E2(admission_token A2)
   +--> gateway E3(admission_token A3)
       in parallel
```

The batch represents one model/controller decision boundary containing several independent effects.

That maps naturally to how agent runtimes can emit multiple tool calls from one reasoning episode.

---

# 14. Batch admission token semantics

A token/reference should identify a durable effect intent row; do not use an opaque in-memory bearer token as the sole authority.

Each intent records:

```text
intent_id
batch id
basis contract revision
admission state
stable effect request identity
normalized request fingerprint/ref
```

The gateway verifies:

- intent belongs to continuation;
- request fingerprint matches the actual normalized gateway request;
- intent is dispatch-admitted;
- current continuation is not closed;
- current contract revision has not superseded the admitted basis if policy requires that check;
- canonical effect request identity has not already been bound to a different payload.

Then it reserves/replays the canonical effect identity and binds it mechanically.

---

# 15. Owner contract changes after batch admission

A batch is analogous to a set of tool calls already emitted from one current reasoning decision.

But if an owner contract revision arrives before some admitted calls reach their gateways, executing old intent may be wrong.

Conservative v1 rule:

```text
gateway rejects unbound admitted intent if
current_contract_revision_id != intent.basis_contract_revision_id
```

Fresh Sol re-reasons and may supersede/re-admit.

This check does not ask Soma to understand semantic compatibility. It simply prevents silently executing under a contract revision different from the one that admitted the intent.

Once canonical Task/Run effect identity has already been reserved/launched, later contract changes do not erase it; Sol may decide to cancel/steer using canonical authority.

---

# 16. Other continuation state changes after batch admission

Do not invalidate a batch merely because:

- another registered source was refreshed;
- a source row was mechanically linked;
- Task/Run state changed underneath.

The batch was already admitted as one reasoning decision.

The critical invalidators before first canonical effect reservation are:

- continuation closed/cancelled;
- governing contract revision changed;
- intent explicitly superseded/abandoned;
- request fingerprint mismatch.

This reduces needless contention while preserving owner-authority changes.

---

# 17. Root version semantics should separate lifecycle/control from world changes

Iteration 20 conservatively suggested incrementing root `state_version` for many metadata writes.

This iteration refines that.

Root `state_version` should protect mutations of **continuation control state**, not act as a mirror of every external source transition.

Likely increment on:

- contract revision pointer change;
- capsule pointer change;
- effect admission reservation/batch;
- explicit intent supersession/abandonment;
- source registry membership/relation change;
- continuation closure.

Do not increment because underlying Task/Run status changed; those have their own versions/tokens.

Mechanical post-admission binding of a pre-authorized intent may not need to invalidate sibling intents in the same batch.

Implementation tests should prove exact semantics.

---

# 18. EffectIntent lifecycle simplification

After inline atomic local reservation, many immediate effects may move directly:

```text
admitted -> bound_to_effect
```

inside one transaction.

Deferred/batch cases need visible states such as:

```text
reserved
admitted
bound
superseded
abandoned
uncertain_correlation   # only for unsupported legacy source paths
```

Avoid workflow-like states such as:

```text
ready
queued
running
completed
```

Those belong to canonical Task/Run.

---

# 19. Can `continuation_effect_intents` be eliminated with inline admission?

No.

Even if common single-effect admission is hidden inside a gateway, the durable intent row still solves independent problems:

- same-continuation optimistic admission history;
- semantic purpose/provenance;
- stable effect request ID derivation;
- deferred/batch effects;
- contract basis;
- crash reconciliation;
- mapping one reasoning decision to canonical effect identity.

It remains an independent authority.

---

# 20. Can `continuation_commands` be eliminated?

Not yet.

Each durable authority can carry request IDs, but continuation still has mutations that are not naturally represented solely by content rows:

- close/cancel;
- source retirement;
- batch admission replay;
- binding/supersession mutations;
- potentially repeated update requests with same controller identity.

A bounded command/idempotency journal remains the cleanest central replay guard.

However it must remain mutation audit, not a hidden source of semantic state.

---

# 21. Revised normalized continuation authority set

After Iterations 18-22:

```text
1. controller_continuations
   lifecycle + current pointers/control version

2. continuation_contract_revisions
   immutable governing controller requirement revisions + provenance

3. continuation_capsules
   immutable Sol handoff + basis contract revision + basis source frontier

4. continuation_effect_intents
   non-executable side-effect admission/provenance/correlation

5. continuation_sources
   canonical external source relevance/provenance registry

6. continuation_commands
   mutation request idempotency/CAS audit
```

External truth remains outside these tables:

```text
Task
Run
ProjectScope
repo/service/provider state
Knowledge
```

No table stores reasoning phase or next action.

---

# 22. Common active-Chat behavior after convergence

## Ordinary read

```text
Sol -> repo_query / task_query / ssh_query / ... -> Sol
```

No continuation ceremony.

## Ordinary short write where semantic continuity is irrelevant

```text
Sol -> existing gateway -> result -> Sol
```

No continuation ceremony.

## One durable/risky tracked effect in an active continuation

```text
Sol -> existing gateway(effect + continuation_admission) -> result -> Sol
```

One call.

## Several independent tracked effects from one reasoning decision

```text
Sol -> admit_effect_batch once
    -> existing gateways in parallel with admissions
    -> results -> Sol
```

One extra coordination call for a genuinely multi-effect durable boundary.

## Deferred intent

Explicit reserve intent only when Sol intentionally wants to preserve an effect decision without launching it now.

This is rare and meaningful.

---

# 23. Fresh-context resume behavior

Still:

```text
owner: "continue"
  |
  v
Sol discovers continuation
  |
  v
resume projection:
  current contract revision + provenance
  prior Sol handoff + its basis contract revision
  contract changed? flag
  registered source observations/deltas
  adapter strengths/coverage uncertainty
  unresolved effect intents/admissions
  retrieval refs
  |
  v
Sol reasons
```

No next-step recommendation from Soma.

---

# 24. Does inline admission make Soma a model runner?

No.

Soma still has no loop that automatically:

- calls the model;
- selects a tool;
- invokes a pending intent;
- decides completion;
- schedules next work.

Inline admission only executes **inside an already owner/Sol-selected tool invocation**.

That is consistent with Soma being an agent-computer interface rather than a second agent.

---

# 25. Failure tests

## Single effect UX

- current continuation + one tracked Run effect completes with one public effect call, not reserve/claim/bind choreography;
- stale expected continuation version rejects before canonical effect reservation;
- replay uses same effect request identity and returns same Run/Task.

## Atomic local identity

- crash after shared transaction commit but before worker launch leaves intent + canonical effect identity + source lineage recoverable;
- no launch-to-link ambiguity for supported Task/Run paths.

## Parallel batch

- 3 intents admitted in one CAS;
- all 3 matching gateway calls may reserve/launch independently/parallel;
- one sibling binding does not invalidate the others;
- contract revision before an unbound sibling gateway call rejects that sibling.

## Fast path

- no continuation metadata -> existing tool behavior unchanged.

## Authority

- continuation helper never selects effect gateway;
- no pending intent auto-executes;
- Task/Run remains sole execution/lifecycle authority.

---

# 26. Result

**Iteration 22 verdict: ACCEPT HYBRID ADMISSION.**

The corrected architecture can preserve strong continuation-side effect admission **without making Sol manage a transaction protocol on every action**.

Preferred behavior:

```text
single tracked immediate effect
 -> inline mechanical continuation admission inside the existing selected gateway
 -> atomically reserve local intent + canonical Task/Run identity/source relation where possible
 -> existing gateway launches after commit

parallel multi-effect decision
 -> one explicit batch admission
 -> normal gateways execute admitted effects in parallel

deferred effect
 -> explicit non-executable intent reservation
```

This keeps the natural agent interface while preserving:

- optimistic stale-controller rejection;
- contract-version safety;
- stable effect request correlation;
- Task/Run authority neutrality;
- no reasoning locks;
- no second executor.

---

# Next research question

Iteration 23 should perform another full adversarial attack on the Iterations 18-22 architecture, specifically looking for:

- hidden workflow semantics in EffectIntent/admission;
- over-serialization or impossible atomicity claims;
- unsafe batch authorization persistence;
- command/source/intent authority overlap;
- security/provenance gaps;
- same-thread UX regressions;
- whether direct provider/domain actions exist that cannot fit Task/Run atomic reservation and therefore need an explicit weaker capability class.
