# G6 v9 Mechanical Evidence Repair Readiness - 2026-08-13

Status: `G6_V9_MECHANICAL_EVIDENCE_REPAIR_READY_FOR_SCREENING`

## Why v9 exists

Fresh v8 C1 failed `0/8` after all eight real provider generations produced evidence quotes that were either non-exact or non-unique. That failure exposed implementation drift from the canonical G3.4 architecture: the reasoning worker should own semantic work and evidence selection; Soma should own durable/mechanical transport; Sol should own semantic adjudication.

Historical failure record: `docs/agent-worker-research/G6_V8_C1_FAILURE_2026-08-13.md`.

The canonical implementation plan now states this authority boundary explicitly in G6.2.

## v9 boundary

The provider remains a smart reasoning worker. It:

- reads the exact frozen assignment material;
- answers the assigned fact-key questions;
- decides which assigned source locations it believes support each claim;
- reports `source_path`, `start_line`, and `end_line` evidence locations;
- preserves uncertainty when appropriate.

Soma does **not** judge whether the selected passage proves the claim. Soma only validates and preserves mechanical facts:

- assignment/fact-key identity;
- source membership in the frozen assignment;
- source hash/identity already frozen by the benchmark packet;
- one-based line-range validity and bounded span size;
- schema/bounds/provenance;
- deterministic evidence materialization;
- durable Task/result/FanIn identity and completeness.

Soma materializes the exact frozen source locator and a bounded exact source excerpt into generic `EvidenceSubmissionV1`. The worker-declared link is preserved; semantic truth is not created by Soma.

Sol remains the evaluator for:

- fact correctness;
- unsupported assertions;
- whether a worker-declared evidence location actually supports the claim;
- evidence precision;
- contradictions/conflicts;
- uncertainty quality;
- final synthesis.

If semantic verification needs another opinion, use Sol/another reasoning worker rather than adding semantic heuristics to Soma.

## Implementation

New provider bridge:

- `soma/reasoning/benchmark_evidence_v9.py`

Backend binding:

- `soma/reasoning/codex_g6_backend.py`

Zero-provider regression coverage:

- `tests/test_benchmark_evidence_v9.py`
- updated `tests/test_codex_g6_backend.py`
- updated `tests/test_agent_worker_benchmark_runner.py`

The historical v8 bridge remains in `soma/reasoning/benchmark_evidence.py`; v9 is explicitly versioned rather than rewriting historical provider evidence semantics in place.

## Frozen v9 identities

Measured locally by run `20260813T161143Z_executable_profile_c1f64234`:

- execution ref: `execution-contract:codex-app-server:g6:v9`
- execution hash: `4d7b46d31e7bdc3f4e76544d8c6a83986394fd32f58f8418acf5cdeeabd4c538`
- output ref: `output-contract:soma.agent_worker_benchmark.semantic.v6`
- output hash: `16b379a29b648f8ea53182023a120f4113d8b97eb7a4e01840cabfde6cdd456f`
- source-locator contract hash: `77c4c3d18f1a5661b06f981076ab9a1acf4647ea48f27e90334cea862c93ce66`
- packet-binding hash: `7859d7c1a02dc2a30cd746f5ebe7c7185a7918a34dc53c6779fa85fd1a79dbdb`
- evidence-compaction hash: `37687c9b81d2c13d506f9b61404a4b751068720e1ea3478a2a439a7cb8c23026`
- prompt-contract hash: `51e73555566e2257c061c68208902d5ef24f392bf2dae29333cf3ab3f313eeee`

Provider route, model (`gpt-5.6-luna`), low effort, ChatGPT authentication, read-only authority, and provider-native subagent prohibition remain unchanged.

## Provider prompt/schema sizing

The provider source view contains deterministic numbered source lines. Prompt bytes by unit are:

| Unit | Prompt bytes | Strict schema bytes |
| --- | ---: | ---: |
| B01 | 43,912 | 4,041 |
| B02 | 47,748 | 4,042 |
| B03 | 48,192 | 4,071 |
| B04 | 83,749 | 4,063 |
| B05 | 58,856 | 4,116 |
| B06 | 45,650 | 4,095 |
| B07 | 95,713 | 4,007 |
| B08 | 129,961 | 4,026 |

No provider generation was used to compute these values.

## Local validation

Focused v9/backend gate:

- run `20260813T160025Z_executable_profile_0a71a9e1`;
- `37 passed`.

Broad G6 architecture regression:

- run `20260813T160341Z_executable_profile_2a7afae2`;
- `320 passed in 181.86 s`;
- the pytest suite was fully green;
- the run then reported one Ruff-only unused re-export marker in the new v9 module.

That Ruff marker was corrected without behavior change. Post-fix focused verification:

- run `20260813T161116Z_executable_profile_2b17e58c`;
- `16 passed`;
- selected Ruff checks passed.

Final broad selected Ruff verification:

- run `20260813T161229Z_executable_profile_010dfb0c`;
- all checks passed.

The v9-specific regression explicitly proves that a deliberately semantically wrong claim with a mechanically valid assigned locator is preserved by Soma rather than semantically rejected. That is intentional: Sol owns that judgment.

## Provider/quota preflight

Post-repair provider preflight run `20260813T161156Z_executable_profile_c595a3e4` passed:

- authentication: `chatgpt`;
- selected model `gpt-5.6-luna` available;
- protocol manifest unchanged: `dcc92e96e856b1d4f93548f7f8f73e26aa87766431a0e44ceb23049c58c0dcbc`;
- generated protocol schema count: `273`;
- model generations observed: `94`;
- provider send boundaries crossed: `102`;
- current hard model-generation ceiling: `118`.

The entire v9 repair and validation consumed **zero** additional Codex generations.

## Required next experiment

v9 materially changes the provider/output contract, so v7/v8 trials cannot be mixed with v9 for canonical concurrency selection.

A fair v9 screening must freshly run:

1. C1;
2. C2;
3. C4;
4. C8.

That requires at most `32` model generations. With `94` already observed, the required hard ceiling is:

```text
126
```

The current ceiling `118` is intentionally insufficient. No v9 provider trial should start until the owner explicitly authorizes ceiling `126`.

Do not pre-authorize confirmation capacity. After v9 screening, only quality-passing candidates should receive staged confirmation capacity.

## Gate result

`G6 V9 MECHANICAL EVIDENCE REPAIR LOCALLY ACCEPTED`

`SMART WORKER -> SOMA MECHANICAL PRESERVATION -> SOL SEMANTIC ADJUDICATION`

`94/118 GENERATIONS OBSERVED; ZERO GENERATIONS SPENT ON V9 REPAIR`

`READY FOR FRESH V9 C1/C2/C4/C8 SCREENING AFTER EXPLICIT CEILING 126`

`G6.4 REMAINS BLOCKED`

`G7 REMAINS BLOCKED`
