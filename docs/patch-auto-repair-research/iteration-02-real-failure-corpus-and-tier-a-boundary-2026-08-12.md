# Patch Auto-Repair Research - Iteration 02

Date: 2026-08-12
Status: research only
Repository: Soma
Lane observed: `lane/memory-integration-foundation-1`
Final repository snapshot used for this journal: `4168d7493f592bf7d3a28f16b0770e9697d83260`

## Scope and discipline

Iteration 01 established that Soma already materializes a complete per-file patch candidate before creating an applicable managed preview, and that candidate validation can be inserted before preview bundle creation without changing repository-apply authority.

Iteration 02 moves from architectural feasibility to empirical policy design. Its primary goals are:

1. recover the two real malformed-payload incidents from Soma's durable evidence rather than reason from a hypothetical example;
2. identify what the incidents actually have in common;
3. determine whether a deterministic deletion-only repair would have been safe in both cases;
4. find counterexamples where syntax recovery is not sufficient to prove semantic preservation;
5. measure a narrow false-positive control against the current Soma Python source tree;
6. refine the conditions under which a future Tier-A repair could ever be considered mechanically proven.

No production source, schema, runtime, connector state, or repository behavior was changed by this research. The only intended repository change is this journal. There is no restart, connector refresh, commit, or push.

The active Agent/Worker implementation lane continued moving while this research was running. At the final status check, HEAD was `4168d7493f592bf7d3a28f16b0770e9697d83260`, `soma/tasks/models.py` had unrelated unstaged work, and the following unrelated untracked files remained present:

- `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md`
- `docs/patch-auto-repair-research/iteration-01-current-patch-pipeline-and-repair-feasibility-2026-08-12.md`

Those files and the unstaged Agent/Worker change were not modified by this iteration.

## Executive finding

Iteration 02 confirms that the motivating failure class is real, recoverable from durable evidence, and mechanically distinctive. It also finds a critical counterexample to a naive auto-repair rule.

Two independent malformed patch incidents were recovered from the same active implementation window:

```text
Incident A
successful repo_apply
    -> malformed soma/company_kernel/__init__.py
    -> Python SyntaxError
    -> one-file correction

Incident B
successful repo_apply
    -> malformed tests/test_company_kernel_schema_models.py
    -> Python SyntaxError
    -> one-file correction
    -> tests pass
```

Both leaked fragments have the same transport shape:

```text
}] , "<field belonging to RepoPatchPreview outside operations>" : ...
```

The concrete outer fields observed were:

- `commit_title`
- `view`

The current `RepoPatchPreview` schema declares the fields after `operations` as:

- `commit_title`
- `commit_description`
- `view`
- `response_budget_bytes`

This gives Soma a much stronger possible detector than generic searches for words such as `new_text` or `expected_sha256`: a versioned rule can recognize a serialized closure of the patch operation/operations array followed immediately by a field that belongs to the outer preview envelope.

However, automatic deletion of that suffix is **not mechanically safe in every real incident**.

For Incident A, deleting the leaked transport suffix makes the file compile, but it also removes the comma separating two adjacent Python string literals. Python legally concatenates adjacent literals during compilation. The resulting `__all__` entry becomes:

```text
"WorkPackageWorkPackageAttempt"
```

instead of two entries:

```text
"WorkPackage",
"WorkPackageAttempt",
```

Therefore this candidate:

```text
original candidate invalid
+ exact transport suffix identified
+ delete suffix
+ repaired candidate compiles
```

is still insufficient proof for automatic repair.

Iteration 02 therefore keeps the first implementation recommendation conservative: detect and block/suggest first. It also refines what a later Tier-A proof would have to establish beyond syntax recovery.

## 1. Durable failure corpus

### 1.1 Incident A - `commit_title` transport leakage into `__init__.py`

#### Malformed apply

Durable apply run:

`20260812T035657Z_repo_apply_330c61c4`

Managed patch:

`20260812T035645Z_patch_8d9c02b6`

Git HEAD at apply:

`fbc7b60fc78f0b1768d1053494e9f6caa073028b`

Files changed by the apply:

- `soma/company_kernel/models.py`
- `soma/company_kernel/schema.py`
- `soma/company_kernel/store.py`
- `soma/company_kernel/__init__.py`

The resulting malformed `soma/company_kernel/__init__.py` had SHA-256:

`46393511e89112e09879e0cea16e41fc2708a2d7d54ce706057efe520d55def6`

The apply itself completed successfully under Soma's current contract. Patch status shows no validation error because candidate syntax is not currently part of repository preview validation.

#### Parser evidence

The subsequent validation run:

`20260812T035903Z_executable_profile_71df6035`

failed during Python import/pytest collection. Protected durable stdout records:

```text
File "D:\Github\Soma\soma\company_kernel\__init__.py", line 97
  "WorkPackage"}],"commit_title":"G1.2 additive Company Kernel graph schema v2
               ^
SyntaxError: closing parenthesis '}' does not match opening parenthesis '[' on line 60
```

This is direct evidence of outer patch-control syntax inside source content, not an inference from later test behavior.

#### Correction

Correction apply run:

`20260812T035936Z_repo_apply_952dddf1`

Correction patch:

`20260812T035928Z_patch_c58c7443`

Changed only:

`soma/company_kernel/__init__.py`

Corrected file SHA-256:

`101148bb0f814c52c2c3f3af8d8fe1731fb15e30d89696f74b9c2b7cc0cb30c1`

The current clean file still has that exact SHA-256. Around the repaired location it contains separate `__all__` entries:

```text
"SettledSatisfactionV1",
"WorkPackage",
"WorkPackageAttempt",
"canonical_hash",
```

The accepted `fbc7b60... -> b6c0d99...` commit range independently confirms the intended two-entry structure.

### 1.2 Incident B - `view` transport leakage into a test file

#### Malformed apply

Durable apply run:

`20260812T040558Z_repo_apply_b6f859df`

Managed patch:

`20260812T040551Z_patch_44baa85a`

Git HEAD at apply:

`b6c0d99ed267072c4853aa5b1b25c798632777ae`

Files changed:

- `soma/company_kernel/schema.py`
- `soma/company_kernel/models.py`
- `tests/test_company_kernel_schema_models.py`

The malformed test-file result had SHA-256:

`d091e15e5abde17efbde4218874a0181d7ede4a6f8da023df2b7e18150420d33`

Again, the managed repository apply itself completed successfully under the current patch contract.

#### Parser evidence

The immediate validation run:

`20260812T040606Z_executable_profile_002fd6f0`

failed during pytest collection with:

```text
File "D:\Github\Soma\tests\test_company_kernel_schema_models.py", line 380
  assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"}],"view":"full
                                                                     ^
SyntaxError: unmatched '}'
```

This is a second independent outer-envelope leak, with a different leaked field.

#### Correction

Correction apply run:

`20260812T040647Z_repo_apply_54073656`

Correction patch:

`20260812T040640Z_patch_8f5739ed`

Changed only:

`tests/test_company_kernel_schema_models.py`

Corrected result SHA-256:

`3321a77f002e374c924e1e8ef2519bffccc0f3154f4fa3922d9e477a518864f5`

The following validation run:

`20260812T040655Z_executable_profile_7919ecf7`

passed 39 tests.

The accepted `b6c0d99... -> 888b105...` commit range shows that the intended source line remained:

```text
assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
```

and that the legitimate change in this region was the preceding `migrated_package` assertion block. For this incident, deleting the leaked transport suffix is consistent with the accepted source.

## 2. The shared transport signature is stronger than Iteration 01 assumed

Iteration 01 intentionally did not freeze a literal detector because the exact malformed bytes had not yet been recovered.

Iteration 02 can now state a concrete observed family:

```text
}] , "commit_title" : ...
}] , "view" : ...
```

Whitespace/serialization details may vary, so a conceptual recognizer is:

```text
}\]\s*,\s*"(commit_title|commit_description|view|response_budget_bytes)"\s*:
```

The important feature is not the regex itself. The important feature is where the field names come from: they are outer `RepoPatchPreview` fields, not patch-operation source fields.

Current source evidence in `soma/gateway_models.py` declares:

```text
operation
repo_name
operations
commit_title
commit_description
view
response_budget_bytes
```

A production rule should therefore be schema-derived or schema-version-bound rather than hand-maintained as a generic list of suspicious words.

### Why `expected_sha256` should not be mandatory evidence

Iteration 01 proposed that a Tier-A leak ideally echo operation identity such as the exact `expected_sha256`.

The real corpus shows that this would be too strict as a required condition. Neither recovered parser line needs an `expected_sha256` echo to identify the transport boundary. Incident A contains `commit_title`; Incident B contains `view`.

More importantly, the outer field can be entirely swallowed into `new_text`, so the successfully parsed outer request may not retain the leaked field's intended value at all. The durable apply record for the malformed patch does not provide a reliable reconstructed original model payload; it carries the opaque `patch_id` by design.

The better identity anchor is therefore:

- structural position at the replacement boundary;
- exact outer-envelope field identity;
- candidate syntax regression;
- one unique candidate repair;
- additional lexical/structural proof that deletion does not join source tokens or alter surrounding source structure.

## 3. Critical counterexample: syntax recovery is not semantic proof

A minimal reconstruction of Incident A demonstrates the problem:

```python
__all__ = [
    "SettledSatisfactionV1",
    "WorkPackage"}],"commit_title":"G1.2 additive Company Kernel graph schema v2
    "WorkPackageAttempt",
    "canonical_hash",
]
```

The malformed version fails compilation.

A naive suffix-only deletion yields:

```python
__all__ = [
    "SettledSatisfactionV1",
    "WorkPackage"
    "WorkPackageAttempt",
    "canonical_hash",
]
```

This compiles successfully.

But Python adjacent string literal concatenation makes the actual list equivalent to:

```text
[
  "SettledSatisfactionV1",
  "WorkPackageWorkPackageAttempt",
  "canonical_hash"
]
```

The true repaired source instead contains a comma:

```python
__all__ = [
    "SettledSatisfactionV1",
    "WorkPackage",
    "WorkPackageAttempt",
    "canonical_hash",
]
```

Python's language reference explicitly permits adjacent string/bytes literals to concatenate at compile time.

Primary source:

https://docs.python.org/3/reference/lexical_analysis.html

https://docs.python.org/3/reference/expressions.html

### Consequence

The following rule is rejected:

```text
candidate invalid
+ known transport suffix found
+ delete exact suffix
+ candidate compiles
=> auto-repair
```

It would have silently produced wrong source in one of the two real incidents.

This is the most important Iteration 02 finding.

## 4. Refined Python validation model

### 4.1 `compile()` remains the correct first validity gate

For a complete `.py` candidate, use:

```python
compile(candidate, filename, "exec", dont_inherit=True)
```

Python documents that `compile()` raises `SyntaxError` for invalid source and that `dont_inherit` prevents surrounding future/compiler flags from implicitly affecting compilation.

Primary source:

https://docs.python.org/3/library/functions.html#compile

This remains stronger than relying only on `ast.parse()` for final-candidate acceptance.

### 4.2 Token analysis belongs after successful candidate compilation

Python's `tokenize` documentation explicitly warns that tokenizer behavior is undefined for syntactically invalid Python.

Primary source:

https://docs.python.org/3/library/tokenize.html

Therefore a future rule should not depend on tokenizing the original invalid candidate as authoritative evidence.

A safer order is:

```text
compile original candidate
    -> invalid
identify schema-bound transport suffix
construct one deletion candidate
compile deletion candidate
    -> valid
then tokenize/analyze repaired candidate boundary
```

### 4.3 Boundary-safety proof is required

The Incident A counterexample suggests an additional mechanical proof layer.

At minimum, an automatic deletion candidate must prove that deleting the transport suffix does not cause two independent source tokens to become a different legal source construct.

One immediately necessary guard for Python is:

```text
STRING token before cut
+ STRING token after cut
=> do not auto-repair
```

because adjacent literals can concatenate.

More generally, future research should formalize unsafe adjacency classes, including at least:

- adjacent identifiers/names that can merge lexically;
- numeric literal adjacency;
- operators/delimiters whose deletion changes grouping;
- string/f-string/bytes literal adjacency;
- implicit statement continuation inside `()`, `[]`, or `{}`;
- indentation or line-continuation effects;
- comments/backslashes crossing the repair boundary.

A particularly conservative first Tier-A rule could require the cut to occur at statement-safe top-level structure, for example after a complete logical line with no open bracket context. Incident B appears compatible with that shape; Incident A does not.

This remains a research hypothesis, not an implementation contract.

## 5. Real corpus classification under the refined rule

### Incident A

Evidence:

- baseline source was valid Python before the malformed apply;
- malformed candidate failed compilation;
- strong schema-bound `}],"commit_title":` leak was present;
- deleting that leak can produce compilable Python;
- deletion-only joins adjacent string literals and changes `__all__` semantics.

Classification:

`repair_detected_but_not_mechanically_proven`

Recommended behavior:

`blocked_ambiguous_repair` or equivalent repair suggestion requiring controller resubmission.

### Incident B

Evidence:

- baseline source was valid Python;
- malformed candidate failed compilation;
- strong schema-bound `}],"view":` leak was present;
- deletion-only yields valid Python;
- accepted later source confirms the surrounding assertion line is otherwise unchanged;
- the repair boundary is at the end of a complete assertion statement, not between adjacent string literals.

Classification:

`candidate_for_future_tier_a_rule`

Recommended current behavior:

still `repair_available`, not automatic repair, until the boundary-safety proof is generalized and tested against a larger corpus.

## 6. Mechanical vs semantic failure boundary demonstrated by the same history

The durable run sequence gives an unusually clean demonstration of Soma's intended architectural boundary.

After Incident A's syntax corruption was corrected, the next test run:

`20260812T035944Z_executable_profile_13185e2b`

no longer failed to parse. It ran 39 tests and produced:

```text
1 failed, 38 passed
```

The remaining failure was an ordinary assertion mismatch:

```text
target_schema_version actual 2
expected 1
```

That is not transport corruption. It is implementation/test semantics.

So the same real workflow naturally separates:

```text
SyntaxError caused by leaked tool envelope
    -> candidate validation / patch infrastructure may detect

ordinary assertion failure after syntax is fixed
    -> controller/reasoning layer must decide
```

This supports the architecture boundary rather than merely assuming it.

## 7. Narrow false-positive control against current Soma Python source

A bounded read-only search was run against current Python source under:

- `soma/`: 231 `.py` files examined
- `tests/`: 170 `.py` files examined

For each tree, exact searches were performed for the observed serialization shape using all four post-`operations` outer fields:

```text
}],"commit_title"
}],"commit_description"
}],"view"
}],"response_budget_bytes"
```

Result:

```text
0 hits in soma/
0 hits in tests/
```

This is not proof of zero false positives in all repositories. It is useful local evidence that the schema-bound lexical signature is rare in legitimate Soma Python source, even though the repository contains extensive tests and gateway-related code.

### What this control does not prove

It does not prove:

- the signature cannot legitimately appear in a string/comment/fixture in another project;
- whitespace variants are absent unless searched separately;
- other languages have the same risk profile;
- a regex match is sufficient to authorize repair;
- all Soma Python files are baseline-valid under every supported Python version.

The signature should remain one conjunct in a proof, not the whole proof.

## 8. Repository-wide compile scan experiment was deliberately abandoned

An initial attempt to compile-scan the entire worktree via a durable PowerShell run was too broad and held Soma's repository lock while the Agent/Worker lane was active.

The exact run was cancelled once this became clear:

`20260812T044321Z_executable_profile_8b9bd6d2`

Cancellation confirmed the child/worker were terminated. The scan had no intended source writes.

A prior quoting-corrupted scan command also failed before inspection and reported no changed files:

`20260812T044304Z_executable_profile_37b3190f`

Research process conclusion: future empirical source scans in this track should use bounded `repo_query` operations or explicitly non-locking inspection machinery. A research experiment must not compete with the active implementation lane for repository ownership merely to gather convenience statistics.

The absence of a full compile census is therefore an explicit evidence gap, not silently inferred away.

## 9. Provenance finding: current apply evidence cannot reconstruct original model patch intent

The public apply path intentionally receives only:

```text
operation = previewed_change
patch_id
commit_mode
repo_name
```

`run_query(input)` for the malformed apply confirms that durable apply input preserves this opaque apply contract rather than resending model-authored patch operations.

This is correct for authority and integrity, but it has a consequence for future repair auditing: if preview transforms a candidate, the repair provenance must be explicitly persisted at preview time.

A later investigator should not need to infer the original candidate from a subsequent `SyntaxError` the way this iteration did.

A future repair record should preserve at least:

```text
original_structured_patch_hash
original_candidate_hash
repair_rule_id
repair_rule_version
schema/public capability identity
matched_transport_field
matched_candidate_byte_range
proposed_deleted_byte_range
repaired_candidate_hash
validation_before
validation_after
boundary_safety_checks
repair_disposition
```

If auto-repair is ever enabled, also record:

```text
auto_repair_allowed
actual_candidate_selected
```

The exact original raw MCP/JSON wire bytes should not be claimed unless Soma actually has them. A canonical structured-operation hash is more honest than pretending to preserve a serialization layer that `repo_writer` never received.

## 10. Refined detection classes

### Class 1 - schema-bound transport-envelope leak

Strong evidence:

- suspicious fragment is inside one replacement payload near its boundary;
- fragment closes operation/operations serialization and introduces an outer `RepoPatchPreview` field;
- field identity is derived from the active preview schema/rule version;
- baseline candidate was valid under selected validator;
- patched candidate newly fails validation near the edit/leak location.

Result:

high-confidence mechanical corruption detection.

This still does not automatically imply a safe repair.

### Class 2 - generic syntax regression near edit

Evidence:

- baseline file compiles;
- candidate does not;
- error is in or near edited range;
- no exact transport-envelope signature is proven.

Result:

`blocked_invalid_candidate` or warning according to policy; no automatic rewrite.

### Class 3 - candidate remains syntactically valid but suspicious text exists

Examples:

- transport-looking text in a string/comment/fixture;
- a leaked fragment happens to form valid Python.

Result:

warning/detection telemetry at most unless additional exact transport provenance proves corruption. Do not silently delete valid source.

### Class 4 - post-syntax semantic/code failure

Examples:

- assertion mismatch;
- failing tests;
- wrong API behavior;
- type mismatch requiring reasoning;
- architecture disagreement.

Result:

never repair in repository patch infrastructure.

## 11. Revised Tier-A proof requirements

Iteration 01's proposed Tier-A conditions must be strengthened.

A future Python deletion-only Tier-A rule should require all of the following, not merely most of them:

1. **Applicable validator:** the target is a complete Python source file for which strict candidate validation is enabled.
2. **Valid baseline:** current pre-edit source validates under the same compiler/runtime policy.
3. **New regression:** original post-edit candidate fails `compile(..., "exec", dont_inherit=True)`.
4. **Schema-bound leak:** exactly one strong transport-envelope suffix is identified at a replacement boundary.
5. **Outer-only identity:** leaked key is an outer preview field, not merely a common source token.
6. **Error locality:** syntax failure points into, or immediately after, the edited/leaked region.
7. **Single mechanical edit:** proposed repair is deletion of exactly the identified transport suffix; no inserted punctuation, quote, comma, bracket, indentation, or generated source.
8. **Unique repair:** there is exactly one admissible deletion boundary/candidate under the rule.
9. **Revalidation:** repaired candidate compiles successfully.
10. **Lexical boundary safety:** deletion does not merge adjacent source tokens into a different legal construct.
11. **Structural boundary safety:** deletion does not alter bracket/statement continuation or indentation structure across the cut.
12. **No hidden normalization:** bytes outside the recorded deletion range remain unchanged except already-authorized newline handling.
13. **Complete provenance:** original/repaired candidate hashes, exact byte range, validator results, rule version and schema identity are persisted.
14. **Apply remains dumb:** apply writes only the already-bound repaired candidate and never rediscovers/recomputes repair.

If any condition is not mechanically demonstrated, automatic repair is not allowed.

## 12. Why automatic punctuation insertion remains out of Tier A

Incident A might tempt an implementation to say:

```text
I removed the leaked suffix and Python now joins two strings;
therefore insert the missing comma.
```

Do not do this in Tier A.

Adding a comma is not deletion of transport corruption. It is synthesis of source that was not present in the accepted replacement prefix. Even if the human/controller probably intended it, that crosses from transport cleanup into reconstructing code intent.

For Incident A the correct infrastructure behavior is:

```text
transport corruption detected
one deletion candidate found
candidate compiles but boundary safety fails
repair suggestion/block
controller supplies corrected patch
```

That boundary is clean and auditable.

## 13. Interaction with patch types after the real corpus

### `exact_text`

Best initial detection surface because:

- replacement bytes are explicit;
- source anchor is unique;
- leaked suffix can be localized to `new_text`;
- unchanged prefix/suffix can be proven byte-for-byte.

### `line_range`

Also favorable because the replacement extent is explicit and the old range is already hash/text-bound.

### `python_ast`

High value for candidate validation. Current implementation parses the old source to find the structural target but does not compile the full resulting candidate. The same post-materialization validator should operate on the final candidate.

Do not use AST structure to invent missing punctuation inside `new_text`.

### `unified_diff`

Candidate validation is useful, but automatic repair is less attractive initially because a candidate-level deletion must be mapped back to a diff representation if the original operation itself is to be repaired. Since Soma already persists the final opaque candidate, detection can still block before bundle acceptance, but Tier-A auto-repair for diff payloads should remain deferred.

## 14. Python version and encoding constraints

Current Soma project metadata declares:

```text
requires-python = ">=3.10"
```

The recovered validation runs used Python 3.12.

A candidate compiler running under one interpreter does not perfectly prove compatibility with every Python version permitted by a broad project range. Therefore future validation policy should distinguish:

- syntax regression relative to the current file under the same interpreter;
- repository target/runtime compatibility.

The first is useful for transport-error detection. The second is a broader project/toolchain concern.

Also note that current writer code reads text with UTF-8 decoding using replacement on decode errors in parts of the patch path. A future strict syntax validator should not silently convert encoding ambiguity into repair authority. Non-UTF-8 or undecodable source should produce validation-not-applicable/warning unless encoding handling is explicitly designed.

## 15. Result vocabulary refinement

Iteration 02 suggests separating **detection confidence** from **repair disposition** rather than compressing both into one state.

Example conceptual record:

```text
detection:
  kind: transport_envelope_suffix_leak
  confidence: mechanical

repair:
  candidate_count: 1
  disposition: blocked_boundary_hazard | repair_available | auto_repair_eligible
```

Public result vocabulary can still remain compact:

- `valid`
- `valid_with_warning`
- `repair_available`
- `blocked_invalid_candidate`
- `blocked_ambiguous_repair`
- `validation_not_applicable`
- future `auto_repaired`

But internally the reason why a strong detection is not auto-repairable should be explicit.

Incident A is the canonical example:

```text
strong corruption detection
!=
safe automatic repair
```

## 16. Tests now known to be mandatory

The real incidents should become permanent regression fixtures if implementation is authorized.

### Exact incident fixtures

1. Reconstruct Incident A `commit_title` leak and assert:
   - original candidate invalid;
   - strong leak detected;
   - deletion candidate compiles;
   - boundary-safety guard detects adjacent-string hazard;
   - no automatic repair is allowed.

2. Reconstruct Incident B `view` leak and assert:
   - original candidate invalid;
   - strong leak detected;
   - exact suffix deletion candidate compiles;
   - no token-join/boundary hazard;
   - current first-phase policy still returns repair proposal rather than applying automatically.

### Outer-field variants

Test all current post-operations fields:

- `commit_title`
- `commit_description`
- `view`
- `response_budget_bytes`

Include whitespace and compact JSON variants without broadening into arbitrary field-name matching.

### Negative lexical cases

Must include legitimate source containing the same text inside:

- string literal;
- bytes literal;
- comment;
- docstring;
- test fixture;
- JSON example embedded in Python;
- generated-code test data.

### Boundary hazards

At minimum:

- STRING + STRING implicit concatenation;
- NAME + NAME / lexical merge cases;
- numeric literals;
- operator adjacency;
- bracket continuation;
- backslash continuation;
- comment boundary;
- indentation-sensitive boundary;
- f-string/plain-string adjacency.

### Baseline/candidate matrix

- baseline valid -> candidate valid;
- baseline valid -> candidate invalid;
- baseline invalid -> candidate invalid;
- baseline invalid -> candidate valid;
- validator unavailable;
- runtime-version-sensitive source;
- undecodable/non-UTF-8 source.

### Pipeline invariants

Retain all Iteration 01 requirements:

- no worktree mutation for blocked preview;
- invalid preview cannot apply;
- apply never reruns repair;
- opaque payload tamper checks remain intact;
- stale hash/repository binding remain intact;
- idempotence remains intact;
- newline preservation remains intact;
- rollback/revert remain intact;
- writer remains model-free.

## 17. What the empirical data supports now

### Supported with high confidence

- The motivating class occurred at least twice in the recovered G1 implementation window.
- Both events were accepted by current patch mechanics because current mechanics do not validate final Python syntax.
- Both events contain recognizable outer preview-envelope fragments inside source.
- The two events use different outer fields, so this is a family rather than one literal typo.
- Full-candidate Python compilation before preview acceptance would have caught both before worktree mutation.
- A schema-bound detector is materially stronger than generic suspicious-token detection.
- Pure suffix deletion would have matched the eventual accepted source for Incident B.
- Pure suffix deletion would **not** have matched the eventual accepted source semantics for Incident A even though the deletion candidate compiles.
- Therefore parse/compile success after deletion is not enough to authorize automatic repair.
- Semantic test failures remain cleanly separable from transport/syntax failures.

### Not yet supported strongly enough

- that any Tier-A auto-repair should be activated now;
- that bracket-depth/top-level-line constraints are sufficient for all safe Python boundary repairs;
- that the observed four outer fields cover future schemas automatically;
- that the rule generalizes to non-Python languages;
- that the same false-positive rate holds outside Soma;
- that current runtime Python is always the correct validator for every configured repository;
- that complete repository-wide compile scanning belongs in synchronous preview;
- that `create_file` should use identical policy without exceptions;
- that diff-payload repair should be attempted at all.

## 18. Rejected ideas after Iteration 02

### Reject: compile success after repair proves intent preservation

Incident A disproves it.

### Reject: repair missing punctuation after deleting leaked syntax

That synthesizes source and crosses the deterministic transport-repair boundary.

### Reject: generic `new_text` / `expected_sha256` token matching

The real incidents expose a stronger schema-bound signature. Generic tokens have a much larger legitimate-source surface.

### Reject: require exact leaked outer value to survive elsewhere in request

A malformed boundary can swallow the only copy of the outer field/value into replacement text.

### Reject: tokenize invalid candidate as authoritative proof

Python documents tokenizer behavior as undefined for invalid Python. Token/boundary analysis should run on a successfully compiled repair candidate.

### Reject: broad whole-worktree validation runs during preview/research

The abandoned scan demonstrated unnecessary repository-lock contention. Candidate validation should be scoped to changed candidate files and bounded by existing patch limits.

## 19. Confirmed bugs

No Soma contract bug is confirmed.

Both malformed applications remain correctly classified as `implementation-friction` under current behavior: Soma wrote the exact preview-bound content it was instructed to write.

The research establishes a missing defensive capability, not a violation of the existing patch contract.

## 20. Revised recommendation after Iteration 02

Do not move to implementation planning yet.

The evidence is now strong enough to specify a high-confidence **detector**, but not yet strong enough to specify a generally safe **auto-repairer**.

If implementation were forced today, the safe scope would still be:

```text
complete candidate validation
+ schema-bound transport-leak detection
+ exact repair proposal/provenance
+ block malformed preview from being applicable
- no automatic source mutation
```

The future auto-repair lane is now narrower:

```text
only exact deletion of proven transport bytes
+ unique repair
+ successful candidate validation
+ lexical boundary safety
+ structural boundary safety
+ complete provenance
```

Incident B is a candidate positive fixture for that future lane.

Incident A is a mandatory negative fixture proving why the boundary checks exist.

## 21. Proposed Iteration 03 research focus

The next iteration should continue gathering data rather than drafting the final implementation plan.

Recommended focus:

1. Formalize Python repair-boundary safety using valid repaired token streams and parser structure.
2. Build a synthetic adversarial matrix around the exact schema-bound leak family.
3. Test whether a conservative boundary rule can correctly classify Incident A as unsafe and Incident B as potentially safe without source-specific knowledge.
4. Examine complete-file validation policy for `create_file` as well as the four patch primitives.
5. Evaluate JSON/TOML/XML validation separately; do not assume Python policy transfers directly.
6. Investigate YAML only as an optional/deferred validator because parser/schema behavior differs materially.
7. Determine how repair provenance should be hash-bound into the existing preview bundle without a schema/database migration if possible.
8. Determine whether repository configuration needs an explicit validator policy/version target.
9. Measure candidate-only validation cost using bounded files rather than repository-wide scans.
10. Search a broader historical or multi-repository corpus, if available without disturbing active work, for legitimate occurrences of the strong transport signature and for additional real malformed patch events.

## 22. Iteration 02 conclusion

The research has moved from "this might be detectable" to a concrete, evidence-backed failure family:

```text
replacement source
+ accidental serialization closure of operations (`}]`)
+ outer RepoPatchPreview field (`commit_title`, `view`, ...)
=> invalid Python candidate
```

Soma can detect this class before mutation because the complete candidate already exists during preview.

But the second-order result matters more: **removing obvious transport garbage can expose a different, syntactically legal source program.** Python's implicit literal concatenation made that happen in one of the two actual incidents.

That finding prevents an unsafe shortcut from entering the eventual plan.

The research direction is therefore validated, but the plan is not ready yet. The next useful work is to formalize and attack the repair-boundary proof until we know exactly which cases can be mechanically repaired and which must stop at detection/suggestion.
