# CodexBridge

CodexBridge is a Windows-first local FastMCP bridge between ChatGPT, whitelisted Git repositories, Codex CLI, allowlisted host commands, Git, repository knowledge, and durable run artifacts. It keeps repository inspection separate from write operations, validates every repo by name from `config.yaml`, and records durable run state under `runs/`.

## Architecture

```text
ChatGPT
  -> MCP connector
  -> CodexBridge FastMCP server (HTTP /mcp)
     -> repo whitelist + repo-relative path validation
     -> repository read tools
     -> repository write/preview tools
     -> Codex plan/implement runner
     -> allowlisted command profiles
     -> allowlisted remote-server aliases and command profiles
     -> repository wiki + decision memory
     -> durable async run store + artifacts
     -> supervisors
  -> whitelisted Git repositories
  -> Codex CLI / Git / local Python environments
  -> structured results back to ChatGPT
```

The bridge is designed so ChatGPT can inspect first, plan safely, execute narrow approved changes, recover durable async runs, and use repository-scoped knowledge without exposing arbitrary filesystem access.

## Setup

```powershell
cd D:\Github\CodexBridge
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
copy config.example.yaml config.yaml
```

`pyproject.toml` defines the editable install and `dev` extras. `config.yaml` must list only approved repositories. Every `repos.<name>.path` must exist and must contain a `.git` directory or server startup/config loading will fail.

Current config example:

```yaml
repos:
  stream_alpha:
    path: "D:/Github/Stream_Alpha"
    default_tests:
      - "python -m pytest -q"
      - "python -m pip check"
    command_profiles:
      - command_id: "pytest"
        argv: ["python", "-m", "pytest", "tests/unit", "-q"]
        timeout_seconds: 600
        description: "Run the unit test subset"
        writes_files: false
        async_only: true
runs_dir: "runs"
codex:
  executable: "codex"
  model: ""
  windows_sandbox: ""
  sandbox_private_desktop: null
  default_timeout_seconds: 1800
gemini:
  enabled: false
supervisors:
  default_autonomy_profile: "balanced"
  autonomy_profiles:
    balanced:
      stop_on_requires_human: true
      max_plan_tier: 1
      max_implementation_tier: 2
      require_tests_for_non_docs_changes: false
```

`repos.<name>.command_profiles` is optional. Do not add unsupported keys and do not assume arbitrary shell text is accepted; command registration is by `command_id` plus `argv`.

## Startup

Direct server start:

```powershell
python -m codexbridge.server --config config.yaml --transport http --host 127.0.0.1 --port 8000 --path /mcp
```

That default route serves at `http://127.0.0.1:8000/mcp`.

Helper script:

```powershell
.\scripts\start_codexbridge_mcp.ps1
```

`scripts/start_codexbridge_mcp.ps1` can:

- check the local MCP endpoint
- start the FastMCP server if it is not ready
- optionally check/start the configured Cloudflare tunnel unless `-NoTunnel` is used
- write service logs under `runs\service_logs`

A plain `GET` returning HTTP `406 Not Acceptable` is only route readiness for the MCP endpoint. It means the route is mounted, not that a full MCP client handshake has completed.

Windows service controller:

```powershell
# Open the interactive TUI.
.\codexbridge-service.cmd

# Direct service actions.
.\codexbridge-service.cmd start
.\codexbridge-service.cmd stop
.\codexbridge-service.cmd restart
.\codexbridge-service.cmd status
.\codexbridge-service.cmd logs
.\codexbridge-service.cmd diagnostics

# Inspect or change the supervisor autonomy profile.
.\codexbridge-service.cmd profile-status
.\codexbridge-service.cmd profile-set -Profile permissive
.\codexbridge-service.cmd profile-set -Profile balanced -RestartAfterProfileChange
```

The TUI displays the configured supervisor profile and the current server/tunnel process state. Choose **Select supervisor profile** to switch among the profiles defined under `supervisors.autonomy_profiles` in `config.yaml`. The update is validated and rolled back automatically if the resulting configuration is invalid. A running server must be restarted before the new profile takes effect; the TUI offers to do this immediately.

Server `start`, `stop`, and `restart` actions manage only the local CodexBridge server. They never stop or restart the Cloudflare tunnel. Use the separate tunnel actions or the explicit combined actions when both processes should change. The lifecycle controller supports both Windows PowerShell 5.1 and PowerShell 7, including the normal connection-refused period while a stopped server is starting.

The controller writes service output under `runs\service_logs`. Actions that require elevation use the normal Windows UAC prompt, and the manager verifies process identity before stopping a server or tunnel.

If you publish the local MCP route through a tunnel, keep the `/mcp` suffix in the connector URL, for example `https://example-tunnel.trycloudflare.com/mcp` or `https://example.ngrok-free.app/mcp`.

After server code changes, `config.yaml` changes, or MCP tool-surface changes, restart the server and then refresh or reconnect the ChatGPT connector so it picks up the current endpoint and tool definitions.

## Recommended Workflow

Use the bridge in this order:

1. Inspect first with repository read/search tools.
2. Plan with `codex_plan_task` or `start_codex_plan_task_async`.
3. Approve the plan outside the bridge.
4. Implement with `codex_implement_task` or `start_codex_implement_task_async` only after approval and only with an exclusive `allowed_files` list.
5. Inspect the resulting diff with `repo_git_diff`, `git_diff_summary`, or `repo_git_status`.
6. Use `commit_selected_files` only after explicit approval.

## OpenAI Platform Limitations

Pushing through the current ChatGPT/OpenAI tool path is unavailable because prior attempts were blocked by the platform. A developer may still push locally with Git outside the bridge workflow.

OpenAI safety checks may also intermittently block an otherwise valid MCP tool call before it reaches CodexBridge. Because the request never arrives at the server, CodexBridge cannot inspect, log, retry, or bypass that block. When no CodexBridge response or `run_id` was returned, one identical retry may be appropriate. Once a `run_id` exists, do not repeat the start action; poll the existing run instead.

These are limitations of the current ChatGPT/OpenAI tool path, not CodexBridge product policies.

The human is not expected to run setup or routine repository validation during the normal bridge workflow.

## Repository Inspection

These MCP tools are available for safe repository inspection:

- `list_repo_files`
- `read_repo_file`
- `read_repo_files`
- `search_repo_text`
- `get_recently_modified_files`
- `repo_git_status`
- `repo_git_diff`
- `inspect_commit_range`
- `git_log`
- `inspect_repo_status`
- `git_diff_summary`

Calls use `repo_name` from `config.yaml` plus repo-relative paths such as `src/app.py`. They do not accept arbitrary filesystem paths. Read tools block paths like `.git`, real `.env` files, virtualenv directories, symlinks/junction escapes, many secret-like files, and they redact obvious secret values from returned text.

`inspect_commit_range` is a read-only exact-range helper. It accepts only two full 40-character commit hashes and returns bounded `--name-status`, `--stat`, and unified diff data without accepting flags, rev syntax, or paths.

## Repository Knowledge

Repository knowledge is exposed through:

- `refresh_repo_wiki`
- `read_repo_wiki`
- `search_repo_knowledge`
- `remember_repo_decision`

`refresh_repo_wiki` generates or incrementally refreshes wiki pages under `.codexbridge/wiki` inside the target repository. That directory is generated local knowledge, should stay ignored by Git, and existing generated pages are reused instead of being force-rewritten outside a refresh request. `read_repo_wiki` reads a generated page such as `overview.md`. `search_repo_knowledge` searches both the generated wiki and repository-scoped decision memory in one call. `remember_repo_decision` stores a repository-scoped decision record by default so later planning and recovery runs can reuse the context.

## Allowlisted Project Commands

Built-in command profiles:

- `pytest`
- `pip_check`
- `git_status`

Command execution rules:

- Commands run from validated profiles only.
- Commands execute with `argv` arrays and `shell=False`.
- When possible, the target repository's `.venv` or `venv` Python interpreter is preferred automatically.
- New project-specific validation commands are registered once under `repos.<name>.command_profiles` in `config.yaml`; unrestricted or ad hoc commands use the public PowerShell gateway instead.
- Project commands remain an internal durable substrate for workflows and typed validation adapters; unrestricted PowerShell is the public arbitrary-command gateway.
- Full `pytest` is configured async-only and uses that durable command path.
- `start_pytest_path_async(repo_name, path)` is the dedicated scoped pytest entrypoint for one validated repo-relative directory or `.py` file target, with optional `::` node selectors.
- Scoped pytest accepts no arbitrary flags, command strings, environment overrides, or extra argv. CodexBridge validates and normalizes the target before queueing and again in the worker.
- Async `pytest` runs get per-run temp directories, isolated `--basetemp`, and persisted `stdout.txt` / `stderr.txt` artifacts under the run directory.
- Read-only command profiles intentionally fail if they change tracked or untracked repository state. If a test command must generate repository artifacts, register a separate profile with `writes_files: true` or change the tests so they stop writing into the repository.
- Host capabilities such as CUDA are available only if the server account, driver, project environment, and command profile already support them. CodexBridge does not install CUDA, Python packages, or project dependencies.

If a long command times out in synchronous mode, retrying it synchronously is not the correct recovery path. Register or use the durable async profile and recover through the run tools instead.

## Docker and Docker Compose

Docker support is a dedicated bounded subsystem, not an arbitrary Docker CLI shell. Enable it globally under `docker` and optionally configure Compose files, a Compose project name, and fixed in-container command profiles per repository.

```yaml
docker:
  enabled: true
  executable: "docker"
  max_output_bytes: 100000
  default_timeout_seconds: 600
  allow_push: true
  allow_prune: true
  allow_remove: true
  allow_compose_down_volumes: true
  confirmation_token: "CONFIRM_DOCKER_HIGH_RISK"
repos:
  my_app:
    path: "D:/Github/my_app"
    docker_compose_files: ["docker-compose.yml"]
    docker_project_name: "my-app"
    docker_exec_profiles:
      - command_id: "health"
        argv: ["python", "-m", "app.health"]
        timeout_seconds: 60
        writes_files: false
```

Docker MCP tools:

- `list_docker_capabilities(repo_name)` lists supported operations, gates, Compose configuration, and configured exec command IDs.
- `docker_health()` checks Docker Engine and Compose availability.
- `docker_inspect(repo_name, operation, ...)` performs fixed read-only inspection such as engine info, containers, images, networks, volumes, disk usage, Compose config/ps/images/logs, and bounded object details.
- `start_docker_action_async(repo_name, action, ...)` queues lifecycle and administrative work as a durable run. Poll it with the standard run-status and run-result tools.

Supported actions cover Compose build/up/down/start/stop/restart/pause/unpause/kill/pull, configured Compose or container exec, image build/pull/tag/push, container lifecycle, network and volume creation, removals, and builder/container/image/network/volume/system cleanup. Compose commands execute from the validated repository root and use only repository Compose files. Image-build contexts and Dockerfiles must be repository-relative.

Push, cleanup, removals, and `compose down` with volumes require two independent checks: the relevant `allow_*` setting must be enabled and the exact configured confirmation token must be supplied on that call. The confirmation token is an approval phrase, not a credential. Docker exec accepts only `command_id` values pre-registered under `docker_exec_profiles`; free-form command text, arbitrary argv, shell chaining, interactive shells, and arbitrary host paths are unsupported. Every subprocess uses an argv list with `shell=False`, bounded output, timeouts, durable artifacts for async operations, and repository operation locks.

## Cloudflare DNS, Edge, Rulesets, and Tunnels

Cloudflare support is a global CodexBridge service with repository-scoped access. Credentials and account/zone profiles are defined once under `cloudflare.profiles`; each repository explicitly lists the profile IDs it may use. Adding another website requires only a new global profile and a repository binding, not new Cloudflare code or project-specific tools. It uses the official client-v4 API through Python HTTPS requests and does not expose arbitrary URLs, endpoint paths, HTTP methods, headers, tokens, or GraphQL text.

```yaml
repos:
  andia_beauty:
    path: "D:/Github/Andia_Beauty"
    cloudflare_profiles: ["production"]
  second_site:
    path: "D:/Github/Second_Site"
    cloudflare_profiles: ["second_site_production"]

cloudflare:
  enabled: false
  api_base_url: "https://api.cloudflare.com/client/v4"
  token_env: "CLOUDFLARE_API_TOKEN"
  env_file: ".env"
  timeout_seconds: 30
  max_output_bytes: 500000
  allow_dns_write: false
  allow_cache_purge: false
  allow_zone_settings: false
  allow_rulesets: false
  allow_tunnels: false
  allow_turnstile_write: false
  allow_turnstile_secret_rotation: false
  allow_turnstile_delete: false
  allow_delete: false
  confirmation_token: "CONFIRM_CLOUDFLARE_HIGH_RISK"
  profiles:
    production:
      account_id_env: "CLOUDFLARE_ACCOUNT_ID"
      zone_id_env: "CLOUDFLARE_ZONE_ID"
      zone_name: "example.com"
      allowed_dns_names: ["example.com", "www.example.com"]
      allowed_ruleset_phases: ["http_request_firewall_custom"]
      allowed_tunnel_ids: []
      allowed_turnstile_sitekeys: []
      turnstile:
        secret_destination:
          type: "env_file"
          path: ".env.production"
          variable: "TURNSTILE_SECRET_KEY"
    second_site_production:
      account_id_env: "SECOND_SITE_CLOUDFLARE_ACCOUNT_ID"
      zone_id_env: "SECOND_SITE_CLOUDFLARE_ZONE_ID"
      zone_name: "second-example.com"
      allowed_dns_names: ["second-example.com", "www.second-example.com"]
      allowed_ruleset_phases: ["http_request_firewall_custom"]
      allowed_tunnel_ids: []
      allowed_turnstile_sitekeys: []
      turnstile:
        secret_destination:
          type: "env_file"
          path: ".env.production"
          variable: "SECOND_SITE_TURNSTILE_SECRET_KEY"
```

The API token and optional account/zone IDs can be loaded from the configured `.env` file next to `config.yaml`, or from operating-system environment variables. Operating-system variables take priority. They are read only at request time and are never accepted as MCP arguments or stored in durable inputs. The repository `.gitignore` excludes `.env`.

```dotenv
CLOUDFLARE_API_TOKEN=replace-with-a-scoped-api-token
CLOUDFLARE_ACCOUNT_ID=replace-with-the-32-character-account-id
CLOUDFLARE_ZONE_ID=replace-with-the-32-character-zone-id
```

Profiles restrict DNS names, ruleset phases, tunnel IDs, and mutable Turnstile sitekeys independently. An empty `allowed_turnstile_sitekeys` list permits profile-authorized widget listing but denies widget mutation. Repository bindings are deny-by-default: a repository cannot inspect or modify a profile unless that profile ID appears in its `cloudflare_profiles` list. Do not use the Global API Key and do not paste the token into chat, configuration YAML, logs, or command history.

Cloudflare MCP tools:

- `list_cloudflare_capabilities(repo_name)` lists fixed operations and only the profiles authorized for that repository.
- `cloudflare_health(repo_name, profile_id)` verifies the configured token and authorized profile scope without changing account state.
- `cloudflare_inspect(repo_name, profile_id, operation, ...)` supports the exact names `list_accounts`, `list_zones`, `get_zone`, `list_dns_records`, `turnstile_widgets`, `turnstile_widget`, `list_tunnels`, `list_rulesets`, and `get_ssl_settings`, plus the existing token, DNSSEC, Universal SSL, route, connection, configuration, and bounded analytics operations. `list_turnstile_widgets` remains a compatibility alias for `turnstile_widgets`. Account and zone discovery remains constrained to the authorized profile account.
- `start_cloudflare_action_async(repo_name, profile_id, action, ...)` supports the exact names `create_dns_record`, `update_dns_record`, `delete_dns_record`, `purge_cache`, `update_ssl_settings`, `create_tunnel`, `turnstile_create`, `turnstile_update`, `turnstile_rotate_secret`, and `turnstile_delete`, while retaining the existing compatibility action names.

Turnstile create and update require `allow_turnstile_write`. Secret rotation requires both `allow_turnstile_write` and `allow_turnstile_secret_rotation`; deletion requires `allow_turnstile_delete`. Rotation and deletion also require the exact configured high-risk confirmation phrase. Every widget-specific operation is restricted to `allowed_turnstile_sitekeys`. DNS create/update requires `allow_dns_write`; cache purge, zone settings, rulesets, and tunnels retain their existing independent gates.

Payloads are bounded and schema-checked, DNS names remain within the configured zone and optional allowlist, and ruleset phases, tunnel IDs, and mutable Turnstile sitekeys remain profile-scoped. Tunnel secrets are generated locally when required and are removed from returned data. Responses are recursively redacted and size-limited. Durable runs store sanitized `stdout.txt`, `stderr.txt`, and `cloudflare_result.json` artifacts under `runs/<run_id>/`.

`turnstile_rotate_secret` always sends `{"invalidate_immediately": false}` to Cloudflare. The previous secret therefore remains valid for the two-hour grace period, and Cloudflare does not permit another rotation during that period. The returned new secret is removed from the Cloudflare response object and written directly to the profile's repository-relative `turnstile.secret_destination`. The destination and its temporary replacement must both be Git-ignored regular files. The bridge returns only widget metadata, rotation status, the two-hour grace period, and whether the destination was updated; it never writes the secret to MCP output, stdout, stderr, audit events, durable run inputs, result JSON, reports, diffs, or Git commits. `turnstile_create` uses the same direct secret-delivery path because widget creation also returns a secret.

`get_tunnel_token` remains reported as `secret_delivery_pending`. Cloudflare remains disabled by default, and all write gates default to false. Development and unit tests use mocked HTTP responses and make no live Cloudflare account changes. No live account read or write occurs until the subsystem is enabled, a scoped profile and environment token are configured, and a specific MCP operation is called.

## SSH Deployment and Remote Debugging

CodexBridge uses the local Windows OpenSSH and SCP clients through stable aliases from `%USERPROFILE%/.ssh/config`. Tailscale MagicDNS can provide stable private hostnames, but it is optional; public IP addresses also work behind an alias.

```sshconfig
Host my-vps
    HostName server-name.tailnet-name.ts.net
    User ubuntu
    IdentityFile C:/Users/arash/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

```yaml
ssh:
  enabled: true
  executable: "ssh"
  scp_executable: "scp"
  max_output_bytes: 100000
  max_transfer_bytes: 500000000
  transfer_timeout_seconds: 1800
  allow_transfer: true
  allow_deploy: true
  allow_admin: true
  allow_delete: false
  allow_reboot: false
  confirmation_token: "CONFIRM_SSH_HIGH_RISK"
  hosts:
    my_vps:
      ssh_alias: "my-vps"
      connect_timeout_seconds: 20
      use_sudo: true
      allowed_remote_roots:
        - "/srv/my-app"
        - "/var/log"
      allowed_executables:
        - "docker"
        - "git"
        - "curl"
        - "systemctl"
        - "journalctl"
      watchdog:
        enabled: false
        enforcement_mode: "observe_only"
        max_gpu_memory_percent: 95
        max_gpu_temperature_c: 90
        max_system_memory_percent: 95
        min_disk_free_percent: 5
      deployment_profiles:
        app:
          repo_name: "my_app"
          remote_root: "/srv/my-app"
          local_subdir: "."
          compose_file: "docker-compose.yml"
          compose_project_name: "my-app"
          compose_build: true
          shared_files:
            "/srv/my-app/shared/.env.production": ".env.production"
          health_command_id: "health"
      command_profiles:
        - command_id: "health"
          argv: ["curl", "-fsS", "http://127.0.0.1:3000/health"]
          timeout_seconds: 60
          writes_remote: false
```

SSH MCP tools:

- `list_ssh_capabilities()` lists hosts, remote roots, deployments, fixed commands, supported inspections and risk gates.
- `ssh_host_health(host_id)` performs a non-interactive connection check.
- `ssh_environment_probe(host_id)` returns structured OS, working-directory, Python, virtual-environment, PyTorch, CUDA, RAM, root-disk and GPU metadata without returning the remote environment-variable set.
- `ssh_gpu_telemetry(host_id)` returns structured NVIDIA device and compute-process telemetry, including utilization, memory, temperature and power readings.
- `ssh_inspect(host_id, operation, ...)` provides bounded system, process, port, network, systemd, journal, Docker, Git and remote-file diagnostics.
- `start_ssh_command_async(host_id, command_id)` preserves compatibility with fixed command profiles.
- `start_ssh_monitored_command_async(host_id, command_id)` is the separate monitored path for watchdog-eligible command profiles.
- `start_ssh_action_async(host_id, action, ...)` performs durable service, Compose, Git, package and filesystem administration. `run_argv` accepts only a configured executable plus validated argv; it is not a shell.
- `start_ssh_transfer_async(...)` uploads only repository-scoped local files and downloads only into the durable run directory.
- `start_ssh_deployment_async(host_id, deployment_id, confirmation)` creates a filtered repository archive, uploads it, extracts a release, verifies and links server-side shared secret files, starts or rebuilds Compose with a stable project name, runs the configured health check, and updates the `current` symlink only after health succeeds.

Read-only file access is limited to `allowed_remote_roots` and blocks secret-like files. Uploads reject local secret-like files and parent traversal. Deployment archives exclude `.git`, virtual environments, dependency caches, `node_modules`, run storage and secret-like files. Production `.env` files should live under a server-side shared directory and be linked into each release through `shared_files`; they are never downloaded, packaged, logged or returned to ChatGPT.

Service stops, Compose shutdown, package administration, deletion, reboot, shutdown, overwrite transfers, emergency argv execution and deployments require their matching `allow_*` gate plus the exact configured confirmation token. Every local subprocess uses an argv list with `shell=False`, batch mode, strict host-key checking, disabled password and keyboard-interactive authentication, disabled agent forwarding, cleared forwardings, output limits, timeouts and durable artifacts. Interactive shells, arbitrary command strings, shell operators, tunnels and port forwarding remain unsupported.

Monitored SSH commands are opt-in and separate from ordinary SSH commands. A monitored start is refused unless the command profile has `watchdog_eligible: true` and the host watchdog is enabled. Automatic termination is active only when all of the following are true: `enabled`, `enforcement_mode: "terminate"`, `allow_automatic_termination: true`, and the profile is watchdog-eligible. Observe-only monitored runs record breaches and never terminate solely on a threshold breach.

When termination is active, CodexBridge starts the configured remote argv in a new remote session/process group, persists bounded remote identity metadata (`pid`, `pgid`, `/proc` start-time ticks), samples the structured environment/GPU probe at the configured interval, requires the configured number of consecutive breached samples, and attempts confirmed remote process-group termination. Timeout and cancellation handling are fail-closed: if remote termination is unconfirmed, the run remains `cancellation_pending` or fails with `safety_failure: true` instead of claiming the remote process stopped safely.

A completed remote write means the remote command exited successfully; CodexBridge still reports `remote_state_verified: false` unless a separate inspection or deployment health check confirms the relevant state.

## Controlled External Fixtures

External fixture validation is disabled by default. Configure `external_fixtures` with exact allowed HTTPS hosts, byte and time limits, then call `start_external_fixture_validation_async` with a SHA-256 and a validation mode.

Fixtures are stored only in durable run storage, validated with `none`, `json`, `py_compile`, or `bash_n`, and discarded after the run. URLs containing authentication data, query parameters, fragments, or unapproved hosts are rejected.

## Safe Repository Changes

Preview-first write tools:

- `preview_repo_patch`
- `preview_repo_file_creation`
- `preview_repo_file_removal`
- `apply_previewed_repo_change`
- `get_patch_status`
- `preview_managed_artifact_cleanup`
- `apply_managed_artifact_cleanup`
- `revert_managed_patch`

Direct compatibility tools:

- `apply_repo_patch`
- `create_repo_file`
- `delete_repo_file`
- `move_repo_file`

Current behavior:

- `preview_repo_patch` is read-only and supports multiple non-overlapping edits to the same file, then composes them into one atomic file result.
- `preview_repo_file_creation` and `preview_repo_file_removal` are read-only previews and never change the working tree.
- `apply_previewed_repo_change` accepts only `repo_name` and `patch_id`. It reads executable-looking content from the local opaque preview bundle instead of resending content in the write request, and successful retries return the original result idempotently.
- Opaque preview bundles are repository-bound and validate payload hashes, current file hashes, Git `HEAD` where applicable, path limits, duplicate paths, symlinks, file/byte/line limits, and patch state before writing. Large payloads are split into hash-verified chunks and reassembled before apply.
- Preview/apply supports `modify`, `create`, and `remove`.
- `revert_managed_patch` uses saved rollback data and stale-state protection instead of `git reset` or `git checkout`.
- `commit_selected_files` stages and commits only explicitly listed changed files. Pushing through the current ChatGPT/OpenAI tool path is unavailable because prior attempts were blocked by the platform, while a developer may still push locally with Git outside the bridge workflow.

The older direct write tools remain available for compatibility and direct operations, but the preview/apply flow is the safer default.

`list_capabilities` returns the live action schemas and typed patch-operation contract. Dictionary tool responses include `server_build_hash`, `schema_hash`, and `capability_epoch` so clients can detect stale server processes or schemas.

## Async Run Workflow

Durable async runs cover:

- `start_codex_plan_task_async`
- `start_codex_implement_task_async`
- `start_workflow`
- `start_pytest_path_async`
- `start_external_fixture_validation_async`
- `start_cloudflare_action_async`
- `start_ssh_command_async`
- `start_ssh_action_async`
- `start_ssh_transfer_async`
- `start_ssh_deployment_async`

Read and control them with:

- `get_run_status`
- `get_run_events`
- `get_run_result`
- `list_runs`
- `cancel_run`
- `get_workflow_status`
- `get_workflow_events`
- `get_workflow_result`
- `cancel_workflow`

Workflow:

1. Start the async job and save the returned `run_id`.
2. Poll `get_run_status(run_id)` until the run is terminal.
3. Use `get_run_events(run_id)` for timeline updates when needed.
4. Read the final structured payload with `get_run_result(run_id)`.
5. If the original caller loses the ID, recover it with `list_runs(...)`.
6. If a run must stop, use `cancel_run(run_id)`.

Scoped pytest example:

1. Call `start_pytest_path_async("codexbridge", "tests/test_job_worker.py::test_project_command_worker_rebuilds_scoped_pytest_profile")`.
2. Save the returned `run_id`.
3. Poll `get_run_status(run_id)` until the status is terminal.
4. Read `get_run_result(run_id)` for the final `path`, argv, exit code, and saved output summary.

If OpenAI safety blocks a tool call before CodexBridge returns a response or `run_id`, the call never reached the bridge. One identical retry may be appropriate in that case. Once a `run_id` exists, do not reissue the start call; poll the existing run instead.

Async state is durable across process restarts because run metadata is stored in `runs/codexbridge.sqlite3` with SQLite WAL enabled, while per-run artifacts are written under `runs/<run_id>/`. Long-running allowlisted commands and Codex jobs persist their inputs, events, results, and output files there. Recover by polling or re-reading the saved run, not by reissuing a timed-out synchronous long command.

### Durable Workflows

When you already know the full multi-step engineering sequence, submit one structured workflow with `start_workflow(...)` instead of starting and polling each child run manually. The workflow worker launches the child runs through the existing durable run APIs, waits internally for terminal child status, records step outcomes, and advances the next eligible step without needing repeated ChatGPT monitoring turns.

Supported workflow step types in this batch:

- `codex_implement`
- `project_command`
- `pytest_path`
- `git_readonly`
- `local_summary`

Typical use:

1. Call `start_workflow(repo_name, objective, steps)` with the full ordered step list.
2. Save the returned `workflow_id`.
3. Prefer waiting for the generated PulseSender artifacts under `runs/workflows/<workflow_id>/` instead of polling every child run.
4. Use `get_workflow_status`, `get_workflow_events`, `get_workflow_result`, and `cancel_workflow` for inspection, recovery, or cancellation when needed.

Example:

```powershell
start_workflow `
  -repo_name "codexbridge" `
  -objective "Implement batch and validate it" `
  -steps @(
    @{
      id = "implement"
      type = "codex_implement"
      parameters = @{
        approved_plan = "Implement the approved batch"
        allowed_files = @("codexbridge/workflows/models.py", "tests/test_workflows.py")
        tests = @("python -m pytest -q tests/test_workflows.py")
      }
    },
    @{
      id = "targeted_pytest"
      type = "pytest_path"
      depends_on = @("implement")
      parameters = @{ path = "tests/test_workflows.py" }
    },
    @{
      id = "summary"
      type = "local_summary"
      depends_on = @("implement", "targeted_pytest")
      parameters = @{}
    }
  )
```

## Supervisor Workflow

Supervisor tools remain available for staged recovery work:

- `start_supervised_recovery_task`
- `get_supervisor_status`
- `get_supervisor_events`
- `get_supervisor_result`
- `resume_supervisor`
- `pause_supervisor`
- `cancel_supervisor`
- `get_supervisor_notifications`
- `get_supervisor_resume_prompt`

Typical use:

1. Start a supervisor with `start_supervised_recovery_task(...)`.
2. Inspect it with `get_supervisor_status(...)`.
3. Review durable events and linked child runs.
4. Use `resume_supervisor(supervisor_id)` to advance exactly one safe step.

Current limits are intentional:

- There is no background scheduler yet.
- There is no approve-plan MCP tool yet.
- Use `pause_supervisor(supervisor_id)` only when the supervisor is `queued` or `needs_input`.
- Resume prompts are written to `runs/supervisors/<supervisor_id>/resume_prompt.txt` and point to saved artifacts instead of embedding large raw logs.
- Notification sinks are disabled by default.

## Local Browser Pulse Sender

`scripts/browser_pulse_sender.py` remains a standalone local helper for supervisor handoff states. It is not part of the MCP server and does not modify supervisor behavior. It connects to an existing Chrome or Edge session through local CDP at `http://127.0.0.1:9222`, opens a real ChatGPT chat URL, sends a sanitized resume prompt, and can optionally close the tab.

Recommended browser-launch path:

```powershell
.\scripts\start_chrome_cdp.ps1 -Browser chrome -Port 9222 -UserDataDir "D:\Github\CodexBridge\.pulse-chrome-profile" -ChatUrl "https://chatgpt.com/c/REAL_CHAT_ID"
```

Dry-run smoke test:

```powershell
python .\scripts\browser_pulse_sender.py --runs-dir runs --supervisor-id <supervisor_id> --chat-url https://chatgpt.com/c/<chat_id> --prompt "Browser pulse smoke test. Reply only: pulse received." --dry-run --once
```

Send mode:

```powershell
python .\scripts\browser_pulse_sender.py --runs-dir runs --supervisor-id <supervisor_id> --chat-url https://chatgpt.com/c/<chat_id> --prompt "Browser pulse smoke test. Reply only: pulse received." --send --once --close-tab
```

Current limitations remain explicit:

- It requires a real ChatGPT chat URL.
- It depends on the user's already-authenticated browser session.
- It does not export or store cookies, passwords, or tokens.
- It is local-only helper automation, not an MCP tool.

## Safety Model

CodexBridge's practical safety boundary is:

- repository whitelist enforcement by `repo_name`
- repo-relative path validation for reads and writes
- `shell=False` execution for allowlisted command profiles
- allowlisted SSH aliases and remote command IDs with strict non-interactive OpenSSH options
- fixed official Cloudflare API endpoints with profile-scoped zones, DNS names, ruleset phases and tunnel IDs
- capped command and read outputs
- secret redaction on repository reads and many returned summaries
- pushing through the current ChatGPT/OpenAI tool path is unavailable because prior attempts were blocked by the platform, while a developer may still push locally with Git outside the bridge workflow
- explicit approval before using `commit_selected_files`
- rollback artifacts for managed repository changes

## Validation

For a documentation-only update, the required check is:

```powershell
git diff --check
```

Codex runs these checks and reports the results.
