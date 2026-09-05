from __future__ import annotations

import asyncio

from fastmcp import Client

from soma import server


def test_owner_mcp_initialization_reminds_controller_to_read_agents() -> None:
    async def _initialize() -> str | None:
        async with Client(server.mcp) as client:
            return client.initialize_result.instructions

    instructions = asyncio.run(_initialize())

    assert instructions is not None
    assert "Before substantive work in any repository bound through Soma" in instructions
    assert "current AGENTS.md" in instructions
    assert "Re-read it after switching repositories" in instructions
    assert "fresh/continued chat re-entry" in instructions
