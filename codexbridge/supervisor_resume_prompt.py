from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import redact_and_truncate, truncate_text


ARTIFACT_NAMES = ["prompt.txt", "result.json", "events.jsonl", "stdout.txt", "stderr.txt"]
PROMPT_LIMIT = 20000
PULSESENDER_DELIVERY_NOTE = (
    "If this prompt arrived automatically, it was likely delivered by the local PulseSender watcher. "
    "Continue from the supervisor context. Do not ask the user to manually relay this prompt again."
)


def supervisor_prompt_path(runs_dir: Path, supervisor_id: str) -> Path:
    return runs_dir / "supervisors" / supervisor_id / "resume_prompt.txt"


def write_resume_prompt(runs_dir: Path, supervisor: dict[str, Any], child_run_base_dir: Path | None = None) -> Path:
    path = supervisor_prompt_path(runs_dir, supervisor["supervisor_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    prompt = build_resume_prompt(supervisor, child_run_base_dir or runs_dir)
    path.write_text(prompt, encoding="utf-8")
    return path


def build_resume_prompt(supervisor: dict[str, Any], child_run_base_dir: Path) -> str:
    safe = redact_and_truncate(supervisor, limit=4000)
    metadata = safe.get("metadata") or {}
    child_links = list(safe.get("run_links") or [])
    lines: list[str] = [
        "You are Codex resuming a CodexBridge supervisor context.",
        "",
        PULSESENDER_DELIVERY_NOTE,
        "",
        f"repo_name: {safe.get('repo_name', '')}",
        f"supervisor_id: {safe.get('supervisor_id', '')}",
        f"status: {safe.get('status', '')}",
        f"objective: {_one_line(safe.get('objective', ''))}",
        f"summary: {_one_line(safe.get('summary', ''))}",
        f"error: {_one_line(safe.get('error', ''))}",
        "",
        "Current Context:",
    ]
    for key in ("plan", "approval", "blocked", "hard_stop", "plan_result", "implementation_result", "cancelled_child"):
        if metadata.get(key) not in (None, "", {}, []):
            lines.append(f"- {key}: {_json_preview(metadata[key])}")

    lines.extend(["", "Related Child Runs:"])
    if child_links:
        for link in child_links:
            run_id = str(link.get("run_id", ""))
            role = str(link.get("link_type", "child"))
            lines.append(f"- {role}: {run_id}")
            for artifact in ARTIFACT_NAMES:
                lines.append(f"  - {artifact}: {child_run_base_dir / run_id / artifact}")
    else:
        lines.append("- none")

    lines.extend(["", "Next Action Guidance:", _next_action_guidance(safe), "", "Hard Rules:"])
    lines.extend(
        [
            "- no destructive operations",
            "- no secrets",
            "- no force push",
            "- no outside-repo edits",
            "- no public tool instructions yet",
        ]
    )
    return truncate_text("\n".join(lines) + "\n", PROMPT_LIMIT)


def _one_line(value: Any) -> str:
    return str(redact_and_truncate(value, limit=1000)).replace("\r", " ").replace("\n", " ")[:1000]


def _json_preview(value: Any) -> str:
    return truncate_text(json.dumps(redact_and_truncate(value, limit=2000), sort_keys=True), 2000)


def _next_action_guidance(supervisor: dict[str, Any]) -> str:
    status = supervisor.get("status")
    metadata = supervisor.get("metadata") or {}
    if status == "needs_input" and metadata.get("blocked"):
        return "Resolve the blocking condition before attempting implementation."
    if status == "needs_input" and metadata.get("hard_stop"):
        return "Review the hard-stop reason and obtain the required approval or safer revised plan."
    if status == "needs_input":
        return "Review the plan result and either approve implementation or request a revised plan."
    if status == "failed":
        return "Inspect the linked child result and event artifacts, then propose a safe recovery plan."
    if status == "cancelled":
        return "Confirm cancellation was intended before starting any new supervisor or child run."
    if status == "completed":
        return "Review the final result and repository status before any commit or push approval."
    return "Inspect supervisor metadata and linked artifacts before taking further action."
