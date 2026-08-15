# Iteration 25 - Remove Semantic Source Registry; Use Mechanical Effect Lineage

Date: 2026-08-15
Status: RESEARCH - simplification iteration
Track: Sol-centric agentic reasoning architecture
Builds on: Iteration 24 free-form semantic handoff

---

## Research question

Does v1 actually need a persistent `continuation_sources` registry and automatic source-delta reconciliation, or can fresh Sol recover effectively from a simpler combination of:

1. current controller contract;
2. latest free-form Sol handoff;
3. mechanically associated durable effects;
4. ordinary fresh tool reads selected by Sol?

The goal is to remove any state that requires Sol to classify its reasoning dependencies for Soma.

---

# 1. Why attack `continuation_sources`

The prior design asked Sol to register canonical sources as things such as:

```text
initiated_effect
evidence_reference
constraint_reference
resource_context
result_dependency
```

Even though the registry was intentionally mechanical and non-semantic, this still creates a model-bookkeeping burden:

```text
read source
reason about source
remember whether source should be registered
choose relation type
maintain registry as relevance changes
retire stale relations
```

This is dangerously close to the same pattern rejected in Iteration 24:

> ask the model to maintain a machine-readable representation of its cognitive context.

---

# 2. Source completeness is impossible anyway

A registry can never prove:

```text
all relevant world state is registered
```

Sol may forget a source.

A relevant external fact may change without any registered source changing.

A repository snapshot can return to the same state after transient edits.

A provider may expose only current state and no historical watermark.

Therefore automatic `registered_source_deltas` are useful only as a convenience, not as a correctness proof.

If the convenience requires significant model bookkeeping, it may not be worth the architecture.

---

# 3. Successful runner-owned systems do not require semantic dependency registries

Codex compaction preserves model-readable semantic context plus runner-owned history/context. The model is not required to publish a complete dependency graph of everything relevant to future reasoning.

OpenAI Agents SDK Sessions preserve conversation items because the runner owns them.

Claude Code resumes runner-owned sessions by ID.

Primary sources:

- OpenAI Codex compaction prompt/source
  - https://github.com/openai/codex/blob/main/codex-rs/prompts/templates/compact/prompt.md
  - https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs
- OpenAI Agents SDK Sessions
  - https://openai.github.io/openai-agents-python/sessions/
- Claude Code CLI session resume
  - https://code.claude.com/docs/en/cli-usage

Soma cannot preserve ChatGPT's hidden session, so it needs a handoff. But that does not imply it needs a model-maintained semantic source graph.

---

# 4. Separate two kinds of continuity evidence

## A. Semantic context

Owned by Sol handoff text.

Example:

```text
We are repairing Hedioum on Oracle. The binary was promoted but the service
still needs post-restart verification. Do not touch the websites. Relevant
repo is D:\Github\dnstm-setup; current production path is ...
```

Future Sol understands what matters from natural language.

## B. Effects Soma itself admitted/executed

These are mechanically knowable.

Examples:

```text
Task task_123
Run 20260815T...
repo patch transaction ...
Cloudflare action Run ...
SSH action Run ...
```

Soma can associate these with a continuation without asking Sol to classify them as reasoning dependencies.

---

# 5. Use existing continuation command/admission records as effect lineage

If an effect gateway is called with optional continuation association, the effect admission can mechanically record:

```text
continuation_id
gateway/operation
controller_request_id
canonical_effect_kind
canonical_effect_id
created_at
```

This can live in `continuation_commands` (or equivalent command/audit row) because it is a mutation/admission receipt.

No second `continuation_sources` row is required merely to remember that the effect happened under this continuation.

The canonical Task/Run remains the effect authority.

---

# 6. Resume can derive current effect state mechanically

Given continuation command/effect receipts, `resume` can mechanically produce a bounded section such as:

```text
associated_effects
  Task task_123 -> running
  Run run_456   -> completed, result available
  Run run_789   -> recovery_pending
```

This is useful because Soma owns the identities.

No Sol-authored source classification is required.

---

# 7. Read-only evidence should usually remain in handoff prose + normal tools

Suppose prior Sol inspected:

- a repository file;
- a Knowledge record;
- a server configuration;
- an external webpage;
- a log snippet.

There is little value in forcing every such read into a persistent source registry.

Instead prior Sol's free-form handoff can preserve the high-signal references it believes matter.

Fresh Sol then decides:

```text
which facts need re-reading?
which facts are stable enough to trust from handoff?
which current state should be checked before acting?
```

That is semantic judgment and belongs to Sol.

---

# 8. Machine references may be embedded naturally

The handoff can contain ordinary references such as:

```text
Task: task_123
Run: 20260815T...
Repo: D:\Github\Soma @ abc123
Doc: docs/foo.md
Knowledge: knowledge_id xyz
```

Soma does not need to parse these references to make the checkpoint valid.

Future Sol can read them as text and call the appropriate tools.

If later evidence shows automatic machine extraction of references materially improves recovery, add it as an optional convenience - not a semantic authority.

---

# 9. What about long-running effects created after the last handoff?

This is where mechanical effect lineage is stronger than prose.

Example:

```text
Capsule/Handoff C1 written
  -> Sol launches Run R1
  -> Chat disappears before another checkpoint
```

If the action gateway associated R1 with the continuation mechanically, fresh Sol can receive:

```text
prior handoff C1
+ associated effect R1 current state/result
```

without C1 needing to predict or encode the later result.

This solves the most important post-checkpoint continuity gap.

---

# 10. What about external changes not caused by Soma?

They are not automatically known.

That is acceptable and honest.

Fresh Sol uses the handoff and current objective to decide which world state needs reinspection.

Do not create watchers/global event buses merely to pretend Soma has complete environmental awareness.

---

# 11. Remove automatic delta semantics from the core

The prior architecture tried to compute:

```text
capsule frontier
vs
current registered source tokens
```

and return deltas automatically.

After Iteration 24, this is no longer necessary for core correctness.

A simpler resume bundle is:

```text
current_contract
latest_handoff_text
handoff_metadata
associated_effects + current canonical status
continuation lifecycle/history metadata
retrieval handles
```

Fresh Sol then uses ordinary Soma tools for any additional current-state checks.

This keeps semantic re-entry intelligent rather than attempting to precompute relevance mechanically.

---

# 12. Architecture simplification

Removing `continuation_sources` returns the minimal persistence candidate to four authorities, but **not** the old Iteration 10 four-table design.

Current candidate:

```text
1. controller_continuations
   identity/lifecycle/state_version
   current contract revision pointer
   latest handoff pointer

2. continuation_contract_revisions
   immutable controller instruction text/artifact revisions
   honest provenance

3. continuation_handoffs
   immutable free-form Sol handoff text
   basis contract revision
   hash/time

4. continuation_commands
   idempotency/CAS for continuation mutations
   mechanical effect-admission/link receipts
```

No `continuation_sources` table.

No `decision_basis` table/field requirement.

No observation acknowledgement.

No semantic dependency graph.

---

# 13. Effect association should be cheap

For a normal effect call under active continuation, the model should not have to submit a rich continuation object.

A future gateway design should aim for the smallest possible mechanical association, conceptually:

```text
continuation_id
```

plus only whatever request/idempotency fields the effect authority itself already needs.

Whether an expected continuation version is required for effect admission is **not settled here**; the next iteration must attack that separately because mandatory continuation CAS can conflict with legitimate parallel tool calls.

---

# 14. No inference that associated effect is semantically important forever

Effect association means only:

> this effect was initiated while pursuing this continuation.

It does not mean:

- effect remains relevant forever;
- effect controls continuation lifecycle;
- continuation owns the effect;
- terminal effect means objective complete;
- fresh Sol must inspect every historical effect in detail.

Resume should return a bounded recent/active/high-signal projection with deeper history retrievable by reference.

---

# 15. Retention / growth

Because effect lineage is mechanical, it may grow.

Do not solve this with semantic model classification.

Use ordinary mechanical policies:

- bounded recent list;
- always include active/nonterminal/recovery-pending effects;
- include terminal effects after latest handoff or within a bounded recent window;
- deeper history by cursor/reference.

No model-generated importance score.

---

# 16. Acceptance scenario

```text
1. Sol opens continuation with controller contract revision R1.
2. Sol works normally and writes free-form handoff H1.
3. Sol starts Run A associated with continuation.
4. Sol starts Task B associated with continuation.
5. Chat disappears.
6. A completes; B becomes recovery_pending.
7. Fresh Chat: owner says "continue".
8. Soma resume returns R1 + H1 + current A/B status.
9. Fresh Sol reads H1 and A/B state.
10. Fresh Sol independently queries repo/service/Knowledge facts that H1 says matter.
11. Fresh Sol continues reasoning.
```

No source registry is required.

---

# 17. Failure modes accepted honestly

Without source registry Soma cannot automatically tell fresh Sol that an arbitrary read-only source changed.

But the old registry could not prove completeness either.

The new design trades an incomplete convenience feature for:

- less model bookkeeping;
- less schema pressure;
- less false confidence;
- smaller persistence surface;
- more natural agent reasoning.

This is a favorable trade for v1.

---

# 18. Verdict

**REMOVE `continuation_sources` FROM THE V1 CORE CANDIDATE.**

Use:

```text
free-form Sol handoff
+
mechanically associated canonical effects
+
normal fresh tool inspection chosen by Sol
```

instead of a persistent semantic relevance/source registry.

The next iteration must attack the remaining controversial mechanism: whether every continuation-associated effect should be gated by `expected_continuation_version`, or whether that turns continuation into an unnecessary semantic serialization layer and breaks natural parallel tool use.
