# GATE-C-PREREQ-1 — Quarantine Adjudication

**Date:** 2026-07-27
**Status:** implemented and tested. Awaiting owner acceptance.
**Unblocks:** `SCOPE-FOUNDATION-1` Gate C, which
[`SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md`](SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md)
records as not approvable until this prerequisite is accepted.

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
| Repeated requests are idempotent | `test_adjudication_is_idempotent_and_single_shot` |
| Crash/restart cannot create two replacements | `test_concurrent_adjudication_yields_exactly_one_replacement` — two threads race, exactly one wins |
| Evidence queryable without manual SQL | `test_evidence_is_queryable_without_manual_sql` |
| No second authority introduced | `test_no_second_authority_is_introduced` — task, run, and backend-launch counts are unchanged |
| No historical disposition performed | the migration is `CREATE TABLE` + `CREATE INDEX` only and writes no row |

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

- `tests/test_project_scope_quarantine_adjudication.py`: **12 passed**
- `tests/test_project_scope_foundation.py`: **19 passed**
- affected gateway/task/capability modules: **172 passed**
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
