"""Production read-only Codex App Server backend for repository reasoning tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .backends import ReasoningBackendObservationV1
from .codex_repository_backend_support import (
    CodexRepositoryBackendError,
    CodexRepositoryBackendSupport,
)
from .codex_repository_contract import (
    CODEX_REPOSITORY_AUTHORITY_REF,
    CODEX_REPOSITORY_OUTPUT_CONTRACT_REF,
    CODEX_REPOSITORY_PROVIDER_ROUTE_REF,
    CODEX_REPOSITORY_TOOL_POLICY_REF,
    authority_hash,
    output_contract_hash,
    provider_route_hash,
    tool_policy_hash,
)
from .git_snapshot import GitCommitSourceLoader
from .models import ReasoningSpecV1
from .repository_assignment import RepositoryReasoningAssignmentV1


class CodexRepositoryReasoningBackend(CodexRepositoryBackendSupport):
    """Smart worker semantics over durable Task/backend mechanics."""

    def _validate_spec(
        self, spec: ReasoningSpecV1
    ) -> tuple[RepositoryReasoningAssignmentV1, Path, GitCommitSourceLoader]:
        expected = {
            "output_contract_ref": CODEX_REPOSITORY_OUTPUT_CONTRACT_REF,
            "output_contract_hash": output_contract_hash(),
            "tool_policy_ref": CODEX_REPOSITORY_TOOL_POLICY_REF,
            "tool_policy_hash": tool_policy_hash(),
            "authority_ref": CODEX_REPOSITORY_AUTHORITY_REF,
            "authority_hash": authority_hash(),
            "provider_route_ref": CODEX_REPOSITORY_PROVIDER_ROUTE_REF,
            "provider_route_hash": provider_route_hash(self.model, self.effort),
        }
        for field_name, value in expected.items():
            if getattr(spec, field_name) != value:
                raise CodexRepositoryBackendError(
                    f"repository reasoning spec {field_name} does not match route contract"
                )
        if spec.mutation_policy != "read_only":
            raise CodexRepositoryBackendError(
                "repository Codex route requires read_only mutation policy"
            )
        if spec.continuation_policy != "none":
            raise CodexRepositoryBackendError(
                "repository reasoning v1 requires continuation_policy none"
            )
        if spec.budgets.provider_internal_concurrency_limit != 1:
            raise CodexRepositoryBackendError(
                "repository reasoning v1 keeps provider-internal subagents disabled"
            )
        if spec.context_refs or spec.dependency_proof_refs:
            raise CodexRepositoryBackendError(
                "repository reasoning v1 does not silently ignore context/dependency refs"
            )
        assignment = self.assignment_resolver(spec.assignment_ref)
        if assignment.assignment_ref != spec.assignment_ref:
            raise CodexRepositoryBackendError(
                "resolved assignment reference does not match ReasoningSpec"
            )
        if assignment.assignment_hash != spec.assignment_hash:
            raise CodexRepositoryBackendError(
                "resolved assignment hash does not match ReasoningSpec"
            )
        root = Path(self.repository_root_resolver(assignment.repo_name)).resolve()
        if not root.is_dir():
            raise CodexRepositoryBackendError(
                f"repository {assignment.repo_name!r} has no usable root"
            )
        loader = GitCommitSourceLoader(root, assignment.source_commit)
        if loader.source_commit != assignment.source_commit:
            raise CodexRepositoryBackendError(
                "assignment source_commit did not resolve to the exact frozen commit"
            )
        return assignment, root, loader

    @staticmethod
    def extract_usage(token_usage_events: tuple[dict[str, Any], ...]) -> dict[str, int]:
        if not token_usage_events:
            return {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
            }
        params = token_usage_events[-1]
        block = params.get("tokenUsage") or params.get("usage") or {}
        candidate = (
            (block.get("total") or block.get("last") or block)
            if isinstance(block, dict)
            else {}
        )
        if not isinstance(candidate, dict):
            candidate = {}

        def pick(*names: str) -> int:
            for name in names:
                value = candidate.get(name)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
            return 0

        return {
            "input_tokens": pick("inputTokens", "input_tokens"),
            "cached_input_tokens": pick("cachedInputTokens", "cached_input_tokens"),
            "output_tokens": pick("outputTokens", "output_tokens"),
            "reasoning_output_tokens": pick(
                "reasoningOutputTokens", "reasoning_output_tokens"
            ),
            "total_tokens": pick("totalTokens", "total_tokens"),
        }

    def start(
        self, spec: ReasoningSpecV1, backend_ref: str
    ) -> ReasoningBackendObservationV1:
        from .codex_repository_execution import execute_repository_reasoning

        return execute_repository_reasoning(self, spec, backend_ref)
