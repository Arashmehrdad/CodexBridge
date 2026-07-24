# Soma

Soma is a Windows-first, client-neutral MCP engineering control plane. It connects an MCP-capable controller to local Git repositories, durable PowerShell execution, remote hosts, infrastructure providers, repository knowledge, Hermes tools, and the optional Trading Lab domain package.

Soma is not a coding-agent runtime and does not launch Codex, Claude Code, Gemini CLI, or another model-agent process. The connected client remains the reasoning controller; Soma supplies durable identity, execution, cancellation, evidence, repository operations, and bounded domain gateways.

## Current state

The current public surface contains **30 consolidated MCP gateways**. The major completed milestones are:

- durable run ownership, restart reconciliation, process-tree cancellation, locks, and atomic terminal publication;
- unrestricted owner-authorized local PowerShell, including parallel command groups;
- compact `cf1.v1` public projections with exact authoritative evidence retrieval;
- hash-bound managed repository previews, applies, rollback evidence, and selected-file commits;
- shared multi-session Hermes service with a one-request companion fallback;
- durable workflows and supervisors;
- repository wiki and scoped decision memory;
- bounded Docker, Cloudflare, and SSH providers;
- Trading Lab extracted into its own package and wired back through one adapter;
- strict Trading Lab companion steps for research, decision, model review, and demo-only execution;
- hidden Windows logon startup for both the Soma server and Cloudflare tunnel.

No roadmap lane is implicitly active. New implementation work starts only when the owner selects a bounded batch.

## Design principles

1. **Durable before powerful.** Accepted asynchronous work is persisted before launch and remains recoverable across server restarts.
2. **One controller, no hidden second agent.** Hermes is a searchable tool runtime, not a delegated model loop.
3. **Inspect before mutation.** Repository reads, previews, applies, validation, and commits are separate operations.
4. **Preserve once, disclose progressively.** Compact responses are the default; complete authoritative inputs, outputs, results, and artifacts stay retrievable by explicit evidence operations.
5. **Owner-controlled execution.** The local PowerShell path is intentionally unrestricted in permissive mode. Correctness comes from exact identity, leases, idempotency, cancellation, evidence, and reconciliation—not pretend permission prompts.
6. **Private network boundary.** The unrestricted MCP server binds to loopback by default and must be reached remotely only through an owner-controlled authenticated tunnel or equivalent private transport.
7. **Provider boundaries stay narrow.** Docker, Cloudflare, SSH, Hermes, and Trading Lab expose typed gateways rather than arbitrary provider APIs.

## Architecture

```text
MCP-capable controller
  |
  v
Soma FastMCP server  http://127.0.0.1:8000/mcp
  |
  +-- system identity, health, config reload and rollback
  +-- repository inspection and hash-bound managed changes
  +-- durable local and remote execution
  +-- run, workflow and supervisor state
  +-- repository wiki and scoped decision memory
  +-- Hermes one-request companion / shared worker service
  +-- Docker, Cloudflare and SSH domain gateways
  +-- Trading Lab adapter
  |
  +-- runs/soma.sqlite3              authoritative SQLite/WAL state
  +-- runs/<run_id>/                 protected inputs, output and evidence
  +-- runs/workflows/                workflow artifacts
  +-- runs/supervisors/              supervisor artifacts and resume prompts
  +-- runs/trading/                  Trading Lab journals and state
  +-- <repo>/.soma/wiki/             generated repository knowledge
```

The service is Windows-first, but most of the Python core is platform-neutral. Windows-specific process identity, PowerShell, Scheduled Tasks, MT5, and service-control behavior are tested explicitly where they matter.

## Requirements

Core:

- Windows 10 or 11;
- Python **3.10+**; Python 3.12 is the primary local environment;
- Git;
- Windows PowerShell 5.1 for service scripts.

Common optional components:

- PowerShell 7 (`pwsh.exe`) for the unrestricted executable profile;
- `cloudflared` plus an authenticated tunnel configuration;
- Windows OpenSSH client for SSH operations;
- Docker Desktop for Docker/Compose operations;
- a pinned Hermes checkout and environment for Hermes integration;
- a sibling `TradingLab` checkout and MetaTrader 5 demo terminal for Trading Lab.

## Installation

```powershell
cd D:\Github\Soma
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item config.example.yaml config.yaml
```

`config.yaml`, `.env`, run state, virtual environments, caches, and generated wiki files are Git-ignored.

Validate the configuration before starting the service:

```powershell
.\soma-service.cmd validate-config
```

### Minimal configuration

Start with `config.example.yaml`. At minimum, configure one Git repository and the run directory:

```yaml
repos:
  soma:
    path: "D:/Github/Soma"
    commit_mode: "explicit_only"
    allow_push: false
    refuse_unrelated_staged_files: true
    require_commit_report: true

runs_dir: "runs"

supervisors:
  default_autonomy_profile: "permissive"
  autonomy_profiles:
    permissive:
      stop_on_requires_human: true
      max_plan_tier: 3
      max_implementation_tier: 3
      require_tests_for_non_docs_changes: false
```

For unrestricted local PowerShell, configure an enabled executable profile with the exact local `pwsh.exe` path:

```yaml
executable_profiles:
  powershell:
    profile_id: "powershell"
    enabled: true
    executable_path: "C:/Program Files/PowerShell/7/pwsh.exe"
    target: "local"
    working_directory_policy: "arbitrary"
    environment_policy: "arbitrary"
    stdin_mode: "bytes"
    stdout_mode: "protected_artifact"
    stderr_mode: "protected_artifact"
    timeout_seconds: 600
    allow_no_timeout: true
    cancellation_policy: "process_tree"
    public_output_max_bytes: 100000
    preserve_protected_artifacts: true
    autonomy_profile: "permissive"
    unrestricted_argv: true
    unrestricted_paths: true
    unrestricted_environment: true
    unrestricted_network: true
    unrestricted_child_processes: true
```

Executable profiles preserve executable identity and I/O behavior. They are not intended to become a second user-permission system.

### Repository discovery

Explicit `repos:` entries always win. Unknown repository names can also be discovered from direct sibling Git repositories under approved roots inferred from configured repository parents.

Optional environment controls:

```text
SOMA_AUTO_DISCOVER_REPOS=0
SOMA_REPO_ROOTS=D:/Github;E:/Projects
SOMA_REPO_EXCLUDES=.fallow,secrets,archive
SOMA_REPO_MAX_DEPTH=1
```

See [`docs/automatic-repo-discovery.md`](docs/automatic-repo-discovery.md) for the exact normalization and exclusion rules.

## Starting and managing Soma

### Direct server start

```powershell
.\.venv\Scripts\python.exe -m soma.server `
  --config config.yaml `
  --transport http `
  --host 127.0.0.1 `
  --port 8000 `
  --path /mcp
```

The default local endpoint is:

```text
http://127.0.0.1:8000/mcp
```

A plain `GET` returning HTTP `406 Not Acceptable` means the MCP route is mounted. It is a readiness probe, not a complete MCP handshake.

### Service controller

Open the interactive controller:

```powershell
.\soma-service.cmd
```

Common direct actions:

```powershell
# Server only; the tunnel is not interrupted.
.\soma-service.cmd start
.\soma-service.cmd stop
.\soma-service.cmd restart
.\soma-service.cmd status

# Tunnel only.
.\soma-service.cmd tunnel-start
.\soma-service.cmd tunnel-stop
.\soma-service.cmd tunnel-restart
.\soma-service.cmd tunnel-status

# Combined lifecycle.
.\soma-service.cmd start-all
.\soma-service.cmd stop-all

# Diagnostics and logs.
.\soma-service.cmd validate-config
.\soma-service.cmd diagnostics
.\soma-service.cmd logs
.\soma-service.cmd follow-logs
.\soma-service.cmd open-logs
```

The controller:

- launches the server and tunnel hidden;
- verifies process command lines before adopting or stopping them;
- refuses to kill an unrelated process that owns the configured port;
- avoids duplicate server or tunnel instances;
- records PID files and service logs under `runs\service_logs`;
- uses UAC only when a verified process requires elevation to stop.

Server `restart` intentionally leaves the Cloudflare tunnel untouched. This keeps the public tunnel stable during ordinary source or package rollouts.

### Hidden startup at Windows sign-in

Soma can register a hidden Scheduled Task for the current Windows user. It starts both the server and tunnel **after sign-in**; it is not a machine service that runs before a user logs on.

```powershell
# Install or replace the hidden task.
.\scripts\manage_soma_startup.ps1 install

# Inspect task state and its last result.
.\scripts\manage_soma_startup.ps1 status

# Run the same startup action immediately.
.\scripts\manage_soma_startup.ps1 run

# Remove the task.
.\scripts\manage_soma_startup.ps1 uninstall
```

Defaults:

- task name: `Soma MCP Startup`;
- logon delay: 20 seconds, allowing networking to settle;
- task window: hidden;
- multiple instances: ignored;
- battery operation: allowed;
- startup log: `runs\service_logs\soma-startup-task.log`.

The startup action is idempotent. If the verified server and tunnel already exist, it records their healthy state and exits without restarting them.

### Cloudflare tunnel

The service controller expects the configured tunnel file at:

```text
%USERPROFILE%\.cloudflared\soma-mcp.yml
```

Keep `/mcp` at the end of the public connector URL. Never expose the unrestricted local server directly to the public internet.

### Reload versus restart

`system_action` with `action: "reload"` reloads supported configuration modules. It does **not** replace the Python process or load newly installed package code.

Use a controlled server restart after:

- Python source changes;
- package installation or upgrade;
- MCP tool registration or schema changes;
- changes that the reload result marks as requiring restart.

After a tool-surface change, refresh or reconnect the MCP client so its cached schemas match the live capability epoch.

## Public MCP surface

The public API is deliberately consolidated into 30 gateways. Use `system_query` with `operation: "capabilities"` as the source of truth for live schemas.

| Area | Public gateways |
| --- | --- |
| System | `system_query`, `system_action` |
| Durable runs | `run_start`, `run_query`, `cancel_run` |
| Repositories | `repo_query`, `repo_preview`, `repo_apply`, `repo_commit` |
| Workflows | `workflow_query`, `workflow_action` |
| Supervisors | `supervisor_query`, `supervisor_action` |
| Knowledge | `knowledge_query`, `knowledge_action` |
| SSH | `ssh_query`, `ssh_inspect`, `ssh_action` |
| Docker | `docker_query`, `docker_action` |
| Cloudflare | `cloudflare_query`, `cloudflare_action` |
| Trading Lab | `trading_query`, `trading_signal_submit`, `trading_signal_get`, `trading_signal_list`, `trading_signal_cancel_before_entry`, `trading_companion_action`, `trading_action_submit`, `trading_runtime_control` |

Public gateway projections normally include live identity fields such as `server_build_hash`, `schema_hash`, and `capability_epoch`. Capability-identity checks provide the exact comparison path when a client must prove that its cached schemas match the running service.

### System gateway

`system_query` provides:

- `capabilities`;
- lightweight `self_check`;
- exact `capability_identity` comparison;
- local-model health;
- configuration validation;
- reload status.

`system_action` supports validated configuration `reload` and last-known-good `rollback`.

The lightweight self-check verifies imports, package identity, configuration, SQLite/WAL stores, supervisor state, service identity, and availability of the comprehensive validation script. It does not run pytest or start another server.

### Durable execution

`run_start` operations:

- `powershell` — unrestricted owner-authorized local PowerShell;
- `remote_powershell` — optional PowerShell on a configured remote Windows host;
- `powershell_group` — parallel durable local runs;
- `hermes_companion` — one-request Hermes process;
- `hermes_service` — shared persistent Hermes worker service.

`run_query` operations:

- lifecycle: `status`, `control`, `summary`, `summary_list`, `list`;
- evidence: `input`, `output`, `events`, `terminal`, `result`;
- groups: `group_status`, `group_result`;
- engineering state: `locks`, `preflight`.

A short PowerShell command may request `return_when: "terminal_or_timeout"` with `wait_seconds` from 0 to 20. The run is still persisted before launch. Wait expiry never cancels the run.

Once a start call returns a `run_id`, do not repeat it after a client timeout. Poll the existing run.

### Repository gateway

`repo_query` is read-only and supports:

- `status` and `compact_status`;
- managed `patch_status`;
- bounded `list_files`, `read_files`, and `search_text`;
- `recent_files`;
- frozen `diff` summaries, hunks, and full evidence;
- `log`;
- exact `commit_range` inspection.

All paths are repository-relative. Reads reject traversal, `.git`, virtual environments, real environment files, secret-like files, and symlink or junction escapes. Text results are bounded and obvious secret values are redacted.

Managed changes use three stages:

1. `repo_preview` creates an opaque, hash-bound preview for `patch`, `create_file`, `remove_file`, or managed cleanup.
2. `repo_apply` atomically applies a preview, cleanup, rollback, or verified move. Preview replays are idempotent and stale content fails closed.
3. `repo_commit` creates a protected branch or commits only explicitly selected existing changes.

A managed patch preview can bind its commit title and description. The apply operation verifies repository identity, `HEAD`, source hashes, payload hashes, paths, limits, newline behavior, and current worktree state before mutation. Rollback uses stored evidence and stale-state protection rather than `git reset` or `git checkout`.

The public gateway does not expose Git push. Push manually outside Soma when appropriate.

### Workflows and supervisors

`workflow_action` starts or cancels a durable dependency-ordered workflow. `workflow_query` reads status, events, and results.

`supervisor_action` starts, resumes, pauses, or cancels a durable supervisor. `supervisor_query` reads status, result, events, notifications, and the bounded resume prompt.

Both reuse the same durable run substrate. They must not introduce a second repository-lock or process-ownership system.

### Repository knowledge

`knowledge_action`:

- `refresh_wiki` — generate or incrementally refresh `.soma/wiki`;
- `remember_decision` — persist a repository-scoped accepted decision.

`knowledge_query`:

- `read_wiki` — read one generated page;
- `search` — search generated wiki content and repository-scoped memory.

The wiki is a generated cache, not the source of truth. Check its freshness fields and verify architecture-sensitive claims against live source before editing.

See [`docs/repository-knowledge.md`](docs/repository-knowledge.md).

## Compact projections and authoritative evidence

Soma stores complete authoritative state once and returns bounded public projections by default.

```text
Authoritative record
  complete request, lifecycle, output, result and evidence

Compact public projection (cf1.v1)
  small deterministic response for ordinary controller decisions

Explicit evidence retrieval
  exact input, output tail, artifact, event page, full result, file range or diff hunk
```

Compact output must preserve errors, safety failures, partial outcomes, ambiguous mutations, cancellation uncertainty, cleanup state, and reconciliation requirements. A compact success-shaped response must never conceal an authoritative failure.

Cursors bind their operation, filters, ordering, response view, snapshot or content identity, and expiry. Repository continuation binds to file or worktree hashes so content changes fail as stale rather than mixing versions.

## Durable state and recovery

The authoritative run database is:

```text
runs/soma.sqlite3
```

SQLite WAL mode is enabled. Per-run protected artifacts live under:

```text
runs/<run_id>/
```

Soma persists launch intent before process creation and records launcher, worker, and child identities. Restart reconciliation can:

- adopt a verifiably active worker;
- relaunch eligible queued work idempotently;
- retain an uncertain operation in an explicit recovery state;
- preserve locks while work may still be active.

Terminal state and structured result are published atomically. Cancellation targets the owned process tree. PID values are never trusted without additional process identity.

## Hermes integration

Soma integrates Hermes as a tool runtime only. It does not invoke a Hermes model-agent loop.

Two paths are available through `run_start`:

- `hermes_companion` launches one version-pinned process for one request;
- `hermes_service` uses a supervised persistent worker pool for concurrent sessions.

Supported service operations are `tool_search`, `tool_describe`, and `tool_call`. Requests bind to the expected registry generation and schema hash. Stale requests fail closed instead of running against silently changed tools.

The shared service preserves session ownership, exact request cancellation, worker replacement, restart adoption, bounded stderr, provider-specific concurrency limits, and one explicit fallback to the one-request companion when configured.

See [`docs/hermes-tool-runtime-feasibility.md`](docs/hermes-tool-runtime-feasibility.md) and the H2 completion record in [`PLANS.md`](PLANS.md).

## Trading Lab

Trading Lab is a separate Python package and repository. Soma owns the MCP transport, configuration, compact projections, and durable host boundary; `trading_lab` owns market data, packets, signals, outcomes, actions, safety, runtime state, replay, reports, and MT5 integration.

The only in-process seam is:

```text
soma/trading_lab_adapter.py
```

The dependency is one-way: Trading Lab does not import Soma.

### Installation

For active development:

```powershell
pwsh -File .\scripts\install_trading_lab_dev.ps1
```

For a reproducible clean wheel:

```powershell
pwsh -File .\scripts\install_trading_lab_pinned.ps1 `
  -ExpectedCommit <40-character-commit> `
  -ExpectedSha256 <wheel-sha256>
```

The pinned installer verifies the Trading Lab checkout, derives a deterministic `SOURCE_DATE_EPOCH`, builds a reproducible wheel, verifies its SHA-256, installs with `--no-deps`, and stamps package provenance. `system_query.self_check` reports the loaded package version, module path, source commit, and editable state.

### Configuration

Trading is disabled by default and structurally demo-only:

```yaml
trading:
  enabled: false
  provider: "mt5"
  account_environment: "demo"
  terminal_path: "C:/Path/To/MetaTrader 5/terminal64.exe"
  symbol: "BITCOIN_i"
  provider_utc_offset_seconds: 0
  maximum_tick_age_seconds: 120
```

There is no `live` execution mode in configuration, policy, gateway models, or the Trading Lab package.

### Capabilities

Read operations include health, symbols, specification, fresh tick, H1/H4 candles, historical ticks, market packets, signal outcomes, rejection records, data quality, calibration, deterministic replay, action journals, runtime state, demo performance, reconciliation, and companion journals.

Signals are immutable and packet-bound: the caller references a retained market packet instead of supplying market facts. The action gateway performs validation, strategy policy, fresh-price checks, symbol and volume normalization, risk and margin checks, `order_check`, idempotent submission, durable state transitions, and broker reconciliation. Raw `MetaTrader5.order_send()` is never public.

The companion cycle is:

```text
start research against a fresh packet
  -> decide LONG / SHORT / NO_TRADE
  -> second-pass model review APPROVED / REJECTED
  -> execute from the approved immutable signal
  -> reconcile internal-paper or broker-demo state
```

At execute time, callers supply only the companion cycle ID, idempotency key, and volume. Symbol, direction, execution mode, policy, experiment, stop-loss, and take-profit are derived from the approved signal.

Unattended trading scheduling is not enabled by default. Starting Soma at Windows sign-in does not start the Trading Lab runtime or place any order.

See:

- [`docs/trading-lab-separation.md`](docs/trading-lab-separation.md)
- [`docs/trading-lab-redesign-evidence.md`](docs/trading-lab-redesign-evidence.md)
- [`docs/trading-lab-tl9-live-readiness-review.md`](docs/trading-lab-tl9-live-readiness-review.md)

## Optional domain providers

### SSH

SSH is disabled by default. The public surface is split intentionally:

- `ssh_query` — capabilities and hash-bound profile-change lifecycle;
- `ssh_inspect` — host health, environment, GPU telemetry, and bounded inspection;
- `ssh_action` — profile apply, configured command, monitored command, reviewed script, permissive root shell, administration, transfer, and deployment.

Remote identity, process groups, cancellation, watchdog samples, transfer manifests, and deployment evidence are durable. Readable paths are limited to configured POSIX roots. Secret-like files and unsafe path escapes are blocked.

`root_shell` is a hash-pinned, high-risk permissive operation. It is not a substitute for ordinary structured commands.

### Docker

Docker is disabled by default. `docker_query` exposes capabilities, health, and bounded inspection. `docker_action` exposes fixed Compose, image, container, network, volume, exec, and cleanup actions.

Repository Compose files, build contexts, Dockerfiles, and exec command IDs are configured in `config.yaml`. Destructive cleanup, removal, push, and volume deletion remain behind the matching provider gate and confirmation value.

### Cloudflare

Cloudflare is disabled by default. Each repository must be bound explicitly to an authorized global profile.

`cloudflare_query` provides profile-scoped capabilities, health, and bounded inspection. `cloudflare_action` provides typed DNS, cache, SSL, DNSSEC, ruleset, Turnstile, tunnel, and route changes.

Tokens are loaded from operating-system environment variables or the configured ignored `.env` file at request time. They are never accepted as MCP arguments. Turnstile secrets are delivered directly to an ignored repository-relative destination and removed from public responses and durable logs.

## Recommended engineering workflow

A normal repository batch should follow this sequence:

1. `run_query.preflight` — confirm branch, `HEAD`, dirty state, active runs, and locks.
2. `repo_query` — read exact files, search source, inspect recent changes, status, history, and diffs.
3. `repo_preview` — build one hash-bound, reviewable change with meaningful commit metadata.
4. Inspect the exact preview diff.
5. `repo_apply` — apply the opaque preview once; poll its durable transaction if needed.
6. Validate proportionately through `run_start.powershell`.
7. Reinspect status and history with `repo_query`.
8. Use `repo_commit.commit_selected` only for explicitly selected existing changes that were not committed by the managed apply.

Do not reset, clean, stash, amend, rebase, or discard unrelated work. Preserve tool-owned evidence such as `.codex-tmp` unless the task explicitly owns it.

### Example durable PowerShell request

The exact MCP call is structured data; the profile receives PowerShell arguments:

```json
{
  "operation": "powershell",
  "repo_name": "soma",
  "profile_id": "powershell",
  "argv": [
    "-NoProfile",
    "-Command",
    "python -m pytest -q tests/test_run_store.py; exit $LASTEXITCODE"
  ],
  "working_directory": "D:\\Github\\Soma",
  "timeout_seconds": 600,
  "return_when": "accepted"
}
```

For independent work, use `powershell_group` instead of opening unrelated serial runs. Group cancellation and child cancellation target only the owned process trees.

## Security and operational boundaries

Soma is powerful by design. Its primary boundary is owner-controlled deployment, not a sandbox.

- Bind the MCP server to loopback.
- Use an authenticated owner-controlled tunnel for remote access.
- Never expose the unrestricted MCP endpoint directly to the public internet.
- Keep `config.yaml`, `.env`, SSH keys, tunnel credentials, MT5 credentials, and run artifacts out of Git.
- Do not paste secrets into MCP arguments, chat, logs, or configuration examples.
- Treat compact responses as non-authoritative summaries and use explicit evidence retrieval for exact investigation.
- Keep destructive provider actions typed, scoped, idempotent where possible, and reconciled after ambiguous transport failures.
- Preserve repository and resource locks until process exit or ownership transfer is verified.
- Do not use PowerShell to launch a coding-agent CLI or another model-agent process.
- Do not add live-money trading. The supported trading modes are `internal_paper` and `broker_demo` only.
- Do not rent paid compute solely for Soma roadmap validation.

The public repository gateway does not provide arbitrary filesystem reads. Unrestricted host access exists only through the explicitly configured PowerShell execution profile.

## MCP client notes

After a source, package, or schema rollout:

1. restart the Soma server through the verified controller;
2. leave the tunnel running unless it independently needs maintenance;
3. refresh or reconnect the MCP client;
4. compare the loaded schemas with `system_query.capability_identity` when exact convergence matters.

A connector can occasionally return HTTP 502 while the local service is restarting or because an upstream connector path failed. If no Soma response and no `run_id` exist, one identical retry may be reasonable. Once a `run_id` exists, never repeat the start request—poll it.

## Development and validation

Install development dependencies with:

```powershell
python -m pip install -e ".[dev]"
```

Typical focused checks:

```powershell
python -m pytest -q tests/<target>.py
python -m ruff check soma tests
python -m pip check
git diff --check
```

Run the complete repository audit only when the batch justifies it:

```powershell
.\scripts\comprehensive_self_check.ps1
```

That script covers:

- `python -m pip check`;
- the full pytest suite;
- `git diff --check`;
- package identity;
- isolated FastMCP startup on a free local port.

For documentation-only changes, inspect the scoped diff and run only:

```powershell
git diff --check
```

Never claim a validation command that did not run.

## Project layout

```text
soma/
  server.py                    FastMCP registration and dispatch
  gateway_models.py            strict discriminated public schemas
  config.py                    validated YAML configuration
  run_store.py                 authoritative durable run state
  job_manager.py / job_worker.py
                               local durable execution and recovery
  repo_reader.py / repo_writer.py
                               bounded reads and managed changes
  run_public_result.py         compact terminal projections
  run_artifacts.py             protected evidence handling
  workflows/                   durable dependency-ordered workflows
  supervisor/                  supervisor models and flow
  hermes_*.py                  companion and shared Hermes service
  ssh_*.py                     remote execution and policy
  docker_tools.py              bounded Docker integration
  cloudflare_tools.py          bounded Cloudflare integration
  trading_lab_adapter.py       sole Trading Lab package seam
  memory/                      scoped memory and search
  dashboard/                   local read-only dashboard components
  local_agent/                 bounded local operational components

scripts/
  manage_soma_service.ps1      verified hidden server/tunnel controller
  manage_soma_startup.ps1      hidden current-user logon task
  start_soma_mcp.ps1           direct startup helper
  comprehensive_self_check.ps1 complete validation gate
  install_trading_lab_dev.ps1  editable Trading Lab install
  install_trading_lab_pinned.ps1
                               reproducible Trading Lab wheel install
  browser_pulse_sender.py      optional local browser return helper

runs/                          ignored durable state and artifacts
docs/                          architecture, roadmap and evidence records
tests/                         unit, contract and Windows integration tests
```

## Documentation map

- [`PLANS.md`](PLANS.md) — current owner decisions and active roadmap state.
- [`AGENTS.md`](AGENTS.md) — controller and engineering rules.
- [`docs/roadmap-v2-achievements.md`](docs/roadmap-v2-achievements.md) — completed implementation history and evidence.
- [`docs/Soma_Agentic_Runtime_Audit_and_Strategic_Roadmap_Revised.md`](docs/Soma_Agentic_Runtime_Audit_and_Strategic_Roadmap_Revised.md) — revised audit and strategic direction.
- [`docs/domain-tool-gateway-migration.md`](docs/domain-tool-gateway-migration.md) — consolidated gateway design.
- [`docs/domain-tool-gateway-progress.md`](docs/domain-tool-gateway-progress.md) — migration record from legacy wrappers.
- [`docs/repository-knowledge.md`](docs/repository-knowledge.md) — wiki and memory behavior.
- [`docs/pilot-evidence.md`](docs/pilot-evidence.md) — real-project operational evidence.
- [`docs/trading-lab-separation.md`](docs/trading-lab-separation.md) — package extraction and equivalence evidence.
- [`docs/Soma_Third_Party_Licensing_and_Integration_Policy.md`](docs/Soma_Third_Party_Licensing_and_Integration_Policy.md) — third-party integration guidance.

## Known boundaries

- Soma does not launch or supervise coding-agent CLIs.
- Manual external-coder handoff artifacts are inert exports only.
- The Windows startup task runs after the configured user signs in, not before logon.
- Configuration reload is not a code or package restart.
- The public repository surface has no Git push operation.
- Optional providers remain disabled until explicitly configured.
- Trading is demo-only; unattended scheduling is not enabled by default.
- Generated wiki content is a cache and can be stale.
- Legacy durable records may remain readable, but retired operation names are not executable capabilities.

Soma’s operating rule is simple: **preserve the complete truth durably, expose only the useful slice now, and never confuse a compact projection with the authoritative record.**
