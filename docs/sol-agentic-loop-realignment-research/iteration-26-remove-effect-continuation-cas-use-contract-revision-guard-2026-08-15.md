# Iteration 26 - Remove Effect Continuation CAS; Use Contract-Revision Guard

Date: 2026-08-15
Status: RESEARCH - concurrency and effect-admission simplification
Track: Sol-centric agentic reasoning architecture
Builds on: Iterations 24-25

---

## Research question

Should every effect associated with a continuation require an `expected_continuation_version` CAS, or does that over-serialize Sol's natural reasoning/tool behavior and make Soma solve a semantic concurrency problem it does not own?

---

# 1. Prior proposal under attack

Earlier iterations proposed:

```text
Sol A resumes continuation V10
Sol B resumes continuation V10

A launches effect with expected V10
 -> wins CAS
 -> continuation becomes V11

B launches effect with expected V10
 -> rejected stale
```

The motivation was to prevent two Chat instances from acting from divergent reasoning state.

This appears mechanically neat but contains a hidden semantic claim:

> only one reasoning branch may cross an effect boundary from a continuation version.

That is not necessarily desirable or enforceable by Soma.

---

# 2. Why the effect-level continuation CAS is suspicious

## 2.1 It serializes legitimate parallel tool use

Current capable agents routinely issue multiple independent calls in parallel.

If every first effect increments the continuation version, sibling effects prepared from the same reasoning episode become stale unless they are pre-batched.

That forces extra mechanisms such as:

```text
batch admission
predeclared effect set
admission tokens
effect-intent reservation
```

This is exactly the kind of protocol ceremony the owner wants to avoid.

## 2.2 It makes handoff state behave like execution state

A semantic handoff revision should not become a global execution lock.

The continuation exists to help fresh Sol re-enter context, not to serialize every external operation.

## 2.3 It overstates Soma intelligence

A changed continuation version does not necessarily mean another Sol's reasoning is invalid.

A same-version continuation does not prove reasoning is fresh.

Therefore continuation version is a poor proxy for reasoning validity.

## 2.4 It confuses branching with corruption

Codex explicitly supports `/fork`, and Claude Code supports `--fork-session` when resumed work should become a separate session.

Multiple reasoning branches are a legitimate agent/session pattern, not automatically an error.

Primary references:

- OpenAI Codex TUI tooltips (`/fork`, `/side`, `codex resume`)
  - https://github.com/openai/codex/blob/main/codex-rs/tui/tooltips.txt
- Claude Code CLI `--fork-session`, `--resume`, `--continue`
  - https://code.claude.com/docs/en/cli-usage

Soma normal Chat continuation should not invent a single-writer cognitive lease unless a real requirement demonstrates the need.

---

# 3. What Soma actually needs to guard mechanically

There is one high-value semantic boundary Soma *can* understand:

> Which governing controller contract revision did Sol believe it was acting under?

If a continuation's current contract is R3 and an old Chat attempts an associated effect saying it is acting under R2, Soma can mechanically reject:

```text
superseded_contract_revision
```

No reasoning interpretation is needed.

---

# 4. Candidate minimal effect association

For an effect that should be mechanically associated with a continuation, use conceptually:

```text
continuation_id
basis_contract_revision_id
```

plus the effect authority's normal request/idempotency fields.

Soma verifies:

```text
continuation exists/open
basis_contract_revision_id belongs to continuation
basis_contract_revision_id == current_contract_revision_id
normal effect-specific authorization/preconditions pass
```

Then it admits/executes using the canonical gateway.

---

# 5. What this guard catches

Example:

```text
R3: "repair service but do not touch websites"

old Chat still believes R2:
"repair service and update website config if needed"

old Chat submits tracked effect with basis R2
```

Soma mechanically knows R2 is no longer current and can reject before the associated effect launches.

This is a real deterministic safety property.

---

# 6. What it deliberately does not catch

Two Sol instances may both act under current contract R3.

Soma does not know whether:

- one has better reasoning;
- one read newer logs;
- their effects are semantically redundant;
- one changed its plan;
- one should defer to the other.

Therefore core continuation does not attempt to decide those questions.

Underlying effect authorities still enforce what they actually know:

```text
repository mutation locks
Task state-version guards
ProjectScope generations
file/hash preconditions
Run request idempotency
provider/tool authorization
resource-specific constraints
```

---

# 7. Parallel effects remain natural

Under unchanged contract R3:

```text
Sol decides:
  inspect host A
  inspect host B
  run test C
```

All may be associated with:

```text
continuation K
basis contract R3
```

without a continuation CAS invalidating sibling calls.

This preserves native parallel tool use.

---

# 8. Same-contract concurrent Sol branches are not automatically forbidden

Suppose two fresh Chats both resume the same continuation under R3.

Both may reason.

Both may perform effects allowed under R3.

This can create ordinary resource contention, but that belongs to the underlying effect/resource authority.

Examples:

- same repo mutation -> existing repo lock/patch preconditions;
- same Task mutation -> Task version/idempotency;
- same logical Run request -> future Run request-id replay seam;
- independent projects/resources -> may proceed concurrently.

This matches the owner's multi-project/no-reasoning-lock requirement better than continuation-level execution serialization.

---

# 9. If single-writer continuation is ever needed, make it explicit and optional

Do not smuggle a reasoning lock into v1 via state-version semantics.

If future real usage proves an objective sometimes needs exclusive controller ownership, design a separate opt-in capability such as:

```text
exclusive continuation claim / lease
```

with explicit semantics and owner-visible behavior.

That is a different feature.

Do not build it preemptively.

---

# 10. What continuation state_version remains useful for

Continuation CAS still makes sense for **continuation metadata mutations**, for example:

```text
change current contract pointer
write/replace latest handoff pointer
complete/cancel lifecycle
rename/archive metadata
```

It protects the continuation record from lost-update races.

It should not automatically gate unrelated canonical effects.

---

# 11. Handoff writes may still use CAS

If two Sol branches both try to publish the new canonical latest handoff, one may win and the other may receive a stale metadata error.

That is acceptable because `latest_handoff_id` is a single pointer.

The losing branch can:

- read the new latest handoff;
- decide whether its handoff still matters;
- fork a continuation later if branch persistence becomes a real product requirement.

No effect rollback is implied.

---

# 12. Contract revision update semantics

Contract revisions remain immutable.

Changing controller direction creates R(n+1) and atomically updates the continuation's current contract pointer.

Tracked future effects should carry the current contract revision identity.

Important limitation:

Soma only knows about controller-direction changes that have been explicitly recorded as a new contract revision.

If the user changes direction in Chat and Sol fails to record the change before acting, Soma cannot infer that omission.

Do not claim otherwise.

---

# 13. This removes `decision_basis` from effect admission

No effect-level semantic evidence list is required.

No:

```text
decision_basis[]
observed Task versions used in reasoning
registered evidence frontier
reasoning freshness token
```

Instead:

```text
contract revision guard
+
normal effect-specific mechanical preconditions
```

This is narrower but much more truthful.

---

# 14. What about stale world state?

If an effect inherently depends on a mutable target, the relevant gateway should expose a target-specific mechanical precondition where practical.

Examples:

```text
repo patch -> expected content hash / preview hash
Task action -> if_state_version
Knowledge update -> expected revision/hash if supported
provider update -> resource version/etag if provider supports it
```

These should be designed because the **effect authority** understands them, not because continuation tries to model Sol's reasoning inputs.

---

# 15. Effect lineage record

After a successful associated effect admission, `continuation_commands` can record a receipt such as:

```text
continuation_id
basis_contract_revision_id
operation = associated_effect
canonical_effect_kind
canonical_effect_id
controller_request_id
created_at
```

No continuation version increment is required merely because an effect occurred unless the implementation needs a normal audit/update timestamp.

If state_version is incremented for bookkeeping, it must not make sibling effects stale.

Prefer separate metadata semantics over using one integer for unrelated concerns.

---

# 16. Run idempotency remains independent

Iteration 19 remains valid:

Direct durable Run creation should gain its own stable logical request ID + request hash replay seam.

That solves duplicate launch after lost response.

It does not depend on continuation CAS.

Continuation association may store the resulting Run ID as lineage.

---

# 17. Acceptance scenarios

## Scenario A - parallel sibling effects

```text
contract R3 current
Sol launches A, B, C in parallel under R3
all pass normal effect authority
```

PASS.

## Scenario B - owner changed contract

```text
R3 current
old Chat submits effect under R2
```

Reject mechanically as superseded contract.

PASS.

## Scenario C - two Sol branches same contract

```text
A and B both under R3
A mutates repo
B attempts conflicting repo mutation
```

Continuation does not decide which reasoning wins.

Repo/effect authority handles contention/stale patch preconditions.

PASS.

## Scenario D - response lost after Run creation

Retry same Run logical request ID/hash -> same Run.

PASS once Iteration 19 Run replay seam exists.

---

# 18. Architecture after this correction

Continuation becomes less like a controller and more like a durable semantic re-entry record:

```text
ControllerContinuation
  identity/lifecycle
  current contract revision
  latest free-form handoff

Contract revisions
  governing controller text history

Handoffs
  free-form Sol semantic context

Commands/effect receipts
  continuation mutations + mechanically associated effects
```

Execution remains:

```text
Sol -> canonical Soma gateway -> Task/Run/repo/service authority
```

No continuation execution scheduler.

No continuation reasoning lock.

---

# 19. Verdict

**REMOVE MANDATORY `expected_continuation_version` CAS FROM EFFECT ADMISSION.**

Use instead:

```text
current contract-revision guard
+
underlying effect authority's own mechanical preconditions/idempotency
```

Keep continuation CAS for continuation metadata/lifecycle writes only.

This is simpler, parallel-friendly and more honest about Soma's lack of semantic intelligence.

The next convergence iteration should test whether the remaining four-authority continuation kernel plus Run request-idempotency is now minimal enough, and whether any hidden model-formatting burden remains in the normal Chat UX.
