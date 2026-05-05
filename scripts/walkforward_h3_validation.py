"""trend_filtered_sma の walk-forward 検証 — IS でフィルタなし、OOS で適用すると edge は残るか?

実は trend_filtered_sma はパラメータ最適化していないので IS/OOS の問題は限定的だが、
OOS でも positive edge が再現されるかは独立検証として価値がある。
"""
from __future__ import annotations

import argparse
import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from leverage_survival_lab.backtest.runner import BacktestConfig, run_backtest
from leverage_survival_lab.backtest.walkforward import split_walkforward
from leverage_survival_lab.strategies import RandomStrategy, SMACrossStrategy, TrendFilteredSMA


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--train-bars", type=int, default=24 * 90)
    p.add_argument("--test-bars", type=int, default=24 * 30)
    p.add_argument("--leverages", default="2,3,5,10")
    args = p.parse_args()

    console = Console()
    df = pd.read_parquet(args.data)

    levs = [float(x) for x in args.leverages.split(",")]
    rows = []
    for train, test in split_walkforward(df, train_bars=args.train_bars, test_bars=args.test_bars):
        for L in levs:
            for strategy_cls, strategy_kwargs in [
                (RandomStrategy, {"p_long": 0.05, "p_short": 0.05, "seed": int(train.index[0].timestamp())}),
                (SMACrossStrategy, {"fast": 20, "slow": 50}),
                (TrendFilteredSMA, {"fast": 20, "slow": 50, "trend": 200}),
            ]:
                strat = strategy_cls(**strategy_kwargs)
                cfg = BacktestConfig(leverage=L, stop_loss=-0.02, risk_fraction=1.0)
                # IS
                sig_is = strat.generate(train)
                r_is = run_backtest(train, sig_is, cfg)
                # OOS
                sig_oos = strat.generate(test)
                r_oos = run_backtest(test, sig_oos, cfg)
                rows.append({
                    "test_start": test.index[0].strftime("%Y-%m-%d"),
                    "leverage": L,
                    "strategy": strategy_cls.__name__,
                    "is_log_ret": np.log(max(r_is.final_equity, 1.0) / cfg.initial_equity),
                    "oos_log_ret": np.log(max(r_oos.final_equity, 1.0) / cfg.initial_equity),
                })

    res = pd.DataFrame(rows)

    table = Table(title="Walk-forward edge validation (mean log-return by strategy × leverage)")
    table.add_column("Leverage")
    for s in res["strategy"].unique():
        table.add_column(f"{s} IS")
        table.add_column(f"{s} OOS")
    for L in levs:
        row = [f"{int(L)}x"]
        for s in res["strategy"].unique():
            sub = res[(res["leverage"] == L) & (res["strategy"] == s)]
            if sub.empty:
                row.extend(["—", "—"])
                continue
            row.append(f"{sub['is_log_ret'].mean():+.3f}")
            row.append(f"{sub['oos_log_ret'].mean():+.3f}")
        table.add_row(*row)
    console.print(table)


if __name__ == "__main__":
    main()
