from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from codexbridge.config import AppConfig, CodexRouterConfig
from codexbridge.policy import PolicyEngine, PolicyEvaluationRequest
from codexbridge.policy.models import PolicyDecisionValue

from .codex_client import CodexClient, ExistingCodexRunnerClient, NoopCodexClient
from .context_builder import CodexContextBuilder
from .models import (
    CodexEscalationRequest,
    CodexEscalationStatus,
    CodexInvocationRequest,
    CodexRouterResult,
)
from .packet_writer import write_invocation_artifacts, write_packet_artifacts
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
CODEX_MARKERS = (
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


class CodexEscalationRouter:
    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        router_config: CodexRouterConfig | None = None,
        policy_engine: PolicyEngine | None = None,
        context_builder: CodexContextBuilder | None = None,
        codex_client: CodexClient | None = None,
        packet_dir: Path | None = None,
    ):
        self.config = config
        self.router_config = router_config or (
            config.codex_router if config else CodexRouterConfig()
        )
        self.policy_engine = policy_engine or PolicyEngine()
        self.context_builder = context_builder or CodexContextBuilder(
            config=self.router_config
        )
        self.codex_client = codex_client or (
            ExistingCodexRunnerClient(config)
            if config and self.router_config.codex_router_invoke_enabled
            else NoopCodexClient()
        )
        self.packet_dir = packet_dir or (
            config.resolve_codex_router_packet_dir()
            if config
            else Path.cwd() / "runs" / "codex_escalations"
        )

    def route_escalation(self, request: CodexEscalationRequest) -> CodexRouterResult:
        audit_id = f"codex_router_{uuid4().hex}"
        route = self._route_status(request.objective)
        if route in {
            CodexEscalationStatus.LOCAL_ONLY,
            CodexEscalationStatus.CODEX_NOT_NEEDED,
        }:
            return CodexRouterResult(
                escalation_id=request.escalation_id,
                status=route,
                reasons=["task_is_local_only"],
                audit_event_id=audit_id,
            )
        if route in {
            CodexEscalationStatus.HUMAN_REQUIRED,
            CodexEscalationStatus.BLOCKED,
        }:
            return CodexRouterResult(
                escalation_id=request.escalation_id,
                status=route,
                reasons=["human_only_or_blocked"],
                sensitivity_flags=detect_sensitive_text(request.objective),
                audit_event_id=audit_id,
            )

        autonomy_profile = (
            "chatgpt_delegated"
            if self.router_config.codex_router_require_policy_approval
            else "permissive"
        )
        policy = self.policy_engine.evaluate(
            PolicyEvaluationRequest(
                action=request.objective,
                action_type=request.task_type or "codex_escalation",
                repo_name=request.repo_name,
                repo_path=request.repo_path,
                autonomy_profile=autonomy_profile,
                permission_tier="write_apply_under_delegated_approval",
            )
        )
        packet, sensitivity, skipped = self.context_builder.build_packet(
            request, policy.to_dict()
        )
        prompt = build_codex_prompt(packet)
        artifacts = write_packet_artifacts(self.packet_dir, packet, prompt)

        if sensitivity and self.router_config.codex_router_block_sensitive:
            return CodexRouterResult(
                escalation_id=request.escalation_id,
                status=CodexEscalationStatus.BLOCKED,
                packet=packet,
                artifacts=artifacts,
                policy_decision=policy.to_dict(),
                reasons=["sensitive_context_blocked", *skipped],
                sensitivity_flags=sensitivity,
                audit_event_id=audit_id,
            )
        if policy.blocked:
            return CodexRouterResult(
                escalation_id=request.escalation_id,
                status=CodexEscalationStatus.BLOCKED,
                packet=packet,
                artifacts=artifacts,
                policy_decision=policy.to_dict(),
                reasons=policy.reasons,
                sensitivity_flags=policy.sensitivity_flags,
                audit_event_id=audit_id,
            )
        if policy.human_required:
            return CodexRouterResult(
                escalation_id=request.escalation_id,
                status=CodexEscalationStatus.HUMAN_REQUIRED,
                packet=packet,
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
            and self.router_config.codex_router_require_policy_approval
        ):
            return CodexRouterResult(
                escalation_id=request.escalation_id,
                status=CodexEscalationStatus.APPROVAL_REQUIRED,
                packet=packet,
                artifacts=artifacts,
                policy_decision=policy.to_dict(),
                approval_request_id=policy.approval_request_id,
                reasons=["policy_approval_required"],
                audit_event_id=audit_id,
            )

        if request.invoke_codex and self.router_config.codex_router_invoke_enabled:
            invocation = CodexInvocationRequest(packet=packet, prompt=prompt)
            result = self.codex_client.invoke(invocation)
            artifacts = write_invocation_artifacts(
                artifacts, invocation.model_dump(mode="json"), result
            )
            return CodexRouterResult(
                escalation_id=request.escalation_id,
                status=CodexEscalationStatus.INVOKED
                if result.invoked
                else result.status,
                packet=packet,
                artifacts=artifacts,
                invocation_result=result,
                policy_decision=policy.to_dict(),
                audit_event_id=audit_id,
            )

        return CodexRouterResult(
            escalation_id=request.escalation_id,
            status=CodexEscalationStatus.PACKET_READY,
            packet=packet,
            artifacts=artifacts,
            policy_decision=policy.to_dict(),
            approval_request_id=policy.approval_request_id,
            reasons=["packet_ready_codex_not_invoked"],
            audit_event_id=audit_id,
        )

    def _route_status(self, objective: str) -> CodexEscalationStatus:
        text = objective.lower()
        if any(marker in text for marker in HUMAN_MARKERS):
            return CodexEscalationStatus.HUMAN_REQUIRED
        if any(marker in text for marker in LOCAL_ONLY_MARKERS):
            return CodexEscalationStatus.LOCAL_ONLY
        if any(marker in text for marker in CODEX_MARKERS):
            return CodexEscalationStatus.CODEX_REQUIRED
        return CodexEscalationStatus.CODEX_NOT_NEEDED


def build_codex_prompt(packet) -> str:
    snippets = "\n\n".join(
        f"## {item.source}\n{item.text}" for item in packet.relevant_snippets
    )
    return "\n".join(
        [
            "CodexBridge escalation packet.",
            "",
            f"Objective: {packet.objective}",
            f"Repo name: {packet.repo_name or ''}",
            f"Repo path: {packet.repo_path or ''}",
            f"Task type: {packet.task_type}",
            f"Relevant files: {', '.join(str(item.path) for item in packet.relevant_files) or 'None'}",
            f"Current error: {packet.current_error}",
            f"Failure summary: {packet.failure_summary}",
            f"Tests already run: {', '.join(packet.tests_already_run) or 'None'}",
            f"Validation commands: {', '.join(packet.validation_commands) or 'None'}",
            f"Constraints: {'; '.join(item.text for item in packet.constraints) or 'None'}",
            f"Allowed files: {', '.join(packet.allowed_files) or 'None specified'}",
            f"Forbidden files: {', '.join(packet.forbidden_files) or 'None specified'}",
            f"Expected output: {packet.expected_output}",
            "",
            "Safety boundaries: avoid unrelated changes, do not touch secrets, do not deploy, do not push.",
            "Report changed files and validation results.",
            "",
            snippets,
        ]
    ).strip()
