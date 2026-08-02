# V3-1A Interaction Foundation Architecture Review — Acceptance Audit

**Date:** 2026-08-02  
**Audited package:** `V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1`  
**Verdict:** accepted; `V3-1A-INTERACTION-COMMANDS-1` may resume under the corrected scope below.  
**Push:** not authorised.

## 1. Executive verdict

The adversarial review is accepted. It defines one coherent authority model for durable controller interaction without introducing a second Task, Run, checkpoint, delivery, or acceptance lifecycle.

The accepted design is feasible in Soma's existing shared `runs/soma.sqlite3` authority:

- `TaskStore.transaction()` already exposes one `BEGIN IMMEDIATE` transaction over the canonical task database;
- canonical task-command operations already support connection-scoped reads and writes;
- `WorkerSubstrateStore` uses the same database and is structurally forbidden from owning Task or Run state;
- additive worker-substrate migrations can extend subordinate message and attempt evidence without rewriting historical records;
- canonical task state already contains non-terminal `awaiting_controller`;
- exact task, run, ProjectScope, session, and checkpoint identities already exist and can be validated in one transaction.

Acceptance of the design does not claim that the current inert substrate implements it. The current v1 substrate intentionally lacks the atomic command/interaction coordinator, complete contract hash, generic message class and organisational references, delivery-attempt claim, and central wait/resume transition policy. Those are the authorised implementation deltas for the next package.

## 2. Transaction and authority ownership

One narrow coordinator must open the shared main-store transaction and call connection-scoped primitives owned by their canonical stores:

- `TaskStore` reserves the canonical task command and retains command ownership;
- `WorkerSubstrateStore` reserves the subordinate message envelope and delivery intent in the same transaction;
- the coordinator validates Task, Run, ProjectScope, session, checkpoint, cancellation, expiry, supersession, sender, recipient, and optional mandate references;
- no subordinate store writes canonical Task or Run state;
- one separate central transition policy applies evidence-proven wait/resume effects through canonical store methods.

A crash therefore leaves both command and interaction reservation durable, or neither. Filesystem payload bytes may be written content-addressed before the transaction, but remain inert and unreferenced unless the transaction commits.

## 3. Message identity and complete contract hash

One message identity is subordinate to exactly one canonical command. Its complete normalized contract must include at least:

- project, task, run, session, and optional checkpoint identity;
- sender and recipient references;
- message class and public command kind;
- optional mandate/reference version;
- requested task state version;
- payload reference, hash, and byte count;
- adapter/protocol capability evidence required for delivery;
- caller idempotency key.

The complete contract hash, not payload hash alone, decides replay equivalence. Identical replay returns the original command/message identities. Any changed contract field is an explicit conflict and creates no second command, message, attempt, or send.

## 4. Delivery-attempt state machine

The accepted subordinate state model distinguishes message disposition from transport-attempt evidence.

Message evidence may be reserved, acknowledged, rejected, uncertain, cancelled, expired, or superseded. A separate attempt record must distinguish:

1. reserved and never attempted;
2. attempt durably claimed by one sender;
3. dispatch outcome unknown;
4. acknowledged;
5. rejected;
6. prevented or invalidated by cancellation, expiry, or supersession.

Only a reserved, still-authorised message may receive its first attempt claim. An outcome-unknown attempt is never automatically resent. Acknowledgement is durable evidence, not permission by itself to resume canonical work.

## 5. Wait/resume transition authority

`awaiting_controller` remains non-terminal. Entering it must atomically correlate the canonical Task and Run, one open checkpoint, the exact session binding, deadline policy, retained ownership state, and transition evidence. It must not publish a terminal result, set terminal timestamps, or release repository/resource authority.

Supplying input may resume the same Task, Run, session, and checkpoint only through one central transition policy after exact acknowledgement and after rechecking:

- task state version;
- open checkpoint identity;
- session and ProjectScope identity;
- cancellation, expiry, revocation, supersession, and owner/authority version precedence;
- technical execution resumability.

A crash after acknowledgement but before canonical resume is repaired idempotently from durable evidence without sending again.

## 6. Message-class effects

The generic envelope does not make every message lifecycle-bearing.

- `command`: may direct work only under its exact command policy.
- `decision`: may resolve only its correlated checkpoint through the central transition policy.
- `progress_report`: informational; cannot resume, cancel, publish, or accept.
- `evidence_submission`: appends evidence; cannot imply substantive acceptance.
- `outcome_proposal`: requests review; cannot close work.
- `cancellation` and future `revocation`: outrank pending communication but do not claim an already-active process or external action has stopped.

The first public package exposes only `steer` and `supply_input`; the internal envelope must nevertheless preserve typed semantics and future sender/recipient/mandate compatibility.

## 7. Precedence contract

The linearized precedence is:

1. cancellation or future revocation denies new protected action;
2. supersession or ownership/mandate-version change invalidates stale authority;
3. expiry prevents late checkpoint resolution;
4. exact state, session, checkpoint, sender, and recipient validation;
5. delivery acknowledgement;
6. central canonical resume decision.

A late acknowledgement remains evidence but cannot reopen cancelled, terminal, expired, superseded, differently versioned, or technically unrecoverable work. Message state never releases locks, publishes results, or proves descendant termination.

## 8. Adversarial scenario verdicts

- **A — identical concurrent input:** one command, one message, one payload identity, at most one attempt claim; both callers receive the same identities.
- **B — conflicting replay:** first complete contract remains authoritative; conflict is explicit; no second send.
- **C — crash before claim:** durable evidence proves never attempted; one later claim is allowed only after all authority checks still pass.
- **D — crash after claim:** outcome becomes unknown/uncertain; no blind resend.
- **E — acknowledgement before resume:** recovery completes only the local canonical transition, idempotently and without resend, after rechecking precedence.
- **F — cancellation before send:** cancellation prevents an attempt claim and checkpoint resolution.
- **G — cancellation during send:** late acknowledgement cannot resume; process containment remains with Run authority.
- **H — stale parent decision:** exact mandate/checkpoint mismatch preserves evidence but cannot affect replacement work.
- **I — revocation during active action:** new protected actions stop; active execution remains unresolved until canonical containment proves outcome.
- **J — informational report:** stored and correlated; no lifecycle or acceptance effect.
- **K — wrong authority relationship:** rejected or retained as unauthorised evidence; cannot direct or resume work.
- **L — ownership handoff:** exactly one effective owner version; old-owner messages cannot become newly authoritative.
- **M — technical parent failure:** logical input cannot fabricate process readiness or release ownership.
- **N — evidence versus acceptance:** provenance and completeness may be proven; substantive acceptance remains outside the substrate.

Every scenario has one unambiguous authoritative outcome and requires no second generic lifecycle manager.

## 9. Bounded implementation scope

The resumed package may change only the smallest coherent surface needed for:

- additive worker-substrate schema/models for message contract identity and transport attempts;
- connection-scoped TaskStore and WorkerSubstrateStore reservation primitives;
- one command-interaction coordinator;
- one central wait/resume/precedence policy;
- additive `steer` and `supply_input` task commands and public schemas;
- deterministic stand-in transport and crash/race fixtures;
- non-terminal Run/Task waiting projections and recovery;
- focused compatibility, secrecy, concurrency, cancellation, expiry, and protocol tests;
- completion evidence and public contract inventory updates.

It must not implement real provider execution, teams, departments, permanent roles, capability delegation, V3-1B, generic external mutation, workflow/supervisor migration, worker-facing Soma MCP, production activation, deployment, or push.

## 10. Required corrections to the paused gate

Before or with product code, `V3_1A_INTERACTION_COMMANDS_1_GATE_2026-07-31.md` must explicitly require:

1. a generic typed internal message envelope while keeping public commands narrow;
2. sender, recipient, and optional mandate/version references;
3. one complete command-contract hash;
4. connection-scoped command and interaction inserts under one shared transaction;
5. a separate durable transport-attempt claim/evidence record;
6. central precedence and wait/resume policy rather than caller interpretation;
7. no blind retry from an outcome-unknown attempt;
8. informational classes that cannot mutate lifecycle or imply acceptance;
9. cancellation/revocation precedence that does not fabricate process containment;
10. explicit authority-delta evidence confirming zero new generic lifecycle authority.

## 11. Stop conditions and final disposition

Return to architecture review if implementation requires a second task/run/checkpoint/delivery lifecycle, direct subordinate Task/Run writes, blind uncertain resend, lock release without quiescence proof, acknowledgement-driven resume outside the central policy, live provider execution, or broader organisation/company-kernel state.

With the corrections above, `V3-1A-INTERACTION-COMMANDS-1` is authorised to resume as the sole implementation package. Progression after this package is determined by its objective acceptance gate; routine engineering acceptance does not require a separate owner ceremony. Irreversible external actions, push, production activation, or product-direction changes still require explicit owner instruction.
