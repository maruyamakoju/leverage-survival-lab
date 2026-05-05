"""複数資産で同じ実験を回し、H1 のクロス資産妥当性を検証する。

使用例:
    python scripts/run_cross_asset.py --assets BTC,ETH,SOL --n-windows 200
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console

from leverage_survival_lab.analysis.stats import wilson_ci
from leverage_survival_lab.config import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--assets", default="BTC,ETH,SOL")
    p.add_argument("--n-windows", type=int, default=200)
    p.add_argument("--seed-base", type=int, default=42)
    args = p.parse_args()

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    py = sys.executable
    summary_rows: list[dict] = []

    for asset in args.assets.split(","):
        asset = asset.strip()
        data_path = Path(f"data/raw/binance_{asset}USDT_1h.parquet")
        if not data_path.exists():
            console.print(f"[yellow]skip[/yellow] {asset}: missing {data_path}")
            continue

        name = f"cross_{asset}_n{args.n_windows}"
        out_path = settings.results_dir / f"grid_{name}.parquet"
        if out_path.exists():
            console.print(f"[grey]skip {asset}: already done[/grey]")
        else:
            # 最大3回リトライ
            ok = False
            for attempt in range(3):
                seed = args.seed_base + attempt * 100
                cmd = [py, "-X", "faulthandler", "-W", "ignore::RuntimeWarning",
                       "scripts/run_realdata_experiment.py",
                       "--data", str(data_path),
                       "--n-windows", str(args.n_windows),
                       "--seed", str(seed),
                       "--name", name]
                console.print(f"[cyan]{asset}[/cyan] attempt {attempt+1} (seed={seed})")
                res = subprocess.run(cmd, capture_output=False)
                if res.returncode == 0 and out_path.exists():
                    ok = True
                    break
            if not ok:
                console.print(f"[red]{asset}: FAILED after 3 attempts[/red]")
                continue

        # H1 サマリ
        df = pd.read_parquet(out_path)
        df = df[df["error"].isna()] if "error" in df.columns else df
        for L in [25.0, 50.0, 100.0]:
            sub = df[df["leverage"] == L]
            if sub.empty:
                continue
            successes = int((sub["final_equity"] >= settings.initial_equity_usdt * 0.10).sum())
            ci = wilson_ci(successes, len(sub))
            summary_rows.append({
                "asset": asset, "leverage": int(L), "n": len(sub),
                "survival": ci.p, "ci_lo": ci.lo, "ci_hi": ci.hi,
            })

    if summary_rows:
        sdf = pd.DataFrame(summary_rows)
        out_summary = settings.results_dir / f"cross_asset_summary_n{args.n_windows}.parquet"
        sdf.to_parquet(out_summary, compression="zstd")
        console.print(f"\n[green]cross-asset summary[/green] saved: {out_summary}")
        console.print(sdf.to_string(index=False))


if __name__ == "__main__":
    main()
