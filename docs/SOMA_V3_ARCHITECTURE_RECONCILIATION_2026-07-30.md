# SOMA-V3-ARCH-RECONCILIATION-1 — Architecture Review Reconciliation

**Date:** 2026-07-30  
**Status:** owner-accepted reconciliation amended by the 2026-07-31 organisational contract and interaction-foundation architecture hold; sequencing remains controlled through `PLANS.md`.
**Decision level:** C — V3 sequencing, lifecycle authority and implementation-boundary decision.  
**Architecture:** [`SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md`](SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md)  
**Repository basis:** branch `lane/memory-integration-foundation-1`; architecture commit `510b9fa0e17c2ff4c188e3d4b7c32159833f4081`.

## 1. Purpose

The first V3 architecture was reviewed through:

- an adversarial Claude Opus architectural red-team;
- an independent Codex repository-grounded feasibility audit;
- ChatGPT reconciliation with the owner.

Both reviews accepted the owner-approved destination. They disagreed mainly about how early Soma should consolidate its existing lifecycle authorities.

This record resolves that disagreement and updates the V3 sequence.

## 2. Preserved destination

The following direction remains unchanged:

- Soma is the durable operating system of an owner-governed autonomous company.
- Cortana is the owner-facing executive interface.
- The company may operate continuously, but worker sessions are short, bounded, interactive and disposable.
- Soma remains canonical authority for company continuity, plans, work, acceptance, evidence and recovery.
- External providers and worker runtimes remain replaceable.
- Multi-agent organisation must earn its coordination cost against a simpler baseline.

No review found a surviving reason to redesign the destination.

## 3. Confirmed architecture correction

The original roadmap attempted to prove the Company Kernel before scheduling the interactive worker substrate required by that proof.

The current task/run plane already owns durable work, process identity, cancellation, recovery and result publication. It does not yet provide the production contract for:

- provider-native session binding;
- mid-package steering and supplied input;
- crash-safe interaction delivery;
- non-terminal controller waiting and continuation;
- explicit provider-session recovery;
- provider child-process identity and orphan proof;
- raw provider usage events;
- exact executive acceptance of a published result for one route-independent outcome.

The accepted provider pilot is evidence that native provider capabilities exist. It is not a production adapter.

Therefore the roadmap begins with:

```text
hierarchical-intelligence organisational contract
        ↓
adversarial interaction-foundation review
        ↓
smallest durable interactive worker substrate
        ↓
V3-1b kernel of one
        ↓
role-scoped worker capability broker
        ↓
collaboration and temporary organisation
```

The owner-accepted authority is [`SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`](SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md).

## 4. Owner decision — progressive lifecycle convergence

The owner rejected both extremes:

```text
consolidate every lifecycle before V3
```

and:

```text
leave every existing lifecycle untouched while V3 adds more
```

The accepted rule is:

> **Consolidate as V3 goes. Every lane must converge the generic lifecycle territory it actually touches, while preserving irreducible domain semantics.**

### Generic lifecycle responsibilities

These should progressively converge into the canonical task/run authority when a V3 lane needs them:

- work admission and accountable ownership;
- queued, running, waiting and terminal meaning;
- interaction and supplied input;
- cancellation;
- retry, route fallback and superseding attempts;
- leases and process identity;
- restart recovery and uncertainty;
- result publication;
- executive acceptance and owner adjudication.

### Domain state that remains domain-specific

Examples include:

- Trading Lab order validation, broker submission and reconciliation facts;
- SSH activation, acknowledgement and rollback facts;
- customer deal, invoice, support and consent states;
- provider-native session identity and protocol cursors.

Those records may link to canonical tasks. They do not become task states merely because work is required to advance them.

## 5. Lane-level authority rule

Every V3 lane must record:

1. authorities touched;
2. generic lifecycle responsibilities moved or projected into the canonical task/run plane;
3. domain state retained outside it and the reason;
4. compatibility bridges introduced or retained;
5. exact retirement condition and owning future lane for every temporary bridge;
6. net change in canonical authority count.

A lane must not close with a new unexplained generic lifecycle authority.

This is progressive convergence, not mandatory deletion. Existing public or durable surfaces remain compatible until a separate owner-approved migration or retirement gate is satisfied.

## 6. Reconciled Claude and Codex findings

### Accepted from Claude

- the interactive worker substrate was missing from the roadmap sequence;
- route changes require an outcome identity above route-specific task idempotency;
- waiting, result acceptance and wrong-route prevention need durable substrate rather than prompt rules;
- workers must not receive the current broad Soma MCP surface;
- the first proof should be smaller than the original multi-department spike;
- the simplest one-executive configuration must be allowed to win.

### Accepted from Codex

- the existing Task → Run authority is extended, not replaced;
- the provider pilot measured capabilities but did not implement integration;
- outcome identity and route-attempt identity must remain separate;
- no global lifecycle consolidation belongs in the V3 critical path;
- role-scoped capability exposure can be added through a separate positive-allowlist broker without redesigning all public gateways;
- V3-1a and V3-1b should defer departments, generic mutation, dashboard product work and the A/B/C organisation comparison.

### Rejected overcorrections

- a preliminary lane that attempts to unify every lifecycle authority;
- treating research, knowledge, SSH or Trading Lab analogues as already-complete Company Kernel authorities;
- preserving all current lifecycle fragmentation indefinitely;
- classifying workflows or supervisors as protected business domains; they are generic lifecycle managers that must project or retire overlapping responsibility when later V3 lanes touch it;
- changing the autonomous-company destination because its first implementation slice is a kernel of one.

## 7. Route-independent outcome authority

The canonical company outcome sits above route-specific tasks:

```text
one WorkPackage outcome
    ├── canonical task attempt A → run A
    └── canonical task attempt B → run B
                         ↓
               one AcceptanceCommit
```

Changing provider, executable profile, argv or model does not change the intended outcome. Each route remains a separate canonical task attempt with its own existing idempotency and evidence.

The proposed outcome identity is based on:

- Mission identity;
- accepted PlanRevision identity;
- versioned canonical intent or exact contract hash;
- canonical target identity, normally an exact ProjectScope resource.

Semantic similarity is not an idempotency mechanism.

## 8. Worker access boundary

The current Soma MCP surface remains owner/executive-facing.

V3-1a and V3-1b workers receive no direct Soma MCP access. A later worker-facing broker must:

- expose positive role-level intent allowlists;
- bind an unforgeable principal to project, task, session and role;
- verify exact gateway, operation and schema identity;
- deny before dispatch;
- call existing internal service functions without becoming another task or run authority.

Discovery filtering alone is not authorisation.

## 9. Corrected first proofs

### V3-1a

Proves one bounded interactive provider session through the canonical task/run authority, including restart, steering/input, waiting, cancellation, usage and zero direct Soma MCP access.

### V3-1b

Proves one Mission, one current PlanRevision, bounded WorkPackages, route-independent outcomes, route-specific canonical task attempts and one crash-safe AcceptanceCommit.

The original department comparison is deferred until the substrate, kernel, cost evidence and golden-task evaluation set exist.

## 10. Final consistency-audit refinements

The final independent consistency audit produced four accepted refinements:

1. **Terminology:** distinguish TaskAdmission, ResultPublication, OutcomeAcceptance, and CharterRatification. Existing `TaskState.ACCEPTED` means admission only.
2. **Checkpoint expiry:** every controller-wait checkpoint has a durable deadline. Expiry may release locks only after the provider worker is confirmed quiescent or terminated; otherwise the task becomes uncertain and ownership is retained.
3. **Provider-session invalidation:** a missing, invalid, or corrupt native session becomes durable uncertainty. Soma does not automatically launch a clean replacement attempt without executive adjudication.
4. **Outcome concurrency:** V3-1B permits one non-terminal route attempt per outcome by default. Any later deliberately parallel candidate topology must be declared before launch and cannot create competing authoritative acceptances.

The audit also confirmed that workflows and supervisors are generic lifecycle managers rather than irreducible domains.

## 11. Deferred owner decisions

The following remain lane-specific decisions rather than implied activation:

- amendment of `AGENTS.md` and the active roadmap before Soma launches bounded provider workers;
- exact outcome-intent vocabulary and normalisation version;
- verifier results eligible for automatic acceptance;
- provider-cost semantics beyond raw native usage and provider-reported USD;
- activation of scheduled autonomous advancement;
- company-global memory and third-party personal-data authority;
- timing and objective for the later A/B/C organisation comparison.

## 12. Implementation authority - 2026-08-15 provenance correction

This reconciliation originally recorded that Arash explicitly activated `V3-1A - INTERACTIVE-WORKER-SUBSTRATE-1`. A later owner review on 2026-08-15 did not accept the generated Company gate chain as sufficient proof that the Autonomous Company roadmap had been unfrozen. This historical statement therefore must not be reused as independent owner-authorisation evidence for later Company implementation.

`V3-1A`, `V3-1B`, and `V3-2` implementation/evidence remain preserved repository history. The owner specifically disputes the activation provenance of `V3-1B` / `V3-2`. The Autonomous Company roadmap is now frozen. No `V3-3` or later Company implementation may begin unless the owner explicitly names and reopens that Company lane. Current sequencing authority is the corrected root [`PLANS.md`](../PLANS.md).
