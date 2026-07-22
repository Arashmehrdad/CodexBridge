from __future__ import annotations

from pathlib import Path

from soma.config import LocalCodingConfig

from .models import LocalCodingClassification, LocalPatchOperation
from .redaction import detect_sensitivity


SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".cs",
    ".cpp",
    ".c",
    ".h",
}
BLOCKED_TASK_MARKERS = (
    "delete volume",
    "drop database",
    "format drive",
    "rm -rf",
    "wipe",
)


def classify_local_coding_task(
    objective: str,
    operations: list[LocalPatchOperation],
    config: LocalCodingConfig | None = None,
) -> LocalCodingClassification:
    settings = config or LocalCodingConfig()
    text = objective.lower()
    blocked: list[str] = []
    sensitivity = detect_sensitivity(objective.replace("non-secret", "non_sensitive"))
    if sensitivity:
        blocked.append("secret_like_objective")
    if any(marker in text for marker in BLOCKED_TASK_MARKERS):
        blocked.append("ineligible_task_type")
    if len({Path(operation.target_file) for operation in operations}) > 1:
        blocked.append("multi_file_edit_blocked")
    if len(operations) > settings.local_coding_max_operations:
        blocked.append("too_many_operations")
    for operation in operations:
        suffix = Path(operation.target_file).suffix.lower()
        if settings.local_coding_block_source_code and suffix in SOURCE_EXTENSIONS:
            blocked.append("source_code_blocked")
        if settings.local_coding_block_tests and _looks_like_test_path(
            operation.target_file
        ):
            blocked.append("test_file_blocked")
    if not operations:
        blocked.append("no_patch_operations")
    if blocked:
        return LocalCodingClassification(
            eligible=False,
            reason="Local coding task is blocked.",
            blocked_reasons=sorted(set(blocked)),
            suggested_route="local_repo_tools_or_human",
            risk_level="high",
        )
    return LocalCodingClassification(
        eligible=True,
        reason="Task is eligible for local-coding preview.",
        risk_level="low",
    )


def _looks_like_test_path(path: Path) -> bool:
    parts = [part.lower() for part in Path(path).parts]
    name = Path(path).name.lower()
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")
