"""Claude Code 自律エージェントの Demo ループ — 1 サイクル分。

実用上は Claude Code が外側から駆動する想定だが、ここでは「人間が編集可能な
意思決定モジュール」をプレースホルダで埋め、ループの形を実証する。

サイクル:
1. 現在の history から次の問いを選ぶ
2. grid spec を生成
3. 実験を回す
4. 結果を分析
5. insight を history に append
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd
from rich.console import Console

from leverage_survival_lab.agent import Experiment, History, Hypothesis, initial_hypotheses
from leverage_survival_lab.backtest.grid import GridSpec, run_grid_realdata, save_grid_results
from leverage_survival_lab.config import settings


def synthesize_insight(grid_df: pd.DataFrame, hypothesis: Hypothesis) -> str:
    """grid 結果から insight 文字列を組み立てる(超単純な式)。"""
    n = len(grid_df)
    high_lev = grid_df[grid_df["leverage"] >= 50.0]
    high_bust = float(high_lev["is_bust"].mean()) if len(high_lev) else float("nan")
    summary = (
        f"hypothesis={hypothesis.name}; "
        f"n_sims={n}; "
        f"bust_rate@>=50x={high_bust*100:.1f}%; "
        f"non_bust_count@>=50x={int((~high_lev['is_bust']).sum()) if len(high_lev) else 0}"
    )
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=50)
    p.add_argument("--cycles", type=int, default=1)
    args = p.parse_args()

    console = Console()
    history = History()
    hypotheses = initial_hypotheses()

    df = pd.read_parquet(args.data)

    for cycle in range(args.cycles):
        # 1. 次の問い
        h = hypotheses[cycle % len(hypotheses)]
        console.print(f"[bold cyan]Cycle {cycle+1}[/bold cyan]: investigating {h.name}: {h.description}")

        # 2. grid spec
        spec = GridSpec(n_seeds=args.n_windows)

        # 3. 実験
        started = datetime.now(timezone.utc)
        out_df = run_grid_realdata(
            df, spec, n_windows=args.n_windows, seed=42 + cycle, n_workers=1, show_progress=False,
        )
        finished = datetime.now(timezone.utc)
        out_path = save_grid_results(out_df, f"agent_cycle{cycle+1}_{h.name}")

        # 4. 分析 → insight
        insight = synthesize_insight(out_df, h)
        console.print(f"  insight: {insight}")

        # 5. log
        history.append(Experiment(
            hypothesis=h, grid_spec={"n_windows": args.n_windows, "spec": spec.__dict__},
            seed=42 + cycle, started_at=started, finished_at=finished,
            grid_path=out_path, insight=insight,
        ))

    console.print(f"[green]agent log[/green]: {history.log_path}")
    console.print(f"experiments: {len(history.experiments)}")


if __name__ == "__main__":
    main()
