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
    hold_max_ticks: int = 120          # 後方互換用(0 で無効化、現在は hold_max_seconds 優先)
    hold_max_seconds: int = 600        # 実時間ベースの保有上限(秒)
    cooldown_ticks: int = 10
    cooldown_seconds: int = 30         # 実時間ベースのクールダウン(秒)
    z_threshold: float = 1.5      # |z|>this → mean-revert entry
    momentum_threshold: float = 0.0008  # short-term return > this → trend entry
    history_size: int = 60
    log_path: Path = Path("results/ai_trader_log.jsonl")
    bust_at: float = 0.30
    # 戦略モード: zscore / rsi / momentum
    strategy: str = "zscore"
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    candle_seconds: int = 60     # RSI 用に何秒で1本のロウソクにするか
    bootstrap_parquet: str | None = None  # 起動時に過去 1m データから minute_closes を初期化
    breakout_window: int = 30    # momentum mode で何バーの高安をブレイク判定に使うか


class AITrader:
    """単純なハイブリッド戦略の AI トレーダー。"""

    def __init__(self, cfg: BotConfig) -> None:
        self.cfg = cfg
        self.prices: deque[float] = deque(maxlen=cfg.history_size)
        # ロウソク用: 1 ロウソク = candle_seconds 秒の最後の close
        self.minute_closes: deque[float] = deque(maxlen=200)
        self._cur_candle_close: float | None = None
        self._cur_candle_bucket: int = -1
        self.last_trade_tick = -10**9
        self.last_trade_ts: datetime | None = None
        self.tick_idx = 0
        self.now_ts: datetime | None = None
        self.position_opened_at: int | None = None
        self.position_opened_ts: datetime | None = None
        self.bootstrap_count: int = 0  # bootstrap で注入した candle 数
        self.live_candle_count: int = 0  # 起動後に live で観測した完成 candle 数(累積)
        self.last_logged_pnl_pct: float = 0.0
        # httpx クライアントは非同期コンテキスト内で初期化(Windows で event loop 問題を避ける)
        self.client: httpx.AsyncClient | None = None
        self.log_path = cfg.log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_equity: float | None = None
        self.stopped = False
        # tick が来てる証跡を残す(debug)
        self.last_heartbeat_tick = 0
        # WS state.pos が None を連続で見た回数(SL/TP/清算 検知用)
        self._null_pos_streak: int = 0

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

    def _update_candle(self, price: float, ts_str: str | None) -> None:
        """tick を candle に集約。candle 完成時に minute_closes へ push。"""
        # ts_str を秒単位の bucket に変換
        if not ts_str:
            return
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            bucket = int(ts.timestamp()) // self.cfg.candle_seconds
        except Exception:
            return
        if bucket != self._cur_candle_bucket:
            # 前のバケット完成 → push、live 観測本数をインクリメント
            if self._cur_candle_close is not None:
                self.minute_closes.append(self._cur_candle_close)
                self.live_candle_count += 1
            self._cur_candle_bucket = bucket
        self._cur_candle_close = price

    def _rsi(self) -> float | None:
        """minute_closes から RSI(period) を計算。

        防御的: 値は float に強制変換し、非数値は無視する。長時間ライブで稀に
        deque へ予期せぬ型が混入したことによる TypeError を見たことがある。
        """
        period = self.cfg.rsi_period
        if len(self.minute_closes) < period + 1:
            return None
        try:
            arr = [float(x) for x in self.minute_closes if isinstance(x, int | float)]
        except (TypeError, ValueError):
            return None
        if len(arr) < period + 1:
            return None
        gains: list[float] = []
        losses: list[float] = []
        for i in range(1, len(arr)):
            d = arr[i] - arr[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

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
        """次のアクションを決定。

        重要: state["position"] は WebSocket ブロードキャスト由来でラグがあるため、
        bot 内部の `position_opened_at` を「自分が建玉している」の真値として使う。
        state.position が連続 N ティック None を見せたら SL/TP/清算 で閉じたとみなす。
        """
        cfg = self.cfg
        state_pos = state["position"]

        # 自分の認識でポジションがあるなら
        if self.position_opened_at is not None:
            # state が「ポジなし」を 3t 連続で見せたら → SL/TP/清算 で閉じた
            if state_pos is None:
                self._null_pos_streak += 1
                if self._null_pos_streak >= 3:
                    self.position_opened_at = None
                    self._null_pos_streak = 0
                    self.last_trade_tick = self.tick_idx  # cooldown 開始
                return None
            else:
                self._null_pos_streak = 0

            held_ticks = self.tick_idx - self.position_opened_at
            held_secs: float = 0.0
            if self.position_opened_ts is not None and self.now_ts is not None:
                held_secs = (self.now_ts - self.position_opened_ts).total_seconds()
            # 実時間基準を優先(秒)。未設定/古いプリセット用に hold_max_ticks も保険として残す。
            if cfg.hold_max_seconds > 0 and held_secs >= cfg.hold_max_seconds:
                return ("close", f"保有 {held_secs:.0f}秒 (上限 {cfg.hold_max_seconds}秒) 超過")
            if cfg.hold_max_seconds <= 0 and held_ticks >= cfg.hold_max_ticks:
                return ("close", f"保有 {held_ticks}t (上限 {cfg.hold_max_ticks}t) 超過")

            # RSI 戦略時: RSI が中立(50)に戻ったら early exit
            if cfg.strategy == "rsi" and held_secs >= 60:  # 最低 60秒は保有
                rsi = self._rsi()
                if rsi is not None:
                    side = state_pos.get("side")
                    # SHORT (overbought で建玉) → RSI が 55 を割ったら戻り → 利確
                    if side == "short" and rsi < 55:
                        return ("close", f"RSI 戻り {rsi:.1f} < 55 (SHORT 利確)")
                    # LONG (oversold で建玉) → RSI が 45 を超えたら戻り → 利確
                    if side == "long" and rsi > 45:
                        return ("close", f"RSI 戻り {rsi:.1f} > 45 (LONG 利確)")
            return None

        # ノーポジ(自分の認識上)
        # state.pos が予期せずポジションを示してたら(再起動 + 既存ポジ)→ 引き継ぐ
        if state_pos is not None:
            self.position_opened_at = self.tick_idx
            self.position_opened_ts = self.now_ts
            return None

        # cooldown(実時間 + tick の両方を満たすまで再エントリしない)
        if self.tick_idx - self.last_trade_tick < cfg.cooldown_ticks:
            return None
        if (cfg.cooldown_seconds > 0 and self.last_trade_ts is not None
                and self.now_ts is not None
                and (self.now_ts - self.last_trade_ts).total_seconds() < cfg.cooldown_seconds):
            return None

        # ---- RSI mode ---- (トーナメント勝者)
        if cfg.strategy == "rsi":
            rsi = self._rsi()
            if rsi is None:
                return None
            if rsi < cfg.rsi_oversold:
                return ("long", f"RSI={rsi:.1f} < {cfg.rsi_oversold} (oversold)")
            if rsi > cfg.rsi_overbought:
                return ("short", f"RSI={rsi:.1f} > {cfg.rsi_overbought} (overbought)")
            return None

        # ---- momentum mode ---- (ブレイクアウト追従)
        if cfg.strategy == "momentum":
            if len(self.minute_closes) < cfg.breakout_window + 1:
                return None
            # bootstrap した古い candle と現在価格の段差で偽ブレイクが連発するのを防ぐ:
            # bot 自身が live で観測した完成 candle が breakout_window+1 本溜まるまで判定を保留。
            # (deque は maxlen 固定なので len(minute_closes) - bootstrap_count では常に 0 になる罠を避けて
            #  live_candle_count を別カウンタで累積する。)
            if self.live_candle_count < cfg.breakout_window + 1:
                return None
            arr = list(self.minute_closes)
            window = arr[-cfg.breakout_window - 1 : -1]   # 直近 N バー(現在は除く)
            current = arr[-1]
            hi = max(window)
            lo = min(window)
            # ブレイクアウト判定: 0.05% 以上の超過で確定(ノイズ除外)
            buf = 0.0005
            if current > hi * (1 + buf):
                return ("long", f"BO上抜け: {current:.0f} > {hi:.0f} (×{cfg.breakout_window}本高値)")
            if current < lo * (1 - buf):
                return ("short", f"BO下抜け: {current:.0f} < {lo:.0f} (×{cfg.breakout_window}本安値)")
            return None

        # ---- zscore (デフォルト) ----
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
        self.last_trade_ts = self.now_ts

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
                self.position_opened_ts = self.now_ts
            await self._log({"action": f"open_{action}", "reason": reason, "price": price,
                              "lev": lev, "size": size, "ok": ok, "result": msg})
        elif action == "close":
            r = await self._post("/api/close", {})
            self.position_opened_at = None
            self.position_opened_ts = None
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
        # 実時間 now_ts を毎 tick で更新(hold/cooldown の実時間判定に使う)
        ts_str = state.get("ts")
        if ts_str:
            try:
                self.now_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        if self.now_ts is None:
            self.now_ts = datetime.now(UTC)
        # candle aggregator(RSI 用)
        if ts_str:
            self._update_candle(price, ts_str)
        # 200 ticks ごとに heartbeat ログ
        if self.tick_idx - self.last_heartbeat_tick >= 200:
            self.last_heartbeat_tick = self.tick_idx
            extra = {}
            if self.cfg.strategy == "rsi":
                rsi = self._rsi()
                extra["rsi"] = round(rsi, 2) if rsi is not None else None
                extra["candles"] = len(self.minute_closes)
            await self._log({"action": "HEARTBEAT", "tick": self.tick_idx,
                              "price": price, "pos": state["position"] is not None,
                              "equity": state["equity"], "total": state["total_value"],
                              **extra})
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
        try:
            decision = self._decide(state)
        except Exception as e:
            await self._log({"action": "DECIDE_ERROR", "error": str(e),
                              "type": type(e).__name__, "tick": self.tick_idx})
            return
        if decision is None:
            return
        action, reason = decision
        try:
            await self._execute(action, reason, state)
        except Exception as e:
            await self._log({"action": "ERROR", "reason": reason, "error": str(e)})

    def _bootstrap_candles(self) -> int:
        """parquet から最新の close 価格を minute_closes に注入。"""
        if not self.cfg.bootstrap_parquet:
            return 0
        try:
            import pandas as pd
            df = pd.read_parquet(self.cfg.bootstrap_parquet)
            # 最新 200 本(1m足前提)を注入
            for px in df["close"].tail(200).tolist():
                self.minute_closes.append(float(px))
            self.bootstrap_count = len(self.minute_closes)
            return self.bootstrap_count
        except Exception as e:
            print(f"bootstrap failed: {e}", flush=True)
            return 0

    async def run(self) -> None:
        """WebSocket 接続して state を受信し続ける。"""
        ws_url = self.cfg.base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        bootstrap_n = self._bootstrap_candles()
        await self._log({"action": "START", "config": {
            "leverage": self.cfg.leverage, "size_pct": self.cfg.size_pct,
            "sl_pct": self.cfg.sl_pct, "tp_pct": self.cfg.tp_pct,
            "strategy": self.cfg.strategy,
            "bootstrap_candles": bootstrap_n,
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


PRESETS: dict[str, dict[str, Any]] = {
    # results/tournament_summary.parquet の真の勝者(random を除く実戦略)。
    # rsi @ 3x, SL=-3% は score 0.273, win_rate 52%, survival 100%, median_ret +1.15%。
    "tournament-rsi": dict(
        strategy="rsi", leverage=3.0, size=0.4, sl=3.0, tp=100.0,
        rsi_period=14, rsi_oversold=30.0, rsi_overbought=70.0,
        hold=0,  # 実時間ベース(hold_max_seconds)を優先
    ),
    # breakout 系の最良(breakout @ 1x, SL=-5%, score 0.233)。
    # momentum mode を 1x で安全に試す。
    "tournament-breakout": dict(
        strategy="momentum", leverage=1.0, size=0.5, sl=5.0, tp=100.0,
        breakout_window=30,
        hold=0,
    ),
    # 高ボラ寄り検証用:breakout@2x sl=-5% (score 0.222)。
    "tournament-breakout-2x": dict(
        strategy="momentum", leverage=2.0, size=0.5, sl=5.0, tp=100.0,
        breakout_window=30,
        hold=0,
    ),
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8765")
    p.add_argument("--preset", choices=sorted(PRESETS), default=None,
                   help="トーナメント勝者プリセットでパラメータを上書き")
    p.add_argument("--strategy", choices=["zscore", "rsi", "momentum"], default="zscore")
    p.add_argument("--leverage", type=float, default=25.0)
    p.add_argument("--size", type=float, default=0.30, help="0..1")
    p.add_argument("--sl", type=float, default=1.5)
    p.add_argument("--tp", type=float, default=2.5)
    p.add_argument("--hold", type=int, default=120,
                   help="保有上限の tick 数(0 で無効、--hold-secs を使用)")
    p.add_argument("--hold-secs", type=int, default=600,
                   help="保有上限の秒数(>0 で有効、tick より優先)")
    p.add_argument("--cooldown", type=int, default=10,
                   help="再エントリ猶予の tick 数")
    p.add_argument("--cooldown-secs", type=int, default=30,
                   help="再エントリ猶予の秒数(tick と AND で判定)")
    p.add_argument("--z-threshold", type=float, default=1.5)
    p.add_argument("--rsi-period", type=int, default=14)
    p.add_argument("--rsi-oversold", type=float, default=30.0)
    p.add_argument("--rsi-overbought", type=float, default=70.0)
    p.add_argument("--candle-seconds", type=int, default=60)
    p.add_argument("--bootstrap", default=None,
                   help="起動時に minute_closes に注入する 1m parquet パス")
    p.add_argument("--breakout-window", type=int, default=30,
                   help="momentum mode で N 分間の高安ブレイク判定に使うバー数")
    p.add_argument("--bust-at", type=float, default=0.30,
                   help="残高がこの比率を割ったら停止")
    p.add_argument("--log", default="results/ai_trader_log.jsonl")
    args = p.parse_args()
    if args.preset:
        for k, v in PRESETS[args.preset].items():
            setattr(args, k, v)
        print(f"[preset] {args.preset}: {PRESETS[args.preset]}", flush=True)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = BotConfig(
        base_url=args.base_url, leverage=args.leverage, size_pct=args.size,
        sl_pct=args.sl, tp_pct=args.tp,
        hold_max_ticks=args.hold, hold_max_seconds=args.hold_secs,
        cooldown_ticks=args.cooldown, cooldown_seconds=args.cooldown_secs,
        z_threshold=args.z_threshold, bust_at=args.bust_at,
        strategy=args.strategy, rsi_period=args.rsi_period,
        rsi_oversold=args.rsi_oversold, rsi_overbought=args.rsi_overbought,
        candle_seconds=args.candle_seconds,
        bootstrap_parquet=args.bootstrap,
        breakout_window=args.breakout_window,
        log_path=Path(args.log),
    )
    trader = AITrader(cfg)
    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        print("\n[stopped by user]")


if __name__ == "__main__":
    main()
