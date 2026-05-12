from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import LocalPatchOperation, LocalPatchOperationType


def apply_operations_to_text(original: str, operations: list[LocalPatchOperation]) -> str:
    text = original
    for operation in operations:
        if operation.operation_type == LocalPatchOperationType.EXACT_TEXT_REPLACE:
            if operation.old_text not in text:
                raise ValueError("old_text not found")
            text = text.replace(operation.old_text, operation.new_text, 1)
        elif operation.operation_type == LocalPatchOperationType.APPEND_LINE:
            separator = "" if text.endswith("\n") or text == "" else "\n"
            text = f"{text}{separator}{operation.new_text}\n"
        elif operation.operation_type == LocalPatchOperationType.REPLACE_LINE:
            if operation.line_number is None or operation.line_number < 1:
                raise ValueError("line_number is required for replace_line")
            lines = text.splitlines(keepends=True)
            if operation.line_number > len(lines):
                raise ValueError("line_number is out of range")
            newline = "\n" if lines[operation.line_number - 1].endswith("\n") else ""
            lines[operation.line_number - 1] = operation.new_text + newline
            text = "".join(lines)
        elif operation.operation_type == LocalPatchOperationType.UPDATE_JSON_KEY:
            data = json.loads(text or "{}")
            data[operation.json_key] = operation.json_value
            text = json.dumps(data, indent=2, sort_keys=True) + "\n"
        else:
            raise ValueError(f"Unsupported operation: {operation.operation_type}")
    return text


def parse_objective_patch(objective: str, repo_path: Path) -> tuple[Path | None, list[LocalPatchOperation]]:
    # Compact explicit syntax for local-agent routing:
    # prepare local edit: replace README.md :: old text => new text
    text = objective.strip()
    if text.lower().startswith("replace ") and " :: " in text and "=>" in text:
        path_part, replacement = text[len("replace ") :].split(" :: ", 1)
        old, new = replacement.split("=>", 1)
        target = Path(path_part.strip())
        return target, [
            LocalPatchOperation(
                operation_type=LocalPatchOperationType.EXACT_TEXT_REPLACE,
                target_file=target,
                old_text=old.strip(),
                new_text=new.strip(),
            )
        ]
    if text.lower().startswith("append ") and " :: " in text:
        path_part, line = text[len("append ") :].split(" :: ", 1)
        target = Path(path_part.strip())
        return target, [LocalPatchOperation(operation_type=LocalPatchOperationType.APPEND_LINE, target_file=target, new_text=line.strip())]
    return None, []


def coerce_json_value(value: Any) -> Any:
    return value
