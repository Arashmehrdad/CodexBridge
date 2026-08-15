# Patch Auto-Repair Research - Iteration 04

Date: 2026-08-12
Status: research only
Repository: Soma
Lane observed: `lane/memory-integration-foundation-1`
Repository snapshot at final pre-journal check: `4fd5c327b57350c02a958a2d0f52cb73d8cffb43`

## Scope and discipline

Iteration 04 was intended as an evidence-hardening pass before final implementation planning.

The primary questions were:

1. Can the Iteration 03 Python logical-line (`NEWLINE`) boundary gate be broken by a broader adversarial/fuzz corpus?
2. Are there additional real successful-repository-apply -> repository-parser-failure incidents beyond the two recovered in Iteration 02?
3. What does candidate validation cost on Soma's actual Windows/Python runtime?
4. Can a silent deterministic auto-repair ever be mechanically proven under Soma's current public gateway/input contract?
5. If not, what is the smallest explicit resolution flow that preserves the existing preview/apply authority model?
6. Should `unified_diff` participate in a first repair-proposal lane?
7. Is further broad research likely to change the architecture, or is the evidence now sufficient to synthesize a plan?

No production source, runtime, schema, connector, public gateway, or database was modified by this research. No restart, commit, or push was performed.

The active Agent/Worker implementation lane continued moving during this iteration. All of its tracked/untracked source and test files were treated as parked concurrent work and were not modified by this research.

## Executive conclusion

Iteration 04 changes one major recommendation and closes the central research uncertainty.

The Python `NEWLINE` boundary gate survived the expanded adversarial work and remains a good **repair-candidate safety check**.

However, silent Tier-A auto-repair cannot be mechanically proven under Soma's **current parsed-input boundary**.

The reason is fundamental rather than a missing regex or parser rule.

By the time `repo_writer` receives a patch, the public request has already been parsed into ordinary model fields. `repo_preview` passes downstream:

```text
request.operations
request.commit_title
request.commit_description
```

There is no trusted provenance bit saying:

```text
these bytes inside new_text were accidentally serialized from the outer request envelope
```

Therefore these two requests are indistinguishable to deterministic Soma code after parsing:

```text
A: accidental new_text = 'x = 1}],"view":"full'
B: intentional  new_text = 'x = 1}],"view":"full'
```

If every downstream input is identical, no deterministic function can classify A as accidental and B as intentional.

So a content-only silent repair rule that changes A must also change B.

That violates the original research constraint:

```text
no semantic guessing
no hidden generation
no silently changing intentional source
```

The correct first architecture is therefore not silent auto-repair.

It is:

```text
repo_preview(patch)
    -> materialize candidate
    -> validate
    -> detect strong repair candidate
    -> preview remains non-applicable
    -> durable repair proposal

repo_preview(resolve_patch, source_patch_id, decision)
    decision = accept_repair | accept_original
    -> create a NEW ordinary managed preview

repo_apply(previewed_change, new_patch_id)
    -> unchanged existing apply path
```

This preserves all important boundaries:

- Soma may mechanically detect likely transport corruption.
- Soma may construct one deterministic deletion-only repair proposal.
- Soma does not decide intent silently.
- The controller explicitly selects repaired or original bytes.
- The selected bytes receive a new preview identity/hash.
- `repo_apply` remains opaque and dumb.
- Intentionally invalid source has an explicit escape hatch.
- Existing safety/path/hash failures cannot be overridden by `accept_original`.

The research is now mature enough for **plan synthesis**. A fifth broad research iteration is not recommended unless planning exposes a specific evidence gap.

---

## 1. Current gateway boundary - direct source evidence

### 1.1 `RepoPatchPreview`

Current `soma/gateway_models.py` defines the public patch-preview model with:

```text
operation = "patch"
repo_name
operations
commit_title
commit_description
view
response_budget_bytes
```

The outer fields following `operations` are exactly the family recovered in Iteration 02:

```text
commit_title
commit_description
view
response_budget_bytes
```

Two real incidents contained:

```text
}],"commit_title":...
}],"view":...
```

inside Python source.

### 1.2 Parsed request loses serialization provenance

Current `soma/server.py` routes the parsed request as:

```text
if operation == patch:
    preview_repo_patch(
        request.repo_name,
        request.operations,
        request.commit_title,
        request.commit_description,
    )
```

The downstream writer does not receive:

- raw MCP request bytes;
- raw JSON serialization;
- source-token ownership metadata;
- parser recovery metadata;
- a boundary event saying which bytes originated in which outer field.

It receives already-parsed Python values.

This distinction is the basis of the impossibility result in Section 7.

### 1.3 Public patch primitives

Current public capability schema exposes:

```text
exact_text
line_range
unified_diff
python_ast
```

Internal writer helpers also contain additional aliases/whole-file mechanics, but the research plan should be based on the public four unless the public contract changes separately.

---

## 2. Expanded Python boundary experiment

Iteration 03 proposed a narrow post-repair gate:

```text
1. identify one exact deletion range independently;
2. delete exactly that range;
3. repaired candidate must compile;
4. tokenize the repaired candidate;
5. no token may span the cut;
6. only horizontal whitespace may occur from cut to next token;
7. next token must be NEWLINE (logical-line terminator).
```

The goal is not to prove intent.

The goal is narrower:

> If the deleted bytes are already known to be transport corruption, does removing them cause source before and after the cut to become part of one Python logical statement/expression?

### 2.1 Generated corpus

A local in-memory fuzz/adversarial campaign generated approximately:

```text
2,000 valid Python programs
40,000 random candidate cut positions
```

The generated corpus included combinations of:

- ASCII identifiers;
- Unicode identifiers/content;
- LF and CRLF line endings;
- assignments;
- calls;
- nested calls;
- dict/list/tuple/set literals;
- comprehensions;
- function definitions;
- conditionals;
- loops;
- decorators;
- comments;
- strings and adjacent strings;
- f-strings;
- arithmetic/operator expressions;
- attributes;
- subscriptions;
- implicit continuation;
- explicit backslash continuation;
- EOF without final newline;
- trailing horizontal whitespace.

Of the random cuts, the logical-line gate admitted:

```text
3,184
```

positions.

For admitted positions, injecting representative real schema-leak suffix forms made the resulting candidate invalid as expected.

No admitted cut was found where non-horizontal source material remained between the cut and physical logical-line termination.

This is not a proof over the Python language. It is materially stronger empirical evidence than the 35-case hand-built matrix from Iteration 03.

### 2.2 Why fuzzing did not change the gate

The gate naturally rejects broad hazard families without enumerating every token pair:

```text
open (), [], {}              -> NL, not NEWLINE
explicit backslash           -> no NEWLINE at cut
same-line operator           -> operator token before NEWLINE
same-line call               -> '(' before NEWLINE
same-line attribute          -> '.' before NEWLINE
same-line subscription       -> '[' before NEWLINE
same-line second statement   -> ';' before NEWLINE
same-line comment            -> COMMENT before NEWLINE
adjacent string continuation -> STRING/NL rather than immediate NEWLINE
lexical merge                -> token spans cut
```

This remains substantially cleaner than maintaining a hand-written table of all unsafe adjacency combinations.

---

## 3. Cross-runtime validation on Soma host

The broad fuzz run used a research Python 3.13.5 environment.

Soma's actual `.venv` currently reports:

```text
Python 3.12.10
```

A compact adversarial fixture set was therefore rechecked on Soma's own runtime.

### 3.1 Fixture correction discovered

The first compact run reported four apparent mismatches for:

```text
return
yield
break
continue
```

Those were not tokenizer/gate differences.

The fixtures placed those statements at module scope, where the complete source is invalid Python before boundary classification.

This exposed an important test-design rule:

```text
boundary-safe statement shape
!=
valid complete Python file in arbitrary context
```

The four fixtures were corrected by placing them in valid function/loop context.

Corrected Soma-host result:

```text
Python 3.12.10
corrected cases: 4
wrong: 0
```

Research implication:

Future regression fixtures must first satisfy complete-file validity under the validator runtime. The boundary gate is evaluated only after the proposed repaired complete candidate successfully compiles.

---

## 4. Soma-host candidate validation performance

A bounded in-memory benchmark was run through Soma's existing durable PowerShell/Python execution path.

No repository source files were read or modified by the benchmark. The generated candidates existed in process memory.

Runtime:

```text
Python 3.12.10
```

Observed approximate median timing (milliseconds):

```text
candidate size     compile     tokenize
-------------      -------     --------
~10 KB              2.15        2.12
~50 KB             10.79       12.39
~200 KB            41.89       56.12
~500 KB           102.13      170.90
~1 MB             541.61      988.16
```

Approximate combined cost:

```text
~10 KB      ~4 ms
~50 KB      ~23 ms
~200 KB     ~98 ms
~500 KB    ~273 ms
~1 MB     ~1.53 s
```

### 4.1 Consequences

Candidate-only validation is cheap for ordinary source files.

It is not free for large files.

The current patch system limits:

- number of patch files;
- changed lines;
- changed byte delta;

but **changed-byte delta is not a parser-cost bound**.

A one-byte modification can target a 1 MB or larger source file.

Therefore the final plan requires dedicated validation budgets such as:

```text
max_candidate_bytes_per_file
max_total_candidate_bytes_per_preview
max_files_validated
validation_wall_clock_budget
```

Exact thresholds should be selected during implementation planning/acceptance rather than guessed in research.

A reasonable design pattern is:

```text
within budget -> strict validation
outside budget -> validation_unavailable / warning according to policy
resource exception -> bounded diagnostic, never service failure
```

The validator must catch at least relevant parser/resource exceptions and avoid turning malformed source into a repository-preview service outage.

---

## 5. Historical durable failure sweep

Iteration 04 inspected the durable failed-run history around and before the active implementation period.

The sweep included:

- the two known G1 repository parser failures;
- subsequent Agent/Worker implementation validation failures;
- failed executable-profile runs back into the prior evening window.

### 5.1 Confirmed repository parser incidents remain two

The two confirmed successful-apply -> repository-source `SyntaxError` incidents remain:

#### Incident A

```text
soma/company_kernel/__init__.py
leaked outer field: commit_title
```

#### Incident B

```text
tests/test_company_kernel_schema_models.py
leaked outer field: view
```

No third repository-source transport-leak `SyntaxError` was discovered in the inspected window.

### 5.2 Other failures were materially different

More recent failures included:

- `NameError` during test collection;
- ordinary assertion/test failures;
- Ruff formatting failures;
- missing files;
- malformed research/command scripts;
- command-line quoting/serialization failures.

Several `SyntaxError` entries in durable history referred to:

```text
<string>
<stdin>
```

rather than repository source files.

Those are command/research-script construction failures and are not evidence of repository patch transport leakage.

### 5.3 Evidence strength

The historical sweep does not claim exhaustive proof over every Soma run ever created.

It does support the narrower statement:

```text
the confirmed repository transport-leak corpus remains exactly two incidents in the inspected implementation/history window
```

This is sufficient to justify defensive detection work, but too small to estimate a reliable production false-positive rate for silent automatic mutation.

---

## 6. Schema-bound detector after fuzzing

The strongest observed detector remains a conjunctive, schema-bound rule.

A candidate finding should require evidence such as:

```text
- modified Python baseline validates;
- final materialized candidate newly fails validation;
- failure location is at/near one operation's replacement tail;
- replacement tail matches a version-bound serialization closure;
- closure introduces a field belonging to the outer RepoPatchPreview envelope;
- exactly one bounded suffix deletion candidate exists;
- deletion candidate validates;
- Python logical-line gate passes or fails explicitly;
```

Observed outer-field family:

```text
commit_title
commit_description
view
response_budget_bytes
```

The detector should derive/bind this identity from the gateway schema/capability version rather than treat these words as globally suspicious source tokens.

### 6.1 Detection confidence is not repair authority

Iteration 04 makes this separation explicit:

```text
strong mechanical corruption pattern
!=
proof of accidental user/controller intent
```

Soma can say:

```text
"this candidate exactly resembles a known outer-envelope serialization leak"
```

without being entitled to say:

```text
"the caller definitely did not intend these bytes"
```

That distinction drives the final architecture.

---

## 7. Impossibility result for silent auto-repair under current contract

This is the central Iteration 04 result.

### 7.1 Statement

Under the current public gateway/parser contract, Soma cannot mechanically distinguish an accidental outer-envelope-looking string inside a replacement field from an intentional identical string supplied by the caller.

### 7.2 Construction

Consider two upstream intentions:

```text
Intent A:
  caller meant: x = 1
  serialization/control syntax accidentally leaked into new_text

Intent B:
  caller intentionally meant literal source bytes:
  x = 1}],"view":"full
```

After request parsing, suppose both produce exactly the same `RepoPatchPreview` object:

```text
operations[0].new_text == 'x = 1}],"view":"full'
```

All fields visible to `repo_preview`/`repo_writer` are now identical.

### 7.3 Deterministic consequence

For any deterministic downstream repair function `F`:

```text
identical input -> identical output
```

Therefore:

```text
F(A_parsed) == F(B_parsed)
```

If `F` deletes the suffix for A, it deletes the same suffix for B.

There is no downstream content predicate that can recover the lost upstream intention with certainty.

Compilation, tokenization, schema-shaped text, error locality, hashes and uniqueness can increase confidence that a repair is plausible, but none restores the missing provenance fact.

### 7.4 What would be required to change this result

Silent mechanical auto-repair could become provable only if the trusted input contract changes to preserve additional origin evidence, for example:

```text
- raw serialization/token ownership from the transport parser;
- explicit upstream field-boundary recovery metadata;
- a controller-signed/structured repair authorization;
- another trusted provenance channel proving those exact bytes were not authored content.
```

None exists in the current `repo_preview` input path.

### 7.5 Research verdict

The original proposed Tier A changes meaning:

```text
old idea:
  Tier A = Soma silently repairs when all mechanical checks pass

revised result:
  Tier A = Soma can mechanically produce a high-confidence repair PROPOSAL
           and prove that the proposal is syntactically/boundary safe
```

Intent selection remains explicit.

---

## 8. Minimal explicit resolution architecture

The current preview/apply model makes a clean resolution flow possible without teaching `repo_apply` about source repair.

### 8.1 First preview

Conceptual request:

```text
repo_preview(operation="patch", ...)
```

Soma performs normal operation validation, materializes full candidate and runs candidate validation.

If a strong repair candidate exists:

```text
status: preview_failed / repair_pending
applicable: false
repair_proposal:
  source_patch_id
  rule_id
  matched_field
  original_candidate_sha256
  proposed_candidate_sha256
  exact deletion range
  deleted_bytes_sha256
  validator result before/after
  boundary proof
  disposition: repair_available
```

No worktree mutation occurs.

### 8.2 Resolution preview

Add a preview-side resolution operation conceptually like:

```text
repo_preview(
    operation="resolve_patch",
    repo_name=...,
    source_patch_id=...,
    decision="accept_repair" | "accept_original",
)
```

The resolution must be repository-bound and source-preview-bound.

It produces a **new patch ID** rather than mutating the old preview in place.

Why a new patch ID is preferable:

- original evidence remains immutable by lifecycle convention;
- selected candidate gets its own payload identity;
- normal stale/hash/repository checks can be repeated;
- audit clearly records proposal vs decision;
- `repo_apply` does not need special repair semantics;
- retries/idempotence are easier to reason about.

### 8.3 `accept_repair`

Soma selects the already-computed deterministic proposal bytes.

It must not rerun an open-ended search for a new repair.

Required checks include:

```text
source patch still exists
source patch belongs to same repository
source proposal record/hash unchanged
current target baseline hashes still match source preview
proposed candidate hash matches recorded proposal
repair rule/version matches recorded proposal
```

Then Soma creates a normal new managed preview whose payload is the selected repaired candidate.

### 8.4 `accept_original`

This is essential for intentionally invalid source/fixtures.

It must mean only:

```text
explicitly override candidate-language/format validation for these exact original candidate bytes
```

It must **not** override:

- stale expected hash;
- repository fingerprint mismatch;
- path traversal;
- symlink restrictions;
- sensitive/blocked files;
- binary restrictions;
- operation overlap/exclusivity failures;
- payload limits;
- malformed patch primitive structure;
- any existing safety/authority check unrelated to candidate language validity.

The resulting new preview records a validation override and exact original candidate hash.

### 8.5 Apply remains unchanged

After resolution:

```text
repo_apply(
    operation="previewed_change",
    repo_name=...,
    patch_id=new_patch_id,
)
```

The existing opaque apply semantics remain the authority boundary.

This is preferable to adding:

```text
repo_apply(operation="repair_and_apply")
```

because repair intent would then become entangled with worktree mutation and recovery.

---

## 9. Public response/status implications

Current compact `repo_preview` response exposes counts and broad validation information but does not have repair-proposal fields.

Current `patch_status` projection exposes lifecycle/status, changed files, errors and apply result but not arbitrary manifest validation/repair provenance.

A first implementation therefore needs deliberate bounded projections for repair state.

Conceptual compact fields:

```text
repair_available: true|false
repair_candidate_count
repair_disposition
repair_rule_id
repair_changed_byte_count
original_candidate_sha256
proposed_candidate_sha256
```

Full preview/status can expose bounded detailed provenance:

```text
matched outer field
validation before/after
error location
byte range
boundary proof
validator/runtime identity
source patch id
resolution child patch id, if any
```

Do not dump unbounded malformed replacement text into compact responses.

---

## 10. Bundle/provenance model after explicit resolution

Iteration 03 suggested a possible future bundle v4 for authoritative auto-repair metadata.

Iteration 04 refines that recommendation.

### 10.1 Detection/proposal source preview

A failed source preview can carry proposal metadata in an extended bundle/manifest record because it is not applicable.

Conceptual:

```text
candidate_validation
repair_proposals[]
```

### 10.2 Resolution child preview

The selected child preview should record:

```text
resolution:
  source_patch_id
  decision
  source_original_candidate_sha256
  source_proposed_candidate_sha256
  selected_candidate_sha256
  repair_rule_id
  repair_rule_version
  validation_override: true|false
  resolved_at
```

The selected candidate's ordinary payload hash remains the apply identity.

### 10.3 Bundle version

Whether this requires bumping bundle version 3 depends on compatibility semantics chosen during planning.

Research recommendation:

- advisory metadata on non-applicable failed previews can plausibly extend v3;
- a new applicable resolution-child semantic should strongly consider v4 so old code cannot silently ignore authoritative resolution provenance.

This is a file-format compatibility decision, not necessarily a SQL/database migration.

### 10.4 Integrity terminology remains limited

As established in Iteration 03, current manifest/payload hashes prove consistency relative to the same managed bundle, not external tamper-proof immutability.

Do not describe repair provenance as independently cryptographically immutable unless a new trust anchor is introduced.

---

## 11. Unified diff decision

### 11.1 Candidate validation remains useful

A successful unified-diff operation already materializes a complete final candidate.

Therefore Python/JSON candidate validation can apply to the result in exactly the same place as other primitives.

### 11.2 First repair-proposal lane should exclude unified diff

For the first implementation, transport-repair proposals should be limited to primitives where the user-authored replacement payload has a direct explicit string boundary:

```text
exact_text
line_range
python_ast
```

`unified_diff` should receive:

```text
candidate validation
+ diagnostics
- no transport suffix repair proposal initially
```

Reasons:

1. the authored object is a diff grammar rather than direct replacement text;
2. outer-envelope leakage may already fail diff parsing before candidate materialization;
3. mapping a candidate-level suspicious suffix back to exactly which diff bytes are transport corruption is less direct;
4. there is no real unified-diff transport-leak incident in the corpus;
5. explicit resolution removes the urgency to generalize repair transformation across every primitive in v1.

This is an intentional scope boundary, not a claim that unified-diff repair is impossible.

### 11.3 Future path

If real evidence appears, research can define a diff-specific detector based on added-line provenance and exact diff grammar boundaries.

Until then, validation-only is safer.

---

## 12. Create-file policy after impossibility result

`RepoCreateFilePreview` has a similarly shaped outer envelope:

```text
path
content
commit_title
commit_description
view
response_budget_bytes
```

So serialization-shaped leakage into `content` is conceptually possible.

But there is still no real create-file incident in the corpus and no baseline file.

First-phase recommendation remains:

```text
create .py invalid:
  warning/diagnostic by default

create .py invalid + strong schema-bound leak proposal:
  non-applicable preview + explicit resolution required

accept_original:
  permits intentional invalid fixture/source

accept_repair:
  selects deterministic proposal
```

Do not silently auto-repair create content.

---

## 13. Validator applicability policy

### 13.1 Modified Python files

Strong first-phase rule:

```text
baseline compiles
candidate fails
=> invalid regression
```

This is valuable even when no transport repair proposal exists.

Policy should distinguish:

```text
invalid_regression
baseline_already_invalid
candidate_valid
validation_unavailable
validation_budget_exceeded
```

### 13.2 Baseline already invalid

Do not claim the patch introduced invalid syntax merely because candidate is also invalid.

Possible result:

```text
validity unchanged/unknown
warning
no generic hard block solely from baseline-invalid comparison
```

A strong transport proposal may still be reported, but explicit resolution is required.

### 13.3 Runtime identity

Record at least:

```text
validator = python_compile
python major.minor.micro
implementation if relevant
```

Same-runtime baseline-vs-candidate comparison is the key transport-regression signal.

Do not overclaim compatibility with all Python versions declared by the repository.

### 13.4 Resource budgets

A candidate validator must have explicit byte/time bounds independent of `changed_bytes`.

Budget exceedance must be visible as a validation state rather than silently treated as success.

---

## 14. Non-Python validators - scope for final plan

The architectural impossibility result is language-independent:

```text
content alone cannot prove upstream intent when provenance was lost before validation
```

Therefore JSON/TOML/YAML/XML should not receive silent auto-repair in the first plan either.

The useful near-term distinction is **validation**, not repair.

### JSON

Good early full-document validator candidate.

First plan can reasonably include:

```text
.json complete candidate -> strict parse within byte budget
```

### TOML

Useful but runtime/dependency gated because Soma's supported Python floor and `tomllib` availability differ.

May be deferred or capability-gated.

### XML

Defer synchronous hard parsing until parser/resource/security policy is explicit.

### YAML

Defer hard validation initially. Parser version/tags/schema behavior make it a separate policy problem.

The plan does not need every format in v1 to solve the observed Python failure class.

---

## 15. Rejected approaches after Iteration 04

### Reject: silent content-only Tier-A auto-repair

Reason: impossible to distinguish intentional identical source from accidental spill under current parsed input contract.

### Reject: treat high statistical confidence as mechanical proof of intent

Fuzzing can validate boundary safety, not upstream authorship intent.

### Reject: `repo_apply(repair_and_apply)`

Combines intent resolution with mutation/recovery and weakens the clean preview/apply boundary.

### Reject: mutate failed preview in place after controller accepts repair

Prefer a new child preview so original evidence and selected bytes have distinct durable identities.

### Reject: make invalid Python universally impossible to preview/apply

Repositories legitimately contain parser fixtures, scratch files and version-targeted source. Explicit `accept_original` is required.

### Reject: let `accept_original` bypass existing repository safety checks

The override is candidate-language validity only.

### Reject: unified-diff repair proposal in first activation

No real corpus and weaker authored-byte boundary mapping.

### Reject: infer parser cost from changed-byte delta

Host benchmark shows full candidate size is the relevant cost driver.

---

## 16. Confirmed bugs

No existing Soma contract bug is confirmed.

The two motivating incidents remain implementation-friction under the current contract:

```text
Soma faithfully applied the opaque previewed payload it was given.
```

Iteration 04 does confirm one design limitation relevant to a future feature:

```text
current parsed preview input does not preserve enough provenance to make silent transport auto-repair mechanically certain
```

That is not a violation of current behavior.

It is an input-contract fact the new feature must respect.

---

## 17. Required acceptance tests implied by all four iterations

The eventual plan should include at least the following test families.

### 17.1 Real incident regression fixtures

Incident A:

```text
commit_title leak
candidate invalid
repair proposal found
repair candidate compiles
logical-line gate fails (NL)
no automatic selection
```

Incident B:

```text
view leak
candidate invalid
repair proposal found
repair candidate compiles
logical-line gate passes (NEWLINE)
explicit accept_repair creates child preview
normal apply can apply child preview
```

### 17.2 Intent ambiguity fixture

Two source previews with identical malformed replacement bytes but different hypothetical upstream intentions must produce the same deterministic proposal.

Test contract should explicitly state:

```text
Soma does not claim to know which intention is true
```

### 17.3 `accept_original`

- candidate-language validation fails;
- explicit accept_original creates child preview containing exact original candidate bytes;
- child records override provenance;
- ordinary apply applies only that selected child payload;
- no hidden source rewrite occurs.

### 17.4 Override isolation

`accept_original` must not bypass:

- stale SHA;
- path violation;
- symlink restriction;
- repository mismatch;
- binary restriction;
- operation overlap;
- patch size/line limits;
- malformed primitive structure.

### 17.5 Proposal identity

- source patch hash/identity stable;
- exact original candidate hash stored;
- proposed candidate hash stored;
- exact deleted byte range stored;
- deleted-byte hash stored;
- repair rule/version stored;
- gateway/schema capability identity stored;
- source -> child resolution link stored.

### 17.6 Resolution idempotence

Repeated identical resolution requests should either:

- return the same existing child preview; or
- deterministically create one canonical child according to the chosen contract.

Do not generate an unbounded chain of duplicate resolution previews.

### 17.7 Staleness

If repository content/HEAD changes between source preview and resolution:

```text
resolution must not silently carry stale baseline authority forward
```

Either reject resolution or revalidate and create a new source relationship under explicit rules.

### 17.8 Apply remains repair-blind

Tests must prove:

```text
repo_apply never runs candidate repair detection
repo_apply never chooses accept_repair vs accept_original
repo_apply only verifies/applies selected opaque child payload
```

### 17.9 Performance/resource tests

- normal 10-200 KB candidates remain bounded;
- large candidate crosses configured validation budget predictably;
- timeout/resource exception is diagnostic, not service crash;
- 50-file preview total budget is enforced;
- changed-byte delta cannot bypass candidate-byte budget.

### 17.10 Cross-runtime fixtures

At minimum run the boundary fixture suite on Soma's supported/tested Python runtimes.

Keep contextual validity correct for statements such as `return`, `break`, `continue` and `yield`.

---

## 18. Research-to-plan handoff decisions

The following questions are sufficiently answered for planning.

### Q1. Where does validation belong?

After complete candidate materialization and before an applicable preview bundle is created.

### Q2. Should apply re-run repair?

No.

### Q3. Is Python `compile()` useful?

Yes, especially baseline-valid -> candidate-invalid regression detection.

### Q4. Is compile success after deletion proof of safety?

No. Incident A disproved this.

### Q5. Is the Python `NEWLINE` gate useful?

Yes, as a structural safety gate for a proposed deletion-only repair.

### Q6. Does the `NEWLINE` gate prove intent?

No.

### Q7. Can current Soma silently auto-repair with mechanical certainty?

No, because upstream serialization provenance is absent after request parsing.

### Q8. What replaces silent auto-repair?

Durable deterministic repair proposal + explicit resolution into a new preview.

### Q9. How should intentionally invalid source work?

Explicit `accept_original` override scoped only to candidate-language validation.

### Q10. Should `repo_apply` change semantics?

No.

### Q11. Should unified_diff receive repair proposals in v1?

No; validation only.

### Q12. Should create_file be a universal syntax hard block?

No; no baseline and legitimate invalid-source use cases.

### Q13. Are dedicated parser budgets required?

Yes. Soma-host benchmark demonstrates the need.

### Q14. Is a DB schema migration inherently required?

No. Proposal/resolution metadata can conceptually live in managed bundle JSON; bundle compatibility/versioning still needs a plan decision.

### Q15. Is the research ready for plan synthesis?

Yes.

---

## 19. Suggested final implementation-plan shape

This section is not implementation authorization. It is the research handoff structure the next planning pass should expand into staged tasks.

### Stage A - candidate validation foundation

- validator result model;
- Python baseline/candidate compile validation;
- candidate-byte/time budgets;
- bounded public diagnostics;
- no repair yet.

### Stage B - transport repair proposal

- schema-bound detector for direct replacement primitives;
- exact deletion-only candidate;
- Python repaired-candidate compile;
- `NEWLINE` boundary gate;
- durable proposal provenance;
- failed/non-applicable source preview.

### Stage C - explicit resolution preview

- `resolve_patch` preview operation or equivalent;
- decisions `accept_repair` / `accept_original`;
- source-to-child linkage;
- new payload identity;
- validation-override scoping;
- idempotence/staleness rules.

### Stage D - apply compatibility

- normal `previewed_change` apply only;
- verify new bundle/resolution semantics as needed;
- prove no repair logic runs in apply;
- rollback/revert unchanged.

### Stage E - format expansion

- JSON complete-document validator;
- decide TOML capability gate;
- defer XML/YAML unless separately justified.

### Stage F - telemetry/evidence period

Before considering any future upstream-proven automatic resolution:

- count repair proposals;
- count accepted repair/original decisions;
- measure false-positive proposals;
- measure validation cost/budget skips;
- collect any additional real transport families.

This evidence can inform whether a future input-contract change is worthwhile.

---

## 20. Remaining plan-level decisions, not research blockers

These can be resolved during implementation planning rather than another broad research iteration:

1. exact validator byte/time thresholds;
2. exact public result field names;
3. whether resolution is a new `repo_preview` operation or another controller-neutral preview-side action;
4. bundle v3 extension vs v4 for applicable resolution children;
5. exact idempotency key for repeated resolution;
6. how much deleted transport text to retain vs hash-only provenance;
7. whether JSON ships in the first implementation stage or immediately after Python;
8. exact Python runtime support/test matrix;
9. naming: `repair_available`, `repair_proposal`, `candidate_resolution`, etc.

These are design choices with enough evidence to adjudicate in a plan.

---

## 21. Iteration 04 conclusion

The research started with a tempting objective:

```text
Can Soma silently fix obvious malformed patch payloads?
```

Four iterations changed that into a more precise and safer architecture.

Iteration 01 found the correct candidate-materialization seam.

Iteration 02 recovered two real failures and proved that deletion + successful compilation can silently change Python semantics.

Iteration 03 found a strong Python logical-line boundary gate that rejects the real adjacent-string trap.

Iteration 04 attacked that gate, measured real host cost, searched for more incidents, and identified the decisive information-theoretic boundary:

```text
once the request has been parsed and provenance is lost,
identical source bytes cannot reveal whether they were accidental or intentional.
```

Therefore the final safe architecture is:

```text
validate
  -> detect
  -> propose deterministic repair
  -> require explicit resolution
  -> create new hash-bound preview
  -> apply unchanged
```

The `NEWLINE` gate remains valuable, but as proof that a **proposal** does not join Python logical statements—not as proof of caller intent.

This resolves the largest open safety question without turning Soma into a semantic coding agent.

### Research verdict

```text
RESEARCH SUFFICIENT FOR PLAN SYNTHESIS
```

Do not start another broad iteration automatically.

The next step should be to synthesize Iterations 01-04 into a staged implementation plan with explicit acceptance gates, compatibility decisions, rollout sequence and non-goals.

If that planning pass exposes a specific unresolved technical question, return to targeted research only for that question.
