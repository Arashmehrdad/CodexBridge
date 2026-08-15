# Iteration 9 - Legacy/Public Surface Overlap and Compatibility Audit

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected during this iteration: `3c14b997e7f3d4dfff074695dc2509d7c38d5730`

## Scope

Iterations 1-8 have stabilized the corrected target concept:

```text
normal Chat / Sol
 -> lightweight durable Sol-loop bookkeeping when needed
 -> canonical Task / Run / tools
 -> observation/evidence
 -> Sol reasons again
```

with Work keeping its native ChatGPT agentic loop and optional specialists remaining off the default path.

Iteration 9 audits compatibility cost before final synthesis. It asks:

1. Which overlapping legacy orchestration paths are still public contracts?
2. Which are only internal/compatibility code?
3. Which tests/documentation make immediate removal expensive or unsafe?
4. Which reasoning-provider surfaces are public even while owner-disabled?
5. What can be deprecated/bypassed first without breaking historical compatibility?
6. Which accepted history should be superseded rather than rewritten?

No retirement or public-schema change is authorized here.

## Hard constraints

No runtime/service restart, Company activation, reasoning-provider activation, Codex use, provider generation, production config change, push, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

Company remains frozen.

Concurrent unrelated repository work was left untouched.

Classification labels:

- **REPOSITORY FACT** - current source/tests/docs/history evidence.
- **OWNER REQUIREMENT** - explicit owner direction.
- **INFERENCE** - supported compatibility/architecture conclusion, not implementation authority.
- **OPEN QUESTION** - unresolved until later implementation planning or consumer measurement.

---

# 1. Progressive convergence already anticipated Workflow/Supervisor overlap

## 1.1 Historical architecture warning

**REPOSITORY FACT**

`docs/V3_1A_INTERACTIVE_WORKER_SUBSTRATE_PLAN_2026-07-30.md` explicitly says:

> Workflows and supervisors are generic compatibility lifecycle managers.

It further says V3-1A should not broaden into their migration, and that a later lane which first uses equivalent planning/collaboration responsibilities must **project or retire the overlap under the progressive-convergence gate** rather than casually add another authority.

## 1.2 Importance now

**INFERENCE**

The proposed normal-Chat Sol loop is exactly the kind of later lane that touches adjacent continuation/orchestration territory.

Therefore the correct response is neither:

```text
leave Workflow/Supervisor forever because they are old
```

nor:

```text
delete them immediately because the new loop is cleaner
```

It is:

```text
introduce the minimal Sol loop without taking over their public contracts,
then progressively converge/retire overlapping legacy authorities with explicit compatibility gates.
```

This is consistent with already-accepted architecture history.

---

# 2. Workflow is still a first-class public gateway

## 2.1 Public inventory

**REPOSITORY FACT**

`PUBLIC_GATEWAY_INVENTORY` includes:

```text
workflow_query
workflow_action
```

`workflow_action` is described as a durable workflow mutation path.

Public tool metadata tells ChatGPT:

```text
Use this when the user explicitly wants to start or cancel a validated durable workflow.
Workflow steps can launch allowlisted project commands that may write files.
```

## 2.2 Server implementation

**REPOSITORY FACT**

`soma.server:workflow_action` is a real MCP tool.

It supports:

```text
start -> start_workflow(repo_name, objective, steps)
cancel -> cancel_workflow(workflow_id)
```

`workflow_query` publicly exposes status/events/result.

This is not dead internal code.

## 2.3 README contract

**REPOSITORY FACT**

README lists Workflows as a public tool family and says:

- `workflow_action` starts/cancels a durable dependency-ordered workflow;
- `workflow_query` reads status/events/results.

## 2.4 Test compatibility

**REPOSITORY FACT**

Current tests bind Workflow into:

- CF1 gateway operation inventory;
- MCP action discovery;
- flat public input contract;
- gateway model validation;
- server routing;
- transport content-text gate;
- workflow-specific durability/behavior tests (`test_workflow_durability.py`, `test_workflows.py`).

The CF1 test explicitly treats `workflow_action.start` as a durable action path with durable input/request echo.

## 2.5 Classification

**KEEP PUBLICLY FOR INITIAL REALIGNMENT; DEPRECATE/CONVERGE LATER WHERE OVERLAP IS PROVEN.**

Do not remove Workflow in the first Sol-loop patch.

Instead:

- keep it for explicit deterministic dependency-ordered workflows;
- stop treating it as the normal Chat cognitive loop;
- later measure whether equivalent deterministic sequences can converge onto canonical Tasks/parallel groups or a thinner workflow projection;
- preserve explicit users that genuinely request a workflow.

---

# 3. Supervisor is also a first-class public gateway

## 3.1 Public inventory and metadata

**REPOSITORY FACT**

Public inventory includes:

```text
supervisor_query
supervisor_action
```

Metadata says `supervisor_action` starts/resumes/pauses/cancels a durable supervisor and can advance child execution.

## 3.2 Server implementation

**REPOSITORY FACT**

`supervisor_action.start` calls:

```text
start_supervised_recovery_task(repo, objective, task, constraints, ...)
```

The same public gateway supports resume/pause/cancel.

`supervisor_query` exposes:

- status;
- events;
- result;
- notifications;
- resume prompt.

## 3.3 README contract

README publicly documents Supervisor tools and their lifecycle behavior.

## 3.4 Test compatibility

**REPOSITORY FACT**

Supervisor is bound into the same public-contract tests as Workflow:

- CF1 inventory;
- discovery;
- flat schemas;
- tool request models;
- server routing;
- transport gate.

In addition, dedicated tests cover:

- `test_supervisor_engine.py`;
- `test_supervisor_notifications.py`;
- `test_supervisor_resume_prompt.py`;
- `test_supervisor_service.py`;
- `test_supervisor_store.py`;
- `test_supervisor_upgrade_flow.py`;
- `test_supervisor_upgrade_local_agent.py`.

## 3.5 Architecture problem remains real

Iteration 6 showed that Supervisor's internal flow performs semantic work that belongs with Sol:

- inspect;
- plan;
- heuristic routing;
- optional local-model planning;
- decide whether external coding is needed;
- recommend next action/question.

## 3.6 Classification

**PUBLIC COMPATIBILITY HOLD; COGNITIVE ROLE DEPRECATED IN TARGET ARCHITECTURE.**

The first Sol-loop implementation should not delete Supervisor's public family.

But the future canonical architecture should stop using Supervisor as the default recovery/planning engine.

Later convergence should likely:

1. preserve read/query access to historical supervisor records;
2. stop creating new Supervisor records from normal Sol-controlled work;
3. migrate useful validation/report/notification pieces lower into Task/Run/return-loop helpers;
4. eventually deprecate `supervisor_action.start` after consumer evidence and replacement paths exist;
5. maintain historical status/result retrieval for old IDs.

This avoids breaking history while removing the second planner prospectively.

---

# 4. LocalAgent semantic orchestrator is not a public gateway

## 4.1 Public inventory absence

**REPOSITORY FACT**

There is no `local_agent` gateway in `PUBLIC_GATEWAY_INVENTORY`.

The current public surface contains no `local_agent_action` or equivalent MCP entry.

## 4.2 Remaining source dependencies

**REPOSITORY FACT**

LocalAgent code is still referenced internally by:

- dashboard data sources;
- legacy jobs/profile models;
- memory/audit helpers;
- local coding;
- Supervisor;
- server local-model health/config imports.

Dedicated tests remain for:

- local agent orchestrator;
- local model/Ollama adapter;
- command runner;
- policy integration;
- external coder integration;
- local coding integration;
- Supervisor upgrade integration.

## 4.3 Consequence

**INFERENCE**

The semantic `LocalAgentOrchestrator` can be removed from the **future control path** much more cheaply than Workflow/Supervisor can be removed from the public schema.

A first cleanup can:

- simply not call/use it from the new Sol loop;
- freeze new feature investment in its natural-language routing;
- keep shared compatibility helpers temporarily;
- progressively detach internal modules from `local_agent` enums/audit classes where useful.

No public gateway deletion is required to stop LocalAgent from being an architectural brain.

## 4.4 Classification

**BYPASS/DEPRECATE SEMANTIC ORCHESTRATOR EARLY; CLEAN INTERNAL DEPENDENCIES LATER.**

This is a high-value, low-public-compatibility-risk realignment target.

---

# 5. Reasoning Task is public schema even though runtime capability is owner-disabled

## 5.1 Public operation exists

**REPOSITORY FACT**

`task_action` includes the public operation:

```text
start_reasoning
```

Its request model fixes:

```text
task_kind = reasoning
backend_kind = soma_reasoning
```

The server refuses with `reasoning_backend_not_activated` when owner configuration disables reasoning.

When enabled, the server constructs a repository reasoning assignment/spec and calls `TaskManager.start_reasoning_task()`.

## 5.2 Public metadata presents it as an optional route

**REPOSITORY FACT**

Task metadata says:

```text
start uses durable command backend.
start_reasoning is owner-gated and read-only;
use it only for reasoning, never ordinary execution.
```

This is better than silently routing ordinary work to the provider, but the name still presents `reasoning` as a first-class Task operation.

## 5.3 Capability advertisement is activation-sensitive

**REPOSITORY FACT**

Tests verify:

- inactive Task capabilities advertise only `durable_command` / `soma_durable_run`;
- `reasoning` and `soma_reasoning` appear only after activation;
- however `start_reasoning` remains in the public operation inventory/schema.

This distinction is useful:

```text
schema supports optional route
!=
runtime route enabled
```

## 5.4 Test depth

**REPOSITORY FACT**

Reasoning Task support is backed by substantial durable-mechanics tests:

- `test_reasoning_task_integration.py`;
- `test_reasoning_task_recovery.py`;
- `test_reasoning_backend_store.py`;
- `test_reasoning_contract.py`;
- fake reasoning backend tests;
- repository reasoning runtime/backend/assignment/evidence tests;
- public gateway model/routing tests;
- canonical Task capability tests;
- Company admission/acceptance tests;
- G6 benchmark tests.

The tests prove meaningful durability properties such as:

- exact idempotent replay;
- no duplicate provider create after response loss;
- restart after Task commit before provider claim;
- durable start-attempt identity;
- ProjectScope attachment;
- bounded result/evidence references.

## 5.5 Classification

**DO NOT DELETE MECHANICS. PUBLIC NAME/ROLE SHOULD BE SUPERSEDED CAREFULLY, NOT RIPPED OUT.**

The first normal-Chat Sol-loop implementation need not remove `start_reasoning`.

Safer initial posture:

- keep runtime disabled unless explicitly owner-authorized;
- ensure the new loop has zero dependency on it;
- update future architecture docs/metadata so it is described as optional specialist delegation rather than the normal Chat agentic engine;
- later decide whether compatibility permits renaming/deprecating `start_reasoning` in favor of a neutral specialist route.

Removing the enum/schema immediately would destroy useful provider-durability tests and create unnecessary migration/public-hash churn.

---

# 6. Current public metadata contains terminology that should eventually be superseded

## 6.1 Task metadata

Current wording:

```text
start_reasoning ... use it only for reasoning
```

This can be misread as “Soma's reasoning layer.”

## 6.2 Company metadata

Current Company action wording explicitly says:

```text
reserve one reasoning attempt
```

This accurately describes current implementation but encodes the drift directly in public UX.

## 6.3 Future correction principle

**INFERENCE**

Do not falsify current runtime behavior in metadata before implementation changes.

When the architecture changes, update metadata prospectively to match the new truth.

Historical accepted descriptors/hashes should remain recorded in historical gate docs.

This track should not rewrite old schema hashes or acceptance documents.

---

# 7. Public-schema identity makes removals non-trivial

## 7.1 Repository architecture

**REPOSITORY FACT**

Soma tracks:

- public gateway inventory version;
- operation inventory;
- flat public input contracts;
- public descriptor identity/hashes;
- tool metadata;
- MCP discovery;
- transport content projections.

Tests freeze these relationships.

## 7.2 Consequence

**INFERENCE**

Removing or renaming a public gateway/operation is not a local refactor.

It affects:

- schema identity;
- operation inventory identity;
- discovery fixtures;
- metadata tests;
- external client expectations;
- README/docs;
- possibly cached connector/tool discovery.

Therefore the cleanup sequence should prefer **behavioral deprecation and bypass** before public removal.

---

# 8. Compatibility strategy: separate creation routes from historical read routes

A repeated pattern emerges for Workflow and Supervisor.

## 8.1 Historical records remain valuable

Existing durable IDs may need to remain queryable for:

- evidence;
- audit;
- old project recovery;
- regression fixtures;
- migration proof.

## 8.2 New creation can be deprecated independently

**INFERENCE**

A future convergence can distinguish:

```text
read/query old record
```

from:

```text
create new record under legacy lifecycle
```

This allows gradual retirement:

1. new Sol-loop work stops creating legacy Supervisor/Workflow objects unless explicitly requested for their narrow deterministic function;
2. query gateways remain for historical state;
3. start/create actions become deprecated later;
4. only after measured non-use can public action operations be removed.

This is safer than deleting read/write families together.

---

# 9. Workflow should keep an explicit niche during convergence

Unlike Supervisor, Workflow has a legitimate non-cognitive use case:

```text
known deterministic dependency-ordered sequence
```

Examples:

- run command A, then B if A succeeds;
- execute a reviewed validation sequence;
- deterministic batch steps with no fresh semantic judgment between them.

**INFERENCE**

The corrected architecture therefore does not require Workflow to disappear completely.

Possible long-term outcomes:

- retain a much thinner deterministic workflow capability;
- converge workflow steps onto canonical Task identities;
- remove Workflow's independent generic lifecycle authority while keeping a graph/schedule projection;
- or preserve the existing engine if its overlap is small and clearly documented.

This is a later implementation decision.

The key rule now is simply:

```text
Workflow != Sol cognitive loop.
```

---

# 10. Supervisor has a weaker long-term niche

Supervisor's distinctive public function is recovery/engineering supervision, but its current implementation includes semantic planning/routing that Sol should own.

Useful non-cognitive pieces include:

- durable recovery record;
- validation results;
- linked Runs;
- notification/report artifacts;
- resume prompt formatting;
- pause/cancel mechanics.

**INFERENCE**

Most of those can eventually project from or attach to canonical Task/Run/ControllerLoop state without preserving a Supervisor planner.

Therefore Supervisor is a stronger retirement candidate than Workflow once compatibility work is ready.

---

# 11. Return-loop/PulseSender compatibility is low-risk because it is already separate

**REPOSITORY FACT from prior iteration**

Return-loop models explicitly state:

```text
soma_sends_messages = false
controls_browser = false
send_policy = external_pulsesender_only
```

## Consequence

No public cognitive contract needs to be removed.

A future loop continuation bundle can become another input to optional delivery mechanisms without making PulseSender part of Task/loop truth.

Manual wake-up continues to work if delivery is absent.

**Classification:** KEEP OPTIONAL, NO CLEANUP BLOCKER.

---

# 12. Public reasoning support should be reframed before it is renamed

## Immediate safe correction

Architecture docs and future implementation should say:

```text
start_reasoning / soma_reasoning = legacy-compatible optional specialist-provider route
```

not:

```text
Soma's core reasoning layer
```

## Later public migration options

### Option A - keep names indefinitely as compatibility terminology

Pros:
- minimal schema churn;
- preserves tests/history.

Cons:
- misleading architecture terminology remains.

### Option B - add a new neutral specialist route, deprecate old name

Pros:
- correct future semantics;
- migration path.

Cons:
- temporarily more surface area;
- new schema/version work.

### Option C - remove reasoning Task entirely and model specialists elsewhere

Pros:
- cleanest ontology if justified.

Cons:
- throws away mature Task/provider durability integration;
- likely unnecessary.

## Leading research preference

**INFERENCE**

Option B or compatibility-preserving Option A is more plausible than deletion.

The durable provider-operation mechanics are too useful to discard merely because the old name overstates their role.

---

# 13. Local-model/Ollama code should not block the Sol loop

Local model adapters/config/health remain in source and tests.

They may still support explicit optional features or legacy UI.

**INFERENCE**

The normal-Chat Sol loop should neither initialize nor depend on them.

A later cleanup can measure whether any current non-Supervisor/non-LocalAgent consumer still requires the adapter.

This is another example where **dependency removal can be later than architectural bypass**.

---

# 14. Dashboard compatibility should consume truth, not preserve legacy authority

Dashboard code reads LocalAgent, jobs, supervisors, runs, etc.

**INFERENCE**

Dashboard visibility is not a reason to keep a deprecated orchestration authority alive.

Later dashboard evolution should:

- continue showing historical legacy records where useful;
- add ControllerLoop/Task views if implemented;
- stop treating LocalAgent/Supervisor records as the canonical current agent state.

UI/read compatibility follows authority; it should not define authority.

---

# 15. Test strategy for future cleanup

The current test suite is an asset. It should be partitioned conceptually rather than deleted wholesale.

## 15.1 Preserve mechanical provider durability tests

Keep tests proving:

- provider send ambiguity;
- idempotency;
- restart recovery;
- result/evidence linkage;
- ProjectScope containment;
- cancellation uncertainty.

If terminology changes, migrate these to optional specialist semantics.

## 15.2 Preserve historical read compatibility tests

Old Workflow/Supervisor records should remain readable through any promised compatibility horizon.

## 15.3 Change creation-route tests only when deprecation is authorized

Public discovery/inventory tests should change together with an explicit public schema/version gate, not accidentally during loop implementation.

## 15.4 Add Sol-loop tests independently

The future loop should have focused tests for:

- loop command idempotency;
- atomic Task ownership attachment;
- Task observation fingerprinting;
- stale acknowledgement;
- multiple active Tasks;
- terminal Task -> controller attention;
- uncertainty visibility;
- explicit completion;
- fresh-chat discovery;
- no dependency on reasoning/Company/Supervisor/Workflow.

This allows new architecture to prove itself without rewriting old tests prematurely.

---

# 16. Public-surface migration risk matrix

| Surface/component | Public now? | Immediate Sol-loop dependency? | Cleanup risk | Research recommendation |
|---|---:|---:|---:|---|
| `task_query/task_action start` | yes | yes | high | KEEP core |
| `task_action start_reasoning` | yes schema, runtime gated | no | medium/high | KEEP disabled/optional; reframe; later deprecate/rename if justified |
| `workflow_query/action` | yes | no | high | KEEP during first loop patch; narrow niche; later converge |
| `supervisor_query/action` | yes | no | high | KEEP compatibility initially; stop using as default planner; later retire creation path |
| LocalAgentOrchestrator | no direct public gateway | no | medium internal | BYPASS early; later detach helpers |
| reasoning backend store/runtime | indirect via Task/Company | no | medium | KEEP optional provider mechanics |
| Company `reserve_attempt` | yes when Company runtime used | no | high + frozen | DO NOT TOUCH in Sol-loop lane |
| Worker gateway | separate optional surface | no | medium | KEEP dormant |
| EvidenceSubmission/FanIn | internal/provider contracts | no | low/medium | KEEP optional |
| Return-loop/PulseSender | optional external contract | no | low | KEEP optional |

---

# 17. Historical docs/gates must remain immutable evidence

Accepted gates record what was actually implemented and tested at the time.

Examples include:

- G2 reasoning Task acceptance;
- G6 benchmark/evidence gates;
- V3-1A worker interaction gates;
- Company outcome acceptance gates;
- public schema/descriptor identity gates.

**OWNER REQUIREMENT / INFERENCE**

Do not rewrite these to pretend the architecture was always Sol-centric.

Instead create future supersession records saying:

```text
historical claim/mechanics remain true
but this interpretation/path is no longer the preferred/core architecture
```

This preserves archaeology and avoids corrupting evidence.

---

# 18. Terminology migration can happen in layers

## Layer 1 - architecture vocabulary

Immediately in new research/plans:

```text
Sol control loop
canonical action Task
optional specialist provider
subordinate worker
Work-native subagent
```

Avoid using `reasoning backend` as the core brain.

## Layer 2 - UX/metadata

Change only when implementation truth supports it.

For example, later describe `start_reasoning` as legacy/optional specialist route.

## Layer 3 - schema/enums/public operations

Rename/deprecate only with explicit migration/public-schema gates.

## Layer 4 - historical docs/data

Never rewrite semantic history merely for terminology cleanliness.

---

# 19. Smallest likely first implementation package after research

This is **not authorization or the final plan**, only a compatibility implication.

The compatibility evidence strongly favors an initial realignment package that:

- adds the lightweight ControllerLoop authority alongside existing Task;
- coordinates loop-owned Task reservation through existing TaskManager/TaskStore;
- exposes compact loop query/action operations;
- leaves Workflow/Supervisor public gateways intact;
- leaves `start_reasoning` schema intact and owner-disabled;
- leaves Company untouched/frozen;
- does not touch worker gateway, FanIn, Codex, Hermes reasoning, or PulseSender;
- does not remove LocalAgent code yet but does not route new loop work through it.

That would realign the actual control path without forcing unrelated public migrations into the same change.

Final implementation sequencing still belongs in the synthesis after one more gap check.

---

# 20. Compatibility evidence supports progressive, not destructive cleanup

The repository has accumulated multiple generations:

```text
Workflow
Supervisor
LocalAgent
canonical Task/Run
Agent/Worker optional specialist infrastructure
Company
future Sol loop
```

The clean target is not to make every historical subsystem disappear in one commit.

**INFERENCE**

A safe convergence sequence is conceptually:

```text
1. establish correct new authority
2. route new normal work through it
3. stop extending overlapping legacy authority
4. preserve query/history
5. measure remaining creation-path consumers
6. migrate mechanical helpers lower
7. deprecate old creation routes
8. remove only after compatibility evidence permits
```

This is exactly what progressive convergence was intended to achieve.

---

# 21. Iteration 9 conclusions

## REPOSITORY FACT

1. Workflow and Supervisor are still first-class public MCP gateway families.
2. Both are represented in public inventory, metadata, README, discovery, input-schema, transport, and CF1 tests.
3. Both also have dedicated behavioral/durability tests.
4. LocalAgent semantic orchestration is not itself a public gateway.
5. LocalAgent still has significant internal compatibility dependencies.
6. `task_action.start_reasoning` is public schema but runtime owner-gated/disabled by default.
7. Reasoning Tasks have strong durability/recovery/provider-ambiguity tests worth preserving.
8. Earlier accepted V3-1A architecture already called Workflow/Supervisor compatibility lifecycle managers subject to later progressive convergence.

## INFERENCE

1. The first Sol-loop implementation should not remove Workflow or Supervisor public gateways.
2. New normal-Chat work should simply stop using Supervisor/LocalAgent as semantic routers.
3. LocalAgent cognitive routing can be bypassed early because it is not a public gateway.
4. Supervisor creation is a stronger eventual retirement candidate than deterministic Workflow.
5. Workflow may retain a narrow explicit deterministic-sequence role even after convergence.
6. Reasoning provider mechanics should be preserved as optional specialist infrastructure; public terminology can be superseded gradually.
7. Public-schema removal/renaming should be a separate gate after consumer measurement.
8. Historical accepted docs should be superseded, never rewritten.

---

# 22. Remaining gaps before final synthesis

The research now has enough evidence for the architecture and most migration concerns. A final synthesis iteration should still explicitly resolve/document:

1. the exact corrected architecture diagram;
2. Chat vs Work responsibility matrix;
3. Sol vs Soma matrix;
4. native subagent vs optional external specialist matrix;
5. final component KEEP/MOVE/RENAME/OPTIONAL/DEPRECATE/REMOVE inventory;
6. exact missing capabilities;
7. exact drift timeline;
8. minimal loop contract and atomic Task seam;
9. compatibility/migration concerns;
10. implementation sequence recommendation;
11. explicit do-not-implement list;
12. historical supersession strategy;
13. remaining open questions that must stay open rather than be guessed.

That should be Iteration 10 research synthesis, not implementation.

---

# Sources inspected

## Architecture/history

- `docs/V3_1A_INTERACTIVE_WORKER_SUBSTRATE_PLAN_2026-07-30.md`
- prior realignment Iterations 1-8

## Public surface

- `soma/public_gateway_inventory.py`
- `soma/public_tool_metadata.py`
- `soma/cf1_gateway_operation_inventory.py`
- `soma/server.py`
- `README.md`

## Tests / compatibility evidence

- `tests/test_cf1_gateway_operation_inventory.py`
- `tests/test_mcp_action_discovery.py`
- `tests/test_mcp_flat_input_contract.py`
- `tests/test_tool_gateway_models.py`
- `tests/test_transport_content_text_gate.py`
- `tests/test_workflow_durability.py`
- `tests/test_workflows.py`
- `tests/test_supervisor_engine.py`
- `tests/test_supervisor_notifications.py`
- `tests/test_supervisor_resume_prompt.py`
- `tests/test_supervisor_service.py`
- `tests/test_supervisor_store.py`
- `tests/test_supervisor_upgrade_flow.py`
- `tests/test_supervisor_upgrade_local_agent.py`
- `tests/test_local_agent_orchestrator.py`
- `tests/test_local_agent_local_model.py`
- `tests/test_durable_command_runner.py`
- `tests/test_reasoning_task_integration.py`
- `tests/test_reasoning_task_recovery.py`
- `tests/test_task_interaction_gateway.py`
- `tests/test_reasoning_backend_store.py`
- `tests/test_reasoning_contract.py`
- repository test inventory used to identify related compatibility suites
