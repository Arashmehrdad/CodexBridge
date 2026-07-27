# GATE-C-PREREQ-1 Owner Review

**Date:** 2026-07-27
**Decision:** returned for one focused fix; not accepted.
**Schema v2 activation:** not authorized.
**Gate C:** remains blocked and unapproved.

## What passed

The implementation preserves terminal quarantine, keeps the original evidence immutable, references rathe than creates successor tasks, requires exact project scope, prevents cross-project identity probing, exposes evidence without manual SQL, and introduces no second task/run/process authority. The focused suite independently passed: `12 passed in 4.97s`.

The reported full suite result of `2067 passed, 35 skipped`  is consistent with the twelve new tests and no reported regression.

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
