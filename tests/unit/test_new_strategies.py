"""新戦略(funding flip / trend filtered)のテスト。"""
from __future__ import annotations

import pandas as pd

from leverage_survival_lab.data.synthetic import gbm_ohlcv
from leverage_survival_lab.strategies import FundingFlipStrategy, TrendFilteredSMA


def test_trend_filtered_sma_signal_in_range() -> None:
    df = gbm_ohlcv(n_bars=500, drift=0.0001, vol=0.01, seed=0)
    sig = TrendFilteredSMA(fast=10, slow=30, trend=100).generate(df)
    assert sig.isin([-1, 0, 1]).all()
    assert len(sig) == len(df)


def test_trend_filtered_sma_no_long_below_trend() -> None:
    """価格が 200SMA 以下の区間で long シグナルが出ないこと。"""
    df = gbm_ohlcv(n_bars=500, drift=-0.001, vol=0.005, seed=1)  # 下降トレンド
    strat = TrendFilteredSMA(fast=10, slow=30, trend=100)
    sig = strat.generate(df)
    close = df["close"]
    t = close.rolling(100).mean()
    below_trend = close < t
    # below_trend で long シグナルが立っていないこと
    assert not (sig[below_trend] == 1).any()


def test_funding_flip_no_funding_returns_zeros() -> None:
    df = gbm_ohlcv(n_bars=200, seed=0)
    sig = FundingFlipStrategy(funding_series=None).generate(df)
    assert (sig == 0).all()


def test_funding_flip_threshold_triggers_short() -> None:
    df = gbm_ohlcv(n_bars=200, seed=0)
    # 全期間で大きな正のファンディング → 全期間 ショート
    funding = pd.Series(0.001, index=df.index, name="rate")
    strat = FundingFlipStrategy(threshold=0.0003, lookback=24, funding_series=funding)
    sig = strat.generate(df)
    # 24 バー目以降は全部 -1 になるはず
    assert (sig.iloc[24:] == -1).all()
