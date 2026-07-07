from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PATCH_OPERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["path", "expected_sha256", "type"],
    "properties": {
        "path": {"type": "string"},
        "expected_sha256": {"type": "string"},
        "type": {
            "type": "string",
            "enum": ["exact_text", "line_range", "unified_diff", "python_ast"],
        },
        "old_text": {"type": "string"},
        "new_text": {"type": "string"},
        "start_line": {"type": "integer", "minimum": 1},
        "end_line": {"type": "integer", "minimum": 1},
        "diff": {"type": "string"},
        "target_type": {
            "type": "string",
            "enum": ["function", "class", "import"],
        },
        "target_name": {"type": "string"},
        "insert_if_missing": {"type": "boolean"},
    },
    "additionalProperties": False,
}


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def server_build_hash(package_root: Path | None = None) -> str:
    root = (package_root or _package_root()).resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def schema_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def capability_metadata(schema_payload: Any | None = None) -> dict[str, str]:
    build = server_build_hash()
    schema = schema_hash(
        schema_payload if schema_payload is not None else PATCH_OPERATION_SCHEMA
    )
    return {
        "server_build_hash": build,
        "schema_hash": schema,
        "capability_epoch": f"{build[:12]}-{schema[:12]}",
    }
