"""バックテスト実行器 — 単一資産・単一戦略・固定パラメータの最小ループ。

look-ahead 防止: シグナルは bar t の close で生成、約定は bar t+1 の open。
清算判定は当該バーの High/Low を使う。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from ..engine.leverage import FeeModel, LeverageEngine, Side
from ..strategies.base import Strategy


@dataclass
class BacktestConfig:
    initial_equity: float = 1_000_000.0
    leverage: float = 10.0
    stop_loss: float | None = -0.02   # -2% (notional比, 価格変動率)
    take_profit: float | None = None  # +x% (利確)
    risk_fraction: float = 1.0        # equity の何割を IM に充てるか
    fee: FeeModel = field(default_factory=FeeModel)
    funding_rates: pd.Series | None = None  # ts -> rate(8h)。Noneなら 0。
    bust_threshold: float = 0.10
    side_mode: Literal["both", "long_only", "short_only"] = "both"


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    n_liquidations: int
    final_equity: float
    is_bust: bool
    total_fees: float
    total_funding: float


def _stop_price(entry: float, side: Side, sl_pct: float) -> float:
    """SL 価格(価格変動率指定)。sl_pct は負の値で渡す前提(例: -0.02)。"""
    return entry * (1.0 + side.sign * sl_pct)


def _tp_price(entry: float, side: Side, tp_pct: float) -> float:
    return entry * (1.0 + side.sign * tp_pct)


def run_backtest(df: pd.DataFrame, signal: pd.Series, config: BacktestConfig) -> BacktestResult:
    """OHLCV と Signal を受け取り、レバレッジエンジンを通してバックテストする。

    df は ['open','high','low','close','volume'] を持ち、index は時系列。
    signal は同じ index を持つ {-1,0,+1} の系列。
    """
    if not df.index.equals(signal.index):
        raise ValueError("df and signal must share the same index")
    if not {"open", "high", "low", "close"}.issubset(df.columns):
        raise ValueError("df must have OHLC columns")

    eng = LeverageEngine(initial_equity=config.initial_equity, fee=config.fee)
    equity_curve = np.empty(len(df), dtype=np.float64)
    # 各 trade レコードはすべて同じキー集合を持たせる(pd.DataFrame 構築の安定化)
    trades: list[dict[str, float | str | int | None]] = []
    _trade_keys = ("bar", "action", "side", "price", "pnl")

    def _record(bar: int, action: str, side: str, price: float, pnl: float | None = None) -> None:
        trades.append({"bar": bar, "action": action, "side": side, "price": float(price),
                       "pnl": float(pnl) if pnl is not None else None})

    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    sigs = signal.to_numpy()
    fund = (
        config.funding_rates.reindex(df.index, fill_value=0.0).to_numpy()
        if config.funding_rates is not None
        else np.zeros(len(df))
    )

    n = len(df)
    for i in range(n):
        # 1) ファンディング適用(8h単位の rate を bar 解像度に分割するのは外で済ませる前提)
        if eng.position is not None and fund[i] != 0.0:
            eng.apply_funding(mark=opens[i], rate=float(fund[i]))

        # 2) 当該バー中の清算/SL/TP判定(High/Lowに対して)
        if eng.position is not None:
            pos = eng.position
            # 清算が最優先
            if pos.is_liquidated(bar_high=highs[i], bar_low=lows[i]):
                eng.force_liquidate()
                _record(i, "liquidated", pos.side.value, pos.liq_price)
            else:
                # SL / TP
                exit_price: float | None = None
                exit_kind: str | None = None
                if config.stop_loss is not None:
                    sl = _stop_price(pos.entry, pos.side, config.stop_loss)
                    if (pos.side is Side.LONG and lows[i] <= sl) or (
                        pos.side is Side.SHORT and highs[i] >= sl
                    ):
                        exit_price = sl
                        exit_kind = "stop_loss"
                if config.take_profit is not None and exit_price is None:
                    tp = _tp_price(pos.entry, pos.side, config.take_profit)
                    if (pos.side is Side.LONG and highs[i] >= tp) or (
                        pos.side is Side.SHORT and lows[i] <= tp
                    ):
                        exit_price = tp
                        exit_kind = "take_profit"
                if exit_price is not None and exit_kind is not None:
                    net = eng.close(price=exit_price, is_stop=(exit_kind == "stop_loss"))
                    _record(i, exit_kind, pos.side.value, exit_price, pnl=net)

        # 3) シグナルに従って次バー始値で約定する想定 → ここでは「翌バー i+1 の open」を予約
        #    実装上は次のループの先頭で約定させる方が単純なので、
        #    ここでは単純に「現バー i のシグナル → 現バー i の close で発注」モデルを採用し、
        #    実際の約定は次バー i+1 の open で行う。
        if i + 1 < n and eng.position is None and sigs[i] != 0:
            target_side = Side.LONG if sigs[i] > 0 else Side.SHORT
            if config.side_mode == "long_only" and target_side is Side.SHORT:
                pass
            elif config.side_mode == "short_only" and target_side is Side.LONG:
                pass
            else:
                # 翌バー open で約定 → 翌イテレーションで反映するため、
                # ここでフラグだけ立てて次ループ先頭で open する。
                # 単純化のため、次ループ先頭で sigs[i-1] を見て約定する書き方ではなく、
                # ここで直接「次バーの始値で開く」操作をしてしまう(同じ意味)。
                next_open = float(opens[i + 1])
                eng.open(side=target_side, price=next_open, leverage=config.leverage,
                         risk_fraction=config.risk_fraction, bar=i + 1)
                _record(i + 1, "open", target_side.value, next_open)

        # 4) equity 記録(現ポジの含み損益込みで mark)
        unrealized = eng.position.unrealized_pnl(closes[i]) if eng.position else 0.0
        equity_curve[i] = eng.equity + unrealized

        if eng.is_bust(threshold=config.bust_threshold):
            # bust 後は強制クローズしてその後は equity 横ばい
            if eng.position is not None:
                eng.close(price=closes[i])
            equity_curve[i:] = eng.equity
            break

    eq_series = pd.Series(equity_curve, index=df.index, name="equity")
    # 空 trades の場合の DataFrame コンストラクタ安定化のため、明示的にカラム指定
    trade_df = pd.DataFrame(trades, columns=list(_trade_keys)) if trades else pd.DataFrame(columns=list(_trade_keys))
    return BacktestResult(
        equity_curve=eq_series,
        trades=trade_df,
        n_liquidations=eng.n_liquidations,
        final_equity=float(eq_series.iloc[-1]),
        is_bust=eng.is_bust(threshold=config.bust_threshold),
        total_fees=eng.total_fees,
        total_funding=eng.total_funding,
    )
