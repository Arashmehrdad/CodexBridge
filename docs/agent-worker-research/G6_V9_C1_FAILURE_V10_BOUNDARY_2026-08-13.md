# G6 v9 Fresh C1 Failure and v10 Boundary - 2026-08-13

Status: `G6_V10_LOCALLY_READY_PROVIDER_CAPACITY_BLOCKED`

## v9 fresh C1 observation

Run: `20260813T162054Z_executable_profile_81c1b754`

Trial: `g6trial_02d132eb2ff4ee7dd66dbb3b`

- execution contract: `execution-contract:codex-app-server:g6:v9`;
- canonical concurrency: `1`;
- makespan: `441.156 s`;
- Task/backend starts: `8`;
- automatic retries: `0`;
- submissions: `0/8`;
- required fact-key recall: `0/40`;
- model generations observed: `94 -> 101`;
- provider send boundaries: `102 -> 110`;
- hard ceiling remained `126`.

Seven units produced a counted provider generation and ended without a valid submission. B05 crossed the provider send boundary but the trial snapshot still reported its Task as `running` after `134.328 s`; no B05 model-generation marker was counted by trial close. The outer durable benchmark run itself completed normally.

C2/C4/C8 were not launched after the universal C1 submission failure.

## Architecture audit after v9

The v9 locator shape fixed the earlier quote-copy problem, but local audit found two acceptance rules that still crossed the intended worker/Soma boundary.

First, `BenchmarkSourceLocatorV1` imposed an eight-line maximum span through a local Pydantic model validator. That cross-field rule was not represented in the provider JSON Schema. A worker could therefore produce an output accepted by the provider-facing schema and still have Soma reject the entire result solely because the chosen evidence range was longer than eight lines.

Second, a worker that declared `complete` but omitted one assignment fact key was converted into transport-invalid output. Missing facts are a benchmark-quality defect, not an invalid transport or provenance condition. FanIn/Sol already have the correct place to measure recall and judge the result.

These are architectural defects independently established by source audit. This record does not claim either defect was the exact validation error for every v9 provider output because the existing trial summary does not expose each backend's private validation diagnostic.

## v10 correction

Execution contract is advanced to `execution-contract:codex-app-server:g6:v10` while keeping the same worker-facing semantic shape (`soma.agent_worker_benchmark.semantic.v6`).

Soma now accepts a worker-chosen evidence location when it is mechanically valid:

- source path belongs to the immutable assignment;
- start/end lines are positive and ordered;
- end line exists in the declared assigned source;
- canonical source/hash/provenance can be materialized and persisted.

Soma no longer imposes a semantic evidence-span size limit.

Soma also preserves an otherwise structurally valid worker submission when assignment fact keys are missing. Missing facts reduce benchmark recall in FanIn/Sol rather than erasing the worker submission.

The worker remains responsible for analysis, claims, and evidence choice. Sol remains responsible for semantic correctness, unsupported-assertion scoring, evidence precision, contradiction handling, and final synthesis.

## Local validation

Focused v10 boundary validation:

- run `20260813T163428Z_executable_profile_6dc7bc06`;
- `29 passed`;
- includes explicit proofs that a valid 12-line worker-selected source range is accepted and that a missing fact key remains a preserved submission instead of becoming transport-invalid.

Focused Ruff:

- run `20260813T163642Z_executable_profile_111d1f9a`;
- all checks passed.

Broad G6/Task/Kernel/evidence regression:

- run `20260813T163659Z_executable_profile_67c77600`;
- `322 passed in 222.87 s`.

Provider preflight after the correction:

- run `20260813T164108Z_executable_profile_3d953920`;
- ChatGPT authentication healthy;
- `gpt-5.6-luna` available;
- protocol manifest unchanged at `dcc92e96e856b1d4f93548f7f8f73e26aa87766431a0e44ceb23049c58c0dcbc`;
- generated protocol schema count `273`;
- model generations remained `101`;
- provider send boundaries remained `110`;
- current hard model-generation ceiling remained `126`.

## Capacity boundary

A fair fresh v10 screening still requires one trial each of C1/C2/C4/C8 under the same v10 contract: worst case `32` additional model generations.

Current counted generations are `101`, so the next explicit owner ceiling required for a complete fresh screen is `133`.

The existing `126` authorization is not silently extended. No v10 provider generation may start until the owner explicitly authorizes the new ceiling.

## Gate result

`V9 SCREENING STOPPED AFTER FRESH C1 UNIVERSAL SUBMISSION FAILURE`

`V10 MECHANICAL/SEMANTIC AUTHORITY BOUNDARY LOCALLY ACCEPTED`

`322 BROAD REGRESSION TESTS PASS`

`101 MODEL GENERATIONS OBSERVED`

`FRESH V10 SCREENING REQUIRES EXPLICIT CEILING 133`

`G6.4 BLOCKED`

`G7 BLOCKED`
