"""FastAPI app for live paper trading GUI.

Architecture:
- Single global PaperBroker (per-process, in-memory).
- Binance WebSocket subscriber runs as asyncio background task and feeds
  price ticks to the broker.
- Browser opens / and gets the HTML.
- Browser opens WebSocket /ws → backend pushes state JSON on every tick
  and after every trade action.
- Trade actions are POST /api/* endpoints that mutate the broker and
  trigger an immediate broadcast.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..engine.leverage import maintenance_margin_rate
from ..trading.paper import PaperBroker
from .binance_ws import binance_trade_stream

logger = logging.getLogger(__name__)


class AppState:
    """Per-process singleton holding the broker and connected clients."""

    def __init__(self) -> None:
        self.broker = PaperBroker(initial_equity=1_000_000.0,
                                   default_leverage=10.0,
                                   default_size_pct=0.5)
        self.connections: set[WebSocket] = set()
        self.symbol: str = "btcusdt"
        self.last_event: dict[str, Any] = {"type": "init"}
        self.lock = asyncio.Lock()

    def snapshot(self) -> dict[str, Any]:
        b = self.broker
        pos = b.position
        return {
            "ts": b.ticks[-1].ts if b.ticks else None,
            "price": b.last_price,
            "initial_equity": b.initial_equity,
            "equity": b.equity,
            "unrealized_pnl": b.unrealized_pnl,
            "total_value": b.total_value,
            "pnl_pct": (b.total_value / b.initial_equity - 1.0) * 100 if b.initial_equity else 0.0,
            "default_leverage": b.default_leverage,
            "default_size_pct": b.default_size_pct,
            "sl_pct": b.sl_pct,
            "tp_pct": b.tp_pct,
            "position": ({
                "side": pos.side.value,
                "qty": pos.qty,
                "entry": pos.entry,
                "leverage": pos.leverage,
                "liq_price": pos.liq_price,
                "initial_margin": pos.initial_margin,
                "liq_distance_pct": (
                    abs(b.last_price - pos.liq_price) / b.last_price * 100 if b.last_price else 0.0
                ),
            } if pos else None),
            "n_trades": len(b.trades),
            "n_liquidations": b.engine.n_liquidations,
            "trades_recent": [
                {"ts": t.ts, "action": t.action, "price": t.price, "qty": t.qty,
                 "leverage": t.leverage, "pnl": t.pnl}
                for t in b.trades[-30:]
            ],
            "last_event": self.last_event,
        }


state = AppState()


async def broadcast(msg: dict[str, Any]) -> None:
    if not state.connections:
        return
    payload = json.dumps(msg)
    dead: list[WebSocket] = []
    for ws in list(state.connections):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        state.connections.discard(ws)


async def price_stream_task() -> None:
    """Binance trade ストリームを購読し、broker に tick を渡す。"""
    while True:
        try:
            async for tick in binance_trade_stream(state.symbol):
                price = float(tick["p"])
                # broker tick (intra-tick range = price 単点なので high=low=price)
                async with state.lock:
                    msgs = state.broker.tick(price=price, high=price, low=price, ts=tick.get("ts"))
                if msgs:
                    state.last_event = {"type": "auto", "messages": msgs}
                await broadcast({"type": "state", "data": state.snapshot()})
        except Exception as e:
            logger.warning("price stream error: %s; retrying in 3s", e)
            await asyncio.sleep(3.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(price_stream_task())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Leverage Survival Lab — Paper Trading", lifespan=lifespan)

# Serve static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = static_dir / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/state")
async def get_state() -> JSONResponse:
    return JSONResponse(state.snapshot())


@app.post("/api/long")
async def api_long(payload: dict[str, Any] | None = None) -> JSONResponse:
    payload = payload or {}
    size = payload.get("size_pct")
    lev = payload.get("leverage")
    async with state.lock:
        msg = state.broker.long(size_pct=size, leverage=lev)
    state.last_event = {"type": "user", "action": "long", "message": msg}
    snap = state.snapshot()
    await broadcast({"type": "state", "data": snap})
    return JSONResponse({"message": msg, "state": snap})


@app.post("/api/short")
async def api_short(payload: dict[str, Any] | None = None) -> JSONResponse:
    payload = payload or {}
    size = payload.get("size_pct")
    lev = payload.get("leverage")
    async with state.lock:
        msg = state.broker.short(size_pct=size, leverage=lev)
    state.last_event = {"type": "user", "action": "short", "message": msg}
    snap = state.snapshot()
    await broadcast({"type": "state", "data": snap})
    return JSONResponse({"message": msg, "state": snap})


@app.post("/api/close")
async def api_close() -> JSONResponse:
    async with state.lock:
        msg = state.broker.close()
    state.last_event = {"type": "user", "action": "close", "message": msg}
    snap = state.snapshot()
    await broadcast({"type": "state", "data": snap})
    return JSONResponse({"message": msg, "state": snap})


@app.post("/api/sl")
async def api_sl(payload: dict[str, Any]) -> JSONResponse:
    raw = payload.get("pct")
    pct = -abs(float(raw)) / 100 if raw not in (None, "") else None
    async with state.lock:
        msg = state.broker.set_sl(pct)
    state.last_event = {"type": "user", "action": "sl", "message": msg}
    await broadcast({"type": "state", "data": state.snapshot()})
    return JSONResponse({"message": msg})


@app.post("/api/tp")
async def api_tp(payload: dict[str, Any]) -> JSONResponse:
    raw = payload.get("pct")
    pct = abs(float(raw)) / 100 if raw not in (None, "") else None
    async with state.lock:
        msg = state.broker.set_tp(pct)
    state.last_event = {"type": "user", "action": "tp", "message": msg}
    await broadcast({"type": "state", "data": state.snapshot()})
    return JSONResponse({"message": msg})


@app.post("/api/defaults")
async def api_defaults(payload: dict[str, Any]) -> JSONResponse:
    """既定の lev / size_pct を変更。"""
    if "leverage" in payload:
        state.broker.set_leverage(float(payload["leverage"]))
    if "size_pct" in payload:
        state.broker.set_size(float(payload["size_pct"]) / 100)
    await broadcast({"type": "state", "data": state.snapshot()})
    return JSONResponse({"message": "ok"})


@app.post("/api/reset")
async def api_reset(payload: dict[str, Any] | None = None) -> JSONResponse:
    """口座をリセット。"""
    payload = payload or {}
    eq = float(payload.get("equity", 1_000_000.0))
    lev = float(payload.get("leverage", 10.0))
    size = float(payload.get("size_pct", 50.0)) / 100
    async with state.lock:
        state.broker = PaperBroker(initial_equity=eq, default_leverage=lev, default_size_pct=size)
    state.last_event = {"type": "user", "action": "reset",
                        "message": f"reset equity={eq:,.0f} lev={lev}x size={size*100:.0f}%"}
    await broadcast({"type": "state", "data": state.snapshot()})
    return JSONResponse({"message": "ok"})


@app.post("/api/precheck")
async def api_precheck(payload: dict[str, Any]) -> JSONResponse:
    """指定パラメータが reject されるかを返す(ボタン disable 用)。"""
    eq = state.broker.equity
    lev = float(payload.get("leverage", state.broker.default_leverage))
    size = float(payload.get("size_pct", state.broker.default_size_pct * 100)) / 100
    notional = eq * size * lev
    mm = maintenance_margin_rate(notional)
    ok = mm < 1.0 / lev
    return JSONResponse({
        "ok": ok, "notional": notional, "mm": mm, "max_lev_at_size": int(1.0 / mm) if mm > 0 else 999,
    })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    state.connections.add(ws)
    try:
        # 接続直後に現状を送る
        await ws.send_text(json.dumps({"type": "state", "data": state.snapshot()}))
        while True:
            # クライアントからの ping 等を受ける(基本は受信不要)
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        state.connections.discard(ws)


def run() -> None:
    """`lsl-web` エントリポイント。"""
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")


if __name__ == "__main__":
    run()
