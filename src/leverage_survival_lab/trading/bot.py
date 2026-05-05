"""AI トレーダーボット — Web GUI と同じ口座を裏で操作する。

設計:
- WebSocket /ws で state を受信(価格・ポジション・残高をリアルタイム把握)
- 価格履歴から短期モメンタム + 平均回帰の z-score を計算
- 現状ノーポジなら判断 → /api/long or /api/short を叩く
- ポジション中は SL/TP の自動執行に任せ、時間経過で強制クローズ
- 全判断を日本語でログ出力(画面下のステータス + ファイル)

戦略パラメータ(アグレッシブ寄り):
  leverage: 25 倍
  size_pct: 0.30 (30%)
  sl_pct:   1.5%
  tp_pct:   2.5%
  hold_max_ticks: 120 (約 2 分)
  trade_cooldown: 10 ticks(連投防止)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import websockets


@dataclass
class BotConfig:
    base_url: str = "http://127.0.0.1:8765"
    leverage: float = 25.0
    size_pct: float = 0.30
    sl_pct: float = 1.5
    tp_pct: float = 2.5
    hold_max_ticks: int = 120
    cooldown_ticks: int = 10
    z_threshold: float = 1.5      # |z|>this → mean-revert entry
    momentum_threshold: float = 0.0008  # short-term return > this → trend entry
    history_size: int = 60
    log_path: Path = Path("results/ai_trader_log.jsonl")
    bust_at: float = 0.30  # equity が初期の 30% を割ったら停止


class AITrader:
    """単純なハイブリッド戦略の AI トレーダー。"""

    def __init__(self, cfg: BotConfig) -> None:
        self.cfg = cfg
        self.prices: deque[float] = deque(maxlen=cfg.history_size)
        self.last_trade_tick = -10**9
        self.tick_idx = 0
        self.position_opened_at: int | None = None
        self.last_logged_pnl_pct: float = 0.0
        # httpx クライアントは非同期コンテキスト内で初期化(Windows で event loop 問題を避ける)
        self.client: httpx.AsyncClient | None = None
        self.log_path = cfg.log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_equity: float | None = None
        self.stopped = False
        # tick が来てる証跡を残す(debug)
        self.last_heartbeat_tick = 0

    # ---- helpers ----
    def _zscore(self) -> float:
        if len(self.prices) < self.cfg.history_size // 2:
            return 0.0
        arr = list(self.prices)
        mean = sum(arr) / len(arr)
        var = sum((x - mean) ** 2 for x in arr) / len(arr)
        std = var ** 0.5
        if std == 0:
            return 0.0
        return (arr[-1] - mean) / std

    def _short_momentum(self) -> float:
        """直近 5 ティック vs その前 5 ティック の return。"""
        if len(self.prices) < 10:
            return 0.0
        arr = list(self.prices)
        recent = arr[-5:]
        prior = arr[-10:-5]
        return (sum(recent) / 5) / (sum(prior) / 5) - 1.0

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            self.client = httpx.AsyncClient(base_url=self.cfg.base_url, timeout=10)
        r = await self.client.post(path, json=body)
        return r.json()

    async def _log(self, rec: dict[str, Any]) -> None:
        rec = {"ts": datetime.now(UTC).isoformat(), **rec}
        line = json.dumps(rec, ensure_ascii=False)
        print(line, flush=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---- decision ----
    def _decide(self, state: dict[str, Any]) -> tuple[str, str] | None:
        """次のアクションを決定。"""
        cfg = self.cfg
        pos = state["position"]

        # 既にポジションがある場合 → 時間切れチェック
        if pos is not None:
            held_ticks = self.tick_idx - (self.position_opened_at or self.tick_idx)
            if held_ticks >= cfg.hold_max_ticks:
                return ("close", f"保有 {held_ticks}t (上限 {cfg.hold_max_ticks}t) 超過")
            return None

        # cooldown 中?
        if self.tick_idx - self.last_trade_tick < cfg.cooldown_ticks:
            return None

        # 履歴が薄ければ何もしない
        if len(self.prices) < self.cfg.history_size // 2:
            return None

        z = self._zscore()
        m = self._short_momentum()

        # 平均回帰: z が極端なら逆張り
        if z > cfg.z_threshold:
            return ("short", f"平均回帰: z={z:+.2f} > {cfg.z_threshold}")
        if z < -cfg.z_threshold:
            return ("long", f"平均回帰: z={z:+.2f} < {-cfg.z_threshold}")

        # 中立域でモメンタムが強ければ順張り
        if abs(z) < 0.5:
            if m > cfg.momentum_threshold:
                return ("long", f"順張り: 5t モメンタム {m*100:+.3f}% > {cfg.momentum_threshold*100:.3f}%")
            if m < -cfg.momentum_threshold:
                return ("short", f"順張り: 5t モメンタム {m*100:+.3f}%")

        return None

    def _safe_params(self, equity: float) -> tuple[float, float]:
        """現状の equity / MM tier に対して安全な (lev, size) を返す。

        cfg の希望値 (lev, size) を起点に、想定元本が MM tier の制約を超えるなら
        size を縮小して 1/lev > mm を満たす最大の size を返す。
        """
        from ..engine.leverage import maintenance_margin_rate
        lev = self.cfg.leverage
        size = self.cfg.size_pct
        # 希望サイズで通れば OK
        notional = equity * size * lev
        mm = maintenance_margin_rate(notional)
        if mm < 1.0 / lev:
            return lev, size
        # サイズを縮めて再計算
        for shrink_pct in (0.20, 0.10, 0.05, 0.02):
            n = equity * shrink_pct * lev
            if maintenance_margin_rate(n) < 1.0 / lev:
                return lev, shrink_pct
        # それでも駄目ならレバを下げる
        return min(lev, 10.0), 0.10

    async def _execute(self, action: str, reason: str, state: dict[str, Any]) -> None:
        cfg = self.cfg
        price = state["price"]
        # cooldown は試行段階で常に更新(reject でも連投しない)
        self.last_trade_tick = self.tick_idx

        if action in ("long", "short"):
            lev, size = self._safe_params(state["equity"])
            await self._post("/api/sl", {"pct": cfg.sl_pct})
            await self._post("/api/tp", {"pct": cfg.tp_pct})
            path = "/api/long" if action == "long" else "/api/short"
            r = await self._post(path, {"size_pct": size, "leverage": lev})
            msg = r.get("message", "")
            ok = "取引拒否" not in msg and "エラー" not in msg
            if ok:
                self.position_opened_at = self.tick_idx
            await self._log({"action": f"open_{action}", "reason": reason, "price": price,
                              "lev": lev, "size": size, "ok": ok, "result": msg})
        elif action == "close":
            r = await self._post("/api/close", {})
            self.position_opened_at = None
            await self._log({"action": "close", "reason": reason, "price": price,
                              "result": r.get("message")})

    # ---- main loop ----
    async def consume_state(self, state: dict[str, Any]) -> None:
        if self.stopped:
            return
        price = state.get("price") or 0
        if price <= 0:
            return
        self.tick_idx += 1
        self.prices.append(price)
        # 200 ticks ごとに heartbeat ログ
        if self.tick_idx - self.last_heartbeat_tick >= 200:
            self.last_heartbeat_tick = self.tick_idx
            await self._log({"action": "HEARTBEAT", "tick": self.tick_idx,
                              "price": price, "pos": state["position"] is not None,
                              "equity": state["equity"], "total": state["total_value"]})
        if self.initial_equity is None:
            self.initial_equity = state["initial_equity"]

        # bust check
        total = state["total_value"]
        if self.initial_equity and total <= self.initial_equity * self.cfg.bust_at:
            await self._log({"action": "STOP", "reason": f"残高 ${total:,.0f} が初期の {self.cfg.bust_at*100:.0f}% を割った",
                              "total_value": total})
            self.stopped = True
            return

        # 同期: ローカルの position_opened_at と実際のポジ状態のズレを修正
        if state["position"] is None and self.position_opened_at is not None:
            # SL/TP が発火して閉じている可能性
            self.position_opened_at = None
        decision = self._decide(state)
        if decision is None:
            return
        action, reason = decision
        try:
            await self._execute(action, reason, state)
        except Exception as e:
            await self._log({"action": "ERROR", "reason": reason, "error": str(e)})

    async def run(self) -> None:
        """WebSocket 接続して state を受信し続ける。"""
        ws_url = self.cfg.base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        await self._log({"action": "START", "config": {
            "leverage": self.cfg.leverage, "size_pct": self.cfg.size_pct,
            "sl_pct": self.cfg.sl_pct, "tp_pct": self.cfg.tp_pct,
        }})
        # 接続リトライループ
        while not self.stopped:
            try:
                async with websockets.connect(ws_url) as ws:
                    async for raw in ws:
                        if self.stopped:
                            break
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if msg.get("type") == "state":
                            await self.consume_state(msg["data"])
            except (websockets.exceptions.WebSocketException, OSError) as e:
                await self._log({"action": "WS_RECONNECT", "error": str(e)})
                await asyncio.sleep(2.0)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8765")
    p.add_argument("--leverage", type=float, default=25.0)
    p.add_argument("--size", type=float, default=0.30, help="0..1")
    p.add_argument("--sl", type=float, default=1.5)
    p.add_argument("--tp", type=float, default=2.5)
    p.add_argument("--hold", type=int, default=120)
    p.add_argument("--cooldown", type=int, default=10)
    p.add_argument("--z-threshold", type=float, default=1.5)
    p.add_argument("--bust-at", type=float, default=0.30,
                   help="残高がこの比率を割ったら停止")
    p.add_argument("--log", default="results/ai_trader_log.jsonl")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = BotConfig(
        base_url=args.base_url, leverage=args.leverage, size_pct=args.size,
        sl_pct=args.sl, tp_pct=args.tp,
        hold_max_ticks=args.hold, cooldown_ticks=args.cooldown,
        z_threshold=args.z_threshold, bust_at=args.bust_at,
        log_path=Path(args.log),
    )
    trader = AITrader(cfg)
    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        print("\n[stopped by user]")


if __name__ == "__main__":
    main()
