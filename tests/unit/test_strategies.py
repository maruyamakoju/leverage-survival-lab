"""戦略モジュールのスモークテスト。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from leverage_survival_lab.strategies import (
    BollingerStrategy,
    BreakoutStrategy,
    RandomStrategy,
    RSIStrategy,
    SMACrossStrategy,
)


def _make_ohlcv(n: int = 500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 0.01, size=n)
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.003, size=n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, size=n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": rng.uniform(1, 10, size=n)},
        index=idx,
    )


def test_random_strategy_signals_in_range() -> None:
    df = _make_ohlcv()
    sig = RandomStrategy(p_long=0.1, p_short=0.1, seed=1).generate(df)
    assert sig.isin([-1, 0, 1]).all()
    assert len(sig) == len(df)


def test_sma_cross_signals_in_range() -> None:
    df = _make_ohlcv()
    sig = SMACrossStrategy(fast=5, slow=20).generate(df)
    assert sig.isin([-1, 0, 1]).all()


def test_rsi_signals_in_range() -> None:
    df = _make_ohlcv()
    sig = RSIStrategy(period=14).generate(df)
    assert sig.isin([-1, 0, 1]).all()


def test_bollinger_signals_in_range() -> None:
    df = _make_ohlcv()
    sig = BollingerStrategy().generate(df)
    assert sig.isin([-1, 0, 1]).all()


def test_breakout_signals_in_range() -> None:
    df = _make_ohlcv()
    sig = BreakoutStrategy().generate(df)
    assert sig.isin([-1, 0, 1]).all()
