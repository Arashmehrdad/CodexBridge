# Iteration 13 - Registered Observation and Evidence Frontier Architecture

Date: 2026-08-15
Status: RESEARCH ONLY - implementation not authorized
Track: Sol-centric agentic reasoning architecture

## Research question

Iteration 11 showed that observation cannot be coupled one-to-one with Sol actions or canonical Tasks. Iteration 12 proposed a Sol-authored semantic resumption capsule whose evidence basis should be reconciled with current external truth on resume.

This iteration asks:

> How should Soma represent the evidence/world-state frontier that a Sol reasoning capsule has already incorporated, and how should Soma expose what changed afterward, across Tasks, Runs, repositories, ProjectScope, knowledge, services and journals - without creating a global event bus, a competing truth store, or a semantic observer model?

The target is a **bounded registered-source observation frontier**.

---

# 1. Evidence base

## Primary research

### Agent-Computer Observation Interfaces Enable Dynamic Computer Use (Li & Shi, 2026)

The paper identifies action-coupled observation as a limitation in dynamic environments. Its Agent-Computer Observation Interface decouples adaptive observation from discrete actions and persists selected dynamic information as text. The key architectural lesson for Soma is not to copy its media pipeline; it is that **relevant observations can arise independently of an agent action**.

### The Devil Is in the Interface: Evaluating How Tool Architecture Shapes Coding Agent Behavior (Xu et al., 2026)

Controlled experiments show that how tools/information are organized changes agent exploration, consistency, step count and token cost even when the underlying capability set is similar. This strengthens the case for designing Soma's model-facing observation interface deliberately rather than exposing raw internal journals.

## OpenAI Agents SDK

The SDK distinguishes:

- raw model streaming events;
- higher-level run-item events for messages/tool calls/tool outputs/handoffs/approvals;
- final/current RunResult state;
- durable `RunState` for interrupted runner-owned execution.

The event stream is useful operationally, but the complete run result/state remains a separate abstraction.

## OpenHands / other agent runtimes reviewed in Iteration 11

Event streams can be effective internal communication backbones, while the model/controller consumes a maintained State rather than treating the raw stream as the only current truth.

## Soma repository

Current Soma already has multiple strong source-specific authorities:

- canonical Task `state_version`;
- Task event IDs and `latest_event_id(task_id)`;
- RunStore events with earliest/latest event IDs and cursor-gap detection;
- ProjectScope generation, binding/attempt statuses and quarantine/recovery truth;
- repository live state and Git identity through `repo_query`;
- canonical Knowledge record revision/content hash/lifecycle;
- service/provider-specific query surfaces;
- external durable journals in specialized domains.

This means a new global observation store should not duplicate their truth.

---

# 2. Observation is not caused only by Sol actions

The previous Task-centered intuition looked like:

```text
Sol launches Task T
 -> T changes
 -> observation exists
```

That remains valid for many effects, but it is not general enough.

Relevant state can change because:

```text
another Chat/thread modifies the repository
service changes externally
owner provides new information
running process changes state with no Sol call
recovery/quarantine logic detects inconsistency
knowledge record is superseded
external journal receives an event
scheduled/remote system changes independently
```

## Architecture rule

A reasoning continuation may depend on **sources**, some of which are effects Sol controls and some of which are merely evidence/world context.

Therefore:

```text
Task membership != complete observation universe
```

---

# 3. Do not build a global project event cursor

A tempting solution is:

```text
project_event_stream
  every Task event
  every Run event
  every repo change
  every service change
  every memory write
  every external event
```

and let each continuation store one global cursor.

## REJECT

Reasons:

1. It creates another canonical truth authority over systems that already own their own truth.
2. It couples unrelated concurrent work inside one project.
3. It creates large amounts of irrelevant model-facing noise.
4. It requires background event ingestion/watchers for systems that currently expose query-only state.
5. It turns Soma into a universal event-sourcing platform before evidence shows that is necessary.
6. A single cursor has poor semantics when sources have different retention, version and freshness models.
7. It can make multi-project concurrency harder rather than easier.

The owner wants a useful nervous system, not an event warehouse.

---

# 4. Registered-source frontier

## Leading architecture hypothesis

A reasoning continuation explicitly names only the authoritative sources whose changes matter to its current objective.

Conceptually:

```text
Continuation
  registered source A
  registered source B
  registered source C

Capsule C1
  semantic state
  incorporated frontier manifest F1

F1
  source A token at capsule time
  source B token at capsule time
  source C token at capsule time
```

On resume:

```text
resolve current tokens for A/B/C
compare with F1
return bounded mechanical deltas
Sol reconciles
```

This keeps relevance under Sol's semantic control while comparison remains mechanical.

---

# 5. Registering a source is not monitoring it continuously

This distinction is important.

```text
registered source
!= background watcher
!= notification subscription
!= repository lock
!= polling loop
```

Core semantics:

> When Soma builds a continuation/resume projection, this source is part of the authoritative state that must be resolved and compared against the capsule's incorporated frontier.

If a source already has a durable event journal, Soma may use its watermark.

If a source only offers a live snapshot, Soma may refresh it at query/resume time.

Automatic continuous monitoring or wake-up remains optional future transport/observer infrastructure, not a prerequisite for this architecture.

---

# 6. A source needs a source-specific observation token, not one universal integer

Different authorities expose change differently.

Examples:

```text
Task
  state_version
  latest_task_event_id
  compact observation hash

Run
  state_version
  latest_run_event_id
  compact run-state hash

ProjectScope
  scope_generation
  binding/attempt/quarantine state hash
  relevant updated_at/version where authoritative

Knowledge record
  revision
  content hash
  lifecycle/effective-status identity

Git repository
  HEAD
  bounded index/worktree state hash
  no guaranteed historical watermark by default

External journal
  journal-native event/cursor sequence

Service query
  bounded current-state hash
  possibly no historical watermark
```

Trying to force all of these into `version: int` would either lose information or create fake precision.

---

# 7. ObservationTokenV1 candidate

Conceptual only:

```text
ObservationTokenV1
  source_kind
  source_id
  authority_ref
  scope_identity?

  snapshot_hash

  change_watermark?
    kind
    value

  observation_class
    durable_journal
    versioned_snapshot
    live_snapshot
    snapshot_only

  observed_at

  retrieval_ref?
  history_retrieval_ref?
```

## Important hashing rule

`observed_at` must not itself enter the semantic `snapshot_hash`.

Otherwise merely refreshing an unchanged source would appear as a meaningful state change.

---

# 8. Snapshot hash and change watermark solve different problems

## Snapshot hash

Answers:

> Is the current bounded authoritative state different from what the capsule incorporated?

## Change watermark

Answers:

> Did this source record relevant changes after the capsule, even if the current state later returned to an equivalent snapshot?

Example:

```text
baseline state = healthy
service -> failed -> recovered -> healthy
resume current state = healthy
```

Snapshot-only comparison says unchanged.

A durable event watermark says history advanced.

Depending on the objective, that transient failure may be crucial evidence.

## Architecture rule

Where an existing authority exposes a trustworthy monotonic event/version watermark, use it.

Where it does not, do **not** fabricate one.

Expose the observation limitation honestly.

---

# 9. Source freshness classes

A model-facing source contract should make its epistemic strength visible.

## `durable_journal`

- current snapshot available;
- monotonic durable history/cursor available;
- transient changes can usually be detected;
- history gap can be reported explicitly.

Examples: canonical Task events, Run events, domain journals where retention guarantees hold.

## `versioned_snapshot`

- authoritative current state;
- version/generation changes monotonically enough to reveal updates;
- may not expose every intermediate event.

Examples: some Task/Knowledge/ProjectScope projections.

## `live_snapshot`

- current state refreshed on demand;
- stable identity/hash available;
- no guarantee that transient intermediate states were observed.

Example: Git repository worktree status queried only on resume.

## `snapshot_only`

- only best-effort current observation available;
- change-history claim must be weak.

Some external services may initially fall here.

This is better than presenting every source as equally observable.

---

# 10. Task source should be a composite controller observation

Iteration 10/re-audit already discovered that hashing only Task columns can miss ProjectScope/recovery facts.

Iteration 13 refines that into a source adapter concept.

For a registered canonical Task, `TaskObservationSourceV1` can mechanically combine:

```text
task identity
Task state / phase / state_version
checkpoint/result/evidence references
recovery state/reason
backend bounded status
latest Task event ID
relevant ProjectScope binding/attempt/generation/quarantine projection
```

The canonical authorities remain TaskStore/RunStore/ProjectScope. The source adapter merely creates one bounded model-facing token/projection.

## Benefit

A continuation need not separately register ProjectScope for every Task merely to preserve containment truth; the Task source can include its required scope projection.

---

# 11. Run source is separate only when direct Run truth matters

Many normal durable actions should be observed through their canonical Task.

Registering both Task and Run by default may duplicate noise.

Use direct Run source when:

- the Run exists without canonical Task compatibility context;
- low-level process/event history itself is relevant;
- a diagnostic investigation intentionally tracks process state beneath Task projection.

Current RunStore already has durable event IDs/cursors and explicit cursor-gap detection, making it a strong `durable_journal` source.

---

# 12. ProjectScope is authority, not a reasoning source by default

ProjectScope should always be enforced where applicable.

That does not mean every continuation should independently monitor all ProjectScope rows.

Preferred:

- Task source includes the Task's exact scope projection;
- direct resource/project source can be registered only when project lifecycle/resource binding itself is part of the reasoning objective.

This keeps containment mandatory without flooding the frontier with internal bookkeeping.

---

# 13. Repository observation is inherently weaker without a journal

Current Soma can query live Git repository state.

A bounded repository observation might include:

```text
repo identity
branch
HEAD
index/worktree status fingerprint
relevant path fingerprints where explicitly requested
```

This is useful but normally a `live_snapshot`, not a complete mutation history.

Example limitation:

```text
Capsule sees clean repo at HEAD H
another thread edits file
then reverts it
resume sees clean repo at HEAD H
```

A live snapshot cannot prove the transient edit happened.

## Architecture decision

Do not add a repository-wide watcher/event journal just to make this theoretical case observable.

If transient mutation history is important, it should usually already exist as:

- a managed repo patch/apply Task/Run;
- Git commit/reflog evidence;
- explicit execution evidence;
- optional future repository observer.

Core continuation should truthfully label repo source as live/current-state observation.

---

# 14. Knowledge source should track revision/lifecycle, not fuzzy retrieval results

Current canonical Knowledge records have:

- stable record identity;
- `revision`;
- content hash;
- lifecycle/supersession semantics.

A continuation may register a specific Knowledge record or durable decision as an evidence/constraint source.

Do **not** register "semantic search query X" as a canonical source token because fuzzy retrieval ranking can change for unrelated reasons and is not a stable truth identity.

Correct:

```text
source = knowledge record K
baseline revision/hash/effective status
```

Not:

```text
source = whatever top-5 memory search currently returns
```

---

# 15. External services need adapter-specific honesty

Some service APIs expose version IDs, ETags, generations or durable journal cursors.

Others expose only current state.

The observation-source adapter should preserve that distinction.

Never infer:

```text
current value unchanged
=> nothing happened since last capsule
```

unless the source's change watermark actually supports that claim.

---

# 16. Owner input is not just another polled source

A new owner message arrives directly in the active Chat context and has immediate semantic priority.

It should not require registration in Soma's observation frontier to matter.

If an owner instruction needs to survive future fresh-context resumption, Sol should incorporate it into the next semantic capsule and/or promote durable preferences/decisions into canonical memory as appropriate.

---

# 17. Control effects and evidence dependencies must be distinct

A registered source may have one of several reasoning roles.

Candidate roles:

```text
control_effect
  effect initiated/owned by this continuation
  cancellation/interaction authority follows canonical Task rules

evidence_dependency
  read-only source whose changes matter
  may be shared by many continuations

constraint_source
  durable authority whose current status constrains reasoning

resource_context
  current world/resource state relevant to decisions
```

## Critical rule

```text
source registration != control ownership
```

A continuation that reads another Task's result or a repository state does not gain cancellation or mutation authority over it.

This preserves one-control-owner semantics for effectful Tasks while allowing many readers.

---

# 18. Source registration must preserve ProjectScope isolation

For scoped sources:

- register exact project/resource identity;
- resolve through canonical ProjectScope checks;
- reject/quarantine mismatched generation or cross-project access according to existing authority;
- never let a continuation ID become a capability bypass.

A source token should include enough scope identity to detect that a logically named resource was rebound/recreated under another generation.

Reasoning reads remain lock-free; scope validation is identity/authority validation, not repository mutation ownership.

---

# 19. FrontierManifest candidate

Rather than storing an independent per-Task `last_consumed_observation_hash`, a semantic capsule can reference a content-addressed manifest of exactly what external evidence basis Sol incorporated.

Conceptually:

```text
FrontierManifestV1
  continuation_id
  capsule_id
  captured_at

  sources[]
    source_kind
    source_id
    role
    authority_ref
    scope_identity?
    snapshot_hash
    change_watermark?
    observation_class
    retrieval_ref?
```

The manifest is immutable and belongs to the capsule's provenance.

---

# 20. Major simplification: semantic incorporation should be anchored by capsule, not delivery acknowledgement

The earlier design proposed:

```text
continuation query returns observation
 -> Sol acknowledges observation hash
 -> store last_consumed_observation_hash
```

Iteration 13 identifies a conceptual flaw:

```text
delivered to model != semantically incorporated into durable reasoning state
```

A tool result may be delivered while:

- Sol has not yet interpreted it;
- Sol is interrupted mid-reasoning;
- the Chat response fails;
- Sol sees it but has not made a durable semantic update;
- several observations need to be integrated together.

## Better durable boundary

A **new Sol-authored resumption capsule** is the positive assertion:

> Sol has incorporated evidence frontier F into this explicit semantic state.

Therefore the latest capsule's `FrontierManifest` can serve as the durable incorporation boundary.

---

# 21. This may remove `ack_observations` from the core architecture

Provisional simplification:

```text
OLD
  controller_continuation_tasks.last_consumed_observation_hash
  ack_observations command

CANDIDATE NEW
  latest capsule -> incorporated_frontier_ref/hash
```

Then:

```text
new evidence
=
current registered-source tokens
compared with
latest capsule frontier manifest
```

No independent durable acknowledgement is required merely because data was returned.

## Advantages

1. Stronger semantics: "incorporated" has an explicit Sol-authored semantic artifact behind it.
2. Fewer state machines/commands.
3. No false assumption that delivery equals cognition.
4. Capsule and evidence basis remain inseparable provenance.
5. Fresh-context resumption naturally knows what prior Sol had already incorporated.

## Trade-off

Until another capsule is written, a repeated continuation query may continue reporting the same changes.

That is acceptable for correctness. The live Chat context can remember it already saw them. If repeated delivery later proves annoying, a non-authoritative/ephemeral delivery cursor can optimize UX without becoming semantic truth.

Do not add such optimization before evidence demands it.

---

# 22. Capsule creation becomes an evidence-incorporation commit

A useful conceptual transaction is now:

```text
Sol has current semantic interpretation S
and has incorporated registered source frontier F

submit capsule S + exact source tokens F

Soma transaction:
  validate continuation/version
  re-resolve or validate supplied source tokens
  fail stale if relevant source changed before commit
  persist capsule + frontier manifest atomically/logically
  advance continuation version
```

If Sol simultaneously launches a long-running effect:

```text
same short ownership transaction also reserves Task/effect identity
then external effect launches after commit
```

This gives capsule claims a precise evidence basis.

---

# 23. Stale-safe capsule commit

Suppose Sol queries repository R and Task T, reasons, then tries to checkpoint.

Between query and commit, T changes.

Soma should not silently bind the new semantic capsule to a frontier Sol did not see.

Candidate contract:

- Sol submits the exact observation tokens/frontier hash it reasoned from.
- Soma recomputes/re-resolves current registered source tokens inside/around a short validation boundary.
- If a source changed, reject the capsule as stale or require explicit acknowledgement of the newer token.

The exact transaction strategy depends on source type because remote/live sources cannot be held under SQLite transaction.

## Important implementation boundary for later

Do **not** hold a SQLite transaction while refreshing external sources.

Possible future pattern:

```text
resolve source tokens outside transaction
compute frontier hash
BEGIN short transaction
  validate continuation CAS
  validate durable local source versions that can be checked atomically
  persist capsule/frontier
COMMIT
```

Remote source freshness must be represented honestly; no distributed transaction is implied.

---

# 24. Source comparison outcomes should be mechanical

Candidate change classifications:

```text
unchanged
snapshot_changed
history_advanced
snapshot_changed_and_history_advanced
source_missing
source_identity_changed
scope_invalid
source_unavailable
history_gap
freshness_unknown
```

Soma should not emit semantic labels such as:

```text
"this proves hypothesis X"
"retry is recommended"
"continue to stage 3"
```

That remains Sol's reasoning.

---

# 25. Model-facing delta projection

A fresh resume bundle should not dump raw source events by default.

Candidate bounded projection:

```text
changed_sources[]
  source_kind
  source_id
  role
  change_class
  prior_token_ref/hash
  current_token
  compact_current_projection
  history_available
  history_gap
  retrieval_ref
  history_retrieval_ref?
```

The projection should contain only mechanically derived fields from the authoritative source adapter.

Sol can selectively fetch full evidence.

---

# 26. Event history should be retrieval, not default context

Current Task and Run stores already support bounded event retrieval.

That is valuable when:

- state changed unexpectedly;
- transient history matters;
- recovery occurred;
- Sol needs chronology.

But a normal resume bundle should usually say:

```text
Task T current state = completed
Task event watermark advanced 17 -> 24
history retrieval available
```

rather than injecting all seven events automatically.

This matches Soma's compact-projection philosophy and interface research showing that tool organization affects agent efficiency.

---

# 27. History gaps are observations, not silent failure

RunStore already detects cursor gaps.

A registered source whose baseline history token is no longer retrievable should expose:

```text
history_gap = true
```

This means:

> Current state is known, but Soma cannot prove/reconstruct every change since the capsule frontier.

Sol can then decide whether current state is sufficient or further verification is needed.

Do not fabricate "unchanged" when evidence retention is incomplete.

---

# 28. Dynamic observation and future watchers

AOI research demonstrates value from observing changes between actions in truly dynamic environments.

Soma core does not need to implement continuous observation for every source now.

Future optional observer adapters could:

- watch a registered volatile source;
- append bounded durable events to a source-specific journal;
- enable a stronger `durable_journal` token for that source;
- optionally feed PulseSender/browser notification transports.

But observer infrastructure remains separable from:

- Sol cognition;
- continuation semantics;
- source registration;
- manual owner wake-up.

This prevents wake-up/observer UX from blocking the core architecture.

---

# 29. Registered-source set should itself be Sol-directed

Soma may mechanically auto-register sources that are inseparable from an effect Sol just created, e.g. its canonical Task observation.

Beyond that, source relevance is semantic.

Sol should be able to say, conceptually:

```text
this repository state matters
this service status matters
this knowledge decision is an active constraint
this external journal matters
```

Soma should not automatically register every source in the project based on heuristics.

This is another place where a local model/classifier would recreate semantic routing drift.

---

# 30. Source set evolution

As reasoning changes, sources can become irrelevant or new sources can matter.

Candidate rules:

- registering/unregistering source is a versioned continuation mutation;
- active `control_effect` Task should remain represented until terminal/contained or ownership is explicitly transferred/resolved;
- read-only evidence sources may be dropped when Sol decides they no longer matter;
- removing a source does not delete its authoritative evidence;
- capsule frontier records the exact source set that semantic state incorporated at that moment.

Older capsules therefore remain interpretable even after current registration changes.

---

# 31. Source identity must be stable and opaque

Avoid mutable human labels as the only identity.

Examples:

- Task -> `task_id`;
- Run -> `run_id`;
- Knowledge -> `knowledge_id`;
- Project resource -> `resource_id` + generation where relevant;
- repository -> canonical repo binding/resource identity, not just path text;
- external journal -> journal/provider-native durable identity.

Display labels may be added separately.

---

# 32. Repository source should not lock the repository

Resolving current repository status/HEAD for reasoning is a read.

It must not acquire/retain the repository mutation operation lock merely because the source is registered.

Concrete side-effecting repository operations retain existing lock semantics.

This preserves the multi-project reasoning invariant.

---

# 33. Source resolution costs should remain bounded

A continuation with hundreds of registered sources could become expensive.

Do not solve this prematurely with semantic pruning.

Mechanical controls can include later:

- source-count budget;
- compact projection budget;
- lazy detail retrieval;
- source grouping where an existing authority already offers one bounded aggregate;
- explicit truncation/has_more;
- parallel independent read resolution where safe.

Sol decides which sources matter; Soma enforces mechanical budgets.

---

# 34. Parallel source resolution is appropriate

Registered source reads are often independent.

The Codex research from Iteration 11 supports batching/parallelizing independent evidence reads.

A continuation query could mechanically resolve independent registered sources concurrently, subject to source-specific safety/rate limits.

This is execution efficiency, not semantic subagent reasoning.

No repository mutation lock is acquired for these reads.

---

# 35. Failure to resolve one source should not erase the rest

A robust resume projection should allow:

```text
source A = resolved changed
source B = unavailable
source C = resolved unchanged
source D = history gap
```

rather than failing the whole continuation query.

Sol can reason about partial observability explicitly.

However scope/authority violations should remain hard errors for the affected source and must not leak cross-project data.

---

# 36. Evidence frontier is not long-term memory

The frontier answers:

> What external authoritative state had prior Sol incorporated into this capsule?

It is operational provenance.

It should not be retrieved as general semantic memory for unrelated future objectives.

Capsule/frontier archival and canonical knowledge remain distinct lifecycles.

---

# 37. Effect results can outlive continuation closure

Closing an objective continuation should not delete canonical Task/Run/evidence.

The frontier/capsule simply stops being the active reasoning-resumption anchor.

Durable execution evidence remains retrievable under its canonical authority.

This preserves one authority per concern.

---

# 38. Pressure tests

## Scenario A - Task completes while Sol absent

Capsule frontier contains Task token at running/event 10.

Current source is completed/event 14.

Resume:

```text
snapshot_changed + history_advanced
```

Sol retrieves result/evidence and reasons.

PASS.

## Scenario B - Task enters and leaves recovery before resume

Current Task eventually completes normally but Task event watermark advanced across recovery events.

Resume can still report history advanced even if current snapshot looks healthy.

PASS if event retention remains available; otherwise explicit history gap.

## Scenario C - repository changed by another thread

Registered repo live snapshot differs from capsule baseline.

Resume reports current repo changed.

No control ownership inferred.

PASS.

## Scenario D - repo changed and reverted between checks

No repository event journal; current snapshot matches baseline.

Core must **not** claim no transient change occurred. It can only say current snapshot matches baseline under `live_snapshot` observation class.

PASS by epistemic honesty, not by impossible reconstruction.

## Scenario E - knowledge decision superseded

Registered Knowledge source revision/effective status changes.

Resume surfaces mechanically.

PASS.

## Scenario F - unrelated project changes

Not registered; no noise enters this continuation.

PASS.

## Scenario G - same evidence delivered twice without new capsule

Resume/query may repeat it because semantic incorporation has not been durably asserted.

Correctness preserved.

PASS.

## Scenario H - Sol integrates evidence and checkpoints

New capsule is submitted with current frontier F2.

Future resume compares against F2, not delivery history.

PASS.

## Scenario I - source changes during capsule commit

Local durable token mismatch causes stale rejection.

Remote/live source race remains bounded by stated freshness semantics; no distributed transaction claim.

PASS if contract is explicit.

## Scenario J - source history has been pruned

Current state resolves; baseline cursor cannot be replayed.

Resume says `history_gap` rather than unchanged.

PASS.

---

# 39. Candidate architecture after Iteration 13

The active-objective continuity picture is now:

```text
                     SOL / CHATGPT
              adaptive reasoning trajectory
                         |
          interprets evidence / decides actions
                         |
                         v
             ReasoningResumptionCapsule
          explicit Sol-authored semantic state
                         |
             incorporated frontier F
                         |
                         v
               FrontierManifest
       exact registered source tokens as-of F
                         |
         +---------------+----------------+
         |               |                |
      Task source      repo source     knowledge/source/etc
     canonical truth   live truth       canonical truth
         |               |                |
         +---------------+----------------+
                         |
                current resolution
                         |
              mechanical deltas since F
                         |
                         v
                     SOL reasons
```

There is no Task-loop scheduler in this diagram.

---

# 40. Implication for the previous three-table proposal

Iteration 13 now strongly questions two earlier pieces:

## Earlier `last_consumed_observation_hash`

Likely unnecessary as the semantic durability boundary if capsule frontier replaces it.

## Earlier `ack_observations`

Likely unnecessary in core because delivery != semantic incorporation.

The architecture may instead need:

```text
continuation identity/lifecycle
latest capsule ref/hash
registered source set
frontier manifest per capsule
control/evidence links
idempotent command journal
```

Exact schema still must wait for Soma-specific convergence.

---

# 41. What Iteration 13 rejects

1. Task-only observation universe.
2. Global project event stream/cursor as default architecture.
3. Background watcher requirement for every source.
4. Pretending all sources have monotonic event histories.
5. Treating current snapshot equality as proof no transient change occurred.
6. Fuzzy memory-search results as stable source identity.
7. Source registration conferring mutation/control authority.
8. Raw event streams injected by default into Sol context.
9. Semantic summarizer deciding which source changes matter.
10. Durable `ack_observations` merely because a response was delivered.
11. Repository mutation locks for registered-source reads.
12. Distributed transaction claims across remote sources.

---

# 42. Iteration 13 provisional verdict

**The best-supported observation architecture is a Sol-directed registered-source frontier anchored to each Sol-authored semantic resumption capsule.**

The key semantic distinction is:

```text
evidence delivered
!= evidence incorporated

new capsule with frontier F
= explicit durable claim that Sol's checkpoint incorporates F
```

This substantially simplifies the earlier continuation design and gives a cleaner authority model.

The model-facing resume packet should expose compact current source projections and mechanical deltas after the capsule frontier, with deeper evidence available by reference.

No global event bus or new semantic observer model is required.

---

# 43. Next research iteration

Proceed to:

**Iteration 14 - Soma-Specific Architecture Convergence and Minimal Kernel Design**

This iteration must map Iterations 11-13 onto current Soma and answer:

1. What new persistent authorities are actually required?
2. Can capsule payloads use an existing artifact mechanism safely, or is a dedicated small store cleaner?
3. Can frontier manifests be immutable artifacts rather than mutable tables?
4. Which existing gateways/source adapters can produce ObservationTokenV1 without changing their canonical truth?
5. What exactly remains of `controller_continuations`, Task associations and command journal?
6. Can `ack_observations` and per-Task consumed hashes be removed entirely?
7. What is the smallest public surface for normal Chat/Sol?
8. How does same-thread fast path avoid unnecessary ceremony?
9. How is persist-capsule + reserve-effect made crash-safe without forking TaskManager?
10. What existing Agent/Worker/Workflow/Supervisor components should be reused, bypassed or left compatibility-only?
11. What tests prove fresh-context semantic resumption actually works?
12. What should supersede Iteration 10 as the final architecture authority?

No implementation plan should be produced until that convergence iteration completes and is re-audited against the owner requirements.
