# Iteration 27 - Opaque Continuation Context Handle

Date: 2026-08-15
Status: RESEARCH - interface simplification
Track: Sol-centric agentic reasoning architecture
Builds on: Iterations 24-26

---

## Research question

Can Soma reduce remaining continuation protocol ceremony by giving Sol **one opaque context handle** instead of requiring it to reconstruct or repeatedly submit multiple continuation/version fields?

---

# 1. Current pain point

After Iterations 24-26, the strongest remaining model-carried metadata for a tracked effect is conceptually:

```text
continuation_id
basis_contract_revision_id
```

This is already much smaller than prior designs, but it still asks Sol to carry and correctly pair two machine identities.

The owner explicitly warned against repeating the historical formatting/protocol treadmill.

Therefore test whether these identities can be collapsed into one opaque handle minted by Soma.

---

# 2. Precedent: runner-owned systems expose opaque continuation identities

Successful session/stateful APIs usually make callers carry a compact opaque identity rather than reconstruct hidden state.

Examples:

## Claude Code

Claude Code exposes session IDs for resume/fork. The SDK guidance explicitly says to capture a session ID and pass it back to resume a specific session.

Primary sources:

- https://code.claude.com/docs/en/sessions
- https://code.claude.com/docs/en/agent-sdk/sessions

## Gemini Interactions API

Stateful mode uses `previous_interaction_id`; the server then restores conversation history and tool/thought linkage internally. Thought signatures are handled server-side in stateful mode.

Primary sources:

- https://ai.google.dev/gemini-api/docs/interactions-overview
- https://ai.google.dev/gemini-api/docs/thought-signatures

## General lesson

The caller carries:

```text
opaque handle
```

while the runtime resolves:

```text
hidden/structured state
```

Soma cannot restore hidden ChatGPT model state, but the interface pattern is still useful for Soma-owned continuation metadata.

---

# 3. Candidate Soma handle

Conceptually:

```text
continuation_context_ref = "ctx_..."
```

Soma resolves it to:

```text
continuation_id
contract_revision_id
context generation / validity metadata
```

The handle is returned by:

- `continuation open`;
- `continuation resume`;
- `contract revision update`.

Sol carries the one opaque value when it wants a checkpoint or tracked effect associated with that current governing context.

---

# 4. This handle is NOT authorization

Hard rule:

> Possessing a continuation context handle grants no capability.

It must never bypass:

- ProjectScope;
- repository authorization;
- tool profile authorization;
- provider credentials;
- Task/Run control authority;
- owner gates such as Codex explicit authorization.

The handle is only:

```text
continuation association + current governing contract identity
```

Call it a context reference/handle rather than an access token if necessary to avoid capability semantics.

---

# 5. Contract revision invalidates old context handles

Suppose:

```text
R3 current
ctx_A -> continuation K + R3
```

Owner/controller direction changes and Soma records R4.

Soma returns:

```text
ctx_B -> continuation K + R4
```

If an old Chat later submits a tracked effect with `ctx_A`, Soma mechanically resolves:

```text
ctx_A basis = R3
current contract = R4
```

and rejects:

```text
stale_continuation_context
```

No semantic reasoning inspection is involved.

---

# 6. Parallel effects remain valid

Unlike a single-use CAS token, `ctx_B` is reusable while R4 remains current.

Therefore Sol may naturally issue:

```text
call A(ctx_B)
call B(ctx_B)
call C(ctx_B)
```

in parallel.

All are associated with the same current governing contract.

No sibling call invalidates another.

This is essential for natural agent tool use.

---

# 7. Handoff checkpoint becomes simple

Instead of:

```text
checkpoint(
  continuation_id,
  basis_contract_revision_id,
  expected_state_version,
  structured_capsule...
)
```

prefer conceptually:

```text
checkpoint(
  continuation_context_ref = ctx_B,
  handoff_text = "...free-form engineering handoff...",
  request_id = ...
)
```

Soma resolves the context handle and performs only mechanical validation.

If the governing contract changed, checkpoint is stale and Sol should resume/reconcile before publishing a new canonical handoff.

---

# 8. Effect association becomes simple

For effect gateways that support continuation association:

```text
normal effect request
+ optional continuation_context_ref
```

Soma mechanically records:

```text
this canonical Task/Run/effect was initiated under continuation K contract R4
```

No source classification.

No decision basis.

No reasoning-state payload.

No continuation execution scheduler.

---

# 9. Context handle implementation options

The exact representation belongs in implementation planning, but candidates include:

## A. Random opaque row identity

```text
ctx_<random>
```

stored on/with contract revision.

Pros:

- simple;
- easy revocation/status lookup;
- no embedded semantics.

## B. Deterministically derived opaque identity

Hash/domain-separated identity from continuation + contract revision + salt/material.

Pros:

- reproducibility where desired.

Cons:

- care required not to accidentally turn hash material into auth semantics.

## C. Signed self-describing token

Not preferred for v1.

It adds key management/expiry/claim semantics that are unnecessary when Soma already has local SQLite lookup.

Recommendation: random opaque reference stored locally.

---

# 10. Handle lifetime

A context handle remains mechanically current while:

```text
continuation is open
and
its referenced contract revision is current
```

It may remain stored historically after supersession for provenance, but effect/checkpoint use returns stale.

Completion/cancellation also makes the handle inactive for new associated effects unless a query-only operation explicitly allows historical use.

---

# 11. Does this solve exact Chat session identity?

No.

The handle is **not** a ChatGPT conversation ID.

Different Chat instances may receive/use the same current Soma context handle.

That is intentional after Iteration 26: continuation does not impose a reasoning single-writer lock.

The handle identifies shared durable semantic context, not one model session.

---

# 12. What fresh Sol receives

A minimal resume response can provide:

```text
continuation_context_ref = ctx_B
current contract text/ref
latest free-form Sol handoff
associated canonical effects + current statuses
continuation metadata/history refs
```

Fresh Sol then reasons normally.

The only continuation-specific scalar it needs to carry into later tracked effects/checkpoints is `ctx_B`.

---

# 13. What if Sol forgets the handle?

This is recoverable.

Sol can call `continuation resume/status` again and receive the current handle.

The handle is not secret and should not require owner reconstruction.

This is much safer than expecting Sol to reconstruct multiple IDs from prose.

---

# 14. What if the handle is copied into another Chat?

That is allowed as semantic continuation.

It does not grant external mutation permission.

Normal tool authorization still applies.

If the contract has changed, the copied old handle is rejected as stale.

---

# 15. Relationship to continuation state_version

State version remains internal/mechanical for continuation metadata CAS.

The model does not normally need to carry it for effect association.

This is an important simplification:

```text
model-facing continuity = context handle
internal lost-update protection = state_version
```

Do not expose internal CAS fields to Sol unless a specific mutation operation genuinely requires them and cannot resolve replay safely otherwise.

---

# 16. Relationship to request idempotency

The continuation context handle does not replace effect request identity.

Example:

```text
ctx_B              -> which continuation/contract context
run_request_id X   -> which logical Run start
request_hash H     -> exact effect request material
```

A lost Run response is recovered via Run request-id replay, not via the continuation handle.

Keep these authorities separate.

---

# 17. Historical lineage becomes easy

Effect receipt can store:

```text
continuation_context_ref
resolved continuation_id
resolved contract_revision_id
canonical effect kind/id
request identity
created_at
```

When the contract later changes, historical effects remain accurately tied to the context under which they were initiated.

No rewriting.

---

# 18. Model-formatting burden test

Compare prior candidates.

## Iteration 16 style

Model had to reason about/populate:

```text
contract partition
handoff fields
frontier
sources
roles
pending intents
```

## Iteration 23 style

Model still had to populate:

```text
decision_basis
continuation version
contract revision
```

## Current candidate

Model supplies:

```text
free-form handoff text when checkpointing
one opaque context handle when associating tracked durable work
normal canonical tool arguments
```

This is a major reduction in semantic formatting dependency.

---

# 19. Acceptance scenarios

## Resume

```text
owner: continue
Sol -> continuation resume
Soma -> ctx_B + contract + handoff + effect status
```

PASS.

## Parallel calls

```text
A(ctx_B), B(ctx_B), C(ctx_B)
```

All may proceed under normal resource/effect rules.

PASS.

## Contract change

```text
R4 replaces R3
ctx_A bound to R3
```

Effect/checkpoint using ctx_A rejected stale.

PASS.

## Lost handle

Resume returns current handle again.

PASS.

## Unauthorized operation

Valid ctx_B + unauthorized tool action remains unauthorized.

PASS.

---

# 20. Verdict

**ADOPT OPAQUE CONTINUATION CONTEXT HANDLE AS THE PRIMARY MODEL-FACING CONTINUATION IDENTITY.**

The interface principle becomes:

> Sol should carry one opaque durable context reference, not reconstruct Soma's continuation protocol.

This follows the successful session/interaction pattern used by mature agent runtimes while remaining honest that Soma provides semantic re-entry, not exact ChatGPT runtime resumption.

The next iteration should perform a full minimality/UX attack on the current candidate:

```text
continuation root
contract revisions
free-form handoffs
command/effect receipts
opaque current context handle
Run request idempotency enhancement
```

and look specifically for any remaining field that exists only because earlier research assumed Soma needed to understand Sol's reasoning.
