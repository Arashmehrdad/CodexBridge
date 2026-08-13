"""Versioned G6 v9 evidence-contract identity.

The v8 provider experiment is immutable evidence.  This module defines the next
contract identity separately so the accepted v8 adapter source does not need to
be rewritten in place.
"""

from __future__ import annotations

from typing import Final

G6_V9_EXECUTION_CONTRACT_REF: Final[str] = "execution-contract:codex-app-server:g6:v9"
G6_V9_OUTPUT_CONTRACT_REF: Final[str] = (
    "output-contract:soma.agent_worker_benchmark.semantic.v6"
)
G6_V9_RELATION_MODEL: Final[str] = "support_only_line_spans"
G6_V9_MAX_SPAN_LINES: Final[int] = 8
