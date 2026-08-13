from soma.reasoning.codex_repository_contract import (
    authority_hash,
    make_repository_reasoning_spec,
    output_contract_hash,
    provider_route_hash,
    semantic_prompt,
    tool_policy_hash,
)
from soma.reasoning.repository_assignment import RepositoryReasoningAssignmentV1


def test_repository_spec_hash_bindings_are_exact() -> None:
    spec = make_repository_reasoning_spec(
        assignment_ref="reasoning_assignment:" + "1" * 64,
        assignment_hash="2" * 64,
    )
    assert spec.output_contract_hash == output_contract_hash()
    assert spec.tool_policy_hash == tool_policy_hash()
    assert spec.authority_hash == authority_hash()
    assert spec.provider_route_hash == provider_route_hash()
    assert spec.mutation_policy == "read_only"
    assert spec.continuation_policy == "none"
    assert spec.budgets.provider_internal_concurrency_limit == 1


def test_prompt_preserves_worker_soma_sol_authority_split() -> None:
    assignment = RepositoryReasoningAssignmentV1(
        repo_name="Soma",
        source_commit="0123456789abcdef0123456789abcdef01234567",
        objective="Explain canonical Task state ownership.",
    )
    prompt = semantic_prompt(assignment)
    assert assignment.source_commit in prompt
    assert assignment.objective in prompt
    assert "reason about the code yourself" in prompt
    assert "Soma will not judge whether the evidence proves your claim" in prompt
    assert "Sol performs semantic adjudication and synthesis" in prompt
