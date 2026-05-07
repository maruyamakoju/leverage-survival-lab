"""Gate 0 Round 5 — VolBreakoutStrategy on BTC 1h.

Pre-registered in [docs/stage_gate.md](../docs/stage_gate.md) Round 5 spec
(commit 77691d8).

Strategy fixed to VolBreakoutStrategy with classic Turtle-style params:
atr_period=14, lookback=20, k_atr=1.5, vol_lookback=100, vol_threshold=1.0.

Bonferroni n_trials = 12 (lev x SL).
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from leverage_survival_lab.analysis.stats import deflated_sharpe
from leverage_survival_lab.backtest.grid import GridSpec, run_grid_realdata
from leverage_survival_lab.config import settings

LEVERAGES = (1, 2, 3, 5)
STOP_LOSSES = (None, -0.02, -0.05)
TAKE_PROFITS = (None,)
STRATEGY = "vol_breakout"
WINDOW_DAYS = 90
SEED = 20260507
N_WINDOWS_DEFAULT = 200

GATE0_THRESHOLDS = {
    "median_annual_log_return": 0.0,
    "deflated_sharpe_prob": 0.95,
    "bust_rate_window_50pct": 0.05,
}


def _summarize(grid_df: pd.DataFrame, *, window_days: float) -> pd.DataFrame:
    valid = grid_df[grid_df["error"].isna()] if "error" in grid_df.columns else grid_df
    initial = settings.initial_equity_usdt
    cells = list(valid.groupby(["leverage", "stop_loss", "take_profit"], dropna=False))
    n_trials = max(1, len(cells))
    annualization = 365.25 / window_days

    rows: list[dict] = []
    for (leverage, sl, tp), g in cells:
        n = len(g)
        finals = g["final_equity"].to_numpy()
        log_ret = np.log(np.clip(finals / initial, 1e-9, None))
        ann_log_ret = log_ret * annualization

        if log_ret.std(ddof=0) > 0:
            sharpe = float(math.sqrt(annualization) * log_ret.mean() / log_ret.std(ddof=0))
        else:
            sharpe = float("nan")
        dsr = (
            deflated_sharpe(sharpe, n_trials=n_trials, n_periods=n)
            if not math.isnan(sharpe) else float("nan")
        )
        bust_w = float((g["min_equity_ratio"] < 0.5).mean())

        rows.append({
            "leverage": float(leverage),
            "stop_loss": sl,
            "take_profit": tp,
            "n": n,
            "median_annual_log_return": float(np.median(ann_log_ret)),
            "mean_annual_log_return": float(np.mean(ann_log_ret)),
            "sample_sharpe": sharpe,
            "deflated_sharpe_prob": float(dsr) if not math.isnan(dsr) else float("nan"),
            "bust_rate_window_50pct": bust_w,
            "median_total_fees_pct": float(g["total_fees"].median() / initial),
            "median_total_funding_pct": float(g["total_funding"].median() / initial),
            "median_n_trades": float(g["n_trades"].median()),
        })
    out = pd.DataFrame(rows)
    out["pass_return"] = out["median_annual_log_return"] > GATE0_THRESHOLDS["median_annual_log_return"]
    out["pass_dsr"] = out["deflated_sharpe_prob"] > GATE0_THRESHOLDS["deflated_sharpe_prob"]
    out["pass_bust"] = out["bust_rate_window_50pct"] < GATE0_THRESHOLDS["bust_rate_window_50pct"]
    out["gate0_pass"] = out["pass_return"] & out["pass_dsr"] & out["pass_bust"]
    return out.sort_values(
        ["gate0_pass", "median_annual_log_return"], ascending=[False, False]
    ).reset_index(drop=True)


def _fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "nan"
    return f"{x * 100:+.2f}%"


def _render(console: Console, df: pd.DataFrame) -> None:
    table = Table(title=f"VolBreakout Round 5 (n_trials={len(df)})")
    for col in ["lev", "SL", "n", "med_ann", "Sharpe", "DSR", "bust_w", "fund%", "trades", "Gate0"]:
        table.add_column(col)
    for _, r in df.iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        table.add_row(
            f"{int(r['leverage'])}x", sl, str(int(r["n"])),
            _fmt_pct(float(r["median_annual_log_return"])),
            f"{r['sample_sharpe']:+.2f}",
            f"{r['deflated_sharpe_prob']:.3f}" if not pd.isna(r["deflated_sharpe_prob"]) else "nan",
            _fmt_pct(float(r["bust_rate_window_50pct"])),
            _fmt_pct(float(r["median_total_funding_pct"])),
            f"{r['median_n_trades']:.0f}",
            "PASS" if bool(r["gate0_pass"]) else "fail",
        )
    console.print(table)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-windows", type=int, default=N_WINDOWS_DEFAULT)
    p.add_argument("--name", default="gate0_round5_btc")
    args = p.parse_args()

    console = Console()
    df = pd.read_parquet("data/raw/binance_BTCUSDT_1h.parquet")
    fr = pd.read_parquet("data/raw/binance_BTCUSDT_funding.parquet")["rate"]
    console.print(f"[cyan]BTC[/cyan]: 1h {df.shape[0]:,} bars, funding {fr.shape[0]:,} ticks")

    spec = GridSpec(
        leverages=LEVERAGES,
        stop_losses=STOP_LOSSES,
        take_profits=TAKE_PROFITS,
        strategies=(STRATEGY,),
        n_seeds=args.n_windows,
    )
    n_cells = len(spec.leverages) * len(spec.stop_losses) * len(spec.take_profits) * args.n_windows
    console.print(f"running {n_cells:,} simulations")

    grid = run_grid_realdata(
        df, spec,
        window_bars=24 * WINDOW_DAYS,
        n_windows=args.n_windows,
        seed=SEED,
        n_workers=1,
        show_progress=False,
        funding_rates=fr,
    )
    raw_path = settings.results_dir / f"{args.name}_n{args.n_windows}.parquet"
    grid.to_parquet(raw_path, compression="zstd")

    summary = _summarize(grid, window_days=float(WINDOW_DAYS))
    summary_path = settings.results_dir / f"{args.name}_n{args.n_windows}_summary.parquet"
    summary.to_parquet(summary_path, compression="zstd")

    _render(console, summary)
    n_pass = int(summary["gate0_pass"].sum())
    console.print(f"\n[bold]Round 5 PASS: {n_pass} / {len(summary)}[/bold]")
    if n_pass:
        console.print("[bold green]Gate 0 通過 cell あり -> Gate 1 へ[/bold green]")
    else:
        console.print("[bold red]全 cell fail — SMA + FundingFlip + VolBreakout 全滅[/bold red]")

    # Markdown report
    lines = [
        f"# Gate 0 Round 5 — VolBreakoutStrategy (BTC, window={WINDOW_DAYS}d, N={args.n_windows})",
        "",
        "Pre-reg: stage_gate.md Round 5 (commit 77691d8). "
        "atr_period=14, lookback=20, k_atr=1.5, vol_lookback=100, vol_threshold=1.0.",
        "",
        f"PASS: **{n_pass} / {len(summary)}**",
        "",
        "| Lev | SL | n | Median ann log-ret | Sample Sharpe | DSR prob | Bust(window) "
        "| Med funding | Med trades | Gate 0 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        lines.append(
            f"| {int(r['leverage'])}x | {sl} | {int(r['n'])} | "
            f"{_fmt_pct(float(r['median_annual_log_return']))} | "
            f"{r['sample_sharpe']:+.3f} | "
            f"{r['deflated_sharpe_prob']:.3f} | "
            f"{_fmt_pct(float(r['bust_rate_window_50pct']))} | "
            f"{_fmt_pct(float(r['median_total_funding_pct']))} | "
            f"{r['median_n_trades']:.0f} | "
            f"{'PASS' if bool(r['gate0_pass']) else 'fail'} |"
        )
    Path(settings.results_dir / f"{args.name}_n{args.n_windows}_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
