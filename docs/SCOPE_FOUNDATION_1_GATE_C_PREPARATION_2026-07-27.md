# SCOPE-FOUNDATION-1 Gate C Preparation

**Date:** 2026-07-27  
**Status:** prepared for owner identity review, but not authorized or executed.  
**Live state:** ProjectScope v1 is installed, empty, and `inactive`; scoped writes are disabled.  
**Execution blocker:** `GATE-C-PREREQ-1` must provide an explicit owner-only quarantine adjudication or supersession path before Gate C can be approved.

## Decision requested later

Gate C will require a separate owner decision covering all of the following together:

1. approve the exact immutable project and resource IDs below;
2. accept the exact normalized repository identity and exclusive binding;
3. confirm that `GATE-C-PREREQ-1` has been implemented, tested, and accepted;
4. authorize one bootstrap and scoped-write cutover using the reviewed procedure;
5. keep historical disposition, memory, Obsidian, Hermes, other run producers, and push outside Gate C.

This preparation does not grant any of those permissions.

## Proposed exact identity manifest

| Field | Proposed value |
|---|---|
| `project_id` | `proj_a144f759-1619-4276-9292-28704b6611f4` |
| `project_key` | `soma` |
| `resource_id` | `res_5b67936d-9599-4f08-b817-b3c30564400f` |
| `resource_kind` | `repository` |
| `repo_name` | `soma` |
| repository root input | `D:\Github\Soma` |
| canonical repository root | `d:/github/soma` |
| repository identity hash | `1f7c8e8726a452826177d0fb06d08b0e73df3695cd9e52f3a37d9b53cd451441` |
| access mode | `exclusive` |
| initial lifecycle | `active` |
| initial scope generation | `1` |

The opaque IDs were generated once for this review package. They are proposals, not inferred identities. Folder names, repository names, paths, conversations, and historical records do not authorize them.

## Live bootstrap preview

A live read-only `ProjectScopeStore.preview_bootstrap()` was executed twice using the exact manifest above.

Evidence run: `20260727T164356Z_executable_profile_e44caaed`

Results:

- preview `ok: true`;
- conflicts: `[]`;
- `would_apply: true`;
- input hash: `772e40251a7b88f42550beddf0f6993985fb156d46d4681f7aeab07c9cbe7c2d`;
- both previews were identical;
- every project, resource, binding, reservation, quarantine, and bootstrap-event table remained at zero rows;
- `scoped_writes_enabled = 0`, `ever_activated = 0`;
- ProjectScope remained schema v1 and enforcement `inactive`.

No live row or setting was changed.

## Disposable exact-ID cutover rehearsal

The current Gate B store was copied with SQLite's online backup API into a disposable directory. The exact proposed manifest was then exercised only on that copy.

Evidence run: `20260727T164558Z_executable_profile_645e5444`

Expected deterministic evidence:

- bootstrap input hash: `772e40251a7b88f42550beddf0f6993985fb156d46d4681f7aeab07c9cbe7c2d`;
- bootstrap outcome hash: `019e667a1df73d795564a009d0fc9f7f18f93b08e5248c7b3d9d9703a7a65bc1`;
- bootstrap evidence event ID: `9d86f38841f0bcee291f09514a8dba7a072c7d3330f51f9c0477be9e2b8a17d5`;
- repeated bootstrap produced the same outcome and event identity;
- one project, one repository resource, one resource binding, one repository binding, and one bootstrap event existed;
- zero task reservations, run attempts, and quarantine rows existed;
- enabling scoped writes produced enforcement `enforced`;
- disabling them afterwards produced enforcement `paused` with `ever_activated = 1`;
- integrity check returned `ok`;
- foreign-key check returned zero rows.

Windows deferred deletion of the disposable SQLite file until the verifier process exited. Follow-up cleanup run `20260727T164633Z_executable_profile_51dc7f12` removed it and confirmed `REMAINING_GATE_C_TEMP_ITEMS=0`. This was a temporary-file cleanup issue, not a bootstrap or integrity failure.

## GATE-C-PREREQ-1 - quarantine adjudication or supersession

Gate A acceptance deliberately made quarantine terminal and evidence-preserving. Current production code can enter quarantine but contains no owner operation that resolves the operational dead end without manual SQL.

Before Gate C approval, a narrow prerequisite must prove:

- quarantined rows are never changed back to `reserved`, `attached`, or another active state;
- the owner can explicitly create an adjudication or a replacement/superseding task/run identity;
- the original quarantined identity and evidence remain immutable;
- the operation requires exact `project_id`, exact quarantined identity, a reason, and an idempotency key;
- cross-project requests fail before disclosing or mutating the quarantined record;
- repeated requests are idempotent;
- crash/restart cannot create two replacements;
- the resulting evidence is queryable without manual SQL;
- no second task, run, process, result, evidence, or lock authority is introduced;
- no historical disposition is performed.

A focused implementation and acceptance commit is required. Gate C must not be approved merely because the live quarantine table is currently empty.

## Gate C execution procedure after the blocker closes

### Phase 1 - maintenance and fresh evidence

1. Confirm a clean tracked worktree, no active or launch-pending runs, no workers, and no operation locks.
2. Stop the server and prohibit concurrent old or new writers.
3. Take a fresh standalone SQLite backup and record file hash, run/task counts, stable ID hashes, incumbent-schema hash, integrity, and foreign-key results.
4. Re-run the exact bootstrap preview and require the reviewed input hash, no conflicts, and zero live row changes.
5. Stop if the proposed IDs, canonical path, identity hash, repository configuration, or preview result differs.

### Phase 2 - bootstrap while enforcement remains inactive

1. Apply the exact bootstrap manifest once.
2. Re-apply once to prove idempotency.
3. Require the reviewed input, outcome, and event hashes.
4. Verify exactly one project/resource/resource-binding/repository-binding/bootstrap event.
5. Verify zero task reservations, run attempts, and quarantine rows.
6. Keep `scoped_writes_enabled = 0` until all bootstrap checks pass.

Before scoped writes are enabled, rollback may restore the fresh pre-Gate-C backup. The additive Gate B schema may also be retained with the new binding while enforcement remains inactive, but the disposition must be recorded explicitly.

### Phase 3 - irreversible cutover boundary

1. Start only the current scope-aware binary; no older write-capable process may run concurrently.
2. Enable scoped writes once.
3. Verify enforcement `enforced`, `ever_activated = 1`, and the exact active binding.
4. Restart or reload only through the validated scope-aware runtime path.
5. Require capability convergence and all startup reconciliation paths `ok`.

Once a scoped task exists, do not restore the pre-Gate-C database: that would erase authoritative scope reservations. Rollback then means stopping writers, disabling scoped mutation to enter `paused`, retaining the sidecars and bindings, and continuing only with a scope-aware binary.

### Phase 4 - live controller proof

Use a harmless durable command and exact controller request ID to prove:

- explicit `project_id` start succeeds;
- identical replay returns the same task and run;
- status, result, events, links, run status, cancellation guard, and artifact access accept the correct project;
- a wrong project fails before backend query, signal, result, event, link, or artifact access;
- an omitted-project start resolves only because exactly one active repository binding exists;
- the scoped request hash differs from the legacy hash and remains stable;
- task and run reservations contain the exact project/resource/generation and attach once;
- direct ChatGPT, Claude, and Codex MCP calls use Soma directly, without a shell proxy or CLI-as-controller workaround;
- public response budgets and publication hashes remain valid.

A failed proof pauses scoped writes and stops the gate. It does not trigger an inline relaunch loop.

## Stop conditions

Stop and report if:

- any identity must be inferred or normalized beyond the reviewed repository locator;
- the live preview hash or conflict set differs;
- any historical task, run, memory record, or quarantine disposition changes;
- the prerequisite remedy is absent or requires manual SQL;
- an older writer is present;
- bootstrap creates unexpected rows;
- scoped writes enable before bootstrap verification;
- a cross-project operation reaches backend data or process control;
- startup reconciliation is not clean;
- integrity, foreign-key, stable-ID, incumbent-schema, publication-hash, or response-budget checks fail;
- rollback would require dropping sidecars or erasing scoped records;
- memory, Obsidian, Hermes, worktrees, credentials, or unrelated run producers become necessary.

## Explicit exclusions

This preparation and later Gate C approval do not authorize:

- historical assignment, backfill, or quarantine disposition;
- project-scoped memory, Obsidian integration, or `PILOT-MEMORY-1`;
- Hermes or external-session migration;
- worktree, credential, lock-key, workflow, supervisor, SSH, scheduler, Trading Lab, or other producer migration;
- permission tiers or restrictive autonomy policy;
- pushing local commits.

## Current decision state

Gate C is prepared, not approved, and not executable until `GATE-C-PREREQ-1` is accepted. The exact identity manifest is ready for owner review. Live ProjectScope remains empty and inactive.
