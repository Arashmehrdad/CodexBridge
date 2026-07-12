from __future__ import annotations
from pathlib import Path
from uuid import uuid4

from codexbridge.config import LocalCodingConfig
from codexbridge.events import append_jsonl
from codexbridge.local_agent.models import CommandRunStatus
from codexbridge.local_agent.runner import LocalAgentCommandRunner
from codexbridge.policy import PolicyEngine, PolicyEvaluationRequest
from codexbridge.policy.models import ApprovalStatus, CanonicalPermissionTier
from codexbridge.return_loop.atomic_writer import atomic_write_json, atomic_write_text
from codexbridge.run_store import utc_now

from .classifier import classify_local_coding_task
from .models import (
    LocalCodingRequest,
    LocalCodingRun,
    LocalCodingStatus,
    LocalEditProposal,
    LocalPatchApplyResult,
    LocalPatchOperation,
    LocalPatchPreview,
    LocalPatchRollbackResult,
)
from .patch_apply import apply_text_atomically
from .patch_builder import apply_operations_to_text, parse_objective_patch
from .patch_preview import sha256_text, unified_diff
from .patch_validator import validate_patch
from ..repo_wiki import mark_repo_wiki_stale
from .rollback import restore_original_content


class LocalCodingManager:
    def __init__(
        self,
        *,
        runs_dir: Path | None = None,
        config: LocalCodingConfig | None = None,
        policy_engine: PolicyEngine | None = None,
        command_runner: LocalAgentCommandRunner | None = None,
        local_model=None,
    ):
        self.config = config or LocalCodingConfig()
        self.runs_dir = Path(runs_dir or Path.cwd() / "runs" / "local_coding").resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.policy_engine = policy_engine or PolicyEngine()
        self.command_runner = command_runner or LocalAgentCommandRunner(
            runs_dir=self.runs_dir.parent
        )
        self.local_model = local_model

    def prepare_local_edit(self, request: LocalCodingRequest) -> LocalPatchPreview:
        operations = request.operations or self._operations_from_request(request)
        classification = classify_local_coding_task(
            request.objective, operations, self.config
        )
        run_dir = self._run_dir(request.edit_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._event(
            request.edit_id,
            "local_coding_requested",
            "Local coding requested",
            {"objective": request.objective},
        )
        if not classification.eligible:
            return self._blocked_preview(request, classification.blocked_reasons)

        target_file = operations[0].target_file
        target_path = self._target_path(request.repo_path, target_file)
        if not _target_is_readable(request.repo_path, target_path):
            return self._blocked_preview(
                request,
                [
                    "path_outside_repo"
                    if not _target_inside_repo(request.repo_path, target_path)
                    else "target_file_missing"
                ],
            )
        if target_path.stat().st_size > self.config.local_coding_max_file_bytes:
            return self._blocked_preview(request, ["file_too_large"])
        original = target_path.read_text(encoding="utf-8")
        try:
            updated = apply_operations_to_text(original, operations)
        except ValueError as exc:
            return self._blocked_preview(request, [str(exc).replace(" ", "_")])
        diff = unified_diff(original, updated, target_file)
        validation = validate_patch(
            repo_path=request.repo_path,
            target_file=target_file,
            original=original,
            updated=updated,
            diff=diff,
            config=self.config,
        )
        if not validation.valid:
            return self._blocked_preview(request, validation.blocked_reasons, diff=diff)

        preview_policy = self.policy_engine.evaluate(
            PolicyEvaluationRequest(
                action=_policy_safe_action(request.objective),
                action_type="local_coding_preview",
                repo_name=request.repo_name,
                repo_path=request.repo_path,
                permission_tier=CanonicalPermissionTier.T3_WRITE_PREVIEW_DRY_RUN,
            )
        )
        apply_policy = self.policy_engine.evaluate(
            PolicyEvaluationRequest(
                action=_policy_safe_action(request.objective),
                action_type="local_coding_apply",
                repo_name=request.repo_name,
                repo_path=request.repo_path,
                permission_tier=CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
            )
        )
        status = (
            LocalCodingStatus.BLOCKED
            if preview_policy.blocked or apply_policy.human_required
            else LocalCodingStatus.APPROVAL_REQUIRED
        )
        approval_request_id = apply_policy.approval_request_id
        proposal = LocalEditProposal(
            edit_id=request.edit_id,
            objective=request.objective,
            repo_name=request.repo_name,
            repo_path=request.repo_path,
            target_file=target_file,
            operations=operations,
            original_sha256=sha256_text(original),
            resulting_sha256=sha256_text(updated),
            changed_lines=validation.changed_lines,
            changed_bytes=validation.changed_bytes,
            status=status,
            classification=classification,
            policy_result=apply_policy.to_dict(),
            approval_request_id=approval_request_id,
            validation_commands=request.validation_commands
            or self.config.local_coding_default_validation_commands,
            rollback_path=run_dir / "rollback.patch",
            created_at=utc_now(),
            audit_event_id=f"local_coding_{uuid4().hex}",
        )
        atomic_write_json(run_dir / "proposal.json", proposal.to_dict())
        atomic_write_text(run_dir / "preview.diff", diff)
        atomic_write_text(run_dir / "preview.md", _preview_markdown(proposal, diff))
        atomic_write_json(
            run_dir / "policy_result.json",
            {"preview": preview_policy.to_dict(), "apply": apply_policy.to_dict()},
        )
        if approval_request_id:
            approval = self.policy_engine.approval_store.get(approval_request_id)
            atomic_write_json(
                run_dir / "approval_request.json", approval.model_dump(mode="json")
            )
        atomic_write_text(run_dir / "original_snapshot.txt", original)
        self._write_run(
            LocalCodingRun(
                edit_id=request.edit_id,
                status=status,
                repo_name=request.repo_name,
                repo_path=request.repo_path,
                target_file=target_file,
                objective=request.objective,
                proposal_path=run_dir / "proposal.json",
                preview_diff_path=run_dir / "preview.diff",
                preview_md_path=run_dir / "preview.md",
                approval_request_id=approval_request_id,
                artifact_paths=[
                    run_dir / name
                    for name in (
                        "proposal.json",
                        "preview.diff",
                        "preview.md",
                        "policy_result.json",
                        "approval_request.json",
                        "original_snapshot.txt",
                    )
                ],
                created_at=proposal.created_at,
                updated_at=utc_now(),
                audit_event_id=proposal.audit_event_id,
            )
        )
        self._event(
            request.edit_id,
            "preview_ready",
            "Patch preview created",
            {"status": status.value, "approval_request_id": approval_request_id},
        )
        return LocalPatchPreview(
            edit_id=request.edit_id,
            status=status,
            proposal_path=run_dir / "proposal.json",
            preview_diff_path=run_dir / "preview.diff",
            preview_md_path=run_dir / "preview.md",
            policy_result_path=run_dir / "policy_result.json",
            approval_request_path=run_dir / "approval_request.json"
            if approval_request_id
            else None,
            diff_summary=f"{validation.changed_lines} changed lines, {validation.changed_bytes} changed bytes",
            unified_diff=diff,
            blocked_reasons=[]
            if status != LocalCodingStatus.BLOCKED
            else apply_policy.reasons,
            audit_event_id=proposal.audit_event_id,
        )

    def apply_local_edit(
        self, edit_id: str, approval_request_id: str
    ) -> LocalPatchApplyResult:
        run_dir = self._run_dir(edit_id)
        audit_id = f"local_coding_{uuid4().hex}"
        if not self.config.local_coding_apply_enabled:
            return self._apply_blocked(edit_id, "local_coding_apply_disabled", audit_id)
        proposal = LocalEditProposal.model_validate_json(
            (run_dir / "proposal.json").read_text(encoding="utf-8")
        )
        if proposal.approval_request_id != approval_request_id:
            return self._apply_blocked(edit_id, "approval_request_mismatch", audit_id)
        approval = self.policy_engine.approval_store.get(approval_request_id)
        if (
            approval.required_approver != "chatgpt"
            or approval.status != ApprovalStatus.APPROVED
        ):
            return self._apply_blocked(edit_id, "approval_not_approved", audit_id)
        target_path = self._target_path(proposal.repo_path, proposal.target_file)
        original = target_path.read_text(encoding="utf-8")
        if sha256_text(original) != proposal.original_sha256:
            return self._apply_blocked(
                edit_id, "original_hash_mismatch", audit_id, target_path
            )
        updated = apply_operations_to_text(original, proposal.operations)
        diff = unified_diff(original, updated, proposal.target_file)
        validation = validate_patch(
            repo_path=proposal.repo_path,
            target_file=proposal.target_file,
            original=original,
            updated=updated,
            diff=diff,
            config=self.config,
        )
        if not validation.valid:
            return self._apply_blocked(
                edit_id,
                "validation_blocked:" + ",".join(validation.blocked_reasons),
                audit_id,
                target_path,
            )
        atomic_write_text(run_dir / "rollback.patch", diff)
        atomic_write_text(run_dir / "original_snapshot.txt", original)
        apply_text_atomically(target_path, updated)
        try:
            mark_repo_wiki_stale(
                proposal.repo_path,
                proposal.repo_name,
                reason="local_coding_apply",
            )
        except Exception:
            # Wiki freshness is advisory; never turn an already-applied,
            # policy-approved local edit into a false write failure.
            pass
        command_results = self._run_validation(proposal)
        status = (
            LocalCodingStatus.VALIDATION_PASSED
            if _validation_success(command_results)
            else LocalCodingStatus.VALIDATION_FAILED
        )
        result = LocalPatchApplyResult(
            edit_id=edit_id,
            status=status,
            target_file=target_path,
            apply_result_path=run_dir / "apply_result.json",
            validation_results_path=run_dir / "validation_results.json",
            rollback_patch_path=run_dir / "rollback.patch",
            validation_results=command_results,
            audit_event_id=audit_id,
        )
        atomic_write_json(
            run_dir / "apply_request.json",
            {"edit_id": edit_id, "approval_request_id": approval_request_id},
        )
        atomic_write_json(
            run_dir / "validation_results.json", {"results": command_results}
        )
        atomic_write_json(run_dir / "apply_result.json", result.to_dict())
        self._update_run(
            edit_id, status=status, apply_result_path=run_dir / "apply_result.json"
        )
        self._event(edit_id, "patch_applied", "Patch applied", {"status": status.value})
        return result

    def rollback_local_edit(self, edit_id: str) -> LocalPatchRollbackResult:
        run_dir = self._run_dir(edit_id)
        if not (run_dir / "proposal.json").exists():
            return LocalPatchRollbackResult(
                edit_id=edit_id,
                status=LocalCodingStatus.FAILED,
                error="unmanaged_edit",
                audit_event_id=f"local_coding_{uuid4().hex}",
            )
        proposal = LocalEditProposal.model_validate_json(
            (run_dir / "proposal.json").read_text(encoding="utf-8")
        )
        result = restore_original_content(
            edit_id=edit_id,
            target_file=self._target_path(proposal.repo_path, proposal.target_file),
            original_snapshot_path=run_dir / "original_snapshot.txt",
            result_path=run_dir / "rollback_result.json",
        )
        if result.status == LocalCodingStatus.ROLLED_BACK:
            self._update_run(
                edit_id,
                status=LocalCodingStatus.ROLLED_BACK,
                rollback_result_path=run_dir / "rollback_result.json",
            )
        self._event(
            edit_id,
            "rollback_completed",
            "Rollback completed",
            {"status": result.status.value},
        )
        return result

    def get(self, edit_id: str) -> LocalCodingRun:
        return LocalCodingRun.model_validate_json(
            (self._run_dir(edit_id) / "run.json").read_text(encoding="utf-8")
        )

    def list(self, limit: int = 20) -> list[LocalCodingRun]:
        runs = [
            LocalCodingRun.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self.runs_dir.glob("*/run.json")
        ]
        runs.sort(key=lambda item: item.updated_at, reverse=True)
        return runs[:limit]

    def cancel(self, edit_id: str) -> LocalCodingRun:
        self._update_run(edit_id, status=LocalCodingStatus.CANCELLED)
        self._event(edit_id, "cancelled", "Local edit cancelled", {})
        return self.get(edit_id)

    def _operations_from_request(
        self, request: LocalCodingRequest
    ) -> list[LocalPatchOperation]:
        target, operations = parse_objective_patch(request.objective, request.repo_path)
        if target and request.target_file is None:
            request.target_file = target
        if (
            self.config.local_coding_use_local_model
            and not operations
            and self.local_model is not None
        ):
            try:
                proposal = self.local_model.draft_local_edit(request.objective)
                return proposal.operations
            except Exception:
                return []
        return operations

    def _blocked_preview(
        self, request: LocalCodingRequest, reasons: list[str], diff: str = ""
    ) -> LocalPatchPreview:
        run_dir = self._run_dir(request.edit_id)
        audit_id = f"local_coding_{uuid4().hex}"
        atomic_write_json(
            run_dir / "proposal.json",
            {
                "edit_id": request.edit_id,
                "status": LocalCodingStatus.BLOCKED.value,
                "blocked_reasons": reasons,
            },
        )
        atomic_write_text(run_dir / "preview.diff", diff)
        atomic_write_text(
            run_dir / "preview.md",
            "Local coding preview blocked.\n\n"
            + "\n".join(f"- {reason}" for reason in reasons),
        )
        atomic_write_json(
            run_dir / "policy_result.json", {"blocked": True, "reasons": reasons}
        )
        self._write_run(
            LocalCodingRun(
                edit_id=request.edit_id,
                status=LocalCodingStatus.BLOCKED,
                repo_name=request.repo_name,
                repo_path=request.repo_path,
                target_file=request.target_file,
                objective=request.objective,
                proposal_path=run_dir / "proposal.json",
                preview_diff_path=run_dir / "preview.diff",
                preview_md_path=run_dir / "preview.md",
                artifact_paths=[
                    run_dir / "proposal.json",
                    run_dir / "preview.diff",
                    run_dir / "preview.md",
                    run_dir / "policy_result.json",
                ],
                created_at=utc_now(),
                updated_at=utc_now(),
                audit_event_id=audit_id,
            )
        )
        self._event(
            request.edit_id,
            "preview_blocked",
            "Patch preview blocked",
            {"reasons": reasons},
        )
        return LocalPatchPreview(
            edit_id=request.edit_id,
            status=LocalCodingStatus.BLOCKED,
            proposal_path=run_dir / "proposal.json",
            preview_diff_path=run_dir / "preview.diff",
            preview_md_path=run_dir / "preview.md",
            policy_result_path=run_dir / "policy_result.json",
            diff_summary="blocked",
            unified_diff=diff,
            blocked_reasons=reasons,
            audit_event_id=audit_id,
        )

    def _apply_blocked(
        self, edit_id: str, error: str, audit_id: str, target_path: Path | None = None
    ) -> LocalPatchApplyResult:
        result = LocalPatchApplyResult(
            edit_id=edit_id,
            status=LocalCodingStatus.BLOCKED,
            target_file=target_path,
            apply_result_path=self._run_dir(edit_id) / "apply_result.json",
            error=error,
            audit_event_id=audit_id,
        )
        atomic_write_json(
            self._run_dir(edit_id) / "apply_result.json", result.to_dict()
        )
        self._event(edit_id, "apply_blocked", "Patch apply blocked", {"error": error})
        return result

    def _run_validation(self, proposal: LocalEditProposal) -> list[dict]:
        results = []
        for command_id in proposal.validation_commands:
            if command_id not in {"git_status", "pytest", "pip_check"}:
                results.append(
                    {
                        "command_id": command_id,
                        "status": "blocked",
                        "error": "unknown_validation_command",
                    }
                )
                continue
            result = self.command_runner.run_project_command(
                command_id=command_id,
                repo_name=proposal.repo_name,
                repo_path=proposal.repo_path,
            )
            results.append(result.to_dict())
        return results

    def _target_path(self, repo_path: Path, target_file: Path) -> Path:
        target = Path(target_file)
        return (
            target.resolve()
            if target.is_absolute()
            else (Path(repo_path).resolve() / target).resolve()
        )

    def _run_dir(self, edit_id: str) -> Path:
        return self.runs_dir / edit_id

    def _write_run(self, run: LocalCodingRun) -> None:
        atomic_write_json(self._run_dir(run.edit_id) / "run.json", run.to_dict())

    def _update_run(self, edit_id: str, **fields) -> None:
        run = self.get(edit_id)
        for key, value in fields.items():
            setattr(run, key, value)
        run.updated_at = utc_now()
        self._write_run(run)

    def _event(self, edit_id: str, action: str, message: str, metadata: dict) -> None:
        append_jsonl(
            self._run_dir(edit_id) / "events.jsonl",
            {
                "timestamp": utc_now(),
                "edit_id": edit_id,
                "action": action,
                "message": message,
                "metadata": metadata,
            },
        )


def _preview_markdown(proposal: LocalEditProposal, diff: str) -> str:
    return "\n".join(
        [
            f"# Local Edit Preview: {proposal.edit_id}",
            "",
            f"- Status: {proposal.status.value}",
            f"- Target file: {proposal.target_file}",
            f"- Changed lines: {proposal.changed_lines}",
            f"- Changed bytes: {proposal.changed_bytes}",
            f"- Approval request: {proposal.approval_request_id or ''}",
            "",
            "```diff",
            diff,
            "```",
            "",
        ]
    )


def _validation_success(results: list[dict]) -> bool:
    if not results:
        return True
    blocked = {
        CommandRunStatus.BLOCKED.value,
        CommandRunStatus.PROFILE_MISSING.value,
        CommandRunStatus.PERMISSION_DENIED.value,
        CommandRunStatus.REPO_MISSING.value,
    }
    return all(
        item.get("status") not in blocked and (item.get("exit_code") in {0, None})
        for item in results
    )


def _target_inside_repo(repo_path: Path, target_path: Path) -> bool:
    try:
        Path(target_path).resolve().relative_to(Path(repo_path).resolve())
        return True
    except ValueError:
        return False


def _target_is_readable(repo_path: Path, target_path: Path) -> bool:
    return (
        _target_inside_repo(repo_path, target_path)
        and Path(target_path).exists()
        and Path(target_path).is_file()
    )


def _policy_safe_action(objective: str) -> str:
    return objective.replace("non-secret", "non_sensitive")
