# Iteration 39 - Real-Workflow Pressure Test: Soma Skill Layer

Date: 2026-08-15
Status: research only; product/architecture pressure test
Track: Sol-centric agent interface + Soma Skill layer

## Purpose

Pressure-test the Iterations 32-38 Skill architecture against realistic Soma/Arash workflows before final synthesis.

Candidate under test:

```text
Agent Skills open package format
external private canonical Skill Library
immutable whole-package revisions
skill_query
skill_action
Sol owns Skill selection
progressive pull loading in normal Chat
bundled scripts use existing Task/Run execution authority
no Skill activation state in continuation
native/browser surfaces are adapters
```

## Workflow 1 - Explicit normal-Chat Skill use

Owner:

```text
use arash-research for this
```

Expected:

```text
Sol -> skill_query.search/get exact current arash-research ref
Sol reads SKILL.md
Sol performs research workflow
```

Result: PASS.

No browser add-on or native Skill installation is required if Soma is connected.

## Workflow 2 - Implicitly useful Skill

Owner asks a complex research question but does not name `arash-research`.

Desired:

```text
Sol notices a reusable Skill may help
-> skill_query.search(...)
-> selects arash-research if relevant
```

Architecture: viable.

Product certainty: NOT YET PROVEN.

Unlike a native Skill host, normal Chat + Soma does not receive every Skill name/description at session startup. It only sees the stable `skill_query` tool description.

Therefore Skill-discovery recall must be measured.

Do not solve this by adding a semantic router before measurement.

## Workflow 3 - Ordinary request where no Skill is useful

Owner asks a simple one-off question.

Desired:

```text
Sol answers normally
no skill_query call
```

This is the matching false-positive side of the discovery problem.

The Skill gateway description must encourage search when a stored workflow is plausibly useful without becoming a mandatory preflight for every request.

## Workflow 4 - Update `arash-research` from a successful research session

Owner:

```text
update my arash-research Skill with what we learned here
```

Expected:

```text
skill_query.get(current ref)
Sol authors revised Agent Skills package
skill_action validates + stores immutable new revision
current revision moves when requested
earlier revision retained
```

Result: PASS architecturally.

Soma validates package mechanics, not the semantic quality of the new research rules.

## Workflow 5 - Skill changes mid-continuation

Objective begins under R7.

Owner later improves the Skill to R8 while the objective remains open.

Fresh Chat receives:

```text
current continuation contract
prior Sol handoff
linked Task/Run state
```

Then Skill discovery occurs normally.

Expected default:

```text
fresh Sol loads current R8
```

Old R7 remains available for provenance/debugging.

Result: PASS.

No continuation Skill state is required.

## Workflow 6 - Exact historical reproduction

Owner:

```text
why did the old research session behave differently?
```

If an exact old `skill_ref` is known from audit/artifact/user note:

```text
skill_query.get(R7)
compare to current R8
```

Result: PASS.

If no exact mechanical reference was ever recorded, Soma must not claim it knows which Skill was cognitively active. That limitation is honest and acceptable.

## Workflow 7 - Skill contains helper script

`SKILL.md` references:

```text
scripts/check_repo.py
```

Expected:

```text
Sol -> skill_query.resource(exact ref, script path)
Sol decides to run it
Sol -> existing run_start/Task execution path
Run preserves normal durable evidence
```

Result: PASS.

Skill package never becomes process authority.

## Workflow 8 - Skill asks for domain action

A Skill says:

```text
update Cloudflare record
```

Expected:

```text
Sol -> cloudflare_action
```

not:

```text
Skill runtime -> hidden shell/curl
```

Result: PASS.

Domain gateways retain their authority.

## Workflow 9 - Multiple Skills

Research task also involves scientific reporting.

Sol may load:

```text
arash-research
scientific-reporting
```

Soma returns exact independent packages.

Sol reconciles instructions under normal model/user instruction precedence.

Result: PASS.

No merge engine required.

## Workflow 10 - Conflicting Skills

Two loaded Skills give conflicting workflow advice.

Expected:

```text
Soma does not choose a winner
Sol reasons from current user request + instruction hierarchy
```

Result: PASS as an authority boundary.

Semantic quality remains model responsibility.

## Workflow 11 - Large Skill library

Assume hundreds of Skills.

Public MCP descriptor remains constant-size because the library is behind one `skill_query`, not one tool per Skill.

Search returns bounded metadata; full bodies load only on demand.

Result: PASS architecturally.

Search/index scaling becomes an implementation benchmark, not a public-contract redesign.

## Workflow 12 - Native ChatGPT/Work/Codex use

A Soma Skill revision is exported as a standard Agent Skills package and installed natively where supported.

Native host may then discover/activate it using its own Skill system.

Result: PASS.

Soma is not required in the native activation path, though the Skill may still instruct Sol to use Soma tools.

## Workflow 13 - Native and Soma copies diverge

Soma has R8; native ChatGPT has exported R7.

Expected:

- no false synchronization claim;
- explicit export/import needed to converge;
- both remain identifiable by package content/version/provenance.

Result: PASS with accepted explicit-sync limitation.

## Workflow 14 - Browser add-on unavailable

Normal Chat still has connected Soma tools.

Expected:

```text
skill_query remains sufficient for correctness
```

Result: PASS.

Browser picker remains optional UX.

## Workflow 15 - Soma unavailable

Native installed Skill may still work in a compatible product.

Soma-managed Skill library cannot be queried while Soma is unavailable.

Result: expected availability boundary, not architecture failure.

## Workflow 16 - Same-name external import

Owner already has `arash-research` R8.

An external package also declares `name: arash-research`.

Expected:

```text
import may create candidate/new revision with provenance
current does not silently change
explicit activation/replacement required
```

Result: PASS after Iteration 38 correction.

## Workflow 17 - Out-of-band package edit

Installed immutable R8 bytes are modified outside Soma.

Expected:

```text
R8 verification fails / drift detected
Soma does not serve modified bytes as R8
new valid content must become a new revision/import
```

Result: PASS as a required integrity invariant.

## Workflow 18 - Fresh Chat receives only `continue`

Continuation resume gives Sol current objective/handoff/effects.

If the resumed task benefits from a workflow, Sol may search Skills then.

Result: PASS, subject to the same Skill-discovery recall question as Workflow 2.

## Main remaining weakness: discovery recall

The core architecture cannot guarantee that normal Chat will call `skill_query.search` every time a helpful Skill exists, because Soma does not own ChatGPT startup context and deliberately does not inject the whole Skill catalog.

This is a measurable UX/routing problem.

### Required A/B corpus extension

Extend the existing normal-Chat routing/evaluation method with Skill cases.

At minimum measure:

```text
explicit Skill request -> correct exact Skill retrieval
implicit good Skill match -> search/retrieval recall
no useful Skill -> unnecessary skill_query rate
multiple plausible Skills -> selection quality
conflicting Skills -> no hidden Soma arbitration
resource-needed -> on-demand resource retrieval
script-needed -> existing execution gateway used
Skill update request -> skill_action, not repo/knowledge mutation
```

Useful metrics:

```text
skill_search_recall
skill_search_false_positive_rate
correct_skill_at_k
unnecessary_skill_calls
full-body-overfetch rate
resource-overfetch rate
normal-task latency/call cost
```

### Possible outcomes

If `skill_query` alone performs well:

```text
browser add-on unnecessary for core UX
```

If implicit discovery recall is weak but explicit/manual use is strong:

```text
optional browser picker becomes valuable
```

If native Skill hosting is available on a surface:

```text
native adapter may provide better automatic discovery there
```

None of these outcomes require a second Soma model/router.

## Product acceptance target

Normal explicit UX:

```text
owner: use arash-research
Sol: loads it and works
```

Normal implicit UX target:

```text
owner: research this architecture properly
Sol: notices reusable workflow may help
Sol: searches/loads arash-research
```

Skill-management UX:

```text
owner: update arash-research with what we learned
Sol: creates a new immutable revision
Sol: reports old ref -> new ref
```

No IDs should need to be manually managed by the owner in ordinary use.

## Verdict

**REAL-WORKFLOW PASS WITH ONE MEASURABLE PRODUCT RISK.**

The Skill architecture survives realistic workflows. The remaining uncertainty is automatic Skill-discovery recall in normal Chat, which should be measured with an extension of Soma's existing normal-Chat golden corpus rather than solved by adding a router or injecting all Skill metadata.

The architecture is ready for a final synthesis after this correction.

This iteration does not authorize implementation.
