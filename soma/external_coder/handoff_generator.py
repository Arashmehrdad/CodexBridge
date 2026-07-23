"""Provider-neutral external-coder handoff generation.

Generates a bounded handoff artifact that a human operator can manually
supply to Claude Code, Codex, Gemini CLI, or any other coding agent.
Nothing in this package invokes an external model or executable.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from soma.config import AppConfig, ExternalCoderConfig
from soma.policy import PolicyEngine, PolicyEvaluationRequest
from soma.policy.models import PolicyDecisionValue

from .context_builder import ExternalCoderContextBuilder
from .models import (
    ExternalCoderHandoff,
    ExternalCoderHandoffRequest,
    ExternalCoderHandoffResult,
    ExternalCoderHandoffStatus,
    RepositoryStateSnapshot,
)
from .handoff_writer import write_handoff_artifacts
from .redaction import detect_sensitive_text


LOCAL_ONLY_MARKERS = (
    "inspect repo",
    "list files",
    "summarize",
    "summarise",
    "run tests",
    "pytest",
    "pip check",
    "search memory",
    "job status",
    "generate report",
    "pending approvals",
)
CODER_MARKERS = (
    "edit",
    "fix",
    "refactor",
    "create module",
    "failing test",
    "update multiple",
    "architecture-sensitive",
)
HUMAN_MARKERS = (
    "secret",
    "credential",
    "api key",
    "token",
    "password",
    "production deploy",
    "public release",
    "push to main",
    "push to master",
    "rm -rf",
    "external permission",
)


def capture_repository_state(
    repo_path: Path | None, *, max_status_bytes: int = 8000
) -> RepositoryStateSnapshot:
    """Capture branch, HEAD, and bounded worktree status for the handoff.

    Read-only git inspection through soma.git_tools; failures are recorded
    instead of raised so handoff generation never depends on git health.
    """
    if repo_path is None:
        return RepositoryStateSnapshot(captured=False, error="no_repo_path")
    from soma import git_tools

    try:
        branch = git_tools.git_branch(repo_path)
        head = git_tools.git_head(repo_path)
        status = git_tools.git_status(repo_path)
    except Exception as exc:
        return RepositoryStateSnapshot(captured=False, error=str(exc)[:500])
    # `git status --branch` always emits a `## <branch>` header line;
    # only non-header entries mean the worktree is dirty.
    clean = not any(
        line.strip() and not line.startswith("##") for line in status.splitlines()
    )
    encoded = status.encode("utf-8")
    if len(encoded) > max_status_bytes:
        status = (
            encoded[:max_status_bytes].decode("utf-8", errors="ignore")
            + "\n[truncated]"
        )
    return RepositoryStateSnapshot(
        captured=True,
        branch=branch,
        head=head,
        worktree_status=status,
        worktree_clean=clean,
    )


class ExternalCoderHandoffGenerator:
    """Route a coding-shaped objective into a manual handoff artifact.

    Replaces the retired Codex escalation router. The only outcomes are
    informational states and a written handoff packet; there is no
    invocation path of any kind.
    """

    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        handoff_config: ExternalCoderConfig | None = None,
        policy_engine: PolicyEngine | None = None,
        context_builder: ExternalCoderContextBuilder | None = None,
        handoff_dir: Path | None = None,
    ):
        self.config = config
        self.handoff_config = handoff_config or (
            config.external_coder if config else ExternalCoderConfig()
        )
        self.policy_engine = policy_engine or PolicyEngine()
        self.context_builder = context_builder or ExternalCoderContextBuilder(
            config=self.handoff_config
        )
        self.handoff_dir = handoff_dir or (
            config.resolve_external_coder_handoff_dir()
            if config
            else Path.cwd() / "runs" / "external_coder_handoffs"
        )

    def generate_handoff(
        self, request: ExternalCoderHandoffRequest
    ) -> ExternalCoderHandoffResult:
        audit_id = f"external_coder_{uuid4().hex}"
        route = self._route_status(request.objective)
        if route in {
            ExternalCoderHandoffStatus.LOCAL_ONLY,
            ExternalCoderHandoffStatus.EXTERNAL_CODER_NOT_NEEDED,
        }:
            return ExternalCoderHandoffResult(
                handoff_id=request.handoff_id,
                status=route,
                reasons=["task_is_local_only"],
                audit_event_id=audit_id,
            )
        if route in {
            ExternalCoderHandoffStatus.HUMAN_REQUIRED,
            ExternalCoderHandoffStatus.BLOCKED,
        }:
            return ExternalCoderHandoffResult(
                handoff_id=request.handoff_id,
                status=route,
                reasons=["human_only_or_blocked"],
                sensitivity_flags=detect_sensitive_text(request.objective),
                audit_event_id=audit_id,
            )

        autonomy_profile = (
            "balanced"
            if self.handoff_config.external_coder_require_policy_approval
            else "permissive"
        )
        policy = self.policy_engine.evaluate(
            PolicyEvaluationRequest(
                action=request.objective,
                action_type=request.task_type or "external_coder_handoff",
                repo_name=request.repo_name,
                repo_path=request.repo_path,
                autonomy_profile=autonomy_profile,
                permission_tier="write_apply_under_delegated_approval",
            )
        )
        handoff, sensitivity, skipped = self.context_builder.build_handoff(
            request, policy.to_dict()
        )
        handoff.repository_state = capture_repository_state(
            request.repo_path,
            max_status_bytes=self.handoff_config.external_coder_max_worktree_status_bytes,
        )
        prompt = build_handoff_prompt(handoff)
        artifacts = write_handoff_artifacts(self.handoff_dir, handoff, prompt)

        if sensitivity and self.handoff_config.external_coder_block_sensitive:
            return ExternalCoderHandoffResult(
                handoff_id=request.handoff_id,
                status=ExternalCoderHandoffStatus.BLOCKED,
                handoff=handoff,
                artifacts=artifacts,
                policy_decision=policy.to_dict(),
                reasons=["sensitive_context_blocked", *skipped],
                sensitivity_flags=sensitivity,
                audit_event_id=audit_id,
            )
        if policy.blocked:
            return ExternalCoderHandoffResult(
                handoff_id=request.handoff_id,
                status=ExternalCoderHandoffStatus.BLOCKED,
                handoff=handoff,
                artifacts=artifacts,
                policy_decision=policy.to_dict(),
                reasons=policy.reasons,
                sensitivity_flags=policy.sensitivity_flags,
                audit_event_id=audit_id,
            )
        if policy.human_required:
            return ExternalCoderHandoffResult(
                handoff_id=request.handoff_id,
                status=ExternalCoderHandoffStatus.HUMAN_REQUIRED,
                handoff=handoff,
                artifacts=artifacts,
                policy_decision=policy.to_dict(),
                approval_request_id=policy.approval_request_id,
                reasons=policy.reasons,
                audit_event_id=audit_id,
            )
        if (
            policy.decision
            in {
                PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL,
                PolicyDecisionValue.ALLOWED_WITH_CHATGPT_DELEGATED_APPROVAL,
            }
            and self.handoff_config.external_coder_require_policy_approval
        ):
            return ExternalCoderHandoffResult(
                handoff_id=request.handoff_id,
                status=ExternalCoderHandoffStatus.APPROVAL_REQUIRED,
                handoff=handoff,
                artifacts=artifacts,
                policy_decision=policy.to_dict(),
                approval_request_id=policy.approval_request_id,
                reasons=["policy_approval_required"],
                audit_event_id=audit_id,
            )

        return ExternalCoderHandoffResult(
            handoff_id=request.handoff_id,
            status=ExternalCoderHandoffStatus.HANDOFF_READY,
            handoff=handoff,
            artifacts=artifacts,
            policy_decision=policy.to_dict(),
            approval_request_id=policy.approval_request_id,
            reasons=["handoff_ready_for_manual_use"],
            audit_event_id=audit_id,
        )

    def _route_status(self, objective: str) -> ExternalCoderHandoffStatus:
        text = objective.lower()
        if any(marker in text for marker in HUMAN_MARKERS):
            return ExternalCoderHandoffStatus.HUMAN_REQUIRED
        if any(marker in text for marker in LOCAL_ONLY_MARKERS):
            return ExternalCoderHandoffStatus.LOCAL_ONLY
        if any(marker in text for marker in CODER_MARKERS):
            return ExternalCoderHandoffStatus.NEEDS_EXTERNAL_CODER
        return ExternalCoderHandoffStatus.EXTERNAL_CODER_NOT_NEEDED


def build_handoff_prompt(handoff: ExternalCoderHandoff) -> str:
    """Render the handoff as a provider-neutral prompt for manual use."""
    snippets = "\n\n".join(
        f"## {item.source}\n{item.text}" for item in handoff.relevant_snippets
    )
    state = handoff.repository_state
    repository_lines = (
        [
            f"Branch: {state.branch}",
            f"HEAD: {state.head}",
            "Worktree: clean"
            if state.worktree_clean
            else f"Worktree status:\n{state.worktree_status}",
        ]
        if state.captured
        else [f"Repository state unavailable: {state.error or 'not captured'}"]
    )
    return "\n".join(
        [
            "Soma external-coder handoff.",
            "",
            "You are an external coding agent (for example Claude Code, Codex,",
            "Gemini CLI, or another tool the operator chose). This handoff was",
            "generated by Soma and supplied to you manually; Soma has not",
            "executed, launched, or supervised any coding agent.",
            "",
            "# Objective",
            handoff.objective,
            "",
            "# Repository state",
            f"Repo name: {handoff.repo_name or ''}",
            f"Repo path: {handoff.repo_path or ''}",
            *repository_lines,
            "",
            "# Relevant files",
            ", ".join(str(item.path) for item in handoff.relevant_files) or "None",
            "",
            "# Evidence and failures",
            f"Current error: {handoff.current_error or 'None'}",
            f"Failure summary: {handoff.failure_summary or 'None'}",
            f"Tests already run: {', '.join(handoff.tests_already_run) or 'None'}",
            "",
            "# Approved scope",
            f"Allowed files: {', '.join(handoff.allowed_files) or 'None specified'}",
            f"Forbidden files: {', '.join(handoff.forbidden_files) or 'None specified'}",
            "",
            "# Constraints and repository safety rules",
            "; ".join(item.text for item in handoff.constraints) or "None",
            "Safety boundaries: avoid unrelated changes, do not touch secrets,",
            "do not deploy, do not push, stay within the approved scope.",
            "",
            "# Tests and validation commands",
            ", ".join(handoff.validation_commands) or "None",
            "",
            "# Expected completion report",
            handoff.expected_report or "Changed files and validation results.",
            "",
            snippets,
        ]
    ).strip()
