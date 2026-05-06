"""Gate 1 PREVIEW (not official) — cross-asset re-run of trend_filtered_sma.

Note: this is a preview, not an official Gate 1 evaluation, because:
- ETH/SOL funding rates were not retrievable from this environment, so
  ETH/SOL runs are funding-free (BTC keeps real funding injected).
- Funding adds ~0.5% per 90d on BTC at 1x; expect a similar magnitude bias
  for ETH/SOL — the funding-free numbers below are upper bounds.

Pre-reg deviation acknowledgement: Gate 1 (per stage_gate.md) requires
identical conditions across BTC/ETH/SOL with funding. We cannot satisfy
that here, so we mark the result as preview and do NOT use it to declare
Gate 1 pass/fail.

Round 2 picked window=90d as the most informative aggregation, so we use
that single window here. lev x SL grid matches Round 2.
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

WINDOW_DAYS = 90
LEVERAGES = (1, 2, 3, 5)
STOP_LOSSES = (None, -0.02, -0.05)
TAKE_PROFITS = (None,)
STRATEGY = "trend_filtered_sma"
SEED = 20260507

GATE0_THRESHOLDS = {
    "median_annual_log_return": 0.0,
    "deflated_sharpe_prob": 0.95,
    "bust_rate_window_50pct": 0.05,
}


def _load_asset(asset: str) -> tuple[pd.DataFrame, pd.Series | None]:
    px_path = Path(f"data/raw/binance_{asset}USDT_1h.parquet")
    if not px_path.exists():
        raise SystemExit(f"missing price parquet: {px_path}")
    df = pd.read_parquet(px_path)
    fr_path = Path(f"data/raw/binance_{asset}USDT_funding.parquet")
    fr = pd.read_parquet(fr_path)["rate"] if fr_path.exists() else None
    return df, fr


def _summarize(grid_df: pd.DataFrame, *, window_days: float, asset: str,
                funding_present: bool) -> pd.DataFrame:
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
            sharpe = float(
                math.sqrt(annualization) * log_ret_window.mean() / log_ret_window.std(ddof=0)
            )
        else:
            sharpe = float("nan")
        dsr = (
            deflated_sharpe(sharpe, n_trials=n_trials, n_periods=n)
            if not math.isnan(sharpe) else float("nan")
        )
        bust_w = float((g["min_equity_ratio"] < 0.5).mean())
        rows.append({
            "asset": asset,
            "funding_present": funding_present,
            "leverage": float(leverage),
            "stop_loss": sl,
            "take_profit": tp,
            "n": n,
            "median_annual_log_return": float(np.median(annual_log_ret)),
            "sample_sharpe": sharpe,
            "deflated_sharpe_prob": float(dsr) if not math.isnan(dsr) else float("nan"),
            "bust_rate_window_50pct": bust_w,
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


def _render(console: Console, df: pd.DataFrame, asset: str, funding_present: bool) -> None:
    title = f"{asset} (funding={'YES' if funding_present else 'NO (preview)'})"
    table = Table(title=title)
    for col in ["lev", "SL", "n", "med_ann", "Sharpe", "DSR_prob", "bust_w", "fund%", "Gate0"]:
        table.add_column(col)
    for _, r in df.iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        table.add_row(
            f"{int(r['leverage'])}x",
            sl,
            str(int(r["n"])),
            _fmt_pct(float(r["median_annual_log_return"])),
            f"{r['sample_sharpe']:+.2f}",
            f"{r['deflated_sharpe_prob']:.3f}" if not pd.isna(r["deflated_sharpe_prob"]) else "nan",
            _fmt_pct(float(r["bust_rate_window_50pct"])),
            _fmt_pct(float(r["median_total_funding_pct"])),
            "PASS" if bool(r["gate0_pass"]) else "fail",
        )
    console.print(table)


def _write_markdown(per_asset: dict[str, pd.DataFrame], out_path: Path, n_windows: int) -> None:
    lines = [
        f"# Gate 1 PREVIEW — {STRATEGY} cross-asset (window={WINDOW_DAYS}d, N={n_windows})",
        "",
        "**This is a preview, not official Gate 1.** ETH/SOL funding could not be retrieved",
        "in this environment, so those runs are funding-free (upper-bound estimates).",
        "BTC keeps real funding injected.",
        "",
        f"Strategy fixed: `{STRATEGY}` (Round 2 winner among the existing zoo).",
        "",
    ]
    for asset, df in per_asset.items():
        funding = bool(df["funding_present"].iloc[0])
        passes = int(df["gate0_pass"].sum())
        lines += [
            f"## {asset} (funding {'injected' if funding else 'OMITTED — upper bound'})",
            "",
            f"PASS cells: **{passes} / {len(df)}**",
            "",
            "| Lev | SL | Median ann log-ret | Sample Sharpe | DSR prob | Bust(window) "
            "| Med funding | Gate 0 |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for _, r in df.iterrows():
            sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
            lines.append(
                f"| {int(r['leverage'])}x | {sl} | "
                f"{_fmt_pct(float(r['median_annual_log_return']))} | "
                f"{r['sample_sharpe']:+.3f} | "
                f"{r['deflated_sharpe_prob']:.3f} | "
                f"{_fmt_pct(float(r['bust_rate_window_50pct']))} | "
                f"{_fmt_pct(float(r['median_total_funding_pct']))} | "
                f"{'PASS' if bool(r['gate0_pass']) else 'fail'} |"
            )
        lines.append("")

    # Cross-asset robust view
    combined = pd.concat(per_asset.values(), ignore_index=True)
    robust = (
        combined.groupby(["leverage", "stop_loss", "take_profit"], dropna=False)
        .agg(
            assets=("asset", "nunique"),
            min_median_ann_log_ret=("median_annual_log_return", "min"),
            mean_median_ann_log_ret=("median_annual_log_return", "mean"),
            max_bust=("bust_rate_window_50pct", "max"),
            min_sharpe=("sample_sharpe", "min"),
            n_pass=("gate0_pass", "sum"),
        )
        .reset_index()
        .sort_values(["assets", "min_median_ann_log_ret"], ascending=[False, False])
    )
    lines += [
        "## Cross-asset robust view (worst across assets)",
        "",
        "Sorted by min median ann log-ret across assets (worst-asset performance).",
        "",
        "| Lev | SL | Assets | Min ann log-ret | Mean ann log-ret | Max bust | Min Sharpe | "
        "PASS-asset count |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in robust.iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        lines.append(
            f"| {int(r['leverage'])}x | {sl} | {int(r['assets'])} | "
            f"{_fmt_pct(float(r['min_median_ann_log_ret']))} | "
            f"{_fmt_pct(float(r['mean_median_ann_log_ret']))} | "
            f"{_fmt_pct(float(r['max_bust']))} | "
            f"{r['min_sharpe']:+.3f} | "
            f"{int(r['n_pass'])} |"
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-windows", type=int, default=200)
    p.add_argument("--name", default="gate1_preview")
    p.add_argument("--assets", default="BTC,ETH,SOL")
    args = p.parse_args()

    console = Console()
    per_asset: dict[str, pd.DataFrame] = {}
    assets = [a.strip().upper() for a in args.assets.split(",") if a.strip()]

    for asset in assets:
        df, fr = _load_asset(asset)
        funding_present = fr is not None
        console.print(
            f"\n[cyan]{asset}[/cyan]: {df.shape[0]:,} bars "
            f"({df.index.min().date()} -> {df.index.max().date()}), "
            f"funding={'YES' if funding_present else 'NO'}"
        )

        spec = GridSpec(
            leverages=LEVERAGES,
            stop_losses=STOP_LOSSES,
            take_profits=TAKE_PROFITS,
            strategies=(STRATEGY,),
            n_seeds=args.n_windows,
        )
        grid = run_grid_realdata(
            df, spec,
            window_bars=24 * WINDOW_DAYS,
            n_windows=args.n_windows,
            seed=SEED,
            n_workers=1,
            show_progress=False,
            funding_rates=fr,
        )
        raw_path = settings.results_dir / f"{args.name}_{asset}_n{args.n_windows}.parquet"
        grid.to_parquet(raw_path, compression="zstd")

        summary = _summarize(grid, window_days=float(WINDOW_DAYS),
                              asset=asset, funding_present=funding_present)
        summary_path = settings.results_dir / f"{args.name}_{asset}_n{args.n_windows}_summary.parquet"
        summary.to_parquet(summary_path, compression="zstd")
        per_asset[asset] = summary
        _render(console, summary, asset, funding_present)

    report_path = settings.results_dir / f"{args.name}_n{args.n_windows}_report.md"
    _write_markdown(per_asset, report_path, args.n_windows)
    console.print(f"\n[green]report[/green]: {report_path}")

    pass_summary = ", ".join(
        f"{a}={int(per_asset[a]['gate0_pass'].sum())}/{len(per_asset[a])}"
        for a in per_asset
    )
    console.print(f"[bold]preview PASS counts: {pass_summary}[/bold]")


if __name__ == "__main__":
    main()
