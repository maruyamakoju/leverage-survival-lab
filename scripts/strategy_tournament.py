"""戦略トーナメント — 各戦略 × (レバ, SL, TP) 組合せをバックテストし、勝者を見つける。

研究フェーズの全 6 戦略を、より細かい (lev, sl, tp) パラメータで横並び評価する。
基準: 過去 BTC 1h × 200 ランダム 30日窓での平均終端残高 + 勝率 + Sharpe。
"""
from __future__ import annotations

import argparse
import logging
from itertools import product

import numpy as np
import pandas as pd
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from leverage_survival_lab.analysis.metrics import sharpe_ratio
from leverage_survival_lab.backtest.grid import (
    GridSpec, run_grid_realdata, save_grid_results
)
from leverage_survival_lab.config import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler()])

    df = pd.read_parquet(args.data)
    console.print(f"loaded {len(df)} bars")

    # トーナメント設定:
    #   研究で 1-3x は trend_filtered_sma に edge があったので、その近辺を厚く
    #   stop_loss: -1, -2, -3, -5%
    #   take_profit: なし(SL のみ) と +5% 利確
    #   strategies: 全部入り
    spec = GridSpec(
        leverages=(1, 2, 3, 5, 10),
        stop_losses=(-0.01, -0.02, -0.03, -0.05),
        take_profits=(None,),
        strategies=("random", "sma_cross", "rsi", "bollinger", "breakout", "trend_filtered_sma"),
        n_seeds=args.n_windows,
    )
    console.print(f"tournament: {spec.n_cells():,} simulations")

    out_df = run_grid_realdata(
        df, spec, n_windows=args.n_windows, seed=args.seed,
        n_workers=1, show_progress=False,
    )
    save_grid_results(out_df, "tournament_winner_search")

    valid = out_df[out_df["error"].isna()] if "error" in out_df.columns else out_df

    # 各 (戦略, レバ, SL) セルで集計
    rows = []
    for (strat, lev, sl), g in valid.groupby(["strategy_name", "leverage", "stop_loss"], dropna=False):
        successes = (g["final_equity"] >= 100_000).sum()
        rows.append({
            "strategy": strat,
            "lev": int(lev),
            "sl": sl if pd.isna(sl) else f"{sl*100:.0f}%",
            "n": len(g),
            "win_rate": float((g["final_equity"] >= settings.initial_equity_usdt).mean()),
            "survival": float(successes / len(g)),
            "median_eq": float(g["final_equity"].median()),
            "mean_eq": float(g["final_equity"].mean()),
            "median_ret": float(g["final_equity"].median() / settings.initial_equity_usdt - 1),
            "mean_ret": float(g["final_equity"].mean() / settings.initial_equity_usdt - 1),
            "median_dd": float(g["max_drawdown"].median()),
        })
    summary = pd.DataFrame(rows)

    # スコア:平均リターン + 勝率(両方が大事)
    summary["score"] = summary["mean_ret"] + summary["win_rate"] * 0.5

    summary = summary.sort_values("score", ascending=False).reset_index(drop=True)
    out_path = settings.results_dir / "tournament_summary.parquet"
    summary.to_parquet(out_path, compression="zstd")
    console.print(f"saved: {out_path}")

    # 上位 15 表示
    table = Table(title="Top 15 (戦略, レバ, SL) by mean return + 0.5*win_rate")
    for col in ["strategy", "lev", "sl", "win_rate", "survival", "median_ret", "mean_ret", "median_dd"]:
        table.add_column(col)
    for _, r in summary.head(15).iterrows():
        table.add_row(
            r["strategy"], str(r["lev"]), str(r["sl"]),
            f"{r['win_rate']*100:.1f}%", f"{r['survival']*100:.1f}%",
            f"{r['median_ret']*100:+.2f}%", f"{r['mean_ret']*100:+.2f}%",
            f"{r['median_dd']*100:.1f}%",
        )
    console.print(table)

    # 期待値プラスのセル
    pos = summary[summary["mean_ret"] > 0]
    console.print(f"\n期待値プラスのセル: {len(pos)} / {len(summary)}")
    if len(pos) > 0:
        console.print(pos.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
