"""ワンショットで主要結果を再現するエントリポイント。

順序:
1. データ取得(既存ファイルがあれば skip)
2. 実データ N=500 grid 実験
3. 仮説検定レポート
4. ヒートマップ・レポート PNG 生成
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], *, env: str = "") -> None:
    print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        print(f"!! exited with {res.returncode}")
        sys.exit(res.returncode)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-windows", type=int, default=500)
    p.add_argument("--name", default="reproduced_run")
    p.add_argument("--skip-fetch", action="store_true", help="OHLCV 再取得を skip")
    args = p.parse_args()

    py = sys.executable
    data_path = Path("data/raw/binance_BTCUSDT_1h.parquet")

    # 1. データ取得
    if not args.skip_fetch and not data_path.exists():
        print("[1/4] fetching OHLCV...")
        run([py, "-m", "leverage_survival_lab.data.fetch", "ohlcv",
             "--symbol", "BTC/USDT", "--tf", "1h", "--since", "2020-01-01"])
    else:
        print(f"[1/4] data exists at {data_path}, skipping fetch")

    # 2. グリッド実験
    print(f"[2/4] running grid experiment N={args.n_windows}...")
    run([py, "-X", "faulthandler", "scripts/run_realdata_experiment.py",
         "--n-windows", str(args.n_windows), "--name", args.name])

    grid_path = f"results/grid_{args.name}.parquet"

    # 3. 仮説検定
    print("[3/4] running hypothesis tests...")
    run([py, "scripts/test_hypotheses.py", "--input", grid_path, "--name", args.name])

    # 4. レポート
    print("[4/4] generating report...")
    run([py, "scripts/generate_report.py", "--input", grid_path, "--name", args.name])

    print(f"\n✓ done. see:")
    print(f"  - results/grid_{args.name}.parquet")
    print(f"  - results/hypothesis_test_{args.name}.md")
    print(f"  - results/report_{args.name}.md")
    print(f"  - results/figures/{args.name}/heatmap_*.png")


if __name__ == "__main__":
    main()
