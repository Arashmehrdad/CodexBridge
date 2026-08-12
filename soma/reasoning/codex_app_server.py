"""Bounded Codex App Server client for the G5 CLI provider lane.

This module speaks the documented ``codex app-server --stdio`` JSONL protocol.
It does not own canonical Task state and it does not grant Codex mutation
authority. The first real pilot runs with a read-only sandbox, synthetic input,
and explicit provider identity capture.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


CODEX_APP_SERVER_PROTOCOL = "codex.app_server.jsonl"
CODEX_PILOT_CLIENT_NAME = "soma-cdx-r1"
CODEX_PILOT_CLIENT_VERSION = "0.1.0"


class CodexAppServerError(RuntimeError):
    """Base error for the bounded App Server client."""


class CodexAppServerTransportError(CodexAppServerError):
    """The stdio transport failed or closed unexpectedly."""


class CodexAppServerRpcError(CodexAppServerError):
    """App Server returned a JSON-RPC error for one request."""

    def __init__(self, method: str, error: Any):
        super().__init__(f"Codex App Server request {method!r} failed: {error!r}")
        self.method = method
        self.error = error


class CodexUnexpectedServerRequest(CodexAppServerError):
    """The read-only pilot received an unsupported server-initiated request."""


class CodexMessageTransport(Protocol):
    """Tiny transport contract so protocol behavior can be tested without Codex."""

    def send(self, message: dict[str, Any]) -> None: ...

    def receive(self, timeout_seconds: float) -> dict[str, Any]: ...

    def close(self) -> None: ...


class StdioCodexTransport:
    """Newline-delimited JSON transport over one local Codex App Server process."""

    def __init__(
        self,
        *,
        codex_executable: str,
        working_directory: str,
        stderr_history: int = 100,
    ) -> None:
        executable = Path(codex_executable)
        if not executable.is_absolute():
            raise ValueError("codex_executable must be an absolute path")
        cwd = Path(working_directory)
        if not cwd.is_absolute():
            raise ValueError("working_directory must be an absolute path")

        argv = self._launch_argv(executable)
        self._process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise CodexAppServerTransportError("Codex stdio pipes were not created")

        self._messages: queue.Queue[dict[str, Any] | BaseException] = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=max(1, stderr_history))
        self._closed = False
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_reader.start()

    @staticmethod
    def _launch_argv(executable: Path) -> list[str]:
        suffix = executable.suffix.lower()
        if os.name == "nt" and suffix in {".cmd", ".bat"}:
            comspec = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
            return [comspec, "/d", "/s", "/c", str(executable), "app-server", "--stdio"]
        return [str(executable), "app-server", "--stdio"]

    def _read_stdout(self) -> None:
        stdout = self._process.stdout
        assert stdout is not None
        try:
            for line in stdout:
                text = line.strip()
                if not text:
                    continue
                try:
                    message = json.loads(text)
                except json.JSONDecodeError as exc:
                    self._messages.put(
                        CodexAppServerTransportError(
                            f"Codex emitted non-JSON stdout: {text[:256]!r}: {exc}"
                        )
                    )
                    return
                if not isinstance(message, dict):
                    self._messages.put(
                        CodexAppServerTransportError(
                            "Codex emitted a non-object JSONL protocol message"
                        )
                    )
                    return
                self._messages.put(message)
        except BaseException as exc:  # pragma: no cover - OS pipe failure
            self._messages.put(CodexAppServerTransportError(str(exc)))

    def _read_stderr(self) -> None:
        stderr = self._process.stderr
        if stderr is None:
            return
        try:
            for line in stderr:
                self._stderr.append(line.rstrip("\r\n"))
        except OSError:
            return

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        return tuple(self._stderr)

    def send(self, message: dict[str, Any]) -> None:
        if self._closed:
            raise CodexAppServerTransportError("Codex transport is closed")
        stdin = self._process.stdin
        assert stdin is not None
        payload = json.dumps(
            message,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        try:
            stdin.write(payload + "\n")
            stdin.flush()
        except OSError as exc:
            raise CodexAppServerTransportError(
                f"Codex stdin write failed: {exc}"
            ) from exc

    def receive(self, timeout_seconds: float) -> dict[str, Any]:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        try:
            item = self._messages.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            if self._process.poll() is not None:
                detail = " | ".join(self.stderr_tail[-5:])
                raise CodexAppServerTransportError(
                    f"Codex App Server exited with {self._process.returncode}; {detail}"
                ) from exc
            raise TimeoutError(
                "Timed out waiting for Codex App Server message"
            ) from exc
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._process.stdin is not None:
                self._process.stdin.close()
        except OSError:
            pass

        # Codex is commonly launched through the npm ``codex.cmd`` wrapper on
        # Windows. Closing stdin is the protocol-level shutdown signal for the
        # App Server child. Terminating the wrapper immediately can orphan that
        # child while it still owns the working directory, so give EOF-driven
        # shutdown a bounded grace period before escalating.
        if self._process.poll() is None:
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=2)

        self._reader.join(timeout=2)
        self._stderr_reader.join(timeout=2)


@dataclass(frozen=True)
class CodexTurnEvidence:
    thread_id: str
    turn_id: str
    status: str
    events: tuple[dict[str, Any], ...]
    agent_message: str
    token_usage_events: tuple[dict[str, Any], ...]
    terminal_error: Any | None = None


class CodexAppServerClient:
    """Synchronous bounded client with exact-id request and notification capture."""

    def __init__(
        self,
        transport: CodexMessageTransport,
        *,
        request_timeout_seconds: float = 30.0,
    ) -> None:
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        self.transport = transport
        self.request_timeout_seconds = request_timeout_seconds
        self.notifications: list[dict[str, Any]] = []
        self.server_requests: list[dict[str, Any]] = []
        self.orphan_responses: list[dict[str, Any]] = []
        self._next_request_id = 1
        self._initialized = False

    def __enter__(self) -> "CodexAppServerClient":
        self.initialize()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def close(self) -> None:
        self.transport.close()

    def initialize(self, *, experimental_api: bool = False) -> dict[str, Any]:
        if self._initialized:
            raise CodexAppServerError("Codex App Server client is already initialized")
        params: dict[str, Any] = {
            "clientInfo": {
                "name": CODEX_PILOT_CLIENT_NAME,
                "title": "Soma CDX-R1",
                "version": CODEX_PILOT_CLIENT_VERSION,
            }
        }
        if experimental_api:
            params["capabilities"] = {"experimentalApi": True}
        request_id = self._begin_request_core("initialize", params)
        result = self._await_response_core(request_id, "initialize")
        self.transport.send({"method": "initialized", "params": {}})
        self._initialized = True
        return result

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        request_id = self.begin_request(method, params or {})
        return self.await_response(
            request_id,
            method,
            timeout_seconds=timeout_seconds,
        )

    def begin_request(self, method: str, params: dict[str, Any] | None = None) -> int:
        """Cross the provider-send boundary exactly once and return its request ID."""

        if not self._initialized:
            raise CodexAppServerError("Codex App Server client is not initialized")
        return self._begin_request_core(method, params or {})

    def await_response(
        self,
        request_id: int,
        method: str,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Await an already-sent request without sending any replacement request."""

        if not self._initialized:
            raise CodexAppServerError("Codex App Server client is not initialized")
        return self._await_response_core(
            request_id,
            method,
            timeout_seconds=timeout_seconds,
        )

    def _begin_request_core(self, method: str, params: dict[str, Any]) -> int:
        if not method:
            raise ValueError("method is required")
        request_id = self._next_request_id
        self._next_request_id += 1
        self.transport.send({"method": method, "id": request_id, "params": params})
        return request_id

    def _await_response_core(
        self,
        request_id: int,
        method: str,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        timeout = timeout_seconds or self.request_timeout_seconds
        while True:
            message = self.transport.receive(timeout)
            if self._handle_server_message(message):
                continue
            if message.get("id") != request_id:
                self.orphan_responses.append(message)
                continue
            if "error" in message:
                raise CodexAppServerRpcError(method, message.get("error"))
            result = message.get("result")
            if not isinstance(result, dict):
                raise CodexAppServerTransportError(
                    f"Codex response for {method!r} has no object result"
                )
            return result

    def _handle_server_message(self, message: dict[str, Any]) -> bool:
        method = message.get("method")
        if not isinstance(method, str):
            return False
        if "id" not in message:
            self.notifications.append(message)
            return True

        self.server_requests.append(message)
        request_id = message["id"]
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            self.transport.send({"id": request_id, "result": {"decision": "decline"}})
            return True
        if method == "mcpServer/elicitation/request":
            self.transport.send(
                {
                    "id": request_id,
                    "result": {"action": "decline", "content": None},
                }
            )
            return True

        self.transport.send(
            {
                "id": request_id,
                "error": {
                    "code": -32099,
                    "message": "Soma CDX-R1 read-only pilot does not service this request",
                },
            }
        )
        raise CodexUnexpectedServerRequest(
            f"Unexpected Codex server request during read-only pilot: {method}"
        )

    def _receive_notification(self, timeout_seconds: float) -> dict[str, Any]:
        while True:
            message = self.transport.receive(timeout_seconds)
            if self._handle_server_message(message):
                if "id" not in message and isinstance(message.get("method"), str):
                    return message
                continue
            self.orphan_responses.append(message)

    def account_read(self) -> dict[str, Any]:
        return self.request("account/read", {"refreshToken": False})

    def rate_limits_read(self) -> dict[str, Any]:
        return self.request("account/rateLimits/read", {})

    def model_list(self, *, include_hidden: bool = False) -> dict[str, Any]:
        return self.request("model/list", {"includeHidden": include_hidden})

    def start_thread(
        self,
        *,
        working_directory: str,
        model: str = "",
    ) -> dict[str, Any]:
        cwd = Path(working_directory)
        if not cwd.is_absolute():
            raise ValueError("working_directory must be absolute")
        params: dict[str, Any] = {
            "cwd": str(cwd),
            "approvalPolicy": "never",
            "sandbox": "read-only",
        }
        if model:
            params["model"] = model
        return self.request("thread/start", params)

    def resume_thread(self, thread_id: str) -> dict[str, Any]:
        if not thread_id:
            raise ValueError("thread_id is required")
        return self.request("thread/resume", {"threadId": thread_id})

    def read_thread(
        self, thread_id: str, *, include_turns: bool = True
    ) -> dict[str, Any]:
        if not thread_id:
            raise ValueError("thread_id is required")
        return self.request(
            "thread/read",
            {"threadId": thread_id, "includeTurns": include_turns},
        )

    def fork_thread(self, thread_id: str, *, last_turn_id: str = "") -> dict[str, Any]:
        if not thread_id:
            raise ValueError("thread_id is required")
        params: dict[str, Any] = {"threadId": thread_id}
        if last_turn_id:
            params["lastTurnId"] = last_turn_id
        return self.request("thread/fork", params)

    @staticmethod
    def turn_start_params(
        *,
        thread_id: str,
        prompt: str,
        client_user_message_id: str,
        output_schema: dict[str, Any],
        model: str = "",
        effort: str = "",
    ) -> dict[str, Any]:
        if not thread_id:
            raise ValueError("thread_id is required")
        if not prompt:
            raise ValueError("prompt is required")
        if not client_user_message_id:
            raise ValueError("client_user_message_id is required")
        params: dict[str, Any] = {
            "threadId": thread_id,
            "clientUserMessageId": client_user_message_id,
            "input": [{"type": "text", "text": prompt}],
            "approvalPolicy": "never",
            "sandboxPolicy": {"type": "readOnly"},
            "outputSchema": output_schema,
        }
        if model:
            params["model"] = model
        if effort:
            params["effort"] = effort
        return params

    def begin_turn(
        self,
        *,
        thread_id: str,
        prompt: str,
        client_user_message_id: str,
        output_schema: dict[str, Any],
        model: str = "",
        effort: str = "",
    ) -> int:
        """Send exactly one turn/start request without awaiting its acknowledgement."""

        params = self.turn_start_params(
            thread_id=thread_id,
            prompt=prompt,
            client_user_message_id=client_user_message_id,
            output_schema=output_schema,
            model=model,
            effort=effort,
        )
        return self.begin_request("turn/start", params)

    def start_turn(
        self,
        *,
        thread_id: str,
        prompt: str,
        client_user_message_id: str,
        output_schema: dict[str, Any],
        model: str = "",
        effort: str = "",
    ) -> dict[str, Any]:
        request_id = self.begin_turn(
            thread_id=thread_id,
            prompt=prompt,
            client_user_message_id=client_user_message_id,
            output_schema=output_schema,
            model=model,
            effort=effort,
        )
        return self.await_response(request_id, "turn/start")

    def wait_for_turn_started(
        self,
        *,
        thread_id: str,
        timeout_seconds: float,
    ) -> str:
        """Capture the exact provider turn ID as soon as ``turn/started`` arrives."""

        if not thread_id:
            raise ValueError("thread_id is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        deadline = time.monotonic() + timeout_seconds

        for notification in self.notifications:
            turn_id = self._started_turn_id(notification, thread_id)
            if turn_id:
                return turn_id

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for Codex thread {thread_id!r} to start a turn"
                )
            notification = self._receive_notification(remaining)
            turn_id = self._started_turn_id(notification, thread_id)
            if turn_id:
                return turn_id

    @staticmethod
    def _started_turn_id(notification: dict[str, Any], thread_id: str) -> str:
        if notification.get("method") != "turn/started":
            return ""
        params = notification.get("params")
        if not isinstance(params, dict) or params.get("threadId") != thread_id:
            return ""
        turn = params.get("turn")
        if not isinstance(turn, dict):
            return ""
        turn_id = turn.get("id")
        return turn_id if isinstance(turn_id, str) else ""

    def interrupt_turn(self, *, thread_id: str, turn_id: str) -> dict[str, Any]:
        if not thread_id or not turn_id:
            raise ValueError("thread_id and turn_id are required")
        return self.request(
            "turn/interrupt",
            {"threadId": thread_id, "turnId": turn_id},
        )

    def wait_for_turn_completed(
        self,
        *,
        thread_id: str,
        turn_id: str,
        timeout_seconds: float,
    ) -> CodexTurnEvidence:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        deadline = time.monotonic() + timeout_seconds

        observed: list[dict[str, Any]] = []
        usage_events: list[dict[str, Any]] = []
        agent_message = ""

        for notification in self.notifications:
            if self._notification_matches_thread(notification, thread_id):
                observed.append(notification)
                self._capture_turn_material(
                    notification,
                    usage_events=usage_events,
                    agent_message_holder=[agent_message],
                )
                candidate = self._agent_message(notification)
                if candidate:
                    agent_message = candidate
                completed = self._completed_turn(notification, thread_id, turn_id)
                if completed is not None:
                    return CodexTurnEvidence(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        status=str(completed.get("status") or ""),
                        events=tuple(observed),
                        agent_message=agent_message,
                        token_usage_events=tuple(usage_events),
                        terminal_error=completed.get("error"),
                    )

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for Codex turn {turn_id!r} to complete"
                )
            notification = self._receive_notification(remaining)
            if not self._notification_matches_thread(notification, thread_id):
                continue
            observed.append(notification)
            params = notification.get("params")
            if notification.get("method") == "thread/tokenUsage/updated" and isinstance(
                params, dict
            ):
                usage_events.append(dict(params))
            candidate = self._agent_message(notification)
            if candidate:
                agent_message = candidate
            completed = self._completed_turn(notification, thread_id, turn_id)
            if completed is None:
                continue
            return CodexTurnEvidence(
                thread_id=thread_id,
                turn_id=turn_id,
                status=str(completed.get("status") or ""),
                events=tuple(observed),
                agent_message=agent_message,
                token_usage_events=tuple(usage_events),
                terminal_error=completed.get("error"),
            )

    @staticmethod
    def _notification_matches_thread(
        notification: dict[str, Any], thread_id: str
    ) -> bool:
        params = notification.get("params")
        if not isinstance(params, dict):
            return False
        candidate = params.get("threadId")
        if candidate == thread_id:
            return True
        thread = params.get("thread")
        return isinstance(thread, dict) and thread.get("id") == thread_id

    @staticmethod
    def _completed_turn(
        notification: dict[str, Any], thread_id: str, turn_id: str
    ) -> dict[str, Any] | None:
        if notification.get("method") != "turn/completed":
            return None
        params = notification.get("params")
        if not isinstance(params, dict) or params.get("threadId") != thread_id:
            return None
        turn = params.get("turn")
        if not isinstance(turn, dict) or turn.get("id") != turn_id:
            return None
        return turn

    @staticmethod
    def _agent_message(notification: dict[str, Any]) -> str:
        if notification.get("method") != "item/completed":
            return ""
        params = notification.get("params")
        if not isinstance(params, dict):
            return ""
        item = params.get("item")
        if not isinstance(item, dict) or item.get("type") != "agentMessage":
            return ""
        text = item.get("text")
        return text if isinstance(text, str) else ""

    @staticmethod
    def _capture_turn_material(
        notification: dict[str, Any],
        *,
        usage_events: list[dict[str, Any]],
        agent_message_holder: list[str],
    ) -> None:
        params = notification.get("params")
        if notification.get("method") == "thread/tokenUsage/updated" and isinstance(
            params, dict
        ):
            usage_events.append(dict(params))
        candidate = CodexAppServerClient._agent_message(notification)
        if candidate:
            agent_message_holder[0] = candidate


def find_turn_by_client_user_message_id(
    thread: dict[str, Any],
    client_user_message_id: str,
) -> str | None:
    """Resolve one persisted turn by the exact echoed user-message client ID.

    App Server persists ``clientUserMessageId`` as ``userMessage.clientId``.
    Zero matches remain uncertain. Multiple matching turn IDs are a protocol
    conflict and must never be resolved by timestamps or caller preference.
    """

    if not client_user_message_id:
        raise ValueError("client_user_message_id is required")
    turns = thread.get("turns")
    if not isinstance(turns, list):
        return None

    matches: set[str] = set()
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        turn_id = turn.get("id")
        items = turn.get("items")
        if not isinstance(turn_id, str) or not turn_id or not isinstance(items, list):
            continue
        for item in items:
            if (
                isinstance(item, dict)
                and item.get("type") == "userMessage"
                and item.get("clientId") == client_user_message_id
            ):
                matches.add(turn_id)
                break

    if len(matches) > 1:
        raise CodexAppServerError(
            "Codex persisted one clientUserMessageId under multiple turn IDs: "
            + ", ".join(sorted(matches))
        )
    return next(iter(matches)) if matches else None


def resolve_codex_executable() -> str:
    """Resolve Codex without relying on a shell alias at execution time."""

    candidates = (
        shutil.which("codex.cmd"),
        shutil.which("codex.exe"),
        shutil.which("codex"),
    )
    for candidate in candidates:
        if candidate:
            resolved = str(Path(candidate).resolve())
            if Path(resolved).is_absolute():
                return resolved
    raise CodexAppServerTransportError("Codex executable is not available on PATH")


def canonical_schema_manifest_hash(schema_root: Path) -> tuple[str, int]:
    """Hash generated App Server JSON schemas independent of object-key ordering."""

    root = Path(schema_root)
    if not root.is_dir():
        raise ValueError("schema_root must be a directory")
    pairs: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        canonical = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        pairs.append(
            (
                path.relative_to(root).as_posix(),
                hashlib.sha256(canonical).hexdigest(),
            )
        )
    if not pairs:
        raise ValueError("schema_root contains no JSON schema files")
    manifest = "".join(f"{name}={digest}\n" for name, digest in pairs).encode("utf-8")
    return hashlib.sha256(manifest).hexdigest(), len(pairs)
