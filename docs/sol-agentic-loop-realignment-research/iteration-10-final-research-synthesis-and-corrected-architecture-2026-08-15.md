# Iteration 10 - Final Research Synthesis and Corrected Sol-Centric Architecture

Date: 2026-08-15
Status: FINAL RESEARCH SYNTHESIS - implementation not authorized
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected at synthesis: `3c14b997e7f3d4dfff074695dc2509d7c38d5730`

## Executive summary

The research question was:

> What is the smallest, cleanest change that turns the architecture already built into the owner's intended Sol-centric durable agentic loop, while preserving useful infrastructure and removing/isolating redundant reasoning-worker architecture?

The answer is now supported strongly enough to plan later implementation.

### Core conclusion

Soma does **not** need another default reasoning brain.

The missing capability for normal Chat is a **small durable continuation substrate that lets Sol's own reasoning loop survive interruptions**.

The **Sol reasoning loop** is:

```text
Sol reasons
  -> Sol chooses zero/one/many actions
  -> Soma durably owns exact action Tasks / Runs / evidence
  -> environment changes
  -> canonical Task observation changes
  -> owner wakes Chat when needed
  -> Soma returns the unconsumed mechanical changes
  -> Sol reasons again
  -> repeat
  -> Sol explicitly declares the objective complete
```

**Terminology freeze:** this cognitive `reason -> act -> observe -> reason` cycle is what this architecture means by **loop**. A Task lifecycle, a sequence of Tasks, a scheduler, and Soma's durable bookkeeping are **not** the loop. Tasks are actions chosen by Sol during the reasoning loop; they never drive or advance the reasoning loop themselves.

ChatGPT Work is different. Work already supplies its own native multi-step agentic cognition and subagent orchestration. Work should use Soma's **shared durable execution/evidence/memory substrate**, not a second Soma cognitive loop.

The expensive Agent/Worker programme is mostly salvageable. Its durable lower-level mechanics are useful. The drift is concentrated in the elevation of `reasoning worker / reasoning backend` into a core semantic path and in legacy semantic routers such as LocalAgent/Supervisor.

The smallest credible new durable authority is currently a three-part lightweight **reasoning-continuation substrate**. To avoid confusing durable bookkeeping with the reasoning loop, the working implementation vocabulary is:

```text
controller_continuations
controller_continuation_tasks
controller_continuation_commands
```

The continuation substrate persists enough state for the **Sol reasoning loop** to resume. It does not itself loop, reason, schedule the next Task, or decide that another stage should run.

It must also obey a hard concurrency boundary: **neither the Sol reasoning loop nor its ControllerContinuation bookkeeping owns a repository operation lock.** Multiple unrelated projects must be able to reason and maintain continuation state simultaneously. Repository/resource locks belong only to concrete side-effecting execution that actually requires exclusive ownership, and only for the lifetime of that operation.

It does **not** need:

- a reasoning model;
- a turn table;
- copied observation rows;
- a transcript store;
- a mandatory DAG;
- a scheduler;
- a Worker/FanIn path;
- Company/Mission/Plan;
- Codex;
- Hermes reasoning;
- automatic Chat wake-up.

This research therefore recommends a future implementation strategy of **addition + routing correction + gradual convergence**, not an Agent/Worker purge.

No implementation is authorized by this document.

---

# 1. Research method and evidence status

This synthesis incorporates nine prior research iterations preserved under:

```text
docs/sol-agentic-loop-realignment-research/
```

Those iterations separately established:

1. current Chat / Work / native-agent product reality;
2. original owner intent and the drift timeline;
3. minimum durable Sol control-loop state;
4. mode-aware Chat vs Work integration;
5. loop-contract minimization;
6. Agent/Worker component reuse/reposition classification;
7. specialist/subagent boundaries and atomic loop-to-Task ownership;
8. frozen Company/Mission/Plan interaction;
9. legacy/public-surface compatibility cost.

The research used:

- current official OpenAI product/docs sources for Chat/Work/subagent/tool behavior;
- actual Soma source;
- tests;
- Git history;
- accepted gate/result documents;
- legacy architecture documents;
- the owner-provided CodexBridge Local Agent Roadmap v2;
- explicit owner clarifications during the research.

Facts and inferences remain separated below.

---

# 2. Owner requirements now frozen by this research

These are not inferred preferences. They are explicit owner requirements.

## 2.1 Sol / main ChatGPT remains the brain

**OWNER REQUIREMENT**

Important semantic reasoning belongs to the main ChatGPT/Sol intelligence.

The normal default must not become:

```text
Sol
 -> Soma
 -> weaker/external reasoning worker
 -> Sol merely reviews the worker
```

The desired default is:

```text
Sol
 -> action
 -> observation
 -> Sol
```

## 2.2 Soma extends ChatGPT; it does not replace ChatGPT's cognitive layer

Soma's core value is:

- durable action identity;
- durable process/execution state;
- persistence across interruption;
- idempotency/replay;
- recovery/uncertainty;
- evidence/provenance;
- machine/service/tool access;
- long-running execution;
- project/resource ownership;
- memory/knowledge;
- compact continuation state.

## 2.3 Normal Chat and Work are intentionally asymmetric

**OWNER REQUIREMENT**

Normal Chat may need Soma's lightweight agentic-continuation add-on.

Work already has its native multi-step agentic loop and should not receive a duplicate Soma reasoning loop.

## 2.4 Specialist agents are optional

Codex, Claude, provider-native agents, Responses/API agents, or future model specialists may be used for explicitly justified bounded work.

They are not prerequisites for the architecture.

Codex remains **explicit owner authorization only**.

## 2.5 Automatic wake-up is not a core requirement

The owner can manually wake Chat after long work.

PulseSender or a future Chrome/browser extension may improve delivery convenience later.

They remain transport adapters, never reasoning authorities.

## 2.6 Company remains frozen

Nothing in this research reopens Company.

Normal Chat loop implementation must proceed independently of Company.

## 2.7 Multi-project reasoning must remain lock-free

**OWNER REQUIREMENT**

Soma is a shared control plane for many projects that may be active simultaneously. A ControllerContinuation, Sol reasoning cycle, continuation query, Task observation read, evidence inspection, or planning step must **not** acquire or retain a repository operation lock merely because the reasoning objective or Task is associated with a repository.

The governing separation is:

```text
Task / continuation association != repository / resource ownership
```

A continuation may associate zero, one, or many canonical Tasks with one Sol reasoning objective without owning the underlying repository. ProjectScope identifies the project/resource relationship; it does not imply exclusive mutation ownership.

**REPOSITORY FACT**

Current `OperationLockStore` locks are keyed by `repo_name`, so existing repository mutation ownership is repository-scoped rather than globally serialized. Current `JobManager` durable runs, however, default `repository_lock_required` to `True`, with only narrowly supported exceptions. Therefore a future ControllerContinuation implementation must not be represented as an ordinary lock-owning durable Run merely to gain persistence.

The intended concurrency model is:

```text
Sol loop A -> Project A -> reasoning / observation --------+
Sol loop B -> Project B -> reasoning / observation --------+ simultaneous
Sol loop C -> Project C -> reasoning / observation --------+

Concrete mutation in repo A -> repo-A lock only while needed
Concrete mutation in repo B -> repo-B lock only while needed
```

Even when several Sol loops concern the **same** repository, their reasoning, evidence reads, and continuation bookkeeping should remain concurrent. Concrete executions that require repository/resource mutation ownership serialize according to the **current granularity of that resource authority**. Today `OperationLockStore` is keyed by `repo_name`, so same-repository mutations may serialize more broadly than true file-level conflicts. Refining that lock granularity is a separate resource-concurrency problem; ControllerContinuation must neither widen it nor participate in it merely because Sol is reasoning.

**IMPLEMENTATION INVARIANT**

ControllerContinuation SQLite transactions must also be short atomic bookkeeping transactions. Soma must never hold a database write transaction while Sol is reasoning, waiting for a tool/backend result, waiting for the owner to wake Chat, or waiting for a Task to change. Otherwise a repository-lock bottleneck would merely be replaced by a database-lock bottleneck.

`Lock-free reasoning` does **not** mean SQLite metadata writes never serialize. Brief database write coordination during a bounded atomic mutation is expected and acceptable. The forbidden condition is carrying that transaction/lock across cognition or external waiting.

---

# 3. Current OpenAI product reality that affects the architecture

## 3.1 Chat and Work are separate ChatGPT experiences

**DOCUMENTED FACT**

Current OpenAI documentation distinguishes:

- Chat: conversational assistance;
- Work: longer multi-step agentic work and finished deliverables;
- Codex: separate software-development experience.

Work is explicitly an agentic surface and current documentation describes native subagent workflows where specialized agents can operate in parallel and the main thread collects/consolidates their results.

Official sources consulted across this track include:

- OpenAI Help Center - `ChatGPT Work and Codex`;
- OpenAI - `ChatGPT Work`;
- OpenAI / ChatGPT Learn - `Subagents`;
- OpenAI API - `Model guidance`;
- OpenAI Help Center - Plugins / Skills documentation.

## 3.2 Work already provides the cognitive loop Soma would otherwise be tempted to rebuild

**DOCUMENTED FACT + INFERENCE**

Work plans, performs multi-step work, uses tools/apps/files, and supports native delegated subagents.

Therefore a second model-driven Soma reasoning loop under Work would duplicate product capability, consume tokens/context, and create conflicting control ownership.

## 3.3 No reliable inbound Chat-vs-Work MCP marker was established

**OPEN QUESTION / NEGATIVE FINDING**

The research found no official documented external App/MCP invocation field that Soma can rely on to identify `normal Chat` versus `Work` for every call.

Therefore the architecture must not depend on such a marker.

## 3.4 Mode awareness is usage-based, not execution-truth-based

**INFERENCE**

Shared execution truth remains mode-neutral.

Normal Chat explicitly uses the lightweight loop when durable continuation is useful.

Work simply uses the shared Soma Task/Run/evidence substrate under Work's own agentic controller.

No heuristic surface detection is needed.

---

# 4. Corrected target architecture

## 4.1 Whole system

```text
                                 USER
                                   |
                  +----------------+----------------+
                  |                                 |
             NORMAL CHAT                          WORK
                  |                                 |
                 SOL                         WORK / SOL NATIVE
          main semantic authority             AGENTIC LOOP
                  |                                 |
       when durable continuation                    |
             is useful                              |
                  |                                 |
                  v                                 |
      +-------------------------+                   |
      | lightweight Sol loop    |                   |
      | objective/version       |                   |
      | Task ownership links    |                   |
      | consumed obs hashes     |                   |
      | idempotent commands     |                   |
      +------------+------------+                   |
                   |                                |
                   +---------------+----------------+
                                   |
                                   v
                       +-----------------------+
                       | SOMA SHARED SUBSTRATE |
                       +-----------------------+
                       | canonical Task        |
                       | durable Run/process   |
                       | ProjectScope          |
                       | tools/services        |
                       | result/evidence       |
                       | recovery/uncertainty  |
                       | memory/knowledge      |
                       +-----------+-----------+
                                   |
                                   v
                        EXTERNAL ENVIRONMENT
                                   |
                                   v
                         CANONICAL OBSERVATIONS
                                   |
                  +----------------+----------------+
                  |                                 |
          normal-Chat loop sees             Work receives result
          unconsumed Task change            through native flow
                  |                                 |
                  v                                 v
                 SOL                            WORK / SOL
             reasons again                   continues natively
```

## 4.2 Optional specialist branch

```text
Sol / Work main thread
        |
        | explicitly decides delegation is useful
        v
canonical specialist Task
        |
restricted worker/provider infrastructure
        |
EvidenceSubmission / FanIn only if genuinely needed
        |
        v
Sol / Work main thread
interprets and decides
```

This branch is **not** part of the normal critical path.

## 4.3 Optional delivery branch

```text
Soma durable result/continuation state
       |
       +--> manual owner wake/query       [baseline]
       |
       +--> PulseSender                   [optional]
       |
       +--> future browser extension      [optional]
```

Delivery never changes task truth or reasoning ownership.

---

# 5. Chat vs Work responsibility matrix

| Concern | Normal Chat | ChatGPT Work | Soma |
|---|---|---|---|
| Understand user intent | Sol | Work/Sol | no semantic ownership |
| Important semantic reasoning | Sol | Work/Sol | no core semantic reasoning |
| Adaptive multi-step cognition | lightweight Sol continuation when needed | native Work loop | durable support only |
| Working plan | Sol cognition | Work native | do not own by default |
| Decide next action after result | Sol | Work/Sol | expose exact mechanical facts |
| Native subagent orchestration | not assumed as core normal-Chat primitive | Work owns | do not duplicate |
| Durable action identity | consume | consume | canonical Task |
| Process/external execution | request/review | request/review | Run/JobManager/tools |
| Long-running execution | may disconnect/re-enter | Work may continue natively | authoritative external execution |
| Result/evidence | interpret | interpret | preserve/reference |
| Recovery/uncertainty | decide response | decide response | mechanically preserve |
| Goal completion | Sol explicitly declares | Work/main controller | never infer semantically |
| Memory/project facts | use intentionally | use intentionally | durable store |
| Wake-up/delivery | manual baseline | product-native where applicable | optional adapter only |

---

# 6. Sol vs Soma responsibility matrix

| Responsibility | Sol / ChatGPT | Soma |
|---|---:|---:|
| Interpret user objective | yes | no |
| Decide what evidence means | yes | no |
| Choose next semantic action | yes | no |
| Decide whether to delegate to specialist | yes | no automatic escalation |
| Decide goal complete | yes | no |
| Persist exact Task identity | consume | yes |
| Persist action/backend identity | consume | yes |
| Own process tree | no | yes |
| Execute tools/services | request | yes |
| Persist output/evidence refs | consume | yes |
| Track idempotency/replay | rely on | yes |
| Preserve uncertain external effects | inspect/decide | yes |
| Track which Task observation Sol consumed | acknowledge | yes |
| Determine that mechanical state changed | inspect | yes |
| Infer semantic recommended next action | yes | **no** |
| Store private chain-of-thought | **no durable requirement** | **never** |

The key architectural line is:

```text
Soma may know that Sol needs to look again.
Soma must not decide what Sol should conclude.
```

---

# 7. Native subagent vs optional external specialist matrix

| Type | Who owns orchestration? | Canonical Soma Task for child? | Appropriate role |
|---|---|---|---|
| Work-native subagent | ChatGPT Work | not by default | independent read-heavy parallel work, bounded delegated tasks |
| Codex subagent | Codex surface | not automatically | coding/repo delegation inside Codex when owner uses Codex |
| Normal-Chat optional external specialist | Sol chooses; Soma may own provider operation | yes if Soma owns durable provider operation | second opinion, bounded independent research, specialized capability |
| Hermes headless worker | Soma execution service | Task/Run for actual execution as appropriate | tools/execution concurrency, not reasoning |
| Parallel command group | Soma deterministic scheduler | child Runs / appropriate Task linkage | mechanical fan-out, no independent cognition |
| Cheap/local model specialist | only explicit optional use | only if made durable/owned | bounded mechanically verifiable transformation, not mandatory pre-reasoner |

### Specialist decision rule

```text
semantic judgment needed?
    no -> deterministic Soma execution
    yes -> Sol/Work reasons directly
           unless bounded delegation has a concrete benefit
```

Concrete benefits include:

- independent parallel inspection;
- context isolation for noisy work;
- independent adversarial verification;
- a specialized capability;
- explicit owner request.

Not sufficient:

- “it needs reasoning”;
- “it is long-running”;
- “there are several actions”;
- “a cheaper model exists”;
- “we already built workers.”

---

# 8. Minimal missing capability for normal Chat

## 8.1 What is actually missing

Canonical Task already solves execution identity and lifecycle very well.

What it does not represent is a user objective that spans multiple Tasks and multiple Sol reasoning turns.

`awaiting_controller` already handles a **non-terminal running Task** that needs input, but it cannot represent:

```text
Task A is terminal
 -> result exists
 -> Sol must decide what to do next
```

without corrupting Task terminal semantics.

Therefore one lightweight **reasoning-continuation substrate** is justified. It preserves the state needed to resume Sol's reasoning loop; it is not a Task loop or workflow engine.

## 8.2 Minimum storage hypothesis after pressure testing

The minimal credible design is three small authorities.

### `controller_continuations`

Research shape:

```text
continuation_id
label?                       # bounded discovery hint
objective_ref
objective_hash?              # where reference contract supports it
constraints_ref?
state = open | completed | cancelled
state_version
created_at
updated_at
closed_at?
```

Deliberately absent:

- model/provider;
- Chat/Work mode;
- conversation ID;
- Task backend;
- reasoning text;
- transcript;
- Plan/DAG;
- worker identity;
- scheduler state;
- ProjectScope ownership requirement.

### `controller_continuation_tasks`

Research shape:

```text
continuation_id
task_id
attached_at
last_consumed_observation_hash
last_consumed_at?
correlation_ref?             # optional, not required for core
```

This is **durable continuation association/control provenance**, not a copy of Task state and not a scheduler edge. The Sol reasoning loop remains the only thing that decides whether another Task should exist.

### `controller_continuation_commands`

Research shape:

```text
command_id
continuation_id
operation
controller_request_id
request_hash
expected_continuation_version
resulting_continuation_version
status
created_at
completed_at?
compact disposition/result ref?
```

Purpose:

- durable idempotency;
- replay conflict detection;
- audit of continuation mutation;
- no cognitive lifecycle and no automatic Task progression.

## 8.3 What the pressure test removed

Not needed in minimal core:

- controller-turn table;
- copied observation table;
- global observation stream/cursor;
- controller/model identity;
- Chat conversation ID;
- mode field;
- project ownership on continuation;
- plan graph;
- hidden recommended-next-action;
- provider identity.

This minimization is important: the add-on should not quietly become another agent framework.

---

# 9. Controller continuation observation fingerprint

## 9.1 Canonical Task remains the action authority, but is not the only continuation input

Do not copy Task lifecycle/results or other authority rows into continuation records.

Re-audit found that a literal hash of only the `tasks` row is too narrow. Controller-relevant mechanical truth can also live in existing authorities such as ProjectScope attempt state, checkpoint state, and authoritative Task event/recovery evidence.

Instead define one versioned bounded **computed** projection, conceptually:

```text
ControllerObservationV1
    task
        task_id
        task_kind
        state
        phase
        state_version
        backend_kind
        backend_ref
        result_ref
        result_hash
        evidence_ref
        recovery_state
        recovery_reason
    project_scope
        binding_status
        project_id
        resource_id
        scope_generation
        attempt_status
    checkpoint
        checkpoint_ref
        open_count / relevant status
    controller_relevant_authority_watermark(s)
        only where needed to prove no relevant transition can disappear
```

Exact fields/watermarks remain implementation-design detail and must be proven by tests. The key invariant is:

> No controller-relevant mechanical change in an authority associated with a continuation-linked Task may occur without changing the continuation observation fingerprint or otherwise remaining explicitly unconsumed.

Compute:

```text
observation_hash = SHA256(canonical(ControllerObservationV1))
```

The continuation substrate stores only this last-consumed hash, never a copied observation body.

## 9.2 Detecting a new Sol-relevant observation

```text
current ControllerObservationV1 hash
    !=
continuation membership last_consumed_observation_hash
```

means controller-visible mechanical truth changed since Sol last acknowledged it.

## 9.3 Acknowledgement must be stale-safe

Sol acknowledges exact observed hashes.

Inside one short transaction Soma recomputes the complete current aggregate observation from its canonical authorities.

If any included authority changed after Sol queried it, acknowledgement fails stale rather than hiding unseen state.

## 9.4 `controller_turn_required` is derived

Soma may mechanically derive attention-required when unconsumed observation state includes, for example:

- terminal result/failure/cancellation;
- `awaiting_controller` checkpoint;
- ProjectScope attachment recovery/quarantine/generation mismatch;
- recovery pending;
- uncertain state;
- changed result/evidence publication;
- a controller-relevant event/watermark not yet consumed.

Soma must not derive semantic actions such as retry, edit, delegate, or complete.

---

# 10. Atomic continuation-associated Task creation

## 10.1 Existing seam already proves feasibility

`TaskStore.reserve_task_in_connection()` exists so another authority can reserve a canonical Task inside a shared SQLite transaction.

ProjectScope and Company admission already use the pattern:

```text
BEGIN
 -> validate higher-level authority/version
 -> reserve ProjectScope attempt if needed
 -> TaskStore.reserve_task_in_connection
 -> attach scope/owner relation
COMMIT
 -> launch backend effect afterward
```

`ExecutionBackend.reserve()` allocates an inert backend reference without launching work.

## 10.2 Future continuation-associated action pattern

Sol first decides, inside the reasoning loop, that an action should be taken. The continuation substrate then atomically records that action relationship before the existing Task authority launches it.

Research target:

```text
reserve inert backend identity

BEGIN IMMEDIATE
 -> validate continuation open + expected version
 -> validate continuation command replay/hash
 -> validate/reserve ProjectScope if needed
 -> reserve canonical Task via existing TaskStore seam
 -> insert continuation-to-Task association/control provenance
 -> establish initial consumed controller-observation fingerprint
 -> attach ProjectScope Task relation if needed
 -> record continuation command / advance continuation version
COMMIT

existing Task/backend launch authority continues
```

## 10.3 Critical rule

A future `ContinuationManager` or continuation coordinator must **not copy TaskManager execution/reconciliation logic**.

The continuation component coordinates durable association/provenance only; Task/Run remain execution authorities, and Sol's reasoning loop remains the authority that decides whether any next action exists.

---

# 11. Normal-Chat reasoning-loop continuation behavior

## 11.1 Persist continuation only when useful

Do not create a continuation record for every Chat or every reasoning turn.

Reasonable trigger conditions include:

- action may outlive current Chat turn/session;
- multiple durable actions belong to one user objective;
- interruption/recovery matters;
- uncertain effects must survive;
- Sol needs exact “what changed since I last looked?” state.

For one immediate action whose result returns in the active turn, direct Soma tool/Task use remains valid.

## 11.2 Continuing after owner wakes Chat

```text
owner: continue
Sol: list/retrieve relevant open continuation
Soma: objective + linked Task state + unconsumed changes + uncertainty
Sol: interprets
Sol: acknowledges exact observations
Sol: chooses next action(s) or completion
```

No old Chat thread ID is required.

## 11.3 Multiple durable continuations are legitimate

Do not enforce one continuation record per user/project. Several independent Sol reasoning objectives may be active simultaneously.

Fresh Chat can list recent/open continuations and select by continuation ID/label/context.

If ambiguous, Sol asks the owner.

## 11.4 Completion is explicit

```text
all Tasks terminal
```

is not equal to:

```text
goal complete
```

Only after Sol/the owner semantically decides the reasoning objective is complete or cancelled may the corresponding continuation record be closed. Task terminality never advances or completes the reasoning loop.

---

# 12. Existing Agent/Worker component inventory

This is the final research classification.

## KEEP - core shared substrate

### Canonical Task

Role: durable action/execution identity.

### RunStore / JobManager / process ownership

Role: durable external/process execution, cancellation, recovery, evidence/publication.

### ExecutionBackend protocol + DurableRunBackend

Role: backend-neutral execution seam.

### ProjectScope

Role: exact resource/generation ownership and containment.

### `awaiting_controller` / checkpoints / interaction transition mechanics

Role: a still-running Task pauses for controller input and resumes safely.

### Task result/evidence references

Role: canonical observations consumed by Sol/Work.

### Parallel command groups

Role: deterministic execution concurrency, “more hands” without more minds.

### Hermes headless tool runtime

Role: tool/execution capability only.

### Canonical memory/knowledge

Role: durable facts/decisions/context, separate from transactional continuation state.

---

# 13. KEEP but MOVE/REPOSITION as optional specialist infrastructure

## Worker interaction substrate

Use only when a real subordinate provider/session exists.

## Worker authority/capability broker

Valuable security boundary for restricted subordinate workers; not normal owner/Sol path.

## Worker gateway

Keep dormant unless a real subordinate worker needs Soma capability.

## Worker process containment

Reusable lower-level safety for any owned child process.

## EvidenceSubmissionV1

Use for semantic specialist outputs/evidence, not every Task.

## FanInV1

Use for genuine multi-specialist aggregation, not ordinary action loops.

## Reasoning backend lifecycle/store mechanics

Keep persist-before-provider-send, provider-binding, ambiguity, cancellation, publication and provenance mechanics.

Reposition as **optional intelligent/specialist provider infrastructure**, not Soma's default brain.

## Codex repository backend/runtime

Keep as owner-gated provider-specific optional specialist adapter.

No automatic use.

## Return-loop/PulseSender contract

Keep as optional delivery transport.

---

# 14. RE-EVALUATE / RENAME / compatibility-hold

## `TaskKind.REASONING`

A deliberately delegated intelligent specialist may legitimately be a canonical Task.

But Sol's own reasoning turn must never be represented as a subordinate reasoning Task.

Current enum may remain for compatibility initially, then be superseded/renamed only with a migration/public-schema gate.

## `BackendKind.SOMA_REASONING`

Same conclusion: useful compatibility/provider-operation identity, misleading as core architecture terminology.

## `start_reasoning`

Public schema exists but runtime is owner-disabled by default.

Initial realignment should leave it disabled/optional and change architectural interpretation first.

Later decide whether to retain as legacy name or add a neutral specialist route and deprecate it.

## Company reasoning-specific acceptance branch

Historical compatibility required; future Company reopening may generalize prospective backend acceptance without rewriting existing hashes/rows.

---

# 15. DEPRECATE / converge prospectively

## LocalAgentOrchestrator semantic routing

Target status: **deprecate as cognitive authority**.

Reason:

- keyword intent classification;
- local model route;
- decides command/model/supervisor/external coder path.

Sol already performs this semantic decision better and should own it.

Good news: it is not a public gateway, so the new loop can bypass it without immediate public schema change.

Preserve mechanical helper dependencies temporarily.

## Supervisor cognitive lifecycle

Target status: **stop using for new normal Sol-controlled work; later retire creation path**.

Reason:

- planning;
- heuristic route selection;
- local model planning;
- external-coder decision;
- recommended next action.

Preserve historical query/read and salvage validation/report/notification mechanics.

## Legacy `soma/jobs/LongRunJobManager`

Target status: retire execution path.

It already admits in source that in-memory process ownership cannot survive manager recreation and directs unattended work to durable JobManager/RunStore.

## Legacy local-agent memory writes

Target status: continue convergence to canonical knowledge/memory authorities.

---

# 16. Workflow final classification

Workflow is not the Sol cognitive loop.

However it retains a legitimate niche for explicit deterministic dependency-ordered work where no fresh Sol judgment is needed between steps.

Because Workflow is a public gateway with dedicated tests/README/discovery contracts, the first Sol-loop patch should leave it intact.

Longer-term options:

- retain a narrow deterministic workflow engine;
- converge steps onto canonical Tasks;
- remove independent lifecycle authority while keeping graph projection;
- deprecate only overlapping creation modes.

**Final research classification:** KEEP COMPATIBILITY / REPOSITION / LATER CONVERGENCE.

---

# 17. Supervisor final classification

Supervisor has weaker unique value because its semantic planning/routing overlaps Sol directly.

Because it is still public, deletion in the first patch is inappropriate.

Recommended future convergence:

1. stop routing new normal work through Supervisor;
2. retain historical `supervisor_query`;
3. salvage validation, notification, resume-report artifacts;
4. deprecate `supervisor_action.start` after consumer measurement;
5. retire lifecycle creation once replacement/evidence exists.

**Final research classification:** PUBLIC COMPATIBILITY HOLD / COGNITIVE ROLE DEPRECATED / LATER RETIREMENT CANDIDATE.

---

# 18. Company/Mission/Plan final classification

Company remains frozen.

The original Company architecture is not inherently contrary to Sol-centric design. It already names ChatGPT/Cortana as executive authority and treats providers/workers as optional/disposable.

Useful durable concepts:

- Company identity;
- Mission;
- PlanRevision as explicit accepted organizational commitment;
- route-neutral WorkPackage;
- WorkPackageAttempt -> canonical Task;
- ProjectScope;
- OutcomeAcceptance distinct from process success;
- projection-based lifecycle derivation.

Current defect:

```text
reserve_attempt
 -> required ReasoningSpec
 -> TaskKind.REASONING
 -> SOMA_REASONING
```

This contradicts the original “optional providers degrade cleanly” law.

If Company is ever explicitly reopened, attempt admission should be re-researched as provider-neutral canonical Task routing, and V3-3+ cognition should be reevaluated against current ChatGPT Work.

Normal Chat loop must not touch Company.

---

# 19. Exact conceptual errors introduced by the previous Agent/Worker plan

The research identified specific transitions rather than blaming all worker code.

## Error 1 - conflating “normal Chat lacks durable agentic continuation” with “Soma needs a reasoning worker”

The missing capability was controller continuity around Sol.

The proposed solution became external model cognition.

These are not the same problem.

## Error 2 - promoting semantic reasoning into a core Task/backend category

G2 added:

```text
TaskKind.REASONING
BackendKind.SOMA_REASONING
```

The durable mechanics were good, but the architecture started treating semantic work as naturally belonging to a provider backend.

## Error 3 - reasoning worker becomes “the semantic actor”

Later G6 benchmark language explicitly says the reasoning worker reads material, answers, and chooses evidence while Sol performs downstream adjudication.

That can be valid for an **optional specialist benchmark**, but it was allowed to harden into a general architecture model.

## Error 4 - Company work admission becomes reasoning-provider admission

WorkPackage attempt admission became structurally dependent on the reasoning backend even though original Company rules say providers are optional.

## Error 5 - failing to keep Work's native agentic capability separate from Soma's role

Current Work now provides native multi-step agent cognition/subagents. Continuing to place another reasoning loop underneath it is redundant.

## Error 6 - legacy semantic routers remained conceptually available

LocalAgent and Supervisor contain intent classification/planning/routing that compete with Sol.

These are historical layers, not the corrected control authority.

---

# 20. Exact drift timeline

## 2026-07-18

Historical achievement record states:

```text
ChatGPT owns reasoning, implementation decisions, and managed source changes.
```

**Meaning:** original Sol/ChatGPT reasoning ownership.

## 2026-07-26

Strategic architecture says schedules do **not** start a hidden general reasoning loop; when judgment is needed, transition to `awaiting_controller`.

Delivery is separate from task outcome.

**Meaning:** original missing-continuation concept was already correct.

## 2026-08-02

`awaiting_controller` / resume/recovery mechanics become real implementation.

**Meaning:** strong aligned infrastructure.

## 2026-08-12 - Agent/Worker Iteration 1

`reasoning_worker` introduced as one future worker category/backend possibility while Sol remains proposed head.

**Meaning:** conceptual broadening; not yet fatal.

## 2026-08-12 - G2 / commit `fcba03c2...`

`TaskKind.REASONING` and `BackendKind.SOMA_REASONING` become canonical.

**Meaning:** primary transition from optional idea to first-class architecture route.

## 2026-08-12/13 - later Agent/Worker research/G6

Reasoning worker becomes the semantic actor for assignments; Sol adjudicates later.

**Meaning:** drift hardens.

## 2026-08-14

Owner-gated public reasoning Task activation path is added; Company attempt admission relies on reasoning route.

Production reasoning remains disabled.

**Meaning:** architecture becomes activation-ready but has not become unavoidable live runtime behavior.

## 2026-08-15 - this realignment track

Research re-establishes:

```text
Sol cognition
 -> Soma durable actions/observations
 -> Sol cognition
```

and moves provider reasoning to optional specialist branch.

---

# 21. Missing capabilities inventory

## Missing capability A - lightweight durable objective/loop identity

Needed for a goal spanning multiple terminal Tasks/Chat turns.

## Missing capability B - loop-to-Task control ownership

Needed to group exact actions under one objective without redefining Task.

## Missing capability C - “what changed since Sol last looked?” bookkeeping

Best current hypothesis: per-Task last-consumed observation fingerprint.

## Missing capability D - stale-safe observation acknowledgement

Needed so Sol cannot accidentally acknowledge a newer state it did not inspect.

## Missing capability E - explicit loop completion/cancellation

Needed because Task terminality cannot semantically close the user goal.

## Missing capability F - compact fresh-Chat discovery/continuation projection

Needed for owner “continue” after refresh/new Chat.

## Missing capability G - atomic continuation-associated Task reservation

No new execution engine needed; existing transaction seam can support it.

Everything else required for the initial loop largely already exists.

---

# 22. Things that are **not** missing core capabilities

Do not mistake these for blockers:

- external reasoning model;
- Codex;
- native subagents in normal Chat;
- new Worker manager;
- new DAG engine;
- new workflow scheduler;
- automatic Chat wake-up;
- Company Kernel;
- mission planner;
- separate memory system;
- new result/evidence authority;
- second process/job manager.

The absence of those does not prevent the Sol loop.

---

# 23. Compatibility and migration concerns

## 23.1 Public schema stability

Workflow, Supervisor and `start_reasoning` are current public contract elements.

Do not remove them incidentally while adding the loop.

## 23.2 Historical reasoning data

Existing Task/backend/evidence/Company AcceptanceCommit rows and hashes must remain interpretable.

Do not rename persisted enum values in-place without a migration/compatibility strategy.

## 23.3 Company history

Company acceptance hashes and backend-specific validation branches are historical evidence.

Future generalization must preserve old contracts.

## 23.4 Workflow/Supervisor historical records

Even if new creation stops later, query/read access may need to remain indefinitely or through a defined compatibility horizon.

## 23.5 Task semantics

Do not weaken canonical Task terminality to accommodate the goal loop.

A terminal Task stays terminal.

## 23.6 Workspace fields

Task `workspace_kind/workspace_ref` already mean repository workspace and must not be reused for loop ID.

## 23.7 Task links

Current typed Task links do not naturally represent a higher-level loop owner. A dedicated loop membership table is cleaner than overloading link semantics.

## 23.8 Memory

Do not use fuzzy memory retrieval as the authority for transactional observation consumption or Task ownership.

---

# 24. Risks of the realignment

## Risk 1 - building too much loop infrastructure

Mitigation: keep the three-authority minimal contract; no turn/observation table until evidence demands it.

## Risk 2 - creating another lifecycle authority

Mitigation: continuation-record lifecycle only `open/completed/cancelled`; derive action status from Tasks. This lifecycle does not advance the Sol reasoning loop.

## Risk 3 - accidentally forking Task execution

Mitigation: use `reserve_task_in_connection` / existing TaskManager seams; no duplicate launcher/reconciler.

## Risk 4 - duplicate effect after loop/Task race

Mitigation: commit loop membership + Task reservation before backend launch.

## Risk 5 - stale observation acknowledgement

Mitigation: recompute the complete aggregate ControllerObservation hash transactionally, not only Task-row fields.

## Risk 6 - new loop becomes mandatory for simple work

Mitigation: direct Task/tool path remains first-class.

## Risk 7 - old Supervisor/Workflow remains accidentally preferred

Mitigation: new architecture/docs/metadata route normal continuation to Sol loop; later deprecate legacy creation.

## Risk 8 - optional specialist path creeps back into default

Mitigation: explicit invariant: Task failure/result returns attention to Sol; no automatic provider escalation.

## Risk 9 - Work duplication

Mitigation: Work uses shared substrate directly and does not require a ControllerContinuation driver; Work owns its own reasoning loop.

## Risk 10 - Company gets accidentally unfrozen

Mitigation: no Company dependency/change in initial Sol-loop implementation.

## Risk 11 - loop membership bypasses ProjectScope

Mitigation: `loop_id -> task_id` proves continuation/control relationship only. Every scoped read/mutation must still resolve and honor current ProjectScope identity, generation, attachment, and quarantine truth.

## Risk 12 - controller-relevant transition disappears between queries

Mitigation: prove the ControllerObservation hash domain covers every relevant existing authority; include an authoritative event/recovery watermark where a transient relevant transition could otherwise disappear.

## Risk 13 - loop-created Task request IDs collide across projects/loops

Mitigation: Task `controller_request_id` is globally unique today. Derive stable replay-safe child Task request identities from continuation + continuation command + action identity/index rather than reusing an unscoped human token.

## Risk 14 - loop design overclaims same-repository mutation parallelism

Mitigation: preserve current repository/resource lock granularity. ControllerContinuation keeps reasoning/continuation bookkeeping outside that lock domain; it does not silently replace repository-wide mutation locking with file-level conflict detection.

---

# 25. Recommended future implementation sequence

This is a **research recommendation only**. It is not authorization to implement.

## Phase 0 - explicit supersession/authority gate

Before code:

- create one reviewed realignment implementation plan;
- cite this research series;
- explicitly state Company remains frozen;
- explicitly state reasoning/Codex remains disabled unless owner separately authorizes;
- define exact files/public-schema scope;
- record which historical Agent/Worker interpretation is superseded without rewriting old gates.

## Phase 1 - minimal internal ControllerContinuation schema/models/store

Add only:

```text
controller_continuations
controller_continuation_tasks
controller_continuation_commands
```

Requirements:

- additive migration;
- idempotent command journal;
- CAS state version;
- no provider/model fields;
- no Company dependency;
- no service activation side effect;
- no repository/resource lock acquisition for loop creation, reasoning, continuation, observation reads, or bookkeeping;
- short SQLite transactions only; never hold a write transaction across Sol reasoning, backend/tool waits, owner wake-up, or Task waits;
- no public tool yet if an internal proof is safer first.

## Phase 2 - aggregate ControllerObservation fingerprint + continuation projection

Implement a versioned mechanical continuation projection computed from existing canonical authorities rather than hashing only the Task row.

Prove:

- terminal Task change becomes unconsumed;
- running/no-change does not create noise;
- ProjectScope attempt recovery/quarantine/generation changes become unconsumed even if Task-row fields do not otherwise change;
- checkpoint/recovery/uncertainty changes appear;
- controller-relevant event/recovery transitions cannot disappear unseen;
- stale acknowledgement fails if any included authority changed;
- acknowledgement never changes Task/ProjectScope/checkpoint truth;
- no copied observation table is required;
- no semantic recommendation is generated.

## Phase 3 - atomic continuation-associated Task reservation

Coordinate:

- loop CAS/idempotency;
- ProjectScope where needed;
- existing canonical Task reservation;
- loop membership;
- initial aggregate ControllerObservation baseline;
- stable collision-safe Task controller-request identity derived for the loop action;

in one short SQLite transaction before backend launch.

`loop_id -> task_id` membership is **not** an authority bypass. Scoped Task reads/actions through the loop must continue to honor canonical ProjectScope project/resource identity, scope generation, attachment, and quarantine status.

This transaction establishes durable logical ownership only. **Task/loop ownership must not acquire a repository operation lock.** If the selected backend later performs a mutation that requires exclusive resource ownership, that concrete execution path acquires the appropriate repository/resource lock independently and releases it according to that resource authority's existing granularity/lifetime.

Do not duplicate TaskManager backend launch/recovery.

## Phase 4 - compact public continuation query/action surface

Only after internal proof.

Likely minimal concepts:

Query:

```text
capabilities
list
status / continuation
```

Actions:

```text
create
update_context
start_task / attach owned Task through coordinator
ack_observations
complete
cancel
```

Exact operation topology remains for implementation design.

Metadata must explain:

- use loop only for durable multi-turn normal-Chat continuation;
- direct Task/tools remain valid;
- loop does not reason;
- loop does not activate external model providers.

## Phase 5 - normal-Chat UX/Skill guidance, only if empirically useful

Teach normal Chat to:

- use direct Soma tools for simple work;
- establish loop when continuation durability adds value;
- query unconsumed observations after re-entry;
- reason itself;
- explicitly complete the loop.

Skill is guidance, not authority.

## Phase 6 - validation on real interrupted workflows

Test scenarios:

- one immediate Task;
- multi-Task sequential reasoning;
- parallel independent Tasks;
- long job while Chat disappears;
- Task failure;
- uncertain external effect;
- running Task `awaiting_controller`;
- machine/Soma restart;
- fresh Chat “continue”;
- stale acknowledgement;
- replayed continuation command;
- loop completion while Tasks active;
- no reasoning provider installed/enabled;
- multiple independent Sol reasoning objectives use ControllerContinuations concurrently across unrelated projects;
- multiple loops may read/inspect the same repository concurrently without acquiring its operation lock;
- concrete repository mutations continue to serialize according to current repository/resource lock granularity; ControllerContinuation does not widen or falsely refine it;
- ProjectScope attempt recovery/quarantine/generation change becomes visible even when Task-row state alone would miss it;
- loop membership cannot bypass ProjectScope authority checks;
- controller-relevant transient/event-only change cannot disappear between continuation queries;
- loop-created Task controller request identities remain collision-safe across simultaneous loops/projects and replay to the same Task;
- loop SQLite transactions release before any Sol/tool/backend/wait interval;
- Work direct Soma use remains unaffected.

## Phase 7 - route correction, not deletion

After loop proves useful:

- make new normal reasoning-loop continuation use ControllerContinuation rather than Supervisor/LocalAgent;
- leave public Workflow/Supervisor compatibility intact initially;
- document `start_reasoning` as optional specialist route;
- do not enable it.

## Phase 8 - separate legacy convergence packages

Only later, separately reviewed:

- Supervisor creation deprecation;
- LocalAgent internal dependency cleanup;
- Workflow convergence/narrowing;
- optional specialist terminology/public migration;
- Company provider-neutral admission if and only if Company is explicitly reopened.

---

# 26. Explicit things that should **NOT** be implemented in the first realignment

1. **Do not** enable `reasoning.enabled`.
2. **Do not** invoke Codex.
3. **Do not** make Codex/Claude/Hermes/local model the normal Chat brain.
4. **Do not** create a new reasoning-worker manager.
5. **Do not** build a general DAG, stage runner, or Task loop inside ControllerContinuation.
6. **Do not** create a turn table unless later evidence proves necessary.
7. **Do not** copy Task states/results into loop observation rows.
8. **Do not** create a second Task/Run executor.
9. **Do not** reimplement TaskManager launch/reconciliation inside the loop.
10. **Do not** use Company/Mission/Plan for ordinary Chat goals.
11. **Do not** unfreeze Company.
12. **Do not** alter Company admission as part of the loop patch.
13. **Do not** remove Workflow/Supervisor public gateways in the first patch.
14. **Do not** delete reasoning-provider durability mechanics merely because their framing drifted.
15. **Do not** require EvidenceSubmission/FanIn for ordinary Tasks.
16. **Do not** require Worker gateway/authority for normal Sol actions.
17. **Do not** build PulseSender/Chrome wake-up as a blocker.
18. **Do not** bind loop truth to one Chat conversation/thread ID.
19. **Do not** infer Chat vs Work from behavior.
20. **Do not** store private chain-of-thought.
21. **Do not** automatically escalate failures to another model.
22. **Do not** automatically launch a summarizer/model for large outputs.
23. **Do not** treat all Tasks terminal as semantic goal completion.
24. **Do not** rewrite accepted historical gate documents.
25. **Do not** acquire or retain a repository/resource operation lock for ControllerContinuation state, Sol reasoning, planning, evidence reads, continuation queries, or observation acknowledgement.
26. **Do not** infer that Task ownership or ProjectScope membership grants exclusive repository ownership.
27. **Do not** hold a SQLite write transaction while Sol reasons or while any external Task/tool/backend/owner response is pending.

---

# 27. Historical supersession strategy

The repository contains accepted historical evidence that remains factually true even where the architectural interpretation is no longer preferred.

Recommended policy:

## Preserve

- G2 reasoning Task acceptance;
- G6 benchmark/evidence results;
- V3-1A worker interaction acceptance;
- Company outcome acceptance;
- public schema identity records;
- old roadmap/legacy documents.

## Add later

One explicit architecture realignment/supersession record stating:

- the mechanical properties remain accepted;
- `reasoning worker / reasoning backend` is no longer the core normal-Chat control architecture;
- reasoning-provider routes are optional specialist compatibility paths;
- Sol/Work owns semantic cognition according to surface;
- ControllerContinuation becomes the normal-Chat durable continuation authority if implementation is accepted; the actual reasoning loop remains Sol's cognitive cycle.

## Never

Do not edit old accepted docs so they appear to have said something they did not.

Historical honesty is more valuable than terminology neatness.

---

# 28. Terminology recommendation

## `Sol`

Main ChatGPT reasoning authority in this owner architecture.

## `Sol reasoning loop`

The actual cognitive cycle owned by Sol: `reason -> decide -> act -> observe -> reason`. This is what **loop** means in this architecture. It is not a Soma table, Task state machine, workflow, scheduler, or sequence of Tasks.

## `ControllerContinuation` / working implementation name

Lightweight durable objective/continuation state that lets the Sol reasoning loop survive interruption.

It does **not** reason, loop, schedule, advance stages, or choose the next Task. Avoid using `loop` in the persisted component/API name, because that invites the exact Task-loop/workflow misinterpretation this realignment is removing.

## `Task`

Canonical durable action/execution identity.

## `Run`

Concrete execution/process/provider-run authority where applicable.

## `specialist`

A deliberately delegated bounded intelligent capability; optional.

## `subagent`

Reserve for genuine native/provider independent agent loops, especially Work/Codex product terminology.

Do not call headless Hermes execution processes subagents.

## `worker`

Subordinate execution/capability principal; does not imply cognition.

## `reasoning backend`

Legacy/current code term. In new architecture prose, prefer “optional specialist provider/backend” unless referring to the exact historical/current implementation name.

## `controller`

The semantic decision authority is Sol/Work/owner according to context; Soma stores controller-visible state but does not semantically control the objective.

---

# 29. Why the corrected design helps rather than burdens Sol

The owner explicitly wanted the add-on to make Sol more capable, not more difficult to use.

The minimal architecture satisfies that by avoiding unnecessary ceremony.

## Simple task

```text
Sol -> Soma tool/Task -> result -> Sol
```

No loop required.

## Long/multi-turn task

```text
Sol -> lightweight loop + Task(s)
Chat disappears
Soma keeps exact execution truth
owner returns
Sol receives only what changed
Sol continues
```

No need to rediscover all Tasks manually.

## No duplicated thinking

Soma does not force Sol to review another model's plan every cycle.

## Context efficiency

Continuation bundle contains:

- objective/context refs;
- active linked Tasks;
- only unconsumed Task changes;
- result/evidence pointers;
- uncertainty/checkpoints.

It does not dump full logs/transcripts/repeated evidence.

## Recovery safety

Exact Task identities and observation hashes prevent “I think this probably finished” guessing after interruption.

This is the actual value of the add-on.

---

# 30. Why the corrected design also helps Work

Work gets Soma's strongest features without a second planner:

- durable external actions;
- machine/service access;
- exact evidence;
- restart/recovery truth;
- memory/project state;
- long-running external operations.

Work keeps its native:

- planning;
- semantic continuation;
- native subagents;
- result synthesis.

This prevents token/context waste and ownership conflicts.

---

# 31. Why the Agent/Worker investment was not wasted

The programme built many difficult pieces that the corrected architecture still needs for optional delegation and safe external execution:

- provider-neutral Task/backend seam;
- precise idempotency;
- persist-before-send;
- outcome-unknown handling;
- process containment;
- capability broker;
- isolated worker gateway;
- evidence/provenance envelopes;
- deterministic FanIn;
- restart recovery;
- bounded public projections;
- provider binding identity.

The mistake was mainly **placement and default-role interpretation**, not engineering quality.

The realignment therefore gains a lot by moving these parts to the side branch rather than deleting them.

---

# 32. Open questions intentionally left open

Research is complete enough for implementation planning, but these details should be resolved during a reviewed plan/prototype rather than guessed now.

1. Final public name for the durable substrate: `controller_continuation` or another non-`loop` term that cannot be confused with the Sol reasoning loop.
2. Exact ControllerObservationV1 field set/hash domain/version.
3. Exact continuation command operations and request-ID scoping.
4. Whether a continuation can adopt an already-running Task as control owner in v1 or only reference its evidence.
5. Exact active-Task policy when Sol closes/cancels a continuation after making a semantic reasoning decision.
6. Objective/constraints reference storage: artifact vs knowledge/memory reference vs dedicated content-addressed payload.
7. Fresh-Chat continuation ranking/discovery UX when several open continuations exist.
8. Whether an optional continuation label is user-authored, Sol-authored, or derived.
9. Whether public continuation gateways are separate `continuation_query/continuation_action` or another clean controller-plane topology.
10. Whether Work ever benefits from using the same continuation record as optional external objective grouping; not needed for v1.
11. Future neutral naming/migration for `reasoning` specialist Task/backend.
12. Future Company provider-neutral admission design, only if Company is explicitly reopened.

None of these blocks the core architectural conclusion.

---

# 33. Final answer to the original research questions

## Q1. Current Chat vs Work distinction?

Chat is conversational; Work is the native longer multi-step agentic ChatGPT surface. Do not assume ordinary Chat has the same agent loop/subagent surface.

## Q2. Which agentic behavior should Soma not duplicate?

Work's planning, multi-step cognition, native subagent orchestration, and semantic result synthesis.

## Q3. What native subagents exist?

Current OpenAI docs describe Work/Codex subagent workflows. They are best for independent bounded parallel work and carry extra token/coordination cost.

## Q4. Who remains reasoning authority?

The main Work/ChatGPT thread collects/synthesizes delegated results. In the owner's architecture Sol/main ChatGPT remains the important decision authority.

## Q5. What is actually missing for `Sol -> act -> observe -> Sol`?

A lightweight durable objective/membership/observation-consumption layer above canonical Tasks.

## Q6. Which existing Agent/Worker pieces solve parts of it?

Task/Run identity, idempotency, backend abstraction, recovery, checkpoints, evidence refs, ProjectScope, process ownership, provider durability, and transaction seams.

## Q7. Which pieces came from worker-centric drift?

Core elevation of reasoning worker/backend, LocalAgent/Supervisor semantic routing, reasoning-only Company attempt admission.

## Q8. Proper role of major components?

- Task: action identity.
- backend: execution route.
- Evidence/FanIn: optional specialist aggregation.
- reasoning backend: optional specialist provider mechanics.
- Codex: explicit-owner-authorized specialist.
- Hermes: headless execution/tools.
- Workflow: explicit deterministic sequence compatibility/niche.
- Supervisor: legacy compatibility; cognitive role to retire.
- Company/Mission/Plan: frozen optional organizational layer, not normal loop.

## Q9. Should reasoning backend remain first class?

Not as the core cognitive axis. Preserve it as optional specialist/provider infrastructure for compatibility, with future terminology cleanup.

## Q10. Separate Sol reasoning-loop cognition from continuation/execution state?

Yes. Sol owns the cognitive reasoning loop. The minimum durable continuation state must be separate from Task execution state, because one reasoning objective spans zero/one/many Tasks and Task terminality is only execution truth.

## Q11. What durable state does Sol require?

Minimum: objective/context refs, loop version/lifecycle, linked Task identities, exact last-consumed **aggregate ControllerObservation fingerprints**, idempotent loop mutations, explicit completion/cancellation. The observation body itself remains computed from existing authorities rather than copied into loop storage.

## Q12. How does control return to Sol?

Mechanically expose new/unconsumed controller observations derived from canonical Task + relevant ProjectScope/checkpoint/recovery/event authority. The owner can manually wake Chat. Optional delivery adapters can notify later.

## Q13. How represent waiting/new observation/completion?

Derived mechanical facts from linked canonical authorities plus explicit loop completion, not a semantic Soma state machine.

## Q14. How survive interruption/restart?

Loop/Task/Run/command state in durable SQLite + canonical evidence and replay/CAS semantics. No reasoning ownership transfer occurs.

## Q15. How does Company complement the loop?

Only as optional formal organizational truth for large missions. It must not duplicate Work/Sol working plans or be required for normal Chat.

## Q16. Where did drift happen?

Primarily August 12 G2 when reasoning became a canonical Task/backend and later G6 when reasoning worker became semantic actor; later Company admission made that route structurally central.

## Q17. Terminology correction?

Separate Sol/controller cognition, execution worker, specialist/subagent, provider backend, and Task/Run identity. Stop using “reasoning backend” as shorthand for Soma's brain.

## Q18. Corrected target preserving useful work?

Sol/Work owns cognition; lightweight normal-Chat loop owns continuation bookkeeping; Task/Run owns execution; existing worker/provider machinery becomes optional subordinate specialist infrastructure.

---

# 34. Research completion verdict

**RESEARCH COMPLETE FOR IMPLEMENTATION-PLAN AUTHORITY.**

The architecture is now supported by:

- current product evidence;
- repository history;
- source contracts;
- tests;
- accepted historical gates;
- explicit owner requirements.

Further broad research is not currently needed before drafting a bounded implementation plan.

The next step, **only after owner approval**, should be a separate implementation-planning phase for the minimal normal-Chat ControllerContinuation substrate supporting the Sol reasoning loop.

That plan should begin from this constraint:

> Add the smallest durable continuation layer around Sol. Keep reasoning/continuation outside repository operation locks across simultaneous projects; Task/loop ownership must not imply repository ownership; preserve existing resource-lock granularity for concrete mutations rather than widening it; keep loop database transactions short; derive continuation from an aggregate canonical ControllerObservation so ProjectScope/checkpoint/recovery/event truth cannot disappear; never let loop membership bypass ProjectScope; namespace loop-created Task request identities for collision-safe replay. Do not touch Company, do not activate reasoning providers, do not invoke Codex, do not remove public legacy gateways, and do not fork canonical Task/Run execution.

No implementation begins in this research thread without the owner explicitly moving us into that phase.

---

# 35. Source index

## Realignment research

- `docs/sol-agentic-loop-realignment-research/iteration-01-current-chatgpt-work-native-agent-reality-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-02-original-intent-drift-and-normal-chat-addon-boundary-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-03-minimal-durable-sol-control-loop-state-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-04-mode-aware-chat-vs-work-integration-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-05-minimal-loop-contract-pressure-test-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-06-agent-worker-component-reuse-and-reposition-audit-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-07-specialist-boundaries-and-atomic-loop-task-ownership-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-08-company-mission-plan-interaction-with-sol-loop-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-09-legacy-public-surface-overlap-and-compatibility-audit-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/reaudit-2026-08-15-sol-loop-research.md`

## Key historical Soma architecture/evidence

- `docs/legacy/Soma_Roadmap_V2_Achievement_Record_2026-07-18.md`
- `docs/legacy/Soma_Roadmap_V2_Strategic_Architecture_2026-07-26.md`
- `docs/V3_1A_INTERACTIVE_WORKER_SUBSTRATE_PLAN_2026-07-30.md`
- `docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md`
- `docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`
- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md`
- `docs/agent-worker-research/*`
- `docs/V3_1B_OUTCOME_ACCEPTANCE_1_RESULT_2026-08-14.md`
- `docs/V3_1B_CONTROLLED_LIVE_KERNEL_OF_ONE_ACTIVATION_1_GATE_2026-08-14.md`
- `PLANS.md`

## Key source authorities

- `soma/tasks/*`
- `soma/run_store.py`
- `soma/job_manager.py`
- `soma/operation_locks.py`
- `soma/project_scope/*`
- `soma/worker_substrate/*`
- `soma/worker_authority/*`
- `soma/worker_gateway/*`
- `soma/worker_process/*`
- `soma/worker_evidence/*`
- `soma/reasoning/*`
- `soma/workflows/*`
- `soma/supervisor/*`
- `soma/local_agent/*`
- `soma/company_kernel/*`
- `soma/return_loop/*`
- `soma/public_gateway_inventory.py`
- `soma/public_tool_metadata.py`
- `soma/cf1_gateway_operation_inventory.py`
- `soma/server.py`

## Current official OpenAI sources consulted across research

- OpenAI Help Center - `ChatGPT Work and Codex`
- OpenAI - `ChatGPT Work`
- OpenAI / ChatGPT Learn - `Subagents`
- OpenAI API - `Model guidance`
- OpenAI Agents SDK - `Running agents`, `Results`, `Sessions`
- OpenAI Help Center - `Plugins in ChatGPT and Codex`
- OpenAI Help Center - `Skills in ChatGPT`

## Owner-supplied historical context

- `CodexBridge Local Agent Expansion Roadmap v2`
