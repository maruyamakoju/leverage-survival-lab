"""仮説検定・信頼区間ユーティリティ。"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class WilsonCI:
    p: float
    lo: float
    hi: float
    n: int


def wilson_ci(successes: int, n: int, *, alpha: float = 0.05) -> WilsonCI:
    """Wilson score 信頼区間(生存率の CI)。"""
    if n == 0:
        return WilsonCI(p=float("nan"), lo=float("nan"), hi=float("nan"), n=0)
    z = stats.norm.ppf(1 - alpha / 2)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return WilsonCI(p=p, lo=max(0.0, centre - half), hi=min(1.0, centre + half), n=n)


def two_proportion_z(p1: float, n1: int, p2: float, n2: int) -> tuple[float, float]:
    """2標本比率のZ検定 (z, p_two_sided)。"""
    if n1 == 0 or n2 == 0:
        return (float("nan"), float("nan"))
    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return (float("inf") if p1 != p2 else 0.0, 0.0 if p1 != p2 else 1.0)
    z = (p1 - p2) / se
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return (z, p)


def bonferroni(pvals: list[float], alpha: float = 0.05) -> tuple[list[bool], float]:
    """Bonferroni 補正。返り値: (棄却フラグ, 補正後α)"""
    m = len(pvals)
    a_adj = alpha / m
    return [p < a_adj for p in pvals], a_adj


def bh_fdr(pvals: list[float], alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg FDR 制御。返り値: 各検定の棄却フラグ。"""
    arr = np.array(pvals)
    m = len(arr)
    order = np.argsort(arr)
    ranked = arr[order]
    thresh = (np.arange(1, m + 1) / m) * alpha
    pass_mask = ranked <= thresh
    if not pass_mask.any():
        return [False] * m
    last_pass = int(np.where(pass_mask)[0].max())
    reject = np.zeros(m, dtype=bool)
    reject[order[: last_pass + 1]] = True
    return reject.tolist()


def deflated_sharpe(
    sharpe: float, *, n_trials: int, n_periods: int, skew: float = 0.0, kurt: float = 3.0
) -> float:
    """Bailey & López de Prado 'Deflated Sharpe Ratio' の確率(>0 で本物)。

    多重比較で偶然得られたとは言い難いかを 0..1 で返す。0.95 以上で「本物」と解釈。
    """
    if n_trials <= 1 or n_periods <= 1:
        return float("nan")
    sr0 = math.sqrt(2 * math.log(n_trials)) * (1.0 - 0.5772 / math.sqrt(2 * math.log(n_trials)))
    var = (1 - skew * sharpe + (kurt - 1) / 4 * sharpe**2) / (n_periods - 1)
    z = (sharpe - sr0) / math.sqrt(var) if var > 0 else float("nan")
    return float(stats.norm.cdf(z)) if not math.isnan(z) else float("nan")


def survival_summary(grid_df: pd.DataFrame, *, threshold: float = 0.10,
                      initial: float = 1_000_000.0) -> pd.DataFrame:
    """grid 結果から (strategy, leverage, stop_loss) 別の生存率と CI を集計。"""
    grouped = grid_df.groupby(["strategy_name", "leverage", "stop_loss"], dropna=False)
    rows = []
    for (s, L, sl), g in grouped:
        successes = int((g["final_equity"] >= initial * threshold).sum())
        n = len(g)
        ci = wilson_ci(successes, n)
        rows.append({
            "strategy": s,
            "leverage": L,
            "stop_loss": sl,
            "n": n,
            "survival": ci.p,
            "ci_lo": ci.lo,
            "ci_hi": ci.hi,
            "median_final": float(g["final_equity"].median()),
            "p_bust": float(g["is_bust"].mean()),
            "median_dd": float(g["max_drawdown"].median()),
        })
    return pd.DataFrame(rows).sort_values(["strategy", "leverage", "stop_loss"]).reset_index(drop=True)
