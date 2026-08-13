# G6 C1 Screening Baseline - 2026-08-13

Status: `C1_BASELINE_ACCEPTED`

G6.2 screening is **not complete**. This record freezes the accepted C1 baseline before any C2/C4/C8 result is observed under the accepted provider contract.

## Frozen execution identity

- source commit: `b53404fa9600412a4b3dd0fafd664a856096257b`
- provider route: ChatGPT-authenticated Codex App Server
- model: `gpt-5.6-luna`
- reasoning effort: `low`
- provider-native subagents: disabled
- mutation policy: read-only
- execution contract ref: `execution-contract:codex-app-server:g6:v7`
- execution contract hash: `bc84b22a23fdff7a63ff69ebb138a6e9bd8a4824678df83c04d839fe78d4c8d7`
- frozen B01-B08 assignment packets: unchanged

The v7 contract mechanically binds provider Structured Output to each frozen packet:

- claim `subject_key` is an exact assignment-fact enum;
- citation arrays reference an exact packet-local citation-ID enum;
- provider-authored line arithmetic, excerpts, evidence IDs, and parallel evidence rows are not accepted as authority;
- Soma derives bounded final evidence rows and cross-references mechanically;
- support and opposition citation sets are explicitly disjoint;
- evidence compaction remains bounded to the existing 24-record `EvidenceSubmissionV1` ceiling.

## Accepted C1 trial

- durable run: `20260813T092857Z_executable_profile_86e2d4fb`
- trial id: `g6trial_b4d09bff4a8f145b2a1d32b6`
- trial manifest hash: `b4d09bff4a8f145b2a1d32b624d96eb6c4eac0cf8d130f17405ed53e97399bc5`
- FanIn hash: `700046d301c19036c928207400e8eea07d1e3baa6e70b3becafb6d69f1cc91d8`
- canonical concurrency limit: `1`
- measured peak active canonical Tasks: `1`
- makespan: `385.657` seconds
- Task/backend starts: `8`
- automatic retries: `0`

Mechanical quality:

- collected submissions: `8 / 8`
- schema-valid submission rate: `100%`
- evidence-reference validity: `100%`
- required fact-key recall: `40 / 40 = 100%`
- critical-trap failures: `0`
- missing units: `0`
- partial units: `0`
- blocked units: `0`
- uncertain units: `0`
- provider input tokens: `502174`
- provider output tokens: `6872`
- API spend: `$0`

## Frozen Sol semantic scoring policy

The semantic scoring policy was fixed before observing any C2/C4/C8 candidate result.

- scoring-policy hash: `8032a6a7116b1b7a8a235659db554b0de915541366577ae68fcc426d53916c10`
- fact-key correctness = semantically correct required facts / assignment-required facts
- unsupported-assertion rate = unsupported structured claims / structured claims
- evidence precision = correctly supportive/oppositional published claim-to-evidence links / published claim-to-evidence links
- future non-C1 quality gate keeps the frozen roadmap thresholds: unsupported assertions <= 5%, fact-key recall no more than 2 percentage points below C1, evidence precision no more than 2 percentage points below C1, plus the mechanical gates.

Gold mutation after seeing candidate results is forbidden without a versioned rubric change and rerun of affected comparisons.

## Sol adjudication

Durable semantic adjudication:

- ref: `g6-trial:g6trial_b4d09bff4a8f145b2a1d32b6:semantic-adjudication`
- hash: `e9121dc5b0b6135726752545528941249e1e6bc4292083853bc8588480b16224`
- evaluator: `sol`
- required facts correct: `40 / 40 = 100%`
- unsupported claims: `0 / 41 = 0%`
- semantically precise published evidence links: `181 / 181 = 100%`
- baseline eligible: `true`

All 41 structured claims and all 181 published claim-to-evidence links were reviewed against the frozen B01-B08 source packets.

The two unresolved B03 uncertainties are material and correctly preserved:

1. the frozen sources establish a supervised-worker ceiling of 32 but do not establish the current configured worker count;
2. the frozen sources establish a shared Hermes service but do not independently define the semantic meaning of an independent reasoning mind.

FanIn reports one structured conflict on `hermes.supervisor_worker_ceiling`. Sol adjudicates it as **complementary, not contradictory**: the code ceiling is 32, while the worker correctly states that the ceiling does not prove 32 workers are currently configured or running.

## Audit trail from failed provider contracts

Earlier real-provider attempts are retained as immutable diagnostic evidence rather than overwritten. They exposed and caused fixes for:

- strict Structured Output schema incompatibility;
- missing provider-terminal forensic evidence;
- conflation of send attempts with model generations;
- unreliable model-authored source line/excerpt locators;
- duplicate citation/evidence identity namespaces;
- parallel evidence-list synchronization;
- EvidenceSubmission envelope overflow;
- underspecified support/opposition polarity;
- out-of-catalog provider citation identifiers.

The accepted C1 result is therefore not a rerun of the earlier failed contracts; v7 has a distinct execution-contract identity and successor WorkPackageAttempts.

## Provider quota checkpoint

At this acceptance point the durable G6 ledger records:

- provider send boundaries crossed: `38`
- model generations observed: `30`
- current hard model-generation ceiling: `32`
- unused capacity under current ceiling: `2`

Two remaining generations are insufficient for any eight-unit C2/C4/C8 screening condition. No additional screening condition may start unless the hard provider ceiling is explicitly extended. The existing 30 generations remain historical evidence and are not rewritten or refunded.

## Post-baseline architecture regression

- durable run: `20260813T095847Z_executable_profile_5e04e645`
- result: `315 passed`
- duration: `206.47` seconds
- Ruff: all selected implementation checks passed

The regression covered the G6 benchmark/adjudication layers plus Company Kernel graph/admission/recovery, canonical Task and reasoning lifecycle, Codex App Server/backend contracts, worker evidence/FanIn, ProjectScope, protected mutation containment, interaction dispatch, and operation-lock ownership semantics.

## Verdict

`C1_BASELINE_ACCEPTED`

`G6_2_SCREENING_INCOMPLETE`

Next provider work, after an explicit quota-ceiling extension, is C2 screening under the exact same accepted v7 controls. C4 and C8 follow only after terminal evidence for the preceding condition is reconciled. No screening winner may be selected from C1 alone.
