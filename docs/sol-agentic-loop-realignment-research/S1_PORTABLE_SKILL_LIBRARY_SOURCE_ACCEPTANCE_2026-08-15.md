# S1 Portable Skill Library Foundation — Source Acceptance

Date: 2026-08-15
Status: **SOURCE ACCEPTED — NOT LIVE ACTIVATED**
Stage: S1 only
Branch: `lane/memory-integration-foundation-1`
Implementation commit: `5dc8861968a68b9deea504aad0feb8b91a1ca8b7`
C5 baseline: `96bae73182f08708874b37fe48d336c32b4f913e`

## 1. Authority

S1 was implemented against:

- `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_IMPLEMENTATION_PLAN_2026-08-15.md`
  - SHA256: `c7ecbc45407adc5ad33db7abe402ec8838cbb9066f0fdc867e87cb984497a45f`
- `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_FINAL_AUDIT_2026-08-15.md`
  - SHA256: `e7bd042223e9e6560b9760509a2eee789cdf996b0a430e3b225be56a35c7ee9b`

The governing architectural invariant remains:

```text
Sol / ChatGPT = semantic reasoning controller
Soma          = mechanical truth, retrieval and execution substrate
Skill         = reusable guidance, not capability or authority
```

S1 does not introduce a Skill router, planner, reasoning engine, execution runtime, or a second semantic Skill format.

## 2. Accepted source scope

The implementation commit contains exactly four files:

```text
soma/config.py
soma/skills/__init__.py
soma/skills/library.py
tests/test_skill_library.py
```

Commit-range evidence from the C5 baseline:

```text
4 files changed, 1203 insertions(+)
```

No `docs/soma-improvement-research/*` file is included.

## 3. Canonical package format

S1 preserves the Agent Skills package as the semantic artifact:

```text
<skill-name>/
  SKILL.md
  scripts/        optional
  references/     optional
  assets/         optional
  ...             any other valid regular package files
```

Soma does not translate the package into a `SomaSkillV1` semantic schema.

The Markdown body is opaque to the library. Only mechanical package and standards-level metadata are validated.

## 4. Owner-controlled library location

`SkillLibraryConfig` now provides an explicit canonical library configuration.

Production intent:

```text
skill_library_kind = external_private_library
skill_library_root = <absolute owner-configured private path>
```

Development compatibility fallback:

```text
skill_library_kind = runs_internal_development
<runs>/skills
```

The fallback name intentionally exposes that it is a development location and is not the production-intent canonical owner library.

Configured external roots must be absolute. `external_private_library` without an explicit absolute root is rejected.

This follows the external-root honesty established by canonical project memory while keeping Skills a separate authority from project memory.

## 5. Self-contained external library architecture

The S1 library is self-contained beneath the resolved Skill-library root:

```text
<skill_library_root>/
  registry.sqlite3
  revisions/
    <package-hash>/
      <skill-name>/
        SKILL.md
        ... package files ...
  .staging/
```

Canonical semantic content is the immutable package bytes under `revisions/`.

`registry.sqlite3` stores only mechanical identity, provenance, state, and mutation replay information. It is not a replacement representation of Skill instructions.

The Skill registry is deliberately not added to `runs/soma.sqlite3`; reusable owner Skill artifacts remain independently portable under their configured owner root.

## 6. Agent-Skills-valid immutable revision layout

The exact immutable package root is:

```text
<skill_library_root>/revisions/<package-hash>/<skill-name>/
```

Therefore `SKILL.md` remains immediately beneath a directory whose name matches the Skill frontmatter `name`.

Historical revision trees are not placed beneath native scanner roots such as `.agents/skills` or `~/.agents/skills/`.

S1 contains no native scanner/export adapter. That remains a later concern.

## 7. Whole-package deterministic identity

S1 hashes the complete effective package, not only `SKILL.md` and not only conventional directories.

For every regular package file the deterministic manifest contains:

```text
normalized package-relative path using `/`
raw SHA256 of exact file bytes
size_bytes
```

Manifest entries are sorted by normalized package-relative path.

The canonical JSON representation of that manifest is SHA256-hashed to produce `package_hash`.

Mutable filesystem metadata such as mtime is excluded.

The additional deterministic `size_bytes` field does not weaken identity; exact byte SHA256 remains authoritative and size contributes another stable package fact.

Tests prove that changing any one of these changes package identity:

```text
SKILL.md
scripts/*
references/*
assets/*
custom/other regular files
```

Mapping/input order does not change the manifest or package hash.

## 8. Immutable Skill references

S1 uses content-addressed exact revision references:

```text
skill:<name>@sha256:<package-hash>
```

An exact ref names one immutable package revision.

Changing package bytes creates a different package hash/ref; the existing exact ref is never silently rebound.

## 9. Mechanical package validation

S1 validates only package mechanics and standards-level metadata.

Accepted validation includes:

```text
SKILL.md must exist
SKILL.md must be UTF-8
YAML frontmatter must exist and terminate
frontmatter must contain non-empty name
frontmatter must contain non-empty description
name uses the bounded portable lowercase/hyphen form
name length <= 64 characters
description length <= 1024 characters
package-relative paths only
no absolute paths
no `..` traversal
no backslash path ambiguity
no empty path segments
no Windows drive/colon ambiguity
no trailing-dot/trailing-space path components
no case-folding path collisions
bounded file count
bounded total package bytes
bounded single-file bytes
all symlinks rejected for v1 directory imports
frontmatter name == immediate package-root directory for directory import
stable deterministic manifest
```

The library does not decide whether a Skill's advice is correct, useful, safe, optimal, or intelligent.

## 10. Package bounds

Default internal bounds are explicit and configurable:

```text
max_files       = 256
max_total_bytes = 16 MiB
max_file_bytes  = 4 MiB
```

The public normal-Chat `files[]` request shape is not part of S1. S3 can adapt bounded text/base64 submission to this byte-package substrate without changing canonical package identity.

## 11. Crash-safe immutable materialization

Import follows this mechanical ordering:

```text
validate bounded package
compute exact manifest/package hash
stage under <root>/.staging
materialize revisions/<hash>/<name> atomically
record revision/provenance/state/replay metadata transactionally
```

If immutable materialization succeeds but later registry work fails, the content-addressed package may remain as an orphan. A retry verifies and reuses that exact immutable package and can complete registry recording safely.

A half-written package is never presented as a different revision identity.

## 12. Import request replay

`import_revision` requires a stable `controller_request_id` and normalized request hash.

The normalized mutation identity includes mechanical import semantics such as:

```text
Skill name
package hash
source kind/ref
make-current intent
expected state version
```

Behavior:

```text
same request ID + same normalized mutation -> stable replay
same request ID + different package/mutation -> SkillRequestConflict
```

Tests prove lost-response-style replay does not create a second revision.

## 13. Content convergence

Package identity remains content-derived independently of request identity.

Behavior:

```text
same Skill name + same package bytes
  -> same package_hash
  -> same skill_ref
  -> one immutable revision
```

Concurrent imports of identical bytes converge to one immutable revision.

## 14. Provenance

S1 records mechanical provenance separately from package identity.

Supported v1 source categories are:

```text
owner_local_import
repo_builtin_seed
native_exported_copy
imported_source
```

Each revision may record multiple provenance observations using `(source_kind, source_ref)`.

Therefore two sources that supply identical bytes converge to one immutable revision without erasing either provenance record.

A different package with the same Skill name may be imported as a new historical revision, but import does not silently replace the current package.

Project-local repository Skills are not automatically discovered or ingested.

## 15. Current/enabled mechanical state

S1 lays the internal reliability substrate required by the final audit for later S3 lifecycle operations.

Each Skill has mechanical state:

```text
current_package_hash
enabled
state_version
updated_at
```

State is distinct from immutable package bytes.

Changing current/enabled state does not rewrite historical revisions.

## 16. Compare-and-set protection

Internal `set_current` and `set_enabled` primitives require:

```text
expected_state_version
controller_request_id
```

They use compare-and-set rather than last-writer-wins mutation.

Concurrent `set_current` attempts from the same state version are proven to produce exactly:

```text
one winner
one stale-state conflict
```

Mutation request replay is stable and does not apply a second state transition.

These are internal S1 substrate methods only. No public `skill_action` gateway exists yet.

## 17. Integrity before promotion

`set_current` verifies the exact target immutable revision before moving the current pointer.

A historical revision modified out of band cannot be promoted as current merely because its old registry row still exists.

It fails as:

```text
package_integrity_mismatch
```

## 18. External drift detection

`get_revision(skill_ref)` reconstructs and validates the package identity against the stored immutable hash.

If canonical package bytes, paths, symlink status, or Skill-name relationship have changed out of band, retrieval fails with:

```text
package_integrity_mismatch
```

S1 never silently recomputes a new hash and pretends the same revision changed.

## 19. Historical revision immutability

Tests create multiple revisions, change the current pointer, and re-read old exact refs.

Old revision bytes remain independently addressable and unchanged.

Rollback in the later lifecycle layer can therefore be implemented mechanically as selecting an existing historical exact ref rather than copying package bytes.

## 20. No execution authority

Importing a package never executes bundled scripts.

A dedicated acceptance test imports a script that would create a marker file if executed; the marker is never created.

Source audit also found no subprocess launcher in `soma/skills`.

S1 does not introduce:

```text
skill_execute
SkillRuntime
hidden subprocess launch
Task/Run bypass
permission grants from Skill text
```

Future script execution, if requested, must use existing Soma Task/Run/domain execution authorities and an exact immutable resource path.

## 21. No second reasoning head

Read-only source scans over `soma/skills` found:

```text
router       -> no implementation hit
skill_execute -> no hit
LocalAgent   -> no hit
Supervisor   -> no hit
.agents      -> no hit
subprocess   -> no hit
```

The only `reasoning` occurrence is the module boundary statement that the Skill body is not parsed into plans, steps, routes, or reasoning state.

S1 therefore preserves Sol/ChatGPT as the semantic controller.

## 22. No public Skill gateway in S1

S1 intentionally adds no MCP/public Skill tool.

Not implemented in S1:

```text
skill_query
skill_action
Skill search/ranking gateway
normal-Chat list/search/get/resource
public files[] text/base64 ingestion
native Skill synchronization/export
built-in seed activation
```

Those remain in S2, S3, and S4 according to the accepted stage order.

## 23. Focused S1 acceptance

Initial focused run:

```text
run_id: 20260815T144331Z_executable_profile_cd210068
26 passed in 2.58s
Ruff: PASS
git diff --check: PASS
```

After concurrency/current-integrity hardening, final focused run:

```text
run_id: 20260815T144418Z_executable_profile_0864b3ab
28 passed in 2.74s
Ruff: PASS
git diff --check: PASS
```

The 28-test suite includes:

```text
external-root configuration honesty
minimal standards-valid package
whole-package hashing
mapping-order determinism
path traversal/non-portable path rejection
case-collision rejection
metadata validation
parent-directory/name validation
symlink rejection
package bounds
content convergence
multiple provenance observations
same-name source conflict without silent current replacement
import replay/conflict
out-of-band mutation detection
historical immutable retrieval
concurrent current-pointer CAS
state mutation replay
concurrent duplicate import convergence
tampered revision current-promotion refusal
no script execution
orphan-safe retry after registry failure
```

## 24. Cross-authority regression

Broad regression run:

```text
run_id: 20260815T144446Z_executable_profile_a894b7af
411 passed in 208.37s (0:03:28)
Ruff: PASS
git diff --check: PASS
exit_code: 0
lease_generation: 1
no worker recovery/relaunch
```

This covered S1 together with the existing configuration, RunStore/JobManager, continuation C1-C3, C4 Task/ProjectScope, C5 Run association, Hermes, and public contract/inventory seams.

## 25. Public contract non-interference

Because S1 adds no public gateway, its acceptance requires the C5 public contract to remain unchanged.

Fresh source identity probe:

```text
run_id: 20260815T144847Z_executable_profile_9775ea96
public gateways: 36
operation schemas: 275
discovery converged: true
public schema:
d0f8937730423a528e11dd6ad3a434402974f7aacb64e33a181ec3a28b5f64ec
public descriptor:
2041e44b4eb1ffb4f03a15f99a29521f0e8ad52e64e299b23e3c58255e6ac3bd
```

Canonical operation-inventory probe:

```text
run_id: 20260815T144904Z_executable_profile_bbd874fb
operation_inventory_gateway_count: 36
operation_inventory_hash:
07724723b5bfd4ebc2d6cef405bd39d8d0dfeece70a61c42f0c9e297c0f80e30
```

These are exactly the accepted C5 identities.

A preliminary identity probe mislabeled one returned tuple position as `inventory`; that label was not used as evidence. The canonical `_operation_identity_metadata` probe above was run immediately afterward and is the accepted inventory measurement.

## 26. C5 direct-Run operation hashes remain unchanged

```text
run_start.powershell
72660cbb255664cc1aa6e6825da0436761728d7d62beff74178e8f6e507f9a5f

run_start.remote_powershell
56414bda30c2d8624b0b1c4f249854137cf3951eecf8fc3d59fcfb718dd0f591

run_start.hermes_companion
bb2aeaeb72b5ce23b401b5840c7827b5c5a0d4e5e9bf91b6879bedc9dbe946e0

run_start.powershell_group
683c294968eb5719b5d19411d6928f7e407be0596cd389a7dc51219276cc753a

run_start.hermes_service
17ffb09310432c11e6666ad3a0c7bb23d014dd9263b03fc31d8945668c10265a
```

S1 therefore caused no public Run-contract churn.

## 27. Concurrent work preservation

Immediately before the S1 implementation commit, the worktree contained 18 untracked files under:

```text
docs/soma-improvement-research/
```

covering iterations 01 through 18.

They were treated as unrelated concurrent work and excluded from the S1 commit.

The selected S1 implementation commit contains exactly the four accepted source/test files and no improvement-research document.

## 28. Activation boundary

S1 is **source accepted, not live activated**.

No Soma restart was performed.
No connector refresh was performed.
No public operation repair was performed.
No Skill root was activated as a live production user library.
No native Skill export/synchronization was performed.
No push was performed.
No Codex agent was invoked.
No subagent was invoked.

The currently running Soma process may therefore still report source/running build drift until a later authorized rollout stage. That is not an S1 acceptance failure.

## 29. Explicitly deferred

S1 does not claim completion of:

```text
S2 progressive-disclosure skill_query
S3 public skill_action lifecycle and normal-Chat files[] ingestion
S4 built-in/seed Skill packaging
I1 integrated programme acceptance
I2 rollout/live activation
native scanner export/synchronization
project-local Skill auto-discovery
semantic Skill routing
Skill execution runtime
```

## 30. Verdict

**S1 PORTABLE SKILL LIBRARY FOUNDATION: SOURCE ACCEPTED — NOT LIVE ACTIVATED**

The source now provides a portable, owner-rooted, content-addressed Agent Skills library with immutable whole-package revisions, deterministic validation and hashing, provenance, replay-safe import mechanics, CAS-ready current/enabled state, and out-of-band integrity detection.

It does so without changing the public MCP surface, without creating a second semantic Skill representation, without automatically trusting repository-local Skills, without executing Skill content, and without moving semantic reasoning authority away from Sol/ChatGPT.

The next sequential gate is **S2 — `skill_query` progressive-disclosure gateway**. S2 is not started by this acceptance.
