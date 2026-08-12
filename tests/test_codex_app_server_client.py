"""G5 CDX-R1 bounded Codex App Server client tests."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import pytest

from soma.reasoning.codex_app_server import (
    CODEX_PILOT_CLIENT_NAME,
    CodexAppServerClient,
    CodexAppServerError,
    CodexUnexpectedServerRequest,
    StdioCodexTransport,
    canonical_schema_manifest_hash,
    find_turn_by_client_user_message_id,
)


class ScriptedTransport:
    def __init__(self, incoming: list[dict[str, Any]]):
        self.incoming = deque(incoming)
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def receive(self, timeout_seconds: float) -> dict[str, Any]:
        assert timeout_seconds > 0
        if not self.incoming:
            raise TimeoutError("script exhausted")
        return self.incoming.popleft()

    def close(self) -> None:
        self.closed = True


def _initialize_response() -> dict[str, Any]:
    return {
        "id": 1,
        "result": {
            "userAgent": "codex-cli/0.145.0",
            "codexHome": "C:/Users/test/.codex",
            "platformFamily": "windows",
            "platformOs": "windows",
        },
    }


def _output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }


def test_stdio_close_prefers_graceful_eof_exit_before_terminate() -> None:
    class FakeStdin:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()
            self.wait_timeouts: list[float] = []
            self.terminated = False
            self.killed = False
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float) -> int:
            self.wait_timeouts.append(timeout)
            self.returncode = 0
            return 0

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

    class FakeThread:
        def __init__(self) -> None:
            self.join_timeouts: list[float] = []

        def join(self, timeout: float | None = None) -> None:
            assert timeout is not None
            self.join_timeouts.append(timeout)

    transport = object.__new__(StdioCodexTransport)
    transport._closed = False
    transport._process = FakeProcess()
    transport._reader = FakeThread()
    transport._stderr_reader = FakeThread()

    transport.close()

    assert transport._process.stdin.closed is True
    assert transport._process.wait_timeouts == [5]
    assert transport._process.terminated is False
    assert transport._process.killed is False
    assert transport._reader.join_timeouts == [2]
    assert transport._stderr_reader.join_timeouts == [2]


def test_initialize_and_account_read_capture_chatgpt_auth() -> None:
    transport = ScriptedTransport(
        [
            {"method": "configWarning", "params": {"summary": "fixture"}},
            _initialize_response(),
            {
                "id": 2,
                "result": {
                    "account": {
                        "type": "chatgpt",
                        "email": "fixture@example.invalid",
                        "planType": "plus",
                    },
                    "requiresOpenaiAuth": True,
                },
            },
        ]
    )
    client = CodexAppServerClient(transport)

    initialized = client.initialize()
    account = client.account_read()

    assert initialized["userAgent"] == "codex-cli/0.145.0"
    assert account["account"]["type"] == "chatgpt"
    assert transport.sent[0]["method"] == "initialize"
    assert transport.sent[0]["params"]["clientInfo"]["name"] == CODEX_PILOT_CLIENT_NAME
    assert transport.sent[1] == {"method": "initialized", "params": {}}
    assert transport.sent[2] == {
        "method": "account/read",
        "id": 2,
        "params": {"refreshToken": False},
    }
    assert client.notifications == [
        {"method": "configWarning", "params": {"summary": "fixture"}}
    ]


def test_thread_and_turn_requests_are_mechanically_read_only(tmp_path: Path) -> None:
    thread = {
        "id": "thr_fixture",
        "model": "gpt-fixture",
        "status": {"type": "idle"},
        "turns": [],
    }
    turn = {"id": "turn_fixture", "status": "inProgress", "items": [], "error": None}
    transport = ScriptedTransport(
        [
            _initialize_response(),
            {"id": 2, "result": {"thread": thread}},
            {
                "method": "turn/started",
                "params": {"threadId": "thr_fixture", "turn": turn},
            },
            {"id": 3, "result": {"turn": turn}},
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thr_fixture",
                    "turnId": "turn_fixture",
                    "item": {
                        "id": "item_agent",
                        "type": "agentMessage",
                        "text": '{"answer":"ok"}',
                    },
                },
            },
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "thr_fixture",
                    "tokenUsage": {
                        "total": {
                            "inputTokens": 12,
                            "cachedInputTokens": 0,
                            "outputTokens": 5,
                            "reasoningOutputTokens": 2,
                            "totalTokens": 17,
                        }
                    },
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thr_fixture",
                    "turn": {
                        "id": "turn_fixture",
                        "status": "completed",
                        "items": [],
                        "error": None,
                    },
                },
            },
        ]
    )
    client = CodexAppServerClient(transport)
    client.initialize()

    started_thread = client.start_thread(working_directory=str(tmp_path))
    started_turn = client.start_turn(
        thread_id=started_thread["thread"]["id"],
        prompt="synthetic fixture only",
        client_user_message_id="soma-cdx-r1-message-1",
        output_schema=_output_schema(),
        effort="low",
    )
    evidence = client.wait_for_turn_completed(
        thread_id="thr_fixture",
        turn_id=started_turn["turn"]["id"],
        timeout_seconds=10,
    )

    thread_request = transport.sent[2]
    assert thread_request["method"] == "thread/start"
    assert thread_request["params"]["approvalPolicy"] == "never"
    assert thread_request["params"]["sandbox"] == "read-only"
    assert thread_request["params"]["cwd"] == str(tmp_path)

    turn_request = transport.sent[3]
    assert turn_request["method"] == "turn/start"
    assert turn_request["params"]["approvalPolicy"] == "never"
    assert turn_request["params"]["sandboxPolicy"] == {"type": "readOnly"}
    assert turn_request["params"]["clientUserMessageId"] == "soma-cdx-r1-message-1"
    assert turn_request["params"]["outputSchema"] == _output_schema()
    assert turn_request["params"]["effort"] == "low"

    assert evidence.thread_id == "thr_fixture"
    assert evidence.turn_id == "turn_fixture"
    assert evidence.status == "completed"
    assert evidence.agent_message == '{"answer":"ok"}'
    assert len(evidence.token_usage_events) == 1
    assert any(event["method"] == "turn/started" for event in evidence.events)
    assert evidence.events[-1]["method"] == "turn/completed"


def test_wait_for_turn_started_captures_exact_id_before_start_ack() -> None:
    transport = ScriptedTransport(
        [
            _initialize_response(),
            {
                "method": "turn/started",
                "params": {
                    "threadId": "thr_cancel",
                    "turn": {
                        "id": "turn_cancel",
                        "status": "inProgress",
                        "items": [],
                        "error": None,
                    },
                },
            },
            {
                "id": 2,
                "result": {
                    "turn": {
                        "id": "turn_cancel",
                        "status": "inProgress",
                        "items": [],
                        "error": None,
                    }
                },
            },
            {"id": 3, "result": {}},
        ]
    )
    client = CodexAppServerClient(transport)
    client.initialize()

    start_request_id = client.begin_turn(
        thread_id="thr_cancel",
        prompt="fixture",
        client_user_message_id="cancel-message",
        output_schema=_output_schema(),
    )
    turn_id = client.wait_for_turn_started(
        thread_id="thr_cancel",
        timeout_seconds=5,
    )
    interrupted = client.interrupt_turn(
        thread_id="thr_cancel",
        turn_id=turn_id,
    )

    assert start_request_id == 2
    assert turn_id == "turn_cancel"
    assert interrupted == {}
    assert transport.sent[2]["method"] == "turn/start"
    assert transport.sent[3] == {
        "method": "turn/interrupt",
        "id": 3,
        "params": {"threadId": "thr_cancel", "turnId": "turn_cancel"},
    }
    assert client.orphan_responses == [
        {
            "id": 2,
            "result": {
                "turn": {
                    "id": "turn_cancel",
                    "status": "inProgress",
                    "items": [],
                    "error": None,
                }
            },
        }
    ]


def test_exact_resume_read_fork_and_interrupt_never_use_fuzzy_identity() -> None:
    transport = ScriptedTransport(
        [
            _initialize_response(),
            {"id": 2, "result": {"thread": {"id": "thr_root", "turns": []}}},
            {"id": 3, "result": {"thread": {"id": "thr_root", "turns": []}}},
            {
                "id": 4,
                "result": {
                    "thread": {
                        "id": "thr_fork",
                        "forkedFromId": "thr_root",
                        "turns": [],
                    }
                },
            },
            {"id": 5, "result": {}},
        ]
    )
    client = CodexAppServerClient(transport)
    client.initialize()

    client.resume_thread("thr_root")
    client.read_thread("thr_root", include_turns=True)
    fork = client.fork_thread("thr_root", last_turn_id="turn_1")
    client.interrupt_turn(thread_id="thr_root", turn_id="turn_2")

    assert fork["thread"]["forkedFromId"] == "thr_root"
    assert transport.sent[2] == {
        "method": "thread/resume",
        "id": 2,
        "params": {"threadId": "thr_root"},
    }
    assert transport.sent[3] == {
        "method": "thread/read",
        "id": 3,
        "params": {"threadId": "thr_root", "includeTurns": True},
    }
    assert transport.sent[4] == {
        "method": "thread/fork",
        "id": 4,
        "params": {"threadId": "thr_root", "lastTurnId": "turn_1"},
    }
    assert transport.sent[5] == {
        "method": "turn/interrupt",
        "id": 5,
        "params": {"threadId": "thr_root", "turnId": "turn_2"},
    }
    wire = json.dumps(transport.sent)
    assert "resume-last" not in wire
    assert '"last"' not in wire


def test_provider_approval_request_is_declined_before_request_completes() -> None:
    transport = ScriptedTransport(
        [
            _initialize_response(),
            {
                "method": "item/commandExecution/requestApproval",
                "id": 99,
                "params": {
                    "threadId": "thr_1",
                    "turnId": "turn_1",
                    "itemId": "item_1",
                },
            },
            {"id": 2, "result": {"account": None, "requiresOpenaiAuth": True}},
        ]
    )
    client = CodexAppServerClient(transport)
    client.initialize()

    client.account_read()

    assert client.server_requests[0]["id"] == 99
    assert transport.sent[3] == {"id": 99, "result": {"decision": "decline"}}


def test_unknown_server_request_fails_closed_and_returns_protocol_error() -> None:
    transport = ScriptedTransport(
        [
            _initialize_response(),
            {
                "method": "some/future/request",
                "id": 77,
                "params": {"opaque": True},
            },
        ]
    )
    client = CodexAppServerClient(transport)
    client.initialize()

    with pytest.raises(CodexUnexpectedServerRequest, match="future"):
        client.account_read()

    assert transport.sent[-1] == {
        "id": 77,
        "error": {
            "code": -32099,
            "message": "Soma CDX-R1 read-only pilot does not service this request",
        },
    }


def test_turn_wait_uses_bounded_transport_timeout() -> None:
    transport = ScriptedTransport(
        [
            _initialize_response(),
            {
                "id": 2,
                "result": {
                    "thread": {"id": "thr_timeout", "turns": []},
                },
            },
            {
                "id": 3,
                "result": {
                    "turn": {
                        "id": "turn_timeout",
                        "status": "inProgress",
                        "items": [],
                        "error": None,
                    }
                },
            },
        ]
    )
    client = CodexAppServerClient(transport)
    client.initialize()
    client.resume_thread("thr_timeout")
    client.start_turn(
        thread_id="thr_timeout",
        prompt="fixture",
        client_user_message_id="timeout-message",
        output_schema=_output_schema(),
    )

    with pytest.raises(TimeoutError, match="script exhausted"):
        client.wait_for_turn_completed(
            thread_id="thr_timeout",
            turn_id="turn_timeout",
            timeout_seconds=1,
        )


def test_canonical_schema_manifest_hash_ignores_object_key_order(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "nested").mkdir(parents=True)
    (second / "nested").mkdir(parents=True)

    (first / "root.json").write_text(
        '{"type":"object","properties":{"b":{"type":"string"},"a":{"type":"integer"}}}',
        encoding="utf-8",
    )
    (second / "root.json").write_text(
        '{"properties":{"a":{"type":"integer"},"b":{"type":"string"}},"type":"object"}',
        encoding="utf-8",
    )
    (first / "nested" / "item.json").write_text('{"z":1,"a":[3,2,1]}', encoding="utf-8")
    (second / "nested" / "item.json").write_text(
        '{\n  "a": [3, 2, 1],\n  "z": 1\n}', encoding="utf-8"
    )

    first_hash, first_count = canonical_schema_manifest_hash(first)
    second_hash, second_count = canonical_schema_manifest_hash(second)

    assert first_count == second_count == 2
    assert first_hash == second_hash


def test_begin_turn_crosses_send_boundary_once_and_await_never_resends() -> None:
    transport = ScriptedTransport(
        [
            _initialize_response(),
            {
                "id": 2,
                "result": {
                    "turn": {
                        "id": "turn_boundary",
                        "status": "inProgress",
                        "items": [],
                        "error": None,
                    }
                },
            },
        ]
    )
    client = CodexAppServerClient(transport)
    client.initialize()

    request_id = client.begin_turn(
        thread_id="thr_boundary",
        prompt="fixture",
        client_user_message_id="client-boundary-1",
        output_schema=_output_schema(),
        model="gpt-5.6-luna",
        effort="low",
    )
    sent_after_begin = list(transport.sent)
    response = client.await_response(request_id, "turn/start")

    assert request_id == 2
    assert response["turn"]["id"] == "turn_boundary"
    assert transport.sent == sent_after_begin
    turn_requests = [
        item for item in transport.sent if item.get("method") == "turn/start"
    ]
    assert len(turn_requests) == 1
    assert turn_requests[0]["params"]["clientUserMessageId"] == "client-boundary-1"


def test_lost_ack_reconciliation_finds_exact_persisted_turn_by_client_id() -> None:
    thread = {
        "id": "thr_recovery",
        "turns": [
            {
                "id": "turn_old",
                "items": [
                    {
                        "id": "user_old",
                        "type": "userMessage",
                        "clientId": "other-client-id",
                        "content": [],
                    }
                ],
            },
            {
                "id": "turn_recovered",
                "items": [
                    {
                        "id": "user_recovered",
                        "type": "userMessage",
                        "clientId": "soma-lost-ack-1",
                        "content": [],
                    },
                    {"id": "agent_1", "type": "agentMessage", "text": "done"},
                ],
            },
        ],
    }

    assert (
        find_turn_by_client_user_message_id(thread, "soma-lost-ack-1")
        == "turn_recovered"
    )
    assert find_turn_by_client_user_message_id(thread, "missing-client") is None


def test_lost_ack_reconciliation_refuses_duplicate_client_id_across_turns() -> None:
    thread = {
        "id": "thr_conflict",
        "turns": [
            {
                "id": "turn_a",
                "items": [
                    {
                        "type": "userMessage",
                        "clientId": "duplicate-client",
                        "content": [],
                    }
                ],
            },
            {
                "id": "turn_b",
                "items": [
                    {
                        "type": "userMessage",
                        "clientId": "duplicate-client",
                        "content": [],
                    }
                ],
            },
        ],
    }

    with pytest.raises(CodexAppServerError, match="multiple turn IDs"):
        find_turn_by_client_user_message_id(thread, "duplicate-client")


def test_canonical_schema_manifest_requires_json_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no JSON"):
        canonical_schema_manifest_hash(tmp_path)
