# Soma Roadmap V2 Achievement Record

> Preservation snapshot created on 2026-07-18 from `PLANS.md` at commit
> `d1c43340af48c03ca31505ef64f4c6a60248f61c`. The roadmap below is retained
> verbatim as historical implementation, validation, and decision evidence.
> It is not the active execution order. See [`../PLANS.md`](../PLANS.md) for
> current work.

---

# Soma Unified Engineering Roadmap

## Executive Direction

Soma is a local engineering control plane between ChatGPT and the user's machines, repositories, services, and remote hosts.

The target operating model is:

```text
ChatGPT
  -> Soma MCP
  -> local policy and orchestration
      -> repository inspection and managed patching
      -> durable command and executable runs
      -> workflows and supervisors
      -> local model and project memory
      -> SSH and remote controllers
      -> return-loop reports
      -> external-coder handoffs (manual use only)
```

Codex execution has been removed from Soma entirely (2026-07-23); coding work is handed off manually through provider-neutral external-coder handoffs. Repository changes continue through managed preview/apply tools and explicit local commits.

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

- `permissive` is the only active execution profile and the only profile that may receive execution capability work.
- C1 removed legacy execution-profile routing from active configuration, runtime schemas, policy evaluation, workers, and public capability output. Removed names may remain only in negative validation tests or historical migration evidence.
- General permission tiers, delegated-approval terminology, and supervisor planning profiles are separate policy concepts and are not compatibility execution routes.
- `human_only` remains a classification for managed Soma tools. It is not a reliable boundary inside an unrestricted PowerShell session.

### Operator risk acceptance

The operator may durably enable a permissive capability and accept its risk once in configuration. After that capability is enabled, Soma should not repeatedly ask for per-invocation approval.

The generic executable substrate exists only to launch the configured PowerShell executable durably and directly. It is not a product-level requirement to create separate unrestricted profiles for every program PowerShell can invoke.

Unrestricted PowerShell is an explicit operator override and the single arbitrary-command gateway. It can run any command, executable, script, shell, cmdlet, function, module, provider, or child process available to the service account, including SSH, Git, OpenSSL, Docker, Python, package managers, compilers, deployment tools, network clients, service controls, and user-installed programs. Soma must not filter commands by executable name, command type, verb, arguments, path, destination, or purpose after this profile is enabled. The service account, Windows security model, remote credentials, installed software, and host permissions are the effective boundaries.

### Direct process launch where possible

Soma launches the configured absolute PowerShell executable directly with `shell=False`. PowerShell is intentionally an unrestricted command interpreter and may create arbitrary child processes, invoke other shells, or launch any installed executable available to the service account.

The direct launch prevents an additional accidental `cmd.exe` or local shell layer. It does not restrict what an enabled unrestricted PowerShell process can do, and it does not require separate Soma gateways for SSH, Git, OpenSSL, Docker, Python, or other commands.

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

Codex prompt transport was historically repaired and validated in T1, later disabled by configuration, and finally removed entirely (2026-07-23) together with the Codex CLI runner, gateways, and router. Soma now generates provider-neutral external-coder handoffs for manual use with any coding agent; historical `codex_plan_task` / `codex_implement_task` records remain readable as legacy read-only run types. The roadmap remains executable without any coding-agent integration.

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
- The live mixed-newline `soma/server.py` acceptance gate changed exactly one semantic line in commit `13479fd4317466bd4b49f34c4809473632d8e08d` and reverted it exactly in commit `ba3272925778938e93240089bfbac159c95b6709`.
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

Status: **complete**.

Checkpoint (2026-07-16):

- Reviewed-script `arguments` survive both server forwarding hops: `ssh_action` -> `start_ssh_reviewed_script_async` -> `JobManager.start_ssh_reviewed_script`.
- Permissive `pwsh` arguments are covered through forced-PTY SSH command construction and the durable worker revalidation/execution path.
- `ssh.active_autonomy_profiles` makes `permissive` the only active SSH execution profile for this installation; disabled profiles fail before durable run or lock creation, and capability output distinguishes active from compatibility-only profiles.
- Permissive root-shell execution now writes complete filesystem-protected stdout/stderr artifacts while the durable/public result remains redacted and bounded.
- `docs/permissive-migration-inventory.md` records the remaining runtime, configuration, test, fixture, documentation, and restricted-wrapper candidates for C1, while preserving the distinction between autonomy profiles and delegated-approval terminology.
- Implementation commits through `f10fd12b1815b0729d8bfa71d9d90d92a121746d`.
- Focused validation passed: `tests/test_ssh_worker.py` 37 passed; `tests/test_tool_gateway_models.py` 25 passed; `tests/test_job_manager.py` 56 passed. Earlier adjacent checkpoints also passed `tests/test_ssh_commands.py`, `tests/test_ssh_tools.py`, `tests/test_config.py`, and `tests/test_service_reload.py` for the forced-PTY and profile-activation changes.
- Next roadmap unit: X1 minimal durable PowerShell launch contract.

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

Status: **complete**.

Checkpoint (2026-07-16):

- Added validated executable-profile configuration for absolute executable identity, target, working directory, environment, stdin/stdout/stderr, timeout, cancellation, protected artifacts, public-output limits, and permissive-only invocation.
- Executable resolution rejects disabled, missing, remote, symlinked, non-file, and SHA-256-mismatched profiles before child creation.
- Durable executable requests persist the verified executable identity, exact argv, working directory, environment, binary-safe stdin, timeout policy, and artifact/publication policy before launch.
- The worker revalidates persisted identity and policy, launches `[absolute_executable, *exact_argv]` directly with `shell=False`, attaches the child PID, streams complete binary stdout/stderr artifacts, bounds public summaries, and applies exact process-tree timeout termination.
- Lifecycle regressions prove quoting-sensitive argv preservation, binary stdin/stdout round-trip, protected artifact completeness, pre-launch identity-drift rejection, child termination after failed durable attachment, and verified timeout terminal state.
- Implementation commits through `6383466c69140d524a19b4f9731c942dab2817fe`.
- Focused validation passed: `tests/test_executable_profile_worker.py` 4 passed; `tests/test_executable_profiles.py` 5 passed; `tests/test_job_manager.py` 56 passed.
- Next roadmap unit: X2 unrestricted local PowerShell any-command gateway.

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

Status: **complete**.

Checkpoint (2026-07-16):

- Published `operation: powershell` through the public `run_start` gateway, defaulting to the configured `powershell` executable profile while allowing an explicitly selected compatible PowerShell profile.
- The gateway forwards exact argv, arbitrary working directory, arbitrary environment values, text stdin, strict base64-decoded binary stdin, and timeout/no-timeout selection into the existing durable executable-profile lifecycle without command, cmdlet, path, child-executable, or network filtering.
- Strict discriminated request validation rejects cross-operation fields and simultaneous text/binary stdin before durable launch; malformed base64 fails before process creation.
- Implementation commits: `f5933c3bc8b695d6f129e692bc43fbb9619a1476` and `e01cea33dbae7eef0c30002f67990b3a97e55b3c`.
- Focused validation passed: `tests/test_tool_gateway_models.py` 26 passed; `tests/test_server.py` 27 passed; `tests/test_executable_profiles.py` 5 passed.
- Live configured PowerShell 7 acceptance now proves `-Command`, `-File`, `-EncodedCommand`, stdin script execution, explicit native `cmd.exe` child launch, arbitrary working directories and environment values, filesystem paths containing spaces, and loopback TCP networking through the durable worker with complete protected artifacts.
- Implementation commits for the live acceptance matrix: `580336caa206dce743a33d8560f1da178ceadf56`, `84e02819b4cf57c7445ddd29c1e9ab9a942257b1`, `fbd8f25072404dbe79bf31d96102d1aee353fa1b`, and `1846f676b2df3d4af92e77126007f402353c091d`.
- Live validation passed: `tests/test_powershell_acceptance.py` 3 passed.
- Live harmless PowerShell process-tree cancellation now proves the PowerShell parent and its native child are both terminated through exact process-tree control; implementation commit: `eac0148af7dec606ee2f9238251f949b9e1840d1`.
- Restart reconciliation coverage proves a verified active worker is adopted, its repository lock is reclaimed, and no replacement worker is launched; `tests/test_job_manager.py::test_reconcile_startup_adopts_verified_active_worker` remains the canonical regression.
- Final X2 validation: `tests/test_powershell_acceptance.py` 4 passed and the adjacent job-manager reconciliation suite passed.
- The active local `config.yaml` now enables the absolute PowerShell 7 permissive profile with unrestricted argv, paths, environment, network, child processes, binary input, protected output, no-timeout support, and process-tree cancellation; configuration validation and hot reload passed on 2026-07-16.
- Next roadmap unit: X2A durable parallel PowerShell command fan-out.

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

A separately configured `powershell.exe` profile may be supported for Windows PowerShell compatibility. Soma must use the configured absolute path and must not silently substitute one PowerShell edition for another.

Required capability:

- any command means any command available to the service account: no Soma allowlist or special per-program gateway is required;
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

There must be no cmdlet, verb, module, script-text, argument, path, registry, service, process, child-executable, executable-name, command-type, remoting, or network-target filtering after the permissive PowerShell profile is enabled. If PowerShell can invoke it under the service account, Soma must allow it.

Soma may offer safer helpers for protected secrets, temporary files, transcripts, and environment references, but those helpers must not restrict the commands PowerShell can execute.

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

Status: **complete**.

Checkpoint (2026-07-16):

- Added a durable command-group store backed by the existing SQLite run database.
- Parent group metadata and every child run row are inserted in one immediate transaction before any worker process can be created; initially eligible children use `launch_pending`, while concurrency-throttled children use the non-recoverable `pending` state.
- Every child reservation persists its run ID, position, idempotency key, independent worker lease token, exact executable-profile input, and run-directory identity.
- Duplicate child run IDs or idempotency keys are rejected, and any database conflict rolls back the parent plus every newly inserted sibling.
- Added a two-phase PowerShell group launcher that validates every child specification before reservation, reserves the complete group atomically, materializes every protected child input and launch event, and only then spawns eligible workers.
- Connected the two-phase launcher to `JobManager.start_powershell_group` and the public `run_start` contract as `operation: powershell_group`, including strict nested child models, per-child text or base64 binary stdin, optional lower requested concurrency, and lock-free policy validation.
- `max_concurrent_powershell` and a lower per-group request limit determine the initial eligible set; excess accepted children remain durable in `pending` without a worker or startup-reconciliation eligibility.
- Validation failures occur before group or child persistence, and individual worker-launch failures are recorded against the affected child without preventing later eligible siblings from launching.
- Full-suite validation after the public group connection and ninth action-discovery variant passed with `1084 passed, 1 skipped`; `python -m pip check` found no broken requirements and `git diff --check` passed.
- Focused X2A validation passed: `tests/test_parallel_groups.py` 6 passed; `tests/test_tool_gateway_models.py` 27 passed; manager delegation regression 1 passed; pending-child cancellation regression 1 passed; public action-discovery regression 1 passed.
- Implementation commits through `f6a77513ef842dd1de0ac97e313bd2cf940786e5`; roadmap evidence checkpoint `247917750cafedab0b0a1017a8fe2328fbc34b57`.
- Added atomic slot refill across all durable command groups. One `BEGIN IMMEDIATE` transaction counts globally active group children, enforces both `max_concurrent_powershell` and lower per-group limits, and promotes only ordered `pending` rows to `launch_pending` with a state-version bump.
- Claimed children launch through lease- and state-version-checked worker creation. A competing refill cannot claim them twice, and a lost launch claim terminates the duplicate launcher before recording infrastructure failure.
- Worker terminal completion triggers refill without masking the completed child's result; startup reconciliation also refills available slots after active-worker adoption and terminal-result repair.
- Focused refill validation passed: `tests/test_parallel_groups.py` 8 passed; `tests/test_job_manager.py` 58 passed; `parallel_groups.py` and `job_worker.py` passed `py_compile`.
- Slot-refill implementation commits: `b49f9af060787ef0ef07087bedd888423da3a568`, `7489f5f651c97a350acfaea2be137554cd2935aa`, and `2b9be8791a68de94fbfe2651073faf1ea00bbda5`.
- Durable aggregate publication now derives group state, per-status counts, terminal counts, timestamps, and ordered child summaries from the authoritative child rows and persists the snapshot in `command_groups.result_json`.
- Aggregate state is refreshed during slot refill and startup reconciliation, so terminal children cannot leave the parent permanently stale.
- `JobManager` now exposes durable group status and whole-group cancellation. Whole-group cancellation targets pending children before active children, suppresses intermediate refill, reuses exact child process-tree cancellation, then performs one final refill and aggregate publication. Direct child cancellation also releases a PowerShell slot.
- Focused validation passed: `tests/test_parallel_groups.py` 10 passed; `tests/test_job_manager.py` 59 passed; `parallel_groups.py` passed `py_compile`.
- Aggregate/cancellation implementation commits: `d9eb389a38945832fd7db2e9b43f6fb1e90ea66c`, `d9d3a40288fb35dcad372200846c927682430647`, and `d63eac68c350c60728a090e5682e1b8623b26b05`.
- Public group lifecycle access is now exposed through the existing gateways: `run_query` supports strict `group_status` and `group_result` operations, while `cancel_run` routes durable `powershell_group` IDs to exact whole-group cancellation without introducing another public tool.
- Focused public-gateway validation passed: `tests/test_tool_gateway_models.py` 29 passed and `tests/test_server.py` 27 passed.
- Public group gateway commits: `abfeb5d5c1d85e0323131a172c5127ae053bc232` and `4535ff92a283cf9a6b5e79843ffd14170982542d`.
- Live Windows acceptance now proves capped fan-out leaves excess children durably pending, terminal completion refills the released slot, and every child completes with independent artifacts.
- The live gate exposed and fixed a lock-policy defect: `repository_lock_policy: none` children no longer require operation-lock claim or heartbeat in the worker, and restart reconciliation no longer forces lock-free adopted workers into `recovery_pending`.
- Restart acceptance verifies the active child keeps the same worker PID and launch-attempt count, while the pending sibling remains pending until the adopted child releases its slot.
- Uncapped acceptance with `max_concurrent_powershell: null` launches every child immediately; a deliberate failing child does not stop successful siblings under `continue_all`.
- Focused validation passed: `tests/test_parallel_groups.py` 11 passed; `tests/test_parallel_powershell_acceptance.py` 3 passed.
- Live acceptance and lock-free adoption commits: `2e23f69adef94ae0ad26fc7c073bd4dfab2f074e`, `d47fd07ff85526958a55c06d3e85f7ed8e1d2013`, `8eca429f1511107f6c4e23c0bac1cd21e2c3702d`, `0c842866cb1aaacd1d69e390969e55f61cafa8e5`, and `04d0564a77a753c9d114ec6ba1a4ca99293bdef7`.
- Live cancellation acceptance now proves whole-group cancellation terminates the exact active PowerShell/native-child process tree, cancels durably pending siblings, publishes terminal child results, and preserves complete protected stdout/stderr artifacts. Individual-child cancellation also releases the slot so a pending sibling launches and completes independently.
- Aggregate group child summaries now publish bounded protected artifact references derived from each terminal child result without merging child output.
- Cancellation and aggregate-artifact commits: `e99d4741c7705cafebc68c8b442a7db8f4e73f0d` and `4eea0bc09ee897539de505fdd25ab035b8520347`.
- Focused validation passed: `tests/test_parallel_powershell_acceptance.py` 5 passed; `tests/test_parallel_groups.py` 11 passed; `parallel_groups.py` passed `py_compile`.
- Added and passed the explicit `max_concurrent_powershell: 8` live acceptance gate: eight independent PowerShell children reached `running` concurrently, two excess accepted children remained durably `pending`, and all ten completed after ordered slot refill.
- Final X2A validation passed: `tests/test_parallel_powershell_acceptance.py` 7 passed; full suite 1099 passed, 1 skipped; `python -m pip check` reported no broken requirements; `git diff --check` passed.
- Eight-process acceptance commit: `e5a6b3101bf784012fa65551f9b581f763a3be6a`.
- X2A acceptance is complete. Optional X3 specialist executable profiles remain deferred and are not prerequisites.
- Next roadmap unit: C1 permissive-only migration and tool cleanup.

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

- `max_concurrent_powershell: null` means Soma imposes no product-level cap on how many unrestricted PowerShell processes may be open concurrently and attempts to launch every accepted child immediately; operating-system, account, memory, process, network, and remote-host limits remain effective.
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
- survive Soma restart by reconciling and adopting every verifiably active child independently;
- prevent restart reconciliation from launching a duplicate child whose process or remote controller already exists;
- allow cancellation of one child, all active children, or pending children only;
- preserve independent stdout, stderr, transcripts, binary artifacts, and terminal results;
- stream or query interleaved group events without merging child output into an ambiguous shared stream.

The implementation must use independent durable child runs rather than relying solely on PowerShell background jobs inside one host process. A PowerShell child may itself create jobs or processes, but Soma group ownership must remain outside that child so one host failure does not erase the state of the other commands.

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

Passwords and key material may be supplied by any method OpenSSL supports. Soma should additionally offer protected stdin, temporary file, and environment-reference paths so the operator is not forced to expose secrets on the process command line. This is an ergonomic protection, not a restriction on OpenSSL capability.

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

Status: **complete**.

Checkpoint (2026-07-16 through 2026-07-17):

- Added a before/after capability matrix covering compatibility SSH autonomy routing, local project-command surfaces, reviewed-script and administration wrappers, and durable evidence retention.
- New `SSHConfig` instances and `config.example.yaml` now activate only `permissive`; explicit legacy profile lists remain loadable during the deterministic migration window.
- Focused configuration validation passed with `tests/test_config.py` at 22 passed.
- Configuration validation now emits a deterministic `ssh_active_autonomy_profiles_v1` migration report for explicitly configured legacy SSH profiles, including the configured order, detected legacy values, the permissive-only replacement, rollback data, and an explicit durable-history preservation guarantee.
- Migration-report validation passed with `tests/test_config.py` at 22 passed and `tests/test_service_reload.py` at 7 passed; implementation commit `6bcf03bdbba17f3032716a301e96ad94c9fddd65`.
- The SSH active-profile schema and runtime authorization gate are now permissive-only; legacy configured values are rejected deterministically before durable run or lock creation. The public supervisor request schema was also narrowed without changing delegated-approval terminology. Implementation commits: `0e4e0442d3a961d8baf096bbfac82128edbcb44a` and `1d2f1be1e7dace2305fd2fc78e4e85c8f0246d0b`.
- Focused validation: `tests/test_config.py` 22 passed.
- Retained SSH manager, server, and public gateway defaults now select `permissive`; active behavior tests were migrated accordingly, while removed-profile requests still prove deterministic rejection before durable run or lock creation. Implementation commits: `96e76d95dfa86316b9b5c402b5c17a9f6acb478e`, `9f33d33eaa300e4b1e77af033ab1beb7a7634852`, and `9ada9b7428b57362755c7b5aa71b43cca07b9970`.
- Focused validation passed: `tests/test_job_manager.py` 59 passed; `tests/test_server.py` 27 passed; `tests/test_tool_gateway_models.py` 29 passed; `tests/test_mcp_action_discovery.py` 31 passed.
- The SSH gateway autonomy-profile type and policy matrix are now permissive-only across structured, reviewed-script, and root-shell modes; removed legacy values fail strict validation before authorization. Capability output no longer advertises compatibility-only SSH profiles. Implementation commits: `786485b348da652ad8eee79cc0a4d4165767c898`, `744de1b73cfdd30dea725f7d637ae0cf60d85394`, `a759e1e76a047ca04f194565e695d7d396f77952`, and `398259dee79a86b7cfbb0877be792950a0fd60cb`.
- Focused validation passed: `tests/test_ssh_policy.py` 32 passed; `tests/test_tool_gateway_models.py` 29 passed; `tests/test_ssh_tools.py` 13 passed.
- Persisted SSH worker fixtures and canonical policy assertions now use `permissive` for active command, reviewed-script, action, transfer, and deployment paths. Removed-profile and tampered-policy cases still prove deterministic rejection, while `T6_HUMAN_ONLY_RISKY_ACTION` deployment evidence remains human-authorized. Implementation commits: `7116775a28ed4c05d8df8af890d0a7c2ed186cf9`, `1b1c44d6a0d4051725cfc5c7580b19c5c5cbd6c8`, and `05a6c095acb436e088877c9b21bf6aa14d9203a4`.
- Focused validation passed: `tests/test_ssh_worker.py` 37 passed.
- Server SSH helper annotations are now permissive-only, including the deployment helper default; the unrelated supervisor autonomy default remains unchanged. Persisted generic SSH worker inputs now reject non-permissive autonomy values before policy evaluation while preserving stable validation wording. Implementation commits: `0bfacd439f0a60fe9913d4278c0b79f7304fc194`, `d2adf4a0d933ae14f4138bb95733865c4322bd6d`, `984fb4ea17f59bd0f4bdb8be738f7bfed351fb7c`, and `95444d07c24dde4d49ef73f7746917e96045bd41`.
- Focused validation passed: `soma/server.py` py_compile; `tests/test_server.py` 27 passed; `tests/test_ssh_worker.py` 37 passed.
- The remaining monitored-SSH worker success fixture now persists `permissive` instead of the removed `balanced` profile. Regression validation passed: the targeted worker test 1 passed; the full durable suite 1094 passed and 1 skipped. Implementation commit: `48f9591a252453040a3fd2759b2d8ea0ddde22ad`.
- The local self-check now uses a run-scoped pytest `--basetemp`, a 600-second suite allowance, and a 60-second MCP transport readiness window, eliminating the global Windows temp ACL failure and premature startup-probe timeout. Regression validation passed: `tests/test_self_check.py` 6 passed; the full durable suite 1096 passed and 1 skipped; the complete durable self-check returned `ok: true` with dependency, Git, WAL-store, permissive supervisor, and HTTP 406 MCP readiness checks all green. Implementation commit: `c6750ae1089758ff6e321c2b64b4988347a234d9`.
- The synchronous server `run_project_command` compatibility tool has been removed together with its discovery metadata, direct server/discovery tests, and README guidance. Durable workflow `project_command` steps, typed validation operations, and the independent `LocalAgentCommandRunner.run_project_command` remain intact. Implementation commit: `414acbf39d16c9baacc5d4fd4d6af5e984879ad3`.
- Focused validation passed: `soma/server.py` py_compile; `tests/test_server.py` 25 passed; `tests/test_mcp_action_discovery.py` 30 passed. A separate broad PowerShell pytest run failed only on the pre-existing global `pytest-of-arash` permission issue; isolated durable pytest runs remained authoritative.
- The active `LocalAgentCommandRunner.run_project_command` call chain is now classified. It directly serves local-agent task routing and synchronous validation in local-coding and supervisor flows. Unlike durable `JobManager` commands, it writes a separate local-agent artifact tree and has no RunStore lease, restart adoption, process-tree cancellation, repository-operation lock, or protected binary-output contract; deleting it would break callers that currently require immediate results.
- Added `DurableProjectCommandRunner`, which launches through `JobManager.start_project_command`, waits on authoritative `RunStore` state, preserves the immediate `CommandRunResult` contract, returns durable artifact references, and requests durable cancellation when the bounded synchronous wait expires. Direct lifecycle coverage proves success, nonzero exit, timeout cancellation, repository mismatch, and permission rejection. Implementation commits: `a17905253a270fe33ed14884990b22a9dad3130e`, `48323721f7dd14d8c6df4d8c72c6201f36a9b5cc`, `7fe1145419626e8dd3734b29dd520894c2d23129`, and `7f1f717cd4909d21245f180ded8c97437517ed10`.
- Local-coding and supervisor construction paths now accept the application configuration, configuration path, and shared `JobManager`, selecting `DurableProjectCommandRunner` when configured while preserving explicit runner injection and the existing immediate-result API. Implementation commits: `00bb86c0236e8d79c67a54e678b6d99731a37f80` and `f48c15adb469dd434771e042237a393777e05497`.
- Focused validation passed: `tests/test_durable_command_runner.py` 5 passed; `tests/test_local_coding_manager.py` 10 passed; `tests/test_supervisor_upgrade_flow.py` 7 passed.
- The local-agent orchestration path now accepts the live `AppConfig`, configuration path, and shared durable `JobManager`, forwards them into lazily constructed local-coding and supervisor managers, and selects `DurableProjectCommandRunner` for general project-command routing whenever application configuration is available. Explicit manager/runner injection and the no-configuration compatibility fallback remain intact. Implementation commits: `51f0cea22e68b1d846029182260c2a1a859a1f21`, `a0708bd63ff76388012f022680bb276437fcf4dc`, `a12d15cfc5c1c5f6780ecba1a8b38ec16a7f027d`, and `2fb8c6294ffd4ac44d2829bdd6391fb03449a9e8`.
- Focused validation passed: `tests/test_local_coding_local_agent.py` 4 passed; `tests/test_supervisor_upgrade_local_agent.py` 4 passed; `tests/test_local_agent_runner.py` 15 passed.
- No production `LocalAgentOrchestrator` construction site remains without durable application context; no-context instances are test-only. Accepted project-command tasks require either durable context or an explicitly injected runner implementing the structural `ProjectCommandRunner` protocol. Local-coding and supervisor flows enforce the same construction rule. Implementation commits: `36729ba16d77d03e388a1879a44ccfc0c6b8e4c8` and `da0c1d8b997975162b35814e0acfcbbe249dfc56`.
- The test-only direct-subprocess `LocalAgentCommandRunner`, standalone helper, lazy public exports, and separate `runs/local_agent/commands` artifact path have been removed. Runtime type dependencies now use the structural `ProjectCommandRunner` protocol; orchestrator behavior tests use an injected runner double, while durable lifecycle behavior remains covered by `DurableProjectCommandRunner` tests. Implementation commits: `98952d13acb589cdd3e14c1752371fc9549579f7`, `750c448dade83f7de71e758a5a146ad5708c44c3`, and `da41f7613347a5273d6533fb43b5e6a7fb23012a`.
- Focused validation passed: `tests/test_local_agent_runner.py` 6 passed; `tests/test_durable_command_runner.py` 5 passed; `tests/test_local_coding_manager.py` 11 passed; `tests/test_supervisor_upgrade_flow.py` 8 passed. Repository search found no remaining `local_agent.runner` import.
- The duplicate local-agent command-profile registry and its standalone tests are removed. `DurableProjectCommandRunner` now owns only the local permission and bounded-wait policy, while argv resolution remains authoritative in the durable core command-profile registry. Implementation commits: `76e98280d61fe059e2f09f14dfd6e2db27de6a7d`, `ce4dfa8fc3f0a898d258eb69e9250b0ae43ba3e2`, and `aafaee0015bc646af4bcc83e2e63c3b277c5841e`.
- Focused validation passed: `tests/test_durable_command_runner.py` 5 passed; `tests/test_local_agent_runner.py` 6 passed.
- The public generic `run_start(operation="project_command")` route and its internal server forwarding helper are removed. Durable `JobManager.start_project_command` remains an internal substrate for workflows and `DurableProjectCommandRunner`; typed path validation and unrestricted PowerShell remain public. Implementation commits: `7f2dee8014a3f5e88c774e2d66591b6699fb3bef` and `8b27c73c6eb755fa5ef9fa6c5f1e7ab91040a828`.
- Focused validation passed: `tests/test_tool_gateway_models.py` 29 passed; `tests/test_mcp_action_discovery.py` 29 passed; `tests/test_server.py` 25 passed.
- Built-in `ruff_check`, `ruff_format_check`, `ruff_format`, `mypy`, and duplicate `git_diff_check` profiles are removed after repository-wide call-site inspection found no runtime callers. Unrestricted PowerShell replaces ad hoc lint/format/typecheck execution, while retained `git_readonly(operation="diff_check")` provides the fixed Git validation. Repository-configured profiles remain internal durable workflow contracts because live configuration still uses them for repository-specific validation, repair, and service-management operations. Implementation commit: `21662eb3419fa2a726f20cfc30b100bd36330c32`.
- Focused validation passed: `tests/test_command_profiles.py` 59 passed.
- Live configuration inventory now classifies all repository-configured project-command profiles. Soma retains `andia_ssh_config_check`, `andia_ssh_alias_repair`, and `soma_service_restart` because they provide reviewed inspection, rollback-capable repair, or service lifecycle semantics. The Andia frontend `eslint`, `typecheck`, `vitest`, and `frontend_validate` profiles are ordinary validation commands with no tracked workflow or operational caller in this repository and are candidates for deterministic migration to unrestricted PowerShell before removal from the active external configuration.
- Configuration validation now emits deterministic `ordinary_validation_command_profiles_v1` reports for ordinary repository-configured validation profiles. Each report records the repository, candidate IDs, the complete configured profile as rollback data, an exact unrestricted-PowerShell request with working directory and timeout, and the durable-history preservation guarantee. Implementation commit: `8fcab876d4669c836e742974cb29f539de72d764`.
- Focused validation passed: `tests/test_config.py` 24 passed; `tests/test_service_reload.py` 8 passed.
- Live unrestricted-PowerShell replacement smoke evidence (2026-07-17): `typecheck` completed with exit code 0; `vitest` completed with 6 files and 20 tests passed; `frontend_validate` completed with exit code 0. The original `eslint .` replacement exposed an inaccessible pre-existing `.pytest_cache` and then a generated `output/run-production-smoke.mjs` file that is already excluded from version control. A reviewed non-destructive replacement using ESLint `--ignore-pattern .pytest_cache/** --ignore-pattern output/**` completed with exit code 0 without changing ACLs or deleting generated data.
- The four ordinary Andia validation command profiles (`eslint`, `typecheck`, `vitest`, and `frontend_validate`) are removed from active `config.yaml`. Their prior definitions remain preserved in the deterministic migration report design and roadmap evidence as rollback data; unrestricted PowerShell is now the active replacement and durable historical runs remain untouched.
- Active configuration validation and reload passed after removal. Empty ordinary-profile migrations are omitted entirely, proving deterministic absence after migration. Implementation commit: `f0b5da1e513df51e8ada297bcce2fc5213e28688`.
- Managed cleanup explicitly rejects the durable `runs` evidence root. Cleanup remains limited to registered scratch roots and requires preview, repository fingerprint, per-file hashes, regular-file validation, and idempotent application. Durable databases, runs, protected artifacts, results, events, and delivered manifests are retained.
- SSH reviewed-script, administration, transfer, and deployment surfaces remain intentionally assigned to R3/R4/X4 because they still provide remote transport, staging, and ownership behavior without replacement parity; their retention is not an incomplete C1 compatibility route.
- Final focused validation passed: `tests/test_service_reload.py` 9 passed; `tests/test_managed_artifacts.py` 5 passed; `tests/test_powershell_acceptance.py` 4 passed; `tests/test_parallel_powershell_acceptance.py` 7 passed.
- Live unrestricted-PowerShell smoke passed for Git 2.53.0, OpenSSH for Windows 9.5p2, Git-for-Windows OpenSSL 3.5.5, and Python 3.12.10. The full C1 exit gate passed with 1103 tests passed and 1 skipped; `python -m pip check` found no broken requirements; `git diff --check` passed.
- C1 acceptance is complete. The next roadmap unit is R3 transfer policy and managed staging, followed by R4 durable remote ownership and X4 unrestricted remote PowerShell.

Goal: remove restrictive and duplicated execution surfaces that no longer provide value once unrestricted PowerShell and direct executable profiles are proven.

The final capability and call-site inventory is recorded in `docs/permissive-migration-inventory.md`. C1 removed legacy execution-profile routing, redundant local command wrappers, obsolete built-in profiles, duplicate local-agent execution code, and migrated ordinary configured validation commands. Remote SSH transport, staging, reviewed-script, administration, transfer, and deployment surfaces are retained for R3/R4/X4 until durable remote replacement parity is proven.

Retain these core controls even in permissive-only mode:

- repository query, preview, apply, revert, move, and commit primitives;
- durable run state, leases, process identity, reconciliation, cancellation, locks, and events;
- configuration validation and reload;
- SSH transport, remote controller, transfer, and staging primitives;
- protected artifacts, return-loop publication, and audit metadata;
- workflows, supervisors, status, and recovery tooling;
- durable parallel command groups and independent child-run controls;
- unrestricted PowerShell as the single arbitrary-command gateway; optional specialist executable profiles only where independently justified.

Durable run history and protected evidence are retained even when their originating tool is removed. The explicit C1 policy excludes `runs/`, databases, protected artifacts, results, events, reports, and delivered manifests from managed cleanup; only registered scratch roots may be previewed and hash-verified for deletion.

Acceptance:

- a before/after capability matrix proves every removed tool is replaced or intentionally abandoned;
- active configuration contains only `permissive` execution routing;
- removed route names have no runtime call sites, schemas, tests, docs, or stale config fields;
- configuration migration is deterministic and rollback-capable;
- managed temporary artifacts from removed tools can be previewed and cleaned without deleting durable evidence;
- full tests, `python -m pip check`, `git diff --check`, and live unrestricted-PowerShell/parallel-fan-out smoke tests pass after cleanup, including PowerShell launching SSH, Git, OpenSSL, and other representative executables.

## R3 - Transfer Policy and Managed Staging

Status: **complete**.

Checkpoint (2026-07-17):

- Newly accepted durable SSH transfers now persist a versioned `transfer_manifest` before worker launch.
- File uploads record the exact source byte length and SHA-256; the worker revalidates both and rejects source drift before invoking SCP.
- Downloads record a deterministic run-relative staging destination under `downloads/<name>`; the worker verifies that persisted destination before transfer execution.
- Existing durable transfer runs created before the manifest contract remain executable, while any present malformed manifest fails before the transfer executor is called.
- Windows text-file fixtures now derive size and digest from actual bytes, preserving CRLF correctness.
- Implementation commits: `df22eebdc679c79e0e66425e7cf599b1fecc7afa`, `18b31e47fca665fc5ad0a92bdb79e48a1f743c53`, and `4453c49158bcd523101233c6676d8866fb387492`.
- Focused validation passed: `tests/test_job_manager.py` 59 passed; `tests/test_ssh_worker.py` 37 passed; `soma/job_manager.py` and `soma/job_worker.py` passed `py_compile`; `git diff --check` passed.
- Downloads now use a deterministic hidden partial path, remove stale partial state before retry, verify the completed artifact byte length and SHA-256, and publish to the final run-relative destination with `os.replace` only after successful SCP completion.
- Failed downloads remove partial staging content and never publish an ambiguous final artifact. Binary payload coverage includes NUL and non-UTF-8 bytes.
- Download-publication implementation commits: `84815e824718a457f69defee9d7d7f70ecfe2b13`, `833140fba1b99eabab87e57fd25dd11233ddb497`, `9b56dce83d3c6f518c7738ef4a401c9f91cb5bb6`, and `9ca4adbe0f7baa52c30934e65ffa49fc6689f353`.
- Focused validation passed: `tests/test_ssh_tools.py` 14 passed; `tests/test_ssh_worker.py` 37 passed; `soma/ssh_tools.py` and `soma/job_worker.py` passed `py_compile`; `git diff --check` passed.
- Recursive directory uploads now persist deterministic manifests with stable POSIX relative-path ordering, per-file byte lengths and SHA-256 hashes, aggregate file count, and aggregate byte count. Empty directories produce an explicit zero-file manifest; symbolic links and non-regular entries are rejected before durable launch.
- The worker rebuilds the complete recursive manifest immediately before SCP and rejects any added, removed, renamed, resized, or content-changed file before transfer execution. Historical pre-manifest transfers remain compatible.
- Recursive-manifest implementation commits: `13d8ba82ff473cebc3199805707850018e53ed9f`, `2c92bcf3555ab83248fccb70f39971e0cdd6c891`, and `69fbb3d91aa59822901505877f953c15d5b35efd`.
- Focused validation passed: `tests/test_transfer_manifests.py`, `tests/test_job_manager.py`, and `tests/test_ssh_worker.py` completed with **99 passed**; `transfer_manifests.py`, `job_manager.py`, and `job_worker.py` passed `py_compile`; `git diff --check` passed.
- Download transfers now persist a versioned cleanup manifest before SCP launch. The manifest explicitly separates the deterministic hidden partial artifact from the published download, marks the published artifact as protected evidence, and permits cleanup only for declared run-relative staging entries.
- Retry cleanup is idempotent, rejects path traversal, symbolic links, non-regular artifacts, and any attempt to delete a protected publication. Stale partials are removed before retry; failed-transfer partials are removed after execution; completed downloads remain preserved under `downloads/<name>`.
- Cleanup-manifest implementation commits: `034d2a315eb2a3fc2ed63f641fd0f36b543efb2b` and the following roadmap checkpoint commit.
- Focused validation passed: `tests/test_transfer_manifests.py`, `tests/test_ssh_tools.py`, and `tests/test_ssh_worker.py` completed with **56 passed**; `transfer_manifests.py`, `ssh_tools.py`, and `job_worker.py` passed `py_compile`; `git diff --check` passed.
- Executable-profile runs now receive a versioned staging manifest before durable launch. Binary or UTF-8 text stdin is materialized under `inputs/stdin.bin`, with exact byte length and SHA-256, while stdout/stderr declarations classify each output as protected evidence or ordinary staged output according to the persisted profile policy.
- The staging manifest binds every entry to the invoking run ID and lease generation. Workers reject run/lease drift, unsafe run-relative paths, missing or changed input bytes, malformed output declarations, and invalid protected-artifact classifications before child launch. Historical pre-manifest executable runs remain compatible.
- Completed output metadata records exact byte length, SHA-256, classification, invoking run ID, and lease generation for each declared stream.
- Executable-staging implementation commits: `066a13c5ab700ec8ce2a3b23fbaa17017cdc39e5`, `12c31e624df3355f0f43e9420e0a28ee61f2a5bb`, `36abfd3203bbc751733b6d6f4abec11662203cb5`, and `d27ee08acb1d7780df5ceca1ce3b29800fb3e774`.
- Focused validation passed: `tests/test_executable_staging.py`, `tests/test_executable_profiles.py`, `tests/test_executable_profile_worker.py`, and `tests/test_job_manager.py` completed with **71 passed**; `executable_staging.py`, `executable_profiles.py`, `job_manager.py`, and `job_worker.py` passed `py_compile`; `git diff --check` passed.
- Reviewed-script and monitored remote-controller runs now receive versioned staging manifests before durable worker launch. Reviewed scripts are materialized as protected UTF-8 input under `inputs/reviewed-script.bin` with exact size and SHA-256; both tool classes declare protected stdout/stderr evidence bound to the invoking run ID and lease generation.
- Workers revalidate tool identity, run identity, lease generation, exact run-relative output paths, protected classifications, and reviewed-script bytes before remote execution. Completed outputs publish exact size/SHA-256 metadata, while historical pre-manifest runs remain compatible.
- SSH staging implementation commits: `7bf668967285251bed64709fe8b11602e57ee959`, `b535bf9c4b89c9a85dafe46a44c571da955817be`, `9d5d8fee92745212c97597e72f3ed86d5c69dd24`, and `4ae85be66221d48bc1b4b6376c82d7a9679df856`.
- Focused validation passed: `tests/test_job_manager.py` and `tests/test_ssh_worker.py` completed with **96 passed**; `ssh_staging.py`, `job_manager.py`, and `job_worker.py` passed `py_compile`; `git diff --check` passed.
- Explicit overwrite/retry acceptance now proves an existing published download is preserved and SCP is not invoked without `overwrite=true`; confirmed overwrite removes stale hidden partial staging before retry and atomically replaces the prior publication only after successful binary-safe transfer.
- Reviewed-script and monitored remote-controller staging manifests are revalidated repeatedly without mutation, preserving the exact staged script bytes, run/lease binding, output paths, and protected-evidence classifications.
- R3 closure commits: `214e545ecb4bef48aeb5c968084ce475d26ca356` and `e4e0276c4d39a04413c10feb6ee034729211a54a`.
- Focused closure validation passed: `tests/test_ssh_staging.py`, `tests/test_ssh_tools.py`, and `tests/test_transfer_manifests.py` completed with **23 passed**.
- Adjacent R3 validation passed: `tests/test_job_manager.py`, `tests/test_ssh_worker.py`, `tests/test_ssh_staging.py`, `tests/test_ssh_tools.py`, and `tests/test_transfer_manifests.py` completed with **119 passed**; changed transfer/staging/manager/worker modules passed `py_compile`; `git diff --check` passed.
- The full R3 exit gate passed with **1116 passed, 1 skipped**; `python -m pip check` reported no broken requirements; `git diff --check` passed.
- R3 acceptance is complete. The next roadmap unit is R4: define and persist the authoritative remote-controller state contract, beginning with request/execution identity, idempotency, controller fingerprint/version, remote state paths, process identity, heartbeat, and cancellation/publication fields before remote launch.

Goal: provide predictable transfer scope for reviewed scripts, executable profiles, and remote controllers.

Active policy:

- `unrestricted`: arbitrary paths available to the service account or registered remote user under the enabled permissive profile.

`repo_only` and `configured_roots` remain frozen SSH transfer/staging compatibility policies during R3. C1 retained them because current remote transport and staging still require their boundaries; do not add new behavior beyond the R3 migration and acceptance work.

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

Status: **complete**.

Checkpoint (2026-07-17):

- Added a deterministic versioned remote-controller state contract before durable monitored-command launch.
- The persisted contract binds request ID, execution ID, idempotency key, host, command, lease generation, controller version/fingerprint, remote state/input/stdout/stderr/result paths, process identity placeholders, authoritative state/heartbeat, cancellation evidence, publication/cleanup state, executable identity, timeout, and resource-monitor state.
- Local bridge state records the remote job ID and state directory plus remote PID/PGID/start identity placeholders, last authoritative heartbeat, publication/cleanup state, and explicit reconciliation/uncertainty state.
- Workers rebuild and compare the complete accepted contract before any remote-controller execution, rejecting run, lease, command, argv, timeout, path, fingerprint, or state drift.
- The remote controller now creates its state directory and atomically publishes `input.json`, `state.json`, and terminal `result.json` with file and directory fsync before replacing visible state.
- Launch ownership is reported only after PID, PGID, process-start identity, execution ID, state path, running state, heartbeat, and durable-ownership evidence have been persisted remotely; incomplete or unsafe identity aborts launch.
- Running controllers refresh the authoritative heartbeat atomically and terminal publication updates both result and state before emitting the verified exit marker.
- Focused validation passed with `tests/test_ssh_watchdog.py`, `tests/test_remote_controller_state.py`, and `tests/test_ssh_worker.py`: **46 passed**; adjacent validation with those suites plus `tests/test_job_manager.py`: **105 passed**; changed modules passed `py_compile`; `git diff --check` passed.
- Added deterministic local reconciliation classification for matching live state, terminal state, invalid authoritative state, identity mismatch, and network/state uncertainty.
- Added a bounded remote-state probe that reads authoritative `state.json` and optional `result.json` without launching a second controller; probe timeouts and transport failures remain explicitly uncertain rather than terminal.
- Reconciliation/probe validation passed with `tests/test_remote_controller_state.py`, `tests/test_ssh_watchdog.py`, and `tests/test_ssh_worker.py`: **52 passed**; changed modules passed `py_compile`; `git diff --check` passed.
- Startup recovery now probes the authoritative remote state before changing bridge lifecycle state. Matching live controllers are recorded as adopted without duplicate launch, network/state uncertainty remains non-terminal, and terminal remote evidence is conditionally transitioned and canonically published exactly once.
- Startup reconciliation validation passed with `tests/test_job_manager.py`, `tests/test_remote_controller_state.py`, and `tests/test_ssh_watchdog.py`: **74 passed**; changed `job_manager.py` passed `py_compile`; `git diff --check` passed.
- Adopted live controllers now receive one deduplicated in-process reconciliation poller per run. The poller reloads durable state before every probe, retains the accepted contract and lease identity, continues remote heartbeat/result reconciliation during the same service lifetime, stops at terminal state or invalid contract/tool state, and allows the existing conditional terminal/publication path to remain the exactly-once authority.
- Re-entry polling validation passed with the focused regression at **1 passed, 59 deselected** and adjacent `tests/test_job_manager.py`, `tests/test_remote_controller_state.py`, and `tests/test_ssh_watchdog.py` at **75 passed**; changed modules and tests passed `py_compile`; `git diff --check` passed.
- Authoritative remote cancellation now atomically persists `cancellation_requested_at` and `cancellation_pending` before signalling, re-verifies the persisted PID/PGID/process-start identity, terminates that exact process group with TERM/KILL escalation, then atomically publishes terminal cancellation evidence and `cancellation_completed_at` before the local lifecycle may transition to `cancelled`.
- Manager cancellation retains the repository lock and local `cancellation_pending` state unless both exact remote termination and durable remote cancellation completion are confirmed, preserving the existing conditional terminal/publication path against concurrent completion races.
- Cancellation regression coverage proves remote request/completion state publication, exact process-group signals, manager contract forwarding, and remote-completion-before-local-terminal ordering. Adjacent `tests/test_ssh_watchdog.py`, `tests/test_remote_controller_state.py`, `tests/test_job_manager.py`, and `tests/test_ssh_worker.py` passed with **114 passed**; changed implementation and tests passed `py_compile`; `git diff --check` passed.
- Terminal publication now converges when cancellation loses either its initial claim or final terminal transition: the winning terminal state is canonically published through the idempotent publication path and the matching repository lock is released only after publication succeeds.
- Regression coverage proves concurrent natural completion wins over cancellation without being overwritten, publishes exactly once, and releases the lock; restart reconciliation of remotely completed cancellation also transitions locally, preserves remote terminal evidence, publishes exactly once, and remains idempotent under duplicate reconciliation.
- Focused `tests/test_job_manager.py` validation passed with **63 passed**; adjacent `tests/test_ssh_watchdog.py`, `tests/test_remote_controller_state.py`, `tests/test_job_manager.py`, and `tests/test_ssh_worker.py` passed with **116 passed**; changed modules and tests passed `py_compile`; `python -m pip check` and `git diff --check` passed.
- Implementation commits through `38a54b974abc515683718b62bd9ea0d59748e686`.
- Controlled live-host exit gate passed on 2026-07-18 against the isolated QuoteFollow Oracle acceptance fixture. The same durable execution survived local worker loss and service restart, ran for 3,931 seconds, retained execution ID `5ae97707e6257059c325eb6e4b5ee379`, PID/PGID `1567113`, process-start identity `398057789`, and a fresh authoritative heartbeat, while duplicate reconcilers adopted rather than relaunched it.
- Identity-scoped cancellation verified the persisted remote identity, durably recorded the cancellation request, terminated the exact process group with TERM, removed parent PID `1567113`, child PID `1567114`, and grandchild PID `1567115`, and atomically published remote `cancelled` state/result evidence with return code `-15`.
- The local run `20260717T222632Z_ssh_monitored_command_fae9475e` converged to one canonical `cancelled` terminal result, published hash `fa0ac0e1e895b1ccf4b71c5988c87f3b7d42a2a65f02a8871757534fa2c48db2` exactly once, released the repository lock, and remained byte-for-byte publication-idempotent across two additional startup reconciliations.
- Final validation passed: focused R4 suites **116 passed**; full repository suite **1,131 passed, 1 skipped**; `python -m pip check` reported no broken requirements; `git diff --check` passed. Durable evidence is recorded in `docs/r4-live-host-acceptance.md`.
- Windows-origin reviewed Bash/`sh` and permissive root-shell scripts now verify the submitted content hash, canonicalize CRLF or lone CR to LF before durable persistence, stage and execute the canonical bytes under a new exact hash, and retain the submitted hash plus an explicit normalization flag as audit metadata. Direct SSH argv execution and PowerShell payloads remain unchanged and byte-preserving.
- R4 is complete. Its durable remote controller and managed staging foundation are available to monitored Linux-native SSH work and the optional X4 remote PowerShell capability.

Goal: remote work survives Soma restart and local worker loss.

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
- Soma restarts during execution and reattaches;
- duplicate reconcilers cannot start duplicate remote controllers;
- cancellation kills the verified process group and descendants;
- terminal evidence is published once.

## X4 - Unrestricted Remote PowerShell

Depends on X2, R3, and R4.

Status: **complete (optional capability)**.

Checkpoint (2026-07-18):

- Added the provider-neutral, versioned remote PowerShell request envelope with absolute remote `pwsh`/`powershell` executable identity, exact argv, arbitrary working directory and environment values, binary-safe stdin, optional no-timeout operation, and deterministic request fingerprinting.
- The envelope does not filter or reinterpret PowerShell command text, child executable names, arguments, paths, or environment values.
- Focused `tests/test_remote_powershell.py` validation passed with **10 passed** through the durable-input unit.
- Added strict persisted-envelope revalidation and a deterministic R4 controller binding that preserves the exact executable argv, request fingerprint, run identity, lease generation, and timeout policy without introducing a second ownership model.
- `JobManager.start_remote_powershell` now validates the registered host and persists the exact request envelope, R4 binding, and authoritative controller state before worker launch and repository-lock acquisition.
- The shared R4 controller contract now preserves an explicit no-timeout policy as `null` instead of coercing it to an integer; focused controller-state validation passed with **8 passed** and manager validation passed with **64 passed**.
- Implementation commits through `49e130dc4907e95e9d95063c4a8c2441b26b14c2`.
- The durable worker now revalidates the complete X4 payload and dispatches `remote_powershell` through the existing R4 monitored-controller lifecycle without a second ownership model.
- Remote controller launch preserves exact executable argv, arbitrary working directory and environment values, binary stdin bytes, and explicit no-timeout semantics; controller input evidence records the delivered working directory, environment, and stdin byte count before child launch.
- Startup adoption, in-process reconciliation polling, terminal publication, and exact remote cancellation now include `remote_powershell` alongside monitored SSH commands.
- Focused validation passed: `tests/test_remote_powershell.py` **11 passed**; `tests/test_ssh_watchdog.py` **9 passed**; `tests/test_job_manager.py` **64 passed**; changed worker and watchdog modules passed `py_compile`.
- Worker-dispatch implementation commits: `4053d66ce835e483719c0a47bde9681d2d010b93`, `003bc9a92fa840e8f583cc2e9a1860a1deb4dc4b`, `cbd5d6b35f13607d77c6248c8ca4ef3b64416ce1`, and `66bdb51037695e13096458152cb739a31f3cdfb8`.
- The public `run_start` gateway now exposes `operation: remote_powershell` with registered host identity, absolute remote PowerShell executable path, exact argv, arbitrary working directory and environment values, strict base64 binary stdin, and optional no-timeout execution. The server decodes binary input before forwarding the exact request to the existing durable X4 manager path.
- Public-gateway implementation commit: `65d2293b5cef0a85d6f4f6ea34fdfec68892f70c`. Focused validation passed: `tests/test_tool_gateway_models.py` **31 passed**; `tests/test_server.py` **25 passed**; changed gateway and server modules passed `py_compile`; `git diff --check` passed.
- Every newly accepted X4 durable input now includes a versioned protected artifact manifest bound to the invoking run, lease generation, R4 execution ID, authoritative remote stdout/stderr paths, deterministic run-relative local binary publication paths, binary transfer encoding, and pending publication state.
- Worker-side durable-input reconstruction rejects any remote path, local path, classification, encoding, execution identity, run identity, or lease-generation drift before remote launch.
- Artifact-manifest implementation commit: `079f348535cc5b698a48dae3349b682a4f08a03d`. Focused validation passed: `tests/test_remote_powershell.py` **13 passed**; adjacent `tests/test_job_manager.py` **64 passed**; `soma/remote_powershell.py` passed `py_compile`.
- The worker now retrieves authoritative remote stdout and stderr with the existing binary SCP transfer path, atomically publishes them at the declared protected artifact locations, independently verifies byte length and SHA-256 after publication, and records a completed manifest without routing arbitrary output bytes through the SSH text stream.
- Binary-publication implementation commit: `c4190ce5946e79f110311540a9605bbcbaf3f5aa`. Focused validation passed: `tests/test_remote_powershell.py` **14 passed**; adjacent `tests/test_job_manager.py` **64 passed**; changed worker and contract modules passed `py_compile`; `git diff --check` passed.
- The remote controller now captures the requested and resolved PowerShell executable paths, exact byte length, SHA-256, and PowerShell version before launching the accepted command. The evidence is persisted in authoritative remote input/state/result files, re-probed after terminal completion, and bound to the accepted request fingerprint and R4 execution identity in the protected terminal result.
- Identity/version implementation commit: `2c4ebf745375064d88d7555a0f11a46024b31b3b`. Focused validation passed: `tests/test_remote_powershell.py` **16 passed**; adjacent `tests/test_ssh_watchdog.py` **9 passed**; `soma/remote_powershell.py` passed `py_compile`.
- Operator scope decision (2026-07-18): the deployed VPS fleet uses Linux-native SSH, Bash, Python, and direct executable tooling. Remote PowerShell remains available as an optional feature for registered hosts that already provide `pwsh` or `powershell`; installing or staging PowerShell on Linux hosts solely for acceptance is not required.
- The live remote-PowerShell native-command and loopback-network gate is removed as a roadmap blocker. Existing focused automated contract, gateway, worker, staging, artifact, identity, reconciliation, and cancellation coverage remains authoritative for the optional feature.
- X4 is complete under this scope decision. The next executable roadmap unit is R5 absolute resource enforcement.

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

- the public remote PowerShell request and result contract remains deterministic and binary-safe;
- remote PowerShell reuses the accepted R4 restart-adoption, reconciliation, exact cancellation, and exactly-once publication protocol;
- focused automated tests verify request preservation, gateway dispatch, durable input, protected artifact publication, and executable identity evidence;
- no PowerShell command text, child executable, or child argument is silently removed, rewritten, or filtered;
- live remote PowerShell smoke testing is optional and applies only when a registered host already provides `pwsh` or `powershell`; its absence does not block Linux VPS operation or roadmap progress.

## R5 - Absolute Resource Enforcement

Status: **in progress**.

Checkpoint (2026-07-18):

- Added a deterministic remote-memory policy contract with the roadmap defaults: conservative `40_000_000_000`, graceful `45_000_000_000`, and hard `48_000_000_000` bytes.
- Absolute cgroup memory samples are evaluated before optional host-percentage evidence; every result records the exact sample, configured thresholds, matched threshold, action, and precedence decision.
- Permissive policy metadata can explicitly raise or disable thresholds while preserving validation and visibility.
- Implementation commits: `4ad26247afd84ffeeb8f7a2af7121772d1a36150` and `8b6ce72e00fff829c54af8582779e385d6cb841d`.
- Focused validation passed: `tests/test_remote_resource_enforcement.py` **7 passed**; `soma/remote_resource_enforcement.py` passed `py_compile`.
- The accepted memory policy is now part of every new authoritative R4 controller contract before launch. Remote controller input and running state persist the exact policy, current cgroup memory sample, source path, deterministic decision, sample timestamp, and explicit absolute-cgroup-first evidence.
- Every authoritative remote heartbeat refreshes the resource-monitor evidence atomically with the heartbeat while leaving termination behavior disabled for this unit. Missing or inaccessible cgroup files are recorded as `unavailable` rather than inferred from host percentages or treated as terminal.
- Implementation commits: `753746db272f83552fb0b1cd05a6c603f71f671c`, `fc5d665a4799a498ba05bdf4a7d4d3281491fe83`, and `817c3586a6fbdced3c34abbc7c0938c4a84da309`.
- Focused validation passed: `tests/test_remote_resource_enforcement.py` **7 passed**; `tests/test_remote_controller_state.py` **8 passed**; `tests/test_ssh_watchdog.py` **9 passed**; changed controller-state and watchdog modules passed `py_compile`; `git diff --check` passed.
- The authoritative remote controller now enforces `graceful_terminate` and `hard_terminate` decisions against the verified remote process group. Graceful enforcement sends `SIGTERM`, waits for bounded exit, then revalidates identity before `SIGKILL`; hard enforcement proceeds directly to identity-verified `SIGKILL`.
- The triggering cgroup sample, source path, exact threshold decision, process-identity verification, signals sent, timestamps, confirmation state, error, and terminal resource-enforcement outcome are persisted in controller state and terminal result evidence.
- Internal encoded controllers now have a separate bounded `16_384`-byte transport ceiling while ordinary configured SSH command profiles retain the existing `4_096`-byte limit.
- Implementation commits: `e5cc6fd4ad8adaad8feebd4eb781d48cabdcf9bd`, `de4ff4e9b3765ae6f98566e4cb6fcccead36e1a5`, `5fbd4c5f4a052fc24503d4e37f77894057e8f7cb`, and `7e86a09b03251f4bc1d582e15e04d35790f5dbe5`.
- Focused validation passed: `tests/test_ssh_watchdog.py` **9 passed** and `tests/test_ssh_commands.py` **29 passed**; `soma/ssh_watchdog.py` passed `py_compile`.
- Added POSIX execution-level coverage that runs the generated controller against disposable local process groups for graceful exit, forced escalation, direct hard termination, identity-mismatch refusal, and exact persisted state/result evidence.
- Implementation commit: `f460329a15d662cca76e99f4aac195d66bc2d06f`.
- Windows validation collected the suite successfully with **4 skipped** because the service host has no POSIX process groups; adjacent validation passed with `tests/test_ssh_watchdog.py` **9 passed**, `tests/test_remote_resource_enforcement.py` **7 passed**, and the new execution test passed `py_compile`.
- A direct WSL validation attempt could not execute because no Linux distribution with `bash` is installed. The POSIX execution cases remain ready for Linux CI or a disposable Linux validation host rather than being simulated on Windows.
- Next executable unit: run the new execution suite on a disposable Linux environment, then add the remaining R5 resource signals (GPU temperature/memory, disk, heartbeat, and CUDA OOM) to the authoritative controller evidence without weakening the absolute-memory-first policy.

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
- environment values reach local PowerShell and supported Linux-native remote execution paths unchanged; remote PowerShell is included only when a registered host already provides it.

## R7 - Provider-Neutral Disposable-Host Acceptance Gate

Goal: prove the complete contract on a disposable host before paid or workload-specific use.

The generic suite must prove:

- native endpoint access and capability discovery;
- permissive-only active routing and clean rejection of removed profiles;
- unrestricted transfers;
- unrestricted local PowerShell profiles and Linux-native remote SSH execution;
- arbitrary local PowerShell command text, modules, paths, environment, child processes, and network operations;
- fire-and-return parallel groups for the supported local and remote execution substrates;
- restart adoption, individual cancellation, group cancellation, mixed outcomes, and aggregate reporting for parallel groups;
- unrestricted permissive root shell;
- unrestricted local PowerShell and Linux-native remote execution running representative native commands such as SSH, Git, OpenSSL, Docker, and Python without per-program gateways;
- optional remote PowerShell smoke coverage only when a registered target already provides `pwsh` or `powershell`; absence of PowerShell on Linux hosts is not a gate failure;
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

### Codex re-enable path (closed)

This path is closed: the Codex execution stack was removed on 2026-07-23 and replaced with provider-neutral external-coder handoff generation. Any future coding-agent integration would be a new design, not a re-enablement.

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
- `max_concurrent_powershell` controls the number of simultaneously open unrestricted PowerShell processes, and a `null` value removes the Soma product-level cap;
- each child retains independent process identity, leases, output, artifacts, status, cancellation, and restart adoption;
- group restart reconciliation does not duplicate surviving children;
- group and individual cancellation target exact verified process trees;
- lock-free same-repository execution is available when explicitly selected and its race risk is recorded;
- aggregate status and final results preserve mixed child outcomes without obscuring individual evidence.

### Permissive-only cleanup gate — passed

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
- unrestricted PowerShell is explicit, operator-enabled, auditable, and permits any command available to the service account without Soma command allowlists;
- UI and local-model expansion do not outrun execution correctness.
