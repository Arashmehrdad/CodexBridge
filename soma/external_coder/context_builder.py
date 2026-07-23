from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from soma.config import ExternalCoderConfig
from soma.memory.repository import ProjectMemoryRepository
from soma.run_store import utc_now

from .models import (
    ExternalCoderConstraint,
    ExternalCoderContextFile,
    ExternalCoderContextSnippet,
    ExternalCoderHandoff,
    ExternalCoderHandoffRequest,
)
from .redaction import detect_sensitive_text, redact_for_handoff


class ExternalCoderContextBuilder:
    def __init__(
        self,
        *,
        config: ExternalCoderConfig | None = None,
        memory_repository: ProjectMemoryRepository | None = None,
        local_model=None,
    ):
        self.config = config or ExternalCoderConfig()
        self.memory_repository = memory_repository
        self.local_model = local_model

    def build_handoff(
        self, request: ExternalCoderHandoffRequest, policy_decision: dict
    ) -> tuple[ExternalCoderHandoff, list[str], list[str]]:
        snippets: list[ExternalCoderContextSnippet] = []
        context_files: list[ExternalCoderContextFile] = []
        sensitivity: list[str] = []
        skipped: list[str] = []
        context_bytes = 0

        for path in request.relevant_files:
            resolved = Path(path)
            allowed, reason = self._path_allowed(resolved, request.repo_path)
            if not allowed:
                context_files.append(
                    ExternalCoderContextFile(
                        path=resolved, included=False, skipped_reason=reason
                    )
                )
                skipped.append(f"{resolved}: {reason}")
                continue
            data = resolved.read_bytes()
            text = data.decode("utf-8", errors="replace")
            flags = detect_sensitive_text(text)
            if flags and self.config.external_coder_block_sensitive:
                sensitivity.extend(flags)
                context_files.append(
                    ExternalCoderContextFile(
                        path=resolved,
                        included=False,
                        skipped_reason="sensitive_content",
                        bytes_read=len(data),
                    )
                )
                continue
            if len(data) > self.config.external_coder_max_file_bytes:
                context_files.append(
                    ExternalCoderContextFile(
                        path=resolved,
                        included=False,
                        skipped_reason="file_too_large",
                        bytes_read=len(data),
                    )
                )
                skipped.append(f"{resolved}: file_too_large")
                continue
            if flags and self.config.external_coder_redact_sensitive:
                text = redact_for_handoff(text)
                sensitivity.extend(flags)
            if (
                context_bytes + len(text.encode("utf-8"))
                <= self.config.external_coder_max_context_bytes
            ):
                snippets.append(
                    ExternalCoderContextSnippet(source=str(resolved), text=text)
                )
                context_bytes += len(text.encode("utf-8"))
                context_files.append(
                    ExternalCoderContextFile(
                        path=resolved, included=True, bytes_read=len(data)
                    )
                )
            else:
                context_files.append(
                    ExternalCoderContextFile(
                        path=resolved,
                        included=False,
                        skipped_reason="context_budget_exceeded",
                        bytes_read=len(data),
                    )
                )

        if request.current_error:
            error_text = request.current_error
            if (
                len(error_text.encode("utf-8"))
                > self.config.external_coder_max_log_bytes
            ):
                error_text = (
                    error_text.encode("utf-8")[
                        : self.config.external_coder_max_log_bytes
                    ].decode("utf-8", errors="ignore")
                    + "\n[truncated]"
                )
            flags = detect_sensitive_text(error_text)
            if flags and self.config.external_coder_redact_sensitive:
                error_text = redact_for_handoff(error_text)
            sensitivity.extend(flags)
            snippets.append(
                ExternalCoderContextSnippet(source="current_error", text=error_text)
            )

        memory_context = self._memory_context(request)
        local_summary = self._local_model_summary(request)
        handoff = ExternalCoderHandoff(
            handoff_id=request.handoff_id,
            objective=request.objective,
            task_type=request.task_type,
            repo_name=request.repo_name,
            repo_path=request.repo_path,
            relevant_files=context_files,
            relevant_snippets=snippets,
            current_error=redact_for_handoff(request.current_error)
            if self.config.external_coder_redact_sensitive
            else request.current_error,
            failure_summary=redact_for_handoff(request.failure_summary)
            if self.config.external_coder_redact_sensitive
            else request.failure_summary,
            tests_already_run=request.tests_already_run,
            validation_commands=request.validation_commands
            or self.config.external_coder_default_validation_commands,
            constraints=[
                ExternalCoderConstraint(text=item) for item in request.constraints
            ],
            allowed_files=request.allowed_files,
            forbidden_files=request.forbidden_files,
            expected_report=request.expected_report,
            policy_decision=policy_decision,
            approval_request_id=policy_decision.get("approval_request_id"),
            memory_context=memory_context,
            local_model_summary=local_summary,
            source_artifacts=[],
            created_at=utc_now(),
            audit_event_id=f"external_coder_handoff_{uuid4().hex}",
        )
        return handoff, sorted(set(sensitivity)), skipped

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

    def _memory_context(self, request: ExternalCoderHandoffRequest) -> list[dict]:
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

    def _local_model_summary(self, request: ExternalCoderHandoffRequest) -> str:
        if (
            not self.config.external_coder_use_local_model_summary
            or self.local_model is None
        ):
            return ""
        try:
            result = self.local_model.compress_context(request.objective)
            return result.content if getattr(result, "content", "") else ""
        except Exception:
            return ""
