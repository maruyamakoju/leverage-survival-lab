"""grid 関連のユニットテスト。"""
from __future__ import annotations

import pytest

from leverage_survival_lab.backtest.grid import (
    GridSpec,
    GridTask,
    _data_for_seed,
    _run_one,
    random_window_slices,
)
from leverage_survival_lab.data.synthetic import gbm_ohlcv


def test_grid_spec_n_cells() -> None:
    spec = GridSpec(
        leverages=(1, 10, 100),
        stop_losses=(-0.01, None),
        take_profits=(None,),
        strategies=("random",),
        n_seeds=5,
    )
    assert spec.n_cells() == 3 * 2 * 1 * 1 * 5


def test_run_one_returns_dict_with_expected_keys() -> None:
    _, df = _data_for_seed(0, 240, 0.0, 0.01)
    t = GridTask(strategy_name="random", leverage=2.0, stop_loss=-0.05,
                 take_profit=None, seed=0, risk_fraction=1.0, data_id="test")
    r = _run_one(t, df)
    assert {"final_equity", "is_bust", "max_drawdown", "n_liquidations", "error"}.issubset(r.keys())


def test_run_one_invalid_strategy_returns_error() -> None:
    _, df = _data_for_seed(0, 240, 0.0, 0.01)
    t = GridTask(strategy_name="UNKNOWN", leverage=2.0, stop_loss=None,
                 take_profit=None, seed=0, risk_fraction=1.0, data_id="test")
    r = _run_one(t, df)
    assert r["error"] is not None


def test_random_window_slices() -> None:
    df = gbm_ohlcv(n_bars=10_000, seed=1)
    slices = random_window_slices(df, window_bars=100, n_windows=20, seed=42)
    assert len(slices) <= 20  # 重複可能性のため <=
    for label, sub in slices:
        assert len(sub) == 100
        assert label.startswith("win")


def test_random_window_slices_too_large_window_raises() -> None:
    df = gbm_ohlcv(n_bars=100, seed=1)
    with pytest.raises(ValueError):
        random_window_slices(df, window_bars=200, n_windows=5)
