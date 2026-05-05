"""fixtures.py / synthetic.py のテスト。"""
from __future__ import annotations

import pandas as pd
import pytest

from leverage_survival_lab.data.fixtures import (
    list_scenarios,
    scenario_window,
    slice_scenario,
)
from leverage_survival_lab.data.synthetic import crash_ohlcv, gbm_ohlcv


def test_list_scenarios_returns_known_keys() -> None:
    out = list_scenarios()
    names = {s["name"] for s in out}
    assert "covid_crash_2020" in names
    assert "may_2021_flush" in names
    assert "ftx_collapse_2022" in names


def test_scenario_window_known() -> None:
    s, e = scenario_window("covid_crash_2020")
    assert s.year == 2020 and s.month == 3
    assert e.year == 2020


def test_scenario_window_unknown_raises() -> None:
    with pytest.raises(KeyError):
        scenario_window("nonexistent")


def test_slice_scenario_filters() -> None:
    idx = pd.date_range("2020-01-01", "2020-12-31", freq="D", tz="UTC")
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    sub = slice_scenario(df, "covid_crash_2020")
    assert len(sub) > 0
    assert sub.index.min() >= pd.Timestamp("2020-03-09", tz="UTC")
    assert sub.index.max() <= pd.Timestamp("2020-03-20", tz="UTC")


def test_gbm_ohlcv_deterministic() -> None:
    df1 = gbm_ohlcv(n_bars=100, seed=42)
    df2 = gbm_ohlcv(n_bars=100, seed=42)
    pd.testing.assert_frame_equal(df1, df2)


def test_gbm_ohlcv_high_low_consistency() -> None:
    df = gbm_ohlcv(n_bars=500, seed=0)
    assert (df["high"] >= df["close"]).all()
    assert (df["low"] <= df["close"]).all()
    assert (df["high"] >= df["low"]).all()


def test_crash_ohlcv_shows_drop() -> None:
    df = crash_ohlcv(n_bars=200, crash_at=100, crash_pct=-0.30, seed=0)
    pre = df["close"].iloc[99]
    at = df["close"].iloc[100]
    # 30% 程度の下落
    assert at < pre * 0.85
    # crash バーの low は close と一致
    assert df["low"].iloc[100] == at
