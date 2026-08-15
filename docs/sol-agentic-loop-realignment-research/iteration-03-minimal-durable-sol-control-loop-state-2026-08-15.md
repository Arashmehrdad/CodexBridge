# Iteration 3 - Minimal Durable Sol Control-Loop State

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected: `938f1764dcab30a8bd8235ea2c822ba6d8c0826c`

## Scope

Iteration 2 established that the desired normal-Chat add-on is a durable control loop **around Sol**, not a second reasoning model underneath Sol.

Iteration 3 asks the next concrete question:

> What is the smallest durable state Soma must preserve so normal Chat/Sol can safely continue `reason -> act -> observe -> reason` across interruptions, while canonical Task remains the execution authority?

This iteration maps the requirement against existing Soma source and current OpenAI agent-loop concepts. It does not authorize schema or runtime implementation.

## Hard constraints

No implementation, migration, runtime/service restart, Company activation, reasoning-provider activation, Codex use, provider generation, production config change, push, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

Company remains frozen.

Automatic browser/thread wake-up remains outside the core loop. Manual owner wake-up is an accepted baseline. PulseSender/browser extension work is a separate transport concern.

Classification labels:

- **DOCUMENTED FACT** - current official OpenAI documentation.
- **REPOSITORY FACT** - current Soma source/docs/Git evidence.
- **OWNER REQUIREMENT** - explicit owner direction.
- **INFERENCE** - supported architectural conclusion, not yet accepted implementation.
- **OPEN QUESTION** - deliberately unresolved.

---

# 1. External reference model: what an agent loop actually needs

## 1.1 OpenAI Agents SDK loop

**DOCUMENTED FACT**

Current OpenAI Agents SDK documentation describes the built-in agent loop approximately as:

1. call the LLM with current input;
2. inspect model output;
3. if the model emits a final output, stop;
4. if it emits tool calls, execute those tools, append the tool results, and call the model again;
5. continue until final output or a configured turn limit/interruption.

The SDK also supports resumable `RunState` for interrupted runs and session/server-managed state for conversation continuation.

Sources:

- OpenAI Agents SDK, `Running agents`: https://openai.github.io/openai-agents-python/running_agents/
- OpenAI Agents SDK, `Results`: https://openai.github.io/openai-agents-python/results/
- OpenAI Agents SDK, `Sessions`: https://openai.github.io/openai-agents-python/sessions/

## 1.2 Relevance - pattern, not implementation dependency

**INFERENCE**

The useful conceptual pattern is not “use the Agents SDK inside Soma.” The pattern is:

```text
model decision
 -> tool/action
 -> tool result/observation
 -> same model decides again
 -> explicit final output stops the loop
```

For the owner's normal-Chat architecture:

```text
model = Sol / main ChatGPT
runtime durability = Soma
```

Soma should therefore preserve the **boundary information needed to reconnect those Sol turns**.

It should not instantiate its own model runner merely to imitate this loop.

## 1.3 Conversation memory and operational loop state are different

**DOCUMENTED FACT**

The OpenAI SDK separates agent-run state/session continuation from tool execution/result items. Sessions maintain conversation history across runs; resumable run state preserves interrupted execution context.

**INFERENCE**

Normal Chat already owns its conversational transcript/context. Soma should not clone the entire Chat transcript into a second canonical conversation store just to become agentic.

Soma needs the operational delta that Chat alone cannot safely reconstruct after interruption:

- which durable actions were issued;
- what became observable after the last Sol turn;
- which actions are still running;
- which external effects are uncertain;
- what evidence/result references exist;
- whether Sol has already consumed those observations;
- whether Sol explicitly declared the goal complete.

---

# 2. Canonical Task is an action/execution identity, not a goal-loop identity

## 2.1 Task's current authority

**REPOSITORY FACT**

`soma/tasks/models.py` and `soma/tasks/store.py` define Task as the canonical public execution identity.

Every `TaskRecord` carries:

- `task_id`;
- `controller_request_id` and request hash;
- optional `objective_ref` and `constraints_ref`;
- exact `backend_kind`, executor, and backend reference;
- state/phase/state version;
- checkpoint reference;
- result/evidence references;
- recovery state;
- timestamps.

The store explicitly says it is authoritative for Task identity, links, commands, checkpoints, and events, but **not** worker/process/lease/lock/evidence/result bodies.

Every ownership-sensitive Task update uses compare-and-set state versioning.

## 2.2 Task terminal state follows backend execution state

**REPOSITORY FACT**

Current Task state mapping derives execution lifecycle from backend status:

```text
launch_pending / queued -> queued
running                 -> running
needs_input             -> awaiting_controller
completed / partial     -> completed
timed_out / failed      -> failed
cancelled               -> cancelled
unknown                  -> uncertain
```

Task completion therefore means the selected backend execution reached a terminal condition whose authoritative result is referenced.

## 2.3 Why Task cannot equal the whole Sol-controlled goal

**OWNER REQUIREMENT**

A user goal may require several Sol turns and several actions.

Examples:

```text
Sol reasons
 -> inspect repo Task A
 -> Sol reads result
 -> run tests Task B
 -> Sol reads failure
 -> modify something through an authorized route Task C
 -> Sol validates Task D
 -> Sol declares goal complete
```

One action finishing does not mean the goal is complete.

**INFERENCE**

Canonical Task should remain the exact durable identity of an **action/execution attempt**.

Using one Task as the whole goal would create several problems:

1. Task requires one selected backend identity.
2. Task terminal state is tied to backend terminal state.
3. One Sol turn may issue multiple independent Tasks.
4. A Sol turn may issue no Task at all and instead revise intent, ask the owner a question, or declare completion.
5. A terminal Task cannot naturally remain the active controller identity for later reasoning/actions without weakening its execution semantics.

Therefore the control loop needs an identity/layer **above or alongside Task**, unless a later experiment proves equivalent semantics can be derived without persistent loop identity.

This is the strongest Iteration 3 structural finding.

---

# 3. `awaiting_controller` is useful but narrower than the whole Sol loop

## 3.1 Existing controller wait is strong durable machinery

**REPOSITORY FACT**

`soma/worker_substrate/transitions.py` provides an atomic non-terminal controller-wait transition.

It coordinates existing Task, Run, ProjectScope, checkpoint, session-binding, and deadline authorities in one transaction.

Entering the wait:

- requires an exact running Task and Run;
- creates an idempotent durable checkpoint;
- records prompt/input schema/context/evidence references;
- moves Task and Run to `awaiting_controller`;
- keeps the Run non-terminal;
- requires exact state-version matching;
- prevents conflicting open checkpoints;
- supports durable acknowledgement/resume semantics;
- preserves uncertainty if transport delivery cannot be proven.

## 3.2 What it correctly solves

**INFERENCE**

Existing `awaiting_controller` is a very good fit for this case:

```text
one still-running external action
 -> cannot continue without controller/Sol input
 -> preserve checkpoint
 -> Sol provides input later
 -> same action resumes
```

Examples could include an interactive command, long operation requiring a decision, or a provider/session that genuinely remains active while waiting.

## 3.3 What it does not solve

**REPOSITORY FACT**

The transition explicitly rejects terminal Runs and requires the Task/Run to still be running before entering controller wait.

**INFERENCE**

Therefore it is not the complete goal-level agentic loop.

A very common Sol cycle is:

```text
Task A completes
 -> result/observation becomes available
 -> Task A is terminal
 -> Sol must now reason about what to do next
```

That should **not** reopen Task A or reinterpret its terminal state as `awaiting_controller`.

The goal-level control layer must be able to say:

```text
new observation exists for Sol
```

while leaving Task A truthfully terminal.

This distinction prevents execution state from being corrupted for cognitive convenience.

---

# 4. The current Task plane already contains many reusable loop ingredients

## 4.1 Idempotency and versioning

**REPOSITORY FACT**

Task has:

- controller request identity;
- normalized request hashing;
- idempotent replay;
- state version CAS;
- durable commands.

**INFERENCE**

Future Sol-loop actions should reuse these mechanics rather than inventing another execution-idempotency layer.

A loop/cycle may need its own controller-turn identity, but action execution should still resolve to canonical Tasks.

## 4.2 Objective and constraints are already references

**REPOSITORY FACT**

Task already has `objective_ref` and `constraints_ref` rather than forcing large objective/constraint bodies into the Task row.

**INFERENCE**

The control-loop layer should follow the same reference-first principle.

Large plans, user text, reports, or context should remain content-addressed or memory/artifact references where possible. The loop should carry compact identity/state, not duplicate context bodies.

## 4.3 Task events provide ordered mechanical history

**REPOSITORY FACT**

Task events contain:

- ordered ID;
- timestamp;
- level;
- stage/message;
- state/state version;
- structured data.

Task projections are intentionally compact and reference authoritative result/evidence retrieval rather than embedding large bodies.

**INFERENCE**

The same design style is suitable for goal-level observations: ordered small events/references plus explicit retrieval pointers.

---

# 5. Interactive worker messaging contains useful delivery mechanics, not the Sol-loop identity

## 5.1 Substrate deliberately owns no second lifecycle

**REPOSITORY FACT**

`soma/worker_substrate/models.py` explicitly states:

- provider session is a binding fact, not another running lifecycle;
- no provider enum is made canonical;
- no queued/running/terminal vocabulary is duplicated;
- interactive commands remain subordinate to canonical Task.

`InteractionCoordinator` atomically reserves a TaskCommand and subordinate message.

`InteractionDispatcher` uses persist-before-send and records transport `outcome_unknown` rather than blindly retrying when delivery outcome is ambiguous.

## 5.2 Relevance to the Sol loop

**INFERENCE**

This subsystem provides good reusable patterns:

- persist decision-bearing intent before effect;
- exact sender/recipient and idempotency identity;
- payload-by-reference;
- state-version binding;
- ambiguity preserved rather than guessed.

But provider-session/message identity should not become the normal Chat goal identity.

Normal Chat's Sol control loop may have no subordinate provider session at all.

---

# 6. Workflow is too execution-plan-centric to be the default normal-Chat loop

## 6.1 Current Workflow semantics

**REPOSITORY FACT**

`soma/workflows/models.py` defines an independent workflow lifecycle with:

- `workflow_id`;
- objective;
- fixed step graph;
- workflow status;
- step statuses;
- worker lease/generation/PID;
- active child Run;
- result/publication state;
- recommended next action.

Step types are execution-specific (`project_command`, pytest, git read-only, local summary; old Codex step retained only for historical parsing).

## 6.2 Why it is not the default Sol loop

**INFERENCE**

A normal Sol agentic cycle is not necessarily a predeclared static workflow.

Sol often chooses the next action **after observing the previous result**.

Forcing every normal Chat goal into Workflow would:

- require premature plan materialization;
- create a second lifecycle beside canonical Task;
- add worker/lease machinery unrelated to cognitive continuity;
- make simple one-action loops unnecessarily heavy;
- risk Soma owning planning decisions that should remain with Sol.

Workflow algorithms may still be useful for explicitly deterministic known sequences. They should not define normal Chat's cognitive loop by default.

---

# 7. Supervisor is especially unsuitable as the core Sol-loop brain

## 7.1 Current Supervisor behavior

**REPOSITORY FACT**

`soma/supervisor/models.py` and `soma/supervisor/supervisor_flow.py` define an independent supervisor lifecycle including states such as:

```text
inspecting
planning
validating_locally
needs_external_coder
needs_input
completed
```

The flow performs local inspection, creates a plan, uses heuristics and optionally a local model, decides whether an external-coder handoff is needed, runs validation, and writes recommended-next-action/question-for-ChatGPT outputs.

## 7.2 Architectural problem

**OWNER REQUIREMENT**

Normal Chat/Sol should own important reasoning and next-action decisions.

**INFERENCE**

Supervisor's historical design is almost exactly the kind of duplicate planning/semantic layer that the corrected architecture should avoid as the default control loop.

Useful parts may include reporting, durable artifacts, validation wrappers, or return prompts. Its planning/decision lifecycle should not become the Sol agentic add-on.

A later cleanup iteration should classify Supervisor functionality piece by piece.

---

# 8. Memory/knowledge is necessary context but not transactional control state

## 8.1 Existing memory models

**REPOSITORY FACT**

Soma has memory/knowledge records for:

- static memory;
- run memory;
- artifact memory;
- decision memory;
- job memory;
- controller/owner knowledge with lifecycle/provenance;
- project/repository facts and source references.

These are useful continuity/context systems.

## 8.2 Why memory alone is insufficient

**INFERENCE**

A durable Sol loop needs exact transactional answers to questions such as:

- Did Sol already issue this action?
- Which Tasks belong to this controller cycle?
- Which observations arrived after Sol last reasoned?
- Has Sol already consumed this observation?
- Is an external effect outcome unknown?
- Did Sol explicitly declare the overall goal complete?

Generic memory retrieval is not the right authority for those questions.

Memory may preserve/refine durable context and accepted decisions, but loop/action/observation identity should remain mechanically exact.

---

# 9. ProjectScope is scope/ownership, not cognitive state

**REPOSITORY FACT**

ProjectScope provides project/resource identity, generation, access mode, Task/attempt binding state, and quarantine semantics.

**INFERENCE**

The Sol loop should reference ProjectScope where relevant rather than create a second project/repository ownership model.

But ProjectScope cannot answer “what observation has Sol not yet considered?” or “has Sol declared this goal complete?”

Therefore it complements but does not replace loop state.

---

# 10. The minimum durable information Sol actually needs

This section is a research proposal, not a final schema.

## 10.1 Goal/loop identity

**INFERENCE**

A continuing normal-Chat objective likely needs one stable identity independent of any individual Task backend.

Minimum candidate facts:

```text
loop_id
controller_kind = chatgpt_sol / opaque controller identity
project/scope ref if relevant
objective_ref (+ content hash if needed)
constraints/context refs if needed
state_version
created/updated timestamps
```

The objective should be stored/referenceable because after Chat interruption the owner may simply say “continue,” and Sol needs to know which durable work context Soma believes is active.

The final name does not have to be `loop` or `controller_loop`.

## 10.2 Controller-turn identity

**INFERENCE**

One Sol reasoning turn can issue:

- zero actions;
- one action;
- multiple actions.

For replay safety and observation accounting, the loop probably needs a durable concept equivalent to a **controller turn/cycle**.

Candidate facts:

```text
turn_ref / cycle_ref
loop_id
expected loop state version
controller-authored decision/plan reference (optional)
issued Task refs
created timestamp
turn sealed/acknowledged marker
```

The turn record must not store private chain-of-thought. A compact plan/decision summary or explicit next-action intent may be stored only if Sol intentionally publishes it as durable controller state.

## 10.3 Action links

**INFERENCE**

Every effectful/external action remains a canonical Task.

The loop needs only a durable relation:

```text
controller turn -> Task(s)
```

with optional role/purpose metadata.

It should not copy Task status, process identity, result bodies, or backend evidence into the loop record.

## 10.4 Observation stream

**INFERENCE**

Soma needs a small ordered observation/event stream representing things that may matter to the next Sol turn.

Candidate observation kinds include:

```text
task_started
task_terminal
result_published
checkpoint_opened
checkpoint_resolved
recovery_required
uncertain_external_effect
owner_input_available
memory/context changed (only when explicitly relevant)
```

Each observation should primarily contain:

```text
observation sequence/id
timestamp
source Task/Run/checkpoint ref
mechanical disposition
evidence/result retrieval ref
small bounded summary only where mechanically sourced
```

Soma should not write semantic interpretations such as “this failure means change library X.” That remains Sol's job.

## 10.5 Observation-consumption cursor

**INFERENCE - IMPORTANT**

The smallest robust answer to “does Sol need another turn?” may not be a large lifecycle state machine at all.

A simple pattern is:

```text
latest_observation_seq
last_observation_seq_consumed_by_Sol
```

If new decision-relevant observations exist after the last Sol-consumed cursor, then Soma can mechanically report:

```text
controller_turn_required = true
```

This does not decide **what** Sol should do.

It only reports that the environment changed since Sol last reasoned.

This concept deserves direct testing in a later prototype/research exercise before any schema is accepted.

## 10.6 Unresolved uncertainty

**REPOSITORY FACT**

Soma already models outcome-unknown/uncertain conditions conservatively in Task/backend/transport layers.

**INFERENCE**

The loop projection should collect references to unresolved uncertainty but must not duplicate or reinterpret them.

Sol must be able to see:

```text
unresolved_action_refs
reason/evidence refs
```

before issuing a potentially duplicate external effect.

## 10.7 Goal completion

**OWNER REQUIREMENT**

Soma must not decide semantically that the user's goal is complete merely because Tasks are terminal.

**INFERENCE**

Goal completion should require an explicit controller/Sol declaration (or owner cancellation), bound to the current loop state version.

Soma may mechanically report:

```text
all_current_actions_terminal = true
```

but that is not equivalent to:

```text
goal_complete = true
```

This distinction is central to preserving Sol as the brain.

---

# 11. Derived loop conditions instead of another giant lifecycle

A major research goal is to avoid creating another heavyweight state machine.

## 11.1 Conditions Soma can derive mechanically

**INFERENCE**

From action links, Task state, checkpoints, recovery evidence, observation cursors, and explicit controller declarations, Soma could derive projections such as:

```text
waiting_on_external_action
new_observation_available
controller_turn_required
interactive_task_awaiting_input
unresolved_uncertainty
all_current_actions_terminal
controller_declared_complete
owner_cancelled
```

These are orthogonal facts, not necessarily one mutually exclusive enum.

## 11.2 Why orthogonal facts may be better

A loop can simultaneously be:

```text
one Task still running
AND
one earlier Task has new evidence
AND
one uncertain effect needs review
```

A single status enum tends to hide such combinations or becomes enormous.

**INFERENCE**

The normal-Chat add-on may therefore need **less** lifecycle state than Workflow/Supervisor, not more.

A small versioned record + action links + ordered observations + explicit completion declaration may be enough.

This remains a hypothesis to validate.

---

# 12. How a normal-Chat cycle could work without automatic wake-up

This is a behavioral research model, not implementation pseudocode.

## 12.1 Start or continue

```text
Owner -> normal Chat/Sol: objective / "continue"
Sol queries or creates the durable loop context
Soma returns compact current state + unconsumed observations
```

## 12.2 Sol reasons

```text
Sol interprets objective + observations
Sol decides zero/one/many next actions
```

Any durable plan summary stored in Soma is controller-authored output, never hidden chain-of-thought.

## 12.3 Sol acts

```text
Sol submits one controller turn/cycle
Soma persists turn identity/version
Soma reserves/links canonical Task(s)
Tasks execute through existing backends/tools
```

For simple one-action work, the UX may collapse this into one high-level call while preserving the same durable facts underneath.

## 12.4 Environment changes

```text
Task states/results/checkpoints/recovery facts change
Soma appends compact observation refs
```

No model reasoning is required for this bookkeeping.

## 12.5 Long job case

```text
Sol/Chat goes away
Task continues durably
Task completes
observation/result ref is persisted
owner later wakes Chat
```

No replacement reasoning backend is invoked.

## 12.6 Sol returns

```text
Sol queries loop continuation bundle
Soma returns only new/unconsumed observations + relevant active/uncertain action refs
Sol acknowledges/advances observation cursor
Sol reasons again
```

## 12.7 Stop

```text
Sol explicitly declares goal complete
or owner cancels/abandons it
```

Task completion by itself never closes the goal.

---

# 13. Proposed continuation bundle for Sol

One core usability requirement is that continuation should help Sol rather than dump bookkeeping on it.

**INFERENCE**

A compact continuation response should probably include:

```text
loop identity + version
objective reference / compact controller-authored objective
project/scope identity if relevant
controller-declared constraints/stop criteria refs
active action Task refs + compact states
new observations since last Sol cursor
terminal result/evidence retrieval refs
open interactive checkpoints
unresolved uncertainty/recovery refs
last controller-authored plan/next-intent ref if one exists
mechanical flags:
  waiting_on_external_action
  controller_turn_required
  all_current_actions_terminal
explicit completion/cancellation declaration if present
```

It should **not** include by default:

- entire Chat transcript;
- private model reasoning;
- full stdout/stderr;
- repeated evidence bodies;
- provider-native child-agent transcripts;
- automatically invented recommended next action.

This keeps the add-on context-efficient and reduces the chance that durable state competes with ChatGPT's own context rather than helping it.

---

# 14. Multiple actions and optional parallelism

## 14.1 One Sol turn may issue several independent actions

**OWNER REQUIREMENT / INFERENCE**

Normal Chat agentic capability should not require a separate reasoning worker merely to parallelize execution.

Sol may decide:

```text
inspect A
inspect B
run test C
```

and Soma can link several canonical Tasks to one controller turn.

## 14.2 No generic DAG is required for every case

If the actions are independent, a list of action links plus existing Task lifecycle may be enough.

If actions have real dependencies or mission-level structure, existing/planned DAG concepts may become useful.

**INFERENCE**

DAG machinery should be an optional escalation based on work structure, not a prerequisite for the Sol loop.

This directly supports the owner's “help rather than make things harder” requirement.

---

# 15. No-action reasoning turns must be legitimate

**INFERENCE**

A proper Sol control loop must allow a reasoning turn that issues no external Task.

Examples:

- Sol determines the goal is complete;
- Sol asks the owner a clarifying question;
- Sol updates a controller-authored plan/constraint;
- Sol decides to wait for an already-running action;
- Sol decides an uncertain effect must be manually adjudicated before continuing.

This is another reason Task cannot itself be the controller-turn identity.

---

# 16. `Sol should reason again` must be mechanical, not semantic

The owner specifically asked how Soma can represent that another Sol turn is needed without Soma itself making semantic decisions.

## 16.1 Candidate rule

**INFERENCE**

Soma may report `controller_turn_required` when one or more mechanically named conditions hold, for example:

1. an unconsumed terminal/result observation exists;
2. an interactive checkpoint requires controller input;
3. a recovery/uncertainty condition requires controller adjudication;
4. the owner supplied new input to the loop;
5. Sol explicitly scheduled/marked a future controller checkpoint and it became due.

## 16.2 What Soma must not do

Soma must not set `controller_turn_required` because it semantically inferred:

- test failure means edit code;
- source A contradicts source B;
- the goal is probably complete;
- a new plan is better;
- another model should be consulted.

Those are Sol judgments.

## 16.3 Awaiting external action is different

If all relevant current actions are still running and there is no unconsumed decision-bearing observation, Soma can mechanically report:

```text
waiting_on_external_action = true
controller_turn_required = false
```

The owner can still wake/query Chat at any time. This is not a scheduler requirement.

---

# 17. Company/Mission/Plan does not belong in the core simple loop

**REPOSITORY FACT**

Company/Mission/Plan provides higher-level organizational/plan/work-package concepts and is currently frozen by owner direction.

**OWNER REQUIREMENT**

Company must not be reactivated or reinterpreted as the next implementation track.

**INFERENCE**

The minimal normal-Chat loop should not depend on Company/Mission/Plan.

Possible future relationship:

```text
simple personal task
 -> Sol loop + canonical Tasks

large explicit mission/company programme
 -> Mission/Plan/WorkPackages may supply higher-order objective/dependency context
 -> execution still canonical Tasks
 -> Sol/Work remains reasoning authority according to mode
```

This lets Company complement long-horizon structure without forcing every conversation into organizational machinery.

---

# 18. Work mode should probably reuse execution facts but not the Chat loop driver

**DOCUMENTED FACT from Iteration 1**

ChatGPT Work already supplies native multi-step agentic reasoning and subagent behavior.

**INFERENCE**

The Task/result/evidence/recovery substrate described here is still useful to Work.

But Work may not need Soma's normal-Chat **controller-turn driver** because Work already owns its cognitive agent loop.

Mode-aware architecture may therefore look like:

```text
NORMAL CHAT
Sol
 -> lightweight durable Sol-loop context
 -> canonical Tasks / Soma execution
 -> observations
 -> Sol

WORK
Work-native agentic loop / Sol
 -> canonical Tasks / Soma execution
 -> observations
 -> Work-native loop continues
```

The same action/evidence substrate can serve both without duplicating Work's planning/agent layer.

---

# 19. Relationship to the current `reasoning` Task/backend

This iteration does not decide removal.

## 19.1 Core-path conclusion

**INFERENCE**

The `REASONING` Task/backend is not required to implement the minimum normal-Chat Sol loop described above.

The core loop can function with:

```text
Sol reasoning
canonical durable action Tasks
observation references
Sol reasoning again
```

## 19.2 Possible future optional role

A reasoning backend may remain useful if Sol/owner explicitly wants a bounded specialist/model task, such as:

- independent second opinion;
- parallel research specialist;
- provider-native subagent tree outside Work;
- deliberately delegated analysis.

In that case it should be treated as **optional specialist execution**, not “the thing that makes Chat agentic.”

Later component audit must decide whether the current `TaskKind.REASONING` name/location is still the cleanest representation for that optional function.

---

# 20. Iteration 3 provisional minimal architecture

```text
                         OWNER
                           |
                           v
                    NORMAL CHAT / SOL
                           |
                       reason turn
                           |
               controller-authored intent
                           |
                           v
              +----------------------------+
              | lightweight durable loop   |
              | identity/version           |
              | turn/cycle refs            |
              | Task links                 |
              | observation cursor         |
              | explicit completion marker |
              +-------------+--------------+
                            |
                    zero / one / many
                     canonical Tasks
                            |
          +-----------------+------------------+
          |                 |                  |
      local/tool         long run          external service
      execution          execution         execution
          |                 |                  |
          +-----------------+------------------+
                            |
                Task/result/evidence truth
                            |
                     observation refs
                            |
              +-------------v--------------+
              | new observations since Sol |
              | unresolved uncertainty     |
              | active action refs         |
              +-------------+--------------+
                            |
                owner wakes Chat if needed
                            |
                            v
                    NORMAL CHAT / SOL
                      reason again
```

Optional PulseSender/browser delivery can sit beside the observation layer without changing reasoning ownership.

---

# 21. What changed in our understanding

## Before Iteration 3

A plausible idea was that existing `awaiting_controller` plus Task state might already be enough for the full loop.

## After source audit

**INFERENCE**

That is too simple.

`awaiting_controller` is excellent for a **non-terminal action waiting for input**, but the overall Sol goal must survive across terminal Tasks and multiple Tasks.

Therefore the corrected architecture likely needs a **very small goal/controller layer distinct from execution Task state**.

The important word is **small**.

It should not recreate Workflow, Supervisor, Company Kernel, or a model agent runtime.

The minimal candidate is closer to:

```text
stable loop identity
+ controller-turn/cycle identity
+ links to canonical Tasks
+ ordered observation refs
+ Sol-consumption cursor
+ explicit Sol completion declaration
```

This is a research hypothesis, not yet an implementation plan.

---

# 22. Open questions for the next iteration

1. Can the loop layer be represented as a small append-only event ledger plus one projection row rather than multiple lifecycle tables?
2. Is an explicit controller-turn record required, or can turn identity be safely encoded through idempotency/request grouping?
3. How should normal Chat obtain/reuse a stable loop ID when a conversation restarts or the owner says “continue”?
4. Should one normal Chat conversation have multiple concurrent active loops?
5. How does the loop bind to project/scope without forcing every personal task into ProjectScope?
6. What exact events qualify as decision-bearing observations versus noise?
7. How should Sol acknowledge observation consumption atomically so reconnect does not lose or duplicate context?
8. Should controller-authored plan/next-action summaries be optional content-addressed artifacts?
9. How should owner input be represented when it arrives outside a currently open Task checkpoint?
10. Can existing Task links be extended/reused for loop-to-Task relations without making TaskStore own loop state?
11. How should a loop survive a fresh Chat thread where ChatGPT conversation history is unavailable but Soma state remains?
12. How should Work identify that the normal-Chat loop driver is unnecessary while still using the same Task/evidence substrate?
13. Which exact Supervisor/Workflow/reasoning components should later be kept, moved, renamed, or retired once this minimal loop is proven?

---

# Sources inspected

## Official OpenAI sources

- OpenAI Agents SDK - `Running agents`: https://openai.github.io/openai-agents-python/running_agents/
- OpenAI Agents SDK - `Results`: https://openai.github.io/openai-agents-python/results/
- OpenAI Agents SDK - `Sessions`: https://openai.github.io/openai-agents-python/sessions/
- OpenAI Agents SDK - `Agents`: https://openai.github.io/openai-agents-python/agents/

These are used as a conceptual reference for model/tool/result/continuation boundaries only. They are not proposed as Soma runtime dependencies.

## Soma repository

- `soma/tasks/models.py`
- `soma/tasks/store.py`
- `soma/tasks/projections.py`
- `soma/tasks/manager.py`
- `soma/run_public_result.py`
- `soma/worker_substrate/models.py`
- `soma/worker_substrate/coordinator.py`
- `soma/worker_substrate/dispatch.py`
- `soma/worker_substrate/transitions.py`
- `soma/workflows/models.py`
- `soma/supervisor/models.py`
- `soma/supervisor/supervisor_flow.py`
- `soma/memory/models.py`
- `soma/knowledge/models.py`
- `soma/project_scope/models.py`
- `soma/return_loop/models.py`
- `soma/remote_controller_state.py`

## Prior realignment research

- `docs/sol-agentic-loop-realignment-research/iteration-01-current-chatgpt-work-native-agent-reality-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-02-original-intent-drift-and-normal-chat-addon-boundary-2026-08-15.md`
