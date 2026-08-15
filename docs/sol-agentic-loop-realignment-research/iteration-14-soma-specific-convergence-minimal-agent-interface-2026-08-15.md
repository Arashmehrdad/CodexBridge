# Iteration 14 - Soma-Specific Convergence and Minimal Agent Interface

Date: 2026-08-15
Status: RESEARCH CONVERGENCE - implementation still not authorized
Track: Sol-centric agentic reasoning architecture
Repository state inspected during iteration: branch `lane/memory-integration-foundation-1`, HEAD `a9fe3ae32f5b26a8b8a7e0764431df2f8f62cda2` (`Correct Company WorkPackage route neutrality`)

## Purpose

Iterations 11-13 reopened the architecture after discovering that the earlier `reason -> act -> observe -> reason` framing was too narrow.

They established three stronger ideas:

1. Sol owns an adaptive reasoning trajectory; Soma must not encode a cognitive state machine.
2. Robust fresh-context continuation likely needs a bounded **Sol-authored semantic resumption capsule**.
3. New evidence should be computed from a **registered authoritative source frontier anchored to that capsule**, not from Task-only observation acknowledgements.

This iteration maps those ideas onto the Soma codebase and asks:

> What is the smallest new durable kernel and public interface Soma actually needs to support Sol's reasoning continuity without duplicating existing Task/Run/ProjectScope/Knowledge authorities or forcing ordinary Soma actions through a new workflow?

---

# 1. Current Soma after Company repair

## REPOSITORY FACT

At this iteration's inspection point, the concurrent Company repair lane had committed:

```text
a9fe3ae Correct Company WorkPackage route neutrality
```

The tracked worktree was clean. The Sol research documents and canonical memory contract remained untracked owner/research artifacts.

This is relevant only as a moving-target check; Company remains a separate architecture and is not reopened by this iteration.

---

# 2. The central convergence: Soma should expose an agent interface, not implement an agent algorithm

The architecture now reads most cleanly as:

```text
                       SOL / CHATGPT
                 adaptive reasoning trajectory

       interpret / investigate / plan / revise / validate / decide
                         |
               zero / one / many calls
                         |
                         v
                 SOMA AGENT INTERFACE

        existing precise tools + durable effect authorities
        compact world/evidence observations
        recovery / uncertainty / provenance
        semantic continuation capsule + source frontier
                         |
          +--------------+---------------+
          |              |               |
       Task/Run      repos/services    Knowledge
       effect truth    world truth      durable facts
```

The **reasoning loop/trajectory belongs entirely above Soma**.

Soma provides:

- capabilities;
- durable external state;
- model-legible observations;
- exact uncertainty;
- semantic resumption support.

It does not prescribe the model's reasoning order.

---

# 3. Canonical Task is important but not the universal action wrapper

Earlier Sol-loop research drifted toward making canonical Task the mandatory child/effect of a continuation.

Repository reality argues against that.

## REPOSITORY FACT

Many first-class public Soma action gateways already launch durable Runs directly through `JobManager`, including families such as:

- Cloudflare actions;
- SSH actions/deployments;
- Docker actions;
- generic `run_start` operations;
- managed repository apply operations through their own durable run/transaction path.

For example, `cloudflare_action` delegates to `JobManager.start_cloudflare_action()`, which creates/launches a durable `cloudflare_action` Run directly.

Canonical Task remains a first-class higher-level effect identity for Task-plane operations, but it is not currently the universal wrapper around every Soma capability.

## INFERENCE - IMPORTANT

Do **not** force all Sol actions through canonical Task merely so the continuation layer can track them.

That would:

- add ceremony to otherwise good tools;
- fork/mirror existing public contracts;
- require broad migration across unrelated gateway families;
- confuse reasoning continuity with execution normalization;
- risk creating a new orchestration bottleneck.

The continuation architecture should be **effect-authority neutral**.

---

# 4. Effect-authority-neutral source model

A reasoning continuation may care about:

```text
canonical Task
canonical durable Run
repository current state
canonical Knowledge record
Project/resource state
future service/journal source adapter
```

The registered-source model from Iteration 13 naturally supports this.

## Roles

```text
control_effect
  Task or Run initiated for this reasoning objective

evidence_dependency
  read-only canonical evidence from any authority

constraint_source
  durable decision/config/state that constrains the reasoning

resource_context
  repository/service/world state to reconcile on resume
```

No source registration changes the underlying source's authority.

---

# 5. Most direct durable Soma actions can be tracked as Run sources

This substantially reduces the need for continuation-specific integration into every gateway.

Existing mutation tool:

```text
Sol -> cloudflare_action
     -> returns durable run_id
```

Continuation can subsequently register:

```text
source_kind = run
source_id = returned run_id
role = control_effect
```

Same pattern applies to many direct durable Run-producing Soma tools.

Task-plane action:

```text
Sol -> task_action
     -> returns task_id / backend identity
```

Continuation registers canonical Task source as the higher-level effect authority.

This preserves existing public UX.

---

# 6. The unavoidable launch-to-link crash gap

If Sol does:

```text
launch existing action gateway
 -> action starts
 -> Chat disappears before continuation links returned run/task ID
```

then the effect exists but is not yet associated with the continuation.

The earlier Task-only design tried to eliminate this by atomically reserving Task + continuation membership before launch.

That cannot be applied generically to every current gateway without invasive refactoring.

## Convergence principle

Do not distort the whole tool architecture to eliminate a small recoverable gap in v1.

Instead preserve **intent before effect**, then reconcile conservatively if the effect identity was not linked.

---

# 7. Pending effect intent inside the semantic capsule

Before a long/effectful action that may outlive Chat, Sol can checkpoint a structured pending effect intent as part of the resumption capsule.

Conceptual:

```text
pending_effect_intent
  intent_id
  tool_name
  normalized_request_hash
  bounded request/reference material needed for reconciliation
  expected_effect_kind = task | run | direct
  semantic purpose
```

This says:

> Prior Sol had decided this effect should be attempted after this checkpoint.

It does **not** say the effect was definitely launched.

After the action gateway returns, Sol links the returned Task/Run source with `origin_intent_id`.

---

# 8. Crash recovery for an unbound pending effect intent

Fresh Sol may see:

```text
capsule contains pending intent I
no registered effect source bound to I
```

Correct interpretation:

```text
outcome/launch status requires reconciliation
```

Not:

```text
retry automatically
```

Sol may inspect:

- recent Runs;
- tool/provider state;
- repository state;
- idempotency evidence where available;
- exact external state.

If existence cannot be proven, uncertainty remains explicit.

This applies Soma's existing persist-before-send/outcome-unknown philosophy to semantic continuity without requiring every gateway to support a new transaction protocol immediately.

---

# 9. Where atomic pre-effect binding is already feasible, keep the stronger path

Canonical Task already has a reservation seam (`reserve_task_in_connection`) and backends can reserve inert identities.

Some JobManager paths internally support `reserved_run_id`.

Therefore future effect types may support:

```text
checkpoint + reserve effect identity + register source
COMMIT
launch effect
```

when the existing authority exposes a safe reservation seam.

But v1 continuation architecture should define this as an **optional stronger integration**, not require it for every public capability.

No second execution launcher is created.

---

# 10. Current Run authority is already a strong observation source

## REPOSITORY FACT

`runs` contains `state_version`, status, phase, result publication identity/hash and other durable lifecycle fields.

RunStore also has per-Run event history with earliest/latest event IDs and explicit cursor-gap detection.

This makes Run a good `durable_journal` observation source:

```text
snapshot token
  state_version + bounded run projection hash

history watermark
  latest_event_id
```

No new Run observation table is needed.

---

# 11. Current Task authority is also a strong observation source

## REPOSITORY FACT

Task has CAS `state_version`, checkpoints, result/evidence refs, recovery state and event IDs.

Re-audit already showed its controller-facing observation must include relevant ProjectScope truth.

A Task source adapter can therefore produce a composite token without changing canonical Task semantics.

No copied Task observation rows are required.

---

# 12. Repository live-state source should remain snapshot-class

Current `repo_query` can resolve branch/HEAD/worktree state without mutation.

Use that as current world context where useful.

Do not build a hidden repository watcher merely to strengthen the token.

The source adapter should honestly describe its class as live/current-state snapshot unless/until a durable change journal exists.

---

# 13. Knowledge source should remain exact-record based

Current canonical Knowledge has stable IDs, revisions, content hashes and lifecycle/supersession semantics.

Continuation can reference exact Knowledge records as constraints/evidence.

Fuzzy knowledge search remains a retrieval tool, not observation identity.

---

# 14. Existing long-term Knowledge is not the resumption capsule store

Current `KnowledgeInput` is flexible enough technically to store a checkpoint body, but semantic fit matters more than schema convenience.

The resumption capsule contains transient operational semantics:

- current interpretation;
- provisional plan;
- unresolved questions;
- pending effect intents;
- resume focus.

Those should not automatically enter canonical long-term project memory.

Therefore a dedicated continuation/capsule authority remains justified.

---

# 15. Existing ExternalCoder handoff is not the new capsule authority

Existing handoff code proves:

- bounded typed packets are practical;
- atomic JSON/text writers exist;
- inert handoffs can be stored without launching an agent.

But it also includes ExternalCoder policy/routing concepts, memory retrieval and optional local-model summarization.

Core Sol continuation should not inherit those dependencies.

At most, low-level atomic writer/hash patterns may be reused.

---

# 16. Storage convergence: keep the first version in the existing SQLite authority

Iteration 12 considered filesystem/content-addressed artifacts for capsules.

Soma-specific evidence favors a simpler first design.

## Existing facts

- Task and Run durability already live in the existing `runs/soma.sqlite3` authority.
- SQLite uses WAL.
- Task schema uses additive migrations.
- caller-owned transactions already coordinate higher-level relationships with Task reservation.
- capsules/frontier manifests should be bounded, not megabyte transcripts.

## Leading convergence recommendation

Store bounded immutable capsule JSON and frontier JSON **inside the same SQLite database** initially.

Advantages:

- one transactional authority;
- no SQLite/filesystem split-brain problem;
- easy hash validation;
- easy immutable history;
- future atomic Task integration remains possible;
- fewer new subsystems.

This is simpler than inventing a general artifact store now.

Large evidence remains referenced externally; capsule/frontier payloads stay bounded.

---

# 17. Minimal persistent authority candidate: four tables

This supersedes the earlier three-table Task-centric hypothesis for research purposes.

## 17.1 `controller_continuations`

Only identity/lifecycle/discovery metadata.

Conceptual:

```text
continuation_id PRIMARY KEY
label
state = open | completed | cancelled
state_version
latest_capsule_id
created_at
updated_at
closed_at
```

Deliberately absent:

- model/provider;
- plan state;
- Task state;
- repository lock;
- Chat conversation ID;
- current reasoning phase;
- recommended next action.

## 17.2 `continuation_capsules`

Immutable Sol-authored semantic checkpoints.

Conceptual:

```text
capsule_id PRIMARY KEY
continuation_id
capsule_version
predecessor_capsule_id
semantic_json
semantic_hash
frontier_json
frontier_hash
checkpoint_reason
created_at
```

`semantic_json` includes the current objective contract rather than requiring a separate mutable objective table.

## 17.3 `continuation_sources`

Current registered relevant source set.

Conceptual:

```text
continuation_id
source_kind
source_id
role
scope_identity_json
origin_intent_id
status = active | retired
registered_at
retired_at
metadata_json

UNIQUE(continuation_id, source_kind, source_id, role)
```

A partial uniqueness rule should enforce at most one active `control_effect` owner where that source kind's semantics require exclusive control ownership.

Evidence references can be shared.

## 17.4 `continuation_commands`

Immutable/idempotent mutation journal.

Conceptual:

```text
command_id PRIMARY KEY
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

Purpose is mechanical replay/CAS/audit only.

---

# 18. Why no separate objective table

The active objective/constraints/done criteria are semantic state.

Requiring an initial capsule when opening a durable continuation gives one versioned place to preserve:

```text
objective
constraints
done criteria
current interpretation
```

If owner/Sol changes the objective materially, a new capsule captures the new semantic state.

Older capsules preserve prior objective context for audit without another revision table.

Continuation row itself only needs discovery/lifecycle identity.

---

# 19. Why no `controller_continuation_tasks` table

`continuation_sources` replaces it with a generic relation.

Task is one source kind among several.

This avoids hard-coding:

```text
continuation == set of Tasks
```

and better matches real Soma capability usage.

---

# 20. Why no copied observation table

Current authoritative sources already own their state/history.

Capsule `frontier_json` records only source tokens/hashes/watermarks as provenance.

Current resume projection resolves sources live.

No copied Task/Run/service result bodies are needed.

---

# 21. Why no durable `ack_observations`

Iteration 13's distinction holds:

```text
delivery != semantic incorporation
```

A new capsule is the durable semantic incorporation boundary.

Therefore the minimum core does not need:

- `last_consumed_observation_hash`;
- per-Task consumed hash state;
- `ack_observations` command.

If repeated same-thread delivery later proves annoying, use ephemeral/client-supplied pagination/delivery tokens rather than redefining semantic truth.

---

# 22. Source adapter layer is code, not new truth

Introduce an internal protocol conceptually like:

```text
ObservationSourceAdapter
  resolve(registration) -> SourceObservation
  retrieval(registration) -> retrieval metadata
```

`SourceObservation` contains:

```text
ObservationTokenV1
compact mechanical projection
retrieval refs
history retrieval refs
```

Adapters read canonical authorities; they do not persist competing state.

Candidate initial adapters:

1. Task
2. Run
3. repository
4. Knowledge record

Potential later adapters:

- Cloudflare resource current state;
- SSH/service current state;
- trading/domain journal;
- other connected resources with stable identity.

Do not build every adapter in the first patch unless a real workflow needs it.

---

# 23. Continuation open operation

Conceptual public mutation:

```text
continuation_action.open
```

Input includes:

- idempotent controller request ID;
- bounded label;
- initial semantic capsule;
- initial registered sources if any;
- exact frontier tokens for sources Sol already incorporated.

Output:

- continuation ID/version;
- capsule ID/hash;
- registered-source identities;
- compact retrieval instructions.

No Task/Run launch occurs simply because continuation opened.

---

# 24. Checkpoint operation

Conceptual:

```text
continuation_action.checkpoint
```

Input:

- continuation ID;
- expected continuation version;
- controller request ID/hash;
- new Sol-authored semantic capsule;
- exact evidence frontier Sol claims to have incorporated;
- optional pending effect intent descriptors.

Behavior:

- validate shape/budgets;
- validate local durable source tokens stale-safely where possible;
- persist immutable capsule/frontier;
- update latest capsule pointer/version;
- no external effect launch.

---

# 25. Register-source operation

Conceptual:

```text
continuation_action.register_source
```

Use after:

- an existing action gateway returns Task/Run identity;
- Sol decides a repository/Knowledge/resource source should be tracked;
- an effect intent becomes bound to a canonical effect identity.

Registration does not claim prior capsule incorporated the source.

Until next checkpoint, it is naturally **new/unincorporated** evidence relative to the latest capsule frontier.

This is exactly what we want.

---

# 26. Retire-source operation

A Sol/controller decision may retire a source when it no longer matters.

Retirement:

- does not delete canonical evidence;
- does not transfer control automatically;
- must preserve active effect safety;
- is versioned/idempotent.

An active unresolved `control_effect` should not be silently dropped merely to clean context.

Exact rules belong in implementation planning.

---

# 27. Resume/query operation

Conceptual:

```text
continuation_query.resume
```

Behavior:

1. retrieve latest capsule;
2. list active registered sources;
3. resolve independent source observations, preferably in parallel where safe;
4. compare with capsule frontier;
5. expose mechanically changed/unavailable/gapped sources;
6. include unresolved pending effect intents and bound/unbound state;
7. expose exact retrieval refs;
8. return bounded projection.

No semantic next-action recommendation.

---

# 28. Other minimal query operations

Likely:

```text
capabilities
list
status
resume
capsule_history   # explicit, bounded
sources           # explicit, bounded
```

`status` should remain cheap and may avoid refreshing expensive live sources.

`resume` is the operation that resolves current source state for reasoning re-entry.

---

# 29. Close/cancel continuation semantics

Closing a continuation means:

> Sol/owner considers this reasoning objective resolved or abandoned.

It must not automatically cancel all effects unless explicitly requested and safe.

Potential operations:

```text
complete
cancel
```

with clear policy for active control effects.

The important invariant remains:

```text
Task/Run terminality != reasoning objective complete
```

and:

```text
continuation close != delete canonical execution evidence
```

---

# 30. Public gateway topology

The old 34-gateway compatibility argument should not force bad semantics.

Because continuation is neither Task nor Knowledge nor Workflow, overloading those gateways would hide the new authority boundary.

## Leading recommendation

Add two deliberate public families when implementation is authorized:

```text
continuation_query
continuation_action
```

This would intentionally increase public inventory rather than smuggling continuation operations into `task_action`.

Any gateway-count change must receive the normal public schema/inventory/CF1 test updates.

Workflow/Supervisor remain compatibility surfaces and are not removed in the same patch.

---

# 31. Why not call public tools `loop_*`

Owner terminology is explicit:

```text
loop = Sol reasoning loop/trajectory
```

The persisted Soma component is only continuation state.

Therefore avoid:

```text
loop_query
loop_action
controller_loop
```

for the new public/persistence surface.

`continuation_*` is less likely to recreate Task-loop confusion.

---

# 32. Same-thread fast path

A major usability requirement is avoiding ceremony.

## Simple/short action

```text
Sol -> existing Soma tool -> result -> Sol
```

No continuation.

## Active Chat, several synchronous reads

Use ordinary tools. No capsule after each read.

## Objective starts to cross continuity risk

Only then:

```text
open/checkpoint continuation
```

## Long effect launched

Checkpoint pending intent first if continuity risk matters, call existing gateway, then register returned effect identity.

## Same Chat remains active

Sol can continue using ordinary tools. No need to re-read the capsule every turn.

This keeps Soma helpful rather than bureaucratic.

---

# 33. Fresh-Chat path

User opens/wakes normal Chat and says continue.

Sol:

```text
continuation_query.list/status
 -> select relevant open continuation
continuation_query.resume
 -> receive capsule + current deltas
 -> retrieve deeper evidence as needed
 -> reason
```

Then Sol may:

- do nothing but reason;
- inspect more sources;
- revise interpretation;
- ask owner;
- execute one/many actions;
- checkpoint before another continuity-risk boundary;
- complete/cancel continuation.

Soma does not choose among these.

---

# 34. Work path remains separate

ChatGPT Work already owns its long-running model runner/context and native agentic reasoning trajectory.

Default Work use:

```text
Work/Sol -> existing Soma tools directly
```

No Soma continuation driver required.

Optional use cases for `continuation_*` from Work may include:

- explicit handoff to normal Chat;
- owner-requested durable cross-surface checkpoint;
- external effect tracking that must outlive Work context.

These are interoperability cases, not duplicated cognition.

No Chat-vs-Work inference is required for correctness.

---

# 35. No specialist/provider dependency

None of the new four-table candidate requires:

- `TaskKind.REASONING`;
- `BackendKind.SOMA_REASONING`;
- Codex;
- Claude;
- Hermes reasoning;
- local model;
- worker gateway;
- FanIn.

Optional specialists remain ordinary bounded capabilities Sol may explicitly invoke.

The continuation kernel is fully usable with all reasoning providers disabled.

---

# 36. Company remains outside the architecture

Company's new route-neutral repair is good evidence that the repository is moving back toward provider-neutral effects.

But Company remains:

- frozen unless owner reopens it;
- unnecessary for normal Chat reasoning continuity;
- a higher organizational layer if ever used later.

Do not use Company Mission/Plan/WorkPackage as continuation state.

---

# 37. Workflow and Supervisor remain bypassed for new cognition

The prior compatibility result still holds.

- Workflow may remain a narrow deterministic-sequence compatibility capability.
- Supervisor remains historical compatibility and should not become Sol's cognitive driver.
- LocalAgent semantic routing should not sit between Sol and Soma tools.

The new continuation kernel is not implemented on top of any of them.

---

# 38. Locking model

Continuation operations are metadata/observation operations.

They must not acquire repository mutation operation locks for:

- open;
- checkpoint;
- register source;
- resume;
- source reads;
- capsule history;
- close metadata.

Short SQLite write transactions are allowed/required for durable CAS/idempotency.

Never hold SQLite transaction while:

- Sol reasons;
- remote/live source query runs;
- external effect launches;
- owner input is awaited.

Concrete actions keep their existing resource-lock authority.

---

# 39. Multi-project model

Continuation identity is not repository ownership.

One continuation may involve sources from multiple resources if existing authority permits them.

Several continuations may inspect the same repository simultaneously.

A shared evidence source may be referenced by several continuations.

A `control_effect` source may have stricter single-owner semantics.

ProjectScope validation remains source-specific and must not be bypassed by continuation IDs.

---

# 40. Capsule/frontier size discipline

Do not create a transcript replacement.

Candidate starting budgets for later planning/testing, not frozen values:

```text
semantic capsule JSON: bounded tens of KB, not MB
registered source count: bounded
frontier manifest JSON: bounded
resume response: existing CF1-style response budget
```

Large logs/results/evidence stay referenced.

When over budget, fail explicitly or require source pruning/retrieval strategy; do not semantically truncate arbitrary capsule fields behind Sol's back.

---

# 41. Source-resolution concurrency

Independent read-only source resolution can run concurrently.

This is mechanical I/O parallelism, not subagent reasoning.

Example:

```text
resolve Task T
resolve Run R
resolve repo state
resolve Knowledge K
```

in parallel where adapters are independent and rate limits allow.

The output is then deterministically assembled into one bounded resume projection for Sol.

---

# 42. No semantic source pruning by Soma

If too many sources are registered, Soma may report budget pressure.

It must not silently decide:

```text
"these five sources probably matter less"
```

Sol owns relevance decisions.

Mechanical truncation for display must retain `has_more`/retrieval identity and must not change registered-source truth.

---

# 43. Capsule/frontier commit and remote-source races

No system can atomically snapshot arbitrary remote services together with SQLite without distributed transaction support.

Do not pretend otherwise.

For local durable sources in the same DB, stronger stale validation may be possible.

For live/remote sources:

- resolve immediately before capsule submission;
- record observation timestamp/class/token;
- treat freshness according to adapter contract;
- on next resume, compare current observation.

This is epistemically honest and sufficient for a reasoning agent that can revalidate uncertain facts.

---

# 44. Pending intent should be structured but not executable

The capsule's pending effect intent is useful for crash reconciliation, but it must not become a queued workflow item.

Soma must not see:

```text
pending intent I
```

and automatically execute it.

It exists only so future Sol can answer:

> What was prior Sol about to do, and do I need to determine whether it actually happened?

This is semantic continuity, not scheduling.

---

# 45. Existing action idempotency remains source-specific

Some existing pathways have strong idempotency/reserved identity; others do not expose the same contract publicly.

Continuation should not fabricate uniform idempotency.

Where an effect gateway supports an idempotency key/request identity, pending intent can bind it.

Where not, fresh Sol must reconcile conservatively before retrying.

Future gateway improvements can progressively add correlation/reservation seams without blocking the initial continuation kernel.

---

# 46. Reasoning quality depends heavily on the observation interface

The interface research reinforces a practical design priority:

Spend engineering effort on:

- exact source identity;
- compact mechanical projections;
- excellent retrieval affordances;
- honest uncertainty/freshness;
- parallel-friendly reads;
- clear current-vs-history distinction;
- semantic capsule quality guidance;

rather than inventing more orchestration abstractions.

This is likely where Soma most directly makes Sol a better agent.

---

# 47. Fresh-context acceptance test is essential

Mechanical unit tests are necessary but not sufficient.

The feature's actual purpose is:

> A fresh normal Chat/Sol can continue an interrupted objective without the owner reconstructing the entire prior reasoning history.

After implementation, one acceptance lane should use real owner workflows:

1. start objective in normal Chat;
2. create capsule before a meaningful long effect;
3. let effect/state evolve;
4. open a genuinely fresh Chat;
5. say `continue`;
6. verify Sol retrieves the right continuation, understands prior decisions/constraints, reconciles new evidence, avoids rejected paths and chooses a sensible next investigation/action.

This evaluates semantic resumption without requiring access to private chain-of-thought.

---

# 48. Mechanical test matrix

Future implementation plan should include at least:

## Continuation storage

- open idempotency;
- CAS/version conflicts;
- immutable capsule history;
- capsule hash integrity;
- bounded payload rejection;
- restart reconstruction.

## Source registry

- register/retire idempotency;
- Task source resolution;
- Run source resolution;
- repo live snapshot resolution;
- Knowledge revision resolution;
- ProjectScope mismatch/quarantine;
- shared evidence source;
- single control-effect owner where enforced.

## Frontier

- snapshot change;
- event watermark advance with equal current snapshot;
- history gap;
- source unavailable;
- source identity change;
- newly registered source absent from capsule frontier;
- stale local-source capsule commit.

## Pending intent

- intent checkpointed before effect;
- effect linked after launch;
- crash/unbound intent survives restart;
- no automatic retry;
- later source binding resolves intent correlation.

## Concurrency

- multiple unrelated continuations concurrently query/checkpoint;
- no repository operation lock on reasoning/source reads;
- short SQLite transaction only;
- same-repo reads remain concurrent.

## Independence

- reasoning provider disabled;
- Company disabled/frozen;
- Supervisor/Workflow unavailable to new path;
- direct existing tools remain usable without continuation.

---

# 49. What can be deleted from the previous proposed architecture before it is ever implemented

Research-only concepts that should no longer enter the implementation plan:

```text
controller_continuation_tasks
last_consumed_observation_hash
ack_observations
Task-only observation universe
Task-as-mandatory-effect wrapper
ControllerObservation as one monolithic Task-centric hash
fixed reason/act/observe state language
```

They were useful stepping stones, but Iterations 11-14 provide a cleaner model.

Historical research docs should remain unchanged as evidence of the reasoning progression; the future final synthesis should supersede them explicitly.

---

# 50. Minimal architecture candidate after convergence

```text
                     SOL / CHATGPT
              adaptive reasoning trajectory
                         |
                         v
                  SOMA AGENT INTERFACE
       existing tools + continuation_query/action
                         |
        +----------------+----------------+
        |                                 |
  existing action/world              CONTINUATION KERNEL
     authorities                     four small tables
        |                                 |
 Tasks / Runs / repos /           continuation identity
 services / Knowledge             immutable capsules
        |                         registered sources
        |                         command journal
        |                                 |
        +---------- source adapters ------+
                         |
                 resume reconciliation
                         |
       latest Sol capsule + changes after its frontier
                         |
                         v
                    SOL reasons
```

The continuation kernel is not the reasoning loop.

It is a durable **re-entry interface** for the reasoning loop.

---

# 51. Open design questions after convergence

The core architecture is much clearer, but several details still deserve an adversarial iteration before a new final synthesis.

1. Exact capsule field schema and maximum budgets.
2. Whether semantic capsule JSON should be rigid typed fields or permit a bounded structured body plus required core fields.
3. Exact source adapter token schema/versioning.
4. Exact control-effect uniqueness semantics for direct Runs versus Tasks.
5. Pending effect intent request normalization and sensitive-data handling.
6. Source registration permissions across multi-resource objectives.
7. Whether current source set changes require checkpointing or can remain separate controller metadata.
8. How to rank/select open continuations when owner says only `continue` in a fresh Chat.
9. Whether a continuation can intentionally fork into two reasoning objectives or should require explicit new continuation IDs.
10. Closure behavior with active effects.
11. Retention/archival policy for old capsules/frontiers.
12. Public capability metadata/skill guidance that teaches Sol to checkpoint only at continuity-risk boundaries.
13. How much same-thread continuation querying is useful before it becomes unnecessary overhead.
14. Whether Work needs any explicit capability metadata saying continuation is optional/cross-surface only.

---

# 52. Iteration 14 convergence verdict

**The strongest Soma architecture is no longer a durable Task loop or even a Task-centric ControllerContinuation. It is a small semantic continuation kernel embedded beneath a high-quality, effect-authority-neutral agent interface.**

The proposed minimum new persistence is four concerns:

```text
continuation identity/lifecycle
immutable Sol-authored semantic capsules + incorporated frontier manifests
registered authoritative sources/effects
idempotent continuation command journal
```

Everything else should remain in existing authorities.

The critical authority split is:

```text
Sol
  interprets
  plans if useful
  chooses tools/effects
  integrates evidence
  decides when semantic state should be checkpointed
  decides completion

Soma
  exposes tools
  persists bounded capsules verbatim
  preserves canonical effect/world truth
  resolves registered source deltas mechanically
  exposes uncertainty/recovery/provenance
  never chooses the semantic next step
```

This architecture preserves almost all valuable infrastructure built so far while avoiding the Agent/Worker reasoning-authority mistake.

---

# 53. Recommended next research step

Do **not** yet rewrite Iteration 10 into an implementation plan.

Run one final adversarial research iteration:

**Iteration 15 - Adversarial Architecture Review and Failure-Mode Pressure Test**

It should attack this candidate from at least these angles:

- Does the capsule become hidden chain-of-thought persistence?
- Does pending intent accidentally become a workflow queue?
- Can source registration leak cross-project data/authority?
- Can stale capsules cause unsafe repeated side effects?
- Can repeated capsules drift like compaction summaries?
- Is four-table state actually minimal, or can it be reduced further?
- Are direct Run effects safely trackable without wrapping all gateways?
- What happens if Chat disappears before checkpoint, after checkpoint, during effect launch, after launch but before link, after link, during resume, or during checkpoint commit?
- Can same-thread use remain essentially as frictionless as today?
- Does Work remain completely unaffected by default?
- Does any wording still allow an implementer to turn Soma into the semantic actor?

Only after that adversarial pass should a new **Iteration 16 final synthesis** supersede Iteration 10 and authorize implementation planning.
