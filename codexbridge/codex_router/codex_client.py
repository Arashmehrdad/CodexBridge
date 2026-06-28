from __future__ import annotations

from pathlib import Path
from typing import Protocol

from codexbridge.config import AppConfig
from codexbridge.runner import CodexRunner

from .models import CodexEscalationStatus, CodexInvocationRequest, CodexInvocationResult


class CodexClient(Protocol):
    def invoke(self, request: CodexInvocationRequest) -> CodexInvocationResult: ...


class NoopCodexClient:
    def invoke(self, request: CodexInvocationRequest) -> CodexInvocationResult:
        return CodexInvocationResult(
            status=CodexEscalationStatus.UNAVAILABLE,
            invoked=False,
            summary="Codex invocation is disabled; packet is ready for review.",
        )


class ExistingCodexRunnerClient:
    def __init__(self, config: AppConfig):
        self.config = config

    def invoke(self, request: CodexInvocationRequest) -> CodexInvocationResult:
        packet = request.packet
        if packet.repo_path is None or packet.repo_name is None:
            return CodexInvocationResult(
                status=CodexEscalationStatus.FAILED,
                invoked=False,
                error="repo_name and repo_path are required",
            )
        result = CodexRunner(self.config).implement_task(
            packet.repo_name,
            Path(packet.repo_path),
            request.prompt,
            packet.allowed_files,
            packet.validation_commands,
        )
        return CodexInvocationResult(
            status=CodexEscalationStatus.COMPLETED
            if result.get("exit_code") == 0
            else CodexEscalationStatus.FAILED,
            invoked=True,
            summary=result.get("summary", ""),
            metadata=result,
        )
