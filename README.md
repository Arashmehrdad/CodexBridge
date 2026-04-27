# CodexBridge

CodexBridge is a local Windows 11 MCP bridge that lets ChatGPT hand compact implementation work to Codex CLI inside whitelisted repositories.

Architecture:

```text
ChatGPT app
  -> MCP connector
  -> CodexBridge FastMCP server
  -> repo whitelist lookup
  -> Codex CLI / Git CLI
  -> runs/ artifacts
  -> structured result back to ChatGPT
```

ChatGPT acts as the strategist, researcher, and roadmap writer. Codex acts as the planner, implementer, and test runner. The bridge separates read-only tools from write tools, records every Codex run, and never pushes automatically.

## Human Involvement Policy

CodexBridge exists to reduce human involvement. The human is not expected to run setup, tests, server checks, connector readiness checks, `git status`, or tunnel checks by hand.

Codex should run non-destructive local checks and report results. The human only approves:

- plans
- commits
- pushes
- unsafe external actions
- ChatGPT connector UI approval that cannot be automated safely

## Batch Execution Policy

Codex plans work in small batches. After the human approves the batch plan, Codex implements all approved batches sequentially in one run and stops only for a blocker or safety issue.

Each batch reports changed files, checks run, results, and remaining risks.

## Windows Setup Reference

```powershell
cd D:\Github\CodexBridge
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
copy config.example.yaml config.yaml
```

These commands are documented for transparency. Codex should run required local setup and validation when asked to verify the bridge.

`config.yaml` must point only to approved repositories, and every repo path must exist and contain a `.git` directory.

Example:

```yaml
repos:
  stream_alpha:
    path: "D:/Github/Stream_Alpha"
    default_tests:
      - "python -m pytest"
runs_dir: "runs"
codex:
  executable: "codex"
  default_timeout_seconds: 1800
gemini:
  enabled: false
```

## Autonomous Verification

```powershell
python -m codexbridge.self_check --config config.yaml --path /mcp
python -m pytest -q
python -m pip check
```

Codex runs these checks and reports the results.

## Start The MCP Server

```powershell
python -m codexbridge.server --config config.yaml --transport http --host 127.0.0.1 --port 8000 --path /mcp
```

Readiness checks may see HTTP `406 Not Acceptable` from a plain `GET /mcp`. That is acceptable as route-mounted evidence only because MCP Streamable HTTP expects protocol-specific headers; it is not full protocol success.

## Expose To ChatGPT

Cloudflare Tunnel:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Point the ChatGPT connector to the HTTPS tunnel URL ending in `/mcp`, for example:

```text
https://example-tunnel.trycloudflare.com/mcp
```

ngrok:

```powershell
ngrok http 8000
```

Point the ChatGPT connector to the HTTPS ngrok URL ending in `/mcp`, for example:

```text
https://example.ngrok-free.app/mcp
```

Tunnel URLs expose local tooling. Only use them after configuring the repo whitelist and confirming that no secrets are exposed in prompts, logs, or summaries. Actual ChatGPT connector approval/login remains a human approval step.

## ChatGPT Connector Notes

Configure the ChatGPT MCP connector to point at the local or tunneled CodexBridge MCP endpoint. Use only repo names from `config.yaml`; never send filesystem paths.

Recommended workflow:

1. Call `inspect_repo_status(repo_name)`.
2. Call `codex_plan_task(repo_name, task, constraints)`.
3. Review and approve the returned plan.
4. Call `codex_implement_task(repo_name, approved_plan, allowed_files, tests)`.
5. Review `git_diff_summary(repo_name)`.
6. Commit selected files with `commit_selected_files(...)` only after explicit approval.

`push_current_branch` is intentionally not implemented in the MVP.

## Async Run Workflow

CodexBridge v2 adds durable async run tools for longer jobs:

1. Call `start_codex_plan_task_async(...)` or `start_codex_implement_task_async(...)`.
2. Save the returned `run_id`.
3. Poll `get_run_status(run_id)` and `get_run_events(run_id)`.
4. Fetch the final result with `get_run_result(run_id)`.

Runs are indexed in `runs/codexbridge.sqlite3` using SQLite WAL mode and write artifacts under `runs/<run_id>/`. Plain synchronous tools remain available for short tasks.
