# SCOPE-FOUNDATION-1 Gate C Activation

**Date:** 2026-07-27
**Status:** owner-approved, executed, and verified, with two proof items unexecuted (see Limitations).
**Scope executed:** exact-identity bootstrap and scoped-write cutover against `runs/soma.sqlite3`.

Executes the procedure in
[`SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md`](SCOPE_FOUNDATION_1_GATE_C_PREPARATION_2026-07-27.md),
authorized as one continuous lane stopping only on a documented stop condition.
No documented stop condition fired.

## Approved identity, applied exactly

| Field | Value |
|---|---|
| `project_id` | `proj_a144f759-1619-4276-9292-28704b6611f4` |
| `project_key` | `soma` |
| `resource_id` | `res_5b67936d-9599-4f08-b817-b3c30564400f` |
| `repo_name` | `soma` |
| canonical repository root | `d:/github/soma` |
| repository identity hash | `1f7c8e8726a452826177d0fb06d08b0e73df3695cd9e52f3a37d9b53cd451441` |
| access mode | `exclusive` |
| lifecycle / scope generation | `active` / `1` |

Both the canonical root and the identity hash were re-derived at execution time
from the reviewed locator and matched the reviewed values. Nothing was inferred.

## Phase 1 - maintenance and fresh evidence

- preflight clean at `6d5845b7d6384f19bdd1694d5d511550ddd889ec`, zero running,
  queued, and launch-pending runs, zero locks;
- server stopped; zero `soma.server` processes and zero port-8000 listeners
  confirmed before any database access;
- backup `runs/gate-c-20260727T195813Z/soma-pre-gate-c-backup.sqlite3`,
  SHA-256 `ad6661de99c6ad7decf2df4e8ac797224ecad24d1d15f3f88fbc0da7b949b900`,
  `131,309,568` bytes;
- fresh baseline: `4,728` runs, `2` tasks, run-ID hash
  `fcd1f180ef2d7ae68ad6a2eb60e37c9df6fea1e442fcb4aaff29d20eeb6b5f84`,
  publication hash `9c4b2961d6845641512fb94c78fe3fdc603c48b222527d34a97871deb8daea16`;
- ProjectScope confirmed at v2 with settings `[0, 0]` and every scope data
  table empty; integrity `ok`; foreign-key violations `0`;
- preview run twice, identical, `ok: true`, `conflicts: []`, `would_apply: true`,
  input hash `772e40251a7b88f42550beddf0f6993985fb156d46d4681f7aeab07c9cbe7c2d`
  matching the reviewed value, and provably changed no live row.

## Phase 2 - bootstrap with enforcement still inactive

Applied twice. All three reviewed hashes reproduced exactly:

- input hash `772e40251a7b88f42550beddf0f6993985fb156d46d4681f7aeab07c9cbe7c2d`;
- outcome hash `019e667a1df73d795564a009d0fc9f7f18f93b08e5248c7b3d9d9703a7a65bc1`;
- evidence event ID `9d86f38841f0bcee291f09514a8dba7a072c7d3330f51f9c0477be9e2b8a17d5`;
- the second apply produced the identical outcome and event identity.

Row counts after bootstrap were exactly one project, one repository resource,
one resource binding, one repository binding, and one bootstrap event, with zero
task reservations, run attempts, quarantine rows, and adjudications. Settings
remained `[0, 0]` and enforcement remained `inactive`, which is the documented
last point at which the fresh backup could simply be restored. Incumbent run and
task identities and the publication hash were unchanged.

## Phase 3 - irreversible cutover

The switch has no public MCP surface, so it was applied store-level with every
writer stopped, and only the scope-aware binary was started afterwards. This
satisfies "no older write-capable process may run concurrently" more strongly
than enabling against a live process would, and the subsequent start is the
restart the procedure calls for.

- `scoped_writes_enabled` and `ever_activated` both `1`;
- enforcement `enforced`;
- exactly one active binding, matching the approved identity field for field;
- no scoped records created by the cutover itself;
- incumbent identities and publication hash unchanged; integrity `ok`;
  foreign-key violations `0`;
- runtime restarted (PID `7508`), capability identity `converged: true` with
  `mismatches: []`, epoch `198835df5c9c-42bdb69d96fb`;
- startup reconciliation `ok` across `job_runs`, `project_scope`, `tasks`,
  `workflows`, `ssh_activation`, and `ssh_activation_coordinator`, with
  `failed: []`, `incomplete: []`, `missing: []`.

## Phase 4 - live controller proof

| Requirement | Result |
|---|---|
| explicit scoped start | task `task_20260727T200740Z_8f8995778083`, run `20260727T200740Z_executable_profile_889ea764`, exit `0` |
| same-project idempotent replay | `created: false`, `idempotent_replay: true`, same task, same run, same hash |
| correct-project task and run reads | status, result, links, run terminal all `ok` with exact scope echoed |
| wrong-project fail-closed access | `project_scope_mismatch` on task status, run status, run output, and cancel |
| unique omitted-project resolution | task `task_20260727T201140Z_98d213ccd993` resolved to the single active binding |
| exact reservation and attachment | every reservation and attempt carries the exact project, resource, and generation `1`, each attached once |
| scoped vs legacy request hash | scoped `551042be...` matches the live task, legacy `6dc479ab...`, differ and stable |
| response budget and publication hash | payload `1,994` within budget `12,288`; `result_published_hash` `8d375ec6...`; `public_result_status: ready` |
| direct Claude MCP | proven; every call in this activation was a direct Claude MCP call with no shell proxy or CLI-as-controller |
| direct ChatGPT MCP | **not executed** - see Limitations |
| direct Codex MCP | **not executed** - see Limitations |

Wrong-project rejection returned no state, no backend reference, and no
artifact data, and left the target task untouched at its existing state version.

## Limitations

Two required proof items were not executed. `direct ChatGPT MCP` and
`direct Codex MCP` require driving external MCP clients, which this lane cannot
do. They are not blocked or failing - they are unattempted. Both clients reach
the same HTTP MCP endpoint and the same scope enforcement demonstrated here, so
no separate code path is implicated, but that is an inference and not a
measurement. Closing Gate C's proof list completely requires exercising those
two clients directly.

## Incident: one unresolved task from a malformed request

The first explicit start omitted `working_directory`, which the executable
profile requires. The backend launch failed with
`ValueError: Arbitrary working-directory policy requires a directory`.

- task `task_20260727T200608Z_8719fe3d9754`;
- backend reference `20260727T200608Z_executable_profile_aa64f982`;
- final state `uncertain`, `recovery_state: unresolved`,
  `recovery_reason: backend_run_record_missing`;
- its run attempt is `recovery_pending` with `run_attachment_incomplete`.

This was a malformed request from the controller, not a Gate C defect, and the
system behaved correctly: the scope reservation attached with the exact
identity, no backend run record was fabricated, and the task was marked
`uncertain` rather than reported as succeeded. It is left in place. Resolving it
would mean quarantine adjudication or disposition, which Gate C explicitly
excludes, so it is recorded here for a separate owner decision.

## Post-activation state

```
ProjectScope schema:   2 / 2
Scoped writes:         enabled
Enforcement:           enforced
ever_activated:        1
Projects:              1
Resources/bindings:    1 / 1 / 1
Bootstrap events:      1
Task reservations:     3
Run attempts:          3   (2 attached, 1 recovery_pending)
Quarantine:            0
Adjudications:         0
Integrity:             ok
Foreign-key check:     0
Push:                  none
```

## Rollback position

A scoped task now exists, so the pre-Gate-C backup must **not** be restored:
that would erase authoritative scope reservations. Per the prepared boundary,
rollback now means stopping writers, disabling scoped mutation to enter
`paused`, retaining the sidecars and bindings, and continuing only with a
scope-aware binary. `runs/gate-c-20260727T195813Z/` is retained as the
pre-cutover reference for identity comparison, not as a restore target.

## Still excluded and unauthorized

Historical assignment, backfill, and quarantine disposition; project-scoped
memory, Obsidian, and `PILOT-MEMORY-1`; Hermes or external-session migration;
worktree, credential, lock-key, workflow, supervisor, SSH, scheduler, and
Trading Lab producer migration; permission tiers; `_pytest-cf1-temp` cleanup;
and push.
