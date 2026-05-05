"""Cross margin エンジンの単体テスト。"""
from __future__ import annotations

import math

import pytest

from leverage_survival_lab.engine.cross_margin import CrossMarginEngine, _pid
from leverage_survival_lab.engine.leverage import FeeModel, Side


def _eng() -> CrossMarginEngine:
    return CrossMarginEngine(initial_equity=1_000_000.0, fee=FeeModel())


def test_open_multiple_positions() -> None:
    eng = _eng()
    p1 = eng.open(side=Side.LONG, price=100.0, leverage=10, risk_fraction=0.1)
    p2 = eng.open(side=Side.SHORT, price=50.0, leverage=5, risk_fraction=0.1)
    assert len(eng.positions) == 2
    assert p1 is not p2


def test_close_specific_position() -> None:
    eng = _eng()
    p1 = eng.open(side=Side.LONG, price=100.0, leverage=10, risk_fraction=0.1)
    p2 = eng.open(side=Side.LONG, price=100.0, leverage=10, risk_fraction=0.1)
    eng.close(p1, price=110.0)
    assert len(eng.positions) == 1
    assert eng.positions[0] is p2


def test_close_unknown_position_raises() -> None:
    eng = _eng()
    p = eng.open(side=Side.LONG, price=100.0, leverage=10, risk_fraction=0.1)
    eng.close(p, price=110.0)
    with pytest.raises(ValueError):
        eng.close(p, price=120.0)


def test_account_liquidation_when_eq_below_mm() -> None:
    eng = _eng()
    # 100x ポジションを2つ建て、価格暴落で account-level 清算
    p1 = eng.open(side=Side.LONG, price=100.0, leverage=100, risk_fraction=0.4)
    p2 = eng.open(side=Side.LONG, price=100.0, leverage=100, risk_fraction=0.4)
    # 大暴落マーク
    marks = {_pid(p1): 50.0, _pid(p2): 50.0}
    triggered = eng.step_check_account_liquidation(marks)
    assert triggered
    assert eng.positions == []
    assert eng.n_liquidations == 1
    assert eng.equity >= 0.0  # クランプされる


def test_apply_funding_reduces_equity_for_long() -> None:
    eng = _eng()
    eng.open(side=Side.LONG, price=100.0, leverage=10, risk_fraction=0.1)
    eq_before = eng.equity
    eng.apply_funding(mark=100.0, rate=0.0001)
    assert eng.equity < eq_before
    assert eng.total_funding > 0


def test_invalid_risk_fraction_raises() -> None:
    eng = _eng()
    with pytest.raises(ValueError):
        eng.open(side=Side.LONG, price=100.0, leverage=10, risk_fraction=0.0)
    with pytest.raises(ValueError):
        eng.open(side=Side.LONG, price=100.0, leverage=10, risk_fraction=1.5)
