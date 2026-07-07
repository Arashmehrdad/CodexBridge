from __future__ import annotations

import json
from pathlib import Path

from codexbridge.codex_router import CodexEscalationRequest, CodexEscalationRouter
from codexbridge.codex_router.codex_client import NoopCodexClient
from codexbridge.codex_router.models import CodexEscalationStatus, CodexInvocationResult
from codexbridge.config import CodexRouterConfig
from codexbridge.memory.repository import ProjectMemoryRepository
from codexbridge.policy import PolicyEngine


def router(tmp_path: Path, **kwargs) -> CodexEscalationRouter:
    return CodexEscalationRouter(
        router_config=kwargs.pop("router_config", CodexRouterConfig()),
        policy_engine=kwargs.pop(
            "policy_engine", PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals")
        ),
        packet_dir=tmp_path / "runs" / "codex_escalations",
        **kwargs,
    )


def test_local_only_tasks_are_not_escalated(tmp_path: Path) -> None:
    for objective in (
        "inspect repo",
        "summarize logs",
        "run tests",
        "search memory for failures",
    ):
        result = router(tmp_path).route_escalation(
            CodexEscalationRequest(objective=objective)
        )
        assert result.status == CodexEscalationStatus.LOCAL_ONLY
        assert result.packet is None


def test_edit_create_refactor_fix_are_codex_required_packets(tmp_path: Path) -> None:
    for objective in (
        "edit source file",
        "create module for routing",
        "refactor policy code",
        "fix failing test after diagnosis",
    ):
        result = router(tmp_path).route_escalation(
            CodexEscalationRequest(
                objective=objective, repo_name="repo", repo_path=tmp_path
            )
        )
        assert result.status == CodexEscalationStatus.APPROVAL_REQUIRED
        assert result.packet is not None
        assert result.approval_request_id


def test_human_only_tasks_are_not_escalated(tmp_path: Path) -> None:
    for objective in ("use API key", "production deploy", "push to main", "rm -rf ."):
        result = router(tmp_path).route_escalation(
            CodexEscalationRequest(objective=objective)
        )
        assert result.status == CodexEscalationStatus.HUMAN_REQUIRED


def test_packet_artifacts_are_written_and_include_required_fields(
    tmp_path: Path,
) -> None:
    source = tmp_path / "app.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    result = router(tmp_path).route_escalation(
        CodexEscalationRequest(
            objective="edit source file",
            repo_name="repo",
            repo_path=tmp_path,
            relevant_files=[source],
            current_error="AssertionError",
            tests_already_run=["pytest"],
            constraints=["minimal edit"],
            allowed_files=["app.py"],
            forbidden_files=[".env"],
            expected_output="patch and validation",
        )
    )

    artifacts = result.artifacts
    assert artifacts.packet_json_path.exists()
    assert artifacts.prompt_path.exists()
    assert artifacts.context_manifest_path.exists()
    packet = json.loads(artifacts.packet_json_path.read_text(encoding="utf-8"))
    assert packet["objective"] == "edit source file"
    assert packet["current_error"] == "AssertionError"
    assert packet["tests_already_run"] == ["pytest"]
    assert packet["allowed_files"] == ["app.py"]
    assert packet["expected_output"] == "patch and validation"
    assert packet["policy_decision"]
    assert packet["audit_event_id"]


def test_packet_blocks_sensitive_context_and_respects_file_size(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("api key = abc123", encoding="utf-8")
    big = tmp_path / "big.txt"
    big.write_text("x" * 100, encoding="utf-8")
    config = CodexRouterConfig(codex_router_max_file_bytes=10)
    result = router(tmp_path, router_config=config).route_escalation(
        CodexEscalationRequest(
            objective="edit source file",
            repo_path=tmp_path,
            relevant_files=[secret, big],
        )
    )

    assert result.status == CodexEscalationStatus.BLOCKED
    assert "API_KEY" in result.sensitivity_flags
    manifest = json.loads(
        result.artifacts.context_manifest_path.read_text(encoding="utf-8")
    )
    assert any(
        item["skipped_reason"] == "file_too_large"
        for item in manifest["relevant_files"]
    )


def test_huge_logs_are_truncated_not_fully_embedded(tmp_path: Path) -> None:
    config = CodexRouterConfig(
        codex_router_max_log_bytes=20, codex_router_block_sensitive=False
    )
    result = router(tmp_path, router_config=config).route_escalation(
        CodexEscalationRequest(objective="edit source file", current_error="x" * 100)
    )

    error_snippet = [
        item
        for item in result.packet.relevant_snippets
        if item.source == "current_error"
    ][0].text
    assert "[truncated]" in error_snippet
    assert len(error_snippet) < 50


def test_memory_context_and_local_model_summary_are_optional(tmp_path: Path) -> None:
    memory_repo = ProjectMemoryRepository(
        db_path=tmp_path / "runs" / "memory" / "project_memory.sqlite3"
    )
    memory_repo.remember_project_fact("Router architecture uses packet artifacts")

    class FakeLocalModel:
        def compress_context(self, text):
            return type("Result", (), {"content": "compressed summary"})()

    from codexbridge.codex_router.context_builder import CodexContextBuilder

    builder = CodexContextBuilder(
        memory_repository=memory_repo, local_model=FakeLocalModel()
    )
    result = router(tmp_path, context_builder=builder).route_escalation(
        CodexEscalationRequest(objective="edit router architecture")
    )

    assert result.packet.memory_context
    assert result.packet.local_model_summary == "compressed summary"


class FakeCodexClient:
    def __init__(self):
        self.called = False

    def invoke(self, request):
        self.called = True
        return CodexInvocationResult(
            status=CodexEscalationStatus.COMPLETED, invoked=True, summary="done"
        )


def test_fake_codex_client_called_only_when_invoke_enabled_and_policy_permits(
    tmp_path: Path,
) -> None:
    client = FakeCodexClient()
    config = CodexRouterConfig(
        codex_router_invoke_enabled=True, codex_router_require_policy_approval=False
    )
    result = router(
        tmp_path, router_config=config, codex_client=client
    ).route_escalation(
        CodexEscalationRequest(objective="edit source file", invoke_codex=True)
    )

    assert client.called is True
    assert result.status == CodexEscalationStatus.INVOKED


def test_noop_codex_client_does_not_call_codex(tmp_path: Path) -> None:
    result = NoopCodexClient().invoke(type("Req", (), {})())

    assert result.status == CodexEscalationStatus.UNAVAILABLE
    assert result.invoked is False


def test_router_modules_do_not_introduce_forbidden_integrations() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("codexbridge/codex_router").glob("*.py")
    )

    assert "subprocess" not in source
    assert "PulseSender" not in source
    assert "playwright" not in source.lower()
    assert "selenium" not in source.lower()
