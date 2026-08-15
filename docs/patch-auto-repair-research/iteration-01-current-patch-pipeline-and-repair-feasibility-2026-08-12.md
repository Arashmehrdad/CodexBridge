# Patch Auto-Repair Research - Iteration 01

Date: 2026-08-12
Status: research only
Repository: Soma
Lane observed: `lane/memory-integration-foundation-1`
Repository snapshot at final source check: `02a2afbc8b174b3cc5ced1bfeb8676ebddc8acf6`

## Scope and discipline

This iteration investigates whether Soma can reduce controller patch-construction mistakes by validating the complete post-edit candidate before it becomes an applicable managed preview, and whether a very narrow class of mechanically obvious corruption can eventually be repaired deterministically.

No production source, schema, runtime, connector state, or repository behavior was changed by this research. The only intended repository change is this research journal. No restart, connector refresh, commit, or push is part of this iteration.

The active Agent/Worker implementation lane moved while this research was in progress. At the final status check, unrelated untracked work included:

- `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md`
- `soma/reasoning/__init__.py`
- `soma/reasoning/models.py`
- `soma/worker_evidence/__init__.py`
- `soma/worker_evidence/models.py`

Those files were treated as parked concurrent work and were not modified.

## Executive finding

The smallest useful improvement is real, but Tier-A automatic repair should not be the first activation.

Soma already has almost exactly the right architectural seam for candidate validation:

```text
structured patch operations
        |
_validate_operations
        |
full per-file candidate materialized in memory as new_content
        |
[NEW: deterministic candidate validation / transport-leak analysis]
        |
_write_preview_bundle
        |
opaque candidate payload + SHA-256 identity
        |
repo_apply(previewed_change, patch_id)
        |
apply verifies repository/file/payload identity
        |
atomic worktree write
```

The current implementation already materializes the complete candidate before worktree mutation. It already stores the exact candidate as an opaque, hash-bound payload. The public apply path already consumes only the `patch_id`, not a second model-authored patch payload. Therefore candidate validation can be inserted before preview acceptance without giving Soma any new semantic authority.

The observed failure class is not a confirmed Soma bug. Current Soma behavior is contract-consistent: if malformed control/tool-call text is present inside `new_text`, Soma treats it as requested source content, materializes it, previews it, binds its hash, and later writes exactly that previewed content after integrity checks.

Recommendation for a first implementation, if later authorized:

1. Add candidate validation and high-confidence transport-leak detection at preview time.
2. For a uniquely repairable leak, return a transparent `repair_available` result with the exact proposed suffix removal and before/after hashes.
3. Do not mutate the candidate automatically in the first activation.
4. Collect real malformed-payload examples and prove detector precision.
5. Only then consider a narrowly versioned Tier-A auto-repair rule.

This should reduce repeated controller friction while preserving Soma's role as deterministic infrastructure.

## 1. Confirmed current Soma behavior

### 1.1 Public preview and apply authority

Evidence:

- `soma/gateway_models.py` around lines 1100-1185 defines `RepoPatchPreview` and `RepoPreviewedChangeApply`.
- `RepoPatchPreview` accepts a list of structured operation dictionaries.
- `RepoPreviewedChangeApply` requires a `patch_id` and commit mode; it does not require the model to resend replacement text.
- `soma/server.py` around lines 6621-6650 routes public `repo_preview(operation="patch")` to the internal preview implementation.
- `soma/server.py` around lines 6653-6695 routes public `repo_apply` through the durable job manager.
- `soma/job_manager.py` around lines 1370-1398 records `previewed_change` as a durable repository apply operation.
- `soma/job_worker.py` around lines 2595-2615 executes `repo_writer.apply_previewed_repo_change(repo_root, patch_id, runs_dir)`.

Authority consequence: the public write path is already separated from model-authored patch construction. Once a preview is accepted, apply is an execution of the stored opaque candidate, not a fresh interpretation of edit intent.

### 1.2 Patch operation primitives

The public capability schema in `soma/capabilities.py` exposes four primary patch types:

- `exact_text`
- `line_range`
- `unified_diff`
- `python_ast`

The writer contains compatibility aliases internally, but this research treats the four public types above as the relevant contract surface.

### 1.3 Candidate materialization already exists

`_validate_operations` in `soma/repo_writer.py` reads each target file, verifies path constraints and the caller-provided file hash, applies all requested operations in memory, and constructs one final per-file state.

For each successfully composed file it produces a validated record containing, among other fields:

- current file SHA-256;
- current content;
- complete `new_content`;
- unified diff;
- changed-line and changed-byte counts;
- newline diagnostics;
- per-operation validation results;
- warnings.

This answers a central Iteration 1 question: Soma already materializes the full candidate file before apply and before worktree mutation.

### 1.4 Existing mechanical validation hooks

Current preview validation already checks substantial transport/edit mechanics:

- repository-relative path validation;
- blocked file types and sensitive paths through reader/writer path policy;
- file existence, file-vs-directory, symlink and binary restrictions;
- stale SHA-256 mismatch;
- exact-text anchor uniqueness;
- exact-text overlap between same-file operations;
- line-range bounds plus expected range content/hash checks;
- strict unified-diff hunk parsing and context/removal matching;
- Python AST target discovery for top-level function/class/import operations;
- operation exclusivity rules;
- newline preservation and newline-only-change detection;
- total changed-line and changed-byte limits.

What is missing is a generic validation of the complete post-edit candidate as source/data in its target language or format.

### 1.5 `python_ast` validates the old tree, not the resulting candidate

`_apply_python_ast_operation` and `_apply_python_ast_preserving_newlines` call `ast.parse(content or "\n")` so Soma can locate the requested top-level function, class, or import in the current file.

The replacement `new_text` is then inserted textually. The resulting full candidate is not parsed or compiled again.

This means a `python_ast` operation can have a structurally valid target and still produce syntactically invalid Python if the replacement payload itself is malformed. That is not a violation of the current contract; it is simply an available validation gap.

### 1.6 Preview identity is already strong

`preview_repo_patch` calls `_validate_operations`, then places each validated file's complete `new_content` into the preview bundle as opaque payload text.

`_write_preview_bundle` persists payload bytes and a manifest. Bundle version 3 records, per operation, the current file hash plus payload metadata including a payload SHA-256 and size. The manifest is repository-bound using a repository fingerprint and records the Git HEAD observed at preview time.

Current identity contract therefore already binds the exact candidate that apply is allowed to write.

### 1.7 Apply-time verification and rollback

`apply_previewed_repo_change` verifies before mutation:

- patch lifecycle status;
- bundle version;
- repository fingerprint;
- operation entries and duplicate paths;
- relevant Git HEAD stability for modify/remove operations;
- current file SHA-256 for modifications;
- opaque payload assembly and payload hash integrity;
- path/file constraints again;
- changed-line and changed-byte limits again.

Before mutation it saves rollback bytes. Writes use atomic temp-file replacement. If a multi-file apply fails, Soma attempts rollback and records failure/rollback state.

A separate `revert_managed_patch` path verifies the current applied-file hashes before restoring rollback content.

This is an important boundary for the research: a future repair layer does not need to invent transactionality. It should feed a validated candidate into the existing preview identity and transaction system.

## 2. Observed real failure mode

The motivating failure was controller-side patch construction error, observed twice during Agent/Worker implementation. A replacement intended to contain source code accidentally included trailing tool-call/control-plane syntax, conceptually similar to:

```text
<intended Python replacement>
new_text=...
expected_sha256=...
})
```

The current research input does not contain the exact raw malformed replacement bytes from those two incidents. Therefore this iteration does not claim that one literal regex can already identify every observed event.

Classification remains:

`implementation-friction`

not a confirmed Soma bug.

Soma followed its current authority contract faithfully: replacement text is source content unless an existing structural rule says otherwise.

## 3. Where detection belongs

### Primary seam: preview, after candidate materialization and before bundle acceptance

Best location:

```text
_validate_operations(...)
    -> validated file records with new_content
    -> candidate validators
    -> transport-leak detector
    -> optional repair proposal
    -> _write_preview_bundle(...)
```

Why this seam is strong:

- the full candidate exists;
- no worktree file has been mutated;
- current file and requested operation metadata are still available;
- syntax errors can be compared against the edited region;
- existing diff/newline statistics are available;
- the existing opaque payload hash can bind the accepted final candidate;
- public apply authority does not change.

### Secondary seam: apply-time provenance verification

If repair is eventually added, apply should verify the stored repair/candidate identity, but it should not independently rediscover or rerun repair.

Preview decides what exact bytes are eligible to become an applicable candidate. Apply verifies and writes those bytes.

This avoids two repair engines making different decisions across time/runtime versions.

### Post-apply validation

Post-apply syntax checks are too late for the motivating failure. They may be useful in a broader future transaction-validation design, but making them authoritative now would create new rollback behavior for files that are intentionally invalid or validated by a different toolchain.

They are not required for the smallest useful improvement.

## 4. Python validation feasibility

Python candidate validation can be added without changing patch authority because parsing/compilation is deterministic inspection of the already-materialized candidate. It does not decide what code should mean or rewrite logic.

For complete `.py` candidates, `compile(candidate, filename, "exec", dont_inherit=True)` is a better correctness signal than `ast.parse(candidate)` alone.

The Python documentation explicitly notes that successful `ast.parse()` does not guarantee compilable Python because scoping checks happen during compilation. For example, an isolated top-level `return` can produce an AST and still fail compilation.

Important constraints:

1. Baseline comparison matters. If the current file is already invalid under the validator, a candidate parse failure alone should not prove the edit is bad.
2. Runtime version matters. Soma's interpreter may not match the repository's target Python version. Python's `feature_version` parsing is documented as best-effort, not a perfect emulation of another interpreter.
3. Parser resource failures must be bounded and caught. Python documents stack-depth/resource failure possibilities for sufficiently complex input.
4. Syntax validation should report exact error location and whether it intersects or immediately follows the edited range.

Initial Python validation states should therefore distinguish at least:

- baseline valid, candidate valid;
- baseline valid, candidate invalid;
- baseline invalid, candidate invalid;
- validation unavailable/not applicable.

Only the second state is a strong new-regression signal by itself.

## 5. High-confidence signature for leaked patch-control syntax

A safe detector must not treat the mere presence of words such as `new_text`, `expected_sha256`, `path`, braces, or `})` as corruption. All of those can be legitimate source text, test data, examples, comments, strings, fixtures, or code generators.

The proposed signature is conjunctive and operation-aware.

A candidate is eligible for a high-confidence `transport_control_suffix_leak` finding only when all required evidence is present:

1. The suspicious text occurs at the trailing boundary of one replacement payload, not at an arbitrary interior location.
2. The original full candidate newly fails the relevant candidate validator when the baseline current file was valid, or there is another strong structural failure exactly at the replacement tail.
3. The suffix matches a versioned, explicitly enumerated control-fragment grammar rather than a broad token regex.
4. The suffix contains at least one strong identity echo from the surrounding operation, preferably the exact 64-hex `expected_sha256`, and where available matching path/type/target metadata.
5. The proposed repair deletes only the suspicious trailing suffix. The intended replacement prefix is byte-for-byte preserved.
6. Removing that suffix yields a candidate that validates.
7. There is exactly one admissible suffix boundary and one admissible repaired candidate.
8. The changed byte range is minimal and recorded exactly.

If any of these conditions fails, automatic repair is not mechanically proved.

The exact raw malformed payloads from the two motivating incidents should be captured before defining the production grammar. Without those bytes, this iteration can specify the safety contract but should not freeze a literal suffix recognizer.

## 6. Can the observed class be deterministically repaired?

Potentially yes, but only for a narrower subclass than "source contains tool-looking text."

A deterministic repair is defensible when:

```text
baseline candidate state: valid
original candidate state: invalid
known transport suffix: exact match + operation metadata echo
candidate after deleting exactly that suffix: valid
number of valid repair cuts: 1
bytes changed: suspicious suffix only
```

That is close to mechanically provable intent preservation because Soma is not generating replacement source. It is only removing a transport fragment that can be tied back to the patch envelope itself.

However, this iteration recommends not enabling automatic mutation yet. Two motivating events are not enough evidence to know the real suffix family or false-positive surface.

## 7. False-positive cases that make broad auto-repair dangerous

Examples that must not be silently changed:

- a Python test intentionally embeds `expected_sha256=...` in a string;
- a fixture contains malformed Python for parser testing;
- documentation or source comments demonstrate repository tool syntax;
- a generated source file intentionally embeds tool-call examples;
- a source generator outputs JSON/Python snippets containing patch field names;
- a repository intentionally keeps a syntactically incomplete file;
- the repository targets a Python grammar newer or older than Soma's interpreter;
- multiple suffix cuts produce valid Python;
- deleting a suspicious suffix makes parsing succeed but also removes legitimate code;
- the candidate is syntactically valid even with the suspicious tokens;
- the syntax error is outside the edited region;
- the current file was already invalid under the selected validator.

These cases support a conservative rule: syntax validity is evidence, not proof of intent. Transport identity plus unique minimal repair is the key extra evidence.

## 8. Recommended first implementation mode

Recommended starting point: `detection + repair suggestion`, not Tier-A auto-repair.

Suggested behavior for a strong unique leak finding:

- do not create an applicable `preview_ok` candidate from the malformed content;
- return `repair_available` or equivalent;
- show the rule ID, suspicious byte range, exact number of removed bytes, original candidate hash, proposed candidate hash, validation-before and validation-after;
- require the controller to resubmit the corrected patch during the first activation phase.

This immediately prevents the damaging friction loop while generating a corpus of confirmed repair proposals.

After sufficient evidence, a later explicitly authorized version could allow auto-repair only for rules whose false-positive rate has been demonstrated to be effectively zero under the required identity anchors.

## 9. Candidate result vocabulary

The proposed vocabulary is useful with one timing caveat:

- `valid` - applicable candidate with no relevant warning.
- `valid_with_warning` - candidate is applicable, but non-authoritative diagnostics exist.
- `repair_available` - one deterministic repair proposal exists, but was not applied.
- `blocked_invalid_candidate` - candidate violates an enforced validation policy and no safe repair exists.
- `blocked_ambiguous_repair` - more than one repair or boundary is plausible.
- `validation_not_applicable` - no trusted validator is configured for this file/context.
- `auto_repaired` - reserve for a later activation; do not introduce as first behavior.

No production enum is recommended in this research iteration.

## 10. Provenance and identity contract

Current bundle identity is strong for the final candidate, but a future repair feature must preserve both pre-repair and post-repair identity.

A `PatchRepairRecordV1`-like record should contain:

```text
original_patch_hash
original_candidate_hash
repair_kind
repair_rule_version
repaired_patch_hash
repaired_candidate_hash
changed_byte_ranges[]
validation_before
validation_after
auto_repair_allowed
auto_repair_applied
explanation
```

Additional recommendations:

- `original_patch_hash` should hash a canonical serialization of the structured operation object received by Soma. `repo_writer` may not have access to the transport's raw MCP/JSON byte serialization, so it should not pretend otherwise.
- `original_candidate_hash` hashes the exact candidate before repair.
- `repaired_candidate_hash` should equal the opaque preview payload identity that apply later verifies.
- `changed_byte_ranges` should be expressed both relative to the replacement payload and, where available, the full candidate file.
- the repair record should be persisted in the managed preview bundle or a hash-bound sidecar, not only returned transiently.
- compact public responses can expose a concise summary; full patch status can expose complete provenance.
- apply must never recalculate a repair. It only verifies the stored record/payload integrity and writes the preview-bound candidate.

This prevents hidden rewriting.

## 11. Interaction with current patch types

### `exact_text`

Good first target for detection. Soma knows the exact replacement payload and the exact unique source anchor. A trailing corruption suffix in `new_text` can be mapped precisely to the edited range.

### `line_range`

Also a good first target. The edited region is explicit, and the implementation already requires expected range evidence. Candidate-level validation can localize a new syntax failure to the replacement range.

### `python_ast`

Especially valuable for candidate validation because the current implementation parses the old file to find the structural target but does not validate the resulting file. Detection can be added without changing AST edit authority.

Do not use the new validator to invent or rewrite function/class bodies.

### `unified_diff`

Soma already performs strict hunk syntax/context checking without Git-style fuzz. Candidate-level language validation can still inspect the resulting full file.

Automatic repair of the diff payload itself should be deferred. Translating a candidate-level suffix deletion back into one or more diff lines is a larger provenance problem and is not needed for Iteration 1's smallest useful improvement. Detection-only is safer here initially.

## 12. Other language-aware validators worth considering

Initial support should favor deterministic standard-library parsers with clear file semantics:

- `.py`: Python compilation, with baseline comparison and runtime-version caveats.
- `.json`: JSON parse, where the file is expected to be a complete JSON document.
- `.toml`: `tomllib` parse where available and where the file is expected to be TOML.
- `.xml`: XML parse only where complete-document semantics are expected.

Defer or make opt-in initially:

- YAML, because parser dependency, tag/schema behavior, and YAML-version differences make "valid" less uniform;
- tolerant multi-language parsers as hard blockers;
- language-server diagnostics as authoritative patch acceptance criteria.

Tree-sitter is interesting for future diagnostics because its parse tree explicitly represents `ERROR` and inserted `MISSING` nodes, which can help localize syntax damage while still producing a tree. That tolerance is useful for diagnostics, but it is weaker as a binary validity gate than a native compiler/parser.

## 13. External research comparison

Primary/current sources checked on 2026-08-12:

### Python parser/compiler

Python 3.14 documentation states that `ast.parse()` is implemented via compile-with-AST flags and explicitly warns that AST parsing success does not guarantee executable-valid Python because compilation performs additional checks.

Relevant source:
- https://docs.python.org/3/library/ast.html

Design lesson for Soma: if Python syntax enforcement is desired, compile the complete candidate rather than relying only on AST construction; treat interpreter-version mismatch as a policy concern.

### Git patch preflight and atomicity

Current `git apply` documentation exposes `--check` to test whether a patch is applicable without applying it. Git also documents default whole-patch failure/working-tree non-mutation when hunks do not apply, unless reject mode is explicitly requested. Context-free patches are discouraged because surrounding context is a safety measure.

Relevant source:
- https://git-scm.com/docs/git-apply

Design lesson for Soma: validation-before-mutation and exact applicability checks are established safe-edit patterns. Soma already follows this shape for hash/context/newline mechanics; language candidate validation would extend preflight rather than redesign apply.

### LibCST codemods

LibCST codemods separate transformation results into success/failure/skip, preserve warnings, can skip generated code, support explicit parser Python versions, and provide before/after codemod tests.

Relevant source:
- https://libcst.readthedocs.io/en/latest/codemods.html

Design lesson for Soma: structured transforms benefit from explicit warnings, skips and testable before/after identity. This supports transparent repair provenance rather than silent rewrite.

### Tree-sitter

Tree-sitter represents unrecognized syntax with `ERROR` nodes and parser-recovery insertions with `MISSING` nodes.

Relevant sources:
- https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html
- https://tree-sitter.github.io/tree-sitter/cli/parse.html

Design lesson for Soma: tolerant parsers can provide localized diagnostics for additional languages later, but their ability to recover means they should not automatically be treated as strict validity gates.

### Language Server Protocol

The current LSP site identifies 3.18 as the latest specification and standardizes a separation between editor clients and language-specific servers for diagnostics and related language features.

Relevant source:
- https://microsoft.github.io/language-server-protocol/
- https://microsoft.github.io/language-server-protocol/specifications/lsp/3.18/specification/

Design lesson for Soma: language-aware diagnostics can remain an external/advisory layer. Soma does not need to become a language server or semantic code agent to benefit from deterministic syntax checks.

### OpenAI Codex public pattern

Current OpenAI Codex Security documentation describes validation before surfacing a finding, generation of a minimal patch suggestion, human review rather than automatic repository mutation, and revalidation after remediation.

Relevant source:
- https://help.openai.com/en/articles/20001107

This is not public evidence of a low-level Codex patch-transport repair algorithm, and this research should not infer one. The useful pattern is the separation between validation, minimal proposed change, review, and later application.

### Anthropic Claude Code public pattern

Anthropic's Claude Code documentation exposes explicit tool permission boundaries. Its SDK documentation also documents `updatedInput` for permission flows where a shown edit/diff is manually changed, making the mutation of tool input explicit rather than silently pretending the original input was unchanged.

Relevant sources:
- https://docs.anthropic.com/en/docs/claude-code/cli-usage
- https://docs.anthropic.com/en/docs/claude-code/sdk

Again, this is not public evidence of an automatic patch-repair algorithm. The relevant design lesson is provenance: if tool input is changed, that changed input should be represented explicitly.

## 14. Should Soma recommend narrower edit primitives?

Soma should not automatically convert a broad `exact_text` operation into `line_range` or `python_ast`.

Reasons:

- conversion changes the anchoring contract;
- finding an AST target from arbitrary text can require semantic inference;
- line-range and structural edits are not guaranteed to be equivalent to the controller's chosen operation;
- hidden conversion would complicate preview identity and debugging.

A low-noise advisory may eventually be useful for exceptionally large replacement surfaces, for example:

```text
Large replacement surface detected. Consider line_range or python_ast if the edit has a stable narrower anchor.
```

It should not claim that a narrower primitive definitely exists. It should be thresholded and ideally justified by real failure data. This ergonomics feature is lower priority than candidate validation and should not be bundled into the first implementation.

## 15. Required tests before activation

### Detector unit tests

- exact known leaked suffix with matching operation identity is detected;
- same control words inside a Python string are not detected;
- same control words inside comments/docs/fixtures are not detected solely by token presence;
- a suffix containing a different SHA-256 from the current operation is not Tier-A eligible;
- original candidate invalid + unique suffix removal valid is `repair_available`;
- original candidate valid does not trigger repair;
- repaired candidate still invalid does not trigger repair;
- two valid suffix cut points produce `blocked_ambiguous_repair`;
- current/baseline file already invalid does not become a generic hard block;
- syntax error outside the edited range does not become a transport-leak repair;
- Python version mismatch is reported without semantic guessing;
- parser `SyntaxError`, `ValueError`, `MemoryError`, and `RecursionError` paths fail safely.

### Patch-type tests

- `exact_text` candidate validation;
- `line_range` candidate validation;
- `python_ast` candidate validation after structural replacement;
- `unified_diff` candidate detection without automatic diff rewriting.

### Provenance tests

- original structured operation canonical hash is stable;
- original candidate hash matches exact pre-repair bytes;
- proposed candidate hash matches exact post-repair bytes;
- changed byte ranges reconstruct the exact difference;
- repair rule/version is persisted;
- compact and full status expose consistent repair summary;
- tampering with repaired payload or repair record is rejected.

### Pipeline safety tests

- blocked/repair-available preview never mutates worktree;
- an invalid/blocked preview cannot be applied;
- apply does not rerun or reinterpret repair;
- existing payload chunk/tamper protections remain intact;
- stale file hash and repository binding protections remain intact;
- apply idempotence remains intact;
- rollback/revert behavior remains intact;
- newline preservation remains byte-for-byte compatible;
- existing symlink/path/sensitive-file protections remain intact;
- repo writer still imports no Codex runner or model component.

### Performance tests

Benchmark full-candidate validation on representative small and large source files under Soma's current patch/file limits. Validation should remain cheap enough to run synchronously during preview. Resource exceptions must be bounded and surfaced as validation-unavailable rather than crashing the service.

## 16. Candidate policy tiers

### Tier A - mechanically provable transport repair

Future-only, after detector evidence exists.

Required properties:

- exact versioned rule;
- exact operation metadata echo;
- suffix-only deletion;
- one repair candidate;
- minimal bytes;
- validation before fails and validation after succeeds;
- complete provenance persisted.

### Tier B - ambiguous but suggestible

Examples:

- multiple plausible quote/bracket repairs;
- parse error near the edit but no exact transport identity;
- suspicious control tokens remain but candidate is otherwise valid;
- a possible suffix cut exists but more than one repaired candidate validates.

Behavior: warning or blocked suggestion, no automatic source change.

### Tier C - semantic/code problem

Examples:

- failing tests;
- wrong API usage;
- type errors requiring reasoning;
- changed behavior;
- incorrect assertion;
- architecture mismatch.

Behavior: never auto-repair in repository infrastructure. Return evidence to the controller/reasoning layer.

## 17. Rejected ideas in Iteration 1

### Reject: `ast.parse` failure means every Python patch is blocked

Too many false positives: pre-existing invalid files, fixtures, target-version mismatch, generated/incomplete files.

### Reject: delete any tail containing `expected_sha256` or `new_text`

Those tokens can be legitimate source content. Identity-anchored grammar plus candidate validation is required.

### Reject: ask an LLM inside Soma what the model meant

Violates the deterministic-infrastructure boundary and creates a second semantic coding agent.

### Reject: silently repair and only expose the repaired diff

Destroys provenance and makes debugging tool/model failures harder.

### Reject: rerun repair at apply time

Can diverge from preview due to runtime/rule changes and weakens preview identity.

### Reject: auto-convert broad edits to AST/line-range operations

Changes operation semantics/authority and requires inference.

### Reject: broad formatter-based repair

Formatting can rewrite large portions of a file and is not a proof of controller intent.

## 18. Unresolved questions

1. What are the exact raw leaked suffixes from the two motivating incidents? These are needed to define a production rule grammar.
2. Should enforced syntax validation be configured per repository/path, or should baseline-valid -> candidate-invalid be an unconditional block for selected file types?
3. Which interpreter/version should validate Python when repository target version differs from Soma's runtime?
4. Should `create_file` share the same candidate-validation framework in the first implementation or follow after patch edits?
5. Should repair provenance live directly in `manifest.json` or in a separate hash-bound `repair.json` sidecar referenced by the manifest?
6. What public response budget is appropriate for concise repair evidence without echoing large replacement payloads?
7. How much real telemetry/corpus evidence is sufficient before Tier-A auto-repair is allowed?
8. Should exact strong transport leaks be `repair_available` with no applicable preview, or `blocked_invalid_candidate` plus a separate repair proposal object? Both preserve safety; naming should match the surrounding gateway conventions.

## 19. Confirmed bugs

None confirmed in Iteration 1.

The motivating event remains correctly classified as controller implementation friction under Soma's current contract.

## 20. Direct answers to Iteration 1 questions

1. **Where can malformed replacement content be detected before worktree mutation?** After `_validate_operations` materializes each complete `new_content`, before `_write_preview_bundle` marks/stores an applicable preview.
2. **Does Soma already materialize a candidate before apply?** Yes. Complete per-file candidates are built in memory during preview and persisted as opaque payloads.
3. **What validation hooks already exist?** Path/file safety, stale hashes, anchor/range/diff/AST-target validation, overlap/exclusivity, newline diagnostics, size limits, payload identity, repository binding and apply-time rechecks.
4. **Could Python syntax validation be added without changing patch authority?** Yes. Deterministic compile/parse inspection of the complete candidate fits the current preview phase and does not grant semantic rewrite authority.
5. **What signature distinguishes leaked control syntax from legitimate source?** Not token presence alone. Require a trailing replacement-boundary fragment matching a versioned control grammar, operation metadata identity echo, new candidate validation failure, unique suffix-only deletion, and successful validation after deletion.
6. **Can the real observed class be deterministically repaired with near-zero ambiguity?** A narrow metadata-anchored suffix-leak subclass likely can. The exact two raw incidents should be captured before freezing the rule.
7. **What false positives make auto-repair dangerous?** Legitimate tool-like strings/comments/fixtures/generated code, intentionally invalid files, target-version mismatch, multiple valid cut points, syntax errors outside the edit, and candidates already invalid before the patch.
8. **What should first implementation start with?** Detection plus repair suggestion, with the malformed preview non-applicable. Delay auto-repair until rule precision is demonstrated.
9. **What tests are required?** Detector negatives/positives, all four patch types, provenance/tamper checks, no-mutation guarantees, apply identity/idempotence, rollback/newline regressions, parser resource failures, and performance bounds.
10. **Would this reduce controller friction enough to justify complexity?** Yes, if implemented as one small candidate-validation stage that reuses the existing materialized candidate and opaque preview identity. No, if expanded into semantic fixing, broad formatting, operation conversion, or a multi-language reasoning subsystem.

## 21. Iteration 1 conclusion

Soma does not need a new patch engine. It needs, at most, a conservative validation stage between candidate materialization and preview acceptance.

The architecture is already unusually favorable for this because:

- preview is read-only with respect to the worktree;
- final candidates already exist in memory;
- final candidates are already hash-bound;
- public apply already consumes an opaque preview identity;
- apply and rollback are already transactional and defensive;
- no model component is required in the writer.

The smallest useful next implementation, if authorized later, is therefore:

```text
candidate validator
+ high-confidence transport-suffix detector
+ transparent repair proposal/provenance
- no automatic rewrite at first
```

That is enough to prevent a repeat of the motivating malformed-Python preview while preserving the central boundary: Soma can detect mechanical transport/edit-construction errors, but the controller remains responsible for what the code should mean.
