from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256

import pytest

from codexbridge.trading.market_chart import PNG_SIGNATURE, render_market_packet_chart
from codexbridge.trading.market_packet import MarketPacket, packet_content_hash

from test_market_packet import build


def test_chart_is_deterministic_and_bound_to_packet_identity() -> None:
    packet, provider = build()
    calls_before = list(provider.calls)

    first = render_market_packet_chart(packet)
    second = render_market_packet_chart(packet)

    assert provider.calls == calls_before
    assert first == second
    assert first.png_bytes.startswith(PNG_SIGNATURE)
    assert first.png_sha256 == sha256(first.png_bytes).hexdigest()
    assert first.chart_id == f"mc_{packet.content_hash[:24]}"
    assert first.packet_id == packet.packet_id
    assert first.packet_content_hash == packet.content_hash


def test_chart_rendering_does_not_mutate_authoritative_packet_values() -> None:
    packet, _ = build()
    completed_before = packet.payload.completed_4h_candles
    developing_before = packet.payload.developing_4h_candle
    tick_before = packet.payload.latest_tick

    chart = render_market_packet_chart(packet)

    assert packet.payload.completed_4h_candles == completed_before
    assert packet.payload.developing_4h_candle == developing_before
    assert packet.payload.latest_tick == tick_before
    assert packet_content_hash(packet.payload) == packet.content_hash
    with pytest.raises(FrozenInstanceError):
        chart.width = 1  # type: ignore[misc]


def test_authoritative_candle_change_changes_packet_and_png_identity() -> None:
    packet, _ = build()
    candles = list(packet.payload.completed_4h_candles)
    candles[-1] = replace(candles[-1], close=candles[-1].close + 3.0)
    payload = replace(packet.payload, completed_4h_candles=tuple(candles))
    changed_hash = packet_content_hash(payload)
    changed_packet = MarketPacket(
        packet_id=f"mp_{changed_hash[:24]}",
        content_hash=changed_hash,
        payload=payload,
    )

    original = render_market_packet_chart(packet)
    changed = render_market_packet_chart(changed_packet)

    assert changed.chart_id != original.chart_id
    assert changed.png_sha256 != original.png_sha256
    assert changed.png_bytes != original.png_bytes


def test_chart_rejects_invalid_dimensions() -> None:
    packet, _ = build()

    with pytest.raises(ValueError, match="at least 320x240"):
        render_market_packet_chart(packet, width=319)
    with pytest.raises(ValueError, match="at least 320x240"):
        render_market_packet_chart(packet, height=239)
