from __future__ import annotations

from typing import Any

from codexbridge.config import LocalModelConfig
from codexbridge.run_store import utc_now

from .models import LocalModelResult, LocalModelStatus
from .ollama_adapter import OllamaChatAdapter, Transport


class LocalModelClient:
    def __init__(self, config: LocalModelConfig | None = None, adapter: OllamaChatAdapter | None = None):
        self.config = config or LocalModelConfig()
        self.adapter = adapter or OllamaChatAdapter(
            base_url=self.config.base_url,
            model=self.config.model,
            timeout_seconds=self.config.timeout_seconds,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    @classmethod
    def enabled_with_transport(cls, *, config: LocalModelConfig | None = None, transport: Transport) -> "LocalModelClient":
        effective = config or LocalModelConfig(enabled=True)
        adapter = OllamaChatAdapter(
            base_url=effective.base_url,
            model=effective.model,
            timeout_seconds=effective.timeout_seconds,
            temperature=effective.temperature,
            max_tokens=effective.max_tokens,
            transport=transport,
        )
        return cls(config=effective, adapter=adapter)

    def summarize_log(self, text: str, **overrides: Any) -> LocalModelResult:
        return self._call("summarize_log", "Summarize this log output for an engineer. Focus on failures and next checks.", text, **overrides)

    def classify_error(self, text: str, **overrides: Any) -> LocalModelResult:
        return self._call("classify_error", "Classify this error. Return the likely category, cause, and useful next diagnostic step.", text, **overrides)

    def compress_context(self, text: str, **overrides: Any) -> LocalModelResult:
        return self._call("compress_context", "Compress this context while preserving facts, constraints, commands run, and open questions.", text, **overrides)

    def explain_test_failure(self, text: str, **overrides: Any) -> LocalModelResult:
        return self._call("explain_test_failure", "Explain this test failure concisely. Include likely cause and next local check.", text, **overrides)

    def draft_codex_prompt(self, context: str, **overrides: Any) -> LocalModelResult:
        return self._call(
            "draft_codex_prompt",
            "Draft a compact prompt packet for a future Codex coding task. Do not claim to run Codex or edit files.",
            context,
            **overrides,
        )

    def decide_whether_codex_needed(self, context: str, **overrides: Any) -> LocalModelResult:
        return self._call(
            "decide_whether_codex_needed",
            "Decide whether this task likely needs Codex later. Return reasoning only; do not route or execute anything.",
            context,
            **overrides,
        )

    def summarize_log_json(self, text: str, **overrides: Any) -> LocalModelResult:
        return self._call_json("summarize_log", "Return JSON with keys summary, likely_cause, next_steps.", text, **overrides)

    def classify_error_json(self, text: str, **overrides: Any) -> LocalModelResult:
        return self._call_json("classify_error", "Return JSON with keys category, likely_cause, next_step.", text, **overrides)

    def call_json(self, *, task_type: str, system_prompt: str, text: str, **overrides: Any) -> LocalModelResult:
        return self._call_json(task_type, system_prompt, text, **overrides)

    def _call(self, task_type: str, system_prompt: str, text: str, **overrides: Any) -> LocalModelResult:
        if not self.config.enabled:
            return _blocked_result(task_type, self.config, "Local model is disabled.")
        return self.adapter.call(task_type=task_type, messages=_messages(system_prompt, text), **overrides)

    def _call_json(self, task_type: str, system_prompt: str, text: str, **overrides: Any) -> LocalModelResult:
        if not self.config.enabled:
            return _blocked_result(task_type, self.config, "Local model is disabled.")
        return self.adapter.call_json(task_type=task_type, messages=_messages(system_prompt, text), **overrides)


def _messages(system_prompt: str, text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]


def _blocked_result(task_type: str, config: LocalModelConfig, error: str) -> LocalModelResult:
    return LocalModelResult(
        request_id=f"local_model_blocked_{task_type}",
        task_type=task_type,
        model=config.model,
        base_url=config.base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout_seconds=config.timeout_seconds,
        status=LocalModelStatus.BLOCKED,
        error=error,
        duration_seconds=0.0,
        audit_event_id=f"local_model_blocked_{task_type}",
        created_at=utc_now(),
    )
