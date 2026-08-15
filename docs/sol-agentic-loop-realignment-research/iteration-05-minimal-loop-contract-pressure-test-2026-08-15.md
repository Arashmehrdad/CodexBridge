# Iteration 5 - Minimal Loop Contract Pressure Test

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected: `938f1764dcab30a8bd8235ea2c822ba6d8c0826c`

## Scope

Iteration 3 proposed a lightweight durable layer containing some combination of:

```text
loop identity
controller turn/cycle identity
Task links
observation refs/cursor
explicit completion
```

Iteration 4 established that this layer is primarily a normal-Chat continuity capability and must not become a second Work agent loop.

Iteration 5 tries to **remove as much of the proposed layer as possible**.

The central question is:

> What is the smallest mechanically safe contract that lets Sol resume a user objective, know which canonical Tasks belong to it, detect which decision-relevant Task facts changed since Sol last considered them, and explicitly finish the objective?

This is a design-research pressure test only. No schema or runtime implementation is authorized.

## Hard constraints

No implementation, migration, runtime/service restart, Company activation, reasoning-provider activation, Codex use, provider generation, production config change, push, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

Company remains frozen.

Wake-up remains outside the core contract. Manual owner wake-up is sufficient.

Classification labels:

- **DOCUMENTED FACT** - current official OpenAI documentation.
- **REPOSITORY FACT** - current Soma source/docs/history evidence.
- **OWNER REQUIREMENT** - explicit owner direction.
- **INFERENCE** - supported design conclusion, not implementation authority.
- **OPEN QUESTION** - intentionally unresolved.

---

# 1. Pressure-test rule: every new durable concept must justify itself

The proposed normal-Chat layer is not allowed to grow merely because agent frameworks commonly have sessions, runs, turns, messages, plans, observations, checkpoints, and traces.

**OWNER REQUIREMENT**

The add-on must help Sol rather than make normal Chat harder.

**INFERENCE**

Therefore a new durable concept survives this iteration only if an existing Soma authority cannot answer the required question safely.

The required questions are narrow:

1. What user objective is Sol still pursuing?
2. Which canonical Tasks/actions belong to that objective?
3. Which Task facts have changed since Sol last considered them?
4. Are any linked actions still active or uncertain?
5. Has Sol explicitly declared the objective complete?
6. Can repeated/replayed loop mutations be detected safely?
7. Can a fresh Chat discover enough durable state to continue?

Everything else should be derived or referenced.

---

# 2. Existing Task tables cannot themselves represent the goal

## 2.1 Task has strong execution identity

**REPOSITORY FACT**

The accepted Task schema stores:

- one `task_id`;
- one globally unique `controller_request_id`;
- one normalized request hash;
- one Task kind;
- one selected backend kind/executor/reference;
- state/phase/version;
- result/evidence/recovery references;
- optional parent Task;
- workspace identity;
- checkpoints/events/commands/links in subordinate tables.

The same SQLite database contains Task and Run authorities, allowing transactional coordination without a second database.

## 2.2 One Task cannot safely become one overall Sol goal

**INFERENCE**

A goal may span many terminal Tasks. Task terminality must retain its execution meaning.

Therefore one distinct goal/control identity still survives the minimization pass.

**SURVIVES:** one small durable **loop/objective record**.

---

# 3. Existing `workspace_kind/workspace_ref` cannot be repurposed as loop identity

## 3.1 Current meaning

**REPOSITORY FACT**

Task `workspace_kind` / `workspace_ref` are actively populated by current code.

Durable command Task creation uses:

```text
workspace_kind = "repository"
workspace_ref  = effective_repo_name
```

Reasoning Task creation uses the same repository meaning.

Company admission and worker activation fixtures also use the fields as repository workspace identity.

## 3.2 Conclusion

**INFERENCE - REJECTED SHORTCUT**

Do not redefine `workspace_ref` to mean a Sol-loop identifier.

Doing so would overload an accepted field with a fundamentally different concept and make old/new Task projections ambiguous.

If a loop-to-Task relationship is needed, represent it explicitly.

---

# 4. Existing Task links cannot express loop ownership without changing their contract

## 4.1 Current link contract

**REPOSITORY FACT**

`TaskLinkTargetKind` currently allows only:

```text
task
durable_run
backend
```

`TaskLinkType` includes:

```text
parent
child
backend_run
backend
related
supersedes
```

The `task_links` table's source is always a canonical Task.

## 4.2 Could `related` point to a loop anyway?

No under the current typed contract: there is no loop target kind.

## 4.3 Options

### Extend Task links with `controller_loop`

Advantages:
- reuse existing table/indexing;
- natural reference graph.

Costs:
- changes accepted Task link vocabulary;
- makes TaskStore partially responsible for a new higher-level control concept;
- requires migration/model/public projection changes;
- relationship direction is awkward because Task is the source while loop is the owner/group.

### Separate loop-to-Task membership table

Advantages:
- Task contract remains unchanged;
- loop owns only its own membership facts;
- exact unique ownership policy can be stated independently;
- can carry observation-consumption bookkeeping without polluting Task links.

Cost:
- one new small table.

## 4.4 Iteration 5 result

**INFERENCE**

A dedicated loop-to-Task membership record is cleaner than overloading current Task links.

**SURVIVES:** explicit loop-to-Task membership.

This does not mean a complex DAG. It is only a membership/ownership edge.

---

# 5. A first-class controller-turn table does NOT survive the minimization pass

## 5.1 Why a turn initially seemed useful

Iteration 3 noted that one Sol turn may issue zero, one, or many Tasks and suggested a turn/cycle identity for grouping actions.

## 5.2 What safety property actually requires a turn?

Pressure testing found no core property that requires a durable turn row.

The loop needs to know:

- which Tasks belong to the objective;
- what Task facts Sol has already consumed;
- whether the objective is explicitly complete.

It does **not** need to reconstruct every ChatGPT reasoning turn.

## 5.3 Multiple actions do not require a turn record

Sol can attach multiple canonical Tasks to the same loop.

Their exact action identities and request idempotency remain Task-owned.

If a future feature needs to say “these three actions came from one controller decision,” an optional opaque batch/correlation reference can be added to membership/command metadata without creating a new lifecycle.

## 5.4 Zero-action turns do not require a turn record

A zero-action Sol turn can:

- continue waiting;
- update the durable objective/constraints reference if needed;
- declare completion;
- ask the owner a question in Chat.

None requires a persisted turn entity.

## 5.5 Result

**INFERENCE - REMOVED FROM MINIMAL CORE**

No first-class `controller_turn` / `cycle` table is justified for the minimal normal-Chat loop.

This is a material simplification from Iteration 3.

---

# 6. A separate durable observation table may also be unnecessary

## 6.1 Existing authoritative observation source

**REPOSITORY FACT**

Canonical Task already exposes the decision-relevant mechanical facts needed by Sol:

- state;
- phase;
- state version;
- backend status/reference;
- checkpoint reference/open count;
- result reference/hash/publication;
- evidence reference;
- recovery state/reason;
- timestamps;
- Task events for detailed history.

Task projections deliberately reference authoritative evidence rather than duplicating bodies.

## 6.2 Duplicating Task transitions into loop observations creates a second truth

A new observation table that copies:

```text
Task A completed
result hash X
recovery state Y
```

creates synchronization questions:

- what if Task commits but observation append crashes?
- what if observation arrives twice?
- which copy is authoritative?
- must every Task transition know about loop membership?
- do read-only queries now mutate to backfill observations?

These problems are avoidable if the loop treats Task as the observation authority.

## 6.3 The actual missing fact is “has Sol already considered this Task state?”

**INFERENCE - KEY MINIMIZATION**

The loop does not need a second copy of the observation.

It needs a durable **consumption baseline** for each linked Task.

Conceptually:

```text
current_task_observation = canonical projection of decision-relevant Task fields
current_hash = hash(current_task_observation)

last_consumed_hash = loop membership bookkeeping

if current_hash != last_consumed_hash:
    new observation exists for Sol
```

## 6.4 Result

**INFERENCE - REMOVED FROM MINIMAL CORE**

A standalone `loop_observations` table is not currently justified.

Task/Run/checkpoint/evidence remain authoritative observations.

The loop stores only which exact Task observation Sol has acknowledged/consumed.

---

# 7. State version alone is not the best observation cursor

## 7.1 Candidate: `last_consumed_task_state_version`

Simple approach:

```text
membership.last_consumed_state_version = N
```

If Task state version increases, Sol has not seen the newest Task state.

## 7.2 Problem

**INFERENCE**

Task state version is an ownership/concurrency version, not explicitly a semantic observation version.

Future Task changes could increment it for mechanically important but controller-irrelevant fields, and relying on its current exact mutation behavior would couple the loop to internal implementation details.

Conversely, a future result/evidence metadata change could matter even if its relationship to state version changes.

## 7.3 Better candidate: mechanical observation fingerprint

Compute a canonical hash over a deliberately versioned, bounded set of Task fields relevant to controller continuation.

Research shape:

```text
TaskObservationV1 = {
    task_id,
    task_kind,
    state,
    phase,
    state_version,          # included as evidence, not sole trigger
    backend_kind,
    backend_ref,
    result_ref,
    result_hash,
    evidence_ref,
    checkpoint_ref,
    recovery_state,
    recovery_reason
}

observation_hash = SHA256(canonical(TaskObservationV1))
```

The exact field set is not final.

## 7.4 Why this is stronger

- Task remains authoritative;
- loop does not duplicate Task values;
- observation meaning is explicitly versioned;
- incidental Task internals can be excluded;
- result/recovery/checkpoint changes are visible;
- acknowledgement can be exact and replay-safe.

**SURVIVES:** per-membership last-consumed **observation hash**, not copied observation body.

---

# 8. Observation acknowledgement can be explicit and atomic

## 8.1 Required behavior

When Sol receives a continuation bundle, it should be able to say:

```text
I have considered Task A at observation hash H1
I have considered Task B at observation hash H2
```

## 8.2 Stale-ack safety

**INFERENCE**

An acknowledgement must not accidentally consume a newer Task state that arrived between query and acknowledgement.

A safe conceptual operation is:

```text
acknowledge_observations(
    loop_id,
    expected_loop_version,
    [{task_id, expected_observation_hash}, ...],
    controller_request_id
)
```

Inside the shared SQLite transaction, Soma recomputes each current observation hash.

If any differs from the supplied hash, the acknowledgement fails stale rather than marking unseen evidence as consumed.

If all match, membership `last_consumed_observation_hash` values advance atomically.

## 8.3 Why shared database matters

**REPOSITORY FACT**

Canonical Task tables already live in `runs/soma.sqlite3` specifically so Task/Run-related control facts can be coordinated transactionally.

**INFERENCE**

If a future loop component lives in the same database, exact acknowledgement can reuse the same transactional pattern without a distributed consistency problem.

---

# 9. `controller_turn_required` becomes a pure derived projection

## 9.1 No lifecycle state needed

**INFERENCE**

Soma can derive:

```text
new_observation_available
```

by comparing current Task observation hashes with membership consumption hashes.

It can derive:

```text
controller_turn_required
```

when an unconsumed observation is mechanically decision-bearing.

## 9.2 Decision-bearing conditions

Research candidate conditions include current Task observation showing:

- terminal completion/failure/cancellation;
- `awaiting_controller` checkpoint;
- `recovery_pending`;
- `uncertain`;
- changed result/evidence publication;
- changed unresolved recovery/ambiguity fact.

A Task merely remaining `queued` or `running` does not by itself require another Sol reasoning turn.

## 9.3 Soma still does not decide the next action

The projection means only:

```text
something changed that requires/justifies controller attention
```

not:

```text
edit code
retry
use Codex
change plan
mark goal complete
```

Those remain Sol decisions.

---

# 10. A small loop projection row survives

## 10.1 Why pure event sourcing is unnecessary here

One option was an append-only loop event ledger with all state derived from events.

That gives strong history, but the minimal contract still needs efficient:

- active-loop discovery;
- CAS versioning;
- current objective/constraints references;
- explicit completion state.

A small projection row is simpler.

## 10.2 Candidate minimal loop row

Research-only shape:

```text
ControllerLoopV1
    loop_id
    label                       # bounded discovery hint, optional
    objective_ref
    objective_hash              # if referenced object contract supports it
    constraints_ref             # optional
    state = open | completed | cancelled
    state_version
    created_at
    updated_at
    closed_at?
```

Fields deliberately absent:

- Chat conversation ID;
- Work/Chat mode;
- model/provider name;
- reasoning effort;
- plan graph;
- current reasoning text;
- transcript;
- worker identity;
- backend reference;
- process state;
- mission/company identity;
- automatic next action.

## 10.3 Do we need `project_id`?

**INFERENCE**

Not in the minimal core.

A personal objective may span multiple repositories/services, while canonical Tasks already carry their exact ProjectScope where required.

Loop discovery can later index/derive linked project resources without making one project own the whole objective.

If a particular implementation needs an optional project hint, it should remain non-authoritative metadata rather than a universal ownership requirement.

---

# 11. Loop-to-Task membership row survives

Research-only shape:

```text
ControllerLoopTaskV1
    loop_id
    task_id
    attached_at
    last_consumed_observation_hash
    last_consumed_at?
    correlation_ref?            # optional, not required for core
```

## 11.1 Ownership policy

**OPEN QUESTION**

Should one canonical Task be owned by at most one active controller loop?

Strong default hypothesis:

- one loop may link many Tasks;
- one Task has one **control owner loop**;
- other goals may reference that Task's result/evidence without sharing execution ownership.

This would prevent two independent loops from both deciding they own cancellation/retry semantics for the same effectful action.

But the policy must be tested against legitimate cross-goal reuse before being accepted.

## 11.2 No Task result duplication

Membership contains no Task state/result body.

It only points to Task and records the last exact observation Sol consumed.

---

# 12. Idempotency requires a small command journal

## 12.1 Why loop row + membership alone is not enough

**OWNER REQUIREMENT / REPOSITORY PRECEDENT**

Soma's durable control operations should be safe under retries, reconnects, and ambiguous client delivery.

Task already implements controller-request idempotency and conflict detection.

A loop operation needs equivalent semantics.

## 12.2 Why `last_controller_request_id` on the loop row is insufficient

If request R1 succeeds, then R2 succeeds, and a delayed replay of R1 arrives, the current row cannot identify R1 safely if only the latest request is stored.

## 12.3 Minimal command journal

A small immutable command table survives:

```text
ControllerLoopCommandV1
    command_id
    loop_id
    operation
    controller_request_id
    request_hash
    expected_loop_version
    resulting_loop_version
    status
    created_at
    completed_at?
    result_ref? / compact disposition
```

Unique identity conceptually includes the controller request ID in the appropriate scope.

This table is not a second reasoning lifecycle. It is the replay/audit authority for loop mutations.

**SURVIVES:** loop command journal.

---

# 13. Final minimal storage candidate is three small authorities, not an agent framework

After removing turn and observation tables, the minimum credible durable set is:

```text
1. controller_loops
   current objective + explicit lifecycle + CAS version

2. controller_loop_tasks
   exact Task membership + last Sol-consumed observation hash

3. controller_loop_commands
   idempotency/replay/audit for loop mutations
```

Everything else is referenced or derived from existing authorities.

There is no:

- reasoning worker;
- agent process;
- turn table;
- message transcript;
- loop observation copy;
- DAG;
- scheduler;
- provider session;
- model configuration;
- hidden planner.

This is a much smaller design than the initial Agent/Worker architecture.

---

# 14. Do we need a separate loop event table?

## 14.1 Arguments for one

An event ledger could preserve:

- objective revisions;
- completion declarations;
- Task attachments;
- acknowledgement history;
- cancellation;
- human notes.

## 14.2 Arguments against one in the minimal contract

The immutable command journal already records every loop mutation request and its resulting version.

Task history remains in Task events.

Memory/knowledge can preserve durable semantic decisions when intentionally written.

A separate event table would duplicate command history unless a measured query/audit need appears.

## 14.3 Result

**INFERENCE - DEFER**

Do not add a fourth loop-event table in the minimal design.

Use the command journal as mutation history unless later evidence shows it is insufficient.

---

# 15. Do we need durable controller identity?

## 15.1 Earlier hypothesis

Iteration 4 considered a `controller_ref` distinct from Chat/Work mode.

## 15.2 Pressure test

What core safety property would it add today?

Current normal Chat integration does not expose a proven stable controller-instance identity.

Inventing `controller_ref="sol"` would not distinguish sessions/controllers and would provide no real authority.

Task operations already rely on explicit request IDs, state versions, project/resource authority, and the authenticated app/user path rather than a model-name identity.

## 15.3 Result

**INFERENCE - REMOVED FROM MINIMAL CORE**

Do not require a durable `controller_ref` until there is a real external identity to bind and a named safety/ownership need.

The loop command journal + expected state version + request hash is enough for current controller mutation ordering.

If a future ChatGPT platform exposes a trustworthy controller/session identity, it can be added as provenance without redefining loop semantics.

---

# 16. Do we need Chat conversation identity?

## 16.1 No current reliable field

Iteration 4 found no documented inbound Chat-vs-Work surface marker, and current Soma source has no conversation ID field.

## 16.2 Architecture should work without one

**OWNER REQUIREMENT**

Fresh Chat continuation is important.

Binding loop truth to one conversation would actually make recovery worse if the owner starts a new Chat.

## 16.3 Result

**INFERENCE - EXPLICITLY EXCLUDED**

A Chat conversation/thread ID is not part of the core loop identity.

A future UI/delivery adapter may map a conversation to a loop for convenience, but the loop survives independently.

---

# 17. Fresh-Chat discovery can remain simple

## 17.1 Required behavior

Owner may say:

```text
continue
continue the Soma research
continue task X
```

Sol should be able to discover durable active loops without knowing an old Chat thread ID.

## 17.2 Minimal query capability

**INFERENCE**

A loop query surface needs at least:

```text
list open/recent loops
get one loop continuation projection
```

List projection can include bounded:

- loop ID;
- label;
- objective reference and perhaps small reference-derived title/summary;
- state/version;
- linked Task counts;
- active/uncertain counts;
- whether decision-bearing unconsumed observations exist;
- last update time.

Sol can use current user context to select the right loop.

## 17.3 Multiple active loops are legitimate

Do not enforce “one active loop per user/project.”

The owner may legitimately have several concurrent research, deployment, training, and administrative goals.

If selection is ambiguous, Sol can ask the owner or use explicit loop ID.

---

# 18. Continuation projection is computed, not stored

A `loop_query(status/continue)` result can join:

```text
controller_loop row
+ membership rows
+ current canonical Task compact observations
```

and derive:

```text
linked_task_count
active_tasks
unconsumed_task_observations
open_checkpoints
unresolved_uncertainty
all_linked_tasks_terminal
waiting_on_external_action
controller_turn_required
```

## 18.1 No semantic recommended-next-action

The projection must not invent:

```text
recommended_next_action = "edit X"
```

because that is exactly the judgment Sol should perform after seeing the evidence.

A mechanical hint such as:

```text
controller_turn_required = true
reason_codes = ["task_terminal_unconsumed"]
```

is acceptable.

---

# 19. Pressure-test scenarios

## Scenario A - one immediate action

```text
loop created only if durable continuation is useful
Task A attached
Task A completes
Sol queries continuation
Task observation hash differs from consumed baseline
Sol reasons
Sol acknowledges H(A)
Sol declares loop complete
```

Passes without turn/observation tables.

## Scenario B - three parallel inspections

```text
one loop
Tasks A/B/C attached
A and B complete; C still running
```

Projection:

```text
new observations: A, B
active: C
controller_turn_required: true
waiting_on_external_action: also true for C
```

Orthogonal derived facts handle the mixed state better than one giant loop enum.

Passes.

## Scenario C - long job outlives Chat

```text
Task A running
Chat disappears
Task A completes
owner later opens/wakes Chat
Sol queries loop
```

Current Task observation hash differs from stored consumed hash.

No background reasoning or wake-up required.

Passes.

## Scenario D - interactive Task waits for input

Task enters canonical `awaiting_controller` with checkpoint.

Loop projection exposes the current Task checkpoint as an unconsumed decision-bearing observation.

Sol supplies input through the existing Task checkpoint/interaction path, not through a duplicate loop checkpoint system.

Passes.

## Scenario E - uncertain external effect

Task current recovery/uncertainty fields change.

Observation fingerprint changes.

Loop projection reports unresolved uncertainty and requires controller attention.

Sol cannot accidentally acknowledge a newer changed observation because acknowledgement verifies the exact hash.

Passes conceptually.

## Scenario F - Sol reasons but launches no action

Sol may:

- leave loop open and wait;
- update objective/constraints reference through loop command;
- declare complete;
- cancel.

No turn record is needed.

Passes.

## Scenario G - fresh Chat, no old transcript

Sol lists open loops, retrieves one objective reference and current Task/observation projection, then continues.

No conversation ID required.

Passes if objective/constraint refs are sufficient; this becomes a later usability test.

## Scenario H - replayed loop mutation

Loop command journal binds controller request ID to request hash and expected loop version.

Identical replay returns recorded result; changed payload under same request ID conflicts.

Passes conceptually by reusing Task-plane patterns.

## Scenario I - Task changes during observation acknowledgement

Acknowledgement runs transactionally and recomputes current observation hashes.

Stale supplied hash fails; newer state remains unconsumed.

Passes conceptually.

## Scenario J - Task created but loop attachment crashes

This is a real design boundary.

If Sol creates Task through an ordinary Task call and then separately attaches it to the loop, a crash between the two can leave legitimate but unlinked work.

**OPEN QUESTION / IMPORTANT**

Implementation planning must decide how loop-owned actions obtain atomic membership without duplicating Task start semantics.

Candidates include:

1. optional loop ownership parameters at canonical Task reservation, validated through a loop coordinator in the same SQLite transaction;
2. a high-level loop action that delegates to existing TaskManager reservation while coordinating membership;
3. recoverable post-attachment using exact controller request linkage and explicit adoption.

No choice is made here.

This is probably the most important unresolved transactional seam after Iteration 5.

---

# 20. Should one Task belong to multiple loops?

## Case for many-to-many

One expensive research/inspection Task could provide evidence useful to several goals.

## Case against many control owners

Two loops that both “own” one mutable/effectful Task could conflict over:

- cancellation;
- retry/supersession;
- whether an uncertain effect is resolved;
- whether observation consumption implies anything about the other loop.

## Leading distinction

**INFERENCE**

Separate:

```text
execution/control ownership
from
evidence/result reuse
```

One Task should likely have at most one loop as its execution/control owner.

Other loops can reference its immutable result/evidence through existing evidence/reference mechanisms without becoming Task owners.

This follows Soma's existing preference for one canonical owner of an effectful execution identity.

Still open pending concrete cross-goal examples.

---

# 21. Explicit loop completion remains necessary

## 21.1 Why it cannot be derived

All linked Tasks terminal may mean:

- goal succeeded;
- goal failed and needs a new approach;
- evidence was insufficient;
- owner changed objective;
- another Task should be launched.

Soma cannot know semantically which.

## 21.2 Minimal lifecycle

**INFERENCE**

Only three loop states appear necessary so far:

```text
open
completed
cancelled
```

No `running`, `waiting`, `needs_input`, `planning`, or `reasoning` loop states are required because those are derived from linked Task facts or belong to Sol cognition.

## 21.3 Completion command

Sol explicitly issues completion under expected loop version.

Soma may mechanically warn/refuse if linked effectful Tasks are still non-terminal unless the command explicitly addresses them, but Soma does not decide whether the **goal** is semantically complete.

The exact active-Task closure policy is deferred.

---

# 22. Objective revision should update the loop, not create a Plan system

A goal may evolve after new evidence.

**INFERENCE**

Minimal loop should permit a versioned `update_context` / equivalent command changing:

- objective reference;
- constraints reference;
- label.

The command journal preserves prior request history.

This is not a PlanRevision DAG.

If a task genuinely requires immutable multi-package planning, higher-level plan machinery may be layered separately.

Normal Chat does not need PlanRevision to change “now validate the other service too.”

---

# 23. Private reasoning must never be persisted as loop state

**OWNER REQUIREMENT / PRODUCT BOUNDARY**

The add-on should preserve useful controller state, not hidden chain-of-thought.

Minimal loop stores only explicit, intentionally externalized controller facts such as:

- objective/constraints references;
- attached action identities;
- acknowledged mechanical observation hashes;
- explicit lifecycle commands.

If Sol intentionally wants to preserve a plan summary or decision, that can be written as a bounded controller-authored artifact/memory reference.

There is no `reasoning_text`, `thoughts`, or private scratchpad field in the minimal contract.

---

# 24. Why a command journal is not “another workflow”

It is important not to overreact to having a third table.

The loop command journal does not execute a plan or autonomously advance steps.

It answers only:

```text
Did this exact loop mutation happen?
Was it replayed?
What loop version did it observe/produce?
```

This is equivalent in spirit to Task command/idempotency evidence, not a cognitive worker.

---

# 25. Public operation hypothesis after minimization

No final public API is accepted, but the smallest useful conceptual surface is now much smaller than earlier hypotheses.

Possible query operations:

```text
capabilities
list
status / continue
```

Possible mutation operations:

```text
create
update_context
attach/adopt_task        # exact semantics unresolved
ack_observations
complete
cancel
```

There is no:

```text
reason
plan
spawn_worker
choose_backend
synthesize
auto_continue
```

in the loop API.

Sol does those cognitive operations outside Soma.

---

# 26. Relationship to direct Soma tool use

**INFERENCE**

The loop should remain optional.

If one Soma tool call returns quickly in the same active Chat and no durable continuation is useful, Sol can continue to call it directly.

The loop becomes useful when one or more are true:

- work may outlive the current Chat turn/session;
- multiple durable actions belong to one user objective;
- interruption/restart recovery matters;
- Sol needs an exact “what changed since I last looked?” projection;
- ambiguity/uncertainty must survive across turns.

This keeps normal Chat light.

---

# 27. Relationship to Work after minimization

The minimal loop is so small that Work could technically use it for external objective continuity, but **Work should not be required to**.

Work's native agentic loop can use canonical Soma Tasks directly.

If later evidence shows Work benefits from persistent external-action grouping, the same neutral loop record might serve as an optional external objective ledger without taking over planning.

No separate Work loop implementation is justified.

---

# 28. Relationship to current reasoning Task/backend

Nothing in the minimal loop requires `TaskKind.REASONING` or `BackendKind.SOMA_REASONING`.

Core normal-Chat path remains:

```text
Sol cognition
 -> loop bookkeeping when useful
 -> canonical execution Tasks
 -> Task observation hashes
 -> Sol cognition
```

Reasoning Tasks remain candidates for optional specialist delegation only and will be audited separately.

---

# 29. Iteration 5 proposed minimal architecture

```text
NORMAL CHAT / SOL
        |
        | explicit objective when durable continuation useful
        v
+-------------------------+
| ControllerLoop          |
| loop_id                 |
| label/ref(s)            |
| open/completed/cancelled|
| state_version           |
+------------+------------+
             |
             | membership
             v
+-------------------------+      +-----------------------------+
| ControllerLoopTask      |----->| canonical Task              |
| loop_id                 |      | authoritative execution     |
| task_id                 |      | state/result/recovery/etc.  |
| last_consumed_obs_hash  |      +-------------+---------------+
+-------------------------+                    |
             ^                                 |
             | current observation hash        |
             +---------------------------------+
             |
     continuation projection
             |
             v
       NORMAL CHAT / SOL

Loop mutations are protected by:

+-------------------------+
| ControllerLoopCommand   |
| request id/hash         |
| expected/result version |
| durable disposition     |
+-------------------------+
```

No second model exists in this architecture.

---

# 30. What was removed from the hypothesis

Compared with Iteration 3, Iteration 5 removes from the **minimal core**:

- first-class controller-turn table;
- first-class observation/event copy table;
- global observation cursor;
- controller identity field;
- Chat conversation identity;
- mode field;
- project ownership requirement;
- plan/DAG identity;
- hidden recommended-next-action;
- reasoning-provider identity.

What remains:

1. one small loop projection row;
2. one loop-to-Task membership row with last-consumed observation fingerprint;
3. one immutable loop command/idempotency journal.

This is currently the smallest design that still appears to satisfy durability, replay, multi-Task grouping, observation consumption, fresh-Chat discovery, and explicit completion.

---

# 31. Main unresolved seam: atomic Task ownership attachment

This is the next implementation-relevant research question, but implementation is not yet authorized.

We need to determine whether the future normal-Chat loop should:

- wrap Task reservation in a loop coordinator;
- add an optional loop ownership contract to Task start;
- or use a recoverable adoption protocol.

Requirements:

1. never fork Task execution logic;
2. never allow a crash to silently create an effectful unowned Task when the caller believed it was loop-owned;
3. preserve existing Task controller-request idempotency;
4. preserve ProjectScope authority;
5. permit direct Tasks outside any loop;
6. avoid changing unrelated public tools if possible.

This should be studied before selecting a public API.

---

# 32. Next research questions

Iteration 6 should focus on **reuse and cleanup mapping**, not add more loop concepts.

Specifically:

1. Which current Agent/Worker components map directly under the minimal loop?
2. Which current reasoning-backend components are reusable optional specialist infrastructure?
3. Which WorkerEvidence/FanIn pieces are useful only for true parallel specialist delegation and should stay off the simple path?
4. Which Supervisor/Workflow components duplicate Sol cognition versus provide useful deterministic execution/reporting?
5. Can the atomic loop-to-Task attachment reuse existing ProjectScope/Task reservation coordinator patterns?
6. What terminology should replace `reasoning worker`/`reasoning backend` in the core architecture?
7. Does the minimal loop need a new gateway family, or can a clean controller-plane gateway emerge from existing compatibility surfaces without semantic overload?
8. Which accepted historical gates should remain untouched but be superseded by a realignment decision document later?

No implementation plan should be written until those questions and the Company interaction audit are complete.

---

# Sources inspected

## Soma repository

- `soma/tasks/schema.py`
- `soma/tasks/store.py`
- `soma/tasks/models.py`
- `soma/tasks/manager.py`
- `soma/tasks/projections.py`
- `soma/company_kernel/admission.py`
- `soma/worker_gateway/activation.py`
- prior realignment research Iterations 1-4

## Official OpenAI reference retained from Iteration 4

- OpenAI API, `Model guidance`: https://developers.openai.com/api/docs/guides/latest-model

The external model guidance remains only a supporting conceptual reference: use direct model judgment where each tool result may change the next decision; use bounded programmatic execution where fresh judgment is unnecessary. The minimal Soma loop remains independent of the OpenAI API/Agents SDK.
