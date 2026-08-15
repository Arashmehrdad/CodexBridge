# Iteration 11 - Agent Reasoning Trajectory and Resumption Architecture

Date: 2026-08-15
Status: RESEARCH ONLY - architecture reopened; implementation not authorized
Track: Sol-centric agentic reasoning architecture

## Why this iteration exists

The previous research correctly rejected the Agent/Worker drift in which a subordinate reasoning provider became Soma's semantic actor. It also correctly separated Sol reasoning from canonical Task execution.

However, the later shorthand used to describe the desired Sol loop - `reason -> act -> observe -> reason` - is itself too restrictive. It risks encoding a ReAct-like one-reason/one-action/one-observation state machine into Soma even though production agent systems do not require cognition to follow that fixed sequence.

The owner clarification for this iteration is:

> "Loop" means the reasoning loop/trajectory of Sol, not a Task loop.

The new research question is therefore broader:

> What architecture should Soma provide so normal Chat/Sol can behave as a full adaptive agent across interruptions, long waits, many tools, changing evidence, context pressure, and fresh-chat resumption - without Soma becoming a planner, semantic scheduler, or second reasoning brain?

This iteration does **not** assume that the three-table ControllerContinuation proposal is final. It treats that design as a hypothesis to pressure-test against real agent runtimes and current research.

---

# 1. Evidence base

This iteration uses primary implementation/documentation sources and primary research where possible.

## OpenAI / Codex

- OpenAI Codex Prompting Guide, 2026-02-25
  - https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide
- OpenAI ChatGPT/Codex long-running work guidance
  - https://learn.chatgpt.com/docs/long-running-work
- openai/codex current `codex-rs/core/src/session/turn.rs`
  - https://github.com/openai/codex/blob/main/codex-rs/core/src/session/turn.rs
- openai/codex context-compaction handoff prompt
  - https://github.com/openai/codex/blob/main/codex-rs/prompts/templates/compact/prompt.md

## OpenAI Agents SDK

- Running agents / Runner loop
  - https://openai.github.io/openai-agents-python/running_agents/
- Agent orchestration
  - https://openai.github.io/openai-agents-python/multi_agent/
- RunState durable pause/resume boundary
  - https://openai.github.io/openai-agents-python/ref/run_state/
- Human-in-the-loop / serialized RunState
  - https://openai.github.io/openai-agents-python/human_in_the_loop/
- Sessions and context management
  - https://openai.github.io/openai-agents-python/sessions/
  - https://openai.github.io/openai-agents-python/context/
- Sandbox agent memory / snapshots / compaction
  - https://openai.github.io/openai-agents-python/sandbox/memory/
  - https://openai.github.io/openai-agents-python/sandbox/guide/

## Anthropic

- Anthropic tool-use concepts / agentic tool runner
  - https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/tool-use-concepts.md
- Anthropic Claude Code Foundations, 2026-07
  - https://www.anthropic.com/webinars/claude-code-foundations

## Google Gemini CLI

- Gemini CLI configuration / loop detection / context compression
  - https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/configuration.md
- Gemini CLI hooks
  - https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md
  - https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- Gemini core client
  - https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/core/client.ts

## OpenHands

- OpenHands architecture / AgentController / State / EventStream / Runtime
  - https://github.com/OpenHands/OpenHands/blob/main/openhands/README.md

## Primary research

- Yang et al., "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering", 2024
  - https://arxiv.org/abs/2405.15793
- Li & Shi, "Agent-Computer Observation Interfaces Enable Dynamic Computer Use", 2026
  - https://arxiv.org/abs/2606.29472
- Xu et al., "The Devil Is in the Interface: Evaluating How Tool Architecture Shapes Coding Agent Behavior", 2026
  - https://arxiv.org/abs/2608.11386

---

# 2. Finding: production agent harness loops are simple; model cognition is not

## DOCUMENTED FACT

OpenAI Agents SDK describes its Runner loop approximately as:

1. call the current LLM;
2. if it returns final output, end;
3. if it returns tool calls, execute them and feed results back, then call the LLM again;
4. if it performs a handoff, change active agent and call again;
5. stop at final output or a turn bound.

Anthropic's tool runner describes the same broad harness pattern: keep calling the model, execute requested tools, return tool results, and continue until the model stops requesting tools. Multiple tool calls may be emitted in one model response.

OpenHands documents a pedagogical action/observation loop but notes that its real implementation uses message passing through an EventStream and a maintained State.

## DOCUMENTED FACT - CODEX

Current Codex `turn.rs` is not one model call per user turn. A single logical turn can contain repeated model sampling requests. After a sampling request, Codex computes `model_needs_follow_up`; pending input can also force continuation. If further work is needed it can compact context mid-turn and continue sampling.

Therefore:

```text
one user turn != one reasoning episode
one reasoning episode != one tool call
one tool result != necessarily one reasoning cycle
```

## INFERENCE - STRONG

The harness needs a **continuation condition**, not a hard-coded cognitive algorithm.

A simple runner can repeatedly give the model an opportunity to reason, but the model decides internally whether to:

- inspect more context;
- plan;
- revise a plan;
- call zero tools;
- call one tool;
- call many independent tools;
- interpret returned evidence;
- validate;
- retry with a different approach;
- ask the user;
- delegate;
- produce a final answer.

Therefore Soma should **not** encode a sequence such as:

```text
REASONING -> ACTION -> OBSERVATION -> REASONING
```

as persisted controller state.

That would confuse the runner/harness boundary with model cognition.

---

# 3. Finding: Codex explicitly batches and parallelizes evidence gathering

## DOCUMENTED FACT

The current Codex Prompting Guide tells the model to think before tool calls, determine all files/resources needed, batch independent reads, issue them in parallel, analyze the batch, and repeat only if results reveal unpredictable further reads.

Conceptually:

```text
model reasoning episode
  -> decide evidence set
  -> tool A + tool B + tool C + ...
  -> aggregate results
  -> next model reasoning episode
```

This disproves a one-action-per-reasoning-cycle assumption.

## INFERENCE

For Soma, the correct primitive is not "the next action". Sol may emit **an action set** with dependency structure that is obvious locally:

- independent actions can be parallel;
- dependent actions remain sequential;
- no general persistent DAG is required merely to represent ordinary parallel tool use.

Existing canonical Tasks can represent durable external actions where durability is needed. Lightweight synchronous tool calls do not necessarily deserve canonical Task identity.

This preserves the prior rule:

> Do not turn every tool call into a durable Task merely because it happened inside a reasoning trajectory.

---

# 4. Finding: plans are mutable cognitive scaffolding, not the agent runner

## DOCUMENTED FACT

Codex exposes an `update_plan` tool and instructs the model to maintain plan hygiene. The plan consists of mutable steps/statuses. OpenAI's Codex prompt separately instructs the model to proactively gather context, plan, implement, test, and refine.

OpenAI's long-running-work guidance says that the same context is used so ChatGPT can choose the next step and decide when work is complete. It recommends a clear outcome, constraints, and verification criteria; `/plan` may be used to refine an unclear goal before `/goal`.

Anthropic's Claude Code product teaching similarly describes a broad `read, plan, act, observe` agentic workflow and separately exposes plan mode.

## INFERENCE - STRONG

A plan is **model-authored working state**. It may be useful, changed, abandoned, expanded, or unnecessary.

Soma should not promote a working plan into an obligatory execution graph.

Correct separation:

```text
Sol reasoning trajectory
  may create/revise a plan
  may use no explicit plan
  may replace the plan after evidence

Soma
  may durably store/reference an explicit plan artifact when Sol chooses
  must not execute plan steps merely because they are pending
```

This is distinct from Company `PlanRevision`, which represents an accepted organizational commitment rather than scratch/working cognition.

---

# 5. Finding: action and observation should not be coupled

## PRIMARY RESEARCH FACT

The 2026 Agent-Computer Observation Interface (AOI) paper explicitly argues that current computer-use loops often tie observation to action and therefore miss dynamic information between actions. AOI decouples adaptive observation from discrete actions and reports large gains on dynamic tasks without retraining the models.

## REPOSITORY / SYSTEM IMPLICATION

Soma already has multiple sources whose truth can change while Sol takes no action:

- durable run state;
- Task recovery state;
- service/process state;
- external providers;
- repository state changed by another concurrent project/thread;
- owner input;
- future notifications/pulse transports;
- potentially connected services with their own event journals.

Therefore this is too narrow:

```text
Sol acts
 -> that action produces observation
```

The architecture needs to tolerate:

```text
world changes
 -> evidence/observation becomes available
 -> Sol later integrates it
```

with **zero preceding Sol action**.

## INFERENCE - STRONG

The continuation design should eventually describe an **observation frontier** or **evidence frontier**, not only `Task -> last_consumed_observation_hash`.

Task-linked observation remains one important source, but not necessarily the only source of reasoning-relevant change.

This does not automatically imply one giant global event stream. It implies that the model-visible continuation bundle must be able to say what relevant authoritative sources changed since the last reasoning checkpoint.

---

# 6. Finding: interface design is a first-class agent capability

## PRIMARY RESEARCH FACT

SWE-agent demonstrated that changing the agent-computer interface substantially changes software-engineering agent performance even without changing the underlying language model.

The August 2026 paper "The Devil Is in the Interface" reports that tool architecture changes agent behavior even when underlying capabilities are similar. Its experiments report meaningful changes in consistency, exploration, step count, and token use across different tool organizations; lightweight text-based cognitive-scaffolding tools had much smaller effects than interface/tool architecture.

## INFERENCE - VERY IMPORTANT FOR SOMA

Soma's highest-value contribution may be less about "implementing a reasoning loop" and more about giving Sol an **excellent agent interface**:

- semantically precise tool names/contracts;
- bounded, model-legible observations;
- exact durable identity for effects;
- clear authority/ref provenance;
- parallel-friendly reads;
- idempotent mutations;
- easy evidence retrieval;
- compact current-state projections;
- clean distinction between current truth and historical events;
- explicit uncertainty rather than fabricated certainty;
- resumable context/checkpoint retrieval.

That is consistent with the owner's original "Soma as nervous system" concept.

The model already reasons. Soma should make the external world **easy for the model to perceive and manipulate correctly**.

---

# 7. Finding: production runtimes separate model-visible context, runtime state, and world/workspace state

OpenAI Agents SDK provides a particularly useful decomposition.

## DOCUMENTED FACT

It distinguishes:

1. model/conversation input state;
2. app/runtime context (`RunContextWrapper`);
3. serializable `RunState` for interrupted execution;
4. sandbox/workspace state and snapshots;
5. memory distilled for future runs.

`RunState` is explicitly called a durable pause/resume boundary. It stores enough runtime state to continue an interrupted run, including model responses, generated items, approvals, current step, and conversation identifiers.

Sandbox agents separately preserve workspace/sandbox state. Memory is separately described as distilled lessons useful for future runs rather than the same thing as conversational session history.

## INFERENCE

This decomposition matters because the current Soma continuation hypothesis partially collapses these concerns.

For normal Chat/Sol, we have at least four distinct kinds of durable truth:

```text
A. reasoning-context continuity
   what Sol needs to understand where the reasoning trajectory currently stands

B. execution/runtime continuity
   exact Task/Run/process/provider state

C. world/resource continuity
   repository/service/files/external resource state

D. long-term memory/knowledge
   durable decisions, preferences, facts, lessons
```

These should not become one giant continuation row.

Canonical Task/Run already owns B.
ProjectScope/resources and concrete systems own much of C.
Canonical knowledge/memory already owns much of D.

The unresolved architectural question is primarily A and the projection joining A+B+C+D for Sol.

---

# 8. Finding: Codex uses a model-authored context checkpoint for long reasoning trajectories

## DOCUMENTED FACT

The current open-source Codex compaction prompt says it is performing a **CONTEXT CHECKPOINT COMPACTION** and asks for a handoff summary for another LLM that will resume the task.

It specifically asks to preserve:

- current progress and key decisions;
- important context, constraints, and user preferences;
- remaining work / clear next steps;
- critical data, examples, and references needed to continue.

The Codex Prompting Guide describes compaction as enabling multi-hour reasoning without hitting context limits.

## INFERENCE - MATERIAL NEW ARCHITECTURE QUESTION

A fresh normal-Chat Sol instance cannot resume an interrupted reasoning trajectory from execution state alone.

This packet is insufficient in the general case:

```text
objective
+ Tasks
+ Task results
```

because Sol may previously have established:

- an interpretation of the objective;
- hypotheses already rejected;
- why one approach was chosen over another;
- a provisional plan;
- a non-obvious constraint discovered from evidence;
- what evidence has already been evaluated;
- what still needs validation;
- a decision not yet materialized as a Task.

If the exact Chat context is still present, Chat itself may supply that continuity. But if the goal is robust fresh-chat or cross-context resumption, Soma likely needs a **model-authored reasoning checkpoint/handoff artifact**.

This is not private chain-of-thought. It is an explicit, bounded operational summary intentionally produced for future continuation, analogous to Codex compaction.

## PROVISIONAL CANDIDATE

A continuation could reference an immutable/versioned artifact such as:

```text
ReasoningCheckpointV1
  objective/status summary
  current interpretation
  key decisions and rationale needed for continuation
  active constraints/preferences
  current working plan if one exists
  completed/inapplicable/rejected approaches worth preserving
  unresolved questions/uncertainties
  evidence already incorporated (refs/hashes)
  pending durable actions (Task refs)
  remaining validation / next decision boundary
  produced_at
  controller = Sol
```

Important constraints:

- authored/accepted by Sol, not generated semantically by Soma;
- no hidden chain-of-thought requirement;
- bounded and model-legible;
- may be replaced by a newer checkpoint;
- should reference canonical Task/evidence rather than copy large bodies;
- should not become executable plan authority.

Whether this deserves a dedicated schema or can reuse canonical knowledge/artifact storage remains open.

---

# 9. Finding: exact runtime resumption and semantic resumption are different

## DOCUMENTED FACT

OpenAI Agents SDK can serialize exact `RunState` because it owns the model runner. It can restore current agent, generated model items, approvals, model responses, current interrupted step, and related runtime metadata.

Codex owns its own model session and context, so it can compact/reinject the conversation and continue sampling internally.

## CONSTRAINT - SOMA + NORMAL CHAT

Soma does **not** own Sol's internal ChatGPT model runner.

Therefore Soma cannot generally serialize and restore:

- hidden reasoning state;
- exact sampling continuation;
- private chain-of-thought;
- internal model KV/cache state;
- arbitrary ChatGPT product runtime internals.

## INFERENCE - STRONG

Soma should aim for **semantic resumption**, not pretend to offer exact model-runtime resumption.

Semantic resumption means:

```text
fresh/returned Sol
  receives enough explicit checkpoint + authoritative current world state
  to continue the same objective intelligently
```

This is the best architecture available without becoming the model host itself.

This also explains why a tiny three-table bookkeeping layer may be insufficient on its own: it solves durable identity and delta consumption, but not necessarily semantic continuity after the model context is gone.

---

# 10. Finding: event streams are useful internal infrastructure but poor default model context

## DOCUMENTED FACT

OpenHands uses an EventStream as the communication backbone between AgentController, Runtime, frontend, and other components. Its maintained `State` includes current step, recent history, and long-term plan.

Gemini CLI also exposes rich lifecycle/core events and hooks around the agent loop.

## INFERENCE

Soma already has many event journals. That is valuable for:

- audit;
- recovery;
- concurrency;
- debugging;
- evidence provenance;
- reconstructing authoritative state.

But feeding raw event history to Sol every time would be expensive and noisy.

The model-facing continuation surface should probably use:

```text
compact current projection
+ unconsumed meaningful deltas/watermarks
+ retrieval refs for deeper evidence
```

not:

```text
entire event stream
```

This is consistent with Soma's existing bounded projection philosophy.

---

# 11. Finding: deterministic safeguards belong in the harness; semantic recovery belongs to the model

## DOCUMENTED FACT

Gemini CLI implements deterministic loop detection, action limits, context compression, and hooks. OpenAI Agents SDK has `max_turns`, tool execution concurrency controls, approvals, guardrails, and serialized interruptions. Codex has stop hooks, compaction, token budgets, sandbox/approval policy, and tool execution mechanics.

These systems do **not** require the deterministic harness to choose the semantic alternative when the model encounters a failure.

## INFERENCE

Soma can mechanically provide:

- idempotency;
- concurrency limits;
- cancellation;
- resource ownership;
- retries where the retry is transport/mechanical rather than semantic;
- timeout/deadline handling;
- observation freshness;
- stale-write rejection;
- approval interruption;
- loop/repetition diagnostics if later useful;
- bounded context/evidence projections.

But when evidence says:

```text
approach failed
```

Soma must not decide:

```text
therefore choose approach B
```

That remains Sol's cognitive responsibility.

---

# 12. Revised conceptual architecture candidate

This is a **research candidate**, not a final design.

Instead of describing Soma as implementing the reasoning loop, model the system as:

```text
                         SOL / CHATGPT
                   adaptive reasoning trajectory

       interpret / investigate / plan / revise / validate / decide
                 |          |             |          |
                 +------ zero / one / many capability calls ------+
                                      |
                                      v
                    SOMA AGENT INTERFACE / NERVOUS SYSTEM

           capability discovery + exact tool contracts
           durable action identity where needed
           bounded current-state observations
           evidence/provenance retrieval
           interruption/approval/recovery truth
           world/resource access
           semantic continuation checkpoint storage/retrieval
           observation/evidence frontier
                                      |
                   +------------------+------------------+
                   |                  |                  |
                Tasks/Runs       repos/services      knowledge/memory
                execution        world/resource       long-term facts
                  truth              truth                truth
```

The model is not forced through states like PLAN, ACT, OBSERVE.

When Sol is active, it may call Soma repeatedly in whatever pattern is useful. When Sol is not active, Soma preserves external truth and any explicit reasoning checkpoint already supplied by Sol.

On return/fresh Chat:

```text
Soma -> compact continuation bundle
        - objective/constraints/done criteria
        - latest Sol-authored reasoning checkpoint
        - authoritative pending/running/terminal action state
        - new evidence since checkpoint/frontier
        - unresolved interruptions/uncertainty
        - retrieval refs

Sol -> reconstructs current situation
    -> chooses its own next cognitive/action step
```

This is closer to the architecture of a **resumable model-driven agent harness** than a workflow engine.

---

# 13. Pressure test against owner requirements

## Sol remains the brain

PASS.

No other model is required. Soma does not generate semantic next steps.

## No weaker-model pre-reasoning

PASS.

Checkpoint author is Sol. Mechanical projections may be computed by code.

## Work should not receive duplicate cognition

PASS, provisionally.

Work already owns its model-runner trajectory. It may still benefit from Soma's capability/evidence/world interfaces, while the special normal-Chat resumption layer could be unnecessary or only an optional external checkpoint.

## Codex only on explicit owner request

PASS.

Nothing in this architecture requires Codex.

## Multiple projects simultaneously

PASS.

Reasoning/checkpoint/evidence reads do not require repository mutation locks. Concrete execution keeps existing resource-lock behavior.

## No Task-loop architecture

PASS, stronger than before.

Tasks are effect identities only. They do not imply sequence or next-step logic.

## User wake-up remains acceptable

PASS.

Wake-up is transport. Once Chat is active again, Sol requests the continuation bundle.

---

# 14. Where the previous three-table hypothesis now looks incomplete

The previous minimum proposed approximately:

```text
controller_continuations
controller_continuation_tasks
controller_continuation_commands
```

with a last-consumed observation hash.

Iteration 11 does **not** prove this is wrong, but reveals two missing dimensions that must be resolved before implementation planning.

## Gap A - semantic reasoning checkpoint

A Task/evidence frontier says what the world did, but not necessarily what Sol had concluded from it.

Fresh-context resumption may require a Sol-authored checkpoint/handoff artifact.

## Gap B - observation sources beyond Tasks

A reasoning trajectory can consume relevant changes that are not causally produced by its Tasks.

The observation frontier therefore cannot be defined only as Task membership hashes if Soma is intended to become a general-purpose agent interface.

These gaps may be solved by references/metadata rather than additional heavy tables. The point is architectural completeness, not schema growth.

---

# 15. Candidate durable state decomposition after Iteration 11

Do not treat this as final schema.

A minimal durable semantic-continuation concept may need to reference five things:

```text
1. Objective contract
   outcome + constraints + definition of done

2. Latest reasoning checkpoint
   explicit Sol-authored operational handoff summary

3. Effect set
   canonical durable Tasks/Runs Sol initiated and still cares about

4. Observation frontier
   what authoritative evidence/state Sol has already incorporated

5. Interruptions / unresolved uncertainty
   exact pending owner/controller decisions and ambiguous effects
```

Most actual truth should remain in existing authorities and be referenced rather than copied.

Potentially:

```text
ContinuationRecord
  continuation_id
  objective_ref/hash
  checkpoint_ref/hash
  state/version
  created/updated/closed

ContinuationEffectLink
  continuation_id
  task_id
  control_role / evidence_role

ContinuationFrontier
  continuation_id
  source_kind
  source_id
  consumed_version/hash/watermark

ContinuationCommand
  idempotent mutation journal
```

This is deliberately only a **shape for the next research iteration**. It is not an implementation recommendation yet.

---

# 16. Critical design question: who writes the reasoning checkpoint and when?

Codex can create its compaction checkpoint automatically because Codex owns the model loop.

Soma does not own Sol's model loop.

Possible options:

## Option A - explicit checkpoint before long waits

Sol calls something like `continuation_checkpoint(...)` before starting/waiting on a long action.

Advantages:
- exact semantic authority;
- no background model;
- fresh Chat can resume well.

Risks:
- extra ceremony;
- easy to forget;
- may burden Sol on simple tasks.

## Option B - checkpoint only when continuity risk appears

Examples:
- a Task will outlive the current turn;
- user says pause;
- context is getting large;
- several durable actions are active;
- fresh-chat handoff is explicitly requested.

This may be the best low-burden policy, but it needs empirical testing.

## Option C - rely entirely on Chat history unless fresh-chat continuation is requested

Advantages:
- minimum machinery.

Risks:
- weak recovery if thread/context disappears;
- does not fully exploit Soma durability;
- owner explicitly values handoffs/continuity.

## Option D - Soma generates the semantic checkpoint

REJECT as default.

That would require another model or deterministic semantic summarizer and risks recreating the exact reasoning-worker mistake. Mechanical extraction can help, but semantic handoff authority should remain Sol unless owner explicitly requests another specialist.

---

# 17. Critical design question: how broad should the observation frontier be?

Three candidate scopes:

## Task-only frontier

Smallest and easiest.

Good for durable-command continuation, but misses non-Task world changes.

## Registered-source frontier

A continuation explicitly tracks only authoritative sources Sol says are relevant:

```text
Task T1
Task T2
repo R generation/head
service S state/version
knowledge record K
external durable journal J cursor
```

This is bounded and likely general enough.

## Global project event frontier

Everything under a project can wake/change continuation state.

Likely too noisy and risks coupling unrelated concurrent work.

**Leading hypothesis:** registered-source frontier is more compatible with multi-project concurrency and Sol-directed cognition than a global project cursor.

Needs further research and repository pressure testing.

---

# 18. Critical design question: continuation record versus reasoning session

The current term `ControllerContinuation` correctly avoids Task-loop confusion, but may still emphasize bookkeeping rather than the real purpose.

Potential conceptual names for later evaluation:

- reasoning continuation;
- agent continuation;
- reasoning session checkpoint;
- objective continuation;
- cognitive handoff state;
- agent context capsule;
- continuation capsule.

No naming decision is made here.

The essential property is:

> It is not the reasoning algorithm. It is the externally persisted state required to let Sol re-enter the same reasoning trajectory.

---

# 19. What this iteration rejects

1. A persisted `PLAN -> ACT -> OBSERVE -> PLAN` state machine.
2. One durable Task for every tool call.
3. One reasoning turn per Task transition.
4. Automatic next-Task scheduling when a Task completes.
5. Treating Task output as the only possible observation source.
6. Treating a working plan as canonical execution authority.
7. Persisting private chain-of-thought.
8. Creating a second model to summarize Sol by default.
9. Feeding the model an unbounded raw event stream on every continuation.
10. Making exact model-runtime resumption claims Soma cannot support through normal Chat.

---

# 20. What this iteration strengthens from prior research

1. **Sol is the semantic actor.** Stronger than before.
2. **Soma is nervous system/interface, not second brain.** Stronger than before.
3. **Tasks are effects, not cognition.** Stronger than before.
4. **Execution truth stays canonical in Task/Run.** Unchanged.
5. **Working plans remain model-owned.** Stronger distinction.
6. **Company remains separate/frozen.** Unchanged.
7. **Specialists are optional and explicit.** Unchanged.
8. **Multi-project reasoning remains lock-free.** Unchanged.
9. **Wake-up is transport, not cognition.** Unchanged.
10. **Bounded model-facing projections are important.** Stronger due interface research.

---

# 21. Provisional Iteration 11 verdict

**THE PREVIOUS FIXED `reason -> act -> observe -> reason` MODEL IS TOO NARROW AND SHOULD NOT DRIVE IMPLEMENTATION.**

The best-supported direction after this iteration is:

> Let Sol own an unconstrained adaptive reasoning trajectory. Soma should provide a high-quality agent interface plus durable semantic resumption: exact world/effect truth, bounded observations, evidence/provenance, interruptions, and a Sol-authored reasoning checkpoint/handoff when continuity across lost model context matters.

The architecture should resemble:

```text
model-driven agent runtime semantics
+ durable external world state
+ explicit semantic checkpointing
+ compact observation frontier
```

rather than:

```text
workflow state machine
+ Task progression
```

But research is **not complete**. Two architectural questions are now important enough to deserve dedicated iterations before a new final synthesis:

1. **Resumption architecture:** What is the minimum semantic checkpoint/continuation packet needed for a fresh Sol context to resume correctly without over-persisting cognition?
2. **Observation architecture:** How should Soma represent a bounded registered-source observation frontier across Tasks, repositories, services, journals, and external changes without creating a global event bus or new competing truth authority?

Suggested next research sequence:

- Iteration 12 - Semantic resumption/checkpoint design: Codex compaction, RunState, session/context memory, handoff design, and fresh-Chat recovery.
- Iteration 13 - Observation/evidence interface design: Task-independent observations, registered-source watermarks, event-vs-snapshot tradeoffs, and model-facing projection shape.
- Iteration 14 - Soma-specific architecture convergence: map the resulting design onto existing Task/Run/ProjectScope/Knowledge/Public Gateway systems and produce a corrected synthesis only after these pressure tests.

No implementation should begin from Iteration 10 while this reopened architecture research is active.
