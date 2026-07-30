# V3-1A-ADAPTER-CONTRACT-1 — Acceptance Audit

**Date:** 2026-07-30
**Status:** accepted and closed after independent audit corrections.
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Submitted implementation:** `63a1d81` and fixture-integrity follow-up `61583a4`.
**Audit correction:** `7d629c5bdd0ade1d3d0da262bcd8509f50744041`.
**Push:** none; still not authorised.

## 1. Verdict

`V3-1A-ADAPTER-CONTRACT-1` is **accepted after corrections**.

The submitted package established the correct architecture: a pure internal adapter contract, explicit three-valued capabilities, frozen provider fixtures, exact native-session extraction, inert command specifications, provider-native usage extraction, and no public or lifecycle authority. The independent audit found material fail-closed gaps in the submitted contract. Those gaps were corrected and regression-covered before acceptance.

The accepted package remains inert. It launches no process, applies no environment, captures no PID, sends no prompt, registers no gateway, changes no task command, and writes no production substrate record.

## 2. Accepted implementation

The accepted internal package is `soma/worker_adapters/`.

It provides:

- one provider-neutral `WorkerAdapter` contract;
- explicit adapter, provider, protocol, and capability identities;
- inert start and exact-ID resume specifications;
- Claude Code stream-JSON classification;
- Codex `exec --json` classification;
- exact native session/thread identity resolution;
- provider claim classification separated from canonical task outcome;
- raw provider usage extraction using the worker-substrate field names;
- frozen fixture loading with per-read hash verification;
- no server registration or public operation.

The fixture corpus contains 18 pinned files:

- 6 `reconstructed_from_pilot_record` fixtures;
- 11 `synthetic_drift_probe` fixtures;
- 1 `inferred_unverified` Codex failure fixture.

No fixture is represented as a surviving byte-for-byte provider capture. That limitation remains explicit and binding.

## 3. Independent audit findings and corrections

### 3.1 Executable identity was not actually resolved

The submitted `ProviderCommandSpec` described `executable_path` as fully resolved but accepted `codex.exe` and other PATH-relative values.

**Correction:** command specifications now require an absolute Windows or POSIX path, reject unresolved `..` segments and NULs, and refuse PATH lookup identities. File existence and file identity remain the active process gate's responsibility because this package executes nothing.

### 3.2 Stream drift was local rather than stream-wide

An unknown or malformed event could coexist with a later recognised completion event. The submitted result then exposed trusted completion and usage despite protocol uncertainty.

**Correction:** `StreamParseResult` now distinguishes raw provider claims from trusted protocol projections. Missing or conflicting identity, any unknown or malformed event, or competing terminal claims makes the whole stream `protocol_uncertain`. Such a stream retains parsed evidence but exposes no trusted completion, failure, or persistable usage.

### 3.3 Unmeasured Codex failure was treated as trusted

The `turn.failed` shape was inferred from documentation and explicitly labelled unmeasured, but the parser mapped it directly to a trusted provider failure claim.

**Correction:** the shape remains `UNKNOWN` until a genuine reviewed capture exists. It creates protocol uncertainty and cannot drive failure projection.

### 3.4 Invalid provider usage could escape the adapter

Negative token figures and negative, NaN, or infinite provider costs passed the adapter coercion helpers.

**Correction:** coercion now returns no figure for invalid values, and `UsageExtraction` independently refuses negative/non-integer token values, invalid sequence numbers, and non-finite or negative provider cost text.

### 3.5 Malformed ordinary evidence could retain secret-bearing bytes

The submitted malformed-line record copied a bounded raw excerpt. A truncated provider line may contain credentials, private prompts, or source content.

**Correction:** ordinary parsed evidence now stores only a non-secret marker, exact SHA-256 fingerprint, byte count, and parse reason. A future protected-evidence path may retain original bytes under explicit retention and access policy; this adapter contract does not.

### 3.6 Payload-reference validation was only prefix-based

Any value beginning with `worker_payload:` was accepted.

**Correction:** prompt references are mandatory and must exactly match `worker_payload:<lowercase sha256>`. Payload references remain forbidden in argv.

## 4. Accepted fail-closed semantics

The final contract distinguishes:

- **raw provider claim:** a recognised event asserted completion or failure;
- **protocol uncertainty:** the stream contains evidence that prevents safe projection;
- **trusted provider report:** a recognised claim from a fully resolved, drift-free, non-contradictory stream;
- **canonical task result:** never created by the adapter and still owned by the Task → Run plane.

Unknown or malformed events do not disappear. They are retained as evidence, but they taint the whole stream for outcome and usage projection.

Exact session identity remains case-sensitive. Missing or conflicting identity refuses binding. Resume-last remains unconstructible.

## 5. Capability disposition

| Capability | Claude Code | Codex |
|---|---|---|
| Structured stream | supported | supported |
| Native session identity | supported | supported |
| Exact-ID resume | supported | supported |
| Mid-turn steering | supported from accepted pilot evidence | unmeasured |
| Stdin prompt | supported from accepted pilot evidence | unmeasured |
| Provider-reported USD | supported | not supported |
| Token breakdown | not supported by measured fixture | supported |
| Failure-event mapping | supported | unmeasured and not trusted |
| Orphan-free root cancellation | not supported | not supported |

`UNMEASURED` is not treated as support.

## 6. Validation evidence

### Corrected focused gate

```text
208 passed
```

This consists of the expanded adapter-contract suite plus the unchanged 43-test worker-substrate foundation suite.

### Adjacent public and authority regression

```text
99 passed
```

Covered public capabilities, CF1 gateway inventory and contract freeze, public gateway inventory, canonical task plane, and ProjectScope foundation.

### Fixture checkout proof

All 18 fixture files were materialised through Git checkout into a disposable directory. Every file:

- matched its pinned SHA-256;
- contained no carriage-return byte;
- remained protected by `.gitattributes` with `text: unset`.

### Mechanical and authority audit

- adapter modules compile;
- `git diff --check` passes;
- `EventClass` remains disjoint from `TaskState`;
- `soma/server.py` does not import the adapter package;
- no provider process or network work is present;
- generic lifecycle-authority delta is `+0`.

### Known adjacent cancellation baseline

`tests/test_job_manager.py::test_cancel_run_marks_cancelled` still fails with `cancelled: false`. The failure reproduces independently and is unchanged by the adapter package. It is not waived. Repair or explicit evidence-backed disposition is a mandatory acceptance item in the next process gate.

## 7. Authority delta

The package adds no canonical authority.

- Provider events remain evidence, not task state.
- Command specifications remain inert data, not launch authority.
- Adapters do not write TaskStore, RunStore, ProjectScope, or WorkerSubstrateStore.
- Usage extraction returns subordinate evidence fields; a caller must still pass through the accepted substrate checks.
- No gateway, connector schema, public hash, task command, backend kind, or production database path changed.

**Net generic lifecycle-authority count:** unchanged.

## 8. Remaining limitations

- No genuine provider stream byte capture exists yet.
- Codex `turn.failed`, stdin prompt delivery, and steering remain unmeasured.
- Protocol version is a Soma review marker because neither CLI stamps a provider protocol version.
- Sequence numbers are fixture line indices; a later incremental reader needs a stable monotonic per-session sequence.
- Absolute command paths are represented, but existence, stable file identity, environment application, launch, PID capture, and cancellation are not implemented here.
- No real Claude or Codex account, executable, or process was used.

## 9. Next gate

The next active bounded gate is [`V3_1A_PROCESS_IDENTITY_1_GATE_2026-07-30.md`](V3_1A_PROCESS_IDENTITY_1_GATE_2026-07-30.md): sanitised stand-in launch, exact executable identity, provider-child process attachment, and owned-tree cancellation.

`V3-1A-INTERACTION-COMMANDS-1` remains inactive until cancellation and zero-descendant proof are reliable.
