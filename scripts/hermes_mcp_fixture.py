from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("codexbridge-disposable-fixture")


@mcp.tool()
def echo_fixture(value: str) -> dict[str, str]:
    """Echo a value through the CodexBridge disposable MCP fixture."""
    return {"source": "codexbridge-disposable-mcp", "value": value}


if __name__ == "__main__":
    mcp.run(transport="stdio")
