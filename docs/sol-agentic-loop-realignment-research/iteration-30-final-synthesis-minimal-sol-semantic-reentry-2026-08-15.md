# Iteration 30 - Final Synthesis: Minimal Sol Semantic Re-entry Architecture

Date: 2026-08-15
Status: FINAL RESEARCH SYNTHESIS - implementation planning may follow only on owner approval
Track: Sol-centric agentic reasoning architecture
Supersedes for implementation authority: Iteration 16 and the intermediate architectural candidates from Iterations 18-23
Historical research remains preserved and should not be rewritten.

---

# Executive conclusion

The research has converged on a substantially simpler architecture after repeated adversarial attack and after applying the owner's historical warning about failed model-formatting/schema approaches.

The final principle is:

> **Sol/ChatGPT is the reasoning agent. Soma should provide tools, durable external truth, effect identity/recovery, and a very small semantic re-entry layer. Soma must not require Sol to serialize its reasoning into a machine-readable cognitive schema.**

The target is:

```text
USER / OWNER
     |
     v
SOL / CHATGPT
adaptive reasoning
     |
     +---- ordinary Soma reads/effects ----+
     |                                      |
     v                                      v
SOMA AGENT INTERFACE                 canonical world/effect truth
                                     Task / Run / repo / service /
                                     ProjectScope / Knowledge

When fresh-context continuity matters:

SOL writes one free-form handoff
Soma preserves it + governing instruction revision
Soma mechanically links durable Task/Run effects when asked
Fresh Sol receives those facts and reasons again
```

There is no Soma reasoning algorithm.

There is no Task loop.

There is no semantic planner.

There is no model-maintained evidence graph.

---

# 1. Why earlier replacement architectures were still too complicated

The first Agent/Worker correction correctly restored Sol as reasoning authority, but subsequent designs still tried to make Soma understand too much about the reasoning process.

Examples that have now been rejected from the core:

```text
structured ContinuationCapsule semantic fields
incorporated_frontier
continuation_sources
source roles
decision_basis
pending effect intents
effect-level continuation CAS
last_consumed_observation_hash
ack_observations
reason/act/observe persisted phases
```

The common mistake was subtle:

> taking information useful to Sol and turning it into a schema Soma expected Sol to maintain correctly.

The owner correctly identified this as the same failure family as the old Agent/Worker implementation plan, which repeatedly added increasingly strict model-produced contracts and formatting without solving the semantic problem.

---

# 2. External agent-runtime evidence

## OpenAI Codex

Current Codex compaction asks the model for a concise human/agent-readable handoff summary, not a detailed machine-readable cognition object.

The Codex runner separately preserves real user messages and canonical initial context around the compaction summary.

Primary sources:

- https://github.com/openai/codex/blob/main/codex-rs/prompts/templates/compact/prompt.md
- https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs

This gives the key pattern:

```text
runner-owned/mechanical state remains structured
+
model-authored semantic continuity remains natural language
```

## OpenAI Agents SDK

The Agents SDK can serialize exact `RunState` and preserve Sessions because it owns the runner/history boundary.

Primary sources:

- https://openai.github.io/openai-agents-python/ref/run_state/
- https://openai.github.io/openai-agents-python/sessions/

Soma normal Chat does not own that boundary, so it should not pretend it can reconstruct it from model-generated JSON.

## Claude Code / Gemini

Claude Code uses opaque session IDs for resume/fork.

Gemini stateful Interactions uses an opaque `previous_interaction_id` while the server carries the detailed hidden conversation/tool/thought linkage.

Primary sources:

- https://code.claude.com/docs/en/sessions
- https://code.claude.com/docs/en/agent-sdk/sessions
- https://ai.google.dev/gemini-api/docs/interactions-overview
- https://ai.google.dev/gemini-api/docs/thought-signatures

The transferable interface lesson is:

> give the model a small opaque context handle; keep machine state behind that handle.

Soma cannot provide exact model-runtime continuation, but it can use the same interface discipline for Soma-owned semantic re-entry state.

---

# 3. Final authority split

## Sol owns

```text
interpretation
investigation strategy
what evidence matters
planning/replanning
whether to call zero/one/many tools
semantic validation
whether to ask owner
whether to use a bounded specialist
whether objective is complete
```

## Soma owns

```text
capability/tool contracts
durable Task/Run identity
effect execution/recovery
repository/service/machine access
ProjectScope/resource authority
request idempotency where implemented
mechanical hashes/versions
controller instruction revisions it was given
free-form handoff bytes it was given
effect-origin links it recorded
```

Soma never decides whether Sol's reasoning is stale or correct.

---

# 4. The final v1 continuation kernel: four boring authorities

```text
1. controller_continuations
2. continuation_contract_revisions
3. continuation_handoffs
4. continuation_effect_links
```

No fifth semantic/source/event table is required for v1.

---

# 5. `controller_continuations`

Purpose:

- durable identity;
- lifecycle/discovery;
- current governing contract pointer.

Conceptual fields only:

```text
continuation_id
safe label
state = open | completed | cancelled
current_contract_revision_id
creation_request_id
creation_request_hash
created_at
updated_at
closed_at?
closure request metadata if needed
```

Deliberately absent:

```text
reasoning phase
model/provider identity
next step
next Task
plan graph
source frontier
repository lock
ChatGPT conversation ID
semantic scheduler state
```

No repo mutation lock is acquired by continuation existence/read/write.

---

# 6. `continuation_contract_revisions`

Purpose:

> preserve the governing controller instruction history independently from Sol's evolving interpretation.

Conceptual fields:

```text
contract_revision_id
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

The instruction is primarily bounded free-form text/artifact, not a schema forcing Sol to classify:

```text
objective
constraints[]
exclusions[]
authorization[]
done_criteria[]
```

unless a future specific mechanical feature truly requires one of those fields.

Provenance must be honest.

Soma may say:

```text
controller_submitted_text
owner_confirmed_artifact
external_authority_ref
```

but must not claim `owner_exact` merely because Sol submitted text to Soma.

---

# 7. Contract revision identity is the model-facing continuation context ref

No separate context-token table is needed.

The immutable `contract_revision_id` itself is already an opaque context handle.

Public tools may expose it under a friendlier name:

```text
continuation_context_ref
```

Soma resolves it to the continuation and checks whether it is still the current governing revision.

This follows the opaque session/interaction handle pattern without pretending to resume hidden model state.

---

# 8. `continuation_handoffs`

Purpose:

> store one bounded free-form engineering handoff authored by Sol/owner for future Sol.

Conceptual fields:

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

`handoff_text` is opaque to Soma.

Soma may validate:

- size;
- UTF-8;
- sensitivity/secret handling;
- identity/hash;
- request replay;
- current contract context at checkpoint time.

Soma does not parse it into semantic fields.

---

# 9. Handoff prompt principle

Checkpoint guidance may say approximately:

> Write a concise engineering handoff for another Sol. Preserve what matters to continue: current situation, important decisions/constraints, unfinished work, critical references and uncertainty. Use whatever structure makes this task easiest to resume.

This is guidance, not a parser contract.

No required headings.

No arrays/enums for reasoning content.

No schema version treadmill when a new task domain needs different handoff content.

---

# 10. Handoff is not chain-of-thought

The handoff contains explicit operational context useful to another competent agent/engineer.

It does not require or store:

```text
private chain-of-thought
scratchpad
token-by-token reasoning
hidden model state
```

---

# 11. `continuation_effect_links`

Purpose:

> mechanically remember durable Task/Run effects initiated while pursuing a continuation, especially effects created after the latest semantic handoff.

Conceptual v1 fields:

```text
link_id
continuation_id
contract_revision_id
effect_kind = task | run
effect_id
created_at
```

Optional safe mechanical metadata may identify gateway/operation/request identity.

The link means only:

> effect E originated while pursuing continuation K under contract revision R.

It does not mean:

- continuation owns E;
- E is semantically important forever;
- E is a dependency;
- E should be cancelled when continuation changes;
- E completion advances a reasoning stage;
- E completion means objective completion.

---

# 12. Why no `continuation_sources`

A model-maintained source registry was rejected because:

- it requires Sol to classify/maintain reasoning dependencies;
- it cannot prove completeness anyway;
- external world changes can occur outside registered sources;
- live snapshots cannot prove no transient change;
- fresh Sol is better placed to decide which current facts require reinspection.

Resume therefore does **not** pretend to return all world changes.

Fresh Sol reads the handoff and calls normal tools to inspect current world state as needed.

---

# 13. Why no `decision_basis`

Soma cannot know whether Sol listed all evidence that mattered to its reasoning.

A required `decision_basis` recreates the failed formatting pattern:

- under-listing creates false confidence;
- over-listing creates needless stale errors;
- schema design must predict cognition categories;
- model budget is spent formatting reasoning for Soma.

Therefore effect safety uses only mechanical preconditions the **effect authority itself** understands.

Examples:

```text
Task mutation -> if_state_version
repo patch -> expected preview/content hash
ProjectScope -> exact generation/binding
Run start -> logical request identity/hash
provider resource update -> provider-native version/etag if available
```

No claim of stale-reasoning detection.

---

# 14. No effect-level continuation CAS

Continuation state/version is not a proxy for reasoning freshness.

Mandatory continuation CAS on every effect would:

- serialize legitimate parallel tool calls;
- require batch-intent protocols;
- turn semantic continuity into an execution lock;
- make reasoning branches look like corruption.

Therefore several effects may be initiated under the same current contract revision.

Several Sol branches may also act under the same current contract.

Underlying resource/effect authorities handle actual mechanical conflicts.

---

# 15. Current contract guard for associated effects

For a **continuation-associated** effect, Sol supplies the current opaque `continuation_context_ref` (the contract revision ID).

Soma mechanically verifies:

```text
revision exists
continuation is open
revision belongs to continuation
revision == continuation.current_contract_revision_id
```

If the controller contract changed:

```text
stale_continuation_context
```

This is a real deterministic property.

But it must be described correctly.

---

# 16. Important limitation: context association is not a security boundary

Soma cannot know that an arbitrary ordinary tool call belongs to a continuation if Sol omits the context ref.

No documented trustworthy ChatGPT conversation/continuation identity is currently available to Soma on every MCP call for automatic binding.

Therefore:

> The stale-contract check applies only to continuation-associated calls.

An ordinary call without continuation association remains governed by normal Soma authorization/resource rules.

Do not claim Soma can prevent every old Chat from acting.

Do not infer continuation association from repo/time/resource because concurrent projects/Chats are legitimate.

---

# 17. Model-facing burden is intentionally tiny

During normal continuation use Sol needs only:

```text
checkpoint:
  current context_ref
  free-form handoff_text

tracked durable effect:
  normal effect arguments
  optional current context_ref

contract update:
  current context_ref
  new free-form controller instruction text/ref
```

No semantic reasoning JSON.

This is the central usability invariant.

---

# 18. Normal fast path remains unchanged

Most work should still be:

```text
Sol -> existing Soma tool -> result -> Sol
```

No continuation is required for every read/action.

No checkpoint after every observation.

No source registration after every read.

Continuation is used when fresh-context recovery would be valuable.

---

# 19. Resume bundle

A minimal fresh-context response should contain clearly separated mechanical/semantic material:

```text
continuation
  id / label / lifecycle

continuation_context_ref
  current contract revision identity

controller_instruction
  current free-form contract text/ref
  provenance label

sol_handoff
  newest free-form handoff text
  its contract revision
  timestamp

contract_changed_since_handoff
  mechanically true/false

associated_effects
  bounded Task/Run links with current canonical status/result/recovery hints

retrieval
  deeper handoff/effect history refs
```

No `recommended_next_action` from Soma.

No source-delta engine.

Sol decides what to inspect next.

---

# 20. Contract changed after latest handoff

If latest handoff H3 was authored under R3 and owner direction is now R4:

```text
current_contract = R4
handoff_contract = R3
contract_changed_since_handoff = true
```

Fresh Sol must reconcile instead of blindly following H3.

This is one of the most useful deterministic continuation facts Soma can provide.

---

# 21. Concurrent handoffs

Handoffs are immutable and sequence-numbered.

If two branches publish close together, preserve both.

Resume may return newest plus bounded history indication.

Do not infer semantic supersession simply because one has a larger sequence number.

Do not build a branch graph in v1.

---

# 22. Multi-project concurrency

Hard invariants remain:

- reasoning never takes repo mutation lock;
- resume/list/handoff/contract metadata writes never take repo mutation lock;
- unrelated projects remain concurrent;
- same-repo reads/reasoning remain concurrent;
- only actual side effects use existing resource/repo locking;
- local continuation DB transactions remain short;
- never hold DB transaction while Sol reasons, owner waits, remote provider responds, or worker executes.

---

# 23. Direct Run request idempotency is required general infrastructure

Current canonical Task start already has strong controller request identity/hash replay semantics.

Direct durable Run start should gain an equivalent general capability:

```text
logical_run_request_id
normalized_request_hash
```

Behavior:

```text
new request ID -> reserve/create one Run
same ID + same hash -> return existing Run, no relaunch
same ID + different hash -> conflict
```

This should be a general RunStore/JobManager improvement, not continuation-only middleware.

It fixes lost-response duplicate-launch risk everywhere.

---

# 24. Associated effect reservation/link must be durable before launch

Where strong continuation effect lineage is claimed:

```text
validate current contract ref
reserve canonical Task/Run identity
insert continuation_effect_link
commit
launch existing backend
```

The effect link and canonical identity should be atomically/recoverably durable before external worker/effect execution.

Task already has connection-scoped reservation precedents.

Direct Run needs the Iteration 19 reservation/idempotency enhancement to support an equally strong path.

No new executor is introduced.

---

# 25. Effect link omission remains recoverable but not automatic

If Sol forgets to pass the context ref:

- effect runs normally;
- no continuation effect link exists;
- fresh Sol may still discover it from handoff/repo/run inspection;
- Soma must not guess association from time/repo similarity.

This is an accepted v1 limitation.

The one-scalar burden is small enough to test empirically rather than building a mandatory wrapper.

---

# 26. Work architecture

No change.

ChatGPT Work already owns its own model runner/context/subagent orchestration.

Default:

```text
Work/Sol -> existing Soma tools directly
```

Use Soma continuation only for explicit cross-context/cross-surface durability if desired.

No Work mode detector is required.

---

# 27. Specialist/provider architecture

No change.

Optional reasoning/provider workers remain bounded specialist capabilities only.

They are not:

- required for continuation;
- automatic fallback;
- default checkpoint writer;
- semantic owner.

Codex use remains explicit owner-authorized where that owner gate applies.

---

# 28. Company architecture

Company remains separate.

Its Mission/PlanRevision/WorkPackage/Outcome/Acceptance records are organizational commitments.

Normal Chat continuation is lightweight active-objective semantic re-entry.

Do not use Company plan machinery for normal handoffs.

---

# 29. Long-term Knowledge

Knowledge remains separate.

Use it for accepted durable reusable facts/decisions/preferences/lessons.

Do not automatically parse handoff text into Knowledge.

Stable information may be promoted by explicit Sol/owner semantic action.

---

# 30. Things explicitly removed from implementation authority

Do not implement from older iterations:

```text
ControllerLoop
structured reasoning-state capsule
controller_continuation_tasks
continuation_sources
source roles/frontiers
decision_basis
pending effect intent table
continuation_effect_intents
ack_observations
last_consumed_observation_hash
Task-only observation fingerprint
effect-level expected_continuation_version CAS
reasoning lease/single-writer lock
semantic scheduler
next_step / next_stage
reasoning worker as default brain
```

---

# 31. Minimal persistence deletion test

## Remove continuation root

Lose lifecycle/discovery/current contract pointer.

Keep.

## Remove contract revisions

Lose governing-direction history and stale-context detection.

Keep.

## Remove handoffs

Lose semantic fresh-context re-entry.

Keep.

## Remove effect links

Lose mechanical discovery of durable effects launched after latest handoff.

Keep.

Four concerns survive adversarial deletion.

---

# 32. Implementation planning sequence recommendation

This is research guidance, not implementation authorization.

## Phase 0 - authority freeze

- accept Iteration 30 as implementation-planning authority;
- explicitly mark Iteration 16/18-23 architecture details superseded;
- preserve historical research;
- protect concurrent repo work.

## Phase 1 - general direct Run idempotency

- add logical Run request ID/hash replay semantics;
- preserve existing Run ID as canonical effect identity;
- prove no duplicate launch after lost response/retry;
- make reservation connection-scoped if needed for atomic linking.

This is useful independently of continuation.

## Phase 2 - internal continuation persistence

Implement only:

```text
controller_continuations
continuation_contract_revisions
continuation_handoffs
continuation_effect_links
```

No public semantic parser.

## Phase 3 - read/open/resume/checkpoint/contract update

- open continuation with first contract revision;
- immutable free-form checkpoint;
- resume bundle;
- lifecycle close/cancel;
- request replay per immutable record.

## Phase 4 - Task effect association

- optional `continuation_context_ref` on appropriate Task starts;
- current contract guard;
- atomic Task reservation + effect link;
- no effect-level continuation CAS.

## Phase 5 - Run effect association

After Phase 1:

- optional context ref on appropriate durable Run starts;
- atomic/recoverable Run reservation + effect link;
- replay same logical Run request safely.

## Phase 6 - normal Chat guidance

Teach only the small UX:

- fast path normally;
- create/checkpoint continuation only when continuity matters;
- handoff is free-form;
- carry current context ref for tracked durable effects;
- resume then inspect current world state as needed;
- never treat handoff as current world truth.

## Phase 7 - real fresh-Chat acceptance

Test actual owner workflows.

Do not declare success from unit tests alone.

---

# 33. Mechanical acceptance tests

## Contract revisions

- immutable revision history;
- request replay/conflict;
- atomic current pointer update;
- old context ref rejected for associated checkpoint/effect;
- provenance labels honest.

## Handoffs

- arbitrary valid free-form text accepted within bounds;
- no required headings/semantic fields;
- immutable hash integrity;
- request replay/conflict;
- sequence ordering;
- contract revision recorded;
- secret/sensitivity boundary.

## Effect links

- Task/Run identity validated;
- link durable before launch where supported;
- no copied effect state;
- current status resolved from canonical authority;
- contract origin retained after later contract revisions;
- omission of association does not break ordinary gateway.

## Run idempotency

- same logical request ID + same hash -> same Run;
- same ID + different hash -> conflict;
- concurrent identical requests -> one Run;
- lost response retry -> no duplicate worker launch.

## Concurrency

- parallel associated effects under same current contract allowed;
- no continuation reasoning lock;
- unrelated repos/projects concurrent;
- actual repo/resource conflicts remain under existing authority.

---

# 34. Mandatory semantic acceptance tests

The feature exists for model continuity, so test with fresh Sol.

At minimum:

## A. interrupted repository implementation

Fresh Chat must recover enough to inspect current repo and continue without owner reconstructing history.

## B. long-running scientific Run

Fresh Chat must identify the linked Run/current result state and continue scientific reasoning.

## C. remote service repair

Fresh Chat must recover prior effect lineage, then independently verify current remote state before further action.

## D. controller contract change

Fresh Chat must see new contract + old handoff mismatch and not blindly follow the old handoff.

## E. free-form handoff variability

Use very different domains without changing the handoff schema.

The architecture fails if success requires adding semantic fields for each new workflow.

---

# 35. Product acceptance test

Desired normal-Chat experience:

```text
owner: work on this
Sol: works normally with Soma

[when continuity risk becomes meaningful]
Sol: writes one short handoff

[durable effects]
Sol: ordinary tool call + one opaque context ref when useful

[later, fresh Chat]
owner: continue
Sol: resumes contract + handoff + linked effect status
Sol: inspects current world state as needed
Sol: continues reasoning
```

If the owner has to manually manage IDs, sources, evidence arrays, plans or continuation stages, the design has failed.

---

# 36. What Soma can honestly promise

Soma can promise:

```text
I preserved the controller instruction revision I was given.
I preserved Sol's handoff text exactly.
I can tell whether that context revision is still current.
I can show canonical Task/Run effects mechanically linked to it.
I can show current truth from those effect authorities.
I can preserve/replay durable Run starts once Run idempotency is implemented.
```

Soma cannot promise:

```text
Sol reasoned correctly.
Sol included every important fact in the handoff.
Sol associated every effect.
no relevant unobserved world state changed.
this is the exact hidden ChatGPT runtime state.
```

This honesty boundary is a feature, not a deficiency.

---

# 37. Final terminology

## Sol reasoning trajectory / reasoning loop

Adaptive cognition owned by Sol.

## Continuation

Soma-owned durable identity for one active objective that may need semantic re-entry.

## Contract revision / continuation context ref

Immutable governing controller instruction revision. Its opaque ID is the current model-facing continuation context reference.

## Handoff

Free-form bounded engineering note authored for future Sol. Opaque to Soma. Not chain-of-thought.

## Effect link

Mechanical origin relation from continuation/contract revision to canonical Task/Run effect.

## Task / Run

Canonical external-work authorities. Not the reasoning loop.

---

# 38. Final research verdict

**RESEARCH CONVERGED ON A MINIMAL SOL SEMANTIC RE-ENTRY ARCHITECTURE.**

The strongest current design is:

```text
SOL reasons normally

SOMA provides:
  four small continuation authorities
  one opaque current context reference
  one free-form handoff channel
  mechanical Task/Run lineage
  existing world/effect tools
  general Run idempotency/recovery
```

This architecture specifically avoids repeating the previous Agent/Worker failure mode of trying to make model intelligence reliable by forcing it into increasingly strict semantic formats.

Iteration 30 supersedes Iteration 16 and intermediate Iterations 18-23 for implementation-planning authority.

Iterations 24-29 provide the corrective evidence and adversarial path leading to this synthesis.

Implementation itself remains unauthorized by this research document.
