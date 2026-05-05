"""パフォーマンス指標と Risk of Ruin 推定。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def returns_from_equity(equity: pd.Series) -> pd.Series:
    """equity曲線 -> 単純収益率系列。"""
    return equity.pct_change().dropna()


def sharpe_ratio(equity: pd.Series, periods_per_year: int = 365 * 24) -> float:
    """年率シャープ。periods_per_year は時間足:24*365、日足:365 等。"""
    r = returns_from_equity(equity)
    if r.empty or r.std() == 0:
        return float("nan")
    return float(np.sqrt(periods_per_year) * r.mean() / r.std(ddof=0))


def sortino_ratio(equity: pd.Series, periods_per_year: int = 365 * 24) -> float:
    r = returns_from_equity(equity)
    downside = r[r < 0]
    if r.empty or downside.std() == 0:
        return float("nan")
    return float(np.sqrt(periods_per_year) * r.mean() / downside.std(ddof=0))


def drawdown_series(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0


def max_drawdown(equity: pd.Series) -> float:
    return float(drawdown_series(equity).min())


def calmar_ratio(equity: pd.Series, periods_per_year: int = 365 * 24) -> float:
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return float("nan")
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    n_years = len(equity) / periods_per_year
    if n_years <= 0:
        return float("nan")
    cagr = (1.0 + total_return) ** (1.0 / n_years) - 1.0
    return cagr / mdd


def survival_rate(final_equities: np.ndarray, initial: float, threshold: float = 0.10) -> float:
    """N シミュレーションの最終 equity 配列から、initial*threshold 以上を維持した比率。"""
    return float((final_equities >= initial * threshold).mean())


def risk_of_ruin(p_win: float, b: float, *, ruin_pct: float = 0.5, n_units: int | None = None) -> float:
    """Kelly 風 Risk of Ruin の閉形式近似。

    p_win : 勝率、b: payoff ratio (勝ち1単位/負け1単位)、
    ruin_pct: 破産しきい値(例 0.5 = 半減で破産)。

    `(1 - edge) / (1 + edge)` を使う Vince の単純近似。edge < 0 のとき必ず破産する。
    """
    edge = p_win - (1 - p_win) / b
    if edge <= 0:
        return 1.0
    base = (1 - edge) / (1 + edge)
    units = n_units if n_units is not None else int(round(1.0 / ruin_pct))
    return float(base ** units)
