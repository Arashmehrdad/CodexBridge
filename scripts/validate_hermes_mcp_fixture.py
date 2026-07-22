from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from soma.hermes_companion_protocol import HERMES_COMPANION_PROTOCOL_VERSION

FIXTURE_QUERY = "Soma disposable MCP fixture"
FIXTURE_VALUE = "durable-mcp-gate"


def _request(process: subprocess.Popen[str], payload: dict[str, Any]) -> dict[str, Any]:
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps(payload, sort_keys=True) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError("Hermes companion exited without a response")
    response = json.loads(line)
    if not isinstance(response, dict):
        raise RuntimeError("Hermes companion response is not an object")
    if response.get("ok") is not True:
        raise RuntimeError(f"Hermes companion request failed: {response}")
    return response


def validate(checkout: Path, repository: Path) -> dict[str, Any]:
    checkout = checkout.resolve()
    repository = repository.resolve()
    runtime_home = repository / "runs" / "hermes-mcp-fixture-home"
    runtime_home.mkdir(parents=True, exist_ok=True)
    fixture = repository / "scripts" / "hermes_mcp_fixture.py"
    config = runtime_home / "config.yaml"
    config.write_text(
        "mcp_servers:\n"
        "  soma_fixture:\n"
        f"    command: {json.dumps(sys.executable)}\n"
        "    args:\n"
        f"      - {json.dumps(str(fixture))}\n"
        "    env:\n"
        f"      HERMES_HOME: {json.dumps(str(runtime_home))}\n"
        "    connect_timeout: 30\n"
        "    timeout: 30\n",
        encoding="utf-8",
    )

    environment = dict(os.environ)
    environment["HERMES_HOME"] = str(runtime_home)
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(repository), environment.get("PYTHONPATH", "")) if value
    )
    command = [
        sys.executable,
        "-m",
        "soma.hermes_companion",
        "--hermes-checkout",
        str(checkout),
    ]
    process = subprocess.Popen(
        command,
        cwd=repository,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        handshake = _request(process, {"operation": "handshake"})
        identity = {
            "protocol_version": HERMES_COMPANION_PROTOCOL_VERSION,
            "registry_generation": handshake["registry_generation"],
            "effective_schema_hash": handshake["effective_schema_hash"],
        }
        search = _request(
            process,
            {
                "operation": "tool_search",
                **identity,
                "query": FIXTURE_QUERY,
                "limit": 10,
            },
        )
        if search.get("result_count") != 1:
            raise RuntimeError(f"expected one disposable MCP tool, observed {search}")
        tool_name = search["results"][0]["name"]
        describe = _request(
            process,
            {"operation": "tool_describe", **identity, "tool_name": tool_name},
        )
        call = _request(
            process,
            {
                "operation": "tool_call",
                **identity,
                "tool_name": tool_name,
                "arguments": {"value": FIXTURE_VALUE},
            },
        )
        result_text = call["result"] if isinstance(call["result"], str) else json.dumps(call["result"])
        if "soma-disposable-mcp" not in result_text or FIXTURE_VALUE not in result_text:
            raise RuntimeError(f"unexpected disposable MCP result: {call['result']!r}")
        if handshake.get("model_runtime_initialized") is not False:
            raise RuntimeError("Hermes model runtime initialization evidence is invalid")
        return {
            "tool_name": tool_name,
            "tool_schema_hash": describe["tool_schema_hash"],
            "registry_generation": handshake["registry_generation"],
            "effective_schema_hash": handshake["effective_schema_hash"],
            "model_runtime_initialized": handshake["model_runtime_initialized"],
            "result": call["result"],
        }
    finally:
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        stderr = process.stderr.read() if process.stderr is not None else ""
        if process.returncode not in (0, None):
            raise RuntimeError(
                f"Hermes companion exited with {process.returncode}: {stderr[-4000:]}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hermes-checkout",
        default="runs/hermes-pinned-validation",
    )
    parser.add_argument("--repository", default=".")
    args = parser.parse_args()
    evidence = validate(Path(args.hermes_checkout), Path(args.repository))
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
