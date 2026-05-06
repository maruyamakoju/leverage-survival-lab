"""Gate 0 評価 — cost-aware backtest with funding rates injected.

[docs/stage_gate.md](../docs/stage_gate.md) の Gate 0 (戦略の経済的成立性) を測定する。
funding rate は `BacktestConfig.funding_rates` 経由で注入される — 既存 grid runner の
default は funding なし (rate=0) だが、本スクリプトは `binance_BTCUSDT_funding.parquet`
の実 funding を必ず注入する。

合否判定 (Gate 0):
  - median_annual_log_return > 0     (window log-return を 365.25/window_days で年率化)
  - deflated_sharpe_prob   > 0.95    (Bonferroni 補正済 DSR で「本物」確率)
  - bust_rate_30d_50pct    < 0.05    (30日 window 内で equity が初期の 50% を割った割合)

bust_rate は本来 250 営業日基準だが、本ラウンドは 30日 window で proxy として測る
(window を伸ばす round 2 で再評価)。
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
    "bust_rate_30d_50pct": 0.05,
}


def _load_btc(asset: str = "BTC") -> tuple[pd.DataFrame, pd.Series]:
    px_path = Path(f"data/raw/binance_{asset}USDT_1h.parquet")
    fr_path = Path(f"data/raw/binance_{asset}USDT_funding.parquet")
    if not px_path.exists():
        raise SystemExit(f"price parquet missing: {px_path}")
    df = pd.read_parquet(px_path)
    if not fr_path.exists():
        raise SystemExit(f"funding parquet missing: {fr_path}")
    fr = pd.read_parquet(fr_path)["rate"]
    return df, fr


def _summarize(grid_df: pd.DataFrame, *, window_days: float) -> pd.DataFrame:
    """グリッド結果から (strategy, leverage, sl, tp) 別の Gate 0 メトリクスを集計。"""
    valid = grid_df[grid_df["error"].isna()] if "error" in grid_df.columns else grid_df
    initial = settings.initial_equity_usdt

    rows: list[dict] = []
    cells = list(valid.groupby(
        ["strategy_name", "leverage", "stop_loss", "take_profit"], dropna=False
    ))
    n_trials = max(1, len(cells))

    for (strategy, leverage, sl, tp), g in cells:
        n = len(g)
        finals = g["final_equity"].to_numpy()
        log_ret_window = np.log(np.clip(finals / initial, 1e-9, None))
        annualization = 365.25 / window_days
        annual_log_ret = log_ret_window * annualization

        # Sharpe: window 単位の log-return を独立サンプルとみなして Sharpe を算出
        # (各 window が独立な 30日サンプルなので、これはシミュ単位 Sharpe)
        if log_ret_window.std(ddof=0) > 0:
            sample_sharpe = float(
                math.sqrt(annualization) * log_ret_window.mean() / log_ret_window.std(ddof=0)
            )
        else:
            sample_sharpe = float("nan")

        dsr_prob = (
            deflated_sharpe(sample_sharpe, n_trials=n_trials, n_periods=n)
            if not math.isnan(sample_sharpe)
            else float("nan")
        )

        bust_30d = float((g["min_equity_ratio"] < 0.5).mean())
        bust_threshold_finals = float((finals < initial * 0.5).mean())
        liq_rate = float((g["n_liquidations"] > 0).mean())

        rows.append({
            "strategy": strategy,
            "leverage": float(leverage),
            "stop_loss": sl,
            "take_profit": tp,
            "n": n,
            "median_window_log_return": float(np.median(log_ret_window)),
            "median_annual_log_return": float(np.median(annual_log_ret)),
            "mean_annual_log_return": float(np.mean(annual_log_ret)),
            "sample_sharpe": sample_sharpe,
            "deflated_sharpe_prob": float(dsr_prob) if not math.isnan(dsr_prob) else float("nan"),
            "bust_rate_30d_50pct": bust_30d,
            "final_below_50pct": bust_threshold_finals,
            "liq_rate": liq_rate,
            "median_total_fees_pct": float(g["total_fees"].median() / initial),
            "median_total_funding_pct": float(g["total_funding"].median() / initial),
        })

    out = pd.DataFrame(rows)
    out["pass_return"] = out["median_annual_log_return"] > GATE0_THRESHOLDS["median_annual_log_return"]
    out["pass_dsr"] = out["deflated_sharpe_prob"] > GATE0_THRESHOLDS["deflated_sharpe_prob"]
    out["pass_bust"] = out["bust_rate_30d_50pct"] < GATE0_THRESHOLDS["bust_rate_30d_50pct"]
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


def _render(console: Console, df: pd.DataFrame, n: int = 25) -> None:
    table = Table(title=f"Gate 0 evaluation (top {min(n, len(df))} cells by annual log-return)")
    for col in [
        "strategy", "lev", "SL", "TP", "n",
        "med_ann_log_ret", "DSR_prob", "bust_30d", "fees%", "fund%", "Gate 0",
    ]:
        table.add_column(col)
    for _, r in df.head(n).iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        tp = "None" if pd.isna(r["take_profit"]) else _fmt_pct(float(r["take_profit"]))
        table.add_row(
            str(r["strategy"]),
            f"{int(r['leverage'])}x",
            sl,
            tp,
            str(int(r["n"])),
            _fmt_pct(float(r["median_annual_log_return"])),
            _fmt_prob(float(r["deflated_sharpe_prob"])),
            _fmt_pct(float(r["bust_rate_30d_50pct"])),
            _fmt_pct(float(r["median_total_fees_pct"])),
            _fmt_pct(float(r["median_total_funding_pct"])),
            "PASS" if bool(r["gate0_pass"]) else "fail",
        )
    console.print(table)


def _write_markdown(df: pd.DataFrame, *, out_path: Path, n_windows: int, asset: str,
                     window_days: float, fee_taker: float, fee_slippage: float) -> None:
    pass_cells = df[df["gate0_pass"]].copy()
    lines = [
        f"# Gate 0 Report — {asset} (N={n_windows} windows, {int(window_days)}-day each)",
        "",
        "Cost model:",
        f"- taker fee = {fee_taker * 100:.3f}%",
        f"- per-leg slippage = {fee_slippage * 100:.3f}%",
        f"- funding = injected from `data/raw/binance_{asset}USDT_funding.parquet`",
        "",
        "Pass criteria (all three required):",
        f"- median annualized log-return > {GATE0_THRESHOLDS['median_annual_log_return']:.0%}",
        f"- Deflated Sharpe probability > {GATE0_THRESHOLDS['deflated_sharpe_prob']:.0%}"
        f" (Bonferroni n_trials = {len(df)})",
        f"- 30-day bust rate (equity < 50% of initial) < "
        f"{GATE0_THRESHOLDS['bust_rate_30d_50pct']:.0%}",
        "",
        f"## Gate 0 Pass Cells ({len(pass_cells)} / {len(df)})",
        "",
    ]

    if len(pass_cells) == 0:
        lines.append(
            "**No cell passed Gate 0.** "
            "This reinforces H3 (1x ですら手数料負けで負期待値) with funding now included. "
            "Either Gate 0 thresholds need to be reconsidered (and that change "
            "pre-registered), or no naive strategy in the current zoo is economically viable "
            "on BTC perp at low/mid leverage with realistic costs."
        )
    else:
        lines.extend([
            "| Strategy | Lev | SL | TP | n | Median ann log-ret | DSR prob "
            "| Bust 30d | Median fees | Median funding |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for _, r in pass_cells.iterrows():
            sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
            tp = "None" if pd.isna(r["take_profit"]) else _fmt_pct(float(r["take_profit"]))
            lines.append(
                f"| {r['strategy']} | {int(r['leverage'])}x | {sl} | {tp} | "
                f"{int(r['n'])} | {_fmt_pct(float(r['median_annual_log_return']))} | "
                f"{_fmt_prob(float(r['deflated_sharpe_prob']))} | "
                f"{_fmt_pct(float(r['bust_rate_30d_50pct']))} | "
                f"{_fmt_pct(float(r['median_total_fees_pct']))} | "
                f"{_fmt_pct(float(r['median_total_funding_pct']))} |"
            )

    lines.extend(["", "## All Cells (top 30 by annual log-return)", "",
                   "| Strategy | Lev | SL | TP | Med ann log-ret | DSR prob "
                   "| Bust 30d | Final<50% | Liq | Gate 0 |",
                   "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for _, r in df.head(30).iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else _fmt_pct(float(r["stop_loss"]))
        tp = "None" if pd.isna(r["take_profit"]) else _fmt_pct(float(r["take_profit"]))
        lines.append(
            f"| {r['strategy']} | {int(r['leverage'])}x | {sl} | {tp} | "
            f"{_fmt_pct(float(r['median_annual_log_return']))} | "
            f"{_fmt_prob(float(r['deflated_sharpe_prob']))} | "
            f"{_fmt_pct(float(r['bust_rate_30d_50pct']))} | "
            f"{_fmt_pct(float(r['final_below_50pct']))} | "
            f"{_fmt_pct(float(r['liq_rate']))} | "
            f"{'PASS' if bool(r['gate0_pass']) else 'fail'} |"
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--asset", default="BTC")
    p.add_argument("--n-windows", type=int, default=200)
    p.add_argument("--window-days", type=int, default=30)
    p.add_argument("--seed", type=int, default=20260507)
    p.add_argument("--n-workers", type=int, default=1)
    p.add_argument("--name", default="gate0_btc")
    args = p.parse_args()

    console = Console()
    df, fr = _load_btc(args.asset)
    console.print(
        f"[cyan]{args.asset}[/cyan]: 1h {df.shape[0]:,} bars "
        f"({df.index.min().date()} -> {df.index.max().date()}), "
        f"funding {fr.shape[0]:,} ticks"
    )

    spec = GridSpec(
        leverages=(1, 2, 3, 5, 10),
        stop_losses=(None, -0.02, -0.05),
        take_profits=(None,),
        strategies=(
            "sma_cross", "rsi", "bollinger", "breakout", "trend_filtered_sma",
        ),
        n_seeds=args.n_windows,
    )
    n_cells = (
        len(spec.leverages) * len(spec.stop_losses) * len(spec.take_profits)
        * len(spec.strategies) * args.n_windows
    )
    console.print(f"running {n_cells:,} simulations")

    grid = run_grid_realdata(
        df, spec,
        window_bars=24 * args.window_days,
        n_windows=args.n_windows,
        seed=args.seed,
        n_workers=args.n_workers,
        show_progress=False,
        funding_rates=fr,
    )

    raw_path = settings.results_dir / f"{args.name}_n{args.n_windows}.parquet"
    grid.to_parquet(raw_path, compression="zstd")
    console.print(f"[green]raw[/green]: {raw_path}")

    summary = _summarize(grid, window_days=float(args.window_days))
    summary_path = settings.results_dir / f"{args.name}_n{args.n_windows}_summary.parquet"
    summary.to_parquet(summary_path, compression="zstd")
    console.print(f"[green]summary[/green]: {summary_path}")

    # FeeModel デフォルト値を読む(report 用)
    from leverage_survival_lab.engine.leverage import FeeModel
    fm = FeeModel()
    report_path = settings.results_dir / f"{args.name}_n{args.n_windows}_report.md"
    _write_markdown(
        summary, out_path=report_path, n_windows=args.n_windows, asset=args.asset,
        window_days=float(args.window_days),
        fee_taker=fm.taker_fee, fee_slippage=fm.slippage,
    )
    console.print(f"[green]report[/green]: {report_path}")

    _render(console, summary, n=25)
    pass_count = int(summary["gate0_pass"].sum())
    console.print(f"\n[bold]Gate 0 pass cells: {pass_count} / {len(summary)}[/bold]")


if __name__ == "__main__":
    main()
