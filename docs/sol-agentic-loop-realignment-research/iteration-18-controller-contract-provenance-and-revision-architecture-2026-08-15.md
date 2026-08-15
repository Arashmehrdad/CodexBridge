# Iteration 18 - Controller Contract Provenance and Revision Architecture

Date: 2026-08-15
Status: RESEARCH - focused alternative search after Iteration 17 attack
Track: Sol-centric agent interface / semantic continuation

---

# Research question

Iteration 17 found that Iteration 16's `controller_contract` model had two coupled defects:

1. Soma cannot independently prove that text submitted by Sol is byte-for-byte identical to the originating ChatGPT owner message, because Soma does not own ChatGPT conversation items or the hidden model runner.
2. Putting the current controller contract inside every Sol-authored continuation capsule couples two different lifecycles: owner/controller requirement revision and model-authored semantic handoff revision.

This iteration asks:

> What is the smallest honest contract authority that lets a fresh Sol know what objective/constraints currently govern the continuation, what prior handoff was authored under, and where the governing contract came from - without pretending Soma owns ChatGPT message history or forcing owner confirmations on ordinary work?

---

# 1. External runtime evidence

## 1.1 OpenAI Agents SDK Sessions

OpenAI Agents SDK Sessions preserve actual conversation items because the SDK/runtime owns the session history. Before each run, session history is loaded and prepended to new input; after a run, new user, assistant and tool items are persisted.

Source:
- https://openai.github.io/openai-agents-python/sessions/

This is stronger provenance than Soma has for normal Chat because Soma does not receive ChatGPT's canonical conversation item stream.

## 1.2 OpenAI Agents SDK RunState

`RunState` can serialize an interrupted agent run because the SDK owns the runner, model responses, generated items, approval state and optional server-managed conversation identifiers.

Source:
- https://openai.github.io/openai-agents-python/ref/run_state/

Again, Soma normal Chat does not own this boundary.

## 1.3 Codex App Server

Codex app-server owns named thread/turn/item identities. A thread can be resumed using its thread ID, and turn steering uses an expected turn ID to prevent steering the wrong active turn.

Source:
- https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md

This shows a useful general principle: when the runtime owns the input/event stream, it can give exact provenance and concurrency identity. Soma should not claim an equivalent guarantee where it does not own the upstream stream.

---

# 2. Current Soma precedents

## 2.1 Company `plan_revisions`

Current Company source already uses the shape needed for durable accepted plan authority:

```text
mission root
  current_plan_revision_id

plan_revisions
  plan_revision_id
  mission_id
  revision_number
  parent_plan_revision_id
  plan_contract_json
  plan_content_hash
  accepted_by_ref
  acceptance_basis_ref
  controller_request_id
  request_hash
  accepted_at
```

The Mission root points at the current immutable PlanRevision.

A new revision is admitted under CAS against current revision/state version, and controller request replay is hash guarded.

This is a stronger precedent for continuation contracts than copying current contract text into every handoff capsule.

## 2.2 Canonical Knowledge

Knowledge already distinguishes `authority_class` and provenance metadata such as controller, source references, revision, content hash and temporal validity.

This reinforces a second principle:

> content identity and authority/provenance are separate concerns.

A correct hash proves exact stored content, not that the content originated from a particular upstream authority.

---

# 3. Alternative A - contract embedded only in capsules

Shape:

```text
ContinuationCapsule
  contract
  handoff
  frontier
```

## Strengths

- fewest tables;
- one self-contained handoff object;
- every capsule has the contract it claims to use.

## Failures

### Lifecycle coupling

Owner changes and Sol handoffs are independent events.

The owner can change a requirement without Sol yet having produced a new semantic checkpoint.

If a contract update requires a capsule, Soma is forcing a model-handoff event to represent a controller-authority event.

### False authorship

A capsule is conceptually Sol-authored operational state. Embedding the authoritative contract inside it makes it easy to infer that Sol authored or owns the contract.

### Revision loss or duplication

Either every capsule repeats the current contract, creating redundant authoritative copies, or contract-only revisions cannot exist.

## Verdict

REJECT.

Iteration 16 should not keep contract authority inside the capsule as its primary home.

---

# 4. Alternative B - current contract on continuation root, copy old contract into capsules

Shape:

```text
controller_continuations
  current_contract_json
  current_contract_hash
  contract_version

continuation_capsules
  basis_contract_version
  basis_contract_copy
  handoff
  frontier
```

## Strengths

- current requirement is directly discoverable;
- contract can change independently from handoff;
- prior capsule can preserve the old contract it used.

## Failures

### Historical contract changes can disappear

Suppose contract moves:

```text
V1 -> V2 -> V3
```

while no semantic handoff is written between V1 and V3.

If the root is mutable and only capsules preserve old copies, V2 can disappear as a durable authority event.

That may matter for audit, owner correction history, and explaining why an effect was authorized at a particular moment.

### Authoritative duplication

The root and multiple capsules may all hold copies of authoritative contract content.

That creates more integrity rules than a normalized revision authority.

### Root overwrite recovery

A corrupted/interrupted implementation must prove that current pointer/content/version moved consistently. This is solvable transactionally, but it is still inferior to immutable revision rows plus pointer update.

## Verdict

VIABLE but not best.

Use only if contract revision history is deliberately declared unnecessary. Current Soma design philosophy strongly favors preserving authority-changing history, so that tradeoff is not attractive.

---

# 5. Alternative C - immutable contract revisions + root pointer

Shape:

```text
controller_continuations
  continuation_id
  current_contract_revision_id
  state
  state_version
  latest_capsule_id

continuation_contract_revisions
  contract_revision_id
  continuation_id
  revision_number
  parent_contract_revision_id
  contract_json / contract_ref
  contract_hash
  provenance_class
  source_ref / source_locator
  asserted_authority
  controller_request_id
  request_hash
  created_at

continuation_capsules
  capsule_id
  continuation_id
  basis_contract_revision_id
  handoff
  basis_frontier
```

## Strengths

### Independent lifecycles

Owner/controller contract can advance without inventing a new Sol handoff.

Sol handoff can advance without rewriting the governing contract.

### Exact historical relationship

A capsule states only:

```text
I was authored against contract revision R
```

If the current contract has since advanced:

```text
current_contract_revision_id != capsule.basis_contract_revision_id
```

resume can mechanically expose:

```text
contract_changed_since_handoff = true
```

### Historical authority is immutable

Effects/intents/capsules can reference the exact contract revision that governed them.

### Existing Soma precedent

This closely matches Company's root-pointer + immutable `plan_revisions` architecture without importing Company semantics into normal Chat continuation.

### No need to pretend the capsule owns owner authority

Capsule stays purely model-authored operational handoff.

## Cost

- one additional table;
- one additional revision identity;
- slightly more schema/API surface.

## Verdict

PREFERRED.

The extra table is justified because it represents an actual independent authority/lifecycle, not implementation ceremony.

---

# 6. Provenance problem: what Soma can and cannot truthfully claim

## Soma can prove

If Sol calls a future continuation tool with contract text X, Soma can prove:

```text
controller submitted X
stored canonical X
hash(X) = H
request identity/hash = R
```

It can also preserve an external immutable source reference if one is available.

## Soma cannot prove in ordinary normal Chat

Without a first-class ChatGPT conversation-item reference supplied by the platform, Soma cannot independently prove:

```text
X is byte-for-byte the owner's original ChatGPT message
X contains every owner instruction relevant to the objective
Sol did not omit surrounding conversation context
```

Therefore v1 terminology must avoid cryptographic-sounding claims such as:

```text
verified_owner_exact
canonical_chat_message
owner_message_hash
```

unless a future upstream integration actually supplies that identity.

---

# 7. Recommended provenance classes

The exact enum belongs in implementation planning, but the semantic classes should distinguish at least:

```text
controller_capture
  controller states that the material captures owner/controller requirements;
  Soma verifies stored bytes/hash only, not upstream Chat provenance.

controller_interpretation
  normalized/structured interpretation authored by Sol/controller;
  explicitly not verbatim owner text.

external_authority_ref
  immutable/content-addressed external source supplied with a verifiable ref/hash.

owner_confirmed_artifact
  owner-approved durable artifact/reference outside ordinary ephemeral chat text,
  only where such a source really exists.
```

A future ChatGPT integration could add:

```text
platform_message_ref
```

if OpenAI ever exposes a stable first-party message/input identity to the app/tool boundary.

Do not invent that now.

---

# 8. Default normal-Chat UX should remain lightweight

The architecture must not require:

```text
"Please confirm this exact contract before I can continue"
```

for ordinary work.

Default behavior can be:

```text
Sol captures a bounded controller contract
provenance = controller_capture or controller_interpretation
```

Fresh Sol then receives both the content and the provenance label.

If the owner later corrects the contract, create a new immutable contract revision.

Owner confirmation should be used only when the owner actually requests or performs a durable acceptance action, not as mandatory bureaucracy.

---

# 9. Contract revision semantics

A contract revision should represent a meaningful governing change, not every conversational turn.

Examples that should create a revision:

- objective changes;
- hard constraint added/removed;
- explicit exclusion changed;
- authorization boundary changed;
- owner changes success/done terms;
- owner explicitly supersedes a prior requirement.

Examples that should normally remain in Sol handoff:

- new hypothesis;
- debugging diagnosis;
- revised working plan;
- derived test criterion;
- implementation preference inferred by Sol;
- temporary resume focus.

---

# 10. Contract revision CAS

Recommended mutation:

```text
update_contract(
  continuation_id,
  expected_current_contract_revision_id,
  expected_state_version,
  controller_request_id,
  contract_material,
  provenance
)
```

Inside one short SQLite transaction:

1. validate continuation open;
2. validate expected continuation state version;
3. validate expected current contract revision;
4. replay/hash conflict check;
5. insert immutable new contract revision;
6. update root current pointer + state_version;
7. commit.

No reasoning, remote call or repo lock inside this transaction.

This mirrors current Soma CAS/revision patterns.

---

# 11. Capsule checkpoint semantics after this correction

Checkpoint no longer contains the authoritative current contract body as its own partition.

Instead:

```text
ContinuationCapsule
  basis_contract_revision_id
  sol_handoff
  basis_frontier
```

At checkpoint time:

- submitted `basis_contract_revision_id` must equal the current contract revision unless an explicitly stale handoff mode is ever justified;
- local frontier tokens are stale-checked where feasible;
- capsule is immutable;
- root latest capsule pointer advances under CAS.

If the contract changes after the checkpoint, the old capsule remains valid as a historical statement of Sol's state under the old contract, but it is visibly stale relative to current requirements.

---

# 12. Resume projection after this correction

Fresh Sol should receive:

```text
current_controller_contract
  current revision id
  contract content/ref
  provenance class
  asserted authority

prior_sol_handoff
  capsule id
  basis contract revision id
  authored_at
  handoff state

contract_delta
  changed_since_handoff = true | false
  previous revision ref if different
  current revision ref

registered_source_deltas
  mechanical source changes relative to capsule basis frontier

coverage_and_uncertainty
  what registered sources do and do not cover
```

This makes a critical case explicit:

```text
owner changed objective while Sol was away
```

Fresh Sol must reconcile the new current contract before following old handoff plans.

---

# 13. Does this force a fifth table?

Yes, and that is acceptable.

The previous four-table minimum was an optimization target masquerading as an architecture invariant.

After Iteration 17, contract authority is clearly independent from:

- continuation lifecycle root;
- Sol handoff capsules;
- registered source relevance;
- mutation command/idempotency journal.

Therefore normalized v1 is now conceptually:

```text
controller_continuations
continuation_contract_revisions
continuation_capsules
continuation_sources
continuation_commands
```

Five tables.

Do not collapse independent authority merely to preserve a nice number.

---

# 14. Why not store active contracts in canonical Knowledge?

Rejected for v1.

Reason:

- active objective contracts are operational continuation state, often temporary;
- Knowledge is intended for reusable durable facts/decisions/preferences/lessons;
- putting every temporary goal/constraint into Knowledge pollutes long-term semantic memory;
- contract revision lifecycle is scoped to one active continuation.

A final stable decision may later be promoted to Knowledge explicitly.

---

# 15. Why not reuse Company PlanRevision?

Rejected.

Company PlanRevision is an accepted organizational/business commitment under Company/Mission authority.

Normal Chat continuation contract is simply the governing owner/controller objective for one Sol reasoning trajectory.

The revision *pattern* is reusable; the authority/domain is not.

---

# 16. Failure tests

The preferred design must pass:

## Provenance honesty

- controller-captured contract is never labelled platform-verified owner text;
- external authoritative reference preserves source identity/hash;
- provenance survives restart.

## Revision lineage

- V1 -> V2 -> V3 all remain addressable even if no capsule exists for V2;
- parent lineage is unambiguous;
- content-identical replay is idempotent;
- same request ID with different content conflicts.

## Contract/handoff skew

- latest capsule basis V2, current contract V3 -> resume says changed;
- capsule is not rewritten;
- old plan/focus is visibly subordinate to V3.

## Concurrency

- two simultaneous contract updates from V2: one wins CAS, one receives stale conflict;
- no repository lock is acquired;
- no remote source read occurs inside the transaction.

## UX

- owner does not need to confirm every capture;
- fresh Chat can understand provenance without owner reconstructing history.

---

# 17. Result

**Iteration 18 verdict: ACCEPT ALTERNATIVE C.**

Replace Iteration 16's contract-inside-capsule authority with:

```text
ControllerContinuation
  -> current ContractRevision

ContinuationCapsule
  -> basis ContractRevision
  -> Sol handoff
  -> declared/basis source frontier
```

Use explicit provenance labels that describe what Soma actually knows.

Do not claim byte-for-byte owner-message provenance unless a future upstream ChatGPT integration supplies a verifiable message/input reference.

The five-table shape is currently better architecture than the previous four-table minimum.

---

# Next research question

Iteration 19 should attack the second major weakness from Iteration 17:

> How should direct durable Run effects gain stable crash-safe correlation and idempotent replay without forcing every Run through canonical Task or creating a second generic executor?
