"""ペーパートレード(仮想金)のコアロジック。

設計方針:
- LeverageEngine をラップし、高レベル API (long / short / close / status) を提供
- 価格は外部から `tick(price, high, low, ts)` で投入する設計(replay/live どちらでも使える)
- Stop loss / take profit はティックごとに自動執行
- セッション履歴を JSON で保存可能
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..engine.leverage import FeeModel, LeverageEngine, Side


@dataclass
class TickRecord:
    ts: str
    price: float
    equity: float
    position_side: str | None
    position_qty: float
    unrealized_pnl: float


@dataclass
class TradeRecord:
    ts: str
    action: str           # open_long / open_short / close / liquidated / stop_loss / take_profit
    price: float
    qty: float
    leverage: float
    pnl: float | None = None
    note: str = ""


@dataclass
class PaperBroker:
    """ペーパートレード口座。LeverageEngine の上に座る。"""

    initial_equity: float = 1_000_000.0
    fee: FeeModel = field(default_factory=FeeModel)
    default_leverage: float = 10.0
    default_size_pct: float = 1.0      # equity の何割を IM に充てるか
    sl_pct: float | None = None         # 価格逆行 % で SL
    tp_pct: float | None = None         # 価格順行 % で TP

    engine: LeverageEngine = field(init=False)
    last_price: float = field(default=0.0, init=False)
    trades: list[TradeRecord] = field(default_factory=list, init=False)
    ticks: list[TickRecord] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.engine = LeverageEngine(initial_equity=self.initial_equity, fee=self.fee)

    # ---- helpers ----
    @property
    def equity(self) -> float:
        return self.engine.equity

    @property
    def position(self):
        return self.engine.position

    @property
    def unrealized_pnl(self) -> float:
        if self.engine.position is None:
            return 0.0
        return self.engine.position.unrealized_pnl(self.last_price)

    @property
    def total_value(self) -> float:
        return self.equity + self.unrealized_pnl

    def _record(self, action: str, price: float, qty: float, leverage: float,
                pnl: float | None = None, note: str = "") -> None:
        self.trades.append(TradeRecord(
            ts=datetime.now(UTC).isoformat(),
            action=action, price=price, qty=qty, leverage=leverage,
            pnl=pnl, note=note,
        ))

    # ---- commands ----
    def _pre_check(self, lev: float, rf: float) -> str | None:
        """事前に「実質的に瞬時清算」になる組み合わせを reject。"""
        from ..engine.leverage import maintenance_margin_rate
        notional = self.equity * rf * lev
        mm = maintenance_margin_rate(notional)
        if mm >= 1.0 / lev:
            max_lev = int(1.0 / mm)
            return (f"!! REJECTED: notional ${notional:,.0f} requires mm={mm*100:.1f}% "
                    f"which exceeds 1/{lev:.0f}={1.0/lev*100:.2f}%. "
                    f"At this size, max leverage is ~{max_lev}x. "
                    f"Reduce 'size' or 'lev'.")
        return None

    def long(self, size_pct: float | None = None, leverage: float | None = None) -> str:
        if self.engine.position is not None:
            return "already in position; close first"
        L = leverage if leverage is not None else self.default_leverage
        rf = size_pct if size_pct is not None else self.default_size_pct
        warn = self._pre_check(L, rf)
        if warn:
            return warn
        try:
            self.engine.open(side=Side.LONG, price=self.last_price, leverage=L, risk_fraction=rf)
        except (RuntimeError, ValueError) as e:
            return f"error: {e}"
        pos = self.engine.position
        assert pos is not None
        self._record("open_long", self.last_price, pos.qty, L,
                     note=f"liq={pos.liq_price:.2f}")
        return f"opened LONG {pos.qty:.6f} @ {self.last_price:.2f}, lev={L}x, liq={pos.liq_price:.2f}"

    def short(self, size_pct: float | None = None, leverage: float | None = None) -> str:
        if self.engine.position is not None:
            return "already in position; close first"
        L = leverage if leverage is not None else self.default_leverage
        rf = size_pct if size_pct is not None else self.default_size_pct
        warn = self._pre_check(L, rf)
        if warn:
            return warn
        try:
            self.engine.open(side=Side.SHORT, price=self.last_price, leverage=L, risk_fraction=rf)
        except (RuntimeError, ValueError) as e:
            return f"error: {e}"
        pos = self.engine.position
        assert pos is not None
        self._record("open_short", self.last_price, pos.qty, L,
                     note=f"liq={pos.liq_price:.2f}")
        return f"opened SHORT {pos.qty:.6f} @ {self.last_price:.2f}, lev={L}x, liq={pos.liq_price:.2f}"

    def close(self) -> str:
        if self.engine.position is None:
            return "no open position"
        pos = self.engine.position
        side, qty, lev = pos.side.value, pos.qty, pos.leverage
        net = self.engine.close(price=self.last_price)
        self._record("close", self.last_price, qty, lev, pnl=net)
        return f"closed {side.upper()} {qty:.6f} @ {self.last_price:.2f}, pnl={net:+.2f}"

    def set_sl(self, pct: float | None) -> str:
        self.sl_pct = pct
        return f"stop loss = {pct*100:.2f}%" if pct is not None else "stop loss cleared"

    def set_tp(self, pct: float | None) -> str:
        self.tp_pct = pct
        return f"take profit = {pct*100:.2f}%" if pct is not None else "take profit cleared"

    def set_leverage(self, lev: float) -> str:
        self.default_leverage = lev
        return f"default leverage = {lev}x"

    def set_size(self, size_pct: float) -> str:
        self.default_size_pct = size_pct
        return f"default size = {size_pct*100:.0f}%"

    # ---- tick processing ----
    def tick(self, *, price: float, high: float | None = None, low: float | None = None,
             ts: str | None = None) -> list[str]:
        """1 tick 進める。高低を渡せば SL/TP/清算を bar 内で判定する。"""
        msgs: list[str] = []
        self.last_price = price
        h = high if high is not None else price
        lo = low if low is not None else price

        if self.engine.position is not None:
            pos = self.engine.position
            # 1) liquidation
            if pos.is_liquidated(bar_high=h, bar_low=lo):
                liq_p = pos.liq_price
                qty, lev = pos.qty, pos.leverage
                self.engine.force_liquidate()
                self._record("liquidated", liq_p, qty, lev, pnl=-pos.initial_margin)
                msgs.append(f"!! LIQUIDATED at {liq_p:.2f}, equity now {self.equity:.2f}")
            else:
                # 2) SL
                if self.sl_pct is not None:
                    sl_price = pos.entry * (1.0 + pos.side.sign * self.sl_pct)
                    hit = (pos.side is Side.LONG and lo <= sl_price) or (
                        pos.side is Side.SHORT and h >= sl_price)
                    if hit:
                        net = self.engine.close(price=sl_price, is_stop=True)
                        self._record("stop_loss", sl_price, pos.qty, pos.leverage, pnl=net)
                        msgs.append(f"~ SL hit at {sl_price:.2f}, pnl={net:+.2f}")
                # 3) TP
                if self.tp_pct is not None and self.engine.position is not None:
                    pos2 = self.engine.position
                    tp_price = pos2.entry * (1.0 + pos2.side.sign * self.tp_pct)
                    hit_tp = (pos2.side is Side.LONG and h >= tp_price) or (
                        pos2.side is Side.SHORT and lo <= tp_price)
                    if hit_tp:
                        net = self.engine.close(price=tp_price)
                        self._record("take_profit", tp_price, pos2.qty, pos2.leverage, pnl=net)
                        msgs.append(f"+ TP hit at {tp_price:.2f}, pnl={net:+.2f}")

        # tick record
        pos = self.engine.position
        self.ticks.append(TickRecord(
            ts=ts or datetime.now(UTC).isoformat(),
            price=price, equity=self.equity,
            position_side=pos.side.value if pos else None,
            position_qty=pos.qty if pos else 0.0,
            unrealized_pnl=self.unrealized_pnl,
        ))
        return msgs

    # ---- persistence ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_equity": self.initial_equity,
            "default_leverage": self.default_leverage,
            "default_size_pct": self.default_size_pct,
            "sl_pct": self.sl_pct,
            "tp_pct": self.tp_pct,
            "equity": self.equity,
            "last_price": self.last_price,
            "n_trades": len(self.trades),
            "n_ticks": len(self.ticks),
            "n_liquidations": self.engine.n_liquidations,
            "trades": [asdict(t) for t in self.trades],
            "saved_at": datetime.now(UTC).isoformat(),
        }

    def save(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass
class TradingSession:
    """REPL ループ。replay or live フィードを差し替え可能。"""

    broker: PaperBroker
    feed: Any   # iterator yielding tick dicts {price, high, low, ts}
    auto_advance: int = 0   # >0 なら毎回 N ticks 自動進行(no input prompt)

    def step(self) -> tuple[dict, list[str]]:
        """1 tick 進める。"""
        tick_data = next(self.feed)
        msgs = self.broker.tick(**tick_data)
        return tick_data, msgs
