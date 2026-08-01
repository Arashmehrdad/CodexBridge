# RELIABILITY-1 — Existing Runtime Hardening

**Activated:** 2026-08-01  
**Status:** active; sole implementation lane  
**Owner decision:** accepted before further large V3 implementation  
**Branch:** `lane/memory-integration-foundation-1`  
**Push:** not authorised

## Purpose

Prove that Soma's existing capabilities work reliably together under ordinary use, restart, replay, cancellation, failure, recovery, and newly discovered projects before adding another architectural layer.

`V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1` remains preserved but parked. No V3 interaction product implementation, provider-agent launch, team/mandate implementation, capability-broker work, or later company architecture may begin while this lane is active.

## Working method

This is a defect-driven hardening lane, not a redesign programme.

Every defect must:

1. be reproduced or supported by durable evidence;
2. receive a severity and affected authority boundary;
3. be repaired by the smallest coherent change;
4. gain a focused regression test;
5. receive adjacent validation proportional to its blast radius;
6. be recorded here with its disposition and evidence.

Do not perform speculative refactors, weaken fail-closed checks, create parallel authorities, rewrite history, reset/clean/stash unrelated work, or push.

## Baseline at activation

Recorded on 2026-08-01 before the first reliability mutation:

```text
branch:                 lane/memory-integration-foundation-1
HEAD:                   55e5feba187d7f444e131a0675990c2c7dfb5a2d
worktree:               clean
active runs:            0
queued runs:            0
launch-pending runs:    0
repository locks:       0
capability convergence: true
schema mismatches:      0
```

The baseline is healthy, but recent real-use failures prove that integration seams still require systematic adversarial validation.

## Required reliability passes

### R1-0 — Contract and observability baseline

**Initial capture:** complete on 2026-08-01; deeper anomaly investigation continues through the later passes.

- Gate and bug ledger frozen at commit `51ede5239f0c0be3b62e9e17a5b49709affda927`.
- Source, running build, public input schema, discovery cache, and authoritative operation inventory converged with zero mismatches; 246 operation schemas across 32 public gateways were visible.
- Lightweight self-check, configuration validation, startup reconciliation, and supervisor-store checks passed.
- SQLite `integrity_check` returned `ok`; foreign-key violations were zero; WAL was active; freelist count was zero.
- Public preflight reported a clean worktree, zero active/queued/launch-pending runs, and zero repository locks.
- Canonical memory was healthy and drift-free for both Soma (19 records) and `axon_modelling` (1 record). The optional provider remained explicitly degraded, so retrieval correctly reported `catalog_lexical` rather than claiming semantic coverage.
- The database census exposed `REL-005`: two published terminal workflows retained nonterminal child-step rows despite successful startup reconciliation.

### R1-1 — Fresh-project onboarding and project isolation

- Discover a disposable Git repository under an approved root.
- Prove explicit ProjectScope onboarding, idempotent repeat, exact `memory_scope`, canonical memory save/search/get/supersede/archive, and clean teardown of disposable content.
- Repeat after restart.
- Adversarially test similar repository names, wrong project IDs, wrong roots, ambiguous bindings, and cross-project retrieval.
- Reads must never create authority silently.

**Live progress on 2026-08-01:** two deliberately similar disposable repositories, `soma_reliability_r1_20260801_a` and `soma_reliability_r1_20260801_b`, were discovered under `D:/Github` and bound exclusively to distinct deterministic project/resource identities. Explicit onboarding, idempotent repeat, exact scope resolution, save/search/get, supersession, compare-and-swap archive, bidirectional sibling-search isolation, direct foreign-memory-ID refusal, existing-project isolation, and mixed project/repository identity refusal all passed. Both disposable canaries are archived. Post-restart replay returned the same project/resource identities and preserved both custom project keys, proving `REL-010` live. A Git repository created outside every trusted discovery root was refused by `memory_bind_repository` and then removed without durable authority. Ambiguous normalized aliases were proven to select the first trusted root silently and are corrected by `REL-012`; exact folder names remain valid disambiguators while non-exact collisions fail closed before dynamic config or ProjectScope mutation. `REL-013` adds a generation-bound `memory_archive_repository` action that preserves all authority rows, refuses any task/run scope history, blocks archived rebootstrap, and makes an archived binding non-resolvable. R1-1 now needs only post-restart live archival of both disposable bindings, idempotent replay, exact folder deletion, and final absence verification.

### R1-2 — Runtime and connector convergence

- Prove committed source, running server, public input schema, operation inventory, discovery cache, and connector contract agree after restart.
- Prove code changes that cannot hot-reload report restart-required honestly.
- Prove stale connector schemas fail visibly and recover after refresh.
- Add a bounded operator-visible activation check for newly added public operations.

### R1-3 — Repository transaction reliability

- Exercise preview, manual apply, inspection, selected-file commit, automatic commit, stale-hash refusal, exact-context refusal, manual revert, automatic revert, move, cleanup, UTF-8, LF/CRLF, and rollback.
- Prove disposable manual apply/revert leaves both HEAD and worktree unchanged.
- Prove no empty/content-neutral commits are created by the recommended exploratory path.
- Prove rejected multi-edit transactions apply nothing and return useful per-operation diagnostics.
- Prove branch creation leaves the requested branch actively checked out before any subsequent write or commit, and removes any partial branch if the checkout postcondition fails.

**Live progress on 2026-08-01:** the isolated repository `soma_reliability_r13_20260801` completed the transaction matrix on branch `reliability/r1-3-transactions`. Stale-hash and exact-context previews failed before mutation; a two-operation preview with one valid and one invalid edit returned per-operation diagnostics while leaving HEAD and worktree unchanged. Branch creation created and checked out the requested branch atomically. Manual UTF-8/Persian/emoji apply, exact read-back, and selected-file commit passed. Automatic create/apply/commit and automatic revert/commit passed. A logical CRLF edit and revert preserved the original two CRLF sequences with zero newline-only churn. Hash-pinned moves preserved the exact content hash in both directions. Managed cleanup passed, replay was idempotent, and a changed-after-preview artifact was preserved by hash refusal before a fresh preview cleaned it. Hash-pinned manual removal and manual revert left HEAD unchanged and restored the exact file hash. A content-neutral selected-file commit was refused with no empty commit. The fixture ended clean at `5577287095000e01b951a11cfbcbf3afd79ded73`. `REL-014` and `REL-015` were discovered during this matrix and are source-fixed; formal R1-3 closure waits only for their batch restart activation proof.

### R1-4 — Durable task/run lifecycle

- Test admission, idempotent replay, conflicting replay, launch failure, cancellation, completion race, result publication, evidence retrieval, and restart reconciliation.
- Exercise queued, launch-pending, running, cancellation-pending, uncertain ownership, stale worker identity, and recovery disposition.
- Prove no duplicate child launch and no terminal publication before owned process-tree absence.

### R1-5 — Supervisor, workflow, handoff, and recovery seams

- Re-test every deliberate handoff state, including `needs_external_coder`, `approval_required`, `needs_input`, `blocked`, and terminal outcomes.
- Prove browser pulse exits or reports correctly rather than polling forever.
- Test workflow/supervisor crash windows, missing child attachment, stale decisions, cancellation precedence, and exact resume correlation.
- Do not activate the paused V3 interaction-command design.

### R1-6 — Storage, integrity, and operational runbook

- Check SQLite integrity and foreign keys.
- Inspect abandoned runs, stale locks, reconciliation events, evidence growth, and generated/tool-owned path hygiene.
- Prove canonical memory integrity/drift reporting and rebuild behaviour.
- Produce one concise operator runbook for startup, shutdown, restart, health checks, connector refresh, project onboarding, recovery, and evidence retrieval.

## Severity

- **Critical:** data loss, cross-project leakage, unauthorised action, duplicate irreversible action, or false terminal success.
- **High:** deadlock, unrecoverable durable state, silent partial write, wrong ownership, or public contract/runtime divergence that blocks normal use.
- **Medium:** safe refusal, misleading diagnostics, history pollution, avoidable operator intervention, or bounded compatibility break.
- **Low:** cosmetic or low-impact ergonomics with no authority, durability, isolation, or evidence risk.

Critical and high defects block lane acceptance. Medium defects require correction or an explicit owner-accepted deferral with bounded impact. Low defects may be deferred only when recorded.

## Bug ledger

| ID | Severity | State | Defect | Evidence / disposition |
|---|---|---|---|---|
| REL-001 | High | closed before activation | Browser pulse did not recognise `needs_external_coder`/approval handoff states and could poll forever. | Corrected and regression-tested in `REPO-DOCUMENT-EDITING-1`. |
| REL-002 | High | closed before activation | Sequential line-range edits could target shifted content without source anchoring. | Anchors, strict bounds, and same-file exclusivity added; regression-tested. |
| REL-003 | Medium | closed before activation | Every exploratory apply/revert committed immediately, creating history confetti. | `commit_mode="manual"` plus explicit selected-file commit and zero-commit apply/revert proof. |
| REL-004 | High | closed before activation | Dynamic repository discovery and ProjectScope onboarding could diverge, making canonical memory impossible for new projects. | `memory_bind_repository` added; real `axon_modelling` binding/save/read-back verified. |
| REL-005 | High | closed; live | A workflow parent could be terminal `reported / failed` and publication-complete while child-step rows remained `running` or `pending`. Valid old artifacts caused future startup reconciliation to preserve the contradiction indefinitely. | Reproduced publicly on `20260711T204946Z_workflow_8a0f35b2` and `20260711T205044Z_workflow_3b1b2847`. Terminal publication now reconciles orphaned open steps, republishes under the repaired hash, emits a durable event, and refuses to hide any still-owned child run. Validation: 26 focused plus 83 adjacent tests passed. A SQLite backup was created at `runs/reliability-1/rel-005-20260801T093654Z/soma-before-rel-005.sqlite3` (SHA-256 `fe8479e86184d60419b51d6c9e22243810f481a1acc334fb38aaddb6571732e2`). Both live records were repaired and publicly verified: running/running became failed/failed; running/pending became failed/skipped; both publication hashes reproduce exactly. Source/runtime convergence after restart proved the general repair live. |
| REL-006 | Medium | closed; live | Hermes shared-service responses exposed `active_toolsets: []` beside a populated callable registry. The field represented an optional selection filter, where empty meant unrestricted, but its name and missing catalog identity naturally led controllers to conclude that zero toolsets were available and refuse valid work. Soma also passed the empty list into Hermes even though the pinned Hermes contract defines `None` as unrestricted. | Reproduced live at registry generation 85: official `tool_search` returned five `mcp-searchconsole` tools and official `tool_call` returned `pong`, while the outer result still said `active_toolsets: []`. Responses now expose `catalog_tool_count`, `catalog_toolset_count`, `catalog_toolsets`, `toolset_selection_mode`, and `selected_toolsets`; the legacy field remains with explicit semantics. Unrestricted execution now passes `None`, not an empty allowlist. Validation: 56 focused Hermes tests plus 217 public-result/server projection tests passed; post-restart capability identity converged. |
| REL-007 | Medium | closed; live | `run_query(terminal)` returned top-level `ok: false` for a healthy pending query and for terminal run failures, while also returning an empty `error`. The flag mixed query success with the run's business outcome, encouraging controllers to treat ordinary pending or failed work as a broken Soma query. | Reproduced live on a running validation run. Read responses now use top-level `ok` and `query_succeeded` strictly for query success, declare `ok_semantics: query_success`, and expose `terminal`, `result_available`, `run_ok`, and `run_outcome` separately. Projection fallback remains a successful query but is marked `projection_degraded`. |
| REL-008 | Medium | closed; live | A successful fresh repository-status read could carry `recommended_action: Retry the live repository-status check`, causing controllers to distrust valid live Git state and repeat work unnecessarily. | Reproduced on Soma's own clean live status. Successful full and compact status results now explicitly return an empty recommended action; retry guidance is emitted only for timeout/failure or non-fresh results. |
| REL-009 | High | closed; live | Capability identity used one connector-refresh instruction for every mismatch. A source/running build mismatch therefore told controllers to refresh ChatGPT instead of restarting Soma, while operation-inventory defects and connector drift also received the same generic advice. | Mismatches are now classified into `restart_required`, `connector_refresh_required`, and `operation_contract_repair_required`, with ordered machine-readable and human-readable recovery actions. Restart-only, connector-only, and operation-schema regression tests prove distinct remediation. REL-007 through REL-009 validation: 236 focused tests plus 470 adjacent gate/contract tests passed, with 26 expected skips. Post-restart live probes proved all three corrected contracts active. |
| REL-010 | Medium | closed; live | An idempotent `memory_bind_repository` repeat returned `project_key: ""` even when the existing ProjectScope project had a persisted custom key. The binding identity remained correct, but the response discarded authoritative identity metadata and could mislead controllers comparing first-bind and repeat-bind acknowledgements. | Reproduced live with disposable repository A. `RepositoryBinding` now carries the persisted `projects.project_key`, repository resolution selects it, and both first-time and repeated binding responses return the stored value. A custom-key regression test proves persistence. Validation: 39 focused ProjectScope/memory tests plus 363 adjacent ProjectScope, knowledge, discovery, inventory, and public-contract tests passed; Python compilation and `git diff --check` passed. Post-restart live replay returned `reliability-r1-isolation-a` and `reliability-r1-isolation-b` unchanged with `binding_applied: false`. |
| REL-011 | High | closed; live | `repo_commit(operation="create_branch")` created a local branch but deliberately did not check it out, then returned `ok: true`. A controller could therefore begin writing or committing on the previous branch while believing the new lane was active. | Reproduced with a disposable repository: before `master`, after `master`, requested branch present, and function result `ok: true`. The primitive now uses one create-and-switch command, verifies the active branch, reports `previous_branch`, `current_branch`, `branch_created`, and `switched`, and removes a partial branch if the postcondition is not met. The after-probe ended on `feature/rel011-after` with `status: checked_out` and `switched: true`. Validation: 146 focused Git/gateway/inventory tests plus 241 adjacent discovery and public-contract tests passed, with 26 expected skips; Python compilation and `git diff --check` passed. Post-restart capability identity converged with the corrected primitive loaded. |
| REL-012 | High | fix validated; runtime activation pending restart | Dynamic repository discovery silently selected the first trusted Git root when a non-exact alias normalized to multiple folder names. A caller could therefore receive a valid repository resolution for the wrong project and perform later reads or writes under incorrect ownership. | Reproduced in isolated temporary roots: `Alpha-Beta` and `Alpha.Beta` both matched `alpha_beta`, which resolved to `Alpha-Beta` without an error. Resolution now applies exact-folder precedence, then requires a unique canonical alias, then a unique separator-insensitive alias; any tie names all candidates and fails before dynamic config or ProjectScope mutation. Exact folder names still disambiguate. Wrong-root onboarding was also proven to fail closed independently. Validation: 60 focused discovery/resolution/ProjectScope/memory tests plus 477 adjacent repository, Git, server, inventory, and public-contract tests passed; compilation and `git diff --check` passed. |
| REL-013 | Medium | fix validated; runtime and connector activation pending restart/refresh | ProjectScope supported archived lifecycle internally but exposed no safe public repository-binding teardown. Disposable repository roots therefore had to remain on disk indefinitely or be deleted while still holding active authority. | Added `memory_archive_repository` with exact project/repository identity and compare-and-swap scope generation. It archives only projects with zero task/run scope history, increments generation, preserves every project/resource/binding row, makes active resolution fail, supports exact idempotent replay, and prevents `memory_bind_repository` from rebootstraping archived or suspended identities. No schema migration is needed because lifecycle and generation are existing authority fields. Validation: 146 focused ProjectScope/memory/schema/inventory tests plus 375 adjacent server, discovery, connector-contract, capability, footprint, and transport tests passed, with 26 expected skips; compilation and `git diff --check` passed. |
| REL-014 | Medium | fix validated; runtime activation pending restart | Read and preview gateways accepted an exact discovered folder alias while durable `repo_apply` rejected the same alias as an unknown repository. The caller had to translate the preview response into a canonical name manually, breaking one transaction identity across preview and apply. | Reproduced with `__soma_reliability_r13_20260801`: preview succeeded and returned canonical `soma_reliability_r13_20260801`, but apply with the original folder alias was refused before mutation; retry with the canonical name succeeded. `repo_apply` now resolves once through the discovery-aware public identity path, persists only the canonical repository name into the durable run, and preserves `requested_repo_name` in its acknowledgement. Validation: 462 repository/server/worker/public-contract tests passed before the adjacent REL-015 batch; the final combined suite passed 498 tests, plus compilation and `git diff --check`. |
| REL-015 | Medium | fix validated; runtime activation pending restart | A deliberate changed-after-preview managed-artifact refusal was publicly classified as `infrastructure_failure` with risk `Async worker failed`, even though the worker and storage were healthy and the artifact was correctly preserved. This encouraged the wrong recovery action for an expected hash-safety conflict. | Reproduced live by previewing `.ruff_cache/stale-probe`, changing its hash, and applying the stale cleanup. The file remained intact, but the terminal result reported infrastructure failure. Durable `repo_apply` now converts expected managed-write `ValueError` conflicts into `validation_failure` safety refusals with the exact reason and no invented infrastructure risk; unexpected exceptions still use the generic infrastructure path. A worker-level regression proves persisted status, classification, safety state, and public-outcome inputs. Final validation: 498 tests passed; compilation and `git diff --check` passed. |

## Investigation observations

These are not classified as defects without a failing behavioral reproduction:

- **OBS-001:** optional canonical-memory provider health is degraded for the checked projects; canonical storage and integrity are healthy, and retrieval honestly reports lexical mode.
- **OBS-002:** the latest startup `job_runs` reconciliation recorded approximately 101 seconds while succeeding. R1-4/R1-6 must determine whether this is expected historical volume cost or an operational performance defect.
- **OBS-003:** historical supervisor rows remain in planning/needs-input states. R1-5 must distinguish intentionally parked handoffs from abandoned or misleading state before assigning a bug ID.
- **OBS-004:** internal ProjectScope startup reconciliation returns `ok: true, available: false` without a reason when its schema is not installed. This was not found on a public controller path and did not reproduce an incorrect action, so it remains an observation rather than a defect.
- **OBS-005 (resolved in source as REL-013):** ProjectScope supports active/suspended/archived lifecycle states internally but previously exposed no safe public repository-binding teardown operation. The bounded archival action is validated; post-restart live archival and disposable-root deletion remain before R1-1 closes.

## Controller-contract clarity audit

The 2026-08-01 audit mechanically scanned public and projection code for overloaded `ok`, `active`, `enabled`, `selected`, `available`, `ready`, `degraded`, `fallback`, empty-list, empty-string, and generic recovery sentinels. It then reproduced candidates through live gateways and checked adjacent tests.

No REL-006-equivalent ambiguity was found in canonical task status/result, workflow status/result, supervisor status/resume prompts, canonical memory health/results, startup reconciliation, repository search timeout/partial results, or explicit unavailable/never-recorded states. Those surfaces separate query success, availability, state, reason, and evidence sufficiently for an unfamiliar controller. `run_query(control)` unchanged polling was also checked: source emits `unchanged: true` only when the caller supplies an exact `if_state_version`; the earlier suspicious transcript was not reproducible as a source defect.

New defects receive the next sequential identifier. Investigation findings that do not reproduce as defects must remain observations and must not be presented as bugs.

## Acceptance gate

`RELIABILITY-1` closes only when:

- zero known critical or high defects remain;
- all medium defects are fixed or explicitly owner-deferred with bounded impact;
- a fresh disposable repository passes discovery through canonical memory before and after restart;
- source/runtime/schema/inventory/connector convergence passes;
- repository manual and automatic transaction paths pass without history pollution;
- replay, cancellation, crash-window, recovery, and evidence-publication scenarios pass;
- similar-project isolation and wrong-scope adversarial tests pass;
- no unexplained stale locks, abandoned runs, integrity failures, or hidden partial successes remain;
- every repaired defect has a regression test;
- focused and broad relevant suites pass;
- the operational runbook is complete;
- worktree is clean and nothing is pushed.

Only after owner review and acceptance may `PLANS.md` reactivate the next large V3 lane.
