# Iteration 17 - Adversarial Attack on Iteration 16 Architecture

Date: 2026-08-15
Status: ATTACK AUDIT - Iteration 16 survives at the authority boundary but does NOT survive unchanged as an implementation-ready architecture
Track: Sol-centric agentic reasoning architecture

This iteration deliberately tries to falsify the conclusions of Iteration 16 rather than defend them.

The attack uses:

- current `openai/codex` turn/compaction behavior;
- current OpenAI Agents SDK session and resumable-RunState semantics;
- graph-runtime checkpointing as a counterexample where the runtime truly owns next-step state;
- current Soma Task/Run/ProjectScope/Knowledge/public gateway source;
- crash, concurrency, provenance and observability thought experiments.

The goal is not to add features. It is to identify claims in Iteration 16 that are too strong, under-specified, or assigned to the wrong authority.

---

# 1. Executive attack verdict

The central architecture survives:

> Sol remains the semantic reasoning authority. Soma should provide durable tools, external-state truth, evidence and semantic re-entry support without becoming a semantic planner/workflow engine.

The following Iteration 16 conclusions also survive:

- no persisted `reason -> act -> observe -> reason` cognitive state machine;
- no default reasoning worker beneath Sol;
- no universal Task wrapper;
- fast path remains first class;
- continuation is optional durability scaffolding;
- Work does not need a duplicate Soma cognitive driver;
- no automatic pending-intent execution;
- no global observation bus required for v1;
- no repository mutation lock for reasoning/continuation reads;
- exact runner resume is unavailable to normal-Chat Soma;
- a model-authored operational handoff is a reasonable semantic-resumption substitute when exact conversation/runtime state is unavailable.

However, seven important parts fail or need material correction:

1. a capsule frontier does **not prove semantic incorporation**;
2. an `exact owner contract` cannot be claimed without trustworthy provenance from owner-origin material;
3. current contract state and Sol handoff state have different lifecycles and should not be coupled as if every contract revision were a semantic checkpoint;
4. same-continuation concurrent controllers can create split-brain side effects unless tracked effects cross a pre-effect CAS boundary;
5. direct Run-based effects currently lack strong controller-request correlation, so launch-to-link recovery can be ambiguous;
6. `one control owner per effect` invents a new authority in the continuation layer and should not be a v1 capability rule;
7. a registered-source frontier is only **bounded observability**, never proof that all relevant world changes were seen.

Therefore:

> **Iteration 16 should remain an important synthesis, but it is not safe to use as the final implementation authority without a correction synthesis after this attack.**

---

# 2. Attack: capsule frontier cannot prove semantic incorporation

Iteration 16 says a new Sol-authored capsule with frontier F is the durable claim that the handoff "incorporates" F.

That is still too strong.

Soma can prove only that:

- source tokens F were supplied/submitted with the capsule;
- local tokens were stale-checked where supported;
- the controller/model chose to write a handoff associated with F.

Soma cannot inspect hidden reasoning and therefore cannot prove that Sol actually understood, considered, or semantically integrated every observation represented by F.

The same epistemic problem that invalidated `ack_observations == incorporated` also applies to `capsule frontier == incorporated`.

## Correction

Rename the semantic claim.

Prefer:

```text
basis_frontier
or
declared_basis_frontier
```

Meaning:

> These are the source observations the controller declared as the external evidence basis for this handoff.

Do **not** claim:

```text
semantically incorporated frontier
```

as a mechanically provable fact.

This still supports delta calculation:

```text
current registered-source token != prior basis token
```

without pretending Soma can attest to cognition.

## Verdict

MATERIAL CORRECTION.

The no-ack simplification survives, but its replacement must be phrased as controller-declared evidence basis, not proof of semantic incorporation.

---

# 3. Attack: `exact owner contract` provenance is not actually proven

Iteration 16 labels the controller contract as exact/high-authority owner objective and constraints.

In normal Chat, Soma receives tool-call arguments authored by Sol. Soma does not independently receive the originating ChatGPT user-message object, its immutable message ID, or a cryptographic proof that a submitted string was copied byte-for-byte from the owner message.

Therefore this sequence is possible:

```text
owner says X
 -> Sol interprets/paraphrases X as X'
 -> continuation_action.open(contract=X')
 -> Soma hashes X'
```

Soma can prove that X' is exactly what the controller submitted.

It cannot prove that X' is exactly what the owner originally said.

Calling X' an `exact owner contract` creates false provenance.

## Current agent-runtime comparison

Runner-owned session systems can persist original user input items because the runner owns that message stream. Soma normal Chat does not.

That missing boundary matters.

## Correction

Contract provenance must be explicit.

Possible authority classes:

```text
owner_confirmed_exact
controller_captured_owner_text
controller_interpretation
external_authoritative_ref
```

Exact names are planning detail; the invariant is not.

Soma must never upgrade controller-supplied text to owner-authenticated truth merely because it is content-hashed.

If a future ChatGPT/App interface exposes immutable owner-message references, Soma can strengthen provenance later.

Until then, default normal-Chat capture is controller-origin material that may contain exact quoted owner text but is not independently authenticated as such.

## Security implication

If owner-origin material contains secrets/sensitive text, "preserve exact" conflicts with "do not store secrets in capsule text".

The architecture needs protected exact references where necessary, plus a safe projected contract view.

Redaction cannot be described as exact preservation of the original bytes.

## Verdict

MATERIAL CORRECTION.

The contract/handoff authority split survives, but `owner exactness` must become provenance-aware rather than assumed.

---

# 4. Attack: contract lifecycle and handoff lifecycle are improperly coupled

Iteration 16 stores:

```text
controller_contract
prior_sol_handoff
basis/frontier
```

inside one immutable capsule.

But these have different semantic lifecycles.

A high-authority contract can change because the owner changes direction.

A Sol handoff changes because Sol re-evaluates the situation.

Those events do not have to happen simultaneously.

## Failure case

```text
Capsule C1:
  contract V1
  handoff H1 authored against V1

owner changes contract to V2

system creates C2 merely to carry V2
but reuses/copies H1
```

A fresh Sol may now see H1 next to V2 and incorrectly infer that H1 was reasoned under V2.

The inverse failure is also possible: forcing Sol to author a new handoff immediately merely because the contract changed creates unnecessary semantic work and may generate low-quality placeholder state.

## Better authority ownership

The continuation root should probably own the **current contract revision/reference**:

```text
controller_continuations
  current_contract_ref/hash
  current_contract_version
  contract_provenance
  state_version
  latest_capsule_id
```

A capsule should carry:

```text
basis_contract_ref/hash/version
handoff
basis_frontier
```

Meaning:

> Handoff H was authored under contract version V.

If current contract becomes V+1 while latest handoff still references V, resume reports:

```text
contract_changed_since_handoff = true
```

and Sol reconciles before following the old handoff.

## Does this require a fifth table?

Not necessarily.

The four-table shape can survive if the continuation root stores the current bounded contract/ref and contract mutation is journaled in `continuation_commands`.

A separate immutable contract-revision table may still be justified later if full contract revision history or large protected bodies require it, but the attack does **not** prove a fifth table is mandatory.

It does prove that Iteration 16 assigns current contract ownership to the wrong record.

## Verdict

MATERIAL CORRECTION.

Four tables remain plausible, but field/authority ownership must change.

---

# 5. Attack: same-continuation split-brain is not safely handled

Iteration 16 correctly allows multiple unrelated continuations to reason concurrently.

But it does not adequately address two Chat/Sol instances resuming the **same continuation** concurrently.

Example:

```text
Chat A resumes continuation K at version 8
Chat B resumes continuation K at version 8

A reasons -> launch side effect EA
B reasons -> launch side effect EB

only later do they attempt checkpoint/source registration
```

A CAS conflict on the later checkpoint is too late. Both effects may already exist.

This is analogous to why runner-owned conversation systems need a coherent single logical history/serialization boundary. Soma cannot serialize Sol reasoning, but it can serialize durable continuation mutations before a tracked effect is launched.

## Do NOT solve this with a repository lock

That would violate the multi-project/no-reasoning-lock invariant.

Do NOT hold a long database lease while Sol thinks either.

## Better solution: pre-effect continuation CAS

For any side effect that wants continuation-level crash/control semantics:

```text
Sol decides effect(s)
 -> reserve pending intent(s) under expected continuation version
 -> commit short CAS transaction
 -> only successful reserver launches those effect(s)
```

A stale concurrent Sol loses the CAS before causing the tracked effect and must re-resume/reconcile.

Parallel effects chosen in one reasoning episode can reserve multiple intents in one bounded mutation.

This creates **single-writer semantics only at the durable effect boundary**, not a lock on reasoning.

Read-only reasoning remains fully concurrent.

## Consequence

Iteration 16 says Sol "may" checkpoint before a long/risky effect.

For an effect advertised as crash-safe continuation-controlled work, that boundary must be **required**, not optional.

Untracked fast-path actions can remain outside this guarantee.

## Verdict

MATERIAL CORRECTION.

No long-lived controller lease is required, but tracked effect launch must have a pre-effect CAS reservation boundary.

---

# 6. Attack: Run effect neutrality is conceptually right but operationally too strong

Iteration 16 correctly rejects Task as a universal wrapper and treats Task/Run as peer effect authorities.

That survives conceptually.

But current Soma source shows an asymmetry:

## Task path

Canonical Task starts expose `controller_request_id` and request-hash/idempotency handling.

## Direct Run path

Current public `RunStartRequest` variants such as local PowerShell/remote PowerShell/Hermes do not expose an equivalent generic `controller_request_id`.

`JobManager._create_and_launch()` normally allocates a new `run_id` internally unless a caller already has access to an internal `reserved_run_id` seam.

Direct Cloudflare/SSH/Docker action families also create durable Runs through existing JobManager execution paths, but the public caller does not generally pre-own a stable Run identity suitable for continuation reconciliation.

## Failure case

```text
intent I is persisted
 -> direct Run action launched
 -> Chat disappears before Run ID is linked to I
 -> two similar concurrent Runs exist
```

A fresh Sol can inspect recent Runs and request fingerprints, but may be unable to prove which Run corresponds to I.

That is **best-effort discovery**, not robust crash correlation.

## Correction: effect adapter capability classes

Effect-neutrality should remain, but a source/effect adapter must advertise its correlation/control strength.

Conceptually:

```text
exact_reserved_identity
stable_idempotency_key
stable_request_correlation
best_effort_discovery
observation_only
```

Only effects with sufficiently strong correlation should be described as continuation crash-safe `control_effect` in v1.

## Architectural options

Preferred long-term direction:

Add a provider-neutral stable request/correlation identity to durable Run creation, persisted in Run authority, rather than wrapping every Run in Task.

Alternative initial restriction:

Use direct Runs as evidence sources, but do not promise deterministic launch-to-link reconciliation until Run correlation is strengthened.

## Verdict

MATERIAL CORRECTION.

`Task is not universal` survives.

`Task and Run are equally ready as crash-safe controlled effects today` does not.

---

# 7. Attack: one control owner per effect invents continuation authority

Iteration 16 proposes:

```text
at most one active continuation may register an effect as control_effect
```

This sounds tidy but is not clearly justified by existing canonical authority.

Task/Run already own:

- state/version;
- cancellation semantics;
- input/checkpoint semantics where supported;
- execution identity;
- recovery.

A continuation relationship should not silently become a new authorization or ownership layer over those authorities.

## Failure cases

- one effect legitimately informs two objectives;
- an owner intentionally coordinates the same durable service/effect from two reasoning objectives;
- a stale/abandoned continuation retains the exclusive claim;
- continuation closure now requires complex claim transfer/release semantics;
- source registration becomes capability authority rather than provenance/relevance metadata.

## Correction

For v1, `continuation_sources.role` should describe **relationship/provenance**, not grant exclusive operational control.

Possible roles:

```text
initiated_effect
evidence_dependency
constraint_source
resource_context
```

Any mutation of the underlying Task/Run remains subject to its canonical authorization, CAS, idempotency and scope rules.

If real workflows later demonstrate a need for semantic single-controller ownership, design it explicitly as a separate coordination primitive with expiry/transfer semantics rather than smuggling it into source registration.

## Verdict

LIKELY REMOVE FROM V1.

The continuation layer should not invent new effect authority without evidence that existing Task/Run concurrency controls are insufficient.

---

# 8. Attack: registered-source frontier is not complete world observability

Iteration 16 sometimes uses language such as "changes since handoff" that can sound complete.

But resume compares only sources Sol previously registered plus newly linked sources.

Relevant world changes may occur elsewhere:

- an unregistered file/repository;
- an external service not represented by an adapter;
- a human manual change;
- an external provider mutation;
- a dependency Sol did not know mattered when it checkpointed.

Therefore:

```text
no registered-source delta
```

does **not** imply:

```text
nothing relevant changed in the world
```

## Correction

Resume output should use explicit bounded language:

```text
registered_source_changes
tracked_source_coverage
unavailable_sources
history_gaps
untracked_world_changes_possible = true
```

The last field may be implicit by contract rather than literally boolean, but the semantics must be impossible to mistake.

`changes_since_handoff` should be defined as:

> changes detected among the registered sources relative to the capsule basis frontier.

Not global change detection.

## Verdict

MATERIAL SEMANTIC TIGHTENING.

The registered-source design survives; completeness claims do not.

---

# 9. Attack: `authoritative current source state` is too strong for remote/live sources

Iteration 16 properly distinguishes live snapshots from durable journals, but it still sometimes calls `current_sources` authoritative.

For local canonical Task/Run/Knowledge state, this can be accurate.

For remote provider/service reads, Soma often only has:

- source-reported snapshot;
- observation timestamp;
- provider consistency semantics;
- bounded freshness;
- possible eventual consistency;
- possible incomplete read.

## Correction

Authority should be represented per adapter:

```text
canonical_local_authority
provider_reported_state
versioned_snapshot
live_snapshot
journal_backed_projection
```

The continuation layer is authoritative about **what it observed and how**, not necessarily about absolute global truth behind a remote provider.

## Verdict

TIGHTEN LANGUAGE/ADAPTER CONTRACT.

---

# 10. Attack: four-table minimality is a hypothesis, not a proven theorem

Iteration 16 says four tables are minimal enough and gives reasonable normalization arguments.

The attack does not prove that four tables are wrong.

But after moving current contract state to the continuation root and weakening `control_effect`, table responsibilities change.

The likely four concerns remain:

```text
controller_continuations
continuation_capsules
continuation_sources
continuation_commands
```

with revised ownership:

## `controller_continuations`

```text
continuation identity/lifecycle/CAS
current contract ref/hash/version/provenance
latest capsule ID
```

## `continuation_capsules`

```text
immutable Sol/owner handoff
basis_contract_version/hash
basis_frontier
checkpoint provenance
```

## `continuation_sources`

```text
relevant canonical source/effect identities
relationship role
adapter/capability metadata
scope identity
origin intent correlation where available
```

## `continuation_commands`

```text
idempotent mutation/CAS journal
```

A fifth immutable contract-revision table remains an optional normalization choice if implementation evidence shows command references are insufficient.

## Verdict

FOUR TABLES STILL PLAUSIBLE, NOT YET FROZEN.

Implementation planning should prove the exact schema from required invariants rather than treating the number four as architecture doctrine.

---

# 11. Attack: capsule handoff schema may be over-structured

Iteration 16 lists fields such as:

```text
situation_summary
current_interpretation
explicit_decisions
rejected paths
operational success criteria
unresolved questions
working plan
resume focus
```

These are useful prompts for a high-quality handoff, but requiring every field structurally can create ceremony, empty filler and pressure the model to manufacture state that does not exist.

Current Codex compaction guidance is deliberately compact and task-dependent rather than a giant fixed semantic state schema.

## Correction

Separate:

```text
mechanically required envelope
```

from:

```text
model-authored handoff body/schema version
```

Mechanically required fields should be small:

- identity/time;
- basis contract version;
- basis frontier;
- handoff content hash/schema version;
- perhaps bounded structured `pending_effect_intents` because crash reconciliation depends on them.

The rest can be a bounded structured-or-text handoff whose guidance tells Sol what information is useful when applicable.

Do not force `working_plan`, `rejected_paths`, or `resume_focus` to exist on every checkpoint.

## Verdict

SIMPLIFY REQUIRED SCHEMA.

The handoff concept survives; a rigid pseudo-cognitive form should not.

---

# 12. Attack: exact contract preservation versus privacy/secret discipline

The design simultaneously wants:

```text
preserve exact owner/controller terms
```

and:

```text
do not store secrets in continuation text
```

These can conflict.

Example owner request may contain:

- token/credential;
- private endpoint;
- sensitive personal data;
- confidential document excerpt.

A mechanical redactor changes the exact text.

## Correction

Contract storage must support:

```text
safe projected contract
+
protected exact reference when necessary
```

The protected record may live in existing protected evidence/artifact storage or another already-approved secure authority; Iteration 17 does not prescribe a new secret store.

Resume should receive only the minimum authorized projection/reference required for the current operation.

## Verdict

MATERIAL SECURITY DETAIL FOR PLANNING.

---

# 13. Attack: resume selection can pick the wrong objective

Iteration 16 says a fresh Chat may receive only `continue`, list open continuations and select the obvious one.

This is a desired UX, not a guaranteed deterministic fact.

If several open continuations have similar labels/resources/recency, automatic selection can resume the wrong objective.

## Correction

Define confidence/ambiguity behavior mechanically:

```text
one unambiguous candidate -> resume
multiple plausible candidates -> show concise disambiguation
no plausible candidate -> ask owner rather than guessing
```

Do not use a local semantic model to choose.

This remains compatible with Sol making the semantic choice from deterministic candidate metadata.

## Verdict

NO ARCHITECTURE BREAK; ACCEPTANCE TEST MUST INCLUDE AMBIGUITY.

---

# 14. Attack: "no global observation bus" remains correct, but source adapters need explicit capability contracts

A generic source interface is useful only if it does not pretend all sources behave alike.

Every adapter should expose capabilities such as:

```text
supports_stable_version
supports_history_watermark
supports_exact_correlation
supports_local_stale_check
supports_parallel_read
consistency_class
observation_class
```

Then resume logic can remain mechanical.

Without this capability layer, conditional logic migrates into one giant adapter switch and the abstraction stops being honest.

## Verdict

SURVIVES WITH CAPABILITY MATRIX.

---

# 15. Corrected concurrency model

The audit recommends **not** adding a long-lived "reasoning owner" lease.

That would make reasoning brittle and recreate lock semantics the owner explicitly does not want.

Instead:

```text
many controllers may READ/reason from continuation K

only mutation against expected continuation_version V may commit

tracked side effects require:
  reserve intent(s) under expected V
  -> successful CAS advances version
  -> then launch

stale controller:
  CAS fails before tracked launch
  -> re-resume/reconcile
```

This provides optimistic single-writer semantics at durable decision/effect boundaries while preserving lock-free reasoning.

---

# 16. Corrected effect model

Do not define a binary `control_effect` capability merely from registration role.

Instead distinguish:

```text
relationship:
  initiated_effect
  evidence_dependency
  constraint_source
  resource_context

adapter correlation strength:
  exact/stable
  idempotent
  request-correlated
  best-effort
  none
```

Crash-safe controlled launch requires sufficient correlation strength plus pre-effect intent CAS.

A Run can still be a first-class source even if it is only observation/best-effort correlated.

This preserves effect-neutrality without overpromising exactly-once-like recovery.

---

# 17. Corrected contract/handoff model

Working revised shape:

```text
ControllerContinuation
  continuation_id
  state
  state_version

  current_contract
    contract_ref_or_bounded_body
    contract_hash
    contract_version
    provenance_class
    protected_ref?

  latest_capsule_id
```

```text
ContinuationCapsule
  capsule_id
  continuation_id
  predecessor_capsule_id
  authored_at

  basis_contract_hash/version

  handoff
    bounded model/owner-authored operational handoff
    non-authoritative

  basis_frontier
    registered source observation tokens declared as basis

  pending_effect_intents[]  # only when relevant
```

If:

```text
current_contract_version != capsule.basis_contract_version
```

resume must expose contract drift before the old handoff is followed.

This is cleaner than pretending a contract update and a semantic checkpoint are the same event.

---

# 18. Corrected resume authority structure

A safer resume projection is:

```text
current_controller_contract
  provenance-aware current high-priority instruction/constraint material

prior_sol_handoff
  non-authoritative handoff authored under basis_contract_version

contract_delta
  current contract changed since handoff? exact revision/hash relationship

registered_sources
  bounded per-adapter observations

registered_source_deltas
  current tokens vs capsule basis frontier

coverage_and_uncertainty
  unavailable/gapped/untracked/best-effort/ambiguous facts

pending_intent_reconciliation
  exact/best-effort/unresolved correlation status

retrieval_refs
  deeper evidence
```

Avoid the word `incorporated` in mechanical fields.

Avoid presenting registered-source deltas as global world completeness.

---

# 19. What Iteration 16 got right and should NOT be reopened

This attack did **not** find evidence for moving semantic reasoning back into Soma.

It did not justify:

- Agent/Worker reasoning as default;
- Supervisor semantic routing;
- workflow DAG as normal-Chat cognition;
- automatic specialist fallback;
- automatic pending-intent execution;
- Task as universal execution wrapper;
- automatic next-step choice;
- repository locks around reasoning;
- Company as mandatory parent of normal continuation.

The strongest conclusion from the entire research track remains:

> **Soma should improve the interface and durability around Sol, not replace Sol's reasoning.**

---

# 20. New implementation blockers discovered by this attack

Do not draft a final implementation plan until these are resolved explicitly:

1. contract provenance model;
2. current-contract ownership/lifecycle versus capsule basis contract;
3. basis-frontier terminology and semantics (declared basis, not proven cognition);
4. pre-effect continuation CAS rule for tracked side effects;
5. direct Run correlation/idempotency strategy or explicit v1 capability restriction;
6. removal/redefinition of exclusive `control_effect` ownership;
7. registered-source coverage/uncertainty contract;
8. adapter capability matrix;
9. minimal required versus optional handoff schema;
10. secret/protected exact-contract representation.

---

# 21. External architecture evidence used in the attack

## OpenAI Codex

Current Codex turn code continues model sampling while follow-up work or pending input exists and performs context compaction when needed. This supports the high-level Sol-driven adaptive trajectory conclusion.

Codex's current compaction prompt asks for a concise handoff containing progress, decisions, constraints/preferences, remaining work and critical references for another LLM. This supports an operational handoff, not a persisted cognitive state machine.

## OpenAI Agents SDK

Current Sessions preserve original conversation items across runs when the SDK owns the history, while `RunState` captures exact resumable runner state for interruptions because the SDK owns the runner. That contrast supports the claim that Soma normal Chat can only offer semantic resumption, but it also exposes why Soma cannot honestly claim authenticated original owner-message provenance unless such a message identity is supplied to it.

The Agents SDK also handles server-managed conversation locking/retry semantics, illustrating that a shared logical conversation/continuation needs coherent mutation ordering even though model cognition itself need not be locked.

## Graph runtimes

LangGraph checkpoints explicit `next` graph nodes because the graph runtime owns that topology. This remains a counterexample showing why Soma should not persist next semantic steps for Sol.

---

# 22. Final adversarial verdict

**ITERATION 16: PARTIALLY ACCEPTED, NOT IMPLEMENTATION-READY AS WRITTEN.**

Accepted architectural core:

```text
Sol = semantic reasoning authority
Soma = agent interface + durable external truth + semantic re-entry substrate
```

Rejected/modified details:

```text
capsule frontier proves semantic incorporation       -> NO
exact owner contract provenance by default           -> NO
contract must live only inside capsule               -> NO
tracked effect can launch before continuation CAS    -> NO
all Runs equally crash-correlatable today            -> NO
one continuation owns effect control by registration -> NOT JUSTIFIED
registered sources imply complete change coverage    -> NO
```

Revised direction:

```text
current provenance-aware controller contract
+
Sol-authored handoff tied to the contract version it was authored under
+
controller-declared basis frontier
+
registered-source bounded observations/deltas
+
pre-effect CAS intent reservation for tracked side effects
+
source-adapter capability/correlation semantics
+
canonical Task/Run/world authorities remain independent
```

The next research step should be a **correction/convergence iteration**, not implementation planning yet. That iteration should decide the Run correlation strategy and freeze the exact four-table (or justified five-table) authority ownership after the above corrections.

No runtime implementation is authorized by this audit.
