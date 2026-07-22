# CodexBridge Active Engineering Plan

## Purpose

CodexBridge is the durable control plane connecting this ChatGPT conversation to local machines, repositories, services, remote hosts, and external tool runtimes.

```text
ChatGPT conversation
  -> reasoning, user context, tool selection, and approvals
  -> CodexBridge MCP
      -> durable identity, policy, execution, cancellation, and evidence
      -> local and remote engineering substrates
      -> Hermes searchable tool runtime
          -> built-in tools, plugins, skills, and connected MCP tools
```

ChatGPT remains the reasoning agent. Hermes supplies tools; its Codex, Claude, or other model-agent loop is not part of this request path.

This file is an active decision document, not an engineering journal. The complete V2 implementation and validation history through commit `d1c43340af48c03ca31505ef64f4c6a60248f61c` is preserved in [`docs/roadmap-v2-achievements.md`](docs/roadmap-v2-achievements.md).

## Governing Decisions

### Durable before powerful

Every accepted asynchronous operation must persist launch intent, request identity, ownership and lease state, cancellation state, output locations, and terminal publication semantics before it is production-ready.

### ChatGPT remains the brain

- The live ChatGPT conversation owns reasoning, user context, planning, and tool selection.
- CodexBridge exposes governed capabilities to that conversation.
- Hermes is a tool runtime, not a delegated reasoning agent, for this integration.
- The design does not depend on exporting ChatGPT's private memory store. Relevant context stays in the conversation; only required tool arguments or explicit context are transmitted.

### Reuse Hermes rather than duplicate it

- Reuse Hermes registration, availability checks, toolsets, plugin discovery, MCP discovery, and searchable dispatch where feasible.
- Do not create one CodexBridge wrapper for every Hermes tool.
- New Hermes plugins or MCP tools should become discoverable without corresponding CodexBridge source changes.
- Pin and negotiate the supported Hermes interface so upstream changes fail explicitly.

### Existing execution decisions remain in force

- `permissive` is the only active execution profile.
- Unrestricted PowerShell remains the single arbitrary-command local gateway.
- Native remote Linux execution continues through the accepted R4 controller protocol.
- Remote PowerShell remains optional for hosts that already provide it.
- Existing human-only boundaries continue to apply to real-money, credential, destructive, and production-impacting actions.

### No paid infrastructure for validation

- Do not start, rent, or retain RunPod or any other paid remote/GPU host solely for CodexBridge testing, acceptance, or roadmap evidence.
- Prefer local Windows validation, deterministic mocks and replayed fixtures, existing free CI, or infrastructure already running for an actual user-requested workload.
- OS-, provider-, or hardware-specific execution evidence that cannot be obtained without new cost is non-blocking deferred evidence. Collect it opportunistically during real work rather than making it a roadmap gate.

### Evidence before Roadmap V3

After the Hermes integration reaches its bounded gate, architectural feature expansion pauses. CodexBridge will be exercised on real projects before another broad reliability roadmap is created.

## Current Baseline

Complete: D1-D5 durability; G0/G1 managed editing and executable closure; X1/X2 unrestricted local PowerShell; X2A parallel groups; C1 permissive-only cleanup; R3 managed transfer; R4 durable remote Linux ownership; and optional X4 remote PowerShell.

R5 absolute resource enforcement is complete. H1A has selected and pinned the Hermes companion-process architecture. H1B now includes the versioned companion, durable public gateway, policy-preserving built-in calls, plugin and MCP discovery, repository-owned Hermes-home binding, and successful public connected-MCP execution.

Parallel PowerShell cancellation acceptance is complete. Whole-group and individual-child cancellation terminate the attached Windows process tree, preserve or refill sibling slots as required, and publish durable terminal results. Acceptance waits for durable child attachment before asserting process-owned readiness markers, so normal worker import time cannot create a false cancellation failure.

Known observations, not yet separate repair programs:

- occasional HTTP 502 responses from the ChatGPT connector path;
- external acceptance fixtures that may disappear independently of CodexBridge;
- increased complexity in durable state and reconciliation contracts.

Collect operational evidence before prescribing broad fixes for these observations.

## Active Sequence

Only CF1 is active. Every other implementation lane is intentionally paused.

1. CF1.0: freeze the public-representation contract and collect end-to-end measurements.
2. CF1.1: add scalar SQL-backed run summary queries and stable pagination.
3. CF1.2: add compact control polling and delta-event semantics.
4. CF1.3: materialize bounded terminal public projections tied to authoritative result hashes.
5. CF1.4: add manifest-secured exact evidence retrieval.
6. CF1.5: add repository read, search, and diff progressive disclosure.
7. CF1.6: bring every remaining public gateway under the unsolicited-response contract.
8. CF1.7: complete connector-visible and cross-project rollout acceptance.
9. Review CF1 evidence and explicitly decide whether H2, TL5, or another lane resumes next.

Do not resume H2, TL5, SSH work, reliability/autonomy work, or any other roadmap batch until CF1 is complete and this document explicitly reactivates it.

## Priority 0 - CF1 Chat Footprint and Progressive Disclosure

Status: **active; highest priority**.

### Objective

Reduce the total CodexBridge tool footprint inserted into ChatGPT conversations by at least **90 percent** while preserving complete authoritative evidence, exact command inputs and outputs, cancellation and recovery semantics, repository locks, result hashes, debugging capability, model access to requested detail, and current execution throughput.

The repair applies globally to every CodexBridge-managed project and public gateway, including CodexBridge, Andiya, Wan2.2, Hermes, Trading Lab, supervisors, workflows, SSH, parallel groups, and future repositories.

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

Status: **complete. CF1.3 is next and has not started**.

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

- Add `public_result_json`, `public_result_schema_version`, `public_result_source_sha256`, and `public_result_status` or equivalent durable fields.
- Materialize one deterministic, schema-versioned, tool-aware public projection when the authoritative terminal result publishes.
- Bind the projection to the complete authoritative `result_json` SHA-256 and preserve `result_json` byte-for-byte.
- Include bounded normalized outcome fields capable of distinguishing success, partial completion, validation failure, policy denial, needs-input, cancellation requested, cancellation verified, cancellation uncertain, infrastructure failure, cleanup incomplete, ambiguous side effect, and reconciliation required.
- Enforce deterministic per-field UTF-8 byte limits for summaries, errors, risks, changed files, tests, diagnostics, and artifact references; truncation must expose original byte count and an exact evidence handle.
- A projector failure must never block authoritative terminal publication. Publish a tiny bounded fallback envelope containing terminal state, source-result hash, projection error classification, and evidence handles.
- Reuse a projection only when source hash and schema version match; rebuild old projections lazily and persist them only through a safe compare-and-set path.
- Keep current pending-result behavior compatible while ensuring completed runs never require decoding the complete result merely to serve the compact projection.

### CF1.4 - Manifest-secured exact evidence retrieval

Status: **implementation complete for manifest-bound output compatibility; acceptance blocked by one unrelated full-suite Hermes persistent-worker PID failure**.

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
- native Python compilation passed for all changed Python files. Ruff lint still reports only the pre-existing unused `server.py` import, while whole-file formatting remains intentionally unapplied because it would rewrite unrelated legacy formatting. Pytest evidence is retained from CodexBridge runs; `.codex-tmp/` remains preserved;
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
- focused CodexBridge pytest validation passed with 36 gateway-model tests, 27 server tests, and 6 gateway-inventory tests; the complete suite reported 1,379 passed and 5 skipped, with only the already-documented Hermes persistent-process PID assertion failing. Native compilation, `python -m pip check`, and `git diff --check` passed; Ruff reports the same pre-existing unused import in `server.py`.

Third independently reviewable slice — immediate managed-apply acknowledgement:

- `repo_apply` now records a durable `repo_apply` run and repository lock before returning a compact acknowledgement containing transaction/run identity, accepted state, preview or cleanup identity, bounded control polling, and explicit terminal evidence access;
- the durable worker reuses the existing hash-verified apply, rollback, commit, wiki-staleness, and manifest lifecycle behavior; duplicate requests are refused while the same transaction is active, and completed manifest replay remains idempotent without reapplying files;
- the acknowledgement is capped at 4 KB and the operation inventory records its durable-input and bounded-response contract. CodexBridge pytest validation passed with 28 server tests, 6 gateway-inventory tests, 72 job-manager tests, and 36 gateway-model tests; the complete suite reported 1,379 passed and 5 skipped, with only the already-documented Hermes persistent-process PID assertion failing. Native compilation, `python -m pip check`, and `git diff --check` passed; Ruff reports only pre-existing unused imports.

Fourth independently reviewable slice — compact managed-apply terminal projection:

- terminal `repo_apply` results now expose bounded operation/patch identity, changed-file projection, commit hash, idempotent replay state, rollback status when present, validation pass/fail counts, and collapsed preserved/remaining-work counts;
- raw stdout/stderr and full validation payloads remain evidence-only, while the existing public-result UTF-8 budget, redaction, source hash, and explicit evidence handle continue to apply;
- focused CodexBridge pytest validation passed with 20 public-result materialization tests. Native compilation, Ruff, and `git diff --check` passed; `python -m pip check` remains green from the preceding slice.

Fifth independently reviewable slice — repository-bound local executable defaults:

- local executable-profile runs that omit `working_directory` now bind their process current directory to the registered repository root when the profile uses `service_default`; arbitrary and fixed directory policies retain their existing validation rules;
- the durable input records the resolved absolute directory before launch, preventing an omitted directory from silently inheriting the service process directory while preserving explicit full evidence and existing profile security checks;
- focused CodexBridge pytest validation passed with 7 executable-profile tests. Native compilation and `git diff --check` passed; Ruff reports the same pre-existing unused import in `job_manager.py`.

Sixth independently reviewable slice — hash-bound automatic commit metadata:

- automatic managed-write commits now include a deterministic SHA-256 of the exact normalized changed-path batch alongside the durable run ID in the commit body;
- the structured commit report exposes a metadata hash, and the recorded Git commit is verified to contain the same run and changed-path binding, so replay cannot substitute a different batch identity silently;
- focused CodexBridge pytest validation passed with 36 Git-tool tests. Native compilation, Ruff, and `git diff --check` passed; the only Ruff finding remains the pre-existing unused import in `job_manager.py`.

Seventh independently reviewable slice — bounded dedicated-validator controls:

- Python compile, Bash syntax, and JSON validation gateway schemas now accept an explicit bounded `timeout_seconds` control, persist it in the durable request, and enforce the same 1–604,800-second envelope before launch;
- validator terminal results include a compact structured validation summary with pass/fail state, error count, representative redacted diagnostic text, and truncation state, while full streams remain available only through explicit evidence retrieval;
- focused CodexBridge pytest validation passed with 36 gateway-model tests, 21 public-result tests, and 28 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the three pre-existing unused imports in `job_manager.py`, `job_worker.py`, and `server.py`.

Eighth independently reviewable slice — bounded ordinary result reads:

- `run_query(operation="result")` now routes to the bounded source-hash-bound terminal projection by default, preventing legacy diagnosis payloads from returning oversized authoritative JSON through the ordinary gateway;
- `view="full"` remains an explicit authoritative retrieval path, and callers that supply the existing chunk cursor are promoted to that full path for compatibility and exact reconstruction;
- focused CodexBridge pytest validation passed with 5 public-result gateway tests. Native compilation and `git diff --check` passed; Ruff reports the pre-existing unused import in `server.py`.

Ninth independently reviewable slice — bounded knowledge search freshness envelope:

- repository knowledge search now applies a deterministic 12-KB UTF-8 response budget after capability metadata is attached, preserving generation/head/branch freshness identities while collapsing excess wiki and memory hits;
- the response reports `response_bytes` and `truncated`, and existing repository-scoped search semantics, stale-generation metadata, and explicit wiki-page retrieval remain unchanged;
- focused CodexBridge pytest validation passed with 7 knowledge-integration tests. Native compilation, Ruff, and `git diff --check` passed; pip check remains green from the preceding slice.

Tenth independently reviewable slice — caller-bound preview commit metadata:

- patch previews now accept bounded caller-supplied commit title and description fields, validate them with the existing commit-message policy, and persist them in the protected manifest together with an opaque `Preview-ID` binding;
- preview apply returns only the manifest-bound metadata, and managed commit finalization preserves that title while appending the durable run ID and deterministic changed-path SHA-256, preventing replay or a later request from substituting commit identity;
- focused CodexBridge pytest validation passed with 92 repository-writer tests, 37 Git-tool tests, 36 gateway-model tests, and the legacy server compatibility regression. The full-suite run before that compatibility adjustment reported 1,386 passed and 5 skipped with two failures; the focused rerun removed the preview-wrapper failure, leaving only the already-documented Hermes persistent-process PID assertion. Native compilation, `git diff --check`, and `python -m pip check` passed; Ruff reports only the pre-existing unused imports.

Eleventh independently reviewable slice — bounded mixed-newline diagnostics:

- patch previews now report exact old/new LF, CRLF, and bare-CR counts, whether each version is mixed, and the first 20 affected line locations with total-count and truncation fields;
- diagnostic projection is capped at 8 KB before returning or persisting preview metadata, while the existing byte-preserving default and explicit legacy normalization behavior remain unchanged;
- focused CodexBridge pytest validation passed with 94 repository-writer tests. Native compilation, Ruff, and `git diff --check` passed; pip check remains green.

Twelfth independently reviewable slice — explicit normalization-risk warning:

- mixed-newline patch previews now warn before an explicitly requested normalized edit would rewrite the file’s newline forms, while the default preserved mode remains byte-preserving and apply still requires the existing expected content hash;
- the warning is copied into the protected preview manifest and remains non-fatal, so callers can deliberately request legacy normalization without confusing it with an accidental default behavior;
- focused CodexBridge pytest validation passed with 95 repository-writer tests. Native compilation, Ruff, pip check, and `git diff --check` passed.

Thirteenth independently reviewable slice — bounded lock reads:

- `run_query(operation="locks")` now defaults to a compact lock projection with bounded item count, a caller-selected 1–64-KB response budget, explicit `has_more`/truncation metadata, and response byte accounting;
- `view="full"` preserves the existing complete lock evidence path, while the operation inventory and gateway schema expose the compact/full distinction explicitly;
- focused CodexBridge pytest validation passed with 29 server tests and 36 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fourteenth independently reviewable slice — bounded repository file lists:

- `repo_query(operation="list_files")` now defaults to a compact repository-relative path projection with a caller-selected 1–64-KB serialized UTF-8 budget, explicit `count`/`total_count`, `has_more`, truncation, and response byte accounting;
- the direct `list_repo_files` compatibility wrapper remains full by default, while `view="full"` preserves complete path evidence and the operation inventory records the compact/full distinction;
- focused CodexBridge pytest validation passed with 30 server tests, 37 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifteenth independently reviewable slice — bounded recent-file lists:

- `repo_query(operation="recent_files")` now defaults to a compact recent-file projection with a caller-selected 1–64-KB serialized UTF-8 budget, explicit `count`/`total_count`, `has_more`, truncation, and response byte accounting;
- the direct `get_recently_modified_files` compatibility wrapper remains full by default, while `view="full"` preserves complete recent-file evidence and the operation inventory records the compact/full distinction;
- focused CodexBridge pytest validation passed with 31 server tests, 38 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixteenth independently reviewable slice — bounded commit-log lists:

- `repo_query(operation="log")` now defaults to a compact commit projection with a caller-selected 1–64-KB serialized UTF-8 budget, explicit `count`/`total_count`, `has_more`, truncation, and response byte accounting;
- the direct `git_log` compatibility wrapper remains full by default, while `view="full"` preserves complete commit-log evidence and the operation inventory records the compact/full distinction;
- focused CodexBridge pytest validation passed with 32 server tests, 39 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventeenth independently reviewable slice — bounded repository status:

- `repo_query(operation="status")` now defaults to a compact live-status projection with a caller-selected 1–64-KB serialized UTF-8 budget, preserved changed-file totals, `has_more`, truncation, and response byte accounting;
- the direct `inspect_repo_status` compatibility wrapper remains full by default, while `view="full"` preserves complete status evidence and the operation inventory distinguishes it from the existing compact-status operation;
- focused CodexBridge pytest validation passed with 33 server tests, 40 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighteenth independently reviewable slice — bounded managed-patch status:

- `repo_query(operation="patch_status")` now defaults to a compact managed-patch lifecycle projection with a caller-selected 1–64-KB serialized UTF-8 budget, changed-file/error counts, `apply_ok`, `has_more`, truncation, and response byte accounting;
- the direct `get_patch_status` compatibility wrapper remains full by default, while `view="full"` preserves complete patch manifest evidence and compact mode omits full apply/error payloads;
- focused CodexBridge pytest validation passed with 34 server tests, 41 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Nineteenth independently reviewable slice — bounded compact repository status:

- `repo_query(operation="compact_status")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget while preserving its compatibility-shaped status fields, and reports `truncated`, `has_more`, `response_budget_bytes`, and `response_bytes` when the projection is reduced;
- the compact status operation inventory now records the bounded-object response contract and 12-KB default/maximum budget; existing direct status behavior and tool-owned-field filtering remain unchanged;
- focused CodexBridge pytest validation passed with 35 server tests, 42 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twentieth independently reviewable slice — bounded Docker inspection:

- `docker_query(operation="inspect")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims redacted stdout/stderr and diagnostic fields deterministically while preserving the existing inspection result shape, explicit truncation state, and command safety checks;
- the Docker inspection inventory now records a bounded-object response contract with a 12-KB default/maximum budget; capabilities, health, and direct inspection compatibility remain available;
- focused CodexBridge pytest validation passed with 36 server tests, 43 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-first independently reviewable slice — bounded Cloudflare inspection:

- `cloudflare_query(operation="inspect")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and deterministically trims paginated provider results or diagnostic metadata while preserving profile authorization, page/per-page compatibility, and explicit truncation state;
- the Cloudflare inspection inventory now records a bounded-object response contract with a 12-KB default/maximum budget and retains page-number pagination metadata;
- focused CodexBridge pytest validation passed with 37 server tests, 44 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-second independently reviewable slice — bounded H4 candle retrieval:

- `trading_query(operation="h4_candles")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims completed candles deterministically while preserving the configured demo-terminal checks, completed-count limit, and developing-candle shape;
- the H4 candle inventory now records a bounded-object response contract with a 12-KB default/maximum budget and limit-only pagination semantics;
- focused CodexBridge pytest validation passed with 37 server tests, 45 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-third independently reviewable slice — bounded historical-tick retrieval:

- `trading_query(operation="historical_ticks")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims the returned tick list deterministically while preserving timezone-aware range validation and the configured demo-terminal checks;
- the historical-tick inventory now records a bounded-object response contract with a 12-KB default/maximum budget and explicit truncation metadata;
- focused CodexBridge pytest validation passed with 37 server tests, 46 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-fourth independently reviewable slice — bounded supervisor events:

- `supervisor_query(operation="events")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the ordered event list, preserving supervisor identity, event ordering, and the existing item limit;
- events and notifications are now represented separately in the gateway inventory, with the event operation carrying a bounded-object 12-KB default/maximum budget while notification compatibility remains unchanged;
- focused CodexBridge pytest validation passed with 38 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-fifth independently reviewable slice — bounded supervisor notifications:

- `supervisor_query(operation="notifications")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the notification list, preserving delivery-status filtering, ordering, supervisor identity, and the existing item limit;
- the notification inventory now records the bounded-object 12-KB default/maximum response contract alongside the previously bounded event operation;
- focused CodexBridge pytest validation passed with 39 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-sixth independently reviewable slice — bounded workflow events:

- `workflow_query(operation="events")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the ordered event list, preserving workflow identity, event ordering, and the existing 100–500 item limit;
- the workflow event inventory now records a bounded-object response contract with a 12-KB default/maximum budget and explicit truncation metadata;
- focused CodexBridge pytest validation passed with 40 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-seventh independently reviewable slice — bounded SSH inspection:

- `ssh_inspect(operation="inspection")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims redacted stdout/stderr and diagnostics deterministically while preserving host/path/target validation, bounded tail input, and existing structured health/telemetry variants;
- the SSH inventory now separates inspection from structured health/telemetry and records a bounded-object 12-KB default/maximum response contract for inspection;
- focused CodexBridge pytest validation passed with 41 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-eighth independently reviewable slice — bounded Trading Lab signal list:

- `trading_signal_list` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the immutable journal projection, preserving its limit and record fields;
- the signal-list inventory now records a bounded-object response contract with a 12-KB default/maximum budget and explicit truncation metadata;
- focused CodexBridge pytest validation passed with 42 server tests, 47 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Twenty-ninth independently reviewable slice — search contract convergence:

- the authoritative CF1 gateway inventory now matches the implemented `repo_query(operation="search_text")` contract: fixed 16-KB UTF-8 budgeting, cursor pagination, exact-file scope, snapshot/hash-bound continuation, and explicit timeout/partial-result reporting;
- focused CodexBridge pytest validation passed with 6 gateway-inventory tests and 47 gateway-model tests. Native compilation, pip check, `git diff --check`, and focused Ruff checks passed; no runtime search behavior changed in this documentation/contract-convergence slice.

Thirtieth independently reviewable slice — bounded Docker capability discovery:

- `docker_query(operation="capabilities")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims capability lists deterministically while preserving policy gates, configured profiles, and the direct health path;
- the Docker inventory now separates capabilities from health and records a bounded-object 12-KB default/maximum response contract for capability discovery;
- focused CodexBridge pytest validation passed with 43 server tests, 48 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-first independently reviewable slice — bounded Cloudflare capability discovery:

- `cloudflare_query(operation="capabilities")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims capability lists deterministically while preserving authorized profile/action metadata and the direct health path;
- the Cloudflare inventory now separates capabilities from health and records a bounded-object 12-KB default/maximum response contract for capability discovery;
- focused CodexBridge pytest validation passed with 44 server tests, 49 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-second independently reviewable slice — bounded Docker health:

- `docker_query(operation="health")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims verbose engine/Compose diagnostics deterministically while preserving provider health fields and the existing capability/inspection paths;
- the Docker health inventory now records a bounded-object 12-KB default/maximum response contract;
- focused CodexBridge pytest validation passed with 45 server tests, 50 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-third independently reviewable slice — bounded Cloudflare health:

- `cloudflare_query(operation="health")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims verbose profile diagnostics deterministically while preserving profile authorization, health fields, and the capability/inspection paths;
- the Cloudflare health inventory now records a bounded-object 12-KB default/maximum response contract;
- focused CodexBridge pytest validation passed with 46 server tests, 51 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-fourth independently reviewable slice — bounded symbol discovery:

- `trading_query(operation="symbols")` now accepts a caller-selected 1–64-KB serialized UTF-8 budget and trims only the tail of the symbol list, preserving configured demo-terminal checks and scalar trading-query behavior;
- the trading inventory now separates symbol discovery from scalar health/specification/tick operations and records a bounded-object 12-KB default/maximum response contract;
- focused CodexBridge pytest validation passed with 46 server tests, 52 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-fifth independently reviewable slice — bounded parallel-group reads:

- `run_query(operation="group_status"|"group_result")` now defaults to a compact 12-KB UTF-8 projection that omits request and artifact payloads, bounds child summaries, and reports truncation and response-byte metadata;
- `view="full"` remains an explicit complete group/evidence path, while group query schemas and the gateway inventory now record the compact/full distinction and bounded response contract;
- focused CodexBridge pytest validation passed with 53 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-sixth independently reviewable slice — bounded supervisor resume prompts:

- `supervisor_query(operation="resume_prompt")` now defaults to a compact 12-KB UTF-8 content projection with explicit truncation, `has_more`, original content-byte count, and serialized response-byte accounting;
- compact prompt responses omit local filesystem paths, while `view="full"` retains the existing explicit prompt/evidence path and supervisor compatibility behavior;
- focused CodexBridge pytest validation passed with 54 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-seventh independently reviewable slice — bounded workflow snapshots:

- `workflow_query(operation="status"|"result")` now defaults to compact 12-KB UTF-8 projections with bounded step diagnostics, explicit truncation, and response-byte accounting;
- compact workflow responses omit objective, process, and artifact payloads, while `view="full"` remains explicit complete snapshot/evidence access;
- focused CodexBridge pytest validation passed with 55 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-eighth independently reviewable slice — bounded system self-check:

- `system_query(operation="self_check")` now defaults to a compact 12-KB projection retaining per-check outcome, status, error, warning, exit-code, and duration fields with explicit truncation and response-byte accounting;
- compact self-check responses omit verbose command streams, while `view="full"` preserves explicit complete diagnostics and existing direct self-check behavior;
- focused CodexBridge pytest validation passed with 56 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Thirty-ninth independently reviewable slice — bounded single-signal retrieval:

- `trading_signal_get` now defaults to a compact 12-KB UTF-8 projection that bounds narrative and candle-context fields and reports truncation and serialized response bytes;
- `view="full"` preserves explicit complete immutable signal-record retrieval and existing journal/idempotency behavior;
- focused CodexBridge pytest validation passed with 57 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fortieth independently reviewable slice — bounded signal cancellation results:

- `trading_signal_cancel_before_entry` now returns the same compact 12-KB UTF-8 signal projection as single-signal reads, with bounded narrative fields and response-byte accounting;
- cancellation state transitions and immutable journal payloads remain unchanged, while `view="full"` preserves explicit complete record access;
- focused CodexBridge pytest validation passed with 58 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-first independently reviewable slice — bounded signal submission results:

- `trading_signal_submit` now defaults to the compact 12-KB UTF-8 signal projection, bounding narrative fields and reporting truncation and response-byte metadata;
- immutable journal insertion, idempotency replay, and validation remain unchanged, while `view="full"` preserves explicit complete record access;
- focused CodexBridge pytest validation passed with 59 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-second independently reviewable slice — bounded wiki-page retrieval:

- `knowledge_query(operation="read_wiki")` now defaults to a compact 12-KB serialized UTF-8 page projection with truncation, `has_more`, and response-byte metadata while preserving generation, freshness, and page identity fields;
- `view="full"` remains explicit complete-page access, and repository wiki validation/error behavior is unchanged;
- focused CodexBridge pytest validation passed with 8 knowledge-integration tests, 59 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, `git diff --check`, and scoped Ruff all passed.

Forty-third independently reviewable slice — bounded knowledge search contract:

- `knowledge_query(operation="search")` now exposes a caller-selected 1–64-KB serialized UTF-8 response budget with `truncated`, `has_more`, and response-byte metadata over the existing wiki/memory freshness envelope;
- item limits, repository scoping, global-memory opt-in, and search ranking remain unchanged;
- focused CodexBridge pytest validation passed with 8 knowledge-integration tests, 59 gateway-model tests, and 6 gateway-inventory tests. Native compilation, pip check, `git diff --check`, and scoped Ruff all passed.

Forty-fourth independently reviewable slice — bounded repo-commit results:

- `repo_commit` now defaults to a compact 12-KB UTF-8 mutation projection retaining operation/status, commit identity, and changed-file metadata with truncation and response-byte accounting;
- selected-file and branch-creation policy checks remain unchanged, while `view="full"` preserves explicit complete mutation metadata access;
- focused CodexBridge pytest validation passed with 60 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-fifth independently reviewable slice — bounded supervisor snapshots:

- `supervisor_query(operation="status"|"result")` now defaults to compact 12-KB UTF-8 projections retaining lifecycle, publication, diagnostic, and link-count metadata while omitting nested plan/implementation payloads;
- `view="full"` remains explicit complete snapshot/evidence access, and supervisor lifecycle behavior is unchanged;
- focused CodexBridge pytest validation passed with 61 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-sixth independently reviewable slice — bounded system action acknowledgements:

- `system_action(action="reload"|"rollback")` now defaults to a compact 12-KB acknowledgement retaining lifecycle status, operation counts, rollback outcome, and bounded diagnostics;
- `view="full"` preserves explicit complete lifecycle evidence access and the existing direct reload/rollback tools remain unchanged;
- focused CodexBridge pytest validation passed with 62 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Forty-seventh independently reviewable slice — bounded knowledge action acknowledgements:

- `knowledge_action(action="refresh_wiki"|"remember_decision")` now defaults to a compact 12-KB acknowledgement retaining lifecycle identity, freshness metadata, and page/file or memory counts while bounding diagnostics and summaries;
- `view="full"` preserves explicit complete mutation evidence access, and the existing direct wiki-refresh and decision-write functions remain unchanged;
- focused CodexBridge pytest validation passed with 9 knowledge-integration tests, 62 gateway-model tests, and 6 gateway-inventory tests. Native compilation, Ruff, pip check, and `git diff --check` passed.

Forty-eighth independently reviewable slice — bounded repository batch reads:

- `repo_query(operation="read_files")` now publishes explicit aggregate `has_more`, `truncated_batch`, `payload_bytes`, and `response_bytes` metadata while enforcing the serialized response budget at the final boundary;
- the existing 20-file limit, streamed per-file content, redaction, hash-bound continuation, and compatibility behavior remain intact;
- focused CodexBridge pytest validation passed with 72 repository-reader tests and 6 gateway-inventory tests. Native compilation, Ruff, pip check, and `git diff --check` passed.

Forty-ninth independently reviewable slice — bounded SSH query projections:

- `ssh_query(operation="capabilities"|"profile_preview"|"profile_status")` now defaults to compact 12-KB projections retaining host/lifecycle/hash identity and collapsing large capability diffs to counts;
- `view="full"` preserves explicit complete capability and profile evidence access, while existing internal SSH query functions and security validation remain unchanged;
- focused CodexBridge pytest validation passed with 63 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fiftieth independently reviewable slice — bounded workflow cancellation:

- `workflow_action(action="cancel")` now defaults to the compact 12-KB workflow projection, retaining lifecycle identity and bounded step diagnostics while preserving cancellation semantics;
- `view="full"` remains explicit complete workflow evidence access, and workflow starts plus direct cancellation behavior remain compatible;
- focused CodexBridge pytest validation passed with 64 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-first independently reviewable slice — bounded direct run cancellation:

- `cancel_run` now defaults to a compact 12-KB acknowledgement retaining run/group identity, status, and diagnostic counts while bounding process-tree details;
- explicit `view="full"` preserves complete cancellation evidence, and legacy one-argument callers plus cancellation routing remain compatible;
- focused CodexBridge pytest validation passed with 65 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-second independently reviewable slice — bounded supervisor lifecycle mutations:

- `supervisor_action(action="resume"|"pause"|"cancel")` now defaults to compact 12-KB lifecycle projections retaining supervisor identity/status/publication metadata and bounded diagnostics;
- `view="full"` remains explicit complete supervisor evidence access, and durable lifecycle transitions remain unchanged;
- focused CodexBridge pytest validation passed with 66 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-third independently reviewable slice — bounded scalar trading queries:

- `trading_query(operation="health"|"specification"|"tick")` now defaults to compact 12-KB scalar projections retaining provider-safe scalar fields while bounding oversized adapter payloads;
- `view="full"` remains explicit complete adapter evidence access, and existing symbols/candle/historical bounds plus provider lifecycle behavior remain unchanged;
- focused CodexBridge pytest validation passed with 67 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-fourth independently reviewable slice — bounded system summaries:

- `system_query(operation="capabilities"|"local_model_health"|"validate_config"|"reload_status")` now defaults to compact projections retaining scalar health/configuration fields and collection counts under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete system evidence access, while `self_check` and the underlying individual system functions retain their existing behavior;
- focused CodexBridge pytest validation passed with 68 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-fifth independently reviewable slice — bounded SSH health and telemetry:

- `ssh_inspect(operation="host_health"|"environment_probe"|"gpu_telemetry")` now defaults to compact projections retaining scalar host/health fields and collection counts under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete SSH evidence access, while bounded inspection, underlying SSH probes, and existing host security checks remain unchanged;
- focused CodexBridge pytest validation passed with 69 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-sixth independently reviewable slice — bounded SSH profile apply:

- `ssh_action(action="profile_apply")` now defaults to a compact mutation projection retaining change/status/activation scalars and counts under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete profile-apply evidence access, while hash verification, repository locking, activation, and existing SSH action behavior remain unchanged;
- focused CodexBridge pytest validation passed with 70 gateway-model tests and 6 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-seventh independently reviewable slice — bounded repository previews:

- `repo_preview` now defaults to compact preview metadata retaining patch/cleanup identity, changed-line and byte statistics, diagnostic counts, and diff byte size under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete diff and validation evidence access, while opaque preview persistence, path/hash validation, and apply compatibility remain unchanged;
- focused CodexBridge pytest validation passed with 71 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-eighth independently reviewable slice — bounded commit-range inspection:

- `repo_query(operation="commit_range")` now defaults to a compact projection retaining both commit identities, changed-file count, diff statistics, and diff byte size under a caller-selected 1–64-KB UTF-8 budget;
- `view="full"` remains explicit complete commit-range evidence access, while full-hash validation, canonical repository binding, and legacy direct inspection remain unchanged;
- focused CodexBridge pytest validation passed with 72 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Fifty-ninth independently reviewable slice — explicit supervisor notification evidence:

- `supervisor_query(operation="notifications")` keeps its compact item- and UTF-8-bounded default while accepting `view="full"` for complete delivery-status-filtered notification evidence;
- notification ordering, limit enforcement, supervisor identity, and existing internal bounded reads remain unchanged;
- focused CodexBridge pytest validation passed with 73 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixtieth independently reviewable slice — capability identity convergence:

- `system_query(operation="capability_identity")` now reports source-derived and running-service build/schema/epoch identities and compares caller-supplied connector/discovery identities, returning explicit mismatch names under the compact envelope;
- convergence checks are read-only and do not reload or mutate services; existing capability discovery and system-query operations remain available, with `view="full"` preserving the complete identity record;
- focused CodexBridge pytest validation passed with 74 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-first independently reviewable slice — operation-inventory drift check:

- capability identity now includes a deterministic operation-inventory hash and gateway count, and compares a caller-supplied connector/discovery inventory hash to report explicit operation-schema drift;
- inventory hashing normalizes operation sets deterministically, remains read-only, and preserves all existing capability identity and compact/full behavior;
- focused CodexBridge pytest validation passed with 74 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-second independently reviewable slice — synchronous live capability discovery:

- `system_query(operation="capabilities")` now resolves the async live MCP tool listing through a safe synchronous bridge, while preserving compatibility with synchronous test/legacy providers and compact/full projections;
- discovery failures remain explicit structured errors, and no service reload or mutation is performed;
- focused CodexBridge pytest validation passed with 75 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-third independently reviewable slice — explicit public-schema and discovery-cache identities:

- `system_query(operation="capability_identity")` now exposes distinct public-schema and discovery-cache generation identities alongside the legacy source/running capability fields;
- callers can bind connector-loaded public schema, operation inventory, and discovery-cache expectations, with bounded explicit mismatch names and preserved legacy schema checks;
- focused CodexBridge pytest validation passed with 76 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-fourth independently reviewable slice — managed-write knowledge freshness:

- compact terminal projections for `repo_apply` now retain bounded knowledge freshness state, source and indexed generations, stale reason, and an explicit `knowledge_action(refresh_wiki)` recommendation without embedding wiki content;
- authoritative apply results and full evidence remain unchanged, while callers can detect stale knowledge directly from the ordinary managed-write projection;
- focused CodexBridge pytest validation passed with 21 public-result tests and 46 adjacent server tests. Native compilation, pip check, `git diff --check`, and scoped Ruff passed.

Sixty-fifth independently reviewable slice — per-operation schema drift reporting:

- `system_query(operation="capability_identity")` now discovers live MCP input schemas, fingerprints each operation, and reports bounded missing, extra, and connector-schema mismatches by operation name;
- lazy knowledge-tool registration is included in the live discovery pass, and any drift or discovery failure returns explicit bounded refresh guidance without mutating or reloading the service;
- focused CodexBridge pytest validation passed with 77 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-sixth independently reviewable slice — consecutive discovery convergence:

- capability identity now performs two consecutive live operation-schema discovery passes and reports pass disagreement explicitly, rather than treating one transient snapshot as converged;
- the compact response includes pass count and convergence state, while schema mismatches retain affected operation names and bounded connector-refresh guidance;
- focused CodexBridge pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-seventh independently reviewable slice — capability-payload identity metadata:

- authoritative `list_capabilities` responses now carry the same operation-inventory, public-schema, and discovery-cache identities as `capability_identity`, enabling connector refresh checks directly against the live capability payload;
- compact capability projections retain identity scalars and full capability views preserve the complete action/schema evidence, with no service mutation or reload;
- focused CodexBridge pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-eighth independently reviewable slice — live input-schema aggregate identity:

- capability discovery and identity responses now include a deterministic aggregate hash of the live gateway input schemas, supplementing operation-inventory and per-operation fingerprints;
- the aggregate is checked across both consecutive discovery passes, so structural connector drift cannot hide behind an unchanged operation-name inventory;
- focused CodexBridge pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Sixty-ninth independently reviewable slice — connector binding for live input schemas:

- `capability_identity` now accepts an explicit connector expectation for the aggregate live-input-schema hash and reports `connector_live_input_schema_hash` drift separately from legacy schema and operation-inventory mismatches;
- matching expectations remain read-only and bounded, while stale expectations retain affected mismatch names and refresh guidance;
- focused CodexBridge pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventieth independently reviewable slice — versioned system compact envelopes:

- compact `system_query` projections, including the dedicated `self_check` path, now carry the standard projection version, compact view marker, non-authoritative notice, truncation state, and response-byte accounting;
- explicit `view="full"` system responses remain complete authoritative evidence and are unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests and 7 gateway-inventory tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-first independently reviewable slice — versioned compact repository status:

- `repo_query(operation="compact_status")` now carries the standard compact projection version, view marker, non-authoritative notice, truncation state, and response-byte accounting;
- existing tool-owned filtering, byte-budget trimming, direct compatibility behavior, and full status evidence remain unchanged;
- focused CodexBridge pytest validation passed with 46 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-second independently reviewable slice — versioned compact repository file lists:

- `repo_query(operation="list_files")` now carries the standard compact projection version, view marker, non-authoritative notice, truncation state, and response-byte accounting;
- explicit full file-list retrieval and existing repository-relative path/security checks remain unchanged;
- focused CodexBridge pytest validation passed with 46 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-third independently reviewable slice — versioned compact recent-file lists:

- `repo_query(operation="recent_files")` now carries the standard compact projection version, view marker, non-authoritative notice, truncation state, and response-byte accounting;
- explicit full recent-file evidence and live filesystem ordering remain unchanged;
- focused CodexBridge pytest validation passed with 46 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-fourth independently reviewable slice — versioned compact commit logs:

- `repo_query(operation="log")` now carries the standard compact projection version, view marker, non-authoritative notice, truncation state, and response-byte accounting;
- explicit full and legacy git-log retrieval remain unchanged, including path scoping and bounded commit-list trimming;
- focused CodexBridge pytest validation passed with 46 server tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-fifth independently reviewable slice — versioned compact cancellation acknowledgements:

- compact `cancel_run` responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing byte/count/truncation metadata;
- cancellation routing, status/error distinctions, process-tree counts, and explicit full cancellation evidence remain unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-sixth independently reviewable slice — versioned compact workflow projections:

- compact workflow status/result responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing step/truncation/byte metadata;
- workflow identifiers, child-run linkage, bounded step summaries/errors, and explicit full workflow evidence remain unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-seventh independently reviewable slice — versioned compact system-action responses:

- compact `system_action` responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing lifecycle/count/truncation/byte metadata;
- reload/rollback routing, lifecycle error detail, bounded module lists, and explicit full action evidence remain unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-eighth independently reviewable slice — versioned compact SSH-query responses:

- compact `ssh_query` responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing host/capability-count/truncation/byte metadata;
- SSH capability and profile-preview routing, hash/error fields, and explicit full query evidence remain unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Seventy-ninth independently reviewable slice — versioned compact supervisor snapshots:

- compact supervisor status/result snapshots now carry the standard projection version, compact view marker, non-authoritative notice, and existing run-link/presence/truncation/byte metadata;
- supervisor lifecycle identifiers, bounded summaries, child status, and explicit full snapshot evidence remain unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eightieth independently reviewable slice — versioned compact supervisor resume prompts:

- compact supervisor resume-prompt responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing UTF-8 content/truncation/byte metadata;
- protected prompt-path omission, supervisor identity, truncation behavior, and explicit full prompt retrieval remain unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-first independently reviewable slice — versioned compact parallel-group responses:

- compact `run_query(operation="group_status"/"group_result")` responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing child-count/truncation/byte metadata;
- group child lifecycle fields, protected artifact omission, bounded summaries/errors, and explicit full group evidence remain unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-second independently reviewable slice — versioned compact Trading Lab scalar responses:

- compact Trading Lab scalar query responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing provider-result/truncation/byte metadata;
- demo-only provider gating, scalar field filtering, disabled/disconnected behavior, and explicit full query responses remain unchanged;
- focused CodexBridge pytest validation passed with 78 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-third independently reviewable slice — versioned compact Docker health responses:

- compact Docker health responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing engine/Compose truncation/byte metadata;
- Docker connectivity semantics, bounded diagnostic reduction, and explicit full health evidence remain unchanged;
- focused CodexBridge pytest validation passed with 79 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-fourth independently reviewable slice — versioned compact Docker capability listings:

- compact Docker capability listings now carry the standard projection version, compact view marker, non-authoritative notice, and existing operation-array/truncation/byte metadata;
- capability risk gates, repository scoping, requested-name handling, and bounded operation contents remain unchanged;
- focused CodexBridge pytest validation passed with 80 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

Eighty-fifth independently reviewable slice — versioned compact Cloudflare health responses:

- compact Cloudflare health responses now carry the standard projection version, compact view marker, non-authoritative notice, and existing authorized-profile/diagnostic truncation/byte metadata;
- profile authorization, token/engine diagnostics, repository identity, and bounded health semantics remain unchanged;
- focused CodexBridge pytest validation passed with 81 gateway-model tests. Native compilation, pip check, and `git diff --check` passed; Ruff reports only the pre-existing unused server import.

- Inventory and adapt workflows, supervisors, SSH, remote controllers, Hermes, parallel groups, Docker, Cloudflare, knowledge, Trading Lab, system health, and every other public gateway.
- Define a small versioned response envelope carrying view, projection version, payload byte count, truncation state, continuation/evidence handles, source identity where relevant, and a clear non-authoritative-summary marker.
- Apply deterministic per-field and whole-response UTF-8 byte budgets before serialization completes.
- No ordinary unsolicited public result may exceed 64 KB.
- Compact responses must not echo full prompts, scripts, patches, argv, environment, stdin, credentials, request bodies, or complete provider payloads.
- MCP structured content and text fallback must not duplicate the same representation; acceptance measures both channels separately and together.
- Preserve operational distinctions, errors, safety failures, partial results, mutation ambiguity, and reconciliation requirements across every gateway.
- Keep explicit full/evidence paths for every gateway that can produce information larger than its compact projection.
- Reuse existing compact gateway shapes where they satisfy the new envelope, but do not grandfather oversized or JSON-decoding paths merely because they already exist.

### CF1.7 - Compatibility rollout and cross-project acceptance

Compatibility rollout:

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

Live acceptance covers CodexBridge, Andiya, and Wan2.2 with an ordinary implementation, failed validation, active long run, unchanged poll, cancellation, partial result, ambiguous mutation and reconciliation, parallel group, large repository file, search continuation, frozen diff hunks, workflow/supervisor result, SSH state, executable binary artifact, and Hermes-backed call.

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

CF1 completes only after every exit gate passes and the user explicitly accepts the roadmap review. Until then all later roadmap lanes remain paused.

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
- Use a small versioned Hermes companion process over stdio; do not import Hermes into the CodexBridge service process and do not invoke a Hermes model-agent loop.
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
- the current CodexBridge environment initially lacked the pinned Hermes core dependency `requests==2.33.0`, so five built-in modules (`browser_tool`, `delegate_tool`, `terminal_tool`, `vision_tools`, and `x_search_tool`) were unavailable and emitted bounded protected warnings;
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
- plugin and connected-MCP tools therefore enter the same schema-bound catalog and normal `model_tools.handle_function_call` execution path without tool-specific CodexBridge wrappers;
- pinned interface drift for either discovery entry point fails closed, while ordinary plugin/server discovery failures are retained as bounded handshake initialization warnings;
- synthetic connected-MCP registration coverage proves a newly discovered MCP tool appears in the catalog, contributes its dynamic toolset, and executes through the generic bound executor;
- focused validation: `tests/test_hermes_companion.py` reported `7 passed`, and the companion module compiled.

Disposable connected-MCP execution evidence completed on 2026-07-19:

- added a repository-owned stdio MCP fixture and a reusable acceptance harness using an isolated `HERMES_HOME` under ignored `runs`, leaving the user's real Hermes configuration untouched;
- the actual pinned Hermes checkout discovered `mcp__codexbridge_fixture__echo_fixture`, included it in registry generation `85`, and bound it to effective schema hash `8b43af99fe9ea6e41bfd82542f4f42764816bf36bf53156cd64c6fe6c59db160`;
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
- public search run `20260719T184845Z_executable_profile_00575f0e` discovered `mcp__codexbridge_fixture__echo_fixture` under the same catalog identity;
- public describe run `20260719T184849Z_executable_profile_82d878a9` bound tool-schema hash `87fb4050ba48900df327f896d8fcae53dfca0203e8eb6350352f016b380b2074`;
- public call run `20260719T184854Z_executable_profile_f5fd4fb2` returned source `codexbridge-disposable-mcp` and value `public-durable-mcp-gate`, with protected stdout SHA-256 `54c65db5b8c13717f273dcacb22901d7938ca5d3a5d3434d421e81ab62604dd9` and empty protected stderr;
- no Hermes model-agent loop or tool-specific CodexBridge wrapper participated in the path.

Repository-owned reversible side-effect fixture contract completed on 2026-07-19:

- extended the disposable connected-MCP fixture with caller-supplied idempotency keys, atomic repository-owned outcome state, exact argument-drift rejection, authoritative reconciliation, and explicit reversal;
- an intentional post-commit ambiguous response leaves the mutation durably visible for reconciliation;
- replay with the same key and arguments returns the original outcome with `applied: false`, preserving `application_count: 1` rather than applying the mutation twice;
- focused validation: `tests/test_hermes_mcp_fixture.py` reported `3 passed`, and adjacent `tests/test_hermes_companion.py` reported `7 passed`.

Public reversible side-effect acceptance completed on 2026-07-19:

- fresh public handshake run `20260719T201034Z_executable_profile_6130c7ba` bound registry generation `88` and effective schema hash `d6c2814409cad1c28c075bd134d4ea1806617154f3b7206b10173ec8e5cdfc39`, with `model_runtime_initialized: false`, protected stdout SHA-256 `f898728d1a176770ba0939294754a4a2de2f59fc5873a076e5d8b91af468b125`, and empty protected stderr;
- public search run `20260719T201113Z_executable_profile_fd0f7afd` bound `mcp__codexbridge_fixture__apply_reversible_fixture` to tool-schema hash `4eff7674906c70b559b9255711bd10dd560326232299bf1fd4b5f4a2e117b90c`;
- ambiguous apply run `20260719T201158Z_executable_profile_5291aff8` committed idempotency key `h1-public-side-effect-20260719-2012` and then returned the intentional post-commit error, with protected stdout SHA-256 `150ac9686f4cc112cc0d5e4c28893cc841fd95851f2c8fa5e61d250516cbc7dc` and empty stderr;
- reconciliation run `20260719T201203Z_executable_profile_a17bc66e` verified the authoritative outcome existed with value `public-durable-side-effect` and `application_count: 1`;
- replay run `20260719T201207Z_executable_profile_60006013` returned `applied: false` while preserving the same single application, proving the ambiguous result was not blindly duplicated;
- reversal run `20260719T201211Z_executable_profile_7c752b60` returned `reverted: true`, and final reconciliation run `20260719T201216Z_executable_profile_51e57bc3` verified `exists: false`;
- the acceptance exposed that the fixture MCP child did not inherit the companion-only `HERMES_HOME`; the fixture now fails closed without an explicit home and the generated MCP server configuration passes the repository-owned home directly;
- isolation regression validation: `tests/test_hermes_mcp_fixture.py` reported `4 passed`.

Lifecycle acceptance completed on 2026-07-19:

- added a bounded, side-effect-free `mcp__codexbridge_fixture__wait_fixture` tool for deterministic lifecycle testing;
- fresh public handshake run `20260719T211753Z_executable_profile_56f93e9f` bound registry generation `89` and effective schema hash `a308c1820ae7e601a71cedc6ff27be866c5d40221070244b826ca657b7f2aa78`, with `model_runtime_initialized: false` and empty protected stderr;
- exact describe run `20260719T211801Z_executable_profile_7213674c` bound tool-schema hash `012082dc6fb140f730f2e93f1add7934e895517f0b4123ebab6096a9c8c74104`;
- cancellable call run `20260719T211806Z_executable_profile_94dcc96d` reached verified `running` ownership with result publication still `not_published`, then `cancel_run` confirmed process-tree termination for the child and worker and published one terminal `cancelled` result;
- the cancelled run returned empty public stdout/stderr and no `hermes_response`, proving an interrupted call cannot publish an unverified tool result;
- startup reconciliation regression coverage proves a persisted active Hermes worker with verified process identity is adopted with exact companion catalog metadata intact, its repository lock retained, and result publication left `not_published` until the worker finishes;
- focused validation: `tests/test_hermes_mcp_fixture.py` reported `5 passed`, and `tests/test_job_manager.py` reported `69 passed`.

H1 acceptance is complete. The next executable unit is OP1: begin the evidence-driven real-project pilot with a repository-owned pilot evidence log and record representative ordinary CodexBridge/Hermes work without architectural expansion.

### H1B - Minimal external surface

The preferred ChatGPT-facing capability can search enabled tools, describe one exact schema, invoke it with validated arguments, inspect long-running status/results, and cancel through authoritative ownership.

The contract must preserve Hermes version, registry generation or schema hash, tool identity, selected toolset, accepted arguments, result classification, and artifact references. Exact public tool names are chosen during implementation.

### H1C - Execution and policy

- ChatGPT plans and chooses the tool; Hermes must not reinterpret the task through a second model.
- CodexBridge remains authoritative for request identity, durability, cancellation, bounded output, protected evidence, and applicable locks.
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
- ChatGPT invokes one Hermes-connected MCP tool without tool-specific CodexBridge code.
- Evidence proves no Hermes model-agent invocation occurred.
- Exact tool/schema identity and arguments are durable.
- One approved reversible side effect executes once and its external outcome is verified.
- Ambiguous responses reconcile without duplicate mutation.
- Accepted asynchronous calls have deterministic restart and cancellation behavior.
- Credentials and protected results stay out of bounded public output.

No real-money purchase, booking, cancellation, or refund is used as an acceptance test.

## H2 - Shared Multi-Session Hermes Service

Status: **paused after H2.2; CF1 is the sole active roadmap lane**.

The production motivation remains valid: the H1 one-request companion path pays the full Hermes and MCP startup cost on every call, and live handshake run `20260720T191848Z_executable_profile_4c2eff11` measured **23.501 seconds** under registry generation `85` and effective schema hash `8ccc02adee339326497a10953c749d73ae5eade6a92f41c21bb59cde573cd987`, with `model_runtime_initialized: false`, empty protected stderr, and no repository lock.

H2.1 established the generation-scoped service-runtime foundation. H2.2 added a process-identity-verified persistent stdio worker, exact request cancellation, bounded stderr evidence, and live warm-process reuse: focused run `20260720T204859Z_executable_profile_907209be` passed `21` tests plus compilation and `git diff --check`; live run `20260720T205034Z_executable_profile_5aa2fc68` launched pinned Hermes in **37.152 seconds** and served two bound `searchconsole` searches through verified PID `34824` in **0.004 seconds** and **0.003 seconds**, with no model runtime and empty protected stderr. The observed registry generation was `85` and schema hash was `467d7969a09e309505aa66560c61e0b27e38c51e659f35f04e00e5517ea459d4`.

This work is preserved as an isolated building block only. H2 remains incomplete: durable service supervision, worker replacement, restart adoption, public gateway routing, explicit H1 fallback, five-live-session acceptance, and a real Search Console API call through the shared path are still required. No further lifecycle, shared-service, gateway, adoption, or live H2 work may proceed until CF1 is complete and H2 is explicitly reactivated.

The completed H1 path remains the safe compatibility baseline: each ChatGPT request launches one durable, schema-bound Hermes companion process. Commit `9bb17f0452fe9419138b6f99a606a885bbe3a664` removes the incorrect repository-wide serialization from new Hermes companion runs, so independent discovery and tool calls can execute concurrently without taking a CodexBridge repository operation lock. This fixes the immediate multi-chat blocker but does not turn the one-request companion into the final shared service.

H2 will replace per-call companion startup as the primary path with one persistent Hermes service that is independent of any repository and supports concurrent, isolated sessions from multiple ChatGPT conversations. Repository identity is optional context supplied only to tools that genuinely need it; Trading Lab work, repository writes, and ordinary Search Console or other read-only calls must not block one another merely because they pass through the same CodexBridge instance.

### H2A - Shared service and session contract

- Run one version-pinned, supervised Hermes service with explicit health, build, protocol, registry-generation, and effective-schema identity.
- Give every invocation a durable CodexBridge run ID plus a distinct Hermes request/session ID; one chat must never consume, cancel, or publish another chat's result.
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

The 2026-07-20 concurrent H2/Trading decision is superseded by the CF1 priority decision. H2 and Trading Lab are both paused implementation lanes. Their completed work and acceptance criteria remain preserved, but neither may resume until CF1 passes and the user explicitly selects the next lane. Future H2 batches must still refresh HEAD, active and queued durable runs, and repository locks before every write or validation and must regenerate previews against the latest HEAD. No H2 completion claim is allowed until persistent process reuse, five-session isolation, cancellation isolation, atomic registry reload, deterministic restart/adoption, explicit H1 fallback, and read-only Search Console acceptance are demonstrated with live evidence.

## OP1 - Evidence-Driven Real-Project Pilot

Status: **complete; observation review closed on 2026-07-20**.

The repository-owned evidence log is [`docs/pilot-evidence.md`](docs/pilot-evidence.md). Its first entry records ordinary durable validation, one pre-acceptance rejection because parallel PowerShell execution was disabled in the live capability configuration, and successful serial recovery with no lost or duplicated work. A second entry records a successful durable Hermes-backed connected-MCP call under registry generation `89`, with exact tool/schema identity, no model runtime, empty protected stderr, and no lost or duplicated work after correcting one caller-side PowerShell invocation mistake. A third entry records a second pre-acceptance parallel rejection under the same live build during a genuinely independent two-test workload. A fourth entry records a clean durable serial regression of the reversible-side-effect and lifecycle fixture with five passing tests, one worker claim, one terminal publication, and no repository mutation. A fifth entry proves the repeated parallel rejection was live configuration drift rather than a code defect: `parallel_execution.enabled` remained `false` despite the completed X2A contract. The ignored config was changed to `true`, validated, and hot-reloaded without restarting CodexBridge or Cloudflare; public group `20260720T010132Z_powershell_group_3da40097` then completed two overlapping child runs successfully. A sixth entry exercises the repaired capability on a real two-test workload: the first group exposed the known shared Windows pytest-temp permission problem, while an immediate retry with isolated repository-owned basetemps completed both children concurrently with `5 passed` and `6 passed`. A seventh entry records a successful schema-bound Hermes `read_file` call against the live OP1 section of `PLANS.md` under registry generation `79`, with the exact tool schema, accepted arguments, no model runtime, empty protected stderr, and no repository mutation after correcting one caller-side request-construction mistake. An eighth entry exercises a Hermes-connected reversible action under registry generation `89`: an intentionally ambiguous post-commit response was authoritatively reconciled at exactly one application, replay returned `applied: false`, reversal succeeded, and final reconciliation proved absence. Several caller-harness and transport mistakes caused bounded failed attempts but no lost or duplicated work. A ninth entry reruns the complete seven-test Windows parallel lifecycle acceptance suite through the durable validation gateway, covering fan-out, restart adoption, exact cancellation, and pending-child refill with no lost or duplicated work. A tenth entry exercises the complete live service self-check, promotes the known stale `run_start` schema assertion from observation to a bounded repair, and restores the full gate to `1194 passed, 5 skipped` with healthy imports, configuration, dependencies, stores, and HTTP transport. An eleventh entry exercises bounded real-service capability and health paths: Cloudflare correctly reports no configured repository profiles, while Docker reports an installed Windows client and Compose runtime but an unavailable Docker Desktop Linux engine. Neither condition caused mutation, lost work, duplicate work, or a CodexBridge defect, and no service was started solely for evidence. A twelfth entry repairs two real-workflow contract defects: `repo_query diff` no longer crashes if a Git capture stream is absent, and the advertised `stdin_text` field now UTF-8 encodes safely for byte-capable PowerShell profiles. Focused and adjacent suites passed, a server-only durable restart adopted its worker and published once, the Cloudflare PID remained unchanged, and both public paths were verified under the new build. Parallel execution is available and usable for representative validation. The formal review found no unresolved security, destructive-targeting, corruption, lost-work, duplicate-work, or continuation-blocking defect. Bounded contract defects discovered during real use were repaired and regression-locked; configuration and infrastructure availability observations remain operational evidence rather than architectural programs. OP1 is complete, no Roadmap V3 promotion threshold was crossed, and the next roadmap unit is TL0.

After H1, freeze architectural expansion and exercise:

- ordinary local repository and service work that requires no newly rented infrastructure;
- parallel build or test work;
- repeated connector use across separate ChatGPT sessions;
- Hermes-backed reads and approved reversible external actions;
- optional remote or GPU-host work only when that infrastructure is already running for an actual user-requested workload, never provisioned solely for the pilot.

Create a separate pilot evidence log. Each entry records timestamp, project, expected outcome, HEAD/build identity, relevant run/tool identities, exact failure, lost or duplicated work, recovery, attribution, reproduction frequency, and artifacts.

Record normal friction before redesign. Repair immediately only for security violations, destructive targeting, lost or duplicated work, unrecoverable corruption, or a blocker preventing continuation.

## TL - CodexBridge Trading Lab

Status: **paused at TL5 while CF1 is the sole active roadmap lane; TL0 through TL4 accepted on 2026-07-20**.

This is a separate product roadmap. OP1 evidence has been reviewed and closed. TL0 passed against the user-established Alpari MT5 demo environment, with the retained acceptance bundle in [`docs/trading-lab-tl0-evidence.md`](docs/trading-lab-tl0-evidence.md). TL1 through TL4 have completed their deterministic acceptance gates. Trading development remains demo/internal-paper only; live-money execution is unavailable and out of scope.

### Core architecture

Do not build broker connectivity from scratch.

```text
Alpari
  <->
MetaTrader 5 terminal
  <->
Official MetaTrader5 Python integration
  <->
CodexBridge Trading Lab
  <->
ChatGPT
```

The official MetaTrader 5 Python package is the broker-platform boundary for account details, symbol specifications, live bid/ask ticks, historical candles and ticks, active orders and positions, margin and profit calculations, order validation, order submission with one stop-loss and one take-profit, and completed-order/deal history.

Python communicates locally with a running MT5 terminal rather than a cloud REST API. The terminal is therefore a supervised Windows runtime dependency with explicit health, reconnect, and stale-data handling.

### Relationship with Hermes

Do not force MT5 through Hermes merely because Hermes exposes tools.

```text
CodexBridge Trading domain
  |- MT5 adapter
  |    prices, candles, account, orders, positions
  |- Trading Lab
  |    signals, threshold portfolios, simulation, results
  `- Hermes gateway
       news, economic events, and optional external research tools
```

CodexBridge owns durable trading state, account and terminal identity, signals, portfolios, positions, orders, reconciliation, and lifecycle evidence. Hermes may supply external context, but it must not own balances, positions, orders, or trade lifecycle.

### Frozen v1 experiment

```yaml
broker: Alpari
platform: MetaTrader 5
broker_environment: practice/demo

instrument: discovered from the connected Alpari MT5 terminal
analysis_timeframe: 4H
analysis_frequency: once per hour

decisions:
  - LONG
  - SHORT
  - NO_TRADE

confidence_range: 50-99

virtual_portfolios:
  thresholds: T50 through T99
  baseline_source: actual Alpari MT5 account equity and currency captured at experiment start
  example_baseline: 1000 USD for the current practice account
  initialization: each threshold portfolio is an independent clone of the captured baseline
  allocation_per_trade: 1 USD normalized virtual notional
  maximum_combined_allocation: 20 percent of each portfolio's own current equity
  cohort_boundary: deposit, withdrawal, account reset, or intentional baseline change starts a new experiment cohort

trade_structure:
  entry: one market entry
  stop_loss: one fixed price
  take_profit: one fixed price

excluded:
  - trailing stops
  - multiple take-profits
  - partial exits
  - scaling in or out
  - fixed holding deadline
  - confidence-based position sizing
  - leverage optimisation
  - real-money execution
```

For v1, remove entry zones and pending-order logic. When the current executable price is unsuitable, ChatGPT returns `NO_TRADE`. Pending limit and stop entries are a later leaf after the market-entry trunk is stable.

### Exact signal contract

```yaml
signal_id:
created_at_utc:
broker: alpari
symbol:
analysis_timeframe: 4H

decision: LONG | SHORT | NO_TRADE
confidence: 50-99 | null

bid:
ask:
spread:
market_data_timestamp:
latest_completed_4h_candle:
developing_4h_candle:

entry_type: MARKET
entry_reference_price:
stop_loss:
take_profit:
risk_reward:

reason:
news_context:
market_snapshot_id:
```

Validation is deliberately narrow:

- `LONG`: `stop_loss < executable entry < take_profit`;
- `SHORT`: `take_profit < executable entry < stop_loss`;
- the bridge calculates risk/reward but does not impose an arbitrary minimum or relocate ChatGPT's stop-loss or take-profit;
- `NO_TRADE` has no executable entry, stop-loss, take-profit, or confidence-driven allocation.

### Confidence behaviour

One signal receives one score. For a `SHORT` signal with confidence `73`, portfolios `T50` through `T73` are eligible and `T74` through `T99` do not trade.

Each threshold portfolio is independent. A portfolio already holding the symbol skips the signal while another eligible portfolio may still enter.

### Honest execution-price rules

The simulator must not use midpoint prices.

- open long at ask;
- close long at bid;
- open short at bid;
- close short at ask.

This naturally includes broker spread.

A trade ends only when its take-profit or stop-loss is reached. The 4H interval is the analysis candle timeframe, not a four-hour holding deadline.

After connectivity loss, CodexBridge retrieves missed ticks where available. If both stop-loss and take-profit appear inside the same historical candle and reliable tick ordering cannot be recovered, the outcome is `AMBIGUOUS_DATA`; the system must never choose the favourable result silently.

### Main components

#### 1. MT5 provider adapter

Responsibilities:

- connect and authenticate to the local MT5 terminal;
- discover broker-specific symbols rather than hardcoding names such as `BTCUSD`;
- read complete symbol specifications;
- retrieve fresh bid/ask ticks;
- retrieve completed and developing 4H candles;
- retrieve historical ticks after downtime;
- inspect account, connection, and terminal health;
- later, submit demo orders and inspect positions, orders, deals, and history.

#### 2. Immutable market-packet builder

Every hourly analysis receives one immutable packet:

```yaml
packet_id:
provider:
server:
account_environment: demo
symbol:
created_at_utc:

symbol_specification:
  digits:
  tick_size:
  tick_value:
  contract_size:
  minimum_volume:
  volume_step:
  margin_information:

latest_tick:
  bid:
  ask:
  timestamp:

completed_4h_candles: 100-200
developing_4h_candle:
data_age:
warnings:
content_hash:
```

The packet builder also produces a simple candlestick PNG from exactly the same data. Structured values remain authoritative; the chart is interpretive assistance only.

#### 3. Immutable signal journal

After submission, direction, confidence, entry, stop-loss, take-profit, reason, market snapshot, and timestamp cannot change. A mistaken signal may be marked invalid before execution, but it must never be edited after later market movement becomes visible.

#### 4. Threshold portfolio engine

Maintain 50 independent portfolios, `T50` through `T99`, each storing:

- experiment cohort identity;
- baseline equity and currency captured from the Alpari MT5 account at experiment start;
- current equity;
- available allocation;
- open position;
- completed trades;
- net P&L;
- maximum drawdown.

Every threshold portfolio begins as an independent clone of the same captured account equity and currency. For the current practice account, the example baseline is 1,000 USD. The portfolios do not share or divide the broker balance. After initialization, each evolves independently from its own trades and must not be continuously resynchronised to the broker account.

A deposit, withdrawal, account reset, or intentional baseline change closes the current baseline definition and starts a new experiment cohort; it must not rewrite the history or current equity of an existing cohort.

The 1 USD experiment allocation means normalized virtual notional at 1x exposure. It is not an MT5 lot and not leveraged broker margin, preventing broker minimum volume and leverage from contaminating confidence-threshold testing. Maximum combined active allocation remains capped at 20 percent of each portfolio's own current equity.

#### 5. Deterministic trade supervisor

This component performs no analysis. It only:

- watches bid/ask;
- opens eligible virtual positions;
- detects the first stop-loss or take-profit event;
- calculates P&L and recorded costs;
- updates threshold portfolios;
- recovers open trades after service restart;
- resolves every position exactly once.

It must reuse CodexBridge durable workers, leases, heartbeats, protected evidence, process ownership, cancellation, and restart reconciliation rather than creating another durability subsystem.

#### 6. Evaluation engine

Report per threshold:

- signal count;
- entered-trade count;
- win rate;
- net P&L;
- average return;
- profit factor;
- maximum drawdown;
- longest losing streak;
- average stop-loss distance;
- average take-profit distance;
- average risk/reward;
- monthly results;
- results by confidence band.

Do not select the single highest-profit threshold. Prefer positive performance with enough trades, acceptable drawdown, stability across neighbouring thresholds, and persistence across genuinely fresh periods.

### CodexBridge tool surface

Read tools:

- `trading_provider_health`;
- `trading_list_symbols`;
- `trading_symbol_specification`;
- `trading_market_packet`;
- `trading_open_virtual_positions`;
- `trading_signal_get`;
- `trading_signal_list`;
- `trading_threshold_report`;
- `trading_portfolio_status`.

Write tools:

- `trading_signal_submit`;
- `trading_signal_cancel_before_entry`;
- `trading_lab_start`;
- `trading_lab_stop`;
- `trading_lab_reset`.

Separately gated demo-execution tools may later include:

- `trading_demo_order_submit`;
- `trading_demo_order_close`;
- `trading_demo_order_cancel`;
- `trading_demo_reconcile`.

There is no live-order tool in v1.

### Safety model

Trading environment and autonomy remain separate axes. The current CodexBridge deployment remains permissive-only; any future restoration of additional autonomy profiles must never change trading execution mode implicitly.

```yaml
execution_mode:
  - internal_paper
  - broker_demo
  - live
```

Selecting `permissive` must never promote `internal_paper` or `broker_demo` to `live`.

Hard controls:

- credentials never appear in logs, events, summaries, or public tool output;
- demo and live accounts use separate configuration and identity;
- global trading kill switch;
- idempotency key on every signal and order;
- one active position per symbol per threshold;
- 20 percent combined allocation cap;
- duplicate-order detection;
- broker-ticket reconciliation;
- stale-data rejection;
- disconnected-terminal rejection;
- explicit environment identity on every packet, signal, position, and order;
- no automatic promotion to live execution.

### Roadmap

#### TL0 - Alpari/MT5 acceptance spike

Status: **complete**.

Acceptance completed on 2026-07-20. The exact broker symbol is `BITCOIN_i`; the demo account, contract specification, live bid/ask, completed and developing H4 candles, minimum-volume buy and sell checks, minimum demo buy and sell round trips, order/position/deal/history retrieval, and terminal restart/reconnection all passed. The account baseline was read from MT5 as `1000.00 USD` before the acceptance trades and ended at `998.72 USD` after two immediate spread losses; future experiment cohorts must recapture current equity and currency rather than hard-code either value. Full evidence and durable artifact identities are preserved in [`docs/trading-lab-tl0-evidence.md`](docs/trading-lab-tl0-evidence.md).

Before repository implementation:

- create an Alpari MT5 practice account;
- install and log into MT5;
- discover the exact BTC symbol;
- read its complete contract specification;
- confirm fresh bid and ask;
- retrieve completed and developing 4H candles;
- confirm both buy and sell are supported;
- run `order_check` for buy and sell with one stop-loss and one take-profit;
- place the smallest demo buy and sell;
- confirm account, position, order, deal, and history retrieval;
- capture the practice account's actual equity and currency as the candidate experiment baseline;
- restart MT5 and test reconnection.

Gate: a written evidence bundle containing symbol name, minimum volume, contract size, spread, account mode, captured account equity and currency, order-check and demo-order results, reconnection evidence, and screenshots or protected logs. The evidence must show that the baseline is read from MT5 rather than hard-coded; the current practice-account example is 1,000 USD.

No CodexBridge trading source file may be created before TL0 passes.

#### TL1 - Read-only MT5 adapter

Status: **complete; accepted on 2026-07-20**.

The provider, repository-scoped demo-only configuration boundary, and public `trading_query` surface now cover provider health, bounded symbol discovery, configured-symbol specification, fresh bid/ask ticks, completed and developing H4 candles, and timezone-aware historical tick recovery. The exact symbol path distinguishes `BITCOIN_i` from `BITCOIN CASH_i`, retains raw provider epochs, and normalizes the observed `+03:00` broker offset explicitly. Trading remains disabled by default and the configuration cannot express live execution.

The first live public-gateway smoke exposed a real provider defect hidden by dictionary fixtures: the official MetaTrader5 package returns NumPy structured rows, and converting them with `tolist()` discarded field names, producing zero-valued candles. Commit `fdcfedd49aca6d1b150ad6197b45d085ae3553c3` preserves structured row identity and adds a named-record regression.

Acceptance evidence:

- focused provider run `20260720T112042Z_project_command_d49b3c06`: `5 passed`;
- adjacent gateway run `20260720T112057Z_project_command_ac547436`: `34 passed`;
- live Alpari demo gateway run `20260720T112127Z_executable_profile_b8cd735d`: exit `0`, empty protected stderr, protected stdout SHA-256 `c75b9a258e42db0294293a8029c1bd79d9b8e9dbffcc0cbf6d6b87c11040acfa`;
- live health returned connected demo account `Alpari-MT5-Demo`, `998.72 USD` balance/equity;
- symbol discovery returned exactly `BITCOIN CASH_i` and `BITCOIN_i` for the Bitcoin query;
- specification returned contract size `1.0`, minimum volume `0.01`, and volume step `0.01` for `BITCOIN_i`;
- fresh tick returned bid `64237.51`, ask `64301.79`, age below one second, and the raw/normalized timestamp pair;
- five completed H4 candles plus one developing H4 candle contained real nonzero OHLC and raw timestamps;
- the preceding 30-minute recovery range returned nonempty historical ticks with raw and normalized timestamps.

Gate: passed. TL2 is now active.

#### TL2 - Market packet and chart

Status: **complete; accepted on 2026-07-20**.

The repository has frozen market-packet payload and envelope models, deterministic canonical JSON and SHA-256 content identity, and a builder that reads health, exact symbol specification, one fresh tick, and 100-200 completed H4 candles plus one developing candle from one connected demo-provider snapshot. The builder rejects disconnected or non-demo providers, stale ticks, symbol drift, incomplete history, non-H4 candles, unordered or duplicate completed candles, and any completed/developing overlap.

A deterministic standard-library PNG renderer now consumes only the immutable packet candle tuple. It never receives or rereads the provider, preserves the structured packet unchanged, distinguishes the developing candle visually, binds chart identity to the packet content hash, and publishes a SHA-256 identity for the exact PNG bytes without adding a plotting dependency.

Acceptance evidence:

- commit `b82860de70319931cb26df8bc7918e80067ec877` added `codexbridge/trading/market_packet.py`;
- commit `0523968510868983edd2444e11264255bf658d2f` added deterministic packet regressions;
- commit `f3ca56101736eea4769c582372dd0b3f929910f1` added deterministic candlestick PNG rendering;
- commits `5a795f841005f7be0ef872bf54b7f1d35e3deae3` and `06b7d0433c6b5bdd45614a69e6c6c06b426fef7a` added and corrected focused chart regressions;
- packet run `20260720T142613Z_project_command_47e482f0`: `6 passed`;
- adjacent provider run `20260720T142636Z_project_command_6a1284ac`: `5 passed`;
- chart run `20260720T152826Z_project_command_23d0d57a`: `4 passed`;
- adjacent packet run `20260720T152837Z_project_command_6a037c29`: `6 passed`.

Gate: passed. TL3 is now active.

#### TL3 - Signal journal

Status: **complete; accepted on 2026-07-20**.

The durable journal defines frozen `LONG | SHORT | NO_TRADE` payloads, canonical content hashing, exact market-packet ID/hash binding, ask-priced long and bid-priced short validation, bridge-calculated spread and risk/reward, and strict `50-99` integer confidence. `NO_TRADE` rejects confidence and executable prices. SQLite WAL storage provides deterministic signal IDs, unique idempotency keys, immutable payload JSON, append-only lifecycle events, restart persistence, idempotent replay, cancellation only before entry, and entered/cancelled state exclusion without rewriting the signal payload.

Strict public request models and the `trading_signal_submit`, `trading_signal_get`, `trading_signal_list`, and `trading_signal_cancel_before_entry` gateways now share one repository-owned journal at `runs/trading/signals.sqlite3`. The public surface exposes no entry or execution transition. Submission replay is idempotent, conflicting content under one key fails closed, and cancellation preserves the exact immutable packet-bound payload.

The first focused run exposed one real validation defect: fractional confidence `73.5` was truncated to `73`. Commit `54468c2ac6e880a258e4d3793761a111067119e9` requires an actual non-boolean integer and preserves the frozen confidence contract.

Acceptance evidence:

- commits `1904b86fba59c0867ad4196a37273c6afd8be684`, `91129fb4ed04e1a73a82211668a4d6eda92ed276`, `54468c2ac6e880a258e4d3793761a111067119e9`, and `28cec59e5723731da4ca16a536d836011b0aa459` added and exported the immutable durable journal;
- commit `1932ee0c4b0389a44f5763f58aef1c95195ac5a7` added the strict public signal gateway and focused regressions;
- repaired journal run `20260720T162831Z_project_command_438f9d0c`: `16 passed`;
- adjacent packet run `20260720T162847Z_project_command_96c69e54`: `6 passed`;
- isolated public gateway run `20260720T171444Z_project_command_fced8b2d`: `36 passed`;
- isolated journal rerun `20260720T171458Z_project_command_11f449d7`: `16 passed`.

Gate: passed. TL4 is now active.

#### TL4 - Threshold simulator

Status: **complete; accepted on 2026-07-20**.

The frozen threshold engine creates exactly 50 independent portfolios, `T50` through `T99`, from one captured demo-account equity and currency baseline. Each portfolio receives its own immutable record and evolves independently. Trade routing uses a normalized `1.00 USD` stake at 1x virtual exposure, skips busy portfolios without blocking eligible free neighbours, treats `NO_TRADE` as a no-op, and is idempotent for repeated signal IDs.

Confidence `73` enters exactly `T50` through `T73` when all are free. Deposit, withdrawal, account reset, and intentional baseline-change transitions create new immutable experiment cohorts linked to the prior cohort while preserving all earlier balances, open-signal state, and cohort identity. Initialization from provider health fails closed unless the provider is connected, initialized, demo-only, and exposes equity.

Acceptance evidence:

- commits `2577d3e`, `cbf6995`, and `159e826` added the threshold simulator and focused regressions;
- focused threshold run `20260720T183936Z_project_command_a18926aa`: `6 passed`;
- adjacent immutable signal-journal run `20260720T184007Z_project_command_6ef7444e`: `16 passed`;
- both runs used repository-owned isolated pytest basetemps and changed no files.

Gate: passed. TL5 is now active.

#### TL5 - Durable supervisor

Track bid/ask and resolve exactly one stop-loss or one take-profit event.

Gate: restart during an open trade, recover it, and resolve it exactly once; ambiguous candle ordering becomes `AMBIGUOUS_DATA`.

#### TL6 - Reports and calibration

Add threshold, confidence, drawdown, stability, and fresh-period reports.

Gate: reports reproduce exactly from the append-only event journal.

#### TL7 - Alpari demo mirror

Mirror one selected reference threshold into the actual demo account while retaining all 50 virtual portfolios.

Gate: internal and broker fills, spreads, tickets, and outcomes reconcile without duplicate orders.

#### TL8 - Hourly orchestration

Only after manual operation is trustworthy:

```text
hourly market packet
  -> ChatGPT analysis
  -> immutable signal
  -> threshold decisions
  -> deterministic monitoring
```

No forced trade is generated when the signal is `NO_TRADE`, market data is stale, the terminal is disconnected, or validation fails.

#### TL9 - Live-readiness review

There is no automatic promotion.

Review:

- broker verification and residency requirements;
- deposit and withdrawal path;
- minimum practical position;
- fees, spread, commission, and swaps;
- broker reliability;
- regulatory and tax implications;
- performance on a genuinely fresh paper sample;
- operational recovery evidence;
- whether a live tool should exist at all.

Any live-execution implementation requires a new explicit roadmap decision, separate configuration, human approval boundaries, and independent acceptance evidence.

### Build/reuse boundary

Reuse:

- MT5 terminal;
- official MetaTrader5 Python package;
- Alpari price feed and demo execution;
- CodexBridge durability, policy, artifact, cancellation, and reconciliation infrastructure;
- Hermes external research tools.

Build:

- provider-neutral trading domain;
- immutable market packets and signal journal;
- `T50` through `T99` virtual portfolios;
- deterministic stop-loss/take-profit supervisor;
- confidence calibration and reporting;
- demo-order reconciliation.

Do not build a broker, general charting platform, discretionary strategy engine, or another Stream Alpha.

The next preserved Trading Lab gate is TL5: implement the deterministic durable supervisor that opens eligible virtual positions from immutable signals, watches honest bid/ask prices, resolves exactly one stop-loss or take-profit outcome, recovers open work after restart, and records `AMBIGUOUS_DATA` whenever reliable tick ordering cannot determine which boundary was reached first. TL5 is not active and must not resume until CF1 is complete and the user explicitly reactivates Trading Lab.

## Roadmap V3 Promotion Rules

Promote an observation when it violates a durability/security invariant, can lose or duplicate work, blocks a representative workflow, repeatedly requires manual recovery, reveals a repeated architectural pattern, or carries sufficient expected impact.

Attribute connector 502s before repair. Treat external fixture loss as infrastructure unavailability unless CodexBridge mishandles it. Write Roadmap V3 only after representative pilot evidence is reviewed.

## Deferred Work

- paid RunPod or other paid remote/GPU validation; evidence may be collected only opportunistically during actual user-requested workloads;
- broad environment and secret-reference expansion beyond H1 needs;
- a large provider-neutral synthetic acceptance matrix;
- project-memory and local-model expansion;
- supervisor, workflow, optional coding, and dashboard expansion;
- Codex re-enablement.

Historical R6, R7, P2, gate, commit, and validation specifications remain in the V2 achievement record.

## Validation and Commit Policy

For code: run focused then proportional adjacent tests, `git diff --check`, milestone-level full checks where justified, and real process/host tests when OS behavior is the subject. Commit every completed batch locally and never push without explicit instruction.

For documentation only: inspect the exact diff, run `git diff --check`, confirm only intended documentation changed, commit locally, confirm a clean worktree, and do not run the full suite.

Before every write or validation, inspect active durable runs and repository locks. Preserve unrelated work and never reset, clean, restore, discard, stash, amend, rebase, or rewrite history.
