# G3 Resolution Preview Acceptance - 2026-08-15

Status: **ACCEPTED**

Authoritative plan:
`docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md`

Accepted source HEAD before this evidence record:
`66ca893c9d4579c2e55b235b5ad3d6567fd381d0`

Public activation remains deferred to G4. This gate accepts the internal resolution semantics only.

## Scope accepted

G3 implements explicit controller resolution of a `preview_resolution_required` v4 source preview into one deterministic managed child preview.

The accepted flow is:

```text
source v4 preview
  -> preview_resolution_required
  -> explicit controller decision
       accept_repair | accept_original
  -> deterministic child patch identity
  -> child preview_ok only after incumbent repository safety checks
  -> ordinary repo_apply / revert lifecycle on child only
```

The source preview is never rewritten into the child payload and never becomes applicable.

## Commit chain

- `6525a078729de66b41e3b62ea095f5e4547b2c4c` - Add G3.1 deterministic patch resolution identity
- `2d52af21ad1000d7628a00cbcffa0acefc6a3c62` - Implement G3 explicit patch resolution children
- `a58c1260082f1d2381a72e4c02ad1d67eca3573e` - Complete G3.4 durable resolution recovery
- `3f791c41223c66cd1d050cecede4675ed89c23c1` - Complete G3 resolution negative proofs
- `66ca893c9d4579c2e55b235b5ad3d6567fd381d0` - Format G3 resolution implementation

## G3.1 - Deterministic internal resolution identity

Accepted:

- `PatchResolutionRequestV1` with bounded request identity;
- exact `accept_repair` / `accept_original` decision validation;
- source-manifest identity hash bound to immutable source material rather than mutable lifecycle state;
- deterministic resolution-request hash;
- deterministic child patch ID preserving the existing managed patch ID shape;
- exact replay convergence;
- request-ID/content conflict rejection;
- deterministic child collision rejection;
- wrong repository, unknown source, stale source, non-resolution-required source, and conflicting already-resolved requests fail closed.

Focused G3.1 validation:

- run `20260815T063616Z_executable_profile_39ac7d20`
- 7 passed
- Ruff passed
- `git diff --check` passed

## G3.2 - accept_repair

Accepted:

- resolution selects only the exact proposal payload already preserved in the source v4 bundle;
- repair detection/search is not rerun during resolution;
- proposal ID and repaired payload descriptor/hash/size are reverified;
- original malformed source payload remains preserved in the source preview;
- child carries source patch ID, proposal ID, resolution request ID/hash, source-manifest identity hash, selected payload hashes, commit metadata, and source proposal evidence;
- child becomes `preview_ok` only after the ordinary current repository preconditions pass.

Instrumentation proves resolution does not call `build_patch_repair_proposal` or reopen the detector/search path.

## G3.3 - accept_original

Accepted:

- exact source payload bytes are selected;
- child records `candidate_validation_override = accept_original`;
- the override bypasses only the candidate-language regression gate;
- repository binding, Git HEAD requirements, current file hash, path safety, payload integrity, operation structure, binary/symlink restrictions, file count, line count, and changed-byte limits remain enforced;
- failed/stale/invalid resolution requests do not durably claim or poison the source preview.

During this gate an incumbent write-path safety gap was found: resolving the path before checking `Path.is_symlink()` could hide an in-repository symlink behind its resolved target. The repository write seam was strengthened to reject the caller's lexical symlink path before returning the resolved write target. This applies to existing repository write paths as well as resolution.

Core G3.2/G3.3 validation after that correction:

- run `20260815T064055Z_executable_profile_481948a1`
- 18 passed
- Ruff passed
- `git diff --check` passed

## G3.4 - Durable source/child lifecycle and recovery

Accepted:

- unresolved source exposes resolution-required status, repair availability, proposal ID, and resolution choices;
- resolved source exposes selected child, decision, request identity, and remains non-applicable;
- child exposes source linkage, decision, proposal identity where applicable, and its own independent apply/revert lifecycle;
- applying or reverting the child does not alter the source lifecycle from `resolved`;
- fresh-process recovery reconstructs source/child linkage using managed patch files only, without relying on chat/process memory;
- exact replay after recovery converges on the same deterministic child.

Compatibility validation with the existing repo-writer/server surfaces used the actual Trading Lab import root:

- run `20260815T064408Z_executable_profile_df92fee3`
- 186 passed
- Ruff passed
- `git diff --check` passed

## Required negative proofs

Explicit tests prove rejection of:

- wrong proposal ID;
- `accept_repair` when no proposal exists;
- `accept_original` carrying repair-only semantics through the wrong decision shape;
- same resolution request ID replayed with changed decision/material;
- unknown source patch;
- wrong repository;
- non-resolution-required source;
- stale current file hash;
- changed Git HEAD when the source preview requires matching HEAD;
- path escape;
- malformed/unsupported operation;
- tampered source payload;
- changed-byte limit overflow;
- file-count limit overflow;
- binary target;
- symlink target;
- deterministic child collision with differing content;
- direct apply of the resolution-required source;
- direct apply of the resolved source.

Final negative matrix:

- run `20260815T064554Z_executable_profile_b91e5e05`
- 13 passed
- Ruff passed
- `git diff --check` passed

The Python f-string structural-hazard regression test was also made tokenizer-version-neutral: both `token_spans_deletion_cut` and `next_token_not_logical_newline` are accepted rejection evidence. The safety invariant is rejection; the tokenizer's exact diagnostic category is not a portable contract.

## Gate 3 final acceptance run

After Ruff mechanical formatting of only the new clean G3 files:

- run `20260815T073338Z_executable_profile_53754699`
- **204 passed**
- Ruff lint: pass
- Ruff format: **7 files already formatted**
- `git diff --check`: pass

No legacy mixed-EOL repo-writer formatting sweep was performed.

## Public boundary / activation state

G3 remains internal-only as required by the plan.

Search of:

- `soma/gateway_models.py`
- `soma/server.py`
- `soma/public_gateway_inventory.py`
- `soma/cf1_gateway_operation_inventory.py`

found **zero** `resolve_patch` public wiring hits.

Capability identity at acceptance reports:

- operation inventory gateway count: **34**
- public schema hash: `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`
- public descriptor hash: `771b818449b3de0498a23ca987a606b9aeb08753ac9e27cf61a51460ad9cda0f`
- operation inventory hash: `7b61ecc4ef565357483c11168e55f3fa962e767a295a720453af7ca86f7f731f`
- connector refresh required: false
- operation-contract repair required: false

The source build hash differs from the currently running build hash because G3 changed internal source after the service was started. `capability_identity` therefore recommends a restart. That restart is intentionally **not** performed at G3: the public schema is unchanged, `resolve_patch` is not public yet, and source activation belongs to the later activation/public integration sequence rather than this internal semantics gate.

## Authority and compatibility conclusions

Accepted invariants:

1. Repair remains deterministic and model-free.
2. `accept_repair` selects preserved bytes only; it does not search again.
3. `accept_original` is an explicit controller override of candidate-language validation only.
4. Source resolution-required/resolved previews are permanently non-applicable.
5. Only the selected child can enter ordinary apply/revert lifecycle.
6. `repo_apply` remains repair-blind.
7. Source and child identities/lifecycle are durable across reconnect/restart.
8. Existing v2/v3/v4 apply compatibility remains intact.
9. Public tool topology and public schema remain unchanged at this gate.
10. No G4 public wiring, connector refresh, push, deploy, Codex use, provider subagent use, or Company-lane work occurred.

## Concurrent work preservation

Concurrent untracked canonical-memory and Sol agentic-loop research files under `/docs` were treated as separate owner work and were not modified, staged, deleted, renamed, or included in G3 commits.

## Gate result

**G3 - Explicit Resolution and Deterministic Child Preview: ACCEPTED.**

Next top-level gate is G4, which may wire `repo_preview(operation="resolve_patch")` publicly and therefore intentionally changes the repo-preview public input schema/identity. G4 has not started in this acceptance record.
