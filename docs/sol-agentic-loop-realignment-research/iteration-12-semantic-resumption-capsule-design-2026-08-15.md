# Iteration 12 - Semantic Resumption Capsule Design

Date: 2026-08-15
Status: RESEARCH ONLY - implementation not authorized
Track: Sol-centric agentic reasoning architecture

## Research question

Iteration 11 established that Soma should not encode a fixed `reason -> act -> observe -> reason` cognitive state machine. Sol owns an adaptive reasoning trajectory, while Soma should provide a strong agent interface and durable continuity.

This iteration asks:

> What is the minimum explicit state Soma must preserve so a returned or fresh Sol context can intelligently resume the same reasoning objective when Soma does not own the ChatGPT model runner and therefore cannot serialize exact hidden model runtime state?

This is a **semantic resumption** problem, not a Task-loop problem.

---

# 1. Evidence base

Primary/current sources used in this iteration include:

## OpenAI Codex

- Current Codex context-compaction handoff prompt:
  - `openai/codex/codex-rs/prompts/templates/compact/prompt.md`
- Current Codex prompting guide and long-running-work guidance.
- Current Codex turn/session implementation reviewed in Iteration 11.

## OpenAI Agents SDK

- `RunState`: documented durable pause/resume boundary for a runner-owned agent run.
- Sessions: persistent model-visible conversation history across runs.
- Context management: app/runtime context is separate from model-visible conversation state.
- Sandbox concepts: `RunState`, sandbox `session_state`, and workspace snapshots are separate resume mechanisms.
- Sandbox memory: long-term distilled memory is explicitly separate from conversational Session history.

## Google Gemini CLI

- Session save/resume stores conversation history.
- Mutation checkpointing stores project file snapshot + conversation history + the pending tool call.
- `GEMINI.md` / memory is separate persistent project/user context.
- Current configuration separately exposes session checkpointing, context compression, and memory.

## Agent-memory research

- MemGym (2026) explicitly separates memory quality from reasoning/tool-use competence and targets dynamic memory formation in coding, deep research, tool-use dialogue and computer use.
- Agent Memory: Characterization and System Implications of Stateful Long-Horizon Workloads (2026) characterizes agent memory as a separate systems problem with construction, retrieval and generation costs/trade-offs.

Open repository issue reports around Codex/Gemini context compaction were used only as field evidence of failure modes, not as authoritative product contracts.

---

# 2. Exact runtime resumption versus semantic resumption

## DOCUMENTED FACT

OpenAI Agents SDK `RunState` can serialize enough runner-owned state to resume an interrupted run. It includes model responses, generated items, approval/interruption state, current interrupted step, tool-use tracking and optional server-managed conversation identity.

A sandbox-capable run can additionally resume a live/serialized sandbox session or seed a fresh workspace from a snapshot.

## CONSTRAINT

Soma does not own the normal ChatGPT/Sol runner.

Therefore Soma cannot correctly serialize or restore:

- hidden model reasoning state;
- private chain-of-thought;
- model KV/cache state;
- exact internal sampling continuation;
- arbitrary ChatGPT product runtime objects;
- exact server-side thread execution state unless ChatGPT itself exposes such an API in the future.

## INFERENCE - HARD ARCHITECTURE BOUNDARY

Soma must **not imitate `RunState` incompletely and call it exact resume**.

The achievable contract is:

```text
semantic resumption
=
returned/fresh Sol receives enough explicit prior semantic state
+ authoritative current external state
+ changes since that semantic state was authored

to reconstruct the situation and continue intelligently
```

This is weaker than exact runtime resume but much stronger than merely storing a goal and Task IDs.

---

# 3. Four continuity layers must remain separate

The runtime evidence strongly supports four distinct authorities.

```text
Layer A - live/model-visible conversation continuity
  ChatGPT thread / SDK Session / provider conversation state

Layer B - active reasoning-objective semantic continuity
  explicit operational handoff/checkpoint for the current objective

Layer C - external execution and world continuity
  Tasks / Runs / repositories / services / journals / resources

Layer D - long-term durable knowledge and memory
  accepted decisions / facts / user preferences / reusable lessons
```

For Soma normal Chat:

- ChatGPT itself primarily owns A while the thread remains available.
- The new architecture may need to own/reference B.
- Soma already has strong authorities for much of C.
- canonical project knowledge/memory owns D.

## Critical design rule

Do not collapse B into D.

A current debugging hypothesis, provisional plan, unresolved question, or temporary resume pointer should not automatically become durable project memory.

Likewise, do not collapse B into C. Exact Task state says what an effect did; it does not fully say what Sol currently understands about the objective.

---

# 4. Why objective + Tasks is insufficient for fresh-context resumption

Consider:

```text
Objective: fix intermittent deployment failure
Task A: inspect logs -> completed
Task B: run validation -> completed
Task C: patch config -> completed
```

A fresh model can retrieve those results, but may still not know:

- which hypothesis A disproved;
- why B changed the interpretation of the failure;
- which temporary workaround was rejected;
- what owner constraint ruled out another approach;
- whether C was exploratory or intended as final;
- what still needs verification;
- which evidence has already been semantically incorporated;
- whether a previous apparent success was later invalidated.

Re-deriving all of that from raw evidence can be expensive, and sometimes impossible if a relevant prior discussion was not itself an external artifact.

## DOCUMENTED ANALOGUE

Codex's current compaction prompt explicitly requests a handoff for another LLM containing current progress/key decisions, important context/constraints/preferences, what remains, and critical references.

This is direct evidence that model-to-model continuation benefits from a **semantic handoff layer** beyond raw tool state.

---

# 5. The semantic resumption object should be a capsule, not a transcript

Working research term:

```text
ReasoningResumptionCapsule
```

This is deliberately not called a reasoning state machine, turn, or loop state.

## Purpose

A capsule answers:

> If another Sol instance had only a compact packet plus access to Soma's authoritative evidence, what would it need to avoid starting the reasoning trajectory over from scratch?

## Non-purpose

It is not:

- private chain-of-thought;
- full transcript;
- exact model state;
- executable workflow;
- mandatory plan;
- list of Tasks to auto-run;
- long-term memory dump;
- semantic summary generated by a weaker model.

---

# 6. Minimum semantic content hypothesis

A useful capsule probably needs the following semantic classes.

## 6.1 Objective contract

```text
objective
active constraints
success / done criteria
owner-imposed exclusions or authority boundaries
```

These should preferably reference the durable objective contract rather than duplicate it when an authoritative reference already exists.

## 6.2 Current interpretation

A concise explicit statement of what Sol currently believes the situation is.

Examples:

- current diagnosis;
- currently favored explanation;
- current architectural interpretation;
- current state of the investigation.

This is not hidden reasoning. It is the conclusion/state-of-understanding needed to continue.

## 6.3 Key decisions

Only decisions whose loss would materially change continuation.

Each may include a **brief decision basis**, not chain-of-thought.

Example:

```text
Decision: do not use provider-native reasoning as the default path.
Basis: it duplicates Sol cognition and caused prior authority drift.
```

## 6.4 Rejected/superseded approaches worth preserving

Not every failed thought deserves storage.

Preserve only paths likely to be wastefully rediscovered or accidentally reintroduced, together with the evidence/reference that invalidated them when available.

## 6.5 Current working plan, only if one exists

A working plan is optional mutable cognitive scaffolding.

The capsule may summarize it, but:

- it is explicitly non-authoritative;
- it is not a DAG executor;
- future Sol may replace it immediately after reconciling new evidence.

## 6.6 Unresolved questions / uncertainty

This is essential for honest continuation.

Examples:

- unknown cause;
- effect outcome uncertain;
- conflicting evidence;
- owner decision required;
- validation not yet performed.

## 6.7 Evidence already incorporated

Do not copy evidence bodies.

Instead record bounded references/hashes/watermarks sufficient to establish:

```text
"this semantic capsule was authored after Sol had incorporated evidence frontier F"
```

This becomes the bridge to Iteration 13.

## 6.8 Active durable effects

Reference Tasks/Runs that remain relevant to the reasoning objective.

The capsule should not copy their lifecycle state. Current state is resolved live when resuming.

## 6.9 Resume focus

Codex's compaction contract asks for clear next steps. That is useful, but in Soma it must be explicitly **advisory and stale-sensitive**.

A better field than authoritative `next_action` is something like:

```text
resume_focus
```

meaning:

> what Sol expected to investigate/decide/validate next, as of this capsule

On resume, Sol first reconciles the capsule with current world/effect changes and then decides whether that focus is still valid.

---

# 7. Proposed capsule shape for further testing

This is conceptual, not implementation schema.

```text
ReasoningResumptionCapsuleV1

identity
  continuation_id
  capsule_id
  capsule_version
  authored_at
  authored_by = Sol/controller

objective
  objective_ref/hash
  constraints_ref/hash
  done_criteria_ref/hash or compact text

semantic_state
  current_interpretation
  key_decisions[]
  rejected_or_superseded_paths[]
  unresolved_questions[]
  working_plan_summary?        # optional, explicitly non-executable
  resume_focus?                # advisory, not authoritative

evidence_basis
  incorporated_frontier_ref/hash
  critical_evidence_refs[]

active_effect_refs
  task_ids[]                    # references only

continuity_metadata
  predecessor_capsule_ref/hash?
  reason_for_checkpoint
```

The exact text budgets, field normalization and storage mechanism remain open.

---

# 8. The checkpoint should be authored by Sol

## OWNER REQUIREMENT + ARCHITECTURAL INFERENCE

The semantic checkpoint must not be generated by a default weaker summarizer/provider.

Otherwise the architecture recreates the Agent/Worker problem in subtler form:

```text
Sol reasons
 -> another model decides what mattered
 -> future Sol receives that model's interpretation
```

That makes the intermediary model a semantic bottleneck and can silently corrupt continuity.

## Correct authority

```text
Sol decides what semantic state matters
 -> submits bounded capsule
 -> Soma validates shape/size/references mechanically
 -> Soma persists it verbatim/canonically
```

Soma may mechanically populate immutable identity/timestamps/hashes and live effect references, but must not invent semantic conclusions.

---

# 9. Avoid burdening Sol: checkpoint only at continuity-risk boundaries

A checkpoint on every tool call would be exactly the sort of ceremony the owner rejected.

## No checkpoint needed

Usually no semantic capsule update for:

- one synchronous inspection returning in the same active Chat turn;
- trivial calculation;
- short deterministic tool sequence;
- every individual file read;
- every Task state transition;
- every internal reasoning episode.

## Strong checkpoint candidates

A new capsule is useful when one of these occurs:

1. **Before a durable external effect that may outlive the current Chat context**, after Sol has made the semantic decision to launch it.
2. **Before deliberately pausing or handing over to a fresh Chat**.
3. **After a major semantic decision or change of direction** when losing it would cause expensive rediscovery.
4. **Before an expected long wait** where Chat may disappear.
5. **At an explicit owner-requested handoff/checkpoint**.
6. Potentially when model/context pressure is known, if the ChatGPT surface someday exposes a reliable signal.

Do not invent an unreliable context-pressure detector from prompt length or elapsed time.

---

# 10. Important atomicity insight: semantic checkpoint before effect

The existing Task architecture already follows:

```text
persist identity first
 -> launch external effect second
```

The same boundary can protect semantic continuity.

When Sol chooses a long-running/effectful action under an active continuation, a robust sequence is conceptually:

```text
Sol has reasoned and decided to launch effect E

BEGIN short durable transaction
  persist/supersede latest Sol-authored resumption capsule
  reserve canonical Task/effect identity
  associate Task with continuation
  anchor capsule/frontier identity
COMMIT

launch effect E through existing Task authority
```

If Chat disappears immediately after launch, future Sol receives:

- what prior Sol believed/decided **before the effect**;
- exact identity/state of the effect;
- any new evidence produced since that capsule.

This is substantially safer than:

```text
launch effect
 -> hope there is enough Chat history later
```

## Critical rule

The transaction persists caller-supplied semantic content; it does **not** run a model or hold the database transaction while Sol reasons.

---

# 11. After the effect completes, Soma should not rewrite the capsule

Suppose:

```text
Capsule C says:
  "Hypothesis X is favored; Task T is being run to validate it."

Task T completes while Sol is absent and disproves X.
```

Soma must **not** semantically edit the capsule to say hypothesis X is false.

Instead:

```text
C remains immutable truth about what Sol believed as of frontier F
current authoritative Task evidence says T disproved/failed/returned result R
continuation bundle says new evidence exists after F
```

Returned Sol performs the semantic update.

This preserves authority and provenance.

---

# 12. Resumption should be reconciliation, not blind continuation

A stale `next_action` is dangerous.

Correct fresh-context behavior:

```text
1. Load latest capsule.
2. Resolve current objective/constraints.
3. Resolve authoritative current state of registered effects/resources.
4. Show changes after the capsule's incorporated frontier.
5. Sol reconciles old interpretation with new truth.
6. Sol chooses whatever reasoning/action path is now appropriate.
```

The system therefore should not present:

```text
NEXT_TASK = X
```

as an instruction from Soma.

It may present:

```text
prior_resume_focus = X
new_evidence_since_capsule = [...]
```

and let Sol decide.

---

# 13. Same-thread and fresh-thread behavior should differ only in how much continuity is needed

## Same active Chat thread

The ChatGPT thread already contains rich model-visible context.

Soma should not redundantly inject a large capsule on every call.

Use the capsule as durability insurance and for explicit continuation queries, not as a second transcript.

## Same thread after a long external wait

Soma can return:

```text
new external evidence since capsule/frontier
+ current effect state
```

The existing Chat context may already contain the semantic capsule implicitly.

## Fresh Chat / lost context

Soma returns the full compact resumption bundle:

```text
objective contract
latest semantic capsule
new authoritative deltas since capsule
current relevant effect/resource state
unresolved interruptions/uncertainty
retrieval refs
```

This is the high-value case.

---

# 14. Active semantic state is not long-term memory

## REPOSITORY FACT

Current canonical Knowledge supports durable controller memory with lifecycle/provenance/supersession. It is designed for accepted project knowledge, decisions and other durable records.

## INFERENCE

`ReasoningResumptionCapsule` should not default into Knowledge merely because Knowledge can store Markdown/text.

Reasons:

- temporary hypotheses would pollute durable memory;
- working plans age quickly;
- resumption state has one active objective lifecycle;
- frequent capsule supersession would create noisy semantic memory;
- memory retrieval could surface stale provisional thinking in unrelated future work.

## Promotion path

A semantic item can separately be promoted to canonical Knowledge when Sol/owner determines it has durable value.

Example:

```text
Capsule contains provisional architectural decision D
 -> owner/Sol later accepts D as durable project architecture
 -> explicit knowledge write creates canonical durable decision
```

The capsule may then reference that durable decision instead of carrying duplicate text.

---

# 15. Existing ExternalCoder handoff offers mechanics, not semantics

## REPOSITORY FACT

Soma's existing `ExternalCoderHandoff` is a bounded inert handoff packet and `handoff_writer.py` atomically writes JSON/text artifacts.

This proves useful lower-level mechanics already exist:

- bounded typed handoff object;
- atomic artifact writing;
- context/evidence manifests;
- inert packet with no automatic launch requirement.

## REPOSITORY FACT - DO NOT REUSE AS AUTHORITY

Its current context builder also performs memory search and can invoke a local-model context compressor when configured.

Those semantics are unsuitable for core Sol continuation.

## INFERENCE

Potential reuse later:

- atomic writer helpers;
- artifact hash/provenance style;
- manifest/reference mechanics.

Do **not** reuse:

- semantic routing;
- local-model summary;
- ExternalCoder policy decisions;
- its task-type classifier assumptions.

A new capsule should remain Sol-authored.

---

# 16. Capsule storage options

No final choice yet.

## Option A - bounded semantic fields directly in continuation DB

Advantages:
- atomic with continuation/Task reservation;
- easy CAS/versioning;
- simple retrieval.

Risks:
- mixes larger semantic text with transactional rows;
- harder to content-address and inspect independently;
- schema pressure if capsule evolves.

## Option B - immutable content-addressed capsule artifact + DB pointer

Advantages:
- clean separation between transactional identity and semantic payload;
- easy hashing/provenance;
- immutable historical capsules;
- flexible schema evolution.

Risks:
- requires a robust generic artifact authority or carefully scoped new one;
- atomicity across SQLite + filesystem must be designed conservatively.

## Option C - canonical Knowledge record

Not preferred for active capsule state for reasons above.

## Option D - reuse ExternalCoder handoff storage directly

Not preferred. It carries the wrong semantic domain and dependencies.

## Leading hypothesis

A small transactional continuation row containing:

```text
latest_capsule_ref
latest_capsule_hash
latest_capsule_version
```

plus an immutable bounded capsule artifact looks cleanest conceptually, **if** a safe artifact identity/write boundary can be proven.

Otherwise a dedicated bounded capsule table may be simpler and safer than forcing reuse.

Iteration 14 should decide after repository-specific transaction/recovery inspection.

---

# 17. Capsule history and supersession

A reasoning trajectory may produce many checkpoints.

Avoid two extremes:

```text
keep only latest text with no history
```

and:

```text
inject every historical capsule into every resume
```

## Candidate model

- Capsules immutable.
- Continuation points to latest capsule.
- New capsule names predecessor and supersedes it for active resumption.
- Old capsules remain retrievable as provenance for a bounded retention horizon or until objective archival policy runs.
- Resume projection injects only latest capsule by default.
- Older capsule retrieval is explicit.

This avoids a growing transcript while retaining audit/recovery ability.

---

# 18. Compaction teaches a second lesson: repeated summaries can degrade

Codex issue reports describe loss of older constraints/progress across repeated compactions and requests for explicit task/frontier checkpoints. These reports are not product contracts, but they expose a plausible failure mode:

```text
summary of summary of summary
 -> semantic drift / lost frontier / repeated work
```

## INFERENCE

Soma should not update capsules by asking Sol to summarize only the **previous capsule**.

When creating a new capsule, Sol should have access to:

```text
previous capsule
+ current relevant context
+ authoritative evidence since previous frontier
```

and produce a fresh current-state capsule.

Durable accepted facts/decisions should be referenced from canonical memory rather than repeatedly paraphrased across capsules where possible.

---

# 19. Do not make `resume_focus` a completion mechanism

A capsule may say:

```text
resume_focus = validate configuration change with integration tests
```

But if the world changes while Sol is away, that may no longer be correct.

Therefore:

```text
resume_focus is prior Sol intent
!= pending executable Task
!= workflow edge
!= mandatory next action
```

Likewise:

```text
all Tasks terminal
!= capsule automatically advances
!= objective complete
```

Returned Sol owns both interpretation and completion judgment.

---

# 20. Owner changes and new instructions supersede the capsule semantically

If the owner returns and says:

```text
"Actually stop that approach and do Y instead."
```

The old capsule remains provenance, but new owner instruction is higher-priority current context.

The next Sol reasoning episode should:

1. reconcile owner instruction;
2. inspect/cancel/contain any old effects as appropriate;
3. create a new semantic capsule when continuation durability is again needed.

Soma must not treat the prior capsule as immutable instruction authority.

---

# 21. Capsule completeness should be testable without judging private reasoning

We cannot test whether a capsule contains hidden chain-of-thought. We should not try.

We can test operational resumption quality.

Candidate acceptance test:

> Give a fresh Sol instance only the objective contract, capsule, current authoritative state/deltas, and retrieval capabilities. Can it correctly identify the current problem frontier, avoid already-rejected work, respect owner constraints, and continue without requiring the owner to re-explain the project state?

This is observable and directly tied to the user's goal.

---

# 22. Adversarial resumption scenarios

## Scenario A - long Task completes successfully while Chat is gone

Before launch:
- capsule C recorded;
- Task T reserved/associated;
- effect launches.

On resume:
- C says why T was run;
- current T result is new since C;
- fresh Sol interprets T and decides next step.

PASS candidate.

## Scenario B - Task fails in a surprising way

C's `resume_focus` assumed success path.

On resume, failure evidence outranks stale focus. Sol changes approach.

PASS if focus is advisory only.

## Scenario C - another project/thread changes the same repository

C contains old repo/evidence frontier.

Resume bundle shows repository/source change after C. Sol reconciles rather than blindly executing old plan.

PASS only if Iteration 13 observation frontier includes the relevant source.

## Scenario D - owner changes objective while Task is still running

New owner instruction supersedes old semantic intent. Existing Task remains exact durable effect requiring explicit cancellation/containment decision.

PASS.

## Scenario E - no Task exists

Sol spent time investigating and formed a major architectural conclusion, then owner asks to pause.

Capsule can preserve semantic state even with zero Tasks.

This proves continuation cannot be defined purely through Task membership.

## Scenario F - ten tiny synchronous reads

No capsule updates during those reads. Sol reasons normally in active Chat context.

PASS; no ceremony.

## Scenario G - repeated long-running stages

One capsule per continuity-risk/milestone boundary, not per Task transition. New capsule supersedes old for default resume.

PASS candidate if context remains bounded.

## Scenario H - fresh Sol disagrees with previous Sol

Capsule records prior interpretation and evidence basis. Fresh Sol can revise it after seeing current evidence.

PASS. Capsule is provenance/current handoff, not dogma.

---

# 23. Proposed minimal resumption bundle

For a **fresh** Chat context, a model-facing bundle should likely contain:

```text
ContinuationResumeBundleV1

objective
  compact objective / refs
  active constraints
  definition of done

prior_semantic_state
  latest ReasoningResumptionCapsule

current_effect_state
  compact Task/Run projections for registered relevant effects

new_since_capsule
  registered-source changes after capsule frontier

interruptions
  approvals / awaiting-controller / uncertainty / recovery

retrieval
  exact refs/tools for deeper evidence
```

No semantic `recommended_next_action` from Soma.

No full event dump.

No private reasoning.

No automatic provider delegation.

---

# 24. Potential simplification of the earlier continuation schema

Iteration 10 hypothesized separate continuation commands and Task membership with consumed observation hashes.

Iteration 12 suggests the central semantic primitive may instead be:

```text
Continuation
  objective identity
  latest capsule identity
  lifecycle/version

Capsule
  semantic resumption state as of frontier F

Registered effects/sources
  what current external truth is relevant

Command journal
  idempotent mutations
```

The exact table count is less important than the authority split.

Do not freeze schema until Iteration 13 defines the observation/source frontier.

---

# 25. Interaction with Work

ChatGPT Work already owns its own native long-running model context/agent trajectory.

Therefore:

- Work should not be forced to emit Soma semantic capsules every reasoning step.
- Work can still use Soma Tasks/Run/world/evidence tools directly.
- A Soma capsule might be useful only for explicit cross-surface handoff, owner-requested durable checkpoint, or external work that must later be continued by normal Chat.

This remains an optional interoperability case, not core Work cognition.

---

# 26. Interaction with Company

Company remains frozen and separate.

A reasoning-resumption capsule is **not** a Company PlanRevision.

Difference:

```text
ReasoningResumptionCapsule
  transient operational semantic handoff for one active reasoning objective

Company PlanRevision
  accepted durable organizational commitment
```

Do not merge them.

---

# 27. Interaction with long-term knowledge

A useful three-way distinction is now:

```text
working cognition
  lives in active Chat/model context
  not persisted by Soma as hidden reasoning

resumption capsule
  bounded current-objective operational semantic handoff
  active only for continuity

canonical knowledge
  accepted durable facts/decisions/preferences/lessons
  intended for future unrelated/recurrent retrieval
```

This separation reduces semantic pollution and makes authority clearer.

---

# 28. Revised checkpoint trigger hypothesis

Leading low-burden policy:

```text
No active continuation needed
 -> ordinary tool use; no capsule

Sol decides an objective/action now needs durability across interruption
 -> create/open continuation + capsule

Sol makes a major semantic update and is about to cross a continuity-risk boundary
 -> supersede capsule

External world changes while Sol absent
 -> no semantic capsule rewrite

Sol returns
 -> reconcile capsule + new evidence
 -> update capsule only if another durability boundary is approaching

Objective done/cancelled
 -> close continuation
 -> optionally promote durable lessons/decisions to Knowledge separately
```

This is much lighter than persistent turn-by-turn journaling.

---

# 29. What Iteration 12 rejects

1. Exact model-runtime resume claims for normal Chat.
2. Persisting private chain-of-thought.
3. Full transcript as the Soma continuity mechanism.
4. Objective + Tasks as sufficient general semantic continuity.
5. Writing every temporary hypothesis into canonical memory.
6. A weaker model as default checkpoint summarizer.
7. Updating semantic capsule automatically when a Task changes.
8. Treating capsule `resume_focus` as an executable next step.
9. Checkpointing every tool call or Task transition.
10. Blindly continuing old plans without reconciling current evidence.
11. Reusing ExternalCoder semantic routing/local summary for Sol continuity.
12. Freezing the continuation schema before the observation frontier is researched.

---

# 30. Iteration 12 provisional verdict

**A Sol-authored, bounded semantic resumption capsule appears necessary for robust fresh-context continuation, but only at continuity-risk boundaries.**

The strongest architecture candidate is now:

```text
SOL
  owns live adaptive reasoning
  authors occasional semantic resumption capsule

SOMA
  durably stores/references that capsule
  keeps exact execution/world truth in existing authorities
  tracks what registered evidence changed after the capsule
  returns a compact reconciliation bundle on resume
  never chooses the next semantic step
```

The key new design rule is:

> **Persist semantic intent before launching an effect that may outlive the current model context, then let future world changes accumulate as authoritative deltas rather than rewriting the semantic checkpoint.**

This mirrors Soma's existing persist-before-effect philosophy while preserving Sol as semantic authority.

However, this design cannot be finalized until the observation/evidence frontier is defined.

---

# 31. Next research iteration

Proceed to:

**Iteration 13 - Registered Observation and Evidence Frontier Architecture**

Questions:

1. Which non-Task sources can be registered as relevant to a reasoning continuation?
2. Should a source use version, hash, event cursor, generation, timestamp, or source-specific watermark?
3. How can Soma detect meaningful changes without polling or copying every external system?
4. How should transient event-only changes remain visible if current snapshot later returns to the prior value?
5. How does ProjectScope constrain source registration across simultaneous projects?
6. How can model-facing deltas remain bounded and retrieval-oriented?
7. When should a source be a control-owned effect versus read-only evidence dependency?
8. Can existing Task events, RunStore, repository heads/generations, knowledge records, service queries and external journals provide enough source identities without a new global event bus?

Do not produce a new final synthesis or implementation plan until Iteration 13 and Soma-specific convergence are complete.
