# Iteration 24 - Free-form Semantic Handoff over Structured Reasoning State

Date: 2026-08-15
Status: RESEARCH - corrective iteration after owner warning about repeated formatting/schema failure
Track: Sol-centric agentic reasoning architecture

---

## Research question

How should Soma preserve enough semantic continuity for a fresh Sol **without requiring Sol to serialize its reasoning into rigid schemas**?

The trigger for this iteration is an important historical warning from the owner: the previous Agent/Worker implementation repeatedly tried to improve reliability by adding increasingly strict model-produced contracts, schemas, evidence shapes, proof fields and formatting rules. Multiple revisions did not solve the underlying semantic problem and made the architecture harder to use.

The candidate `decision_basis`, structured `ContinuationCapsule`, and similar fields risk repeating that mistake under new names.

---

# 1. Adversarial hypothesis

Assume the following design rule is wrong:

> If a future Sol needs semantic state, require current Sol to populate a detailed structured handoff object.

Attack it from three directions:

1. model reliability;
2. architecture authority;
3. user/operator ergonomics.

---

# 2. Current Codex evidence

OpenAI Codex's current compaction prompt does **not** ask the model to serialize a detailed machine-readable reasoning state.

It asks for a concise handoff summary for another LLM containing broad human/agent-readable content such as:

- current progress and key decisions;
- important context, constraints, or user preferences;
- remaining work;
- critical data, examples or references.

This is deliberately semantic text, not a state-machine schema.

Primary source:

- OpenAI Codex `codex-rs/prompts/templates/compact/prompt.md`
- https://github.com/openai/codex/blob/main/codex-rs/prompts/templates/compact/prompt.md

More importantly, Codex does not make the summary carry all continuity authority.

Current `compact.rs` separately preserves real user messages and re-injects canonical initial context around the compaction summary. The summary is one model-authored semantic handoff inside a runner-owned history structure.

Primary source:

- OpenAI Codex `codex-rs/core/src/compact.rs`
- https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs

This separation matters:

```text
runner-owned exact/mechanical context
        +
model-authored free-form semantic summary
```

not:

```text
model-authored structured object
that pretends to be all exact state
```

---

# 3. Current OpenAI model guidance supports leaner interfaces

OpenAI's current GPT-5.6 model guidance recommends leaner prompts and tool descriptions, and reports that reducing repeated instructions/examples can improve evaluation performance while reducing token use.

It also distinguishes bounded deterministic/programmatic processing from situations where each result may change the model's next decision; in those cases direct model/tool interaction is preferred.

Primary source:

- OpenAI Model Guidance
- https://developers.openai.com/api/docs/guides/latest-model

Architectural implication:

> Do not convert semantic judgment into a large structured contract merely because structured contracts are easier for code to validate.

Soma should validate only facts Soma actually owns.

---

# 4. Runner-owned systems can preserve exact state because they own it

The OpenAI Agents SDK can serialize `RunState` because it owns the agent runner and its model/tool execution state.

Sessions can preserve conversation history because the SDK owns the session history.

Claude Code can resume a session by ID because Claude Code owns the session.

Primary sources:

- https://openai.github.io/openai-agents-python/ref/run_state/
- https://openai.github.io/openai-agents-python/sessions/
- https://code.claude.com/docs/en/cli-usage

Soma normal-Chat integration owns none of those hidden runtime/session boundaries.

Therefore Soma should not compensate by asking Sol to recreate exact runtime state in JSON.

---

# 5. Failure mode of structured semantic capsules

A structured capsule such as:

```text
current_interpretation
explicit_decisions[]
rejected_paths[]
unresolved_questions[]
working_plan[]
resume_focus
decision_basis[]
```

creates several false assumptions.

## 5.1 Field-completeness assumption

It assumes Sol reliably remembers which semantic fact belongs in which field every time.

Missing a field can silently become missing continuity.

## 5.2 Taxonomy assumption

It assumes the schema designer predicted the categories future reasoning will need.

Real reasoning does not naturally divide into a fixed stable taxonomy.

## 5.3 Parser-authority assumption

Once fields exist, implementation tends to start treating them as machine authority.

Example:

```text
resume_focus = "run test X"
```

can slowly mutate from helpful handoff prose into implicit executable next-step state.

## 5.4 Version treadmill

When a model repeatedly fails an edge case, the natural engineering reaction becomes:

```text
V1 -> add field
V2 -> add enum
V3 -> add provenance
V4 -> add another required list
...
```

This is exactly the historical failure pattern the owner identified.

## 5.5 Cognitive tax

The model spends reasoning/tool budget formatting internal semantic state for Soma rather than solving the objective.

---

# 6. Better architecture: semantic text is opaque to Soma

The semantic checkpoint should be conceptually:

```text
SolHandoff

handoff_id                  # mechanical
continuation_id             # mechanical
basis_contract_revision_id  # mechanical
authored_at                 # mechanical
content_hash                # mechanical
handoff_text                # opaque UTF-8 / Markdown text
```

Soma may enforce:

- maximum byte size;
- UTF-8 validity;
- secret/sensitivity policy;
- immutability/content hash;
- continuation identity;
- contract revision identity;
- idempotent write identity.

Soma must **not** parse `handoff_text` to determine:

- decisions;
- plan;
- next step;
- evidence importance;
- unresolved questions;
- completion;
- retry strategy;
- specialist need.

Those semantics are for the next Sol.

---

# 7. Prompt guidance may suggest content but never define a parser contract

A useful checkpoint prompt may say:

> Write a concise engineering handoff for another Sol. Preserve what matters to continue: current situation, important decisions/constraints, unfinished work, critical references and any uncertainty. Use whatever structure makes this task easiest to resume.

That is guidance, not a wire schema.

The handoff may be:

- paragraphs;
- bullets;
- a tiny table;
- code/path references;
- task-specific sections;
- a combination.

No required headings.

No semantic parser.

No schema upgrade because one project needed a different kind of reasoning note.

---

# 8. Contract text should also remain semantically simple

Iteration 18 correctly separated governing contract revision from Sol handoff revision.

This iteration further tightens the shape:

A contract revision should primarily preserve one bounded **controller instruction text/artifact** plus honest provenance metadata.

Do not require the model to split the controller's request into:

```text
objective
hard_constraints[]
exclusions[]
authorization_boundaries[]
done_criteria[]
```

unless a specific product feature genuinely needs one of those fields mechanically.

A better conceptual record is:

```text
ContinuationContractRevision

revision_id
continuation_id
parent_revision_id
submitted_text_or_artifact_ref
content_hash
provenance_class
controller_request_id
created_at
```

`provenance_class` describes what Soma can actually prove, for example:

```text
controller_submitted_text
owner_confirmed_artifact
external_authority_ref
```

Do not call text `owner_exact` unless Soma has an upstream boundary that can establish that fact.

---

# 9. Machine facts remain structured because they are machine facts

This correction does **not** mean remove schemas from Soma.

Structured contracts remain appropriate for facts Soma mechanically owns, such as:

```text
continuation_id
state_version
contract_revision_id
Task ID
Run ID
request identity/hash
Task state_version
Run status/state_version
ProjectScope generation
repo HEAD
file/content hash
result publication state
```

The rule is:

> Structure the machine state, not the model's cognition.

---

# 10. Relationship to `decision_basis`

The prior candidate required Sol to serialize the mutable evidence it materially used for a side-effect decision.

That is too close to the old failure pattern.

Reasons:

1. Soma cannot know whether Sol listed all material evidence.
2. Sol may over-list evidence and create needless stale failures.
3. Sol may under-list evidence and create false confidence.
4. Different reasoning tasks need different evidence concepts.
5. Repeated formatting refinement recreates schema treadmill risk.

Therefore:

**`decision_basis` should not be a required architectural concept.**

Effect safety should instead use mechanical preconditions intrinsic to the effect/source itself where available.

Examples:

```text
Task mutation -> expected Task state_version
repo patch -> expected source/file/content hash
ProjectScope mutation -> expected scope generation
Run start -> stable logical request identity/hash
continuation-tracked effect -> expected continuation state_version
```

These are facts Soma understands without interpreting Sol's reasoning.

---

# 11. What Soma cannot guarantee

Without a model-owned runner or full conversation history, Soma cannot guarantee:

```text
Sol noticed every relevant fact
Sol used every relevant observation
Sol's reasoning is globally fresh
handoff text contains every useful thought
unregistered world state did not change
```

The architecture must say this plainly.

Soma can guarantee only its own mechanical invariants and durable records.

---

# 12. Potential simplification of the source registry

If semantic handoff is free-form, requiring Sol to maintain a detailed registry of every read dependency may also be unnecessary.

A future iteration should test whether fresh-Chat resumption really needs a general `continuation_sources` authority, or whether most useful state can be assembled from:

1. current controller contract revision;
2. latest free-form Sol handoff;
3. mechanically associated Tasks/Runs/effects;
4. current canonical statuses for those effects;
5. ordinary tool queries selected by fresh Sol after reading the handoff.

This could eliminate another source of model bookkeeping.

Do not remove `continuation_sources` yet; attack it separately.

---

# 13. Existing Soma precedent

Soma already contains inert external-coder handoff artifact machinery and atomic text/file writers.

Useful reusable mechanics:

- immutable/bounded artifact writing;
- content hashing/provenance;
- sensitivity/redaction handling;
- artifact references.

Do **not** reuse its current semantic routing/local-model summarization or detailed handoff field taxonomy for Sol continuation.

The useful precedent is the artifact boundary, not the old intelligence architecture.

---

# 14. Acceptance test for the semantic checkpoint

A handoff mechanism passes only if all of these are true:

1. Sol can write a checkpoint naturally without conforming to a semantic JSON taxonomy.
2. Soma does not need to understand handoff prose.
3. A fresh Sol can read it and recover the important thread.
4. Exact machine facts are separately available from canonical Soma authorities.
5. Repeated handoffs do not require schema changes when the task domain changes.
6. A simple project and a scientific/debugging/ops project can use the same storage contract while writing completely different handoff prose.
7. No handoff field becomes an executable next-step queue.

---

# 15. Verdict

**ACCEPT FREE-FORM SEMANTIC HANDOFF; REJECT STRUCTURED REASONING-STATE CAPSULE AS THE DEFAULT.**

The most promising boundary is now:

```text
Controller instruction history
    -> immutable text/artifact revisions + provenance

Sol semantic continuity
    -> one bounded opaque handoff text per checkpoint

Machine/external truth
    -> existing structured Task/Run/ProjectScope/repo/Knowledge/service authorities
```

This is much closer to the architecture used by successful agent runtimes:

- runner-owned exact context remains structured/runtime-owned;
- model-authored semantic compaction is human/agent-readable text;
- tools/world state remain machine-readable separately.

The next iteration should attack whether `continuation_sources` and explicit semantic source bookkeeping are necessary at all, or whether Soma can derive enough continuation context mechanically from canonical effect lineage plus the free-form handoff.
