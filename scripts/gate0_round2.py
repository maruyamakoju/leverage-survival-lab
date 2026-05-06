"""Gate 0 Round 2 — strategy-fixed (trend_filtered_sma) across multiple windows.

Pre-registered in [docs/stage_gate.md](../docs/stage_gate.md) Round 2 spec
(commit pre-dating this script execution).

- Strategy fixed: trend_filtered_sma (= bot V3.9 trend_sma logic)
- Window-days: {30, 90, 180} evaluated independently
- Leverages: {1, 2, 3, 5}x  (10x+ excluded; Round 1 confirmed total wipeout)
- Stop-losses: {None, -2%, -5%}
- Take-profits: {None}
- N = 200 random windows / window-length, seed=20260507
- Funding: real BTC funding rate injected
- Bonferroni n_trials = 12 (lev x SL) per window-length; the strategy axis is fixed.
- Pass = all of:
    median_annual_log_return > 0
    deflated_sharpe_prob > 0.95
    bust_rate_window_50pct < 5%
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

GATE0_THRESHOLDS = {
    "median_annual_log_return": 0.0,
    "deflated_sharpe_prob": 0.95,
    "bust_rate_window_50pct": 0.05,
}

WINDOW_DAYS_LIST = (30, 90, 180)
LEVERAGES = (1, 2, 3, 5)
STOP_LOSSES = (None, -0.02, -0.05)
TAKE_PROFITS = (None,)
STRATEGY = "trend_filtered_sma"
N_WINDOWS_DEFAULT = 200
SEED = 20260507


def _load_btc() -> tuple[pd.DataFrame, pd.Series]:
    px = pd.read_parquet("data/raw/binance_BTCUSDT_1h.parquet")
    fr = pd.read_parquet("data/raw/binance_BTCUSDT_funding.parquet")["rate"]
    return px, fr


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
        log_ret_window = np.log(np.clip(finals / initial, 1e-9, None))
        annual_log_ret = log_ret_window * annualization

        if log_ret_window.std(ddof=0) > 0:
            sample_sharpe = float(
                math.sqrt(annualization) * log_ret_window.mean() / log_ret_window.std(ddof=0)
            )
        else:
            sample_sharpe = float("nan")
        dsr = (
            deflated_sharpe(sample_sharpe, n_trials=n_trials, n_periods=n)
            if not math.isnan(sample_sharpe) else float("nan")
        )
        bust_w = float((g["min_equity_ratio"] < 0.5).mean())

        rows.append({
            "window_days": int(window_days),
            "strategy": STRATEGY,
            "leverage": float(leverage),
            "stop_loss": sl,
            "take_profit": tp,
            "n": n,
            "median_window_log_return": float(np.median(log_ret_window)),
            "median_annual_log_return": float(np.median(annual_log_ret)),
            "mean_annual_log_return": float(np.mean(annual_log_ret)),
            "sample_sharpe": sample_sharpe,
            "deflated_sharpe_prob": float(dsr) if not math.isnan(dsr) else float("nan"),
            "bust_rate_window_50pct": bust_w,
            "final_below_50pct": float((finals < initial * 0.5).mean()),
            "liq_rate": float((g["n_liquidations"] > 0).mean()),
            "median_total_fees_pct": float(g["total_fees"].median() / initial),
            "median_total_funding_pct": float(g["total_funding"].median() / initial),
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


def _fmt_prob(x: float) -> str:
    if pd.isna(x):
        return "nan"
    return f"{x:.3f}"


def _render(console: Console, df: pd.DataFrame, window_days: int) -> None:
    table = Table(title=f"{STRATEGY} window={window_days}d (n_trials={len(df)})")
    for col in [
        "lev", "SL", "n", "med_ann_log_ret", "Sharpe", "DSR_prob", "bust_w", "fees%", "fund%", "Gate 0",
    ]:
        table.add_column(col)
    for _, r in df.iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        table.add_row(
            f"{int(r['leverage'])}x",
            sl,
            str(int(r["n"])),
            _fmt_pct(float(r["median_annual_log_return"])),
            f"{r['sample_sharpe']:+.2f}" if not pd.isna(r["sample_sharpe"]) else "nan",
            _fmt_prob(float(r["deflated_sharpe_prob"])),
            _fmt_pct(float(r["bust_rate_window_50pct"])),
            _fmt_pct(float(r["median_total_fees_pct"])),
            _fmt_pct(float(r["median_total_funding_pct"])),
            "PASS" if bool(r["gate0_pass"]) else "fail",
        )
    console.print(table)


def _write_markdown(by_window: dict[int, pd.DataFrame], out_path: Path, n_windows: int) -> None:
    lines = [
        f"# Gate 0 Round 2 — {STRATEGY} (BTC, N={n_windows})",
        "",
        "Strategy fixed in pre-reg ([stage_gate.md](../docs/stage_gate.md) Round 2 spec).",
        "",
        f"- Leverages: {LEVERAGES}",
        f"- Stop-losses: {STOP_LOSSES}",
        f"- Take-profits: {TAKE_PROFITS}",
        f"- Bonferroni n_trials = {len(LEVERAGES) * len(STOP_LOSSES)} per window-length",
        "- Real Binance BTC funding injected",
        "",
    ]
    for w in sorted(by_window):
        df = by_window[w]
        passes = df[df["gate0_pass"]]
        lines += [
            f"## window = {w} days",
            "",
            f"PASS cells: **{len(passes)} / {len(df)}**",
            "",
            "| Lev | SL | Median ann log-ret | Sample Sharpe | DSR prob | Bust(window) | "
            "Med fees | Med funding | Gate 0 |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for _, r in df.iterrows():
            sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
            lines.append(
                f"| {int(r['leverage'])}x | {sl} | "
                f"{_fmt_pct(float(r['median_annual_log_return']))} | "
                f"{r['sample_sharpe']:+.3f} | "
                f"{_fmt_prob(float(r['deflated_sharpe_prob']))} | "
                f"{_fmt_pct(float(r['bust_rate_window_50pct']))} | "
                f"{_fmt_pct(float(r['median_total_fees_pct']))} | "
                f"{_fmt_pct(float(r['median_total_funding_pct']))} | "
                f"{'PASS' if bool(r['gate0_pass']) else 'fail'} |"
            )
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-windows", type=int, default=N_WINDOWS_DEFAULT)
    p.add_argument("--name", default="gate0_round2_btc")
    args = p.parse_args()

    console = Console()
    df, fr = _load_btc()
    console.print(
        f"[cyan]BTC[/cyan]: 1h {df.shape[0]:,} bars "
        f"({df.index.min().date()} -> {df.index.max().date()}), funding {fr.shape[0]:,} ticks"
    )

    by_window: dict[int, pd.DataFrame] = {}
    for w in WINDOW_DAYS_LIST:
        spec = GridSpec(
            leverages=LEVERAGES,
            stop_losses=STOP_LOSSES,
            take_profits=TAKE_PROFITS,
            strategies=(STRATEGY,),
            n_seeds=args.n_windows,
        )
        n_cells = (
            len(spec.leverages) * len(spec.stop_losses) * len(spec.take_profits) * args.n_windows
        )
        console.print(f"\n[bold]window={w}d[/bold] running {n_cells:,} simulations")
        grid = run_grid_realdata(
            df, spec,
            window_bars=24 * w,
            n_windows=args.n_windows,
            seed=SEED,
            n_workers=1,
            show_progress=False,
            funding_rates=fr,
        )
        raw_path = settings.results_dir / f"{args.name}_w{w}_n{args.n_windows}.parquet"
        grid.to_parquet(raw_path, compression="zstd")

        summary = _summarize(grid, window_days=float(w))
        summary_path = settings.results_dir / f"{args.name}_w{w}_n{args.n_windows}_summary.parquet"
        summary.to_parquet(summary_path, compression="zstd")

        by_window[w] = summary
        _render(console, summary, w)

    report_path = settings.results_dir / f"{args.name}_n{args.n_windows}_report.md"
    _write_markdown(by_window, report_path, args.n_windows)
    console.print(f"\n[green]report[/green]: {report_path}")

    overall_pass = any(int(d["gate0_pass"].sum()) > 0 for d in by_window.values())
    pass_summary = ", ".join(
        f"w{w}={int(by_window[w]['gate0_pass'].sum())}/{len(by_window[w])}"
        for w in sorted(by_window)
    )
    console.print(f"\n[bold]Round 2 PASS counts: {pass_summary}[/bold]")
    console.print(
        "[bold green]Gate 0 暫定通過[/bold green]" if overall_pass
        else "[bold red]Gate 0 全 window で fail[/bold red]"
    )


if __name__ == "__main__":
    main()
