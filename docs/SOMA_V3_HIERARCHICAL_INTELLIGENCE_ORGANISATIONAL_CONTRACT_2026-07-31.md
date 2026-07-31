# SOMA-V3-ORG-CONTRACT-1 — Hierarchical Intelligence and Durable Organisation

**Date:** 2026-07-31  
**Status:** owner-accepted target architecture contract; organisational research closed at saturation.  
**Decision level:** C — foundational organisational authority, delegation, communication, capability, acceptance, and execution-safety boundary.  
**Owner:** Arash.  
**Supersedes on conflict:** organisational assumptions in [`SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md`](SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md) and [`SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md`](SOMA_V3_ARCHITECTURE_RECONCILIATION_2026-07-30.md).  
**Implementation effect:** documentation and gate sequencing only. No company-kernel, team, provider, capability-broker, or production behaviour is activated by this decision.

## 1. Final decision

Soma will provide the durable organisation around intelligent agents. It will not attempt to encode agent reasoning as one enormous deterministic workflow.

The frozen statement is:

> **Agents exercise judgment. Roles carry organisational responsibility. Authorities delegate direction, approve exceptions, and accept outcomes. Soma preserves durable organisational truth and coherent state. Capability systems control concrete access. Technical supervision owns execution, containment, cancellation, and recovery. Acceptance authorities judge substantive correctness. Mechanical systems alone authorise irreversible state transitions.**

The design combines:

- a stable authority spine;
- task-specific adaptive collaboration;
- bounded delegated judgment;
- durable communication and responsibility;
- explicit concrete capabilities;
- mechanically proven operational safety.

Single-agent execution remains the default. Multi-agent organisation must earn its coordination cost.

## 2. Intelligence and mechanical authority

A capable child agent receives purpose, expected outcome, scope, constraints, authority, escalation conditions, and reporting expectations. It may choose methods, investigate, adapt, consult specialists, and make local decisions inside that frame.

Soma must not convert this judgment into procedural micromanagement.

Intelligent agents may judge:

- how to approach the mission;
- which evidence is relevant;
- which method or tool is appropriate inside their authority;
- when ambiguity or risk is meaningful;
- when a specialist or temporary subagent would help;
- whether an outcome appears correct;
- when an escalation boundary has been reached.

Soma and its mechanical authorities prove only operational and procedural facts, including:

- the active mandate and authority version;
- sender, recipient, task, session, checkpoint, and resource coherence;
- concrete capability possession;
- idempotency and delivery evidence;
- cancellation, revocation, expiry, and supersession precedence;
- process containment and repository ownership;
- required evidence references, hashes, provenance, and reviewer records;
- permission for an irreversible state transition or ResultPublication.

Soma does not decide whether evidence intellectually establishes architectural or business correctness. That substantive judgment belongs to the named acceptance authority, human or delegated intelligent agent.

## 3. Distinct identities

The following identities must never be collapsed:

### Role

A durable organisational responsibility such as Chief of Staff, Engineering Lead, Researcher, Reviewer, or Risk Authority. A Role is independent of provider, model, account, session, and operating-system process.

### Agent identity

An optional persistent persona, memory, skill, and evaluation identity that may occupy one or more assignments over time. Agent identity is replaceable and cannot silently modify organisational authority.

### Assignment

A bounded binding of one Role to an Agent identity or execution configuration for one mission, work period, or task scope.

### Session

One bounded provider conversation or working episode. A Session is disposable and may not own organisational continuity.

### Execution

The exact operating-system process or contained process tree that technically realises a session or tool action. Execution identity owns no logical direction or acceptance authority.

The intended mapping is:

```text
Role
  ↓ occupied through Assignment
Agent identity or replaceable worker configuration
  ↓ acts through
Session
  ↓ realised by
Execution
```

Replacing Claude, Codex, ChatGPT, Hermes, a model, an account, a native session, or a process must not replace the Role or lose the accepted mandate and organisational record.

## 4. Four linked graphs

Soma must preserve four linked but non-interchangeable graphs.

### 4.1 Authority graph

Records who may:

- direct work;
- issue or amend a mandate;
- revoke authority;
- accept or reject an outcome;
- approve exceptional risk;
- transfer accountable ownership.

Authority relationships are typed. They are not forced through one universal parent pointer.

### 4.2 Collaboration graph

Records who is currently:

- working together;
- reporting progress;
- consulting a peer or specialist;
- challenging a proposal;
- delegating temporary subordinate work;
- sharing a bounded context packet.

The collaboration graph may adapt to the task. It does not change authority or concrete access by itself.

### 4.3 Execution-ownership graph

Records which technical authority:

- started a session or process;
- owns containment and liveness;
- may cancel or stop it;
- reconciles it after failure;
- proves quiescence or tree emptiness.

The technical parent manages operational reality. It does not decide the mission or accept the result merely because it launched the worker.

### 4.4 Resource-capability graph

Records who may concretely access:

- repositories and worktrees;
- tools and gateways;
- credentials and secret classes;
- budgets and spending envelopes;
- connectors and external systems;
- mutation, commit, push, deployment, or customer-contact surfaces.

Organisational authority may request or delegate access only within its delegable ceiling. It does not manufacture a repository lock, credential, budget, or execution capability.

## 5. Accountable ownership

Every active work item has exactly one accountable owner.

The organisation may contain multiple directing, consulting, reviewing, risk, acceptance, capability-granting, and reporting relationships, but one identity remains accountable for the work item’s current organisational outcome.

Accountable ownership transfer must be atomic:

- the old and new owner may never both be current;
- the work item may never silently have no current owner;
- the transfer records issuer, old owner, new owner, reason, effective version, and exact transition evidence;
- failure before commit leaves the old owner authoritative;
- failure after commit leaves the new owner authoritative.

Temporary subagents and specialists report into the accountable work item. They do not become competing accountable owners unless an explicit atomic transfer occurs.

## 6. Delegation mandate

Every child begins work under an immutable, content-addressed, versioned mandate.

A mandate includes at minimum:

- mandate ID and content hash;
- parent mandate and delegation lineage;
- issuer identity and authority relationship;
- intended recipient Role and optional assigned Agent or Session;
- project, task, work-item, resource, and time scope;
- purpose and expected outcome;
- permitted and prohibited actions;
- delegable authority;
- capability and budget ceilings;
- escalation and reporting conditions;
- acceptance authority;
- risk authority;
- accountable owner;
- effective time and optional expiry;
- status: proposed, active, superseded, revoked;
- superseding mandate ID where applicable.

Effective child authority is always the intersection of:

```text
parent delegable authority
∩ organisational policy
∩ concrete resource grants
∩ child mandate
```

Natural-language instructions may narrow judgment. They cannot mint permissions the issuer does not possess.

A child may delegate only authority that is both held and marked delegable, and every downward delegation may narrow but never silently expand authority.

## 7. Amendment, acknowledgement, revocation, and cancellation

### 7.1 Ordinary amendment

A normal amendment, changed instruction, or authority expansion does not become operational for the child merely because it was stored. It must be delivered to the exact current task/session and acknowledged against the expected mandate version.

Until correlated acknowledgement, the child remains governed by the last acknowledged version unless the work is centrally paused, cancelled, or adjudicated.

### 7.2 Authority narrowing

A centrally recorded narrowing may immediately deny new protected actions through the capability and policy layers even before the child acknowledges the updated instruction.

### 7.3 Revocation linearization point

Revocation has one canonical linearization point: the successful durable transition of the mandate to revoked under the expected version.

After that point:

- Soma denies every new protected action under that mandate;
- pending commands or decisions cannot restore its authority;
- a late acknowledgement cannot reactivate it;
- the child may continue only unprotected reasoning or reporting permitted by policy;
- already-started external or process actions are not presumed stopped.

Already-started actions enter cancellation, containment, or recovery handling until their real outcome is proven. Revocation ends future authority immediately; it does not fabricate operational quiescence.

### 7.4 Cancellation precedence

Cancellation outranks pending commands, mandate amendments, decisions, acknowledgements, checkpoint resolution, and resume attempts. A stale message cannot reopen cancelled, expired, superseded, replacement, or terminal work.

## 8. Organisational communication

Soma should use one durable content-addressed communication foundation while preserving distinct message semantics.

Every envelope binds at minimum:

- sender and recipient identity or typed authority relationship;
- project, task, work item, and accountable owner;
- session and mandate references where applicable;
- message class and content hash;
- idempotency identity;
- correlation or checkpoint identity;
- reservation and transport-attempt evidence;
- acknowledgement or terminal delivery disposition;
- expiry, supersession, and cancellation state.

Message classes include:

### Command or mandate amendment

Requires exact delivery and acknowledgement before it may direct or expand active work.

### Clarification request or escalation

Opens a correlated checkpoint and expects a response from an authorised relationship such as directing authority, risk authority, or owner.

### Decision

May resolve a checkpoint or permit continuation only when task, session, mandate, version, checkpoint, cancellation, and expiry checks all match.

### Progress report

Informational. It never changes authority, resolves a checkpoint, resumes work, or implies acceptance.

### Evidence submission

Appends traceable evidence. It never implies substantive sufficiency or acceptance.

### Outcome proposal

Requests review. It does not close the work item or publish an accepted outcome.

### Acceptance or rejection

Acts only through the named acceptance authority and the exact current result/evidence identity.

### Revocation or cancellation

Takes precedence centrally. Delivery to the child remains important for stopping voluntary work, but acknowledgement is not required for Soma to deny new protected actions.

## 9. Delivery-attempt truth

A durable communication record must distinguish:

- reserved and definitely never attempted;
- transport attempt durably claimed;
- outcome unknown after an attempted send;
- acknowledged;
- rejected;
- superseded, expired, or cancelled.

A reserved message may be claimed once. An outcome-unknown message is never blindly resent. Recovery requires exact recipient/provider evidence or explicit adjudication.

Exactly-once external effect is not inferred from a local send call. Idempotency and acknowledgement must be established at the correct authority boundary.

## 10. Permanent roles and temporary subagents

Soma distinguishes:

### Durable organisational roles

Long-lived responsibilities such as Chief of Staff, Engineering Lead, Researcher, or Reviewer. Their identity and responsibility survive provider and session replacement.

### Temporary subagents

Bounded subordinate work created for a specific assignment. A temporary subagent:

- receives a narrowed mandate;
- inherits exact project/task/resource context;
- cannot delegate authority it did not receive;
- reports evidence and outcome to its logical work relationship;
- does not become a new canonical task, plan, or acceptance authority merely because it is a separate model session;
- terminates or becomes inactive after its assignment.

Permanent teams, departments, and dynamic role creation are later company-kernel concerns. The interaction foundation needs only the identity and message primitives that can support them later.

## 11. Context and memory

Shared organisational truth and role-specific context packets are preferred over universal shared conversation history.

Every agent may receive the current goal, accepted decisions, mandate, task state, and relevant dependencies. Private evidence, secrets, source files, customer data, specialist detail, and unrelated conversations remain scoped to the role and concrete capability grant.

Agent memory, personality, skills, and self-description may evolve only within their own versioned authority. They may not silently modify:

- a current mandate;
- organisational responsibility;
- accountable ownership;
- capability grants;
- mechanical permissions;
- acceptance or risk authority.

Accio Work is retained as a product and interaction precedent for Team Lead/member collaboration, temporary SubAgents, role descriptions, memory, skills, tools, and permissions. Its public material does not establish Soma’s required durability, acknowledgement, cancellation, idempotency, containment, checkpoint, or publication guarantees and therefore is not architectural proof.

## 12. Interaction-foundation scope

The current `V3-1A-INTERACTION-COMMANDS-1` implementation must not absorb the complete company model.

The minimum durable substrate authorised for that gate is limited to:

- exact sender and recipient references;
- project, task, run, session, checkpoint, and mandate references;
- generic content-addressed message envelopes;
- command versus informational-report semantics;
- idempotent reservation;
- durable transport-attempt claim and uncertain outcome;
- acknowledgement and correlation;
- canonical non-terminal wait and resume;
- cancellation, revocation, expiry, and supersession precedence;
- stale-message rejection;
- procedural evidence sufficient for later organisational layers.

Explicitly deferred:

- permanent team and department implementation;
- dynamic durable role creation;
- broad capability delegation;
- organisational negotiation, voting, councils, or markets;
- self-modifying organisational identity;
- company-global memory evolution;
- real provider launch and production use;
- V3-1B Company Kernel implementation.

## 13. Adversarial invariants

The architecture is unacceptable if any scenario permits:

1. one work item to have two accountable owners or none during handoff;
2. an issuer to delegate authority it does not hold or cannot delegate;
3. an unacknowledged authority expansion to become usable;
4. a revoked mandate to authorise a new protected action;
5. revocation to be mistaken for proof that an already-started action stopped;
6. a late decision or acknowledgement to resume cancelled, expired, superseded, replacement, or terminal work;
7. an informational report or evidence submission to change lifecycle state;
8. a temporary subagent to become a competing task, result, acceptance, or recovery authority;
9. a technical parent to become logical or acceptance authority merely because it launched a process;
10. an organisational manager to gain concrete resource capability merely because it directs the work;
11. Agent memory or personality changes to alter mandates or permissions;
12. an uncertain transport attempt to be blindly resent;
13. a model’s confidence to substitute for containment, lock, cancellation, idempotency, or publication proof;
14. procedural evidence presence to substitute for substantive acceptance judgment.

## 14. Research closure

The research loop covered organisational delegation, adaptive multi-agent collaboration, actor-style technical supervision, durable workflow communication, agent-team products including Accio Work, and adversarial failure cases.

The research changed the architecture in material ways:

- delegated intent replaced procedural micromanagement;
- logical direction separated from technical execution ownership;
- Role, Agent, Assignment, Session, and Execution identities were separated;
- authority, collaboration, execution ownership, and resource capability became four linked graphs;
- immutable mandates, acknowledgement, revocation, and atomic accountable ownership were added;
- message classes received distinct lifecycle semantics;
- procedural sufficiency was separated from substantive acceptance;
- permanent roles were separated from temporary subagents;
- stable authority was combined with adaptive collaboration.

Further broad organisational or competitor research is unlikely to change the foundation. The next useful work is adversarial contract review and the smallest interaction-substrate implementation consistent with this document.
