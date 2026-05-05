"""自律エージェントの 1 サイクルを単独プロセスで実行する。

外側のオーケストレータから subprocess で呼び出される想定。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from leverage_survival_lab.agent import Hypothesis, initial_hypotheses
from leverage_survival_lab.backtest.grid import GridSpec, run_grid_realdata, save_grid_results
from leverage_survival_lab.config import settings


def synthesize_insight(grid_df: pd.DataFrame, hypothesis: Hypothesis) -> str:
    valid = grid_df[grid_df["error"].isna()] if "error" in grid_df.columns else grid_df
    n = len(valid)
    if hypothesis.name == "H1":
        survival = float((valid[valid["leverage"] == 100.0]["final_equity"] >= 100_000).mean())
        return (f"H1: 100x 30d survival = {survival*100:.2f}% (N={n}). "
                f"100x bust rate = {float(valid[valid['leverage']==100.0]['is_bust'].mean())*100:.1f}%")
    if hypothesis.name == "H4":
        bust_50 = float(valid[valid["leverage"] == 50.0]["is_bust"].mean())
        bust_100 = float(valid[valid["leverage"] == 100.0]["is_bust"].mean())
        return f"H4: bust@50x={bust_50*100:.1f}% bust@100x={bust_100*100:.1f}% (N={n})"
    high = valid[valid["leverage"] >= 50.0]
    low = valid[valid["leverage"] <= 5.0]
    return f"{hypothesis.name}: bust@<=5x={float(low['is_bust'].mean())*100:.1f}% bust@>=50x={float(high['is_bust'].mean())*100:.1f}% N={n}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=50)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--hypothesis-idx", type=int, required=True)
    p.add_argument("--out-log", default="results/agent_log.jsonl")
    args = p.parse_args()

    hypotheses = initial_hypotheses()
    h = hypotheses[args.hypothesis_idx]

    df = pd.read_parquet(args.data)
    spec = GridSpec(n_seeds=args.n_windows)
    started = datetime.now(timezone.utc)
    out_df = run_grid_realdata(df, spec, n_windows=args.n_windows, seed=args.seed,
                                n_workers=1, show_progress=False)
    finished = datetime.now(timezone.utc)
    grid_path = save_grid_results(out_df, f"agent_cycle_{h.name}_seed{args.seed}")
    insight = synthesize_insight(out_df, h)

    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": {"name": h.name, "description": h.description,
                       "operationalization": h.operationalization,
                       "rejection_rule": h.rejection_rule},
        "grid_spec": {"n_windows": args.n_windows, "leverages": list(spec.leverages),
                      "stop_losses": list(spec.stop_losses), "strategies": list(spec.strategies),
                      "risk_fractions": list(spec.risk_fractions)},
        "seed": args.seed,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_sec": (finished - started).total_seconds(),
        "grid_path": str(grid_path),
        "insight": insight,
    }
    Path(args.out_log).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"OK cycle hypothesis={h.name} seed={args.seed} duration={rec['duration_sec']:.1f}s insight={insight}")


if __name__ == "__main__":
    main()
