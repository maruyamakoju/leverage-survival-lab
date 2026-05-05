"""Binance の trade stream を購読し、tick を yield する。

地域によっては fstream.binance.com (Futures) がブロックされる。
spot stream (stream.binance.com) は広く利用可能で、価格は perp と
0.05% 以内で追従するため、paper trading の現在価格としては十分。

イベント形式 (aggTrade): { "e": "aggTrade", "p": "59000.0", "q": "0.001", "T": 1700000000000, ... }
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import websockets

logger = logging.getLogger(__name__)

# 優先度順: spot 優先(地域制限が少ない)。futures は試行の上 fallback。
BINANCE_STREAM_URLS = [
    "wss://stream.binance.com:9443/ws",   # spot
    "wss://fstream.binance.com/ws",        # USDT-M perp(地域制限あり)
]


async def _connect_with_fallback(symbol: str) -> tuple[Any, str]:
    """利用可能な stream に接続。connection と source ラベルを返す。"""
    last_err: Exception | None = None
    for base in BINANCE_STREAM_URLS:
        url = f"{base}/{symbol.lower()}@aggTrade"
        try:
            ws = await asyncio.wait_for(
                websockets.connect(url, ping_interval=20, ping_timeout=20),
                timeout=8,
            )
            label = "spot" if "9443" in base else "perp"
            logger.info("connected to %s (%s)", url, label)
            return ws, label
        except (TimeoutError, OSError, websockets.exceptions.WebSocketException) as e:
            last_err = e
            logger.warning("failed to connect %s: %s", url, e)
    raise RuntimeError(f"all binance streams unreachable; last error: {last_err}")


async def binance_trade_stream(symbol: str = "btcusdt") -> AsyncIterator[dict[str, Any]]:
    """`symbol` の aggTrade イベントを yield する。再接続は外側で。"""
    ws, source = await _connect_with_fallback(symbol)
    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("e") != "aggTrade":
                continue
            ts_ms = int(data.get("T", 0))
            yield {
                "p": data["p"],   # price (str)
                "q": data["q"],   # quantity (str)
                "T": ts_ms,
                "source": source,
                "ts": datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat() if ts_ms else None,
            }
    finally:
        await ws.close()
