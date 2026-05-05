"""大規模実験を chunk に分割し、subprocess で実行してマージする。

Windows 環境で長時間プロセスが時々セグフォルトするため、複数の小さなプロセスに分けて
リスクを最小化する。各 chunk は独立な seed を持つ。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

from leverage_survival_lab.config import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--total-windows", type=int, default=2000)
    p.add_argument("--chunk-size", type=int, default=200)
    p.add_argument("--name", default="real_btc_chunked")
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    args = p.parse_args()

    py = sys.executable
    n_chunks = (args.total_windows + args.chunk_size - 1) // args.chunk_size
    chunk_paths: list[Path] = []

    for c in range(n_chunks):
        seed = 42 + c
        chunk_name = f"{args.name}_chunk{c:02d}"
        chunk_path = settings.results_dir / f"grid_{chunk_name}.parquet"

        if chunk_path.exists():
            print(f"[chunk {c+1}/{n_chunks}] already done: {chunk_path}")
            chunk_paths.append(chunk_path)
            continue

        # 最大3回リトライ
        ok = False
        for attempt in range(3):
            cmd = [py, "-X", "faulthandler", "-W", "ignore::RuntimeWarning",
                   "scripts/run_realdata_experiment.py",
                   "--n-windows", str(args.chunk_size),
                   "--seed", str(seed + attempt * 1000),
                   "--name", chunk_name,
                   "--data", args.data]
            print(f"[chunk {c+1}/{n_chunks}] attempt {attempt+1}: seed={seed + attempt * 1000}")
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and chunk_path.exists():
                ok = True
                break
            print(f"  -> failed (returncode {res.returncode}), retrying...")

        if not ok:
            print(f"[chunk {c+1}/{n_chunks}] FAILED after 3 attempts; skipping")
            continue
        chunk_paths.append(chunk_path)

    # マージ
    if not chunk_paths:
        print("no successful chunks")
        sys.exit(1)
    dfs = [pd.read_parquet(p) for p in chunk_paths]
    merged = pd.concat(dfs, ignore_index=True)
    out = settings.results_dir / f"grid_{args.name}.parquet"
    merged.to_parquet(out, compression="zstd")
    print(f"\n✓ merged {len(chunk_paths)} chunks into {out} ({len(merged):,} rows)")


if __name__ == "__main__":
    main()
