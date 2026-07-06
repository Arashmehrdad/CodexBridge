from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any, Callable

from .git_tools import changed_files
from .run_guards import snapshot_workspace


PhaseCallback = Callable[[str, dict[str, Any] | None], None]


@dataclass
class TransactionFileSnapshot:
    path: str
    existed: bool
    content: bytes | None


@dataclass
class TransactionContext:
    repo_root: Path
    touched_paths: list[str]
    phase_callback: PhaseCallback | None = None
    baseline_workspace: dict[str, tuple[int, int]] = field(init=False)
    baseline_dirty_files: list[str] = field(init=False)
    file_snapshots: dict[str, TransactionFileSnapshot] = field(init=False)
    temp_artifacts: list[Path] = field(default_factory=list)
    phases: list[dict[str, Any]] = field(default_factory=list)
    rollback: dict[str, Any] = field(
        default_factory=lambda: {"attempted": False, "ok": True, "errors": []}
    )
    validation_results: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.baseline_workspace = snapshot_workspace(self.repo_root)
        self.baseline_dirty_files = changed_files(self.repo_root)
        snapshots: dict[str, TransactionFileSnapshot] = {}
        for relative in self.touched_paths:
            absolute = self.repo_root / relative
            if absolute.exists():
                snapshots[relative] = TransactionFileSnapshot(
                    path=relative,
                    existed=True,
                    content=absolute.read_bytes(),
                )
            else:
                snapshots[relative] = TransactionFileSnapshot(
                    path=relative,
                    existed=False,
                    content=None,
                )
        self.file_snapshots = snapshots

    def set_phase(self, phase: str, details: dict[str, Any] | None = None) -> None:
        payload = {"phase": phase}
        if details:
            payload.update(details)
        self.phases.append(payload)
        if self.phase_callback is not None:
            self.phase_callback(phase, details)

    def register_temp_artifact(self, path: Path) -> None:
        self.temp_artifacts.append(path)

    def classify_changes(self) -> tuple[list[str], list[str], list[str]]:
        baseline_dirty_set = set(self.baseline_dirty_files)
        touched_content_changes = {
            relative
            for relative, snapshot in self.file_snapshots.items()
            if _path_changed_since_snapshot(self.repo_root / relative, snapshot)
        }
        introduced = sorted(touched_content_changes - baseline_dirty_set)
        preserved = sorted(baseline_dirty_set)
        workspace_changes = sorted(touched_content_changes)
        return introduced, preserved, workspace_changes


def _path_changed_since_snapshot(
    absolute: Path, snapshot: TransactionFileSnapshot
) -> bool:
    if absolute.exists() != snapshot.existed:
        return True
    if not absolute.exists():
        return False
    return absolute.read_bytes() != snapshot.content


def rollback_transaction(
    context: TransactionContext,
    *,
    write_bytes: Callable[[Path, bytes], None],
    unlink_path: Callable[[Path], None],
) -> dict[str, Any]:
    context.rollback["attempted"] = True
    for relative in reversed(context.touched_paths):
        snapshot = context.file_snapshots[relative]
        absolute = context.repo_root / relative
        try:
            if snapshot.existed:
                assert snapshot.content is not None
                write_bytes(absolute, snapshot.content)
            elif absolute.exists():
                unlink_path(absolute)
        except Exception as exc:  # pragma: no cover - exercised via tests
            context.rollback["ok"] = False
            context.rollback["errors"].append(f"{relative}: {exc}")
    for artifact in reversed(context.temp_artifacts):
        try:
            if artifact.exists():
                if artifact.is_dir():
                    shutil.rmtree(artifact)
                else:
                    artifact.unlink()
        except Exception as exc:  # pragma: no cover - exercised via tests
            context.rollback["ok"] = False
            context.rollback["errors"].append(f"{artifact}: {exc}")
    return dict(context.rollback)


def build_transaction_result(
    context: TransactionContext,
    *,
    validation_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    introduced, preserved, workspace_changes = context.classify_changes()
    return {
        "phases": list(context.phases),
        "validation_results": validation_results
        if validation_results is not None
        else list(context.validation_results),
        "rollback": dict(context.rollback),
        "introduced_changes": introduced,
        "preserved_preexisting_changes": preserved,
        "workspace_changes": workspace_changes,
    }
