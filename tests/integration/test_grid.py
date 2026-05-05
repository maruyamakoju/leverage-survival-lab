"""グリッド実験の小規模スモークテスト。"""
from __future__ import annotations

import pytest

from leverage_survival_lab.backtest.grid import GridSpec, run_grid_synthetic


@pytest.mark.integration
def test_run_grid_synthetic_small() -> None:
    spec = GridSpec(
        leverages=(2.0, 100.0),
        stop_losses=(-0.02, None),
        take_profits=(None,),
        strategies=("random",),
        n_seeds=3,
    )
    df = run_grid_synthetic(spec, n_bars=240, n_workers=1, show_progress=False)
    # 2 lev × 2 sl × 1 tp × 1 strat × 3 seeds = 12 行
    assert len(df) == 12
    assert {"final_equity", "is_bust", "max_drawdown", "sharpe"}.issubset(df.columns)
    # 100x の方が破産率が高いはず
    p_bust_100 = df[df["leverage"] == 100.0]["is_bust"].mean()
    p_bust_2 = df[df["leverage"] == 2.0]["is_bust"].mean()
    assert p_bust_100 >= p_bust_2
