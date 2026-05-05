"""実データ(Binance OHLCV)でランダム30日窓モンテカルロを回す。"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.logging import RichHandler

from leverage_survival_lab.analysis.stats import survival_summary
from leverage_survival_lab.backtest.grid import GridSpec, run_grid_realdata, save_grid_results
from leverage_survival_lab.config import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=100)
    p.add_argument("--window-bars", type=int, default=24 * 30)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-workers", type=int, default=1)
    p.add_argument("--name", default="real_btc_n100")
    p.add_argument("--strategies", default="random,sma_cross,rsi,bollinger,breakout")
    args = p.parse_args()

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(console=console)])

    df = pd.read_parquet(args.data)
    console.print(f"[bold]loaded[/bold] {len(df)} bars from {args.data}")

    spec = GridSpec(
        n_seeds=args.n_windows,
        strategies=tuple(args.strategies.split(",")),
    )
    out_df = run_grid_realdata(
        df, spec,
        window_bars=args.window_bars,
        n_windows=args.n_windows,
        seed=args.seed,
        n_workers=args.n_workers,
    )
    out = save_grid_results(out_df, args.name)
    console.print(f"[green]saved[/green]: {out}")

    if "error" in out_df.columns:
        n_err = int(out_df["error"].notna().sum())
        if n_err > 0:
            console.print(f"[red]errors[/red]: {n_err}/{len(out_df)}")
            console.print(out_df[out_df["error"].notna()][["strategy_name", "leverage", "stop_loss", "data_id", "error"]].head(5).to_string(index=False))

    valid = out_df[out_df["error"].isna()] if "error" in out_df.columns else out_df
    summary = survival_summary(valid)
    summary_path = settings.results_dir / f"summary_{args.name}.parquet"
    summary.to_parquet(summary_path, compression="zstd")
    console.print(f"[green]summary[/green]: {summary_path}")
    console.print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
