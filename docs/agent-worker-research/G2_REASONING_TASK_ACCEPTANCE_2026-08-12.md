# G2 Reasoning Task Acceptance

Date: 2026-08-12
Status: ACCEPTED
Repository: `D:\Github\Soma`
Branch: `lane/memory-integration-foundation-1`
Pre-G2 accepted HEAD: `02a2afbc8b174b3cc5ced1bfeb8676ebddc8acf6`
G2 implementation HEAD: `b15ca0b680e7b0f95b0e19d724e74bfc58bf315a`

## 1. Acceptance decision

Implementation Gate 2 is accepted.

Soma now has an internal provider-neutral reasoning Task path with deterministic fake-provider proof only. Canonical Task remains lifecycle authority; provider/backend state remains subordinate evidence. No real provider, public reasoning start operation, service restart, connector refresh, or live activation occurred.

## 2. Checkpoint commits

### G2.1 - bounded evidence and reasoning specs

`14a9bdf7b6faf0f81ac7451474dd3640cdc4a9df`

`Soma: add bounded worker evidence and reasoning specs`

Added pure contracts:

- `EvidenceSubmissionV1` with 12 KiB normal target and 32 KiB hard serialized ceiling;
- max 1 KiB UTF-8 executive summary;
- bounded claims/evidence/artifacts/uncertainties/blockers/excerpts/provenance refs;
- explicit claim classes `observation`, `inference`, `recommendation`, `negative_finding`;
- strict reference-first provenance/full-evidence retrieval rather than transcript bodies;
- `ReasoningSpecV1` with bounded context/dependency refs, budgets, explicit provider route, continuation policy, and mutation policy.

### G2.2 - subordinate durable reasoning backend

`4168d7493f592bf7d3a28f16b0770e9697d83260`

`Soma: add durable fake reasoning backend`

Added separate additive `reasoning_backend` schema v1 and durable backend/start-attempt evidence.

Start-delivery vocabulary is exactly:

```text
not_attempted
claimed_not_sent
accepted_bound
rejected
outcome_unknown
```

Provider binding remains subordinate:

```text
unbound
bound
uncertain
```

The single-claimer send-boundary rule is:

1. reserve Soma backend ref without provider work;
2. persist exact spec/route binding;
3. create one unique `claimed_not_sent` start attempt;
4. exactly one caller atomically enters `outcome_unknown` before provider create/send;
5. crash before that boundary may safely replay the same start-attempt identity;
6. after `outcome_unknown`, automatic replay never resubmits provider create;
7. exact provider binding/rejection later resolves that same attempt.

The deterministic fake backend proves success, rejection, long-running cancellation, malformed output, delayed result publication, crash-before-send, ambiguous acknowledgement, and restart/query recovery without external provider use.

### G2.3 - canonical Task integration

`fcba03c2e553920d11b0300d72b51c0a44983bd4`

`Soma: integrate provider-neutral reasoning Tasks`

Internal additions:

```text
TaskKind.REASONING = "reasoning"
BackendKind.SOMA_REASONING = "soma_reasoning"
```

No provider/model name appears in canonical Task enums.

Reasoning normalized request binds:

- exact ReasoningSpec ref/hash;
- ProjectScope project/resource/generation;
- optional WorkPackageAttempt ref/hash;
- exact dependency-proof refs/hashes;
- selected provider-neutral backend kind/executor;
- parent Task identity where present.

Provider-local operation/session IDs are excluded.

TaskManager now resolves persisted backend kind explicitly:

- durable command -> incumbent durable backend;
- reasoning -> configured provider-neutral reasoning adapter;
- missing reasoning adapter -> canonical `uncertain/unresolved`, never durable fallback.

ProjectScope remains the single scope/ownership plane. Its attempt attachment/startup reconciliation was made backend-kind-aware so reasoning backend refs resolve through `reasoning_backend_runs` while durable refs continue to resolve through `runs`. No second scope plane or ProjectScope schema was introduced.

Reasoning backend links use generic `backend` identity; durable backend-run links remain unchanged.

Public Task capability advertisement deliberately remains durable-command-only until a later explicit activation decision. MCP/public schema/discovery compatibility therefore remains unchanged.

### G2.4 - restart and fault proof

`b15ca0b680e7b0f95b0e19d724e74bfc58bf315a`

`Soma: prove reasoning Task restart recovery`

The restart matrix uses new TaskManager, ReasoningBackendStore, FakeReasoningBackend and ProjectScopeStore instances over the same SQLite state and proves:

- crash after backend-ref reserve before Task commit leaves no split canonical state;
- crash after Task commit before backend claim reuses the same canonical Task;
- crash after start claim before provider-send boundary reuses the same start-attempt identity;
- provider success followed by response loss never causes duplicate create after restart;
- backend restart may publish result before Task observes terminal state, then Task reconciles to completed;
- cancellation after reconnect delegates once to the recovered backend;
- ambiguous create acknowledgement remains recovery-pending and never resubmits;
- ambiguous cancellation stays uncertain rather than fabricating success;
- duplicate controller request replays deterministically;
- same request ID with changed normalized material fails closed;
- malformed output remains failure across restart and never becomes canonical success;
- bounded result references are stable across restart/retry and contain no transcript body.

## 3. Gate validation

Gate group:

`20260812T050440Z_powershell_group_675378ed`

Results:

```text
G2 evidence/spec/backend/Task/restart suites:
63 passed in 15.87s

Legacy canonical Task + ProjectScope foundation + quarantine/adjudication:
84 passed in 29.39s

MCP discovery/flat-input + Candidate-B public descriptor identity/wiring:
205 passed in 21.53s
```

Total focused/affected G2 acceptance result:

`352 passed`

Additional checkpoint evidence before the final gate included:

- canonical Task plane: 41/41 green throughout integration;
- reasoning Task integration: 11/11 green;
- reasoning backend store/fake: 19/19 green;
- MCP discovery/flat compatibility: 187/187 green;
- Candidate-B descriptor identity/wiring: 18/18 green.

No full repository suite was run because the affected Task/ProjectScope/reasoning/public-contract coverage was sufficient.

## 4. Quality and compatibility

Final G2 quality gate:

```text
Ruff check across all G2 source/test files: passed
Ruff format --check on 14 newly created G2 Python files: passed
git diff --check: passed
```

The committed G2 range `02a2afb..b15ca0b` contains exactly 21 source/test files:

```text
soma/project_scope/store.py
soma/reasoning/__init__.py
soma/reasoning/backends.py
soma/reasoning/fake.py
soma/reasoning/models.py
soma/reasoning/schema.py
soma/reasoning/store.py
soma/tasks/__init__.py
soma/tasks/backends.py
soma/tasks/manager.py
soma/tasks/models.py
soma/tasks/projections.py
soma/tasks/store.py
soma/worker_evidence/__init__.py
soma/worker_evidence/models.py
tests/test_fake_reasoning_backend.py
tests/test_reasoning_backend_store.py
tests/test_reasoning_contract.py
tests/test_reasoning_task_integration.py
tests/test_reasoning_task_recovery.py
tests/test_worker_evidence_contract.py
```

Range size:

`4517 insertions, 62 deletions`

No G2 change touched:

- `soma/server.py`;
- public gateway inventory/metadata;
- public gateway request schemas;
- Hermes model/runtime initialization;
- Company Kernel graph acceptance code;
- workflow/supervisor runtime;
- real provider configuration.

The observed Soma `public_schema_hash` remains the accepted Candidate-B value:

`84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c`

No source/runtime activation claim is inferred from that running-service metadata because Soma was not restarted.

## 5. Authority boundaries proven

G2 proves the following separation:

```text
Task
  owns canonical lifecycle / idempotency / controller recovery

Reasoning backend
  owns provider start/binding/status/result/cancellation evidence

Provider operation/session ID
  is subordinate evidence only
```

A provider terminal claim is never by itself canonical Task success. Canonical completion requires valid bounded result publication evidence. Invalid output becomes Task failure; uncertain create/binding becomes recovery rather than fabricated success.

ProjectScope continues to reserve and attach the exact Task/backend attempt identity before execution effects are treated as owned.

## 6. Implementation observations

### Observation A - ProjectScope backend-neutrality seam

Classification: `implementation-friction`

Finding:

`project_run_attempts` was structurally backend-neutral, but `attach_attempt()` and startup reconciliation still assumed every backend ref existed in `runs`.

Resolution:

The helpers now resolve backend evidence according to persisted Task `BackendKind`: durable refs use `runs`, reasoning refs use `reasoning_backend_runs`, unknown/missing kinds fail closed. ProjectScope schema/authority did not split.

Architecture impact after correction: none.

### Observation B - oversized managed preview classification

Classification: `platform-change / tooling-friction`

Finding:

One large one-shot `repo_preview(create_file)` for `soma/reasoning/store.py` was blocked before mutation with a platform safety-classification failure.

Resolution:

The file was created through smaller hash-bound Soma previews/patches. No blind write or unmanaged bypass was used.

Architecture impact: none.

### Candidate-B organic monitoring

No new wrong-tool routing, misleading title/description, unnecessary confirmation, tool-card ambiguity, or public-schema regression was observed.

Soma's repository/run tools continued to route correctly. A temporary repository-busy refusal while a managed apply finished was correct coordination behavior and cleared through `run_query(preflight)` without bypassing the lock.

## 7. Negative-boundary verification

G2 did not:

- call OpenAI, Claude, Codex or another reasoning provider;
- use provider quota;
- add provider/model names to Task enums;
- create a second work-unit lifecycle;
- expose reasoning Task start publicly;
- alter the 32 public tool names or public input schemas;
- restart Soma;
- refresh the ChatGPT connector;
- refresh the repository wiki;
- mutate canonical project memory;
- push the branch.

Four unrelated untracked documents remained outside every G2 commit and were not incorporated.

## 8. Gate decision

```text
G2: ACCEPTED
provider-neutral reasoning Task: internal / deterministic-fake proven
Task lifecycle authority: canonical Task
reasoning backend authority: subordinate evidence only
real provider: none
public reasoning start: none
public tool/schema change: none
restart: none
connector refresh: none
push: none
```

The next implementation gate is G3 deterministic FanIn and downstream dependency-proof freezing. G3 does not authorize real provider work or protected mutations.
