"""risk_fraction を1つだけ受け取り、専用プロセスで実験する。

外側のオーケストレータから subprocess 経由で呼び出すことで、長時間実行による
ネイティブメモリ問題を回避する。
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd
from rich.console import Console
from rich.logging import RichHandler

from leverage_survival_lab.analysis.stats import wilson_ci
from leverage_survival_lab.backtest.grid import GridSpec, run_grid_realdata, save_grid_results
from leverage_survival_lab.config import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--rf", type=float, required=True)
    p.add_argument("--strategies", default="random")
    p.add_argument("--name-prefix", default="rf_isolated")
    args = p.parse_args()

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(console=console)])

    df = pd.read_parquet(args.data)
    spec = GridSpec(
        leverages=(100.0,),  # 100x のみ
        n_seeds=args.n_windows,
        strategies=tuple(args.strategies.split(",")),
        risk_fractions=(args.rf,),
    )
    out_df = run_grid_realdata(df, spec, n_windows=args.n_windows, seed=args.seed,
                                n_workers=1, show_progress=False)
    name = f"{args.name_prefix}_rf{args.rf:.2f}"
    save_grid_results(out_df, name)

    h1 = out_df[out_df["leverage"] == 100.0]
    successes = int((h1["final_equity"] >= settings.initial_equity_usdt * 0.10).sum())
    ci = wilson_ci(successes, len(h1))
    console.print(f"rf={args.rf:.2f}  N={len(h1)}  100x survival={ci.p*100:.2f}%  CI=[{ci.lo*100:.2f}%, {ci.hi*100:.2f}%]")


if __name__ == "__main__":
    main()
