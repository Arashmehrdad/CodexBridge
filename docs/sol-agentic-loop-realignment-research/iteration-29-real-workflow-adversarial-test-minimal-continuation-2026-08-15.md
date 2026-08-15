# Iteration 29 - Real-Workflow Adversarial Test of the Minimal Continuation Candidate

Date: 2026-08-15
Status: RESEARCH - adversarial workflow validation
Track: Sol-centric agentic reasoning architecture
Builds on: Iterations 24-28

---

## Research question

Does the minimal candidate from Iteration 28 survive realistic workflows of the kind the owner actually runs, without reintroducing structured reasoning state or making Soma harder to use?

Candidate under test:

```text
controller_continuations
continuation_contract_revisions
continuation_handoffs
continuation_effect_links
```

with:

```text
contract_revision_id as opaque continuation_context_ref
free-form handoff text
Task/Run effect lineage
no source registry
no decision_basis
no effect-level continuation CAS
no reasoning lock
```

---

# 1. Scenario A - interrupted Soma repository implementation

Representative pattern:

- Sol is implementing a multi-stage Soma roadmap item;
- repository may also be touched by another implementation thread;
- owner may pause/resume or move to a fresh Chat;
- commit/push boundaries and Codex authorization may be constrained by owner instruction;
- some repository mutations are durable Runs/repo transactions.

## Candidate behavior

Current contract revision R3 contains the active controller instruction text/artifact.

Sol checkpoint H7 is free-form and may say naturally:

```text
Current implementation is at X. Y passed. Z remains. Do not commit/push.
Another thread owns Company repair; do not touch its files. Repo is D:\Github\Soma.
Relevant evidence: patch/run IDs ...
```

Sol performs a repo mutation associated with R3.

Effect link records canonical Run/Task identity.

Fresh Chat resumes:

```text
R3 + H7 + linked effect current status
```

Fresh Sol then calls repo status/diff itself before deciding what to do.

## Result

PASS.

The absence of a source registry is beneficial here because repository state is inherently live and concurrent. Fresh Sol should inspect the actual repo rather than rely on precomputed semantic deltas.

---

# 2. Scenario B - long-running scientific Run

Representative pattern:

- Sol launches an Axon/PneumoniaMNIST experiment;
- the Run outlives current Chat interaction;
- owner later returns with "check" or "continue";
- scientific interpretation depends on terminal result/evidence, not merely process completion.

## Candidate behavior

Sol has current context ref R2.

A durable Run is started with optional association to R2.

`continuation_effect_links` records Run R.

Chat disappears.

When fresh Sol resumes, Soma can mechanically show:

```text
Run R -> running/completed/failed/recovery_pending
result publication state
retrieval handle
```

Sol then decides whether to inspect result, logs, artifacts, scientific evidence, or rerun anything.

No handoff schema needs fields for model accuracy, test metrics, GPU parameters, or scientific hypotheses.

## Result

PASS, **conditional on direct Run request-idempotency/effect-link reservation being made crash-safe as identified in Iteration 19.**

---

# 3. Scenario C - remote service repair

Representative pattern:

- Sol changes a service through SSH/Cloudflare/Docker/run gateway;
- effect is durable Run-backed;
- remote world can change independently afterward;
- fresh Sol must verify current service state before further mutation.

## Candidate behavior

Handoff records semantic context in natural prose.

Associated effect link identifies the canonical durable Run.

Resume shows what Soma knows about the effect.

Fresh Sol explicitly calls current service/SSH/provider inspection tools before reasoning about the next operation.

No persistent source registry tries to claim complete remote-world awareness.

## Result

PASS.

This is more honest than source-token delta machinery because remote state can change outside Soma.

---

# 4. Scenario D - owner changes instruction mid-work

Example:

```text
R3: "repair Hedioum; do not touch websites"
```

Later owner changes direction and Sol records:

```text
R4: updated controller instruction
```

R4 becomes current.

An old Chat still holding R3 attempts a **continuation-associated** effect.

## Candidate behavior

R3 is submitted as continuation context ref.

Soma resolves R3 -> continuation K and sees:

```text
K.current_contract_revision_id = R4
```

Reject mechanically:

```text
stale_continuation_context
```

## Result

PASS for associated effects.

## Important limitation

If old Sol omits the continuation context ref and calls an ordinary gateway directly, Soma cannot infer that the call belongs to K or that Sol is acting under R3.

Therefore the context-ref guard is **not a security boundary** and must never be described as one.

It is a continuity/provenance/stale-contract feature for calls that participate in continuation association.

This limitation is fundamental unless ChatGPT exposes a trustworthy automatic conversation/continuation binding to Soma or Soma introduces a separate mandatory context-bound execution surface.

No such mandatory wrapper is justified for v1.

---

# 5. Scenario E - fresh Chat receives only "continue"

Assume several projects may exist, but one continuation is clearly the most recent/relevant.

## Candidate behavior

Sol lists open continuations and receives bounded discovery hints:

```text
continuation id
label
state
current contract revision
last handoff time
active/recovery effect counts
```

If one is obvious, Sol resumes it.

Resume returns:

```text
current context ref
controller instruction text/ref
latest free-form handoff
the contract revision that handoff was written under
contract_changed_since_handoff flag
associated Task/Run statuses
retrieval refs
```

Sol reasons and performs any fresh inspections needed.

## Result

PASS.

If several continuations are genuinely ambiguous, owner clarification is legitimate. No local semantic router is required.

---

# 6. Scenario F - multiple unrelated projects simultaneously

Two or more continuations exist for independent repos/projects.

## Candidate behavior

Continuation metadata operations use only short local DB transactions.

No repository mutation lock is acquired for:

- reasoning;
- handoff write;
- contract revision;
- resume/list;
- effect-link read.

Concrete effects keep their existing Task/Run/repo/resource locking.

## Result

PASS.

No global reasoning lock and no project-wide semantic scheduler is introduced.

---

# 7. Scenario G - two Sol branches under same current contract

Both branches hold current context R5.

Both reason and perform associated effects.

## Candidate behavior

Both effects may proceed if their underlying canonical authorities permit them.

Continuation does not decide which Sol is smarter/current.

If they conflict mechanically:

- repo lock/hash may reject/serialize;
- Task state version may reject;
- Run request identity may replay/conflict;
- ProjectScope/resource authority may reject.

## Result

PASS as an intentional architecture property.

This avoids falsely treating reasoning branches as corruption.

---

# 8. Scenario H - repeated checkpoints and semantic drift

H1 -> H2 -> H3 over a long objective.

Free-form handoffs may still lose detail over repeated summarization.

## Candidate mitigation

The governing controller contract is separate and immutable by revision.

All prior handoffs remain immutable/retrievable.

Checkpoint guidance tells Sol to write a fresh handoff from current live context plus prior references as useful, not mechanically summarize the previous handoff.

Stable reusable facts/decisions belong in canonical Knowledge by explicit promotion.

Resume may expose a bounded handoff history reference if latest handoff appears insufficient.

## Result

PASS with residual model-quality risk.

No schema can eliminate this risk without recreating the failed structured-reasoning approach.

Real acceptance testing must measure whether fresh Sol can actually continue.

---

# 9. Scenario I - Sol forgets to associate an effect

Sol starts a durable effect but omits the continuation context ref.

## Consequence

Effect executes normally under canonical Soma authority.

No continuation effect link is created.

Fresh Sol will not automatically see this effect in the continuation resume bundle unless the handoff or other evidence points to it.

## Can Soma fix this automatically?

Not reliably.

Soma does not receive a documented trustworthy ChatGPT thread/continuation identity with every MCP call that would let it infer association.

Inferring from repo/resource/time would be unsafe under multi-project/concurrent use.

## Correct treatment

Treat effect association as a **best-effort continuation convenience**, not a capability/security requirement.

Model guidance can strongly prefer passing the current context ref for durable effects while an active continuation is being pursued.

Because the burden is one opaque scalar rather than a structured semantic object, this is acceptable for v1.

## Result

PASS with explicit limitation.

---

# 10. Scenario J - effect link crash gap

Dangerous sequence:

```text
canonical Run/Task created
 -> process crashes
 -> continuation link not written
```

This recreates a discovery gap.

## Required strong path

For continuation-associated Task/Run starts, canonical effect reservation and `continuation_effect_links` insertion should happen in the same local SQLite transaction where architecture permits.

For Task, existing connection-scoped reservation seams provide a precedent.

For direct Run, Iteration 19's planned request-idempotent reservation seam should be designed to permit the same transaction or an equivalently recoverable relation.

Worker/effect launch occurs after the durable identity/link commit.

## Result

**MATERIAL IMPLEMENTATION REQUIREMENT.**

The four-table architecture remains valid, but strong effect continuity depends on this atomic reservation/link seam.

---

# 11. Scenario K - Run response lost

Sol requests direct Run R and the response disappears after durable creation.

## Without Iteration 19 enhancement

Retry may create/attempt another Run or require recent-run guessing.

## With stable Run logical request ID/hash

Retry returns existing canonical Run.

Effect link can also be replayed/verified deterministically.

## Result

**Run request idempotency remains required before calling direct Run continuation association crash-safe.**

---

# 12. Scenario L - handoff write fails

Checkpoint free-form text is submitted but DB write fails.

## Behavior

No partial handoff should become visible.

Prior handoff remains latest by sequence.

Sol may retry the same checkpoint request ID/hash and receive the same created handoff if first commit actually succeeded.

Each handoff row therefore needs its own request identity/hash replay behavior.

No generic continuation command journal is necessary.

## Result

PASS.

---

# 13. Scenario M - contract revision write fails

R4 is submitted to replace R3.

## Required transaction

In one short DB transaction:

```text
validate R3 is current
create immutable R4
move continuation current pointer to R4
```

Crash gives either:

```text
R3 remains current
```

or:

```text
R4 exists and is current
```

never an orphan accepted contract that the root forgot to select.

Request replay returns R4 if already committed.

## Result

PASS.

---

# 14. Scenario N - contract changes while old long effect remains active

Run R was initiated under R3.

Owner records R4 while R is still running.

## Candidate behavior

Do not auto-cancel R.

Effect link permanently records origin contract revision R3.

Resume under R4 shows R still active and its origin context.

Sol/owner decides whether R should continue/cancel/be ignored.

## Result

PASS.

This preserves authority separation.

---

# 15. Scenario O - current contract is new but latest handoff is old

R3 + H3 exist.

Owner changes to R4 but no new Sol checkpoint exists yet.

## Resume must show

```text
current contract = R4
latest handoff = H3
handoff contract = R3
contract_changed_since_handoff = true
```

Fresh Sol must reconcile before following H3's old plan.

## Result

PASS.

This is one of the strongest reasons to keep contract and handoff separate.

---

# 16. Formatting regression test

Ask: what special semantic structure must Sol produce during these workflows?

Answer:

```text
contract change -> one free-form instruction text/ref
checkpoint -> one free-form handoff text
tracked effect -> one opaque context ref
```

No task-specific JSON semantic taxonomy is required.

## Result

PASS.

This is a major improvement over the historical Agent/Worker design and over Iterations 16-23.

---

# 17. Remaining failure classes

The minimal architecture intentionally does not solve:

1. Sol semantic mistakes;
2. omitted continuation association;
3. world changes Sol does not inspect;
4. exact ChatGPT hidden-state resume;
5. semantic merge of two concurrent Sol branches;
6. automatic wake-up;
7. universal distributed transaction across remote providers.

Attempting to solve these in v1 would require either intelligence Soma does not have or invasive orchestration the owner does not want.

---

# 18. Material findings

## Finding A - context association is not an enforcement/security boundary

A valid architecture must stop saying or implying:

> Soma prevents all stale old Chat effects.

Correct statement:

> For continuation-associated calls, Soma can reject a context ref tied to a superseded governing contract. Calls that omit continuation association remain ordinary Soma calls governed by their normal authority.

## Finding B - atomic effect reservation/link is the main new durability seam

The architecture is simple, but implementation must make Task/Run identity plus continuation origin relation durable before launch where strong continuity is claimed.

## Finding C - direct Run idempotency is general infrastructure, not continuation cognition

Add it to Run authority because it improves all durable Run callers.

## Finding D - semantic quality must be tested empirically

The free-form handoff cannot be validated by a schema.

The real test is fresh Sol successfully continuing representative owner workflows.

---

# 19. Adversarial verdict

**THE MINIMAL FOUR-AUTHORITY CANDIDATE SURVIVES REAL-WORKFLOW ATTACK WITH TWO EXPLICIT INFRASTRUCTURE REQUIREMENTS AND ONE HONEST LIMITATION.**

Infrastructure requirements:

1. stable request-id/hash replay for direct Run creation;
2. atomic/recoverable Task/Run reservation + continuation effect-link relation before launch for associated effects.

Honest limitation:

3. continuation context association is best-effort/model-supplied and cannot govern calls that omit it.

None of these require structured reasoning output or a Soma reasoning engine.

---

# 20. Recommended next research step

One final synthesis should supersede Iteration 16 and the intermediate 18-23 candidate architecture with the simplified result from 24-29.

That synthesis should freeze only:

```text
Sol = semantic reasoning authority
Soma = agent interface + durable semantic re-entry
contract revisions = free-form governing controller text/history
handoffs = free-form Sol engineering handoff text
context ref = current contract revision identity
effect links = mechanical Task/Run origin lineage
Run idempotency = canonical Run infrastructure
no source registry
no decision basis
no effect-level continuation CAS
no reasoning lock
no semantic parser
```

Implementation planning should not begin from older iteration details after this final synthesis is accepted.
