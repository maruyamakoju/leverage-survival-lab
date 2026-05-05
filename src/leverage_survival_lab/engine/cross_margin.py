"""Cross margin エンジン(MVP) — 複数ポジションを単一の equity プールで運用。

Isolated と異なり、清算は **口座エクイティ全体**が維持証拠金合計を下回ったとき発生する。
このとき開いている全ポジションが連鎖的に強制決済される。

注: これはまだ簡易実装。Binance 等の Cross では maintenance margin 階層も
ポジションごとに評価する必要があるが、本実装では平均維持率で近似する。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .leverage import FeeModel, Position, Side, maintenance_margin_rate


@dataclass
class CrossMarginEngine:
    """Cross margin で複数ポジションを抱えるエンジン。"""

    initial_equity: float
    fee: FeeModel = field(default_factory=FeeModel)

    equity: float = field(init=False)
    positions: list[Position] = field(default_factory=list, init=False)
    realized_pnl: float = field(default=0.0, init=False)
    total_fees: float = field(default=0.0, init=False)
    total_funding: float = field(default=0.0, init=False)
    n_liquidations: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.equity = self.initial_equity

    # ---- internal helpers -------------------------------------------------
    def _total_notional(self, marks: dict[str, float]) -> float:
        return sum(p.qty * marks.get(_pid(p), p.entry) for p in self.positions)

    def _total_unrealized(self, marks: dict[str, float]) -> float:
        return sum(p.unrealized_pnl(marks.get(_pid(p), p.entry)) for p in self.positions)

    def _maintenance_required(self, marks: dict[str, float]) -> float:
        # 簡略化: 各ポジションごとに mm_rate × 現マーク notional を要求
        total = 0.0
        for p in self.positions:
            mark = marks.get(_pid(p), p.entry)
            mm = maintenance_margin_rate(p.qty * mark)
            total += p.qty * mark * mm
        return total

    # ---- public API -------------------------------------------------------
    def open(
        self, *, side: Side, price: float, leverage: float, risk_fraction: float = 0.10,
        symbol: str = "BTC/USDT", bar: int = 0,
    ) -> Position:
        if not 0.0 < risk_fraction <= 1.0:
            raise ValueError("risk_fraction must be in (0, 1]")
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        im = self.equity * risk_fraction
        notional = im * leverage
        qty = notional / price
        mm_rate = maintenance_margin_rate(notional)
        from .leverage import liquidation_price
        liq = liquidation_price(entry=price, leverage=leverage, side=side, mm=mm_rate)

        cost = self.fee.entry_cost(notional)
        self.equity -= cost
        self.total_fees += cost

        pos = Position(side=side, entry=price, qty=qty, leverage=leverage,
                       initial_margin=im, mm_rate=mm_rate, liq_price=liq, open_bar=bar)
        # symbol を毎ポジに紐付け(簡易: open_bar フィールド近傍で別管理)
        # 本実装では各ポジが単一銘柄前提で symbol は外部 dict で参照
        self.positions.append(pos)
        return pos

    def close(self, position: Position, *, price: float, is_stop: bool = False) -> float:
        if position not in self.positions:
            raise ValueError("position not in this engine")
        notional = position.qty * price
        pnl = position.side.sign * (price - position.entry) * position.qty
        cost = self.fee.exit_cost(notional, is_stop=is_stop)
        net = pnl - cost
        self.equity += net
        self.realized_pnl += pnl
        self.total_fees += cost
        self.positions.remove(position)
        return net

    def apply_funding(self, *, mark: float, rate: float) -> None:
        """全ポジションにファンディングを適用(同一銘柄前提の簡略版)。"""
        for p in self.positions:
            payment = p.side.sign * p.qty * mark * rate
            self.equity -= payment
            self.total_funding += payment

    def step_check_account_liquidation(self, marks: dict[str, float]) -> bool:
        """口座エクイティ全体が維持証拠金を下回ったら、全ポジ強制決済。

        marks は {symbol: mark_price}。本実装では _pid(p) -> str がキーの代用。
        """
        net_eq = self.equity + self._total_unrealized(marks)
        required = self._maintenance_required(marks)
        if net_eq <= required:
            # 全ポジを清算扱い(IM 損失として没収)
            for p in list(self.positions):
                self.equity = max(0.0, self.equity - p.initial_margin)
                self.realized_pnl -= p.initial_margin
            self.positions.clear()
            self.n_liquidations += 1
            return True
        return False

    def is_bust(self, threshold: float = 0.10) -> bool:
        return self.equity <= self.initial_equity * threshold


def _pid(p: Position) -> str:
    """Position を辞書キーとして識別するための簡易 ID。"""
    return f"{id(p)}"
