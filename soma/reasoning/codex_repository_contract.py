"""Provider contract for the production read-only Codex repository worker."""

from __future__ import annotations

from typing import Final

from soma.reasoning.backends import content_hash
from soma.reasoning.models import ReasoningBudgetsV1, ReasoningSpecV1
from soma.reasoning.repository_assignment import RepositoryReasoningAssignmentV1
from soma.reasoning.repository_evidence import semantic_output_schema


CODEX_REPOSITORY_MODEL: Final[str] = "gpt-5.6-luna"
CODEX_REPOSITORY_EFFORT: Final[str] = "low"
CODEX_REPOSITORY_PROTOCOL_MANIFEST_SHA256: Final[str] = (
    "dcc92e96e856b1d4f93548f7f8f73e26aa87766431a0e44ceb23049c58c0dcbc"
)
CODEX_REPOSITORY_PROVIDER_ROUTE_REF: Final[str] = (
    "provider-route:codex-app-server:repository:v1"
)
CODEX_REPOSITORY_OUTPUT_CONTRACT_REF: Final[str] = (
    "output-contract:repository_reasoning.semantic.v1"
)
CODEX_REPOSITORY_TOOL_POLICY_REF: Final[str] = (
    "tool-policy:codex-repository-read-only:v1"
)
CODEX_REPOSITORY_AUTHORITY_REF: Final[str] = "authority:repository-reasoning:v1"
CODEX_REPOSITORY_DEFAULT_WALL_TIME_SECONDS: Final[int] = 300
CODEX_REPOSITORY_DEFAULT_OUTPUT_BYTES: Final[int] = 32 * 1024


def provider_route_hash(
    model: str = CODEX_REPOSITORY_MODEL,
    effort: str = CODEX_REPOSITORY_EFFORT,
) -> str:
    return content_hash(
        {
            "schema": "soma.reasoning.codex_repository.route.v1",
            "provider": "codex",
            "transport": "app_server_stdio",
            "authentication": "chatgpt",
            "model": model,
            "effort": effort,
            "protocol_manifest_sha256": CODEX_REPOSITORY_PROTOCOL_MANIFEST_SHA256,
            "provider_internal_subagents": False,
        }
    )


def output_contract_hash() -> str:
    return content_hash(semantic_output_schema())


def tool_policy_hash() -> str:
    return content_hash(
        {
            "schema": "soma.reasoning.codex_repository.tool_policy.v1",
            "approval_policy": "never",
            "sandbox": "read_only",
            "repository_read_tools": True,
            "external_network": False,
            "mcp": False,
            "plugins": False,
            "protected_broker": False,
            "provider_internal_subagents": False,
        }
    )


def authority_hash() -> str:
    return content_hash(
        {
            "schema": "soma.reasoning.repository_authority.v1",
            "worker_authority": "semantic_analysis_and_evidence_choice",
            "soma_authority": "mechanical_lifecycle_identity_and_evidence_materialization",
            "sol_authority": "semantic_adjudication_and_synthesis",
            "mutation_policy": "read_only",
        }
    )


def make_repository_reasoning_spec(
    *,
    assignment_ref: str,
    assignment_hash: str,
    wall_time_seconds: int = CODEX_REPOSITORY_DEFAULT_WALL_TIME_SECONDS,
    output_bytes: int = CODEX_REPOSITORY_DEFAULT_OUTPUT_BYTES,
    model: str = CODEX_REPOSITORY_MODEL,
    effort: str = CODEX_REPOSITORY_EFFORT,
) -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref=assignment_ref,
        assignment_hash=assignment_hash,
        output_contract_ref=CODEX_REPOSITORY_OUTPUT_CONTRACT_REF,
        output_contract_hash=output_contract_hash(),
        tool_policy_ref=CODEX_REPOSITORY_TOOL_POLICY_REF,
        tool_policy_hash=tool_policy_hash(),
        authority_ref=CODEX_REPOSITORY_AUTHORITY_REF,
        authority_hash=authority_hash(),
        provider_route_ref=CODEX_REPOSITORY_PROVIDER_ROUTE_REF,
        provider_route_hash=provider_route_hash(model, effort),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=wall_time_seconds,
            output_bytes=output_bytes,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def semantic_prompt(assignment: RepositoryReasoningAssignmentV1) -> str:
    """Give the smart worker the task while keeping Soma's role mechanical."""
    instructions = assignment.instructions or "No additional instructions."
    return (
        "You are a smart read-only repository reasoning worker. Perform the task, "
        "reason about the code yourself, and choose the source locations that you "
        "believe support your conclusions. You may use read-only repository tools "
        "and commands. Do not modify files, Git state, services, or external systems. "
        f"The only authoritative source revision is commit {assignment.source_commit}. "
        "Inspect that exact commit rather than uncommitted working-tree content; use "
        "Git commit-aware reads such as git show/grep when needed. Return only the "
        "object required by the provided output schema. Evidence locations are "
        "repository-relative source_path plus inclusive one-based start_line/end_line. "
        "Do not copy proof quotes. Soma will only verify that your cited path/range "
        "exists in the frozen commit and will materialize it mechanically. Soma will "
        "not judge whether the evidence proves your claim; Sol performs semantic "
        "adjudication and synthesis. Preserve uncertainty or blockers when warranted.\n\n"
        f"OBJECTIVE:\n{assignment.objective}\n\n"
        f"ADDITIONAL INSTRUCTIONS:\n{instructions}"
    )


def execution_contract_hash() -> str:
    return content_hash(
        {
            "schema": "soma.reasoning.codex_repository.execution_contract.v1",
            "provider_route_ref": CODEX_REPOSITORY_PROVIDER_ROUTE_REF,
            "provider_route_hash": provider_route_hash(),
            "output_contract_ref": CODEX_REPOSITORY_OUTPUT_CONTRACT_REF,
            "output_contract_hash": output_contract_hash(),
            "tool_policy_ref": CODEX_REPOSITORY_TOOL_POLICY_REF,
            "tool_policy_hash": tool_policy_hash(),
            "authority_ref": CODEX_REPOSITORY_AUTHORITY_REF,
            "authority_hash": authority_hash(),
            "provider_internal_concurrency_limit": 1,
            "mutation_policy": "read_only",
        }
    )
