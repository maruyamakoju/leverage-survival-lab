"""H1〜H4 を grid 実験結果から検定する。

H1: 100倍レバの30日生存率 < 10%(全戦略 × 全損切水準で)
H2: 各レバ倍率に最適な損切ライン(内点解)が存在する
H3: 正Sharpe戦略でも、レバが閾値を超えると期待log-returnが負に転じる
H4: 50倍以上ではナイーブ戦略の生存率がランダム戦略と統計的有意差なし

入力: results/grid_*.parquet (grid runner の出力)
出力: results/hypothesis_test_<name>.md (markdown)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from leverage_survival_lab.analysis.stats import (
    bonferroni,
    survival_summary,
    two_proportion_z,
    wilson_ci,
)


def test_h1(grid_df: pd.DataFrame, *, threshold: float = 0.10, initial: float = 1_000_000.0,
            target_lev: float = 100.0, target_pct: float = 0.10) -> dict:
    """H1: 100x で全 (strategy, stop_loss) セルの生存率 CI 上限が 10% 未満か。"""
    sub = grid_df[grid_df["leverage"] == target_lev]
    cells = sub.groupby(["strategy_name", "stop_loss"], dropna=False)
    rows = []
    n_cells_violating = 0
    for (strat, sl), g in cells:
        successes = int((g["final_equity"] >= initial * threshold).sum())
        ci = wilson_ci(successes, len(g))
        violates = ci.hi >= target_pct
        n_cells_violating += int(violates)
        rows.append({"strategy": strat, "stop_loss": sl, "n": len(g),
                     "survival": ci.p, "ci_hi": ci.hi, "violates_h1": violates})
    detail = pd.DataFrame(rows)
    return {
        "supported": n_cells_violating == 0,
        "n_total_cells": len(rows),
        "n_violating": n_cells_violating,
        "max_ci_hi": float(detail["ci_hi"].max()) if len(detail) else float("nan"),
        "detail": detail,
    }


def test_h2(grid_df: pd.DataFrame, *, threshold: float = 0.10, initial: float = 1_000_000.0) -> dict:
    """H2: 各 (strategy, leverage) で生存率最大の stop_loss が内点解(端点でない)か。"""
    summary = survival_summary(grid_df, threshold=threshold, initial=initial)
    rows = []
    for (strat, L), g in summary.groupby(["strategy", "leverage"]):
        g = g.copy()
        # stop_loss を順序付け: -0.005, -0.01, -0.02, -0.05, NaN(=なし)
        order = {-0.005: 0, -0.01: 1, -0.02: 2, -0.05: 3}
        g["sl_order"] = g["stop_loss"].map(lambda x: order.get(x, 4))
        g = g.sort_values("sl_order")
        if len(g) < 3:
            continue
        idx_max = int(g["survival"].idxmax())
        max_pos = int(g.loc[idx_max, "sl_order"])
        is_interior = 0 < max_pos < (len(g) - 1)
        rows.append({"strategy": strat, "leverage": L,
                     "best_stop_loss": g.loc[idx_max, "stop_loss"],
                     "best_survival": g.loc[idx_max, "survival"],
                     "interior": is_interior})
    detail = pd.DataFrame(rows)
    return {
        "supported_pct": float(detail["interior"].mean()) if len(detail) else float("nan"),
        "detail": detail,
    }


def test_h3(grid_df: pd.DataFrame, *, threshold: float = 0.10, initial: float = 1_000_000.0) -> dict:
    """H3: 各戦略で、平均終端 log-return が正→負に転じるレバ閾値を推定。"""
    g = grid_df.copy()
    g["log_return"] = np.log(np.maximum(g["final_equity"], 1.0) / initial)
    means = g.groupby(["strategy_name", "leverage"])["log_return"].mean().reset_index()
    rows = []
    for strat, m in means.groupby("strategy_name"):
        m = m.sort_values("leverage")
        # 期待log-returnが正→負に変わる最初のレバ
        prev_pos = m.iloc[0]["log_return"] > 0
        crossover = None
        for _, r in m.iterrows():
            if prev_pos and r["log_return"] <= 0:
                crossover = float(r["leverage"])
                break
            prev_pos = r["log_return"] > 0
        rows.append({"strategy": strat, "crossover_leverage": crossover,
                     "mean_log_ret_lev1": float(m.iloc[0]["log_return"])})
    detail = pd.DataFrame(rows)
    return {"detail": detail}


def test_h4(grid_df: pd.DataFrame, *, threshold: float = 0.10, initial: float = 1_000_000.0,
            high_lev: tuple[float, ...] = (50.0, 100.0)) -> dict:
    """H4: 高レバ領域(50x以上)でナイーブ戦略 vs ランダム の生存率に有意差がないか。"""
    pvals = []
    rows = []
    for L in high_lev:
        rand = grid_df[(grid_df["leverage"] == L) & (grid_df["strategy_name"] == "random")]
        n_rand = len(rand)
        succ_rand = int((rand["final_equity"] >= initial * threshold).sum())
        p_rand = succ_rand / n_rand if n_rand else float("nan")
        for strat in ["sma_cross", "rsi", "bollinger", "breakout"]:
            sub = grid_df[(grid_df["leverage"] == L) & (grid_df["strategy_name"] == strat)]
            n = len(sub)
            succ = int((sub["final_equity"] >= initial * threshold).sum())
            p = succ / n if n else float("nan")
            z, pval = two_proportion_z(p, n, p_rand, n_rand)
            pvals.append(pval)
            rows.append({"leverage": L, "strategy": strat, "p_strategy": p, "p_random": p_rand,
                         "z": z, "p_value": pval})
    detail = pd.DataFrame(rows)
    rejects, alpha_adj = bonferroni([r if not np.isnan(r) else 1.0 for r in pvals], alpha=0.05)
    detail["reject_null"] = rejects
    return {
        "supported": not any(rejects),  # H4は「有意差なし」を主張
        "alpha_adj": alpha_adj,
        "detail": detail,
    }


def write_report(results: dict, name: str, out_path: Path) -> None:
    md: list[str] = [f"# Hypothesis Test Report — {name}", ""]

    md.append("## H1 — 100x leverage 30日生存率 < 10%")
    h1 = results["H1"]
    md.append(f"- Supported: **{h1['supported']}**")
    md.append(f"- Cells violating: {h1['n_violating']} / {h1['n_total_cells']}")
    md.append(f"- Max CI upper bound: {h1['max_ci_hi']:.4f}")
    md.append("")
    md.append("```")
    md.append(h1["detail"].to_string(index=False))
    md.append("```")
    md.append("")

    md.append("## H2 — 各レバ倍率に最適な損切ラインが内点解として存在")
    h2 = results["H2"]
    md.append(f"- Interior solution rate: {h2['supported_pct']*100:.1f}%")
    md.append("")
    md.append("```")
    md.append(h2["detail"].to_string(index=False))
    md.append("```")
    md.append("")

    md.append("## H3 — 戦略エッジが消失する閾値レバ")
    h3 = results["H3"]
    md.append("```")
    md.append(h3["detail"].to_string(index=False))
    md.append("```")
    md.append("")

    md.append("## H4 — 50x以上でナイーブ戦略 vs ランダム の有意差なし(Bonferroni 補正)")
    h4 = results["H4"]
    md.append(f"- Supported (no significant difference): **{h4['supported']}**")
    md.append(f"- Adjusted α: {h4['alpha_adj']:.5f}")
    md.append("")
    md.append("```")
    md.append(h4["detail"].to_string(index=False))
    md.append("```")
    md.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="results/grid_*.parquet")
    p.add_argument("--name", required=True, help="output report name")
    args = p.parse_args()

    grid_df = pd.read_parquet(args.input)
    grid_df = grid_df[grid_df["error"].isna()] if "error" in grid_df.columns else grid_df

    results = {
        "H1": test_h1(grid_df),
        "H2": test_h2(grid_df),
        "H3": test_h3(grid_df),
        "H4": test_h4(grid_df),
    }
    out = Path("results") / f"hypothesis_test_{args.name}.md"
    write_report(results, args.name, out)
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
