# V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1 — Adversarial Contract Review

**Date:** 2026-07-31  
**Status:** active documentation-only review gate; interaction product implementation is paused.  
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`  
**Organisational contract:** [`SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`](SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md)  
**Runtime baseline:** `06cc054ed3dfe2dac877dc8ea67875522a8463ad`  
**Push:** not authorised.

## 1. Purpose

Prevent the interaction gate from repeating the process-control patch loop.

The process corrective chain showed that local evidence plus duplicated caller interpretation creates recurring leaks. The interaction foundation crosses TaskStore, RunStore, WorkerSubstrateStore, checkpoints, sessions, payload storage, transport attempts, cancellation, expiry, public commands, and future organisational communication. Product implementation remains paused until one narrow authority contract proves that callers cannot independently resend, resume, revoke, release ownership, publish, or close work.

This gate changes documentation and scope only. It does not authorise runtime schemas, migrations, gateways, message delivery, provider launch, teams, mandates, or company-kernel state.

## 2. Review question

Can `V3-1A-INTERACTION-COMMANDS-1` implement the smallest durable communication substrate required by future hierarchical intelligence while preserving canonical Task → Run authority and preventing duplicated lifecycle interpretation?

The answer must be demonstrated through explicit invariants and adversarial scenarios before coding resumes.

## 3. Minimal authorised substrate

The eventual implementation gate may cover only:

- exact project, task, run, sender, recipient, session, checkpoint, and optional mandate references;
- one generic content-addressed message envelope;
- message class with command versus informational semantics;
- caller idempotency and complete contract hash;
- atomic canonical command plus subordinate interaction reservation;
- durable transport-attempt claim;
- acknowledged, rejected, uncertain, cancelled, expired, and superseded delivery evidence;
- genuinely non-terminal controller waiting;
- exact checkpoint correlation and evidence-proven resume;
- cancellation, revocation, expiry, supersession, and stale-message precedence;
- one central proof-to-lifecycle transition policy;
- deterministic stand-in transport only.

The gate must not implement the full organisational model.

## 4. Required authority separation

### Canonical Task authority

Owns task identity, command reservation, state version, task state, checkpoint lifecycle, and public command projection.

### Canonical Run authority

Owns execution state, lease, repository ownership, cancellation, recovery, terminal transition, and ResultPublication.

### Worker substrate

Owns subordinate session binding, message payload identity, transport-attempt evidence, acknowledgement, deadline, expiry, usage, and provider-child evidence. It may not write canonical task or run state directly.

### Organisational references

Sender, recipient, typed relationship, accountable owner, and mandate identity are durable references required for future organisation. This gate does not create permanent roles, teams, departments, capability grants, or acceptance state.

### Acceptance authority

Substantive acceptance remains outside this gate. Presence of evidence does not imply that the evidence establishes correctness.

## 5. Required central primitives

### 5.1 Atomic command-interaction reservation

One shared transaction or authority-preserving coordinator must reserve:

- canonical task command;
- complete command-contract hash;
- caller idempotency key;
- content-addressed payload identity;
- subordinate interaction identity;
- exact task, run, session, checkpoint, sender, recipient, and mandate references;
- initial delivery state proving that no transport attempt has started.

A crash may leave all of these records or none of them. It may not leave an orphan canonical command or orphan interaction intent.

### 5.2 Durable transport-attempt claim

Before transport begins, one sender must durably claim the attempt. Recovery must distinguish:

- reserved and never attempted;
- attempt claimed but dispatch not proven;
- send may have occurred and outcome is unknown;
- acknowledged;
- rejected;
- cancelled, expired, or superseded.

An outcome-unknown attempt is never blindly resent.

### 5.3 Canonical wait-resume transition authority

One narrow transition policy alone may coordinate task, run, checkpoint, session, command, and interaction evidence.

No ordinary caller may independently decide that an acknowledgement is sufficient to resume work.

### 5.4 Typed message semantics

The envelope is generic; lifecycle effects are not.

- `command` may direct work only after exact acknowledgement rules are satisfied;
- `decision` may resolve one correlated checkpoint and resume only through the central transition policy;
- `progress_report` is informational and cannot change lifecycle;
- `evidence_submission` appends evidence and cannot imply acceptance;
- `outcome_proposal` requests review and cannot close work;
- `cancellation` or future `revocation` outranks pending communication.

The first runtime gate may expose only `STEER` and `SUPPLY_INPUT`, but its internal contract must not make every future message resumptive.

## 6. Adversarial scenarios

### Scenario A — identical concurrent input

Two controllers submit the same idempotency key and identical full command contract concurrently.

Required result:

- one canonical command;
- one interaction;
- one payload identity;
- at most one transport-attempt claim;
- both callers receive the same durable identity;
- no duplicate send.

### Scenario B — conflicting replay

The same idempotency key is reused with a different payload, message class, state version, session, checkpoint, sender, recipient, or mandate reference.

Required result:

- one winner remains durable;
- the conflict is explicit;
- no second interaction or send exists.

### Scenario C — crash before attempt claim

Reservation commits and Soma crashes before transport is claimed.

Required result:

- state proves the message was never attempted;
- recovery may claim it once if cancellation, expiry, supersession, and state-version checks still permit.

### Scenario D — crash after attempt claim

The sender claims the attempt and crashes before proving whether dispatch occurred.

Required result:

- state becomes or remains outcome-unknown;
- automatic resend is forbidden;
- checkpoint remains non-terminal;
- recovery requires exact transport/provider evidence or adjudication.

### Scenario E — acknowledgement before canonical resume

The exact interaction is acknowledged, then Soma crashes before checkpoint resolution and task/run resume.

Required result:

- recovery may complete the local projection idempotently;
- it does not send again;
- cancellation, expiry, revocation, supersession, or a changed task version still wins.

### Scenario F — cancellation before send

Cancellation linearises after reservation but before attempt claim.

Required result:

- no transport attempt may begin;
- input cannot resolve the checkpoint;
- task remains under cancellation authority.

### Scenario G — cancellation during send

Cancellation linearises while transport outcome is uncertain.

Required result:

- a late acknowledgement cannot resume work;
- task remains cancellation-pending or cancelled;
- execution and repository ownership follow existing containment proof, not message state.

### Scenario H — stale parent decision

A decision is valid for mandate version 3 and checkpoint A. Before delivery, the work is superseded by mandate version 4 or replacement checkpoint B.

Required result:

- the old decision remains durable evidence;
- it cannot resolve B or resume the replacement work;
- no best-effort matching by text or semantic similarity is allowed.

### Scenario I — revocation while an action is active

A future mandate is revoked while the child has already started an external or process action.

Required result:

- every new protected action is denied from the revocation linearization point;
- the active action is not presumed stopped;
- cancellation, containment, or recovery owns the unresolved operation;
- a late child acknowledgement cannot reactivate authority.

The first interaction implementation need not create mandates, but its message and precedence contract must not prevent this later rule.

### Scenario J — informational report

A child submits progress or evidence while waiting.

Required result:

- the report is stored and correlated;
- checkpoint and task/run state do not change;
- no resume occurs;
- no acceptance is implied.

### Scenario K — wrong authority relationship

A peer or technical supervisor sends a decision that only the directing authority may issue.

Required result:

- the envelope may be durably rejected or stored as unauthorised evidence;
- it cannot resolve the checkpoint or direct work.

The first gate may use a minimal sender/recipient reference rather than full authority graphs, but it must preserve the ability to enforce typed relationships later.

### Scenario L — ownership handoff

A future accountable owner transfer occurs while a question is open.

Required result:

- exactly one owner is current before and after the atomic transfer;
- the old owner cannot issue a new authoritative decision after transfer;
- an already-recorded response remains evidence but must match the effective authority version before use.

### Scenario M — technical parent failure

The process supervisor dies or execution becomes uncertain while the logical parent supplies input.

Required result:

- logical input cannot fabricate operational readiness;
- the task remains recovery-pending or uncertain until technical execution authority proves a resumable state;
- no lock release or terminal publication is inferred from organisational communication.

### Scenario N — evidence versus acceptance

A child submits all required evidence references and claims success.

Required result:

- Soma may prove references, hashes, provenance, and required-review presence;
- no substantive acceptance is created automatically;
- acceptance remains a later authority transition.

## 7. Binding invariants

Implementation may resume only with a design where:

1. one transaction reserves canonical command and subordinate interaction;
2. one durable claim controls each transport attempt;
3. uncertain attempts are never blindly resent;
4. one central policy applies wait, resume, cancellation, expiry, supersession, and stale-message precedence;
5. informational messages cannot change lifecycle;
6. acknowledgement alone cannot override a newer canonical state;
7. task, run, session, checkpoint, sender, recipient, and mandate references remain exact and opaque;
8. the substrate cannot directly mutate canonical task/run state;
9. no caller independently releases locks, publishes results, or resumes execution from interaction evidence;
10. future revocation can deny new protected actions without claiming active execution stopped;
11. future ownership transfer can be atomic without redesigning message identity;
12. substantive acceptance remains outside the interaction substrate.

## 8. Contract-review acceptance gate

This documentation gate closes only when an independent review confirms:

- every scenario has one unambiguous authoritative outcome;
- no scenario requires a second task, run, checkpoint, delivery, or acceptance lifecycle;
- the proposed transaction boundary is feasible in the existing shared SQLite authority without letting WorkerSubstrateStore own Task/Run state;
- public `STEER` and `SUPPLY_INPUT` can remain narrow projections over the generic internal envelope;
- delivery-attempt state distinguishes never-attempted from outcome-unknown;
- cancellation and stale-state precedence are central rather than copied across callers;
- the implementation file/authority surface is bounded;
- product implementation can proceed without teams, departments, permanent roles, capability delegation, real providers, or V3-1B.

## 9. Required review report

The independent review must report:

1. transaction and authority ownership;
2. exact message identity and contract hash;
3. delivery-attempt state machine;
4. wait/resume transition table;
5. message-class effects;
6. cancellation, expiry, supersession, and future revocation precedence;
7. sender/recipient and future mandate compatibility;
8. each adversarial scenario verdict;
9. implementation scope and excluded files/authorities;
10. stop conditions;
11. whether `V3-1A-INTERACTION-COMMANDS-1` may be reactivated for product implementation.

## 10. Disposition

- organisational research: closed;
- target organisational contract: owner-accepted;
- this adversarial architecture review: active;
- `V3-1A-INTERACTION-COMMANDS-1` product implementation: paused;
- process-identity foundation: remains accepted;
- real provider execution, teams, company kernel, capability broker, production activation, deployment, and push: inactive and unauthorised.
