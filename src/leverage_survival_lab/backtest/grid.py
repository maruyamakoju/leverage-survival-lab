"""モンテカルロ・グリッド実験ランナー。

実験の独立変数(strategy × leverage × stop_loss × take_profit × seed × ...)を
組み合わせ、並列に backtest を回し、結果を Parquet に書き出す。

設計方針:
- 1 タスク = 1 シミュレーション(decompose を細かくして並列効率を上げる)
- 結果は long-format DataFrame: 1 行 = 1 シミュレーション
- 再現性: (strategy, params, seed, data_id) で完全に決定論的
"""
from __future__ import annotations

import itertools
import logging
import multiprocessing as mp
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

from ..analysis.metrics import max_drawdown, sharpe_ratio
from ..config import settings
from ..strategies import (
    BollingerStrategy,
    BreakoutStrategy,
    RandomStrategy,
    RSIStrategy,
    SMACrossStrategy,
    Strategy,
)
from .runner import BacktestConfig, run_backtest

logger = logging.getLogger(__name__)


STRATEGY_FACTORIES: dict[str, Any] = {
    "random":    lambda seed: RandomStrategy(p_long=0.05, p_short=0.05, seed=seed),
    "sma_cross": lambda seed: SMACrossStrategy(fast=20, slow=50),
    "rsi":       lambda seed: RSIStrategy(period=14),
    "bollinger": lambda seed: BollingerStrategy(window=20, n_std=2.0),
    "breakout":  lambda seed: BreakoutStrategy(window=20),
}


@dataclass
class GridSpec:
    """グリッド独立変数の仕様。"""
    leverages: tuple[float, ...] = (1, 2, 5, 10, 25, 50, 100)
    stop_losses: tuple[float | None, ...] = (-0.005, -0.01, -0.02, -0.05, None)
    take_profits: tuple[float | None, ...] = (None,)
    strategies: tuple[str, ...] = ("random", "sma_cross", "rsi", "bollinger", "breakout")
    risk_fractions: tuple[float, ...] = (1.0,)
    n_seeds: int = 100
    risk_fraction: float = 1.0  # legacy single-value (使われ続ける)

    def n_cells(self) -> int:
        return (len(self.leverages) * len(self.stop_losses) * len(self.take_profits) *
                len(self.strategies) * len(self.risk_fractions) * self.n_seeds)


@dataclass(frozen=True)
class GridTask:
    strategy_name: str
    leverage: float
    stop_loss: float | None
    take_profit: float | None
    seed: int
    risk_fraction: float
    data_id: str  # データセット識別子(例 "synthetic_24h_30d_seedXX" or "binance_BTCUSDT_1h_2024")


def _run_one(task: GridTask, df: pd.DataFrame) -> dict[str, Any]:
    """単一シミュレーションを実行し、結果サマリ dict を返す。

    例外時は ``error`` フィールド付きの行を返す(グリッド全体を止めない)。
    """
    try:
        strat: Strategy = STRATEGY_FACTORIES[task.strategy_name](task.seed)
        sig = strat.generate(df)
        cfg = BacktestConfig(
            leverage=task.leverage,
            stop_loss=task.stop_loss,
            take_profit=task.take_profit,
            risk_fraction=task.risk_fraction,
            initial_equity=settings.initial_equity_usdt,
        )
        res = run_backtest(df, sig, cfg)
        eq = res.equity_curve
        return {
            **asdict(task),
            "final_equity": res.final_equity,
            "total_return": float(eq.iloc[-1] / eq.iloc[0] - 1.0),
            "max_drawdown": float(max_drawdown(eq)),
            "sharpe": float(sharpe_ratio(eq, periods_per_year=24 * 365)),
            "n_liquidations": res.n_liquidations,
            "is_bust": res.is_bust,
            "total_fees": res.total_fees,
            "total_funding": res.total_funding,
            "n_trades": len(res.trades),
            "error": None,
        }
    except Exception as e:
        return {
            **asdict(task),
            "final_equity": float("nan"),
            "total_return": float("nan"),
            "max_drawdown": float("nan"),
            "sharpe": float("nan"),
            "n_liquidations": -1,
            "is_bust": True,
            "total_fees": 0.0,
            "total_funding": 0.0,
            "n_trades": 0,
            "error": f"{type(e).__name__}: {e}",
        }


def _data_for_seed(seed: int, n_bars: int, drift: float, vol: float) -> tuple[str, pd.DataFrame]:
    """シード別の合成データセット(データレンジ多様性のため)。"""
    from ..data.synthetic import gbm_ohlcv
    df = gbm_ohlcv(n_bars=n_bars, drift=drift, vol=vol, seed=seed)
    return f"synthetic_n{n_bars}_d{drift:.4f}_v{vol:.4f}_seed{seed}", df


def run_grid_synthetic(
    spec: GridSpec,
    *,
    n_bars: int = 24 * 30,
    drift: float = 0.0,
    vol: float = 0.015,
    n_workers: int | None = None,
    show_progress: bool = True,
) -> pd.DataFrame:
    """合成データで グリッド実験を回す(各 seed ごとに新しい価格パスを生成)。"""
    n_workers = n_workers or max(1, (os.cpu_count() or 2) - 1)
    tasks: list[GridTask] = []
    cached_data: dict[int, tuple[str, pd.DataFrame]] = {}
    for seed in range(spec.n_seeds):
        cached_data[seed] = _data_for_seed(seed, n_bars, drift, vol)
    for L, sl, tp, strat, seed in itertools.product(
        spec.leverages, spec.stop_losses, spec.take_profits, spec.strategies, range(spec.n_seeds)
    ):
        tasks.append(GridTask(
            strategy_name=strat, leverage=float(L), stop_loss=sl, take_profit=tp,
            seed=seed, risk_fraction=spec.risk_fraction,
            data_id=cached_data[seed][0],
        ))

    logger.info("running %d simulations on %d workers", len(tasks), n_workers)

    # n_workers=1 時は逐次実行、>1 時は ProcessPool。pickle のために df を毎回渡す。
    results: list[dict[str, Any]] = []
    if n_workers <= 1:
        it = tasks
        if show_progress:
            it = tqdm(it, total=len(tasks), mininterval=2.0, miniters=500)  # type: ignore[assignment]
        for t in it:
            df = cached_data[t.seed][1]
            results.append(_run_one(t, df))
    else:
        # 各 task に必要な df を同梱し pool で分散
        payloads = [(t, cached_data[t.seed][1]) for t in tasks]
        with mp.get_context("spawn").Pool(n_workers) as pool:
            it = pool.imap_unordered(_grid_worker, payloads, chunksize=8)
            if show_progress:
                it = tqdm(it, total=len(payloads))  # type: ignore[assignment]
            for r in it:
                results.append(r)

    return _safe_records_to_df(results)


def _grid_worker(payload: tuple[GridTask, pd.DataFrame]) -> dict[str, Any]:
    task, df = payload
    return _run_one(task, df)


def _safe_records_to_df(records: list[dict[str, Any]]) -> pd.DataFrame:
    """list[dict] -> DataFrame の安全な構築。

    pandas が list-of-dict に対して Windows 上でセグフォルトする回帰があるため、
    キーごとに list を集めて column-wise に DataFrame を作る。
    """
    if not records:
        return pd.DataFrame()
    keys = list(records[0].keys())
    cols: dict[str, list[Any]] = {k: [] for k in keys}
    for r in records:
        for k in keys:
            cols[k].append(r.get(k))
    return pd.DataFrame(cols)


def save_grid_results(df: pd.DataFrame, name: str) -> Path:
    out = settings.results_dir / f"grid_{name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, compression="zstd")
    return out


def random_window_slices(
    df: pd.DataFrame, *, window_bars: int, n_windows: int, seed: int = 0
) -> list[tuple[str, pd.DataFrame]]:
    """過去データからランダム位置で window_bars 分の連続スライスを n_windows 個切り出す。

    返り値: [(label, slice_df), ...]
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    if window_bars >= n:
        raise ValueError("window_bars must be < len(df)")
    starts = rng.integers(0, n - window_bars, size=n_windows)
    out: list[tuple[str, pd.DataFrame]] = []
    for k, s in enumerate(sorted({int(x) for x in starts})):
        sub = df.iloc[s : s + window_bars].copy()
        ts0 = sub.index.min()
        out.append((f"win{k}_{ts0.strftime('%Y%m%d')}", sub))
    return out


def run_grid_realdata(
    df: pd.DataFrame,
    spec: GridSpec,
    *,
    window_bars: int = 24 * 30,
    n_windows: int = 100,
    seed: int = 0,
    n_workers: int = 1,
    show_progress: bool = True,
) -> pd.DataFrame:
    """実データに対しランダム期間で n_windows 個のサンプルを切り、各 (戦略×レバ×SL×TP) で回す。"""
    windows = random_window_slices(df, window_bars=window_bars, n_windows=n_windows, seed=seed)
    cached = dict(windows)

    tasks: list[GridTask] = []
    for L, sl, tp, strat, rf, (label, _) in itertools.product(
        spec.leverages, spec.stop_losses, spec.take_profits, spec.strategies,
        spec.risk_fractions, windows
    ):
        tasks.append(GridTask(
            strategy_name=strat, leverage=float(L), stop_loss=sl, take_profit=tp,
            seed=hash(label) & 0x7fffffff, risk_fraction=float(rf),
            data_id=label,
        ))

    logger.info("running %d simulations on %d workers (real data)", len(tasks), n_workers)

    results: list[dict[str, Any]] = []
    if n_workers <= 1:
        it = tasks
        if show_progress:
            it = tqdm(it, total=len(tasks), mininterval=2.0, miniters=500)  # type: ignore[assignment]
        for t in it:
            results.append(_run_one(t, cached[t.data_id]))
    else:
        payloads = [(t, cached[t.data_id]) for t in tasks]
        with mp.get_context("spawn").Pool(n_workers) as pool:
            it = pool.imap_unordered(_grid_worker, payloads, chunksize=8)
            if show_progress:
                it = tqdm(it, total=len(payloads), mininterval=2.0, miniters=500)  # type: ignore[assignment]
            for r in it:
                results.append(r)

    return _safe_records_to_df(results)
