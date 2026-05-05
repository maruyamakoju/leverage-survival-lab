"""拡張トーナメント — V1 で勝者だった RSI を中心に細部最適化、TP も導入する。

調査軸:
- 戦略: rsi(複数 period), trend_filtered_sma, 既存 5 種
- レバ: 1, 2, 3, 5, 7
- SL: -1%, -2%, -3%, -5%
- TP: None, +3%, +5%, +10%
- 窓: 200 個ランダム30日(BTC 1h)
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from leverage_survival_lab.backtest.grid import (
    GridSpec, run_grid_realdata, save_grid_results
)
from leverage_survival_lab.config import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler()])

    df = pd.read_parquet(args.data)
    console.print(f"loaded {len(df)} bars")

    spec = GridSpec(
        leverages=(1, 2, 3, 5, 7),
        stop_losses=(-0.01, -0.02, -0.03, -0.05),
        take_profits=(None, 0.03, 0.05, 0.10),
        strategies=("rsi", "trend_filtered_sma", "sma_cross",
                    "bollinger", "breakout", "random"),
        n_seeds=args.n_windows,
    )
    console.print(f"tournament v2: {spec.n_cells():,} simulations")

    out_df = run_grid_realdata(
        df, spec, n_windows=args.n_windows, seed=args.seed,
        n_workers=1, show_progress=False,
    )
    save_grid_results(out_df, "tournament_v2")

    valid = out_df[out_df["error"].isna()] if "error" in out_df.columns else out_df

    rows = []
    for (strat, lev, sl, tp), g in valid.groupby(
        ["strategy_name", "leverage", "stop_loss", "take_profit"], dropna=False
    ):
        rows.append({
            "strategy": strat,
            "lev": int(lev),
            "sl": "None" if pd.isna(sl) else f"{sl*100:.0f}%",
            "tp": "None" if pd.isna(tp) else f"+{tp*100:.0f}%",
            "n": len(g),
            "win_rate": float((g["final_equity"] >= settings.initial_equity_usdt).mean()),
            "median_eq": float(g["final_equity"].median()),
            "mean_eq": float(g["final_equity"].mean()),
            "median_ret": float(g["final_equity"].median() / settings.initial_equity_usdt - 1),
            "mean_ret": float(g["final_equity"].mean() / settings.initial_equity_usdt - 1),
            "sharpe_proxy": float(g["sharpe"].median()) if "sharpe" in g.columns else 0.0,
        })
    summary = pd.DataFrame(rows)

    # スコア: median return がプラス + 勝率(Sharpe で安定性も)
    summary["score"] = (
        summary["median_ret"] +
        summary["win_rate"] * 0.3 +
        summary["mean_ret"] * 0.5
    )

    summary = summary.sort_values("score", ascending=False).reset_index(drop=True)
    out_path = settings.results_dir / "tournament_v2_summary.parquet"
    summary.to_parquet(out_path, compression="zstd")
    console.print(f"saved: {out_path}")

    # 中央値プラスのみ抽出
    pos = summary[summary["median_ret"] > 0].copy()
    console.print(f"\n中央値プラスのセル: {len(pos)} / {len(summary)}")

    table = Table(title="Top 20 by score (median_ret + 0.3*win_rate + 0.5*mean_ret)")
    for col in ["strategy", "lev", "sl", "tp", "win_rate", "median_ret", "mean_ret"]:
        table.add_column(col)
    for _, r in summary.head(20).iterrows():
        table.add_row(
            r["strategy"], str(r["lev"]), str(r["sl"]), str(r["tp"]),
            f"{r['win_rate']*100:.1f}%",
            f"{r['median_ret']*100:+.2f}%",
            f"{r['mean_ret']*100:+.2f}%",
        )
    console.print(table)


if __name__ == "__main__":
    main()
