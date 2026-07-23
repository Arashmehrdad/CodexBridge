"""Durable trading safety controls and redaction.

A global pause/kill switch, allowed-symbol control, stale-price and
spread limits, exposure/volume/action-rate/daily-loss limits, and
credential redaction for every public or model-readable surface. The
kill switch is durable: it survives restart and is honoured by the
action gateway and the runtime supervisor. Emergency close actions stay
available while the switch is active — pausing trading must never
prevent getting flat.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc


@dataclass(frozen=True)
class SafetyLimits:
    allowed_symbols: tuple[str, ...] = ("BITCOIN_i",)
    maximum_tick_age_seconds: float = 120.0
    maximum_spread_usd: float = 200.0
    maximum_position_volume_lots: float = 0.05
    maximum_open_volume_lots: float = 0.10
    maximum_actions_per_hour: int = 30
    maximum_daily_loss_usd: float = 25.0

    def __post_init__(self) -> None:
        if not self.allowed_symbols:
            raise ValueError("allowed_symbols must not be empty")
        for name, value in (
            ("maximum_tick_age_seconds", self.maximum_tick_age_seconds),
            ("maximum_spread_usd", self.maximum_spread_usd),
            (
                "maximum_position_volume_lots",
                self.maximum_position_volume_lots,
            ),
            ("maximum_open_volume_lots", self.maximum_open_volume_lots),
            ("maximum_actions_per_hour", self.maximum_actions_per_hour),
            ("maximum_daily_loss_usd", self.maximum_daily_loss_usd),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class KillSwitchState:
    active: bool
    reason: str
    changed_at_utc: datetime | None


def redact_health(health: Any) -> dict[str, Any]:
    """Provider health for public/model-readable output: no login, no
    credentials."""
    return {
        "initialized": bool(getattr(health, "initialized", False)),
        "connected": bool(getattr(health, "connected", False)),
        "account_environment": str(
            getattr(health, "account_environment", "unknown")
        ),
        "server": str(getattr(health, "server", "")),
        "currency": str(getattr(health, "currency", "")),
        "balance": getattr(health, "balance", None),
        "equity": getattr(health, "equity", None),
        "login": "[redacted]",
    }


class TradingSafetyController:
    """Durable kill switch plus limit checks."""

    def __init__(self, db_path: Path, *, limits: SafetyLimits | None = None):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.limits = limits or SafetyLimits()
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_safety_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    occurred_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_action_rate (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at_utc TEXT NOT NULL
                )
                """
            )

    # -- kill switch --------------------------------------------------------

    def kill_switch(self) -> KillSwitchState:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_safety_events"
                " WHERE event_type IN ('kill_switch_on', 'kill_switch_off')"
                " ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return KillSwitchState(active=False, reason="", changed_at_utc=None)
        return KillSwitchState(
            active=str(row["event_type"]) == "kill_switch_on",
            reason=str(row["reason"]),
            changed_at_utc=datetime.fromisoformat(str(row["occurred_at_utc"])),
        )

    def activate_kill_switch(
        self, reason: str, *, at_utc: datetime | None = None
    ) -> KillSwitchState:
        self._record("kill_switch_on", reason, at_utc)
        return self.kill_switch()

    def release_kill_switch(
        self, reason: str, *, at_utc: datetime | None = None
    ) -> KillSwitchState:
        self._record("kill_switch_off", reason, at_utc)
        return self.kill_switch()

    def _record(
        self, event_type: str, reason: str, at_utc: datetime | None
    ) -> None:
        occurred = (at_utc or datetime.now(UTC)).astimezone(UTC)
        normalized = str(reason).strip()
        if not normalized:
            raise ValueError("reason must not be empty")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO trading_safety_events"
                " (event_type, reason, occurred_at_utc) VALUES (?, ?, ?)",
                (event_type, normalized, occurred.isoformat()),
            )
            conn.commit()

    # -- action rate --------------------------------------------------------

    def record_action(self, *, at_utc: datetime | None = None) -> None:
        occurred = (at_utc or datetime.now(UTC)).astimezone(UTC)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO trading_action_rate (occurred_at_utc) VALUES (?)",
                (occurred.isoformat(),),
            )
            conn.commit()

    def actions_in_last_hour(self, *, now: datetime | None = None) -> int:
        moment = (now or datetime.now(UTC)).astimezone(UTC)
        cutoff = (moment - timedelta(hours=1)).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM trading_action_rate"
                " WHERE occurred_at_utc > ?",
                (cutoff,),
            ).fetchone()
        return int(row["n"])

    # -- limit checks -------------------------------------------------------

    def violations(
        self,
        *,
        symbol: str,
        spread_usd: float | None,
        tick_age_seconds: float | None,
        requested_volume_lots: float | None,
        open_volume_lots: float,
        daily_loss_usd: float,
        now: datetime | None = None,
        emergency: bool = False,
    ) -> list[str]:
        """All limit violations for a prospective action.

        Emergency close actions skip the kill switch and rate limit —
        pausing trading must never prevent getting flat — but still
        require an allowed symbol.
        """
        found: list[str] = []
        limits = self.limits
        if not emergency:
            state = self.kill_switch()
            if state.active:
                found.append(f"kill switch is active: {state.reason}")
            if (
                self.actions_in_last_hour(now=now)
                >= limits.maximum_actions_per_hour
            ):
                found.append(
                    "action rate limit reached:"
                    f" {limits.maximum_actions_per_hour}/hour"
                )
        if symbol and symbol not in limits.allowed_symbols:
            found.append(
                f"symbol {symbol!r} is not in the allowed set"
                f" {limits.allowed_symbols}"
            )
        if (
            tick_age_seconds is not None
            and tick_age_seconds > limits.maximum_tick_age_seconds
        ):
            found.append(
                f"price is stale: {tick_age_seconds:.1f}s >"
                f" {limits.maximum_tick_age_seconds:.1f}s"
            )
        if (
            spread_usd is not None
            and spread_usd > limits.maximum_spread_usd
        ):
            found.append(
                f"spread {spread_usd:.2f} exceeds limit"
                f" {limits.maximum_spread_usd:.2f}"
            )
        if not emergency:
            if (
                requested_volume_lots is not None
                and requested_volume_lots
                > limits.maximum_position_volume_lots
            ):
                found.append(
                    f"volume {requested_volume_lots} exceeds per-position"
                    f" limit {limits.maximum_position_volume_lots}"
                )
            if (
                requested_volume_lots is not None
                and open_volume_lots + requested_volume_lots
                > limits.maximum_open_volume_lots
            ):
                found.append(
                    f"total exposure {open_volume_lots + requested_volume_lots}"
                    f" exceeds limit {limits.maximum_open_volume_lots}"
                )
            if daily_loss_usd >= limits.maximum_daily_loss_usd:
                found.append(
                    f"daily loss {daily_loss_usd:.2f} reached limit"
                    f" {limits.maximum_daily_loss_usd:.2f}"
                )
        return found
