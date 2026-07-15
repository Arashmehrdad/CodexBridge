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

The immediate program is no longer feature expansion through increasingly narrow wrappers. It is:

1. finish byte-safe managed editing;
2. transition active execution development to the `permissive` profile only;
3. add the minimum generic executable substrate required to launch PowerShell durably;
4. make unrestricted local PowerShell the single arbitrary-command engineering gateway;
5. allow unrestricted PowerShell to run any command, executable, script, shell, module, cmdlet, or child process available to the service account, including SSH, Git, OpenSSL, Docker, Python, package managers, compilers, and user-installed programs;
6. add durable fire-and-return parallel PowerShell command groups that launch multiple independent commands concurrently;
7. migrate callers and remove redundant restricted and per-executable execution tools after parity is proven;
8. complete transfer, durable remote ownership, resource, environment, and acceptance work;
9. return to local-model, memory, dashboard, and optional local-coding expansion only after execution correctness is proven.

## Governing Engineering Principles

### Durable before powerful

Every accepted asynchronous operation must have durable launch intent, ownership identity, lease state, cancellation state, output locations, and terminal publication semantics before it is considered production-ready.

### Permissive-only active execution policy

- `permissive` is the only execution profile receiving new capability work.
- `readonly` and `chatgpt_delegated` are frozen compatibility profiles. Do not add new commands, transports, policy branches, tests, or documentation solely to expand them.
- Existing callers may continue to load the frozen profiles until the C1 migration and cleanup batch proves they are unused and removes them safely.
- `human_only` remains a classification for managed CodexBridge tools. It is not a reliable boundary inside an unrestricted PowerShell session.

### Operator risk acceptance

The operator may durably enable a permissive capability and accept its risk once in configuration. After that capability is enabled, CodexBridge should not repeatedly ask for per-invocation approval.

The generic executable substrate exists only to launch the configured PowerShell executable durably and directly. It is not a product-level requirement to create separate unrestricted profiles for every program PowerShell can invoke.

Unrestricted PowerShell is an explicit operator override and the single arbitrary-command gateway. It can run any command, executable, script, shell, cmdlet, function, module, provider, or child process available to the service account, including SSH, Git, OpenSSL, Docker, Python, package managers, compilers, deployment tools, network clients, service controls, and user-installed programs. CodexBridge must not filter commands by executable name, command type, verb, arguments, path, destination, or purpose after this profile is enabled. The service account, Windows security model, remote credentials, installed software, and host permissions are the effective boundaries.

### Direct process launch where possible

CodexBridge launches the configured absolute PowerShell executable directly with `shell=False`. PowerShell is intentionally an unrestricted command interpreter and may create arbitrary child processes, invoke other shells, or launch any installed executable available to the service account.

The direct launch prevents an additional accidental `cmd.exe` or local shell layer. It does not restrict what an enabled unrestricted PowerShell process can do, and it does not require separate CodexBridge gateways for SSH, Git, OpenSSL, Docker, Python, or other commands.

### Full evidence, bounded public output

The durable run directory may contain complete stdout, stderr, binary output, inputs, hashes, and execution metadata. Public MCP responses remain bounded and may redact sensitive material. Permissive execution does not imply automatic disclosure of private keys, passwords, or binary artifacts in chat.

### Small independent batches

Every completed repository change is locally committed. Each batch must be independently reviewable and validated. Do not combine patch-engine repair, unrestricted PowerShell, OpenSSL enablement, cleanup, remote durability, and acceptance testing into one broad refactor. Do not push unless explicitly requested.

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

G0 closed the mixed-line-ending managed-patch blocker. The remaining R2 server forwarding change is the first active G1 unit.

## Revised Implementation Order

## G0 - Byte-Safe Managed Patch Engine

Status: **complete**.

Checkpoint (2026-07-15):

- Exact-text, line-range, unified-diff, and Python-AST edits preserve untouched mixed-line-ending bytes by default.
- Replacement text uses the target region's newline style where applicable; callers may explicitly set `preserve_newlines: false` only for legacy whole-file normalization.
- Preview results and manifests report raw changed lines, logical changed lines, and newline-only changed lines separately.
- Preserved-mode previews reject unrelated newline-only churn before any repository write.
- Focused repository-writer validation passed with `91 passed`; changed `repo_writer.py` passed `py_compile`; `tests/test_capabilities.py` passed with `5 passed`.
- The live mixed-newline `codexbridge/server.py` acceptance gate changed exactly one semantic line in commit `13479fd4317466bd4b49f34c4809473632d8e08d` and reverted it exactly in commit `ba3272925778938e93240089bfbac159c95b6709`.
- The reverted `server.py` SHA-256 is `301271cbbe32f2756917643df0bfa38ac4b47b0a65039059144c8f14796331a4`, matching the pre-apply hash; the worktree is clean and no file was rewritten solely to normalize line endings.
- G0 exit validation passed with the full repository suite at `1053 passed, 1 skipped`; `python -m pip check` found no broken requirements; `repo_writer.py` and `server.py` passed `py_compile`; `git diff --check` passed.

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

## G1 - Permissive-Only Transition and Minimal R2 Closure

Depends on G0.

Status: **in progress**.

Checkpoint (2026-07-16):

- Reviewed-script `arguments` survive both server forwarding hops: `ssh_action` -> `start_ssh_reviewed_script_async` -> `JobManager.start_ssh_reviewed_script`.
- Permissive `pwsh` arguments are covered through forced-PTY SSH command construction and the durable worker revalidation/execution path.
- `ssh.active_autonomy_profiles` can make `permissive` the only active SSH execution profile; disabled profiles fail before durable run or lock creation, and capability output distinguishes active from compatibility-only profiles.
- Implementation commits through `850907fde784707ead0d570acf150d8d70ab38d3`.
- Focused validation passed: `tests/test_ssh_worker.py` 37 passed; `tests/test_tool_gateway_models.py` 25 passed; `tests/test_job_manager.py` 56 passed. Earlier adjacent checkpoints also passed `tests/test_ssh_commands.py`, `tests/test_ssh_tools.py`, `tests/test_config.py`, and `tests/test_service_reload.py` for the forced-PTY and profile-activation changes.
- Next G1 unit: verify permissive root-shell protected full artifacts and bounded public summaries, then generate the route/config/test/document migration inventory required for C1 cleanup.

Goal: close only the server and transport gaps required for the permissive migration. Do not spend roadmap capacity expanding the frozen profiles.

Deliverables:

- Forward reviewed-script `arguments` through `ssh_action` and `start_ssh_reviewed_script_async` where the compatibility path is still needed.
- Add permissive server delegation and forced-PTY coverage for arguments and `pwsh`.
- Confirm permissive `structured`, `reviewed_script`, and `root_shell` paths remain usable during migration.
- Add configuration that makes `permissive` the only active execution profile for this installation.
- Mark `readonly` and `chatgpt_delegated` as compatibility-only and collect their remaining callers for C1 removal.
- Do not add new feature behavior to either frozen profile.

Acceptance:

- Permissive request arguments survive model -> server -> manager -> worker -> SSH command unchanged.
- Permissive root shell retains protected full artifacts and bounded public summaries.
- Frozen profiles either preserve their existing behavior unchanged or fail cleanly when disabled.
- A generated migration inventory identifies every route, config field, test, and document eligible for C1 cleanup.

## X1 - Minimal Durable PowerShell Launch Contract

Goal: create the reusable durable process substrate needed to launch unrestricted PowerShell directly. Do not expand this batch into separate unrestricted product gateways for executables that PowerShell can already run.

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

- The enabled permissive PowerShell profile receives arbitrary argv and script content without filtering or reinterpretation.
- Quoting-sensitive arguments reach the child process exactly.
- Binary stdin/stdout round-trip without JSON or text corruption.
- Disabled or unregistered executable profiles fail before process creation.

## X2 - Unrestricted Local PowerShell Any-Command Gateway

Depends on X1.

Status target: primary unrestricted local engineering gateway.

Configuration example:

```yaml
executable_profiles:
  powershell:
    enabled: true
    executable_path: "C:/Program Files/PowerShell/7/pwsh.exe"
    target: local
    autonomy_profile: permissive
    unrestricted_argv: true
    unrestricted_script_text: true
    unrestricted_paths: true
    unrestricted_environment: true
    unrestricted_network: true
    unrestricted_child_processes: true
    allow_no_timeout: true
```

A separately configured `powershell.exe` profile may be supported for Windows PowerShell compatibility. CodexBridge must use the configured absolute path and must not silently substitute one PowerShell edition for another.

Required capability:

- any command means any command available to the service account: no CodexBridge allowlist or special per-program gateway is required;
- arbitrary PowerShell argv;
- arbitrary `-Command`, `-File`, `-EncodedCommand`, and stdin script content;
- arbitrary scripts, functions, modules, profiles, providers, execution-policy flags, and language features supported by the selected PowerShell executable;
- arbitrary filesystem, registry, certificate-store, environment, process, service, scheduled-task, WMI/CIM, COM, package-manager, remoting, and network operations available to the service account;
- arbitrary native child executables, including `cmd.exe`, Bash, Python, Git, OpenSSL, Docker, SSH, compilers, package managers, deployment tools, user-installed programs, and any other executable available to the service account;
- arbitrary working directory, paths, environment variables, credentials, and network targets;
- text or binary stdin and protected input files;
- bounded public output plus complete protected stdout, stderr, transcript, and binary artifacts;
- configurable timeout or no timeout;
- exact process-tree cancellation and durable restart-safe run state.

There must be no cmdlet, verb, module, script-text, argument, path, registry, service, process, child-executable, executable-name, command-type, remoting, or network-target filtering after the permissive PowerShell profile is enabled. If PowerShell can invoke it under the service account, CodexBridge must allow it.

CodexBridge may offer safer helpers for protected secrets, temporary files, transcripts, and environment references, but those helpers must not restrict the commands PowerShell can execute.

Acceptance:

- literal command text and quoting-sensitive argv reach the configured PowerShell executable unchanged;
- `-Command`, `-File`, `-EncodedCommand`, and stdin modes work;
- PowerShell can launch and wait for arbitrary native child processes;
- arbitrary filesystem paths and environment values work when Windows permissions allow them;
- a loopback network test and a harmless child-process tree prove monitoring and cancellation;
- restart reconciliation adopts a live PowerShell run without duplicate launch;
- no per-command approval is requested after the profile is enabled;
- no intermediate `cmd.exe` is created unless the submitted PowerShell command explicitly launches it.

## X2A - Durable Parallel PowerShell Command Fan-Out

Depends on X1 and X2. Remote durability features become available after R4.

Goal: provide a Codex-like parallel execution primitive by opening a configurable number of independent unrestricted PowerShell processes at the same time and returning control immediately instead of waiting for any process to finish.

Public contract:

- accept one command group containing multiple child command specifications;
- support unrestricted PowerShell children that may themselves run any available command, plus remote-controller children after remote durability is implemented;
- persist the parent group and reserve every child run ID before launching the first process;
- launch every eligible child concurrently in `all_at_once` mode;
- return the group ID and complete child run-ID list as soon as launch intents are durably accepted;
- never wait for child completion in the start response;
- expose separate status, output, events, result, retry, and cancellation operations for the group and each child;
- publish an eventual aggregate group result without blocking the original launch request.

Configuration and execution modes:

```yaml
parallel_execution:
  enabled: true
  autonomy_profile: permissive
  default_mode: all_at_once
  max_concurrent_powershell: null
  return_after: launch_accepted
  repository_lock_policy: caller_selected
```

- `max_concurrent_powershell: null` means CodexBridge imposes no product-level cap on how many unrestricted PowerShell processes may be open concurrently and attempts to launch every accepted child immediately; operating-system, account, memory, process, network, and remote-host limits remain effective.
- An optional integer `max_concurrent_powershell` sets the maximum number of simultaneously open unrestricted PowerShell processes. Additional accepted children remain durably pending until a process slot becomes available.
- A command group may request a lower per-group concurrency value, but it may not silently exceed a configured global limit unless the global value is `null`.
- `repository_lock_policy: none` allows commands to run concurrently against the same repository or directory, accepting race and corruption risk.
- `repository_lock_policy: exclusive` retains the existing repository ownership behavior where required.
- `repository_lock_policy: per_child` allows independent locks or lock-free children to be mixed in one group.
- There is no implicit ordering or dependency between children in `all_at_once` mode.

Durability and lifecycle:

- create a durable group launch intent before any child process is created;
- assign each child an idempotency key, run ID, lease token, lease generation, and process identity;
- track `pending`, `launch_pending`, `running`, `completed`, `failed`, `cancelled`, and `recovery_pending` independently per child;
- track aggregate counts and group state without treating one child failure as implicit cancellation of the others;
- support group policies `continue_all`, `cancel_remaining_on_failure`, and `cancel_group_on_request`, with `continue_all` as the permissive default;
- survive CodexBridge restart by reconciling and adopting every verifiably active child independently;
- prevent restart reconciliation from launching a duplicate child whose process or remote controller already exists;
- allow cancellation of one child, all active children, or pending children only;
- preserve independent stdout, stderr, transcripts, binary artifacts, and terminal results;
- stream or query interleaved group events without merging child output into an ambiguous shared stream.

The implementation must use independent durable child runs rather than relying solely on PowerShell background jobs inside one host process. A PowerShell child may itself create jobs or processes, but CodexBridge group ownership must remain outside that child so one host failure does not erase the state of the other commands.

Acceptance:

- with `max_concurrent_powershell: 8`, eight independent unrestricted PowerShell processes can be opened concurrently and receive eight reserved child IDs before launch completion;
- when more than eight children are accepted under that configuration, excess children remain durably pending and launch as process slots become available;
- with `max_concurrent_powershell: null`, all accepted children enter `launch_pending` or `running` without waiting for the first child to finish;
- the start call returns while slow children are still running;
- children can run different arbitrary commands concurrently through independent unrestricted PowerShell processes;
- one failing child does not stop successful siblings under `continue_all`;
- individual and whole-group cancellation target exact verified process trees;
- service restart adopts all surviving children without duplicate launch;
- `max_concurrent_powershell: null` demonstrates that the number of simultaneously open PowerShell processes is constrained only by the operating system and service account;
- caller-selected lock-free execution can run multiple commands against the same working tree, with the accepted race risk recorded in durable metadata;
- group status and final summary accurately report every child outcome and artifact reference.

## X3 - Optional Specialist Executable Profiles

Status: **optional after X2 acceptance; not required for unrestricted command capability**.

PowerShell already provides unrestricted access to SSH, Git, OpenSSL, Docker, Python, and every other executable available to the service account. Separate direct executable profiles may be added later only when they provide measurable value such as binary-stream ergonomics, exact native argv APIs, lower launch overhead, or specialized artifact handling. They must not be prerequisites for running those commands through PowerShell.

The former direct OpenSSL design is retained below only as an optional specialist example, not as a required roadmap gate.

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

- `openssl version -a` records executable and library identity;
- random binary generation round-trips as a protected artifact;
- key, CSR, and certificate workflows complete in an isolated test directory;
- custom config and provider options reach OpenSSL unchanged;
- a local loopback `s_server`/`s_client` test proves network and cancellation behavior without relying on the public internet;
- arbitrary output paths work when Windows permissions allow them;
- no shell process is created for ordinary direct OpenSSL execution.

## C1 - Permissive-Only Migration and Tool Cleanup

Depends on X2 and X2A acceptance. Optional specialist executable profiles are not prerequisites. Cleanup must follow replacement, not precede it.

Goal: remove restrictive and duplicated execution surfaces that no longer provide value once unrestricted PowerShell and direct executable profiles are proven.

Create a capability and call-site inventory, then migrate active callers to the smallest retained substrate. Candidate removals include:

- `readonly` and `chatgpt_delegated` execution-profile routing, configuration, policy branches, fixtures, and documentation;
- restricted local command wrappers superseded by unrestricted PowerShell;
- duplicated reviewed-script wrappers where PowerShell, direct executable profiles, or remote root shell provide complete parity;
- bounded administration wrappers whose only remaining purpose is command filtering;
- obsolete command-profile definitions, approval paths, compatibility adapters, tests, and examples;
- stale generated artifacts and registered temporary files created by removed tools.

Retain these core controls even in permissive-only mode:

- repository query, preview, apply, revert, move, and commit primitives;
- durable run state, leases, process identity, reconciliation, cancellation, locks, and events;
- configuration validation and reload;
- SSH transport, remote controller, transfer, and staging primitives;
- protected artifacts, return-loop publication, and audit metadata;
- workflows, supervisors, status, and recovery tooling;
- durable parallel command groups and independent child-run controls;
- unrestricted PowerShell as the single arbitrary-command gateway; optional specialist executable profiles only where independently justified.

Do not delete durable run history or protected evidence merely because its originating tool was removed. Add an explicit retention/cleanup policy instead.

Acceptance:

- a before/after capability matrix proves every removed tool is replaced or intentionally abandoned;
- active configuration contains only `permissive` execution routing;
- removed route names have no runtime call sites, schemas, tests, docs, or stale config fields;
- configuration migration is deterministic and rollback-capable;
- managed temporary artifacts from removed tools can be previewed and cleaned without deleting durable evidence;
- full tests, `python -m pip check`, `git diff --check`, and live unrestricted-PowerShell/parallel-fan-out smoke tests pass after cleanup, including PowerShell launching SSH, Git, OpenSSL, and other representative executables.

## R3 - Transfer Policy and Managed Staging

Goal: provide predictable transfer scope for reviewed scripts, executable profiles, and remote controllers.

Active policy:

- `unrestricted`: arbitrary paths available to the service account or registered remote user under the enabled permissive profile.

`repo_only` and `configured_roots` remain frozen compatibility policies only until C1 removes them or a retained non-execution subsystem proves it still requires them. Do not add new behavior to either policy.

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

## X4 - Unrestricted Remote PowerShell

Depends on X2, R3, and R4.

Goal: expose unrestricted PowerShell on registered permissive remote hosts so it can run any command available to the configured remote account.

Deliverables:

- remote PowerShell executable identity and version capture;
- arbitrary PowerShell command text, argv, scripts, modules, paths, environment, child processes, remoting, and network targets;
- arbitrary SSH, Git, OpenSSL, Docker, Python, package-manager, compiler, deployment, and other executable invocation through PowerShell when available to the remote account;
- binary-safe staged and streamed input/output;
- remote protected artifacts and local publication manifests;
- restart adoption and exact process-group cancellation;
- optional elevated or root execution only through explicitly configured credentials, remote-user policy, or the separate permissive root-shell gateway.

Acceptance:

- local and remote PowerShell profiles share one request/result contract;
- remote execution survives bridge restart;
- arbitrary PowerShell child-process and loopback network tests pass on the disposable host;
- representative SSH, Git, OpenSSL, and other native commands run successfully through PowerShell;
- no PowerShell command text, child executable, or child argument is silently removed, rewritten, or filtered.

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

Permissive PowerShell and OpenSSL remain able to use literal environment values, inline credentials, command-line password options, or any other mechanism their native command languages support when the operator chooses. Reference delivery is the recommended path, not a forced limitation.

Acceptance:

- missing references fail before child launch;
- secret values do not appear in public events or summaries when references are used;
- temporary material is removed or conservatively reported for repair after crashes;
- environment values reach local and remote PowerShell and OpenSSL unchanged.

## R7 - Provider-Neutral Disposable-Host Acceptance Gate

Goal: prove the complete contract on a disposable host before paid or workload-specific use.

The generic suite must prove:

- native endpoint access and capability discovery;
- permissive-only active routing and clean rejection of removed profiles;
- unrestricted transfers;
- unrestricted local and remote PowerShell profiles;
- arbitrary PowerShell command text, modules, paths, environment, child processes, and network operations;
- fire-and-return parallel groups with multiple local and remote children launched concurrently;
- restart adoption, individual cancellation, group cancellation, mixed outcomes, and aggregate reporting for parallel groups;
- unrestricted permissive root shell;
- unrestricted local and remote PowerShell running representative native commands such as SSH, Git, OpenSSL, Docker, and Python without per-program gateways;
- arbitrary child-executable arguments, paths, environment values, and network targets;
- binary input/output and protected artifact publication;
- execution longer than one hour;
- service restart survival and remote reattachment;
- absolute resource enforcement and permissive overrides;
- exact verified process-tree cancellation;
- durable result, report, return-loop, and cleanup evidence;
- absence of runtime references to tools removed by C1.

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
- reusable unrestricted PowerShell, direct executable, OpenSSL, and parallel fan-out steps;
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

### Unrestricted PowerShell gate

- an explicitly enabled permissive profile exposes arbitrary PowerShell command text, argv, scripts, modules, paths, environment, child processes, remoting, and network operations without filtering;
- the configured absolute PowerShell executable is launched directly with `shell=False`;
- the service account and operating system are acknowledged as the effective security boundary;
- durable lifecycle, restart adoption, exact process-tree cancellation, transcripts, and protected artifacts remain correct;
- no per-command approval is requested after enablement.

### Parallel execution gate

- one start request can durably reserve and launch multiple independent child commands concurrently;
- the start response returns group and child IDs without waiting for any child to finish;
- `max_concurrent_powershell` controls the number of simultaneously open unrestricted PowerShell processes, and a `null` value removes the CodexBridge product-level cap;
- each child retains independent process identity, leases, output, artifacts, status, cancellation, and restart adoption;
- group restart reconciliation does not duplicate surviving children;
- group and individual cancellation target exact verified process trees;
- lock-free same-repository execution is available when explicitly selected and its race risk is recorded;
- aggregate status and final results preserve mixed child outcomes without obscuring individual evidence.

### Permissive-only cleanup gate

- `permissive` is the only active execution profile;
- frozen profile routes and redundant restricted wrappers are removed after caller migration;
- core durability, repository, transport, artifact, status, and recovery controls remain;
- no stale schemas, config fields, tests, docs, or registered temporary artifacts remain for removed tools;
- durable historical evidence is retained under an explicit retention policy.

### Remote execution gate

- registered permissive hosts support unrestricted PowerShell that can run any command available to the configured account, plus durable SSH transport and root-shell/controller facilities where remote ownership requires them;
- long execution survives bridge restart;
- remote jobs are adopted from fresh authoritative state;
- exact process groups and descendants can be cancelled;
- transfer, resource, environment, publication, and cleanup evidence is complete.

### Final control-plane gate

- local operations, long jobs, remote jobs, and unrestricted PowerShell do not depend on Codex;
- only the permissive execution profile remains active;
- ChatGPT can inspect, launch, monitor, cancel, and continue work through durable reports;
- ChatGPT can launch multiple independent commands concurrently and receive control immediately with durable group and child IDs;
- unrestricted PowerShell is explicit, operator-enabled, auditable, and permits any command available to the service account without CodexBridge command allowlists;
- UI and local-model expansion do not outrun execution correctness.
