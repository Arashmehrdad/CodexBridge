"""Equivalence between the superseded in-tree trading implementation and
the standalone ``trading_lab`` package.

Two independent proofs run here:

1. **Domain equivalence.** The same scenario is executed twice against
   isolated temporary databases -- once through ``soma.trading``, once
   through ``trading_lab`` -- and the serialized results must match. This
   is the evidence that justified the cutover.
2. **Source equivalence.** Every module the package inherited must still
   be byte-identical to the copy it replaced, apart from the package
   header. If someone patches one side only, this fails.

Both proofs are skipped once ``soma/trading`` is deleted, which is the
intended terminal state. What survives the deletion is
``test_trading_lab_gateway.py``: the public-gateway behavior tests.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pytest

UTC = timezone.utc
SYMBOL = "BITCOIN_i"
OFFSET = 3 * 60 * 60
H4 = 4 * 60 * 60
DEVELOPING_RAW_OPEN = 1_784_534_400
DEVELOPING_OPEN_UTC = datetime.fromtimestamp(DEVELOPING_RAW_OPEN - OFFSET, tz=UTC)
NOW = DEVELOPING_OPEN_UTC + timedelta(hours=1)

LEGACY_PRESENT = find_spec("soma.trading") is not None

pytestmark = pytest.mark.skipif(
    not LEGACY_PRESENT,
    reason="soma.trading has been removed; trading_lab is the only backend",
)

# The modules the package inherited, and must not drift from.
SHARED_MODULES = (
    "action_gateway",
    "broker_time",
    "executors",
    "lab_reports",
    "market_chart",
    "market_packet",
    "mt5_provider",
    "outcome_resolver",
    "packet_store",
    "replay_engine",
    "safety",
    "signal_journal_v2",
    "strategy_policy",
    "tick_archive",
    "trading_runtime",
    "versions",
)


def canonical(value: Any) -> Any:
    """Soma's own trading serializer, applied identically to both sides.

    Extended beyond ``_trading_json`` with enum, set, and date handling so
    that domain objects the public gateway never serializes -- strategy
    policies, version tables -- can still be compared exactly.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return canonical(asdict(value))
    if isinstance(value, Enum):
        return canonical(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): canonical(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(json.dumps(canonical(item), sort_keys=True) for item in value)
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


# Fields both implementations stamp from the wall clock. They can never
# be byte-equal across two sequential runs, so they are compared
# semantically -- both sides must carry a well-formed UTC instant -- and
# then normalized out of the exact comparison. Nothing else is exempt.
VOLATILE_FIELDS = frozenset(
    {
        "created_at_utc",
        "inserted_at_utc",
        "occurred_at_utc",
        "requested_at_utc",
        "updated_at_utc",
    }
)
VOLATILE_PLACEHOLDER = "<wall-clock>"


def _assert_utc_instant(where: str, value: Any) -> None:
    assert isinstance(value, str) and value, f"{where} is not a timestamp"
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"{where} is not timezone-aware"
    assert parsed.utcoffset() == timedelta(0), f"{where} is not UTC"


def normalize(value: Any, where: str = "") -> Any:
    """Replace wall-clock stamps after checking both sides carry one."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            path = f"{where}.{key}"
            if key in VOLATILE_FIELDS and item is not None:
                _assert_utc_instant(path, item)
                result[key] = VOLATILE_PLACEHOLDER
            else:
                result[key] = normalize(item, path)
        return result
    if isinstance(value, list):
        return [
            normalize(item, f"{where}[{index}]")
            for index, item in enumerate(value)
        ]
    return value


def blob(value: Any) -> str:
    """Deterministic bytes for exact comparison."""
    return json.dumps(
        normalize(canonical(value)), sort_keys=True, ensure_ascii=False
    )


class Backend:
    """One trading implementation, wired to its own temporary databases."""

    def __init__(self, root: str, directory: Path) -> None:
        self.root = root
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def module(self, name: str) -> Any:
        return import_module(f"{self.root}.{name}")

    @property
    def top(self) -> Any:
        return import_module(self.root)

    def packet_store(self) -> Any:
        return self.module("packet_store").MarketPacketStore(
            self.directory / "packets.sqlite3"
        )

    def signal_journal(self) -> Any:
        return self.module("signal_journal_v2").SignalJournalV2(
            self.directory / "signals.sqlite3",
            self.packet_store(),
            expected_symbol=SYMBOL,
        )

    def outcome_journal(self) -> Any:
        return self.module("outcome_resolver").SignalOutcomeJournal(
            self.directory / "outcomes.sqlite3"
        )

    def tick_archive(self) -> Any:
        return self.module("tick_archive").TickArchive(
            self.directory / "ticks.sqlite3",
            self.directory / "tick_archives",
        )

    def action_journal(self) -> Any:
        return self.module("action_gateway").TradingActionJournal(
            self.directory / "actions.sqlite3"
        )

    def safety(self) -> Any:
        return self.module("safety").TradingSafetyController(
            self.directory / "safety.sqlite3"
        )

    def action_gateway(self) -> Any:
        return self.module("action_gateway").ActionGateway(
            journal=self.action_journal(), safety=self.safety()
        )

    def runtime(self) -> Any:
        return self.module("trading_runtime").TradingRuntime(
            runtime_db_path=self.directory / "runtime.sqlite3",
            packet_store=self.packet_store(),
            signal_journal=self.signal_journal(),
            outcome_journal=self.outcome_journal(),
            tick_archive=self.tick_archive(),
            action_journal=self.action_journal(),
            gateway=self.action_gateway(),
            symbol=SYMBOL,
        )

    # -- Deterministic fixtures ------------------------------------------

    def provider_timestamp(self, raw_epoch: int) -> Any:
        return self.module("mt5_provider").ProviderTimestamp(
            raw_epoch_seconds=raw_epoch,
            provider_utc_offset_seconds=OFFSET,
            normalized_utc=datetime.fromtimestamp(raw_epoch - OFFSET, tz=UTC),
        )

    def candle(self, raw_open: int, value: float) -> Any:
        return self.module("mt5_provider").Candle(
            symbol=SYMBOL,
            timeframe="4H",
            open_time=self.provider_timestamp(raw_open),
            open=value,
            high=value + 2,
            low=value - 1,
            close=value + 1,
            tick_volume=100,
            spread=64,
            real_volume=0,
        )

    def specification(self) -> Any:
        return self.module("mt5_provider").SymbolSpecification(
            symbol=SYMBOL,
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=0.01,
            contract_size=1.0,
            minimum_volume=0.01,
            maximum_volume=300.0,
            volume_step=0.01,
            trade_mode=4,
            order_mode=63,
            margin_initial=0.0,
            margin_maintenance=0.0,
            currency_base="USD",
            currency_profit="USD",
            currency_margin="USD",
        )

    def health(self) -> Any:
        return self.module("mt5_provider").ProviderHealth(
            initialized=True,
            connected=True,
            account_environment="demo",
            server="Alpari-MT5-Demo",
            login=123,
            currency="USD",
            balance=998.72,
            equity=998.72,
            last_error=(1, "Success"),
        )

    def packet_provider(self) -> Any:
        backend = self

        class _Provider:
            def __init__(self) -> None:
                broker_epoch = int(NOW.timestamp()) + OFFSET
                open_epoch = broker_epoch - (broker_epoch % H4)
                self.completed = [
                    backend.candle(open_epoch - H4 * (100 - i), 60_000 + i)
                    for i in range(100)
                ]
                self.developing = backend.candle(open_epoch, 61_000)
                self.tick = backend.module("mt5_provider").Tick(
                    symbol=SYMBOL,
                    bid=64_000.0,
                    ask=64_064.0,
                    last=0.0,
                    volume=1.0,
                    timestamp=backend.provider_timestamp(
                        int(NOW.timestamp()) + OFFSET - 15
                    ),
                    age_seconds=15.0,
                    fresh=True,
                )

            def health(self) -> Any:
                return backend.health()

            def symbol_specification(self, symbol: str) -> Any:
                return backend.specification()

            def latest_tick(self, _symbol: str) -> Any:
                return self.tick

            def h4_candles(self, _symbol: str, *, completed_count: int = 200):
                return self.completed[-completed_count:], self.developing

        return _Provider()

    def build_packet(self) -> Any:
        return self.module("market_packet").MarketPacketBuilder(
            now=lambda: NOW
        ).build(self.packet_provider(), SYMBOL, completed_count=100)

    def archived_tick(self, at: datetime, bid: float, ask: float) -> Any:
        return self.module("tick_archive").ArchivedTick(
            symbol=SYMBOL,
            raw_epoch_seconds=int(at.timestamp()) + OFFSET,
            broker_utc_offset_seconds=OFFSET,
            normalized_utc=at,
            bid=bid,
            ask=ask,
            last=0.0,
            volume=1.0,
            flags=0,
            source="equivalence",
        )


@pytest.fixture()
def backends(tmp_path: Path) -> tuple[Backend, Backend]:
    return (
        Backend("soma.trading", tmp_path / "legacy"),
        Backend("trading_lab", tmp_path / "package"),
    )


def both(backends: tuple[Backend, Backend], scenario) -> tuple[Any, Any]:
    """Run one scenario on each backend and return both results."""
    legacy, package = backends
    return scenario(legacy), scenario(package)


def assert_equivalent(backends: tuple[Backend, Backend], scenario) -> Any:
    """Exact serialized equality between the two implementations.

    Wall-clock stamps are checked semantically (both sides must produce a
    well-formed UTC instant) and then normalized; every other byte must
    match exactly.
    """
    legacy_result, package_result = both(backends, scenario)
    assert blob(legacy_result) == blob(package_result)
    return package_result


class TestSourceEquivalence:
    """The package modules must not drift from the ones they replaced."""

    @pytest.mark.parametrize("name", SHARED_MODULES)
    def test_module_source_is_identical(self, name: str) -> None:
        legacy = Path(import_module(f"soma.trading.{name}").__file__)
        package = Path(import_module(f"trading_lab.{name}").__file__)
        assert legacy.read_text("utf-8") == package.read_text("utf-8"), name

    def test_the_package_covers_every_legacy_module(self) -> None:
        legacy_root = Path(import_module("soma.trading").__file__).parent
        package_root = Path(import_module("trading_lab").__file__).parent
        legacy_names = {
            path.stem
            for path in legacy_root.glob("*.py")
            if path.stem != "__init__"
        }
        package_names = {
            path.stem
            for path in package_root.glob("*.py")
            if path.stem != "__init__"
        }
        assert legacy_names <= package_names
        assert legacy_names == set(SHARED_MODULES)

    def test_public_names_are_a_superset(self) -> None:
        legacy = set(import_module("soma.trading").__all__)
        package = set(import_module("trading_lab").__all__)
        assert legacy <= package


class TestProviderModelEquivalence:
    def test_health(self, backends) -> None:
        assert_equivalent(backends, lambda b: b.health())

    def test_specification(self, backends) -> None:
        assert_equivalent(backends, lambda b: b.specification())

    def test_candles(self, backends) -> None:
        assert_equivalent(
            backends,
            lambda b: [b.candle(DEVELOPING_RAW_OPEN - H4 * i, 60_000 + i) for i in range(5)],
        )

    def test_redacted_health_hides_the_login(self, backends) -> None:
        result = assert_equivalent(
            backends, lambda b: b.module("safety").redact_health(b.health())
        )
        assert result["login"] == "[redacted]"
        assert result["server"] == "Alpari-MT5-Demo"

    def test_broker_offset_detection(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            module = b.module("broker_time")
            samples = [
                module.OffsetSample(
                    raw_epoch_seconds=int(NOW.timestamp()) + OFFSET + index,
                    host_utc=NOW + timedelta(seconds=index),
                )
                for index in range(5)
            ]
            return module.detect_broker_utc_offset(
                samples, detected_at_utc=NOW
            )

        detection = assert_equivalent(backends, scenario)
        assert detection.offset_seconds == OFFSET

    def test_h4_boundary_rules(self, backends) -> None:
        assert_equivalent(
            backends,
            lambda b: [
                b.module("broker_time").broker_h4_open_epoch(
                    DEVELOPING_RAW_OPEN + delta
                )
                for delta in (0, 1, H4 - 1, H4, H4 * 3 + 7)
            ],
        )


class TestPacketEquivalence:
    def test_packet_content_hash_is_identical(self, backends) -> None:
        packet = assert_equivalent(backends, lambda b: b.build_packet())
        assert packet.content_hash

    def test_stored_packet_round_trip(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            stored = b.packet_store().store(
                b.build_packet(), inserted_at_utc=NOW
            )
            return b.packet_store().get(stored.packet_id)

        assert_equivalent(backends, scenario)

    def test_packet_listing_and_count(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            store = b.packet_store()
            store.store(b.build_packet(), inserted_at_utc=NOW)
            return {
                "packets": store.list_packets(limit=10, offset=0),
                "total": store.count_packets(),
            }

        assert_equivalent(backends, scenario)

    def test_chart_bytes_are_identical(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            chart = b.module("market_chart").render_market_packet_chart(
                b.build_packet()
            )
            return {
                "chart_id": chart.chart_id,
                "png_sha256": chart.png_sha256,
                "width": chart.width,
                "height": chart.height,
                "size": len(chart.png_bytes),
            }

        chart = assert_equivalent(backends, scenario)
        assert chart["png_sha256"]


class TestSignalJournalEquivalence:
    def submission(self, b: Backend, packet_id: str, **overrides) -> Any:
        module = b.module("signal_journal_v2")
        payload = dict(
            packet_id=packet_id,
            decision=module.SignalDecisionV2.LONG,
            confidence=73,
            stop_loss=63_400.0,
            take_profit=65_400.0,
            reason="equivalence",
            news_context="",
            model_version="model-1",
            prompt_version="prompt-1",
            policy_id="hourly_fixed_bracket_v1",
            execution_mode="internal_paper",
            experiment_id="exp1",
            submitted_at_utc=NOW + timedelta(minutes=2),
        )
        payload.update(overrides)
        return module.SignalSubmissionV2(**payload)

    def test_submit_and_get(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            stored = b.packet_store().store(
                b.build_packet(), inserted_at_utc=NOW
            )
            journal = b.signal_journal()
            record = journal.submit(
                "key-1", self.submission(b, stored.packet_id)
            )
            return journal.get(record.signal_id)

        record = assert_equivalent(backends, scenario)
        assert record.signal_id.startswith("sig2_")

    def test_signal_content_hash_is_identical(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            stored = b.packet_store().store(
                b.build_packet(), inserted_at_utc=NOW
            )
            record = b.signal_journal().submit(
                "key-hash", self.submission(b, stored.packet_id)
            )
            return record.content_hash

        assert len(assert_equivalent(backends, scenario)) == 64

    def test_idempotent_resubmission(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            stored = b.packet_store().store(
                b.build_packet(), inserted_at_utc=NOW
            )
            journal = b.signal_journal()
            submission = self.submission(b, stored.packet_id)
            first = journal.submit("same", submission)
            second = journal.submit("same", submission)
            return {
                "same_id": first.signal_id == second.signal_id,
                "count": journal.count(),
            }

        assert assert_equivalent(backends, scenario) == {
            "same_id": True,
            "count": 1,
        }

    def test_rejection_records_match(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            journal = b.signal_journal()
            module = b.module("signal_journal_v2")
            try:
                journal.submit("bad", self.submission(b, "mp_missing"))
            except module.SignalRejectedError as exc:
                return {
                    "rejection": exc.rejection,
                    "listed": journal.list_rejections(limit=10),
                }
            raise AssertionError("expected a rejection")

        assert_equivalent(backends, scenario)

    def test_listing_filters_and_counts(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            stored = b.packet_store().store(
                b.build_packet(), inserted_at_utc=NOW
            )
            journal = b.signal_journal()
            module = b.module("signal_journal_v2")
            journal.submit("k1", self.submission(b, stored.packet_id))
            journal.submit(
                "k2",
                self.submission(
                    b,
                    stored.packet_id,
                    decision=module.SignalDecisionV2.SHORT,
                    stop_loss=65_000.0,
                    take_profit=62_000.0,
                ),
            )
            return {
                "all": journal.list(limit=10, offset=0),
                "total": journal.count(),
                "submitted": journal.count(
                    status=module.SignalStatusV2.SUBMITTED
                ),
                "by_experiment": journal.count(experiment_id="exp1"),
                "paged": journal.list(limit=1, offset=1),
            }

        assert_equivalent(backends, scenario)

    def test_cancel_before_entry(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            stored = b.packet_store().store(
                b.build_packet(), inserted_at_utc=NOW
            )
            journal = b.signal_journal()
            record = journal.submit(
                "k-cancel", self.submission(b, stored.packet_id)
            )
            cancelled = journal.cancel_before_entry(
                record.signal_id,
                "withdrawn",
                cancelled_at_utc=NOW + timedelta(minutes=5),
            )
            return {
                "record": cancelled,
                "events": journal.events(record.signal_id),
            }

        assert_equivalent(backends, scenario)


class TestOutcomeEquivalence:
    def signal_record(self, b: Backend, **overrides) -> Any:
        module = b.module("signal_journal_v2")
        versions = b.module("versions")
        payload = dict(
            signal_id="sig2_equivalence000000000001",
            idempotency_key="key-equivalence",
            content_hash="0" * 64,
            schema_version=versions.SIGNAL_SCHEMA_VERSION,
            packet_id="mp_test",
            packet_hash="0" * 64,
            symbol=SYMBOL,
            bid=64_000.0,
            ask=64_064.0,
            spread=64.0,
            market_data_timestamp=NOW,
            tick_raw_epoch_seconds=int(NOW.timestamp()) + OFFSET,
            broker_utc_offset_seconds=OFFSET,
            parent_h4_raw_open_epoch=DEVELOPING_RAW_OPEN,
            parent_h4_open_utc=DEVELOPING_OPEN_UTC,
            packet_age_seconds=15.0,
            decision=module.SignalDecisionV2.LONG,
            confidence=73,
            entry_reference_price=64_064.0,
            stop_loss=63_400.0,
            take_profit=65_400.0,
            risk_reward=None,
            model_version="model-1",
            prompt_version="prompt-1",
            policy_id="hourly_fixed_bracket_v1",
            execution_mode="internal_paper",
            experiment_id="exp1",
            reason="equivalence",
            news_context="",
            status=module.SignalStatusV2.SUBMITTED,
            submitted_at_utc=NOW,
            inserted_at_utc=NOW,
            entered_at_utc=None,
        )
        payload.update(overrides)
        return module.SignalRecordV2(**payload)

    def test_resolution_from_ticks(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            ticks = [
                b.archived_tick(
                    NOW + timedelta(minutes=index), 65_500.0, 65_560.0
                )
                for index in range(1, 4)
            ]
            return b.module("outcome_resolver").resolve_from_ticks(
                self.signal_record(b), ticks
            )

        outcome = assert_equivalent(backends, scenario)
        assert outcome.status.value == "RESOLVED_TP"

    def test_stop_loss_resolution(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            ticks = [
                b.archived_tick(
                    NOW + timedelta(minutes=index), 63_000.0, 63_060.0
                )
                for index in range(1, 4)
            ]
            return b.module("outcome_resolver").resolve_from_ticks(
                self.signal_record(b), ticks
            )

        outcome = assert_equivalent(backends, scenario)
        assert outcome.status.value == "RESOLVED_SL"

    def test_data_gap_resolution(self, backends) -> None:
        assert_equivalent(
            backends,
            lambda b: b.module("outcome_resolver").resolve_from_ticks(
                self.signal_record(b), []
            ),
        )

    def test_outcome_journal_round_trip(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            ticks = [
                b.archived_tick(
                    NOW + timedelta(minutes=index), 65_500.0, 65_560.0
                )
                for index in range(1, 4)
            ]
            outcome = b.module("outcome_resolver").resolve_from_ticks(
                self.signal_record(b), ticks
            )
            journal = b.outcome_journal()
            journal.record(outcome)
            return {
                "stored": journal.get(outcome.signal_id),
                "listed": journal.list(limit=10, offset=0),
                "count": journal.count(),
                "events": journal.events(outcome.signal_id),
            }

        assert_equivalent(backends, scenario)

    def test_reports_are_identical(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            signals = [self.signal_record(b)]
            ticks = [
                b.archived_tick(
                    NOW + timedelta(minutes=index), 65_500.0, 65_560.0
                )
                for index in range(1, 4)
            ]
            outcome = b.module("outcome_resolver").resolve_from_ticks(
                signals[0], ticks
            )
            outcomes = {outcome.signal_id: outcome}
            reports = b.module("lab_reports")
            replay = b.module("replay_engine")
            return {
                "calibration": reports.build_calibration_report(
                    signals, outcomes, experiment_id="exp1", rejection_count=0
                ),
                "replay": reports.build_replay_report(
                    signals,
                    outcomes,
                    experiment_id="exp1",
                    base_config=replay.ReplayConfig(threshold=70),
                    thresholds=(70, 71, 72),
                    minimum_sample=1,
                ),
            }

        assert_equivalent(backends, scenario)

    def test_replay_engine_is_identical(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            replay = b.module("replay_engine")
            signals = [self.signal_record(b)]
            ticks = [
                b.archived_tick(
                    NOW + timedelta(minutes=index), 65_500.0, 65_560.0
                )
                for index in range(1, 4)
            ]
            outcome = b.module("outcome_resolver").resolve_from_ticks(
                signals[0], ticks
            )
            outcomes = {outcome.signal_id: outcome}
            return {
                "replayed": replay.replay_signals(
                    signals, outcomes, replay.ReplayConfig(threshold=70)
                ),
                "swept": replay.sweep_thresholds(
                    signals,
                    outcomes,
                    base_config=replay.ReplayConfig(threshold=70),
                    thresholds=(70, 75, 80),
                    minimum_sample=1,
                ),
            }

        assert_equivalent(backends, scenario)


class TestTickArchiveEquivalence:
    def test_ingest_range_hash_and_gaps(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            archive = b.tick_archive()
            historical = b.module("mt5_provider").HistoricalTick
            ticks = [
                historical(
                    symbol=SYMBOL,
                    bid=64_000.0 + index,
                    ask=64_064.0 + index,
                    last=0.0,
                    volume=1.0,
                    flags=0,
                    timestamp=b.provider_timestamp(
                        int(NOW.timestamp()) + OFFSET + index * 60
                    ),
                )
                for index in range(10)
            ]
            ingested = archive.ingest(ticks, source="equivalence")
            start = NOW - timedelta(minutes=1)
            end = NOW + timedelta(minutes=30)
            range_hash, count = archive.range_hash(SYMBOL, start, end)
            return {
                "ingested": ingested,
                "range_hash": range_hash,
                "count": count,
                "gaps": archive.detect_gaps(
                    SYMBOL, start, end, max_gap_seconds=30.0
                ),
                "ticks": archive.ticks_between(SYMBOL, start, end),
            }

        result = assert_equivalent(backends, scenario)
        assert result["ingested"] == 10

    def test_daily_archive(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            archive = b.tick_archive()
            historical = b.module("mt5_provider").HistoricalTick
            archive.ingest(
                [
                    historical(
                        symbol=SYMBOL,
                        bid=64_000.0,
                        ask=64_064.0,
                        last=0.0,
                        volume=1.0,
                        flags=0,
                        timestamp=b.provider_timestamp(
                            int(NOW.timestamp()) + OFFSET
                        ),
                    )
                ],
                source="equivalence",
            )
            record = archive.archive_day(SYMBOL, NOW.date())
            return {
                "content_sha256": record.content_sha256,
                "relative_path": record.relative_path,
                "tick_count": record.tick_count,
                "day": record.day,
                "contents": archive.read_archive(record),
            }

        assert_equivalent(backends, scenario)


class TestActionGatewayEquivalence:
    def executor(self, b: Backend) -> Any:
        gateway = b.module("action_gateway")
        return b.module("executors").PaperExecutor(
            quote_source=lambda _s: gateway.Quote(
                bid=64_000.0, ask=64_064.0, age_seconds=1.0
            ),
            rules_source=lambda _s: b.specification(),
        )

    def request(self, b: Backend, **overrides) -> Any:
        gateway = b.module("action_gateway")
        policy = b.module("strategy_policy")
        payload = dict(
            idempotency_key="act-1",
            action_type=policy.ActionType.MARKET_ENTRY,
            origin="model",
            capability_role=policy.CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=policy.ExecutionMode.INTERNAL_PAPER,
            policy_id="agentic_demo_v1",
            experiment_id="exp1",
            symbol=SYMBOL,
            direction="LONG",
            volume_lots=0.01,
            stop_loss=63_000.0,
            take_profit=65_000.0,
        )
        payload.update(overrides)
        return gateway.ActionRequest(**payload)

    def test_market_entry_record(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            record = b.action_gateway().submit(
                self.request(b), self.executor(b)
            )
            journal = b.action_journal()
            return {
                "record": record,
                "fetched": journal.get(record.action_id),
                "listed": journal.list(limit=10, offset=0),
                "count": journal.count(),
                "events": journal.events(record.action_id),
            }

        assert_equivalent(backends, scenario)

    def test_idempotent_action(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            gateway = b.action_gateway()
            executor = self.executor(b)
            first = gateway.submit(self.request(b), executor)
            second = gateway.submit(self.request(b), executor)
            return {
                "same": first.action_id == second.action_id,
                "count": b.action_journal().count(),
            }

        assert assert_equivalent(backends, scenario) == {
            "same": True,
            "count": 1,
        }

    def test_policy_refusal_is_identical(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            record = b.action_gateway().submit(
                self.request(b, policy_id="hourly_fixed_bracket_v1",
                             action_type=b.module("strategy_policy").ActionType.REVERSE),
                self.executor(b),
            )
            return {"state": record.state.value, "error": record.error}

        result = assert_equivalent(backends, scenario)
        assert result["state"] == "REJECTED"

    def test_research_collector_may_not_act(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            policy = b.module("strategy_policy")
            record = b.action_gateway().submit(
                self.request(
                    b,
                    capability_role=policy.CapabilityRole.RESEARCH_COLLECTOR,
                ),
                self.executor(b),
            )
            return {"state": record.state.value, "error": record.error}

        result = assert_equivalent(backends, scenario)
        assert result["state"] == "REJECTED"

    def test_kill_switch_blocks_identically(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            safety = b.safety()
            safety.activate_kill_switch("halted", at_utc=NOW)
            gateway = b.module("action_gateway").ActionGateway(
                journal=b.action_journal(), safety=safety
            )
            record = gateway.submit(self.request(b), self.executor(b))
            return {
                "state": record.state.value,
                "error": record.error,
                "kill_switch": safety.kill_switch(),
            }

        result = assert_equivalent(backends, scenario)
        assert result["state"] == "REJECTED"

    def test_every_action_type_behaves_identically(self, backends) -> None:
        """The completeness gate: no action may diverge between backends."""

        def scenario(b: Backend) -> Any:
            policy = b.module("strategy_policy")
            gateway = b.action_gateway()
            executor = self.executor(b)
            results = {}
            for index, action in enumerate(sorted(
                policy.ActionType, key=lambda item: item.value
            )):
                record = gateway.submit(
                    self.request(
                        b,
                        idempotency_key=f"sweep-{index}",
                        action_type=action,
                        policy_id="agentic_demo_v1",
                    ),
                    executor,
                )
                results[action.value] = {
                    "state": record.state.value,
                    "error": record.error,
                    "action_type": record.action_type.value,
                }
            return results

        results = assert_equivalent(backends, scenario)
        from trading_lab.service import ACTION_OPERATIONS

        assert set(results) == set(ACTION_OPERATIONS)


class TestRuntimeEquivalence:
    def test_start_status_stop_and_events(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            runtime = b.runtime()
            started = runtime.start(now=NOW)
            status = runtime.status()
            stopped = runtime.stop("done", now=NOW + timedelta(minutes=1))
            return {
                "started": started,
                "status": status,
                "stopped": stopped,
                "events": runtime.events(limit=20),
            }

        assert_equivalent(backends, scenario)

    def test_kill_switch_round_trip(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            safety = b.safety()
            on = safety.activate_kill_switch("halt", at_utc=NOW)
            off = safety.release_kill_switch(
                "resume", at_utc=NOW + timedelta(minutes=5)
            )
            return {"on": on, "off": off, "final": safety.kill_switch()}

        assert_equivalent(backends, scenario)

    def test_safety_violations(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            safety = b.safety()
            safety.record_action(at_utc=NOW)
            return {
                "in_last_hour": safety.actions_in_last_hour(now=NOW),
                "limits": b.module("safety").SafetyLimits(),
            }

        assert_equivalent(backends, scenario)


class TestStrategyPolicyEquivalence:
    def test_policies_resolve_identically(self, backends) -> None:
        assert_equivalent(
            backends,
            lambda b: [
                b.module("strategy_policy").resolve_policy(name)
                for name in ("hourly_fixed_bracket_v1", "agentic_demo_v1")
            ],
        )

    def test_version_identities_match(self, backends) -> None:
        def scenario(b: Backend) -> Any:
            versions = b.module("versions")
            return {
                name: getattr(versions, name)
                for name in sorted(dir(versions))
                if name.isupper()
            }

        assert_equivalent(backends, scenario)

    def test_action_type_membership_matches(self, backends) -> None:
        assert_equivalent(
            backends,
            lambda b: sorted(
                action.value for action in b.module("strategy_policy").ActionType
            ),
        )
