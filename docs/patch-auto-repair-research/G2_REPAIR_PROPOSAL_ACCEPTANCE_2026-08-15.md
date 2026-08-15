# G2 Repair Proposal Acceptance - 2026-08-15

Status: ACCEPTED

Lane: Patch Auto-Repair
Gate: G2 - Deterministic Transport Repair Proposal
Branch: `lane/memory-integration-foundation-1`
Acceptance HEAD before this record: `182f6ce754258542c18c5771c2d72c927f511b5b`

## 1. Scope

This record accepts Gate 2 of the patch auto-repair implementation plan.

Accepted implementation commits:

- `a6551ee775b57a9d93062579de5d81d6a0b55213` - G2.1 authored-span provenance;
- `26eb9adf64d454c0b5056b21ae770590405226b4` - G2.2 exact versioned transport-leak detectors;
- `3c14b997e7f3d4dfff074695dc2509d7c38d5730` - G2.3 Python logical-line deletion proof;
- `af00e2b1a87dac37b690819d9ce50e4c38424514` - G2.4 durable repair proposal evidence;
- `fd3c78e3bf1acd6e7ac36ca9d4b3a5dc8fd83390` - G2.5 resolution-required source preview state;
- `182f6ce754258542c18c5771c2d72c927f511b5b` - Gate-2 new-file Ruff formatting cleanup.

Gate 2 does not implement controller resolution, `accept_repair`, `accept_original`, selected child preview creation, public `resolve_patch`, public schema changes, connector refresh, runtime activation, deployment, push, or model/LLM repair.

## 2. G2.1 authored-span provenance

Gate 2 adds `soma/repo_patch_repair.py` and conservative authored-span evidence.

Accepted direct repair primitives are only:

- `exact_text`;
- `line_range`;
- `python_ast`.

Internal compatibility aliases collapse to those three canonical primitive names and do not become separate repair policies.

For a single direct edit, `AuthoredSpanProvenanceV1` records only the minimal candidate byte interval that is certainly changed relative to the baseline. It includes the operation index, canonical primitive, byte start/end, and SHA-256 of the owned candidate span.

The ownership contract fails closed:

- multi-operation same-file composition is `ambiguous_composition`;
- unsupported primitives are `unsupported_primitive`;
- no actual changed candidate span is `no_changed_span`;
- non-owned dispositions carry no claimed byte range or span hash;
- suspicious transport-looking bytes that already existed in the baseline remain outside the owned changed span.

This provenance is attached after final candidate materialization and is persisted beside candidate validation in new v4 patch bundles.

## 3. G2.2 exact detector rules

The detector recognizes only the two recovered transport-corruption families:

- `repo_preview.patch.trailing_commit_title.v1`;
- `repo_preview.patch.trailing_view.v1`.

No generic JSON-looking or tool-call-looking heuristic is accepted.

The detector searches only inside an `owned` direct-edit span and returns exact deletion candidates with:

- rule identity/version;
- operation index and primitive;
- deletion byte start/end;
- deleted-byte SHA-256;
- bounded deleted excerpt.

Unreviewed outer-field lookalikes such as `commit_description`, `expected_sha256`, or case-variant field names do not match.

Multiple matching reviewed signatures remain multiple candidates. Gate 2 never chooses among them by confidence, ordering, or model judgment.

## 4. G2.3 Python logical-line proof

A detected byte suffix is not sufficient for a repair proposal. `PythonLogicalLineProofV1` requires all of the following:

1. the original candidate is invalid Python;
2. the proposed deletion bytes exactly match the detector coordinates/hash;
3. the deletion-only candidate compiles as Python;
4. no token spans the deletion cut;
5. bytes between the cut and next token are horizontal whitespace only;
6. the next Python token at the cut is logical `NEWLINE`, not continuation `NL`.

This is the key semantic boundary recovered from the two real incidents.

Incident B:

`assert ... == "ok"}],"view":"full`

After the exact transport suffix is removed, the cut lands at the completed assertion's logical `NEWLINE`; the proof passes.

Incident A:

`"WorkPackage"}],"commit_title":"G1.2 additive Company Kernel graph schema v2`

Deletion alone produces syntactically valid Python, but it would join adjacent string literals inside an open list. The tokenizer reports continuation `NL` at the cut, not logical `NEWLINE`; the proof rejects the repair.

The focused suite also rejects continuation/fusion hazards involving function calls, list/dict/tuple/set displays, comprehensions, operators, attribute/subscript expressions, explicit backslash continuations, comments/semicolons, and f-string/token boundaries.

Unicode, CRLF, EOF-without-newline, trailing horizontal whitespace, and a fixed-seed bounded adversarial corpus are covered.

## 5. G2.4 deterministic proposal and separate repair payload

`PatchRepairProposalV1` is a deletion-only proposal contract, not an apply decision.

A proposal can be built only when:

- baseline candidate validation is valid;
- final candidate validation is invalid;
- a validation regression is explicitly recorded;
- authored-span provenance is owned;
- exactly one reviewed transport detector candidate exists;
- the Python logical-line gate passes;
- exact deletion yields the repaired bytes/hash proved by the gate.

Proposal identity is deterministic from the rule/path/operation/primitive/original/repaired/span/deletion identities. `created_at` does not change the proposal ID.

A proposal records bounded provenance including:

- proposal/rule identity;
- original candidate SHA-256;
- repaired candidate SHA-256;
- owned replacement-span hash;
- exact deletion range and deleted-byte SHA-256;
- bounded deleted excerpt;
- Python validation before/after summary;
- logical-line proof;
- repaired payload descriptor and size/hash.

The malformed source payload is never rewritten by proposal construction.

For exactly one patch-level proposal, the source bundle retains its ordinary original `payload_*` bytes and stores repaired bytes separately as a hash/size-bound `repair_payload_<id>.bin` artifact. Proposal metadata cannot select those repaired bytes for application.

If more than one file/proposal is plausible, Gate 2 persists no selected patch-level proposal and creates no repair payload rather than guessing.

The integrity terminology remains deliberately limited: manifest and payload hashes establish managed-bundle internal consistency, not an external immutable trust anchor against coordinated storage rewrites.

## 6. G2.5 source preview applicability boundary

A baseline-valid Python modification that becomes candidate-invalid is now classified:

`preview_resolution_required`

Such a source preview is:

- `ok = false`;
- `applicable = false`;
- `resolution_required = true`;
- optionally repair-available when exactly one Gate-2 proposal exists.

The source preview preserves the malformed original payload and proposal evidence. Gate 2 does not select either original or repaired bytes.

Both fresh apply paths now use an applicability whitelist:

- idempotent `applied` replay remains supported;
- `reverted` remains rejected;
- legacy `preview_failed` remains rejected with its compatibility message;
- only `preview_ok` may begin a fresh apply;
- `preview_resolution_required` is rejected;
- unknown future/non-applicable statuses are rejected rather than falling through to writes.

This whitelist is enforced in both:

- `apply_repo_patch(...)` operation-revalidation path;
- `apply_previewed_repo_change(...)` opaque managed-bundle path.

Compatibility boundaries are preserved:

- ordinary valid Python preview remains `preview_ok` and applicable;
- baseline-invalid to candidate-invalid edits are not newly blocked because they are not validation regressions;
- deterministic `budget_skipped` validation is not newly blocked;
- v2/v3/v4 `preview_ok` bundle compatibility remains under the existing apply contract;
- preview itself does not mutate repository source;
- attempted apply of a resolution-required source does not mutate repository source.

## 7. Focused acceptance evidence

Final post-format Gate-2 acceptance run:

`20260815T052451Z_executable_profile_054411f1`

Covered:

- `tests/test_repo_candidate_validation.py`;
- `tests/test_repo_patch_repair.py`;
- `tests/test_repo_patch_repair_integration.py`;
- `tests/test_repo_writer.py`;
- Ruff lint over candidate-validation, repair, writer, and focused test modules;
- Ruff-format check over the five new/clean G1+G2 modules/tests;
- `git diff --check`.

Results:

- pytest: PASS - 184 passed;
- Ruff lint: PASS;
- Ruff-format for new/clean files: PASS - 5 files already formatted;
- `git diff --check`: PASS.

The final suite includes deterministic real-incident fixtures, detector negatives, ambiguity cases, Python structural hazards, fixed-seed fuzz/adversarial cases, bundle/proposal persistence, source-payload preservation, repair-payload identity, both apply-path negative proofs, valid compatibility, baseline-invalid compatibility, budget-skip compatibility, and unknown-status fail-closed behavior.

## 8. EOL and legacy formatter diagnostics

Diagnostic run:

`20260815T052422Z_executable_profile_cc344af0`

Current EOL counts reported:

- `soma/repo_writer.py`: 2206 CRLF, 152 LF, 0 bare CR;
- `tests/test_repo_writer.py`: 2557 CRLF, 98 LF, 0 bare CR;
- `soma/repo_patch_repair.py`: LF-only;
- `tests/test_repo_patch_repair.py`: LF-only;
- `tests/test_repo_patch_repair_integration.py`: LF-only.

The new Gate-2 files are Ruff-format clean at acceptance.

`repo_writer.py` and `tests/test_repo_writer.py` continue to report whole-file Ruff-format debt. That condition was already established and accepted as pre-existing in `G1_CANDIDATE_VALIDATION_ACCEPTANCE_2026-08-15.md`. Gate 2 deliberately did not normalize those large mixed-EOL legacy files; its changes there were narrow managed patch hunks validated by focused tests, Ruff lint, and `git diff --check`.

## 9. Public/runtime compatibility

A live capability check during G2.6 reported:

- public actions: 34;
- public operation-inventory gateways: 34;
- accepted public schema hash: `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`;
- runtime/live input schema hash remains the same accepted hash.

No public tool was added.

No public request schema was changed.

No connector refresh, service restart, runtime activation, deployment, push, provider call, or Codex/subagent use is part of G2.

## 10. Concurrent-work boundary

Concurrent research output under `docs/sol-agentic-loop-realignment-research/` and the pre-existing `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` are outside this lane.

New research files appearing there during Gate 2 were treated as expected concurrent work, preserved, and excluded from all Gate-2 implementation/formatting commits.

## 11. Gate verdict

G2 - Deterministic Transport Repair Proposal is ACCEPTED.

The repository now has:

- conservative authored-byte ownership;
- exactly two versioned recovered-incident detector rules;
- a Python logical-line structural proof that distinguishes safe Incident B from unsafe Incident A;
- at most one deterministic deletion-only repair proposal;
- separately preserved hash-bound repair payload evidence;
- immutable source-preview payload evidence in the proposal phase;
- a non-applicable `preview_resolution_required` source state;
- fresh-apply whitelisting that prevents the source preview from reaching writes.

No controller decision has been made and no repaired/original candidate can yet be selected through a resolution operation.

The next top-level implementation gate is G3 - Explicit Resolution and Deterministic Child Preview. Gate 2 completion does not itself activate G3.
