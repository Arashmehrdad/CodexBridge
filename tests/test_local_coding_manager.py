from __future__ import annotations

from pathlib import Path

from codexbridge.config import LocalCodingConfig
from codexbridge.local_agent.models import CommandRunResult, CommandRunStatus, PermissionTier
from codexbridge.local_coding import (
    LocalCodingManager,
    LocalCodingRequest,
    LocalCodingStatus,
    LocalPatchOperation,
    LocalPatchOperationType,
)
from codexbridge.policy import PolicyEngine
from codexbridge.policy.models import ApprovalStatus
from codexbridge.run_store import utc_now


class FakeCommandRunner:
    def __init__(self, status: CommandRunStatus = CommandRunStatus.SUCCESS):
        self.status = status
        self.calls: list[str] = []

    def run_project_command(self, *, command_id: str, repo_name=None, repo_path=None, **kwargs):
        self.calls.append(command_id)
        return CommandRunResult(
            run_id=f"run_{command_id}",
            command_id=command_id,
            repo_name=repo_name,
            repo_path=Path(repo_path) if repo_path else None,
            working_directory=Path(repo_path) if repo_path else Path.cwd(),
            argv=["fake", command_id],
            permission_tier=PermissionTier.READ_ONLY,
            status=self.status,
            exit_code=0 if self.status == CommandRunStatus.SUCCESS else 1,
            duration_seconds=0.01,
            timeout_seconds=1,
            timed_out=False,
            stdout_path=Path("stdout.txt"),
            stderr_path=Path("stderr.txt"),
            result_path=Path("result.json"),
            audit_event_id="audit_command",
            created_at=utc_now(),
        )


def make_manager(tmp_path: Path, repo: Path, *, apply_enabled: bool = False, runner=None) -> LocalCodingManager:
    return LocalCodingManager(
        runs_dir=tmp_path / "runs" / "local_coding",
        config=LocalCodingConfig(local_coding_apply_enabled=apply_enabled),
        policy_engine=PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals"),
        command_runner=runner or FakeCommandRunner(),
    )


def replace_request(repo: Path, edit_id: str = "local_edit_readme") -> LocalCodingRequest:
    return LocalCodingRequest(
        edit_id=edit_id,
        objective="fix typo in README",
        repo_path=repo,
        target_file=Path("README.md"),
        operations=[
            LocalPatchOperation(
                operation_type=LocalPatchOperationType.EXACT_TEXT_REPLACE,
                target_file=Path("README.md"),
                old_text="helo",
                new_text="hello",
            )
        ],
        validation_commands=["git_status"],
    )


def test_eligible_readme_typo_creates_preview_without_modifying_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_text("helo world\n", encoding="utf-8")
    manager = make_manager(tmp_path, repo)

    preview = manager.prepare_local_edit(replace_request(repo))

    run_dir = tmp_path / "runs" / "local_coding" / "local_edit_readme"
    assert preview.status == LocalCodingStatus.APPROVAL_REQUIRED
    assert readme.read_text(encoding="utf-8") == "helo world\n"
    assert (run_dir / "proposal.json").exists()
    assert (run_dir / "preview.diff").exists()
    assert (run_dir / "preview.md").exists()
    assert (run_dir / "policy_result.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert "+hello world" in (run_dir / "preview.diff").read_text(encoding="utf-8")


def test_docs_line_update_and_json_metadata_preview(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "guide.md").write_text("old line\n", encoding="utf-8")
    (repo / "README.md").write_text("{}", encoding="utf-8")
    manager = make_manager(tmp_path, repo)

    docs_preview = manager.prepare_local_edit(
        LocalCodingRequest(
            edit_id="local_edit_docs",
            objective="update one docs line",
            repo_path=repo,
            operations=[
                LocalPatchOperation(
                    operation_type=LocalPatchOperationType.REPLACE_LINE,
                    target_file=Path("docs/guide.md"),
                    line_number=1,
                    new_text="new line",
                )
            ],
        )
    )
    json_preview = manager.prepare_local_edit(
        LocalCodingRequest(
            edit_id="local_edit_json",
            objective="update non-secret config metadata in README json",
            repo_path=repo,
            operations=[
                LocalPatchOperation(
                    operation_type=LocalPatchOperationType.UPDATE_JSON_KEY,
                    target_file=Path("README.md"),
                    json_key="name",
                    json_value="codexbridge",
                )
            ],
        )
    )

    assert docs_preview.status == LocalCodingStatus.APPROVAL_REQUIRED
    assert json_preview.status == LocalCodingStatus.APPROVAL_REQUIRED


def test_source_test_multifile_large_huge_path_and_secret_blocks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "app.py").write_text("helo\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text("helo\n", encoding="utf-8")
    (repo / "README.md").write_text("helo\n", encoding="utf-8")
    (repo / "huge.md").write_text("x" * 30000, encoding="utf-8")
    manager = make_manager(tmp_path, repo)

    def preview(edit_id: str, objective: str, path: str, new: str = "hello"):
        return manager.prepare_local_edit(
            LocalCodingRequest(
                edit_id=edit_id,
                objective=objective,
                repo_path=repo,
                operations=[
                    LocalPatchOperation(
                        operation_type=LocalPatchOperationType.EXACT_TEXT_REPLACE,
                        target_file=Path(path),
                        old_text="helo",
                        new_text=new,
                    )
                ],
            )
        )

    assert preview("local_edit_source", "fix typo in docs", "app.py").status == LocalCodingStatus.BLOCKED
    assert preview("local_edit_test", "fix typo in docs", "tests/test_app.py").status == LocalCodingStatus.BLOCKED
    assert preview("local_edit_path", "fix typo in README", "../README.md").status == LocalCodingStatus.BLOCKED
    assert preview("local_edit_secret", "fix typo in README", "README.md", "password=abc").status == LocalCodingStatus.BLOCKED
    assert manager.prepare_local_edit(
        LocalCodingRequest(
            edit_id="local_edit_large",
            objective="update one README line",
            repo_path=repo,
            operations=[LocalPatchOperation(operation_type=LocalPatchOperationType.APPEND_LINE, target_file=Path("README.md"), new_text="x" * 5000)],
        )
    ).status == LocalCodingStatus.BLOCKED
    assert manager.prepare_local_edit(
        LocalCodingRequest(
            edit_id="local_edit_multifile",
            objective="update docs line",
            repo_path=repo,
            operations=[
                LocalPatchOperation(operation_type=LocalPatchOperationType.APPEND_LINE, target_file=Path("README.md"), new_text="a"),
                LocalPatchOperation(operation_type=LocalPatchOperationType.APPEND_LINE, target_file=Path("docs/missing.md"), new_text="b"),
            ],
        )
    ).status == LocalCodingStatus.BLOCKED
    assert preview("local_edit_huge", "fix typo in README", "huge.md").status == LocalCodingStatus.BLOCKED


def test_apply_requires_chatgpt_approval_and_rollback_restores_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_text("helo world\n", encoding="utf-8")
    manager = make_manager(tmp_path, repo, apply_enabled=True)
    preview = manager.prepare_local_edit(replace_request(repo))

    blocked = manager.apply_local_edit("local_edit_readme", preview.approval_request_path.stem if preview.approval_request_path else "")
    assert blocked.status == LocalCodingStatus.BLOCKED
    approval_id = manager.get("local_edit_readme").approval_request_id
    assert approval_id is not None
    manager.policy_engine.approval_store.record_decision(approval_id, decided_by="chatgpt", approved=True)

    applied = manager.apply_local_edit("local_edit_readme", approval_id)
    assert applied.status == LocalCodingStatus.VALIDATION_PASSED
    assert readme.read_text(encoding="utf-8") == "hello world\n"
    assert (tmp_path / "runs" / "local_coding" / "local_edit_readme" / "apply_result.json").exists()
    assert (tmp_path / "runs" / "local_coding" / "local_edit_readme" / "rollback.patch").exists()

    rolled_back = manager.rollback_local_edit("local_edit_readme")
    assert rolled_back.status == LocalCodingStatus.ROLLED_BACK
    assert readme.read_text(encoding="utf-8") == "helo world\n"


def test_apply_rechecks_original_hash_and_unknown_validation_is_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_text("helo world\n", encoding="utf-8")
    manager = make_manager(tmp_path, repo, apply_enabled=True)
    manager.prepare_local_edit(replace_request(repo, "local_edit_hash"))
    approval_id = manager.get("local_edit_hash").approval_request_id
    assert approval_id is not None
    manager.policy_engine.approval_store.record_decision(approval_id, decided_by="chatgpt", approved=True)
    readme.write_text("changed elsewhere\n", encoding="utf-8")

    result = manager.apply_local_edit("local_edit_hash", approval_id)

    assert result.status == LocalCodingStatus.BLOCKED
    assert result.error == "original_hash_mismatch"

    readme.write_text("helo world\n", encoding="utf-8")
    manager.prepare_local_edit(
        LocalCodingRequest(
            edit_id="local_edit_unknown_validation",
            objective="fix typo in README",
            repo_path=repo,
            operations=replace_request(repo).operations,
            validation_commands=["unknown"],
        )
    )
    approval_id = manager.get("local_edit_unknown_validation").approval_request_id
    assert approval_id is not None
    manager.policy_engine.approval_store.record_decision(approval_id, decided_by="chatgpt", approved=True)
    result = manager.apply_local_edit("local_edit_unknown_validation", approval_id)
    assert result.status == LocalCodingStatus.VALIDATION_FAILED
    assert result.validation_results[0]["status"] == "blocked"


def test_rollback_cannot_affect_unmanaged_edit(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, tmp_path)

    result = manager.rollback_local_edit("missing")

    assert result.status == LocalCodingStatus.FAILED
    assert result.error == "unmanaged_edit"


def test_fake_local_model_can_draft_tiny_patch_when_enabled(tmp_path: Path) -> None:
    class FakeLocalModel:
        def draft_local_edit(self, objective: str):
            return type("Proposal", (), {"operations": replace_request(repo).operations})()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("helo world\n", encoding="utf-8")
    manager = LocalCodingManager(
        runs_dir=tmp_path / "runs" / "local_coding",
        config=LocalCodingConfig(local_coding_use_local_model=True),
        policy_engine=PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals"),
        command_runner=FakeCommandRunner(),
        local_model=FakeLocalModel(),
    )

    preview = manager.prepare_local_edit(LocalCodingRequest(edit_id="local_edit_model", objective="fix typo in README", repo_path=repo))

    assert preview.status == LocalCodingStatus.APPROVAL_REQUIRED
    assert (tmp_path / "runs" / "local_coding" / "local_edit_model" / "proposal.json").exists()


def test_unavailable_local_model_does_not_fail_explicit_patch(tmp_path: Path) -> None:
    class BrokenLocalModel:
        def draft_local_edit(self, objective: str):
            raise RuntimeError("unavailable")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("helo world\n", encoding="utf-8")
    manager = LocalCodingManager(
        runs_dir=tmp_path / "runs" / "local_coding",
        config=LocalCodingConfig(local_coding_use_local_model=True),
        policy_engine=PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals"),
        command_runner=FakeCommandRunner(),
        local_model=BrokenLocalModel(),
    )

    preview = manager.prepare_local_edit(replace_request(repo, "local_edit_explicit"))

    assert preview.status == LocalCodingStatus.APPROVAL_REQUIRED


def test_local_coding_package_introduces_no_codex_pulsesender_browser_or_subprocess_imports() -> None:
    package = Path("codexbridge/local_coding")
    text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    assert "PulseSender" not in text
    assert "playwright" not in text
    assert "selenium" not in text
    assert "subprocess" not in text
    assert "CodexEscalationRouter" not in text
