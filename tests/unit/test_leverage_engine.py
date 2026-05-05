"""レバレッジエンジンのユニットテスト。"""
from __future__ import annotations

import math

import pytest

from leverage_survival_lab.engine.leverage import (
    DEFAULT_MM_TIERS,
    FeeModel,
    LeverageEngine,
    MarginMode,
    Position,
    Side,
    liquidation_price,
    maintenance_margin_rate,
)


class TestLiquidationPrice:
    def test_long_100x_basic(self) -> None:
        # 100x long, mm=0.5% → 0.5% 下落で清算 → 99.5
        p = liquidation_price(entry=100.0, leverage=100, side=Side.LONG, mm=0.005)
        assert math.isclose(p, 99.5, rel_tol=1e-6)

    def test_short_100x_basic(self) -> None:
        p = liquidation_price(entry=100.0, leverage=100, side=Side.SHORT, mm=0.005)
        assert math.isclose(p, 100.5, rel_tol=1e-6)

    def test_1x_long_liq_far_below(self) -> None:
        # 1x long, mm=0.5% → factor = 1 - 0.005 = 0.995, p_liq = entry * (1 - 0.995) = 0.5
        # つまり 99.5% 下落で清算。1x 取引で実質的に清算が起きないことを確認。
        p = liquidation_price(entry=100.0, leverage=1, side=Side.LONG, mm=0.005)
        assert math.isclose(p, 0.5, rel_tol=1e-6)

    def test_invalid_leverage_raises(self) -> None:
        with pytest.raises(ValueError):
            liquidation_price(entry=100.0, leverage=0, side=Side.LONG, mm=0.005)

    def test_mm_inferred_from_notional(self) -> None:
        # 小額: 階層 0 (mm=0.4%)
        p_small = liquidation_price(entry=100.0, leverage=10, side=Side.LONG, notional=1000.0)
        assert math.isclose(p_small, 100.0 * (1 - 0.1 + 0.004), rel_tol=1e-6)


class TestMaintenanceMargin:
    def test_lowest_tier(self) -> None:
        assert maintenance_margin_rate(1000.0) == DEFAULT_MM_TIERS[0][1]

    def test_highest_tier(self) -> None:
        assert maintenance_margin_rate(1e9) == DEFAULT_MM_TIERS[-1][1]

    def test_monotonic(self) -> None:
        notionals = [1e3, 1e5, 5e5, 5e6, 5e7]
        rates = [maintenance_margin_rate(n) for n in notionals]
        assert rates == sorted(rates)


class TestFeeModel:
    def test_round_trip(self) -> None:
        fm = FeeModel()
        ec = fm.entry_cost(100_000)
        xc = fm.exit_cost(100_000)
        # taker 0.04% + slip 0.05% = 0.09% per side
        assert math.isclose(ec, 90.0, rel_tol=1e-6)
        assert math.isclose(xc, 90.0, rel_tol=1e-6)

    def test_stop_extra(self) -> None:
        fm = FeeModel()
        normal = fm.exit_cost(100_000, is_stop=False)
        stop = fm.exit_cost(100_000, is_stop=True)
        assert stop > normal


class TestLeverageEngineFlow:
    def _eng(self) -> LeverageEngine:
        return LeverageEngine(initial_equity=1_000_000.0, fee=FeeModel())

    def test_open_then_close_at_same_price_only_fees(self) -> None:
        eng = self._eng()
        eng.open(side=Side.LONG, price=100.0, leverage=10)
        eng.close(price=100.0)
        # 同価格で閉じても手数料分だけ赤字
        assert eng.equity < 1_000_000.0
        # 手数料は片道 (taker 0.04% + slip 0.05%) * notional → 往復で 0.18%
        # notional = 1M * 10 = 10M, fees ≈ 18,000
        assert math.isclose(1_000_000.0 - eng.equity, 18_000.0, rel_tol=1e-3)

    def test_long_winning_trade(self) -> None:
        eng = self._eng()
        eng.open(side=Side.LONG, price=100.0, leverage=10)
        eng.close(price=110.0)
        # +10% 上昇 × 10倍レバ = +100% (手数料前)、約 1M → ~2M 弱
        assert eng.equity > 1_900_000.0

    def test_short_winning_trade(self) -> None:
        eng = self._eng()
        eng.open(side=Side.SHORT, price=100.0, leverage=10)
        eng.close(price=90.0)
        assert eng.equity > 1_900_000.0

    def test_force_liquidation_zeroes_isolated_im(self) -> None:
        eng = self._eng()
        eng.open(side=Side.LONG, price=100.0, leverage=100)
        eng.force_liquidate()
        # Isolated 100x, IM = equity 全額(risk_fraction=1.0)
        # → 清算で IM 全額消失、equity は 0 でクランプ
        assert eng.equity == 0.0
        assert eng.n_liquidations == 1

    def test_double_open_raises(self) -> None:
        eng = self._eng()
        eng.open(side=Side.LONG, price=100.0, leverage=10)
        with pytest.raises(RuntimeError):
            eng.open(side=Side.SHORT, price=100.0, leverage=10)

    def test_close_without_position_raises(self) -> None:
        with pytest.raises(RuntimeError):
            self._eng().close(price=100.0)

    def test_step_check_liquidation_triggers_for_long(self) -> None:
        eng = self._eng()
        eng.open(side=Side.LONG, price=100.0, leverage=100)
        # liq_price は ~99 付近。bar_low がそこを下回れば清算
        liq = eng.position.liq_price  # type: ignore[union-attr]
        assert eng.step_check_liquidation(bar_high=100.5, bar_low=liq - 0.1)
        assert eng.position is None
        assert eng.n_liquidations == 1

    def test_funding_payment_long_pays_when_positive_rate(self) -> None:
        eng = self._eng()
        eng.open(side=Side.LONG, price=100.0, leverage=10)
        eq_before = eng.equity
        eng.apply_funding(mark=100.0, rate=0.0001)  # 0.01%
        assert eng.equity < eq_before
        assert eng.total_funding > 0


class TestPositionUnrealized:
    def test_long_unrealized(self) -> None:
        pos = Position(side=Side.LONG, entry=100.0, qty=10.0, leverage=10,
                       initial_margin=100.0, mm_rate=0.005, liq_price=99.0)
        assert math.isclose(pos.unrealized_pnl(110.0), 100.0)
        assert math.isclose(pos.unrealized_pnl(90.0), -100.0)

    def test_short_unrealized(self) -> None:
        pos = Position(side=Side.SHORT, entry=100.0, qty=10.0, leverage=10,
                       initial_margin=100.0, mm_rate=0.005, liq_price=101.0)
        assert math.isclose(pos.unrealized_pnl(90.0), 100.0)
        assert math.isclose(pos.unrealized_pnl(110.0), -100.0)


def test_margin_mode_enum_values() -> None:
    assert MarginMode.ISOLATED.value == "isolated"
    assert MarginMode.CROSS.value == "cross"
