"""Run low/mid-leverage cross-asset robustness checks.

This is intentionally focused on the band that still showed possible edge in
the larger experiments: 1x to 10x, selected stop-loss/take-profit settings, and
non-random strategies.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from leverage_survival_lab.backtest.grid import GridSpec, run_grid_realdata, save_grid_results
from leverage_survival_lab.config import settings


def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _summarize(asset: str, df: pd.DataFrame) -> pd.DataFrame:
    valid = df[df["error"].isna()] if "error" in df.columns else df
    rows: list[dict] = []
    for (strategy, leverage, stop_loss, take_profit), g in valid.groupby(
        ["strategy_name", "leverage", "stop_loss", "take_profit"], dropna=False
    ):
        final = g["final_equity"]
        ret = final / settings.initial_equity_usdt - 1.0
        rows.append({
            "asset": asset,
            "strategy": strategy,
            "leverage": float(leverage),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "n": len(g),
            "win_rate": float((final >= settings.initial_equity_usdt).mean()),
            "survival": float((final >= settings.initial_equity_usdt * 0.10).mean()),
            "bust_rate": float(g["is_bust"].mean()),
            "median_ret": float(ret.median()),
            "mean_ret": float(ret.mean()),
            "median_dd": float(g["max_drawdown"].median()),
        })
    summary = pd.DataFrame(rows)
    summary["score"] = (
        summary["median_ret"]
        + 0.5 * summary["mean_ret"]
        + 0.3 * summary["win_rate"]
        - 0.5 * summary["bust_rate"]
    )
    return summary.sort_values("score", ascending=False).reset_index(drop=True)


def _render_table(console: Console, title: str, df: pd.DataFrame, n: int = 12) -> None:
    table = Table(title=title)
    for col in ["asset", "strategy", "lev", "sl", "tp", "win", "surv", "med", "mean", "dd"]:
        table.add_column(col)
    for _, r in df.head(n).iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        tp = "None" if pd.isna(r["take_profit"]) else _fmt_pct(float(r["take_profit"]))
        table.add_row(
            str(r["asset"]),
            str(r["strategy"]),
            f"{int(r['leverage'])}x",
            sl,
            tp,
            f"{r['win_rate'] * 100:.1f}%",
            f"{r['survival'] * 100:.1f}%",
            _fmt_pct(float(r["median_ret"])),
            _fmt_pct(float(r["mean_ret"])),
            _fmt_pct(float(r["median_dd"])),
        )
    console.print(table)


def _write_markdown(summary: pd.DataFrame, out_path: Path) -> None:
    robust = (
        summary.groupby(["strategy", "leverage", "stop_loss", "take_profit"], dropna=False)
        .agg(
            assets=("asset", "nunique"),
            avg_score=("score", "mean"),
            min_survival=("survival", "min"),
            avg_win_rate=("win_rate", "mean"),
            avg_median_ret=("median_ret", "mean"),
            worst_median_dd=("median_dd", "min"),
        )
        .reset_index()
        .sort_values(["assets", "avg_score"], ascending=[False, False])
    )

    lines = [
        "# Codex Low-Leverage Cross-Asset Report",
        "",
        "## Top Robust Cells",
        "",
        "| Strategy | Lev | SL | TP | Assets | Avg score | Min survival | Avg win | Avg median ret | Worst median DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in robust.head(30).iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        tp = "None" if pd.isna(r["take_profit"]) else _fmt_pct(float(r["take_profit"]))
        lines.append(
            f"| {r['strategy']} | {int(r['leverage'])}x | {sl} | {tp} | "
            f"{int(r['assets'])} | {r['avg_score']:.4f} | "
            f"{r['min_survival'] * 100:.1f}% | {r['avg_win_rate'] * 100:.1f}% | "
            f"{_fmt_pct(float(r['avg_median_ret']))} | {_fmt_pct(float(r['worst_median_dd']))} |"
        )

    lines.extend(["", "## Top By Asset", ""])
    for asset, g in summary.groupby("asset"):
        lines.extend([
            f"### {asset}",
            "",
            "| Strategy | Lev | SL | TP | Win | Survival | Median ret | Mean ret | Median DD |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for _, r in g.head(15).iterrows():
            sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
            tp = "None" if pd.isna(r["take_profit"]) else _fmt_pct(float(r["take_profit"]))
            lines.append(
                f"| {r['strategy']} | {int(r['leverage'])}x | {sl} | {tp} | "
                f"{r['win_rate'] * 100:.1f}% | {r['survival'] * 100:.1f}% | "
                f"{_fmt_pct(float(r['median_ret']))} | {_fmt_pct(float(r['mean_ret']))} | "
                f"{_fmt_pct(float(r['median_dd']))} |"
            )
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--assets", default="BTC,ETH,SOL")
    p.add_argument("--n-windows", type=int, default=200)
    p.add_argument("--seed", type=int, default=20260507)
    p.add_argument("--name", default="codex_lowlev_cross_asset")
    p.add_argument("--n-workers", type=int, default=1)
    args = p.parse_args()

    console = Console()
    all_summaries: list[pd.DataFrame] = []
    for asset in [a.strip().upper() for a in args.assets.split(",") if a.strip()]:
        data_path = Path(f"data/raw/binance_{asset}USDT_1h.parquet")
        if not data_path.exists():
            console.print(f"[yellow]skip[/yellow] {asset}: missing {data_path}")
            continue

        df = pd.read_parquet(data_path)
        spec = GridSpec(
            leverages=(1, 2, 3, 5, 7, 10),
            stop_losses=(-0.02, -0.05, None),
            take_profits=(None, 0.10),
            strategies=("sma_cross", "rsi", "breakout", "trend_filtered_sma"),
            n_seeds=args.n_windows,
        )
        console.print(f"[cyan]{asset}[/cyan] {spec.n_cells():,} simulations")
        grid = run_grid_realdata(
            df,
            spec,
            n_windows=args.n_windows,
            seed=args.seed,
            n_workers=args.n_workers,
            show_progress=False,
        )
        save_grid_results(grid, f"{args.name}_{asset}_n{args.n_windows}")
        summary = _summarize(asset, grid)
        all_summaries.append(summary)
        _render_table(console, f"{asset} top cells", summary, n=8)

    if not all_summaries:
        raise SystemExit("no assets processed")

    combined = pd.concat(all_summaries, ignore_index=True)
    out_summary = settings.results_dir / f"{args.name}_summary_n{args.n_windows}.parquet"
    out_report = settings.results_dir / f"{args.name}_report_n{args.n_windows}.md"
    combined.to_parquet(out_summary, compression="zstd")
    _write_markdown(combined, out_report)
    console.print(f"[green]summary[/green]: {out_summary}")
    console.print(f"[green]report[/green]: {out_report}")

    robust = (
        combined.groupby(["strategy", "leverage", "stop_loss", "take_profit"], dropna=False)
        .agg(
            assets=("asset", "nunique"),
            avg_score=("score", "mean"),
            min_survival=("survival", "min"),
            avg_win_rate=("win_rate", "mean"),
            avg_median_ret=("median_ret", "mean"),
            worst_median_dd=("median_dd", "min"),
        )
        .reset_index()
        .sort_values(["assets", "avg_score"], ascending=[False, False])
    )
    robust_display = robust.assign(asset="ALL", mean_ret=robust["avg_median_ret"]).rename(columns={
        "avg_win_rate": "win_rate",
        "min_survival": "survival",
        "avg_median_ret": "median_ret",
        "worst_median_dd": "median_dd",
    })
    _render_table(console, "combined robust cells", robust_display, n=12)


if __name__ == "__main__":
    main()
