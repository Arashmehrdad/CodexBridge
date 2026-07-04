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
- `git_log`
- `inspect_repo_status`
- `git_diff_summary`

Calls use `repo_name` from `config.yaml` plus repo-relative paths such as `src/app.py`. They do not accept arbitrary filesystem paths. Read tools block paths like `.git`, real `.env` files, virtualenv directories, symlinks/junction escapes, many secret-like files, and they redact obvious secret values from returned text.

## Repository Knowledge

Repository knowledge is exposed through:

- `refresh_repo_wiki`
- `read_repo_wiki`
- `search_repo_knowledge`
- `remember_repo_decision`

`refresh_repo_wiki` generates or incrementally refreshes wiki pages under `.codexbridge/wiki` inside the target repository. `read_repo_wiki` reads a generated page such as `overview.md`. `search_repo_knowledge` searches both the generated wiki and repository-scoped decision memory in one call. `remember_repo_decision` stores a repository-scoped decision record by default so later planning and recovery runs can reuse the context.

## Allowlisted Project Commands

Built-in command profiles:

- `pytest`
- `ruff_check`
- `ruff_format_check`
- `ruff_format`
- `mypy`
- `pip_check`
- `git_status`
- `git_diff_check`

Command execution rules:

- Commands run from validated profiles only.
- Commands execute with `argv` arrays and `shell=False`.
- When possible, the target repository's `.venv` or `venv` Python interpreter is preferred automatically.
- New project-specific commands are registered once under `repos.<name>.command_profiles` in `config.yaml`.
- `run_project_command(repo_name, command_id)` is for short profiles only.
- Full `pytest` is configured async-only and must use `start_project_command_async`, then `get_run_status` and `get_run_result`.
- `start_pytest_path_async(repo_name, path)` is the dedicated scoped pytest entrypoint for one validated repo-relative directory or `.py` file target, with optional `::` node selectors.
- Scoped pytest accepts no arbitrary flags, command strings, environment overrides, or extra argv. CodexBridge validates and normalizes the target before queueing and again in the worker.
- Async `pytest` runs get per-run temp directories, isolated `--basetemp`, and persisted `stdout.txt` / `stderr.txt` artifacts under the run directory.
- Read-only command profiles intentionally fail if they change tracked or untracked repository state. If a test command must generate repository artifacts, register a separate profile with `writes_files: true` or change the tests so they stop writing into the repository.
- Host capabilities such as CUDA are available only if the server account, driver, project environment, and command profile already support them. CodexBridge does not install CUDA, Python packages, or project dependencies.

If a long command times out in synchronous mode, retrying it synchronously is not the correct recovery path. Register or use the durable async profile and recover through the run tools instead.

## Safe Repository Changes

Preview-first write tools:

- `preview_repo_patch`
- `preview_repo_file_creation`
- `preview_repo_file_removal`
- `apply_previewed_repo_change`
- `revert_managed_patch`

Direct compatibility tools:

- `apply_repo_patch`
- `create_repo_file`
- `delete_repo_file`
- `move_repo_file`

Current behavior:

- `preview_repo_patch` is read-only and supports multiple non-overlapping edits to the same file, then composes them into one atomic file result.
- `preview_repo_file_creation` and `preview_repo_file_removal` are read-only previews and never change the working tree.
- `apply_previewed_repo_change` accepts only `repo_name` and `patch_id`. It reads executable-looking content from the local opaque preview bundle instead of resending content in the write request.
- Opaque preview bundles are repository-bound and validate payload hashes, current file hashes, Git `HEAD` where applicable, path limits, duplicate paths, symlinks, file/byte/line limits, and patch state before writing.
- Preview/apply supports `modify`, `create`, and `remove`.
- `revert_managed_patch` uses saved rollback data and stale-state protection instead of `git reset` or `git checkout`.
- `commit_selected_files` stages and commits only explicitly listed changed files. Pushing through the current ChatGPT/OpenAI tool path is unavailable because prior attempts were blocked by the platform, while a developer may still push locally with Git outside the bridge workflow.

The older direct write tools remain available for compatibility and direct operations, but the preview/apply flow is the safer default.

## Async Run Workflow

Durable async runs cover:

- `start_codex_plan_task_async`
- `start_codex_implement_task_async`
- `start_project_command_async`
- `start_pytest_path_async`

Read and control them with:

- `get_run_status`
- `get_run_events`
- `get_run_result`
- `list_runs`
- `cancel_run`

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
