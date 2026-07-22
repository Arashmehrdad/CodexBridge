from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from soma.config import CodexRouterConfig
from soma.memory.repository import ProjectMemoryRepository
from soma.run_store import utc_now

from .models import (
    CodexConstraint,
    CodexContextFile,
    CodexContextSnippet,
    CodexEscalationPacket,
    CodexEscalationRequest,
)
from .redaction import detect_sensitive_text, redact_for_codex


class CodexContextBuilder:
    def __init__(
        self,
        *,
        config: CodexRouterConfig | None = None,
        memory_repository: ProjectMemoryRepository | None = None,
        local_model=None,
    ):
        self.config = config or CodexRouterConfig()
        self.memory_repository = memory_repository
        self.local_model = local_model

    def build_packet(
        self, request: CodexEscalationRequest, policy_decision: dict
    ) -> tuple[CodexEscalationPacket, list[str], list[str]]:
        snippets: list[CodexContextSnippet] = []
        context_files: list[CodexContextFile] = []
        sensitivity: list[str] = []
        skipped: list[str] = []
        context_bytes = 0

        for path in request.relevant_files:
            resolved = Path(path)
            allowed, reason = self._path_allowed(resolved, request.repo_path)
            if not allowed:
                context_files.append(
                    CodexContextFile(
                        path=resolved, included=False, skipped_reason=reason
                    )
                )
                skipped.append(f"{resolved}: {reason}")
                continue
            data = resolved.read_bytes()
            text = data.decode("utf-8", errors="replace")
            flags = detect_sensitive_text(text)
            if flags and self.config.codex_router_block_sensitive:
                sensitivity.extend(flags)
                context_files.append(
                    CodexContextFile(
                        path=resolved,
                        included=False,
                        skipped_reason="sensitive_content",
                        bytes_read=len(data),
                    )
                )
                continue
            if len(data) > self.config.codex_router_max_file_bytes:
                context_files.append(
                    CodexContextFile(
                        path=resolved,
                        included=False,
                        skipped_reason="file_too_large",
                        bytes_read=len(data),
                    )
                )
                skipped.append(f"{resolved}: file_too_large")
                continue
            if flags and self.config.codex_router_redact_sensitive:
                text = redact_for_codex(text)
                sensitivity.extend(flags)
            if (
                context_bytes + len(text.encode("utf-8"))
                <= self.config.codex_router_max_context_bytes
            ):
                snippets.append(CodexContextSnippet(source=str(resolved), text=text))
                context_bytes += len(text.encode("utf-8"))
                context_files.append(
                    CodexContextFile(path=resolved, included=True, bytes_read=len(data))
                )
            else:
                context_files.append(
                    CodexContextFile(
                        path=resolved,
                        included=False,
                        skipped_reason="context_budget_exceeded",
                        bytes_read=len(data),
                    )
                )

        if request.current_error:
            error_text = request.current_error
            if len(error_text.encode("utf-8")) > self.config.codex_router_max_log_bytes:
                error_text = (
                    error_text.encode("utf-8")[
                        : self.config.codex_router_max_log_bytes
                    ].decode("utf-8", errors="ignore")
                    + "\n[truncated]"
                )
            flags = detect_sensitive_text(error_text)
            if flags and self.config.codex_router_redact_sensitive:
                error_text = redact_for_codex(error_text)
            sensitivity.extend(flags)
            snippets.append(
                CodexContextSnippet(source="current_error", text=error_text)
            )

        memory_context = self._memory_context(request)
        local_summary = self._local_model_summary(request)
        packet = CodexEscalationPacket(
            escalation_id=request.escalation_id,
            objective=request.objective,
            task_type=request.task_type,
            repo_name=request.repo_name,
            repo_path=request.repo_path,
            relevant_files=context_files,
            relevant_snippets=snippets,
            current_error=redact_for_codex(request.current_error)
            if self.config.codex_router_redact_sensitive
            else request.current_error,
            failure_summary=redact_for_codex(request.failure_summary)
            if self.config.codex_router_redact_sensitive
            else request.failure_summary,
            tests_already_run=request.tests_already_run,
            validation_commands=request.validation_commands
            or self.config.codex_router_default_validation_commands,
            constraints=[CodexConstraint(text=item) for item in request.constraints],
            allowed_files=request.allowed_files,
            forbidden_files=request.forbidden_files,
            expected_output=request.expected_output,
            policy_decision=policy_decision,
            approval_request_id=policy_decision.get("approval_request_id"),
            memory_context=memory_context,
            local_model_summary=local_summary,
            source_artifacts=[],
            created_at=utc_now(),
            audit_event_id=f"codex_packet_{uuid4().hex}",
        )
        return packet, sorted(set(sensitivity)), skipped

    def _path_allowed(self, path: Path, repo_path: Path | None) -> tuple[bool, str]:
        if not path.exists() or not path.is_file():
            return False, "missing_or_not_file"
        if repo_path is None:
            return True, ""
        try:
            path.resolve().relative_to(repo_path.resolve())
            return True, ""
        except ValueError:
            return False, "outside_repo"

    def _memory_context(self, request: CodexEscalationRequest) -> list[dict]:
        if self.memory_repository is None:
            return []
        try:
            result = self.memory_repository.search(
                request.objective,
                repo_name=request.repo_name,
                limit=5,
            )
            if not result.records:
                for term in request.objective.split():
                    if len(term) < 4:
                        continue
                    result = self.memory_repository.search(
                        term,
                        repo_name=request.repo_name,
                        limit=5,
                    )
                    if result.records:
                        break
            return [
                {
                    "memory_id": record.memory_id,
                    "title": record.title,
                    "summary": record.summary,
                    "tags": record.tags,
                }
                for record in result.records
                if not record.sensitivity_flags
            ]
        except Exception:
            return []

    def _local_model_summary(self, request: CodexEscalationRequest) -> str:
        if (
            not self.config.codex_router_use_local_model_summary
            or self.local_model is None
        ):
            return ""
        try:
            result = self.local_model.compress_context(request.objective)
            return result.content if getattr(result, "content", "") else ""
        except Exception:
            return ""
