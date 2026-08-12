# G6.1 Frozen Benchmark Package Acceptance - 2026-08-12

## Gate

This record accepts the local materialization of the frozen canonical 1/2/4/8 agent/worker benchmark package.

No provider/model turn is part of G6.1.

Canonical implementation plan:

`docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`

Canonical plan SHA-256:

`fa2afb72e51e5cc4494f29b7470eb33cd8a951144a2bc78db5e65a6d8301bea2`

Frozen Iteration-5 research source:

`docs/agent-worker-research/iteration-05-frozen-graph-reasoning-broker-and-benchmark-contracts-2026-08-12.md`

Iteration-5 SHA-256:

`dc9afbfd94525890922225839488cc7b25e9798d0c61271d4bf3f0ea97d19cdb`

## Frozen research identity

Repository:

`soma`

Source commit:

`b53404fa9600412a4b3dd0fafd664a856096257b`

Frozen research corpus hash:

`a5feb6f20076bf17e64b51b66b65186b4b132417edeede83b7717472ac1df998`

Units:

- B01 canonical Task/backend authority;
- B02 Company Kernel identity/authority;
- B03 Hermes headless/concurrency substrate;
- B04 legacy Workflow versus parallel-run substrates;
- B05 provider-adapter capability truth;
- B06 interaction delivery durability;
- B07 ProjectScope and mutation containment;
- B08 Run/publication/recovery truth.

Each unit preserves the five required fact keys/questions and its critical trap from Iteration 5.

## Research-hash serialization gap

Iteration 5 records:

- the source commit;
- all unit/source paths;
- all 21 per-source SHA-256 values;
- the frozen corpus hash;
- that the corpus manifest contains repository, commit, unit IDs, lane IDs, paths, and hashes.

It does not record the canonical JSON/byte serialization recipe used to derive the frozen corpus hash, nor the concrete lane-ID strings used in that calculation.

G6.1 therefore does not fabricate a recomputation of `a5feb6f...`. The frozen research hash is preserved as inherited research provenance.

The implementation adds a separate fully explicit materialization manifest whose hash is independently reproducible.

## Source-byte representation finding

The first direct Git-blob verification exposed a deterministic Windows worktree detail in the frozen research hashes.

Across the 21 sources:

- 15 recorded research hashes equal the raw Git blob bytes at `b53404f...`;
- 6 recorded research hashes equal the deterministic CRLF representation of the corresponding raw Git blob;
- every recorded research hash matches exactly one accepted representation derived from the immutable Git source.

The six CRLF-materialized sources are not read from the current worktree. They are reconstructed from the immutable Git blob by explicit LF -> CRLF conversion and then checked against the frozen research SHA.

Each G6 assignment source now carries:

- frozen research source SHA-256;
- raw Git blob SHA-256;
- explicit representation marker (`git_blob` or `git_blob_crlf_materialization`);
- exact materialized source content.

This preserves both immutable Git provenance and the exact byte identity measured by the research freeze.

## Implementation materialization identity

Implementation schema:

`soma.agent_worker_benchmark.materialization.v1`

Implementation materialization-manifest SHA-256:

`63b9be19c3e4d2246f35f8e733abd3caaac31afde93cdbbe61d12ea3602b7b06`

Verified shape:

- units: 8;
- sources: 21;
- `git_blob`: 15;
- `git_blob_crlf_materialization`: 6.

The implementation manifest explicitly records that the original research-hash serialization recipe is not recorded.

## Frozen assignment packets

Assignment schema:

`soma.agent_worker_benchmark.assignment.v1`

Question/rubric version:

`g6-question-rubric.v1`

Evidence contract:

`evidence_submission.v1`

Evidence bounds:

- normal target: 12 KiB;
- hard ceiling: 32 KiB.

Each assignment packet contains only:

- frozen corpus/repository/commit identity;
- implementation materialization hash;
- unit/lane identity;
- exact five fact-key questions;
- exact critical trap and expected disposition;
- output-contract bounds;
- common read-only instruction;
- frozen source bytes reconstructed from the immutable source commit.

Frozen packet SHA-256 values:

- B01 `a2d05c93c174927a09060a89e43c3da29ee8f174a7776f0992de91de9af062df`
- B02 `be05bfd28e2524c3a6259c61caee40e7445540cab8024d1c23171f7aa62656cd`
- B03 `b20a010c3d05082ac878e48fee26ad4b8c9611d7f5ae46b6f1d0d92dfda537bb`
- B04 `7c08a455af58b23c4d4d81530e743f8744aa14d019cb05fa7b162d7f40339074`
- B05 `bfa5e6e0c2e16a89049b187c9d285e4e046bdc3b8ee6a49c547d35a50551d6b7`
- B06 `55a7cea415a1277e61d41bfbbb3f966f92d5db46d0b94180d2f001cb837a6f11`
- B07 `047edfabb6c390f6a55a95392d448fb156faadf16d83804e69cb767149e6cd6f`
- B08 `41183fc5ccb9c6ac92c75de4c86bfd76b432476bc1180aa7fa58e0c36aa0882f`

Repeated materialization produces byte-identical packets.

## Accepted implementation

Core materializer:

`soma/agent_worker_benchmark.py`

Tests:

`tests/test_agent_worker_benchmark.py`

Relevant commits:

- `7d87d95c976c430eb849e31ce33c106aaa3c1832` - initial frozen benchmark materializer;
- `246ed53c0dd9fb4506117366cf35295b9508b4df` - G6.1 materializer tests;
- `8f547eb06fa9a33a6a76699b6d13135f73221580` - exact mixed-EOL research-source reproduction;
- `7a9f963fe120344ccbc16328c50916fcdd5acb48` - accepted Ruff formatting.

Validation run:

`20260812T154047Z_executable_profile_5afbc0da`

Result:

- 5 passed;
- Ruff lint clean;
- Ruff format clean;
- all 21 source representations verified;
- all eight packet hashes emitted and frozen.

## Non-activation

G6.1 did not:

- launch Codex or any other reasoning-provider turn;
- spend API credit;
- consume ChatGPT/Codex model-turn quota;
- start a canonical benchmark Task;
- mutate any external resource;
- enable provider-native subagents;
- alter the 32-gateway public surface;
- restart Soma;
- refresh the connector;
- push the branch.

## Gate result

`G6.1 ACCEPTED - FROZEN BENCHMARK PACKAGE MATERIALIZED`

Next gate is G6.2 screening scaffolding and, only after a new explicit owner model-turn ceiling exists, real C1/C2/C4/C8 provider execution.
