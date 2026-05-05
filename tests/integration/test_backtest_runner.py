"""バックテストランナーの結合テスト。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from leverage_survival_lab.backtest import BacktestConfig, run_backtest
from leverage_survival_lab.strategies import RandomStrategy, SMACrossStrategy


def _make_ohlcv(n: int = 1000, drift: float = 0.0, vol: float = 0.01, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, size=n)
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, vol / 3, size=n)))
    low = close * (1 - np.abs(rng.normal(0, vol / 3, size=n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": rng.uniform(1, 10, size=n)},
        index=idx,
    )


@pytest.mark.integration
def test_backtest_runs_without_error_low_lev() -> None:
    df = _make_ohlcv(n=500)
    sig = RandomStrategy(p_long=0.05, p_short=0.05, seed=0).generate(df)
    result = run_backtest(df, sig, BacktestConfig(leverage=2.0, stop_loss=-0.05))
    assert result.equity_curve.shape[0] == len(df)
    assert result.final_equity > 0


@pytest.mark.integration
def test_high_leverage_more_likely_to_bust() -> None:
    """100倍レバの方が低レバよりも破産率が高いことを確認(H1の方向性チェック)。"""
    df = _make_ohlcv(n=1000, drift=0.0, vol=0.02)
    rng = np.random.default_rng(0)
    busts_high = 0
    busts_low = 0
    n = 30
    for _s in range(n):
        sig = RandomStrategy(p_long=0.05, p_short=0.05, seed=int(rng.integers(0, 10**9))).generate(df)
        r_high = run_backtest(df, sig, BacktestConfig(leverage=100.0, stop_loss=-0.01))
        r_low = run_backtest(df, sig, BacktestConfig(leverage=2.0, stop_loss=-0.05))
        busts_high += int(r_high.is_bust)
        busts_low += int(r_low.is_bust)
    # 高レバの破産率は低レバ以上であるべき
    assert busts_high >= busts_low


@pytest.mark.integration
def test_signal_index_mismatch_raises() -> None:
    df = _make_ohlcv(n=100)
    sig = SMACrossStrategy(fast=5, slow=20).generate(df).iloc[:-5]
    with pytest.raises(ValueError):
        run_backtest(df, sig, BacktestConfig())
