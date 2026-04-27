from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath

from .safety import is_secret_like_file


@dataclass(frozen=True)
class PolicyDecision:
    accepted: bool
    tier: int
    risk_level: str
    requires_human: bool
    reason: str = ""
    estimated_duration_minutes: int = 10
    recommended_check_after_minutes: int = 2

    def to_start_response(self, run_id: str | None = None, status: str = "queued") -> dict:
        return {
            "run_id": run_id,
            "accepted": self.accepted,
            "status": status,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "recommended_check_after_minutes": self.recommended_check_after_minutes,
            "risk_level": self.risk_level,
            "requires_human": self.requires_human,
            "reason": self.reason,
        }


def _looks_docs_only(paths: list[str]) -> bool:
    docs_suffixes = {".md", ".rst", ".txt"}
    docs_prefixes = ("docs/", "documentation/")
    if not paths:
        return False
    for path in paths:
        normalized = path.replace("\\", "/").lower()
        suffix = PureWindowsPath(normalized).suffix
        if suffix not in docs_suffixes and not normalized.startswith(docs_prefixes):
            return False
    return True


def decide_plan_task(task: str, constraints: str | None = None) -> PolicyDecision:
    text = f"{task}\n{constraints or ''}".lower()
    if any(word in text for word in ("credential", "login", "secret", "token", "force push", "delete volume")):
        return PolicyDecision(False, 3, "high", True, "Plan request appears to require human-only action")
    return PolicyDecision(True, 1, "low", False, "Plan-only jobs are auto-approved")


def decide_implementation_task(approved_plan: str, allowed_files: list[str], tests: list[str]) -> PolicyDecision:
    text = f"{approved_plan}\n{' '.join(tests)}".lower()
    if any(word in text for word in ("force push", "credential", "browser login", "secret", "delete volume")):
        return PolicyDecision(False, 3, "high", True, "Request appears to require human-only action")
    secret_files = [path for path in allowed_files if is_secret_like_file(path)]
    if secret_files:
        return PolicyDecision(False, 3, "high", True, f"Secret-like files are not allowed: {secret_files}")
    if _looks_docs_only(allowed_files):
        return PolicyDecision(True, 1, "low", False, "Docs-only allowed-file implementation is auto-approved")
    return PolicyDecision(True, 2, "medium", False, "Normal implementation requires ChatGPT approval before start")
