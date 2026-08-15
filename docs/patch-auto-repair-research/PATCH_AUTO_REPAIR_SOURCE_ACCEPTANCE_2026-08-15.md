# Patch Auto-Repair Source Acceptance - 2026-08-15

Status: **SOURCE ACCEPTED, NOT LIVE ACTIVATED**

## Scope

This record closes Gate 8 of:

- `docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md`
- plan SHA-256: `197e69d5f546744332de39549831f497a67495183e3df23aea6fb4f217b6e21a`

G8 is a source-release acceptance gate only. It does not authorize A1 live activation, a Soma restart/reload for Patch Auto-Repair, connector Refresh, live `resolve_patch` use, push, deployment, or any other production action.

The source HEAD entering this final G8 closure was:

- `7a144e6440474d5e38e6bacdf28a2492b20a80fc` - `Harden Soma Cloudflare tunnel lifecycle`

That post-G7 tunnel commit is a separate emergency reliability change containing only:

- `scripts/manage_soma_service.ps1`
- `scripts/start_soma_mcp.ps1`
- `tests/test_service_manager_script.py`

It is not part of the Patch Auto-Repair source lane.

## Accepted predecessor gates

The Patch Auto-Repair source lane reached G8 with G1-G7 already accepted.

Final predecessor commits include:

- G1 acceptance: `fef45702367ecf1015a1ab95139547f172ab588f`
- G2 acceptance: `fb57bac7545b5c4eb14b05d919bb557bb6c5eaa2`
- G3 acceptance: `e7a17a1be0b1e14d1ae03ae105157a6e0a74d206`
- G4 source acceptance: `6507206f32cf8b578431c132baf9a152d60d3bf0`
- G5 compatibility acceptance: `234dcaaf7f8fab91eea1deac0cdd62a0ea9e84e6`
- G6 format validation acceptance: `bb551744824fd7abbac02441f901b543bac33d7f`
- G7 implementation: `8afead07fd1a390ba2daac621bceccce9707fa7e`
- G7 acceptance: `3a078706c5dd86cab8576ba5e8c0e5feb4082b1c`

## G8.1 - Final focused release sweep

Final current-HEAD release run:

- run: `20260815T103013Z_executable_profile_b36daa01`
- status: completed
- exit code: `0`
- duration: `526.532 s`
- pytest: **599 passed in 508.03 s**
- Ruff check: passed
- `git diff --check`: passed
- terminal marker: `G8_FOCUSED_RELEASE_SWEEP_OK`

The sweep covered the complete focused Patch Auto-Repair validator, repair, resolution, apply/revert compatibility, evidence, repo-writer, public-gateway, schema, descriptor, inventory, discovery, and capability surface:

- `tests/test_repo_candidate_validation.py`
- `tests/test_repo_candidate_validation_json_g6.py`
- `tests/test_repo_patch_repair.py`
- `tests/test_repo_patch_repair_integration.py`
- `tests/test_repo_patch_resolution.py`
- `tests/test_repo_patch_resolution_service.py`
- `tests/test_repo_apply_compatibility_g5.py`
- `tests/test_repo_patch_evidence_g7.py`
- `tests/test_repo_writer.py`
- `tests/test_repo_patch_resolution_public_gateway.py`
- `tests/test_tool_gateway_models.py`
- `tests/test_cf1_gateway_operation_inventory.py`
- `tests/test_mcp_flat_input_contract.py`
- `tests/test_mcp_action_discovery.py`
- `tests/test_public_tool_metadata.py`
- `tests/test_capabilities.py`
- `tests/test_public_descriptor_identity.py`

This independently reproduces the earlier pre-tunnel G8 sweep:

- run: `20260815T090503Z_executable_profile_38e868b6`
- result: **599 passed in 201.61 s**
- `git diff --check`: passed

The slower final run showed no functional regression; it reached the same passing test count and exit-zero release marker.

## G8.2 - Fixed real-incident corpus and deterministic adversarial proof

The final G8 sweep includes `tests/test_repo_patch_repair.py`, whose accepted G2 corpus contains the two frozen real transport-leak incidents plus fixed-seed bounded adversarial/fuzz coverage.

The G2 acceptance record remains:

- `docs/patch-auto-repair-research/G2_REPAIR_PROPOSAL_ACCEPTANCE_2026-08-15.md`
- accepted G2 validation run: `20260815T052451Z_executable_profile_054411f1`
- result: **184 passed**

The corpus proves both sides of the Tier-A boundary:

- the known safe logical-newline suffix corruption is proposed only when bounded tokenizer proof succeeds;
- the known unsafe continuation-context corruption is rejected;
- fixed-seed adversarial cases reject function-call, container, comprehension, operator, attribute, subscript, backslash, comment, semicolon, f-string, Unicode, CRLF, and EOF hazards covered by the frozen suite.

No G8 change expanded the detector rule set or weakened the explicit-resolution invariant.

## G8.3 - Public schema, descriptor, and inventory identity

The final G8 suite reran the focused public identity tests and passed them as part of the 599-test release sweep.

Accepted source identities remain the G4 identities carried unchanged through G7:

- public tool count: `34`
- operation schema count: `264`
- public schema hash: `ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42`
- public descriptor hash: `7acb65f1c6e3d4b85ea82296bd7d5cec281211c1b5bc00214d3b5b4860106273`
- operation inventory hash: `71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`
- `repo_preview.resolve_patch` schema hash: `2fdbe6ae4bb313cc6a406f66b0db46140ee0979fe04a2035a37de14b697a0213`

G5-G7 did not introduce another public gateway branch, and the separate tunnel commit changes no public gateway/schema source.

## G8.4 - Runtime remains intentionally pre-activation

A live `system_query(capability_identity)` check during G8 returned the expected source/runtime divergence rather than false convergence:

- running operation schema count: `263`
- running public schema hash: `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`
- running public descriptor hash: `771b818449b3de0498a23ca987a606b9aeb08753ac9e27cf61a51460ad9cda0f`
- running operation inventory hash: `7b61ecc4ef565357483c11168e55f3fa962e767a295a720453af7ca86f7f731f`
- `restart_required = true`
- mismatch: `source_running_server_build_hash`

This is not a G8 failure. It is the required proof that source acceptance has not silently performed A1. No restart/reload or connector Refresh was performed by G8.

## G8.5 - Toolchain and format checks

The repository `pyproject.toml` declares the dev toolchain as:

- `pytest`
- `ruff`

It does not configure mypy, pyright, or another dedicated type checker. G8 therefore did not invent a new type-check gate outside the repository's declared validation toolchain.

Ruff lint over the touched Patch Auto-Repair source/test surface passed in the final release sweep.

A separate format/newline diagnostic ran as:

- `20260815T104033Z_executable_profile_fee998ea`
- status: completed
- exit code: `0`
- terminal marker: `G8_EOL_FORMAT_DIAGNOSTIC_OK`

All 14 newly introduced Patch Auto-Repair Python source/test files checked by the clean-file formatter set are Ruff-formatted.

Whole-file `ruff format --check` over all 22 touched source/test files reports exactly three legacy whole-file formatter debts:

- `soma/repo_writer.py`
- `soma/server.py`
- `tests/test_repo_writer.py`

G8 independently proved those warnings predate the Patch Auto-Repair edits:

- baseline probe run: `20260815T104110Z_executable_profile_1d826491`
- pre-Patch-Auto-Repair `soma/repo_writer.py`: formatter exit `1`
- pre-Patch-Auto-Repair `tests/test_repo_writer.py`: formatter exit `1`
- pre-G4 `soma/server.py`: formatter exit `1`

No whole-file formatting rewrite is included in this lane.

The first newline-probe attempt, `20260815T104007Z_executable_profile_c636d5e4`, failed before repository interaction because the diagnostic harness used a backslash inside a Python f-string expression. It changed no files. The corrected probe above is the accepted evidence.

## G8.6 - Newline diagnostics

The corrected diagnostic inspected all 22 touched source/test files. Every file ends with a newline and no file contains bare-CR line endings.

New Patch Auto-Repair implementation/test files are LF-only.

Existing repository files preserve their established line-ending policy rather than being normalized opportunistically. Notable existing-file diagnostics:

- `soma/repo_writer.py`: `2303 CRLF`, `152 LF`, `0 bare CR`
- `tests/test_repo_writer.py`: `2557 CRLF`, `98 LF`, `0 bare CR`
- `soma/gateway_models.py`: `3028 CRLF`, `0 LF-only`
- `soma/server.py`: `7109 CRLF`, `0 LF-only`
- `soma/cf1_gateway_operation_inventory.py`: `1740 CRLF`, `0 LF-only`
- `tests/test_cf1_gateway_operation_inventory.py`: `532 CRLF`, `0 LF-only`

The mixed newline state in the two repo-writer legacy files was already documented before this release lane and is not normalized by G8.

## G8.7 - Exact commit-range and contamination audit

The repository history contains a separate Company route-neutrality correction interleaved between G2 and G3. G8 therefore does **not** misrepresent the entire chronological P0-G7 window as one pure feature range.

The Patch Auto-Repair lane was independently inspected as two exact contiguous source ranges around that unrelated work.

### Range A - P0 through G2

- base: `168656b50c33d5945cf1f33655e9065dfd783549`
- head: `fb57bac7545b5c4eb14b05d919bb557bb6c5eaa2`
- changed paths: `15`
- result: only Patch Auto-Repair research/acceptance docs, candidate validation, repair, repo-writer integration, and dedicated tests

### Interleaved work - explicitly excluded

The following Company commits are outside Patch Auto-Repair:

- `a9fe3ae32f5b26a8b8a7e0764431df2f8f62cda2` - `Correct Company WorkPackage route neutrality`
- `b03065cfa51c2d43cf6d9d67c178e1038b2b8e2e` - `Remove leaked reasoning names from Company proofs`
- `43b5a0829f8b05aa353b1d8ce82bd152e52fb2e9` - `Record Company route neutrality correction`

### Range B - G3 through G7

- base: `43b5a0829f8b05aa353b1d8ce82bd152e52fb2e9`
- head: `3a078706c5dd86cab8576ba5e8c0e5feb4082b1c`
- changed paths: `23`
- result: only Patch Auto-Repair resolution, public gateway, compatibility, format validation, evidence/telemetry source, dedicated tests, and acceptance docs

Neither accepted Patch Auto-Repair range contains:

- Agent/Worker source or tests;
- Company source or tests;
- canonical-memory source or docs;
- Sol continuation/skill-layer research;
- Cloudflare tunnel lifecycle files.

The post-G7 tunnel commit `7a144e6440474d5e38e6bacdf28a2492b20a80fc` was separately inspected and contains only its three tunnel/service files listed above.

## G8.8 - Concurrent untracked work preserved

The worktree contains unrelated untracked canonical-memory and Sol continuation/skill-layer research documents from concurrent work.

G8 did not edit, stage, delete, normalize, or include those files. The final G8 commit must select only this acceptance record.

## Final verdict

**SOURCE ACCEPTED, NOT LIVE ACTIVATED**

Patch Auto-Repair G8 is complete at the source layer.

All required focused release tests pass; the fixed real-incident and deterministic adversarial corpus remains covered; public identity checks pass; lint and diff integrity pass; newline diagnostics are recorded; legacy formatter debt is proven pre-existing rather than normalized; and the accepted source ranges are clean of Agent/Worker, Company, canonical-memory, Sol research, and tunnel-lifecycle contamination.

No push is authorized or performed.

No A1 action is authorized or performed.

Endpoint: create one local selected-file commit containing this G8 acceptance record, then STOP.
