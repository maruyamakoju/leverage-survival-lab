"""Walk-forward 分析 — in-sample でパラメータ最適化、out-of-sample で評価。

設計:
- 全期間を ``train_bars`` + ``test_bars`` の連続スライディング窓に分割
- 各窓の IS (in-sample) 部分で `param_grid` を試して `score_fn` を最大化
- そのまま OOS (out-of-sample) 部分で評価
- IS 過剰適合の度合いは IS スコアと OOS スコアの差で診断
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .runner import BacktestConfig, BacktestResult, run_backtest
from ..strategies.base import Strategy


@dataclass
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    best_params: dict[str, Any]
    is_score: float
    oos_score: float
    oos_result: BacktestResult


def split_walkforward(
    df: pd.DataFrame, *, train_bars: int, test_bars: int, step_bars: int | None = None
) -> Iterable[tuple[pd.DataFrame, pd.DataFrame]]:
    """連続するスライディング窓 (train_df, test_df) を yield する。"""
    step = step_bars or test_bars
    n = len(df)
    start = 0
    while start + train_bars + test_bars <= n:
        train = df.iloc[start : start + train_bars]
        test = df.iloc[start + train_bars : start + train_bars + test_bars]
        yield train, test
        start += step


def walkforward(
    df: pd.DataFrame,
    *,
    train_bars: int,
    test_bars: int,
    strategy_factory: Callable[..., Strategy],
    param_grid: list[dict[str, Any]],
    base_config: BacktestConfig,
    score_fn: Callable[[BacktestResult], float],
) -> list[WalkForwardWindow]:
    """Walk-forward ループを実行。"""
    out: list[WalkForwardWindow] = []
    for train, test in split_walkforward(df, train_bars=train_bars, test_bars=test_bars):
        # IS 最適化
        best_params, best_score = None, float("-inf")
        for params in param_grid:
            strat = strategy_factory(**params)
            sig = strat.generate(train)
            res = run_backtest(train, sig, base_config)
            s = score_fn(res)
            if s > best_score:
                best_score = s
                best_params = params
        # OOS 評価
        assert best_params is not None
        strat = strategy_factory(**best_params)
        sig_oos = strat.generate(test)
        oos = run_backtest(test, sig_oos, base_config)
        out.append(WalkForwardWindow(
            train_start=train.index[0], train_end=train.index[-1],
            test_start=test.index[0], test_end=test.index[-1],
            best_params=best_params, is_score=best_score,
            oos_score=score_fn(oos), oos_result=oos,
        ))
    return out
