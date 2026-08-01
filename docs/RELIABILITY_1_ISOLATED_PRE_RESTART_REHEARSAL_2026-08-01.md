# RELIABILITY-1 — Isolated Pre-Restart Rehearsal

**Date:** 2026-08-01  
**Source commit:** `31d976ebc6f60a492037edadacbd3aef2f8d9698`  
**Evidence run:** `20260801T202707Z_executable_profile_8c25080f`  
**Live restart performed:** no  
**Shared configuration changed:** no  
**Push performed:** no

## Purpose

Rehearse the restart-dependent portions of `REL-017`, `REL-018`, and `REL-019` against an isolated copy of the live store before an owner-approved quiet restart is available.

This rehearsal was not live activation. The shared Soma process, live SQLite rows, live run artifacts, connector, services, and configuration were left untouched.

## Isolation method

1. Created an online SQLite backup of `runs/soma.sqlite3` inside a temporary `runs/reliability-1` directory.
2. Redirected every copied `runs.run_dir` to the temporary rehearsal root.
3. Copied only the newest 100 existing `result.json` artifacts so the bounded startup artifact audit exercised realistic healthy history.
4. Removed the rehearsal command's own nonterminal run row from the copy.
5. Cleared copied operation locks.
6. Loaded source configuration in the rehearsal process with only `runs_dir` replaced by the temporary root.
7. Replaced worker spawning with a function that would fail the rehearsal if any reconciliation path attempted to launch work.
8. Ran job-run reconciliation and supervisor reconciliation through the durable startup readiness recorder.
9. Repeated both paths to prove idempotency.
10. Verified copied integrity and foreign keys, then re-read the live database to prove its pending Hermes and planning-supervisor sets were unchanged.
11. Deleted the temporary database and artifact tree after the evidence was published by the owning durable diagnostic run.

## Baseline copied from live state

- Five terminal Hermes runs had incomplete publication:
  - `20260801T172616Z_hermes_service_65188393`
  - `20260801T172638Z_hermes_service_55b02de2`
  - `20260801T172645Z_hermes_service_dfe645dd`
  - `20260801T172709Z_hermes_service_a15425d5`
  - `20260801T172726Z_hermes_service_7a7f8e2f`
- Nine supervisors remained `planning`.
- The copied startup-readiness record had no `supervisors` path because the running process predates `REL-017`.

## Job-run reconciliation result

- First pass reconciled exactly **5** runs.
- Duration: **1.902 seconds**.
- Each Hermes row became publication-complete in the copy.
- Every copied `result.json` existed and its SHA-256 matched `result_published_hash`.
- Every public result was `ready` or `fallback` and carried a 64-character source hash.
- A sampled healthy recent artifact preserved both its modification time and content hash, proving healthy history was not rewritten.
- Second pass reconciled **0** runs in **1.482 seconds**.

This supports the expected live improvement from the current 46.219-second startup record, while preserving the requirement for a real post-restart timing measurement.

## Supervisor reconciliation result

The first pass reconciled all nine stale parents in **0.803 seconds**:

| Supervisor | From | To |
|---|---|---|
| `20260713T123649Z_supervisor_22d38f9b` | `planning` | `failed` |
| `20260707T160720Z_supervisor_2bd03e17` | `planning` | `needs_input` |
| `20260706T212214Z_supervisor_76c48c35` | `planning` | `failed` |
| `20260706T212202Z_supervisor_b88aabaa` | `planning` | `cancelled` |
| `20260706T212140Z_supervisor_021d1386` | `planning` | `needs_input` |
| `20260706T212034Z_supervisor_0ad6c122` | `planning` | `failed` |
| `20260706T212029Z_supervisor_b18ddff9` | `planning` | `needs_input` |
| `20260630T104711Z_supervisor_89efe2b1` | `planning` | `needs_input` |
| `20260428T155121Z_supervisor_66b38ce7` | `planning` | `needs_input` |

After reconciliation, the copied supervisor counts were:

- `cancelled`: 2
- `failed`: 3
- `needs_input`: 15
- `planning`: 0

The second pass returned no transitions. No worker spawn was attempted.

## Readiness and integrity

- Source startup readiness: `ok: true`
- Missing startup paths: none
- Failed startup paths: none
- SQLite `integrity_check`: `ok`
- Foreign-key violations: 0

## Live-state non-mutation proof

After the isolated rehearsal:

- the live incomplete-publication set was still the same five Hermes run IDs;
- the live `planning` supervisor set was still the same nine IDs;
- no shared service was restarted, stopped, refreshed, or reconfigured;
- no live result artifact was created or changed;
- the repository worktree remained clean before documentation of this evidence.

## Disposition

The isolated rehearsal validates the source-side activation sequence and expected historical outcomes for `REL-017` through `REL-019`. It does not replace the owner-approved quiet restart and live post-activation checks. The live process remains intentionally behind source until that window exists.
