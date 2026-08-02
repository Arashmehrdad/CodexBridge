# V3-1A Deterministic Interaction Actions — Result

**Date:** 2026-08-02  
**Parent package:** `V3-1A-INTERACTION-COMMANDS-1`  
**Status:** accepted and closed as the deterministic transport/public-command slice  
**Commits:**

- `105da47dde70bafae38764808605c86e47b91b9e` — initial deterministic interaction dispatch
- `3c94db4df67399a9ddfa236b48c3d3985f59892c` — initial TaskManager interaction actions
- `06d75ca197eb43fc9a356e1a7f9315241d0e7193` — reconciled dispatcher, strict public contracts, import-cycle repair, and final validation

**Push:** not authorised and not performed.  
**Activation:** source only; the running server remains on the prior build.

## 1. Accepted outcome

Soma now exposes narrow public `task_action` operations for `steer` and `supply_input` over the existing canonical Task → Run authority without launching Claude Code, Codex, or any provider process.

The package adds:

- one provider-neutral reference-only interaction transport port;
- deterministic acknowledged, rejected, and outcome-unknown stand-ins for tests;
- one integrated `InteractionDispatcher` coordinating existing command, message, attempt, and resume authorities;
- strict discriminated gateway request models for `steer` and `supply_input`;
- TaskManager actions, capability projection, server routing, and CF1 inventory derived from the same public command contract.

The production transport default remains deliberately unavailable. Public discovery therefore describes the contract without falsely claiming live provider delivery.

## 2. Persist-before-send and single-claimer behavior

Before transport is called, the existing shared transaction has already persisted:

- the canonical version-guarded task command;
- the subordinate generic message;
- exact project, resource, task, run, session, checkpoint, sender, recipient, optional mandate, and payload identities;
- one complete normalized contract hash.

The dispatcher then claims the message through the durable transport-attempt table. Exactly one claim can win.

A replayed attempt is interpreted as follows:

- `claimed` remains unresolved and is not relabelled or resent;
- `outcome_unknown` remains uncertain and is not resent;
- `acknowledged` may repair only the local command/checkpoint projection;
- `rejected` or `prevented` completes the canonical command as failed without inventing delivery.

Concurrent identical dispatch requests converge on one command, one message, one attempt, and one transport call.

## 3. Public `supply_input`

`SUPPLY_INPUT` requires:

- exact project and task identity;
- exact task state version;
- exact bound provider-session identity;
- exact open checkpoint identity;
- caller idempotency identity;
- exact sender and recipient references;
- non-empty payload.

The payload is stored content-addressed before dispatch and is never echoed. Only durable acknowledged evidence can resolve the exact checkpoint and resume the same Task and Run. Rejection, uncertainty, stale versions, wrong checkpoint, wrong session, wrong scope, expiry, cancellation, supersession, and technical continuity failure all fail closed.

## 4. Public `steer`

`STEER` is accepted only when:

- the canonical task is non-terminal and version-matched;
- the exact provider session is durably bound;
- the provider adapter declares measured mid-turn steering support;
- the injected transport supports the provider and command.

The deterministic Claude stand-in can acknowledge steering. Codex steering remains rejected because the adapter declares it unmeasured rather than supported. Steering does not resolve an unrelated checkpoint or advance canonical Task/Run lifecycle by itself.

## 5. Payload and evidence safety

Transport receives references only:

- payload reference;
- SHA-256;
- byte count;
- message and attempt identity;
- provider-session and checkpoint identity.

It does not receive raw payload bytes through the request object. Public responses report IDs, disposition, uncertainty, resume state, and bounded evidence references without payload echo.

Acknowledgement without a non-empty durable evidence reference is downgraded to outcome unknown. Unexpected transport exceptions record only the sanitized exception type and a generic no-resend reason; provider exception text is not persisted.

## 6. Reliability defects and concurrency reconciliation

### REL-027 — import-order circularity

Fresh-process import run `20260802T191343Z_executable_profile_1ad055d6` proved that a top-level `TaskManager` import of the worker-substrate package created an import-order-dependent circular initialization. A narrower pytest subset had passed because another module had already populated the import graph.

The fix moves interaction transport, dispatcher, message-class, and exception imports behind TaskManager runtime boundaries. Both fresh-process import orders passed in group `20260802T191856Z_powershell_group_6b41e8ff`, and the permanent subprocess regression now exercises both orders.

### Duplicate ChatGPT continuation

The client/UI interruption caused the failed response to continue editing in parallel with the recovery response. Soma's hash-bound previews rejected stale writes, active runs were not cancelled, and no conflicting merge was forced. After the parallel writer stopped, stability run `20260802T191805Z_executable_profile_d9072789` observed an identical HEAD and worktree digest in four samples across 20 seconds. The two partial implementations were then reconciled into one dispatcher and one test surface.

## 7. Authority delta

Added:

- one internal dispatcher coordinating already-owned authorities;
- two narrow public task actions;
- one provider-neutral transport port and deterministic test stand-ins;
- bounded public capability and inventory metadata.

Not added:

- no new Task or Run lifecycle;
- no scheduler, supervisor, lease owner, lock owner, process owner, result publisher, or acceptance authority;
- no new durable table in the dispatcher or transport modules;
- no provider account, process, prompt, live stream, stdin channel, or external transport;
- no worker-facing Soma MCP access;
- no automatic resend after uncertain or unresolved delivery.

Repository search confirms exactly one `InteractionDispatcher` definition.

## 8. Validation

Focused interaction gate:

- `20260802T192106Z_executable_profile_57a489a3` — **100 passed**.

Initial public gate:

- `20260802T192106Z_executable_profile_2ba44106` — **218 passed, 2 stale contract assertions failed**; runtime behavior was green and the historical expected operation lists were corrected.

Targeted contract rerun:

- `20260802T192710Z_executable_profile_bf438779` — **3 passed**.

Final public/server/inventory gate:

- `20260802T192737Z_executable_profile_74a042fa` — **220 passed**.

Full repository regression floor:

- `20260802T193529Z_executable_profile_c9cd079d` — **2657 passed, 35 skipped, 1 expected xfail** in 562.96 seconds.

Additional evidence:

- compilation passed;
- Ruff passed;
- `git diff --check` passed;
- both clean-process import orders passed;
- package import and public discovery passed;
- authority audit found one dispatcher and no new lifecycle/publication authority.

## 9. Known limitation

The source is not active in the running Soma service. No live `steer` or `supply_input` claim is made before a later controlled restart and connector refresh.

The production transport is intentionally unavailable. This result proves controller semantics and deterministic transport behavior only; it does not prove live Claude Code or Codex interaction.

## 10. Next active slice

The final bounded V3-1A slice is checkpoint expiry and recovery closure:

- one central idempotent expiry processor over the exact open checkpoint and deadline;
- canonical pause/cancellation request through existing process authority where required;
- no lock or resource release without accepted quiescence or zero-descendant proof;
- explicit recovery classification for pending-never-attempted, unresolved claimed, outcome-unknown, acknowledged-before-resume, resolved-before-run-resume, and in-flight-at-expiry windows;
- final cancellation-before-send, cancellation-during-send, late-acknowledgement, and late-input precedence tests;
- process/cancellation regression floor and final package authority-delta audit.

Real provider execution, production activation, V3-1B, deployment, and push remain outside this slice.
