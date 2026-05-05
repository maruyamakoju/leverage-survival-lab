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
    """grid 結果から insight 文字列を組み立てる。"""
    valid = grid_df[grid_df["error"].isna()] if "error" in grid_df.columns else grid_df
    n = len(valid)
    high_lev = valid[valid["leverage"] >= 50.0]
    low_lev = valid[valid["leverage"] <= 5.0]

    if hypothesis.name == "H1":
        survival = float((valid[valid["leverage"] == 100.0]["final_equity"] >= 100_000).mean())
        return (f"H1: 100x 30d survival = {survival*100:.2f}% (N={n}). "
                f"100x bust rate = {float(valid[valid['leverage']==100.0]['is_bust'].mean())*100:.1f}%")
    elif hypothesis.name == "H4":
        bust_50 = float(valid[valid["leverage"] == 50.0]["is_bust"].mean())
        bust_100 = float(valid[valid["leverage"] == 100.0]["is_bust"].mean())
        return f"H4: bust@50x={bust_50*100:.1f}% bust@100x={bust_100*100:.1f}% (no strategy advantage at high lev)"
    else:
        high_bust = float(high_lev["is_bust"].mean()) if len(high_lev) else float("nan")
        low_bust = float(low_lev["is_bust"].mean()) if len(low_lev) else float("nan")
        return f"{hypothesis.name}: bust@<=5x={low_bust*100:.1f}% bust@>=50x={high_bust*100:.1f}% N={n}"


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
