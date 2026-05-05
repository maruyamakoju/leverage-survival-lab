"""データ品質モジュールのテスト。"""
from __future__ import annotations

import pandas as pd

from leverage_survival_lab.data.quality import (
    assess_ohlcv,
    detect_regimes,
    expected_timedelta,
    fill_gaps_forward,
)
from leverage_survival_lab.data.synthetic import gbm_ohlcv


def test_expected_timedelta() -> None:
    assert expected_timedelta("1m") == pd.Timedelta(minutes=1)
    assert expected_timedelta("5m") == pd.Timedelta(minutes=5)
    assert expected_timedelta("1h") == pd.Timedelta(hours=1)
    assert expected_timedelta("4h") == pd.Timedelta(hours=4)
    assert expected_timedelta("1d") == pd.Timedelta(days=1)


def test_assess_ohlcv_clean() -> None:
    df = gbm_ohlcv(n_bars=500, bar_freq="h", seed=1)
    rep = assess_ohlcv(df, "1h")
    assert rep.n_rows == 500
    assert rep.n_duplicates == 0
    assert rep.n_gaps == 0
    assert rep.is_healthy()


def test_assess_ohlcv_with_gap() -> None:
    df = gbm_ohlcv(n_bars=100, bar_freq="h", seed=2)
    # 真ん中に gap
    df_gapped = pd.concat([df.iloc[:50], df.iloc[60:]])
    rep = assess_ohlcv(df_gapped, "1h")
    assert rep.n_gaps >= 1


def test_fill_gaps_forward() -> None:
    df = gbm_ohlcv(n_bars=100, bar_freq="h", seed=3)
    df_gapped = pd.concat([df.iloc[:50], df.iloc[60:]])
    filled = fill_gaps_forward(df_gapped, "1h")
    # 連続 index になっている
    diffs = filled.index.to_series().diff().dropna().unique()
    assert len(diffs) == 1
    assert diffs[0] == pd.Timedelta(hours=1)


def test_detect_regimes_returns_known_labels() -> None:
    df = gbm_ohlcv(n_bars=24 * 60, bar_freq="h", drift=0.0, vol=0.01, seed=4)
    regimes = detect_regimes(df, window=24 * 7)
    assert regimes.isin({"range", "trend_up", "trend_down", "crash"}).all()
