# Iteration 15 - Adversarial Architecture Review and Failure-Mode Pressure Test

Date: 2026-08-15
Status: RESEARCH ONLY - adversarial review; implementation not authorized
Track: Sol-centric agentic reasoning architecture
Architecture under attack: Iteration 14 semantic continuation kernel + effect-authority-neutral agent interface

## Purpose

Iteration 14 converged on a small semantic continuation kernel underneath Soma's existing tools and canonical effect/world authorities. Before accepting that architecture, this iteration deliberately tries to break it.

The questions are not "can this be implemented?" but:

- Does any part quietly turn Soma into the semantic actor again?
- Does the capsule accidentally become stored chain-of-thought?
- Does pending intent become a workflow queue?
- Can stale handoff state trigger duplicated side effects?
- Can repeated checkpoints drift away from the owner's real goal?
- Can source registration bypass ProjectScope or leak unrelated work?
- Is the proposed four-table kernel actually minimal?
- Does the design remain easy enough that Sol will use it only when useful?
- Can direct existing Run-producing tools remain first-class?
- Does Work remain unaffected by default?

This is a failure-oriented review. Findings that survive it become candidates for the new final synthesis.

---

# 1. Additional comparative evidence

## LangGraph

Current LangGraph persistence saves graph state as checkpoints at graph super-step boundaries. A checkpoint includes state values and the graph's `next` nodes/tasks. Replay resumes the graph from those explicit execution boundaries.

This works because LangGraph **owns the execution graph**.

## Microsoft Agent Framework

Current Microsoft Agent Framework explicitly distinguishes:

- Agents: model-driven agents that call tools;
- Harness: an opinionated model-driven agent for long multi-step work, including planning/todo/context compaction/memory;
- Workflows: graph-based deterministic routing with checkpointing and human-in-the-loop.

Its self-hosting guidance also separates session state from conversation-history providers.

## Temporal

Temporal is a durable workflow runtime designed to recover/replay application workflow execution across crashes and failures. That is a strong model for durable deterministic external execution, but it is not evidence that Soma should serialize Sol's semantic reasoning as workflow nodes.

## Adversarial lesson

Exact `next node` / replay semantics belong to runtimes that own the graph/runner.

Soma does not own normal Chat/Sol's model runner.

Therefore fields such as:

```text
next_stage
next_task
current_reasoning_phase
node_to_execute
```

would be architectural fabrication unless they are merely explicit prior-Sol advisory handoff text.

The continuation kernel must preserve **re-entry context**, not model execution position.

---

# 2. Attack: capsule becomes hidden chain-of-thought persistence

## Failure mode

A field named `reasoning_state`, `reasoning_trace`, or an unrestricted free-form "why" section could encourage Sol or future implementers to serialize private/internal deliberation.

That would be unnecessary, potentially huge, semantically unstable, and contrary to the intended architecture.

## Correction

Rename the semantic object conceptually from `ReasoningResumptionCapsule` toward a neutral **ContinuationCapsule / SolHandoffCapsule**.

The payload should contain only explicit operational handoff state suitable to show another competent agent/user:

```text
current situation / interpretation
explicit decisions
brief decision basis or evidence refs
important constraints
rejected paths worth not repeating
unresolved questions
optional working-plan summary
pending effect intents
resume focus
```

It must not request or store:

```text
hidden reasoning
scratchpad
chain-of-thought
internal token-by-token deliberation
```

## Acceptance invariant

> A capsule should read like a high-quality engineering handoff, not a transcript of private cognition.

PASS with terminology/schema tightening.

---

# 3. Attack: repeated capsule compaction drifts the actual user objective

## Failure mode

If each new Sol-authored capsule paraphrases the previous capsule's objective, then repeated handoff can produce:

```text
owner goal G0
 -> capsule paraphrase G1
 -> capsule paraphrase G2
 -> ...
 -> drifted goal Gn
```

This is especially dangerous because future Sol might treat the capsule as authoritative and optimize for a mutated objective.

## MATERIAL CORRECTION

The capsule must distinguish two authority partitions:

### A. exact controller/owner contract

Preserve verbatim or content-addressed exact material for:

```text
owner objective / request
explicit hard constraints
explicit exclusions / authorization boundaries
owner changes to those terms
```

This contract must **not** be silently rewritten by semantic compaction.

### B. non-authoritative Sol handoff state

Contains:

```text
current interpretation
provisional plan
current diagnosis/hypothesis
explicit decisions made within the contract
unresolved questions
resume focus
```

Sol may revise B freely after new evidence.

## Schema implication without adding a fifth table

`continuation_capsules` can contain separately hashed partitions:

```text
contract_json
contract_hash
handoff_json
handoff_hash
frontier_json
frontier_hash
```

The capsule remains one immutable record, but authority is explicit.

When the owner changes the objective/constraint contract, the new capsule must carry the exact updated contract or an exact authoritative reference to it. A mere handoff paraphrase cannot change the contract.

PASS after correction.

---

# 4. Attack: derived success criteria are mistaken for owner constraints

## Failure mode

Sol often derives useful completion criteria even when the owner did not spell them out.

If those are stored in the exact owner contract, future Sol may treat a provisional implementation judgment as an immutable user requirement.

## Correction

Separate:

```text
contract.hard_constraints / explicit owner done terms
```

from:

```text
handoff.operational_success_criteria
```

Derived criteria remain revisable model-authored state unless explicitly accepted by the owner as part of the contract.

PASS with explicit authority labels.

---

# 5. Attack: pending effect intent becomes a hidden workflow queue

## Failure mode

A stored structure like:

```text
pending_effect_intent = "run tests"
```

could tempt a worker/reconciler to automatically execute unbound intents on restart.

That would recreate Task/workflow progression under another name.

## Hard rule

A pending effect intent is **historical semantic provenance only**:

> Prior Sol had decided/was about to attempt this effect as of capsule C.

It has no executable transition.

Allowed mechanical states in resume projection:

```text
bound_to_effect
unbound
ambiguous
superseded_by_new_capsule
```

Forbidden automatic transition:

```text
unbound -> execute
```

Only active Sol/owner may decide to issue the action after reconciliation.

PASS if no background executor/reconciler consumes pending intent as work.

---

# 6. Attack: stale pending intent duplicates a side effect

## Crash window

```text
C: pending intent I persisted
external gateway launches effect E
Chat dies before E is registered
fresh Sol sees I unbound
```

Fresh Sol may be tempted to reissue the same request.

## Required behavior

Unbound pending effect intent must project as **launch outcome uncertain until reconciled** unless the underlying gateway provides a reliable idempotency/reservation identity proving otherwise.

Resume bundle should expose:

```text
intent I
expected tool/effect class
request fingerprint
no bound canonical effect identity
reconciliation refs/capabilities if available
```

Sol then checks recent Runs/provider/world state before deciding whether retry is safe.

## Future stronger integration

Where a gateway later accepts a stable controller/idempotency/correlation ID, bind `intent_id` to it so outcome reconciliation improves.

Do not require broad gateway migration for v1.

PASS conservatively, but this uncertainty must be first-class.

---

# 7. Attack: direct Run effects are second-class compared with Task

## Failure mode

If the continuation source model treats Task as the real effect and Run as legacy, normal Cloudflare/SSH/Docker/run_start/repo operations become awkward or require wrappers.

## Repository fact

Current Soma deliberately has many public action gateways whose canonical durable effect evidence is a Run.

## Rule

`source_kind=run` is a first-class control/evidence source.

Task remains first-class where Task is the higher-level authority, but the continuation kernel is not allowed to force Task creation merely for tracking.

PASS.

---

# 8. Attack: two continuations both claim control of the same effect

## Failure mode

Two open reasoning objectives register the same non-terminal Task/Run as `control_effect`, then make contradictory cancellation/input decisions.

## Correction

For source kinds that have effect-control semantics, enforce at most one active continuation control owner for the same canonical effect identity.

Conceptually:

```text
UNIQUE(source_kind, source_id)
WHERE role = 'control_effect' AND status = 'active'
```

or equivalent transactionally enforced rule.

Any number of continuations may register the same effect as read-only `evidence_dependency`.

## Important nuance

This relation does not create control authority stronger than the underlying Task/Run API. It only prevents ambiguous higher-level ownership among continuations.

PASS with constraint.

---

# 9. Attack: continuation source registration bypasses ProjectScope

## Failure mode

Caller learns/guesses `task_id` or `resource_id` from Project B while operating in Project A and registers it into a continuation. Later `resume` might expose compact state/evidence that normal scoped query would reject.

## Hard security/containment rule

Source adapters must call the **same canonical scope/authorization checks** required by the underlying public source query.

Registration must persist exact scope identity needed for later revalidation, including where applicable:

```text
project_id
resource_id
scope_generation
binding identity
```

Resume must revalidate current scope before returning source data.

A continuation ID is never an authorization capability.

Scope-invalid source outcome must be explicit and non-enumerating where existing security semantics require it.

PASS only if source adapters reuse existing authority checks rather than implementing weaker copies.

---

# 10. Attack: multi-project continuation leaks by being globally scoped

## Failure mode

One continuation legitimately spans several resources/projects, but listing/querying it could surface all associated source labels to a context authorized for only one project.

## Correction

Continuation discovery/access needs its own controller/owner authorization boundary separate from ProjectScope.

In this personal Soma deployment, the owner/controller may currently be globally authorized, but the data model must not *infer* cross-project authority from one registered source.

Future multi-user/tenant semantics should be able to partition continuations by authenticated owner/controller/workspace without schema replacement.

At minimum:

- continuation identity has controller/owner namespace metadata or derives from the trusted gateway context;
- each source independently revalidates its own scope;
- public list/resume never broadens access relative to existing tools.

No single `project_id` should be mandatory on continuation itself if legitimate cross-project objectives must remain possible.

PASS with explicit two-level authorization concept.

---

# 11. Attack: four tables are not minimal

Iteration 14 proposed:

```text
controller_continuations
continuation_capsules
continuation_sources
continuation_commands
```

Can any be removed?

## Remove `continuation_commands`?

Would require scattering idempotency/controller-request identity across open/checkpoint/source/close tables and recreating replay logic independently.

REJECT removal. One command journal is simpler and follows existing Task patterns.

## Remove `continuation_sources` and store source set only in capsule?

An effect can be launched/identified **after** the latest semantic capsule without any new semantic conclusion. Requiring a new capsule solely to attach a returned `run_id` would conflate semantic checkpointing with bookkeeping and add ceremony.

REJECT removal.

## Remove `continuation_capsules` and store latest handoff only in continuation row?

Would lose immutable semantic provenance, predecessor lineage, exact frontier basis and crash-safe historical handoff state. It would also make update-in-place corruption harder to audit.

REJECT removal.

## Remove `controller_continuations` and infer objective identity from capsules?

Would make lifecycle/discovery/current-pointer/CAS awkward and force scanning semantic records.

REJECT removal.

## Verdict

Four tables remain a plausible **minimum clean normalized authority**, not an arbitrary expansion.

PASS.

---

# 12. Attack: capsule/frontier should be separate tables

## Failure mode

Embedding `frontier_json` in capsule might make source comparison/history difficult.

## Counterargument

A frontier is the exact evidence basis of **that semantic capsule**. It is immutable provenance, not independently mutable domain state.

Separate mutable frontier rows could create another lifecycle and allow capsule semantics to detach from their evidence basis.

## Verdict

Keep frontier content inseparable from capsule record (embedded canonical JSON + hash) in v1.

If size/indexing later requires normalization, preserve immutable capsule-frontier identity.

PASS current approach.

---

# 13. Attack: repeated capsules drift even if objective contract is stable

## Failure mode

Even with exact contract, the model-authored handoff can degrade through repeated summary-of-summary checkpoints:

- rejected approach reason lost;
- constraint interpretation distorted;
- stale hypothesis retained;
- key evidence omitted.

## Mitigations

### 13.1 Full current handoff, not a patch

Each checkpoint submits a complete bounded current handoff state, not a semantic delta patch that requires reconstructing meaning from the whole lineage.

### 13.2 Do not summarize only the previous capsule

Checkpoint guidance should instruct Sol to build the current handoff from:

```text
exact contract
+ current live Chat context
+ previous handoff where useful
+ canonical durable decisions/knowledge refs
+ evidence/deltas since previous frontier
```

### 13.3 Promote stable facts/decisions out of the capsule

Once a decision/fact is accepted as durable project truth, record/reference canonical Knowledge instead of repeatedly paraphrasing it.

### 13.4 Preserve predecessor history but inject only latest by default

Older capsules remain retrievable for audit/recovery but do not bloat normal resume context.

### 13.5 Fresh-context acceptance testing

Real handoff quality must be evaluated empirically over multiple checkpoint cycles.

PASS with operational discipline; cannot be made mathematically drift-free without owning exact model context.

---

# 14. Attack: capsule is treated as canonical truth after world changes

## Failure mode

Capsule says hypothesis X / repo clean / approach A. While Sol is absent, registered sources change.

Fresh Sol might trust capsule prose over current canonical world state.

## Projection rule

Resume bundle must label partitions clearly:

```text
prior_handoff_state        non-authoritative, authored_at T
exact_controller_contract authoritative request/constraint context
current_source_state       authoritative per source adapter
changes_since_frontier     mechanically derived
```

The UI/tool schema should avoid flattening these into one undifferentiated object.

## Model guidance

Reconcile current authoritative source state **before** following `resume_focus` or provisional working plan.

PASS with explicit projection semantics.

---

# 15. Attack: objective contract itself changes while Sol absent

Owner can provide a new message in the current Chat before `resume` or may deliberately change the goal.

## Rule

Current owner input outranks prior capsule contract.

A later checkpoint records the updated exact contract under explicit controller/owner authority.

Soma must not mutate the stored contract merely because external world state changed.

PASS.

---

# 16. Attack: capsule commit races with a local source change

## Failure mode

Sol reads Task T at version 4, reasons, submits capsule claiming frontier T@4, but T reaches version 5 before capsule commit.

## Strong local contract

For durable local sources in the same SQLite authority, checkpoint commit should validate submitted source token/version against current canonical state in the same short transaction where feasible.

If changed:

```text
stale_frontier
```

and no capsule is persisted as if Sol had incorporated unseen state.

## Remote/live sources

No distributed transaction. Record exact observed token/timestamp/class; freshness remains bounded by source adapter semantics.

PASS.

---

# 17. Attack: remote source changes one millisecond after checkpoint

This cannot be eliminated without external transaction/locking support.

Correct semantics:

```text
capsule incorporated remote observation R as observed at T
```

not:

```text
remote state stayed unchanged through commit
```

Next resume resolves current source and reports differences.

PASS through epistemic honesty.

---

# 18. Attack: transient event happens and disappears between snapshots

For `durable_journal` sources, history watermark detects it.

For snapshot-only/live-snapshot sources, it may be unknowable.

## Rule

Observation class is part of the model-facing contract. Soma never upgrades a snapshot source to "no changes happened" semantics.

PASS.

---

# 19. Attack: raw event history floods model context

## Failure mode

Resume across ten Runs injects thousands of log/event records, destroying context efficiency.

## Rule

Default resume includes:

```text
compact current projection
change class
watermark movement/history gap
retrieval ref
```

Full history requires explicit retrieval by Sol.

PASS.

---

# 20. Attack: Soma semantically filters source changes

## Failure mode

A local model/heuristic decides which changed sources are "important" before Sol sees them, recreating hidden semantic routing.

## Rule

Soma may mechanically:

- bound size;
- paginate;
- group by source kind;
- sort deterministically;
- mark changed/unchanged/unavailable/history gap;

It may not semantically discard changed registered sources.

If response budget is exceeded, expose `has_more` and retrieval continuation.

PASS.

---

# 21. Attack: all registered sources are refreshed on every cheap status query

Would be expensive and could contact external systems unnecessarily.

## Correction

Separate:

```text
status
  cheap local continuation/capsule/source metadata

resume
  deliberate re-entry operation that resolves current registered-source observations
```

Optionally allow bounded source subsets later.

PASS.

---

# 22. Attack: source registration itself becomes semantic routing

## Failure mode

Soma auto-detects a large repository/project and registers dozens of things it "thinks" matter.

## Rule

Auto-registration is allowed only for **mechanically inseparable effect identity** produced by an explicit continuation-aware operation.

All broader evidence/resource relevance selection belongs to Sol/owner.

No local model/classifier decides source relevance.

PASS.

---

# 23. Attack: same-thread usage becomes slower than today's Soma

## Failure mode

Every tool call requires:

```text
checkpoint
call tool
register source
resume
checkpoint again
```

This would be a failed product even if architecturally pure.

## Hard UX rule

Continuation is **exceptional durability scaffolding**, not the default call path.

Fast path remains exactly:

```text
Sol -> existing Soma tool -> result -> Sol
```

Use continuation when:

- objective already spans interruption/fresh-context risk;
- a long effect is about to outlive context;
- user explicitly wants pause/handoff;
- significant semantic state would be costly to reconstruct.

When an open continuation exists, Sol does not need to checkpoint after every action. It checkpoints only when it wants a new durable semantic resumption point.

PASS only if skill/tool guidance preserves this.

---

# 24. Attack: open continuation itself creates cognitive ceremony

## Simplification

Opening should atomically create the first capsule. There is no useful empty continuation that later waits for semantic initialization.

Thus:

```text
open = create continuation identity + initial contract/handoff/frontier
```

This eliminates one half-initialized state.

PASS.

---

# 25. Attack: source set changes require unnecessary semantic checkpoint

Iteration 14 correctly separates source registration from capsule creation.

A new returned `run_id` can be registered without pretending Sol made a new semantic conclusion.

Because latest capsule frontier lacks the new source, it naturally appears as new/unincorporated at resume.

PASS.

---

# 26. Attack: registered effect finishes and source is retired automatically

Automatic retirement could hide result evidence before Sol incorporates it.

## Rule

Terminality does not auto-retire a control/evidence source from reasoning context.

Sol retires it only after its result no longer needs to remain in the active continuation source set, typically after a later capsule incorporates the relevant outcome.

Mechanical cleanup may be considered only after continuation closure/archival policy.

PASS.

---

# 27. Attack: completion automatically cancels active effects

## Failure mode

Sol decides objective done while diagnostic/background effect still runs. Automatic cancellation could destroy useful evidence or cause an unsafe partial external operation.

## Rule

Continuation `complete/cancel` must name active-effect disposition explicitly or refuse ambiguous closure where unresolved controlled effects exist.

Potential explicit dispositions for later planning:

```text
leave_running_and_detach_control
cancel_selected_effects
require_effects_terminal
```

Do not invent one universal default during research.

PASS conceptually; exact policy remains implementation-plan question.

---

# 28. Attack: direct Run has weak higher-level ownership semantics

A direct Run may expose cancellation but not the same parent/controller model as Task.

## Rule

Continuation `control_effect` ownership is only a higher-level anti-conflict relation. It cannot grant capabilities absent from Run/Task authority.

Cancellation/input still delegates to canonical effect API.

PASS.

---

# 29. Attack: continuation tries to normalize all effect idempotency

Current Soma gateways vary in idempotency/reservation strength.

A generic continuation layer cannot honestly make all external effects exactly-once.

## Rule

Expose effect-specific replay/correlation capability.

Pending intent can include a request fingerprint, but:

```text
fingerprint != proof of exactly-once execution
```

Where canonical effect supports idempotency, reuse it.

Where not, surface uncertainty and require semantic reconciliation before retry.

PASS.

---

# 30. Attack: old reasoning-worker path sneaks back in as capsule generator

## Hard rejection

No automatic:

```text
Soma -> local model -> summarize Sol state
```

No automatic:

```text
Soma -> reasoning backend -> decide capsule
```

No Codex capsule generator unless owner explicitly delegates that bounded specialist task, and even then it would not replace Sol as default continuation authority.

Core capsule is caller/Sol-authored.

PASS.

---

# 31. Attack: Work is forced into continuation semantics

## Rule

No default Work integration.

Work owns its own native context/runner/harness. It uses Soma tools directly.

`continuation_*` is optional for:

- cross-surface handoff;
- explicit owner checkpoint;
- external effects that need later normal-Chat continuation.

No mode detector is required.

PASS.

---

# 32. Attack: Work native subagents are mirrored as Soma sources automatically

Reject.

A Work-native subagent/model session is not automatically a Soma effect source.

Only durable external Soma effects/evidence actually routed through Soma need Soma identities.

PASS.

---

# 33. Attack: the continuation kernel becomes Company-lite

## Failure mode

Objective + sources + capsules + commands slowly accumulates Mission/Plan/WorkPackage semantics.

## Boundary

Continuation has:

- one active reasoning objective/handoff lifecycle;
- no organization hierarchy;
- no accepted business PlanRevision;
- no WorkPackage decomposition authority;
- no acceptance authority graph;
- no autonomous company reconciliation.

Company remains a separate optional organizational layer.

PASS.

---

# 34. Attack: continuation kernel duplicates Workflow

## Comparative evidence

Graph runtimes such as LangGraph and Microsoft Workflows persist explicit graph state and `next` execution nodes because they own deterministic/semi-deterministic execution topology.

## Boundary

Continuation must never persist executable topology such as:

```text
next_node
next_step
edges
ready_tasks
stage_index
```

unless it is merely quoted as non-authoritative prior-Sol handoff text.

Deterministic sequence needs can continue to use Workflow compatibility machinery.

PASS.

---

# 35. Attack: source adapter becomes a second canonical projection authority

## Rule

Observation source adapter must be pure/bounded projection over canonical source truth.

It may hash normalized relevant fields but must not maintain independent mutable lifecycle state about the source.

If source projection needs history watermark, use canonical source's journal/version.

PASS.

---

# 36. Attack: continuation source token changes because of irrelevant timestamps

## Rule

Snapshot hash must exclude refresh timestamps and other non-semantic query metadata.

Token schema needs explicit canonicalization/versioning.

`observed_at` is provenance, not change content.

PASS.

---

# 37. Attack: adapter schema changes make all old capsules look stale

## Correction

Every observation token/frontier entry needs adapter/schema version.

When adapter version changes:

- old token remains interpretable through versioned normalization/migration where feasible;
- otherwise resume explicitly reports `token_version_uncomparable` and refreshes current state without pretending semantic equality/difference.

Do not silently hash with new schema against old hash.

PASS with versioning.

---

# 38. Attack: capsule schema evolves and old handoffs become unreadable

Same rule:

- version capsule schema;
- immutable old records;
- migration/projection layer for model-facing resume;
- never rewrite historical capsule body in place merely to match latest schema.

PASS.

---

# 39. Attack: capsule contains secrets

Sol may be reasoning about credentials/service config.

## Rule

Capsule schema/gateway must apply the same secret-bearing material discipline used elsewhere in Soma:

- semantic capsule should reference protected secret/evidence identities rather than store secret values;
- pending effect intent should store normalized/request hashes and safe references, not arbitrary secret-bearing payload copies;
- standard redaction/sensitivity detection can operate mechanically at the write boundary;
- if required semantic content cannot be safely persisted, capsule write should reject or require protected reference form rather than silently expose it.

Do not feed secret values into long-term Knowledge by promotion.

PASS with security integration requirement.

---

# 40. Attack: fresh Chat cannot find the right continuation

User may say only:

```text
continue
```

with several open continuations.

## Minimal discovery contract

`continuation_query.list` should return bounded non-sensitive discovery hints:

```text
continuation_id
label
last_checkpoint_at
short exact/approved objective hint
state
source counts / active-effect count
```

Sol can select confidently when obvious or ask owner only when genuinely ambiguous.

No fuzzy semantic router is required in Soma.

Future ranking can be deterministic recency/project/source affinity, not model semantic ownership.

PASS.

---

# 41. Attack: continuation label itself leaks sensitive objective content

Labels must be bounded and treated as potentially user-visible discovery metadata.

Allow explicit safe labels; do not automatically derive them from arbitrary secret-bearing payloads.

PASS.

---

# 42. Attack: Chat disappears before first checkpoint

No durable semantic state exists.

Soma cannot preserve information that Sol never externalized.

## Honest guarantee boundary

```text
semantic resumption guarantee begins at the last successfully committed capsule
```

Same-thread Chat history may still help, but Soma cannot claim otherwise.

PASS by explicit limitation.

---

# 43. Attack: Chat disappears after checkpoint, before effect launch

State:

- capsule persisted;
- pending intent unbound;
- no proven effect.

Fresh Sol sees unbound/uncertain pending intent and decides whether/how to proceed.

PASS.

---

# 44. Attack: Chat disappears during effect launch

State:

- capsule persisted;
- pending intent exists;
- effect may or may not have started;
- no bound source identity necessarily recorded.

Resume must classify launch outcome as uncertain and reconcile before retry.

PASS if pending intent never auto-executes.

---

# 45. Attack: Chat disappears after effect launch, before link

Same conservative state as above, though recent Run/provider inspection may prove the effect exists.

If found, Sol registers it and continues.

PASS.

---

# 46. Attack: Chat disappears after source link, before new capsule

Latest capsule frontier does not include the newly registered source.

Resume reports it as new/unincorporated.

This is correct.

PASS.

---

# 47. Attack: Chat disappears during capsule commit

SQLite transaction either commits the new immutable capsule/frontier/latest pointer or leaves the previous capsule authoritative.

No partially updated semantic state should be visible after restart.

PASS if migration/store implementation uses one local transaction.

---

# 48. Attack: Chat disappears during resume source resolution

Resume is a read/projection operation. No semantic incorporation state is updated merely because some sources were read.

Retrying resume is safe; it may show fresher current state.

This reinforces removal of `ack_observations`.

PASS.

---

# 49. Attack: Sol sees evidence, reasons, but never checkpoints before disappearing

That semantic integration is not durable in Soma.

This is unavoidable without owning the model runner.

Do not reintroduce automatic weaker-model summarization to close this theoretical gap.

Instead rely on low-burden checkpoint guidance at genuine continuity-risk boundaries.

PASS with explicit limitation.

---

# 50. Attack: repeated resume returns the same changes

Without `ack_observations`, repeated `resume` before a new capsule may show the same deltas.

This is semantically correct: no durable claim says Sol incorporated them.

If UX later needs suppression inside one active Chat, use ephemeral/client-local delivery cursor/session state, explicitly non-authoritative.

Do not add durable semantic acknowledgement in v1.

PASS.

---

# 51. Attack: source registry grows forever

## Rule

Sources are explicitly retired by Sol/controller when no longer relevant, with safety restrictions for active control effects.

Closed continuations may be archived and their active source set compacted/marked inactive, while capsules/frontier history remain bounded provenance.

Retention policy can be added later without changing current semantic authority.

PASS.

---

# 52. Attack: capsules grow forever

Default resume loads only latest capsule.

History retrieval is explicit and bounded.

Retention/archival can later preserve only hashes/critical checkpoints according to owner policy, but v1 should prefer correctness/provenance over premature deletion.

PASS.

---

# 53. Attack: SQLite becomes a bottleneck

Capsules/source registrations/commands are small metadata operations.

Use WAL and short transactions.

Do not hold DB writes across:

- model reasoning;
- remote source refresh;
- effect launch;
- owner wait.

Concurrent source reads may run outside write transactions.

Given Soma's existing single local durable DB architecture, this is consistent with current scale.

PASS for v1; benchmark if usage grows.

---

# 54. Attack: registered source reads acquire repository mutation locks

Reject.

Observation/read adapters remain lock-free with respect to repository operation locks.

Concrete writes keep existing locking.

PASS.

---

# 55. Attack: semantic capsule update accidentally closes/completes objective

Checkpointing and completion must be separate commands.

A handoff saying "looks complete" is not a lifecycle transition unless Sol/owner explicitly invokes `complete` with expected continuation version.

PASS.

---

# 56. Attack: all effects terminal implies completion

Never infer.

A reasoning objective may need analysis, validation, synthesis or owner communication after all current effects are terminal.

PASS.

---

# 57. Attack: failure triggers automatic specialist escalation

Still forbidden.

Failure is source evidence for Sol.

No automatic Codex/reasoning-worker/local-model launch.

PASS.

---

# 58. Attack: large resume context triggers automatic summarizer

Still forbidden by default.

Mechanical pagination/bounded projections first.

Sol can choose an explicit specialist if useful and owner policy permits.

PASS.

---

# 59. Attack: continuity kernel stores provider/model identity

Not needed for semantic correctness and could couple records to transient product implementation.

Capsule `authored_by` may identify semantic authority class (`sol/controller/owner`) without hard-coding model SKU/provider.

PASS.

---

# 60. Attack: continuation is bound to Chat conversation ID

Fresh-context continuation specifically requires independence from one Chat thread ID.

A conversation/thread reference may be optional correlation metadata if product later exposes it reliably, never the identity/authority of the continuation.

PASS.

---

# 61. Attack: exact objective wording is too large for a capsule

The contract can reference a bounded immutable artifact or canonical source if necessary.

For ordinary objectives, store exact bounded text directly.

The critical rule is content identity/hash and authority, not where bytes physically live.

Do not silently summarize exact owner constraints merely to fit a small field.

PASS.

---

# 62. Attack: one continuation spans several unrelated goals

This degrades handoff quality and source relevance.

## Guidance

One continuation should represent one coherent reasoning objective.

When Sol recognizes a genuinely independent objective, open another continuation rather than turning one capsule into a project portfolio.

This is guidance, not a semantic DAG.

PASS.

---

# 63. Attack: one goal branches into two valid alternatives

Do not build graph-fork semantics in v1.

Sol can:

- keep alternatives in one handoff until one is chosen; or
- explicitly open a second continuation if independent long-lived exploration is warranted.

No automatic branch scheduler.

PASS.

---

# 64. Attack: continuation command journal itself becomes event sourcing for all truth

Reject.

Command journal records mutation requests/dispositions/idempotency only.

Current lifecycle lives in continuation row; current source truth lives in canonical authorities; semantic handoff lives in capsule.

Do not reconstruct all canonical state solely by replaying command events.

PASS.

---

# 65. Attack: source registry becomes a general dependency graph

No edges between sources, no readiness propagation, no dependency scheduler.

Role is relevance/control relation only.

PASS.

---

# 66. Attack: the architecture makes Soma harder to use than Codex

The reference systems reinforce a product principle:

- model-driven harnesses should let the model call tools naturally;
- graph/checkpoint machinery belongs where explicit workflows need it;
- memory/session/persistence layers should mostly disappear from the user's normal interaction.

Therefore the user experience target is:

```text
most turns: identical to today
long/interrupted objective: Soma quietly gives Sol a durable handoff/re-entry seam
fresh Chat: "continue" can recover semantic + world state
```

If implementation requires the owner to manually manage capsules/source IDs in ordinary use, the design has failed even if tests pass.

PASS as a design requirement, not yet proven in implementation.

---

# 67. Revised capsule shape after adversarial review

Working concept only:

```text
ContinuationCapsuleV1

identity
  continuation_id
  capsule_id
  capsule_version
  predecessor_capsule_id
  authored_at
  authority_class = sol | owner/controller

contract                    # exact/high-authority partition
  objective_exact_or_ref
  objective_hash
  hard_constraints_exact_or_refs
  contract_hash
  owner_instruction_refs?

handoff                     # non-authoritative Sol operational state
  situation_summary
  explicit_decisions[]
  concise_decision_basis_or_evidence_refs[]
  rejected_paths_worth_preserving[]
  operational_success_criteria[]
  unresolved_questions[]
  working_plan_summary?
  pending_effect_intents[]
  resume_focus?

frontier
  registered source tokens incorporated by this handoff

metadata
  checkpoint_reason
  schema_version
```

No private reasoning trace.

---

# 68. Revised authority labels for resume projection

`continuation_query.resume` should make the authority distinction impossible to miss:

```text
controller_contract
  exact/high-authority request and constraints

prior_sol_handoff
  non-authoritative semantic checkpoint as-of time/frontier

current_sources
  authoritative/bounded projections per source authority

changes_since_handoff
  mechanically derived comparisons

uncertainty
  missing/gapped/unbound/ambiguous source or effect facts

retrieval
  deeper evidence refs
```

This is better than presenting one generic "continuation state" blob.

---

# 69. Four-table kernel survives the adversarial review

After pressure testing, the minimal normalized persistence still appears to be:

```text
controller_continuations
continuation_capsules
continuation_sources
continuation_commands
```

but with **important semantic corrections**:

1. capsule has separate exact contract and non-authoritative handoff partitions;
2. capsule is a handoff, not reasoning trace;
3. frontier is capsule provenance, not mutable acknowledgement state;
4. source registry is effect/world relevance, not dependency graph;
5. pending intent is uncertainty/reconciliation provenance, never queued work;
6. Task and Run are peer canonical effect source kinds according to underlying authority.

---

# 70. What still should not enter v1

1. Any model runner inside Soma.
2. Any semantic scheduler.
3. `next_step`/`next_stage` fields.
4. DAG/edges/readiness propagation.
5. automatic pending-intent execution.
6. automatic specialist fallback.
7. default local-model summarization.
8. per-observation durable acknowledgement.
9. universal Task wrapping.
10. global project event bus.
11. continuous watchers as a prerequisite.
12. Chat-vs-Work inference.
13. conversation-ID identity binding.
14. Company dependency.
15. Supervisor/Workflow cognitive routing.

---

# 71. Failure-mode matrix summary

| Failure boundary | Durable state after failure | Correct resume behavior |
|---|---|---|
| before any capsule | no Soma semantic guarantee | use live Chat/owner context; cannot fabricate lost semantics |
| after capsule, before action | handoff + unbound intent | decide/reconcile whether to execute |
| during action launch | handoff + unbound/ambiguous intent | reconcile before retry |
| after launch, before link | handoff + unbound intent; effect may exist | inspect canonical Run/Task/provider, bind if found |
| after link, before new capsule | source registered but absent from old frontier | report as new/unincorporated |
| during capsule commit | old or new capsule atomically current | retry checkpoint if needed |
| during resume | no semantic state mutation | retry read; fresher state okay |
| source changes after capsule | prior handoff + newer source token | Sol reconciles |
| history pruned | current source known + history gap | expose uncertainty; Sol decides verification |

---

# 72. Adversarial verdict

**PASS WITH MATERIAL CAPSULE-AUTHORITY CORRECTION.**

The architecture survives the failure-mode review, but Iteration 14's capsule concept must be corrected so that the owner's exact objective/constraints do not drift through Sol-authored semantic summaries.

The strongest candidate now is:

> Soma should provide a high-quality agent interface plus a four-table semantic continuation kernel. A continuation stores an immutable, bounded Sol handoff capsule whose exact controller contract is separately identified from non-authoritative operational interpretation, together with the authoritative source frontier that handoff incorporated. Current world/effect truth remains in Task/Run/repository/Knowledge/service authorities. On resume, Soma mechanically reconciles current registered sources against the capsule frontier and returns the exact contract, prior handoff, new evidence and uncertainty to Sol. Sol alone decides what to think or do next.

No graph/workflow/reasoning state machine is needed.

---

# 73. Recommendation for Iteration 16 final synthesis

Iteration 16 should explicitly supersede Iteration 10 and freeze the following before any implementation plan:

1. **Reasoning authority** - Sol/Work according to surface; Soma never semantic actor.
2. **Reasoning model** - adaptive trajectory, no fixed reason/act/observe state machine.
3. **Soma role** - agent interface / nervous system + semantic re-entry support.
4. **Fast path** - existing tools remain direct; continuation is optional durability scaffolding.
5. **Persistence** - four small tables in existing SQLite for v1.
6. **Capsule** - exact controller contract + non-authoritative Sol handoff + incorporated frontier; no chain-of-thought.
7. **Observation** - registered source adapters; source-specific snapshot/watermark classes; no global event bus.
8. **Incorporation** - new capsule frontier is durable semantic incorporation boundary; no `ack_observations`.
9. **Effects** - Task/Run and future canonical effect identities tracked without universal wrapping.
10. **Pending intent** - crash reconciliation only; never queued work.
11. **Scope/security** - continuation never bypasses source-specific ProjectScope/authorization.
12. **Concurrency** - reasoning/source reads lock-free; short DB CAS only.
13. **Work** - unaffected by default.
14. **Company** - separate/frozen.
15. **Specialists** - optional explicit delegation only; Codex owner-gated.
16. **Public surface** - dedicated `continuation_query` / `continuation_action` is semantically cleaner than overloading Task/Workflow.
17. **Acceptance** - fresh-Chat real workflow test is mandatory, not just unit tests.

Only after that synthesis should a separate implementation-planning phase begin on owner approval.
