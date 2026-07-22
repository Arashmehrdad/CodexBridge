from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from soma.local_agent.models import LocalModelStatus
from soma.local_agent.ollama_adapter import OllamaChatAdapter


class FakeResponse:
    def __init__(self, payload: dict[str, Any] | str, status: int = 200):
        self.status = status
        self.payload = payload

    def read(self) -> bytes:
        if isinstance(self.payload, str):
            return self.payload.encode("utf-8")
        return json.dumps(self.payload).encode("utf-8")


def success_payload(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


def test_adapter_builds_openai_compatible_request() -> None:
    captured: dict[str, Any] = {}

    def transport(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(success_payload("summary"))

    result = OllamaChatAdapter(model="llama3.2", transport=transport).call(
        task_type="summarize_log",
        messages=[{"role": "user", "content": "pytest output"}],
    )

    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["timeout"] == 30
    assert captured["method"] == "POST"
    assert captured["body"]["model"] == "llama3.2"
    assert captured["body"]["messages"] == [
        {"role": "user", "content": "pytest output"}
    ]
    assert captured["body"]["stream"] is False
    assert result.status == LocalModelStatus.SUCCESS
    assert result.content == "summary"


def test_default_base_url_is_ollama_openai_compatible() -> None:
    adapter = OllamaChatAdapter()

    assert adapter.base_url == "http://localhost:11434/v1"


def test_connection_failure_returns_unavailable() -> None:
    def transport(request: urllib.request.Request, timeout: int) -> FakeResponse:
        raise urllib.error.URLError("connection refused")

    result = OllamaChatAdapter(transport=transport).call(
        task_type="classify_error", messages=[{"role": "user", "content": "err"}]
    )

    assert result.status == LocalModelStatus.UNAVAILABLE
    assert result.error


def test_timeout_returns_timeout() -> None:
    def transport(request: urllib.request.Request, timeout: int) -> FakeResponse:
        raise urllib.error.URLError(socket.timeout("timed out"))

    result = OllamaChatAdapter(transport=transport).call(
        task_type="classify_error", messages=[{"role": "user", "content": "err"}]
    )

    assert result.status == LocalModelStatus.TIMEOUT


def test_non_2xx_response_returns_failed() -> None:
    result = OllamaChatAdapter(
        transport=lambda request, timeout: FakeResponse("bad gateway", status=502)
    ).call(
        task_type="summarize_log",
        messages=[{"role": "user", "content": "log"}],
    )

    assert result.status == LocalModelStatus.FAILED
    assert "502" in result.error


def test_malformed_response_returns_failed() -> None:
    result = OllamaChatAdapter(
        transport=lambda request, timeout: FakeResponse({"choices": []})
    ).call(
        task_type="summarize_log",
        messages=[{"role": "user", "content": "log"}],
    )

    assert result.status == LocalModelStatus.FAILED
    assert "Malformed" in result.error


def test_json_mode_success_returns_parsed_json() -> None:
    captured: dict[str, Any] = {}

    def transport(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(success_payload('{"category":"test_failure"}'))

    result = OllamaChatAdapter(transport=transport).call_json(
        task_type="classify_error",
        messages=[{"role": "user", "content": "failure"}],
    )

    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert result.status == LocalModelStatus.SUCCESS
    assert result.parsed_json == {"category": "test_failure"}


def test_json_mode_invalid_json_returns_invalid_json() -> None:
    result = OllamaChatAdapter(
        transport=lambda request, timeout: FakeResponse(success_payload("not json"))
    ).call_json(
        task_type="classify_error",
        messages=[{"role": "user", "content": "failure"}],
    )

    assert result.status == LocalModelStatus.INVALID_JSON
    assert result.parsed_json is None
