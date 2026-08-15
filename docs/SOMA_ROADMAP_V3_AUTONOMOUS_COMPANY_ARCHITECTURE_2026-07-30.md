# SOMA-V3-ARCH-1 — Autonomous Company Architecture

**Date:** 2026-07-30  
**Status:** preserved owner-accepted Company architecture; implementation progression is FROZEN by the 2026-08-15 owner correction in `PLANS.md`. Historical implementation evidence does not authorise a later Company lane.
**Decision level:** C — foundational company authority, autonomy, safety and product-direction boundary.  
**Owner:** Arash.  
**Executive design authority:** ChatGPT/Cortana, subject to owner approval and the review process below.  
**Related accepted foundations:** [`Soma_Architecture_Reevaluation_Findings_2026-07-26.md`](Soma_Architecture_Reevaluation_Findings_2026-07-26.md), [`SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md`](SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md), [`SCOPE_FOUNDATION_1_PRODUCTION_LANE_PROPOSAL_2026-07-27.md`](SCOPE_FOUNDATION_1_PRODUCTION_LANE_PROPOSAL_2026-07-27.md), [`task1-canonical-task-plane-evidence.md`](task1-canonical-task-plane-evidence.md), [`pilot-acp-1-decision-2026-07-26.md`](pilot-acp-1-decision-2026-07-26.md), [`SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md`](SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md).  
**Research basis:** five iterative reference-design rounds covering multi-agent companies, dynamic teams, long-horizon benchmarks, live autonomous-company projects, and mature coordination systems.

## 1. Decision

Soma V3 will target an **owner-controlled, operationally autonomous company operating system**.

The end state is not a larger agent framework, a single long-running super-agent, or a collection of disconnected assistants. It is a durable company kernel that can receive one owner objective, form the smallest useful temporary organisation, plan and execute work through short interactive worker sessions, coordinate departments, preserve decisions and commitments, operate business systems, expose a live company dashboard, and interact with the owner through Cortana.

The target relationship is:

```text
Arash
  ↓
Cortana
owner companion, executive interface, explanation and escalation
  ↓
Soma Company Kernel
company constitution, organisation, plans, authority, budgets,
decisions, commitments, work packages, recovery and evidence
  ↓
Disposable specialist workers
Claude Code, Codex, Hermes and future role-specific workers
  ↓
Replaceable business and production systems
CRM, finance, billing, analytics, workspace, creative and live interaction
```

Soma remains the canonical authority. External systems retain authority only for their specialist records. Workers reason, propose and execute bounded assignments; they do not become the durable company.

[`SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`](SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md) is authoritative for organisational identity, delegated judgment, accountable ownership, mandates, message semantics, resource capability, technical supervision, revocation, and substantive acceptance.

## 2. North star

The owner should be able to say:

> Build, launch and operate a useful SaaS product within these constraints.

Cortana and Soma should then be able to:

1. clarify the objective, constraints, risk tolerance, budget and success criteria;
2. determine which capabilities and departments are genuinely required;
3. form the smallest sufficient temporary organisation;
4. create one canonical company charter and plan;
5. assign bounded authority, budgets and responsibilities;
6. coordinate structured cross-department requests, challenges, reviews and decisions;
7. execute through short, interactive, recoverable work packages;
8. escalate only genuine owner decisions;
9. preserve every accepted decision, commitment, result and important dissent;
10. operate customer, financial, creative and communication systems through safe replaceable boundaries;
11. measure product, company and worker performance;
12. dissolve temporary organisational structures without losing company knowledge;
13. present the whole company through a coherent dashboard and Cortana companion.

The final product should feel like a real organisation operating under one owner, not like several chatbots submitting isolated essays.

## 3. Meaning of “fully autonomous”

“Fully autonomous” does **not** mean legally ownerless, unconstrained, or dependent on one agent running continuously.

The accepted meaning is:

> **Operationally autonomous, owner-governed, continuously inspectable and interruptible.**

The company may continue routine work without requesting approval after every small action when it remains inside accepted authority, quality, cost, risk and side-effect boundaries. The owner retains final authority over company direction, high-impact expenditure, legal commitments, exceptional risk and irreversible actions.

The company may run for months. No individual agent session should.

## 4. Governing design laws

### 4.1 Continuous company, discontinuous agents

Long-lived objectives are executed through a sequence of short-lived worker sessions. Canonical company state survives the destruction of every worker process and conversation.

### 4.2 Interactive chunk-by-chunk execution

Every work package ends at an explicit review boundary:

```text
accept
revise
retry through a different route
replan
escalate
stop
```

The executive layer communicates with workers during the bounded package when clarification or steering is needed. V3 must not convert autonomy into one enormous unattended prompt.

### 4.3 One authority per concern

Soma owns company identity, organisational intent, plans, authority, decisions, commitments, work-package contracts and durable continuity. Existing Soma authorities retain project scope, tasks, runs, evidence and recovery. External systems own only their specialist records. Presentation systems remain projections.

### 4.4 The smallest sufficient organisation

A department exists only when a distinct authority boundary, specialist capability, independent judgment, sustained workload or meaningful parallelism justifies its coordination cost.

### 4.5 Agent output is proposed state

Conversation, analysis, generated documents and worker claims do not become company truth automatically. Terminology remains explicit:

- **TaskAdmission** means a controller request was durably admitted to the canonical task plane; the existing `TaskState.ACCEPTED` is this admission state, not deliverable approval.
- **ResultPublication** means an execution authority published an exact result and hash.
- **OutcomeAcceptance** means the executive selected one exact published result for a WorkPackage outcome through an immutable AcceptanceCommit.
- **CharterRatification** means the owner or delegated constitutional authority accepted a CompanyCharter or revision.

Only an authorised transition in the correct authority creates a canonical decision, commitment, deliverable, mutation, or accepted outcome.

### 4.6 Narrow capabilities, internal routing

Workers receive a small role-specific intent surface. They do not see or trial Soma's full public operation inventory. Soma selects the backend, performs preflight, applies approved fallback and prevents equivalent repeated failures.

### 4.7 Reasoning is separated from powerful writes

Workers propose external mutations. Soma evaluates policy, authority, cost, scope and idempotency, then a narrow executor performs the approved action with scoped credentials.

### 4.8 Optional providers degrade cleanly

Higgsfield, Tavus/PAL, Buzz, AgentTeams, a CRM, an ERP, premium models and other providers may improve the company. None may be required for the Company Kernel to function.

### 4.9 Multi-agent complexity must earn its cost

Every multi-agent configuration is compared with a simpler executive-plus-tools baseline. More agents are accepted only when they improve outcome quality, independence, reliability, speed or parallelism enough to justify added cost and coordination.

### 4.10 Company learning is promoted, not improvised

Production experience may propose a new skill, policy, routing rule, adapter, model or workflow. Changed behaviour becomes active only after evaluation and authorised promotion. Live agents do not rewrite their own authority or permanent behaviour.

### 4.11 Progressive lifecycle convergence

V3 does not pause for a wholesale consolidation of every existing lifecycle authority, and it does not preserve generic lifecycle duplication indefinitely.

Whenever a V3 lane touches an existing lifecycle surface, that lane must:

1. identify every authority involved;
2. distinguish generic execution state from irreducible domain state;
3. move or project generic work ownership, waiting, cancellation, retry, recovery, result and adjudication semantics into the canonical task/run authority;
4. preserve domain-specific facts in their existing domain authority;
5. name any temporary compatibility bridge, its canonical side and its retirement condition;
6. close with no unexplained increase in canonical lifecycle authority.

The intended direction is:

```text
generic lifecycle authorities decrease
canonical task/run coverage increases
domain-specific records remain explicit
```

A broad abstract cleanup lane is rejected. So is using compatibility as a reason to make duplicate generic authorities permanent.

### 4.12 Hierarchical intelligence

Authorities define purpose, scope, constraints, delegated authority, success, escalation, and reporting boundaries. Capable child agents choose methods and escalate exceptions.

### 4.13 Stable authority and adaptive collaboration

Authority remains durable and typed while collaboration may form task-specific peer, specialist, and temporary-subagent relationships. Single-agent execution remains the default.

### 4.14 Distinct identities and authorities

Role, Agent identity, Assignment, Session, and Execution remain separate. Logical direction, substantive acceptance, technical supervision, and concrete resource capability are linked but non-interchangeable.

### 4.15 Accountable ownership and mandates

Every active work item has exactly one accountable owner; transfer is atomic. Delegation uses immutable, content-addressed, versioned mandates constrained by the issuer’s delegable authority and concrete grants.

### 4.16 Revocation and acceptance

Revocation and cancellation stop new authorised actions from one durable transition without pretending existing activity has stopped. Soma proves procedural and operational prerequisites; named acceptance authorities judge substantive correctness.

## 5. Evidence classes

Every major V3 decision should identify its evidence class:

```text
REPO-VERIFIED
Confirmed against Soma's current implementation and durable state.

EXTERNALLY-VERIFIED
Confirmed from official documentation, research, source repositories or direct pilots.

PROPOSED
A design inference requiring a bounded implementation or compatibility spike.
```

This document contains accepted product direction and proposed implementation architecture. It does not pretend that the Company Kernel has already been implemented.

## 6. Authority and state planes

V3 separates five planes. They may interact, but they must not become competing truths.

### 6.1 Constitution plane

Versioned, owner-readable and reviewable company configuration:

- mission and strategic principles;
- company and department templates;
- role definitions;
- policies and prohibitions;
- authority and escalation rules;
- budget policy;
- playbooks and standard operating procedures;
- role capability packages;
- evaluation criteria;
- promoted skills and routing policies.

This plane is declarative and versioned. Agents may propose changes. Authorised promotion creates a new immutable accepted version.

### 6.2 Operational authority plane

Transactional Soma-owned state:

- active company and mission identity;
- organisation specifications and observed conditions;
- role assignments;
- plan revisions;
- work-package contracts;
- canonical tasks and run references;
- proposals, challenges, dependencies and decisions;
- budgets and consumption reservations;
- commitments and deliverables;
- owner escalations;
- external mutation intent and confirmation;
- recovery and reconciliation state.

This is the live company authority.

### 6.3 Specialist system-of-record plane

Replaceable external or specialised systems own records for their domains:

- CRM: contacts, companies, leads, deals and customer activity;
- accounting/ERP: ledgers, invoices, expenses, suppliers and statutory records;
- billing: payment and subscription lifecycle;
- support: tickets and service history;
- product analytics: raw events, cohorts and experiments;
- creative providers: generated media and provider job state;
- communication providers: calls, messages and channel-specific delivery state.

Soma stores exact bindings, important cross-system commitments, health, provenance and confirmed outcomes. It does not duplicate entire external databases.

### 6.4 Collaboration plane

Rooms, messages, meetings, presence and working artifacts. Buzz, AgentTeams, Matrix or another provider may implement this plane.

The collaboration plane helps people and agents think together. It is not the canonical plan, decision system or task authority.

### 6.5 Projection plane

The company dashboard, notifications and Cortana views are rebuildable projections of canonical state. Deleting a projection must not delete the company.

## 7. Core domain model

The architecture defines conceptual objects and invariants, not fixed implementation files or schemas.

### 7.1 Company and mission objects

#### Company

A durable operating identity owned by Arash. It contains the accepted constitution reference, business-system bindings and long-lived company context.

A Company is not automatically a legal entity. Legal identity, if present, is an exact external reference with explicit jurisdiction and responsibility.

#### Mission

A bounded owner objective undertaken by the Company. Examples include:

- validate a product opportunity;
- build and launch a SaaS;
- recover a production incident;
- conduct a pricing review;
- run a customer-acquisition experiment.

A Mission owns its charter, constraints, success criteria, budget envelope and Organisation Instance.

#### Product

A durable business or deliverable identity that may span multiple missions. Product lifecycle must not be confused with task lifecycle.

#### Objective and KPI

An Objective describes the intended outcome. A KPI measures progress or result. A KPI never grants permission to violate process constraints.

Every objective must contain both outcome targets and process constraints.

### 7.2 Organisational objects

#### OrganisationInstance

The temporary organisation formed for one mission. It has a desired specification, observed status, active conditions and lifecycle.

#### Department

An authority and collaboration grouping of roles. Departments are created dynamically when justified; they are not a mandatory fixed corporate roster.

#### Role

The responsibility and authority position that must exist, independent of which model or runtime occupies it.

Examples:

- Product Lead;
- Engineering Lead;
- Design Reviewer;
- Go-to-Market Analyst;
- Customer Success Representative.

#### Talent

The skills, procedures, domain knowledge, evaluation history and specialist behaviour attached to a role assignment.

#### Vessel

The execution configuration:

- model;
- harness;
- context policy;
- capability manifest;
- environment;
- timeout and retry policy;
- cost limits;
- verification requirements.

#### Assignment

One Talent and one Vessel occupying one Role for a bounded mission or work period. Replacing a model changes the Assignment or Vessel, not the Role or accepted company plan.

#### Session

One short execution episode. Sessions are disposable and may not own canonical company continuity.

### 7.3 Planning and collaboration objects

#### CompanyCharter

The accepted mission contract containing:

- objective;
- scope;
- assumptions;
- constraints;
- budget;
- success and stop criteria;
- owner authority boundaries;
- permitted external effects;
- required assurance.

#### PlanRevision

One immutable accepted revision of the company plan. Every worker result states which plan revision it addresses.

Only one PlanRevision is current for one mission. Earlier revisions remain preserved.

#### WorkPackage

A short executive contract for one coherent outcome. It includes:

- expected result;
- accepted inputs;
- plan revision;
- accountable role;
- permitted capabilities;
- dependencies;
- time, token and cash ceilings;
- external-side-effect classification;
- required evidence;
- acceptance criteria;
- escalation and stop conditions.

A WorkPackage does **not** create a second execution lifecycle. It links to the existing canonical task and run authorities for execution.

#### Proposal

A candidate change, recommendation or output submitted for consideration.

#### Challenge

A structured objection that identifies the disputed claim, evidence, risk or dependency. Challenges remain attached to the final decision even when rejected.

#### DependencyRequest

A bounded request from one role or department to another. It does not transfer ownership of the mission or canonical plan.

#### Decision

An authorised selection among alternatives. It records the decision owner, evidence, rejected alternatives, dissent, affected plan revision and supersession.

#### Commitment

A promise or obligation created by the company, especially toward customers, suppliers, regulators, employees or the owner. Commitments receive stronger lifecycle and closure controls than ordinary tasks.

#### Deliverable and DeliverableGraph

Deliverables are related outputs whose consistency may need verification across documents, code, designs, calculations, contracts and customer material.

The graph records which source facts, calculations, requirements and decisions support each output. Acceptance applies to the consistent set, not merely to isolated files.

### 7.4 Governance objects

#### Policy

An executable rule governing actions, resources, conditions and exceptions.

#### AuthorityGrant

A bounded delegation from a parent authority to a role or assignment. A child may not delegate more authority, budget or scope than the parent owns.

#### BudgetEnvelope

A bounded cash, token, time or provider-credit allocation with reservation, consumption, return and escalation semantics.

#### EscalationRule

Defines when the executive layer must stop and ask the owner or another authority.

#### Evaluation and Scorecard

Records outcome quality, reliability, cost, route selection, correction behaviour, policy compliance and repeated performance for a WorkerConfiguration, role, playbook or organisational topology.

### 7.5 External-system objects

#### BusinessSystemBinding

An exact, project- and company-scoped binding to an external system, account, workspace or tenant.

#### ExternalRecordReference

An opaque reference to a specialist record, preserving provider, object type, stable identifier, scope and provenance.

#### MutationProposal

A worker-produced request for a consequential external action. It includes:

- principal and accountable assignment;
- requested action;
- target resource;
- intended effect;
- expected cost;
- evidence;
- policy and risk classification;
- idempotency identity;
- rollback, compensation or manual-remedy plan.

#### MutationOutboxRecord

The durable approved instruction committed before external execution.

#### MutationConfirmation

The exact external provider result, identity and observed effect. A proposal is not treated as completed merely because an API request was sent.

## 8. Relationship to existing Soma authorities

V3 extends Soma; it does not replace proven foundations.

### ProjectScope

ProjectScope remains the authority for repository and project isolation. A Company or Mission may bind one or more exact projects. The first V3 spike should use one existing project scope rather than inventing cross-project execution prematurely.

### Canonical task plane

The task plane remains the sole canonical execution lifecycle. Company WorkPackages create or bind canonical tasks; they do not duplicate task state.

### RunStore and execution providers

Run attempts, process identity, cancellation, recovery, results and evidence remain with existing Soma execution authorities.

### Interactive worker execution boundary

The accepted provider pilot demonstrated stable native provider session identities, explicit resume and context retention, structured usage evidence, and native steering for Claude. It selected thin Soma-owned adapters over provider-native protocols; it did not implement the production boundary.

V3 adds interactive provider sessions as bindings beneath the existing Task → Run authority. Provider sessions may own opaque native session identity and protocol cursors. They must not own a second queued/running/waiting/cancelled/terminal lifecycle, leases, result publication or recovery authority.

The first implementation outcome must add crash-safe session binding, steering and supplied input, non-terminal controller waiting, explicit-ID recovery, child-process identity, cancellation evidence and raw provider usage while preserving the canonical task/run owners.

### Progressive convergence with existing authorities

Workflows and supervisors are legacy **generic lifecycle managers**, not business domains. They remain readable and operational for compatibility, but their overlapping planning, step execution, waiting, cancellation, retry, recovery, result, and publication responsibilities must be projected into canonical tasks/runs or retired when V3-1B, V3-3, or another lane first touches that territory. Compatibility does not grant permanent authority.

SSH activation, Trading Lab, memory, research, and future business systems contain irreducible domain facts. When a V3 lane touches them, it consolidates only generic work semantics into the task/run plane and leaves domain facts where they belong.

Examples:

- task state owns whether broker reconciliation work is waiting, running or complete; Trading Lab owns order submission and broker-confirmation facts;
- task state owns whether SSH work is running or failed; SSH activation owns activation and rollback facts;
- task state owns worker waiting, cancellation and recovery; a provider-session binding owns only native session identity and interaction-delivery evidence;
- workflow and supervisor records may remain compatibility projections, but they may not launch new V3 work through an independent generic lifecycle once the corresponding V3 territory is active.

No V3 lane may introduce a new lifecycle manager merely to wrap an existing one.

### Memory and research

Canonical memory preserves company decisions, preferences, lessons and continuity. The research platform preserves source-backed investigation. Neither system becomes a task or company-lifecycle authority.

### Repository and infrastructure providers

Existing SSH, Docker, Cloudflare, PowerShell and repository capabilities remain internal execution backends. Company workers should interact through role-level intents rather than choosing among raw providers.

## 9. Company lifecycle

### 9.1 Objective intake

Cortana receives the owner objective and establishes what is known, uncertain and prohibited. Missing details are resolved only when they materially affect the charter.

### 9.2 Charter formation

The CompanyCharter is proposed and accepted. It becomes the parent boundary for all downstream authority, budgets and work.

### 9.3 Capability analysis

The Organisation Compiler identifies the capabilities required to satisfy the charter. It does not begin from a fixed department list.

### 9.4 Organisation formation

Candidate roles and workers are selected using prior performance, explicit capability, cost and—when useful—a cheap diagnostic assignment.

The smallest sufficient OrganisationInstance is activated.

### 9.5 Plan acceptance

Departments may provide independent input, but one PlanRevision becomes canonical through executive acceptance.

### 9.6 Interactive execution

The executive layer repeatedly creates one bounded WorkPackage, delegates it, communicates with the worker, validates the result and chooses the next transition.

### 9.7 Adaptation

The organisation may recruit, release, replace, merge or split roles when evidence shows the current structure is insufficient or wasteful. Every structural change is canonical and reviewable.

### 9.8 Mission closure

The mission enters a closing state while outstanding commitments, external mutations, artifacts, budgets and temporary resources are resolved. Temporary departments and workers dissolve only after closure conditions pass.

The Company, Product, accepted decisions, playbooks, evidence and scorecards persist.

## 10. Organisation formation gate

A separate department should be activated only when at least one of these conditions holds:

1. it requires a distinct authority, confidentiality or policy boundary;
2. its work can progress meaningfully in parallel;
3. it needs specialised tools, knowledge or a different worker configuration;
4. independent judgment is valuable before executive reconciliation;
5. the workload persists across enough packages to justify coordination;
6. an existing role is overloaded or creates a conflict of interest.

Otherwise the executive should use a bounded specialist call or tool rather than forming a department.

The initial organisation is a hypothesis. It may be revised after evidence.

## 11. Interactive executive work-package loop

This is the central V3 execution mechanism.

```text
accepted objective and plan
        ↓
select one coherent next outcome
        ↓
create bounded WorkPackage
        ↓
assign Role + Talent + Vessel
        ↓
short interactive worker Session
        ↓
produce result, evidence and uncertainties
        ↓
independent validation where required
        ↓
executive review
        ↓
accept / revise / route differently / replan / escalate / stop
        ↓
next WorkPackage
```

### Required properties

- No package depends on an unbounded conversation.
- The worker receives accepted current state, not the full historical chat by default.
- The worker may ask bounded clarification questions during execution.
- Accepted external evidence and artifacts survive worker replacement.
- Unaccepted conversational assumptions are discarded when the session ends.
- The executive explicitly decides whether autonomy may continue.
- Long missions are decomposed into phases and packages small enough to inspect.

### Autonomous continuation

Cortana may continue without owner approval only when:

- the result meets the accepted gate;
- no material assumption or objective changed;
- authority, budget and time remain inside the charter;
- no owner-only external action is required;
- relevant assurance passes;
- uncertainty remains below the configured escalation threshold.

## 12. Collaboration and brainstorming protocol

The company may use visible rooms and meetings, but conversation is not authority.

### Canonical blackboard

The collaboration layer projects a structured company blackboard containing:

- objective and current plan revision;
- accepted facts and assumptions;
- open questions;
- proposals;
- challenges and dissent;
- dependency requests;
- evidence;
- accepted decisions;
- commitments;
- current blockers.

### Deliberation protocol

For material cross-department decisions:

1. relevant departments produce independent initial positions before seeing peer conclusions;
2. positions are preserved;
3. one bounded challenge and clarification round occurs;
4. departments may revise only with an identified reason or evidence;
5. the executive adjudicates using evidence, policy, constraints and authority;
6. unresolved minority dissent remains attached to the decision.

Majority vote, longest response and final message do not create truth.

### Meetings

Meetings are temporary processes with:

- purpose;
- participants;
- required inputs;
- bounded duration or rounds;
- structured outcome;
- unresolved items;
- accountable next actions.

A meeting that produces no canonical output is disposable conversation.

## 13. Capability routing and wrong-tool prevention

V3 must address the observed failure mode where workers repeatedly choose unsuitable or equivalent tools before eventually reaching the correct path.

### Role capability manifest

Each role sees a small intent vocabulary. An Engineering assignment might receive:

```text
inspect_codebase
propose_change
apply_reviewed_change
run_validation
request_environment_action
submit_result
```

It should not receive raw choices such as SSH, Docker, Cloudflare and PowerShell unless the package genuinely requires direct provider expertise.

### Routing path

```text
role-level intent
→ exact target and scope
→ policy and capability check
→ deterministic/preferred route
→ preflight
→ one bounded attempt
→ classified fallback or escalation
```

### Failure classes

```text
transient
bounded retry with backoff

wrong route
no equivalent retry; select approved fallback

invalid request
return for correction

policy refusal
stop; do not bypass

provider unavailable
use declared degraded/manual path

unknown repeated failure
stop and escalate
```

### Circuit breaker

Equivalent intent, target and failure classification must not be retried through cosmetically different commands without new evidence. Route performance feeds later WorkerConfiguration and capability-routing evaluation.

## 14. Desired and observed organisation

Soma stores the desired organisation separately from observed reality.

### OrganisationSpec

- active departments and roles;
- desired assignments;
- capability grants;
- budgets;
- plan generation;
- collaboration topology;
- required external bindings;
- desired worker availability.

### OrganisationStatus

- actual worker and provider availability;
- active assignments and sessions;
- current work packages;
- pending owner decisions;
- blockers;
- budget consumption;
- external-system health;
- observed plan generation;
- reconciliation failures.

### Conditions

Status should expose explicit conditions such as:

```text
PlanAccepted
WorkersAvailable
WaitingForOwner
BudgetHealthy
ExternalSystemsHealthy
Blocked
Closing
Ready
```

Each condition records reason, message, observed generation and transition time.

### Reconciler

The Organisation Reconciler performs one bounded correction at a time:

- recreate a missing disposable worker;
- restore an assignment binding;
- revoke a stale capability token;
- repair collaboration membership;
- mark a provider unavailable;
- publish an honest blocker;
- resume the next unresolved package.

It must not fabricate success or repeat accepted work.

## 15. Safe external mutation plane

Reasoning workers should not hold broad credentials for CRM, finance, social publishing, production deployment or customer communication.

### Mutation flow

```text
worker proposes external action
        ↓
Soma validates identity, scope, policy, authority, budget and risk
        ↓
owner approval when required
        ↓
approved mutation and outbox record committed durably
        ↓
scoped executor performs action
        ↓
provider result and observed effect recorded
        ↓
confirmation, retry, compensation or manual remedy
```

### Required properties

- stable idempotency identity;
- exact target and intended effect;
- no secret in ordinary prompts or evidence;
- scoped and revocable execution credential;
- replay-safe handling;
- business-specific compensation or manual-remedy path;
- honest distinction between requested, sent, accepted and confirmed.

Multi-system changes use an explicit orchestrated sequence. Failure does not imply that reality can always be rolled back; unresolved partial effects become incidents or owner decisions.

## 16. Cortana

Cortana is the persistent owner-facing executive interface, not merely a voice skin.

### Responsibilities

- receive goals in natural language;
- explain current company state and why decisions were made;
- create and review charters and plan revisions;
- coordinate departments and bounded work packages;
- surface dissent, risk, budget and uncertainty;
- continue routine work within delegated authority;
- interrupt the owner only for genuine decisions;
- allow immediate owner steering, pause, cancellation and reprioritisation;
- retrieve durable company history and evidence;
- remain responsive while slower worker sessions operate underneath.

### Owner-only decisions

Default owner escalation includes:

- material change to mission or product direction;
- expenditure above accepted thresholds;
- binding legal, financial or exceptional customer commitments;
- policy exceptions;
- high-risk personal or customer-data use;
- irreversible publication or deployment outside delegated bounds;
- abandoning substantial accepted work;
- accepting major unresolved dissent or uncertainty;
- changing the constitutional authority model.

Thresholds and delegations remain configurable by Company and Mission.

## 17. Company dashboard

The dashboard is the visible headquarters of the autonomous company.

### Required views

- companies, products and missions;
- company charter and success criteria;
- current organisation and role assignments;
- accepted plan and phase timeline;
- active WorkPackages and linked canonical tasks;
- dependencies and blockers;
- proposals, decisions, dissent and owner escalations;
- budgets, subscriptions, tokens, provider credits and runway indicators;
- deliverable graph and acceptance status;
- customer commitments and external-system references;
- risk, policy and assurance findings;
- worker and organisational performance;
- provider and reconciliation health;
- company activity and collaboration rooms;
- direct Cortana conversation.

### Dashboard rule

The dashboard reads projections and submits explicit commands. It may not become a second task, plan, decision or memory authority.

## 18. Business backbone and provider boundaries

Soma coordinates business systems rather than rebuilding mature products.

### 18.1 CRM and customer operations

A replaceable CRM owns contacts, companies, leads, opportunities, activities and customer relationships. Tavus/PAL, voice, chat, email and human representatives are interaction providers above the CRM.

Soma owns:

- exact customer-related commitments;
- cross-department follow-up work;
- policy and escalation;
- durable task and decision references;
- provider binding and health;
- confirmed external outcomes.

### 18.2 Finance, accounting and billing

Accounting or ERP software owns the ledger, invoices, expenses, purchasing and statutory business records. Stripe or another processor owns payment and subscription events.

Soma owns budgets, approval boundaries, planned expenditure, task coordination and exact external references. It does not become an accounting ledger.

### 18.3 Product analytics and market learning

External analytics systems may own raw events. Soma preserves hypotheses, experiments, success criteria, interpreted outcomes and decisions.

The company must close the loop:

```text
hypothesis
→ experiment
→ observed metric
→ reviewed interpretation
→ product or strategy decision
```

### 18.4 Creative production

Higgsfield is a future candidate for premium image, video and advertising production. It is one optional `CreativeProductionProvider`, not an architectural dependency.

Without Higgsfield, the company must still be able to create:

- creative strategy;
- scripts and storyboards;
- prompts and shot lists;
- product and interface designs;
- manual production packages;
- simpler assets through another provider.

Provider absence may reduce polish, speed or automation. It may not stop the company from planning, building or preparing a launch.

### 18.5 Live customer interaction

Tavus/PAL or another live-interaction provider may supply video, voice or embodied customer communication. It does not own the CRM, customer commitments or company memory.

Text, email, forms, human handoff and manual follow-up remain valid degraded modes.

### 18.6 Collaboration workspace

Buzz, AgentTeams, Matrix or another provider may host rooms, meetings, presence and working artifacts.

Provider selection is postponed until a real workspace requirement exists. Any chosen provider receives projections from Soma and returns exact conversation or artifact references. It may not own company tasks, plans, decisions or canonical memory.

## 19. Security, privacy and governance

V3 must treat company autonomy as a security boundary.

Required controls include:

- exact company, mission, project, role, assignment and external-account identity;
- fail-closed scope resolution;
- executable capability and authority checks;
- least-privilege, revocable credentials held behind gateways;
- secret exclusion from ordinary worker prompts, logs and evidence;
- customer consent, lawful-purpose and retention records where applicable;
- data classification preserved across departments and artifacts;
- prompt-injection and untrusted-content boundaries;
- explicit human takeover for customer and high-risk actions;
- immutable audit references for decisions and external mutations;
- backup, export and replacement plans for external systems;
- visible incidents and recovery failures.

The owner remains legally and strategically responsible. Software autonomy does not transfer legal accountability to an agent.

## 20. Independent assurance

The creator of a deliverable should not be its sole acceptance authority when the risk warrants separation.

Assurance functions may include:

- code review and automated testing;
- product and UX review;
- factual and research verification;
- security and privacy review;
- legal or policy checks;
- financial consistency checks;
- brand and customer-communication review;
- launch-readiness assessment;
- post-launch monitoring and incident review.

Assurance should prefer verifiable evidence over additional debate. Tests, source evidence, policy and observed outcomes outrank confident agreement among agents.

## 21. Evaluation and autonomy graduation

V3 evaluates the whole worker configuration and organisation, not only the model name.

### WorkerConfiguration identity

A stable evaluated identity includes:

- model and version;
- harness;
- role and Talent version;
- capability manifest;
- context policy;
- limits and fallback policy;
- evaluation and assurance method.

### Required measurements

- final outcome quality;
- repeated reliability, not one attractive demo;
- time to first useful work;
- total cost and provider credit use;
- number of worker and model calls;
- wrong-route attempts;
- rework and duplicated work;
- contradictory commitments;
- cross-deliverable inconsistency;
- unnecessary owner escalations;
- policy violations;
- recovery after interruption;
- customer or market outcome where applicable.

### Autonomy levels

A capability graduates from simulated or proposal-only operation toward autonomous execution only after repeated evidence supports the increased authority. High-impact actions retain stricter approval even when routine performance is strong.

## 22. Organisational memory and genuine learning

V3 preserves the owner's definition that retrieval alone is not learning.

### Organisational memory

Decisions, postmortems, examples, workflows and retrieved context improve continuity but remain memory.

### Promoted capability learning

A validated new skill module, routing policy, evaluator, workflow implementation or adapter changes future behaviour without replaying the original correction. This qualifies as learning after evaluation and authorised promotion.

### Parametric learning

Model adapters, fine-tuning or other parameter updates may be introduced later through an offline pipeline:

```text
production trajectories
→ privacy and quality filtering
→ training/evaluation corpus
→ candidate update
→ fixed benchmark and safety gate
→ authorised promotion
```

No production worker changes its own weights, authority or permanent instructions during live operation.

## 23. Recommended Roadmap V3 outcome sequence

This architecture is an end-state design. The implementation sequence begins with the interactive substrate the original draft assumed but did not schedule.

### V3-0 — Architecture reconciliation

- Claude Opus architectural red-team is complete.
- Codex repository-grounded feasibility review is complete.
- The owner-approved destination remains unchanged.
- Review corrections and progressive lifecycle convergence are recorded in [`SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md`](SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md).
- No implementation begins until the owner explicitly activates the first lane.

### V3-1a — Interactive worker substrate

Extend the canonical Task → Run authority with one bounded provider-native interactive worker path.

Required outcomes:

- provider-session binding with exact native identity;
- explicit resume by identity after Soma and adapter restart;
- crash-safe steering and supplied-input delivery;
- real non-terminal `AWAITING_CONTROLLER` continuation with a durable checkpoint deadline;
- bounded checkpoint-expiry handling that never releases ownership while a worker may still mutate;
- provider-session invalidation recovery that becomes durable uncertainty and requires adjudication before a fresh attempt;
- provider-child process identity and zero-orphan cancellation evidence;
- raw, deduplicated provider usage events;
- fixed sanitised launch environment;
- provider protocol fixtures and fail-closed drift handling;
- no worker access to Soma MCP.

This lane performs progressive convergence for worker waiting, interaction, cancellation and recovery. It may not create a second worker lifecycle manager.

### V3-1b — Kernel of one

Prove the smallest useful company kernel with one executive role before creating departments.

Minimum additive authority:

- Company reference;
- Mission bound to one exact ProjectScope;
- immutable accepted PlanRevision with one-current CAS;
- bounded WorkPackage contract;
- WorkPackageAttempt links to route-specific canonical tasks;
- route-independent outcome identity;
- one AcceptanceCommit selecting an exact published result hash.

This lane performs progressive convergence for outcome adjudication. WorkPackage execution state is projected from canonical tasks and runs; it does not copy their lifecycle.

### V3-2 — Role-scoped capability broker

Before any worker receives Soma capabilities, add a separate worker-facing positive-allowlist boundary that binds an unforgeable principal to project, task, session, role and exact intent/operation identity. The current owner/executive MCP surface remains unchanged.

Discovery filtering is not authorisation. Workers receive no direct current Soma MCP connection before this outcome closes.

### V3-3 — Interactive executive loop and bounded collaboration

Add package-completion-driven executive advancement, structured proposals, challenges, dependency requests, deliberation, dissent and owner escalation over the kernel-of-one. Reuse research and knowledge records where they fit; do not grant them task or result-acceptance authority.

### V3-4 — Temporary organisation formation

Add the smallest-sufficient-organisation gate, temporary Roles and Assignments, organisation revision and bounded cross-role collaboration. A one-executive configuration remains valid and may outperform a larger team.

### V3-5 — Organisation observation and reconciliation

Add only the desired-versus-observed organisation behaviours justified by measured worker reconstruction, provider health and collaboration needs. The organisation reconciler selects bounded transitions and invokes canonical owners; it does not own PIDs, leases, cancellation or result publication.

### V3-6 — Cortana and company dashboard

Deliver the owner-facing company experience over canonical projections. Begin with text, owner decisions and live status. Voice and richer presence remain replaceable presentation capabilities.

### V3-7 — Business-system binding and safe mutations

Add generic external-system references and policy-governed mutation execution only after the worker capability boundary exists. Reuse domain-specific mutation authorities where present; do not duplicate Trading Lab or other domain journals.

### V3-8 — Bounded provider pilots

Research and pilot CRM, finance/accounting, billing, workspace, creative production, live customer interaction, analytics and support only when a real company workflow requires them.

### V3-9 — Autonomous company trial

Give the system one bounded real objective and prove that it can plan, execute, review, prepare launch and measure outcomes with limited owner intervention. Scheduled autonomous advancement remains gated by cost ceilings and the fixed golden-task evaluation set.

### V3-10 — Organisational optimisation and genuine learning

Compare the kernel-of-one against larger organisational configurations, promote measured playbooks and routing improvements, and later admit skill or parameter updates through explicit evaluation gates.

## 24. First implementation evidence boundary

The original `COMPANY-KERNEL-SPIKE-1` mixed an unbuilt interactive worker substrate, a company kernel, multiple departments, capability enforcement, external mutation and dashboard reconstruction. It is replaced by two sequential proofs.

### 24.1 V3-1a — Interactive worker substrate proof

#### Objective

Prove that Soma can supervise one bounded interactive provider session through the canonical task/run plane without relying on a long-running conversation or creating another execution authority.

#### Required proof

1. Soma launches one interactive worker through a canonical task and run.
2. The run binds an exact provider-native session identity durably.
3. One steering message and one supplied answer are persisted before delivery and applied idempotently.
4. A controller wait remains non-terminal, has a durable deadline, and survives restart. On expiry, Soma attempts a bounded safe pause or cancellation. It may transition to `PAUSED` and release locks only after the provider worker is confirmed quiescent or terminated with a resumable session binding; otherwise it enters `UNCERTAIN` and retains ownership until adjudicated.
5. Soma, the adapter and provider child are terminated; explicit-ID resume restores provider context without replaying worker conversation history.
6. If explicit-ID provider reattachment fails because the session is missing, invalid, or corrupt, Soma records durable uncertainty with exact evidence. It must not automatically launch a clean replacement attempt; an executive recovery decision may later adopt evidence, supersede with a fresh attempt, or stop.
7. Cancellation leaves no owned descendant process for Claude and Codex.
8. Raw usage events are deduplicated and queryable by session, run and task.
9. The launch environment excludes provider-recursion markers, inherited MCP configuration and unrelated credentials.
10. Protocol drift or unprovable interaction delivery fails closed as durable uncertainty.
11. The worker cannot discover or invoke any Soma MCP operation.

#### Stop conditions

- provider context cannot be resumed by exact identity;
- waiting requires a terminal run or a new lifecycle manager;
- a checkpoint can wait indefinitely without a durable deadline and bounded expiry disposition;
- timeout can release a repository/resource lock while a provider worker may still mutate;
- invalid provider-session recovery silently launches a fresh attempt;
- duplicate input or steering can be delivered after replay;
- cancellation can publish success while an owned worker continues mutating;
- usage evidence cannot be preserved in provider-native units;
- implementation requires broad unrelated lifecycle consolidation.

### 24.2 V3-1b — Kernel-of-one proof

#### Objective

Prove one continuous company mission executed through discontinuous, bounded worker sessions and exact executive acceptance.

#### Required proof

1. one Company reference, Mission and current immutable PlanRevision exist;
2. the Mission binds exactly one active ProjectScope;
3. every WorkPackage has a route-independent outcome identity;
4. changed provider, profile or argv creates a controlled superseding task attempt under the same outcome;
5. by default, one outcome permits at most one non-terminal route attempt. A superseding route requires the prior attempt to be terminal or explicitly contained. Later evaluation contracts may deliberately permit parallel candidate attempts, but they must declare that topology before launch and still enforce one authoritative OutcomeAcceptance unless multiple accepted deliverables are part of the contract;
6. only one exact published result hash can receive the AcceptanceCommit;
7. a crash after result publication but before OutcomeAcceptance does not rerun accepted work or fabricate acceptance;
8. a package requiring an owner decision suspends, survives restart and resumes without replaying worker conversation;
9. deliberation references preserve alternatives and dissent without becoming execution authority;
10. deleting and rebuilding projections changes no canonical record;
11. owner-turn and package-completion events can each drive one bounded `reconcile_one` transition.

#### Measurements

```text
time to first useful result
package authoring burden
worker/session count
interaction count
resume fidelity
orphan process count
raw provider usage
wrong-route attempts
duplicate outcome attempts
duplicate acceptance attempts
owner interventions
recovery correctness
```

#### Stop conditions

- a new durable authority appears for task admission, run execution, plan currency, result publication, decision acceptance or memory writes beyond the declared baseline;
- WorkPackage copies task/run lifecycle state;
- one route change duplicates accepted work;
- acceptance cannot be made crash-safe and unique;
- recovery requires replaying a lost worker conversation;
- an optional provider or direct worker MCP connection is required.

### 24.3 Deferred organisational comparison

The original A/B/C comparison is deferred until V3-1a, V3-1b, cost evidence and the golden-task evaluation set exist. A one-executive company is a valid outcome, not a failed organisation. Larger teams must later earn their coordination cost on an objective that genuinely requires authority separation, independent judgment or useful parallelism.

### 24.4 Progressive-convergence lane gate

Every V3 implementation lane must close with an authority delta:

1. lifecycle authorities touched;
2. generic responsibilities moved or projected into the canonical task/run plane;
3. domain states intentionally retained and why;
4. temporary compatibility bridges and exact retirement conditions;
5. net canonical-authority count: decreased, unchanged, or explicitly temporary.

A lane cannot claim completion while leaving a new unexplained generic lifecycle authority behind.

## 25. Explicit non-goals and rejected approaches

This architecture rejects:

- one uninterrupted agent run for a long mission;
- a fixed department zoo for every objective;
- free-form swarms as company authority;
- majority consensus as acceptance;
- CrewAI, LangGraph, AutoGen, OpenFang, Kortix, AgentTeams, Buzz or another framework as Soma's canonical control plane;
- a second execution lifecycle beneath the Company Kernel;
- a wholesale lifecycle-consolidation programme before the first V3 proof;
- leaving duplicate generic lifecycle authority permanent merely because it predates V3;
- copying CRM, accounting or billing databases into Soma;
- making Higgsfield, Tavus or another subscription mandatory;
- exposing every Soma operation to every worker;
- direct broad provider credentials inside reasoning workers;
- dashboard state as canonical truth;
- silent fallback or silent degraded operation;
- live self-modification of worker authority or permanent behaviour;
- defining success as agent activity rather than verified company outcome.

## 26. Reference patterns adopted without adopting their control planes

| Reference family | Adopted design pattern |
|---|---|
| MetaGPT | typed roles, outputs and operating procedures |
| ChatDev | structured cross-role clarification and review |
| Magentic-One | separate task/plan ledger and progress evaluation |
| AutoGen / OpenAI Agents SDK | manager-controlled specialists and bounded handoffs |
| CrewAI | deterministic company flow around bounded autonomous crews |
| DyLAN / AgentVerse | dynamic recruitment and revisable team formation |
| MOISE+ | structural, functional and authority dimensions remain separate |
| Contract Net | bounded work offers and accountable assignment |
| Blackboard systems | shared canonical working state separate from conversation |
| OneManCompany | Role/Talent/Vessel separation and visible company metaphor |
| Kortix | reviewed configuration-as-code and promoted self-improvement |
| OpenFang | capability profiles, loop guards, metering and sensitive-data flow |
| AgentTeams | desired worker/team resources, room projection and credential gateway |
| GitHub Agentic Workflows | reasoning workers propose writes; scoped jobs apply them |
| Kubernetes | desired-versus-observed reconciliation, conditions and finalisation |
| Temporal | durable mission, bounded activities, classified retry and pause semantics |
| BPMN/Camunda | deterministic business skeleton around agentic work |
| Actor supervision | restart, replace, stop or escalate disposable workers |
| GitOps | immutable reviewed constitution changes and reconciliation |
| Event sourcing | append-only material decisions with rebuildable projections |
| Transactional outbox and sagas | durable, idempotent external effects and compensation |
| Cedar-style policy | explicit principal/action/resource/context authorisation |

These are design references. Any later dependency requires its own bounded solution discovery and compatibility decision.

## 27. Claude Opus architectural red-team brief

Claude should challenge this design without replacing the owner-approved destination.

Required review questions:

1. Where does the design accidentally introduce a second authority?
2. Which domain objects are unnecessary, ambiguous or overlapping?
3. Can the interactive work-package loop be simpler while preserving the invariants?
4. Are interruption, reconciliation and external-mutation semantics complete?
5. Where could a long-running agent or hidden conversational dependency reappear?
6. Are authority, budget and owner-escalation rules enforceable rather than aspirational?
7. Does the organisation model support a one-person/simple-agent configuration without ceremony?
8. Which security, privacy or customer-harm paths remain under-specified?
9. Which end-state capabilities should be delayed or removed from V3?
10. What is the smallest coherent Company Kernel spike that still tests the destination?

Claude should return contradictions, risks, simpler alternatives and blocking questions. It should not produce implementation changes or silently choose providers.

## 28. Codex repository-feasibility brief

Codex should inspect the live repository and map this architecture onto current Soma reality.

Required review questions:

1. Which current models, stores, gateways and lifecycle authorities can be reused unchanged?
2. Where should Company, Mission, PlanRevision and WorkPackage attach without duplicating tasks or workflows?
3. What exact compatibility and migration risks exist?
4. Which current lifecycle overlaps would block the first spike, and which can remain untouched?
5. What is the smallest additive schema and service boundary for the spike?
6. How can role capability manifests project onto current public operations without a broad operation cleanup?
7. How can restart recovery prove that worker conversations are disposable?
8. What existing evidence, events and result mechanisms can support decisions, dissent and deliverables?
9. What focused tests and fixtures are required before broader implementation?
10. Which architecture claims are impractical or conflict with the current codebase?

Codex should produce a feasibility map and implementation options, not commit code, create a lane or rewrite the product direction.

## 29. Review and promotion process

1. Claude Opus completed the architectural red-team.
2. Codex completed the independent repository-grounded feasibility review.
3. ChatGPT reconciled both reports without changing the owner-approved destination.
4. Arash accepted progressive lifecycle convergence: consolidate the generic lifecycle territory each V3 lane touches, without a broad preliminary cleanup and without permanent duplicate authority.
5. The reconciliation is recorded in [`SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md`](SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md).
6. `V3-1A`, `V3-1B` and `V3-2` implementation/evidence exist in the repository. On 2026-08-15 the owner corrected the implementation sequence: the Autonomous Company roadmap remains frozen, `V3-1B` / `V3-2` activation provenance is disputed, and none of these records authorise `V3-3` or any later Company lane. The future Company sequence remains preserved as architecture only until explicitly reopened by the owner.

A generic `continue` does not authorise implementation, provider installation, subscription purchase, customer contact, external publication, deployment or push.

## 30. Final architecture statement

> **Soma V3 is the operating system of an owner-governed autonomous company. Cortana is its human face and executive interface. Soma preserves the constitution, organisation, plans, authority, work, decisions, commitments, evidence and recovery. Temporary departments collaborate through bounded structured interactions. Short-lived workers execute one inspectable chunk at a time. Generic lifecycle authority progressively converges into the canonical task/run plane as V3 touches it, while irreducible domain facts remain with their domains. External business, creative and interaction providers remain replaceable. The company may operate continuously; its agents may not become the company.**
