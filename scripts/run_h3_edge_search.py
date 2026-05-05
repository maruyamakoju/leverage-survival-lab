"""H3 用エッジ探索: trend_filtered_sma を BTC で動かし、レバ別期待 log-return を見る。

目的: 「正のシャープを持つ戦略があるなら、レバを上げると閾値で負に転じる」という H3 を
    実証可能にするため、エッジを持つ可能性のある戦略を試す。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from rich.console import Console

from leverage_survival_lab.backtest.grid import GridSpec, run_grid_realdata, save_grid_results
from leverage_survival_lab.config import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--name", default="h3_trend_filtered")
    args = p.parse_args()

    console = Console()
    df = pd.read_parquet(args.data)
    spec = GridSpec(
        leverages=(1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 100),
        stop_losses=(-0.02,),  # 固定 -2%
        take_profits=(None,),
        strategies=("trend_filtered_sma", "sma_cross", "random"),
        n_seeds=args.n_windows,
    )
    out_df = run_grid_realdata(df, spec, n_windows=args.n_windows, seed=args.seed,
                                n_workers=1, show_progress=False)
    save_grid_results(out_df, args.name)
    console.print(f"saved {len(out_df)} rows")

    valid = out_df[out_df["error"].isna()] if "error" in out_df.columns else out_df

    console.print("\n=== Mean log-return by (strategy, leverage) ===")
    valid = valid.assign(log_ret=lambda d: np.log(np.maximum(d["final_equity"], 1.0) / settings.initial_equity_usdt))
    pivot = valid.groupby(["strategy_name", "leverage"])["log_ret"].mean().unstack().T
    console.print(pivot.to_string(float_format=lambda x: f"{x:+.4f}"))

    console.print("\n=== Survival rate by (strategy, leverage) ===")
    pivot2 = (
        valid.assign(survives=lambda d: (d["final_equity"] >= settings.initial_equity_usdt * 0.10).astype(int))
             .groupby(["strategy_name", "leverage"])["survives"].mean().unstack().T
    )
    console.print(pivot2.to_string(float_format=lambda x: f"{x*100:5.1f}%"))


if __name__ == "__main__":
    main()
