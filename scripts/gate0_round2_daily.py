"""Gate 0 Round 2 Step A — timeframe round (1h -> 1d / 1w resample).

Round 2 でも 1h で全 fail だった `trend_filtered_sma` を、より長い時間軸 (daily,
weekly) で再評価する。SMA(20/50/200) のパラメータ意味が変わる (timeframe ごとに
20日/50日/200日 vs 20時間/50時間/200時間) ので、これは「同戦略の異なる時間軸への
適用」となる。pre-reg 上は許容範囲 (Round 2 は戦略を trend_filtered_sma に固定済み)。

判定基準は Round 2 と同一 (median ann log-ret > 0 / DSR > 0.95 / bust < 5%)。
funding は daily/weekly では bar 解像度が荒いので、注入時の 8h 単位の効果は丸まる
(BacktestConfig は reindex(fill=0) するため、bar 内最初の funding tick だけ反映)。
これは粗い近似だが、Round 1/2 との比較可能性を優先して同経路を使う。
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
STRATEGY = "trend_filtered_sma"
SEED = 20260507

GATE0_THRESHOLDS = {
    "median_annual_log_return": 0.0,
    "deflated_sharpe_prob": 0.95,
    "bust_rate_window_50pct": 0.05,
}

# (timeframe, window_bars, window_days)
# Daily SMA(200) needs >=200 bars warmup; weekly with same SMA params needs >=200 weeks
# (~4 years) which would bend the pre-reg by forcing param changes.
# Keep daily-only with windows that include warmup + meaningful in-sample period.
TIMEFRAME_CONFIGS = [
    ("1d", 240, 240.0),  # ~8 months, SMA200 warmup + 40-bar runway
    ("1d", 365, 365.0),  # 1 year
    ("1d", 540, 540.0),  # 1.5 years
]


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    return out


def _summarize(grid_df: pd.DataFrame, *, window_days: float, timeframe: str) -> pd.DataFrame:
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
            "timeframe": timeframe,
            "window_days": window_days,
            "leverage": float(leverage),
            "stop_loss": sl,
            "take_profit": tp,
            "n": n,
            "median_annual_log_return": float(np.median(ann_log_ret)),
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


def _render(console: Console, df: pd.DataFrame, label: str) -> None:
    table = Table(title=label)
    for col in ["lev", "SL", "n", "med_ann", "Sharpe", "DSR", "bust_w", "Gate0"]:
        table.add_column(col)
    for _, r in df.iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        table.add_row(
            f"{int(r['leverage'])}x", sl, str(int(r["n"])),
            _fmt_pct(float(r["median_annual_log_return"])),
            f"{r['sample_sharpe']:+.2f}",
            f"{r['deflated_sharpe_prob']:.3f}" if not pd.isna(r["deflated_sharpe_prob"]) else "nan",
            _fmt_pct(float(r["bust_rate_window_50pct"])),
            "PASS" if bool(r["gate0_pass"]) else "fail",
        )
    console.print(table)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-windows", type=int, default=200)
    p.add_argument("--name", default="gate0_round2_daily")
    args = p.parse_args()

    console = Console()
    px_1h = pd.read_parquet("data/raw/binance_BTCUSDT_1h.parquet")
    fr = pd.read_parquet("data/raw/binance_BTCUSDT_funding.parquet")["rate"]
    console.print(
        f"[cyan]source[/cyan]: 1h {px_1h.shape[0]:,} bars, funding {fr.shape[0]:,} ticks"
    )

    px_by_tf: dict[str, pd.DataFrame] = {
        "1d": _resample(px_1h, "1D"),
        "1w": _resample(px_1h, "1W"),
    }
    for tf, df in px_by_tf.items():
        console.print(f"[cyan]{tf}[/cyan] {df.shape[0]:,} bars "
                       f"({df.index.min().date()} -> {df.index.max().date()})")

    all_summaries: list[pd.DataFrame] = []

    for tf, window_bars, window_days in TIMEFRAME_CONFIGS:
        df = px_by_tf[tf]
        # サンプル数チェック: window_bars が df と比して小さすぎないか
        if window_bars >= len(df) - 10:
            console.print(f"[yellow]skip[/yellow] {tf} w={window_bars}: not enough bars")
            continue

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
        label = f"{STRATEGY} {tf} window={window_bars}bars (~{int(window_days)}d)"
        console.print(f"\n[bold]{label}[/bold] running {n_cells:,} simulations")
        grid = run_grid_realdata(
            df, spec,
            window_bars=window_bars,
            n_windows=args.n_windows,
            seed=SEED,
            n_workers=1,
            show_progress=False,
            funding_rates=fr,
        )
        suffix = f"{tf}_{window_bars}bars"
        raw_path = settings.results_dir / f"{args.name}_{suffix}_n{args.n_windows}.parquet"
        grid.to_parquet(raw_path, compression="zstd")

        summary = _summarize(grid, window_days=window_days, timeframe=tf)
        summary_path = settings.results_dir / f"{args.name}_{suffix}_n{args.n_windows}_summary.parquet"
        summary.to_parquet(summary_path, compression="zstd")
        all_summaries.append(summary)
        _render(console, summary, label)

    combined = pd.concat(all_summaries, ignore_index=True) if all_summaries else pd.DataFrame()
    if not combined.empty:
        combined_path = settings.results_dir / f"{args.name}_combined_n{args.n_windows}.parquet"
        combined.to_parquet(combined_path, compression="zstd")
        console.print(f"\n[green]combined[/green]: {combined_path}")

        n_pass = int(combined["gate0_pass"].sum())
        console.print(f"[bold]Total PASS: {n_pass} / {len(combined)} cells[/bold]")
        if n_pass:
            console.print("[bold green]Gate 0 暫定通過 cell あり[/bold green]")
            _render(console, combined[combined["gate0_pass"]], "PASS cells")
        else:
            console.print("[bold red]全 timeframe × 全 cell fail[/bold red]")


if __name__ == "__main__":
    main()
