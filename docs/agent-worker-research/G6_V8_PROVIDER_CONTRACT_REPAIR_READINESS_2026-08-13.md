# G6 v8 Provider Contract Repair Readiness - 2026-08-13

Status: `G6_V8_PROVIDER_CONTRACT_REPAIR_READY_FOR_SCREENING`

## Boundary

This record freezes the local, zero-provider repair that follows `G6_3_CONFIRMATION_COMPLETE_NO_SELECTION`.

It does not select canonical concurrency and it does not authorize another model generation.

Prior closeout: `docs/agent-worker-research/G6_3_CONFIRMATION_NO_SELECTION_2026-08-13.md`

Prior v7 execution contract: `execution-contract:codex-app-server:g6:v7`.

## Measured v7 failure class

The v7 provider shape exposed separate `supports_citation_ids` and `opposes_citation_ids` arrays. Local Pydantic validation could require the sets to be disjoint after generation, but the provider-facing JSON Schema could not express that cross-field relation.

The same invalid-output class occurred in three real generations: C2/B03, C1 repetition 2/B03, and C1 repetition 3/B05. Each placed one citation in both relations and Soma correctly failed closed.

Independent complete trials also exhibited semantic polarity drift: proof for a negative/mechanical statement was sometimes emitted through the opposition relation, reducing evidence precision below the frozen gate.

The v7 evidence remains immutable historical evidence and is not repaired in place.

## v8 structural repair

The provider-facing claim contract is now support-only.

Each claim returns `evidence_quotes`, where each entry contains exactly:

- an assignment-provided `source_path`;
- one exact source `quote`.

There is no provider-facing opposition relation.

For a negative finding, the claim itself must state the negative finding and the selected quote must support that negative statement. If exact support is unavailable, the worker must preserve uncertainty or a partial/blocked disposition instead of attaching context-only evidence.

Soma validates each quote against the immutable assignment source and requires:

- source path belongs to the assignment;
- quote is non-empty and at most 480 characters;
- quote is single-line;
- quote occurs exactly once in the declared frozen source.

Soma then injects source hash, exact line locator, excerpt, fact key, fact value, and evidence ID mechanically. Final generic `EvidenceSubmissionV1` remains unchanged: all provider proof maps to `supports_evidence_ids`; `opposes_evidence_ids` is empty.

Identical source-quote repetitions within one claim are deduplicated before bounded evidence compaction.

## Structured-output compatibility check

The current official OpenAI Structured Outputs guide was checked before freezing this repair. Its supported-schema section explicitly lists string `pattern`, array `minItems`/`maxItems`, and other constraints used by the selected strict schema as supported for ordinary Structured Outputs; the additional restriction excluding `pattern` applies to fine-tuned models. No real provider call was needed for this documentation check.

## Frozen v8 identities

- execution ref: `execution-contract:codex-app-server:g6:v8`
- execution hash: `fea6ead0fbdc474b9f7068b50c30187c3c40d2083f8c6cf02feff76c4653b2bd`
- output ref: `output-contract:soma.agent_worker_benchmark.semantic.v5`
- output hash: `d102a8588a343c05dbc74dfd439d23f380c2cf7a02832cea5ea39948a8f3b8b0`
- source-quote contract hash: `b28770dfc95d3d843dd24a40e3a8d216eb11556fba37c7c56314ce36fa526b64`
- packet-binding hash: `629e631284bbe90d2ae19e9b0d975e38cdd1dbd7acf855d7fd94be7cf292b38f`
- evidence-compaction hash: `7ed2eac8fbb27795a45065339b7d9f31612e59b5b018585390f09106b0ed9dfd`
- prompt-instruction hash: `120ec93bc5895215f13d2794cf2fd99ac62a5852a7b0db7677636699324a99db`

Provider route, model, effort, read-only authority, and provider-native subagent prohibition remain unchanged.

## Prompt-size result

Removing the mechanically duplicated citation catalog reduced the reconstructed provider prompt by about 60 percent for every frozen unit while keeping the exact assignment source bytes in the prompt once.

| Unit | v7 reconstructed bytes | v8 bytes | Reduction |
| --- | ---: | ---: | ---: |
| B01 | 99,192 | 39,625 | 60.1% |
| B02 | 105,913 | 42,308 | 60.1% |
| B03 | 108,317 | 42,229 | 61.0% |
| B04 | 188,124 | 75,790 | 59.7% |
| B05 | 133,139 | 51,705 | 61.2% |
| B06 | 104,341 | 40,647 | 61.0% |
| B07 | 218,025 | 87,003 | 60.1% |
| B08 | 295,983 | 118,013 | 60.1% |

Measured locally by run `20260813T143633Z_executable_profile_3915a953`; no provider generation occurred.

Packet-bound strict schemas are approximately 3.95-4.07 KiB per unit.

## Local validation

Focused repair gate:

- run `20260813T143310Z_executable_profile_56fe105b`;
- `33 passed`;
- covers semantic evidence bridge, Codex G6 backend, and benchmark runner.

Focused Ruff:

- run `20260813T143533Z_executable_profile_ec3c191e`;
- all checks passed.

Broad G6 architecture regression:

- run `20260813T143713Z_executable_profile_f82bad36`;
- `316 passed in 188.41 s`;
- selected Ruff checks passed.

The one-test increase from the previous 315-test closeout is the new local v8 contract coverage, not a removed prior test.

## Quota preservation

Post-repair quota status run `20260813T144125Z_executable_profile_8cb16fdd` proves:

- model generations observed: `86`;
- hard model-generation ceiling: `86`;
- provider send boundaries crossed: `94`;
- API spend remains `$0`;
- no model generation was consumed by the repair.

## Required next experiment

The v8 change materially alters the fixed provider/output contract. Therefore the v7 screening results cannot be mixed with v8 for canonical selection.

A fresh v8 screening must rerun all four canonical conditions:

1. C1;
2. C2;
3. C4;
4. C8.

This is especially necessary because C2's v7 failure was the removed structural overlap class, while C8's v7 rejection included the removed polarity relation.

Four screening trials require at most `32` additional model generations. With `86` already observed, a new explicit owner ceiling of `118` is required before the first v8 provider trial.

Do not authorize confirmation capacity in advance. After v8 screening, predeclare confirmation only for C1 plus the actual quality-passing non-C1 candidates. This stages quota rather than reserving the worst-case confirmation budget prematurely.

## Gate result

`G6 V8 PROVIDER CONTRACT REPAIR LOCALLY ACCEPTED`

`READY FOR FRESH V8 C1/C2/C4/C8 SCREENING AFTER EXPLICIT CEILING 118`

`G6.4 REMAINS BLOCKED`

`G7 REMAINS BLOCKED`
