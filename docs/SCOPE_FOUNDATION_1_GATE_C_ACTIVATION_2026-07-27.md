# SCOPE-FOUNDATION-1 Gate C Activation

**Date:** 2026-07-27
**Status:** owner-approved, executed, fully controller-proven, and recovery-closed.
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
| direct ChatGPT MCP | proven after activation review: direct scoped `task_action.start` replay returned `created: false`, `idempotent_replay: true`, the same task/run, and request hash `551042be...` |
| direct Codex MCP | proven through the attached CodexBridge Soma plugin: exact scoped replay and status read, with no shell, CLI, subprocess, new reservation, run attempt, or backend execution |

Wrong-project rejection returned no state, no backend reference, and no
artifact data, and left the target task untouched at its existing state version.

## Controller-route note

All three controller proofs are now complete. Claude proved the direct MCP route
during activation. ChatGPT later replayed the exact scoped request through its
connected Soma tools. Codex then used the attached CodexBridge Soma plugin,
without a shell, CLI, or subprocess, to replay the same request and read status.

The Codex proof establishes the attached CodexBridge plugin route. It does not
independently establish that the running Codex task loaded the separately
installed global `soma` MCP namespace. That distinction is retained as routing
provenance, not as an open Gate C proof item.

## Incident closure: malformed proof task terminally superseded

The first explicit start omitted `working_directory`, which the executable
profile requires. The backend launch failed before creating a durable run and
the canonical task correctly entered `uncertain / unresolved` rather than
claiming success. Leaving that record non-terminal was an operational loose end,
so a narrow public recovery operation was added and exercised.

`task_action.resolve_recovery` is exact-project, state-version guarded, and
idempotent. In one main-store transaction it:

- moves only an unresolved missing-backend task to canonical `failed`, phase
  `recovery`, with recovery `resolved`;
- preserves the absent backend and leaves result/evidence references empty;
- terminally quarantines the task reservation and its run attempt;
- writes immutable quarantine evidence and a single `superseded` adjudication;
- links the completed successor to the failed task with `supersedes`;
- appends one recovery-disposition event;
- commits every authority change together or rolls all of them back.

Implementation and focused fixes:

- `b27e8133826ebcc230753e740f4182a7e64a843a` - atomic recovery surface;
- `d8fb79835e4f6c67cf1c15f02a7dabe4b76c4279` - exact scope ownership query;
- `b4c22ee28d2aa5901db80efe4b6915e326dcc747` - correct non-enumerating error classification.

Validation evidence:

- focused recovery cases: `6 passed` in
  `20260727T212346Z_executable_profile_2fe670b5`;
- full canonical-task and quarantine pair: `63 passed` in
  `20260727T212408Z_executable_profile_aff5d79c`;
- ProjectScope foundation and discovery/contract matrix: `321 passed` in
  `20260727T212454Z_executable_profile_9ab55a0a`;
- Ruff: clean in `20260727T212656Z_executable_profile_0a51daed`;
- exact-current-store disposable rehearsal: every check passed in
  `20260727T212831Z_executable_profile_43a66ca8`.

Soma restarted on build
`1632dc6ed8950c5e7dfa10ef5af83c30c71350260f9c1fd778c625d28c109546`;
all ten self-checks passed and ProjectScope remained enforced. The live HTTP MCP
`tools/list` exposed the reviewed strict `resolve_recovery` branch. The current
ChatGPT conversation's attached tool card retained an older cached schema and
rejected the new operation client-side, so a FastMCP client called the same live
HTTP MCP endpoint directly after asserting the schema. No private manager call,
manual SQL mutation, or store bypass was used.

Live execution and identical replay passed in
`20260727T213459Z_executable_profile_9d884557`:

- target `task_20260727T200608Z_8719fe3d9754` is now terminal `failed`, state
  version `3`, recovery `resolved`;
- missing backend `20260727T200608Z_executable_profile_aa64f982` remains absent;
- reservation and attempt are `quarantined` under the exact project/resource and
  scope generation `1`;
- successor `task_20260727T200740Z_8f8995778083` remains completed and unchanged;
- adjudication ID
  `5426bdebddec1b8e7c9d1c63e02178082055bf7faa46e3a5c31a2a8b0ff5f507`;
- request hash
  `e78d65a2db7997fa4ee99cd06bffa90b304578db6d8f9565c4d93292ce2710f9`;
- quarantine evidence hash
  `9f2159c4cc3d4fbafa0e8f929eb81fbdf038c4537ff5458e7b7f019cd9edeab2`;
- replay returned the same adjudication with `replayed: true`.

Independent read-only durable verification passed in
`20260727T213703Z_executable_profile_16b42010`: one quarantine row, one
adjudication, one supersedes link, one recovery event, no fabricated backend or
result, integrity `ok`, and zero foreign-key violations. The incident is closed;
it is no longer an active or unresolved task.

## Post-activation state

```
ProjectScope schema:   2 / 2
Scoped writes:         enabled
Enforcement:           enforced
ever_activated:        1
Projects:              1
Resources/bindings:    1 / 1 / 1
Bootstrap events:      1
Task reservations:     3   (2 attached, 1 quarantined)
Run attempts:          3   (2 attached, 1 quarantined)
Quarantine:            1
Adjudications:         1   (superseded)
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
