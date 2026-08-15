# S3 Skill Lifecycle Source Acceptance - 2026-08-15

## Verdict

**S3 SOURCE ACCEPTED.**

S3 adds the bounded public `skill_action` lifecycle gateway over the already accepted S1 immutable portable Skill library and S2 progressive-disclosure read surface.

This is a **source acceptance only**. The running Soma connector was not restarted or refreshed for this stage. S3 is therefore **not live activated** by this acceptance.

Implementation commit:

- `839e04615336252cb800afe57572faecb9cf1888`
- title: `Implement S3 Skill lifecycle gateway`
- exact implementation scope: 14 files
- diff: 707 insertions, 15 deletions

Accepted predecessor:

- S2 acceptance HEAD: `a319d5f6ce06a4d8cfb7ccdf2071798add8704b1`

## Programme boundary

S3 implements the exact v1 lifecycle mutation surface required by the continuation/Skill-layer programme:

- `import_revision`
- `set_current`
- `rollback`
- `enable`
- `disable`

It deliberately does **not** add:

- permanent purge or delete;
- Skill execution;
- `skill_execute`;
- a Skill runtime;
- subprocess execution from the Skill package;
- semantic Skill routing;
- automatic Skill selection;
- automatic project-local `.agents` ingestion;
- LocalAgent or Supervisor semantic routing;
- second-model Skill classification;
- permission or capability authority derived from a Skill;
- hidden workflow DAGs or reasoning state.

Sol/ChatGPT remains responsible for semantic interpretation and choosing whether a Skill is relevant. Soma remains responsible for mechanical library identity, immutable bytes, lifecycle state, replay identity, and CAS safety.

## Public gateway

S3 adds one public gateway:

`skill_action`

Its public discriminated union contains exactly five branches:

1. `import_revision`
2. `set_current`
3. `rollback`
4. `enable`
5. `disable`

No other Skill mutation branch is exposed.

### Public annotations

The served metadata is intentionally conservative:

- `readOnlyHint = false`
- `destructiveHint = true`
- `idempotentHint = true`
- `openWorldHint = false`

The gateway is mutating and can replace the current pointer or disable normal discovery, so it is not advertised as read-only or purely additive. Stable controller request identity makes exact retries mechanically idempotent. The operation is local to the owner Skill library and does not require open-world access.

## Direct Chat import contract

`import_revision` supports bounded package ingestion directly from normal Chat through `files[]`.

Each file contains:

- `relative_path`
- exactly one of:
  - UTF-8 `text`
  - validated `base64_bytes`

The public model caps direct ingestion at 256 files. The underlying S1 `SkillLibrary` continues to enforce configured decoded package limits, including per-file and total package bytes.

The public import source kinds are deliberately limited to explicit external/owner ingestion:

- `owner_local_import`
- `imported_source`

The gateway does not expose `repo_builtin_seed` as a normal Chat import source, preventing an arbitrary repository-local Skill from being silently promoted through this surface.

## Immutable import semantics

The S3 gateway delegates canonical package behavior to the accepted S1 `SkillLibrary` rather than implementing a second storage path.

Import remains:

1. bounded;
2. metadata validated;
3. path normalized and collision checked;
4. whole-package manifest/hash derived;
5. materialized under immutable content-addressed revision storage;
6. recorded in the Skill registry;
7. optionally made current using state-version CAS.

Bundled scripts are treated as bytes only. Import never executes them.

## Replay identity

Every S3 lifecycle mutation requires `controller_request_id`.

### Import replay

For `import_revision`:

- same controller request ID + same canonical package/request => existing result replay;
- same controller request ID + different package/request => `skill_request_conflict`.

### Pointer/state replay

For `set_current`, `rollback`, `enable`, and `disable`:

- exact lost-response retry returns the existing mechanical result;
- the retry does not advance state a second time;
- a conflicting request identity is rejected.

No generic semantic command journal was added.

## CAS semantics

Mutable Skill state remains guarded by S1 state-version compare-and-swap.

The public action model requires `expected_state_version` for:

- `set_current`
- `rollback`
- `enable`
- `disable`

For `import_revision`, `expected_state_version` remains optional when no current pointer change is requested, but is available for guarded `make_current` behavior.

There is no last-writer-wins lifecycle update path.

## Rollback semantics

`rollback` is a convenience operation over the same mechanical current-pointer primitive as `set_current`.

It:

- points current to an already existing immutable historical `skill_ref`;
- requires state-version CAS;
- requires a stable controller request ID;
- does not duplicate or rewrite the old package;
- leaves later revisions intact and retrievable by exact immutable ref.

Rollback is therefore library pointer repair, not history mutation.

## Enable/disable semantics

`enable` and `disable` modify only normal discovery visibility.

Disabling a Skill:

- removes it from current-enabled `skill_query.list/search` discovery;
- does not delete the package;
- does not invalidate the immutable `skill_ref`;
- does not turn the Skill into an authorization object.

Exact immutable ref retrieval remains available while disabled.

Re-enabling restores normal current-enabled discovery.

## Error projection

The gateway maps mechanical failures to stable public error codes:

- `package_integrity_mismatch`
- `skill_not_found`
- `skill_request_conflict`
- `stale_skill_state`
- `invalid_skill_action`

These are mechanical library/action failures only. Soma does not infer semantic intent or choose a recovery action for the model.

## Crash-safety evidence

S3 acceptance explicitly covers both required import interruption boundaries.

### Failure during staging/materialization

A failure-injection test forces the atomic immutable staging move to fail while importing with `make_current=True`.

Verified result:

- no Skill revision is registered;
- no Skill state/current pointer exists;
- no immutable revision directory for the package is published;
- the staging directory is cleaned;
- no half-current revision becomes visible.

### Failure after immutable materialization but before registry commit

The existing S1 orphan-materialization test deliberately fails registry request recording after immutable bytes have been materialized.

Verified result:

- one immutable orphan materialization may remain;
- the registry/history remains empty;
- retrying the same import safely adopts/records the same immutable package;
- no duplicate revision is created;
- the recovered revision passes integrity verification.

Together these prove the intended stage -> immutable materialize -> registry ordering does not create a half-published current Skill.

## Concurrency evidence

### Concurrent `set_current`

Two writers use the same expected state version while targeting different immutable revisions.

Verified:

- exactly one writer succeeds;
- exactly one writer receives `stale_skill_state`;
- state version advances exactly once;
- the resulting current pointer is one of the two requested immutable refs;
- no last-writer-wins overwrite occurs.

### Concurrent enable/disable

`enable` and `disable` race using the same expected state version.

Verified:

- exactly one succeeds;
- exactly one receives `stale_skill_state`;
- state version advances exactly once;
- no later blind overwrite occurs.

## Direct Chat ingestion evidence

The S3 gateway test imports one package containing:

- textual `SKILL.md`;
- a binary resource encoded as base64;
- a Python script resource containing a sentinel side effect.

Verified:

- import succeeds;
- binary bytes round-trip exactly through S2 `skill_query.resource`;
- the script is never executed during import or retrieval;
- exact request replay is stable;
- same request ID with changed package bytes is rejected as conflict.

## Historical retrieval evidence

The lifecycle test imports two immutable revisions of one Skill, promotes the second, then rolls current back to the first.

Verified:

- current name lookup resolves to the first revision after rollback;
- second revision remains retrievable by its exact immutable ref;
- the second revision is correctly projected as historical;
- instruction bytes for both revisions remain distinct and intact.

This preserves the S2 exact-ref re-fetch promise after lifecycle mutations.

## Discovery evidence

The enable/disable lifecycle test verifies:

1. current enabled Skill appears in normal discovery;
2. disable removes it from normal current-enabled list discovery;
3. exact immutable ref retrieval still succeeds while disabled;
4. enable restores normal discovery.

No discovery action selects a Skill on behalf of Sol.

## Authority audit

Source searches performed during S3 acceptance found:

- zero `skill_execute` implementation;
- zero `SkillRuntime` implementation;
- zero `.agents` automatic discovery under `soma/skills`;
- zero subprocess path under `soma/skills`.

The new `skill_action` source references are confined to:

- gateway request models;
- `soma.server` lifecycle dispatch;
- public gateway inventory;
- public human-facing metadata;
- CF1 operation inventory.

No semantic reasoning subsystem was added.

## Skill-layer focused acceptance

Initial focused run:

- run: `20260815T154005Z_executable_profile_1a9c946e`
- result: 52 passed, 1 failed
- failure classification: new S3 test expected the wrong accepted S2 binary response field (`content_encoding` instead of existing `encoding`)
- S2 source was not changed.

Corrected focused run:

- run: `20260815T154220Z_executable_profile_842acfc2`
- result: **53 passed**
- Ruff: PASS
- `git diff --check`: PASS

After adding explicit staging-failure evidence:

- run: `20260815T154806Z_executable_profile_ab23c68d`
- result: **54 passed**
- Ruff: PASS
- `git diff --check`: PASS

## Public-contract acceptance

Public seam run:

- run: `20260815T154417Z_executable_profile_552a66ab`
- result: **399 passed in 184.89s**
- Ruff: PASS
- `git diff --check`: PASS

This covered:

- S1 library;
- S2 query service/gateway;
- S3 action gateway;
- public descriptor identity;
- public gateway inventory;
- CF1 operation inventory;
- MCP discovery;
- flattened input contract;
- public metadata wiring;
- public tool metadata;
- gateway models.

## Final cross-authority seal

S3 reused the exact accepted S2 final cross-authority command and added the S3 lifecycle test, making the S3 seal a strict superset of the S2 seal surface.

Final run:

- run: `20260815T154844Z_executable_profile_e788a13f`
- result: **650 passed in 236.91s**
- Ruff: PASS
- `git diff --check`: PASS
- lease generation: 1
- launch attempts: 1
- no recovery
- no relaunch
- no cancellation
- no stale worker

The suite included:

- S1 portable Skill library;
- S2 progressive Skill query;
- S3 Skill lifecycle action;
- continuation persistence/service/gateway/schema coexistence;
- JobManager;
- RunStore and public Run projections;
- canonical Task plane;
- ProjectScope foundation;
- Hermes companion client;
- public gateway/inventory/metadata/descriptor/flat-input/model seams.

## Final public identity

Fresh identity re-check after the final source freeze:

- run: `20260815T155308Z_executable_profile_60a6cb2b`
- discovery converged: true
- gateway/tool count: **38**
- operation schema count: **286**
- public input schema hash: `5ef04e36efed1496ede40ffe3c51c8f8fe3de06255f0b9ecfda15905c4df8ebd`
- public descriptor hash: `e53780fa49bc31702e89601bd8f9b8db3844b15aeac5b77c0659a0e2171ebd60`
- operation inventory hash: `ffdcc0d5f7bb2d93316c3ce0b67de86b1d8f1dc35162316005b95a117417165b`

S3 moved topology exactly as intended from S2:

- gateways: 37 -> 38
- operations: 281 -> 286
- delta: +1 gateway, +5 operations

Exact `skill_action` operation hashes:

- `disable`: `45480000a0a2a9077e572949c264517454e66b3a4b332b95c6b77fe04d3c0927`
- `enable`: `3d9c07c69a71a237722311d936ca5ce54038ab6f817cf713eb6f102cbd5eac03`
- `import_revision`: `583c878c413d8bc64fac28317eb717bc3079f6876e7ea5e0ed9bed7c63e13551`
- `rollback`: `5177c3af068f13d08ad579a11811825bca2dbf63e8c26bc823a8e9843fa6af9a`
- `set_current`: `0538e99e06392fa656a0ec1ff66b9b34b8f3f1340f83e202437d226b34b4374c`

## Implementation commit contamination audit

Commit range:

- base: `a319d5f6ce06a4d8cfb7ccdf2071798add8704b1`
- head: `839e04615336252cb800afe57572faecb9cf1888`

Exact result:

- 14 files
- 707 insertions
- 15 deletions

Files:

1. `soma/cf1_gateway_operation_inventory.py`
2. `soma/gateway_models.py`
3. `soma/public_gateway_inventory.py`
4. `soma/public_tool_metadata.py`
5. `soma/server.py`
6. `tests/test_cf1_gateway_operation_inventory.py`
7. `tests/test_mcp_action_discovery.py`
8. `tests/test_mcp_flat_input_contract.py`
9. `tests/test_public_descriptor_identity.py`
10. `tests/test_public_gateway_inventory.py`
11. `tests/test_public_metadata_wiring.py`
12. `tests/test_public_tool_metadata.py`
13. `tests/test_skill_action_gateway.py`
14. `tests/test_skill_library.py`

No `docs/soma-improvement-research/*` file entered the implementation commit.

At implementation sealing, 24 unrelated improvement-research documents remained untracked and preserved.

## Live activation boundary

S3 acceptance did **not** perform:

- Soma service restart;
- connector refresh;
- connector repair;
- live Skill-library migration or import into the owner library;
- live `skill_action` mutation;
- push;
- Codex invocation;
- subagent invocation;
- second-model reasoning.

The running connector therefore remains whatever live build it had before this source-only gate. Source acceptance does not imply live activation.

## Programme state after S3

Mandatory gates accepted after this record:

- F0
- F1
- C1
- C2
- C3
- C4
- C5
- S1
- S2
- S3

That is **10 / 13 mandatory gates = 76.9%**.

Remaining mandatory sequence:

1. S4
2. I1
3. I2

No later gate is authorized by this acceptance record.

## Next boundary

The next sequential gate is **S4 only**.

S4 has not been started as part of S3 acceptance.
