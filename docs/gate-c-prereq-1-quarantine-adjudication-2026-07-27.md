# GATE-C-PREREQ-1 — Quarantine Adjudication

**Date:** 2026-07-27
**Status:** implemented and tested, then owner-reviewed and returned for one
focused idempotency fix. That fix is implemented as specified — see §3.1.
Awaiting re-review. Nothing outside the fix was widened.
**Unblocks:** `SCOPE-FOUNDATION-1` Gate C, which
[`SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md`](SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md)
records as not approvable until this prerequisite is accepted.

**Owner review:** the terminal-quarantine and supersession design was accepted in principle, but the implementation was not. A repeated idempotency key was treated as a replay solely from its deterministic adjudication ID, so a changed disposition, reason, or successor under that same key returned the first row instead of rejecting a different request. See [`gate-c-prereq-1-owner-review-2026-07-27.md`](gate-c-prereq-1-owner-review-2026-07-27.md); the finding and its closure are in §3.1 below.

**Not activated.** The live store remains at ProjectScope schema **v1**. This
change adds schema **v2**, which is applied only by an explicit owner-approved
activation. Nothing here bootstraps a project, enables scoped writes, classifies
a historical record, or restarts the running server.

---

## 1. The problem this closes

Gate A made quarantine terminal and evidence-preserving on purpose. The
consequence, raised in the Gate A review §5.2 and ratified by the owner, is that
a quarantined task or run attempt had no owner-facing resolution at all: no code
path leaves `quarantined`, so the only remedy was manual SQL. That is not an
operator remedy, and the proposal says so explicitly.

The fix is deliberately *not* an unquarantine. Quarantine stays terminal. What
was missing is a way to **record a decision beside the preserved record**, so
the dead end becomes explicitly resolved rather than silently permanent.

## 2. Design

One additive migration, `project_scope` v2, adding a single table:

```
project_scope_adjudications
  adjudication_id            deterministic sha256 over
                             (domain, project_id, record_kind, record_id, idempotency_key)
  project_id, record_kind, record_id
  disposition                'acknowledged' | 'superseded'
  successor_task_id          required iff superseded, and never equal to record_id
  reason, idempotency_key
  request_hash               normalized fingerprint of the decision this key
                             was used for (see §3.1)
  quarantine_evidence_hash   copied from the preserved quarantine row
  created_at
  UNIQUE(record_kind, record_id)
  UNIQUE(project_id, record_kind, record_id, idempotency_key)
  FK -> projects, FK -> project_scope_quarantine
```

Two dispositions, neither of which revives a record:

- **`acknowledged`** — the owner has seen the dead record and accepts it. The
  operational dead end is now explicit and queryable.
- **`superseded`** — the owner points at an existing, same-project, non-quarantined
  task reservation as the replacement.

Supersession **references** a successor rather than creating one. Task identity
stays with the task store, so no second task, run, process, result, evidence, or
lock authority is introduced — an explicit prerequisite constraint.

`UNIQUE(record_kind, record_id)` is what makes a crash or a race unable to
produce two replacements: the constraint is in the schema, not in application
logic that a restart could re-enter.

## 3. Prerequisite properties and where each is proved

All twelve tests in
[`tests/test_project_scope_quarantine_adjudication.py`](../tests/test_project_scope_quarantine_adjudication.py)
pass.

| Required property | Evidence |
|---|---|
| Quarantined rows never return to an active state | `test_adjudication_preserves_the_quarantined_record` — the quarantine row is compared field-by-field before and after and is identical; both task and attempt remain `quarantined` |
| Owner can create an adjudication or a superseding identity | `test_supersession_requires_an_active_same_project_successor` |
| Original identity and evidence remain immutable | same as row 1, plus an in-transaction assertion that rolls back if the record or its evidence hash moved |
| Requires exact `project_id`, exact identity, reason, idempotency key | `test_invalid_requests_are_rejected_before_any_write`, `test_mcp_surface_is_strict_and_scope_mandatory` |
| Cross-project fails before disclosing or mutating | `test_cross_project_adjudication_fails_without_disclosure` |
| Repeated requests are idempotent | `test_adjudication_is_idempotent_and_single_shot`, plus the two conflict tests in §3.1 |
| Crash/restart cannot create two replacements | `test_concurrent_adjudication_yields_exactly_one_replacement` — two threads race, exactly one wins |
| Evidence queryable without manual SQL | `test_evidence_is_queryable_without_manual_sql` |
| No second authority introduced | `test_no_second_authority_is_introduced` — task, run, and backend-launch counts are unchanged |
| No historical disposition performed | the migration is `CREATE TABLE` + `CREATE INDEX` only and writes no row |

### 3.1 Idempotency conflict — review finding, closed

The owner's acceptance review rejected the first implementation on a real
defect. Reusing one idempotency key with a **materially different** decision
returned the original adjudication as a successful replay:

```
first  : acknowledged / "first decision"          -> written
second : superseded / valid successor / "conflicting decision", same key
returned: acknowledged / replayed=true            <- wrong
```

Changing only the `reason` under the same key behaved the same way. A caller
could therefore believe a different owner decision had been accepted when
nothing was recorded — the most dangerous shape of failure for an operation
whose whole purpose is recording an owner's intent.

The original single-shot check only compared the derived `adjudication_id`,
which is a hash over `(domain, project_id, record_kind, record_id,
idempotency_key)`. Two requests that differ *only* in their decision content
hash identically, so the check could not see them apart. Matching that ID
proves the same key addressed the same record — nothing more.

The fix is the one the review specified. Migration v2 was **amended rather than
superseded by a v3**, which is sound only because no store has ever applied v2;
the live store is at v1 and applying v2 requires an authorization that has not
been given. Re-verified read-only against the live store immediately before
this change was committed:

```
applied versions: [('canonical_task_plane', 1), ('project_scope', 1)]
project_scope_adjudications present: False
```

The new `request_hash` column is a sha256 over a distinct domain string plus
every decision-bearing field: project, record kind and ID, disposition,
successor task ID, and the **normalized** reason. Normalization matters — the
reason is stripped and bounded before hashing, so the same decision written
with incidental whitespace replays instead of falsely conflicting
(`test_reused_key_with_a_different_decision_is_rejected` pins this). A replay
now requires both the adjudication ID *and* the request hash to match; any
divergence raises and names the differing fields, which is diagnostic only —
the gate itself is the single hash comparison.

The column is written once with the row and has no update path, so a stored
decision cannot be retro-fitted to match a later request.

This is fail-closed. A caller that hits the conflict has recorded nothing and
can resubmit under a new key, which the pre-existing single-shot rule then
rejects on the correct grounds — the record is already adjudicated.

The review's probe, re-run against the fix on a disposable store:

```
First request:  acknowledged / 'first decision'
Second (different disposition): REJECTED -> Idempotency key was already used for
  a different decision (differing fields: disposition, successor_task_id, reason)
Second (different reason only): REJECTED -> Idempotency key was already used for
  a different decision (differing fields: reason)
Exact resubmit: acknowledged / replayed=True
Rows on record: [('acknowledged', 'first decision', '')]
```

Every case the review asked to be tested:

| Case | Behaviour | Test |
|---|---|---|
| Same key, identical normalized request | replay, `replayed=true`, no second row | `…different_decision_is_rejected` (whitespace variant), `…is_idempotent_and_single_shot` |
| Same key, changed `disposition` | rejected, naming the fields | `…different_decision_is_rejected` |
| Same key, changed `reason` only | rejected | `…different_decision_is_rejected` |
| Same key, changed `successor_task_id` | rejected | `…different_successor_is_rejected` |
| Different key after adjudication | rejected as single-shot (unchanged) | `…is_idempotent_and_single_shot` |
| Concurrent identical requests | both callers get the same accepted decision, exactly one row | `…resolve_by_request_fingerprint` |
| Concurrent conflicting requests | one accepted, one rejected, exactly one row | `…resolve_by_request_fingerprint` |

`test_reused_key_with_a_different_successor_is_rejected` also pins that an
identical resubmission still replays, so the conflict check cannot silently
harden into "no idempotency at all". Each conflict test asserts the stored row
is unchanged and still the only one on record.

The gap existed because the original idempotency test covered only the matching
replay and the different-key case, and never varied decision content under a
fixed key. That axis is now tested per field, and under concurrency.

### Non-disclosure detail

A cross-project request and a request for a nonexistent identity produce the
**same** error string, asserted by equality in the test. A caller therefore
cannot use the error to discover whether another project's identity exists.

## 4. MCP surface

Additive, strict, and project-mandatory:

- `task_query(operation="quarantine", project_id=…)` — project-scoped quarantine
  evidence with any adjudication attached.
- `task_action(operation="adjudicate_quarantine", …)` — the decision.

Unlike the Gate A fields, `project_id` here is **required**, not optional. There
is no project-less form of either operation, so quarantine evidence cannot be
reached through the owner-controller compatibility path.

## 5. Activation status and its visible consequence

`PROJECT_SCOPE_SCHEMA_VERSION` is now `2`. The live store is at `1`.

Until an owner-approved activation applies v2, the live runtime will report:

```json
"project_scope": { "schema_version": 1, "target_schema_version": 2,
                   "up_to_date": false,
                   "missing_tables": ["project_scope_adjudications"] }
```

This is intended. A pending activation should be **visible** rather than silent,
which is the same principle as the STABILIZE-1.4 reconciliation work. Calling
either new operation against a v1 store returns a clear message naming the
pending activation rather than an obscure SQL error
(`test_adjudication_requires_schema_v2`).

Applying v2 is a Gate-B-shaped event: stop, back up, rehearse on a disposable
copy, apply once, verify, restart. It is not authorized by this record.

## 6. CF1 operation inventory

Adding two gateway operations tripped three declared-contract guards, which is
the inventory machinery working as designed rather than incidental breakage:

- `test_inventory_matches_every_current_mcp_discriminator` — the CF1 inventory
  must enumerate every live discriminator;
- `test_task_gateways_are_discoverable_with_strict_request_unions` — the task
  gateways pin their exact operation sets;
- `test_capability_identity_binds_public_schema_and_discovery_cache` —
  capability identity stopped converging while the inventory disagreed with the
  runtime.

Both operations are now registered in
[`soma/cf1_gateway_operation_inventory.py`](../soma/cf1_gateway_operation_inventory.py)
with byte budgets, pagination behaviour, and notes, and
`CF1_GATEWAY_OPERATION_INVENTORY_VERSION` is bumped from
`cf1.3.gateway-operations.v14` to `v15`. That constant is pinned by a test on
purpose: an inventory change must be acknowledged deliberately, not absorbed
silently.

## 7. Validation

- `tests/test_project_scope_quarantine_adjudication.py`: **15 passed**
  (12 at first review, plus the three added by the §3.1 fix)
- `tests/test_project_scope_foundation.py`: **19 passed**
- affected gateway/task/capability modules: **172 passed**
- full suite: **2070 passed, 35 skipped** — the pre-lane baseline of 2055 plus
  exactly the 15 tests in this lane, with no regression

The first full-suite run of the fix reported `1 failed, 2069 passed`. The
failure was `test_chat_footprint_acceptance.py::
test_projection_overhead_and_full_retrieval_performance`, a wall-clock
assertion (`excess_median <= 0.5`, measured `16.09`). Three focused suites were
running against the same machine at the time. It passes in isolation and on a
rerun of the full suite with nothing else competing, and it measures chat
projection overhead, which shares no code with the scope store. Recorded here
rather than quietly re-run: the test is timing-sensitive under load, which is
worth knowing independently of this lane.
- ruff check across `soma/` and changed tests: passed

Three existing tests were updated, all of them declared-contract pins rather
than behavioural assertions:

1. `init_db() == [1]` encoded "exactly one migration exists". It now asserts
   against the declared migration list, so a further ordered version cannot
   silently weaken it.
2. The task gateway operation sets gained `quarantine` and
   `adjudicate_quarantine`.
3. The pinned inventory version moved to `v15`.

No behavioural assertion was relaxed to make this land.

## 8. What this does not do

It does not approve Gate C, apply schema v2 to any live store, restart the
server, bootstrap a project, enable scoped writes, dispose of any historical
record, or push.

The §3.1 fix in particular was kept to the bounds the review set: it touches
migration v2's table definition, the adjudication write and replay path, and
its tests. It does not extend into permissions, historical disposition, Gate C
bootstrap, memory, or unrelated cleanup.
