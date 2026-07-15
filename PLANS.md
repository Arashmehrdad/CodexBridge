# CodexBridge Unified Engineering Roadmap

## Executive Direction

CodexBridge is a local engineering control plane between ChatGPT and the user's machines, repositories, services, and remote hosts.

The target operating model is:

```text
ChatGPT
  -> CodexBridge MCP
  -> local policy and orchestration
      -> repository inspection and managed patching
      -> durable command and executable runs
      -> workflows and supervisors
      -> local model and project memory
      -> SSH and remote controllers
      -> return-loop reports
      -> Codex only when explicitly enabled
```

Codex is currently disabled by operator choice and is not a dependency for this roadmap. Repository changes continue through managed preview/apply tools and explicit local commits.

The immediate program is no longer feature expansion at any cost. It is:

1. finish byte-safe managed editing and the incomplete R2 server handoff;
2. add an operator-enabled unrestricted executable substrate;
3. make OpenSSL the first unrestricted executable profile;
4. complete transfer, durable remote ownership, resource, environment, and acceptance work;
5. return to local-model, memory, dashboard, and optional local-coding expansion only after execution correctness is proven.

## Governing Engineering Principles

### Durable before powerful

Every accepted asynchronous operation must have durable launch intent, ownership identity, lease state, cancellation state, output locations, and terminal publication semantics before it is considered production-ready.

### Explicit capability profiles

- `readonly`: inspection and fixed non-destructive commands.
- `chatgpt_delegated`: structured execution, reviewed scripts, managed writes, and ordinary engineering operations.
- `permissive`: operator-authorized unrestricted capabilities on explicitly registered machines, hosts, and executable profiles.
- `human_only`: financial actions, public release, protected-branch push, production infrastructure changes, and external permission grants unless separately reclassified by the operator.

### Operator risk acceptance

The operator may durably enable a permissive capability and accept its risk once in configuration. After that capability is enabled, CodexBridge should not repeatedly ask for per-invocation approval unless the request crosses a different protected boundary.

For an unrestricted executable profile, CodexBridge enforces the identity of the executable and the integrity of its lifecycle. It does not attempt to reinterpret or censor the executable's own command language.

### Direct process launch where possible

Dedicated executable gateways launch an absolute configured executable with structured argv and `shell=False`. A dedicated root-shell gateway remains separate for actions that genuinely require shell syntax.

This prevents accidental shell injection without limiting the enabled executable's native options.

### Full evidence, bounded public output

The durable run directory may contain complete stdout, stderr, binary output, inputs, hashes, and execution metadata. Public MCP responses remain bounded and may redact sensitive material. Permissive execution does not imply automatic disclosure of private keys, passwords, or binary artifacts in chat.

### Small independent batches

Every completed repository change is locally committed. Each batch must be independently reviewable and validated. Do not combine patch-engine repair, OpenSSL enablement, remote durability, and acceptance testing into one broad refactor. Do not push unless explicitly requested.

## Current State

### Reliability foundation - complete

Batches D1-D5 established and validated:

- durable `launch_pending` state before worker creation;
- separate launcher, worker, and child process identity;
- worker lease tokens, lease generations, state versions, and process-start identity;
- process-aware startup reconciliation and active-worker adoption;
- conditional terminal transitions and stale-generation rejection;
- workflow worker leases and idempotent child attachment;
- supervisor child attachment and unified repository operation locks;
- conservative legacy long-job containment;
- atomic return-loop publication and delivered-manifest preservation.

Historical full-suite evidence reached `932 passed, 1 skipped`, with `python -m pip check` and `git diff --check` passing at the D5 exit gate.

### Existing control-plane foundations

The repository already contains foundations for:

- repository-scoped MCP tools and capability metadata;
- managed repository preview/apply/commit operations;
- SQLite-backed runs and durable artifacts;
- workflows, supervisors, cancellation, events, and heartbeats;
- local-agent orchestration and an Ollama adapter;
- project commands and scoped validation runners;
- return-loop reports and PulseSender-compatible manifests;
- read-only dashboard visibility;
- native SSH inspection, commands, administration, transfers, deployments, reviewed scripts, and permissive root shell contracts.

These components should be extended rather than replaced.

### Codex status

Codex prompt transport was historically repaired and validated in T1. Codex execution is now intentionally disabled in configuration and hard-blocked before process launch. The roadmap must remain executable without Codex.

### Remote execution status

R1 policy and request contracts are complete.

R2 is in progress. Reviewed-script model, command, manager, and worker layers now support bounded arguments and `pwsh`. Canonical envelopes allow safely quoted data arguments for Bash, `sh`, Python 3, and PowerShell while rejecting alternate launchers and unquoted shell syntax.

Latest focused evidence:

- `tests/test_tool_gateway_models.py`: 23 passed;
- `tests/test_ssh_commands.py`: 28 passed;
- `tests/test_job_manager.py`: 55 passed;
- existing `tests/test_ssh_worker.py` checkpoint: 37 passed.

The remaining R2 server forwarding change is blocked by a managed-patch defect that normalizes mixed line endings in `codexbridge/server.py` and creates unrelated large diffs.

## Revised Implementation Order

## G0 - Byte-Safe Managed Patch Engine

Status: **next required batch**.

Goal: managed edits must change only the requested bytes or syntax region, including files with mixed line endings.

Deliverables:

- Preserve untouched bytes for `exact_text`, `line_range`, `unified_diff`, and `python_ast` operations.
- Define explicit newline behavior for replacement text without normalizing unrelated lines.
- Reject previews that produce unrelated newline-only churn.
- Add regression fixtures containing LF, CRLF, and intentionally mixed line endings.
- Add a preview assertion that reports changed logical lines separately from newline-only changes.
- Revalidate preview/apply/revert idempotency and rollback hashes.

Acceptance:

- A one-line edit to mixed-line-ending `server.py` produces a one-line semantic diff.
- Applying and reverting the patch restores the exact original SHA-256.
- No repository file is rewritten solely to normalize line endings.

## G1 - Complete R2 Execution Gateway Paths

Depends on G0.

Goal: close the public server handoff and finish the three execution modes.

Deliverables:

- Forward reviewed-script `arguments` through `ssh_action` and `start_ssh_reviewed_script_async`.
- Add server-level model and delegation coverage for arguments and `pwsh`.
- Add argument-bearing forced-PTY coverage.
- Confirm `structured` execution always uses configured argv and never falls back to shell interpretation.
- Confirm `reviewed_script` supports hash-pinned Bash, `sh`, Python 3, and PowerShell with explicit arguments.
- Confirm `root_shell` remains an explicitly permissive, separate gateway with protected full artifacts and bounded public summaries.

Acceptance:

- `readonly` rejects reviewed scripts and root shell.
- `chatgpt_delegated` accepts structured execution and reviewed scripts.
- `permissive` accepts structured execution, reviewed scripts, and unrestricted registered-host root shell.
- Request arguments survive model -> server -> manager -> worker -> SSH command unchanged.

## X1 - Generic Unrestricted Executable Profile Contract

Goal: create one reusable direct-executable substrate rather than a one-off OpenSSL wrapper.

Build an `ExecutableProfile` contract with:

- profile ID and enabled flag;
- absolute executable path;
- optional expected executable SHA-256 and signer/version metadata;
- local or remote execution target;
- working-directory policy;
- environment policy;
- stdin mode: none, text, bytes, file, or protected reference;
- stdout/stderr mode: text, bytes, file, or protected artifact;
- timeout policy, including operator-enabled no-timeout runs;
- cancellation and process-tree policy;
- public-output and protected-artifact policy;
- autonomy profile required to invoke it.

Permissive executable profiles may enable:

- arbitrary argv;
- arbitrary working directory allowed by the service account;
- arbitrary filesystem paths allowed by the service account;
- arbitrary environment names and values or references;
- arbitrary network destinations used by the executable;
- binary-safe input and output;
- no subcommand or flag allowlist.

Engineering boundaries that remain:

- launch the configured absolute executable directly with `shell=False`;
- never resolve the executable from an untrusted working-directory PATH entry;
- persist the exact executable identity, argv representation, target, timestamps, and exit state;
- use the durable run/lease/cancellation model;
- keep shell execution in the separate root-shell gateway;
- let operating-system permissions remain the final local security boundary.

Acceptance:

- An enabled permissive profile receives arbitrary argv without filtering or reinterpretation.
- Quoting-sensitive arguments reach the child process exactly.
- Binary stdin/stdout round-trip without JSON or text corruption.
- Disabled or unregistered executable profiles fail before process creation.

## X2 - Unrestricted Local OpenSSL Gateway

Depends on X1.

Status target: first unrestricted executable profile.

Configuration example:

```yaml
executable_profiles:
  openssl:
    enabled: true
    executable_path: "C:/Program Files/OpenSSL-Win64/bin/openssl.exe"
    target: local
    autonomy_profile: permissive
    unrestricted_argv: true
    unrestricted_paths: true
    unrestricted_environment: true
    unrestricted_network: true
    allow_no_timeout: true
```

Required capability:

- any OpenSSL command and option;
- arbitrary command ordering and argument values supported by OpenSSL;
- arbitrary input and output paths available to the service account;
- custom `OPENSSL_CONF` and other OpenSSL environment variables;
- custom providers, provider paths, property queries, modules, engines, and configuration files;
- certificate, CSR, key, digest, signature, encryption, decryption, CMS, PKCS#7, PKCS#8, PKCS#12, OCSP, CMP, TLS client, TLS server, random, and diagnostic operations;
- arbitrary network endpoints for commands such as `s_client`, `s_server`, OCSP, and CMP;
- text or binary stdin;
- binary-safe stdout and stderr artifacts;
- configurable timeout or no timeout;
- arbitrary working directory and filenames;
- protected full output plus bounded public status.

There must be no OpenSSL subcommand, option, path, provider, engine, configuration-file, key-size, algorithm, or network-target filtering in the permissive profile.

Passwords and key material may be supplied by any method OpenSSL supports. CodexBridge should additionally offer protected stdin, temporary file, and environment-reference paths so the operator is not forced to expose secrets on the process command line. This is an ergonomic protection, not a restriction on OpenSSL capability.

Acceptance:

- `openssl version -a` records executable and library identity.
- random binary generation round-trips as a protected artifact.
- key, CSR, and certificate workflows complete in an isolated test directory.
- custom config and provider options reach OpenSSL unchanged.
- a local loopback `s_server`/`s_client` test proves network and cancellation behavior without relying on the public internet.
- arbitrary output paths work when Windows permissions allow them.
- no shell process is created for ordinary OpenSSL execution.

## R3 - Transfer Policy and Managed Staging

Goal: provide predictable transfer scope for reviewed scripts, executable profiles, and remote controllers.

Policies:

- `repo_only`: local paths remain inside the registered repository; remote paths remain inside configured roots.
- `configured_roots`: local and remote paths may use explicitly configured roots.
- `unrestricted`: arbitrary paths available to the service account or registered remote user; permissive only.

Deliverables:

- deterministic staging paths and hashes;
- atomic upload/download publication where possible;
- cleanup manifests and retry-safe cleanup;
- binary-safe transfers;
- executable-profile input/output staging;
- protected artifact classification;
- audit metadata linking transfers to the invoking run and lease generation.

Acceptance:

- bounded profiles cannot escape their configured roots;
- permissive transfers can use arbitrary paths when OS/remote permissions allow them;
- retries do not duplicate or silently overwrite without the requested overwrite policy;
- staged content is hash-verified before execution.

## R4 - Durable Remote Job Protocol

Goal: remote work survives CodexBridge restart and local worker loss.

Remote controller state must include:

- request ID, execution ID, and idempotency key;
- authoritative state and heartbeat;
- controller fingerprint and version;
- stdout, stderr, input, and result locations;
- PID, process group ID, and process-start identity;
- cancellation request and completion evidence;
- executable or shell identity;
- resource-monitor state.

Local state must include:

- host ID and remote job ID;
- remote state directory;
- remote PID/PGID and verified process identity;
- lease generation and last authoritative heartbeat;
- publication and cleanup state;
- uncertainty/reconciliation state.

Required behavior:

- launch returns only after durable remote ownership is established;
- service restart adopts a matching live remote controller;
- local worker loss does not terminate or duplicate remote work;
- cancellation targets the exact verified remote process group;
- network uncertainty does not trigger duplicate launch or false terminal state;
- remote state is authoritative for execution; local `RunStore` remains authoritative for bridge lifecycle and publication.

Acceptance:

- remote work runs beyond one hour;
- CodexBridge restarts during execution and reattaches;
- duplicate reconcilers cannot start duplicate remote controllers;
- cancellation kills the verified process group and descendants;
- terminal evidence is published once.

## X3 - Unrestricted Remote OpenSSL

Depends on X2, R3, and R4.

Goal: expose the same unrestricted OpenSSL profile on a registered permissive remote host.

Deliverables:

- remote executable identity and version capture;
- arbitrary OpenSSL argv, paths, environment, providers, configuration, and network targets;
- binary-safe staged and streamed input/output;
- remote protected artifacts and local publication manifests;
- restart adoption and exact process-group cancellation;
- optional root execution only through the separately enabled permissive root-shell or remote-user configuration.

Acceptance:

- local and remote OpenSSL profiles share one request/result contract;
- remote execution survives bridge restart;
- provider/config/key/certificate and loopback TLS tests pass on the disposable host;
- no OpenSSL option is silently removed or rewritten.

## R5 - Absolute Resource Enforcement

Goal: prevent runaway long jobs while preserving explicit permissive overrides.

Default remote cgroup v2 thresholds:

- hard: `48_000_000_000` bytes;
- graceful: `45_000_000_000` bytes;
- conservative: `40_000_000_000` bytes.

Deliverables:

- read cgroup v2 absolute values before host percentages;
- retain GPU temperature/memory, disk, heartbeat, and CUDA OOM signals;
- graceful termination followed by verified process-group escalation;
- record the exact threshold, sample, decision, and termination evidence;
- allow an explicit permissive profile to raise or disable configured thresholds where the host supports it, without weakening identity or cancellation checks.

Acceptance:

- each threshold path is deterministically tested;
- disabled/raised limits are visible in durable metadata;
- the exact process tree is terminated when enforcement fires.

## R6 - Environment and Secret References

Goal: support both unrestricted environment capability and safer secret delivery.

Deliverables:

- arbitrary environment maps for profiles that explicitly permit them;
- durable reference identifiers for protected values;
- launch-time resolution through inherited environment, protected stdin, or temporary files;
- binary-safe temporary material;
- cleanup after launch or terminal reconciliation;
- protected full diagnostics and bounded public summaries;
- explicit metadata showing which reference IDs were used without persisting their values.

Permissive OpenSSL remains able to use literal environment values or command-line password options when the operator chooses. Reference delivery is the recommended path, not a forced limitation.

Acceptance:

- missing references fail before child launch;
- secret values do not appear in public events or summaries when references are used;
- temporary material is removed or conservatively reported for repair after crashes;
- environment values reach local and remote OpenSSL unchanged.

## R7 - Provider-Neutral Disposable-Host Acceptance Gate

Goal: prove the complete contract on a disposable host before paid or workload-specific use.

The generic suite must prove:

- native endpoint access and capability discovery;
- profile and execution-mode enforcement;
- bounded and unrestricted transfers;
- reviewed Bash, `sh`, Python 3, and PowerShell scripts;
- unrestricted permissive root shell;
- unrestricted local and remote OpenSSL profiles;
- arbitrary OpenSSL provider/config/path/network arguments;
- binary input/output and protected artifact publication;
- execution longer than one hour;
- service restart survival and remote reattachment;
- absolute resource enforcement and permissive overrides;
- exact verified process-tree cancellation;
- durable result, report, return-loop, and cleanup evidence.

Run the same provider-neutral contract against RunPod only after the generic suite passes. Core code and tests must contain no workload-specific or provider-specific behavior.

## P2 - Local Agent and Product Expansion

Begin after R7 unless a smaller supporting change is required by an earlier batch.

### Project memory

- consolidate static, run, artifact, decision, and job memory;
- retrieve the latest durable task context without relying on ChatGPT conversation memory;
- add retention and repair tools;
- keep memory writes auditable and repository-scoped.

### Local model

- summarise logs and failures;
- compress context;
- select likely files;
- draft plans and reports;
- route tasks without making unrestricted engineering decisions silently;
- remain optional when Ollama is unavailable.

### Supervisor and workflow improvements

- local diagnosis before any coding escalation;
- reusable execution and OpenSSL steps;
- durable pause/resume and needs-input packets;
- improved recovery reports;
- no Codex dependency while Codex remains disabled.

### Optional local coding

- use managed patch preview/apply only after G0;
- start with small, low-risk changes;
- require diff, validation, rollback identity, and commit evidence;
- expand scope only from proven acceptance data.

### Dashboard

- preserve visibility-first design;
- add executable-profile and remote-controller state;
- show protected-artifact references without exposing their contents;
- add write controls only after execution gates are complete.

### Codex re-enable path

Codex may be re-enabled later as an optional coding escalation only after an explicit operator decision. Re-enabling requires config validation, process-launch tests, and confirmation that local orchestration remains the default. No current batch depends on it.

## Validation Policy

For code batches:

1. run the smallest affected tests first;
2. run adjacent integration tests;
3. run `git diff --check`;
4. run the full suite and `python -m pip check` at milestone exit gates or when shared runtime behavior changes materially;
5. perform real Windows process tests for local durable execution;
6. perform disposable-host tests for remote lifecycle behavior;
7. commit each completed change locally;
8. do not push without explicit instruction.

For documentation-only batches:

- inspect the exact diff;
- run `git diff --check`;
- confirm a clean worktree after the local commit;
- do not run the full suite unless the documentation change affects generated/runtime behavior.

## Program Exit Gates

### Managed editing gate

- mixed-line-ending files can be edited without unrelated churn;
- preview/apply/revert restores exact hashes;
- R2 server forwarding is complete.

### Unrestricted OpenSSL gate

- an explicitly enabled permissive profile exposes all OpenSSL-native commands and options without filtering;
- arbitrary paths, environment, providers, config, engines, network targets, and binary I/O work within service-account permissions;
- execution uses the configured absolute executable and `shell=False`;
- durable lifecycle, cancellation, and protected artifacts remain correct.

### Remote execution gate

- registered permissive hosts support unrestricted root shell and unrestricted OpenSSL;
- long execution survives bridge restart;
- remote jobs are adopted from fresh authoritative state;
- exact process groups and descendants can be cancelled;
- transfer, resource, environment, publication, and cleanup evidence is complete.

### Final control-plane gate

- local operations, long jobs, remote jobs, and unrestricted executable profiles do not depend on Codex;
- ChatGPT can inspect, launch, monitor, cancel, and continue work through durable reports;
- dangerous capabilities are explicit, operator-enabled, auditable, and bounded only by their declared engineering and operating-system boundaries;
- UI and local-model expansion do not outrun execution correctness.
