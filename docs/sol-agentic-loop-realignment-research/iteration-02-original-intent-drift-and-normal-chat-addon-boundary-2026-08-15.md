# Iteration 2 - Original Intent, Drift Trace, and Normal-Chat Add-on Boundary

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected: `938f1764dcab30a8bd8235ea2c822ba6d8c0826c`

## Scope

Iteration 1 established the current OpenAI product distinction: normal Chat and Work are different surfaces; Work already supplies native multi-step agentic behavior and subagents, while ordinary Chat should not be assumed to have the same native agentic loop.

Iteration 2 reconstructs the owner's original Soma intent from repository history, identifies the conceptual point where the Agent/Worker programme moved away from that intent, and freezes the boundary for the desired **normal-Chat agentic reasoning add-on**.

This iteration does **not** design the final state machine yet. It determines what the add-on is and is not, so later research cannot accidentally substitute a second reasoning model for Sol.

## Hard constraints

No implementation is authorized by this document.

No runtime/service restart, Company activation, reasoning-provider activation, Codex use, Codex App Server/API/CLI use, provider generation, production config change, push, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

Company remains frozen.

The owner additionally clarified during this iteration that automatic wake-up/delivery into an exact normal Chat thread is **not a core architecture requirement for now**. The owner can wake the Chat manually. PulseSender or a future browser/Chrome extension may later improve delivery UX, but they are optional transport and must not become a reason to introduce another reasoning model.

Classification labels:

- **DOCUMENTED FACT** - current official OpenAI documentation established in Iteration 1.
- **REPOSITORY FACT** - current or historical Soma source/docs/Git evidence.
- **OWNER REQUIREMENT** - explicit owner direction.
- **INFERENCE** - conclusion supported by evidence but not itself directly recorded as a fact.
- **OPEN QUESTION** - intentionally unresolved for later research.

---

# 1. The original architectural center was ChatGPT, not a Soma reasoning worker

## 1.1 July controller boundary

**REPOSITORY FACT**

`docs/legacy/Soma_Roadmap_V2_Achievement_Record_2026-07-18.md` records the controller boundary explicitly:

> ChatGPT owns reasoning, implementation decisions, and managed source changes.

The same section says Soma had no coding-agent worker/router/CLI runner in the active architecture and treats removed legacy execution routes as compatibility history rather than active capability.

This is unusually strong historical evidence because it is not merely an aspirational diagram. It appears in the achievement record describing the accepted control-plane state.

## 1.2 Existing useful control-plane foundations were already separated from cognition

**REPOSITORY FACT**

The same achievement record lists useful Soma foundations including:

- repository-scoped tools and capability metadata;
- managed repository operations;
- SQLite-backed durable runs and artifacts;
- workflows/supervisors/cancellation/events/heartbeats;
- project commands and validation runners;
- return-loop reports and PulseSender-compatible manifests;
- SSH and external-machine execution.

The document says these should be **extended rather than replaced**.

**INFERENCE**

The original value proposition was already close to the owner's current correction:

```text
ChatGPT/Sol = judgment and decisions
Soma        = durable operational substrate
```

The missing capability was continuity/control around ChatGPT's reasoning, not a new permanent reasoning brain underneath ChatGPT.

---

# 2. The pre-drift roadmap already described the missing Sol return boundary

## 2.1 Durable scheduling explicitly rejected a hidden reasoning loop

**REPOSITORY FACT**

`docs/legacy/Soma_Roadmap_V2_Strategic_Architecture_2026-07-26.md`, Phase 8, states:

- schedules launch canonical tasks;
- schedules **do not start a hidden general reasoning loop**;
- when new judgment is required, the task transitions to `awaiting_controller`.

That same phase separates return delivery from task outcome and notes that polling/task discovery remain authoritative because an MCP server cannot always initiate a new controller turn.

Possible delivery adapters included PulseSender/browser delivery, file, webhook, or future channels.

Delivery failure was explicitly not allowed to change task outcome.

## 2.2 This directly resembles the desired normal-Chat add-on

**OWNER REQUIREMENT**

The desired normal-Chat path is:

```text
Sol reasons
  -> Sol acts through Soma
  -> Soma preserves/executes
  -> observation becomes available
  -> Sol reasons again
  -> repeat until complete
```

The owner has clarified that, for now, the owner can manually wake normal Chat when long-running work finishes.

Therefore the core architecture does **not** need to solve automatic thread wake-up before it can provide a useful agentic extension.

**INFERENCE**

The July `awaiting_controller` concept is architecturally much closer to this desired loop than the later `reasoning backend` concept.

The semantic meaning should be understood as:

```text
awaiting_controller
= deterministic/external work reached a boundary where Sol must decide again
```

not:

```text
awaiting_controller
= ask another model to think instead
```

---

# 3. The controller-wait primitive was implemented before reasoning Tasks existed

## 3.1 August 2 implementation history

**REPOSITORY FACT**

Git history for `soma/worker_substrate/transitions.py` shows:

- `c89ead7f173a1d93bdfd961824db523dc4f70489` - `Add atomic non-terminal controller waiting` - 2026-08-02;
- `ac490f2f040251c83373afdb7e529389ec653cc5` - `Add acknowledged input resume semantics`;
- `bf455b1da14f1fd5f959483444efa66662a78844` - `Close interaction expiry and recovery races`.

Current code still atomically transitions both canonical Task and Run to `awaiting_controller`, creates a durable checkpoint, records context/evidence references, and supports later resume/input semantics.

The canonical Task vocabulary includes:

```text
AWAITING_CONTROLLER
RECOVERY_PENDING
UNCERTAIN
```

and the Task phase vocabulary includes `AWAITING_CONTROLLER`.

## 3.2 Importance for the new research

**INFERENCE**

Soma already contains substantial machinery for the **pause at a judgment boundary / preserve state / resume later** part of the desired normal-Chat agentic loop.

This does not prove the current checkpoint schema is the final Sol-loop schema. It does prove that the project need not invent continuity from zero.

**OPEN QUESTION**

The current controller-wait implementation was built around explicit controller input/checkpoint semantics. Later research must determine whether a Sol reasoning-turn boundary is:

- exactly the same primitive;
- a generalized form of the same primitive;
- or a sibling cognitive-state record above execution Task state.

No answer is assumed yet.

---

# 4. CodexBridge history also preserved ChatGPT as decision maker

## 4.1 Historical roadmap evidence

**REPOSITORY-ADJACENT HISTORICAL FACT**

The owner-supplied `CodexBridge Local Agent Expansion Roadmap v2` predates the current Soma Agent/Worker programme and states a target shape in which:

- ChatGPT remains strategist/final decision maker;
- the local agent handles cheap operational/long-running work;
- a durable job manager runs training and other long jobs;
- PulseSender returns reports to ChatGPT;
- Codex is reserved for coding/editing when needed.

Its long-run job section explicitly describes:

```text
ChatGPT starts durable work
ChatGPT may disconnect
work completes later
result returns to ChatGPT
ChatGPT decides the next action
```

## 4.2 What remains useful from that roadmap

**INFERENCE**

Several old labels (`local agent`, `Ollama`, `Codex escalation`) no longer match the desired architecture and should not be restored blindly.

But its control direction remains highly relevant:

```text
external/durable machinery performs operations
ChatGPT decides what the observations mean and what happens next
```

That is continuity evidence for the owner's current clarification rather than a new idea introduced in August 2026.

---

# 5. Where the Agent/Worker research first began to drift

The drift was gradual. It should not be attributed to one component or one commit.

## 5.1 First conceptual expansion: workers became possible semantic actors

**REPOSITORY FACT**

`docs/agent-worker-research/iteration-01-current-capability-and-architecture-baseline-2026-08-12.md` correctly preserved several important boundaries:

- Sol remains user-facing reasoning/adjudication head;
- Hermes is headless execution, not a reasoning subagent;
- Codex must not become universal worker identity;
- native OpenAI subagents and tool parallelism are distinct.

However, it also introduced the future taxonomy:

```text
execution_worker
retrieval_worker
scout_worker
reasoning_worker
```

and identified Responses/Agents SDK or another model-backed route as a possible future `reasoning_worker` backend.

The leading hybrid hypothesis became:

```text
Sol semantic decomposition
-> Soma durable graph
-> heterogeneous workers
-> Sol adjudication
```

**INFERENCE**

This was not yet a hard architectural error. Bounded specialist reasoning can legitimately exist as an optional capability.

The drift risk began because **reasoning work** started being modeled as a normal backend category inside Soma rather than first asking whether the missing normal-Chat capability was simply durable return of control to Sol.

## 5.2 The critical conceptual transition: reasoning became canonical Task/backend work

**REPOSITORY FACT**

`docs/agent-worker-research/G2_REASONING_TASK_ACCEPTANCE_2026-08-12.md` records the accepted G2 transition.

At commit:

`fcba03c2e553920d11b0300d72b51c0a44983bd4`

Soma added:

```text
TaskKind.REASONING = "reasoning"
BackendKind.SOMA_REASONING = "soma_reasoning"
```

G2 also added:

- `ReasoningSpecV1`;
- a durable subordinate reasoning backend;
- provider create/send ambiguity semantics;
- reasoning Task restart recovery;
- result/evidence publication for model/provider output.

At this point, reasoning was no longer only an optional conceptual specialist. It had become a first-class canonical Task route.

**INFERENCE - PRIMARY DRIFT POINT**

This is the clearest architectural transition that must be re-evaluated.

The durable provider mechanics themselves are potentially valuable. The questionable assumption is the elevation:

```text
semantic reasoning request
-> canonical Soma reasoning Task
-> model/provider backend
```

as a core progression for Soma.

For the owner's desired normal-Chat add-on, the default path should instead be tested as:

```text
Sol semantic reasoning turn
-> Soma records action/control state
-> external action/evidence
-> controller-turn boundary
-> Sol semantic reasoning turn
```

The difference is who owns the cognitive continuation.

## 5.3 Later research hardened the reasoning-worker role

**REPOSITORY FACT**

By Agent/Worker Iterations 3-4 and the implementation plan, documents explicitly described:

- a `reasoning backend` under canonical Task;
- optional provider-native agent trees under that backend;
- `reasoning worker` as the semantic actor for benchmark assignments;
- Sol as the final adjudicator/synthesizer of worker submissions.

The G6 implementation plan states that the **reasoning worker is the semantic actor** for the assigned material, while Sol performs later unsupported-assertion/evidence/contradiction/final adjudication.

## 5.4 Why that is not the owner's intended default architecture

**OWNER REQUIREMENT**

The owner does not want a weaker or subordinate model routinely doing the important thinking while Sol merely reviews the result.

For normal Chat, the goal is to add the missing **agentic continuity around Sol itself**.

For Work, native agentic reasoning already exists and should not be recreated underneath it.

**INFERENCE**

Therefore the later Agent/Worker architecture inverted the desired default responsibility in one important way:

```text
later worker framing:
Sol decomposes -> reasoning worker thinks -> Sol adjudicates

owner-intended normal Chat loop:
Sol thinks -> Soma acts/preserves -> Sol observes -> Sol thinks again
```

Optional specialist reasoning may still be useful, but it must be an exception chosen by Sol/owner, not the mechanism that makes normal Chat agentic.

---

# 6. The drift did not make the whole Agent/Worker programme wrong

## 6.1 Valuable mechanics embedded in the reasoning path

**REPOSITORY FACT**

G2 and later work implemented/proved useful mechanics including:

- provider-neutral backend identity;
- persist-before-send/create semantics;
- explicit ambiguous-outcome handling;
- idempotent replay;
- restart recovery;
- cancellation uncertainty;
- bounded result/evidence references;
- exact provenance;
- no silent fallback to a different backend;
- canonical Task/backend linkage.

Later EvidenceSubmission/FanIn work also clearly separates deterministic structural validation from semantic judgment.

## 6.2 Preliminary classification

This is not the final component audit; that belongs in later iterations.

Current provisional classification:

### Likely KEEP / REUSE

- canonical Task identity and state/versioning;
- durable Run/process ownership;
- controller wait/checkpoint machinery;
- persist-before-effect semantics;
- idempotency/replay;
- recovery/uncertainty handling;
- result/evidence references;
- provenance;
- bounded evidence transport;
- FanIn as deterministic aggregation where actual parallel specialist work exists.

### Likely REPOSITION / MAKE OPTIONAL

- reasoning backend transport mechanics;
- provider-native reasoning tree support;
- reasoning-worker evidence envelopes;
- Codex/provider adapters.

### Requires direct re-evaluation

- `TaskKind.REASONING` as a core canonical Task kind;
- `BackendKind.SOMA_REASONING` as a core architectural axis;
- language that treats a reasoning worker as the normal semantic actor;
- Company admission logic that structurally requires a reasoning provider to create legitimate work.

No removal decision is made in Iteration 2.

---

# 7. Corrected definition of the normal-Chat add-on

## 7.1 The add-on is a Sol control-loop extension

**OWNER REQUIREMENT**

Normal Chat lacks Work's native long-running agentic operating surface. Soma may therefore add the missing durable loop around normal Chat.

The add-on should be understood as:

```text
NORMAL CHAT / SOL
       |
       | reason
       v
   intended action
       |
       v
      SOMA
state + task identity + execution + evidence + recovery
       |
       v
   observation
       |
       v
controller/Sol turn required
       |
       v
NORMAL CHAT / SOL
       |
       | reason again
       +---------------------> ...
```

Soma is the durable **control substrate** around Sol's turns.

It is not the semantic reasoner between Sol turns.

## 7.2 The add-on should be lightweight when the task is lightweight

**OWNER REQUIREMENT**

The owner wants the add-on to help Sol rather than make normal work more difficult.

**INFERENCE - DESIGN CRITERION**

Therefore normal Chat must not be forced into a heavyweight mission/DAG/worker process for every task.

A useful future architecture should likely support at least two scales:

```text
simple turn/action
Sol -> one Soma action -> observation -> Sol

longer durable loop
Sol -> persisted objective/control context -> one or more Soma actions
    -> observation/checkpoint -> Sol -> continue
```

Mission/Plan/Company machinery, complex DAGs, or parallel workers should appear only when their value justifies their overhead.

This is a research criterion, not yet a schema decision.

## 7.3 The add-on must not duplicate Work

**DOCUMENTED FACT from Iteration 1**

Work already provides ChatGPT-native longer multi-step agent behavior and native subagent workflows.

**OWNER REQUIREMENT**

For Work, Soma should provide durability, external execution, memory/state, recovery, evidence, long-running operations, and machine/service access.

It should not insert a second routine reasoning loop under Work.

**INFERENCE**

The corrected architecture is intentionally mode-aware:

```text
Normal Chat:
Sol + Soma durable control-loop extension

Work:
Work's native agentic loop + Soma durability/external capability extension
```

The same Task/execution/evidence substrate may serve both surfaces, but the cognitive orchestration behavior should not be identical.

---

# 8. Wake-up and return delivery are explicitly not the core problem

## 8.1 Owner clarification

**OWNER REQUIREMENT**

For now, the owner will wake normal Chat when necessary.

PulseSender exists but has not been relied on as a robust primary mechanism. A future Chrome/browser add-on similar to PulseSender could later automate delivery.

## 8.2 Architectural consequence

**INFERENCE**

The core add-on only needs to guarantee that when Sol is present again, Soma can truthfully expose enough durable state and observations for Sol to continue without guessing or replaying ambiguous work.

Therefore this research must **not** drift into:

- building browser automation to wake Chat;
- inventing a provider/model merely because Chat is asleep;
- treating notification delivery as task completion;
- blocking the Sol-loop architecture on exact-thread callback support.

Return delivery is a separable adapter concern.

The architecture should remain correct under manual wake-up and polling.

---

# 9. What state the normal-Chat add-on probably needs - but has not yet proven

The next iteration must research this rather than accept a prewritten schema.

Candidate durable cognitive/control facts include:

- objective / current user intent;
- current controller/loop identity;
- current plan or next intended action, if one exists;
- completed actions;
- observations/evidence since the last Sol turn;
- unresolved/ambiguous actions;
- failed actions and retry/recovery state;
- explicit questions/blockers requiring Sol judgment;
- completion/stop criteria;
- last Sol/controller state version;
- current project/scope context;
- whether another Sol turn is required.

**OPEN QUESTION**

How much of this belongs in canonical Task, checkpoints/events, a new lightweight controller-loop record, project memory, or derived projections?

**OPEN QUESTION**

Should cognitive/control-loop state and execution/task state be separate first-class concepts?

A likely reason to separate them is that one Sol reasoning turn may issue zero, one, or multiple execution Tasks, while one Task may finish without meaning the user's goal is complete.

This must be tested against actual Soma structures before any schema is proposed.

---

# 10. Design criteria for the future normal-Chat add-on

These criteria are frozen for subsequent research unless the owner changes them.

## Criterion A - Sol remains the semantic authority

**OWNER REQUIREMENT**

Important reasoning and continuation decisions return to Sol.

Soma may mechanically determine that new evidence exists, a task ended, a checkpoint is unresolved, or an external effect is uncertain. Soma should not infer the semantic next step simply to keep the loop moving.

## Criterion B - use existing normal Chat naturally

**OWNER REQUIREMENT / INFERENCE**

The feature should feel like normal Chat becoming more persistent and capable, not like the user entering a separate workflow product.

For simple tasks, extra orchestration should be nearly invisible.

## Criterion C - durability without cognitive duplication

Soma should preserve everything Sol needs to safely continue after:

- browser refresh;
- lost connection;
- Chat interruption/restart;
- Soma restart;
- machine restart;
- long-running operation.

Recovery must not silently transfer reasoning ownership to another model.

## Criterion D - Work-native functionality wins inside Work

If Work already supplies planning/subagents/multi-step reasoning adequately, Soma should not duplicate that cognitive machinery.

## Criterion E - specialist agents are optional tools

Codex, Claude, Responses/API agents, native subagents, or future providers may be useful for bounded specialist work.

They are not prerequisites for the core Chat + Soma loop.

Codex remains owner-authorized only.

## Criterion F - wake-up is optional transport

Manual wake-up must be a supported baseline.

PulseSender/browser extension/other delivery may improve convenience later without changing task truth or reasoning ownership.

## Criterion G - no compulsory heavyweight graph

Mission/Plan/DAG/FanIn machinery is justified only when the work actually needs it.

One simple action should not require pretending to be a company or a multi-agent programme.

## Criterion H - preserve expensive useful infrastructure

Do not delete Agent/Worker code because its framing drifted.

First identify which mechanics solve durability/execution/evidence problems independently of the reasoning-worker concept.

---

# 11. Precise drift timeline so far

This timeline is preliminary and will be expanded in the full history audit.

## 2026-07-18 - explicit ChatGPT reasoning ownership

Historical achievement record states ChatGPT owns reasoning and implementation decisions.

**Classification:** original architecture evidence.

## 2026-07-26 - durable continuity without hidden reasoning loop

Strategic roadmap says schedules do not start a hidden general reasoning loop and move to `awaiting_controller` when judgment is required. Delivery is separate.

**Classification:** original architecture evidence.

## 2026-08-02 - controller wait/resume becomes real substrate

Commits add atomic non-terminal controller waiting, acknowledged resume semantics, and recovery-race handling.

**Classification:** useful implementation aligned with original intent.

## 2026-08-12 - Agent/Worker research introduces reasoning workers

Iteration 1 retains Sol as adjudication head but introduces `reasoning_worker` as a future worker category/backend possibility.

**Classification:** first conceptual broadening; not inherently wrong, but the missing Sol-loop problem was not kept separate enough.

## 2026-08-12 - G2 makes reasoning a canonical Task/backend route

`fcba03c2...` adds `TaskKind.REASONING` and `BackendKind.SOMA_REASONING` after durable fake-provider work.

**Classification:** primary conceptual transition requiring re-evaluation.

## 2026-08-12 to 2026-08-13 - reasoning worker becomes semantic actor

Later research/benchmark design explicitly treats the reasoning worker as the semantic actor on assignments and Sol as downstream adjudicator.

**Classification:** drift hardens into operating model.

## 2026-08-14 - real owner-gated reasoning Task activation path added

Git history records `1092dbc8eccfac88a9c6ef5b04cf5c667b2070e8` (`Add owner-gated reasoning Task activation`), followed by public reasoning Task acceptance.

Production reasoning remains disabled, so the architecture can be re-evaluated without having become required runtime behavior.

**Classification:** provider-specific route reaches activation-ready form, but remains owner-disabled.

---

# 12. Iteration 2 conclusion

## DOCUMENTED / REPOSITORY FACTS

1. The accepted July architecture explicitly placed reasoning with ChatGPT.
2. The July roadmap explicitly rejected a hidden general reasoning loop inside Soma and used `awaiting_controller` when new judgment was required.
3. Durable `awaiting_controller` / resume / recovery machinery was implemented on August 2.
4. The Agent/Worker research on August 12 initially retained Sol as head but introduced reasoning workers as a future backend class.
5. G2 then made reasoning a first-class canonical Task/backend route.
6. Later benchmark architecture explicitly made the reasoning worker a semantic actor.
7. The real reasoning activation path remains disabled by default.

## OWNER REQUIREMENTS

1. Normal Chat should gain a durable **Sol agentic-loop add-on**, not a replacement reasoning brain.
2. Work already has its own native agentic reasoning; Soma should extend Work rather than duplicate it.
3. Specialist/subordinate agents can exist when useful, but core reasoning should not routinely be outsourced.
4. The add-on should reduce friction rather than create more ceremony.
5. Automatic wake-up is not a core requirement for now; manual wake-up is acceptable.

## INFERENCE

The smallest clean correction is likely not a wholesale Agent/Worker rollback.

The research should now pivot from:

```text
How should Soma host reasoning workers?
```

to:

```text
What is the minimum durable controller-loop state Soma must preserve so normal Chat/Sol can repeatedly reason -> act -> observe -> reason across interruptions?
```

Existing reasoning-backend machinery should be audited afterward as optional specialist/provider infrastructure rather than assumed to be the core loop.

No implementation decision is authorized yet.

---

# 13. Next iteration - minimal durable Sol control-loop state

Iteration 3 should investigate the actual add-on mechanics, using existing Soma source rather than inventing a new framework.

Questions:

1. What durable identity represents one continuing Sol-controlled goal/loop, if any new identity is needed at all?
2. Can existing canonical Task + checkpoints/events represent the loop cleanly, or is Task strictly execution state?
3. Should cognitive/control state be separate from execution/task state?
4. What exact observation bundle does Sol need on re-entry?
5. How does Soma represent `Sol should reason again` without choosing the semantic next action?
6. How are multiple actions from one Sol turn represented?
7. How is a no-action reasoning turn represented?
8. What does `goal complete` mean, and who is allowed to declare it?
9. How can continuation remain lightweight for ordinary Chat tasks?
10. Which current `awaiting_controller`, checkpoint, interaction, task-event, result/evidence and recovery primitives can be reused unchanged?
11. What state is necessary after manual wake-up so Sol can safely continue after a long job?
12. What should explicitly stay outside the core loop: PulseSender, Chrome wake-up extension, Codex, external reasoning providers, Company scheduling, native subagents?

Iteration 3 must not assume a new database table or state machine until the existing substrate has been mapped against these needs.

---

# Sources inspected

## Soma repository

- `docs/legacy/Soma_Roadmap_V2_Achievement_Record_2026-07-18.md`
- `docs/legacy/Soma_Roadmap_V2_Strategic_Architecture_2026-07-26.md`
- `soma/tasks/models.py`
- `soma/worker_substrate/transitions.py`
- `soma/tasks/manager.py`
- `docs/agent-worker-research/iteration-01-current-capability-and-architecture-baseline-2026-08-12.md`
- `docs/agent-worker-research/iteration-03-identity-revision-attempt-and-fanin-contract-2026-08-12.md`
- `docs/agent-worker-research/iteration-04-dag-replanning-and-reasoning-backend-contract-2026-08-12.md`
- `docs/agent-worker-research/G2_REASONING_TASK_ACCEPTANCE_2026-08-12.md`
- `docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`
- Git history for `soma/tasks/models.py`
- Git history for `soma/worker_substrate/transitions.py`
- Git history for `soma/reasoning/runtime.py`

## Owner-supplied historical architecture

- `CodexBridge Local Agent Expansion Roadmap v2`

## Owner clarification captured during this iteration

- Normal Chat should gain the missing durable Sol reasoning/control loop through Soma.
- Work already has native agentic reasoning and should not receive a duplicate reasoning layer.
- The owner can manually wake Chat after long-running work for now.
- PulseSender or a future Chrome/browser add-on is optional delivery UX, not the cognitive architecture.
