# G1 Candidate Validation Acceptance - 2026-08-15

Status: ACCEPTED

Lane: Patch Auto-Repair
Gate: G1 - Candidate Validation Foundation
Branch: `lane/memory-integration-foundation-1`
Acceptance HEAD before this record: `938f1764dcab30a8bd8235ea2c822ba6d8c0826c`

## 1. Scope

This record accepts only Gate 1 of the patch auto-repair implementation plan.

Accepted implementation commits:

- `f5c5b4b5fe16c2128d636fcde5926176c18a47ce` - G1.1 pure bounded candidate validation;
- `79632dc9dcd7cbe055570163183a3556677de309` - G1.2 final composed-candidate integration;
- `938f1764dcab30a8bd8235ea2c822ba6d8c0826c` - G1.3 managed preview bundle v4 validation metadata.

Gate 1 does not implement transport-corruption detection, repair synthesis, resolution, applicability changes, public request-schema changes, connector refresh, runtime activation, deployment, push, or provider/model repair.

## 2. Accepted candidate-validation contract

The implementation adds `soma/repo_candidate_validation.py` with a pure bounded Python candidate validator.

The accepted v1 contract includes:

- immutable `CandidateValidationV1` evidence;
- bounded `CandidateDiagnosticV1` diagnostics;
- shared per-preview `CandidateValidationBudget` accounting;
- Python validation through `compile(..., "exec")` without import or execution;
- baseline-valid to candidate-invalid regression detection;
- deterministic `budget_skipped` evidence when validation budgets cannot admit a candidate;
- candidate SHA-256 and candidate byte-size identity;
- explicit validator/runtime identity;
- bounded syntax-error messages and locations where available.

Accepted validation budgets are:

- maximum candidate file bytes: 512 KiB;
- maximum total candidate bytes per preview: 2 MiB;
- maximum validated files per preview: 20;
- maximum candidate-validation wall budget: 2.0 seconds.

These budgets are separate from existing patch changed-byte and changed-line safety limits.

## 3. Final candidate integration

`repo_writer._validate_operations()` now invokes Python candidate validation only after all accepted operations targeting the same file have been composed into the final candidate.

The integration preserves these properties:

- one final validation event per changed Python file rather than one event per intermediate edit;
- exact baseline bytes are supplied for modification previews;
- exact final candidate bytes are supplied for validation;
- preview validation does not write candidate source to the repository;
- candidate-validation budget exhaustion does not bypass stale-hash, path, symlink, binary, overlap, newline, or other existing patch safety checks;
- non-Python patch candidates are not assigned synthetic Python validation evidence.

Gate 1 does not make invalid Python automatically repairable or directly non-applicable. That policy remains outside G1.

## 4. Managed preview bundle v4

New managed preview bundles now use `bundle_version = 4`.

For Python modification previews, bounded candidate-validation evidence is persisted alongside the ordinary selected payload descriptor.

The selected payload remains identified and verified by the existing opaque payload files/chunks plus payload SHA-256 and size metadata. Candidate-validation metadata is evidence beside that payload identity; it does not select replacement bytes.

Compatibility is retained:

- v2 managed bundles remain readable/applicable;
- v3 managed bundles remain readable/applicable;
- v4 managed bundles use the same payload assembly and hash-verification strength as the prior opaque bundle path;
- creation/removal previews can be v4 bundles without gaining unsupported Python-candidate semantics in this gate.

The integrity wording remains intentionally limited: managed payload and manifest hashes establish internal bundle consistency. They are not claimed to be an external immutable cryptographic trust anchor against a coordinated rewrite by an actor that can modify both managed payload storage and the manifest.

## 5. Focused test acceptance

Acceptance command covered:

- `tests/test_repo_candidate_validation.py`;
- `tests/test_repo_writer.py`;
- Ruff lint for the two implementation modules and two focused test files;
- `git diff --check`;
- Ruff-format and EOL diagnostics for all four touched files.

Primary acceptance run:

`20260815T045252Z_executable_profile_fa25e28b`

Functional results from that run:

- pytest: PASS - 127 passed;
- Ruff lint: PASS;
- `git diff --check`: PASS.

The command's aggregate exit code was non-zero only because the diagnostic portion reported the already-existing Ruff-format debt in `soma/repo_writer.py` and `tests/test_repo_writer.py`, and the first EOL helper had a quoting error. The functional test/lint/diff results above were independently reported as successful by the same run.

Follow-up EOL/format diagnostic run:

`20260815T045340Z_executable_profile_0ef692e0`

Current working-tree EOL counts:

- `soma/repo_candidate_validation.py`: 245 LF, 0 CRLF, 0 bare CR;
- `soma/repo_writer.py`: 142 LF, 2128 CRLF, 0 bare CR;
- `tests/test_repo_candidate_validation.py`: 271 LF, 0 CRLF, 0 bare CR;
- `tests/test_repo_writer.py`: 98 LF, 2555 CRLF, 0 bare CR.

All four files end with a newline.

Ruff-format status from that diagnostic:

- `soma/repo_candidate_validation.py`: PASS, already formatted;
- `tests/test_repo_candidate_validation.py`: PASS, already formatted;
- `soma/repo_writer.py`: diagnostic says it would reformat;
- `tests/test_repo_writer.py`: diagnostic says it would reformat.

This legacy formatter debt predates Gate 1. The pre-G1 planning/acceptance anchor `9f5444572434145bd042ac4242c8f50f576bd32f` was tested directly through Ruff-format in run:

`20260815T045423Z_executable_profile_d4ad7466`

At that pre-G1 commit, both `soma/repo_writer.py` and `tests/test_repo_writer.py` already produced `Would reformat` under the same repository Ruff configuration. The current HEAD blobs were also checked in run `20260815T045415Z_executable_profile_e0338cb4` and retain that same legacy whole-file formatter state.

Gate 1 therefore does not normalize those large legacy files as a side effect. Doing so here would create unrelated whole-file formatting/EOL churn. The new isolated G1 module and its dedicated test file are formatter-clean.

## 6. Behavioral proofs included in the focused suites

The accepted tests prove at least the following Gate-1 properties:

- baseline-valid/candidate-valid Python;
- baseline-valid/candidate-invalid regression detection;
- baseline-invalid/candidate-invalid distinction;
- create-style no-baseline validator semantics in the pure validator;
- bounded diagnostics;
- Unicode Python source;
- LF, CRLF, and missing-EOF-newline parsing;
- exact 512 KiB admission and over-limit skip behavior;
- per-preview file-count, total-byte, and wall-budget behavior;
- deterministic budget-skip evidence;
- validator does not import or execute candidate code;
- validator does not read or write the claimed candidate path;
- final composed same-file candidate is validated once;
- budget exhaustion does not bypass ordinary patch safety;
- candidate validation remains internal to G1.2 before bundle persistence;
- G1.3 persists bounded validation evidence in v4;
- validation metadata cannot select different payload bytes;
- v4 payload tampering remains rejected;
- v2/v3 apply compatibility remains intact;
- existing preview/apply/revert compatibility remains covered by the repo-writer suite.

## 7. Public/runtime compatibility

A live capability check after G1 implementation reported:

- public actions: 34;
- public operation-inventory gateways: 34;
- accepted public schema hash: `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`;
- runtime/live input schema hash remains the same accepted hash.

No public tool was added.

No public request schema was changed.

No connector refresh, service restart, runtime activation, deployment, or push is part of G1.

## 8. Concurrent-work boundary

Concurrent research output under `docs/sol-agentic-loop-realignment-research/` and the pre-existing `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` are outside this lane.

They are intentionally not included in the G1 implementation or this selected acceptance commit.

## 9. Gate verdict

G1 - Candidate Validation Foundation is ACCEPTED.

The repository now has a bounded pure Python candidate validator, final-candidate integration, and durable bundle-v4 validation evidence while preserving the existing selected-payload integrity path and v2/v3 compatibility.

No deterministic repair detector or proposal exists yet.

No source preview resolution flow exists yet.

No candidate-validation applicability policy has been activated yet.

The next implementation gate is G2 - Deterministic Transport Repair Proposal. Per the implementation plan, completion of G1 does not itself authorize or implement G2.
