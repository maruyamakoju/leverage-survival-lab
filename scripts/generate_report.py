"""グリッド結果から包括的なマークダウン+PNGレポートを生成する。

入力: results/grid_<name>.parquet
出力:
  - results/report_<name>.md
  - results/figures/<name>/heatmap_<strategy>.png
  - results/figures/<name>/equity_samples_<strategy>_<lev>.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from leverage_survival_lab.analysis.plots import survival_heatmap
from leverage_survival_lab.analysis.stats import survival_summary, wilson_ci


def fmt_pct(x: float) -> str:
    return f"{x*100:.2f}%" if not np.isnan(x) else "—"


def render_md(name: str, df: pd.DataFrame, fig_dir: Path) -> str:
    summary = survival_summary(df)
    md: list[str] = [
        f"# Leverage Survival Lab — Report: {name}",
        "",
        "## 概要",
        "",
        f"- 総シミュレーション数: **{len(df):,}**",
        f"- 戦略: {', '.join(sorted(df['strategy_name'].unique()))}",
        f"- レバレッジ水準: {sorted(df['leverage'].unique())}",
        f"- 損切水準: {sorted(df['stop_loss'].dropna().unique())} + None",
        f"- データ識別子例: `{df['data_id'].iloc[0]}`",
        "",
        "## 仮説別サマリ",
        "",
        "### H1 — 100倍レバ生存率は損切ルール問わず < 10%",
        "",
    ]

    h1 = summary[summary["leverage"] == 100.0]
    md.append("| Strategy | Stop Loss | N | Survival | CI Upper | Violates H1 |")
    md.append("|----------|-----------|---|----------|----------|-------------|")
    for _, r in h1.iterrows():
        sl = "None" if pd.isna(r["stop_loss"]) else f"{r['stop_loss']*100:.2f}%"
        md.append(f"| {r['strategy']} | {sl} | {int(r['n'])} | {fmt_pct(r['survival'])} | {fmt_pct(r['ci_hi'])} | "
                  f"{'YES' if r['ci_hi'] >= 0.10 else 'no'} |")
    md.append("")

    md.append("### H4 — 50x以上で戦略間の生存率有意差なし(粗集計)")
    md.append("")
    md.append("| Lev | Strategy | Survival | CI |")
    md.append("|-----|----------|----------|----|")
    high = summary[summary["leverage"].isin([50.0, 100.0])]
    for _, r in high.iterrows():
        md.append(f"| {int(r['leverage'])}x | {r['strategy']} | {fmt_pct(r['survival'])} | "
                  f"[{fmt_pct(r['ci_lo'])}, {fmt_pct(r['ci_hi'])}] |")
    md.append("")

    md.append("## 戦略別ヒートマップ")
    md.append("")
    fig_dir.mkdir(parents=True, exist_ok=True)
    for strategy in sorted(df["strategy_name"].unique()):
        out = fig_dir / f"heatmap_{strategy}.png"
        survival_heatmap(summary, strategy=strategy,
                        title=f"30-day Survival Rate — {strategy} (N={summary[summary['strategy']==strategy]['n'].iloc[0]})",
                        save_to=out)
        plt.close("all")
        rel = out.relative_to(fig_dir.parent.parent)
        md.append(f"### {strategy}")
        md.append("")
        md.append(f"![{strategy}]({rel.as_posix()})")
        md.append("")

    md.append("## レバ × 平均終端残高")
    md.append("")
    md.append("| Lev | Mean Final Equity (USDT) | Median | % Bust |")
    md.append("|-----|-------------------------|--------|--------|")
    for L, g in df.groupby("leverage"):
        md.append(f"| {int(L)}x | {g['final_equity'].mean():,.0f} | "
                  f"{g['final_equity'].median():,.0f} | {g['is_bust'].mean()*100:.1f}% |")
    md.append("")

    md.append("## 注釈・限界")
    md.append("")
    md.append("- 本シミュレータは Isolated 単一ポジションを前提としている")
    md.append("- スリッページモデルは notional 比固定(深度ベースではない)")
    md.append("- 実データは Binance USDT-M Perp BTC/USDT のみ")
    md.append("- 結果は再現可能 (seed, params, commit hash) — 詳細は `docs/hypotheses.md`")
    return "\n".join(md)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--name", required=True)
    args = p.parse_args()

    df = pd.read_parquet(args.input)
    df = df[df["error"].isna()] if "error" in df.columns else df

    base = Path("results")
    fig_dir = base / "figures" / args.name
    md = render_md(args.name, df, fig_dir)
    out = base / f"report_{args.name}.md"
    out.write_text(md, encoding="utf-8")
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
