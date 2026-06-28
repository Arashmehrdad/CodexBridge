from __future__ import annotations

from .config import AppConfig
from .safety import redact_secret_values, reject_secret_like_file


class GeminiSummarizer:
    """Disabled-by-default Gemini summarizer stub.

    The MVP intentionally makes no Gemini API calls. This class exists to
    centralize future redaction and refusal behavior.
    """

    def __init__(self, config: AppConfig):
        self.config = config

    def summarize(self, text: str, source_files: list[str] | None = None) -> str:
        if not self.config.gemini.enabled:
            raise RuntimeError("Gemini summarization is disabled")
        for source_file in source_files or []:
            reject_secret_like_file(source_file)
        return redact_secret_values(text)
