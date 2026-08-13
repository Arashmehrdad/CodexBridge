# G6.2 Screening Acceptance - 2026-08-13

Status: `G6_2_SCREENING_ACCEPTED`

## Gate

This record closes the frozen G6.2 C1/C2/C4/C8 real-provider screening stage. It does **not** select a canonical concurrency winner; screening only determines which conditions are eligible for G6.3 confirmation.

Canonical plan: `docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`

Plan SHA-256: `fa2afb72e51e5cc4494f29b7470eb33cd8a951144a2bc78db5e65a6d8301bea2`

Frozen source commit: `b53404fa9600412a4b3dd0fafd664a856096257b`

Provider controls remained unchanged from C1: ChatGPT-authenticated Codex App Server, `gpt-5.6-luna`, low reasoning effort, provider-native subagents disabled, read-only mutation policy, execution contract `execution-contract:codex-app-server:g6:v7` (`bc84b22a23fdff7a63ff69ebb138a6e9bd8a4824678df83c04d839fe78d4c8d7`).

## Frozen C1 baseline

Accepted record: `docs/agent-worker-research/G6_C1_SCREENING_BASELINE_2026-08-13.md`

- run `20260813T092857Z_executable_profile_86e2d4fb`;
- trial `g6trial_b4d09bff4a8f145b2a1d32b6`;
- peak `1`, makespan `385.657 s`;
- submissions `8/8`, fact-key recall `40/40`, traps `0`;
- unsupported claims `0/41`;
- evidence precision `181/181 = 100%`;
- semantic adjudication `e9121dc5b0b6135726752545528941249e1e6bc4292083853bc8588480b16224`.

Frozen non-C1 floor: zero trap failures, 100% schema-valid submissions, zero missing units, unsupported assertions <=5%, fact-key recall >=98%, semantic evidence precision >=98%.

## C2 - mechanical fail

- run `20260813T103238Z_executable_profile_a8b67eb3`;
- trial `g6trial_2d5a57a61d3932df7db1f97b`;
- manifest `2d5a57a61d3932df7db1f97bb0f96c2d5b5a480dcb0b340caba90cea1c632db4`;
- FanIn `ea15f80f5430861443d84093ec39415b1dc28ba0ea05542c3c9f4775e5e5100e`;
- peak `2`, makespan `222.235 s`, Task/backend starts `8`, retries `0`;
- submissions `7/8`, schema-valid `87.5%`, evidence-reference validity `87.5%`;
- fact-key recall `35/40 = 87.5%`, traps `0`, missing unit `B03`;
- input/output tokens `452321 / 6073`, API spend `$0`.

B03 reached a real provider generation but failed closed as `invalid_benchmark_output`: its structured payload declared one citation in both support and opposition for the same claim, violating the frozen v7 evidence contract. No rerun was used to erase the measured failure.

Verdict: `C2_FAIL_MECHANICAL`. C2 is not eligible for confirmation.

## C4 - quality pass

- run `20260813T121433Z_executable_profile_19269f33`;
- trial `g6trial_483b32286cb07b4dec9601d4`;
- manifest `483b32286cb07b4dec9601d48bc9d5792125dea3fb3e62aa5380c84266ee9467`;
- FanIn `2a12b8a840878311604093ff1768ba309ebee2e8a6f9311d89da26c179462673`;
- peak `4`, makespan `117.672 s`, starts `8`, retries `0`;
- submissions `8/8`, schema-valid `100%`, evidence-reference validity `100%`;
- fact-key recall `40/40`, traps `0`, input/output tokens `501017 / 6746`.

Sol adjudication: `g6-trial:g6trial_483b32286cb07b4dec9601d4:semantic-adjudication`, hash `89a34e9a6017cb91a8c8b1bb9716ff1d1c18e91f7c55bf8b9226f0e9f355257f`.

- correct facts `40/40`;
- unsupported claims `0/40`;
- precise links `181/184 = 98.369565%`;
- reported uncertainties `4`; material/preserved `3/3`;
- structured conflicts `0`.

All 43 novel C4 links were reviewed after exact C1-gold reuse. Three B03 links were semantically relevant but had inverted declared `opposes` polarity; the remaining links were precise.

Verdict: `C4_PASS_QUALITY_GATE`. C4 is eligible for confirmation.

## C8 - semantic evidence-precision fail

- run `20260813T123025Z_executable_profile_d2ea5b56`;
- trial `g6trial_35ee8ec5b558525f4ddce087`;
- manifest `35ee8ec5b558525f4ddce0879cb7e851033edea16f6fc3d8f246264b776f7093`;
- FanIn `8aada06fd3727e694a38d93454308aa5536e1e9b094ec5b3210a8a5bb7b3c83e`;
- peak `8`, makespan `101.000 s`, starts `8`, retries `0`;
- submissions `8/8`, schema-valid `100%`, evidence-reference validity `100%`;
- fact-key recall `40/40`, traps `0`, input/output tokens `498703 / 6885`.

Sol adjudication: `g6-trial:g6trial_35ee8ec5b558525f4ddce087:semantic-adjudication`, hash `ebd7a85da785e78f5b77ee09227abf9eaf6f579665ba12ad1db70ef1d1a8f34c`.

- correct facts `40/40`;
- unsupported claims `0/41`;
- precise links `181/185 = 97.837838%`;
- reported/material/preserved uncertainties `3/3/3`;
- structured conflicts `1`.

The FanIn conflict on `lock.current_granularity` is complementary: one variant states repository-name lock granularity; the second rejects unsupported role-based ownership and describes the same mechanical acquisition.

All 38 novel C8 links were reviewed after exact C1-gold reuse. Four had inverted declared polarity: one B06 `interaction.outcome_unknown_rule` link and three B07 `lock.current_granularity` links were placed in `opposes` even though their passages supported the corresponding negative/mechanical claim. The resulting `97.837838%` precision is below the frozen `98%` floor. Faster wall-clock performance cannot override the quality gate.

Verdict: `C8_FAIL_EVIDENCE_PRECISION`. C8 is not eligible for confirmation.

## Screening comparison

| Condition | Peak | Makespan | Mechanical gate | Evidence precision | Confirmation eligible |
| --- | ---: | ---: | --- | ---: | --- |
| C1 | 1 | 385.657 s | PASS | 100.000% | baseline / yes |
| C2 | 2 | 222.235 s | FAIL | not adjudicated | no |
| C4 | 4 | 117.672 s | PASS | 98.370% | yes |
| C8 | 8 | 101.000 s | PASS | 97.838% | no |

No winner is selected from screening. The only non-C1 quality-passing candidate is C4, so G6.3 must compare C1 and C4 only.

## Post-screening regression

Run `20260813T124524Z_executable_profile_dd682bbd` passed `315` tests in `226.67 s`; all selected Ruff checks passed.

## Provider quota checkpoint

At G6.2 close:

- provider send boundaries crossed `62`;
- model generations observed `54`;
- hard model-generation ceiling `54`;
- unused generation capacity `0`;
- API spend `$0`.

The failed C2 generation remains historical evidence and is not refunded or rewritten.

## Predeclared G6.3 confirmation order

Before any confirmation result is observed, the eligible set and balanced order are frozen as:

1. C4 repetition 2;
2. C1 repetition 2;
3. C1 repetition 3;
4. C4 repetition 3.

This yields three total observations per eligible condition and distributes the two conditions across the confirmation window.

Four confirmation trials require a worst-case additional `32` model generations. With `54` already observed, G6.3 requires a new explicit hard ceiling of at least `86` before the first confirmation trial may start. No G6.3 provider turn is authorized by this acceptance record alone.

## Gate result

`G6.2 ACCEPTED - SCREENING COMPLETE`

Entering G6.3: C1 baseline and C4 candidate.

Rejected at screening: C2 for mechanical completeness; C8 for semantic evidence precision below the frozen floor.

No canonical concurrency winner exists yet.
