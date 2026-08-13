# G6 v10 Budget Closure - 2026-08-13

Status: `G6_PROVIDER_ROUTE_ACCEPTED_CONCURRENCY_BENCHMARK_CLOSED_INCONCLUSIVE`

## Owner boundary

The owner explicitly ended further benchmark token spend and authorized exactly one additional Codex provider generation to wrap up the G6 provider-contract repair.

No full C1/C2/C4/C8 rerun is authorized by this record. No concurrency winner may be inferred from the incomplete v10 experiment.

## v10 local acceptance carried forward

The v10 contract preserves the intended architecture boundary:

- the reasoning worker owns semantic analysis, answers, and evidence selection;
- Soma validates and persists only mechanical assignment/source/locator/provenance facts;
- Sol owns semantic adjudication and final synthesis.

Before the final provider smoke, v10 had already passed:

- focused boundary validation: `29 passed`;
- broad G6/Task/Kernel/evidence regression: `322 passed`;
- focused Ruff: clean;
- ChatGPT-authenticated provider preflight with `gpt-5.6-luna` available.

Historical v7/v8/v9 failures remain immutable evidence and are not rewritten or normalized away.

## One-generation final provider smoke

Run: `20260813T165114Z_executable_profile_a1c832b1`

Smoke: `g6smoke_9d4260ac5e4488dfcbf7eefa`

Unit: `B01`

Execution-contract hash: `fcc62bcfdf98fdfc621a3ffb619a13ce0eece0742f1c3c64455734381ce3cd36`

Result:

- provider terminal claim: `success`;
- provider status: `completed`;
- Task state: `completed`;
- output-contract disposition: `valid`;
- EvidenceSubmission present: yes;
- benchmark assessment present: yes;
- smoke success: `true`;
- model generations observed: `101 -> 102`;
- provider send boundaries: `110 -> 111`.

The final smoke therefore demonstrates that the repaired v10 smart-worker/mechanical-Soma contract can complete one real provider Task end-to-end and publish mechanically valid evidence without Soma semantically grading the worker.

An earlier malformed local invocation failed before provider execution and consumed no Codex generation; it is not part of the provider evidence claim above.

## G6 closure decision

The original throughput experiment is closed without a canonical concurrency selection.

Result:

`CANONICAL_CONCURRENCY = UNSELECTED`

This is intentional. A single smoke is evidence for provider-contract viability, not evidence for a throughput winner. Historical C1/C2/C4/C8 measurements were produced under superseded contracts and must not be combined with v10 as if they were one controlled experiment.

For current implementation work, concurrency remains a bounded controller/runtime policy rather than a benchmark-promoted global constant. No value of 1, 2, 4, or 8 is promoted by G6.

If throughput optimization is ever reopened, it requires a fresh same-contract comparison under new explicit provider authorization. Until then, the system should use its existing bounded/conservative runtime behavior rather than claiming a scientifically selected optimum.

## G6.4 and G7 disposition

The owner-directed budget closure ends the provider-expensive optimization ladder here.

- G6.4 recovery-matrix work is deferred; deterministic/local recovery coverage remains valid but no new real-provider recovery campaign is required for this closure.
- G7 provider-native subagent benchmarking is deferred and must not consume Codex/provider capacity unless the owner explicitly reopens it.
- Neither deferred optimization experiment may be represented as completed.
- They are not blockers for continuing the core Agent/Worker implementation because no result from either experiment is being used to set runtime authority or topology.

## Final gate

`V10 REAL PROVIDER SMOKE PASS`

`EXACTLY ONE ADDITIONAL CODEX GENERATION USED`

`G6 PROVIDER CONTRACT ACCEPTED`

`G6 CONCURRENCY BENCHMARK CLOSED INCONCLUSIVE`

`NO CANONICAL CONCURRENCY VALUE PROMOTED`

`G6.4 DEFERRED`

`G7 DEFERRED`

`NO FURTHER CODEX USAGE AUTHORIZED BY THIS RECORD`
