# G6 Format Validation Acceptance - 2026-08-15

Status: **ACCEPTED - SOURCE ONLY, NOT LIVE**

## Scope

Gate 6 expands managed repository candidate-language validation from Python to complete JSON documents while deliberately refusing to broaden deterministic repair synthesis or parser dependencies merely because additional formats exist.

Accepted G6 implementation commit:

- `ebd5e23d320f2763fc11b79ee3c145210dca9c86` - `Add G6 bounded JSON candidate validation`

The accepted G5 source baseline was:

- `234dcaaf7f8fab91eea1deac0cdd62a0ea9e84e6` - `Accept G5 apply compatibility`

The Patch Auto-Repair implementation plan remains:

- `docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md`
- SHA-256: `197e69d5f546744332de39549831f497a67495183e3df23aea6fb4f217b6e21a`

## G6.1 - JSON complete-document validation

G6 adds `validate_json_candidate(...)` to the existing pure bounded candidate-validation layer.

The validator:

- accepts already-materialized bytes only;
- has no repository, network, model, agent, import, or execution authority;
- validates one complete JSON document;
- uses the existing shared `CandidateValidationBudget` limits;
- preserves the existing `repo_candidate_validation.v1` evidence model;
- hashes the exact candidate bytes;
- emits bounded deterministic diagnostics;
- treats `baseline_bytes=None` as diagnostic-only create-file validation rather than a regression source.

Frozen JSON policy constants are:

- validator: `json.loads.strict`
- encoding policy: `utf-8-strict`
- duplicate-key policy: `reject`
- non-finite-number policy: `reject`

### Strict UTF-8

JSON candidate bytes are decoded with strict UTF-8. Invalid UTF-8 produces bounded `json_encoding_error` evidence.

### Duplicate member names

Duplicate JSON object member names are rejected through an `object_pairs_hook` rather than inheriting Python's permissive last-key-wins behavior.

The diagnostic records only that a duplicate member exists; it does not echo the duplicate key value into evidence.

### Non-finite numeric constants

`NaN`, `Infinity`, and `-Infinity` are rejected. They are accepted by Python's default JSON decoder but are outside the strict JSON policy adopted for managed candidate validation.

### Numeric representation independence

JSON integer and floating-point tokens are parsed as strings for validation purposes (`parse_int=str`, `parse_float=str`). This keeps the check syntax-focused and prevents a syntactically valid document from failing merely because CPython's integer digit limit or floating-point representation is narrower than the source token.

### Nesting/resource behavior

The pre-existing file/preview/wall-time budgets remain authoritative. Excessive parser nesting that raises `RecursionError` is converted into bounded `json_nesting_error` evidence rather than escaping the validator.

### Modification policy

For existing `.json` files:

- baseline valid + candidate valid -> ordinary applicable preview;
- baseline valid + candidate invalid -> `preview_resolution_required`;
- JSON regressions do **not** invoke transport-corruption repair synthesis;
- therefore JSON resolution-required sources have no repair proposal in G6;
- `accept_original` remains the explicit controller validation override.

The resolution child preserves the raw candidate evidence as `regression_detected` while separately recording:

`candidate_validation_override = "accept_original"`

This preserves both facts instead of rewriting history: the candidate mechanically regressed validation, and the controller explicitly chose it anyway.

The selected child then uses the ordinary repair-blind apply/revert engine accepted in G5.

### Create-file policy

A `.json` create preview is diagnostic-first because there is no trusted valid baseline from which to infer a regression.

An invalid new JSON document therefore:

- persists JSON candidate validation evidence;
- reports aggregate `candidate_validation_status = "invalid"`;
- remains `preview_ok` rather than becoming resolution-required;
- receives no repair proposal;
- can still be explicitly applied and reverted through the ordinary managed-patch lifecycle.

### Repair boundary

`repo_writer` now gates repair proposal synthesis on candidate language being exactly `python`.

JSON validation can affect resolution-required state, but JSON never enters `build_patch_repair_proposal(...)` in G6. A dedicated test replaces that function with a fail-on-call sentinel and proves JSON preview construction does not call it.

Valid JSON containing transport-looking string content remains an ordinary valid preview and is not rewritten or proposed for repair.

## G6.2 - TOML capability decision

Decision: **C - DEFER TOML VALIDATION**.

Repository/runtime evidence:

- `pyproject.toml` still declares `requires-python = ">=3.10"`;
- stdlib `tomllib` is therefore not universally available across Soma's declared runtime range;
- no TOML parser dependency such as `tomli` is declared;
- no TOML parser path/import exists in the touched candidate-validation or repo-writer implementation.

G6 does not add a runtime dependency merely for patch ergonomics. `.toml` remains outside candidate-language validation until the runtime/dependency policy changes or a separately reviewed parser capability is justified.

## G6.3 - XML/YAML decision

**XML and YAML remain deferred.**

`PyYAML` is already a project dependency, but dependency presence alone is not authority to add YAML hard validation. The plan explicitly requires a targeted parser/security/resource-policy follow-up before XML/YAML enter this lane.

Dedicated G6 tests prove malformed-looking `.toml`, `.yaml`, `.yml`, and `.xml` modification candidates currently retain:

- `candidate_validation = None`;
- aggregate validation status `not_applicable`;
- no resolution-required state from format validation;
- no repair proposal.

No YAML, XML, TOML, `tomli`, or `tomllib` parser import was added to the touched implementation.

## Validation evidence

### Focused G6/G1-G3 behavior

Run: `20260815T083056Z_executable_profile_9dd498c2`

Result after correcting one test expectation about preserved accept-original provenance:

- **65 passed**
- Ruff lint passed
- only mechanical Ruff formatting remained for the new test file at that point

The corrected expectation is that an accept-original child preserves raw `regression_detected` evidence and records the explicit override separately.

### Integrated G1-G6 repo-writer compatibility

Run: `20260815T083220Z_executable_profile_c7a8fbf4`

Environment included the established standalone Trading Lab import root.

Result:

- **198 passed**
- Ruff check passed
- Ruff format check passed
- `git diff --check` passed

Coverage includes the legacy repo-writer suite, Python/JSON candidate validation, G2 repair behavior, G3 resolution, G5 repair-blind apply/revert, and G6 format policy.

### Public-contract regression

Run: `20260815T083426Z_executable_profile_7c1df047`

This reran the exact G4 public-contract acceptance suite and added the G6 validators/tests.

Result:

- **453 passed in 176.41s**
- Ruff check passed
- Ruff format check passed
- `git diff --check` passed

No public gateway model, metadata, or operation-inventory source file was changed by G6.

### Fresh-process source identity

Run: `20260815T083748Z_executable_profile_30f8ab2a`

Result:

- public tool count: **34**
- operation schema count: **264**
- two-pass discovery stable: `true`
- public schema hash: `ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42`
- public descriptor hash: `7acb65f1c6e3d4b85ea82296bd7d5cec281211c1b5bc00214d3b5b4860106273`
- operation inventory hash: `71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`
- `repo_preview.resolve_patch` schema hash: `2fdbe6ae4bb313cc6a406f66b0db46140ee0979fe04a2035a37de14b697a0213`

The four pre-existing `repo_preview` operation hashes also remain identical to G4.

Therefore G6 changes internal candidate evidence/preview semantics only and does not alter the accepted G4 public input contract.

## Changed implementation/proof files

The G6 implementation commit contains exactly:

- `soma/repo_candidate_validation.py`
- `soma/repo_writer.py`
- `tests/test_repo_candidate_validation_json_g6.py`

No Company, Agent/Worker, Sol agentic-loop research, or canonical-memory file entered the implementation commit.

## Runtime remains intentionally pre-G4

Gate 6 is source acceptance, not activation.

Soma was **not restarted** for G6 and the ChatGPT connector was **not refreshed**. The running MCP process therefore intentionally remains on the pre-G4 public contract until the separately authorized A1 activation stage.

The running public schema remains:

`00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`

This source/runtime divergence is expected and must not be repaired inside G6.

## Explicit non-actions

Gate 6 did **not**:

- add a public tool;
- change the accepted G4 public request schema;
- add JSON repair synthesis;
- enable TOML validation;
- enable XML/YAML validation;
- add a TOML dependency;
- weaken G5 apply/revert authority separation;
- restart Soma;
- refresh the ChatGPT connector;
- push or deploy;
- use Codex or provider subagents;
- modify concurrent Sol agentic-loop research or `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md`.

## Gate verdict

**G6 FORMAT VALIDATION ACCEPTED.**

Soma now has bounded complete-document JSON candidate validation with explicit strict policies, while repair synthesis remains Python-only and TOML/XML/YAML remain intentionally deferred.

**STOP at the top-level G6 boundary.**
