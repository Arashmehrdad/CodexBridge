# G5 Apply/Revert Compatibility Acceptance - 2026-08-15

Status: **ACCEPTED**

Gate: **G5 - Apply/revert compatibility hardening**

Authoritative implementation plan:

`docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md`

G4 source-acceptance baseline:

`6507206f32cf8b578431c132baf9a152d60d3bf0` - `Accept G4 public gateway source`

G5 proof commit:

`68d310cfce099e5ddda7b9d9c714ea70af582228` - `Prove G5 apply and revert compatibility`

## 1. Scope

G5 exists to prove that candidate validation, deterministic repair proposals, explicit source resolution, and selected child previews did **not** leak semantic intelligence into repository apply authority.

No production source was changed in G5.

The complete tracked G5 delta from the accepted G4 baseline is exactly:

```text
A  tests/test_repo_apply_compatibility_g5.py
```

`git diff --stat 6507206f..68d310cf` reports one file added and no production changes.

Concurrent untracked Sol-loop research and `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` were preserved and excluded from every G5 commit.

## 2. G5.1 - Repair-blind apply proof

### Dynamic authority-separation proof

`test_g5_1_apply_selected_child_is_parser_and_repair_blind` creates a real G2 repair proposal, resolves it through the accepted G3 service, then makes all of the following fail immediately if called during apply:

```text
repo_writer.build_patch_repair_proposal
repo_writer.derive_authored_span_provenance
repo_writer.validate_python_candidate
builtins.compile
ast.parse
tokenize.tokenize
tokenize.generate_tokens
```

`apply_previewed_repo_change()` still succeeds and consumes the already-selected child payload.

Therefore apply does not:

- run the repair detector;
- derive authored-span provenance;
- validate or compile Python;
- tokenize source;
- search for a repair;
- select between source and repaired candidates.

`test_g5_1_apply_uses_child_payload_not_resolution_decision_metadata` additionally proves resolution metadata is provenance, not a second payload-selection control plane. Even when the child resolution decision metadata is deliberately altered after child creation, apply writes the hash-bound child payload and does not reinterpret the decision to select different bytes.

### Static source proof

Durable run:

`20260815T081956Z_executable_profile_b34d23ed`

The AST/source audit of `apply_previewed_repo_change()` returned:

```json
{
  "forbidden_hits": [],
  "has_assemble_payload": true,
  "has_git_head": true,
  "has_hashlib": true,
  "has_repo_fingerprint": true,
  "has_resolve_path": true,
  "has_rollback": true
}
```

This directly confirms that the function contains the expected opaque payload/safety machinery and no repair/parser authority.

### Selected-child safety proof

Dedicated G5 tests prove a selected child still rechecks:

- repository fingerprint;
- current file hash;
- lexical path safety;
- opaque payload hash;
- recomputed changed-line limits;
- Git HEAD when the preview is HEAD-bound.

The selected child receives no privileged bypass merely because it originated from an explicit resolution.

## 3. G5.2 - Legacy bundle compatibility

Historical bundle formats were reconstructed from the actual repository history rather than approximated from the current v4 writer.

### Historical v2

Source commit:

`44f0312` - `feat: add opaque preview-backed repository changes`

The actual v2 writer emitted:

```text
bundle_version = 2
payload_file
payload_sha256
```

with no chunk list or payload-size field.

The G5 fixture writes that historical manifest/payload shape to disk and proves:

- `preview_ok` applies successfully;
- exact payload bytes are written;
- `preview_failed` is rejected before mutation.

### Historical v3

Source commit:

`b40d75d` - `feat: complete durable repository workflow hardening`

The actual v3 writer added:

```text
payload_chunks
payload_size_bytes
```

while preserving the payload hash descriptor.

The G5 fixture writes the actual v3 shape and proves:

- `preview_ok` applies successfully;
- `preview_failed` is rejected;
- v3 descriptor semantics remain readable by the current apply engine.

### v4 lifecycle and future-version behavior

G5 explicitly proves:

- `preview_resolution_required` source bundles are rejected by apply;
- `resolved` source bundles are rejected by apply;
- a resolution-pending/non-final source state is rejected by apply;
- a selected v4 child in `preview_ok` is applicable;
- unsupported future bundle version `999` fails closed.

Current accepted apply versions remain exactly:

```text
2
3
4
```

## 4. G5.3 - Revert and rollback

The dedicated G5 suite resolves and exercises both explicit decisions:

```text
accept_repair
accept_original
```

For both decisions it proves:

1. the selected child applies through ordinary `apply_previewed_repo_change()`;
2. the selected child reverts through ordinary `revert_managed_patch()`;
3. exact baseline bytes are restored;
4. the child retains its complete `resolution` provenance after revert;
5. the source remains `resolved` and still points at the same child/decision;
6. the source itself is not revertable because it was never an applied change.

### Partial-write rollback

`test_g5_3_selected_child_partial_write_failure_rolls_back_exact_bytes` uses a two-file selected child and injects a failure on the second `.soma_apply_tmp` write.

The first file has already crossed the apply boundary when the second write fails.

The test proves:

- apply raises the existing partial-rollback failure;
- first-file bytes are restored exactly;
- second-file bytes remain exactly at baseline;
- child lifecycle records failure rather than pretending success;
- source resolution provenance remains durable and unchanged.

This confirms the selected child uses the incumbent rollback engine rather than a repair-specific write path.

## 5. Validation evidence

### Dedicated G5 suite

Initial functional run:

`20260815T081631Z_executable_profile_8ddd9993`

Result before mechanical formatting:

```text
16 passed
Ruff check passed
Ruff format requested only mechanical formatting of the new G5 test file
```

The formatter-only diff was applied through managed repo preview/apply; no production file was formatted or changed.

### Full G1-G5 repository-write compatibility slice

Final environment-correct run:

`20260815T081901Z_executable_profile_4042cf01`

Environment:

```text
PYTHONPATH=D:\Github\TradingLab\src
```

Result:

```text
220 passed in 32.95s
All checks passed
5 files already formatted
git diff --check passed
```

Covered together:

```text
tests/test_repo_apply_compatibility_g5.py
tests/test_repo_patch_resolution.py
tests/test_repo_patch_resolution_service.py
tests/test_repo_patch_repair.py
tests/test_repo_patch_repair_integration.py
tests/test_repo_candidate_validation.py
tests/test_repo_writer.py
```

An earlier run, `20260815T081749Z_executable_profile_3467b494`, reached the final four server-import tests and failed only because that shell did not include the standalone Trading Lab package on `PYTHONPATH`. The four failures were `ModuleNotFoundError: trading_lab`; no G5 assertion failed. The exact same suite passed after supplying the repository's established Trading Lab import root.

## 6. Public-contract non-change

G5 changes no public request model, gateway, operation inventory, tool metadata, or production implementation.

Fresh-process source identity at G5 proof commit:

Run:

`20260815T082101Z_executable_profile_32bc5aed`

```text
tool_count = 34
operation_count = 264
public_schema_hash = ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42
public_descriptor_hash = 7acb65f1c6e3d4b85ea82296bd7d5cec281211c1b5bc00214d3b5b4860106273
operation_inventory_hash = 71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588
stable = true
```

These are exactly the accepted G4 source identities.

The running MCP service remains intentionally pre-G4 because G4/G5 source acceptance does not authorize activation. Live runtime still advertises the prior 34-tool / 263-operation contract and public schema:

`00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`

No Soma restart, connector refresh, push, deployment, Codex invocation, or provider subagent was performed in G5.

## 7. Gate verdict

**G5 ACCEPTED.**

Authority separation is proven:

```text
preview / validation / repair / resolution
              |
              v
       selected preview_ok child
              |
              v
       opaque repo_apply engine
              |
              v
       ordinary rollback/revert
```

`repo_apply` remains a deterministic executor of already-selected, hash-bound bundle bytes. It has no authority to reason about source language, detect corruption, synthesize repairs, choose candidates, or reinterpret resolution intent.

Endpoint reached: **apply/revert authority separation accepted; STOP at top-level G5.**
