"""risk_fraction(1ポジで資金の何割を IM にするか)を sweep する実験。

H1 / H4 の頑健性チェック: risk_fraction が小さければ単発清算でも一発死しないはず。
このとき高レバの生存率は改善するか?
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.logging import RichHandler

from leverage_survival_lab.analysis.stats import survival_summary, wilson_ci
from leverage_survival_lab.backtest.grid import GridSpec, run_grid_realdata, save_grid_results
from leverage_survival_lab.config import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--name", default="rf_sweep_btc_n100")
    p.add_argument("--risk-fractions", default="1.0,0.5,0.25,0.10,0.05")
    p.add_argument("--strategies", default="random")
    args = p.parse_args()

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(console=console)])

    df = pd.read_parquet(args.data)
    rfs = tuple(float(x) for x in args.risk_fractions.split(","))
    spec = GridSpec(
        n_seeds=args.n_windows,
        strategies=tuple(args.strategies.split(",")),
        risk_fractions=rfs,
    )
    console.print(f"running {spec.n_cells()} simulations, rfs={rfs}")

    out_df = run_grid_realdata(df, spec, n_windows=args.n_windows, seed=args.seed,
                                n_workers=1, show_progress=False)
    out_path = save_grid_results(out_df, args.name)
    console.print(f"[green]saved[/green]: {out_path} ({len(out_df)} rows)")

    # risk_fraction × leverage の生存率テーブル
    console.print("\n=== Survival rate by (risk_fraction, leverage) at 100x focus ===")
    valid = out_df[out_df["error"].isna()] if "error" in out_df.columns else out_df
    for rf in rfs:
        sub = valid[(valid["risk_fraction"] == rf) & (valid["leverage"] == 100.0)]
        successes = int((sub["final_equity"] >= settings.initial_equity_usdt * 0.10).sum())
        ci = wilson_ci(successes, len(sub))
        console.print(f"  rf={rf:.2f}  N={len(sub):4d}  100x survival = {ci.p*100:5.2f}%  CI=[{ci.lo*100:.2f}%, {ci.hi*100:.2f}%]")

    # 全 leverage × risk_fraction
    console.print("\n=== Survival rate matrix (rows: leverage, cols: risk_fraction) ===")
    pivot = (
        valid.assign(survives=lambda d: (d["final_equity"] >= settings.initial_equity_usdt * 0.10).astype(int))
             .groupby(["leverage", "risk_fraction"])["survives"]
             .mean()
             .unstack()
    )
    console.print(pivot.to_string(float_format=lambda x: f"{x*100:5.1f}%"))


if __name__ == "__main__":
    main()
