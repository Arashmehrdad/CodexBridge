# V3-1B-OUTCOME-ACCEPTANCE-1 — Acceptance Result

**Date:** 2026-08-14  
**Status:** ACCEPTED / CLOSED  
**Gate:** `docs/V3_1B_OUTCOME_ACCEPTANCE_1_GATE_2026-08-14.md`  
**Implementation commit:** `a6e4d0634b0c6624f7364f8d0e49ea2774811130`  
**Public-fixture alignment commit:** `120908b6671fd1dcd5b1d1edd7cdc0a485a880a1`  
**Provider activation:** unchanged / disabled  
**Push:** none

## Result

The Kernel-of-One now has one bounded internal OutcomeAcceptance authority. It can create exactly one immutable `AcceptanceCommit` for one WorkPackage outcome only after exact current company, plan, scope, Task/backend and publication evidence has been named and mechanically verified. Process success or backend completion alone never accepts an outcome.

Accepted outcomes:

- one request names the exact Company, Mission, current PlanRevision, WorkPackage, outcome, WorkPackageAttempt, canonical Task, backend kind/reference, ProjectScope project/resource/generation, Mission kernel version, named acceptance authority, acceptance basis and publication hashes;
- the acceptance authority must equal the immutable Company executive and the Mission/WorkPackage accountable and acceptance authority chain;
- the WorkPackage must belong to the exact asserted current PlanRevision;
- ProjectScope must contain the exact active, current-generation, non-quarantined Task/backend attempt and both bindings must be attached;
- canonical Task state must be `completed`, recovery-free, `result_published`, and its Task kind/executor/backend/result/evidence identity must match the selected backend;
- durable-command acceptance requires one exact canonical Run with `status='completed'`, `exit_code=0`, no safety/recovery/publication error, published result metadata, exact result hash, exact `public_result_source_sha256`, and exact Task terminal-evidence linkage;
- reasoning acceptance requires a definitely bound provider operation, terminal success, valid versioned output contract, published EvidenceSubmission, evidence index, provider binding/provenance/raw-evidence identities, no uncertain cancellation/binding, and exact Task result/evidence linkage;
- reasoning acceptance does not create or require a synthetic canonical Run; `backend_ref` remains subordinate execution identity beneath the canonical Task and `run_id` is `NULL`;
- one exact request replay returns the existing immutable AcceptanceCommit without incrementing Mission state again, including after later scope archival/replanning;
- changed material under the same controller request fails closed; a second request for the same outcome fails closed;
- concurrent identical requests converge to one create plus replay, while conflicting requests produce one winner;
- AcceptanceCommit insertion and Mission `kernel_state_version` compare-and-set are one `BEGIN IMMEDIATE` transaction and injected faults leave old-or-new state only.

## Provider-neutral schema migration

Company Kernel schema advances from v3 to v4. The migration translates historical durable-Run AcceptanceCommit rows deterministically:

- `backend_kind='soma_durable_run'`;
- `backend_ref=run_id`;
- historical `run_id` remains unchanged;
- every incumbent acceptance fact is preserved rather than inferred or rewritten;
- the pre-v4 optional empty acceptance-basis hash remains reconstructable for immutable history, while every new OutcomeAcceptance request requires a real SHA-256 basis hash;
- migration failure rolls the table, row, triggers and migration marker back to exact v3 state.

A separate copied-live migration proof backed up the current live SQLite database to a disposable file and migrated only that copy. Evidence:

- Company Kernel version before: `0`;
- version after: `4`;
- migrations applied: `[1, 2, 3, 4]`;
- second migration call: `[]`;
- 52 incumbent non-kernel tables retained identical row fingerprints;
- acceptance translation check: exact;
- SQLite integrity: `ok`;
- foreign-key violations: `0`.

The live database was not migrated or otherwise mutated by that proof.

## Immutable dependency-proof compatibility

Provider-neutral fields would have changed the historical content hash of a durable-Run AcceptanceCommit if the old evaluator simply hashed the expanded model. That would invalidate immutable `accepted_outcome` proof references.

The accepted fix preserves the exact v1 AcceptanceCommit hash contract for durable-Run acceptances by hashing the historical payload under `soma.company_kernel.acceptance_commit.v1`. Reasoning acceptances use the new full provider-neutral payload under `soma.company_kernel.acceptance_commit.v2`. Tests verify both exact digests.

## Validation

Focused OutcomeAcceptance proof after the final exact-plan/evidence tightening:

- `50 passed`;
- Ruff: clean.

Broad adjacent Company Kernel / dependency / ProjectScope / reasoning / canonical Task / protected-tool proof:

- `328 passed`;
- Ruff: clean.

Full repository validation after correcting two stale test-only public-schema identity fixtures:

- `3107 passed`;
- `35 skipped`;
- `1 xfailed`;
- `0 failed`;
- `git diff --check`: clean.

The two fixture corrections reflect the already-live 32-tool public input contract (`f7dc8e9296b62e6f82843ba64a8a67078a4d9ff6dd1ecf7a6659f36097fab4a4`); output-schema and operation-inventory identities remained unchanged. They did not change runtime behavior.

Soma lightweight self-check is green. Fresh Task capabilities still advertise only `durable_command` with backend `soma_durable_run`; the production reasoning backend is not active. `config.yaml` contains no `reasoning:` override, so `ReasoningRuntimeConfig.enabled` remains its default `false`.

## Authority delta

New authority is deliberately narrow: the internal Company Kernel can record one exact named-authority outcome acceptance and increment Mission kernel state atomically after canonical evidence validation.

It does not gain semantic auto-acceptance, provider/model authority, new Task/Run launch authority, a public Company gateway, `reconcile_one`, scheduling, delegation, worker-facing Soma MCP, external mutation, deployment or push.

No Codex/provider generation was used. No Soma restart or connector refresh was required because this package does not activate a public Company capability or production reasoning route.

## Next package

Advance to a separately bounded V3-1B projection + `reconcile_one` package: derive bounded Company/Mission/Plan/WorkPackage state from accepted canonical facts and permit one explicit `reconcile_one` transition at the already-defined owner-turn/package-completion boundary. Public `company_query` / `company_action` gateways and live Company Kernel activation remain later gates.
