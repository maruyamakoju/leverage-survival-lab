"""Walk-forward の単体テスト。"""
from __future__ import annotations

import pandas as pd

from leverage_survival_lab.backtest.runner import BacktestConfig, BacktestResult
from leverage_survival_lab.backtest.walkforward import split_walkforward, walkforward
from leverage_survival_lab.data.synthetic import gbm_ohlcv
from leverage_survival_lab.strategies.sma_cross import SMACrossStrategy


def test_split_walkforward_yields_windows() -> None:
    df = gbm_ohlcv(n_bars=1000, seed=0)
    windows = list(split_walkforward(df, train_bars=300, test_bars=100))
    assert len(windows) > 0
    for tr, te in windows:
        assert len(tr) == 300
        assert len(te) == 100
        assert tr.index[-1] < te.index[0]


def test_walkforward_basic_run() -> None:
    df = gbm_ohlcv(n_bars=600, seed=0)

    def factory(*, fast: int, slow: int) -> SMACrossStrategy:
        return SMACrossStrategy(fast=fast, slow=slow)

    grid = [{"fast": 10, "slow": 30}, {"fast": 20, "slow": 50}]
    cfg = BacktestConfig(leverage=2.0, stop_loss=-0.05)
    out = walkforward(df, train_bars=300, test_bars=100,
                     strategy_factory=factory, param_grid=grid,
                     base_config=cfg,
                     score_fn=lambda r: r.final_equity)
    assert len(out) >= 1
    for w in out:
        assert w.best_params in grid
        assert isinstance(w.oos_result, BacktestResult)
        assert w.train_end < w.test_start


def test_split_walkforward_too_short_returns_empty() -> None:
    df = gbm_ohlcv(n_bars=100, seed=0)
    windows = list(split_walkforward(df, train_bars=80, test_bars=50))
    assert windows == []
