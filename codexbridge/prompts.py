from __future__ import annotations

from typing import Iterable


def build_plan_prompt(repo_name: str, task: str, constraints: str | None = None) -> str:
    constraints_text = constraints or "No additional constraints provided."
    return f"""You are Codex running through CodexBridge in PLAN-ONLY mode.

Repository name: {repo_name}

Task:
{task}

Constraints:
{constraints_text}

Hard rules:
- Inspect only.
- Do not create files.
- Do not edit files.
- Do not delete files.
- Do not install packages.
- Do not run formatters that write files.
- Do not run migrations or code generation that writes files.
- Do not commit.
- Do not push.
- Do not touch unrelated dirty files.
- The task above is complete and ready for planning. Do not ask the user to send the actual task.
- If planning is impossible, state the blocker explicitly instead of returning a placeholder response.

Return a structured implementation plan with:
- summary
- files likely to inspect
- files likely to edit
- risks
- tests
- approval question
- final line: PLAN_STATUS: ready or PLAN_STATUS: blocked
"""


def build_implementation_prompt(
    repo_name: str,
    approved_plan: str,
    allowed_files: Iterable[str],
    tests: Iterable[str],
) -> str:
    allowed = "\n".join(f"- {path}" for path in allowed_files) or "- No files approved"
    tests_text = (
        "\n".join(f"- {command}" for command in tests) or "- No explicit tests provided"
    )
    return f"""You are Codex running through CodexBridge in IMPLEMENTATION mode.

Repository name: {repo_name}

Approved plan:
{approved_plan}

Allowed files:
{allowed}

Tests to run:
{tests_text}

Hard rules:
- Implement only the approved_plan. Do not broaden, reinterpret, or replace its scope.
- The allowed_files list is an exclusive write allowlist.
- Do not create, edit, move, or delete any file outside allowed_files, including temporary or diagnostic files at the repository root.
- If any required write is outside allowed_files or any allowed path is not writable, stop immediately and report a blocker. Do not create a fallback document or alternative implementation.
- Do not commit.
- Do not push.
- Do not touch unrelated dirty files.
- Run only provided tests unless the approved plan clearly requires normal project verification.
- Report changed files, tests run, exit code, final summary, and remaining risks.
- End with exactly these machine-readable lines:
  FINAL_STATUS: completed|blocked|failed
  PLAN_CONFORMANCE: yes|no
  BLOCKERS: none or a concise blocker description
"""


def build_result_summary_prompt(raw_result: str) -> str:
    return f"""Summarize this CodexBridge run result without adding claims.

Return:
- summary
- changed files
- tests run
- remaining risks

Raw result:
{raw_result}
"""
