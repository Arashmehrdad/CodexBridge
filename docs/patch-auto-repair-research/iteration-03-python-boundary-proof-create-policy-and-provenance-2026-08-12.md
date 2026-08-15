# Patch Auto-Repair Research - Iteration 03

Date: 2026-08-12
Status: research only
Repository: Soma
Lane observed: `lane/memory-integration-foundation-1`
Repository snapshot at final pre-journal check: `4168d7493f592bf7d3a28f16b0770e9697d83260`

## Scope

Iteration 01 established the candidate-validation seam. Iteration 02 recovered the two real malformed patch incidents and proved that `compile()` success after deleting obvious transport text is not enough to authorize automatic repair.

Iteration 03 asks a narrower question:

> Can Soma prove, without source-specific semantic reasoning, that deleting a known trailing patch-control suffix cannot join the source on the two sides of the cut into a different Python statement or expression?

Secondary questions:

1. Does the same policy apply to `create_file`?
2. How should JSON/TOML/XML validation be staged?
3. Can repair provenance fit into the current managed preview bundle without a database migration?
4. What integrity claim does the current bundle actually support?
5. Is full candidate compilation/token inspection cheap enough in principle to remain synchronous?

No production source, runtime, schema, connector state, or public tool contract was changed. The only intended repository change is this research journal. No restart, commit, or push is part of this iteration.

Concurrent Agent/Worker work was treated as parked. At the final pre-journal status check it included unstaged changes in:

- `soma/project_scope/store.py`
- `soma/tasks/backends.py`
- `soma/tasks/manager.py`
- `soma/tasks/models.py`
- `soma/tasks/projections.py`
- `soma/tasks/store.py`

and untracked:

- `tests/test_reasoning_task_integration.py`
- `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md`
- Iteration 01 and Iteration 02 patch-auto-repair journals

None of those files were modified by this research.

## Executive finding

Iteration 03 finds a promising **narrow Python boundary proof** that is materially stronger than the Iteration 02 lexical-hazard checklist.

For a deletion-only repair candidate, after the repaired full file has successfully compiled:

```text
1. The transport detector proves one exact trailing deletion range.
2. The repaired source is tokenized, not the invalid source.
3. No token is allowed to span across the deletion cut.
4. Between the cut and the next token, only horizontal whitespace may exist.
5. The next token must be Python NEWLINE: a logical-line terminator.
```

Conceptually:

```text
invalid candidate
    |
known trailing transport suffix [cut_start:cut_end]
    |
delete exactly those bytes
    |
repaired candidate compiles
    |
tokenize repaired candidate
    |
no token crosses cut
    |
next token after optional horizontal whitespace == NEWLINE
    |
logical-line boundary proof passes
```

This rule separates the two real incidents without knowing anything about `__all__`, assertions, Company Kernel, or the later accepted code:

- Incident B (`}],"view":...` after a complete assertion) reaches `NEWLINE` at the cut and passes the boundary test.
- Incident A (`}],"commit_title":...` after `"WorkPackage"` inside an open list) reaches `NL`, not `NEWLINE`, and is rejected.

The distinction is language-defined. Python uses `NEWLINE` for the end of a logical line. `NL` is a non-terminating newline generated when a logical line continues across physical lines; the parser ignores it.

This means the guard naturally rejects:

- implicit continuation inside `()`, `[]`, `{}`;
- the real adjacent-string-literal trap;
- explicit backslash continuation;
- same-line call/subscript/attribute continuation;
- same-line operators and semicolons;
- lexical token fusion across the cut;
- same-line comments or other tokens following the cut.

The rule is still not ready to activate as automatic repair. The main remaining risk is not Python token joining anymore; it is **proving that the matched deletion bytes are truly an appended transport suffix and not intentional invalid fixture/source content** across repositories and patch primitives.

The recommendation therefore remains detection + repair proposal for first activation, while this logical-line rule becomes the leading candidate for a later Tier-A eligibility gate.

## 1. Source inspection: current candidate and create pipelines

### 1.1 Patch candidates

Current `soma/repo_writer.py` still composes all operations into one final `new_content` per file inside `_validate_operations` before `_write_preview_bundle`.

The final record includes current content, `new_content`, diff and newline/change diagnostics. `preview_repo_patch` copies `new_content` into the opaque payload as `payload_text`.

This remains the correct insertion seam for candidate validation.

### 1.2 Create-file candidates

`preview_repo_file_creation` is simpler:

```text
content
  -> _validate_create_target(path, size)
  -> diff from empty file
  -> payload_text = content
  -> _write_preview_bundle
```

`_validate_create_target` validates path/existence/parent and the 200 KB create limit. It does not validate language syntax or format.

This is important because create-file policy lacks a pre-edit baseline. A modified `.py` file can support the strong observation:

```text
baseline valid under same validator
candidate newly invalid
```

A newly created `.py` file cannot.

Therefore `create_file` should not inherit the modified-file blocking policy automatically.

## 2. Python logical-line boundary proof

### 2.1 Why `NEWLINE` is useful

Python's lexical reference defines a program as logical lines and states that the end of a logical line is represented by `NEWLINE`.

Official source:

https://docs.python.org/3/reference/lexical_analysis.html

The token constants documentation distinguishes:

```text
NEWLINE = end of logical line
NL      = non-terminating newline while a logical line continues
```

Official source:

https://docs.python.org/3/library/token.html

This distinction captures several hazards that would otherwise require separate handwritten bracket and continuation rules.

### 2.2 Why tokenize only the repaired candidate

Python's `tokenize` documentation warns that the module is designed for syntactically valid Python and behavior on invalid Python is undefined.

Official source:

https://docs.python.org/3/library/tokenize.html

Therefore:

```text
wrong:
  tokenize malformed candidate and infer repair

right:
  compile malformed candidate -> failure
  detect exact transport suffix independently
  delete exactly that suffix
  compile repaired candidate -> success
  tokenize repaired candidate for boundary proof
```

### 2.3 Proposed narrow rule

Let:

```text
C_bad = complete invalid post-edit candidate
[a:b) = exact deletion range identified as transport suffix
C_fix = C_bad[:a] + C_bad[b:]
cut   = a in C_fix
```

Tier-A boundary eligibility would require:

```text
compile(C_bad) fails
compile(C_fix) succeeds
```

Then tokenize `C_fix` and map token row/column coordinates to character/byte offsets.

Reject if any token satisfies:

```text
token.start < cut < token.end
```

because the repair boundary lies inside a token created by deletion.

Then locate the first token starting at or after `cut`.

Allow only horizontal whitespace between `cut` and that token:

```text
space
TAB
formfeed
```

The token must be `NEWLINE`.

A zero-length/synthetic final `NEWLINE` emitted for a final physical line without an explicit newline can still satisfy the logical-line condition. A bare `ENDMARKER` should not be sufficient for the first Tier-A rule; this avoids automatically reducing a suspicious candidate to empty/whitespace-only content.

### 2.4 Why this rejects Incident A

Deletion-only reconstruction of Incident A produces conceptually:

```python
__all__ = [
    "SettledSatisfactionV1",
    "WorkPackage"
    "WorkPackageAttempt",
    "canonical_hash",
]
```

The physical newline after `"WorkPackage"` occurs while `[` remains open.

Python therefore emits `NL`, not `NEWLINE`.

The rule rejects the repair before any semantic inspection of string contents is needed.

### 2.5 Why this accepts Incident B

Deletion-only reconstruction of Incident B produces conceptually:

```python
assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
```

At the deletion cut, all delimiters in the assertion are closed and the physical newline terminates the logical line.

The next token is `NEWLINE`.

The boundary rule therefore classifies it as structurally eligible for a future Tier-A rule.

## 3. Synthetic adversarial matrix

A local in-memory Python experiment was run without touching the Soma repository. The experiment reconstructed a known transport suffix and applied the proposed logical-line gate to repaired valid candidates.

The final hand-built matrix contained 35 cases.

### Expected eligible cases

- real Incident-B-like assertion boundary;
- assignment at logical line end;
- return;
- raise;
- pass;
- import;
- closed dict expression;
- closed call expression;
- `if` compound header before its newline;
- decorator line before a function definition;
- break;
- continue;
- yield;
- final complete statement without an explicit trailing newline;
- complete statement followed by horizontal trailing spaces;
- complete statement followed by a trailing tab.

### Expected ineligible cases

- real Incident-A-like adjacent strings inside a list;
- continuation inside parentheses;
- adjacent strings inside a list;
- adjacent strings inside a tuple;
- semicolon and second statement on same logical line;
- call continuation `func(...)` across the cut;
- attribute continuation `.attr`;
- subscription continuation `[0]`;
- same-line string literal concatenation;
- same-line binary operator;
- same-line comment after the cut;
- explicit backslash continuation;
- NAME token merge across cut;
- NUMBER token merge across cut;
- triple-quoted string spanning the cut;
- dict continuation inside braces;
- comprehension continuation;
- spaces followed by comment;
- spaces followed by semicolon.

Result:

```text
35 / 35 classified as expected
0 false accepts in the hand-built matrix
0 false rejects in the hand-built matrix
```

This is not statistical proof. The matrix is small and intentionally adversarial rather than sampled from arbitrary repositories. It is evidence that the `NEWLINE` formulation subsumes the concrete hazards discovered in Iteration 02 and several nearby classes with one language-defined condition.

## 4. What the logical-line rule actually proves

If the deletion range itself is already proven to be appended transport corruption, the rule provides a strong mechanical statement:

> Removing the suffix does not cause source text after the cut to continue the source text before the cut as the same Python logical line.

This is stronger and cleaner than enumerating every possible token pair.

It prevents both:

### Lexical fusion

Example:

```text
foo + deleted transport + bar
```

If deletion produces token `foobar`, that token spans the cut and the rule rejects.

### Syntactic continuation without lexical fusion

Examples:

```text
func + deleted transport + (arg)
obj  + deleted transport + .attr
obj  + deleted transport + [0]
"a" + deleted transport + "b"
```

These do not necessarily create one token across the cut, but a token other than `NEWLINE` appears after the cut, so the rule rejects.

### Implicit continuation

Inside open `()`, `[]`, `{}`, a physical newline is `NL`, not `NEWLINE`, so the rule rejects.

### Explicit continuation

A backslash-continued physical line does not produce the required logical-line `NEWLINE` at the cut, so the rule rejects.

## 5. What it does not prove

The rule does **not** prove that suspicious bytes are transport corruption.

A repository can intentionally contain or generate malformed Python. A patch can intentionally create a parser fixture. A model can also produce source that happens to contain gateway-looking strings.

Therefore Tier-A still needs the independent transport proof from Iteration 02:

```text
- exact known outer preview-envelope grammar;
- exact trailing boundary of one replacement payload;
- one rule version bound to active gateway schema/capability identity;
- new candidate syntax regression;
- exactly one deletion range;
- bounded deletion size;
- no inserted or synthesized source bytes.
```

The logical-line proof answers only the second half:

```text
if those bytes are definitely transport,
is deleting them source-boundary safe?
```

## 6. Suggested Python Tier-A proof after Iteration 03

A future automatic repair should require all of the following:

1. target is a complete `.py` source candidate;
2. validator policy is applicable;
3. modified-file baseline compiles under the same policy;
4. original candidate fails compilation;
5. exactly one schema-bound trailing transport suffix is detected;
6. suffix belongs to one operation replacement boundary, not arbitrary file interior;
7. deletion length is bounded;
8. repair deletes only those bytes;
9. repaired candidate compiles;
10. tokenize only the repaired candidate;
11. no token spans the cut;
12. only horizontal whitespace may appear from cut to next token;
13. next token is `NEWLINE`;
14. bytes outside deletion range are identical;
15. before/after candidate hashes and rule identity are persisted;
16. apply never reruns repair.

If any condition fails:

```text
no auto-repair
```

The appropriate result is repair suggestion, invalid-candidate block, or ambiguous-repair block.

## 7. `create_file` requires a separate policy

### 7.1 What can be reused

A complete newly-created `.py` candidate can still be compiled before preview acceptance.

The same post-repair logical-line proof can also be applied if an exact transport suffix is independently identified.

### 7.2 What cannot be reused

There is no current-file baseline.

For modified files, this is strong evidence:

```text
current file compiles
candidate does not
```

For creation, this distinction is impossible.

A user may intentionally create:

- an incomplete scratch file;
- an intentionally invalid parser fixture;
- a version-targeted Python file unsupported by Soma's interpreter.

Therefore a first implementation should not make generic create-file Python compilation a universal hard block merely because modified-file validation is a hard block.

### 7.3 Recommended initial create behavior

Until real create-file failure corpus exists:

```text
.py create candidate invalid
  -> diagnostic / warning by default

.py create candidate invalid
+ exact schema-bound transport leak proven
  -> block as transport corruption / repair suggestion

no automatic repair of create content in first activation
```

Repository policy could later opt into strict create validation.

## 8. Runtime/version policy remains material

Current Soma project metadata states:

```text
requires-python = ">=3.10"
```

The recovered real validation runs were executed with Python 3.12.

A same-runtime baseline comparison is strong for detecting a newly introduced syntax regression in an existing file.

It is not equivalent to proving compatibility with every Python version declared by a broad project range.

Python's `ast.parse(feature_version=...)` is documented as best-effort rather than exact emulation of another interpreter, so it should not be used to overclaim target-version compatibility.

Official source:

https://docs.python.org/3/library/ast.html

For the first implementation, validator results should record the actual interpreter major/minor used.

## 9. Format validator expansion

### 9.1 JSON - good early validation candidate

Python `json.loads()` parses a complete JSON document and raises `JSONDecodeError` for invalid JSON.

Official source:

https://docs.python.org/3/library/json.html

Important detail: `JSONDecoder.raw_decode()` explicitly supports a valid JSON prefix followed by extraneous trailing data. It is therefore the wrong hard-validity primitive for complete-file candidate validation.

Use complete-document parsing, not prefix parsing.

Initial recommendation:

```text
JSON candidate validation: reasonable early addition
JSON auto-repair: defer until separate boundary proof is researched
```

Also enforce existing candidate-size bounds because Python documentation warns that malicious JSON can consume significant CPU/memory.

### 9.2 TOML - useful but runtime-gated

`tomllib` provides complete TOML parsing and raises `TOMLDecodeError` for invalid documents.

Official source:

https://docs.python.org/3/library/tomllib.html

But `tomllib` was added in Python 3.11, while Soma's project metadata currently allows Python 3.10.

Therefore a standard-library-only TOML validator cannot be assumed available on every currently supported Soma interpreter.

Options for later planning:

- require Python >=3.11 for this validator only;
- make TOML validation capability-gated;
- add a dependency such as `tomli` for older runtimes;
- defer TOML enforcement.

The documentation also warns that malicious TOML can consume considerable CPU/memory, reinforcing the need for size bounds.

### 9.3 XML - defer hard validation

Python's XML documentation warns about maliciously constructed XML and resource/security hazards in XML parsing, with behavior depending in part on the Expat version/configuration.

Official source:

https://docs.python.org/3/library/xml.html

A repository preview endpoint processes model/user-provided candidate content, so XML should not become a hard synchronous parser gate casually.

Initial recommendation:

```text
XML syntax validator: defer pending parser/security choice and explicit size/resource policy
```

### 9.4 YAML - still deferred

Iteration 03 did not find enough evidence to make YAML a hard blocker. Soma already depends on PyYAML, but YAML version/tag/construction behavior and repository-specific schemas are materially less uniform than Python/JSON syntax validity.

A future YAML iteration should distinguish parser syntax from object construction and custom-tag semantics.

## 10. Preview-bundle provenance inspection

Current `_write_preview_bundle` writes bundle version 3.

The manifest contains:

```text
patch_id
bundle_version
repo_fingerprint
git_head_at_preview
status
operations[]
errors
warnings
commit metadata
```

Each payload operation records a descriptor including:

```text
payload file/chunks
payload_sha256
payload_size_bytes
```

This is a convenient place for validation and repair provenance because it already follows the candidate through preview/apply lifecycle.

No SQL/database schema migration is required merely to add JSON manifest fields.

## 11. Important integrity correction: the manifest is not an external trust anchor

Iteration 01/02 described the candidate as hash-bound, which is correct relative to the preview manifest. Iteration 03 clarifies the exact strength of that statement.

Existing test evidence in `tests/test_repo_writer.py` deliberately performs this sequence:

```text
1. create a managed preview;
2. replace payload_0.bin with different bytes;
3. update manifest.operations[0].payload_sha256 to match;
4. update payload size;
5. apply previewed change;
6. assert the changed bytes are accepted exactly.
```

This means current apply protects against:

```text
payload bytes inconsistent with manifest descriptor
```

but does not provide an external cryptographic anchor against:

```text
coordinated modification of both payload and manifest by a party able to write managed patch storage
```

This is not necessarily a defect under Soma's local threat model. It matters for terminology and repair provenance design.

Do not call a repair record "cryptographically immutable" merely because it contains hashes inside the same editable manifest.

## 12. Provenance rollout options

### Option A - detection/suggestion only, bundle v3 extension

For the first conservative activation, candidate validation metadata can be stored as extra manifest JSON fields while a malformed preview remains `preview_failed` / non-applicable.

Current apply already refuses `preview_failed` previews.

A conceptual record:

```text
candidate_validation:
  validator: python_compile
  interpreter: 3.12.x
  baseline_status: valid
  candidate_status: invalid
  error_line: ...

repair_proposal:
  rule_id: repo_patch_outer_envelope_suffix_v1
  rule_schema_hash: ...
  matched_field: view
  original_candidate_sha256: ...
  proposed_candidate_sha256: ...
  delete_start: ...
  delete_end: ...
  deleted_bytes_sha256: ...
  boundary_gate: logical_newline
  disposition: repair_available
```

Because apply cannot execute a failed preview, old apply behavior cannot accidentally bypass the proposal decision.

### Option B - future auto-repair, stronger bundle semantics

If preview ever automatically selects a repaired payload, a new bundle format/version is cleaner.

Reasons:

- apply should explicitly understand that the payload was transformed;
- apply should verify repaired-candidate hash and repair record consistency;
- old apply code should not silently ignore authoritative repair metadata;
- provenance semantics become part of the bundle contract rather than advisory JSON.

A future `bundle_version = 4` is therefore preferable to silently changing the meaning of version 3.

This is a file-format/version change, not necessarily a database-schema migration.

## 13. What provenance can realistically preserve

The writer should preserve what it actually knows, not invent a raw-wire history.

Recommended identities:

```text
canonical_structured_patch_sha256
original_candidate_sha256
repaired_candidate_sha256
repair_rule_id
repair_rule_version
public_schema_hash / capability identity
matched_outer_field
deletion byte range
deleted_bytes_sha256
validator/runtime identity
boundary proof result
final disposition
```

If the exact deleted transport text is useful for audit, it can be retained in a separately bounded opaque repair artifact or a tightly bounded manifest field. Do not allow an unbounded leaked argument tail to bloat the managed bundle.

The original raw MCP/JSON serialization should not be claimed unless an upstream layer explicitly persists it.

## 14. Performance microbenchmark - indicative only

A local in-memory microbenchmark outside Soma measured `compile()` plus `tokenize` on generated valid Python of increasing size. This was **not** executed on the Soma Windows host and is not an acceptance benchmark.

Approximate median timings observed:

```text
~7.5 KB:    compile  ~1 ms, tokenize  ~1 ms
~39 KB:     compile  ~6 ms, tokenize  ~7 ms
~159 KB:    compile ~26 ms, tokenize ~25 ms
~409 KB:    compile ~67 ms, tokenize ~126 ms
~829 KB:    compile ~156 ms, tokenize ~252 ms
~1.67 MB:   compile ~364 ms, tokenize ~493 ms
```

Interpretation:

- candidate-only validation is inexpensive for ordinary source files;
- tokenization cost becomes noticeable for very large candidates;
- modified-file size is not currently capped by the 200 KB create limit;
- preview can target up to 50 files;
- therefore a final implementation plan needs explicit per-file/total validation budgets rather than assuming parser cost is free.

A Soma-host benchmark on representative real files remains required before final plan acceptance.

## 15. Candidate validator resource policy

The future validator should be bounded independently from patch-size accounting.

Potential policy dimensions:

```text
max candidate bytes eligible for strict synchronous validation
max total candidate bytes per preview
max validator wall-clock budget
max number of validated files
resource exception -> validation_unavailable, not service crash
```

Do not reuse `changed_bytes` as a proxy for candidate parse cost. A one-byte edit can target a very large file.

This is an important distinction not captured by Iteration 01.

## 16. Refined result model

Iteration 03 reinforces the need to separate three concepts:

```text
candidate validity
transport-corruption detection
repair eligibility
```

Example:

```text
candidate_validation:
  state: invalid_regression

corruption_detection:
  kind: outer_preview_envelope_suffix
  confidence: mechanical

repair:
  deletion_candidate_count: 1
  repaired_validation: valid
  boundary_proof: logical_newline
  disposition: repair_available | tier_a_eligible | blocked_boundary_hazard
```

Incident A:

```text
candidate invalid
corruption strongly detected
repair compiles
boundary proof = NL / fail
=> blocked boundary hazard
```

Incident B:

```text
candidate invalid
corruption strongly detected
repair compiles
boundary proof = NEWLINE / pass
=> future Tier-A candidate
```

## 17. Public patch primitive implications

### exact_text

Best initial transport-repair research surface.

The replacement `new_text` is explicit, and Soma can prove that a suspicious match is a suffix of that payload rather than arbitrary file interior.

### line_range

Also favorable. Replacement `new_text` is explicit and the selected old range already has expected text/hash evidence.

### python_ast

Good candidate for final-file validation. The old source is already parsed to find the target. The resulting candidate should be compiled separately.

A Tier-A transport deletion can only operate on the supplied replacement suffix; AST logic must not synthesize punctuation or rewrite the body.

### unified_diff

Full candidate validation is useful, but repair provenance is harder because the caller's authored artifact is the diff while the final candidate is materialized text.

Keep automatic repair deferred for unified diff until a clean mapping/provenance model is researched.

### create_file

Validation useful; baseline absent; strict blocking and automatic repair require separate policy.

## 18. Current strongest safe first implementation

If implementation were authorized today, Iteration 03 still recommends:

```text
Phase 1
------
modified .py candidate compile validation
+ baseline comparison
+ schema-bound transport suffix detection
+ repair proposal
+ exact before/after hashes and byte range
+ malformed preview remains non-applicable
+ create-file warnings / strong-leak blocking only
+ no automatic repair
```

The new `NEWLINE` proof should be implemented as **telemetry/tested eligibility logic**, not immediately used to mutate source automatically.

That produces real operating data on how often Tier-A conditions would have passed without risking silent repair.

## 19. Why not activate Tier A yet?

The Python boundary question is much closer to solved, but several evidence gaps remain:

1. only two real transport-corruption incidents are in the corpus;
2. the exact outer-envelope detector needs testing across more serialization/whitespace variants;
3. legitimate invalid-source fixtures across other repositories have not been surveyed;
4. unified-diff mapping remains unresolved;
5. create-file transport leak shape has no real example;
6. runtime/target-version policy is not finalized;
7. validator resource budgets need Soma-host measurements;
8. bundle-v3 versus v4 provenance rollout needs an explicit compatibility decision;
9. non-Python auto-repair boundaries have not been proven;
10. no property-based/fuzz campaign has yet attacked the logical-line gate.

A solid final plan should resolve or explicitly defer each of those rather than hide them.

## 20. Confirmed bugs

No Soma contract bug is confirmed in Iteration 03.

One research clarification is important:

- current managed payload hashes are integrity checks relative to their manifest;
- the manifest is not an independently anchored immutable record.

This is a property of the current design and test contract, not automatically a security defect.

## 21. Proposed Iteration 04

Continue research before final planning.

Recommended next focus:

1. Property-based/adversarial fuzzing of the Python `NEWLINE` boundary gate.
2. Generate schema-bound corruption variants with whitespace, escaped text, multiple outer fields and truncated outer envelopes.
3. Survey historical Soma runs for any additional parser failures after successful `repo_apply` beyond the two known incidents.
4. Search a broader legitimate-source corpus if available for exact schema-bound signatures.
5. Define validator applicability/configuration, especially Python runtime/version behavior.
6. Run bounded Soma-host performance measurements without holding the repository lock for long-running scans.
7. Decide bundle-v3 advisory metadata vs bundle-v4 authoritative repair provenance.
8. Research unified-diff repair mapping or explicitly exclude it from Tier A.
9. Research `create_file` leak signatures separately rather than infer them from patch operations.
10. Evaluate YAML parser-only validation and custom-tag false positives.

## 22. Iteration 03 conclusion

Iteration 02 showed why "delete garbage and compile" is unsafe.

Iteration 03 finds a compact language-defined condition that blocks the discovered semantic trap:

```text
repair must land at a Python logical-line boundary (`NEWLINE`)
```

not merely at a physical newline.

That distinction correctly rejects the real `WorkPackage` adjacent-literal case because an open list turns its newline into `NL`. It accepts the complete assertion boundary from the real `view` leak.

The 35-case adversarial matrix supports the rule, but is not enough to turn it into automatic mutation authority.

The research is now converging. The likely eventual architecture is no longer vague:

```text
candidate validation
    + schema-bound transport detector
    + deletion-only repair proposal
    + Python logical-line boundary proof
    + hash/provenance record
    + strict resource budget
    + apply remains opaque/dumb
```

The remaining work is primarily evidence hardening, rollout/provenance compatibility, and policy scoping rather than discovering a completely different architecture.
