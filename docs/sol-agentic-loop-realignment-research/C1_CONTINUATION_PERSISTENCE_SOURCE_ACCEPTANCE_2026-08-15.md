# C1 Continuation Persistence Source Acceptance - 2026-08-15

## Verdict

**SOURCE ACCEPTED, NOT LIVE ACTIVATED.**

C1 implements the internal persistence foundation for Sol semantic continuation and stops before C2 service/public integration.

No Soma service restart, connector refresh, public gateway activation, Codex use, subagent use, or push was performed.

## Authority

Implementation authority:

- `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_IMPLEMENTATION_PLAN_2026-08-15.md`, Phase C1.
- `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_FINAL_AUDIT_2026-08-15.md`.
- `docs/sol-agentic-loop-realignment-research/iteration-30-final-synthesis-minimal-sol-semantic-reentry-2026-08-15.md`.
- `docs/sol-agentic-loop-realignment-research/iteration-31-repository-proof-run-idempotency-and-effect-linking-2026-08-15.md`.

F1 prerequisite was already source-accepted before C1:

- implementation `d6f51f01875660eb2593df50db8a76dd34f85bef`;
- acceptance `7f7a5522ae58c9ea6a9a99ac2961a07c38218dd1`.

The canonical project-memory contract was versioned separately before C1:

- `e876974837fdb3640887d78f0781b3654cc4c3ad` - `Record canonical project memory contract`.

## C1 implementation commit

Commit:

`8797c94214e9eddd85c4c5b8700b5092a0649e97`

Subject:

`Implement C1 continuation persistence foundation`

Exact commit range from `e876974837fdb3640887d78f0781b3654cc4c3ad`:

- 6 files;
- 1,657 insertions;
- no unrelated files.

Files:

- `soma/continuations/__init__.py`
- `soma/continuations/models.py`
- `soma/continuations/schema.py`
- `soma/continuations/store.py`
- `tests/test_continuation_store.py`
- `tests/test_continuation_schema_coexistence.py`

## Persistence authority

C1 uses the existing main Soma SQLite authority:

`runs/soma.sqlite3`

It does not introduce a second database or external semantic state store.

Schema component:

`sol_semantic_continuation`

Target schema version:

`1`

Migration name:

`minimal_sol_semantic_continuation`

The migration uses the existing component-versioned `soma_schema_migrations` ledger, applies transactionally, is replay-safe, and coexists with existing Run, canonical Task, and ProjectScope persistence.

## Exact four-table kernel

C1 creates exactly the four accepted continuation concerns:

1. `controller_continuations`
2. `continuation_contract_revisions`
3. `continuation_handoffs`
4. `continuation_effect_links`

No continuation command journal, semantic router, decision table, phase state machine, source frontier, Skill state, or model scratchpad table was added.

### `controller_continuations`

Owns only:

- continuation identity;
- optional label;
- lifecycle: `open | completed | cancelled`;
- current contract-revision pointer;
- creation replay identity/hash;
- timestamps and terminal closure replay metadata.

Closing/cancelling a continuation does not cancel, reinterpret, or mutate linked Task/Run effects.

### `continuation_contract_revisions`

Contract revisions are immutable history records with:

- opaque `contract_revision_id`;
- owning `continuation_id`;
- parent revision;
- monotonically increasing revision number;
- exactly one of free-form instruction text or instruction reference;
- content hash;
- explicit provenance class/reference;
- stable controller request ID and normalized request hash;
- creation timestamp.

The model-facing `continuation_context_ref` is the opaque contract revision ID itself.

A contract update validates the supplied current context and performs an atomic compare-and-set of the continuation's current revision pointer.

### `continuation_handoffs`

Handoffs are immutable, bounded, free-form text records.

They carry:

- opaque handoff identity;
- continuation and governing contract-revision identity;
- monotonic sequence number;
- free-form handoff text;
- content hash;
- replay request ID/hash;
- timestamp.

There are no required semantic headings or structured reasoning fields. C1 does not parse handoff meaning and does not store chain-of-thought.

### `continuation_effect_links`

Effect links record only mechanical origin/provenance:

`continuation + contract revision -> canonical Task or Run effect`

They do not copy effect status, result, recovery state, or lifecycle authority.

The schema enforces one continuation origin per canonical effect through unique `(effect_kind, effect_id)` identity.

The store verifies that the referenced canonical Task/Run exists in the shared main SQLite database before creating a link.

## C1 store contract

Implemented internal store behaviors:

- atomic continuation open + first governing contract revision;
- stable request replay/conflict for immutable writes;
- context-ref resolution;
- `current + open` guard for continuation-sensitive writes;
- contract revision append with atomic pointer CAS;
- immutable free-form handoff append and bounded history reads;
- latest-handoff read;
- connection-scoped effect-link insertion for future C4/C5 composition;
- canonical Task/Run target validation;
- origin-conflict rejection;
- idempotent complete/cancel lifecycle closure;
- history/context reads remain available after closure.

Transactions are short and do not span Sol reasoning, owner interaction, remote calls, or worker execution.

## Important replay ordering

For immutable record writes, replay lookup occurs before stale/closed guards.

Therefore a response-lost retry for an already-written immutable record can recover the original record even if the continuation subsequently changed contract revision or was closed.

A genuinely new write under an old context ref remains rejected as stale.

## Open continuation invariant

A continuation is not durably opened without its first contract revision.

`open_continuation` atomically inserts:

- the continuation row; and
- revision 1;

using a deferred foreign-key relation for the current-revision pointer.

This matches the accepted research rule: open a continuation with its first governing contract revision.

## Shared-authority compatibility

C1 directly proves coexistence with existing Soma authority rather than relying on separate test databases.

`tests/test_continuation_schema_coexistence.py` verifies:

- `TaskStore` and `ContinuationStore` address the same `runs/soma.sqlite3`;
- migration ledger contains canonical Task plane versions 1 and 2 plus continuation version 1;
- a real canonical Task can be mechanically linked from inside `TaskStore.transaction()`;
- Task truth remains owned by TaskStore and unchanged by the link.

A separate Run effect test proves continuation closure leaves canonical Run state/input unchanged.

## Forbidden semantic machinery audit

Direct source searches under `soma/continuations` returned zero hits for:

- `next_step`
- `reasoning_phase`
- `active_skill`
- `source_frontier`
- `continuation_commands`

C1 therefore preserves the accepted "four boring authorities" design and does not recreate a Soma reasoning engine.

## Test evidence

### Fresh-database smoke

Run:

`20260815T122733Z_executable_profile_d4714ac9`

Result:

- exit 0;
- schema component `sol_semantic_continuation` at version 1;
- exact four tables present;
- no missing tables;
- atomic open + first contract revision succeeded.

### Initial C1 mechanical gate

Run:

`20260815T122842Z_executable_profile_17b9b7d7`

Result:

- 14 C1 tests passed;
- Ruff passed;
- `git diff --check` passed;
- exit 0.

This covered migration, replay/conflict, CAS, concurrent revision update, handoff persistence, lifecycle closure, post-close reads, Run effect origin, and caller-owned rollback.

### Shared SQLite regression gate

Run:

`20260815T122908Z_executable_profile_d940eb46`

Suites included:

- continuation store;
- RunStore;
- canonical Task plane;
- ProjectScope foundation and quarantine adjudication;
- Task interaction actions.

Result:

- 123 passed in 40.56s;
- Ruff passed;
- `git diff --check` passed;
- exit 0.

### Public-surface negative proof

Run:

`20260815T123006Z_executable_profile_ffe3b896`

Suites included:

- continuation store;
- public descriptor identity;
- public gateway inventory;
- CF1 gateway-operation inventory;
- tool gateway models.

Result:

- 136 passed in 166.99s;
- Ruff passed;
- `git diff --check` passed;
- exit 0.

### Direct Task coexistence gate

Run:

`20260815T123505Z_executable_profile_3cab0ba6`

Result:

- 16 C1/coexistence tests passed in 2.13s;
- Ruff passed;
- `git diff --check` passed;
- exit 0.

### Final combined C1 acceptance sweep

Run:

`20260815T123525Z_executable_profile_d2cc0e8f`

Combined suites included:

- both C1 persistence/coexistence suites;
- RunStore;
- canonical Task plane;
- ProjectScope foundation/quarantine;
- Task interaction actions;
- public descriptor identity;
- public gateway inventory;
- CF1 gateway-operation inventory;
- tool gateway models.

Result:

- **247 passed in 200.95s**;
- Ruff passed;
- `git diff --check` passed;
- exit 0;
- one worker/lease; no recovery event.

## Fresh source public identity

Fresh-process source identity run:

`20260815T123957Z_executable_profile_20cf117b`

C1 correctly produces no public topology change beyond the already accepted F1 source contract:

- public gateway/tool count: **34**;
- operation schema count: **264**;
- operation schema error: empty;
- discovery passes converged: true;
- public schema hash: `f233334aa321d4cb8621c46777d49b4c2eb8a7db3fe010e96f384d45eaef54b0`;
- public descriptor hash: `2197483f531081738a5fc2a1560dcb1cad49b89568762970da8494557371528a`;
- operation inventory hash: `71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`;
- operation inventory gateway count: **34**.

`run_start` operation hashes remain the F1 values, including unchanged excluded variants:

- `run_start.powershell`: `a20c7d64460204f4b8def5bb07977316896e391282cdbd0e0fd31e91bc5b0e24`;
- `run_start.remote_powershell`: `439a9e6f1a23b1d636bded9634faa49aee4f8bcaf898702272913ff4363a56c2`;
- `run_start.hermes_companion`: `6f2968303820e17c9834b56fc9d415bddefe74c847c857040e67926f5fcf4594`;
- `run_start.powershell_group`: `683c294968eb5719b5d19411d6928f7e407be0596cd389a7dc51219276cc753a`;
- `run_start.hermes_service`: `17ffb09310432c11e6666ad3a0c7bb23d014dd9263b03fc31d8945668c10265a`.

This is the required C1 result: persistence source exists, but there is no C1 public gateway or operation yet.

## Concurrent-work protection

During C1, separate untracked `docs/soma-improvement-research/` work continued to appear.

At C1 implementation commit time, iterations 01 through 10 were present as unrelated untracked files.

They were treated as protected concurrent work and were not edited, staged, or committed by C1.

The C1 implementation commit range proves exactly six intended files and no contamination.

## Live/runtime boundary

C1 is **not live activated**.

The running Soma process still predates the already source-accepted F1 contract. A restart/activation was intentionally not performed during F1 or C1.

C1 therefore does not claim that continuation persistence is reachable through the currently running public MCP service.

That activation/public wiring belongs to later programme gates, not C1.

## Acceptance classification

C1 is accepted as an internal source foundation because it mechanically proves:

- one main durable SQLite authority;
- exactly four continuation persistence concerns;
- additive/replay-safe component migration;
- atomic open + first revision;
- immutable contract revisions and free-form handoffs;
- current-revision CAS and stale-ref rejection;
- write rejection after close while reads remain available;
- record replay/conflict behavior;
- connection-scoped Task/Run origin linking;
- no copied effect lifecycle truth;
- no semantic reasoning state machine;
- no public topology expansion;
- compatibility with Run, Task, ProjectScope, and public contract tests.

**Final verdict: SOURCE ACCEPTED, NOT LIVE ACTIVATED.**

Next programme stage after explicit authorization: **C2 - continuation service composition.**
