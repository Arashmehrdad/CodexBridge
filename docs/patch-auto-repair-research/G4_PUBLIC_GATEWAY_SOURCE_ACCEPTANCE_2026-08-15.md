# G4 Public Gateway Source Acceptance - 2026-08-15

Status: **ACCEPTED - SOURCE ONLY, NOT LIVE**

## Scope

Gate 4 extends the existing public `repo_preview` gateway with one new discriminated operation, `resolve_patch`, and extends bounded `patch_status` continuity. It does not add a public tool, does not add apply authority, and does not activate the source change in the running Soma service.

The accepted G3 deterministic resolution service remains the only implementation of source-to-child resolution. The public gateway is a thin repository-bound route into that service.

## Accepted source commits

- G4.1 request model: `8bcf0042b3f3f5067133576192c765d68c716c40` - `Add G4.1 public patch resolution request model`
- G4.2-G4.4 public source wiring: `9727fb299f840b7993cca113f24adbfbf59a7818` - `Wire G4 public patch resolution source`

Acceptance source HEAD before this evidence record: `9727fb299f840b7993cca113f24adbfbf59a7818`.

## Public request contract

`repo_preview(operation="resolve_patch")` now has a strict source-side request variant with:

- `repo_name`
- `source_patch_id` using the managed patch-ID shape
- `resolution_request_id`
- `decision`: `accept_repair` or `accept_original`
- `proposal_id`
- `view`
- `response_budget_bytes`

Cross-field rules are enforced at the public request model:

- `accept_repair` requires an exact `repair_[0-9a-f]{16}` proposal ID.
- `accept_original` forbids `proposal_id`.
- unknown fields remain forbidden.
- `RepoApplyRequest` is unchanged.

## Public routing and bounded evidence

`repo_preview(resolve_patch)` resolves repository identity and delegates to `soma.repo_patch_resolution_service.resolve_patch_preview`. It does not rerun repair detection or search and does not write repository content.

The compact preview projection can expose bounded scalar continuity including:

- `applicable`
- `candidate_validation_status`
- `resolution_required`
- `repair_available`
- `repair_proposal_id`
- `source_patch_id`
- `selected_child_patch_id`
- `decision`
- `resolution_request_id`
- `proposal_id`
- `idempotent_replay`

`repo_query(operation="patch_status")` now exposes bounded source/child continuity including:

- `bundle_version`
- `applicable`
- `resolution_required`
- `repair_available`
- `repair_proposal_id`
- `source_patch_id`
- `resolution_decision`
- `selected_child_patch_id`
- `candidate_validation_status`

No payload body is added to compact patch status.

## Public topology and metadata

The owner public topology remains exactly **34 tools**. No new public gateway was added.

Only the existing `repo_preview` purpose text was broadened to include explicit managed-patch resolution. Its Candidate-B annotations remain unchanged:

- `readOnlyHint = false`
- `destructiveHint = false`
- `idempotentHint = false`
- `openWorldHint = false`

The CF1 gateway operation inventory advances from `cf1.3.gateway-operations.v22` to `cf1.3.gateway-operations.v23` and adds only the `repo_preview.resolve_patch` operation entry.

## Source identity change

Accepted G3 baseline identities:

- public tool count: `34`
- operation schema count: `263`
- public schema hash: `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`
- public descriptor hash: `771b818449b3de0498a23ca987a606b9aeb08753ac9e27cf61a51460ad9cda0f`
- operation inventory hash: `7b61ecc4ef565357483c11168e55f3fa962e767a295a720453af7ca86f7f731f`

Accepted G4 source identities:

- public tool count: `34`
- operation schema count: `264`
- public schema hash: `ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42`
- public descriptor hash: `7acb65f1c6e3d4b85ea82296bd7d5cec281211c1b5bc00214d3b5b4860106273`
- operation inventory hash: `71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`
- `repo_preview.resolve_patch` operation schema hash: `2fdbe6ae4bb313cc6a406f66b0db46140ee0979fe04a2035a37de14b697a0213`

The four pre-existing `repo_preview` branch identities remain unchanged:

- `repo_preview.patch`: `4d89611108387f06cfa7e883e929ef9e9f3a186c041422e80b4865d81be9889f`
- `repo_preview.create_file`: `e39e14c7fd0c453537c179ae7033865cfefbd24cb0aef65d485af26a3abcc0c4`
- `repo_preview.remove_file`: `d66e7e06c85d450d7f98eb902b1d912c22cc453fa64285d0306994730e57c86d`
- `repo_preview.cleanup`: `dcf96554c7b64de9f32ceb71abfc19961ee9ac2fcc2265b3bdecc2cc446b343f`

A fresh-process comparison of the accepted G3 commit against G4 source proved:

- old operation count: `263`
- new operation count: `264`
- added operations: exactly `repo_preview.resolve_patch`
- removed operations: none
- changed existing operation schema hashes: none
- both discovery passes stable

Evidence run: `20260815T075811Z_executable_profile_748e4d93` - `G4_IDENTITY_ISOLATION_OK`.

## Validation evidence

### Full G4 public/source regression

Run: `20260815T075302Z_executable_profile_7c4d282d`

Result:

- **410 passed**
- Ruff check: passed
- `git diff --check`: passed

Coverage includes public gateway models, CF1 operation inventory, flat MCP input contract, action discovery, Candidate-B public metadata, capability identity tests, public descriptor identity, G4 focused resolution gateway tests, and G1-G3 resolution/repair compatibility suites.

### Direct repo-writer compatibility

Run: `20260815T075837Z_executable_profile_1cad4655`

Result:

- **127 passed**
- Ruff check: passed
- `git diff --check`: passed

This directly re-proves existing repo-writer and candidate-validation behavior after the G4 source projection/status additions.

### Fresh source identity

Run: `20260815T075643Z_executable_profile_7212cb69`

Result:

- public tool count: `34`
- operation schema count: `264`
- two-pass discovery stable
- exact G4 source hashes recorded above

## Runtime remains intentionally old

G4 is a source-acceptance gate, not activation.

The running Soma process was **not restarted** and the connector was **not refreshed**. The live runtime therefore intentionally still advertises the accepted pre-G4 public schema:

`00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`

The live baseline also still reports:

- public descriptor hash: `771b818449b3de0498a23ca987a606b9aeb08753ac9e27cf61a51460ad9cda0f`
- operation inventory hash: `7b61ecc4ef565357483c11168e55f3fa962e767a295a720453af7ca86f7f731f`
- operation schema count: `263`

`system_query(capability_identity)` correctly reports source/running build divergence and `restart_required = true`; this divergence is expected at the G4 source-only endpoint and is not repaired here.

## Explicit non-actions

Gate 4 did **not**:

- add a 35th public tool;
- change `RepoApplyRequest`;
- add repair behavior to `repo_apply`;
- restart Soma;
- refresh the ChatGPT connector;
- perform live `resolve_patch` smoke traffic;
- push or deploy;
- use Codex or provider subagents;
- modify concurrent Sol agentic-loop research or canonical-memory draft files.

## Gate verdict

**G4 PUBLIC GATEWAY SOURCE ACCEPTED.**

The source tree now contains the reviewed 34-tool `repo_preview(resolve_patch)` contract and bounded patch-status continuity. The running service intentionally remains on the pre-G4 public contract. Runtime/connector activation is deferred to the separately authorized activation stage defined by the Patch Auto-Repair plan.

**STOP at the top-level G4 boundary.**
