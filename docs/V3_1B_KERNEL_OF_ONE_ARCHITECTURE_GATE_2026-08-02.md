# V3-1B — Kernel of One Architecture Gate

**Date:** 2026-08-02  
**Status:** active; documentation-only architecture gate  
**Parent roadmap:** [`SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md`](SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md)  
**Depends on:** accepted V3-1A lane completion and the owner-accepted hierarchical-intelligence organisational contract  
**Implementation:** not authorised by this gate  
**Push:** not authorised

## 1. Objective

Design and independently audit the smallest useful company kernel with one executive role before adding departments, permanent teams, broad capability delegation, scheduled autonomy, or external business mutations.

The kernel must represent one continuous Mission executed through discontinuous, bounded canonical Task and Run attempts, while keeping executive OutcomeAcceptance distinct from TaskAdmission and ResultPublication.

## 2. Minimum additive authority

The architecture must define the smallest coherent contracts for:

- one Company reference;
- one Mission bound to exactly one active ProjectScope;
- immutable PlanRevision records with one-current compare-and-set selection;
- bounded WorkPackage contracts;
- route-independent outcome identity;
- WorkPackageAttempt links to route-specific canonical Tasks;
- one AcceptanceCommit selecting one exact published result hash.

These records may add company-domain facts. They may not copy Task or Run execution lifecycle, own processes, control locks, publish run results, or reinterpret `TaskState.ACCEPTED` as substantive outcome acceptance.

## 3. Canonical authorities that remain unchanged

- ProjectScope owns project, repository, task, run, and resource coherence.
- TaskStore and TaskManager own TaskAdmission, task state, task commands, checkpoints, and canonical task projections.
- RunStore, JobManager, workers, process control, and operation locks own durable execution, containment, cancellation, evidence, and ResultPublication.
- WorkerSubstrateStore owns subordinate provider-session and interaction evidence only.
- The new kernel may own Mission, plan, package, route-independent outcome, and executive AcceptanceCommit facts only.

## 4. Required architecture decisions

The review must resolve, with exact identifiers and transaction boundaries:

1. Company identity and whether V3-1B needs more than one Company record in the first proof.
2. Mission identity, immutable intent, and exact binding to one active ProjectScope generation.
3. PlanRevision content addressing, lineage, one-current compare-and-set, supersession, and crash recovery.
4. WorkPackage contract fields: purpose, authority, constraints, success evidence, escalation, reporting, and dependency boundaries.
5. Route-independent outcome normalisation and versioning.
6. WorkPackageAttempt linkage to canonical task identity without duplicating task state.
7. Default one-non-terminal-attempt-per-outcome rule and the exact containment evidence required before supersession.
8. AcceptanceCommit eligibility, exact ResultPublication hash binding, one-winner uniqueness, and idempotent replay.
9. Crash after ResultPublication but before AcceptanceCommit.
10. Owner-decision waiting and restart without replaying worker conversation.
11. Proposal, alternative, dissent, and deliberation references that remain non-authoritative.
12. Projection rebuild and reconciliation behavior.
13. Bounded `reconcile_one` triggers from owner turns and package-completion events.
14. Compatibility and retirement implications for generic workflow/supervisor lifecycle managers when this lane first touches their territory.

## 5. Adversarial proof requirements

The architecture review must prove that the design cannot:

- create a second Task or Run lifecycle;
- create competing authoritative acceptance records;
- accept an unpublished, mismatched, mutated, or wrong-scope result;
- launch duplicate route attempts after replay or restart;
- silently supersede a still-mutating attempt;
- infer substantive correctness from process success alone;
- let a proposal, verifier note, or deliberation record become execution or acceptance authority;
- lose the current PlanRevision or accepted outcome across crash windows;
- grant authority or capability not held by the issuing executive/mandate;
- make departments or permanent roles necessary for the kernel-of-one proof.

## 6. Required evidence before implementation

The documentation gate closes only with:

- repository-grounded authority inventory showing what can be reused and what must be additive;
- proposed schemas, identities, hashes, foreign keys, uniqueness constraints, and migration strategy;
- transaction and compare-and-set boundaries for plan selection, attempt reservation, supersession, and acceptance;
- state/projection diagrams proving execution lifecycle is derived from canonical Tasks and Runs;
- crash and replay matrix for every authority transition;
- ProjectScope isolation and wrong-scope adversarial plan;
- compatibility analysis for workflows, supervisors, result publication, memory, and public gateways;
- public contract proposal with bounded projections and no premature implementation;
- focused and broad validation plan;
- independent acceptance audit that either accepts the design, corrects it, or returns it for revision.

## 7. Explicit exclusions

This gate does not authorise:

- V3-1B product implementation;
- real provider launch or account use;
- worker-facing Soma MCP access;
- departments, permanent teams, or organisation formation;
- role-scoped capability broker implementation;
- scheduled autonomous advancement;
- generic external-system mutation;
- production activation, deployment, purchase, credential work, or push;
- broad workflow/supervisor migration beyond architecture analysis required by the kernel boundary.

## 8. Stop conditions

Return to architecture correction rather than implementation if:

- WorkPackage requires its own execution lifecycle;
- OutcomeAcceptance cannot be separated from TaskAdmission and ResultPublication;
- one-current PlanRevision or one-winner AcceptanceCommit cannot be enforced transactionally;
- route-independent outcomes cannot survive provider/profile/argv changes;
- supersession can occur without terminal or explicit containment evidence;
- ProjectScope coherence cannot be enforced on every company-domain record;
- the proof requires departments, broad capabilities, real providers, or production activation;
- the design depends on semantic similarity for identity or idempotency.

## 9. Exit

Produce a repository-grounded architecture proposal and an independent acceptance audit. Only an accepted audit may activate a bounded V3-1B implementation gate. Until then, all V3-1B product code and later V3 outcomes remain inactive.
