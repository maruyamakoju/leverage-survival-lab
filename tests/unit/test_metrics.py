"""指標関数のテスト。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from leverage_survival_lab.analysis.metrics import (
    drawdown_series,
    max_drawdown,
    risk_of_ruin,
    survival_rate,
)


def test_max_drawdown_basic() -> None:
    eq = pd.Series([1.0, 1.2, 0.9, 1.1, 0.6])
    # peak=1.2, low=0.6 → -0.5
    assert math.isclose(max_drawdown(eq), -0.5, rel_tol=1e-9)


def test_drawdown_series_zero_at_new_high() -> None:
    eq = pd.Series([1.0, 1.1, 1.2])
    dd = drawdown_series(eq)
    assert (dd == 0.0).all()


def test_survival_rate_threshold() -> None:
    finals = np.array([100, 50, 9, 200, 11])
    # initial=100, threshold=0.10 → >=10 が4件 → 0.8
    assert math.isclose(survival_rate(finals, initial=100.0, threshold=0.10), 0.8)


def test_risk_of_ruin_negative_edge_is_one() -> None:
    # p=0.4, b=1 → edge = 0.4 - 0.6 = -0.2 < 0 → 必ず破産
    assert risk_of_ruin(p_win=0.4, b=1.0) == 1.0


def test_risk_of_ruin_positive_edge() -> None:
    r = risk_of_ruin(p_win=0.55, b=1.0, n_units=2)
    assert 0.0 < r < 1.0
