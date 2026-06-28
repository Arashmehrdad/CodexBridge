from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from codexbridge.return_loop.atomic_writer import atomic_write_text

from .models import LocalCodingStatus, LocalPatchRollbackResult


def restore_original_content(
    *, edit_id: str, target_file: Path, original_snapshot_path: Path, result_path: Path
) -> LocalPatchRollbackResult:
    audit_id = f"local_coding_{uuid4().hex}"
    if not original_snapshot_path.exists():
        result = LocalPatchRollbackResult(
            edit_id=edit_id,
            status=LocalCodingStatus.FAILED,
            target_file=target_file,
            rollback_result_path=result_path,
            error="rollback_snapshot_missing",
            audit_event_id=audit_id,
        )
        atomic_write_text(result_path, result.model_dump_json(indent=2))
        return result
    atomic_write_text(target_file, original_snapshot_path.read_text(encoding="utf-8"))
    result = LocalPatchRollbackResult(
        edit_id=edit_id,
        status=LocalCodingStatus.ROLLED_BACK,
        target_file=target_file,
        rollback_result_path=result_path,
        audit_event_id=audit_id,
    )
    atomic_write_text(result_path, result.model_dump_json(indent=2))
    return result
