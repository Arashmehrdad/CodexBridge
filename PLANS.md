# Soma Active Engineering Plan

## Purpose

Soma is the durable control plane connecting this ChatGPT conversation to local machines, repositories, services, remote hosts, and external tool runtimes.

```text
ChatGPT conversation
  -> reasoning, user context, tool selection, and approvals
  -> Soma MCP
      -> durable identity, policy, execution, cancellation, and evidence
      -> local and remote engineering substrates
      -> Hermes searchable tool runtime
          -> built-in tools, plugins, skills, and connected MCP tools
```

ChatGPT remains the reasoning and implementation controller. Hermes supplies tools only; no model-agent loop is part of this request path or may be launched through unrestricted PowerShell.

This file is an active decision document, not an engineering journal. The complete V2 implementation and validation history through commit `d1c43340af48c03ca31505ef64f4c6a60248f61c` is preserved in [`docs/roadmap-v2-achievements.md`](docs/roadmap-v2-achievements.md).

## Governing Decisions

### Durable before powerful

Every accepted asynchronous operation must persist launch intent, request identity, ownership and lease state, cancellation state, output locations, and terminal publication semantics before it is production-ready.

### ChatGPT remains the brain

- The live ChatGPT conversation owns reasoning, user context, planning, and tool selection.
- Soma exposes governed capabilities to that conversation.
- Hermes is a tool runtime, not a delegated reasoning agent, for this integration.
- The design does not depend on exporting ChatGPT's private memory store. Relevant context stays in the conversation; only required tool arguments or explicit context are transmitted.

### Reuse Hermes rather than duplicate it

- Reuse Hermes registration, availability checks, toolsets, plugin discovery, MCP discovery, and searchable dispatch where feasible.
- Do not create one Soma wrapper for every Hermes tool.
- New Hermes plugins or MCP tools should become discoverable without corresponding Soma source changes.
- Pin and negotiate the supported Hermes interface so upstream changes fail explicitly.

### Existing execution decisions remain in force

- `permissive` is the only active execution profile.
- Unrestricted PowerShell remains the single arbitrary-command local gateway.
- Native remote Linux execution continues through the accepted R4 controller protocol.
- Remote PowerShell remains optional for hosts that already provide it.
- Existing human-only boundaries continue to apply to real-money, credential, destructive, and production-impacting actions.

### No paid infrastructure for validation

- Do not start, rent, or retain RunPod or any other paid remote/GPU host solely for Soma testing, acceptance, or roadmap evidence.
- Prefer local Windows validation, deterministic mocks and replayed fixtures, existing free CI, or infrastructure already running for an actual user-requested workload.
- OS-, provider-, or hardware-specific execution evidence that cannot be obtained without new cost is non-blocking deferred evidence. Collect it opportunistically during real work rather than making it a roadmap gate.

### Evidence before Roadmap V3

After the Hermes integration reaches its bounded gate, architectural feature expansion pauses. Soma will be exercised on real projects before another broad reliability roadmap is created.

## Current Baseline

Complete: D1-D5 durability; G0/G1 managed editing and executable closure; X1/X2 unrestricted local PowerShell; X2A parallel groups; C1 permissive-only cleanup; R3 managed transfer; R4 durable remote Linux ownership; and optional X4 remote PowerShell.

R5 absolute resource enforcement is complete. H1A has selected and pinned the Hermes companion-process architecture. H1B now includes the versioned companion, durable public gateway, policy-preserving built-in calls, plugin and MCP discovery, repository-owned Hermes-home binding, and successful public connected-MCP execution.

Parallel PowerShell cancellation acceptance is complete. Whole-group and individual-child cancellation terminate the attached Windows process tree, preserve or refill sibling slots as required, and publish durable terminal results. Acceptance waits for durable child attachment before asserting process-owned readiness markers, so normal worker import time cannot create a false cancellation failure.

Known observations, not yet separate repair programs:

- occasional HTTP 502 responses from the ChatGPT connector path;
- external acceptance fixtures that may disappear independently of Soma;
- increased complexity in durable state and reconciliation contracts.

Collect operational evidence before prescribing broad fixes for these observations.

## Active Sequence

No implementation lane is currently active. TASK-1 completed on 2026-07-25 and this roadmap now requires an explicit, bounded owner selection before another implementation lane begins.

A generic `continue` must not reactivate CF1, TL0-TL9, H1/H2, OP1, SSH-A1, TASK-1, broad reliability/autonomy work, or Roadmap V3. The next implementation unit must be explicitly selected and bounded by the owner. Roadmap Phase 2 is the natural successor but is not automatically active.

Completed sequence:

1. CF1 completed the compact public-representation, evidence-retrieval, repository progressive-disclosure, gateway-envelope, and connector rollout work.
2. H2 completed the shared multi-session Hermes service and its live acceptance.
3. OP1 completed the evidence-driven real-project pilot without crossing the Roadmap V3 promotion threshold.
4. The original TL0-TL9 program completed and was superseded by the authoritative Trading Lab redesign.
5. Trading Lab's scheduled ChatGPT companion cycle was implemented in the standalone package, wired through Soma, and live-accepted for no-order and internal-paper execution.
6. SSH-A1 completed credential-source probing, reference-bound profiles, managed host identity, capability snapshots, canonical project bindings, durable transactional activation/rollback, public gateway exposure, documentation, and live connector rollout.
7. TASK-1 completed the first bounded batch of roadmap Phase 1: a canonical task schema and transactional migration, typed controller-neutral task models, one mapped durable execution backend, compact task status and result queries, one state-version-guarded command, idempotent task creation, restart-safe reconciliation, and live acceptance.

The owner-facing SSH contract is now available: provide a local credential location or existing SSH alias plus host/project intent. The controller handles source discovery, field mapping, preview, authentication, capability discovery, project validation, activation, and rollback without asking the owner to edit configuration or paste secret values.

A generic `continue` must not reactivate TL0-TL9, broad reliability/autonomy work, Roadmap V3, broker-demo scheduling, SSH-A1, or another lane. The next implementation unit must be explicitly selected and bounded by the user.

The first owner-supplied real-host onboarding is operational use of the completed SSH-A1 capability, not an automatically active implementation lane. The first minimum-size broker-demo order and unattended trading scheduling remain separate operational decisions.

## Priority 0 - TASK-1 Canonical Task Plane Foundation

Status: **complete; implementation, focused and full-suite validation, static gates, isolated source startup, controlled live restart, and live task-backed acceptance closed on 2026-07-25**.

Complete contracts, compatibility guarantees, migration and rollback boundaries, test coverage, and live evidence are recorded in [`docs/task1-canonical-task-plane-evidence.md`](docs/task1-canonical-task-plane-evidence.md).

### Completion evidence

- canonical `tasks`, `task_links`, `task_commands`, `task_checkpoints`, and `task_events` were added by ordered transactional migrations recorded in `soma_schema_migrations` at component `canonical_task_plane` version 1, with no change to any existing table;
- typed task models carry the complete controller-neutral state vocabulary and contain no approval, permission-tier, autonomy, or controller-specific value;
- the durable local command path (`executable_profile`) is mapped as the first and default backend by delegation, not by forking its execution logic;
- `task_query` (`capabilities`, `status`, `result`, `events`, `links`) and `task_action` (`start`, `cancel`) took the public gateway count from 30 to 32 with operation inventory `cf1.3.gateway-operations.v11`;
- task creation is idempotent on `controller_request_id` plus a normalized request hash: a matching replay returns the existing task, a differing request is rejected explicitly, and concurrent duplicates plus post-restart retries provably create only one backend run;
- `task_action.cancel` is state-version guarded, delegates to the run engine, rejects stale versions with the current version, reports `cancellation_pending` until termination is proven, and is a no-op once terminal;
- restart-safe reconciliation covers active workers, incomplete launches, stale projections, pending cancellation, unpublished result linkage, duplicate reconcilers, and inconsistent backend identity, and never invents success;
- 41 focused tests plus the complete suite passed at **1917 passed and 35 skipped**; Ruff, Python compilation, `pip check`, and whitespace hygiene passed;
- isolated source startup returned `/health = OK` with both task gateways discoverable; the controlled live restart converged source and running build identity at `3ca1a1abd9384901691c921e956c230a12fe007d091ff4945c198030d27e8a69`;
- live acceptance ran canonical task `task_20260725T114648Z_19cd9d57aaee` over durable run `20260725T114648Z_executable_profile_e5186cdc` to `completed`, with the task result referencing the authoritative run result hash, and live version-guarded cancellation of `task_20260725T114748Z_06a2add4ca6e` confirmed real process termination with no leaked locks;
- existing `run_start`, `run_query`, and `cancel_run` behaviour is unchanged, and legacy runs remain readable without a canonical task.

No historical run was backfilled into a canonical task, and no legacy store was deleted.

### Objective

Introduce one controller-neutral canonical task identity above Soma's existing durable execution engine, so that a future controller can supervise every execution type through one compact task protocol without losing recovery, cancellation, or evidence behaviour.

The initial relationship is:

```text
canonical task
  -> references one selected execution backend
  -> maps to an existing durable run
  -> reuses the existing worker, lease, cancellation, evidence, result, and recovery systems
```

This is an additive compatibility layer, not a second execution engine.

### Permanent boundaries

- the existing durable engine remains the first and default backend;
- no second worker, lease, lock, evidence, result, scheduler, or repository authority;
- no deletion or broad refactor of legacy run, workflow, supervisor, or domain systems;
- no approval states, permission tiers, autonomy gates, confirmation phrases, or command allowlists as user-permission barriers;
- controller-neutral terminology only; no `awaiting_chatgpt`, `needs_approval`, or approval state in the canonical task model;
- exact authoritative evidence is stored once, and public task responses are compact projections referencing that existing evidence;
- all existing public run APIs and their behaviour are preserved.

### Bounded first implementation

1. canonical task schema and ordered transactional migration;
2. typed task models and controller-neutral state machine;
3. mapping for one existing durable execution type;
4. compact task status and result queries;
5. one state-version-guarded task command;
6. idempotent task creation;
7. compatibility and migration tests;
8. live discovery and restart acceptance.

Explicitly out of scope for this batch: the application container, scheduler, browser, desktop, Temporal, memory sidecars, capability-broker migration, worktrees, and legacy deletion.

### Selected initial backend

The durable local PowerShell/executable-profile path (`run_start.operation = "powershell"` -> `JobManager.start_executable_profile` -> `executable_profile` runs) is the smallest current public durable execution path that exercises the real engine and can be tested safely.

Its execution logic is not forked. A task-backed start reserves the durable run identity, records it, then delegates to the existing manager. Legacy direct `run_start` remains available and unchanged.

### Canonical states

```text
accepted
queued
running
awaiting_controller
paused
cancellation_pending
recovery_pending
completed
failed
cancelled
uncertain
```

The first slice does not exercise every state, but the schema vocabulary is complete and contains no controller-specific or approval-specific value.

### Exit gate

One canonical task can represent, supervise, cancel, and recover a real durable local execution through `task_query` and `task_action`, with the task result referencing the authoritative run result rather than competing with it, and with every existing run API unchanged.

Met on 2026-07-25.

### Remaining for a later Phase 1/Phase 2 batch

- only the durable local command backend is mapped; workflow, supervisor, SSH, Hermes, remote PowerShell, command-group, and domain executions are not yet canonical tasks;
- only `cancel` is implemented as a version-guarded command; `steer`, `input`, `pause`, `resume`, and `retry` remain future work;
- `task_checkpoints` exists but no checkpoint is created yet, so controller checkpoint round-trips are not exercised;
- `recovery_pending` and `uncertain` are reported honestly with no automated repair command;
- no historical run is represented as a canonical task.

## Priority 0 - SSH-A1 Agent-Driven Credential Binding and Transactional Host Activation

Status: **complete; implementation, deterministic acceptance, full-suite validation, isolated startup, restart, and live connector convergence closed on 2026-07-25**.

### Completion evidence

- secret-safe credential probing supports dotenv files, process environment, OpenSSH config, connection files, and direct key references without returning resolved values;
- reference-bound profiles resolve only at execution time and preserve legacy literal, alias, and connection-file compatibility;
- Soma-managed host identity supports pinned, first-use, and explicit-rotation policies with staged trust and rollback;
- versioned capability snapshots and canonical project-to-host bindings are durable, hash-bound, independently replaceable, and read-only validated;
- `profile_apply` is a durable, restart-recoverable transaction covering candidate authentication, capability discovery, project validation, atomic config/trust/pointer activation, post-checks, verified rollback, and honest `RECOVERY_REQUIRED` handling;
- the free fake-host source-to-activation acceptance passed without exposing credential values or touching a real host;
- the complete functional suite passed with **1,864 passed and 35 skipped**; the affected post-cleanup suite passed 68 tests; Ruff, dependency checks, and whitespace hygiene passed;
- isolated source startup returned `/health = OK`, the controlled live restart completed, and source/running build identity converged at `fffcfdeb47678b26a8b681c4984bcacdc5a0ae7305b3b47337a76898a2b60318`;
- live discovery exposes all seven SSH query operations: `capabilities`, `credential_probe`, `profile_preview`, `profile_status`, `capability_snapshot`, `project_bindings`, and `project_binding_validation`.

No existing host was automatically migrated and no real credential was used during implementation acceptance. A future owner-supplied real-host onboarding uses this completed capability and remains subject to the normal fingerprint, authentication, validation, and rollback transaction.

### Objective

Allow the owner to place key-based SSH credential references at any supported local file location and point the controller at that location. Soma must inspect the source locally without returning values, bind the fields, verify local key hygiene and remote host identity, authenticate, discover capabilities, validate optional project bindings, and activate the candidate transactionally.

### Permanent boundaries

- no raw private-key material through MCP, chat, YAML, logs, manifests, or durable run inputs;
- no SSH password or keyboard-interactive authentication;
- no project-specific host-migration code;
- no active config, managed host-key, capability pointer, or project-binding mutation before candidate checks pass;
- automatic rollback covers every local resource changed by activation;
- existing run, lease, cancellation, repository-lock, and service-reload authorities are reused;
- the controller performs the deterministic multi-call workflow; no second model-agent loop is introduced.

### Detailed plan

See [`docs/ssh-agent-driven-host-onboarding-plan.md`](docs/ssh-agent-driven-host-onboarding-plan.md) for the data model, public operations, state machine, security invariants, implementation sequence, required tests, and exit gates.


## Priority 0 - CF1 Chat Footprint and Progressive Disclosure

Status: **complete; CF1.0-CF1.7 implementation, live rollout, compatibility, and footprint acceptance closed on 2026-07-24**.

### Objective

Reduce the total Soma tool footprint inserted into ChatGPT conversations by at least **90 percent** while preserving complete authoritative evidence, exact command inputs and outputs, cancellation and recovery semantics, repository locks, result hashes, debugging capability, model access to requested detail, and current execution throughput.

The repair applies globally to every Soma-managed project and public gateway, including Soma, Andiya, Wan2.2, Hermes, Trading Lab, supervisors, workflows, SSH, parallel groups, and future repositories.

### Architectural boundary

CF1 is a presentation-and-retrieval-plane repair over the accepted durable execution core. It must not create another execution architecture or change:

- worker, launcher, or child ownership;
- lease identity or heartbeats;
- repository-lock acquisition or release;
- cancellation targeting or reconciliation;
- startup adoption and recovery decisions;
- terminal state/result atomicity;
- protected artifact retention or hashing;
- H2 concurrency semantics;
- Trading Lab execution or journal semantics.

The three representations are:

```text
Authoritative record
  complete durable request, lifecycle state, output, result, and evidence
  never truncated and never replaced by a summary

Chat projection
  small deterministic versioned representation returned by default

Evidence retrieval
  exact artifact, range, search match, tail, hunk, request, or full record
  requested explicitly and bound to immutable content identity
```

Every compact representation must declare that it is non-authoritative and that the complete authoritative record remains available.

### Public views

Use fixed, versioned projections rather than arbitrary caller-selected database fields:

```yaml
view:
  summary: default minimal operational representation
  standard: summary plus bounded diagnostics
  full: explicit existing lossless cursor-based representation
```

The default summary must preserve operationally meaningful distinctions. It must not collapse partial completion, validation failure, policy denial, needs-input, cancellation uncertainty, infrastructure failure, incomplete cleanup, ambiguous side effects, or required reconciliation into apparent success.

Normalized bounded state may include:

```text
lifecycle_status
outcome
current_phase
action_required
validation_state
cancellation_state
cleanup_state
reconciliation_required
safety_failure
state_version
```

Full input, argv, environment, reviewed scripts, staging manifests, executable identity, progress JSON, full result JSON, stdout/stderr, local paths, and artifact internals remain absent from ordinary summary views.

### Cross-cutting contracts

#### Decision-version semantics

`state_version` changes for every transition material to ChatGPT decisions, including lifecycle, phase, cancellation, worker/child attachment, restart reconciliation, lock ownership, terminal publication, ambiguous-mutation reconciliation, and needs-input transitions. Ordinary heartbeat refreshes must not continuously invalidate conditional polling; liveness uses bounded timestamps or a separate generation.

#### Stable cursors

Opaque cursors bind operation, filters, ordering, view, representation version, response budget, snapshot boundary, final sort key, and expiry. Run lists use stable keyset pagination rather than offsets. Explicit full mode retains the existing frozen redacted snapshot and lossless reconstruction contract.

#### Repository content identity

File continuation binds to file SHA-256 and supports both line and byte offsets. Changed content fails with a stale-content response rather than mixing versions. Search continuation binds to a repository/worktree snapshot identity. Diff inspection uses a frozen diff artifact or snapshot ID so file statistics, hunk indexes, selected hunks, and explicit full retrieval all refer to the same evidence.

#### Artifact security

Opaque artifact IDs are necessary but not sufficient. Retrieval enforces authoritative-manifest membership, run-directory containment, symlink and traversal rejection, public/protected classification, secret redaction, text/binary handling, encoding and byte-range semantics, bounded scanning, bounded matches, bounded duration, immutable size, and SHA-256 identity.

The system distinguishes artifact existence, retrievability by trusted internal code, and public retrievability through ChatGPT.

#### Materialized projection identity

A terminal public projection is tied to the authoritative result through at least:

```text
public_result_json
public_result_schema_version
public_result_source_sha256
public_result_status
```

Reuse is permitted only when source hash and schema version match. Old projections rebuild lazily. A projection-builder failure must never block authoritative terminal publication; a tiny bounded fallback envelope must still expose the terminal outcome and evidence identity.

#### Deterministic byte budgets

Budgets use serialized UTF-8 bytes, not character counts. Per-field limits prevent one summary, error, path, test message, or artifact list from exhausting the whole response. Truncation occurs only at valid Unicode boundaries and reports original byte count, omitted-content identity where appropriate, and an exact retrieval handle.

Never cut serialized JSON in the middle, silently omit errors, hide safety failures, or lose continuation metadata. Response metadata reports a non-self-referential payload byte count; final connector-visible wire size is measured separately.

### CF1.0 - Contract and end-to-end measurement

Status: **complete**.

Completion decision:

- the public projection contract now freezes normalized outcomes, public views, whole-response and per-field UTF-8 byte budgets, cursor binding, decision-version behavior, artifact visibility, redaction, and stale-content semantics;
- every public gateway and operation has a versioned inventory covering implementation path, response path, size limits, request echo, JSON-decoding cost, pagination, and connector representation;
- representative fixtures and footprint measurements cover the required lifecycle, provider, repository, workflow, supervisor, Hermes, executable, parallel-group, and Trading Lab cases;
- current run-store columns, JSON/internal columns, SQL selection behavior, query plans, index proposals, and independent run-path latency/allocation/decode baselines are recorded;
- the frozen full run transport, recursive redaction, reviewed-script masking, repository path safety and hashing, compact repository status, and opaque managed-write identity are bound to existing regression evidence;
- CF1.0 changes no production response or execution behavior. All non-CF1 roadmap lanes remain paused.

Before changing production behavior:

- inventory every public gateway operation, its implementation path, current default and maximum response size, request-echo behavior, JSON-decoding cost, pagination behavior, and connector-visible representation;
- record the existing full run transport, recursive redaction, reviewed-script masking, repository path safety, file hashing, compact repository status, and opaque hash-verified managed-write identities as compatibility invariants with regression tests rather than rebuilding them;
- measure request arguments, server projection bytes, MCP structured-content bytes, MCP text-content bytes, connector wrapping, duplicated representations, and total conversation-visible round-trip bytes;
- capture the existing approximately 837-KB twenty-run list plus successful, failed, active, cancelled, partial, ambiguous-side-effect, Hermes, executable-profile, repository-read, repository-search, large-diff, parallel-group, SSH, workflow, supervisor, Trading Lab, Docker, Cloudflare, and knowledge fixtures;
- benchmark current run `list`, `status`, `control`, `events`, `output`, and `result` paths independently so compact improvements are not credited to unrelated transport behavior;
- verify which summary and control fields already exist as scalar database columns, which require new scalar columns, and which belong only in terminal public materialization;
- inspect query plans and add an index proposal only where measurements prove it is needed;
- define normalized outcome semantics, per-field UTF-8 byte budgets, cursor semantics, artifact visibility classes, redaction rules, decision-version behavior, and stale-content behavior;
- retain the existing frozen, redacted, SHA-256-bound full-response cursor and exact reconstruction tests unchanged as the explicit full-view compatibility path.

Measure serialized bytes, response construction time, SQLite query time, JSON blobs selected and decoded, peak Python allocations, p50/p95 latency, request bytes, connector-visible bytes, and full-evidence hashes.

No production contract change occurs in CF1.0.

### CF1.1 - Scalar run summaries and stable compact lists

Status: **complete**.

Completion decision:

- scalar SQL-backed summary, list, and control-snapshot queries use explicit compact projections and do not select or decode authoritative JSON blobs, lease tokens, or run directories;
- additive public `summary` and `summary_list` operations enforce 6-KB and 12-KB serialized UTF-8 ceilings while preserving every legacy full operation unchanged;
- compact list membership is frozen by a row-ID watermark, scalar state may refresh between pages, and opaque keyset cursors bind filters, ordering, view, projection version, budget, snapshot, final key, and expiry;
- the measured `created_at DESC, run_id DESC` index removes the temporary ordering B-tree and accelerates every representative filter shape; the redundant repository/status composite candidate is rejected;
- each fetched list row is projected once during byte fitting, avoiding repeated redaction and truncation work;
- on the live 3,247-row run database, compact twenty-run responses measured 97.15 percent smaller and p95 latency measured 34.19 ms versus 60.42 ms for the legacy list, a 43.41 percent improvement;
- acceptance is green with 1,333 tests passed, 5 skipped, and no broken Python requirements.

- Add store-level scalar query methods for one run summary, paginated run summaries, and one control snapshot using explicit column lists.
- Compact queries must not select or decode `input_json`, `progress_json`, `result_json`, worker lease tokens, run directories, protected evidence, full argv, environment, or reviewed scripts.
- Calculate elapsed time, heartbeat age, stale-worker state, and other derived control values from scalar timestamps and identity fields without loading JSON blobs.
- Add stable keyset pagination ordered by an immutable tuple such as `created_at DESC, run_id DESC`; do not use offsets.
- Bind the opaque compact-list cursor to filters, ordering, view version, byte budget, snapshot boundary, final sort key, and expiry.
- Define whether compact list membership is frozen while item states refresh or whether the whole page is frozen; test that inserts and state changes cannot duplicate, skip, or reorder entries incorrectly.
- Set the default public list limit to 10 and the public maximum to 100.
- Add only measurement-justified indexes supporting repository, status, creation time, and run-ID filtering.
- Keep the existing archival full-row and frozen full-response path available explicitly and hash-identical.

### CF1.2 - Compact control, decision-version polling, and delta events

Status: **complete**.

Completion decision:

- decision-relevant phase, lifecycle, process-attachment, cancellation, lock-ownership, reconciliation, and terminal-publication changes advance `state_version` atomically with the underlying state mutation;
- same-phase progress, output heartbeats, ordinary worker heartbeats, and repository-lock heartbeats remain version-quiet, so conditional polling is not invalidated by liveness noise;
- repository-lock acquisition is durably bound once to the run, owner changes and release advance the version transactionally, and startup reconciliation can repair interrupted legacy binding idempotently;
- public `control` uses explicit scalar SQL with zero authoritative JSON decoding, an 8-KB full-response ceiling, and deterministic matching-`if_state_version` envelopes below 1 KB before process probes or lock lookup;
- `last_output_at` and `cancellation_requested_at` are scalar-mirrored with tolerant backfill; the live 3,265-row database backfilled 637 historical values with zero mismatches;
- legacy `after_id` event polling remains supported, while the public default is now 20 events with a maximum of 500, ascending `id` ordering, `next_after_id`, `next_cursor`, and `has_more`;
- opaque event cursors are run-bound, projection- and budget-bound, checksum-protected, and expire after five minutes; malformed, checksum, run-mismatch, missing-anchor gap, ahead-of-latest, and expiry failures are explicit;
- event messages and nested data are redacted and bounded, each event is projected once, byte fitting removes only a suffix, and a resized page regenerates its cursor from the final event actually returned;
- event pages enforce a 12-KB serialized UTF-8 ceiling without changing authoritative event storage or the legacy internal event-list API;
- after the controlled server restart and connector refresh, live capabilities exposed compact summaries, conditional control, and event cursors under capability epoch `5f614429d00e-42bdb69d96fb`;
- live acceptance returned a 409-byte unchanged control envelope, a 2,457-byte six-event page, and a deterministic 957-byte empty continuation preserving its anchor and expiry;
- focused validation reported 106 passed; the complete repository suite reported 1,341 passed and 5 skipped; `python -m pip check` reported no broken requirements.

### CF1 rollout choke-point remediation

Status: **required cross-cutting CF1 exit gates**. These findings do not reopen the durable execution architecture or create a separate reliability roadmap. Their implementation belongs to CF1.3-CF1.7 as assigned below.

1. **One compact engineering preflight — CF1.6**
   - Add one read-only bounded operation returning running, queued, and launch-pending work; conflicting repository locks; branch and HEAD; tracked-worktree cleanliness; collapsed tool-owned counts; and the live capability epoch.
   - The default response must be at most 12 KB, expose exact-detail continuation only when requested, and replace the current four-or-more-call preflight sequence for ordinary repository work.

2. **Compact managed-write results — CF1.6**
   - `repo_apply` and related write gateways must return changed files, commit hash, rollback status, validation summary, and collapsed preserved-work counts by default.
   - Do not repeat every preserved `.codex-tmp` path through top-level fields, nested manifests, and commit reports. The ordinary managed-apply response must be at most 12 KB; an explicit evidence handle provides the complete attribution manifest.

3. **Meaningful hash-bound commit metadata — CF1.6**
   - Carry a caller-supplied commit title and optional description in the preview bundle or apply contract, bind them to the opaque preview identity, validate their size and content, and retain the current generic title only as a safe fallback.
   - Acceptance must prove that replay cannot alter commit metadata and that ordinary git history identifies the actual batch rather than only `apply_previewed_repo_change`.

4. **Unambiguous repository-bound command execution — CF1.6**
   - For a repository-scoped PowerShell request, omission of `working_directory` should resolve to the registered repository root or fail with a schema-level message before durable launch.
   - Tool descriptions and request contracts must state that `argv` belongs to the selected executable profile; the `powershell` profile receives PowerShell arguments rather than an arbitrary child executable argv.
   - Prefer dedicated allowlisted profiles for routine `pytest` and `pip check` validation so callers do not need shell-wrapper syntax.

5. **Manifest-bound output compatibility — CF1.4**
   - Route `run_query(output)` through the authoritative artifact resolver so executable-profile `stdout.bin` and `stderr.bin` are retrievable under the same bounded compatibility operation as text outputs.
   - Acceptance includes a successful executable-profile run where only manifest-listed binary stream artifacts exist; an empty or unavailable output response is a failure when the manifest proves output exists.

6. **Compact terminal default — CF1.3 and CF1.4**
   - The ordinary terminal path must use the source-hash-bound compact projection rather than echoing full argv, executable identity, complete stdout, and provider-specific internals.
   - Complete terminal result and exact stream bytes remain available only through explicit full-result or artifact evidence retrieval.

7. **Schema-operation drift after connector refresh — CF1.7**
   - Verify the connector-loaded operation names and input schemas against the live public operation inventory after every connector refresh; a matching aggregate schema identity is insufficient when an operation is missing, renamed, or structurally stale.
   - Acceptance requires zero missing, extra, or schema-mismatched operations across two consecutive fresh discovery passes, and any drift must fail explicitly with the affected operation names and bounded refresh guidance.

8. **Strong mixed-newline diagnostics — CF1.5**
   - Repository reads, previews, and validators that inspect text must report mixed `CRLF`, `LF`, and lone `CR` content with counts and affected line locations or bounded ranges rather than one ambiguous newline label.
   - Acceptance uses fixtures containing all three newline forms and proves exact counts, the first 20 affected locations or ranges, an explicit truncation indicator, and a diagnostic response no larger than 8 KB.

9. **No accidental whole-file newline normalization — CF1.5**
   - Repository preview and apply paths must preserve untouched byte ranges and existing newline sequences unless newline normalization is an explicit, hash-bound requested operation.
   - Acceptance edits one bounded region in each mixed-newline fixture and proves byte-for-byte equality outside the intended edit, unchanged newline counts outside that region, and an explicit preview warning before any requested whole-file normalization.

10. **Immediate managed-apply acknowledgement — CF1.6**
   - `repo_apply` must durably record the transaction and return an immediate compact acknowledgement with transaction ID, accepted state, preview identity, repository identity, and polling operation before connector transport timeout can obscure whether the mutation was accepted.
   - Acceptance injects a post-acceptance apply delay beyond the connector request timeout, receives the acknowledgement within 2 seconds and below 4 KB, then reaches one unambiguous terminal result through compact polling without replaying the mutation.

11. **Bounded validator timeout and error schemas — CF1.6**
   - Every dedicated validator schema must expose bounded timeout control and return compact structured validation errors with counts, representative failures, truncation state, and an evidence handle for exact diagnostics.
   - Acceptance proves caller-selected timeouts are enforced within the requested limit plus 1 second, timeout is distinct from validation failure, and 1,000 synthetic failures produce an ordinary response no larger than 12 KB while exact errors remain retrievable.

12. **Bounded legacy terminal diagnosis — CF1.6**
   - Ordinary terminal reads, including legacy diagnosis paths that can currently exceed 30 KB, must use the bounded compact terminal projection rather than returning the authoritative full result or complete diagnostic streams.
   - Acceptance uses a legacy terminal result with at least 30 KB of diagnostics, keeps the ordinary response at or below 12 KB, preserves terminal status and failure classification, and reconstructs the exact complete diagnosis only through explicit evidence retrieval.

13. **Explicit search-text file scope — CF1.5**
   - `search_text` must define a first-class repository-relative file-scope input, distinguish exact-file scope from directory and pattern scope, and reject ambiguous or conflicting scope combinations before scanning.
   - Acceptance proves one exact-file search scans only that file, reports the resolved scope in the compact envelope, returns no matches from sibling files, and rejects conflicting file and directory scope with a schema-level response below 4 KB.

14. **Build and schema convergence integrity — CF1.7**
   - Expose distinct identities for source revision, running service build, public tool schema, connector-loaded schema, and discovery-cache generation; do not overload one ambiguous `schema_hash` when the public discriminator set changes.
   - After restart or refresh, capability discovery, connector invocation, and tool-resource discovery must converge on the same source, service, public-schema, connector-schema, and discovery-cache identity set. Acceptance requires two consecutive fresh discovery passes with exact identity agreement; a mismatch fails explicitly within one pass with the divergent identities and bounded refresh guidance rather than silently serving stale contracts.

15. **Bounded knowledge freshness — CF1.6 and CF1.7**
   - Managed writes must expose a compact knowledge-freshness result with source generation and stale reason, plus an explicit bounded refresh action or recommendation.
   - Do not inline a full knowledge rebuild into the write response. Acceptance proves that the repository knowledge generation can be advanced deliberately and that callers can detect stale knowledge without inspecting a giant apply payload.

Required acceptance evidence:

- one-call preflight produces the same conflict decision as the legacy multi-call sequence;
- an apply preserving at least 100 tool-owned files remains within its response ceiling and exposes the exact full manifest separately;
- managed commit metadata is hash-bound and visible in `git log`;
- repository-bound PowerShell validation succeeds without ambiguous executable semantics;
- manifest-listed `.bin` output is retrievable through the compatibility output path;
- connector operation names and input schemas match the live inventory after refresh;
- mixed-newline diagnostics are exact and bounded, and bounded edits preserve untouched bytes and newline sequences;
- delayed managed apply acknowledges within 2 seconds and completes through compact polling without replay;
- validator timeouts are enforced and 1,000 validation failures remain within 12 KB with exact evidence retrieval;
- a legacy terminal diagnosis larger than 30 KB returns a compact projection no larger than 12 KB;
- exact-file `search_text` scope excludes sibling files and rejects conflicting scope inputs;
- source, service, public-schema, connector-schema, and discovery-cache identities agree after refresh;
- stale knowledge is visible and deliberately refreshable without unbounded write responses.

### CF1.3 - Source-hash-bound terminal public projection

Status: **complete; exercised end to end by `tests/test_chat_footprint_acceptance.py`**.

- Add `public_result_json`, `public_result_schema_version`, `public_result_source_sha256`, and `public_result_status` or equivalent durable fields.
- Materialize one deterministic, schema-versioned, tool-aware public projection when the authoritative terminal result publishes.
- Bind the projection to the complete authoritative `result_json` SHA-256 and preserve `result_json` byte-for-byte.
- Include bounded normalized outcome fields capable of distinguishing success, partial completion, validation failure, policy denial, needs-input, cancellation requested, cancellation verified, cancellation uncertain, infrastructure failure, cleanup incomplete, ambiguous side effect, and reconciliation required.
- Enforce deterministic per-field UTF-8 byte limits for summaries, errors, risks, changed files, tests, diagnostics, and artifact references; truncation must expose original byte count and an exact evidence handle.
- A projector failure must never block authoritative terminal publication. Publish a tiny bounded fallback envelope containing terminal state, source-result hash, projection error classification, and evidence handles.
- Reuse a projection only when source hash and schema version match; rebuild old projections lazily and persist them only through a safe compare-and-set path.
- Keep current pending-result behavior compatible while ensuring completed runs never require decoding the complete result merely to serve the compact projection.

### CF1.4 - Manifest-secured exact evidence retrieval

Status: **implementation complete for manifest-bound output compatibility; the previously blocking full-suite Hermes persistent-worker PID failure was root-caused and fixed on 2026-07-22 (venv launcher redirection, see H2)**.

Current implementation and validation evidence:

- `run_query(output)` now resolves executable-profile `stdout.bin` and `stderr.bin` only through the durable staging manifest, validates run identity, classification, containment, regular-file and symlink safety, and returns bounded redacted text tails with source size, SHA-256, manifest generation, and opaque artifact identity without exposing local paths;
- runs without a staging manifest retain compatibility through an explicit fixed-name legacy adapter for `stdout.txt` and `stderr.txt`; a present but invalid manifest fails rather than falling back to guessed filenames;
- focused validation passed with 74 combined artifact-resolver and job-manager tests after formatting, plus 3 executable-staging tests and 26 server tests; the exact unrelated Hermes failure passed alone with 1 test;
- two complete repository runs each reported 1,367 passed and 5 skipped, with the same unrelated `tests/test_hermes_service_process.py::test_one_verified_process_serves_multiple_bound_requests` PID assertion failing only in the full-suite context; H2 remains paused and untouched;
- `python -m pip check` reported no broken requirements; repository-virtual-environment Ruff format and lint checks passed for the two new Python files, and all four changed Python files compiled successfully. Legacy-file whole-file formatting was deliberately not retained because it produced unrelated churn;
- no new CF1 retrieval choke point was discovered. The full-suite-only Hermes process instability remains an acceptance blocker to resolve in its owning lane or test-isolation boundary, not authorization to resume H2 during CF1.4.

Add narrow run-evidence operations:

```text
artifact_index
artifact_tail
artifact_range
artifact_search
request_summary
request_full
result_full
```

- Resolve every artifact through an authoritative run/staging manifest or an explicitly defined legacy-output manifest adapter; never guess filenames from caller input.
- Support current text outputs and executable-profile manifest-bound binary outputs, including `.txt` and `.bin`, without exposing local filesystem paths.
- Preserve the existing bounded `run_query(output)` behavior as a compatibility operation, but route it through the same validated resolver rather than assuming only `stdout.txt` and `stderr.txt`.
- Use opaque artifact IDs bound to run ID, artifact identity, classification, immutable size, SHA-256, encoding/binary mode, and manifest generation.
- Enforce run-directory containment, manifest membership, regular-file checks, symlink and traversal rejection, public/protected classification, secret redaction, and reviewed-script exclusion.
- Apply strict limits to bytes scanned, bytes returned, search duration, match count, and continuation lifetime.
- Define byte-range semantics for binary evidence and character/line semantics for decoded text, with exact hashes and continuation metadata for reconstruction.
- Distinguish artifact existence, trusted-internal retrievability, and public ChatGPT retrievability.
- MCP resource links remain optional until connector acceptance proves that they reduce transcript cost without duplicating payloads.

### CF1.5 - Repository progressive disclosure and content-bound continuation

Status: **CF1.5 repository read, search, and diff slices complete; CF1.6 remains paused**.

First-slice implementation and validation evidence:

- `repo_query(read_files)` now streams text windows instead of rejecting files above 500 KB or loading complete files into memory, with a 300-line default window, 48-KB default and minimum response budget, and 128-KB hard ceiling;
- responses expose line and byte bounds, next line and byte offsets, content SHA-256, bounded opaque continuation, explicit truncation reason, serialized payload size, and structured `stale_content` rejection when a continuation's source hash no longer matches;
- continuations checksum-bind repository-relative path, source hash, mode, next line, and next byte; traversal, blocked paths, binary files, symlinks, secret redaction, explicit line ranges, and legacy small-file newline behavior remain covered;
- focused file-read validation passed with 70 tests, including a one-megabyte single-line fixture, byte continuation, exact multi-window reconstruction, cursor tampering, stale-file rejection, redaction compatibility, and a 48-KB serialized response-budget fixture; adjacent server and gateway-schema validation passed with 91 tests, followed by a 36-test gateway-model rerun after the final schema-bound assertions;
- the complete repository suite reported 1,371 passed and 5 skipped, with only the already-documented full-suite-only `tests/test_hermes_service_process.py::test_one_verified_process_serves_multiple_bound_requests` PID assertion failing; H2 remains paused and untouched;
- scoped Ruff lint, Python compilation, `git diff --check`, and `python -m pip check` passed. Whole-file Ruff formatting remains intentionally unapplied because it would rewrite unrelated legacy formatting;
- no new choke point was added. Windows `CRLF` read normalization was caught during focused validation and restored for compatibility; mixed-newline diagnostics and write-normalization protection remain assigned to existing choke points 8 and 9.

Search-slice implementation and validation evidence:

- `repo_query(search_text)` now has a bounded public path with a 16-KB response ceiling, 800-character redacted snippets, explicit `partial`/`timeout` flags, and a structured `search_timeout` result that preserves partial hits and a continuation when the time budget expires;
- exact repository-relative `file_path` scope is first-class, mutually exclusive with directory/pattern scope, and reports the resolved scope without scanning sibling files; legacy directory and ripgrep callers remain compatible when they do not request the bounded contract;
- opaque search cursors checksum-bind the query, scope, patterns, case mode, result limit, deterministic file ordering, and a SHA-256 worktree snapshot; a changed file, added/deleted candidate, or mismatched request returns bounded `stale_content` rather than mixing result generations;
- focused repository-reader validation passed with 72 tests, including exact-file exclusion, cursor continuation, tamper rejection, stale-result rejection, and redacted bounded results; gateway-model validation passed with 36 tests after adding the scope, cursor, and response-budget contract;
- native Python compilation passed for all changed Python files. Ruff lint still reports only the pre-existing unused `server.py` import, while whole-file formatting remains intentionally unapplied because it would rewrite unrelated legacy formatting. Pytest evidence is retained from Soma runs; `.codex-tmp/` remains preserved;
- no new choke point was discovered. Search scope/continuation is now covered by existing choke point 13; diff behavior remains explicitly deferred to the next CF1.5 slice.

Diff-slice implementation and validation evidence:

- `repo_query(diff)` now supports a bounded summary view with changed-file additions/deletions, indexed hunk metadata, a SHA-256 snapshot identity, and a 32-KB response ceiling; path-scoped and staged selection use the existing repository-relative safety validation;
- selected hunk and explicit full views require the summary's immutable `snapshot_id`; retrieval recomputes the current diff and returns bounded `stale_snapshot` evidence instead of mixing generations, while legacy raw diff callers remain unchanged;
- focused diff validation passed with 36 tests covering statistics, path scoping, hunk indexes, exact selected-hunk text, explicit full retrieval, stale snapshots, and legacy Git behavior; gateway-model validation passed with 36 tests and server regressions with 26 tests;
- native Python compilation, `python -m pip check`, and `git diff --check` passed. Ruff passes for changed files other than the pre-existing unused `server.py` import; whole-file formatting remains intentionally unapplied to avoid unrelated churn;
- the complete repository suite reported 1,377 passed and 5 skipped, with only the already-documented Hermes persistent-process PID assertion failing; no CF1.5 diff test failed and H2 remains paused;
- no new choke point was discovered. Diff snapshot identity and hunk retrieval satisfy the existing CF1.5 immutable-diff requirements; CF1.6 has not started.

Chat-facing defaults:

```yaml
file_reads:
  default_combined_content: 48 KB
  hard_public_ceiling: 128 KB
  default_file_window: 300 lines
  maximum_batch_items: 10
search:
  default_results: 20
  hard_max_results: 100
  default_snippet_characters: 800
  hard_snippet_characters: 2000
  default_response_budget: 16 KB
diffs:
  ordinary_budget: 32 KB
```

- Reuse the current relative-path validation, blocked-root rules, symlink/junction rejection, binary detection, secret redaction, line-range support, and SHA-256 reporting.
- Replace the blanket large-text-file rejection with bounded streaming reads so an exact requested window can be served without loading the full file into memory.
- Return line and byte offsets, `next_start_line`, `next_byte_offset`, content SHA-256, total lines when cheaply available, size, truncation reason, and an opaque continuation bound to the same content identity.
- Reject continuation with a stale-content response when the file hash or worktree snapshot changes; never concatenate ranges from different file versions.
- Enforce batch budgets before and during reading rather than reading up to 2 MB and blanking later items after the limit is exceeded.
- Use at most 10 default batch items while retaining an explicit bounded compatibility mode where required.
- Bind repository-search continuation to query, directory, patterns, case sensitivity, ordering, worktree snapshot identity, byte budget, last result key, and expiry.
- Return bounded redacted snippets under the 16-KB default response budget with `next_cursor`, `has_more`, and explicit timeout/partial-result semantics.
- Replace ordinary raw-diff delivery with changed-file statistics, a frozen diff snapshot, bounded hunk metadata, selected exact hunks, and explicit full retrieval through that same snapshot.
- Keep path-scoped and staged diff support, but ensure all statistics, hunk indexes, selected hunks, and full retrieval reference one immutable diff identity.
- Preserve `repo_query(compact_status)` as the compact status pattern and bring the other repository reads under equivalent deterministic envelopes.

### CF1.6 - Remaining public gateway conformance and compact envelopes

First independently reviewable slice — bounded `run_query(output)`:

- ordinary `RunQueryRequest(operation="output")` now selects a compact view with a fixed 12-KB serialized UTF-8 budget, preserving redacted stream tails, artifact metadata, truncation state, and evidence handles;
- explicit `view="full"` and legacy direct `get_run_output` calls retain the existing tail and manifest-bound evidence behavior, so exact protected output remains deliberately retrievable;
- focused validation passed with 72 `JobManager` tests, 36 gateway-model tests, and 26 server regressions;
- the complete repository suite reported 1,378 passed and 5 skipped, with only the already-documented Hermes persistent-process PID assertion failing. Native compilation, `python -m pip check`, and `git diff --check` passed; Ruff reports only pre-existing unused imports in `job_manager.py` and `server.py`;

Second independently reviewable slice — single bounded preflight:

- `run_query(operation="preflight", repo_name=...)` now combines fresh compact tracked-worktree state (branch, HEAD, cleanliness, changed-file and collapsed tool-owned counts), running/queued/launch-pending run summaries, repository locks, and the live capability epoch in one read-only projection;
- the response is capped at 12 KB with explicit truncation and byte-count fields; existing individual status, list, lock, summary, and full-evidence operations remain available for detail retrieval;
- focused Soma pytest validation passed with 36 gateway-model tests, 27 server tests, and 6 gateway-inventory tests; the complete suite reported 1,379 passed and 5 skipped, with only the already-documented Hermes persistent-process PID assertion failing. Native compilation, `python -m pip check`, and `git diff --check` passed; Ruff reports the same pre-existing unused import in `server.py`.

Third independently reviewable slice — immediate managed-apply acknowledgement:

- `repo_apply` now records a durable `repo_apply` run and repository lock before returning a compact acknowledgement containing transaction/run identity, accepted state, preview or cleanup identity, bounded control polling, and explicit terminal evidence access;
- the durable worker reuses the existing hash-verified apply, rollback, commit, wiki-staleness, and manifest lifecycle behavior; duplicate requests are refused while the same transaction is active, and completed manifest replay remains idempotent without reapplying files;
- the acknowledgement is capped at 4 KB and the operation inventory records its durable-input and bounded-response contract. Soma pytest validation passed with 28 server tests, 6 gateway-inventory tests, 72 job-manager tests, and 36 gateway-model tests; the complete suite reported 1,379 passed and 5 skipped, with only the already-documented Hermes persistent-process PID assertion failing. Native compilation, `python -m pip check`, and `git diff --check` passed; Ruff reports only pre-existing unused imports.

Fourth independently reviewable slice — compact managed-apply terminal projection:

- terminal `repo_apply` results now expose bounded operation/patch identity, changed-file projection, commit hash, idempotent replay state, rollback status when present, validation pass/fail counts, and collapsed preserved/remaining-work counts;
- raw stdout/stderr and full validation payloads remain evidence-only, while the existing public-result UTF-8 budget, redaction, source hash, and explicit evidence handle continue to apply;
- focused Soma pytest validation passed with 20 public-result materialization tests. Native compilation, Ruff, and `git diff --check` passed; `python -m pip check` remains green from the preceding slice.

Fifth independently reviewable slice — repository-bound local executable defaults:

- local executable-profile runs that omit `working_directory` now bind their process current directory to the registered repository root when the profile uses `service_default`; arbitrary and fixed directory policies retain their existing validation rules;
- the durable input records the resolved absolute directory before launch, preventing an omitted directory from silently inheriting the service process directory while preserving explicit full evidence and existing profile security checks;
- focused Soma pytest validation passed with 7 executable-profile tests. Native compilation and `git diff --check` passed; Ruff reports the same pre-existing unused import in `job_manager.py`.

Sixth independently reviewable slice — hash-bound automatic commit metadata:

- automatic managed-write commits now include a deterministic SHA-256 of the exact normalized changed-path batch alongside the durable run ID in the commit body;
- the structured commit report exposes a metadata hash, and the recorded Git commit is verified to contain the same run and changed-path binding, so replay cannot substitute a different batch identity silently;
- focused Soma pytest validation passed with 36 Git-tool tests. Native compilation, Ruff, and `git diff --check` passed; the only Ruff finding remains the pre-existing unused import in `job_manager.py`.

Seventh independently reviewable slice — bounded dedicated-validator controls:

- Python compile, Bash syntax, and JSON validation gateway schemas now accept an explicit bounded `timeout_seconds` control, persist it in the durable request, and enforce the same 1–604,800-second envelope before launch;
- validator terminal results include a compact structured validation summary with pass/fail state, error count, representative redacted diagnostic text, and truncation state, while full streams remain available only through explicit evidence retrieval;
- focused Soma pytest validation passed with 36 gateway-model tests, 21 public-result tests, and 28 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the three pre-existing unused imports in `job_manager.py`, `job_worker.py`, and `server.py`.

Eighth independently reviewable slice — bounded ordinary result reads:

- `run_query(operation="result")` now routes to the bounded source-hash-bound terminal projection by default, preventing legacy diagnosis payloads from returning oversized authoritative JSON through the ordinary gateway;
- `view="full"` remains an explicit authoritative retrieval path, and callers that supply the existing chunk cursor are promoted to that full path for compatibility and exact reconstruction;
- focused Soma pytest validation passed with 5 public-result gateway tests. Native compilation and `git diff --check` passed; Ruff reports the pre-existing unused import in `server.py`.

Ninth independently reviewable slice — bounded knowledge search freshness envelope:

- repository knowledge search now applies a deterministic 12-KB UTF-8 response budget after capability metadata is attached, preserving generation/head/branch freshness identities while collapsing excess wiki and memory hits;
- the response reports `response_bytes` and `truncated`, and existing repository-scoped search semantics, stale-generation metadata, and explicit wiki-page retrieval remain unchanged;
- focused Soma pytest validation passed with 7 knowledge-integration tests. Native compilation, Ruff, and `git diff --check` passed; pip check remains green from the preceding slice.

Tenth independently reviewable slice — caller-bound preview commit metadata:

- patch previews now accept bounded caller-supplied commit title and description fields, validate them with the existing commit-message policy, and persist them in the protected manifest together with an opaque `Preview-ID` binding;
- preview apply returns only the manifest-bound metadata, and managed commit finalization preserves that title while appending the durable run ID and deterministic changed-path SHA-256, preventing replay or a later request from substituting commit identity;
- focused Soma pytest validation passed with 92 repository-writer tests, 37 Git-tool tests, 36 gateway-model tests, and the legacy server compatibility regression. The full-suite run before that compatibility adjustment reported 1,386 passed and 5 skipped with two failures; the focused rerun removed the preview-wrapper failure, leaving only the already-documented Hermes persistent-process PID assertion. Native compilation, `git diff --check`, and `python -m pip check` passed; Ruff reports only the pre-existing unused imports.

Eleventh independently reviewable slice — bounded mixed-newline diagnostics:

- patch previews now report exact old/new LF, CRLF, and bare-CR counts, whether each version is mixed, and the first 20 affected line locations with total-count and truncation fields;
- diagnostic projection is capped at 8 KB before returning or persisting preview metadata, while the existing byte-preserving default and explicit legacy normalization behavior remain unchanged;
- focused Soma pytest validation passed with 94 repository-writer tests. Native compilation, Ruff, and `git diff --check` passed; pip check remains green.

Twelfth independently reviewable slice — explicit normalization-risk warning:

- mixed-newline patch previews now warn before an explicitly requested normalized edit would rewrite the file’s newline forms, while the default preserved mode remains byte-preserving and apply still requires the existing expected content hash;
- the warning is copied into the protected preview manifest and remains non-fatal, so callers can deliberately request legacy normalization without confusing it with an accidental default behavior;
- focused Soma pytest validation passed with 95 repository-writer tests. Native compilation, Ruff, pip check, and `git diff --check` passed.

Thirteenth independently reviewable slice — bounded lock reads:

- `run_query(operation="locks")` now defaults to a compact lock projection with bounded item count, a caller-selected 1–64-KB response budget, explicit `has_more`/truncation metadata, and response byte accounting;
- `view="full"` preserves the existing complete lock evidence path, while the operation inventory and gateway schema expose the compact/full distinction explicitly;
- focused Soma pytest validation passed with 29 server tests and 36 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fourteenth independently reviewable slice — bounded repository file lists:

- `repo_query(operation="list_files")` now defaults to a compact repository-relative path projection with a caller-selected 1–64-KB serialized UTF-8 budget, explicit `count`/`total_count`, `has_more`, truncation, and response byte accounting;
- the direct `list_repo_files` compatibility wrapper remains full by default, while `view="full"` preserves complete path evidence and the operation inventory records the compact/full distinction;
- focused Soma pytest validation passed with 30 server tests, 37 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifteenth independently reviewable slice — bounded recent-file lists:

- `repo_query(operation="recent_files")` now defaults to a compact recent-file projection with a caller-selected 1–64-KB serialized UTF-8 budget, explicit `count`/`total_count`, `has_more`, truncation, and response byte accounting;
- the direct `get_recently_modified_files` compatibility wrapper remains full by default, while `view="full"` preserves complete recent-file evidence and the operation inventory records the compact/full distinction;
- focused Soma pytest validation passed with 31 server tests, 38 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixteenth independently reviewable slice — bounded commit-log lists:

- `repo_query(operation="log")` now defaults to a compact commit projection with a caller-selected 1–64-KB serialized UTF-8 budget, explicit `count`/`total_count`, `has_more`, truncation, and response byte accounting;
- the direct `git_log` compatibility wrapper remains full by default, while `view="full"` preserves complete commit-log evidence and the operation inventory records the compact/full distinction;
- focused Soma pytest validation passed with 32 server tests, 39 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventeenth independently reviewable slice — bounded repository status:

- `repo_query(operation="status")` now defaults to a compact live-status projection with a caller-selected 1–64-KB serialized UTF-8 budget, preserved changed-file totals, `has_more`, truncation, and response byte accounting;
- the direct `inspect_repo_status` compatibility wrapper remains full by default, while `view="full"` preserves complete status evidence and the operation inventory distinguishes it from the existing compact-status operation;
- focused Soma pytest validation passed with 33 server tests, 40 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighteenth independently reviewable slice — bounded managed-patch status:

- `repo_query(operation="patch_status")` now defaults to a compact managed-patch lifecycle projection with a caller-selected 1–64-KB serialized UTF-8 budget, changed-file/error counts, `apply_ok`, `has_more`, truncation, and response byte accounting;
- the direct `get_patch_status` compatibility wrapper remains full by default, while `view="full"` preserves complete patch manifest evidence and compact mode omits full apply/error payloads;
- focused Soma pytest validation passed with 34 server tests, 41 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Nineteenth independently reviewable slice — bounded compact repository status:

- `repo_query(operation="compact_status")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget while preserving its compatibility-shaped status fields, and reports `truncated`, `has_more`, `response_budget_bytes`, and `response_bytes` when the projection is reduced;
- the compact status operation inventory now records the bounded-object response contract and 12-KB default/maximum budget; existing direct status behavior and tool-owned-field filtering remain unchanged;
- focused Soma pytest validation passed with 35 server tests, 42 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twentieth independently reviewable slice — bounded Docker inspection:

- `docker_query(operation="inspect")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims redacted stdout/stderr and diagnostic fields deterministically while preserving the existing inspection result shape, explicit truncation state, and command safety checks;
- the Docker inspection inventory now records a bounded-object response contract with a 12-KB default/maximum budget; capabilities, health, and direct inspection compatibility remain available;
- focused Soma pytest validation passed with 36 server tests, 43 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-first independently reviewable slice — bounded Cloudflare inspection:

- `cloudflare_query(operation="inspect")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and deterministically trims paginated provider results or diagnostic metadata while preserving profile authorization, page/per-page compatibility, and explicit truncation state;
- the Cloudflare inspection inventory now records a bounded-object response contract with a 12-KB default/maximum budget and retains page-number pagination metadata;
- focused Soma pytest validation passed with 37 server tests, 44 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-second independently reviewable slice — bounded H4 candle retrieval:

- `trading_query(operation="h4_candles")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims completed candles deterministically while preserving the configured demo-terminal checks, completed-count limit, and developing-candle shape;
- the H4 candle inventory now records a bounded-object response contract with a 12-KB default/maximum budget and limit-only pagination semantics;
- focused Soma pytest validation passed with 37 server tests, 45 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-third independently reviewable slice — bounded historical-tick retrieval:

- `trading_query(operation="historical_ticks")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims the returned tick list deterministically while preserving timezone-aware range validation and the configured demo-terminal checks;
- the historical-tick inventory now records a bounded-object response contract with a 12-KB default/maximum budget and explicit truncation metadata;
- focused Soma pytest validation passed with 37 server tests, 46 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-fourth independently reviewable slice — bounded supervisor events:

- `supervisor_query(operation="events")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the ordered event list, preserving supervisor identity, event ordering, and the existing item limit;
- events and notifications are now represented separately in the gateway inventory, with the event operation carrying a bounded-object 12-KB default/maximum budget while notification compatibility remains unchanged;
- focused Soma pytest validation passed with 38 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-fifth independently reviewable slice — bounded supervisor notifications:

- `supervisor_query(operation="notifications")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the notification list, preserving delivery-status filtering, ordering, supervisor identity, and the existing item limit;
- the notification inventory now records the bounded-object 12-KB default/maximum response contract alongside the previously bounded event operation;
- focused Soma pytest validation passed with 39 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-sixth independently reviewable slice — bounded workflow events:

- `workflow_query(operation="events")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the ordered event list, preserving workflow identity, event ordering, and the existing 100–500 item limit;
- the workflow event inventory now records a bounded-object response contract with a 12-KB default/maximum budget and explicit truncation metadata;
- focused Soma pytest validation passed with 40 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-seventh independently reviewable slice — bounded SSH inspection:

- `ssh_inspect(operation="inspection")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims redacted stdout/stderr and diagnostics deterministically while preserving host/path/target validation, bounded tail input, and existing structured health/telemetry variants;
- the SSH inventory now separates inspection from structured health/telemetry and records a bounded-object 12-KB default/maximum response contract for inspection;
- focused Soma pytest validation passed with 41 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-eighth independently reviewable slice — bounded Trading Lab signal list:

- `trading_signal_list` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the immutable journal projection, preserving its limit and record fields;
- the signal-list inventory now records a bounded-object response contract with a 12-KB default/maximum budget and explicit truncation metadata;
- focused Soma pytest validation passed with 42 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-ninth independently reviewable slice — search contract convergence:

- the authoritative CF1 gateway inventory now matches the implemented `repo_query(operation="search_text")` contract: fixed 16-KB UTF-8 budgeting, cursor pagination, exact-file scope, snapshot/hash-bound continuation, and explicit timeout/partial-result reporting;
- focused Soma pytest validation passed with 6 gateway-inventory tests and 47 gateway-model tests. Native compilation, pip check, `git diff --check`, and focused Ruff checks passed; no runtime search behavior changed in this documentation/contract-convergence slice.

Thirtieth independently reviewable slice — bounded Docker capability discovery:

- `docker_query(operation="capabilities")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims capability lists deterministically while preserving policy gates, configured profiles, and the direct health path;
- the Docker inventory now separates capabilities from health and records a bounded-object 12-KB default/maximum response contract for capability discovery;
- focused Soma pytest validation passed with 43 server tests, 48 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-first independently reviewable slice — bounded Cloudflare capability discovery:

- `cloudflare_query(operation="capabilities")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims capability lists deterministically while preserving authorized profile/action metadata and the direct health path;
- the Cloudflare inventory now separates capabilities from health and records a bounded-object 12-KB default/maximum response contract for capability discovery;
- focused Soma pytest validation passed with 44 server tests, 49 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-second independently reviewable slice — bounded Docker health:

- `docker_query(operation="health")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims verbose engine/Compose diagnostics deterministically while preserving provider health fields and the existing capability/inspection paths;
- the Docker health inventory now records a bounded-object 12-KB default/maximum response contract;
- focused Soma pytest validation passed with 45 server tests, 50 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-third independently reviewable slice — bounded Cloudflare health:

- `cloudflare_query(operation="health")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims verbose profile diagnostics deterministically while preserving profile authorization, health fields, and the capability/inspection paths;
- the Cloudflare health inventory now records a bounded-object 12-KB default/maximum response contract;
- focused Soma pytest validation passed with 46 server tests, 51 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-fourth independently reviewable slice — bounded symbol discovery:

- `trading_query(operation="symbols")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the symbol list, preserving configured demo-terminal checks and scalar trading-query behavior;
- the trading inventory now separates symbol discovery from scalar health/specification/tick operations and records a bounded-object 12-KB default/maximum response contract;
- focused Soma pytest validation passed with 46 server tests, 52 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-fifth independently reviewable slice — bounded parallel-group reads:

- `run_query(operation="group_status"|"group_result")` now defaults to a compact 12-KB UTF-8 projection that omits request and artifact payloads, bounds child summaries, and reports truncation and response-byte metadata;
- `view="full"` remains an explicit complete group/evidence path, while group query schemas and the gateway inventory now record the compact/full distinction and bounded response contract;
- focused Soma pytest validation passed with 53 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-sixth independently reviewable slice — bounded supervisor resume prompts:

- `supervisor_query(operation="resume_prompt")` now defaults to a compact 12-KB UTF-8 content projection with explicit truncation, `has_more`, original content-byte count, and serialized response-byte accounting;
- compact prompt responses omit local filesystem paths, while `view="full"` retains the existing explicit prompt/evidence path and supervisor compatibility behavior;
- focused Soma pytest validation passed with 54 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-seventh independently reviewable slice — bounded workflow snapshots:

- `workflow_query(operation="status"|"result")` now defaults to compact 12-KB UTF-8 projections with bounded step diagnostics, explicit truncation, and response-byte accounting;
- compact workflow responses omit objective, process, and artifact payloads, while `view="full"` remains explicit complete snapshot/evidence access;
- focused Soma pytest validation passed with 55 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-eighth independently reviewable slice — bounded system self-check:

- `system_query(operation="self_check")` now defaults to a compact 12-KB projection retaining per-check outcome, status, error, warning, exit-code, and duration fields with explicit truncation and response-byte accounting;
- compact self-check responses omit verbose command streams, while `view="full"` preserves explicit complete diagnostics and existing direct self-check behavior;
- focused Soma pytest validation passed with 56 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-ninth independently reviewable slice — bounded single-signal retrieval:

- `trading_signal_get` now defaults to a compact 12-KB UTF-8 projection that bounds narrative and candle-context fields and reports truncation and serialized response bytes;
- `view="full"` preserves explicit complete immutable signal-record retrieval and existing journal/idempotency behavior;
- focused Soma pytest validation passed with 57 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fortieth independently reviewable slice — bounded signal cancellation results:

- `trading_signal_cancel_before_entry` now returns the same compact 12-KB UTF-8 signal projection as single-signal reads, with bounded narrative fields and response-byte accounting;
- cancellation state transitions and immutable journal payloads remain unchanged, while `view="full"` preserves explicit complete record access;
- focused Soma pytest validation passed with 58 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-first independently reviewable slice — bounded signal submission results:

- `trading_signal_submit` now defaults to the compact 12-KB UTF-8 signal projection, bounding narrative fields and reporting truncation and response-byte metadata;
- immutable journal insertion, idempotency replay, and validation remain unchanged, while `view="full"` preserves explicit complete record access;
- focused Soma pytest validation passed with 59 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-second independently reviewable slice — bounded wiki-page retrieval:

- `knowledge_query(operation="read_wiki")` now defaults to a compact 12-KB serialized UTF-8 page projection with truncation, `has_more`, and response-byte metadata while preserving generation, freshness, and page identity fields;
- `view="full"` remains explicit complete-page access, and repository wiki validation/error behavior is unchanged;
- focused Soma pytest validation passed with 8 knowledge-integration tests, 59 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, `git diff --check`, and scoped Ruff all passed.

Forty-third independently reviewable slice — bounded knowledge search contract:

- `knowledge_query(operation="search")` now exposes a caller-selected 1–64-KB serialized UTF-8 response budget with `truncated`, `has_more`, and response-byte metadata over the existing wiki/memory freshness envelope;
- item limits, repository scoping, global-memory opt-in, and search ranking remain unchanged;
- focused Soma pytest validation passed with 8 knowledge-integration tests, 59 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, `git diff --check`, and scoped Ruff all passed.

Forty-fourth independently reviewable slice — bounded repo-commit results:

- `repo_commit` now defaults to a compact 12-KB UTF-8 mutation projection retaining operation/status, commit identity, and changed-file metadata with truncation and response-byte accounting;
- selected-file and branch-creation policy checks remain unchanged, while `view="full"` preserves explicit complete mutation metadata access;
- focused Soma pytest validation passed with 60 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-fifth independently reviewable slice — bounded supervisor snapshots:

- `supervisor_query(operation="status"|"result")` now defaults to compact 12-KB UTF-8 projections retaining lifecycle, publication, diagnostic, and link-count metadata while omitting nested plan/implementation payloads;
- `view="full"` remains explicit complete snapshot/evidence access, and supervisor lifecycle behavior is unchanged;
- focused Soma pytest validation passed with 61 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-sixth independently reviewable slice — bounded system action acknowledgements:

- `system_action(action="reload"|"rollback")` now defaults to a compact 12-KB acknowledgement retaining lifecycle status, operation counts, rollback outcome, and bounded diagnostics;
- `view="full"` preserves explicit complete lifecycle evidence access and the existing direct reload/rollback tools remain unchanged;
- focused Soma pytest validation passed with 62 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-seventh independently reviewable slice — bounded knowledge action acknowledgements:

- `knowledge_action(action="refresh_wiki"|"remember_decision")` now defaults to a compact 12-KB acknowledgement retaining lifecycle identity, freshness metadata, and page/file or memory counts while bounding diagnostics and summaries;
- `view="full"` preserves explicit complete mutation evidence access, and the existing direct wiki-refresh and decision-write functions remain unchanged;
- focused Soma pytest validation passed with 9 knowledge-integration tests, 62 gateway-model tests, and 6 gateway-inventory tests. Native compilation, Ruff, pip check, and `git diff --check` passed.

Forty-eighth independently reviewable slice — bounded repository batch reads:

- `repo_query(operation="read_files")` now publishes explicit aggregate `has_more`, `truncated_batch`, `payload_bytes`, and `response_bytes` metadata while enforcing the serialized response budget at the final boundary;
- the existing 20-file limit, streamed per-file content, redaction, hash-bound continuation, and compatibility behavior remain intact;
- focused Soma pytest validation passed with 72 repository-reader tests and 6 gateway-inventory tests. Native compilation, Ruff, pip check, and `git diff --check` passed.

Forty-ninth independently reviewable slice — bounded SSH query projections:

- `ssh_query(operation="capabilities"|"profile_preview"|"profile_status")` now defaults to compact 12-KB projections retaining host/lifecycle/hash identity and collapsing large capability diffs to counts;
- `view="full"` preserves explicit complete capability and profile evidence access, while existing internal SSH query functions and security validation remain unchanged;
- focused Soma pytest validation passed with 63 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fiftieth independently reviewable slice — bounded workflow cancellation:

- `workflow_action(action="cancel")` now defaults to the compact 12-KB workflow projection, retaining lifecycle identity and bounded step diagnostics while preserving cancellation semantics;
- `view="full"` remains explicit complete workflow evidence access, and workflow starts plus direct cancellation behavior remain compatible;
- focused Soma pytest validation passed with 64 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-first independently reviewable slice — bounded direct run cancellation:

- `cancel_run` now defaults to a compact 12-KB acknowledgement retaining run/group identity, status, and diagnostic counts while bounding process-tree details;
- explicit `view="full"` preserves complete cancellation evidence, and legacy one-argument callers plus cancellation routing remain compatible;
- focused Soma pytest validation passed with 65 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-second independently reviewable slice — bounded supervisor lifecycle mutations:

- `supervisor_action(action="resume"|"pause"|"cancel")` now defaults to compact 12-KB lifecycle projections retaining supervisor identity/status/publication metadata and bounded diagnostics;
- `view="full"` remains explicit complete supervisor evidence access, and durable lifecycle transitions remain unchanged;
- focused Soma pytest validation passed with 66 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-third independently reviewable slice — bounded scalar trading queries:

- `trading_query(operation="health"|"specification"|"tick")` now defaults to compact 12-KB scalar projections retaining provider-safe scalar fields while bounding oversized adapter payloads;
- `view="full"` remains explicit complete adapter evidence access, and existing symbols/candle/historical bounds plus provider lifecycle behavior remain unchanged;
- focused Soma pytest validation passed with 67 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-fourth independently reviewable slice — bounded system summaries:

- `system_query(operation="capabilities"|"local_model_health"|"validate_config"|"reload_status")` now defaults to compact projections retaining scalar health/configuration fields and collection counts under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete system evidence access, while `self_check` and the underlying individual system functions retain their existing behavior;
- focused Soma pytest validation passed with 68 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-fifth independently reviewable slice — bounded SSH health and telemetry:

- `ssh_inspect(operation="host_health"|"environment_probe"|"gpu_telemetry")` now defaults to compact projections retaining scalar host/health fields and collection counts under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete SSH evidence access, while bounded inspection, underlying SSH probes, and existing host security checks remain unchanged;
- focused Soma pytest validation passed with 69 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-sixth independently reviewable slice — bounded SSH profile apply:

- `ssh_action(action="profile_apply")` now defaults to a compact mutation projection retaining change/status/activation scalars and counts under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete profile-apply evidence access, while hash verification, repository locking, activation, and existing SSH action behavior remain unchanged;
- focused Soma pytest validation passed with 70 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-seventh independently reviewable slice — bounded repository previews:

- `repo_preview` now defaults to compact preview metadata retaining patch/cleanup identity, changed-line and byte statistics, diagnostic counts, and diff byte size under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete diff and validation evidence access, while opaque preview persistence, path/hash validation, and apply compatibility remain unchanged;
- focused Soma pytest validation passed with 71 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-eighth independently reviewable slice — bounded commit-range inspection:

- `repo_query(operation="commit_range")` now defaults to a compact projection retaining both commit identities, changed-file count, diff statistics, and diff byte size under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete commit-range evidence access, while full-hash validation, canonical repository binding, and legacy direct inspection remain unchanged;
- focused Soma pytest validation passed with 72 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-ninth independently reviewable slice — explicit supervisor notification evidence:

- `supervisor_query(operation="notifications")` keeps its compact item- and UTF-8-bounded default while accepting `view="full"` for complete delivery-status-filtered notification evidence;
- notification ordering, limit enforcement, supervisor identity, and existing internal bounded reads remain unchanged;
- focused Soma pytest validation passed with 73 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixtieth independently reviewable slice — capability identity convergence:

- `system_query(operation="capability_identity")` now reports source-derived and running-service build/schema/epoch identities and compares caller-supplied connector/discovery identities, returning explicit mismatch names under the compact envelope;
- convergence checks are read-only and do not reload or mutate services; existing capability discovery and system-query operations remain available, with `view="full"` preserving the complete identity record;
- focused Soma pytest validation passed with 74 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-first independently reviewable slice — operation-inventory drift check:

- capability identity now includes a deterministic operation-inventory hash and gateway count, and compares a caller-supplied connector/discovery inventory hash to report explicit operation-schema drift;
- inventory hashing normalizes operation sets deterministically, remains read-only, and preserves all existing capability identity and compact/full behavior;
- focused Soma pytest validation passed with 74 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-second independently reviewable slice — synchronous live capability discovery:

- `system_query(operation="capabilities")` now resolves the async live MCP tool listing through a safe synchronous bridge, while preserving compatibility with synchronous test/legacy providers and compact/full projections;
- discovery failures remain explicit structured errors, and no service reload or mutation is performed;
- focused Soma pytest validation passed with 75 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-third independently reviewable slice — explicit public-schema and discovery-cache identities:

- `system_query(operation="capability_identity")` now exposes distinct public-schema and discovery-cache generation identities alongside the legacy source/running capability fields;
- callers can bind connector-loaded public schema, operation inventory, and discovery-cache expectations, with bounded explicit mismatch names and preserved legacy schema checks;
- focused Soma pytest validation passed with 76 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-fourth independently reviewable slice — managed-write knowledge freshness:

- compact terminal projections for `repo_apply` now retain bounded knowledge freshness state, source and indexed generations, stale reason, and an explicit `knowledge_action(refresh_wiki)` recommendation without embedding wiki content;
- authoritative apply results and full evidence remain unchanged, while callers can detect stale knowledge directly from the ordinary managed-write projection;
- focused Soma pytest validation passed with 21 public-result tests and 46 adjacent server tests. Native compilation, pip check, `git diff --check`, and scoped Ruff passed.

Sixty-fifth independently reviewable slice — per-operation schema drift reporting:

- `system_query(operation="capability_identity")` now discovers live MCP input schemas, fingerprints each operation, and reports bounded missing, extra, and connector-schema mismatches by operation name;
- lazy knowledge-tool registration is included in the live discovery pass, and any drift or discovery failure returns explicit bounded refresh guidance without mutating or reloading the service;
- focused Soma pytest validation passed with 77 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-sixth independently reviewable slice — consecutive discovery convergence:

- capability identity now performs two consecutive live operation-schema discovery passes and reports pass disagreement explicitly, rather than treating one transient snapshot as converged;
- the compact response includes pass count and convergence state, while schema mismatches retain affected operation names and bounded connector-refresh guidance;
- focused Soma pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-seventh independently reviewable slice — capability-payload identity metadata:

- authoritative `list_capabilities` responses now carry the same operation-inventory, public-schema, and discovery-cache identities as `capability_identity`, enabling connector refresh checks directly against the live capability payload;
- compact capability projections retain identity scalars and full capability views preserve the complete action/schema evidence, with no service mutation or reload;
- focused Soma pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-eighth independently reviewable slice — live input-schema aggregate identity:

- capability discovery and identity responses now include a deterministic aggregate hash of the live gateway input schemas, supplementing operation-inventory and per-operation fingerprints;
- the aggregate is checked across both consecutive discovery passes, so structural connector drift cannot hide behind an unchanged operation-name inventory;
- focused Soma pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-ninth independently reviewable slice — connector binding for live input schemas:

- `capability_identity` now accepts an explicit connector expectation for the aggregate live-input-schema hash and reports `connector_live_input_schema_hash` drift separately from legacy schema and operation-inventory mismatches;
- matching expectations remain read-only and bounded, while stale expectations retain affected mismatch names and refresh guidance;
- focused Soma pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventieth independently reviewable slice — versioned system compact envelopes:

- compact `system_query` projections, including the dedicated `self_check` path, now carry the standard projection version, compact view marker, non-authoritative notice, truncation state, and response-byte accounting;
- explicit `view="full"` system responses remain complete authoritative evidence and are unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-first independently reviewable slice — versioned compact repository status:

- `repo_query(operation="compact_status")` now carries the standard compact projection version, view marker, non-authoritative notice, truncation state, and response-byte accounting;
- existing tool-owned filtering, byte-budget trimming, direct compatibility behavior, and full status evidence remain unchanged;
- focused Soma pytest validation passed with 46 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-second independently reviewable slice — versioned compact repository file lists:

- `repo_query(operation="list_files")` now carries the standard compact projection version, view marker, non-authoritative notice, truncation state, and response-byte accounting;
- explicit full file-list retrieval and existing repository-relative path/security checks remain unchanged;
- focused Soma pytest validation passed with 46 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-third independently reviewable slice — versioned compact recent-file lists:

- `repo_query(operation="recent_files")` now carries the standard compact projection version, view marker, non-authoritative notice, truncation state, and response-byte accounting;
- explicit full recent-file evidence and live filesystem ordering remain unchanged;
- focused Soma pytest validation passed with 46 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-fourth independently reviewable slice — versioned compact commit logs:

- `repo_query(operation="log")` now carries the standard compact projection version, view marker, non-authoritative notice, truncation state, and response-byte accounting;
- explicit full and legacy git-log retrieval remain unchanged, including path scoping and bounded commit-list trimming;
- focused Soma pytest validation passed with 46 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-fifth independently reviewable slice — versioned compact cancellation acknowledgements:

- compact `cancel_run` responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing byte/count/truncation metadata;
- cancellation routing, status/error distinctions, process-tree counts, and explicit full cancellation evidence remain unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-sixth independently reviewable slice — versioned compact workflow projections:

- compact workflow status/result responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing step/truncation/byte metadata;
- workflow identifiers, child-run linkage, bounded step summaries/errors, and explicit full workflow evidence remain unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-seventh independently reviewable slice — versioned compact system-action responses:

- compact `system_action` responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing lifecycle/count/truncation/byte metadata;
- reload/rollback routing, lifecycle error detail, bounded module lists, and explicit full action evidence remain unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-eighth independently reviewable slice — versioned compact SSH-query responses:

- compact `ssh_query` responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing host/capability-count/truncation/byte metadata;
- SSH capability and profile-preview routing, hash/error fields, and explicit full query evidence remain unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-ninth independently reviewable slice — versioned compact supervisor snapshots:

- compact supervisor status/result snapshots now carry the standard projection version, compact view marker, non-authoritative notice, and existing run-link/presence/truncation/byte metadata;
- supervisor lifecycle identifiers, bounded summaries, child status, and explicit full snapshot evidence remain unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eightieth independently reviewable slice — versioned compact supervisor resume prompts:

- compact supervisor resume-prompt responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing UTF-8 content/truncation/byte metadata;
- protected prompt-path omission, supervisor identity, truncation behavior, and explicit full prompt retrieval remain unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-first independently reviewable slice — versioned compact parallel-group responses:

- compact `run_query(operation="group_status"/"group_result")` responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing child-count/truncation/byte metadata;
- group child lifecycle fields, protected artifact omission, bounded summaries/errors, and explicit full group evidence remain unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-second independently reviewable slice — versioned compact Trading Lab scalar responses:

- compact Trading Lab scalar query responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing provider-result/truncation/byte metadata;
- demo-only provider gating, scalar field filtering, disabled/disconnected behavior, and explicit full query responses remain unchanged;
- focused Soma pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-third independently reviewable slice — versioned compact Docker health responses:

- compact Docker health responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing engine/Compose truncation/byte metadata;
- Docker connectivity semantics, bounded diagnostic reduction, and explicit full health evidence remain unchanged;
- focused Soma pytest validation passed with 79 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-fourth independently reviewable slice — versioned compact Docker capability listings:

- compact Docker capability listings now carry the standard projection version, compact view marker, non-authoritative notice, and existing operation-array/truncation/byte metadata;
- capability risk gates, repository scoping, requested-name handling, and bounded operation contents remain unchanged;
- focused Soma pytest validation passed with 80 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-fifth independently reviewable slice — versioned compact Cloudflare health responses:

- compact Cloudflare health responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing authorized-profile/diagnostic truncation/byte metadata;
- profile authorization, token/engine diagnostics, repository identity, and bounded health semantics remain unchanged;
- focused Soma pytest validation passed with 81 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-sixth independently reviewable slice — versioned compact Cloudflare capability listings: the compact capability projection carries the standard envelope while profile authorization, bounded operation contents, and full evidence remain unchanged.

Eighty-seventh consolidated slice — CF1 identity, durability, evidence, and transport hardening (commits `2acf399`..`55c5bb1`):

- operation schema identities are qualified by `gateway.operation`; duplicate identities with different schemas are collisions, connector expectation capacity is no longer capped at an incomplete 128-entry set, and fresh-process identity convergence is tested;
- managed applies now persist successful results with `ended_at`/`duration_seconds` (a successful commit can no longer be reported failed) and no longer recursively scan the whole workspace per transaction; observed managed-apply time fell from ~342.9 s to ~0.665 s (~516×);
- explicit `view="full"` retrieval was restored for every compacted route the audit identified (Docker, Cloudflare, trading, workflow/supervisor events, SSH bounded inspection, knowledge search, collections/events), protected by a table-driven gateway-inventory test;
- one shared `cf1.v1` compact envelope (`view`, `projection_version`, `non_authoritative`, `notice`) is applied centrally, including strict knowledge output schemas; full responses stay undecorated and authoritative;
- repository reads, patch previews, and dedicated text validators report exact newline diagnostics (LF/CRLF/lone-CR counts, first 20 immutable style ranges, truncation flag, ending-newline state) with corrected lone-CR line totals;
- the MCP transport wraps dict results in a `ToolResult` so the complete payload appears once in structured content with a ≤512-byte human-readable text summary; direct Python callers still receive plain dictionaries.
- Define a small versioned response envelope carrying view, projection version, payload byte count, truncation state, continuation/evidence handles, source identity where relevant, and a clear non-authoritative-summary marker.
- Apply deterministic per-field and whole-response UTF-8 byte budgets before serialization completes.
- No ordinary unsolicited public result may exceed 64 KB.
- Compact responses must not echo full prompts, scripts, patches, argv, environment, stdin, credentials, request bodies, or complete provider payloads.
- MCP structured content and text fallback must not duplicate the same representation; acceptance measures both channels separately and together.
- Preserve operational distinctions, errors, safety failures, partial results, mutation ambiguity, and reconciliation requirements across every gateway.
- Keep explicit full/evidence paths for every gateway that can produce information larger than its compact projection.
- Reuse existing compact gateway shapes where they satisfy the new envelope, but do not grandfather oversized or JSON-decoding paths merely because they already exist.

### CF1.7 - Compatibility rollout and cross-project acceptance

Status: **complete; local acceptance, live connector rollout, schema-identity convergence, and cross-project compatibility acceptance closed on 2026-07-24**.

Completion decision:

- the live public operation inventory and effective input schemas converged across runtime discovery, connector-visible discovery, and compatibility checks;
- every public tool accepted its minimum valid schema through the live MCP boundary, legacy wrappers remained readable without being advertised, and mixed flat/wrapped requests failed explicitly;
- exact large-input recovery reconstructed 1,468,221 bytes through 90 cursor-bound chunks, while compact status measured 1,728 bytes versus 26,029 bytes for the legacy/full representation;
- the lightweight live self-check passed all nine checks, and the final comprehensive CF1 audit reported 1,776 passed and 34 skipped with clean dependencies, diff hygiene, package identity, and isolated MCP startup;
- authoritative evidence remains preserved while compact projections are the ordinary ChatGPT path.

The detailed rollout narrative below is retained as the historical implementation and acceptance record; its steps are complete rather than pending work.

`tests/test_chat_footprint_acceptance.py` (31 tests, all passing) now proves the CF1 acceptance gates against production code:

- all 19 authoritative CF1 fixtures are exercised exactly once, hash-bound, with every lifecycle/outcome distinction distinguishable in the compact result; terminal scenarios run through the real `RunStore`, terminal-state transitions, publication, and `JobManager.get_terminal_result()`; the active run stays on the pending path with control-route evidence;
- evidence recovery is 100% (49/49 declared evidence kinds) with canonical-JSON equality against the stored authoritative `result_json` and matching `source_result_sha256` bindings; the gateway full route is reassembled and hash-verified through its inline/chunked transport;
- production responses hold their serialized UTF-8 budgets: terminal 12 KB, summary 6 KB, control 8 KB, unchanged poll 1 KB, events 12 KB, repository search 16 KB, read batch 48 KB, diff 32 KB, everything within 64 KB;
- twenty realistic durable run summaries paginate losslessly under the 12 KB list budget (pages of 11,212 / 11,212 / 2,726 bytes; first page 9 of 20, byte-limited, stable cursor, no loss or duplication);
- the ~837 KB twenty-run payload (844,721 canonical bytes reconstructed from durable rows) never enters the conversation path: full enumeration costs 25,150 compact bytes (~3.0%) while every run's complete result remains exactly recoverable;
- conversation-visible bytes fell from 1,875,110 (representative pre-CF1 baseline: duplicated structured+text payloads in the connector envelope) to 29,060 through the real MCP transport — a 98.45% reduction with zero duplicate complete-payload copies (structured 25,424 B, bounded text 2,496 B, wrapper 1,140 B);
- performance: compact terminal projection p50 0.041 ms / p95 0.052 ms (2 ms gate); full retrieval medians 61.3 ms vs the 62.4 ms direct-retrieval baseline per 50-call batch (no regression against the 5% gate); compact SQL summary paths decode no JSON blobs; the MCP text summary is serialization-free and capped at 512 bytes;
- compatibility and safety: direct Python callers receive dictionaries, MCP callers receive structured content plus the bounded text summary, legacy rows materialize once and reuse, stale bindings rebuild, and compact responses exclude lease tokens, run directories, secret values, reviewed scripts, and protected stdout/stderr while evidence handles stay usable.

Full-suite validation ran three times through durable Soma pytest execution. The first run was invalidated by a concurrent documentation edit (the read-only guard correctly flagged the changed worktree) and exposed three real failures fixed in `14c6502` (the strict `knowledge_action` output schema rejected its own compact refresh acknowledgement) and `2bef4c1` (discovery exactness inventories missing the intentionally restored `view`/`response_budget_bytes` fields). The final run reports 1,505 passed, 5 skipped, and exactly one failure: the documented, unrelated `tests/test_hermes_service_process.py::test_one_verified_process_serves_multiple_bound_requests` full-suite-only PID instability, which passes alone and remains outside CF1 scope. A one-off pid-file read race in `test_powershell_acceptance.py` was observed once under full-suite load, passes alone, and is tracked separately.

Compatibility rollout (completed):

1. add compact operations and versioned views without changing existing explicit-full behavior;
2. preserve the current frozen full run cursor and exact chunk reconstruction contract;
3. update tool descriptions so ChatGPT selects compact operations by default and full/evidence operations deliberately;
4. add compatibility and deprecation metadata to verbose defaults where appropriate;
5. update supervisors, workflows, internal callers, and gateway adapters before changing any legacy alias;
6. restart or reload the service only through the accepted deployment procedure;
7. refresh the ChatGPT connector schema and verify the loaded capability epoch;
8. test compact and legacy behavior in a fresh conversation and with an older caller that still uses the legacy operations;
9. measure server bytes, MCP bytes, connector-visible bytes, request bytes, and total conversation transcript bytes;
10. only after acceptance decide whether legacy `list`, `status`, and `result` become compact aliases.

Live acceptance covers Soma, Andiya, and Wan2.2 with an ordinary implementation, failed validation, active long run, unchanged poll, cancellation, partial result, ambiguous mutation and reconciliation, parallel group, large repository file, search continuation, frozen diff hunks, workflow/supervisor result, SSH state, executable binary artifact, and Hermes-backed call.

Acceptance must prove exact full-evidence reconstruction, authoritative-result hash equality, no connector-visible duplication, no lost error or safety state, no worker-path regression, and at least 90-percent total session-footprint reduction.
### Performance and size gates

The repair is rejected if it saves transcript space by slowing or weakening execution.

```text
20-run summary list:                  <= 12 KB
single summary/status:                 <= 6 KB
compact terminal result:              <= 12 KB
unchanged polling response:            <= 1 KB
default events response:              <= 12 KB
default repository search:            <= 16 KB
default repository read batch:        <= 48 KB
ordinary diff inspection:             <= 32 KB
ordinary unsolicited response:        <= 64 KB
representative session reduction:     >= 90 percent
full evidence recoverability:         100 percent
full-result hash equality:            100 percent
```

Compact list p95 must not be slower than the current list and should be at least 25 percent faster. Compact status must not be slower than the current control query. Compact terminal reads may be no more than 5 percent slower than scalar state reads. Legacy full paths may regress by no more than 5 percent. Worker execution must show zero measurable regression. Median terminal-summary overhead must remain at or below 2 ms.

### Safety and correctness gates

The implementation must prove:

- authoritative `input_json` and `result_json` remain unchanged;
- protected artifact bytes and hashes remain unchanged;
- secret redaction remains active in summaries and evidence retrieval;
- reviewed scripts remain excluded or redacted from public views;
- exact process cancellation, startup reconciliation, and repository locks are unchanged;
- errors, safety failures, partial outcomes, and ambiguous mutations survive every projection;
- cursor and continuation snapshots cannot mix evidence versions;
- large Hermes responses remain fully retrievable;
- public summaries cannot be mistaken for authoritative records;
- old database rows remain readable;
- connector-visible output contains no duplicate representation.

### Focused test suites

```text
tests/test_run_public_projections.py
tests/test_run_store_summary_queries.py
tests/test_public_result_materialization.py
tests/test_artifact_query.py
tests/test_repo_response_budgets.py
tests/test_conditional_run_polling.py
tests/test_chat_footprint_acceptance.py
```

Tests assert that compact SQL never selects JSON columns, run lists do not call `json.loads`, terminal projections are deterministic and source-hash bound, errors and safety states survive projections, continuation reconstructs exact omitted content, explicit full chunking remains valid, legacy rows work, the 837-KB fixture fits within 12 KB, and latency/allocation gates hold.

### Commit sequence

```text
CF1.0  Add contract, gateway inventory, footprint fixtures, and benchmarks
CF1.1  Add scalar run-summary store queries and stable cursors
CF1.2  Add compact run-list, control, polling, and delta-event operations
CF1.3  Materialize bounded source-hash-bound terminal projections
CF1.4  Add manifest-secured artifact evidence retrieval
CF1.5  Add repository response budgets and content-bound continuation
CF1.6  Bring remaining public gateways under the compact contract
CF1.7  Complete connector rollout, cross-project acceptance, and documentation
```

Each commit must be independently reviewable and preserve existing explicit-full behavior.

### Out of scope

The first repair does not include a Chrome extension, ChatGPT DOM modification, automatic deletion of conversations, model-generated handovers, durable-run ownership changes, H2 concurrency redesign, Trading Lab execution changes, protected-evidence reduction, broad transport replacement, or model-generated summaries.

The governing design principle is:

> Preserve everything once; transmit only what is useful now.

CF1 is complete: every exit gate passed and later work proceeded only through explicit bounded user selections. No future roadmap lane is activated by this historical section.

## R5 - Absolute Resource Enforcement

Status: **complete**.

Implemented:

- deterministic cgroup-v2 absolute memory policy at conservative `40_000_000_000`, graceful `45_000_000_000`, and hard `48_000_000_000` bytes;
- policy and samples in authoritative R4 state and heartbeats;
- graceful and hard process-group enforcement with identity revalidation;
- persisted threshold, signal, identity, confirmation, and terminal evidence;
- a separate `16_384`-byte ceiling for internal encoded controllers;
- authoritative GPU temperature/memory, disk-capacity, controller-heartbeat, and bounded CUDA-OOM evidence while preserving absolute-memory-first enforcement;
- POSIX execution coverage for graceful exit, forced escalation, direct hard termination, identity refusal, and persisted evidence.

Acceptance evidence:

- `tests/test_remote_controller_state.py`: `8 passed`;
- `tests/test_ssh_watchdog.py`: `9 passed`;
- `tests/test_remote_resource_enforcement.py`: `7 passed`;
- `tests/test_ssh_watchdog_execution.py`: `4 skipped` on Windows as platform-gated;
- the actual generated controller completed all four process-group cases on the existing free Linux host: graceful, escalation, hard, and identity refusal;
- affected modules compiled and `git diff --check` passed.

R5 satisfies deterministic threshold paths, visible overrides, exact termination targeting, durable remaining-signal evidence, and real POSIX process-group validation without provisioning paid infrastructure.

## H1 - ChatGPT-Controlled Hermes Tool Runtime

Status: **complete**.

### H1A - Feasibility audit

- Identify and pin the candidate Hermes revision.
- Confirm registry, toolset, search, schema, dispatch, result, cancellation, and approval interfaces.
- Prove whether `tool_search`, `tool_describe`, and `tool_call` work without a Hermes model-agent loop.
- Inspect how built-ins, plugins, skills, and connected MCP tools enter the effective registry.
- Identify required runtime state, credentials, browser state, and long-running ownership.
- Prefer a versioned process boundary: upstream server mode or a small Hermes companion adapter.
- Avoid direct in-process Hermes imports unless no stable boundary exists and the coupling is explicitly accepted.

The audit produces a compact decision and implementation scope; it must not silently expand into implementation.

H1A decision (2026-07-18):

- Pin `NousResearch/hermes-agent` revision `862b1b37bf0aadba3a98b3756c7d71779379b53b` as the initial compatibility target.
- Use a small versioned Hermes companion process over stdio; do not import Hermes into the Soma service process and do not invoke a Hermes model-agent loop.
- The existing upstream `mcp_serve.py` is session/event/approval oriented and is not the required generic tool-runtime boundary.
- Hermes catalog search and schema description can execute as pure registry reads. Deferred `tool_call` can invoke the underlying tool without model inference while preserving the normal Hermes hook, guardrail, edit-approval, and approval path.
- Built-ins, plugins, and connected MCP tools converge in the effective registry. Skills remain instruction resources unless associated code registers an actual tool.
- Generic detached or long-running tools remain unsupported initially because the registry has no provider-neutral external ownership and cancellation contract.
- The accepted implementation scope and evidence are recorded in [`docs/hermes-tool-runtime-feasibility.md`](docs/hermes-tool-runtime-feasibility.md).

H1B protocol foundation completed on 2026-07-18:

- added a versioned companion handshake bound to Hermes revision `862b1b37bf0aadba3a98b3756c7d71779379b53b`;
- bound registry generation and deterministic effective-schema hash into handshake, search, and describe responses;
- added deterministic interface-drift failures for protocol, revision, registry-generation, and schema changes;
- added bounded `tool_search` summaries and exact `tool_describe` schema identity;
- added fail-closed evidence that no Hermes model-runtime module was initialized;
- focused validation: `tests/test_hermes_companion_protocol.py` reported `5 passed`, the protocol module compiled, and `git diff --check` passed.

Pinned companion executable adapter completed on 2026-07-18:

- added a JSON-lines stdio executable that verifies the exact Hermes Git revision before importing upstream code;
- imports only the pinned `tools.registry` discovery boundary and fails closed on registry interface drift;
- emits the accepted handshake and routes schema-bound read-only `tool_search` and `tool_describe` requests;
- bounds request and response sizes and emits deterministic error envelopes;
- rejects any observed Hermes model-runtime import before serving requests;
- focused validation: `tests/test_hermes_companion.py` reported `5 passed`, `tests/test_hermes_companion_protocol.py` reported `5 passed`, the adapter compiled, and `git diff --check` passed.

Durable companion client contract completed on 2026-07-19:

- added bounded one-request handshake/search/describe launch construction over the existing durable executable-profile lifecycle;
- persisted the pinned Hermes revision, checkout, operation, and expected registry/schema identity in the accepted client metadata;
- added exact one-response parsing with handshake and bound catalog-identity verification;
- focused validation: `tests/test_hermes_companion_client.py` reported `5 passed`, the client module compiled, and `git diff --check` passed.

Public gateway and terminal publication completed on 2026-07-19:

- added the `hermes_companion` public `run_start` operation for handshake, search, and describe;
- persisted pinned checkout, revision, operation, registry generation, and schema hash in the authoritative executable input;
- the worker now verifies the exact one-response protocol before terminal publication and includes the verified Hermes response beside protected stdout/stderr artifact metadata;
- malformed, failed, multiply emitted, operation-drifted, generation-drifted, or schema-drifted responses fail the durable run rather than publishing unverified catalog data;
- focused validation: `tests/test_hermes_companion_client.py` reported `5 passed`, `tests/test_tool_gateway_models.py` reported `32 passed`, and `tests/test_job_manager.py` reported `68 passed`.

Live public H1B gate completed on 2026-07-19:

- repaired the ignored live `config.yaml` profile boundary that had joined `unrestricted_child_processes: true` to `parallel_execution:`, causing every fresh durable worker to exit before lease claim;
- cancelled the abandoned queued validator, validated the repaired configuration, reloaded it without restarting the tunnel, and proved fresh PowerShell and allowlisted Git workers claim and complete normally;
- restored the ignored pinned checkout at Hermes revision `862b1b37bf0aadba3a98b3756c7d71779379b53b`;
- aligned the companion with the pinned registry interface by running explicit built-in discovery and reading the raw registered schemas without invoking availability checks or a Hermes model loop;
- `tests/test_hermes_companion.py` reported `6 passed`, the adapter compiled, and the compatibility fixes were committed as `620913c5b9a78e8741681d2d96f96c302486c82f` and `baa7354696ca841efd56070fb066d19aa36d8048`;
- the public MCP `run_start(operation="hermes_companion")` handshake completed as run `20260719T035330Z_executable_profile_9e38e2d0`, publishing registry generation `57`, effective schema hash `9489c958268618207783c6e4e31e2b93d37db06841c49657de4d194f78e71445`, pinned revision identity, and `model_runtime_initialized: false`;
- schema-bound public search completed as run `20260719T035421Z_executable_profile_d0111a56`, and exact describe completed as run `20260719T035424Z_executable_profile_c7ec0d5a`; both published verified `hermes_response` data, terminal result hashes, and protected stdout/stderr artifact hashes under the same catalog identity;
- the current Soma environment initially lacked the pinned Hermes core dependency `requests==2.33.0`, so five built-in modules (`browser_tool`, `delegate_tool`, `terminal_tool`, `vision_tools`, and `x_search_tool`) were unavailable and emitted bounded protected warnings;
- installed that exact upstream-pinned dependency into the live companion environment, then reran the pinned handshake as run `20260719T051116Z_executable_profile_7cf66ac2`;
- the aligned handshake completed with empty stderr, registry generation `72`, effective schema hash `3c409ad2b545f2251550f22e5924d6af6c0fd1775cd4840f8c21fca6b5eab870`, and `model_runtime_initialized: false`; protected stdout hash `1613bdd8197cbe5e4e7c7602e7316bfb6f0803436cad4fa577458032c9c1808e` and empty-stderr hash `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` were durably published.

Bound tool-call path completed on 2026-07-19:

- added a one-request `tool_call` companion operation bound to the accepted protocol version, pinned Hermes revision, registry generation, effective-schema hash, exact tool identity, exact tool-schema hash, and accepted argument object;
- replaced the lower-level registry dispatcher with pinned `model_tools.handle_function_call`, preserving request middleware, plugin pre-tool blocks, approval guards, execution middleware, and post-tool hooks against the real tool identity;
- exposed `tool_call` through the public durable Hermes gateway after the policy-path gate passed;
- proved a real bounded read-only `read_file` call against the pinned generation-72 catalog and schema hash `3c409ad2b545f2251550f22e5924d6af6c0fd1775cd4840f8c21fca6b5eab870` as run `20260719T072023Z_executable_profile_bccfab47`;
- the call read lines 1-5 of `PLANS.md`, published exact arguments and tool-schema hash `265fc44e1ec436b2716993e33375040ac26ebae8fc87c770851089db21b93633`, emitted empty stderr, and did not initialize a Hermes model-agent runtime;
- focused validation: `tests/test_hermes_companion.py` reported `6 passed` and `tests/test_tool_gateway_models.py` reported `32 passed`.

Plugin and MCP discovery alignment completed on 2026-07-19:

- companion startup now invokes the pinned Hermes `discover_plugins()` and `discover_mcp_tools()` entry points before freezing the effective registry snapshot;
- plugin and connected-MCP tools therefore enter the same schema-bound catalog and normal `model_tools.handle_function_call` execution path without tool-specific Soma wrappers;
- pinned interface drift for either discovery entry point fails closed, while ordinary plugin/server discovery failures are retained as bounded handshake initialization warnings;
- synthetic connected-MCP registration coverage proves a newly discovered MCP tool appears in the catalog, contributes its dynamic toolset, and executes through the generic bound executor;
- focused validation: `tests/test_hermes_companion.py` reported `7 passed`, and the companion module compiled.

Disposable connected-MCP execution evidence completed on 2026-07-19:

- added a repository-owned stdio MCP fixture and a reusable acceptance harness using an isolated `HERMES_HOME` under ignored `runs`, leaving the user's real Hermes configuration untouched;
- the actual pinned Hermes checkout discovered `mcp__soma_fixture__echo_fixture`, included it in registry generation `85`, and bound it to effective schema hash `8b43af99fe9ea6e41bfd82542f4f42764816bf36bf53156cd64c6fe6c59db160`;
- exact describe published tool-schema hash `87fb4050ba48900df327f896d8fcae53dfca0203e8eb6350352f016b380b2074`;
- the generic policy-preserving executor returned the fixture marker and value `durable-mcp-gate` with `model_runtime_initialized: false`;
- durable validation run `20260719T092053Z_executable_profile_616c1625` completed with empty stderr, both fixture scripts compiled, and `tests/test_hermes_companion.py` remained `7 passed`.

Repository-owned Hermes-home binding completed on 2026-07-19:

- added an optional `hermes_home` field to the public durable `hermes_companion` request;
- the client resolves and accepts only an existing non-symlink directory contained by the active repository, then injects only the exact `HERMES_HOME` environment key into the existing executable lifecycle;
- arbitrary companion environment injection remains unavailable;
- focused validation: `tests/test_hermes_companion_client.py` reported `6 passed` and `tests/test_tool_gateway_models.py` reported `32 passed`.

Public connected-MCP gateway acceptance completed on 2026-07-19:

- corrected the dedicated Hermes executable profile to use `environment_policy: arbitrary` with unrestricted environment delivery, while the public companion contract still injects only the validated repository-owned `HERMES_HOME` key;
- validated and reloaded the live configuration without restarting the service or tunnel;
- public handshake run `20260719T184837Z_executable_profile_e3d7d21e` published registry generation `85`, effective schema hash `8b43af99fe9ea6e41bfd82542f4f42764816bf36bf53156cd64c6fe6c59db160`, protected stdout SHA-256 `db40d703b817243b48e525ca413a58e0e7cced73f2b65085aba8298e6068d3e9`, and empty protected stderr;
- public search run `20260719T184845Z_executable_profile_00575f0e` discovered `mcp__soma_fixture__echo_fixture` under the same catalog identity;
- public describe run `20260719T184849Z_executable_profile_82d878a9` bound tool-schema hash `87fb4050ba48900df327f896d8fcae53dfca0203e8eb6350352f016b380b2074`;
- public call run `20260719T184854Z_executable_profile_f5fd4fb2` returned source `soma-disposable-mcp` and value `public-durable-mcp-gate`, with protected stdout SHA-256 `54c65db5b8c13717f273dcacb22901d7938ca5d3a5d3434d421e81ab62604dd9` and empty protected stderr;
- no Hermes model-agent loop or tool-specific Soma wrapper participated in the path.

Repository-owned reversible side-effect fixture contract completed on 2026-07-19:

- extended the disposable connected-MCP fixture with caller-supplied idempotency keys, atomic repository-owned outcome state, exact argument-drift rejection, authoritative reconciliation, and explicit reversal;
- an intentional post-commit ambiguous response leaves the mutation durably visible for reconciliation;
- replay with the same key and arguments returns the original outcome with `applied: false`, preserving `application_count: 1` rather than applying the mutation twice;
- focused validation: `tests/test_hermes_mcp_fixture.py` reported `3 passed`, and adjacent `tests/test_hermes_companion.py` reported `7 passed`.

Public reversible side-effect acceptance completed on 2026-07-19:

- fresh public handshake run `20260719T201034Z_executable_profile_6130c7ba` bound registry generation `88` and effective schema hash `d6c2814409cad1c28c075bd134d4ea1806617154f3b7206b10173ec8e5cdfc39`, with `model_runtime_initialized: false`, protected stdout SHA-256 `f898728d1a176770ba0939294754a4a2de2f59fc5873a076e5d8b91af468b125`, and empty protected stderr;
- public search run `20260719T201113Z_executable_profile_fd0f7afd` bound `mcp__soma_fixture__apply_reversible_fixture` to tool-schema hash `4eff7674906c70b559b9255711bd10dd560326232299bf1fd4b5f4a2e117b90c`;
- ambiguous apply run `20260719T201158Z_executable_profile_5291aff8` committed idempotency key `h1-public-side-effect-20260719-2012` and then returned the intentional post-commit error, with protected stdout SHA-256 `150ac9686f4cc112cc0d5e4c28893cc841fd95851f2c8fa5e61d250516cbc7dc` and empty stderr;
- reconciliation run `20260719T201203Z_executable_profile_a17bc66e` verified the authoritative outcome existed with value `public-durable-side-effect` and `application_count: 1`;
- replay run `20260719T201207Z_executable_profile_60006013` returned `applied: false` while preserving the same single application, proving the ambiguous result was not blindly duplicated;
- reversal run `20260719T201211Z_executable_profile_7c752b60` returned `reverted: true`, and final reconciliation run `20260719T201216Z_executable_profile_51e57bc3` verified `exists: false`;
- the acceptance exposed that the fixture MCP child did not inherit the companion-only `HERMES_HOME`; the fixture now fails closed without an explicit home and the generated MCP server configuration passes the repository-owned home directly;
- isolation regression validation: `tests/test_hermes_mcp_fixture.py` reported `4 passed`.

Lifecycle acceptance completed on 2026-07-19:

- added a bounded, side-effect-free `mcp__soma_fixture__wait_fixture` tool for deterministic lifecycle testing;
- fresh public handshake run `20260719T211753Z_executable_profile_56f93e9f` bound registry generation `89` and effective schema hash `a308c1820ae7e601a71cedc6ff27be866c5d40221070244b826ca657b7f2aa78`, with `model_runtime_initialized: false` and empty protected stderr;
- exact describe run `20260719T211801Z_executable_profile_7213674c` bound tool-schema hash `012082dc6fb140f730f2e93f1add7934e895517f0b4123ebab6096a9c8c74104`;
- cancellable call run `20260719T211806Z_executable_profile_94dcc96d` reached verified `running` ownership with result publication still `not_published`, then `cancel_run` confirmed process-tree termination for the child and worker and published one terminal `cancelled` result;
- the cancelled run returned empty public stdout/stderr and no `hermes_response`, proving an interrupted call cannot publish an unverified tool result;
- startup reconciliation regression coverage proves a persisted active Hermes worker with verified process identity is adopted with exact companion catalog metadata intact, its repository lock retained, and result publication left `not_published` until the worker finishes;
- focused validation: `tests/test_hermes_mcp_fixture.py` reported `5 passed`, and `tests/test_job_manager.py` reported `69 passed`.

H1 acceptance is complete. The next executable unit is OP1: begin the evidence-driven real-project pilot with a repository-owned pilot evidence log and record representative ordinary Soma/Hermes work without architectural expansion.

### H1B - Minimal external surface

The preferred ChatGPT-facing capability can search enabled tools, describe one exact schema, invoke it with validated arguments, inspect long-running status/results, and cancel through authoritative ownership.

The contract must preserve Hermes version, registry generation or schema hash, tool identity, selected toolset, accepted arguments, result classification, and artifact references. Exact public tool names are chosen during implementation.

### H1C - Execution and policy

- ChatGPT plans and chooses the tool; Hermes must not reinterpret the task through a second model.
- Soma remains authoritative for request identity, durability, cancellation, bounded output, protected evidence, and applicable locks.
- Search and description are read-only.
- Side effects include communications, bookings, purchases, refunds, credential changes, destructive actions, and real-money operations.
- Ambiguous transport failure must never cause blind replay of a mutation.
- Automatic mutation retry requires provider-appropriate idempotency or outcome reconciliation.
- Secrets use the narrowest safe existing channel and never appear in public events or summaries.
- Long-running tools use an accepted durable owner or are explicitly unsupported.

R6 secret-reference work is conditional supporting scope: implement only the minimum required if existing protected input and environment mechanisms cannot safely launch Hermes.

### H1D - Acceptance

- ChatGPT searches Hermes without loading every deferred schema into the connector.
- ChatGPT inspects and invokes one read-only built-in or plugin tool.
- ChatGPT invokes one Hermes-connected MCP tool without tool-specific Soma code.
- Evidence proves no Hermes model-agent invocation occurred.
- Exact tool/schema identity and arguments are durable.
- One approved reversible side effect executes once and its external outcome is verified.
- Ambiguous responses reconcile without duplicate mutation.
- Accepted asynchronous calls have deterministic restart and cancellation behavior.
- Credentials and protected results stay out of bounded public output.

No real-money purchase, booking, cancellation, or refund is used as an acceptance test.

## H2 - Shared Multi-Session Hermes Service

Status: **complete; reactivated by user selection on 2026-07-22 after CF1 local acceptance, implemented, live-accepted, and validated the same day**. Final durable full-suite validation: run `20260722T212128Z_project_command_262b02fe` reported **1537 passed, 5 skipped, 0 failed** in 284.60 s with exit code 0 and an unchanged repository-state guard — including the formerly full-suite-failing Hermes persistent-worker PID test, now passing under the durable venv interpreter.

The production motivation remains valid: the H1 one-request companion path pays the full Hermes and MCP startup cost on every call, and live handshake run `20260720T191848Z_executable_profile_4c2eff11` measured **23.501 seconds** under registry generation `85` and effective schema hash `8ccc02adee339326497a10953c749d73ae5eade6a92f41c21bb59cde573cd987`, with `model_runtime_initialized: false`, empty protected stderr, and no repository lock.

H2.1 established the generation-scoped service-runtime foundation. H2.2 added a process-identity-verified persistent stdio worker, exact request cancellation, bounded stderr evidence, and live warm-process reuse: focused run `20260720T204859Z_executable_profile_907209be` passed `21` tests plus compilation and `git diff --check`; live run `20260720T205034Z_executable_profile_5aa2fc68` launched pinned Hermes in **37.152 seconds** and served two bound `searchconsole` searches through verified PID `34824` in **0.004 seconds** and **0.003 seconds**, with no model runtime and empty protected stderr. The observed registry generation was `85` and schema hash was `467d7969a09e309505aa66560c61e0b27e38c51e659f35f04e00e5517ea459d4`.

On 2026-07-22 the remaining H2 scope — durable service supervision, deterministic worker replacement, restart adoption, public gateway routing, narrow concurrency controls, explicit H1 fallback, five-live-session acceptance, and a real Search Console API call through the shared path — was implemented and accepted; see the H2 completion record below.

The completed H1 path remains the safe compatibility baseline: each ChatGPT request launches one durable, schema-bound Hermes companion process. Commit `9bb17f0452fe9419138b6f99a606a885bbe3a664` removes the incorrect repository-wide serialization from new Hermes companion runs, so independent discovery and tool calls can execute concurrently without taking a Soma repository operation lock. This fixes the immediate multi-chat blocker but does not turn the one-request companion into the final shared service.

H2 will replace per-call companion startup as the primary path with one persistent Hermes service that is independent of any repository and supports concurrent, isolated sessions from multiple ChatGPT conversations. Repository identity is optional context supplied only to tools that genuinely need it; Trading Lab work, repository writes, and ordinary Search Console or other read-only calls must not block one another merely because they pass through the same Soma instance.

### H2A - Shared service and session contract

- Run one version-pinned, supervised Hermes service with explicit health, build, protocol, registry-generation, and effective-schema identity.
- Give every invocation a durable Soma run ID plus a distinct Hermes request/session ID; one chat must never consume, cancel, or publish another chat's result.
- Preserve current exact tool identity, tool-schema hash, accepted arguments, bounded output, protected evidence, cancellation, restart recovery, and no-model-runtime guarantees.
- Keep the current one-request companion as a bounded fallback and compatibility path until persistent-service acceptance is complete.
- Permit multiple read-only discovery, description, and tool-call requests to overlap without a repository lock or one global Hermes execution lock.

### H2B - Narrow concurrency controls

Serialize only the resource that can actually conflict:

- Hermes installation, removal, upgrade, configuration editing, and registry reload use one Hermes-administration lock.
- Shared credential changes use a credential-specific lock and never expose secret values in public state.
- Providers and individual tools may declare concurrency and rate limits without reducing unrelated tools to one global queue.
- Mutations targeting the same external resource require provider-appropriate idempotency, reconciliation, or a resource-scoped mutation lock.
- Read-only calls remain concurrent unless the provider itself requires a narrower limit.

### H2C - Acceptance

- Five independent ChatGPT sessions can concurrently search, describe, or invoke bounded read-only Hermes tools and receive isolated durable results.
- A long Trading Lab or repository run can overlap with a Search Console read without either acquiring or waiting on the other's repository lock.
- Cancelling one long Hermes call terminates only its owned execution and does not interrupt other sessions or the shared service.
- Registry reload is serialized, publishes one new generation atomically, and causes stale schema-bound requests to fail closed rather than execute against drifted tools.
- Two unrelated providers can run concurrently, while two mutations against the same external resource are serialized or safely reconciled.
- Service restart adoption, health recovery, output bounds, protected evidence, and fallback to the one-request companion are demonstrated under live acceptance.

### H2 completion record (2026-07-22)

**Root cause of the documented full-suite-only PID failure.** The failure was never a race or test pollution: the durable full suite runs under `.venv`, whose Windows `python.exe` is a launcher redirector, so the companion that serves requests is a child of the `Popen` PID. Manual isolated runs used the direct system interpreter and passed. The failure reproduced deterministically in isolation under the venv interpreter. The fix binds worker process-identity verification to the serving process: the companion self-reports its PID in the handshake `python_identity`, `PersistentHermesWorker` verifies the serving identity for ready/dispatch/cancel while keeping the launch root as the termination anchor, and cancel/close terminate both trees, closing an orphan leak when the redirector root exits first. Redirector-shape regression tests reproduce the venv topology on any interpreter. No assertion was weakened and no timing sleep was added.

**Architecture.** `HermesServiceRuntime` (H2.1/H2.2 generation and ownership core) is now owned by `HermesServiceSupervisor` (worker launch, deterministic replacement of dead unleased workers with exact registry-identity equality, supervised registry reload, persisted worker-identity records, restart adopt-or-replace), fronted by `HermesServiceGateway` (public `run_start` operation `hermes_service`; distinct durable Soma run ID plus Hermes request ID per invocation; result reads and cancellation enforced against the owning run/request/session triple; stale schema-bound requests fail closed with no fallback; exactly one explicit bounded fallback to the H1 one-request companion when the service is unavailable, labelled with mode and reason). `hermes_concurrency` provides the narrow H2B controls: a named Hermes-administration lock (install/upgrade/configuration/removal/registry-reload only), per-credential locks keyed and reported solely by SHA-256 digests, glob-scoped tool concurrency and min-interval rate limits leaving unmatched tools fully concurrent, and resource-scoped mutation locks serializing only same-resource mutations. Configuration is the opt-in `hermes_service` section (checkout, python_executable, worker_count, state_path, fallback profile, tool_limits).

**Acceptance evidence (live, pinned checkout `runs/hermes-pinned-validation` at the pinned revision, registry generation `85`, schema `467d7969…459d4`, `model_runtime_initialized: false`; JSON evidence under `.codex-tmp/h2c-acceptance/`).**

- Five live sessions concurrently issued bounded `tool_search` calls through the production gateway: five distinct durable run and request IDs, all completed, and every one of the twenty cross-session result reads was rejected with an ownership error. A focused regression additionally proves five-way true overlap with per-session ownership enforcement.
- A real bounded Search Console API call (`mcp__searchconsole__gsc_list_sites`) succeeded through the shared service in 0.823 s with 498 bounded output bytes and exact tool identity plus tool-schema hash, while an unrelated provider call (`read_file`) genuinely overlapped on a second worker.
- A live in-flight `gsc_search_analytics` request was cancelled by its owning triple: the request terminated as `cancelled`, the shared service survived, and health returned ready.
- A worker tree was killed mid-service: the next two calls completed on distinct run IDs (no duplicate publication), capacity was restored by deterministic replacement (replacement count 2), and health returned two ready workers.
- Restart adoption: a second service instance found four recorded still-live worker PIDs from a severed instance, terminated them deterministically (including redirector/serving PID pairs such as 49448/51896), and started fresh verified workers; zero survivors.
- A shared-service read completed in 0.013 s while the repository operation lock was held — no lock interference.
- Same-generation registry reload failed closed (`candidate registry generation must be newer`); the newer-generation atomic publish, drain, and stale fail-closed paths are regression-locked in focused tests; a live stale-generation request failed closed with `stale_identity`.
- Explicit H1 fallback under a simulated service outage executed exactly one one-request companion call (4.233 s) labelled `one_request_companion_fallback` with the outage reason.

**Performance.** Cold shared-service start: 14.203 s total for two workers (10.102 s + 4.100 s). Warm shared calls: 0.026-0.128 s, versus the documented 23.501 s H1 per-call cost — the per-call Hermes startup cost is removed on the shared path.

**Bounded output and protected evidence.** All shared results honoured `max_output_bytes` (observed 498-50001 encoded bytes ≤ 65536); worker stderr remains bounded (64 KiB ring) and surfaces only as a bounded tail inside deterministic error messages.

**Remaining risks.**

- Live conflicting-mutation serialization was proven at the mechanism level (gateway resource-lock tests); no real external mutation was exercised because H2C acceptance forbids side-effectful calls against production properties.
- The live Soma server process predates this build; the shared service activates in the connector after the next service restart with `hermes_service.enabled: true` configured.
- A gateway built before a configuration reload keeps its original service settings until restart.
- Supervisor capacity restoration after a failed request is synchronous and can add one worker-launch latency (~10 s) to the failing caller's response.

## OP1 - Evidence-Driven Real-Project Pilot

Status: **complete; observation review closed on 2026-07-20**.

The repository-owned evidence log is [`docs/pilot-evidence.md`](docs/pilot-evidence.md). Its first entry records ordinary durable validation, one pre-acceptance rejection because parallel PowerShell execution was disabled in the live capability configuration, and successful serial recovery with no lost or duplicated work. A second entry records a successful durable Hermes-backed connected-MCP call under registry generation `89`, with exact tool/schema identity, no model runtime, empty protected stderr, and no lost or duplicated work after correcting one caller-side PowerShell invocation mistake. A third entry records a second pre-acceptance parallel rejection under the same live build during a genuinely independent two-test workload. A fourth entry records a clean durable serial regression of the reversible-side-effect and lifecycle fixture with five passing tests, one worker claim, one terminal publication, and no repository mutation. A fifth entry proves the repeated parallel rejection was live configuration drift rather than a code defect: `parallel_execution.enabled` remained `false` despite the completed X2A contract. The ignored config was changed to `true`, validated, and hot-reloaded without restarting Soma or Cloudflare; public group `20260720T010132Z_powershell_group_3da40097` then completed two overlapping child runs successfully. A sixth entry exercises the repaired capability on a real two-test workload: the first group exposed the known shared Windows pytest-temp permission problem, while an immediate retry with isolated repository-owned basetemps completed both children concurrently with `5 passed` and `6 passed`. A seventh entry records a successful schema-bound Hermes `read_file` call against the live OP1 section of `PLANS.md` under registry generation `79`, with the exact tool schema, accepted arguments, no model runtime, empty protected stderr, and no repository mutation after correcting one caller-side request-construction mistake. An eighth entry exercises a Hermes-connected reversible action under registry generation `89`: an intentionally ambiguous post-commit response was authoritatively reconciled at exactly one application, replay returned `applied: false`, reversal succeeded, and final reconciliation proved absence. Several caller-harness and transport mistakes caused bounded failed attempts but no lost or duplicated work. A ninth entry reruns the complete seven-test Windows parallel lifecycle acceptance suite through the durable validation gateway, covering fan-out, restart adoption, exact cancellation, and pending-child refill with no lost or duplicated work. A tenth entry exercises the complete live service self-check, promotes the known stale `run_start` schema assertion from observation to a bounded repair, and restores the full gate to `1194 passed, 5 skipped` with healthy imports, configuration, dependencies, stores, and HTTP transport. An eleventh entry exercises bounded real-service capability and health paths: Cloudflare correctly reports no configured repository profiles, while Docker reports an installed Windows client and Compose runtime but an unavailable Docker Desktop Linux engine. Neither condition caused mutation, lost work, duplicate work, or a Soma defect, and no service was started solely for evidence. A twelfth entry repairs two real-workflow contract defects: `repo_query diff` no longer crashes if a Git capture stream is absent, and the advertised `stdin_text` field now UTF-8 encodes safely for byte-capable PowerShell profiles. Focused and adjacent suites passed, a server-only durable restart adopted its worker and published once, the Cloudflare PID remained unchanged, and both public paths were verified under the new build. Parallel execution is available and usable for representative validation. The formal review found no unresolved security, destructive-targeting, corruption, lost-work, duplicate-work, or continuation-blocking defect. Bounded contract defects discovered during real use were repaired and regression-locked; configuration and infrastructure availability observations remain operational evidence rather than architectural programs. OP1 is complete and no Roadmap V3 promotion threshold was crossed. No roadmap unit is auto-selected: the original TL0-TL9 sequence was later completed and superseded by the authoritative Trading Lab redesign.

After H1, freeze architectural expansion and exercise:

- ordinary local repository and service work that requires no newly rented infrastructure;
- parallel build or test work;
- repeated connector use across separate ChatGPT sessions;
- Hermes-backed reads and approved reversible external actions;
- optional remote or GPU-host work only when that infrastructure is already running for an actual user-requested workload, never provisioned solely for the pilot.

Create a separate pilot evidence log. Each entry records timestamp, project, expected outcome, HEAD/build identity, relevant run/tool identities, exact failure, lost or duplicated work, recovery, attribution, reproduction frequency, and artifacts.

Record normal friction before redesign. Repair immediately only for security violations, destructive targeting, lost or duplicated work, unrecoverable corruption, or a blocker preventing continuation.

## TL - Soma Trading Lab

Status: **redesigned on 2026-07-23; scheduled ChatGPT companion cycle implemented, wired through Soma, and live-accepted on 2026-07-24**. The runtime threshold-portfolio experiment is removed and superseded. Trading Lab remains an optional capability provider gated behind `trading.enabled` (off by default, demo-only by construction); it owns no core lifecycle. Live-money execution must not exist per the TL9 review, and the redesign keeps it structurally impossible: no execution mode, configuration field, gateway model, policy, or tool can express `live`.

The original TL0–TL9 roadmap (threshold portfolios T50–T99, cloned baselines, the 1 USD normalized allocation, 20 percent caps, the TL5 runtime supervisor, the TL7 demo mirror, and the TL8 orchestrator) completed its gates and was then replaced by this redesign. The detailed TL0–TL9 narratives and their acceptance evidence are preserved verbatim in [`docs/roadmap-v2-achievements.md`](docs/roadmap-v2-achievements.md); the TL0 broker-acceptance bundle remains [`docs/trading-lab-tl0-evidence.md`](docs/trading-lab-tl0-evidence.md) and the TL9 live-readiness review remains [`docs/trading-lab-tl9-live-readiness-review.md`](docs/trading-lab-tl9-live-readiness-review.md).

### Redesigned architecture (authoritative)

```text
Alpari MT5 demo terminal
  <-> official MetaTrader5 Python package (5.0.5735)
  <-> MT5Provider (read adapter; broker offset detected, never assumed)
  <-> immutable market-packet store        (packet_store.py)
  <-> packet-bound signal journal v2       (signal_journal_v2.py)
  <-> durable tick archive                 (tick_archive.py)
  <-> independent outcome resolver         (outcome_resolver.py)
  <-> deterministic offline replay+reports (replay_engine.py, lab_reports.py)
  <-> guarded action gateway + executors   (action_gateway.py, executors.py)
  <-> durable runtime with decoupled
      supervision                          (trading_runtime.py)
```

Core invariants:

- A model decision is stored exactly once in the immutable signal journal. Submission references a stored market packet and derives symbol, bid/ask, timestamps, packet hash, and parent H4 candle identity from retained evidence; the caller can never supply its own copy of a market fact. Invalid submissions persist as explicit rejected-signal records.
- Each directional signal resolves independently from retained/fetched historical ticks with honest prices (LONG enters ask and exits/tests on bid; SHORT enters bid and exits/tests on ask; spread is embedded exactly once). Resolution never observes anything earlier than the signal entry time and processes observations chronologically. Outcomes are `RESOLVED_TP`, `RESOLVED_SL`, `UNRESOLVED_DATA_GAP`, or `AMBIGUOUS_WITHOUT_TICKS`; ambiguity stays a factual unknown, upgradeable only by real recovered ticks, and conservative-loss treatment exists only in scenario report columns.
- Threshold and occupancy analysis happens **only** through deterministic offline replay with configurable threshold, occupancy policy, notional/risk model, and cost model, recording `SKIPPED_CONFIDENCE` and `BLOCKED_EXISTING_POSITION`. Small samples are `INSUFFICIENT_SAMPLE` and never ranked; stable neighbouring threshold regions are preferred over one maximum-profit point.
- Two separate reports: signal-quality/confidence calibration (with parent-H4 correlation groups and rejected-submission counts) and strategy replay (thresholds and occupancy effects). Both support explicit historical experiment selection, offset pagination with totals, and a resolution period basis that includes positions opened before a period but resolved within it.
- Broker-time boundary: the UTC offset is detected from several fresh ticks on connect/reconnect and rounded to the quarter hour; raw broker timestamp, detected offset, and normalized UTC ride on every relevant record; offset changes append events without reinterpreting history; H4 boundaries are computed in broker time before normalization; ticks are retained append-only and exported as hash-verified compressed daily archives with gap detection.
- Every component version is recorded on its records (`versions.py`): packet schema, signal schema, normalizer, resolver, replay engine, cost model, and policy identities.

### Capability and strategy separation

Capability roles gate whether a caller may act and in which mode: `research_collector` (reads and signal submission only), `internal_paper_agent` (simulated actions), `broker_demo_agent` (guarded Alpari demo actions). Strategy policies gate what a strategy may use: `hourly_fixed_bracket_v1` permits exactly one market entry with one original model-selected stop-loss/take-profit, immutable after entry — no modification, trailing, reversal, stacking, or partial exit; `agentic_demo_v1` opens the complete management surface (market/pending/stop-limit entries, cancel/replace, full/partial close, scale-in/out, SL/TP set/modify/remove, break-even, profit locking, reversal, hedging, multiple targets, time/condition/news exits, durable trailing stops, flatten symbol/account, emergency close-all). `live` is structurally disabled.

Every model action passes one pipeline: schema validation → execution-mode policy → strategy policy → fresh-price validation → symbol/volume normalization → risk checks → margin/profit calculation → `order_check` → idempotent submission → durable persistence (`REQUESTED`, `VALIDATED`, `REJECTED`, `SUBMITTING`, `SUBMITTED`, `BROKER_CONFIRMED`, `FAILED`, `RECONCILED`) → broker reconciliation. The model never calls `MetaTrader5.order_send()`; only gateway-owned executors touch broker APIs, and the demo executor re-verifies the demo environment on every call. Duplicate exposure for a symbol is refused unless the strategy allows stacking, and experiment/cohort transitions cannot bypass the rule. Actions record origin, mode, policy, experiment, signal, eligibility, old/new values, and reconciliation; modified/manual/agentic trades are excluded from the fixed-bracket research dataset.

Reversal is close → reconcile → revalidate fresh price → open opposite; partial failure leaves the account flat and is recorded honestly. Trailing supervisors and standing time/condition exits are derived from durable confirmed action records on every pass, so they survive restart without any in-memory registry.

### Safety

Demo-only execution; durable global pause/kill switch (emergency close-all stays available while paused); allowed-symbol control; stale-price, spread, exposure, volume, action-rate, and daily-loss limits; duplicate prevention; account login and all credentials redacted from public/model-readable output; append-only immutable evidence everywhere.

### Public surface

`trading_query` operations: `health`, `symbols`, `specification`, `tick`, `h4_candles`, `historical_ticks`, `market_packet_get/list`, `outcome_get/list`, `rejection_list`, `data_quality`, `calibration_report`, `replay_report`, `action_get/list`, `companion_get/list`, `runtime_status`, `demo_performance`, `reconciliation_report`. The removed runtime virtual-portfolio operations (`open_virtual_positions`, `portfolio_status`, `threshold_report`) return an explicit deprecation pointing at the replay surface. Write tools: packet-bound `trading_signal_submit`, `trading_signal_cancel_before_entry`, the guarded `trading_action_submit`, `trading_runtime_control` (start/stop/status, kill switch, manual supervision/analysis passes), and the strict `trading_companion_action` cycle (`start`, `decide`, model-owned `review`, `execute`). Companion execution derives symbol, direction, mode, policy, experiment, and bracket from the approved immutable signal; callers provide only cycle identity, idempotency identity, and volume. Journal reads paginate with explicit totals; nothing silently truncates at 1,000 records.

### Redesign acceptance status (honest)

Complete with runtime wiring and evidence — see [`docs/trading-lab-redesign-evidence.md`](docs/trading-lab-redesign-evidence.md) for the full bundle:

- deterministic regressions for every audit defect (packet binding, pre-entry exclusion, decoupled supervision, duplicate exposure, report semantics, runtime wiring) and the full suite green (1,567 tests) after legacy removal;
- live demo acceptance on 2026-07-23 (read-only + internal paper): detected broker offset `+10800 s`, live immutable packet with broker-time parent H4 identity, packet-bound accept/reject against live data, runtime analysis entry through the guarded gateway, all seven supervision steps green, 3,471 retained live ticks with range hash and zero gaps, honest unresolved outcome, and zero broker orders sent;
- companion acceptance on 2026-07-24: one forced no-order cycle ended `NO_TRADE` with no action, and one directional internal-paper cycle blocked execution before model review, bound approval to the immutable signal hash, then reconciled successfully with zero broker-demo orders. The standalone package and Soma boundary were regression-tested, and the currently loaded pinned package is Trading Lab 0.2.4 from commit `c1a4218fa938fed1d415f21ab3c7ca3640c4df7c`.

Not yet done, requiring explicit future steps:

- no live broker-demo **order** has been sent through the new `DemoExecutor`; the first guarded demo order through `trading_action_submit` should be a supervised, explicitly requested step;
- no genuinely fresh analysed signal sample exists yet, so the calibration and replay reports have no real research data;
- `news_exit` supervision has no news feed; it currently honours only explicit deadlines/price conditions;
- scheduled hourly operation (cron/loop invoking `trading_runtime_control`) is an operator decision and is not enabled by default.

### Build/reuse boundary

Reuse: the MT5 terminal, the official MetaTrader5 Python package, the Alpari price feed and demo execution, Soma durability/policy/artifact/reconciliation infrastructure, and Hermes external research tools. Build nothing broker-shaped from scratch; do not build a broker, general charting platform, discretionary strategy engine, or another Stream Alpha. The TL9 decision stands: no live-execution tool may be built without a new explicit roadmap decision, separate live configuration and identity, human approval boundaries, and a fresh-sample performance record through the redesigned reports.

## Roadmap V3 Promotion Rules

Promote an observation when it violates a durability/security invariant, can lose or duplicate work, blocks a representative workflow, repeatedly requires manual recovery, reveals a repeated architectural pattern, or carries sufficient expected impact.

Attribute connector 502s before repair. Treat external fixture loss as infrastructure unavailability unless Soma mishandles it. Write Roadmap V3 only after representative pilot evidence is reviewed.

## Deferred Work

- paid RunPod or other paid remote/GPU validation; evidence may be collected only opportunistically during actual user-requested workloads;
- broad environment and secret-reference expansion beyond H1 needs;
- a large provider-neutral synthetic acceptance matrix;
- project-memory and local-model expansion;
- supervisor, workflow, optional coding, and dashboard expansion.

ChatGPT is Soma's reasoning and implementation controller. Source changes use
`repo_preview`, `repo_apply`, and `repo_commit`; deterministic execution and
validation use durable PowerShell. Neither Soma nor its controller may launch a
coding-agent CLI or model-agent process, including indirectly through PowerShell.
Any handoff packet is an inert export artifact for human use outside Soma.
Removed legacy run records remain readable only for compatibility and do not
represent an executable capability.

Historical R6, R7, P2, gate, commit, and validation specifications remain in the V2 achievement record.

## Validation and Commit Policy

For code: run focused then proportional adjacent tests, `git diff --check`, milestone-level full checks where justified, and real process/host tests when OS behavior is the subject. Commit every completed batch locally and never push without explicit instruction.

For documentation only: inspect the exact diff, run `git diff --check`, confirm only intended documentation changed, commit locally, confirm a clean worktree, and do not run the full suite.

Before every write or validation, inspect active durable runs and repository locks. Preserve unrelated work and never reset, clean, restore, discard, stash, amend, rebase, or rewrite history.
