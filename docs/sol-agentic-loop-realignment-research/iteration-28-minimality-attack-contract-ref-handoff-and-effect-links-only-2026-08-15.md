# Iteration 28 - Minimality Attack: Contract Ref, Free-form Handoff, and Effect Links Only

Date: 2026-08-15
Status: RESEARCH - convergence/minimality attack
Track: Sol-centric agentic reasoning architecture
Builds on: Iterations 24-27

---

## Research question

After removing structured semantic capsules, source registries, decision-basis formatting and effect-level continuation CAS, what is the **smallest durable Soma continuation architecture** that still solves the owner's actual problem?

Attack every remaining table/field that exists only because earlier research assumed Soma needed to understand Sol's reasoning.

---

# 1. Owner problem restated narrowly

Normal Chat/Sol already reasons.

The missing capability is:

```text
Sol works on an objective
 -> external work/state may outlive the Chat context
 -> owner later wakes a fresh Chat
 -> fresh Sol should recover enough context to continue
```

Soma must help without becoming:

- a reasoning engine;
- a workflow/task loop;
- a semantic dependency tracker;
- a model-output parser;
- a second planner.

---

# 2. Current candidate entering this attack

After Iterations 24-27:

```text
continuation root
contract revisions
free-form handoffs
continuation commands/effect receipts
opaque context handle
Run request-idempotency enhancement
```

Attack each piece.

---

# 3. Attack: separate opaque context handle

Iteration 27 proposed a random `ctx_...` handle resolving to:

```text
continuation_id
current contract_revision_id
```

But contract revision identity is already:

- immutable;
- opaque;
- unique;
- associated with exactly one continuation;
- naturally invalidated for current-effect use when superseded.

Therefore a separate stored context-handle mapping is unnecessary.

Use the contract revision ID itself as the model-facing context reference.

Public naming may still call the returned value:

```text
continuation_context_ref
```

but mechanically it can be the immutable current contract revision identity.

This removes one concept and one lookup mapping.

---

# 4. Effect/checkpoint context validation becomes trivial

Given `continuation_context_ref = contract_revision_id R3`:

Soma resolves R3 -> continuation K.

Then mechanically checks:

```text
K is open
K.current_contract_revision_id == R3
```

If yes, context is current.

If not:

```text
stale_continuation_context
```

No state-version token is carried by Sol.

No separate context-token lifecycle exists.

---

# 5. Attack: generic `continuation_commands` table

Why did prior designs need it?

Main reasons were:

- idempotent mutations;
- CAS audit;
- effect-admission receipts;
- replay history.

But after simplification, each actual immutable authority can carry its own idempotency identity.

## Contract revision

Store:

```text
controller_request_id
request_hash
```

on `continuation_contract_revisions`.

## Handoff

Store:

```text
controller_request_id
request_hash
```

on `continuation_handoffs`.

## Continuation open

Store creation request ID/hash on root.

## Complete/cancel

Lifecycle commands can be mechanically idempotent by current state plus optional request identity fields on root/a tiny lifecycle event only if tests prove necessary.

## Effect lineage

A generic command journal is less clear than a direct relation to the canonical effect.

Conclusion:

`continuation_commands` is not obviously required for the simplified v1.

---

# 6. Better fourth authority: `continuation_effect_links`

The one piece we genuinely need beyond root/contract/handoff is automatic lineage for durable effects created after a handoff.

Conceptual v1 table:

```text
continuation_effect_links

id
continuation_id
contract_revision_id
effect_kind = task | run
effect_id
controller_request_id?
created_at
```

Optional safe metadata may identify gateway/operation, but avoid semantic labels.

This row means only:

> canonical effect E was initiated while pursuing continuation K under governing contract revision R.

No ownership.

No dependency semantics.

No next-step semantics.

---

# 7. Why Task/Run only is enough for v1 effect links

Most important Soma durable work already converges on canonical Task or durable Run.

Direct operations such as repository apply, SSH, Cloudflare, Docker and run_start use/produce durable Run authority in existing Soma pathways.

Canonical Task remains available where Task is the higher-level authority.

V1 does not need a universal arbitrary-source/effect link framework.

If a future durable effect genuinely lacks Task/Run identity, add support only after a measured workflow requires it.

---

# 8. Heterogeneous effect relation is mechanical, not semantic

For v1:

```text
effect_kind = task
 -> validate Task exists

effect_kind = run
 -> validate Run exists
```

The effect link never copies effect state.

Resume resolves current status from the canonical Task/Run authority.

No duplicate observation storage.

---

# 9. Could effect association live directly on Task/Run instead?

Alternative:

```text
tasks.continuation_contract_revision_id
runs.continuation_contract_revision_id
```

Rejected as first choice because:

- spreads an optional semantic-continuity concern through core execution tables;
- requires parallel schema changes across heterogeneous authorities;
- makes future effect kinds harder;
- couples Task/Run lifecycle schema to Chat continuation.

A tiny external lineage table is cleaner.

---

# 10. Minimal four-table candidate

The resulting persistence candidate is:

```text
1. controller_continuations
2. continuation_contract_revisions
3. continuation_handoffs
4. continuation_effect_links
```

This is a different four-table design from Iteration 16.

There is no:

```text
continuation_sources
continuation_commands
continuation_effect_intents
decision_basis
frontier
ack cursor
reasoning phase
next step
next Task
DAG
scheduler
```

---

# 11. `controller_continuations`

Minimal role:

```text
continuation_id
safe label
state = open | completed | cancelled
current_contract_revision_id
creation_request_id/hash
created_at
updated_at
closed_at?
```

Do not require:

- model identity;
- conversation ID;
- provider;
- reasoning phase;
- latest handoff pointer;
- repo/project ownership;
- reasoning lock.

Latest handoff can be derived from handoff sequence/time.

---

# 12. `continuation_contract_revisions`

Minimal role:

```text
contract_revision_id    # also model-facing continuation_context_ref
continuation_id
parent_revision_id?
revision_number
instruction_text_or_artifact_ref
content_hash
provenance_class
controller_request_id
request_hash
created_at
```

Current pointer lives on continuation root.

Changing the governing instruction creates a new immutable revision and atomically moves the root pointer.

---

# 13. `continuation_handoffs`

Minimal role:

```text
handoff_id
continuation_id
contract_revision_id
sequence_number
handoff_text
content_hash
controller_request_id
request_hash
created_at
```

No parsed semantic fields.

No frontier.

No source list.

No plan fields.

No private chain-of-thought.

`sequence_number` can be allocated transactionally for deterministic ordering.

Every handoff remains immutable even if another handoff is written later.

---

# 14. Concurrent handoffs

Two Sol branches may checkpoint near-simultaneously under the same contract revision.

Do not delete either.

Assign sequence numbers transactionally.

Resume normally returns the newest handoff plus a bounded indication that additional recent handoffs exist if necessary.

Do not infer semantic supersession merely from sequence.

If real usage shows branch-aware handoff lineage is necessary, add an optional predecessor reference later.

Do not build a branch graph in v1.

---

# 15. `continuation_effect_links`

Minimal role:

```text
link_id
continuation_id
contract_revision_id
effect_kind
effect_id
created_at
```

Possible uniqueness:

```text
UNIQUE(effect_kind, effect_id)
```

for origin lineage in v1.

Other continuations may still read/reference the same canonical effect through normal Task/Run tools; they do not need another origin link.

---

# 16. No general state_version required at model boundary

The root may use internal transactional/CAS mechanics where useful, but Sol should not normally carry a continuation numeric state version.

The high-value stale semantic boundary is current contract revision identity.

For contract update:

```text
expected current context ref = R3
create R4
move pointer R3 -> R4 atomically
```

For checkpoint/effect association:

```text
submitted context ref must still equal current contract revision
```

This is easier for Sol and more meaningful than a generic counter.

---

# 17. No effect single-writer semantics

Several effects under current R3 may proceed in parallel.

Several Sol branches under current R3 may also initiate work.

Underlying resource/effect authorities handle their own conflicts.

Continuation only detects a superseded governing contract, not stale reasoning.

---

# 18. Run request idempotency remains an enabling substrate change

Iteration 19 remains important but separate from continuation persistence.

Direct durable Run creation needs:

```text
logical request identity
normalized request hash
same ID + same hash -> replay existing Run
same ID + different hash -> conflict
```

This lets continuation-associated direct Runs survive lost responses without duplicate launch.

It should be implemented as a general Run capability, useful outside continuation too.

Do not make it a continuation-only wrapper.

---

# 19. Resume bundle can now be extremely simple

Conceptually:

```text
continuation
  id / label / state

context_ref
  current contract_revision_id

controller_instruction
  current contract text/ref + provenance label

sol_handoff
  newest free-form handoff text
  handoff's contract_revision_id
  authored_at

contract_changed_since_handoff
  true/false mechanically derived

associated_effects
  bounded Task/Run links with current canonical status/result/recovery hints

retrieval
  deeper handoff/effect history refs
```

No automatic semantic recommendation.

No source-delta engine.

---

# 20. Fresh Sol behavior

```text
owner: continue

Sol -> continuation resume

Soma returns:
  current context ref
  current controller instruction
  latest free-form handoff
  current status of mechanically linked effects

Sol:
  reads it
  decides which repo/service/files/logs/Knowledge need fresh inspection
  reasons normally
  uses ordinary Soma tools
```

This puts intelligence where it belongs.

---

# 21. Normal active Chat behavior

Most calls remain unchanged.

Continuation-specific behavior is only:

## Checkpoint

```text
handoff_text + current context_ref
```

## Tracked durable effect

```text
normal effect request + optional current context_ref
```

## Contract update

```text
new controller instruction text/ref + previous/current context_ref
```

Everything else is ordinary Soma.

---

# 22. Formatting burden audit

What Sol must semantically format:

```text
one free-form handoff text
```

What Sol must mechanically carry:

```text
one opaque context_ref
```

What Sol no longer formats:

```text
decision arrays
source roles
frontier tokens
evidence basis lists
next-step fields
reasoning phases
pending effect intents
semantic completion criteria schema
```

This directly addresses the owner's historical Agent/Worker formatting failure warning.

---

# 23. What Soma can honestly guarantee

Soma can guarantee:

- immutable contract revision history it was given;
- immutable handoff text it was given;
- which current contract revision is selected;
- whether a submitted context ref is current;
- canonical Task/Run effect identities mechanically linked to the continuation;
- current Task/Run truth from those authorities;
- normal Run/Task idempotency/recovery once the underlying authority supports it.

Soma cannot guarantee:

- handoff semantic completeness;
- reasoning freshness;
- that Sol noticed every relevant fact;
- global world-state completeness;
- that two Sol branches should or should not take the same semantic action.

This is the correct honesty boundary.

---

# 24. Relationship to long-term Knowledge

No change.

Handoff is temporary active-objective semantic continuity.

Knowledge is accepted durable reusable fact/decision memory.

Sol/owner may explicitly promote a stable fact/decision to Knowledge.

Do not automatically parse handoff prose into Knowledge.

---

# 25. Relationship to Work

No change.

Work has its own runner/context.

Default Work behavior remains:

```text
Work/Sol -> Soma tools
```

Continuation is optional for explicit cross-context/cross-surface durability.

---

# 26. Relationship to Company

No change.

Company/Mission/PlanRevision/WorkPackage are durable organizational commitments.

Normal Chat continuation is not Company.

Do not reuse Company plan machinery for free-form Sol handoff.

---

# 27. Adversarial deletion test

Can each table be deleted?

## Delete continuation root?

Lose lifecycle/discovery/current contract pointer.

Keep.

## Delete contract revisions?

Lose immutable governing-direction history and stale-context detection.

Keep.

## Delete handoffs?

Lose semantic re-entry state.

Keep.

## Delete effect links?

Fresh Sol cannot mechanically discover durable effects launched after handoff without broad Run/Task guessing.

Keep.

Four concerns survive deletion attack.

---

# 28. Remaining open questions are implementation-level

Broad architecture no longer depends on unresolved semantic schema questions.

Implementation planning still must determine:

- exact bounded text sizes;
- request-id/hash normalization;
- IDs and migrations;
- how Task/Run gateway internals create effect links transactionally;
- direct Run idempotency migration;
- public gateway shape;
- compact resume projection budgets;
- secret/redaction discipline;
- tests and compatibility inventory.

These do not require Soma to understand reasoning.

---

# 29. Verdict

**CURRENT BEST CANDIDATE: FOUR BORING AUTHORITIES + GENERAL RUN IDEMPOTENCY.**

```text
controller_continuations
continuation_contract_revisions
continuation_handoffs
continuation_effect_links
```

Model-facing semantics:

```text
one opaque current context_ref
one free-form handoff text when checkpointing
```

Everything else stays in existing canonical Soma authorities.

This is materially simpler and less cognitively invasive than Iterations 16-23 and avoids the historical model-formatting failure pattern.

A final adversarial iteration should now try to break this minimal candidate using real owner workflows: interrupted repo implementation, long-running scientific Run, remote-service repair, contract change mid-work, and fresh-Chat `continue`.
