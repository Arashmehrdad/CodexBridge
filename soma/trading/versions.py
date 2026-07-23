"""Frozen version identities for every Trading Lab evidence component.

Every durable record produced by the redesigned Trading Lab carries the
version of the component that produced it, so offline replay and reports
can group and compare evidence produced by different implementations
without reinterpreting historical records.
"""

from __future__ import annotations

from typing import Final

# Immutable market packet schema persisted by the packet store.
PACKET_SCHEMA_VERSION: Final[str] = "tl_packet_v2"

# Expanded immutable signal schema (packet-bound, versioned, with
# explicit rejected-signal records).
SIGNAL_SCHEMA_VERSION: Final[str] = "tl_signal_v2"

# Broker-time normalization (offset detection and H4 boundary rules).
NORMALIZER_VERSION: Final[str] = "tl_normalizer_v1"

# Independent per-signal outcome resolution from retained ticks.
RESOLVER_VERSION: Final[str] = "tl_resolver_v1"

# Deterministic offline replay engine.
REPLAY_ENGINE_VERSION: Final[str] = "tl_replay_v1"

# Cost model applied by the replay engine. Honest bid/ask entry and
# exit prices already embed the spread; this version names any further
# per-trade cost treatment.
COST_MODEL_VERSION: Final[str] = "tl_cost_spread_only_v1"

# Strategy policy identities. These are permission surfaces, not
# capabilities: the gateway exposes the full guarded action surface and
# the policy decides what a given strategy may use.
POLICY_HOURLY_FIXED_BRACKET_V1: Final[str] = "hourly_fixed_bracket_v1"
POLICY_AGENTIC_DEMO_V1: Final[str] = "agentic_demo_v1"

KNOWN_POLICY_IDS: Final[tuple[str, ...]] = (
    POLICY_HOURLY_FIXED_BRACKET_V1,
    POLICY_AGENTIC_DEMO_V1,
)
