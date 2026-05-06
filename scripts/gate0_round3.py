"""Gate 0 Round 3 — FundingFlipStrategy on BTC.

Pre-registered in [docs/stage_gate.md](../docs/stage_gate.md) Round 3 spec
(commit ba2f7f8 or its successor).

Strategy: FundingFlipStrategy(threshold=0.0003, lookback=24)
- Short when 24h funding average > +0.03% / 8h (overheated long)
- Long when 24h funding average < -0.03% / 8h (overheated short)

This script does not go through grid.run_grid_realdata because the
strategy needs funding_series injected at construction time (signal
source) AND BacktestConfig also takes funding_rates (cost). We loop
explicitly to keep both wired without modifying grid.py.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from leverage_survival_lab.analysis.metrics import max_drawdown
from leverage_survival_lab.analysis.stats import deflated_sharpe
from leverage_survival_lab.backtest.grid import random_window_slices
from leverage_survival_lab.backtest.runner import BacktestConfig, run_backtest
from leverage_survival_lab.config import settings
from leverage_survival_lab.strategies.funding_filter import FundingFlipStrategy

LEVERAGES = (1, 2, 3, 5)
STOP_LOSSES = (None, -0.02, -0.05)
TAKE_PROFITS = (None,)
WINDOW_DAYS = 90
WINDOW_BARS = 24 * WINDOW_DAYS
SEED = 20260507
N_WINDOWS_DEFAULT = 200
THRESHOLD = 0.0003
LOOKBACK = 24

GATE0_THRESHOLDS = {
    "median_annual_log_return": 0.0,
    "deflated_sharpe_prob": 0.95,
    "bust_rate_window_50pct": 0.05,
}


def _run_one(
    wdf: pd.DataFrame, fr: pd.Series, *,
    leverage: float, stop_loss: float | None, take_profit: float | None,
) -> dict:
    strat = FundingFlipStrategy(threshold=THRESHOLD, lookback=LOOKBACK, funding_series=fr)
    sig = strat.generate(wdf)
    cfg = BacktestConfig(
        leverage=leverage,
        stop_loss=stop_loss,
        take_profit=take_profit,
        initial_equity=settings.initial_equity_usdt,
        funding_rates=fr,
    )
    res = run_backtest(wdf, sig, cfg)
    eq = res.equity_curve
    eq0 = float(eq.iloc[0])
    return {
        "leverage": float(leverage),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "final_equity": res.final_equity,
        "total_return": float(eq.iloc[-1] / eq0 - 1.0),
        "max_drawdown": float(max_drawdown(eq)),
        "min_equity_ratio": float(eq.min() / eq0),
        "n_liquidations": res.n_liquidations,
        "is_bust": res.is_bust,
        "total_fees": res.total_fees,
        "total_funding": res.total_funding,
        "n_trades": len(res.trades),
        "n_signal_nonzero": int((sig != 0).sum()),
    }


def _summarize(records: pd.DataFrame, *, window_days: float) -> pd.DataFrame:
    initial = settings.initial_equity_usdt
    cells = list(records.groupby(["leverage", "stop_loss", "take_profit"], dropna=False))
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
            "median_n_signal_nonzero": float(g["n_signal_nonzero"].median()),
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
    table = Table(title=f"FundingFlip 90d N={len(df) and df['n'].iloc[0]} (n_trials={len(df)})")
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
    p.add_argument("--name", default="gate0_round3_btc")
    args = p.parse_args()

    console = Console()
    df = pd.read_parquet("data/raw/binance_BTCUSDT_1h.parquet")
    fr = pd.read_parquet("data/raw/binance_BTCUSDT_funding.parquet")["rate"]
    console.print(
        f"[cyan]BTC[/cyan]: 1h {df.shape[0]:,} bars, funding {fr.shape[0]:,} ticks"
    )

    windows = random_window_slices(df, window_bars=WINDOW_BARS, n_windows=args.n_windows, seed=SEED)
    console.print(f"running {len(windows) * len(LEVERAGES) * len(STOP_LOSSES):,} simulations")

    records: list[dict] = []
    for label, wdf in windows:
        for lev in LEVERAGES:
            for sl in STOP_LOSSES:
                for tp in TAKE_PROFITS:
                    rec = _run_one(wdf, fr, leverage=float(lev), stop_loss=sl, take_profit=tp)
                    rec["window_label"] = label
                    records.append(rec)

    raw = pd.DataFrame(records)
    raw_path = settings.results_dir / f"{args.name}_n{args.n_windows}.parquet"
    raw.to_parquet(raw_path, compression="zstd")

    summary = _summarize(raw, window_days=float(WINDOW_DAYS))
    summary_path = settings.results_dir / f"{args.name}_n{args.n_windows}_summary.parquet"
    summary.to_parquet(summary_path, compression="zstd")

    _render(console, summary)
    n_pass = int(summary["gate0_pass"].sum())
    console.print(f"\n[bold]Round 3 PASS: {n_pass} / {len(summary)}[/bold]")
    if n_pass:
        console.print("[bold green]Gate 0 通過 cell あり -> Gate 1 official 検討[/bold green]")
    else:
        console.print("[bold red]全 cell fail — SMA + Funding 両方 fail[/bold red]")

    # Markdown report
    lines = [
        f"# Gate 0 Round 3 — FundingFlipStrategy (BTC, window={WINDOW_DAYS}d, N={args.n_windows})",
        "",
        f"Pre-reg: stage_gate.md Round 3 spec. threshold={THRESHOLD}, lookback={LOOKBACK}.",
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
    report_path = settings.results_dir / f"{args.name}_n{args.n_windows}_report.md"
    Path(report_path).write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]report[/green]: {report_path}")


if __name__ == "__main__":
    main()
