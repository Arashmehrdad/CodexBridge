# Iteration 16 - Final Synthesis: Sol Agent Interface and Semantic Continuation Architecture

Date: 2026-08-15
Status: FINAL RESEARCH SYNTHESIS - implementation planning may follow only on owner approval
Track: Sol-centric agentic reasoning architecture
Supersedes for implementation authority: Iteration 10 and its earlier three-table ControllerContinuation hypothesis
Historical iterations remain preserved as research evidence and are not rewritten.

---

# Executive conclusion

The research began with a correction to an Agent/Worker architecture that had accidentally moved semantic reasoning away from Sol and into subordinate reasoning providers. It then discovered that the first replacement model was still too narrow because it described agentic reasoning as a fixed `reason -> act -> observe -> reason` cycle and made canonical Task too central.

After Iterations 11-15, the best-supported architecture is different and simpler at the semantic level:

> **Sol/ChatGPT already owns the adaptive reasoning trajectory. Soma should not implement a reasoning algorithm. Soma should become a high-quality agent-computer interface plus a small semantic continuation kernel that preserves exact external truth and enough explicit handoff state for Sol to re-enter the same reasoning objective after interruption or fresh-context return.**

The target system is:

```text
                         USER / OWNER
                              |
                              v
                        SOL / CHATGPT
                 adaptive reasoning trajectory

        interpret / investigate / plan / revise / validate / decide
                 |             |              |
                 +------ zero / one / many capability calls ------+
                                      |
                                      v
                         SOMA AGENT INTERFACE

             precise tools / capability discovery / bounded views
             durable effects / evidence / recovery / uncertainty
             repository + service + machine + knowledge access
             semantic continuation / fresh-context re-entry
                                      |
                 +--------------------+--------------------+
                 |                    |                    |
            Tasks / Runs         repos / services      Knowledge
            effect truth          world truth          durable facts
```

The reasoning trajectory is **not** stored as workflow state.

Soma never decides:

```text
next semantic step
next Task
next stage
whether a hypothesis is true
whether to retry with another approach
whether to delegate to a specialist
whether the overall objective is complete
```

Those decisions belong to Sol/Work/owner according to context.

---

# 1. What "reasoning loop" means after research

The phrase **reasoning loop** refers to Sol's model-driven adaptive trajectory, not to a fixed persisted sequence.

It may include any ordering such as:

```text
interpret
investigate
read several sources in parallel
form/revise a hypothesis
plan or skip explicit planning
call zero/one/many tools
integrate evidence
validate
change direction
ask the owner
invoke a bounded specialist
reason further without any external action
conclude
```

One user turn may contain multiple reasoning/model episodes and multiple tool calls. One reasoning episode may emit several independent tool calls. A world observation may arrive without being caused by a Sol action.

Therefore Soma must not encode:

```text
REASONING -> ACTION -> OBSERVATION -> REASONING
```

as durable semantic state.

---

# 2. Why production agent runtimes support this conclusion

## Codex

Current Codex guidance and implementation show:

- proactive context gathering;
- planning when useful;
- parallel independent reads/tool calls;
- repeated model sampling inside one logical turn;
- test/validate/refine behavior;
- context compaction and continuation across long work;
- a model-authored handoff summary when context is compacted.

The runner/harness may have a simple continuation condition, but cognition is not a fixed one-action ReAct state machine.

## OpenAI Agents SDK

The SDK explicitly distinguishes LLM orchestration, where the model plans/reasons/decides, from code orchestration for deterministic flows. It can serialize exact `RunState` because it owns the runner.

## LangGraph / Microsoft Workflows

Graph runtimes persist explicit next nodes/supersteps/checkpoints because they own execution topology.

That is useful for deterministic workflows but is the wrong abstraction for Soma's normal-Chat reasoning continuity.

## General interface research

SWE-agent and later agent-interface research show that tool/observation interface design materially changes agent effectiveness even without changing the underlying model.

This supports investing in Soma's interface quality rather than constructing another semantic planner.

---

# 3. Exact runtime resumption is not available to Soma normal Chat

Soma does not own ChatGPT's hidden model runner.

It cannot serialize or restore:

- private chain-of-thought;
- hidden model state;
- exact sampling continuation;
- KV/cache state;
- arbitrary internal ChatGPT runtime objects.

Therefore Soma must not claim exact runner resume.

The correct contract is **semantic resumption**:

> A returned/fresh Sol receives an exact controller contract, the latest explicit Sol handoff, current authoritative external state, and the changes/uncertainty since that handoff, so it can reconstruct the situation and continue intelligently.

---

# 4. Four continuity layers

Keep these separate:

```text
A. live model/conversation continuity
   owned by ChatGPT/Work while context exists

B. active-objective semantic continuation
   new Soma continuation kernel

C. external execution/world continuity
   Tasks, Runs, repositories, services, resources, journals

D. long-term memory/knowledge
   accepted durable decisions, facts, preferences, lessons
```

The new architecture primarily adds B and a clean projection joining B with C/D when Sol resumes.

Do not turn temporary reasoning handoff into long-term memory.

---

# 5. Soma's architectural role: agent interface / nervous system

Soma's strongest value is to make the external world easy for Sol to perceive and manipulate correctly.

That means:

- precise tool contracts;
- capability discovery;
- exact effect identity;
- durable execution where needed;
- idempotency where source authority supports it;
- recovery and outcome uncertainty;
- process/resource ownership;
- ProjectScope containment;
- bounded current-state observations;
- event/history retrieval by reference;
- evidence/provenance;
- parallel-friendly read interfaces;
- semantic continuation checkpoints;
- fresh-context resume projection.

Soma is not a second brain.

---

# 6. Fast path remains first-class

Most work should look exactly as it does today:

```text
Sol -> existing Soma tool -> result -> Sol
```

No continuation is required for:

- simple synchronous actions;
- ordinary reads;
- short deterministic tool sequences;
- every file read;
- every Task transition;
- every internal reasoning episode.

The continuation kernel is **optional durability scaffolding** activated only when losing current semantic state would matter.

---

# 7. When a continuation is useful

Strong candidates:

1. an objective already spans multiple Chat turns or fresh-context risk;
2. a long-running external effect may outlive the current Chat context;
3. the owner explicitly pauses/hands off;
4. significant semantic state would be costly to reconstruct;
5. multiple durable effects/world sources need to be reconciled later;
6. owner explicitly wants cross-surface/fresh-Chat continuation.

This keeps the feature helpful rather than bureaucratic.

---

# 8. Minimal semantic continuation kernel

The research converges on four small persistent concerns in the existing Soma SQLite authority:

```text
controller_continuations
continuation_capsules
continuation_sources
continuation_commands
```

This is not a workflow graph.

---

# 9. `controller_continuations`

Role: durable identity, lifecycle, discovery and CAS root for one coherent reasoning objective.

Conceptual fields:

```text
continuation_id
owner/controller namespace metadata
safe label
state = open | completed | cancelled
state_version
latest_capsule_id
created_at
updated_at
closed_at
```

Deliberately absent:

- model/provider identity;
- reasoning phase;
- next step;
- next Task;
- scheduler state;
- plan graph;
- repository mutation lock;
- required Chat conversation ID;
- Company/Mission identity.

---

# 10. `continuation_capsules`

Role: immutable explicit handoff authored by Sol/owner at meaningful continuity boundaries.

A capsule is an **engineering handoff**, not private reasoning.

It must have three separately identified partitions:

```text
A. controller_contract
B. prior_sol_handoff
C. incorporated_frontier
```

Each partition is canonicalized/hashed independently or equivalently protected so authority cannot blur.

---

# 11. Capsule controller contract

This is the high-authority part.

It preserves exact or content-addressed material for:

```text
owner objective/request
explicit hard constraints
explicit exclusions
explicit authorization boundaries
owner changes to those terms
```

This material must not drift through repeated semantic summarization.

If the owner changes the contract, the update must be explicit and the new capsule must preserve the exact updated contract/ref.

Derived Sol completion criteria or provisional interpretations do not silently become owner requirements.

---

# 12. Capsule Sol handoff

Non-authoritative operational state useful to a future Sol.

Conceptual fields:

```text
situation_summary
current_interpretation
explicit_decisions[]
concise decision basis / evidence refs[]
rejected_or_superseded_paths_worth_preserving[]
operational_success_criteria[]
unresolved_questions[]
working_plan_summary?          # optional, non-executable
pending_effect_intents[]
resume_focus?                  # advisory only
```

This handoff may be revised after new evidence.

It is not canonical world truth.

---

# 13. Capsule must not contain chain-of-thought

Forbidden as a design requirement:

```text
private reasoning trace
scratchpad
internal token-by-token deliberation
hidden chain-of-thought
full transcript
```

The capsule should be suitable to hand to another competent engineer/agent or show to the owner.

Store conclusions, explicit decisions, operational context and evidence references - not private deliberation.

---

# 14. Capsule incorporated frontier

The frontier says:

> These exact registered source observations formed the external evidence basis that prior Sol had incorporated when it authored this handoff.

The frontier is immutable provenance tied to the capsule.

It is not a mutable acknowledgement cursor.

---

# 15. `continuation_sources`

Role: current set of authoritative external sources/effects relevant to the reasoning objective.

Conceptual fields:

```text
continuation_id
source_kind
source_id
role
scope_identity
origin_intent_id?
status = active | retired
registered_at
retired_at
safe metadata
```

A source is not automatically a Task.

---

# 16. Source roles

At minimum conceptually:

```text
control_effect
  effect initiated/controlled for this objective

evidence_dependency
  read-only evidence shared freely

constraint_source
  durable authority whose current state constrains reasoning

resource_context
  repository/service/world state relevant to decisions
```

Registration never grants authority the underlying source does not already provide.

---

# 17. Task is not the universal effect wrapper

Canonical Task remains important, but many existing Soma actions already have canonical durable Run authority.

Examples include current direct durable action families such as Cloudflare/SSH/Docker/run_start and related operations.

Do not force them through Task merely for continuation tracking.

Correct approach:

```text
Task-based effect -> register Task source
Run-based effect  -> register Run source
repo/world evidence -> register appropriate read-only source
```

The continuation kernel is **effect-authority neutral**.

---

# 18. One control owner, many evidence readers

For an effect whose cancellation/input/retry could be semantically conflicting:

```text
at most one active continuation may register it as control_effect
```

Other continuations may reference it as read-only evidence.

This higher-level relation does not override canonical Task/Run authority.

---

# 19. Initial source adapters

A minimal v1 should likely start with source adapters that are already strongly supported by Soma:

1. canonical Task;
2. durable Run;
3. repository current-state snapshot;
4. exact canonical Knowledge record.

Later adapters may cover service/provider/domain journals when real workflows justify them.

Do not build a universal observer framework first.

---

# 20. Observation token model

Different authorities expose different change semantics.

Use source-specific tokens containing conceptually:

```text
source kind/id
adapter/schema version
authority/scope identity
snapshot hash
optional change watermark
observation class
observed_at
retrieval refs
```

Observation classes should distinguish:

```text
durable_journal
versioned_snapshot
live_snapshot
snapshot_only
```

This prevents false claims that all sources can reveal transient history.

---

# 21. Snapshot and history are different

Snapshot hash answers:

```text
is current bounded state different from the capsule baseline?
```

Watermark answers:

```text
did durable history advance after the baseline, possibly through transient states?
```

Use existing canonical watermarks where they exist.

Do not fabricate history for live-snapshot sources.

---

# 22. Existing Soma sources already provide strong tokens

## Task

Can combine:

- state/phase/state_version;
- result/evidence/checkpoint/recovery refs;
- latest Task event ID;
- bounded backend state;
- relevant ProjectScope projection.

## Run

Has:

- state_version;
- durable status/result publication;
- per-Run events and latest event ID;
- cursor-gap detection.

## ProjectScope

Provides:

- project/resource identity;
- scope generation;
- binding/attempt/quarantine state.

Usually included through source-specific validation/composite Task observation rather than registered globally.

## Knowledge

Exact record identity/revision/content hash/lifecycle.

## Repository

Current branch/HEAD/worktree fingerprint as live snapshot unless stronger journal evidence exists.

---

# 23. No global observation event bus

Do not create one giant stream containing every project change.

It would:

- duplicate canonical authorities;
- create noise;
- couple unrelated concurrent work;
- require watchers everywhere;
- create a new retention/cursor system;
- tempt semantic filtering.

The registered-source frontier is smaller and Sol-directed.

---

# 24. Source registration is not monitoring

Core registration means:

> Resolve/compare this source when a continuation resume projection is deliberately requested.

It does not imply:

- continuous polling;
- automatic wake-up;
- repository lock ownership;
- notification subscription.

Future observers/PulseSender/browser notification mechanisms can strengthen delivery without changing reasoning authority.

---

# 25. Evidence delivery is not semantic incorporation

This is a key correction from Iteration 10.

```text
Soma returned evidence O
```

does not prove:

```text
Sol semantically integrated O before interruption
```

Therefore remove the core concept of durable `ack_observations` / `last_consumed_observation_hash`.

A **new Sol-authored capsule with frontier F** is the durable claim that Sol's handoff state incorporates F.

---

# 26. Repeated resume before checkpoint is allowed to repeat deltas

Until another capsule is written, the same source changes may appear again.

That is correct.

If same-thread UX later needs suppression, use ephemeral/client-local delivery state, not a new semantic authority.

---

# 27. `continuation_commands`

Role: idempotent mutation journal/CAS audit only.

Conceptual:

```text
command_id
continuation_id
operation
controller_request_id
request_hash
expected_state_version
resulting_state_version
status
result_ref
created_at
completed_at
```

It is not a general event-sourcing authority for source/world state.

---

# 28. Why four tables are minimal enough

Removing any one causes worse coupling:

- no continuation row -> poor lifecycle/discovery/CAS;
- no capsule table -> mutable handoff loses provenance/frontier lineage;
- no source table -> returned effect identities force unnecessary semantic checkpoints;
- no command table -> idempotency/replay scattered across every mutation.

Frontier remains embedded/immutable with capsule rather than becoming a fifth mutable authority.

---

# 29. Storage location

For v1, prefer the existing `runs/soma.sqlite3` durable authority with additive migration.

Reasons:

- existing Task/Run/ProjectScope persistence already lives there;
- WAL and transaction patterns already exist;
- capsule/frontier payloads are bounded metadata, not large transcripts;
- one transaction avoids filesystem/DB split-brain;
- local Task/source stale validation can be stronger.

Large evidence remains referenced externally.

---

# 30. Pending effect intent

When an effect may outlive Chat, Sol may checkpoint before launch with a structured intent:

```text
intent_id
semantic purpose
tool/effect class
safe normalized request fingerprint/reference
expected effect identity class
```

This records prior Sol intent for crash reconciliation.

It is **never executable work**.

---

# 31. Pending intent is not a queue

Forbidden transition:

```text
unbound pending intent -> automatically execute
```

If an intent remains unbound after interruption, fresh Sol must reconcile whether an effect actually launched before deciding whether to issue anything again.

Soma only reports:

```text
bound
unbound
ambiguous
superseded
```

mechanically.

---

# 32. Persist intent before risky/long effect

Useful durability boundary:

```text
Sol decides effect E is appropriate
 -> checkpoint exact contract + handoff + frontier + pending intent I
 -> call existing Soma action gateway
 -> receive Task/Run identity E
 -> register E as source bound to I
```

This adds durability without changing the action gateway's semantic authority.

---

# 33. Launch-to-link gap is handled conservatively

If Chat disappears after launch but before source registration:

- capsule proves prior intent;
- exact effect may or may not exist;
- no automatic retry;
- fresh Sol inspects recent Runs/provider/world evidence;
- if found, registers effect;
- if not provable, uncertainty remains explicit.

This is safer than forcing every existing tool through a new wrapper in v1.

---

# 34. Stronger future effect integration remains possible

Where existing authority exposes safe inert identity reservation/idempotency, a later optimization can atomically:

```text
checkpoint
reserve effect identity
register source
commit
launch effect
```

Current Task reservation seams and some `reserved_run_id` internals demonstrate feasibility for selected paths.

But this is not required for all gateways in the first architecture.

---

# 35. Public interface recommendation

Use dedicated semantics:

```text
continuation_query
continuation_action
```

rather than hiding the new authority inside Task, Workflow, Supervisor or Knowledge.

This intentionally adds public gateway surface and should receive normal inventory/schema/CF1 review when implementation is authorized.

Avoid `loop_*` names because `loop` belongs to Sol's reasoning trajectory.

---

# 36. Candidate public query semantics

Conceptually:

```text
capabilities
list
status
resume
capsule_history
sources
```

`status` is cheap/local.

`resume` deliberately refreshes current registered-source observations and builds the re-entry bundle.

---

# 37. Candidate public action semantics

Conceptually:

```text
open            # creates continuation + first capsule
checkpoint      # immutable new capsule/frontier
register_source
retire_source
complete
cancel
```

Exact request schemas belong in implementation planning.

No action operation automatically launches pending intents.

---

# 38. `open` should create first capsule atomically

Do not permit an empty half-initialized continuation waiting for later semantic content.

Opening durable continuity means creating:

- identity;
- exact controller contract;
- initial Sol handoff;
- initial frontier/source context as applicable.

---

# 39. Resume bundle authority structure

A fresh-context response should clearly separate:

```text
controller_contract
  exact/high-authority objective and hard constraints

prior_sol_handoff
  non-authoritative operational semantic state as-of capsule time/frontier

current_sources
  authoritative bounded projections per underlying source

changes_since_handoff
  mechanical source-token comparisons

uncertainty
  missing/gapped/unavailable/unbound/ambiguous facts

retrieval
  exact references for deeper evidence
```

No `recommended_next_action` generated by Soma.

---

# 40. Resume is reconciliation

Fresh Sol should conceptually:

1. read exact contract;
2. read prior Sol handoff;
3. inspect current authoritative source states/deltas;
4. reconcile stale prior interpretation with current truth;
5. retrieve deeper evidence as needed;
6. choose its own reasoning/action path.

The prior `resume_focus` or working plan is advisory only.

---

# 41. Capsule checkpoint is the semantic incorporation boundary

When Sol creates a new capsule, it asserts:

> This explicit handoff state incorporates frontier F.

For local durable sources, Soma should stale-check submitted token/version where transactionally feasible.

If source changed before commit, reject stale rather than silently claim Sol incorporated unseen evidence.

For remote/live sources, record honest observation time/class/token; no distributed transaction claim.

---

# 42. Capsule authority and drift protection

Each capsule should carry separately hashed/identified:

```text
controller contract
Sol handoff
frontier
```

Checkpoint guidance must not ask Sol to merely summarize the previous capsule.

A fresh handoff should be built from:

```text
exact contract
+ current live context
+ prior handoff where useful
+ canonical durable Knowledge refs
+ new evidence since prior frontier
```

Stable accepted facts/decisions should migrate into canonical Knowledge rather than be endlessly re-paraphrased.

---

# 43. Long-term Knowledge remains separate

Use Knowledge for:

- accepted durable architectural/product decisions;
- stable facts;
- owner preferences;
- reusable lessons.

Do not store every temporary diagnosis/provisional plan as canonical memory.

Promotion from handoff -> Knowledge is explicit semantic action by Sol/owner.

---

# 44. ProjectScope and authorization

Continuation is not a capability bypass.

Every registered source must be resolved under the same canonical scope/authorization required by its normal source query.

For scoped sources persist/revalidate exact identity such as:

```text
project_id
resource_id
scope_generation
```

where applicable.

A continuation may span legitimate multiple resources/projects, so do not force one repository/project ownership field onto the continuation itself.

Continuation discovery has its own trusted owner/controller namespace; source access remains independently authorized.

---

# 45. Multi-project concurrency

Hard invariants:

- Sol reasoning acquires no repository mutation lock;
- continuation reads/checkpoints/source registration acquire no repository mutation lock;
- several continuations can inspect the same repo concurrently;
- unrelated projects remain concurrent;
- short SQLite CAS transactions are allowed;
- never hold DB transaction while Sol reasons, remote source is queried, effect launches, or owner input is awaited;
- concrete side effects keep existing resource lock semantics.

---

# 46. Source-resolution concurrency

Independent read-only registered sources may be resolved in parallel subject to adapter/rate-limit constraints.

This is I/O parallelism, not subagent reasoning.

One failed source should not erase all other observations; return partial observability explicitly unless access/security semantics require a hard affected-source failure.

---

# 47. History gaps are first-class uncertainty

If a baseline durable event cursor is no longer retrievable:

```text
current state may still be known
history_gap = true
```

Do not fabricate "nothing changed".

Sol decides whether current state is sufficient or more verification is necessary.

---

# 48. Repository observation remains honest

Without a dedicated journal, repository status is a live snapshot.

Current equality with baseline does not prove no transient edit occurred.

Do not add a repo watcher just to eliminate this theoretical limitation in v1.

Managed mutations already have stronger evidence through Runs/patches/commits where applicable.

---

# 49. Same-thread behavior

When the active Chat thread already holds rich context:

- do not inject full capsule on every call;
- do not checkpoint every observation;
- continue using ordinary Soma tools naturally;
- checkpoint only before genuine continuity risk or explicit handoff.

The feature should mostly disappear during normal active work.

---

# 50. Fresh-Chat behavior

Owner can open/wake a new normal Chat and say:

```text
continue
```

Sol:

1. lists/statuses open continuations;
2. selects obvious relevant one or asks only if genuinely ambiguous;
3. calls `continuation_query.resume`;
4. receives exact contract + prior handoff + current source deltas/uncertainty;
5. retrieves deeper evidence if necessary;
6. continues reasoning.

This is the key product acceptance scenario.

---

# 51. Discovery metadata

List should expose bounded safe hints:

```text
continuation_id
safe label
state
last checkpoint time
short safe objective hint/ref
active-effect/source counts
```

Do not use a local semantic model to choose the continuation.

Deterministic recency/source affinity can help, with Sol/owner resolving real ambiguity.

---

# 52. Work architecture

ChatGPT Work already owns its own multi-step model runner/context/subagent orchestration.

Default:

```text
Work/Sol -> existing Soma tools directly
```

No Soma continuation driver is required.

Optional continuation use only for:

- explicit cross-surface handoff;
- owner-requested durable checkpoint;
- external work intended to be resumed later by normal Chat.

No mode detector is required for correctness.

---

# 53. Specialist architecture

Optional specialist providers/workers remain subordinate capabilities.

Good uses may include explicitly chosen bounded independent work.

They are not:

- default reasoning authority;
- automatic failure fallback;
- default checkpoint summarizer;
- required for continuation.

Codex remains explicit owner authorization only.

---

# 54. Company architecture

Company remains separate and frozen unless explicitly reopened.

Its recent provider-neutral WorkPackage repair is compatible with this architecture but not part of normal-Chat continuation.

Do not use:

```text
Mission
PlanRevision
WorkPackage
```

for ordinary reasoning handoff state.

A Company accepted PlanRevision is organizational commitment; a ContinuationCapsule working plan is provisional model-authored handoff scaffolding.

---

# 55. Workflow/Supervisor/LocalAgent

New normal-Chat reasoning continuity should bypass their semantic routing roles.

- Workflow may remain a narrow deterministic-sequence compatibility tool.
- Supervisor remains compatibility/history, not cognition.
- LocalAgent semantic classifier/router should not sit between Sol and Soma's agent interface.

Do not remove public compatibility surfaces in the first continuation implementation package unless separately authorized.

---

# 56. Reasoning-provider compatibility

Historical `TaskKind.REASONING`, `BackendKind.SOMA_REASONING`, evidence durability and provider ambiguity mechanics can remain as optional specialist infrastructure.

Do not enable them merely to implement continuation.

The new architecture must pass with reasoning provider disabled.

---

# 57. No automatic wake-up dependency

Owner manually waking Chat remains a valid v1 contract.

PulseSender/browser extension/notification adapters can later improve delivery.

They do not change semantic authority and must not become model reasoning engines.

---

# 58. Crash/failure semantics

## Before first capsule

No Soma semantic-resumption guarantee exists. Soma cannot persist semantic state never externalized.

## After capsule, before effect launch

Handoff exists; pending intent may be unbound. Future Sol decides what to do.

## During/after launch before effect link

Outcome uncertain until reconciled. Never auto-retry.

## After effect source link, before next capsule

Registered source is new relative to old frontier; resume exposes it.

## During capsule commit

SQLite atomicity yields previous or new capsule, never partial semantic state.

## During resume

Read/projection only; no semantic incorporation mutation. Safe to retry.

---

# 59. Closure semantics

`complete` / `cancel` are explicit semantic lifecycle commands.

Never infer completion from all effects being terminal.

Active controlled effects require explicit safe disposition policy; do not silently cancel or detach them.

Canonical Task/Run/evidence outlive continuation closure.

---

# 60. What is explicitly removed from the target design

Do not implement from earlier research:

```text
ControllerLoop
controller_continuation_tasks
last_consumed_observation_hash
ack_observations
Task-only observation hash
Task-as-universal effect wrapper
fixed reason/act/observe persisted states
semantic next-step recommendation
semantic scheduler
reasoning worker as default brain
```

These were research stepping stones, not final architecture.

---

# 61. Minimal source adapter contract

Conceptually:

```text
ObservationSourceAdapter
  kind/version
  validate_registration(...)
  resolve(...) -> SourceObservation
  retrieval_metadata(...)
```

`SourceObservation` is a bounded mechanical projection containing:

```text
ObservationToken
compact current state
history/freshness status
retrieval refs
```

Adapters do not persist independent source lifecycle state.

---

# 62. Capsule and source budgets

V1 should enforce bounded payloads.

Exact numbers belong in planning/testing, but principles are frozen:

- no MB-scale transcript capsules;
- no unbounded source registry;
- no raw log/event dumps by default;
- explicit `has_more` / retrieval refs;
- semantic capsule fields should fail safely if they cannot be persisted completely rather than being silently meaning-truncated.

---

# 63. Security / secret handling

Continuation payloads must follow Soma's existing protected-evidence discipline.

- avoid secret values in capsule text;
- pending intent stores safe fingerprints/refs rather than arbitrary secret-bearing request payloads;
- use protected references for sensitive evidence;
- apply mechanical sensitivity/redaction checks at write boundary;
- do not promote secrets into Knowledge.

---

# 64. Versioning

Version:

- capsule schema;
- source adapter/token schema;
- public continuation contract.

Never silently compare old/new token hashes under different normalizations.

If comparison is impossible, expose `token_version_uncomparable` or equivalent uncertainty and refresh current state.

Historical capsules remain immutable.

---

# 65. Implementation sequence recommendation

This is still **research guidance**, not authorization.

A future reviewed implementation plan should likely sequence:

## Phase 0 - supersession/acceptance gate

- adopt Iteration 16 as architecture authority;
- explicitly supersede Iteration 10 implementation recommendation;
- freeze authority/terminology invariants;
- inventory exact public/schema changes;
- protect concurrent repo work.

## Phase 1 - internal persistence only

- additive four-table schema;
- models/store;
- capsule partition hashing;
- idempotent command journal;
- no public tools yet.

## Phase 2 - source adapter proof

- Task adapter;
- Run adapter;
- repository adapter;
- Knowledge adapter;
- ProjectScope/security revalidation;
- bounded token/version semantics.

## Phase 3 - internal resume projection

- exact contract/prior handoff/current sources/deltas/uncertainty/retrieval;
- parallel read resolution where safe;
- no semantic recommendation.

## Phase 4 - public continuation gateways

- `continuation_query` / `continuation_action`;
- public inventory/CF1/schema updates;
- compatibility surfaces unchanged.

## Phase 5 - pending-intent/effect linking

- safe structured intent;
- direct Run and Task source registration;
- conservative unbound reconciliation;
- stronger atomic reservation only where existing authority supports it.

## Phase 6 - normal-Chat guidance

Teach Sol:

- fast path by default;
- checkpoint only at continuity risk;
- exact contract vs handoff distinction;
- resume reconciliation before following old focus;
- no automatic provider delegation.

## Phase 7 - real fresh-Chat acceptance

Use interrupted owner workflows, not synthetic unit tests only.

## Phase 8 - later optimizations

Only after evidence:

- continuation-aware correlation fields in selected action gateways;
- optional observer/wake-up integrations;
- ephemeral delivery cursor if repeated deltas are annoying;
- more source adapters;
- retention/archive tuning.

---

# 66. Mandatory mechanical acceptance tests

## Persistence

- additive migration/restart;
- capsule immutable/hash integrity;
- exact contract partition integrity;
- handoff partition integrity;
- frontier integrity;
- CAS/idempotency/conflicts.

## Security/scope

- cross-project source registration rejected;
- scope generation/quarantine revalidated;
- continuation ID never bypasses source authority;
- discovery metadata non-sensitive.

## Sources

- Task token + event watermark;
- Run token + event watermark;
- repo live snapshot;
- Knowledge revision/lifecycle;
- adapter version mismatch;
- history gap;
- unavailable source;
- newly registered source not in frontier.

## Control ownership

- one active control owner per effect;
- many evidence readers;
- retirement does not delete evidence.

## Pending intent

- unbound survives restart;
- never auto-executes;
- ambiguous launch never auto-retries;
- later Run/Task link resolves correlation.

## Concurrency

- several continuations read/checkpoint concurrently;
- no repo mutation lock for source reads/metadata;
- no DB transaction across remote wait/reasoning/effect launch.

## Independence

- reasoning provider disabled;
- Company disabled/frozen;
- Supervisor/Workflow not used;
- direct existing tools still work without continuation.

---

# 67. Mandatory semantic acceptance test

The architecture exists to solve a model/user continuity problem, so mechanical tests alone are insufficient.

Required real workflow:

```text
1. normal Chat pursues a non-trivial objective
2. Sol reaches a continuity-risk boundary and checkpoints
3. one or more relevant external effects/world states evolve
4. original Chat context is deliberately abandoned
5. genuinely fresh Chat receives only the normal user cue (e.g. "continue")
6. Sol discovers/resumes the correct continuation
7. Sol respects exact owner contract
8. Sol recovers prior important decisions/rejected paths from handoff
9. Sol reconciles current source changes
10. Sol does not blindly repeat uncertain effects
11. Sol chooses a sensible next reasoning/action path without owner reconstructing the project history
```

This is the real acceptance criterion.

---

# 68. Terminology freeze

## Sol reasoning trajectory / reasoning loop

The adaptive cognition owned by Sol. Not persisted as a state machine.

## Agent interface

Soma's capability/observation/effect/evidence surface used by Sol.

## Continuation

Durable identity/lifecycle for one coherent active reasoning objective that may need re-entry.

## ContinuationCapsule / Sol handoff capsule

Bounded explicit operational handoff; exact controller contract + non-authoritative Sol state + evidence frontier. Not chain-of-thought.

## Source

Canonical external effect/world/evidence authority registered as relevant.

## Frontier

Exact source observations prior Sol says its handoff incorporated.

## Pending effect intent

Prior Sol's pre-effect semantic intent used only for crash reconciliation. Never queued work.

## Task

Canonical Task-plane effect identity where applicable, not the reasoning loop.

## Run

Canonical durable execution identity where applicable, equally trackable as an effect source.

## Workflow

Explicit deterministic/semi-deterministic sequence capability, separate from reasoning continuity.

## Company

Optional/frozen organizational mission/commitment layer, separate from normal Chat continuation.

---

# 69. Things future implementers must not infer

Do not infer:

- continuation means autonomous scheduler;
- capsule means model scratchpad;
- source list means dependency graph;
- pending intent means work queue;
- terminal effects mean objective complete;
- Task must wrap every action;
- Work needs Soma reasoning loop;
- provider reasoning is required;
- a registered repo must be locked;
- delivery means semantic incorporation;
- current snapshot equality proves no transient change;
- exact owner objective may be paraphrased on every checkpoint.

---

# 70. Relationship to the original owner intent

The corrected architecture matches the original direction much more closely than the Agent/Worker drift did.

The owner wanted:

```text
ChatGPT/Sol with its memory and reasoning
+ Soma's durable tools, machine/service access, recovery and continuity
```

not:

```text
ChatGPT dispatches reasoning to another worker that becomes the thinker
```

The resulting architecture is essentially:

> **Give Sol a durable nervous system and a reliable handoff back into its own reasoning trajectory.**

That is narrower, more reusable and less cognitively invasive than building another agent framework underneath Sol.

---

# 71. Final research verdict

**RESEARCH COMPLETE FOR A NEW IMPLEMENTATION-PLANNING PHASE.**

Iteration 16 supersedes Iteration 10 for implementation authority.

The architecture is now supported by:

- current Codex behavior/prompt/runtime evidence;
- OpenAI Agents SDK runner/resumption/context separation;
- Anthropic/Gemini/OpenHands comparative agent patterns;
- graph/workflow runtime counterexamples showing where explicit next-node state belongs;
- primary agent-interface/observation research;
- current Soma Task/Run/ProjectScope/Knowledge/public-gateway contracts;
- adversarial crash/security/drift/UX pressure testing;
- explicit owner requirements.

No further broad architecture research is required before drafting an implementation plan **unless the owner wants another focused research question**.

Implementation itself is not authorized by this document.

The next step, only on owner approval, should be a bounded implementation-planning lane based on this synthesis, with no Codex invocation, no Company reopening, no reasoning-provider activation and no unrelated legacy cleanup.
