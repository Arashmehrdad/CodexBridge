# Iteration 8 - Company/Mission/Plan Interaction with the Sol-Centric Loop

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected: `26eb9adf64d454c0b5056b21ae770590405226b4`
Company status: FROZEN by owner direction

## Scope

Iterations 1-7 established the corrected core architecture:

- normal Chat becomes durably agentic by preserving a lightweight control loop around Sol;
- Work keeps its native ChatGPT agentic loop;
- canonical Task/Run remain the durable external-action authority;
- specialists are optional bounded delegation, not the default reasoning brain;
- most Agent/Worker infrastructure is reusable below or beside the Sol loop;
- the normal-Chat loop must not depend on Company, Codex, reasoning providers, workers, Workflow, Supervisor, or automatic wake-up.

Iteration 8 asks how the frozen Company/Mission/Plan architecture relates to this corrected core.

The goal is not to redesign or reactivate Company. It is to determine:

1. which Company concepts complement Sol's durable control loop;
2. which Company concepts would duplicate ChatGPT/Work planning if used indiscriminately;
3. where current Company implementation became entangled with the later reasoning-worker architecture;
4. what must eventually be reconsidered if the owner explicitly reopens a Company lane.

No Company implementation is modified or unfrozen here.

## Hard constraints

No runtime/service restart, Company activation, reasoning-provider activation, Codex use, provider generation, production config change, push, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

`PLANS.md` is authoritative for the current freeze: a generic `continue`, historical acceptance text, or existing source does not reopen Company.

An unrelated modified file, `soma/repo_patch_repair.py`, was present and left untouched.

Classification labels:

- **REPOSITORY FACT** - current source/docs/history evidence.
- **OWNER REQUIREMENT** - explicit owner direction.
- **DOCUMENTED FACT** - current official OpenAI behavior already established in earlier iterations.
- **INFERENCE** - supported architecture conclusion, not implementation authority.
- **OPEN QUESTION** - intentionally unresolved until a future owner-authorized Company review.

---

# 1. Company is frozen, and this audit does not change that

## 1.1 Current active plan

**REPOSITORY FACT**

`PLANS.md` states:

- the Autonomous Company roadmap is **FROZEN**;
- V3-1B and V3-2 implementation remain preserved historical/current repository state;
- V3-3 and later lanes are inactive;
- no Company implementation resumes without a new explicit owner instruction naming the Company lane;
- a generic `continue` cannot reopen Company;
- the owner/executive public surface remains at the accepted boundary unless separately reviewed.

## 1.2 Research consequence

**OWNER REQUIREMENT / INFERENCE**

This iteration may classify existing Company architecture and identify future correction seams, but it must not:

- change Company schema;
- change admission;
- activate Company;
- alter current Plan/WorkPackage semantics;
- reinterpret the normal-Chat realignment as permission to resume V3-3.

Any eventual Company change requires a separately authorized future lane.

---

# 2. The original Company architecture already puts ChatGPT/Cortana above Soma

## 2.1 Executive authority

**REPOSITORY FACT**

`docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md` names:

```text
Owner: Arash
Executive design authority: ChatGPT/Cortana
```

Its target relationship is:

```text
Arash
  -> Cortana
     owner companion, executive interface, explanation and escalation
  -> Soma Company Kernel
     company constitution, organisation, plans, authority, budgets,
     decisions, commitments, work packages, recovery and evidence
  -> disposable specialist workers
  -> replaceable business and production systems
```

## 2.2 Company was not originally supposed to be one giant reasoning agent

**REPOSITORY FACT**

The same architecture states:

- the end state is **not** a single long-running super-agent;
- long-lived objectives survive sequences of short worker sessions;
- one authority exists per concern;
- agent output is proposed state, not automatically company truth;
- optional providers must degrade cleanly;
- multi-agent complexity must earn its cost;
- single-agent execution remains valid/default;
- generic lifecycle authorities should decrease while canonical Task/Run coverage increases.

The hierarchical intelligence contract says even more directly:

> Soma will provide the durable organisation around intelligent agents. It will not attempt to encode agent reasoning as one enormous deterministic workflow.

## 2.3 Corrected interpretation

**INFERENCE**

The original Company destination is not inherently incompatible with the Sol-centric correction.

A cleaner reading is:

```text
Sol / ChatGPT / Cortana
    = executive judgment

Company Kernel
    = durable organisational commitments, authority, accepted plans,
      work-package identity, outcomes, evidence and continuity

canonical Task / Run
    = concrete execution

specialist workers
    = optional bounded delegates
```

The architecture drift occurred primarily in how Company work was later admitted/executed, not in the mere existence of Company/Mission/Plan records.

---

# 3. Mission is not the same thing as a normal-Chat controller loop

## 3.1 Mission semantics

**REPOSITORY FACT**

The Company model defines a `Mission` as a bounded owner objective undertaken by a Company. It carries:

- Company identity;
- mission key;
- exact ProjectScope/resource/generation;
- canonical mission contract/hash;
- accountable owner;
- acceptance authority;
- current PlanRevision;
- plan/kernel state versions.

The architecture examples include large organisational objectives such as:

- build and launch a SaaS;
- recover a production incident;
- validate a product opportunity;
- run a customer-acquisition experiment.

## 3.2 Normal-Chat loop semantics

The proposed lightweight Sol loop is intentionally smaller:

```text
objective reference
open/completed/cancelled
state version
linked canonical Tasks
last Sol-consumed Task observation fingerprints
idempotent loop commands
```

It need not have:

- Company identity;
- formal budget/authority chain;
- ProjectScope ownership at the whole-objective level;
- accepted PlanRevision;
- WorkPackages;
- OutcomeAcceptance.

## 3.3 Conclusion

**INFERENCE**

Do not collapse `ControllerLoop` and `Mission`.

A normal Chat objective may be too small or informal to justify Company semantics.

Possible future relationship:

```text
ordinary personal/engineering objective
    -> ControllerLoop only when durable continuation is useful

explicit large organisational mission
    -> Mission/Plan may exist
    -> Sol/Work still owns reasoning
    -> concrete actions remain canonical Tasks
```

A Mission may later reference or encompass controller-loop activity, but Company must remain an optional higher-order domain layer.

---

# 4. PlanRevision can be useful if it means durable accepted organisational commitment

## 4.1 Current PlanRevision is immutable accepted domain state

**REPOSITORY FACT**

`PlanRevision` contains:

- Mission identity;
- monotonic revision number;
- optional parent revision;
- canonical plan contract/hash;
- deliberation reference/hash;
- named `accepted_by_ref`;
- acceptance basis;
- controller request/hash;
- accepted timestamp.

The Company architecture treats accepted plans as durable organisational truth rather than transient reasoning text.

## 4.2 Work already has native cognitive planning

**DOCUMENTED FACT from Iterations 1/4**

ChatGPT Work already plans approaches and performs multi-step work natively.

Normal Chat/Sol also reasons and may form an internal or explicitly summarized plan between actions.

## 4.3 Required distinction

**INFERENCE - IMPORTANT**

A future Company `PlanRevision` remains justified only if it means something stronger/different than ChatGPT's working plan.

Useful distinction:

```text
ChatGPT/Work/Sol working plan
    = cognitive strategy, freely revised during reasoning

Company PlanRevision
    = explicit durable accepted organisational commitment
      that defines WorkPackage/outcome/authority relationships
```

If Company PlanRevision merely mirrors every ephemeral plan produced by Work/Sol, it duplicates the agentic layer and should not exist for that task.

## 4.4 Consequence

When Company is eventually reconsidered, the question should not be:

> How do we make Soma plan instead of Work?

It should be:

> Which plan decisions are important enough to be promoted from ChatGPT's working cognition into durable organisational truth?

This follows the existing Company principle that agent output is proposed state until an authorized transition accepts it.

---

# 5. WorkPackage is a useful route-neutral contract concept

## 5.1 Current model deliberately excludes execution/provider identity

**REPOSITORY FACT**

`normalize_work_package_contract()` rejects route-specific fields including:

- provider/model;
- profile/executable;
- argv/environment;
- session;
- Task/Run/PID/worker identities.

`WorkPackage` instead carries:

- Mission and PlanRevision;
- package key;
- route-neutral outcome ID;
- ProjectScope/resource/generation;
- canonical contract/hash;
- accountable owner and acceptance authority;
- evidence requirements.

## 5.2 Why this survives realignment

**INFERENCE**

This separation is conceptually strong:

```text
what organisational outcome is required
    !=
how/where/by whom it is executed
```

That remains useful whether execution is performed by:

- one direct durable command Task;
- several Sol-driven Tasks;
- Work-native activity plus one Soma external effect;
- an explicitly authorized specialist provider.

The route-neutral WorkPackage contract should not be discarded merely because the current admission route is provider-coupled.

---

# 6. WorkPackageAttempt -> canonical Task is also a good boundary

## 6.1 Current model

**REPOSITORY FACT**

A `WorkPackageAttempt` stores:

- exact WorkPackage/outcome identity;
- one canonical `task_id`;
- route request hash/descriptor;
- superseded-attempt relationship;
- containment evidence;
- controller request/hash.

The Company architecture therefore already separates:

```text
WorkPackage outcome intent
 -> concrete attempt route
 -> canonical Task
```

## 6.2 Corrected role

**INFERENCE**

This is reusable.

The future correction should be about **which Task route an attempt may use**, not about deleting WorkPackageAttempt.

A WorkPackageAttempt should conceptually be able to bind to an appropriate provider-neutral canonical Task route chosen by the executive/controller, rather than being synonymous with a reasoning provider.

---

# 7. Current Company admission is the main Company-specific drift seam

## 7.1 Admission request hard-wires reasoning

**REPOSITORY FACT**

`soma/company_kernel/admission.py` defines:

```text
AdmissionRequestV1.reasoning_spec: ReasoningSpecV1
```

It imports and depends on:

- reasoning spec hashes/refs;
- `REASONING_EXECUTOR`;
- `normalize_reasoning_request`;
- `TaskKind.REASONING`;
- `BackendKind.SOMA_REASONING`.

The admission function is literally named:

```text
admit_reasoning_work_package
```

It refuses when no reasoning backend is configured.

It creates a WorkPackageAttempt + ProjectScope attempt + canonical Task transactionally, but the Task is always:

```text
TaskKind.REASONING
BackendKind.SOMA_REASONING
```

and then `start_reasoning_task()` is invoked after the transaction.

## 7.2 Public gateway repeats the coupling

**REPOSITORY FACT**

`company_action reserve_attempt` explicitly checks:

```text
if not config.reasoning.enabled:
    reserve_attempt is unavailable
```

Capabilities expose:

```text
reasoning_attempt_route_enabled
```

as the availability indicator.

## 7.3 Coordinator also accepts only prepared reasoning admissions

**REPOSITORY FACT**

`soma/company_kernel/coordinator.py` defines:

```text
PreparedReasoningAdmissionV1
```

with a required `ReasoningSpecV1`, and every actual admission calls `admit_reasoning_work_package()`.

The coordinator itself is mechanically well-bounded and explicitly says it performs no semantic adjudication/provider inference, but its input route type is still reasoning-specific.

## 7.4 Conflict with the original Company laws

**REPOSITORY FACT + INFERENCE**

This implementation contradicts the preserved Company architecture's own design law:

```text
Optional providers degrade cleanly.
None may be required for the Company Kernel to function.
```

Today, the Company identity/plan/query/projection layers can exist without a provider, but the implemented attempt-admission path cannot enter ordinary work without the reasoning provider route.

That explains the earlier live boundary where `reserve_attempt` truthfully refused while reasoning was disabled.

## 7.5 Classification

**REPOSITION / FUTURE SUPERSESSION REQUIRED, COMPANY STILL FROZEN.**

The admission transaction mechanics are useful.

The route-specific assumption is the problem.

A future owner-authorized Company review should make attempt admission provider-neutral, allowing the selected concrete Task route to be appropriate to the WorkPackage instead of hard-wiring reasoning.

No such change is authorized now.

---

# 8. Company admission already demonstrates the transaction pattern needed by the Sol loop

## 8.1 Existing atomicity

**REPOSITORY FACT**

Company admission currently performs in one SQLite transaction:

```text
ProjectScope.reserve_task_attempt
TaskStore.reserve_task_in_connection
ProjectScope.attach_task
insert WorkPackageAttempt
```

External/provider Task start happens only after the transaction commits.

## 8.2 Relevance to the normal-Chat loop

**INFERENCE**

Although Company admission's route is semantically wrong for the normal Sol loop, its transaction architecture independently validates the Iteration 7 design:

```text
higher-level owner record
+ ProjectScope membership
+ canonical Task reservation
```

can be committed atomically before effect launch.

The future lightweight loop can reuse the same pattern without importing Company concepts.

This is useful infrastructure evidence, not Company activation.

---

# 9. Company projections are strongly aligned with lifecycle convergence

## 9.1 No duplicate WorkPackage lifecycle column

**REPOSITORY FACT**

`soma/company_kernel/projections.py` explicitly states:

> The Company Kernel deliberately stores no WorkPackage lifecycle column.

It derives WorkPackage/attempt state from:

- immutable Company facts;
- ProjectScope;
- canonical Task state;
- backend publication evidence;
- AcceptanceCommit.

## 9.2 Why this is good

**INFERENCE**

This follows exactly the architecture we want elsewhere:

```text
domain identity/commitment
 + canonical execution truth
 -> projection
```

rather than copying generic execution lifecycle into every higher-level domain.

The normal-Chat loop's proposed Task-observation fingerprint is philosophically similar: derive controller-visible state from canonical Task truth instead of copying execution status into another agent lifecycle.

## 9.3 Classification

**KEEP conceptually.**

If Company is later reopened, projection-based lifecycle convergence is a strong part of the existing implementation and should not be undone.

---

# 10. OutcomeAcceptance is conceptually separate from process success

## 10.1 Existing distinction

**REPOSITORY FACT**

The Company architecture distinguishes:

```text
TaskAdmission
ResultPublication
OutcomeAcceptance
```

A backend/task succeeding does not automatically accept the substantive Company outcome.

`AcceptanceCommit` binds exact:

- Company/Mission/WorkPackage/outcome/attempt;
- Task/backend identity;
- publication hash/source hash;
- named acceptance authority;
- acceptance basis.

## 10.2 Fit with Sol-centric reasoning

**INFERENCE**

This is a useful distinction for large explicit organisational work.

Sol/Work or another named acceptance authority may judge substantive correctness after Soma proves the mechanical facts.

That matches the realigned principle:

```text
Soma proves execution/evidence identity.
Sol / named intelligent authority judges meaning/correctness.
```

OutcomeAcceptance should therefore not be removed simply because `soma_reasoning` appears in its current backend union.

---

# 11. AcceptanceCommit's current backend enum is a compatibility issue, not a conceptual reason to discard acceptance

## 11.1 Current schema

**REPOSITORY FACT**

`AcceptanceCommit.backend_kind` currently permits exactly:

```text
soma_durable_run
soma_reasoning
```

and acceptance has separate durable-run and reasoning-publication validation branches.

## 11.2 Future concern

**INFERENCE**

If `SOMA_REASONING` is later renamed/repositioned as optional specialist infrastructure, Company acceptance compatibility must be handled carefully.

Historical AcceptanceCommits and their content hashes are immutable evidence. They must not be rewritten just to modernize terminology.

Possible future strategy:

- retain legacy enum/value for historical rows;
- add a new provider-neutral specialist/backend category prospectively if needed;
- preserve old hash contracts;
- use migration/projection compatibility rather than mutating history.

This belongs to a future Company/reasoning cleanup plan, not this research implementation.

---

# 12. Reconciliation is currently mechanical and should stay that way

## 12.1 Current behavior

**REPOSITORY FACT**

`reconcile_one` explicitly says it is:

- not a scheduler;
- not a Task/Run dispatcher;
- not a plan/package/acceptance mutation engine.

It records bounded receipts for:

```text
owner_turn -> no_op
package_completion -> acceptance_candidate_ready
```

It validates exact ProjectScope, Mission version, current WorkPackage projection, and publication hash.

## 12.2 Corrected role

**INFERENCE**

This is compatible with Sol-centric architecture as long as it remains a mechanical receipt/projection boundary.

It must not evolve into:

```text
package completes
 -> reconciliation semantically chooses next plan/action/provider
```

without explicit executive reasoning.

A package-completion receipt can tell Sol/Work that a decision boundary exists. Sol/Work decides what that means.

---

# 13. Company and the lightweight normal-Chat loop should remain layered, not merged

## 13.1 Minimal normal path

```text
Normal Chat / Sol
 -> optional ControllerLoop
 -> canonical Task
 -> Run/external effect
 -> observation
 -> Sol
```

## 13.2 Optional large organisational path

```text
Owner
 -> Sol / Work executive reasoning
 -> explicit Mission
 -> accepted durable PlanRevision when justified
 -> WorkPackage(s)
 -> concrete WorkPackageAttempt(s)
 -> canonical Task(s)
 -> result/evidence
 -> named substantive acceptance
 -> executive reasoning continues
```

## 13.3 Important rule

**INFERENCE**

Company is **not** a required parent of every ControllerLoop.

ControllerLoop is **not** a replacement for Mission/Plan when genuine durable organisational commitment is needed.

They solve different levels of state.

---

# 14. ChatGPT Work changes the future Company design question

## 14.1 Historical timing

The Company architecture predates the current August 2026 Work product capabilities established in Iteration 1.

## 14.2 Current Work capability

**DOCUMENTED FACT from prior iterations**

Work now supplies:

- long multi-step agentic work;
- planning;
- tool/app use;
- native subagent orchestration;
- long-running project behavior.

## 14.3 Future Company consequence

**INFERENCE - IMPORTANT**

Before any future V3-3+ Company lane is reopened, the Company architecture should be re-evaluated against **current Work**, not against the older assumption that Soma needs to provide all executive multi-step cognition itself.

Potential future corrected relationship:

```text
Work / Sol
    = executive cognition and adaptive multi-step reasoning

Company Kernel
    = durable organisation, authority, commitments, promoted plans,
      WorkPackage/outcome identity, acceptance and external continuity
```

That could substantially simplify V3-3/V3-4 compared with the historical design.

But this is future research authority only. Company remains frozen.

---

# 15. Work planning and Company PlanRevision can coexist only with a promotion boundary

## Bad architecture

```text
Work changes its working plan
 -> Soma automatically creates PlanRevision
 -> every internal cognitive adjustment becomes Company truth
```

This would duplicate Work's agentic layer and produce excessive durable state.

## Better conceptual boundary

```text
Work/Sol reasons and adapts freely
 -> when a plan/commitment materially affects organisational authority,
    WorkPackages, budgets, acceptance, or long-lived commitments
 -> explicitly promote/accept a durable Company PlanRevision
```

**INFERENCE**

This mirrors the existing Company principle that agent outputs are proposals until mechanically accepted through the proper authority.

The distinction should be tested only if Company is reopened.

---

# 16. The future fully autonomous Company continuity question remains open

## 16.1 Why this is separate from normal Chat

The owner has accepted manual wake-up as the baseline for the **normal-Chat Sol loop**.

A future Company objective, however, historically aims to continue operational work for long periods with limited owner intervention.

## 16.2 Open question

**OPEN QUESTION**

If Company is ever reopened, what ChatGPT surface owns long-horizon executive reasoning while the owner/normal Chat is absent?

Possible future candidates to research then include:

- ChatGPT Work's native long-running/agentic capabilities;
- scheduled/recurring Work mechanisms where officially appropriate;
- an explicitly owner-authorized external reasoning route if a product gap remains.

## 16.3 Hard boundary now

Do **not** answer this by restoring the current generic reasoning-worker architecture into the normal Chat core.

The future Company autonomy problem is separate and may have a different product-surface solution.

No current official integration claim is made here about Soma programmatically waking/controlling Work.

---

# 17. Company concepts that complement the Sol loop

Provisional classification:

| Company concept | Fit with Sol-centric architecture | Role |
|---|---|---|
| Company identity | KEEP if Company reopened | Long-lived organizational identity |
| Mission | KEEP / optional higher-order layer | Formal bounded owner objective |
| PlanRevision | KEEP with strict promotion boundary | Durable accepted organizational commitment, not every cognitive plan |
| WorkPackage | KEEP | Route-neutral outcome contract |
| WorkPackageAttempt | KEEP | Exact concrete attempt tied to canonical Task |
| ProjectScope binding | KEEP | Exact resource/generation authority |
| AcceptanceCommit | KEEP conceptually | Separate process success from substantive accepted outcome |
| Company projections | KEEP | Derive lifecycle from canonical Task/backend truth |
| Reconciliation receipt | KEEP if mechanical | Decision-boundary receipt, not semantic planner |
| Reasoning-only admission | REPOSITION / SUPERSEDE LATER | Current provider coupling contradicts optional-provider law |
| PreparedReasoningAdmission coordinator | REPOSITION LATER | Mechanical coordinator good; route type too narrow |
| Company-native worker reasoning hierarchy | RE-EVALUATE against Work | May duplicate modern Work cognition |
| Company required for normal Chat loop | REJECT | Too heavy and wrong layer |

---

# 18. What must not happen during Sol-loop implementation

Even if Company code already exists, the future normal-Chat loop implementation must not:

1. depend on Company schema being installed;
2. create Company/Mission automatically for normal goals;
3. create PlanRevision for every Sol plan;
4. require WorkPackage admission before a normal Task;
5. activate `company_kernel.enabled`;
6. activate reasoning to make Company admission work;
7. alter Company public gateways as a side effect;
8. migrate AcceptanceCommit semantics casually;
9. reopen V3-3 or later lanes;
10. use Company as a shortcut for the three-table lightweight loop.

This separation is essential to keep the add-on lightweight.

---

# 19. What a future Company realignment would probably need to research

Only after explicit owner reopening:

1. Replace reasoning-only `reserve_attempt` with provider-neutral attempt routing.
2. Decide whether one WorkPackageAttempt can map to direct durable command, optional specialist, or another Task kind without weakening outcome identity.
3. Generalize coordinator inputs from `PreparedReasoningAdmissionV1` to route-neutral prepared attempts.
4. Preserve dependency proof and concurrency mechanics.
5. Preserve WorkPackage route-neutral identity.
6. Preserve historical reasoning-backed AcceptanceCommits/hashes.
7. Generalize prospective OutcomeAcceptance backend validation without rewriting history.
8. Re-evaluate V3-3+ cognitive/executive behavior against ChatGPT Work.
9. Decide what Company PlanRevision truly promotes beyond Work's native working plan.
10. Ensure Company remains optional relative to ordinary Sol-loop use.

This is a future research list, not an implementation queue.

---

# 20. Historical interpretation correction

The previous implementation sequence effectively moved toward:

```text
Mission / Plan / WorkPackage
 -> reasoning-provider admission
 -> reasoning Task
 -> provider output
 -> OutcomeAcceptance
```

That made an optional provider look structurally central.

The original Company documents support a cleaner interpretation:

```text
Sol / ChatGPT / Cortana executive judgment
 -> durable Mission / promoted Plan / WorkPackage when justified
 -> provider-neutral canonical Task/execution route
 -> evidence
 -> named executive/substantive acceptance
```

**INFERENCE**

The second shape better matches both:

- the original Company design laws;
- the current Sol-centric realignment.

No Company code is changed now.

---

# 21. Relationship to Work and normal Chat matrix

| Concern | Normal Chat | Work | Company Kernel |
|---|---|---|---|
| Immediate semantic reasoning | Sol | Work/Sol native | none |
| Multi-step cognitive control | lightweight Sol loop only when needed | native Work loop | none by default |
| Working/adaptive plan | Sol cognition | Work native plan | not canonical Company truth |
| Durable organizational plan | usually unnecessary | may propose/promote | PlanRevision when explicitly accepted |
| User goal continuity | ControllerLoop if useful | Work native + external Soma truth | Mission only for formal Company objective |
| Concrete action | canonical Task | canonical Task | WorkPackageAttempt points to Task |
| External execution | Soma Run/tools | Soma Run/tools | derived through Task |
| Result/evidence | Sol interprets | Work interprets | acceptance may bind exact publication |
| Substantive completion | Sol declares loop complete | Work/main controller | named AcceptanceCommit for Company outcome |
| Specialist delegation | optional | native/optional | optional, must not be structurally required |

---

# 22. Main finding

**INFERENCE**

Company/Mission/Plan should not be deleted from the architecture merely because the recent implementation drifted toward reasoning workers.

The durable Company domain can still be useful for **formal long-horizon organizational truth**.

But it must remain above, and separate from, ChatGPT's cognitive layer.

The exact current defect is narrower:

```text
Company attempt admission is reasoning-provider-specific.
```

That should eventually be superseded by provider-neutral Task routing if/when Company is explicitly reopened.

The normal-Chat Sol loop should proceed independently and must not wait for or modify that frozen Company work.

---

# 23. Iteration 8 conclusions

## REPOSITORY FACT

1. `PLANS.md` explicitly freezes Company.
2. Original Company docs name ChatGPT/Cortana as executive design authority.
3. Original Company laws require optional providers to degrade cleanly and multi-agent complexity to earn its cost.
4. Company WorkPackage contracts are deliberately route-neutral.
5. WorkPackageAttempts already point to canonical Tasks.
6. Company projections derive lifecycle from Task/backend truth instead of storing duplicate WorkPackage lifecycle.
7. Current Company attempt admission requires `ReasoningSpecV1`, `TaskKind.REASONING`, `SOMA_REASONING`, and an enabled reasoning backend.
8. Public `reserve_attempt` refuses while reasoning is disabled.
9. The bounded coordinator accepts only prepared reasoning admissions.
10. Reconciliation remains receipt-only/mechanical and does not schedule or semantically decide next work.

## OWNER REQUIREMENT

1. Company remains frozen.
2. Sol/ChatGPT remains the reasoning authority.
3. Work already has native agentic reasoning and must not receive a duplicate Soma cognitive loop.
4. Normal Chat loop must be lightweight and independent of Company.

## INFERENCE

1. Company durable domain concepts are mostly compatible with Sol-centric architecture.
2. Mission/Plan must remain optional higher-order structures for formal organizational work.
3. Company PlanRevision should represent promoted/accepted durable commitment, not mirror ChatGPT's ephemeral working plan.
4. Current reasoning-only admission is the main Company-specific drift seam.
5. Future Company admission should likely become provider-neutral over canonical Task routes, but only after explicit owner reopening.
6. Current Work capabilities should be re-researched before any future V3-3+ cognitive/executive implementation.
7. Company projections and OutcomeAcceptance separation are valuable and should be preserved conceptually.

---

# 24. Next iteration

Iteration 9 should audit the **legacy/public-surface overlap and compatibility cost** before final synthesis:

- Workflow public gateway and current consumers/tests;
- Supervisor public gateway and current consumers/tests;
- LocalAgent public surfaces;
- reasoning Task public operations and acceptance tests;
- current Company public references to reasoning;
- which legacy paths can be deprecated without breaking accepted compatibility;
- which historical terms should be superseded instead of renamed in place;
- what can remain dormant indefinitely versus what must be cleaned to prevent future Sol-loop drift.

The objective is to gather enough migration/compatibility evidence for a final research synthesis, not to perform retirement.

---

# Sources inspected

## Current active/frozen planning

- `PLANS.md`

## Company architecture

- `docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md`
- `docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`

## Company implementation

- `soma/company_kernel/models.py`
- `soma/company_kernel/store.py`
- `soma/company_kernel/bootstrap.py`
- `soma/company_kernel/admission.py`
- `soma/company_kernel/coordinator.py`
- `soma/company_kernel/projections.py`
- `soma/company_kernel/reconciliation.py`
- `soma/company_kernel/gateway.py`
- `soma/company_kernel/acceptance.py` (reasoning/durable acceptance references inspected through source search and prior iterations)

## Prior realignment research

- Iterations 1-7 under `docs/sol-agentic-loop-realignment-research/`
