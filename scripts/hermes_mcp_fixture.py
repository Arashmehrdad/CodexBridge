from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("codexbridge-disposable-fixture")


def _state_path() -> Path:
    home = Path(os.environ.get("HERMES_HOME", ".")).resolve()
    home.mkdir(parents=True, exist_ok=True)
    return home / "codexbridge-side-effect-fixture.json"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"mutations": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("mutations"), dict):
        raise RuntimeError("fixture state is invalid")
    return data


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


@mcp.tool()
def echo_fixture(value: str) -> dict[str, str]:
    """Echo a value through the CodexBridge disposable MCP fixture."""
    return {"source": "codexbridge-disposable-mcp", "value": value}


@mcp.tool()
def apply_reversible_fixture(
    idempotency_key: str,
    value: str,
    simulate_ambiguous_response: bool = False,
) -> dict[str, Any]:
    """Apply one reversible fixture mutation exactly once for an idempotency key."""
    key = idempotency_key.strip()
    if not key:
        raise ValueError("idempotency_key must not be empty")
    state = _load_state()
    mutations = state["mutations"]
    existing = mutations.get(key)
    if existing is not None:
        if existing["value"] != value:
            raise ValueError("idempotency key was already used with different arguments")
        return {"applied": False, "idempotency_key": key, "outcome": existing}
    outcome = {"value": value, "application_count": 1}
    mutations[key] = outcome
    _save_state(state)
    if simulate_ambiguous_response:
        raise RuntimeError("simulated ambiguous response after committed mutation")
    return {"applied": True, "idempotency_key": key, "outcome": outcome}


@mcp.tool()
def reconcile_reversible_fixture(idempotency_key: str) -> dict[str, Any]:
    """Return the authoritative external outcome for one fixture mutation."""
    key = idempotency_key.strip()
    state = _load_state()
    outcome = state["mutations"].get(key)
    return {"idempotency_key": key, "exists": outcome is not None, "outcome": outcome}


@mcp.tool()
def revert_reversible_fixture(idempotency_key: str) -> dict[str, Any]:
    """Revert one fixture mutation and report whether an outcome was removed."""
    key = idempotency_key.strip()
    state = _load_state()
    outcome = state["mutations"].pop(key, None)
    _save_state(state)
    return {"idempotency_key": key, "reverted": outcome is not None, "outcome": outcome}


if __name__ == "__main__":
    mcp.run(transport="stdio")
