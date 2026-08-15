# G7 Evidence and Telemetry Acceptance - 2026-08-15

Status: **ACCEPTED - SOURCE ONLY, NOT LIVE**

## Scope

Gate 7 adds bounded observability for the Patch Auto-Repair lifecycle without creating a surveillance surface, transcript log, new durable counter store, database migration, or automatic resolution authority.

Accepted G7 implementation commit:

- `8afead07fd1a390ba2daac621bceccce9707fa7e` - `Add G7 bounded patch evidence aggregation`

The accepted G6 source baseline was:

- `bb551744824fd7abbac02441f901b543bac33d7f` - `Accept G6 format validation`

The Patch Auto-Repair implementation plan remains:

- `docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md`
- SHA-256: `197e69d5f546744332de39549831f497a67495183e3df23aea6fb4f217b6e21a`

## G7.1 - Evidence derived from existing managed manifests

G7 adds the internal read-only module:

- `soma/repo_patch_evidence.py`

Its entry point is:

`summary_patch_evidence(repo_root, runs_dir, ...)` conceptually; the implemented function is `summarize_patch_evidence(...)`.

The summarizer derives aggregate evidence from existing `runs/managed_patches/<patch_id>/manifest.json` records. It does not introduce another persistence path.

It can aggregate:

- candidate validations attempted;
- candidate disposition counts;
- candidate language counts;
- repair proposals by `rule_id`;
- `accept_repair` decisions;
- `accept_original` decisions;
- `accept_original` after a repair proposal as a review signal;
- currently unresolved `preview_resolution_required` source manifests;
- validation elapsed-time buckets;
- candidate-size buckets;
- malformed validation-record counts;
- manifest read/ownership filtering evidence.

Resolution child manifests are ignored for validation/proposal/decision aggregation so source evidence is not counted twice after resolution.

### Validation elapsed buckets

The frozen aggregate buckets are:

- `< 1 ms`
- `1 ms to < 5 ms`
- `5 ms to < 25 ms`
- `25 ms to < 100 ms`
- `>= 100 ms`
- invalid/missing

### Candidate-size buckets

The frozen aggregate buckets are:

- `< 1 KiB`
- `1 KiB to < 16 KiB`
- `16 KiB to < 64 KiB`
- `64 KiB to < 256 KiB`
- `256 KiB to < 512 KiB`
- `>= 512 KiB`
- invalid/missing

These are reporting buckets only. They do not change validation or apply limits.

## Bounded manifest window

The first real-repository read exposed an operational issue that unit fixtures could not: the shared managed-patch history is large enough that an unbounded scan is inappropriate for a telemetry projection.

Initial real scan evidence:

Run: `20260815T085434Z_executable_profile_895ee6ab`

Result before adding a manifest-count budget:

- duration: **83.769 seconds**
- managed patch directories examined: **6,794**
- current-repository source manifests: **1,280**
- foreign/unbound manifests skipped: **5,514**
- candidate validations found: **33**
- candidate validation disposition: all `valid`
- candidate language: all `python`
- manifest read errors: `0`
- payload bodies read: `false`

G7 therefore added an explicit manifest scan budget rather than accepting unbounded history traversal.

Frozen scan policy:

- default manifests examined: **512**
- hard maximum caller budget: **4,096**
- ordering: newest managed patch ID first
- all matching directory names may be enumerated to establish truncation, but only the bounded newest window is stat/read as manifests;
- result exposes both `matching_patch_directories_discovered` and `scan_truncated`.

Bounded real scan evidence:

Run: `20260815T085823Z_executable_profile_4c3e87df`

Result:

- duration: **3.406 seconds**
- matching managed patch directories discovered: **6,797**
- manifest scan limit: **512**
- manifests examined: **512**
- `scan_truncated = true`
- current-repository source manifests in window: **338**
- foreign/unbound manifests skipped: **174**
- candidate validations in window: **35**
- candidate validation disposition: all `valid`
- candidate language: all `python`
- manifest read errors: `0`
- payload bodies read: `false`

The bounded snapshot is intentionally a newest-first window, not a claim of exhaustive historical totals when `scan_truncated=true`.

## Privacy and evidence minimization

G7 does not read managed patch payload/chunk/repair files.

A dedicated test replaces `Path.read_bytes` with a guard that fails for any filename other than `manifest.json`; the summary succeeds and reads only the manifest.

The aggregate result does not emit:

- patch IDs;
- source/model bodies;
- payload bytes;
- repair payload bytes;
- deleted repair excerpts;
- proposal IDs.

The result exposes only bounded aggregate counts/policy flags.

No additional copy of user/model source is stored for telemetry.

## Repository ownership and malformed evidence

Only manifests whose `repo_fingerprint` matches the requested repository contribute evidence.

Foreign or unbound manifests are counted as skipped and do not mix into the repository aggregate.

Malformed, oversized, missing, symlinked, or identity-mismatched manifest records do not abort valid evidence from other patch directories; they contribute bounded `manifest_read_errors` instead.

The managed-patch evidence root itself must be a regular directory and fails closed if it is a symlink.

Each manifest is capped at **2 MiB** for this evidence projection.

## G7.2 - False-positive review signal

`accept_original` after a repair proposal is recorded as:

`accept_original_after_repair_proposal_review_signals`

This is intentionally named a **review signal**, not a detector false-positive verdict.

The event can mean that the proposed corruption shape was intentional, that the controller preferred the original for another reason, or that the detector deserves later review. G7 does not infer which explanation is true.

A dedicated test proves the summary does not emit a `false_positive` conclusion from this event.

Similarly, a source that currently remains in `preview_resolution_required` is counted only as:

`currently_unresolved_resolution_required_sources`

G7 does not infer that the controller intentionally abandoned it. The summary explicitly reports:

`intentional_abandonment = not_inferred_from_unresolved_state`

## Rejected conflict/stale attempts are not faked

The plan lists resolution conflicts/stale failures as useful evidence.

Those failures are **not durably encoded in managed patch manifests** under the accepted G3 design. G3 intentionally avoids mutating a source manifest when a stale/invalid/conflicting resolution request fails preflight.

G7 does not weaken that property merely to obtain a counter.

The manifest-only summary therefore reports:

`resolution_conflicts_or_stale_failures = not_available_from_managed_patch_manifests`

Existing durable run/invocation evidence remains the appropriate place to investigate rejected public calls after activation. A future aggregate over that evidence would require its own bounded query design; it is not silently synthesized here.

## G7.3 - No silent/proven automatic resolution

G7 explicitly exports:

- `writes_state = false`
- `silent_auto_resolution_authorized = false`

Evidence quantity or detector confidence does not change the accepted explicit-resolution invariant.

Silent automatic repair remains prohibited unless a future **input contract itself** preserves trusted transport origin/provenance before parsing ambiguity is lost. If such a transport exists later, that exact contract must be researched separately.

No downstream regex/probability/telemetry threshold is treated as a substitute for trusted origin provenance.

## Validation evidence

### Focused G7 + G1-G6 compatibility

Run: `20260815T085745Z_executable_profile_c5bc91d2`

Result:

- **156 passed in 19.07s**
- Ruff check: passed
- Ruff format check: passed
- `git diff --check`: passed

Coverage includes:

- G7 aggregate evidence and scan bounds;
- G1 Python candidate validation;
- G6 JSON candidate validation;
- G2 repair proposal behavior;
- G3 explicit resolution;
- G5 repair-blind apply/revert compatibility.

The earlier run `20260815T085008Z_executable_profile_0af6dfcb` reached **150 passing tests plus one harness-only failure** caused by monkeypatching `Path.stat`, which also intercepted `Path.is_symlink()` internals. The harness was corrected without production semantic change.

### Public identity isolation

Run: `20260815T085846Z_executable_profile_ccd1cad7`

Result:

- focused public identity tests: **21 passed**
- public tool count: **34**
- operation schema count: **264**
- discovery stable: `true`
- public schema hash: `ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42`
- public descriptor hash: `7acb65f1c6e3d4b85ea82296bd7d5cec281211c1b5bc00214d3b5b4860106273`
- operation inventory hash: `71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`
- `repo_preview.resolve_patch` schema hash: `2fdbe6ae4bb313cc6a406f66b0db46140ee0979fe04a2035a37de14b697a0213`

These are exactly the accepted G4 source identities. G7 adds no public gateway or schema branch.

## Changed implementation/proof files

The G7 implementation commit contains exactly:

- `soma/repo_patch_evidence.py`
- `tests/test_repo_patch_evidence_g7.py`

No Company, Agent/Worker, Sol continuation/skill-layer research, new Sol implementation plan, or canonical-memory file entered the G7 implementation commit.

## Runtime remains intentionally pre-G4

Gate 7 is source acceptance, not activation.

Soma was not restarted for G7 and the ChatGPT connector was not refreshed. The running MCP process therefore intentionally remains on the pre-G4 public contract until A1 activation.

The running public schema remains:

`00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`

## Explicit non-actions

Gate 7 did **not**:

- create a database migration;
- add a durable telemetry counter table;
- add a public telemetry tool;
- read or duplicate patch payload bodies for telemetry;
- record transcripts;
- mutate source manifests on rejected resolution attempts;
- classify `accept_original` as proof of a false positive;
- infer intentional abandonment from unresolved state;
- enable silent automatic repair;
- change the accepted G4 public request schema;
- restart Soma;
- refresh the ChatGPT connector;
- push or deploy;
- use Codex or provider subagents;
- modify the concurrent Sol continuation/skill-layer plan, research files, final audit, or `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md`.

## Gate verdict

**G7 EVIDENCE AND TELEMETRY POLICY ACCEPTED.**

Soma now has a bounded, read-only, privacy-minimized aggregate evidence projection over existing managed patch manifests, with explicit limits on what can and cannot truthfully be inferred from that evidence.

No amount of telemetry changes the explicit-controller-resolution invariant.

**STOP at the top-level G7 boundary.**
