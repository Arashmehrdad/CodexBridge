# V3-1B-SCHEMA-MODELS-1 — Company Kernel Schema and Models Gate

**Date:** 2026-08-02
**Status:** active; bounded source implementation gate
**Parent lane:** `V3-1B — Kernel of One`
**Architecture:** [`V3_1B_KERNEL_OF_ONE_ARCHITECTURE_PROPOSAL_2026-08-02.md`](V3_1B_KERNEL_OF_ONE_ARCHITECTURE_PROPOSAL_2026-08-02.md)
**Acceptance basis:** [`V3_1B_KERNEL_OF_ONE_ARCHITECTURE_ACCEPTANCE_AUDIT_2026-08-02.md`](V3_1B_KERNEL_OF_ONE_ARCHITECTURE_ACCEPTANCE_AUDIT_2026-08-02.md)
**Runtime activation:** not authorised
**Push:** not authorised

## 1. Objective

Implement only the additive Company Kernel v1 schema, immutable source models, deterministic identity/hash helpers required by those models, ordered migration registration, and copied-live migration proof.

This package establishes durable structure. It does not expose company behavior.

## 2. Authorised outcome

The source may add the minimum coherent implementation for:

- Company;
- Mission;
- immutable accepted PlanRevision;
- immutable bounded WorkPackage;
- immutable WorkPackageAttempt linkage fields;
- immutable AcceptanceCommit fields;
- immutable bounded reconciliation receipts;
- component schema-version discovery and migration to Company Kernel v1;
- strict models and canonical serialization/hash validation for the exact architecture contract.

The migration must be additive and idempotent. Existing ProjectScope, Task, Run, interaction, publication, workflow, supervisor and domain records remain unchanged.

## 3. Authority invariants

The package is unacceptable if it:

- adds WorkPackage or attempt execution status, process, PID, lease, lock, result, publication, cancellation or recovery authority;
- changes ProjectScope, Task, Run, WorkerSubstrateStore or ResultPublication semantics;
- lets a caller create the Company root executive authority;
- permits Mission owner or acceptance authority to differ from the configured Company executive in v1;
- permits PlanRevision, WorkPackage or AcceptanceCommit authority to escape that Mission ceiling;
- adds a second task, run, workflow, scheduler or acceptance lifecycle;
- backfills or converts workflow/supervisor records;
- creates or launches a canonical Task or Run;
- exposes company query/action gateways or advertises runtime capability.

## 4. Required migration proof

Acceptance requires all of the following:

1. fresh database migration reaches Company Kernel v1;
2. a copied live database migrates successfully;
3. applying the migration again is idempotent;
4. `PRAGMA integrity_check` returns `ok`;
5. `PRAGMA foreign_key_check` returns no rows;
6. existing non-migration tables and rows are unchanged by content and count;
7. no workflow/supervisor backfill occurs;
8. all proposed unique keys, composite foreign keys and immutability triggers exist;
9. invalid cross-Mission, cross-Company, cross-outcome and authority-ceiling inserts fail;
10. a valid same-company, same-mission, single-executive chain succeeds;
11. existing migrations and fresh/copy-live convergence tests remain green;
12. absent or older Company Kernel schema is reported honestly and never treated as active capability.

## 5. Required model proof

Models must:

- reject unknown fields;
- preserve exact opaque identifiers rather than infer scope;
- validate fixed-length hashes and bounded contract fields;
- keep route-neutral WorkPackage/outcome material separate from route-specific attempt material;
- exclude provider, profile, argv, environment, session, Task ID and Run ID from route-independent outcome identity;
- be immutable after construction where the architecture declares immutable facts;
- provide deterministic canonical serialization and exact replay hashes;
- contain no public operation that mutates the live kernel.

## 6. Validation and evidence

The package closes only with:

- focused schema/model tests;
- copied-live migration evidence with pre/post compatibility census;
- negative authority and relationship tests;
- migration idempotency and rollback tests;
- adjacent ProjectScope/Task/Run/schema regression tests;
- the full relevant repository test gate;
- an implementation result document recording files, migrations, runs, incidents and exact acceptance decision;
- a clean worktree, local commit and refreshed canonical repository knowledge.

## 7. Explicit exclusions

This gate does not authorise:

- Company/Mission bootstrap through a public or live runtime action;
- plan selection or WorkPackage creation APIs;
- attempt reservation or Task/Run coordination;
- AcceptanceCommit creation APIs;
- projections or `reconcile_one` behavior;
- public `company_query` or `company_action` gateways;
- real providers, provider accounts or worker-facing Soma MCP;
- departments, roles, assignments, teams or delegation;
- scheduled autonomy or background reconciliation;
- external mutation, deployment, production activation, restart, connector refresh or push.

## 8. Stop conditions

Stop and return to architecture if implementation requires a duplicate lifecycle field, weakens the fixed executive ceiling, cannot migrate copied-live data without modifying existing authority rows, or requires any excluded runtime behavior.

## 9. Exit

Produce an accepted schema/models implementation and copied-live migration proof. Only that acceptance may activate the next separately bounded V3-1B package. No later V3-1B behavior is implied by this gate.
