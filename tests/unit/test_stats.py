"""統計検定ユーティリティのテスト。"""
from __future__ import annotations

import math

import pandas as pd

from leverage_survival_lab.analysis.stats import (
    bh_fdr,
    bonferroni,
    deflated_sharpe,
    survival_summary,
    two_proportion_z,
    wilson_ci,
)


def test_wilson_ci_extremes() -> None:
    # 全部成功
    ci = wilson_ci(100, 100)
    assert ci.lo > 0.95
    assert math.isclose(ci.hi, 1.0, abs_tol=1e-9)
    # 全部失敗
    ci = wilson_ci(0, 100)
    assert math.isclose(ci.lo, 0.0, abs_tol=1e-9)
    assert ci.hi < 0.05


def test_wilson_ci_zero_n() -> None:
    ci = wilson_ci(0, 0)
    assert math.isnan(ci.p)


def test_two_proportion_z_significant() -> None:
    z, p = two_proportion_z(0.9, 1000, 0.5, 1000)
    assert abs(z) > 5
    assert p < 1e-6


def test_two_proportion_z_null() -> None:
    z, p = two_proportion_z(0.5, 1000, 0.5, 1000)
    assert math.isclose(z, 0.0)
    assert math.isclose(p, 1.0)


def test_bonferroni_basic() -> None:
    rejects, alpha_adj = bonferroni([0.001, 0.04, 0.06], alpha=0.05)
    assert rejects == [True, False, False]
    assert math.isclose(alpha_adj, 0.05 / 3)


def test_bh_fdr_basic() -> None:
    # すべて 0.5 → 棄却なし
    assert bh_fdr([0.5, 0.5, 0.5]) == [False, False, False]
    # 1つだけ強い
    rejects = bh_fdr([0.001, 0.5, 0.5, 0.5])
    assert rejects[0] is True
    assert all(not r for r in rejects[1:])


def test_deflated_sharpe_runs() -> None:
    p = deflated_sharpe(2.0, n_trials=50, n_periods=500)
    assert 0.0 <= p <= 1.0


def test_survival_summary_aggregates() -> None:
    df = pd.DataFrame({
        "strategy_name": ["random"] * 6,
        "leverage": [10] * 6,
        "stop_loss": [-0.02] * 6,
        "final_equity": [1_500_000, 0, 100_000, 50_000, 0, 1_200_000],
        "is_bust": [False, True, True, True, True, False],
        "max_drawdown": [-0.1, -1.0, -0.9, -0.95, -1.0, -0.2],
    })
    out = survival_summary(df, threshold=0.10, initial=1_000_000.0)
    assert len(out) == 1
    row = out.iloc[0]
    # 100% 以上残った: 2件 (1.5M, 1.2M), 10%以上 (>=100k) は3件 (1.5M, 100k, 1.2M)
    assert math.isclose(row["survival"], 3 / 6)
