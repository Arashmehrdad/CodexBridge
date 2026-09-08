"""Compatibility gates for Soma's supported FastMCP runtime."""

from __future__ import annotations

import fastmcp
from fastmcp.tools import ToolResult


def test_supported_fastmcp_version_is_installed() -> None:
    assert fastmcp.__version__ == "4.0.3"


def test_tool_result_uses_the_public_fastmcp_import() -> None:
    assert ToolResult.__module__ == "fastmcp.tools.base"
