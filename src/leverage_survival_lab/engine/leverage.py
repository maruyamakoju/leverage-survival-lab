"""レバレッジエンジン — 証拠金・清算・手数料・スリッページ・ファンディングを厳密にモデル化。

設計上の重要事項:
* Isolated / Cross の両 margin mode に対応
* 清算判定は各バーの High/Low に対して実施(終値だけでは不十分)
* Look-ahead bias 防止: シグナルは bar t の close で生成、約定は bar t+1 の open
* すべての価格・数量は float64。pandas の整合性を保つため Decimal は使わない
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        """long=+1, short=-1。PnL 計算で使う。"""
        return 1 if self is Side.LONG else -1


class MarginMode(str, Enum):
    ISOLATED = "isolated"
    CROSS = "cross"


@dataclass(frozen=True)
class FeeModel:
    """取引手数料・スリッページモデル。

    Binance USDT-M Perp の VIP0 デフォルト値を参考にしている。
    """

    taker_fee: float = 0.0004        # 0.04%
    maker_fee: float = 0.0002        # 0.02%
    slippage: float = 0.0005         # 0.05% (片道, notional比)
    stop_extra_slippage: float = 0.0005  # ストップ約定時の追加スリッページ

    def entry_cost(self, notional: float, *, taker: bool = True) -> float:
        """エントリー時に差し引かれる手数料+スリッページの合計額(USDT)。"""
        fee = self.taker_fee if taker else self.maker_fee
        return notional * (fee + self.slippage)

    def exit_cost(self, notional: float, *, taker: bool = True, is_stop: bool = False) -> float:
        fee = self.taker_fee if taker else self.maker_fee
        slip = self.slippage + (self.stop_extra_slippage if is_stop else 0.0)
        return notional * (fee + slip)


# 維持証拠金率の階層(Binance USDT-M BTC を参考に簡略化)
# notional の上限と維持証拠金率のリスト
DEFAULT_MM_TIERS: Final[tuple[tuple[float, float], ...]] = (
    (50_000, 0.004),
    (250_000, 0.005),
    (1_000_000, 0.01),
    (5_000_000, 0.025),
    (20_000_000, 0.05),
    (float("inf"), 0.10),
)


def maintenance_margin_rate(notional: float, tiers: tuple[tuple[float, float], ...] = DEFAULT_MM_TIERS) -> float:
    """notional に応じた維持証拠金率を返す。"""
    for upper, rate in tiers:
        if notional <= upper:
            return rate
    return tiers[-1][1]  # safety net


def liquidation_price(
    *,
    entry: float,
    leverage: float,
    side: Side,
    mm: float | None = None,
    notional: float | None = None,
) -> float:
    """Isolated 単一ポジションの清算価格を返す。

    Long:  p_liq = entry * (1 - (1/L - mm))
    Short: p_liq = entry * (1 + (1/L - mm))

    100x ロングで mm=0.5% なら、価格が (1/100 - 0.005) = 0.5% 下落した時点で清算。

    `mm` を省略した場合は `notional` から階層的に推定する。

    >>> round(liquidation_price(entry=100.0, leverage=100, side=Side.LONG, mm=0.005), 4)
    99.5
    >>> round(liquidation_price(entry=100.0, leverage=100, side=Side.SHORT, mm=0.005), 4)
    100.5
    """
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    if mm is None:
        if notional is None:
            raise ValueError("either mm or notional must be provided")
        mm = maintenance_margin_rate(notional)
    factor = 1.0 / leverage - mm
    if side is Side.LONG:
        return entry * (1.0 - factor)
    return entry * (1.0 + factor)


@dataclass
class Position:
    """単一の建玉。"""

    side: Side
    entry: float
    qty: float                # 契約数(常に正、方向は side)
    leverage: float
    margin_mode: MarginMode = MarginMode.ISOLATED
    initial_margin: float = 0.0      # 預けた証拠金 (USDT)
    mm_rate: float = 0.0             # 維持証拠金率
    liq_price: float = 0.0
    open_bar: int = 0                # debug 用

    @property
    def notional(self) -> float:
        return self.entry * self.qty

    def unrealized_pnl(self, mark: float) -> float:
        return self.side.sign * (mark - self.entry) * self.qty

    def is_liquidated(self, bar_high: float, bar_low: float) -> bool:
        """このバーの値動きで清算が起きたか。"""
        if self.side is Side.LONG:
            return bar_low <= self.liq_price
        return bar_high >= self.liq_price


@dataclass
class LeverageEngine:
    """単一ポジション × Isolated を扱う最小実装(MVP)。

    後段で複数ポジション・Cross・部分決済に拡張する。
    """

    initial_equity: float
    fee: FeeModel = field(default_factory=FeeModel)
    mm_tiers: tuple[tuple[float, float], ...] = DEFAULT_MM_TIERS

    equity: float = field(init=False)
    position: Position | None = field(default=None, init=False)
    realized_pnl: float = field(default=0.0, init=False)
    total_fees: float = field(default=0.0, init=False)
    total_funding: float = field(default=0.0, init=False)
    n_liquidations: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.equity = self.initial_equity

    # ---- helpers ----------------------------------------------------------------
    def _mm(self, notional: float) -> float:
        return maintenance_margin_rate(notional, self.mm_tiers)

    # ---- public API -------------------------------------------------------------
    def open(
        self,
        *,
        side: Side,
        price: float,
        leverage: float,
        risk_fraction: float = 1.0,
        bar: int = 0,
    ) -> Position:
        """ポジションを建てる。risk_fraction は equity に対する IM の比率(0<r<=1)。"""
        if self.position is not None:
            raise RuntimeError("position already open; close it first")
        if not 0.0 < risk_fraction <= 1.0:
            raise ValueError("risk_fraction must be in (0, 1]")
        if leverage <= 0:
            raise ValueError("leverage must be positive")

        im = self.equity * risk_fraction
        notional = im * leverage
        qty = notional / price
        mm_rate = self._mm(notional)
        liq = liquidation_price(entry=price, leverage=leverage, side=side, mm=mm_rate)

        # エントリー手数料を equity から差し引く
        cost = self.fee.entry_cost(notional)
        self.equity -= cost
        self.total_fees += cost

        self.position = Position(
            side=side,
            entry=price,
            qty=qty,
            leverage=leverage,
            initial_margin=im,
            mm_rate=mm_rate,
            liq_price=liq,
            open_bar=bar,
        )
        return self.position

    def close(self, *, price: float, is_stop: bool = False) -> float:
        """現在のポジションを決済し、確定 PnL を返す。"""
        if self.position is None:
            raise RuntimeError("no open position")
        pos = self.position
        notional = pos.qty * price
        pnl = pos.side.sign * (price - pos.entry) * pos.qty
        cost = self.fee.exit_cost(notional, is_stop=is_stop)
        net = pnl - cost
        self.equity += net
        self.realized_pnl += pnl
        self.total_fees += cost
        self.position = None
        return net

    def force_liquidate(self) -> None:
        """清算処理 — 残り IM を没収し equity から差し引く(簡易版)。"""
        if self.position is None:
            return
        # Isolated: IM 全額が消失。realized_pnl は -IM
        self.equity -= self.position.initial_margin
        self.realized_pnl -= self.position.initial_margin
        self.position = None
        self.n_liquidations += 1

    def apply_funding(self, *, mark: float, rate: float) -> None:
        """ファンディング支払い/受取を適用する。"""
        if self.position is None:
            return
        payment = self.position.side.sign * self.position.qty * mark * rate
        # long が rate>0 なら支払い(equity 減)
        self.equity -= payment
        self.total_funding += payment

    def step_check_liquidation(self, *, bar_high: float, bar_low: float) -> bool:
        """このバーの High/Low で清算が起きたら force_liquidate を呼ぶ。返り値: 清算が起きたか。"""
        if self.position is None:
            return False
        if self.position.is_liquidated(bar_high=bar_high, bar_low=bar_low):
            self.force_liquidate()
            return True
        return False

    def is_bust(self, threshold: float = 0.10) -> bool:
        """初期残高の `threshold` を割ったか(default 10%)。"""
        return self.equity <= self.initial_equity * threshold
