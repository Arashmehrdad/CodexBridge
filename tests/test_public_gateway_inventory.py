from __future__ import annotations

import ast
from pathlib import Path

from soma.public_gateway_inventory import (
    PUBLIC_GATEWAY_INVENTORY,
    PUBLIC_GATEWAY_INVENTORY_VERSION,
    PUBLIC_GATEWAY_NAMES,
)


PUBLIC_TOOL_SOURCES = (
    Path("soma/server.py"),
    Path("soma/knowledge_tools_integration.py"),
)


def _is_public_tool_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return isinstance(target, ast.Attribute) and target.attr == "tool"


def _discover_public_tool_names() -> set[str]:
    names: set[str] = set()
    for path in PUBLIC_TOOL_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(_is_public_tool_decorator(decorator) for decorator in node.decorator_list):
                names.add(node.name)
    return names


def test_inventory_exactly_covers_current_public_gateway_surface() -> None:
    assert PUBLIC_GATEWAY_NAMES == _discover_public_tool_names()


def test_inventory_entries_are_versioned_unique_and_actionable() -> None:
    assert PUBLIC_GATEWAY_INVENTORY_VERSION == "cf1.0.v1"
    assert len(PUBLIC_GATEWAY_NAMES) == len(PUBLIC_GATEWAY_INVENTORY)

    for entry in PUBLIC_GATEWAY_INVENTORY:
        assert entry.name
        assert entry.family
        assert entry.source in {
            "soma.server",
            "soma.knowledge_tools_integration",
        }
        assert entry.response_path
        assert entry.cf1_risk


def test_inventory_covers_every_required_cf1_gateway_family() -> None:
    families = {entry.family for entry in PUBLIC_GATEWAY_INVENTORY}
    assert families == {
        "cloudflare",
        "codex",
        "docker",
        "knowledge",
        "repository",
        "runs",
        "ssh",
        "supervisors",
        "system",
        "trading",
        "workflows",
    }

