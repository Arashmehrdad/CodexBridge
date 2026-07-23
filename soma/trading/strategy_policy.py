"""Capability roles, execution modes, action types, and strategy policies.

Capability is separate from strategy permission. The gateway exposes the
complete guarded action surface; a capability role decides whether the
caller may act at all and in which execution mode, and a strategy policy
decides which actions that strategy is allowed to use. ``live`` is not
an execution mode here and cannot be constructed — live execution is
structurally disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from .versions import POLICY_AGENTIC_DEMO_V1, POLICY_HOURLY_FIXED_BRACKET_V1


class ExecutionMode(str, Enum):
    INTERNAL_PAPER = "internal_paper"
    BROKER_DEMO = "broker_demo"


class CapabilityRole(str, Enum):
    RESEARCH_COLLECTOR = "research_collector"
    INTERNAL_PAPER_AGENT = "internal_paper_agent"
    BROKER_DEMO_AGENT = "broker_demo_agent"


class ActionType(str, Enum):
    # Entries.
    MARKET_ENTRY = "market_entry"
    PENDING_LIMIT_ENTRY = "pending_limit_entry"
    PENDING_STOP_ENTRY = "pending_stop_entry"
    PENDING_STOP_LIMIT_ENTRY = "pending_stop_limit_entry"
    # Pending management.
    CANCEL_PENDING = "cancel_pending"
    REPLACE_PENDING = "replace_pending"
    # Position sizing.
    CLOSE_FULL = "close_full"
    CLOSE_PARTIAL = "close_partial"
    SCALE_IN = "scale_in"
    SCALE_OUT = "scale_out"
    # Bracket management.
    SET_SLTP = "set_sltp"
    MODIFY_SLTP = "modify_sltp"
    REMOVE_SLTP = "remove_sltp"
    BREAK_EVEN = "break_even"
    LOCK_PROFIT = "lock_profit"
    SET_MULTIPLE_TARGETS = "set_multiple_targets"
    # Direction and hedging.
    REVERSE = "reverse"
    HEDGE_OPEN = "hedge_open"
    HEDGE_CLOSE = "hedge_close"
    # Standing exit policies.
    TIME_EXIT = "time_exit"
    CONDITION_EXIT = "condition_exit"
    NEWS_EXIT = "news_exit"
    TRAILING_STOP_SET = "trailing_stop_set"
    TRAILING_STOP_CANCEL = "trailing_stop_cancel"
    # Account safety surface.
    FLATTEN_SYMBOL = "flatten_symbol"
    FLATTEN_ACCOUNT = "flatten_account"
    EMERGENCY_CLOSE_ALL = "emergency_close_all"


ENTRY_ACTIONS: Final[frozenset[ActionType]] = frozenset(
    {
        ActionType.MARKET_ENTRY,
        ActionType.PENDING_LIMIT_ENTRY,
        ActionType.PENDING_STOP_ENTRY,
        ActionType.PENDING_STOP_LIMIT_ENTRY,
        ActionType.SCALE_IN,
        ActionType.HEDGE_OPEN,
    }
)

EMERGENCY_ACTIONS: Final[frozenset[ActionType]] = frozenset(
    {
        ActionType.FLATTEN_SYMBOL,
        ActionType.FLATTEN_ACCOUNT,
        ActionType.EMERGENCY_CLOSE_ALL,
    }
)

STANDING_POLICY_ACTIONS: Final[frozenset[ActionType]] = frozenset(
    {
        ActionType.TIME_EXIT,
        ActionType.CONDITION_EXIT,
        ActionType.NEWS_EXIT,
        ActionType.TRAILING_STOP_SET,
        ActionType.TRAILING_STOP_CANCEL,
    }
)


@dataclass(frozen=True)
class StrategyPolicy:
    policy_id: str
    allowed_actions: frozenset[ActionType]
    allow_stacking: bool
    requires_fixed_bracket: bool
    description: str

    def allows(self, action: ActionType) -> bool:
        return ActionType(action) in self.allowed_actions


HOURLY_FIXED_BRACKET_V1 = StrategyPolicy(
    policy_id=POLICY_HOURLY_FIXED_BRACKET_V1,
    allowed_actions=frozenset({ActionType.MARKET_ENTRY}),
    allow_stacking=False,
    requires_fixed_bracket=True,
    description=(
        "One market entry with one original model-selected stop-loss and"
        " take-profit, immutable after entry: no modification, trailing,"
        " reversal, stacking, or partial exit."
    ),
)

AGENTIC_DEMO_V1 = StrategyPolicy(
    policy_id=POLICY_AGENTIC_DEMO_V1,
    allowed_actions=frozenset(ActionType),
    allow_stacking=True,
    requires_fixed_bracket=False,
    description=(
        "Complete guarded demo management surface: entries, pending"
        " management, sizing, bracket management, reversal, hedging,"
        " standing exit policies, and flattening."
    ),
)

STRATEGY_POLICIES: Final[dict[str, StrategyPolicy]] = {
    HOURLY_FIXED_BRACKET_V1.policy_id: HOURLY_FIXED_BRACKET_V1,
    AGENTIC_DEMO_V1.policy_id: AGENTIC_DEMO_V1,
}

# Which execution modes each capability role may act in. The research
# collector may never act: reads and signal submission only.
ROLE_ACTION_MODES: Final[dict[CapabilityRole, frozenset[ExecutionMode]]] = {
    CapabilityRole.RESEARCH_COLLECTOR: frozenset(),
    CapabilityRole.INTERNAL_PAPER_AGENT: frozenset(
        {ExecutionMode.INTERNAL_PAPER}
    ),
    CapabilityRole.BROKER_DEMO_AGENT: frozenset({ExecutionMode.BROKER_DEMO}),
}


def resolve_policy(policy_id: str) -> StrategyPolicy:
    policy = STRATEGY_POLICIES.get(str(policy_id).strip())
    if policy is None:
        raise ValueError(
            f"unknown strategy policy {policy_id!r};"
            f" known: {sorted(STRATEGY_POLICIES)}"
        )
    return policy


def role_may_act(role: CapabilityRole, mode: ExecutionMode) -> bool:
    return ExecutionMode(mode) in ROLE_ACTION_MODES[CapabilityRole(role)]
