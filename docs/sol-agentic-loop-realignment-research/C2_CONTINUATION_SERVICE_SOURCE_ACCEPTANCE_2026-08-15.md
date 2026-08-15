# C2 Continuation Service Source Acceptance - 2026-08-15

## Verdict

**SOURCE ACCEPTED, NOT LIVE ACTIVATED.**

C2 implements the internal bounded continuation service/resume projection over the accepted C1 continuation persistence layer and the existing canonical Task/Run read authorities.

C2 does not add a public gateway, does not add an operation, does not alter the continuation persistence schema, does not restart Soma, and does not activate continuation functionality in the running MCP service.

Implementation commit:

`ed4b5b0beaa64ac6187dc418d83554d4cb9ea74b`

Subject:

`Implement C2 continuation resume service`

Implementation commit range from accepted C1 HEAD `3f1501beceb17fe426d4e933b4294b4af053b20d` contains exactly four files:

- `soma/continuations/__init__.py`
- `soma/continuations/service.py`
- `soma/continuations/store.py`
- `tests/test_continuation_service.py`

Diff stat:

`4 files changed, 883 insertions(+)`

No unrelated concurrent research file is part of the implementation commit.

---

## Planning authority

C2 implements Phase C2 from:

`docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_IMPLEMENTATION_PLAN_2026-08-15.md`

with the architecture constraints rechecked against:

`docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_FINAL_AUDIT_2026-08-15.md`

The governing C2 principle remains:

> Soma returns bounded mechanical continuation material plus current canonical effect truth. Sol/ChatGPT performs semantic reconciliation and chooses what to do next.

No semantic planner, next-action engine, reasoning state machine, or second reasoning model was introduced.

---

## C2 service boundary

The new internal `ContinuationService` composes three existing authorities that all use the same main Soma database:

- `ContinuationStore`
- `TaskStore`
- `RunStore`

The constructor verifies that all three resolve to the same `runs/soma.sqlite3` path.

C2 remains a read/composition layer. It does not take ownership of Task state, Run state, worker lifecycle, continuation persistence, or effect execution.

No C2 schema migration is required. The accepted C1 persistence component and its four tables remain unchanged.

---

## Resume projection

The C2 resume projection is versioned as:

`continuation.resume.v1`

A bounded resume response contains:

### Continuation identity

- continuation ID
- human label
- lifecycle
- created/updated/closed timestamps

### Governing context

- current `continuation_context_ref`
- current contract revision ID and revision number
- current free-form instruction text or durable reference
- content hash
- provenance class/reference
- revision creation timestamp

### Sol handoff

- newest immutable handoff, when present
- free-form handoff text
- handoff content hash
- contract revision under which the handoff was authored
- sequence number and timestamp

The handoff remains opaque semantic material. C2 does not parse it into required reasoning fields.

### Contract mismatch fact

C2 deterministically returns:

`contract_changed_since_handoff`

This is true exactly when the newest handoff's immutable contract revision differs from the continuation's current governing contract revision.

C2 does not interpret what that mismatch means. Fresh Sol must reconcile the old handoff with the current governing instruction.

### Associated effects

The resume bundle contains a bounded page of continuation origin links with current Task/Run projections fetched at read time.

The origin relation remains mechanical only:

`continuation + contract revision -> canonical Task/Run effect`

C2 does not copy canonical effect lifecycle state into continuation persistence.

### Retrieval metadata

The resume bundle provides bounded history metadata and opaque continuation-bound pagination cursors for deeper handoff/effect inspection.

Default history page size:

`20`

Maximum history page size:

`100`

The resume call can choose a smaller bounded effect page without dumping complete continuation history into fresh Sol context.

---

## Task projection authority

For a linked canonical Task, C2 reads current truth through `TaskStore` at projection time.

The bounded projection includes mechanical fields such as:

- state
- phase
- state version
- result reference/hash
- evidence reference
- recovery state/reason/reconciled timestamp
- updated/started/ended timestamps

C2 deliberately does **not** derive or expose an `objective_complete` conclusion from terminal Task state.

A terminal Task means only what canonical Task authority says about that Task. It does not mean the owner objective or continuation is complete.

---

## Run projection authority

For a linked canonical Run, C2 reads current truth through `RunStore` at projection time.

It uses the bounded Run summary projection plus the existing bounded public-result snapshot.

The C2 Run projection includes current mechanical facts such as:

- status
- current phase
- state version
- summary/error/safety-failure flag
- recovery reason
- exit code
- started/ended timestamps
- bounded public result publication/status data

C2 does not expose authoritative raw `result_json` as part of the resume projection.

Run lifecycle and recovery remain solely RunStore/JobManager authority.

---

## Missing and corrupt historical targets

C2 preserves continuation origin history even when a linked historical target can no longer be projected normally.

If the canonical Task/Run target is absent, the origin link remains present and the canonical projection is marked:

`projection_status = missing`

If the target exists but current canonical projection fails conservatively, the origin link remains present and the canonical projection is marked:

`projection_status = unavailable`

with only a bounded mechanical error type.

C2 never deletes the origin link, silently relinks it, or manufactures replacement state.

Acceptance includes an intentionally deleted historical Run target and an intentionally corrupt historical Task state row.

---

## History and cursor contract

C2 adds mechanical count/page primitives to `ContinuationStore` without changing C1 persistence semantics.

Handoffs are paged newest-first by immutable sequence number.

Effect links are paged newest-first by the deterministic tuple:

`created_at DESC, link_id DESC`

Service cursors are opaque checksum-bound base64url payloads carrying only mechanical pagination position.

A cursor is bound to:

- cursor version
- continuation ID
- history collection (`handoffs` or `effects`)
- mechanical page position

A cursor from one continuation cannot be replayed against another continuation.

The C2 service also explicitly distinguishes:

- an existing continuation with empty history; from
- a syntactically valid but nonexistent continuation.

The latter remains a `Continuation not found` error rather than being projected as empty history.

---

## Lifecycle read behavior

C2 resume/history remains readable after a continuation is completed or cancelled, as required by the C1/C2 contract.

Closing a continuation affects whether new continuation-sensitive writes are permitted; it does not erase historical semantic re-entry material or current effect projections.

Acceptance explicitly proves resume after completion.

---

## Concurrent handoffs

C2 does not infer semantic supersession between concurrent handoffs.

C1 preserves both immutable records with monotonic sequence identities. C2 history returns both, and resume selects the mechanically newest handoff while retaining bounded history retrieval for earlier records.

Acceptance concurrently writes two handoffs and proves both remain retrievable.

---

## Explicit semantic exclusions

Source scans of `soma/continuations` found no implementation of:

- `recommended_next_action`
- `next_step`
- `reasoning_phase`

The C2 acceptance test recursively checks that the resume projection contains none of:

- `recommended_next_action`
- `next_action`
- `next_step`
- `reasoning_phase`
- `pending_action`

C2 does not decide which tool Sol should call, whether the handoff is still semantically correct, whether a terminal effect completes the objective, or which current-world facts should be re-read.

---

## Targeted final C1+C2 gate

Final targeted run after all C2 hardening:

`20260815T125147Z_executable_profile_fe8b8de7`

Environment:

- Python: `C:\Users\arash\AppData\Local\Programs\Python\Python311\python.exe`
- `PYTHONPATH=D:\Github\TradingLab\src;D:\Github\Soma`

Result:

- **29 passed in 4.94s**
- Ruff: **All checks passed**
- `git diff --check`: **PASS**
- exit code: **0**

This targeted suite covers C1 persistence, C1 shared-schema coexistence, and all final C2 service behavior.

---

## Final broad acceptance gate

Final broad run on the exact source later committed as `ed4b5b0b...`:

`20260815T125212Z_executable_profile_300fd9f7`

Result:

- **499 passed in 211.79s**
- Ruff: **All checks passed**
- `git diff --check`: **PASS**
- exit code: **0**
- lease generation: **1**
- launch attempts: **1**
- no worker stale condition
- no recovery reason
- no safety failure

The broad gate combines C1/C2 with the shared/current authorities C2 depends on, including:

- RunStore
- Run public projections
- public result materialization/gateway behavior
- canonical Task plane
- ProjectScope foundation/quarantine behavior
- public gateway models/inventory
- public descriptor identity
- CF1 operation inventory
- MCP action discovery
- flat input contract tests

No shared-authority regression was observed.

---

## Fresh source public identity

Fresh-process source identity after the final C2 acceptance run:

`20260815T125612Z_executable_profile_3d0cf162`

Result:

- public gateways/tools: **34**
- operation schemas: **264**
- discovery passes converged: **true**
- operation schema error: empty

Hashes remain exactly the accepted F1/C1 source values:

Public schema:

`f233334aa321d4cb8621c46777d49b4c2eb8a7db3fe010e96f384d45eaef54b0`

Public descriptor:

`2197483f531081738a5fc2a1560dcb1cad49b89568762970da8494557371528a`

Operation inventory:

`71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`

This is the expected C2 result: internal composition changed while public topology and public contract identity did not move.

Public continuation gateways remain deferred to C3.

---

## Line-ending audit note

The targeted runs emitted Git warnings that the working-copy LF form of:

- `soma/continuations/__init__.py`
- `soma/continuations/store.py`

would be converted to CRLF the next time Git's current Windows `core.autocrlf` behavior touches those files.

This is non-blocking for C2 because:

- both files were already LF C1 files before C2;
- C2 did not introduce mixed line endings;
- managed patch newline diagnostics reported no mixed-EOL defect;
- `git diff --check` passed;
- repository `.gitattributes` does not impose a contrary general EOL contract.

C2 deliberately did not create a giant newline-only conversion diff merely to silence this advisory warning.

---

## Concurrent work preservation

During C2, a separate `docs/soma-improvement-research/` research lane continued creating untracked documents.

By the final pre-commit audit, Iterations **01 through 14** were present as concurrent untracked work.

They were treated as protected throughout C2.

None is part of implementation commit `ed4b5b0beaa64ac6187dc418d83554d4cb9ea74b`.

The implementation commit range proves exactly four C2 files and no concurrent research contamination.

---

## Activation boundary

C2 is **not live activated**.

No Soma service restart was performed.

No connector Refresh was requested or performed.

No public continuation gateway was registered.

No public capability count was changed.

No push was performed.

No Codex or provider subagent was used.

The running Soma service therefore remains on the older live process identity until a separately authorized activation stage.

---

## Final C2 classification

**C2 - SOURCE ACCEPTED, NOT LIVE ACTIVATED.**

Accepted properties:

- bounded resume composition exists;
- current governing contract is returned;
- newest free-form Sol handoff is returned without semantic parsing;
- contract revision mismatch since handoff is mechanically detectable;
- linked Task/Run effects are projected from current canonical authorities;
- missing/corrupt historical targets are handled conservatively without erasing origin history;
- handoff/effect history is bounded and cursor-paginated;
- concurrent handoffs remain preserved;
- closed continuations remain readable;
- no semantic next-action field or reasoning state machine exists;
- public Soma topology remains 34 gateways / 264 operation schemas;
- C3 public continuation gateway work has **not** started.
