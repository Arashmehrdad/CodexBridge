# Iteration 7 - Specialist Boundaries and Atomic Loop-to-Task Ownership

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected: `fef45702367ecf1015a1ab95139547f172ab588f`

## Scope

Iteration 6 showed that most Agent/Worker mechanics are reusable lower-level infrastructure, while semantic routing/planning and the treatment of a reasoning worker as a core cognitive actor are the main drift.

Iteration 7 addresses two remaining high-risk seams:

1. **When is any subordinate specialist/subagent justified at all?**
2. **How can the lightweight normal-Chat Sol loop own canonical Tasks atomically without creating another Task launcher?**

The purpose is to stop optional specialist capability from creeping back into the core architecture and to prove that the minimal loop can attach to existing Task infrastructure cleanly.

No implementation is authorized.

## Hard constraints

No runtime/service restart, Company activation, reasoning-provider activation, Codex use, provider generation, production config change, push, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

Company remains frozen.

Codex remains owner-authorized only.

Manual Chat wake-up remains the baseline. PulseSender/browser delivery is outside the cognitive architecture.

Classification labels:

- **DOCUMENTED FACT** - current official OpenAI documentation.
- **REPOSITORY FACT** - current Soma source/docs/history evidence.
- **OWNER REQUIREMENT** - explicit owner direction.
- **INFERENCE** - supported architectural conclusion, not implementation authority.
- **OPEN QUESTION** - intentionally unresolved.

---

# 1. Official OpenAI boundary: subagents are an optimization for independent work

## 1.1 ChatGPT Work and Codex own their subagent orchestration

**DOCUMENTED FACT**

Current OpenAI Subagents documentation says ChatGPT Work and Codex can run subagent workflows by spawning specialized agents in parallel and collecting their results into one response.

It further states:

- Work subagents run in ChatGPT's hosted environment;
- ChatGPT/Codex handles spawning, routing follow-up instructions, waiting for results, and closing agent threads;
- the main thread collects/consolidates the results;
- subagents consume more tokens than comparable single-agent work.

Source:

- OpenAI / ChatGPT Learn, `Subagents`: https://learn.chatgpt.com/docs/agent-configuration/subagents

## 1.2 Best-fit tasks are independent and read-heavy

**DOCUMENTED FACT**

OpenAI recommends subagents for work that can be split into bounded independent pieces and specifically gives examples such as:

- exploration;
- tests;
- triage;
- log analysis;
- summarization;
- large-document/codebase scans.

OpenAI says subagents can reduce context pollution by moving noisy intermediate work off the main thread and returning distilled results.

The same documentation recommends starting with read-heavy parallel work and being more cautious with parallel write-heavy workflows because simultaneous edits create conflicts and coordination overhead.

## 1.3 API model guidance makes the same “fresh judgment” distinction

**DOCUMENTED FACT**

Current GPT-5.6 model guidance distinguishes:

- Programmatic Tool Calling for bounded tool-heavy workflows that do **not** need fresh model judgment between each step;
- Multi-agent for independent parallel workstreams;
- direct model/tool interaction where intermediate results materially affect the next decision.

Source:

- OpenAI API, `Model guidance`: https://developers.openai.com/api/docs/guides/latest-model

## 1.4 Architectural implication

**INFERENCE**

Subagents are not a prerequisite for agentic reasoning.

They are an optimization when:

```text
work is separable
AND parallelism or context isolation adds value
AND delegated output can be bounded
```

This supports the corrected Soma rule:

```text
Sol remains the main semantic actor.
Specialists exist only when delegation is materially useful.
```

---

# 2. Core decision rule: default to Sol, not delegation

**OWNER REQUIREMENT**

A weaker or subordinate model should not routinely perform the important reasoning instead of Sol.

**INFERENCE - CORE RULE**

The default decision tree should conceptually be:

```text
Does the task require semantic judgment?
    |
    +-- no --> deterministic Soma/tool execution
    |
    +-- yes --> Sol reasons directly
                 |
                 +-- would independent bounded delegation
                     materially improve speed, context hygiene,
                     diversity, or verification?
                         |
                         +-- no --> Sol continues directly
                         |
                         +-- yes --> optional specialist(s)
                                     -> bounded evidence/result
                                     -> Sol synthesizes/decides
```

This reverses the earlier Agent/Worker assumption that semantic work naturally maps to a `reasoning_worker` Task.

Delegation must justify itself.

---

# 3. Specialist justification criteria

A subordinate intelligent specialist should be considered only when at least one concrete benefit exists.

## 3.1 Parallel independent inspection

Examples:

- inspect several independent repositories/components;
- evaluate several independent hypotheses;
- search several unrelated source domains;
- review security/tests/maintainability as separate read-heavy dimensions.

**INFERENCE**

This is the strongest case for parallel specialists because outputs can be independently bounded and synthesized later.

## 3.2 Context isolation

A specialist may be useful when a subtask creates large noisy intermediate output that would pollute Sol's main context:

- huge logs;
- broad codebase scans;
- many test reports;
- large document sections.

The specialist returns a compact evidence-linked summary rather than raw noise.

## 3.3 Independent second opinion / adversarial verification

A specialist can add value when Sol intentionally wants:

- an independent critique;
- red-team analysis;
- a second implementation review;
- fact verification isolated from Sol's initial conclusion.

The independence itself is the benefit.

## 3.4 Specialized capability

A provider may have a concrete capability Sol's current surface does not expose directly, for example:

- dedicated coding environment;
- specialized repository sandbox;
- provider-specific tool integration.

This is capability delegation, not cognitive replacement.

## 3.5 Explicit owner preference

The owner may simply request a named specialist/agent/provider.

That explicit request is sufficient to consider the route subject to its existing authorization gates.

---

# 4. Conditions that do NOT justify a specialist

## 4.1 “The task needs reasoning”

Not enough.

Sol already reasons.

## 4.2 “Normal Chat lacks Work's agent loop”

Not enough.

The missing capability is durable return of control to Sol, solved by the lightweight loop.

## 4.3 “The work is long-running”

Not enough.

Long duration belongs to durable JobManager/RunStore execution unless model cognition is genuinely needed during the job.

## 4.4 “There are several actions”

Not enough.

Several deterministic actions can use canonical Tasks, parallel command groups, or ordinary tool calls.

## 4.5 “A cheaper model could do it”

Cost alone does not justify moving important semantic authority away from Sol.

A cheaper specialist is appropriate only when the work is sufficiently bounded and the quality/verification contract makes the tradeoff worthwhile.

## 4.6 “We already built worker infrastructure”

Sunk implementation cost is not architectural justification.

Worker infrastructure remains available when a real delegation case exists.

---

# 5. Surface-specific specialist policy

## 5.1 ChatGPT Work

**DOCUMENTED FACT**

Work already owns subagent spawning/orchestration and collects the outputs into the main Work response.

**OWNER REQUIREMENT**

Do not add a second Soma subagent manager underneath Work.

**INFERENCE**

Default Work rule:

```text
Work decides whether its native subagents are useful.
Soma does not mirror each Work-native child as a canonical Task
unless that child independently owns a Soma/external effect that requires
Soma durability/authority.
```

Provider-native child-agent threads are provenance/internal orchestration, not automatically Soma lifecycle identities.

## 5.2 Normal Chat

Normal Chat's core Sol loop has no required native subagent primitive.

If a future/supported native Chat delegation primitive exists in the specific surface, Sol may use it where useful.

Otherwise an optional external specialist can run through Soma's subordinate-worker/provider infrastructure only when deliberately selected.

The core loop remains fully functional with zero specialists.

## 5.3 Codex

**OWNER REQUIREMENT**

Codex can only be used after explicit owner authorization.

Therefore Codex is never selected automatically because:

- code exists;
- a repository is involved;
- normal Chat needs another reasoning turn;
- a test failed;
- an Agent/Worker benchmark once preferred a Codex path.

When authorized, Codex may be a useful coding/repository specialist.

## 5.4 Hermes

Integrated Hermes remains headless tool/execution infrastructure.

Parallel Hermes instances mean execution concurrency, not independent semantic minds.

## 5.5 Deterministic parallel execution

Use parallel command/tool execution when independent work needs more execution bandwidth but no independent model judgment.

This should be preferred over spawning model workers for mechanical tasks.

---

# 6. Native Work subagents should not be projected one-for-one into Soma Tasks

## Problem

A provider-native Work subagent tree can contain many short-lived child threads.

Mirroring every child as a canonical Soma Task would:

- duplicate Work's own orchestration identity;
- couple Soma to provider-specific tree topology;
- inflate Task/state/evidence records;
- risk treating provider-local scheduling as external authority;
- make Work's internal implementation a Soma contract.

## Correct boundary

**INFERENCE**

A Work-native child becomes relevant to Soma only when a distinct Soma-owned fact exists, for example:

```text
child requests one durable Soma external action
 -> that action is a canonical Task
```

or:

```text
Work explicitly delegates an external specialist operation to Soma
 -> one canonical specialist Task owns that provider operation
 -> provider's own internal children remain provider provenance
```

This preserves the correct identity hierarchy:

```text
Work native cognitive tree
    |
    +--> Soma Task only at a real Soma/external ownership boundary
```

---

# 7. Optional specialist Task identity

Iteration 6 found that a deliberately delegated intelligent-provider operation may legitimately deserve a canonical Task.

The problem is the current term `REASONING`, not necessarily the existence of such Tasks.

## 7.1 What the Task represents

**INFERENCE**

A specialist Task should represent:

```text
Sol/Work explicitly delegated bounded work to an external intelligent provider,
and Soma owns the durable provider-operation lifecycle/evidence.
```

It does **not** represent:

```text
Sol's own reasoning turn.
```

## 7.2 Naming candidates

No rename is accepted yet.

Candidates:

```text
specialist
intelligent_specialist
delegated_analysis
model_operation
provider_operation
```

Tradeoffs:

- `specialist` is broad and provider-neutral but may also cover non-model work;
- `delegated_analysis` is semantically narrow and poor for implementation specialists;
- `model_operation` overcouples to model-backed providers;
- `provider_operation` is mechanically accurate but too generic;
- `intelligent_specialist` states the intent but is awkward terminology.

## 7.3 Current recommendation

**INFERENCE**

Do not spend implementation effort renaming enums until the full synthesis decides whether the public distinction is needed at all.

The immediate architectural correction can be made by **removing `REASONING` from the core path** and documenting it as compatibility/optional specialist infrastructure.

Historical compatibility may be cheaper than a schema rename in the first cleanup.

---

# 8. Worker authority/gateway should remain dormant unless a subordinate worker exists

**REPOSITORY FACT**

Worker authority and worker gateway are separate from the owner/executive Soma surface and already require exact grants/principals.

**INFERENCE**

They should not be initialized/invoked merely because a normal Chat loop exists.

Activation condition should conceptually be:

```text
an actual subordinate worker/provider needs direct Soma capability
```

not:

```text
agentic task exists
```

This keeps the normal Chat loop simple while retaining a powerful containment system for future specialists.

---

# 9. EvidenceSubmission/FanIn trigger rule

## Use them when

- multiple semantic specialists return claims/evidence;
- the producer is not Sol and Sol must adjudicate its evidence;
- completeness/missing-unit accounting matters;
- provenance across parallel specialists matters.

## Do not use them when

- canonical Task result is already the authoritative observation;
- one command/test/tool action finishes;
- a deterministic command group returns child Run results;
- Work itself already consolidates native subagents and Soma only needs a final external action result.

**INFERENCE**

EvidenceSubmission and FanIn are **delegation protocols**, not generic Task protocols.

---

# 10. Atomic loop-to-Task ownership: existing Soma already has the needed transactional seam

Iteration 5 identified a dangerous hypothetical race:

```text
create effectful Task
CRASH
attach Task to loop
```

The controller might believe the Task belongs to the loop while durable state does not.

## 10.1 Existing connection-scoped Task reservation

**REPOSITORY FACT**

`TaskStore.reserve_task_in_connection(conn, ...)` exists specifically so another authority can coordinate Task insertion inside an existing SQLite transaction.

It provides:

- exact controller-request replay checking;
- request-hash conflict detection;
- Task insert;
- backend link insert;
- parent link insert;
- no backend execution launch inside the insert.

## 10.2 Existing ProjectScope precedent

**REPOSITORY FACT**

Current `TaskManager` already performs this pattern for scoped Tasks:

```text
BEGIN transaction
 -> validate/replay controller request
 -> ProjectScope.reserve_task_attempt(...)
 -> TaskStore.reserve_task_in_connection(...)
 -> ProjectScope.attach_task(...)
COMMIT
 -> only then launch backend work
```

Worker-gateway activation uses the same style.

Company admission also coordinates ProjectScope + Task + WorkPackageAttempt in one transaction, although its current reasoning-provider dependency is a separate architectural issue.

## 10.3 Important backend property

**REPOSITORY FACT**

The generic `ExecutionBackend.reserve()` contract allocates a backend reference **without creating durable work**.

Therefore obtaining a backend identity before the Task/loop transaction does not itself execute the effect.

## 10.4 Conclusion

**INFERENCE - STRONG**

The future Sol loop does **not** need another Task launcher.

A loop coordinator can use the same shared SQLite transaction pattern:

```text
reserve inert backend reference

BEGIN IMMEDIATE
 -> validate loop exists/open + expected loop version
 -> validate loop command idempotency/replay
 -> validate ProjectScope if required
 -> reserve ProjectScope attempt if required
 -> reserve canonical Task through TaskStore.reserve_task_in_connection
 -> insert loop-to-Task ownership membership
 -> attach ProjectScope Task binding if required
 -> record/result loop command + advance loop version
COMMIT

existing Task backend launch path continues
```

The exact factoring is an implementation-design question, but the transactional feasibility is proven by existing code.

---

# 11. Why backend launch must stay outside the ownership transaction

Backend process/provider launch can fail, block, or become ambiguous and cannot be a SQLite atomic operation.

Existing Task design correctly uses:

```text
persist identity first
 -> launch effect later
 -> recover if launch boundary is incomplete/uncertain
```

**INFERENCE**

The loop must preserve this ordering.

A crash after the loop+Task transaction but before launch yields:

```text
loop owns Task
Task has reserved backend identity
no effect has silently escaped
Task recovery can detect incomplete launch
```

That is safe and recoverable.

A crash after external launch but before loop ownership would be the dangerous case; the single transaction before launch prevents it.

---

# 12. Do not copy TaskManager launch logic into a new LoopManager

**INFERENCE - DESIGN RULE**

A future loop component may coordinate reservation, but it must not reimplement:

- durable-command launch;
- reasoning/specialist provider launch;
- ProjectScope logic;
- backend reconciliation;
- cancellation;
- result publication.

Those stay in existing Task/backend authorities.

Possible future code factoring may extract a shared internal reservation coordinator or add an ownership hook/contract to TaskManager.

The implementation plan must choose the smallest approach after tests/consumers are audited.

---

# 13. Existing Task adoption versus new Task creation

The minimal loop may need two distinct relationships.

## 13.1 Create loop-owned Task

Strongest ownership semantics.

The loop and Task membership are persisted atomically before launch.

Likely used for effectful actions Sol initiates while pursuing the loop objective.

## 13.2 Attach/adopt an already-existing Task

Potential use cases:

- a Task was started directly just before the loop was created;
- read-only result from another controller context is relevant;
- migration/compatibility from existing work.

This is riskier because execution may already exist.

## 13.3 Ownership versus evidence reference

**INFERENCE**

Do not call every useful pre-existing Task “owned” by the loop.

Separate:

```text
control ownership
```

from:

```text
evidence/result reference
```

For a completed or externally owned Task, the loop may simply reference its immutable result/evidence without gaining cancellation/retry ownership.

## 13.4 Adoption rule candidate

Actual ownership adoption should probably be tightly limited to cases where:

- Task has no existing loop/control owner;
- exact ProjectScope is compatible;
- current Task state is acceptable;
- owner/controller explicitly requests adoption;
- state/version is named;
- effect ambiguity is preserved.

Whether adoption is needed in v1 remains open.

---

# 14. One control owner per effectful Task remains the safest default

**INFERENCE**

A canonical Task that can mutate/cancel/retry an external effect should have at most one higher-level loop/control owner.

Reason:

- two loops could issue contradictory cancellation/continuation decisions;
- observation consumption is loop-local, but execution ownership must not be ambiguous;
- result/evidence can still be referenced by any number of other goals.

Suggested conceptual split:

```text
ControllerLoopTaskOwnership
    one owner max

EvidenceReference
    many readers allowed
```

This follows Soma's broader single-authority philosophy without preventing reuse of evidence.

---

# 15. Loop command idempotency can wrap Task request idempotency without duplicating it

## Problem

A high-level request such as:

```text
loop_action.start_task(...)
```

may create both:

- one loop command;
- one canonical Task.

Both need replay safety.

## Candidate contract

**INFERENCE**

The high-level controller request should deterministically bind:

```text
loop request identity
expected loop version
task normalized request hash
```

The transaction records both the loop command and Task controller request.

On replay:

- identical high-level request returns the already-linked Task;
- changed material under the same request ID conflicts;
- no second Task/backend effect is created.

This reuses Task idempotency as the action identity rather than inventing a parallel execution request hash.

Exact request-ID derivation/scope is deferred.

---

# 16. Observation fingerprint attaches naturally after atomic ownership

Once loop membership is inserted with the Task:

```text
last_consumed_observation_hash = initial Task observation hash
```

or a defined “unseen initial state” sentinel.

## Choice A - initial hash considered consumed

Sol already knows it just started the Task, so `accepted/backend_reserved` need not cause an immediate “reason again” signal.

New later Task state changes create a new fingerprint.

## Choice B - no consumed hash initially

The loop would immediately report the newly created Task itself as a new observation.

That adds noise.

## Leading hypothesis

**INFERENCE**

When Sol itself atomically creates the Task, set the membership baseline to the exact Task observation produced by that creation transaction.

Then only **subsequent changes** become unconsumed observations.

For adopted existing Tasks, the caller should explicitly choose/acknowledge the current observation baseline to avoid hiding existing terminal/uncertain facts.

---

# 17. No automatic specialist escalation from Task failure

This deserves an explicit invariant.

Bad path:

```text
Task fails
 -> Soma sees failure
 -> Soma starts Codex/reasoning worker
```

Correct path:

```text
Task fails
 -> Task observation fingerprint changes
 -> loop reports controller_turn_required
 -> Sol inspects evidence
 -> Sol decides retry/change/delegate/ask owner/stop
```

**OWNER REQUIREMENT / INFERENCE**

This invariant is the practical heart of the Sol-centric architecture.

No deterministic failure handler should silently change reasoning ownership.

---

# 18. No automatic specialist escalation from context size alone

Large logs/context may justify a specialist, but the decision still belongs to Sol/Work.

Soma may expose mechanical facts such as:

```text
artifact bytes
result truncation
available retrieval refs
```

It should not automatically spawn a model summarizer merely because output is large.

Sol can choose:

- retrieve a bounded slice;
- ask Soma for deterministic extraction;
- delegate to an optional specialist;
- use Work-native subagents where already in Work.

---

# 19. No weaker-model “pre-reasoning” requirement

Earlier architectures used cheap/local models for:

- error explanation;
- context compression;
- file selection;
- planning drafts;
- deciding whether Codex was needed.

**OWNER REQUIREMENT**

Important reasoning should not routinely be outsourced to a weaker model.

**INFERENCE**

Cheap models may still be intentionally used for **mechanically checkable transformations** or explicit low-value specialist work, but they should not sit as a mandatory preprocessor in front of Sol.

For example:

Acceptable candidate:

```text
large repetitive classification task
 -> cheap specialist with structured output
 -> sampled/mechanical verification
 -> Sol uses result
```

Not acceptable as core:

```text
all failures -> cheap model decides likely cause -> Sol sees compressed conclusion only
```

unless Sol explicitly chooses that tradeoff.

---

# 20. Work-native subagent permission inheritance reinforces Soma's boundary

**DOCUMENTED FACT**

OpenAI says Work subagents use the tools available to the parent chat; website/connector permissions remain tool-specific.

Codex subagents inherit parent permission/sandbox controls unless deliberately overridden.

## Implication

**INFERENCE**

Soma should continue enforcing its own exact action/ProjectScope/policy contracts regardless of whether a call originates from a main Work thread or a Work subagent.

Soma does not need to understand Work's entire subagent tree to remain safe.

Tool authority remains at the Soma action boundary.

---

# 21. Specialist provenance should remain subordinate

If an optional specialist Task uses a provider that internally spawns children, the provider provenance can record:

- provider run/session;
- child/agent path;
- raw event hashes;
- cited source references.

But those provider-local children should not gain independent Soma mutation authority merely because they exist.

Worker authority grants, if required, remain explicit and bounded.

This preserves the useful Agent/Worker provenance work without elevating provider topology into architecture truth.

---

# 22. Specialist result acceptance

A provider claims success; Soma can mechanically verify:

- provider binding;
- output contract validity;
- expected result/evidence publication;
- provenance/hash integrity;
- no unresolved cancellation/binding ambiguity.

Soma still cannot conclude:

```text
specialist's semantic answer is correct
```

Sol/Work performs that judgment.

This boundary is already present in EvidenceSubmission/FanIn and should be retained.

---

# 23. Corrected specialist architecture

```text
                         SOL / WORK MAIN THREAD
                                  |
                        semantic decision owner
                                  |
                  +---------------+---------------+
                  |                               |
          normal Soma action             optional delegation
                  |                               |
          canonical Task                 canonical specialist Task
                  |                               |
          durable execution               restricted provider/worker
                  |                               |
          result/evidence                 EvidenceSubmission if useful
                  |                               |
                  +---------------+---------------+
                                  |
                         SOL / WORK synthesis
```

For Work-native subagents:

```text
Work main thread
 -> Work native subagents
 -> Work consolidates
```

Soma appears only where an actual Soma action/external ownership boundary is crossed.

---

# 24. Corrected normal-Chat loop + atomic Task creation

```text
Normal Chat / Sol
       |
       | reason
       v
ControllerLoop(open, version N)
       |
       | Sol decides explicit action
       v
reserve inert backend ref
       |
       v
+---------------- ONE SQLITE TRANSACTION ----------------+
| validate loop version/request replay                   |
| reserve ProjectScope attempt if required               |
| reserve canonical Task                                 |
| attach loop control ownership                          |
| establish initial consumed Task observation fingerprint|
| record loop command / advance loop version             |
+--------------------------------------------------------+
       |
       | commit before effect
       v
existing Task/backend launch
       |
   environment
       |
Task state/result/evidence changes
       |
observation fingerprint differs
       |
loop projection: controller_turn_required
       |
owner wakes Chat if necessary
       |
       v
Normal Chat / Sol reasons again
```

No subordinate model is involved unless Sol separately chooses one.

---

# 25. Can direct Task start remain available? Yes.

**INFERENCE**

The lightweight loop must not replace direct Task use.

Two legitimate paths remain:

```text
A. Direct one-shot action
Sol/Work -> task_action.start -> Task

B. Durable goal-owned action
Sol -> loop action/coordinator -> atomic loop membership + same canonical Task
```

Both converge on the same Task/backend execution authority.

This preserves simple UX and backward compatibility.

---

# 26. Public API implications - still research only

The atomic seam suggests a future high-level loop mutation may be justified for loop-owned Task creation.

Conceptual operation:

```text
loop_action.start_task
```

But this should be a **coordinator**, not a new executor.

It would:

- validate loop command/version;
- invoke existing Task normalization/reservation logic;
- coordinate membership transactionally;
- return the canonical Task identity.

It must not acquire independent backend launch/reconciliation logic.

## Alternative

Extend `task_action.start` with an optional `controller_loop_ref` plus expected loop version.

Advantages:
- no extra high-level start operation.

Risks:
- pollutes Task API with a higher-level optional control concern;
- may complicate existing union branches;
- loop command idempotency becomes awkward.

## Current leaning

**INFERENCE**

A compact `loop_action` coordinator is conceptually cleaner, provided its implementation delegates into one shared internal Task reservation/start authority rather than copying it.

Do not decide until API/schema compatibility is audited.

---

# 27. Specialist decision matrix

| Work shape | Preferred actor |
|---|---|
| Simple semantic judgment | Sol / Work main thread |
| Sequential result changes next decision | Sol / Work main thread between actions |
| Exact command/tool execution | Soma deterministic execution |
| Several independent exact commands | Soma parallel execution where safe |
| Large noisy read-heavy exploration | Optional native/specialist subagent if useful |
| Independent second opinion | Optional specialist |
| Parallel independent research dimensions | Optional specialists; Sol/Work synthesizes |
| Write-heavy shared-state coding | Prefer one main owner; parallelize cautiously |
| Long-running deterministic training/test | Soma durable JobManager/RunStore |
| Coding specialist | Codex only with explicit owner authorization |
| Integrated Hermes | Tool/execution runtime, not semantic specialist |
| Work-native subagents | Work owns orchestration; Soma only owns external actions |
| Normal Chat continuation | Sol loop; no specialist required |

---

# 28. Invariants carried forward

These should be treated as strong research invariants unless later evidence disproves them.

1. **Sol/Work main thread owns semantic continuation.**
2. **Specialist delegation is optional, never required for normal Chat agentic continuity.**
3. **Task failure returns control to Sol; it does not auto-escalate to another model.**
4. **Long-running work does not imply model reasoning.**
5. **Parallel deterministic work uses execution parallelism before model parallelism.**
6. **Work owns Work-native subagent orchestration.**
7. **Provider-native child agents are provenance, not automatically Soma Tasks.**
8. **Codex remains explicit-owner-authorized only.**
9. **Worker authority/gateway stays dormant without a real subordinate worker.**
10. **EvidenceSubmission/FanIn stays off the simple Task path.**
11. **Loop ownership + Task reservation must commit before external effect launch.**
12. **Loop coordinator must reuse, not fork, TaskManager/TaskStore execution logic.**
13. **One effectful Task should have one control owner; evidence can have many readers.**
14. **No private reasoning text is persisted.**

---

# 29. What changed in our understanding

## Before Iteration 7

The loop-to-Task attachment race was the biggest unresolved technical concern, and specialist worker policy was still broad.

## After Iteration 7

**INFERENCE**

The loop attachment problem is likely solvable with existing proven transaction patterns. `reserve_task_in_connection()` plus ProjectScope's current coordinator model provides the exact seam needed to add one loop membership fact before any effect launches.

The specialist boundary is also narrower:

```text
specialist = explicit bounded optimization/capability
not
specialist = generic semantic work executor
```

This further reduces the amount of new architecture required.

---

# 30. Remaining research before synthesis

The core Sol-loop architecture is now reasonably stable. Remaining research should concentrate on areas that could still impose unwanted higher-level semantics:

1. Company/Mission/Plan interaction while Company remains frozen.
2. Legacy Workflow/Supervisor/public-gateway consumer impact and retirement compatibility.
3. Existing reasoning Task/backend public API/history migration concerns.
4. Exact loop discovery/context semantics across fresh chats and multiple active loops.
5. Whether objective/constraint references should reuse current content-addressed artifact/memory contracts.
6. Public API shape and capability metadata - only after existing consumers/tests are mapped.
7. Final historical drift timeline and terminology supersession strategy.

No implementation plan should be produced until those are resolved.

---

# Sources consulted

## Current official OpenAI sources

- OpenAI / ChatGPT Learn, `Subagents`: https://learn.chatgpt.com/docs/agent-configuration/subagents
  - current documentation establishes Work/Codex subagent orchestration, main-thread result collection, token cost, read-heavy parallel use cases, and caution for parallel write-heavy work.
- OpenAI API, `Model guidance`: https://developers.openai.com/api/docs/guides/latest-model
  - current documentation distinguishes bounded programmatic tool workflows, multi-agent independent workstreams, and fresh model judgment.
- OpenAI Help Center, `ChatGPT Work and Codex`: https://help.openai.com/en/articles/20001275/

## Soma repository

- `soma/tasks/store.py`
- `soma/tasks/manager.py`
- `soma/tasks/backends.py`
- `soma/project_scope/store.py`
- `soma/worker_gateway/activation.py`
- `soma/company_kernel/admission.py` - inspected only as frozen architectural evidence
- `soma/worker_authority/*`
- `soma/worker_gateway/*`
- `soma/worker_evidence/*`
- `soma/reasoning/*`
- `soma/parallel_groups.py`
- prior realignment Iterations 1-6
