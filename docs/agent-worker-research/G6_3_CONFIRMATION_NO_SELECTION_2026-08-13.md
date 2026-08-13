# G6.3 Confirmation - No Canonical Concurrency Selection - 2026-08-13

Status: `G6_3_CONFIRMATION_COMPLETE_NO_SELECTION`

## Gate

This record closes the frozen G6.3 confirmation experiment after the predeclared C4/C1/C1/C4 sequence completed under the same accepted v7 provider contract.

No canonical concurrency value is selected because neither confirmed condition remains quality-passing across its three observations.

Canonical plan: `docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`

G6.2 acceptance: `docs/agent-worker-research/G6_2_SCREENING_ACCEPTANCE_2026-08-13.md`

Provider controls remained unchanged:

- source commit `b53404fa9600412a4b3dd0fafd664a856096257b`;
- ChatGPT-authenticated Codex App Server;
- model `gpt-5.6-luna`;
- low reasoning effort;
- provider-native subagents disabled;
- read-only mutation policy;
- execution contract `execution-contract:codex-app-server:g6:v7`;
- execution-contract hash `bc84b22a23fdff7a63ff69ebb138a6e9bd8a4824678df83c04d839fe78d4c8d7`;
- frozen C1 semantic baseline and 98% relative evidence-precision floor unchanged.

## Predeclared order executed exactly

1. C4 repetition 2;
2. C1 repetition 2;
3. C1 repetition 3;
4. C4 repetition 3.

No replacement trial was inserted after a failed observation and no failed generation was refunded or erased.

## C1 confirmation

### C1 repetition 1 - accepted baseline

- trial `g6trial_b4d09bff4a8f145b2a1d32b6`;
- makespan `385.657 s`;
- submissions `8/8`;
- schema-valid `100%`;
- fact-key recall `40/40`;
- evidence precision `181/181 = 100%`;
- quality: PASS.

### C1 repetition 2 - mechanical fail

- run `20260813T131516Z_executable_profile_0aee7664`;
- trial `g6trial_5db961626e3279c6e49207ad`;
- makespan `324.625 s`;
- submissions `7/8`;
- schema-valid `87.5%`;
- fact-key recall `35/40 = 87.5%`;
- missing unit `B03`;
- provider input/output tokens `452321 / 6067`.

B03 crossed a real provider generation but failed closed. `BenchmarkSemanticPayloadV1.claims.3` placed one citation in both support and opposition for the same claim. The exact provider turn is retained in durable invalid-output evidence. No retry was launched.

Verdict: `C1_R2_FAIL_MECHANICAL`.

### C1 repetition 3 - mechanical fail

- run `20260813T132143Z_executable_profile_88b8ad41`;
- trial `g6trial_13c69e95d301434251de144b`;
- makespan `321.188 s`;
- submissions `7/8`;
- schema-valid `87.5%`;
- fact-key recall `35/40 = 87.5%`;
- missing unit `B05`;
- provider input/output tokens `445870 / 6330`.

B05 crossed a real provider generation but failed closed. `BenchmarkSemanticPayloadV1.claims.2` placed one citation in both support and opposition for the same claim. No retry was launched.

Verdict: `C1_R3_FAIL_MECHANICAL`.

C1 therefore has only `1/3` quality-passing observations. The faster makespans of repetitions 2 and 3 are not valid throughput evidence for winner selection because each omitted one required unit.

## C4 confirmation

### C4 repetition 1 - screening quality pass

- trial `g6trial_483b32286cb07b4dec9601d4`;
- makespan `117.672 s`;
- submissions `8/8`;
- fact-key recall `40/40`;
- unsupported claims `0/40`;
- evidence precision `181/184 = 98.369565%`;
- quality: PASS.

### C4 repetition 2 - semantic evidence-precision fail

- run `20260813T131218Z_executable_profile_6b776d3b`;
- trial `g6trial_3e2adade0ecbdd9cf288763b`;
- FanIn `ce9e72bdb295926b09354f6cf82278f6860ef3251f048b748b406feb1155538d`;
- makespan `118.828 s`;
- submissions `8/8`;
- schema-valid `100%`;
- fact-key recall `40/40`;
- provider input/output tokens `501017 / 6949`;
- aggregate submission bytes `186025`;
- FanIn response bytes `47998`.

Durable Sol adjudication:

- ref `g6-trial:g6trial_3e2adade0ecbdd9cf288763b:semantic-adjudication`;
- hash `b7304ae564ff7bb36d5b67f172a4f6e20183ac197fbcf33a4774eadc18d6a84c`;
- correct required facts `40/40`;
- unsupported claims `0/40`;
- precise evidence links `183/190 = 96.315789%`;
- material/preserved uncertainties `2/2`.

All previously adjudicated precise C1/C4-screen/C8 link signatures were reused, and the remaining novel links were reviewed against the frozen source commit. Seven links were imprecise: one B01 BackendKind locator stops before the enum member; three B03 concurrency citations invert support/opposition polarity; one B05 cancellation locator stops before the support value and measured observation; one B07 duplicate-detection locator only fetches the row before the fingerprint comparison; and one B08 publication locator stops before the publication-identity predicates.

Verdict: `C4_R2_FAIL_EVIDENCE_PRECISION`.

### C4 repetition 3 - semantic evidence-precision fail

- run `20260813T132740Z_executable_profile_88d682f9`;
- trial `g6trial_d1b749e7d498b205f761e96c`;
- FanIn `9c705be4fbf39762a37316d52b06af0f2bfdb6a0095fbe4839d16060c62dab71`;
- makespan `111.781 s`;
- submissions `8/8`;
- schema-valid `100%`;
- fact-key recall `40/40`;
- provider input/output tokens `500138 / 7212`;
- aggregate submission bytes `182259`;
- FanIn response bytes `47744`.

Durable Sol adjudication:

- ref `g6-trial:g6trial_d1b749e7d498b205f761e96c:semantic-adjudication`;
- hash `08c062e86e73a96231c63ef7476f2798cab172a500c3dff11fb21938d2095e0f`;
- correct required facts `40/40`;
- unsupported claims `0/42`;
- precise evidence links `173/181 = 95.580110%`;
- material/preserved uncertainties `2/2`.

The two FanIn conflicts are complementary rather than contradictory: `task.canonical_state_owner` combines canonical Task/run authority with the rejection of treating `TaskState.ACCEPTED` as substantive WorkPackage outcome acceptance; `kernel.topology_v1` combines the `single_active` topology fact with rejection of the claim that WorkPackage owns running/completed execution lifecycle.

Eight links were imprecise. Four B02 trap-rejection links were placed in `opposes_evidence_ids` even though their passages support the negative claim. The other four are a B01 BackendKind locator stopping before the enum member, a B02 topology locator stopping before the topology field, a B04 parallel-group locator stopping before the group table, and an unrelated B05 payload-reference constant cited for provider-completion semantics.

Verdict: `C4_R3_FAIL_EVIDENCE_PRECISION`.

C4 therefore also has only `1/3` quality-passing observations. Its fast wall-clock measurements cannot override the frozen semantic evidence-quality floor.

## Confirmation result

| Condition | Observation 1 | Observation 2 | Observation 3 | Confirmed quality status |
| --- | --- | --- | --- | --- |
| C1 | PASS | mechanical FAIL | mechanical FAIL | NOT CONFIRMED |
| C4 | PASS | semantic FAIL | semantic FAIL | NOT CONFIRMED |

The implementation plan selects a winner only among quality-passing conditions. A condition cannot be treated as confirmed quality-passing when two of its three observations fail the frozen quality gate. Therefore the tie-break hierarchy is not entered and no confirmed wall-clock winner is computed.

Result:

`NO_CANONICAL_CONCURRENCY_SELECTION`

No value is written for `CANONICAL_CONCURRENCY`.

## Repeated v7 failure pattern

The confirmation experiment proves that v7 is not stable enough for promotion, even though its accepted C1 observation was excellent.

The exact same cross-field invalid-output class occurred repeatedly under real provider generation:

- C2 B03;
- C1 repetition 2 B03;
- C1 repetition 3 B05.

In each case one citation was emitted in both support and opposition for one claim and Soma correctly failed closed rather than guessing or repairing provider semantics.

Separately, multiple complete trials showed evidence-polarity drift: passages that semantically support a negative/mechanical claim were emitted through `opposes_evidence_ids`, lowering semantic evidence precision. This affected C4 screening, C8 screening, and both C4 confirmation repetitions at different rates.

These are measured provider-contract reliability findings, not benchmark results to be normalized away.

## Quota checkpoint

After the exact predeclared four confirmation trials:

- model generations observed `86`;
- hard model-generation ceiling `86`;
- unused generation capacity `0`;
- provider send boundaries crossed `94`;
- API spend `$0`.

No further provider generation is authorized by this record.

## Post-confirmation regression

Run `20260813T134125Z_executable_profile_c2efff9d` passed `315` tests in `206.99 s`; all selected Ruff checks passed.

No active benchmark run or repository operation lock remained after confirmation.

## Hard boundary

G6.4 cannot start because the plan says recovery injection occurs **after concurrency selection**.

G7 cannot start because provider-native subagent benchmarking occurs **only after canonical concurrency has been selected**.

The failed v7 observations are immutable evidence. They must not be rewritten, selectively discarded, or repaired in place.

Any next provider attempt requires a versioned execution-contract repair and a new explicitly authorized model-generation ceiling. The most direct repair research target is the benchmark-specific evidence-polarity contract: remove the cross-field support/opposition ambiguity structurally rather than asking the provider to obey a relation that JSON Structured Output cannot enforce. Any such change must receive a new contract identity and rerun the affected quality comparison; the accepted v7 evidence remains historical.

## Gate result

`G6.3 COMPLETE - NO QUALITY-CONFIRMED CONCURRENCY WINNER`

`G6.4 BLOCKED`

`G7 BLOCKED`

Next lane: versioned G6 provider-contract repair research before any further real model generation.
