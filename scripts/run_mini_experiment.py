"""ミニ実験 — 合成データで H1 の方向性を確認する。

実データ取得を待たずにパイプライン全体が動くか確認するためのスクリプト。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from leverage_survival_lab.analysis.metrics import survival_rate
from leverage_survival_lab.backtest import BacktestConfig, run_backtest
from leverage_survival_lab.strategies import RandomStrategy

console = Console()


def make_synthetic(n: int, seed: int, drift: float = 0.0, vol: float = 0.015) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, size=n)
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, vol / 3, size=n)))
    low = close * (1 - np.abs(rng.normal(0, vol / 3, size=n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": np.ones(n)}, index=idx)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-bars", type=int, default=24 * 30, help="バー数(1h × 30日)")
    parser.add_argument("--n-iter", type=int, default=200, help="モンテカルロ反復数")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    leverages = [1, 2, 5, 10, 25, 50, 100]
    stops = [-0.005, -0.01, -0.02, -0.05, None]

    rng = np.random.default_rng(args.seed)
    table = Table(title=f"30日生存率 (N={args.n_iter}, RandomStrategy)")
    table.add_column("Lev")
    for sl in stops:
        table.add_column(f"SL={sl if sl is None else f'{sl*100:.1f}%'}")

    for L in leverages:
        row = [f"{L}x"]
        for sl in stops:
            finals: list[float] = []
            for k in range(args.n_iter):
                seed_k = int(rng.integers(0, 10**9))
                df = make_synthetic(args.n_bars, seed=seed_k)
                sig = RandomStrategy(p_long=0.05, p_short=0.05, seed=seed_k).generate(df)
                r = run_backtest(df, sig, BacktestConfig(leverage=float(L), stop_loss=sl))
                finals.append(r.final_equity)
            sr = survival_rate(np.array(finals), initial=1_000_000.0, threshold=0.10)
            row.append(f"{sr*100:5.1f}%")
        table.add_row(*row)

    console.print(table)


if __name__ == "__main__":
    main()
