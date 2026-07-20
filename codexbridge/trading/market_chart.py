from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from hashlib import sha256

from .market_packet import MarketPacket


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BACKGROUND = (255, 255, 255)
AXIS = (96, 96, 96)
UP = (32, 128, 64)
DOWN = (192, 48, 48)
DEVELOPING = (48, 96, 192)


@dataclass(frozen=True)
class MarketChart:
    chart_id: str
    packet_id: str
    packet_content_hash: str
    png_sha256: str
    png_bytes: bytes
    width: int
    height: int


def _chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def _set_pixel(image: bytearray, width: int, height: int, x: int, y: int, colour: tuple[int, int, int]) -> None:
    if x < 0 or x >= width or y < 0 or y >= height:
        return
    index = (y * width + x) * 3
    image[index:index + 3] = bytes(colour)


def _vertical(image: bytearray, width: int, height: int, x: int, first: int, last: int, colour: tuple[int, int, int]) -> None:
    low, high = sorted((first, last))
    for y in range(low, high + 1):
        _set_pixel(image, width, height, x, y, colour)


def _rectangle(image: bytearray, width: int, height: int, left: int, top: int, right: int, bottom: int, colour: tuple[int, int, int]) -> None:
    x0, x1 = sorted((left, right))
    y0, y1 = sorted((top, bottom))
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            _set_pixel(image, width, height, x, y, colour)


def _png(width: int, height: int, pixels: bytearray) -> bytes:
    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        start = y * stride
        rows.extend(pixels[start:start + stride])
    return b"".join(
        (
            PNG_SIGNATURE,
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _chunk(b"IDAT", zlib.compress(bytes(rows), level=9)),
            _chunk(b"IEND", b""),
        )
    )


def render_market_packet_chart(packet: MarketPacket, *, width: int = 1200, height: int = 640) -> MarketChart:
    """Render deterministic candles from the exact immutable packet, without provider access."""

    if width < 320 or height < 240:
        raise ValueError("chart dimensions must be at least 320x240")
    candles = (*packet.payload.completed_4h_candles, packet.payload.developing_4h_candle)
    if not candles:
        raise ValueError("market packet contains no candles")

    prices = [value for candle in candles for value in (candle.low, candle.high)]
    price_low = min(prices)
    price_high = max(prices)
    if price_high <= price_low:
        raise ValueError("market packet candle price range must be positive")

    left = 48
    right = width - 24
    top = 24
    bottom = height - 40
    plot_width = right - left
    plot_height = bottom - top
    if plot_width < len(candles) * 2:
        raise ValueError("chart width is too small for the packet candle count")

    pixels = bytearray(BACKGROUND * (width * height))
    _vertical(pixels, width, height, left, top, bottom, AXIS)
    _rectangle(pixels, width, height, left, bottom, right, bottom, AXIS)

    def price_y(value: float) -> int:
        ratio = (price_high - value) / (price_high - price_low)
        return top + round(ratio * plot_height)

    slot = plot_width / len(candles)
    body_half_width = max(1, min(4, int(slot // 3)))
    for index, candle in enumerate(candles):
        x = left + min(plot_width, round((index + 0.5) * slot))
        colour = DEVELOPING if index == len(candles) - 1 else (UP if candle.close >= candle.open else DOWN)
        _vertical(pixels, width, height, x, price_y(candle.high), price_y(candle.low), colour)
        open_y = price_y(candle.open)
        close_y = price_y(candle.close)
        if open_y == close_y:
            _rectangle(pixels, width, height, x - body_half_width, open_y, x + body_half_width, open_y, colour)
        else:
            _rectangle(pixels, width, height, x - body_half_width, open_y, x + body_half_width, close_y, colour)

    png_bytes = _png(width, height, pixels)
    png_hash = sha256(png_bytes).hexdigest()
    return MarketChart(
        chart_id=f"mc_{packet.content_hash[:24]}",
        packet_id=packet.packet_id,
        packet_content_hash=packet.content_hash,
        png_sha256=png_hash,
        png_bytes=png_bytes,
        width=width,
        height=height,
    )
