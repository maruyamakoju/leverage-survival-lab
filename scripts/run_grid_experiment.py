"""グリッド実験オーケストレータ — 合成データで本格的なモンテカルロを回す。

使用例:
    python scripts/run_grid_experiment.py --n-seeds 100 --n-workers 4 --name pilot_v1
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from rich.console import Console
from rich.logging import RichHandler

from leverage_survival_lab.analysis.stats import survival_summary
from leverage_survival_lab.backtest.grid import GridSpec, run_grid_synthetic, save_grid_results
from leverage_survival_lab.config import settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-seeds", type=int, default=100)
    parser.add_argument("--n-bars", type=int, default=24 * 30)
    parser.add_argument("--drift", type=float, default=0.0)
    parser.add_argument("--vol", type=float, default=0.015)
    parser.add_argument("--n-workers", type=int, default=1)
    parser.add_argument("--name", default=None)
    parser.add_argument("--strategies", default="random,sma_cross,rsi,bollinger,breakout")
    args = parser.parse_args()

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(console=console)])

    name = args.name or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    spec = GridSpec(
        n_seeds=args.n_seeds,
        strategies=tuple(args.strategies.split(",")),
    )
    console.print(f"[bold]Grid spec[/bold]: {spec.n_cells()} simulations")

    df = run_grid_synthetic(
        spec, n_bars=args.n_bars, drift=args.drift, vol=args.vol,
        n_workers=args.n_workers,
    )
    out = save_grid_results(df, name)
    console.print(f"[green]saved[/green]: {out}")

    summary = survival_summary(df)
    summary_path = settings.results_dir / f"summary_{name}.parquet"
    summary.to_parquet(summary_path, compression="zstd")
    console.print(f"[green]summary[/green]: {summary_path}")
    console.print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
