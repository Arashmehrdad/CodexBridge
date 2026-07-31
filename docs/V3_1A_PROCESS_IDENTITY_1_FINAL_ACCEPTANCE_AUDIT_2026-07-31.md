# V3-1A-PROCESS-IDENTITY-1 — Final Independent Acceptance Audit

**Date:** 2026-07-31
**Verdict:** accepted after iterative corrective packages.
**Accepted runtime commit:** `7cc66c50675a91ff958d39a3c53e6246a88268d6`
**Branch:** `lane/memory-integration-foundation-1`
**Push:** none.

## 1. Scope of this verdict

This is the final acceptance record for the complete `V3-1A-PROCESS-IDENTITY-1` chain. It does not claim that the original process-identity submission passed unchanged.

The accepted result is the cumulative implementation formed by:

1. `bd007ec72ca7b2e24ffe7b4587570f0173a111d8` — initial sanitised stand-in launch and process-identity package;
2. `c1c5b535e9bb95b14b701546ce716653faf6688d` — identity-proven canonical cancellation;
3. `89fb199c4a1a62fc464eed38d6b2836b3094941b` — publication, identity capture, and crash containment;
4. `b6adcae3267607e26d471163153b2cbec92b41b5` — identity-safe launch-failure containment;
5. `7cc66c50675a91ff958d39a3c53e6246a88268d6` — root-exit versus owned-tree containment closure.

The later `b2f68e7d90fd96fa320627f26f25f056f889fcbe` commit adds only the parked Orbit UI research note and does not alter the accepted runtime.

## 2. Final safety contract

The accepted implementation enforces all of the following:

- a live PID is never terminated as owned work without exact matching process-start identity or pre-established kernel ownership proof;
- launcher and executable-child identities are captured before healthy attachment;
- identity-capture failure performs no raw-PID query, descendant enumeration, or PID-based termination;
- creator-handle cleanup can prove root exit only, not descendant absence;
- root-only cleanup remains non-terminal `recovery_pending` and retains or quarantines mutation ownership;
- terminal launch failure requires exact owned-tree-empty proof;
- Windows Job Objects are established before a contained root can execute, use `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and provide kernel membership evidence;
- cancellation verifies zero owned descendants before terminal cancellation publication;
- publication failure after proven termination is reported honestly and retries the same authoritative result without repeating termination;
- cancellation wins races against ordinary progress and repository locks are released only after accepted termination proof;
- unprovable containment retains repository ownership and remains available for explicit recovery adjudication.

The decisive distinction is now explicit:

```text
root exited
    !=
owned process tree is empty
    !=
terminal cancellation or failure may be published
```

## 3. Independent adversarial review

The audit repeated the previously failing boundary rather than relying only on committed tests.

### Escaped descendant

A real root process spawned a child before identity capture was forced to fail. Creator-handle cleanup stopped and reaped the root while the child remained alive temporarily.

The corrected implementation reported:

- root exit confirmed;
- owned-tree absence not proven;
- terminal containment false;
- no raw-PID termination;
- canonical status `recovery_pending`;
- terminal result not published;
- repository lock retained.

### Kernel-owned tree proof

A root, child, and descendant launched inside a pre-established Windows Job Object were terminated through kernel ownership. Terminal safety became true only after exact job membership became empty.

### Publication retry

The integrated cancellation regression forced a real `atomic_write_json` failure after zero-process cancellation proof. The first response reported partial publication failure, the canonical cancelled result remained unchanged, the repository lock was released under the accepted zero-process policy, and retry published the identical result and source hash without another termination attempt.

## 4. Independent validation

Durable audit runs:

- `20260731T062839Z_executable_profile_dadc2999` — seven sharp regressions: **7 passed**;
- `20260731T062839Z_executable_profile_e1890e0e` — structural root/tree-proof audit: `DESCENDANT_CONTAINMENT_STRUCTURAL_OK`;
- `20260731T062839Z_executable_profile_e4b673e8` — focused process, cancellation, substrate, adapter, JobManager, worker, parallel, and process-control selection: **413 passed, 1 xfailed**;
- `20260731T063101Z_executable_profile_0566624b` — uncontended full repository suite: **2556 passed, 35 skipped, 1 xfailed**;
- `20260731T064251Z_executable_profile_5951afd1` — `pip check`, changed-file Ruff format/check, and `git diff --check`: passed.

The single strict xfail is the previously disclosed `worker_identity` value exposure through `get_status`. Launcher and child identity values remain excluded from the governed public projections. Removing the older worker identity field is a separate public-contract decision and was not silently folded into this gate.

No process or cancellation test was deselected.

## 5. Migration, compatibility, and authority

The accepted chain remains additive and compatible:

- `launcher_identity` and `child_identity` are additive RunStore columns with no historical backfill;
- historical rows with empty identity are treated as unproven ownership, never trusted retroactively;
- public gateway and request-schema inventories are unchanged by the descendant-containment package;
- the live public schema hash remained unchanged during audit;
- ProjectScope, TaskStore, RunStore, JobManager, repository-lock, and ResultPublication ownership remain where they were;
- worker-process code constructs and records evidence but does not own canonical lifecycle or result acceptance;
- no new supervisor, lifecycle manager, lease authority, result publisher, task command, provider execution path, or public worker gateway was introduced.

**Net generic lifecycle-authority delta:** `+0`.

## 6. Known limitations accepted for this gate

- The implementation remains stand-in only. No real Claude Code or Codex process, account, prompt, or provider stream was used.
- Canonical launchers do not currently pre-establish a Job Object for every launch. Therefore a fresh identity-capture failure conservatively remains `recovery_pending` even after the root is known to have exited; explicit recovery adjudication is required because descendant absence was not proven.
- Non-Windows platforms have no equivalent kernel containment in this package and therefore degrade honestly to uncertainty where tree absence cannot be proven.
- Job Object handles do not provide restart adoption. `KILL_ON_JOB_CLOSE` deliberately stops disposable workers when the controller dies; later recovery uses durable task/run/session state and exact provider-native resume.
- The pre-existing `worker_identity` public exposure remains recorded by a strict xfail and requires a separate public-contract decision.
- CIM enumeration remains supporting evidence only and may be comparatively slow on Windows.

None of these limitations weakens the accepted no-raw-PID, zero-descendant, publication, or lock-retention contracts.

## 7. Acceptance decision

`V3-1A-PROCESS-IDENTITY-1` is accepted and closed.

Its corrective subgates remain preserved as historical evidence of defects found and corrected; they are not separate active lifecycle authorities.

The process boundary is now sufficient to open the next bounded V3-1A package:

`V3-1A-INTERACTION-COMMANDS-1 — Canonical Controller Interaction and Non-Terminal Waiting`.

That next gate may add steering and supplied-input command semantics over the existing canonical Task → Run and worker-substrate records. It may not launch a real provider, use provider accounts, expose Soma MCP to workers, start V3-1B, activate production behavior, or push.
