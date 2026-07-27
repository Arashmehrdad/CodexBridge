# GATE-C-PREREQ-1 Owner Review

**Date:** 2026-07-27
**Decision:** focused finding closed; prerequisite accepted.
**Schema v2 activation:** not authorized.
**Gate C:** remains unapproved; schema v2 activation is still a separate owner gate.

## What passed

The implementation preserves terminal quarantine, keeps the original evidence immutable, references rather than creates successor tasks, requires exact project scope, prevents cross-project identity probing, exposes evidence without manual SQL, and introduces no second task/run/process authority. The focused suite independently passed: `12 passed in 4.97s`.

The reported full suite result of `2067 passed, 35 skipped` is consistent with the twelve new tests and no reported regression.

## Blocking finding

Soma's canonical idempotency rule is:

- same key and same normalized request returns the existing result;
- same key and a different normalized request is rejected.

The adjudication implementation derives `adjudication_id` from the project, record identity, and `idempotency_key`, but stores no normalized request hash. Once a row exists, matching that ID is treated as sufficient proof of replay.

A disposable review probe demonstrated:

- first request: `acknowledged`, reason `first decision`;
- second request with the same key: `superseded`, a valid successor, reason `conflicting decision`;
- returned result: the original `acknowledged` row with `replayed = true`;
- third request with the same key and a changed reason also returned the original reason.

Evidence run: `20260727T182300Z_executable_profile_118cc7bc`.

This is unsafe because a caller can believe a materially different owner decision succeeded when it did not.

## Required bounded fix

Because schema v2 is not live, amend migration v2 rather than adding schema v3:

1. Add an immutable normalized `request_hash` to `project_scope_adjudications`.
2. Compute it over the decision-bearing fields: project, record kind and ID, disposition, normalized reason, and successor task ID.
3. On replay, return the existing row only when both the deterministic adjudication ID and request hash match.
4. Reject the same idempotency key with any changed decision-bearing field.
5. Add tests for:
   - identical normalized request replay;
   - same key with changed disposition;
   - same key with changed reason;
   - same key with changed successor;
   - different key after adjudication remaining single-shot;
   - concurrent identical and conflicting requests.

Do not widen this into permissions, historical disposition, Gate C bootstrap, memory, or unrelated cleanup.

## Memory shadow decision

The `PILOT-MEMORY-1` shadow result is accepted as honest limitation evidence. Seven synthetic substring-based checks passing does not establish that the baseline is sufficient and does not justify a graph or memory service. Benchmark hardening may continue separately on supersession chains, semantic retrieval, metadata drift, and scale. No production memory authority or integration is authorized.

## Re-review and acceptance

Commit `22fd884bf685d766fcdad2b9ca017cede4acf183` closes the finding exactly within the requested boundary. Migration v2 now stores an immutable `request_hash` over the normalized decision-bearing fields. Replay requires both the deterministic adjudication ID and the request hash to match; changed disposition, normalized reason, or successor is rejected. Incidental surrounding whitespace normalizes to the same request, preserving real retry behavior. Concurrent identical requests converge on one row and one replay; concurrent conflicting requests produce one accepted decision and one rejection.

Independent owner re-review reran the full focused file: **15 passed in 8.57s** (`20260727T185749Z_executable_profile_e47f4947`). The live store was then checked read-only: applied ProjectScope version remains `1`, `project_scope_adjudications` is absent, all existing ProjectScope sidecars are empty, and settings remain `(scoped_writes_enabled=0, ever_activated=0)` (`20260727T185839Z_executable_profile_8732b61b`).

**Acceptance:** `GATE-C-PREREQ-1` is accepted and closed. This acceptance does not authorize applying schema v2, restarting the server on the v2 build, bootstrapping Gate C identities, enabling scoped writes, historical disposition, memory integration, Hermes changes, cleanup of `_pytest-cf1-temp`, or pushing.
