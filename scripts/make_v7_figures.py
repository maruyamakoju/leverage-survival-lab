"""V7 公開素材用の図表を生成する。

出力先: results/figures/v7_*.png
- v7_round_tally.png      : 5 ラウンド集計 (0/195)
- v7_sharpe_ceiling.png   : trend_filtered_sma の sample Sharpe 天井 (window × lev × SL)
- v7_cross_asset.png      : 1x SL=-5% を BTC/ETH/SOL で並べた Sharpe / Median ann log-ret
- v7_funding_growth.png   : window が伸びるほど funding cost が累積するグラフ
- v7_round1_overview.png  : Round 1 の戦略別 median ann log-ret 分布
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT_DIR = Path("results/figures")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- 1) 5 ラウンド集計 ---------------------------------------------------------

def fig_round_tally() -> None:
    rounds = [
        ("Round 1\n(5 strategies)", 0, 75),
        ("Round 2\n(trend_sma\nx 3 windows)", 0, 36),
        ("Gate 1 preview\n(BTC/ETH/SOL)", 0, 36),
        ("Timeframe\n(daily resample)", 0, 36),
        ("Round 3\n(FundingFlip)", 0, 12),
    ]
    labels = [r[0] for r in rounds]
    passes = [r[1] for r in rounds]
    totals = [r[2] for r in rounds]
    fails = [t - p for t, p in zip(totals, passes, strict=True)]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(labels))
    ax.bar(x, fails, color="#cc4444", label="fail")
    ax.bar(x, passes, bottom=fails, color="#33aa55", label="PASS")
    for i, (p, t) in enumerate(zip(passes, totals, strict=True)):
        ax.text(i, t + 1.5, f"{p}/{t}", ha="center", fontsize=11, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("cells evaluated", fontsize=11)
    ax.set_title("Stage-Gate Round Tally — 0 / 195 cells PASS\n"
                  "(Gate 0 = median ann log-ret > 0 AND DSR > 0.95 AND bust < 5%)",
                  fontsize=12)
    ax.set_ylim(0, max(totals) * 1.15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right")
    fig.tight_layout()
    out = OUT_DIR / "v7_round_tally.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"saved {out}")


# ---- 2) trend_filtered_sma の Sharpe 天井 (3 window 比較) ----------------------

def fig_sharpe_ceiling() -> None:
    parts: list[pd.DataFrame] = []
    for w in (30, 90, 180):
        df = pd.read_parquet(f"results/gate0_round2_btc_w{w}_n200_summary.parquet")
        df = df[["leverage", "stop_loss", "sample_sharpe"]].copy()
        df["window"] = f"{w}d"
        parts.append(df)
    combined = pd.concat(parts, ignore_index=True)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    for ax, w in zip(axes, (30, 90, 180), strict=True):
        sub = combined[combined["window"] == f"{w}d"].copy()
        sub["sl_label"] = sub["stop_loss"].apply(
            lambda v: "None" if pd.isna(v) else f"{v * 100:.0f}%"
        )
        pivot = sub.pivot(index="sl_label", columns="leverage", values="sample_sharpe")
        # row order: None, -2%, -5% (top to bottom)
        pivot = pivot.reindex(["None", "-2%", "-5%"])
        pivot = pivot.reindex(sorted(pivot.columns), axis=1)
        im = ax.imshow(pivot.values, vmin=-1.5, vmax=1.0, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels([f"{int(c)}x" for c in pivot.columns])
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index)
        ax.set_title(f"window = {w}d", fontsize=11)
        ax.set_xlabel("leverage")
        if w == 30:
            ax.set_ylabel("stop loss")
        for i, _sl in enumerate(pivot.index):
            for j, _lev in enumerate(pivot.columns):
                v = pivot.iloc[i, j]
                if pd.isna(v):
                    continue
                ax.text(j, i, f"{v:+.2f}", ha="center", va="center",
                         color="black" if abs(v) < 0.6 else "white", fontsize=9)
    cbar = fig.colorbar(im, ax=axes, fraction=0.04, pad=0.02)
    cbar.set_label("sample Sharpe (after-cost)")
    fig.suptitle(
        "trend_filtered_sma sample Sharpe never exceeds +0.64 — "
        "real-trading needs >1.0", fontsize=12, y=1.03
    )
    out = OUT_DIR / "v7_sharpe_ceiling.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out}")


# ---- 3) cross-asset Sharpe 反転 (1x SL=-5%) -----------------------------------

def fig_cross_asset() -> None:
    rows: list[dict] = []
    for asset in ("BTC", "ETH", "SOL"):
        df = pd.read_parquet(f"results/gate1_preview_{asset}_n200_summary.parquet")
        cell = df[(df["leverage"] == 1.0) & (df["stop_loss"] == -0.05)]
        r = cell.iloc[0]
        rows.append({
            "asset": asset,
            "median_ann_ret": r["median_annual_log_return"],
            "sharpe": r["sample_sharpe"],
            "bust": r["bust_rate_window_50pct"],
            "funding_present": bool(r["funding_present"]),
        })
    d = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    # (a) Median ann log-ret
    ax = axes[0]
    colors = ["#4488cc" if a == "BTC" else "#bbbbbb" for a in d["asset"]]
    bars = ax.bar(d["asset"], d["median_ann_ret"] * 100, color=colors)
    for bar, v in zip(bars, d["median_ann_ret"], strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                 f"{v * 100:+.1f}%", ha="center", fontsize=10)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Median annualised log-return")
    ax.set_title("Median return (positive on all 3)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # (b) Sample Sharpe
    ax = axes[1]
    sharpe_colors = ["#33aa55" if s > 0 else "#cc4444" for s in d["sharpe"]]
    bars = ax.bar(d["asset"], d["sharpe"], color=sharpe_colors)
    for bar, v in zip(bars, d["sharpe"], strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + (0.03 if v > 0 else -0.06),
                 f"{v:+.2f}", ha="center", fontsize=10)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Sample Sharpe (after-cost)")
    ax.set_title("Sharpe flips negative on ETH")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.suptitle(
        "trend_filtered_sma 1x SL=-5%: BTC edge does not transfer to ETH "
        "(cross-asset preview, ETH/SOL funding-free)",
        fontsize=11, y=1.01
    )
    fig.tight_layout()
    out = OUT_DIR / "v7_cross_asset.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out}")


# ---- 4) funding cost growth (window 期間依存) ---------------------------------

def fig_funding_growth() -> None:
    rows: list[dict] = []
    for w in (30, 90, 180):
        df = pd.read_parquet(f"results/gate0_round2_btc_w{w}_n200_summary.parquet")
        for _, r in df.iterrows():
            rows.append({
                "window_days": w,
                "leverage": int(r["leverage"]),
                "stop_loss": "None" if pd.isna(r["stop_loss"]) else f"{r['stop_loss'] * 100:.0f}%",
                "median_funding_pct": float(r["median_total_funding_pct"]) * 100,
            })
    d = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(9, 5))
    # Plot lines for each (lev, SL) pair: too many — instead pick representative:
    # 1x SL=-5%, 1x SL=None, 2x SL=-5%, 5x SL=-2%
    picks = [(1, "-5%"), (1, "None"), (2, "-5%"), (3, "-5%"), (5, "-2%")]
    for lev, sl in picks:
        sub = d[(d["leverage"] == lev) & (d["stop_loss"] == sl)]
        if sub.empty:
            continue
        sub = sub.sort_values("window_days")
        ax.plot(sub["window_days"], sub["median_funding_pct"], marker="o",
                 label=f"{lev}x SL={sl}")
    ax.set_xlabel("window length (days)")
    ax.set_ylabel("median funding cost (% of equity)")
    ax.set_title("Funding cost grows roughly linearly with holding window")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out = OUT_DIR / "v7_funding_growth.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"saved {out}")


# ---- 5) Round 1 全戦略 median ann log-ret 散布 -------------------------------

def fig_round1_overview() -> None:
    df = pd.read_parquet("results/gate0_btc_n200_summary.parquet")
    fig, ax = plt.subplots(figsize=(10, 5.5))

    strategies = sorted(df["strategy"].unique())
    palette = plt.cm.tab10.colors  # type: ignore[attr-defined]
    color_map = {s: palette[i % 10] for i, s in enumerate(strategies)}

    # x = (lev, sl) jitter, y = median annual log return
    # We just plot per-strategy
    for s in strategies:
        sub = df[df["strategy"] == s].copy()
        ann = sub["median_annual_log_return"] * 100
        # x position: leverage + small jitter for SL
        sl_offset = sub["stop_loss"].apply(
            lambda v: 0 if pd.isna(v) else (-0.15 if v == -0.02 else 0.15)
        )
        x = sub["leverage"] + sl_offset
        ax.scatter(x, ann, color=color_map[s], label=s, s=60, alpha=0.85,
                    edgecolors="white")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("leverage")
    ax.set_ylabel("median annualised log-return (%)")
    ax.set_title("Round 1 — median annualised log-return by strategy & leverage\n"
                  "(positive medians exist; Sharpe / DSR fails them)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xticks([1, 2, 3, 5, 10])
    ax.set_xticklabels(["1x", "2x", "3x", "5x", "10x"])
    ax.set_ylim(-50, 50)  # clip extreme outliers for readability
    ax.legend(loc="lower left", fontsize=9, ncol=2)
    fig.tight_layout()
    out = OUT_DIR / "v7_round1_overview.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"saved {out}")


def main() -> None:
    fig_round_tally()
    fig_sharpe_ceiling()
    fig_cross_asset()
    fig_funding_growth()
    fig_round1_overview()


if __name__ == "__main__":
    main()
