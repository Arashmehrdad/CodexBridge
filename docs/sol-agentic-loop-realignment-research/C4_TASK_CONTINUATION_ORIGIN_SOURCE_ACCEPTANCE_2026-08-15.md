# C4 Task Continuation Origin - Source Acceptance

Date: 2026-08-15
Status: **SOURCE ACCEPTED, NOT LIVE ACTIVATED**
Branch: `lane/memory-integration-foundation-1`
C3 accepted base: `d327a83a59031537948b10d73c2ec4b776ed51ee`
C4 implementation commit: `8dabac7a520385fb5245fe0aa478bd52d7d8c234`

## Gate intent

C4 adds optional continuation origin provenance to the canonical durable Task start path without making continuation identity an authorization mechanism, without copying Task or Run lifecycle truth into the continuation store, and without changing the reasoning-controller boundary.

The accepted public field is:

`continuation_context_ref`

It is the identity of the **current open continuation contract revision**. It records mechanical origin only. It is explicitly not an authorization token, ownership lease, reasoning lease, planner state, or Skill selector.

C4 applies only to canonical durable Task start (`task_action.start`). It does not attach continuation origin to `start_reasoning`, does not add a new gateway, and does not add a new public operation.

## Accepted implementation

### Public model and routing

`TaskDurableCommandStart` now accepts optional `continuation_context_ref` with a bounded scalar contract and public description stating that it records mechanical provenance only and is not authorization.

`server.task_action` forwards the value only for durable Task `start`.

Strict model tests reject `continuation_context_ref` on `start_reasoning`.

### Request identity

Context-free Task starts preserve their existing normalized request hash exactly.

When `continuation_context_ref` is non-empty, the normalized request is wrapped in the dedicated hash domain:

`soma.continuation.task_origin.v1`

The context revision identity therefore participates in Task idempotency.

Consequences:

- same controller request + same payload + same continuation context -> replay of the same Task;
- same controller request + changed continuation context -> deterministic controller request hash conflict;
- same controller request originally created without continuation context cannot later be silently relinked to one;
- legacy no-context callers retain their previous request hashes.

### Lazy continuation dependency

`TaskManager` lazily creates `ContinuationStore` only when continuation origin is actually requested.

A context-free durable Task start does not initialize continuation tables merely by passing through TaskManager. This preserves the opt-in boundary.

### Current/open validation

Before any backend identity reservation for a context-bearing start, TaskManager verifies the submitted revision is the continuation's current revision and the continuation lifecycle is `open`.

Mechanical failures are reported distinctly:

- `stale_continuation_contract`
- `continuation_closed`
- `continuation_context_not_found`
- `invalid_continuation_context_ref`
- `continuation_origin_conflict`
- `continuation_origin_reservation_failed`

A stale, closed, missing, or invalid context is rejected before Task reservation and before backend launch.

### Atomic Task origin association

For a context-bearing durable Task start, one caller-owned `TaskStore.transaction()` (`BEGIN IMMEDIATE`) covers the durable reservation boundary.

Inside that transaction C4 performs, as applicable:

1. controller-request replay/concurrency check;
2. current/open continuation-context validation;
3. ProjectScope Task/Run attempt reservation when ProjectScope is active;
4. canonical Task reservation;
5. ProjectScope Task attachment when active;
6. immutable continuation effect-link insertion for the Task origin.

Only after the transaction commits can backend execution proceed.

This means a newly created Task cannot become durably visible with a half-attached continuation origin. If effect-link insertion fails, the Task reservation rolls back with it.

### ProjectScope composition

C4 composes with the existing ProjectScope reservation transaction rather than creating a second authority.

The scoped acceptance proof verifies that before backend handoff all of the following are already durable:

- canonical Task row;
- ProjectScope Task attachment;
- ProjectScope Run attempt reservation;
- immutable continuation Task-origin effect link.

### Replay and concurrency

The accepted implementation preserves one Task, one immutable origin link, and one backend launch for identical concurrent context-bearing starts.

A six-thread identical-request proof converged on one Task identity, one continuation link, and one backend launch.

Replay never launches another backend and never inserts another origin link.

### Crash and rollback windows

C4 explicitly covers the post-commit/pre-launch crash window.

A synthetic crash after atomic Task+origin commit but before backend launch leaves:

- the same durable Task;
- the same immutable continuation effect link;
- no backend launch.

A retry returns the same Task and does not create a second origin or silently launch a second backend.

A forced continuation-link insertion integrity failure proves the inverse boundary: the transaction rolls back the Task reservation, leaves no origin link, and launches no backend.

### Immutable origin

Task state transitions do not update or copy status into `continuation_effect_links`.

The link remains an immutable origin fact while Task state remains authoritative in the canonical Task plane and Run state remains authoritative in the durable Run plane.

## Compatibility evidence

### Existing Task/gateway compatibility checkpoint

Run:

`20260815T133123Z_executable_profile_9e0cc683`

Result:

- **139 passed**
- Ruff: PASS
- `git diff --check`: PASS

This was executed after the C4 TaskManager path was introduced and before dedicated C4 tests were layered on top. It proved the existing context-free Task plane and gateway behavior still passed.

### Dedicated C4 Task-origin gate

Run:

`20260815T133633Z_executable_profile_f0957e3f`

Result:

- **10 passed, 41 deselected**
- Ruff: PASS

Covered:

- legacy no-context hash preservation;
- atomic current/open Task origin;
- stale and closed rejection before reservation;
- same-context replay;
- missing/different-origin conflict;
- six-way identical concurrency;
- post-commit/pre-launch crash;
- rollback on forced link failure;
- immutable origin through Task state changes;
- dedicated continuation-origin hash domain.

### ProjectScope composition gate

Run:

`20260815T133730Z_executable_profile_b283ceb8`

Result:

- **11 passed, 62 deselected**
- Ruff: PASS

This includes the direct ProjectScope + Task + continuation-origin same-transaction proof.

## Public contract movement

C4 intentionally does not change public gateway or operation counts.

Fresh final source identity run:

`20260815T135149Z_executable_profile_412cd6ac`

Result:

- public gateways: **36**
- operation schemas: **275**
- discovery passes converged: **true**
- operation schema error: empty

Public schema hash:

`0a8619fdfb568afd3721c35cbd6f8ac6163387021d3d9a8e99b290151abf7852`

Public descriptor hash:

`0424fc41754af1e0093d002a2fc1c367f21cebc2ddd92b2455dc0cb338feac67`

Operation inventory hash:

`07724723b5bfd4ebc2d6cef405bd39d8d0dfeece70a61c42f0c9e297c0f80e30`

`task_action.start` operation schema hash:

`dbec910992fba53e7e873a99e6cae6e74bcf1fcc8623029e08850f6b0f62a403`

Input-schema digest:

`08378ecb0d817df9c1a96562ae0a802c00284a9ac45c1e592cc3dff061ac67d7`

Output-schema digest remains:

`d482baa253584213a1922641c84664b1a079899b1bdd88f5231c1d043a890c63`

The operation inventory hash and 36/275 topology therefore remain unchanged from C3. The intentional movement is the existing Task start input/descriptor identity because of the optional provenance field.

## Flat-input completeness fixture correction

Exploratory public run:

`20260815T133916Z_executable_profile_20d047a0`

reached **299 passed / 1 failed** in its broad public batch. The sole failure was:

`tests/test_mcp_flat_input_contract.py::test_tested_inventory_covers_every_public_gateway`

The failure showed that an older flat-input test partition still omitted the two continuation gateways introduced and accepted in C3:

- `continuation_query`
- `continuation_action`

This was a stale test allowlist, not a C4 runtime defect. The fixture was corrected without changing runtime behavior.

Correction proof:

`20260815T134306Z_executable_profile_75826440`

Result:

- **175 passed**

The only stderr was Git's existing LF-to-CRLF working-copy advisory on already-LF/mixed test files. There was no mixed-EOL correctness failure and `git diff --check` remained clean. No newline-only normalization was introduced.

## Final combined acceptance

Final run:

`20260815T134335Z_executable_profile_06717112`

Result:

- **444 passed in 195.61s**
- Ruff: PASS
- `git diff --check`: PASS
- exit code: 0
- single worker lease generation: 1
- no recovery event
- no stale worker

The combined gate covers the C4 Task-origin suite together with the full canonical Task plane, ProjectScope foundation, continuation C1-C3 behavior, public gateway models, flat-input contract, public descriptor/schema identity, metadata, inventory, and discovery behavior selected for this gate.

## Commit-range audit

C3 accepted base:

`d327a83a59031537948b10d73c2ec4b776ed51ee`

C4 implementation:

`8dabac7a520385fb5245fe0aa478bd52d7d8c234`

Exact range:

- **10 files changed**
- **574 insertions**
- **9 deletions**

Files:

- `soma/gateway_models.py`
- `soma/server.py`
- `soma/tasks/manager.py`
- `soma/tasks/models.py`
- `tests/test_canonical_task_plane.py`
- `tests/test_mcp_flat_input_contract.py`
- `tests/test_project_scope_foundation.py`
- `tests/test_public_descriptor_identity.py`
- `tests/test_public_metadata_wiring.py`
- `tests/test_tool_gateway_models.py`

No concurrent `docs/soma-improvement-research/*` file is part of the implementation commit.

## Architecture boundary

C4 does **not**:

- make Soma a semantic planner;
- add a next-action engine;
- add reasoning-phase state;
- add a reasoning lease or model ownership lock;
- infer the meaning of a continuation instruction;
- infer whether a Task should be started;
- copy Task or Run lifecycle state into continuation origin links;
- attach continuation provenance to the reasoning Task path;
- add Skill routing;
- modify direct `run_start` continuation origin behavior (reserved for C5).

Sol / ChatGPT remains the semantic reasoning controller. Soma records mechanical provenance and enforces only the accepted persistence/idempotency contracts.

## Live-state boundary

C4 is accepted at source only.

No Soma restart was performed as part of C4.
No connector Refresh was performed.
No live activation was performed.
No push was performed.
No Codex or model subagent was invoked.

The currently running Soma process remains older than the accumulated F1/C1/C2/C3/C4 source and therefore should not be described as exposing C4 live until a later authorized rollout gate performs the required activation and verification.

## Verdict

**C4 ACCEPTED - SOURCE ONLY.**

The next sequential gate is **C5 - direct single-Run continuation origin association**. C5 is not part of this acceptance and must not be treated as started by this record.
