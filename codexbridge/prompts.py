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

Return a structured implementation plan with:
- summary
- files likely to inspect
- files likely to edit
- risks
- tests
- approval question
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
- Implement only the approved_plan.
- Touch only allowed_files unless impossible.
- If another file must change, stop and explain why.
- Do not commit.
- Do not push.
- Do not touch unrelated dirty files.
- Run only provided tests unless the approved plan clearly requires normal project verification.
- Report changed files, tests run, exit code, final summary, and remaining risks.
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
