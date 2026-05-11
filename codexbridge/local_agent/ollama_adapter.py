from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from codexbridge.run_store import utc_now

from .audit import create_audit_event
from .models import LocalModelMessage, LocalModelRequest, LocalModelResult, LocalModelStatus


Transport = Callable[[urllib.request.Request, int], Any]


class OllamaChatAdapter:
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3.2",
        timeout_seconds: int = 30,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        transport: Transport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.transport = transport or _urlopen

    def call(
        self,
        *,
        task_type: str,
        messages: list[dict[str, str] | LocalModelMessage],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_seconds: int | None = None,
        json_mode: bool = False,
    ) -> LocalModelResult:
        request = LocalModelRequest(
            task_type=task_type,
            model=model or self.model,
            base_url=self.base_url,
            messages=[message if isinstance(message, LocalModelMessage) else LocalModelMessage(**message) for message in messages],
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
            timeout_seconds=self.timeout_seconds if timeout_seconds is None else timeout_seconds,
            response_format={"type": "json_object"} if json_mode else None,
            json_mode=json_mode,
        )
        return self._send(request, parse_json=json_mode)

    def call_json(self, **kwargs: Any) -> LocalModelResult:
        kwargs["json_mode"] = True
        return self.call(**kwargs)

    def _send(self, request: LocalModelRequest, *, parse_json: bool) -> LocalModelResult:
        created_at = utc_now()
        started = time.monotonic()
        audit_started = create_audit_event(
            task_id=request.request_id,
            action="local_model_request_started",
            message="Local model request started",
            metadata={"model": request.model, "task_type": request.task_type},
        )
        body = {
            "model": request.model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.response_format:
            body["response_format"] = request.response_format

        http_request = urllib.request.Request(
            f"{request.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        status = LocalModelStatus.SUCCESS
        content = ""
        parsed_json: Any | None = None
        error = ""
        try:
            response = self.transport(http_request, request.timeout_seconds)
            status_code = int(getattr(response, "status", getattr(response, "code", 200)))
            raw_body = response.read().decode("utf-8")
            if status_code < 200 or status_code >= 300:
                status = LocalModelStatus.FAILED
                error = f"Local model HTTP status {status_code}: {_safe_error(raw_body)}"
            else:
                payload = json.loads(raw_body)
                content = str(payload["choices"][0]["message"]["content"])
                if parse_json:
                    try:
                        parsed_json = json.loads(content)
                    except json.JSONDecodeError as exc:
                        status = LocalModelStatus.INVALID_JSON
                        error = f"Local model returned invalid JSON: {exc.msg}"
        except urllib.error.HTTPError as exc:
            status = LocalModelStatus.FAILED
            error = f"Local model HTTP status {exc.code}: {_safe_error(_read_error_body(exc))}"
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout)):
                status = LocalModelStatus.TIMEOUT
            else:
                status = LocalModelStatus.UNAVAILABLE
            error = _safe_error(str(exc))
        except TimeoutError as exc:
            status = LocalModelStatus.TIMEOUT
            error = _safe_error(str(exc))
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            status = LocalModelStatus.FAILED
            error = f"Malformed local model response: {_safe_error(str(exc))}"

        duration = time.monotonic() - started
        audit_completed = create_audit_event(
            task_id=request.request_id,
            action="local_model_request_completed",
            message=f"Local model request completed with status: {status.value}",
            metadata={"model": request.model, "task_type": request.task_type, "duration_seconds": duration, "status": status.value},
        )
        audit_event_id = audit_completed.event_id if audit_started else audit_completed.event_id
        return LocalModelResult(
            request_id=request.request_id,
            task_type=request.task_type,
            model=request.model,
            base_url=request.base_url,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
            response_format=request.response_format,
            json_mode=request.json_mode,
            status=status,
            content=content,
            parsed_json=parsed_json,
            error=error,
            duration_seconds=duration,
            audit_event_id=audit_event_id,
            created_at=created_at,
        )


def _urlopen(request: urllib.request.Request, timeout_seconds: int) -> Any:
    return urllib.request.urlopen(request, timeout=timeout_seconds)


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")
    except Exception:
        return ""


def _safe_error(text: str) -> str:
    return text[:500]
