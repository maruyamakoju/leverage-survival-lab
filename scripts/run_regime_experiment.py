"""市場レジームごとに H1 の生存率を再評価する。

レジーム: trend_up / trend_down / range / crash
各レジームから 30日窓を抽出 → モンテカルロ → H1 検定
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console
from rich.logging import RichHandler

from leverage_survival_lab.analysis.stats import survival_summary, wilson_ci
from leverage_survival_lab.backtest.grid import GridSpec, _data_for_seed, _run_one, GridTask
from leverage_survival_lab.config import settings
from leverage_survival_lab.data.quality import detect_regimes


def classify_window(sub: pd.DataFrame) -> str:
    """単一 30日窓を直接分類。"""
    total_ret = float(sub["close"].iloc[-1] / sub["close"].iloc[0] - 1.0)
    # 当該窓内 max drawdown
    peak = sub["close"].cummax()
    dd = (sub["close"] / peak - 1.0).min()
    if dd <= -0.30:
        return "crash"
    if total_ret >= 0.20:
        return "trend_up"
    if total_ret <= -0.20:
        return "trend_down"
    return "range"


def find_regime_windows(
    df: pd.DataFrame, regime: str, *, window_bars: int, n_windows: int, seed: int = 0,
) -> list[tuple[str, pd.DataFrame]]:
    """指定レジームに分類される 30日窓を抽出。"""
    rng = np.random.default_rng(seed)
    out: list[tuple[str, pd.DataFrame]] = []
    n = len(df)
    attempts = 0
    seen_starts: set[int] = set()
    while len(out) < n_windows and attempts < n_windows * 200:
        s = int(rng.integers(0, n - window_bars))
        if s in seen_starts:
            attempts += 1
            continue
        seen_starts.add(s)
        sub = df.iloc[s : s + window_bars]
        if classify_window(sub) == regime:
            ts0 = df.index[s]
            out.append((f"{regime}_{ts0.strftime('%Y%m%d')}", sub.copy()))
        attempts += 1
    return out


def run_single_regime(
    df: pd.DataFrame, regime: str, *, n_windows: int, seed: int, console: Console,
) -> pd.DataFrame:
    spec = GridSpec()
    windows = find_regime_windows(df, regime, window_bars=24*30, n_windows=n_windows, seed=seed)
    if not windows:
        console.print(f"[yellow]no windows found for {regime}[/yellow]")
        return pd.DataFrame()
    console.print(f"[cyan]{regime}[/cyan]: {len(windows)} windows")

    import itertools
    rows: list[dict] = []
    for L, sl, tp, strat, (label, sub) in itertools.product(
        spec.leverages, spec.stop_losses, spec.take_profits, spec.strategies, windows
    ):
        t = GridTask(strategy_name=strat, leverage=float(L), stop_loss=sl, take_profit=tp,
                     seed=hash(label) & 0x7fffffff, risk_fraction=spec.risk_fraction,
                     data_id=label)
        r = _run_one(t, sub)
        r["regime"] = regime
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--regime", required=True, help="単一レジーム指定")
    p.add_argument("--name", default="regime")
    args = p.parse_args()

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(console=console)])

    df = pd.read_parquet(args.data)
    console.print(f"loaded {len(df)} bars")

    out_df = run_single_regime(df, args.regime, n_windows=args.n_windows, seed=args.seed, console=console)
    out_path = settings.results_dir / f"grid_{args.name}_{args.regime}.parquet"
    out_df.to_parquet(out_path, compression="zstd")
    console.print(f"[green]saved[/green]: {out_path} (rows: {len(out_df)})")

    # H1 サマリ
    if len(out_df) > 0:
        h1 = out_df[out_df["leverage"] == 100.0]
        successes = int((h1["final_equity"] >= settings.initial_equity_usdt * 0.10).sum())
        ci = wilson_ci(successes, len(h1))
        console.print(f"\n=== H1: 100x in regime={args.regime} ===")
        console.print(f"  N={len(h1)}  survival={ci.p*100:5.2f}%  CI=[{ci.lo*100:.2f}%, {ci.hi*100:.2f}%]")


if __name__ == "__main__":
    main()
