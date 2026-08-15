# Iteration 21 - Continuation Source Relevance, Coverage and Observation Strength

Date: 2026-08-15
Status: RESEARCH - focused alternative search after Iteration 17 attack
Track: Sol-centric agent interface / semantic continuation

---

# Research question

Iteration 17 found two overclaims in Iteration 16:

1. `continuation_sources` risked inventing a new high-level control ownership authority over effects that are already canonically owned by Task/Run/domain authorities.
2. A registered-source frontier can only describe explicitly registered observations. It cannot prove that nothing else in the world changed or that every relevant source was registered.

This iteration asks:

> What should `continuation_sources` mean if registration must not imply exclusive effect control, global monitoring, or complete world coverage, and how should resume expose source changes/freshness honestly without building a universal event bus?

---

# 1. Core correction

Replace the mental model:

```text
continuation owns/monitors these sources
```

with:

```text
continuation declares these canonical external authorities relevant to semantic re-entry
```

Registration is a **relationship/provenance fact**.

It does not transfer authority.

---

# 2. Alternative A - continuation owns controlled effects

Iteration 16 proposed a rule similar to:

```text
at most one continuation may register effect E as control_effect
```

## Intended benefit

Prevent two reasoning objectives from issuing conflicting control operations against one Task/Run.

## Failure

Canonical Task/Run already owns:

- state;
- cancellation/version guards;
- checkpoints/input;
- recovery;
- execution identity.

Adding an exclusive continuation owner introduces a second semantic ownership layer with unclear transfer/lease/recovery semantics.

A continuation may have *initiated* an effect without owning every future legitimate operation on that effect.

Example:

```text
Continuation A starts long benchmark Task T
owner later opens another Chat to inspect or cancel T directly
```

The Task plane should remain the authority for whether cancellation is valid.

## Verdict

REJECT exclusive `control_effect` ownership in v1.

---

# 3. Alternative B - registered sources define a complete dependency/world set

Shape:

```text
all relevant world truth is in continuation_sources
```

Then resume could theoretically say:

```text
no changes since capsule
```

## Failure

Soma cannot generally prove all relevant world state has been registered.

Examples:

- another service becomes relevant after the handoff;
- repository dependency changes outside the registered repo;
- provider-side state changes that the chosen adapter does not project;
- owner changes something manually;
- an effect exists that failed to bind because Chat died;
- a new source matters only after fresh Sol interprets new evidence.

## Verdict

REJECT completeness semantics.

A source registry is an explicit observed/relevant subset, not a closed-world model.

---

# 4. Alternative C - no durable source registry; rediscover everything on every resume

Shape:

```text
capsule has handoff only
fresh Sol rereads repo/tasks/runs/services manually
```

## Strengths

- no source table;
- no false completeness implication.

## Failures

### Loses exact effect provenance

A prior long-running Task/Run identity should not require rediscovery heuristics.

### Expensive fresh-context recovery

Fresh Sol would repeatedly search broad histories to locate obvious known authorities.

### Weak delta comparison

Without a durable baseline of which exact source identities and tokens prior Sol used, resume cannot mechanically distinguish known effect evolution from arbitrary reconstruction.

## Verdict

REJECT.

A bounded registry remains useful if semantics are narrowed correctly.

---

# 5. Alternative D - relevance/provenance registry with explicit observation strength

Preferred shape:

```text
continuation_sources
  continuation_id
  source_kind
  source_id
  relation_kind
  origin_intent_id?
  adapter_version
  scope identity
  active/retired
  safe metadata
```

Meaning:

> This continuation has a durable reason to care about this canonical source during re-entry.

The source remains owned by its native authority.

## Verdict

PREFERRED.

---

# 6. Recommended relation kinds

Avoid authority-bearing words such as `owner` or `control_effect`.

Conceptual relations:

```text
initiated_effect
  source is the canonical effect produced from a continuation effect intent

evidence_reference
  source provides evidence relevant to reasoning

constraint_reference
  source contains current durable facts/constraints that should be checked on resume

resource_context
  source is a world/resource context worth refreshing

result_dependency
  source result is awaited/used by the objective
```

These are semantic relevance labels only.

They grant no cancellation, steering, write or lock authority.

---

# 7. Effect intent is the provenance authority

For continuation-initiated effects, the strongest lineage is:

```text
ContractRevision R
   |
Sol / current continuation state
   |
EffectIntent I admitted under CAS
   |
stable effect request identity
   |
canonical Task/Run E
   |
continuation_sources relation:
  initiated_effect, origin_intent_id=I
```

The source row does not claim to own E.

It says why E is relevant and how it entered this reasoning objective.

---

# 8. Observation adapter capability vector

A single class label such as `durable_journal` vs `live_snapshot` is useful but not expressive enough.

An adapter should publish mechanical capabilities separately.

Conceptual `ObservationCapabilities`:

```text
identity_strength
  stable | scoped_stable | ephemeral

current_state_strength
  local_authoritative | provider_reported | cached | bounded_snapshot

change_detection
  journal_watermark | monotonic_version | snapshot_hash | none

history_strength
  complete_since_watermark | bounded_history | no_history

request_correlation
  exact_idempotent_request | stable_effect_identity | none

scope_revalidation
  project_scope | provider_profile | local_identity | none

freshness_semantics
  transaction_time | observed_at | provider_timestamp | unknown
```

Exact enum names belong in planning.

The point is architectural:

> never let one source token pretend to offer guarantees its adapter does not have.

---

# 9. Observation token semantics

A source observation token should mean:

```text
for adapter version A
and observation domain D
at time T
this bounded projection had identity/state S
with change/history evidence W if available
```

It must **not** silently mean:

```text
the entire underlying resource had no other relevant change
```

unless the adapter can genuinely prove that.

Therefore include or derive an observation-domain/schema identity in the token.

Example:

```text
repo_status.v2
```

is different from:

```text
repo_full_tree_hash.v1
```

Even if both point to the same repository.

---

# 10. Registered-source deltas, not world deltas

Resume terminology should be explicit:

```text
registered_source_observations
registered_source_deltas
```

Avoid:

```text
world_changes
all_changes
nothing_changed
```

unless a specific source adapter can make that statement within a bounded domain.

Global resume should carry a top-level coverage statement such as:

```text
coverage = explicit_registered_sources_only
```

and explain that Sol may inspect additional world state when current reasoning makes it relevant.

---

# 11. Frontier terminology correction

Iteration 17 already found that `incorporated_frontier` overclaims cognition.

With this source correction, the preferred term is:

```text
basis_frontier
```

or:

```text
declared_basis_frontier
```

Meaning:

> these registered source observations were declared as the external evidence basis associated with the Sol handoff capsule.

It does not prove:

- Sol deeply understood every item;
- the source set was complete;
- no unregistered state mattered;
- no transient change occurred outside source history guarantees.

---

# 12. Current canonical source strengths

## Task

Strong local identity and version semantics.

Potential observation material:

- Task state/phase/state_version;
- result/checkpoint/recovery/evidence refs;
- latest Task event ID;
- ProjectScope binding/attempt/quarantine projection;
- backend publication state where needed.

Strength:

```text
stable identity
local authoritative Task row
monotonic state version
durable Task event watermark
scope revalidation
```

## Run

Potential material:

- Run status/state_version;
- result publication state/hash;
- event latest ID/cursor semantics;
- recovery/process identity summaries.

After Iteration 19 enhancement, Run can additionally expose exact logical request correlation for supported starts.

## Knowledge

Strong content/revision authority inside canonical Knowledge domain:

- knowledge ID;
- revision;
- content hash;
- lifecycle;
- provenance/authority class.

## Repository

Without a complete dedicated mutation journal, repo observation remains bounded current state.

Potential domain:

- branch;
- HEAD;
- index/worktree status/fingerprint;
- optionally selected path hashes.

It must be labelled snapshot-based.

Current equality does not prove there was no edit/revert between observations.

---

# 13. Remote/provider source strengths

A provider query may be authoritative for what the provider reports while still lacking local transactional freshness.

Use precise language:

```text
provider_reported_current_state
observed_at = T
provider_timestamp = P if supplied
```

not universal:

```text
authoritative_now
```

For some provider APIs the read may itself have eventual consistency or bounded projection semantics.

Adapters should expose what is known rather than normalize everything to one false strength.

---

# 14. Source registration should validate identity, not semantic necessity

Soma can mechanically validate:

- source exists or is addressable;
- scope/profile authorization is valid;
- source identity format;
- duplicate registration;
- relation shape;
- adapter support.

Soma should not decide:

```text
this source is semantically important enough
this source is irrelevant now
this source should replace another source
```

Those are Sol/controller judgments.

Retirement is explicit controller action or mechanically linked to effect provenance only where the semantics are unambiguous.

---

# 15. Resume should be a partial observability projection

Preferred response shape:

```text
current_contract
prior_sol_handoff
contract_changed_since_handoff

registered_sources:
  source identity
  relation
  adapter capabilities
  current bounded observation
  basis observation
  delta status
  freshness/history status
  retrieval refs

unresolved_effect_intents

coverage:
  explicit_registered_sources_only
  unavailable_source_count
  history_gap_count
  snapshot_only_count
  unbound_intent_count

uncertainty:
  exact mechanical reasons
```

Fresh Sol then decides whether more discovery is needed.

---

# 16. Source refresh should remain pull-based in core

Core `resume` deliberately resolves registered sources when requested.

Do not make registration imply:

- watcher installation;
- continuous polling;
- webhook subscription;
- automatic wake-up;
- background semantic filtering.

Future source-specific observers can improve delivery/freshness as independent adapters.

The semantic continuation architecture must remain correct without them.

---

# 17. Parallel source refresh

Independent registered sources may be refreshed concurrently.

This is mechanical I/O parallelism.

A failed source should usually produce:

```text
source unavailable / stale / auth changed / history gap
```

while preserving successfully refreshed sources.

Do not discard the whole resume bundle merely because one optional provider is unreachable.

Security/scope failure for one source must not be silently downgraded; mark that source inaccessible and avoid leaking prior protected payload.

---

# 18. New-source discovery after handoff

Because registered sources are not complete, fresh Sol can discover a new relevant authority during resume.

Correct flow:

```text
resume registered sources
 -> Sol interprets
 -> Sol discovers source X matters
 -> ordinary read/capability query if needed
 -> register X if durable future re-entry value exists
```

This is expected behavior, not a failure of the registry.

Do not automatically crawl adjacent resources to simulate completeness.

---

# 19. Unbound effect intent belongs in coverage uncertainty

A reserved/claimed intent with no bound canonical Task/Run is an especially important blind spot.

Resume should expose it separately even though there is no source row yet:

```text
unresolved_effect_intent
stable effect request id
correlation capability
launch/bind status
```

Fresh Sol can reconcile using the effect authority's idempotent request lookup/replay.

This closes one of the biggest gaps in the simple source registry model.

---

# 20. Do not infer source retirement from terminal state

A completed Task/Run may remain highly relevant evidence.

Therefore:

```text
Task terminal != retire source
Run terminal != retire source
```

Source retirement means:

> future semantic re-entry no longer needs this source in the default registered projection.

Only Sol/controller decides that, except for explicit cleanup policy approved later.

---

# 21. No source graph in v1

Do not add:

```text
source dependency edges
ready propagation
source-triggered next actions
```

If Sol needs to know that result B depends on Task A, the handoff or canonical Task/Company/Workflow domain may already express that where appropriate.

Continuation sources are a flat relevance/provenance registry.

This avoids recreating Workflow DAG semantics.

---

# 22. Failure tests

## Authority

- registering Task T never grants cancellation authority beyond Task plane;
- same Task can be referenced by multiple continuations as evidence/relevance;
- no exclusive continuation owner field required.

## Coverage honesty

- zero registered deltas -> response does not say global world unchanged;
- snapshot-only repo equality -> no claim of no transient edits;
- new unregistered relevant source can be added after resume;
- adapter observation domain is visible/versioned.

## Adapter strength

- Task exposes version + event watermark;
- Run exposes version + event watermark and request correlation only when supported;
- repo exposes snapshot semantics;
- unavailable remote provider reports freshness/availability uncertainty.

## Partial failure

- 3 sources refresh, 1 provider unavailable -> 3 observations remain usable and 1 explicit uncertainty returned.

## Intent gap

- unbound effect intent appears even with no source row;
- fresh Sol can reconcile through stable effect request identity.

---

# 23. Result

**Iteration 21 verdict: ACCEPT narrow relevance/provenance registry semantics.**

`continuation_sources` remains useful, but its authority is reduced and clarified:

```text
registered source = explicitly relevant canonical external authority
```

not:

```text
registered source = continuation-owned / globally monitored / complete world model
```

Remove exclusive `control_effect` ownership from v1.

Add adapter capability/observation-domain semantics so source tokens are honest about:

- identity strength;
- current-state authority/freshness;
- change detection;
- history strength;
- request correlation;
- scope revalidation.

Resume reports **registered-source deltas and coverage uncertainty**, never universal world completeness.

---

# Next research question

Iteration 22 should converge Iterations 18-21 back into one corrected architecture and attack whether the now-six-table kernel is actually minimal, whether effect-intent admission is too bureaucratic, and whether the resulting normal-Chat UX still feels like Sol naturally using tools rather than operating a transaction system.
