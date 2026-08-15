# P0.2 Patch Pipeline Drift Acceptance - 2026-08-15

Status: `ACCEPTED - IMPLEMENTATION SEAMS RECONCILED`

## Gate

This record closes P0.2 of the owner-activated patch auto-repair implementation lane.

Canonical plan:

`docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md`

Planning source point:

`4fd5c327b57350c02a958a2d0f52cb73d8cffb43`

Audit HEAD:

`9a362300d62f180cb249c495db8606915752b999`

P0.1 preservation commit:

`9a362300d62f180cb249c495db8606915752b999`

No production source, runtime configuration, provider route, service, connector, deployment, or external system was changed by this gate.

## Worktree boundary

At audit entry the tracked worktree was clean. The only remaining untracked file was:

`docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md`

That owner planning artifact remained untouched and excluded from this gate.

## Drift scope

The commit range from the planning source point to the audit HEAD contains 156 changed files, with 42,849 insertions and 737 deletions. Most of that change belongs to later Agent/Worker, provider, Company, public-routing, test, and documentation work.

The critical patch-engine file `soma/repo_writer.py` is absent from that changed-file set.

## Source identity reconciliation

| Surface | Planning identity / expectation | Current identity / state | Classification |
| --- | --- | --- | --- |
| `soma/repo_writer.py` | `dc686e4889028cc5a9f426d4b5fcd6e745b1d0ebdb6b4358bc6d6b9dededc319` | exact same SHA-256 | `compatible` |
| `soma/gateway_models.py` | `33ab828a585d1a00848eaa4bbefbda4398de3570f2e3bdf17c0f171aed9a634e` | `e3fe58650a56787606526838719da9bbd487b12c5030e71481c43516fc388563`; later Company/reasoning/SSH/public models added, repository preview/apply topology preserved | `compatible` |
| `soma/server.py` | `ee15e1729209beca0a63fcebed22daef40f6b67047c022af3e44ada2274bdbef` | `9aaa3e6b6e79fb47e498e88282f6735c5c089d0ef9086b4129e80aa4990a9f16`; later runtime/public wiring added, repository preview/apply/status delegation preserved | `compatible` |
| `soma/public_tool_metadata.py` | existing repository tool metadata | `4b6f98884617072baa14445c697c13afa624c5dd1bca8c790f8f57ae78409f91`; routing descriptions evolved, repository tool roles preserved | `compatible` |
| `soma/public_gateway_inventory.py` | repository gateways already public | `38bec45be360113f976ebfa4d0ce92d2b5911f4ea0bfe7cee101c2d2cff26452`; public surface is now 34 tools, repository gateway names unchanged | `compatible` |
| `soma/cf1_gateway_operation_inventory.py` | repository operation inventory present | `48155dd5d26fc0fdb3fd4e2ec070a6e9e18c310306e2a46c345184bd23e799e1`, inventory version `cf1.3.gateway-operations.v22`; repository operations remain compatible | `compatible` |
| repository writer / preview / apply / patch-status tests | focused coverage required | existing focused tests remain present for edit types, byte/newline preservation, patch status, schemas, server delegation, inventory, and discovery | `compatible` |
| later Agent/Worker, provider, Company, SSH and unrelated public-routing implementation | not an input to the repair design | broad additive work outside the patch materialization/apply seam | `unrelated` |

No audited difference is classified `requires-plan-adjustment` or `invalidates-research-assumption`.

The public surface increase that occurred elsewhere in Soma does not alter the plan's invariant. The auto-repair feature must preserve the **current** owner/executive public tool count of 34 and extend the existing `repo_preview` gateway rather than add a new top-level public tool.

## Re-proof 1 - complete candidate materialization still precedes bundle write

`_validate_operations()` remains the shared patch-validation/composition seam in `soma/repo_writer.py`.

For each first-seen target path it reads the current bytes, derives the current SHA-256, preserves the original content, and initializes the normalized/preserved working candidate. It then applies the requested semantic operation into the working candidate and returns one final validated per-file result.

`preview_repo_patch()` calls `_validate_operations()` first. For each validated file it places the final materialized candidate into the bundle input as:

```text
payload_text = op["new_content"]
```

Only after that full candidate exists does it call `_write_preview_bundle()`.

Verdict: **re-proven**.

## Re-proof 2 - preview bundle preserves exact selected payload bytes and hashes

`_write_preview_bundle()` still takes each complete `payload_text`, encodes it as UTF-8, and passes the bytes to `build_payload_parts()`.

The resulting payload bytes/chunks are written atomically into the managed patch directory. The manifest records the payload descriptor, including payload file/chunk identity, SHA-256, and byte size.

Current preview bundle version remains:

`3`

Verdict: **re-proven**.

## Re-proof 3 - repo_apply remains blind to semantic edit intent

`apply_previewed_repo_change()` currently accepts opaque managed bundle versions `{2, 3}`.

For modify/create actions it:

1. validates repository binding, HEAD/current-file identity, and path safety;
2. calls `assemble_payload()` over the stored bundle payload files;
3. verifies and obtains the selected `payload_bytes`;
4. prepares the atomic write from those bytes.

It does not replay `exact_text`, `line_range`, `unified_diff`, `python_ast`, or other original semantic edit instructions to reconstruct the file at apply time.

Verdict: **re-proven**. The G1/G2 design can continue to treat apply as a deterministic executor of already-selected candidate bytes.

## Re-proof 4 - bundle compatibility assumption remains valid

Preview currently emits bundle version 3. Apply accepts versions 2 and 3.

The implementation plan's intended additive bundle-v4 evolution remains valid: v4 can be added without redefining the historical v2/v3 apply contract, provided compatibility is explicitly retained and tested.

Verdict: **compatible**.

## Re-proof 5 - public repository request topology remains compatible

Current `RepoPreviewRequest` is still a discriminated union containing:

- `patch`;
- `create_file`;
- `remove_file`;
- `cleanup`.

Current `RepoApplyRequest` remains:

- `previewed_change`;
- `cleanup`;
- `revert`;
- `move_file`.

`server.repo_preview` delegates those preview operations to the existing repository writer authorities. `server.repo_apply` still launches the managed durable repository-apply path through `JobManager.start_repo_apply`.

There is currently no `resolve_patch` operation. Therefore G4 can still add that operation to the existing `repo_preview` union rather than introduce a new top-level public gateway.

Verdict: **re-proven**.

## Re-proof 6 - patch status remains recoverable by patch ID

`RepoPatchStatusQuery` remains available through `repo_query` with exact `repo_name` and `patch_id`.

`server.get_patch_status()` delegates directly to:

```text
_repo_writer.get_patch_status(repo_root, patch_id, _get_runs_dir())
```

Focused coverage remains in the server, gateway-model, CF1 inventory, and MCP discovery tests, including compact/full patch-status views.

Verdict: **re-proven**.

## Re-proof 7 - no competing candidate-validation or repair layer was introduced

Repository-wide source searches under `soma/` returned zero hits for:

- `resolve_patch`;
- `candidate_validation`;
- `repair_proposal`.

No later Agent/Worker or Company implementation introduced another candidate validator, repair proposal authority, or patch-resolution state machine.

Verdict: **re-proven**.

## Public contract baseline entering implementation

Current owner/executive public surface:

`34 tools`

Current accepted public schema hash:

`00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`

Current repository gateway roles remain:

- `repo_query` - repository/evidence inspection including patch status;
- `repo_preview` - durable hash-bound preview creation without repository mutation;
- `repo_apply` - managed preview application/revert/cleanup/move through durable execution;
- `repo_commit` - selected validated local Git commits.

Later public routing metadata changes are compatible with the repair plan. G4 must intentionally update public input-schema identity if `resolve_patch` is added, while retaining the 34-tool top-level inventory and following the existing runtime/connector schema-convergence discipline.

## Implementation consequences

P0.2 requires **no architecture rewrite** before G1.

The reconciled starting assumptions are:

1. G1 may use the existing `_validate_operations()` seam; `soma/repo_writer.py` itself is byte-identical to the planning baseline.
2. Candidate-language validation can be attached after final per-file candidate materialization without changing current semantic operation behavior.
3. Bundle v4 remains an additive evolution over historical v2/v3 compatibility.
4. `repo_apply` must remain repair-blind and execute only already-selected opaque payload bytes.
5. G4 must extend `repo_preview`; it must not create a 35th owner/executive tool.
6. Current public schema identity and connector-refresh discipline, not planning-time public counts, govern later activation.
7. No later Agent/Worker or Company source needs to be absorbed into the auto-repair design merely because it changed after the planning anchor.

## Gate verdict

`P0.2 ACCEPTED`

`PATCH ENGINE SEAM UNCHANGED`

`PUBLIC REPOSITORY TOPOLOGY COMPATIBLE`

`NO COMPETING REPAIR LAYER`

`NO RESEARCH ASSUMPTION INVALIDATED`

`NO PLAN RECONCILIATION REQUIRED BEFORE G1`

P0.2 ends here. G1 candidate-validation implementation is a separate next stage and is not started by this acceptance record.
