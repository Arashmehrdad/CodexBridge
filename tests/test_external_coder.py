from __future__ import annotations

import json
import subprocess
from pathlib import Path

from soma.config import ExternalCoderConfig
from soma.external_coder import (
    ExternalCoderHandoffGenerator,
    ExternalCoderHandoffRequest,
    ExternalCoderHandoffStatus,
    build_handoff_prompt,
    capture_repository_state,
)
from soma.memory.repository import ProjectMemoryRepository
from soma.policy import PolicyEngine


def generator(tmp_path: Path, **kwargs) -> ExternalCoderHandoffGenerator:
    return ExternalCoderHandoffGenerator(
        handoff_config=kwargs.pop("handoff_config", ExternalCoderConfig()),
        policy_engine=kwargs.pop(
            "policy_engine", PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals")
        ),
        handoff_dir=tmp_path / "runs" / "external_coder_handoffs",
        **kwargs,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo


def test_local_only_tasks_do_not_produce_handoffs(tmp_path: Path) -> None:
    for objective in (
        "inspect repo",
        "summarize logs",
        "run tests",
        "search memory for failures",
    ):
        result = generator(tmp_path).generate_handoff(
            ExternalCoderHandoffRequest(objective=objective)
        )
        assert result.status == ExternalCoderHandoffStatus.LOCAL_ONLY
        assert result.handoff is None


def test_coding_objectives_route_to_approval_required_handoffs(tmp_path: Path) -> None:
    for objective in (
        "edit source file",
        "create module for routing",
        "refactor policy code",
        "fix failing test after diagnosis",
    ):
        result = generator(tmp_path).generate_handoff(
            ExternalCoderHandoffRequest(
                objective=objective, repo_name="repo", repo_path=tmp_path
            )
        )
        assert result.status == ExternalCoderHandoffStatus.APPROVAL_REQUIRED
        assert result.handoff is not None
        assert result.approval_request_id


def test_human_only_tasks_are_never_handed_off(tmp_path: Path) -> None:
    for objective in ("use API key", "production deploy", "push to main", "rm -rf ."):
        result = generator(tmp_path).generate_handoff(
            ExternalCoderHandoffRequest(objective=objective)
        )
        assert result.status == ExternalCoderHandoffStatus.HUMAN_REQUIRED


def test_handoff_artifacts_include_required_fields(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    result = generator(tmp_path).generate_handoff(
        ExternalCoderHandoffRequest(
            objective="edit source file",
            repo_name="repo",
            repo_path=tmp_path,
            relevant_files=[source],
            current_error="AssertionError",
            tests_already_run=["pytest"],
            constraints=["minimal edit"],
            allowed_files=["app.py"],
            forbidden_files=[".env"],
            expected_report="patch and validation",
        )
    )

    artifacts = result.artifacts
    assert artifacts.handoff_json_path.exists()
    assert artifacts.prompt_path.exists()
    assert artifacts.context_manifest_path.exists()
    handoff = json.loads(artifacts.handoff_json_path.read_text(encoding="utf-8"))
    assert handoff["objective"] == "edit source file"
    assert handoff["current_error"] == "AssertionError"
    assert handoff["tests_already_run"] == ["pytest"]
    assert handoff["allowed_files"] == ["app.py"]
    assert handoff["expected_report"] == "patch and validation"
    assert handoff["policy_decision"]
    assert handoff["audit_event_id"]
    assert "repository_state" in handoff


def test_handoff_prompt_is_provider_neutral_and_complete(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    config = ExternalCoderConfig(external_coder_require_policy_approval=False)
    result = generator(tmp_path, handoff_config=config).generate_handoff(
        ExternalCoderHandoffRequest(
            objective="edit source file",
            repo_name="repo",
            repo_path=repo,
            relevant_files=[repo / "app.py"],
            current_error="AssertionError: expected 2",
            tests_already_run=["pytest"],
            validation_commands=["pytest", "pip_check"],
            constraints=["minimal edit"],
            allowed_files=["app.py"],
            expected_report="Changed files, validation output, remaining risks.",
        )
    )

    assert result.status == ExternalCoderHandoffStatus.HANDOFF_READY
    prompt = result.artifacts.prompt_path.read_text(encoding="utf-8")
    for section in (
        "# Objective",
        "# Repository state",
        "# Relevant files",
        "# Evidence and failures",
        "# Approved scope",
        "# Constraints and repository safety rules",
        "# Tests and validation commands",
        "# Expected completion report",
    ):
        assert section in prompt
    # Provider-neutral: names multiple agents, prescribes none.
    assert "Claude Code" in prompt
    assert "Gemini CLI" in prompt
    assert "supplied to you manually" in prompt
    # Repository state captured from a real repo.
    state = result.handoff.repository_state
    assert state.captured is True
    assert state.branch == "main"
    assert len(state.head) == 40
    assert state.worktree_clean is True


def test_repository_state_capture_is_bounded_and_error_tolerant(
    tmp_path: Path,
) -> None:
    missing = capture_repository_state(tmp_path / "not-a-repo")
    assert missing.captured is False
    assert missing.error

    none_state = capture_repository_state(None)
    assert none_state.captured is False

    repo = _init_repo(tmp_path)
    for index in range(50):
        (repo / f"file-{index}.txt").write_text("x", encoding="utf-8")
    bounded = capture_repository_state(repo, max_status_bytes=100)
    assert bounded.captured is True
    assert bounded.worktree_clean is False
    assert "[truncated]" in bounded.worktree_status
    assert len(bounded.worktree_status.encode("utf-8")) < 200


def test_handoff_blocks_sensitive_context_and_respects_file_size(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("api key = abc123", encoding="utf-8")
    big = tmp_path / "big.txt"
    big.write_text("x" * 100, encoding="utf-8")
    config = ExternalCoderConfig(external_coder_max_file_bytes=10)
    result = generator(tmp_path, handoff_config=config).generate_handoff(
        ExternalCoderHandoffRequest(
            objective="edit source file",
            repo_path=tmp_path,
            relevant_files=[secret, big],
        )
    )

    assert result.status == ExternalCoderHandoffStatus.BLOCKED
    assert "API_KEY" in result.sensitivity_flags
    manifest = json.loads(
        result.artifacts.context_manifest_path.read_text(encoding="utf-8")
    )
    assert any(
        item["skipped_reason"] == "file_too_large"
        for item in manifest["relevant_files"]
    )


def test_huge_logs_are_truncated_not_fully_embedded(tmp_path: Path) -> None:
    config = ExternalCoderConfig(
        external_coder_max_log_bytes=20, external_coder_block_sensitive=False
    )
    result = generator(tmp_path, handoff_config=config).generate_handoff(
        ExternalCoderHandoffRequest(
            objective="edit source file", current_error="x" * 100
        )
    )

    error_snippet = [
        item
        for item in result.handoff.relevant_snippets
        if item.source == "current_error"
    ][0].text
    assert "[truncated]" in error_snippet
    assert len(error_snippet) < 50


def test_memory_context_and_local_model_summary_are_optional(tmp_path: Path) -> None:
    memory_repo = ProjectMemoryRepository(
        db_path=tmp_path / "runs" / "memory" / "project_memory.sqlite3"
    )
    memory_repo.remember_project_fact("Handoff architecture uses packet artifacts")

    class FakeLocalModel:
        def compress_context(self, text):
            return type("Result", (), {"content": "compressed summary"})()

    from soma.external_coder.context_builder import ExternalCoderContextBuilder

    builder = ExternalCoderContextBuilder(
        memory_repository=memory_repo, local_model=FakeLocalModel()
    )
    result = generator(tmp_path, context_builder=builder).generate_handoff(
        ExternalCoderHandoffRequest(objective="edit handoff architecture")
    )

    assert result.handoff.memory_context
    assert result.handoff.local_model_summary == "compressed summary"


def test_package_has_no_invocation_or_transport_code() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("soma/external_coder").glob("*.py")
    )

    assert "subprocess" not in source
    assert "Popen" not in source
    assert "os.exec" not in source
    assert "os.system" not in source
    assert "shutil.which" not in source
    assert "spawn" not in source.lower()
    assert "PulseSender" not in source
    assert "playwright" not in source.lower()
    assert "selenium" not in source.lower()


def test_prompt_never_embeds_launch_instructions() -> None:
    from soma.external_coder.models import ExternalCoderHandoff

    handoff = ExternalCoderHandoff(
        handoff_id="handoff_x",
        objective="edit file",
        task_type="external_coder_handoff",
        created_at="2026-07-23T00:00:00+00:00",
        audit_event_id="audit_x",
    )
    prompt = build_handoff_prompt(handoff)
    assert "do not push" in prompt
    assert "# Expected completion report" in prompt
