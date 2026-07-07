from __future__ import annotations

from pathlib import Path

from codexbridge.capabilities import (
    PATCH_OPERATION_SCHEMA,
    capability_metadata,
    schema_hash,
    server_build_hash,
)


def test_patch_operation_schema_lists_supported_variants() -> None:
    variants = PATCH_OPERATION_SCHEMA["properties"]["type"]["enum"]
    assert variants == ["exact_text", "line_range", "unified_diff", "python_ast"]


def test_schema_hash_is_order_independent_for_objects() -> None:
    assert schema_hash({"b": 2, "a": 1}) == schema_hash({"a": 1, "b": 2})


def test_server_build_hash_changes_with_python_content(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    module = package / "module.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    first = server_build_hash(package)
    module.write_text("VALUE = 2\n", encoding="utf-8")
    second = server_build_hash(package)
    assert first != second


def test_capability_metadata_contains_stable_epoch() -> None:
    first = capability_metadata(PATCH_OPERATION_SCHEMA)
    second = capability_metadata(PATCH_OPERATION_SCHEMA)
    assert first == second
    assert first["capability_epoch"] == (
        f"{first['server_build_hash'][:12]}-{first['schema_hash'][:12]}"
    )
